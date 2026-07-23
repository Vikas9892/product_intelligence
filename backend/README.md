# Backend — Multi-Modal Product Intelligence Engine

FastAPI backend service. This document covers **Milestone 1 (Backend
Skeleton)**, **Milestone 2 (Configuration Management)**, **Milestone 3
(Logging)**, and **Milestone 4 (FastAPI Application Factory)**: project
structure, dependency management, tooling, typed/validated settings,
centralized logging, and the app factory + lifespan wiring.
No API endpoints, database models, or AI/business logic exist yet — that is
intentional. See [Why no code yet?](#why-no-code-yet) below.

## Project overview

This service will eventually ingest multi-modal product data (text +
images), generate embeddings, run hybrid vector/keyword search, and expose
LLM-assisted metadata, duplicate detection, and pricing intelligence over a
FastAPI HTTP API. Milestone 1 establishes the foundation everything else is
built on: a repo that lints, type-checks, tests, and installs the same way
on every machine and in CI, before a single line of business logic exists.

## Folder structure

```
backend/
├── app/
│   ├── main.py            # ASGI entrypoint: `app = create_app()`, what uvicorn serves
│   ├── application.py     # `create_app()` factory: builds and configures the FastAPI instance
│   ├── lifespan.py        # Startup/shutdown logic wired via FastAPI's lifespan API
│   ├── api/                # HTTP route definitions (FastAPI routers) — empty until Milestone 5
│   ├── core/               # App-wide concerns: settings, logging, security, startup/shutdown
│   │   ├── constants.py    # Fixed, non-configurable values (enums, prefixes, insecure-default marker)
│   │   ├── paths.py        # Centralized filesystem paths (backend root, storage, uploads, logs)
│   │   ├── settings.py     # Typed/validated settings schema (BaseModel groups + BaseSettings root)
│   │   ├── config.py       # Singleton accessor: `from app.core.config import settings`
│   │   └── logging.py      # Centralized logging: `from app.core.logging import get_logger`
│   ├── services/          # Business logic, orchestration between repositories/external calls
│   ├── repositories/      # Data access layer (DB, vector store, cache) behind an interface
│   ├── models/             # ORM / persistence models
│   ├── schemas/            # Pydantic request/response schemas (API contracts)
│   ├── workers/            # Background jobs / async task consumers
│   ├── middleware/         # ASGI middleware (request logging, correlation IDs, etc.) — empty until later
│   ├── dependencies/       # FastAPI dependency-injection providers
│   └── utils/              # Small stateless helpers shared across layers
├── tests/                  # pytest test suite, mirrors the app/ package layout
├── scripts/              # One-off / maintenance scripts (not part of the importable app)
├── docs/                 # Design notes, ADRs, phase write-ups
├── pyproject.toml        # Single source of truth: dependencies + tool config
├── uv.lock               # Locked, reproducible dependency versions (commit this)
├── README.md             # This file
├── .python-version       # Pins the interpreter uv provisions (3.12)
├── .gitignore             # Backend-specific ignore rules
└── .env.example           # Template for local environment variables
```

Each layer under `app/` has a single responsibility so that later
milestones add files into an already-agreed structure instead of inventing
one under time pressure: routes call services, services call repositories,
repositories touch the database/vector store/cache, and schemas define what
crosses the HTTP boundary. `core/` and `dependencies/` wire these layers
together; `middleware/`, `workers/`, and `utils/` are cross-cutting.

## Why no code yet?

Adding `main.py` on day one is how projects end up with untested,
unformatted, unstructured code that "works" but can't be safely extended.
Instead, Milestone 1 fixes the *process* first — dependency locking,
formatting, linting, type-checking, testing, and git hooks — so that every
file added in Milestones 2–13 is held to the same bar automatically instead
of relying on someone remembering to run `black` before committing.

## Every file explained

**Root of the repo** (`Product_Intelligence_Platform/`):

| File | Purpose |
|---|---|
| `.pre-commit-config.yaml` | Registers git hooks (ruff, black, mypy, whitespace/large-file/secret checks) that run automatically on `git commit`, scoped to `backend/`. |
| `.editorconfig` | Cross-editor formatting defaults (indent size, line endings, final newline) so VS Code/PyCharm/vim agree without per-developer config. |
| `.gitignore` | Repo-wide ignore rules (venvs, caches, `.env`, OS files); also reserves entries for a future `frontend/`. |
| `Makefile` | One-word entrypoints (`make install/run/lint/format/typecheck/test/clean`) that wrap the underlying `uv` commands. |
| `README.md` | Project overview and phase roadmap. |

**Inside `backend/`:**

| File | Purpose |
|---|---|
| `pyproject.toml` | Declares the package, its runtime dependencies (`fastapi`, `uvicorn`, `pydantic-settings`), dev dependencies, and all tool configuration (`[tool.ruff]`, `[tool.black]`, `[tool.mypy]`, `[tool.pytest.ini_options]`, `[tool.coverage.*]`). |
| `uv.lock` | Exact resolved versions of every dependency (direct and transitive) for reproducible installs; generated by `uv`, never hand-edited. |
| `.python-version` | Tells `uv` (and other tools that respect this file) to provision/use Python 3.12 for this project. |
| `.gitignore` | Backend-specific ignores (`.venv/`, caches, `.env`), redundant with the root file but keeps the backend self-contained if it's ever split into its own repo. |
| `.env.example` | Documents every variable the settings schema (`app/core/settings.py`) accepts, grouped and commented; copy to `.env` locally (`.env` is gitignored — see [Milestone 2](#milestone-2--configuration-design-decisions)). |
| `README.md` | This file. |
| `app/__init__.py` and one `__init__.py` per subpackage | Makes each directory an importable Python package and enables absolute imports like `from app.core import ...`. Deliberately empty. |
| `app/core/constants.py` | Fixed values the *code* decides, not per-deployment config: `Environment`/`LogLevel` enums, the `/api/v1` prefix, the obviously-fake default secret key, supported image extensions, pagination limits. |
| `app/core/paths.py` | The one place that knows where the backend root actually is (`Path(__file__).resolve().parents[2]`) and derives `storage/`, `storage/uploads/`, and `logs/` from it. Exposes `ensure_runtime_directories()` to create them — not called on import, so importing config stays side-effect-free and tests stay hermetic. |
| `app/core/settings.py` | The configuration *schema*: six `BaseModel` groups (`ApplicationSettings`, `DatabaseSettings`, `AIModelSettings`, `StorageSettings`, `SecuritySettings`, `LoggingSettings`) composed into one `Settings(BaseSettings)` root, with field-level and cross-field validation. No side effects — every class is directly constructible in a unit test. |
| `app/core/config.py` | The composition root: caches one `Settings()` instance via `@lru_cache` and exposes it as both `get_settings()` (for later FastAPI `Depends()` use) and the module-level `settings` singleton every other module should import. |
| `app/core/logging.py` | Configures the stdlib root logger (level from `settings.logging.level`, one console handler, a `timestamp \| level \| logger name \| message` formatter) and exposes `get_logger(name)` so any module gets a working, consistently formatted logger with zero setup. |
| `app/lifespan.py` | `lifespan(app)`: an `@asynccontextmanager` passed to `FastAPI(lifespan=...)`. Before `yield` (startup) it logs that the app is starting and calls `paths.ensure_runtime_directories()`; after `yield` (shutdown) it logs that the app is stopping. No database/AI connections yet — reserved for later milestones. |
| `app/application.py` | `create_app() -> FastAPI`: the only place `FastAPI(...)` is instantiated. Sets `title`/`description`/`version` from `settings.application` + `constants.DEFAULT_APP_DESCRIPTION`, wires in `lifespan`, then calls the private `_register_routers(app)` seam (currently empty) before returning the instance. |
| `app/main.py` | ASGI entrypoint: `app = create_app()`. This is the `app.main:app` target `uvicorn`/`make run` serve — one line of logic, everything real lives in `create_app()`. |
| `tests/__init__.py`, `tests/core/__init__.py` | Makes `tests/` and `tests/core/` packages so pytest resolves absolute imports the same way the app does; `tests/` mirrors `app/`'s layout. |
| `tests/test_environment.py` | A single sanity test (Python version check) proving the pytest + coverage pipeline actually runs. Real application tests start in Milestone 8. |
| `tests/core/test_paths.py` | Verifies path relationships (`UPLOAD_DIR` under `STORAGE_DIR`, etc.) and that `ensure_runtime_directories()` creates the right directories, using `monkeypatch` + `tmp_path` so it never touches the real filesystem. |
| `tests/core/test_settings.py` | Covers defaults, field validation (port range, minimum secret-key length, `SecretStr` not leaking into `repr()`), env-var overrides via nested `__` delimiters, and every production-safety rule in `Settings._validate_production_safety`. |
| `tests/core/test_config.py` | Confirms `get_settings()` returns the same cached object across calls, that `cache_clear()` forces a fresh one, and that the module-level `settings` singleton is a real `Settings` instance. |
| `tests/core/test_logging.py` | Covers level resolution (explicit override vs. `settings.logging.level`), the idempotent/`force` handler-installation behavior, the console formatter's exact output, and an end-to-end check that `get_logger(...).info(...)` really reaches stdout formatted correctly. An autouse fixture snapshots/restores the real root logger around every test so nothing here leaks into other tests. |
| `tests/test_lifespan.py` | Enters/exits `lifespan(app)` as an async context manager directly (no HTTP server needed) and asserts, via `caplog`, that the startup message logs before `yield` and the shutdown message logs after; asserts `paths.ensure_runtime_directories` is called exactly once on startup via `monkeypatch`. |
| `tests/test_application.py` | Confirms `create_app()` returns a `FastAPI` instance with `title`/`version`/`description` sourced from settings/constants, that each call returns an independent instance (no shared global), that no business routes are registered yet (only FastAPI's built-in docs/openapi routes), and — via `TestClient` as a context manager — that the app's startup/shutdown lifespan runs without raising. |
| `tests/test_main.py` | Confirms `app.main.app` is a real `FastAPI` instance with the expected title, proving the module-level `app = create_app()` entrypoint actually works end-to-end. |
| `scripts/.gitkeep`, `docs/.gitkeep` | Empty-directory placeholders — git does not track empty directories, so these keep the scaffold intact until real content lands. |

## Milestone 2 — configuration design decisions

**Why split `settings.py` and `config.py`?** `settings.py` is a pure
schema — six `BaseModel` groups plus one `BaseSettings` root with
validators — with zero side effects, so every class in it is directly
constructible in a unit test without touching real environment variables.
`config.py` is the composition root: the *only* place that actually calls
`Settings()`, and it caches that single instance with `@lru_cache`. Nothing
else in the app should ever call `Settings()` directly — always
`from app.core.config import settings`.

**Why grouped/nested settings instead of one flat class?** Six independent
concerns (application, database, AI models, storage, security, logging)
in one flat `BaseSettings` becomes an unreadable wall of fields with no
sense of ownership. Nesting each group as its own `BaseModel` field on the
root, combined with `pydantic-settings`' `env_nested_delimiter="__"`,
gives env vars like `SECURITY__SECRET_KEY` and `DATABASE__URL` that are
self-documenting about which group they belong to, while each group stays
independently testable and reusable (e.g. a future Celery worker could
import just `AIModelSettings` without pulling in HTTP-server config).

**Why does `Settings` validate production, not just parse it?**
`pydantic-settings` will happily hand you a `Settings` object where
`environment=production` but `secret_key` is still the insecure dev
default — it has no idea those two fields are related. The
`_validate_production_safety` model validator encodes that relationship
explicitly: in production, the secret key must be overridden, `debug` must
be `False`, and the database must not be SQLite. Getting any of these
wrong **fails application startup immediately** with a clear
`ValidationError` instead of silently running with a security or
correctness hole — cheap to hit in CI/staging, expensive to hit after a
production deploy.

**Why raise instead of auto-correcting (e.g. forcing `debug=False`)?**
Auto-correcting a misconfigured production environment hides the mistake —
the deploy "works" but the operator never learns their env vars were
wrong. Raising turns it into an immediate, loud boot failure instead.

**Why `SecretStr` for `secret_key` and `openai_api_key`?** Pydantic's
`SecretStr` masks the value in `repr()`/`str()`/logs (`SecretStr('*****')`)
so a stray `print(settings)` or exception traceback can't leak it; call
`.get_secret_value()` explicitly when the real value is actually needed.

**Why does `AIModelSettings` exist if no AI calls are made yet?** So that
when Milestone 8 (LLM Metadata Generation) needs an OpenAI key and model
names, `.env` and the settings schema don't have to change shape — only
the (currently empty) `AI_MODELS__OPENAI_API_KEY` needs a real value.

**Why is `paths.ensure_runtime_directories()` not called automatically?**
Creating directories is a side effect. If it ran on import, simply
`import app.core.config` in a test would create `storage/`/`logs/`
directories on disk as a side effect of importing a module — surprising
and something CI shouldn't need to clean up. It's explicit, and later
milestones call it once at application startup.

**Why enable the `pydantic.mypy` plugin?** Without it, mypy treats
`Settings.__init__` as a plain generated `__init__` and doesn't know about
`pydantic-settings`' private constructor kwargs (`_env_file=None`, used in
tests to ignore the real `.env` file) or that a `dict` passed for a nested
`BaseModel` field gets validated/coerced into that model at runtime. Adding
`plugins = ["pydantic.mypy"]` to `[tool.mypy]` teaches mypy pydantic's
actual runtime semantics, so `mypy .` stays clean under `strict = true`
without resorting to `# type: ignore` comments anywhere in the test suite.

## Milestone 3 — logging design decisions

**Why configure the root logger instead of a package-specific one?**
Every logger created anywhere in the process (`logging.getLogger(__name__)`
in any module, plus third-party libraries) propagates up to the root
logger by default. Configuring the root once means every logger in the
app — current and future — is consistently formatted without each module
having to configure itself.

**Why `get_logger(name)` instead of just documenting "use
`logging.getLogger(__name__)`"?** Both produce the same logger object —
`get_logger` is a thin wrapper — but it guarantees `configure_logging()`
has run first. Without it, a module that logs before anything has called
`configure_logging()` explicitly would emit unformatted messages via
Python's default handler-less root logger behavior. `get_logger` makes
"just works" the only outcome.

**Why is `configure_logging()` idempotent instead of always
reconfiguring?** It's called implicitly by *every* `get_logger()` call
(so the first one configures logging without any module needing to know
that). If it reconfigured every time, importing ten modules would mean
ten redundant handler rebuilds, and — if it appended instead of replaced —
duplicate handlers producing every log line multiple times. The
`_configured` guard makes repeat calls free; `force=True` exists for
callers (mainly tests, and later Milestone 4's app startup after settings
might have changed) that genuinely need to rebuild it.

**Why accept an explicit `level` override instead of only ever reading
`settings.logging.level`?** Reading from settings is the real production
path and the default when `level` is omitted. The override exists so unit
tests can exercise "what if the level were DEBUG" without mutating the
shared `settings` singleton (which would leak into other tests) — a pure
parameter is easier to reason about than temporarily monkeypatching global
config.

**Why is `_build_handlers()` a separate function that just returns a
list?** It's the one seam a file handler needs later: add
`_build_file_handler()` and append it to the list `_build_handlers()`
returns. `configure_logging()`, `get_logger()`, and every call site stay
untouched — satisfying "extend to file handlers without changing calling
code" without speculatively building file-handling (rotation, path from
`paths.LOG_DIR`, etc.) before anything needs it.

**Why is the module named `app/core/logging.py`, shadowing the stdlib
module name?** Python 3 imports are absolute by default, so `import
logging` inside this file unambiguously resolves to the stdlib module
(`sys.modules['logging']`), not itself (`sys.modules['app.core.logging']`)
— there's no actual collision. This is the same naming convention already
used for `app/core/config.py` and is common in production FastAPI
codebases; the alternative (`logging_config.py`) was considered but
rejected as more to type for no real disambiguation benefit.

**Why isn't `settings.logging.json_logs` wired up yet?** It's reserved
from Milestone 2 for structured/JSON logging, which this milestone
intentionally doesn't implement — the requirement was one consistent
console formatter. Adding a conditional JSON formatter now would be
building for a need that doesn't exist yet.

## Milestone 4 — application factory design decisions

**Why a `create_app()` factory instead of a module-level `app =
FastAPI()`?** A module-level `app` is a single shared, mutable object —
every test that imports it gets the *same* instance, so one test's state
(or a route registered by mistake) can leak into another. A factory
function returns a brand-new instance on every call, so
`tests/test_application.py` can build as many independent apps as it needs,
and later milestones can build differently-configured apps (e.g. for
integration tests) without any special-casing.

**Why three files (`main.py`, `application.py`, `lifespan.py`) instead of
one?** Each has a single reason to change. `lifespan.py` only changes when
startup/shutdown behavior changes (adding a DB pool in a later milestone).
`application.py` only changes when app *construction* changes (metadata,
routers, eventually middleware/exception handlers). `main.py` never
changes at all — it's permanently `app = create_app()` — so it can be
uvicorn's stable entrypoint (`uvicorn app.main:app`) while everything
behind it evolves freely.

**Why FastAPI's `lifespan` parameter instead of the deprecated
`@app.on_event("startup")` / `@app.on_event("shutdown")` decorators?** The
decorator-based events API is deprecated in modern FastAPI/Starlette and
splits one logical "app lifetime" concern into two disconnected callbacks
with no shared state between them. `lifespan` is a single
`@asynccontextmanager`: everything before `yield` is startup, everything
after is shutdown, and they can share local variables (e.g. a database
engine created at startup and closed at shutdown) — a shape later
milestones' resource setup/teardown will need anyway.

**Why does `lifespan` call `paths.ensure_runtime_directories()` instead of
it running on import?** `app/core/paths.py` deliberately left this
uncalled (see Milestone 2 above) specifically so it would run exactly
once, at real application startup — this milestone is that startup. Tests
that only import `app.core.config`/`app.core.paths` still touch no real
filesystem; only actually starting the app (via `create_app()` + its
lifespan, or `TestClient`) creates `storage/`, `storage/uploads/`, and
`logs/`.

**Why log via `app.core.logging.get_logger`, not `print()`?** The whole
point of Milestone 3 was one consistently formatted logger everywhere in
the app; startup/shutdown are exactly the kind of operational events
(when did the process come up, when did it go down, with what version and
in what environment) that belong in that same stream, not bypassing it.

**Why is `_register_routers()` a separate function that currently does
nothing?** Same seam pattern as `logging._build_handlers()` in Milestone
3: one obvious place, agreed now, for `app.include_router(...)` calls to
land in Milestone 5+, so adding the first real route is a one-line change
inside an existing function instead of restructuring `create_app()`.
Building an actual router registry/aggregator before any router exists
would be speculative — this is the minimum seam that keeps the two
concerns (app construction vs. route wiring) separate.

**Why does `create_app()` set `description` from a new
`constants.DEFAULT_APP_DESCRIPTION` instead of `settings.application`?**
`title` and `version` are legitimately things an operator might reasonably
override per-deployment (hence they live in `Settings`, with constants
only as their default). The API description is prose the *code* owns, not
something a deployment should be able to change via an env var — so it
belongs in `constants.py` alongside the other fixed, non-configurable
values, not the settings schema.

**Why does the app start successfully with zero routes?** Proving the
factory + lifespan work correctly *before* any business route exists means
a bug here can't hide behind a passing route test — `TestClient(app)` in
`tests/test_application.py` exercises the full startup/shutdown cycle
against an app that only has FastAPI's own built-in `/docs`, `/redoc`, and
`/openapi.json`, isolating "does the app boot" from "does a specific
endpoint work" (the latter starts in Milestone 5).

## Setup instructions

Prerequisites: [`uv`](https://docs.astral.sh/uv/) installed (`uv` manages
its own Python interpreters, so a system Python is not required).

```bash
cd backend
uv sync              # creates .venv, installs runtime + dev dependencies from uv.lock
uv run pre-commit install --config ../.pre-commit-config.yaml
```

Or from the repo root via the Makefile: `make install`.

## Development workflow

| Command | What it does |
|---|---|
| `make lint` | `ruff check .` — static lint errors, import order, bugbear/simplify rules |
| `make format` | `ruff format .` + `black .` — auto-format code |
| `make typecheck` | `mypy .` — strict static type checking |
| `make test` | `pytest` — runs the suite with coverage (`--cov=app`) |
| `make run` | Starts `uvicorn app.main:app --reload` — the app boots with no business routes yet (only `/docs`, `/redoc`, `/openapi.json`) |
| `make clean` | Removes `.venv`, caches, and build artifacts |

Every one of these also runs directly with `uv run <tool>` from inside
`backend/` (e.g. `uv run ruff check .`) if you'd rather not use `make`.
Pre-commit runs `ruff`, `black`, and `mypy` automatically on every commit
that touches `backend/`, so CI failures should be rare by the time a commit
lands.

## How this project was created from scratch

The exact commands used to produce this milestone, in order, from the
repo root (`Product_Intelligence_Platform/`):

```bash
# 1. Folder structure
mkdir -p backend/app/{api,core,services,repositories,models,schemas,workers,middleware,dependencies,utils} \
         backend/tests backend/scripts backend/docs
touch backend/app/__init__.py backend/app/api/__init__.py backend/app/core/__init__.py \
      backend/app/services/__init__.py backend/app/repositories/__init__.py \
      backend/app/models/__init__.py backend/app/schemas/__init__.py \
      backend/app/workers/__init__.py backend/app/middleware/__init__.py \
      backend/app/dependencies/__init__.py backend/app/utils/__init__.py \
      backend/tests/__init__.py

# 2. Python toolchain
uv python install 3.12
echo "3.12" > backend/.python-version

# 3. Project + dependencies (pyproject.toml's [project] table is hand-written first;
#    `uv add` then resolves versions and appends them automatically)
cd backend
uv add fastapi "uvicorn[standard]" pydantic-settings
uv add --dev ruff black mypy pytest pytest-asyncio pytest-cov httpx pre-commit
cd ..

# 4. Tool configuration (ruff/black/mypy/pytest/coverage) hand-added to
#    backend/pyproject.toml under [tool.*] tables — see that file directly.

# 5. Repo-wide tooling
#    .pre-commit-config.yaml, .editorconfig, .gitignore, Makefile, README.md — hand-written, repo root
#    backend/.gitignore, backend/.env.example — hand-written

# 6. Verify
cd backend
uv run ruff check .
uv run black --check .
uv run mypy .
uv run pytest
cd ..

# 7. Version control
git init
git add -A
git commit -m "feat: initialize backend skeleton (Milestone 1)"
```

**Milestone 2 (Configuration Management)** added, from the repo root:

```bash
# 1. Config schema
#    backend/app/core/{constants,paths,settings,config}.py — hand-written

# 2. .env support
#    backend/.env.example rewritten for the nested "__" schema; a local
#    backend/.env was copied from it (gitignored, never committed)
cp backend/.env.example backend/.env

# 3. Enable the pydantic mypy plugin so `mypy --strict` understands
#    pydantic-settings' dynamic constructor/coercion behaviour
#    (added `plugins = ["pydantic.mypy"]` under [tool.mypy] in pyproject.toml)

# 4. Tests
mkdir -p backend/tests/core
touch backend/tests/core/__init__.py
#    backend/tests/core/{test_paths,test_settings,test_config}.py — hand-written

# 5. Verify
cd backend
uv run ruff check .
uv run black --check .
uv run mypy .
uv run pytest
cd ..

# 6. Version control
git add -A
git commit -m "feat: add configuration management (Milestone 2)"
```

**Milestone 3 (Logging)** added, from the repo root:

```bash
# 1. Logging module
#    backend/app/core/logging.py — hand-written

# 2. Tests
#    backend/tests/core/test_logging.py — hand-written

# 3. Verify
cd backend
uv run ruff check .
uv run black --check .
uv run mypy .
uv run pytest
cd ..

# 4. Version control
git add -A
git commit -m "feat: add centralized logging (Milestone 3)"
```

**Milestone 4 (FastAPI Application Factory)** added, from the repo root:

```bash
# 1. Application factory, lifespan, and entrypoint
#    backend/app/{lifespan,application,main}.py — hand-written
#    backend/app/core/constants.py — added DEFAULT_APP_DESCRIPTION

# 2. Tests
#    backend/tests/{test_lifespan,test_application,test_main}.py — hand-written

# 3. Verify
cd backend
uv run ruff check .
uv run black --check .
uv run mypy .
uv run pytest
uv run uvicorn app.main:app --reload   # manual smoke test: confirms it boots
cd ..

# 4. Version control
git add -A
git commit -m "feat: add FastAPI application factory (Milestone 4)"
```

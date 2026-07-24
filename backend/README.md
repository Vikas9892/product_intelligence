# Backend — Multi-Modal Product Intelligence Engine

FastAPI backend service. This document covers all of **Phase 1**
(Milestones 1–8: backend skeleton, configuration, logging, the app
factory, health endpoints, global exception handling, middleware, and
testing/CI — see the per-milestone sections below) and **Phase 2A
(Product Upload Pipeline)**: the first real business endpoint, accepting
a product image plus metadata, validating it, and storing it.
No database persistence, image processing, embeddings, or AI/search
functionality exist yet — that is intentional. See
[Why no code yet?](#why-no-code-yet) and the
[Phase 2A section](#phase-2a--product-upload-pipeline-design-decisions)
below.

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
│   ├── api/                # HTTP route definitions (FastAPI routers)
│   │   ├── health.py        # GET /health, /ready, /version — unversioned system endpoints
│   │   └── products.py      # POST /products/upload (mounted under /api/v1) — Phase 2A
│   ├── core/               # App-wide concerns: settings, logging, security, startup/shutdown
│   │   ├── constants.py    # Fixed, non-configurable values (enums, prefixes, insecure-default marker)
│   │   ├── paths.py        # Centralized filesystem paths (backend root, storage, uploads, logs)
│   │   ├── settings.py     # Typed/validated settings schema (BaseModel groups + BaseSettings root)
│   │   ├── config.py       # Singleton accessor: `from app.core.config import settings`
│   │   └── logging.py      # Centralized logging: `from app.core.logging import get_logger`
│   ├── exceptions/         # Domain exception hierarchy + global exception handlers
│   │   ├── base.py          # `AppException` — the base every domain exception subclasses
│   │   ├── errors.py        # Concrete exceptions: ValidationException, ResourceNotFoundException, ...
│   │   └── handlers.py       # Registers handlers converting every error path to one JSON envelope
│   ├── middleware/         # Cross-cutting ASGI middleware, applied to every request/response
│   │   ├── request_id.py    # Assigns/propagates a request/correlation ID
│   │   ├── timing.py         # Measures request duration
│   │   ├── logging.py        # Logs request start/completion (uses the ID + duration above)
│   │   └── security_headers.py # Stamps baseline security response headers
│   ├── services/          # Business logic, orchestration between repositories/external calls
│   │   └── upload_service.py # Phase 2A: validates + durably stores uploaded product images
│   ├── repositories/      # Data access layer (DB, vector store, cache) behind an interface
│   ├── models/             # ORM / persistence models
│   ├── schemas/            # Pydantic request/response schemas (API contracts)
│   │   ├── health.py        # Response models for /health, /ready, /version
│   │   ├── errors.py        # The `{"success", "error": {...}}` envelope every error returns
│   │   └── product.py       # ProductCreate, ProductImage, UploadResponse, ProductResponse — Phase 2A
│   ├── workers/            # Background jobs / async task consumers
│   ├── dependencies/       # FastAPI dependency-injection providers
│   │   └── upload.py        # `get_upload_service()` — Phase 2A's first real dependency provider
│   └── utils/              # Small stateless helpers shared across layers
│       └── metadata.py      # FileMetadata + parse_file_metadata() — Phase 2B "Parse Metadata" stage
├── tests/                  # pytest test suite, mirrors the app/ package layout
├── scripts/              # One-off / maintenance scripts (not part of the importable app)
├── docs/                 # Design notes, ADRs, phase write-ups
├── pyproject.toml        # Single source of truth: dependencies + tool config
├── uv.lock               # Locked, reproducible dependency versions (commit this)
├── README.md             # This file
├── .python-version       # Pins the interpreter uv provisions (3.12)
├── .gitignore             # Backend-specific ignore rules
└── .env.example           # Template for local environment variables

.github/workflows/ci.yml   # Repo-root: GitHub Actions — ruff, black --check, mypy, pytest
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
| `.github/workflows/ci.yml` | GitHub Actions workflow (Milestone 8): on every push/PR to `main`, installs `uv`, then runs `ruff check`, `black --check`, `mypy`, and `pytest` against `backend/` — the same four commands `make lint/format/typecheck/test` run locally, so "passes locally" and "passes in CI" mean the same thing. |

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
| `app/application.py` | `create_app() -> FastAPI`: the only place `FastAPI(...)` is instantiated. Sets `title`/`description`/`version` from `settings.application` + `constants.DEFAULT_APP_DESCRIPTION`, wires in `lifespan`, then calls three private seams in order — `_register_middleware`, `_register_exception_handlers`, `_register_routers` — before returning the instance. |
| `app/main.py` | ASGI entrypoint: `app = create_app()`. This is the `app.main:app` target `uvicorn`/`make run` serve — one line of logic, everything real lives in `create_app()`. |
| `app/api/health.py` | `GET /health`, `/ready`, `/version` (Milestone 5). Deliberately unversioned (not under `/api/v1`) — see the Milestone 5 section below for why. Logs each call at `DEBUG` via `get_logger`. |
| `app/schemas/health.py` | Response models for the three endpoints above: `HealthResponse`, `ReadinessResponse` (with a `checks: dict[str, bool]` shape ready for real dependency checks later), `VersionResponse`. |
| `app/schemas/errors.py` | `ErrorResponse`/`ErrorDetail` (Milestone 6): the single `{"success": false, "error": {"code", "message", "details"}}` shape every error response uses. |
| `app/exceptions/base.py` | `AppException` (Milestone 6): the base class every domain exception subclasses. Carries a `status_code` (transport), a stable `code` (API contract), and a human `message` — see the Milestone 6 section for why those are kept separate instead of just using `HTTPException`. |
| `app/exceptions/errors.py` | Concrete, domain-agnostic exceptions: `ValidationException` (422), `ResourceNotFoundException` (404), `ConflictException` (409), (Phase 2A) `UnsupportedMediaTypeException` (415) and `FileTooLargeException` (413) for upload validation, and (Phase 2B) `ChecksumException` (500) for a checksum that couldn't be computed. |
| `app/exceptions/handlers.py` | `register_exception_handlers(app)`: registers one handler each for `AppException`, `RequestValidationError`, `StarletteHTTPException`, and `Exception` (the catch-all for real bugs), so every error path returns the same JSON envelope. |
| `app/middleware/request_id.py` | `RequestIDMiddleware` (Milestone 7): reuses an inbound `X-Request-ID` header or generates a UUID4, stores it on `request.state.request_id`, echoes it back as a response header. |
| `app/middleware/timing.py` | `TimingMiddleware`: measures handling duration with `time.perf_counter`, stores it on `request.state.duration_ms`, echoes it as `X-Response-Time-Ms`. |
| `app/middleware/logging.py` | `RequestLoggingMiddleware`: logs one line when a request starts, one when it finishes — both tagged with the request ID, the completion line also with status code and duration. |
| `app/middleware/security_headers.py` | `SecurityHeadersMiddleware`: stamps a baseline set of OWASP-recommended security response headers (`X-Content-Type-Options`, `X-Frame-Options`, etc.) via `setdefault`, so a route that already set one of these wins. |
| `app/schemas/product.py` | Phase 2A schemas: `ProductCreate` (name/description/category/price, bound from individual `Form(...)` fields), `ProductImage` (metadata about one stored file), `UploadResponse` (the upload endpoint's actual response), and `ProductResponse` — reserved ahead of need for once a database exists, the same way Phase 1's `AIModelSettings` was reserved. |
| `app/services/upload_service.py` | Phase 2A: `UploadService` — validates an uploaded file's filename/extension, declared MIME type, and size (streaming to disk in bounded chunks, never buffering more than one chunk past the limit), and stores accepted files under a generated (never client-supplied) filename. All limits default to `settings.storage.*`/`constants.SUPPORTED_IMAGE_MIME_TYPES` but are constructor-overridable for tests. |
| `app/services/checksum_service.py` | Phase 2B: `ChecksumService.compute_sha256(path)` — streams an already-stored file from disk in 1 MiB chunks and returns its SHA-256 hex digest. Standalone (operates on any file path, not coupled to the upload stream) so later phases (duplicate detection, caching, integrity checks) reuse it instead of reimplementing hashing. Raises `ChecksumException` if the file can't be read. |
| `app/utils/metadata.py` | Phase 2B: `FileMetadata` (transport-agnostic file metadata: filename, extension, MIME type, size, SHA-256 checksum, upload timestamp) and `parse_file_metadata(image, checksum_sha256=...)`, the adapter from Phase 2A's `ProductImage` + a computed checksum into this internal object. |
| `app/dependencies/upload.py` | `get_upload_service()`: a cached-singleton dependency provider for `UploadService`, mirroring `app.core.config.get_settings`'s pattern — Phase 2A's first real use of the `app/dependencies/` package reserved since Milestone 1. |
| `app/api/products.py` | `POST /products/upload` (mounted under `/api/v1` — a real, versioned business endpoint, unlike `health.py`'s system routes). Accepts product metadata as individual `Form(...)` fields plus a `File()` upload, delegates validation/storage entirely to `UploadService`, returns an `UploadResponse`. See the Phase 2A section below for why the fields are individual `Form(...)` params rather than a single `Annotated[ProductCreate, Form()]`. |
| `tests/__init__.py`, `tests/core/__init__.py`, `tests/api/__init__.py`, `tests/middleware/__init__.py`, `tests/exceptions/__init__.py`, `tests/schemas/__init__.py`, `tests/services/__init__.py`, `tests/dependencies/__init__.py`, `tests/utils/__init__.py` | Makes each test directory a package so pytest resolves absolute imports the same way the app does; `tests/` mirrors `app/`'s layout. |
| `tests/conftest.py` | Shared fixtures (Milestone 8): `app` (a fresh `create_app()` instance per test) and `client` (a `TestClient` bound to it, entered as a context manager so the lifespan actually runs). Only fixtures genuinely needed by multiple modules live here. |
| `tests/test_environment.py` | A single sanity test (Python version check) proving the pytest + coverage pipeline actually runs. |
| `tests/core/test_paths.py` | Verifies path relationships (`UPLOAD_DIR` under `STORAGE_DIR`, etc.) and that `ensure_runtime_directories()` creates the right directories, using `monkeypatch` + `tmp_path` so it never touches the real filesystem. |
| `tests/core/test_settings.py` | Covers defaults, field validation (port range, minimum secret-key length, `SecretStr` not leaking into `repr()`), env-var overrides via nested `__` delimiters, every production-safety rule in `Settings._validate_production_safety` (including the Milestone 7 `trusted_hosts` rule), and the new `cors_allowed_origins`/`trusted_hosts` defaults. |
| `tests/core/test_config.py` | Confirms `get_settings()` returns the same cached object across calls, that `cache_clear()` forces a fresh one, and that the module-level `settings` singleton is a real `Settings` instance. |
| `tests/core/test_logging.py` | Covers level resolution (explicit override vs. `settings.logging.level`), the idempotent/`force` handler-installation behavior, the console formatter's exact output, and an end-to-end check that `get_logger(...).info(...)` really reaches stdout formatted correctly. An autouse fixture snapshots/restores the real root logger around every test so nothing here leaks into other tests. |
| `tests/test_lifespan.py` | Enters/exits `lifespan(app)` as an async context manager directly (no HTTP server needed) and asserts, via `caplog`, that the startup message logs before `yield` and the shutdown message logs after; asserts `paths.ensure_runtime_directories` is called exactly once on startup via `monkeypatch`. |
| `tests/test_application.py` | Confirms `create_app()`'s metadata, that exactly the expected routes are registered (system routes unprefixed, `products.upload` under `/api/v1`), that all middleware are registered in the exact documented order, that a handler is registered for every error path, and — via `TestClient` and settings monkeypatches — the actual runtime behavior of the CORS and TrustedHost middleware (allowed vs. rejected origin/host). |
| `tests/test_main.py` | Confirms `app.main.app` is a real `FastAPI` instance with the expected title, proving the module-level `app = create_app()` entrypoint actually works end-to-end. |
| `tests/api/test_health.py` | Hits `/health`, `/ready`, `/version` through the shared `client` fixture and asserts the exact JSON body each returns. |
| `tests/middleware/test_request_id.py` | Builds a minimal app with only `RequestIDMiddleware` registered; asserts a UUID4 is generated when no ID is supplied, and that a caller-supplied `X-Request-ID` is echoed back unchanged. |
| `tests/middleware/test_timing.py` | Builds a minimal app with only `TimingMiddleware`; asserts the `X-Response-Time-Ms` header reflects at least the handler's simulated delay, and that `request.state.duration_ms` isn't visible from inside the handler (it's only set after the handler returns). |
| `tests/middleware/test_logging.py` | Builds minimal apps with different combinations of `RequestIDMiddleware`/`TimingMiddleware` present; asserts the logged lines fall back to `-`/`?ms` placeholders when those aren't registered, and carry the real ID/duration when they are. |
| `tests/middleware/test_security_headers.py` | Asserts the full baseline header set is present, and that `setdefault` means a header the route already set (e.g. a custom `X-Frame-Options`) is not overwritten. |
| `tests/exceptions/test_base.py`, `test_errors.py` | Unit tests for `AppException` and its concrete subclasses' defaults/overrides — no HTTP involved. |
| `tests/exceptions/test_handlers.py` | Integration tests: a throwaway FastAPI app with `register_exception_handlers` applied and routes that deliberately raise each error type, asserting the exact JSON envelope for domain exceptions, `RequestValidationError`, plain `HTTPException`, and unhandled exceptions (and that the latter never leaks the real exception message). |
| `tests/schemas/test_product.py` | Field validation (empty name, negative price, numeric-string coercion), a `ProductImage`/`UploadResponse` round-trip through `model_dump`/`model_validate`, and a sanity construction of the reserved `ProductResponse`. |
| `tests/services/test_upload_service.py` | Unit tests for `UploadService` against a fake `UploadFile` and a `tmp_path` upload directory: successful storage (content matches, filename is generated, extension preserved/lowercased), every validation rejection (missing filename, disallowed extension/MIME type, oversized file), and that a rejected/oversized upload leaves no partial file behind. |
| `tests/dependencies/test_upload.py` | Confirms `get_upload_service()` returns a cached singleton and that `cache_clear()` forces a fresh instance — the same contract `tests/core/test_config.py` verifies for `get_settings()`. |
| `tests/services/test_checksum_service.py` | Confirms the digest matches `hashlib.sha256` directly for both a small file and one spanning multiple 1 MiB chunk reads, that identical content hashes identically and different content differs, and that a missing file raises `ChecksumException`. |
| `tests/utils/test_metadata.py` | Confirms `FileMetadata` rejects a malformed/uppercase checksum, and that `parse_file_metadata` correctly lowercases the derived extension while carrying every other `ProductImage` field through unchanged. |
| `tests/api/test_products.py` | Integration tests against the *real* `create_app()` app, with `get_upload_service` overridden (`app.dependency_overrides`) to redirect storage to `tmp_path`: a successful upload's response shape and on-disk file content, every validation failure's status code and error envelope (missing name, disallowed extension/MIME type, negative price), and the oversized-file 413 case. |
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

## Milestone 5 — health & system endpoints design decisions

**Why are `/health`, `/ready`, and `/version` two separate concepts
(liveness vs. readiness) instead of one endpoint?** Kubernetes (and any
similar orchestrator/load balancer) asks two different questions that
demand different answers. *Liveness* ("is this process still running and
able to respond at all?") controls whether the orchestrator **restarts**
the container — it must never depend on anything that can be transiently
unavailable, or a temporary database blip causes needless restart churn
that doesn't fix the database. *Readiness* ("can this instance serve
traffic **right now**?") controls whether the orchestrator **routes**
traffic to it — a process can be alive but not ready (still warming up, a
dependency briefly down), and should keep running without receiving
requests in that state. Collapsing both into one endpoint would force a
single response to answer two questions with different consequences.

**Why is `ReadinessResponse.checks` an empty dict right now instead of a
single boolean?** No dependencies (database, vector store, cache) exist
yet to check — Milestone 8's scope explicitly excludes them. Shaping the
field as `dict[str, bool]` now means later milestones add entries
(`{"database": True}`) without changing the response's *shape*, so
existing API consumers don't have to handle a schema change just because
a new dependency got added.

**Why are these three routes mounted at `/health`/`/ready`/`/version`
directly, not under `settings.application.api_prefix` (`/api/v1`)?**
Infrastructure that calls them — the Kubernetes kubelet, a load balancer's
health check, an uptime monitor — is configured once with a fixed path and
is not part of "the API" a versioned contract applies to; it should never
need reconfiguring just because the business API moved from `/api/v1` to
`/api/v2`. Business routers added in later milestones *do* go under the
prefix.

**Why is `/version` useful?** It answers "what's actually running right
now" from outside the process: confirming a deploy actually rolled out
(compare the returned `version` to what was just shipped), tagging
monitoring dashboards/metrics by version, and giving support/bug reports a
reliable "what version were you on" answer without needing shell access to
the host.

## Milestone 6 — global exception handling design decisions

**Why not just raise `HTTPException` everywhere?** `HTTPException` only
carries a status code and a free-text `detail` string — there's no place
for a *stable, machine-readable* identifier a client can safely branch on
across releases. Every call site ends up inventing its own `detail`
wording, and two totally different failures (a missing product vs. a
missing user) can legitimately share the same status code (404), so a
client can't distinguish them without string-matching wording that's
allowed to change. `AppException` fixes this by carrying both a
`status_code` (the transport-layer concern) *and* a `code` (the API
contract — e.g. `"resource_not_found"`, stable across releases)
independently.

**Why a base `AppException` class instead of one exception per case
inline?** A shared base means `app/exceptions/handlers.py` catches *one*
type once and correctly handles every present and future subclass — a new
domain exception (e.g. a future `InsufficientStockException`) needs zero
changes to the handler, only a new class in `errors.py` that sets
`status_code`/`code`/`message`.

**Why register a handler for `Exception` itself, not just for
`AppException`?** Domain code raising `AppException` is the "expected
failure" path; a raw `Exception` (a real bug — a `None` where a value was
assumed, a third-party call that raised something unanticipated) is not.
Without a catch-all, an unhandled bug would fall through to Starlette's
default plain-text 500 page instead of the same JSON envelope every other
error uses — breaking the "one consistent shape" contract exactly when a
client needs it most (a real outage). Registering a handler for `Exception`
specifically routes it into Starlette's `ServerErrorMiddleware` (its
outermost middleware — see `_register_middleware`'s docstring), so it also
catches exceptions raised by other middleware, not just inside a route.

**Why does the unhandled-exception handler log the real exception
(`logger.exception`, with traceback) but respond with a generic
"An unexpected error occurred."?** These serve different audiences. An
operator debugging an incident needs the real traceback — that's what
`logger.exception` is for. An API *client* receiving the raw exception
message (a stack frame, a database connection string fragment, an
internal file path) is an information-disclosure risk, not a debugging
aid — attackers routinely fingerprint backends this way. Keeping the log
detailed and the response generic serves both needs without trading one
off against the other.

**Why is `RequestValidationError` (FastAPI's own request-schema
validation) handled separately from `ValidationException`?** They catch
different failure classes. `RequestValidationError` fires when a request
doesn't match its Pydantic schema at all (missing/mistyped fields) —
FastAPI raises this itself, before a route body even runs.
`ValidationException` is for business-rule validation a schema alone can't
express (e.g. "end_date must be after start_date"), raised explicitly by
route/service code. Both return the same 422 + `"validation_error"`
envelope to the client — the distinction is about *where the check lives*,
not what the client sees.

**Why derive the `code` for a plain `HTTPException` from
`http.HTTPStatus(status_code).phrase` instead of a hand-written
status-to-code mapping?** Every standard HTTP status already has a
canonical reason phrase (`404` → "Not Found") that stdlib's `http` module
already knows — deriving `"not_found"` from it means every status code
gets a sensible, consistent `code` for free, with no mapping table to keep
in sync as new routes introduce new status codes.

## Milestone 7 — middleware design decisions

**Why middleware instead of repeating this logic in every route?**
Request ID generation, timing, logging, and security headers apply
identically to *every* request regardless of what the route does —
implementing them per-route would mean remembering to add the same
boilerplate to every new endpoint forever, with every route free to get it
slightly wrong. Middleware wraps the entire request/response cycle once,
so the guarantee ("every response has a request ID, a timing header, and
security headers") holds structurally instead of by convention.

**Middleware execution order — how does it actually work?** Starlette's
`add_middleware()` *prepends* to an internal list, and the final ASGI
stack wraps the router in that list's order — the practical effect is
**the last `add_middleware()` call becomes the outermost layer** (first to
see the request, last to see the response). `app/application.py`'s
`_register_middleware()` calls `add_middleware()` innermost-first so the
resulting runtime order, outermost to innermost, is:

```
TrustedHost -> CORS -> GZip -> SecurityHeaders
    -> RequestID -> RequestLogging -> Timing -> (routing)
```

- **TrustedHost** outermost: reject a forged/invalid `Host` header as
  cheaply as possible, before any other work happens.
- **CORS** next: must wrap every response — including error responses
  built by the exception handlers — so preflight requests and error
  responses both get correct CORS headers.
- **GZip** next: compresses whatever the inner stack produced, so it must
  be outer relative to anything that sets response headers/body content.
- **SecurityHeaders**: same reasoning — must see every response, success
  or error, to stamp its headers on it.
- **RequestID** must be outer of **RequestLogging**: the ID has to exist
  on `request.state` before the logging middleware's "request started"
  line is written.
- **RequestLogging** must be outer of **Timing**: a middleware's
  post-`call_next` code only runs after everything inner to it has fully
  finished — so logging can only read the duration `Timing` computed if
  timing is inner of logging.
- **Timing** innermost (of the custom stack): its measurement should
  reflect actual request handling, not the overhead of the outer layers.

**Why does middleware still run around exception-handler-built responses?**
Starlette always places `ExceptionMiddleware` directly around the router —
innermost of all user middleware. When a route raises and a handler builds
a response, that response still flows back out through every middleware
above it (headers get added, the request gets logged) exactly as if the
route had returned normally. This is also why `_register_exception_handlers`
is called *after* `_register_middleware` in `create_app()` conceptually
lines up: middleware wraps around routing+error-handling as one unit.

**What are request/correlation IDs, and why generate one per request?**
A request ID uniquely tags one request through logs; a *correlation* ID is
the same concept propagated across service boundaries so one logical
operation can be traced end-to-end through multiple services. This
codebase treats them as the same value: `RequestIDMiddleware` reuses an
inbound `X-Request-ID` header when a caller (or upstream service) already
set one, generating a fresh UUID4 only when none was supplied — so a
request that hopped through an API gateway or another internal service
keeps one consistent ID the whole way, and every log line for it (across
every service, if they all adopt the same header) can be grepped together.

**Why `time.perf_counter()` for timing instead of `time.time()`?**
`time.perf_counter()` is a monotonic clock meant specifically for
measuring elapsed intervals; `time.time()` reflects wall-clock time and
can jump backwards or forwards under NTP adjustments, which could produce
a wrong — even negative — duration for the exact same request.

**Why `BaseHTTPMiddleware` for the four custom middlewares instead of raw
ASGI middleware?** `BaseHTTPMiddleware` (Starlette's `Request`/`Response`-
based middleware base) is dramatically simpler to write and test —
`dispatch(request, call_next)` reads like a function, not an ASGI protocol
implementation — at the cost of some known limitations around streaming
responses and background tasks that don't apply here (nothing in this app
streams a response body or schedules a `BackgroundTask` yet). Raw ASGI
middleware (like Starlette's own `GZipMiddleware`/`CORSMiddleware`/
`TrustedHostMiddleware`, used as-is rather than reimplemented) is the
right tool when those limitations *do* matter — which is part of why
those three are used directly from Starlette rather than hand-rolled.

**Why is CORS opt-in (`cors_allowed_origins` defaults to `[]`) but
`trusted_hosts` opt-out (defaults to `["*"]`, accept-any)?** They fail in
opposite directions. An empty CORS allow-list is the *safe* default — no
browser can make a cross-origin request against the API until a
deployment explicitly lists its frontend's origin, so getting it wrong by
omission just means "CORS doesn't work yet," not a vulnerability. A
wildcard `trusted_hosts` is convenient for local dev (any `Host` header is
accepted) but is a real Host-header-injection exposure in production — so
`Settings._validate_production_safety` (Milestone 2's pattern, extended
here) raises at startup if `trusted_hosts` is still `["*"]` when
`environment=production`, the same "fail loud at boot, don't run
insecurely" principle as the existing secret-key/debug/SQLite checks.

**Why a security-headers *middleware* instead of e.g. relying on a reverse
proxy to add them?** Not every deployment of this service is guaranteed to
sit behind a proxy that adds them, and defense-in-depth means the app
shouldn't depend on infrastructure it doesn't control for a baseline that's
this cheap to guarantee itself. It's deliberately a *baseline* only — a
tuned `Content-Security-Policy` needs to know what a later milestone
actually serves (e.g. any CDN assets the Swagger UI docs pull in) — so CSP
is not set here.

## Milestone 8 — testing & CI design decisions

**Why `tests/conftest.py` now, when Milestones 1–4 didn't need one?**
Milestones 1–4's tests each needed different, narrow fixtures (a
root-logger snapshot/restore, `tmp_path`/`monkeypatch` for paths) that
didn't repeat across files. Starting with Milestones 5–7, most test
modules need the *same* thing — a fresh app instance and a `TestClient`
bound to it — so factoring `app`/`client` into `conftest.py` avoids that
setup being copy-pasted into every test file that needs it, while
fixtures still narrow enough for one file (like the logging tests'
root-logger fixture) stay local to that file.

**Why does the `client` fixture use `TestClient` as a context manager
instead of just `TestClient(app)`?** Only entering `TestClient` as a
context manager (`with TestClient(app) as client:`) actually triggers the
app's lifespan — startup before the first request, shutdown after the
block exits — the same as a real deployment. Constructing `TestClient(app)`
without the `with` skips the lifespan entirely, silently leaving something
like a database connection pool (in a later milestone) never opened.

**Why does testing the global exception handlers require a *separate*,
throwaway FastAPI app (`tests/exceptions/test_handlers.py`) instead of
using the real app or the shared `client` fixture?** The real app has no
routes that deliberately fail, and adding test-only "raise this exception"
routes to it would leak test scaffolding into production code. Building a
minimal app with just `register_exception_handlers()` applied plus a
handful of intentionally-failing routes exercises the *real*
FastAPI/Starlette exception-dispatch machinery end-to-end — which a plain
unit test calling a handler function directly with a hand-built `Request`
object could not — without polluting `app/application.py`.

**Why does that same test file need `TestClient(..., raise_server_exceptions=False)`?**
A subtle Starlette behavior: `ServerErrorMiddleware` sends the registered
handler's response *and then re-raises the original exception* so
debuggers/test runners can still see the real traceback. `TestClient`
re-raises that into the test itself by default (`raise_server_exceptions=True`),
so a test asserting on the 500 response's *body* would instead see a
Python exception propagate out of `client.get(...)`. Passing
`raise_server_exceptions=False` disables that re-raise so the response can
actually be asserted on — a common gotcha when first testing a catch-all
exception handler.

**Why does each custom middleware get its own isolated test file
(`tests/middleware/test_*.py`) building a minimal app with *only that
middleware* registered, rather than testing them all through the real
app?** Testing `RequestIDMiddleware` in isolation means a failure there
can only mean "request ID logic is broken" — not "something in the seven-
middleware stack interacted badly." `tests/test_application.py` then
separately covers the *integration* concern (are all seven registered, in
the right order, and do the two settings-driven ones — CORS,
TrustedHost — behave correctly with real settings values) — each layer is
tested at the altitude where a failure is most informative.

**Why assert the exact middleware order via
`[m.cls for m in app.user_middleware]` in a test, instead of only testing
observable behavior (headers, logs)?** Some ordering mistakes (e.g.
swapping `RequestLoggingMiddleware` and `TimingMiddleware`) wouldn't
necessarily *crash* anything — the duration would just silently read as
the `"?ms"` placeholder forever, a bug that's easy to miss in a manual
smoke test. Asserting the registered class order directly turns "did
someone reorder `_register_middleware()`'s calls by accident" into an
immediate, obvious test failure instead of a subtle production log defect.

**Why GitHub Actions instead of another CI provider?** The repository
already lives on GitHub — Actions requires no new account, billing
relationship, or webhook configuration to get CI running, and its
workflow YAML lives in the repo itself (`.github/workflows/ci.yml`),
versioned alongside the code it tests.

**Why does `ci.yml` run the exact same four commands
(`ruff check`, `black --check`, `mypy`, `pytest`) as `make lint/format/
typecheck/test` instead of its own bespoke CI-only checks?** So "it passes
locally" and "it passes in CI" mean the same thing — a contributor running
`make test` before pushing gets the same signal CI will give, with no
CI-only check that can surprise them after a push. `--locked` on `uv sync`
is the one deliberate CI-specific addition: it fails fast if `uv.lock` is
out of sync with `pyproject.toml`, instead of CI silently re-resolving and
masking a forgotten `uv lock`.

**Why automate linting/type-checking/testing in CI at all, given
pre-commit already runs `ruff`/`black`/`mypy` locally?** Pre-commit hooks
are opt-in per developer machine (`pre-commit install` has to have been
run) and can be bypassed (`git commit --no-verify`) or simply not
installed yet on a fresh clone. CI is the one check that runs
unconditionally on every push/PR regardless of what's configured locally,
so it's the actual guarantee "main never has code that fails lint/
type-check/tests" — pre-commit is the fast local feedback loop, CI is the
enforcement backstop.

## Phase 2A — Product Upload Pipeline design decisions

**Why does `POST /products/upload` accept individual `Form(...)` fields
instead of `Annotated[ProductCreate, Form()]`?** FastAPI's "Form models"
feature normally spreads a `Form()`-annotated Pydantic model's fields as
flat top-level form fields — this works fine in isolation (verified
directly against this FastAPI version). But the moment a *second* body
parameter is also present — here, the `File()` upload — FastAPI switches
the whole request body to "embedded" mode, expecting the model nested
under one key (`{"product": {...}}`) rather than flat fields, which is
neither how a browser `<form enctype="multipart/form-data">` nor most
HTTP clients send metadata alongside a file. Accepting `name`,
`description`, `category`, and `price` as individual `Form(...)`
parameters (with the same constraints `ProductCreate`'s fields declare)
keeps the wire format flat; `ProductCreate` is then constructed from the
validated individual values and remains the canonical schema everywhere
else (the `UploadResponse.product` field, and later a JSON-based creation
endpoint once persistence exists). This was discovered empirically while
building this milestone — worth knowing if a future endpoint combines a
Pydantic form model with a file upload again.

**Why does `UploadService` exist separately from the route function?**
`app/api/products.py` stays a thin HTTP adapter — parse the request,
delegate, shape the response — while all the actual policy (which
extensions/MIME types are allowed, how big is too big, where files land
on disk) lives in one unit-testable class with zero FastAPI/Starlette
dependency in its own logic (it takes a `fastapi.UploadFile`, but nothing
about its validation/storage behavior requires an HTTP request to exist).
`tests/services/test_upload_service.py` exercises every validation rule
directly, faster and more precisely than doing the same through HTTP.

**Why is `UploadService`'s upload directory/size limit/allowed types
constructor-overridable instead of only ever reading `settings`
directly?** Same idiom as `app.core.logging.configure_logging`'s explicit
`level` override (Milestone 3): reading `settings.storage.*` is the real
production path and the default when a param is omitted, but tests need
to redirect storage to a `tmp_path` and shrink the size limit without
monkeypatching the global `settings` singleton (which would leak into
other tests). The check is `is not None`, not truthiness, for the same
reason Milestone 3 chose it — so a caller could pass `max_upload_size_mb=0`
deliberately without it being silently treated as "not provided".

**Why does `app/dependencies/upload.py` matter, when `UploadService()`
could just be constructed inline in the route?** It's Phase 2A's first
real use of the `app/dependencies/` package that's been reserved (empty)
since Milestone 1. `Depends(get_upload_service)` — cached the same way
`get_settings()` is — means `tests/api/test_products.py` can override
*just this one dependency*
(`app.dependency_overrides[get_upload_service] = lambda: UploadService(upload_dir=tmp_path)`)
on the real `create_app()` app, exercising the real router, real
middleware, and real exception handlers while never touching the real
`backend/storage/` directory. Constructing `UploadService()` inline in
the route would work functionally but would leave no seam for tests to
substitute a different instance.

**Why validate the file by streaming to disk in chunks, enforcing the
size limit as it goes, instead of checking `Content-Length` or reading
the whole file first?** The `Content-Length` header is client-supplied
and not authoritative — trusting it means a client can lie. Fully
buffering the file before checking its size defeats the point of a size
limit (a malicious/broken upload could still exhaust memory before ever
being rejected). Streaming in 1 MiB chunks and aborting — deleting the
partial file — the moment the cumulative size exceeds the limit means
`UploadService` never holds more than one chunk past the configured
maximum in memory or on disk, regardless of what the client claims or
sends.

**Why is the declared MIME type (`UploadFile.content_type`) validated but
not the file's actual bytes?** The `Content-Type` of a multipart part is
also client-supplied — validating it is a legitimate first line of
defense (catches accidental/obviously-wrong uploads immediately, cheaply,
before any disk I/O), but not authoritative against a deliberately
mislabeled file. Verifying the *actual* bytes are a valid image (e.g. via
Pillow) is real content-sniffing that belongs to a later image-processing
phase — explicitly out of scope here (see "Do not implement" at the top
of this milestone) — not upload validation.

**Why is the stored filename always generated (`uuid4().hex` + extension),
never the client-supplied `original_filename`?** Using a client-supplied
filename as an actual disk path is a classic path-traversal vector
(`../../etc/passwd`-style names) and a collision hazard (two uploads
named `photo.jpg`). Generating the on-disk name sidesteps both entirely —
there's no sanitization logic to get subtly wrong, because the untrusted
value is never used as a path component. The original name is preserved
in `ProductImage.original_filename` for display purposes only.

**Why do `ProductCreate` and `ProductImage` exist as schemas if there's no
database yet?** They're the actual request/response contract for `POST
/products/upload` today — a Pydantic model is needed regardless of
whether a database exists, since it's what defines the shape of the form
fields and the JSON response. `ProductResponse` is the one schema that
*is* purely reserved ahead of need (not used by any route yet), the same
pattern as Phase 1's `AIModelSettings` — defined now so a later
persistence phase's routes/tests don't have to invent the contract from
scratch.

**Why does `backend/.gitignore` now ignore `storage/` entirely?**
Milestone 1 already established that runtime directories
(`paths.ensure_runtime_directories()`) are created at startup, not
source-controlled — but until Phase 2A, nothing ever actually wrote a
file into `storage/uploads/`, so the gap (an uploaded file could get
accidentally `git add -A`'d) was latent. Ignoring `storage/` outright
(no `.gitkeep`, unlike `scripts/`/`docs/`) is correct specifically because
it's runtime-created and recreated automatically — it should never be
part of the repository's tracked content.

**Why does `python-multipart` appear as a new runtime dependency?**
FastAPI's form/file parsing (`Form(...)`, `File(...)`, `UploadFile`) is
built on top of `python-multipart` for parsing `multipart/form-data`
request bodies, and FastAPI only raises a runtime error demanding it the
moment a route actually declares a form/file parameter — it's an optional
dependency of FastAPI itself, not bundled by default, so any endpoint
that accepts uploads needs it added explicitly (`uv add python-multipart`).

## Phase 2B — Product Processing & Metadata Normalization design decisions

*(This section grows milestone by milestone as Phase 2B lands — currently
covers the Checksum Service and File Metadata milestones.)*

**Why does `ChecksumService` re-read the file from disk instead of
computing the checksum inline while `UploadService` streams it to disk in
the first place?** This is a deliberate tradeoff, not an oversight. Hashing
inline (updating a running SHA-256 as each chunk is written) would save a
second read, but it would couple Phase 2A's `UploadService` — already
built, tested, and documented — to a Phase 2B concern, and it would make
`ChecksumService` a thin appendage of the upload stream rather than a
genuinely standalone utility. Keeping it standalone means it can hash
*any* file already on disk (useful later for verifying a file's integrity
without re-uploading it, not just newly-uploaded ones), matching how the
deliverable frames it — reused later for "duplicate detection, caching,
integrity verification," all operations on already-stored files. The cost
is a second read of the file; given this project's small default upload
size cap, that's negligible next to the architectural clarity.

**Why does `ChecksumService.compute_sha256` raise `ChecksumException`
instead of letting the underlying `OSError` propagate?** An `OSError` here
means something went wrong with the *server's* filesystem (the file
vanished, permissions changed) between being stored and being hashed —
not a client input problem. Wrapping it in a typed `AppException` gives
it a 500 status, a stable `code` ("checksum_error"), and a message that
doesn't leak a raw filesystem path/errno straight to an API response,
the same reasoning `UploadService`'s existing exceptions already follow.

**Why does `FileMetadata` live in `app/utils/metadata.py`, separate from
both `ProductImage` (`app/schemas/product.py`) and the future `Product`
domain model (`app/models/product.py`)?** Each represents the same
underlying file at a different layer. `ProductImage` is what
`UploadService` knows the instant a file is saved — filename, stored
name, MIME type, size, timestamp — and is also an HTTP response shape.
`FileMetadata` is the richer, purely internal picture once Phase 2B's
processing has run (adds the derived `extension` and the checksum,
neither of which `UploadService` computes). It's deliberately not
folded into `ProductImage` itself, because `ProductImage` is Phase 2A's
already-stable API contract — extending it would mean every consumer of
`UploadResponse` (today, just the one route) has to reason about
checksum-computation timing; keeping it a separate internal type means
`ProductImage` never needs to change as Phase 2B's processing logic
evolves.

**Why does `parse_file_metadata` take a `ProductImage` plus a separately
computed `checksum_sha256`, instead of computing the checksum itself?**
Single responsibility: this function's job is *shaping* metadata already
known into the internal representation, not deciding *how* a checksum
gets computed (that's `ChecksumService`'s job, and it needs the file's
on-disk path, which `ProductImage` deliberately doesn't expose — see
Phase 2A's rationale for keeping server filesystem paths out of API-
facing schemas). Composing the two in `ProductService` (next milestone)
keeps each piece independently testable: `parse_file_metadata`'s tests
never need a real file on disk, and `ChecksumService`'s tests never need
a `ProductImage`.

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
| `make run` | Starts `uvicorn app.main:app --reload` — serves `/health`, `/ready`, `/version` (Milestone 5) |
| `make clean` | Removes `.venv`, caches, and build artifacts |

Every one of these also runs directly with `uv run <tool>` from inside
`backend/` (e.g. `uv run ruff check .`) if you'd rather not use `make`.
Pre-commit runs `ruff`, `black`, and `mypy` automatically on every commit
that touches `backend/`, so CI failures should be rare by the time a commit
lands. The mypy hook is a `repo: local` hook (`.pre-commit-config.yaml`)
that shells out to `uv run --directory backend mypy .` — the exact same
command, working directory, and dependency environment as `make
typecheck`/CI — rather than the more common `mirrors-mypy` hook, which runs
mypy in its own isolated environment and needs every dependency mypy
touches hand-listed in `additional_dependencies`, silently drifting out of
sync with `pyproject.toml` over time.

## Continuous integration

`.github/workflows/ci.yml` runs on every push and pull request to `main`:
installs `uv`, provisions Python from `backend/.python-version`, runs
`uv sync --locked` (fails if `uv.lock` doesn't match `pyproject.toml`), then
`ruff check .`, `black --check .`, `mypy .`, and `pytest` — the same four
commands `make lint/format/typecheck/test` run locally. See the Milestone 8
section below for why CI mirrors the local commands exactly, and why it
exists at all alongside pre-commit.

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

**Milestone 5 (Health & System Endpoints)** added, from the repo root:

```bash
# 1. Response schemas + router
#    backend/app/schemas/health.py, backend/app/api/health.py — hand-written
#    backend/app/application.py — _register_routers() now includes health_router

# 2. Tests
mkdir -p backend/tests/api
touch backend/tests/api/__init__.py
#    backend/tests/api/test_health.py — hand-written

# 3. Verify
cd backend
uv run ruff check .
uv run black --check .
uv run mypy .
uv run pytest
cd ..

# 4. Version control
git add -A
git commit -m "feat: add health, readiness, and version endpoints (Milestone 5)"
```

**Milestone 6 (Global Exception Handling)** added, from the repo root:

```bash
# 1. Error envelope schema, exception hierarchy, and handlers
mkdir -p backend/app/exceptions
touch backend/app/exceptions/__init__.py
#    backend/app/schemas/errors.py — hand-written
#    backend/app/exceptions/{base,errors,handlers}.py — hand-written
#    backend/app/application.py — register_exception_handlers(app) wired in

# 2. Tests
mkdir -p backend/tests/exceptions
touch backend/tests/exceptions/__init__.py
#    backend/tests/exceptions/{test_base,test_errors,test_handlers}.py — hand-written

# 3. Verify
cd backend
uv run ruff check .
uv run black --check .
uv run mypy .
uv run pytest
cd ..

# 4. Version control
git add -A
git commit -m "feat: add global exception handling (Milestone 6)"
```

**Milestone 7 (Middleware)** added, from the repo root:

```bash
# 1. Custom middleware + settings for the two settings-driven edge middlewares
#    backend/app/middleware/{request_id,timing,logging,security_headers}.py — hand-written
#    backend/app/core/settings.py — added ApplicationSettings.trusted_hosts,
#    .cors_allowed_origins, and a production-safety rule rejecting a wildcard
#    trusted_hosts in production
#    backend/.env.example — documented the two new variables
#    backend/app/application.py — _register_middleware() wires CORS, GZip,
#    TrustedHost (Starlette built-ins) plus the four custom middlewares above,
#    in the order documented in that function's docstring

# 2. Tests
mkdir -p backend/tests/middleware
touch backend/tests/middleware/__init__.py
#    backend/tests/middleware/test_{request_id,timing,logging,security_headers}.py — hand-written
#    backend/tests/test_application.py — extended with middleware-order,
#    exception-handler-registration, CORS, and TrustedHost coverage
#    backend/tests/core/test_settings.py — extended for the new settings fields

# 3. Verify
cd backend
uv run ruff check .
uv run black --check .
uv run mypy .
uv run pytest
uv run uvicorn app.main:app --reload   # manual smoke test: confirmed headers + log lines
cd ..

# 4. Version control
git add -A
git commit -m "feat: add cross-cutting request middleware (Milestone 7)"
```

**Milestone 8 (Testing & CI Foundation)** added, from the repo root:

```bash
# 1. Shared test fixtures
#    backend/tests/conftest.py — hand-written (app + client fixtures)

# 2. GitHub Actions CI
mkdir -p .github/workflows
#    .github/workflows/ci.yml — hand-written: ruff, black --check, mypy, pytest

# 3. Fixed a pre-existing bug surfaced while wiring up CI: the mypy
#    pre-commit hook (mirrors-mypy) had been silently broken since
#    Milestone 4 introduced FastAPI imports — its isolated environment's
#    additional_dependencies never included fastapi/pytest/httpx, and even
#    after adding them, running mypy from the repo root (rather than from
#    backend/) broke `mypy_path = "."` resolution of the `app` package.
#    Replaced it with a `repo: local` hook that runs
#    `uv run --directory backend mypy .` — the project's own dependency
#    environment, the same working directory `make typecheck`/CI use.
#    .pre-commit-config.yaml — hand-edited

# 4. Verify
cd backend
uv run ruff check .
uv run black --check .
uv run mypy .
uv run pytest
cd ..
uv run --project backend pre-commit run --all-files -c .pre-commit-config.yaml

# 5. Version control
git add -A
git commit -m "feat: add testing fixtures and CI foundation (Milestone 8)"
```

**Phase 2A (Product Upload Pipeline)** added, from the repo root:

```bash
# 1. New runtime dependency: FastAPI's Form()/File()/UploadFile support
#    needs python-multipart, an optional dependency not installed by default
cd backend
uv add python-multipart
cd ..

# 2. Constants + exceptions
#    backend/app/core/constants.py — added SUPPORTED_IMAGE_MIME_TYPES
#    backend/app/exceptions/errors.py — added UnsupportedMediaTypeException,
#    FileTooLargeException

# 3. Schemas, service, dependency provider, router
#    backend/app/schemas/product.py — hand-written
#    backend/app/services/upload_service.py — hand-written
#    backend/app/dependencies/upload.py — hand-written
#    backend/app/api/products.py — hand-written
#    backend/app/application.py — _register_routers() now includes
#    products_router, mounted under settings.application.api_prefix

# 4. Never source-control uploaded files
#    backend/.gitignore — added storage/

# 5. Tests
mkdir -p backend/tests/schemas backend/tests/services backend/tests/dependencies
touch backend/tests/schemas/__init__.py backend/tests/services/__init__.py \
      backend/tests/dependencies/__init__.py
#    backend/tests/schemas/test_product.py — hand-written
#    backend/tests/services/test_upload_service.py — hand-written
#    backend/tests/dependencies/test_upload.py — hand-written
#    backend/tests/api/test_products.py — hand-written
#    backend/tests/test_application.py — extended for the new business route

# 6. Verify
cd backend
uv run ruff check .
uv run black --check .
uv run mypy .
uv run pytest
uv run uvicorn app.main:app --reload   # manual smoke test with curl -F uploads
cd ..
uv run --project backend pre-commit run --all-files -c .pre-commit-config.yaml

# 7. Version control
git add -A
git commit -m "feat: add product upload pipeline (Phase 2A)"
```

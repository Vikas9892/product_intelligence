# Backend — Multi-Modal Product Intelligence Engine

FastAPI backend service. This document covers all of **Phase 1**
(Milestones 1–8: backend skeleton, configuration, logging, the app
factory, health endpoints, global exception handling, middleware, and
testing/CI — see the per-milestone sections below), **Phase 2A (Product
Upload Pipeline)**: the first real business endpoint, accepting a product
image plus metadata, validating it, and storing it; **Phase 2B (Product
Processing & Metadata Normalization)**: turning that stored upload into a
checksummed, normalized, identified internal `Product` domain object; and
**Phase 3 (Image Processing Pipeline)**: standardizing the uploaded image
itself — orientation, color mode, size — into the consistent format
AI models expect, before that `Product` is finalized.
No database persistence, embeddings, or AI/search functionality exist
yet — that is intentional. See
[Why no code yet?](#why-no-code-yet), the
[Phase 2A section](#phase-2a--product-upload-pipeline-design-decisions),
the
[Phase 2B section](#phase-2b--product-processing--metadata-normalization-design-decisions),
and the
[Phase 3 section](#phase-3--image-processing-pipeline-design-decisions)
below.

## Project overview

This service will eventually ingest multi-modal product data (text +
images), generate embeddings, run hybrid vector/keyword search, and expose
LLM-assisted metadata, duplicate detection, and pricing intelligence over a
FastAPI HTTP API. Milestone 1 establishes the foundation everything else is
built on: a repo that lints, type-checks, tests, and installs the same way
on every machine and in CI, before a single line of business logic exists.

## Roadmap

This project is planned across 20 phases. Phases 1–19 are complete and
documented below (see each phase's own "design decisions" section and
its entry under
[How this project was created from scratch](#how-this-project-was-created-from-scratch)).
Phase 20 has not been specified yet — no milestone list, config keys, or
scope exists for it, so it's listed here only as a placeholder in the
numbering, not as a commitment to specific future functionality.

| Phase | Title | Status |
|---|---|---|
| 1 | Backend skeleton, configuration, logging, app factory, health endpoints, exception handling, middleware, testing/CI | Complete |
| 2A | Product Upload Pipeline | Complete |
| 2B | Product Processing & Metadata Normalization | Complete |
| 3 | Image Processing Pipeline | Complete |
| 4 | Image Embedding Pipeline | Complete |
| 5 | Vector Search & Retrieval | Complete |
| 6 | Text Embeddings & Hybrid Search | Complete |
| 7 | Catalog Intelligence & Product Enrichment | Complete |
| 8 | Duplicate Detection Engine | Complete |
| 9 | Intelligent Recommendation Engine | Complete |
| 10 | Retrieval Evaluation Framework | Complete |
| 11 | Cross-Encoder Reranking | Complete |
| 12 | Asynchronous AI Processing Pipeline | Complete |
| 13 | Model Registry & AI Lifecycle Management | Complete |
| 14 | AI Observability & Monitoring | Complete |
| 15 | Cross-Encoder Re-ranking & Intelligent Duplicate Verification | Complete |
| 16 | Explainable AI & Decision Intelligence | Complete |
| 17 | Pricing Intelligence Engine | Complete |
| 18 | Analytics & Business Intelligence Platform | Complete |
| 19 | Enterprise Platform Features (multi-tenancy, RBAC, audit, quotas) | Complete |
| 20 | Not yet specified | Planned |

## Folder structure

```
backend/
├── app/
│   ├── main.py            # ASGI entrypoint: `app = create_app()`, what uvicorn serves
│   ├── application.py     # `create_app()` factory: builds and configures the FastAPI instance
│   ├── lifespan.py        # Startup/shutdown logic wired via FastAPI's lifespan API
│   ├── api/                # HTTP route definitions (FastAPI routers)
│   │   ├── health.py        # GET /health, /ready, /version — unversioned system endpoints
│   │   └── products.py      # POST /products/upload (mounted under /api/v1) — Phase 2A + 2B
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
│   │   ├── upload_service.py # Phase 2A: stores uploaded product images (validation now delegated)
│   │   ├── checksum_service.py # Phase 2B: SHA-256 of an already-stored file
│   │   ├── product_service.py # Phase 2B: orchestrates checksum/image-processing/normalization/ID -> Product
│   │   └── image_processing_service.py # Phase 3: validate -> orient -> RGB -> resize -> save -> ImageMetadata
│   ├── validators/         # Reusable, pure validation functions — no I/O, no service state
│   │   ├── file_validator.py # Filename/extension + declared MIME type checks
│   │   ├── product_validator.py # Post-normalization product-field invariant checks
│   │   └── image_validator.py # Phase 3: genuine-image / corruption / format / dimension checks
│   ├── repositories/      # Data access layer (DB, vector store, cache) behind an interface
│   ├── models/             # Internal domain models — ORM-backed once persistence exists
│   │   ├── product.py       # `Product` — internal domain model, distinct from the API schemas — Phase 2B
│   │   └── image_metadata.py # `ImageMetadata` — internal, includes real filesystem paths — Phase 3
│   ├── schemas/            # Pydantic request/response schemas (API contracts)
│   │   ├── health.py        # Response models for /health, /ready, /version
│   │   ├── errors.py        # The `{"success", "error": {...}}` envelope every error returns
│   │   └── product.py       # ProductCreate, ProductImage, UploadResponse, ProductResponse — Phase 2A
│   ├── workers/            # Background jobs / async task consumers
│   ├── dependencies/       # FastAPI dependency-injection providers
│   │   ├── upload.py        # `get_upload_service()` — Phase 2A's first real dependency provider
│   │   └── product.py       # `get_product_service()` — Phase 2B (composes ImageProcessingService too)
│   └── utils/              # Small stateless helpers shared across layers
│       ├── metadata.py      # FileMetadata + parse_file_metadata() — Phase 2B "Parse Metadata" stage
│       └── image.py         # Phase 3: apply_orientation, normalize_color_mode, resize, filename helper
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
| `app/core/constants.py` | Fixed values the *code* decides, not per-deployment config: `Environment`/`LogLevel` enums, the `/api/v1` prefix, the obviously-fake default secret key, supported image extensions/MIME types, pagination limits, and (Phase 3) `SUPPORTED_IMAGE_PIL_FORMATS`, the standardized `PROCESSED_IMAGE_FORMAT`/`_EXTENSION`, and the default dimension limits. |
| `app/core/paths.py` | The one place that knows where the backend root actually is (`Path(__file__).resolve().parents[2]`) and derives `storage/`, `storage/uploads/`, `storage/processed/` (Phase 3), and `logs/` from it. Exposes `ensure_runtime_directories()` to create them — not called on import, so importing config stays side-effect-free and tests stay hermetic. |
| `app/core/settings.py` | The configuration *schema*: six `BaseModel` groups (`ApplicationSettings`, `DatabaseSettings`, `AIModelSettings`, `StorageSettings`, `SecuritySettings`, `LoggingSettings`) composed into one `Settings(BaseSettings)` root, with field-level and cross-field validation. `StorageSettings` gained three Phase 3 fields: `processed_dir`, `max_image_dimension_px` (safety ceiling), `processed_image_size_px` (resize target). No side effects — every class is directly constructible in a unit test. |
| `app/core/config.py` | The composition root: caches one `Settings()` instance via `@lru_cache` and exposes it as both `get_settings()` (for later FastAPI `Depends()` use) and the module-level `settings` singleton every other module should import. |
| `app/core/logging.py` | Configures the stdlib root logger (level from `settings.logging.level`, one console handler, a `timestamp \| level \| logger name \| message` formatter) and exposes `get_logger(name)` so any module gets a working, consistently formatted logger with zero setup. |
| `app/lifespan.py` | `lifespan(app)`: an `@asynccontextmanager` passed to `FastAPI(lifespan=...)`. Before `yield` (startup) it logs that the app is starting and calls `paths.ensure_runtime_directories()`; after `yield` (shutdown) it logs that the app is stopping. No database/AI connections yet — reserved for later milestones. |
| `app/application.py` | `create_app() -> FastAPI`: the only place `FastAPI(...)` is instantiated. Sets `title`/`description`/`version` from `settings.application` + `constants.DEFAULT_APP_DESCRIPTION`, wires in `lifespan`, then calls three private seams in order — `_register_middleware`, `_register_exception_handlers`, `_register_routers` — before returning the instance. |
| `app/main.py` | ASGI entrypoint: `app = create_app()`. This is the `app.main:app` target `uvicorn`/`make run` serve — one line of logic, everything real lives in `create_app()`. |
| `app/api/health.py` | `GET /health`, `/ready`, `/version` (Milestone 5). Deliberately unversioned (not under `/api/v1`) — see the Milestone 5 section below for why. Logs each call at `DEBUG` via `get_logger`. |
| `app/schemas/health.py` | Response models for the three endpoints above: `HealthResponse`, `ReadinessResponse` (with a `checks: dict[str, bool]` shape ready for real dependency checks later), `VersionResponse`. |
| `app/schemas/errors.py` | `ErrorResponse`/`ErrorDetail` (Milestone 6): the single `{"success": false, "error": {"code", "message", "details"}}` shape every error response uses. |
| `app/exceptions/base.py` | `AppException` (Milestone 6): the base class every domain exception subclasses. Carries a `status_code` (transport), a stable `code` (API contract), and a human `message` — see the Milestone 6 section for why those are kept separate instead of just using `HTTPException`. |
| `app/exceptions/errors.py` | Concrete, domain-agnostic exceptions: `ValidationException` (422), `ResourceNotFoundException` (404), `ConflictException` (409), (Phase 2A) `UnsupportedMediaTypeException` (415) and `FileTooLargeException` (413) for upload validation, (Phase 2B) `ChecksumException` (500) for a checksum that couldn't be computed, and (Phase 3) `InvalidImageException` (422, corrupted/undecodable image data) and `ImageTooLargeException` (413, pixel dimensions rather than byte size). |
| `app/exceptions/handlers.py` | `register_exception_handlers(app)`: registers one handler each for `AppException`, `RequestValidationError`, `StarletteHTTPException`, and `Exception` (the catch-all for real bugs), so every error path returns the same JSON envelope. |
| `app/middleware/request_id.py` | `RequestIDMiddleware` (Milestone 7): reuses an inbound `X-Request-ID` header or generates a UUID4, stores it on `request.state.request_id`, echoes it back as a response header. |
| `app/middleware/timing.py` | `TimingMiddleware`: measures handling duration with `time.perf_counter`, stores it on `request.state.duration_ms`, echoes it as `X-Response-Time-Ms`. |
| `app/middleware/logging.py` | `RequestLoggingMiddleware`: logs one line when a request starts, one when it finishes — both tagged with the request ID, the completion line also with status code and duration. |
| `app/middleware/security_headers.py` | `SecurityHeadersMiddleware`: stamps a baseline set of OWASP-recommended security response headers (`X-Content-Type-Options`, `X-Frame-Options`, etc.) via `setdefault`, so a route that already set one of these wins. |
| `app/schemas/product.py` | Phase 2A schemas: `ProductCreate` (name/description/category/price, bound from individual `Form(...)` fields), `ProductImage` (metadata about one stored file), `UploadResponse` (the upload endpoint's actual response — extended in Phase 2B with `product_id`/`checksum_sha256`, and in Phase 3 with `processed_image`), `ProcessedImageInfo` (Phase 3: the API-safe width/height/format/color_mode view, deliberately excluding real filesystem paths), and `ProductResponse` — reserved ahead of need for once a database exists, the same way Phase 1's `AIModelSettings` was reserved. |
| `app/models/product.py` | Phase 2B: `Product` — the internal domain model `ProductService` builds, deliberately separate from the `app/schemas/product.py` API contracts (see that phase's design decisions below for why). Holds normalized fields, the generated `id`, a `FileMetadata`, and (Phase 3) an `ImageMetadata`; never returned directly by a route. |
| `app/models/image_metadata.py` | Phase 3: `ImageMetadata` — internal, transport-agnostic description of a processed image: width, height, format, color mode, and the real `original_path`/`processed_path` filesystem paths. Built exclusively by `ImageProcessingService`; its paths are exactly why this stays a separate internal model from any API schema. |
| `app/services/upload_service.py` | Phase 2A: `UploadService` — stores an accepted file under a generated (never client-supplied) filename, streaming it to disk in bounded chunks while enforcing the size limit as it goes (never buffering more than one chunk past the limit). Filename/extension and MIME type validation were extracted to `app/validators/file_validator.py` in Phase 2B — this service now calls into it rather than deciding validation rules itself. All limits default to `settings.storage.*`/`constants.SUPPORTED_IMAGE_MIME_TYPES` but are constructor-overridable for tests. |
| `app/validators/file_validator.py` | Phase 2B: `validate_filename_and_extension`, `validate_mime_type` — pure functions (no I/O, no service state) extracted out of `UploadService` so validation rules are reusable independent of *how* a file gets stored. Size validation deliberately stays in `UploadService` — it's an inherently streaming, as-you-go check, not a pure function over an already-known value. |
| `app/validators/image_validator.py` | Phase 3: `ImageValidator` — verifies a stored file is a genuine, undamaged image (Pillow's `verify()` then a fresh reopen + full decode, per Pillow's own recommended pattern), rejects formats outside `constants.SUPPORTED_IMAGE_PIL_FORMATS`, and enforces `settings.storage.max_image_dimension_px`. Checks the *actually decoded* format, not the file extension or declared MIME type. |
| `app/validators/product_validator.py` | Phase 2B: `validate_normalized_name`, `validate_price` — re-check domain invariants *after* normalization that `ProductCreate`'s schema-level validation can't express (e.g. a name that's all whitespace passes `min_length=1` before trimming but is invalid after) or that should hold regardless of which caller builds a `Product`, not just the HTTP route. |
| `app/services/checksum_service.py` | Phase 2B: `ChecksumService.compute_sha256(path)` — streams an already-stored file from disk in 1 MiB chunks and returns its SHA-256 hex digest. Standalone (operates on any file path, not coupled to the upload stream) so later phases (duplicate detection, caching, integrity checks) reuse it instead of reimplementing hashing. Raises `ChecksumException` if the file can't be read. |
| `app/utils/metadata.py` | Phase 2B: `FileMetadata` (transport-agnostic file metadata: filename, extension, MIME type, size, SHA-256 checksum, upload timestamp) and `parse_file_metadata(image, checksum_sha256=...)`, the adapter from Phase 2A's `ProductImage` + a computed checksum into this internal object. |
| `app/utils/image.py` | Phase 3: pure Pillow transformation functions with no file I/O — `apply_orientation` (bakes in the EXIF rotation, via `ImageOps.exif_transpose`), `normalize_color_mode` (flattens any transparency onto white, then converts to RGB), `resize_preserving_aspect_ratio` (downscale-only, never upscales), `generate_processed_filename`. Each is directly unit-testable against an in-memory `PIL.Image`, no disk or service needed. |
| `app/services/image_processing_service.py` | Phase 3: `ImageProcessingService.process_image(original_path, stored_filename)` — validates via `ImageValidator`, then applies orientation, normalizes color mode, resizes, and saves a standardized JPEG copy under `settings.storage.processed_dir`, returning `ImageMetadata`. All Pillow calls run in a thread pool (blocking I/O), the same pattern `UploadService`/`ChecksumService` already use. |
| `app/services/product_service.py` | Phase 2B (extended in Phase 3): `ProductService.process_upload(product, image)` — the orchestrator. Locates the stored file, computes its checksum, standardizes the image (`ImageProcessingService`, Phase 3), parses `FileMetadata`, normalizes `name`/`description`/`category`/`price` (the module-level `_normalize_*` functions), re-validates the normalized result, generates a UUID4, and builds a `Product`. Logs each pipeline stage (never file contents). |
| `app/dependencies/upload.py` | `get_upload_service()`: a cached-singleton dependency provider for `UploadService`, mirroring `app.core.config.get_settings`'s pattern — Phase 2A's first real use of the `app/dependencies/` package reserved since Milestone 1. |
| `app/dependencies/product.py` | `get_product_service()`: the same cached-singleton pattern for `ProductService`. Neither `ChecksumService` nor (Phase 3) `ImageProcessingService` gets a provider of its own — both are composed internally by `ProductService`, not depended on directly by any route. |
| `app/api/products.py` | `POST /products/upload` (mounted under `/api/v1` — a real, versioned business endpoint, unlike `health.py`'s system routes). Accepts product metadata as individual `Form(...)` fields plus a `File()` upload; calls `UploadService.save_upload` (Phase 2A) then `ProductService.process_upload` (Phase 2B, now including Phase 3's image processing) in sequence, and maps the resulting `Product` (including its `image_metadata`) onto `UploadResponse`. See the Phase 2A section for why the fields are individual `Form(...)` params rather than a single `Annotated[ProductCreate, Form()]`. |
| `tests/__init__.py`, `tests/core/__init__.py`, `tests/api/__init__.py`, `tests/middleware/__init__.py`, `tests/exceptions/__init__.py`, `tests/schemas/__init__.py`, `tests/services/__init__.py`, `tests/dependencies/__init__.py`, `tests/utils/__init__.py`, `tests/validators/__init__.py`, `tests/models/__init__.py` | Makes each test directory a package so pytest resolves absolute imports the same way the app does; `tests/` mirrors `app/`'s layout. |
| `tests/services/test_product_service.py` | Direct unit tests for every `_normalize_*` function (trimming, case, category slugification and separator-collapsing, price rounding), plus `process_upload` end-to-end against `tmp_path` with a real Pillow-generated image: a full success case (checksum matches `hashlib.sha256` on the real stored content, fields normalized correctly, `image_metadata` populated, a fresh UUID4 per call), the whitespace-only-name and negative-price defensive-validation paths (the latter via `ProductCreate.model_construct` to simulate a caller that bypassed schema validation), a missing stored file raising `ChecksumException`, and a corrupt stored file raising `InvalidImageException`. |
| `tests/dependencies/test_product.py` | Confirms `get_product_service()` returns a cached singleton and that `cache_clear()` forces a fresh instance — the same contract as `tests/dependencies/test_upload.py`. |
| `tests/conftest.py` | Shared fixtures (Milestone 8): `app` (a fresh `create_app()` instance per test) and `client` (a `TestClient` bound to it, entered as a context manager so the lifespan actually runs). Only fixtures genuinely needed by multiple modules live here. |
| `tests/test_environment.py` | A single sanity test (Python version check) proving the pytest + coverage pipeline actually runs. |
| `tests/core/test_paths.py` | Verifies path relationships (`UPLOAD_DIR`/`PROCESSED_DIR` under `STORAGE_DIR`, etc.) and that `ensure_runtime_directories()` creates the right directories (including Phase 3's `PROCESSED_DIR`), using `monkeypatch` + `tmp_path` so it never touches the real filesystem. |
| `tests/core/test_settings.py` | Covers defaults, field validation (port range, minimum secret-key length, `SecretStr` not leaking into `repr()`), env-var overrides via nested `__` delimiters, every production-safety rule in `Settings._validate_production_safety` (including the Milestone 7 `trusted_hosts` rule), the `cors_allowed_origins`/`trusted_hosts` defaults, and (Phase 3) `StorageSettings`' defaults and its two positive-only dimension fields. |
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
| `tests/schemas/test_product.py` | Field validation (empty name, negative price, numeric-string coercion), a `ProcessedImageInfo` construction check, a `ProductImage`/`UploadResponse` (now including `processed_image`) round-trip through `model_dump`/`model_validate`, and a sanity construction of the reserved `ProductResponse`. |
| `tests/services/test_upload_service.py` | Unit tests for `UploadService` against a fake `UploadFile` and a `tmp_path` upload directory: successful storage (content matches, filename is generated, extension preserved/lowercased), every validation rejection (missing filename, disallowed extension/MIME type, oversized file), and that a rejected/oversized upload leaves no partial file behind. |
| `tests/dependencies/test_upload.py` | Confirms `get_upload_service()` returns a cached singleton and that `cache_clear()` forces a fresh instance — the same contract `tests/core/test_config.py` verifies for `get_settings()`. |
| `tests/services/test_checksum_service.py` | Confirms the digest matches `hashlib.sha256` directly for both a small file and one spanning multiple 1 MiB chunk reads, that identical content hashes identically and different content differs, and that a missing file raises `ChecksumException`. |
| `tests/utils/test_metadata.py` | Confirms `FileMetadata` rejects a malformed/uppercase checksum, and that `parse_file_metadata` correctly lowercases the derived extension while carrying every other `ProductImage` field through unchanged. |
| `tests/utils/test_image.py` | Unit tests against in-memory Pillow images, no disk: `apply_orientation` (EXIF orientation 6 swaps dimensions; no-tag/normal-orientation images pass through unchanged), `normalize_color_mode` (RGB is a no-op by object identity; RGBA transparency flattens to white while opaque RGBA color is preserved; grayscale/palette convert to RGB), `resize_preserving_aspect_ratio` (downscales correctly, is a no-op at/under the limit, never produces a zero-sized result for a 1×1 image), and `generate_processed_filename`'s extension standardization. |
| `tests/validators/test_file_validator.py` | Direct unit tests for both functions: allowed/disallowed extensions and MIME types, extension lowercasing, missing/empty filename, a filename with no extension at all, and a missing MIME type. |
| `tests/validators/test_product_validator.py` | Confirms `validate_normalized_name` rejects only a blank string, and `validate_price` accepts `None`/zero/positive values but rejects negative ones. |
| `tests/validators/test_image_validator.py` | Against real files on disk: accepts valid JPEG/PNG/WEBP/1×1 images; rejects a non-image file, a severely truncated JPEG (fails `verify()`), and a JPEG truncated at 90% of its bytes (passes `verify()` but fails the full decode — exercises that failure path specifically); rejects a format outside the allowed set even with a *misleading extension* (a BMP saved as `photo.jpg`, proving this checks real decoded content); and rejects/accepts images at, above, and below a configurable dimension limit. |
| `tests/models/test_product.py` | Confirms `Product` constructs with all fields (including Phase 3's `image_metadata`), accepts `None` for every optional field, and round-trips through `model_dump`/`model_validate`. |
| `tests/models/test_image_metadata.py` | Confirms `ImageMetadata` constructs with all fields, rejects non-positive width/height, and round-trips through `model_dump`/`model_validate`. |
| `tests/services/test_image_processing_service.py` | Against real files on disk: a full success case (correct `ImageMetadata`, a genuinely reopenable output JPEG), RGBA PNG → RGB JPEG conversion, resizing an oversized image while preserving aspect ratio, leaving a small image at its original size, processing a 1×1 image without error, applying EXIF orientation before saving (dimensions swap correctly), creating the processed directory if missing, and propagating each of `ImageValidator`'s three exception types (plus confirming no processed file is written when validation fails). |
| `tests/api/test_products.py` | Integration tests against the *real* `create_app()` app, with both `get_upload_service` and `get_product_service` (now composing an `ImageProcessingService`) overridden (`app.dependency_overrides`) to redirect storage to the same `tmp_path`. Every uploaded file is a real Pillow-generated JPEG. Covers: a successful upload's normalized response fields and `processed_image` dimensions/format, a valid `product_id`/`checksum_sha256` (verified against `hashlib.sha256` on the actual submitted bytes), on-disk file content, every validation failure's status code and error envelope (missing name, whitespace-only name reaching `ProductService`, disallowed extension/MIME type, negative price, a non-image file with an allowed extension — Phase 3's `invalid_image`), and the oversized-file 413 case. |
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

Phase 2B shipped as six milestones, each its own commit — Checksum
Service, File Metadata, Validators, Product Domain Model, ProductService,
and finally Router Integration (this section's last entry) — so each
piece could be verified and reviewed independently rather than landing as
one large, hard-to-review change.

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

**Why extract `file_validator.py` out of `UploadService` now, instead of
leaving the validation logic where Phase 2A put it?** Phase 2B introduces
a second reason to want these same rules: `ProductService`'s pipeline
needs to validate *normalized* product fields too, and putting all
validation logic in dedicated `app/validators/` modules — rather than
scattered across whichever service happens to need it first — means both
`UploadService` and `ProductService` (and any future caller) share one
place that decides what's acceptable, instead of validation rules being
an accidental side effect of `UploadService`'s specific implementation.
This is also a concrete instance of a general principle worth stating
plainly: **don't put validation inside services.** A service's job is to
*orchestrate* (validate, then act); the validation rules themselves are a
separate, independently testable concern.

**Why is file *size* validation deliberately NOT moved into
`file_validator.py`?** Extension and MIME type validation are pure
functions over an already-known value (you have the filename/content-type
string before you check it). Size validation is fundamentally different:
the file's total size isn't known until it's been completely read, and
`UploadService` deliberately checks the running total *during* the
streaming read (aborting and deleting the partial file the moment the
limit is exceeded) rather than reading everything first and checking
after — see Phase 2A's rationale. Forcing that into a "pure validator
function" shape would mean either buffering the whole file first
(defeating the point) or leaking streaming/disk-I/O concerns into what's
supposed to be a dependency-free validator module. It stays exactly where
it naturally belongs: interleaved with the write loop in `UploadService`.

**Why does `product_validator.py` re-check things `ProductCreate`'s
pydantic `Field()` constraints already seem to cover (e.g. price
non-negativity)?** Two independent reasons converge on the same
validator: (1) a name of `"   "` (whitespace) satisfies
`Field(min_length=1)` — the *raw* string has length 3 — but is invalid
once normalized to `""`, a case schema validation structurally cannot
catch because normalization hasn't happened yet at that point. (2)
`Product` (the domain model, next milestone) shouldn't have to trust that
every possible caller already ran it through `ProductCreate` and FastAPI's
validation — a defense-in-depth domain layer validates its own
invariants at the point a domain object is actually built, not just at
the HTTP boundary. Price's non-negativity check is cheap insurance for
(2) even though today's only caller already satisfies it via (1)'s
sibling mechanism.

**Why is `Product` (`app/models/product.py`) a separate type from
`ProductCreate`/`ProductResponse` (`app/schemas/product.py`), given both
are pydantic `BaseModel`s and could plausibly be the same class?** They
answer different questions and change for different reasons.
`ProductCreate` answers "what shape must an HTTP request arrive in" — it's
coupled to FastAPI (`Form()` bindings, `Field()` constraints tuned for
raw/untrusted input) and changes when the *wire contract* changes.
`Product` answers "what is a product, internally" — no FastAPI coupling
at all, holds the generated `id` and the richer `FileMetadata` neither
`ProductCreate` nor `ProductResponse` carry, and changes when the
*business concept* changes (e.g. a later phase adding an internal
processing-status field that should never appear in an API response).
Collapsing them into one class would mean every future change has to ask
"does this affect the wire contract or just internals" and often get it
wrong under time pressure; keeping them separate from the start means
that question never has to be asked. This is also literally what the
phase's deliverables asked for — "Separate `UploadResponse` from
`Product`" — made concrete: `app/api/products.py` (next milestone) maps
`Product`'s fields onto `UploadResponse` explicitly, so a route never
returns the internal model directly, and the API response shape stays
whatever `UploadResponse` declares even if `Product` grows new
internal-only fields later.

**Why doesn't `Product` re-declare `ProductCreate`'s `Field()`
constraints (`min_length`, `max_length`, `ge=0`)?** By the time
`ProductService` constructs a `Product`, the values have already passed
through `ProductCreate`'s schema validation *and*
`app/validators/product_validator.py`'s post-normalization checks (see
above) — both are the actual enforcement points. Repeating the same
constraints a third time on `Product` would be pure duplication with
nothing new enforced; a domain model built exclusively by one trusted,
internal factory (`ProductService`) is allowed to trust its constructor
was called correctly, the same way a class's private helper methods
don't re-validate arguments the public method already checked.

**Why do the `_normalize_*` functions live as module-level, underscore-
prefixed functions in `product_service.py` rather than their own file or
a `Normalizer` class?** The phase's own prescribed folder structure lists
no dedicated normalizer module — normalization is treated as part of
`ProductService`'s orchestration, not an independent, swappable component
the way validation (used by multiple services) or checksumming
(genuinely reusable across features) are. Module-level functions
(matching the existing precedent of `app/exceptions/handlers.py`'s
`_error_code_for_status` and `app/core/logging.py`'s
`_build_handlers`/`_console_formatter`) are directly unit-testable without
needing a class instance, while staying private to the module that's
their only caller — the right amount of structure for logic that doesn't
need to be reused or substituted independently.

**Why does `_normalize_name` only trim whitespace (no case change), while
`_normalize_category` both lowercases *and* slugifies?** They represent
genuinely different kinds of data. A product name is a proper
noun/brand — `"Nike"` and `"nike"` are the same brand but a route that
silently lowercased "Nike" to "nike" would be presenting the brand
incorrectly back to the user; only whitespace is unambiguously
insignificant there. A category, by contrast, exists purely to group and
filter products consistently — `"Men Tshirts"`, `"men tshirts"`, and
`"MEN-TSHIRTS"` should all collapse to the identical `"men-tshirts"` slug
so that filtering/grouping by category actually works, which requires
both case-folding and structural normalization (spaces/punctuation ->
hyphens), not just whitespace trimming.

**Why is price normalized with `round(price, 2)` rather than a `Decimal`
type?** `ProductCreate.price` is already a `float` (chosen in Phase 2A to
keep form-field coercion simple — form data arrives as strings, and
pydantic's lax mode coerces `"19.99"` to `float` without extra
configuration). Introducing `Decimal` now, only for the rounding step,
would mean converting `float` -> `Decimal` -> back to `float` (since
`Product.price` and the API response are still `float`) for no actual
precision benefit — floating-point imprecision matters when *repeatedly
accumulating* money (e.g. summing many prices), not for rounding one
value for display. A real ledger/accounting feature in a later phase
would be the appropriate place to introduce `Decimal` end-to-end, not
here.

**Why does `ProductService.process_upload` take an already-built
`ProductImage` (from `UploadService`) instead of the raw `UploadFile`
itself?** It keeps the two services' responsibilities cleanly separated
along the line the pipeline diagram itself draws: `UploadService` owns
*"is this file acceptable, and where does it live"* (Phase 2A);
`ProductService` owns *"now that it's stored, process it into a
product"* (Phase 2B). Passing `UploadFile` into `ProductService` would
require it to also know about streaming/validation/storage — exactly the
concerns Phase 2A already solved and tested. The router
(`app/api/products.py`, next milestone) is what actually sequences the
two calls.

**Why does the logging follow exactly this sequence — "Upload processing
started" -> "Checksum generated" -> "Normalization complete" -> "Product
processed" — and never include file contents?** This directly mirrors
the four checkpoints the phase asked for, giving an operator reading logs
a clear, ordered trace of exactly how far a given upload got if something
fails partway through (e.g. logs ending after "Checksum generated" but
before "Normalization complete" immediately localizes a bug to
normalization/validation). File *contents* are exactly the kind of thing
that must never appear in a log line — arbitrarily large, potentially
sensitive, and useless for debugging compared to the filename/checksum/id
that are actually logged instead.

**Why does `UploadResponse.product` reflect the *normalized* fields
(what `ProductService` produced) rather than exactly what the client
submitted?** The response should describe what was actually processed and
would, in a later phase, be persisted — showing the raw un-normalized
input back would misrepresent that. A client that submitted `" Nike "`
and a category of `"Men Tshirts"` sees `"Nike"` and `"men-tshirts"` in the
response, which is also simply more useful: it's confirmation of the
canonical form the system will use everywhere else (filtering, search,
display) going forward.

**Why do `product_id` and `checksum_sha256` land as new top-level fields
on `UploadResponse`, instead of nesting them inside `ProductImage`?**
`ProductImage` is Phase 2A's contract for "what `UploadService` knows the
instant a file is saved" — before a checksum has even been computed.
Extending it with a field that's only populated by a *different*,
later-running service would blur what `ProductImage` actually represents
and could create a confusing window where an `image` object exists with
the field unset. Adding `product_id`/`checksum_sha256` directly to
`UploadResponse` instead keeps `ProductImage`'s meaning exactly what it
was in Phase 2A, while still surfacing both new pieces of information at
the top level of the one response a client actually receives.

**Why does the router call `upload_service.save_upload` and
`product_service.process_upload` as two sequential `await`s, instead of
`ProductService` internally depending on `UploadService`?** This mirrors
the pipeline the phase's own diagram draws: Upload (Phase 2A, "is this
file acceptable, where does it live") happens completely, then
processing (Phase 2B, "now that it's stored, build a product from it")
begins. Keeping that sequencing visible in the router — rather than
hidden inside a `ProductService` that internally calls `UploadService` —
means the route function itself is a readable, linear description of the
whole pipeline, and each service can be tested (and reasoned about)
without needing the other to exist.

## Phase 3 — Image Processing Pipeline design decisions

This is where AI-facing work begins: standardizing an uploaded image into
the consistent format models like CLIP/DINOv2 expect, before any
embedding/model-calling phase exists. Six pieces landed, in dependency
order (not quite the milestone numbering the phase spec listed, since
that numbering wasn't a buildable order — utilities and the domain model
are dependencies of the validator/service that use them, so they're built
first; see the "How this was created" commands below for the exact
correspondence): image utilities, the `ImageMetadata` domain model,
`ImageValidator`, `ImageProcessingService`, and finally wiring it all into
`ProductService`/the router/response schema.

**Why is `ImageValidator` a class (with configurable limits) while
`file_validator.py` is plain functions?** `ImageValidator` needs to hold
configuration (`max_dimension_px`, `allowed_formats`) across its two
internal steps (`_verify_integrity`, `_decode`) the same way
`UploadService`/`ProductService` hold theirs — a class with an `__init__`
is the natural shape for "a validator with configurable limits called
more than once," the same reasoning that already makes those two
services classes rather than free functions. `file_validator.py`'s two
functions take their limits as explicit parameters instead because they
have no state to hold between calls and nothing else to configure.

**Why the two-pass `verify()` then reopen-and-`load()` pattern, instead of
just calling `.load()` once?** This is Pillow's own documented pattern for
a reason: `Image.verify()` is a cheap structural check (headers/file
structure, no full pixel decode) that catches obviously malformed files
fast, but Pillow's own docs say the `Image` object is unusable for
anything else afterward — hence reopening fresh. Relying on `verify()`
alone isn't enough, though: it can pass on a file whose *pixel data* is
truncated (see `tests/validators/test_image_validator.py`'s "scan data"
test, which found the exact byte-truncation percentage where this
actually happens) — only a full `.load()` catches that. Using only
`.load()` and skipping `.verify()` would work for correctness, but
`verify()`-then-`load()` is what Pillow recommends and it costs nothing
extra to keep it, so both checks stay.

**Why catch `Exception` broadly in `ImageValidator` instead of specific
Pillow exception types?** Pillow raises different exception types across
its per-format plugins and failure modes — plain `OSError`,
`SyntaxError`, its own `UnidentifiedImageError`, and others — for "this
isn't decodable." Enumerating all of them (and keeping the list current
as Pillow evolves) would be a maintenance burden for no benefit: every
one of them means the same thing to a caller ("not a valid image"),
converted uniformly to `InvalidImageException`.

**Why does `InvalidImageException` (422) exist separately from
`UnsupportedMediaTypeException` (415), when Phase 2A already established
415 for "the payload is the wrong kind of thing"?** They're different
failures at different points in the pipeline. `UnsupportedMediaTypeException`
already covers "the file's *extension/declared type* isn't accepted"
(Phase 2A, `file_validator`) and now also "it decoded fine, but to a
format outside the allowed set" (Phase 3, e.g. a real BMP). Neither of
those describes "the bytes claim to be an image and even have an allowed
extension, but Pillow can't make sense of them at all" — corruption,
truncation, or a non-image file with a misleading name. That's a
different failure mode (the *content* is broken, not merely the wrong
*kind*), so it gets its own type and its own 422. This is exactly the
`InvalidImageException` the Phase 2B section predicted might be needed
"once something actually raises it" — deliberately not added back then
because nothing did yet.

**Why is `ImageTooLargeException` (413) distinct from Phase 2A's
`FileTooLargeException` (413), given they share a status code?** They
measure two independent things a client could abuse independently: byte
size on disk (`FileTooLargeException`, enforced while streaming to disk)
versus decoded pixel dimensions (`ImageTooLargeException`, enforced by
`ImageValidator` after a full decode). A small, heavily-compressed file
can still decode into an enormous pixel grid — a classic
"decompression bomb" — so passing the byte-size check proves nothing
about the dimension check, and vice versa. Sharing a status code is fine
(clients that care about the distinction branch on `code`, not status);
what matters is that each has its own independent, correctly-scoped
enforcement point.

**Why does every processed image get re-encoded to JPEG, even a PNG or
WEBP input?** Standardizing the *output* format (not just color mode)
removes an entire axis of variation every downstream consumer would
otherwise have to handle: no alpha channel to worry about (already
resolved during color-mode normalization), one decoder to support, one
set of assumptions about compression artifacts. A later phase generating
embeddings only ever has to open one format, regardless of what a client
originally uploaded.

**Why does `resize_preserving_aspect_ratio` only ever downscale, never
upscale?** Upscaling a smaller image fabricates detail that was never
actually captured — it would make a low-resolution photo *look* like it
has more information than it does, which is actively misleading input to
a downstream embedding model rather than neutral. A smaller image is left
exactly as it is; only images exceeding the target size are resized down.

**Why does `normalize_color_mode` flatten transparency onto a *white*
background specifically, not black or some other color?** There's no
universally "correct" answer — a transparent pixel has no defined color,
full stop — but white is the least visually surprising default for
product photography specifically (the overwhelmingly common real-world
use case here): product photos are conventionally shot against white or
neutral backgrounds already, so compositing transparency onto white tends
to blend in rather than introduce a jarring border artifact the way black
often would against a light-colored product.

**Why does `apply_orientation` strip the EXIF orientation tag rather than
just rotating the pixels and leaving the tag in place?** `ImageOps.exif_transpose`
does this automatically as part of applying the rotation — and it must:
if the tag were left at (say) `6` after the pixels were already rotated
to account for it, any *other* tool that reads EXIF (a browser, another
image library, a later phase's own re-processing) would rotate an
already-correctly-oriented image a second time. Baking the rotation into
the pixels and clearing the tag is what makes "orientation" a property of
the pixel data going forward, not metadata a future reader has to
remember to check.

**Why does `ImageProcessingService` run every Pillow call inside
`run_in_threadpool`, the same as `UploadService`/`ChecksumService`?**
Pillow's I/O and decode/encode operations are synchronous and CPU/disk-
bound — calling them directly inside an `async def` would block the
single event loop for the duration of every image operation, stalling
every other concurrent request the server is handling. This is the same
reasoning Phase 2A/2B already established for file I/O; Phase 3 just
applies it to Pillow specifically.

**Why does `ProductService` compose `ImageProcessingService` internally
(the same way it already composes `ChecksumService`) instead of the
router calling `UploadService` → `ChecksumService` → `ImageProcessingService`
→ `ProductService` as four separate steps, matching the phase's own
pipeline diagram literally?** "Keep routers thin" is stated as a hard
requirement in both this phase and Phase 2B's — exploding the router into
four sequential service calls would violate that, and would also break
the precedent Phase 2B already set (checksum computation lives inside
`ProductService`, not the router). Read as a *logical* data-flow diagram
(what depends on what, in what order) rather than a literal call
sequence the router must perform, the diagram is fully satisfied: the
router still calls exactly two things (`UploadService.save_upload`, then
`ProductService.process_upload`), and internally `ProductService` runs
checksum → image processing → metadata → normalize → validate → build, in
that order — "the image is processed before metadata is finalized" holds
exactly as stated.

**Why does `ProcessedImageInfo` (the API-facing schema) expose only
width/height/format/color_mode, and not `ImageMetadata`'s
`original_path`/`processed_path`?** Those are real server filesystem
paths — the same reasoning that already keeps `ProductImage` (Phase 2A)
down to a generated `stored_filename` rather than a path. Leaking a
server's directory structure into an API response is an unforced
information disclosure with no benefit to a legitimate client.

**Why does `UploadResponse.processed_image` sit as a new top-level field
rather than nested inside `image` (`ProductImage`)?** Same reasoning
Phase 2B already used for `checksum_sha256`: `ProductImage` is Phase 2A's
contract for "what `UploadService` knows the instant a file is saved" —
before any Phase 3 processing has even started. Extending it with fields
a *later*, different service populates would blur what `ProductImage`
actually represents and create a window where an `image` object exists
with those fields meaningless/unset.

**Why doesn't this phase add HEIC support, despite the phase's own
motivation section naming it as a real-world format phones commonly
produce?** HEIC isn't decodable by Pillow out of the box — it requires an
additional third-party plugin dependency (e.g. `pillow-heif`), which
isn't among this phase's listed deliverables. Mentioning HEIC as
*motivation* for why normalization matters in general doesn't imply every
mentioned format must be supported; the explicitly listed supported
formats (JPEG/PNG/WEBP, unchanged from Phase 2A) are what's actually
implemented. A HEIC upload today is correctly rejected as an unsupported
extension at the existing `file_validator` stage — adding real HEIC
support later is a small, isolated addition (one new allowed extension/
MIME type/PIL format, plus the new dependency) whenever it's actually
needed.

## Phase 4 — Image Embedding Pipeline design decisions

This is the first phase that actually calls an AI model. Five pieces
landed, in dependency order: AI settings + a new exception type,
`BaseEmbeddingService` (the abstraction `ProductService` depends on),
`ModelManager` (lazy-loads and caches CLIP checkpoints), `CLIPEmbeddingService`
(the concrete implementation), the `ImageEmbedding` domain model, and
finally wiring it all into `ProductService`/the router/response schema —
the same "build the interface and its dependencies before the thing that
composes them" order Phase 3 used.

**Why extend `AIModelSettings` instead of creating the phase-suggested
`app/config/ai.py`?** `AIModelSettings` already existed from Phase 1,
explicitly reserved for "AI provider and model configuration" with
`openai_api_key`/`embedding_model`/`llm_model` fields for a future
OpenAI-based *text* embedding/LLM phase — no calls to them were made yet.
Adding a second, differently-named config module for image-model settings
would fragment AI configuration across two places for no benefit; the
phase's own "follow the architecture from previous phases" instruction is
better served by using the seam Phase 1 already built than by following
the suggested folder layout literally. `clip_model_name`/`embedding_device`/
`embedding_batch_size` are kept as distinctly-named fields rather than
reusing `embedding_model`, since a CLIP checkpoint name and an OpenAI
text-embedding model name are unrelated settings that happen to share the
word "embedding."

**Why does `ModelManager` have no `get_model_manager()` cached-singleton
factory, unlike `get_settings()`/`get_upload_service()`/`get_product_service()`?**
A `ModelManager` only ever needs to exist once because `CLIPEmbeddingService`
(its only caller) is itself constructed exactly once, as part of the
already-cached `get_product_service()` singleton. Being constructed once,
transitively, is exactly the same "loaded once, reused forever" guarantee
a dedicated cache would provide — a second caching layer on top would be
redundant and would need to be kept in sync with the first for no reason.

**Why is `ModelManager.get_model` thread-safe (double-checked locking)
when nothing else in this codebase needs explicit locking?** Every other
service here is stateless per-request or only ever mutates request-scoped
data. `ModelManager` is different: it holds process-wide mutable state (a
dict of loaded models) that concurrent requests genuinely race over on
first use. Without locking, two concurrent requests for the same
not-yet-loaded model could both pass the "is it cached?" check, both
trigger a real (expensive) load, and both end up needlessly holding a
duplicate copy of the model in memory. The lock is only acquired on a
cache miss — an already-loaded model is returned with no locking
overhead at all.

**Why does `CLIPEmbeddingService._encode_batch` read `.pooler_output`
off the result of `model.get_image_features(...)` instead of using the
tensor directly?** This is a real, version-specific behavior discovered
by inspecting the installed `transformers` library's own source
(`inspect.getsource`), not assumed from documentation: in the installed
version, `get_image_features` returns a `BaseModelOutputWithPooling`
object, not a bare tensor — the actual image embedding (after CLIP's
visual projection layer) lives at `.pooler_output` on that object. Trusting
outdated tutorials/docs here would have silently produced wrong code that
only fails once a real model is loaded, which is exactly why this phase's
integration tests load a real (if tiny) checkpoint rather than relying
solely on fakes.

**Why does every embedding get L2-normalized before being returned?**
Downstream consumers of an embedding (semantic search, duplicate
detection — later, out-of-scope-for-this-phase work) almost always want
cosine similarity between vectors. Normalizing once, at generation time,
means cosine similarity reduces to a plain dot product wherever it's
later needed, rather than every future caller having to remember to
normalize (or re-normalize) it themselves.

**Why does `BaseEmbeddingService` declare an abstract `model_name`
property, not just the two `generate_embedding(s)` methods the phase
spec listed?** `ProductService` needs to record, on every `ImageEmbedding`
it builds, which model actually produced that vector. Reading it from
settings would be wrong the moment a test (or a future caller) injects a
`CLIPEmbeddingService` configured with a different model than the
process-wide default — the service that did the encoding is the only
real source of truth for what model it used, so the interface makes that
queryable rather than letting callers guess.

**Why does `ProductService` embed `image_metadata.processed_path` (the
standardized JPEG `ImageProcessingService` produced), not the original
uploaded file?** The whole point of Phase 3's standardization step —
consistent orientation, color mode, encoding — is that everything
downstream, including embedding generation, operates on one predictable
representation instead of every possible input format/orientation/color
mode a client might upload. Embedding the raw upload would reintroduce
exactly the variation Phase 3 exists to remove.

**Why does `EmbeddingInfo` (the API-facing schema) expose only
`model_name`/`dimension`, never `ImageEmbedding.vector`?** Same reasoning
Phase 3's `ProcessedImageInfo` already established for excluding server
filesystem paths: a raw 512-float (or whatever the model's dimension is)
array has no use to an API consumer today — no similarity search or
persistence layer exists yet for a client to do anything with it — so
returning it would just bloat every response with data nobody can act on
yet, without a considered decision about wire format, precision, or size
once it actually matters.

**Why does `ProductService` construct its `CLIPEmbeddingService` as a
`BaseEmbeddingService | None = None` constructor parameter, matching
`checksum_service`/`image_processing_service`, instead of importing
`CLIPEmbeddingService` directly?** This is the same "depend on the seam,
not the concrete implementation" reasoning already used throughout this
codebase — a future encoder (DINOv2, SigLIP, ...) becomes a drop-in
replacement with nothing outside `app/services/embeddings/` changing, and
tests can inject a fast fake instead of loading a real model.

**Why do this phase's tests use a hybrid strategy — fast fake-loader
logic tests plus a handful of tests against a real, tiny CLIP checkpoint
(`hf-internal-testing/tiny-random-CLIPModel`), instead of fakes
everywhere?** Fakes alone would have missed the `.pooler_output` bug
above entirely — they only assert that *this codebase's* logic is
correct, not that real `transformers`/`torch` behaves the way the code
assumes. A tiny, fast-downloading real checkpoint published specifically
for test suites gives genuine end-to-end confidence (model loading,
device placement, real tensor shapes, real inference) at a fraction of
the size/time cost of the actual default model
(`openai/clip-vit-base-patch32`), which is only ever downloaded outside
of tests, on first real use.

## Phase 5 — Vector Search & Retrieval design decisions

This phase closes the loop Phase 4 deliberately left open: an embedding
existed per product, but nothing stored it anywhere searchable. Six
pieces landed, in dependency order: `BaseVectorStore` (plus `NearestNeighbor`,
built ahead of its own milestone for the same reason Phase 3/4's domain
models were), `QdrantVectorStore`, the rest of the search domain models
(`SearchQuery`/`SearchResult`), `SearchService` (plus wiring `ProductService`
to upsert on upload), the `/products/search` endpoint, and a final pass
hardening test coverage across the whole pipeline.

**Why does `ProductService` upsert into the vector store, when the phase
spec's own milestones only describe the search *query* side?** Without
it, `SearchService` would only ever search an empty collection — the
feature would be mechanically correct and permanently useless against
real uploads. Upserting immediately after building a `Product`, in the
same request, keeps "a product is uploaded" and "a product is
searchable" one atomic-feeling step, the same way Phase 4 folded
embedding generation into the upload flow rather than leaving it a
separate, easy-to-forget call.

**Why is `QdrantVectorStore`'s collection created lazily, on first use,
rather than eagerly at construction — unlike, say, `UploadService`/
`ImageProcessingService` eagerly `mkdir`-ing their directories?** Those
`mkdir` calls are local filesystem operations with no failure mode worth
guarding against in normal operation. A live Qdrant connection is
different: `ProductService`/`SearchService` build a `QdrantVectorStore` as
part of their own construction, and eager collection-creation would mean
*constructing* either service — including in a plain dependency-injection
unit test, or at real application startup — requires a running Qdrant
server before any request ever actually needs one. This was caught
directly: an initial eager implementation broke
`tests/dependencies/test_product.py`'s "does this provider return an
instance" test the moment it tried to build a real `ProductService`.
Fixed by reusing `ModelManager`'s (Phase 4) exact double-checked-locking
"lazy, load/create once" pattern instead.

**Why cosine distance, non-configurable?** `CLIPEmbeddingService`
(Phase 4) already L2-normalizes every embedding it produces specifically
so cosine similarity — the angle between two vectors, not their raw
magnitude — is the meaningful notion of "similar" for CLIP embeddings.
Any other distance metric would be measuring something CLIP's embedding
space wasn't shaped for.

**Why does `BaseVectorStore` know nothing about `SearchQuery`/`SearchResult`
(Phase 5's other domain models), only the more primitive `NearestNeighbor`?**
`BaseVectorStore` is a general storage abstraction — `upsert`/`search`/
`delete`/`exists`/`health` on vectors, IDs, and metadata — that has no
inherent reason to know about "a search," specifically. `SearchQuery`/
`SearchResult` are `SearchService`'s own vocabulary for bundling a
resolved query and its outcome; coupling the storage interface to them
would make `BaseVectorStore` harder to reuse for anything other than
today's one use case (e.g. a future duplicate-detection phase that also
needs `upsert`/`search` but has nothing to do with "a search request").

**Why does `SearchService` compose `ImageProcessingService` itself
(standardizing the query image) rather than trusting whatever the client
uploaded?** A stored product's embedding was generated from its
*standardized* image (Phase 4) — same orientation, color mode, and size
every time. Embedding a raw, un-standardized query image would compare
two embeddings produced under different preprocessing, degrading
similarity scores for reasons that have nothing to do with the products
actually looking different. Reusing `ImageProcessingService` (the exact
class `ProductService` already uses) guarantees both sides of the
comparison go through identical preprocessing.

**Why does `QdrantVectorStore.search`'s `filters` parameter only support
equality (`{"category": "shoes"}`), not richer range/comparison queries?**
It's deliberately the smallest thing that satisfies the phase's actual
requirement ("metadata filtering") without building a query-DSL translator
nothing calls yet. Qdrant's own `MatchValue` filter condition (what
`_build_filter` translates every key/value pair into) is itself
equality-only for exactly this reason — richer filtering (numeric ranges,
etc.) would need a different Qdrant condition type, added when a real use
case needs it rather than speculatively now.

**Why does `ProductSearchResult` (the API schema) duplicate
`NearestNeighbor` (the internal domain model) field-for-field instead of
returning `NearestNeighbor` directly?** Same reasoning as every other
schema/model split in this codebase (see `app/models/product.py`'s
docstring) — the API response is a contract this codebase controls
independently of whatever shape happens to come back from the vector
store internally. Today they happen to have identical fields; that's a
coincidence of this phase, not a guarantee either type won't diverge
later (e.g. `NearestNeighbor` gaining an internal-only field that
shouldn't reach a client).

**Why does the response only ever include `product_id`/`score`/`metadata`,
never the raw embedding vector — for either the query image or a
matched product?** Stated directly in the phase requirements ("Never
expose raw embedding vectors"), and consistent with `EmbeddingInfo`
(Phase 4) already establishing "don't return a raw float array a client
has no way to act on."

**Why do the vector-store tests run against a real
`QdrantClient(location=":memory:")` instead of a fake?** The official
client's own local, in-process mode gives genuine confidence that this
codebase's actual filter/point/collection construction is compatible with
the real `qdrant-client` API — which matters concretely: this client
version (`1.18.0`) replaced the older `search` method with `query_points`,
discovered by inspecting the installed library directly rather than
trusting possibly-outdated docs, the same diagnostic approach Phase 4
used for `get_image_features`'s `.pooler_output`. A fake would only ever
prove this codebase's own logic was internally consistent, not that it
actually matches Qdrant's real behavior.

## Phase 6 — Text Embeddings & Hybrid Search design decisions

This phase adds a second modality alongside Phase 4/5's image pipeline:
every uploaded product now also gets a text embedding (from its name,
brand, category, and description), indexed into its own Qdrant
collection, searchable on its own or fused with an image search. Six
pieces landed, in dependency order: text embedding infrastructure
(`BaseTextEmbeddingService`, `SentenceTransformerEmbeddingService`,
`TextModelManager`, `TextEmbedding`), the two-collection vector store
redesign that both product indexing and search need, product text
indexing (`ProductService` wiring), `HybridSearchService`, and finally
the replaced `/products/search` endpoint.

### Architecture

```
                     ProductService.process_upload
                              │
              ┌───────────────┼───────────────┐
              ▼                               ▼
      CLIPEmbeddingService          SentenceTransformerEmbeddingService
      (image embedding)             (text embedding: name/brand/
              │                      category/description)
              ▼                               ▼
      QdrantVectorStore.upsert_image   QdrantVectorStore.upsert_text
              │                               │
              ▼                               ▼
      "product_images" collection    "product_text" collection


                        HybridSearchService.search
                              │
              ┌───────────────┼───────────────┐
              ▼                               ▼
        SearchService                  TextSearchService
      (image-only search)            (text-only search)
              │                               │
              ▼                               ▼
      search_image(...)                search_text(...)
              │                               │
              └───────────────┬───────────────┘
                               ▼
                   score fusion (hybrid mode only)
                               │
                               ▼
                    ranked HybridSearchResult list
```

`SearchService` and `TextSearchService` each depend only on
`BaseVectorStore`/their own embedding service — neither knows the other
exists. `HybridSearchService` is the only thing that composes both,
matching the codebase's established "depend on the seam, not the
concrete implementation" pattern (Phase 4's `BaseEmbeddingService`)
applied one layer up: a search *pipeline* composed from single-modality
building blocks, not one service that knows about every modality itself.

### Text Embeddings

`SentenceTransformerEmbeddingService` (`BAAI/bge-small-en-v1.5` by
default, 384-dimensional) mirrors `CLIPEmbeddingService` closely: lazy
model loading via `TextModelManager` (a near-exact copy of `ModelManager`'s
double-checked-locking "load once" pattern, reusing its `resolve_device`
function directly rather than duplicating it), batched inference off the
event loop, and normalized output — except Sentence Transformers
normalizes natively (`encode(normalize_embeddings=...)`) where CLIP
needed a manual L2-normalize step.

The text actually embedded for a product is built from its raw, only
lightly-trimmed name/brand/category/description — deliberately *not*
`_normalize_category`'s slugified form (`"men-tshirts"`). Slugifying
exists so category is a stable, exact-match filter value for Qdrant; a
sentence embedding model should see natural language ("Men Tshirts"),
not a URL-safe slug. The two normalizations serve different purposes and
are kept independent — see `ProductService._build_text_representation`.

### Collections

Two Qdrant collections, both cosine distance, both created lazily on
first use (see `QdrantVectorStore`'s own docstring): `product_images`
(512-dimensional, matching the default CLIP checkpoint) and
`product_text` (384-dimensional, matching the default Sentence
Transformers checkpoint). `BaseVectorStore`'s abstract methods
(`upsert`/`search`/`delete`/`exists`) all take an explicit
`VectorCollection` argument; `upsert_image`/`upsert_text`/`search_image`/
`search_text` are concrete convenience methods on the base class itself,
implemented once in terms of those five primitives — a concrete
`QdrantVectorStore` subclass never has to implement per-modality logic
twice, and the per-collection lazy-creation state (a dict of "ready"
flags, a dict of locks, both keyed by `VectorCollection`) means loading
one collection never blocks the other.

Every point's payload (in both collections) carries the same metadata:
`name`, `brand`, `category`, `price`, `description` — built once in
`ProductService` and reused for both the image and text upserts, since
it's the same product's metadata regardless of which collection is
storing which vector.

### Score Fusion

`HybridSearchService.search` dispatches on whatever's actually provided:

- **Image only** — runs `SearchService.search_by_image`, returns its
  scores/ranking untouched.
- **Text only** — runs `TextSearchService.search_by_text`, returns its
  scores/ranking untouched.
- **Both** — runs both searches (each asked for the same `top_k` the
  caller requested — see the trade-off this implies below), merges
  candidates by `product_id`, and computes

  ```
  final_score = IMAGE_WEIGHT * image_score + TEXT_WEIGHT * text_score
  ```

  A candidate present in only one side's results contributes `0.0` for
  the side it's missing from, gets tagged with only that side's modality
  in `matched_modalities`, then the fused, deduplicated list is sorted
  descending and truncated to `top_k`.

Single-modality scores are returned **unweighted** — multiplying every
score by `IMAGE_WEIGHT` when there's no text query to balance against
would just deflate every score by a constant factor for no benefit; the
weights only mean something as a *relative* balance between two
modalities actually being fused.

**Known limitation, by design:** because both sub-searches are asked for
the caller's own `top_k` (not an inflated candidate pool), a product that
ranks outside `top_k` on *both* individual searches can never surface
after fusion, even if it would have scored well combined. Over-fetching
to guard against this is a real hybrid-search refinement, but it's a
ranking-quality tuning knob this phase's own scope excludes
("Learning-to-rank"), so it's a documented trade-off rather than an
unstated gap.

### Supported Search Modes

`POST /api/v1/products/search` accepts an optional `file` (query image)
and an optional `query` (text) — at least one is required, or
`HybridSearchService` raises `ValidationException` (422) — plus optional
`brand`/`category`/`min_price`/`max_price` filters and `top_k`. The three
modes (image-only, text-only, hybrid) aren't separate endpoints; which
one runs is entirely determined by which fields the request actually
included. The response never includes a raw embedding vector — only
`product_id`, `score`, `matched_modalities`, and `metadata` — the same
"don't expose data a client can't act on" reasoning `EmbeddingInfo`
(Phase 4) and Phase 5's original search response already established.

### Configuration

New settings, all following the established grouped-settings pattern
(`app/core/settings.py`):

| Setting | Default | Purpose |
|---|---|---|
| `AI_MODELS__TEXT_MODEL_NAME` | `BAAI/bge-small-en-v1.5` | Sentence Transformers checkpoint |
| `AI_MODELS__TEXT_DEVICE` | `auto` | `"auto"`/`"cpu"`/`"cuda[:N]"`, same convention as `embedding_device` |
| `AI_MODELS__TEXT_BATCH_SIZE` | `32` | Forward-pass batch size for text embedding |
| `AI_MODELS__TEXT_NORMALIZE` | `true` | Passed to `encode(normalize_embeddings=...)` |
| `VECTOR_STORE__IMAGE_COLLECTION_NAME` | `product_images` | Renamed from Phase 5's `collection_name` |
| `VECTOR_STORE__IMAGE_VECTOR_SIZE` | `512` | Renamed from Phase 5's `vector_size` |
| `VECTOR_STORE__TEXT_COLLECTION_NAME` | `product_text` | New |
| `VECTOR_STORE__TEXT_VECTOR_SIZE` | `384` | New |
| `HYBRID_SEARCH__IMAGE_WEIGHT` | `0.7` | Score fusion weight |
| `HYBRID_SEARCH__TEXT_WEIGHT` | `0.3` | Score fusion weight |

Renaming `VECTOR_STORE__COLLECTION_NAME`/`VECTOR_STORE__VECTOR_SIZE`
(rather than leaving them and adding new text-specific names alongside)
was a deliberate breaking change: Phase 5's single collection *becomes*
the image collection this phase, and keeping the old names around
unused/renamed-in-spirit-only would be more confusing than a clean
rename, especially since nothing outside this codebase held a persisted
dependency on the old names yet (no production Qdrant deployment exists).

### Why does `BaseVectorStore`'s per-modality `VectorCollection` enum live
in `app/services/vectorstore/base.py`, while a separate, value-identical
`SearchModality` enum lives in `app/models/search.py`?

They mean different things that only happen to share two values today —
"which Qdrant collection an operation targets" vs. "which query type
matched a hybrid search result" — but the deeper reason they're not the
same type is that `app.services.vectorstore.base` already imports
`NearestNeighbor`/`ProductFilters` *from* `app.models.search`; having
`app.models.search` import `VectorCollection` back would be a circular
import. `SearchModality` accepts a small amount of duplication to avoid
a real layering problem.

### Why is `HybridSearchService` a separate class instead of teaching
`SearchService` about text?

This was an explicit design call, not just an implementation detail:
keeping `SearchService` (image-only) and the new `TextSearchService`
(text-only) each focused on one modality, with `HybridSearchService`
composing both plus its own fusion logic, keeps every piece independently
testable and means neither single-modality service has to carry logic
(weights, fusion, "what if the other modality wasn't queried") that has
nothing to do with its own actual job.

### Why does `ProductService` build the text representation and generate
the text embedding immediately after the image embedding, in the same
request, rather than as a separate step?

Same reasoning Phase 4 already established for folding image-embedding
generation into upload, and Phase 5 for upserting into the vector store
there too: `HybridSearchService`/`TextSearchService` can only ever find
products that already have a text-collection entry. Doing it later, as a
separate call, would be an easy-to-forget follow-up step and would leave
a window where a product exists but isn't fully searchable.

### Why does `ProductCreate` gain a new `brand` field in this phase,
when Phase 6's own milestones are about embeddings, not the upload schema?

The phase's own Milestone 2 requirements list "Brand" as one of the four
inputs building a product's text representation (alongside name,
category, description) — brand genuinely didn't exist as a capturable
field before this phase, so adding it (optional, following the exact
same pattern `description`/`category`/`price` already use) was necessary
to satisfy that requirement, not a scope-creeping addition.

## Phase 7 — Catalog Intelligence & Product Enrichment design decisions

This phase adds a deterministic (no LLMs, no OCR, no object detection)
enrichment step to the upload pipeline: every product now also gets a
structured `ProductAttributes` guess (brand/category/color/material/
gender/age_group/style/pattern/season/occasion), a list of generated
`CatalogTag`s, and a `quality_score`, all derived from the product's own
submitted text and its processed image. Six pieces landed, in dependency
order: the domain models, `TextAttributeExtractionService`,
`ImageAttributeExtractionService`, the `CatalogIntelligenceService`
orchestrator that merges both, upload-pipeline wiring, and finally test
hardening.

### Architecture

```
                     ProductService.process_upload
                              │
                    (after text embedding)
                              ▼
                  CatalogIntelligenceService.enrich
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
  TextAttributeExtractionService   ImageAttributeExtractionService
  (regex/keyword matching on       (Pillow pixel analysis on the
   name/brand/category/description) processed image: color/brightness/
              │                     orientation/resolution)
              ▼                               ▼
      list[AttributePrediction]        list[AttributePrediction]
      list[CatalogTag]                 list[CatalogTag]
              └───────────────┬───────────────┘
                              ▼
                    _merge_attributes / _merge_tags
                  (highest confidence wins; tags dedup,
                   agreeing sources upgrade to Source.HYBRID)
                              ▼
                    _compute_quality_score
                  (weighted completeness/confidence/consistency)
                              ▼
                    CatalogIntelligenceResult
          (stored on Product.catalog_intelligence; color/material/
           gender/season/style/tags added to vector store metadata)
```

Like `HybridSearchService` (Phase 6), `CatalogIntelligenceService` is a
thin orchestrator with no extraction logic of its own — each extraction
service is independently testable, and the orchestrator's only job is
merge/conflict-resolution/scoring.

### Text Intelligence

`TextAttributeExtractionService` is deliberately **not** `async def` —
unlike every other service in this codebase, it does zero I/O (pure
regex/dict-lookup over the product's own already-in-memory strings), so
wrapping it in `run_in_threadpool` or declaring it `async` would add
overhead for no benefit. This is a documented, reasoned exception to the
"every service method is async" convention established since Phase 3, not
an oversight.

Already-submitted structured fields (`brand`, `category`) are trusted at
confidence `1.0` rather than re-derived from text — a caller who typed
"Nike" as the brand shouldn't have that overridden by a lower-confidence
keyword match. Everything else (color, material, gender, style, pattern,
season, occasion, age_group) comes from word-boundary keyword matching
(`\bkeyword\b`, case-insensitive) against hand-curated lookup tables —
`_find_first_keyword` picks the earliest-occurring match for singular
attributes (only one value can win); `_find_all_keywords` returns every
match for tag generation (a product can genuinely have multiple relevant
tags). An unrecognized brand is never hallucinated — it's simply not
returned as a prediction, matching the "don't fill with a low-confidence
guess" philosophy carried into `CatalogIntelligenceService`'s own
threshold logic.

### Image Intelligence

`ImageAttributeExtractionService` runs against the *processed* image path
(`ImageMetadata.processed_path` — the same file `CLIPEmbeddingService`
embeds from, already standardized by Phase 3), never the raw upload.
`extract_attributes` only proposes `color` (the one image-derived signal
that maps onto an actual `ProductAttributes` field — analyzing a photo
can't reliably say "gender" or "material"); `generate_tags` additionally
tags orientation (`portrait`/`landscape`/`square`), brightness
(`dark`/`medium`/`bright`), and resolution (`low_resolution`), always
returning exactly four tags. Dominant color is computed from a 50×50
downsampled thumbnail (`Image.getcolors()`) for speed, then matched to
the nearest of eleven named colors by squared Euclidean distance in RGB
space — deliberately coarse (a shoe that's "crimson" reads as "Red"),
since the goal is a searchable/filterable label, not colorimetric
precision.

### Conflict Resolution & Quality Scoring

Both extraction services can propose a value for the same attribute (in
practice, only `color`). `CatalogIntelligenceService._merge_attributes`
groups predictions by attribute name and the **highest-confidence
candidate wins**; a winner below `ATTRIBUTE_CONFIDENCE_THRESHOLD` is
dropped entirely rather than filled with a low-confidence guess — the
phase's own worked example (text says "Red" at 0.95, image says "Orange"
at 0.61) resolves to `color: "Red"`. Tags follow similar logic but aren't
one-per-attribute: `_merge_tags` deduplicates by tag string, upgrades a
tag proposed by *both* extraction services to `Source.HYBRID`, sorts by
descending confidence, and caps at `MAX_GENERATED_TAGS`.

`quality_score` is a configurable weighted sum:

```
quality = QUALITY_COMPLETENESS_WEIGHT * completeness
        + QUALITY_CONFIDENCE_WEIGHT   * confidence
        + QUALITY_CONSISTENCY_WEIGHT  * consistency
```

- **completeness** — fraction of `ProductAttributes`' fields that got filled.
- **confidence** — mean confidence across every filled attribute.
- **consistency** — `1 - (conflicting attributes / attributes with any candidate)`.

The result is clamped to `[0, 1]` since the three weights aren't required
to sum to exactly `1.0` (an operator may reasonably want to tune only
one).

### Upload Integration

`ProductService.process_upload` calls `CatalogIntelligenceService.enrich`
right after text embedding generation, using the same **raw** submitted
`name`/`brand`/`category`/`description` that `_build_text_representation`
already uses (not `_normalize_category`'s slugified form) — a keyword
extractor should see "Men Tshirts", not "men-tshirts", for the same
reason a sentence embedding model should. The result is stored on the new
`Product.catalog_intelligence` field (always present — disabled via
settings still produces an empty `ProductAttributes`/no tags/`0.0`
quality score, rather than making the field itself optional) and its
`color`/`material`/`gender`/`season`/`style`/`tags` are added to the
vector store metadata dict. `brand`/`category` in that metadata
deliberately **stay** the pre-existing normalized/slugified values rather
than switching to catalog intelligence's own guesses — changing what
they mean would silently break `ProductFilters` equality-matching
(Phase 6) for anything already indexed; the five new fields have no
prior meaning to preserve, so they're populated directly from whatever
catalog intelligence resolved.

### Configuration

New settings, all under `CatalogIntelligenceSettings`
(`app/core/settings.py`), env prefix `CATALOG_INTELLIGENCE__`:

| Setting | Default | Purpose |
|---|---|---|
| `CATALOG_INTELLIGENCE__ENABLED` | `true` | Master switch; disabled yields an empty `CatalogIntelligenceResult` |
| `CATALOG_INTELLIGENCE__ENABLE_TEXT_ATTRIBUTES` | `true` | Toggle the text extraction pipeline independently |
| `CATALOG_INTELLIGENCE__ENABLE_IMAGE_ATTRIBUTES` | `true` | Toggle the image extraction pipeline independently |
| `CATALOG_INTELLIGENCE__ATTRIBUTE_CONFIDENCE_THRESHOLD` | `0.60` | Below this, a winning attribute/tag is dropped, not guessed |
| `CATALOG_INTELLIGENCE__MAX_GENERATED_TAGS` | `20` | Cap on tags per product after merging |
| `CATALOG_INTELLIGENCE__QUALITY_COMPLETENESS_WEIGHT` | `0.50` | Quality score weight |
| `CATALOG_INTELLIGENCE__QUALITY_CONFIDENCE_WEIGHT` | `0.30` | Quality score weight |
| `CATALOG_INTELLIGENCE__QUALITY_CONSISTENCY_WEIGHT` | `0.20` | Quality score weight |

### Explicitly out of scope this phase

No OCR, no LLMs/GPT calls, no YOLO/SAM/object detection, no duplicate
detection, no recommendation engine, no Redis, no background workers, no
new databases — every attribute/tag here comes from deterministic
regex/keyword matching or pixel-level image statistics, matching the
phase spec's own "Do NOT Implement" list. Duplicate detection and a
recommendation engine are explicitly future phases that will *consume*
this phase's attributes/tags, not something this phase builds itself.

### Why does `app/models/` hold these domain models instead of a new
`app/domain/` package (as the phase's own suggested layout names it)?

Same reasoning as every model added in earlier phases: `app/models/`
is this codebase's established location for internal domain models
(`Product`, `ImageMetadata`, `ImageEmbedding`, `TextEmbedding`, ...);
introducing a parallel `app/domain/` package for only this phase's models
would fragment where "the domain model" lives for no benefit, especially
since `Product` (in `app/models/product.py`) is precisely what
`CatalogIntelligenceResult` attaches to.

### Why does `Source` (TEXT/IMAGE/HYBRID) live in `catalog_tags.py`
rather than its own module?

Both `CatalogTag` and `AttributePrediction` need it, and `catalog_tags.py`
is where it's first needed — a dedicated `source.py` for one three-value
enum shared by two closely-related models would be more indirection than
the enum itself warrants.

## Phase 8 — Duplicate Detection Engine design decisions

This phase adds a duplicate-detection step that evaluates every uploaded
product against the existing catalog *before* it's indexed, combining
four independent similarity signals (image, text, metadata, attributes)
into one weighted confidence score. Five pieces landed, in dependency
order: the domain models, `SimilarityScorer`, `DuplicateDetectionService`,
upload-pipeline integration (`OFF`/`WARN`/`BLOCK` modes), and a dedicated
`POST /products/check-duplicate` endpoint for checking without uploading.

### Architecture

```
                     ProductService.process_upload
                              │
                (after catalog intelligence)
                              ▼
                  DuplicateDetectionService.detect
                              │
                              ▼
                  HybridSearchService.search
              (image + text query, top-K candidates)
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
     one HybridSearchResult            one HybridSearchResult
     per candidate, per candidate...
                              │
                              ▼
              SimilarityScorer.score (once per candidate)
          ┌──────────┬──────────┬──────────┬──────────┐
          ▼          ▼          ▼          ▼          │
       image       text     metadata   attribute       │
     (reused      (reused    (rapidfuzz  (rapidfuzz     │
      hybrid       hybrid    name/brand/  ProductAttributes
      search       search    category)    fields)        │
      score)       score)                                │
          └──────────┴──────────┴──────────┴─────────────┘
                              ▼
                      DuplicateResult
             (per-signal weight/contribution + overall)
                              ▼
              rank by overall_similarity, threshold the best
                              ▼
                      DuplicateDecision
              ┌───────────────┴───────────────┐
              ▼                               ▼
        OFF: skip                    WARN: store + attach
                                      BLOCK: reject (409), don't index
```

`SimilarityScorer` is deliberately the one place similarity is computed —
`DuplicateDetectionService` only ranks/thresholds what it returns. That
separation is the phase's own explicit design goal: the same scorer can
later be reused by a recommendation engine or a cross-encoder reranker
without dragging retrieval/decision logic along with it.

### Similarity Signals

Given the product being checked and one candidate already retrieved by
`HybridSearchService`, `SimilarityScorer.score` computes four signals and
bundles them into a `DuplicateResult`:

- **image** — the candidate's own `image_score` from hybrid retrieval
  (`HybridSearchResult` gained this field, alongside the existing fused
  `score`, specifically so this signal could be reused rather than
  re-embedding the image a second time just to get an unfused number).
- **text** — the same reuse, using `candidate.text_score`.
- **metadata** — `rapidfuzz.fuzz.token_sort_ratio`, case-insensitive and
  word-order-insensitive, averaged over whichever of name/brand/category
  is present on both sides. Tolerates typos ("Nike" vs "Nikee") and the
  candidate's slugified category metadata ("running-shoes" vs "Running
  Shoes") without either being scored as a real difference.
- **attribute** — the same fuzzy-ratio approach, field-by-field, over
  `ProductAttributes`' brand/category/color/material/style/gender against
  the candidate's metadata. A field missing on either side is excluded
  from the average rather than penalized — a product simply lacking a
  detected `material` isn't evidence of dissimilarity.

Each signal is weighted and summed:

```
overall_similarity = IMAGE_WEIGHT * image_score
                    + TEXT_WEIGHT * text_score
                    + METADATA_WEIGHT * metadata_score
                    + ATTRIBUTE_WEIGHT * attribute_score
```

clamped to `[0, 1]` (cosine similarity can stray slightly outside that
range). `DuplicateDetectionSettings` validates the four weights sum to
exactly `1.0` — they represent a complete split of "how much each signal
counts," so a misconfigured deployment fails fast at startup rather than
silently producing a confidence score that doesn't mean what it claims to.

### Decision Making

`DuplicateDetectionService.detect` retrieves `DUPLICATE_DETECTION__TOP_K`
candidates via `HybridSearchService`, scores each independently, ranks by
`overall_similarity`, and thresholds the best one against
`DUPLICATE_DETECTION__THRESHOLD`. The winner (if any) becomes
`matched_product`/`confidence`; every scored candidate is exposed via
`top_candidates`, highest similarity first, so a caller can inspect the
full picture rather than just the winner. No candidates at all (an empty
catalog, or a genuinely novel product) yields a `DuplicateDecision` with
`is_duplicate=False`, `confidence=0.0`, and an explanatory `reason` —
never an error.

### Upload Integration

`ProductService.process_upload` calls `DuplicateDetectionService.detect`
right after catalog intelligence enrichment (it needs the resolved
`ProductAttributes` for the attribute signal), using the raw submitted
name/brand/category/description — the same reasoning already established
for text embedding and catalog intelligence. Three modes
(`DuplicateDetectionMode`, configured via `DUPLICATE_DETECTION__MODE`):

- **`OFF`** — detection never runs; `Product.duplicate_decision` is still
  always populated (mirroring `catalog_intelligence`'s "always present"
  convention), just with a neutral "disabled" decision.
- **`WARN`** — detection runs, the product is stored/indexed regardless
  of the outcome, and the decision is attached to `UploadResponse` for
  the caller's own judgment.
- **`BLOCK`** — the exact same detection, but a flagged duplicate raises
  `ConflictException` (409) *before* normalization, `Product`
  construction, or the vector store upsert — a rejected upload never
  becomes searchable and never needs a compensating delete.

### Duplicate-Check Endpoint

`POST /products/check-duplicate` answers "would this be a duplicate?"
without ever storing or indexing anything — useful for a client that
wants to warn a user *before* they commit to uploading. `DuplicateCheckService`
composes `ImageProcessingService` (to get the processed image path
catalog intelligence needs), `CatalogIntelligenceService`, and
`DuplicateDetectionService` — the same three steps `ProductService` runs,
minus normalization/validation/persistence. Accepts optional `top_k`/
`threshold` form fields that override the configured defaults for that
one call only. The response never includes a raw embedding vector,
matching every other response schema in this codebase (`EmbeddingInfo`,
`ProductSearchResult`).

### Configuration

New settings, all under `DuplicateDetectionSettings`
(`app/core/settings.py`), env prefix `DUPLICATE_DETECTION__`:

| Setting | Default | Purpose |
|---|---|---|
| `DUPLICATE_DETECTION__MODE` | `warn` | `off`/`warn`/`block` |
| `DUPLICATE_DETECTION__THRESHOLD` | `0.90` | Minimum `overall_similarity` to count as a match |
| `DUPLICATE_DETECTION__TOP_K` | `10` | Candidates retrieved per check |
| `DUPLICATE_DETECTION__IMAGE_WEIGHT` | `0.35` | Confidence formula weight |
| `DUPLICATE_DETECTION__TEXT_WEIGHT` | `0.25` | Confidence formula weight |
| `DUPLICATE_DETECTION__METADATA_WEIGHT` | `0.20` | Confidence formula weight |
| `DUPLICATE_DETECTION__ATTRIBUTE_WEIGHT` | `0.20` | Confidence formula weight |

The four weights must sum to `1.0` (validated at settings-load time).

### Explicitly out of scope this phase

No cross-encoder reranking, no LLM verification, no human review
workflow, no background workers, no OCR, no recommendation engine, no
pricing intelligence, no Redis caching, no UI/frontend, no unrelated
database migrations — matching the phase spec's own "Do NOT Implement"
list. A recommendation engine and cross-encoder reranking are explicitly
future phases that will *reuse* `SimilarityScorer`, not something this
phase builds itself.

### Why does `HybridSearchResult` gain `image_score`/`text_score` fields
instead of `DuplicateDetectionService` re-running image/text search itself?

`HybridSearchService` already computes both per-modality scores
internally (`_FusionEntry.image_score`/`text_score`) before fusing them
into the single `score` `HybridSearchService` returns to search callers
— exposing them on `HybridSearchResult` reuses a number that's already
been computed rather than a `SimilarityScorer` needing to re-run
`SearchService`/`TextSearchService` (and pay the same embedding cost)
just to recover it. The two new fields are additive and default to
`0.0`, so `POST /products/search`'s existing response schema (which maps
`HybridSearchResult` field-by-field, not by unpacking the whole model) is
unaffected.

### Why does `ProductService` reprocess the image a second time during
duplicate detection, when it already processed it once for its own embedding?

`DuplicateDetectionService` delegates candidate retrieval entirely to
`HybridSearchService`, which (via `SearchService`) always re-standardizes
whatever image path it's given — that's how single-modality image search
already worked before this phase, and reusing it here (rather than
teaching `HybridSearchService` to accept a pre-computed embedding) keeps
duplicate detection from needing its own parallel image-processing path.
It's a real, accepted redundancy — the same trade-off `HybridSearchService`
already documents for over-fetching in score fusion — not an oversight.

## Phase 9 — Intelligent Recommendation Engine design decisions

This phase adds a recommendation engine that finds products related to
an *already-uploaded* one, identified only by ID — "similar products"
and "related products," with "complementary products" reserved for a
future phase. Five pieces landed, in dependency order: the domain models
(plus retrieval-by-ID infrastructure the whole phase depends on),
`RecommendationScorer`, `RecommendationEngineService` (retrieval, ranking,
diversity), the `GET /products/{id}/recommendations` endpoint, and
human-readable explanations.

### Architecture

```
                     GET /products/{id}/recommendations
                              │
                              ▼
              RecommendationEngineService.recommend
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
   BaseVectorStore.retrieve_text     HybridSearchService.search_by_product_id
   (target's own stored metadata)    (target's own stored vector(s) as the
              │                       query — no re-upload needed; self
              │                       already excluded from results)
              │                               │
              │                               ▼
              │                    top-K candidates (overfetched 3x
              │                     when diversity is enabled)
              │                               │
              └───────────────┬───────────────┘
                               ▼
                  RecommendationScorer.score (once per candidate)
          ┌──────────┬──────────┬──────────┬──────────┐
          ▼          ▼          ▼          ▼
     Similarity   Attribute      Tag       Quality
     (reused        Match       Match     (candidate's own
      hybrid      (color/       (Jaccard   stored quality_score)
      search      material/      overlap
      score)      gender/...)   of tags)
          └──────────┴──────────┴──────────┴──────────┘
                               ▼
                  RecommendationCandidate (final_score + reason)
                               ▼
                  sort by final_score, descending
                               ▼
                  diversity filter (round-robin by brand)
                               ▼
                  explanation generation (per final candidate)
                               ▼
                  RecommendationResult (top_k, ranked)
```

Like `DuplicateDetectionService` (Phase 8), `RecommendationEngineService`
is a thin orchestrator — `RecommendationScorer` owns every signal
computation, so the same scorer can be reused by a future cross-encoder
reranker (Phase 10) or pricing intelligence phase without dragging
retrieval/ranking/diversity logic along with it. That separation is this
phase's own explicitly stated design goal.

### Finding a Product by ID Alone

`GET /products/{id}/recommendations` takes only a product ID — no image
or text is resubmitted. Since this project still has no database (see
"No database write" notes throughout this README), the *only* place a
product's own data lives after upload is Qdrant itself. This phase adds
that lookup capability:

- `BaseVectorStore` gains `retrieve(collection, product_id) -> StoredPoint | None`
  (plus `retrieve_image`/`retrieve_text` convenience wrappers) — fetches
  a point's own stored vector *and* metadata directly by ID, distinct
  from `search` (which finds *other* points by similarity).
- `SearchService`/`TextSearchService` each gain `search_by_vector`
  (search using an already-computed vector, skipping embedding
  generation entirely) and `retrieve_by_id` (delegates to the vector
  store's own `retrieve_image`/`retrieve_text`).
- `HybridSearchService` gains `search_by_product_id`: fetches the
  target's own stored vector(s), searches with them via
  `search_by_vector`, fuses the same way `.search()` already does, and
  **excludes the target product itself** from the results (Milestone 3's
  "Remove Self" step) — internally requesting one extra candidate so
  self-exclusion never silently shrinks the caller's requested `top_k`.

`ProductService` also now writes `quality_score` (Phase 7's
`CatalogIntelligenceResult.quality_score`) into vector metadata — the
only way a candidate's quality score survives being retrieved purely by
ID rather than freshly computed.

### Scoring

`RecommendationScorer.score` computes four independent signals per
candidate and combines them:

```
final_score = SIMILARITY_WEIGHT   * similarity
            + ATTRIBUTE_WEIGHT    * attribute_match
            + TAG_WEIGHT          * tag_match
            + QUALITY_WEIGHT      * quality_score
```

- **similarity** — the candidate's own fused score from hybrid
  retrieval, reused as-is (the same "reuse what retrieval already
  computed" reasoning `SimilarityScorer`, Phase 8, established).
- **attribute match** — the fraction of `color`/`material`/`gender`/
  `season`/`style` that agree (case-insensitive) between target and
  candidate, counted only over fields present on both sides.
  `brand`/`category` are intentionally excluded from this continuous
  score — they get their own `shared_brand`/`shared_category` booleans
  instead, since they're usually the single most salient fact behind
  "why was this recommended."
- **tag match** — Jaccard overlap (`|shared| / |union|`) between the
  target's and candidate's tag sets.
- **quality** — the candidate's own stored `quality_score`.

Clamped to `[0, 1]`; `RecommendationSettings` validates the four weights
sum to exactly `1.0`, the same reasoning `DuplicateDetectionSettings`
(Phase 8) already established for its own four-weight formula. The
scorer never ranks or compares candidates against each other — that's
`RecommendationEngineService`'s job.

### Diversity

Without a diversity step, a catalog dominated by one brand would return
five near-identical results ("Nike, Nike, Nike, Nike, Nike"). `_diversify`
groups already-score-sorted candidates by their own `brand` metadata and
takes one candidate per brand per round — best-scoring first — round-
robining across brands until `top_k` is filled ("Nike, Adidas, Puma,
Asics, Nike, ..."). This only works if there's variety to diversify
*from*, so `RecommendationEngineService` overfetches
(`_DIVERSITY_OVERFETCH_MULTIPLIER = 3`) candidates beyond the requested
`top_k` whenever `RECOMMENDATION_DIVERSITY_ENABLED` is on; disabling it
requests exactly `top_k` and returns the raw score order.

### `SIMILAR` vs `RELATED`

Both recommendation types use the exact same scoring formula — the phase
spec describes one formula, not two per type. What differs is which
stored embedding(s) anchor candidate retrieval: `SIMILAR` uses the
target's full hybrid (image + text) profile; `RELATED` restricts
retrieval to `SearchModality.TEXT` alone, decoupling the result from
pure visual likeness (e.g. a shirt's "related" results lean on
category/attributes rather than which photo looks most alike).
`COMPLEMENTARY` ("goes well with," e.g. socks for shoes) is intentionally
left unimplemented — it needs a different kind of relationship entirely
(products that pair well together, not products that resemble each
other) that neither similarity signal here can express, matching the
phase spec's own "future-ready" framing.

### Explanations

`RecommendationScorer` only produces *structured* evidence
(`RecommendationReason` — matched attribute names, shared tags, two
booleans); `RecommendationEngineService` turns that into a plain-English
sentence once per final, diversified recommendation — phrasing is a
presentation concern, kept separate from *what* matched. Applicable
clauses (similar visual appearance, same category, same brand, shared
attributes, matching tags, high catalog quality) are joined in a fixed,
most-salient-first order; a candidate matching on nothing specific still
gets an honest fallback ("Related based on overall similarity.") rather
than an empty string.

### API

`GET /products/{id}/recommendations` accepts optional `top_k`/
`recommendation_type` query parameters and returns, per recommendation:
`product_id`, `score`, a nested `reason` (`matched_attributes`,
`matched_tags`, `shared_brand`, `shared_category`), and `explanation`.
Never includes a raw embedding vector or `product_id` isn't found returns
404 (`ResourceNotFoundException`) — the same "don't expose data a client
can't act on" and not-found conventions every earlier phase's endpoints
already establish.

### Configuration

New settings, all under `RecommendationSettings` (`app/core/settings.py`),
env prefix `RECOMMENDATION__`:

| Setting | Default | Purpose |
|---|---|---|
| `RECOMMENDATION__ENABLED` | `true` | Master switch |
| `RECOMMENDATION__TOP_K` | `10` | Default recommendations returned (a per-request `top_k` can override) |
| `RECOMMENDATION__DIVERSITY_ENABLED` | `true` | Round-robin-by-brand diversity filter |
| `RECOMMENDATION__SIMILARITY_WEIGHT` | `0.55` | Final-score formula weight |
| `RECOMMENDATION__ATTRIBUTE_WEIGHT` | `0.20` | Final-score formula weight |
| `RECOMMENDATION__TAG_WEIGHT` | `0.15` | Final-score formula weight |
| `RECOMMENDATION__QUALITY_WEIGHT` | `0.10` | Final-score formula weight |

The four weights must sum to `1.0` (validated at settings-load time).

### Explicitly out of scope this phase

No collaborative filtering, no user behavior analytics, no purchase
history, no matrix factorization, no deep learning recommenders, no
LLM-generated recommendations, no Redis caching, no background workers,
no cross-encoder reranking (reserved for Phase 10), no pricing
intelligence, no frontend/UI — matching the phase spec's own "Do NOT
Implement" list. Every signal here is deterministic (reused retrieval
scores, rapidfuzz-free exact/Jaccard matching, a fixed weighted formula).

### Why does `RecommendationEngineService` hold its own `BaseVectorStore`,
when `HybridSearchService` already composes one indirectly?

`HybridSearchService`'s own `SearchService`/`TextSearchService` are
private to it — reaching into `hybrid_search_service._search_service`
from outside would break encapsulation. Fetching the target product's
own metadata (needed for the attribute/tag/quality signals) is a direct
lookup this class needs independently of hybrid search's own retrieval,
so it composes `BaseVectorStore` directly, the same way `ProductService`
already does for its own reasons.

### Why does `RecommendationCandidate` (Milestone 1) double as both
`RecommendationScorer`'s return type and the unit `RecommendationEngineService`
ranks, unlike Phase 8's `DuplicateResult`/`DuplicateCandidate` split?

`similarity_score`/`quality_score`/`final_score`/`reason` already *is*
the full detail — there's no separate "list of raw per-signal weight/
contribution objects" this phase needs the way Phase 8's `SimilaritySignal`
list captured. Inventing a second, structurally-identical type purely to
mirror Phase 8's shape would be indirection without benefit.

## Phase 10 — Retrieval Evaluation Framework design decisions

This phase adds an offline benchmark harness that measures how well the
existing retrieval systems — hybrid search, recommendations, duplicate
detection — actually perform, using standard information-retrieval
metrics against a labeled dataset. It computes nothing new about
products; it only judges what the earlier phases' own services already
return.

### Architecture

```
             evaluation/dataset.json (or a caller-selected subset)
                              │
                              ▼
                     DatasetLoader.load()
                              │
                              ▼
                RetrievalEvaluator.evaluate(queries)
                              │
              per query, dispatch by task_type
     ┌────────────────────────┼────────────────────────┐
     ▼                        ▼                        ▼
RETRIEVAL              RECOMMENDATION               DUPLICATE
HybridSearchService     RecommendationEngineService  DuplicateDetectionService
.search(text=...)       .recommend(SIMILAR)          .detect_by_product_id(...)
     └────────────────────────┼────────────────────────┘
                              ▼
              ranked product IDs vs. query.ground_truth
                              │
                              ▼
        Precision@K / Recall@K / MRR / NDCG@K / Hit Rate@K / latency
                     (K = 1, 5, 10; per-query, then averaged per task_type)
                              │
                              ▼
                        BenchmarkReport
                    ┌─────────┴─────────┐
                    ▼                   ▼
         POST /evaluation/run    scripts/benchmark.py
         (JSON response)         (benchmark.json + benchmark.md on disk)
```

Like `RecommendationEngineService`/`DuplicateDetectionService` before it,
`RetrievalEvaluator` is deliberately thin: it computes metrics (pure
functions of "what came back" vs. "what should have"), never similarity
or ranking itself — every ranked list it judges comes from a system an
earlier phase already built and tested. No new retrieval logic exists
anywhere in this phase.

### Dataset Format

`evaluation/dataset.json` (a genuine top-level resource directory,
alongside `scripts/`/`docs/` — not part of the importable `app` package,
the same reasoning `app/core/paths.py` already documents for those) is a
flat JSON array, kept deliberately minimal per the phase spec's own
literal example:

```json
{"query": "red running shoes", "expected_products": ["<uuid>", ...]}
```

Every other field is optional per entry — a bare `{"query": ...,
"expected_products": [...]}` is a `RETRIEVAL` query by default;
`RECOMMENDATION`/`DUPLICATE` entries add `"task_type"` and `"product_id"`
instead of `"query"`. One flat file describes all three evaluation
tasks — no separate dataset file per task type. `DatasetLoader` validates
every entry through `EvaluationQuery` itself, naming the offending
index/ID in the raised `EvaluationException` rather than silently
skipping malformed data.

### Metrics

Five metrics, each computed at `K = 1, 5, 10`, binary relevance (a
product either is or isn't in `ground_truth.expected_products`):

- **Precision@K** — fraction of the top-K *actually returned* results
  that are relevant. Divides by how many results were actually returned,
  not by K itself, so a system with legitimately fewer than K candidates
  (a small catalog) isn't unfairly penalized for not padding its list.
- **Recall@K** — fraction of all relevant products found in the top-K.
- **Hit Rate@K** — `1.0` if any relevant product appears in the top-K,
  else `0.0`.
- **MRR** (Mean Reciprocal Rank) — `1 / rank` of the first relevant hit,
  averaged across queries.
- **NDCG@K** (Normalized Discounted Cumulative Gain) — rank-weighted
  relevance, normalized against the ideal ordering so the result always
  falls in `[0, 1]` regardless of how many relevant products exist.

All five are pure, stateless module-level functions, unit-tested against
hand-computed expected values independent of any live system. An empty
`expected_products` set yields `0.0` for every metric (a conservative
choice — treating "nothing was labeled relevant" as vacuously perfect
would make an unlabeled query look like a flawless one).

### Per-Query Failure Isolation

One query's failure — a stale `product_id` the dataset still references,
a system it evaluates raising — is caught and recorded on that query's
own `EvaluationQueryResult.error`, the same "don't let one bad entry sink
the batch" reasoning `DuplicateDetectionService`'s per-candidate handling
and `ProductService`'s per-item batch processing already established. A
failed query is excluded from its task type's aggregate averages (so a
few bad product IDs don't silently drag down an otherwise-healthy
system's reported quality) but still counted in `failure_count` and
`query_results`, so it's visible rather than hidden. `evaluate()` itself
only raises `EvaluationException` for failures outside any single
query — the default dataset failing to load, or aggregation itself
failing unexpectedly.

### Benchmark Execution

Two ways to run the same evaluation:

- `POST /evaluation/run` — thin router, no evaluation logic of its own:
  loads the dataset, narrows it to the request's `query_ids`/`limit`
  subset (a request-shaping concern that lives in the router, the same
  way `ProductFilters` narrows a search request before
  `HybridSearchService` ever sees it — not inside `RetrievalEvaluator`),
  calls `RetrievalEvaluator.evaluate`, and shapes the response. Never
  omitting a body at all runs the full configured dataset.
- `scripts/benchmark.py` — a standalone CLI (mirroring `scripts/`'s
  existing purpose; not part of `app`), writing both `benchmark.json`
  (the full `BenchmarkReport`) and a human-readable `benchmark.md`
  (throughput, a per-task-type metrics table, and a "## Failures"
  section) to `EVALUATION__BENCHMARK_OUTPUT` (`reports/` by default) —
  the reproducible, offline artifact the phase spec asks for.

Neither path logs embeddings or raw vectors, matching every earlier
phase's own logging conventions.

### Configuration

New settings, all under `EvaluationSettings` (`app/core/settings.py`),
env prefix `EVALUATION__`:

| Setting | Default | Purpose |
|---|---|---|
| `EVALUATION__ENABLED` | `true` | Master switch |
| `EVALUATION__TOP_K` | `10` | Default K passed to each evaluated system when a query doesn't set its own `top_k` |
| `EVALUATION__BENCHMARK_OUTPUT` | `reports/` | Where `scripts/benchmark.py` writes `benchmark.json`/`benchmark.md` |
| `EVALUATION__LATENCY_METRICS_ENABLED` | `true` | Whether per-query wall-clock latency is measured and reported |

### Explicitly out of scope this phase

No cross-encoder reranking, no LLM-judge scoring, no human evaluation, no
online A/B testing, no Redis, no Celery/background workers, no UI
dashboards, no model training — matching the phase spec's own "Do NOT
Implement" list. Every metric here is a deterministic function of a
labeled dataset and whatever the systems under test already return.

### Why does `EvaluationQuery` accept `image_path` when `RetrievalEvaluator` doesn't dispatch it yet?

The domain model is future-ready per the phase spec's own framing — the
same "accept the field now, implement the dispatch later" pattern
`RecommendationType.COMPLEMENTARY` (Phase 9) already established. A
`RETRIEVAL` query with only `image_path` and no `text` fails as its own
per-query error today (image-based dispatch isn't implemented), not a
crash — consistent with how every other unsupported or malformed entry
in the dataset is handled.

### Why does duplicate-detection evaluation need a new `DuplicateDetectionService.detect_by_product_id` method?

`EvaluationQuery` only carries a `product_id` for `DUPLICATE`/
`RECOMMENDATION` queries — but `DuplicateDetectionService.detect()`
(Phase 8) expects a freshly-uploaded image/text/attributes, not a
product ID alone. Rather than duplicate `SimilarityScorer`/decision logic
inside `RetrievalEvaluator` itself (explicitly disallowed by this phase's
"no duplicated retrieval logic" requirement), `DuplicateDetectionService`
gained `detect_by_product_id`: it reconstructs a `ProductAttributes` from
the target's own stored vector metadata (the same `retrieve_text`/
`retrieve_image` infrastructure Phase 9 built for recommendations) and
reuses the exact same `SimilarityScorer`/`_build_decision` path
`detect()` already uses.

## Phase 11 — Cross-Encoder Reranking design decisions

This phase adds an optional refinement stage that reorders an
already-retrieved candidate pool using a cross-encoder — a model that
scores a query and one candidate *together* rather than comparing two
independently-computed embeddings — before hybrid search, duplicate
detection, or recommendations return their final answer.

### Architecture

```
      HybridSearchService.search_by_(image|text|vector)
                     │
          Top N candidates (already ranked by
           embedding cosine similarity)
                     │
                     ▼  (only when reranking is enabled)
            overfetch to RERANKER__TOP_N
                     │
                     ▼
             RerankerService.rerank(query, candidates)
                     │
        ┌────────────┴────────────┐
        ▼                         ▼
  build one (query,        CrossEncoderService.score_pairs
   document) pair per       (ModelManagerCrossEncoder: lazy-
   candidate (from its       loaded, thread-safe, batched)
   own stored metadata)
        └────────────┬────────────┘
                      ▼
         sigmoid-normalize each raw score into [0, 1]
                      ▼
              sort, descending; truncate to top_k
                      ▼
              RerankResult (RerankedCandidate + RerankReason
                        per survivor)
                      │
        ┌─────────────┼─────────────┐
        ▼             ▼             ▼
 HybridSearchService  Recommendation   DuplicateDetection
 .search: replaces    EngineService:   Service: replaces
 .score               replaces .score  .text_score
```

`RerankerService` is deliberately thin, mirroring every other
orchestrator in this codebase (`RecommendationEngineService`,
`DuplicateDetectionService`): it does no retrieval of its own —
`candidates` must already come from `HybridSearchService` — and
`CrossEncoderService` owns the actual model inference, so
`RerankerService`'s only job is pooling, pairing, sorting, and
truncating.

### Cross-Encoder vs. Embedding Similarity

Every existing retrieval signal in this codebase (`HybridSearchResult.
score`, `image_score`, `text_score`) comes from comparing two
*independently* computed embeddings with cosine similarity — fast (a
candidate's vector is computed once, at upload time, and reused for
every future query) but limited: the model never sees the query and the
candidate together, so it can't reason about how they specifically
relate. A cross-encoder (`cross-encoder/ms-marco-MiniLM-L-6-v2`, a
small, CPU-friendly MS-MARCO-tuned checkpoint) feeds the query and one
candidate's text into the model jointly, letting it attend across both —
slower per pair (nothing can be precomputed and reused across queries)
but typically a materially more accurate relevance judgment. That
asymmetry is exactly why reranking is applied to a small, already-
retrieved top-N pool rather than the whole catalog: embedding search is
still what finds the candidates in the first place.

### Why Sigmoid-Normalize the Rerank Score?

A cross-encoder outputs an unbounded relevance logit — a confident match
can score well above `1.0`, an irrelevant pair well below `0.0` (verified
directly against the real model: a clearly relevant pair scored `~9.0`
in manual testing). Left as raw logits, every integration that
substitutes a rerank score into an existing `[0, 1]`-scored field would
either lose precision to clamping (many confidently-relevant candidates
collapsing to the same `1.0`) or need its own ad-hoc normalization.
`RerankerService._normalize` applies a sigmoid once, so
`RerankedCandidate.rerank_score` stays directly comparable to every
other score already in this codebase (`HybridSearchResult.score`,
`RecommendationCandidate.similarity_score`, `DuplicateResult.
overall_similarity`, ...) without each caller reinventing the transform.
`CrossEncoderService.score_pairs` itself still returns the *raw* score —
normalization is `RerankerService`'s concern, not the scoring service's.

### Integration: Which Field Gets Replaced, and Why

Reranking never replaces an existing scorer's math (`SimilarityScorer`/
`RecommendationScorer` are untouched) — it replaces one of that scorer's
*inputs*, chosen per integration based on what each scorer actually
reads:

- **`HybridSearchService.search`** — reranking *is* the final answer
  here (no downstream scorer), so the reranked candidates' `.score` is
  overwritten with the rerank score directly, and the list is truncated
  to `top_k`. Only applies when a text query is present (text-only or
  hybrid mode) — the cross-encoder scores *text* pairs, so an image-only
  search has nothing to build a query-document pair from and is
  returned unreranked, a documented limitation rather than a bug.
- **`RecommendationEngineService.recommend`** — `RecommendationScorer`
  reuses `candidate.score` as-is for its "similarity" signal, so
  substituting the rerank score there directly improves that signal
  before the existing weighted formula runs.
- **`DuplicateDetectionService.detect`/`detect_by_product_id`** —
  `SimilarityScorer` never reads `candidate.score` at all; it reads
  `candidate.image_score`/`text_score` independently. A cross-encoder's
  joint-attention relevance judgment is a strictly more accurate
  refinement of "how textually similar is this candidate" than the
  embedding cosine similarity `text_score` started as, so reranking
  substitutes into `text_score` instead, flowing into the existing
  `text_weight`-weighted formula with no scorer changes at all. Calling
  `HybridSearchService.search` with `reranking_enabled=False` explicitly
  avoids scoring the same candidates through the cross-encoder twice.

### Latency/Quality Trade-off

Reranking is applied to an overfetched pool capped at `RERANKER__TOP_N`
(50 by default) candidates, never the full retrieved set — a cross-
encoder forward pass is far more expensive per candidate than the
embedding cosine similarity that found them, so only the top of an
already-ranked list is ever re-scored, batched (`RERANKER__BATCH_SIZE`)
and pushed off the event loop the same way every embedding service in
this codebase already does. Each of the three integrations overfetches
*retrieval* itself up to `RERANKER__TOP_N` (rather than pre-truncating
to the caller's requested `top_k` before reranking runs) so reranking
has a real pool to reorder — the same overfetch reasoning
`RecommendationEngineService`'s own diversity filter (Phase 9) already
established.

### Why Reranking Defaults to Disabled

`RerankerSettings.enabled` defaults to `False` — the only feature flag
in this codebase that does. Every other configurable toggle
(`RECOMMENDATION__ENABLED`, `CATALOG_INTELLIGENCE__ENABLED`, `EVALUATION__ENABLED`,
...) gates deterministic, already-cheap computation; this one gates a
*real transformer model load and inference call* on every applicable
request. Defaulting it on would silently add that cost — and a
first-request model download requiring internet access — to a project
whose own `DatabaseSettings` docstring promises "runs with zero config
locally." An operator turns it on explicitly (`RERANKER__ENABLED=true`)
once the model is reachable and the added latency is acceptable.

### Configuration

New settings, all under `RerankerSettings` (`app/core/settings.py`), env
prefix `RERANKER__`:

| Setting | Default | Purpose |
|---|---|---|
| `RERANKER__ENABLED` | `false` | Master switch — see "Why Reranking Defaults to Disabled" |
| `RERANKER__MODEL_NAME` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | Hugging Face Hub cross-encoder checkpoint |
| `RERANKER__TOP_N` | `50` | How many top candidates get reranked per request |
| `RERANKER__BATCH_SIZE` | `16` | Query-document pairs per cross-encoder forward pass |
| `RERANKER__DEVICE` | `auto` | Same `"auto"`/`"cpu"`/`"cuda[:N]"` convention as `AIModelSettings`' own device fields |

Every one of `HybridSearchService.search`/`RecommendationEngineService.
recommend`/`DuplicateDetectionService.detect`/`detect_by_product_id`
also accepts a per-call `reranking_enabled` override, the same
"constructor default, per-call override" convention `top_k`/`threshold`
already use throughout this codebase — `RetrievalEvaluator.
compare_reranking` (below) is what actually exercises that override.

### Evaluation Integration

`RetrievalEvaluator.evaluate` gained a `reranking_enabled` parameter,
threaded through to whichever system a query dispatches to.
`RetrievalEvaluator.compare_reranking` runs the *same* dataset through
`evaluate` twice — once forced off, once forced on — and diffs the two
`BenchmarkReport`s into a `RerankComparisonReport` (`{task_type:
{metric_name: after - before}}`), producing exactly the phase spec's own
worked example (MRR: before `0.81`, after `0.90`) without an operator
hand-computing it from two separate runs. Two ways to run it, mirroring
Phase 10's own "script + API" pattern: `scripts/benchmark.py
--compare-reranking` writes `rerank_comparison.json`/`rerank_comparison.md`;
`POST /evaluation/compare-reranking` returns the same comparison over
the API, reusing `/evaluation/run`'s own `query_ids`/`limit` subset
filtering and response shaping.

### Explicitly out of scope this phase

No LLM reranking, no fine-tuning, no online/reinforcement learning, no
distributed inference, no GPU-specific optimizations, no background
workers, no Redis caching — matching the phase spec's own "Do NOT
Implement" list. Reranking is a deterministic function of the
pretrained cross-encoder checkpoint and whatever candidates retrieval
already found.

## Phase 12 — Asynchronous AI Processing Pipeline design decisions

This phase turns product upload from a single long-running synchronous
request into a queue-and-worker pipeline: the API acknowledges a request
in milliseconds, and a separate worker process runs the actual AI
pipeline (image processing, embeddings, catalog intelligence, duplicate
detection, vector indexing, recommendation cache warm-up) afterward —
"exactly how production ML systems work," per the phase's own framing.

### Architecture

```
        POST /products/upload
                │
      UploadService.save_upload
     (validate + store the file —
      still synchronous: a client
      needs this to fail fast, and
      the worker needs a file
      already on disk to process)
                │
                ▼
   pre-assign product_id + job_id
                │
                ▼
        QueueManager.enqueue
        (RedisQueue: pending list)
                │
                ▼
        202 Accepted (product_id,
         job_id, status_url)
                │
   ═══════════════════════════════  <- request/response ends here
                │
                ▼           (separate OS process: scripts/run_workers.py)
         WorkerManager
     (worker_concurrency many
      ProductWorker loops +
      1 crash-recovery loop)
                │
                ▼
      ProductWorker.process_one
                │
                ▼
   ProductService.process_upload   <- unchanged from Phase 2B (one
   (image processing, embeddings,     opaque call — see "Progress
    catalog intelligence, duplicate    Reporting" below)
    detection, vector indexing)
                │
                ▼
   RecommendationEngineService.recommend
   -> RecommendationCacheRepository.set
                │
                ▼
      Job marked COMPLETED
   (or: exception -> QueueManager.retry
    -> RETRYING with backoff, or FAILED
    -> dead-letter queue, after max_retries)
```

`GET /jobs/{job_id}` / `GET /products/{id}/status` (looked up by job ID
or product ID respectively) poll a job's `status`/`progress`/
`current_stage` at any point in this pipeline; `GET /jobs/dead-letter`
lists everything that permanently failed.

### Why Redis Only, No Database

The phase's own "Existing Architecture" list mentions PostgreSQL, but
this codebase has never had one — every phase through 11 explicitly
deferred persistence ("this pipeline processes but does not persist").
Building a real ORM/migrations layer just for job/product-status
tracking would be a substantial new subsystem, and none of this phase's
six milestones actually ask for one — they ask for `app/jobs/`,
`app/queue/`, `app/workers/`, all explicitly Redis-backed ("a
lightweight Redis-backed implementation is sufficient" — the phase
spec's own words, stated about the queue but equally true of job-status
storage, which is exactly the same kind of simple keyed record). `Job`
(the queued unit of work, persisted as JSON at `job:{job_id}` in Redis)
*is* the product's processing status — there's no separate database
row to keep in sync with it. `DatabaseSettings` stays exactly as
reserved/unused as it already was.

### Job Lifecycle

```
PENDING --(dequeue)--> RUNNING --(success)--> COMPLETED
                           │
                      (failure)
                           │
                           v
                      RETRYING --(backoff elapses, re-dequeued)--> RUNNING
                           │
                (retry_count > max_retries)
                           │
                           v
                        FAILED  (moved to the dead-letter queue)
```

`Job` (`app/jobs/base_job.py`) carries `job_id`/`product_id`/
`created_at`/`updated_at`/`retry_count` (Milestone 1's own required
fields) plus `progress`/`current_stage` (status-endpoint payload) and
`retry_history` (a `JobResult` per attempt — Milestone 5's own
requirement). `job_type` exists so a second job type could be added
later without a new record shape (`payload` is a generic `dict`) — only
`PRODUCT_PROCESSING` is implemented this phase.

### Queue Internals

`RedisQueue` (`app/queue/redis_queue.py`) keys everything by
`ASYNC_PIPELINE__QUEUE_NAME` (`"product_processing"` by default —
"configurable queues," the phase spec's own requirement, since a
different queue name is a fully independent queue):

| Redis key | Type | Purpose |
|---|---|---|
| `{queue_name}:pending` | LIST | Job IDs waiting to be dequeued (FIFO: `RPUSH`/`LPOP`) |
| `{queue_name}:processing` | HASH | Job ID -> dequeue timestamp; in-flight jobs, for crash recovery |
| `{queue_name}:delayed` | ZSET | Job ID -> ready-at timestamp; jobs waiting out a retry's backoff delay |
| `{queue_name}:dead_letter` | LIST | Job IDs that exhausted `max_retries` |
| `job:{job_id}` | STRING (JSON) | The actual `Job` record |
| `product:{product_id}:job_id` | STRING | Secondary index for `get_by_product_id` |

`dequeue()` promotes any due `delayed` entries back onto `pending`
*before* popping — no separate scheduler process is needed (Celery/RQ-
style delayed-task workers are explicitly out of scope this phase); a
plain sorted set plus a check on every dequeue is enough for a
lightweight implementation. `QueueManager` (`app/queue/queue_manager.py`)
is the thin, lazily-constructed singleton facade every caller
(`ProductWorker`, `app/api/products.py`, `app/api/jobs.py`) actually
depends on — never `RedisQueue` directly — so a second queue backend
(`ASYNC_PIPELINE__QUEUE_BACKEND` reserves the name) would only require a
new `BaseQueue` implementation.

### Retry Policy

`retry()` computes `delay = RETRY_DELAY_SECONDS * 2^(retry_count - 1)`
— attempt 1's failure waits one base delay, attempt 2's waits two,
attempt 3's waits four, and so on — and schedules the job into the
`delayed` sorted set at `now + delay`. If incrementing `retry_count`
would exceed `max_retries` (configured per-job from
`ASYNC_PIPELINE__MAX_RETRIES`, so an operator can change the default
without affecting jobs already queued under the old value), the job is
moved to the dead-letter queue instead (`status=FAILED`) — callers
(`ProductWorker`) only ever call `retry()`, never decide the dead-letter
branch themselves. Every retry and every dead-letter transition is
logged (`logger.warning`, with `job_id`/`product_id`/`attempt`/`delay`/
`error` — never the job's own `payload`, so a submitted product's
name/description/image metadata never lands in logs).

### Dead-Letter Queue

A job that exhausts its retries is never discarded — "never lose a
job," the phase's own requirement — it moves to
`{queue_name}:dead_letter` and stays there, `status=FAILED`, with its
last `error` and full `retry_history` intact. `GET /jobs/dead-letter`
(Milestone 5) lists every such job's current record, so an operator can
see *what* failed and *why* instead of it silently vanishing from view.
There's no automatic "revive from dead-letter" action this phase — only
inspection; re-driving a permanently-failed job is an operational
decision, not something this phase's spec asks the system to do on its
own.

### Idempotency

`product_id` is generated *before* a job is enqueued (`app/api/
products.py`'s `_queue_for_processing`) and never changes across
retries — `ProductService.process_upload` gained an optional
`product_id` parameter (backward compatible; omitted, it still generates
a fresh UUID4 exactly as before Phase 12) specifically so `ProductWorker`
can pass the job's own ID through on every attempt. Every write this
pipeline makes — the Qdrant image/text upserts — is keyed by that same
ID, and an upsert with the same ID is naturally idempotent: reprocessing
a retried job converges to the same final indexed state rather than
creating a duplicate point per attempt.

### Progress Reporting: Why Coarse, Not Per-Stage

`ProductWorker` reports `progress`/`current_stage` at a handful of
checkpoints (validating, processing, generating recommendations,
completed) around one opaque call to `ProductService.process_upload`,
not at every internal stage (image processing, embeddings, catalog
intelligence, duplicate detection, vector indexing individually). This
phase's own requirement is to extend the architecture "without modifying
existing business services" — `ProductService` already owns that exact
sequence, and reaching into its private sub-services from outside would
break the same encapsulation every other orchestrator's own docstring in
this codebase already establishes (`HybridSearchService`,
`RecommendationEngineService`, ...). The trade-off is honest: a client
polling status sees progress jump from ~40% to ~80%, not a live
per-stage percentage — a deliberate consequence of preserving that
boundary, not an oversight.

### Recommendation Cache

After `process_upload` succeeds, `ProductWorker` also calls
`RecommendationEngineService.recommend` once and stores the result in
`RecommendationCacheRepository` (Redis, TTL'd via
`RECOMMENDATION__CACHE_TTL_SECONDS`) — the diagram's own "Recommendation
Cache" pipeline stage. `GET /products/{id}/recommendations` checks this
cache first, but only for a plain default request
(`recommendation_type=SIMILAR`, no `top_k` override — the only shape
`ProductWorker` ever warms); a customized request always computes live,
so a cache hit can never return something that doesn't match what was
actually asked for. A cache miss (nothing warmed yet, or the entry
expired) falls back to live computation exactly as before this phase —
the cache is a warm-up optimization, not a strict consistency
guarantee.

### Monitoring

`GET /jobs/{job_id}` / `GET /products/{id}/status` / `GET
/jobs/dead-letter` are this phase's own monitoring surface — no metrics
exporter or dashboard is part of this phase's scope, but every stage
that matters is logged: job creation (`enqueue`), worker start/stop
(`WorkerManager`'s own start/stop-loop logs), every retry and dead-letter
transition (`RedisQueue.retry`), completion and failure
(`ProductWorker._complete`/`_fail`), and the crash-recovery loop's own
periodic check (`WorkerManager._run_recovery_loop`). None of these ever
log a job's `payload` or a raw embedding vector.

### Worker Lifecycle

`WorkerManager` (`app/workers/worker_manager.py`) runs entirely outside
the API process — `app/lifespan.py` stays untouched, matching the
architecture diagram's own separate "Worker Process" boxes, so the API
stays responsive regardless of worker load. `scripts/run_workers.py` is
the standalone entrypoint that actually runs it (`uv run python
scripts/run_workers.py`), spawning `WORKER_CONCURRENCY` many
`ProductWorker` loops plus one crash-recovery loop
(`QueueManager.requeue_stale_jobs`, checked every `JOB_TIMEOUT_SECONDS`
— a job still `processing` after that long almost certainly belongs to
a worker that crashed mid-job). Graceful shutdown
(SIGINT/SIGTERM): every loop only checks its stop flag *between* jobs,
never mid-job, so an in-flight job always finishes (or fails through to
a scheduled retry) before the process actually exits.

### Configuration

New settings, all under `AsyncPipelineSettings` (`app/core/settings.py`),
env prefix `ASYNC_PIPELINE__`:

| Setting | Default | Purpose |
|---|---|---|
| `ASYNC_PIPELINE__ENABLED` | `true` | Master switch — `false` falls back to the pre-Phase-12 fully-synchronous upload |
| `ASYNC_PIPELINE__QUEUE_BACKEND` | `redis` | Reserved for a future second backend; only `"redis"` exists today |
| `ASYNC_PIPELINE__REDIS_URL` | `redis://localhost:6379/0` | Where `RedisQueue`/`RecommendationCacheRepository` connect |
| `ASYNC_PIPELINE__QUEUE_NAME` | `product_processing` | Redis key prefix for the pending/processing/delayed/dead-letter structures |
| `ASYNC_PIPELINE__MAX_RETRIES` | `5` | Attempts before a job is dead-lettered |
| `ASYNC_PIPELINE__RETRY_DELAY_SECONDS` | `5` | Base exponential-backoff delay |
| `ASYNC_PIPELINE__WORKER_CONCURRENCY` | `4` | How many `ProductWorker` loops `WorkerManager` runs |
| `ASYNC_PIPELINE__JOB_TIMEOUT_SECONDS` | `300` | Crash-recovery threshold/check interval |

Unlike `RerankerSettings.enabled` (Phase 11, defaults `false` because it
bolts an optional refinement onto already-working endpoints),
`ASYNC_PIPELINE__ENABLED` defaults `true` — this phase's async pipeline
*is* the deliverable, not an optional add-on.

### Explicitly out of scope this phase

No Kubernetes, Kafka, RabbitMQ, Celery, Ray, Airflow, distributed
workers, auto-scaling, or GPU scheduling — matching the phase spec's own
"Do NOT Implement" list, and its own "a lightweight Redis-backed
implementation is sufficient." Every queue/worker primitive here is
plain `asyncio` and Redis data structures, nothing more.

## Phase 13 — Model Registry & AI Lifecycle Management design decisions

This phase adds a lightweight, in-memory `ModelRegistry` that tracks
which version of each AI model (image embedding, text embedding,
reranker) is currently active — centralizing model metadata and
lifecycle state so the services that actually load and run those models
(`ModelManager`, `TextModelManager`, `ModelManagerCrossEncoder`) no
longer hardcode a model name themselves.

### Architecture

```
        ModelRegistry
   (in-memory: which version
    is ACTIVE, per ModelType)
            │
   registry.get_active_model(ModelType.X)
            │
            ▼
  CLIPEmbeddingService / SentenceTransformerEmbeddingService /
  CrossEncoderService
   (resolve model_name from the registry;
    an explicit model_name still wins outright)
            │
            ▼
  ModelManager / TextModelManager / ModelManagerCrossEncoder
   (unchanged from earlier phases — still own
    actual loading/caching of the Hugging Face model)
            │
            ▼
      CLIP / BGE / Cross-Encoder
```

`ModelRegistry` never loads a model itself — see that service's own
docstring: "Pure metadata bookkeeping... this class never loads a
model." Its only job is answering "which model name should be loaded
for this type," the same separation of concerns `HybridSearchService`
keeps from the vector store it queries.

### Why `app/models/`, Not `app/domain/`

The phase spec's own milestone literally says `app/domain/` for
`ModelInfo`/`ModelType`/`ModelStatus`/`ModelVersion`, but this codebase
has never had a separate `domain/` package — every earlier phase's own
Pydantic domain models (`Product`, `DuplicateDecision`,
`RecommendationResult`, `EvaluationQuery`, ...) live in `app/models/`,
and Phase 11's spec asked for the same `app/domain/` wording for its own
domain models, resolved the same way then. Phase 13 reapplies that
precedent rather than introducing a second, parallel location for
domain models this late in the project.

### Seeding: Reusing Existing Settings, Not New Env Vars

The phase's configuration section asks for `IMAGE_MODEL`/`TEXT_MODEL`/
`RERANK_MODEL` env vars that the registry "validates... on startup," but
this codebase already has a single source of truth for exactly those
three values: `AIModelSettings.clip_model_name`/`.text_model_name` and
`RerankerSettings.model_name` — the same settings
`CLIPEmbeddingService`/`SentenceTransformerEmbeddingService`/
`CrossEncoderService` have always read directly. Introducing a second,
disagreeing set of flat env vars for the same three model names would
only invite them to drift out of sync with each other. `ModelRegistry`
seeds one `"1.0.0"`, `ACTIVE` entry per `ModelType` from those existing
settings at construction — "validates these on startup" is satisfied by
raising `ModelRegistryException` immediately if any configured name is
blank, rather than deferring that failure to whenever a model is first
loaded.

### Lifecycle: Register, Activate, Deactivate

`ModelRegistry` keeps, per `ModelType`, a `{version: ModelInfo}` map.
`register()` rejects a duplicate `(type, version)` pair
(`ConflictException`, 409); if the newly-registered version's own
`status` is `ACTIVE`, every other version of that type is demoted to
`INACTIVE` first — **at most one `ACTIVE` version exists per type at any
time**. `activate(type, version)`/`deactivate(type, version)` move an
already-registered version between those states the same way, and both
raise `ResourceNotFoundException` (404) for a version that was never
registered. `ModelStatus` also has `DEPRECATED`/`EXPERIMENTAL` for a
version that's neither the current default nor fully retired — a
candidate replacement model can be registered as `EXPERIMENTAL` and
evaluated (see below) before ever being promoted to `ACTIVE`.

### Registry Integration

`CLIPEmbeddingService`/`SentenceTransformerEmbeddingService`/
`CrossEncoderService` each gained an optional `model_registry:
ModelRegistry | None` constructor parameter. An explicit `model_name`
still wins outright (unit tests that pin a specific fake model
checkpoint are unaffected); when `model_name` is omitted, the service
now resolves it through
`registry.get_active_model(ModelType.X).model_name` instead of reading
`settings.ai_models.*`/`settings.reranker.model_name` directly. Since
the registry's own default seeding reads those exact same settings,
this is a behavior-preserving refactor: every existing caller that
relied on the old settings-driven default gets back the identical model
name, just routed through the registry now.

### Model Health & Metadata API

`GET /models` / `GET /models/{type}` / `GET /models/{type}/active`
(`app/api/models.py`) expose the registry's bookkeeping read-only:
model name, version, status, dimension, provider, `created_at`. No
model is ever loaded to answer any of these — "No runtime inference.
Metadata only," per the phase's own requirement — each route is a thin
adapter over `ModelRegistry.list_models`/`get_active_model`.

### Evaluation Integration: Model Provenance

`BenchmarkReport` (Phase 10) gained a `models` field: a snapshot of
whichever model was `ACTIVE`, per `ModelType`, at the moment
`RetrievalEvaluator.evaluate` ran. This is the phase's own "Model ->
Metrics -> Timestamp -> Version" record — a report now carries enough to
say "CLIP ViT-B/32 -> Recall@10 -> 0.91" without a separate lookup, and
a future model swap (registering and activating a SigLIP/OpenCLIP
version instead) is comparable against past runs purely by diffing two
reports' `models`/`overall_metrics` — `RetrievalEvaluator`'s own
dispatch and metric-computation logic never needs to change to support
that comparison. `POST /evaluation/run`'s response and
`scripts/benchmark.py`'s Markdown report both surface this same
snapshot.

### Configuration

No new environment variables this phase. `ModelRegistry` seeds itself
from settings that already existed before this phase
(`AIModelSettings.clip_model_name`/`.text_model_name`,
`RerankerSettings.model_name`) — see "Seeding" above for why no new
`IMAGE_MODEL`/`TEXT_MODEL`/`RERANK_MODEL` variables were added.

### Explicitly out of scope this phase

No MLflow, Hugging Face Hub uploads, model training/fine-tuning,
distributed model serving, GPU scheduling, automatic model download, or
A/B traffic splitting — matching the phase spec's own "Do NOT
Implement" list. `ModelRegistry` stays exactly what its own docstring
says: metadata and lifecycle bookkeeping, nothing more.

## Phase 14 — AI Observability & Monitoring design decisions

This phase adds a Prometheus-compatible metrics and health-reporting
layer over everything built so far — API requests, AI inference,
background workers, the Redis queue, and model/dependency health — while
keeping that observability layer independent of the business logic it
watches.

### Architecture

```
                     Prometheus
                          ▲  (scrapes GET /metrics)
                          │
      ┌───────────────────┼───────────────────┐
      │                   │                   │
   FastAPI            Worker Pool          AI Models
 (http_request_*)   (worker_jobs_*)   (embedding/rerank/
      │                   │            model_load metrics)
      └───────────────────┼───────────────────┘
                          ▼
                   MetricsRegistry
              (one process-wide set of
               Prometheus collectors)
                          │
                          ▼
              GET /metrics   +   GET /system/health,
                                  GET /system/stats
```

### MetricsRegistry: One Registry, Idempotent Collectors

`MetricsRegistry` (`app/metrics/metrics_registry.py`) owns every
Prometheus collector this codebase records into, and is bare-constructed
the same way `ModelRegistry`/`HybridSearchService` are — every
instrumented service takes an optional `metrics_registry` parameter,
defaulting to `MetricsRegistry()`. Because that means the class can be
constructed many times per process (every `create_app()` in the test
suite, every bare-constructed service), the collector factories in
`app/metrics/base_metrics.py` are **idempotent**: the first construction
registers a real `Counter`/`Gauge`/`Histogram` into `prometheus_client`'s
process-wide default registry (the one `GET /metrics` exposes); every
later one looks the collector up by name and reuses it, instead of
raising `ValueError: Duplicated timeseries`. Metric names live as
constants in `app/metrics/metric_names.py`, and `METRICS__NAMESPACE`
(default `product_intelligence`) prefixes all of them —
`product_upload_seconds` is exposed as
`product_intelligence_product_upload_seconds`.

### The Master Switch

Every `record_*`/`observe_*` method checks `METRICS__ENABLED` once and
no-ops if it's off — a single flag, checked in one place, rather than
each of the dozen-plus instrumented call sites re-reading settings. So
turning metrics off makes every instrumented service behave exactly as
it did before this phase, with zero recording overhead.

### Queue Gauges Are Polled, Not Pushed

`queue_depth`, `worker_jobs_running`, and `worker_dead_letter_size`
reflect *current* Redis state. Rather than incrementing/decrementing a
counter from inside `RedisQueue`/`QueueManager` — which would couple the
observability layer to the queue's own business logic and drift out of
sync after any crash/restart — each of these three gauges is wired via
`prometheus_client`'s `set_function()` to re-read the actual Redis
list/hash length *fresh on every scrape*, through a small independent
synchronous Redis connection that only reads `settings.async_pipeline`'s
already-public `redis_url`/`queue_name`. That connection uses a short
socket timeout so a `/metrics` scrape fast-fails (reporting `0.0`) when
Redis is down — a scrape must never hang or 500 just because a dependency
is unreachable. This is the same "never raises" contract
`QdrantVectorStore.health()` already establishes for itself.

### What Gets Measured Where

| Layer | Metric | Where it's recorded |
|---|---|---|
| API | `http_request_*` (count, latency, in-progress) | `prometheus-fastapi-instrumentator` middleware |
| Upload | `product_upload_seconds` | `MetricsRegistry.observe_product_upload` |
| Image/text embeddings | `embedding_latency_seconds`, `embedding_inference_total` (per model, per outcome) | `CLIPEmbeddingService`/`SentenceTransformerEmbeddingService` |
| Model loading | `model_load_seconds` (per model type, first load only) | the three `*ModelManager`s |
| Reranking | `rerank_latency_seconds`, `rerank_inference_total` | `RerankerService` |
| Recommendations | `recommendation_requests_total` | `RecommendationEngineService` |
| Duplicate detection | `duplicate_detection_total`, `duplicate_similarity_score` | `DuplicateDetectionService` |
| Workers | `worker_jobs_total` (success/failure), `worker_job_duration_seconds` | `ProductWorker` |
| Queue | `queue_depth`, `worker_jobs_running`, `worker_dead_letter_size` | `MetricsRegistry` (polled) |

Cross-encoder inference is measured once, at the `RerankerService` level
(where a rerank pass *is* one cross-encoder inference call), rather than
also inside `CrossEncoderService.score_pairs` — measuring both would
double-count the same work.

### GET /metrics

`_register_metrics` (`app/application.py`) wires
`prometheus-fastapi-instrumentator` into the app behind
`METRICS__PROMETHEUS_ENABLED`: it adds the standard `http_request_*`
series and exposes `GET /metrics`, which serves those alongside every
custom collector in the default registry. `get_metrics_registry()` is
called at startup so all custom metrics appear even on a freshly-started
idle process (at their zero values), rather than materializing only once
some request has lazily constructed the service that owns them. The
instrumentator's middleware sits outermost of the whole stack (it times
the entire request), and `/metrics` is kept out of the OpenAPI schema —
it's an operational endpoint, not part of the business API contract, the
same treatment the unversioned health probes get.

### Health Dashboard

`GET /system/health` and `GET /system/stats` (`app/api/system.py`, gated
on `METRICS__HEALTH_ENDPOINTS_ENABLED`) are backed by
`SystemHealthService` — read-only and failure-tolerant: it pings Redis,
asks the vector store whether it's reachable, reads current queue
lengths, and counts active models, degrading any failed check to
`"unhealthy"`/`0` rather than raising. Both routes always return `200`; a
degraded dependency is reported in the *body* (`"redis": "unhealthy"`),
not as an HTTP error, so a monitoring scrape of the dashboard itself
never fails because a dependency is down. These are distinct from the
unversioned `/health`/`/ready` liveness/readiness probes (Phase 1): those
answer "is this process alive / able to serve," while these expose a
richer operational view of the whole platform's dependencies.

`workers` in the health payload is the configured `WORKER_CONCURRENCY`,
**not** a live count of running worker processes — the API and the worker
pool are separate processes (`scripts/run_workers.py`), and the API has
no direct handle on how many workers are actually alive. A true liveness
count would need workers to heartbeat into Redis, which is beyond this
phase's scope; the field is documented as the configured target rather
than silently implying more than it knows.

### Grafana Dashboards & Alerting Ideas

No Grafana dashboards or alert rules are shipped in this repo (they live
in a monitoring deployment, not application code), but the metrics above
are named and labeled to make the obvious ones straightforward to build:

- **Throughput/latency panels**: `rate(http_request_total[5m])`,
  histogram quantiles over `product_upload_seconds`,
  `embedding_latency_seconds`, `rerank_latency_seconds`.
- **Queue health**: `queue_depth` and `worker_dead_letter_size` over
  time; a steadily-rising `queue_depth` means workers aren't keeping up.
- **Error rate**: `worker_jobs_total{status="failure"}` vs.
  `{status="success"}`; `embedding_inference_total{status="failure"}`.
- **Alerting ideas**: page on `worker_dead_letter_size > 0` (jobs are
  being permanently lost), on `queue_depth` growing monotonically for N
  minutes (worker starvation), on a high `http_request` 5xx rate, or on
  `product_intelligence_up`-style scrape failures (Prometheus's own
  `up == 0` for this target — Redis/Qdrant down shows up as `unhealthy`
  in `/system/health` but the process still scrapes).

### Configuration

New settings, all under `MetricsSettings` (`app/core/settings.py`), env
prefix `METRICS__`:

| Setting | Default | Purpose |
|---|---|---|
| `METRICS__ENABLED` | `true` | Master switch for recording any metric at all |
| `METRICS__PROMETHEUS_ENABLED` | `true` | Whether `GET /metrics` is exposed (independent of recording) |
| `METRICS__HEALTH_ENDPOINTS_ENABLED` | `true` | Whether `GET /system/health` and `/system/stats` are registered |
| `METRICS__NAMESPACE` | `product_intelligence` | Prefix prepended to every custom metric name |

### Explicitly out of scope this phase

No Jaeger, Zipkin, Datadog, New Relic, Kubernetes monitoring,
OpenTelemetry collectors, or CloudWatch — matching the phase spec's own
"Do NOT Implement" list. The implementation stays focused on
Prometheus-compatible metrics and health reporting, nothing more.

## Phase 15 — Cross-Encoder Re-ranking & Intelligent Duplicate Verification design decisions

This phase upgrades duplicate detection from embedding-only retrieval to
a production-grade pipeline: after vector retrieval, a cross-encoder
reranks the candidates, then explicit business rules validate the best
match, producing an explainable duplicate confidence — exactly how many
real search/ranking systems work.

### Built On, Not Instead Of, Phase 11

Cross-encoder reranking already existed in this codebase (Phase 11:
`BaseReranker`/`RerankerService`/`CrossEncoderService`/
`ModelManagerCrossEncoder`, wired through the model registry in Phase 13
and metered in Phase 14). Phase 15's spec described a "current pipeline"
with no reranking and asked for a fresh `app/services/reranking/` package
— but re-creating those components would have duplicated working, tested
code and violated the phase's own "never rewrite completed phases /
continue existing architecture" rules. So this phase **composes** the
existing reranking infrastructure and adds only what was genuinely new:
warm-up inference, an explainable business-rules layer, a verification
orchestrator, the richer API response, and two new metrics.

### Architecture

```
                     Upload
                        │
                 Image/Text
                        │
                  Embeddings (CLIP / BGE)
                        │
                     Qdrant  (top-K retrieval, reranking off)
                        │
              Cross-Encoder Reranker  (RerankerService, Phase 11)
                        │
              Business Validation  (BusinessRulesEvaluator: brand,
                        │            category, price, title, attributes)
              Duplicate Confidence  (weighted blend + hard-gate veto)
                        │
                 DuplicateVerification  ->  check-duplicate response
```

### Sequence (POST /products/check-duplicate, verification enabled)

```
Client ─► check_duplicate (router)
             │
             ▼
        UploadService.save_upload            (validate + store the image)
             │
             ▼
        DuplicateCheckService.check
             │  image processing + catalog intelligence (for attributes)
             ▼
        DuplicateVerificationService.verify
             │  1. HybridSearchService.search (reranking_enabled=False)
             │  2. RerankerService.rerank      → cross_encoder_score per candidate
             │  3. BusinessRulesEvaluator.evaluate(best candidate)
             │  4. confidence = w_ce·CE + w_br·business ; veto overrides
             ▼
        DuplicateVerification ──► DuplicateCheckResponse
        (duplicate, confidence, cross_encoder_score,
         retrieval_similarity, reasons[…])
```

### Why a Separate Verification Service

`DuplicateVerificationService` is new and distinct from Phase 8's
`DuplicateDetectionService` (which is left **unchanged** and still powers
upload-time WARN/BLOCK). The two have genuinely different output
contracts: detection produces a single *weighted* `DuplicateDecision`;
verification produces an *explainable* `DuplicateVerification` that
separates the cross-encoder signal from the raw retrieval signal and
lists human-readable reasons. Verification retrieves with reranking
*off* and runs its own explicit rerank pass, so the same candidates are
never scored by the cross-encoder twice — the exact reasoning
`DuplicateDetectionService` already documents for its own rerank step.

### Business Rules & the Hard-Gate Veto

`BusinessRulesEvaluator` is a pure, stateless component (no retrieval, no
model inference — like `SimilarityScorer`) that compares the checked
product against the best candidate on five rules: **brand** (exact,
normalized), **category** (fuzzy, `token_sort_ratio` ≥ 0.90, since a
stored slug is compared against a natural-language submission),
**price** (within `MAX_PRICE_DIFFERENCE_RATIO`), **title** (fuzzy ≥
`TITLE_SIMILARITY_THRESHOLD`), and **attribute overlap** (color/material/
gender/style). It returns a normalized `[0, 1]` score (fraction of
*applicable* rules satisfied — rules with data missing on either side are
skipped, not counted against), a list of `VerificationReason`s, and a
`veto` flag.

The final decision blends the two signals —
`confidence = CROSS_ENCODER_WEIGHT · cross_encoder_score +
BUSINESS_RULES_WEIGHT · business_score` — but `is_duplicate` also
requires the cross-encoder score to clear `CROSS_ENCODER_THRESHOLD`
**and** no configured hard gate to be violated. `REQUIRE_SAME_BRAND` /
`REQUIRE_SAME_CATEGORY` are those hard gates: when set, a brand/category
mismatch **vetoes** the duplicate verdict outright, no matter how
confident the cross-encoder is — the phase's own "`cross_encoder > 0.95`
AND brand same AND category same" example made absolute.

### Warm-Up Inference

`ModelManagerCrossEncoder` gained an optional warm-up
(`RERANKER__WARMUP_ENABLED`): immediately after the model is first loaded
(inside the load lock, so exactly once per model), it runs one throwaway
`predict` so the *first real* rerank request doesn't pay the transformer
cold-start cost (lazy CUDA-kernel compilation / graph construction).
Warm-up is non-fatal — a failure is logged and swallowed, leaving the
successfully-loaded model cached — and off by default, since forcing an
inference at load time on a CPU-only dev box is pure wasted latency
there; a GPU deployment that cares about first-request tail latency turns
it on.

### API: Backward Compatible

`DuplicateCheckService.check` now returns a unified `DuplicateVerification`
regardless of backend: when `DUPLICATE_VERIFICATION__ENABLED` is off (the
default) it delegates to the weighted `DuplicateDetectionService` and
adapts the decision into that shape with `cross_encoder_score`/
`retrieval_similarity` left `None`; when on, it runs the verification
pipeline. The `DuplicateCheckResponse` gains `cross_encoder_score`,
`retrieval_similarity`, and a human-readable `reasons` list, plus an
optional `price` form field feeding the price rule — but **every
pre-Phase-15 field keeps its exact meaning**, so existing clients are
unaffected (the new fields are simply `null`/empty when verification is
off).

### Metrics (Phase 14 integration)

`DuplicateVerificationService` records two new Prometheus metrics through
the existing `MetricsRegistry` (rerank latency/failures were already
tracked in Phase 14 via `RerankerService`):

- `duplicate_verification_confidence` (histogram) — the cross-encoder
  confidence distribution of the best candidate per check.
- `duplicate_verification_decisions_total{decision="duplicate"|"not_duplicate"}`
  (counter) — the duplicate-decision distribution.

Grafana/alerting ideas: watch the confidence histogram's quantiles drift
(a model swap or catalog shift), and alert if the `duplicate` fraction of
decisions spikes (a mis-tuned threshold flagging everything).

### Configuration

New settings under `DuplicateVerificationSettings` (env prefix
`DUPLICATE_VERIFICATION__`) plus one addition to `RerankerSettings`:

| Setting | Default | Purpose |
|---|---|---|
| `DUPLICATE_VERIFICATION__ENABLED` | `false` | Master switch — off keeps the weighted-similarity endpoint behavior |
| `DUPLICATE_VERIFICATION__CROSS_ENCODER_THRESHOLD` | `0.95` | Minimum cross-encoder score to be eligible as a duplicate |
| `DUPLICATE_VERIFICATION__REQUIRE_SAME_BRAND` | `false` | Hard gate: a brand mismatch vetoes the verdict |
| `DUPLICATE_VERIFICATION__REQUIRE_SAME_CATEGORY` | `false` | Hard gate: a category mismatch vetoes the verdict |
| `DUPLICATE_VERIFICATION__MAX_PRICE_DIFFERENCE_RATIO` | `0.25` | Price tolerance for the "close price" signal |
| `DUPLICATE_VERIFICATION__CROSS_ENCODER_WEIGHT` | `0.7` | Confidence blend weight (with business weight, sums to 1.0) |
| `DUPLICATE_VERIFICATION__BUSINESS_RULES_WEIGHT` | `0.3` | Confidence blend weight |
| `DUPLICATE_VERIFICATION__TITLE_SIMILARITY_THRESHOLD` | `0.85` | Fuzzy name-overlap ratio for the "title similarity" signal |
| `RERANKER__WARMUP_ENABLED` | `false` | Run one warm-up inference after the cross-encoder first loads |

Like `RERANKER__ENABLED`, verification defaults **off** because turning
it on runs a real cross-encoder model on every check — defaulting it on
would break this project's zero-config-runs-locally promise the first
time the endpoint is hit without the model downloaded.

### Benchmark: Before / After Reranking

Reranking's retrieval-quality impact is measured by the Phase 11
evaluation framework, not re-implemented here:
`POST /api/v1/evaluation/compare-reranking` runs the configured dataset
once with reranking off and once on, returning both metric sets plus the
per-metric deltas (e.g. `MRR: before 0.81, after 0.90`); the same numbers
render in `scripts/benchmark.py`'s Markdown report. Phase 13's
`BenchmarkReport.models` records which model produced each run, so a
future reranker swap stays comparable.

### Explicitly out of scope this phase

No new reranking package duplicating Phase 11, no rewrite of
`DuplicateDetectionService`, no placeholder/TODO code. The verification
pipeline reuses the existing reranker, model registry, and metrics
infrastructure, and adds only the business-rules and verification layers
on top.

## Phase 16 — Explainable AI & Decision Intelligence design decisions

This phase adds a centralized explanation layer: every major AI decision
(hybrid search, cross-encoder reranking, duplicate verification,
recommendations) can be turned into a human-readable, structured
`ExplanationTrace`, and three trace endpoints expose those explanations
for an already-indexed product.

### The Explanation Layer Reads Decisions, Never Makes Them

The single hard rule of this phase — "explanation generation must not
affect inference results" — is enforced structurally: explainers are
pure and read-only. Each takes a decision object a subsystem already
produced (`HybridSearchResult`, `RerankedCandidate`,
`DuplicateVerification`, `RecommendationCandidate`) and maps it into an
`ExplanationTrace`, never mutating it and never re-running inference. The
trace endpoints run the *same* by-product-id inference the platform would
run anyway (`RecommendationEngineService.recommend`,
`DuplicateDetectionService.detect_by_product_id`) and hand the results to
the explainer — explaining a decision is indistinguishable, to the
inference code, from not explaining it.

### Built On Existing Reason Types

The codebase already produced phase-specific reason/signal types
(`SimilaritySignal`, `RecommendationReason`, `RerankReason`,
`VerificationReason`). This phase does **not** rewrite them — it adds a
general domain (`DecisionReason`, `DecisionWeight`, `ConfidenceBreakdown`,
`ExplanationTrace`) that the explainers *map those existing outputs into*.
`DecisionWeight` is the general-purpose successor to `SimilaritySignal`
(its `value` isn't clamped to `[0, 1]`, so a cross-encoder logit can be
surfaced faithfully); `DecisionReason` generalizes the various reason
types behind one `code`+`description`+optional-`weight` shape.

### Architecture

```
   HybridSearchResult ─┐
   RerankedCandidate  ─┤
   DuplicateVerification ─┼─►  Explainers ──►  ExplanationTrace
   RecommendationCandidate ┘   (pure, read-only)   (summary + reasons +
                                    │               ConfidenceBreakdown)
                                    ▼
                            ExplanationService  ──►  trace endpoints
                            (facade + metrics)
```

`BaseExplainer[T]` is a generic interface (PEP 695 syntax) so each
concrete explainer is fully typed against exactly the decision it
explains; `ExplanationService` composes all four behind `explain_*`
methods and is the single seam the routes depend on. `ExplanationBuilder`
owns the pure presentation work — weight math (`contribution = value ·
weight`) and Oxford-comma natural-language summaries — so no explainer
re-implements phrasing.

### Decision Flow (GET /products/{id}/explanations)

```
Client ─► product_explanations (router)
             │
             ├─► DuplicateDetectionService.detect_by_product_id ─► DuplicateDecision
             │        └─► decision_to_verification ─► DuplicateVerification
             │                 └─► ExplanationService.explain_duplicate ─► trace
             │
             └─► RecommendationEngineService.recommend ─► [RecommendationCandidate]
                      └─► ExplanationService.explain_recommendation (each) ─► [trace]
                                    │
                                    ▼
                      ProductExplanationsResponse
                      {duplicate: trace, recommendations: [trace…]}
```

### The Endpoints

- `GET /recommendations/{product_id}/trace` — one explanation trace per
  recommended product (its "decision timeline").
- `GET /duplicates/{product_id}/trace` — the product's duplicate-decision
  trace (reuses `decision_to_verification`, the adapter extracted from
  Phase 15, so an already-indexed product's weighted `DuplicateDecision`
  is explained through the same `DuplicateExplainer`).
- `GET /products/{product_id}/explanations` — both combined into one
  explanation tree.

All three are read-only `GET`s, additive (no existing endpoint changed),
and each `ExplanationResponse` carries the natural-language `summary`, the
structured `reasons` tree, the `ConfidenceBreakdown` score accounting, and
a `created_at` timestamp.

### Metrics (Phase 14 integration)

`ExplanationService` records three metrics through the existing
`MetricsRegistry`: `explanation_seconds` (build latency),
`explanations_total{decision_type=…}` (generation count + decision-type
distribution), and `explanation_confidence` (confidence distribution, for
the average-confidence view). Every `explain_*` call is timed and
recorded.

### Configuration

No new settings this phase — the explanation layer has nothing to
configure. It reuses the existing services, the Phase 13 model registry,
and the Phase 14 metrics registry, adding only read-only endpoints and
the explanation domain.

### Explicitly out of scope this phase

Explanations for pricing intelligence are deferred to the (future)
pricing phase — the explainers are built so a `PriceEstimateExplainer`
slots in the same way. No rewrite of any existing reason/signal type, no
change to any inference path.

## Phase 17 — Pricing Intelligence Engine design decisions

This phase estimates a fair market price for a product from
*semantically similar priced products* — retrieval-driven, not
static rules — using deterministic algorithms over the comparables the
existing search pipeline finds.

### Reuses Retrieval, Trains Nothing

Pricing runs **no ML training and no new model**. It reuses the
retrieval pipeline (`HybridSearchService`, and the Phase 11 cross-encoder
when reranking is on) to find comparable products, then applies plain,
reproducible arithmetic. The same comparables and strategy always produce
the same estimate — no randomness anywhere. That's why `PRICING__ENABLED`
defaults **on** (unlike the reranker/verification flags): pricing itself
adds no heavy model load; it's only as heavy as the retrieval it reuses.

### Architecture

```
   POST /pricing/estimate (described)     GET /pricing/{id} (indexed)
             │                                      │
             ▼                                      ▼
   HybridSearchService.search            search_by_product_id
   (text query, optional rerank)         (reuses stored embedding)
             └──────────────┬───────────────────────┘
                            ▼
                    PriceNormalizer
              (keep positively-priced comparables)
                            ▼
                    PriceEstimator
        IQR outlier removal ─► aggregate (strategy) ─► confidence
                            ▼
                      PriceEstimate
             {price, confidence, comparables, reason}
```

`PricingEngine` is the concrete `BasePricingService`; a route depends on
that interface, not the engine. Two entry points: price a *described*
(not-yet-indexed) product from its text, or price an *already-indexed*
product by ID (reusing its stored embedding, target excluded).

### The Algorithms (deterministic)

1. **Outlier removal** — a Tukey IQR fence drops comparables whose price
   falls outside `[Q1 − k·IQR, Q3 + k·IQR]` (`k = OUTLIER_IQR_MULTIPLIER`,
   default `1.5`), *before* aggregation, so even the mean-based strategies
   aren't skewed by a mispriced listing. Skipped below four comparables
   (quartiles aren't meaningful).
2. **Aggregation** (`PRICING__STRATEGY`):
   - **weighted average** — prices weighted by each comparable's
     similarity, so a closer match pulls the estimate more.
   - **trimmed mean** — drops the cheapest/most-expensive `TRIM_RATIO`
     fraction from each end before averaging.
   - **median** — the middle price, fully robust to extremes.
3. **Confidence** — blends how many comparables survived (`count_factor`,
   saturating at twice `MIN_COMPARABLES`) with how tightly their prices
   agree (`spread_factor = 1 − coefficient_of_variation`). Plentiful *and*
   consistent comparables score `HIGH`; below `MIN_COMPARABLES` the band
   is forced `LOW` no matter how tight — too little evidence to trust.

Every estimate carries a human-readable `pricing_reason` (strategy,
comparable count, outliers removed, confidence band) — the phase's
"explainable pricing" requirement.

### API

- `POST /pricing/estimate` — price a described product from a JSON body
  (`name` required; `top_k` overridable).
- `GET /pricing/{product_id}` — price an already-indexed product by ID
  (`404` if not indexed).

Both return `{estimated_price, confidence, confidence_score, strategy,
comparable_count, pricing_reason, comparables[]}`. `estimated_price` is
`0.0` with `confidence="low"` and no comparables when nothing priced could
be found — distinguishable from a real (always `> 0`) estimate. The
router is registered only when `PRICING__ENABLED` is on.

### Metrics (Phase 14 integration)

`PricingEngine` records three metrics through the existing
`MetricsRegistry`: `pricing_seconds` (latency, retrieval + aggregation),
`pricing_estimates_total{confidence=…}` (count + confidence-band
distribution), and `pricing_confidence` (confidence-score distribution).

### Benchmarking pricing accuracy

No pricing dataset ships with the repo, so a full accuracy harness isn't
built here (the same reason the retrieval benchmark, Phase 10, ships its
own small dataset and pricing has none). The intended evaluation is
standard and deterministic: hold out a set of already-priced products,
call `GET /pricing/{id}` for each (its own price excluded, since
`search_by_product_id` excludes the target), and compare the estimate
against the true price with MAPE (mean absolute percentage error). Because
the whole engine is deterministic, such a benchmark is fully reproducible
run to run.

### Configuration

New settings under `PricingSettings` (env prefix `PRICING__`):

| Setting | Default | Purpose |
|---|---|---|
| `PRICING__ENABLED` | `true` | Registers the pricing endpoints |
| `PRICING__STRATEGY` | `trimmed_mean` | Aggregation algorithm |
| `PRICING__TOP_K` | `20` | How many comparables to retrieve |
| `PRICING__TRIM_RATIO` | `0.1` | Fraction trimmed per end for trimmed mean (`0 ≤ x < 0.5`) |
| `PRICING__MIN_COMPARABLES` | `3` | Below this, confidence can't exceed LOW |
| `PRICING__OUTLIER_IQR_MULTIPLIER` | `1.5` | Tukey fence multiplier for outlier removal |

### Explicitly out of scope this phase

No ML price model, no training, no time-series/seasonal modeling, no
currency conversion — deterministic retrieval-plus-arithmetic only, per
the phase's own "no ML training, deterministic algorithms" requirement.

## Phase 18 — Analytics & Business Intelligence Platform design decisions

This phase turns operational activity into business insights over a
REST-only surface: per-day usage counts, a live dashboard, model
inventory analytics, and daily/weekly/monthly trend reports with
JSON/Markdown export.

### Historical Reporting on Redis, No Database

Historical analytics needs *persisted* daily history, but this project
has no database (the Redis-only decision from Phase 12). So the analytics
layer stores its history in **Redis daily buckets**:
`AnalyticsRepository` increments a per-day counter per event
(`analytics:count:{event}:{YYYY-MM-DD}`) and accumulates
product-processing latency into per-day sum/count keys, each with a
90-day TTL so history self-prunes. `AnalyticsEngine` reads those buckets
to aggregate any window. This keeps analytics consistent with the rest of
the platform's lightweight, no-DB architecture while still supporting
real historical reporting.

### Recording Is Fail-Soft

The upload / duplicate-check / recommendation / search endpoints each
record their event, and `ProductWorker` records processing latency — but
recording is **fail-soft**: a Redis write that fails is logged and
swallowed, never breaking the request that triggered it (an upload
succeeds even if the analytics counter can't be written). Analytics is an
observation of the business, never a dependency of it.

### Architecture

```
   upload / check-duplicate / recommendation / search endpoints
   ProductWorker (latency)
             │  record_event / record_latency (fail-soft)
             ▼
      AnalyticsRepository  ── Redis daily buckets (TTL'd) ──┐
                                                            │  read
                                                            ▼
                                                     AnalyticsEngine
                                                     (+ ModelRegistry)
                                                            │
             ┌──────────────┬───────────────┬──────────────┤
             ▼              ▼               ▼              ▼
      /analytics/      /analytics/     /analytics/    /analytics/
       dashboard         models         pipeline        trends
                                                    (JSON | Markdown)
```

`AnalyticsEngine` is a pure reader — it never records an event and never
runs a model. Per-model *inference counts* stay in Prometheus
(`embedding_inference_total{model}`, Phase 14); the analytics `models`
view is about model *lifecycle/inventory* (active version + registered
count per type, from the Phase 13 registry), not re-counting inference.

### The Endpoints

- `GET /analytics/dashboard` — today's usage, the trailing window's usage,
  and how many models are active.
- `GET /analytics/models` — per model type: the active version, lifecycle
  status, and registered-version count, plus window usage.
- `GET /analytics/pipeline` — the window's throughput and average
  product-processing latency, as a labeled report.
- `GET /analytics/trends?metric=&granularity=&periods=&format=` — a
  daily/weekly/monthly trend for one metric, as JSON or a Markdown table.
  Granularities are **fixed-length windows** (1/7/30 days), not calendar
  months, so buckets are deterministic and trivially derived from the
  per-day counters.

All read endpoints are additive `GET`s, registered only when
`ANALYTICS__ENABLED` is on.

### Metrics

Per the phase's "reuse existing metrics" requirement, no new Prometheus
metrics are added: the `/analytics` endpoints are covered by the standard
`http_request_*` series (Phase 14), and the events they report on already
have their own metrics (`worker_jobs_total`,
`duplicate_verification_decisions_total`, ...). The analytics layer's own
job is the *historical* view Prometheus counters can't provide.

### Configuration

New settings under `AnalyticsSettings` (env prefix `ANALYTICS__`):

| Setting | Default | Purpose |
|---|---|---|
| `ANALYTICS__ENABLED` | `true` | Registers the `/analytics` endpoints |
| `ANALYTICS__WINDOW_DAYS` | `7` | Default trailing window for the dashboard/pipeline aggregates |

### Explicitly out of scope this phase

No frontend (REST-only, per the phase requirement), no database, no
real-time streaming or per-minute granularity — day-grained historical
reporting over Redis buckets, nothing heavier.

## Phase 19 — Enterprise Platform Features design decisions

This phase adds multi-tenancy, RBAC, API-key authentication, audit
logging, and per-tenant quotas/rate limiting — as an **opt-in layer** that
leaves the pre-Phase-19 platform untouched when disabled.

### Opt-In, So Nothing Breaks

`ENTERPRISE__ENABLED` defaults to **`False`**. With it off, the platform
is exactly what it was through Phase 18: unauthenticated, single-tenant,
every endpoint open. The enterprise router isn't even registered, and no
existing route gains an auth requirement. Turning it on activates
API-key auth + RBAC on the enterprise-gated routes, tenant isolation,
audit logging, and quotas. This is what let the whole phase be **additive**
— honoring the standing "never rewrite completed phases" rule and the
phase's own "maintain backward compatibility." Deep tenant isolation
(threading a `tenant_id` through every Phase 2–18 service) was explicitly
*not* done; instead the layer provides an isolation **mechanism**
(`TenantScope`) an enterprise-aware caller uses, leaving existing
single-tenant callers on their unscoped defaults.

### Architecture

```
   request ─► get_auth_context ──► AuthContext (org, tenant, role, key)
                    │  (X-API-Key → AuthenticationService, 401 on bad key)
      ┌─────────────┼─────────────────────────┐
      ▼             ▼                          ▼
 require_permission   enforce_quota      TenantScope.from_auth
 (RBAC, 403)          (429 over limit)   (tenant-scoped names)
      │                                        │
      ▼                                        ▼
  /organizations //api-keys //audit //usage    tenant-scoped Qdrant
  (audit-logged)                                collections + Redis keys
```

Everything persists in **Redis** (no database), matching the Phase 12
decision: organizations, tenants, API-key records, audit logs, and quota
counters are all Redis-backed.

### API-Key Security

- Keys are **high-entropy** random tokens (`pik_` + 24 random bytes,
  url-safe ≈ 192 bits) — not user-chosen, so a plain **SHA-256** hash is a
  sound at-rest representation (a slow salted KDF is for low-entropy
  passwords, not this).
- Only the **hash** and a short non-secret **prefix** are stored; the raw
  key is returned **exactly once** at creation and is never stored,
  recoverable, or logged.
- Verification recomputes the hash and compares it in **constant time**
  (`hmac.compare_digest`), so a wrong key doesn't leak timing.
- The prefix is the lookup index, so authenticating a key is a single
  Redis GET plus one hash comparison.

### RBAC & No Privilege Escalation

`Role` (owner ⊇ admin ⊇ member ⊇ viewer) maps to a set of `Permission`s;
a route guards itself with `require_permission(Permission.X)` and a key
whose role lacks `X` gets a **403** (distinct from the **401** a missing
key gets). Creating a key can never mint one with **more** authority than
the caller: `POST /api-keys` rejects a requested role whose permissions
aren't a subset of the caller's own.

### Tenant Isolation

Every tenant-scoped operation partitions on the authenticated
`tenant_id`: API-key listing/revocation only ever touches the caller's
tenant (revoking another tenant's key `404`s — it's indistinguishable
from "doesn't exist," so a caller can't even probe for it), the audit log
and quota counters are per-tenant Redis keys, and `TenantScope` derives
physically-separate Qdrant collection names
(`{prefix}_{tenant_id}_{base}`) for an enterprise-aware vector store.

### Audit & Quotas

Key-management actions (`create_api_key`, `revoke_api_key`) append an
append-only `AuditEvent` to the tenant's Redis log (newest first, capped).
`enforce_quota` records each request against the tenant's per-day and
per-minute Redis counters and returns **429** when either limit is
exceeded (a configured limit of `0` disables that check). Quota
enforcement is **fail-closed** — if Redis is unreachable the guarded
request errors rather than silently allowing unlimited traffic.

### Security Review Notes

- **Bootstrap is open.** `POST /organizations` requires no key — it's how
  a new account obtains its first (owner) key. In a real deployment this
  would sit behind a platform-admin gate (a deploy-time bootstrap token);
  here it's the documented bootstrap entry point, and it's the *only* open
  enterprise route.
- **No secret ever leaves except once.** Raw keys appear only in the
  create responses; listings expose prefix + metadata only. Audit events
  and logs never carry a raw key, embedding, or product payload.
- **Auth vs. authorization are distinct** (401 vs. 403), and identity is
  established before quota is consumed (an unauthenticated request never
  counts against a tenant's quota).
- **Backward compatibility.** With the layer off, there is no
  authentication surface at all — the security posture is unchanged from
  Phase 18.

### Configuration

New settings under `EnterpriseSettings` (env prefix `ENTERPRISE__`):

| Setting | Default | Purpose |
|---|---|---|
| `ENTERPRISE__ENABLED` | `false` | Master switch — off preserves the pre-Phase-19 platform exactly |
| `ENTERPRISE__API_KEY_HEADER` | `X-API-Key` | Header the raw key is read from |
| `ENTERPRISE__DAILY_REQUEST_QUOTA` | `10000` | Per-tenant per-day request ceiling (`0` disables) |
| `ENTERPRISE__RATE_LIMIT_PER_MINUTE` | `120` | Per-tenant per-minute ceiling (`0` disables) |
| `ENTERPRISE__COLLECTION_PREFIX` | `tenant` | Namespaces a tenant's Qdrant collections |

### Explicitly out of scope this phase

No deep per-service tenant retrofit (the isolation mechanism is provided,
not force-wired through Phase 2–18 services), no OAuth/OIDC/SSO, no
external identity provider, no database — API-key + RBAC + Redis-backed
tenancy, opt-in and additive.

## Setup instructions

Prerequisites: [`uv`](https://docs.astral.sh/uv/) installed (`uv` manages
its own Python interpreters, so a system Python is not required).

```bash
cd backend
uv sync              # creates .venv, installs runtime + dev dependencies from uv.lock
cd ..
uv run --project backend pre-commit install
```

`pre-commit install` deliberately runs from the **repo root**, not
`backend/` — git hooks always execute with their working directory at the
repo root (regardless of where `git commit` is run from inside the repo),
and `.pre-commit-config.yaml` lives there too, so this is the one command
in this whole file that should *not* be run from inside `backend/`.
`--project backend` still points it at backend's venv (where the
`pre-commit` package is actually installed) without changing the working
directory. An earlier version of this instruction (`cd backend && ...
--config ../.pre-commit-config.yaml`) baked a relative path into the
installed git hook that pointed *above* the repo at actual hook-execution
time — silently broken since Milestone 1. See the Makefile's `install`
target for the same fix, with the reasoning duplicated as a comment there.

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

**Phase 2B (Product Processing & Metadata Normalization)** added, from
the repo root — six milestones, each its own commit:

```bash
cd backend

# Milestone 1/6 — Checksum Service
#   app/exceptions/errors.py — added ChecksumException
#   app/services/checksum_service.py — hand-written
#   tests/services/test_checksum_service.py — hand-written
uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest
cd .. && git add -A && git commit -m "feat: add checksum service (Phase 2B milestone 1/6)" && cd backend

# Milestone 2/6 — File Metadata utility
#   app/utils/metadata.py — hand-written
mkdir -p tests/utils && touch tests/utils/__init__.py
#   tests/utils/test_metadata.py — hand-written
uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest
cd .. && git add -A && git commit -m "feat: add file metadata parser (Phase 2B milestone 2/6)" && cd backend

# Milestone 3/6 — Validators
mkdir -p app/validators tests/validators
touch app/validators/__init__.py tests/validators/__init__.py
#   app/validators/{file_validator,product_validator}.py — hand-written
#   app/services/upload_service.py — refactored to call file_validator
#   tests/validators/test_{file_validator,product_validator}.py — hand-written
uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest
cd .. && git add -A && git commit -m "feat: add reusable validators (Phase 2B milestone 3/6)" && cd backend

# Milestone 4/6 — Product domain model
#   app/models/product.py — hand-written
mkdir -p tests/models && touch tests/models/__init__.py
#   tests/models/test_product.py — hand-written
uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest
cd .. && git add -A && git commit -m "feat: add Product domain model (Phase 2B milestone 4/6)" && cd backend

# Milestone 5/6 — ProductService orchestrator
#   app/services/product_service.py — hand-written
#   app/dependencies/product.py — hand-written
#   tests/services/test_product_service.py, tests/dependencies/test_product.py — hand-written
uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest
cd .. && git add -A && git commit -m "feat: add ProductService orchestrator (Phase 2B milestone 5/6)" && cd backend

# Milestone 6/6 — Router integration
#   app/schemas/product.py — UploadResponse gained product_id, checksum_sha256
#   app/api/products.py — now calls product_service.process_upload after upload_service.save_upload
#   tests/api/test_products.py — updated for the new response shape + dependency overrides
uv run ruff check .
uv run black --check .
uv run mypy .
uv run pytest
uv run uvicorn app.main:app --reload   # manual smoke test with curl -F uploads
cd ..
uv run --project backend pre-commit run --all-files -c .pre-commit-config.yaml
git add -A
git commit -m "feat: wire ProductService into the upload endpoint (Phase 2B milestone 6/6)"
```

**Phase 3 (Image Processing Pipeline)** added, from the repo root — six
steps in dependency order (not the phase spec's own milestone numbering,
which wasn't a buildable sequence — the validator/service that use the
utilities and domain model need those to exist first):

```bash
cd backend
uv add pillow
cd ..

# Step 1 — constants/settings/paths
#   app/core/constants.py — added SUPPORTED_IMAGE_PIL_FORMATS,
#   PROCESSED_IMAGE_FORMAT/_EXTENSION, dimension defaults
#   app/core/paths.py — added PROCESSED_DIR, updated ensure_runtime_directories
#   app/core/settings.py — StorageSettings gained processed_dir,
#   max_image_dimension_px, processed_image_size_px
#   app/exceptions/errors.py — added InvalidImageException, ImageTooLargeException
#   backend/.env.example — documented the three new STORAGE__ variables

# Step 2 — image utilities
#   app/utils/image.py — hand-written
#   tests/utils/test_image.py — hand-written

# Step 3 — ImageMetadata domain model
#   app/models/image_metadata.py — hand-written
mkdir -p backend/tests/models  # (already existed from Phase 2B)
#   tests/models/test_image_metadata.py — hand-written

# Step 4 — ImageValidator
#   app/validators/image_validator.py — hand-written
#   tests/validators/test_image_validator.py — hand-written

# Step 5 — ImageProcessingService
#   app/services/image_processing_service.py — hand-written
#   tests/services/test_image_processing_service.py — hand-written

# Step 6 — integration
#   app/models/product.py — Product gained image_metadata: ImageMetadata
#   app/services/product_service.py — composes ImageProcessingService,
#   calls it between checksum and metadata parsing
#   app/schemas/product.py — added ProcessedImageInfo, UploadResponse
#   gained processed_image
#   app/api/products.py — maps Product.image_metadata onto the response
#   tests/models/test_product.py, tests/services/test_product_service.py,
#   tests/schemas/test_product.py, tests/api/test_products.py — updated
#   for the new required field / real-image test fixtures

cd backend
uv run ruff check .
uv run black --check .
uv run mypy .
uv run pytest
uv run uvicorn app.main:app --reload   # manual smoke test: resize, EXIF
                                        # rotation, RGBA->RGB, corruption
cd ..
uv run --project backend pre-commit run --all-files
git add -A
git commit -m "feat: add image processing pipeline (Phase 3)"
```

**Phase 4 (Image Embedding Pipeline)** added, from the repo root — six
steps in dependency order:

```bash
cd backend
uv add transformers torch --extra-index-url https://download.pytorch.org/whl/cpu
cd ..

# Step 1 — AI settings + exceptions
#   app/core/settings.py — AIModelSettings gained clip_model_name,
#   embedding_device, embedding_batch_size
#   app/core/constants.py — added DEFAULT_CLIP_MODEL_NAME
#   app/exceptions/errors.py — added EmbeddingGenerationException
#   backend/.env.example — documented the three new AI_MODELS__ variables
#   tests/core/test_settings.py — extended with TestAIModelSettings

# Step 2 — BaseEmbeddingService abstraction
#   app/services/embeddings/base.py — hand-written (generate_embedding(s)
#   plus an abstract model_name property)
#   tests/services/embeddings/test_base.py — hand-written

# Step 3 — ModelManager
#   app/services/embeddings/model_manager.py — hand-written
#   tests/services/embeddings/test_model_manager.py — hand-written
#   (includes a thread-safety test and a real-tiny-model integration test)

# Step 4 — CLIPEmbeddingService
#   app/services/embeddings/clip_service.py — hand-written (implements
#   model_name as a property returning self._model_name)
#   tests/services/embeddings/test_clip_service.py — hand-written
#   (batching, normalization, error wrapping, and real-tiny-model tests)

# Step 5 — ImageEmbedding domain model
#   app/models/embedding.py — hand-written
#   tests/models/test_embedding.py — hand-written

# Step 6 — integration
#   app/models/product.py — Product gained embedding: ImageEmbedding
#   app/services/product_service.py — composes CLIPEmbeddingService,
#   calls it between image processing and metadata parsing
#   app/schemas/product.py — added EmbeddingInfo, UploadResponse
#   gained embedding
#   app/api/products.py — maps Product.embedding onto the response
#   app/dependencies/product.py — docstring updated to note
#   CLIPEmbeddingService/ModelManager's "loaded once" guarantee
#   tests/models/test_product.py, tests/services/test_product_service.py,
#   tests/schemas/test_product.py, tests/api/test_products.py — updated
#   for the new required field / fake and real-tiny-model fixtures

cd backend
uv run ruff check .
uv run black --check .
uv run mypy .
uv run pytest
uv run uvicorn app.main:app --reload   # manual smoke test with curl -F uploads,
                                        # inspect response.embedding
cd ..
uv run --project backend pre-commit run --all-files
git add -A
git commit -m "feat: add image embedding pipeline (Phase 4)"
```

**Phase 5 (Vector Search & Retrieval)** added, from the repo root — six
milestones, each its own commit:

```bash
cd backend
uv add qdrant-client
cd ..

# Milestone 1 — BaseVectorStore abstraction
#   app/models/search.py — NearestNeighbor (built ahead of Milestone 3,
#   since BaseVectorStore.search needs it as a return type)
#   app/services/vectorstore/base.py — BaseVectorStore, VectorRecord
#   tests/models/test_search.py, tests/services/vectorstore/test_base.py — hand-written
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: add vector store abstraction (Phase 5 milestone 1/6)"

# Milestone 2 — Qdrant integration
#   app/core/constants.py — added DEFAULT_VECTOR_COLLECTION_NAME,
#   DEFAULT_VECTOR_SIZE, DEFAULT_SEARCH_TOP_K, MAX_SEARCH_TOP_K
#   app/core/settings.py — added VectorStoreSettings
#   app/exceptions/errors.py — added VectorStoreException
#   backend/.env.example — documented the four new VECTOR_STORE__ variables
#   app/services/vectorstore/qdrant_store.py — QdrantVectorStore
#   tests/core/test_settings.py, tests/services/vectorstore/test_qdrant_store.py — hand-written
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: add Qdrant vector store integration (Phase 5 milestone 2/6)"

# Milestone 3 — search domain models
#   app/models/search.py — added SearchQuery, SearchResult
#   tests/models/test_search.py — extended
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: add search domain models (Phase 5 milestone 3/6)"

# Milestone 4 — SearchService + upsert-on-upload wiring
#   app/services/vectorstore/search_service.py — SearchService
#   app/services/product_service.py — composes BaseVectorStore, upserts
#   after building each Product
#   app/dependencies/search.py — get_search_service
#   tests/services/vectorstore/test_search_service.py,
#   tests/services/test_product_service.py, tests/dependencies/test_search.py,
#   tests/api/test_products.py — hand-written / updated
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: add SearchService and wire product uploads into the vector store (Phase 5 milestone 4/6)"

# Milestone 5 — search API endpoint
#   app/schemas/search.py — ProductSearchResult, ProductSearchResponse
#   app/api/search.py — POST /products/search
#   app/application.py — registers search_router
#   tests/schemas/test_search.py, tests/api/test_search.py,
#   tests/test_application.py — hand-written / updated
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: expose the product search API endpoint (Phase 5 milestone 5/6)"

# Milestone 6 — comprehensive test hardening
#   tests/services/vectorstore/test_qdrant_store.py — duplicate IDs, empty
#   results, metadata filters, similarity ordering, top-k boundary,
#   error-wrapping per method, collection-creation thread-safety
#   tests/api/test_search.py — category filter, top_k end-to-end
#   backend/README.md — this section
cd backend
uv run ruff check .
uv run black --check .
uv run mypy .
uv run pytest
uv run uvicorn app.main:app --reload   # manual smoke test: upload a product,
                                        # then search with the same image
cd ..
uv run --project backend pre-commit run --all-files
git add -A
git commit -m "test: harden vector search test coverage (Phase 5 milestone 6/6)"
```

**Phase 6 (Text Embeddings & Hybrid Search)** added, from the repo root —
six milestones, each its own commit. Milestone 3 was actually built (and
committed) before Milestone 2, since product text indexing depends on the
two-collection vector store existing first — the phase's own milestone
numbering isn't a buildable order here, the same reordering earlier
phases already used for their own dependencies:

```bash
cd backend
uv add sentence-transformers
cd ..

# Milestone 1 — text embedding infrastructure
#   app/services/embeddings/text_base.py — BaseTextEmbeddingService
#   app/services/embeddings/text_model_manager.py — TextModelManager
#   (reuses ModelManager.resolve_device directly)
#   app/services/embeddings/sentence_transformer_service.py — SentenceTransformerEmbeddingService
#   app/models/text_embedding.py — TextEmbedding
#   app/core/constants.py — added DEFAULT_TEXT_MODEL_NAME, DEFAULT_TEXT_VECTOR_SIZE
#   app/core/settings.py — AIModelSettings gained text_model_name/text_device/
#   text_batch_size/text_normalize
#   app/exceptions/errors.py — added TextEmbeddingException
#   backend/.env.example — documented the four new AI_MODELS__TEXT_* variables
#   tests/services/embeddings/test_text_base.py, test_text_model_manager.py,
#   test_sentence_transformer_service.py, tests/models/test_text_embedding.py,
#   tests/core/test_settings.py — hand-written / extended
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: add text embedding infrastructure (Phase 6 milestone 1/6)"

# Milestone 3 — text vector storage (built before milestone 2, see above)
#   app/services/vectorstore/base.py — BaseVectorStore methods gained a
#   VectorCollection argument; upsert_image/upsert_text/search_image/
#   search_text added as concrete convenience methods
#   app/services/vectorstore/qdrant_store.py — manages two collections,
#   each with independent lazy creation and locking
#   app/models/search.py — added ProductFilters (replaces the old flat
#   filters dict now that price needs a range condition)
#   app/core/constants.py, app/core/settings.py — collection settings
#   renamed/extended for two collections; added HybridSearchSettings
#   backend/.env.example — updated VECTOR_STORE__ variables
#   app/services/vectorstore/search_service.py, app/api/search.py — updated
#   for the new collection-aware/ProductFilters signatures
#   tests/services/vectorstore/test_base.py, test_qdrant_store.py,
#   test_search_service.py, tests/services/test_product_service.py,
#   tests/models/test_search.py, tests/core/test_settings.py,
#   tests/api/test_products.py, tests/api/test_search.py — updated
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: split the vector store into image and text collections (Phase 6 milestone 3/6)"

# Milestone 2 — product text indexing
#   app/services/product_service.py — builds a text representation
#   (name/brand/category/description) and embeds it right after the
#   image embedding; upserts into both collections
#   app/models/product.py — Product gained brand, text_embedding
#   app/schemas/product.py, app/api/products.py — ProductCreate/the
#   upload form gained an optional brand field
#   tests/services/test_product_service.py, tests/models/test_product.py,
#   tests/schemas/test_product.py, tests/api/test_products.py,
#   tests/api/test_search.py — hand-written / updated
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: generate and index a text embedding for every uploaded product (Phase 6 milestone 2/6)"

# Milestone 4 — HybridSearchService
#   app/services/vectorstore/text_search_service.py — TextSearchService
#   (mirrors SearchService, but text-only)
#   app/services/vectorstore/hybrid_search_service.py — HybridSearchService
#   (dispatches image-only/text-only/hybrid; weighted score fusion)
#   app/models/search.py — added SearchModality, HybridSearchResult
#   app/exceptions/errors.py — added HybridSearchException
#   app/dependencies/hybrid_search.py — get_hybrid_search_service
#   tests/services/vectorstore/test_text_search_service.py,
#   test_hybrid_search_service.py, tests/dependencies/test_hybrid_search.py,
#   tests/models/test_search.py — hand-written / extended
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: add hybrid search with weighted score fusion (Phase 6 milestone 4/6)"

# Milestone 5 — replace the search API endpoint
#   app/schemas/search.py — ProductSearchResult gained matched_modalities
#   app/api/search.py — rewritten: optional file + optional query (at
#   least one required), brand/category/price-range filters, backed by
#   HybridSearchService instead of SearchService
#   tests/schemas/test_search.py, tests/api/test_search.py — rewritten
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: replace the search endpoint with image/text/hybrid search (Phase 6 milestone 5/6)"

# Milestone 6 — test hardening + documentation
#   tests/api/test_products.py — confirms an upload actually lands in
#   both the image and text collections, not just that ProductService's
#   own unit tests believe it does
#   tests/api/test_search.py — brand/category/price-range filters, top_k,
#   end-to-end through the real hybrid endpoint
#   tests/services/test_product_service.py — concurrent uploads produce
#   distinct products
#   tests/services/vectorstore/test_hybrid_search_service.py — concurrent
#   searches each return their own correct, uncontaminated result
#   backend/README.md — this section
cd backend
uv run ruff check .
uv run black --check .
uv run mypy .
uv run pytest
uv run uvicorn app.main:app --reload   # manual smoke test: upload a product,
                                        # then search by image, by text, and by both
cd ..
uv run --project backend pre-commit run --all-files
git add -A
git commit -m "test: harden text and hybrid search test coverage (Phase 6 milestone 6/6)"

## Phase 7 — Catalog Intelligence & Product Enrichment (built from scratch)

```bash
# Milestone 1/6 — catalog intelligence domain models
#   app/models/catalog_tags.py — Source enum (TEXT/IMAGE/HYBRID), CatalogTag
#   app/models/attribute_prediction.py — AttributePrediction
#   app/models/product_attributes.py — ProductAttributes
#   app/models/catalog_intelligence_result.py — CatalogIntelligenceResult
#   app/exceptions/errors.py — added CatalogIntelligenceException
#   tests/models/test_{catalog_tags,attribute_prediction,
#   product_attributes,catalog_intelligence_result}.py — hand-written
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: add catalog intelligence domain models (Phase 7 milestone 1/6)"

# Milestone 2/6 — TextAttributeExtractionService
#   app/services/catalog/text_attribute_service.py — hand-curated keyword
#   lookup tables; extract_attributes (first-match wins) and
#   generate_tags (every match, plus descriptor keywords)
#   tests/services/catalog/test_text_attribute_service.py — hand-written,
#   verified against the phase's own "Nike Air Zoom Pegasus" worked example
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: add deterministic text attribute extraction (Phase 7 milestone 2/6)"

# Milestone 3/6 — ImageAttributeExtractionService
#   app/core/constants.py — added LOW_RESOLUTION_MAX_PIXELS,
#   MEDIUM_RESOLUTION_MAX_PIXELS, BRIGHTNESS_DARK_MAX, BRIGHTNESS_BRIGHT_MIN
#   app/utils/image.py — compute_dominant_color, classify_color_name,
#   compute_brightness, classify_brightness, classify_orientation,
#   compute_aspect_ratio, classify_resolution
#   app/services/catalog/image_attribute_service.py — hand-written
#   tests/utils/test_image.py — extended
#   tests/services/catalog/test_image_attribute_service.py — hand-written,
#   every test against a real Pillow-generated image, no mocking
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: add deterministic image attribute extraction (Phase 7 milestone 3/6)"

# Milestone 4/6 — CatalogIntelligenceService orchestrator
#   app/core/settings.py — added CatalogIntelligenceSettings
#   backend/.env.example — documented the eight new CATALOG_INTELLIGENCE__ variables
#   app/services/catalog/catalog_intelligence_service.py — merges
#   AttributePrediction/CatalogTag lists (highest confidence wins,
#   agreeing sources upgrade tags to Source.HYBRID), computes a weighted
#   quality score
#   tests/services/catalog/test_catalog_intelligence_service.py —
#   fake extraction-service doubles for conflict resolution / tag merging /
#   quality score / feature flags / error wrapping
#   tests/core/test_settings.py — extended with TestCatalogIntelligenceSettings
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: add CatalogIntelligenceService orchestrator (Phase 7 milestone 4/6)"

# Milestone 5/6 — upload pipeline integration
#   app/models/product.py — Product gained catalog_intelligence
#   app/services/product_service.py — composes CatalogIntelligenceService,
#   calls .enrich() right after text embedding generation using the raw
#   submitted name/brand/category/description; adds color/material/
#   gender/season/style/tags to vector store metadata (brand/category
#   stay the pre-existing normalized/slugified values)
#   tests/models/test_product.py, tests/services/test_product_service.py —
#   updated for the new required field / new TestProcessUploadCatalogIntelligence class
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: wire catalog intelligence into the upload pipeline (Phase 7 Milestone 5)"

# Milestone 6/6 — test hardening + documentation
#   tests/services/catalog/test_catalog_intelligence_service.py —
#   TestRealPipelineIntegration: the real (non-fake) text + image
#   extraction services composed end-to-end against the phase's own
#   worked example, plus a malformed-metadata (unicode/whitespace-only/
#   very long text) no-crash test
#   tests/services/test_product_service.py — the pre-existing concurrent-
#   uploads test now also exercises catalog intelligence in every run
#   backend/README.md — this section
cd backend
uv run ruff check .
uv run black --check .
uv run mypy .
uv run pytest
uv run uvicorn app.main:app --reload   # manual smoke test: upload a
                                        # product, confirm the
                                        # "Catalog intelligence enrichment
                                        # applied" log line and a
                                        # sensible tags/quality_score
cd ..
uv run --project backend pre-commit run --all-files
git add -A
git commit -m "test: harden catalog intelligence test coverage and document Phase 7 (Phase 7 milestone 6/6)"
git push
```

## Phase 8 — Duplicate Detection Engine (built from scratch)

```bash
# Milestone 1/6 — duplicate detection domain models
#   app/models/similarity_signal.py — SimilaritySignal
#   app/models/duplicate_candidate.py — DuplicateCandidate
#   app/models/duplicate_result.py — DuplicateResult (SimilarityScorer's
#   detailed per-candidate output)
#   app/models/duplicate_decision.py — DuplicateDecision
#   app/core/constants.py — added DuplicateDetectionMode (OFF/WARN/BLOCK)
#   app/exceptions/errors.py — added DuplicateDetectionException
#   tests/models/test_{similarity_signal,duplicate_candidate,
#   duplicate_result,duplicate_decision}.py — hand-written
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: add duplicate detection domain models (Phase 8 milestone 1/6)"

# Milestone 2/6 — SimilarityScorer
#   app/models/search.py — HybridSearchResult gained image_score/text_score
#   app/services/vectorstore/hybrid_search_service.py — _fuse/
#   _single_modality_result populate the two new fields
#   app/core/settings.py — added DuplicateDetectionSettings (weights
#   validated to sum to 1.0)
#   backend/.env.example — documented the seven new DUPLICATE_DETECTION__ variables
#   app/services/duplicate/similarity_scorer.py — hand-written (rapidfuzz
#   token_sort_ratio for metadata/attribute signals; reuses hybrid
#   search's own image_score/text_score)
#   tests/models/test_search.py, tests/services/vectorstore/
#   test_hybrid_search_service.py, tests/core/test_settings.py — extended
#   tests/services/duplicate/test_similarity_scorer.py — hand-written
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: add SimilarityScorer for duplicate detection (Phase 8 milestone 2/6)"

# Milestone 3/6 — DuplicateDetectionService orchestrator
#   app/utils/text.py — build_text_representation extracted out of
#   ProductService (shared, avoids a circular import once ProductService
#   composes this service next milestone)
#   app/services/duplicate/duplicate_detection_service.py — hand-written:
#   retrieves candidates via HybridSearchService, scores each via
#   SimilarityScorer, ranks/thresholds into a DuplicateDecision
#   tests/utils/test_text.py, tests/services/duplicate/
#   test_duplicate_detection_service.py — hand-written
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: add DuplicateDetectionService orchestrator (Phase 8 milestone 3/6)"

# Milestone 4/6 — upload pipeline integration
#   app/models/product.py — Product gained duplicate_decision
#   app/services/product_service.py — composes DuplicateDetectionService,
#   calls .detect() right after catalog intelligence enrichment;
#   BLOCK-mode duplicates raise ConflictException before normalization/
#   indexing
#   app/schemas/product.py — added DuplicateInfo, UploadResponse gained duplicate
#   app/api/products.py — maps Product.duplicate_decision onto the response
#   tests/models/test_product.py, tests/services/test_product_service.py,
#   tests/schemas/test_product.py, tests/api/test_products.py,
#   tests/api/test_search.py — updated for the new required field /
#   OFF mode in unrelated suites / new TestProcessUploadDuplicateDetection class
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: wire duplicate detection into the upload pipeline (Phase 8 milestone 4/6)"

# Milestone 5/6 — duplicate-check API endpoint
#   app/services/duplicate/duplicate_detection_service.py — detect()
#   gained per-call top_k/threshold overrides
#   app/services/duplicate/duplicate_check_service.py — hand-written:
#   image processing -> catalog intelligence -> duplicate detection,
#   without storing/indexing anything
#   app/dependencies/duplicate.py — get_duplicate_check_service
#   app/schemas/duplicate.py — DuplicateCandidateInfo,
#   DuplicateSignalBreakdown, DuplicateCheckResponse
#   app/api/products.py — POST /products/check-duplicate
#   tests/services/duplicate/test_duplicate_check_service.py,
#   tests/dependencies/test_duplicate.py, tests/schemas/test_duplicate.py,
#   tests/api/test_check_duplicate.py — hand-written
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: add duplicate-check API endpoint (Phase 8 milestone 5/6)"

# Milestone 6/6 — test hardening + documentation
#   tests/services/duplicate/test_duplicate_detection_service.py —
#   concurrent detect() calls each return their own uncontaminated
#   decision, unicode/whitespace-only/very-long-text malformed input
#   tests/test_application.py — extended for the new registered route
#   backend/README.md — this section
cd backend
uv run ruff check .
uv run black --check .
uv run mypy .
uv run pytest
uv run uvicorn app.main:app --reload   # manual smoke test: upload a
                                        # product twice with WARN mode,
                                        # confirm the second upload's
                                        # "duplicate" field flags a match;
                                        # then call
                                        # POST /products/check-duplicate
                                        # against the same product without
                                        # uploading a third time
cd ..
uv run --project backend pre-commit run --all-files
git add -A
git commit -m "test: harden duplicate detection test coverage and document Phase 8 (Phase 8 milestone 6/6)"
git push
```

## Phase 9 — Intelligent Recommendation Engine (built from scratch)

```bash
# Milestone 1/6 — recommendation domain models + retrieval-by-ID infra
#   app/models/recommendation_type.py — RecommendationType (SIMILAR/RELATED/COMPLEMENTARY)
#   app/models/recommendation_reason.py — RecommendationReason
#   app/models/recommendation_candidate.py — RecommendationCandidate
#   app/models/recommendation_result.py — RecommendationResult
#   app/exceptions/errors.py — added RecommendationException
#   app/models/search.py — added StoredPoint
#   app/services/vectorstore/base.py — added retrieve/retrieve_image/retrieve_text
#   app/services/vectorstore/qdrant_store.py — implements retrieve()
#   app/services/vectorstore/search_service.py, text_search_service.py —
#   each gained search_by_vector + retrieve_by_id
#   app/services/vectorstore/hybrid_search_service.py — added
#   search_by_product_id (self-exclusion, +1 internal overfetch)
#   app/services/product_service.py — vector metadata gained quality_score
#   tests/models/test_recommendation_{type,reason,candidate,result}.py,
#   tests/services/vectorstore/test_{base,qdrant_store,search_service,
#   text_search_service,hybrid_search_service}.py — hand-written / extended
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: add recommendation domain models and retrieval-by-ID infra (Phase 9 milestone 1/6)"

# Milestone 2/6 — RecommendationScorer
#   app/core/settings.py — added RecommendationSettings (weights validated to sum to 1.0)
#   backend/.env.example — documented the seven new RECOMMENDATION__ variables
#   app/services/recommendation/recommendation_scorer.py — hand-written:
#   similarity (reused)/attribute match/tag match (Jaccard)/quality, weighted
#   tests/core/test_settings.py — extended
#   tests/services/recommendation/test_recommendation_scorer.py — hand-written
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: add RecommendationScorer (Phase 9 milestone 2/6)"

# Milestone 3/6 — RecommendationEngineService orchestrator
#   app/services/recommendation/recommendation_engine_service.py —
#   hand-written: search_by_product_id retrieves candidates, scores each,
#   sorts, diversifies (round-robin by brand, 3x overfetch)
#   tests/services/recommendation/test_recommendation_engine_service.py — hand-written
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: add RecommendationEngineService orchestrator (Phase 9 milestone 3/6)"

# Milestone 4/6 — recommendations API endpoint
#   app/dependencies/recommendation.py — get_recommendation_engine_service
#   app/schemas/recommendation.py — RecommendationReasonInfo, RecommendationInfo,
#   RecommendationsResponse
#   app/api/products.py — GET /products/{id}/recommendations
#   tests/schemas/test_recommendation.py, tests/dependencies/test_recommendation.py,
#   tests/api/test_recommendations.py, tests/test_application.py — hand-written / updated
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: add recommendations API endpoint (Phase 9 milestone 4/6)"

# Milestone 5/6 — recommendation explanations
#   app/services/recommendation/recommendation_engine_service.py —
#   _build_explanation: turns RecommendationReason + scores into one
#   plain-English sentence per final, diversified recommendation
#   tests/services/recommendation/test_recommendation_engine_service.py,
#   tests/api/test_recommendations.py — extended
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: generate human-readable recommendation explanations (Phase 9 milestone 5/6)"

# Milestone 6/6 — test hardening + documentation
#   tests/services/recommendation/test_recommendation_scorer.py —
#   unrelated-products, malformed-metadata (unicode, non-string values,
#   non-list tags, non-numeric quality_score)
#   tests/services/recommendation/test_recommendation_engine_service.py —
#   concurrent recommend() calls each return their own uncontaminated result
#   backend/README.md — this section
cd backend
uv run ruff check .
uv run black --check .
uv run mypy .
uv run pytest
uv run uvicorn app.main:app --reload   # manual smoke test: upload two
                                        # Nike products and one Adidas
                                        # product, then GET
                                        # /products/{id}/recommendations
                                        # for one of the Nike products —
                                        # confirm the other Nike product
                                        # and the Adidas product both
                                        # appear with populated
                                        # reason/explanation fields
cd ..
uv run --project backend pre-commit run --all-files
git add -A
git commit -m "test: harden recommendation test coverage and document Phase 9 (Phase 9 milestone 6/6)"
git push
```

## Phase 10 — Retrieval Evaluation Framework (built from scratch)

```bash
# Milestone 1/6 — evaluation domain models
#   app/core/paths.py — added EVALUATION_DIR, DEFAULT_DATASET_PATH,
#   REPORTS_DIR; ensure_runtime_directories() also creates REPORTS_DIR
#   app/core/settings.py — added EvaluationSettings
#   backend/.env.example — documented the four new EVALUATION__ variables
#   app/exceptions/errors.py — added EvaluationException
#   app/models/evaluation_query.py — EvaluationTaskType, GroundTruth, EvaluationQuery
#   app/models/retrieval_metrics.py — RetrievalMetrics
#   app/models/evaluation_result.py — EvaluationQueryResult
#   app/models/benchmark_report.py — BenchmarkReport
#   tests/core/test_paths.py, test_settings.py — extended
#   tests/models/test_evaluation_query.py, test_retrieval_metrics.py,
#   test_evaluation_result.py, test_benchmark_report.py — hand-written
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: add evaluation domain models (Phase 10 milestone 1/6)"

# Milestone 2/6 — evaluation dataset + loader
#   backend/evaluation/dataset.json — checked-in 3-entry sample (one per task type)
#   app/services/evaluation/dataset_loader.py — hand-written: reads/validates
#   the flat JSON array into EvaluationQuery objects
#   tests/services/evaluation/test_dataset_loader.py — hand-written
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: add evaluation dataset and loader (Phase 10 milestone 2/6)"

# Milestone 3/6 — RetrievalEvaluator
#   app/services/duplicate/duplicate_detection_service.py — extended:
#   added detect_by_product_id (reuses SimilarityScorer/_build_decision,
#   no duplicated logic)
#   app/services/evaluation/retrieval_evaluator.py — hand-written:
#   Precision@K/Recall@K/MRR/NDCG@K/Hit Rate@K as pure functions, dispatch
#   by task_type, per-query failure isolation, aggregation by task_type
#   tests/services/duplicate/test_duplicate_detection_service.py — extended
#   tests/services/evaluation/test_retrieval_evaluator.py — hand-written
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: add RetrievalEvaluator (Phase 10 milestone 3/6)"

# Milestone 4/6 — benchmark runner script
#   scripts/benchmark.py — hand-written: run_benchmark() + render_markdown()
#   write benchmark.json/benchmark.md to EVALUATION__BENCHMARK_OUTPUT; CLI
#   entry point with --dataset/--output args
#   tests/scripts/test_benchmark.py — hand-written
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
uv run python scripts/benchmark.py --output /tmp/benchmark_smoke   # manual
    # smoke test: confirmed graceful per-query failure isolation and
    # correct report file generation with Qdrant not running locally
git add -A
git commit -m "feat: add benchmark runner script (Phase 10 milestone 4/6)"

# Milestone 5/6 — evaluation API endpoint
#   app/dependencies/evaluation.py — get_dataset_loader, get_retrieval_evaluator
#   app/schemas/evaluation.py — EvaluationRunRequest, EvaluationMetricsInfo,
#   EvaluationQueryResultInfo, EvaluationRunResponse
#   app/api/evaluation.py — POST /evaluation/run (query_ids/limit subset filtering)
#   app/application.py — registered evaluation_router
#   tests/dependencies/test_evaluation.py, tests/schemas/test_evaluation.py,
#   tests/api/test_evaluation.py, tests/test_application.py — hand-written / updated
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: add evaluation API endpoint (Phase 10 milestone 5/6)"

# Milestone 6/6 — test hardening + documentation
#   tests/services/evaluation/test_retrieval_evaluator.py — added
#   TestConcurrency: concurrent evaluate() calls each return their own
#   uncontaminated result (metric correctness, malformed datasets, empty
#   datasets, benchmark generation, and latency reporting were already
#   covered by Milestones 1-5's own tests)
#   backend/README.md — this section
cd backend
uv run ruff check .
uv run black --check .
uv run mypy .
uv run pytest
cd ..
uv run --project backend pre-commit run --all-files
git add -A
git commit -m "test: harden evaluation test coverage and document Phase 10 (Phase 10 milestone 6/6)"
git push
```

## Phase 11 — Cross-Encoder Reranking (built from scratch)

```bash
# Milestone 1-2/6 — cross-encoder infrastructure + rerank domain models
#   (domain models pulled forward: BaseReranker's abstract interface
#   needs RerankResult to exist first)
#   app/core/constants.py — added DEFAULT_RERANKER_MODEL_NAME
#   app/core/settings.py — added RerankerSettings (enabled defaults False —
#   the only feature flag in this codebase that does, since it gates a
#   real model load/inference call, not deterministic computation)
#   backend/.env.example — documented the five new RERANKER__ variables
#   app/exceptions/errors.py — added RerankException
#   app/utils/text.py — added build_text_representation_from_metadata
#   app/models/rerank_reason.py, reranked_candidate.py, rerank_result.py
#   app/services/base_reranker.py — BaseReranker abstract interface
#   app/services/model_manager_cross_encoder.py — ModelManagerCrossEncoder,
#   mirrors TextModelManager's lazy-loading/thread-safety exactly
#   app/services/cross_encoder_service.py — CrossEncoderService.score_pairs,
#   batched, never exposes raw model outputs
#   tests/core/test_settings.py, tests/utils/test_text.py — extended
#   tests/models/test_rerank_{reason,candidate,result}.py,
#   tests/services/test_{model_manager_cross_encoder,cross_encoder_service}.py
#   — hand-written, including real-tiny-model integration tests
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: add cross-encoder infrastructure and rerank domain models (Phase 11 milestone 1-2/6)"

# Milestone 3/6 — RerankerService
#   app/services/reranker_service.py — hand-written: overfetch pool ->
#   build query/document pairs -> CrossEncoderService.score_pairs ->
#   sigmoid-normalize -> sort -> truncate top_k -> RerankResult
#   tests/services/test_reranker_service.py — hand-written
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: add RerankerService (Phase 11 milestone 3/6)"

# Milestone 4/6 — integration into search, recommendations, duplicate detection
#   app/services/vectorstore/hybrid_search_service.py — reranks text/hybrid
#   queries, replaces .score (image-only search left unreranked)
#   app/services/recommendation/recommendation_engine_service.py — reranks
#   against the target's own text representation, replaces .score
#   app/services/duplicate/duplicate_detection_service.py — reranks against
#   the checked product's text, replaces .text_score instead (SimilarityScorer
#   never reads .score); calls HybridSearchService.search with
#   reranking_enabled=False to avoid double-scoring the same candidates
#   tests/services/vectorstore/test_hybrid_search_service.py,
#   tests/services/recommendation/test_recommendation_engine_service.py,
#   tests/services/duplicate/test_duplicate_detection_service.py — extended
#   tests/services/evaluation/test_retrieval_evaluator.py,
#   tests/services/test_product_service.py,
#   tests/services/duplicate/test_duplicate_check_service.py — fake
#   HybridSearchService/DuplicateDetectionService overrides updated for
#   the new reranking_enabled parameter
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: integrate reranking into search, recommendations, and duplicate detection (Phase 11 milestone 4/6)"

# Milestone 5/6 — evaluation integration (before/after comparison)
#   app/models/rerank_comparison_report.py — RerankComparisonReport
#   app/services/evaluation/retrieval_evaluator.py — evaluate() gained a
#   reranking_enabled override threaded to every dispatch target;
#   compare_reranking runs the dataset with it forced off then on and
#   diffs the resulting metrics per task type
#   scripts/benchmark.py — --compare-reranking flag writes
#   rerank_comparison.json/rerank_comparison.md
#   app/schemas/evaluation.py — RerankComparisonResponse
#   app/api/evaluation.py — POST /evaluation/compare-reranking, sharing
#   query_ids/limit subset filtering with /evaluation/run via _resolve_queries
#   tests/models/test_rerank_comparison_report.py,
#   tests/services/evaluation/test_retrieval_evaluator.py,
#   tests/scripts/test_benchmark.py, tests/api/test_evaluation.py,
#   tests/test_application.py — hand-written / extended
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: add reranking comparison to the evaluation framework (Phase 11 milestone 5/6)"

# Milestone 6/6 — test hardening + documentation
#   Coverage audit against the phase's own test-coverage checklist
#   (reranking correctness, empty candidates, malformed metadata, batching,
#   concurrency, disabled reranking, evaluation comparison) — already
#   satisfied by Milestones 1-5's own tests; any remaining gaps closed here
#   backend/README.md — this section
cd backend
uv run ruff check .
uv run black --check .
uv run mypy .
uv run pytest
cd ..
uv run --project backend pre-commit run --all-files
git add -A
git commit -m "test: harden reranking test coverage and document Phase 11 (Phase 11 milestone 6/6)"
git push
```

## Phase 12 — Asynchronous AI Processing Pipeline (built from scratch)

```bash
# Milestone 1-2/6 — job infrastructure + Redis-backed queue
#   (committed together: RedisQueue depends on the AsyncPipelineSettings
#   this commit also adds)
#   app/jobs/job_status.py, job_types.py, job_result.py, base_job.py —
#   Job/JobStatus/JobType/JobResult
#   app/exceptions/errors.py — added JobException
#   app/core/settings.py — added AsyncPipelineSettings (enabled defaults
#   true — this phase's async pipeline is the deliverable itself)
#   backend/.env.example — documented the eight new ASYNC_PIPELINE__ variables
#   app/queue/base_queue.py — BaseQueue abstract interface
#   app/queue/redis_queue.py — RedisQueue: pending/processing/delayed/
#   dead-letter Redis structures, exponential backoff, crash recovery
#   app/queue/queue_manager.py, app/dependencies/queue.py — QueueManager
#   lazy singleton facade
#   pyproject.toml — added redis (runtime) and fakeredis (dev/test,
#   in-memory protocol-compatible fake) dependencies
#   tests/jobs/, tests/queue/, tests/dependencies/test_queue.py,
#   tests/core/test_settings.py — hand-written
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: add job and Redis-backed queue infrastructure (Phase 12 milestone 1-2/6)"

# Milestone 3/6 — worker pipeline
#   app/services/product_service.py — process_upload gained an optional
#   product_id parameter (backward compatible) so a worker can pre-assign
#   one and reuse it across every retry attempt (idempotency)
#   app/workers/product_worker.py — ProductWorker: dequeue, call
#   process_upload as one opaque call, warm the recommendation cache,
#   report completion or route failures through QueueManager.retry
#   app/workers/worker_manager.py — runs worker_concurrency many
#   ProductWorker loops plus one crash-recovery loop; graceful shutdown
#   app/repositories/recommendation_cache_repository.py —
#   RecommendationCacheRepository (Redis, TTL'd)
#   BaseQueue/RedisQueue/QueueManager gained update() (in-place progress
#   persistence, distinct from ack()/retry() which move a job between lists)
#   tests/workers/, tests/repositories/, tests/services/test_product_service.py
#   — hand-written / extended
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: add worker pipeline for background product processing (Phase 12 milestone 3/6)"

# Milestone 4/6 — upload integration + status endpoints
#   app/schemas/product.py — added UploadAcceptedResponse
#   app/schemas/job.py — JobStatusResponse (shared by both status routes)
#   app/api/jobs.py — GET /jobs/{job_id}
#   app/api/products.py — POST /products/upload branches on
#   ASYNC_PIPELINE__ENABLED; added GET /products/{id}/status; GET
#   /products/{id}/recommendations now checks RecommendationCacheRepository
#   first for a plain default request
#   app/dependencies/recommendation.py — added get_recommendation_cache_repository
#   scripts/run_workers.py — standalone WorkerManager entrypoint,
#   graceful shutdown on SIGINT/SIGTERM
#   tests/api/test_products.py, test_check_duplicate.py, test_search.py,
#   test_recommendations.py — each fixture now forces
#   ASYNC_PIPELINE__ENABLED=false (they seed/exercise the full synchronous
#   pipeline through real HTTP requests)
#   tests/api/test_upload_async.py, tests/schemas/test_job.py,
#   tests/scripts/test_run_workers.py — hand-written
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: integrate async upload pipeline with job/product status endpoints (Phase 12 milestone 4/6)"

# Milestone 5/6 — dead-letter queue inspection
#   app/queue/base_queue.py, redis_queue.py, queue_manager.py —
#   get_dead_letter_job_ids promoted to the formal BaseQueue interface
#   app/api/jobs.py — GET /jobs/dead-letter (registered before
#   /jobs/{job_id} so "dead-letter" is never parsed as a job ID)
#   tests/api/test_upload_async.py, tests/queue/test_queue_manager.py —
#   extended
#   (exponential backoff, configurable retry count, retry history, and
#   logging every retry were already built in Milestones 2-3)
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: add dead-letter queue inspection endpoint (Phase 12 milestone 5/6)"

# Milestone 6/6 — test hardening + documentation
#   Coverage audit against the phase's own test-coverage checklist
#   (enqueue, dequeue, retries, failures, duplicate jobs, worker crash
#   recovery, concurrent workers, idempotency, graceful shutdown) — all
#   already satisfied by Milestones 1-5's own tests
#   backend/README.md — this section
cd backend
uv run ruff check .
uv run black --check .
uv run mypy .
uv run pytest
cd ..
uv run --project backend pre-commit run --all-files
git add -A
git commit -m "test: harden async pipeline test coverage and document Phase 12 (Phase 12 milestone 6/6)"
git push
```

## Phase 13 — Model Registry & AI Lifecycle Management (built from scratch)

```bash
# Milestone 1/6 — model domain
#   app/models/model_type.py — ModelType (IMAGE_EMBEDDING/TEXT_EMBEDDING/RERANKER)
#   app/models/model_status.py — ModelStatus (ACTIVE/INACTIVE/DEPRECATED/EXPERIMENTAL)
#   app/models/model_version.py — ModelVersion (semantic-version Annotated str alias)
#   app/models/model_info.py — ModelInfo domain model
#   app/exceptions/errors.py — added ModelRegistryException
#   tests/models/test_model_{type,status,version,info}.py — hand-written
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: add model registry domain (Phase 13 milestone 1/6)"

# Milestone 2/6 — ModelRegistry service
#   app/services/model_registry.py — register/get_active_model/get_model/
#   list_models/activate/deactivate; seeds one ACTIVE v1.0.0 entry per
#   ModelType from the existing AIModelSettings/RerankerSettings values
#   app/dependencies/model_registry.py — cached-singleton provider
#   tests/services/test_model_registry.py, tests/dependencies/test_model_registry.py
#   — hand-written
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: add ModelRegistry service (Phase 13 milestone 2/6)"

# Milestone 3/6 — registry integration
#   app/services/embeddings/clip_service.py,
#   app/services/embeddings/sentence_transformer_service.py,
#   app/services/cross_encoder_service.py — each gained an optional
#   model_registry parameter; model_name now resolves through
#   registry.get_active_model(ModelType.X) when not given explicitly
#   tests/services/embeddings/test_clip_service.py,
#   test_sentence_transformer_service.py, tests/services/test_cross_encoder_service.py
#   — extended with registry-resolution coverage
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: resolve model names via ModelRegistry (Phase 13 milestone 3/6)"

# Milestone 4/6 — model health & metadata API
#   app/schemas/model.py — ModelInfoResponse
#   app/api/models.py — GET /models, GET /models/{type}, GET /models/{type}/active
#   app/application.py — _register_routers() now includes models_router
#   tests/api/test_models.py — hand-written
#   tests/test_application.py — extended for the three new business routes
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: add model health and metadata API (Phase 13 milestone 4/6)"

# Milestone 5/6 — evaluation integration
#   app/models/benchmark_report.py — BenchmarkReport gained a models field
#   app/services/evaluation/retrieval_evaluator.py — RetrievalEvaluator
#   gained an optional model_registry parameter; evaluate() snapshots
#   every ACTIVE model into the report it returns
#   app/schemas/evaluation.py, app/api/evaluation.py — EvaluationRunResponse
#   surfaces the same models snapshot
#   scripts/benchmark.py — render_markdown gained a "Models" section
#   tests/services/evaluation/test_retrieval_evaluator.py,
#   tests/models/test_benchmark_report.py, tests/api/test_evaluation.py,
#   tests/scripts/test_benchmark.py — extended
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: record model provenance on every benchmark run (Phase 13 milestone 5/6)"

# Milestone 6/6 — test hardening + documentation
#   Coverage audit against the phase's own test-coverage checklist
#   (registration, duplicate versions, active model switching, invalid
#   metadata, registry lookup, API responses) — already satisfied by
#   Milestones 1-5's own tests
#   backend/README.md — this section, the Phase 13 design-decisions
#   section, and the Roadmap section (Phases 1-13 complete, 14-20 not
#   yet specified)
cd backend
uv run ruff check .
uv run black --check .
uv run mypy .
uv run pytest
cd ..
uv run --project backend pre-commit run --all-files
git add -A
git commit -m "test: harden model registry test coverage and document Phase 13 (Phase 13 milestone 6/6)"
git push
```

## Phase 14 — AI Observability & Monitoring (built from scratch)

```bash
# Milestone 1/6 — metrics infrastructure
#   pyproject.toml — added prometheus-client + prometheus-fastapi-instrumentator
#   app/metrics/base_metrics.py — idempotent get_or_create_counter/gauge/histogram
#   app/metrics/metric_names.py — metric name constants (namespaced at registration)
#   app/metrics/metrics_registry.py — MetricsRegistry: every collector this codebase
#   records into; queue-state gauges poll Redis fresh per scrape (never coupling to
#   RedisQueue/QueueManager); master switch (METRICS__ENABLED) no-ops every record
#   app/core/settings.py — added MetricsSettings (enabled/prometheus_enabled/
#   health_endpoints_enabled/namespace)
#   backend/.env.example — documented the four new METRICS__ variables
#   app/dependencies/metrics.py — cached-singleton provider
#   tests/metrics/, tests/dependencies/test_metrics.py, tests/core/test_settings.py
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: add metrics infrastructure (Phase 14 milestone 1/6)"

# Milestone 2/6 — AI metrics
#   app/services/embeddings/clip_service.py, sentence_transformer_service.py —
#   per-model embedding latency/count/failures
#   app/services/embeddings/model_manager.py, text_model_manager.py,
#   app/services/model_manager_cross_encoder.py — model-load time (first load only)
#   app/services/reranker_service.py — rerank latency + success/failure
#   app/services/recommendation/recommendation_engine_service.py — request count
#   app/services/duplicate/duplicate_detection_service.py — check count + per-candidate
#   overall_similarity; every service gained an optional metrics_registry parameter
#   tests/services/** — extended with per-service metrics assertions
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: instrument AI services with metrics (Phase 14 milestone 2/6)"

# Milestone 3/6 — worker metrics
#   app/workers/product_worker.py — worker_jobs_total (success/failure) +
#   worker_job_duration_seconds; the queue-state gauges were already covered by
#   MetricsRegistry's Redis polling in Milestone 1
#   tests/workers/test_product_worker.py — extended
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: instrument worker jobs with metrics (Phase 14 milestone 3/6)"

# Milestone 4/6 — Prometheus integration
#   app/application.py — _register_metrics wires prometheus-fastapi-instrumentator
#   behind METRICS__PROMETHEUS_ENABLED, exposes GET /metrics (http_request_* series
#   plus every custom collector), instrumentator middleware outermost
#   app/metrics/metrics_registry.py — short Redis socket timeout so a scrape fast-fails
#   tests/api/test_metrics_endpoint.py — hand-written
#   tests/test_application.py — expected middleware order updated for the new outermost
#   Prometheus middleware
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: expose Prometheus /metrics endpoint (Phase 14 milestone 4/6)"

# Milestone 5/6 — health dashboard
#   app/services/system_health_service.py — SystemHealthService: Redis/Qdrant health,
#   queue depth, active-model count, uptime; read-only + failure-tolerant
#   app/schemas/system.py — SystemHealthResponse/SystemStatsResponse
#   app/api/system.py — GET /system/health, GET /system/stats (always 200)
#   app/application.py — system_router registered behind METRICS__HEALTH_ENDPOINTS_ENABLED
#   app/dependencies/system.py — cached-singleton provider
#   tests/services/test_system_health_service.py, tests/api/test_system.py,
#   tests/dependencies/test_system.py — hand-written
#   tests/test_application.py — extended for the two new business routes
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: add system health dashboard endpoints (Phase 14 milestone 5/6)"

# Milestone 6/6 — test hardening + documentation
#   Coverage audit against the phase's own test-coverage checklist (metrics
#   registration, concurrent updates, health endpoints, Prometheus output, worker
#   metrics, model metrics) — satisfied by Milestones 1-5's own tests
#   backend/README.md — this section, the Phase 14 design-decisions section, and the
#   Roadmap update (Phases 1-14 complete, 15-20 not yet specified)
cd backend
uv run ruff check .
uv run black --check .
uv run mypy .
uv run pytest
cd ..
uv run --project backend pre-commit run --all-files
git add -A
git commit -m "test: harden observability test coverage and document Phase 14 (Phase 14 milestone 6/6)"
git push
```

## Phase 15 — Cross-Encoder Re-ranking & Intelligent Duplicate Verification (built from scratch)

Built *on top of* the existing Phase 11 reranking infrastructure (see the
design-decisions section above for why the spec's requested fresh
`app/services/reranking/` package was intentionally not created).

```bash
# Milestone 1/6 — verification domain + config
#   app/models/verification_reason.py — VerificationReason (code + human message)
#   app/models/duplicate_verification.py — DuplicateVerification (is_duplicate,
#   confidence, cross_encoder_score, retrieval_similarity, matched_product, reasons)
#   app/core/settings.py — DuplicateVerificationSettings (enabled/thresholds/
#   hard gates/blend weights, weights validated to sum to 1.0)
#   app/exceptions/errors.py — added DuplicateVerificationException
#   backend/.env.example — documented the eight new DUPLICATE_VERIFICATION__ vars
#   tests/models/, tests/core/test_settings.py
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: add duplicate verification domain and config (Phase 15 milestone 1/6)"

# Milestone 2/6 — cross-encoder warm-up inference
#   app/services/model_manager_cross_encoder.py — one throwaway inference after
#   first load (inside the lock, exactly once), non-fatal, gated by
#   RERANKER__WARMUP_ENABLED
#   app/core/settings.py — added RerankerSettings.warmup_enabled
#   tests/services/test_model_manager_cross_encoder.py — extended
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: add cross-encoder warm-up inference (Phase 15 milestone 2/6)"

# Milestone 3/6 — reranking pipeline (confidence)
#   app/services/duplicate/duplicate_verification_service.py — composes
#   HybridSearchService + RerankerService: retrieval (reranking off) -> rerank ->
#   cross_encoder_score/retrieval_similarity/threshold-based is_duplicate
#   app/dependencies/duplicate.py — added get_duplicate_verification_service
#   tests/services/duplicate/test_duplicate_verification_service.py,
#   tests/dependencies/test_duplicate.py
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: add duplicate verification reranking pipeline (Phase 15 milestone 3/6)"

# Milestone 4/6 — business-rules verification
#   app/services/duplicate/business_rules_evaluator.py — BusinessRulesEvaluator
#   (brand/category/price/title/attribute overlap -> score + veto + reasons)
#   app/services/duplicate/duplicate_verification_service.py — blends cross-encoder
#   + business score into confidence; hard-gate veto overrides is_duplicate
#   tests/services/duplicate/test_business_rules_evaluator.py + extended verification tests
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: add business-rules duplicate verification (Phase 15 milestone 4/6)"

# Milestone 5/6 — API integration
#   app/services/duplicate/duplicate_check_service.py — returns a unified
#   DuplicateVerification; delegates to verification when enabled, else adapts the
#   weighted DuplicateDecision into that shape
#   app/schemas/duplicate.py — DuplicateCheckResponse gained cross_encoder_score/
#   retrieval_similarity/reasons (backward compatible)
#   app/api/products.py — check-duplicate maps the new fields; added optional price form field
#   tests/services/duplicate/test_duplicate_check_service.py, tests/api/test_check_duplicate.py
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: expose cross-encoder verification in check-duplicate API (Phase 15 milestone 5/6)"

# Milestone 6/6 — metrics + documentation
#   app/metrics/metric_names.py, metrics_registry.py — duplicate_verification_confidence
#   (histogram) + duplicate_verification_decisions_total (counter); recorded by
#   DuplicateVerificationService
#   tests/metrics/test_metrics_registry.py, verification-service metrics tests
#   backend/README.md — this section, the Phase 15 design-decisions section
#   (architecture + sequence diagram + benchmark), and the Roadmap update
#   (Phases 1-15 complete, 16-20 not yet specified)
cd backend
uv run ruff check .
uv run black --check .
uv run mypy .
uv run pytest
cd ..
uv run --project backend pre-commit run --all-files
git add -A
git commit -m "feat: add duplicate-verification metrics and document Phase 15 (Phase 15 milestone 6/6)"
git push
```

## Phase 16 — Explainable AI & Decision Intelligence (built from scratch)

Built *on top of* the existing reason/signal types (see the
design-decisions section above) — the explanation layer maps them, it
never rewrites them.

```bash
# Milestone 1/6 — explanation domain + service
#   app/models/decision_reason.py, decision_weight.py, confidence_breakdown.py,
#   explanation_trace.py — the general explanation domain
#   app/services/explanations/base_explainer.py (generic BaseExplainer[T]),
#   explanation_builder.py (pure weight math + Oxford-comma summaries),
#   explanation_service.py (facade, optional MetricsRegistry)
#   app/schemas/explanation.py — ExplanationResponse; app/dependencies/explanations.py
#   tests/models/, tests/services/explanations/, tests/dependencies/, tests/schemas/
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: add explanation domain and service (Phase 16 milestone 1/6)"

# Milestone 2/6 — search & reranking explanations
#   app/services/explanations/hybrid_search_explainer.py — image/text -> final
#   score contributions; rerank_explainer.py — initial rank -> CE score -> final rank
#   tests/services/explanations/
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: add hybrid-search and reranking explainers (Phase 16 milestone 2/6)"

# Milestone 3/6 — duplicate & recommendation explanations
#   app/services/explanations/duplicate_explainer.py — maps a DuplicateVerification's
#   CE score, retrieval similarity, and business-rule reasons into a trace
#   recommendation_explainer.py — maps shared brand/category/attributes/tags + scores
#   tests/services/explanations/
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: add duplicate and recommendation explainers (Phase 16 milestone 3/6)"

# Milestone 4/6 — decision-trace API
#   app/services/explanations/explanation_service.py — composes all four explainers
#   behind explain_* methods
#   app/services/duplicate/duplicate_check_service.py — decision_to_verification made public
#   app/dependencies/duplicate.py — get_duplicate_detection_service provider
#   app/schemas/explanation.py — TraceBundleResponse/ProductExplanationsResponse
#   app/api/explanations.py — GET /recommendations/{id}/trace, /duplicates/{id}/trace,
#   /products/{id}/explanations
#   app/application.py — explanations_router registered
#   tests/api/test_explanations.py, tests/test_application.py — extended
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: add decision-trace API (Phase 16 milestone 4/6)"

# Milestone 5/6 — explanation metrics
#   app/metrics/metric_names.py, metrics_registry.py — explanation_seconds,
#   explanations_total (per decision_type), explanation_confidence
#   app/services/explanations/explanation_service.py — every explain_* call is timed + recorded
#   tests/metrics/, tests/services/explanations/
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: add explanation metrics (Phase 16 milestone 5/6)"

# Milestone 6/6 — tests + documentation
#   Coverage audit; backend/README.md — this section, the Phase 16 design-decisions
#   section (architecture + decision flow + sequence), and the Roadmap update
#   (Phases 1-16 complete, 17-20 not yet specified)
cd backend
uv run ruff check .
uv run black --check .
uv run mypy .
uv run pytest
cd ..
uv run --project backend pre-commit run --all-files
git add -A
git commit -m "test: harden explanation coverage and document Phase 16 (Phase 16 milestone 6/6)"
git push
```

## Phase 17 — Pricing Intelligence Engine (built from scratch)

```bash
# Milestone 1/6 — pricing domain + config
#   app/core/constants.py — PricingStrategy enum
#   app/models/price_confidence.py, comparable_product.py, price_estimate.py
#   app/core/settings.py — PricingSettings; app/exceptions/errors.py — PricingException
#   app/schemas/pricing.py — PricingRequest/PricingResponse
#   backend/.env.example — PRICING__ variables; tests/models/, tests/schemas/, tests/core/
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: add pricing domain and config (Phase 17 milestone 1/6)"

# Milestone 2/6 — price normalizer + estimator
#   app/services/pricing/price_normalizer.py — extracts positively-priced comparables
#   price_estimator.py — weighted average / trimmed mean / median + count-based confidence
#   base_pricing_service.py — the interface; tests/services/pricing/
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: add price normalizer and estimator (Phase 17 milestone 2/6)"

# Milestone 3/6 — comparable retrieval
#   app/services/pricing/pricing_engine.py — reuses HybridSearchService.search /
#   search_by_product_id, normalizes, estimates; app/dependencies/pricing.py
#   tests/services/pricing/, tests/dependencies/
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: add pricing engine comparable retrieval (Phase 17 milestone 3/6)"

# Milestone 4/6 — pricing algorithms
#   app/services/pricing/price_estimator.py — IQR outlier removal + spread-aware
#   confidence (count x price agreement); tests/services/pricing/
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: add outlier removal and spread-aware confidence (Phase 17 milestone 4/6)"

# Milestone 5/6 — pricing API
#   app/api/pricing.py — POST /pricing/estimate, GET /pricing/{product_id}
#   app/application.py — pricing_router registered behind PRICING__ENABLED
#   tests/api/test_pricing.py, tests/test_application.py
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: add pricing API (Phase 17 milestone 5/6)"

# Milestone 6/6 — metrics + documentation
#   app/metrics/metric_names.py, metrics_registry.py — pricing_seconds,
#   pricing_estimates_total (per confidence band), pricing_confidence
#   app/services/pricing/pricing_engine.py — records pricing metrics
#   backend/README.md — this section, the Phase 17 design-decisions section
#   (architecture + algorithms + benchmark), and the Roadmap update
cd backend
uv run ruff check .
uv run black --check .
uv run mypy .
uv run pytest
cd ..
uv run --project backend pre-commit run --all-files
git add -A
git commit -m "feat: add pricing metrics and document Phase 17 (Phase 17 milestone 6/6)"
git push
```

## Phase 18 — Analytics & Business Intelligence Platform (built from scratch)

Redis-only persistence (no database) for historical daily buckets — see
the design-decisions section above.

```bash
# Milestone 1/6 — analytics domain
#   app/models/analytics_event.py (enum), usage_metrics.py, analytics_report.py
#   (AnalyticsReport/DashboardSummary/TrendReport/TrendPoint); tests/models/
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: add analytics domain (Phase 18 milestone 1/6)"

# Milestone 2/6 — analytics engine + Redis daily buckets
#   app/repositories/analytics_repository.py — per-day counters + latency sum/count,
#   TTL'd, fail-soft recording
#   app/services/analytics/analytics_engine.py — usage/dashboard/report aggregation
#   app/core/settings.py — AnalyticsSettings; app/dependencies/analytics.py
#   app/api/products.py, search.py, app/workers/product_worker.py — record events/latency
#   tests/repositories/, tests/services/analytics/, tests/core/
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: add analytics engine and Redis daily buckets (Phase 18 milestone 2/6)"

# Milestone 3/6 — model analytics
#   app/models/model_analytics.py; app/services/analytics/analytics_engine.py —
#   model_analytics() reads active version + registered count per type from ModelRegistry
#   tests/models/, tests/services/analytics/
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: add model analytics (Phase 18 milestone 3/6)"

# Milestone 4/6 — dashboard APIs
#   app/schemas/analytics.py; app/api/analytics.py — GET /analytics/dashboard,
#   /analytics/models, /analytics/pipeline; app/application.py — analytics_router
#   behind ANALYTICS__ENABLED; tests/api/test_analytics.py, tests/test_application.py
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: add analytics dashboard API (Phase 18 milestone 4/6)"

# Milestone 5/6 — trend reports + export
#   app/core/constants.py — TrendGranularity/ExportFormat enums
#   app/services/analytics/analytics_engine.py — trend(); trend_exporter.py — Markdown
#   app/api/analytics.py — GET /analytics/trends (JSON | Markdown)
#   tests/services/analytics/, tests/api/
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: add trend reports and export (Phase 18 milestone 5/6)"

# Milestone 6/6 — tests + documentation
#   Coverage audit; backend/.env.example — ANALYTICS__ variables
#   backend/README.md — this section, the Phase 18 design-decisions section, and the
#   Roadmap update (Phases 1-18 complete, 19-20 not yet specified)
cd backend
uv run ruff check .
uv run black --check .
uv run mypy .
uv run pytest
cd ..
uv run --project backend pre-commit run --all-files
git add -A
git commit -m "test: harden analytics coverage and document Phase 18 (Phase 18 milestone 6/6)"
git push
```

## Phase 19 — Enterprise Platform Features (built from scratch)

An opt-in enterprise layer (ENTERPRISE__ENABLED, default off) — additive,
Redis-backed, no rewrite of any completed phase (see the design-decisions
section above).

```bash
# Milestone 1/6 — organization domain
#   app/models/role.py (Role/Permission + ROLE_PERMISSIONS), organization.py
#   (Organization/Tenant), api_key.py (ApiKey/ApiKeyCreation), audit_event.py
#   app/core/settings.py — EnterpriseSettings; app/exceptions/errors.py —
#   AuthenticationException(401)/AuthorizationException(403)/QuotaExceededException(429)
#   backend/.env.example — ENTERPRISE__ variables; tests/models/, tests/core/
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: add enterprise organization domain (Phase 19 milestone 1/6)"

# Milestone 2/6 — API-key auth + RBAC
#   app/services/enterprise/api_keys.py (generate/hash/verify), authentication_service.py
#   app/models/auth_context.py; app/repositories/organization_repository.py,
#   api_key_repository.py (Redis, indexed by prefix)
#   app/dependencies/enterprise.py — require_permission RBAC guard (401/403)
#   tests/services/enterprise/, tests/repositories/, tests/dependencies/
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: add API-key authentication and RBAC (Phase 19 milestone 2/6)"

# Milestone 3/6 — tenant isolation mechanism
#   app/services/enterprise/tenant_scope.py — tenant-scoped Qdrant collection names +
#   Redis namespaces derived from the tenant; tests/services/enterprise/
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: add tenant isolation mechanism (Phase 19 milestone 3/6)"

# Milestone 4/6 — audit logging + quotas
#   app/repositories/audit_repository.py (per-tenant append-only log),
#   quota_repository.py (per-day + per-minute counters)
#   app/dependencies/enterprise.py — shared get_auth_context + enforce_quota (429)
#   tests/repositories/, tests/dependencies/
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: add audit logging and quotas (Phase 19 milestone 4/6)"

# Milestone 5/6 — enterprise management API
#   app/schemas/enterprise.py; app/api/enterprise.py — /organizations (bootstrap),
#   /api-keys (create/list/revoke, no privilege escalation, audit-logged), /audit, /usage
#   app/application.py — enterprise_router registered behind ENTERPRISE__ENABLED
#   tests/api/test_enterprise.py
cd backend && uv run ruff check . && uv run black --check . && uv run mypy . && uv run pytest && cd ..
git add -A
git commit -m "feat: add enterprise management API (Phase 19 milestone 5/6)"

# Milestone 6/6 — tests, security review, documentation
#   Coverage audit; backend/README.md — this section, the Phase 19 design-decisions
#   section (architecture + API-key security + RBAC + tenant isolation + security review),
#   and the Roadmap update (Phases 1-19 complete, 20 not yet specified)
cd backend
uv run ruff check .
uv run black --check .
uv run mypy .
uv run pytest
cd ..
uv run --project backend pre-commit run --all-files
git add -A
git commit -m "test: harden enterprise coverage and document Phase 19 (Phase 19 milestone 6/6)"
git push
```

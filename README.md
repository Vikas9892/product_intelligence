# Multi-Modal Product Intelligence Engine

A production-grade AI application for ingesting, understanding, and searching
product catalogs across text and images — combining embeddings, vector
search, LLM-generated metadata, duplicate detection, and pricing
intelligence behind a FastAPI backend.

This repository is built incrementally across 13 phases, each shipped as a
reviewable milestone rather than a single monolithic drop.

## Roadmap

| Phase | Focus |
|------:|-------|
| 0  | Planning |
| 1  | Backend skeleton (complete) |
| 2  | Product ingestion — 2A (upload pipeline) + 2B (processing/normalization) complete |
| **3**  | **Image processing — complete, this milestone** |
| 4  | Text embeddings |
| 5  | Image embeddings |
| 6  | Vector database |
| 7  | Hybrid search |
| 8  | LLM metadata generation |
| 9  | Duplicate detection |
| 10 | Pricing intelligence |
| 11 | Frontend |
| 12 | Production features |
| 13 | Deployment |

## Repository layout

```
.
├── backend/                # FastAPI service — see backend/README.md
├── .github/workflows/ci.yml # GitHub Actions: ruff, black --check, mypy, pytest
├── .pre-commit-config.yaml # Repo-wide git hooks (ruff, black, mypy, hygiene)
├── .editorconfig           # Repo-wide editor formatting rules
├── Makefile                # make install / run / lint / format / test / clean
└── README.md                # You are here
```

Future phases add sibling directories at this level (e.g. `frontend/` in
Phase 11, `infra/` in Phase 13) without disturbing `backend/`.

## Getting started

See [`backend/README.md`](backend/README.md) for full backend setup,
tooling, and development workflow instructions. From the repo root:

```bash
make install   # uv sync + pre-commit install
make lint      # ruff check
make format    # ruff format + black
make typecheck # mypy
make test      # pytest with coverage
```

`make run` starts `uvicorn app.main:app --reload`, serving `/health`,
`/ready`, `/version`, and `POST /api/v1/products/upload` (now including
Phase 3's image standardization).

## Status

Phases 1 and 2 (Backend Foundation, Product Ingestion) are complete, and
Phase 3 (Image Processing) has now landed too:

- **Milestone 1 — Backend Skeleton**: project structure, dependency
  management (`uv`), linting/formatting/type-checking, testing, and
  pre-commit are configured.
- **Milestone 2 — Configuration Management**: typed, validated settings
  (`app/core/{constants,paths,settings,config}.py`) grouped by concern,
  loaded from `.env`, with production-safety validation and a cached
  singleton.
- **Milestone 3 — Logging**: centralized logging (`app/core/logging.py`)
  — level read from settings, one console handler, a consistent
  formatter, and `get_logger(name)` for any module to use.
- **Milestone 4 — FastAPI Application Factory**: `create_app()`
  (`app/application.py`) + a `lifespan` (`app/lifespan.py`) that logs
  startup/shutdown and provisions runtime directories; `app/main.py` is
  the ASGI entrypoint.
- **Milestone 5 — Health & System Endpoints**: `GET /health`, `/ready`,
  `/version` (`app/api/health.py`), deliberately unversioned and outside
  `settings.application.api_prefix`.
- **Milestone 6 — Global Exception Handling**: an `AppException` hierarchy
  (`app/exceptions/`) and global handlers so every error — domain-raised,
  request-validation, plain `HTTPException`, or an unhandled bug — returns
  the same `{"success", "error": {"code", "message", "details"}}` envelope.
- **Milestone 7 — Middleware**: request ID/correlation, timing, request
  logging, security headers (`app/middleware/`), plus CORS, GZip, and
  TrustedHost, registered in a deliberately documented order
  (`app/application.py::_register_middleware`).
- **Milestone 8 — Testing & CI Foundation**: shared pytest fixtures
  (`tests/conftest.py`) and a GitHub Actions workflow
  (`.github/workflows/ci.yml`) running ruff, black --check, mypy, and
  pytest on every push/PR to `main`.
- **Phase 2A — Product Upload Pipeline**: `POST /api/v1/products/upload`
  (`app/api/products.py`) accepts product metadata plus an image file,
  validates it (extension, MIME type, size) via `UploadService`
  (`app/services/upload_service.py`), and stores it under the runtime
  upload directory `app/core/paths.py` established in Phase 1 — no
  database write yet.
- **Phase 2B — Product Processing & Metadata Normalization**: six
  milestones building the pipeline from a stored upload to a processed
  `Product`: a reusable `ChecksumService` (SHA-256), an internal
  `FileMetadata` parser, extracted `app/validators/` (file + product),
  the internal `Product` domain model (`app/models/product.py`,
  deliberately separate from the API schemas), and `ProductService`
  (`app/services/product_service.py`) orchestrating checksum + metadata +
  normalization + validation + UUID4 generation — now wired into the
  upload endpoint. Still no database write.
- **Phase 3 — Image Processing Pipeline**: the first AI-facing work.
  `ImageValidator` (`app/validators/image_validator.py`) verifies an
  upload is a genuine, undamaged, appropriately-sized image (Pillow's
  `verify()` + a full reopen/decode — never trusting the file extension);
  `ImageProcessingService` (`app/services/image_processing_service.py`)
  then applies EXIF orientation, converts to RGB (flattening any
  transparency onto white), resizes (downscale-only, preserving aspect
  ratio), and saves a standardized JPEG under a new `storage/processed/`
  directory, returning an internal `ImageMetadata`
  (`app/models/image_metadata.py`) — now the middle stage of
  `ProductService`'s pipeline, between checksum computation and field
  normalization. Still no database write, no embeddings, no AI model
  calls.

208 unit/integration tests, 99% coverage on `app/`.

No database persistence, embeddings, or AI/search code exists yet by
design — see [`backend/README.md`](backend/README.md) for the full
rationale and every design decision behind the phases above.

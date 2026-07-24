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
| **1**  | **Backend skeleton (this milestone)** |
| 2  | Product ingestion |
| 3  | Image processing |
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
`/ready`, and `/version` (Milestone 5) — no business endpoints yet.

## Status

Phase 1 (Backend Foundation) is complete:

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

75 unit tests, 99% coverage on `app/`.

No database models or AI code exist yet by design — see
[`backend/README.md`](backend/README.md) for the full rationale and every
design decision behind the milestones above.

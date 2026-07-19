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

`make run` will start the API server once Milestone 4 (FastAPI App) adds an
application entrypoint — there is intentionally no `app.main:app` yet.

## Status

- **Milestone 1 — Backend Skeleton**: project structure, dependency
  management (`uv`), linting/formatting/type-checking, testing, and
  pre-commit are configured.
- **Milestone 2 — Configuration Management**: typed, validated settings
  (`app/core/{constants,paths,settings,config}.py`) grouped by concern,
  loaded from `.env`, with production-safety validation and a cached
  singleton. 19 unit tests, 99% coverage on `app/core`.

No API endpoints, database models, or AI code exist yet by design — see
[`backend/README.md`](backend/README.md) for the full rationale.

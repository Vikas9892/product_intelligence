# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project follows
[Semantic Versioning](https://semver.org/).

> [!NOTE]
> These entries track **development milestones** by implementation phase, not tagged public releases. The packaged version string in `pyproject.toml` is currently `0.1.0`; it will be bumped to `1.0.0` when the feature-complete milestone below is formally released. No dates are attached because the phases were not individually tagged.

---

## [1.0.0] — Feature-complete (in preparation)

Consolidation of Phases 1–19 into a documented, feature-complete backend: multi-modal
ingestion, hybrid search, recommendations, duplicate detection, deterministic pricing,
explainability, analytics, and an opt-in enterprise layer — all fully typed and covered
by 1327 tests at 99% branch coverage.

### Added
- Complete project documentation set: `README.md`, `ARCHITECTURE.md`, `DEPLOYMENT.md`,
  `DEMO.md`, `CHANGELOG.md`, `CONTRIBUTING.md`.

### Notes
- No relational database, containerization, CI/CD, or cloud deployment is included yet;
  these are tracked as the remaining production-deployment work (see `DEPLOYMENT.md`).

---

## Phase history (0.x milestones)

### [0.19.0] — Enterprise platform features
- Opt-in multi-tenancy layer (`ENTERPRISE__ENABLED`, off by default).
- API-key authentication (`pik_` tokens, SHA-256 at rest, constant-time verification).
- RBAC with `owner`/`admin`/`member`/`viewer` roles and no privilege escalation.
- Tenant isolation via per-tenant namespacing of Qdrant collections and Redis keys.
- Per-tenant audit logging and daily/per-minute usage quotas.
- Endpoints: organizations, API keys, audit, usage.

### [0.18.0] — Analytics & business intelligence
- REST analytics over Redis daily buckets (fail-soft recording).
- Windowed usage metrics, dashboard snapshot, pipeline aggregates, and trend reports.
- Endpoints: `/analytics/{dashboard,models,pipeline,trends}`.

### [0.17.0] — Pricing intelligence
- Deterministic fair-price estimation reusing the retrieval pipeline.
- Strategies: trimmed mean (default), weighted average, median.
- IQR (Tukey-fence) outlier removal and confidence gating on comparable count.
- Endpoints: `POST /pricing/estimate`, `GET /pricing/{product_id}`.

### [0.16.0] — Explainable AI & decision intelligence
- `ExplanationService` facade over per-subject explainers.
- Structured decision traces for recommendations, duplicates, and rankings.
- Endpoints: recommendation/duplicate traces and product explanations.

### [0.15.0] — Cross-encoder duplicate verification
- On-demand, explainable duplicate verification (retrieval → cross-encoder → business rules).
- Separates the cross-encoder signal from raw retrieval similarity, with reasons.
- Opt-in (`DUPLICATE_VERIFICATION__ENABLED`), powering a richer `POST /products/check-duplicate`.

### [0.14.0] — Metrics & observability
- `MetricsRegistry` with idempotent Prometheus collectors under a configurable namespace.
- Latency/count metrics across upload, embedding, rerank, worker, pricing, and explanations.
- `GET /metrics` (via instrumentator) and operational `GET /system/health`, `/system/stats`.

### [0.13.0] — Model registry
- Metadata registry tracking the active model version per model type.
- Startup validation of configured model names; embedding/reranker services resolve
  their default model name through the registry.
- Endpoints: `GET /models`, `/models/{type}`, `/models/{type}/active`.

### [0.12.0] — Async processing pipeline
- Redis-backed job queue with retry, backoff, and dead-letter handling.
- Standalone worker pool (`scripts/run_workers.py`) with graceful shutdown.
- Uploads return `202 Accepted`; idempotent, retry-safe job processing.
- Recommendation cache warmed by the worker after processing.
- Endpoints: `GET /jobs/{job_id}`, `GET /jobs/dead-letter`, product status.

### [0.11.0] — Cross-encoder reranking
- Optional cross-encoder reranking of top retrieval candidates (`RERANKER__ENABLED`).
- Reused across search, recommendations, duplicate verification, and pricing.

### [0.10.0] — Retrieval evaluation
- Retrieval quality metrics and benchmark reports over an evaluation dataset.
- Endpoints: `POST /evaluation/run`, `POST /evaluation/compare-reranking`.

### [0.9.0] — Recommendation engine
- Similar-product recommendations: retrieval + multi-signal scoring + brand diversity.
- Configurable score weights (similarity, attribute, tag, catalog quality).
- Endpoint: `GET /products/{id}/recommendations`.

### [0.8.0] — Duplicate detection
- Upload-time weighted-similarity duplicate detection.
- Modes: `OFF`, `WARN`, `BLOCK` (blocks likely duplicates before persistence, `409`).

### [0.7.0] — Catalog intelligence
- Per-upload enrichment: attribute extraction, tag generation, and a quality score.
- Confidence-thresholded predictions feed vector-store metadata.

### [0.6.0] — Text embeddings & hybrid search
- BGE text embeddings (384-d) and a `product_text` Qdrant collection.
- `HybridSearchService` fusing image and text scores (`0.7`/`0.3` by default).

### [0.5.0] — Vector store
- Qdrant integration and the `product_images` collection (cosine, 512-d).
- Image-only semantic search over indexed products.

### [0.4.0] — Image embeddings
- CLIP image embeddings (512-d) generated during upload processing.

### [0.3.0] — Image processing
- Image standardization: orientation, color mode, and resizing.
- Decompression-bomb protection and dimension/size guards.

### [0.2.0] — Product ingestion
- Upload service (file validation and storage) and product processing service.
- Checksums, field normalization, and validation.

### [0.1.0] — Backend foundation
- FastAPI application factory, lifespan, and configuration/logging infrastructure.
- Health/readiness/version endpoints, global exception handling, and the middleware stack.

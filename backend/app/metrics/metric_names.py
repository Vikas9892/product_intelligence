"""Metric name constants (Phase 14).

Bare suffixes only — `MetricsRegistry` prepends `settings.metrics.namespace`
(`prometheus_client`'s own `namespace=` argument) to every one of these,
so `PRODUCT_UPLOAD_SECONDS` becomes the exposed series
`product_intelligence_product_upload_seconds`. Kept as constants (not
inlined string literals in `metrics_registry.py`) so a metric's name is
defined exactly once and referenced, never retyped, everywhere it's
used — the same reasoning `app.core.constants` already applies project-wide.

The seven names commented "Milestone 4" are this phase's own explicitly
required metric names; everything else fills in the rest of Milestones
1-3's own tracking requirements (model load time, inference counts,
duplicate-comparison similarity, ...) using the same naming convention.
"""

# --- Milestone 4: explicitly required metric names ---
PRODUCT_UPLOAD_SECONDS = "product_upload_seconds"
EMBEDDING_LATENCY_SECONDS = "embedding_latency_seconds"
RERANK_LATENCY_SECONDS = "rerank_latency_seconds"
QUEUE_DEPTH = "queue_depth"
WORKER_JOBS_TOTAL = "worker_jobs_total"
DUPLICATE_DETECTION_TOTAL = "duplicate_detection_total"
RECOMMENDATION_REQUESTS_TOTAL = "recommendation_requests_total"

# --- Milestone 1-2: AI inference/model-loading metrics ---
EMBEDDING_INFERENCE_TOTAL = "embedding_inference_total"
RERANK_INFERENCE_TOTAL = "rerank_inference_total"
MODEL_LOAD_SECONDS = "model_load_seconds"
DUPLICATE_SIMILARITY_SCORE = "duplicate_similarity_score"

# --- Milestone 3: worker/queue state metrics ---
WORKER_JOB_DURATION_SECONDS = "worker_job_duration_seconds"
WORKER_JOBS_RUNNING = "worker_jobs_running"
WORKER_DEAD_LETTER_SIZE = "worker_dead_letter_size"

# --- Phase 15: cross-encoder duplicate verification metrics ---
DUPLICATE_VERIFICATION_CONFIDENCE = "duplicate_verification_confidence"
DUPLICATE_VERIFICATION_DECISIONS_TOTAL = "duplicate_verification_decisions_total"

# --- Phase 16: explainable-AI metrics ---
EXPLANATION_SECONDS = "explanation_seconds"
EXPLANATIONS_TOTAL = "explanations_total"
EXPLANATION_CONFIDENCE = "explanation_confidence"

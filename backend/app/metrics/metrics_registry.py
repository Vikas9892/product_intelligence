"""`MetricsRegistry`: the process-wide collection of every metric this codebase records (Phase 14).

Bare-constructed the same way every other cross-cutting sub-service in
this codebase is (`ModelRegistry()`, `HybridSearchService()`, ...) —
every instrumented service (`CLIPEmbeddingService`,
`SentenceTransformerEmbeddingService`, `CrossEncoderService`,
`RerankerService`, `RecommendationEngineService`,
`DuplicateDetectionService`, `ProductService`, `ProductWorker`, the three
`*ModelManager`s) accepts an optional `metrics_registry:
MetricsRegistry | None` constructor parameter, defaulting to a bare
`MetricsRegistry()` when not injected. `app.metrics.base_metrics`'s
idempotent collector factories are what make constructing this class
more than once per process safe (every `create_app()` call in the test
suite does exactly that) — the *first* construction registers real
collectors into `prometheus_client`'s process-wide default `REGISTRY`
(the one `GET /metrics` exposes); every later one finds and reuses the
same collector objects rather than raising `ValueError: Duplicated
timeseries`.

**Master switch.** Every `record_*`/`observe_*` method checks
`self._enabled` (`METRICS__ENABLED`) first and no-ops if it's `False` —
one flag, checked once per call, rather than every one of the dozen-plus
call sites across the codebase re-reading `settings.metrics.enabled`
itself.

**Queue/worker state gauges are polled, not pushed.** `queue_depth`,
`worker_jobs_running`, and `worker_dead_letter_size` reflect *current*
Redis state (how many jobs are pending/in-flight/dead-lettered right
now) — rather than incrementing/decrementing a running counter from
inside `RedisQueue`/`QueueManager` (which would mean this "independent
observability layer" the phase asks for reaching into the job-queue's
own business logic, and would drift out of sync with reality after any
crash/restart), each of these three `Gauge`s is wired via
`set_function()` to a small, synchronous, independent Redis connection
that re-reads the actual list/hash length fresh every time `GET
/metrics` is scraped. This module only reads `settings.async_pipeline`'s
already-public `redis_url`/`queue_name` (configuration, exactly the same
category of dependency `ModelRegistry` already has on
`settings.ai_models`/`settings.reranker`) — it never imports `RedisQueue`,
`QueueManager`, or `ProductWorker` themselves. A polling function that
fails (Redis unreachable) returns `0.0` rather than raising — a `/metrics`
scrape must never itself become a source of 500s.
"""

from typing import Protocol

import redis as sync_redis
from prometheus_client import REGISTRY, CollectorRegistry

from app.core.config import settings
from app.core.logging import get_logger
from app.metrics import metric_names
from app.metrics.base_metrics import (
    get_or_create_counter,
    get_or_create_gauge,
    get_or_create_histogram,
)

logger = get_logger(__name__)


class _SyncRedisLike(Protocol):
    """What `_poll_queue_length` actually depends on — not the full `redis.Redis` surface —
    so tests can supply a lightweight fake instead of a real connection."""

    def llen(self, name: str) -> int:
        raise NotImplementedError

    def hlen(self, name: str) -> int:
        raise NotImplementedError


class MetricsRegistry:
    """Owns every Prometheus collector this codebase records metrics into."""

    def __init__(
        self,
        *,
        enabled: bool | None = None,
        namespace: str | None = None,
        registry: CollectorRegistry = REGISTRY,
        sync_redis_client: _SyncRedisLike | None = None,
    ) -> None:
        self._enabled = enabled if enabled is not None else settings.metrics.enabled
        self._namespace = namespace if namespace is not None else settings.metrics.namespace
        self._registry = registry
        #: One lazily-used synchronous Redis connection, kept open and
        #: reused across every scrape (rather than reconnecting on every
        #: `set_function` call) — see `_poll_queue_length`. Short socket
        #: timeouts bound how long a single `/metrics` scrape can block
        #: when Redis is unreachable: a scrape must fail fast (and report
        #: `0.0` for the gauges), never hang the scraper for seconds
        #: retrying a dead connection.
        self._sync_redis_client = (
            sync_redis_client
            if sync_redis_client is not None
            else sync_redis.Redis.from_url(
                settings.async_pipeline.redis_url,
                socket_connect_timeout=0.25,
                socket_timeout=0.25,
            )
        )

        self.product_upload_seconds = get_or_create_histogram(
            metric_names.PRODUCT_UPLOAD_SECONDS,
            "Time to process one uploaded product (ProductService.process_upload).",
            namespace=self._namespace,
            registry=self._registry,
        )
        self.embedding_latency_seconds = get_or_create_histogram(
            metric_names.EMBEDDING_LATENCY_SECONDS,
            "Time to generate embeddings for one batch, per model.",
            ["model"],
            namespace=self._namespace,
            registry=self._registry,
        )
        self.embedding_inference_total = get_or_create_counter(
            metric_names.EMBEDDING_INFERENCE_TOTAL,
            "Embedding inference calls, per model and outcome.",
            ["model", "status"],
            namespace=self._namespace,
            registry=self._registry,
        )
        self.model_load_seconds = get_or_create_histogram(
            metric_names.MODEL_LOAD_SECONDS,
            "Time to load a model onto its device (first use only), per model type.",
            ["model_type"],
            namespace=self._namespace,
            registry=self._registry,
        )
        self.rerank_latency_seconds = get_or_create_histogram(
            metric_names.RERANK_LATENCY_SECONDS,
            "Time to rerank one candidate pool (RerankerService.rerank).",
            namespace=self._namespace,
            registry=self._registry,
        )
        self.rerank_inference_total = get_or_create_counter(
            metric_names.RERANK_INFERENCE_TOTAL,
            "Cross-encoder reranking calls, per outcome.",
            ["status"],
            namespace=self._namespace,
            registry=self._registry,
        )
        self.recommendation_requests_total = get_or_create_counter(
            metric_names.RECOMMENDATION_REQUESTS_TOTAL,
            "Recommendation requests handled.",
            namespace=self._namespace,
            registry=self._registry,
        )
        self.duplicate_detection_total = get_or_create_counter(
            metric_names.DUPLICATE_DETECTION_TOTAL,
            "Duplicate-detection checks run.",
            namespace=self._namespace,
            registry=self._registry,
        )
        self.duplicate_similarity_score = get_or_create_histogram(
            metric_names.DUPLICATE_SIMILARITY_SCORE,
            "overall_similarity of each candidate compared during duplicate detection.",
            namespace=self._namespace,
            registry=self._registry,
        )
        self.worker_jobs_total = get_or_create_counter(
            metric_names.WORKER_JOBS_TOTAL,
            "Background jobs processed by a worker, per outcome.",
            ["status"],
            namespace=self._namespace,
            registry=self._registry,
        )
        self.worker_job_duration_seconds = get_or_create_histogram(
            metric_names.WORKER_JOB_DURATION_SECONDS,
            "Time a worker spent on one job attempt.",
            namespace=self._namespace,
            registry=self._registry,
        )
        self.queue_depth = get_or_create_gauge(
            metric_names.QUEUE_DEPTH,
            "Jobs currently waiting to be dequeued.",
            namespace=self._namespace,
            registry=self._registry,
        )
        self.worker_jobs_running = get_or_create_gauge(
            metric_names.WORKER_JOBS_RUNNING,
            "Jobs currently checked out by a worker (in-flight).",
            namespace=self._namespace,
            registry=self._registry,
        )
        self.worker_dead_letter_size = get_or_create_gauge(
            metric_names.WORKER_DEAD_LETTER_SIZE,
            "Jobs currently sitting in the dead-letter queue.",
            namespace=self._namespace,
            registry=self._registry,
        )
        self.duplicate_verification_confidence = get_or_create_histogram(
            metric_names.DUPLICATE_VERIFICATION_CONFIDENCE,
            "Cross-encoder confidence of the best candidate per duplicate-verification check.",
            namespace=self._namespace,
            registry=self._registry,
        )
        self.duplicate_verification_decisions_total = get_or_create_counter(
            metric_names.DUPLICATE_VERIFICATION_DECISIONS_TOTAL,
            "Duplicate-verification decisions, per outcome.",
            ["decision"],
            namespace=self._namespace,
            registry=self._registry,
        )

        self.queue_depth.set_function(lambda: self._poll_queue_length("pending", llen=True))
        self.worker_jobs_running.set_function(
            lambda: self._poll_queue_length("processing", llen=False)
        )
        self.worker_dead_letter_size.set_function(
            lambda: self._poll_queue_length("dead_letter", llen=True)
        )

    def observe_embedding(self, *, model: str, seconds: float, success: bool) -> None:
        """Record one embedding-generation batch's latency and outcome, for `model`."""
        if not self._enabled:
            return
        self.embedding_latency_seconds.labels(model=model).observe(seconds)
        self.embedding_inference_total.labels(
            model=model, status="success" if success else "failure"
        ).inc()

    def observe_model_load(self, *, model_type: str, seconds: float) -> None:
        """Record how long an actual (first-use) model load took, for `model_type`."""
        if not self._enabled:
            return
        self.model_load_seconds.labels(model_type=model_type).observe(seconds)

    def observe_rerank(self, *, seconds: float, success: bool) -> None:
        """Record one `RerankerService.rerank` call's latency and outcome."""
        if not self._enabled:
            return
        self.rerank_latency_seconds.observe(seconds)
        self.rerank_inference_total.labels(status="success" if success else "failure").inc()

    def record_recommendation_request(self) -> None:
        """Record one `RecommendationEngineService.recommend` call."""
        if not self._enabled:
            return
        self.recommendation_requests_total.inc()

    def record_duplicate_detection(self, *, similarity_scores: list[float]) -> None:
        """Record one duplicate-detection check and each candidate's `overall_similarity`."""
        if not self._enabled:
            return
        self.duplicate_detection_total.inc()
        for score in similarity_scores:
            self.duplicate_similarity_score.observe(score)

    def observe_product_upload(self, seconds: float) -> None:
        """Record one `ProductService.process_upload` call's total duration."""
        if not self._enabled:
            return
        self.product_upload_seconds.observe(seconds)

    def record_worker_job(self, *, status: str, seconds: float) -> None:
        """Record one worker job attempt's outcome (`"success"`/`"failure"`) and duration."""
        if not self._enabled:
            return
        self.worker_jobs_total.labels(status=status).inc()
        self.worker_job_duration_seconds.observe(seconds)

    def record_duplicate_verification(
        self, *, confidence: float | None, is_duplicate: bool
    ) -> None:
        """Record one duplicate-verification check's cross-encoder confidence and decision (Phase 15).

        `confidence` is the best candidate's cross-encoder score — `None`
        when no candidate was retrieved to score (the confidence
        histogram then gets no sample, but the decision is still counted).
        """
        if not self._enabled:
            return
        if confidence is not None:
            self.duplicate_verification_confidence.observe(confidence)
        self.duplicate_verification_decisions_total.labels(
            decision="duplicate" if is_duplicate else "not_duplicate"
        ).inc()

    def _poll_queue_length(self, key_suffix: str, *, llen: bool) -> float:
        """Synchronously read the current length of `{queue_name}:{key_suffix}` from Redis.

        `llen=True` for the list-shaped `pending`/`dead_letter` keys;
        `llen=False` for the hash-shaped `processing` key (`HLEN`) — see
        `RedisQueue`'s own docstring for what each Redis key holds. Never
        raises: a scrape must succeed even if Redis is unreachable, the
        same "never raises" reasoning `QdrantVectorStore.health()`
        already establishes.
        """
        try:
            key = f"{settings.async_pipeline.queue_name}:{key_suffix}"
            length = (
                self._sync_redis_client.llen(key) if llen else self._sync_redis_client.hlen(key)
            )
            return float(length)
        except Exception:
            logger.warning("Failed to poll queue length for gauge: key_suffix=%s", key_suffix)
            return 0.0

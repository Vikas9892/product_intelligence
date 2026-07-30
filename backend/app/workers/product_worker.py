"""`ProductWorker`: dequeues and processes `PRODUCT_PROCESSING` jobs (Phase 12).

Pipeline, per the phase spec's own diagram: Receive Job -> [Image
Processing -> Image Embeddings -> Text Embeddings -> Catalog
Intelligence -> Vector Indexing -> Duplicate Detection] (all inside one
call to `ProductService.process_upload` — see "Why one opaque call?"
below) -> Recommendation Generation (this worker's own step, warming
`RecommendationCacheRepository`) -> Done.

**Why one opaque call to `ProductService.process_upload`, not six
separate stage calls?** This phase's own requirement is to extend the
architecture "without modifying existing business services" —
`ProductService` already owns exactly this sequence (see its own
docstring), and reaching into its private sub-services
(`_image_processing_service`, `_embedding_service`, ...) from outside
would break the same encapsulation `HybridSearchService`'s own docstring
already warns against for its own private sub-services. The trade-off:
`Job.progress`/`current_stage` are coarse (a handful of checkpoints
around the one call), not a live per-stage percentage — an honest
consequence of preserving that boundary, not an oversight.

**Idempotency.** A job is created with one `product_id` and never
regenerates it across retries (see `ProductService.process_upload`'s own
docstring for why `ProductWorker` always passes the job's own
`product_id` through). Every write this pipeline makes is a Qdrant
*upsert* keyed by that same ID, so reprocessing the same job converges
to the same final state rather than creating duplicate indexed points.

**Retries/backoff.** A failed attempt calls `QueueManager.retry`, which
owns the actual backoff/dead-letter decision (see `RedisQueue`'s own
docstring) — this class only decides *that* a failure happened, never
how many times to retry or how long to wait.

**Never logs job payloads or embeddings** — only IDs, stages, and
counts, matching this phase's own logging requirement.
"""

import time
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.core.logging import get_logger
from app.jobs.base_job import Job
from app.jobs.job_result import JobResult
from app.jobs.job_status import JobStatus
from app.jobs.job_types import JobType
from app.metrics.metrics_registry import MetricsRegistry
from app.models.recommendation_type import RecommendationType
from app.queue.queue_manager import QueueManager
from app.repositories.analytics_repository import AnalyticsRepository
from app.repositories.recommendation_cache_repository import RecommendationCacheRepository
from app.schemas.product import ProductCreate, ProductImage
from app.services.product_service import ProductService
from app.services.recommendation.recommendation_engine_service import RecommendationEngineService

logger = get_logger(__name__)

_STAGE_VALIDATING = "Validating Upload"
_STAGE_PROCESSING = "Processing Upload"
_STAGE_CACHING_RECOMMENDATIONS = "Generating Recommendations"
_STAGE_COMPLETED = "Completed"


def build_product_processing_payload(product: ProductCreate, image: ProductImage) -> dict[str, Any]:
    """Build the `Job.payload` a `PRODUCT_PROCESSING` job needs to (re)process this upload.

    Used by `app/api/products.py` when queuing a new job; `ProductWorker`
    is what reads this same shape back out via `_parse_payload`.
    """
    return {"product": product.model_dump(mode="json"), "image": image.model_dump(mode="json")}


class ProductWorker:
    """Dequeues and processes `JobType.PRODUCT_PROCESSING` jobs, one at a time."""

    def __init__(
        self,
        *,
        queue_manager: QueueManager | None = None,
        product_service: ProductService | None = None,
        recommendation_engine_service: RecommendationEngineService | None = None,
        recommendation_cache_repository: RecommendationCacheRepository | None = None,
        metrics_registry: MetricsRegistry | None = None,
        analytics_repository: AnalyticsRepository | None = None,
    ) -> None:
        self._queue_manager = queue_manager if queue_manager is not None else QueueManager()
        self._product_service = product_service if product_service is not None else ProductService()
        self._recommendation_engine_service = (
            recommendation_engine_service
            if recommendation_engine_service is not None
            else RecommendationEngineService()
        )
        self._recommendation_cache_repository = (
            recommendation_cache_repository
            if recommendation_cache_repository is not None
            else RecommendationCacheRepository()
        )
        self._metrics = metrics_registry if metrics_registry is not None else MetricsRegistry()
        self._analytics = (
            analytics_repository if analytics_repository is not None else AnalyticsRepository()
        )

    async def process_one(self) -> bool:
        """Dequeue and fully process (at most) one job.

        Returns whether a job was actually available to process — lets a
        caller (`WorkerManager`) tell "the queue was empty" apart from
        "a job was attempted."
        """
        job = await self._queue_manager.dequeue()
        if job is None:
            return False

        attempt = job.retry_count + 1
        start = time.monotonic()
        logger.info(
            "Worker processing job: job_id=%s, product_id=%s, job_type=%s, attempt=%d",
            job.job_id,
            job.product_id,
            job.job_type.value,
            attempt,
        )

        # `JobType` only has one member today (see its own docstring) — a
        # real invariant, not a case this worker needs to gracefully
        # degrade for, the same "assert real invariants rather than
        # defensively handle impossible cases" reasoning `QdrantVectorStore`
        # (Phase 9) already established for its own mode-dependent type.
        assert job.job_type is JobType.PRODUCT_PROCESSING

        try:
            await self._report_progress(job, progress=10, stage=_STAGE_VALIDATING)
            product, image = _parse_payload(job.payload)

            await self._report_progress(job, progress=40, stage=_STAGE_PROCESSING)
            processed_product = await self._product_service.process_upload(
                product, image, product_id=job.product_id
            )

            await self._report_progress(job, progress=80, stage=_STAGE_CACHING_RECOMMENDATIONS)
            await self._warm_recommendation_cache(processed_product.id)
        except Exception as exc:
            await self._fail(job, start=start, attempt=attempt, error=str(exc))
            return True

        await self._complete(job, start=start, attempt=attempt)
        return True

    async def _warm_recommendation_cache(self, product_id: UUID) -> None:
        try:
            result = await self._recommendation_engine_service.recommend(
                product_id=product_id, recommendation_type=RecommendationType.SIMILAR
            )
            await self._recommendation_cache_repository.set(product_id, result)
        except Exception:
            # Non-fatal: a product that finished processing successfully
            # shouldn't be retried (re-running the whole expensive
            # pipeline) just because this warm-up step failed — the live
            # GET /products/{id}/recommendations endpoint still works
            # without a cache hit.
            logger.warning(
                "Recommendation cache warm-up failed (non-fatal): product_id=%s",
                product_id,
                exc_info=True,
            )

    async def _report_progress(self, job: Job, *, progress: int, stage: str) -> None:
        job.progress = progress
        job.current_stage = stage
        job.updated_at = datetime.now(UTC)
        await self._queue_manager.update(job)

    async def _complete(self, job: Job, *, start: float, attempt: int) -> None:
        duration = time.monotonic() - start
        completed_at = datetime.now(UTC)
        job.status = JobStatus.COMPLETED
        job.progress = 100
        job.current_stage = _STAGE_COMPLETED
        job.error = None
        job.updated_at = completed_at
        job.retry_history = [
            *job.retry_history,
            JobResult(
                attempt=attempt, success=True, duration_seconds=duration, completed_at=completed_at
            ),
        ]
        await self._queue_manager.update(job)
        await self._queue_manager.ack(job)
        self._metrics.record_worker_job(status="success", seconds=duration)
        await self._analytics.record_latency(duration)
        logger.info(
            "Worker completed job: job_id=%s, product_id=%s, attempt=%d, duration=%.4fs",
            job.job_id,
            job.product_id,
            attempt,
            duration,
        )

    async def _fail(self, job: Job, *, start: float, attempt: int, error: str) -> None:
        duration = time.monotonic() - start
        job.retry_history = [
            *job.retry_history,
            JobResult(
                attempt=attempt,
                success=False,
                error=error,
                duration_seconds=duration,
                completed_at=datetime.now(UTC),
            ),
        ]
        self._metrics.record_worker_job(status="failure", seconds=duration)
        logger.warning(
            "Worker failed to process job: job_id=%s, product_id=%s, attempt=%d, error=%s",
            job.job_id,
            job.product_id,
            attempt,
            error,
        )
        # retry() persists job (including the retry_history mutation
        # above, the same in-memory object) itself — no separate update()
        # call needed here.
        await self._queue_manager.retry(job, error=error)


def _parse_payload(payload: dict[str, Any]) -> tuple[ProductCreate, ProductImage]:
    return (
        ProductCreate.model_validate(payload["product"]),
        ProductImage.model_validate(payload["image"]),
    )

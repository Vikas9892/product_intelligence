"""Unit tests for `ProductWorker`.

Composes a real `QueueManager`/`RedisQueue` backed by `fakeredis` (so
retry/backoff/dead-letter integration is exercised for real, not
reimplemented as a fake) alongside fake `ProductService`/
`RecommendationEngineService`/`RecommendationCacheRepository` doubles
(each already covered by their own test modules, and each would
otherwise need real image files/models to exercise).
"""

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import fakeredis
from fakeredis import aioredis as fake_aioredis
from prometheus_client import CollectorRegistry

from app.jobs.base_job import Job
from app.jobs.job_status import JobStatus
from app.metrics.metrics_registry import MetricsRegistry
from app.models.catalog_intelligence_result import CatalogIntelligenceResult
from app.models.duplicate_decision import DuplicateDecision
from app.models.embedding import ImageEmbedding
from app.models.image_metadata import ImageMetadata
from app.models.product import Product
from app.models.product_attributes import ProductAttributes
from app.models.recommendation_candidate import RecommendationCandidate
from app.models.recommendation_reason import RecommendationReason
from app.models.recommendation_result import RecommendationResult
from app.models.recommendation_type import RecommendationType
from app.models.text_embedding import TextEmbedding
from app.queue.queue_manager import QueueManager
from app.queue.redis_queue import RedisQueue
from app.repositories.recommendation_cache_repository import RecommendationCacheRepository
from app.schemas.product import ProductCreate, ProductImage
from app.services.product_service import ProductService
from app.services.recommendation.recommendation_engine_service import RecommendationEngineService
from app.utils.metadata import FileMetadata
from app.workers.product_worker import ProductWorker, build_product_processing_payload


class _FakeProductService(ProductService):
    def __init__(self, *, product: Product | None = None, error: Exception | None = None) -> None:
        self._product = product
        self._error = error
        self.calls: list[dict[str, object]] = []

    async def process_upload(
        self, product: ProductCreate, image: ProductImage, *, product_id: UUID | None = None
    ) -> Product:
        self.calls.append({"product_id": product_id, "name": product.name})
        if self._error is not None:
            raise self._error
        assert self._product is not None
        return self._product


class _FakeRecommendationEngineService(RecommendationEngineService):
    def __init__(self, *, error: Exception | None = None) -> None:
        self._error = error
        self.calls: list[UUID] = []

    async def recommend(
        self,
        *,
        product_id: UUID,
        recommendation_type: RecommendationType = RecommendationType.SIMILAR,
        top_k: int | None = None,
        reranking_enabled: bool | None = None,
    ) -> RecommendationResult:
        self.calls.append(product_id)
        if self._error is not None:
            raise self._error
        return RecommendationResult(
            recommendations=[
                RecommendationCandidate(
                    product_id=uuid4(),
                    similarity_score=0.9,
                    quality_score=0.8,
                    final_score=0.85,
                    reason=RecommendationReason(),
                )
            ],
            processing_time=0.01,
            recommendation_type=recommendation_type,
        )


class _MultiProductFakeService(ProductService):
    """Returns whichever `Product` was registered for the `product_id` it's called with —
    lets the concurrency test prove two workers each processed their own distinct job."""

    def __init__(self, products_by_id: dict[UUID, Product]) -> None:
        self._products_by_id = products_by_id

    async def process_upload(
        self, product: ProductCreate, image: ProductImage, *, product_id: UUID | None = None
    ) -> Product:
        assert product_id is not None
        return self._products_by_id[product_id]


def _product(product_id: UUID) -> Product:
    now = datetime.now(UTC)
    return Product(
        id=product_id,
        name="Widget",
        brand=None,
        description=None,
        category=None,
        price=None,
        file_metadata=FileMetadata(
            original_filename="photo.jpg",
            extension=".jpg",
            content_type="image/jpeg",
            size_bytes=10,
            checksum_sha256="a" * 64,
            uploaded_at=now,
        ),
        image_metadata=ImageMetadata(
            width=50,
            height=50,
            format="JPEG",
            color_mode="RGB",
            original_path=Path("/tmp/original.jpg"),
            processed_path=Path("/tmp/processed.jpg"),
        ),
        embedding=ImageEmbedding(
            product_id=product_id, model_name="fake-clip", embedding_dimension=2, vector=[0.1, 0.2]
        ),
        text_embedding=TextEmbedding(
            product_id=product_id, model_name="fake-text", embedding_dimension=2, vector=[0.1, 0.2]
        ),
        catalog_intelligence=CatalogIntelligenceResult(
            attributes=ProductAttributes(), tags=[], quality_score=0.0, processing_time=0.0
        ),
        duplicate_decision=DuplicateDecision(is_duplicate=False, confidence=0.0, reason="off"),
    )


def _image() -> ProductImage:
    return ProductImage(
        original_filename="photo.jpg",
        stored_filename="stored.jpg",
        content_type="image/jpeg",
        size_bytes=10,
        uploaded_at=datetime.now(UTC),
    )


def _job(
    *,
    max_retries: int = 3,
    retry_delay_seconds: float = 5.0,
    server: fakeredis.FakeServer | None = None,
) -> tuple[Job, QueueManager]:
    now = datetime.now(UTC)
    product_id = uuid4()
    payload = build_product_processing_payload(ProductCreate(name="Widget"), _image())
    job = Job(
        job_id=uuid4(),
        product_id=product_id,
        payload=payload,
        created_at=now,
        updated_at=now,
        max_retries=max_retries,
    )
    client = fake_aioredis.FakeRedis(
        server=server if server is not None else fakeredis.FakeServer(), decode_responses=True
    )
    queue_manager = QueueManager(
        queue=RedisQueue(
            redis_client=client, queue_name="test-worker", retry_delay_seconds=retry_delay_seconds
        )
    )
    return job, queue_manager


def _worker(
    *,
    queue_manager: QueueManager,
    product_service: ProductService | None = None,
    recommendation_engine_service: RecommendationEngineService | None = None,
    recommendation_cache_repository: RecommendationCacheRepository | None = None,
    metrics_registry: MetricsRegistry | None = None,
) -> ProductWorker:
    return ProductWorker(
        queue_manager=queue_manager,
        product_service=product_service if product_service is not None else _FakeProductService(),
        recommendation_engine_service=(
            recommendation_engine_service
            if recommendation_engine_service is not None
            else _FakeRecommendationEngineService()
        ),
        recommendation_cache_repository=(
            recommendation_cache_repository
            if recommendation_cache_repository is not None
            else RecommendationCacheRepository(
                redis_client=fake_aioredis.FakeRedis(decode_responses=True)
            )
        ),
        metrics_registry=metrics_registry,
    )


class TestEmptyQueue:
    async def test_returns_false_when_no_job_is_available(self) -> None:
        _job_unused, queue_manager = _job()
        worker = _worker(queue_manager=queue_manager)

        assert await worker.process_one() is False


class TestSuccessfulProcessing:
    async def test_processes_a_job_end_to_end(self) -> None:
        job, queue_manager = _job()
        product = _product(job.product_id)
        await queue_manager.enqueue(job)
        worker = _worker(
            queue_manager=queue_manager, product_service=_FakeProductService(product=product)
        )

        processed = await worker.process_one()

        assert processed is True
        stored = await queue_manager.get(job.job_id)
        assert stored is not None
        assert stored.status is JobStatus.COMPLETED
        assert stored.progress == 100
        assert stored.current_stage == "Completed"
        assert stored.error is None
        assert len(stored.retry_history) == 1
        assert stored.retry_history[0].success is True

    async def test_uses_the_jobs_own_product_id(self) -> None:
        job, queue_manager = _job()
        product = _product(job.product_id)
        await queue_manager.enqueue(job)
        product_service = _FakeProductService(product=product)
        worker = _worker(queue_manager=queue_manager, product_service=product_service)

        await worker.process_one()

        assert product_service.calls[0]["product_id"] == job.product_id

    async def test_warms_the_recommendation_cache(self) -> None:
        job, queue_manager = _job()
        product = _product(job.product_id)
        await queue_manager.enqueue(job)
        recommendation_engine_service = _FakeRecommendationEngineService()
        cache_repository = RecommendationCacheRepository(
            redis_client=fake_aioredis.FakeRedis(decode_responses=True)
        )
        worker = _worker(
            queue_manager=queue_manager,
            product_service=_FakeProductService(product=product),
            recommendation_engine_service=recommendation_engine_service,
            recommendation_cache_repository=cache_repository,
        )

        await worker.process_one()

        assert recommendation_engine_service.calls == [job.product_id]
        cached = await cache_repository.get(job.product_id)
        assert cached is not None

    async def test_a_failed_cache_warm_up_does_not_fail_the_job(self) -> None:
        job, queue_manager = _job()
        product = _product(job.product_id)
        await queue_manager.enqueue(job)
        worker = _worker(
            queue_manager=queue_manager,
            product_service=_FakeProductService(product=product),
            recommendation_engine_service=_FakeRecommendationEngineService(
                error=RuntimeError("recommendation engine boom")
            ),
        )

        await worker.process_one()

        stored = await queue_manager.get(job.job_id)
        assert stored is not None
        assert stored.status is JobStatus.COMPLETED


class TestMetrics:
    async def test_records_a_successful_job(self) -> None:
        metrics = MetricsRegistry(registry=CollectorRegistry())
        job, queue_manager = _job()
        await queue_manager.enqueue(job)
        worker = _worker(
            queue_manager=queue_manager,
            product_service=_FakeProductService(product=_product(job.product_id)),
            metrics_registry=metrics,
        )

        await worker.process_one()

        assert (
            metrics._registry.get_sample_value(
                "product_intelligence_worker_jobs_total", {"status": "success"}
            )
            == 1.0
        )
        assert (
            metrics._registry.get_sample_value(
                "product_intelligence_worker_job_duration_seconds_count"
            )
            == 1.0
        )

    async def test_records_a_failed_job(self) -> None:
        metrics = MetricsRegistry(registry=CollectorRegistry())
        job, queue_manager = _job()
        await queue_manager.enqueue(job)
        worker = _worker(
            queue_manager=queue_manager,
            product_service=_FakeProductService(error=RuntimeError("boom")),
            metrics_registry=metrics,
        )

        await worker.process_one()

        assert (
            metrics._registry.get_sample_value(
                "product_intelligence_worker_jobs_total", {"status": "failure"}
            )
            == 1.0
        )


class TestFailureAndRetry:
    async def test_a_failure_schedules_a_retry_not_a_completion(self) -> None:
        job, queue_manager = _job()
        await queue_manager.enqueue(job)
        worker = _worker(
            queue_manager=queue_manager,
            product_service=_FakeProductService(error=RuntimeError("processing boom")),
        )

        await worker.process_one()

        stored = await queue_manager.get(job.job_id)
        assert stored is not None
        assert stored.status is JobStatus.RETRYING
        assert stored.retry_count == 1
        assert stored.error == "processing boom"
        assert len(stored.retry_history) == 1
        assert stored.retry_history[0].success is False

    async def test_exhausting_retries_dead_letters_the_job(self) -> None:
        job, queue_manager = _job(max_retries=0)
        await queue_manager.enqueue(job)
        worker = _worker(
            queue_manager=queue_manager,
            product_service=_FakeProductService(error=RuntimeError("boom")),
        )

        await worker.process_one()

        stored = await queue_manager.get(job.job_id)
        assert stored is not None
        assert stored.status is JobStatus.FAILED

    async def test_retrying_the_same_job_reuses_the_same_product_id(self) -> None:
        # Idempotency: the product_id passed to ProductService never
        # changes across attempts, so retries converge (Qdrant upsert)
        # rather than creating a second indexed product per attempt.
        job, queue_manager = _job(max_retries=3, retry_delay_seconds=0.01)
        await queue_manager.enqueue(job)
        product_service = _FakeProductService(error=RuntimeError("transient"))
        worker = _worker(queue_manager=queue_manager, product_service=product_service)

        await worker.process_one()  # fails, scheduled for retry

        product_service._error = None
        product_service._product = _product(job.product_id)
        await asyncio.sleep(0.05)
        await worker.process_one()

        assert {call["product_id"] for call in product_service.calls} == {job.product_id}


class TestConcurrentWorkers:
    async def test_two_workers_never_process_the_same_job_twice(self) -> None:
        server = fakeredis.FakeServer()
        jobs_and_managers = [_job(server=server) for _ in range(6)]
        queue_manager = jobs_and_managers[0][1]
        for job, _manager in jobs_and_managers:
            await queue_manager.enqueue(job)

        products_by_id = {job.product_id: _product(job.product_id) for job, _ in jobs_and_managers}

        def _make_worker() -> ProductWorker:
            client = fake_aioredis.FakeRedis(server=server, decode_responses=True)
            manager = QueueManager(queue=RedisQueue(redis_client=client, queue_name="test-worker"))
            return _worker(
                queue_manager=manager,
                product_service=_MultiProductFakeService(products_by_id),
            )

        worker_a, worker_b = _make_worker(), _make_worker()
        await asyncio.gather(
            *(worker_a.process_one() for _ in range(3)), *(worker_b.process_one() for _ in range(3))
        )

        completed_ids = set()
        for job, _ in jobs_and_managers:
            stored = await queue_manager.get(job.job_id)
            assert stored is not None
            assert stored.status is JobStatus.COMPLETED
            completed_ids.add(stored.product_id)
        assert completed_ids == set(products_by_id)

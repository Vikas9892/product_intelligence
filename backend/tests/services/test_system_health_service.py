"""Unit tests for `SystemHealthService`.

Uses `fakeredis` for the Redis-backed checks and a fake `BaseVectorStore`
for the Qdrant check, so nothing real needs to be running. A dedicated
seeded `ModelRegistry` controls the active-model count.
"""

from typing import Any
from uuid import UUID

from fakeredis import aioredis as fake_aioredis

from app.models.model_info import ModelInfo
from app.models.model_status import ModelStatus
from app.models.model_type import ModelType
from app.models.search import NearestNeighbor, ProductFilters, StoredPoint
from app.services.model_registry import ModelRegistry
from app.services.system_health_service import SystemHealthService
from app.services.vectorstore.base import BaseVectorStore, VectorCollection, VectorRecord


class _FakeVectorStore(BaseVectorStore):
    def __init__(self, *, healthy: bool = True) -> None:
        self._healthy = healthy

    async def upsert(self, collection: VectorCollection, records: list[VectorRecord]) -> None:
        return None

    async def search(
        self,
        collection: VectorCollection,
        query_vector: list[float],
        *,
        top_k: int,
        filters: ProductFilters | None = None,
    ) -> list[NearestNeighbor]:
        return []

    async def delete(self, collection: VectorCollection, product_ids: list[UUID]) -> None:
        return None

    async def exists(self, collection: VectorCollection, product_id: UUID) -> bool:
        return False

    async def retrieve(self, collection: VectorCollection, product_id: UUID) -> StoredPoint | None:
        return None

    async def health(self) -> bool:
        return self._healthy


class _UnreachableRedis:
    """Every operation raises — simulates Redis being down."""

    async def ping(self) -> bool:
        raise ConnectionError("boom")

    async def llen(self, name: str) -> int:
        raise ConnectionError("boom")

    async def hlen(self, name: str) -> int:
        raise ConnectionError("boom")


def _registry_with_active_models() -> ModelRegistry:
    registry = ModelRegistry(seed_from_settings=False)
    registry.register(
        ModelInfo(
            model_name="clip",
            version="1.0.0",
            model_type=ModelType.IMAGE_EMBEDDING,
            dimension=512,
            status=ModelStatus.ACTIVE,
        )
    )
    registry.register(
        ModelInfo(
            model_name="clip-experimental",
            version="1.1.0",
            model_type=ModelType.IMAGE_EMBEDDING,
            dimension=512,
            status=ModelStatus.EXPERIMENTAL,
        )
    )
    registry.register(
        ModelInfo(
            model_name="bge",
            version="1.0.0",
            model_type=ModelType.TEXT_EMBEDDING,
            dimension=384,
            status=ModelStatus.ACTIVE,
        )
    )
    return registry


def _service(**kwargs: Any) -> SystemHealthService:
    return SystemHealthService(
        redis_client=kwargs.pop("redis_client", fake_aioredis.FakeRedis(decode_responses=True)),
        vector_store=kwargs.pop("vector_store", _FakeVectorStore()),
        model_registry=kwargs.pop("model_registry", _registry_with_active_models()),
        worker_concurrency=kwargs.pop("worker_concurrency", 4),
        queue_name=kwargs.pop("queue_name", "test-queue"),
    )


class TestHealth:
    async def test_reports_healthy_when_everything_is_up(self) -> None:
        service = _service()

        health = await service.health()

        assert health.redis == "healthy"
        assert health.qdrant == "healthy"
        assert health.workers == 4
        assert health.active_models == 2
        assert health.uptime_seconds >= 0.0

    async def test_reports_redis_unhealthy_when_ping_fails(self) -> None:
        service = _service(redis_client=_UnreachableRedis())

        health = await service.health()

        assert health.redis == "unhealthy"
        assert health.queue_depth == 0

    async def test_reports_qdrant_unhealthy_when_the_store_is_down(self) -> None:
        service = _service(vector_store=_FakeVectorStore(healthy=False))

        health = await service.health()

        assert health.qdrant == "unhealthy"

    async def test_queue_depth_reflects_the_pending_list(self) -> None:
        client = fake_aioredis.FakeRedis(decode_responses=True)
        await client.rpush("test-queue:pending", "a", "b", "c")
        service = _service(redis_client=client)

        health = await service.health()

        assert health.queue_depth == 3


class TestStats:
    async def test_reports_aggregate_statistics(self) -> None:
        client = fake_aioredis.FakeRedis(decode_responses=True)
        await client.rpush("test-queue:pending", "a", "b")
        await client.hset("test-queue:processing", "job1", "123")
        await client.rpush("test-queue:dead_letter", "x")
        service = _service(redis_client=client)

        stats = await service.stats()

        assert stats.queue_depth == 2
        assert stats.jobs_in_flight == 1
        assert stats.dead_letter_size == 1
        assert stats.active_models == 2
        assert stats.registered_models == 3
        assert stats.worker_concurrency == 4

    async def test_stats_degrade_to_zero_when_redis_is_down(self) -> None:
        service = _service(redis_client=_UnreachableRedis())

        stats = await service.stats()

        assert stats.queue_depth == 0
        assert stats.jobs_in_flight == 0
        assert stats.dead_letter_size == 0

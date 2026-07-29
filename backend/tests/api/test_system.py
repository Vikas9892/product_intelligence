"""Integration tests for `GET /api/v1/system/health` and `/system/stats`.

Builds the *real* `create_app()` app, overriding `get_system_health_service`
with a `SystemHealthService` wired to `fakeredis` + a fake vector store +
a seeded registry — the service's own logic is covered in isolation by
`test_system_health_service.py`; this suite proves the routes are wired
and shaped correctly.
"""

from collections.abc import Iterator
from uuid import UUID

import pytest
from fakeredis import aioredis as fake_aioredis
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.application import create_app
from app.core.config import settings
from app.dependencies.system import get_system_health_service
from app.models.model_info import ModelInfo
from app.models.model_status import ModelStatus
from app.models.model_type import ModelType
from app.models.search import NearestNeighbor, ProductFilters, StoredPoint
from app.services.model_registry import ModelRegistry
from app.services.system_health_service import SystemHealthService
from app.services.vectorstore.base import BaseVectorStore, VectorCollection, VectorRecord

_HEALTH_URL = f"{settings.application.api_prefix}/system/health"
_STATS_URL = f"{settings.application.api_prefix}/system/stats"


class _FakeVectorStore(BaseVectorStore):
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
        return True


def _registry() -> ModelRegistry:
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
    return registry


@pytest.fixture
def system_client() -> Iterator[TestClient]:
    app: FastAPI = create_app()
    service = SystemHealthService(
        redis_client=fake_aioredis.FakeRedis(decode_responses=True),
        vector_store=_FakeVectorStore(),
        model_registry=_registry(),
        worker_concurrency=4,
        queue_name="test-queue",
    )
    app.dependency_overrides[get_system_health_service] = lambda: service
    with TestClient(app) as client:
        yield client


class TestSystemHealthEndpoint:
    def test_returns_the_health_snapshot_shape(self, system_client: TestClient) -> None:
        response = system_client.get(_HEALTH_URL)

        assert response.status_code == 200
        body = response.json()
        assert body["redis"] == "healthy"
        assert body["qdrant"] == "healthy"
        assert body["workers"] == 4
        assert body["queue_depth"] == 0
        assert body["active_models"] == 1
        assert ":" in body["uptime"]


class TestSystemStatsEndpoint:
    def test_returns_the_stats_shape(self, system_client: TestClient) -> None:
        response = system_client.get(_STATS_URL)

        assert response.status_code == 200
        body = response.json()
        assert body["worker_concurrency"] == 4
        assert body["active_models"] == 1
        assert body["registered_models"] == 1
        assert body["queue_depth"] == 0
        assert body["jobs_in_flight"] == 0
        assert body["dead_letter_size"] == 0
        assert body["uptime_seconds"] >= 0.0


class TestHealthEndpointsDisabled:
    def test_routes_absent_when_health_endpoints_disabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings.metrics, "health_endpoints_enabled", False)
        app = create_app()

        with TestClient(app) as client:
            assert client.get(_HEALTH_URL).status_code == 404
            assert client.get(_STATS_URL).status_code == 404

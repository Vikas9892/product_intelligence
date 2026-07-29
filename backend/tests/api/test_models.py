"""Integration tests for `GET /api/v1/models`, `/models/{type}`, `/models/{type}/active`.

Builds the *real* `create_app()` application, overriding `get_model_registry`
with a `ModelRegistry(seed_from_settings=False)` seeded with known test
data — the registry's own bookkeeping logic is `test_model_registry.py`'s
job (already covered there in isolation); this suite only proves the
router itself is wired correctly: request parsing, type filtering, and
response shaping. No model is ever loaded to answer any of these routes.
"""

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.application import create_app
from app.core.config import settings
from app.dependencies.model_registry import get_model_registry
from app.models.model_info import ModelInfo
from app.models.model_status import ModelStatus
from app.models.model_type import ModelType
from app.services.model_registry import ModelRegistry

_MODELS_URL = f"{settings.application.api_prefix}/models"


def _model_info(
    *,
    model_type: ModelType = ModelType.IMAGE_EMBEDDING,
    version: str = "1.0.0",
    status: ModelStatus = ModelStatus.ACTIVE,
    model_name: str = "openai/clip-vit-base-patch32",
    dimension: int = 512,
) -> ModelInfo:
    return ModelInfo(
        model_name=model_name,
        version=version,
        model_type=model_type,
        dimension=dimension,
        status=status,
    )


@pytest.fixture
def models_client() -> Iterator[tuple[TestClient, ModelRegistry]]:
    app: FastAPI = create_app()
    registry = ModelRegistry(seed_from_settings=False)
    registry.register(_model_info(model_type=ModelType.IMAGE_EMBEDDING, version="1.0.0"))
    registry.register(
        _model_info(
            model_type=ModelType.IMAGE_EMBEDDING,
            version="1.1.0",
            status=ModelStatus.EXPERIMENTAL,
        )
    )
    registry.register(
        _model_info(
            model_type=ModelType.TEXT_EMBEDDING,
            model_name="BAAI/bge-small-en-v1.5",
            dimension=384,
        )
    )
    app.dependency_overrides[get_model_registry] = lambda: registry
    with TestClient(app) as client:
        yield client, registry


class TestListModels:
    def test_lists_every_registered_model(
        self, models_client: tuple[TestClient, ModelRegistry]
    ) -> None:
        client, _registry = models_client

        response = client.get(_MODELS_URL)

        assert response.status_code == 200
        assert len(response.json()) == 3

    def test_response_shape_matches_model_info(
        self, models_client: tuple[TestClient, ModelRegistry]
    ) -> None:
        client, _registry = models_client

        response = client.get(_MODELS_URL)

        body = next(item for item in response.json() if item["version"] == "1.0.0")
        assert body["model_name"] == "openai/clip-vit-base-patch32"
        assert body["model_type"] == "image_embedding"
        assert body["status"] == "active"
        assert body["dimension"] == 512
        assert body["provider"] == "Hugging Face"
        assert "created_at" in body


class TestListModelsByType:
    def test_narrows_to_the_requested_type(
        self, models_client: tuple[TestClient, ModelRegistry]
    ) -> None:
        client, _registry = models_client

        response = client.get(f"{_MODELS_URL}/image_embedding")

        assert response.status_code == 200
        body = response.json()
        assert len(body) == 2
        assert all(item["model_type"] == "image_embedding" for item in body)

    def test_returns_an_empty_list_for_a_type_with_nothing_registered(
        self, models_client: tuple[TestClient, ModelRegistry]
    ) -> None:
        client, _registry = models_client

        response = client.get(f"{_MODELS_URL}/reranker")

        assert response.status_code == 200
        assert response.json() == []

    def test_an_invalid_type_returns_a_validation_error(
        self, models_client: tuple[TestClient, ModelRegistry]
    ) -> None:
        client, _registry = models_client

        response = client.get(f"{_MODELS_URL}/not-a-real-type")

        assert response.status_code == 422


class TestGetActiveModel:
    def test_returns_the_active_model_for_the_type(
        self, models_client: tuple[TestClient, ModelRegistry]
    ) -> None:
        client, _registry = models_client

        response = client.get(f"{_MODELS_URL}/image_embedding/active")

        assert response.status_code == 200
        body = response.json()
        assert body["version"] == "1.0.0"
        assert body["status"] == "active"

    def test_returns_404_when_no_model_is_active_for_the_type(
        self, models_client: tuple[TestClient, ModelRegistry]
    ) -> None:
        client, _registry = models_client

        response = client.get(f"{_MODELS_URL}/reranker/active")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "resource_not_found"

"""Integration tests for `GET /api/v1/products/{id}/recommendations`.

Builds the *real* `create_app()` application, overriding
`get_upload_service`/`get_product_service`/`get_recommendation_engine_service`
to redirect storage to `tmp_path` and share one tiny real CLIP model plus
one in-memory Qdrant instance across both the seeding uploads and the
recommendation request — the same strategy `test_check_duplicate.py`
already uses. Seeds the vector store via the real `/products/upload`
endpoint (duplicate detection OFF, since it isn't this suite's concern),
then requests recommendations for one of the seeded products.
"""

import io
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from qdrant_client import QdrantClient

from app.application import create_app
from app.core.config import settings
from app.core.constants import DuplicateDetectionMode
from app.dependencies.product import get_product_service
from app.dependencies.recommendation import get_recommendation_engine_service
from app.dependencies.upload import get_upload_service
from app.services.embeddings.base import BaseEmbeddingService
from app.services.embeddings.clip_service import CLIPEmbeddingService
from app.services.embeddings.model_manager import ModelManager
from app.services.embeddings.text_base import BaseTextEmbeddingService
from app.services.image_processing_service import ImageProcessingService
from app.services.product_service import ProductService
from app.services.recommendation.recommendation_engine_service import RecommendationEngineService
from app.services.upload_service import UploadService
from app.services.vectorstore.hybrid_search_service import HybridSearchService
from app.services.vectorstore.qdrant_store import QdrantVectorStore
from app.services.vectorstore.search_service import SearchService
from app.services.vectorstore.text_search_service import TextSearchService

_UPLOAD_URL = f"{settings.application.api_prefix}/products/upload"

_TINY_MODEL_NAME = "hf-internal-testing/tiny-random-CLIPModel"
_shared_model_manager = ModelManager(device="cpu")
_image_vector_size = _shared_model_manager.get_model(_TINY_MODEL_NAME)[0].config.projection_dim


class _FakeTextEmbeddingService(BaseTextEmbeddingService):
    """Deterministic: same text -> same vector, so related products score highly."""

    @property
    def model_name(self) -> str:
        return "fake-text-model"

    @property
    def dimension(self) -> int:
        return 4

    async def embed_text(self, text: str) -> list[float]:
        return [0.1, 0.2, 0.3, 0.4]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed_text(text) for text in texts]


def _image_file(
    *, color: tuple[int, int, int] = (200, 30, 30)
) -> dict[str, tuple[str, io.BytesIO, str]]:
    buffer = io.BytesIO()
    Image.new("RGB", (40, 40), color).save(buffer, format="JPEG")
    buffer.seek(0)
    return {"file": ("photo.jpg", buffer, "image/jpeg")}


def _override_services(
    app: FastAPI,
    upload_dir: Path,
    *,
    embedding_service: BaseEmbeddingService,
    text_embedding_service: BaseTextEmbeddingService,
    vector_store: QdrantVectorStore,
) -> None:
    image_processing_service = ImageProcessingService(processed_dir=upload_dir / "processed")
    hybrid_search_service = HybridSearchService(
        search_service=SearchService(
            upload_dir=upload_dir,
            image_processing_service=image_processing_service,
            embedding_service=embedding_service,
            vector_store=vector_store,
        ),
        text_search_service=TextSearchService(
            text_embedding_service=text_embedding_service, vector_store=vector_store
        ),
    )

    app.dependency_overrides[get_upload_service] = lambda: UploadService(upload_dir=upload_dir)
    app.dependency_overrides[get_product_service] = lambda: ProductService(
        upload_dir=upload_dir,
        image_processing_service=image_processing_service,
        embedding_service=embedding_service,
        text_embedding_service=text_embedding_service,
        # This suite isn't about duplicate detection — OFF avoids seeded
        # uploads being rejected or interfering with recommendations.
        duplicate_detection_mode=DuplicateDetectionMode.OFF,
        vector_store=vector_store,
    )
    app.dependency_overrides[get_recommendation_engine_service] = lambda: (
        RecommendationEngineService(
            hybrid_search_service=hybrid_search_service, vector_store=vector_store
        )
    )


@pytest.fixture
def recommendations_client(tmp_path: Path) -> Iterator[TestClient]:
    app = create_app()
    vector_store = QdrantVectorStore(
        client=QdrantClient(location=":memory:"),
        image_collection_name="test_recommendations_image",
        image_vector_size=_image_vector_size,
        text_collection_name="test_recommendations_text",
        text_vector_size=4,
    )
    embedding_service = CLIPEmbeddingService(
        model_name=_TINY_MODEL_NAME, model_manager=_shared_model_manager
    )
    _override_services(
        app,
        tmp_path,
        embedding_service=embedding_service,
        text_embedding_service=_FakeTextEmbeddingService(),
        vector_store=vector_store,
    )

    with TestClient(app) as client:
        yield client


def _seed_product(
    client: TestClient,
    *,
    name: str,
    brand: str,
    category: str = "Running Shoes",
    color: tuple[int, int, int] = (200, 30, 30),
) -> str:
    response = client.post(
        _UPLOAD_URL,
        data={"name": name, "brand": brand, "category": category},
        files=_image_file(color=color),
    )
    assert response.status_code == 201
    product_id: str = response.json()["product_id"]
    return product_id


class TestGetRecommendations:
    def test_returns_other_seeded_products(self, recommendations_client: TestClient) -> None:
        target_id = _seed_product(recommendations_client, name="Nike Air Zoom", brand="Nike")
        other_id = _seed_product(recommendations_client, name="Nike Pegasus", brand="Nike")

        response = recommendations_client.get(
            f"{settings.application.api_prefix}/products/{target_id}/recommendations"
        )

        assert response.status_code == 200
        body = response.json()
        assert body["recommendation_type"] == "similar"
        recommended_ids = [rec["product_id"] for rec in body["recommendations"]]
        assert other_id in recommended_ids
        assert target_id not in recommended_ids

    def test_never_returns_a_raw_vector_or_embedding(
        self, recommendations_client: TestClient
    ) -> None:
        target_id = _seed_product(recommendations_client, name="Nike Air Zoom", brand="Nike")
        _seed_product(recommendations_client, name="Nike Pegasus", brand="Nike")

        response = recommendations_client.get(
            f"{settings.application.api_prefix}/products/{target_id}/recommendations"
        )

        assert "vector" not in response.text
        assert "embedding" not in response.text

    def test_each_recommendation_includes_a_reason_and_explanation(
        self, recommendations_client: TestClient
    ) -> None:
        target_id = _seed_product(recommendations_client, name="Nike Air Zoom", brand="Nike")
        _seed_product(recommendations_client, name="Nike Pegasus", brand="Nike")

        response = recommendations_client.get(
            f"{settings.application.api_prefix}/products/{target_id}/recommendations"
        )

        body = response.json()
        assert len(body["recommendations"]) >= 1
        recommendation = body["recommendations"][0]
        assert "reason" in recommendation
        assert "matched_attributes" in recommendation["reason"]
        assert "matched_tags" in recommendation["reason"]
        assert isinstance(recommendation["explanation"], str)
        assert recommendation["explanation"] != ""

    def test_respects_a_custom_top_k(self, recommendations_client: TestClient) -> None:
        target_id = _seed_product(recommendations_client, name="Nike Air Zoom", brand="Nike")
        for i in range(3):
            _seed_product(recommendations_client, name=f"Nike Model {i}", brand="Nike")

        response = recommendations_client.get(
            f"{settings.application.api_prefix}/products/{target_id}/recommendations",
            params={"top_k": 1},
        )

        assert response.status_code == 200
        assert len(response.json()["recommendations"]) == 1

    def test_related_recommendation_type_is_accepted(
        self, recommendations_client: TestClient
    ) -> None:
        target_id = _seed_product(recommendations_client, name="Nike Air Zoom", brand="Nike")
        _seed_product(recommendations_client, name="Nike Pegasus", brand="Nike")

        response = recommendations_client.get(
            f"{settings.application.api_prefix}/products/{target_id}/recommendations",
            params={"recommendation_type": "related"},
        )

        assert response.status_code == 200
        assert response.json()["recommendation_type"] == "related"

    def test_an_unknown_product_id_returns_404(self, recommendations_client: TestClient) -> None:
        response = recommendations_client.get(
            f"{settings.application.api_prefix}/products/{uuid4()}/recommendations"
        )

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "resource_not_found"

    def test_an_invalid_uuid_returns_a_validation_error(
        self, recommendations_client: TestClient
    ) -> None:
        response = recommendations_client.get(
            f"{settings.application.api_prefix}/products/not-a-uuid/recommendations"
        )

        assert response.status_code == 422

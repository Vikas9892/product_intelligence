"""Integration tests for `POST /api/v1/products/search`.

Builds the *real* `create_app()` application, overriding
`get_upload_service`/`get_product_service`/`get_hybrid_search_service` to
redirect storage to `tmp_path` and to share one tiny real CLIP model, one
small real Sentence Transformers model, and one in-memory Qdrant instance
(both collections) across upload and search — the same tiny-checkpoint,
in-memory-Qdrant strategy every other API test file in this project uses.
Sharing everything across upload and search is what makes these tests
genuine: a product uploaded through the real `/products/upload` endpoint
must actually be findable through the real `/products/search` endpoint
afterward, by image, by text, or by both.
"""

import io
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from qdrant_client import QdrantClient

from app.application import create_app
from app.core.config import settings
from app.core.constants import DuplicateDetectionMode
from app.dependencies.hybrid_search import get_hybrid_search_service
from app.dependencies.product import get_product_service
from app.dependencies.upload import get_upload_service
from app.services.embeddings.clip_service import CLIPEmbeddingService
from app.services.embeddings.model_manager import ModelManager
from app.services.embeddings.sentence_transformer_service import (
    SentenceTransformerEmbeddingService,
)
from app.services.embeddings.text_model_manager import TextModelManager
from app.services.image_processing_service import ImageProcessingService
from app.services.product_service import ProductService
from app.services.upload_service import UploadService
from app.services.vectorstore.hybrid_search_service import HybridSearchService
from app.services.vectorstore.qdrant_store import QdrantVectorStore
from app.services.vectorstore.search_service import SearchService
from app.services.vectorstore.text_search_service import TextSearchService

_UPLOAD_URL = f"{settings.application.api_prefix}/products/upload"
_SEARCH_URL = f"{settings.application.api_prefix}/products/search"

_TINY_IMAGE_MODEL_NAME = "hf-internal-testing/tiny-random-CLIPModel"
_SMALL_TEXT_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
_TEXT_VECTOR_SIZE = 384

_shared_image_model_manager = ModelManager(device="cpu")
_shared_text_model_manager = TextModelManager(device="cpu")
_image_vector_size = _shared_image_model_manager.get_model(_TINY_IMAGE_MODEL_NAME)[
    0
].config.projection_dim


def _image_bytes(
    *, size: tuple[int, int] = (20, 20), color: tuple[int, int, int] = (255, 0, 0)
) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="JPEG")
    return buffer.getvalue()


def _image_file(
    *, filename: str = "photo.jpg", content: bytes | None = None
) -> dict[str, tuple[str, io.BytesIO, str]]:
    return {
        "file": (
            filename,
            io.BytesIO(content if content is not None else _image_bytes()),
            "image/jpeg",
        )
    }


def _override_services(app: FastAPI, upload_dir: Path, *, vector_store: QdrantVectorStore) -> None:
    embedding_service = CLIPEmbeddingService(
        model_name=_TINY_IMAGE_MODEL_NAME, model_manager=_shared_image_model_manager
    )
    text_embedding_service = SentenceTransformerEmbeddingService(
        model_name=_SMALL_TEXT_MODEL_NAME,
        dimension=_TEXT_VECTOR_SIZE,
        model_manager=_shared_text_model_manager,
    )
    image_processing_service = ImageProcessingService(processed_dir=upload_dir / "processed")

    app.dependency_overrides[get_upload_service] = lambda: UploadService(upload_dir=upload_dir)
    app.dependency_overrides[get_product_service] = lambda: ProductService(
        upload_dir=upload_dir,
        image_processing_service=image_processing_service,
        embedding_service=embedding_service,
        text_embedding_service=text_embedding_service,
        # This suite covers search itself, not duplicate detection (see
        # tests/services/test_product_service.py and
        # tests/services/duplicate/) — OFF avoids every seeded upload
        # here also re-running a real hybrid search.
        duplicate_detection_mode=DuplicateDetectionMode.OFF,
        vector_store=vector_store,
    )
    app.dependency_overrides[get_hybrid_search_service] = lambda: HybridSearchService(
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


@pytest.fixture
def search_client(tmp_path: Path) -> Iterator[TestClient]:
    app = create_app()
    vector_store = QdrantVectorStore(
        client=QdrantClient(location=":memory:"),
        image_collection_name="test_hybrid_search_image",
        image_vector_size=_image_vector_size,
        text_collection_name="test_hybrid_search_text",
        text_vector_size=_TEXT_VECTOR_SIZE,
    )
    _override_services(app, tmp_path, vector_store=vector_store)

    with TestClient(app) as client:
        yield client


def _upload(
    search_client: TestClient,
    *,
    name: str = "Widget",
    brand: str | None = None,
    category: str | None = None,
    price: str | None = None,
    content: bytes | None = None,
) -> str:
    data = {"name": name}
    if brand is not None:
        data["brand"] = brand
    if category is not None:
        data["category"] = category
    if price is not None:
        data["price"] = price
    response = search_client.post(_UPLOAD_URL, data=data, files=_image_file(content=content))
    product_id: str = response.json()["product_id"]
    return product_id


class TestSearchProducts:
    def test_finds_a_previously_uploaded_product_by_image(self, search_client: TestClient) -> None:
        content = _image_bytes(color=(10, 20, 30))
        product_id = _upload(search_client, content=content)

        response = search_client.post(_SEARCH_URL, data={}, files=_image_file(content=content))

        assert response.status_code == 200
        product_ids = [result["product_id"] for result in response.json()["results"]]
        assert product_id in product_ids

    def test_finds_a_previously_uploaded_product_by_text(self, search_client: TestClient) -> None:
        product_id = _upload(search_client, name="Red Running Shoe")

        response = search_client.post(_SEARCH_URL, data={"query": "a red running shoe"})

        assert response.status_code == 200
        product_ids = [result["product_id"] for result in response.json()["results"]]
        assert product_id in product_ids

    def test_hybrid_search_with_both_image_and_text(self, search_client: TestClient) -> None:
        content = _image_bytes(color=(40, 50, 60))
        product_id = _upload(search_client, name="Blue Widget", content=content)

        response = search_client.post(
            _SEARCH_URL,
            data={"query": "a blue widget"},
            files=_image_file(content=content),
        )

        assert response.status_code == 200
        match = next(
            result for result in response.json()["results"] if result["product_id"] == product_id
        )
        assert set(match["matched_modalities"]) == {"image", "text"}

    def test_returns_422_when_neither_image_nor_text_is_given(
        self, search_client: TestClient
    ) -> None:
        response = search_client.post(_SEARCH_URL, data={})

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"

    def test_never_returns_a_raw_vector(self, search_client: TestClient) -> None:
        content = _image_bytes(color=(70, 80, 90))
        _upload(search_client, content=content)

        response = search_client.post(_SEARCH_URL, data={}, files=_image_file(content=content))

        for result in response.json()["results"]:
            assert "vector" not in result
            assert set(result.keys()) == {"product_id", "score", "matched_modalities", "metadata"}

    def test_returns_an_empty_result_list_when_nothing_has_been_uploaded(
        self, search_client: TestClient
    ) -> None:
        response = search_client.post(_SEARCH_URL, data={"query": "anything"})

        assert response.status_code == 200
        assert response.json()["results"] == []

    def test_a_non_image_file_returns_422(self, search_client: TestClient) -> None:
        response = search_client.post(
            _SEARCH_URL,
            data={},
            files=_image_file(content=b"this is not image data at all"),
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_image"

    def test_category_filter_excludes_products_from_other_categories(
        self, search_client: TestClient
    ) -> None:
        shoe_id = _upload(search_client, name="Shoe Widget", category="shoes")
        shirt_id = _upload(search_client, name="Shirt Widget", category="shirts")

        response = search_client.post(_SEARCH_URL, data={"query": "widget", "category": "shirts"})

        product_ids = [result["product_id"] for result in response.json()["results"]]
        assert shirt_id in product_ids
        assert shoe_id not in product_ids

    def test_brand_filter_excludes_products_from_other_brands(
        self, search_client: TestClient
    ) -> None:
        nike_id = _upload(search_client, name="Nike Widget", brand="Nike")
        adidas_id = _upload(search_client, name="Adidas Widget", brand="Adidas")

        response = search_client.post(_SEARCH_URL, data={"query": "widget", "brand": "Nike"})

        product_ids = [result["product_id"] for result in response.json()["results"]]
        assert nike_id in product_ids
        assert adidas_id not in product_ids

    def test_price_range_filter_excludes_products_outside_the_range(
        self, search_client: TestClient
    ) -> None:
        cheap_id = _upload(search_client, name="Cheap Widget", price="5.00")
        mid_id = _upload(search_client, name="Mid Widget", price="50.00")
        expensive_id = _upload(search_client, name="Expensive Widget", price="500.00")

        response = search_client.post(
            _SEARCH_URL, data={"query": "widget", "min_price": "10", "max_price": "100"}
        )

        product_ids = [result["product_id"] for result in response.json()["results"]]
        assert mid_id in product_ids
        assert cheap_id not in product_ids
        assert expensive_id not in product_ids

    def test_top_k_limits_the_number_of_results(self, search_client: TestClient) -> None:
        for i in range(5):
            _upload(search_client, name=f"Widget {i}")

        response = search_client.post(_SEARCH_URL, data={"query": "widget", "top_k": "2"})

        assert len(response.json()["results"]) == 2

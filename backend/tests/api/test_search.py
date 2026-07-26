"""Integration tests for `POST /api/v1/products/search`.

Builds the *real* `create_app()` application, overriding
`get_upload_service`/`get_product_service`/`get_search_service` to redirect
storage to `tmp_path` and to share one tiny real CLIP model plus one
in-memory Qdrant collection across both the upload and search endpoints —
the same tiny checkpoint and in-memory-Qdrant strategy
`tests/api/test_products.py`/`tests/services/vectorstore/test_qdrant_store.py`
already use. Sharing both across upload and search is what makes these
tests genuine: a product uploaded through the real `/products/upload`
endpoint must actually be findable through the real `/products/search`
endpoint afterward.
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
from app.dependencies.product import get_product_service
from app.dependencies.search import get_search_service
from app.dependencies.upload import get_upload_service
from app.services.embeddings.clip_service import CLIPEmbeddingService
from app.services.embeddings.model_manager import ModelManager
from app.services.image_processing_service import ImageProcessingService
from app.services.product_service import ProductService
from app.services.upload_service import UploadService
from app.services.vectorstore.qdrant_store import QdrantVectorStore
from app.services.vectorstore.search_service import SearchService

_UPLOAD_URL = f"{settings.application.api_prefix}/products/upload"
_SEARCH_URL = f"{settings.application.api_prefix}/products/search"

_TINY_MODEL_NAME = "hf-internal-testing/tiny-random-CLIPModel"
_shared_model_manager = ModelManager(device="cpu")
_vector_size = _shared_model_manager.get_model(_TINY_MODEL_NAME)[0].config.projection_dim


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
        model_name=_TINY_MODEL_NAME, model_manager=_shared_model_manager
    )
    image_processing_service = ImageProcessingService(processed_dir=upload_dir / "processed")

    app.dependency_overrides[get_upload_service] = lambda: UploadService(upload_dir=upload_dir)
    app.dependency_overrides[get_product_service] = lambda: ProductService(
        upload_dir=upload_dir,
        image_processing_service=image_processing_service,
        embedding_service=embedding_service,
        vector_store=vector_store,
    )
    app.dependency_overrides[get_search_service] = lambda: SearchService(
        upload_dir=upload_dir,
        image_processing_service=image_processing_service,
        embedding_service=embedding_service,
        vector_store=vector_store,
    )


@pytest.fixture
def search_client(tmp_path: Path) -> Iterator[TestClient]:
    app = create_app()
    vector_store = QdrantVectorStore(
        client=QdrantClient(location=":memory:"),
        image_collection_name="test_search_products_image",
        image_vector_size=_vector_size,
        text_collection_name="test_search_products_text",
    )
    _override_services(app, tmp_path, vector_store=vector_store)

    with TestClient(app) as client:
        yield client


class TestSearchProducts:
    def test_finds_a_previously_uploaded_product(self, search_client: TestClient) -> None:
        content = _image_bytes(color=(10, 20, 30))
        upload_response = search_client.post(
            _UPLOAD_URL,
            data={"name": "Widget", "category": "shoes"},
            files=_image_file(content=content),
        )
        assert upload_response.status_code == 201
        product_id = upload_response.json()["product_id"]

        search_response = search_client.post(
            _SEARCH_URL,
            data={},
            files=_image_file(content=content),
        )

        assert search_response.status_code == 200
        body = search_response.json()
        product_ids = [result["product_id"] for result in body["results"]]
        assert product_id in product_ids

    def test_returned_metadata_matches_the_uploaded_product(
        self, search_client: TestClient
    ) -> None:
        content = _image_bytes(color=(40, 50, 60))
        upload_response = search_client.post(
            _UPLOAD_URL,
            data={"name": "Nike Widget", "category": "Men Tshirts", "price": "19.99"},
            files=_image_file(content=content),
        )
        product_id = upload_response.json()["product_id"]

        search_response = search_client.post(
            _SEARCH_URL,
            data={},
            files=_image_file(content=content),
        )

        match = next(
            result
            for result in search_response.json()["results"]
            if result["product_id"] == product_id
        )
        assert match["metadata"] == {
            "name": "Nike Widget",
            "category": "men-tshirts",
            "price": 19.99,
        }

    def test_never_returns_a_raw_vector(self, search_client: TestClient) -> None:
        content = _image_bytes(color=(70, 80, 90))
        search_client.post(_UPLOAD_URL, data={"name": "Widget"}, files=_image_file(content=content))

        search_response = search_client.post(
            _SEARCH_URL, data={}, files=_image_file(content=content)
        )

        for result in search_response.json()["results"]:
            assert "vector" not in result
            assert set(result.keys()) == {"product_id", "score", "metadata"}

    def test_returns_an_empty_result_list_when_nothing_has_been_uploaded(
        self, search_client: TestClient
    ) -> None:
        response = search_client.post(_SEARCH_URL, data={}, files=_image_file())

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
        shoe_content = _image_bytes(color=(11, 22, 33))
        shirt_content = _image_bytes(color=(200, 210, 220))
        shoe_response = search_client.post(
            _UPLOAD_URL,
            data={"name": "Shoe Widget", "category": "shoes"},
            files=_image_file(content=shoe_content),
        )
        shirt_response = search_client.post(
            _UPLOAD_URL,
            data={"name": "Shirt Widget", "category": "shirts"},
            files=_image_file(content=shirt_content),
        )
        shoe_id = shoe_response.json()["product_id"]
        shirt_id = shirt_response.json()["product_id"]

        search_response = search_client.post(
            _SEARCH_URL,
            data={"category": "shirts"},
            files=_image_file(content=shirt_content),
        )

        product_ids = [result["product_id"] for result in search_response.json()["results"]]
        assert shirt_id in product_ids
        assert shoe_id not in product_ids

    def test_top_k_limits_the_number_of_results(self, search_client: TestClient) -> None:
        for i in range(5):
            search_client.post(
                _UPLOAD_URL,
                data={"name": f"Widget {i}"},
                files=_image_file(content=_image_bytes(color=(i * 10, i * 10, i * 10))),
            )

        response = search_client.post(
            _SEARCH_URL,
            data={"top_k": "2"},
            files=_image_file(content=_image_bytes(color=(0, 0, 0))),
        )

        assert len(response.json()["results"]) == 2

"""Integration tests for `POST /api/v1/products/check-duplicate`.

Builds the *real* `create_app()` application, overriding
`get_upload_service`/`get_product_service`/`get_duplicate_check_service`
to redirect storage to `tmp_path` and share one tiny real CLIP model plus
one in-memory Qdrant instance across both the seeding upload and the
duplicate check — the same strategy `test_search.py` already uses.
Seeds the vector store via the real `/products/upload` endpoint (WARN
mode, so the seed itself isn't rejected), then checks that an
(almost-)identical second product is flagged, and a genuinely different
one is not.
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
from app.dependencies.duplicate import get_duplicate_check_service
from app.dependencies.product import get_product_service
from app.dependencies.upload import get_upload_service
from app.services.catalog.catalog_intelligence_service import CatalogIntelligenceService
from app.services.duplicate.duplicate_check_service import DuplicateCheckService
from app.services.duplicate.duplicate_detection_service import DuplicateDetectionService
from app.services.embeddings.base import BaseEmbeddingService
from app.services.embeddings.clip_service import CLIPEmbeddingService
from app.services.embeddings.model_manager import ModelManager
from app.services.embeddings.text_base import BaseTextEmbeddingService
from app.services.image_processing_service import ImageProcessingService
from app.services.product_service import ProductService
from app.services.upload_service import UploadService
from app.services.vectorstore.hybrid_search_service import HybridSearchService
from app.services.vectorstore.qdrant_store import QdrantVectorStore
from app.services.vectorstore.search_service import SearchService
from app.services.vectorstore.text_search_service import TextSearchService

_UPLOAD_URL = f"{settings.application.api_prefix}/products/upload"
_CHECK_URL = f"{settings.application.api_prefix}/products/check-duplicate"

_TINY_MODEL_NAME = "hf-internal-testing/tiny-random-CLIPModel"
_shared_model_manager = ModelManager(device="cpu")
_image_vector_size = _shared_model_manager.get_model(_TINY_MODEL_NAME)[0].config.projection_dim


class _FakeTextEmbeddingService(BaseTextEmbeddingService):
    """Deterministic: same text -> same vector, so near-identical products score highly."""

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


def _image_bytes(
    *, size: tuple[int, int] = (40, 40), color: tuple[int, int, int] = (200, 30, 30)
) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="JPEG")
    return buffer.getvalue()


def _image_file(
    *,
    filename: str = "photo.jpg",
    content: bytes | None = None,
    color: tuple[int, int, int] = (200, 30, 30),
) -> dict[str, tuple[str, io.BytesIO, str]]:
    body = content if content is not None else _image_bytes(color=color)
    return {"file": (filename, io.BytesIO(body), "image/jpeg")}


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
    # Every DuplicateDetectionService below must share this same
    # hybrid_search_service (pointed at upload_dir/vector_store) —
    # otherwise ProductService's own default DuplicateDetectionService
    # would fall back to production settings.storage.upload_dir, which
    # doesn't hold this test's stored file.
    duplicate_detection_service = DuplicateDetectionService(
        hybrid_search_service=hybrid_search_service, threshold=0.80
    )

    app.dependency_overrides[get_upload_service] = lambda: UploadService(upload_dir=upload_dir)
    app.dependency_overrides[get_product_service] = lambda: ProductService(
        upload_dir=upload_dir,
        image_processing_service=image_processing_service,
        embedding_service=embedding_service,
        text_embedding_service=text_embedding_service,
        # WARN (not OFF): this suite seeds the vector store through a real
        # upload and must not have that seed rejected.
        duplicate_detection_mode=DuplicateDetectionMode.WARN,
        duplicate_detection_service=duplicate_detection_service,
        vector_store=vector_store,
    )

    app.dependency_overrides[get_duplicate_check_service] = lambda: DuplicateCheckService(
        image_processing_service=image_processing_service,
        catalog_intelligence_service=CatalogIntelligenceService(),
        duplicate_detection_service=duplicate_detection_service,
        upload_dir=upload_dir,
    )


@pytest.fixture
def check_duplicate_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    # This suite seeds products via the real /products/upload endpoint and
    # expects the pre-Phase-12 synchronous 201 response — the async
    # pipeline (Phase 12, on by default) would instead queue the upload
    # for a worker that never runs in these tests.
    monkeypatch.setattr(settings.async_pipeline, "enabled", False)
    app = create_app()
    vector_store = QdrantVectorStore(
        client=QdrantClient(location=":memory:"),
        image_collection_name="test_check_duplicate_image",
        image_vector_size=_image_vector_size,
        text_collection_name="test_check_duplicate_text",
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


def _seed_product(client: TestClient) -> str:
    response = client.post(
        _UPLOAD_URL,
        data={
            "name": "Nike Air Zoom Pegasus",
            "brand": "Nike",
            "category": "Running Shoes",
            "description": "Lightweight breathable red running shoe with mesh upper",
        },
        files=_image_file(),
    )
    assert response.status_code == 201
    product_id: str = response.json()["product_id"]
    return product_id


class TestCheckDuplicateFindsAMatch:
    def test_an_almost_identical_product_is_flagged_a_duplicate(
        self, check_duplicate_client: TestClient
    ) -> None:
        seeded_product_id = _seed_product(check_duplicate_client)

        response = check_duplicate_client.post(
            _CHECK_URL,
            data={
                "name": "Nike Air Zoom Pegasus",
                "brand": "Nike",
                "category": "Running Shoes",
                "description": "Lightweight breathable red running shoe with mesh upper",
            },
            files=_image_file(),
        )

        assert response.status_code == 200
        body = response.json()
        assert body["duplicate"] is True
        assert body["matched_product"] == seeded_product_id
        assert body["signals"] is not None
        assert len(body["top_candidates"]) == 1

    def test_never_returns_a_raw_vector(self, check_duplicate_client: TestClient) -> None:
        _seed_product(check_duplicate_client)

        response = check_duplicate_client.post(
            _CHECK_URL,
            data={"name": "Widget"},
            files=_image_file(),
        )

        assert "vector" not in response.text
        assert "embedding" not in response.text


class TestCheckDuplicateFindsNoMatch:
    def test_a_completely_different_product_is_not_flagged(
        self, check_duplicate_client: TestClient
    ) -> None:
        _seed_product(check_duplicate_client)

        response = check_duplicate_client.post(
            _CHECK_URL,
            data={
                "name": "Vintage Wooden Chair",
                "brand": "Acme",
                "category": "Furniture",
                "description": "A sturdy oak dining chair with a carved backrest",
            },
            files=_image_file(color=(10, 200, 10)),
        )

        assert response.status_code == 200
        body = response.json()
        assert body["duplicate"] is False
        assert body["matched_product"] is None

    def test_an_empty_catalog_yields_no_candidates(
        self, check_duplicate_client: TestClient
    ) -> None:
        response = check_duplicate_client.post(
            _CHECK_URL,
            data={"name": "Widget"},
            files=_image_file(),
        )

        assert response.status_code == 200
        body = response.json()
        assert body["duplicate"] is False
        assert body["top_candidates"] == []
        assert body["signals"] is None


class TestCheckDuplicateOverrides:
    def test_a_low_threshold_override_flags_a_weaker_match(
        self, check_duplicate_client: TestClient
    ) -> None:
        _seed_product(check_duplicate_client)

        response = check_duplicate_client.post(
            _CHECK_URL,
            data={"name": "Something else entirely", "threshold": "0.01"},
            files=_image_file(color=(10, 200, 10)),
        )

        assert response.status_code == 200
        assert response.json()["duplicate"] is True

    def test_only_a_required_name_is_needed(self, check_duplicate_client: TestClient) -> None:
        response = check_duplicate_client.post(
            _CHECK_URL,
            data={"name": "Minimal Widget"},
            files=_image_file(),
        )

        assert response.status_code == 200


class TestCheckDuplicateValidation:
    def test_missing_required_name_returns_the_standard_error_envelope(
        self, check_duplicate_client: TestClient
    ) -> None:
        response = check_duplicate_client.post(_CHECK_URL, files=_image_file())

        assert response.status_code == 422

    def test_a_non_image_file_returns_422(self, check_duplicate_client: TestClient) -> None:
        response = check_duplicate_client.post(
            _CHECK_URL,
            data={"name": "Widget"},
            files={"file": ("not-an-image.jpg", io.BytesIO(b"not an image"), "image/jpeg")},
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_image"

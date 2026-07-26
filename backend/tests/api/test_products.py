"""Integration tests for `POST /api/v1/products/upload`.

Builds the *real* `create_app()` application (not a throwaway app) but
overrides the `get_upload_service` and `get_product_service` dependencies
(`app.dependency_overrides[...] = ...`) to redirect storage to the same
`tmp_path` — this is exactly the seam `app/dependencies/` exists for (see
that package's module docstrings), and means these tests exercise the
real router, real middleware, and real global exception handlers without
ever writing into the real `backend/storage/` directory.

Every uploaded file here is a real, Pillow-generated JPEG
(`_valid_jpeg_bytes`) — since Phase 3, the pipeline actually decodes and
validates image content, so placeholder byte strings like
`b"fake-image-bytes"` (used before Phase 3) no longer make it past
`ImageProcessingService`.
"""

import hashlib
import io
import uuid
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
from app.dependencies.product import get_product_service
from app.dependencies.upload import get_upload_service
from app.services.embeddings.clip_service import CLIPEmbeddingService
from app.services.embeddings.model_manager import ModelManager
from app.services.embeddings.text_base import BaseTextEmbeddingService
from app.services.image_processing_service import ImageProcessingService
from app.services.product_service import ProductService
from app.services.upload_service import UploadService
from app.services.vectorstore.base import VectorCollection
from app.services.vectorstore.qdrant_store import QdrantVectorStore

_UPLOAD_URL = f"{settings.application.api_prefix}/products/upload"

# The same tiny, fast-loading real CLIP checkpoint the embeddings test
# suite uses — proves the real embedding pipeline is wired end-to-end
# through the HTTP layer, without paying full CLIP's download/load cost.
# One shared `ModelManager` across every test in this file so it's loaded
# once, not once per request.
_TINY_MODEL_NAME = "hf-internal-testing/tiny-random-CLIPModel"
_shared_model_manager = ModelManager(device="cpu")


class _FakeTextEmbeddingService(BaseTextEmbeddingService):
    """A fast, deterministic stand-in for the real Sentence Transformers
    service — these tests exercise the upload *pipeline*, not text
    embedding quality (that's `test_sentence_transformer_service.py`'s
    job), so there's no reason to pay a real model's load cost here.
    """

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


# An in-memory Qdrant instance (the real client's own local mode, not a
# fake) instead of a real server — these tests don't need to assert
# anything about the vector store itself (that's `test_qdrant_store.py`'s
# job), just that ProductService's upsert calls don't blow up the
# request. `text_vector_size` matches `_FakeTextEmbeddingService.dimension`.
_image_vector_size = _shared_model_manager.get_model(_TINY_MODEL_NAME)[0].config.projection_dim
_shared_vector_store = QdrantVectorStore(
    client=QdrantClient(location=":memory:"),
    image_collection_name="test_products_image",
    image_vector_size=_image_vector_size,
    text_collection_name="test_products_text",
    text_vector_size=4,
)


def _valid_jpeg_bytes(
    *, size: tuple[int, int] = (20, 20), color: tuple[int, int, int] = (255, 0, 0)
) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="JPEG")
    return buffer.getvalue()


def _override_services(app: FastAPI, upload_dir: Path) -> None:
    app.dependency_overrides[get_upload_service] = lambda: UploadService(upload_dir=upload_dir)
    app.dependency_overrides[get_product_service] = lambda: ProductService(
        upload_dir=upload_dir,
        image_processing_service=ImageProcessingService(processed_dir=upload_dir / "processed"),
        embedding_service=CLIPEmbeddingService(
            model_name=_TINY_MODEL_NAME, model_manager=_shared_model_manager
        ),
        text_embedding_service=_FakeTextEmbeddingService(),
        # This suite covers the upload pipeline itself, not duplicate
        # detection (see tests/services/test_product_service.py's
        # TestProcessUploadDuplicateDetection and
        # tests/services/duplicate/) — OFF avoids every upload here also
        # re-running a real hybrid search against `_shared_vector_store`.
        duplicate_detection_mode=DuplicateDetectionMode.OFF,
        vector_store=_shared_vector_store,
    )


@pytest.fixture
def upload_client(tmp_path: Path) -> Iterator[TestClient]:
    app = create_app()
    _override_services(app, tmp_path)

    with TestClient(app) as client:
        yield client


def _image_file(
    *,
    filename: str = "photo.jpg",
    content_type: str = "image/jpeg",
    content: bytes | None = None,
) -> dict[str, tuple[str, io.BytesIO, str]]:
    return {
        "file": (
            filename,
            io.BytesIO(content if content is not None else _valid_jpeg_bytes()),
            content_type,
        )
    }


class TestUploadProductSuccess:
    def test_returns_201_with_normalized_product_and_image_metadata(
        self, upload_client: TestClient, tmp_path: Path
    ) -> None:
        response = upload_client.post(
            _UPLOAD_URL,
            data={
                "name": " Nike ",
                "brand": "  Nike  ",
                "description": "  A fine shirt  ",
                "category": "Men Tshirts",
            },
            files=_image_file(),
        )

        assert response.status_code == 201
        body = response.json()
        assert body["product"] == {
            "name": "Nike",
            "brand": "Nike",
            "description": "A fine shirt",
            "category": "men-tshirts",
            "price": None,
        }
        assert body["image"]["original_filename"] == "photo.jpg"
        assert body["image"]["content_type"] == "image/jpeg"

    def test_returns_a_valid_product_id_and_checksum(
        self, upload_client: TestClient, tmp_path: Path
    ) -> None:
        content = _valid_jpeg_bytes(color=(1, 2, 3))
        response = upload_client.post(
            _UPLOAD_URL,
            data={"name": "Widget"},
            files=_image_file(content=content),
        )

        body = response.json()
        assert uuid.UUID(body["product_id"])  # a real UUID string
        assert body["checksum_sha256"] == hashlib.sha256(content).hexdigest()

    def test_returns_processed_image_dimensions_and_format(self, upload_client: TestClient) -> None:
        response = upload_client.post(
            _UPLOAD_URL,
            data={"name": "Widget"},
            files=_image_file(content=_valid_jpeg_bytes(size=(30, 15))),
        )

        body = response.json()
        assert body["processed_image"] == {
            "width": 30,
            "height": 15,
            "format": "JPEG",
            "color_mode": "RGB",
        }

    def test_actually_writes_the_file_to_the_overridden_upload_directory(
        self, upload_client: TestClient, tmp_path: Path
    ) -> None:
        content = _valid_jpeg_bytes(color=(9, 9, 9))
        response = upload_client.post(
            _UPLOAD_URL,
            data={"name": "Widget"},
            files=_image_file(content=content),
        )

        stored_filename = response.json()["image"]["stored_filename"]
        stored_path = tmp_path / stored_filename

        assert stored_path.read_bytes() == content

    def test_returns_embedding_model_name_and_dimension_without_the_raw_vector(
        self, upload_client: TestClient
    ) -> None:
        response = upload_client.post(
            _UPLOAD_URL,
            data={"name": "Widget"},
            files=_image_file(),
        )

        body = response.json()
        model, _processor, _device = _shared_model_manager.get_model(_TINY_MODEL_NAME)
        assert body["embedding"] == {
            "model_name": _TINY_MODEL_NAME,
            "dimension": model.config.projection_dim,
        }
        assert "vector" not in body["embedding"]

    def test_only_a_required_name_is_needed(self, upload_client: TestClient) -> None:
        response = upload_client.post(
            _UPLOAD_URL,
            data={"name": "Minimal Widget"},
            files=_image_file(),
        )

        assert response.status_code == 201
        assert response.json()["product"]["name"] == "Minimal Widget"

    def test_returns_a_non_duplicate_result_when_detection_is_off(
        self, upload_client: TestClient
    ) -> None:
        # This fixture's ProductService runs with DuplicateDetectionMode.OFF
        # (see _override_services) — the response must still always
        # include a `duplicate` object, just a neutral one.
        response = upload_client.post(
            _UPLOAD_URL,
            data={"name": "Widget"},
            files=_image_file(),
        )

        body = response.json()["duplicate"]
        assert body["is_duplicate"] is False
        assert body["matched_product"] is None


class TestUploadIndexesBothCollections:
    """Confirms the full upload -> image embedding -> text embedding ->
    image index -> text index pipeline actually reaches the vector store,
    not just that `ProductService`'s own unit tests believe it does.
    """

    async def test_the_uploaded_product_exists_in_the_image_collection(
        self, upload_client: TestClient
    ) -> None:
        response = upload_client.post(_UPLOAD_URL, data={"name": "Widget"}, files=_image_file())
        product_id = uuid.UUID(response.json()["product_id"])

        assert await _shared_vector_store.exists(VectorCollection.IMAGE, product_id) is True

    async def test_the_uploaded_product_exists_in_the_text_collection(
        self, upload_client: TestClient
    ) -> None:
        response = upload_client.post(_UPLOAD_URL, data={"name": "Widget"}, files=_image_file())
        product_id = uuid.UUID(response.json()["product_id"])

        assert await _shared_vector_store.exists(VectorCollection.TEXT, product_id) is True


class TestUploadProductValidation:
    def test_missing_required_name_returns_the_standard_error_envelope(
        self, upload_client: TestClient
    ) -> None:
        response = upload_client.post(
            _UPLOAD_URL,
            data={},
            files=_image_file(),
        )

        assert response.status_code == 422
        body = response.json()
        assert body["success"] is False
        assert body["error"]["code"] == "validation_error"

    def test_a_name_that_is_only_whitespace_is_rejected_by_product_service(
        self, upload_client: TestClient
    ) -> None:
        # "   " passes Form(min_length=1) (raw length 3) but is blank once
        # ProductService normalizes it - proving the defense-in-depth
        # validator in app.validators.product_validator is actually
        # reachable end-to-end through a real HTTP request, not just in
        # its own unit tests.
        response = upload_client.post(
            _UPLOAD_URL,
            data={"name": "   "},
            files=_image_file(),
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"

    def test_disallowed_extension_returns_415(self, upload_client: TestClient) -> None:
        response = upload_client.post(
            _UPLOAD_URL,
            data={"name": "Widget"},
            files=_image_file(filename="document.txt", content_type="text/plain", content=b"hi"),
        )

        assert response.status_code == 415
        assert response.json()["error"]["code"] == "unsupported_media_type"

    def test_disallowed_mime_type_returns_415(self, upload_client: TestClient) -> None:
        response = upload_client.post(
            _UPLOAD_URL,
            data={"name": "Widget"},
            files=_image_file(filename="photo.jpg", content_type="application/pdf"),
        )

        assert response.status_code == 415
        assert response.json()["error"]["code"] == "unsupported_media_type"

    def test_negative_price_returns_the_standard_error_envelope(
        self, upload_client: TestClient
    ) -> None:
        response = upload_client.post(
            _UPLOAD_URL,
            data={"name": "Widget", "price": "-5"},
            files=_image_file(),
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"

    def test_a_non_image_file_with_an_allowed_extension_returns_422(
        self, upload_client: TestClient
    ) -> None:
        # Extension/MIME type both claim "jpg"/"image/jpeg" (passing
        # UploadService), but the bytes aren't a real image at all —
        # caught by ImageProcessingService (Phase 3), not UploadService.
        response = upload_client.post(
            _UPLOAD_URL,
            data={"name": "Widget"},
            files=_image_file(content=b"this is not image data at all"),
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_image"


class TestUploadProductSizeLimit:
    def test_oversized_file_returns_413(self, tmp_path: Path) -> None:
        app = create_app()
        _override_services(app, tmp_path)
        app.dependency_overrides[get_upload_service] = lambda: UploadService(
            upload_dir=tmp_path, max_upload_size_mb=1
        )

        with TestClient(app) as client:
            response = client.post(
                _UPLOAD_URL,
                data={"name": "Widget"},
                files=_image_file(content=b"0" * (2 * 1024 * 1024)),
            )

        assert response.status_code == 413
        assert response.json()["error"]["code"] == "file_too_large"
        # No *file* was written anywhere — FastAPI resolving the
        # ProductService dependency still eagerly creates the (empty)
        # processed/ directory even though this request fails before ever
        # using it, the same way UploadService's upload_dir always exists.
        written_files = [path for path in tmp_path.rglob("*") if path.is_file()]
        assert written_files == []

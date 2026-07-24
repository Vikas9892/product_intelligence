"""Integration tests for `POST /api/v1/products/upload`.

Builds the *real* `create_app()` application (not a throwaway app) but
overrides both the `get_upload_service` and `get_product_service`
dependencies (`app.dependency_overrides[...] = ...`) to redirect storage
to the same `tmp_path` — this is exactly the seam `app/dependencies/`
exists for (see that package's module docstrings), and means these tests
exercise the real router, real middleware, and real global exception
handlers without ever writing into the real `backend/storage/` directory.
"""

import hashlib
import io
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.application import create_app
from app.core.config import settings
from app.dependencies.product import get_product_service
from app.dependencies.upload import get_upload_service
from app.services.product_service import ProductService
from app.services.upload_service import UploadService

_UPLOAD_URL = f"{settings.application.api_prefix}/products/upload"


def _override_services(app: FastAPI, upload_dir: Path) -> None:
    app.dependency_overrides[get_upload_service] = lambda: UploadService(upload_dir=upload_dir)
    app.dependency_overrides[get_product_service] = lambda: ProductService(upload_dir=upload_dir)


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
    content: bytes = b"fake-image-bytes",
) -> dict[str, tuple[str, io.BytesIO, str]]:
    return {"file": (filename, io.BytesIO(content), content_type)}


class TestUploadProductSuccess:
    def test_returns_201_with_normalized_product_and_image_metadata(
        self, upload_client: TestClient, tmp_path: Path
    ) -> None:
        response = upload_client.post(
            _UPLOAD_URL,
            data={"name": " Nike ", "description": "  A fine shirt  ", "category": "Men Tshirts"},
            files=_image_file(),
        )

        assert response.status_code == 201
        body = response.json()
        assert body["product"] == {
            "name": "Nike",
            "description": "A fine shirt",
            "category": "men-tshirts",
            "price": None,
        }
        assert body["image"]["original_filename"] == "photo.jpg"
        assert body["image"]["content_type"] == "image/jpeg"
        assert body["image"]["size_bytes"] == len(b"fake-image-bytes")

    def test_returns_a_valid_product_id_and_checksum(
        self, upload_client: TestClient, tmp_path: Path
    ) -> None:
        content = b"specific bytes for checksum verification"
        response = upload_client.post(
            _UPLOAD_URL,
            data={"name": "Widget"},
            files=_image_file(content=content),
        )

        body = response.json()
        assert uuid.UUID(body["product_id"])  # a real UUID string
        assert body["checksum_sha256"] == hashlib.sha256(content).hexdigest()

    def test_actually_writes_the_file_to_the_overridden_upload_directory(
        self, upload_client: TestClient, tmp_path: Path
    ) -> None:
        response = upload_client.post(
            _UPLOAD_URL,
            data={"name": "Widget"},
            files=_image_file(content=b"specific-test-content"),
        )

        stored_filename = response.json()["image"]["stored_filename"]
        stored_path = tmp_path / stored_filename

        assert stored_path.read_bytes() == b"specific-test-content"

    def test_only_a_required_name_is_needed(self, upload_client: TestClient) -> None:
        response = upload_client.post(
            _UPLOAD_URL,
            data={"name": "Minimal Widget"},
            files=_image_file(),
        )

        assert response.status_code == 201
        assert response.json()["product"]["name"] == "Minimal Widget"


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
            files=_image_file(filename="document.txt", content_type="text/plain"),
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
        assert list(tmp_path.iterdir()) == []

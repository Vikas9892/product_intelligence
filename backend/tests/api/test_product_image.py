"""Integration tests for `GET /products/{id}/image`.

Regression tests for a system that indexed images, priced from image
similarity and detected duplicates on visual signal -- and could not show the
user the image it reasoned about, because no route read one back.
"""

import io
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.application import create_app
from app.dependencies.product import get_product_image_service
from app.models.search import StoredPoint
from app.services.product_image_service import (
    THUMBNAIL_SIZE_PX,
    ProductImageService,
)

_WITH_IMAGE = UUID("11111111-1111-1111-1111-111111111111")
_WITHOUT_IMAGE = UUID("22222222-2222-2222-2222-222222222222")
_TRAVERSAL = UUID("33333333-3333-3333-3333-333333333333")
_STORED_NAME = "abc123.png"


class _FakeVectorStore:
    """Returns payloads without touching Qdrant."""

    def __init__(self) -> None:
        self._payloads: dict[UUID, dict[str, object]] = {
            _WITH_IMAGE: {"name": "Aurora Runner", "image_filename": _STORED_NAME},
            # Indexed before image serving existed: no reference at all.
            _WITHOUT_IMAGE: {"name": "Legacy Product"},
            # A corrupted payload attempting to escape the storage root.
            _TRAVERSAL: {"name": "Hostile", "image_filename": "../../../../etc/passwd"},
        }

    async def retrieve_image(self, product_id: UUID) -> StoredPoint | None:
        payload = self._payloads.get(product_id)
        if payload is None:
            return None
        return StoredPoint(product_id=product_id, vector=[0.0], metadata=payload)

    async def retrieve_text(self, product_id: UUID) -> StoredPoint | None:
        return await self.retrieve_image(product_id)


def _write_jpeg(path: Path, size: tuple[int, int] = (900, 700)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, (40, 90, 180)).save(path, format="JPEG", quality=90)


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    uploads = tmp_path / "uploads"
    processed = tmp_path / "processed"
    # The processed variant, whose name is derived from the stored one.
    _write_jpeg(processed / "abc123.jpg")

    service = ProductImageService(
        vector_store=_FakeVectorStore(),  # type: ignore[arg-type]
        upload_dir=uploads,
        processed_dir=processed,
        thumbnail_dir=processed / "thumbnails",
    )

    app = create_app()
    app.dependency_overrides[get_product_image_service] = lambda: service
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


class TestImageRoundTrip:
    def test_serves_a_real_image_with_the_right_content_type(self, client: TestClient) -> None:
        response = client.get(f"/api/v1/products/{_WITH_IMAGE}/image")

        assert response.status_code == 200
        assert response.headers["content-type"] == "image/jpeg"
        # A genuinely decodable image, not an error page with a hopeful header.
        with Image.open(io.BytesIO(response.content)) as served:
            assert served.format == "JPEG"
            assert served.size == (900, 700)

    def test_sets_a_long_immutable_cache_header(self, client: TestClient) -> None:
        response = client.get(f"/api/v1/products/{_WITH_IMAGE}/image")

        cache_control = response.headers["cache-control"]
        assert "immutable" in cache_control
        assert "max-age=" in cache_control

    def test_thumbnail_variant_is_smaller(self, client: TestClient) -> None:
        full = client.get(f"/api/v1/products/{_WITH_IMAGE}/image")
        thumb = client.get(f"/api/v1/products/{_WITH_IMAGE}/image?thumbnail=true")

        assert thumb.status_code == 200
        with Image.open(io.BytesIO(thumb.content)) as served:
            assert max(served.size) == THUMBNAIL_SIZE_PX
        assert len(thumb.content) < len(full.content)

    def test_thumbnail_is_generated_once_and_reused(self, client: TestClient) -> None:
        first = client.get(f"/api/v1/products/{_WITH_IMAGE}/image?thumbnail=true")
        second = client.get(f"/api/v1/products/{_WITH_IMAGE}/image?thumbnail=true")

        assert first.content == second.content


class TestMissingImage:
    def test_a_product_with_no_image_reference_is_404(self, client: TestClient) -> None:
        """Distinct from the product not existing, and from images being unsupported."""
        response = client.get(f"/api/v1/products/{_WITHOUT_IMAGE}/image")

        assert response.status_code == 404
        error = response.json()["error"]
        assert error["code"] == "resource_not_found"
        assert "no stored image" in error["message"]

    def test_an_unknown_product_is_404(self, client: TestClient) -> None:
        response = client.get(f"/api/v1/products/{uuid4()}/image")

        assert response.status_code == 404

    def test_a_malformed_id_is_a_validation_error(self, client: TestClient) -> None:
        response = client.get("/api/v1/products/not-a-uuid/image")

        assert response.status_code == 422


class TestPathTraversal:
    """The one route that turns an identifier into a filesystem read."""

    def test_a_traversing_filename_is_rejected_not_served(self, client: TestClient) -> None:
        response = client.get(f"/api/v1/products/{_TRAVERSAL}/image")

        # Refused as "no image", never served, and never a 500.
        assert response.status_code == 404
        assert response.headers["content-type"].startswith("application/json")

    def test_traversal_is_refused_even_when_the_target_exists(self, tmp_path: Path) -> None:
        """A real file outside the root must still not be reachable."""
        outside = tmp_path / "secret.txt"
        outside.write_text("do not serve me", encoding="utf-8")

        service = ProductImageService(
            vector_store=_FakeVectorStore(),  # type: ignore[arg-type]
            upload_dir=tmp_path / "uploads",
            processed_dir=tmp_path / "processed",
        )

        assert service._safe_path(tmp_path / "processed", "../secret.txt") is None

"""Unit tests for `ImageAttributeExtractionService`.

Every test writes a real, small Pillow-generated image to `tmp_path` and
runs the service against it — no mocking, since this service's whole job
is genuine pixel analysis (Pillow I/O), the same reasoning
`test_image_processing_service.py` already uses for `ImageProcessingService`.
"""

from pathlib import Path

import pytest
from PIL import Image

from app.exceptions.errors import CatalogIntelligenceException
from app.models.catalog_tags import Source
from app.services.catalog.image_attribute_service import ImageAttributeExtractionService


def _save(tmp_path: Path, image: Image.Image, *, name: str = "photo.jpg") -> Path:
    path = tmp_path / name
    image.save(path, format="JPEG")
    return path


class TestExtractAttributes:
    async def test_returns_a_color_prediction(self, tmp_path: Path) -> None:
        path = _save(tmp_path, Image.new("RGB", (40, 40), (200, 10, 10)))
        service = ImageAttributeExtractionService()

        predictions = await service.extract_attributes(path)

        assert len(predictions) == 1
        assert predictions[0].attribute == "color"
        assert predictions[0].value == "Red"
        assert predictions[0].source is Source.IMAGE

    async def test_raises_catalog_intelligence_exception_for_a_corrupt_file(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "not-an-image.jpg"
        path.write_bytes(b"not an image")
        service = ImageAttributeExtractionService()

        with pytest.raises(CatalogIntelligenceException):
            await service.extract_attributes(path)


class TestGenerateTags:
    async def test_portrait_image_is_tagged_portrait(self, tmp_path: Path) -> None:
        path = _save(tmp_path, Image.new("RGB", (50, 100), (128, 128, 128)))
        service = ImageAttributeExtractionService()

        tags = await service.generate_tags(path)

        tag_values = {tag.tag for tag in tags}
        assert "portrait" in tag_values

    async def test_landscape_image_is_tagged_landscape(self, tmp_path: Path) -> None:
        path = _save(tmp_path, Image.new("RGB", (100, 50), (128, 128, 128)))
        service = ImageAttributeExtractionService()

        tags = await service.generate_tags(path)

        tag_values = {tag.tag for tag in tags}
        assert "landscape" in tag_values

    async def test_a_transparent_image_is_handled_without_error(self, tmp_path: Path) -> None:
        # Saved as JPEG (no alpha channel support), matching what
        # ImageProcessingService actually hands this service in practice
        # (Phase 3 always flattens transparency before this point) — this
        # proves an originally-RGBA source still works end-to-end.
        rgba = Image.new("RGBA", (60, 60), (0, 200, 0, 128))
        path = tmp_path / "photo.jpg"
        rgba.convert("RGB").save(path, format="JPEG")
        service = ImageAttributeExtractionService()

        tags = await service.generate_tags(path)

        assert len(tags) == 4

    async def test_a_grayscale_image_is_handled_without_error(self, tmp_path: Path) -> None:
        path = _save(tmp_path, Image.new("L", (60, 60), 200))
        service = ImageAttributeExtractionService()

        tags = await service.generate_tags(path)

        tag_values = {tag.tag for tag in tags}
        assert "bright" in tag_values

    async def test_a_low_resolution_image_is_tagged_low_resolution(self, tmp_path: Path) -> None:
        path = _save(tmp_path, Image.new("RGB", (80, 80), (0, 0, 0)))
        service = ImageAttributeExtractionService()

        tags = await service.generate_tags(path)

        tag_values = {tag.tag for tag in tags}
        assert "low_resolution" in tag_values

    async def test_returns_exactly_four_tags(self, tmp_path: Path) -> None:
        path = _save(tmp_path, Image.new("RGB", (100, 100), (10, 10, 200)))
        service = ImageAttributeExtractionService()

        tags = await service.generate_tags(path)

        assert len(tags) == 4
        for tag in tags:
            assert 0.0 <= tag.confidence <= 1.0
            assert tag.source is Source.IMAGE

    async def test_raises_catalog_intelligence_exception_for_a_corrupt_file(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "not-an-image.jpg"
        path.write_bytes(b"not an image")
        service = ImageAttributeExtractionService()

        with pytest.raises(CatalogIntelligenceException):
            await service.generate_tags(path)

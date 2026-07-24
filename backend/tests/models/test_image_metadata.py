"""Unit tests for the internal `ImageMetadata` domain model."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.models.image_metadata import ImageMetadata


def _metadata(**overrides: object) -> ImageMetadata:
    defaults: dict[str, object] = {
        "width": 800,
        "height": 600,
        "format": "JPEG",
        "color_mode": "RGB",
        "original_path": Path("/tmp/uploads/abc.jpg"),
        "processed_path": Path("/tmp/processed/abc.jpg"),
    }
    defaults.update(overrides)
    return ImageMetadata(**defaults)


class TestImageMetadata:
    def test_constructs_with_all_fields(self) -> None:
        metadata = _metadata()

        assert metadata.width == 800
        assert metadata.height == 600
        assert metadata.format == "JPEG"
        assert metadata.color_mode == "RGB"
        assert metadata.original_path == Path("/tmp/uploads/abc.jpg")
        assert metadata.processed_path == Path("/tmp/processed/abc.jpg")

    def test_rejects_a_non_positive_width(self) -> None:
        with pytest.raises(ValidationError):
            _metadata(width=0)

    def test_rejects_a_non_positive_height(self) -> None:
        with pytest.raises(ValidationError):
            _metadata(height=-1)

    def test_round_trips_through_model_dump_and_validate(self) -> None:
        metadata = _metadata()

        dumped = metadata.model_dump(mode="json")
        restored = ImageMetadata.model_validate(dumped)

        assert restored == metadata

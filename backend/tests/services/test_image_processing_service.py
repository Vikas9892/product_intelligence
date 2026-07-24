"""Unit tests for `ImageProcessingService`, against real files on disk."""

from pathlib import Path

import pytest
from PIL import Image

from app.exceptions.errors import (
    ImageTooLargeException,
    InvalidImageException,
    UnsupportedMediaTypeException,
)
from app.services.image_processing_service import ImageProcessingService
from app.validators.image_validator import ImageValidator

_EXIF_ORIENTATION_TAG = 0x0112


def _save_image(
    upload_dir: Path,
    *,
    name: str = "photo.jpg",
    size: tuple[int, int] = (40, 20),
    mode: str = "RGB",
    color: tuple[int, ...] = (255, 0, 0),
    fmt: str = "JPEG",
) -> Path:
    upload_dir.mkdir(parents=True, exist_ok=True)
    path = upload_dir / name
    Image.new(mode, size, color).save(path, format=fmt)
    return path


def _save_image_with_exif_orientation(
    upload_dir: Path, *, orientation: int, size: tuple[int, int] = (40, 20)
) -> Path:
    upload_dir.mkdir(parents=True, exist_ok=True)
    path = upload_dir / "rotated.jpg"
    image = Image.new("RGB", size, (0, 255, 0))
    exif = image.getexif()
    exif[_EXIF_ORIENTATION_TAG] = orientation
    image.save(path, format="JPEG", exif=exif)
    return path


class TestProcessImageSuccess:
    async def test_produces_a_processed_jpeg_with_metadata(self, tmp_path: Path) -> None:
        upload_dir = tmp_path / "uploads"
        processed_dir = tmp_path / "processed"
        original_path = _save_image(upload_dir, size=(40, 20))
        service = ImageProcessingService(processed_dir=processed_dir)

        metadata = await service.process_image(original_path, "photo.jpg")

        assert metadata.width == 40
        assert metadata.height == 20
        assert metadata.format == "JPEG"
        assert metadata.color_mode == "RGB"
        assert metadata.original_path == original_path
        assert metadata.processed_path.is_file()
        assert metadata.processed_path.suffix == ".jpg"

    async def test_processed_output_is_actually_a_valid_jpeg(self, tmp_path: Path) -> None:
        upload_dir = tmp_path / "uploads"
        processed_dir = tmp_path / "processed"
        original_path = _save_image(upload_dir)
        service = ImageProcessingService(processed_dir=processed_dir)

        metadata = await service.process_image(original_path, "photo.jpg")

        with Image.open(metadata.processed_path) as reopened:
            assert reopened.format == "JPEG"
            assert reopened.mode == "RGB"

    async def test_converts_rgba_png_to_rgb_jpeg(self, tmp_path: Path) -> None:
        upload_dir = tmp_path / "uploads"
        processed_dir = tmp_path / "processed"
        original_path = _save_image(
            upload_dir, name="photo.png", mode="RGBA", color=(10, 20, 30, 128), fmt="PNG"
        )
        service = ImageProcessingService(processed_dir=processed_dir)

        metadata = await service.process_image(original_path, "photo.png")

        assert metadata.color_mode == "RGB"
        assert metadata.format == "JPEG"

    async def test_resizes_an_oversized_image_preserving_aspect_ratio(self, tmp_path: Path) -> None:
        upload_dir = tmp_path / "uploads"
        processed_dir = tmp_path / "processed"
        original_path = _save_image(upload_dir, size=(400, 200))
        service = ImageProcessingService(processed_dir=processed_dir, max_output_dimension_px=100)

        metadata = await service.process_image(original_path, "photo.jpg")

        assert metadata.width == 100
        assert metadata.height == 50

    async def test_leaves_a_small_image_at_its_original_size(self, tmp_path: Path) -> None:
        upload_dir = tmp_path / "uploads"
        processed_dir = tmp_path / "processed"
        original_path = _save_image(upload_dir, size=(40, 20))
        service = ImageProcessingService(processed_dir=processed_dir, max_output_dimension_px=1024)

        metadata = await service.process_image(original_path, "photo.jpg")

        assert (metadata.width, metadata.height) == (40, 20)

    async def test_processes_a_tiny_image_without_error(self, tmp_path: Path) -> None:
        upload_dir = tmp_path / "uploads"
        processed_dir = tmp_path / "processed"
        original_path = _save_image(upload_dir, name="tiny.jpg", size=(1, 1))
        service = ImageProcessingService(processed_dir=processed_dir)

        metadata = await service.process_image(original_path, "tiny.jpg")

        assert (metadata.width, metadata.height) == (1, 1)

    async def test_applies_exif_orientation_before_saving(self, tmp_path: Path) -> None:
        upload_dir = tmp_path / "uploads"
        processed_dir = tmp_path / "processed"
        # Orientation 6 = rotate 90 -> width/height swap after correction.
        original_path = _save_image_with_exif_orientation(upload_dir, orientation=6, size=(40, 20))
        service = ImageProcessingService(processed_dir=processed_dir)

        metadata = await service.process_image(original_path, "rotated.jpg")

        assert (metadata.width, metadata.height) == (20, 40)

    async def test_creates_the_processed_directory_if_missing(self, tmp_path: Path) -> None:
        nested_dir = tmp_path / "does" / "not" / "exist"

        ImageProcessingService(processed_dir=nested_dir)

        assert nested_dir.is_dir()


class TestProcessImageValidationFailures:
    async def test_propagates_invalid_image_exception_for_a_corrupt_file(
        self, tmp_path: Path
    ) -> None:
        upload_dir = tmp_path / "uploads"
        upload_dir.mkdir(parents=True)
        original_path = upload_dir / "corrupt.jpg"
        original_path.write_bytes(b"not an image")
        service = ImageProcessingService(processed_dir=tmp_path / "processed")

        with pytest.raises(InvalidImageException):
            await service.process_image(original_path, "corrupt.jpg")

    async def test_propagates_unsupported_media_type_for_a_disallowed_decoded_format(
        self, tmp_path: Path
    ) -> None:
        upload_dir = tmp_path / "uploads"
        original_path = _save_image(upload_dir, size=(10, 10), fmt="BMP")
        service = ImageProcessingService(processed_dir=tmp_path / "processed")

        with pytest.raises(UnsupportedMediaTypeException):
            await service.process_image(original_path, "photo.jpg")

    async def test_propagates_image_too_large_exception(self, tmp_path: Path) -> None:
        upload_dir = tmp_path / "uploads"
        original_path = _save_image(upload_dir, size=(200, 100))
        service = ImageProcessingService(
            processed_dir=tmp_path / "processed",
            validator=ImageValidator(max_dimension_px=50),
        )

        with pytest.raises(ImageTooLargeException):
            await service.process_image(original_path, "photo.jpg")

    async def test_no_processed_file_is_written_when_validation_fails(self, tmp_path: Path) -> None:
        upload_dir = tmp_path / "uploads"
        processed_dir = tmp_path / "processed"
        upload_dir.mkdir(parents=True)
        original_path = upload_dir / "corrupt.jpg"
        original_path.write_bytes(b"not an image")
        service = ImageProcessingService(processed_dir=processed_dir)

        with pytest.raises(InvalidImageException):
            await service.process_image(original_path, "corrupt.jpg")

        assert list(processed_dir.iterdir()) == []

"""Unit tests for `ImageValidator`, against real Pillow-generated files on disk."""

from pathlib import Path

import pytest
from PIL import Image

from app.exceptions.errors import (
    ImageTooLargeException,
    InvalidImageException,
    UnsupportedMediaTypeException,
)
from app.validators.image_validator import ImageValidator


def _save_image(
    tmp_path: Path, *, name: str, size: tuple[int, int] = (20, 10), fmt: str = "JPEG"
) -> Path:
    path = tmp_path / name
    Image.new("RGB", size, (255, 0, 0)).save(path, format=fmt)
    return path


class TestValidateSuccess:
    def test_accepts_a_valid_jpeg(self, tmp_path: Path) -> None:
        path = _save_image(tmp_path, name="photo.jpg", size=(30, 20), fmt="JPEG")
        validator = ImageValidator()

        width, height, image_format = validator.validate(path)

        assert (width, height) == (30, 20)
        assert image_format == "JPEG"

    def test_accepts_a_valid_png(self, tmp_path: Path) -> None:
        path = _save_image(tmp_path, name="photo.png", size=(15, 15), fmt="PNG")
        validator = ImageValidator()

        _, _, image_format = validator.validate(path)

        assert image_format == "PNG"

    def test_accepts_a_valid_webp(self, tmp_path: Path) -> None:
        path = _save_image(tmp_path, name="photo.webp", size=(15, 15), fmt="WEBP")
        validator = ImageValidator()

        _, _, image_format = validator.validate(path)

        assert image_format == "WEBP"

    def test_accepts_a_tiny_image(self, tmp_path: Path) -> None:
        path = _save_image(tmp_path, name="tiny.jpg", size=(1, 1))
        validator = ImageValidator()

        width, height, _ = validator.validate(path)

        assert (width, height) == (1, 1)


class TestValidateCorruption:
    def test_rejects_a_completely_non_image_file(self, tmp_path: Path) -> None:
        path = tmp_path / "not-an-image.jpg"
        path.write_bytes(b"this is definitely not image data" * 10)
        validator = ImageValidator()

        with pytest.raises(InvalidImageException):
            validator.validate(path)

    def test_rejects_a_severely_truncated_jpeg(self, tmp_path: Path) -> None:
        # Keep only a third of the bytes — corrupt enough that even the
        # lightweight verify() step fails. Exercises _verify_integrity's
        # failure path.
        valid_path = _save_image(tmp_path, name="valid.jpg", size=(100, 100))
        truncated_path = tmp_path / "truncated.jpg"
        original_bytes = valid_path.read_bytes()
        truncated_path.write_bytes(original_bytes[: len(original_bytes) // 3])
        validator = ImageValidator()

        with pytest.raises(InvalidImageException):
            validator.validate(truncated_path)

    def test_rejects_a_jpeg_with_truncated_scan_data(self, tmp_path: Path) -> None:
        # Keep 90% of the bytes — the header/structure is intact enough
        # for verify() to pass, but the actual pixel data is incomplete,
        # so a full decode still fails. Exercises _decode's own failure
        # path specifically (verify() alone would miss this).
        valid_path = _save_image(tmp_path, name="valid.jpg", size=(100, 100))
        truncated_path = tmp_path / "scan_truncated.jpg"
        original_bytes = valid_path.read_bytes()
        truncated_path.write_bytes(original_bytes[: int(len(original_bytes) * 0.9)])
        validator = ImageValidator()

        with pytest.raises(InvalidImageException):
            validator.validate(truncated_path)

    def test_rejects_an_empty_file(self, tmp_path: Path) -> None:
        path = tmp_path / "empty.jpg"
        path.write_bytes(b"")
        validator = ImageValidator()

        with pytest.raises(InvalidImageException):
            validator.validate(path)


class TestValidateFormat:
    def test_rejects_a_format_outside_the_allowed_set_even_with_a_misleading_extension(
        self, tmp_path: Path
    ) -> None:
        # Named "photo.jpg" but actually BMP content underneath — proves
        # this validates real decoded content, not the file extension.
        path = tmp_path / "photo.jpg"
        Image.new("RGB", (10, 10), (0, 0, 255)).save(path, format="BMP")
        validator = ImageValidator()

        with pytest.raises(UnsupportedMediaTypeException):
            validator.validate(path)

    def test_allowed_formats_is_configurable(self, tmp_path: Path) -> None:
        path = tmp_path / "photo.bmp"
        Image.new("RGB", (10, 10), (0, 0, 255)).save(path, format="BMP")
        validator = ImageValidator(allowed_formats=frozenset({"BMP"}))

        _, _, image_format = validator.validate(path)

        assert image_format == "BMP"


class TestValidateDimensions:
    def test_rejects_an_image_exceeding_the_configured_max_dimension(self, tmp_path: Path) -> None:
        path = _save_image(tmp_path, name="large.jpg", size=(200, 50))
        validator = ImageValidator(max_dimension_px=100)

        with pytest.raises(ImageTooLargeException):
            validator.validate(path)

    def test_accepts_an_image_exactly_at_the_max_dimension(self, tmp_path: Path) -> None:
        path = _save_image(tmp_path, name="exact.jpg", size=(100, 100))
        validator = ImageValidator(max_dimension_px=100)

        width, height, _ = validator.validate(path)

        assert (width, height) == (100, 100)

    def test_max_dimension_is_configurable(self, tmp_path: Path) -> None:
        path = _save_image(tmp_path, name="small.jpg", size=(10, 10))
        validator = ImageValidator(max_dimension_px=5)

        with pytest.raises(ImageTooLargeException):
            validator.validate(path)

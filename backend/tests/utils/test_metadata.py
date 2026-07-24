"""Unit tests for `app.utils.metadata`."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas.product import ProductImage
from app.utils.metadata import FileMetadata, parse_file_metadata

_VALID_SHA256 = "a" * 64


class TestFileMetadata:
    def test_rejects_a_checksum_of_the_wrong_length(self) -> None:
        with pytest.raises(ValidationError):
            FileMetadata(
                original_filename="a.jpg",
                extension=".jpg",
                content_type="image/jpeg",
                size_bytes=10,
                checksum_sha256="not-a-real-checksum",
                uploaded_at=datetime.now(UTC),
            )

    def test_rejects_uppercase_hex_in_the_checksum(self) -> None:
        with pytest.raises(ValidationError):
            FileMetadata(
                original_filename="a.jpg",
                extension=".jpg",
                content_type="image/jpeg",
                size_bytes=10,
                checksum_sha256="A" * 64,
                uploaded_at=datetime.now(UTC),
            )

    def test_accepts_a_well_formed_checksum(self) -> None:
        metadata = FileMetadata(
            original_filename="a.jpg",
            extension=".jpg",
            content_type="image/jpeg",
            size_bytes=10,
            checksum_sha256=_VALID_SHA256,
            uploaded_at=datetime.now(UTC),
        )

        assert metadata.checksum_sha256 == _VALID_SHA256


class TestParseFileMetadata:
    def test_derives_the_extension_from_the_original_filename(self) -> None:
        image = ProductImage(
            original_filename="photo.PNG",
            stored_filename="generated.png",
            content_type="image/png",
            size_bytes=2048,
            uploaded_at=datetime.now(UTC),
        )

        metadata = parse_file_metadata(image, checksum_sha256=_VALID_SHA256)

        assert metadata.extension == ".png"  # lowercased, unlike the original

    def test_carries_over_the_rest_of_the_image_metadata_unchanged(self) -> None:
        uploaded_at = datetime.now(UTC)
        image = ProductImage(
            original_filename="photo.jpg",
            stored_filename="generated.jpg",
            content_type="image/jpeg",
            size_bytes=4096,
            uploaded_at=uploaded_at,
        )

        metadata = parse_file_metadata(image, checksum_sha256=_VALID_SHA256)

        assert metadata.original_filename == "photo.jpg"
        assert metadata.content_type == "image/jpeg"
        assert metadata.size_bytes == 4096
        assert metadata.uploaded_at == uploaded_at
        assert metadata.checksum_sha256 == _VALID_SHA256

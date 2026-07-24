"""Unit tests for `ProductService` and its normalization functions."""

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.exceptions.errors import ChecksumException, ValidationException
from app.schemas.product import ProductCreate, ProductImage
from app.services.product_service import (
    ProductService,
    _normalize_category,
    _normalize_description,
    _normalize_name,
    _normalize_price,
)


def _write_stored_file(upload_dir: Path, stored_filename: str, content: bytes) -> None:
    upload_dir.mkdir(parents=True, exist_ok=True)
    (upload_dir / stored_filename).write_bytes(content)


def _image(*, stored_filename: str = "generated.jpg", size_bytes: int = 5) -> ProductImage:
    return ProductImage(
        original_filename="photo.jpg",
        stored_filename=stored_filename,
        content_type="image/jpeg",
        size_bytes=size_bytes,
        uploaded_at=datetime.now(UTC),
    )


class TestNormalizeName:
    def test_trims_surrounding_whitespace(self) -> None:
        assert _normalize_name(" Nike ") == "Nike"

    def test_preserves_case(self) -> None:
        assert _normalize_name("Nike") == "Nike"


class TestNormalizeDescription:
    def test_returns_none_for_none(self) -> None:
        assert _normalize_description(None) is None

    def test_trims_surrounding_whitespace(self) -> None:
        assert _normalize_description("  a fine widget  ") == "a fine widget"

    def test_all_whitespace_normalizes_to_none(self) -> None:
        assert _normalize_description("   ") is None


class TestNormalizeCategory:
    def test_returns_none_for_none(self) -> None:
        assert _normalize_category(None) is None

    def test_lowercases_and_slugifies(self) -> None:
        assert _normalize_category("Men Tshirts") == "men-tshirts"

    def test_lowercases_a_single_word(self) -> None:
        assert _normalize_category("BLUE") == "blue"

    def test_collapses_repeated_separators(self) -> None:
        assert _normalize_category("Men   -- Tshirts!!") == "men-tshirts"

    def test_all_whitespace_normalizes_to_none(self) -> None:
        assert _normalize_category("   ") is None


class TestNormalizePrice:
    def test_returns_none_for_none(self) -> None:
        assert _normalize_price(None) is None

    def test_rounds_to_two_decimal_places(self) -> None:
        assert _normalize_price(19.999) == 20.0

    def test_leaves_a_whole_number_as_a_float(self) -> None:
        assert _normalize_price(1999) == 1999.0


class TestProcessUploadSuccess:
    async def test_builds_a_normalized_identified_product(self, tmp_path: Path) -> None:
        content = b"fake-image-bytes"
        image = _image(stored_filename="generated.jpg", size_bytes=len(content))
        _write_stored_file(tmp_path, image.stored_filename, content)
        service = ProductService(upload_dir=tmp_path)
        product_create = ProductCreate(
            name=" Nike ",
            description="  A fine shirt  ",
            category="Men Tshirts",
            price=1999,
        )

        product = await service.process_upload(product_create, image)

        assert product.name == "Nike"
        assert product.description == "A fine shirt"
        assert product.category == "men-tshirts"
        assert product.price == 1999.0

    async def test_generates_a_fresh_uuid4_per_call(self, tmp_path: Path) -> None:
        content = b"fake-image-bytes"
        image = _image()
        _write_stored_file(tmp_path, image.stored_filename, content)
        service = ProductService(upload_dir=tmp_path)
        product_create = ProductCreate(name="Widget")

        first = await service.process_upload(product_create, image)
        second = await service.process_upload(product_create, image)

        assert first.id != second.id

    async def test_file_metadata_checksum_matches_the_stored_content(self, tmp_path: Path) -> None:
        content = b"specific known content for hashing"
        image = _image()
        _write_stored_file(tmp_path, image.stored_filename, content)
        service = ProductService(upload_dir=tmp_path)

        product = await service.process_upload(ProductCreate(name="Widget"), image)

        assert product.file_metadata.checksum_sha256 == hashlib.sha256(content).hexdigest()
        assert product.file_metadata.original_filename == "photo.jpg"
        assert product.file_metadata.extension == ".jpg"


class TestProcessUploadValidation:
    async def test_rejects_a_name_that_is_blank_after_trimming(self, tmp_path: Path) -> None:
        image = _image()
        _write_stored_file(tmp_path, image.stored_filename, b"content")
        service = ProductService(upload_dir=tmp_path)
        # A real caller can reach this: "   " passes ProductCreate's
        # min_length=1 (raw length 3) but is blank once normalized.
        product_create = ProductCreate(name="   ")

        with pytest.raises(ValidationException):
            await service.process_upload(product_create, image)

    async def test_rejects_a_negative_price_on_an_unvalidated_product_create(
        self, tmp_path: Path
    ) -> None:
        image = _image()
        _write_stored_file(tmp_path, image.stored_filename, b"content")
        service = ProductService(upload_dir=tmp_path)
        # ProductCreate's own Field(ge=0) already blocks this through the
        # normal constructor - model_construct bypasses validation to
        # simulate a caller that reaches ProductService without it (e.g.
        # a future non-HTTP caller), proving the defensive re-check works.
        product_create = ProductCreate.model_construct(name="Widget", price=-5.0)

        with pytest.raises(ValidationException):
            await service.process_upload(product_create, image)


class TestProcessUploadChecksumFailure:
    async def test_raises_checksum_exception_if_the_stored_file_is_missing(
        self, tmp_path: Path
    ) -> None:
        image = _image(stored_filename="never-written.jpg")
        service = ProductService(upload_dir=tmp_path)

        with pytest.raises(ChecksumException):
            await service.process_upload(ProductCreate(name="Widget"), image)

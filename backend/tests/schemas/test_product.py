"""Unit tests for the product schemas."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.product import (
    ProcessedImageInfo,
    ProductCreate,
    ProductImage,
    ProductResponse,
    UploadResponse,
)


class TestProductCreate:
    def test_accepts_only_a_required_name(self) -> None:
        product = ProductCreate(name="Widget")

        assert product.name == "Widget"
        assert product.description is None
        assert product.category is None
        assert product.price is None

    def test_rejects_an_empty_name(self) -> None:
        with pytest.raises(ValidationError):
            ProductCreate(name="")

    def test_rejects_a_negative_price(self) -> None:
        with pytest.raises(ValidationError):
            ProductCreate(name="Widget", price=-1.0)

    def test_coerces_a_numeric_string_price(self) -> None:
        # Form data arrives as strings — pydantic's lax coercion (the
        # default) must turn "19.99" into a real float.
        product = ProductCreate.model_validate({"name": "Widget", "price": "19.99"})

        assert product.price == 19.99


class TestProductImage:
    def test_rejects_a_non_positive_size(self) -> None:
        with pytest.raises(ValidationError):
            ProductImage(
                original_filename="a.jpg",
                stored_filename="b.jpg",
                content_type="image/jpeg",
                size_bytes=0,
                uploaded_at=datetime.now(UTC),
            )


class TestProcessedImageInfo:
    def test_constructs_with_all_fields(self) -> None:
        info = ProcessedImageInfo(width=1024, height=768, format="JPEG", color_mode="RGB")

        assert info.width == 1024
        assert info.height == 768
        assert info.format == "JPEG"
        assert info.color_mode == "RGB"


class TestUploadResponse:
    def test_round_trips_through_model_dump_and_validate(self) -> None:
        response = UploadResponse(
            product_id=uuid4(),
            product=ProductCreate(name="Widget"),
            image=ProductImage(
                original_filename="a.jpg",
                stored_filename="b.jpg",
                content_type="image/jpeg",
                size_bytes=1024,
                uploaded_at=datetime.now(UTC),
            ),
            checksum_sha256="a" * 64,
            processed_image=ProcessedImageInfo(
                width=800, height=600, format="JPEG", color_mode="RGB"
            ),
        )

        dumped = response.model_dump(mode="json")
        restored = UploadResponse.model_validate(dumped)

        assert restored == response


class TestProductResponse:
    def test_constructs_the_reserved_persisted_product_shape(self) -> None:
        # Not used by any route yet (Phase 2A is upload-only) — this proves
        # the reserved contract itself is well-formed and round-trips.
        image = ProductImage(
            original_filename="a.jpg",
            stored_filename="b.jpg",
            content_type="image/jpeg",
            size_bytes=1024,
            uploaded_at=datetime.now(UTC),
        )

        product = ProductResponse(
            id=uuid4(),
            name="Widget",
            description=None,
            category=None,
            price=9.99,
            images=[image],
            created_at=datetime.now(UTC),
        )

        assert product.images == [image]

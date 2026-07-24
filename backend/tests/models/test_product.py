"""Unit tests for the internal `Product` domain model."""

from datetime import UTC, datetime
from uuid import uuid4

from app.models.product import Product
from app.utils.metadata import FileMetadata


def _file_metadata() -> FileMetadata:
    return FileMetadata(
        original_filename="photo.jpg",
        extension=".jpg",
        content_type="image/jpeg",
        size_bytes=1024,
        checksum_sha256="a" * 64,
        uploaded_at=datetime.now(UTC),
    )


class TestProduct:
    def test_constructs_with_all_fields(self) -> None:
        product_id = uuid4()
        metadata = _file_metadata()

        product = Product(
            id=product_id,
            name="Widget",
            description="A fine widget",
            category="men-tshirts",
            price=19.99,
            file_metadata=metadata,
        )

        assert product.id == product_id
        assert product.name == "Widget"
        assert product.description == "A fine widget"
        assert product.category == "men-tshirts"
        assert product.price == 19.99
        assert product.file_metadata == metadata

    def test_accepts_optional_fields_as_none(self) -> None:
        product = Product(
            id=uuid4(),
            name="Minimal Widget",
            description=None,
            category=None,
            price=None,
            file_metadata=_file_metadata(),
        )

        assert product.description is None
        assert product.category is None
        assert product.price is None

    def test_round_trips_through_model_dump_and_validate(self) -> None:
        product = Product(
            id=uuid4(),
            name="Widget",
            description=None,
            category=None,
            price=None,
            file_metadata=_file_metadata(),
        )

        dumped = product.model_dump(mode="json")
        restored = Product.model_validate(dumped)

        assert restored == product

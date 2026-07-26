"""Unit tests for the internal `Product` domain model."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from app.models.catalog_intelligence_result import CatalogIntelligenceResult
from app.models.catalog_tags import CatalogTag, Source
from app.models.embedding import ImageEmbedding
from app.models.image_metadata import ImageMetadata
from app.models.product import Product
from app.models.product_attributes import ProductAttributes
from app.models.text_embedding import TextEmbedding
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


def _image_metadata() -> ImageMetadata:
    return ImageMetadata(
        width=800,
        height=600,
        format="JPEG",
        color_mode="RGB",
        original_path=Path("/tmp/uploads/abc.jpg"),
        processed_path=Path("/tmp/processed/abc.jpg"),
    )


def _embedding(product_id: UUID) -> ImageEmbedding:
    return ImageEmbedding(
        product_id=product_id,
        model_name="openai/clip-vit-base-patch32",
        embedding_dimension=4,
        vector=[0.1, 0.2, 0.3, 0.4],
    )


def _text_embedding(product_id: UUID) -> TextEmbedding:
    return TextEmbedding(
        product_id=product_id,
        model_name="BAAI/bge-small-en-v1.5",
        embedding_dimension=3,
        vector=[0.5, 0.6, 0.7],
    )


def _catalog_intelligence() -> CatalogIntelligenceResult:
    return CatalogIntelligenceResult(
        attributes=ProductAttributes(brand="Nike", confidence=0.9),
        tags=[CatalogTag(tag="running", confidence=0.9, source=Source.TEXT)],
        quality_score=0.85,
        processing_time=0.01,
    )


class TestProduct:
    def test_constructs_with_all_fields(self) -> None:
        product_id = uuid4()
        file_metadata = _file_metadata()
        image_metadata = _image_metadata()

        product = Product(
            id=product_id,
            name="Widget",
            brand="Nike",
            description="A fine widget",
            category="men-tshirts",
            price=19.99,
            file_metadata=file_metadata,
            image_metadata=image_metadata,
            embedding=_embedding(product_id),
            text_embedding=_text_embedding(product_id),
            catalog_intelligence=_catalog_intelligence(),
        )

        assert product.id == product_id
        assert product.name == "Widget"
        assert product.brand == "Nike"
        assert product.description == "A fine widget"
        assert product.category == "men-tshirts"
        assert product.price == 19.99
        assert product.file_metadata == file_metadata
        assert product.image_metadata == image_metadata
        assert product.embedding.product_id == product_id
        assert product.text_embedding.product_id == product_id

    def test_accepts_optional_fields_as_none(self) -> None:
        product_id = uuid4()

        product = Product(
            id=product_id,
            name="Minimal Widget",
            brand=None,
            description=None,
            category=None,
            price=None,
            file_metadata=_file_metadata(),
            image_metadata=_image_metadata(),
            embedding=_embedding(product_id),
            text_embedding=_text_embedding(product_id),
            catalog_intelligence=_catalog_intelligence(),
        )

        assert product.brand is None
        assert product.description is None
        assert product.category is None
        assert product.price is None

    def test_round_trips_through_model_dump_and_validate(self) -> None:
        product_id = uuid4()

        product = Product(
            id=product_id,
            name="Widget",
            brand=None,
            description=None,
            category=None,
            price=None,
            file_metadata=_file_metadata(),
            image_metadata=_image_metadata(),
            embedding=_embedding(product_id),
            text_embedding=_text_embedding(product_id),
            catalog_intelligence=_catalog_intelligence(),
        )

        dumped = product.model_dump(mode="json")
        restored = Product.model_validate(dumped)

        assert restored == product

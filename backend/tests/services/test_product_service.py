"""Unit tests for `ProductService` and its normalization functions."""

import asyncio
import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from app.exceptions.errors import (
    ChecksumException,
    EmbeddingGenerationException,
    InvalidImageException,
    TextEmbeddingException,
    ValidationException,
    VectorStoreException,
)
from app.schemas.product import ProductCreate, ProductImage
from app.services.embeddings.base import BaseEmbeddingService
from app.services.embeddings.text_base import BaseTextEmbeddingService
from app.services.image_processing_service import ImageProcessingService
from app.services.product_service import (
    ProductService,
    _build_text_representation,
    _normalize_brand,
    _normalize_category,
    _normalize_description,
    _normalize_name,
    _normalize_price,
)
from app.services.vectorstore.base import BaseVectorStore, VectorCollection, VectorRecord


class _FakeEmbeddingService(BaseEmbeddingService):
    """A deterministic, instant stand-in for `CLIPEmbeddingService`.

    `ProductService`'s own tests care about orchestration (is the
    embedding wired into `Product` correctly?), not embedding *quality* or
    real model behaviour — that's `test_clip_service.py`'s job. Loading a
    real CLIP checkpoint here would make every product-service test pay
    model-loading cost for no added confidence.
    """

    def __init__(self, *, dimension: int = 4, fail: bool = False) -> None:
        self._dimension = dimension
        self._fail = fail
        self.calls: list[Path] = []

    @property
    def model_name(self) -> str:
        return "fake-clip-model"

    async def generate_embedding(self, image_path: Path) -> list[float]:
        self.calls.append(image_path)
        if self._fail:
            raise EmbeddingGenerationException("fake embedding failure")
        return [0.1 * (i + 1) for i in range(self._dimension)]

    async def generate_embeddings(self, image_paths: list[Path]) -> list[list[float]]:
        return [await self.generate_embedding(path) for path in image_paths]


class _FakeTextEmbeddingService(BaseTextEmbeddingService):
    """A deterministic, instant stand-in for `SentenceTransformerEmbeddingService`.

    Same reasoning as `_FakeEmbeddingService` — orchestration, not model
    quality, is what `ProductService`'s own tests care about.
    """

    def __init__(self, *, dimension: int = 3, fail: bool = False) -> None:
        self._dimension = dimension
        self._fail = fail
        self.calls: list[str] = []

    @property
    def model_name(self) -> str:
        return "fake-text-model"

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed_text(self, text: str) -> list[float]:
        self.calls.append(text)
        if self._fail:
            raise TextEmbeddingException("fake text embedding failure")
        return [0.2 * (i + 1) for i in range(self._dimension)]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed_text(text) for text in texts]


class _FakeVectorStore(BaseVectorStore):
    """A deterministic, instant stand-in for `QdrantVectorStore`.

    `ProductService`'s own tests care about orchestration (is the right
    `VectorRecord` upserted, into the right collection?), not Qdrant
    behaviour itself — that's `test_qdrant_store.py`'s job.
    """

    def __init__(self, *, fail: bool = False) -> None:
        self._fail = fail
        self.upserted_image: list[VectorRecord] = []
        self.upserted_text: list[VectorRecord] = []

    async def upsert(self, collection: VectorCollection, records: list[VectorRecord]) -> None:
        if self._fail:
            raise VectorStoreException("fake vector store failure")
        if collection is VectorCollection.IMAGE:
            self.upserted_image.extend(records)
        else:
            self.upserted_text.extend(records)

    async def search(
        self,
        collection: VectorCollection,
        query_vector: list[float],
        *,
        top_k: int,
        filters: Any | None = None,
    ) -> list:  # type: ignore[type-arg]
        return []

    async def delete(self, collection: VectorCollection, product_ids: list) -> None:  # type: ignore[type-arg]
        return None

    async def exists(self, collection: VectorCollection, product_id) -> bool:  # type: ignore[no-untyped-def]
        return False

    async def health(self) -> bool:
        return True


def _build_service(
    tmp_path: Path,
    *,
    embedding_service: BaseEmbeddingService | None = None,
    text_embedding_service: BaseTextEmbeddingService | None = None,
    vector_store: BaseVectorStore | None = None,
) -> ProductService:
    # Every test gets its own ImageProcessingService pointed at a tmp_path
    # subdirectory — never the real settings.storage.processed_dir — and
    # fake embedding/vector-store services instead of loading a real CLIP
    # or Sentence Transformers model, or talking to Qdrant.
    return ProductService(
        upload_dir=tmp_path,
        image_processing_service=ImageProcessingService(processed_dir=tmp_path / "processed"),
        embedding_service=(
            embedding_service if embedding_service is not None else _FakeEmbeddingService()
        ),
        text_embedding_service=(
            text_embedding_service
            if text_embedding_service is not None
            else _FakeTextEmbeddingService()
        ),
        vector_store=vector_store if vector_store is not None else _FakeVectorStore(),
    )


def _write_valid_image(
    upload_dir: Path, stored_filename: str, *, size: tuple[int, int] = (50, 50)
) -> bytes:
    upload_dir.mkdir(parents=True, exist_ok=True)
    path = upload_dir / stored_filename
    Image.new("RGB", size, (255, 0, 0)).save(path, format="JPEG")
    return path.read_bytes()


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


class TestNormalizeBrand:
    def test_returns_none_for_none(self) -> None:
        assert _normalize_brand(None) is None

    def test_trims_surrounding_whitespace(self) -> None:
        assert _normalize_brand("  Nike  ") == "Nike"

    def test_all_whitespace_normalizes_to_none(self) -> None:
        assert _normalize_brand("   ") is None


class TestBuildTextRepresentation:
    def test_joins_all_parts(self) -> None:
        text = _build_text_representation("Widget", "Nike", "Men Tshirts", "A fine shirt")

        assert text == "Widget. Nike. Men Tshirts. A fine shirt"

    def test_omits_missing_parts(self) -> None:
        text = _build_text_representation("Widget", None, None, None)

        assert text == "Widget"

    def test_omits_blank_parts(self) -> None:
        text = _build_text_representation("Widget", "   ", "Men Tshirts", None)

        assert text == "Widget. Men Tshirts"

    def test_does_not_slugify_category(self) -> None:
        # Unlike `_normalize_category`, which slugifies for storage/
        # filtering — the text representation is meant for a semantic
        # embedding model, so it should stay natural language.
        text = _build_text_representation("Widget", None, "Men Tshirts", None)

        assert "Men Tshirts" in text
        assert "men-tshirts" not in text


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
        image = _image(stored_filename="generated.jpg")
        _write_valid_image(tmp_path, image.stored_filename)
        service = _build_service(tmp_path)
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
        image = _image()
        _write_valid_image(tmp_path, image.stored_filename)
        service = _build_service(tmp_path)
        product_create = ProductCreate(name="Widget")

        first = await service.process_upload(product_create, image)
        second = await service.process_upload(product_create, image)

        assert first.id != second.id

    async def test_file_metadata_checksum_matches_the_stored_content(self, tmp_path: Path) -> None:
        image = _image()
        content = _write_valid_image(tmp_path, image.stored_filename)
        service = _build_service(tmp_path)

        product = await service.process_upload(ProductCreate(name="Widget"), image)

        assert product.file_metadata.checksum_sha256 == hashlib.sha256(content).hexdigest()
        assert product.file_metadata.original_filename == "photo.jpg"
        assert product.file_metadata.extension == ".jpg"

    async def test_populates_image_metadata_from_image_processing(self, tmp_path: Path) -> None:
        image = _image()
        _write_valid_image(tmp_path, image.stored_filename, size=(50, 50))
        service = _build_service(tmp_path)

        product = await service.process_upload(ProductCreate(name="Widget"), image)

        assert product.image_metadata.width == 50
        assert product.image_metadata.height == 50
        assert product.image_metadata.format == "JPEG"
        assert product.image_metadata.color_mode == "RGB"
        assert product.image_metadata.processed_path.is_file()


class TestProcessUploadEmbedding:
    async def test_populates_embedding_from_the_embedding_service(self, tmp_path: Path) -> None:
        image = _image()
        _write_valid_image(tmp_path, image.stored_filename)
        fake_embedding_service = _FakeEmbeddingService(dimension=4)
        service = _build_service(tmp_path, embedding_service=fake_embedding_service)

        product = await service.process_upload(ProductCreate(name="Widget"), image)

        assert product.embedding.product_id == product.id
        assert product.embedding.model_name == "fake-clip-model"
        assert product.embedding.embedding_dimension == 4
        assert product.embedding.vector == pytest.approx([0.1, 0.2, 0.3, 0.4])

    async def test_embeds_the_standardized_processed_image_not_the_original_upload(
        self, tmp_path: Path
    ) -> None:
        image = _image()
        _write_valid_image(tmp_path, image.stored_filename)
        fake_embedding_service = _FakeEmbeddingService()
        service = _build_service(tmp_path, embedding_service=fake_embedding_service)

        product = await service.process_upload(ProductCreate(name="Widget"), image)

        assert fake_embedding_service.calls == [product.image_metadata.processed_path]

    async def test_propagates_embedding_generation_exception(self, tmp_path: Path) -> None:
        image = _image()
        _write_valid_image(tmp_path, image.stored_filename)
        service = _build_service(tmp_path, embedding_service=_FakeEmbeddingService(fail=True))

        with pytest.raises(EmbeddingGenerationException):
            await service.process_upload(ProductCreate(name="Widget"), image)


class TestProcessUploadTextEmbedding:
    async def test_populates_text_embedding_from_the_text_embedding_service(
        self, tmp_path: Path
    ) -> None:
        image = _image()
        _write_valid_image(tmp_path, image.stored_filename)
        fake_text_embedding_service = _FakeTextEmbeddingService(dimension=3)
        service = _build_service(tmp_path, text_embedding_service=fake_text_embedding_service)

        product = await service.process_upload(ProductCreate(name="Widget"), image)

        assert product.text_embedding.product_id == product.id
        assert product.text_embedding.model_name == "fake-text-model"
        assert product.text_embedding.embedding_dimension == 3
        assert product.text_embedding.vector == pytest.approx([0.2, 0.4, 0.6])

    async def test_embeds_the_name_brand_category_and_description(self, tmp_path: Path) -> None:
        image = _image()
        _write_valid_image(tmp_path, image.stored_filename)
        fake_text_embedding_service = _FakeTextEmbeddingService()
        service = _build_service(tmp_path, text_embedding_service=fake_text_embedding_service)
        product_create = ProductCreate(
            name="Widget", brand="Nike", category="Men Tshirts", description="A fine shirt"
        )

        await service.process_upload(product_create, image)

        assert fake_text_embedding_service.calls == ["Widget. Nike. Men Tshirts. A fine shirt"]

    async def test_propagates_text_embedding_exception(self, tmp_path: Path) -> None:
        image = _image()
        _write_valid_image(tmp_path, image.stored_filename)
        service = _build_service(
            tmp_path, text_embedding_service=_FakeTextEmbeddingService(fail=True)
        )

        with pytest.raises(TextEmbeddingException):
            await service.process_upload(ProductCreate(name="Widget"), image)


class TestProcessUploadVectorStoreUpsert:
    async def test_upserts_an_image_record_matching_the_built_product(self, tmp_path: Path) -> None:
        image = _image()
        _write_valid_image(tmp_path, image.stored_filename)
        vector_store = _FakeVectorStore()
        service = _build_service(tmp_path, vector_store=vector_store)
        product_create = ProductCreate(
            name="Nike Widget", brand="Nike", category="Men Tshirts", price=19.99
        )

        product = await service.process_upload(product_create, image)

        assert len(vector_store.upserted_image) == 1
        record = vector_store.upserted_image[0]
        assert record.product_id == product.id
        assert record.vector == pytest.approx(product.embedding.vector)
        assert record.metadata == {
            "name": "Nike Widget",
            "brand": "Nike",
            "category": "men-tshirts",
            "price": 19.99,
            "description": None,
        }

    async def test_upserts_a_text_record_matching_the_built_product(self, tmp_path: Path) -> None:
        image = _image()
        _write_valid_image(tmp_path, image.stored_filename)
        vector_store = _FakeVectorStore()
        service = _build_service(tmp_path, vector_store=vector_store)
        product_create = ProductCreate(
            name="Nike Widget", brand="Nike", category="Men Tshirts", price=19.99
        )

        product = await service.process_upload(product_create, image)

        assert len(vector_store.upserted_text) == 1
        record = vector_store.upserted_text[0]
        assert record.product_id == product.id
        assert record.vector == pytest.approx(product.text_embedding.vector)
        assert record.metadata == {
            "name": "Nike Widget",
            "brand": "Nike",
            "category": "men-tshirts",
            "price": 19.99,
            "description": None,
        }

    async def test_propagates_vector_store_exception(self, tmp_path: Path) -> None:
        image = _image()
        _write_valid_image(tmp_path, image.stored_filename)
        service = _build_service(tmp_path, vector_store=_FakeVectorStore(fail=True))

        with pytest.raises(VectorStoreException):
            await service.process_upload(ProductCreate(name="Widget"), image)


class TestProcessUploadValidation:
    async def test_rejects_a_name_that_is_blank_after_trimming(self, tmp_path: Path) -> None:
        image = _image()
        _write_valid_image(tmp_path, image.stored_filename)
        service = _build_service(tmp_path)
        # A real caller can reach this: "   " passes ProductCreate's
        # min_length=1 (raw length 3) but is blank once normalized.
        product_create = ProductCreate(name="   ")

        with pytest.raises(ValidationException):
            await service.process_upload(product_create, image)

    async def test_rejects_a_negative_price_on_an_unvalidated_product_create(
        self, tmp_path: Path
    ) -> None:
        image = _image()
        _write_valid_image(tmp_path, image.stored_filename)
        service = _build_service(tmp_path)
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
        service = _build_service(tmp_path)

        with pytest.raises(ChecksumException):
            await service.process_upload(ProductCreate(name="Widget"), image)


class TestProcessUploadImageProcessingFailure:
    async def test_propagates_invalid_image_exception_for_a_corrupt_stored_file(
        self, tmp_path: Path
    ) -> None:
        image = _image()
        _write_stored_file(tmp_path, image.stored_filename, b"not a real image")
        service = _build_service(tmp_path)

        with pytest.raises(InvalidImageException):
            await service.process_upload(ProductCreate(name="Widget"), image)


class TestProcessUploadConcurrency:
    async def test_concurrent_uploads_each_produce_a_distinct_product(self, tmp_path: Path) -> None:
        image = _image()
        _write_valid_image(tmp_path, image.stored_filename)
        vector_store = _FakeVectorStore()
        service = _build_service(tmp_path, vector_store=vector_store)
        product_create = ProductCreate(name="Widget")

        products = await asyncio.gather(
            *(service.process_upload(product_create, image) for _ in range(8))
        )

        assert len({product.id for product in products}) == 8
        assert len(vector_store.upserted_image) == 8
        assert len(vector_store.upserted_text) == 8

"""Unit tests for `ProductService` and its normalization functions."""

import asyncio
import hashlib
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from app.core.constants import DuplicateDetectionMode
from app.exceptions.errors import (
    ChecksumException,
    ConflictException,
    EmbeddingGenerationException,
    InvalidImageException,
    TextEmbeddingException,
    ValidationException,
    VectorStoreException,
)
from app.models.catalog_intelligence_result import CatalogIntelligenceResult
from app.models.duplicate_decision import DuplicateDecision
from app.models.product_attributes import ProductAttributes
from app.schemas.product import ProductCreate, ProductImage
from app.services.catalog.catalog_intelligence_service import CatalogIntelligenceService
from app.services.duplicate.duplicate_detection_service import DuplicateDetectionService
from app.services.embeddings.base import BaseEmbeddingService
from app.services.embeddings.text_base import BaseTextEmbeddingService
from app.services.image_processing_service import ImageProcessingService
from app.services.product_service import (
    ProductService,
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

    async def retrieve(self, collection: VectorCollection, product_id):  # type: ignore[no-untyped-def]
        return None

    async def health(self) -> bool:
        return True


class _FakeCatalogIntelligenceService(CatalogIntelligenceService):
    """A deterministic, instant stand-in for `CatalogIntelligenceService`.

    Same reasoning as the other fakes here: `ProductService`'s own tests
    care about orchestration (is the result wired into `Product`/the
    vector metadata correctly?), not the real extraction/merge/scoring
    logic — that's `test_catalog_intelligence_service.py`'s job. Defaults
    to an empty result (no attributes, no tags) so tests that don't care
    about catalog intelligence aren't affected by it.
    """

    def __init__(self, *, result: CatalogIntelligenceResult | None = None) -> None:
        self._result = (
            result
            if result is not None
            else CatalogIntelligenceResult(
                attributes=ProductAttributes(), tags=[], quality_score=0.0, processing_time=0.0
            )
        )

    async def enrich(
        self,
        *,
        name: str,
        brand: str | None,
        category: str | None,
        description: str | None,
        image_path: Path,
    ) -> CatalogIntelligenceResult:
        return self._result


class _FakeDuplicateDetectionService(DuplicateDetectionService):
    """A deterministic, instant stand-in for `DuplicateDetectionService`.

    Same reasoning as the other fakes here: `ProductService`'s own tests
    care about orchestration (is the decision wired into `Product`, and
    does `BLOCK` mode actually reject?), not the real retrieval/scoring
    pipeline — that's `test_duplicate_detection_service.py`'s job.
    Defaults to a non-duplicate decision so tests that don't care about
    duplicate detection aren't affected by it.
    """

    def __init__(self, *, decision: DuplicateDecision | None = None) -> None:
        self._decision = (
            decision
            if decision is not None
            else DuplicateDecision(
                is_duplicate=False, confidence=0.0, reason="No candidates were found."
            )
        )
        self.calls: list[str] = []

    async def detect(
        self,
        *,
        name: str,
        brand: str | None,
        category: str | None,
        description: str | None,
        attributes: ProductAttributes,
        image: ProductImage,
        top_k: int | None = None,
        threshold: float | None = None,
        reranking_enabled: bool | None = None,
    ) -> DuplicateDecision:
        self.calls.append(name)
        return self._decision


def _build_service(
    tmp_path: Path,
    *,
    embedding_service: BaseEmbeddingService | None = None,
    text_embedding_service: BaseTextEmbeddingService | None = None,
    catalog_intelligence_service: CatalogIntelligenceService | None = None,
    catalog_intelligence_enabled: bool | None = None,
    duplicate_detection_service: DuplicateDetectionService | None = None,
    duplicate_detection_mode: DuplicateDetectionMode | None = None,
    vector_store: BaseVectorStore | None = None,
) -> ProductService:
    # Every test gets its own ImageProcessingService pointed at a tmp_path
    # subdirectory — never the real settings.storage.processed_dir — and
    # fake embedding/catalog-intelligence/duplicate-detection/vector-store
    # services instead of loading a real CLIP or Sentence Transformers
    # model, running the real catalog intelligence or duplicate detection
    # pipeline, or talking to Qdrant.
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
        catalog_intelligence_service=(
            catalog_intelligence_service
            if catalog_intelligence_service is not None
            else _FakeCatalogIntelligenceService()
        ),
        catalog_intelligence_enabled=catalog_intelligence_enabled,
        duplicate_detection_service=(
            duplicate_detection_service
            if duplicate_detection_service is not None
            else _FakeDuplicateDetectionService()
        ),
        duplicate_detection_mode=duplicate_detection_mode,
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

    async def test_uses_a_caller_supplied_product_id_when_given(self, tmp_path: Path) -> None:
        image = _image()
        _write_valid_image(tmp_path, image.stored_filename)
        service = _build_service(tmp_path)
        preassigned_id = uuid.uuid4()

        product = await service.process_upload(
            ProductCreate(name="Widget"), image, product_id=preassigned_id
        )

        assert product.id == preassigned_id
        assert product.embedding.product_id == preassigned_id
        assert product.text_embedding.product_id == preassigned_id

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
            "color": None,
            "material": None,
            "gender": None,
            "season": None,
            "style": None,
            "tags": [],
            "quality_score": 0.0,
            # Carried so a product's image can be located from its id alone.
            "image_filename": "generated.jpg",
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
            "color": None,
            "material": None,
            "gender": None,
            "season": None,
            "style": None,
            "tags": [],
            "quality_score": 0.0,
            # Carried so a product's image can be located from its id alone.
            "image_filename": "generated.jpg",
        }

    async def test_propagates_vector_store_exception(self, tmp_path: Path) -> None:
        image = _image()
        _write_valid_image(tmp_path, image.stored_filename)
        service = _build_service(tmp_path, vector_store=_FakeVectorStore(fail=True))

        with pytest.raises(VectorStoreException):
            await service.process_upload(ProductCreate(name="Widget"), image)


class TestProcessUploadCatalogIntelligence:
    """Orchestration tests for Phase 7's `CatalogIntelligenceService` integration.

    Merge/conflict-resolution/scoring logic itself is
    `test_catalog_intelligence_service.py`'s job; these tests only check
    that `ProductService` wires the result into `Product.catalog_intelligence`
    and the vector store metadata, and that the feature flag disables it.
    """

    async def test_a_populated_result_is_wired_into_the_product_and_vector_metadata(
        self, tmp_path: Path
    ) -> None:
        image = _image()
        _write_valid_image(tmp_path, image.stored_filename)
        vector_store = _FakeVectorStore()
        catalog_result = CatalogIntelligenceResult(
            attributes=ProductAttributes(
                color="Red",
                material="Mesh",
                gender="Men",
                season="Summer",
                style="Running",
                confidence=0.8,
            ),
            tags=[],
            quality_score=0.75,
            processing_time=0.02,
        )
        service = _build_service(
            tmp_path,
            vector_store=vector_store,
            catalog_intelligence_service=_FakeCatalogIntelligenceService(result=catalog_result),
        )

        product = await service.process_upload(ProductCreate(name="Widget"), image)

        assert product.catalog_intelligence == catalog_result
        record = vector_store.upserted_image[0]
        assert record.metadata["color"] == "Red"
        assert record.metadata["material"] == "Mesh"
        assert record.metadata["gender"] == "Men"
        assert record.metadata["season"] == "Summer"
        assert record.metadata["style"] == "Running"

    async def test_disabling_catalog_intelligence_yields_the_default_empty_result(
        self, tmp_path: Path
    ) -> None:
        image = _image()
        _write_valid_image(tmp_path, image.stored_filename)
        service = _build_service(tmp_path, catalog_intelligence_enabled=False)

        product = await service.process_upload(ProductCreate(name="Widget"), image)

        assert product.catalog_intelligence.attributes == ProductAttributes()
        assert product.catalog_intelligence.tags == []
        assert product.catalog_intelligence.quality_score == 0.0


class TestProcessUploadDuplicateDetection:
    """Orchestration tests for Phase 8's `DuplicateDetectionService` integration.

    Retrieval/scoring logic itself is `test_duplicate_detection_service.py`'s
    job; these tests only check that `ProductService` wires the decision
    into `Product.duplicate_decision` and that the three
    `DuplicateDetectionMode`s (`OFF`/`WARN`/`BLOCK`) behave as documented.
    """

    async def test_off_mode_never_calls_duplicate_detection(self, tmp_path: Path) -> None:
        image = _image()
        _write_valid_image(tmp_path, image.stored_filename)
        duplicate_detection_service = _FakeDuplicateDetectionService(
            decision=DuplicateDecision(
                is_duplicate=True, confidence=0.99, reason="would have matched"
            )
        )
        service = _build_service(
            tmp_path,
            duplicate_detection_service=duplicate_detection_service,
            duplicate_detection_mode=DuplicateDetectionMode.OFF,
        )

        product = await service.process_upload(ProductCreate(name="Widget"), image)

        assert duplicate_detection_service.calls == []
        assert product.duplicate_decision.is_duplicate is False
        assert product.duplicate_decision.confidence == 0.0

    async def test_warn_mode_stores_the_product_and_attaches_the_decision(
        self, tmp_path: Path
    ) -> None:
        image = _image()
        _write_valid_image(tmp_path, image.stored_filename)
        matched_product = uuid.uuid4()
        decision = DuplicateDecision(
            is_duplicate=True,
            confidence=0.95,
            reason="Overall similarity 0.95 meets the threshold.",
            matched_product=matched_product,
        )
        vector_store = _FakeVectorStore()
        service = _build_service(
            tmp_path,
            vector_store=vector_store,
            duplicate_detection_service=_FakeDuplicateDetectionService(decision=decision),
            duplicate_detection_mode=DuplicateDetectionMode.WARN,
        )

        product = await service.process_upload(ProductCreate(name="Widget"), image)

        assert product.duplicate_decision == decision
        assert len(vector_store.upserted_image) == 1

    async def test_block_mode_rejects_a_flagged_duplicate_without_indexing_it(
        self, tmp_path: Path
    ) -> None:
        image = _image()
        _write_valid_image(tmp_path, image.stored_filename)
        decision = DuplicateDecision(
            is_duplicate=True, confidence=0.95, reason="matched", matched_product=uuid.uuid4()
        )
        vector_store = _FakeVectorStore()
        service = _build_service(
            tmp_path,
            vector_store=vector_store,
            duplicate_detection_service=_FakeDuplicateDetectionService(decision=decision),
            duplicate_detection_mode=DuplicateDetectionMode.BLOCK,
        )

        with pytest.raises(ConflictException):
            await service.process_upload(ProductCreate(name="Widget"), image)

        assert vector_store.upserted_image == []

    async def test_block_mode_still_stores_a_non_duplicate(self, tmp_path: Path) -> None:
        image = _image()
        _write_valid_image(tmp_path, image.stored_filename)
        decision = DuplicateDecision(is_duplicate=False, confidence=0.2, reason="no match")
        vector_store = _FakeVectorStore()
        service = _build_service(
            tmp_path,
            vector_store=vector_store,
            duplicate_detection_service=_FakeDuplicateDetectionService(decision=decision),
            duplicate_detection_mode=DuplicateDetectionMode.BLOCK,
        )

        product = await service.process_upload(ProductCreate(name="Widget"), image)

        assert product.duplicate_decision.is_duplicate is False
        assert len(vector_store.upserted_image) == 1


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

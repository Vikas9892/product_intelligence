"""Unit tests for `ProductService` and its normalization functions."""

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest
from PIL import Image

from app.exceptions.errors import (
    ChecksumException,
    EmbeddingGenerationException,
    InvalidImageException,
    ValidationException,
)
from app.schemas.product import ProductCreate, ProductImage
from app.services.embeddings.base import BaseEmbeddingService
from app.services.image_processing_service import ImageProcessingService
from app.services.product_service import (
    ProductService,
    _normalize_category,
    _normalize_description,
    _normalize_name,
    _normalize_price,
)


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


def _build_service(
    tmp_path: Path, *, embedding_service: BaseEmbeddingService | None = None
) -> ProductService:
    # Every test gets its own ImageProcessingService pointed at a tmp_path
    # subdirectory — never the real settings.storage.processed_dir — and a
    # fake embedding service instead of loading a real CLIP model.
    return ProductService(
        upload_dir=tmp_path,
        image_processing_service=ImageProcessingService(processed_dir=tmp_path / "processed"),
        embedding_service=(
            embedding_service if embedding_service is not None else _FakeEmbeddingService()
        ),
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

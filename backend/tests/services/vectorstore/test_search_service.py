"""Unit tests for `SearchService`.

Uses fake `BaseEmbeddingService`/`BaseVectorStore` implementations (fast,
deterministic, no real model or Qdrant involved) to exercise the
orchestration logic in isolation — the same strategy
`tests/services/test_product_service.py` uses for `ProductService`. A
real `ImageProcessingService` still runs against `tmp_path`, since
standardizing the query image the same way a stored product's image was
standardized is exactly the behavior worth proving here.
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from PIL import Image

from app.exceptions.errors import InvalidImageException
from app.models.search import NearestNeighbor, ProductFilters
from app.schemas.product import ProductImage
from app.services.embeddings.base import BaseEmbeddingService
from app.services.image_processing_service import ImageProcessingService
from app.services.vectorstore.base import BaseVectorStore, VectorCollection, VectorRecord
from app.services.vectorstore.search_service import SearchService


class _FakeEmbeddingService(BaseEmbeddingService):
    def __init__(self, *, dimension: int = 4) -> None:
        self._dimension = dimension
        self.calls: list[Path] = []

    @property
    def model_name(self) -> str:
        return "fake-clip-model"

    async def generate_embedding(self, image_path: Path) -> list[float]:
        self.calls.append(image_path)
        return [0.1 * (i + 1) for i in range(self._dimension)]

    async def generate_embeddings(self, image_paths: list[Path]) -> list[list[float]]:
        return [await self.generate_embedding(path) for path in image_paths]


class _FakeVectorStore(BaseVectorStore):
    def __init__(self, *, neighbors: list[NearestNeighbor] | None = None) -> None:
        self._neighbors = neighbors if neighbors is not None else []
        self.search_calls: list[dict[str, Any]] = []

    async def upsert(self, collection: VectorCollection, records: list[VectorRecord]) -> None:
        return None

    async def search(
        self,
        collection: VectorCollection,
        query_vector: list[float],
        *,
        top_k: int,
        filters: ProductFilters | None = None,
    ) -> list[NearestNeighbor]:
        self.search_calls.append(
            {
                "collection": collection,
                "query_vector": query_vector,
                "top_k": top_k,
                "filters": filters,
            }
        )
        return self._neighbors[:top_k]

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
    vector_store: BaseVectorStore | None = None,
    default_top_k: int | None = None,
) -> SearchService:
    return SearchService(
        upload_dir=tmp_path,
        image_processing_service=ImageProcessingService(processed_dir=tmp_path / "processed"),
        embedding_service=(
            embedding_service if embedding_service is not None else _FakeEmbeddingService()
        ),
        vector_store=vector_store if vector_store is not None else _FakeVectorStore(),
        default_top_k=default_top_k,
    )


def _write_valid_image(
    upload_dir: Path, stored_filename: str, *, size: tuple[int, int] = (50, 50)
) -> None:
    upload_dir.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, (255, 0, 0)).save(upload_dir / stored_filename, format="JPEG")


def _write_corrupt_file(upload_dir: Path, stored_filename: str) -> None:
    upload_dir.mkdir(parents=True, exist_ok=True)
    (upload_dir / stored_filename).write_bytes(b"not an image")


def _image(*, stored_filename: str = "query.jpg") -> ProductImage:
    return ProductImage(
        original_filename="query.jpg",
        stored_filename=stored_filename,
        content_type="image/jpeg",
        size_bytes=5,
        uploaded_at=datetime.now(UTC),
    )


class TestSearchByImage:
    async def test_returns_neighbors_from_the_vector_store(self, tmp_path: Path) -> None:
        neighbor = NearestNeighbor(product_id=uuid4(), score=0.9, metadata={"name": "Widget"})
        service = _build_service(tmp_path, vector_store=_FakeVectorStore(neighbors=[neighbor]))
        image = _image()
        _write_valid_image(tmp_path, image.stored_filename)

        result = await service.search_by_image(image)

        assert result.neighbors == [neighbor]
        assert result.query_model_name == "fake-clip-model"

    async def test_uses_the_configured_default_top_k_when_not_specified(
        self, tmp_path: Path
    ) -> None:
        vector_store = _FakeVectorStore()
        service = _build_service(tmp_path, vector_store=vector_store, default_top_k=7)
        image = _image()
        _write_valid_image(tmp_path, image.stored_filename)

        await service.search_by_image(image)

        assert vector_store.search_calls[0]["top_k"] == 7

    async def test_explicit_top_k_overrides_the_default(self, tmp_path: Path) -> None:
        vector_store = _FakeVectorStore()
        service = _build_service(tmp_path, vector_store=vector_store, default_top_k=7)
        image = _image()
        _write_valid_image(tmp_path, image.stored_filename)

        await service.search_by_image(image, top_k=3)

        assert vector_store.search_calls[0]["top_k"] == 3

    async def test_filters_are_passed_through_to_the_vector_store(self, tmp_path: Path) -> None:
        vector_store = _FakeVectorStore()
        service = _build_service(tmp_path, vector_store=vector_store)
        image = _image()
        _write_valid_image(tmp_path, image.stored_filename)
        filters = ProductFilters(category="shoes")

        await service.search_by_image(image, filters=filters)

        assert vector_store.search_calls[0]["filters"] == filters

    async def test_no_filters_means_none_is_passed_through(self, tmp_path: Path) -> None:
        vector_store = _FakeVectorStore()
        service = _build_service(tmp_path, vector_store=vector_store)
        image = _image()
        _write_valid_image(tmp_path, image.stored_filename)

        await service.search_by_image(image)

        assert vector_store.search_calls[0]["filters"] is None

    async def test_searches_the_image_collection(self, tmp_path: Path) -> None:
        vector_store = _FakeVectorStore()
        service = _build_service(tmp_path, vector_store=vector_store)
        image = _image()
        _write_valid_image(tmp_path, image.stored_filename)

        await service.search_by_image(image)

        assert vector_store.search_calls[0]["collection"] == VectorCollection.IMAGE

    async def test_embeds_the_standardized_processed_image_not_the_original_upload(
        self, tmp_path: Path
    ) -> None:
        embedding_service = _FakeEmbeddingService()
        service = _build_service(tmp_path, embedding_service=embedding_service)
        image = _image()
        _write_valid_image(tmp_path, image.stored_filename)

        await service.search_by_image(image)

        embedded_path = embedding_service.calls[0]
        assert embedded_path != tmp_path / image.stored_filename
        assert embedded_path.is_file()
        assert embedded_path.parent.name == "processed"

    async def test_propagates_invalid_image_exception_for_a_corrupt_query_image(
        self, tmp_path: Path
    ) -> None:
        service = _build_service(tmp_path)
        image = _image()
        _write_corrupt_file(tmp_path, image.stored_filename)

        with pytest.raises(InvalidImageException):
            await service.search_by_image(image)

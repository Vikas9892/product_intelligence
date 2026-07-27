"""Unit tests for `TextSearchService`.

Uses fake `BaseTextEmbeddingService`/`BaseVectorStore` implementations
(fast, deterministic, no real model or Qdrant involved) — the same
strategy `test_search_service.py` uses for `SearchService`.
"""

from typing import Any
from uuid import uuid4

from app.models.search import NearestNeighbor, ProductFilters, StoredPoint
from app.services.embeddings.text_base import BaseTextEmbeddingService
from app.services.vectorstore.base import BaseVectorStore, VectorCollection, VectorRecord
from app.services.vectorstore.text_search_service import TextSearchService


class _FakeTextEmbeddingService(BaseTextEmbeddingService):
    def __init__(self, *, dimension: int = 4) -> None:
        self._dimension = dimension
        self.calls: list[str] = []

    @property
    def model_name(self) -> str:
        return "fake-text-model"

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed_text(self, text: str) -> list[float]:
        self.calls.append(text)
        return [0.1 * (i + 1) for i in range(self._dimension)]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed_text(text) for text in texts]


class _FakeVectorStore(BaseVectorStore):
    def __init__(
        self,
        *,
        neighbors: list[NearestNeighbor] | None = None,
        stored_point: StoredPoint | None = None,
    ) -> None:
        self._neighbors = neighbors if neighbors is not None else []
        self._stored_point = stored_point
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

    async def retrieve(self, collection: VectorCollection, product_id) -> StoredPoint | None:  # type: ignore[no-untyped-def]
        return self._stored_point

    async def health(self) -> bool:
        return True


def _build_service(
    *,
    text_embedding_service: BaseTextEmbeddingService | None = None,
    vector_store: BaseVectorStore | None = None,
    default_top_k: int | None = None,
) -> TextSearchService:
    return TextSearchService(
        text_embedding_service=(
            text_embedding_service
            if text_embedding_service is not None
            else _FakeTextEmbeddingService()
        ),
        vector_store=vector_store if vector_store is not None else _FakeVectorStore(),
        default_top_k=default_top_k,
    )


class TestSearchByText:
    async def test_returns_neighbors_from_the_vector_store(self) -> None:
        neighbor = NearestNeighbor(product_id=uuid4(), score=0.9, metadata={"name": "Widget"})
        service = _build_service(vector_store=_FakeVectorStore(neighbors=[neighbor]))

        result = await service.search_by_text("a red running shoe")

        assert result.neighbors == [neighbor]
        assert result.query_model_name == "fake-text-model"

    async def test_embeds_the_query_text(self) -> None:
        embedding_service = _FakeTextEmbeddingService()
        service = _build_service(text_embedding_service=embedding_service)

        await service.search_by_text("a red running shoe")

        assert embedding_service.calls == ["a red running shoe"]

    async def test_searches_the_text_collection(self) -> None:
        vector_store = _FakeVectorStore()
        service = _build_service(vector_store=vector_store)

        await service.search_by_text("a red running shoe")

        assert vector_store.search_calls[0]["collection"] == VectorCollection.TEXT

    async def test_uses_the_configured_default_top_k_when_not_specified(self) -> None:
        vector_store = _FakeVectorStore()
        service = _build_service(vector_store=vector_store, default_top_k=7)

        await service.search_by_text("query")

        assert vector_store.search_calls[0]["top_k"] == 7

    async def test_explicit_top_k_overrides_the_default(self) -> None:
        vector_store = _FakeVectorStore()
        service = _build_service(vector_store=vector_store, default_top_k=7)

        await service.search_by_text("query", top_k=3)

        assert vector_store.search_calls[0]["top_k"] == 3

    async def test_filters_are_passed_through_to_the_vector_store(self) -> None:
        vector_store = _FakeVectorStore()
        service = _build_service(vector_store=vector_store)
        filters = ProductFilters(category="shoes")

        await service.search_by_text("query", filters=filters)

        assert vector_store.search_calls[0]["filters"] == filters

    async def test_no_filters_means_none_is_passed_through(self) -> None:
        vector_store = _FakeVectorStore()
        service = _build_service(vector_store=vector_store)

        await service.search_by_text("query")

        assert vector_store.search_calls[0]["filters"] is None


class TestRetrieveById:
    async def test_returns_the_stored_point_from_the_text_collection(self) -> None:
        product_id = uuid4()
        stored_point = StoredPoint(
            product_id=product_id, vector=[0.1, 0.2, 0.3, 0.4], metadata={"brand": "Nike"}
        )
        vector_store = _FakeVectorStore(stored_point=stored_point)
        service = _build_service(vector_store=vector_store)

        point = await service.retrieve_by_id(product_id)

        assert point == stored_point

    async def test_returns_none_when_not_indexed(self) -> None:
        service = _build_service(vector_store=_FakeVectorStore())

        assert await service.retrieve_by_id(uuid4()) is None

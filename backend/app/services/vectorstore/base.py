"""Vector store abstraction.

`BaseVectorStore` is the interface `SearchService`, `TextSearchService`,
and `ProductService` depend on — not `QdrantVectorStore` directly. Today's
only implementation talks to Qdrant; swapping in Pinecone or Weaviate
later means writing one new class that satisfies this interface, with
nothing outside `app/services/vectorstore/` needing to change. This is
the same "depend on the seam, not the concrete implementation" reasoning
that already shapes `BaseEmbeddingService` (Phase 4).

Every abstract method now takes an explicit `collection: VectorCollection`
first argument (Phase 6) — image and text embeddings live in separate
Qdrant collections (different models, different dimensions), so a vector
store implementation needs to know which one an operation targets.
`upsert_image`/`upsert_text`/`search_image`/`search_text` are the
phase's requested per-modality convenience methods; they're concrete here
(not abstract), implemented once in terms of the five abstract primitives
— "no duplicated logic" per modality, and a concrete `BaseVectorStore`
subclass only ever has to implement `upsert`/`search`/`delete`/`exists`/
`health` to get all four for free.

Every method is `async def`, matching every other service in this
codebase, even though a concrete implementation's actual I/O (an HTTP call
to Qdrant) is blocking. Callers should never need to know or care whether
"search for nearest neighbors" happens to block a thread internally.
"""

from abc import ABC, abstractmethod
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.search import NearestNeighbor, ProductFilters


class VectorCollection(StrEnum):
    """Which of the two Qdrant collections (Phase 6) an operation targets."""

    IMAGE = "image"
    TEXT = "text"


class VectorRecord(BaseModel):
    """One embedding plus its filterable metadata, ready to be upserted.

    Distinct from `app.models.embedding.ImageEmbedding`/
    `app.models.text_embedding.TextEmbedding` (the *embedding* domain
    models `CLIPEmbeddingService`/`SentenceTransformerEmbeddingService`
    produce) — this is the *storage* shape a vector store actually
    persists: the vector itself, plus arbitrary product metadata (name,
    brand, category, price, description, ...) Qdrant keeps as the point's
    payload and can later filter searches on. `ProductService` builds one
    of these per modality from a `Product` right before calling `upsert`.
    """

    product_id: UUID
    vector: list[float]
    metadata: dict[str, Any] = Field(default_factory=dict)


class BaseVectorStore(ABC):
    """Interface for storing and searching product embedding vectors."""

    @abstractmethod
    async def upsert(self, collection: VectorCollection, records: list[VectorRecord]) -> None:
        """Insert or update `records` in `collection`, keyed by `product_id`.

        Upserting an already-present `product_id` replaces its vector and
        metadata in place rather than creating a duplicate entry.
        """
        raise NotImplementedError

    @abstractmethod
    async def search(
        self,
        collection: VectorCollection,
        query_vector: list[float],
        *,
        top_k: int,
        filters: ProductFilters | None = None,
    ) -> list[NearestNeighbor]:
        """Return up to `top_k` nearest neighbors to `query_vector` in `collection`, best match first."""
        raise NotImplementedError

    @abstractmethod
    async def delete(self, collection: VectorCollection, product_ids: list[UUID]) -> None:
        """Remove the records for `product_ids` from `collection`, if present."""
        raise NotImplementedError

    @abstractmethod
    async def exists(self, collection: VectorCollection, product_id: UUID) -> bool:
        """Return whether a record for `product_id` is currently stored in `collection`."""
        raise NotImplementedError

    @abstractmethod
    async def health(self) -> bool:
        """Return whether the underlying store is currently reachable and usable."""
        raise NotImplementedError

    async def upsert_image(self, records: list[VectorRecord]) -> None:
        """Upsert `records` into the image collection."""
        await self.upsert(VectorCollection.IMAGE, records)

    async def upsert_text(self, records: list[VectorRecord]) -> None:
        """Upsert `records` into the text collection."""
        await self.upsert(VectorCollection.TEXT, records)

    async def search_image(
        self,
        query_vector: list[float],
        *,
        top_k: int,
        filters: ProductFilters | None = None,
    ) -> list[NearestNeighbor]:
        """Search the image collection for `query_vector`'s nearest neighbors."""
        return await self.search(VectorCollection.IMAGE, query_vector, top_k=top_k, filters=filters)

    async def search_text(
        self,
        query_vector: list[float],
        *,
        top_k: int,
        filters: ProductFilters | None = None,
    ) -> list[NearestNeighbor]:
        """Search the text collection for `query_vector`'s nearest neighbors."""
        return await self.search(VectorCollection.TEXT, query_vector, top_k=top_k, filters=filters)

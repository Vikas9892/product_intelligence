"""Vector store abstraction.

`BaseVectorStore` is the interface `SearchService` and `ProductService`
depend on — not `QdrantVectorStore` directly. Today's only implementation
talks to Qdrant; swapping in Pinecone or Weaviate later means writing one
new class that satisfies this interface, with nothing outside
`app/services/vectorstore/` needing to change. This is the same "depend
on the seam, not the concrete implementation" reasoning that already
shapes `BaseEmbeddingService` (Phase 4).

Every method is `async def`, matching every other service in this
codebase, even though a concrete implementation's actual I/O (an HTTP call
to Qdrant) is blocking. Callers should never need to know or care whether
"search for nearest neighbors" happens to block a thread internally.
"""

from abc import ABC, abstractmethod
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.search import NearestNeighbor


class VectorRecord(BaseModel):
    """One embedding plus its filterable metadata, ready to be upserted.

    Distinct from `app.models.embedding.ImageEmbedding` (the *embedding*
    domain model `CLIPEmbeddingService` produces) — this is the *storage*
    shape a vector store actually persists: the vector itself, plus
    arbitrary product metadata (name, category, price, ...) Qdrant keeps
    as the point's payload and can later filter searches on.
    `ProductService` builds one of these from a `Product` right before
    calling `upsert`.
    """

    product_id: UUID
    vector: list[float]
    metadata: dict[str, Any] = Field(default_factory=dict)


class BaseVectorStore(ABC):
    """Interface for storing and searching product embedding vectors."""

    @abstractmethod
    async def upsert(self, records: list[VectorRecord]) -> None:
        """Insert or update `records`, keyed by `product_id`.

        Upserting an already-present `product_id` replaces its vector and
        metadata in place rather than creating a duplicate entry.
        """
        raise NotImplementedError

    @abstractmethod
    async def search(
        self,
        query_vector: list[float],
        *,
        top_k: int,
        filters: dict[str, Any] | None = None,
    ) -> list[NearestNeighbor]:
        """Return up to `top_k` nearest neighbors to `query_vector`, best match first.

        `filters` is an optional equality filter on payload fields (e.g.
        `{"category": "shoes"}`) — every neighbor returned must match
        every key/value pair given.
        """
        raise NotImplementedError

    @abstractmethod
    async def delete(self, product_ids: list[UUID]) -> None:
        """Remove the records for `product_ids`, if present."""
        raise NotImplementedError

    @abstractmethod
    async def exists(self, product_id: UUID) -> bool:
        """Return whether a record for `product_id` is currently stored."""
        raise NotImplementedError

    @abstractmethod
    async def health(self) -> bool:
        """Return whether the underlying store is currently reachable and usable."""
        raise NotImplementedError

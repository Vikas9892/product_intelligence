"""Qdrant-backed implementation of `BaseVectorStore`.

Talks to Qdrant through the official `qdrant-client` Python SDK. Every
client call is synchronous/blocking (an HTTP round trip) — like every
other service in this codebase (`ImageProcessingService`,
`CLIPEmbeddingService`, ...), each one runs inside `run_in_threadpool` so
it never blocks the event loop.

The collection is created lazily — on first actual use (upsert, search,
delete, or exists), not at construction time — using the same
double-checked-locking pattern `ModelManager` (Phase 4) uses for lazily
loading a model exactly once. This matters for the same reason it did
there: constructing a `QdrantVectorStore` (which `ProductService`/
`SearchService` do as part of their own construction) must not require a
live Qdrant connection, or every dependency-injection unit test — and the
whole application at startup — would need a running Qdrant just to build
an object graph, before any request ever actually needs one.

Cosine distance is the only metric configured for the collection, since
`CLIPEmbeddingService` already L2-normalizes every embedding it produces
specifically so cosine similarity is meaningful (see that module's
docstring).
"""

import threading
from typing import Any
from uuid import UUID

from qdrant_client import QdrantClient
from qdrant_client import models as qmodels
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.logging import get_logger
from app.exceptions.errors import VectorStoreException
from app.models.search import NearestNeighbor
from app.services.vectorstore.base import BaseVectorStore, VectorRecord

logger = get_logger(__name__)


class QdrantVectorStore(BaseVectorStore):
    """Stores and searches product embedding vectors in a Qdrant collection."""

    def __init__(
        self,
        *,
        client: QdrantClient | None = None,
        collection_name: str | None = None,
        vector_size: int | None = None,
    ) -> None:
        self._client = client if client is not None else QdrantClient(url=settings.vector_store.url)
        self._collection_name = (
            collection_name
            if collection_name is not None
            else settings.vector_store.collection_name
        )
        self._vector_size = (
            vector_size if vector_size is not None else settings.vector_store.vector_size
        )
        self._collection_ready = False
        self._collection_lock = threading.Lock()

    def _ensure_collection(self) -> None:
        """Create the collection (cosine distance) if it doesn't already exist.

        Double-checked locking: an already-ready collection (the common
        case) never contends on the lock at all, and concurrent first
        callers only trigger one real `create_collection` call between
        them — the exact same shape as `ModelManager.get_model`.
        """
        if self._collection_ready:
            return

        with self._collection_lock:
            if self._collection_ready:
                return
            try:
                if not self._client.collection_exists(self._collection_name):
                    logger.info(
                        "Creating Qdrant collection '%s' (size=%d, distance=cosine)",
                        self._collection_name,
                        self._vector_size,
                    )
                    self._client.create_collection(
                        collection_name=self._collection_name,
                        vectors_config=qmodels.VectorParams(
                            size=self._vector_size, distance=qmodels.Distance.COSINE
                        ),
                    )
                self._collection_ready = True
            except Exception as exc:
                raise VectorStoreException(
                    f"Failed to ensure Qdrant collection '{self._collection_name}' exists."
                ) from exc

    async def upsert(self, records: list[VectorRecord]) -> None:
        if not records:
            return

        await run_in_threadpool(self._ensure_collection)
        points = [
            qmodels.PointStruct(
                id=str(record.product_id), vector=record.vector, payload=record.metadata
            )
            for record in records
        ]
        try:
            await run_in_threadpool(
                self._client.upsert, collection_name=self._collection_name, points=points
            )
        except Exception as exc:
            raise VectorStoreException("Failed to upsert vectors into the vector store.") from exc

        logger.info("Upserted %d vector(s) into '%s'", len(records), self._collection_name)

    async def search(
        self,
        query_vector: list[float],
        *,
        top_k: int,
        filters: dict[str, Any] | None = None,
    ) -> list[NearestNeighbor]:
        query_filter = _build_filter(filters) if filters else None
        await run_in_threadpool(self._ensure_collection)
        try:
            response = await run_in_threadpool(
                self._client.query_points,
                collection_name=self._collection_name,
                query=query_vector,
                query_filter=query_filter,
                limit=top_k,
                with_payload=True,
            )
        except Exception as exc:
            raise VectorStoreException("Failed to search the vector store.") from exc

        return [
            NearestNeighbor(
                product_id=UUID(str(point.id)), score=point.score, metadata=point.payload or {}
            )
            for point in response.points
        ]

    async def delete(self, product_ids: list[UUID]) -> None:
        if not product_ids:
            return

        await run_in_threadpool(self._ensure_collection)
        try:
            await run_in_threadpool(
                self._client.delete,
                collection_name=self._collection_name,
                points_selector=qmodels.PointIdsList(
                    points=[str(product_id) for product_id in product_ids]
                ),
            )
        except Exception as exc:
            raise VectorStoreException("Failed to delete vectors from the vector store.") from exc

    async def exists(self, product_id: UUID) -> bool:
        await run_in_threadpool(self._ensure_collection)
        try:
            records = await run_in_threadpool(
                self._client.retrieve,
                collection_name=self._collection_name,
                ids=[str(product_id)],
                with_payload=False,
                with_vectors=False,
            )
        except Exception as exc:
            raise VectorStoreException(
                "Failed to check the vector store for an existing record."
            ) from exc

        return len(records) > 0

    async def health(self) -> bool:
        """Return whether Qdrant is reachable — never raises, unlike every other method.

        A health check exists specifically to answer "is the store up?"
        without itself throwing when it isn't. Every other method raises
        `VectorStoreException` on failure, since a caller there is trying
        to get actual work done, not just probe availability.
        """
        try:
            await run_in_threadpool(self._client.get_collections)
            return True
        except Exception:
            return False


def _build_filter(filters: dict[str, Any]) -> qmodels.Filter:
    """Translate a simple equality-filter dict into Qdrant's `Filter` structure.

    Every key/value pair must match (`must=[...]`) — good enough for the
    equality-only filtering (e.g. `{"category": "shoes"}`) this codebase
    actually needs; it's not a general query-DSL translator.
    """
    return qmodels.Filter(
        must=[
            qmodels.FieldCondition(key=key, match=qmodels.MatchValue(value=value))
            for key, value in filters.items()
        ]
    )

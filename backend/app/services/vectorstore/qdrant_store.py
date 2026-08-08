"""Qdrant-backed implementation of `BaseVectorStore`.

Talks to Qdrant through the official `qdrant-client` Python SDK. Every
client call is synchronous/blocking (an HTTP round trip) — like every
other service in this codebase (`ImageProcessingService`,
`CLIPEmbeddingService`, ...), each one runs inside `run_in_threadpool` so
it never blocks the event loop.

Manages *two* Qdrant collections (Phase 6) — image embeddings and text
embeddings live in separate collections, since they come from different
models with different dimensions and have no reason to be compared
against each other directly. Each collection is created lazily, on first
actual use, independently of the other, using the same double-checked-
locking pattern `ModelManager` (Phase 4) uses for lazily loading a model
exactly once — one dict of "is this collection ready?" flags and one
dict of locks, keyed by `VectorCollection`, instead of duplicating the
single-collection version of this logic twice.

Cosine distance is the only metric configured for either collection,
since `CLIPEmbeddingService`/`SentenceTransformerEmbeddingService` both
already normalize every embedding they produce specifically so cosine
similarity is meaningful.
"""

import threading
from uuid import UUID

from qdrant_client import QdrantClient
from qdrant_client import models as qmodels
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.logging import get_logger
from app.exceptions.errors import VectorStoreException
from app.models.search import NearestNeighbor, ProductFilters, StoredPoint
from app.services.vectorstore.base import BaseVectorStore, VectorCollection, VectorRecord
from app.utils.facets import normalize_facet

logger = get_logger(__name__)


class QdrantVectorStore(BaseVectorStore):
    """Stores and searches product embedding vectors across two Qdrant collections."""

    def __init__(
        self,
        *,
        client: QdrantClient | None = None,
        image_collection_name: str | None = None,
        image_vector_size: int | None = None,
        text_collection_name: str | None = None,
        text_vector_size: int | None = None,
    ) -> None:
        self._client = client if client is not None else QdrantClient(url=settings.vector_store.url)
        self._collection_names: dict[VectorCollection, str] = {
            VectorCollection.IMAGE: (
                image_collection_name
                if image_collection_name is not None
                else settings.vector_store.image_collection_name
            ),
            VectorCollection.TEXT: (
                text_collection_name
                if text_collection_name is not None
                else settings.vector_store.text_collection_name
            ),
        }
        self._vector_sizes: dict[VectorCollection, int] = {
            VectorCollection.IMAGE: (
                image_vector_size
                if image_vector_size is not None
                else settings.vector_store.image_vector_size
            ),
            VectorCollection.TEXT: (
                text_vector_size
                if text_vector_size is not None
                else settings.vector_store.text_vector_size
            ),
        }
        self._collection_ready: dict[VectorCollection, bool] = dict.fromkeys(
            VectorCollection, False
        )
        self._collection_locks: dict[VectorCollection, threading.Lock] = {
            collection: threading.Lock() for collection in VectorCollection
        }

    def _ensure_collection(self, collection: VectorCollection) -> None:
        """Create `collection` (cosine distance) if it doesn't already exist.

        Double-checked locking, per collection: an already-ready
        collection (the common case) never contends on its lock at all,
        and concurrent first callers for the *same* collection only
        trigger one real `create_collection` call between them — the
        exact same shape as `ModelManager.get_model`, just keyed by
        `VectorCollection` instead of a model name.
        """
        if self._collection_ready[collection]:
            return

        with self._collection_locks[collection]:
            if self._collection_ready[collection]:
                return
            name = self._collection_names[collection]
            size = self._vector_sizes[collection]
            try:
                if not self._client.collection_exists(name):
                    logger.info(
                        "Creating Qdrant collection '%s' (size=%d, distance=cosine)", name, size
                    )
                    self._client.create_collection(
                        collection_name=name,
                        vectors_config=qmodels.VectorParams(
                            size=size, distance=qmodels.Distance.COSINE
                        ),
                    )
                self._ensure_facet_indexes(name)
                self._collection_ready[collection] = True
            except Exception as exc:
                raise VectorStoreException(
                    f"Failed to ensure Qdrant collection '{name}' exists."
                ) from exc

    def _ensure_facet_indexes(self, name: str) -> None:
        """Create keyword payload indexes for the facet keys, idempotently.

        Filtering works without an index -- Qdrant falls back to a full scan --
        but only an index makes it scale, and creating them as part of
        collection setup means a fresh environment cannot silently end up
        without them. Idempotent because Qdrant errors on a duplicate index and
        that is not a failure worth propagating.
        """
        for field in _FACET_INDEX_FIELDS:
            try:
                self._client.create_payload_index(
                    collection_name=name,
                    field_name=field,
                    field_schema=qmodels.PayloadSchemaType.KEYWORD,
                )
            except Exception:
                logger.debug("Payload index '%s' already present on '%s'", field, name)

    async def upsert(self, collection: VectorCollection, records: list[VectorRecord]) -> None:
        if not records:
            return

        await run_in_threadpool(self._ensure_collection, collection)
        name = self._collection_names[collection]
        points = [
            qmodels.PointStruct(
                id=str(record.product_id), vector=record.vector, payload=record.metadata
            )
            for record in records
        ]
        try:
            await run_in_threadpool(self._client.upsert, collection_name=name, points=points)
        except Exception as exc:
            raise VectorStoreException(f"Failed to upsert vectors into '{name}'.") from exc

        logger.info("Upserted %d vector(s) into '%s'", len(records), name)

    async def search(
        self,
        collection: VectorCollection,
        query_vector: list[float],
        *,
        top_k: int,
        filters: ProductFilters | None = None,
    ) -> list[NearestNeighbor]:
        name = self._collection_names[collection]
        query_filter = _build_filter(filters) if filters is not None else None
        await run_in_threadpool(self._ensure_collection, collection)
        try:
            response = await run_in_threadpool(
                self._client.query_points,
                collection_name=name,
                query=query_vector,
                query_filter=query_filter,
                limit=top_k,
                with_payload=True,
            )
        except Exception as exc:
            raise VectorStoreException(f"Failed to search '{name}'.") from exc

        return [
            NearestNeighbor(
                product_id=UUID(str(point.id)), score=point.score, metadata=point.payload or {}
            )
            for point in response.points
        ]

    async def delete(self, collection: VectorCollection, product_ids: list[UUID]) -> None:
        if not product_ids:
            return

        name = self._collection_names[collection]
        await run_in_threadpool(self._ensure_collection, collection)
        try:
            await run_in_threadpool(
                self._client.delete,
                collection_name=name,
                points_selector=qmodels.PointIdsList(
                    points=[str(product_id) for product_id in product_ids]
                ),
            )
        except Exception as exc:
            raise VectorStoreException(f"Failed to delete vectors from '{name}'.") from exc

    async def exists(self, collection: VectorCollection, product_id: UUID) -> bool:
        name = self._collection_names[collection]
        await run_in_threadpool(self._ensure_collection, collection)
        try:
            records = await run_in_threadpool(
                self._client.retrieve,
                collection_name=name,
                ids=[str(product_id)],
                with_payload=False,
                with_vectors=False,
            )
        except Exception as exc:
            raise VectorStoreException(f"Failed to check '{name}' for an existing record.") from exc

        return len(records) > 0

    async def retrieve(self, collection: VectorCollection, product_id: UUID) -> StoredPoint | None:
        name = self._collection_names[collection]
        await run_in_threadpool(self._ensure_collection, collection)
        try:
            records = await run_in_threadpool(
                self._client.retrieve,
                collection_name=name,
                ids=[str(product_id)],
                with_payload=True,
                with_vectors=True,
            )
        except Exception as exc:
            raise VectorStoreException(f"Failed to retrieve a record from '{name}'.") from exc

        if not records:
            return None

        record = records[0]
        vector = record.vector
        # This codebase only ever configures one unnamed vector per
        # collection (see `_ensure_collection`) — a dict/named-vector
        # response would mean the collection was created outside this
        # class's own control, which can't happen through this class's
        # own API.
        assert isinstance(vector, list)

        return StoredPoint(product_id=product_id, vector=vector, metadata=record.payload or {})

    async def health(self) -> bool:
        """Return whether Qdrant is reachable — never raises, unlike every other method.

        A health check exists specifically to answer "is the store up?"
        without itself throwing when it isn't, and (unlike every other
        method here) has nothing to do with either individual collection.
        """
        try:
            await run_in_threadpool(self._client.get_collections)
            return True
        except Exception:
            return False


#: Payload fields filtered on, and therefore worth indexing. The canonical
#: `*_key` forms, not the display values -- see `_build_filter`.
_FACET_INDEX_FIELDS = ("brand_key", "category_key")


def _build_filter(filters: ProductFilters) -> qmodels.Filter:
    """Translate `ProductFilters` into Qdrant's `Filter` structure.

    Equality conditions for `brand`/`category`, a `Range` condition for
    price when either bound is given — every condition present must
    match (`must=[...]`). A `ProductFilters` with every field `None`
    translates to an empty `must=[]`, which Qdrant treats as "match
    everything," so passing one through is always safe even when nothing
    is actually being filtered.

    Facet values are matched against the canonical `*_key` payload fields via
    `normalize_facet`, never against the raw user string. `MatchValue` is exact
    and case-sensitive, so passing what the user typed straight through meant
    "Men shoes" could not match stored "men-shoes" and "nike" could not match
    stored "Nike" — every filtered search returned nothing. The normalizer here
    is the same one the ingest path uses.

    A facet that normalizes to `None` (empty, blank, punctuation-only) adds no
    condition at all, rather than a condition matching the empty string. An
    empty brand box must not exclude every product.
    """
    conditions: list[qmodels.FieldCondition] = []
    brand_key = normalize_facet(filters.brand)
    if brand_key is not None:
        conditions.append(
            qmodels.FieldCondition(key="brand_key", match=qmodels.MatchValue(value=brand_key))
        )
    category_key = normalize_facet(filters.category)
    if category_key is not None:
        conditions.append(
            qmodels.FieldCondition(key="category_key", match=qmodels.MatchValue(value=category_key))
        )
    if filters.min_price is not None or filters.max_price is not None:
        conditions.append(
            qmodels.FieldCondition(
                key="price",
                range=qmodels.Range(gte=filters.min_price, lte=filters.max_price),
            )
        )
    built = qmodels.Filter(must=conditions)
    # The literal filter, not the intent. Debug-level so it costs nothing in
    # normal operation, but when a filtered search misbehaves the actual keys
    # and values sent to Qdrant are in the log rather than inferred.
    logger.debug("Qdrant filter built: %s", built.model_dump(exclude_none=True))
    return built

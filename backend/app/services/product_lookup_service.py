"""`ProductLookupService`: reads an indexed product back by ID.

The read side of the catalog. `ProductService` writes products into the vector
store during ingestion; this reads them out again, which nothing previously
could -- see `app/schemas/product_summary.py` for why that mattered and why a
lookup endpoint was chosen over embedding products in every response.

Thin by design: the vector store already exposes `retrieve_image`/
`retrieve_text`, so this resolves IDs to payloads and shapes them, holding no
state and making no decisions.
"""

from uuid import UUID

from app.core.logging import get_logger
from app.schemas.product_summary import ProductSummary
from app.services.vectorstore.base import BaseVectorStore
from app.services.vectorstore.qdrant_store import QdrantVectorStore

logger = get_logger(__name__)


class ProductLookupService:
    """Resolves product IDs to their stored catalog metadata."""

    def __init__(self, *, vector_store: BaseVectorStore | None = None) -> None:
        self._vector_store = vector_store if vector_store is not None else QdrantVectorStore()

    async def get(self, product_id: UUID) -> ProductSummary | None:
        """Return `product_id`'s summary, or `None` if it is not indexed.

        Reads the image collection first and falls back to text. Both carry
        the identical payload, but a product can legitimately exist in one and
        not the other -- an image-only or text-only indexing failure should
        still resolve a name rather than report the product missing.
        """
        point = await self._vector_store.retrieve_image(product_id)
        if point is None:
            point = await self._vector_store.retrieve_text(product_id)
        if point is None:
            return None
        return ProductSummary.from_metadata(product_id, point.metadata)

    async def get_many(self, product_ids: list[UUID]) -> tuple[list[ProductSummary], list[UUID]]:
        """Resolve several IDs. Returns `(found, missing)`.

        Duplicates in the input are collapsed, and order follows the caller's
        request so a client can zip the result back onto its own list without
        re-sorting.

        Lookups run sequentially rather than concurrently: the store is a
        single Qdrant instance, batches are capped at `MAX_BATCH_SIZE`, and
        fanning out would add failure modes for a saving that does not
        register at this size.
        """
        found: list[ProductSummary] = []
        missing: list[UUID] = []
        seen: set[UUID] = set()

        for product_id in product_ids:
            if product_id in seen:
                continue
            seen.add(product_id)
            summary = await self.get(product_id)
            if summary is None:
                missing.append(product_id)
            else:
                found.append(summary)

        logger.info(
            "Product batch resolved: requested=%d, unique=%d, found=%d, missing=%d",
            len(product_ids),
            len(seen),
            len(found),
            len(missing),
        )
        return found, missing

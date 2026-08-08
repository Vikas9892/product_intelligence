"""Text search service: turns a text query into similar-product results.

Mirrors `SearchService` (Phase 5), but for text: embeds the query string
via `BaseTextEmbeddingService` and searches the text collection. No image
processing step here — there's no file to standardize, just a string.

Kept as its own focused service, not merged into `SearchService`, so
`HybridSearchService` (Phase 6) can compose "search by image" and "search
by text" independently and fuse their results — see that module's
docstring for why a combined "hybrid" service is better built by
composing two single-responsibility services than by growing
`SearchService` a second, unrelated job.
"""

from uuid import UUID

from app.core.config import settings
from app.core.logging import get_logger
from app.models.search import ProductFilters, SearchQuery, SearchResult, StoredPoint
from app.services.embeddings.sentence_transformer_service import (
    SentenceTransformerEmbeddingService,
)
from app.services.embeddings.text_base import BaseTextEmbeddingService
from app.services.vectorstore.base import BaseVectorStore
from app.services.vectorstore.qdrant_store import QdrantVectorStore

logger = get_logger(__name__)


class TextSearchService:
    """Orchestrates turning a text query into a ranked list of similar products."""

    def __init__(
        self,
        *,
        text_embedding_service: BaseTextEmbeddingService | None = None,
        vector_store: BaseVectorStore | None = None,
        default_top_k: int | None = None,
    ) -> None:
        self._text_embedding_service = (
            text_embedding_service
            if text_embedding_service is not None
            else SentenceTransformerEmbeddingService()
        )
        self._vector_store = vector_store if vector_store is not None else QdrantVectorStore()
        self._default_top_k = (
            default_top_k if default_top_k is not None else settings.vector_store.default_top_k
        )

    async def search_by_text(
        self,
        query: str,
        *,
        top_k: int | None = None,
        filters: ProductFilters | None = None,
    ) -> SearchResult:
        """Embed `query` and search for products with similar text.

        `filters`, if given, restricts results by brand/category/price
        range. Raises whatever `BaseTextEmbeddingService`/`BaseVectorStore`
        raise on failure.
        """
        # Logs the query's length, not its content — free-form user text
        # has no place in structured logs any more than a raw embedding
        # vector would.
        logger.info("Text search requested: query_length=%d", len(query))

        vector = await self._text_embedding_service.embed_text(query)
        return await self.search_by_vector(vector, top_k=top_k, filters=filters)

    async def search_by_vector(
        self,
        vector: list[float],
        *,
        top_k: int | None = None,
        filters: ProductFilters | None = None,
    ) -> SearchResult:
        """Search for products whose text embedding is closest to an already-computed `vector`.

        Unlike `search_by_text`, this never runs embedding generation —
        used by `HybridSearchService.search_by_product_id` (Phase 9) with
        an existing product's own already-indexed vector (see
        `retrieve_by_id`).
        """
        resolved_top_k = top_k if top_k is not None else self._default_top_k
        search_query = SearchQuery(
            vector=vector,
            model_name=self._text_embedding_service.model_name,
            top_k=resolved_top_k,
            filters=filters,
        )
        logger.info(
            "Executing text search: model=%s, top_k=%d, filters=%s",
            search_query.model_name,
            search_query.top_k,
            search_query.filters,
        )

        neighbors = await self._vector_store.search_text(
            search_query.vector, top_k=search_query.top_k, filters=search_query.filters
        )
        if not neighbors and filters is not None and _has_facets(filters):
            # A filtered search returning nothing is the signature of a facet
            # mismatch, and it is invisible in a results=0 line. Naming the
            # applied facets makes this class of failure diagnosable from logs
            # rather than only from the UI.
            logger.warning(
                "Text search returned no results with facets applied: "
                "brand=%r, category=%r, min_price=%r, max_price=%r",
                filters.brand,
                filters.category,
                filters.min_price,
                filters.max_price,
            )
        logger.info("Text search completed: results=%d", len(neighbors))

        return SearchResult(query_model_name=search_query.model_name, neighbors=neighbors)

    async def retrieve_by_id(self, product_id: UUID) -> StoredPoint | None:
        """Fetch `product_id`'s own stored text vector + metadata, or `None` if not indexed."""
        return await self._vector_store.retrieve_text(product_id)


def _has_facets(filters: ProductFilters) -> bool:
    """Whether any metadata facet was actually applied."""
    return any(
        value is not None
        for value in (filters.brand, filters.category, filters.min_price, filters.max_price)
    )

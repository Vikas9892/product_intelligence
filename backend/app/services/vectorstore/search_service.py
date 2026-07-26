"""Search service: turns an uploaded query image into similar-product results.

`SearchService.search_by_image` orchestrates, in order: standardize the
already-stored query image the same way a product image is standardized
(`ImageProcessingService`, Phase 3 — this must reuse the exact same
standardization a stored product's image already went through, otherwise
the two embeddings being compared wouldn't be comparable), generate its
embedding (`BaseEmbeddingService`, Phase 4), and search the vector store
for its nearest neighbors (`BaseVectorStore`, Phase 5).

Kept as a thin orchestrator, the same way `ProductService` is: no
similarity-scoring logic of its own, no knowledge of Qdrant specifically
— everything delegates to the same services `ProductService` already
composes, plus `BaseVectorStore`. `app/api/search.py` calls this service
and `UploadService` and nothing else — the router itself has no business
logic and never talks to the vector store directly.
"""

from pathlib import Path

from app.core.config import settings
from app.core.logging import get_logger
from app.models.search import SearchQuery, SearchResult
from app.schemas.product import ProductImage
from app.services.embeddings.base import BaseEmbeddingService
from app.services.embeddings.clip_service import CLIPEmbeddingService
from app.services.image_processing_service import ImageProcessingService
from app.services.vectorstore.base import BaseVectorStore
from app.services.vectorstore.qdrant_store import QdrantVectorStore

logger = get_logger(__name__)


class SearchService:
    """Orchestrates turning an uploaded query image into a ranked list of similar products."""

    def __init__(
        self,
        *,
        image_processing_service: ImageProcessingService | None = None,
        embedding_service: BaseEmbeddingService | None = None,
        vector_store: BaseVectorStore | None = None,
        upload_dir: Path | None = None,
        default_top_k: int | None = None,
    ) -> None:
        self._image_processing_service = (
            image_processing_service
            if image_processing_service is not None
            else ImageProcessingService()
        )
        self._embedding_service = (
            embedding_service if embedding_service is not None else CLIPEmbeddingService()
        )
        self._vector_store = vector_store if vector_store is not None else QdrantVectorStore()
        self._upload_dir = upload_dir if upload_dir is not None else settings.storage.upload_dir
        self._default_top_k = (
            default_top_k if default_top_k is not None else settings.vector_store.default_top_k
        )

    async def search_by_image(
        self,
        image: ProductImage,
        *,
        top_k: int | None = None,
        category: str | None = None,
    ) -> SearchResult:
        """Standardize, embed, and search for products visually similar to `image`.

        `image` must describe a file `UploadService` has already written
        under this service's `upload_dir` — the same contract
        `ProductService.process_upload` uses. `category`, if given,
        restricts results to products upserted with that exact category
        metadata. Raises whatever `ImageProcessingService`,
        `BaseEmbeddingService`, or `BaseVectorStore` raise on failure.
        """
        logger.info("Search requested: filename=%s", image.stored_filename)

        stored_path = self._upload_dir / image.stored_filename
        image_metadata = await self._image_processing_service.process_image(
            stored_path, image.stored_filename
        )

        vector = await self._embedding_service.generate_embedding(image_metadata.processed_path)

        resolved_top_k = top_k if top_k is not None else self._default_top_k
        filters = {"category": category} if category is not None else None
        query = SearchQuery(
            vector=vector,
            model_name=self._embedding_service.model_name,
            top_k=resolved_top_k,
            filters=filters,
        )
        logger.info(
            "Executing search: model=%s, top_k=%d, filters=%s",
            query.model_name,
            query.top_k,
            query.filters,
        )

        neighbors = await self._vector_store.search(
            query.vector, top_k=query.top_k, filters=query.filters
        )
        logger.info(
            "Search completed: filename=%s, results=%d",
            image.stored_filename,
            len(neighbors),
        )

        return SearchResult(query_model_name=query.model_name, neighbors=neighbors)

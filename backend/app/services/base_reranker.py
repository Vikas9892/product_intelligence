"""Abstract reranker interface (Phase 11).

Mirrors `app.services.embeddings.text_base.BaseTextEmbeddingService`/
`app.services.vectorstore.base.BaseVectorStore`: an abstract seam between
"something that reranks candidates" and `RerankerService`'s own
cross-encoder implementation, so `HybridSearchService`/
`RecommendationEngineService`/`DuplicateDetectionService` (Milestone 4)
depend on this interface rather than the concrete class — a future
reranking strategy could be substituted without those callers changing.
"""

from abc import ABC, abstractmethod

from app.models.rerank_result import RerankResult
from app.models.search import HybridSearchResult


class BaseReranker(ABC):
    """Reranks a list of already-retrieved candidates against a query."""

    @abstractmethod
    async def rerank(
        self,
        query: str,
        candidates: list[HybridSearchResult],
        *,
        top_k: int | None = None,
    ) -> RerankResult:
        """Rerank `candidates` against `query`, returning at most `top_k` of them.

        `candidates` is assumed already retrieved (by hybrid search) —
        implementations must not perform retrieval of their own.
        """
        raise NotImplementedError

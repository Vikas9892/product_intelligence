"""Internal domain model: `RerankResult`, the final output of one reranking pass.

Built exclusively by `RerankerService.rerank` (`app/services/reranker_service.py`).
`HybridSearchService`/`RecommendationEngineService`/`DuplicateDetectionService`
(Milestone 4) each consume `.candidates` to reorder/rescore their own
domain objects — none of them expose a `RerankResult` directly, the same
"internal domain model, not necessarily an API response shape" reasoning
`HybridSearchResult` itself already follows.
"""

from pydantic import BaseModel, Field

from app.models.reranked_candidate import RerankedCandidate


class RerankResult(BaseModel):
    """A reranked, truncated candidate list for one query, plus how it was produced."""

    query: str
    candidates: list[RerankedCandidate] = Field(default_factory=list)
    processing_time: float = Field(default=0.0, ge=0)
    #: Size of the candidate pool actually sent to the cross-encoder
    #: (after the `RERANK_TOP_N` pool cap, before `top_k` truncation) —
    #: distinct from `len(candidates)`, which reflects `top_k` too.
    original_count: int = 0

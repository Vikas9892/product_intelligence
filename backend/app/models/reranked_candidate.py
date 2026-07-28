"""Internal domain model: `RerankedCandidate`, one candidate after cross-encoder reranking.

Built exclusively by `RerankerService` (`app/services/reranker_service.py`)
— see that module's own docstring for the full pipeline (overfetch, score
query-candidate pairs, sort, truncate). Collapses "the scorer's output"
and "the ranked unit" into one type, the same reasoning
`RecommendationCandidate` (Phase 9) already documents for why it doesn't
split those into two separate types the way `DuplicateResult`/
`DuplicateCandidate` (Phase 8) do: there's no separate "list of raw
per-signal contribution objects" this phase needs beyond what's here.

`metadata` carries the original `HybridSearchResult.metadata` forward
unchanged ("preserve metadata" — Milestone 3's own requirement) so a
caller that only has the reranked list can still recover a candidate's
name/brand/category/etc. without a second lookup.
"""

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.rerank_reason import RerankReason


class RerankedCandidate(BaseModel):
    """One candidate's original and cross-encoder-refined scores, plus its final rank."""

    product_id: UUID
    original_score: float
    rerank_score: float
    final_rank: int
    metadata: dict[str, Any] = Field(default_factory=dict)
    reason: RerankReason

"""Internal domain model: `RerankReason`, the structured evidence behind one rerank outcome.

Produced by `RerankerService` (Phase 11) alongside a candidate's rerank
score — kept as *structured* rank-movement data rather than only a
sentence, mirroring the same "structured evidence, presentation kept
separate" split `RecommendationReason` (Phase 9) already establishes
between a scorer's raw findings and how they get explained.
"""

from pydantic import BaseModel


class RerankReason(BaseModel):
    """Where a candidate ranked before and after cross-encoder reranking, plus why."""

    original_rank: int
    final_rank: int
    #: `original_rank - final_rank`; positive means the candidate moved
    #: up (a lower rank number is better), negative means it moved down.
    rank_delta: int
    explanation: str = ""

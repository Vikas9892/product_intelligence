"""Internal domain model: `RecommendationCandidate`, one scored recommendation.

Doubles as both `RecommendationScorer`'s return type (Milestone 2 — score
one candidate, no ranking) and the unit `RecommendationEngineService`
ranks/diversifies/truncates (Milestone 3) — unlike Phase 8's split between
`DuplicateResult` (the scorer's detailed output) and `DuplicateCandidate`
(the flatter shape exposed on a decision), there's no need for two
separate types here: `similarity_score`/`quality_score`/`final_score`/
`reason` already *is* the detail, and `product_id` is trivially known by
whichever candidate is being scored — collapsing to one model avoids
inventing a second, structurally-identical type for no benefit.

`explanation` defaults to an empty string here (Milestone 1) — `""`
signals "not yet explained," populated once `RecommendationEngineService`
generates human-readable text from `reason` (Milestone 5). Scoring and
explaining are kept as separate steps: `RecommendationScorer` decides
*what* matched (structured, testable in isolation); the engine decides
*how to phrase it* (a presentation concern, not a scoring one).
"""

from uuid import UUID

from pydantic import BaseModel, Field

from app.models.recommendation_reason import RecommendationReason


class RecommendationCandidate(BaseModel):
    """One candidate product, scored against a target product."""

    product_id: UUID
    similarity_score: float = Field(ge=0, le=1)
    quality_score: float = Field(ge=0, le=1)
    final_score: float = Field(ge=0, le=1)
    reason: RecommendationReason
    explanation: str = ""

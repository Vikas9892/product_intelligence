"""Internal domain model: `RecommendationReason`, the structured evidence behind one recommendation.

Produced by `RecommendationScorer` (Phase 9) alongside a recommendation's
scores — kept as *structured* data (a list of attribute names, a list of
shared tag strings, two booleans) rather than a sentence, so
`RecommendationEngineService` can turn it into a human-readable
explanation (Milestone 5) without the scorer needing to know anything
about phrasing. Separating "what matched" (this model) from "how to say
it" (the explanation string) mirrors the same separation
`AttributePrediction`/`CatalogTag` (Phase 7) already draw between a raw
finding and how it gets presented.
"""

from pydantic import BaseModel, Field


class RecommendationReason(BaseModel):
    """Which specific signals a candidate shared with the target product."""

    matched_attributes: list[str] = Field(default_factory=list)
    shared_tags: list[str] = Field(default_factory=list)
    shared_brand: bool = False
    shared_category: bool = False

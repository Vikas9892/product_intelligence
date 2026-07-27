"""Recommendation schemas: the API contract for `GET /products/{id}/recommendations` (Phase 9).

Deliberately separate from `app.models.recommendation_*` (the internal
domain models `RecommendationScorer`/`RecommendationEngineService` build)
for the same reason `app.schemas.product` is kept separate from
`app.models.product` — see that module's docstring. Never exposes a raw
embedding vector, matching every other response schema in this codebase.

`matched_tags` (not `shared_tags`, unlike the internal
`RecommendationReason`) is the one deliberate renaming — an API consumer
reads "which tags this recommendation matched on" more naturally than
"shared," and there's no reason the wire name has to mirror the internal
field name exactly (the same reasoning `app.schemas.search` already
applies renaming `SearchModality` values to plain strings).
"""

from uuid import UUID

from pydantic import BaseModel, Field


class RecommendationReasonInfo(BaseModel):
    """API-safe view of `app.models.recommendation_reason.RecommendationReason`."""

    matched_attributes: list[str] = Field(default_factory=list)
    matched_tags: list[str] = Field(default_factory=list)
    shared_brand: bool = False
    shared_category: bool = False


class RecommendationInfo(BaseModel):
    """One ranked recommendation.

    `product_id` is the only product-identifying field — there's no
    persistence layer yet (see `backend/README.md`) to resolve a full
    product record from, the same limitation `UploadResponse`/
    `ProductSearchResult` already live with.
    """

    product_id: UUID
    score: float
    reason: RecommendationReasonInfo
    explanation: str


class RecommendationsResponse(BaseModel):
    """Response body for `GET /api/v1/products/{product_id}/recommendations`."""

    recommendation_type: str
    recommendations: list[RecommendationInfo] = Field(default_factory=list)

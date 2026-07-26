"""Internal domain model: `CatalogTag`, one searchable tag generated for a product.

Also defines `Source` — which extraction pipeline produced a given tag or
`app.models.attribute_prediction.AttributePrediction` (text-only,
image-only, or both agreeing) — imported from here by
`attribute_prediction.py` rather than duplicated, since both models need
exactly the same three values.

Placed in `app/models/` (not the phase spec's suggested `app/domain/`)
for the same reason every earlier phase's domain models live there — see
`app.models.product.Product`'s docstring for why this codebase keeps
internal domain models in one place, separate from `app.schemas.*`.
"""

from enum import StrEnum

from pydantic import BaseModel, Field


class Source(StrEnum):
    """Which extraction pipeline produced an attribute prediction or tag."""

    TEXT = "text"
    IMAGE = "image"
    HYBRID = "hybrid"


class CatalogTag(BaseModel):
    """One searchable tag `CatalogIntelligenceService` generated for a product."""

    tag: str
    confidence: float = Field(ge=0, le=1)
    source: Source

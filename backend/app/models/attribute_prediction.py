"""Internal domain model: `AttributePrediction`, one raw candidate value for a
single product attribute, before merge/conflict resolution.

`TextAttributeExtractionService`/`ImageAttributeExtractionService` each
return a `list[AttributePrediction]` — their own independent guesses at
attributes like "color" or "brand", each with its own confidence and
source. `CatalogIntelligenceService` merges these (grouping by
`attribute`, picking the highest-confidence value per group — see that
module's docstring for the full conflict-resolution algorithm) into the
single, already-resolved `app.models.product_attributes.ProductAttributes`.
Keeping the raw, pre-merge predictions as their own type (rather than
building `ProductAttributes` directly) is what makes conflict resolution
possible at all: once two predictions are merged into one field, the
information needed to compare them is gone.
"""

from pydantic import BaseModel, Field

from app.models.catalog_tags import Source


class AttributePrediction(BaseModel):
    """One extraction pipeline's guess at the value of a single product attribute.

    `attribute` names a field on `ProductAttributes` (e.g. `"color"`,
    `"brand"`) — deliberately a plain string rather than an enum, since
    both extraction services and `CatalogIntelligenceService` only ever
    need to match it against `ProductAttributes.model_fields`, not
    exhaustively enumerate it up front.
    """

    attribute: str
    value: str
    confidence: float = Field(ge=0, le=1)
    source: Source

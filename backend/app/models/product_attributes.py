"""Internal domain model: `ProductAttributes`, a product's resolved catalog attributes.

The *output* of `CatalogIntelligenceService`'s merge/conflict-resolution
step — every field here is already the single winning value for that
attribute (see `app.models.attribute_prediction.AttributePrediction` for
the pre-merge candidates each extraction service proposes). Every field
is optional: neither `TextAttributeExtractionService` nor
`ImageAttributeExtractionService` can be expected to find every attribute
for every product (a product with no description, for instance, yields
far fewer text-derived attributes than one with a detailed one), and a
missing attribute is a normal, expected outcome — not an error.
"""

from pydantic import BaseModel, Field


class ProductAttributes(BaseModel):
    """A product's resolved catalog attributes, one value per field at most."""

    brand: str | None = None
    category: str | None = None
    subcategory: str | None = None
    color: str | None = None
    material: str | None = None
    pattern: str | None = None
    gender: str | None = None
    age_group: str | None = None
    style: str | None = None
    season: str | None = None
    occasion: str | None = None
    #: Aggregate confidence across every attribute that *was* resolved —
    #: not per-field; see `CatalogIntelligenceService` for how this is
    #: computed from the winning `AttributePrediction`s' own confidences.
    confidence: float = Field(default=0.0, ge=0, le=1)

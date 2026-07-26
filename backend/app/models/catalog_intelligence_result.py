"""Internal domain model: `CatalogIntelligenceResult`, the full output of
`CatalogIntelligenceService` for one product.

Bundles the resolved attributes, the generated tags, and the quality
score together with how long the whole enrichment pipeline took —
`processing_time` exists specifically so that cost is observable
(logged, and available to a caller) without requiring a caller to time
the service call itself.
"""

from pydantic import BaseModel, Field

from app.models.catalog_tags import CatalogTag
from app.models.product_attributes import ProductAttributes


class CatalogIntelligenceResult(BaseModel):
    """The resolved attributes, generated tags, and quality score for one product."""

    attributes: ProductAttributes
    tags: list[CatalogTag] = Field(default_factory=list)
    quality_score: float = Field(ge=0, le=1)
    #: Wall-clock seconds `CatalogIntelligenceService.enrich` took to
    #: produce this result.
    processing_time: float = Field(ge=0)

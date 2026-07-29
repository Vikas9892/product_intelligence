"""Internal domain model: `PriceEstimate`, the full output of one pricing run (Phase 17).

Built by `PricingEngine`: the `estimated_price` (from the configured
`PricingStrategy` over the comparables that survived outlier removal), the
`confidence` band and continuous `confidence_score`, the
`comparables` that informed it, and a human-readable `reason` — the
phase's own "explainable pricing" requirement. Pure, deterministic output:
the same comparables and strategy always produce the same estimate (no ML,
no randomness).

`estimated_price` is `0.0` with `PriceConfidence.LOW` and an empty
`comparables` list when no priced comparable could be found at all — a
caller can tell "no basis to price this" apart from "priced at zero"
(prices are always `> 0`, so a real estimate is never `0.0`).
"""

from pydantic import BaseModel, Field

from app.core.constants import PricingStrategy
from app.models.comparable_product import ComparableProduct
from app.models.price_confidence import PriceConfidence


class PriceEstimate(BaseModel):
    """A fair-market price estimate, its confidence, and the comparables behind it."""

    estimated_price: float = Field(ge=0)
    confidence: PriceConfidence
    confidence_score: float = Field(ge=0, le=1)
    strategy: PricingStrategy
    comparable_count: int = Field(ge=0)
    comparables: list[ComparableProduct] = Field(default_factory=list)
    reason: str

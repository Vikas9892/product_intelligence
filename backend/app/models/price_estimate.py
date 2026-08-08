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

from app.core.constants import PriceStatus, PricingStrategy
from app.models.comparable_product import ComparableProduct
from app.models.price_confidence import PriceConfidence


class PriceEstimate(BaseModel):
    """A fair-market price estimate, its confidence, and the comparables behind it."""

    #: The estimate, or `None` when no estimate was made.
    #:
    #: Absence is modelled as `None`, never as `0.0`. Zero is a *price* -- a
    #: reader seeing "0.00" concludes the product is free or the estimator
    #: crashed, long before reaching the paragraph that explains otherwise.
    #: "We declined to estimate" and "we estimate zero" are different claims
    #: and must not share a representation.
    estimated_price: float | None = Field(default=None, ge=0)
    #: Whether an estimate was produced at all. `status` is the discriminator:
    #: `confidence` is only meaningful when `status is ESTIMATED`.
    status: PriceStatus = PriceStatus.ESTIMATED
    confidence: PriceConfidence
    confidence_score: float = Field(ge=0, le=1)
    strategy: PricingStrategy
    comparable_count: int = Field(ge=0)
    comparables: list[ComparableProduct] = Field(default_factory=list)
    reason: str

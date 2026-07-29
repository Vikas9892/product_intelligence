"""Internal domain model: `PriceConfidence`, how trustworthy a price estimate is (Phase 17).

A coarse, human-readable band (`LOW`/`MEDIUM`/`HIGH`) derived by
`PriceEstimator` from how many comparable products were found and how
tightly their prices agree — a wide spread over few comparables is `LOW`,
a tight spread over many is `HIGH`. `PriceEstimate` carries both this
band and the underlying continuous `confidence_score`, so a caller can
branch on the band or threshold the raw score as it prefers.
"""

from enum import StrEnum


class PriceConfidence(StrEnum):
    """How much to trust a price estimate, as a coarse band."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

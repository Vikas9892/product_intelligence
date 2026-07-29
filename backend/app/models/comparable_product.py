"""Internal domain model: `ComparableProduct`, one priced product used to estimate a fair price (Phase 17).

Built by `PricingEngine` from a `HybridSearchResult` (a semantically
similar, already-indexed product) whose stored metadata carries a usable
`price`. `similarity` is the retrieval (or cross-encoder) score that
found it — used both to weight the `WEIGHTED_AVERAGE` strategy and to show
the caller *why* each comparable was chosen. A `ComparableProduct` always
has a positive `price` (unpriced retrieval results are dropped by
`PriceNormalizer` before one is built), so pricing math never has to
guard against a missing or zero price.
"""

from uuid import UUID

from pydantic import BaseModel, Field


class ComparableProduct(BaseModel):
    """A semantically similar, priced product used as evidence for a price estimate."""

    product_id: UUID
    price: float = Field(gt=0)
    similarity: float
    name: str | None = None
    brand: str | None = None
    category: str | None = None

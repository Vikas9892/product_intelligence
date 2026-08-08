"""Pricing schemas: the API contract for the pricing endpoints (Phase 17).

Deliberately separate from `app.models.price_estimate.PriceEstimate` (the
internal domain model `PricingEngine` builds) for the same reason every
other API schema is kept separate from its domain model. `PricingRequest`
is the `POST /pricing/estimate` body (price a *described* product);
`GET /pricing/{product_id}` prices an already-indexed product and takes no
body. `PricingResponse` is the shared output shape.
"""

from uuid import UUID

from pydantic import BaseModel, Field

from app.models.price_estimate import PriceEstimate


class PricingRequest(BaseModel):
    """Request body for `POST /pricing/estimate` — price a described (not-yet-indexed) product.

    Retrieval uses the product's text (name/brand/category/description),
    so at least a `name` is required; `top_k`/`strategy` are per-request
    overrides of the configured defaults.
    """

    name: str = Field(min_length=1, max_length=200)
    brand: str | None = Field(default=None, max_length=100)
    category: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    top_k: int | None = Field(default=None, gt=0, description="Overrides PRICING__TOP_K.")


class ComparableProductInfo(BaseModel):
    """API-safe view of one `ComparableProduct`."""

    product_id: UUID
    price: float
    similarity: float
    name: str | None = None
    brand: str | None = None
    category: str | None = None


class PricingResponse(BaseModel):
    """Response body for the pricing endpoints.

    `status` discriminates the two states. When it is `"no_estimate"`,
    `estimated_price` is `null` -- never `0.0` -- and `confidence` carries no
    meaning, because there is no estimate to be confident about. Clients must
    branch on `status` rather than testing the price for a sentinel.
    """

    #: `"estimated"` or `"no_estimate"`.
    status: str
    #: `null` when `status` is `"no_estimate"`.
    estimated_price: float | None
    confidence: str
    confidence_score: float
    strategy: str
    comparable_count: int
    pricing_reason: str
    comparables: list[ComparableProductInfo] = Field(default_factory=list)

    @classmethod
    def from_estimate(cls, estimate: PriceEstimate) -> "PricingResponse":
        """Build the API-safe view of `estimate`."""
        return cls(
            status=estimate.status.value,
            estimated_price=estimate.estimated_price,
            confidence=estimate.confidence.value,
            confidence_score=estimate.confidence_score,
            strategy=estimate.strategy.value,
            comparable_count=estimate.comparable_count,
            pricing_reason=estimate.reason,
            comparables=[
                ComparableProductInfo(
                    product_id=c.product_id,
                    price=c.price,
                    similarity=c.similarity,
                    name=c.name,
                    brand=c.brand,
                    category=c.category,
                )
                for c in estimate.comparables
            ],
        )

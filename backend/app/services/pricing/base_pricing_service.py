"""`BasePricingService`: the interface the pricing API depends on (Phase 17).

An abstract seam between "estimate a fair price" and the concrete
`PricingEngine` (Milestone 3), mirroring `BaseReranker`/`BaseVectorStore`/
`BaseExplainer`. Two entry points: price a *described* (not-yet-indexed)
product from its text, and price an *already-indexed* product by ID
(reusing its stored embedding). A route depends on this interface, so a
future alternative pricing implementation could be substituted without the
route changing.
"""

from abc import ABC, abstractmethod
from uuid import UUID

from app.models.price_estimate import PriceEstimate


class BasePricingService(ABC):
    """Estimates a fair market price for a product."""

    @abstractmethod
    async def estimate_for_request(
        self,
        *,
        name: str,
        brand: str | None,
        category: str | None,
        description: str | None,
        top_k: int | None = None,
    ) -> PriceEstimate:
        """Estimate a fair price for a described, not-yet-indexed product."""
        raise NotImplementedError

    @abstractmethod
    async def estimate_for_product(self, product_id: UUID) -> PriceEstimate:
        """Estimate a fair price for an already-indexed product, by ID."""
        raise NotImplementedError

"""FastAPI dependency provider for the pricing engine.

Mirrors `app.dependencies.model_registry.get_model_registry`'s
cached-singleton pattern. `HybridSearchService`/`PriceNormalizer`/
`PriceEstimator` (which `PricingEngine` composes internally) get no
provider of their own — nothing calls them directly from a route.
Returns the `BasePricingService` interface so a route depends on the
seam, not the concrete engine.
"""

from functools import lru_cache

from app.services.pricing.base_pricing_service import BasePricingService
from app.services.pricing.pricing_engine import PricingEngine


@lru_cache(maxsize=1)
def get_pricing_service() -> BasePricingService:
    """Return the process-wide pricing-service singleton, building it on first call."""
    return PricingEngine()

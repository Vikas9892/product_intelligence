"""`PricingEngine`: retrieves comparables and estimates a fair price (Phase 17).

The concrete `BasePricingService`, following the phase's own pipeline:

    text/product -> Hybrid Search (top-K, optional cross-encoder rerank)
        -> PriceNormalizer (keep positively-priced comparables)
        -> PriceEstimator (deterministic aggregation)
        -> PriceEstimate

Reuses the *existing* retrieval pipeline rather than building a new one:
`HybridSearchService.search` (for a described product) and
`.search_by_product_id` (for an already-indexed one). The request path
also reuses the cross-encoder — `reranking_enabled` flows straight into
`HybridSearchService.search`, so pricing comparables are reranked by the
same Phase 11 reranker every other consumer uses. The by-product-id path
uses retrieval order alone (that method has no rerank hook, and price
*aggregation* — unlike top-N ranking — is insensitive to the exact order
of the comparables it averages).

Holds no mutable per-request state, so one instance is safe to share
across concurrent requests. Deterministic end to end: no ML, no
randomness.
"""

import time
from uuid import UUID

from app.core.config import settings
from app.core.logging import get_logger
from app.exceptions.base import AppException
from app.exceptions.errors import PricingException
from app.metrics.metrics_registry import MetricsRegistry
from app.models.price_estimate import PriceEstimate
from app.models.search import HybridSearchResult
from app.services.pricing.base_pricing_service import BasePricingService
from app.services.pricing.price_estimator import PriceEstimator
from app.services.pricing.price_normalizer import PriceNormalizer
from app.services.vectorstore.hybrid_search_service import HybridSearchService
from app.utils.text import build_text_representation

logger = get_logger(__name__)


class PricingEngine(BasePricingService):
    """Estimates a fair price by retrieving, normalizing, and aggregating comparable products."""

    def __init__(
        self,
        *,
        hybrid_search_service: HybridSearchService | None = None,
        normalizer: PriceNormalizer | None = None,
        estimator: PriceEstimator | None = None,
        top_k: int | None = None,
        reranking_enabled: bool | None = None,
        metrics_registry: MetricsRegistry | None = None,
    ) -> None:
        self._hybrid_search_service = (
            hybrid_search_service if hybrid_search_service is not None else HybridSearchService()
        )
        self._normalizer = normalizer if normalizer is not None else PriceNormalizer()
        self._estimator = estimator if estimator is not None else PriceEstimator()
        self._top_k = top_k if top_k is not None else settings.pricing.top_k
        self._reranking_enabled = (
            reranking_enabled
            if reranking_enabled is not None
            else settings.pricing.reranking_enabled
        )
        self._metrics = metrics_registry if metrics_registry is not None else MetricsRegistry()

    async def estimate_for_request(
        self,
        *,
        name: str,
        brand: str | None,
        category: str | None,
        description: str | None,
        top_k: int | None = None,
    ) -> PriceEstimate:
        """Estimate a fair price for a described, not-yet-indexed product.

        Builds the retrieval query from the product's text (the same
        `build_text_representation` every other text-driven feature uses)
        and reranks the comparables with the cross-encoder when enabled.
        Raises `PricingException` (500) if comparable retrieval fails
        unexpectedly; an underlying `AppException` (e.g. a search failure)
        propagates as itself.
        """
        start = time.monotonic()
        text = build_text_representation(name, brand, category, description)
        resolved_top_k = top_k if top_k is not None else self._top_k
        try:
            results = await self._hybrid_search_service.search(
                text=text, top_k=resolved_top_k, reranking_enabled=self._reranking_enabled
            )
        except AppException:
            raise
        except Exception as exc:
            raise PricingException("Failed to retrieve comparable products.") from exc
        return self._estimate(results, start=start)

    async def estimate_for_product(self, product_id: UUID) -> PriceEstimate:
        """Estimate a fair price for an already-indexed product, by ID.

        Reuses `product_id`'s own stored embedding via
        `HybridSearchService.search_by_product_id` (the target is excluded
        from its own comparables). Raises `ResourceNotFoundException` (404)
        if `product_id` isn't indexed (propagated from the search), or
        `PricingException` (500) if retrieval fails unexpectedly.
        """
        start = time.monotonic()
        try:
            results = await self._hybrid_search_service.search_by_product_id(
                product_id, top_k=self._top_k
            )
        except AppException:
            raise
        except Exception as exc:
            raise PricingException("Failed to retrieve comparable products.") from exc
        return self._estimate(results, start=start)

    def _estimate(self, results: list[HybridSearchResult], *, start: float) -> PriceEstimate:
        comparables = self._normalizer.to_comparables(results)
        estimate = self._estimator.estimate(comparables)
        seconds = time.monotonic() - start
        self._metrics.record_pricing(
            seconds=seconds,
            confidence=estimate.confidence.value,
            confidence_score=estimate.confidence_score,
        )
        logger.info(
            "Price estimate complete: retrieved=%d, priced=%d, price=%.2f, "
            "confidence=%s, processing_time=%.4fs",
            len(results),
            estimate.comparable_count,
            estimate.estimated_price,
            estimate.confidence.value,
            seconds,
        )
        return estimate

"""`PriceEstimator`: deterministic aggregation of comparable prices into an estimate (Phase 17).

Pure, stateless, deterministic — no ML, no randomness: the same
comparables and strategy always produce the same `PriceEstimate`. This
milestone implements the three aggregation strategies
(`WEIGHTED_AVERAGE`/`TRIMMED_MEAN`/`MEDIAN`) and a basic count-based
confidence; IQR outlier removal and price-spread-aware confidence refine
this in Milestone 4.

Strategy notes:

- **weighted average** — each comparable's price weighted by its
  similarity, so a closer match pulls the estimate more.
- **trimmed mean** — drops the cheapest/most-expensive `trim_ratio`
  fraction from each end before averaging, so a few extreme listings
  don't skew the estimate.
- **median** — the middle price, fully robust to extreme values.
"""

from statistics import median

from app.core.config import settings
from app.core.constants import PricingStrategy
from app.core.logging import get_logger
from app.models.comparable_product import ComparableProduct
from app.models.price_confidence import PriceConfidence
from app.models.price_estimate import PriceEstimate

logger = get_logger(__name__)


class PriceEstimator:
    """Aggregates comparable prices into a `PriceEstimate` using a configurable strategy."""

    def __init__(
        self,
        *,
        strategy: PricingStrategy | None = None,
        trim_ratio: float | None = None,
        min_comparables: int | None = None,
    ) -> None:
        self._strategy = strategy if strategy is not None else settings.pricing.strategy
        self._trim_ratio = trim_ratio if trim_ratio is not None else settings.pricing.trim_ratio
        self._min_comparables = (
            min_comparables if min_comparables is not None else settings.pricing.min_comparables
        )

    def estimate(
        self, comparables: list[ComparableProduct], *, strategy: PricingStrategy | None = None
    ) -> PriceEstimate:
        """Aggregate `comparables` into a `PriceEstimate` using `strategy` (or the configured default)."""
        resolved_strategy = strategy if strategy is not None else self._strategy

        if not comparables:
            return PriceEstimate(
                estimated_price=0.0,
                confidence=PriceConfidence.LOW,
                confidence_score=0.0,
                strategy=resolved_strategy,
                comparable_count=0,
                comparables=[],
                reason="No comparable priced products were found.",
            )

        price = _aggregate(comparables, resolved_strategy, trim_ratio=self._trim_ratio)
        confidence_score, confidence = self._confidence(comparables)

        estimate = PriceEstimate(
            estimated_price=round(price, 2),
            confidence=confidence,
            confidence_score=confidence_score,
            strategy=resolved_strategy,
            comparable_count=len(comparables),
            comparables=comparables,
            reason=(
                f"Estimated from {len(comparables)} comparable product(s) "
                f"using the {resolved_strategy.value} strategy."
            ),
        )
        logger.info(
            "Price estimated: strategy=%s, price=%.2f, comparables=%d, confidence=%s",
            resolved_strategy.value,
            estimate.estimated_price,
            len(comparables),
            confidence.value,
        )
        return estimate

    def _confidence(self, comparables: list[ComparableProduct]) -> tuple[float, PriceConfidence]:
        """Basic count-based confidence — refined with price spread in Milestone 4."""
        count = len(comparables)
        if count < self._min_comparables:
            return 0.3, PriceConfidence.LOW
        if count < self._min_comparables * 2:
            return 0.6, PriceConfidence.MEDIUM
        return 0.9, PriceConfidence.HIGH


def _aggregate(
    comparables: list[ComparableProduct], strategy: PricingStrategy, *, trim_ratio: float
) -> float:
    prices = [c.price for c in comparables]
    if strategy is PricingStrategy.MEDIAN:
        return median(prices)
    if strategy is PricingStrategy.WEIGHTED_AVERAGE:
        return _weighted_average(comparables)
    return _trimmed_mean(prices, trim_ratio=trim_ratio)


def _weighted_average(comparables: list[ComparableProduct]) -> float:
    """Mean of prices weighted by similarity; falls back to a plain mean if all weights are <= 0."""
    total_weight = sum(max(c.similarity, 0.0) for c in comparables)
    if total_weight <= 0:
        return sum(c.price for c in comparables) / len(comparables)
    return sum(c.price * max(c.similarity, 0.0) for c in comparables) / total_weight


def _trimmed_mean(prices: list[float], *, trim_ratio: float) -> float:
    """Mean after dropping the lowest/highest `trim_ratio` fraction from each end."""
    ordered = sorted(prices)
    cut = int(len(ordered) * trim_ratio)
    trimmed = ordered[cut : len(ordered) - cut] if cut else ordered
    # Trimming everything (tiny list, large ratio) falls back to the full set.
    kept = trimmed if trimmed else ordered
    return sum(kept) / len(kept)

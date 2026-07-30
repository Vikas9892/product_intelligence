"""`PriceEstimator`: deterministic aggregation of comparable prices into an estimate (Phase 17).

Pure, stateless, deterministic — no ML, no randomness: the same
comparables and strategy always produce the same `PriceEstimate`. The
full pricing pipeline:

    comparables
      -> IQR outlier removal (drop prices outside the Tukey fence)
      -> aggregate by strategy (WEIGHTED_AVERAGE / TRIMMED_MEAN / MEDIAN)
      -> confidence from surviving count + price spread
      -> PriceEstimate (+ explainable reason)

Strategy notes:

- **weighted average** — each comparable's price weighted by its
  similarity, so a closer match pulls the estimate more.
- **trimmed mean** — drops the cheapest/most-expensive `trim_ratio`
  fraction from each end before averaging.
- **median** — the middle price, fully robust to extreme values.

Outlier removal runs *before* aggregation so even the mean-based
strategies aren't skewed by a mispriced listing; confidence blends how
many comparables survived with how tightly their prices agree (a wide
spread over few comparables is untrustworthy, a tight spread over many is
solid).
"""

from statistics import mean, median, pstdev, quantiles

from app.core.config import settings
from app.core.constants import PricingStrategy
from app.core.logging import get_logger
from app.models.comparable_product import ComparableProduct
from app.models.price_confidence import PriceConfidence
from app.models.price_estimate import PriceEstimate

logger = get_logger(__name__)

#: Below this many comparables, IQR quartiles aren't meaningful, so
#: outlier removal is skipped entirely.
_MIN_FOR_OUTLIER_REMOVAL = 4

#: Confidence-score cutoffs mapping the blended count·spread score to a band.
_HIGH_SCORE = 0.7
_MEDIUM_SCORE = 0.4


class PriceEstimator:
    """Aggregates comparable prices into a `PriceEstimate` using a configurable strategy."""

    def __init__(
        self,
        *,
        strategy: PricingStrategy | None = None,
        trim_ratio: float | None = None,
        min_comparables: int | None = None,
        outlier_iqr_multiplier: float | None = None,
    ) -> None:
        pricing = settings.pricing
        self._strategy = strategy if strategy is not None else pricing.strategy
        self._trim_ratio = trim_ratio if trim_ratio is not None else pricing.trim_ratio
        self._min_comparables = (
            min_comparables if min_comparables is not None else pricing.min_comparables
        )
        self._outlier_iqr_multiplier = (
            outlier_iqr_multiplier
            if outlier_iqr_multiplier is not None
            else pricing.outlier_iqr_multiplier
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

        kept, removed = self._remove_outliers(comparables)
        price = _aggregate(kept, resolved_strategy, trim_ratio=self._trim_ratio)
        confidence_score, confidence = self._confidence(kept)

        estimate = PriceEstimate(
            estimated_price=round(price, 2),
            confidence=confidence,
            confidence_score=confidence_score,
            strategy=resolved_strategy,
            comparable_count=len(kept),
            comparables=kept,
            reason=_build_reason(
                count=len(kept),
                removed=removed,
                strategy=resolved_strategy,
                confidence=confidence,
            ),
        )
        logger.info(
            "Price estimated: strategy=%s, price=%.2f, kept=%d, removed=%d, confidence=%s",
            resolved_strategy.value,
            estimate.estimated_price,
            len(kept),
            removed,
            confidence.value,
        )
        return estimate

    def _remove_outliers(
        self, comparables: list[ComparableProduct]
    ) -> tuple[list[ComparableProduct], int]:
        """Drop comparables whose price falls outside the Tukey IQR fence.

        Skipped for fewer than four comparables (quartiles aren't
        meaningful) or when the multiplier is disabled. The fence always
        spans at least `[Q1, Q3]`, so every interquartile comparable
        survives — `kept` is never empty.
        """
        if len(comparables) < _MIN_FOR_OUTLIER_REMOVAL or self._outlier_iqr_multiplier <= 0:
            return comparables, 0
        prices = sorted(c.price for c in comparables)
        q1, _q2, q3 = quantiles(prices, n=4)
        iqr = q3 - q1
        lower = q1 - self._outlier_iqr_multiplier * iqr
        upper = q3 + self._outlier_iqr_multiplier * iqr
        kept = [c for c in comparables if lower <= c.price <= upper]
        return kept, len(comparables) - len(kept)

    def _confidence(self, comparables: list[ComparableProduct]) -> tuple[float, PriceConfidence]:
        """Blend surviving-comparable count with price-spread agreement into a confidence.

        `count_factor` saturates at twice `min_comparables`; `spread_factor`
        is `1 - coefficient_of_variation` (tighter agreement -> higher), so
        the blended score rewards both plentiful *and* consistent
        comparables. Below `min_comparables` the band is forced to `LOW` no
        matter how tight the spread — too little evidence to trust.
        """
        count = len(comparables)
        prices = [c.price for c in comparables]
        mean_price = mean(prices)
        coefficient_of_variation = (
            pstdev(prices) / mean_price if count > 1 and mean_price > 0 else 0.0
        )
        count_factor = min(count / (self._min_comparables * 2), 1.0)
        spread_factor = max(0.0, 1.0 - coefficient_of_variation)
        score = round(count_factor * spread_factor, 3)

        if count < self._min_comparables:
            return score, PriceConfidence.LOW
        if score >= _HIGH_SCORE:
            return score, PriceConfidence.HIGH
        if score >= _MEDIUM_SCORE:
            return score, PriceConfidence.MEDIUM
        return score, PriceConfidence.LOW


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


def _build_reason(
    *, count: int, removed: int, strategy: PricingStrategy, confidence: PriceConfidence
) -> str:
    """Build the human-readable pricing reason — the phase's 'explainable pricing' requirement."""
    parts = [f"Estimated from {count} comparable product(s) using the {strategy.value} strategy"]
    if removed:
        parts.append(f"after removing {removed} price outlier(s)")
    parts.append(f"({confidence.value} confidence)")
    return " ".join(parts) + "."

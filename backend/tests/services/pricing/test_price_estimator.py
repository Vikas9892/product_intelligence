"""Unit tests for `PriceEstimator`'s aggregation strategies (Milestone 2)."""

from uuid import uuid4

from app.core.constants import PricingStrategy
from app.models.comparable_product import ComparableProduct
from app.models.price_confidence import PriceConfidence
from app.services.pricing.price_estimator import PriceEstimator


def _comparable(price: float, *, similarity: float = 0.9) -> ComparableProduct:
    return ComparableProduct(product_id=uuid4(), price=price, similarity=similarity)


class TestMedian:
    def test_returns_the_middle_price(self) -> None:
        estimator = PriceEstimator(strategy=PricingStrategy.MEDIAN, min_comparables=1)
        comparables = [_comparable(10.0), _comparable(20.0), _comparable(300.0)]

        estimate = estimator.estimate(comparables)

        assert estimate.estimated_price == 20.0
        assert estimate.strategy is PricingStrategy.MEDIAN


class TestWeightedAverage:
    def test_weights_by_similarity(self) -> None:
        estimator = PriceEstimator(strategy=PricingStrategy.WEIGHTED_AVERAGE, min_comparables=1)
        comparables = [_comparable(100.0, similarity=0.9), _comparable(200.0, similarity=0.1)]

        estimate = estimator.estimate(comparables)

        # (100*0.9 + 200*0.1) / (0.9 + 0.1) = 110
        assert estimate.estimated_price == 110.0

    def test_falls_back_to_plain_mean_when_all_weights_are_zero(self) -> None:
        estimator = PriceEstimator(strategy=PricingStrategy.WEIGHTED_AVERAGE, min_comparables=1)
        comparables = [_comparable(100.0, similarity=0.0), _comparable(200.0, similarity=0.0)]

        estimate = estimator.estimate(comparables)

        assert estimate.estimated_price == 150.0


class TestTrimmedMean:
    def test_drops_extremes_before_averaging(self) -> None:
        estimator = PriceEstimator(
            strategy=PricingStrategy.TRIMMED_MEAN, trim_ratio=0.2, min_comparables=1
        )
        # 5 prices, trim 20% (1 from each end): keeps 10, 12, 14 -> mean 12.
        comparables = [
            _comparable(1.0),
            _comparable(10.0),
            _comparable(12.0),
            _comparable(14.0),
            _comparable(1000.0),
        ]

        estimate = estimator.estimate(comparables)

        assert estimate.estimated_price == 12.0

    def test_no_trim_averages_everything(self) -> None:
        estimator = PriceEstimator(
            strategy=PricingStrategy.TRIMMED_MEAN, trim_ratio=0.1, min_comparables=1
        )
        comparables = [_comparable(10.0), _comparable(20.0)]  # cut = int(2*0.1)=0

        estimate = estimator.estimate(comparables)

        assert estimate.estimated_price == 15.0


class TestEmpty:
    def test_no_comparables_yields_a_zero_low_confidence_estimate(self) -> None:
        estimator = PriceEstimator(strategy=PricingStrategy.MEDIAN)

        estimate = estimator.estimate([])

        assert estimate.estimated_price == 0.0
        assert estimate.confidence is PriceConfidence.LOW
        assert estimate.comparable_count == 0


class TestConfidenceBands:
    def test_few_comparables_is_low(self) -> None:
        estimator = PriceEstimator(strategy=PricingStrategy.MEDIAN, min_comparables=3)

        estimate = estimator.estimate([_comparable(10.0), _comparable(20.0)])

        assert estimate.confidence is PriceConfidence.LOW

    def test_moderate_comparables_is_medium(self) -> None:
        estimator = PriceEstimator(strategy=PricingStrategy.MEDIAN, min_comparables=3)

        estimate = estimator.estimate([_comparable(10.0) for _ in range(4)])

        assert estimate.confidence is PriceConfidence.MEDIUM

    def test_many_comparables_is_high(self) -> None:
        estimator = PriceEstimator(strategy=PricingStrategy.MEDIAN, min_comparables=3)

        estimate = estimator.estimate([_comparable(10.0) for _ in range(6)])

        assert estimate.confidence is PriceConfidence.HIGH


class TestStrategyOverride:
    def test_per_call_strategy_overrides_the_configured_default(self) -> None:
        estimator = PriceEstimator(strategy=PricingStrategy.MEDIAN, min_comparables=1)
        comparables = [_comparable(10.0), _comparable(20.0), _comparable(300.0)]

        estimate = estimator.estimate(comparables, strategy=PricingStrategy.TRIMMED_MEAN)

        assert estimate.strategy is PricingStrategy.TRIMMED_MEAN

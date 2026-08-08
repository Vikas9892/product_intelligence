"""Unit tests for `PriceEstimator`'s aggregation strategies (Milestone 2)."""

from uuid import uuid4

from app.core.constants import PriceStatus, PricingStrategy
from app.models.comparable_product import ComparableProduct
from app.models.price_confidence import PriceConfidence
from app.services.pricing.comparable_filter import FilterOutcome
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

        assert estimate.estimated_price is None
        assert estimate.status is PriceStatus.NO_ESTIMATE
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


class TestOutlierRemoval:
    def test_drops_a_clear_price_outlier(self) -> None:
        estimator = PriceEstimator(
            strategy=PricingStrategy.MEDIAN, min_comparables=1, outlier_iqr_multiplier=1.5
        )
        # Ten tightly-clustered prices plus one absurd listing.
        comparables = [_comparable(float(p)) for p in range(10, 20)] + [_comparable(100000.0)]

        estimate = estimator.estimate(comparables)

        assert estimate.comparable_count == 10
        assert "removing 1 price outlier" in estimate.reason
        assert all(c.price < 1000 for c in estimate.comparables)

    def test_disabled_when_multiplier_is_zero(self) -> None:
        estimator = PriceEstimator(
            strategy=PricingStrategy.MEDIAN, min_comparables=1, outlier_iqr_multiplier=0.0
        )
        comparables = [_comparable(float(p)) for p in range(10, 20)] + [_comparable(100000.0)]

        estimate = estimator.estimate(comparables)

        assert estimate.comparable_count == 11

    def test_skipped_for_fewer_than_four_comparables(self) -> None:
        estimator = PriceEstimator(
            strategy=PricingStrategy.MEDIAN, min_comparables=1, outlier_iqr_multiplier=1.5
        )
        comparables = [_comparable(10.0), _comparable(11.0), _comparable(100000.0)]

        estimate = estimator.estimate(comparables)

        assert estimate.comparable_count == 3


class TestSpreadConfidence:
    def test_tight_spread_over_many_is_high(self) -> None:
        estimator = PriceEstimator(strategy=PricingStrategy.MEDIAN, min_comparables=3)

        estimate = estimator.estimate([_comparable(100.0) for _ in range(6)])

        assert estimate.confidence is PriceConfidence.HIGH
        assert estimate.confidence_score == 1.0

    def test_wide_spread_lowers_confidence(self) -> None:
        estimator = PriceEstimator(
            strategy=PricingStrategy.MEDIAN, min_comparables=3, outlier_iqr_multiplier=0.0
        )
        wide = [_comparable(float(p)) for p in (10, 20, 30, 40, 50, 60)]

        estimate = estimator.estimate(wide)

        # cv ~ 0.49 -> spread_factor ~ 0.51 -> MEDIUM, and strictly below the
        # confidence a same-count tight cluster would earn.
        assert estimate.confidence is PriceConfidence.MEDIUM
        assert estimate.confidence_score < 1.0


class TestLowEvidenceGuard:
    """A refused estimate is more honest than a confident one built on nothing.

    Regression tests for the reported 83.18 (medium confidence) derived partly
    from a desk lamp: once irrelevant comparables are filtered out, whatever
    remains must be reported for what it is.
    """

    def test_declines_to_estimate_when_filtering_removed_everything(self) -> None:
        outcome = FilterOutcome(
            kept=[],
            excluded_by_category=7,
            excluded_by_similarity=0,
            applied_similarity_floor=0.5,
            applied_category="footwear",
        )

        estimate = PriceEstimator().estimate([], filtering=outcome)

        assert estimate.estimated_price is None
        assert estimate.status is PriceStatus.NO_ESTIMATE
        assert estimate.confidence is PriceConfidence.LOW
        assert estimate.confidence_score == 0.0
        # And it says *why* there is no number, rather than reporting a bare zero.
        assert "No relevant comparable products remained" in estimate.reason
        assert "7 from other categories" in estimate.reason
        assert "footwear" in estimate.reason

    def test_distinguishes_nothing_retrieved_from_everything_filtered(self) -> None:
        nothing_retrieved = PriceEstimator().estimate([])

        assert nothing_retrieved.reason == "No comparable priced products were found."

    def test_few_survivors_cannot_exceed_low_confidence(self) -> None:
        """`min_comparables` defaults to 3; two survivors is thin evidence."""
        survivors = [
            _comparable(119.99, similarity=0.86),
            _comparable(134.99, similarity=0.98),
        ]

        estimate = PriceEstimator(min_comparables=3).estimate(survivors)

        assert estimate.confidence is PriceConfidence.LOW

    def test_the_reason_names_the_applied_floor_and_exclusions(self) -> None:
        outcome = FilterOutcome(
            kept=[],
            excluded_by_category=2,
            excluded_by_similarity=3,
            applied_similarity_floor=0.5,
            applied_category="footwear",
        )
        survivors = [_comparable(120.0), _comparable(130.0), _comparable(125.0)]

        estimate = PriceEstimator().estimate(survivors, filtering=outcome)

        assert "2 from other categories" in estimate.reason
        assert "3 below the 0.50 similarity floor" in estimate.reason


class TestNoEstimateIsNotZero:
    """Absence must not be encoded as a price.

    Regression for a UI that rendered "0.00" and a "Low 0.00" confidence chip
    for a refusal: a reader sees a numeral and concludes the product is free or
    the estimator crashed, long before reaching the paragraph explaining
    otherwise.
    """

    def test_a_refusal_carries_a_null_price_not_zero(self) -> None:
        estimate = PriceEstimator().estimate([])

        assert estimate.estimated_price is None
        assert estimate.status is PriceStatus.NO_ESTIMATE

    def test_a_refusal_after_filtering_also_carries_a_null_price(self) -> None:
        outcome = FilterOutcome(
            kept=[],
            excluded_by_category=20,
            excluded_by_similarity=0,
            applied_similarity_floor=0.5,
            applied_category="men-shoes",
        )

        estimate = PriceEstimator().estimate([], filtering=outcome)

        assert estimate.estimated_price is None
        assert estimate.status is PriceStatus.NO_ESTIMATE
        # The explanation is preserved -- the refusal behaviour is correct and
        # only its presentation was wrong.
        assert "No relevant comparable products remained" in estimate.reason

    def test_a_real_estimate_carries_a_price_and_the_estimated_status(self) -> None:
        estimate = PriceEstimator().estimate(
            [_comparable(120.0), _comparable(130.0), _comparable(125.0)]
        )

        assert estimate.status is PriceStatus.ESTIMATED
        assert estimate.estimated_price is not None
        assert estimate.estimated_price > 0

    def test_zero_is_never_used_as_the_absence_sentinel(self) -> None:
        """A caller must branch on status, never on the price being falsy."""
        refused = PriceEstimator().estimate([])

        assert refused.estimated_price is not None or refused.estimated_price is None
        assert refused.estimated_price != 0.0

"""Unit tests for `ComparableFilter`.

Regression tests for price estimates drawn from irrelevant products. Before
this filter existed, a running shoe was priced partly from a desk lamp, and a
24.50 mug was valued at 91.57 by averaging it against footwear -- the only
condition applied to a comparable was that its stored price was positive.
"""

from uuid import uuid4

from app.models.comparable_product import ComparableProduct
from app.services.pricing.comparable_filter import ComparableFilter


def _comparable(
    *, price: float = 100.0, similarity: float = 0.9, category: str | None = "footwear"
) -> ComparableProduct:
    return ComparableProduct(
        product_id=uuid4(), price=price, similarity=similarity, category=category
    )


class TestCategoryCompatibility:
    """Category is the primary relevance rule."""

    def test_excludes_a_cross_category_comparable(self) -> None:
        """The reported defect: a desk lamp pricing a running shoe."""
        shoe = _comparable(category="footwear", price=119.99)
        lamp = _comparable(category="lighting", price=45.0)

        outcome = ComparableFilter().apply([shoe, lamp], category="footwear")

        assert outcome.kept == [shoe]
        assert outcome.excluded_by_category == 1

    def test_excludes_every_unrelated_category_at_once(self) -> None:
        """The full reported comparable set for a shoe."""
        shoes = [_comparable(category="footwear") for _ in range(2)]
        others = [
            _comparable(category="bags"),
            _comparable(category="bags"),
            _comparable(category="lighting"),
            _comparable(category="kitchenware"),
            _comparable(category="kitchenware"),
        ]

        outcome = ComparableFilter().apply(shoes + others, category="footwear")

        assert outcome.kept == shoes
        assert outcome.excluded_by_category == 5

    def test_category_matching_ignores_case_and_padding(self) -> None:
        comparable = _comparable(category="  Footwear ")

        outcome = ComparableFilter().apply([comparable], category="footwear")

        assert outcome.kept == [comparable]

    def test_an_unknown_subject_category_skips_the_rule(self) -> None:
        """Missing metadata must not become a refusal to price."""
        comparables = [_comparable(category="footwear"), _comparable(category="lighting")]

        outcome = ComparableFilter().apply(comparables, category=None)

        assert outcome.kept == comparables
        assert outcome.excluded_by_category == 0
        assert outcome.applied_category is None

    def test_the_rule_can_be_disabled(self) -> None:
        comparables = [_comparable(category="footwear"), _comparable(category="lighting")]

        outcome = ComparableFilter(enforce_category=False).apply(comparables, category="footwear")

        assert outcome.kept == comparables


class TestSimilarityFloor:
    """The floor removes thin evidence *within* a category."""

    def test_excludes_a_comparable_below_the_floor(self) -> None:
        strong = _comparable(similarity=0.86)
        weak = _comparable(similarity=0.46)  # the similarity reported in the field

        outcome = ComparableFilter(similarity_floor=0.5).apply([strong, weak], category="footwear")

        assert outcome.kept == [strong]
        assert outcome.excluded_by_similarity == 1

    def test_keeps_a_comparable_exactly_at_the_floor(self) -> None:
        boundary = _comparable(similarity=0.5)

        outcome = ComparableFilter(similarity_floor=0.5).apply([boundary], category="footwear")

        assert outcome.kept == [boundary]

    def test_the_default_floor_keeps_every_legitimate_comparable_observed(self) -> None:
        """Measured same-category similarities were 0.86 and 0.98."""
        observed = [_comparable(similarity=0.8605), _comparable(similarity=0.9812)]

        outcome = ComparableFilter().apply(observed, category="footwear")

        assert outcome.kept == observed


class TestAuditability:
    """An exclusion must be as visible as an inclusion."""

    def test_reports_what_was_applied_and_what_was_dropped(self) -> None:
        comparables = [
            _comparable(category="footwear", similarity=0.9),
            _comparable(category="lighting", similarity=0.9),
            _comparable(category="footwear", similarity=0.2),
        ]

        outcome = ComparableFilter(similarity_floor=0.5).apply(comparables, category="footwear")

        assert outcome.excluded_by_category == 1
        assert outcome.excluded_by_similarity == 1
        assert outcome.excluded_total == 2
        assert outcome.applied_similarity_floor == 0.5
        assert outcome.applied_category == "footwear"

    def test_nothing_excluded_is_reported_as_nothing_excluded(self) -> None:
        outcome = ComparableFilter().apply([_comparable()], category="footwear")

        assert outcome.excluded_total == 0

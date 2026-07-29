"""Unit tests for `BusinessRulesEvaluator`."""

from typing import Any

from app.models.product_attributes import ProductAttributes
from app.services.duplicate.business_rules_evaluator import BusinessRulesEvaluator


def _evaluator(**kwargs: Any) -> BusinessRulesEvaluator:
    return BusinessRulesEvaluator(
        require_same_brand=kwargs.pop("require_same_brand", False),
        require_same_category=kwargs.pop("require_same_category", False),
        max_price_difference_ratio=kwargs.pop("max_price_difference_ratio", 0.25),
        title_similarity_threshold=kwargs.pop("title_similarity_threshold", 0.85),
    )


def _codes(reasons: list[Any]) -> set[str]:
    return {reason.code for reason in reasons}


class TestBrandRule:
    def test_same_brand_is_a_positive_signal(self) -> None:
        result = _evaluator().evaluate(
            name="Red Shoe",
            brand="Nike",
            category=None,
            price=None,
            attributes=ProductAttributes(),
            candidate_metadata={"brand": "nike"},
        )

        assert "same_brand" in _codes(result.reasons)
        assert result.score == 1.0
        assert result.veto is False

    def test_brand_mismatch_vetoes_when_required(self) -> None:
        result = _evaluator(require_same_brand=True).evaluate(
            name="Red Shoe",
            brand="Nike",
            category=None,
            price=None,
            attributes=ProductAttributes(),
            candidate_metadata={"brand": "Adidas"},
        )

        assert "brand_mismatch" in _codes(result.reasons)
        assert result.veto is True

    def test_brand_mismatch_does_not_veto_when_not_required(self) -> None:
        result = _evaluator(require_same_brand=False).evaluate(
            name="Red Shoe",
            brand="Nike",
            category=None,
            price=None,
            attributes=ProductAttributes(),
            candidate_metadata={"brand": "Adidas"},
        )

        assert result.veto is False

    def test_missing_brand_makes_the_rule_inapplicable(self) -> None:
        result = _evaluator().evaluate(
            name="Red Shoe",
            brand=None,
            category=None,
            price=None,
            attributes=ProductAttributes(),
            candidate_metadata={"brand": "Nike"},
        )

        assert "same_brand" not in _codes(result.reasons)
        assert "brand_mismatch" not in _codes(result.reasons)


class TestCategoryRule:
    def test_same_category_is_a_positive_signal(self) -> None:
        result = _evaluator().evaluate(
            name="Red Shoe",
            brand=None,
            category="Running Shoes",
            price=None,
            attributes=ProductAttributes(),
            candidate_metadata={"category": "running shoes"},
        )

        assert "same_category" in _codes(result.reasons)

    def test_category_mismatch_vetoes_when_required(self) -> None:
        result = _evaluator(require_same_category=True).evaluate(
            name="Red Shoe",
            brand=None,
            category="Shoes",
            price=None,
            attributes=ProductAttributes(),
            candidate_metadata={"category": "Kitchenware"},
        )

        assert "category_mismatch" in _codes(result.reasons)
        assert result.veto is True


class TestPriceRule:
    def test_close_price_is_a_positive_signal(self) -> None:
        result = _evaluator(max_price_difference_ratio=0.25).evaluate(
            name="Red Shoe",
            brand=None,
            category=None,
            price=110.0,
            attributes=ProductAttributes(),
            candidate_metadata={"price": 100.0},
        )

        assert "close_price" in _codes(result.reasons)

    def test_distant_price_is_a_negative_signal(self) -> None:
        result = _evaluator(max_price_difference_ratio=0.25).evaluate(
            name="Red Shoe",
            brand=None,
            category=None,
            price=200.0,
            attributes=ProductAttributes(),
            candidate_metadata={"price": 100.0},
        )

        assert "price_difference" in _codes(result.reasons)

    def test_missing_price_makes_the_rule_inapplicable(self) -> None:
        result = _evaluator().evaluate(
            name="Red Shoe",
            brand=None,
            category=None,
            price=None,
            attributes=ProductAttributes(),
            candidate_metadata={"price": 100.0},
        )

        assert "close_price" not in _codes(result.reasons)
        assert "price_difference" not in _codes(result.reasons)


class TestTitleRule:
    def test_high_title_similarity_is_a_positive_signal(self) -> None:
        result = _evaluator(title_similarity_threshold=0.85).evaluate(
            name="Nike Air Max 90",
            brand=None,
            category=None,
            price=None,
            attributes=ProductAttributes(),
            candidate_metadata={"name": "Nike Air Max 90"},
        )

        assert "title_similarity" in _codes(result.reasons)

    def test_low_title_similarity_is_a_negative_signal(self) -> None:
        result = _evaluator(title_similarity_threshold=0.85).evaluate(
            name="Nike Air Max 90",
            brand=None,
            category=None,
            price=None,
            attributes=ProductAttributes(),
            candidate_metadata={"name": "Wooden Dining Table"},
        )

        assert "title_difference" in _codes(result.reasons)


class TestAttributeOverlap:
    def test_matching_attributes_are_a_positive_signal(self) -> None:
        result = _evaluator().evaluate(
            name="Red Shoe",
            brand=None,
            category=None,
            price=None,
            attributes=ProductAttributes(color="red", material="leather"),
            candidate_metadata={"color": "red", "material": "leather"},
        )

        assert "attribute_overlap" in _codes(result.reasons)

    def test_no_matching_attributes_is_a_negative_signal(self) -> None:
        result = _evaluator().evaluate(
            name="Red Shoe",
            brand=None,
            category=None,
            price=None,
            attributes=ProductAttributes(color="red"),
            candidate_metadata={"color": "blue"},
        )

        assert "attribute_mismatch" in _codes(result.reasons)


class TestScore:
    def test_all_signals_satisfied_scores_one(self) -> None:
        result = _evaluator().evaluate(
            name="Nike Air Max 90",
            brand="Nike",
            category="Shoes",
            price=105.0,
            attributes=ProductAttributes(color="red"),
            candidate_metadata={
                "name": "Nike Air Max 90",
                "brand": "Nike",
                "category": "Shoes",
                "price": 100.0,
                "color": "red",
            },
        )

        assert result.score == 1.0
        assert result.veto is False

    def test_no_applicable_rules_scores_zero(self) -> None:
        result = _evaluator().evaluate(
            name="Widget",
            brand=None,
            category=None,
            price=None,
            attributes=ProductAttributes(),
            candidate_metadata={},
        )

        assert result.score == 0.0
        assert result.reasons == []

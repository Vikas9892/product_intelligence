"""Unit tests for the Phase 17 pricing domain models."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.constants import PricingStrategy
from app.models.comparable_product import ComparableProduct
from app.models.price_confidence import PriceConfidence
from app.models.price_estimate import PriceEstimate


class TestComparableProduct:
    def test_constructs(self) -> None:
        comparable = ComparableProduct(product_id=uuid4(), price=99.0, similarity=0.9, brand="Nike")
        assert comparable.price == 99.0
        assert comparable.brand == "Nike"

    def test_rejects_a_non_positive_price(self) -> None:
        with pytest.raises(ValidationError):
            ComparableProduct(product_id=uuid4(), price=0.0, similarity=0.9)


class TestPriceEstimate:
    def test_constructs_with_comparables(self) -> None:
        estimate = PriceEstimate(
            estimated_price=100.0,
            confidence=PriceConfidence.HIGH,
            confidence_score=0.9,
            strategy=PricingStrategy.TRIMMED_MEAN,
            comparable_count=5,
            comparables=[ComparableProduct(product_id=uuid4(), price=100.0, similarity=0.9)],
            reason="Based on 5 comparable products.",
        )
        assert estimate.estimated_price == 100.0
        assert estimate.confidence is PriceConfidence.HIGH

    def test_defaults_to_no_comparables(self) -> None:
        estimate = PriceEstimate(
            estimated_price=0.0,
            confidence=PriceConfidence.LOW,
            confidence_score=0.0,
            strategy=PricingStrategy.MEDIAN,
            comparable_count=0,
            reason="No comparable products found.",
        )
        assert estimate.comparables == []

    def test_rejects_a_confidence_score_above_one(self) -> None:
        with pytest.raises(ValidationError):
            PriceEstimate(
                estimated_price=1.0,
                confidence=PriceConfidence.HIGH,
                confidence_score=1.5,
                strategy=PricingStrategy.MEDIAN,
                comparable_count=1,
                reason="x",
            )

    def test_round_trips_through_model_dump_and_validate(self) -> None:
        estimate = PriceEstimate(
            estimated_price=100.0,
            confidence=PriceConfidence.MEDIUM,
            confidence_score=0.6,
            strategy=PricingStrategy.WEIGHTED_AVERAGE,
            comparable_count=1,
            comparables=[ComparableProduct(product_id=uuid4(), price=100.0, similarity=0.9)],
            reason="x",
        )
        restored = PriceEstimate.model_validate(estimate.model_dump(mode="json"))
        assert restored == estimate

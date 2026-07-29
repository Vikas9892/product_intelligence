"""Unit tests for the Phase 17 pricing schemas."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.constants import PricingStrategy
from app.models.comparable_product import ComparableProduct
from app.models.price_confidence import PriceConfidence
from app.models.price_estimate import PriceEstimate
from app.schemas.pricing import PricingRequest, PricingResponse


class TestPricingRequest:
    def test_requires_a_name(self) -> None:
        with pytest.raises(ValidationError):
            PricingRequest(name="")

    def test_constructs_with_optional_fields(self) -> None:
        request = PricingRequest(name="Widget", brand="Nike", top_k=5)
        assert request.top_k == 5


class TestPricingResponse:
    def test_maps_an_estimate(self) -> None:
        product_id = uuid4()
        estimate = PriceEstimate(
            estimated_price=100.0,
            confidence=PriceConfidence.HIGH,
            confidence_score=0.9,
            strategy=PricingStrategy.TRIMMED_MEAN,
            comparable_count=1,
            comparables=[
                ComparableProduct(product_id=product_id, price=100.0, similarity=0.9, brand="Nike")
            ],
            reason="Based on 1 comparable product.",
        )

        response = PricingResponse.from_estimate(estimate)

        assert response.estimated_price == 100.0
        assert response.confidence == "high"
        assert response.strategy == "trimmed_mean"
        assert response.pricing_reason == "Based on 1 comparable product."
        assert response.comparables[0].product_id == product_id
        assert response.comparables[0].brand == "Nike"

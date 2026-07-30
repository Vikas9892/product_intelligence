"""Integration tests for the Phase 17 pricing endpoints.

Builds the *real* `create_app()` app, overriding `get_pricing_service`
with a fake — the engine's own logic is covered by its unit tests; this
suite proves the routes delegate and shape the response, and that the
router is gated on PRICING__ENABLED.
"""

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.application import create_app
from app.core.config import settings
from app.core.constants import PricingStrategy
from app.dependencies.pricing import get_pricing_service
from app.exceptions.errors import ResourceNotFoundException
from app.models.comparable_product import ComparableProduct
from app.models.price_confidence import PriceConfidence
from app.models.price_estimate import PriceEstimate
from app.services.pricing.base_pricing_service import BasePricingService

_PREFIX = settings.application.api_prefix
_ESTIMATE_URL = f"{_PREFIX}/pricing/estimate"
_MISSING_ID = uuid4()


class _FakePricingService(BasePricingService):
    def __init__(self) -> None:
        self.received: dict[str, object] = {}

    def _estimate(self) -> PriceEstimate:
        return PriceEstimate(
            estimated_price=99.99,
            confidence=PriceConfidence.HIGH,
            confidence_score=0.9,
            strategy=PricingStrategy.TRIMMED_MEAN,
            comparable_count=1,
            comparables=[
                ComparableProduct(product_id=uuid4(), price=99.99, similarity=0.95, brand="Nike")
            ],
            reason="Estimated from 1 comparable product using the trimmed_mean strategy.",
        )

    async def estimate_for_request(
        self,
        *,
        name: str,
        brand: str | None,
        category: str | None,
        description: str | None,
        top_k: int | None = None,
    ) -> PriceEstimate:
        self.received = {"name": name, "brand": brand, "top_k": top_k}
        return self._estimate()

    async def estimate_for_product(self, product_id: UUID) -> PriceEstimate:
        if product_id == _MISSING_ID:
            raise ResourceNotFoundException("not indexed", resource="product")
        return self._estimate()


@pytest.fixture
def pricing_client() -> Iterator[TestClient]:
    app: FastAPI = create_app()
    app.dependency_overrides[get_pricing_service] = _FakePricingService
    with TestClient(app) as client:
        yield client


class TestEstimate:
    def test_returns_a_price_estimate(self, pricing_client: TestClient) -> None:
        response = pricing_client.post(
            _ESTIMATE_URL, json={"name": "Nike Air Max", "brand": "Nike", "top_k": 5}
        )

        assert response.status_code == 200
        body = response.json()
        assert body["estimated_price"] == 99.99
        assert body["confidence"] == "high"
        assert body["strategy"] == "trimmed_mean"
        assert body["pricing_reason"].startswith("Estimated from 1 comparable")
        assert body["comparables"][0]["brand"] == "Nike"

    def test_requires_a_name(self, pricing_client: TestClient) -> None:
        response = pricing_client.post(_ESTIMATE_URL, json={"brand": "Nike"})

        assert response.status_code == 422

    def test_never_returns_a_raw_vector(self, pricing_client: TestClient) -> None:
        response = pricing_client.post(_ESTIMATE_URL, json={"name": "Widget"})

        assert "vector" not in response.text


class TestPriceIndexedProduct:
    def test_prices_an_indexed_product(self, pricing_client: TestClient) -> None:
        response = pricing_client.get(f"{_PREFIX}/pricing/{uuid4()}")

        assert response.status_code == 200
        assert response.json()["estimated_price"] == 99.99

    def test_404_for_an_unindexed_product(self, pricing_client: TestClient) -> None:
        response = pricing_client.get(f"{_PREFIX}/pricing/{_MISSING_ID}")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "resource_not_found"


class TestPricingDisabled:
    def test_router_absent_when_pricing_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings.pricing, "enabled", False)
        app = create_app()

        with TestClient(app) as client:
            assert client.post(f"{_PREFIX}/pricing/estimate", json={"name": "x"}).status_code == 404

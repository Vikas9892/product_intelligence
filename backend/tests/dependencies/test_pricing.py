"""Unit tests for the `get_pricing_service` dependency provider."""

from app.dependencies.pricing import get_pricing_service
from app.services.pricing.pricing_engine import PricingEngine


class TestGetPricingService:
    def test_returns_a_pricing_engine_instance(self) -> None:
        get_pricing_service.cache_clear()

        service = get_pricing_service()

        assert isinstance(service, PricingEngine)

    def test_returns_a_cached_singleton(self) -> None:
        get_pricing_service.cache_clear()

        first = get_pricing_service()
        second = get_pricing_service()

        assert first is second

"""Unit tests for the `get_product_service` dependency provider."""

from app.dependencies.product import get_product_service
from app.services.product_service import ProductService


class TestGetProductService:
    def test_returns_a_product_service_instance(self) -> None:
        get_product_service.cache_clear()

        service = get_product_service()

        assert isinstance(service, ProductService)

    def test_returns_a_cached_singleton(self) -> None:
        get_product_service.cache_clear()

        first = get_product_service()
        second = get_product_service()

        assert first is second

    def test_cache_clear_forces_a_fresh_instance(self) -> None:
        get_product_service.cache_clear()
        first = get_product_service()

        get_product_service.cache_clear()
        second = get_product_service()

        assert first is not second

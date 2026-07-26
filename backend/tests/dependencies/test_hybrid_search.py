"""Unit tests for the `get_hybrid_search_service` dependency provider."""

from app.dependencies.hybrid_search import get_hybrid_search_service
from app.services.vectorstore.hybrid_search_service import HybridSearchService


class TestGetHybridSearchService:
    def test_returns_a_hybrid_search_service_instance(self) -> None:
        get_hybrid_search_service.cache_clear()

        service = get_hybrid_search_service()

        assert isinstance(service, HybridSearchService)

    def test_returns_a_cached_singleton(self) -> None:
        get_hybrid_search_service.cache_clear()

        first = get_hybrid_search_service()
        second = get_hybrid_search_service()

        assert first is second

    def test_cache_clear_forces_a_fresh_instance(self) -> None:
        get_hybrid_search_service.cache_clear()
        first = get_hybrid_search_service()

        get_hybrid_search_service.cache_clear()
        second = get_hybrid_search_service()

        assert first is not second

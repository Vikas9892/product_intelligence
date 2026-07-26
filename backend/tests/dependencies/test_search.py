"""Unit tests for the `get_search_service` dependency provider."""

from app.dependencies.search import get_search_service
from app.services.vectorstore.search_service import SearchService


class TestGetSearchService:
    def test_returns_a_search_service_instance(self) -> None:
        get_search_service.cache_clear()

        service = get_search_service()

        assert isinstance(service, SearchService)

    def test_returns_a_cached_singleton(self) -> None:
        get_search_service.cache_clear()

        first = get_search_service()
        second = get_search_service()

        assert first is second

    def test_cache_clear_forces_a_fresh_instance(self) -> None:
        get_search_service.cache_clear()
        first = get_search_service()

        get_search_service.cache_clear()
        second = get_search_service()

        assert first is not second

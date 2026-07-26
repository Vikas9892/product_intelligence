"""Unit tests for the `get_duplicate_check_service` dependency provider."""

from app.dependencies.duplicate import get_duplicate_check_service
from app.services.duplicate.duplicate_check_service import DuplicateCheckService


class TestGetDuplicateCheckService:
    def test_returns_a_duplicate_check_service_instance(self) -> None:
        get_duplicate_check_service.cache_clear()

        service = get_duplicate_check_service()

        assert isinstance(service, DuplicateCheckService)

    def test_returns_a_cached_singleton(self) -> None:
        get_duplicate_check_service.cache_clear()

        first = get_duplicate_check_service()
        second = get_duplicate_check_service()

        assert first is second

    def test_cache_clear_forces_a_fresh_instance(self) -> None:
        get_duplicate_check_service.cache_clear()
        first = get_duplicate_check_service()

        get_duplicate_check_service.cache_clear()
        second = get_duplicate_check_service()

        assert first is not second

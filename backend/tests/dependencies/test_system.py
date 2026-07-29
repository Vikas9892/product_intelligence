"""Unit tests for the `get_system_health_service` dependency provider."""

from app.dependencies.system import get_system_health_service
from app.services.system_health_service import SystemHealthService


class TestGetSystemHealthService:
    def test_returns_a_system_health_service_instance(self) -> None:
        get_system_health_service.cache_clear()

        service = get_system_health_service()

        assert isinstance(service, SystemHealthService)

    def test_returns_a_cached_singleton(self) -> None:
        get_system_health_service.cache_clear()

        first = get_system_health_service()
        second = get_system_health_service()

        assert first is second

    def test_cache_clear_forces_a_fresh_instance(self) -> None:
        get_system_health_service.cache_clear()
        first = get_system_health_service()

        get_system_health_service.cache_clear()
        second = get_system_health_service()

        assert first is not second

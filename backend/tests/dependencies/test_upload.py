"""Unit tests for the `get_upload_service` dependency provider."""

from app.dependencies.upload import get_upload_service
from app.services.upload_service import UploadService


class TestGetUploadService:
    def test_returns_an_upload_service_instance(self) -> None:
        get_upload_service.cache_clear()

        service = get_upload_service()

        assert isinstance(service, UploadService)

    def test_returns_a_cached_singleton(self) -> None:
        get_upload_service.cache_clear()

        first = get_upload_service()
        second = get_upload_service()

        assert first is second

    def test_cache_clear_forces_a_fresh_instance(self) -> None:
        get_upload_service.cache_clear()
        first = get_upload_service()

        get_upload_service.cache_clear()
        second = get_upload_service()

        assert first is not second

"""Unit tests for the `get_explanation_service` dependency provider."""

from app.dependencies.explanations import get_explanation_service
from app.services.explanations.explanation_service import ExplanationService


class TestGetExplanationService:
    def test_returns_an_explanation_service_instance(self) -> None:
        get_explanation_service.cache_clear()

        service = get_explanation_service()

        assert isinstance(service, ExplanationService)

    def test_returns_a_cached_singleton(self) -> None:
        get_explanation_service.cache_clear()

        first = get_explanation_service()
        second = get_explanation_service()

        assert first is second

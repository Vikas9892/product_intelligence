"""Unit tests for the `get_recommendation_engine_service` dependency provider."""

from app.dependencies.recommendation import get_recommendation_engine_service
from app.services.recommendation.recommendation_engine_service import RecommendationEngineService


class TestGetRecommendationEngineService:
    def test_returns_a_recommendation_engine_service_instance(self) -> None:
        get_recommendation_engine_service.cache_clear()

        service = get_recommendation_engine_service()

        assert isinstance(service, RecommendationEngineService)

    def test_returns_a_cached_singleton(self) -> None:
        get_recommendation_engine_service.cache_clear()

        first = get_recommendation_engine_service()
        second = get_recommendation_engine_service()

        assert first is second

    def test_cache_clear_forces_a_fresh_instance(self) -> None:
        get_recommendation_engine_service.cache_clear()
        first = get_recommendation_engine_service()

        get_recommendation_engine_service.cache_clear()
        second = get_recommendation_engine_service()

        assert first is not second

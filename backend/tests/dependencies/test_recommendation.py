"""Unit tests for the recommendation dependency providers."""

from app.dependencies.recommendation import (
    get_recommendation_cache_repository,
    get_recommendation_engine_service,
)
from app.repositories.recommendation_cache_repository import RecommendationCacheRepository
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


class TestGetRecommendationCacheRepository:
    def test_returns_a_recommendation_cache_repository_instance(self) -> None:
        get_recommendation_cache_repository.cache_clear()

        repository = get_recommendation_cache_repository()

        assert isinstance(repository, RecommendationCacheRepository)

    def test_returns_a_cached_singleton(self) -> None:
        get_recommendation_cache_repository.cache_clear()

        first = get_recommendation_cache_repository()
        second = get_recommendation_cache_repository()

        assert first is second

    def test_cache_clear_forces_a_fresh_instance(self) -> None:
        get_recommendation_cache_repository.cache_clear()
        first = get_recommendation_cache_repository()

        get_recommendation_cache_repository.cache_clear()
        second = get_recommendation_cache_repository()

        assert first is not second

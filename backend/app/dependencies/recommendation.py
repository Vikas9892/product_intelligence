"""FastAPI dependency providers for recommendations (`RecommendationEngineService`) and
the recommendation cache (`RecommendationCacheRepository`, Phase 12).

Mirrors `app.dependencies.hybrid_search.get_hybrid_search_service`'s
cached-singleton pattern. `RecommendationScorer` (which
`RecommendationEngineService` composes internally) gets no provider of
its own — nothing calls it directly from a route, the same reasoning
`get_hybrid_search_service`'s own docstring already established for
`TextSearchService`. `RecommendationCacheRepository` gets one because
`app/api/products.py`'s `get_recommendations` route reads from it
directly (checking for a worker-precomputed entry before falling back
to `RecommendationEngineService.recommend`) — `ProductWorker`, the
other caller, isn't part of the FastAPI DI graph at all (it runs outside
any request), so it constructs its own instance directly instead.
"""

from functools import lru_cache

from app.repositories.recommendation_cache_repository import RecommendationCacheRepository
from app.services.recommendation.recommendation_engine_service import RecommendationEngineService


@lru_cache(maxsize=1)
def get_recommendation_engine_service() -> RecommendationEngineService:
    """Return the process-wide RecommendationEngineService singleton, building it on first call."""
    return RecommendationEngineService()


@lru_cache(maxsize=1)
def get_recommendation_cache_repository() -> RecommendationCacheRepository:
    """Return the process-wide RecommendationCacheRepository singleton, building it on first call."""
    return RecommendationCacheRepository()

"""FastAPI dependency provider for `RecommendationEngineService`.

Mirrors `app.dependencies.hybrid_search.get_hybrid_search_service`'s
cached-singleton pattern. `RecommendationScorer` (which
`RecommendationEngineService` composes internally) gets no provider of
its own — nothing calls it directly from a route, the same reasoning
`get_hybrid_search_service`'s own docstring already established for
`TextSearchService`.
"""

from functools import lru_cache

from app.services.recommendation.recommendation_engine_service import RecommendationEngineService


@lru_cache(maxsize=1)
def get_recommendation_engine_service() -> RecommendationEngineService:
    """Return the process-wide RecommendationEngineService singleton, building it on first call."""
    return RecommendationEngineService()

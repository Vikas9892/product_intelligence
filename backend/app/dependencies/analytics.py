"""FastAPI dependency providers for the analytics layer.

Mirrors the cached-singleton pattern every other provider uses.
`get_analytics_repository` is depended on directly by the instrumented
business endpoints (to record events) and by `AnalyticsEngine`;
`get_analytics_engine` is depended on by the `/analytics` read endpoints.
"""

from functools import lru_cache

from app.repositories.analytics_repository import AnalyticsRepository
from app.services.analytics.analytics_engine import AnalyticsEngine


@lru_cache(maxsize=1)
def get_analytics_repository() -> AnalyticsRepository:
    """Return the process-wide AnalyticsRepository singleton, building it on first call."""
    return AnalyticsRepository()


@lru_cache(maxsize=1)
def get_analytics_engine() -> AnalyticsEngine:
    """Return the process-wide AnalyticsEngine singleton, building it on first call."""
    return AnalyticsEngine(repository=get_analytics_repository())

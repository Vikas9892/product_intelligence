"""FastAPI dependency provider for `HybridSearchService`.

Mirrors `app.dependencies.search.get_search_service`'s cached-singleton
pattern. `TextSearchService` (which `HybridSearchService` composes
internally) gets no provider of its own, for the same reason
`ProductService`'s composed services don't — nothing calls it directly
from a route.
"""

from functools import lru_cache

from app.services.vectorstore.hybrid_search_service import HybridSearchService


@lru_cache(maxsize=1)
def get_hybrid_search_service() -> HybridSearchService:
    """Return the process-wide HybridSearchService singleton, building it on first call."""
    return HybridSearchService()

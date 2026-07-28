"""FastAPI dependency provider for `QueueManager`.

Mirrors `app.dependencies.hybrid_search.get_hybrid_search_service`'s
cached-singleton pattern. `RedisQueue` (which `QueueManager` composes
internally) gets no provider of its own — nothing calls it directly from
a route, the same reasoning `get_hybrid_search_service`'s own docstring
already established for `TextSearchService`.
"""

from functools import lru_cache

from app.queue.queue_manager import QueueManager


@lru_cache(maxsize=1)
def get_queue_manager() -> QueueManager:
    """Return the process-wide QueueManager singleton, building it on first call."""
    return QueueManager()

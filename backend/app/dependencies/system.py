"""FastAPI dependency provider for `SystemHealthService`.

Mirrors `app.dependencies.model_registry.get_model_registry`'s
cached-singleton pattern — one process-wide instance, built on first use.
"""

from functools import lru_cache

from app.services.system_health_service import SystemHealthService


@lru_cache(maxsize=1)
def get_system_health_service() -> SystemHealthService:
    """Return the process-wide SystemHealthService singleton, building it on first call."""
    return SystemHealthService()

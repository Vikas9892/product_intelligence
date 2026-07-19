"""Composition root for application settings.

`settings.py` defines the schema; this module is the only place that
actually instantiates it, caching a single instance so environment
variables and `.env` are read exactly once per process. Import `settings`
from here anywhere else in the codebase — never call `Settings()` directly
outside this file or a test.

    from app.core.config import settings

    settings.application.port
    settings.database.url

`get_settings` is exposed separately (not just the `settings` singleton)
so it can be used as a FastAPI dependency later (`Depends(get_settings)`)
and so tests can force a fresh read via `get_settings.cache_clear()`.
"""

from functools import lru_cache

from app.core.settings import Settings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide Settings singleton, building it on first call."""
    return Settings()


settings: Settings = get_settings()

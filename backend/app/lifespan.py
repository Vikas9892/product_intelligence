"""Application startup and shutdown behavior.

Wires FastAPI's lifespan API (an async context manager passed to
`FastAPI(lifespan=...)`) to the app: code before `yield` runs once at
process startup, code after `yield` runs once at shutdown. Kept in its own
module — rather than inline in `application.py` — so startup/shutdown
concerns can grow (opening/closing a database pool, a vector store client,
etc. in later milestones) without `create_app()` itself changing.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core import paths
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Run startup logic before yielding control, shutdown logic after.

    No database or AI-provider connections exist yet (later milestones), so
    startup currently only ensures the runtime directories (`storage/`,
    `storage/uploads/`, `logs/`) exist and logs that the app is up; shutdown
    just logs that the process is stopping.
    """
    logger.info(
        "Starting %s v%s (environment=%s)",
        settings.application.name,
        settings.application.version,
        settings.application.environment,
    )
    paths.ensure_runtime_directories()
    logger.info("%s startup complete.", settings.application.name)

    yield

    logger.info("Shutting down %s.", settings.application.name)

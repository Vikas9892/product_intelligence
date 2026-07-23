"""FastAPI application factory.

`create_app()` is the only place `FastAPI(...)` is instantiated — nothing
else in the codebase should construct it directly. A factory (instead of a
module-level `app = FastAPI()`) means every test gets its own fresh
instance instead of importing and mutating one process-wide global, and it
gives later milestones (middleware, exception handlers) one obvious place
to add configuration without touching `app/main.py`.
"""

from fastapi import FastAPI

from app.core import constants
from app.core.config import settings
from app.lifespan import lifespan


def create_app() -> FastAPI:
    """Build and return a fully configured FastAPI application instance."""
    app = FastAPI(
        title=settings.application.name,
        description=constants.DEFAULT_APP_DESCRIPTION,
        version=settings.application.version,
        lifespan=lifespan,
    )

    _register_routers(app)

    return app


def _register_routers(app: FastAPI) -> None:
    """Attach API routers to `app`.

    Deliberately empty — no business routes exist yet. Keeping router
    registration in its own function, rather than inline in `create_app()`,
    means later milestones add `app.include_router(...)` calls here without
    touching application construction/metadata above.
    """

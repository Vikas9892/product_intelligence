"""Health, readiness, and version endpoints.

Deliberately unversioned — mounted at `/health`, `/ready`, `/version`
directly, *not* under `settings.application.api_prefix` (`/api/v1`).
Infrastructure that calls these (Kubernetes kubelet, load balancer health
checks, uptime monitors) is configured with a fixed path and should never
need to change when the business API's version changes; versioned business
routers land under the prefix starting in a later milestone.

Registered via `app.application._register_routers`, not imported directly
by `app.main` — see that module for the registration seam.
"""

from fastapi import APIRouter

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.health import HealthResponse, ReadinessResponse, VersionResponse

logger = get_logger(__name__)

router = APIRouter(tags=["system"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness probe",
    description="Returns 200 if the process is alive. Never checks dependencies — "
    "see /ready for that.",
)
async def health() -> HealthResponse:
    """Liveness probe: used by Kubernetes to decide whether to restart the pod.

    A liveness probe answers one question only — "is this process still
    running and able to respond at all?" — so it must never depend on
    anything that could be transiently unavailable (a database, a
    downstream API). If it did, a temporary database blip would make
    Kubernetes kill and restart a perfectly healthy process, which doesn't
    fix the database and just adds churn.
    """
    logger.debug("Liveness check requested.")
    return HealthResponse()


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Readiness probe",
    description="Returns 200 if this instance can currently serve traffic.",
)
async def ready() -> ReadinessResponse:
    """Readiness probe: used by Kubernetes/load balancers to decide routing.

    A readiness probe answers "can *this* instance handle a request right
    now?" — distinct from liveness because a process can be alive (don't
    restart it) but not ready (don't send it traffic), e.g. while it's
    still warming up or a dependency it needs is temporarily down. No
    dependencies exist yet in this milestone, so this trivially always
    reports ready; `checks` will gain real entries (database connectivity,
    vector store connectivity, ...) as those dependencies are introduced.
    """
    logger.debug("Readiness check requested.")
    return ReadinessResponse()


@router.get(
    "/version",
    response_model=VersionResponse,
    summary="Build and version metadata",
    description="Returns the running application's name, version, and environment.",
)
async def version() -> VersionResponse:
    """Report what's actually deployed.

    Useful for confirming a deploy actually rolled out (compare the
    returned `version` against what was just shipped), for support/bug
    reports ("what version were you running"), and for monitoring
    dashboards that tag metrics by version.
    """
    logger.debug("Version metadata requested.")
    return VersionResponse(
        name=settings.application.name,
        version=settings.application.version,
        environment=settings.application.environment,
    )

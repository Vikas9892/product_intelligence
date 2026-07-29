"""System dashboard endpoints (Phase 14).

`GET /system/health` and `GET /system/stats` (mounted under
`settings.application.api_prefix`, so `/api/v1/system/health` and
`/api/v1/system/stats`) report operational health and aggregate
statistics — Redis/Qdrant reachability, queue depth, active-model count,
worker concurrency, and uptime. Distinct from the unversioned `/health`/
`/ready` liveness/readiness probes (`app/api/health.py`): those answer
"is this process alive / able to serve," while these expose a richer
operational dashboard of the whole platform's dependencies.

Thin adapters, same as every other route in this codebase: delegate to
`SystemHealthService`, shape the response. Both routes always return
`200` — a degraded dependency is reported in the *body*
(`"redis": "unhealthy"`), not as an HTTP error, so a monitoring scrape of
this endpoint itself never fails just because a dependency is down.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.core.logging import get_logger
from app.dependencies.system import get_system_health_service
from app.schemas.system import SystemHealthResponse, SystemStatsResponse
from app.services.system_health_service import SystemHealthService

logger = get_logger(__name__)

router = APIRouter(prefix="/system", tags=["system"])


@router.get(
    "/health",
    response_model=SystemHealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Operational health dashboard",
    description="Reports Redis/Qdrant reachability, queue depth, active-model count, "
    "configured worker concurrency, and process uptime.",
)
async def system_health(
    service: Annotated[SystemHealthService, Depends(get_system_health_service)],
) -> SystemHealthResponse:
    """Return a point-in-time operational health snapshot."""
    health = await service.health()
    logger.info(
        "System health requested: redis=%s, qdrant=%s, queue_depth=%d",
        health.redis,
        health.qdrant,
        health.queue_depth,
    )
    return SystemHealthResponse.from_health(health)


@router.get(
    "/stats",
    response_model=SystemStatsResponse,
    status_code=status.HTTP_200_OK,
    summary="Aggregate platform statistics",
    description="Reports uptime, worker concurrency, queue depth, in-flight and "
    "dead-lettered job counts, and active/registered model counts.",
)
async def system_stats(
    service: Annotated[SystemHealthService, Depends(get_system_health_service)],
) -> SystemStatsResponse:
    """Return aggregate platform statistics."""
    stats = await service.stats()
    logger.info(
        "System stats requested: queue_depth=%d, jobs_in_flight=%d, dead_letter_size=%d",
        stats.queue_depth,
        stats.jobs_in_flight,
        stats.dead_letter_size,
    )
    return SystemStatsResponse.from_stats(stats)

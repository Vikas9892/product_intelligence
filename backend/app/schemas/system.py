"""Response schemas for the system dashboard endpoints (`app/api/system.py`, Phase 14).

Kept separate from `SystemHealth`/`SystemStats` (the internal dataclasses
`SystemHealthService` builds) for the same reason every other API schema
in this codebase is kept separate from its domain model — the wire
contract is independent of the service's own internal shape.
"""

from pydantic import BaseModel

from app.services.system_health_service import SystemHealth, SystemStats


def _format_uptime(seconds: float) -> str:
    """Render an uptime in whole seconds as `H:MM:SS` (matching the spec's `"uptime": "..."`)."""
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}"


class SystemHealthResponse(BaseModel):
    """Response body for `GET /system/health`.

    `redis`/`qdrant` are `"healthy"`/`"unhealthy"` strings (not booleans)
    to match the phase spec's own example payload. `workers` is the
    configured worker concurrency, not a live process count — see
    `SystemHealthService`'s docstring.
    """

    redis: str
    qdrant: str
    workers: int
    queue_depth: int
    active_models: int
    uptime: str

    @classmethod
    def from_health(cls, health: SystemHealth) -> "SystemHealthResponse":
        """Build the wire response from a `SystemHealth` snapshot."""
        return cls(
            redis=health.redis,
            qdrant=health.qdrant,
            workers=health.workers,
            queue_depth=health.queue_depth,
            active_models=health.active_models,
            uptime=_format_uptime(health.uptime_seconds),
        )


class SystemStatsResponse(BaseModel):
    """Response body for `GET /system/stats` — aggregate platform statistics."""

    uptime: str
    uptime_seconds: float
    worker_concurrency: int
    queue_depth: int
    jobs_in_flight: int
    dead_letter_size: int
    active_models: int
    registered_models: int

    @classmethod
    def from_stats(cls, stats: SystemStats) -> "SystemStatsResponse":
        """Build the wire response from a `SystemStats` snapshot."""
        return cls(
            uptime=_format_uptime(stats.uptime_seconds),
            uptime_seconds=stats.uptime_seconds,
            worker_concurrency=stats.worker_concurrency,
            queue_depth=stats.queue_depth,
            jobs_in_flight=stats.jobs_in_flight,
            dead_letter_size=stats.dead_letter_size,
            active_models=stats.active_models,
            registered_models=stats.registered_models,
        )

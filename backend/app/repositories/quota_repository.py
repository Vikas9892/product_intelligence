"""`QuotaRepository`: Redis-backed per-tenant request quotas and rate limits (Phase 19).

Two fixed-window counters per tenant: a per-day counter (for the daily
request quota) and a per-minute counter (for the rate limit). `hit`
increments both for the current day/minute (setting TTLs so the windows
self-expire) and returns the post-increment counts; the caller compares
them against the configured limits. `usage` reads the current day's count
without incrementing, for the `/usage` endpoint. No database — Redis-only.
"""

from datetime import UTC, datetime
from uuid import UUID

import redis.asyncio as redis

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

#: TTLs comfortably longer than each window, so a counter always outlives
#: its window but is cleaned up soon after.
_DAILY_TTL_SECONDS = 2 * 24 * 60 * 60
_MINUTE_TTL_SECONDS = 120


class QuotaRepository:
    """Increments and reads per-tenant daily/per-minute request counters."""

    def __init__(self, *, redis_client: redis.Redis | None = None) -> None:
        self._redis: redis.Redis = (
            redis_client
            if redis_client is not None
            else redis.from_url(settings.async_pipeline.redis_url, decode_responses=True)
        )

    async def hit(self, tenant_id: UUID) -> tuple[int, int]:
        """Record one request for `tenant_id`, returning `(daily_count, minute_count)`."""
        now = datetime.now(UTC)
        daily_key = _daily_key(tenant_id, now)
        minute_key = _minute_key(tenant_id, now)
        daily = await self._redis.incr(daily_key)
        await self._redis.expire(daily_key, _DAILY_TTL_SECONDS)
        minute = await self._redis.incr(minute_key)
        await self._redis.expire(minute_key, _MINUTE_TTL_SECONDS)
        return int(daily), int(minute)

    async def usage(self, tenant_id: UUID) -> int:
        """Return `tenant_id`'s request count so far today (without incrementing)."""
        raw = await self._redis.get(_daily_key(tenant_id, datetime.now(UTC)))
        return int(raw) if raw is not None else 0


def _daily_key(tenant_id: UUID, now: datetime) -> str:
    return f"quota:daily:{tenant_id}:{now.date().isoformat()}"


def _minute_key(tenant_id: UUID, now: datetime) -> str:
    return f"quota:minute:{tenant_id}:{now.strftime('%Y-%m-%dT%H:%M')}"

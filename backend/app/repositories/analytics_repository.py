"""`AnalyticsRepository`: Redis-backed daily analytics buckets (Phase 18).

Stores operational history in per-day Redis counters — no database,
matching this project's Redis-only persistence decision (Phase 12).
Each business event increments a per-day key (`analytics:count:{event}:
{YYYY-MM-DD}`), and product-processing latency accumulates into per-day
sum/count keys, so an average is recoverable per day. Every key is given
a `RETENTION_DAYS` TTL, so history self-prunes without a sweeper.

**Recording is fail-soft.** A `record_*` call that can't reach Redis logs
and returns rather than raising — analytics must never break the request
that triggered the event it's counting (an upload should succeed even if
the analytics write fails). Queries, by contrast, are only issued by the
analytics endpoints themselves, so they surface failures normally. The
sync-timeout-bounded client (short connect timeout) keeps a fail-soft
write from blocking a request for long when Redis is down.
"""

from datetime import UTC, date, datetime

import redis.asyncio as redis

from app.core.config import settings
from app.core.logging import get_logger
from app.models.analytics_event import AnalyticsEvent

logger = get_logger(__name__)

#: How long each daily bucket lives before Redis expires it.
RETENTION_DAYS = 90
_TTL_SECONDS = RETENTION_DAYS * 24 * 60 * 60


class AnalyticsRepository:
    """Records and queries per-day operational counters in Redis."""

    def __init__(self, *, redis_client: redis.Redis | None = None) -> None:
        self._redis: redis.Redis = (
            redis_client
            if redis_client is not None
            else redis.from_url(
                settings.async_pipeline.redis_url,
                decode_responses=True,
                socket_connect_timeout=0.25,
                socket_timeout=0.25,
            )
        )

    async def record_event(self, event: AnalyticsEvent, *, day: date | None = None) -> None:
        """Increment `event`'s counter for `day` (default today) — fail-soft."""
        key = _count_key(event, day or _today())
        try:
            await self._redis.incr(key)
            await self._redis.expire(key, _TTL_SECONDS)
        except Exception:
            logger.warning("Analytics record_event failed (non-fatal): event=%s", event.value)

    async def record_latency(self, seconds: float, *, day: date | None = None) -> None:
        """Accumulate a product-processing `seconds` sample into `day`'s latency buckets — fail-soft."""
        resolved_day = day or _today()
        sum_key = _latency_sum_key(resolved_day)
        count_key = _latency_count_key(resolved_day)
        try:
            await self._redis.incrbyfloat(sum_key, seconds)
            await self._redis.incr(count_key)
            await self._redis.expire(sum_key, _TTL_SECONDS)
            await self._redis.expire(count_key, _TTL_SECONDS)
        except Exception:
            logger.warning("Analytics record_latency failed (non-fatal)")

    async def count_for(self, event: AnalyticsEvent, day: date) -> int:
        """Return `event`'s count on `day` (`0` if none recorded)."""
        raw = await self._redis.get(_count_key(event, day))
        return int(raw) if raw is not None else 0

    async def count_range(self, event: AnalyticsEvent, days: list[date]) -> list[int]:
        """Return `event`'s counts across `days`, in order (`0` for days with none)."""
        if not days:
            return []
        keys = [_count_key(event, day) for day in days]
        raw_values = await self._redis.mget(keys)
        return [int(value) if value is not None else 0 for value in raw_values]

    async def latency_range(self, days: list[date]) -> tuple[float, int]:
        """Return the total latency sum and sample count across `days`."""
        if not days:
            return 0.0, 0
        sums = await self._redis.mget([_latency_sum_key(day) for day in days])
        counts = await self._redis.mget([_latency_count_key(day) for day in days])
        total = sum(float(value) for value in sums if value is not None)
        count = sum(int(value) for value in counts if value is not None)
        return total, count


def _today() -> date:
    return datetime.now(UTC).date()


def _count_key(event: AnalyticsEvent, day: date) -> str:
    return f"analytics:count:{event.value}:{day.isoformat()}"


def _latency_sum_key(day: date) -> str:
    return f"analytics:latency_sum:{day.isoformat()}"


def _latency_count_key(day: date) -> str:
    return f"analytics:latency_count:{day.isoformat()}"

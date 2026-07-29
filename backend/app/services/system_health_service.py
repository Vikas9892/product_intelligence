"""`SystemHealthService`: aggregates operational health/stats for the dashboard endpoints (Phase 14).

Powers `GET /system/health` and `GET /system/stats` (`app/api/system.py`).
Deliberately read-only and side-effect-free: it pings Redis, asks the
vector store whether it's reachable, reads current queue lengths, and
counts active models — never mutating anything, never running inference.

**Every dependency check is failure-tolerant.** A health endpoint exists
precisely to report that something is down without itself falling over
when it is, so each check is wrapped to degrade to `"unhealthy"`/`0`
rather than propagating an exception — the same "never raises" contract
`QdrantVectorStore.health()` already documents for itself.

**"workers" is the configured concurrency, not a live process count.**
The API process and the worker pool run as *separate* processes (see
`WorkerManager`/`scripts/run_workers.py`) — the API has no direct handle
on how many worker processes are actually alive right now. Reporting a
true liveness count would require workers to heartbeat into Redis, which
is beyond this phase's scope; `workers` here is the configured
`WORKER_CONCURRENCY` target, documented as such rather than silently
implying more than it knows.
"""

import time
from dataclasses import dataclass

import redis.asyncio as redis

from app.core.config import settings
from app.core.logging import get_logger
from app.models.model_status import ModelStatus
from app.services.model_registry import ModelRegistry
from app.services.vectorstore.base import BaseVectorStore
from app.services.vectorstore.qdrant_store import QdrantVectorStore

logger = get_logger(__name__)

#: Captured once, when this module is first imported — process start for
#: uptime reporting. Monotonic so it's immune to wall-clock adjustments.
_PROCESS_START = time.monotonic()

_HEALTHY = "healthy"
_UNHEALTHY = "unhealthy"


@dataclass(frozen=True)
class SystemHealth:
    """Point-in-time health snapshot backing `GET /system/health`."""

    redis: str
    qdrant: str
    workers: int
    queue_depth: int
    active_models: int
    uptime_seconds: float


@dataclass(frozen=True)
class SystemStats:
    """Aggregate platform statistics backing `GET /system/stats`."""

    uptime_seconds: float
    worker_concurrency: int
    queue_depth: int
    jobs_in_flight: int
    dead_letter_size: int
    active_models: int
    registered_models: int


class SystemHealthService:
    """Aggregates Redis/Qdrant health, queue depth, active-model count, and uptime."""

    def __init__(
        self,
        *,
        redis_client: redis.Redis | None = None,
        vector_store: BaseVectorStore | None = None,
        model_registry: ModelRegistry | None = None,
        worker_concurrency: int | None = None,
        queue_name: str | None = None,
    ) -> None:
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
        self._vector_store = vector_store if vector_store is not None else QdrantVectorStore()
        self._model_registry = model_registry if model_registry is not None else ModelRegistry()
        self._worker_concurrency = (
            worker_concurrency
            if worker_concurrency is not None
            else settings.async_pipeline.worker_concurrency
        )
        self._queue_name = (
            queue_name if queue_name is not None else settings.async_pipeline.queue_name
        )

    async def health(self) -> SystemHealth:
        """Return a point-in-time health snapshot — never raises."""
        return SystemHealth(
            redis=_HEALTHY if await self._redis_healthy() else _UNHEALTHY,
            qdrant=_HEALTHY if await self._vector_store.health() else _UNHEALTHY,
            workers=self._worker_concurrency,
            queue_depth=await self._list_length("pending"),
            active_models=self._active_model_count(),
            uptime_seconds=self._uptime_seconds(),
        )

    async def stats(self) -> SystemStats:
        """Return aggregate platform statistics — never raises."""
        return SystemStats(
            uptime_seconds=self._uptime_seconds(),
            worker_concurrency=self._worker_concurrency,
            queue_depth=await self._list_length("pending"),
            jobs_in_flight=await self._hash_length("processing"),
            dead_letter_size=await self._list_length("dead_letter"),
            active_models=self._active_model_count(),
            registered_models=len(self._model_registry.list_models()),
        )

    async def _redis_healthy(self) -> bool:
        try:
            return bool(await self._redis.ping())
        except Exception:
            logger.warning("Redis health check failed")
            return False

    async def _list_length(self, key_suffix: str) -> int:
        try:
            return int(await self._redis.llen(f"{self._queue_name}:{key_suffix}"))
        except Exception:
            logger.warning("Queue length check failed: key_suffix=%s", key_suffix)
            return 0

    async def _hash_length(self, key_suffix: str) -> int:
        try:
            return int(await self._redis.hlen(f"{self._queue_name}:{key_suffix}"))
        except Exception:
            logger.warning("Queue length check failed: key_suffix=%s", key_suffix)
            return 0

    def _active_model_count(self) -> int:
        return sum(
            1
            for model_info in self._model_registry.list_models()
            if model_info.status is ModelStatus.ACTIVE
        )

    def _uptime_seconds(self) -> float:
        return time.monotonic() - _PROCESS_START

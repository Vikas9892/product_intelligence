"""`RedisQueue`: a Redis-backed `BaseQueue` implementation (Phase 12).

Five Redis keys per queue name (`settings.async_pipeline.queue_name`,
e.g. `"product_processing"` — "configurable queues," the phase spec's
own requirement, since a different `RedisQueue(queue_name=...)` instance
is a fully independent queue):

- `{queue_name}:pending` (LIST) — job IDs waiting to be dequeued (FIFO:
  `RPUSH` to enqueue, `LPOP` to dequeue).
- `{queue_name}:processing` (HASH, job ID -> dequeue timestamp) — jobs a
  worker currently holds; `requeue_stale_jobs` uses this to recover jobs
  a crashed worker never finished.
- `{queue_name}:delayed` (ZSET, job ID -> ready-at timestamp) — jobs
  waiting out an exponential-backoff retry delay; `dequeue()` promotes
  any that are due back onto `pending` before popping, so no separate
  scheduler process is needed (Celery/RQ-style delayed-task workers are
  explicitly out of scope this phase).
- `{queue_name}:dead_letter` (LIST) — job IDs that exhausted
  `max_retries`, kept for inspection (`get_dead_letter_job_ids`) rather
  than discarded — "never lose a job."
- `job:{job_id}` (STRING, JSON) — the actual `Job` record, the source of
  truth `get`/`get_by_product_id` read from; `product:{product_id}:job_id`
  (STRING) is the secondary index the latter uses.

**Thread safety.** This codebase is asyncio-concurrent, not
multi-threaded (see every other service's own "safe to share across
concurrent requests" reasoning) — `redis.asyncio.Redis`'s connection
pool is exactly what makes that safe here: each command is a single
atomic round-trip at the Redis server itself, so concurrent `asyncio`
tasks sharing one `RedisQueue` never interleave a single operation.

**Never logs job payloads or embeddings** — only IDs, statuses, and
counts, matching this phase's own logging requirement.
"""

import time
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

import redis.asyncio as redis

from app.core.config import settings
from app.core.logging import get_logger
from app.jobs.base_job import Job
from app.jobs.job_status import JobStatus
from app.queue.base_queue import BaseQueue

logger = get_logger(__name__)


class RedisQueue(BaseQueue):
    """Redis-backed job queue: pending/processing/delayed/dead-letter, keyed by queue name."""

    def __init__(
        self,
        *,
        redis_client: redis.Redis | None = None,
        queue_name: str | None = None,
        max_retries: int | None = None,
        retry_delay_seconds: float | None = None,
    ) -> None:
        self._redis: redis.Redis = (
            redis_client
            if redis_client is not None
            else redis.from_url(settings.async_pipeline.redis_url, decode_responses=True)
        )
        self._queue_name = (
            queue_name if queue_name is not None else settings.async_pipeline.queue_name
        )
        self._max_retries = (
            max_retries if max_retries is not None else settings.async_pipeline.max_retries
        )
        self._retry_delay_seconds = (
            retry_delay_seconds
            if retry_delay_seconds is not None
            else settings.async_pipeline.retry_delay_seconds
        )

    @property
    def _pending_key(self) -> str:
        return f"{self._queue_name}:pending"

    @property
    def _processing_key(self) -> str:
        return f"{self._queue_name}:processing"

    @property
    def _delayed_key(self) -> str:
        return f"{self._queue_name}:delayed"

    @property
    def _dead_letter_key(self) -> str:
        return f"{self._queue_name}:dead_letter"

    async def enqueue(self, job: Job) -> None:
        await self._save(job)
        await self._redis.rpush(self._pending_key, str(job.job_id))
        logger.info(
            "Job enqueued: job_id=%s, product_id=%s, queue=%s",
            job.job_id,
            job.product_id,
            self._queue_name,
        )

    async def dequeue(self) -> Job | None:
        await self._promote_due_delayed_jobs()
        job_id_raw = await self._redis.lpop(self._pending_key)
        if job_id_raw is None:
            return None

        job = await self.get(UUID(cast(str, job_id_raw)))
        if job is None:
            logger.warning("Dequeued job ID had no record, dropping: job_id=%s", job_id_raw)
            return None

        await self._redis.hset(self._processing_key, str(job.job_id), str(time.time()))
        job.status = JobStatus.RUNNING
        job.updated_at = datetime.now(UTC)
        await self._save(job)
        logger.info("Job dequeued: job_id=%s, product_id=%s", job.job_id, job.product_id)
        return job

    async def ack(self, job: Job) -> None:
        await self._redis.hdel(self._processing_key, str(job.job_id))
        logger.info("Job acknowledged: job_id=%s, product_id=%s", job.job_id, job.product_id)

    async def retry(self, job: Job, *, error: str) -> None:
        await self._redis.hdel(self._processing_key, str(job.job_id))
        job.retry_count += 1
        job.error = error
        job.updated_at = datetime.now(UTC)

        if job.retry_count > job.max_retries:
            job.status = JobStatus.FAILED
            await self._save(job)
            await self._redis.rpush(self._dead_letter_key, str(job.job_id))
            logger.warning(
                "Job exhausted retries, moved to dead-letter queue: job_id=%s, "
                "product_id=%s, retry_count=%d, error=%s",
                job.job_id,
                job.product_id,
                job.retry_count,
                error,
            )
            return

        job.status = JobStatus.RETRYING
        delay_seconds = self._retry_delay_seconds * (2 ** (job.retry_count - 1))
        ready_at = time.time() + delay_seconds
        await self._save(job)
        await self._redis.zadd(self._delayed_key, {str(job.job_id): ready_at})
        logger.warning(
            "Job scheduled for retry: job_id=%s, product_id=%s, attempt=%d/%d, "
            "delay=%.1fs, error=%s",
            job.job_id,
            job.product_id,
            job.retry_count,
            job.max_retries,
            delay_seconds,
            error,
        )

    async def update(self, job: Job) -> None:
        await self._save(job)

    async def get(self, job_id: UUID) -> Job | None:
        raw = await self._redis.get(f"job:{job_id}")
        return Job.model_validate_json(raw) if raw is not None else None

    async def get_by_product_id(self, product_id: UUID) -> Job | None:
        job_id_raw = await self._redis.get(f"product:{product_id}:job_id")
        return await self.get(UUID(cast(str, job_id_raw))) if job_id_raw is not None else None

    async def get_dead_letter_job_ids(self) -> list[UUID]:
        """Return every job ID currently in the dead-letter queue, oldest first."""
        raw_ids = await self._redis.lrange(self._dead_letter_key, 0, -1)
        return [UUID(cast(str, job_id)) for job_id in raw_ids]

    async def requeue_stale_jobs(self, *, older_than_seconds: float) -> int:
        """Recover jobs stuck in `processing` longer than `older_than_seconds`.

        A worker that crashed (or was killed) mid-job never calls `ack`
        or `retry` for it, so it would otherwise sit in `processing`
        forever, invisible to `dequeue()` — this is what recovers it,
        routing it through the normal `retry()` path (so it still
        respects `max_retries`/backoff/dead-lettering) rather than
        silently reprocessing it immediately.
        """
        now = time.time()
        in_flight = await self._redis.hgetall(self._processing_key)
        requeued = 0
        for job_id_raw, dequeued_at_raw in in_flight.items():
            if now - float(cast(str, dequeued_at_raw)) < older_than_seconds:
                continue
            job = await self.get(UUID(cast(str, job_id_raw)))
            if job is None:
                await self._redis.hdel(self._processing_key, job_id_raw)
                continue
            logger.warning(
                "Recovering stale in-flight job (worker crash suspected): job_id=%s, product_id=%s",
                job.job_id,
                job.product_id,
            )
            await self.retry(job, error="Worker did not complete this job in time.")
            requeued += 1
        return requeued

    async def _save(self, job: Job) -> None:
        await self._redis.set(f"job:{job.job_id}", job.model_dump_json())
        await self._redis.set(f"product:{job.product_id}:job_id", str(job.job_id))

    async def _promote_due_delayed_jobs(self) -> None:
        now = time.time()
        due_job_ids = await self._redis.zrangebyscore(self._delayed_key, 0, now)
        for job_id_raw in due_job_ids:
            job_id = cast(str, job_id_raw)
            await self._redis.zrem(self._delayed_key, job_id)
            await self._redis.rpush(self._pending_key, job_id)

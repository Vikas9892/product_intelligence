"""`QueueManager`: the process-wide facade over the job queue (Phase 12).

`app/dependencies/queue.py`'s `get_queue_manager()` is what actually makes
this a singleton (`lru_cache`, mirroring every other `get_*_service`
provider in this codebase) — `QueueManager` itself is a thin, stateless
wrapper delegating to a `BaseQueue` (`RedisQueue` by default), lazily
constructed only when first needed (importing/building the FastAPI app
never touches Redis; the first real `enqueue`/`dequeue` call does).
`ProductWorker`/`app/api/jobs.py`/`app/api/products.py` all depend on
`QueueManager`, never `RedisQueue` directly, so a future second queue
backend only requires a new `BaseQueue` implementation — none of those
callers change.
"""

from uuid import UUID

from app.jobs.base_job import Job
from app.queue.base_queue import BaseQueue
from app.queue.redis_queue import RedisQueue


class QueueManager:
    """Process-wide facade over the configured job queue backend."""

    def __init__(self, *, queue: BaseQueue | None = None) -> None:
        self._queue = queue if queue is not None else RedisQueue()

    async def enqueue(self, job: Job) -> None:
        await self._queue.enqueue(job)

    async def dequeue(self) -> Job | None:
        return await self._queue.dequeue()

    async def ack(self, job: Job) -> None:
        await self._queue.ack(job)

    async def retry(self, job: Job, *, error: str) -> None:
        await self._queue.retry(job, error=error)

    async def get(self, job_id: UUID) -> Job | None:
        return await self._queue.get(job_id)

    async def get_by_product_id(self, product_id: UUID) -> Job | None:
        return await self._queue.get_by_product_id(product_id)

    async def update(self, job: Job) -> None:
        await self._queue.update(job)

    async def get_dead_letter_job_ids(self) -> list[UUID]:
        return await self._queue.get_dead_letter_job_ids()

    async def requeue_stale_jobs(self, *, older_than_seconds: float) -> int:
        """Recover jobs a crashed worker left stuck in-flight — see `RedisQueue`'s own docstring.

        A no-op (returns `0`) for any future `BaseQueue` implementation
        that doesn't define crash recovery this way.
        """
        requeue = getattr(self._queue, "requeue_stale_jobs", None)
        if requeue is None:
            return 0
        result: int = await requeue(older_than_seconds=older_than_seconds)
        return result

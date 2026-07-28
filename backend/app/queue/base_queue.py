"""Abstract job queue interface (Phase 12).

Mirrors `app.services.vectorstore.base.BaseVectorStore`/
`app.services.base_reranker.BaseReranker`: an abstract seam between
"something that queues and dequeues jobs" and `RedisQueue`'s concrete
Redis-backed implementation, so `QueueManager`/`ProductWorker` depend on
this interface rather than the concrete class — a future queue backend
(the phase spec's own `queue_backend` setting reserves the name) could be
substituted without those callers changing.

Four operations, per the phase spec's own list, plus three every
concrete backend needs beyond that literal list: `get`/`get_by_product_id`
(the status endpoints, `GET /jobs/{job_id}`/`GET /products/{id}/status`,
need to look a job up without dequeuing it) and `update` (persisting a
job's own in-place progress — `ProductWorker` reports `progress`/
`current_stage` partway through a job it still holds, and marks it
`COMPLETED` at the end, neither of which is "enqueue a new attempt" the
way `retry()` is). `retry()` is also where dead-letter routing happens —
a job whose `retry_count` would exceed `max_retries` is moved to the
dead-letter queue instead of being re-scheduled, so callers only ever
need to call one method on failure, never decide the dead-letter branch
themselves.
"""

from abc import ABC, abstractmethod
from uuid import UUID

from app.jobs.base_job import Job


class BaseQueue(ABC):
    """Enqueues, dequeues, and tracks the lifecycle of background jobs."""

    @abstractmethod
    async def enqueue(self, job: Job) -> None:
        """Persist `job` and make it available to `dequeue()`."""
        raise NotImplementedError

    @abstractmethod
    async def dequeue(self) -> Job | None:
        """Pop and return the next pending job, marking it `RUNNING`, or `None` if empty."""
        raise NotImplementedError

    @abstractmethod
    async def ack(self, job: Job) -> None:
        """Acknowledge that `job` finished processing (successfully) and is no longer in-flight."""
        raise NotImplementedError

    @abstractmethod
    async def retry(self, job: Job, *, error: str) -> None:
        """Record `error` and either schedule `job` for another attempt or dead-letter it.

        Increments `job.retry_count`; if it now exceeds `job.max_retries`,
        the job is moved to the dead-letter queue (`status=FAILED`)
        instead of being rescheduled.
        """
        raise NotImplementedError

    @abstractmethod
    async def get(self, job_id: UUID) -> Job | None:
        """Return the current record for `job_id`, or `None` if it was never queued."""
        raise NotImplementedError

    @abstractmethod
    async def get_by_product_id(self, product_id: UUID) -> Job | None:
        """Return the job queued for `product_id`, or `None` if none was."""
        raise NotImplementedError

    @abstractmethod
    async def update(self, job: Job) -> None:
        """Persist `job`'s current fields without moving it between queue lists.

        Used for in-place progress reporting and marking a job
        `COMPLETED` — unlike `ack`/`retry`, this never changes which
        list (pending/processing/delayed/dead-letter) `job` is in.
        """
        raise NotImplementedError

    @abstractmethod
    async def get_dead_letter_job_ids(self) -> list[UUID]:
        """Return every job ID currently in the dead-letter queue, oldest first.

        Milestone 5's own "never lose a job" requirement means a job that
        exhausted its retries must stay inspectable, not just silently
        marked `FAILED` — this is what `GET /jobs/dead-letter`
        (`app/api/jobs.py`) reads from.
        """
        raise NotImplementedError

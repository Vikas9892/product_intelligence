"""Unit tests for `QueueManager`.

Composes a fake `BaseQueue` (already covered in isolation by
`test_redis_queue.py`, via `RedisQueue`) so these tests only prove
`QueueManager` delegates correctly.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.jobs.base_job import Job
from app.queue.base_queue import BaseQueue
from app.queue.queue_manager import QueueManager
from app.queue.redis_queue import RedisQueue


class _FakeQueue(BaseQueue):
    def __init__(self) -> None:
        self.enqueued: list[Job] = []
        self.acked: list[Job] = []
        self.retried: list[tuple[Job, str]] = []
        self._by_id: dict[UUID, Job] = {}

    async def enqueue(self, job: Job) -> None:
        self.enqueued.append(job)
        self._by_id[job.job_id] = job

    async def dequeue(self) -> Job | None:
        return self.enqueued.pop(0) if self.enqueued else None

    async def ack(self, job: Job) -> None:
        self.acked.append(job)

    async def retry(self, job: Job, *, error: str) -> None:
        self.retried.append((job, error))

    async def get(self, job_id: UUID) -> Job | None:
        return self._by_id.get(job_id)

    async def get_by_product_id(self, product_id: UUID) -> Job | None:
        return next((job for job in self._by_id.values() if job.product_id == product_id), None)


class _FakeQueueWithRecovery(_FakeQueue):
    def __init__(self, *, recovered: int) -> None:
        super().__init__()
        self._recovered = recovered
        self.recovery_calls: list[float] = []

    async def requeue_stale_jobs(self, *, older_than_seconds: float) -> int:
        self.recovery_calls.append(older_than_seconds)
        return self._recovered


def _job() -> Job:
    now = datetime.now(UTC)
    return Job(job_id=uuid4(), product_id=uuid4(), created_at=now, updated_at=now)


class TestQueueManagerDelegation:
    async def test_enqueue_delegates_to_the_underlying_queue(self) -> None:
        fake_queue = _FakeQueue()
        manager = QueueManager(queue=fake_queue)
        job = _job()

        await manager.enqueue(job)

        assert fake_queue.enqueued == [job]

    async def test_dequeue_delegates_to_the_underlying_queue(self) -> None:
        fake_queue = _FakeQueue()
        job = _job()
        fake_queue.enqueued.append(job)
        manager = QueueManager(queue=fake_queue)

        assert await manager.dequeue() is job

    async def test_ack_delegates_to_the_underlying_queue(self) -> None:
        fake_queue = _FakeQueue()
        manager = QueueManager(queue=fake_queue)
        job = _job()

        await manager.ack(job)

        assert fake_queue.acked == [job]

    async def test_retry_delegates_to_the_underlying_queue(self) -> None:
        fake_queue = _FakeQueue()
        manager = QueueManager(queue=fake_queue)
        job = _job()

        await manager.retry(job, error="boom")

        assert fake_queue.retried == [(job, "boom")]

    async def test_get_delegates_to_the_underlying_queue(self) -> None:
        fake_queue = _FakeQueue()
        job = _job()
        await fake_queue.enqueue(job)
        manager = QueueManager(queue=fake_queue)

        assert await manager.get(job.job_id) is job

    async def test_get_by_product_id_delegates_to_the_underlying_queue(self) -> None:
        fake_queue = _FakeQueue()
        job = _job()
        await fake_queue.enqueue(job)
        manager = QueueManager(queue=fake_queue)

        assert await manager.get_by_product_id(job.product_id) is job


class TestRequeueStaleJobs:
    async def test_delegates_when_the_queue_supports_recovery(self) -> None:
        fake_queue = _FakeQueueWithRecovery(recovered=3)
        manager = QueueManager(queue=fake_queue)

        result = await manager.requeue_stale_jobs(older_than_seconds=60)

        assert result == 3
        assert fake_queue.recovery_calls == [60]

    async def test_is_a_no_op_when_the_queue_does_not_support_recovery(self) -> None:
        fake_queue = _FakeQueue()
        manager = QueueManager(queue=fake_queue)

        result = await manager.requeue_stale_jobs(older_than_seconds=60)

        assert result == 0


class TestQueueManagerDefaults:
    def test_defaults_to_a_redis_queue(self) -> None:
        manager = QueueManager()

        assert isinstance(manager._queue, RedisQueue)

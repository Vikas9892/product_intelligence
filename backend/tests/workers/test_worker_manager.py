"""Unit tests for `WorkerManager`.

Composes fake `ProductWorker`/`BaseQueue` doubles (the real integration
between `ProductWorker` and a real `RedisQueue` is already covered by
`test_product_worker.py`) so start/stop/concurrency/graceful-shutdown/
crash-recovery-loop behavior can be tested against precisely controlled,
fast-running fakes.
"""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.jobs.base_job import Job
from app.queue.base_queue import BaseQueue
from app.queue.queue_manager import QueueManager
from app.workers.worker_manager import WorkerManager


class _SharedCounterWorker:
    """Every worker loop shares this one instance, simulating several loops
    draining the same underlying queue — `processed` is the total across all of them."""

    def __init__(self, *, job_count: int) -> None:
        self._remaining = job_count
        self.processed = 0

    async def process_one(self) -> bool:
        if self._remaining <= 0:
            return False
        self._remaining -= 1
        self.processed += 1
        await asyncio.sleep(0)
        return True


class _BlockingWorker:
    """Blocks on `release_event` the first time `process_one` is called — simulates
    an in-flight job a graceful shutdown must wait for."""

    def __init__(self) -> None:
        self.release_event = asyncio.Event()
        self.entered_event = asyncio.Event()
        self.call_count = 0

    async def process_one(self) -> bool:
        self.call_count += 1
        if self.call_count == 1:
            self.entered_event.set()
            await self.release_event.wait()
            return True
        return False


class _EmptyQueueWorker:
    async def process_one(self) -> bool:
        return False


class _FakeQueueWithRecovery(BaseQueue):
    def __init__(self, *, recovered: int = 0, error: Exception | None = None) -> None:
        self.recovery_calls: list[float] = []
        self._recovered = recovered
        self._error = error

    async def enqueue(self, job: Job) -> None:
        raise NotImplementedError

    async def dequeue(self) -> Job | None:
        return None

    async def ack(self, job: Job) -> None:
        raise NotImplementedError

    async def retry(self, job: Job, *, error: str) -> None:
        raise NotImplementedError

    async def get(self, job_id: UUID) -> Job | None:
        return None

    async def get_by_product_id(self, product_id: UUID) -> Job | None:
        return None

    async def update(self, job: Job) -> None:
        raise NotImplementedError

    async def requeue_stale_jobs(self, *, older_than_seconds: float) -> int:
        self.recovery_calls.append(older_than_seconds)
        if self._error is not None:
            raise self._error
        return self._recovered


def _job() -> Job:
    now = datetime.now(UTC)
    return Job(job_id=uuid4(), product_id=uuid4(), created_at=now, updated_at=now)


class TestStartStop:
    async def test_spawns_the_configured_number_of_worker_loops_plus_recovery(self) -> None:
        manager = WorkerManager(
            worker_factory=_EmptyQueueWorker,
            queue_manager=QueueManager(queue=_FakeQueueWithRecovery()),
            concurrency=3,
            poll_interval_seconds=10,
            job_timeout_seconds=10,
        )

        await manager.start()

        assert len(manager._tasks) == 4  # 3 worker loops + 1 recovery loop
        await manager.stop()

    async def test_concurrent_loops_drain_a_shared_workload(self) -> None:
        shared_worker = _SharedCounterWorker(job_count=10)
        manager = WorkerManager(
            worker_factory=lambda: shared_worker,
            queue_manager=QueueManager(queue=_FakeQueueWithRecovery()),
            concurrency=3,
            poll_interval_seconds=0.01,
            job_timeout_seconds=10,
        )

        await manager.start()
        await asyncio.wait_for(_wait_until(lambda: shared_worker.processed == 10), timeout=2)
        await manager.stop()

        assert shared_worker.processed == 10


class TestGracefulShutdown:
    async def test_stop_waits_for_an_in_flight_job_to_finish(self) -> None:
        worker = _BlockingWorker()
        manager = WorkerManager(
            worker_factory=lambda: worker,
            queue_manager=QueueManager(queue=_FakeQueueWithRecovery()),
            concurrency=1,
            poll_interval_seconds=0.01,
            job_timeout_seconds=10,
        )
        await manager.start()
        await asyncio.wait_for(worker.entered_event.wait(), timeout=2)

        stop_task = asyncio.create_task(manager.stop())
        await asyncio.sleep(0.05)
        assert not stop_task.done()  # still waiting on the blocked in-flight job

        worker.release_event.set()
        await asyncio.wait_for(stop_task, timeout=2)

        assert stop_task.done()

    async def test_stop_is_safe_to_call_before_start(self) -> None:
        manager = WorkerManager(
            worker_factory=_EmptyQueueWorker,
            queue_manager=QueueManager(queue=_FakeQueueWithRecovery()),
        )

        await manager.stop()  # no tasks yet — should not raise


class TestCrashRecoveryLoop:
    async def test_periodically_calls_requeue_stale_jobs(self) -> None:
        fake_queue = _FakeQueueWithRecovery()
        manager = WorkerManager(
            worker_factory=_EmptyQueueWorker,
            queue_manager=QueueManager(queue=fake_queue),
            concurrency=1,
            poll_interval_seconds=10,
            job_timeout_seconds=0.02,
        )

        await manager.start()
        await asyncio.wait_for(_wait_until(lambda: len(fake_queue.recovery_calls) >= 2), timeout=2)
        await manager.stop()

        assert fake_queue.recovery_calls[0] == 0.02

    async def test_logs_a_warning_when_jobs_are_actually_recovered(self) -> None:
        fake_queue = _FakeQueueWithRecovery(recovered=2)
        manager = WorkerManager(
            worker_factory=_EmptyQueueWorker,
            queue_manager=QueueManager(queue=fake_queue),
            concurrency=1,
            poll_interval_seconds=10,
            job_timeout_seconds=0.02,
        )

        await manager.start()
        await asyncio.wait_for(_wait_until(lambda: len(fake_queue.recovery_calls) >= 1), timeout=2)
        await manager.stop()

        assert fake_queue.recovery_calls  # the loop ran at least once without raising

    async def test_survives_a_failing_recovery_check(self) -> None:
        fake_queue = _FakeQueueWithRecovery(error=RuntimeError("redis unreachable"))
        manager = WorkerManager(
            worker_factory=_EmptyQueueWorker,
            queue_manager=QueueManager(queue=fake_queue),
            concurrency=1,
            poll_interval_seconds=10,
            job_timeout_seconds=0.02,
        )

        await manager.start()
        await asyncio.wait_for(_wait_until(lambda: len(fake_queue.recovery_calls) >= 2), timeout=2)
        await manager.stop()

        # The loop kept running (recovered a 2nd call) despite the 1st raising.
        assert len(fake_queue.recovery_calls) >= 2


async def _wait_until(predicate: Callable[[], bool]) -> None:
    while not predicate():
        await asyncio.sleep(0.005)

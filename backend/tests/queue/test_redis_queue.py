"""Unit tests for `RedisQueue`.

Uses `fakeredis`'s async client — an in-memory, protocol-compatible
stand-in for a real Redis server — so these tests are fast, deterministic,
and need no real Redis instance running. Multiple `RedisQueue`s sharing
one `fakeredis.FakeServer` simulate multiple worker processes hitting the
same real Redis server (`fakeredis.FakeRedis()` instances are otherwise
isolated from each other by default).
"""

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import fakeredis
from fakeredis import aioredis as fake_aioredis

from app.jobs.base_job import Job
from app.jobs.job_status import JobStatus
from app.queue.redis_queue import RedisQueue


def _job(**overrides: object) -> Job:
    now = datetime.now(UTC)
    defaults: dict[str, object] = {
        "job_id": uuid4(),
        "product_id": uuid4(),
        "created_at": now,
        "updated_at": now,
    }
    defaults.update(overrides)
    return Job(**defaults)


def _queue(*, server: fakeredis.FakeServer | None = None, **kwargs: object) -> RedisQueue:
    client = fake_aioredis.FakeRedis(
        server=server if server is not None else fakeredis.FakeServer(), decode_responses=True
    )
    return RedisQueue(redis_client=client, queue_name="test-queue", **kwargs)  # type: ignore[arg-type]


class TestEnqueueDequeue:
    async def test_dequeue_returns_none_when_empty(self) -> None:
        queue = _queue()

        assert await queue.dequeue() is None

    async def test_dequeues_an_enqueued_job(self) -> None:
        queue = _queue()
        job = _job()

        await queue.enqueue(job)
        dequeued = await queue.dequeue()

        assert dequeued is not None
        assert dequeued.job_id == job.job_id
        assert dequeued.product_id == job.product_id

    async def test_dequeue_marks_the_job_running(self) -> None:
        queue = _queue()
        await queue.enqueue(_job())

        dequeued = await queue.dequeue()

        assert dequeued is not None
        assert dequeued.status is JobStatus.RUNNING

    async def test_dequeues_in_fifo_order(self) -> None:
        queue = _queue()
        first, second = _job(), _job()
        await queue.enqueue(first)
        await queue.enqueue(second)

        first_out = await queue.dequeue()
        second_out = await queue.dequeue()

        assert first_out is not None and first_out.job_id == first.job_id
        assert second_out is not None and second_out.job_id == second.job_id

    async def test_duplicate_enqueue_of_the_same_job_id_does_not_duplicate_processing(self) -> None:
        # Re-enqueuing the same job_id (e.g. a caller retrying an upload
        # request) overwrites the same job record and adds a second
        # pending entry, but the job's own identity never duplicates —
        # dequeuing both entries yields the same job_id twice, not two
        # independent jobs.
        queue = _queue()
        job = _job()

        await queue.enqueue(job)
        await queue.enqueue(job)

        first = await queue.dequeue()
        second = await queue.dequeue()

        assert first is not None and second is not None
        assert first.job_id == second.job_id == job.job_id


class TestAck:
    async def test_ack_removes_the_job_from_in_flight_tracking(self) -> None:
        queue = _queue()
        await queue.enqueue(_job())
        job = await queue.dequeue()
        assert job is not None

        await queue.ack(job)

        assert await queue.requeue_stale_jobs(older_than_seconds=0) == 0


class TestRetry:
    async def test_retry_reschedules_within_max_retries(self) -> None:
        queue = _queue(retry_delay_seconds=0.01)
        await queue.enqueue(_job(max_retries=3))
        job = await queue.dequeue()
        assert job is not None

        await queue.retry(job, error="transient failure")

        assert await queue.dequeue() is None  # still waiting out the backoff delay
        await asyncio.sleep(0.05)
        retried = await queue.dequeue()
        assert retried is not None
        assert retried.retry_count == 1
        assert retried.status is JobStatus.RUNNING  # dequeue() re-marks it running
        assert retried.error == "transient failure"

    async def test_retry_uses_exponential_backoff(self) -> None:
        # 1st retry delay = base; 2nd retry delay = 2x base — a
        # comfortably large base and margins keep this deterministic
        # despite real wall-clock scheduling/logging overhead.
        base_delay = 0.2
        queue = _queue(retry_delay_seconds=base_delay)
        await queue.enqueue(_job(max_retries=5))
        job = await queue.dequeue()
        assert job is not None

        await queue.retry(job, error="fail 1")
        await asyncio.sleep(base_delay + 0.15)
        job = await queue.dequeue()
        assert job is not None
        assert job.retry_count == 1

        await queue.retry(job, error="fail 2")
        await asyncio.sleep(base_delay + 0.05)  # short of the 2nd retry's 2x delay
        assert await queue.dequeue() is None
        await asyncio.sleep(base_delay + 0.15)
        job = await queue.dequeue()
        assert job is not None
        assert job.retry_count == 2

    async def test_exhausting_retries_moves_the_job_to_the_dead_letter_queue(self) -> None:
        queue = _queue(retry_delay_seconds=0.01)
        job = _job(max_retries=1)
        await queue.enqueue(job)
        dequeued = await queue.dequeue()
        assert dequeued is not None

        await queue.retry(dequeued, error="fail 1")
        await asyncio.sleep(0.03)
        dequeued = await queue.dequeue()
        assert dequeued is not None

        await queue.retry(dequeued, error="fail 2 (exhausted)")

        dead_letter_ids = await queue.get_dead_letter_job_ids()
        assert dead_letter_ids == [job.job_id]

        stored = await queue.get(job.job_id)
        assert stored is not None
        assert stored.status is JobStatus.FAILED
        assert stored.error == "fail 2 (exhausted)"

    async def test_dead_lettered_jobs_are_never_dequeued_again(self) -> None:
        queue = _queue(retry_delay_seconds=0.01)
        await queue.enqueue(_job(max_retries=0))
        job = await queue.dequeue()
        assert job is not None

        await queue.retry(job, error="fail")

        assert await queue.dequeue() is None


class TestUpdate:
    async def test_persists_progress_without_moving_the_job_between_lists(self) -> None:
        queue = _queue()
        await queue.enqueue(_job())
        job = await queue.dequeue()
        assert job is not None

        job.progress = 60
        job.current_stage = "Generating Embeddings"
        await queue.update(job)

        stored = await queue.get(job.job_id)
        assert stored is not None
        assert stored.progress == 60
        assert stored.current_stage == "Generating Embeddings"
        # Still only reachable via get() — update() didn't re-enqueue it.
        assert await queue.dequeue() is None


class TestLookups:
    async def test_get_returns_none_for_an_unknown_job(self) -> None:
        queue = _queue()

        assert await queue.get(uuid4()) is None

    async def test_get_by_product_id_returns_none_when_never_queued(self) -> None:
        queue = _queue()

        assert await queue.get_by_product_id(uuid4()) is None

    async def test_get_by_product_id_finds_the_queued_job(self) -> None:
        queue = _queue()
        job = _job()
        await queue.enqueue(job)

        found = await queue.get_by_product_id(job.product_id)

        assert found is not None
        assert found.job_id == job.job_id


class TestCrashRecovery:
    async def test_requeue_stale_jobs_recovers_an_in_flight_job(self) -> None:
        server = fakeredis.FakeServer()
        producer = _queue(server=server, retry_delay_seconds=0.01)
        job = _job(max_retries=3)
        await producer.enqueue(job)
        crashed_worker = _queue(server=server)
        dequeued = await crashed_worker.dequeue()
        assert dequeued is not None
        # Simulate the worker crashing here: never ack()/retry() is called.

        recovering_worker = _queue(server=server, retry_delay_seconds=0.01)
        requeued_count = await recovering_worker.requeue_stale_jobs(older_than_seconds=0)

        assert requeued_count == 1
        await asyncio.sleep(0.03)
        recovered = await recovering_worker.dequeue()
        assert recovered is not None
        assert recovered.job_id == job.job_id
        assert recovered.retry_count == 1

    async def test_requeue_stale_jobs_ignores_jobs_within_the_threshold(self) -> None:
        queue = _queue()
        await queue.enqueue(_job())
        dequeued = await queue.dequeue()
        assert dequeued is not None

        requeued_count = await queue.requeue_stale_jobs(older_than_seconds=3600)

        assert requeued_count == 0

    async def test_requeue_stale_jobs_is_a_no_op_when_nothing_is_in_flight(self) -> None:
        queue = _queue()

        assert await queue.requeue_stale_jobs(older_than_seconds=0) == 0


class TestConcurrentWorkers:
    async def test_two_workers_sharing_a_queue_never_dequeue_the_same_job(self) -> None:
        server = fakeredis.FakeServer()
        producer = _queue(server=server)
        jobs = [_job() for _ in range(10)]
        for job in jobs:
            await producer.enqueue(job)

        worker_a = _queue(server=server)
        worker_b = _queue(server=server)

        results = await asyncio.gather(
            *(worker_a.dequeue() if i % 2 == 0 else worker_b.dequeue() for i in range(10))
        )

        dequeued_ids = {result.job_id for result in results if result is not None}
        assert dequeued_ids == {job.job_id for job in jobs}
        assert len(dequeued_ids) == 10

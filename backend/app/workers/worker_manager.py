"""`WorkerManager`: runs a pool of `ProductWorker` loops concurrently (Phase 12).

`worker_concurrency` (`AsyncPipelineSettings`) many independent worker
loops, each repeatedly calling `ProductWorker.process_one()` and backing
off (polling) when the queue is empty. This class never runs inside the
API process itself — `app/lifespan.py` stays untouched, so the API
stays responsive regardless of worker load, matching the architecture
diagram's own separate "Worker Process" boxes — `scripts/run_workers.py`
is what actually invokes it as a standalone process; everything here is
still plain `asyncio`, fully testable in-process via `start()`/`stop()`.

**Crash recovery.** Alongside the worker loops, one recovery loop calls
`QueueManager.requeue_stale_jobs` every `JOB_TIMEOUT_SECONDS` — a job
still sitting in `processing` after that long almost certainly belongs
to a worker process that died mid-job (killed, crashed, OOM), so it's
recovered through the normal `retry()` path rather than lost forever.

**Graceful shutdown.** `stop()` sets an `asyncio.Event` every loop checks
only *between* jobs, never mid-job, then awaits every loop task — an
in-flight job always finishes (or fails through to `retry()`) before the
process actually exits, never killed mid-write.
"""

import asyncio
import contextlib
from collections.abc import Callable
from typing import Protocol

from app.core.config import settings
from app.core.logging import get_logger
from app.queue.queue_manager import QueueManager
from app.workers.product_worker import ProductWorker

logger = get_logger(__name__)


class _Worker(Protocol):
    """What `WorkerManager` actually depends on: a `process_one()` — not the full
    `ProductWorker` type — so tests can supply a lightweight fake loop body."""

    async def process_one(self) -> bool: ...


class WorkerManager:
    """Runs `concurrency` many `ProductWorker` loops, plus one crash-recovery loop, until `stop()`."""

    def __init__(
        self,
        *,
        worker_factory: Callable[[], _Worker] | None = None,
        queue_manager: QueueManager | None = None,
        concurrency: int | None = None,
        poll_interval_seconds: float | None = None,
        job_timeout_seconds: float | None = None,
    ) -> None:
        self._worker_factory = worker_factory if worker_factory is not None else ProductWorker
        self._queue_manager = queue_manager if queue_manager is not None else QueueManager()
        self._concurrency = (
            concurrency if concurrency is not None else settings.async_pipeline.worker_concurrency
        )
        self._poll_interval_seconds = (
            poll_interval_seconds if poll_interval_seconds is not None else 1.0
        )
        self._job_timeout_seconds = (
            job_timeout_seconds
            if job_timeout_seconds is not None
            else settings.async_pipeline.job_timeout_seconds
        )
        self._stop_event = asyncio.Event()
        self._tasks: list[asyncio.Task[None]] = []

    async def start(self) -> None:
        """Spawn `concurrency` worker loops plus one crash-recovery loop."""
        self._stop_event.clear()
        self._tasks = [
            asyncio.create_task(self._run_worker_loop(index)) for index in range(self._concurrency)
        ]
        self._tasks.append(asyncio.create_task(self._run_recovery_loop()))
        logger.info("Worker pool started: concurrency=%d", self._concurrency)

    async def stop(self) -> None:
        """Signal every loop to stop after its current job, and wait for them to exit."""
        self._stop_event.set()
        if self._tasks:
            await asyncio.gather(*self._tasks)
        self._tasks = []
        logger.info("Worker pool stopped: concurrency=%d", self._concurrency)

    async def _run_worker_loop(self, worker_index: int) -> None:
        worker = self._worker_factory()
        logger.info("Worker loop started: worker_index=%d", worker_index)
        while not self._stop_event.is_set():
            processed = await worker.process_one()
            if not processed:
                await self._wait_or_stop(self._poll_interval_seconds)
        logger.info("Worker loop stopped: worker_index=%d", worker_index)

    async def _run_recovery_loop(self) -> None:
        logger.info("Crash-recovery loop started: threshold=%.1fs", self._job_timeout_seconds)
        while not self._stop_event.is_set():
            try:
                requeued = await self._queue_manager.requeue_stale_jobs(
                    older_than_seconds=self._job_timeout_seconds
                )
                if requeued:
                    logger.warning("Crash recovery requeued stale jobs: count=%d", requeued)
            except Exception:
                logger.warning("Crash-recovery check failed", exc_info=True)
            await self._wait_or_stop(self._job_timeout_seconds)
        logger.info("Crash-recovery loop stopped")

    async def _wait_or_stop(self, timeout_seconds: float) -> None:
        """Sleep for `timeout_seconds`, waking early (and staying awake) if `stop()` is called."""
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._stop_event.wait(), timeout=timeout_seconds)

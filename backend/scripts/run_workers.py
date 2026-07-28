"""Runs the background worker pool as a standalone process (Phase 12).

Usage:

    uv run python scripts/run_workers.py

Not part of the importable `app` package, matching `scripts/`'s own
established purpose (see `backend/README.md`'s folder-structure
section). This is the actual "Worker Process" the architecture diagram
draws separately from "Upload API" — `uvicorn app.main:app` never runs
`WorkerManager` itself (see that module's own docstring for why), so
this script is what does, as its own OS process.

Exits gracefully on SIGINT/SIGTERM: `WorkerManager.stop()` lets any
in-flight job finish (or fail through to a scheduled retry) before the
process actually exits, never killed mid-write.
"""

import asyncio
import signal
import sys
from pathlib import Path
from typing import Protocol

# Makes `app` importable when this script is run directly, the same
# reasoning `scripts/benchmark.py` already documents for itself.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings
from app.core.logging import get_logger
from app.workers.worker_manager import WorkerManager

logger = get_logger(__name__)


class _Manageable(Protocol):
    """What `run_until_stopped` actually depends on — not the full `WorkerManager`
    type — so a test can supply a lightweight fake instead of real worker loops."""

    async def start(self) -> None:
        raise NotImplementedError

    async def stop(self) -> None:
        raise NotImplementedError


async def run_until_stopped(
    manager: _Manageable, *, stop_event: asyncio.Event | None = None
) -> None:
    """Start `manager`, then block until a shutdown signal arrives, then stop it gracefully.

    `stop_event` is constructor-injectable (defaulting to a fresh
    `asyncio.Event`) purely for testability — a test can supply its own
    and set it directly instead of needing to raise a real OS signal.
    """
    await manager.start()
    logger.info(
        "Worker pool running: concurrency=%d, queue=%s, redis_url=%s",
        settings.async_pipeline.worker_concurrency,
        settings.async_pipeline.queue_name,
        settings.async_pipeline.redis_url,
    )

    stop_event = stop_event if stop_event is not None else asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            # Not every platform (notably Windows) supports asyncio signal
            # handlers — falling back to the synchronous `signal.signal`
            # still lets Ctrl+C interrupt `stop_event.wait()` below via
            # the default KeyboardInterrupt behavior.
            signal.signal(sig, lambda *_args: stop_event.set())

    await stop_event.wait()
    logger.info("Shutdown signal received, stopping worker pool...")
    await manager.stop()


def main() -> None:
    manager = WorkerManager()
    asyncio.run(run_until_stopped(manager))


if __name__ == "__main__":
    main()

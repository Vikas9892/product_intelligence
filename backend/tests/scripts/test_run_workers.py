"""Unit tests for `scripts/run_workers.py`.

`scripts/` has no `__init__.py` (it's not part of the importable `app`
package) but is still importable as a namespace package here, since
`pyproject.toml`'s `pythonpath = ["."]` already puts `backend/` on
`sys.path` for the test suite — see `tests/scripts/test_benchmark.py`'s
own docstring.
"""

import asyncio

from scripts import run_workers


class _FakeWorkerManager:
    def __init__(self) -> None:
        self.start_calls = 0
        self.stop_calls = 0

    async def start(self) -> None:
        self.start_calls += 1

    async def stop(self) -> None:
        self.stop_calls += 1


class TestRunUntilStopped:
    async def test_starts_the_manager(self) -> None:
        manager = _FakeWorkerManager()
        stop_event = asyncio.Event()
        stop_event.set()  # already "signalled" — returns immediately

        await run_workers.run_until_stopped(manager, stop_event=stop_event)

        assert manager.start_calls == 1

    async def test_stops_the_manager_once_the_event_is_set(self) -> None:
        manager = _FakeWorkerManager()
        stop_event = asyncio.Event()
        stop_event.set()

        await run_workers.run_until_stopped(manager, stop_event=stop_event)

        assert manager.stop_calls == 1

    async def test_blocks_until_the_event_is_set(self) -> None:
        manager = _FakeWorkerManager()
        stop_event = asyncio.Event()

        task = asyncio.create_task(run_workers.run_until_stopped(manager, stop_event=stop_event))
        await asyncio.sleep(0.02)
        assert not task.done()  # still waiting — stop_event was never set

        stop_event.set()
        await asyncio.wait_for(task, timeout=2)

        assert manager.stop_calls == 1

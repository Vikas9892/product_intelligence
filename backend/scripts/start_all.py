"""Runs the API and the worker pool as child processes of one container.

Usage:

    python scripts/start_all.py

**Why this exists.** `uvicorn app.main:app` never runs `WorkerManager` (see
`scripts/run_workers.py`), so the platform normally needs two OS processes.
Locally and under Docker Compose those are two separate containers, which is
the right shape and is what `docker-compose.yml` does.

Render cannot express that shape for *this* app. The API writes an upload to
`storage.upload_dir` (`UploadService.save_upload`), the worker reads that same
path back (`ProductService`), and the API later serves it (`ProductImageService`)
— so both roles need one shared filesystem. On Render a persistent disk is
reachable by exactly one service and cannot be mounted into a second, so
"API service + worker service" would give the worker an empty directory and a
`FileNotFoundError` on every job. Running both roles in one service, against
one disk, is what keeps that contract intact.

**What this costs.** API and worker no longer scale independently, and the
service is capped at a single instance (a Render service with a disk cannot
scale out anyway). Both processes load their own copy of CLIP/BGE/the
cross-encoder, so the instance must be sized for two model sets, not one.
Moving uploads to object storage is what removes this constraint; until then
this is the honest trade.

Two child processes rather than one process running both: `WorkerManager`
does CPU-bound model inference on its event loop, and sharing a loop with
uvicorn would let a single embedding batch stall every in-flight HTTP request.
Separate processes keep the API responsive at the cost of a second model set.

Signals: Render sends SIGTERM on deploy and shutdown, tini forwards it here,
and this forwards it to both children — uvicorn drains in-flight requests and
`run_workers.py` lets the current job finish. If either child exits on its own,
the other is stopped too and this process exits non-zero, so the platform
restarts the whole service rather than leaving it half-running (a live API
with a dead worker is exactly the "stuck at Queued forever" failure that is
invisible from the UI).
"""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from types import FrameType

BACKEND_DIR = Path(__file__).resolve().parents[1]

#: How long a child gets to shut down gracefully after SIGTERM before it is
#: killed. Render's own shutdown grace period is 30s, so this stays under it —
#: a SIGKILL from us with a diagnostic is better than an opaque platform kill.
GRACEFUL_SHUTDOWN_SECONDS = 25

#: Render injects PORT and routes external traffic to it. Falling back to the
#: app's own default keeps this script runnable outside Render unchanged.
PORT = os.environ.get("PORT", "8000")


def _spawn(name: str, argv: list[str]) -> subprocess.Popen[bytes]:
    print(f"[start_all] starting {name}: {' '.join(argv)}", flush=True)
    return subprocess.Popen(argv, cwd=str(BACKEND_DIR))


def main() -> int:
    children: dict[str, subprocess.Popen[bytes]] = {
        # No --workers: a second uvicorn worker would be a third and fourth
        # copy of the models in the same container.
        "api": _spawn(
            "api",
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", PORT],
        ),
        "worker": _spawn("worker", [sys.executable, "scripts/run_workers.py"]),
    }

    shutting_down = False

    def _forward_termination(signum: int, _frame: FrameType | None) -> None:
        nonlocal shutting_down
        if shutting_down:
            return
        shutting_down = True
        print(f"[start_all] received signal {signum}, stopping children", flush=True)
        for name, proc in children.items():
            if proc.poll() is None:
                print(f"[start_all] SIGTERM -> {name}", flush=True)
                proc.terminate()

    signal.signal(signal.SIGTERM, _forward_termination)
    signal.signal(signal.SIGINT, _forward_termination)

    # Supervise: the first child to exit takes the whole service down with it.
    while not shutting_down:
        for name, proc in children.items():
            code = proc.poll()
            if code is not None:
                print(f"[start_all] {name} exited with code {code}; stopping the rest", flush=True)
                _forward_termination(signal.SIGTERM, None)
                break
        time.sleep(1)

    deadline = time.monotonic() + GRACEFUL_SHUTDOWN_SECONDS
    for name, proc in children.items():
        remaining = max(0.0, deadline - time.monotonic())
        try:
            proc.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            print(f"[start_all] {name} did not exit in time; SIGKILL", flush=True)
            proc.kill()
            proc.wait()

    # Report the first non-zero child status, so a crash-loop is visible to the
    # platform instead of being laundered into a clean exit.
    #
    # The raw value is not usable as an exit status: a child killed by a signal
    # reports a negative returncode on POSIX, and Windows reports values far
    # outside 0-255. Both would be mangled by the OS into something arbitrary —
    # possibly into 0, which would report a crash as a clean shutdown. Any
    # non-zero code is collapsed to 1; the real cause is in the line above it.
    for name, proc in children.items():
        if proc.returncode:
            print(
                f"[start_all] {name} returned {proc.returncode}; exiting 1",
                flush=True,
            )
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

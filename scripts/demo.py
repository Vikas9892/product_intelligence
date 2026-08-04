#!/usr/bin/env python3
"""One command from a fresh clone to a verified, populated demo.

    python scripts/demo.py

Starts the stack, waits for it to be healthy, seeds a deterministic demo
catalog through the real upload API, verifies every capability end to end,
and prints where to look.

Cross-platform on purpose. `make demo` wraps this, but the script is the
implementation and runs directly anywhere Python does -- Windows developers
should not need GNU make to see the project work.

Exit codes match the smoke runner: 0 verified, 1 something is broken, 2 the
script could not run (Docker missing, bad arguments).
"""

from __future__ import annotations

import argparse
import contextlib
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER = REPO_ROOT / "scripts" / "smoke" / "runner.py"

#: Where Docker Desktop installs on Windows without always being on PATH --
#: a very common state, and "docker: command not found" is an unhelpful thing
#: to tell someone who has Docker Desktop running in front of them.
_WINDOWS_DOCKER_FALLBACKS = (
    r"C:\Program Files\Docker\Docker\resources\bin\docker.exe",
    r"C:\Program Files\Docker\Docker\resources\bin\docker",
)

_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _paint(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _COLOR else text


def _bold(text: str) -> str:
    return _paint(text, "1")


def _green(text: str) -> str:
    return _paint(text, "32")


def _red(text: str) -> str:
    return _paint(text, "31")


def _dim(text: str) -> str:
    return _paint(text, "2")


def _configure_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            with contextlib.suppress(ValueError, OSError):
                reconfigure(encoding="utf-8", errors="replace")


def find_docker() -> str | None:
    """Locate the docker executable, PATH first then the usual Windows spot."""
    found = shutil.which("docker")
    if found:
        return found
    if sys.platform == "win32":
        for candidate in _WINDOWS_DOCKER_FALLBACKS:
            if Path(candidate).exists():
                return candidate
    return None


def compose_files(profile: str) -> list[str]:
    """Base file plus the requested overlay."""
    overlay = (
        "docker-compose.dev.yml" if profile == "dev" else "docker-compose.prod.yml"
    )
    return ["-f", "docker-compose.yml", "-f", overlay]


def start_stack(docker: str, profile: str, *, build: bool, env: dict[str, str]) -> int:
    """Bring the stack up and wait for health.

    `--wait` is what makes this a one-command flow: it blocks until every
    service with a health check reports healthy, so the smoke run that follows
    is not racing a backend still importing torch.
    """
    command = [docker, "compose", *compose_files(profile), "up", "-d", "--wait"]
    if build:
        command.insert(-2, "--build")

    print(_dim(f"  $ {' '.join(command[1:])}"))
    sys.stdout.flush()  # same buffering reason as run_smoke below
    result = subprocess.run(command, cwd=REPO_ROOT, env=env, check=False)
    return result.returncode


def run_smoke(args: argparse.Namespace, env: dict[str, str]) -> int:
    """Run the verification suite as a subprocess.

    A subprocess rather than an import so its exit code, output buffering and
    signal handling stay exactly as they are when run standalone -- the demo
    wrapper should not be a second, subtly different way to run the suite.
    """
    command = [
        sys.executable,
        str(RUNNER),
        "--base-url",
        args.base_url,
        "--timeout",
        str(args.timeout),
        "--pipeline-timeout",
        str(args.pipeline_timeout),
    ]
    # Flush before handing the terminal to the child. When stdout is a pipe
    # (a CI log, `| tee`), this process block-buffers while the subprocess
    # writes straight through -- so without this the banner printed first
    # lands last, and the log reads as though the demo finished before it
    # started.
    sys.stdout.flush()
    result = subprocess.run(command, cwd=REPO_ROOT, env=env, check=False)
    return result.returncode


def main(argv: list[str] | None = None) -> int:
    _configure_stdout()
    parser = argparse.ArgumentParser(
        prog="demo",
        description="Start, seed and verify a complete Product Intelligence demo.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python scripts/demo.py                    # start, seed, verify\n"
            "  python scripts/demo.py --profile dev      # hot-reload profile\n"
            "  python scripts/demo.py --no-start         # verify what is already running\n"
        ),
    )
    parser.add_argument(
        "--profile",
        choices=("prod", "dev"),
        default="prod",
        help="Compose overlay to start (default: %(default)s).",
    )
    parser.add_argument(
        "--no-start",
        action="store_true",
        help="Do not touch Docker; just seed and verify whatever is already running.",
    )
    parser.add_argument(
        "--no-build",
        action="store_true",
        help="Skip the image build (faster when images are already current).",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("SMOKE_BASE_URL", "http://localhost:8000"),
        help="API origin to verify (default: %(default)s).",
    )
    parser.add_argument(
        "--frontend-port",
        default=os.environ.get("FRONTEND_PORT", "3000"),
        help="Host port to publish the frontend on (default: %(default)s).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help=(
            "Per-request timeout (default: %(default)s). The demo is the cold "
            "path: the first request touching a model waits for it to load."
        ),
    )
    parser.add_argument(
        "--pipeline-timeout",
        type=float,
        default=900.0,
        help=(
            "Seconds to allow for async processing (default: %(default)s). "
            "The first run downloads ~730 MB of model weights."
        ),
    )
    args = parser.parse_args(argv)

    print()
    print(_bold("Product Intelligence - Demo Setup"))
    print()

    env = {**os.environ, "FRONTEND_PORT": str(args.frontend_port)}

    if not args.no_start:
        docker = find_docker()
        if docker is None:
            print(_red("  Docker was not found."))
            print("  Install Docker Desktop, or use --no-start to verify a")
            print("  deployment you are running some other way.")
            return 2

        print(_dim(f"  Starting the {args.profile} stack (first run builds images)..."))
        code = start_stack(docker, args.profile, build=not args.no_build, env=env)
        if code != 0:
            print()
            print(_red("  The stack did not come up."))
            print("  Check `docker compose ps` and `docker compose logs`.")
            print(
                "  A port conflict is the most common cause -- try "
                "--frontend-port 3100."
            )
            return 2
        print()

    started = time.monotonic()
    code = run_smoke(args, env)
    elapsed = time.monotonic() - started

    print()
    if code == 0:
        print(_green(_bold("Demo environment ready.")))
        print()
        print(f"  Frontend    http://localhost:{args.frontend_port}")
        print(f"  API docs    {args.base_url}/docs")
        print(f"  API health  {args.base_url}/health")
        print()
        print(
            _dim(
                "  The catalog holds 8 synthetic demo products with known\n"
                "  relationships. `python scripts/smoke/runner.py --list-catalog`\n"
                "  explains what each one is for."
            )
        )
    else:
        print(_red(_bold("Demo setup failed verification.")))
        print()
        print("  The failing checks are listed above, each with the request that")
        print("  produced it. Useful next steps:")
        print(
            f"    python {RUNNER.relative_to(REPO_ROOT)} --base-url {args.base_url} -v"
        )
        print("    docker compose logs api worker")
    print(_dim(f"  ({elapsed:.0f}s)"))
    print()
    return code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        sys.exit(2)

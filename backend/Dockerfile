# syntax=docker/dockerfile:1.7
#
# Production image for the Multi-Modal Product Intelligence backend.
#
# One image, two runtime roles (the CMD decides which):
#
#   API     uvicorn app.main:app          -- the default CMD below
#   worker  python scripts/run_workers.py -- see docker-compose.yml
#
# Both roles need the identical dependency closure (the worker imports the
# same services the API does), so building two images would mean downloading
# torch twice and keeping two artifacts in sync for no benefit. This is also
# what lets Stage 10+ push a single image to ECR and run it as two ECS
# services.
#
# Build from the repository root so the context is `backend/`:
#   docker build -t product-intelligence-backend:latest ./backend

# ---------------------------------------------------------------------------
# Stage 1: builder -- resolve and install dependencies into a virtualenv
# ---------------------------------------------------------------------------
# Pinned by digest-free tag on purpose: `python:3.12-slim-bookworm` matches
# requires-python ">=3.12,<3.13" in pyproject.toml. The builder is discarded,
# so anything installed here (compilers, uv itself, build metadata) never
# reaches the runtime image.
FROM python:3.12-slim-bookworm AS builder

# Copy the uv binary from its official distroless image rather than curl|sh:
# no network fetch at build time, no shell pipeline to audit, and the version
# is pinned and reproducible. Kept in step with the uv that writes uv.lock on
# developer machines (currently 0.11.28) so the image never has to interpret a
# lock format newer than itself.
COPY --from=ghcr.io/astral-sh/uv:0.11.28 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependency layer, cached independently of application source. Only
# pyproject.toml + uv.lock are copied first, so editing app/ code does not
# invalidate the (very expensive -- torch is ~200 MB even CPU-only) install.
#
# --frozen: fail if uv.lock disagrees with pyproject.toml instead of silently
#           re-resolving, so the image is built from exactly the reviewed,
#           committed dependency set.
# --no-dev: exclude the dev group (pytest, mypy, ruff, black, pre-commit).
#           Quality gates run in CI, never inside a shipped runtime image.
# --no-install-project: install only third-party deps in this layer; the
#           project itself is installed after the source is copied.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# Application source, then the project itself (a fast, tiny layer).
#
# README.md is required here, not optional: pyproject.toml sets
# `readme = "README.md"`, and hatchling reads it while building the wheel.
# It is copied in this layer rather than with pyproject.toml/uv.lock above so
# that editing documentation does not invalidate the expensive dependency
# layer.
COPY README.md ./
COPY app/ ./app/
COPY scripts/ ./scripts/
COPY evaluation/ ./evaluation/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ---------------------------------------------------------------------------
# Stage 2: runtime -- minimal image, no build tooling, non-root
# ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime

# Two added packages. Python is already present in the base, and the apt lists
# are removed in the same layer so they are not committed.
#
# `tini` makes signal handling correct -- see ENTRYPOINT below.
#
# `redis-server` is present but NOT started by default. It is used only where
# the platform offers no managed Redis and no persistent disk -- Hugging Face
# Spaces -- and is opted into at runtime with START_EMBEDDED_REDIS=1
# (scripts/start_all.py). Installing it unconditionally costs a few MB and
# keeps one image valid on every target, rather than forking the Dockerfile per
# platform; leaving it *stopped* by default is what prevents a local Redis from
# silently shadowing a real managed one.
RUN apt-get update \
    && apt-get install --no-install-recommends -y tini redis-server \
    && rm -rf /var/lib/apt/lists/*

# Unprivileged runtime user. A fixed UID/GID (not an auto-assigned one) keeps
# file ownership on the mounted volumes stable and predictable across rebuilds
# and across hosts.
RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin app

ENV \
    # Never buffer stdout/stderr: the app logs via StreamHandler(sys.stdout)
    # (app/core/logging.py), and buffering would delay or lose lines on a
    # container stop, which is exactly when the logs matter most.
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # Use the venv the builder produced, without needing an activate script.
    PATH="/app/.venv/bin:$PATH" \
    VIRTUAL_ENV="/app/.venv" \
    # Hugging Face model cache. Explicit and outside $HOME so it can be a
    # named volume: CLIP (~600 MB) and BGE (~130 MB) download on first use,
    # and without a persistent, writable location every container restart
    # would re-download them. Left unset, huggingface_hub would default to
    # ~/.cache/huggingface, which is neither obvious nor easy to mount.
    HF_HOME=/models \
    # Model downloads are the only outbound network calls the app makes at
    # runtime; keeping telemetry off avoids a second, unrelated one.
    HF_HUB_DISABLE_TELEMETRY=1

WORKDIR /app

# Virtualenv and application source, all owned by the unprivileged user.
COPY --from=builder --chown=app:app /app/.venv/ /app/.venv/
COPY --from=builder --chown=app:app /app/app/ /app/app/
COPY --from=builder --chown=app:app /app/scripts/ /app/scripts/
COPY --from=builder --chown=app:app /app/evaluation/ /app/evaluation/

# Runtime directories, pre-created and owned by `app` so the process can write
# to them whether or not a volume is mounted over them. These mirror
# app/core/paths.py::ensure_runtime_directories, which resolves them from the
# code location (/app) rather than the working directory -- so they are
# correct regardless of where the process is started from.
RUN mkdir -p /app/storage/uploads /app/storage/processed /app/logs /app/reports /models \
    && chown -R app:app /app/storage /app/logs /app/reports /models

USER app

EXPOSE 8000

# Liveness only. GET /health never touches Redis or Qdrant by design
# (app/api/health.py), so a transient dependency outage cannot cause Docker to
# kill an otherwise healthy container -- dependency state belongs in
# /system/health, which is reported, not acted on.
#
# urllib from the already-present interpreter avoids adding curl/wget to the
# runtime image for the sole purpose of probing it.
#
# start-period is generous because the API imports torch and transformers at
# startup; that is slow on a cold container and must not count as a failure.
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"]

# tini as PID 1 reaps zombies and, critically, forwards SIGTERM to the child.
# Without an init, PID 1 in a container ignores signals that have no explicit
# handler installed, which is what turns `docker compose down` into a 10-second
# wait followed by SIGKILL. Both roles handle SIGTERM properly once they
# actually receive it: uvicorn drains in-flight requests, and
# scripts/run_workers.py lets the current job finish before exiting.
ENTRYPOINT ["/usr/bin/tini", "--"]

# Default role: the API. Exec form (no shell), so the signal tini forwards
# reaches uvicorn itself rather than an intermediate /bin/sh.
#
# No --reload (that is a development concern, wired up in the dev compose
# override) and no --workers: horizontal scaling is the orchestrator's job,
# which is how this maps onto ECS task count later.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

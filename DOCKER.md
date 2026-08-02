# Docker

Everything needed to run the complete platform — frontend, API, worker, Redis and
Qdrant — with only Git and Docker installed on the host.

## Table of contents

- [Quick start](#quick-start)
- [Architecture](#architecture)
- [Images](#images)
- [Profiles](#profiles)
- [Configuration](#configuration)
- [Volumes and persistence](#volumes-and-persistence)
- [Health checks](#health-checks)
- [Troubleshooting](#troubleshooting)
- [Design decisions](#design-decisions)

---

## Quick start

```bash
git clone https://github.com/Vikas9892/product_intelligence.git
cd product_intelligence
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Open <http://localhost:3000>.

No `.env` file is required — every setting has a working default, and the two that must
differ inside containers (the Redis and Qdrant URLs) are set in `docker-compose.yml`.

The first build installs PyTorch and builds the Next.js bundle. The first *upload* then
downloads CLIP (~600 MB) and BGE (~130 MB) into the `model_cache` volume, so that one job
takes minutes while later ones take seconds. Measured cold: 215s for the first job, 18s
for subsequent ones.

---

## Architecture

```
                        host :3000            host :8000
                             │                     │
┌────────────────────────────┼─────────────────────┼──────────────────┐
│  network: app (bridge)     ▼                     ▼                  │
│                     ┌────────────┐        ┌────────────┐            │
│                     │  frontend  │───────▶│    api     │            │
│                     │  Next.js   │  proxy │  FastAPI   │            │
│                     │   :3000    │        │   :8000    │            │
│                     └────────────┘        └─────┬──────┘            │
│                                                 │                   │
│                     ┌────────────┐              │                   │
│                     │   worker   │              │                   │
│                     │  pipeline  │              │                   │
│                     └─────┬──────┘              │                   │
│                           │                     │                   │
│              ┌────────────┴──────┬──────────────┴────┐              │
│              ▼                   ▼                   ▼              │
│        ┌──────────┐        ┌──────────┐                             │
│        │  redis   │        │  qdrant  │                             │
│        │  :6379   │        │  :6333   │                             │
│        └──────────┘        └──────────┘                             │
│         not published       not published                           │
└─────────────────────────────────────────────────────────────────────┘
```

The browser only ever talks to the frontend's origin. API calls are proxied server-side
from the frontend container to `http://api:8000`, so CORS never applies and no backend URL
is exposed to the browser.

Redis and Qdrant are **not** published to the host in the production-like profile — only
the dev profile publishes them, for host tooling.

---

## Images

| Image | Roles | Size | Base |
|---|---|---|---|
| `product-intelligence-backend` | `api` **and** `worker` | 2.06 GB | `python:3.12-slim-bookworm` |
| `product-intelligence-frontend` | `frontend` | 408 MB | `node:20-bookworm-slim` |

The backend is **one image running two roles**, chosen by the command:

```
api     uvicorn app.main:app          (the image default)
worker  python scripts/run_workers.py
```

Both roles need the identical dependency closure, so a second image would mean
downloading PyTorch twice and keeping two artifacts in sync for no benefit. This maps
directly onto ECS later: one ECR image, two services.

Both images run as non-root (uid/gid 10001) with `tini` as PID 1.

---

## Profiles

| | Development | Production-like |
|---|---|---|
| Command | `make up-dev` | `make up-prod` |
| Source | bind-mounted | baked into the image |
| Reload | yes (API + Next dev) | no |
| Redis/Qdrant on host | published | internal only |
| Environment | `local`, debug on | `staging`, debug off |
| Logging | DEBUG | INFO |

```bash
# development
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build

# production-like
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

`docker-compose.yml` alone is the shared base and is not intended to be run by itself.
Both overlays only ever *add* to it, so the two environments cannot drift apart.

### Host-based development still works

To run the API and worker on the host with only the datastores in Docker:

```bash
make services-up   # starts only redis + qdrant, with host ports published
make run           # uvicorn on the host
make worker        # worker on the host
```

---

## Configuration

Configuration is injected at runtime. **No `.env` file is ever copied into an image**, and
no secret appears in any committed file.

Set real values in `backend/.env` (gitignored). `docker-compose.yml` wires it in with
`required: false`, so a fresh clone works without one:

```bash
cp backend/.env.example backend/.env
```

### Variables that matter in containers

| Variable | Default in Compose | Why |
|---|---|---|
| `ASYNC_PIPELINE__REDIS_URL` | `redis://redis:6379/0` | Service DNS. `localhost` would mean the container itself. |
| `VECTOR_STORE__URL` | `http://qdrant:6333` | Same. |
| `BACKEND_ORIGIN` | `http://api:8000` | Where the frontend proxies API calls. |
| `HF_HOME` | `/models` | Model cache location, on a named volume. |
| `SECURITY__SECRET_KEY` | *(unset)* | Required for any real deployment. Generate with `python -c "import secrets; print(secrets.token_urlsafe(32))"`. |

### Port overrides

| Variable | Default |
|---|---|
| `FRONTEND_PORT` | 3000 |
| `API_PORT` | 8000 |
| `REDIS_PORT` | 6379 *(dev only)* |
| `QDRANT_HTTP_PORT` | 6333 *(dev only)* |
| `QDRANT_GRPC_PORT` | 6334 *(dev only)* |

```bash
FRONTEND_PORT=3100 make up-prod
```

---

## Volumes and persistence

| Volume | Mounted at | Holds | Survives `down` |
|---|---|---|---|
| `redis_data` | `/data` | Products, jobs, cache, analytics, tenants | yes |
| `qdrant_storage` | `/qdrant/storage` | Image (512-d) and text (384-d) vectors | yes |
| `app_storage` | `/app/storage` | Uploaded and processed images | yes |
| `model_cache` | `/models` | CLIP and BGE weights (~1.3 GB) | yes |

`app_storage` is **shared between `api` and `worker`, and must be.** The API writes the
uploaded file to disk and enqueues a job carrying its *path*; the worker then opens that
path. Without the shared volume every job would fail on a missing file — and it would fail
at the worker, so the API would still have returned a cheerful `202`.

```bash
make down    # stops everything, keeps all four volumes
make reset   # DESTRUCTIVE: deletes all four, including uploads and the model cache
```

> [!WARNING]
> `make reset` erases uploaded images and every product record. The next start
> re-downloads ~730 MB of model weights.

---

## Health checks

| Service | Probe | Notes |
|---|---|---|
| `frontend` | `GET /` | Its own root, *not* the proxied `/health` — otherwise a backend blip would mark a healthy frontend unhealthy. |
| `api` | `GET /health` | Liveness only; never touches Redis or Qdrant by design. |
| `redis` | `redis-cli ping` | |
| `qdrant` | TCP connect to 6333 | The image ships no curl or wget. |
| `worker` | *(none)* | Serves no traffic and opens no socket. |

Startup is health-aware: the frontend waits for the API to be healthy, and the API and
worker both wait for Redis and Qdrant. Typical warm start is ~41s to all-healthy.

Dependency state (as opposed to liveness) is reported at `GET /system/health`:

```json
{ "redis": "healthy", "qdrant": "healthy", "workers": 4, "queue_depth": 0, "active_models": 3 }
```

---

## Troubleshooting

**Port already in use.** Something else on the host owns the port. Override it:
`FRONTEND_PORT=3100 make up-prod`.

**Worker shows `unhealthy`.** It should show no health status at all. If it reports
unhealthy, the `healthcheck: disable: true` on the worker service has been lost — the
worker inherits the image's HTTP probe against a port it never opens.

**First job takes minutes.** Expected: CLIP and BGE are downloading. Watch with
`docker compose logs -f worker`. Only the first job pays this.

**Frontend can't reach the API.** Check the entrypoint substituted the origin:

```bash
docker compose logs frontend | grep "backend origin"
# entrypoint: backend origin set to http://api:8000
```

**Changes not picked up.** `make up-dev` mounts source; `make up-prod` bakes it in and
needs `--build`.

---

## Design decisions

**CPU-only PyTorch on Linux.** On Linux, PyPI's `torch` declares hard dependencies on the
entire CUDA runtime — roughly 5–7 GB — none of which is reachable from a CPU-only
container. `backend/pyproject.toml` points `torch` at PyTorch's CPU index behind a
`sys_platform == 'linux'` marker, which is what makes the image 2.06 GB instead. Windows
and macOS development resolves from PyPI exactly as before.

**The frontend's backend origin is substituted at container start.** Next evaluates
`rewrites()` at *build* time and serializes the destination into `server.js` and two
manifests; the standalone server never re-reads `next.config.ts`. The image is therefore
built against a sentinel on the reserved `.invalid` TLD, and
`frontend/docker-entrypoint.sh` rewrites it at startup — so one image works in every
environment. A failed substitution fails loudly with a DNS error rather than quietly
reaching a real host.

**`staging`, not `production`.** The backend refuses to boot in `production` unless
`database.url` is non-SQLite — but the platform has no relational database at all
(`settings.database` is referenced nowhere outside a docstring; Redis is the datastore).
Selecting `production` would mean inventing a Postgres URL that nothing connects to.
Everything that check protects — debug off, no wildcard trusted hosts — is set explicitly
instead.

**No Nginx, no PostgreSQL.** Next.js already serves the same-origin API proxy, so nothing
needs a reverse proxy in front of it, and the application has no relational database to
run.

---

## AWS mapping (Stage 10+)

```
product-intelligence-backend  ──▶ ECR ──┬──▶ ECS service: api     (uvicorn)
                                        └──▶ ECS service: worker  (run_workers.py)

product-intelligence-frontend ──▶ ECR ─────▶ ECS service: frontend
```

The pieces that make this work are already in place: one backend artifact with a
command-selected role, runtime-injected configuration with nothing baked in, non-root
containers, health endpoints suitable for target-group checks, and service-DNS addressing
that maps onto ECS Service Connect. `app_storage` is the one thing needing attention — a
shared filesystem between the API and worker tasks means EFS, or moving uploads to S3.

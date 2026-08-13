---
name: run-app
description: Launch and drive the Product Intelligence stack — Next.js frontend, FastAPI backend, and the Redis/Qdrant backing services — then verify a change in a real browser. Use when asked to run, start, or screenshot the app, or to confirm something works outside the test suite.
---

# Running the Product Intelligence stack

Four processes, each independently useful. Start only as deep as the
change you are verifying needs.

| Layer | Needed for | Cost |
|---|---|---|
| Frontend only | UI shell, routing, layout, empty/error states | seconds |
| \+ Backend | search, products, system health | seconds |
| \+ Redis/Qdrant | dashboard metrics, pipeline activity | needs Docker |
| \+ Worker pool | **upload / ingest** — nothing else | seconds |

**The worker is a separate OS process and is easy to forget.** See
[§4](#4-worker-pool); it is the single most common cause of a
"broken" app here.

## 1. Frontend

```bash
cd frontend && npm run dev
```

Next.js 15 with Turbopack. **No `.env.local` is required** — every value
has a safe default in `src/config/env.ts`, so an absent env file is a
valid configuration.

Two things that look like failures but aren't:

- **Port 3000 is often already taken** on this machine by a stray `node`
  process that holds the socket without answering HTTP. Next.js prints
  `Port 3000 is in use ... using available port 3001 instead` and moves
  on. Read the actual port out of the startup banner; don't assume 3000.
  Curling the stray listener hangs forever — always pass `--max-time`.
- **The first request to any route takes ~20s** while Turbopack compiles
  it on demand. Poll the port, don't `sleep`. Subsequent loads are fast.

The browser always calls the frontend's own origin. Next rewrites
`/api/v1/*` to `BACKEND_ORIGIN` (default `http://localhost:8000`)
server-side, so backend CORS stays off. That means **a backend failure
surfaces as a 500 from port 3001**, not as a CORS error.

## 2. Backend

```bash
uv run --directory backend uvicorn app.main:app --host 127.0.0.1 --port 8000
```

This is `make run` with the host narrowed — the Makefile binds
`0.0.0.0`, which on Windows triggers a firewall prompt for no benefit
when the frontend proxy is on the same host.

`backend/.env` is already present and points `DATABASE__URL` at
SQLite (`./storage/app.db`), so **no Postgres and no Docker are needed**
just to serve the API. Confirm with:

```bash
curl -s --max-time 20 http://127.0.0.1:8000/health
```

## 3. Redis + Qdrant

Only these two need Docker. Docker Desktop must be running first —
`docker info` fails with a named-pipe error when it isn't.

```bash
make services-up     # docker compose ... up -d --wait redis qdrant
make services-down   # stops them; named volumes and data are kept
```

Without them the app still runs, and the failure is well-scoped and
legible rather than fatal:

- `/system` and the Dashboard **System** card render fine, showing
  `redis unhealthy` / `qdrant unhealthy`
- The Dashboard **metrics** and **pipeline activity** cards show
  "Couldn't load ..." with a Try again button; the backend logs
  `redis.exceptions.TimeoutError: Timeout connecting to server`
- Text search still works

So: seeing exactly those two cards fail means the backing services are
down, not that the frontend or backend is broken.

## 4. Worker pool

```bash
uv run --directory backend python scripts/run_workers.py   # = make worker
```

**`uvicorn app.main:app` never runs `WorkerManager`** — `run_workers.py`
says so in its own docstring, and the architecture diagram draws the
worker as a box separate from the Upload API. Starting the backend does
*not* start the worker. Nothing in the UI tells you it is missing.

Without it, the upload endpoint still accepts the file and enqueues the
job — it returns `202 Accepted`, so the frontend has no error to show.
The job then sits in Redis with nothing to consume it, and the UI parks
on **step 1 Queued at 0%** forever.

That symptom is worth recognizing precisely, because it looks like a
frontend bug and is not:

| Observation | Meaning |
|---|---|
| Stuck at Queued, 0%, no error, no failed request | worker not running |
| `queue_depth` climbing in `/api/v1/system/health` | worker not running |
| `/api/v1/jobs/dead-letter` empty while stuck | job was never picked up, not failed |
| Stuck at Processing, then dead-letter grows | worker *is* running; a pipeline stage is failing |

Confirm with:

```bash
curl -s --max-time 20 http://127.0.0.1:8000/api/v1/system/health
```

`workers: 4` there is configured concurrency, **not** proof a worker
process exists — that field reads the same whether or not the pool is
running. `queue_depth` is the field that actually tells you.

Starting the worker drains whatever has piled up, so a queue that was
stuck clears on its own without re-uploading.

## Driving it in a browser

`chromium-cli` is not installed here, and the Claude-in-Chrome extension
is frequently not connected. Don't reach for either. Playwright's
Chromium **is** already installed, so use `scripts/drive.js` in this
skill directory:

```bash
cd frontend && node .claude/skills/run-app/scripts/drive.js
```

It navigates the Dashboard and AI Search, submits a real query,
screenshots each step, and prints every response with status >= 400.
Point it at another port with `BASE_URL=http://localhost:3000`.

Add `--upload` to also exercise the worker pipeline end to end — it
uploads a sample image, waits for the redirect to `/products/<id>`, and
fails loudly if the job never completes. That flag writes a real product
to the catalog, which is why it is opt-in.

Two gotchas baked into that script, worth knowing if you write your own:

- **Require Playwright by absolute path.** Node resolves modules
  relative to the *script file*, not the cwd. A driver living outside
  `frontend/` cannot `require('@playwright/test')` even when run from
  `frontend/` — it must point into `frontend/node_modules`.
- **The search box has no `type` attribute**, so `input[type="text"]`
  and `input[type="search"]` both miss it. Target it by placeholder:
  `getByPlaceholder(/Describe the product/i)`.

Always look at the screenshot and the failed-request list before calling
a run successful — the shell renders perfectly well while every data
fetch behind it 500s.

## Routes worth driving

`/` dashboard, `/upload`, `/search`, `/duplicates`, `/recommendations`,
`/pricing`, `/analytics`, `/models`, `/enterprise`, `/system`,
`/products/[id]`.

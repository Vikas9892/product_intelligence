# Deploying

Two supported targets for the backend. The frontend goes to Vercel either way.

| | Free route | Paid route |
|---|---|---|
| Frontend | Vercel Hobby — $0 | Vercel Hobby — $0 |
| API + worker | Hugging Face Space, 2 vCPU / 16 GB — $0 | Render Standard, 2 GB — ~$25/mo |
| Redis | in-container, ephemeral — $0 | Render Key Value Starter — ~$10/mo |
| Qdrant | Qdrant Cloud free, 1 GB — $0 | same — $0 |
| Uploaded images | lost on restart | persistent disk — ~$2.50/mo |
| **Total** | **$0** | **~$38/mo** |

The free route is the default and is described first. Its one real
compromise is that uploaded image *files* do not survive a Space restart —
the product records themselves do, because they live in Qdrant.

> **Why not Render's free tier?** It is 512 MB. This backend loads PyTorch
> plus CLIP (~600 MB), BGE (~130 MB) and a cross-encoder, twice — once per
> child process. It cannot fit, at any tier below Standard.

---

# Free route: Hugging Face Spaces + Vercel

## 1. Qdrant Cloud

The product catalog lives here. There is **no SQL database in this project** —
products are stored as Qdrant payloads — so this cluster is the system of
record and is the one thing that must persist.

1. Create a free 1 GB cluster at <https://cloud.qdrant.io>
2. Copy the cluster URL (include the port: `https://….cloud.qdrant.io:6333`)
3. Create an API key and copy it — it is shown once

Collections (`product_images`, `product_text`) are created on first use.

## 2. Create the Space

1. <https://huggingface.co/new-space>
2. **SDK: Docker**, template **Blank**. Hardware: **CPU basic** (free).
3. Note the resulting URL — `https://<owner>-<space>.hf.space`. You need it
   twice below.

## 3. Push the backend to it

A Space is a git repo, and it expects the `Dockerfile` at its **root**. This
repo keeps it in `backend/`, so push that subdirectory as the Space root:

```bash
git remote add hf https://huggingface.co/spaces/<owner>/<space>
git subtree push --prefix backend hf main
```

`backend/README.md` already carries the Hugging Face front matter that
configures the Space, so nothing else needs adding. Re-run the same
`subtree push` to deploy later changes.

If the push is rejected, authenticate with a write token from
<https://huggingface.co/settings/tokens> (use it as the password).

## 4. Set the Space variables

**Settings → Variables and secrets.** Use *Secrets* for the two credentials
and *Variables* for the rest.

| Name | Value | Kind |
|---|---|---|
| `VECTOR_STORE__URL` | your Qdrant cluster URL | secret |
| `VECTOR_STORE__API_KEY` | your Qdrant API key | secret |
| `SECURITY__SECRET_KEY` | `python -c "import secrets; print(secrets.token_urlsafe(32))"` | secret |
| `START_EMBEDDED_REDIS` | `1` | variable |
| `APPLICATION__TRUSTED_HOSTS` | `["<owner>-<space>.hf.space"]` | variable |
| `APPLICATION__ENVIRONMENT` | `staging` | variable |
| `APPLICATION__DEBUG` | `false` | variable |
| `ASYNC_PIPELINE__WORKER_CONCURRENCY` | `2` | variable |
| `PORT` | `8000` | variable |

Notes on the non-obvious ones:

- **`START_EMBEDDED_REDIS=1`** runs Redis as a third child inside the
  container. A Space has no managed Redis, and the external free tiers meter
  commands — this queue polls with a non-blocking `LPOP` once a second per
  worker loop, roughly 8 commands/second while completely idle, which burns
  Upstash's 500,000-per-month allowance in about 17 hours of doing nothing.
  `ASYNC_PIPELINE__REDIS_URL` is left unset because its default,
  `redis://localhost:6379/0`, is already correct for this.
- **`APPLICATION__TRUSTED_HOSTS`** must be a JSON array naming the Space's
  real hostname. `TrustedHostMiddleware` is the outermost middleware, so a
  mismatch rejects every request with 400 before it reaches a route.
- **`PORT=8000`** pins uvicorn to the same port as `app_port` in
  `backend/README.md`'s front matter. Setting both removes any doubt about
  which port the platform routes to.
- **`APPLICATION__ENVIRONMENT=staging`**, not `production` — see
  [Why staging](#why-staging).

Saving these rebuilds the Space. First build is slow (PyTorch), and first
boot downloads ~730 MB of model weights.

## 5. Vercel

1. <https://vercel.com/new> → import this repo
2. **Root Directory → `frontend`** — it is a monorepo; without this Vercel
   builds the wrong thing
3. Environment variable: `BACKEND_ORIGIN` = `https://<owner>-<space>.hf.space`
   (no trailing slash)
4. Deploy

That one variable is the whole integration. `frontend/next.config.ts`
rewrites `/api/v1/*`, `/health`, `/ready` and `/version` to it **server-side**,
so the browser only ever talks to the Vercel origin. Two consequences:

- **CORS is never configured.** Requests reach the backend from Vercel's
  server, not a browser, so they are not cross-origin.
- **A backend failure appears as a 500 from your Vercel domain**, not as a
  CORS error. If the shell renders but every card fails, read the Space
  logs, not Vercel's.

## 6. Verify

```bash
curl https://<owner>-<space>.hf.space/health
curl https://<owner>-<space>.hf.space/api/v1/system/health
```

The second should report `redis: healthy` and `qdrant: healthy`. Then load
the Vercel URL and confirm the Dashboard **System** card agrees.

Then **upload an image**. That is the only step that proves the worker runs:
`workers: 4` in the health payload is configured concurrency and reads the
same whether or not a worker process exists. `queue_depth` climbing while
nothing completes is what indicates a dead worker.

```bash
BASE_URL=https://your-app.vercel.app node .claude/skills/run-app/scripts/drive.js --upload
```

## What to expect on the free Space

- **It sleeps after 48 h of inactivity** and cold-starts on the next request.
  Cold start is slow: PyTorch import plus a re-download of model weights,
  since the disk is ephemeral.
- **Uploaded image files do not survive a restart.** The product row, its
  vectors, attributes and price all live in Qdrant and do survive — but
  `GET /products/{id}/image` will 404 for anything uploaded before the last
  restart. The $5/mo persistent-storage add-on removes this; so does the
  paid Render route.
- **Redis resets with the container**, so queued jobs, analytics counters
  and enterprise records reset too. Consistent with the above: a queued job
  would have referenced an image that is also gone.

---

# Paid route: Render + Vercel

`render.yaml` at the repo root declares both services. Render → **New →
Blueprint** → select this repo; it prompts for `VECTOR_STORE__URL`,
`VECTOR_STORE__API_KEY` and `APPLICATION__TRUSTED_HOSTS`, and generates
`SECURITY__SECRET_KEY` itself. Then do the Vercel step above, pointing
`BACKEND_ORIGIN` at the Render hostname.

Blueprints are not themselves a paid feature — the cost is the `standard`
instance and `starter` Key Value the file declares.

Two Render-specific notes:

- **The API and worker share one service.** This is forced: the API writes
  an upload, the worker reads that exact path, and the API serves it back. A
  Render disk is reachable by exactly one service and cannot be mounted into
  a second, so splitting the roles would hand the worker an empty directory.
  `backend/scripts/start_all.py` documents the trade.
- **Watch the first boot for a permissions error.** The image runs as uid
  10001 and writes under the mounted disk. If Render mounts it root-owned,
  expect `PermissionError` / `Errno 13`. The fix is to chown the mount at
  startup, or drop the `USER app` line from `backend/Dockerfile` — the
  latter trades a real security property for convenience.

---

## Why staging

`APPLICATION__ENVIRONMENT` is `staging`, not `production`, on both routes.
This matches `docker-compose.prod.yml`'s existing reasoning:
`Settings._validate_production_safety` refuses to boot in `production`
unless `DATABASE__URL` is non-SQLite, but this project has no relational
database at all — `settings.database` is referenced nowhere outside a
docstring. Choosing `production` would mean inventing a Postgres URL that
nothing connects to purely to satisfy a validator. Everything that
validator protects — secret key, debug off, non-wildcard trusted hosts — is
set explicitly instead.

## Sources

- [Hugging Face Spaces overview](https://huggingface.co/docs/hub/en/spaces-overview)
- [Spaces storage is ephemeral by default](https://huggingface.co/docs/hub/spaces-storage)
- [Upstash Redis pricing (500k commands/month free)](https://upstash.com/pricing/redis)
- [Render free tier limits](https://render.com/docs/free)
- [Render persistent disks — one service, one instance](https://render.com/docs/disks)
- [`output: standalone` is unnecessary on Vercel](https://github.com/vercel/next.js/discussions/84940)

# Deploying

Two supported routes.

| | Single VM (free) | Managed (paid) |
|---|---|---|
| Everything | one Oracle Always Free VM — **$0** | Render + Vercel — **~$38/mo** |
| Persistence | full: named volumes on the VM | full: Render disk + Qdrant Cloud |
| Effort | you administer one box | click-to-deploy |

The free route is described first and is the default.

> **Why not Hugging Face Spaces?** As of mid-2026 the **Docker SDK is a paid
> feature**, requiring PRO ($9/mo) on personal accounts. Only Static Spaces
> remain free, and this backend cannot run as one.
>
> **Why not Render's free tier?** It is 512 MB. This backend loads PyTorch
> plus CLIP (~600 MB), BGE (~130 MB) and a cross-encoder — twice, once per
> child process. It cannot fit below Standard.

---

# Free route: one Oracle Always Free VM

Everything runs on a single machine with `docker compose`: frontend, API,
worker, Redis and Qdrant. There are **no external services** — no Qdrant
Cloud, no managed Redis, no Vercel. Nothing is metered and nothing expires.

This works because `docker-compose.yml` already models the whole stack, and
because Oracle's Always Free tier is unusually generous: an Ampere A1 ARM
instance with up to 4 OCPU and **24 GB RAM**, free indefinitely.

Only one port is exposed. Caddy terminates TLS and proxies to the frontend;
the frontend re-proxies `/api/v1/*` to the API over the private Docker
network. The API, Redis and Qdrant are never reachable from the internet —
which matters, because in the default single-tenant configuration the API has
no authentication at all, so an open port would be an open catalog and an
open upload endpoint.

```
internet ──► :443 Caddy ──► frontend:3000 ──► api:8000 ──► redis:6379
                                                       └─► qdrant:6333
```

## 1. Create the VM

1. Sign up at <https://cloud.oracle.com>. A card is required for identity
   verification; Always Free resources are not charged.
2. **Compute → Instances → Create instance**
   - **Image:** Ubuntu 24.04
   - **Shape:** `VM.Standard.A1.Flex` (Ampere, ARM) — **4 OCPU, 24 GB**
   - Save the SSH public key it offers, or supply your own
3. Note the **public IPv4 address**.

> **Capacity.** `A1.Flex` is frequently "out of host capacity" in popular
> regions — this is the single most common blocker, and it is not something
> you can configure around. Retry, or pick a less busy region at signup.
> Do not fall back to the `E2.1.Micro` always-free shape: it is 1 GB and
> cannot run this.

ARM is fine here and needs no code changes. `qdrant`, `redis`, `caddy` and
`python:3.12-slim` are all multi-arch, and `backend/pyproject.toml` already
resolves torch from the PyTorch CPU index, which publishes a
`manylinux_2_28_aarch64` wheel for the pinned version — CPU-only, with none
of the CUDA packages PyPI's build would drag in.

## 2. Open the ports — both firewalls

Oracle has two, and **missing the second is the classic failure**: the
security list lets traffic reach the VM, then the VM's own iptables drops it,
and you get a silent timeout with healthy containers.

**a. Cloud firewall.** VCN → Security Lists → Default → **Add Ingress Rules**:

| Source | Protocol | Port |
|---|---|---|
| `0.0.0.0/0` | TCP | 80 |
| `0.0.0.0/0` | TCP | 443 |

**b. Host firewall.** Ubuntu images from Oracle ship iptables rules that drop
everything except SSH. SSH in and run:

```bash
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save
```

## 3. Install Docker

```bash
sudo apt-get update && sudo apt-get install -y ca-certificates curl git
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker $USER && newgrp docker
```

Verify `docker compose version` is **v2.24 or newer** — the overlay uses the
`!reset` tag. If it is older, see the note at the top of
`deploy/oracle/docker-compose.oracle.yml`.

## 4. Get a hostname

Caddy needs a real hostname to obtain a certificate; Let's Encrypt does not
issue for bare IPs. A free subdomain is enough — create one at
<https://www.duckdns.org> and point it at the VM's public IP.

To skip TLS for a first smoke test, set `SITE_ADDRESS=:80` in the next step
and browse to the IP directly. Don't leave it there: every upload and search
would cross the internet unencrypted.

## 5. Configure and start

```bash
git clone https://github.com/Vikas9892/product_intelligence.git
cd product_intelligence

# Secrets live here; the file is gitignored and read by docker-compose.yml.
cat > backend/.env <<EOF
SECURITY__SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
EOF

# Your hostname, read by the overlay.
echo "SITE_ADDRESS=product-intel.duckdns.org" > .env

docker compose \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  -f deploy/oracle/docker-compose.oracle.yml \
  up -d --build
```

The first build compiles the backend image and installs PyTorch — expect
10–20 minutes on 4 ARM cores. First boot then downloads ~730 MB of model
weights into the `model_cache` volume, once for the whole stack.

Watch it come up:

```bash
docker compose ps
docker compose logs -f api worker
```

All five services should reach `healthy` except `worker`, which reports no
health status by design — it serves no port, so there is nothing to probe.

## 6. Verify

```bash
curl https://product-intel.duckdns.org/health
curl https://product-intel.duckdns.org/api/v1/system/health
```

The second should report `redis: healthy` and `qdrant: healthy`. Then open
the site and **upload an image** — the only step that proves the worker runs.
`workers: 4` in the health payload is configured concurrency and reads the
same whether or not a worker process exists; `queue_depth` climbing while
nothing completes is what indicates a dead worker.

```bash
BASE_URL=https://product-intel.duckdns.org \
  node .claude/skills/run-app/scripts/drive.js --upload
```

## Operating it

**Updating.** `git pull && docker compose … up -d --build`. Named volumes
(`app_storage`, `model_cache`, `redis_data`, `qdrant_storage`, `caddy_data`)
survive, so uploads, models, the catalog and your certificate all persist.

**Backups.** Everything durable is in those volumes. Redis is this platform's
primary datastore — it holds the queue, job and product state, analytics and
tenant data — and Qdrant holds the vectors, so back up `redis_data` and
`qdrant_storage` together or the two will disagree.

**Certificates** renew automatically. Keep port 80 open: the ACME HTTP-01
challenge is served on it, so closing it breaks renewal about 60 days later,
long after you have stopped thinking about it.

**Cost control.** Staying within Always Free means one A1 instance totalling
≤4 OCPU / 24 GB and ≤200 GB of block storage. Exceeding it starts billing.

## Optionally keep Vercel

Not needed — the VM serves the frontend. If you want Vercel's CDN and
preview deploys anyway, import the repo with Root Directory `frontend` and
set `BACKEND_ORIGIN` to your VM's HTTPS URL. That requires the API to be
publicly reachable, so you would drop the `api: ports: !reset []` block and
add its port to both firewalls — re-exposing an unauthenticated API. Prefer
the VM-only arrangement unless you specifically need the CDN.

---

# Paid route: Render + Vercel

`render.yaml` declares both services. Render → **New → Blueprint** → select
this repo; it prompts for `VECTOR_STORE__URL`, `VECTOR_STORE__API_KEY` and
`APPLICATION__TRUSTED_HOSTS`, and generates `SECURITY__SECRET_KEY` itself.
Then import the repo on Vercel with Root Directory `frontend` and
`BACKEND_ORIGIN` set to the Render hostname.

Blueprints are not themselves a paid feature — the cost is the `standard`
instance and `starter` Key Value the file declares.

- **The API and worker share one service.** Forced, not chosen: the API
  writes an upload, the worker reads that exact path, and the API serves it
  back. A Render disk is reachable by exactly one service and cannot be
  mounted into a second. `backend/scripts/start_all.py` documents the trade.
- **`APPLICATION__TRUSTED_HOSTS` must name the real hostname.**
  `TrustedHostMiddleware` is outermost, so a mismatch returns 400 for every
  request including Render's health check, failing the deploy for a reason
  that looks unrelated.
- **Watch the first boot for a permissions error.** The image runs as uid
  10001 and writes under the mounted disk; if Render mounts it root-owned,
  expect `PermissionError` / `Errno 13`.

---

## Why staging

`APPLICATION__ENVIRONMENT` is `staging`, not `production`, on both routes —
the reasoning `docker-compose.prod.yml` already documents.
`Settings._validate_production_safety` refuses to boot in `production` unless
`DATABASE__URL` is non-SQLite, but this project has no relational database at
all: `settings.database` is referenced nowhere outside a docstring. Choosing
`production` would mean inventing a Postgres URL nothing connects to purely
to satisfy a validator. Everything that validator protects — secret key,
debug off, non-wildcard trusted hosts — is set explicitly instead.

## Sources

- [Oracle Cloud Always Free resources](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm)
- [Docker Spaces now require a paid plan](https://discuss.huggingface.co/t/docker-sdk-now-marked-as-paid-when-creating-a-new-space/177580)
- [Render free tier limits](https://render.com/docs/free)
- [Render persistent disks — one service, one instance](https://render.com/docs/disks)
- [Caddy automatic HTTPS](https://caddyserver.com/docs/automatic-https)

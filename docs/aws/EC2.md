# Deploying to AWS EC2

The route this project actually deploys on: **one `t4g.medium` instance running
the Compose stack, images pulled from Docker Hub, rolled by GitHub Actions.**

[ARCHITECTURE.md](./ARCHITECTURE.md) describes the ECS/Fargate design and
[COST.md](./COST.md) prices it at ~$115–125/month. That design is not deployed,
and the reason is in COST.md's own table: **ALB + NAT Gateway + ElastiCache is
~$61/month that bills whether or not anyone visits.** For a portfolio that is
idle most of the time, paying an always-on load balancer to front a service
nobody is calling is not a demonstration of production engineering — it is a
demonstration of not reading the bill. The ECS design stays as the documented
production-scale path; this is the one with a URL.

```
                         internet
                            │
                            ▼
                   EC2  t4g.medium (ARM64)
              security group: 22, 80, 443 only
                            │
                    :443  Caddy  ──── Let's Encrypt, auto-renewed
                            │
                    frontend:3000  (Next.js)
                            │  server-side proxy, /api/v1/*
                    api:8000  (FastAPI)  ────┐
                            │                │
                       redis:6379      qdrant:6333
                            │                │
                    worker  ────────────────-┘

  Docker network `app` — redis, qdrant and the API are never
  reachable from the internet. Only Caddy publishes ports.
```

**Everything below already exists in the repo.** The stack is
`docker-compose.yml`, the production profile is `docker-compose.prod.yml`, the
TLS entry point is `deploy/vm/docker-compose.vm.yml`, the Docker Hub images
come from `deploy/aws/docker-compose.hub.yml`, and the pipeline is
`.github/workflows/deploy.yml`. What follows is provisioning, not building.

---

## What it costs

List prices, **us-east-1, August 2026**, at 730 hours/month. Regions differ —
re-check in the [AWS Pricing Calculator](https://calculator.aws) before
committing, particularly if you pick `ap-south-1` for latency from India.

| Line | Rate | Monthly |
|---|---|---|
| `t4g.medium` on-demand | $0.0336 / hr | **$24.53** |
| EBS `gp3` root, 20 GB | $0.08 / GB-mo | **$1.60** |
| Public IPv4 address | $0.005 / hr | **$3.65** |
| Data transfer out | first 100 GB/mo free | **$0.00** |
| **Total** | | **≈ $29.78 / mo** |

Nothing else on the bill, and that is a design property rather than luck: the
instance sits in a **public subnet behind the internet gateway**, so there is
no NAT Gateway (~$32.85/mo — the single largest line in the ECS design). No
ALB, no Route 53, no ECR, no ElastiCache, no S3.

Against a Free Plan balance expiring **5 February 2027**, that is **~$167 to
the expiry date** — inside $200 of credits, outside $100. Two things are worth
knowing before you start:

- **The IPv4 address bills even while the instance is stopped.** Since February
  2024 every public IPv4 is charged hourly whether or not it is attached to a
  running instance. Stopping the box saves the $24.53, not the $3.65.
- **EBS bills while stopped too.** A stopped instance still costs **$5.25/month**
  in address plus volume. Only terminating the instance, deleting the volume and
  releasing the address stops that.

### The cheaper variant: Spot

Everything in this document works unchanged on a **Spot** instance, which is
the one lever that materially cuts the bill without taking the site down.
Graviton Spot typically clears at **~65–70% off** on-demand — check *Spot
Requests → Pricing History* for your region rather than trusting that range —
which puts the total near **$13/month**.

Two settings make it safe to use:

- **Persistent** request (not one-time), with **interruption behaviour =
  `stop`**, not `terminate`. The EBS root volume and every named volume survive,
  and AWS restarts the *same instance* when capacity returns — so the Elastic IP
  stays associated and no DNS changes.
- Nothing else is needed on the application side. Docker starts at boot via
  systemd, and every service in `docker-compose.yml` is already
  `restart: unless-stopped`, so the stack rebuilds itself without intervention.

The honest cost: an interruption gives 2 minutes' notice and the site is then
down for the 3–5 minutes a restart takes, at a time you do not choose and will
not be told about. For a portfolio link that is usually acceptable. Before a
scheduled interview, switch to on-demand for the week.

### Why `t4g.medium` and not something smaller

[ADR-001](./ADR-001-compute.md) measured the running stack: api **602 MiB**
with CLIP and BGE resident, worker **1.15 GiB** steady, qdrant 82 MiB, frontend
52 MiB. That is ~1.9 GB before Ubuntu's own ~400 MB, and before the worker
spikes — `ASYNC_PIPELINE__WORKER_CONCURRENCY` is 4 by default, so four image
decodes plus inference can run at once. A 2 GB `t4g.small` does not fit that
without swapping, and swap-thrashing during a live demo is the failure you
cannot talk your way out of.

ARM is not a compromise here. `backend/uv.lock` pins
`torch-2.13.0+cpu-cp312-cp312-manylinux_2_28_aarch64.whl` from the PyTorch CPU
index, and `qdrant`, `redis`, `caddy`, `python:3.12-slim-bookworm` and
`node:20-bookworm-slim` all publish arm64. Graviton is ~24% cheaper than the
equivalent `t3.medium` for identical capability.

---

## 1. Set the cost guardrail first

Before launching anything. A budget created after the fact does not alert you
about the week you have already paid for.

1. **Billing and Cost Management → Budgets → Create budget**
2. Template: **Monthly cost budget**. Amount: **$40** — above the ~$30 expected
   so normal running does not page you, low enough that a mistake does.
3. Alerts at **50% / 80% / 100%** of *actual*, plus one at **100% of
   forecasted** — the forecast alert is the one that warns you before the money
   is gone rather than after.
4. Email: your own address.

Then **Billing → Free Tier** to watch credit burn, and turn on **Cost Anomaly
Detection** (free) so an unexpected service appearing on the bill is surfaced
without you checking.

> Your account dashboard offers a credit for configuring a cost budget. Claim
> it while you are here.

A budget **alerts**; it does not **stop** anything. Nothing in AWS switches off
your instance when the number is hit. That is what the teardown section at the
bottom is for.

---

## 2. Launch the instance

**EC2 → Launch instance**

| Field | Value | Why |
|---|---|---|
| Name | `product-intelligence` | |
| AMI | **Ubuntu Server 24.04 LTS (64-bit ARM)** | The **ARM** variant. Selecting x86 here silently filters `t4g` out of the instance list, which is the usual cause of "I can't find t4g.medium". |
| Instance type | **`t4g.medium`** | 2 vCPU / 4 GB Graviton2 |
| Key pair | Create new, **ED25519**, name it `pi-deploy` | Downloads `pi-deploy.pem` **once**. Lost means terminate and relaunch. |
| Network | Default VPC, **Auto-assign public IP: Enable** | |
| Storage | **20 GB `gp3`** (not the default 8) | Peak usage is ~10 GB: Ubuntu ~2.5, two backend tags at 2.06 GB each during a deploy, two frontend tags, 1.3 GB of model weights, plus the Qdrant/Redis/upload volumes. 8 GB fills during the first pull; 20 leaves ~10 GB of headroom. |

**Security group** — create new, name `product-intelligence-sg`:

| Type | Port | Source | Why |
|---|---|---|---|
| SSH | 22 | `0.0.0.0/0` | See the note below |
| HTTP | 80 | `0.0.0.0/0` | **Not just a redirect** — the ACME HTTP-01 challenge is served here. Closing it breaks certificate *renewal* ~60 days later, long after you have stopped thinking about it. |
| HTTPS | 443 | `0.0.0.0/0` | |

> **On opening 22 to the world.** The instinct to lock SSH to your own IP is
> right, and it breaks the deploy: GitHub Actions runners come from a large,
> rotating address range, so a pinned source blocks your own pipeline. Open 22
> with **key-only authentication** (Ubuntu's AMI disables password auth by
> default — leave it that way) and accept it.
>
> The production-grade answer is **SSM Session Manager**: an IAM role on the
> instance, the SSM agent dialling out, and *no inbound SSH rule at all*. It is
> the better design and worth naming in an interview. It is also more moving
> parts than this deployment needs, and it is a deliberate, stated trade rather
> than an oversight.

### Elastic IP

**EC2 → Elastic IPs → Allocate**, then **Associate** it with the instance.

Without this, the public IP changes on every stop/start and your DNS record
goes stale — which looks exactly like an outage. The address costs the same
$3.65/month either way, so there is no reason not to.

---

## 3. Install Docker

SSH in (`ubuntu` is the default user on Ubuntu AMIs):

```bash
chmod 600 pi-deploy.pem
ssh -i pi-deploy.pem ubuntu@YOUR_ELASTIC_IP
```

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

Check `docker compose version` reports **v2.24 or newer** — the overlays use
the `!reset` tag, which older versions reject with a parse error.

Unlike the Oracle route in [DEPLOY.md](../DEPLOY.md), there is **no host
firewall step**. AWS's Ubuntu AMI ships with no iptables rules, so the security
group is the only gate. (Oracle's images drop everything but SSH locally, which
is why that document has a step this one does not.)

### Swap — recommended, not required

4 GB has ~2 GB of headroom over the measured steady state, but the worker's
spikes are the tail risk and the Linux OOM killer picks victims by memory
footprint, which here means the worker or the API. 2 GB of swap turns a kill
into a slowdown:

```bash
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

The `fstab` line is the part people forget; without it the swap is gone after
the first reboot.

---

## 4. Get a hostname

Caddy needs a real hostname — Let's Encrypt does not issue certificates for
bare IP addresses. A free subdomain is enough: create one at
<https://www.duckdns.org> and point it at your **Elastic IP**.

This is why the deployment needs no Route 53 (**$0.50/month per hosted zone**,
plus a registered domain). Buy a domain later if you want a nicer URL on your
resume; nothing below changes when you do.

Confirm DNS resolves *before* starting Caddy — a certificate request against a
name that does not yet point at the box counts against Let's Encrypt's rate
limit of **5 duplicate certificates per week**:

```bash
dig +short product-intel.duckdns.org   # must print your Elastic IP
```

---

## 5. Clone and configure

The instance holds the repository because the compose files and the Caddyfile
are read from disk — the *images* come from Docker Hub, but the configuration
that arranges them does not.

```bash
git clone https://github.com/Vikas9892/product_intelligence.git
cd product_intelligence

# Backend secrets. Gitignored, read by docker-compose.yml via env_file.
cat > backend/.env <<EOF
SECURITY__SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
EOF

# Read by the Caddy overlay and the Docker Hub overlay respectively.
cat > .env <<EOF
SITE_ADDRESS=product-intel.duckdns.org
DOCKERHUB_USER=your-dockerhub-username
EOF
```

Do **not** start anything yet — there is nothing on Docker Hub to pull. §6
builds and pushes the images, and its first run brings the stack up.

> If you want the site running before setting up CI, you can build on the
> instance instead — drop the `deploy/aws/docker-compose.hub.yml` overlay and
> use `up -d --build`. It works, and it takes 15+ minutes on two cores while
> competing with nothing else for them. Doing it once to see the stack live is
> reasonable; doing it on every deploy is what §6 exists to prevent.

---

## 6. Wire up CI/CD

`push to main → CI → build arm64 → Docker Hub → SSH → roll the stack`

### a. Docker Hub

Create two **public** repositories under your account:

- `product-intelligence-backend`
- `product-intelligence-frontend`

Public matters twice: unlimited public repositories on the free Docker Personal
plan, and **the EC2 instance never needs Docker Hub credentials** to pull. The
only place a token exists is GitHub's secret store.

Then **Account Settings → Personal access tokens → Generate**, scope
**Read & Write**. A token, not your password — scoped and individually
revocable.

### b. A dedicated deploy key

Generate a keypair used *only* by the pipeline, separate from the `.pem` you
log in with. A leaked CI secret should not also be your interactive access.

On your laptop:

```bash
ssh-keygen -t ed25519 -f pi-cicd -N "" -C "github-actions-deploy"
```

Install the public half on the instance:

```bash
ssh -i pi-deploy.pem ubuntu@YOUR_ELASTIC_IP \
  "cat >> ~/.ssh/authorized_keys" < pi-cicd.pub
```

Capture the host key for pinning — the workflow does **not** `ssh-keyscan` at
run time, because scanning trusts whatever answers on first connection, every
run, forever:

```bash
ssh-keyscan -t ed25519 YOUR_ELASTIC_IP
```

### c. GitHub secrets

**Settings → Secrets and variables → Actions → New repository secret**

| Secret | Value |
|---|---|
| `DOCKERHUB_USERNAME` | your Docker Hub account name |
| `DOCKERHUB_TOKEN` | the access token from (a) |
| `EC2_HOST` | your Elastic IP |
| `EC2_USER` | `ubuntu` |
| `EC2_SSH_KEY` | **entire** contents of `pi-cicd` — including the `-----BEGIN`/`-----END` lines |
| `EC2_KNOWN_HOSTS` | the `ssh-keyscan` output from (b) |
| `SITE_URL` | `https://product-intel.duckdns.org` |

### d. Fire it

`.github/workflows/deploy.yml` triggers on CI completing successfully on
`main`, and on manual dispatch. For the first run use **Actions → Deploy → Run
workflow** so you are not waiting on a commit.

This first run is also what starts the stack: it pulls the freshly pushed
images and brings all six containers up. Expect the *build* job to take
15–25 minutes the first time — the backend's torch layer is uncached — and
under 5 minutes afterwards. First boot then downloads ~730 MB of model weights
into the `model_cache` volume, once for the whole stack, which is why the
deploy job's health check polls for up to five minutes rather than checking
once.

Watch it from the instance if you want to see it happen:

```bash
docker compose ps
docker compose logs -f api worker
```

All services should reach `healthy` except `worker`, which reports no health
status **by design** — it serves no port, so there is nothing to probe.

It builds on `ubuntu-24.04-arm` — a **native** ARM runner, free on public
repositories. This is not a detail: cross-building an arm64 torch install under
QEMU on an x86 runner takes over half an hour and frequently times out.

Each image is tagged twice, with the commit SHA and with `latest`. The deploy
pins the SHA, so `docker compose ps --format '{{.Image}}'` on the box answers
"which commit is running?" — a question `latest` cannot answer, and the first
one you ask when a deploy misbehaves.

---

## 7. Verify

```bash
curl https://product-intel.duckdns.org/health
curl https://product-intel.duckdns.org/api/v1/system/health
```

The second must report `redis: healthy` and `qdrant: healthy`.

Then **upload an image through the UI** — the only step that proves the worker
is alive. `workers: 4` in the health payload is *configured* concurrency and
reads identically whether or not a worker process exists. A `queue_depth` that
climbs while nothing completes is the real signal of a dead worker.

```bash
BASE_URL=https://product-intel.duckdns.org \
  node .claude/skills/run-app/scripts/drive.js --upload
```

---

## Operating it

**Updating.** Push to `main`. That is the whole procedure. To roll back, re-run
an older successful Deploy run, or on the box set `IMAGE_TAG` to a previous SHA
and `up -d`.

**Backups.** Everything durable is in named volumes: `app_storage`,
`model_cache`, `redis_data`, `qdrant_storage`, `caddy_data`. **Redis is the
primary datastore** — queue, job and product state, analytics, tenants — and
Qdrant holds the vectors, so back the two up *together* or they will disagree
about which products exist. An EBS snapshot ($0.05/GB-month) captures the whole
disk consistently and is the simplest option.

**Certificates** renew automatically. Keep port 80 open.

**Disk.** `docker image prune` runs on every deploy, but check `df -h`
occasionally — a deploy briefly holds two backend tags at 2.06 GB each, and a
full disk surfaces as Qdrant refusing writes rather than as an obvious disk
error.

> Note the discrepancy with [COST.md](./COST.md)'s "~3.3 GB per backend tag":
> that figure is for [ADR-005](./ADR-005-model-delivery.md)'s baked-model image,
> which is an ECS decision and **is not implemented in `backend/Dockerfile`**.
> This route downloads models to the `model_cache` volume at first boot instead,
> so the image is the un-baked **2.06 GB**. Baking is the right call when task
> cold-start dominates, which on a VM that boots once it does not.

**What to watch on the bill.** The instance and the IPv4 address are ~99% of
it, and both are fixed. The line that can surprise you is **data transfer out**
past 100 GB/month, which a portfolio will not approach unless something is
scraping it.

---

## Turning it off

| Action | Stops billing for | Still billed | Recovery |
|---|---|---|---|
| `docker compose down` | nothing | everything | `up -d` |
| **Stop** the instance | compute (~$24.53) | EBS + IPv4 (~$5.25/mo) | Start it; ~3–5 min to serve traffic |
| **Terminate** + release the Elastic IP + delete the volume | everything | nothing | Rebuild from this document |

Terminating destroys the named volumes with the instance — catalog, vectors,
uploads and certificate. Snapshot first if any of it matters.

At the credit expiry on **5 February 2027**, decide deliberately. An instance
left running past that date bills a real card at ~$30/month, and the AWS
console will not ask you twice.

---

## Sources

- [EC2 on-demand pricing](https://aws.amazon.com/ec2/pricing/on-demand/)
- [EBS pricing](https://aws.amazon.com/ebs/pricing/)
- [Public IPv4 address charge](https://aws.amazon.com/blogs/aws/new-aws-public-ipv4-address-charge-public-ip-insights/)
- [AWS Budgets](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-managing-costs.html)
- [GitHub-hosted ARM runners](https://github.blog/news-insights/product-news/arm64-on-github-actions-powering-faster-more-efficient-build-systems/)
- [Caddy automatic HTTPS](https://caddyserver.com/docs/automatic-https)
- [Let's Encrypt rate limits](https://letsencrypt.org/docs/rate-limits/)

# ADR-001 — Compute platform

**Status:** Accepted (design only — nothing deployed)
**Date:** 2026-08-04
**Decides:** where the Next.js frontend, the FastAPI API and the AI worker run

---

## Context

Three processes, with genuinely different shapes:

| Process | Shape | Measured memory | Listener |
|---|---|---|---|
| `frontend` | Long-running Node server, request/response | 52 MiB | :3000 |
| `api` | Long-running ASGI server, **loads ML models on demand** | 602 MiB | :8000 |
| `worker` | Long-running queue consumer, heavy CPU inference | 1.15 GiB | none |

Two of these facts constrain the choice more than anything else.

**The frontend is not a static site.** `next.config.ts` sets `output: "standalone"` and
defines `rewrites()` that proxy `/api/v1/*` to the backend. It requires a running Node
process. Any option premised on "just put the build in S3" is disqualified before cost
enters the conversation.

**The worker has no HTTP surface.** It consumes from Redis and exits on SIGTERM. Any
platform whose unit of deployment is "a thing that answers HTTP requests" cannot run it.

---

## Options considered

### A. ECS Fargate for all three — **chosen**

One orchestration model, three services, no servers to patch. The backend image already
runs both API and worker roles by command, so ECS runs the same artifact as two task
definitions — which is what the Stage 8 single-image decision was designed to enable.

### B. App Runner for frontend + API, something else for the worker

App Runner is genuinely nice for the two HTTP services: TLS, autoscaling and deployments
come free, and it would remove the ALB line item.

It cannot run the worker. App Runner scales on request concurrency and has no
queue-consumer primitive; a service with no inbound requests scales to zero and stops
consuming. That forces the worker onto ECS anyway, leaving two compute paradigms, two
deployment mechanisms, two sets of IAM plumbing and a VPC connector to reach Redis and
Qdrant. The saving does not survive the split.

### C. ECS on EC2

Materially cheaper at sustained load — one `t4g.medium` could host all four containers for
roughly a quarter of the Fargate bill. The cost is AMI lifecycle, instance patching,
capacity providers, and bin-packing a 4 GB worker beside everything else.

For a workload at single-digit requests per minute, that is operational surface bought with
no operational need. It is, however, the correct answer at scale, and it is documented as
the scale-up lever in [COST.md](./COST.md).

### D. EC2 running Docker Compose directly

The cheapest credible option (~$12–15/month) and honestly a reasonable choice for a demo
that must stay cheap. Rejected as the *primary* design because it demonstrates none of the
production engineering this stage exists to show: no service isolation, no independent
scaling, no rolling deploys, no task-level IAM. Kept in [COST.md](./COST.md) as the
"portfolio is dormant" fallback.

### E. Lambda for the worker

Superficially attractive for bursty inference. Rejected on three concrete grounds: the
container image would be ~3.3 GB against a 10 GB limit but with cold-start unpacking
measured in tens of seconds; PyTorch cold starts are exactly what the model-baking decision
exists to avoid; and the 15-minute ceiling is uncomfortable next to a pipeline whose cold
path already measured 215 s. The worker is long-running by nature — it is a poor fit for a
function.

---

## Decision

**ECS Fargate for all three services**, in private subnets, behind one ALB.

Task sizing, derived from the measurements above with headroom for inference spikes rather
than guessed:

| Service | vCPU | Memory | Reasoning |
|---|---|---|---|
| `frontend` | 0.25 | 0.5 GB | 52 MiB measured; this is the smallest Fargate size |
| `api` | 0.5 | 2 GB | 602 MiB with CLIP and BGE resident; 2 GB leaves room for concurrent requests |
| `worker` | 1.0 | 4 GB | 1.15 GiB steady; inference and image decode spike well above that |
| `qdrant` | 0.5 | 1 GB | 82 MiB measured at current data volume |

Ephemeral storage: the included **20 GB** is enough. The baked models are 1.3 GB and
processed images are transient — no extra provisioning needed.

**The worker runs on Fargate Spot.** It is the single best Spot candidate in the system:
interruption-tolerant by construction, because a job interrupted mid-flight is redelivered
and retried by machinery that already exists and was verified in Stage 9. Spot is quoted at
up to 70% off on-demand, and the worker is the most expensive task — this is the largest
single cost reduction available without changing the architecture.

The API and frontend stay on-demand. They serve user traffic, and an interrupted API task
is a user-visible 5xx.

---

## Consequences

**Good**

- One deployment model, one set of IAM primitives, one log destination.
- Independent scaling: the worker scales on backlog, the API on request rate.
- No servers, AMIs or patching.
- The single-image, command-selected-role design carries over from Compose untouched — the
  ECS task definitions differ by one field.

**Bad, and accepted**

- Fargate costs roughly 2× equivalent EC2 capacity. Deliberate: bought with operational
  simplicity, and offset by Spot on the largest task and scale-to-zero on the worker.
- Each Fargate task pulls the full image; a ~3.3 GB backend image makes task startup slower
  than a 500 MB one. Quantified and accepted in [ADR-005](./ADR-005-model-delivery.md).
- Scaling the API out costs ~600 MB of resident models per task. The API is not a thin
  proxy, and pretending otherwise would produce undersized tasks.

---

## Revisit when

- Sustained load makes ECS on EC2 or Compute Savings Plans clearly cheaper.
- The API stops loading models (e.g. inference moves entirely behind the worker), at which
  point the API becomes small enough for App Runner to be reconsidered.

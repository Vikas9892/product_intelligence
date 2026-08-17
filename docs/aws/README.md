# AWS

Two documents describe two different things, and the distinction is the point.

**[EC2.md](./EC2.md) is what is deployed** — one `t4g.medium` running the
Compose stack, ~$30/month, images from Docker Hub, rolled by GitHub Actions.

**Everything else on this page is the ECS/Fargate design, which is not
deployed.** No ECS resources exist and no Terraform is written. It was designed
in full, costed at ~$115–125/month, and then declined for this deployment — the
reason is in [COST.md](./COST.md): ALB + NAT Gateway + ElastiCache is ~$61/month
that bills whether or not anyone visits, and a portfolio that is idle most of
the time should not be paying a load balancer to front traffic that is not
arriving.

Both are kept because the *comparison* is the engineering content. Designing
the production-scale architecture and then choosing the $30 one for a workload
that does not need it is the decision; deploying ECS to be able to say "ECS"
would be the opposite of it.

## Start here

| Document | What it answers |
|---|---|
| **[EC2.md](./EC2.md)** | **The deployed route.** Provisioning, cost guardrails, CI/CD, operating it, tearing it down |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | The ECS design in full: diagrams, scaling, observability, failure modes, environments, rejected alternatives |
| [SECURITY.md](./SECURITY.md) | What is internet-facing, security groups, IAM, secrets, TLS — and what the ECS design deliberately does not do |
| [COST.md](./COST.md) | Verified unit prices, derived monthly totals, and how to make it cheap when idle |

## Decisions

| ADR | Decision | Choice |
|---|---|---|
| [001](./ADR-001-compute.md) | Where the three services run | ECS Fargate; **Spot** for the worker |
| [002](./ADR-002-storage.md) | Replacing the shared `app_storage` volume | **S3** — and the refactor is 4 call sites |
| [003](./ADR-003-redis.md) | Redis, which is the system of record | ElastiCache `cache.t4g.micro` |
| [004](./ADR-004-qdrant.md) | Qdrant | Self-hosted on ECS Fargate + EBS, private |
| [005](./ADR-005-model-delivery.md) | Getting CLIP and BGE into a task | **Bake into the image** |

## The three findings that shaped everything

**The API/worker coupling is weaker than it looked.** They exchange `stored_filename` — a
generated opaque identifier, deliberately never a path — which each side joins to its own
configured directory. That is already S3's model, which is why
[ADR-002](./ADR-002-storage.md) costs four edited lines rather than a redesign.

**Redis is the system of record, not a cache.** Products, jobs, analytics and tenant data
all live there, with no relational database anywhere. That inverts the usual ElastiCache
trade-off and makes Redis the one component that cannot be scaled to zero between demos.

**Cold model loading is the dominant latency risk.** Measured 215 s for a first job versus
18 s warm, and it broke the Stage 9 smoke suite outright on a fresh deployment.
[ADR-005](./ADR-005-model-delivery.md) removes it from runtime entirely.

## Honest limitations

Recorded here rather than buried, because a design document that only lists strengths is
not useful:

- A **single NAT Gateway** — an AZ-level single point of failure for egress, taken for cost.
- A **single-node ElastiCache** — no automatic failover; recovery is a snapshot restore.
- A **single Qdrant task** — restarts are brief downtime for search, and the EBS volume makes
  it AZ-affine.
- The **enterprise auth layer stays off**, so the deployed API is unauthenticated and
  single-tenant. It must be enabled before this is exposed publicly with real data.
- Roughly **$61/month of the bill exists whether or not anyone visits** (ALB + NAT +
  ElastiCache). Scale-to-zero cannot reach it; only `terraform destroy` can.

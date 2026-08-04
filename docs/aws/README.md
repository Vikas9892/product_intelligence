# AWS architecture (design)

> **Nothing here is deployed.** No AWS resources exist, no Terraform is written, and no
> application code was changed to produce these documents. This is the design Stage 11 will
> implement.

## Start here

| Document | What it answers |
|---|---|
| **[ARCHITECTURE.md](./ARCHITECTURE.md)** | The whole design: diagrams, scaling, observability, failure modes, environments, rejected alternatives |
| [SECURITY.md](./SECURITY.md) | What is internet-facing, security groups, IAM, secrets, TLS — and what this design deliberately does not do |
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

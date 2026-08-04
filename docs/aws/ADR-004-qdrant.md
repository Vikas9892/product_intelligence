# ADR-004 — Qdrant

**Status:** Accepted (design only — nothing deployed)
**Date:** 2026-08-04
**Decides:** how the vector database runs in AWS

---

## Context

Qdrant holds two cosine collections, auto-created on first use:

| Collection | Dimensions | Source model |
|---|---|---|
| `product_images` | 512 | CLIP ViT-B/32 |
| `product_text` | 384 | BAAI/bge-small-en-v1.5 |

Measured storage after the demo catalog: **836 KB**. Measured memory: **82 MiB**.

Two constraints frame the options:

**Replacing Qdrant is out of scope.** `qdrant-client` is pinned to 1.18, the image is
pinned to `qdrant/qdrant:v1.18.1` to match, and the vector store is abstracted behind
`BaseVectorStore` with a working, tested implementation. Swapping to OpenSearch or Aurora
`pgvector` would be a substantial application change to use a different AWS logo. The stage
brief rules it out and the codebase agrees.

**Qdrant data is derived, not primary.** Vectors are regenerable from the S3 originals plus
the Redis product records. That materially lowers the durability bar compared with Redis —
losing Qdrant costs a reprocessing run, not a catalog.

---

## Options

### A. Qdrant Cloud (managed SaaS)

Attractive: managed backups, upgrades and monitoring, and a free tier that comfortably fits
836 KB.

Rejected on a constraint that is not negotiable. The stage brief states **"Redis and Qdrant
must NOT be publicly exposed."** Qdrant Cloud is an internet-facing endpoint secured by an
API key. Even with an allowlist, the vector store would sit outside the VPC, reachable from
the internet, with traffic leaving AWS and returning — which contradicts the network design
in [SECURITY.md](./SECURITY.md), where every datastore is private-subnet-only and reachable
solely from `api-sg` and `worker-sg`.

Secondary concerns, which would not have been decisive alone: a third-party dependency in
the availability story, egress charges, and a portfolio narrative that becomes "I signed up
for a SaaS" rather than "I ran a stateful service".

### B. Qdrant on EC2

Works and is cheap on a `t4g.small`. But it reintroduces exactly the instance lifecycle —
AMIs, patching, systemd, disk management — that choosing Fargate in
[ADR-001](./ADR-001-compute.md) deliberately avoided, for one small container.

### C. Qdrant on ECS Fargate with an attached EBS volume — **chosen**

One task, one persistent EBS volume, private subnets, reachable only from the API and
worker security groups.

ECS supports attaching an EBS volume to a Fargate task, which is what makes this viable
without EC2: the container gets real block storage that survives task replacement, without
anyone managing an instance.

---

## Decision

**Qdrant on ECS Fargate**, 0.5 vCPU / 1 GB, with a **20 GB gp3 EBS volume** mounted at
`/qdrant/storage`, in private subnets.

- **Desired count is exactly 1.** Not a scaling decision — a correctness one. A single EBS
  volume attaches to a single task, and running two Qdrant replicas against one volume
  would corrupt it. Horizontal scaling requires Qdrant's own clustering, which this data
  volume does not remotely justify.
- **Backups** via scheduled EBS snapshots (AWS Backup, daily, 7-day retention). Qdrant's
  native snapshot API is available as a second, application-level path.
- **Security group** accepts 6333 from `api-sg` and `worker-sg` only. No public ingress,
  no ALB target group, no internet route.
- **Service discovery** through ECS Service Connect or a Cloud Map private DNS name, so the
  application keeps addressing it as `http://qdrant:6333` — the same `VECTOR_STORE__URL`
  shape Compose uses today, so no configuration concept changes.

---

## Consequences

**Good**

- The vector store stays inside the VPC, satisfying the non-exposure constraint outright.
- Demonstrates running a **stateful service on ECS**, which is a more interesting engineering
  story than provisioning a SaaS.
- Consistent with the rest of the compute platform: same orchestrator, same logging, same
  IAM model, same deployment mechanism.
- No third party in the availability path.

**Bad, and accepted**

- Self-managed: version upgrades are a task-definition change plus a restart, and restore
  testing is on us. Tolerable because the data is derived — the ultimate fallback is
  reprocessing from S3.
- Single task means a **restart is downtime** for search, recommendations, pricing and
  duplicate detection. At portfolio traffic that is seconds, and the API degrades with typed
  errors rather than crashing.
- EBS makes the task AZ-affine: the volume lives in one AZ, so an AZ failure requires
  restoring a snapshot into the other. Documented in
  [ARCHITECTURE.md](./ARCHITECTURE.md#backups-and-failure-modes) rather than pretended away.

---

## Revisit when

- The vector count grows enough to need Qdrant clustering or memory-mapped storage tuning —
  at which point EC2 with a larger instance, or Qdrant Cloud inside a VPC peering
  arrangement, both become worth re-pricing.
- The non-exposure constraint changes, which would put Qdrant Cloud's managed operations
  back in contention.

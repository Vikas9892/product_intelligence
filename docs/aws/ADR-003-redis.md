# ADR-003 — Redis

**Status:** Accepted (design only — nothing deployed)
**Date:** 2026-08-04
**Decides:** how Redis runs in AWS

---

## Context

Redis in this platform is **not a cache**. It is the system of record:

| Holds | Reconstructible if lost? |
|---|---|
| Product records | **No** |
| Job state and progress | No |
| The processing queue | No (in-flight work) |
| Dead-letter queue | No |
| Analytics daily buckets | No |
| Enterprise organizations, tenants, API keys, audit log, quotas | **No** |
| Recommendation cache | Yes — regenerated on demand |

There is no relational database. `backend/README.md` says so explicitly, and
`settings.database` is referenced nowhere outside a docstring. Compose already reflects
this by enabling AOF persistence with `--appendfsync everysec` and calling persistence
"required, not optional".

Measured dataset after seeding the demo catalog: **104 KB**. Even a decade of portfolio use
would not approach the smallest managed node.

This inverts the usual ElastiCache trade-off. The normal argument — "it's just a cache,
losing it is cheap" — is exactly wrong here.

---

## Options

### A. Self-hosted Redis container on ECS

Cheapest on paper: one small Fargate task. But persistence on Fargate means attaching an
EBS volume and taking ownership of AOF durability, snapshot scheduling, restore testing,
version upgrades and failover — for the component whose loss destroys the catalog.

Running your own datastore to save ~$12/month, when that datastore is the system of record,
is the wrong trade and the wrong thing to demonstrate.

### B. ElastiCache Serverless

Genuinely attractive on price for bursty demo traffic: Valkey bills a 100 MB minimum
(~$6/month) versus Redis OSS's 1 GB minimum (~$60/month), plus per-ECPU request charges.

Two reservations. Costs scale with request volume in a way that is hard to bound when a
demo is being hammered, and the 1 GB floor on the Redis OSS engine makes the cheap price
contingent on choosing Valkey. For a workload with a *known, tiny, stable* footprint, a
fixed-price node is easier to reason about and easier to explain.

Worth revisiting — the Valkey minimum is competitive with the node below.

### C. ElastiCache node — **chosen**

A single `cache.t4g.micro` running Valkey (Redis-compatible, cheaper than the Redis OSS
engine, and a drop-in for `redis-py`). Roughly **$0.016/hour ≈ $11.68/month** on demand.

Managed gives exactly what matters here: automatic daily snapshots with retention, in-place
minor version upgrades, encryption at rest and in transit, an AUTH token, subnet-group
placement in private subnets, and CloudWatch metrics including
`DatabaseMemoryUsagePercentage` — the one alarm that genuinely protects a system of record
from eviction.

---

## Decision

**ElastiCache, single `cache.t4g.micro` node, Valkey engine**, in private subnets, with:

- **Automatic snapshots**, 7-day retention, plus a manual snapshot before any deploy that
  touches data shape.
- **Encryption in transit** (TLS) and **at rest**, with an AUTH token in Secrets Manager.
- A subnet group spanning both private subnets; a security group accepting 6379 from the
  `api-sg` and `worker-sg` groups **only**.
- No replica in the portfolio configuration.

Adding a replica with Multi-AZ failover roughly doubles this line item. That is the correct
production choice and is **not** the portfolio choice — stated plainly rather than quietly
omitted.

---

## Consequences

**Good**

- The irreplaceable data gets managed backups, encryption and patching.
- Snapshot restore is a documented, testable recovery path rather than an improvisation.
- Memory-pressure alarms are available without building anything.
- Fixed, predictable monthly cost — easy to reason about and easy to explain.

**Bad, and accepted**

- ~$11.68/month always-on, and it is one of the few components that **cannot** be scaled to
  zero between demos without losing the catalog. It is the floor of the running cost.
- Single node means no automatic failover: a node failure loses data back to the last
  snapshot. Accepted for a portfolio; unacceptable for real tenants.
- TLS requires the application to connect with `rediss://`. `redis-py` supports this via the
  URL scheme, so it should be a configuration change — but it is **unverified against this
  codebase** and is listed as a pre-deployment check in
  [ARCHITECTURE.md](./ARCHITECTURE.md#application-changes-required).

---

## Revisit when

- Valkey Serverless minimums make it cheaper at this footprint — plausible today, and worth
  re-pricing before Stage 11 provisions anything.
- Real tenants exist, at which point Multi-AZ with a replica stops being optional.

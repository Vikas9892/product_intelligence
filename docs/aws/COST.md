# Cost analysis

> **Status: design only.** Nothing is deployed and nothing has been billed. These are
> projections from published list prices, not observed spend.

## On the numbers below

The stage brief asks not to fabricate prices. So this document separates two things
carefully:

- **Verified** — checked against AWS's own pricing pages or corroborated search results in
  **August 2026**, for **us-east-1**. Each is cited.
- **Derived** — arithmetic performed here from those rates and from measured resource
  usage. The rate is verified; the monthly total is my calculation and inherits any error in
  my usage assumptions.

Prices change, vary by region, and exclude tax and free-tier credits. Anything a decision
rests on should be re-checked against the AWS Pricing Calculator before Stage 11 provisions
anything. Hours are calculated at **730 per month**.

---

## Verified unit prices

| Resource | Price | Source |
|---|---|---|
| Fargate vCPU | **$0.04048** / vCPU-hour | [Fargate pricing](https://aws.amazon.com/fargate/pricing/) (corroborated) |
| Fargate memory | **$0.004445** / GB-hour | as above |
| Fargate Spot | up to **70% off** on-demand | as above |
| ALB | **$0.0225** / hour + **$0.008** / LCU-hour | [ELB pricing](https://aws.amazon.com/elasticloadbalancing/pricing/) |
| NAT Gateway | **$0.045** / hour + **$0.045** / GB processed | [VPC pricing](https://aws.amazon.com/vpc/pricing/) |
| VPC **gateway** endpoint (S3) | **free** — no hourly, no data charge | as above |
| ElastiCache `cache.t4g.micro` | ~**$0.016** / hour (~$11.68/mo) | search-corroborated |
| ElastiCache Serverless (Valkey) | from ~**$6**/month (100 MB minimum) | search-corroborated |
| S3 Standard | **$0.023** / GB-month | search-corroborated |
| S3 requests | **$0.005** / 1k PUT · **$0.0004** / 1k GET | search-corroborated |
| EBS gp3 | **$0.08** / GB-month (3,000 IOPS included) | search-corroborated |
| Route 53 | **$0.50** / hosted zone-month; **$0.40** / M queries | [Route 53 pricing](https://aws.amazon.com/route53/pricing/) |
| CloudFront | first **1 TB/month egress free**, 10M requests free | search-corroborated |
| CloudWatch Logs | **5 GB/month free**; ~$0.03/GB archived | [CloudWatch pricing](https://aws.amazon.com/cloudwatch/pricing/) |
| CloudWatch alarms | **10 free**, then ~$0.10 / alarm-month | as above |
| ACM certificates | **free** for use with ALB/CloudFront | — |

> The Fargate, ElastiCache, S3, EBS and CloudFront figures came from search results and
> secondary aggregators because AWS's own pricing tables did not render in the fetched
> pages. They match the widely published us-east-1 rates, but they are **one step less
> direct** than the ALB, NAT, Route 53 and CloudWatch numbers, which came from AWS pages.

---

## Derived: always-on cost, everything running 24/7

The honest baseline — nothing scaled down, nothing on Spot.

| Line | Sizing | Derived monthly |
|---|---|---|
| Fargate `frontend` | 0.25 vCPU / 0.5 GB | $9.01 |
| Fargate `api` | 0.5 vCPU / 2 GB | $21.27 |
| Fargate `worker` | 1 vCPU / 4 GB | $42.53 |
| Fargate `qdrant` | 0.5 vCPU / 1 GB | $18.02 |
| ALB | 1 ALB, minimal LCU | ~$16.43 + LCU |
| NAT Gateway | 1, low traffic | ~$32.85 + data |
| ElastiCache | 1 × `cache.t4g.micro` | ~$11.68 |
| EBS (Qdrant) | 20 GB gp3 | $1.60 |
| Route 53 | 1 hosted zone | $0.50 |
| S3 | <1 GB, few thousand requests | <$0.10 |
| CloudFront | within free tier | $0.00 |
| CloudWatch | within/near free tier | ~$1–3 |
| Secrets Manager | 2 secrets | ~$0.80 |
| **Total** | | **≈ $155–165 / month** |

**That is too expensive for a portfolio that is idle most of the time**, and saying so is
more useful than presenting it as the answer. The rest of this document is about not paying
it.

The four dominant lines: **worker $42.53**, **NAT $32.85**, **api $21.27**, **qdrant
$18.02** — Fargate compute plus NAT is ~85% of the bill.

---

## Derived: the realistic portfolio configuration

Three changes, none of which alter the architecture:

1. **Worker on Fargate Spot** — it is interruption-tolerant by construction, because an
   interrupted job is redelivered and retried by machinery that already exists and was
   verified in Stage 9. At ~70% off: **$42.53 → ~$12.76**.
2. **Worker scales to zero** when the queue is empty (target-tracking on the `QueueDepth`
   metric). Idle cost approaches **$0**; it wakes when an upload arrives.
3. **Log retention trimmed** to 14 days (prod) / 3 days (staging).

| Line | Derived monthly |
|---|---|
| Fargate `frontend` | $9.01 |
| Fargate `api` | $21.27 |
| Fargate `qdrant` | $18.02 |
| Fargate `worker` (Spot, mostly at zero) | ~$1–13 |
| ALB | ~$16.43 |
| NAT Gateway | ~$32.85 |
| ElastiCache | ~$11.68 |
| EBS, Route 53, S3, CloudWatch, Secrets | ~$4 |
| **Total** | **≈ $114–127 / month** |

The upper bound assumes the Spot worker runs continuously; the lower assumes it sits at
zero and wakes only for uploads, which is the expected steady state for a portfolio.

Still substantial, and the reason is structural: **ALB + NAT + ElastiCache ≈ $61/month
exists whether or not anyone visits.** Fargate scale-to-zero cannot touch it.

---

## Turning it off between demonstrations

| Lever | Saves | Cost of pulling it |
|---|---|---|
| Worker → 0 tasks when idle | ~$13–43 | None. This is correct behavior, not a compromise. |
| `frontend`/`api`/`qdrant` → 0 outside demo windows | ~$48 | Cold start on next demo; Qdrant needs its EBS volume reattached |
| **Delete the ALB when dormant** | ~$16 | Recreate via Terraform; DNS must be repointed |
| **Delete the NAT Gateway when dormant** | ~$33 | Tasks lose egress; recreate with the stack |
| Keep only ElastiCache + S3 + Route 53 | — | **~$13/month dormant floor** — the catalog survives |
| Destroy everything, keep an ElastiCache snapshot + S3 | — | **~$1/month**; a demo costs a `terraform apply` and a restore |

Because Stage 11 will express all of this as Terraform, `terraform destroy` between demos
is the real cost control, and the reason the dormant floor can be about a dollar rather than
a hundred.

**The `queries/` S3 lifecycle rule** from [SECURITY.md](./SECURITY.md) is a small but real
saving too: image-search and duplicate-check query images are currently never deleted, so
without it that prefix grows forever.

---

## Cheaper architectures, and what they cost you

| Option | Derived monthly | What you give up |
|---|---|---|
| **As designed**, Spot + scale-to-zero | ~$115–125 | — |
| Drop CloudFront, ALB only | ~$115 | Edge caching and the free egress tier; ALB becomes the public entrance |
| **Replace NAT with interface endpoints** (ECR ×2, Logs, SSM, Secrets) | ~$115 | ~5 × $7 ≈ $36 vs NAT's $33 — **not actually cheaper**, but strictly more private. Considered and rejected on cost parity. |
| **ECS on EC2** (one `t4g.medium`, all tasks) | ~$60–70 | AMI patching, capacity providers, bin-packing |
| **Single EC2 running Docker Compose** | ~$12–15 | Everything this stage exists to demonstrate: service isolation, independent scaling, rolling deploys, task IAM |
| **Qdrant Cloud free tier** instead of self-hosted | −$18 | Violates the "not publicly exposed" constraint — see [ADR-004](./ADR-004-qdrant.md) |

The single-EC2 option deserves respect rather than dismissal: for a portfolio that must
simply *be reachable* at low cost, it is the rational choice, and it runs the exact Compose
stack Stage 8 already produces. The ECS design is worth its premium only while the point is
demonstrating production engineering — which is precisely the point here.

---

## What to watch once deployed

| Risk | Why it bites |
|---|---|
| **NAT data processing** | $0.045/GB. Model downloads were the big one — [ADR-005](./ADR-005-model-delivery.md) removes them, and the S3 gateway endpoint removes object traffic. Watch ECR pulls on frequent deploys. |
| **CloudWatch Logs ingestion** | The worker logs a line per pipeline stage per job. Free tier is 5 GB/month; a busy demo plus verbose logging can pass it. Keep `LOGGING__LEVEL=INFO` in prod, not DEBUG. |
| **ECR storage** | ~3.3 GB per backend tag. Without a lifecycle policy, ten builds is 33 GB. Keep the last 10 tags. |
| **Idle Fargate** | The largest avoidable cost. Scale-to-zero on the worker; scheduled scaling on the rest. |
| **Forgotten NAT/ALB** | The two things that bill steadily while nobody is looking. Both are the first to destroy when dormant. |

---

## Free-tier note

A new AWS account gets meaningful credits in the first 12 months, and CloudFront's 1 TB
egress and 10M requests are **permanently** free. That materially changes the first year and
is worth checking before committing to a shape — but a design that only works on free tier
is not a design, so nothing above assumes it.

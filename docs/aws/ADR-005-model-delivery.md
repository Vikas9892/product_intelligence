# ADR-005 — AI model delivery

**Status:** Accepted (design only — nothing implemented)
**Date:** 2026-08-04
**Decides:** how CLIP, BGE and the cross-encoder reach an ECS task

---

## Context

Three models are registered, all loaded locally with CPU-only PyTorch:

| Model | Role | Loaded by |
|---|---|---|
| `openai/clip-vit-base-patch32` | 512-d image embeddings | worker, and API on image search |
| `BAAI/bge-small-en-v1.5` | 384-d text embeddings | worker, and API on text search |
| `cross-encoder/ms-marco-MiniLM-L-6-v2` | Reranking / duplicate verification | worker (off by default) |

Measurements that decide this:

| Fact | Measured |
|---|---|
| Model cache on disk (`HF_HOME=/models`) | **1.3 GB** |
| Backend image today | **2.06 GB** |
| First job with an empty cache | **215 s** |
| Subsequent jobs, warm cache | **18 s** |
| First cold API search | **>30 s** — exceeded the smoke suite's request timeout |

That last row is not hypothetical. Stage 9's smoke suite failed on a genuinely cold
deployment because the first `/products/search` had to download and load BGE before it
could embed a query. Cold model loading is the single largest latency risk in this system,
and it is entirely self-inflicted if left to runtime.

Fargate makes it worse than Compose did: every task starts with empty ephemeral storage, so
"download on first use" happens *per task*, on every deploy and every scale-out — not once
per machine.

---

## Options

### A. Download from Hugging Face at startup

What Compose does today. On ECS this means every task replacement re-downloads ~730 MB,
every scale-out event pays 215 s of cold start, all of it flows through the NAT Gateway at
$0.045/GB, and **a Hugging Face outage becomes a deployment outage**. That last point is
disqualifying on its own: it puts a third party in the critical path of every task start.

### B. EFS-mounted shared model cache

One download, shared by all tasks. Fixes the repetition but adds an EFS filesystem, per-AZ
mount targets and NFS semantics — for read-only data that never changes. It also
reintroduces exactly the shared-filesystem coupling that [ADR-002](./ADR-002-storage.md)
removes. Solving a caching problem by adding a distributed filesystem is disproportionate.

### C. Models in S3, downloaded at startup

Sound and genuinely competitive. Pull ~730 MB from S3 through the free gateway endpoint —
no NAT charges, no third party, faster and more reliable than Hugging Face. Keeps the image
at 2 GB.

The cost is machinery that has to be built and maintained: an artifact-publishing step, a
startup fetch with its own failure handling, and cache-invalidation logic when a model
version changes. It also still leaves a download in the startup path — a smaller, faster
one, but a step that can fail.

### D. Bake the models into the image — **chosen**

Run the Hugging Face download at **build time** so `HF_HOME=/models` ships populated.

- **No startup download at all.** Model load becomes reading local files.
- **No runtime dependency on Hugging Face.** The dependency moves to build time, where a
  failure fails a build rather than a deploy.
- **No NAT egress for models**, ever.
- **Deterministic**: the image and its weights are one immutable, versioned artifact. Two
  tasks from the same image are byte-identical, which is what makes "the thing we tested is
  the thing we shipped" literally true.
- Startup cost becomes ECR image pull, which is inside AWS, fast, and already on the
  critical path for any image.

---

## Decision

**Bake the models into the backend image.** Roughly five lines in `backend/Dockerfile`, in
the builder stage, after dependencies are installed:

```dockerfile
# Populate HF_HOME at build time so no task ever downloads a model at startup.
ENV HF_HOME=/models
RUN --mount=type=cache,target=/root/.cache/uv \
    python -c "from transformers import CLIPModel, CLIPProcessor; \
               CLIPModel.from_pretrained('openai/clip-vit-base-patch32'); \
               CLIPProcessor.from_pretrained('openai/clip-vit-base-patch32')" \
 && python -c "from sentence_transformers import SentenceTransformer; \
               SentenceTransformer('BAAI/bge-small-en-v1.5')"
```

The cross-encoder is **deliberately excluded**. `RERANKER__ENABLED` and
`DUPLICATE_VERIFICATION__ENABLED` both default to false, so baking it would add weight to
every task for a feature that is off. If either is enabled, add it here — a documented
consequence rather than an oversight.

Resulting image: roughly **3.3 GB** (2.06 GB + 1.3 GB, less the cross-encoder).

The `model_cache` volume disappears from the AWS deployment. It stays in Compose, where a
bind-mounted development workflow still benefits from it.

---

## Consequences

**Good**

- Cold start stops being a model problem. The 215 s first job becomes an 18 s first job.
- Hugging Face leaves the runtime critical path entirely.
- No NAT data-processing charges for model traffic.
- Immutable, reproducible artifacts — the same property that makes staging→production
  promotion meaningful.
- Directly fixes the cold-start timeout Stage 9's smoke suite hit on a fresh deployment.

**Bad, and accepted**

- The image grows from 2.06 GB to ~3.3 GB. Every Fargate task pull moves ~60% more bytes,
  and ECR storage grows per retained tag. Mitigated by ECR lifecycle policies (keep the last
  10 tags) and by the fact that the pull is inside AWS on fast internal networking.
- Builds get slower and require network access to Hugging Face. Correct place for that
  dependency: a failed build is visible and retryable; a failed deploy at 3 a.m. is not.
- Changing a model version now requires a rebuild rather than a restart. Appropriate — a
  model change *is* a change to the artifact, and treating it as configuration was always
  the more dangerous option.

---

## Revisit when

- Image size starts hurting deploy times or ECR costs — option C (S3 artifacts through the
  gateway endpoint) is the ready-made next step and needs no rearchitecting.
- Reranking is enabled by default, at which point the cross-encoder joins the bake.
- GPU inference is ever justified. It is not today: the workload is a handful of embeddings
  per upload, CPU-only PyTorch is already pinned for Linux
  (Stage 8 cut ~5–7 GB of unusable CUDA libraries out of the image), and the cheapest GPU
  task would cost more per month than the entire current architecture.

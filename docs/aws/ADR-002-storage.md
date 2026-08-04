# ADR-002 — Object storage: replacing `app_storage`

**Status:** Accepted (design only — nothing implemented)
**Date:** 2026-08-04
**Decides:** how the API hands an uploaded image to the worker once they are separate tasks

---

## Context

In Compose, `api` and `worker` mount the same `app_storage` volume. Stage 8 flagged this as
the one thing that would not lift to ECS cleanly, describing it as the two services
"exchanging filesystem paths".

**Inspecting it closely made the problem considerably smaller than that description
suggests.** They do not exchange paths. They exchange a *name*:

```python
# app/schemas/product.py
class ProductImage(BaseModel):
    """`stored_filename` is a generated identifier, never the client-supplied
    `original_filename` — see `UploadService` for why (path-traversal /
    collision avoidance)."""
    original_filename: str
    stored_filename: str      # <- this is what crosses the boundary
    ...
```

`ProcessedImageInfo` goes further and documents that real filesystem paths **must never
appear in an API response**. The design already treats a path as an internal detail and a
generated opaque identifier as the shared contract.

Each side independently reconstructs a local path:

```python
# 4 sites, and that is the entire surface
app/services/upload_service.py:96           destination  = self._upload_dir / stored_filename   # write
app/services/product_service.py:216         stored_path  = self._upload_dir / image.stored_filename
app/services/vectorstore/search_service.py:79  stored_path = self._upload_dir / image.stored_filename
app/services/duplicate/duplicate_check_service.py:103  stored_path = self._upload_dir / image.stored_filename
```

`upload_dir` is already a constructor parameter on every one of those services, injected
for testing. The seam exists.

Three further facts from the audit shape the decision:

- **Processed images never leave the worker.** `processed_path` is consumed by embedding
  generation, attribute extraction and duplicate scoring — all inside the same process,
  during the same job. Nothing reads it afterwards. It needs no shared storage at all.
- **The backend serves no images.** No `StaticFiles`, no `FileResponse`, no
  `StreamingResponse` anywhere. The frontend documents this and shows a placeholder.
- **Query images are never cleaned up.** Image search and duplicate-check write the
  submitted query image through `UploadService` and never delete it. Today that leaks disk
  slowly and silently. This was found while writing this ADR.

---

## Options

### A. EFS shared filesystem

Mount one EFS filesystem into both tasks at `/app/storage`. **Zero application change** —
that is its real and only significant advantage, and it is a genuine one.

Against it:

- It preserves a shared mutable filesystem between two services, which is the coupling
  worth removing rather than relocating. The next question after "can they share files?" is
  always "who owns this file, and who may delete it?" — and EFS keeps that unanswered.
- Mount targets are per-AZ ENIs, so the network topology grows and every task becomes
  AZ-affine for storage.
- Storage is ~$0.30/GB-month against S3's $0.023 — irrelevant at 204 KB, but the wrong
  direction if images ever become real.
- POSIX semantics over NFS bring locking and consistency questions the application has
  never had to answer, and would now inherit.
- No lifecycle rules, so the query-image leak above stays a leak.
- No path to serving images publicly later without putting a server in front of it.

### B. S3 object storage — **chosen**

The API writes the object under `stored_filename`; the queue carries that same name it
already carries; the worker fetches it to a task-local temp file and the rest of the
pipeline runs unchanged on a local `Path`.

For it:

- `stored_filename` is *already* an opaque, generated, collision-safe identifier. It is a
  well-formed object key by construction — the application has been generating S3 keys
  since Phase 2A without calling them that.
- Eleven nines of durability for the only data in the system that cannot be regenerated.
- No AZ affinity, no mount targets, no filesystem to run out of.
- Free VPC gateway endpoint: S3 traffic never crosses the NAT Gateway, so it costs nothing
  in data processing and never leaves the AWS network.
- Lifecycle rules fix the query-image leak declaratively — expire a `queries/` prefix after
  a day — with no application change.
- Per-prefix IAM: the API gets `PutObject`, the worker gets `GetObject`, and neither gets
  more. Least privilege becomes expressible; on a shared filesystem it is not.
- A direct path to serving product images later via CloudFront with an Origin Access
  Control, which is the obvious next feature and is impossible with EFS without a server.

Against it:

- Requires an application change. It is small, and specified below.
- Adds an S3 round trip to the upload path (~tens of milliseconds against a pipeline whose
  fast path is 18 s).

---

## Decision

**S3.** One bucket per environment, private, versioned, SSE-S3 encrypted, reached through
a VPC gateway endpoint.

```
s3://pi-{env}-images/
    originals/{stored_filename}     # durable; written by api, read by worker
    queries/{stored_filename}       # transient search/dedup inputs; lifecycle-expired at 1 day
```

`processed/` is deliberately **absent**. Processed images are worker-local and short-lived;
uploading them would cost money and buy nothing.

---

## The refactor

The smallest change that makes this work, expressed as a port behind the existing seam.

**One new module** — an object store with two operations:

```python
class ObjectStore(Protocol):
    def put(self, key: str, data: bytes | BinaryIO) -> None: ...
    def materialize(self, key: str) -> Path: ...   # fetch to a task-local temp path
```

Two implementations: `LocalObjectStore` (wrapping today's `upload_dir`, so Compose and the
test suite are unchanged) and `S3ObjectStore` (boto3).

**Four call sites** swap `self._upload_dir / name` for `self._store.materialize(name)`, and
`UploadService`'s write becomes `self._store.put(...)`.

**Unchanged:** the job payload, `ProductImage`, every API schema, every response body, the
queue, the worker's pipeline stages, and `ImageProcessingService` — which keeps writing
processed images to local disk exactly as it does now.

That is the whole change: one module, four edited lines, one new dependency (`boto3`), and
a settings field to select the backend. The local implementation keeps the entire existing
test suite and Compose workflow working untouched.

> Not implemented in this stage. Stage 11 or a dedicated stage should do it, with the
> `LocalObjectStore` proving the seam before `S3ObjectStore` is wired in.

---

## Consequences

**Good**

- API and worker no longer share mutable state. They share a namespace.
- The only irreplaceable data in the system gets S3-grade durability and versioning.
- The query-image leak becomes a lifecycle rule rather than a code change.
- Least privilege becomes expressible per service.
- Image serving via CloudFront becomes a configuration change rather than a redesign.

**Bad, and accepted**

- The application gains a boto3 dependency and an AWS-shaped concept. Mitigated by the port:
  the default implementation is local, so nothing outside AWS needs S3.
- An upload now performs a network write before returning 202. Negligible against pipeline
  latency, and it happens before the queue, so a failed write correctly fails the request
  rather than producing a job that can never succeed.

---

## Revisit when

- Images need to be served to browsers — S3 + CloudFront + OAC, no redesign required.
- Objects grow large enough that presigned direct-to-S3 uploads beat proxying bytes through
  the API.

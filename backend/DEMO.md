# Demo Walkthrough

A hands-on tour of the platform's capabilities using `curl`. It follows the natural order a product takes through the system: **upload → track → search → recommend → duplicate check → price → analytics → enterprise**.

> [!NOTE]
> Response bodies below show the **real field names** from the API schemas. Values (ids, scores, prices) are illustrative — yours will differ. There are no bundled screenshots or recordings in the repository; a capture checklist is provided at the end.

---

## The one-command demo

If you want a working, populated, *verified* environment rather than a guided tour, run this from the repository root:

```bash
python scripts/demo.py
```

`make demo` is the same thing. The script is the implementation and runs directly on any platform with Python — Windows developers do not need GNU make.

It starts the stack, waits for every service to report healthy, seeds a deterministic catalog of 8 synthetic products through the **real upload API**, waits for the async pipeline to finish them, then verifies 30 behaviors end to end and prints where to look:

```
Product Intelligence - Demo Setup

Connectivity & health
  [PASS] API liveness                       HTTP 200 in 53ms
  [PASS] System health                      redis=healthy qdrant=healthy workers=4 models=3
  ...
Demo catalog
  [PASS] Seed demo products                 8 products uploaded
Async pipeline
  [PASS] Jobs reach completion              8 product(s) processed, slowest 56s
  [PASS] Products searchable                all 8 products findable by name
AI intelligence
  [PASS] Image search                       self-match 1.000, twin ranked above unrelated products
  [PASS] Duplicate detected                 detected, confidence 0.977, 4 signals
  ...

ALL CHECKS PASSED  30 checks in 5.9s

Demo environment ready.

  Frontend    http://localhost:3000
  API docs    http://localhost:8000/docs
```

> [!IMPORTANT]
> **First run is slow, and that is expected.** The initial build compiles the images, and the first *upload* downloads CLIP (~600 MB) and BGE (~130 MB) from Hugging Face into the `model_cache` volume. Budget **10–15 minutes** end to end on a cold machine. Measured afterwards: a full seed-and-verify takes **~66 s**, and re-verifying an already-seeded catalog takes **~6 s**. The models are downloaded once and survive `docker compose down`.

Useful variants:

```bash
python scripts/demo.py --profile dev        # hot-reload profile instead
python scripts/demo.py --no-start           # verify something already running
python scripts/demo.py --frontend-port 3100 # when 3000 is taken
```

### The demo catalog

Eight synthetic products, each present for a reason. `python scripts/smoke/runner.py --list-catalog` prints them with their rationale. The relationships are what make the capabilities demonstrable rather than merely exercised:

| Product | Why it exists |
|---|---|
| `shoe_blue_a` | Anchor. Source for recommendations, pricing and duplicate checks. |
| `shoe_blue_b` | Near-identical twin of the anchor — **should** be flagged a duplicate. |
| `shoe_black` | Same category, different brand and colour — recommended, but not a duplicate. |
| `mug_red_a` / `mug_red_b` | A second similarity cluster in an unrelated category. |
| `backpack_blue` | Shares a colour with the blue shoes and nothing else — catches recommendations driven by colour alone. |
| `backpack_black` | Same model, different colour: a third cluster. |
| `lamp_yellow` | Negative control. Must rank **below** real matches, or a system returning everything would look correct. |

All names begin with `Demo ` and every description states the product is synthetic. The images are generated deterministically by `scripts/smoke/images.py` — no downloaded product photography, and byte-identical on every machine.

Seeding is idempotent as far as the API permits: it searches for an exact name-and-brand match and reuses what it finds, so repeated runs upload nothing. See [`seeding.py`](../scripts/smoke/seeding.py) for the two honest limits.

### Verifying a deployment on its own

The same runner works against any deployment, including one you did not start:

```bash
python scripts/smoke/runner.py --base-url http://localhost:8000
python scripts/smoke/runner.py --base-url https://api.example.com --timeout 60
python scripts/smoke/runner.py --only ai        # one stage; prerequisites resolve automatically
```

Exit codes are CI-ready: `0` verified, `1` a check failed (including an unreachable deployment), `2` the runner was misinvoked and never formed a verdict.

---

## Prerequisites for the manual tour

The rest of this document drives the API by hand. Either use the containerized stack above, or run the backend natively:

```bash
# Terminal 1 — API
uv run uvicorn app.main:app --reload

# Terminal 2 — workers (required for async uploads)
uv run python scripts/run_workers.py
```

Base URL: `http://localhost:8000` · Interactive docs: `http://localhost:8000/docs`

Recommended demo order:

```mermaid
flowchart LR
    A[1. Upload] --> B[2. Track job]
    B --> C[3. Search]
    C --> D[4. Recommend]
    D --> E[5. Duplicate check]
    E --> F[6. Price]
    F --> G[7. Analytics]
    G --> H[8. Enterprise]
```

---

## 0. Health check

```bash
curl http://localhost:8000/health
```

---

## 1. Upload a product

Upload is `multipart/form-data`: a required `name` and `file`, plus optional `brand`, `description`, `category`, `price`.

```bash
curl -X POST http://localhost:8000/api/v1/products/upload \
  -F "name=Blue Running Shoes" \
  -F "brand=Nike" \
  -F "category=Men Shoes" \
  -F "price=1999" \
  -F "file=@./shoe.jpg"
```

With the async pipeline enabled (default), the file is stored, a job is queued, and you get **202 Accepted**:

```json
{
  "product_id": "0f2c...",
  "job_id": "7ab1...",
  "status": "queued",
  "status_url": "/api/v1/products/0f2c.../status"
}
```

> If `ASYNC_PIPELINE__ENABLED=false`, the upload is processed inline and returns **201 Created** with the full `UploadResponse` (processed image info, embedding info, duplicate decision).

---

## 2. Track processing

Poll the product's job status until it completes:

```bash
curl http://localhost:8000/api/v1/products/0f2c.../status
```

```json
{
  "job_id": "7ab1...",
  "product_id": "0f2c...",
  "status": "completed",
  "progress": 100,
  "current_stage": "Completed",
  "retry_count": 0,
  "max_retries": 5,
  "error": null,
  "created_at": "2026-07-24T10:00:00Z",
  "updated_at": "2026-07-24T10:00:03Z"
}
```

Jobs that exhaust their retries land in the dead-letter list:

```bash
curl http://localhost:8000/api/v1/jobs/dead-letter
```

---

## 3. Search

Search is also `multipart/form-data`: provide a query `image` (`file`), a text `query`, or both (at least one is required). Optional `brand`/`category`/`min_price`/`max_price` filters apply.

```bash
# Text query
curl -X POST http://localhost:8000/api/v1/products/search \
  -F "query=blue running shoes" \
  -F "top_k=5"

# Image + text (hybrid)
curl -X POST http://localhost:8000/api/v1/products/search \
  -F "query=running shoes" \
  -F "file=@./query.jpg"
```

```json
{
  "results": [
    {
      "product_id": "0f2c...",
      "score": 0.83,
      "matched_modalities": ["image", "text"],
      "metadata": { "name": "Blue Running Shoes", "brand": "nike", "category": "men-shoes" }
    }
  ]
}
```

`matched_modalities` shows which sides contributed; with both provided, the score is the weighted fusion (`0.7 × image + 0.3 × text`).

---

## 4. Recommendations

Get products similar to an existing one:

```bash
curl http://localhost:8000/api/v1/products/0f2c.../recommendations
```

Returns ranked, brand-diversified similar products. (The worker warms this result into the recommendation cache after processing, so it is typically already cached.)

---

## 5. Duplicate check

Check whether a candidate product duplicates something already indexed (`multipart/form-data`, like upload):

```bash
curl -X POST http://localhost:8000/api/v1/products/check-duplicate \
  -F "name=Blue Running Shoes" \
  -F "brand=Nike" \
  -F "file=@./shoe.jpg"
```

The response reports whether it is a duplicate and the confidence. With `DUPLICATE_VERIFICATION__ENABLED=true`, it additionally returns the cross-encoder score, the raw retrieval similarity, and human-readable reasons; with it off, those fields are `null` and the weighted-similarity decision is used.

---

## 6. Pricing

Estimate a fair price from semantically similar priced products. Pricing is JSON:

```bash
curl -X POST http://localhost:8000/api/v1/pricing/estimate \
  -H "Content-Type: application/json" \
  -d '{"name": "Blue Running Shoes", "brand": "Nike", "category": "Men Shoes"}'
```

```json
{
  "estimated_price": 1899.5,
  "confidence": "medium",
  "confidence_score": 0.62,
  "strategy": "trimmed_mean",
  "comparable_count": 12,
  "pricing_reason": "Estimated from 12 comparable products after outlier removal.",
  "comparables": [
    { "product_id": "0f2c...", "price": 1999.0, "similarity": 0.83, "name": "Blue Running Shoes", "brand": "nike" }
  ]
}
```

You can also price an already-indexed product directly:

```bash
curl http://localhost:8000/api/v1/pricing/0f2c...
```

---

## 7. Analytics

REST reports over Redis daily buckets (requires `ANALYTICS__ENABLED=true`):

```bash
curl http://localhost:8000/api/v1/analytics/dashboard
curl http://localhost:8000/api/v1/analytics/pipeline
curl http://localhost:8000/api/v1/analytics/models
curl http://localhost:8000/api/v1/analytics/trends
```

---

## 8. Enterprise (opt-in)

Requires `ENTERPRISE__ENABLED=true`. Bootstrap an organization — the one open endpoint — which returns an owner API key **once**:

```bash
curl -X POST http://localhost:8000/api/v1/organizations \
  -H "Content-Type: application/json" \
  -d '{"name": "Acme"}'
```

```json
{
  "organization": { "id": "...", "name": "Acme" },
  "tenant": { "id": "...", "name": "default" },
  "api_key": { "api_key": { "role": "owner", "prefix": "pik_xxxxxxx" }, "key": "pik_...redacted..." }
}
```

Use the raw key in the configured header (`X-API-Key` by default) for every other enterprise route:

```bash
# Create a scoped key (cannot exceed your own role)
curl -X POST http://localhost:8000/api/v1/api-keys \
  -H "X-API-Key: pik_..." -H "Content-Type: application/json" \
  -d '{"name": "ci", "role": "member"}'

# Inspect usage against quota
curl http://localhost:8000/api/v1/usage -H "X-API-Key: pik_..."

# Read the tenant audit log
curl http://localhost:8000/api/v1/audit -H "X-API-Key: pik_..."
```

Expected behaviors to demonstrate:

| Action | Result |
|---|---|
| Call an enterprise route with no key | `401` |
| A `member` key calling a key-management route | `403` |
| An `admin` minting an `owner` key | `403` (no privilege escalation) |
| Exceeding the configured quota | `429` |

---

## Observability

```bash
curl http://localhost:8000/metrics                  # Prometheus exposition (unprefixed)
curl http://localhost:8000/api/v1/system/health     # operational health
curl http://localhost:8000/api/v1/system/stats      # operational stats
```

---

## Useful screenshots to capture

The repository ships no images. If you assemble a visual walkthrough, these are the highest-value captures:

- [ ] Swagger UI at `/docs` showing the grouped routers.
- [ ] The `202 Accepted` upload response.
- [ ] A job-status response transitioning to `completed`.
- [ ] A hybrid search response with `matched_modalities: ["image", "text"]`.
- [ ] A pricing response including its `comparables`.
- [ ] The enterprise bootstrap response (redact the raw key).
- [ ] A `403` from a privilege-escalation attempt.
- [ ] A snippet of `/metrics` output.

> [!TIP]
> Store any captured assets under `docs/` and link them from this file. Do not commit real secrets — redact API keys in screenshots.

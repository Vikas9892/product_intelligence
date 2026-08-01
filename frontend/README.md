# Product Intelligence — Frontend

The web client for the [Multi-Modal Product Intelligence Engine](../backend/README.md). It
is built to the specification in [`ARCHITECTURE.md`](./ARCHITECTURE.md) and consumes the
existing FastAPI backend **without modifying it**.

> **Status:** Stage 6 complete — Enterprise & Operations. Stage 5 delivered the AI
> Intelligence Experience; On top of the Stage 3
> foundation (shell, API layer, auth, component library) and Stage 4 features (dashboard,
> upload, product detail), every intelligence surface is live: **AI Search** with
> explainability, **Duplicate Intelligence**, **Recommendations**, **Pricing**, and **AI
> Analytics**.

## Features (live)

| Page                            | Data source                                                                  | Notes                                                                                                                      |
| ------------------------------- | ---------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| **Dashboard** (`/`)             | `analytics/dashboard`, `analytics/pipeline`, `system/health`, `system/stats` | Real metric cards, system + pipeline panels, manual refresh; each section degrades independently                           |
| **Upload** (`/upload`)          | `POST /products/upload` → poll `GET /products/{id}/status`                   | Drag-and-drop, live progress, async job tracking, cancel, navigate on completion                                           |
| **AI Search** (`/search`)       | `POST /products/search`, `GET /products/{id}/explanations`                   | Text / image / hybrid modes, real filters, history + saved filters, backend-measured latency, per-result explainability    |
| **Duplicates** (`/duplicates`)  | `POST /products/check-duplicate`                                             | Verdict + confidence, four similarity signals, side-by-side metadata diff, ranked candidates, cross-encoder state          |
| **Recommendations**             | `GET /products/{id}/recommendations`                                         | Cards with score, backend explanation, brand/category/attribute/tag overlap; overlap filters and sorting                   |
| **Pricing** (`/pricing`)        | `POST /pricing/estimate`                                                     | Estimate + confidence + strategy, price distribution chart, comparables table, outlier-handling explainer                  |
| **AI Analytics** (`/analytics`) | `analytics/dashboard`, `/pipeline`, `/models`, `/trends`, `system/stats`     | Usage counters, latency + throughput, four event-trend charts with granularity controls, models in use                     |
| **Enterprise** (`/enterprise`)  | `organizations`, `api-keys`, `audit`, `usage`                                | Capability probe, onboarding, session context, API-key lifecycle, audit log, usage vs quota                                |
| **System** (`/system`)          | `system/health`, `system/stats`, `models`                                    | API/Redis/Qdrant status, queue depth, configured workers, uptime, model registry                                           |
| **Product** (`/products/{id}`)  | recommendations, pricing, explanations, models                               | Metadata (carried from search), embedding summary, pricing, recommendations, duplicate status; image not served by the API |

> [!NOTE]
> The backend is frozen and exposes no list-all, get-one-product, or image-serving
> endpoints. Those gaps are handled honestly (search-driven browse, metadata carried via
> query cache, image placeholder) rather than with mock data or fabricated endpoints.

### Explainability: what is real, and what is not shown

Every figure in the UI comes from a backend response. Where a response does not carry
something, the UI says so instead of synthesizing it.

`ProductSearchResult` returns only `product_id`, `score`, `matched_modalities`, and
`metadata` (`backend/app/schemas/search.py`). So a search result explains itself with:

- **Why retrieved** — `matched_modalities`, mapped to the model that produced the match
  (CLIP for image, BGE for text).
- **Fused relevance** — `score`, labelled as the fused value it is. Image and text signals
  are combined server-side and the individual sides are never returned, so no per-modality
  split is displayed.
- **Recorded decisions** — fetched on demand from `GET /products/{id}/explanations`, which
  is where genuine weighted breakdowns live: each component's `value`, `weight`, and
  `contribution`, the structured `reasons`, and `confidence`.
- **Explicitly absent** — per-modality sub-scores and the cross-encoder score are named as
  not returned by search, with a pointer to where they do exist (duplicate verification).

> [!IMPORTANT]
> In real responses the components' `contribution` values do **not** sum to `total` — the
> scorer applies its own configured weighting internally (live example: 0.9998 + 0.6944
> against a total of 0.9693). The UI therefore presents `total` as the backend's final
> score and never as a sum, and the behavior is pinned by a test.

The same principle governs Duplicate Intelligence:

- `cross_encoder_score` and `retrieval_similarity` are `null` unless the backend runs with
  `DUPLICATE_VERIFICATION__ENABLED=true` (it is **off** by default). The UI reports the
  feature as disabled rather than rendering a placeholder number — the null is a real
  state, not missing data.
- The matched product's descriptive fields are resolved **best-effort** through search,
  because the backend has no get-product endpoint. When the lookup finds nothing, the
  comparison says so instead of showing blanks that could read as real values.
- In the metadata diff, two absent values are marked **Not comparable**, never "Same" —
  agreement on nothing is not evidence of a match.
- Product images are shown for the submitted side only (a local object URL); the backend
  serves no product images, and the matched side states that rather than using a stand-in.

And Recommendations:

- An **empty recommendation set is not the same as "nothing similar exists"**. The worker
  precomputes recommendations when a product is processed and caches them in Redis for an
  hour (`RECOMMENDATION__CACHE_TTL_SECONDS`), so a product indexed into an empty catalog
  legitimately returns `[]` until that expires. The UI explains that rather than showing a
  bare empty state.
- Brand and category overlap chips render whether or not they matched, so "not shared" is
  distinguishable from "not reported".
- Filtering and sorting act only on what was returned — they never re-score. Each filter
  shows how many of the fetched set satisfy it, so an empty filtered view is explained
  before it happens.

And Pricing:

- **Outliers are removed server-side before the response is built**, so `comparables`
  contains only the survivors and the discarded prices are absent from the payload
  entirely. The UI explains the Tukey IQR mechanism and states that the removed prices
  cannot be listed — and deliberately runs **no** client-side outlier detection, which
  could disagree with the backend's own decision.
- The min/median/max line is a plain summary of the comparables in the response, computed
  in the browser and **labelled as such**. `estimated_price`, `confidence`,
  `confidence_score`, and `strategy` are the backend's and are never recomputed.
- A `0.00` estimate with no comparables is called out as "not a real valuation" rather than
  displayed as a price.

And AI Analytics:

- `average_processing_seconds` is the **only** latency figure any JSON endpoint exposes, and
  it covers whole-request processing. There is no per-stage embedding or retrieval timing to
  show, so none is displayed — the page says so and points at `/metrics`, which carries the
  Prometheus histograms and is deliberately not a UI data source.
- Trend points are plotted exactly as returned, **zeros included**. A quiet day is real
  information; dropping or interpolating it would misrepresent the series.
- `/analytics/trends` declares `response_model=None` on the backend (it also serves
  Markdown), so `openapi-typescript` generates no schema for it. Its types are hand-written
  in `endpoints/analytics.ts` and its metric/granularity constants are pinned by a test
  against the backend enums, since a drift there would silently 422.

## Stack

| Concern       | Choice                                          |
| ------------- | ----------------------------------------------- |
| Framework     | Next.js 15 (App Router) + React 19 + TypeScript |
| Styling       | Tailwind CSS v4                                 |
| Components    | shadcn/ui (Radix primitives) + next-themes      |
| Server state  | TanStack Query                                  |
| Client state  | Zustand                                         |
| HTTP / types  | Axios + generated OpenAPI types                 |
| Forms         | React Hook Form + Zod                           |
| Charts        | Recharts (via shadcn chart)                     |
| Testing       | Vitest + React Testing Library (jsdom)          |
| Lint / format | ESLint (flat config) + Prettier                 |

## Prerequisites

- Node.js ≥ 18.18 (developed on Node 22)
- npm
- The FastAPI backend running (for live data and for regenerating API types)

## Getting started

```bash
npm install
cp .env.example .env.local   # optional — every value has a safe default
npm run dev                  # http://localhost:3000
```

By default the app runs in **single-tenant demo mode** (no auth gate, no API key), and
proxies the API so the browser only ever talks to this origin. Set
`NEXT_PUBLIC_ENTERPRISE_ENABLED=true` only when the backend runs with the enterprise layer
on.

### The API proxy

Requests go to a same-origin path and are forwarded by a Next.js rewrite to
`BACKEND_ORIGIN` (default `http://localhost:8000`). This is not incidental — the backend is
frozen, and two of its defaults make direct browser calls unworkable:

- `APPLICATION__CORS_ALLOWED_ORIGINS` defaults to `[]`, so a direct cross-origin request is
  blocked outright. Proxying sidesteps CORS entirely, so the app works against a **stock**
  backend with no `.env` changes.
- `CORSMiddleware` is registered without `expose_headers`, so a cross-origin browser
  response could never read `X-Response-Time-Ms` — the backend's own timing measurement.
  Same-origin responses expose it, which is what lets AI Search report **genuine backend
  latency** rather than a client-side guess.

Point `BACKEND_ORIGIN` at a different backend to retarget the proxy. Setting
`NEXT_PUBLIC_API_BASE_URL` to an absolute URL opts out of the proxy and calls the backend
directly, which then requires backend CORS to be configured.

## Scripts

| Script                 | Purpose                                                   |
| ---------------------- | --------------------------------------------------------- |
| `npm run dev`          | Dev server (Turbopack)                                    |
| `npm run build`        | Production build (`output: "standalone"`)                 |
| `npm start`            | Serve the production build                                |
| `npm run lint`         | ESLint                                                    |
| `npm run typecheck`    | `tsc --noEmit`                                            |
| `npm run format`       | Prettier write                                            |
| `npm run format:check` | Prettier check                                            |
| `npm run test`         | Vitest (run once)                                         |
| `npm run gen:api`      | Regenerate `src/lib/api/schema.d.ts` from `/openapi.json` |
| `npm run check`        | lint + format check + typecheck + test                    |

## Architecture at a glance

- **App shell** (`src/app`, `src/components/common`) — root layout with providers,
  collapsible responsive sidebar, sticky topbar with breadcrumbs, theme toggle, skip link,
  and loading/error/404 boundaries. Routes live under the `(app)` route group.
- **API layer** (`src/lib/api`) — a single Axios instance with request (API-key header) and
  response (error-normalizing) interceptors, generated OpenAPI types + ergonomic aliases, a
  typed request layer, a query-key registry, and the TanStack Query client (retry policy:
  no 4xx retries, network/5xx retried with backoff).
- **Auth** (`src/lib/auth`, `src/stores/auth-store.ts`, `src/components/auth`) — Zustand
  auth store with session/local persistence, optional enterprise mode, client RBAC hints,
  and `RequireAuth` / `RequirePermission` / `RequireEnterprise` guards. Demo mode is
  unauthenticated by design.
- **UI library** (`src/components/ui`, `src/components/data`, `src/components/feedback`) —
  shadcn primitives plus composed pieces: `StatCard`, `StatusChip`, `ConfidenceBadge`,
  `ScoreBar`, `DataTable`, `ChartCard`, `EmptyState`, `ErrorState`, loading skeletons.

See [`ARCHITECTURE.md`](./ARCHITECTURE.md) for the full design.

## Configuration

Public config is read through [`src/config/env.ts`](./src/config/env.ts) with safe defaults;
see [`.env.example`](./.env.example). API types are generated from the backend's
`/openapi.json` — the backend is the single source of truth, so a contract change surfaces
as a TypeScript error here (run `npm run gen:api` to refresh).

## Structure

```
src/
├── app/          # App Router: (app) route group, layouts, loading/error/404
├── components/
│   ├── ui/       # shadcn primitives
│   ├── common/   # shell: sidebar, topbar, breadcrumbs, page header, skip link
│   ├── data/     # StatCard, DataTable, ScoreBar, ConfidenceBadge, ChartCard, …
│   ├── feedback/ # EmptyState, ErrorState, loading skeletons
│   └── auth/     # AuthInitializer + route guards
├── lib/
│   ├── api/      # client, interceptors, generated types, query client/keys
│   ├── auth/     # roles/RBAC, storage, useAuth
│   └── format/   # number/price/percent/score/date formatters
├── providers/    # Query, Theme, Tooltip, Toaster, AuthInitializer
├── stores/       # Zustand auth store
├── config/       # env + navigation config
└── hooks/        # shared hooks (use-mobile)
tests/            # Vitest setup + unit/component tests
```

## Testing & quality

`npm run check` runs the full gate (lint, format check, typecheck, Vitest). Unit/component
tests (Vitest + React Testing Library) cover the API error/retry policy, auth roles and
store, shared components, formatters, dashboard/upload/product/search features, and
automated accessibility checks (jest-axe). End-to-end smoke tests (Playwright) exercise the
app shell, navigation, and theming:

```bash
npm run check          # lint + format + typecheck + unit/component tests
npm run e2e:install    # one-time: download the Playwright browser
npm run e2e            # Playwright end-to-end (auto-starts the dev server)
```

Accessibility baselines: semantic landmarks, a skip link, labelled controls,
keyboard-operable shadcn/Radix primitives, axe assertions, and status/confidence that never
rely on color alone.

## Enterprise & operations

The enterprise layer is **off by default**, and the app is fully usable that way — there is
no authentication gate in demo mode.

### Capability is probed, not configured

The backend mounts the enterprise router only when `ENTERPRISE__ENABLED` is on, which makes
the HTTP status of any enterprise route a reliable signal. The console probes `GET /usage`
and maps the answer:

| Status | Meaning                                                |
| ------ | ------------------------------------------------------ |
| `404`  | router not mounted — the layer is **disabled**         |
| `401`  | mounted, but the key is missing or invalid             |
| `403`  | mounted, key **valid**, role lacks that one permission |
| `200`  | mounted, authenticated, permitted                      |

Two consequences worth stating: a **403 means enterprise is enabled** (reading it as
"unavailable" would hide a working feature), and a network failure maps to **unknown**,
never to disabled — the UI must not claim a feature is switched off when it merely could
not ask. Flipping the backend flag is picked up on reload with no frontend rebuild.

### RBAC mirrors the backend exactly

`src/lib/auth/roles.ts` is a transcription of `backend/app/models/role.py` — the same
`Permission` names and the same `ROLE_PERMISSIONS` mapping. Verified live, per role:

|                  | owner | admin | member | viewer |
| ---------------- | ----- | ----- | ------ | ------ |
| `/organizations` | 200   | 403   | 403    | 403    |
| `/api-keys`      | 200   | 200   | 403    | 403    |
| `/audit`         | 200   | 200   | 403    | 403    |
| `/usage`         | 200   | 200   | 403    | 403    |

> [!IMPORTANT]
> This is **not a rank ladder**. `member` adds `write` to `viewer`, but every
> enterprise-management permission first appears at `admin`, and `manage_organization` only
> at `owner`. A previous minimum-role model got this wrong for `viewUsage` and showed
> members a panel that could only 403. Permission checks therefore derive from the mapping,
> never from rank.

Frontend checks are **hints only**. Gated requests are still issued and the server's
401/403 is the security boundary; a 403 renders an authoritative forbidden state naming the
roles that do grant it.

### API-key secret handling

The backend returns a raw key **only** in the create response — `GET /api-keys` has no `key`
field at all. So a secret is shown exactly once, held in component state, never written to
`localStorage`, and never logged. E2E assertions grep browser storage to prove it. The
session credential itself defaults to `sessionStorage`, with an explicit "remember on this
device" opt-in to `localStorage`.

There is **no rotate action**, because the backend has no rotation endpoint. Rotating means
creating a replacement and revoking the old key, which the UI says rather than implying a
capability that does not exist.

### What the operations page will not claim

- **Configured workers, not live workers.** `workers` is the configured concurrency. The
  backend's own service docstring states the API has no handle on the worker processes and
  implements no heartbeat, so live worker count is not knowable. The label and tooltip say
  so, and a test asserts "Active/Running/Live workers" never appear.
- **A degraded read is not a measurement.** Health checks degrade to `unhealthy`/`0` rather
  than raising, so `queue_depth: 0` while Redis is down is a fallback. Queue depth,
  jobs-in-flight, and dead-letter size all report **Unknown** in that case.
- **`/metrics` is not parsed.** Prometheus text is linked, not scraped; deriving domain
  metrics from it would invent structure the JSON API does not offer.
- **Usage is a snapshot, so it has no chart.** `requests_today` is a counter with no history
  behind it. A quota of `0` means no ceiling — shown as such, not as 0% used.
- **Audit has no pagination**, because the endpoint takes only a `limit` (no cursor or
  offset). Filters visibly narrow _what was fetched_ rather than posing as a server query.

### Running with enterprise enabled

```bash
# backend/.env
ENTERPRISE__ENABLED=true
```

Restart the API and reload the app. Bootstrap an organization from `/enterprise` — that is
the one unauthenticated enterprise endpoint — and the owner key is displayed once.

## End-to-end tests

Playwright runs against a **production build**, not the dev server. `next dev` compiles
routes on first request, so parallel workers hitting cold routes produced multi-second first
paints and assertion timeouts unrelated to the application. Building first removed that
flake class outright (per-test times fell from ~8-12s to ~2-5s).

Backend calls are intercepted per-spec with `page.route`, so the suite is self-contained and
does not need the API running. Fixtures are payloads **captured from the live backend**, so
they represent real contracts rather than invented shapes.

```bash
npm run e2e          # first time: npx playwright install chromium
```

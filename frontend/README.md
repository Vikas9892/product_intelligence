# Product Intelligence — Frontend

The web client for the [Multi-Modal Product Intelligence Engine](../backend/README.md). It
is built to the specification in [`ARCHITECTURE.md`](./ARCHITECTURE.md) and consumes the
existing FastAPI backend **without modifying it**.

> **Status:** Stage 5 in progress — the AI Intelligence Experience. On top of the Stage 3
> foundation (shell, API layer, auth, component library) and Stage 4 features (dashboard,
> upload, product detail), the **AI Search workspace** is live with text, image, and hybrid
> retrieval. Duplicate, recommendation, pricing, and analytics intelligence follow in the
> remaining Stage 5 milestones.

## Features (live)

| Page                           | Data source                                                                  | Notes                                                                                                                      |
| ------------------------------ | ---------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| **Dashboard** (`/`)            | `analytics/dashboard`, `analytics/pipeline`, `system/health`, `system/stats` | Real metric cards, system + pipeline panels, manual refresh; each section degrades independently                           |
| **Upload** (`/upload`)         | `POST /products/upload` → poll `GET /products/{id}/status`                   | Drag-and-drop, live progress, async job tracking, cancel, navigate on completion                                           |
| **AI Search** (`/search`)      | `POST /products/search`, `GET /products/{id}/explanations`                   | Text / image / hybrid modes, real filters, history + saved filters, backend-measured latency, per-result explainability    |
| **Duplicates** (`/duplicates`) | `POST /products/check-duplicate`                                             | Verdict + confidence, four similarity signals, side-by-side metadata diff, ranked candidates, cross-encoder state          |
| **Product** (`/products/{id}`) | recommendations, pricing, explanations, models                               | Metadata (carried from search), embedding summary, pricing, recommendations, duplicate status; image not served by the API |

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

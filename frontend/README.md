# Product Intelligence — Frontend

The web client for the [Multi-Modal Product Intelligence Engine](../backend/README.md). It
is built to the specification in [`ARCHITECTURE.md`](./ARCHITECTURE.md) and consumes the
existing FastAPI backend **without modifying it**.

> **Status:** Stage 3 complete (foundation). The application shell, API layer, auth
> infrastructure, and shared component library are in place. Business features (dashboard,
> upload, search, pricing, analytics, enterprise, …) are built in Stages 4–7 against this
> foundation.

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

By default the app runs in **single-tenant demo mode** (no auth gate, no API key). Point it
at the backend with `NEXT_PUBLIC_API_BASE_URL`; set `NEXT_PUBLIC_ENTERPRISE_ENABLED=true`
only when the backend runs with the enterprise layer on.

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

`npm run check` runs the full gate (lint, format check, typecheck, tests). Tests cover the
API error/retry policy, auth roles and store, the shared components, formatters, breadcrumb
logic, and the app-shell navigation. Accessibility baselines: semantic landmarks, a skip
link, labelled controls, keyboard-operable shadcn/Radix primitives, and status/confidence
that never rely on color alone.

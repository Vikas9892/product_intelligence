# Product Intelligence — Frontend

The web client for the [Multi-Modal Product Intelligence Engine](../backend/README.md). It
is built to the specification in [`ARCHITECTURE.md`](./ARCHITECTURE.md) and consumes the
existing FastAPI backend without modifying it.

> **Status:** Stage 3 · Milestone 1 (Repository Setup). Tooling and structure only — the
> application shell, API layer, and business pages are built in the following milestones.

## Stack

| Concern              | Choice                                          |
| -------------------- | ----------------------------------------------- |
| Framework            | Next.js 15 (App Router) + React 19 + TypeScript |
| Styling              | Tailwind CSS v4                                 |
| Components           | shadcn/ui (Radix primitives)                    |
| Linting / formatting | ESLint (flat config) + Prettier                 |
| Testing              | Vitest + React Testing Library (jsdom)          |

## Prerequisites

- Node.js ≥ 18.18 (developed on Node 22)
- npm

## Getting started

```bash
npm install
cp .env.example .env.local   # optional — every value has a safe default
npm run dev                  # http://localhost:3000
```

## Scripts

| Script                 | Purpose                                   |
| ---------------------- | ----------------------------------------- |
| `npm run dev`          | Start the dev server (Turbopack)          |
| `npm run build`        | Production build (`output: "standalone"`) |
| `npm start`            | Serve the production build                |
| `npm run lint`         | ESLint                                    |
| `npm run lint:fix`     | ESLint with autofix                       |
| `npm run typecheck`    | `tsc --noEmit`                            |
| `npm run format`       | Prettier write                            |
| `npm run format:check` | Prettier check                            |
| `npm run test`         | Vitest (run once)                         |
| `npm run test:watch`   | Vitest (watch)                            |
| `npm run check`        | lint + format check + typecheck + test    |

## Configuration

Public configuration is read through [`src/config/env.ts`](./src/config/env.ts), which
provides safe defaults for every value — so the app boots with no `.env` file in local /
single-tenant demo mode. See [`.env.example`](./.env.example) for the variables.

## Structure

```
src/
├── app/          # Next.js App Router (routes, layouts, boundaries)
├── components/   # ui/ (shadcn) + common/ feedback/ data/ forms/
├── features/     # per-domain business modules (built in Stages 4-7)
├── lib/          # api/ auth/ theme/ format/ utils
├── providers/    # React context providers
├── stores/       # Zustand stores
├── hooks/        # shared hooks
└── config/       # typed env + constants
tests/            # Vitest setup + tests
```

Folders that are populated in later milestones currently hold a `.gitkeep`.

## Absolute imports

The `@/*` alias maps to `src/*` (see `tsconfig.json`) and resolves identically in the app,
in ESLint, and in Vitest (`vite-tsconfig-paths`).

## What is intentionally absent in Milestone 1

No pages beyond a placeholder, no business logic, no backend calls, no auth. Those are added
in Milestones 2–6 per [`ARCHITECTURE.md`](./ARCHITECTURE.md).

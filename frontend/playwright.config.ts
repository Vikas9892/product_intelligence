import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright end-to-end config. Tests live in `e2e/`.
 *
 * The suite runs against a **production build**, not the dev server. That is
 * deliberate: `next dev` compiles each route on first request, so several
 * parallel workers hitting cold routes produced multi-second first paints and
 * intermittent assertion timeouts that had nothing to do with the application.
 * A built server serves every route immediately, which removes that entire
 * class of flake and matches how the app actually runs in production.
 *
 * The build is preceded by a clean (`build:clean`). A leftover `.next` from a
 * previous run can make Next fail with `EINVAL: readlink` on this project's
 * OneDrive-synced path — it reads as a build failure but is purely stale
 * state, and it took the whole suite down with it more than once. The clean is
 * plain `fs.rmSync` via node, so it stays cross-platform.
 *
 * The trade-off is an up-front build (~20s). `reuseExistingServer` keeps that
 * cost off repeat local runs when a server is already listening.
 *
 * It is served the way production will be. `next.config.ts` sets
 * `output: "standalone"`, and `next start` does NOT support that mode — it
 * warns and serves incorrectly, which made every route look like it had a
 * layout fault. The standalone server is launched directly instead, after
 * copying `.next/static` and `public/` beside it, which is precisely what a
 * container image has to do.
 *
 * Backend calls are intercepted per-spec via `page.route`, so the suite is
 * self-contained and does not require the API to be up.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: "list",
  use: {
    baseURL: "http://localhost:3000",
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "npm run build:clean && npm run start:standalone",
    url: "http://localhost:3000",
    reuseExistingServer: !process.env.CI,
    // Generous: covers the production build plus server start.
    timeout: 300_000,
  },
});

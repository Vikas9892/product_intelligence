import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright end-to-end config. Tests live in `e2e/` and run against the dev
 * server (started automatically). The smoke suite exercises the app shell,
 * navigation, and theming — flows that do not require the backend. Run with
 * `npm run e2e` (first time: `npx playwright install chromium`).
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
    command: "npm run dev",
    url: "http://localhost:3000",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});

import { expect, test, type ConsoleMessage, type Page } from "@playwright/test";

/**
 * Release gate: cross-cutting checks that must hold on every route before the
 * frontend is considered shippable.
 *
 * These are the failures a manual click-through reliably misses — a hydration
 * mismatch that self-corrects visually, a 404 on a chunk, a React key warning
 * that only appears in one branch. They are cheap to assert and expensive to
 * discover later.
 */

const ROUTES = [
  "/",
  "/upload",
  "/search",
  "/duplicates",
  "/recommendations",
  "/pricing",
  "/analytics",
  "/models",
  "/system",
  "/enterprise",
];

function json(body: unknown, status = 200) {
  return { status, contentType: "application/json", body: JSON.stringify(body) };
}

/**
 * Every backend call answered, so a console error can only come from the app
 * itself rather than from an unreachable API.
 */
async function stubBackend(page: Page) {
  await page.route("**/api/v1/**", async (route) => {
    const url = route.request().url();
    if (url.includes("/system/health"))
      return route.fulfill(
        json({
          redis: "healthy",
          qdrant: "healthy",
          workers: 4,
          queue_depth: 0,
          active_models: 3,
          uptime: "1:00:00",
        }),
      );
    if (url.includes("/system/stats"))
      return route.fulfill(
        json({
          uptime: "1:00:00",
          uptime_seconds: 3600,
          worker_concurrency: 4,
          queue_depth: 0,
          jobs_in_flight: 0,
          dead_letter_size: 0,
          active_models: 3,
          registered_models: 3,
        }),
      );
    if (url.includes("/analytics/dashboard") || url.includes("/analytics/pipeline")) {
      const usage = {
        uploads: 3,
        duplicate_checks: 1,
        recommendations: 3,
        searches: 12,
        average_processing_seconds: 96.5,
      };
      return route.fulfill(
        json(
          url.includes("dashboard")
            ? {
                today: usage,
                window: usage,
                window_days: 7,
                active_models: 3,
                generated_at: "2026-08-02T00:00:00Z",
              }
            : {
                period: "pipeline_window",
                start_date: "2026-07-26",
                end_date: "2026-08-02",
                usage,
                generated_at: "2026-08-02T00:00:00Z",
              },
        ),
      );
    }
    if (url.includes("/analytics/trends"))
      return route.fulfill(
        json({
          metric: "upload",
          granularity: "daily",
          points: [{ period_start: "2026-08-01", value: 3 }],
          generated_at: "",
        }),
      );
    if (url.includes("/analytics/models"))
      return route.fulfill(
        json({ models: [], window: {}, window_days: 7, generated_at: "2026-08-02T00:00:00Z" }),
      );
    if (url.includes("/models")) return route.fulfill(json([]));
    if (url.includes("/usage"))
      return route.fulfill(
        json({
          tenant_id: "t1",
          requests_today: 1,
          daily_request_quota: 10000,
          rate_limit_per_minute: 120,
        }),
      );
    if (url.includes("/api-keys")) return route.fulfill(json([]));
    if (url.includes("/audit")) return route.fulfill(json([]));
    return route.fulfill(json({ results: [] }));
  });
}

/** Console noise that is not the application's fault. */
function isIgnorable(message: ConsoleMessage): boolean {
  const text = message.text();
  return (
    // React DevTools nag, emitted by React itself in development builds.
    text.includes("Download the React DevTools") ||
    // Next's dev overlay bootstrap.
    text.includes("next-dev-tools")
  );
}

for (const route of ROUTES) {
  test(`${route} loads with a clean console`, async ({ page }) => {
    const errors: string[] = [];
    const warnings: string[] = [];

    page.on("console", (message) => {
      if (isIgnorable(message)) return;
      if (message.type() === "error") errors.push(message.text());
      if (message.type() === "warning") warnings.push(message.text());
    });
    page.on("pageerror", (error) => errors.push(`uncaught: ${error.message}`));

    await stubBackend(page);
    await page.goto(route);
    await expect(page.locator("body")).toBeVisible();
    // Let effects, queries and lazily-imported chunks settle.
    await page.waitForLoadState("networkidle");

    expect(errors, `console errors on ${route}:\n${errors.join("\n")}`).toHaveLength(0);

    // Hydration mismatches surface as warnings and often self-correct on
    // screen, which is exactly why they need asserting rather than eyeballing.
    const hydration = warnings.filter(
      (w) => /hydrat/i.test(w) || /did not match/i.test(w) || /server HTML/i.test(w),
    );
    expect(hydration, `hydration warnings on ${route}:\n${hydration.join("\n")}`).toHaveLength(0);
  });
}

test("no request fails while loading the app shell", async ({ page }) => {
  const failed: string[] = [];
  page.on("requestfailed", (request) => {
    // Intercepted routes are aborted by design in other specs; here everything
    // is fulfilled, so any failure is real.
    failed.push(`${request.method()} ${request.url()} — ${request.failure()?.errorText}`);
  });
  page.on("response", (response) => {
    if (response.status() >= 400) failed.push(`${response.status()} ${response.url()}`);
  });

  await stubBackend(page);
  await page.goto("/");
  await page.waitForLoadState("networkidle");

  expect(failed, `failed requests:\n${failed.join("\n")}`).toHaveLength(0);
});

test("both themes render without console errors", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (m) => {
    if (m.type() === "error" && !isIgnorable(m)) errors.push(m.text());
  });

  await stubBackend(page);
  for (const scheme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme: scheme });
    await page.goto("/system");
    await expect(page.getByText("System operations")).toBeVisible();
  }

  expect(errors, `theme errors:\n${errors.join("\n")}`).toHaveLength(0);
});

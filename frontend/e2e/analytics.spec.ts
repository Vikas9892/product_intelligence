import { expect, test } from "@playwright/test";

/** Real `/analytics/*` and `/system/stats` payloads captured from the backend. */
const DASHBOARD = {
  today: {
    uploads: 3,
    duplicate_checks: 1,
    recommendations: 3,
    searches: 4,
    average_processing_seconds: 96.4843,
  },
  window: {
    uploads: 3,
    duplicate_checks: 1,
    recommendations: 3,
    searches: 12,
    average_processing_seconds: 96.4843,
  },
  window_days: 7,
  active_models: 3,
  generated_at: "2026-08-01T03:13:50.751617Z",
};

const PIPELINE = {
  period: "pipeline_window",
  start_date: "2026-07-26",
  end_date: "2026-08-01",
  usage: {
    uploads: 3,
    duplicate_checks: 1,
    recommendations: 3,
    searches: 12,
    average_processing_seconds: 96.4843,
  },
  generated_at: "2026-08-01T03:13:51.036771Z",
};

const MODELS = {
  models: [
    {
      model_type: "image_embedding",
      active_model: "openai/clip-vit-base-patch32",
      active_version: "1.0.0",
      status: "active",
      registered_versions: 1,
    },
    {
      model_type: "text_embedding",
      active_model: "BAAI/bge-small-en-v1.5",
      active_version: "1.0.0",
      status: "active",
      registered_versions: 1,
    },
  ],
  window: PIPELINE.usage,
  window_days: 7,
  generated_at: "2026-08-01T03:13:51.340244Z",
};

const STATS = {
  uptime: "0:16:01",
  uptime_seconds: 961,
  worker_concurrency: 4,
  queue_depth: 0,
  jobs_in_flight: 0,
  dead_letter_size: 0,
  active_models: 3,
  registered_models: 3,
};

function trendBody(metric: string) {
  return {
    metric,
    granularity: "daily",
    points: [
      { period_start: "2026-07-30", value: 0.0 },
      { period_start: "2026-07-31", value: 3.0 },
      { period_start: "2026-08-01", value: 2.0 },
    ],
    generated_at: "2026-08-01T13:40:05.942334Z",
  };
}

test.beforeEach(async ({ page }) => {
  const json = (body: unknown) => ({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(body),
  });

  await page.route("**/api/v1/analytics/dashboard", (r) => r.fulfill(json(DASHBOARD)));
  await page.route("**/api/v1/analytics/pipeline", (r) => r.fulfill(json(PIPELINE)));
  await page.route("**/api/v1/analytics/models", (r) => r.fulfill(json(MODELS)));
  await page.route("**/api/v1/system/stats", (r) => r.fulfill(json(STATS)));
  await page.route("**/api/v1/analytics/trends*", (route) => {
    const metric = new URL(route.request().url()).searchParams.get("metric") ?? "upload";
    return route.fulfill(json(trendBody(metric)));
  });
});

test("shows usage counters for the reported window", async ({ page }) => {
  await page.goto("/analytics");
  await expect(page.getByRole("heading", { name: "AI Analytics" })).toBeVisible();

  await expect(page.getByText("Searches", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("12", { exact: true }).first()).toBeVisible();
  await expect(page.getByText(/4 today · 7-day window/)).toBeVisible();
});

test("shows latency and pipeline throughput, and is explicit about per-stage gaps", async ({
  page,
}) => {
  await page.goto("/analytics");

  await expect(page.getByText("Latency & pipeline throughput")).toBeVisible();
  await expect(page.getByText("96.48s")).toBeVisible();
  await expect(page.getByText("Queue depth")).toBeVisible();
  await expect(page.getByText("Dead letter")).toBeVisible();

  // The honest note: no per-stage embedding/retrieval latency is invented.
  await expect(
    page.getByText(/Per-stage embedding and retrieval latencies are not exposed/),
  ).toBeVisible();
});

test("renders a trend chart per countable event", async ({ page }) => {
  await page.goto("/analytics");

  await expect(page.getByText("Event trends")).toBeVisible();
  for (const label of ["Uploads", "Searches", "Duplicate checks", "Recommendations"]) {
    await expect(page.getByText(label, { exact: true }).last()).toBeVisible();
  }
  // Four charts, one per metric.
  await expect(page.locator(".recharts-surface")).toHaveCount(4);
});

test("granularity and period controls drive the trends", async ({ page }) => {
  await page.goto("/analytics");

  await page.getByLabel("Granularity").click();
  await page.getByRole("option", { name: "weekly" }).click();
  await expect(page.getByLabel("Granularity")).toContainText("weekly");

  await page.getByLabel("Periods").click();
  await page.getByRole("option", { name: "Last 30" }).click();
  await expect(page.getByLabel("Periods")).toContainText("Last 30");
});

test("lists the models in use", async ({ page }) => {
  await page.goto("/analytics");

  await expect(page.getByText("Models in use (2)")).toBeVisible();
  const table = page.getByRole("table");
  await expect(table.getByText("openai/clip-vit-base-patch32")).toBeVisible();
  await expect(table.getByText("BAAI/bge-small-en-v1.5")).toBeVisible();
});

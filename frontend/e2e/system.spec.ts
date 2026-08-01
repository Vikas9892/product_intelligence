import { expect, test } from "@playwright/test";

/** Real `/system/health` and `/system/stats` payloads from the backend. */
const HEALTHY = {
  redis: "healthy",
  qdrant: "healthy",
  workers: 4,
  queue_depth: 0,
  active_models: 3,
  uptime: "23:19:51",
};

const STATS = {
  uptime: "23:19:51",
  uptime_seconds: 83991,
  worker_concurrency: 4,
  queue_depth: 0,
  jobs_in_flight: 0,
  dead_letter_size: 0,
  active_models: 3,
  registered_models: 3,
};

const MODELS = [
  {
    model_name: "openai/clip-vit-base-patch32",
    version: "1.0.0",
    model_type: "image_embedding",
    status: "active",
    dimension: 512,
    description: "",
    provider: "Hugging Face",
    created_at: "2026-07-31T03:02:15.122034Z",
  },
  {
    model_name: "BAAI/bge-small-en-v1.5",
    version: "1.0.0",
    model_type: "text_embedding",
    status: "active",
    dimension: 384,
    description: "",
    provider: "Hugging Face",
    created_at: "2026-07-31T03:02:15.122034Z",
  },
  {
    model_name: "cross-encoder/ms-marco-MiniLM-L-6-v2",
    version: "1.0.0",
    model_type: "reranker",
    status: "active",
    dimension: 1,
    description: "",
    provider: "Hugging Face",
    created_at: "2026-07-31T03:02:15.122034Z",
  },
];

function stubSystem(page: import("@playwright/test").Page, health: unknown) {
  const json = (body: unknown) => ({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
  return Promise.all([
    page.route("**/api/v1/system/health", (r) => r.fulfill(json(health))),
    page.route("**/api/v1/system/stats", (r) => r.fulfill(json(STATS))),
    page.route("**/api/v1/models", (r) => r.fulfill(json(MODELS))),
  ]);
}

test("reports API, Redis, Qdrant, queue depth, uptime and models", async ({ page }) => {
  await stubSystem(page, HEALTHY);
  await page.goto("/system");

  await expect(page.getByRole("heading", { name: "System" })).toBeVisible();
  await expect(page.getByText("All systems operational")).toBeVisible();

  await expect(page.getByText("API", { exact: true })).toBeVisible();
  await expect(page.getByText("Redis", { exact: true })).toBeVisible();
  await expect(page.getByText("Qdrant", { exact: true })).toBeVisible();
  await expect(page.getByText("Queue depth")).toBeVisible();
  await expect(page.getByText("23:19:51").first()).toBeVisible();
});

test("labels worker concurrency as configured, never as live workers", async ({ page }) => {
  await stubSystem(page, HEALTHY);
  await page.goto("/system");

  // The backend's own docstring says this is configured concurrency, not a
  // process count — the label must not claim otherwise.
  await expect(page.getByText("Configured workers")).toBeVisible();
  await expect(page.getByText("Active workers")).toBeHidden();
  await expect(page.getByText("Running workers")).toBeHidden();
  await expect(page.getByText("Live workers")).toBeHidden();

  await page.getByRole("button", { name: "About Configured workers" }).hover();
  await expect(page.getByText(/NOT a count of running worker processes/)).toBeVisible();
});

test("Redis unavailable: degrades, and stops trusting the queue depth", async ({ page }) => {
  await stubSystem(page, { ...HEALTHY, redis: "unhealthy" });
  await page.goto("/system");

  await expect(page.getByText("Degraded")).toBeVisible();
  await expect(page.getByText("Unavailable").first()).toBeVisible();

  // queue_depth still arrives as 0, but that is the backend's failure
  // fallback, so it must be reported as unknown rather than as an empty queue.
  await expect(page.getByText("Unknown").first()).toBeVisible();
});

test("Qdrant unavailable is reported without hiding the rest", async ({ page }) => {
  await stubSystem(page, { ...HEALTHY, qdrant: "unhealthy" });
  await page.goto("/system");

  await expect(page.getByText("Degraded")).toBeVisible();
  // Redis is fine, so the queue depth is still a real reading.
  await expect(page.getByText("Configured workers")).toBeVisible();
});

test("an unrecognised health value is Unknown, not assumed healthy", async ({ page }) => {
  await stubSystem(page, { ...HEALTHY, qdrant: "something-new" });
  await page.goto("/system");

  await expect(page.getByText("Unknown").first()).toBeVisible();
  await expect(page.getByText("All systems operational")).toBeHidden();
});

test("lists the model registry with versions and dimensions", async ({ page }) => {
  await stubSystem(page, HEALTHY);
  await page.goto("/system");

  await expect(page.getByText("Model registry").first()).toBeVisible();
  const table = page.getByRole("table");
  await expect(table.getByText("openai/clip-vit-base-patch32")).toBeVisible();
  await expect(table.getByText("BAAI/bge-small-en-v1.5")).toBeVisible();
  await expect(table.getByText("cross-encoder/ms-marco-MiniLM-L-6-v2")).toBeVisible();
  await expect(table.getByText("512")).toBeVisible();
});

test("does not parse Prometheus text into invented metrics", async ({ page }) => {
  await stubSystem(page, HEALTHY);
  await page.goto("/system");

  await expect(page.getByText(/Raw Prometheus metrics are exposed at/)).toBeVisible();
  await expect(page.getByText(/They are not read here/)).toBeVisible();
});

test("health endpoint failure shows an error, not a fake healthy state", async ({ page }) => {
  await page.route("**/api/v1/system/health", (route) => route.abort("failed"));
  await page.route("**/api/v1/system/stats", (route) => route.abort("failed"));
  await page.route("**/api/v1/models", (route) => route.abort("failed"));
  await page.goto("/system");

  await expect(page.getByText("Couldn't reach the system health endpoint")).toBeVisible();
  await expect(page.getByText("All systems operational")).toBeHidden();
});

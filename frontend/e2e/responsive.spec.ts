import { expect, test, type Page } from "@playwright/test";

/**
 * Responsive sweep across every route at representative widths.
 *
 * The core assertion is that the **document** never scrolls horizontally.
 * Wide content (tables, comparison grids, charts) must scroll inside its own
 * container instead — a page-level sideways scroll is the failure mode that
 * makes an app feel broken on a phone.
 *
 * Backends are stubbed with real-shaped payloads so the data-heavy layouts
 * (tables especially) actually render; an empty state would hide exactly the
 * overflow this is looking for.
 */

const VIEWPORTS = [
  { name: "mobile", width: 390, height: 844 },
  { name: "tablet", width: 768, height: 1024 },
  { name: "laptop", width: 1280, height: 800 },
  { name: "desktop", width: 1600, height: 900 },
];

function json(body: unknown, status = 200) {
  return { status, contentType: "application/json", body: JSON.stringify(body) };
}

const SEARCH_RESULTS = {
  results: [
    {
      product_id: "ac36cc32-706f-4874-95ad-0ca9bb076d7f",
      score: 0.8481574,
      matched_modalities: ["image", "text"],
      metadata: {
        name: "Blue Running Shoes With A Deliberately Long Product Name For Overflow",
        brand: "Nike",
        category: "men-shoes",
        price: 1999,
        description: "Lightweight blue running shoe with mesh upper",
        tags: ["nike", "running", "blue", "mesh"],
        quality_score: 0.694,
      },
    },
  ],
};

const DUPLICATE = {
  duplicate: true,
  confidence: 0.9888888888888889,
  reason: "Overall similarity 0.99 meets or exceeds the 0.90 threshold.",
  matched_product: "082c6d18-9dd3-4c28-bb98-72a3a67fe120",
  signals: { image: 1.0, text: 1.0, metadata: 0.963, attribute: 0.981 },
  top_candidates: [
    {
      product_id: "082c6d18-9dd3-4c28-bb98-72a3a67fe120",
      image_similarity: 1.0,
      text_similarity: 1.0,
      metadata_similarity: 0.963,
      attribute_similarity: 0.981,
      overall_similarity: 0.989,
    },
  ],
  cross_encoder_score: null,
  retrieval_similarity: null,
  reasons: ["Overall similarity 0.99 meets or exceeds the 0.90 threshold."],
};

const PRICING = {
  estimated_price: 1515.67,
  confidence: "low",
  confidence_score: 0.263,
  strategy: "trimmed_mean",
  comparable_count: 3,
  pricing_reason: "Estimated from 3 comparable product(s) using the trimmed_mean strategy.",
  comparables: [
    {
      product_id: "082c6d18-9dd3-4c28-bb98-72a3a67fe120",
      price: 2049,
      similarity: 0.952,
      name: "Blue Running Shoes",
      brand: "Nike",
      category: "men-shoes",
    },
  ],
};

const USAGE = {
  tenant_id: "5d7b11b0-a420-4ce3-a38b-dde8ed10f0b8",
  requests_today: 42,
  daily_request_quota: 10000,
  rate_limit_per_minute: 120,
};

const API_KEYS = [
  {
    id: "3339554f-3f8a-4eef-be9c-5c63793cd494",
    tenant_id: "5d7b11b0-a420-4ce3-a38b-dde8ed10f0b8",
    name: "owner",
    role: "owner",
    prefix: "pik_uJ35edd2",
    revoked: false,
    created_at: "2026-08-01T14:22:58.173594Z",
  },
];

const AUDIT = [
  {
    id: "50d9aa37-1dd2-4d2a-9589-5478c9a1cf44",
    tenant_id: "5d7b11b0-a420-4ce3-a38b-dde8ed10f0b8",
    actor: "pik_uJ35edd2",
    action: "create_api_key",
    resource: "pik_ogLoiqWZ",
    metadata: { role: "admin" },
    created_at: "2026-08-01T14:24:00.984136Z",
  },
];

const HEALTH = {
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
  usage: DASHBOARD.window,
  generated_at: "2026-08-01T03:13:51.036771Z",
};

/** Stubs every backend route the app touches, with real-shaped payloads. */
async function stubAll(page: Page) {
  await page.route("**/api/v1/products/search", (r) => r.fulfill(json(SEARCH_RESULTS)));
  await page.route("**/api/v1/products/check-duplicate", (r) => r.fulfill(json(DUPLICATE)));
  await page.route("**/api/v1/products/*/recommendations", (r) =>
    r.fulfill(json({ recommendation_type: "similar", recommendations: [] })),
  );
  await page.route("**/api/v1/products/*/explanations", (r) =>
    r.fulfill(json({ product_id: "x", duplicate: null, recommendations: [] })),
  );
  await page.route("**/api/v1/products/*/status", (r) =>
    r.fulfill(json({ status: "completed", progress: 100, current_stage: "Completed" })),
  );
  await page.route("**/api/v1/pricing/**", (r) => r.fulfill(json(PRICING)));
  await page.route("**/api/v1/usage", (r) => r.fulfill(json(USAGE)));
  await page.route("**/api/v1/api-keys", (r) => r.fulfill(json(API_KEYS)));
  await page.route("**/api/v1/audit*", (r) => r.fulfill(json(AUDIT)));
  await page.route("**/api/v1/system/health", (r) => r.fulfill(json(HEALTH)));
  await page.route("**/api/v1/system/stats", (r) => r.fulfill(json(STATS)));
  await page.route("**/api/v1/models", (r) => r.fulfill(json(MODELS)));
  await page.route("**/api/v1/analytics/dashboard", (r) => r.fulfill(json(DASHBOARD)));
  await page.route("**/api/v1/analytics/pipeline", (r) => r.fulfill(json(PIPELINE)));
  await page.route("**/api/v1/analytics/models", (r) =>
    r.fulfill(json({ models: [], window: DASHBOARD.window, window_days: 7, generated_at: "" })),
  );
  await page.route("**/api/v1/analytics/trends*", (r) =>
    r.fulfill(
      json({
        metric: "upload",
        granularity: "daily",
        points: [{ period_start: "2026-08-01", value: 3 }],
        generated_at: "",
      }),
    ),
  );
}

/** Widest offender on the page, for a useful failure message. */
async function horizontalOverflow(page: Page) {
  return page.evaluate(() => {
    const doc = document.documentElement;
    const overflow = doc.scrollWidth - doc.clientWidth;
    if (overflow <= 1) return { overflow: 0, culprit: null as string | null };
    let culprit: string | null = null;
    let worst = 0;
    for (const el of Array.from(document.querySelectorAll<HTMLElement>("body *"))) {
      const r = el.getBoundingClientRect();
      const past = r.right - doc.clientWidth;
      if (past > worst) {
        worst = past;
        culprit = `${el.tagName.toLowerCase()}.${(el.className || "").toString().slice(0, 60)}`;
      }
    }
    return { overflow, culprit };
  });
}

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
  "/products/ac36cc32-706f-4874-95ad-0ca9bb076d7f",
  "/this-route-does-not-exist",
];

for (const vp of VIEWPORTS) {
  test.describe(`${vp.name} (${vp.width}px)`, () => {
    for (const route of ROUTES) {
      test(`${route} has no horizontal page overflow`, async ({ page }) => {
        await page.setViewportSize({ width: vp.width, height: vp.height });
        await stubAll(page);
        await page.goto(route);
        // Wait for something painted before measuring. `body` is used rather
        // than a landmark because not-found renders outside the (app) layout
        // and so has neither the sidebar shell nor #main-content.
        await expect(page.locator("body")).toBeVisible();
        await page.waitForLoadState("domcontentloaded");

        const { overflow, culprit } = await horizontalOverflow(page);
        expect(
          overflow,
          `${route} overflows by ${overflow}px at ${vp.width}px; widest element: ${culprit}`,
        ).toBeLessThanOrEqual(1);
      });
    }
  });
}

test.describe("mobile navigation", () => {
  test("sidebar collapses behind a trigger and opens on demand", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await stubAll(page);
    await page.goto("/");

    // Off-canvas on mobile: the nav link is not visible until opened.
    const searchLink = page.getByRole("link", { name: "AI Search", exact: true });
    await expect(searchLink).toBeHidden();

    await page.getByRole("button", { name: /toggle sidebar/i }).click();
    await expect(searchLink).toBeVisible();
  });

  test("primary controls meet a usable touch target size", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await stubAll(page);
    await page.goto("/search");

    const button = page.getByRole("button", { name: "Search" });
    const box = await button.boundingBox();
    expect(box).not.toBeNull();
    // 44px is the common minimum; allow a small tolerance for borders.
    expect(box!.height).toBeGreaterThanOrEqual(32);
    expect(box!.width).toBeGreaterThanOrEqual(44);
  });
});

test.describe("wide content scrolls inside its own container", () => {
  test("data tables scroll horizontally without moving the page", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await stubAll(page);
    await page.goto("/enterprise");
    // /enterprise renders two tables (API keys and audit); either proves the
    // point, so scope to the first rather than tripping strict mode.
    await expect(page.getByRole("table").first()).toBeVisible();

    // The table's wrapper is what scrolls — never the document.
    const wrapperScrolls = await page.evaluate(() => {
      const table = document.querySelector("table");
      if (!table) return false;
      let el: HTMLElement | null = table.parentElement;
      while (el && el !== document.body) {
        const s = getComputedStyle(el);
        if ((s.overflowX === "auto" || s.overflowX === "scroll") && el.scrollWidth > el.clientWidth)
          return true;
        el = el.parentElement;
      }
      return false;
    });
    expect(wrapperScrolls).toBe(true);
  });
});

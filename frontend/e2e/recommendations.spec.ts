import { expect, test } from "@playwright/test";

/**
 * E2E for the recommendation explorer. Payloads mirror real
 * `POST /products/search` and `GET /products/{id}/recommendations` responses.
 */
const TARGET_ID = "ac36cc32-706f-4874-95ad-0ca9bb076d7f";
const STRONG_ID = "082c6d18-9dd3-4c28-bb98-72a3a67fe120";
const WEAK_ID = "b926f921-5b1d-45eb-8320-67cab7f4e9d5";

const SEARCH_BODY = {
  results: [
    {
      product_id: TARGET_ID,
      score: 0.848,
      matched_modalities: ["text"],
      metadata: {
        name: "Blue Running Shoes",
        brand: "Nike",
        category: "men-shoes",
        price: 1999.0,
        description: "Lightweight blue running shoe with mesh upper",
        tags: ["nike"],
      },
    },
    {
      product_id: STRONG_ID,
      score: 0.84,
      matched_modalities: ["text"],
      metadata: { name: "Blue Running Shoes", brand: "Nike", category: "men-shoes", tags: [] },
    },
  ],
};

const RECOMMENDATIONS_BODY = {
  recommendation_type: "similar",
  recommendations: [
    {
      product_id: STRONG_ID,
      score: 0.9693148348893941,
      reason: {
        matched_attributes: ["color", "material", "gender", "style"],
        matched_tags: ["blue", "mesh", "nike", "running"],
        shared_brand: true,
        shared_category: true,
      },
      explanation: "Similar visual appearance; same category; same brand; shared attributes.",
    },
    {
      product_id: WEAK_ID,
      score: 0.5297858656768398,
      reason: {
        matched_attributes: [],
        matched_tags: ["bright", "square"],
        shared_brand: false,
        shared_category: false,
      },
      explanation: "Similar visual appearance; matching tags (bright, square).",
    },
  ],
};

function routeRecommendations(page: import("@playwright/test").Page, body: unknown) {
  return page.route("**/api/v1/products/*/recommendations", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });
}

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/products/search", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      headers: { "x-response-time-ms": "31.20" },
      body: JSON.stringify(SEARCH_BODY),
    });
  });
});

async function selectProduct(page: import("@playwright/test").Page) {
  await page.goto("/recommendations");
  await expect(page.getByRole("heading", { name: "Recommendations" })).toBeVisible();
  await page.getByLabel("Product search").fill("blue running shoe");
  await page.getByRole("button", { name: "Search" }).click();
  await page.getByRole("list", { name: "Products" }).getByRole("button").first().click();
}

test("shows recommendation cards with reasons, overlap, and score", async ({ page }) => {
  await routeRecommendations(page, RECOMMENDATIONS_BODY);
  await selectProduct(page);

  await expect(page.getByText("Showing 2 of 2 recommendations")).toBeVisible();

  const list = page.getByRole("list", { name: "Recommendations" });
  await expect(list.getByText(/same category; same brand/)).toBeVisible();
  await expect(list.getByText("Matched attributes (4)")).toBeVisible();
  await expect(list.getByText("Matched tags (4)")).toBeVisible();
  await expect(list.getByText(/High · 0\.97/)).toBeVisible();
});

test("filters by overlap and can empty the set explicably", async ({ page }) => {
  await routeRecommendations(page, RECOMMENDATIONS_BODY);
  await selectProduct(page);

  // Each toggle advertises how many of the set satisfy it.
  const brandFilter = page.getByRole("button", { name: /Same brand 1\/2/ });
  await expect(brandFilter).toBeVisible();
  await brandFilter.click();

  await expect(page.getByText("Showing 1 of 2 recommendations")).toBeVisible();

  // Un-toggling restores the full set.
  await brandFilter.click();
  await expect(page.getByText("Showing 2 of 2 recommendations")).toBeVisible();

  // A score floor above the weaker recommendation narrows it again. The
  // underlying set is unchanged — only what is displayed.
  await page.getByLabel("Min score").click();
  await page.getByRole("option", { name: "≥ 0.75" }).click();
  await expect(page.getByText("Showing 1 of 2 recommendations")).toBeVisible();
});

test("sorting re-orders without changing the set", async ({ page }) => {
  await routeRecommendations(page, RECOMMENDATIONS_BODY);
  await selectProduct(page);

  const list = page.getByRole("list", { name: "Recommendations" });
  await expect(list.getByRole("listitem").first()).toContainText("Matched attributes (4)");

  await page.getByRole("button", { name: "Sort descending" }).click();
  await expect(page.getByText("Showing 2 of 2 recommendations")).toBeVisible();
  await expect(list.getByRole("listitem").first()).not.toContainText("Matched attributes (4)");
});

test("explains an empty result as a precomputed-cache cold start", async ({ page }) => {
  await routeRecommendations(page, { recommendation_type: "similar", recommendations: [] });
  await selectProduct(page);

  await expect(page.getByText("No recommendations for this product")).toBeVisible();
  await expect(page.getByText(/precomputed by the worker/)).toBeVisible();
  await expect(page.getByText(/cached for an hour/)).toBeVisible();
});

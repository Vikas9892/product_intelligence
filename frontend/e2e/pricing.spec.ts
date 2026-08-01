import { expect, test } from "@playwright/test";

/** A real `POST /pricing/estimate` response captured from the backend. */
const PRICING_BODY = {
  estimated_price: 1515.67,
  confidence: "low",
  confidence_score: 0.263,
  strategy: "trimmed_mean",
  comparable_count: 3,
  pricing_reason:
    "Estimated from 3 comparable product(s) using the trimmed_mean strategy (low confidence).",
  comparables: [
    {
      product_id: "082c6d18-9dd3-4c28-bb98-72a3a67fe120",
      price: 2049.0,
      similarity: 0.9521787,
      name: "Blue Running Shoes",
      brand: "Nike",
      category: "men-shoes",
    },
    {
      product_id: "ac36cc32-706f-4874-95ad-0ca9bb076d7f",
      price: 1999.0,
      similarity: 0.9521787,
      name: "Blue Running Shoes",
      brand: "Nike",
      category: "men-shoes",
    },
    {
      product_id: "b926f921-5b1d-45eb-8320-67cab7f4e9d5",
      price: 499.0,
      similarity: 0.4222116,
      name: "Red Ceramic Mug",
      brand: "Corelle",
      category: "kitchenware",
    },
  ],
};

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/pricing/estimate", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      headers: { "x-response-time-ms": "8930.12" },
      body: JSON.stringify(PRICING_BODY),
    });
  });
});

async function estimate(page: import("@playwright/test").Page) {
  await page.goto("/pricing");
  await expect(page.getByRole("heading", { name: "Pricing Intelligence" })).toBeVisible();
  await page.getByLabel("Name").fill("Blue Running Shoes");
  await page.getByRole("button", { name: "Estimate price" }).click();
}

test("shows the estimate with its confidence, strategy, and backend reason", async ({ page }) => {
  await estimate(page);

  // Exact: the chart's reference line is also labelled "Estimate 1,515.67".
  await expect(page.getByText("1,515.67", { exact: true })).toBeVisible();
  await expect(page.getByText("Estimate 1,515.67")).toBeVisible();
  await expect(page.getByText(/Low · 0\.26/)).toBeVisible();
  await expect(page.getByText("trimmed_mean").first()).toBeVisible();
  await expect(page.getByText(/Estimated from 3 comparable/)).toBeVisible();
});

test("summarizes the spread and labels it as locally computed", async ({ page }) => {
  await estimate(page);

  await expect(page.getByText("Lowest")).toBeVisible();
  await expect(page.getByText("Median")).toBeVisible();
  await expect(page.getByText("Highest")).toBeVisible();
  // The distinction that matters: this is a summary of the response, not a
  // second estimate from the backend.
  await expect(page.getByText(/computed here for context/)).toBeVisible();
});

test("explains outlier handling without claiming to show removed prices", async ({ page }) => {
  await estimate(page);

  await expect(page.getByText("Outlier handling")).toBeVisible();
  await expect(page.getByText(/Tukey IQR fence/)).toBeVisible();
  await expect(page.getByText(/are not part of the response/)).toBeVisible();
});

test("plots the distribution and lists the comparables as its table view", async ({ page }) => {
  await estimate(page);

  await expect(page.getByText("Price distribution")).toBeVisible();
  // Recharts renders into an SVG inside the chart container.
  await expect(page.locator(".recharts-surface").first()).toBeVisible();

  await expect(page.getByText("Comparable products (3)")).toBeVisible();
  const table = page.getByRole("table");
  await expect(table.getByRole("link", { name: "Red Ceramic Mug" })).toBeVisible();
  await expect(table.getByText("Corelle")).toBeVisible();
});

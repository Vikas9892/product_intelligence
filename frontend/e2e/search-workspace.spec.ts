import { expect, test } from "@playwright/test";

/**
 * E2E for the AI search workspace.
 *
 * The backend search call is intercepted so the suite stays self-contained and
 * deterministic, but the fulfilled payload is the **real** response shape of
 * `POST /products/search` (product_id / score / matched_modalities / metadata),
 * and the timing header is the same `x-response-time-ms` the backend sends —
 * so what the UI renders here is what it renders against the live service.
 */
const SEARCH_ROUTE = "**/api/v1/products/search";

const SEARCH_BODY = {
  results: [
    {
      product_id: "ac36cc32-706f-4874-95ad-0ca9bb076d7f",
      score: 0.8481574,
      matched_modalities: ["text"],
      metadata: {
        name: "Blue Running Shoes",
        brand: "Nike",
        category: "men-shoes",
        price: 1999.0,
        tags: ["nike", "running"],
        quality_score: 0.694,
      },
    },
    {
      product_id: "b926f921-5b1d-45eb-8320-67cab7f4e9d5",
      score: 0.44436413,
      matched_modalities: ["image", "text"],
      metadata: {
        name: "Red Ceramic Mug",
        brand: "Corelle",
        category: "kitchenware",
        price: 499.0,
        tags: ["corelle"],
        quality_score: 0.549,
      },
    },
  ],
};

test.beforeEach(async ({ page }) => {
  await page.route(SEARCH_ROUTE, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      headers: { "x-response-time-ms": "52.77" },
      body: JSON.stringify(SEARCH_BODY),
    });
  });
});

test("runs a text search and renders scores, modalities, and backend latency", async ({ page }) => {
  await page.goto("/search");
  await expect(page.getByRole("heading", { name: "AI Search" })).toBeVisible();

  // Empty state before any search.
  await expect(page.getByText("Search the catalog")).toBeVisible();

  await page.getByLabel("Search query").fill("blue running shoe");
  await page.getByRole("button", { name: "Search" }).click();

  await expect(page.getByText("2 results · text search")).toBeVisible();
  await expect(page.getByText("Blue Running Shoes")).toBeVisible();

  // The latency badge reports the backend's own measurement and says so — the
  // aria-label is the assertion target because "53 ms" also appears in the
  // history entry for the same search.
  await expect(page.getByLabel("Retrieval latency 53 ms, measured by the backend")).toBeVisible();

  // Retrieval provenance straight from matched_modalities. Scoped to the
  // results list, since "Image" is also the name of a search-mode control.
  const results = page.getByRole("list", { name: "Search results" });
  await expect(results.getByText("Image", { exact: true })).toBeVisible();
  await expect(results.getByText("Text", { exact: true }).first()).toBeVisible();
});

test("switches to image mode and requires an image", async ({ page }) => {
  await page.goto("/search");

  await page.getByRole("radio", { name: "Image" }).click();
  await expect(page.getByLabel("Search query")).toBeHidden();
  await expect(page.getByText("Choose an image to search with.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Search by image" })).toBeDisabled();
});

test("records the search in history and can replay it", async ({ page }) => {
  await page.goto("/search");

  await page.getByLabel("Search query").fill("blue running shoe");
  await page.getByRole("button", { name: "Search" }).click();
  await expect(page.getByText("2 results · text search")).toBeVisible();

  // Anchored so it matches the replay button, not the sibling
  // `Remove "blue running shoe" from history` button.
  const history = page.getByRole("button", { name: /^blue running shoe/ });
  await expect(history).toBeVisible();

  // Replaying restores the query and re-runs it.
  await page.getByRole("radio", { name: "Hybrid" }).click();
  await history.click();
  await expect(page.getByLabel("Search query")).toHaveValue("blue running shoe");
});

test("the / shortcut focuses the query box", async ({ page }) => {
  await page.goto("/search");

  // The shortcut is bound in an effect, so wait until React has hydrated —
  // a mode switch only re-renders once the client bundle is live.
  await page.getByRole("radio", { name: "Image" }).click();
  await expect(page.getByText("Choose an image to search with.")).toBeVisible();
  await page.getByRole("radio", { name: "Text" }).click();
  await expect(page.getByLabel("Search query")).toBeVisible();

  await page.locator("body").press("/");
  await expect(page.getByLabel("Search query")).toBeFocused();
});

test("switching to the table view keeps the results", async ({ page }) => {
  await page.goto("/search");
  await page.getByLabel("Search query").fill("shoes");
  await page.getByRole("button", { name: "Search" }).click();
  await expect(page.getByText("2 results · text search")).toBeVisible();

  await page.getByRole("button", { name: "Switch to table view" }).click();
  await expect(page.getByRole("table")).toBeVisible();
  await expect(page.getByRole("cell", { name: /Blue Running Shoes/ })).toBeVisible();
});

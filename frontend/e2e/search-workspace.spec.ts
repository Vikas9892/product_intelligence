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

/**
 * A real explanations payload, copied from a live response. The contributions
 * (0.9998 + 0.6944) deliberately do not sum to `total` (0.9693) — the UI must
 * report the backend's total rather than adding them up.
 */
const EXPLANATIONS_BODY = {
  product_id: "ac36cc32-706f-4874-95ad-0ca9bb076d7f",
  duplicate: {
    decision_type: "duplicate",
    subject_id: "082c6d18-9dd3-4c28-bb98-72a3a67fe120",
    summary:
      "Judged a duplicate because: Overall similarity 1.00 meets or exceeds the 0.90 threshold.",
    confidence: 0.9998867645,
    reasons: [
      {
        code: "weighted_similarity",
        description: "Overall similarity 1.00 meets or exceeds the 0.90 threshold.",
        weight: null,
      },
    ],
    breakdown: null,
    created_at: "2026-07-31T03:13:22.469834Z",
  },
  recommendations: [
    {
      decision_type: "recommendation",
      subject_id: "082c6d18-9dd3-4c28-bb98-72a3a67fe120",
      summary: "Recommended because it shares: the same brand, the same category.",
      confidence: 0.9693148348893941,
      reasons: [
        { code: "shared_brand", description: "the same brand", weight: null },
        { code: "shared_category", description: "the same category", weight: null },
      ],
      breakdown: {
        components: [
          { name: "similarity", value: 0.999773529, weight: 1.0, contribution: 0.999773529 },
          { name: "quality", value: 0.6943939, weight: 1.0, contribution: 0.6943939 },
        ],
        total: 0.9693148348893941,
      },
      created_at: "2026-07-31T03:13:22.570813Z",
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

  await page.route("**/api/v1/products/*/explanations", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(EXPLANATIONS_BODY),
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

test("explains a result from real backend fields only", async ({ page }) => {
  await page.goto("/search");
  await page.getByLabel("Search query").fill("blue running shoe");
  await page.getByRole("button", { name: "Search" }).click();
  await expect(page.getByText("2 results · text search")).toBeVisible();

  const results = page.getByRole("list", { name: "Search results" });
  const firstCard = results.getByRole("listitem").first();

  // Collapsed by default, so a page of results triggers no explanation calls.
  await expect(firstCard.getByText("Why this was retrieved")).toBeHidden();

  await firstCard.getByRole("button", { name: "Why this result?" }).click();

  // What the search response itself carries.
  await expect(firstCard.getByText("Why this was retrieved")).toBeVisible();
  await expect(
    firstCard.getByText("The product text embedding (BGE) matched the query text."),
  ).toBeVisible();
  await expect(firstCard.getByText("Fused relevance score")).toBeVisible();
  await expect(firstCard.getByText("0.8482")).toBeVisible();

  // The recorded decision traces, with the real weighted breakdown. Exact
  // matching: the reason badge "Same brand" and its description "the same
  // brand" would both match a substring locator.
  await expect(firstCard.getByText("Duplicate decision", { exact: true })).toBeVisible();
  await expect(firstCard.getByText("Same brand", { exact: true })).toBeVisible();
  await expect(firstCard.getByText("similarity", { exact: true })).toBeVisible();

  // The total is the backend's reported score, not the sum of contributions.
  await expect(firstCard.getByText("Final 0.97")).toBeVisible();
  await expect(firstCard.getByText("1.69")).toBeHidden();

  // Fields the endpoint does not return are named, not fabricated.
  await expect(firstCard.getByText("Not returned by this endpoint")).toBeVisible();
  await expect(firstCard.getByText("Cross-encoder score")).toBeVisible();
});

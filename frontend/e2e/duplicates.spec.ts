import { expect, test } from "@playwright/test";

/**
 * E2E for Duplicate Intelligence.
 *
 * The intercepted payload is a **real** `POST /products/check-duplicate`
 * response captured from the running backend, including `cross_encoder_score`
 * and `retrieval_similarity` being `null` — the default, because
 * DUPLICATE_VERIFICATION__ENABLED is off. That null is the interesting case:
 * the UI must report the feature as disabled rather than invent a number.
 */
const DUPLICATE_BODY = {
  duplicate: true,
  confidence: 0.9888888888888889,
  reason: "Overall similarity 0.99 meets or exceeds the 0.90 threshold.",
  matched_product: "082c6d18-9dd3-4c28-bb98-72a3a67fe120",
  signals: {
    image: 1.0,
    text: 1.0,
    metadata: 0.9629629629629629,
    attribute: 0.9814814814814815,
  },
  top_candidates: [
    {
      product_id: "082c6d18-9dd3-4c28-bb98-72a3a67fe120",
      image_similarity: 1.0,
      text_similarity: 1.0,
      metadata_similarity: 0.9629629629629629,
      attribute_similarity: 0.9814814814814815,
      overall_similarity: 0.9888888888888889,
    },
    {
      product_id: "b926f921-5b1d-45eb-8320-67cab7f4e9d5",
      image_similarity: 0.9266693,
      text_similarity: 0.45739812,
      metadata_similarity: 0.2818181818181818,
      attribute_similarity: 0.2558441558441558,
      overall_similarity: 0.5462162525324675,
    },
  ],
  cross_encoder_score: null,
  retrieval_similarity: null,
  reasons: ["Overall similarity 0.99 meets or exceeds the 0.90 threshold."],
};

/** The enrichment search that resolves candidate names. */
const SEARCH_BODY = {
  results: [
    {
      product_id: "082c6d18-9dd3-4c28-bb98-72a3a67fe120",
      score: 0.95,
      matched_modalities: ["text"],
      metadata: {
        name: "Blue Running Shoes",
        brand: "Nike",
        category: "men-shoes",
        price: 2049.0,
        tags: [],
      },
    },
  ],
};

/** A tiny valid PNG, so the dropzone's type/size validation genuinely passes. */
const PNG_BASE64 =
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==";

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/products/check-duplicate", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      headers: { "x-response-time-ms": "578.72" },
      body: JSON.stringify(DUPLICATE_BODY),
    });
  });
  await page.route("**/api/v1/products/search", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(SEARCH_BODY),
    });
  });
});

async function submitCheck(page: import("@playwright/test").Page) {
  await page.goto("/duplicates");
  await expect(page.getByRole("heading", { name: "Duplicate Intelligence" })).toBeVisible();

  await page.setInputFiles('input[type="file"]', {
    name: "shoe.png",
    mimeType: "image/png",
    buffer: Buffer.from(PNG_BASE64, "base64"),
  });
  await page.getByLabel("Name").fill("Blue Running Shoes");
  await page.getByLabel("Brand").fill("Nike");
  await page.getByLabel("Category").fill("Men Shoes");
  await page.getByLabel("Price").fill("1999");
  await page.getByRole("button", { name: "Check for duplicates" }).click();
}

test("shows the verdict, confidence, and the four similarity signals", async ({ page }) => {
  await submitCheck(page);

  await expect(page.getByText("Duplicate detected")).toBeVisible();
  await expect(page.getByText(/High · 0\.99/)).toBeVisible();
  await expect(
    page.getByText("Overall similarity 0.99 meets or exceeds the 0.90 threshold.").first(),
  ).toBeVisible();

  // Exact: the cross-encoder "disabled" prose also contains the phrase
  // "weighted similarity signals".
  await expect(page.getByText("Similarity signals", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Image similarity 1.00")).toBeVisible();
  await expect(page.getByLabel("Text similarity 1.00")).toBeVisible();
  await expect(page.getByLabel("Metadata similarity 0.96")).toBeVisible();
  await expect(page.getByLabel("Attribute similarity 0.98")).toBeVisible();
});

test("reports cross-encoder verification as disabled rather than faking a score", async ({
  page,
}) => {
  await submitCheck(page);

  await expect(page.getByText("Cross-encoder verification")).toBeVisible();
  await expect(page.getByText("Disabled on this backend")).toBeVisible();
  await expect(page.getByText(/DUPLICATE_VERIFICATION__ENABLED/)).toBeVisible();
  // No score is rendered, because the backend produced none. Exact matching:
  // the "disabled" prose itself mentions "no cross-encoder score", and
  // getByText does case-insensitive substring matching by default.
  await expect(page.getByText("Cross-encoder score", { exact: true })).toBeHidden();
  await expect(page.getByText("Retrieval similarity", { exact: true })).toBeHidden();
});

test("compares the submitted product against the matched one", async ({ page }) => {
  await submitCheck(page);

  await expect(page.getByText("Side-by-side comparison")).toBeVisible();
  await expect(page.getByText("Metadata differences")).toBeVisible();

  // Name/brand/category were submitted identically; price differs (1999 vs 2049).
  await expect(page.getByText("Differs").first()).toBeVisible();
  await expect(page.getByText("Same").first()).toBeVisible();

  // The backend serves no product images, which the matched side states.
  await expect(page.getByText("The backend serves no product images")).toBeVisible();
});

test("lists every ranked candidate with its per-signal scores", async ({ page }) => {
  await submitCheck(page);

  await expect(page.getByText("Ranked candidates (2)")).toBeVisible();
  const table = page.getByRole("table");
  await expect(table).toBeVisible();
  await expect(table.getByText("Matched")).toBeVisible();
  // The resolved name from the enrichment search.
  await expect(table.getByRole("link", { name: "Blue Running Shoes" })).toBeVisible();
  // A candidate the enrichment search did not return stays honest about it.
  await expect(table.getByText("Unresolved product")).toBeVisible();
});

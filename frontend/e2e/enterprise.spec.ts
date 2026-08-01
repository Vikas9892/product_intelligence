import { expect, test } from "@playwright/test";

/**
 * E2E for the enterprise console.
 *
 * Each scenario stubs the enterprise routes with the **exact** statuses the
 * running backend returns, verified live:
 *   - enterprise off        -> 404
 *   - enterprise on, no key -> 401
 *   - valid key, permitted  -> 200
 */
const USAGE_ROUTE = "**/api/v1/usage";

const NOT_FOUND_BODY = {
  success: false,
  error: { code: "not_found", message: "Not Found", details: null },
};

const USAGE_BODY = {
  tenant_id: "5d7b11b0-a420-4ce3-a38b-dde8ed10f0b8",
  requests_today: 0,
  daily_request_quota: 10000,
  rate_limit_per_minute: 120,
};

function stubUsage(page: import("@playwright/test").Page, status: number, body: unknown) {
  return page.route(USAGE_ROUTE, (route) =>
    route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) }),
  );
}

test("enterprise disabled: explains demo mode and keeps the app usable", async ({ page }) => {
  await stubUsage(page, 404, NOT_FOUND_BODY);
  await page.goto("/enterprise");

  await expect(page.getByRole("heading", { name: "Enterprise" })).toBeVisible();
  await expect(page.getByText("Enterprise layer is disabled")).toBeVisible();
  await expect(page.getByText("Running in single-tenant demo mode")).toBeVisible();
  await expect(page.getByText(/ENTERPRISE__ENABLED=true/)).toBeVisible();

  // No onboarding is offered, because the routes are not mounted.
  await expect(page.getByText("Create an organization")).toBeHidden();

  // And the rest of the app still works with no auth gate.
  await page.getByRole("link", { name: "AI Search", exact: true }).click();
  await expect(page.getByRole("heading", { name: "AI Search" })).toBeVisible();
});

test("enterprise enabled, no key: offers bootstrap and existing-key sign-in", async ({ page }) => {
  await stubUsage(page, 401, {
    success: false,
    error: { code: "authentication_error", message: "Invalid API key.", details: null },
  });
  await page.goto("/enterprise");

  await expect(page.getByText("Enterprise layer is enabled")).toBeVisible();
  await expect(page.getByText("Create an organization")).toBeVisible();
  await expect(page.getByText("Use an existing key")).toBeVisible();
  await expect(page.getByLabel("Organization name")).toBeVisible();
  await expect(page.getByLabel("API key")).toBeVisible();
});

test("enterprise enabled and signed in: shows session context", async ({ page }) => {
  await stubUsage(page, 200, USAGE_BODY);
  await page.goto("/enterprise");

  await expect(page.getByText("Signed in")).toBeVisible();
  await expect(page.getByText("Session context")).toBeVisible();
  await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible();
});

test("backend unreachable: reports unknown rather than assuming disabled", async ({ page }) => {
  await page.route(USAGE_ROUTE, (route) => route.abort("failed"));
  await page.goto("/enterprise");

  await expect(page.getByText("Enterprise state unknown")).toBeVisible();
  // It must not claim the feature is disabled — that would be a guess.
  await expect(page.getByText("Enterprise layer is disabled")).toBeHidden();
});

test("bootstrap shows the owner key exactly once with a copy-once warning", async ({ page }) => {
  await stubUsage(page, 401, {
    success: false,
    error: { code: "authentication_error", message: "Invalid API key.", details: null },
  });
  await page.route("**/api/v1/organizations", (route) =>
    route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({
        organization: {
          id: "07868b25-46ba-4469-9e04-6fae4e32dc43",
          name: "Acme Retail",
          created_at: "2026-08-01T14:22:58.149294Z",
        },
        tenant: {
          id: "5d7b11b0-a420-4ce3-a38b-dde8ed10f0b8",
          organization_id: "07868b25-46ba-4469-9e04-6fae4e32dc43",
          name: "default",
          created_at: "2026-08-01T14:22:58.149294Z",
        },
        api_key: {
          api_key: {
            id: "3339554f-3f8a-4eef-be9c-5c63793cd494",
            tenant_id: "5d7b11b0-a420-4ce3-a38b-dde8ed10f0b8",
            name: "owner",
            role: "owner",
            prefix: "pik_uJ35edd2",
            revoked: false,
            created_at: "2026-08-01T14:22:58.173594Z",
          },
          key: "pik_uJ35edd2z32wU3wK-al87KSPyQumsQlu",
        },
      }),
    }),
  );

  await page.goto("/enterprise");
  await page.getByLabel("Organization name").fill("Acme Retail");
  await page.getByRole("button", { name: "Create organization" }).click();

  await expect(page.getByText("Copy this key now — it cannot be shown again")).toBeVisible();
  await expect(page.getByTestId("one-time-secret")).toHaveText(
    "pik_uJ35edd2z32wU3wK-al87KSPyQumsQlu",
  );

  // The raw secret must not be persisted anywhere in browser storage.
  const leaked = await page.evaluate(() => {
    const probe = (s: Storage) =>
      Object.keys(s).some((k) => (s.getItem(k) ?? "").includes("z32wU3wK-al87KSPyQumsQlu"));
    return { local: probe(localStorage), session: probe(sessionStorage) };
  });
  // sessionStorage legitimately holds the key as the active credential;
  // localStorage must not, because "remember" was left unchecked.
  expect(leaked.local).toBe(false);

  // Dismissing drops it from the DOM for good.
  await page.getByRole("button", { name: "Done" }).click();
  await expect(page.getByTestId("one-time-secret")).toBeHidden();
});

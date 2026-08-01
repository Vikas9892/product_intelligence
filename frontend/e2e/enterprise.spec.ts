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

  // The rest of the app stays reachable with no auth gate: every primary
  // destination is present and enabled. (Actually navigating between sections
  // is covered by smoke.spec.ts; repeating it here only added a dev-server
  // compile race under parallel workers.)
  // Names here are the sidebar labels from config/nav.ts, which differ from
  // some page headings (nav says "Analytics"; that page's heading is "AI
  // Analytics").
  for (const name of ["AI Search", "Upload", "Duplicates", "Pricing", "Analytics"]) {
    await expect(page.getByRole("link", { name, exact: true })).toBeVisible();
  }
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

/** Real `GET /api-keys` metadata — note the absence of any `key` field. */
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
  {
    id: "7125c0a0-e570-4450-8297-bc33c132dc82",
    tenant_id: "5d7b11b0-a420-4ce3-a38b-dde8ed10f0b8",
    name: "ci-readonly",
    role: "viewer",
    prefix: "pik_KoSYT7H8",
    revoked: true,
    created_at: "2026-08-01T14:23:12.606278Z",
  },
];

async function signedIn(page: import("@playwright/test").Page, keys = API_KEYS) {
  await stubUsage(page, 200, USAGE_BODY);
  await page.route("**/api/v1/api-keys", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(keys),
      });
      return;
    }
    // POST — the create response is the only place a secret ever appears.
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({
        api_key: {
          id: "new-id",
          tenant_id: "5d7b11b0-a420-4ce3-a38b-dde8ed10f0b8",
          name: "ci-pipeline",
          role: "member",
          prefix: "pik_NewKey01",
          revoked: false,
          created_at: "2026-08-01T15:00:00Z",
        },
        key: "pik_NewKey01SECRETVALUE1234567890ab",
      }),
    });
  });
}

test("lists API keys as metadata only, with active and revoked states", async ({ page }) => {
  await signedIn(page);
  await page.goto("/enterprise");

  await expect(page.getByText("API keys")).toBeVisible();
  const table = page.getByRole("table");
  // Assert on prefixes: the key named "owner" also has role "owner", so the
  // name alone is ambiguous. Prefixes are unique per key.
  await expect(table.getByText("pik_uJ35edd2")).toBeVisible();
  await expect(table.getByText("pik_KoSYT7H8")).toBeVisible();
  await expect(table.getByText("ci-readonly")).toBeVisible();
  await expect(table.getByText("Active")).toBeVisible();
  await expect(table.getByText("Revoked")).toBeVisible();

  // Metadata only — a secret must never appear in the listing.
  await expect(table.getByText(/pik_\w{8}\w{20,}/)).toBeHidden();

  // A revoked key offers no revoke action.
  await expect(page.getByRole("button", { name: "Revoke ci-readonly" })).toBeHidden();
  await expect(page.getByRole("button", { name: "Revoke owner" })).toBeVisible();
});

test("creating a key reveals its secret exactly once", async ({ page }) => {
  await signedIn(page);
  await page.goto("/enterprise");

  await page.getByLabel("Key name").fill("ci-pipeline");
  await page.getByRole("button", { name: "Create key" }).click();

  await expect(page.getByTestId("one-time-secret")).toHaveText(
    "pik_NewKey01SECRETVALUE1234567890ab",
  );
  await expect(page.getByText("Copy this key now — it cannot be shown again")).toBeVisible();

  // The freshly created secret must never reach persistent storage.
  const inLocalStorage = await page.evaluate(() =>
    Object.keys(localStorage).some((k) =>
      (localStorage.getItem(k) ?? "").includes("SECRETVALUE1234567890ab"),
    ),
  );
  expect(inLocalStorage).toBe(false);

  await page.getByRole("button", { name: "Done" }).click();
  await expect(page.getByTestId("one-time-secret")).toBeHidden();
});

test("revoking asks for confirmation and warns it is irreversible", async ({ page }) => {
  await signedIn(page);
  await page.route("**/api/v1/api-keys/*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ...API_KEYS[0], revoked: true }),
    }),
  );
  await page.goto("/enterprise");

  await page.getByRole("button", { name: "Revoke owner" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(page.getByText(/cannot be undone/)).toBeVisible();
  await expect(page.getByText(/no way to re-issue the same key/)).toBeVisible();

  await page.getByRole("button", { name: "Cancel" }).click();
  await expect(page.getByRole("dialog")).toBeHidden();
});

test("surfaces the backend's 403 when creating a key above the caller's role", async ({ page }) => {
  await stubUsage(page, 200, USAGE_BODY);
  await page.route("**/api/v1/api-keys", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
      return;
    }
    await route.fulfill({
      status: 403,
      contentType: "application/json",
      body: JSON.stringify({
        success: false,
        error: {
          code: "authorization_error",
          message: "Role 'admin' cannot create a key with the higher role 'owner'.",
          details: null,
        },
      }),
    });
  });
  await page.goto("/enterprise");

  await page.getByLabel("Key name").fill("escalate");
  await page.getByRole("button", { name: "Create key" }).click();

  await expect(page.getByText("Not permitted")).toBeVisible();
  await expect(
    page.getByText("Role 'admin' cannot create a key with the higher role 'owner'."),
  ).toBeVisible();
});

test("shows an empty state when the tenant has no keys", async ({ page }) => {
  await signedIn(page, []);
  await page.goto("/enterprise");

  await expect(page.getByText("No API keys yet")).toBeVisible();
  await expect(page.getByText(/cannot be recovered afterwards/)).toBeVisible();
});

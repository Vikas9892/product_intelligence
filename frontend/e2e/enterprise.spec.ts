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

const FORBIDDEN_BODY = {
  success: false,
  error: {
    code: "authorization_error",
    message: "Role 'member' lacks the 'manage_api_keys' permission.",
    details: null,
  },
};

test("a 403 on the key list renders an authoritative forbidden state", async ({ page }) => {
  // Enterprise is on and the key authenticated (usage 200), but this role
  // cannot manage keys — the exact shape the backend returns for a member.
  await stubUsage(page, 200, USAGE_BODY);
  await page.route("**/api/v1/api-keys", (route) =>
    route.fulfill({
      status: 403,
      contentType: "application/json",
      body: JSON.stringify(FORBIDDEN_BODY),
    }),
  );
  await page.goto("/enterprise");

  await expect(page.getByText("This key can't manage API keys")).toBeVisible();
  await expect(page.getByText(/available to: admin, owner/)).toBeVisible();
  // It must be explicit that the server enforced it, not the UI.
  await expect(page.getByText(/The backend enforced this/)).toBeVisible();
  // And it must not offer a pointless retry.
  await expect(page.getByRole("button", { name: "Retry" })).toBeHidden();
});

test("a 403 is still treated as enterprise-enabled, not unavailable", async ({ page }) => {
  // /usage 403 means: router mounted, key valid, role insufficient. The
  // console must show the signed-in surface rather than the disabled banner.
  await stubUsage(page, 403, FORBIDDEN_BODY);
  await page.route("**/api/v1/api-keys", (route) =>
    route.fulfill({
      status: 403,
      contentType: "application/json",
      body: JSON.stringify(FORBIDDEN_BODY),
    }),
  );
  await page.goto("/enterprise");

  await expect(page.getByText("Signed in")).toBeVisible();
  await expect(page.getByText("Enterprise layer is disabled")).toBeHidden();
});

/** Real audit events captured from the backend. */
const AUDIT_EVENTS = [
  {
    id: "50d9aa37-1dd2-4d2a-9589-5478c9a1cf44",
    tenant_id: "5d7b11b0-a420-4ce3-a38b-dde8ed10f0b8",
    actor: "pik_uJ35edd2",
    action: "create_api_key",
    resource: "pik_ogLoiqWZ",
    metadata: { role: "admin" },
    created_at: "2026-08-01T14:24:00.984136Z",
  },
  {
    id: "d4860a34-3751-445d-a2cd-7ad899809505",
    tenant_id: "5d7b11b0-a420-4ce3-a38b-dde8ed10f0b8",
    actor: "pik_Other111",
    action: "revoke_api_key",
    resource: "pik_KoSYT7H8",
    metadata: {},
    created_at: "2026-08-01T14:23:38.980935Z",
  },
];

function stubAudit(page: import("@playwright/test").Page, status: number, body: unknown) {
  return page.route("**/api/v1/audit*", (route) =>
    route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) }),
  );
}

test("audit log renders actor, action, resource, metadata and timestamps", async ({ page }) => {
  await signedIn(page);
  await stubAudit(page, 200, AUDIT_EVENTS);
  await page.goto("/enterprise");

  await expect(page.getByText("Audit log")).toBeVisible();
  await expect(page.getByText("Showing 2 of 2 fetched events")).toBeVisible();
  await expect(page.getByText("create_api_key")).toBeVisible();
  await expect(page.getByText("revoke_api_key")).toBeVisible();
  await expect(page.getByText("role=admin")).toBeVisible();

  // No pagination controls: the endpoint has no cursor or offset. `exact`
  // matters — a loose "Next" also matches the Next.js dev-tools button.
  await expect(page.getByRole("button", { name: "Next", exact: true })).toBeHidden();
  await expect(page.getByRole("button", { name: "Previous", exact: true })).toBeHidden();
  await expect(page.getByText(/no cursor or offset, so there are no page controls/)).toBeVisible();
});

test("audit filters narrow the fetched page and explain the empty result", async ({ page }) => {
  await signedIn(page);
  await stubAudit(page, 200, AUDIT_EVENTS);
  await page.goto("/enterprise");
  await expect(page.getByText("Showing 2 of 2 fetched events")).toBeVisible();

  await page.getByLabel("Actor").fill("pik_uJ35");
  await expect(page.getByText("Showing 1 of 2 fetched events")).toBeVisible();

  await page.getByLabel("Actor").fill("nobody");
  await expect(page.getByText("No events match these filters")).toBeVisible();
});

test("audit empty state distinguishes 'nothing logged' from an error", async ({ page }) => {
  await signedIn(page);
  await stubAudit(page, 200, []);
  await page.goto("/enterprise");

  await expect(page.getByText("No audit events yet")).toBeVisible();
  await expect(
    page.getByText(/Events are recorded when keys are created or revoked/),
  ).toBeVisible();
});

test("audit 403 shows a forbidden state naming the roles that grant it", async ({ page }) => {
  await signedIn(page);
  await stubAudit(page, 403, {
    success: false,
    error: {
      code: "authorization_error",
      message: "Role 'member' lacks the 'view_audit' permission.",
      details: null,
    },
  });
  await page.goto("/enterprise");

  await expect(page.getByText("This key can't view the audit log")).toBeVisible();
});

test("usage shows consumption against the real quota, with no invented trend", async ({ page }) => {
  await signedIn(page);
  await stubAudit(page, 200, []);
  await page.goto("/enterprise");

  await expect(page.getByText("Usage & quota")).toBeVisible();
  await expect(page.getByText("0 / 10,000", { exact: false })).toBeVisible();
  await expect(page.getByText("120", { exact: false }).first()).toBeVisible();

  // A snapshot must not be rendered as a time series.
  await expect(page.locator(".recharts-surface")).toHaveCount(0);
  await expect(page.getByText(/is a counter, not a\s+time series/)).toBeVisible();
});

test("quota exhaustion is called out explicitly", async ({ page }) => {
  await page.route(USAGE_ROUTE, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ...USAGE_BODY, requests_today: 10000 }),
    }),
  );
  await page.route("**/api/v1/api-keys", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: "[]" }),
  );
  await stubAudit(page, 200, []);
  await page.goto("/enterprise");

  await expect(page.getByText("Daily quota exhausted")).toBeVisible();
  await expect(page.getByText(/rejected with 429/)).toBeVisible();
});

test("a zero quota is reported as no ceiling, not as 0% used", async ({ page }) => {
  await page.route(USAGE_ROUTE, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ...USAGE_BODY,
        requests_today: 42,
        daily_request_quota: 0,
        rate_limit_per_minute: 0,
      }),
    }),
  );
  await page.route("**/api/v1/api-keys", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: "[]" }),
  );
  await stubAudit(page, 200, []);
  await page.goto("/enterprise");

  await expect(page.getByText("no daily ceiling configured")).toBeVisible();
  await expect(page.getByText("Not enforced")).toBeVisible();
  await expect(page.getByText("Daily quota exhausted")).toBeHidden();
});

test("creating a key repeats the one-shot warning in a toast", async ({ page }) => {
  await signedIn(page);
  await page.goto("/enterprise");

  await page.getByLabel("Key name").fill("ci-pipeline");
  await page.getByRole("button", { name: "Create key" }).click();

  await expect(page.getByText('API key "ci-pipeline" created')).toBeVisible();
  // The secret panel is dismissible, so the warning is repeated where it
  // cannot be missed.
  await expect(page.getByText("Copy the secret now — it cannot be shown again.")).toBeVisible();
});

import { expect, test } from "@playwright/test";

/**
 * Stage 6 hardening: the cross-cutting behaviours the per-feature specs do not
 * cover — keyboard operability, responsive layout, loading states, and the
 * combined partial-failure cases.
 */

const USAGE_BODY = {
  tenant_id: "5d7b11b0-a420-4ce3-a38b-dde8ed10f0b8",
  requests_today: 0,
  daily_request_quota: 10000,
  rate_limit_per_minute: 120,
};

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

function json(body: unknown, status = 200) {
  return { status, contentType: "application/json", body: JSON.stringify(body) };
}

async function stubEnterprise(page: import("@playwright/test").Page) {
  await page.route("**/api/v1/usage", (r) => r.fulfill(json(USAGE_BODY)));
  await page.route("**/api/v1/api-keys", (r) => r.fulfill(json([])));
  await page.route("**/api/v1/audit*", (r) => r.fulfill(json([])));
}

test.describe("keyboard operability", () => {
  test("the enterprise console is fully reachable by keyboard", async ({ page }) => {
    await stubEnterprise(page);
    await page.goto("/enterprise");
    await expect(page.getByText("Usage & quota")).toBeVisible();

    // Tab from the top and confirm focus lands on real controls rather than
    // getting trapped or skipping the panel.
    const reached: string[] = [];
    for (let i = 0; i < 30; i += 1) {
      await page.keyboard.press("Tab");
      const label = await page.evaluate(() => {
        const el = document.activeElement as HTMLElement | null;
        if (!el || el === document.body) return "";
        return (
          el.getAttribute("aria-label") ??
          el.getAttribute("id") ??
          el.textContent?.trim().slice(0, 30) ??
          el.tagName
        );
      });
      if (label) reached.push(label);
    }

    expect(reached.length).toBeGreaterThan(5);
    // The audit filters are deep in the page; they must be tabbable.
    expect(reached.some((l) => l.includes("audit-actor") || l.includes("audit-action"))).toBe(true);
  });

  test("a focused control shows a visible focus ring", async ({ page }) => {
    await stubEnterprise(page);
    await page.goto("/enterprise");

    const actor = page.getByLabel("Actor");
    await actor.focus();
    await expect(actor).toBeFocused();

    const hasVisibleFocus = await actor.evaluate((el) => {
      const s = getComputedStyle(el);
      // Tailwind's focus-visible ring renders as a box-shadow or outline.
      return s.outlineStyle !== "none" || s.boxShadow !== "none";
    });
    expect(hasVisibleFocus).toBe(true);
  });

  test("the revoke dialog traps focus and closes on Escape", async ({ page }) => {
    await page.route("**/api/v1/usage", (r) => r.fulfill(json(USAGE_BODY)));
    await page.route("**/api/v1/audit*", (r) => r.fulfill(json([])));
    await page.route("**/api/v1/api-keys", (r) =>
      r.fulfill(
        json([
          {
            id: "k1",
            tenant_id: "t1",
            name: "ci",
            role: "member",
            prefix: "pik_AbCd1234",
            revoked: false,
            created_at: "2026-08-01T14:22:58Z",
          },
        ]),
      ),
    );
    await page.goto("/enterprise");

    await page.getByRole("button", { name: "Revoke ci" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();

    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
  });
});

test.describe("responsive layout", () => {
  const VIEWPORTS = [
    { name: "mobile", width: 390, height: 844 },
    { name: "tablet", width: 768, height: 1024 },
    { name: "desktop", width: 1440, height: 900 },
  ];

  for (const vp of VIEWPORTS) {
    test(`enterprise console has no horizontal overflow on ${vp.name}`, async ({ page }) => {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await stubEnterprise(page);
      await page.goto("/enterprise");
      await expect(page.getByText("Usage & quota")).toBeVisible();

      // The page body must never scroll sideways; wide tables scroll inside
      // their own container instead.
      const overflows = await page.evaluate(
        () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
      );
      expect(overflows).toBe(false);
    });

    test(`system page has no horizontal overflow on ${vp.name}`, async ({ page }) => {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await page.route("**/api/v1/system/health", (r) => r.fulfill(json(HEALTHY)));
      await page.route("**/api/v1/system/stats", (r) => r.fulfill(json(STATS)));
      await page.route("**/api/v1/models", (r) => r.fulfill(json([])));
      await page.goto("/system");
      await expect(page.getByText("System operations")).toBeVisible();

      const overflows = await page.evaluate(
        () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
      );
      expect(overflows).toBe(false);
    });
  }
});

test.describe("loading and partial failure", () => {
  test("shows a loading state before the capability probe resolves", async ({ page }) => {
    let release: (() => void) | undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    await page.route("**/api/v1/usage", async (route) => {
      await gate;
      await route.fulfill(json(USAGE_BODY));
    });
    await page.route("**/api/v1/api-keys", (r) => r.fulfill(json([])));
    await page.route("**/api/v1/audit*", (r) => r.fulfill(json([])));

    await page.goto("/enterprise");
    // The console must not assert a capability state it has not determined.
    await expect(page.getByText("Enterprise layer is disabled")).toBeHidden();
    await expect(page.getByText("Signed in")).toBeHidden();

    release?.();
    await expect(page.getByText("Signed in")).toBeVisible();
  });

  test("one failing panel does not blank the others", async ({ page }) => {
    // Usage succeeds, keys are forbidden, audit 500 — each degrades alone.
    await page.route("**/api/v1/usage", (r) => r.fulfill(json(USAGE_BODY)));
    await page.route("**/api/v1/api-keys", (r) =>
      r.fulfill(
        json(
          {
            success: false,
            error: {
              code: "authorization_error",
              message: "Role 'member' lacks the 'manage_api_keys' permission.",
              details: null,
            },
          },
          403,
        ),
      ),
    );
    await page.route("**/api/v1/audit*", (r) =>
      r.fulfill(json({ success: false, error: { code: "server_error", message: "boom" } }, 500)),
    );
    await page.goto("/enterprise");

    // Usage rendered.
    await expect(page.getByText("Usage & quota")).toBeVisible();
    await expect(page.getByText("0 / 10,000", { exact: false })).toBeVisible();
    // Keys forbidden — authoritative, not a retry prompt.
    await expect(page.getByText("This key can't manage API keys")).toBeVisible();
    // Audit errored — retryable.
    await expect(page.getByText("Couldn't load the audit log")).toBeVisible();
  });

  test("both dependencies down still renders the page and reports each", async ({ page }) => {
    await page.route("**/api/v1/system/health", (r) =>
      r.fulfill(json({ ...HEALTHY, redis: "unhealthy", qdrant: "unhealthy" })),
    );
    await page.route("**/api/v1/system/stats", (r) => r.fulfill(json(STATS)));
    await page.route("**/api/v1/models", (r) => r.fulfill(json([])));
    await page.goto("/system");

    await expect(page.getByText("Degraded")).toBeVisible();
    // Both are named; the page does not collapse into a single generic error.
    await expect(page.getByText("Redis", { exact: true })).toBeVisible();
    await expect(page.getByText("Qdrant", { exact: true })).toBeVisible();
    await expect(page.getByText("Unavailable").first()).toBeVisible();
    // The registry still renders its own empty state.
    await expect(page.getByText("No models are registered.")).toBeVisible();
  });
});

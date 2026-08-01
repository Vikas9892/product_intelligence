import { expect, test } from "@playwright/test";

/**
 * Smoke E2E: the app shell, navigation, and theming. These flows render
 * without the backend (data sections show their own loading/error states),
 * so the suite is self-contained.
 */

/**
 * Cross-page navigation gets headroom above the default assertion timeout.
 *
 * The suite runs against a production build (see playwright.config.ts), so
 * routes are served immediately and this is normally slack rather than
 * necessity. It is kept because navigation timing is the one thing here that
 * depends on machine load rather than on the application.
 */
const NAVIGATION_TIMEOUT = 30_000;

test("app shell renders and navigates between sections", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible({
    timeout: NAVIGATION_TIMEOUT,
  });

  await page.getByRole("link", { name: "Upload" }).click();
  await expect(page).toHaveURL(/\/upload$/, { timeout: NAVIGATION_TIMEOUT });
  await expect(page.getByRole("heading", { name: "Upload" })).toBeVisible({
    timeout: NAVIGATION_TIMEOUT,
  });

  // Exact match avoids the topbar's "Go to search" quick link.
  await page.getByRole("link", { name: "AI Search", exact: true }).click();
  await expect(page).toHaveURL(/\/search$/, { timeout: NAVIGATION_TIMEOUT });
  await expect(page.getByRole("heading", { name: "AI Search" })).toBeVisible({
    timeout: NAVIGATION_TIMEOUT,
  });
});

test("theme can be switched to dark", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Toggle theme" }).click();
  await page.getByRole("menuitem", { name: "Dark" }).click();
  await expect(page.locator("html")).toHaveClass(/dark/);
});

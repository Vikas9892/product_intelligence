import { expect, test } from "@playwright/test";

/**
 * Smoke E2E: the app shell, navigation, and theming. These flows render
 * without the backend (data sections show their own loading/error states),
 * so the suite is self-contained.
 */
test("app shell renders and navigates between sections", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();

  await page.getByRole("link", { name: "Upload" }).click();
  await expect(page).toHaveURL(/\/upload$/);
  await expect(page.getByRole("heading", { name: "Upload" })).toBeVisible();

  // The sidebar entry is "Search"; the products list page heading is "Products".
  // Exact match avoids the topbar's "Go to search" quick link.
  await page.getByRole("link", { name: "Search", exact: true }).click();
  await expect(page).toHaveURL(/\/search$/);
  await expect(page.getByRole("heading", { name: "Products" })).toBeVisible();
});

test("theme can be switched to dark", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Toggle theme" }).click();
  await page.getByRole("menuitem", { name: "Dark" }).click();
  await expect(page.locator("html")).toHaveClass(/dark/);
});

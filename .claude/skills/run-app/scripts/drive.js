#!/usr/bin/env node
/**
 * Drive the Product Intelligence frontend in headless Chromium and prove it
 * actually rendered.
 *
 * Node resolves modules relative to THIS FILE, not the cwd, so Playwright has
 * to be required by absolute path into frontend/node_modules. Requiring
 * '@playwright/test' by bare name fails even when run from frontend/.
 */
const path = require('path');
const fs = require('fs');
const os = require('os');

const REPO_ROOT = path.resolve(__dirname, '../../../..');
const { chromium } = require(
  path.join(REPO_ROOT, 'frontend/node_modules/@playwright/test')
);

const BASE_URL = process.env.BASE_URL || 'http://localhost:3001';
const OUT_DIR =
  process.env.OUT_DIR || path.join(os.tmpdir(), 'pi-run-screenshots');

(async () => {
  fs.mkdirSync(OUT_DIR, { recursive: true });

  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

  const failures = [];
  page.on('response', (r) => {
    if (r.status() >= 400) failures.push(`${r.status()} ${r.request().method()} ${r.url()}`);
  });
  page.on('pageerror', (e) => failures.push(`pageerror: ${e.message}`));

  async function shoot(name) {
    const file = path.join(OUT_DIR, `${name}.png`);
    await page.screenshot({ path: file });
    return file;
  }

  // networkidle is NOT enough: React Query paints skeletons first, so a
  // screenshot taken at idle catches a page full of grey placeholders and
  // still reports zero failed requests. Wait for the skeletons to clear.
  async function settle() {
    await page.waitForLoadState('networkidle', { timeout: 30000 }).catch(() => {});
    await page
      .locator('[data-slot="skeleton"]')
      .first()
      .waitFor({ state: 'detached', timeout: 60000 })
      .catch(() => console.warn('  ! skeletons still present after 60s'));
  }

  async function visit(route, name) {
    // Turbopack compiles routes on demand; the first hit can take ~20s.
    const res = await page.goto(BASE_URL + route, {
      waitUntil: 'domcontentloaded',
      timeout: 120000,
    });
    await settle();
    const h1 = await page.locator('h1').first().textContent().catch(() => null);
    console.log(
      `${route.padEnd(10)} -> HTTP ${res && res.status()} | h1="${(h1 || '').trim()}" | ${await shoot(name)}`
    );
  }

  await visit('/', 'dashboard');
  await visit('/search', 'search');

  // The query box has no `type` attribute -- input[type=text] misses it.
  const box = page.getByPlaceholder(/Describe the product/i);
  await box.waitFor({ timeout: 30000 });
  await box.fill('wireless headphones');
  await page.getByRole('button', { name: /^Search$/ }).click();
  await settle();
  console.log(`search submitted -> ${await shoot('search-result')}`);

  const unique = [...new Set(failures)];
  console.log(`\n--- failed requests (${unique.length}) ---`);
  for (const f of unique.slice(0, 20)) console.log(f);
  if (!unique.length) console.log('(none)');

  await browser.close();
  process.exit(unique.length ? 1 : 0);
})().catch((e) => {
  console.error('DRIVER FAILED:', e.message);
  process.exit(2);
});

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

  // Opt-in: exercises the worker pipeline and adds a real row to the catalog.
  if (process.argv.includes('--upload')) {
    const sampleDir = path.join(REPO_ROOT, 'backend/storage/processed');
    const sample = fs
      .readdirSync(sampleDir)
      .find((f) => /\.(jpe?g|png|webp)$/i.test(f));
    if (!sample) throw new Error(`no sample image in ${sampleDir}`);

    await page.goto(BASE_URL + '/upload', { waitUntil: 'domcontentloaded', timeout: 120000 });
    await page.setInputFiles('input[type="file"]', path.join(sampleDir, sample));
    await page.locator('input[name="name"]').fill('Smoke Test Sneaker');
    await page.locator('input[name="brand"]').fill('Nike');
    await page.locator('input[name="category"]').fill('men-shoes');
    await page.locator('input[name="price"]').fill('2499');
    // NOT [name="description"] -- that also matches <meta name="description">.
    await page.locator('textarea').first().fill('Smoke test upload.');
    await page.getByRole('button', { name: /upload|submit|process/i }).last().click();

    // Do NOT stop at 100%: the redirect to /products/<id> lands after it.
    // Parking on step 1 "Queued" at 0% means the worker pool is not running.
    let landed = false;
    for (let i = 0; i < 40; i++) {
      await page.waitForTimeout(3000);
      if (/\/products\//.test(page.url())) { landed = true; break; }
      if (/failed/i.test(await page.locator('body').innerText())) break;
    }
    await settle();
    console.log(
      `upload -> ${landed ? 'completed, redirected to ' + page.url() : 'DID NOT COMPLETE (worker running?)'} | ${await shoot('upload-result')}`
    );
    if (!landed) failures.push('upload never reached the product page');
  }

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

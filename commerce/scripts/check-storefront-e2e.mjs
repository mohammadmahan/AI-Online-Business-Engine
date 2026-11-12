#!/usr/bin/env node
/**
 * LSE — repeatable local browser check for the existing storefront.
 *
 * Two modes, both loopback-only:
 *
 *   node scripts/check-storefront-e2e.mjs
 *     Full journey against a disposable, seeded local database:
 *     home -> catalog -> PDP -> cart persistence -> synthetic checkout ->
 *     merchant order reconciliation, plus status/layout/accessibility guards.
 *
 *   node scripts/check-storefront-e2e.mjs --fail-closed
 *     Against a server started WITHOUT DATABASE_URL: every data surface must
 *     say it is unavailable and checkout must render no customer form.
 *
 * This runner adds no browser dependency: playwright-core is already installed
 * and the local system Chrome is used. It is NOT a production check, creates
 * only synthetic local data, and refuses every non-loopback base URL.
 */
import { existsSync } from 'node:fs';
import { chromium } from 'playwright-core';

const args = new Set(process.argv.slice(2));
const failClosedMode = args.has('--fail-closed');
const base = (process.env.COMMERCE_BASE_URL || 'http://127.0.0.1:13002').replace(/\/$/, '');
const chromePath =
  process.env.CHROME_PATH ||
  (process.platform === 'darwin'
    ? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    : '/usr/bin/google-chrome');

const adminUsername = process.env.ADMIN_USERNAME?.trim() ?? '';
const adminPassword = process.env.ADMIN_PASSWORD ?? '';

let passed = 0;
let failed = 0;

function record(ok, label, detail = '') {
  if (ok) passed += 1;
  else failed += 1;
  console.log(`${ok ? 'PASS' : 'FAIL'} ${label}${detail ? ` — ${detail}` : ''}`);
}

function refuse(message) {
  console.error(`REFUSED ${message}`);
  process.exit(2);
}

function checkLoopbackBase() {
  let url;
  try {
    url = new URL(base);
  } catch {
    refuse(`COMMERCE_BASE_URL is not a URL: ${base}`);
  }
  const loopback = new Set(['127.0.0.1', 'localhost', '::1', '[::1]']);
  if (!loopback.has(url.hostname) || (url.protocol !== 'http:' && url.protocol !== 'https:')) {
    refuse(`COMMERCE_BASE_URL must be loopback HTTP(S), got ${base}`);
  }
}

async function textOf(locator) {
  return (await locator.innerText()).replace(/\s+/g, ' ').trim();
}

async function waitForHeading(page, name) {
  await page.getByRole('heading', { name }).first().waitFor({ state: 'visible', timeout: 15_000 });
}

async function checkLayout(page, path, width) {
  await page.setViewportSize({ width, height: 900 });
  await page.goto(`${base}${path}`, { waitUntil: 'networkidle', timeout: 30_000 });
  const measured = await page.evaluate(() => ({
    vw: window.innerWidth,
    scrollWidth: document.documentElement.scrollWidth,
    direction: getComputedStyle(document.body).direction,
    h1Count: document.querySelectorAll('h1').length,
    unnamedButtons: [...document.querySelectorAll('button')].filter((button) => {
      const text = (button.textContent ?? '').trim();
      return text === '' && !button.getAttribute('aria-label') && !button.getAttribute('title');
    }).length,
  }));
  record(measured.scrollWidth <= measured.vw + 1, `layout ${path} ${width}px no horizontal overflow`, `${measured.scrollWidth} <= ${measured.vw}`);
  record(measured.direction === 'rtl', `layout ${path} ${width}px RTL`, measured.direction);
  record(measured.h1Count === 1, `layout ${path} ${width}px one h1`, String(measured.h1Count));
  record(measured.unnamedButtons === 0, `layout ${path} ${width}px buttons named`, String(measured.unnamedButtons));
}

async function runFailClosed(browser) {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, locale: 'fa-IR' });
  const page = await context.newPage();
  const paths = ['/', '/catalog', '/products/manto-katan-jelo-baste', '/checkout'];

  for (const path of paths) {
    await page.goto(`${base}${path}`, { waitUntil: 'networkidle', timeout: 30_000 });
    const body = await page.locator('body').innerText();
    record(
      body.includes('در این لحظه نمایش داده نمی‌شود'),
      `fail-closed ${path} unavailable notice`,
    );
  }

  await page.goto(`${base}/checkout`, { waitUntil: 'networkidle' });
  record(
    (await page.locator('form[aria-label="فرم تسویهٔ خرید"]').count()) === 0,
    'fail-closed checkout renders no customer form',
  );

  await checkLayout(page, '/catalog', 320);
  await checkLayout(page, '/checkout', 390);
  await context.close();
}

async function runFull(browser) {
  if (adminUsername === '' || adminPassword === '') {
    refuse('ADMIN_USERNAME and ADMIN_PASSWORD are required for the merchant reconciliation step');
  }

  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    locale: 'fa-IR',
    reducedMotion: 'reduce',
  });
  const page = await context.newPage();

  // Stable start: this run owns the synthetic basket it creates.
  await page.goto(`${base}/`, { waitUntil: 'networkidle', timeout: 30_000 });
  await page.evaluate(() => window.localStorage.clear());

  await page.reload({ waitUntil: 'networkidle' });
  await waitForHeading(page, /اندازهٔ درست، رنگ دلخواه/);
  const homeBody = await page.locator('body').innerText();
  record(!homeBody.includes('در این لحظه نمایش داده نمی‌شود'), 'home data surface available');
  record(homeBody.includes('مانتو') && homeBody.includes('شومیز'), 'home renders seeded categories');

  await page.getByRole('link', { name: 'دیدن همهٔ محصولات', exact: true }).click();
  await page.waitForURL('**/catalog', { timeout: 15_000 });
  await page.locator('article h3').first().waitFor({ timeout: 15_000 });
  record((await page.locator('article h3').count()) === 3, 'catalog renders three seeded products');

  const search = page.getByLabel('جست‌وجو');
  await search.fill('شومیز');
  await page.getByRole('heading', { name: 'شومیز ابریشمی یقه گرد' }).waitFor({ timeout: 10_000 });
  const filteredStatus = await textOf(page.locator('p[role="status"]').filter({ hasText: 'محصول' }).first());
  record(/۱ محصول/.test(filteredStatus), 'catalog search narrows to one product', filteredStatus);

  await search.fill('zzzz-no-match');
  await page.getByText('محصولی با این فیلترها پیدا نشد.').waitFor({ timeout: 10_000 });
  record(true, 'catalog no-match empty state');
  await page.getByRole('button', { name: 'پاک کردن فیلترها' }).first().click();
  await page.waitForFunction(() => document.querySelectorAll('article h3').length === 3, null, {
    timeout: 10_000,
  });
  record(true, 'catalog clear filters restores three products');

  await page.goto(`${base}/products/manto-katan-jelo-baste`, { waitUntil: 'networkidle' });
  await waitForHeading(page, 'مانتو کتان جلو بسته');
  await page.getByRole('button', { name: /^M/ }).first().click();
  await page.getByRole('button', { name: 'افزودن به سبد خرید' }).click();
  const drawer = page.getByRole('dialog');
  await drawer.waitFor({ state: 'visible', timeout: 10_000 });
  const drawerText = await textOf(drawer);
  record(drawerText.includes('مانتو کتان جلو بسته') && drawerText.includes('M'), 'cart drawer contains chosen product/size');
  await page.getByRole('button', { name: 'افزودن یک عدد به مانتو کتان جلو بسته' }).click();
  await page.waitForFunction(() => {
    const live = document.querySelector('[role="dialog"] [aria-live="polite"]');
    return live?.textContent?.trim() === '۲';
  }, null, { timeout: 10_000 });
  record(true, 'cart quantity increments to two');
  await page.keyboard.press('Escape');
  await drawer.waitFor({ state: 'hidden', timeout: 10_000 });

  await page.reload({ waitUntil: 'networkidle' });
  await page.getByRole('button', { name: /سبد خرید، ۲ کالا/ }).waitFor({ timeout: 10_000 });
  record(true, 'cart survives reload through localStorage');

  await page.goto(`${base}/checkout`, { waitUntil: 'networkidle' });
  const checkoutForm = page.locator('form[aria-label="فرم تسویهٔ خرید"]');
  await checkoutForm.waitFor({ state: 'visible', timeout: 15_000 });
  await page.getByLabel('نام و نام خانوادگی').fill('کاربر آزمایشی ال‌اس‌ای');
  await page.getByLabel('شمارهٔ موبایل').fill('09120000000');
  await page.getByLabel('نشانی').fill('تهران، خیابان آزمایشی، پلاک ۱، واحد ۱');
  await page.getByLabel('کد پستی').fill('1111111111');

  // D-175 — the Tehran address makes all three approved carriers eligible.
  const carrierRadios = page.locator('input[name="checkout-shipping"]');
  await page.waitForFunction(
    () => document.querySelectorAll('input[name="checkout-shipping"]').length === 3,
    null,
    { timeout: 10_000 },
  );
  const carrierLabels = await page
    .locator('input[name="checkout-shipping"]')
    .evaluateAll((inputs) =>
      inputs.map((input) => input.closest('label')?.textContent?.replace(/\s+/g, ' ').trim() ?? ''),
    );
  record(
    carrierLabels.length === 3 &&
      carrierLabels[0].includes('پست ایران') &&
      carrierLabels[1].includes('تیپاکس') &&
      carrierLabels[2].includes('پیک محلی'),
    'checkout shows three eligible carriers in priority order',
    carrierLabels.join(' | '),
  );
  record(await carrierRadios.first().isChecked(), 'first eligible carrier is preselected');
  await page.getByRole('radio', { name: /پیک محلی/ }).check();
  record(await page.getByRole('radio', { name: /پیک محلی/ }).isChecked(), 'carrier selection is changeable');

  await page.getByRole('button', { name: 'ثبت سفارش' }).click();
  await page.getByRole('heading', { name: 'سفارش ثبت شد' }).waitFor({ timeout: 30_000 });
  const successText = await page.locator('body').innerText();
  record(successText.includes('UNAVAILABLE'), 'checkout reports fail-closed payment status');
  const orderId = successText.match(
    /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i,
  )?.[0];
  record(typeof orderId === 'string', 'checkout returns a synthetic order id', orderId ?? 'missing');
  record(
    (await page.getByRole('button', { name: 'سبد خرید', exact: true }).count()) === 1,
    'cart clears after successful order',
  );

  if (typeof orderId === 'string') {
    await page.goto(`${base}/admin/login`, { waitUntil: 'networkidle' });
    await page.getByLabel('نام کاربری').fill(adminUsername);
    await page.getByLabel('گذرواژه').fill(adminPassword);
    await page.getByRole('button', { name: 'ورود' }).click();
    await page.waitForFunction(() => location.pathname === '/admin', null, { timeout: 20_000 });
    record(true, 'merchant login succeeds');

    await page.goto(`${base}/admin/orders`, { waitUntil: 'networkidle' });
    await page.locator('table').waitFor({ state: 'visible', timeout: 15_000 });
    const ordersText = await page.locator('body').innerText();
    record(ordersText.includes(orderId.slice(0, 8)), 'merchant order list shows the synthetic order', orderId.slice(0, 8));
    record(ordersText.includes('PENDING'), 'merchant order list shows PENDING');
    record(ordersText.includes('کاربر آزمایشی ال‌اس‌ای'), 'merchant order list shows synthetic customer');
    record(ordersText.includes('پیک محلی'), 'merchant order list shows the stored carrier');
  }

  const known = await fetch(`${base}/products/manto-katan-jelo-baste`, { redirect: 'manual' });
  const unknown = await fetch(`${base}/products/no-such-product-lse`, { redirect: 'manual' });
  record(known.status === 200, 'published product HTTP status', String(known.status));
  record(unknown.status === 404, 'unknown product HTTP status is 404, not a soft 200', String(unknown.status));

  for (const width of [320, 390, 1440]) {
    for (const path of ['/', '/catalog', '/checkout']) {
      await checkLayout(page, path, width);
    }
  }

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${base}/`, { waitUntil: 'networkidle' });
  await page.keyboard.press('Tab');
  const focused = await page.evaluate(() => ({
    tag: document.activeElement?.tagName ?? '',
    label: document.activeElement?.getAttribute('aria-label') ?? '',
  }));
  record(focused.tag !== 'BODY', 'keyboard focus enters an interactive storefront control', focused.tag);

  await context.close();
}

checkLoopbackBase();
if (!existsSync(chromePath)) {
  refuse(`Chrome binary not found at ${chromePath}; set CHROME_PATH`);
}

let browser;
try {
  browser = await chromium.launch({ executablePath: chromePath, headless: true });
  if (failClosedMode) await runFailClosed(browser);
  else await runFull(browser);
} catch (error) {
  failed += 1;
  console.error(`FAIL unexpected browser error: ${error instanceof Error ? error.message : String(error)}`);
} finally {
  await browser?.close();
}

console.log(`SUMMARY mode=${failClosedMode ? 'fail-closed' : 'full'} pass=${passed} fail=${failed} base=${base}`);
process.exit(failed === 0 ? 0 : 1);

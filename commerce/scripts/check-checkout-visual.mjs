#!/usr/bin/env node
/**
 * D-177 Phase 2D — real-browser check for the editorial checkout.
 *
 * Drives the installed system Chrome against a LOCAL storefront on a loopback URL
 * only. It uses a synthetic cart and the existing local checkout write path, with
 * no payment provider configured, so the order result must report UNAVAILABLE and
 * the order must remain PENDING.
 *
 * It asserts:
 *
 *   - the checkout shell uses the editorial display face and --sf-* chrome;
 *   - the empty-cart state renders no form;
 *   - invalid fields keep their aria-invalid / aria-describedby / role=alert wiring;
 *   - keyboard order and the visible ink focus ring are intact;
 *   - the two-column desktop layout and single-column phone layout do not overflow;
 *   - a synthetic order reaches the inline success state, shows the gateway's
 *     UNAVAILABLE answer, and never claims a completed payment;
 *   - the cart is cleared after the order is placed;
 *   - native 390/1440 screenshots of the empty, validation and success states.
 *
 * It creates only local synthetic data. It refuses a non-loopback base URL and
 * writes screenshots only.
 */
import { mkdirSync, readFileSync } from 'node:fs';
import path from 'node:path';

import { chromium } from 'playwright-core';

const base = (process.env.COMMERCE_BASE_URL || 'http://127.0.0.1:13003').replace(/\/$/, '');
if (!/^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/.test(base)) {
  console.error(`REFUSED: base URL must be loopback HTTP, got ${base}`);
  process.exit(2);
}

const shotDir = process.env.SHOT_DIR || path.resolve(process.cwd(), '..', 'review');
mkdirSync(shotDir, { recursive: true });

const chromeCandidates = [
  process.env.CHROME_PATH,
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/usr/bin/google-chrome',
  '/usr/bin/chromium',
  '/usr/bin/chromium-browser',
];
const executablePath = chromeCandidates.find((candidate) => candidate && path.isAbsolute(candidate));
if (!executablePath) {
  console.error('REFUSED: no system Chrome path; set CHROME_PATH');
  process.exit(2);
}

let passed = 0;
let failed = 0;
function check(ok, label, detail = '') {
  if (ok) {
    passed += 1;
    console.log(`PASS  ${label}`);
  } else {
    failed += 1;
    console.error(`FAIL  ${label}${detail ? ` — ${detail}` : ''}`);
  }
}

function pngSize(file) {
  try {
    const buffer = readFileSync(file);
    if (buffer.subarray(1, 4).toString() !== 'PNG') return null;
    return { width: buffer.readUInt32BE(16), height: buffer.readUInt32BE(20) };
  } catch {
    return null;
  }
}

async function overflow(page) {
  return page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
}

const browser = await chromium.launch({ executablePath, headless: true });
try {
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    locale: 'fa-IR',
    reducedMotion: 'reduce',
  });
  const page = await context.newPage();

  // --- empty cart ---------------------------------------------------------
  await page.goto(`${base}/`, { waitUntil: 'networkidle' });
  await page.evaluate(() => window.localStorage.clear());
  await page.goto(`${base}/checkout`, { waitUntil: 'networkidle' });

  check(
    (await page.getByRole('heading', { name: 'تسویهٔ خرید' }).count()) === 1,
    'the checkout heading is visible',
  );
  check(
    (await page.getByRole('heading', { name: 'سبد خرید خالی است' }).count()) === 1,
    'empty cart has an explicit state',
  );
  check(
    (await page.locator('form[aria-label="فرم تسویهٔ خرید"]').count()) === 0,
    'empty cart renders no checkout form',
  );
  check(
    (await page.getByRole('link', { name: 'رفتن به فهرست محصولات' }).count()) === 1,
    'empty cart offers the catalog route',
  );
  check((await overflow(page)) <= 0, 'empty checkout has no 390px horizontal overflow');
  await page.setViewportSize({ width: 320, height: 844 });
  check((await overflow(page)) <= 0, 'empty checkout has no 320px horizontal overflow');
  await page.setViewportSize({ width: 390, height: 844 });

  const emptyShot = path.join(shotDir, 'phase-2d-checkout-empty-390.png');
  await page.screenshot({ path: emptyShot, fullPage: true });
  check(pngSize(emptyShot)?.width === 390, 'native 390px empty-checkout screenshot saved');

  // --- build one synthetic cart line -------------------------------------
  await page.goto(`${base}/products/manto-katan-jelo-baste`, { waitUntil: 'networkidle' });
  await page.getByRole('button', { name: /^M/ }).first().click();
  await page.getByRole('button', { name: 'افزودن به سبد خرید' }).click();
  const drawer = page.getByRole('dialog');
  await drawer.waitFor({ state: 'visible', timeout: 10_000 });
  await page.keyboard.press('Escape');
  await drawer.waitFor({ state: 'hidden', timeout: 10_000 });

  await page.goto(`${base}/checkout`, { waitUntil: 'networkidle' });
  const form = page.locator('form[aria-label="فرم تسویهٔ خرید"]');
  await form.waitFor({ state: 'visible', timeout: 15_000 });

  // --- editorial shell and desktop/phone layout --------------------------
  const heading = page.getByRole('heading', { name: 'تسویهٔ خرید' });
  const headingFont = await heading.evaluate((el) => getComputedStyle(el).fontFamily);
  check(
    headingFont.toLowerCase().includes('naskh'),
    'the checkout heading uses the editorial display face',
    headingFont,
  );

  const shell = page.locator('section[aria-labelledby="checkout-customer-title"]');
  const shellBorder = await shell.evaluate((el) => getComputedStyle(el).borderTopColor);
  check(shellBorder === 'rgb(226, 216, 201)', 'the checkout shell uses the sf hairline', shellBorder);

  const submit = page.getByRole('button', { name: 'ثبت سفارش' });
  const submitBackground = await submit.evaluate((el) => getComputedStyle(el).backgroundColor);
  check(submitBackground === 'rgb(23, 19, 15)', 'the submit CTA is the ink button', submitBackground);

  const firstInput = page.locator('#checkout-name');
  const inputBorder = await firstInput.evaluate((el) => getComputedStyle(el).borderTopColor);
  check(inputBorder === 'rgb(185, 168, 146)', 'the fields use the sf strong hairline', inputBorder);

  check((await overflow(page)) <= 0, 'checkout has no 390px horizontal overflow');
  await page.setViewportSize({ width: 320, height: 844 });
  check((await overflow(page)) <= 0, 'checkout has no 320px horizontal overflow');
  await page.setViewportSize({ width: 390, height: 844 });
  const mobileShot = path.join(shotDir, 'phase-2d-checkout-390.png');
  await page.screenshot({ path: mobileShot, fullPage: true });
  check(pngSize(mobileShot)?.width === 390, 'native 390px checkout screenshot saved');

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.waitForTimeout(250);
  const summary = page.locator('section[aria-labelledby="checkout-summary-title"]');
  const panels = await Promise.all([
    shell.boundingBox(),
    summary.boundingBox(),
  ]);
  check(
    Boolean(panels[0] && panels[1] && Math.abs(panels[0].y - panels[1].y) < 12),
    '1440 uses a side-by-side checkout and summary layout',
    JSON.stringify(panels),
  );
  check(
    Boolean(panels[0] && panels[1] && panels[0].x !== panels[1].x),
    '1440 separates the checkout and summary columns',
    JSON.stringify(panels),
  );
  check((await overflow(page)) <= 0, 'checkout has no 1440px horizontal overflow');
  const desktopShot = path.join(shotDir, 'phase-2d-checkout-1440.png');
  await page.screenshot({ path: desktopShot, fullPage: true });
  check(pngSize(desktopShot)?.width === 1440, 'native 1440px checkout screenshot saved');

  // --- keyboard order and focus ring -------------------------------------
  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(250);
  await firstInput.focus();
  await page.keyboard.press('Tab');
  const afterName = await page.evaluate(() => document.activeElement?.id ?? '');
  check(afterName === 'checkout-phone', 'keyboard moves from name to phone', afterName);

  await page.keyboard.press('Tab');
  const afterPhone = await page.evaluate(() => document.activeElement?.id ?? '');
  check(afterPhone === 'checkout-address', 'keyboard moves from phone to address', afterPhone);

  await page.keyboard.press('Tab');
  const afterAddress = await page.evaluate(() => document.activeElement?.id ?? '');
  check(afterAddress === 'checkout-postal', 'keyboard moves from address to postal code', afterAddress);

  const focusRing = await page.evaluate(() => {
    const active = document.activeElement;
    if (!active) return null;
    const style = getComputedStyle(active);
    return {
      width: Number.parseFloat(style.outlineWidth),
      lineStyle: style.outlineStyle,
      color: style.outlineColor,
    };
  });
  check(
    Boolean(
      focusRing &&
        focusRing.width >= 2 &&
        focusRing.lineStyle === 'solid' &&
        focusRing.color === 'rgb(23, 19, 15)',
    ),
    'keyboard focus paints the storefront ink ring',
    JSON.stringify(focusRing),
  );

  // --- validation state ---------------------------------------------------
  await page.locator('#checkout-address').fill('تهران، خیابان آزمایشی، پلاک ۱، واحد ۱');
  await page.waitForFunction(
    () => document.querySelectorAll('input[name="checkout-shipping"]').length === 3,
    null,
    { timeout: 10_000 },
  );
  await submit.click();

  await page.locator('#checkout-name-error').waitFor({ state: 'visible', timeout: 10_000 });
  await page.waitForFunction(() => document.activeElement?.id === 'checkout-name', null, {
    timeout: 5_000,
  });
  check(true, 'invalid submit moves focus to the first invalid field');
  const invalidName = await firstInput.getAttribute('aria-invalid');
  const describedBy = await firstInput.getAttribute('aria-describedby');
  check(invalidName === 'true', 'a validation error marks the field invalid', String(invalidName));
  check(
    describedBy === 'checkout-name-error',
    'a validation error is connected through aria-describedby',
    String(describedBy),
  );
  check(
    (await page.locator('#checkout-phone-error').count()) === 1 &&
      (await page.locator('#checkout-postal-error').count()) === 1,
    'all required-field errors render',
  );
  check((await overflow(page)) <= 0, 'validation state has no 390px horizontal overflow');
  await page.setViewportSize({ width: 320, height: 844 });
  check((await overflow(page)) <= 0, 'validation state has no 320px horizontal overflow');
  await page.setViewportSize({ width: 390, height: 844 });
  const errorShot = path.join(shotDir, 'phase-2d-checkout-errors-390.png');
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: errorShot, fullPage: true });
  check(pngSize(errorShot)?.width === 390, 'native 390px validation screenshot saved');

  // --- synthetic sandbox order -------------------------------------------
  await firstInput.fill('کاربر آزمایشی فاز دو دی');
  await page.locator('#checkout-phone').fill('09120000000');
  await page.locator('#checkout-postal').fill('1111111111');
  await page.getByRole('radio', { name: /پیک محلی/ }).check();

  await submit.click();
  await page.getByRole('heading', { name: 'سفارش ثبت شد' }).waitFor({ timeout: 30_000 });

  const resultRegion = page.locator('section[aria-labelledby="checkout-result-title"]');
  await resultRegion.waitFor({ state: 'visible', timeout: 10_000 });
  const resultText = (await resultRegion.innerText()).replace(/\s+/g, ' ').trim();
  check(resultText.includes('UNAVAILABLE'), 'the result reports the fail-closed gateway status');
  check(resultText.includes('در انتظار پرداخت'), 'the result states the order is awaiting payment');
  check(
    resultText.includes('پرداخت آنلاین انجام نشده'),
    'the result says no online payment was taken',
  );
  check(!resultText.includes('پرداخت با موفقیت'), 'the result never claims a successful payment');
  check(
    /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i.test(resultText),
    'the result shows the synthetic order id',
  );
  check(
    (await page.getByRole('button', { name: 'سبد خرید', exact: true }).count()) === 1,
    'the cart is cleared after the order',
  );
  check((await form.count()) === 0, 'the cleared checkout form is not left beside the result');
  check(
    (await summary.count()) === 0,
    'the zero-total summary is not left beside the completed result',
  );
  check((await overflow(page)) <= 0, 'success state has no 390px horizontal overflow');
  await page.setViewportSize({ width: 320, height: 844 });
  check((await overflow(page)) <= 0, 'success state has no 320px horizontal overflow');
  await page.setViewportSize({ width: 390, height: 844 });

  await page.evaluate(() => window.scrollTo(0, 0));
  const successMobile = path.join(shotDir, 'phase-2d-checkout-success-390.png');
  await page.screenshot({ path: successMobile, fullPage: true });
  check(pngSize(successMobile)?.width === 390, 'native 390px success screenshot saved');

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.waitForTimeout(250);
  check((await overflow(page)) <= 0, 'success state has no 1440px horizontal overflow');
  const successDesktop = path.join(shotDir, 'phase-2d-checkout-success-1440.png');
  await page.screenshot({ path: successDesktop, fullPage: true });
  check(pngSize(successDesktop)?.width === 1440, 'native 1440px success screenshot saved');

  await context.close();
} catch (error) {
  failed += 1;
  console.error(`FAIL unexpected browser error: ${error instanceof Error ? error.message : String(error)}`);
} finally {
  await browser?.close();
}

console.log(`SUMMARY phase=2d pass=${passed} fail=${failed} base=${base} shots=${shotDir}`);
process.exit(failed === 0 ? 0 : 1);

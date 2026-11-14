#!/usr/bin/env node
/**
 * D-177 Phase 2A — real-browser accessibility check for the cart drawer.
 *
 * Why this exists: the drawer's opener is the header button, NOT a Radix
 * `Dialog.Trigger`, so focus restoration is our own code and cannot be proven by
 * the Node suite (no DOM there). This runs the installed `playwright-core`
 * against the LOCAL system Chrome, on the loopback base URL only, and asserts:
 *
 *   - keyboard opening puts focus inside the dialog;
 *   - Tab and Shift+Tab stay inside the dialog (Radix focus trap);
 *   - Escape and the close control both return focus to the opener;
 *   - when the opener is disabling itself (PDP add), the visible header cart
 *     trigger is the fallback;
 *   - the focus ring is actually painted (ink outline, not `none`);
 *   - a populated drawer keeps the page free of horizontal overflow at 320px;
 *   - native screenshots at 390px and 1440px, saved and dimension-verified.
 *
 * It creates no data: the cart is browser `localStorage` only, and the script
 * refuses any non-loopback base URL. It writes screenshots only (no product,
 * order or credential change).
 */
import { existsSync, mkdirSync, readFileSync } from 'node:fs';
import path from 'node:path';

import { chromium } from 'playwright-core';

const base = (process.env.COMMERCE_BASE_URL || 'http://127.0.0.1:13001').replace(/\/$/, '');
if (!/^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/.test(base)) {
  console.error(`REFUSED: base URL must be loopback, got ${base}`);
  process.exit(2);
}

const shotDir = process.env.SHOT_DIR || path.resolve(process.cwd(), '..', '..', 'review');
mkdirSync(shotDir, { recursive: true });

const chromeCandidates = [
  process.env.CHROME_PATH,
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  '/usr/bin/google-chrome',
  '/usr/bin/chromium',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
].filter(Boolean);
const executablePath = chromeCandidates.find((p) => existsSync(p));
if (!executablePath) {
  console.error('BLOCKED: no system Chrome found. Set CHROME_PATH.');
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
    console.log(`FAIL  ${label}${detail ? ` — ${detail}` : ''}`);
  }
}

function pngSize(file) {
  const buf = readFileSync(file);
  const signature = buf.subarray(0, 8).toString('hex');
  if (signature !== '89504e470d0a1a0a') return null;
  return { width: buf.readUInt32BE(16), height: buf.readUInt32BE(20) };
}

const browser = await chromium.launch({ executablePath, headless: true });
const page = await browser.newPage({ viewport: { width: 390, height: 844 } });

const activeInfo = () =>
  page.evaluate(() => {
    const el = document.activeElement;
    const cs = el ? getComputedStyle(el) : null;
    return {
      tag: el?.tagName ?? null,
      label: el?.getAttribute('aria-label') || el?.textContent?.trim().slice(0, 32) || '',
      inDialog: !!el?.closest('[role="dialog"]'),
      isCartTrigger: !!el?.closest('[data-cart-trigger]'),
      focusVisible: el?.matches?.(':focus-visible') ?? false,
      outlineWidth: cs?.outlineWidth ?? '',
      outlineColor: cs?.outlineColor ?? '',
    };
  });

try {
  // ---- empty cart, keyboard open -------------------------------------------------
  await page.goto(`${base}/`, { waitUntil: 'networkidle' });
  await page.evaluate(() => window.localStorage.removeItem('commerce.cart.v1'));
  await page.reload({ waitUntil: 'networkidle' });

  const trigger = page.locator('[data-cart-trigger]');
  await trigger.focus();
  check(await page.evaluate(() => document.activeElement?.hasAttribute('data-cart-trigger')), 'keyboard focus reaches the cart trigger');

  await page.keyboard.press('Enter');
  await page.locator('[role="dialog"]').waitFor({ state: 'visible' });
  let info = await activeInfo();
  check(info.inDialog, 'Enter opens the drawer and moves focus inside it', info.tag);

  // ---- Tab / Shift+Tab trap ------------------------------------------------------
  let trapped = true;
  for (let i = 0; i < 8; i += 1) {
    await page.keyboard.press('Tab');
    const inside = await page.evaluate(() => !!document.activeElement?.closest('[role="dialog"]'));
    if (!inside) trapped = false;
  }
  check(trapped, 'Tab stays inside the dialog (8 presses)');

  let trappedBack = true;
  for (let i = 0; i < 4; i += 1) {
    await page.keyboard.press('Shift+Tab');
    const inside = await page.evaluate(() => !!document.activeElement?.closest('[role="dialog"]'));
    if (!inside) trappedBack = false;
  }
  check(trappedBack, 'Shift+Tab stays inside the dialog (4 presses)');

  // ---- Escape restores the opener ------------------------------------------------
  await page.keyboard.press('Escape');
  await page.locator('[role="dialog"]').waitFor({ state: 'detached' });
  info = await activeInfo();
  check(info.isCartTrigger, 'Escape returns focus to the cart trigger', info.label);

  // ---- close control restores the opener -----------------------------------------
  await page.keyboard.press('Enter'); // trigger still focused
  await page.locator('[role="dialog"]').waitFor({ state: 'visible' });
  const closeBtn = page.getByRole('button', { name: 'بستن' });
  await closeBtn.click();
  await page.locator('[role="dialog"]').waitFor({ state: 'detached' });
  info = await activeInfo();
  check(info.isCartTrigger, 'the close control returns focus to the cart trigger', info.label);

  // ---- visible focus ring --------------------------------------------------------
  await page.keyboard.press('Enter');
  await page.locator('[role="dialog"]').waitFor({ state: 'visible' });
  await page.keyboard.press('Tab');
  info = await activeInfo();
  const ringPainted = info.focusVisible && parseFloat(info.outlineWidth) > 0;
  check(ringPainted, 'a visible focus ring is painted inside the dialog', `${info.outlineWidth} ${info.outlineColor}`);
  await page.keyboard.press('Escape');
  await page.locator('[role="dialog"]').waitFor({ state: 'detached' });

  // ---- populated cart: add a real variant through the PDP -------------------------
  const firstProduct = await page.locator('article h3 a').first().getAttribute('href');
  await page.goto(`${base}${firstProduct}`, { waitUntil: 'networkidle' });
  await page.getByRole('button', { name: /^M\s*موجود/ }).click();
  await page.getByRole('button', { name: 'افزودن به سبد خرید' }).click();
  await page.locator('[role="dialog"]').waitFor({ state: 'visible' });
  const lineCount = await page.locator('[role="dialog"] li').count();
  check(lineCount === 1, 'populated drawer shows the added line');

  // The add button is still focusable, so it IS the correct return target.
  await page.keyboard.press('Escape');
  await page.locator('[role="dialog"]').waitFor({ state: 'detached' });
  info = await activeInfo();
  check(/افزودن/.test(info.label), 'focus returns to the PDP add button that opened the drawer', info.label);

  // …and when that opener no longer exists, the visible cart trigger is used.
  // Direct DOM click: after adding, the button may be disabled for a beat and
  // its accessible name can change, which makes a role locator flaky here.
  const foundAdd = await page.evaluate(() => {
    const button = [...document.querySelectorAll('button')].find((el) =>
      el.textContent?.includes('افزودن به سبد خرید'),
    );
    if (!button) return false;
    button.click();
    return true;
  });
  check(foundAdd, 'the PDP add control is still present for the fallback case');
  await page.locator('[role="dialog"]').waitFor({ state: 'visible' });
  await page.evaluate(() => {
    const button = [...document.querySelectorAll('button')].find((el) =>
      el.textContent?.includes('افزودن به سبد خرید'),
    );
    button?.remove();
  });
  await page.keyboard.press('Escape');
  await page.locator('[role="dialog"]').waitFor({ state: 'detached' });
  info = await activeInfo();
  check(info.isCartTrigger, 'a removed opener falls back to the visible cart trigger', info.label);

  // ---- 320px overflow with the populated drawer open -----------------------------
  await page.setViewportSize({ width: 320, height: 800 });
  await trigger.click();
  await page.locator('[role="dialog"]').waitFor({ state: 'visible' });
  const narrow = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
    dialogRight: document.querySelector('[role="dialog"]').getBoundingClientRect().right,
    dialogLeft: document.querySelector('[role="dialog"]').getBoundingClientRect().left,
  }));
  check(narrow.scrollWidth <= narrow.clientWidth, 'no horizontal overflow at 320 with the drawer open', JSON.stringify(narrow));
  check(narrow.dialogLeft >= 0 && narrow.dialogRight <= 320, 'the drawer fits the 320px viewport');

  // ---- native screenshots 390 + 1440 ---------------------------------------------
  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(250);
  const shot390 = path.join(shotDir, 'drawer-populated-390-native.png');
  await page.screenshot({ path: shot390 });
  const size390 = pngSize(shot390);
  check(size390?.width === 390 && size390?.height === 844, 'native 390px screenshot saved', JSON.stringify(size390));

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.waitForTimeout(250);
  const shot1440 = path.join(shotDir, 'drawer-populated-1440-native.png');
  await page.screenshot({ path: shot1440 });
  const size1440 = pngSize(shot1440);
  check(size1440?.width === 1440 && size1440?.height === 900, 'native 1440px screenshot saved', JSON.stringify(size1440));

  // ---- last resort when BOTH preferred targets are unavailable -------------------
  // The drawer is open with a populated cart from the screenshots above; remove
  // the header trigger so neither it nor the opener can receive focus.
  const bothGone = await page.evaluate(() => {
    document.querySelector('[data-cart-trigger]')?.remove();
    return !document.querySelector('[data-cart-trigger]');
  });
  check(bothGone, 'preferred return targets (opener and cart trigger) are unavailable');

  await page.keyboard.press('Escape');
  await page.locator('[role="dialog"]').waitFor({ state: 'detached' });
  const landing = await page.evaluate(() => {
    const el = document.activeElement;
    const rect = el?.getBoundingClientRect();
    return {
      tag: el?.tagName ?? null,
      isBody: el === document.body,
      inMain: !!el?.closest('#main-content'),
      visible: !!rect && rect.width > 0 && rect.height > 0,
      tabindex: el?.getAttribute('tabindex'),
      text: el?.textContent?.trim().slice(0, 40) ?? '',
    };
  });
  check(
    landing.tag === 'H1' && landing.inMain && !landing.isBody && landing.visible,
    'with both targets gone, focus lands on the visible main-content heading',
    JSON.stringify(landing),
  );

  const shotFallback = path.join(shotDir, 'drawer-fallback-focus-1440.png');
  await page.screenshot({ path: shotFallback });
  check(pngSize(shotFallback)?.width === 1440, 'fallback-focus screenshot saved', shotFallback);

  console.log(`\nScreenshots: ${shot390}\n             ${shot1440}\n             ${shotFallback}`);
} catch (error) {
  failed += 1;
  console.error(`FAIL  script aborted — ${error instanceof Error ? error.stack : String(error)}`);
} finally {
  await browser.close();
}

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);

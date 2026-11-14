#!/usr/bin/env node
/**
 * D-177 Phase 2C — real-browser check for the editorial PDP.
 *
 * Drives the installed system Chrome against the LOCAL storefront on a loopback
 * URL only. It asserts, against the real product fixture:
 *
 *   - the display-face heading, 3:4 gallery and no horizontal overflow at 390;
 *   - the colour chip re-scopes the gallery (alt text carries the colour);
 *   - a size this colour does not stock is DISABLED and labelled ناموجود;
 *   - choosing an in-stock size reveals the quantity control;
 *   - add-to-cart opens the drawer and closing it returns focus to the add
 *     button (the Phase 2A regression, still intact);
 *   - the size-chart modal opens, is the storefront chrome, closes on Escape and
 *     returns focus to its trigger;
 *   - at 1440 the layout is the two-column gallery/buy-box grid, and the buy box
 *     still precedes the description in document order at both widths;
 *   - native 390/1440 screenshots plus the size-chart and added-to-cart states.
 *
 * It writes screenshots only; cart state is browser localStorage.
 */
import { mkdirSync, readFileSync } from 'node:fs';
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

const browser = await chromium.launch({ executablePath, headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });

  await page.goto(`${base}/catalog`, { waitUntil: 'networkidle' });
  const productHref = await page.locator('article h3 a').first().getAttribute('href');
  check(!!productHref, 'a published product is reachable from the catalog', productHref ?? '');
  await page.goto(`${base}${productHref}`, { waitUntil: 'networkidle' });

  const heading = page.locator('main h1');
  check(await heading.isVisible(), 'the product heading is visible');
  const headingFont = await heading.evaluate((el) => getComputedStyle(el).fontFamily);
  check(headingFont.toLowerCase().includes('naskh'), 'the heading uses the editorial display face', headingFont);

  const hero = page.locator('main article img').first();
  const heroBox = await hero.evaluate((el) => {
    const box = el.getBoundingClientRect();
    return { ratio: Math.round((box.height / box.width) * 1000) / 1000, width: Math.round(box.width) };
  });
  check(Math.abs(heroBox.ratio - 4 / 3) < 0.02, 'the hero frame is 3:4', JSON.stringify(heroBox));

  const overflow390 = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  check(overflow390 <= 0, 'no horizontal overflow at 390', `overflow=${overflow390}`);

  const shot390 = path.join(shotDir, 'pdp-390.png');
  await page.screenshot({ path: shot390 });
  check(pngSize(shot390)?.width === 390, 'native 390px PDP screenshot saved');

  // Colour re-scopes the gallery.
  const colorChip = page.getByRole('button', { name: /^کرم/ }).first();
  check((await colorChip.count()) === 1, 'the cream colour chip renders');
  if ((await colorChip.count()) === 1) {
    await colorChip.click();
    check(
      (await colorChip.getAttribute('aria-pressed')) === 'true',
      'the chosen colour reports aria-pressed',
    );
    const alt = await page.locator('main article img').first().getAttribute('alt');
    check((alt ?? '').includes('کرم'), 'the gallery follows the chosen colour', alt ?? '');
  }

  // Cream has no L in stock: the cell must exist and be disabled.
  const outSize = page.getByRole('button', { name: /^L\s*ناموجود/ }).first();
  check((await outSize.count()) === 1, 'the out-of-stock size cell still renders');
  check(await outSize.isDisabled(), 'the out-of-stock size cell is disabled');

  await page.getByRole('button', { name: /^M\s*موجود/ }).first().click();
  check(await page.locator('#pdp-quantity').isVisible(), 'choosing a stocked size reveals the quantity control');

  const addButton = page.getByRole('button', { name: /افزودن به سبد خرید/ });
  await addButton.click();
  const drawer = page.locator('[role="dialog"]');
  await drawer.waitFor({ state: 'visible' });
  check((await drawer.locator('li').count()) >= 1, 'add-to-cart puts the line in the drawer');
  const shotAdded = path.join(shotDir, 'pdp-390-added.png');
  await page.screenshot({ path: shotAdded });
  check(pngSize(shotAdded)?.width === 390, 'native 390px added-to-cart screenshot saved');

  await drawer.getByRole('button', { name: 'بستن' }).click();
  await drawer.waitFor({ state: 'detached' });
  const returnedToAdd = await page.evaluate(
    () => document.activeElement?.textContent?.includes('افزودن به سبد خرید') ?? false,
  );
  check(returnedToAdd, 'closing the drawer returns focus to the PDP add button');

  // Size chart: storefront chrome, Escape closes, focus returns to the guide.
  const guide = page.getByRole('button', { name: /راهنمای اندازه/ }).first();
  await guide.click();
  const chart = page.locator('[role="dialog"]');
  await chart.waitFor({ state: 'visible' });
  check(
    (await chart.getAttribute('data-surface')) === 'storefront',
    'the size chart uses the storefront modal chrome',
  );
  const shotChart = path.join(shotDir, 'pdp-390-sizechart.png');
  await page.screenshot({ path: shotChart });
  check(pngSize(shotChart)?.width === 390, 'native 390px size-chart screenshot saved');

  await page.keyboard.press('Escape');
  await chart.waitFor({ state: 'detached' });
  const returnedToGuide = await page.evaluate(
    () => document.activeElement?.textContent?.includes('راهنمای اندازه') ?? false,
  );
  check(returnedToGuide, 'Escape returns focus to the size-guide trigger');

  // Buy box precedes the description in document order.
  const order390 = await page.evaluate(() => {
    const add = [...document.querySelectorAll('button')].find((el) =>
      el.textContent?.includes('افزودن به سبد خرید'),
    );
    const description = document.querySelector('#pdp-description');
    if (!add || !description) return null;
    return {
      addTop: Math.round(add.getBoundingClientRect().top + window.scrollY),
      descriptionTop: Math.round(description.getBoundingClientRect().top + window.scrollY),
    };
  });
  check(
    order390 !== null && order390.addTop < order390.descriptionTop,
    'the CTA precedes the long description on mobile',
    JSON.stringify(order390),
  );

  // ---- 1440 -------------------------------------------------------------
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`${base}${productHref}`, { waitUntil: 'networkidle' });

  const layout = await page.evaluate(() => {
    const root = document.querySelector('main article > div');
    if (!root) return null;
    const style = getComputedStyle(root);
    return {
      columns: style.gridTemplateColumns.split(' ').filter(Boolean).length,
      overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      addTop: (() => {
        const add = [...document.querySelectorAll('button')].find((el) =>
          el.textContent?.includes('افزودن به سبد خرید'),
        );
        return add ? Math.round(add.getBoundingClientRect().top + window.scrollY) : -1;
      })(),
      descriptionTop: (() => {
        const description = document.querySelector('#pdp-description');
        return description
          ? Math.round(description.getBoundingClientRect().top + window.scrollY)
          : -1;
      })(),
    };
  });
  check(layout?.columns === 2, 'the desktop layout is a two-column gallery/buy box grid', JSON.stringify(layout));
  check(layout?.overflow <= 0, 'no horizontal overflow at 1440', `overflow=${layout?.overflow}`);
  check(
    (layout?.addTop ?? -1) > 0 && (layout?.addTop ?? 0) < (layout?.descriptionTop ?? 0),
    'the buy box sits above the description at 1440',
    JSON.stringify(layout),
  );

  const shot1440 = path.join(shotDir, 'pdp-1440.png');
  await page.screenshot({ path: shot1440 });
  const size1440 = pngSize(shot1440);
  check(
    size1440?.width === 1440 && size1440?.height === 900,
    'native 1440px PDP screenshot saved',
    JSON.stringify(size1440),
  );

  console.log(
    `\nScreenshots: ${shot390}\n             ${shotAdded}\n             ${shotChart}\n             ${shot1440}`,
  );
} finally {
  await browser.close();
}

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);

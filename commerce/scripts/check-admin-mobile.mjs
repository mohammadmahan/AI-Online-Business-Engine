#!/usr/bin/env node
/**
 * Repeatable browser regression for the admin shell's page-level overflow.
 *
 * The inventory table is intentionally wider than a phone: its scroll wrapper
 * must scroll, while the DOCUMENT must not. `contain: paint` on the wrapper is
 * the source fix; this check measures both widths at 320, 390 and desktop.
 *
 * Requires a running authenticated-capable admin server and generated local
 * credentials:
 *   COMMERCE_BASE_URL=http://127.0.0.1:13002 \
 *   ADMIN_USERNAME=... ADMIN_PASSWORD=... npm run check:admin-mobile
 *
 * CHROME_PATH may override the system Chrome binary. This is an isolated local
 * check; it never writes product or order data.
 */
import { chromium } from 'playwright-core';

const base = (process.env.COMMERCE_BASE_URL || 'http://localhost:13001').replace(/\/$/, '');
const username = process.env.ADMIN_USERNAME;
const password = process.env.ADMIN_PASSWORD;
const chromePath =
  process.env.CHROME_PATH ||
  (process.platform === 'darwin'
    ? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    : '/usr/bin/google-chrome');

if (!username || !password) {
  console.error('FAIL ADMIN_USERNAME and ADMIN_PASSWORD are required');
  process.exit(2);
}

const widths = [320, 390, 1440];
let failed = false;
const browser = await chromium.launch({ executablePath: chromePath, headless: true });

try {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const page = await context.newPage();

  await page.goto(`${base}/admin/login`, { waitUntil: 'domcontentloaded' });
  await page.getByLabel('نام کاربری').fill(username);
  await page.getByLabel('گذرواژه').fill(password);
  await Promise.all([
    page.waitForURL((url) => url.pathname === '/admin', { waitUntil: 'commit', timeout: 20_000 }),
    page.getByRole('button', { name: 'ورود' }).click(),
  ]);

  for (const width of widths) {
    await page.setViewportSize({ width, height: 844 });
    await page.goto(`${base}/admin/inventory`, { waitUntil: 'networkidle' });
    const measured = await page.evaluate(() => {
      const de = document.documentElement;
      const t = document.querySelector('table');
      const w = t?.parentElement ?? null;
      return {
        vw: innerWidth,
        documentScrollWidth: de.scrollWidth,
        bodyScrollWidth: document.body.scrollWidth,
        dir: getComputedStyle(document.body).direction,
        tableWrapper: w
          ? {
              clientWidth: w.clientWidth,
              scrollWidth: w.scrollWidth,
              overflowX: getComputedStyle(w).overflowX,
              contain: getComputedStyle(w).contain,
            }
          : null,
      };
    });
    console.log(`MEASURE ${width}px ${JSON.stringify(measured)}`);
    if (measured.documentScrollWidth > measured.vw) {
      console.error(`FAIL page overflow at ${width}px: ${measured.documentScrollWidth} > ${width}`);
      failed = true;
    }
    if (measured.dir !== 'rtl') {
      console.error(`FAIL RTL lost at ${width}px: direction=${measured.dir}`);
      failed = true;
    }
    if (measured.tableWrapper && measured.tableWrapper.overflowX !== 'auto') {
      console.error(`FAIL table wrapper lost horizontal scrolling at ${width}px`);
      failed = true;
    }
    if (
      width < 1024 &&
      measured.tableWrapper &&
      measured.tableWrapper.scrollWidth <= measured.tableWrapper.clientWidth
    ) {
      console.error(`FAIL wide table does not scroll on a narrow viewport at ${width}px`);
      failed = true;
    }
  }

  if (widths.includes(320) && (await page.locator('nav').count()) === 0) {
    console.error('FAIL admin navigation is absent');
    failed = true;
  }
} catch (error) {
  console.error(`FAIL admin mobile check could not complete: ${error.message}`);
  failed = true;
} finally {
  await browser.close();
}

process.exit(failed ? 1 : 0);

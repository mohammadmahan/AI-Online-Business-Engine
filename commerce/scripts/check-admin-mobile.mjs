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

  await page.goto(`${base}/admin/login`, { waitUntil: 'networkidle' });
  const userField = page.getByLabel('نام کاربری');
  await userField.click();
  await userField.pressSequentially(username);
  const passwordField = page.getByLabel('گذرواژه');
  await passwordField.click();
  await passwordField.pressSequentially(password);
  await page.getByRole('button', { name: 'ورود' }).click();
  await page.waitForFunction(() => location.pathname === '/admin', null, { timeout: 20_000 });

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
        rowCount: t ? t.querySelectorAll('tbody tr').length : 0,
        tableWrapper: w
          ? {
              clientWidth: w.clientWidth,
              scrollWidth: w.scrollWidth,
              tableWidth: t ? t.getBoundingClientRect().width : 0,
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
    if (!measured.tableWrapper || measured.rowCount < 2) {
      console.error(`FAIL populated inventory table missing at ${width}px: rows=${measured.rowCount}`);
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
    if (width < 1024) {
      const scroll = await page.evaluate(() => {
        const w = document.querySelector('table')?.parentElement;
        if (!w) return null;
        // Chromium RTL scrollLeft is 0 at the right edge and negative toward the left.
        w.scrollLeft = -Math.abs(w.scrollWidth - w.clientWidth);
        return { scrollLeft: w.scrollLeft, max: w.scrollWidth - w.clientWidth };
      });
      if (!scroll || scroll.scrollLeft >= 0) {
        console.error(`FAIL table cannot be scrolled horizontally at ${width}px`);
        failed = true;
      }
    }
  }

  for (const path of ['/admin', '/admin/orders']) {
    for (const width of widths) {
      await page.setViewportSize({ width, height: 844 });
      await page.goto(`${base}${path}`, { waitUntil: 'networkidle' });
      const pageOverflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
      console.log(`PAGE ${path} ${width}px overflow=${pageOverflow}`);
      if (pageOverflow) {
        console.error(`FAIL page overflow on ${path} at ${width}px`);
        failed = true;
      }
      if ((await page.locator('nav').count()) === 0) {
        console.error(`FAIL admin navigation absent on ${path} at ${width}px`);
        failed = true;
      }
    }
  }
} catch (error) {
  console.error(`FAIL admin mobile check could not complete: ${error.message}`);
  failed = true;
} finally {
  await browser.close();
}

process.exit(failed ? 1 : 0);

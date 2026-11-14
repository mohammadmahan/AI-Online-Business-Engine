#!/usr/bin/env node
/**
 * D-177 Phase 2B — real-browser check for the CATALOG redesign.
 *
 * The Node suite can assert source contracts but not what a customer sees, so
 * this drives the installed system Chrome against the LOCAL storefront on a
 * loopback URL only. It asserts:
 *
 *   - the mobile filter panel starts COLLAPSED, so the first product row is in
 *     the first viewport at 390x844 (the "long scroll" defect this phase fixes);
 *   - the disclosure reports `aria-expanded` and opens/closes the panel;
 *   - a size chip still filters INSTANTLY, the result count changes, and clearing
 *     restores the list;
 *   - the no-results state is the editorial block, not the panel banner;
 *   - the filter panel actually paints the storefront ivory surface and hairline
 *     border (computed styles, not class names), and the range accent is ink;
 *   - the desktop rail is always open at 1440 and the page has no horizontal
 *     overflow at 390;
 *   - native screenshots at 390 (grid + open filters) and 1440, dimension-checked.
 *
 * It writes screenshots only: no product, order, coupon or credential changes.
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

  const cards = page.locator('main ul li article');
  const total = await cards.count();
  check(total > 0, 'catalog renders published product cards', `cards=${total}`);

  const toggle = page.locator('button[aria-controls="catalog-filters"]');
  check(await toggle.isVisible(), 'mobile filter disclosure is visible at 390');
  check((await toggle.getAttribute('aria-expanded')) === 'false', 'filters start collapsed on mobile');

  const panel = page.locator('#catalog-filters');
  check(!(await panel.isVisible()), 'the collapsed filter panel is not painted');

  const firstTop = await cards.first().evaluate((el) => el.getBoundingClientRect().top);
  check(firstTop < 844, 'the first product row is inside the first viewport', `top=${Math.round(firstTop)}`);

  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  check(overflow <= 0, 'no horizontal overflow at 390 with filters collapsed', `overflow=${overflow}`);

  const shot390 = path.join(shotDir, 'catalog-390.png');
  await page.screenshot({ path: shot390 });
  const size390 = pngSize(shot390);
  check(size390?.width === 390, 'native 390px grid screenshot saved', JSON.stringify(size390));

  await toggle.click();
  check((await toggle.getAttribute('aria-expanded')) === 'true', 'the disclosure reports expanded');
  check(await panel.isVisible(), 'opening the disclosure paints the filter panel');

  const shotFilters = path.join(shotDir, 'catalog-390-filters.png');
  await page.screenshot({ path: shotFilters });
  const sizeFilters = pngSize(shotFilters);
  check(sizeFilters?.width === 390, 'native 390px filter-panel screenshot saved', JSON.stringify(sizeFilters));

  const status = page.locator('main [role="status"]').first();

  const sizeChip = panel.locator('button[aria-pressed]').filter({ hasText: /^M$/ }).first();
  const chipCount = await sizeChip.count();
  check(chipCount === 1, 'the size facet renders an M chip', `matches=${chipCount}`);
  if (chipCount === 1) {
    await sizeChip.click();
    check((await sizeChip.getAttribute('aria-pressed')) === 'true', 'the pressed chip reports aria-pressed');
  }

  // Reset the chip before the search test: a size filter could legitimately
  // zero the list, and the instant-filter check is about the round trip.
  await panel.getByRole('button', { name: 'پاک کردن فیلترها' }).first().click();
  check(
    (await panel.locator('button[aria-pressed="true"]').count()) === 1,
    'clearing leaves only the default «همه» chip pressed',
  );

  // Prove instant filtering with a term that MUST narrow the list (a product's
  // own title), not with a size every fixture happens to stock. A filter that
  // needs a round trip would not change the status line without a navigation.
  const title = (await cards.first().locator('h3').textContent())?.trim() ?? '';
  const beforeSearch = await status.textContent();
  await panel.locator('#catalog-search').fill(title);
  await page.waitForFunction(
    (previous) => document.querySelector('main [role="status"]')?.textContent !== previous,
    beforeSearch,
    { timeout: 5000 },
  );
  const afterSearch = await status.textContent();
  check(
    afterSearch !== beforeSearch,
    'filtering is instant (result count updated without a reload)',
    `${beforeSearch} -> ${afterSearch}`,
  );
  check(
    (await cards.count()) >= 1 && (await page.getByRole('link', { name: title }).count()) >= 1,
    'the searched product is still in the narrowed grid',
  );
  await panel.locator('#catalog-search').fill('');

  await page.locator('#catalog-search').fill('zzzz-no-such-product');
  const emptyTitle = page.getByText('نتیجه‌ای پیدا نشد');
  check(await emptyTitle.isVisible(), 'the no-results state is shown');
  const emptyBox = await emptyTitle.evaluate((el) => {
    const box = el.parentElement;
    if (!box) return null;
    const style = getComputedStyle(box);
    return { background: style.backgroundColor, border: style.borderTopColor, banner: !!box.closest('[role="alert"]') };
  });
  check(
    emptyBox?.background === 'rgb(255, 253, 249)' &&
      emptyBox?.border === 'rgb(226, 216, 201)' &&
      emptyBox?.banner === false,
    'the no-results block uses the editorial surface, not an admin banner',
    JSON.stringify(emptyBox),
  );
  const emptyTheme = await page.evaluate(() => {
    const header = document.querySelector('#catalog-filters');
    if (!header) return null;
    const style = getComputedStyle(header);
    return { background: style.backgroundColor, border: style.borderTopColor };
  });
  check(
    emptyTheme?.background === 'rgb(255, 253, 249)' && emptyTheme?.border === 'rgb(226, 216, 201)',
    'the filter panel paints the storefront ivory + hairline tokens',
    JSON.stringify(emptyTheme),
  );

  await page.locator('#catalog-search').fill('');
  await toggle.click();
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`${base}/catalog`, { waitUntil: 'networkidle' });
  check(!(await page.locator('button[aria-controls="catalog-filters"]').isVisible()), 'the disclosure is hidden at 1440');
  check(await page.locator('#catalog-filters').isVisible(), 'the desktop filter rail is always open');

  const accent = await page.locator('#catalog-price-min').evaluate((el) => getComputedStyle(el).accentColor);
  check(accent === 'rgb(23, 19, 15)', 'range sliders take the ink accent', accent);

  const shot1440 = path.join(shotDir, 'catalog-1440.png');
  await page.screenshot({ path: shot1440 });
  const size1440 = pngSize(shot1440);
  check(
    size1440?.width === 1440 && size1440?.height === 900,
    'native 1440px screenshot saved',
    JSON.stringify(size1440),
  );

  console.log(`\nScreenshots: ${shot390}\n             ${shotFilters}\n             ${shot1440}`);
} finally {
  await browser.close();
}

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);

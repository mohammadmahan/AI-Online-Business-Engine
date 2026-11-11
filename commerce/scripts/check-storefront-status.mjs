#!/usr/bin/env node
/**
 * HTTP status regression check for the storefront product route.
 *
 * Run against a built or dev server:
 *   COMMERCE_BASE_URL=http://localhost:13001 \
 *   KNOWN_PRODUCT_SLUG=manto-katan-jelo-baste \
 *     node scripts/check-storefront-status.mjs
 *
 * The known slug is supplied explicitly because this check never guesses or
 * mutates the database. Unknown slugs must return 404, not a 200 soft 404.
 */
const base = (process.env.COMMERCE_BASE_URL || 'http://localhost:13001').replace(/\/$/, '');
const known = process.env.KNOWN_PRODUCT_SLUG || 'manto-katan-jelo-baste';
const unknown = process.env.UNKNOWN_PRODUCT_SLUG || 'no-such-product';
let failed = false;

async function check(label, path, expected) {
  const response = await fetch(`${base}${path}`, { redirect: 'manual' });
  const status = response.status;
  const ok = status === expected;
  console.log(`${ok ? 'PASS' : 'FAIL'} ${label}: ${path} -> ${status} (expected ${expected})`);
  if (!ok) failed = true;
}

/**
 * CSP regression: the image picker fetches its own compressed data: preview
 * before uploading it. A connect-src without data: makes every image upload
 * fail in the browser even though the upload endpoint is healthy.
 */
async function checkCsp() {
  const response = await fetch(`${base}/admin/login`);
  const csp = response.headers.get('content-security-policy') || '';
  const ok = /connect-src[^;]*\bdata:/.test(csp) && /frame-ancestors 'none'/.test(csp);
  console.log(
    `${ok ? 'PASS' : 'FAIL'} admin CSP: data: preview fetch allowed and framing denied`,
  );
  if (!ok) {
    console.log(`  CSP: ${csp || '<missing>'}`);
    failed = true;
  }
}

try {
  await check('known published product', `/products/${encodeURIComponent(known)}`, 200);
  await check('unknown product', `/products/${encodeURIComponent(unknown)}`, 404);
  await checkCsp();
} catch (error) {
  console.error(`FAIL storefront status check could not reach ${base}: ${error.message}`);
  failed = true;
}

process.exit(failed ? 1 : 0);

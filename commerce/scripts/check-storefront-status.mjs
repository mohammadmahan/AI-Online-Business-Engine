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

try {
  await check('known published product', `/products/${encodeURIComponent(known)}`, 200);
  await check('unknown product', `/products/${encodeURIComponent(unknown)}`, 404);
} catch (error) {
  console.error(`FAIL storefront status check could not reach ${base}: ${error.message}`);
  failed = true;
}

process.exit(failed ? 1 : 0);

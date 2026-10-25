#!/usr/bin/env node
/**
 * D-172 Phase 2 — local demo catalog seed runner.
 *
 * Executes `seed-catalog.sql` against the DISPOSABLE commerce harness so the
 * merchant panel and the storefront can be read on a freshly migrated database.
 * This is development convenience, not a migration and not fixture data for a
 * test suite: `npm run smoke:db` resets the schema itself and must never depend
 * on rows seeded here.
 *
 * FAIL-CLOSED GUARD: like `db:reset`, this validates its target BEFORE it opens
 * a connection and refuses unless that target is the loopback harness on the
 * harness port. It cannot be aimed at the canonical instance, staging or
 * production — those are neither loopback nor on 55432 — and there is no flag
 * that overrides it. A seed that wrote demo products into a shared database
 * would be indistinguishable from a merchant's real catalog.
 *
 * The SQL is INSERT-ONLY (category slug / product slug / variant sku): a second
 * run inserts nothing and rewrites no price, stock, description or category. It
 * therefore does not restore values a checkout or an edit has changed either —
 * `db:reset` followed by `db:seed` is the way back to the pristine demo catalog.
 *
 * The file runs inside the transaction it opens, so a failure at any statement
 * leaves the catalog exactly as it was.
 *
 * Usage:  npm run db:seed        (after: npm run db:up && npm run db:migrate)
 */
import { readFile } from 'node:fs/promises';
import { Client } from 'pg';

const HARNESS_PORT = '55432';
const LOOPBACK_HOSTS = new Set(['127.0.0.1', 'localhost', '::1', '[::1]']);

/** Driver errors are reported by name/code/message; never the connection string. */
function describe(error) {
  if (!(error instanceof Error)) return 'unknown error';
  const code =
    typeof error === 'object' && error !== null && 'code' in error
      ? String(error.code)
      : 'n/a';
  return `${error.name} (${code}): ${error.message}`;
}

const raw = process.env.COMMERCE_DATABASE_URL?.trim();
if (!raw) {
  console.error(
    'db:seed refused — COMMERCE_DATABASE_URL is not set. This harness never guesses a target database.',
  );
  process.exit(1);
}

let target;
try {
  target = new URL(raw);
} catch {
  console.error('db:seed refused — COMMERCE_DATABASE_URL is not a parseable URL.');
  process.exit(1);
}

const host = target.hostname;
const port = target.port || '5432';

if (!LOOPBACK_HOSTS.has(host) || port !== HARNESS_PORT) {
  console.error(
    [
      'db:seed refused — refusing a non-harness target:',
      `  host=${host} port=${port}`,
      `  the seed only ever acts on loopback:${HARNESS_PORT} (the disposable harness),`,
      '  never on the canonical instance, staging or production (D-172 G-2 / D-055).',
    ].join('\n'),
  );
  process.exit(1);
}

let sql;
try {
  sql = await readFile(new URL('./seed-catalog.sql', import.meta.url), 'utf8');
} catch (error) {
  console.error(`db:seed refused — could not read seed-catalog.sql: ${describe(error)}`);
  process.exit(1);
}

const counts = `select
  (select count(*) from commerce.categories)::int as categories,
  (select count(*) from commerce.products)::int as products,
  (select count(*) from commerce.product_variants)::int as variants,
  (select count(*) from commerce.product_images)::int as images`;

const client = new Client({ connectionString: raw });
try {
  await client.connect();
} catch (error) {
  console.error(
    `db:seed could not connect to ${host}:${port} — is the harness running (\`npm run db:up\`)?`,
  );
  console.error(`  ${describe(error)}`);
  process.exit(1);
}

try {
  // Fail closed with an actionable message instead of a raw 42P01: the seed
  // assumes the committed migrations are applied, it never creates the schema.
  const schema = await client.query(`select to_regclass('commerce.products') as table`);
  if (schema.rows[0]?.table === null) {
    console.error(
      'db:seed refused — schema "commerce" has no products table; run `npm run db:migrate` first.',
    );
    process.exitCode = 1;
  } else {
    const server = await client.query('select version() as v');
    const before = await client.query(counts);

    console.log(`db:seed target = ${host}:${port} (loopback harness)`);
    console.log(`db:seed server = ${String(server.rows[0]?.v ?? '').split('(')[0]?.trim()}`);

    try {
      // `seed-catalog.sql` opens and commits its own transaction; a rejected
      // statement leaves it open and aborted, so it is rolled back explicitly
      // here rather than relying on connection teardown.
      await client.query(sql);
    } catch (error) {
      await client.query('rollback').catch(() => {});
      console.error('db:seed failed — the transaction was rolled back; no catalog row changed.');
      console.error(`  ${describe(error)}`);
      process.exitCode = 1;
    }

    if (process.exitCode !== 1) {
      const after = await client.query(counts);
      const b = before.rows[0];
      const a = after.rows[0];
      console.log(
        `db:seed catalog = ${a.categories} categories, ${a.products} products, ` +
          `${a.variants} variants, ${a.images} images`,
      );
      console.log(
        `db:seed delta    = categories ${a.categories - b.categories}, ` +
          `products ${a.products - b.products}, variants ${a.variants - b.variants}` +
          (a.categories === b.categories &&
          a.products === b.products &&
          a.variants === b.variants
            ? ' (already seeded — insert-only run)'
            : ''),
      );
    }
  }
} finally {
  await client.end();
}

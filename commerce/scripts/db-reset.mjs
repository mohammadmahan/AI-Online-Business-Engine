#!/usr/bin/env node
/**
 * D-172 Phase 2 hardening — schema reset for the LOCAL commerce harness.
 *
 * Resets ONLY this track's own state so the committed DDL can be re-applied
 * from scratch:
 *
 *   1. `drop schema "commerce" cascade` — the track's namespace (D-172 G-2).
 *      Dropping it is the point: re-applying 0000 + 0001 to an empty namespace
 *      is the check, and `drop` is restricted to the schema this track owns, so
 *      the canonical engine schemas (canonical/registry/events/…) cannot be
 *      touched even by accident (D-055).
 *   2. clear the Drizzle migration journal — Drizzle would otherwise consider
 *      0000/0001 already applied and leave an EMPTY namespace behind (a silent,
 *      deeply confusing state). The journal rows are deleted, not the table, and
 *      only in the journal Drizzle itself created.
 *
 * FAIL-CLOSED GUARD: the reset refuses unless the target is the loopback harness
 * on the harness port. It cannot be aimed at the canonical instance, staging or
 * production — those are neither loopback nor on 55432 — and there is no flag
 * that overrides this. A reset is the one destructive command in this harness,
 * so it is the one command that will not trust an environment variable alone.
 *
 * Usage:  npm run db:reset        (after: npm run db:migrate re-applies the DDL)
 */
import { Client } from 'pg';

const HARNESS_PORT = '55432';
const LOOPBACK_HOSTS = new Set(['127.0.0.1', 'localhost', '::1', '[::1]']);

const raw = process.env.COMMERCE_DATABASE_URL?.trim();
if (!raw) {
  console.error(
    'db:reset refused — COMMERCE_DATABASE_URL is not set. This harness never guesses a target database.',
  );
  process.exit(1);
}

let target;
try {
  target = new URL(raw);
} catch {
  console.error('db:reset refused — COMMERCE_DATABASE_URL is not a parseable URL.');
  process.exit(1);
}

const host = target.hostname;
const port = target.port || '5432';

if (!LOOPBACK_HOSTS.has(host) || port !== HARNESS_PORT) {
  console.error(
    [
      'db:reset refused — refusing a non-harness target:',
      `  host=${host} port=${port}`,
      `  the reset only ever acts on loopback:${HARNESS_PORT} (the disposable harness),`,
      '  never on the canonical instance, staging or production (D-172 G-2 / D-055).',
    ].join('\n'),
  );
  process.exit(1);
}

const client = new Client({ connectionString: raw });
await client.connect();

try {
  const server = await client.query('select version() as v');
  const before = await client.query(
    `select count(*)::int as n from information_schema.tables where table_schema = 'commerce'`,
  );
  console.log(`db:reset target = ${host}:${port} (loopback harness)`);
  console.log(`db:reset server = ${String(server.rows[0]?.v ?? '').split('(')[0]?.trim()}`);

  // 1. the track's namespace
  await client.query('drop schema if exists "commerce" cascade');
  console.log(
    `db:reset dropped schema "commerce" cascade (was ${before.rows[0]?.n ?? 0} tables)`,
  );

  // 2. the Drizzle journal — wherever Drizzle placed it in THIS database.
  const journals = await client.query(
    `select schemaname, tablename from pg_tables where tablename = '__drizzle_migrations'`,
  );
  if (journals.rows.length === 0) {
    console.log('db:reset migration journal: none present');
  }
  for (const row of journals.rows) {
    const qualified = `"${row.schemaname}"."${row.tablename}"`;
    const cleared = await client.query(`delete from ${qualified}`);
    console.log(`db:reset cleared journal ${qualified} (${cleared.rowCount ?? 0} rows)`);
  }

  const after = await client.query(
    `select count(*)::int as n from information_schema.tables where table_schema = 'commerce'`,
  );
  console.log(
    `db:reset done — schema "commerce" now holds ${after.rows[0]?.n ?? 0} tables; run \`npm run db:migrate\` to re-apply 0000 + 0001`,
  );
} finally {
  await client.end();
}

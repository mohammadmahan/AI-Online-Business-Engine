import { defineConfig } from 'drizzle-kit';

/**
 * D-172 (owner rulings G-2/G-3, 2026-10-10): Drizzle is the single owner of
 * schema definitions and migrations for the E-Commerce & Social Publishing
 * track, against the canonical PostgreSQL instance (D-055).
 *
 * `generate` / `check` are OFFLINE (they never open a connection). Only
 * `migrate` / `push` / `studio` read `DATABASE_URL`, and running them against
 * any environment is an owner-gated act (D-045/D-139). No credential is stored
 * in this repository — the variable is supplied by the environment (D-124).
 *
 * `schemaFilter` keeps this toolchain scoped to the `commerce` schema: the
 * canonical engine schemas (canonical/registry/events/provenance/oms/…) are
 * owned elsewhere (`local/db/schema.sql`, D-055) and must never be touched by
 * a fashion-track migration.
 *
 * Two variables, both explicit, neither guessed:
 * - `DATABASE_URL` — the application's canonical connection variable.
 * - `COMMERCE_DATABASE_URL` — the local disposable harness of
 *   `docker-compose.db.yml` (Phase 2 hardening), so `npm run db:migrate` can be
 *   pointed at the harness without pretending the harness is the canonical
 *   instance. An empty value is still an empty value: nothing here defaults to
 *   a host, a port or a database (D-171 §2.2 discipline).
 */
export default defineConfig({
  dialect: 'postgresql',
  schema: './src/db/schema/index.ts',
  out: './drizzle',
  schemaFilter: ['commerce'],
  dbCredentials: {
    url: process.env.DATABASE_URL ?? process.env.COMMERCE_DATABASE_URL ?? '',
  },
});

import { drizzle } from 'drizzle-orm/node-postgres';
import { Pool } from 'pg';

import * as schema from './schema';

/**
 * D-172 Phase 1 — database access for the E-Commerce track.
 *
 * This module is deliberately INERT: it holds no connection string, opens no
 * connection at import time and reads no environment variable. A caller must
 * pass the canonical instance's connection string explicitly, which keeps the
 * credential boundary (D-045) and the zero-leak rule (D-114/D-124) intact —
 * nothing here can leak a value it never saw.
 *
 * The commerce namespace shares the single canonical PostgreSQL instance ruled
 * as the SSOT (D-172 G-1/G-2, D-055); schema and migrations are owned by Drizzle
 * alone (G-3) through `drizzle.config.ts`.
 */
export function createCommerceDb(connectionString: string) {
  if (!connectionString) {
    // Fail closed rather than silently connecting to a default instance
    // (D-171 §2.2 discipline: absence of configuration is never a pass).
    throw new Error(
      'createCommerceDb requires an explicit connection string (DATABASE_URL); refusing to guess a target database',
    );
  }

  const pool = new Pool({ connectionString });
  return { pool, db: drizzle(pool, { schema }) };
}

export type CommerceDb = ReturnType<typeof createCommerceDb>['db'];
export { schema };

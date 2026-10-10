import { pgSchema } from 'drizzle-orm/pg-core';

/**
 * D-172 Phase 1 — the fashion catalog lives in its own PostgreSQL namespace,
 * mirroring the canonical database's house convention of one schema per domain
 * (`canonical`, `registry`, `oms`, `hitl`, `analytics`, … in
 * `local/db/schema.sql`, D-055).
 *
 * The namespace keeps the E-Commerce track's tables addressable and blast-radius
 * separated from the engine's schemas, while sharing the single canonical
 * instance ruled as the SSOT (D-172 G-1/G-2).
 */
export const commerce = pgSchema('commerce');

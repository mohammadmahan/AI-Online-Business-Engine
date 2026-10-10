import { sql } from 'drizzle-orm';
import {
  bigint,
  boolean,
  check,
  index,
  integer,
  text,
  timestamp,
  uuid,
  varchar,
} from 'drizzle-orm/pg-core';

import { discountType } from './enums';
import { commerce } from './schema';

/**
 * D-172 §2.4 — promotions & discounts.
 *
 * Phase 1 (§1.1–§1.5) did not enumerate a coupon table, while §2.4 requires
 * percentage and fixed-amount coupon codes with expiry dates and minimum spend
 * limits. The table is therefore DERIVED FROM §2.4 and recorded as such in
 * D-172 §5.2 — an interface with no storage would be a fake feature.
 *
 * Money is integer Iranian Toman (D-010). A percentage coupon stores its value
 * as a whole number of percent (1–100) and a fixed coupon its Toman amount;
 * the arithmetic itself belongs to the write path that redeems a coupon
 * (Phase 3/6 checkout), never to this table.
 *
 * `used_count` is the only mutable counter and is guarded non-negative; the
 * redemption increment arrives with the checkout path, which must be idempotent
 * per order (D-027 discipline).
 */
export const coupons = commerce.table(
  'coupons',
  {
    id: uuid('id').primaryKey().defaultRandom(),
    code: varchar('code', { length: 64 }).notNull().unique(),
    discountType: discountType('discount_type').notNull(),
    discountValue: bigint('discount_value', { mode: 'number' }).notNull(),
    minSpend: bigint('min_spend', { mode: 'number' }).notNull().default(0),
    expiresAt: timestamp('expires_at', { withTimezone: true }),
    usageLimit: integer('usage_limit'),
    usedCount: integer('used_count').notNull().default(0),
    isActive: boolean('is_active').notNull().default(true),
    description: text('description'),
    createdAt: timestamp('created_at', { withTimezone: true })
      .notNull()
      .defaultNow(),
    updatedAt: timestamp('updated_at', { withTimezone: true })
      .notNull()
      .defaultNow(),
  },
  (table) => [
    index('coupons_is_active_idx').on(table.isActive),
    index('coupons_expires_at_idx').on(table.expiresAt),
    check('coupons_discount_value_positive', sql`${table.discountValue} > 0`),
    check(
      'coupons_percent_within_range',
      sql`${table.discountType} <> 'PERCENT' or ${table.discountValue} <= 100`,
    ),
    check('coupons_min_spend_non_negative', sql`${table.minSpend} >= 0`),
    check(
      'coupons_usage_limit_positive',
      sql`${table.usageLimit} is null or ${table.usageLimit} > 0`,
    ),
    check('coupons_used_count_non_negative', sql`${table.usedCount} >= 0`),
  ],
);

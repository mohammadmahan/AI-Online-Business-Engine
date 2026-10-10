import type { InferInsertModel, InferSelectModel } from 'drizzle-orm';

import type { DiscountType, coupons } from '../db/schema';

/**
 * D-172 §2.4 — typed contracts for promotions & discounts.
 *
 * `expiresAt` crosses the boundary as an ISO-8601 string (a form field and an
 * HTTP payload are both strings); the service layer converts it to a `Date` and
 * refuses a value that is not a real instant, then the column stores
 * `timestamptz`. Nothing here computes a discount: the money path belongs to
 * the checkout write path (Phase 3/6) so there is exactly one place where
 * basket arithmetic happens.
 */

export type CouponRow = InferSelectModel<typeof coupons>;
export type NewCoupon = InferInsertModel<typeof coupons>;

export interface CouponCreatePayload {
  /** Merchant-facing code; stored upper-cased and trimmed by the service. */
  code: string;
  discountType: DiscountType;
  /** Whole percent (1–100) for PERCENT; integer Toman (> 0) for FIXED. */
  discountValue: number;
  minSpend?: number;
  /** ISO-8601 instant; `null`/absent means the coupon never expires. */
  expiresAt?: string | null;
  /** `null`/absent means unlimited redemptions. */
  usageLimit?: number | null;
  description?: string | null;
  isActive?: boolean;
}

export type CouponUpdatePayload = Partial<Omit<CouponCreatePayload, 'code'>>;

export interface CouponTogglePayload {
  isActive: boolean;
}

/**
 * Read model + derived display state. `state` is computed at render time from
 * the stored row and the current instant, so the panel never shows a coupon as
 * usable when it is expired, exhausted or switched off (fail-closed display).
 */
export interface CouponView extends CouponRow {
  state: 'ACTIVE' | 'INACTIVE' | 'EXPIRED' | 'EXHAUSTED';
}

export type CouponEntity = CouponRow;
export type { DiscountType };

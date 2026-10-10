import type { CouponRow, CouponView } from '@/contracts/promotions';

/**
 * D-172 §2.4 — coupon state, as a PURE module.
 *
 * State is DERIVED at read time from the stored row plus the current instant —
 * never stored — so an expired or exhausted coupon can never be displayed as
 * active (fail-closed display, D-171 §2.2). No basket arithmetic happens here:
 * redemption belongs to the checkout write path (Phase 3/6) and must be
 * idempotent per order (D-027).
 */

export type CouponState = CouponView['state'];

export const COUPON_STATE_LABELS: Record<CouponState, string> = {
  ACTIVE: 'فعال',
  INACTIVE: 'غیرفعال',
  EXPIRED: 'منقضی',
  EXHAUSTED: 'سقف استفاده پر شده',
};

export const COUPON_STATE_TONE: Record<CouponState, 'success' | 'neutral' | 'warning'> = {
  ACTIVE: 'success',
  INACTIVE: 'neutral',
  EXPIRED: 'warning',
  EXHAUSTED: 'warning',
};

export function couponState(row: CouponRow, now = new Date()): CouponState {
  if (!row.isActive) {
    return 'INACTIVE';
  }
  if (row.expiresAt !== null && row.expiresAt.getTime() <= now.getTime()) {
    return 'EXPIRED';
  }
  if (row.usageLimit !== null && row.usedCount >= row.usageLimit) {
    return 'EXHAUSTED';
  }
  return 'ACTIVE';
}

export function toCouponView(row: CouponRow, now = new Date()): CouponView {
  return { ...row, state: couponState(row, now) };
}

export function listCouponViews(rows: CouponRow[], now = new Date()): CouponView[] {
  return rows.map((row) => toCouponView(row, now));
}

/** Human-readable discount description (used by the table and the slip). */
export function describeDiscount(
  row: Pick<CouponRow, 'discountType' | 'discountValue'>,
): { code: 'PERCENT' | 'FIXED'; label: string } {
  return row.discountType === 'PERCENT'
    ? { code: 'PERCENT', label: `٪${row.discountValue}` }
    : { code: 'FIXED', label: `${row.discountValue} تومان` };
}

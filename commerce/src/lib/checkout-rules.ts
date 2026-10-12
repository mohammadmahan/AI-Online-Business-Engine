import type { CheckoutTotals, CouponRuleInput, OrderRefused } from '@/contracts/storefront';

/**
 * D-172 §3.4 — checkout arithmetic and coupon eligibility, as a PURE module.
 *
 * Three consumers share this one definition, which is the point:
 *
 *  - the checkout page, to show a live breakdown while the customer types;
 *  - the optimistic pre-flight check (§3.3), to warn BEFORE submitting;
 *  - the write path, to re-check — `placeOrder` recomputes everything inside a
 *    transaction and refuses on mismatch.
 *
 * Money is integer Toman (D-010) and every rule rounds in the SHOP'S favour
 * where a fraction is unavoidable (a percentage discount is floored), so a
 * discount can never exceed the basket and a total can never go negative.
 * Nothing here is authoritative on its own: the persisted order is computed
 * server-side, and no price is ever taken from the browser as truth.
 */

/** Per-line ceiling a customer may order in one submission. */
export const MAX_LINE_QUANTITY = 5;

/** Distinct lines a single order may carry. */
export const MAX_DISTINCT_LINES = 20;

export type CouponRefusalCode = 'INACTIVE' | 'EXPIRED' | 'EXHAUSTED' | 'MIN_SPEND';

export type CouponDecision =
  | { ok: true; code: string; discount: number }
  | { ok: false; code: CouponRefusalCode; message: string };

const COUPON_MESSAGES: Record<CouponRefusalCode, string> = {
  INACTIVE: 'این کد تخفیف غیرفعال است.',
  EXPIRED: 'مهلت استفاده از این کد تخفیف گذشته است.',
  EXHAUSTED: 'سقف استفاده از این کد تخفیف پر شده است.',
  MIN_SPEND: 'مبلغ سفارش به حداقل خرید این کد تخفیف نمی‌رسد.',
};

/**
 * Discount for a coupon against a subtotal. Precedence mirrors
 * `couponState` in `@/lib/coupon-rules` (inactive → expired → exhausted) so the
 * table's badge and the checkout's answer can never disagree.
 */
export function evaluateCoupon(
  coupon: CouponRuleInput,
  subtotal: number,
  now = new Date(),
): CouponDecision {
  const refuse = (code: CouponRefusalCode): CouponDecision => ({
    ok: false,
    code,
    message: COUPON_MESSAGES[code],
  });

  if (!coupon.isActive) {
    return refuse('INACTIVE');
  }
  if (coupon.expiresAt !== null && coupon.expiresAt.getTime() <= now.getTime()) {
    return refuse('EXPIRED');
  }
  if (coupon.usageLimit !== null && coupon.usedCount >= coupon.usageLimit) {
    return refuse('EXHAUSTED');
  }
  if (subtotal < coupon.minSpend) {
    return refuse('MIN_SPEND');
  }

  const raw =
    coupon.discountType === 'PERCENT'
      ? Math.floor((subtotal * coupon.discountValue) / 100)
      : coupon.discountValue;

  return { ok: true, code: coupon.code, discount: Math.min(raw, subtotal) };
}

/**
 * Order arithmetic. The caller passes validated integers; the discount is
 * clamped to the subtotal here as a last line of defence so the payable amount
 * can never be negative, whatever a coupon row says.
 */
export function computeCheckoutTotals(input: {
  subtotal: number;
  discount: number;
  shipping: number;
}): CheckoutTotals {
  const subtotal = Math.max(0, Math.trunc(input.subtotal));
  const discount = Math.min(Math.max(0, Math.trunc(input.discount)), subtotal);
  const shipping = Math.max(0, Math.trunc(input.shipping));
  return { subtotal, discount, shipping, total: subtotal - discount + shipping };
}

/** Refusal helper so services and actions build identical failure shapes. */
export function checkoutRefusal(
  code: OrderRefused['code'],
  message: string,
  extra?: { field?: string; variantId?: string },
): OrderRefused {
  return { ok: false, code, message, ...extra };
}

/**
 * The one place a line quantity is bounded. Returns `null` when the quantity is
 * acceptable, or the Persian reason it is not.
 */
export function quantityProblem(quantity: unknown): string | null {
  if (typeof quantity !== 'number' || !Number.isInteger(quantity)) {
    return 'تعداد باید عدد صحیح باشد.';
  }
  if (quantity < 1) {
    return 'تعداد باید حداقل یک باشد.';
  }
  if (quantity > MAX_LINE_QUANTITY) {
    return `حداکثر ${MAX_LINE_QUANTITY} عدد از هر گونه در یک سفارش قابل ثبت است.`;
  }
  return null;
}

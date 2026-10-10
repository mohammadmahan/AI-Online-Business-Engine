import type { CouponCreatePayload, CouponView } from '@/contracts/promotions';
import { listCouponViews } from '@/lib/coupon-rules';
import {
  issuesToMessage,
  normalizeCouponCode,
  parseInstant,
  validateCoupon,
} from '@/lib/validation';

import type { CommerceRepository, NewCouponInput } from '../repository';

/**
 * D-172 §2.4 — promotions service (server half).
 *
 * Display state is derived in `@/lib/coupon-rules` (the table renders it); this
 * module owns creation and the activation toggle, including the duplicate-code
 * refusal the database also enforces with its UNIQUE constraint.
 */

export { couponState, describeDiscount, listCouponViews, toCouponView } from '@/lib/coupon-rules';

export type CouponMutationResult =
  | { ok: true; coupon: Awaited<ReturnType<CommerceRepository['createCoupon']>> }
  | {
      ok: false;
      code: 'VALIDATION_ERROR' | 'CONFLICT';
      message: string;
      issues?: Array<{ field: string; message: string }>;
    };

export async function createCoupon(
  repo: CommerceRepository,
  payload: CouponCreatePayload,
  now = new Date(),
): Promise<CouponMutationResult> {
  const validation = validateCoupon(payload, now);
  if (!validation.ok) {
    return {
      ok: false,
      code: 'VALIDATION_ERROR',
      message: issuesToMessage(validation.issues),
      issues: validation.issues,
    };
  }

  const code = normalizeCouponCode(payload.code);
  const existing = await repo.findCouponByCode(code);
  if (existing) {
    return {
      ok: false,
      code: 'CONFLICT',
      message: `کد تخفیف «${code}» قبلاً ثبت شده است.`,
      issues: [{ field: 'code', message: 'این کد تکراری است.' }],
    };
  }

  const expiresAt = parseInstant(payload.expiresAt);
  const input: NewCouponInput = {
    code,
    discountType: payload.discountType,
    discountValue: payload.discountValue,
    minSpend: payload.minSpend ?? 0,
    expiresAt: expiresAt ?? null,
    usageLimit: payload.usageLimit ?? null,
    description: payload.description?.trim() || null,
    isActive: payload.isActive ?? true,
  };

  const coupon = await repo.createCoupon(input);
  return { ok: true, coupon };
}

export async function listCoupons(repo: CommerceRepository): Promise<CouponView[]> {
  return listCouponViews(await repo.listCoupons());
}

export async function setCouponActive(
  repo: CommerceRepository,
  couponId: string,
  isActive: boolean,
): Promise<{ ok: true } | { ok: false; code: 'NOT_FOUND'; message: string }> {
  const updated = await repo.setCouponActive(couponId, isActive);
  return updated
    ? { ok: true }
    : { ok: false, code: 'NOT_FOUND', message: 'کد تخفیف پیدا نشد.' };
}

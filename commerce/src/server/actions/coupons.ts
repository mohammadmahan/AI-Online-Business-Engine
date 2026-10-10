'use server';

import { revalidatePath } from 'next/cache';

import type { CouponCreatePayload } from '@/contracts/promotions';

import { withRepository, type CommerceActionResult } from '../db-context';
import { createCoupon, setCouponActive } from '../services/coupons';

/** D-172 §2.4 — coupon creation and activation toggling. */

export async function createCouponAction(
  payload: CouponCreatePayload,
): Promise<CommerceActionResult<{ couponId: string; code: string }>> {
  const result = await withRepository(async (repository) => {
    const created = await createCoupon(repository, payload);
    return created.ok
      ? { ok: true as const, data: { couponId: created.coupon.id, code: created.coupon.code } }
      : {
          ok: false as const,
          code: created.code,
          message: created.message,
          field: created.issues?.[0]?.field,
        };
  });
  if (result.ok) {
    revalidatePath('/admin/promotions');
  }
  return result;
}

export interface ToggleCouponActionInput {
  couponId: string;
  isActive: boolean;
}

export async function setCouponActiveAction(
  input: ToggleCouponActionInput,
): Promise<CommerceActionResult<{ couponId: string; isActive: boolean }>> {
  const result = await withRepository(async (repository) => {
    const outcome = await setCouponActive(repository, input.couponId, input.isActive);
    return outcome.ok
      ? {
          ok: true as const,
          data: { couponId: input.couponId, isActive: input.isActive },
        }
      : { ok: false as const, code: outcome.code, message: outcome.message };
  });
  if (result.ok) {
    revalidatePath('/admin/promotions');
  }
  return result;
}

'use server';

import { revalidatePath } from 'next/cache';

import type { OrderStatus } from '@/db/schema';

import { withRepository, type CommerceActionResult } from '../db-context';
import { MERCHANT_TRANSITION, setTrackingCode, transitionOrder } from '../services/orders';

/**
 * D-172 §2.3 — fulfillment actions.
 *
 * Both transitions are re-validated server-side against `ORDER_TRANSITIONS`
 * even though the dropdown only offers legal options: the option list is a
 * courtesy, the refusal is the guarantee.
 */

export interface TransitionOrderActionInput {
  orderId: string;
  status: OrderStatus;
}

export async function transitionOrderAction(
  input: TransitionOrderActionInput,
): Promise<CommerceActionResult<{ orderId: string; status: OrderStatus }>> {
  const result = await withRepository(async (repository) => {
    // The actor is the MERCHANT PANEL: the trail must not attribute an owner's
    // decision to a machine, and this is the only human-facing transition path.
    const outcome = await transitionOrder(
      repository,
      input.orderId,
      input.status,
      MERCHANT_TRANSITION,
    );
    return outcome.ok
      ? { ok: true as const, data: { orderId: input.orderId, status: input.status } }
      : { ok: false as const, code: outcome.code, message: outcome.message };
  });
  if (result.ok) {
    revalidatePath('/admin/orders');
    revalidatePath(`/admin/orders/${input.orderId}/slip`);
  }
  return result;
}

export interface TrackingCodeActionInput {
  orderId: string;
  trackingCode: string;
}

/**
 * §2.3 — recording the postal code is what triggers the buyer SMS in the
 * roadmap's flow; the SMS adapter is a Phase 6 deliverable and is NOT bound
 * here, so this action records the code and says nothing is sent yet.
 */
export async function setTrackingCodeAction(
  input: TrackingCodeActionInput,
): Promise<CommerceActionResult<{ orderId: string; trackingCode: string }>> {
  const result = await withRepository(async (repository) => {
    const outcome = await setTrackingCode(repository, input.orderId, input.trackingCode);
    return outcome.ok
      ? {
          ok: true as const,
          data: { orderId: input.orderId, trackingCode: input.trackingCode.trim() },
        }
      : { ok: false as const, code: outcome.code, message: outcome.message };
  });
  if (result.ok) {
    revalidatePath('/admin/orders');
    revalidatePath(`/admin/orders/${input.orderId}/slip`);
  }
  return result;
}

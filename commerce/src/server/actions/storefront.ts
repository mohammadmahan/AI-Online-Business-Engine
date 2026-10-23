'use server';

import { revalidatePath } from 'next/cache';

import type {
  CartAvailabilityLine,
  CheckoutDraft,
  OrderRefused,
  PlaceOrderResult,
} from '@/contracts/storefront';

import { DB_NOT_CONFIGURED_MESSAGE, getRepository } from '../db-context';
import { getPaymentGateway } from '../payments/gateway-runtime';
import {
  checkAvailability,
  placeCheckoutOrder,
  type CheckoutLineInput,
} from '../services/checkout';

/**
 * D-172 §3.2–§3.4 — the storefront's two server actions.
 *
 * Both are reached from `'use client'` modules, which is why they live under
 * `@/server/actions/*`: that path is the ONE sanctioned crossing of the
 * client/server boundary (enforced by `src/__tests__/boundary.test.ts`). They
 * import the repository through `db-context`, which is why no browser bundle can
 * ever pull `pg` in.
 *
 * The environment gate is applied FIRST and by hand rather than through
 * `withRepository`, because a refused order must be able to say
 * `EMPTY_CART`/`STOCK_INSUFFICIENT`/`COUPON_INVALID` — a wider vocabulary than
 * the admin's action-failure codes. The repository's own unexpected-error
 * handling is inside `placeCheckoutOrder`, which reports the driver by name and
 * code only (D-114/D-124).
 */

export type AvailabilityCheckResult =
  | { ok: true; lines: CartAvailabilityLine[] }
  | OrderRefused;

/** §3.3 — pre-flight: "can this cart still be bought?" (not authoritative). */
export async function checkCartAvailabilityAction(
  lines: CheckoutLineInput[],
): Promise<AvailabilityCheckResult> {
  const repository = getRepository();
  if (repository === null) {
    return { ok: false, code: 'DB_NOT_CONFIGURED', message: DB_NOT_CONFIGURED_MESSAGE };
  }
  return checkAvailability(repository, lines);
}

/**
 * §3.4 — submits the order. The response carries the persisted order id, the
 * server-computed totals and the gateway's answer; a customer is only ever told
 * what actually happened (AC-8).
 *
 * §6.1 — the gateway is the REAL adapter, resolved at call time from the
 * environment (`getPaymentGateway`). Two answers are possible on an order that
 * was written:
 *
 *   - `UNAVAILABLE` with a `redirectUrl` — ZarinPal issued an authority and the
 *     order row now carries it; the FORM sends the browser to the gateway. No
 *     payment reference is written, because nothing has been charged;
 *   - `UNAVAILABLE` with no URL — the deployment is not configured (no merchant
 *     id / callback URL), so the order is `PENDING` and the customer is told the
 *     payment step is not connected. Fail-closed, exactly as the mock was.
 *
 * Marking the order paid is NOT this action's job: only the verified browser
 * return (`/api/payments/zarinpal/callback`) may do that.
 */
export async function placeOrderAction(draft: CheckoutDraft): Promise<PlaceOrderResult> {
  const repository = getRepository();
  if (repository === null) {
    return { ok: false, code: 'DB_NOT_CONFIGURED', message: DB_NOT_CONFIGURED_MESSAGE };
  }

  const outcome = await placeCheckoutOrder(repository, getPaymentGateway(), draft);
  if (outcome.ok) {
    // The merchant panel reads orders per request, but revalidating keeps the
    // panel's cached segments honest if one is ever added.
    revalidatePath('/admin');
    revalidatePath('/admin/orders');
  }
  return outcome;
}

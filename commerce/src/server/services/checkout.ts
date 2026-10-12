import type {
  CartAvailabilityLine,
  CheckoutDraft,
  OrderRefused,
  PlaceOrderResult,
} from '@/contracts/storefront';
import { quantityProblem } from '@/lib/checkout-rules';
import { shippingAmountFor } from '@/lib/shipping';
import {
  issuesToMessage,
  normalizeCouponCode,
  validateCheckoutCustomer,
} from '@/lib/validation';

import type { PaymentGateway } from '../payments/gateway';
import type { CommerceRepository, PlaceOrderWriteResult } from '../repository';

/**
 * D-172 §3.3/§3.4 — checkout, in two steps.
 *
 * STEP 1, `checkAvailability` — the optimistic pre-flight. It answers per line
 * whether the requested quantity is on hand so the drawer can warn BEFORE the
 * customer submits. It is deliberately NOT authoritative: stock can move between
 * the check and the write, and this call runs outside any transaction. It exists
 * to make a refusal likely-but-early, never to make the write path safe.
 *
 * STEP 2, `placeCheckoutOrder` — the authoritative write. Everything that costs
 * money is resolved from the SSOT inside the repository's transaction (unit
 * prices at D-024, coupon eligibility with an atomic usage counter, shipping
 * amount, totals), so the browser's numbers are treated as DISPLAY ONLY. Format
 * validation runs here so a malformed submission is refused before touching the
 * database, and the repository's refusal codes pass through unchanged.
 *
 * Payment (§3.4): after the order exists as `PENDING`, the gateway adapter is
 * asked to authorise the total. The shipped adapter cannot charge — its default
 * answer is `UNAVAILABLE` — so the customer is told the payment step is not
 * connected and the order stays `PENDING` (AC-8: a status is never faked). A
 * reference is recorded only when a gateway actually issued one, and even then
 * the order status is not moved: marking an order paid belongs to Phase 6.1,
 * where the provider and its callback exist.
 */

export interface CheckoutLineInput {
  variantId: string;
  quantity: number;
}

export function emptyCartRefusal(): OrderRefused {
  return { ok: false, code: 'EMPTY_CART', message: 'سبد خرید خالی است.' };
}

function validationRefusal(message: string, field: string): OrderRefused {
  return { ok: false, code: 'VALIDATION_ERROR', message, field };
}

/**
 * Normalises the client's cart lines into the shape the repository prices.
 *
 * Duplicated variant ids are REFUSED rather than merged: silently summing two
 * lines could push a quantity past the per-line ceiling and would hide a client
 * bug behind a different total. A malformed or oversized quantity is refused
 * with the quantity rule's own Persian message.
 */
export function normalizeCheckoutLines(
  lines: CheckoutLineInput[],
): { ok: true; items: CheckoutLineInput[] } | OrderRefused {
  if (!Array.isArray(lines) || lines.length === 0) {
    return emptyCartRefusal();
  }

  const items: CheckoutLineInput[] = [];
  const seen = new Set<string>();

  for (const line of lines) {
    const variantId = typeof line?.variantId === 'string' ? line.variantId.trim() : '';
    if (variantId.length === 0) {
      return validationRefusal('شناسهٔ گونه در سبد خرید معتبر نیست.', 'lines');
    }
    if (seen.has(variantId)) {
      return validationRefusal('یک گونه در سبد خرید دو بار تکرار شده است.', 'lines');
    }
    const problem = quantityProblem(line.quantity);
    if (problem) {
      return validationRefusal(problem, 'quantity');
    }
    seen.add(variantId);
    items.push({ variantId, quantity: line.quantity });
  }

  return { ok: true, items };
}

/** §3.3 — pre-flight stock/price check. Returns one line per requested item. */
export async function checkAvailability(
  repo: CommerceRepository,
  lines: CheckoutLineInput[],
): Promise<{ ok: true; lines: CartAvailabilityLine[] } | OrderRefused> {
  const normalized = normalizeCheckoutLines(lines);
  if (!normalized.ok) {
    return normalized;
  }
  return { ok: true, lines: await repo.listVariantAvailability(normalized.items) };
}

export async function placeCheckoutOrder(
  repo: CommerceRepository,
  gateway: PaymentGateway,
  draft: CheckoutDraft,
): Promise<PlaceOrderResult> {
  const normalized = normalizeCheckoutLines(draft.lines);
  if (!normalized.ok) {
    return normalized;
  }

  const customerValidation = validateCheckoutCustomer({
    fullName: draft.customer?.fullName,
    phoneNumber: draft.customer?.phoneNumber,
    address: draft.customer?.address,
    postalCode: draft.customer?.postalCode,
  });
  if (!customerValidation.ok) {
    const [first] = customerValidation.issues;
    return validationRefusal(
      issuesToMessage(customerValidation.issues),
      first?.field ?? 'customer',
    );
  }

  const shippingMethodId = typeof draft.shippingMethodId === 'string' ? draft.shippingMethodId : '';
  if (shippingAmountFor(shippingMethodId) === null) {
    return {
      ok: false,
      code: 'SHIPPING_UNKNOWN',
      message: 'روش ارسال انتخابی معتبر نیست.',
      field: 'shippingMethodId',
    };
  }

  const couponCode = draft.couponCode ? normalizeCouponCode(draft.couponCode) : null;

  let written: PlaceOrderWriteResult;
  try {
    written = await repo.placeOrder({
      customer: {
        fullName: draft.customer.fullName,
        phoneNumber: draft.customer.phoneNumber,
        address: draft.customer.address,
        postalCode: draft.customer.postalCode,
      },
      // The delivery address is the address the customer typed for this order;
      // the stored customer profile is never overwritten by it.
      shippingAddress: draft.customer.address,
      shippingMethodId,
      items: normalized.items,
      couponCode,
      paymentRefId: null,
    });
  } catch (error) {
    // The driver's message can echo a connection string (D-114/D-124), so it is
    // reported by name and code only, exactly as `db-context` does.
    const name = error instanceof Error ? error.name : 'UnknownError';
    const code =
      typeof error === 'object' && error !== null && 'code' in error
        ? String((error as { code: unknown }).code)
        : 'n/a';
    console.error('[commerce] placeOrder failed', { name, code });
    return {
      ok: false,
      code: 'UNEXPECTED',
      message: 'ثبت سفارش با خطای غیرمنتظره روبه‌رو شد. هیچ سفارشی ثبت نشد.',
    };
  }

  if (!written.ok) {
    return written;
  }

  const payment = await gateway.authorize({
    orderId: written.orderId,
    amount: written.totals.total,
    description: `سفارش ${written.orderId}`,
  });

  if (payment.status === 'AUTHORIZED' && payment.reference !== null) {
    await repo.setOrderPaymentRef(written.orderId, payment.reference);
  }

  return {
    ok: true,
    orderId: written.orderId,
    totals: written.totals,
    payment,
    couponApplied: written.couponApplied,
    status: 'PENDING',
  };
}

import type { OrderStatus } from '@/db/schema';

import { DB_NOT_CONFIGURED_MESSAGE, getRepository } from '../db-context';
import type { PaymentGateway } from '../payments/gateway';
import { getPaymentGateway } from '../payments/gateway-runtime';
import { ZARINPAL_PROVIDER } from '../payments/zarinpal';
import type { CommerceRepository, PaymentAuthorizationRecord } from '../repository';
import { applyPaymentCallback } from './payment-webhook';

/**
 * D-172 §6.1 — ZarinPal's BROWSER RETURN, processed.
 *
 * ZarinPal sends the customer's browser back with a plain
 * `GET ?Authority=...&Status=OK|NOK`. That request is NOT a signed webhook: it
 * carries no HMAC, so `POST /api/webhooks/payment` cannot accept it and this
 * route must not pretend otherwise. What it CAN do is turn the query string into
 * a claim that is authenticated the way this provider allows — by asking the
 * provider itself (`verifyCallback`) — and then hand the claim to the SAME
 * order-side pipeline the webhook uses (`applyPaymentCallback`). There is no
 * second write path here: one transition service, one audit vocabulary, one
 * idempotency boundary.
 *
 * The refusal order is the pipeline's, cheapest and most authoritative first:
 *
 *   1. an authority at all     → without `Authority` there is nothing to verify;
 *   2. `Status === OK`         → `NOK` (or a missing/unknown value) is the
 *                                provider saying the customer did not pay: no
 *                                verify call, no order read, no write. A cancel
 *                                is information, not an error;
 *   3. a known authorisation   → resolved through the DURABLE store (the order
 *                                row, G-1). A miss covers both "never issued"
 *                                and "issued by another provider" — a callback
 *                                may only move an order through the provider it
 *                                was recorded for;
 *   4. verified by the provider→ `AUTHORIZED` is the ONLY outcome that may move
 *                                an order; a decline or an unreachable provider
 *                                leaves it `PENDING` and the customer can retry;
 *   5. applied idempotently    → `PAID` through `transitionOrder`; a refresh
 *                                finds the order already `PAID` and writes
 *                                nothing (no second audit row).
 *
 * The response is JSON, like every other route in this track's API surface. The
 * customer's browser is the client, so the body is written to be readable as a
 * status: `ok`, `orderId`, `status`, `duplicate`, and a Persian `message`.
 */

export type ZarinPalCallbackRefusalCode =
  | 'AUTHORITY_MISSING'
  | 'UNKNOWN_AUTHORITY'
  | 'DB_NOT_CONFIGURED'
  | 'STORE_UNAVAILABLE'
  | 'VERIFY_UNAVAILABLE'
  | 'VERIFICATION_FAILED'
  | 'ORDER_NOT_FOUND'
  | 'ILLEGAL_TRANSITION'
  | 'ILLEGAL_STATE'
  | 'VALIDATION_ERROR'
  | 'UNEXPECTED';

export type ZarinPalCallbackOutcome =
  | { ok: true; orderId: string; status: OrderStatus; duplicate: boolean; message: string }
  | {
      ok: false;
      /** `PAYMENT_NOT_COMPLETED` is the customer's cancel, not an endpoint error. */
      code: ZarinPalCallbackRefusalCode | 'PAYMENT_NOT_COMPLETED';
      message: string;
    };

/**
 * The handler's dependencies, injected so the whole return path is exercisable
 * offline. Production passes neither: the repository comes from `getRepository`
 * and the gateway from `getPaymentGateway` — the same pair the checkout uses.
 */
export interface ZarinPalCallbackDeps {
  getRepository?: () => CommerceRepository | null;
  gateway?: PaymentGateway;
}

/** Every code a refusal may carry; the union is the handler's whole vocabulary. */
type ZarinPalCallbackCode = Exclude<ZarinPalCallbackOutcome, { ok: true }>['code'];

function httpStatusFor(code: ZarinPalCallbackCode): number {
  switch (code) {
    case 'AUTHORITY_MISSING':
    case 'VALIDATION_ERROR':
      return 400;
    case 'UNKNOWN_AUTHORITY':
    case 'ORDER_NOT_FOUND':
      return 404;
    case 'DB_NOT_CONFIGURED':
    case 'STORE_UNAVAILABLE':
    case 'VERIFY_UNAVAILABLE':
      return 503;
    case 'VERIFICATION_FAILED':
      return 402;
    case 'ILLEGAL_TRANSITION':
    case 'ILLEGAL_STATE':
      return 409;
    case 'UNEXPECTED':
      return 500;
    case 'PAYMENT_NOT_COMPLETED':
    default:
      return 200;
  }
}

function jsonResponse(status: number, body: ZarinPalCallbackOutcome): Response {
  // A payment return is never cacheable and never shared — by any cache.
  return Response.json(body, {
    status,
    headers: { 'cache-control': 'no-store' },
  });
}

function refuse(code: ZarinPalCallbackCode, message: string): Response {
  return jsonResponse(httpStatusFor(code), { ok: false, code, message });
}

/**
 * The pipeline. Returns a `Response` because that is what a route handler owes
 * the runtime; the route itself is a three-line shim, so this function IS the
 * endpoint as far as behaviour is concerned.
 */
export async function handleZarinPalCallback(
  request: Request,
  deps: ZarinPalCallbackDeps = {},
): Promise<Response> {
  const url = new URL(request.url);
  const authority = (url.searchParams.get('Authority') ?? '').trim();
  const status = (url.searchParams.get('Status') ?? '').trim().toUpperCase();

  if (authority.length === 0) {
    return refuse(
      'AUTHORITY_MISSING',
      'بازگشت درگاه بدون شناسهٔ پرداخت (Authority) دریافت شد؛ هیچ سفارشی بررسی یا تغییر نکرد.',
    );
  }

  // NOT OK: the provider has told us the customer did not complete the payment
  // (an abandoned page answers `NOK`). Nothing is verified and nothing is
  // written — an unpaid order is a fact to report, not a failure to repair.
  if (status !== 'OK') {
    return jsonResponse(httpStatusFor('PAYMENT_NOT_COMPLETED'), {
      ok: false,
      code: 'PAYMENT_NOT_COMPLETED',
      message:
        'پرداخت کامل نشد یا لغو شد. هیچ مبلغی دریافت نشده و سفارش در وضعیت «در انتظار پرداخت» باقی مانده است؛ در صورت تمایل می‌توانید دوباره تلاش کنید.',
    });
  }

  const repository = (deps.getRepository ?? getRepository)();
  if (repository === null) {
    return refuse('DB_NOT_CONFIGURED', DB_NOT_CONFIGURED_MESSAGE);
  }

  // THE DURABLE LOOKUP — the same store the adapter writes at request time. It
  // answers two questions at once: WHICH order this authority belongs to (the
  // adapter's verify call needs only the authority; this route needs the order)
  // and WHETHER this deployment ever issued it. A read that FAILS is a 503 the
  // customer can retry; only a read that SUCCEEDS and finds nothing refuses.
  let record: PaymentAuthorizationRecord | null;
  try {
    record = await repository.findPaymentAuthorization(ZARINPAL_PROVIDER, authority);
  } catch {
    return refuse(
      'STORE_UNAVAILABLE',
      'خواندن اطلاعات پرداخت از پایگاهِ دادهٔ مرجع انجام نشد؛ سفارش تغییر نکرد و بازکردن دوبارهٔ این نشانی ممکن است.',
    );
  }

  if (record === null) {
    // Never issued here, or issued by a different provider: both are "not ours
    // to verify", and verifying anyway would ask ZarinPal about an amount this
    // order never requested.
    return refuse(
      'UNKNOWN_AUTHORITY',
      'این شناسهٔ پرداخت برای هیچ سفارشی در این فروشگاه ثبت نشده است؛ پرداخت تأیید نشد و سفارش تغییر نکرد.',
    );
  }

  const gateway = deps.gateway ?? getPaymentGateway();

  let attempt;
  try {
    attempt = await gateway.verifyCallback({ reference: authority });
  } catch {
    // The adapter answers this itself; the guard exists so an adapter that
    // throws can never turn a payment return into an unhandled 500.
    return refuse(
      'VERIFY_UNAVAILABLE',
      'ارتباط با درگاه زرین‌پال برای تأیید پرداخت برقرار نشد؛ سفارش تغییر نکرد و تأیید دوباره ممکن است.',
    );
  }

  if (attempt.status !== 'AUTHORIZED') {
    return refuse(
      attempt.status === 'UNAVAILABLE' ? 'VERIFY_UNAVAILABLE' : 'VERIFICATION_FAILED',
      // The adapter's own Persian explanation, never a raw provider payload.
      attempt.message,
    );
  }

  // THE ONE WRITE PATH. `applyPaymentCallback` owns the lifecycle map, the audit
  // row, the reference write and the replay boundary — the same function the
  // signed webhook calls. A refresh of this URL reaches the "already PAID"
  // branch and writes nothing.
  const applied = await applyPaymentCallback(repository, {
    orderId: record.orderId,
    status: 'PAID',
    reference: attempt.reference,
    metadata: { provider: ZARINPAL_PROVIDER, authority, verification: attempt.code },
  });

  if (!applied.ok) {
    return refuse(applied.code, applied.message);
  }

  return jsonResponse(200, {
    ok: true,
    orderId: applied.orderId,
    status: applied.status,
    duplicate: applied.duplicate,
    message: applied.duplicate
      ? 'این پرداخت پیش‌تر ثبت شده بود؛ سفارش دوباره تغییر نکرد.'
      : attempt.message,
  });
}

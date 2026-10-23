import type { OrderStatus } from '@/db/schema';

import { DB_NOT_CONFIGURED_MESSAGE, getRepository } from '../db-context';
import {
  WEBHOOK_SIGNATURE_HEADER,
  verifyWebhookSignature,
  webhookSecret,
} from '../payments/webhook-signature';
import type { CommerceRepository } from '../repository';
import { transitionOrder } from './orders';

/**
 * D-172 Phase 4 transition / §6.1 — the ASYNC payment callback, processed.
 *
 * This is the seam a gateway will call when it decides by itself: the customer
 * returns from a redirect or the provider confirms hours later. It exists now,
 * before any provider is selected (G-4 / decision 10), because the ORDER write
 * path must not need rewriting when one is chosen — what Phase 6.1 replaces is
 * the signature scheme and the provider's payload, not this pipeline.
 *
 * The pipeline refuses in a fixed order, cheapest and most authoritative first,
 * and every stage either refuses or is impossible to half-apply:
 *
 *   1. seam configured      → a deployment with no secret answers 503, never
 *                             "accept anyway" (there is no unverified mode);
 *   2. authentic            → HMAC over the RAW body, constant-time compare
 *                             (`webhook-signature.ts`);
 *   3. bounded              → a body larger than a callback can legitimately be
 *                             is refused before it is parsed;
 *   4. well-formed          → JSON, then a payload whose fields are actually the
 *                             ones this pipeline uses;
 *   5. connected            → no canonical connection is a refusal;
 *   6. known order, legal move, IDEMPOTENT
 *                           → the transition runs through the SAME service the
 *                             merchant panel uses, so the lifecycle map, the
 *                             stock restock and the audit row are the ones
 *                             already governed; a REPLAY is answered as a
 *                             success with `duplicate: true` and writes nothing.
 *
 * What it deliberately does NOT do: hold a credential, verify a provider's
 * proprietary scheme, send SMS, or move an order to a status a callback has no
 * business asserting. A callback may only claim `PAID` (money arrived) or
 * `CANCELLED` (the attempt was abandoned) — `PROCESSING` and `SHIPPED` are
 * merchant acts about a parcel, and answering them here would let a provider
 * drive fulfilment.
 *
 * The idempotency boundary is the ORDER, not the request: the same callback
 * delivered twice finds the order already in the target status, and the answer
 * is "already processed" (`200`) rather than a second transition. That is also
 * why no event-id ledger exists yet — an order cannot reach the same status
 * twice (enforced again by `order_status_history`'s unique index), so a replay
 * is detectable from the order itself, without a second source of truth that
 * would need its own retention policy.
 */

/** A callback larger than this is not a callback. Refused before parsing. */
export const MAX_WEBHOOK_BODY_BYTES = 64 * 1024;

/** The statuses a payment callback may assert; everything else is the merchant's. */
export const WEBHOOK_ASSERTABLE_STATUSES: OrderStatus[] = ['PAID', 'CANCELLED'];

export interface PaymentWebhookPayload {
  /** The provider's own id for this delivery, recorded for investigation. */
  eventId?: string;
  orderId: string;
  status: 'PAID' | 'CANCELLED';
  /** The provider reference; recorded when the callback actually carries one. */
  reference?: string | null;
}

export type PaymentWebhookRefusalCode =
  | 'WEBHOOK_NOT_CONFIGURED'
  | 'SIGNATURE_MISSING'
  | 'SIGNATURE_MALFORMED'
  | 'SIGNATURE_MISMATCH'
  | 'BODY_TOO_LARGE'
  | 'INVALID_JSON'
  | 'INVALID_EVENT'
  | 'DB_NOT_CONFIGURED'
  | 'ORDER_NOT_FOUND'
  /*
   * The lifecycle service's own refusal codes pass through UNMAPPED: a callback
   * that wants an illegal edge should be told exactly what the merchant panel is
   * told, by the same code, so there is one vocabulary for one rule.
   */
  | 'ILLEGAL_TRANSITION'
  | 'ILLEGAL_STATE'
  | 'VALIDATION_ERROR'
  | 'UNEXPECTED';

export type PaymentWebhookOutcome =
  | {
      ok: true;
      orderId: string;
      status: OrderStatus;
      /** `true` when this delivery changed nothing because it was a replay. */
      duplicate: boolean;
    }
  | { ok: false; code: PaymentWebhookRefusalCode; message: string };

/**
 * The handler's only dependencies, injected so the pipeline can be exercised
 * end-to-end offline: the repository is the in-memory double, the secret a
 * literal. Production passes neither, and then both come from the environment
 * (`getRepository`, `webhookSecret`) — the same fail-closed sources the rest of
 * the track uses.
 */
export interface PaymentWebhookDeps {
  getRepository?: () => CommerceRepository | null;
  secret?: string | null;
}

function httpStatusFor(code: PaymentWebhookRefusalCode): number {
  switch (code) {
    case 'WEBHOOK_NOT_CONFIGURED':
    case 'DB_NOT_CONFIGURED':
      return 503;
    case 'SIGNATURE_MISSING':
    case 'SIGNATURE_MALFORMED':
    case 'SIGNATURE_MISMATCH':
      return 401;
    case 'ORDER_NOT_FOUND':
      return 404;
    case 'ILLEGAL_TRANSITION':
    case 'ILLEGAL_STATE':
      return 409;
    case 'BODY_TOO_LARGE':
      return 413;
    case 'INVALID_JSON':
    case 'INVALID_EVENT':
    case 'VALIDATION_ERROR':
      return 400;
    case 'UNEXPECTED':
    default:
      return 500;
  }
}

function jsonResponse(status: number, body: PaymentWebhookOutcome): Response {
  // A webhook answer is never cacheable and never shared.
  return Response.json(body, {
    status,
    headers: { 'cache-control': 'no-store' },
  });
}

function refuse(code: PaymentWebhookRefusalCode, message: string): Response {
  return jsonResponse(httpStatusFor(code), { ok: false, code, message });
}

/** Field-by-field validation; every refusal names what was wrong, never a value. */
export function parsePaymentWebhookPayload(
  value: unknown,
): { ok: true; payload: PaymentWebhookPayload } | { ok: false; message: string } {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    return { ok: false, message: 'بدنهٔ بازگشت باید یک شیء JSON باشد.' };
  }
  const record = value as Record<string, unknown>;

  const orderId = typeof record.orderId === 'string' ? record.orderId.trim() : '';
  if (orderId.length === 0) {
    return { ok: false, message: 'شناسهٔ سفارش در بازگشت وجود ندارد.' };
  }

  const status = typeof record.status === 'string' ? record.status.toUpperCase() : '';
  if (!WEBHOOK_ASSERTABLE_STATUSES.includes(status as OrderStatus)) {
    return {
      ok: false,
      message: 'وضعیت اعلام‌شده در بازگشت مجاز نیست؛ فقط PAID یا CANCELLED پذیرفته می‌شود.',
    };
  }

  const reference =
    typeof record.reference === 'string' && record.reference.trim().length > 0
      ? record.reference.trim()
      : null;
  const eventId =
    typeof record.eventId === 'string' && record.eventId.trim().length > 0
      ? record.eventId.trim()
      : undefined;

  return {
    ok: true,
    payload: {
      orderId,
      status: status as 'PAID' | 'CANCELLED',
      reference,
      ...(eventId === undefined ? {} : { eventId }),
    },
  };
}

/**
 * The ORDER-SIDE half of a payment callback, shared by every entry point that
 * may assert one.
 *
 * Two routes reach this today: the signed `POST /api/webhooks/payment` and a
 * redirect-based provider's browser return (`payment-callback.ts`). They differ
 * only in how the claim is AUTHENTICATED — an HMAC over the body versus a
 * `verify` call to the provider — so neither may own a copy of the transition,
 * the idempotency boundary or the reference write. This function is that single
 * copy: one lifecycle, one audit row, one answer for a replay.
 *
 * It returns a RESULT, not a `Response`: each route maps it onto its own
 * transport, and a refusal keeps the lifecycle service's own vocabulary
 * (`NOT_FOUND` becomes `ORDER_NOT_FOUND`, because the caller is specific about
 * WHAT was not found — that is what a provider operator reads).
 */
export interface PaymentCallbackVerdict {
  orderId: string;
  status: 'PAID' | 'CANCELLED';
  /** The provider reference, or `null` when the callback carried none. */
  reference: string | null;
  /** Extra facts for the audit row (e.g. a provider event id). Never PII. */
  metadata?: Record<string, unknown>;
}

export type PaymentCallbackResult =
  | { ok: true; orderId: string; status: OrderStatus; duplicate: boolean }
  | {
      ok: false;
      code:
        | 'ORDER_NOT_FOUND'
        | 'ILLEGAL_TRANSITION'
        | 'ILLEGAL_STATE'
        | 'VALIDATION_ERROR'
        | 'UNEXPECTED';
      message: string;
    };

export async function applyPaymentCallback(
  repository: CommerceRepository,
  verdict: PaymentCallbackVerdict,
): Promise<PaymentCallbackResult> {
  const { orderId, status, reference } = verdict;

  try {
    const order = await repository.getOrderDetail(orderId);
    if (!order) {
      return { ok: false, code: 'ORDER_NOT_FOUND', message: 'سفارشی با این شناسه ثبت نشده است.' };
    }

    // THE IDEMPOTENCY BOUNDARY. The order is already where this callback wants
    // it, so the transition it asks for has already happened: answer success
    // (a provider that sees an error will retry, and retrying forever is how a
    // webhook endpoint becomes an outage) and write NOTHING — no second audit
    // row, no second restock. The one exception is a reference the first attempt
    // did not manage to store, and only into a NULL field.
    if (order.status === status) {
      if (status === 'PAID' && reference !== null && order.paymentRefId === null) {
        await repository.setOrderPaymentRef(orderId, reference);
      }
      return { ok: true, orderId, status: order.status, duplicate: true };
    }

    const outcome = await transitionOrder(repository, orderId, status, {
      source: 'PAYMENT_CALLBACK',
      // The trail is the one place these ids live today: the reference is also
      // recorded as an order attribute, but the audit row keeps it even if that
      // write is lost, and the event id is only ever useful next to a timestamp.
      metadata: { ...(verdict.metadata ?? {}), reference },
    });

    if (!outcome.ok) {
      return {
        ok: false,
        code: outcome.code === 'NOT_FOUND' ? 'ORDER_NOT_FOUND' : outcome.code,
        message: outcome.message,
      };
    }

    // Recorded only for a move that actually happened: a refused callback writes
    // nothing at all. The window between the two writes is covered by the audit
    // metadata above, and a replay completes it.
    if (status === 'PAID' && reference !== null) {
      await repository.setOrderPaymentRef(orderId, reference);
    }

    return { ok: true, orderId, status, duplicate: false };
  } catch (error) {
    // Reported by NAME and CODE only: a driver message can echo a connection
    // string (D-114/D-124).
    const name = error instanceof Error ? error.name : 'UnknownError';
    const code =
      typeof error === 'object' && error !== null && 'code' in error
        ? String((error as { code: unknown }).code)
        : 'n/a';
    console.error('[commerce] payment callback failed', { name, code });
    return { ok: false, code: 'UNEXPECTED', message: 'پردازش بازگشت با خطای غیرمنتظره روبه‌رو شد.' };
  }
}

/**
 * The pipeline. Returns a `Response` because that is what a route handler owes
 * the runtime; the route itself is a three-line shim, so this function IS the
 * endpoint as far as behaviour is concerned.
 */
export async function handlePaymentWebhook(
  request: Request,
  deps: PaymentWebhookDeps = {},
): Promise<Response> {
  const rawBody = await request.text();

  const verdict = verifyWebhookSignature({
    rawBody,
    header: request.headers.get(WEBHOOK_SIGNATURE_HEADER),
    secret: deps.secret === undefined ? webhookSecret() : deps.secret,
  });
  if (!verdict.ok) {
    return refuse(verdict.code, verdict.message);
  }

  // Measured AFTER authentication: an unsigned caller learns nothing about our
  // limits, and an authentic one is the only party whose body we read.
  if (Buffer.byteLength(rawBody, 'utf8') > MAX_WEBHOOK_BODY_BYTES) {
    return refuse('BODY_TOO_LARGE', 'بدنهٔ بازگشت بیش از حد بزرگ است.');
  }

  let decoded: unknown;
  try {
    decoded = JSON.parse(rawBody);
  } catch {
    return refuse('INVALID_JSON', 'بدنهٔ بازگشت JSON معتبر نیست.');
  }

  const parsed = parsePaymentWebhookPayload(decoded);
  if (!parsed.ok) {
    return refuse('INVALID_EVENT', parsed.message);
  }
  const { orderId, status } = parsed.payload;
  const reference = parsed.payload.reference ?? null;

  const repository = (deps.getRepository ?? getRepository)();
  if (repository === null) {
    return refuse('DB_NOT_CONFIGURED', DB_NOT_CONFIGURED_MESSAGE);
  }

  const result = await applyPaymentCallback(repository, {
    orderId,
    status,
    reference,
    metadata:
      parsed.payload.eventId === undefined ? undefined : { eventId: parsed.payload.eventId },
  });

  if (!result.ok) {
    return refuse(result.code, result.message);
  }

  return jsonResponse(200, {
    ok: true,
    orderId: result.orderId,
    status: result.status,
    duplicate: result.duplicate,
  });
}

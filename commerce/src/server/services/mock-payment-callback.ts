import type { OrderStatus } from '@/db/schema';

import { DB_NOT_CONFIGURED_MESSAGE, getRepository } from '../db-context';
import type { PaymentGateway } from '../payments/gateway';
import {
  getPaymentGateway,
  isProductionConfig,
  MOCK_PAYMENT_MODE,
  PAYMENT_MODE_ENV,
} from '../payments/gateway-runtime';
import type { CommerceRepository } from '../repository';
import { applyPaymentCallback } from './payment-webhook';

/**
 * D-172 §6.1 (demo) — the OFFLINE mock return, `GET /api/payments/mock/callback`.
 *
 * Why it exists: `PAYMENT_MODE=mock` lets a checkout authorise without any
 * external call, but only a verified callback may move an order to `PAID`
 * (AC-8). Without this route a demo always stops at `PENDING`, which proves
 * nothing about the confirmation path. With it, the mock exercises the SAME
 * pipeline a real provider return uses.
 *
 * The guard is the mode itself, read AT REQUEST TIME:
 *
 *   - `PAYMENT_MODE` is not exactly `mock`, or the build is production →
 *     `404 MOCK_MODE_DISABLED`. A 404, not a 503: a surface that does not exist
 *     outside a demo must not advertise itself as misconfigured. Nothing is
 *     read, verified or written. Production is refused because this track's
 *     production means live money behind the D-139 gate (AC-8, §6.3 NO-GO).
 *   - enabled → the reference must be `MOCK-<orderId>`, which is the only shape
 *     the mock ever issues. An arbitrary reference is refused before the
 *     database is touched.
 *
 * What it does NOT do: invent a transition. Every write goes through
 * `applyPaymentCallback`, the same function the signed webhook and the ZarinPal
 * browser return call — one lifecycle map, one audit vocabulary, one replay
 * boundary. A refresh finds the order `PAID` and writes nothing.
 *
 * Residual risks, stated rather than hidden: while the mode is `mock`, anyone
 * who knows an order id can confirm it, and no money moves. That is why the mode
 * is a demo setting, why the reference keeps its `MOCK-` prefix in the database,
 * and why an unrecognised `PAYMENT_MODE` falls through to ZarinPal instead of
 * here (`gateway-runtime.ts`).
 */

export const MOCK_PROVIDER = 'mock';
export const MOCK_REFERENCE_PREFIX = 'MOCK-';

/**
 * The demo mode is on only for the exact value `mock` (trimmed, folded) AND
 * only outside a production build. Both halves are required: the mode is the
 * opt-in, production is the standing refusal (D-139, AC-8, §6.3 NO-GO).
 */
export function mockModeEnabled(
  env: Readonly<Record<string, string | undefined>> = process.env,
): boolean {
  if (isProductionConfig(env)) {
    return false;
  }
  return (env[PAYMENT_MODE_ENV] ?? '').trim().toLowerCase() === MOCK_PAYMENT_MODE;
}

/**
 * The order a mock reference belongs to, or `null`.
 *
 * The prefix is stripped exactly once: an order id that itself begins with
 * `MOCK-` round-trips correctly, because the adapter always prepends a single
 * prefix to the real id.
 */
export function orderIdFromMockReference(reference: string): string | null {
  const trimmed = reference.trim();
  if (!trimmed.startsWith(MOCK_REFERENCE_PREFIX)) {
    return null;
  }
  const orderId = trimmed.slice(MOCK_REFERENCE_PREFIX.length).trim();
  return orderId.length === 0 ? null : orderId;
}

export type MockCallbackRefusalCode =
  | 'MOCK_MODE_DISABLED'
  | 'REFERENCE_MISSING'
  | 'REFERENCE_INVALID'
  | 'DB_NOT_CONFIGURED'
  | 'VERIFY_UNAVAILABLE'
  | 'VERIFICATION_FAILED'
  | 'ORDER_NOT_FOUND'
  | 'ILLEGAL_TRANSITION'
  | 'ILLEGAL_STATE'
  | 'VALIDATION_ERROR'
  | 'UNEXPECTED';

export type MockCallbackOutcome =
  | { ok: true; orderId: string; status: OrderStatus; duplicate: boolean; message: string }
  | { ok: false; code: MockCallbackRefusalCode; message: string };

function httpStatusFor(code: MockCallbackRefusalCode): number {
  switch (code) {
    case 'MOCK_MODE_DISABLED':
    case 'ORDER_NOT_FOUND':
      return 404;
    case 'REFERENCE_MISSING':
    case 'REFERENCE_INVALID':
      return 400;
    case 'DB_NOT_CONFIGURED':
    case 'VERIFY_UNAVAILABLE':
      return 503;
    case 'VERIFICATION_FAILED':
      return 402;
    case 'ILLEGAL_TRANSITION':
    case 'ILLEGAL_STATE':
      return 409;
    case 'UNEXPECTED':
    default:
      return 500;
  }
}

function jsonResponse(status: number, body: MockCallbackOutcome): Response {
  // A payment return is never cacheable and never shared — by any cache.
  return Response.json(body, {
    status,
    headers: { 'cache-control': 'no-store' },
  });
}

function refuse(code: MockCallbackRefusalCode, message: string): Response {
  return jsonResponse(httpStatusFor(code), { ok: false, code, message });
}

/**
 * The handler's dependencies, injected so the whole return path is exercisable
 * offline. Production passes none of them: the mode comes from the environment,
 * the repository from `getRepository`, and the gateway from
 * `getPaymentGateway` — the same selector the checkout uses.
 */
export interface MockCallbackDeps {
  env?: Readonly<Record<string, string | undefined>>;
  getRepository?: () => CommerceRepository | null;
  gateway?: PaymentGateway;
}

export async function handleMockCallback(
  request: Request,
  deps: MockCallbackDeps = {},
): Promise<Response> {
  // FIRST, before the URL is even read: a demo surface outside demo mode does
  // not exist, and must not reveal why.
  if (!mockModeEnabled(deps.env ?? process.env)) {
    return refuse('MOCK_MODE_DISABLED', 'این نشانی در این استقرار فعال نیست.');
  }

  const url = new URL(request.url);
  const raw = (url.searchParams.get('reference') ?? '').trim();
  if (raw.length === 0) {
    return refuse(
      'REFERENCE_MISSING',
      'بازگشت آزمایشی بدون شناسهٔ پرداخت دریافت شد؛ هیچ سفارشی بررسی یا تغییر نکرد.',
    );
  }

  const orderId = orderIdFromMockReference(raw);
  if (orderId === null) {
    return refuse(
      'REFERENCE_INVALID',
      'شناسهٔ پرداخت آزمایشی معتبر نیست (قالب مورد انتظار: MOCK-<orderId>); هیچ سفارشی تغییر نکرد.',
    );
  }

  const repository = (deps.getRepository ?? getRepository)();
  if (repository === null) {
    return refuse('DB_NOT_CONFIGURED', DB_NOT_CONFIGURED_MESSAGE);
  }

  const gateway = deps.gateway ?? getPaymentGateway();

  let attempt;
  try {
    attempt = await gateway.verifyCallback({ reference: raw });
  } catch {
    // The mock answers this itself; the guard exists so an adapter that throws
    // can never turn a demo return into an unhandled 500.
    return refuse(
      'VERIFY_UNAVAILABLE',
      'تأیید پرداخت آزمایشی انجام نشد؛ سفارش تغییر نکرد.',
    );
  }

  if (attempt.status !== 'AUTHORIZED') {
    return refuse(
      attempt.status === 'UNAVAILABLE' ? 'VERIFY_UNAVAILABLE' : 'VERIFICATION_FAILED',
      attempt.message,
    );
  }

  // THE ONE WRITE PATH — the same function the signed webhook and the ZarinPal
  // return call. The stored reference is the `MOCK-` one this route validated,
  // never the mock's doubled echo, so the row names the order it paid.
  const applied = await applyPaymentCallback(repository, {
    orderId,
    status: 'PAID',
    reference: raw,
    metadata: { provider: MOCK_PROVIDER, verification: attempt.code },
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
      ? 'این پرداخت آزمایشی پیش‌تر ثبت شده بود؛ سفارش دوباره تغییر نکرد.'
      : 'پرداخت آزمایشی تأیید شد؛ سفارش با وضعیت «پرداخت‌شده» ثبت شد.',
  });
}

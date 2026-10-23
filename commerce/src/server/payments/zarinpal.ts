import type { PaymentAttempt } from '@/contracts/storefront';

import type { PaymentAuthorizationStore } from './authority-store';
import type {
  PaymentAuthorizationRequest,
  PaymentCallbackPayload,
  PaymentGateway,
} from './gateway';

/**
 * D-172 §6.1 — the ZarinPal adapter, behind the EXISTING `PaymentGateway` seam.
 *
 * The owner selected ZarinPal as the primary payment provider (decision 10,
 * 2026-10-23). This module is the ADAPTER, not a second dispatch path: it
 * implements the same `authorize()` / `verifyCallback()` pair the mock already
 * implements, so the order write path, the cart and the callback route are
 * untouched. Swapping in Zibal or NextPay later means writing another object of
 * this shape, not editing this file or its callers.
 *
 * The one asymmetry worth stating out loud, because the status vocabulary has
 * no word for it: a ZarinPal payment REQUEST does not take money. It returns an
 * `authority` and a redirect URL, and the customer pays on the gateway's page.
 * Reporting `AUTHORIZED` here would be a lie — and a load-bearing one, because
 * `placeCheckoutOrder` persists `payment_ref_id` for an AUTHORIZED attempt, so
 * an unpaid order would be stamped with a provider reference before any money
 * arrived (AC-8: a status is never faked). `authorize()` therefore answers
 * `UNAVAILABLE` — this step charged nothing and the order stays `PENDING` —
 * while carrying `authority` and `redirectUrl` for the caller to act on.
 * `verifyCallback()` is the only path that can answer `AUTHORIZED`, and only
 * after ZarinPal confirms the payment.
 *
 * Offline by construction: every network effect goes through an injected
 * `ZarinPalTransport`, the default is `fetch`, and no test ever reaches it.
 * Nothing here reads the clock, logs, stores a card number or prints a
 * credential. The merchant id arrives from the environment at CALL time
 * (D-045) and never appears in a returned message (D-114/D-124).
 *
 * Stateless by construction: what the provider authorised (order, authority,
 * amount) is written to the injected `PaymentAuthorizationStore` — the order row
 * in PostgreSQL (G-1) — not remembered here. A callback therefore verifies in a
 * process that never issued it, which a process-local cache could not do. See
 * `authority-store.ts`.
 */

/** The merchant id ZarinPal issues. Owner-supplied; absent today (D-045). */
export const ZARINPAL_MERCHANT_ID_ENV = 'ZARINPAL_MERCHANT_ID';

/**
 * The absolute URL the CUSTOMER'S BROWSER is sent back to after paying.
 *
 * It is NOT the signed webhook: ZarinPal appends `?Authority=...&Status=OK|NOK`
 * and issues a plain `GET`, which the HMAC-guarded `POST /api/webhooks/payment`
 * cannot accept. The route behind this URL is the one that calls
 * `verifyCallback()` — and it therefore owns the same order transition the
 * webhook owns, rather than a second write path. See TODO §G2 for the wiring
 * that is still open.
 */
export const ZARINPAL_CALLBACK_URL_ENV = 'ZARINPAL_CALLBACK_URL';

/** `true` (default) talks to the sandbox host; `false` is production. */
export const ZARINPAL_SANDBOX_ENV = 'ZARINPAL_SANDBOX';

/** Request timeout. A payment request that hangs is a refusal, not a hang. */
export const ZARINPAL_TIMEOUT_MS = 15_000;

/**
 * Integer Toman (D-010) in, integer Rial out. ZarinPal's API speaks Rial and
 * this repository speaks Toman everywhere, so the conversion lives in exactly
 * one function and is asserted by a test rather than sprinkled at call sites.
 */
export const RIAL_PER_TOMAN = 10;

/**
 * The `payment_provider` value this adapter writes. It is the correlation key a
 * callback is resolved with, so it is a stable, provider-owned identifier and
 * never a deployment label (`zarinpal-sandbox` is a GATEWAY id, not this).
 */
export const ZARINPAL_PROVIDER = 'zarinpal';

export type ZarinPalRefusalCode =
  | 'ZARINPAL_NOT_CONFIGURED'
  | 'ZARINPAL_INVALID_AMOUNT'
  | 'ZARINPAL_INVALID_ORDER'
  | 'ZARINPAL_TRANSPORT_ERROR'
  | 'ZARINPAL_MALFORMED_RESPONSE'
  | 'ZARINPAL_REQUEST_REFUSED'
  | 'ZARINPAL_INVALID_AUTHORITY'
  | 'ZARINPAL_UNKNOWN_AUTHORITY'
  | 'ZARINPAL_STORE_ERROR'
  | 'ZARINPAL_VERIFY_REFUSED';

export interface ZarinPalConfig {
  /** `null` when the owner has not supplied one — every call then refuses. */
  merchantId: string | null;
  /** Absolute callback URL; `null` refuses for the same reason. */
  callbackUrl: string | null;
  /** Defaults to `true`: sandbox unless a deployment opts out explicitly. */
  sandbox: boolean;
}

const SANDBOX_BASE = 'https://sandbox.zarinpal.com';
const PRODUCTION_BASE = 'https://payment.zarinpal.com';

/**
 * Read the configuration at CALL time. An absent value is `null`, never a
 * placeholder: a fake merchant id would turn a configuration gap into a
 * provider error the operator has to decode.
 */
export function zarinpalConfigFromEnv(
  env: Record<string, string | undefined> = process.env,
): ZarinPalConfig {
  const merchantId = env[ZARINPAL_MERCHANT_ID_ENV]?.trim() ?? '';
  const callbackUrl = env[ZARINPAL_CALLBACK_URL_ENV]?.trim() ?? '';
  const sandbox = (env[ZARINPAL_SANDBOX_ENV]?.trim() ?? 'true').toLowerCase() !== 'false';

  return {
    merchantId: merchantId.length > 0 ? merchantId : null,
    callbackUrl: callbackUrl.length > 0 ? callbackUrl : null,
    sandbox,
  };
}

/** The three URLs this adapter needs, derived from one flag. */
export function zarinpalEndpoints(sandbox: boolean): {
  request: string;
  verify: string;
  startPay: string;
} {
  const base = sandbox ? SANDBOX_BASE : PRODUCTION_BASE;
  return {
    request: `${base}/pg/v4/payment/request.json`,
    verify: `${base}/pg/v4/payment/verify.json`,
    startPay: `${base}/pg/StartPay/`,
  };
}

export function tomanToRial(toman: number): number {
  return toman * RIAL_PER_TOMAN;
}

export interface ZarinPalHttpRequest {
  url: string;
  body: Record<string, unknown>;
}

export interface ZarinPalHttpResponse {
  status: number;
  /** Parsed JSON, or `null` when the body was not JSON at all. */
  body: unknown;
}

/** The only place a socket exists. Tests inject a fake and never call this. */
export type ZarinPalTransport = (request: ZarinPalHttpRequest) => Promise<ZarinPalHttpResponse>;

const fetchTransport: ZarinPalTransport = async ({ url, body }) => {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'content-type': 'application/json', accept: 'application/json' },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(ZARINPAL_TIMEOUT_MS),
  });

  let parsed: unknown = null;
  try {
    parsed = await response.json();
  } catch {
    parsed = null;
  }

  return { status: response.status, body: parsed };
};

interface Envelope {
  /** True when the body had the shape ZarinPal documents (data or errors). */
  valid: boolean;
  code: number | null;
  authority: string | null;
  refId: string | null;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

/**
 * ZarinPal answers `{ data: { code, authority | ref_id, message }, errors: … }`.
 * The envelope is narrowed field by field — an unexpected shape is a refusal,
 * never a defaulted success.
 */
function readEnvelope(body: unknown): Envelope {
  const root = asRecord(body);
  if (root === null) {
    return { valid: false, code: null, authority: null, refId: null };
  }

  const data = asRecord(root.data);
  const errors = root.errors;
  const hasErrors = errors !== undefined && errors !== null;
  if (data === null && !hasErrors) {
    return { valid: false, code: null, authority: null, refId: null };
  }

  const rawCode = data?.code;
  const code = typeof rawCode === 'number' ? rawCode : Number.NaN;
  const authority = typeof data?.authority === 'string' ? data.authority.trim() : '';
  const rawRef = data?.ref_id;
  const refId =
    typeof rawRef === 'string'
      ? rawRef.trim()
      : typeof rawRef === 'number' && Number.isFinite(rawRef)
        ? String(rawRef)
        : '';

  return {
    valid: true,
    code: Number.isFinite(code) ? code : null,
    authority: authority.length > 0 ? authority : null,
    refId: refId.length > 0 ? refId : null,
  };
}

function refuse(
  status: 'UNAVAILABLE' | 'DECLINED',
  code: ZarinPalRefusalCode,
  message: string,
): PaymentAttempt {
  return { status, code, message, reference: null };
}

function notConfigured(): PaymentAttempt {
  return refuse(
    'UNAVAILABLE',
    'ZARINPAL_NOT_CONFIGURED',
    'درگاه زرین‌پال هنوز تنظیم نشده است (شناسهٔ پذیرنده یا نشانی بازگشت موجود نیست)، بنابراین هیچ مبلغی از مشتری دریافت نمی‌شود و سفارش در انتظار پرداخت می‌ماند.',
  );
}

export interface ZarinPalGatewayOptions {
  config?: ZarinPalConfig;
  transport?: ZarinPalTransport;
  /**
   * Where an issued authority is persisted, REQUIRED.
   *
   * Not optional and never defaulted to an in-memory map: a process-local cache
   * survives neither a restart nor a second instance, and its failure mode is
   * silent — an order paid at the provider whose callback can never be verified
   * here. Compiling without a store is the guard.
   */
  store: PaymentAuthorizationStore;
}

/**
 * Build the adapter. No default export and no module-level environment read:
 * importing this file must never depend on a deployment's configuration.
 *
 * The adapter itself holds NO payment state. Every fact it needs at verify time
 * (which order, which amount) comes back from the injected store, which is what
 * makes a fresh process able to verify a callback it never issued.
 */
export function createZarinPalGateway(options: ZarinPalGatewayOptions): PaymentGateway {
  const config = options.config ?? zarinpalConfigFromEnv();
  const transport = options.transport ?? fetchTransport;
  const store = options.store;
  const endpoints = zarinpalEndpoints(config.sandbox);

  return {
    id: config.sandbox ? 'zarinpal-sandbox' : 'zarinpal',

    async authorize(request: PaymentAuthorizationRequest): Promise<PaymentAttempt> {
      if (!Number.isSafeInteger(request.amount) || request.amount <= 0) {
        return refuse(
          'DECLINED',
          'ZARINPAL_INVALID_AMOUNT',
          'مبلغ سفارش برای ارسال به درگاه معتبر نیست؛ پرداختی آغاز نشد.',
        );
      }
      if (request.orderId.trim().length === 0) {
        return refuse(
          'DECLINED',
          'ZARINPAL_INVALID_ORDER',
          'شناسهٔ سفارش برای ارسال به درگاه معتبر نیست؛ پرداختی آغاز نشد.',
        );
      }
      if (config.merchantId === null || config.callbackUrl === null) {
        return notConfigured();
      }

      const amountRial = tomanToRial(request.amount);
      let response: ZarinPalHttpResponse;
      try {
        response = await transport({
          url: endpoints.request,
          body: {
            merchant_id: config.merchantId,
            amount: amountRial,
            currency: 'IRR',
            callback_url: config.callbackUrl,
            description:
              request.description.trim().slice(0, 255) || `سفارش ${request.orderId}`,
          },
        });
      } catch {
        // Transport failures are Class-A by nature: nothing was charged, and
        // the caller may retry. Never rethrow into the order transaction.
        return refuse(
          'UNAVAILABLE',
          'ZARINPAL_TRANSPORT_ERROR',
          'ارتباط با درگاه زرین‌پال برقرار نشد؛ سفارش ثبت شده اما پرداخت‌نشده باقی می‌ماند.',
        );
      }

      const envelope = readEnvelope(response.body);
      if (!envelope.valid) {
        return refuse(
          'UNAVAILABLE',
          'ZARINPAL_MALFORMED_RESPONSE',
          'پاسخ درگاه زرین‌پال قابل خواندن نبود؛ سفارش ثبت شده اما پرداخت‌نشده باقی می‌ماند.',
        );
      }
      if (envelope.code !== 100 || envelope.authority === null) {
        return refuse(
          'DECLINED',
          'ZARINPAL_REQUEST_REFUSED',
          `درگاه زرین‌پال درخواست پرداخت را نپذیرفت (کد ${envelope.code ?? 'نامشخص'}). سفارش ثبت شده اما پرداخت‌نشده باقی می‌ماند.`,
        );
      }

      const authority = envelope.authority;

      // PERSIST BEFORE REDIRECT. The customer is about to leave this site and
      // pay at the provider; the only way this side can later learn WHICH ORDER
      // and WHICH AMOUNT that authority stands for is the record written here.
      // A store that cannot write is a refusal, not a warning: redirecting
      // anyway would let money arrive for a payment this deployment can never
      // verify.
      try {
        await store.save({
          orderId: request.orderId,
          provider: ZARINPAL_PROVIDER,
          authority,
          amount: request.amount,
        });
      } catch {
        return refuse(
          'UNAVAILABLE',
          'ZARINPAL_STORE_ERROR',
          'ثبت اطلاعات پرداخت در پایگاهِ دادهٔ مرجع انجام نشد؛ به صفحهٔ پرداخت هدایت نمی‌شوید و سفارش تغییر نکرد.',
        );
      }

      // Deliberately NOT `AUTHORIZED`: no money has moved, and the order path
      // persists a payment reference for an authorized attempt (see the module
      // docstring). The caller redirects, then waits for the callback.
      return {
        status: 'UNAVAILABLE',
        code: 'ZARINPAL_REDIRECT_REQUIRED',
        message:
          'برای پرداخت به صفحهٔ درگاه زرین‌پال هدایت می‌شوید. تا زمانی که بازگشت درگاه تأیید نشود، سفارش در انتظار پرداخت می‌ماند.',
        reference: null,
        authority,
        redirectUrl: `${endpoints.startPay}${encodeURIComponent(authority)}`,
      };
    },

    async verifyCallback(payload: PaymentCallbackPayload): Promise<PaymentAttempt> {
      const authority = (payload.reference ?? '').trim();
      if (authority.length === 0) {
        return refuse(
          'DECLINED',
          'ZARINPAL_INVALID_AUTHORITY',
          'بازگشت درگاه بدون شناسهٔ پرداخت (Authority) دریافت شد؛ پرداختی تأیید نشد.',
        );
      }

      // THE DURABLE LOOKUP. A fresh process (or another instance) has no memory
      // of issuing this authority, so the order and its amount come from the
      // store — PostgreSQL, through the repository. A read that FAILS is
      // `UNAVAILABLE` (the provider may retry); only a read that SUCCEEDS and
      // finds nothing is a refusal.
      let record: { orderId: string; provider: string; authority: string; amount: number } | null;
      try {
        record = await store.find(ZARINPAL_PROVIDER, authority);
      } catch {
        return refuse(
          'UNAVAILABLE',
          'ZARINPAL_STORE_ERROR',
          'خواندن اطلاعات پرداخت از پایگاهِ دادهٔ مرجع انجام نشد؛ سفارش تغییر نکرد و تأیید دوباره ممکن است.',
        );
      }

      if (record === null) {
        // No persisted amount means no safe way to call verify: ZarinPal
        // requires the amount, and guessing one would be a fabricated fact.
        return refuse(
          'DECLINED',
          'ZARINPAL_UNKNOWN_AUTHORITY',
          'این شناسهٔ پرداخت برای هیچ سفارشی در این فروشگاه ثبت نشده است؛ تأیید انجام نشد و سفارش تغییر نکرد.',
        );
      }
      if (config.merchantId === null) {
        return notConfigured();
      }

      // The stored amount is the one the request was made with, in Toman; the
      // provider is called in Rial through the same single conversion.
      if (!Number.isSafeInteger(record.amount) || record.amount <= 0) {
        return refuse(
          'DECLINED',
          'ZARINPAL_UNKNOWN_AUTHORITY',
          'مبلغ ثبت‌شده برای این شناسهٔ پرداخت معتبر نیست؛ تأیید انجام نشد و سفارش تغییر نکرد.',
        );
      }

      let response: ZarinPalHttpResponse;
      try {
        response = await transport({
          url: endpoints.verify,
          body: {
            merchant_id: config.merchantId,
            amount: tomanToRial(record.amount),
            authority,
          },
        });
      } catch {
        return refuse(
          'UNAVAILABLE',
          'ZARINPAL_TRANSPORT_ERROR',
          'ارتباط با درگاه زرین‌پال برای تأیید پرداخت برقرار نشد؛ سفارش تغییر نکرد و تأیید دوباره ممکن است.',
        );
      }

      const envelope = readEnvelope(response.body);
      if (!envelope.valid) {
        return refuse(
          'UNAVAILABLE',
          'ZARINPAL_MALFORMED_RESPONSE',
          'پاسخ تأیید درگاه زرین‌پال قابل خواندن نبود؛ سفارش تغییر نکرد.',
        );
      }

      // 100 = verified now, 101 = already verified by an earlier call. Both mean
      // the money arrived; treating 101 as a failure would make a client retry
      // forever, so it is recorded as the same successful outcome.
      //
      // No in-process verdict cache exists any more, and none is needed: the
      // provider itself answers 101 for a replay, so this adapter stays
      // stateless across restarts and instances. The order-level replay guard
      // (the unique `(order_id, to_status)` in `order_status_history`) is what
      // makes the downstream transition idempotent.
      if (envelope.code === 100 || envelope.code === 101) {
        return {
          status: 'AUTHORIZED',
          code: envelope.code === 100 ? 'ZARINPAL_VERIFIED' : 'ZARINPAL_ALREADY_VERIFIED',
          message:
            envelope.code === 100
              ? 'پرداخت با موفقیت تأیید شد.'
              : 'این پرداخت پیش‌تر تأیید شده بود؛ تأیید دوباره انجام نشد و سفارش یک‌بار به‌روزرسانی می‌شود.',
          // The provider reference (never a PAN, never the merchant id). For 101
          // without a ref_id the authority identifies the same payment.
          reference: envelope.refId ?? authority,
        };
      }

      return refuse(
        'DECLINED',
        'ZARINPAL_VERIFY_REFUSED',
        `درگاه زرین‌پال پرداخت را تأیید نکرد (کد ${envelope.code ?? 'نامشخص'}); سفارش تغییر نکرد.`,
      );
    },
  };
}

/**
 * The adapter the application would wire once the owner exports the merchant id
 * and callback URL. Deliberately NOT exported as a ready-made singleton: this
 * module must stay importable without a configured environment, and the default
 * wiring in `checkout.ts` still points at the fail-closed mock.
 *
 * The store is passed through unchanged and is REQUIRED — see
 * `ZarinPalGatewayOptions.store`.
 */
export function createZarinPalGatewayFromEnv(
  options: Omit<ZarinPalGatewayOptions, 'config'>,
): PaymentGateway {
  return createZarinPalGateway({ ...options, config: zarinpalConfigFromEnv() });
}

import { handleZarinPalCallback } from '@/server/services/payment-callback';

/**
 * D-172 §6.1 — the browser-return endpoint: `GET /api/payments/zarinpal/callback`.
 *
 * This file is a THREE-LINE SHIM, for the same reason `api/webhooks/payment` is:
 * everything that decides anything — the `Status` gate, the durable authority
 * lookup, the provider verify and the idempotent `PAID` transition — lives in
 * `@/server/services/payment-callback`, where it is exercised offline with an
 * injected repository and gateway. A route handler is awkward to test and easy
 * to grow logic into; keeping it this thin means the behaviour under test is the
 * behaviour that ships.
 *
 * `ZARINPAL_CALLBACK_URL` must point at this path, absolute
 * (`https://<host>/api/payments/zarinpal/callback`): ZarinPal appends
 * `?Authority=...&Status=OK|NOK` and redirects the CUSTOMER'S BROWSER here with a
 * plain GET. It is not the signed webhook and never was — see `.env.example`.
 *
 * `runtime = 'nodejs'` is explicit because the authority lookup uses the
 * PostgreSQL driver (no Edge equivalent), and the response is `no-store` because
 * a payment return must never be cached.
 */
export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function GET(request: Request): Promise<Response> {
  return handleZarinPalCallback(request);
}

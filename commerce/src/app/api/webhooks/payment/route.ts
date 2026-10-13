import { handlePaymentWebhook } from '@/server/services/payment-webhook';

/**
 * D-172 Phase 4 transition / §6.1 — the asynchronous payment/notification
 * callback endpoint: `POST /api/webhooks/payment`.
 *
 * This file is a THREE-LINE SHIM on purpose, and it is the only place in the
 * track that accepts a request without a session. Everything that decides
 * anything — the configuration gate, the HMAC check, the payload validation, the
 * idempotent transition and the audit row — lives in
 * `@/server/services/payment-webhook`, where it is unit-tested with an injected
 * repository and no HTTP at all. A route handler is awkward to test and easy to
 * grow logic into; keeping it this thin means the endpoint's behaviour is the
 * behaviour under test rather than a copy of it.
 *
 * `runtime = 'nodejs'` is explicit because the signature check uses `node:crypto`
 * (constant-time HMAC comparison has no Edge equivalent), and the provider
 * itself is still an OPEN owner decision (G-4 / decision 10) — no secret is
 * configured today, so the endpoint answers 503 and processes nothing. That is
 * the intended state until the owner selects a provider and exports
 * `COMMERCE_PAYMENT_WEBHOOK_SECRET`.
 */
export const runtime = 'nodejs';

export async function POST(request: Request): Promise<Response> {
  return handlePaymentWebhook(request);
}

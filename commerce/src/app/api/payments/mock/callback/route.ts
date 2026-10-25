import { handleMockCallback } from '@/server/services/mock-payment-callback';

/**
 * D-172 §6.1 (demo) — the OFFLINE browser return:
 * `GET /api/payments/mock/callback?reference=MOCK-<orderId>`.
 *
 * Selected only by `PAYMENT_MODE=mock`: outside that mode the service answers
 * `404 MOCK_MODE_DISABLED` before it reads the query string, so this route is
 * inert in any real deployment.
 *
 * Three lines, for the same reason the ZarinPal return is: every decision —
 * the mode guard, the reference shape, the verify and the idempotent `PAID`
 * transition through `applyPaymentCallback` — lives in
 * `@/server/services/mock-payment-callback`, where it is exercised offline.
 */
export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function GET(request: Request): Promise<Response> {
  return handleMockCallback(request);
}

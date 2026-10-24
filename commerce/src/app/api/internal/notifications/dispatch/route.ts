import { handleNotificationDispatchRequest } from '@/server/notifications/dispatch-endpoint';

/**
 * D-172 §6.2 — `POST /api/internal/notifications/dispatch`.
 *
 * A THREE-LINE SHIM, like `/api/webhooks/payment` and `/healthz`: the verdict
 * logic lives in `@/server/notifications/dispatch-endpoint`, where it is tested
 * with an injected repository, channel, clock and token and no database at all.
 * The route exists only to bind that logic to HTTP.
 *
 * `dynamic = 'force-dynamic'` is required, not cosmetic: the handler reads
 * `NOTIFICATIONS_DISPATCH_TOKEN`, `SMS_LIVE_ENABLED` and `DATABASE_URL` at CALL
 * time, so a build-time prerender would freeze an answer about an environment
 * that does not exist yet (and the build has none of those variables).
 *
 * `runtime = 'nodejs'` is required because the queue speaks SQL through `pg`.
 *
 * No `GET` export: a delivery run is a state change, so Next answers any other
 * method with 405 and nothing can be triggered by a link.
 */
export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function POST(request: Request): Promise<Response> {
  return handleNotificationDispatchRequest(request);
}

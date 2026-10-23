import { handleHealthRequest } from '@/server/services/health';

/**
 * §6.3 G-2 — `GET /healthz`, the readiness endpoint the container probes.
 *
 * A THREE-LINE SHIM, like `/api/webhooks/payment`: the verdict logic lives in
 * `@/server/services/health`, where it is unit-tested with an injected probe and
 * no database at all. The route exists only to bind that logic to HTTP.
 *
 * `dynamic = 'force-dynamic'` is required, not cosmetic: a route handler whose
 * dependencies Next could treat as static would be prerendered at build time —
 * the build has no `DATABASE_URL`, so the prerendered answer would be a
 * permanent `503 db_unconfigured` baked into the image. Forcing dynamic means
 * every probe re-asks the live environment.
 *
 * `runtime = 'nodejs'` is required because the probe uses the `pg` pool; there is
 * no Edge equivalent and no reason to want one.
 *
 * No `POST`/`PUT`/`DELETE` export: any other method is answered by Next with
 * 405, so the surface stays a read-only liveness fact and nothing can be driven
 * through it.
 */
export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function GET(): Promise<Response> {
  return handleHealthRequest();
}

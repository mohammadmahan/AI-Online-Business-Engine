/**
 * Container health endpoint (D-171 container contract, spec §5 option A).
 *
 * The container healthcheck and the deployment probe need a signal that does
 * not depend on rendering a dashboard page, and the read-only surface must not
 * disclose anything while answering: no version, no build id, no probe state,
 * no internals — a fixed, minimal body and `no-store` so nothing caches the
 * answer. It reads no environment, so it is also a truthful liveness signal:
 * if the process can serve HTTP at all, this route answers.
 *
 * Deliberately dependency-free: the Web `Response` global is used directly
 * rather than `NextResponse`, so the route pulls no framework helper into the
 * runtime path.
 */
export const dynamic = 'force-dynamic';

export function GET(): Response {
  return Response.json(
    { status: 'ok' },
    { headers: { 'Cache-Control': 'no-store' } },
  );
}

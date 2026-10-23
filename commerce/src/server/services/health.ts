import { isDatabaseConfigured, probeCanonicalDatabase } from '../db-context';

/**
 * §6.3 G-2 — the readiness contract behind `GET /healthz`.
 *
 * WHY THIS IS NOT A DEPENDENCY-FREE PING. The control plane's spec offers a
 * dependency-free health endpoint because that surface holds no credential at
 * all. This surface is the opposite: every read and write goes through the
 * canonical PostgreSQL instance, so an endpoint that answers "ok" while the
 * database is absent would report a container healthy that can serve nothing —
 * a false pass, which is exactly what D-171 §2.2 forbids ("absence of
 * configuration is never a pass"). The probe therefore asks the question that
 * actually decides whether this process can do its job: does the connection I
 * would use answer `SELECT 1`?
 *
 * FAIL-CLOSED, IN THREE STEPS:
 *   1. no `DATABASE_URL` (absent or blank) → 503 `db_unconfigured`, no probe;
 *   2. configured but the probe throws or exceeds its budget → 503
 *      `db_unreachable` (the driver's message is swallowed, never echoed —
 *      it can carry a connection string, D-114/D-124);
 *   3. only a probe that resolves yields 200.
 *
 * DISCLOSURE POSTURE. The body carries a status and, when unhealthy, one coarse
 * reason code. No version, no host, no driver error, no timing data, no
 * environment names — the reasons are a closed union, so a future edit cannot
 * widen what leaks without failing the type check.
 *
 * CACHING. `no-store` on every answer: a health verdict that a proxy may cache
 * is worse than no health endpoint, because it keeps lying after the database
 * has recovered (or died).
 */

export const HEALTH_PATH = '/healthz';
export const HEALTH_CACHE_CONTROL = 'no-store';

/** The only two ways this surface can be unable to serve. */
export type HealthReason = 'db_unconfigured' | 'db_unreachable';

export interface HealthVerdict {
  status: 'ok' | 'unavailable';
  httpStatus: 200 | 503;
  reason?: HealthReason;
}

/** The two impure edges, injected so the verdict logic is testable offline. */
export interface HealthDependencies {
  configured: () => boolean;
  probe: () => Promise<void>;
}

export async function evaluateHealth(deps: HealthDependencies): Promise<HealthVerdict> {
  if (!deps.configured()) {
    return { status: 'unavailable', httpStatus: 503, reason: 'db_unconfigured' };
  }

  try {
    await deps.probe();
    return { status: 'ok', httpStatus: 200 };
  } catch {
    // Intentionally swallowed: any throw (auth, DNS, timeout, pool exhaustion)
    // is the same operational fact from outside — the database did not answer.
    return { status: 'unavailable', httpStatus: 503, reason: 'db_unreachable' };
  }
}

export function healthResponse(verdict: HealthVerdict): Response {
  const body =
    verdict.status === 'ok'
      ? { status: 'ok' as const }
      : { status: 'unavailable' as const, reason: verdict.reason };

  return new Response(JSON.stringify(body), {
    status: verdict.httpStatus,
    headers: {
      'content-type': 'application/json; charset=utf-8',
      'cache-control': HEALTH_CACHE_CONTROL,
    },
  });
}

/** The route handler's whole body — wired to the real environment and pool. */
export async function handleHealthRequest(): Promise<Response> {
  return healthResponse(
    await evaluateHealth({
      configured: isDatabaseConfigured,
      probe: probeCanonicalDatabase,
    }),
  );
}

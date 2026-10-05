/**
 * Live read-only probe source (D-171 §5.5, Phase 27.7).
 *
 * ── Boundaries ──────────────────────────────────────────────────────────────
 * This module runs on the SERVER ONLY (Node runtime). It performs one GET per
 * configured endpoint with a bounded timeout, records the latency and a SHA-256
 * digest of the raw payload, and never sends or exposes a credential: tokens
 * are read from `CP_PROBE_TOKENS` and used solely as an Authorization header.
 * The seam hands the UI plain `ProbeResult` objects — no tokens, no URLs with
 * secrets, no network handles.
 *
 * ── Fail-closed mapping ─────────────────────────────────────────────────────
 * A probe never fabricates a healthy state. The response is resolved by
 * `resolveResponseVerdict()` (see `@/lib/probes/verdict`):
 *   - 2xx                 → the canonical verdict when the body carries one,
 *                            otherwise HEALTHY, or DEGRADED when slower than
 *                            the threshold;
 *   - 3xx (not followed)  → DEGRADED: the redirect target was never assessed;
 *   - 4xx/5xx             → the verdict the sidecar declared (`DOWN` or
 *                            `UNKNOWN`) when its canonical body parses;
 *                            otherwise UNKNOWN — the status code alone is not
 *                            a verdict and is never coerced into `DOWN`;
 *   - timeout / network / invalid endpoint / missing configuration
 *                        → UNKNOWN with the Persian reason.
 * A `DOWN` or `UNKNOWN` surface carries no CPU/memory figures and no queue
 * readings even when the payload contained them, and the shared build-time
 * guard re-checks that rule.
 *
 * ── Configuration ───────────────────────────────────────────────────────────
 *   CP_PROBE_ENDPOINTS   JSON object: { "postgres": "http://127.0.0.1:9540/healthz", ... }
 *   CP_PROBE_TOKENS      JSON object: { "n8n": "<bearer token>", ... }
 *   CP_PROBE_TIMEOUT_MS  per-probe timeout, default 2500, capped at 10000
 *   CP_PROBE_SLOW_MS     latency above which a 2xx is DEGRADED, default 1000
 * A malformed endpoints/tokens document refuses EVERY probe (config error, all
 * UNKNOWN); one malformed URL affects only its own surface.
 *
 * ── Queue readings ──────────────────────────────────────────────────────────
 * When the Redis or n8n endpoint answers 2xx and its JSON payload exposes the
 * documented fields, the queue monitor renders those readings; otherwise the
 * readings stay `null` → UNKNOWN. Missing fields are never defaulted to zero.
 */

import { createHash } from 'node:crypto';

import { connection } from 'next/server';

import {
  assertTelemetryConsistency,
  CONTAINER_META,
  evaluatingGates,
  GATED_ACTIONS,
  N8N_CRITICAL_WAITING,
  N8N_WARN_WAITING,
  n8nPressure,
  REDIS_CRITICAL_DEPTH,
  REDIS_WARN_DEPTH,
  redisPressure,
  summarizeTelemetry,
} from '@/lib/mock/telemetry-data';
import {
  extractReadings,
  PROBE_CONTAINER_IDS,
  readProbeConfig,
  resolveResponseVerdict,
} from '@/lib/probes/verdict';
import type { N8nReadings, ProbeConfig, RedisReadings } from '@/lib/probes/verdict';
import type { ProbeResult } from '@/types/live-probes';
import type {
  ContainerHealth,
  ContainerId,
  ContainerIncident,
  ContainerMetrics,
  N8nQueueTelemetry,
  QueueTelemetry,
  RedisQueueTelemetry,
  TelemetryDataSource,
  TelemetrySnapshot,
} from '@/types/telemetry';

/** What one probe attempt observed, plus whatever the payload safely exposed. */
interface ProbeOutcome {
  result: ProbeResult;
  /** True when a request was actually attempted (affects `lastProbeUtc`). */
  attempted: boolean;
  metrics: ContainerMetrics | null;
  redis: RedisReadings | null;
  n8n: N8nReadings | null;
}

function sha256(text: string): string {
  return createHash('sha256').update(text, 'utf8').digest('hex');
}

function nowIso(): string {
  return new Date().toISOString();
}

function unassessed(id: ContainerId, reasonFa: string): ProbeOutcome {
  return {
    result: {
      containerId: id,
      status: 'UNKNOWN',
      latencyMs: null,
      payloadDigest: null,
      probedAtUtc: nowIso(),
      reasonFa,
      endpointLabel: null,
      verdictSource: 'transport',
    },
    attempted: false,
    metrics: null,
    redis: null,
    n8n: null,
  };
}

/** One read-only probe with a bounded timeout; never throws. */
async function probeEndpoint(
  id: ContainerId,
  config: ProbeConfig,
): Promise<ProbeOutcome> {
  if (config.configErrorFa !== null) return unassessed(id, config.configErrorFa);

  const spec = config.endpoints[id];
  if (spec === undefined) {
    return unassessed(
      id,
      'endpointی برای این سرویس در CP_PROBE_ENDPOINTS تنظیم نشده است؛ وضعیت نامشخص می‌ماند (fail-closed).',
    );
  }
  if ('invalidReasonFa' in spec) {
    return unassessed(id, `${spec.invalidReasonFa} وضعیت نامشخص می‌ماند (fail-closed).`);
  }

  const token = config.tokens[id];
  const startedAt = performance.now();
  try {
    const response = await fetch(spec.url, {
      method: 'GET',
      headers: {
        accept: 'application/json, text/plain;q=0.9, */*;q=0.8',
        ...(token !== undefined ? { authorization: `Bearer ${token}` } : {}),
      },
      redirect: 'manual',
      cache: 'no-store',
      signal: AbortSignal.timeout(config.timeoutMs),
    });
    const body = await response.text();
    const latencyMs = Math.max(0, Math.round(performance.now() - startedAt));
    const digest = sha256(body);
    const probedAtUtc = nowIso();
    const base = { containerId: id, latencyMs, payloadDigest: digest, probedAtUtc, endpointLabel: spec.label };

    // Verdict fidelity: a canonical sidecar body is honored exactly (DOWN vs
    // UNKNOWN); without one the status code is not coerced into a verdict.
    const verdict = resolveResponseVerdict(response.status, body, id, config.slowMs, latencyMs);
    // Readings cross only for a measured status on a 2xx response; a DOWN or
    // UNKNOWN payload is discarded whole, metric fields included.
    const readings = extractReadings(response.ok, verdict.status, body);
    return {
      result: { ...base, ...verdict },
      attempted: true,
      metrics: readings.metrics,
      redis: readings.redis,
      n8n: readings.n8n,
    };
  } catch (error) {
    const timedOut =
      error instanceof Error && (error.name === 'TimeoutError' || error.name === 'AbortError');
    return {
      result: {
        containerId: id,
        status: 'UNKNOWN',
        latencyMs: null,
        payloadDigest: null,
        probedAtUtc: nowIso(),
        reasonFa: timedOut
          ? `کاوش در ${config.timeoutMs} میلی‌ثانیه پاسخ نگرفت؛ وضعیت نامشخص می‌ماند (fail-closed).`
          : 'اتصال به endpoint کاوش برقرار نشد؛ وضعیت نامشخص می‌ماند (fail-closed).',
        endpointLabel: spec.label,
        verdictSource: 'transport',
      },
      attempted: true,
      metrics: null,
      redis: null,
      n8n: null,
    };
  }
}

function incidentFromOutcome(outcome: ProbeOutcome, status: ContainerHealth['status']): ContainerIncident | null {
  if (status !== 'DEGRADED' && status !== 'DOWN') return null;
  return {
    severity: status,
    noteFa: outcome.result.reasonFa,
    raisedAtUtc: outcome.result.probedAtUtc,
  };
}

/** Build one container row from its probe outcome, fail-closed by construction. */
function containerFromProbe(id: ContainerId, outcome: ProbeOutcome, provenance: TelemetrySnapshot['provenance']): ContainerHealth {
  const meta = CONTAINER_META[id];
  const status = outcome.result.status;
  const measured = status === 'HEALTHY' || status === 'DEGRADED';
  const metrics = measured ? outcome.metrics : null;
  return {
    id,
    titleFa: meta.titleFa,
    containerRef: meta.containerRef,
    status,
    metricsState: metrics !== null ? 'LIVE' : 'UNAVAILABLE',
    metrics,
    portMapping: meta.portMapping,
    // Only a real attempt updates the last-probe instant; a missing endpoint is
    // not a probe that happened.
    lastProbeUtc: outcome.attempted ? outcome.result.probedAtUtc : null,
    detailFa: meta.detailFa,
    incident: incidentFromOutcome(outcome, status),
    probe: outcome.result,
    provenance,
  };
}

function queuesFromOutcomes(redisOutcome: ProbeOutcome, n8nOutcome: ProbeOutcome, config: ProbeConfig): QueueTelemetry {
  const redisAssessed =
    redisOutcome.result.status === 'HEALTHY' || redisOutcome.result.status === 'DEGRADED';
  const redisReadings = redisAssessed ? redisOutcome.redis : null;
  const redisDepth = redisReadings?.depth ?? null;
  const redis: RedisQueueTelemetry = {
    depth: redisDepth,
    throughputPerMin: redisReadings?.throughputPerMin ?? null,
    pressure: redisPressure(redisDepth, REDIS_WARN_DEPTH, REDIS_CRITICAL_DEPTH),
    warnAtDepth: REDIS_WARN_DEPTH,
    criticalAtDepth: REDIS_CRITICAL_DEPTH,
  };

  const n8nAssessed =
    n8nOutcome.result.status === 'HEALTHY' || n8nOutcome.result.status === 'DEGRADED';
  const n8nReadings = n8nAssessed ? n8nOutcome.n8n : null;
  const n8n: N8nQueueTelemetry = {
    active: n8nReadings?.active ?? null,
    waiting: n8nReadings?.waiting ?? null,
    failedLast24h: n8nReadings?.failedLast24h ?? null,
    pressure: n8nPressure(n8nReadings?.waiting ?? null, n8nReadings?.failedLast24h ?? null),
    warnAtWaiting: N8N_WARN_WAITING,
    criticalAtWaiting: N8N_CRITICAL_WAITING,
  };

  return {
    redis,
    n8n,
    probe: {
      redis: config.endpoints.redis !== undefined ? redisOutcome.result : null,
      n8n: config.endpoints.n8n !== undefined ? n8nOutcome.result : null,
    },
  };
}

/** Run every configured probe and assemble a guarded read-only snapshot. */
export async function loadLiveTelemetry(): Promise<TelemetrySnapshot> {
  // Live readings must never be frozen into a static prerender: awaiting the
  // connection opts the route into request-time rendering, and no probe is
  // executed during a build.
  await connection();

  const config = readProbeConfig();
  const outcomes = await Promise.all(PROBE_CONTAINER_IDS.map((id) => probeEndpoint(id, config)));
  const byId = Object.fromEntries(
    outcomes.map((outcome) => [outcome.result.containerId, outcome]),
  ) as Record<ContainerId, ProbeOutcome>;

  const assessed = outcomes.some((outcome) => outcome.result.status !== 'UNKNOWN');
  const provenance: TelemetrySnapshot['provenance'] = assessed ? 'live' : 'unavailable';
  const containers = PROBE_CONTAINER_IDS.map((id) => containerFromProbe(id, byId[id], provenance));
  const queues = queuesFromOutcomes(byId.redis, byId.n8n, config);
  const gates = evaluatingGates();

  const snapshot: TelemetrySnapshot = {
    generatedAt: nowIso(),
    scenario: 'live',
    provenance,
    sourceMode: 'LIVE',
    containers,
    gates,
    queues,
    actions: GATED_ACTIONS,
    writeGate: { tokenPresent: false, signaturePathConnected: false },
    summary: summarizeTelemetry(containers, gates, queues),
  };

  // The live seam is guarded by the same build-time invariants as the mock.
  return assertTelemetryConsistency(snapshot);
}

/** The live implementation of the swap seam. */
export function createLiveTelemetrySource(): TelemetryDataSource {
  return {
    async load(): Promise<TelemetrySnapshot> {
      return loadLiveTelemetry();
    },
  };
}

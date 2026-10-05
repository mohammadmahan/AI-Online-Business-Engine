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
 * A probe never fabricates a healthy state:
 *   - 2xx                → HEALTHY, or DEGRADED when slower than the threshold;
 *   - 3xx (not followed) → DEGRADED: the redirect target was never assessed;
 *   - 4xx/5xx            → DOWN: the endpoint answered with a failure;
 *   - timeout / network / invalid endpoint / missing configuration
 *                        → UNKNOWN with the Persian reason.
 * A `DOWN` or `UNKNOWN` surface carries no CPU/memory figures even when the
 * payload contained them, and the shared build-time guard re-checks that rule.
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

const CONTAINER_IDS: ContainerId[] = ['postgres', 'n8n', 'redis', 'dokploy', 'walrus'];

const DEFAULT_TIMEOUT_MS = 2_500;
const MAX_TIMEOUT_MS = 10_000;
const DEFAULT_SLOW_MS = 1_000;

/** One parsed endpoint: a usable URL or the Persian reason it is unusable. */
type EndpointSpec = { url: URL; label: string } | { invalidReasonFa: string };

interface ProbeConfig {
  endpoints: Partial<Record<ContainerId, EndpointSpec>>;
  tokens: Partial<Record<ContainerId, string>>;
  timeoutMs: number;
  slowMs: number;
  /** Non-null when the configuration itself is unusable (refuses every probe). */
  configErrorFa: string | null;
}

/** What one probe attempt observed, plus whatever the payload safely exposed. */
interface ProbeOutcome {
  result: ProbeResult;
  /** True when a request was actually attempted (affects `lastProbeUtc`). */
  attempted: boolean;
  metrics: ContainerMetrics | null;
  redis: { depth: number; throughputPerMin: number } | null;
  n8n: { active: number; waiting: number; failedLast24h: number } | null;
}

function sha256(text: string): string {
  return createHash('sha256').update(text, 'utf8').digest('hex');
}

function readPositiveInt(raw: string | undefined, fallback: number, max: number): number {
  if (raw === undefined || raw.trim() === '') return fallback;
  const value = Number.parseInt(raw, 10);
  if (!Number.isFinite(value) || value <= 0) return fallback;
  return Math.min(value, max);
}

function parseJsonObject(
  raw: string | undefined,
  label: string,
): { value: Record<string, unknown> | null; error: string | null } {
  if (raw === undefined || raw.trim() === '') return { value: {}, error: null };
  try {
    const parsed: unknown = JSON.parse(raw);
    if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return { value: null, error: `${label} must be a JSON object` };
    }
    return { value: parsed as Record<string, unknown>, error: null };
  } catch {
    return { value: null, error: `${label} is not valid JSON` };
  }
}

/** Read the server-side probe configuration; never throws. */
export function readProbeConfig(): ProbeConfig {
  const timeoutMs = readPositiveInt(process.env.CP_PROBE_TIMEOUT_MS, DEFAULT_TIMEOUT_MS, MAX_TIMEOUT_MS);
  const slowMs = readPositiveInt(process.env.CP_PROBE_SLOW_MS, DEFAULT_SLOW_MS, MAX_TIMEOUT_MS);

  const endpointsRaw = parseJsonObject(process.env.CP_PROBE_ENDPOINTS, 'CP_PROBE_ENDPOINTS');
  const tokensRaw = parseJsonObject(process.env.CP_PROBE_TOKENS, 'CP_PROBE_TOKENS');

  const errors: string[] = [];
  if (endpointsRaw.error) errors.push(endpointsRaw.error);
  if (tokensRaw.error) errors.push(tokensRaw.error);

  if (errors.length > 0) {
    return {
      endpoints: {},
      tokens: {},
      timeoutMs,
      slowMs,
      configErrorFa:
        `پیکربندی کاوش زنده نامعتبر است (${errors.join('؛ ')})؛` +
        ' برای حفظ رفتار fail-closed هیچ کاوشی اجرا نشد و همه‌ی سطوح نامشخص می‌مانند.',
    };
  }

  const endpoints: Partial<Record<ContainerId, EndpointSpec>> = {};
  for (const id of CONTAINER_IDS) {
    const raw = endpointsRaw.value?.[id];
    if (raw === undefined || raw === null || raw === '') continue;
    if (typeof raw !== 'string') {
      endpoints[id] = { invalidReasonFa: 'نشانی کاوش باید یک رشته‌ی http(s) باشد.' };
      continue;
    }
    let url: URL;
    try {
      url = new URL(raw);
    } catch {
      endpoints[id] = { invalidReasonFa: 'نشانی کاوش قابل تجزیه نیست.' };
      continue;
    }
    if (url.protocol !== 'http:' && url.protocol !== 'https:') {
      endpoints[id] = { invalidReasonFa: 'نشانی کاوش باید http یا https باشد.' };
      continue;
    }
    // host + pathname only: a token embedded in a query string is never echoed.
    endpoints[id] = { url, label: `${url.host}${url.pathname}` };
  }

  const tokens: Partial<Record<ContainerId, string>> = {};
  for (const id of CONTAINER_IDS) {
    const raw = tokensRaw.value?.[id];
    if (typeof raw === 'string' && raw !== '') tokens[id] = raw;
  }

  return { endpoints, tokens, timeoutMs, slowMs, configErrorFa: null };
}

function nowIso(): string {
  return new Date().toISOString();
}

function parseJson(text: string): Record<string, unknown> | null {
  try {
    const parsed: unknown = JSON.parse(text);
    if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) return null;
    return parsed as Record<string, unknown>;
  } catch {
    return null;
  }
}

function asNonNegativeInt(value: unknown): number | null {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0 ? value : null;
}

/** Extract CPU/memory figures, but only when every field is present and sane. */
function parseMetrics(payload: Record<string, unknown> | null): ContainerMetrics | null {
  if (payload === null) return null;
  const nested = payload.metrics;
  const source =
    nested !== null && typeof nested === 'object' && !Array.isArray(nested)
      ? (nested as Record<string, unknown>)
      : payload;
  const cpuPercent = source.cpuPercent;
  const memoryUsedMb = source.memoryUsedMb;
  const memoryLimitMb = source.memoryLimitMb;
  const uptimeSeconds = source.uptimeSeconds;
  if (
    typeof cpuPercent !== 'number' ||
    typeof memoryUsedMb !== 'number' ||
    typeof memoryLimitMb !== 'number' ||
    typeof uptimeSeconds !== 'number'
  ) {
    return null;
  }
  if (cpuPercent < 0 || cpuPercent > 100) return null;
  if (memoryUsedMb <= 0 || memoryLimitMb <= 0 || memoryUsedMb > memoryLimitMb) return null;
  if (!Number.isInteger(uptimeSeconds) || uptimeSeconds < 0) return null;
  return { cpuPercent, memoryUsedMb, memoryLimitMb, uptimeSeconds };
}

function parseRedisReadings(
  payload: Record<string, unknown> | null,
): { depth: number; throughputPerMin: number } | null {
  if (payload === null) return null;
  const depth = asNonNegativeInt(payload.depth);
  const throughputPerMin = asNonNegativeInt(payload.throughputPerMin);
  if (depth === null || throughputPerMin === null) return null;
  return { depth, throughputPerMin };
}

function parseN8nReadings(
  payload: Record<string, unknown> | null,
): { active: number; waiting: number; failedLast24h: number } | null {
  if (payload === null) return null;
  const active = asNonNegativeInt(payload.active);
  const waiting = asNonNegativeInt(payload.waiting);
  const failedLast24h = asNonNegativeInt(payload.failedLast24h);
  if (active === null || waiting === null || failedLast24h === null) return null;
  return { active, waiting, failedLast24h };
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

    if (response.ok) {
      const payload = parseJson(body);
      const slow = latencyMs >= config.slowMs;
      const status = slow ? 'DEGRADED' : 'HEALTHY';
      return {
        result: {
          ...base,
          status,
          reasonFa: slow
            ? `پاسخ کاوش کند بود (${latencyMs} ms ≥ آستانه‌ی ${config.slowMs} ms)؛ وضعیت تنزل‌یافته اعلام می‌شود.`
            : '',
        },
        attempted: true,
        metrics: parseMetrics(payload),
        redis: parseRedisReadings(payload),
        n8n: parseN8nReadings(payload),
      };
    }

    if (response.status >= 300 && response.status < 400) {
      return {
        result: {
          ...base,
          status: 'DEGRADED',
          reasonFa: `endpoint با ریدایرکت پاسخ داد (کد ${response.status}) و مقصد دنبال نشد؛ وضعیت تنزل‌یافته اعلام می‌شود.`,
        },
        attempted: true,
        metrics: null,
        redis: null,
        n8n: null,
      };
    }

    return {
      result: {
        ...base,
        status: 'DOWN',
        reasonFa: `endpoint با کد وضعیت ${response.status} پاسخ داد؛ سلامت سرویس تأیید نشد (fail-closed).`,
      },
      attempted: true,
      metrics: null,
      redis: null,
      n8n: null,
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
  const outcomes = await Promise.all(CONTAINER_IDS.map((id) => probeEndpoint(id, config)));
  const byId = Object.fromEntries(
    outcomes.map((outcome) => [outcome.result.containerId, outcome]),
  ) as Record<ContainerId, ProbeOutcome>;

  const assessed = outcomes.some((outcome) => outcome.result.status !== 'UNKNOWN');
  const provenance: TelemetrySnapshot['provenance'] = assessed ? 'live' : 'unavailable';
  const containers = CONTAINER_IDS.map((id) => containerFromProbe(id, byId[id], provenance));
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

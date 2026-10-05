/**
 * Canonical sidecar verdict parsing and the fail-closed verdict resolution of
 * the live probe seam (D-171 §5.5; corrective to Phase 27.7 after closeout).
 *
 * ── Why this module exists ──────────────────────────────────────────────────
 * The read-only sidecar (`local/services/health_sidecar.py`) answers `200` only
 * for `HEALTHY` / `DEGRADED` and answers `503` with a canonical verdict body
 * for `DOWN` **and** `UNKNOWN`. The original seam collapsed every non-2xx
 * response to `DOWN`, which erased the sidecar's honest `UNKNOWN` (a surface it
 * could not assess, e.g. a PLANNED dependency) into a stronger claim than the
 * evidence supported. Verdict fidelity is part of fail-closed honesty: the UI
 * must render exactly the verdict the canonical producer emitted.
 *
 * ── Resolution rules (fail-closed) ──────────────────────────────────────────
 * A response body is only trusted as a verdict when it parses as the EXACT
 * canonical shape — an object whose `containerId` equals the probed surface,
 * whose `status` is one of the four canonical states, whose `reasonFa` is a
 * bounded, control-character-free string that is empty exactly for `HEALTHY`,
 * and whose optional `latencyMs` / `probedAtUtc` are well-typed when present.
 * Anything partial or malformed is rejected — never coerced.
 *
 *   2xx  + canonical HEALTHY/DEGRADED   → that verdict (DEGRADED when slow);
 *   2xx  + canonical DOWN/UNKNOWN       → that verdict, with NO measurements;
 *   4xx/5xx + canonical DOWN/UNKNOWN    → that verdict, with NO measurements;
 *   4xx/5xx + a health claim            → refused: the transport failure wins;
 *   4xx/5xx + no canonical verdict body → UNKNOWN (the body proved nothing
 *                                         and the status code alone is not a
 *                                         verdict);
 *   3xx                                 → DEGRADED (target never assessed);
 *   2xx  + no canonical verdict body    → HEALTHY / DEGRADED (slow): a plain
 *                                         answering endpoint keeps the
 *                                         transport contract it always had.
 *
 * Measurements (`metrics`, `depth`/`throughputPerMin`, n8n counters) cross
 * only when the response was 2xx AND the resolved status is `HEALTHY` or
 * `DEGRADED`. A `DOWN` or `UNKNOWN` surface therefore never carries a reading,
 * even when the payload contained metric fields.
 *
 * The module is deliberately dependency-free (type-only imports) so the seam
 * core can be compiled and asserted by `scripts/check-live-verdicts.mjs`
 * without a running server.
 */

import type { ProbeStatus, ProbeVerdictSource } from '@/types/live-probes';
import type { ContainerId, ContainerMetrics } from '@/types/telemetry';

/** The five canonical container surfaces this seam probes (owner directive). */
export const PROBE_CONTAINER_IDS: readonly ContainerId[] = [
  'postgres',
  'n8n',
  'redis',
  'dokploy',
  'walrus',
];

/** Defaults for the per-probe timeout and the slow-response threshold. */
export const DEFAULT_PROBE_TIMEOUT_MS = 2_500;
export const MAX_PROBE_TIMEOUT_MS = 10_000;
export const DEFAULT_PROBE_SLOW_MS = 1_000;

/** The canonical sidecar verdict vocabulary, exactly as emitted on the wire. */
export const SIDECAR_VERDICT_STATUSES: readonly ProbeStatus[] = [
  'HEALTHY',
  'DEGRADED',
  'DOWN',
  'UNKNOWN',
];

/**
 * Upper bound on a verdict reason. The reason is rendered verbatim, so a
 * payload cannot push an unbounded blob (or a stack trace) into the UI.
 */
export const VERDICT_REASON_MAX_CHARS = 600;

const ISO_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/;
const CONTROL_CHARS_RE = /[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/;

/** A structurally validated canonical sidecar verdict. */
export interface SidecarVerdict {
  status: ProbeStatus;
  /** Trimmed, bounded Persian reason; empty exactly for `HEALTHY`. */
  reasonFa: string;
}

/** The resolved probe verdict plus the path that produced it. */
export interface VerdictDecision {
  status: ProbeStatus;
  reasonFa: string;
  verdictSource: ProbeVerdictSource;
}

/** Redis queue readings exposed by a healthy broker payload. */
export interface RedisReadings {
  depth: number;
  throughputPerMin: number;
}

/** n8n workflow readings exposed by a healthy payload. */
export interface N8nReadings {
  active: number;
  waiting: number;
  failedLast24h: number;
}

/** Every reading a probe may carry; all `null` unless genuinely measured. */
export interface ProbeReadings {
  metrics: ContainerMetrics | null;
  redis: RedisReadings | null;
  n8n: N8nReadings | null;
}

function decision(
  status: ProbeStatus,
  reasonFa: string,
  verdictSource: ProbeVerdictSource,
): VerdictDecision {
  return { status, reasonFa, verdictSource };
}

function parseJsonObject(text: string): Record<string, unknown> | null {
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

/**
 * Parse a response body as the canonical sidecar verdict contract.
 *
 * Returns `null` for anything that is not an exact, complete verdict body for
 * `expectedContainerId` — a partial or malformed body is rejected rather than
 * coerced, so a foreign or broken payload can never be mistaken for a verdict.
 */
export function parseSidecarVerdict(
  bodyText: string,
  expectedContainerId: ContainerId,
): SidecarVerdict | null {
  const payload = parseJsonObject(bodyText);
  if (payload === null) return null;

  // Exact typed match: a verdict for a different surface is not a verdict here.
  if (payload.containerId !== expectedContainerId) return null;

  const status = payload.status;
  if (typeof status !== 'string' || !SIDECAR_VERDICT_STATUSES.includes(status as ProbeStatus)) {
    return null;
  }

  const reasonRaw = payload.reasonFa;
  if (typeof reasonRaw !== 'string') return null;
  const reasonFa = reasonRaw.trim();
  if (CONTROL_CHARS_RE.test(reasonFa)) return null;
  if (reasonFa.length > VERDICT_REASON_MAX_CHARS) return null;
  if (status === 'HEALTHY') {
    if (reasonFa !== '') return null;
  } else if (reasonFa === '') {
    return null;
  }

  if ('latencyMs' in payload) {
    const latency = payload.latencyMs;
    if (typeof latency !== 'number' || !Number.isInteger(latency) || latency < 0) return null;
  }
  if ('probedAtUtc' in payload) {
    const at = payload.probedAtUtc;
    if (typeof at !== 'string' || !ISO_RE.test(at)) return null;
  }

  return { status: status as ProbeStatus, reasonFa };
}

/** True exactly for the statuses that may carry measurements. */
export function isMeasuredStatus(status: ProbeStatus): boolean {
  return status === 'HEALTHY' || status === 'DEGRADED';
}

/**
 * Resolve one received response into a verdict.
 *
 * `httpStatus` is the received status code (3xx included; redirects are never
 * followed), `latencyMs` the seam-measured round trip, `slowMs` the threshold
 * above which a 2xx is reported DEGRADED. Network failures / timeouts never
 * reach this function: the seam reports those as UNKNOWN itself.
 */
export function resolveResponseVerdict(
  httpStatus: number,
  bodyText: string,
  containerId: ContainerId,
  slowMs: number,
  latencyMs: number,
): VerdictDecision {
  const is2xx = httpStatus >= 200 && httpStatus < 300;
  const is3xx = httpStatus >= 300 && httpStatus < 400;
  const verdict = parseSidecarVerdict(bodyText, containerId);

  if (verdict !== null && (is2xx || httpStatus >= 400)) {
    if (!is2xx) {
      // Non-2xx: the canonical producer may declare DOWN or UNKNOWN — honor it
      // exactly. A health claim on an error response is contradictory and is
      // refused (the transport failure wins), never promoted.
      if (verdict.status === 'DOWN' || verdict.status === 'UNKNOWN') {
        return decision(verdict.status, verdict.reasonFa, 'sidecar');
      }
      return decision(
        'DOWN',
        `endpoint با کد وضعیت ${httpStatus} پاسخ داد اما بدنه‌ی آن سلامت را اعلام کرد؛` +
          ' تناقض رد شد و وضعیت از کار افتاده اعلام می‌شود (fail-closed).',
        'transport',
      );
    }
    if (verdict.status === 'HEALTHY' && latencyMs >= slowMs) {
      return decision(
        'DEGRADED',
        `پاسخ کاوش کند بود (${latencyMs} ms ≥ آستانه‌ی ${slowMs} ms)؛ وضعیت تنزل‌یافته اعلام می‌شود.`,
        'sidecar',
      );
    }
    // 2xx carrying DOWN/UNKNOWN is off the producer's own contract, but the
    // declared verdict is honored exactly and, being non-measured, carries no
    // readings. It is never promoted to a healthy badge.
    return decision(verdict.status, verdict.reasonFa, 'sidecar');
  }

  if (is2xx) {
    if (latencyMs >= slowMs) {
      return decision(
        'DEGRADED',
        `پاسخ کاوش کند بود (${latencyMs} ms ≥ آستانه‌ی ${slowMs} ms)؛ وضعیت تنزل‌یافته اعلام می‌شود.`,
        'transport',
      );
    }
    return decision('HEALTHY', '', 'transport');
  }

  if (is3xx) {
    return decision(
      'DEGRADED',
      `endpoint با ریدایرکت پاسخ داد (کد ${httpStatus}) و مقصد دنبال نشد؛ وضعیت تنزل‌یافته اعلام می‌شود.`,
      'transport',
    );
  }

  return decision(
    'UNKNOWN',
    `endpoint با کد وضعیت ${httpStatus} پاسخ داد اما بدنه‌ی آن verdict کانونیک sidecar نبود؛` +
      ' وضعیت نامشخص می‌ماند (fail-closed).',
    'transport',
  );
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

function parseRedisReadings(payload: Record<string, unknown> | null): RedisReadings | null {
  if (payload === null) return null;
  const depth = asNonNegativeInt(payload.depth);
  const throughputPerMin = asNonNegativeInt(payload.throughputPerMin);
  if (depth === null || throughputPerMin === null) return null;
  return { depth, throughputPerMin };
}

function parseN8nReadings(payload: Record<string, unknown> | null): N8nReadings | null {
  if (payload === null) return null;
  const active = asNonNegativeInt(payload.active);
  const waiting = asNonNegativeInt(payload.waiting);
  const failedLast24h = asNonNegativeInt(payload.failedLast24h);
  if (active === null || waiting === null || failedLast24h === null) return null;
  return { active, waiting, failedLast24h };
}

/**
 * Extract every reading a response may carry.
 *
 * Fail-closed by construction: readings cross only when the response was 2xx
 * AND the resolved status is `HEALTHY` or `DEGRADED`. A `DOWN`/`UNKNOWN`
 * payload is discarded whole — metric fields it contained are never surfaced.
 */
export function extractReadings(
  httpOk: boolean,
  status: ProbeStatus,
  bodyText: string,
): ProbeReadings {
  if (!httpOk || !isMeasuredStatus(status)) {
    return { metrics: null, redis: null, n8n: null };
  }
  const payload = parseJsonObject(bodyText);
  return {
    metrics: parseMetrics(payload),
    redis: parseRedisReadings(payload),
    n8n: parseN8nReadings(payload),
  };
}

// ── Configuration (read-only, never echoed) ─────────────────────────────────

/** One parsed endpoint: a usable URL or the Persian reason it is unusable. */
export type EndpointSpec = { url: URL; label: string } | { invalidReasonFa: string };

/** The server-side probe configuration; `configErrorFa` refuses every probe. */
export interface ProbeConfig {
  endpoints: Partial<Record<ContainerId, EndpointSpec>>;
  tokens: Partial<Record<ContainerId, string>>;
  timeoutMs: number;
  slowMs: number;
  /** Non-null when the configuration itself is unusable (refuses every probe). */
  configErrorFa: string | null;
}

function readPositiveInt(raw: string | undefined, fallback: number, max: number): number {
  if (raw === undefined || raw.trim() === '') return fallback;
  const value = Number.parseInt(raw, 10);
  if (!Number.isFinite(value) || value <= 0) return fallback;
  return Math.min(value, max);
}

/**
 * Read the probe configuration from an environment map.
 *
 * Endpoint labels are reduced to `host + pathname` so a token embedded in a
 * query string can never be echoed to the UI, and tokens are kept only as an
 * outbound Authorization value. A malformed endpoints/tokens document refuses
 * EVERY probe (config error, all UNKNOWN); one malformed URL affects only its
 * own surface. Never throws.
 */
export function readProbeConfig(
  env: Record<string, string | undefined> = process.env,
): ProbeConfig {
  const timeoutMs = readPositiveInt(env.CP_PROBE_TIMEOUT_MS, DEFAULT_PROBE_TIMEOUT_MS, MAX_PROBE_TIMEOUT_MS);
  const slowMs = readPositiveInt(env.CP_PROBE_SLOW_MS, DEFAULT_PROBE_SLOW_MS, MAX_PROBE_TIMEOUT_MS);

  const endpointsRaw = readJsonObjectEnv(env.CP_PROBE_ENDPOINTS, 'CP_PROBE_ENDPOINTS');
  const tokensRaw = readJsonObjectEnv(env.CP_PROBE_TOKENS, 'CP_PROBE_TOKENS');

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
  for (const id of PROBE_CONTAINER_IDS) {
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
  for (const id of PROBE_CONTAINER_IDS) {
    const raw = tokensRaw.value?.[id];
    if (typeof raw === 'string' && raw !== '') tokens[id] = raw;
  }

  return { endpoints, tokens, timeoutMs, slowMs, configErrorFa: null };
}

/** Read a JSON-object environment value; never throws. */
function readJsonObjectEnv(
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

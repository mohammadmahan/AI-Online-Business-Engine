/**
 * Deterministic mock provider for telemetry, container health and the
 * V-01..V-10 pipeline gates (D-171 §5.4, Phase 27.6).
 *
 * ── Boundaries ──────────────────────────────────────────────────────────────
 * ZERO external network calls; no credentials are read; nothing is written.
 * Every instant below is a fixed literal, so the page prerenders
 * byte-identically (no `Date.now()`, no `Math.random()`).
 *
 * ── Canonical grounding ─────────────────────────────────────────────────────
 * Gate vocabulary is the Cutover Verification Matrix V-01..V-09
 * (`local/scripts/verify_cutover_readiness.py`, D-145; document
 * `docs/deployment/stage-e-cutover-fingerprint-binding.md` §2) plus the
 * Stage-F single-use owner authorization V-10
 * (`docs/deployment/stage-f-authorization.md` §7.2, D-146/D-147). The verifier
 * emits PASS/FAIL (exit 2 = cannot assess); the control plane presents FAIL as
 * BLOCKED, cannot-assess as EVALUATING, and V-10's refusal semantics as
 * BYPASS_PREVENTED. Containers are the five surfaces the owner directive
 * names; `containerRef` is null where no manifest defines a service (Walrus is
 * PLANNED, D-142).
 *
 * ── Fail-closed invariant guard ─────────────────────────────────────────────
 * `assertTelemetryConsistency()` throws at BUILD time when, among others:
 *   1. a container marked DOWN (or UNKNOWN) carries live metrics,
 *   2. a gate marked BLOCKED (or any non-PASS gate) claims to be passing, or a
 *      BLOCKED / BYPASS_PREVENTED gate lacks its audit failure record,
 *   3. a PASS gate lacks FRESH evidence (absent/stale evidence is never green),
 *   4. summary counts disagree with the rendered rows, or an emergency action
 *      is enabled without an owner token AND the signed write path.
 *
 * ── Scenarios ───────────────────────────────────────────────────────────────
 * `steady` (default), `degraded-pipeline`, `gate-blocked` via
 * `CP_TELEMETRY_SCENARIO`; an unrecognised value falls back to `all-unknown`
 * (NO_DATA) so a typo can never render as healthy.
 */

import type { ProbeResult } from '@/types/live-probes';
import type { Provenance } from '@/types/telemetry';
import type {
  ContainerHealth,
  ContainerId,
  ContainerIncident,
  ContainerMetrics,
  ContainerStatus,
  GateAudit,
  GateEvidence,
  GateId,
  GateStatus,
  N8nQueueTelemetry,
  PipelineGate,
  QueuePressure,
  QueueTelemetry,
  RedisQueueTelemetry,
  TelemetryActionSpec,
  TelemetryDataSource,
  TelemetryOverview,
  TelemetrySnapshot,
} from '@/types/telemetry';

/** Named, deterministic scenarios. Default is `steady`. */
export type TelemetryScenario =
  | 'steady'
  | 'degraded-pipeline'
  | 'gate-blocked'
  | 'all-unknown';

/** Fixed literal instant, so the static prerender is byte-stable. */
const MOCK_INSTANT = '2026-10-05T08:00:00.000Z';

/** Logical-clock literal: `L-` + 16 digits (D-093 precedent). */
function logical(n: number): string {
  return `L-${String(n).padStart(16, '0')}`;
}

const ISO_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/;

/** The five canonical container surfaces (owner directive). */
const CONTAINER_IDS: ContainerId[] = ['postgres', 'n8n', 'redis', 'dokploy', 'walrus'];

/** The ten canonical cutover-gate ids (D-145 + D-146/D-147). */
const GATE_IDS: GateId[] = [
  'V-01',
  'V-02',
  'V-03',
  'V-04',
  'V-05',
  'V-06',
  'V-07',
  'V-08',
  'V-09',
  'V-10',
];

/**
 * Fixed queue thresholds. They are environment parameters in production
 * (owner directive: bounds live in configuration); here they are literals so
 * the mock is deterministic.
 */
export const REDIS_WARN_DEPTH = 200;
export const REDIS_CRITICAL_DEPTH = 800;
export const N8N_WARN_WAITING = 10;
export const N8N_CRITICAL_WAITING = 50;
export const N8N_WARN_FAILED = 1;
export const N8N_CRITICAL_FAILED = 5;

/** One container row BEFORE derivation (metrics state / incident pairing). */
interface ContainerSpec {
  id: ContainerId;
  titleFa: string;
  containerRef: string | null;
  status: ContainerStatus;
  /** Present only when a probe produced readings (HEALTHY / DEGRADED). */
  metrics: ContainerMetrics | null;
  portMapping: string | null;
  lastProbeUtc: string | null;
  detailFa: string;
  incident: ContainerIncident | null;
}

/**
 * The steady container catalog.
 *
 * `postgres`/`n8n`/`redis` are probeable deployment surfaces; `dokploy` and
 * `walrus` are honestly UNKNOWN here — dokploy is not probed from this plane
 * (no credential ever reaches the UI, D-171 §6) and walrus is PLANNED until
 * the D-045 owner gate is passed (D-142).
 */
const BASE_CONTAINERS: ContainerSpec[] = [
  {
    id: 'postgres',
    titleFa: 'پایگاه داده‌ی canonical (PostgreSQL)',
    containerRef: 'engine-local-postgres',
    status: 'HEALTHY',
    metrics: { cpuPercent: 12, memoryUsedMb: 384, memoryLimitMb: 2048, uptimeSeconds: 126_000 },
    portMapping: '127.0.0.1:55432→5432',
    lastProbeUtc: '2026-10-05T07:59:52.000Z',
    detailFa: 'SSOT محلی روی PostgreSQL؛ فقط روی loopback منتشر شده است (D-055).',
    incident: null,
  },
  {
    id: 'n8n',
    titleFa: 'موتور اتوماسیون (n8n)',
    containerRef: 'engine-local-n8n',
    status: 'HEALTHY',
    metrics: { cpuPercent: 8, memoryUsedMb: 512, memoryLimitMb: 2048, uptimeSeconds: 126_000 },
    portMapping: '127.0.0.1:15678→5678',
    lastProbeUtc: '2026-10-05T07:59:54.000Z',
    detailFa: 'اجرای workflowها و صف‌های اتوماسیون؛ در استقرار با کارگزار صف Redis کار می‌کند.',
    incident: null,
  },
  {
    id: 'redis',
    titleFa: 'صف و کش (Redis)',
    containerRef: 'redis',
    status: 'HEALTHY',
    metrics: { cpuPercent: 4, memoryUsedMb: 96, memoryLimitMb: 512, uptimeSeconds: 126_000 },
    portMapping: null,
    lastProbeUtc: '2026-10-05T07:59:53.000Z',
    detailFa: 'کارگزار صف/کش استقرار (Stage D)؛ بدون پورت منتشرشده و فقط روی شبکه‌ی داخلی (D-144).',
    incident: null,
  },
  {
    id: 'dokploy',
    titleFa: 'کنترلر استقرار (Dokploy)',
    containerRef: 'dokploy',
    status: 'UNKNOWN',
    metrics: null,
    portMapping: null,
    lastProbeUtc: null,
    detailFa:
      'از این رابط کاوش نمی‌شود؛ کاوش زنده نیازمند اعتبارنامه است و هیچ اعتبارنامه‌ای در رابط نمایش داده نمی‌شود (D-171 §6).',
    incident: null,
  },
  {
    id: 'walrus',
    titleFa: 'لایه‌ی حافظه (Walrus)',
    containerRef: null,
    status: 'UNKNOWN',
    metrics: null,
    portMapping: null,
    lastProbeUtc: null,
    detailFa:
      'PLANNED (D-142)؛ بدون عبور از گیت مالک (D-045) هیچ اتصال زنده‌ای برقرار نمی‌شود.',
    incident: null,
  },
];

/** One gate row BEFORE derivation (`passes` is derived from the status). */
interface GateSpec {
  id: GateId;
  titleFa: string;
  descriptionFa: string;
  status: GateStatus;
  evidence: GateEvidence | null;
  audit: GateAudit | null;
  lastEvaluatedUtc: string | null;
}

/**
 * The steady gate matrix (D-145 + Stage F).
 *
 * V-04 is BLOCKED with its audit failure record; V-05 is EVALUATING with
 * STALE evidence (stale is labelled, never green); V-09 has no evidence yet;
 * V-10 records a refused bypass attempt (its own guard semantics).
 */
const BASE_GATES: GateSpec[] = [
  {
    id: 'V-01',
    titleFa: 'تأییدیه‌ی انتشار D-138',
    descriptionFa:
      'تأییدیه‌ی D-138 برای کاندید نهایی GO است؛ کهنه یا ناموجود هرگز GO فرض نمی‌شود.',
    status: 'PASS',
    evidence: { reference: 'evidence:launch-attestation:go', staleness: 'FRESH' },
    audit: null,
    lastEvaluatedUtc: '2026-10-05T07:52:00.000Z',
  },
  {
    id: 'V-02',
    titleFa: 'پاکیزگی محیط برنامه‌ریزی',
    descriptionFa:
      'هیچ رمز تولیدی در پوسته‌ی برنامه‌ریزی نیست؛ اسکن زنده‌ی D-045 آن را اثبات می‌کند.',
    status: 'PASS',
    evidence: { reference: 'evidence:planning-env-scan:clean', staleness: 'FRESH' },
    audit: null,
    lastEvaluatedUtc: '2026-10-05T07:52:40.000Z',
  },
  {
    id: 'V-03',
    titleFa: 'قرارداد متغیرهای prod',
    descriptionFa:
      'هر متغیر اجباری ${VAR:?} مانیفست تولید در .env.example مستند شده است.',
    status: 'PASS',
    evidence: { reference: 'evidence:env-contract:.env.example', staleness: 'FRESH' },
    audit: null,
    lastEvaluatedUtc: '2026-10-05T07:53:10.000Z',
  },
  {
    id: 'V-04',
    titleFa: 'سقف منابع و سیاست restart',
    descriptionFa:
      'سیاست restart و سقف CPU/حافظه روی همه‌ی سرویس‌های prod اعمال شده است.',
    status: 'BLOCKED',
    evidence: null,
    audit: {
      reasonFa:
        'سقف منابع برای یکی از سرویس‌های prod اعلام نشده است؛ گیت تا اصلاح مانیفست مسدود می‌ماند.',
      traceId: 'trace-4c19a8f2',
      atLogical: logical(205),
    },
    lastEvaluatedUtc: '2026-10-05T07:54:00.000Z',
  },
  {
    id: 'V-05',
    titleFa: 'قرارداد preflight',
    descriptionFa:
      'runtime_preflight محیط ناقص را رد و محیط کامل را می‌پذیرد (اثبات fail-closed).',
    status: 'EVALUATING',
    evidence: {
      reference: 'evidence:runtime-preflight:previous-run',
      staleness: 'STALE',
    },
    audit: null,
    lastEvaluatedUtc: '2026-10-05T06:20:00.000Z',
  },
  {
    id: 'V-06',
    titleFa: 'ماتریس بازگردانی',
    descriptionFa:
      'ماتریس RB-1..RB-6 و مسیر stop→compensate→reconcile کامل است.',
    status: 'PASS',
    evidence: {
      reference: 'evidence:rollback-matrix:rb-1..rb-6',
      staleness: 'FRESH',
    },
    audit: null,
    lastEvaluatedUtc: '2026-10-05T07:54:30.000Z',
  },
  {
    id: 'V-07',
    titleFa: 'سیاست هدرهای لبه',
    descriptionFa: 'HSTS/nosniff/frame-deny/CSP/HTTPS روی لبه اعمال می‌شود.',
    status: 'PASS',
    evidence: {
      reference: 'evidence:edge-header-policy:applied',
      staleness: 'FRESH',
    },
    audit: null,
    lastEvaluatedUtc: '2026-10-05T07:55:00.000Z',
  },
  {
    id: 'V-08',
    titleFa: 'اثر انگشت مانیفست Stage D',
    descriptionFa:
      'اثر انگشت مانیفست قفل شده است و جداسازی شبکه (بدون پورت روی postgres/redis) برقرار است (D-144/D-145).',
    status: 'PASS',
    evidence: {
      reference: 'evidence:manifest-fingerprint:sha256',
      staleness: 'FRESH',
    },
    audit: null,
    lastEvaluatedUtc: '2026-10-05T07:55:30.000Z',
  },
  {
    id: 'V-09',
    titleFa: 'هم‌خوانی healthcheck با probe',
    descriptionFa:
      'هر healthcheck کانتینر به یک معنای infra_health_probe نگاشت می‌شود؛ سرویس بدون check غیرقابل‌راستی‌آزمایی و مسدود است.',
    status: 'EVALUATING',
    evidence: null,
    audit: null,
    lastEvaluatedUtc: '2026-10-05T07:56:00.000Z',
  },
  {
    id: 'V-10',
    titleFa: 'مجوز یک‌بارمصرف مالک (Stage F)',
    descriptionFa:
      'توکن HMAC یک‌بارمصرف مالک؛ مصرف دقیقاً یک‌بار، و فیلدهای ممنوعه هرگز در حکم نوشته نمی‌شوند (D-146/D-147).',
    status: 'BYPASS_PREVENTED',
    evidence: null,
    audit: {
      reasonFa:
        'تلاش برای استفاده‌ی دوباره از توکن مصرف‌شده رد شد؛ فیلدهای ممنوعه در حکم نپذیرفته شدند (D-146).',
      traceId: 'trace-9b07e4d1',
      atLogical: logical(214),
    },
    lastEvaluatedUtc: '2026-10-05T07:56:40.000Z',
  },
];

/** One queue snapshot BEFORE derivation (pressure is derived below). */
interface QueueSpec {
  redis: { depth: number | null; throughputPerMin: number | null };
  n8n: { active: number | null; waiting: number | null; failedLast24h: number | null };
}

/**
 * Redis pressure, derived from depth against the fixed thresholds.
 * `null` depth means the broker did not answer — UNKNOWN, never OK.
 */
export function redisPressure(
  depth: number | null,
  warnAt: number,
  criticalAt: number,
): QueuePressure {
  if (depth === null) return 'UNKNOWN';
  if (depth >= criticalAt) return 'CRITICAL';
  if (depth >= warnAt) return 'WARN';
  return 'OK';
}

/**
 * n8n pressure: worst of the waiting-backlog and recent-failure severities.
 * Any failed execution in the window prevents an OK reading.
 */
export function n8nPressure(
  waiting: number | null,
  failedLast24h: number | null,
): QueuePressure {
  if (waiting === null || failedLast24h === null) return 'UNKNOWN';
  const waitingSeverity =
    waiting >= N8N_CRITICAL_WAITING ? 3 : waiting >= N8N_WARN_WAITING ? 2 : 0;
  const failedSeverity =
    failedLast24h >= N8N_CRITICAL_FAILED ? 3 : failedLast24h >= N8N_WARN_FAILED ? 2 : 0;
  const severity = Math.max(waitingSeverity, failedSeverity);
  if (severity === 3) return 'CRITICAL';
  if (severity === 2) return 'WARN';
  return 'OK';
}

/** Steady queue readings: broker healthy, no failed executions in the window. */
const BASE_QUEUES: QueueSpec = {
  redis: { depth: 42, throughputPerMin: 186 },
  n8n: { active: 3, waiting: 7, failedLast24h: 0 },
};

/** Container overrides per scenario (merged over the steady catalog). */
const CONTAINER_OVERRIDES: Partial<
  Record<TelemetryScenario, Partial<Record<ContainerId, Partial<ContainerSpec>>>>
> = {
  'degraded-pipeline': {
    n8n: {
      status: 'DEGRADED',
      metrics: { cpuPercent: 41, memoryUsedMb: 1_534, memoryLimitMb: 2048, uptimeSeconds: 126_000 },
      incident: {
        severity: 'DEGRADED',
        noteFa: 'انباشت صف انتظار و شکست‌های اخیر؛ نرخ پردازش زیر نرخ ورودی است.',
        raisedAtUtc: '2026-10-05T07:41:00.000Z',
      },
      lastProbeUtc: '2026-10-05T07:59:58.000Z',
    },
    redis: {
      status: 'DOWN',
      metrics: null,
      incident: {
        severity: 'DOWN',
        noteFa: 'کارگزار صف پاسخ نمی‌دهد؛ عمق صف و نرخ پردازش قابل خواندن نیست.',
        raisedAtUtc: '2026-10-05T07:44:00.000Z',
      },
      lastProbeUtc: '2026-10-05T07:44:02.000Z',
    },
  },
  'gate-blocked': {},
};

/** Gate overrides per scenario. */
const GATE_OVERRIDES: Partial<
  Record<TelemetryScenario, Partial<Record<GateId, Partial<GateSpec>>>>
> = {
  'degraded-pipeline': {
    'V-09': {
      status: 'BLOCKED',
      evidence: null,
      audit: {
        reasonFa:
          'healthcheck کانتینر Redis با قرارداد probe هم‌خوان نیست؛ سرویس غیرقابل‌راستی‌آزمایی مسدود می‌ماند (D-145 §4).',
        traceId: 'trace-77a1e0b5',
        atLogical: logical(231),
      },
    },
  },
  'gate-blocked': {
    'V-03': {
      status: 'BLOCKED',
      evidence: null,
      audit: {
        reasonFa:
          'کلیدهای اجباری ${VAR:?} در .env.example غایب‌اند؛ گیت با فهرست کلیدهای ناقص مسدود است.',
        traceId: 'trace-1d4f6c90',
        atLogical: logical(226),
      },
    },
    'V-07': {
      status: 'BLOCKED',
      evidence: null,
      audit: {
        reasonFa:
          'هدرهای امنیتی روی لبه غیرفعال دیده شد؛ گیت تا اعمال سیاست مسدود می‌ماند.',
        traceId: 'trace-8e52b3a7',
        atLogical: logical(228),
      },
    },
  },
};

/** Queue overrides per scenario. */
const QUEUE_OVERRIDES: Partial<Record<TelemetryScenario, QueueSpec>> = {
  'degraded-pipeline': {
    redis: { depth: null, throughputPerMin: null },
    n8n: { active: 9, waiting: 64, failedLast24h: 7 },
  },
  'gate-blocked': {
    redis: { depth: 236, throughputPerMin: 154 },
    n8n: { active: 4, waiting: 12, failedLast24h: 1 },
  },
};

/**
 * Metadata for the five canonical surfaces, shared with the live source so the
 * two seams cannot drift apart in Persian vocabulary.
 */
export interface ContainerMeta {
  titleFa: string;
  containerRef: string | null;
  portMapping: string | null;
  detailFa: string;
}

export const CONTAINER_META = Object.fromEntries(
  BASE_CONTAINERS.map((spec) => [
    spec.id,
    {
      titleFa: spec.titleFa,
      containerRef: spec.containerRef,
      portMapping: spec.portMapping,
      detailFa: spec.detailFa,
    },
  ]),
) as Record<ContainerId, ContainerMeta>;

/** Build one container row: metrics state is derived from the reading. */
function buildContainer(spec: ContainerSpec, provenance: Provenance): ContainerHealth {
  return {
    id: spec.id,
    titleFa: spec.titleFa,
    containerRef: spec.containerRef,
    status: spec.status,
    metricsState: spec.metrics !== null ? 'LIVE' : 'UNAVAILABLE',
    metrics: spec.metrics,
    portMapping: spec.portMapping,
    lastProbeUtc: spec.lastProbeUtc,
    detailFa: spec.detailFa,
    incident: spec.incident,
    // The mock is not a probe: it never fabricates a probe record.
    probe: null,
    provenance,
  };
}

/** Build one gate row: `passes` is derived from the status, never typed. */
function buildGate(spec: GateSpec): PipelineGate {
  return {
    id: spec.id,
    titleFa: spec.titleFa,
    descriptionFa: spec.descriptionFa,
    status: spec.status,
    passes: spec.status === 'PASS',
    evidence: spec.evidence,
    audit: spec.audit,
    lastEvaluatedUtc: spec.lastEvaluatedUtc,
  };
}

/** Build the queue telemetry: pressure is derived from the readings. */
function buildQueues(spec: QueueSpec): QueueTelemetry {
  const redis: RedisQueueTelemetry = {
    depth: spec.redis.depth,
    throughputPerMin: spec.redis.throughputPerMin,
    pressure: redisPressure(spec.redis.depth, REDIS_WARN_DEPTH, REDIS_CRITICAL_DEPTH),
    warnAtDepth: REDIS_WARN_DEPTH,
    criticalAtDepth: REDIS_CRITICAL_DEPTH,
  };
  const n8n: N8nQueueTelemetry = {
    active: spec.n8n.active,
    waiting: spec.n8n.waiting,
    failedLast24h: spec.n8n.failedLast24h,
    pressure: n8nPressure(spec.n8n.waiting, spec.n8n.failedLast24h),
    warnAtWaiting: N8N_WARN_WAITING,
    criticalAtWaiting: N8N_CRITICAL_WAITING,
  };
  return { redis, n8n, probe: { redis: null, n8n: null } };
}

/** Containers for a scenario. `all-unknown` renders every surface as UNKNOWN. */
function containersFor(scenario: TelemetryScenario, provenance: Provenance): ContainerHealth[] {
  if (scenario === 'all-unknown') {
    return BASE_CONTAINERS.map((spec) =>
      buildContainer(
        { ...spec, status: 'UNKNOWN', metrics: null, incident: null, lastProbeUtc: null },
        provenance,
      ),
    );
  }
  const overrides = CONTAINER_OVERRIDES[scenario] ?? {};
  return BASE_CONTAINERS.map((spec) =>
    buildContainer({ ...spec, ...(overrides[spec.id] ?? {}) }, provenance),
  );
}

/**
 * Every gate without a verdict. The live source cannot evaluate the cutover
 * matrix either, so it renders exactly this list (fail-closed: no verdict is
 * never a pass).
 */
export function evaluatingGates(): PipelineGate[] {
  return BASE_GATES.map((spec) =>
    buildGate({
      ...spec,
      status: 'EVALUATING',
      evidence: null,
      audit: null,
      lastEvaluatedUtc: null,
    }),
  );
}

/** Gates for a scenario. `all-unknown` renders every gate as EVALUATING. */
function gatesFor(scenario: TelemetryScenario): PipelineGate[] {
  if (scenario === 'all-unknown') {
    return evaluatingGates();
  }
  const overrides = GATE_OVERRIDES[scenario] ?? {};
  return BASE_GATES.map((spec) => buildGate({ ...spec, ...(overrides[spec.id] ?? {}) }));
}

/** Queue telemetry for a scenario. `all-unknown` reads nothing at all. */
function queuesFor(scenario: TelemetryScenario): QueueTelemetry {
  if (scenario === 'all-unknown') {
    return buildQueues({
      redis: { depth: null, throughputPerMin: null },
      n8n: { active: null, waiting: null, failedLast24h: null },
    });
  }
  return buildQueues(QUEUE_OVERRIDES[scenario] ?? BASE_QUEUES);
}

const CONTAINER_SEVERITY: Record<ContainerStatus, number> = {
  HEALTHY: 0,
  UNKNOWN: 1,
  DEGRADED: 2,
  DOWN: 3,
};

const PRESSURE_SEVERITY: Record<QueuePressure, number> = {
  OK: 0,
  UNKNOWN: 1,
  WARN: 2,
  CRITICAL: 3,
};

/** Count states and resolve the worst cases. The strip DERIVES all of this. */
export function summarizeTelemetry(
  containers: ContainerHealth[],
  gates: PipelineGate[],
  queues: QueueTelemetry,
): TelemetryOverview {
  let worstContainer: ContainerStatus = 'HEALTHY';
  for (const container of containers) {
    if (CONTAINER_SEVERITY[container.status] > CONTAINER_SEVERITY[worstContainer]) {
      worstContainer = container.status;
    }
  }

  let worstQueuePressure: QueuePressure = 'OK';
  for (const pressure of [queues.redis.pressure, queues.n8n.pressure]) {
    if (PRESSURE_SEVERITY[pressure] > PRESSURE_SEVERITY[worstQueuePressure]) {
      worstQueuePressure = pressure;
    }
  }

  const countContainers = (status: ContainerStatus) =>
    containers.filter((container) => container.status === status).length;
  const countGates = (status: GateStatus) =>
    gates.filter((gate) => gate.status === status).length;

  return {
    containersHealthy: countContainers('HEALTHY'),
    containersDegraded: countContainers('DEGRADED'),
    containersDown: countContainers('DOWN'),
    containersUnknown: countContainers('UNKNOWN'),
    gatesPass: countGates('PASS'),
    gatesBlocked: countGates('BLOCKED'),
    gatesEvaluating: countGates('EVALUATING'),
    gatesBypassPrevented: countGates('BYPASS_PREVENTED'),
    worstContainer,
    worstQueuePressure,
  };
}

/**
 * Independent restatement of the verdict bounds (`@/lib/probes/verdict`).
 *
 * The guard deliberately does NOT import the seam implementation it verifies:
 * it must be able to fail even if that implementation drifts, so the bound is
 * written out here rather than shared.
 */
const PROBE_REASON_MAX_CHARS = 600;
const PROBE_REASON_CONTROL_RE = /[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/;

/** True exactly for the statuses that may carry measurements. */
function isMeasuredProbeStatus(status: ProbeResult['status']): boolean {
  return status === 'HEALTHY' || status === 'DEGRADED';
}

/**
 * Verdict-fidelity checks shared by every probe record (container or queue).
 *
 * A `sidecar` verdict is a parsed canonical body, so it must be able to prove
 * it: the payload digest is present and the reason is a bounded, control-free
 * message (no stack trace, blob or credential-shaped text can reach the UI).
 * The rendered badge is compared against the verdict by the caller, so a
 * parsed verdict can never disagree with the state the user sees.
 */
function probeRecordProblems(probe: ProbeResult, label: string, problems: string[]): void {
  if (probe.verdictSource !== 'sidecar' && probe.verdictSource !== 'transport') {
    problems.push(`${label}: probe verdictSource must be 'sidecar' or 'transport'`);
  }
  if (probe.verdictSource === 'sidecar' && probe.payloadDigest === null) {
    problems.push(`${label}: a sidecar verdict requires the parsed payload digest`);
  }
  if (PROBE_REASON_CONTROL_RE.test(probe.reasonFa)) {
    problems.push(`${label}: probe reason must not carry control characters`);
  }
  if (probe.reasonFa.length > PROBE_REASON_MAX_CHARS) {
    problems.push(
      `${label}: probe reason must stay within ${PROBE_REASON_MAX_CHARS} characters`,
    );
  }
}

/**
 * Assert the snapshot cannot display a state the canonical rules forbid.
 *
 * Throwing is the fail-closed behaviour: a contradictory telemetry snapshot is
 * never rendered with a reassuring badge.
 */
export function assertTelemetryConsistency(snapshot: TelemetrySnapshot): TelemetrySnapshot {
  const problems: string[] = [];

  // ── containers ─────────────────────────────────────────────────────────────
  const containerIds = snapshot.containers.map((container) => container.id);
  for (const id of CONTAINER_IDS) {
    if (!containerIds.includes(id)) {
      problems.push(`missing container ${id} (all five surfaces are required)`);
    }
  }
  if (new Set(containerIds).size !== containerIds.length) {
    problems.push('duplicate container id in snapshot');
  }

  for (const container of snapshot.containers) {
    const id = container.id;
    if (!container.titleFa.trim() || !container.detailFa.trim()) {
      problems.push(`${id}: title and detail must not be empty`);
    }

    if (container.status === 'DOWN' && container.metrics !== null) {
      problems.push(`${id}: DOWN container must not carry live metrics (fail-closed)`);
    }
    if (container.status === 'UNKNOWN' && container.metrics !== null) {
      problems.push(`${id}: UNKNOWN container must not carry metrics`);
    }
    const expectedMetricsState = container.metrics !== null ? 'LIVE' : 'UNAVAILABLE';
    if (container.metricsState !== expectedMetricsState) {
      problems.push(
        `${id}: metricsState ${container.metricsState} != derived ${expectedMetricsState}`,
      );
    }
    // A live probe may prove health without exposing CPU/memory, so a
    // measurement is required rather than resource metrics specifically.
    if (
      (container.status === 'HEALTHY' || container.status === 'DEGRADED') &&
      container.metrics === null &&
      container.probe === null
    ) {
      problems.push(`${id}: ${container.status} requires a measurement (metrics or probe)`);
    }

    const metrics = container.metrics;
    if (metrics !== null) {
      if (metrics.cpuPercent < 0 || metrics.cpuPercent > 100) {
        problems.push(`${id}: cpuPercent must be within 0..100`);
      }
      if (
        metrics.memoryUsedMb <= 0 ||
        metrics.memoryLimitMb <= 0 ||
        metrics.memoryUsedMb > metrics.memoryLimitMb
      ) {
        problems.push(`${id}: memory reading must satisfy 0 < used <= limit`);
      }
      if (!Number.isInteger(metrics.uptimeSeconds) || metrics.uptimeSeconds < 0) {
        problems.push(`${id}: uptimeSeconds must be a non-negative integer`);
      }
    }

    if (container.status === 'HEALTHY' && container.incident !== null) {
      problems.push(`${id}: HEALTHY container must not carry an incident`);
    }
    if (container.status === 'DEGRADED' && container.incident?.severity !== 'DEGRADED') {
      problems.push(`${id}: DEGRADED requires a DEGRADED incident note`);
    }
    if (container.status === 'DOWN' && container.incident?.severity !== 'DOWN') {
      problems.push(`${id}: DOWN requires a DOWN incident note`);
    }
    if (container.status === 'UNKNOWN' && container.incident !== null) {
      problems.push(`${id}: UNKNOWN container must not carry an incident`);
    }
    if (container.incident !== null) {
      if (!container.incident.noteFa.trim()) {
        problems.push(`${id}: incident must state its reason`);
      }
      if (!ISO_RE.test(container.incident.raisedAtUtc)) {
        problems.push(`${id}: incident raisedAtUtc is not an ISO-8601 literal`);
      }
    }

    if (container.status === 'HEALTHY' && container.lastProbeUtc === null) {
      problems.push(`${id}: HEALTHY requires a probe instant`);
    }
    if (container.lastProbeUtc !== null && !ISO_RE.test(container.lastProbeUtc)) {
      problems.push(`${id}: lastProbeUtc is not an ISO-8601 literal`);
    }
    if (container.portMapping !== null && !/^[^\s]+→[0-9]{1,5}$/.test(container.portMapping)) {
      problems.push(`${id}: portMapping must be a host→container mapping or null`);
    }
    if (container.provenance !== snapshot.provenance) {
      problems.push(`${id}: container provenance must match the snapshot provenance`);
    }

    const probe = container.probe;
    if (probe !== null) {
      if (probe.containerId !== container.id) {
        problems.push(`${id}: probe containerId ${probe.containerId} != container id`);
      }
      // Verdict fidelity: the parsed verdict IS the rendered badge state, so a
      // sidecar UNKNOWN can never render as DOWN (or any other state).
      if (probe.status !== container.status) {
        problems.push(
          `${id}: probe verdict ${probe.status} (${probe.verdictSource}) != rendered container status ${container.status}`,
        );
      }
      probeRecordProblems(probe, id, problems);
      if (!ISO_RE.test(probe.probedAtUtc)) {
        problems.push(`${id}: probe probedAtUtc is not an ISO-8601 literal`);
      }
      if (probe.status === 'HEALTHY' && probe.reasonFa.trim()) {
        problems.push(`${id}: HEALTHY probe must not carry an error reason`);
      }
      if (probe.status !== 'HEALTHY' && !probe.reasonFa.trim()) {
        problems.push(`${id}: non-HEALTHY probe must state its Persian reason`);
      }
      if (
        probe.latencyMs !== null &&
        (!Number.isInteger(probe.latencyMs) || probe.latencyMs < 0)
      ) {
        problems.push(`${id}: probe latency must be a non-negative integer or null`);
      }
      if (probe.status !== 'UNKNOWN' && probe.latencyMs === null) {
        problems.push(`${id}: an assessable probe must carry its latency`);
      }
      if (probe.payloadDigest !== null && !/^[0-9a-f]{64}$/.test(probe.payloadDigest)) {
        problems.push(`${id}: probe payload digest must be a SHA-256 hex or null`);
      }
      if (container.provenance === 'mock') {
        problems.push(`${id}: a mock snapshot must not carry probe records`);
      }
    }
  }

  // ── gates ──────────────────────────────────────────────────────────────────
  const gateIds = snapshot.gates.map((gate) => gate.id);
  for (const id of GATE_IDS) {
    if (!gateIds.includes(id)) {
      problems.push(`missing gate ${id} (V-01..V-10 must all be present)`);
    }
  }
  if (new Set(gateIds).size !== gateIds.length) {
    problems.push('duplicate gate id in snapshot');
  }

  for (const gate of snapshot.gates) {
    const id = gate.id;
    if (!gate.titleFa.trim() || !gate.descriptionFa.trim()) {
      problems.push(`${id}: title and description must not be empty`);
    }

    // The mandated invariant: only a PASS gate may claim to be passing, so a
    // BLOCKED (or EVALUATING / BYPASS_PREVENTED) gate can never render green.
    if (gate.passes !== (gate.status === 'PASS')) {
      problems.push(`${id}: ${gate.status} gate must not be marked as passing (fail-closed)`);
    }

    if (gate.status === 'PASS') {
      if (gate.evidence === null) {
        problems.push(`${id}: PASS requires evidence (absent evidence is never green)`);
      } else if (gate.evidence.staleness !== 'FRESH') {
        problems.push(`${id}: PASS requires FRESH evidence (stale evidence is never green)`);
      }
      if (gate.audit !== null) {
        problems.push(`${id}: PASS must not carry a failure audit`);
      }
      if (gate.lastEvaluatedUtc === null) {
        problems.push(`${id}: PASS requires an evaluation instant`);
      }
    }

    if (gate.status === 'BLOCKED' || gate.status === 'BYPASS_PREVENTED') {
      if (gate.audit === null || !gate.audit.reasonFa.trim()) {
        problems.push(`${id}: ${gate.status} requires an audit failure reason`);
      }
      if (gate.audit !== null && !gate.audit.traceId.trim()) {
        problems.push(`${id}: ${gate.status} audit must carry a D-121 trace id`);
      }
      if (gate.audit !== null && !/^L-[0-9]{16}$/.test(gate.audit.atLogical)) {
        problems.push(`${id}: ${gate.status} audit instant is not a logical-clock literal`);
      }
    }

    if (gate.status === 'EVALUATING') {
      if (gate.audit !== null) {
        problems.push(`${id}: EVALUATING must not carry a failure audit`);
      }
      if (gate.evidence !== null && gate.evidence.staleness !== 'STALE') {
        problems.push(`${id}: EVALUATING evidence must be absent or STALE`);
      }
    }

    if (gate.evidence !== null && !gate.evidence.reference.trim()) {
      problems.push(`${id}: evidence reference must not be empty`);
    }
    if (gate.lastEvaluatedUtc !== null && !ISO_RE.test(gate.lastEvaluatedUtc)) {
      problems.push(`${id}: lastEvaluatedUtc is not an ISO-8601 literal`);
    }
  }

  // ── queues ────────────────────────────────────────────────────────────────
  const { redis, n8n } = snapshot.queues;
  if (redis.warnAtDepth <= 0 || redis.criticalAtDepth <= redis.warnAtDepth) {
    problems.push('redis thresholds must satisfy 0 < warn < critical');
  }
  if ((redis.depth === null) !== (redis.throughputPerMin === null)) {
    problems.push('redis depth and throughput must be readable together');
  }
  if (redis.depth !== null && (!Number.isInteger(redis.depth) || redis.depth < 0)) {
    problems.push('redis depth must be a non-negative integer');
  }
  if (
    redis.throughputPerMin !== null &&
    (!Number.isInteger(redis.throughputPerMin) || redis.throughputPerMin < 0)
  ) {
    problems.push('redis throughput must be a non-negative integer');
  }
  const expectedRedisPressure = redisPressure(
    redis.depth,
    redis.warnAtDepth,
    redis.criticalAtDepth,
  );
  if (redis.pressure !== expectedRedisPressure) {
    problems.push(`redis pressure ${redis.pressure} != derived ${expectedRedisPressure}`);
  }

  const n8nReadings = [n8n.active, n8n.waiting, n8n.failedLast24h];
  const allAbsent = n8nReadings.every((value) => value === null);
  const anyAbsent = n8nReadings.some((value) => value === null);
  if (!allAbsent && anyAbsent) {
    problems.push('n8n readings must be all present or all absent');
  }
  const n8nLabels: Array<[string, number | null]> = [
    ['active', n8n.active],
    ['waiting', n8n.waiting],
    ['failedLast24h', n8n.failedLast24h],
  ];
  for (const [label, value] of n8nLabels) {
    if (value !== null && (!Number.isInteger(value) || value < 0)) {
      problems.push(`n8n ${label} must be a non-negative integer`);
    }
  }
  const expectedN8nPressure = n8nPressure(n8n.waiting, n8n.failedLast24h);
  if (n8n.pressure !== expectedN8nPressure) {
    problems.push(`n8n pressure ${n8n.pressure} != derived ${expectedN8nPressure}`);
  }
  if (n8n.failedLast24h !== null && n8n.failedLast24h > 0 && n8n.pressure === 'OK') {
    problems.push('n8n with failed executions must not read OK');
  }
  if (n8n.warnAtWaiting <= 0 || n8n.criticalAtWaiting <= n8n.warnAtWaiting) {
    problems.push('n8n thresholds must satisfy 0 < warn < critical');
  }

  for (const broker of ['redis', 'n8n'] as const) {
    const probe = snapshot.queues.probe?.[broker] ?? null;
    if (probe === null) continue;
    if (probe.containerId !== broker) {
      problems.push(`${broker} queue probe must reference its own container`);
    }
    probeRecordProblems(probe, `${broker} queue`, problems);
    // No phantom metrics: a broker verdict other than HEALTHY/DEGRADED
    // discards the readings whole, whatever the payload exposed.
    if (!isMeasuredProbeStatus(probe.status)) {
      if (broker === 'redis' && (redis.depth !== null || redis.throughputPerMin !== null)) {
        problems.push(
          'redis readings must be absent unless the broker probe assessed HEALTHY/DEGRADED (fail-closed)',
        );
      }
      if (
        broker === 'n8n' &&
        (n8n.active !== null || n8n.waiting !== null || n8n.failedLast24h !== null)
      ) {
        problems.push(
          'n8n readings must be absent unless the probe assessed HEALTHY/DEGRADED (fail-closed)',
        );
      }
    }
    if (!ISO_RE.test(probe.probedAtUtc)) {
      problems.push(`${broker} queue probe instant is not an ISO-8601 literal`);
    }
    if (probe.status !== 'HEALTHY' && !probe.reasonFa.trim()) {
      problems.push(`${broker} queue probe must state its Persian reason`);
    }
    if (
      probe.latencyMs !== null &&
      (!Number.isInteger(probe.latencyMs) || probe.latencyMs < 0)
    ) {
      problems.push(`${broker} queue probe latency must be a non-negative integer or null`);
    }
    if (probe.payloadDigest !== null && !/^[0-9a-f]{64}$/.test(probe.payloadDigest)) {
      problems.push(`${broker} queue probe digest must be a SHA-256 hex or null`);
    }
  }

  // ── the seam that produced the snapshot is stated, not inferred ──────────
  if (snapshot.sourceMode === 'MOCK' && snapshot.provenance === 'live') {
    problems.push('a MOCK snapshot must not claim live provenance');
  }
  if (snapshot.sourceMode === 'LIVE' && snapshot.provenance === 'mock') {
    problems.push('a LIVE snapshot must not claim mock provenance');
  }

  // ── summary is derived, never retyped ─────────────────────────────────────
  const expected = summarizeTelemetry(snapshot.containers, snapshot.gates, snapshot.queues);
  for (const key of Object.keys(expected) as Array<keyof TelemetryOverview>) {
    if (snapshot.summary[key] !== expected[key]) {
      problems.push(`summary.${key} ${snapshot.summary[key]} != ${expected[key]}`);
    }
  }

  // ── gated emergency actions (D-146 / D-171 §6) ────────────────────────────
  for (const action of snapshot.actions) {
    if (!action.titleFa.trim() || !action.descriptionFa.trim()) {
      problems.push(`${action.id}: title and description must not be empty`);
    }
    if (
      action.enabled &&
      (!snapshot.writeGate.tokenPresent || !snapshot.writeGate.signaturePathConnected)
    ) {
      problems.push(
        `${action.id}: action enabled without an owner token and the signed write path (D-146/D-171 §6)`,
      );
    }
    if (action.enabled && action.blockedReasonFa.length > 0) {
      problems.push(`${action.id}: enabled action must not carry a blocked reason`);
    }
    if (!action.enabled && !action.blockedReasonFa.trim()) {
      problems.push(`${action.id}: disabled action must state why it is unavailable`);
    }
  }

  if (problems.length > 0) {
    throw new Error(`fail-closed violation in telemetry snapshot: ${problems.join('; ')}`);
  }
  return snapshot;
}

/**
 * The three gated emergency controls of the override panel (D-171 §5.4/§6).
 *
 * Every one is DISABLED: forcing a gate, restarting a container or flushing a
 * queue each bypass the owner gate, and this phase holds neither a single-use
 * owner token (D-146) nor the signed canonical/webhook write path (D-171 §6).
 * A disabled control always states why (fail-closed); the guard rejects an
 * enabled action without BOTH preconditions.
 */
const FORCE_GATE_REASON =
  'عبور از گیت تنها با حکم یک‌بارمصرف مالک ممکن است (D-146)؛ این رابط نه توکن دارد و نه مسیر نوشتن امضاشده (D-171 §6)';

const RESTART_REASON =
  'راه‌اندازی دوباره نیازمند اعتبارنامه‌ی کنترل‌کننده‌ی استقرار است و هیچ اعتبارنامه‌ای در این رابط نگهداری نمی‌شود (D-171 §6)';

const FLUSH_REASON =
  'تخلیه‌ی صف کنشی برگشت‌ناپذیر است و بدون توکن یک‌بارمصرف مالک و مسیر نوشتن امضاشده اجرا نمی‌شود (D-146/D-171 §6)';

/**
 * The gated emergency controls, exported so the live source renders the same
 * disabled reality: live probes change what is KNOWN, never what may be
 * executed.
 */
export const GATED_ACTIONS: TelemetryActionSpec[] = [
  {
    id: 'FORCE_GATE_PASS',
    titleFa: 'عبور اجباری از گیت',
    descriptionFa:
      'نشاندن وضعیت PASS روی یک گیت بدون شواهد تأییدشده؛ کنشی که تنها با حکم یک‌بارمصرف مالک صادر می‌شود و هرگز از این رابط اجرا نمی‌شود (D-146)',
    requiresSecondConfirmation: true,
    enabled: false,
    blockedReasonFa: FORCE_GATE_REASON,
  },
  {
    id: 'RESTART_CONTAINER',
    titleFa: 'راه‌اندازی دوباره‌ی کانتینر',
    descriptionFa:
      'بازگرداندن یک کانتینر از کارافتاده از مسیر کنترل‌کننده‌ی استقرار، با ثبت رکورد در لجر و بازگشت در صورت شکست (D-121)',
    requiresSecondConfirmation: false,
    enabled: false,
    blockedReasonFa: RESTART_REASON,
  },
  {
    id: 'FLUSH_QUEUE',
    titleFa: 'تخلیه‌ی صف',
    descriptionFa:
      'خالی‌کردن صف کار Redis پس از رفع انسداد؛ کنشی برگشت‌ناپذیر که نیازمند تأیید دوم و حکم مالک است',
    requiresSecondConfirmation: true,
    enabled: false,
    blockedReasonFa: FLUSH_REASON,
  },
];

/** Build the full snapshot for a scenario, guarded for fail-closed consistency. */
export function mockTelemetry(scenario: TelemetryScenario = 'steady'): TelemetrySnapshot {
  const unavailable = scenario === 'all-unknown';
  const containers = containersFor(scenario, unavailable ? 'unavailable' : 'mock');
  const gates = gatesFor(scenario);
  const queues = queuesFor(scenario);
  const snapshot: TelemetrySnapshot = {
    generatedAt: MOCK_INSTANT,
    scenario,
    provenance: unavailable ? 'unavailable' : 'mock',
    sourceMode: 'MOCK',
    containers,
    gates,
    queues,
    actions: GATED_ACTIONS,
    // No token and no signed write path exist in this phase, so every action
    // must be disabled — the guard enforces that pairing.
    writeGate: { tokenPresent: false, signaturePathConnected: false },
    summary: summarizeTelemetry(containers, gates, queues),
  };
  return assertTelemetryConsistency(snapshot);
}

/**
 * Read the active scenario from the environment.
 *
 * Defaults to `steady`; an unrecognised value falls back to `all-unknown`, so a
 * typo can never render as healthy containers or passing gates (fail-closed).
 */
export function activeTelemetryScenario(): TelemetryScenario {
  const raw = process.env.CP_TELEMETRY_SCENARIO;
  if (raw === undefined || raw === '' || raw === 'steady') return 'steady';
  if (raw === 'degraded-pipeline') return 'degraded-pipeline';
  if (raw === 'gate-blocked') return 'gate-blocked';
  return 'all-unknown';
}

/** The mock implementation of the swap seam. */
export function createMockTelemetrySource(
  scenario: TelemetryScenario = 'steady',
): TelemetryDataSource {
  return {
    async load(): Promise<TelemetrySnapshot> {
      return mockTelemetry(scenario);
    },
  };
}

/**
 * The single production seam (D-171 §5.5, Phase 27.7).
 *
 * The deterministic mock remains the DEFAULT so CI and local runs stay
 * byte-stable; `CP_TELEMETRY_MODE=LIVE` selects the server-side read-only
 * probe source instead. The live module is imported lazily so its Node-only
 * probe code is never pulled into a build (or bundle) that does not use it.
 */
export async function getTelemetrySource(): Promise<TelemetryDataSource> {
  if (process.env.CP_TELEMETRY_MODE === 'LIVE') {
    const { createLiveTelemetrySource } = await import('@/lib/probes/live-source');
    return createLiveTelemetrySource();
  }
  return createMockTelemetrySource(activeTelemetryScenario());
}

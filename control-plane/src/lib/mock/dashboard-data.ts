/**
 * Deterministic mock provider for the executive overview (D-171 §5.1).
 *
 * ── Boundaries ──────────────────────────────────────────────────────────────
 * This module makes ZERO external network calls and reads no credentials. It
 * returns fixed, hand-written samples so that:
 *   - the page prerenders identically on every build (no `Date.now()`, no
 *     `Math.random()` — every instant and value below is a literal), and
 *   - nothing here can be mistaken for evidence.
 *
 * Every value carries `provenance: 'mock'`, and the page renders a MOCK note. The directive calls for an explicit notice (D-171 §2.2), so the
 * page renders a MOCK badge plus that notice, because a mocked green is not a
 * verified green. Walrus is reported `unavailable` / `NOT_CONNECTED` in every
 * scenario: the shared-memory layer is PLANNED and may not be shown as
 * connected before the D-045 owner gate (D-142, D-171 §5.5).
 *
 * ── Fail-closed consistency guard ───────────────────────────────────────────
 * `mockSnapshot()` runs `assertFailClosedConsistency()` before returning. A
 * snapshot is rejected when a service or KPI claims a success state that its
 * own metrics contradict — e.g. a green `OK` badge over a metric that reads
 * `NOT_PROBED`. The guard is one-directional on purpose: non-success states
 * (unknown, unavailable, degraded) may carry measured values, because
 * degradation is a threshold judgment; but `ok` asserts that a measurement
 * exists, so it must be backed by measured values everywhere.
 *
 * ── Swap seam ───────────────────────────────────────────────────────────────
 * `createMockDashboardSource()` returns the same `DashboardDataSource`
 * interface a live probe-backed source will implement, so live wiring
 * (Phases 5–18) replaces exactly one function call.
 */

import type {
  DashboardDataSource,
  DashboardSnapshot,
  EmergencyAction,
  KpiCard,
  PendingApproval,
  SystemEvent,
} from '@/types/dashboard';
import type { Metric, ServiceHealth } from '@/types/telemetry';

/** Named, deterministic scenarios. Default is `steady`. */
export type Scenario = 'steady' | 'degraded' | 'all-unknown';

/**
 * The instant every mock reading is stamped with. A fixed literal, so the
 * static prerender is byte-stable across builds and machines.
 */
const MOCK_INSTANT = '2026-10-03T09:30:00.000Z';

/** A mock reading is never evidence, so it never renders as PASS. */
const MOCK_DETAIL = 'داده‌ی نمونه — اعتبارسنجی زنده انجام نشده است';

/**
 * Metric values that mean "no measurement exists". The single source of truth
 * for the guard below, so the provider and its checker cannot drift apart.
 */
const UNMEASURED_VALUES = new Set(['—', 'NOT_PROBED', 'UNKNOWN', 'NOT_CONNECTED']);

/** True when a metric carries a real reading. */
export function isMeasured(metric: Metric): boolean {
  if (metric.value === null) return false;
  return !UNMEASURED_VALUES.has(metric.value.trim().toUpperCase());
}

/** A metric that was never measured; renders as «—». */
function unmeasured(label: string, code: string): Metric {
  return { label, code, value: null };
}

/** A metric that carries a reading. */
function measured(label: string, code: string, value: string): Metric {
  return { label, code, value };
}

/** Placeholder value used by the KPI cards when nothing was measured. */
const KPI_UNMEASURED = '—';

/**
 * Reject any snapshot whose success states are contradicted by its own data.
 *
 * Throwing here is the fail-closed behaviour: a contradictory snapshot is never
 * rendered at all, rather than rendered with a reassuring badge.
 */
export function assertFailClosedConsistency(snapshot: DashboardSnapshot): DashboardSnapshot {
  const problems: string[] = [];

  for (const service of snapshot.services) {
    if (service.state !== 'ok') continue;
    const unmeasuredCodes = service.metrics
      .filter((metric) => !isMeasured(metric))
      .map((metric) => metric.code);
    if (unmeasuredCodes.length > 0) {
      problems.push(`${service.id}: state OK while ${unmeasuredCodes.join(', ')} unmeasured`);
    }
    if (service.lastMeasuredAt === null) {
      problems.push(`${service.id}: state OK with no measurement instant`);
    }
    if (service.provenance === 'unavailable') {
      problems.push(`${service.id}: state OK while provenance is unavailable`);
    }
  }

  for (const kpi of snapshot.kpis) {
    if (kpi.state !== 'ok') continue;
    if (kpi.value === KPI_UNMEASURED) {
      problems.push(`${kpi.id}: state OK with no value`);
    }
    if (kpi.provenance === 'unavailable') {
      problems.push(`${kpi.id}: state OK while provenance is unavailable`);
    }
  }

  if (problems.length > 0) {
    throw new Error(`fail-closed violation in dashboard snapshot: ${problems.join('; ')}`);
  }
  return snapshot;
}

/**
 * Walrus is `unavailable` in EVERY scenario — the memory layer is PLANNED and
 * has no connection until the D-045 owner gate is passed (D-142).
 */
const WALRUS_NOT_CONNECTED: ServiceHealth = {
  id: 'walrus',
  title: 'حافظه‌ی مشترک (Walrus)',
  code: 'MEMORY_LAYER',
  state: 'unavailable',
  provenance: 'unavailable',
  detail: 'لایه‌ی حافظه PLANNED است و تا گذر از گیت مالک (D-045) متصل نمی‌شود',
  metrics: [
    measured('وضعیت', 'STATE', 'NOT_CONNECTED'),
    unmeasured('نام‌فضاهای همگام‌شده', 'SYNCED_NAMESPACES'),
    unmeasured('دوره‌های همگام‌سازی', 'SYNCED_EPOCHS'),
  ],
  lastMeasuredAt: null,
};

/**
 * A service whose probe has not run. Used by the `all-unknown` scenario: the
 * state is `unknown`, so no metric may look like a reading.
 */
function unprobedService(
  id: ServiceHealth['id'],
  title: string,
  code: string,
  metrics: Metric[],
): ServiceHealth {
  return {
    id,
    title,
    code,
    state: 'unknown',
    provenance: 'unavailable',
    detail: 'هیچ اندازه‌گیری‌ای انجام نشده است — وضعیت نامشخص است',
    metrics: metrics.map((metric) => unmeasured(metric.label, metric.code)),
    lastMeasuredAt: null,
  };
}

/** Service health grid for a scenario. */
function services(scenario: Scenario): ServiceHealth[] {
  if (scenario === 'all-unknown') {
    return [
      unprobedService('postgres', 'PostgreSQL (SSOT)', 'CANONICAL_DB', [
        measured('وضعیت اتصال', 'CONNECTION', 'x'),
        measured('استخر اتصال (فعال/بیشینه)', 'POOL', 'x'),
        measured('تأخیر رفت‌وبرگشت', 'ROUNDTRIP', 'x'),
      ]),
      unprobedService('dokploy', 'گره استقرار (Dokploy)', 'DEPLOY_NODE', [
        measured('وضعیت عامل', 'AGENT', 'x'),
        measured('مصرف CPU', 'CPU', 'x'),
        measured('مصرف حافظه', 'RAM', 'x'),
      ]),
      unprobedService('n8n', 'موتور اتوماسیون (n8n)', 'AUTOMATION_ENGINE', [
        measured('جریان‌های فعال', 'ACTIVE_WORKFLOWS', 'x'),
        measured('وضعیت تریگر', 'TRIGGER', 'x'),
        measured('اجراهای در انتظار', 'QUEUED', 'x'),
      ]),
      WALRUS_NOT_CONNECTED,
    ];
  }

  const degraded = scenario === 'degraded';

  return [
    {
      id: 'postgres',
      title: 'PostgreSQL (SSOT)',
      code: 'CANONICAL_DB',
      // The pool reading is degraded in this scenario, so the state is NOT ok:
      // an `ok` badge may never sit above a threshold breach.
      state: degraded ? 'degraded' : 'ok',
      provenance: 'mock',
      detail: degraded
        ? 'داده‌ی نمونه: تأخیر استخر بالاتر از آستانه است'
        : MOCK_DETAIL,
      metrics: [
        measured('وضعیت اتصال', 'CONNECTION', 'CONNECTED'),
        measured('استخر اتصال (فعال/بیشینه)', 'POOL', degraded ? '17 / 20' : '4 / 20'),
        measured('تأخیر رفت‌وبرگشت', 'ROUNDTRIP', degraded ? '412 ms' : '3 ms'),
      ],
      lastMeasuredAt: MOCK_INSTANT,
    },
    {
      id: 'dokploy',
      title: 'گره استقرار (Dokploy)',
      code: 'DEPLOY_NODE',
      // CPU/RAM are high in the degraded scenario, so the state follows.
      state: degraded ? 'degraded' : 'ok',
      provenance: 'mock',
      detail: degraded
        ? 'داده‌ی نمونه: مصرف CPU و حافظه بالاتر از آستانه است'
        : MOCK_DETAIL,
      metrics: [
        measured('وضعیت عامل', 'AGENT', 'RESPONDING'),
        measured('مصرف CPU', 'CPU', degraded ? '78%' : '23%'),
        measured('مصرف حافظه', 'RAM', degraded ? '81%' : '41%'),
      ],
      lastMeasuredAt: MOCK_INSTANT,
    },
    {
      id: 'n8n',
      title: 'موتور اتوماسیون (n8n)',
      code: 'AUTOMATION_ENGINE',
      state: degraded ? 'unavailable' : 'ok',
      provenance: degraded ? 'unavailable' : 'mock',
      detail: degraded
        ? 'داده‌ی نمونه: وب‌هوک پاسخ نمی‌دهد — کنش‌های وابسته غیرفعال‌اند'
        : MOCK_DETAIL,
      // When unreachable, NO metric may report a reading.
      metrics: degraded
        ? [
            unmeasured('جریان‌های فعال', 'ACTIVE_WORKFLOWS'),
            measured('وضعیت تریگر', 'TRIGGER', 'UNREACHABLE'),
            unmeasured('اجراهای در انتظار', 'QUEUED'),
          ]
        : [
            measured('جریان‌های فعال', 'ACTIVE_WORKFLOWS', '12'),
            measured('وضعیت تریگر', 'TRIGGER', 'ACTIVE'),
            measured('اجراهای در انتظار', 'QUEUED', '0'),
          ],
      lastMeasuredAt: degraded ? null : MOCK_INSTANT,
    },
    WALRUS_NOT_CONNECTED,
  ];
}

/** Executive KPI cards for a scenario. */
function kpis(scenario: Scenario): KpiCard[] {
  const unknown = scenario === 'all-unknown';
  const degraded = scenario === 'degraded';
  const provenance = unknown ? ('unavailable' as const) : ('mock' as const);

  return [
    {
      id: 'orders_revenue',
      title: 'سفارش‌ها و درآمد امروز',
      code: 'ORDERS_REVENUE',
      value: unknown ? KPI_UNMEASURED : degraded ? '31' : '148',
      unit: unknown ? undefined : 'سفارش',
      secondary: unknown
        ? 'درآمد: —'
        : degraded
          ? 'درآمد: 41,250,000 تومان'
          : 'درآمد: 186,400,000 تومان',
      trend: unknown
        ? null
        : {
            direction: degraded ? 'down' : 'up',
            deltaPercent: degraded ? 12.4 : 8.6,
            comparison: 'نسبت به دیروز',
          },
      goodWhen: 'up',
      state: unknown ? 'unknown' : degraded ? 'warn' : 'ok',
      detail: unknown ? 'داده‌ای برای این شاخص وجود ندارد' : MOCK_DETAIL,
      provenance,
    },
    {
      id: 'hitl_pending',
      title: 'در انتظار تأیید انسانی',
      code: 'HITL_PENDING',
      value: unknown ? KPI_UNMEASURED : degraded ? '17' : '3',
      unit: unknown ? undefined : 'مورد',
      secondary: unknown
        ? undefined
        : degraded
          ? '۴ مورد بحرانی'
          : '۱ مورد با شدت بالا',
      trend: null,
      goodWhen: 'down',
      // A pending queue is never "ok": it needs human attention by definition.
      state: unknown ? 'unknown' : degraded ? 'alert' : 'warn',
      detail: unknown
        ? 'صف تأیید هنوز متصل نشده است'
        : 'صف از داده‌ی نمونه پر شده است — بازبینی انسانی همچنان لازم است',
      href: '/hitl-queue',
      provenance,
    },
    {
      id: 'automations_running',
      title: 'اتوماسیون‌های در حال اجرا',
      code: 'AUTOMATIONS_RUNNING',
      value: unknown ? KPI_UNMEASURED : degraded ? '0' : '12',
      unit: unknown ? undefined : 'جریان',
      secondary: unknown
        ? undefined
        : degraded
          ? 'موتور در دسترس نیست'
          : '۳ صف فعال',
      trend: null,
      goodWhen: 'up',
      state: unknown ? 'unknown' : degraded ? 'alert' : 'ok',
      detail: unknown ? 'وضعیت موتور اتوماسیون نامشخص است' : MOCK_DETAIL,
      provenance,
    },
    {
      id: 'anomalies',
      title: 'خطاها و ناهنجاری‌ها',
      code: 'ANOMALIES',
      value: unknown ? KPI_UNMEASURED : degraded ? '6' : '0',
      unit: unknown ? undefined : 'مورد',
      secondary: unknown
        ? undefined
        : degraded
          ? '۲ خطای بحرانی'
          : 'بدون خطای ثبت‌شده',
      trend: null,
      goodWhen: 'down',
      state: unknown ? 'unknown' : degraded ? 'alert' : 'ok',
      detail: unknown
        ? 'هیچ اندازه‌گیری‌ای انجام نشده است'
        : 'شمارش از داده‌ی نمونه است، نه از لجر زنده',
      provenance,
    },
  ];
}

/** Pending human-review items — the quick list links into `/hitl-queue`. */
function pendingApprovals(scenario: Scenario): PendingApproval[] {
  if (scenario === 'all-unknown') return [];

  return [
    {
      id: 'HITL-2401',
      severity: 'critical',
      category: 'قیمت‌گذاری',
      source: 'price_sync',
      age: '۲ دقیقه',
      summary: 'کاهش ۳۸٪ قیمت پیشنهادی برای ۴ SKU',
    },
    {
      id: 'HITL-2398',
      severity: 'high',
      category: 'موجودی',
      source: 'inventory_agent',
      age: '۱۴ دقیقه',
      summary: 'بازنشانی موجودی انبار مرکزی به ۰',
    },
    {
      id: 'HITL-2395',
      severity: 'medium',
      category: 'محتوا',
      source: 'content_agent',
      age: '۳۱ دقیقه',
      summary: 'انتشار پیش‌نویس توضیحات محصول',
    },
  ];
}

/** Recent system transitions, each with a D-121 trace id (never a secret). */
function events(scenario: Scenario): SystemEvent[] {
  if (scenario === 'all-unknown') return [];

  const rows: SystemEvent[] = [
    {
      id: 'EVT-8841',
      at: '2026-10-03T09:28:00.000Z',
      kind: 'hitl.item.created',
      summary: 'مورد تأیید جدید در صف ثبت شد',
      traceId: 'trace-8f41c2a7',
    },
    {
      id: 'EVT-8839',
      at: '2026-10-03T09:21:00.000Z',
      kind: 'gate.evidence.stale',
      summary: 'شواهد یک گیت کهنه شد و به STALE تغییر یافت',
      traceId: 'trace-2b90d5e1',
    },
    {
      id: 'EVT-8836',
      at: '2026-10-03T09:12:00.000Z',
      kind: 'automation.run.completed',
      summary: 'اجرای جریان همگام‌سازی محصولات کامل شد',
      traceId: 'trace-77aa31fd',
    },
    {
      id: 'EVT-8833',
      at: '2026-10-03T08:58:00.000Z',
      kind: 'security.redaction.applied',
      summary: 'ماسک‌گذاری داده روی پاسخ یک سرویس اعمال شد',
      traceId: 'trace-19ce04b8',
    },
    {
      id: 'EVT-8830',
      at: '2026-10-03T08:44:00.000Z',
      kind: 'system.theme.changed',
      summary: 'تم نمایشی از روشن به تاریک تغییر کرد',
      traceId: 'trace-5d62ef70',
    },
  ];

  if (scenario === 'degraded') {
    return [
      {
        id: 'EVT-8843',
        at: '2026-10-03T09:29:00.000Z',
        kind: 'webhook.dispatch.failed',
        summary: 'ارسال وب‌هوک ناموفق بود — کنش‌های وابسته غیرفعال شدند',
        traceId: 'trace-c41e77b2',
      },
      ...rows.slice(0, 4),
    ];
  }

  return rows;
}

/** Emergency controls — always preview-only in this phase. */
const EMERGENCY_ACTIONS: EmergencyAction[] = [
  {
    id: 'soft_pause',
    title: 'توقف نرم اتوماسیون‌ها',
    description: 'جریان‌های n8n پس از پایان اجرای جاری متوقف می‌شوند',
    effect: 'اجرای جدید آغاز نمی‌شود؛ اجراهای در جریان کامل می‌شوند',
    requiresSecondConfirmation: true,
    enabled: false,
    blockedReason:
      'مسیر وب‌هوک امضاشده هنوز متصل نیست؛ فعال‌سازی فقط از مسیر مجاز مالک (D-139)',
  },
  {
    id: 'flush_preview',
    title: 'پاک‌سازی سراسری (پیش‌نمایش)',
    description: 'پیش‌نمایش پاک‌سازی کش و صف‌های موقت',
    effect: 'صف‌ها و کش پاک می‌شوند؛ داده‌ی SSOT هرگز تغییر نمی‌کند',
    requiresSecondConfirmation: true,
    enabled: false,
    blockedReason:
      'پاک‌سازی کنشی برگشت‌ناپذیر است و تا اتصال مسیر امضاشده غیرفعال می‌ماند',
  },
];

/** Build the full snapshot for a scenario, guarded for fail-closed consistency. */
export function mockSnapshot(scenario: Scenario = 'steady'): DashboardSnapshot {
  const snapshot: DashboardSnapshot = {
    generatedAt: MOCK_INSTANT,
    scenario,
    provenance: scenario === 'all-unknown' ? 'unavailable' : 'mock',
    services: services(scenario),
    kpis: kpis(scenario),
    pendingApprovals: pendingApprovals(scenario),
    pendingApprovalsTotal:
      scenario === 'all-unknown' ? 0 : scenario === 'degraded' ? 17 : 3,
    events: events(scenario),
    emergencyActions: EMERGENCY_ACTIONS,
  };
  return assertFailClosedConsistency(snapshot);
}

/**
 * Read the active scenario from the environment.
 *
 * Defaults to `steady`; an unrecognised value falls back to `all-unknown` so a
 * typo can never render as a healthy dashboard (fail-closed).
 */
export function activeScenario(): Scenario {
  const raw = process.env.CP_DASHBOARD_SCENARIO;
  if (raw === undefined || raw === '' || raw === 'steady') return 'steady';
  if (raw === 'degraded') return 'degraded';
  if (raw === 'all-unknown') return 'all-unknown';
  return 'all-unknown';
}

/** The mock implementation of the swap seam. */
export function createMockDashboardSource(scenario: Scenario = 'steady'): DashboardDataSource {
  return {
    async load(): Promise<DashboardSnapshot> {
      return mockSnapshot(scenario);
    },
  };
}
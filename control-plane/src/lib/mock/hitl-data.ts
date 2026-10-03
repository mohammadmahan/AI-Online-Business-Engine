/**
 * Deterministic mock provider for the HITL review queue (D-171 §5.2, Phase 27.4).
 *
 * ── Boundaries ──────────────────────────────────────────────────────────────
 * This module makes ZERO external network calls, reads no credentials, and
 * mints no tokens. It returns fixed, hand-written tickets so the page
 * prerenders byte-identically on every build (no `Date.now()`, no
 * `Math.random()` — every instant below is a literal).
 *
 * The ticket vocabulary mirrors the canonical Phase 18 engine
 * (`local/canonical/hitl_contracts.py`): queue types, lifecycle states, roles
 * and the D-101 category taxonomy are the engine's own values, not UI
 * inventions. Values are samples and are labelled as such — a mocked approval
 * is not an approval.
 *
 * ── Fail-closed consistency guard ───────────────────────────────────────────
 * `mockQueue()` runs `assertHitlConsistency()` before returning. It rejects any
 * snapshot that would show a state the canonical engine cannot produce:
 *
 *   1. a ticket carrying a reviewer while PENDING_REVIEW (D-105 validation),
 *   2. a PENDING_REVIEW ticket missing its reviewer, or a terminal ticket with
 *      no reviewer and no EXPIRED status (D-105),
 *   3. an `enabled` action while `tokenPresent` is false — the UI cannot
 *      authorise anything without a single-use owner token (D-146/D-168),
 *   4. an `enabled` action with an empty `blockedReason`, and
 *   5. a queue whose summary counts disagree with its own tickets.
 *
 * ── Swap seam ───────────────────────────────────────────────────────────────
 * `createMockHitlSource()` returns the same `HitlQueueDataSource` interface the
 * real engine-backed source will implement.
 */

import type { Severity } from '@/types/dashboard';
import type {
  HitlActionSpec,
  HitlQueueDataSource,
  HitlQueueSnapshot,
  HitlQueueSummary,
  HitlSeverity,
  HitlTicket,
  PayloadField,
  QueueType,
  ResolutionStatus,
} from '@/types/hitl';

/** Named, deterministic scenarios. Default is `steady`. */
export type HitlScenario = 'steady' | 'busy' | 'all-unknown';

/** Fixed literal instant, so the static prerender is byte-stable. */
const MOCK_INSTANT = '2026-10-03T09:30:00.000Z';

/** A mock value is never evidence, so it never renders as PASS. */
const MOCK_DETAIL = 'داده‌ی نمونه — تصمیم‌گیری زنده انجام نشده است';

/** The canonical queue types (D-105). */
const QUEUE_TYPES: QueueType[] = [
  'INSIGHT_REVIEW',
  'PUBLISH_GATE',
  'ORDER_OVERRIDE',
  'ASSET_FLAG',
];

/** The canonical lifecycle states (D-105). */
const RESOLUTION_STATUSES: ResolutionStatus[] = [
  'PENDING_REVIEW',
  'CLAIMED',
  'APPROVED',
  'REJECTED',
  'MODIFIED',
  'ESCALATED',
  'EXPIRED',
];

/** Severity order for severity-first sorting. Higher index = more severe. */
const SEVERITY_ORDER: HitlSeverity[] = ['low', 'medium', 'high', 'critical'];

/**
 * Statuses that are terminal-but-decided. `EXPIRED` is deliberately separate:
 * it is the only terminal state a reviewer cannot reach (D-105), so it is the
 * only one allowed to have no reviewer.
 */
const DECIDED_STATUSES: ResolutionStatus[] = [
  'APPROVED',
  'REJECTED',
  'MODIFIED',
  'ESCALATED',
];

/**
 * Assert the snapshot cannot display a state the canonical engine forbids.
 *
 * Throwing is the fail-closed behaviour: a contradictory queue is never
 * rendered, rather than rendered with a reassuring badge.
 */
export function assertHitlConsistency(snapshot: HitlQueueSnapshot): HitlQueueSnapshot {
  const problems: string[] = [];

  for (const ticket of snapshot.tickets) {
    const id = ticket.ticket_id;

    if (ticket.resolution_status === 'PENDING_REVIEW' && ticket.reviewer_actor_id !== null) {
      problems.push(`${id}: PENDING_REVIEW must not carry a reviewer (D-105)`);
    }
    if (ticket.resolution_status === 'CLAIMED' && ticket.reviewer_actor_id === null) {
      problems.push(`${id}: CLAIMED requires a reviewer actor (D-105)`);
    }
    if (DECIDED_STATUSES.includes(ticket.resolution_status) && ticket.reviewer_actor_id === null) {
      problems.push(`${id}: ${ticket.resolution_status} requires a reviewer actor (D-105)`);
    }
    if (!QUEUE_TYPES.includes(ticket.queue_type)) {
      problems.push(`${id}: unknown queue_type ${ticket.queue_type} (D-105)`);
    }
    if (!RESOLUTION_STATUSES.includes(ticket.resolution_status)) {
      problems.push(`${id}: unknown resolution_status ${ticket.resolution_status} (D-105)`);
    }
    if (ticket.payload_ref.length === 0) {
      problems.push(`${id}: payload_ref must be non-empty (D-105)`);
    }
    if (ticket.reasoning.length === 0) {
      problems.push(`${id}: reasoning log must not be empty (D-027 rebuild)`);
    }
    if (ticket.ageLogical.length === 0) {
      problems.push(`${id}: ageLogical must not be empty`);
    }
  }

  for (const action of snapshot.actions) {
    if (action.enabled && !snapshot.tokenPresent) {
      problems.push(`${action.decision}: action enabled without an owner token (D-146/D-168)`);
    }
    if (action.enabled && action.blockedReason.length === 0) {
      problems.push(`${action.decision}: enabled action must not carry a blocked reason`);
    }
    if (!action.enabled && action.blockedReason.length === 0) {
      problems.push(`${action.decision}: disabled action must state why it is unavailable`);
    }
  }

  const expected = summarizeTickets(snapshot.tickets);
  if (snapshot.summary.total !== expected.total) {
    problems.push(`summary.total ${snapshot.summary.total} != ${expected.total} tickets`);
  }
  for (const severity of SEVERITY_ORDER) {
    if (snapshot.summary.bySeverity[severity] !== expected.bySeverity[severity]) {
      problems.push(
        `summary.bySeverity.${severity} ${snapshot.summary.bySeverity[severity]} != ` +
          `${expected.bySeverity[severity]}`,
      );
    }
  }

  if (problems.length > 0) {
    throw new Error(`fail-closed violation in HITL queue snapshot: ${problems.join('; ')}`);
  }
  return snapshot;
}

/** Count tickets by severity and status. The summary is derived, never typed twice. */
export function summarizeTickets(tickets: HitlTicket[]): HitlQueueSummary {
  const bySeverity = Object.fromEntries(
    SEVERITY_ORDER.map((severity) => [severity, 0]),
  ) as Record<HitlSeverity, number>;
  const byStatus = Object.fromEntries(
    RESOLUTION_STATUSES.map((status) => [status, 0]),
  ) as Record<ResolutionStatus, number>;

  for (const ticket of tickets) {
    bySeverity[ticket.severity] += 1;
    byStatus[ticket.resolution_status] += 1;
  }

  return {
    total: tickets.length,
    bySeverity,
    byStatus,
    hasCriticalPending: tickets.some(
      (ticket) =>
        ticket.severity === 'critical' && ticket.resolution_status === 'PENDING_REVIEW',
    ),
  };
}

/**
 * Severity-first ordering (D-171 §5.2).
 *
 * Within one severity, the OLDER ticket comes first, because the age is the
 * only ordering signal the engine guarantees. Ties break on `ticket_id` so the
 * order is deterministic rather than dependent on input order.
 */
export function sortBySeverityFirst(tickets: HitlTicket[]): HitlTicket[] {
  return [...tickets].sort((a, b) => {
    const severity =
      SEVERITY_ORDER.indexOf(b.severity) - SEVERITY_ORDER.indexOf(a.severity);
    if (severity !== 0) return severity;
    const age = b.created_at_logical.localeCompare(a.created_at_logical);
    if (age !== 0) return age;
    return a.ticket_id.localeCompare(b.ticket_id);
  });
}

/** A payload field that changes. */
function changed(field: string, before: string, after: string): PayloadField {
  return { field, before, after, changed: true };
}

/** A payload field shown for context but left unchanged. */
function unchanged(field: string, value: string): PayloadField {
  return { field, before: value, after: value, changed: false };
}

/** A reasoning step rebuilt from a D-027 event. */
function step(
  seq: number,
  atLogical: string,
  event: string,
  summary: string,
  traceId: string,
) {
  return { seq, atLogical, event, summary, traceId };
}

/**
 * The four one-click actions (D-171 §5.2).
 *
 * Every action is DISABLED in this phase, and each states its own reason. The
 * UI never mints a token and holds no signing key (D-146), so an enabled
 * action would be a control that looks live but cannot authorise anything —
 * exactly the anti-pattern D-171 §6 forbids.
 */
const NO_TOKEN_REASON =
  'توکن یک‌بارمصرف مالک در رابط ساخته نمی‌شود (D-146)؛ تا اتصال موتور HITL کنش غیرفعال است';

const ACTIONS: HitlActionSpec[] = [
  {
    decision: 'APPROVED',
    title: 'تأیید',
    description: 'پیشنهاد بدون تغییر اعمال می‌شود و از مسیر dispatcher به مصرف‌کننده می‌رسد (D-107)',
    requiresSecondConfirmation: false,
    enabled: false,
    blockedReason: NO_TOKEN_REASON,
  },
  {
    decision: 'MODIFIED',
    title: 'اصلاح',
    description: 'مقدار پیشنهادی با override بازبین جایگزین و سپس اعمال می‌شود (D-105)',
    requiresSecondConfirmation: false,
    enabled: false,
    blockedReason: NO_TOKEN_REASON,
  },
  {
    decision: 'REJECTED',
    title: 'رد',
    description: 'پیشنهاد رد می‌شود؛ هیچ کنشی روی سیستم مقصد اجرا نمی‌شود',
    requiresSecondConfirmation: false,
    enabled: false,
    blockedReason: NO_TOKEN_REASON,
  },
  {
    decision: 'ESCALATED',
    title: 'ارجاع',
    description: 'تیکت با نقش بالاتر به‌صورت PENDING_REVIEW تازه دوباره در صف قرار می‌گیرد (D-105)',
    // Escalation re-queues work for a higher role — a state mutation (D-107),
    // so it needs the second confirmation the spec requires.
    requiresSecondConfirmation: true,
    enabled: false,
    blockedReason: NO_TOKEN_REASON,
  },
];

/** The pending tickets that carry the queue in the `steady` scenario. */
const STEADY_TICKETS: HitlTicket[] = [
  {
    ticket_id: 'HITL-2401',
    queue_type: 'ORDER_OVERRIDE',
    severity: 'critical',
    category: 'inventory_velocity',
    categoryLabel: 'سرعت موجودی',
    payload_ref: 'insight:sha256:3f9a1c07e5b2',
    required_role: 'owner',
    resolution_status: 'PENDING_REVIEW',
    reviewer_actor_id: null,
    created_at_logical: 'L-0000000000000090',
    ageLogical: '۲ دقیقه',
    summary: 'کاهش ۳۸٪ قیمت پیشنهادی برای ۴ SKU — اثر مستقیم روی حاشیه‌ی سود',
    source: 'analyst:inventory_velocity',
    payload: [
      changed('price_toman', '4,250,000', '2,635,000'),
      changed('discount_percent', '0', '38'),
      unchanged('sku_count', '4'),
    ],
    reasoning: [
      step(
        1,
        'L-0000000000000088',
        'insight.generated',
        'بینش از افت نرخ گردش موجودی در بازه‌ی ۷ روزه ساخته شد',
        'trace-4a12b9c3',
      ),
      step(
        2,
        'L-0000000000000089',
        'insight.dispatched_to_hitl',
        'شدت CRITICAL است و ساختاراً قابل پذیرش خودکار نیست (D-104)',
        'trace-4a12b9c4',
      ),
      step(
        3,
        'L-0000000000000090',
        'hitl.ticket.created',
        'تیکت با نقش لازم owner در صف ثبت شد (D-105)',
        'trace-4a12b9c5',
      ),
    ],
  },
  {
    ticket_id: 'HITL-2398',
    queue_type: 'ORDER_OVERRIDE',
    severity: 'high',
    category: 'inventory_velocity',
    categoryLabel: 'سرعت موجودی',
    payload_ref: 'insight:sha256:8b41d2fa09c7',
    required_role: 'ops',
    resolution_status: 'CLAIMED',
    reviewer_actor_id: 'role:ops',
    created_at_logical: 'L-0000000000000072',
    ageLogical: '۱۴ دقیقه',
    summary: 'بازنشانی موجودی انبار مرکزی به صفر برای توقف فروش بیش از موجودی',
    source: 'analyst:inventory_velocity',
    payload: [
      changed('central_stock', '18', '0'),
      unchanged('restock_eta_days', '3'),
    ],
    reasoning: [
      step(
        1,
        'L-0000000000000070',
        'insight.generated',
        'ناهم‌خوانی موجودی با سفارش‌های تأییدنشده شناسایی شد',
        'trace-7c30e1aa',
      ),
      step(
        2,
        'L-0000000000000071',
        'insight.dispatched_to_hitl',
        'شدت HIGH نیازمند بازبینی انسانی است (D-104)',
        'trace-7c30e1ab',
      ),
      step(
        3,
        'L-0000000000000072',
        'hitl.ticket.claimed',
        'بازبین ops تیکت را قفل کرد؛ در این حالت تنها یک برنده وجود دارد (D-106)',
        'trace-7c30e1ac',
      ),
    ],
  },
  {
    ticket_id: 'HITL-2395',
    queue_type: 'PUBLISH_GATE',
    severity: 'medium',
    category: 'content_performance',
    categoryLabel: 'عملکرد محتوا',
    payload_ref: 'slot:publish:2026-10-03:07',
    required_role: 'publisher',
    resolution_status: 'PENDING_REVIEW',
    reviewer_actor_id: null,
    created_at_logical: 'L-0000000000000055',
    ageLogical: '۳۱ دقیقه',
    summary: 'انتشار پیش‌نویس توضیحات محصول در بازه‌ی بعدی — نیازمند تأیید ناشر',
    source: 'publisher:slot_gate',
    payload: [
      changed('slot_state', 'BLOCKED', 'OPEN'),
      unchanged('channel', 'web_store'),
    ],
    reasoning: [
      step(
        1,
        'L-0000000000000054',
        'slot.gate.blocked',
        'بازه‌ی انتشار به دلیل نبود تأیید انسانی قفل شد',
        'trace-1d55f8e2',
      ),
      step(
        2,
        'L-0000000000000055',
        'hitl.ticket.created',
        'تیکت با نقش لازم publisher در صف ثبت شد (D-105)',
        'trace-1d55f8e3',
      ),
    ],
  },
  {
    ticket_id: 'HITL-2390',
    queue_type: 'INSIGHT_REVIEW',
    severity: 'medium',
    category: 'sales_performance',
    categoryLabel: 'عملکرد فروش',
    payload_ref: 'insight:sha256:c20b7e4415aa',
    required_role: 'any',
    resolution_status: 'PENDING_REVIEW',
    reviewer_actor_id: null,
    created_at_logical: 'L-0000000000000041',
    ageLogical: '۵۲ دقیقه',
    summary: 'پیشنهاد توقف کمپین کم‌بازده بر پایه‌ی نرخ تبدیل ۰٫۴٪',
    source: 'analyst:sales_performance',
    payload: [
      changed('campaign_state', 'RUNNING', 'PAUSED'),
      unchanged('conversion_percent', '0.4'),
    ],
    reasoning: [
      step(
        1,
        'L-0000000000000039',
        'insight.generated',
        'نرخ تبدیل زیر آستانه‌ی تعریف‌شده اندازه‌گیری شد',
        'trace-9e07bb41',
      ),
      step(
        2,
        'L-0000000000000041',
        'insight.dispatched_to_hitl',
        'پیشنهاد تغییر وضعیت کمپین است و نیازمند تأیید انسانی است',
        'trace-9e07bb42',
      ),
    ],
  },
  {
    ticket_id: 'HITL-2384',
    queue_type: 'ASSET_FLAG',
    severity: 'low',
    category: 'campaign_attribution',
    categoryLabel: 'اسناد کمپین',
    payload_ref: 'asset:flag:img-2291',
    required_role: 'any',
    resolution_status: 'APPROVED',
    reviewer_actor_id: 'role:publisher',
    created_at_logical: 'L-0000000000000020',
    ageLogical: '۲ ساعت',
    summary: 'نشان‌گذاری دارایی تصویری به‌عنوان نامعتبر — تأییدشده توسط ناشر',
    source: 'assets:flag_producer',
    payload: [changed('asset_state', 'ACTIVE', 'FLAGGED')],
    reasoning: [
      step(
        1,
        'L-0000000000000019',
        'hitl.ticket.created',
        'تیکت نشان‌گذاری دارایی در صف ثبت شد (D-105)',
        'trace-33ba0f11',
      ),
      step(
        2,
        'L-0000000000000020',
        'hitl.ticket.approved',
        'بازبین publisher تصمیم APPROVED را ثبت کرد و لجر زنجیره‌ای شد (D-108)',
        'trace-33ba0f12',
      ),
    ],
  },
  {
    ticket_id: 'HITL-2379',
    queue_type: 'PUBLISH_GATE',
    severity: 'low',
    category: 'scheduling_density',
    categoryLabel: 'تراکم زمان‌بندی',
    payload_ref: 'slot:publish:2026-10-02:19',
    required_role: 'publisher',
    resolution_status: 'EXPIRED',
    reviewer_actor_id: null,
    created_at_logical: 'L-0000000000000004',
    ageLogical: '۱۹ ساعت',
    summary: 'بازه‌ی انتشار منقضی شد — فقط sweep قطعی می‌تواند EXPIRED ثبت کند (D-105)',
    source: 'publisher:slot_gate',
    payload: [unchanged('slot_state', 'BLOCKED')],
    reasoning: [
      step(
        1,
        'L-0000000000000003',
        'hitl.ticket.created',
        'تیکت بازه‌ی انتشار در صف ثبت شد (D-105)',
        'trace-58cc72d0',
      ),
      step(
        2,
        'L-0000000000000004',
        'hitl.ticket.expired',
        'sweep قطعی با ساعت منطقی تزریق‌شده تیکت را منقضی کرد — نه کنش بازبین',
        'trace-58cc72d1',
      ),
    ],
  },
];

/** Extra pending tickets for the `busy` scenario, so the queue is clearly loaded. */
const BUSY_TICKETS: HitlTicket[] = [
  {
    ticket_id: 'HITL-2403',
    queue_type: 'INSIGHT_REVIEW',
    severity: 'critical',
    category: 'sales_performance',
    categoryLabel: 'عملکرد فروش',
    payload_ref: 'insight:sha256:aa17f0c93b21',
    required_role: 'owner',
    resolution_status: 'PENDING_REVIEW',
    reviewer_actor_id: null,
    created_at_logical: 'L-0000000000000092',
    ageLogical: '۱ دقیقه',
    summary: 'افت ناگهانی نرخ تبدیل در کانال اینستاگرام — ۶۲٪ زیر خط پایه',
    source: 'analyst:sales_performance',
    payload: [
      changed('channel_state', 'ACTIVE', 'THROTTLED'),
      unchanged('baseline_percent', '1.9'),
    ],
    reasoning: [
      step(
        1,
        'L-0000000000000091',
        'insight.generated',
        'انحراف معنادار از خط پایه در پنجره‌ی ۲۴ ساعته اندازه‌گیری شد',
        'trace-b104ea77',
      ),
      step(
        2,
        'L-0000000000000092',
        'insight.dispatched_to_hitl',
        'شدت CRITICAL است و پذیرش خودکار ساختاراً ممکن نیست (D-104)',
        'trace-b104ea78',
      ),
    ],
  },
  {
    ticket_id: 'HITL-2402',
    queue_type: 'ASSET_FLAG',
    severity: 'high',
    category: 'content_performance',
    categoryLabel: 'عملکرد محتوا',
    payload_ref: 'asset:flag:vid-4417',
    required_role: 'ops',
    resolution_status: 'PENDING_REVIEW',
    reviewer_actor_id: null,
    created_at_logical: 'L-0000000000000086',
    ageLogical: '۶ دقیقه',
    summary: 'نشان‌گذاری دارایی ویدیویی مشکوک به نقض حق تکثیر',
    source: 'assets:flag_producer',
    payload: [changed('asset_state', 'ACTIVE', 'FLAGGED')],
    reasoning: [
      step(
        1,
        'L-0000000000000085',
        'asset.scan.flagged',
        'اسکن دارایی الگوی مشکوک را علامت زد',
        'trace-6f2c19b4',
      ),
      step(
        2,
        'L-0000000000000086',
        'hitl.ticket.created',
        'تیکت با نقش لازم ops در صف ثبت شد (D-105)',
        'trace-6f2c19b5',
      ),
    ],
  },
  {
    ticket_id: 'HITL-2400',
    queue_type: 'ORDER_OVERRIDE',
    severity: 'medium',
    category: 'inventory_velocity',
    categoryLabel: 'سرعت موجودی',
    payload_ref: 'insight:sha256:d41ba9037c55',
    required_role: 'ops',
    resolution_status: 'ESCALATED',
    reviewer_actor_id: 'role:ops',
    created_at_logical: 'L-0000000000000078',
    ageLogical: '۱۱ دقیقه',
    summary: 'ارجاع به نقش بالاتر برای تصمیم درباره‌ی جبران سفارش ناقص (D-105)',
    source: 'analyst:inventory_velocity',
    payload: [changed('compensation_state', 'PENDING', 'PROPOSED')],
    reasoning: [
      step(
        1,
        'L-0000000000000077',
        'hitl.ticket.claimed',
        'بازبین ops تیکت را قفل کرد؛ تنها یک برنده ممکن است (D-106)',
        'trace-2ae90c31',
      ),
      step(
        2,
        'L-0000000000000078',
        'hitl.ticket.escalated',
        'ارجاع ثبت شد؛ تیکت تازه با نقش بالاتر در صف قرار می‌گیرد',
        'trace-2ae90c32',
      ),
    ],
  },
];

/** Tickets for a scenario, already severity-sorted. */
function tickets(scenario: HitlScenario): HitlTicket[] {
  if (scenario === 'all-unknown') return [];
  const base = scenario === 'busy' ? [...BUSY_TICKETS, ...STEADY_TICKETS] : STEADY_TICKETS;
  return sortBySeverityFirst(base);
}

/** Build the full snapshot for a scenario, guarded for fail-closed consistency. */
export function mockQueue(scenario: HitlScenario = 'steady'): HitlQueueSnapshot {
  const rows = tickets(scenario);
  const snapshot: HitlQueueSnapshot = {
    generatedAt: MOCK_INSTANT,
    scenario,
    provenance: scenario === 'all-unknown' ? 'unavailable' : 'mock',
    tickets: rows,
    summary: summarizeTickets(rows),
    // No token is minted in this phase, so every action must be disabled —
    // the guard below enforces that pairing.
    actions: ACTIONS,
    tokenPresent: false,
  };
  return assertHitlConsistency(snapshot);
}

/**
 * Read the active scenario from the environment.
 *
 * Defaults to `steady`; an unrecognised value falls back to `all-unknown`, so a
 * typo can never render as a loaded queue (fail-closed).
 */
export function activeHitlScenario(): HitlScenario {
  const raw = process.env.CP_HITL_SCENARIO;
  if (raw === undefined || raw === '' || raw === 'steady') return 'steady';
  if (raw === 'busy') return 'busy';
  return 'all-unknown';
}

/** The mock implementation of the swap seam. */
export function createMockHitlSource(scenario: HitlScenario = 'steady'): HitlQueueDataSource {
  return {
    async load(): Promise<HitlQueueSnapshot> {
      return mockQueue(scenario);
    },
  };
}

/** Persian provenance note for the queue page. */
export function hitlProvenanceNote(scenario: string, provenance: HitlQueueSnapshot['provenance']): string {
  if (provenance === 'unavailable') {
    return `هیچ تیکتی بارگذاری نشده است؛ صف به موتور HITL متصل نیست. سناریو: ${scenario}`;
  }
  return `${MOCK_DETAIL}؛ صف از داده‌ی نمونه پر شده است. سناریو: ${scenario}`;
}

/** Severity → Persian label and English code, shared by the queue components. */
export const SEVERITY_LABEL: Record<Severity, { label: string; code: string }> = {
  critical: { label: 'بحرانی', code: 'CRITICAL' },
  high: { label: 'بالا', code: 'HIGH' },
  medium: { label: 'متوسط', code: 'MEDIUM' },
  low: { label: 'پایین', code: 'LOW' },
};

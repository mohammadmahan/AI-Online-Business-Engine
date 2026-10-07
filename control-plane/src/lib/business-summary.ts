/**
 * D-171 §2.3 الف / §10 — Phase 27.12 aggregated Business cards.
 *
 * One pure module turns each page's EXISTING snapshot into the plain-Persian
 * summary the shop owner reads at the top of `/dashboard`, `/automations`,
 * `/hitl-queue`, `/orders` and `/inventory`. It adds no data source, performs
 * no fetch and holds no state: every number below is derived from the snapshot
 * the page already loaded, so a card can never disagree with the page beneath
 * it.
 *
 * ── Fail-closed rules this module enforces ──────────────────────────────────
 * 1. A `success` status requires a LIVE reading. Mock or unavailable data may
 *    show counts, but the aggregate can never be green (D-171 §2.2) — and when
 *    the data is not live the headline says so in words («بر پایهٔ دادهٔ
 *    نمونه…»), not only in a colour.
 * 2. A card whose data is unavailable says «بدون داده» and never zero: an
 *    unreachable source is not a store with nothing to do.
 * 3. `assertBusinessCard()` rejects, at render time, any card that carries
 *    operational jargon (پروب/سایدکار/کانتینر/تلمتری/لجر/HTTP/latency/D-121)
 *    or a cutover gate id (`V-01`…`V-10` — console-only assets), no metric, an
 *    empty string, or a green status without live evidence. A Business card is
 *    therefore structurally incapable of leaking the technical vocabulary the
 *    Technical console owns (§2.3 الف).
 *
 *    `SKU` (شناسه کالا / Stock Keeping Unit) is NOT jargon — the owner ruled
 *    it approved canonical commerce vocabulary, readable in Business cards and
 *    tables (owner ruling 2026-10-07; D-171 row 72).
 *
 * Counts are rendered in Persian digits (Phase 27.12 directive); identifiers,
 * SKU and timestamps keep Latin digits (D-171 §3.1).
 */

import type { CommerceSnapshot } from '@/types/commerce';
import type { KpiCard, DashboardSnapshot } from '@/types/dashboard';
import type { HitlQueueSnapshot } from '@/types/hitl';
import type { InventorySnapshot } from '@/types/inventory';
import type { TelemetrySnapshot } from '@/types/telemetry';

import { formatCountFa, formatTimeUtc } from '@/lib/format';
import { summarize } from '@/lib/telemetry';

/** Card tone vocabulary — identical to `Tone` in `components/ui/tone-badge`. */
export type BusinessTone = 'neutral' | 'success' | 'warning' | 'danger';

export interface BusinessMetric {
  /** Plain-Persian label; never an operational identifier. */
  label: string;
  /** Pre-formatted value (Persian digits for counts). */
  value: string;
  /** One plain sentence explaining what the value counts (27.11 tooltip). */
  tip: string;
}

export interface BusinessCardModel {
  /** Stable per-page id, used for unique tooltip/heading ids. */
  id: string;
  title: string;
  /** One plain-Persian sentence summarising the whole page. */
  headline: string;
  status: { tone: BusinessTone; label: string; code: string };
  provenance: { tone: BusinessTone; label: string; code: string };
  metrics: BusinessMetric[];
  drillDown: { label: string; tip: string };
}

const PROVENANCE = {
  live: { tone: 'success', label: 'خوانش زنده', code: 'LIVE' },
  mock: { tone: 'warning', label: 'دادهٔ نمونه', code: 'MOCK' },
  unavailable: { tone: 'danger', label: 'بدون داده', code: 'NO_DATA' },
} as const satisfies Record<'live' | 'mock' | 'unavailable', BusinessCardModel['provenance']>;

const STATUS = {
  ok: { tone: 'success', label: 'عادی', code: 'OK' },
  review: { tone: 'warning', label: 'نیازمند بررسی', code: 'REVIEW' },
  action: { tone: 'danger', label: 'نیازمند اقدام', code: 'ACTION' },
  processing: { tone: 'warning', label: 'در حال پردازش', code: 'PROCESSING' },
  unknown: { tone: 'neutral', label: 'نامشخص', code: 'UNKNOWN' },
  noData: { tone: 'danger', label: 'بدون داده', code: 'NO_DATA' },
} as const satisfies Record<string, BusinessCardModel['status']>;

/**
 * The drill-down bridge (§2.3 ج). One shared action: it switches the view on
 * the SAME page — no navigation, no reload — and the view switch keeps the
 * scroll position.
 */
const DRILL_DOWN = {
  label: 'مشاهده جزئیات زیرساخت و لاگ‌های زنده',
  tip: 'نمای همین صفحه را به کنسول فنی می‌برد؛ آدرس صفحه و جای اسکرول عوض نمی‌شود و صفحه دوباره بارگذاری نمی‌شود.',
} as const;

/**
 * Operational vocabulary that must never appear on a Business card.
 *
 * `SKU` is deliberately absent: the owner ruled it approved canonical commerce
 * vocabulary (شناسه کالا / Stock Keeping Unit) that a shop owner reads as their
 * own word for a product identifier, on a card or in a table alike (owner
 * ruling 2026-10-07; D-171 row 72). Everything else here stays console-only,
 * including the V-01…V-10 cutover gate ids — the census already classifies gate
 * ids as console-only assets (`check-view-isolation.mjs`), so a gate id on a
 * Business card is a leak the card guard must reject too.
 */
const FORBIDDEN = /(پروب|سایدکار|کانتینر|تلمتری|لجر|HTTP|latency|D-121|sidecar|V-\d{2})/i;

/**
 * Fail-closed guard, in the same spirit as the mock providers' consistency
 * guards: a contradictory or jargon-carrying card is never rendered.
 */
export function assertBusinessCard(model: BusinessCardModel): BusinessCardModel {
  const problems: string[] = [];
  const strings = [
    model.title,
    model.headline,
    model.status.label,
    model.status.code,
    model.provenance.label,
    model.provenance.code,
    model.drillDown.label,
    model.drillDown.tip,
    ...model.metrics.flatMap((metric) => [metric.label, metric.value, metric.tip]),
  ];

  for (const value of strings) {
    if (value.trim().length === 0) problems.push('empty string on a card');
    const jargon = value.match(FORBIDDEN);
    if (jargon) problems.push(`operational jargon "${jargon[0]}" in: ${value}`);
  }
  if (model.metrics.length === 0) problems.push('card carries no metric');
  if (model.status.tone === 'success' && model.provenance.code !== 'LIVE') {
    problems.push('green status without a live reading (D-171 §2.2)');
  }
  if (model.provenance.code === 'NO_DATA' && model.status.code !== 'NO_DATA') {
    problems.push('unavailable data must be reported as «بدون داده»');
  }

  if (problems.length > 0) {
    throw new Error(`fail-closed violation in business card: ${problems.join('; ')}`);
  }
  return model;
}

/** KPI values are pre-formatted strings; only a digits-only value is a count. */
function numericKpiValue(kpi: KpiCard | undefined): number | null {
  if (kpi === undefined) return null;
  const digits = kpi.value.replace(/[٬,]/g, '').trim();
  if (!/^-?\d+$/.test(digits)) return null;
  return Number(digits);
}

/** Latest ISO-8601 instant in a list, or `null` when there is none. */
function latestInstant(instants: readonly string[]): string | null {
  let latest: string | null = null;
  for (const instant of instants) {
    if (latest === null || instant > latest) latest = instant;
  }
  return latest;
}

/** `HH:MM` UTC with Latin digits — timestamps are data, not narrative (§3.1). */
function clock(instant: string | null): string {
  return instant === null ? 'نامشخص' : `${formatTimeUtc(instant)} UTC`;
}

/** `/dashboard` — executive overview (D-171 §5.1). */
export function dashboardBusinessCard(snapshot: DashboardSnapshot): BusinessCardModel {
  const summary = summarize(snapshot.services);
  const pending = snapshot.pendingApprovalsTotal;
  const orders = numericKpiValue(snapshot.kpis.find((kpi) => kpi.id === 'orders_revenue'));
  const needsReview = summary.degraded + summary.unavailable + summary.unknown;

  // No source at all outranks every component state: the card says «بدون داده»
  // rather than reporting a component summary it cannot substantiate.
  const status =
    snapshot.provenance === 'unavailable'
      ? STATUS.noData
      : summary.worst === 'degraded'
        ? STATUS.action
        : summary.worst === 'unavailable'
          ? STATUS.review
          : summary.worst === 'unknown'
            ? STATUS.unknown
            : snapshot.provenance === 'live'
              ? STATUS.ok
              : STATUS.unknown;

  const headline =
    snapshot.provenance === 'unavailable'
      ? 'وضعیت فروشگاه: بدون داده — هیچ منبعی به فروشگاه متصل نیست.'
      : summary.worst === 'degraded'
        ? 'وضعیت فروشگاه: بخشی از فروشگاه به توجه شما نیاز دارد.'
        : summary.worst === 'ok' && status.code === 'OK'
          ? 'وضعیت فروشگاه: آماده و پایدار.'
          : status.code === 'UNKNOWN'
            ? 'وضعیت فروشگاه: نامشخص — تا خوانش زنده، هیچ وضعیتی «سالم» اعلام نمی‌شود.'
            : 'وضعیت فروشگاه: بخشی هنوز متصل نشده و نیازمند بررسی است.';

  return assertBusinessCard({
    id: 'dashboard',
    title: 'وضعیت فروشگاه در یک نگاه',
    headline,
    status,
    provenance: PROVENANCE[snapshot.provenance],
    metrics: [
      {
        label: 'سفارش‌های امروز',
        value: orders === null ? 'نامشخص' : formatCountFa(orders),
        tip: 'تعداد سفارش‌هایی که امروز ثبت شده‌اند.',
      },
      {
        label: 'کارهای در انتظار تصمیم شما',
        value: formatCountFa(pending),
        tip: 'کارهایی که ربات نمی‌تواند تنهایی دربارهٔ آن‌ها تصمیم بگیرد.',
      },
      {
        label: 'بخش‌های آمادهٔ فروشگاه',
        value: `${formatCountFa(summary.ok)} از ${formatCountFa(summary.total)}`,
        tip: 'تعداد بخش‌هایی که فروشگاه برای کار کردن به آن‌ها تکیه دارد و همین حالا پاسخ می‌دهند.',
      },
      {
        label: 'بخش‌های نیازمند بررسی',
        value: formatCountFa(needsReview),
        tip: 'بخش‌هایی که پاسخ نمی‌دهند یا وضعیتشان روشن نیست و باید بررسی شوند.',
      },
    ],
    drillDown: DRILL_DOWN,
  });
}

/** `/automations` — automation health (D-171 §5.4). */
export function automationsBusinessCard(snapshot: TelemetrySnapshot): BusinessCardModel {
  const summary = snapshot.summary;
  const active = summary.containersHealthy;
  const needsReview =
    summary.containersDegraded + summary.containersDown + summary.containersUnknown;
  const checksWaiting =
    summary.gatesBlocked + summary.gatesEvaluating + summary.gatesBypassPrevented;

  // The live route reports `unavailable` when no probe produced a reading (the
  // sidecar is down): that outranks the per-surface states, exactly as the
  // page's own notice does — never a reassuring per-component summary.
  const status =
    snapshot.provenance === 'unavailable'
      ? STATUS.noData
      : summary.worstContainer === 'DOWN'
        ? STATUS.action
        : summary.worstContainer === 'DEGRADED'
          ? STATUS.review
          : summary.worstContainer === 'UNKNOWN'
            ? STATUS.unknown
            : snapshot.sourceMode === 'LIVE' && checksWaiting === 0
              ? STATUS.ok
              : STATUS.unknown;

  const headline =
    snapshot.provenance === 'unavailable'
      ? 'کارهای خودکار فروشگاه: بدون داده — هیچ جریانی خوانده نشده است.'
      : `کارهای خودکار فروشگاه: ${formatCountFa(active)} ربات فعال${
          needsReview > 0 ? ` و ${formatCountFa(needsReview)} ربات نیازمند بررسی` : ''
        }.`;

  return assertBusinessCard({
    id: 'automations',
    title: 'خلاصهٔ کارهای خودکار',
    headline,
    status,
    provenance: PROVENANCE[snapshot.provenance],
    metrics: [
      {
        label: 'ربات‌های فعال',
        value: formatCountFa(active),
        tip: 'ربات‌هایی که همین حالا سالم کار می‌کنند و کارهای فروشگاه را انجام می‌دهند.',
      },
      {
        label: 'ربات‌های نیازمند بررسی',
        value: formatCountFa(needsReview),
        tip: 'ربات‌هایی که پاسخ نمی‌دهند یا وضعیتشان روشن نیست و باید بررسی شوند.',
      },
      {
        label: 'کنترل‌های کیفیت تأییدشده',
        value: formatCountFa(summary.gatesPass),
        tip: 'بررسی‌های اجباری فروشگاه که با مدرک تأیید شده‌اند.',
      },
      {
        label: 'کنترل‌های در انتظار',
        value: formatCountFa(checksWaiting),
        tip: 'بررسی‌هایی که هنوز تأیید نشده‌اند و کارهای فروشگاه را متوقف می‌کنند.',
      },
    ],
    drillDown: DRILL_DOWN,
  });
}

/** `/hitl-queue` — human review queue (D-171 §5.2). */
export function hitlBusinessCard(snapshot: HitlQueueSnapshot): BusinessCardModel {
  const byStatus = snapshot.summary.byStatus;
  const pending = byStatus.PENDING_REVIEW;
  const claimed = byStatus.CLAIMED;
  const decided = byStatus.APPROVED + byStatus.REJECTED + byStatus.MODIFIED;
  const unavailable = snapshot.provenance === 'unavailable';

  const status = unavailable
    ? STATUS.noData
    : snapshot.summary.hasCriticalPending
      ? STATUS.action
      : pending > 0
        ? STATUS.review
        : snapshot.provenance === 'live'
          ? STATUS.ok
          : STATUS.unknown;

  const headline = unavailable
    ? 'کارهای نیازمند تأیید: بدون داده — صف به موتور تأیید متصل نیست.'
    : pending === 0
      ? 'کارهای نیازمند تأیید: هیچ کاری در انتظار تصمیم شما نیست.'
      : `کارهای نیازمند تأیید: ${formatCountFa(pending)} کار منتظر تصمیم شماست${
          snapshot.summary.hasCriticalPending ? ' — دست‌کم یکی فوری است' : ''
        }.`;

  return assertBusinessCard({
    id: 'hitl',
    title: 'خلاصهٔ کارهای نیازمند تأیید',
    headline,
    status,
    provenance: PROVENANCE[snapshot.provenance],
    metrics: [
      {
        label: 'در انتظار تصمیم شما',
        value: formatCountFa(pending),
        tip: 'کارهایی که ربات نمی‌تواند تنهایی تصمیم بگیرد و منتظر تصمیم شماست.',
      },
      {
        label: 'در حال بررسی',
        value: formatCountFa(claimed),
        tip: 'کارهایی که یک همکار آن‌ها را برداشته و همین حالا رویشان کار می‌کند.',
      },
      {
        label: 'تصمیم‌گرفته‌شده',
        value: formatCountFa(decided),
        tip: 'کارهایی که تأیید، اصلاح یا رد شده‌اند.',
      },
      {
        label: 'مهلت‌گذشته',
        value: formatCountFa(byStatus.EXPIRED),
        tip: 'کارهایی که زمان بررسیشان گذشت و بدون تصمیم بسته شدند.',
      },
    ],
    drillDown: DRILL_DOWN,
  });
}

/** `/orders` — commerce summary (D-171 §5.6). */
export function ordersBusinessCard(snapshot: CommerceSnapshot): BusinessCardModel {
  const summary = snapshot.summary;
  const unavailable = snapshot.provenance === 'unavailable';
  const lastChange = latestInstant(snapshot.orders.map((order) => order.lastUpdateUtc));

  const status = unavailable
    ? STATUS.noData
    : summary.failedPaymentCount > 0
      ? STATUS.action
      : summary.pendingProcessingCount > 0
        ? STATUS.processing
        : snapshot.provenance === 'live'
          ? STATUS.ok
          : STATUS.unknown;

  const headline = unavailable
    ? 'سفارش‌ها: بدون داده — دفتر سفارش‌ها به هیچ منبعی متصل نیست.'
    : summary.failedPaymentCount > 0
      ? `سفارش‌ها: ${formatCountFa(summary.failedPaymentCount)} پرداخت ناموفق نیازمند پیگیری است.`
      : summary.pendingProcessingCount > 0
        ? `سفارش‌ها: ${formatCountFa(summary.pendingProcessingCount)} سفارش در حال آماده‌سازی است.`
        : snapshot.provenance === 'live'
          ? 'سفارش‌ها: هیچ سفارشی در انتظار آماده‌سازی نیست.'
          : 'سفارش‌ها: بر پایهٔ دادهٔ نمونه، هیچ سفارشی در انتظار آماده‌سازی نیست.';

  return assertBusinessCard({
    id: 'orders',
    title: 'خلاصهٔ سفارش‌ها و پرداخت',
    headline,
    status,
    provenance: PROVENANCE[snapshot.provenance],
    metrics: [
      {
        label: 'در حال آماده‌سازی',
        value: formatCountFa(summary.pendingProcessingCount),
        tip: 'سفارش‌هایی که ثبت شده‌اند و هنوز آمادهٔ ارسال نشده‌اند.',
      },
      {
        label: 'تکمیل‌شده',
        value: formatCountFa(summary.completedOrderCount),
        tip: 'سفارش‌هایی که تا پایان مراحل آماده‌سازی و ارسال پیش رفته‌اند.',
      },
      {
        label: 'پرداخت ناموفق',
        value: formatCountFa(summary.failedPaymentCount),
        tip: 'سفارش‌هایی که پرداختشان انجام نشده و باید با مشتری پیگیری شوند.',
      },
      {
        label: 'آخرین تغییر سفارش‌ها',
        value: clock(lastChange),
        tip: 'ساعت آخرین به‌روزرسانی سفارش‌ها (به وقت جهانی).',
      },
    ],
    drillDown: DRILL_DOWN,
  });
}

/** `/inventory` — stock summary (D-171 §5.3). */
export function inventoryBusinessCard(snapshot: InventorySnapshot): BusinessCardModel {
  const summary = snapshot.summary;
  const unavailable = snapshot.provenance === 'unavailable';
  const needsAttention = summary.outOfStockCount + summary.driftCount + summary.syncErrorCount;
  const pendingSync = summary.pendingSyncCount + summary.syncErrorCount;

  const status = unavailable
    ? STATUS.noData
    : needsAttention > 0
      ? STATUS.action
      : summary.lowStockCount > 0 || summary.pendingSyncCount > 0
        ? STATUS.review
        : snapshot.provenance === 'live'
          ? STATUS.ok
          : STATUS.unknown;

  const headline = unavailable
    ? 'انبار و محصولات: بدون داده — فهرست کالاها به هیچ منبعی متصل نیست.'
    : summary.outOfStockCount > 0
      ? `انبار و محصولات: ${formatCountFa(summary.outOfStockCount)} کالا تمام شده${
          summary.lowStockCount > 0
            ? ` و ${formatCountFa(summary.lowStockCount)} کالا رو به اتمام است`
            : ' است'
        }.`
      : summary.lowStockCount > 0
        ? `انبار و محصولات: ${formatCountFa(summary.lowStockCount)} کالا رو به اتمام است.`
        : snapshot.provenance === 'live'
          ? 'انبار و محصولات: موجودی همهٔ کالاها کافی است.'
          : 'انبار و محصولات: بر پایهٔ دادهٔ نمونه، موجودی همهٔ کالاها کافی است.';

  return assertBusinessCard({
    id: 'inventory',
    title: 'خلاصهٔ انبار و محصولات',
    headline,
    status,
    provenance: PROVENANCE[snapshot.provenance],
    metrics: [
      {
        label: 'کالاهای رو به اتمام',
        value: formatCountFa(summary.lowStockCount),
        tip: 'کالاهایی که موجودی‌شان به حد هشدار رسیده و باید سفارش شوند.',
      },
      {
        label: 'کالاهای تمام‌شده',
        value: formatCountFa(summary.outOfStockCount),
        tip: 'کالاهایی که موجودی‌شان صفر است و فروش آن‌ها متوقف شده.',
      },
      {
        label: 'مغایرت با فروشگاه آنلاین',
        value: formatCountFa(summary.driftCount),
        tip: 'کالاهایی که قیمت یا موجودی‌شان با فروشگاه آنلاین اختلاف دارد و باید دستی بررسی شود.',
      },
      {
        label: 'همگام‌سازی‌های در انتظار',
        value: formatCountFa(pendingSync),
        tip: 'تغییراتی که هنوز با فروشگاه آنلاین هم‌خوان نشده‌اند.',
      },
      {
        label: 'آخرین تصویر موجودی',
        value: clock(snapshot.generatedAt),
        tip: 'ساعت آخرین تصویری که از انبار گرفته شده (به وقت جهانی).',
      },
    ],
    drillDown: DRILL_DOWN,
  });
}

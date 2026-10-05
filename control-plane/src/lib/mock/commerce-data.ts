/**
 * Deterministic mock provider for commerce, orders and revenue (D-171 §5.6,
 * Phase 27.8).
 *
 * ── Boundaries ──────────────────────────────────────────────────────────────
 * ZERO external network calls, no credentials, nothing written. Every instant
 * below is a fixed literal (or a pure function of one), so the page prerenders
 * byte-identically — no `Date.now()`, no `Math.random()`.
 *
 * ── Canonical grounding ─────────────────────────────────────────────────────
 * The lifecycle is the D-081 state machine (`PLACED → VALIDATED → FULFILLING →
 * COMPLETED`, with `CANCELLED` and the single audit-legal exit `COMPLETED →
 * REFUNDED`; `local/canonical/oms_contracts.py`). The fulfillment column is a
 * PRESENTATION lens over it; the guard rejects any (payment, fulfillment,
 * lifecycle) triple the state machine cannot produce. Money is integer Toman
 * (D-010) — no float ever touches an amount. The gateway log is masked by
 * construction (D-114/D-124): audit entries carry `GW-****NNNN` style
 * references, never a PAN, an auth code or a gateway key. Shipping has no
 * provider (`UNSELECTED`, open decision 11) and payment is dry-run because no
 * provider is selected (open decision 10).
 *
 * ── Fail-closed invariant guard ─────────────────────────────────────────────
 * `assertCommerceConsistency()` throws at BUILD time when, among others:
 *   1. an order with `FAILED` payment is marked `SHIPPED` or `DELIVERED`
 *      (the owner directive's mandated invariant),
 *   2. the settlement/GMV/AOV roll-up disagrees with integer Toman math
 *      recomputed from the rendered rows,
 *   3. a lifecycle/history pair the D-081 machine cannot produce (first
 *      transition is not `PLACED`, last state ≠ `lifecycle`, instants
 *      non-monotonic, missing D-121 trace),
 *   4. money is non-integer or a line total ≠ quantity × unit price,
 *   5. a masked gateway reference leaks a digit run or lacks the mask marker,
 *   6. the shipping provider is anything but `UNSELECTED`, or an action is
 *      enabled without an owner token AND a selected provider.
 *
 * ── Scenarios ───────────────────────────────────────────────────────────────
 * `steady` (default), `surge`, `payment-degraded` via `CP_COMMERCE_SCENARIO`;
 * an unrecognised value falls back to `all-unknown` (NO_DATA) so a typo can
 * never render as a healthy revenue picture.
 */

import type { Provenance } from '@/types/telemetry';
import type {
  Channel,
  CommerceActionSpec,
  CommerceDataSource,
  CommerceSnapshot,
  FulfillmentStatus,
  LifecycleState,
  Order,
  OrderItem,
  PaymentAuditEntry,
  PaymentStatus,
  Receipt,
  RevenueSummary,
  RiskLevel,
  SettlementState,
} from '@/types/commerce';

/** Named, deterministic scenarios. Default is `steady`. */
export type CommerceScenario = 'steady' | 'surge' | 'payment-degraded' | 'all-unknown';

/** Fixed literal instant, so the static prerender is byte-stable. */
const MOCK_INSTANT = '2026-10-05T08:00:00.000Z';
/** The daily window opens at midnight UTC of the snapshot day. */
const DAY_WINDOW_START = '2026-10-05T00:00:00.000Z';
/** The weekly window opens seven days before the snapshot day. */
const WEEK_WINDOW_START = '2026-09-29T00:00:00.000Z';

const ISO_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/;
const ORDER_ID_RE = /^ORD-[0-9]{5}$/;
const SKU_RE = /^P[0-9]{5}(?:-[A-Z0-9]{1,4})*$/;
const TRACE_RE = /^trace-[0-9a-f]{8}$/;

/** Deterministic FNV-1a trace id — a pure function of the literal key (D-121). */
function traceIdFor(key: string): string {
  let hash = 0x811c9dc5;
  for (let index = 0; index < key.length; index += 1) {
    hash ^= key.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return `trace-${hash.toString(16).padStart(8, '0')}`;
}

function plusMinutes(instant: string, minutes: number): string {
  return new Date(new Date(instant).getTime() + minutes * 60_000).toISOString();
}

function isWithin(instant: string, startInclusive: string, endExclusive: string): boolean {
  return instant >= startInclusive && instant < endExclusive;
}

/** Canonical SKU catalogue reused from the inventory view (same literals). */
const SKU_CATALOG: Record<string, { titleFa: string; unitPriceToman: number }> = {
  P90401: { titleFa: 'هدفون بی‌سیم «آرکا»', unitPriceToman: 4_850_000 },
  P90402: { titleFa: 'پاوربانک ۲۰٬۰۰۰ میلی‌آمپری «راه»', unitPriceToman: 1_290_000 },
  P90403: { titleFa: 'ساعت هوشمند «پالس»', unitPriceToman: 6_400_000 },
  P90404: { titleFa: 'اسپیکر بلوتوثی «همهمه»', unitPriceToman: 2_150_000 },
  P90405: { titleFa: 'شارژر سریع ۶۵ وات', unitPriceToman: 980_000 },
  'P90406-BK': { titleFa: 'ماوس‌پد ارگونومیک (مشکی)', unitPriceToman: 420_000 },
  'P90407-GY1': { titleFa: 'کاور محافظ لپ‌تاپ ۱۴ اینچ (طوسی روشن)', unitPriceToman: 640_000 },
  'P90408-CAM': { titleFa: 'کیف حمل دوربین', unitPriceToman: 1_780_000 },
  P90409: { titleFa: 'پایه نگهدارنده گوشی', unitPriceToman: 310_000 },
  P90410: { titleFa: 'اشتراک یک‌ساله نرم‌افزار مدیریت پروژه', unitPriceToman: 3_600_000 },
  P90411: { titleFa: 'لایسنس افزونه گزارش‌ساز فروش', unitPriceToman: 2_400_000 },
  P90412: { titleFa: 'دوره آموزشی «تحلیل داده فروش»', unitPriceToman: 1_950_000 },
  P90413: { titleFa: 'قالب دیجیتال صفحه فرود', unitPriceToman: 890_000 },
  'P90414-WHT': { titleFa: 'هدفون سیمی «آوا» (سفید)', unitPriceToman: 1_450_000 },
};

/** One order row BEFORE derivation (history/audit/receipts/shipping). */
interface OrderSpec {
  orderId: string;
  wooOrderId: number | null;
  customerNameFa: string;
  channel: Channel;
  paymentStatus: PaymentStatus;
  fulfillmentStatus: FulfillmentStatus;
  settlement: SettlementState;
  riskScore: number;
  placedAtUtc: string;
  items: Array<[sku: string, quantity: number]>;
}

/** The D-081 lifecycle implied by the presentation pair (checked by the guard). */
const ALLOWED_LIFECYCLES: Record<
  PaymentStatus,
  Partial<Record<FulfillmentStatus, LifecycleState[]>>
> = {
  PAID: {
    UNFULFILLED: ['VALIDATED'],
    PROCESSING: ['FULFILLING'],
    SHIPPED: ['FULFILLING'],
    DELIVERED: ['COMPLETED'],
    CANCELLED: ['CANCELLED'],
  },
  PENDING_PAYMENT: {
    UNFULFILLED: ['PLACED', 'VALIDATED'],
    CANCELLED: ['CANCELLED'],
  },
  FAILED: {
    UNFULFILLED: ['PLACED', 'VALIDATED'],
    CANCELLED: ['CANCELLED'],
  },
  REFUNDED: {
    DELIVERED: ['REFUNDED'],
  },
};

const ALLOWED_SETTLEMENTS: Record<PaymentStatus, SettlementState[]> = {
  PAID: ['SETTLED', 'PENDING'],
  PENDING_PAYMENT: ['NOT_APPLICABLE'],
  FAILED: ['NOT_APPLICABLE'],
  REFUNDED: ['REFUNDED'],
};

/** The base catalogue — every payment/fulfillment shape is exercised. */
const BASE_ORDERS: OrderSpec[] = [
  {
    orderId: 'ORD-01001',
    wooOrderId: 48_211,
    customerNameFa: 'مریم رضایی',
    channel: 'web_store',
    paymentStatus: 'PAID',
    fulfillmentStatus: 'DELIVERED',
    settlement: 'SETTLED',
    riskScore: 12,
    placedAtUtc: '2026-10-02T09:15:00.000Z',
    items: [['P90401', 1], ['P90406-BK', 2]],
  },
  {
    orderId: 'ORD-01002',
    wooOrderId: 48_260,
    customerNameFa: 'علی موسوی',
    channel: 'telegram',
    paymentStatus: 'PAID',
    fulfillmentStatus: 'SHIPPED',
    settlement: 'PENDING',
    riskScore: 28,
    placedAtUtc: '2026-10-04T17:40:00.000Z',
    items: [['P90403', 1]],
  },
  {
    orderId: 'ORD-01003',
    wooOrderId: 48_301,
    customerNameFa: 'سارا احمدی',
    channel: 'instagram_dm',
    paymentStatus: 'PENDING_PAYMENT',
    fulfillmentStatus: 'UNFULFILLED',
    settlement: 'NOT_APPLICABLE',
    riskScore: 55,
    placedAtUtc: '2026-10-05T07:05:00.000Z',
    items: [['P90405', 1], ['P90409', 1]],
  },
  {
    orderId: 'ORD-01004',
    wooOrderId: 48_312,
    customerNameFa: 'حسین کریمی',
    channel: 'web_store',
    paymentStatus: 'FAILED',
    fulfillmentStatus: 'CANCELLED',
    settlement: 'NOT_APPLICABLE',
    riskScore: 78,
    placedAtUtc: '2026-10-05T06:20:00.000Z',
    items: [['P90403', 1]],
  },
  {
    orderId: 'ORD-01005',
    wooOrderId: 48_318,
    customerNameFa: 'نگار شریفی',
    channel: 'telegram',
    paymentStatus: 'PAID',
    fulfillmentStatus: 'PROCESSING',
    settlement: 'PENDING',
    riskScore: 34,
    placedAtUtc: '2026-10-05T07:30:00.000Z',
    items: [['P90404', 1], ['P90413', 1]],
  },
  {
    orderId: 'ORD-01006',
    wooOrderId: 48_102,
    customerNameFa: 'شرکت آریانا (سفارش سازمانی)',
    channel: 'web_store',
    paymentStatus: 'PAID',
    fulfillmentStatus: 'DELIVERED',
    settlement: 'SETTLED',
    riskScore: 8,
    placedAtUtc: '2026-10-01T11:05:00.000Z',
    items: [['P90410', 1]],
  },
  {
    orderId: 'ORD-01007',
    wooOrderId: 47_988,
    customerNameFa: 'امیر نادری',
    channel: 'web_store',
    paymentStatus: 'REFUNDED',
    fulfillmentStatus: 'DELIVERED',
    settlement: 'REFUNDED',
    riskScore: 21,
    placedAtUtc: '2026-09-30T14:25:00.000Z',
    items: [['P90408-CAM', 1]],
  },
  {
    orderId: 'ORD-01008',
    wooOrderId: null,
    customerNameFa: 'لیلا فرهادی',
    channel: 'instagram_dm',
    paymentStatus: 'FAILED',
    fulfillmentStatus: 'UNFULFILLED',
    settlement: 'NOT_APPLICABLE',
    riskScore: 62,
    placedAtUtc: '2026-10-04T21:10:00.000Z',
    items: [['P90414-WHT', 1]],
  },
  {
    orderId: 'ORD-01009',
    wooOrderId: 48_322,
    customerNameFa: 'رضا قاسمی',
    channel: 'web_store',
    paymentStatus: 'PAID',
    fulfillmentStatus: 'PROCESSING',
    settlement: 'PENDING',
    riskScore: 44,
    placedAtUtc: '2026-10-05T06:55:00.000Z',
    items: [['P90402', 2]],
  },
  {
    orderId: 'ORD-01010',
    wooOrderId: null,
    customerNameFa: 'مینا کاظمی',
    channel: 'telegram',
    paymentStatus: 'PENDING_PAYMENT',
    fulfillmentStatus: 'UNFULFILLED',
    settlement: 'NOT_APPLICABLE',
    riskScore: 25,
    placedAtUtc: '2026-10-05T07:48:00.000Z',
    items: [['P90412', 1]],
  },
  {
    orderId: 'ORD-01011',
    wooOrderId: 48_240,
    customerNameFa: 'پویا رستمی',
    channel: 'instagram_dm',
    paymentStatus: 'PAID',
    fulfillmentStatus: 'SHIPPED',
    settlement: 'PENDING',
    riskScore: 39,
    placedAtUtc: '2026-10-03T13:00:00.000Z',
    items: [['P90407-GY1', 1], ['P90409', 1]],
  },
  {
    orderId: 'ORD-01012',
    wooOrderId: 48_327,
    customerNameFa: 'شیدا مرادی',
    channel: 'telegram',
    paymentStatus: 'PAID',
    fulfillmentStatus: 'DELIVERED',
    settlement: 'SETTLED',
    riskScore: 15,
    placedAtUtc: '2026-10-05T05:10:00.000Z',
    items: [['P90411', 1]],
  },
];

/** `surge` adds four fresh same-day orders (higher volume, same rules). */
const SURGE_EXTRA_ORDERS: OrderSpec[] = [
  {
    orderId: 'ORD-01013',
    wooOrderId: 48_330,
    customerNameFa: 'بهنام اسدی',
    channel: 'web_store',
    paymentStatus: 'PAID',
    fulfillmentStatus: 'PROCESSING',
    settlement: 'PENDING',
    riskScore: 22,
    placedAtUtc: '2026-10-05T07:10:00.000Z',
    items: [['P90401', 1]],
  },
  {
    orderId: 'ORD-01014',
    wooOrderId: 48_333,
    customerNameFa: 'رها پناهی',
    channel: 'instagram_dm',
    paymentStatus: 'PAID',
    fulfillmentStatus: 'UNFULFILLED',
    settlement: 'PENDING',
    riskScore: 31,
    placedAtUtc: '2026-10-05T07:35:00.000Z',
    items: [['P90404', 2]],
  },
  {
    orderId: 'ORD-01015',
    wooOrderId: 48_336,
    customerNameFa: 'کیوان صادقی',
    channel: 'telegram',
    paymentStatus: 'PAID',
    fulfillmentStatus: 'PROCESSING',
    settlement: 'PENDING',
    riskScore: 18,
    placedAtUtc: '2026-10-05T06:55:30.000Z',
    items: [['P90405', 3]],
  },
  {
    orderId: 'ORD-01016',
    wooOrderId: null,
    customerNameFa: 'مرجان دلاوری',
    channel: 'web_store',
    paymentStatus: 'PENDING_PAYMENT',
    fulfillmentStatus: 'UNFULFILLED',
    settlement: 'NOT_APPLICABLE',
    riskScore: 66,
    placedAtUtc: '2026-10-05T07:50:00.000Z',
    items: [['P90408-CAM', 1]],
  },
];

/** `payment-degraded` flips three captures to FAILED and cancels their rows. */
const PAYMENT_DEGRADED_OVERRIDES: Record<string, Partial<OrderSpec>> = {
  'ORD-01005': {
    paymentStatus: 'FAILED',
    fulfillmentStatus: 'CANCELLED',
    settlement: 'NOT_APPLICABLE',
    riskScore: 67,
  },
  'ORD-01009': {
    paymentStatus: 'FAILED',
    fulfillmentStatus: 'CANCELLED',
    settlement: 'NOT_APPLICABLE',
    riskScore: 71,
  },
  'ORD-01011': {
    paymentStatus: 'FAILED',
    fulfillmentStatus: 'CANCELLED',
    settlement: 'NOT_APPLICABLE',
    riskScore: 58,
  },
};

function riskLevelOf(score: number): RiskLevel {
  if (score < 40) return 'LOW';
  if (score < 70) return 'MEDIUM';
  return 'HIGH';
}

function buildItems(spec: OrderSpec): OrderItem[] {
  return spec.items.map(([sku, quantity]) => {
    const entry = SKU_CATALOG[sku];
    if (!entry) {
      throw new Error(`commerce spec references unknown SKU ${sku}`);
    }
    return {
      sku,
      titleFa: entry.titleFa,
      quantity,
      unitPriceToman: entry.unitPriceToman,
      lineTotalToman: entry.unitPriceToman * quantity,
    };
  });
}

function totalOf(items: OrderItem[]): number {
  return items.reduce((sum, item) => sum + item.lineTotalToman, 0);
}

/** Derive the D-081 transition path from the presentation pair. */
function lifecycleOf(spec: OrderSpec): LifecycleState {
  const allowed = ALLOWED_LIFECYCLES[spec.paymentStatus][spec.fulfillmentStatus];
  const [first] = allowed ?? [];
  if (!first) {
    throw new Error(
      `commerce spec ${spec.orderId}: payment ${spec.paymentStatus} cannot be ${spec.fulfillmentStatus}`,
    );
  }
  return first;
}

function buildHistory(spec: OrderSpec, lifecycle: LifecycleState): Order['history'] {
  const entries: Order['history'] = [
    {
      state: 'PLACED',
      atUtc: spec.placedAtUtc,
      noteFa: 'سفارش ثبت شد و در انتظار اعتبارسنجی قرار گرفت.',
      traceId: traceIdFor(`${spec.orderId}:PLACED`),
    },
  ];
  const push = (state: LifecycleState, minutes: number, noteFa: string) => {
    entries.push({
      state,
      atUtc: plusMinutes(spec.placedAtUtc, minutes),
      noteFa,
      traceId: traceIdFor(`${spec.orderId}:${state}`),
    });
  };
  if (lifecycle !== 'PLACED') {
    push('VALIDATED', 12, 'اعتبارسنجی اقلام و موجودی انجام شد.');
  }
  if (lifecycle === 'FULFILLING' || lifecycle === 'COMPLETED' || lifecycle === 'REFUNDED') {
    push('FULFILLING', 45, 'آماده‌سازی و بسته‌بندی آغاز شد.');
  }
  if (lifecycle === 'COMPLETED' || lifecycle === 'REFUNDED') {
    push('COMPLETED', 1_560, 'تحویل تأیید و سفارش تکمیل شد.');
  }
  if (lifecycle === 'CANCELLED') {
    push(
      'CANCELLED',
      30,
      spec.paymentStatus === 'FAILED'
        ? 'پرداخت ناموفق بود و سفارش لغو شد؛ موجودی آزاد شد.'
        : 'سفارش پیش از تکمیل لغو شد؛ موجودی آزاد شد.',
    );
  }
  if (lifecycle === 'REFUNDED') {
    push('REFUNDED', 4_320, 'بازگشت وجه ثبت شد (D-082)؛ رکورد بازگشت صادر شد.');
  }
  return entries;
}

function buildPaymentAudit(spec: OrderSpec, total: number): PaymentAuditEntry[] {
  const base = {
    amountToman: total,
    gatewayRefMasked: `GW-****${spec.orderId.slice(-4)}`,
  };
  const pending: PaymentAuditEntry = {
    ...base,
    atUtc: plusMinutes(spec.placedAtUtc, 1),
    eventFa: 'درخواست پرداخت در درگاه ایجاد شد.',
    outcome: 'PENDING',
    traceId: traceIdFor(`${spec.orderId}:pay:init`),
  };
  const captured: PaymentAuditEntry = {
    ...base,
    atUtc: plusMinutes(spec.placedAtUtc, 8),
    eventFa: 'پرداخت با موفقیت تأیید شد.',
    outcome: 'OK',
    traceId: traceIdFor(`${spec.orderId}:pay:ok`),
  };
  const failed: PaymentAuditEntry = {
    ...base,
    atUtc: plusMinutes(spec.placedAtUtc, 9),
    eventFa: 'درگاه پرداخت را رد کرد؛ سفارش پرداخت‌نشده ماند.',
    outcome: 'FAILED',
    traceId: traceIdFor(`${spec.orderId}:pay:fail`),
  };
  const refunded: PaymentAuditEntry = {
    ...base,
    atUtc: plusMinutes(spec.placedAtUtc, 4_400),
    eventFa: 'بازگشت وجه در درگاه ثبت شد (بدون داده‌ی حساس کارت).',
    outcome: 'OK',
    traceId: traceIdFor(`${spec.orderId}:pay:refund`),
  };
  switch (spec.paymentStatus) {
    case 'PENDING_PAYMENT':
      return [pending];
    case 'PAID':
      return [pending, captured];
    case 'FAILED':
      return [pending, failed];
    case 'REFUNDED':
      return [pending, captured, refunded];
  }
}

function shippingStatusFa(fulfillment: FulfillmentStatus): string {
  switch (fulfillment) {
    case 'UNFULFILLED':
      return 'ارسال آغاز نشده است';
    case 'PROCESSING':
      return 'در حال آماده‌سازی برای ارسال';
    case 'SHIPPED':
      return 'تحویل به پست شد';
    case 'DELIVERED':
      return 'تحویل داده شد';
    case 'CANCELLED':
      return 'لغو شد';
  }
}

function buildReceipts(spec: OrderSpec, lifecycle: LifecycleState, total: number): Receipt[] {
  if (lifecycle !== 'COMPLETED' && lifecycle !== 'REFUNDED') return [];
  const issued: Receipt = {
    receiptId: `RC-${spec.orderId.slice(-5)}`,
    kind: 'ISSUED',
    issuedAtUtc: plusMinutes(spec.placedAtUtc, 1_570),
    totalToman: total,
  };
  if (lifecycle === 'REFUNDED') {
    return [
      issued,
      {
        receiptId: `RF-${spec.orderId.slice(-5)}`,
        kind: 'REFUND',
        issuedAtUtc: plusMinutes(spec.placedAtUtc, 4_380),
        totalToman: total,
      },
    ];
  }
  return [issued];
}

/** Build one complete order row from its spec. */
function buildOrder(spec: OrderSpec): Order {
  const items = buildItems(spec);
  const totalToman = totalOf(items);
  const lifecycle = lifecycleOf(spec);
  const history = buildHistory(spec, lifecycle);
  const lastEntry = history[history.length - 1];
  if (!lastEntry) {
    throw new Error(`commerce spec ${spec.orderId}: history must open with PLACED`);
  }
  return {
    orderId: spec.orderId,
    wooOrderId: spec.wooOrderId,
    customerNameFa: spec.customerNameFa,
    channel: spec.channel,
    totalToman,
    paymentStatus: spec.paymentStatus,
    fulfillmentStatus: spec.fulfillmentStatus,
    lifecycle,
    settlement: spec.settlement,
    placedAtUtc: spec.placedAtUtc,
    lastUpdateUtc: lastEntry.atUtc,
    riskScore: spec.riskScore,
    riskLevel: riskLevelOf(spec.riskScore),
    items,
    history,
    paymentAudit: buildPaymentAudit(spec, totalToman),
    shipping: {
      provider: 'UNSELECTED',
      statusFa: shippingStatusFa(spec.fulfillmentStatus),
      trackingNumber:
        spec.fulfillmentStatus === 'SHIPPED' || spec.fulfillmentStatus === 'DELIVERED'
          ? `POST-${spec.wooOrderId ?? spec.orderId.slice(-5)}`
          : null,
    },
    receipts: buildReceipts(spec, lifecycle, totalToman),
  };
}

function specsFor(scenario: CommerceScenario): OrderSpec[] {
  if (scenario === 'all-unknown') return [];
  let specs = BASE_ORDERS;
  if (scenario === 'surge') specs = [...specs, ...SURGE_EXTRA_ORDERS];
  if (scenario === 'payment-degraded') {
    specs = specs.map((spec) => ({ ...spec, ...(PAYMENT_DEGRADED_OVERRIDES[spec.orderId] ?? {}) }));
  }
  return specs;
}

function ordersFor(scenario: CommerceScenario): Order[] {
  return specsFor(scenario).map(buildOrder);
}

/** Derived revenue roll-up. The guard recomputes every figure independently. */
export function summarizeRevenue(orders: Order[]): RevenueSummary {
  const paidToday = orders.filter(
    (order) =>
      order.paymentStatus === 'PAID' &&
      isWithin(order.placedAtUtc, DAY_WINDOW_START, MOCK_INSTANT),
  );
  const paidAll = orders.filter((order) => order.paymentStatus === 'PAID');
  const dailyGmvToman = paidToday.reduce((sum, order) => sum + order.totalToman, 0);
  const weeklyGmvToman = paidAll
    .filter((order) => isWithin(order.placedAtUtc, WEEK_WINDOW_START, MOCK_INSTANT))
    .reduce((sum, order) => sum + order.totalToman, 0);
  return {
    dailyGmvToman,
    weeklyGmvToman,
    aovToman: paidToday.length > 0 ? Math.round(dailyGmvToman / paidToday.length) : 0,
    pendingSettlementToman: orders
      .filter((order) => order.settlement === 'PENDING')
      .reduce((sum, order) => sum + order.totalToman, 0),
    failedPaymentCount: orders.filter((order) => order.paymentStatus === 'FAILED').length,
    completedOrderCount: orders.filter((order) => order.lifecycle === 'COMPLETED').length,
    pendingProcessingCount: orders.filter(
      (order) =>
        order.paymentStatus === 'PAID' &&
        (order.fulfillmentStatus === 'UNFULFILLED' ||
          order.fulfillmentStatus === 'PROCESSING' ||
          order.fulfillmentStatus === 'SHIPPED'),
    ).length,
    paidOrderCount: paidAll.length,
  };
}

/**
 * The three gated write paths (D-171 §5.6/§6). Every action is DISABLED: the
 * UI holds no single-use owner token (D-146) and no payment/shipping provider
 * is selected (open decisions 10/11), so no real payment path exists.
 */
const NO_TOKEN_REASON =
  'توکن یک‌بارمصرف مالک در این رابط ساخته نمی‌شود (D-146)؛ در حالت dry-run هیچ کنش نوشتنی مجاز نیست';

const NO_PROVIDER_REASON =
  'ارائه‌دهنده‌ی پرداخت/ارسال هنوز انتخاب نشده است (تصمیم‌های باز ۱۰ و ۱۱)؛ اجرای واقعی مسیر پرداخت ممکن نیست';

const ACTIONS: CommerceActionSpec[] = [
  {
    id: 'MARK_SHIPPED',
    titleFa: 'ثبت ارسال و شماره ردیابی',
    descriptionFa:
      'انتقال سفارش پرداخت‌شده به «ارسال‌شده» و اتصال شماره ردیابی؛ نوشتن از مسیر امضاشده با رکورد لجر (D-121)',
    requiresSecondConfirmation: false,
    enabled: false,
    blockedReasonFa: NO_PROVIDER_REASON,
  },
  {
    id: 'ISSUE_INVOICE',
    titleFa: 'صدور فاکتور رسمی',
    descriptionFa:
      'صدور فاکتور با مبالغ عدد صحیح Toman (D-010) و دانلود آن؛ نگهداری سند در لجر عرضه',
    requiresSecondConfirmation: false,
    enabled: false,
    blockedReasonFa: NO_TOKEN_REASON,
  },
  {
    id: 'RETRY_PAYMENT',
    titleFa: 'تلاش دوباره‌ی پرداخت',
    descriptionFa:
      'ایجاد دوباره‌ی درخواست پرداخت برای سفارش پرداخت‌نشده؛ کنشی که بدون ارائه‌دهنده‌ی انتخاب‌شده و حکم مالک ممکن نیست',
    requiresSecondConfirmation: true,
    enabled: false,
    blockedReasonFa: NO_PROVIDER_REASON,
  },
];

/**
 * Assert the snapshot cannot display a state the canonical rules forbid.
 * Throwing is the fail-closed behaviour: a contradictory commerce snapshot is
 * never rendered with persuasive revenue numbers.
 */
export function assertCommerceConsistency(snapshot: CommerceSnapshot): CommerceSnapshot {
  const problems: string[] = [];
  const seenIds = new Set<string>();

  for (const order of snapshot.orders) {
    const id = order.orderId;
    if (!ORDER_ID_RE.test(id)) problems.push(`order id ${id} is not ORD-#####`);
    if (seenIds.has(id)) problems.push(`duplicate order id ${id}`);
    seenIds.add(id);
    if (!order.customerNameFa.trim()) problems.push(`${id}: customer name must not be empty`);
    if (order.wooOrderId !== null && (!Number.isInteger(order.wooOrderId) || order.wooOrderId <= 0)) {
      problems.push(`${id}: wooOrderId must be a positive integer or null`);
    }

    // Identifiers and money are plain integers (D-010); no float ever appears.
    if (!Number.isInteger(order.totalToman) || order.totalToman <= 0) {
      problems.push(`${id}: totalToman must be a positive integer`);
    }
    for (const item of order.items) {
      if (!SKU_RE.test(item.sku)) problems.push(`${id}: SKU ${item.sku} violates the canonical form`);
      if (!SKU_CATALOG[item.sku]) problems.push(`${id}: SKU ${item.sku} is not in the catalogue`);
      if (!Number.isInteger(item.quantity) || item.quantity <= 0) {
        problems.push(`${id}: quantity must be a positive integer`);
      }
      if (!Number.isInteger(item.unitPriceToman) || item.unitPriceToman <= 0) {
        problems.push(`${id}: unitPriceToman must be a positive integer`);
      }
      if (item.lineTotalToman !== item.quantity * item.unitPriceToman) {
        problems.push(`${id}: line total != quantity x unit price`);
      }
    }
    if (order.items.length === 0) problems.push(`${id}: at least one line item is required`);
    if (totalOf(order.items) !== order.totalToman) {
      problems.push(`${id}: totalToman != sum of line totals (integer math)`);
    }

    // The owner directive's mandated invariant.
    if (
      order.paymentStatus === 'FAILED' &&
      (order.fulfillmentStatus === 'SHIPPED' || order.fulfillmentStatus === 'DELIVERED')
    ) {
      problems.push(`${id}: FAILED payment must not be SHIPPED or DELIVERED (fail-closed)`);
    }
    const allowed = ALLOWED_LIFECYCLES[order.paymentStatus][order.fulfillmentStatus];
    if (!allowed || !allowed.includes(order.lifecycle)) {
      problems.push(
        `${id}: (${order.paymentStatus}, ${order.fulfillmentStatus}, ${order.lifecycle}) is not a D-081 legal combination`,
      );
    }
    if (!ALLOWED_SETTLEMENTS[order.paymentStatus].includes(order.settlement)) {
      problems.push(`${id}: settlement ${order.settlement} is illegal for ${order.paymentStatus}`);
    }

    // Risk is a bounded integer; the level is derived, never typed.
    if (!Number.isInteger(order.riskScore) || order.riskScore < 0 || order.riskScore > 100) {
      problems.push(`${id}: riskScore must be an integer within 0..100`);
    }
    if (order.riskLevel !== riskLevelOf(order.riskScore)) {
      problems.push(`${id}: riskLevel disagrees with the risk score`);
    }

    // History must be a real D-081 walk.
    const firstEntry = order.history[0];
    const finalEntry = order.history[order.history.length - 1];
    if (!firstEntry || firstEntry.state !== 'PLACED') {
      problems.push(`${id}: history must open with PLACED`);
    }
    if (!finalEntry || finalEntry.state !== order.lifecycle) {
      problems.push(`${id}: last history state must equal the lifecycle`);
    }
    let previous = '';
    for (const entry of order.history) {
      if (!ISO_RE.test(entry.atUtc)) problems.push(`${id}: history instant is not ISO-8601`);
      if (!TRACE_RE.test(entry.traceId)) problems.push(`${id}: history entry lacks a D-121 trace`);
      if (!entry.noteFa.trim()) problems.push(`${id}: history entry must state its reason`);
      if (previous && entry.atUtc < previous) problems.push(`${id}: history instants must increase`);
      previous = entry.atUtc;
    }
    if (!ISO_RE.test(order.placedAtUtc) || order.lastUpdateUtc !== previous) {
      problems.push(`${id}: lastUpdateUtc must equal the final transition instant`);
    }

    // Ordering/cancellation coherence beyond the triple table.
    if (order.lifecycle === 'CANCELLED' && order.fulfillmentStatus !== 'CANCELLED') {
      problems.push(`${id}: CANCELLED lifecycle requires CANCELLED fulfillment`);
    }
    if (
      order.fulfillmentStatus === 'DELIVERED' &&
      order.lifecycle !== 'COMPLETED' &&
      order.lifecycle !== 'REFUNDED'
    ) {
      problems.push(`${id}: DELIVERED requires the COMPLETED lifecycle or the REFUNDED exit`);
    }
    if (order.paymentStatus === 'REFUNDED' && order.lifecycle !== 'REFUNDED') {
      problems.push(`${id}: REFUNDED payment requires the REFUNDED lifecycle`);
    }

    // Masked gateway log (D-114/D-124): marker present, no digit run (no PAN).
    if (order.paymentAudit.length === 0) {
      problems.push(`${id}: payment audit must not be empty`);
    }
    for (const entry of order.paymentAudit) {
      if (!entry.gatewayRefMasked.includes('****')) {
        problems.push(`${id}: gateway reference must be masked`);
      }
      if (/\d{12,}/.test(entry.gatewayRefMasked)) {
        problems.push(`${id}: gateway reference leaks a digit run (D-114)`);
      }
      if (!Number.isInteger(entry.amountToman) || entry.amountToman !== order.totalToman) {
        problems.push(`${id}: payment audit amount must equal the order total (integer)`);
      }
      if (!TRACE_RE.test(entry.traceId)) {
        problems.push(`${id}: payment audit entry lacks a D-121 trace`);
      }
    }
    const lastAudit = order.paymentAudit[order.paymentAudit.length - 1];
    const lastOutcome = lastAudit?.outcome;
    const expectedOutcome =
      order.paymentStatus === 'PAID' || order.paymentStatus === 'REFUNDED'
        ? 'OK'
        : order.paymentStatus === 'FAILED'
          ? 'FAILED'
          : 'PENDING';
    if (lastOutcome !== expectedOutcome) {
      problems.push(`${id}: payment audit outcome disagrees with the payment status`);
    }

    // Shipping: provider UNSELECTED (open decision 11); tracking only when shipped.
    if (order.shipping.provider !== 'UNSELECTED') {
      problems.push(`${id}: shipping provider must remain UNSELECTED (decision 11)`);
    }
    const shipped =
      order.fulfillmentStatus === 'SHIPPED' || order.fulfillmentStatus === 'DELIVERED';
    if (shipped !== (order.shipping.trackingNumber !== null)) {
      problems.push(`${id}: tracking number must exist exactly for shipped orders`);
    }

    // D-084 receipts: only completed/refunded orders carry them.
    const receipted = order.lifecycle === 'COMPLETED' || order.lifecycle === 'REFUNDED';
    if (!receipted && order.receipts.length > 0) {
      problems.push(`${id}: receipts exist only for completed/refunded orders`);
    }
    if (receipted && !order.receipts.some((receipt) => receipt.kind === 'ISSUED')) {
      problems.push(`${id}: completed/refunded orders require an issued receipt`);
    }
    if (order.lifecycle === 'REFUNDED' && !order.receipts.some((r) => r.kind === 'REFUND')) {
      problems.push(`${id}: refunded orders require a refund receipt`);
    }
    for (const receipt of order.receipts) {
      if (!Number.isInteger(receipt.totalToman) || receipt.totalToman <= 0) {
        problems.push(`${id}: receipt total must be a positive integer`);
      }
      if (!ISO_RE.test(receipt.issuedAtUtc)) {
        problems.push(`${id}: receipt instant is not ISO-8601`);
      }
    }
  }

  // ── the roll-up is derived, never retyped (integer Toman math) ────────────
  const expected = summarizeRevenue(snapshot.orders);
  for (const key of Object.keys(expected) as Array<keyof RevenueSummary>) {
    if (snapshot.summary[key] !== expected[key]) {
      problems.push(`summary.${key} ${snapshot.summary[key]} != derived ${expected[key]}`);
    }
  }
  if (!Number.isInteger(snapshot.summary.aovToman) || snapshot.summary.aovToman < 0) {
    problems.push('aovToman must be a non-negative integer');
  }

  // ── gated actions (D-146 / decisions 10-11) ──────────────────────────────
  for (const action of snapshot.actions) {
    if (!action.titleFa.trim() || !action.descriptionFa.trim()) {
      problems.push(`${action.id}: title and description must not be empty`);
    }
    if (action.enabled && (!snapshot.gate.tokenPresent || !snapshot.gate.providerSelected)) {
      problems.push(
        `${action.id}: action enabled without an owner token and a selected provider (D-146/decisions 10-11)`,
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
    throw new Error(`fail-closed violation in commerce snapshot: ${problems.join('; ')}`);
  }
  return snapshot;
}

/** Build the full snapshot for a scenario, guarded for fail-closed consistency. */
export function mockCommerce(scenario: CommerceScenario = 'steady'): CommerceSnapshot {
  const orders = ordersFor(scenario);
  const unavailable = scenario === 'all-unknown';
  const provenance: Provenance = unavailable ? 'unavailable' : 'mock';
  const snapshot: CommerceSnapshot = {
    generatedAt: MOCK_INSTANT,
    scenario,
    provenance,
    orders,
    summary: summarizeRevenue(orders),
    actions: ACTIONS,
    // No owner token exists here and no provider is selected, so every write
    // action must be disabled — the guard enforces that pairing.
    gate: { tokenPresent: false, providerSelected: false },
  };
  return assertCommerceConsistency(snapshot);
}

/**
 * Read the active scenario from the environment.
 *
 * Defaults to `steady`; an unrecognised value falls back to `all-unknown`, so a
 * typo can never render as a healthy revenue picture (fail-closed).
 */
export function activeCommerceScenario(): CommerceScenario {
  const raw = process.env.CP_COMMERCE_SCENARIO;
  if (raw === undefined || raw === '' || raw === 'steady') return 'steady';
  if (raw === 'surge') return 'surge';
  if (raw === 'payment-degraded') return 'payment-degraded';
  return 'all-unknown';
}

/** The mock implementation of the swap seam. */
export function createMockCommerceSource(
  scenario: CommerceScenario = 'steady',
): CommerceDataSource {
  return {
    async load(): Promise<CommerceSnapshot> {
      return mockCommerce(scenario);
    },
  };
}

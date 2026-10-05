/**
 * Deterministic mock provider for inventory & canonical SKUs (D-171 §5.3,
 * Phase 27.5).
 *
 * ── Boundaries ──────────────────────────────────────────────────────────────
 * This module makes ZERO external network calls, reads no credentials and
 * writes nothing. It returns fixed, hand-written catalog rows so the page
 * prerenders byte-identically on every build (no `Date.now()`, no
 * `Math.random()` — every instant below is a literal or a pure function of a
 * literal).
 *
 * Identifiers obey the canonical formats (`local/canonical/identifiers.py`):
 * Product ID `P#####` (D-014), Variant ID lowercase hyphenated UUIDv4 (D-017),
 * SKU `P#####[-CC][-SS]` with D-032 approved axis codes (D-014). SKUs carry
 * only APPROVED D-032 codes, so the guard rejects an invented suffix such as
 * `-BLK` exactly the way the engine does.
 *
 * ── Fail-closed consistency guard ───────────────────────────────────────────
 * `assertInventoryConsistency()` runs before a snapshot is returned and throws
 * at BUILD time when the snapshot could show a state the canonical rules
 * forbid. In particular, per the owner directive:
 *
 *   1. a row with `stock_qty <= safe_threshold` that carries NO low-stock
 *      alert (and a row above its threshold carrying a stale alert),
 *   2. a row marked `DRIFT_DETECTED` that claims to be clean/synced,
 *
 * plus identifier/money/write-path integrity: identifier formats (D-014/D-015/
 * D-017), SKU–product binding, integer Toman (D-010), a history entry for
 * every terminal sync state, mapping ids only on active D-046 entries, lock
 * reasons whenever locked, D-026 provenance vocabulary, and an enabled action
 * requires BOTH an owner token and a connected write path (D-146/D-171 §6).
 *
 * ── Scenarios ───────────────────────────────────────────────────────────────
 * `steady` (default), `low-stock-surge`, `sync-drift` — selected at build time
 * via `CP_INVENTORY_SCENARIO`. An unrecognised value falls back to
 * `all-unknown`, so a typo can never render as a healthy catalog.
 */

import type {
  InventoryActionSpec,
  InventoryDataSource,
  InventoryItem,
  InventorySnapshot,
  InventorySummary,
  ItemLock,
  ItemProvenance,
  SyncHistoryEntry,
  SyncStatus,
  StockCategory,
  SourceType,
  ReviewState,
  WooMapping,
} from '@/types/inventory';

/** Named, deterministic scenarios. Default is `steady`. */
export type InventoryScenario =
  | 'steady'
  | 'low-stock-surge'
  | 'sync-drift'
  | 'all-unknown';

/** Fixed literal instant, so the static prerender is byte-stable. */
const MOCK_INSTANT = '2026-10-04T08:00:00.000Z';

/** The canonical D-026 source types and review states. */
const SOURCE_TYPES: SourceType[] = [
  'HUMAN_ENTERED',
  'SYSTEM_GENERATED',
  'AI_GENERATED',
  'IMPORTED',
  'EXTERNAL_SYNC',
];
const REVIEW_STATES: ReviewState[] = ['PENDING', 'HUMAN_REVIEWED', 'HUMAN_VERIFIED'];

/** Canonical identifier formats (D-014/D-015/D-017 — identifiers.py). */
const PRODUCT_ID_RE = /^P[0-9]{5}$/;
const VARIANT_ID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const SKU_RE = /^P[0-9]{5}(?:-[A-Z0-9]{1,4})*$/;
const LOGICAL_RE = /^L-[0-9]{16}$/;

/**
 * Approved D-032 axis codes (vocab.py: colour codes + alpha size codes; the
 * mock catalog uses colour axes only). A SKU whose suffix is not in this set is
 * rejected, mirroring `identifiers.is_valid_sku`.
 */
const APPROVED_AXIS_CODES = new Set([
  'BK', 'WHT', 'GRY', 'CHR', 'GY1', 'CRM', 'BEG', 'BRN', 'NCF', 'NVY',
  'BU', 'BU1', 'PTB', 'GRN', 'VGR', 'DGN', 'RED', 'BRG', 'PNK', 'PK1',
  'PRP', 'RNG', 'YW', 'KHK', 'CAM',
  'XS', 'S', 'M', 'LRG', 'XG', 'XXG', '3XG', '4XG',
]);

/** Logical-clock literal: `L-` + 16 digits (D-093 precedent). */
function logical(n: number): string {
  return `L-${String(n).padStart(16, '0')}`;
}

/** Deterministic FNV-1a trace id — a pure function of the literal key. */
function traceIdFor(key: string): string {
  let hash = 0x811c9dc5;
  for (let i = 0; i < key.length; i += 1) {
    hash ^= key.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return `trace-${hash.toString(16).padStart(8, '0')}`;
}

/**
 * Stock state, derived from quantity against threshold — the single source of
 * that derivation. Zero is OUT_OF_STOCK even when the threshold is also zero.
 */
export function stockCategoryOf(stockQty: number, safeThreshold: number): StockCategory {
  if (stockQty === 0) return 'OUT_OF_STOCK';
  if (stockQty <= safeThreshold) return 'LOW_STOCK';
  return 'IN_STOCK';
}

/** Persian detail for one sync-history outcome (never empty). */
function historyDetail(direction: SyncHistoryEntry['direction'], outcome: SyncHistoryEntry['outcome']): string {
  if (outcome === 'FAILED') {
    return 'پاسخ WooCommerce نامعتبر یا ناموفق بود؛ نوشتن متوقف و رکورد شکست ثبت شد (D-052)';
  }
  if (outcome === 'DRIFT') {
    return 'واگرایی canonical و WooCommerce شناسایی شد؛ تا تصمیم انسانی حل نمی‌شود (D-003)';
  }
  if (direction === 'PUSH') {
    return 'ارسال تغییر قیمت/موجودی به WooCommerce با پاسخ موفق (D-034)';
  }
  if (direction === 'PULL') {
    return 'دریافت وضعیت از WooCommerce و اعمال بدون تناقض (D-036)';
  }
  return 'تطبیق کامل canonical و WooCommerce؛ اختلافی یافت نشد (D-040)';
}

/** `[seq, atLogical, direction, outcome]` — expanded by the builder below. */
type HistoryTuple = [
  number,
  string,
  SyncHistoryEntry['direction'],
  SyncHistoryEntry['outcome'],
];

/** One catalog row BEFORE derivation (stock category / alert / clean). */
interface ItemSpec {
  product_id: string;
  variant_id: string;
  sku: string;
  nameFa: string;
  categoryCode: string;
  categoryLabel: string;
  price_toman: number;
  stock_qty: number;
  safe_threshold: number;
  syncStatus: SyncStatus;
  woo: WooMapping;
  history: HistoryTuple[];
  lock: ItemLock;
  provenance: ItemProvenance;
  /** Persian alert reason; a standard reason is used when omitted. */
  alertReason?: string;
}

type ItemOverride = Partial<Pick<ItemSpec, 'stock_qty' | 'syncStatus'>>;

const LOW_STOCK_REASON =
  'موجودی به آستانه‌ی ایمن رسیده است؛ تا شارژ مجدد هشدار فعال می‌ماند (D-082)';
const OUT_OF_STOCK_REASON =
  'موجودی صفر شده است و آستانه‌ی ایمن نقض شده؛ فروش بیش از موجودی ممنوع است (D-082)';

/**
 * The base catalog — Persian samples across tech, digital and physical
 * accessories. Prices are integer Toman (D-010); quantities and thresholds are
 * integers. Statuses were chosen so the `steady` scenario already exercises
 * every sync badge.
 */
const BASE_CATALOG: ItemSpec[] = [
  {
    product_id: 'P90401',
    variant_id: 'a1f2c3d4-5e6f-4a7b-8c9d-0e1f2a3b4c5d',
    sku: 'P90401',
    nameFa: 'هدفون بی‌سیم «آرکا»',
    categoryCode: 'TECH_AUDIO',
    categoryLabel: 'هدفون و صدا',
    price_toman: 4_850_000,
    stock_qty: 12,
    safe_threshold: 4,
    syncStatus: 'IN_SYNC',
    woo: { productId: 3701, variationId: null, active: true },
    history: [
      [1, logical(120), 'PUSH', 'OK'],
      [2, logical(152), 'RECONCILE', 'OK'],
    ],
    lock: { state: 'NONE', reason: null, setAtLogical: null },
    provenance: {
      sourceType: 'EXTERNAL_SYNC',
      reviewState: 'HUMAN_VERIFIED',
      actor: 'system:sync_engine',
    },
  },
  {
    product_id: 'P90402',
    variant_id: 'b2e3d4f5-6a7b-4c8d-9e0f-1a2b3c4d5e6f',
    sku: 'P90402',
    nameFa: 'پاوربانک ۲۰٬۰۰۰ میلی‌آمپری «راه»',
    categoryCode: 'TECH_POWER',
    categoryLabel: 'منبع انرژی',
    price_toman: 1_290_000,
    stock_qty: 3,
    safe_threshold: 5,
    syncStatus: 'PENDING_SYNC',
    woo: { productId: 3702, variationId: null, active: true },
    history: [[1, logical(118), 'PULL', 'OK']],
    lock: { state: 'NONE', reason: null, setAtLogical: null },
    provenance: {
      sourceType: 'EXTERNAL_SYNC',
      reviewState: 'HUMAN_VERIFIED',
      actor: 'system:sync_engine',
    },
  },
  {
    product_id: 'P90403',
    variant_id: 'c3d4e5f6-7b8c-4d9e-8f0a-2b3c4d5e6f70',
    sku: 'P90403',
    nameFa: 'ساعت هوشمند «پالس»',
    categoryCode: 'TECH_WEARABLE',
    categoryLabel: 'پوشیدنی هوشمند',
    price_toman: 6_400_000,
    stock_qty: 0,
    safe_threshold: 2,
    syncStatus: 'IN_SYNC',
    woo: { productId: 3703, variationId: 9101, active: true },
    history: [
      [1, logical(104), 'PUSH', 'OK'],
      [2, logical(140), 'RECONCILE', 'OK'],
    ],
    lock: {
      state: 'STOCK_OVERRIDE',
      reason: 'قفل انسانی روی موجودی: تا تأیید شارژ مجدد، نوشتن همگام‌سازی مجاز نیست',
      setAtLogical: logical(141),
    },
    provenance: {
      sourceType: 'IMPORTED',
      reviewState: 'HUMAN_REVIEWED',
      actor: 'import:product_master',
    },
  },
  {
    product_id: 'P90404',
    variant_id: 'd4e5f6a7-8c9d-4e0f-9a1b-3c4d5e6f7081',
    sku: 'P90404',
    nameFa: 'اسپیکر بلوتوثی «همهمه»',
    categoryCode: 'TECH_AUDIO',
    categoryLabel: 'هدفون و صدا',
    price_toman: 2_150_000,
    stock_qty: 18,
    safe_threshold: 6,
    syncStatus: 'IN_SYNC',
    woo: { productId: 3704, variationId: null, active: true },
    history: [
      [1, logical(122), 'PUSH', 'OK'],
      [2, logical(155), 'RECONCILE', 'OK'],
    ],
    lock: { state: 'NONE', reason: null, setAtLogical: null },
    provenance: {
      sourceType: 'EXTERNAL_SYNC',
      reviewState: 'HUMAN_VERIFIED',
      actor: 'system:sync_engine',
    },
  },
  {
    product_id: 'P90405',
    variant_id: 'e5f6a7b8-9d0e-4f1a-8b2c-4d5e6f708192',
    sku: 'P90405',
    nameFa: 'شارژر سریع ۶۵ وات',
    categoryCode: 'TECH_POWER',
    categoryLabel: 'منبع انرژی',
    price_toman: 980_000,
    stock_qty: 27,
    safe_threshold: 10,
    syncStatus: 'IN_SYNC',
    woo: { productId: 3705, variationId: null, active: true },
    history: [
      [1, logical(126), 'PUSH', 'OK'],
      [2, logical(158), 'RECONCILE', 'OK'],
    ],
    lock: { state: 'NONE', reason: null, setAtLogical: null },
    provenance: {
      sourceType: 'HUMAN_ENTERED',
      reviewState: 'HUMAN_VERIFIED',
      actor: 'role:ops',
    },
  },
  {
    product_id: 'P90406',
    variant_id: 'f6a7b8c9-0e1f-4a2b-9c3d-5e6f708192a3',
    sku: 'P90406-BK',
    nameFa: 'ماوس‌پد ارگونومیک (مشکی)',
    categoryCode: 'ACCESSORY_DESK',
    categoryLabel: 'لوازم میز کار',
    price_toman: 420_000,
    stock_qty: 2,
    safe_threshold: 4,
    syncStatus: 'IN_SYNC',
    woo: { productId: 3706, variationId: 9102, active: true },
    history: [
      [1, logical(112), 'PUSH', 'OK'],
      [2, logical(146), 'RECONCILE', 'OK'],
    ],
    lock: { state: 'NONE', reason: null, setAtLogical: null },
    provenance: {
      sourceType: 'HUMAN_ENTERED',
      reviewState: 'PENDING',
      actor: 'role:ops',
    },
  },
  {
    product_id: 'P90407',
    variant_id: 'a7b8c9d0-1f2a-4b3c-8d4e-6f708192a3b4',
    sku: 'P90407-GY1',
    nameFa: 'کاور محافظ لپ‌تاپ ۱۴ اینچ (طوسی روشن)',
    categoryCode: 'ACCESSORY_PROTECT',
    categoryLabel: 'لوازم محافظ',
    price_toman: 640_000,
    stock_qty: 9,
    safe_threshold: 3,
    syncStatus: 'SYNC_ERROR',
    woo: { productId: 3707, variationId: 9103, active: true },
    history: [
      [1, logical(130), 'PUSH', 'OK'],
      [2, logical(162), 'PUSH', 'FAILED'],
    ],
    lock: { state: 'NONE', reason: null, setAtLogical: null },
    provenance: {
      sourceType: 'EXTERNAL_SYNC',
      reviewState: 'HUMAN_REVIEWED',
      actor: 'system:sync_engine',
    },
  },
  {
    product_id: 'P90408',
    variant_id: 'b8c9d0e1-2a3b-4c4d-9e5f-708192a3b4c5',
    sku: 'P90408-CAM',
    nameFa: 'کیف حمل دوربین',
    categoryCode: 'ACCESSORY_BAG',
    categoryLabel: 'کیف و حمل',
    price_toman: 1_780_000,
    stock_qty: 6,
    safe_threshold: 2,
    syncStatus: 'IN_SYNC',
    woo: { productId: 3708, variationId: null, active: true },
    history: [
      [1, logical(108), 'PUSH', 'OK'],
      [2, logical(138), 'RECONCILE', 'OK'],
    ],
    lock: { state: 'NONE', reason: null, setAtLogical: null },
    provenance: {
      sourceType: 'IMPORTED',
      reviewState: 'HUMAN_REVIEWED',
      actor: 'import:product_master',
    },
  },
  {
    product_id: 'P90409',
    variant_id: 'c9d0e1f2-3b4c-4d5e-8f60-8192a3b4c5d6',
    sku: 'P90409',
    nameFa: 'پایه نگهدارنده گوشی',
    categoryCode: 'ACCESSORY_DESK',
    categoryLabel: 'لوازم میز کار',
    price_toman: 310_000,
    stock_qty: 44,
    safe_threshold: 12,
    syncStatus: 'IN_SYNC',
    woo: { productId: 3709, variationId: null, active: true },
    history: [
      [1, logical(114), 'PUSH', 'OK'],
      [2, logical(149), 'RECONCILE', 'OK'],
    ],
    lock: { state: 'NONE', reason: null, setAtLogical: null },
    provenance: {
      sourceType: 'SYSTEM_GENERATED',
      reviewState: 'HUMAN_REVIEWED',
      actor: 'system:catalog_seed',
    },
  },
  {
    product_id: 'P90410',
    variant_id: 'd0e1f2a3-4c5d-4e6f-9a70-92a3b4c5d6e7',
    sku: 'P90410',
    nameFa: 'اشتراک یک‌ساله نرم‌افزار مدیریت پروژه',
    categoryCode: 'DIGITAL_LICENSE',
    categoryLabel: 'لایسنس دیجیتال',
    price_toman: 3_600_000,
    stock_qty: 100,
    safe_threshold: 20,
    syncStatus: 'IN_SYNC',
    woo: { productId: 3710, variationId: null, active: true },
    history: [
      [1, logical(116), 'PULL', 'OK'],
      [2, logical(151), 'RECONCILE', 'OK'],
    ],
    lock: { state: 'NONE', reason: null, setAtLogical: null },
    provenance: {
      sourceType: 'IMPORTED',
      reviewState: 'HUMAN_REVIEWED',
      actor: 'import:product_master',
    },
  },
  {
    product_id: 'P90411',
    variant_id: 'e1f2a3b4-5d6e-4f70-8b81-a3b4c5d6e7f8',
    sku: 'P90411',
    nameFa: 'لایسنس افزونه گزارش‌ساز فروش',
    categoryCode: 'DIGITAL_LICENSE',
    categoryLabel: 'لایسنس دیجیتال',
    price_toman: 2_400_000,
    stock_qty: 7,
    safe_threshold: 15,
    syncStatus: 'IN_SYNC',
    woo: { productId: 3711, variationId: null, active: true },
    history: [
      [1, logical(110), 'PUSH', 'OK'],
      [2, logical(144), 'RECONCILE', 'OK'],
    ],
    lock: { state: 'NONE', reason: null, setAtLogical: null },
    provenance: {
      sourceType: 'HUMAN_ENTERED',
      reviewState: 'HUMAN_VERIFIED',
      actor: 'role:owner',
    },
  },
  {
    product_id: 'P90412',
    variant_id: 'f2a3b4c5-6e7f-4a81-9c92-b4c5d6e7f809',
    sku: 'P90412',
    nameFa: 'دوره آموزشی «تحلیل داده فروش»',
    categoryCode: 'DIGITAL_COURSE',
    categoryLabel: 'دوره آموزشی',
    price_toman: 1_950_000,
    stock_qty: 250,
    safe_threshold: 40,
    syncStatus: 'IN_SYNC',
    woo: { productId: 3712, variationId: null, active: true },
    history: [
      [1, logical(106), 'PUSH', 'OK'],
      [2, logical(136), 'RECONCILE', 'OK'],
    ],
    lock: { state: 'NONE', reason: null, setAtLogical: null },
    provenance: {
      sourceType: 'AI_GENERATED',
      reviewState: 'HUMAN_VERIFIED',
      actor: 'system:content_pipeline',
    },
  },
  {
    product_id: 'P90413',
    variant_id: 'a3b4c5d6-7f80-4b92-8da3-c5d6e7f8091a',
    sku: 'P90413',
    nameFa: 'قالب دیجیتال صفحه فرود',
    categoryCode: 'DIGITAL_TEMPLATE',
    categoryLabel: 'قالب دیجیتال',
    price_toman: 890_000,
    stock_qty: 31,
    safe_threshold: 10,
    syncStatus: 'DRIFT_DETECTED',
    woo: { productId: 3713, variationId: null, active: true },
    history: [
      [1, logical(126), 'PUSH', 'OK'],
      [2, logical(168), 'RECONCILE', 'DRIFT'],
    ],
    lock: {
      state: 'PRICE_FREEZE',
      reason: 'قیمت canonical تا حل واگرایی با WooCommerce قفل شده است',
      setAtLogical: logical(169),
    },
    provenance: {
      sourceType: 'HUMAN_ENTERED',
      reviewState: 'HUMAN_VERIFIED',
      actor: 'role:owner',
    },
  },
  {
    product_id: 'P90414',
    variant_id: 'b4c5d6e7-8091-4ca3-9eb4-d6e7f8091a2b',
    sku: 'P90414-WHT',
    nameFa: 'هدفون سیمی «آوا» (سفید)',
    categoryCode: 'TECH_AUDIO',
    categoryLabel: 'هدفون و صدا',
    price_toman: 1_450_000,
    stock_qty: 11,
    safe_threshold: 5,
    syncStatus: 'IN_SYNC',
    woo: { productId: 3714, variationId: 9104, active: true },
    history: [
      [1, logical(124), 'PUSH', 'OK'],
      [2, logical(156), 'RECONCILE', 'OK'],
    ],
    lock: { state: 'NONE', reason: null, setAtLogical: null },
    provenance: {
      sourceType: 'HUMAN_ENTERED',
      reviewState: 'HUMAN_VERIFIED',
      actor: 'role:ops',
    },
  },
];

/** Stock/status overrides for the `low-stock-surge` harness. */
const LOW_STOCK_SURGE: Record<string, ItemOverride> = {
  P90401: { stock_qty: 2 },
  P90404: { stock_qty: 4 },
  P90408: { stock_qty: 0 },
  P90414: { stock_qty: 3 },
};

/** Sync overrides for the `sync-drift` harness. */
const SYNC_DRIFT: Record<string, ItemOverride> = {
  P90401: { syncStatus: 'SYNC_ERROR' },
  P90404: { syncStatus: 'DRIFT_DETECTED' },
  P90405: { syncStatus: 'PENDING_SYNC' },
  P90409: { syncStatus: 'DRIFT_DETECTED' },
  P90410: { syncStatus: 'SYNC_ERROR' },
  P90412: { syncStatus: 'DRIFT_DETECTED' },
};

/** The terminal history outcome each sync state requires. */
const TERMINAL_OUTCOME: Record<SyncStatus, SyncHistoryEntry['outcome'] | null> = {
  IN_SYNC: 'OK',
  PENDING_SYNC: null,
  SYNC_ERROR: 'FAILED',
  DRIFT_DETECTED: 'DRIFT',
};

const TERMINAL_DIRECTION: Record<
  SyncHistoryEntry['outcome'],
  SyncHistoryEntry['direction']
> = {
  OK: 'RECONCILE',
  FAILED: 'PUSH',
  DRIFT: 'RECONCILE',
};

/** Build one guarded catalog row out of a spec. */
function buildItem(spec: ItemSpec, index: number): InventoryItem {
  const history: SyncHistoryEntry[] = spec.history.map(
    ([seq, atLogical, direction, outcome]) => ({
      seq,
      atLogical,
      direction,
      outcome,
      detail: historyDetail(direction, outcome),
      traceId: traceIdFor(`${spec.sku}|${seq}|${direction}|${outcome}`),
    }),
  );

  // Ensure the history actually contains the terminal outcome its status
  // claims, so a badge can never outrun the recorded events.
  const terminal = TERMINAL_OUTCOME[spec.syncStatus];
  if (terminal !== null && !history.some((entry) => entry.outcome === terminal)) {
    const seq = history.length + 1;
    const atLogical = logical(170 + index);
    const direction = TERMINAL_DIRECTION[terminal];
    history.push({
      seq,
      atLogical,
      direction,
      outcome: terminal,
      detail: historyDetail(direction, terminal),
      traceId: traceIdFor(`${spec.sku}|${seq}|${direction}|${terminal}`),
    });
  }

  const lastEntry = history[history.length - 1];
  if (!lastEntry) {
    throw new Error(`inventory mock row ${spec.sku}: sync history must not be empty`);
  }

  const stockCategory = stockCategoryOf(spec.stock_qty, spec.safe_threshold);
  const alert =
    stockCategory === 'IN_STOCK'
      ? null
      : {
          level: stockCategory,
          reason:
            spec.alertReason ??
            (stockCategory === 'OUT_OF_STOCK' ? OUT_OF_STOCK_REASON : LOW_STOCK_REASON),
          raisedAtLogical: lastEntry.atLogical,
        };

  return {
    product_id: spec.product_id,
    variant_id: spec.variant_id,
    sku: spec.sku,
    nameFa: spec.nameFa,
    categoryCode: spec.categoryCode,
    categoryLabel: spec.categoryLabel,
    price_toman: spec.price_toman,
    stock_qty: spec.stock_qty,
    safe_threshold: spec.safe_threshold,
    stockCategory,
    alert,
    sync: {
      status: spec.syncStatus,
      // `clean` is a function of status: only a proven IN_SYNC row is clean.
      clean: spec.syncStatus === 'IN_SYNC',
      lastAttemptLogical: lastEntry.atLogical,
      woo: spec.woo,
      history,
    },
    lock: spec.lock,
    provenance: spec.provenance,
  };
}

/** Apply a scenario's overrides to the base catalog and build every row. */
function catalogFor(scenario: InventoryScenario): InventoryItem[] {
  if (scenario === 'all-unknown') return [];
  const overrides = scenario === 'low-stock-surge' ? LOW_STOCK_SURGE : scenario === 'sync-drift' ? SYNC_DRIFT : {};
  return BASE_CATALOG.map((base, index) => {
    const override = overrides[base.sku] ?? {};
    return buildItem({ ...base, ...override }, index);
  });
}

/** Count SKUs by stock and sync state. The summary is DERIVED, never typed twice. */
export function summarizeInventory(items: InventoryItem[]): InventorySummary {
  return {
    totalSkus: items.length,
    lowStockCount: items.filter((item) => item.stockCategory === 'LOW_STOCK').length,
    outOfStockCount: items.filter((item) => item.stockCategory === 'OUT_OF_STOCK').length,
    driftCount: items.filter((item) => item.sync.status === 'DRIFT_DETECTED').length,
    pendingSyncCount: items.filter((item) => item.sync.status === 'PENDING_SYNC').length,
    syncErrorCount: items.filter((item) => item.sync.status === 'SYNC_ERROR').length,
    totalStockUnits: items.reduce((total, item) => total + item.stock_qty, 0),
  };
}

function isPositiveInt(value: number | null): boolean {
  return typeof value === 'number' && Number.isInteger(value) && value > 0;
}

/**
 * Assert the snapshot cannot display a state the canonical rules forbid.
 *
 * Throwing is the fail-closed behaviour: a contradictory inventory is never
 * rendered with a reassuring badge.
 */
export function assertInventoryConsistency(snapshot: InventorySnapshot): InventorySnapshot {
  const problems: string[] = [];
  const seenSkus = new Set<string>();

  for (const item of snapshot.items) {
    const id = item.sku;

    if (seenSkus.has(id)) problems.push(`${id}: duplicate SKU in snapshot`);
    seenSkus.add(id);

    // ── identifiers (D-014/D-015/D-017) ─────────────────────────────────────
    if (!PRODUCT_ID_RE.test(item.product_id)) {
      problems.push(`${id}: product_id ${item.product_id} violates P##### (D-014)`);
    }
    if (!VARIANT_ID_RE.test(item.variant_id)) {
      problems.push(`${id}: variant_id ${item.variant_id} is not a canonical UUIDv4 (D-017)`);
    }
    const skuParts = item.sku.split('-');
    if (
      !SKU_RE.test(item.sku) ||
      skuParts.length > 3 ||
      !skuParts.slice(1).every((code) => APPROVED_AXIS_CODES.has(code))
    ) {
      problems.push(`${id}: SKU violates the D-014 format or uses a non-approved D-032 code`);
    }
    if (item.sku !== item.product_id && !item.sku.startsWith(`${item.product_id}-`)) {
      problems.push(`${id}: SKU must begin with its own product id plus axis codes (D-014)`);
    }
    if (!item.nameFa.trim()) problems.push(`${id}: nameFa must not be empty`);
    if (!item.categoryCode.trim() || !item.categoryLabel.trim()) {
      problems.push(`${id}: category code and label must not be empty`);
    }

    // ── money and stock (D-010 / D-082) ─────────────────────────────────────
    if (!Number.isInteger(item.price_toman) || item.price_toman <= 0) {
      problems.push(`${id}: price_toman must be a positive integer (D-010)`);
    }
    if (!Number.isInteger(item.stock_qty) || item.stock_qty < 0) {
      problems.push(`${id}: stock_qty must be an integer >= 0`);
    }
    if (!Number.isInteger(item.safe_threshold) || item.safe_threshold < 0) {
      problems.push(`${id}: safe_threshold must be an integer >= 0`);
    }

    const expectedCategory = stockCategoryOf(item.stock_qty, item.safe_threshold);
    if (item.stockCategory !== expectedCategory) {
      problems.push(
        `${id}: stockCategory ${item.stockCategory} != derived ${expectedCategory} (D-082)`,
      );
    }

    // ── low-stock alert invariant (owner directive) ──────────────────────────
    if (item.stock_qty <= item.safe_threshold) {
      if (item.alert === null) {
        problems.push(
          `${id}: stock ${item.stock_qty} <= threshold ${item.safe_threshold} without a low-stock alert (fail-closed)`,
        );
      } else if (item.alert.level !== expectedCategory) {
        problems.push(
          `${id}: alert level ${item.alert.level} != stock category ${expectedCategory}`,
        );
      }
    } else if (item.alert !== null) {
      problems.push(
        `${id}: healthy stock (${item.stock_qty} > ${item.safe_threshold}) carries an active alert — stale alerts must be cleared`,
      );
    }
    if (item.alert !== null) {
      if (!item.alert.reason.trim()) problems.push(`${id}: low-stock alert must state a reason`);
      if (!LOGICAL_RE.test(item.alert.raisedAtLogical)) {
        problems.push(`${id}: alert raisedAtLogical is not a logical-clock literal`);
      }
    }

    // ── sync state, drift and history ───────────────────────────────────────
    if (item.sync.clean !== (item.sync.status === 'IN_SYNC')) {
      problems.push(`${id}: clean must be true exactly when status is IN_SYNC`);
    }
    if (item.sync.status === 'DRIFT_DETECTED') {
      if (item.sync.clean) {
        problems.push(`${id}: DRIFT_DETECTED must never be marked clean/synced (D-003)`);
      }
      if (!item.sync.history.some((entry) => entry.outcome === 'DRIFT')) {
        problems.push(`${id}: DRIFT_DETECTED requires a DRIFT history entry`);
      }
    }
    if (item.sync.status === 'SYNC_ERROR' && !item.sync.history.some((entry) => entry.outcome === 'FAILED')) {
      problems.push(`${id}: SYNC_ERROR requires a FAILED history entry (D-052)`);
    }
    if (item.sync.status === 'IN_SYNC') {
      if (!item.sync.woo.active || item.sync.woo.productId === null) {
        problems.push(`${id}: IN_SYNC requires an active WooCommerce mapping (D-046)`);
      }
      if (!item.sync.history.some((entry) => entry.outcome === 'OK')) {
        problems.push(`${id}: IN_SYNC requires an OK history entry`);
      }
    }
    if (item.sync.history.length === 0) {
      problems.push(`${id}: sync history must not be empty`);
    }
    let previousSeq = 0;
    for (const entry of item.sync.history) {
      if (!Number.isInteger(entry.seq) || entry.seq <= previousSeq) {
        problems.push(`${id}: history seq must strictly increase (${entry.seq})`);
      }
      previousSeq = entry.seq;
      if (!LOGICAL_RE.test(entry.atLogical)) {
        problems.push(`${id}: history atLogical is not a logical-clock literal`);
      }
      if (!entry.detail.trim()) problems.push(`${id}: history detail must not be empty`);
      if (!entry.traceId.trim()) problems.push(`${id}: history traceId must not be empty (D-121)`);
    }
    if (!item.sync.woo.active) {
      if (item.sync.woo.productId !== null || item.sync.woo.variationId !== null) {
        problems.push(`${id}: inactive Woo mapping must not carry ids (D-046)`);
      }
    } else {
      if (!isPositiveInt(item.sync.woo.productId)) {
        problems.push(`${id}: active Woo mapping requires a positive product id (woo_live.py)`);
      }
      if (item.sync.woo.variationId !== null && !isPositiveInt(item.sync.woo.variationId)) {
        problems.push(`${id}: Woo variation id must be a positive int or null`);
      }
    }

    // ── lock ────────────────────────────────────────────────────────────────
    if (item.lock.state !== 'NONE') {
      if (!item.lock.reason || !item.lock.reason.trim()) {
        problems.push(`${id}: lock ${item.lock.state} must state its reason`);
      }
      if (item.lock.setAtLogical === null || !LOGICAL_RE.test(item.lock.setAtLogical)) {
        problems.push(`${id}: lock ${item.lock.state} must carry a logical-clock instant`);
      }
    } else if (item.lock.reason !== null || item.lock.setAtLogical !== null) {
      problems.push(`${id}: unlocked row must not carry a lock reason or instant`);
    }

    // ── D-026 provenance ────────────────────────────────────────────────────
    if (!SOURCE_TYPES.includes(item.provenance.sourceType)) {
      problems.push(`${id}: unknown provenance source type ${item.provenance.sourceType} (D-026)`);
    }
    if (!REVIEW_STATES.includes(item.provenance.reviewState)) {
      problems.push(`${id}: unknown review state ${item.provenance.reviewState} (D-026)`);
    }
    if (!item.provenance.actor.trim()) problems.push(`${id}: provenance actor must not be empty`);
  }

  // ── summary is derived, never retyped ─────────────────────────────────────
  const expected = summarizeInventory(snapshot.items);
  for (const key of Object.keys(expected) as Array<keyof InventorySummary>) {
    if (snapshot.summary[key] !== expected[key]) {
      problems.push(`summary.${key} ${snapshot.summary[key]} != ${expected[key]}`);
    }
  }

  // ── gated actions (D-146 / D-171 §6) ──────────────────────────────────────
  for (const action of snapshot.actions) {
    if (action.enabled && (!snapshot.gate.tokenPresent || !snapshot.gate.writePathConnected)) {
      problems.push(
        `${action.id}: action enabled without an owner token and a connected write path (D-146/D-171 §6)`,
      );
    }
    if (action.enabled && action.blockedReason.length > 0) {
      problems.push(`${action.id}: enabled action must not carry a blocked reason`);
    }
    if (!action.enabled && !action.blockedReason.trim()) {
      problems.push(`${action.id}: disabled action must state why it is unavailable`);
    }
  }

  if (problems.length > 0) {
    throw new Error(`fail-closed violation in inventory snapshot: ${problems.join('; ')}`);
  }
  return snapshot;
}

/**
 * The three gated write paths (D-171 §5.3/§6). Every action is DISABLED, each
 * with its own Persian reason: the UI neither mints a single-use owner token
 * (D-146) nor owns the canonical/webhook write path, and this phase is
 * mock-only. A disabled control always says why (D-171 §6).
 */
const NO_WRITE_PATH_REASON =
  'نوشتن فقط از مسیر canonical یا وب‌هوک امضاشده مجاز است (D-171 §6)؛ این رابط هنوز به آن متصل نیست';

const NO_TOKEN_REASON =
  'توکن یک‌بارمصرف مالک در رابط ساخته نمی‌شود (D-146)؛ در حالت نمونه هیچ کنش نوشتنی مجاز نیست';

const ACTIONS: InventoryActionSpec[] = [
  {
    id: 'RESYNC',
    title: 'همگام‌سازی ایمن',
    description:
      'ارسال قیمت و موجودی canonical به WooCommerce از مسیر همگام‌سازی رسمی، با ثبت رکورد لجر برای هر تلاش (D-034/D-121)',
    requiresSecondConfirmation: false,
    enabled: false,
    blockedReason: NO_WRITE_PATH_REASON,
  },
  {
    id: 'PRICE_FREEZE',
    title: 'قفل قیمت',
    description:
      'قفل انسانی روی قیمت این SKU تا حل واگرایی؛ نوشتن قیمت از سمت WooCommerce در این بازه اعمال نمی‌شود',
    requiresSecondConfirmation: true,
    enabled: false,
    blockedReason: NO_TOKEN_REASON,
  },
  {
    id: 'STOCK_OVERRIDE',
    title: 'بازنویسی دستی موجودی',
    description:
      'اصلاح دستی موجودی این SKU با اعتبارسنجی پیش از ارسال و rollback در خطا؛ کنشی برگشت‌ناپذیر و نیازمند تأیید دوم (D-082)',
    requiresSecondConfirmation: true,
    enabled: false,
    blockedReason: NO_TOKEN_REASON,
  },
];

/** Build the full snapshot for a scenario, guarded for fail-closed consistency. */
export function mockInventory(scenario: InventoryScenario = 'steady'): InventorySnapshot {
  const items = catalogFor(scenario);
  const unavailable = scenario === 'all-unknown';
  const snapshot: InventorySnapshot = {
    generatedAt: MOCK_INSTANT,
    scenario,
    provenance: unavailable ? 'unavailable' : 'mock',
    items,
    summary: summarizeInventory(items),
    actions: ACTIONS,
    // No token and no write path exist in this phase, so every action must be
    // disabled — the guard enforces that pairing.
    gate: { tokenPresent: false, writePathConnected: false },
  };
  return assertInventoryConsistency(snapshot);
}

/**
 * Read the active scenario from the environment.
 *
 * Defaults to `steady`; an unrecognised value falls back to `all-unknown`, so a
 * typo can never render as a healthy catalog (fail-closed).
 */
export function activeInventoryScenario(): InventoryScenario {
  const raw = process.env.CP_INVENTORY_SCENARIO;
  if (raw === undefined || raw === '' || raw === 'steady') return 'steady';
  if (raw === 'low-stock-surge') return 'low-stock-surge';
  if (raw === 'sync-drift') return 'sync-drift';
  return 'all-unknown';
}

/** The mock implementation of the swap seam. */
export function createMockInventorySource(
  scenario: InventoryScenario = 'steady',
): InventoryDataSource {
  return {
    async load(): Promise<InventorySnapshot> {
      return mockInventory(scenario);
    },
  };
}

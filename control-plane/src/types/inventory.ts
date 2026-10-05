/**
 * Inventory & canonical SKU contracts (D-171 §5.3, Phase 27.5).
 *
 * These mirror the CANONICAL product/inventory vocabulary rather than inventing
 * a UI-only one, so a reader can diff this file against the engine and see the
 * same words:
 *
 *   - identifiers — Product ID `P#####`, Variant ID (canonical lowercase
 *     hyphenated UUIDv4), SKU `P#####[-CC][-SS]` with D-032 approved axis
 *     codes: `local/canonical/identifiers.py` (D-014/D-015/D-017). All three are
 *     rendered SEPARATELY and none is derived from another (D-015).
 *   - stock identity — the SKU is the stock-keeping identity (D-082,
 *     `local/canonical/oms_contracts.py`).
 *   - money — integer Toman with no decimals anywhere (D-010).
 *   - provenance — the five D-026 source types and three review states
 *     (`local/canonical/identifiers.py`), never a UI invention.
 *   - WooCommerce mapping — positive integer product/variation ids, mirroring
 *     `local/canonical/woo_live.py` and the D-046 mapping registry.
 *
 * The four sync states (`IN_SYNC`, `PENDING_SYNC`, `SYNC_ERROR`,
 * `DRIFT_DETECTED`) are the control plane's presentation codes for the
 * WooCommerce link state. `DRIFT_DETECTED` means canonical and Woo side
 * disagree; no row carrying it may be described as clean or synced.
 *
 * Everything here is a VIEW MODEL: no type in this file authorises a write.
 * Authorisation is a single-use owner token (D-146) plus the canonical/webhook
 * write path (D-171 §6), and this phase holds neither.
 */

import type { Provenance } from './telemetry';

/**
 * WooCommerce link state.
 *
 * `PENDING_SYNC` and `SYNC_ERROR_*` are work outstanding; `DRIFT_DETECTED` is a
 * conflict that must stay explicit until a human resolves it (fail-closed).
 */
export type SyncStatus =
  | 'IN_SYNC'
  | 'PENDING_SYNC'
  | 'SYNC_ERROR'
  | 'DRIFT_DETECTED';

/**
 * Stock state, DERIVED from `stock_qty` against `safe_threshold` — never typed
 * independently (see `stockCategoryOf`). `stock_qty === 0` is OUT_OF_STOCK even
 * when the threshold is also zero.
 */
export type StockCategory = 'IN_STOCK' | 'LOW_STOCK' | 'OUT_OF_STOCK';

/**
 * Manual lock on a row. `PRICE_FREEZE` pins the price against sync writes;
 * `STOCK_OVERRIDE` pins the stock quantity against Woo-side reconciliation.
 * Both are human acts and therefore carry who/why/when.
 */
export type LockState = 'NONE' | 'PRICE_FREEZE' | 'STOCK_OVERRIDE';

/** D-026 provenance source types (canonical tuple). */
export type SourceType =
  | 'HUMAN_ENTERED'
  | 'SYSTEM_GENERATED'
  | 'AI_GENERATED'
  | 'IMPORTED'
  | 'EXTERNAL_SYNC';

/** D-026 review states (canonical tuple). */
export type ReviewState = 'PENDING' | 'HUMAN_REVIEWED' | 'HUMAN_VERIFIED';

/**
 * An active low-stock/out-of-stock alert.
 *
 * Its existence is not optional while `stock_qty <= safe_threshold`: the
 * build-time guard rejects a row that is at or below its threshold without one,
 * because that is exactly the state an operator would miss.
 */
export interface LowStockAlert {
  level: 'LOW_STOCK' | 'OUT_OF_STOCK';
  /** Persian explanation shown next to the row. Never empty. */
  reason: string;
  /** Logical-clock instant the alert was raised (D-093 precedent). */
  raisedAtLogical: string;
}

/**
 * WooCommerce mapping (D-046 registry entry, `woo_live.py` contract).
 *
 * `productId` and `variationId` are positive integers or `null`; a mapping with
 * `active: false` carries no ids at all, so "unmapped" can never be rendered as
 * a stale-but-plausible number.
 */
export interface WooMapping {
  productId: number | null;
  variationId: number | null;
  /** True only while the D-046 registry entry is `active`. */
  active: boolean;
}

/** One entry of the WooCommerce sync history shown in the expandable row. */
export interface SyncHistoryEntry {
  /** Monotonic sequence within the item. */
  seq: number;
  /** Logical-clock instant (fixed literals in the mock — D-093 precedent). */
  atLogical: string;
  direction: 'PUSH' | 'PULL' | 'RECONCILE';
  outcome: 'OK' | 'FAILED' | 'DRIFT';
  /** Persian description of what happened. Never empty. */
  detail: string;
  /** D-121 trace id. Never a credential (D-114/D-124). */
  traceId: string;
}

/** Link state of one row against WooCommerce. */
export interface ItemSync {
  status: SyncStatus;
  /**
   * True only when canonical and Woo are PROVEN equal. `clean` is a function
   * of `status` (only `IN_SYNC` is clean); the guard rejects any row that
   * claims to be clean while carrying drift.
   */
  clean: boolean;
  /** Logical instant of the last completed sync attempt, or `null`. */
  lastAttemptLogical: string | null;
  woo: WooMapping;
  /** Sync history, oldest first. At least one entry per row. */
  history: SyncHistoryEntry[];
}

/** Manual lock carried by one row, with its own explanation. */
export interface ItemLock {
  state: LockState;
  /** Persian reason — required whenever the state is not `NONE`. */
  reason: string | null;
  setAtLogical: string | null;
}

/** D-026 provenance attached to the row. */
export interface ItemProvenance {
  sourceType: SourceType;
  reviewState: ReviewState;
  /** Actor reference (`role:*` / `system:*` / `import:*`) — never a secret. */
  actor: string;
}

/**
 * One canonical SKU row as the table renders it.
 *
 * Identity is carried as three separate values — `product_id`, `variant_id`,
 * `sku` — because D-015 forbids deriving any of them for display. The table
 * renders each in its own column.
 */
export interface InventoryItem {
  /** `P#####` (D-014). */
  product_id: string;
  /** Canonical lowercase hyphenated UUIDv4 (D-017). */
  variant_id: string;
  /** `P#####[-CC][-SS]`, D-014 format with D-032 approved axis codes. */
  sku: string;
  /** Persian product name (localised). */
  nameFa: string;
  /** Presentation category of the mock catalog entry (tech/digital/accessory). */
  categoryCode: string;
  categoryLabel: string;
  /** Integer Toman, never decimal (D-010). */
  price_toman: number;
  /** On-hand quantity for this SKU. SKU is the stock identity (D-082). */
  stock_qty: number;
  /** Reorder threshold; `stock_qty <= safe_threshold` requires an alert. */
  safe_threshold: number;
  /** Derived state — must equal `stockCategoryOf(stock_qty, safe_threshold)`. */
  stockCategory: StockCategory;
  /** Non-null exactly when the row is at or below its threshold. */
  alert: LowStockAlert | null;
  sync: ItemSync;
  lock: ItemLock;
  provenance: ItemProvenance;
}

/**
 * The three gated write paths of this screen (D-171 §5.3/§6).
 *
 * They are rendered DISABLED with their own stated reason: the UI neither
 * mints a single-use owner token (D-146) nor owns the canonical/webhook write
 * path, and the phase is mock-only. An `enabled` action therefore requires a
 * real token AND a connected write path — the guard rejects any other
 * combination.
 */
export type InventoryActionId = 'RESYNC' | 'PRICE_FREEZE' | 'STOCK_OVERRIDE';

/** One gated action. `blockedReason` is non-optional, so a disabled control
 * can never render without telling the operator why (D-171 §6). */
export interface InventoryActionSpec {
  id: InventoryActionId;
  /** Persian action title. */
  title: string;
  /** Persian description of what the action would do once wired. */
  description: string;
  /** True when the action mutates downstream state via the canonical service
   * or the signed n8n webhook (D-171 §6) and needs a second confirmation. */
  requiresSecondConfirmation: boolean;
  enabled: boolean;
  /** Persian reason the action is unavailable. Never empty. */
  blockedReason: string;
}

/** The gate state every action is judged against. */
export interface InventoryGate {
  /** A single-use owner token is present. Always false in this phase (D-146). */
  tokenPresent: boolean;
  /** The canonical/webhook write path is reachable. Always false here. */
  writePathConnected: boolean;
}

/** Derived roll-up; the metrics banner renders exactly this. */
export interface InventorySummary {
  totalSkus: number;
  /** Rows with `LOW_STOCK` (excluding OUT_OF_STOCK). */
  lowStockCount: number;
  outOfStockCount: number;
  /** Active WooCommerce drift count (D-003/D-034–D-045). */
  driftCount: number;
  pendingSyncCount: number;
  syncErrorCount: number;
  /** Total on-hand units across every SKU. */
  totalStockUnits: number;
}

/** Everything the inventory screen renders in one request. */
export interface InventorySnapshot {
  /** ISO-8601 instant this snapshot describes (fixed literal for the mock). */
  generatedAt: string;
  scenario: string;
  /** Provenance of the snapshot as a whole. */
  provenance: Provenance;
  items: InventoryItem[];
  summary: InventorySummary;
  actions: InventoryActionSpec[];
  gate: InventoryGate;
}

/**
 * The single swap seam for live wiring.
 *
 * The page depends on this interface only, so replacing the deterministic mock
 * with the canonical read path requires no component changes.
 */
export interface InventoryDataSource {
  load(): Promise<InventorySnapshot>;
}

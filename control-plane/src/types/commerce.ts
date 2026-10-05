/**
 * Commerce contracts for the Unified Web Control Plane (D-171 §5.6, Phase 27.8).
 *
 * Vocabulary is CANONICAL, never invented here:
 *
 *   - the lifecycle is the D-081 state machine
 *     (`PLACED → VALIDATED → FULFILLING → COMPLETED`, with `CANCELLED` and the
 *     single audit-legal exit `COMPLETED → REFUNDED`; `oms_contracts.py`). The
 *     UI's fulfillment view is a presentation lens over it, and the build-time
 *     guard rejects any pairing the state machine cannot produce;
 *   - money is plain INTEGER Toman (D-010) — there is no float anywhere in
 *     this module and no decimals in any rendered amount;
 *   - the gateway log is MASKED by construction (D-114/D-124): audit entries
 *     carry a masked reference and never a PAN, an auth code or a gateway key;
 *   - shipping has NO provider — `UNSELECTED` mirrors open decision 11, and
 *     payment is DRY-RUN because the provider is not selected (open
 *     decision 10): no real payment path exists in the UI.
 *
 * Fail-closed rules encoded in the types: a `FAILED` payment can never be
 * `SHIPPED`/`DELIVERED` (the guard rejects it), a `REFUNDED` payment exists
 * only on the D-081 legal exit from `COMPLETED`, and every write action is
 * disabled unless an owner token AND a selected provider both exist — neither
 * of which this phase has.
 */

/** Canonical order identifier, `ORD-#####` (owner directive). */
export type OrderId = string;

/** Sales channel tags (D-171 §5.6). */
export type Channel = 'telegram' | 'instagram_dm' | 'web_store';

/**
 * Gateway-side payment state (owner directive). The canonical OMS keeps
 * payment as a BOUNDARY (D-083: only `pending`/`unpaid` markers); this view
 * mirrors the WooCommerce/gateway event state, never a stored credential.
 */
export type PaymentStatus = 'PAID' | 'PENDING_PAYMENT' | 'FAILED' | 'REFUNDED';

/** Fulfillment lens over the D-081 lifecycle (presentation taxonomy). */
export type FulfillmentStatus =
  | 'UNFULFILLED'
  | 'PROCESSING'
  | 'SHIPPED'
  | 'DELIVERED'
  | 'CANCELLED';

/** The canonical D-081 lifecycle states. */
export type LifecycleState =
  | 'PLACED'
  | 'VALIDATED'
  | 'FULFILLING'
  | 'COMPLETED'
  | 'CANCELLED'
  | 'REFUNDED';

/** Order risk bucket; the numeric score is the source of truth. */
export type RiskLevel = 'LOW' | 'MEDIUM' | 'HIGH';

/** Settlement position of captured money. */
export type SettlementState = 'SETTLED' | 'PENDING' | 'NOT_APPLICABLE' | 'REFUNDED';

/** One line item bound to a canonical SKU (D-015/D-017: never derived). */
export interface OrderItem {
  sku: string;
  titleFa: string;
  quantity: number;
  unitPriceToman: number;
  lineTotalToman: number;
}

/** One D-081 transition, carrying its D-121 trace id. */
export interface StatusHistoryEntry {
  state: LifecycleState;
  atUtc: string;
  noteFa: string;
  traceId: string;
}

/**
 * One gateway audit entry — MASKED by construction (D-114/D-124).
 * `gatewayRefMasked` always contains the mask marker; no PAN, no auth code,
 * no gateway key exists anywhere in this shape.
 */
export interface PaymentAuditEntry {
  atUtc: string;
  eventFa: string;
  gatewayRefMasked: string;
  outcome: 'OK' | 'FAILED' | 'PENDING';
  amountToman: number;
  traceId: string;
}

/** Shipping state: provider UNSELECTED (open decision 11), tracking optional. */
export interface ShippingInfo {
  provider: 'UNSELECTED';
  statusFa: string;
  trackingNumber: string | null;
}

/** D-084 receipt reference; integer Toman only. */
export interface Receipt {
  receiptId: string;
  kind: 'ISSUED' | 'REFUND';
  issuedAtUtc: string;
  totalToman: number;
}

/** One order as the table and drawer render it. */
export interface Order {
  orderId: OrderId;
  /** WooCommerce numeric id (D-046 mapping), or null when not yet mapped. */
  wooOrderId: number | null;
  customerNameFa: string;
  channel: Channel;
  totalToman: number;
  paymentStatus: PaymentStatus;
  fulfillmentStatus: FulfillmentStatus;
  lifecycle: LifecycleState;
  settlement: SettlementState;
  placedAtUtc: string;
  lastUpdateUtc: string;
  /** 0..100; `riskLevel` is derived from it, never typed independently. */
  riskScore: number;
  riskLevel: RiskLevel;
  items: OrderItem[];
  history: StatusHistoryEntry[];
  paymentAudit: PaymentAuditEntry[];
  shipping: ShippingInfo;
  receipts: Receipt[];
}

/** Derived revenue roll-up; the KPI strip renders exactly this. */
export interface RevenueSummary {
  dailyGmvToman: number;
  weeklyGmvToman: number;
  aovToman: number;
  pendingSettlementToman: number;
  failedPaymentCount: number;
  completedOrderCount: number;
  pendingProcessingCount: number;
  /** Orders whose payment failed and therefore settled to nothing. */
  paidOrderCount: number;
}

/**
 * Gated write actions (D-171 §5.6/§6). All are rendered DISABLED: this UI
 * holds no single-use owner token (D-146) and no payment/shipping provider is
 * selected (open decisions 10/11), so an enabled control would look live while
 * being unable to authorise anything.
 */
export type CommerceActionId = 'MARK_SHIPPED' | 'ISSUE_INVOICE' | 'RETRY_PAYMENT';

/** One gated action. `blockedReasonFa` is non-optional. */
export interface CommerceActionSpec {
  id: CommerceActionId;
  titleFa: string;
  descriptionFa: string;
  requiresSecondConfirmation: boolean;
  enabled: boolean;
  /** Persian reason the action is unavailable. Never empty. */
  blockedReasonFa: string;
}

/** The facts every action is judged against. */
export interface CommerceWriteGate {
  /** A single-use owner token is present. Always false in this phase (D-146). */
  tokenPresent: boolean;
  /** A payment/shipping provider is selected. Always false (decisions 10/11). */
  providerSelected: boolean;
}

/** Everything the commerce screen renders in one request. */
export interface CommerceSnapshot {
  /** ISO-8601 instant this snapshot describes (fixed literal for the mock). */
  generatedAt: string;
  scenario: string;
  provenance: import('@/types/telemetry').Provenance;
  orders: Order[];
  summary: RevenueSummary;
  actions: CommerceActionSpec[];
  gate: CommerceWriteGate;
}

/**
 * The single swap seam for live wiring: the page depends on this interface
 * only, so replacing the deterministic mock with live WooCommerce/OMS reads
 * requires no component changes.
 */
export interface CommerceDataSource {
  load(): Promise<CommerceSnapshot>;
}

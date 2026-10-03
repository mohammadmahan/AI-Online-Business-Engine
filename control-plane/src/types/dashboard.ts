/**
 * Dashboard view-model contracts (D-171 §5.1).
 *
 * These types describe what the executive overview RENDERS. They are kept
 * separate from `telemetry.ts` on purpose: telemetry is what a probe reports,
 * this is what the page decides to show. The single seam between the two is
 * `DashboardDataSource` at the bottom of this file.
 */

import type { Provenance, ServiceHealth, Trend } from './telemetry';

/** The four executive KPI cards. */
export type KpiId =
  | 'orders_revenue'
  | 'hitl_pending'
  | 'automations_running'
  | 'anomalies';

/**
 * Attention level of a KPI — NOT a verification result.
 *
 * `ok` means "nothing here needs attention in this sample", not "verified".
 * Verification is expressed by `provenance`, which is always rendered
 * alongside the value.
 */
export type KpiState = 'ok' | 'warn' | 'alert' | 'unknown';

export interface KpiCard {
  id: KpiId;
  title: string;
  /** English code, kept for traceability. */
  code: string;
  /** Pre-formatted value using Latin digits (D-171 §3.1). */
  value: string;
  unit?: string;
  /** Secondary reading shown under the primary one. */
  secondary?: string;
  trend: Trend | null;
  /** Which direction is healthy, so colouring is a rule rather than a guess. */
  goodWhen: 'up' | 'down';
  state: KpiState;
  /** Persian explanation of the state. Never empty. */
  detail: string;
  provenance: Provenance;
  /** Internal route this card drills into, when one exists. */
  href?: '/hitl-queue';
}

/** Severity of a pending human-review item. */
export type Severity = 'critical' | 'high' | 'medium' | 'low';

export interface PendingApproval {
  id: string;
  severity: Severity;
  /** Persian category label. */
  category: string;
  /** Originating system. */
  source: string;
  /** Persian relative age, pre-formatted by the provider. */
  age: string;
  summary: string;
}

export interface SystemEvent {
  id: string;
  /** ISO-8601 instant. */
  at: string;
  /** English event kind code (D-121 style). */
  kind: string;
  summary: string;
  /** D-121 trace identifier. Never a credential (D-114/D-124). */
  traceId: string;
}

/**
 * An emergency control shown as a preview.
 *
 * In this phase every action is disabled: no signed webhook path is connected,
 * so activating one would be a control that looks live but does nothing — the
 * anti-pattern the design rules call out. The card states the reason instead.
 */
export interface EmergencyAction {
  id: 'soft_pause' | 'flush_preview';
  title: string;
  description: string;
  /** Persian description of what the action WOULD do once wired. */
  effect: string;
  requiresSecondConfirmation: boolean;
  enabled: boolean;
  /** Persian reason the action is unavailable. Never empty. */
  blockedReason: string;
}

/** Everything the executive overview renders in one request. */
export interface DashboardSnapshot {
  /** ISO-8601 instant this snapshot describes. */
  generatedAt: string;
  /** Name of the deterministic scenario in effect. */
  scenario: string;
  /** Provenance of the snapshot as a whole. */
  provenance: Provenance;
  services: ServiceHealth[];
  kpis: KpiCard[];
  /** Only the top items; `pendingApprovalsTotal` carries the full count. */
  pendingApprovals: PendingApproval[];
  pendingApprovalsTotal: number;
  events: SystemEvent[];
  emergencyActions: EmergencyAction[];
}

/**
 * The single swap seam for live wiring (Phases 5–18).
 *
 * The page depends on this interface only, so replacing the mock with a
 * probe-backed implementation requires no component changes.
 */
export interface DashboardDataSource {
  load(): Promise<DashboardSnapshot>;
}

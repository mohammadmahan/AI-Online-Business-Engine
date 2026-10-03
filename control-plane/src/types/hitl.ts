/**
 * HITL Review Queue contracts (D-171 §5.2, Phase 27.4).
 *
 * These mirror the CANONICAL Phase 18 engine vocabulary
 * (`local/canonical/hitl_contracts.py`, D-105/D-106/D-108) rather than
 * inventing a UI-only vocabulary. Field names are kept in the engine's own
 * snake_case for the identity-bearing values so a reader can diff this file
 * against the engine and see the same words:
 *
 *   - queue types:    INSIGHT_REVIEW | PUBLISH_GATE | ORDER_OVERRIDE | ASSET_FLAG
 *   - lifecycle:      PENDING_REVIEW → CLAIMED → APPROVED | REJECTED |
 *                     MODIFIED | ESCALATED | EXPIRED
 *   - required roles: any | owner | publisher | ops | escalation
 *
 * `EXPIRED` is reachable ONLY from the deterministic sweep, never from a
 * reviewer action — so it is deliberately absent from `ReviewDecision`.
 *
 * Everything here is a VIEW MODEL: it describes what the queue renders. No
 * type in this file implies that a decision was authorised — authorisation is
 * a single-use owner token (D-146) that this phase does not hold.
 */

import type { Severity } from './dashboard';

/**
 * The canonical severity taxonomy, re-exported so the queue and the executive
 * overview cannot drift apart. Codes are uppercase in the engine
 * (`analyst_contracts.py`, D-101); the UI renders the Persian label with the
 * English code as a secondary cue.
 */
export type HitlSeverity = Severity;

/** Queue types (D-105). */
export type QueueType =
  | 'INSIGHT_REVIEW'
  | 'PUBLISH_GATE'
  | 'ORDER_OVERRIDE'
  | 'ASSET_FLAG';

/**
 * Lifecycle status (D-105). `EXPIRED` is sweep-only and never a reviewer
 * decision, so it appears here but not in `ReviewDecision`.
 */
export type ResolutionStatus =
  | 'PENDING_REVIEW'
  | 'CLAIMED'
  | 'APPROVED'
  | 'REJECTED'
  | 'MODIFIED'
  | 'ESCALATED'
  | 'EXPIRED';

/** Reviewer class that may resolve a ticket (D-105). */
export type RequiredRole = 'any' | 'owner' | 'publisher' | 'ops' | 'escalation';

/**
 * What a reviewer may submit. `EXPIRED` is absent by design (D-105): expiry is
 * decided by the deterministic sweep from an injected logical clock, never by
 * a human clicking a button.
 */
export type ReviewDecision = 'APPROVED' | 'REJECTED' | 'MODIFIED' | 'ESCALATED';

/** One field of the proposed payload, with its current value for diffing. */
export interface PayloadField {
  /** Field name as the engine stores it. */
  field: string;
  /** Current value, rendered as text. */
  before: string;
  /** Proposed value, rendered as text. */
  after: string;
  /** True when the proposal changes the value. */
  changed: boolean;
}

/**
 * One step of the reasoning log, REBUILT from D-027 events.
 *
 * This is explicitly not the model's raw chain-of-thought (D-171 §5.2): each
 * step is a durable event the engine already emitted, carrying its D-121 trace
 * id so an operator can follow it into the ledger.
 */
export interface ReasoningStep {
  /** Monotonic sequence within the ticket. */
  seq: number;
  /** Logical-clock stamp (never wall clock — D-093/D-101 precedent). */
  atLogical: string;
  /** D-027 event kind. */
  event: string;
  /** Persian explanation of what the event recorded. */
  summary: string;
  /** D-121 trace identifier. Never a credential (D-114/D-124). */
  traceId: string;
}

/** A ticket as the queue renders it. */
export interface HitlTicket {
  ticket_id: string;
  queue_type: QueueType;
  severity: HitlSeverity;
  /** Canonical category code from the D-101 taxonomy. */
  category: string;
  /** Persian category label. */
  categoryLabel: string;
  payload_ref: string;
  required_role: RequiredRole;
  resolution_status: ResolutionStatus;
  /**
   * Reviewer actor reference (`role:*` / `agent:*`) — `null` while the ticket
   * is PENDING_REVIEW or EXPIRED, because neither state has a reviewer.
   */
  reviewer_actor_id: string | null;
  /** Logical-clock creation stamp. */
  created_at_logical: string;
  /** Persian relative age, pre-formatted by the provider. */
  ageLogical: string;
  /** Persian one-line summary of what the AI proposed. */
  summary: string;
  /** Persian origin of the proposal. */
  source: string;
  /** Proposed payload fields, with current values for the diff. */
  payload: PayloadField[];
  /** Reasoning log rebuilt from D-027 events. */
  reasoning: ReasoningStep[];
}

/**
 * One of the four one-click decisions.
 *
 * In this phase EVERY action is disabled, and the type forces the reason to be
 * carried: `blockedReason` is non-optional, so a disabled control can never be
 * rendered without telling the operator why. This is the D-171 §6 rule — no
 * control may look live while doing nothing.
 */
export interface HitlActionSpec {
  decision: ReviewDecision;
  /** Persian action title. */
  title: string;
  /** Persian description of what the action would do once wired. */
  description: string;
  /**
   * True when the action mutates downstream state through the dispatcher
   * (D-107) and therefore needs a second confirmation.
   */
  requiresSecondConfirmation: boolean;
  enabled: boolean;
  /** Persian reason the action is unavailable. Never empty. */
  blockedReason: string;
}

/** Severity-first ordering summary shown above the table. */
export interface HitlQueueSummary {
  total: number;
  bySeverity: Record<HitlSeverity, number>;
  byStatus: Record<ResolutionStatus, number>;
  /** True when at least one ticket is CRITICAL and still awaiting review. */
  hasCriticalPending: boolean;
}

/** Everything the queue renders in one request. */
export interface HitlQueueSnapshot {
  /** ISO-8601 instant this snapshot describes (fixed literal for the mock). */
  generatedAt: string;
  scenario: string;
  /** Provenance of the snapshot as a whole. */
  provenance: 'live' | 'mock' | 'unavailable';
  tickets: HitlTicket[];
  summary: HitlQueueSummary;
  actions: HitlActionSpec[];
  /**
   * Whether a single-use owner token is present. Always `false` in this phase:
   * the UI neither mints nor holds tokens (D-146), so every action is disabled.
   */
  tokenPresent: boolean;
}

/**
 * The single swap seam for live wiring (Phases 5–18).
 *
 * The page depends on this interface only, so replacing the mock with the real
 * HITL engine (D-106) requires no component changes.
 */
export interface HitlQueueDataSource {
  load(): Promise<HitlQueueSnapshot>;
}

/**
 * AI Ops & Shared Memory Hub contracts — D-171 §4 Phase 5, §5.5 `/ai-engine`.
 *
 * These types describe OBSERVATIONS about the AI runtime, never decisions and
 * never affordances: an unmeasured value is `null` (or `UNKNOWN`) with a stated
 * reason, so a surface can never be rendered as if a reading existed
 * (D-171 §2.2, fail-closed). Nothing here holds a provider handle, a credential
 * or a memory connection — the memory layer is PLANNED behind the D-045 owner
 * gate (D-142), so its honest steady state is `NOT_CONNECTED` with no
 * namespaces and no counts.
 *
 * ── Canonical grounding (vocabulary is taken, not invented) ──────────────────
 * - the shared-memory layer is D-142 (`MystenLabs/MemWal`, Walrus Memory):
 *   PLANNED, external connectivity owner-gated (D-045), local parity backend
 *   already shipped under `local/src/memory/`.
 * - `AiRouteId` values are the canonical task types
 *   (`local/canonical/ai_tasks.py`: `propose_content_idea`, `generate_caption`,
 *   `enrich_description`).
 * - `ObserveStageId` values are the canonical observability stages of the
 *   `ai.observe.v1` schema (`local/canonical/ai_observability.py`, D-065).
 *   The schema records pipeline STAGES — there is no tool-calling registry in
 *   the canonical engine, so this screen reports stage usage and never invents
 *   a tool list.
 * - `BudgetResource` / `BudgetWindow` values are the D-127 resource-budget
 *   vocabulary (`local/canonical/budget_contracts.py`); the soft ratio that
 *   turns a consumption into a warning is the canonical 0.8 (D-063-identical).
 * - `ProposalState` is the D-064 proposal lifecycle
 *   (`local/canonical/ai_proposal_lifecycle.py`):
 *   PROPOSED → IN_REVIEW → {ACCEPTED, REJECTED, MODIFIED_BY_HUMAN}.
 * - proposal ids mirror the canonical durable event-id form `aiprop|<pid>`
 *   so a console row can be traced back to its lifecycle events.
 *
 * Money and latency are INTEGERS here, mirroring the canonical precision
 * (`cost_usd` is recorded at 1e-6; `latency_ms` is whole milliseconds) so no
 * floating-point money ever reaches a renderer (D-010 discipline applied to AI
 * spend).
 */

import type { Provenance } from '@/types/telemetry';

/**
 * Shared-memory layer status (D-142).
 *
 * `NOT_CONNECTED` is the mandated, explicit state until the D-045 owner gate is
 * passed (D-171 §5.5); it is NOT an error and never a zero reading.
 */
export type MemoryConnectionState = 'NOT_CONNECTED' | 'CONNECTED' | 'DEGRADED' | 'UNKNOWN';

/** One named memory namespace. Exists only while the layer is connected. */
export interface MemoryNamespace {
  name: string;
  vectors: number;
  bytes: number;
}

/** Everything this screen reports about the shared-memory layer. */
export interface MemoryLayerStatus {
  state: MemoryConnectionState;
  /** Persian explanation of the state. Never empty. */
  detailFa: string;
  /** EMPTY unless the layer is CONNECTED or DEGRADED. */
  namespaces: MemoryNamespace[];
  /** Total vectors across namespaces; `null` when never measured — never 0. */
  totalVectors: number | null;
  /** Total stored bytes; `null` when never measured — never 0. */
  totalBytes: number | null;
  /** ISO-8601 instant of the last measurement, or `null` when never measured. */
  lastMeasuredUtc: string | null;
  provenance: Provenance;
}

/** The canonical AI execution routes (task types, `ai_tasks.py`). */
export type AiRouteId = 'propose_content_idea' | 'generate_caption' | 'enrich_description';

/** The canonical observability stages of `ai.observe.v1` (D-065). */
export type ObserveStageId =
  | 'provider_call'
  | 'validation'
  | 'divergence'
  | 'lifecycle'
  | 'hitl_decision'
  | 'fallback';

/** How often one canonical stage was recorded for a route. */
export interface AgentStageUsage {
  stage: ObserveStageId;
  invocations: number;
}

/**
 * Agent observability for one execution route (D-171 §5.5).
 *
 * Readings are all-or-nothing: a route is either MEASURED (invocations,
 * successes, failures, rate and latency all present) or UNMEASURED (every one
 * of them `null`). Zero invocations is a measured route whose success rate is
 * `null` — never 100%.
 */
export interface AgentRouteObservability {
  id: AiRouteId;
  /** Persian title of the route. Never empty. */
  titleFa: string;
  invocations: number | null;
  succeeded: number | null;
  failed: number | null;
  /** Derived percentage 0..100, or `null` when nothing was invoked. */
  successRatePercent: number | null;
  /** P95 latency in whole milliseconds, or `null` when never measured. */
  p95LatencyMs: number | null;
  /** ISO-8601 instant of the last run, or `null` when never run. */
  lastRunUtc: string | null;
  /** Canonical stages this route touched; EMPTY while the route is unmeasured. */
  stages: AgentStageUsage[];
}

/** Canonical D-127 resource classes (`budget_contracts.py`). */
export type BudgetResource =
  | 'llm_tokens'
  | 'llm_calls'
  | 'api_calls'
  | 'container_cpu_seconds'
  | 'container_memory_mb'
  | 'memory_ops';

/** Canonical D-127 budget windows. */
export type BudgetWindow = 'per_run' | 'per_logical_day';

/**
 * Budget pressure derived from the consumed ratio.
 *
 * `UNKNOWN` is first-class: an unmeasured consumption is never `OK`.
 */
export type BudgetPressure = 'OK' | 'WARNING' | 'EXCEEDED' | 'UNKNOWN';

/**
 * Token and cost analytics for one route (D-171 §5.5) under the D-063/D-127
 * ceilings.
 *
 * Two ceilings are reported side by side because the canonical engine has two:
 * the D-127 window allowance (`tokenCeiling`, the consumable this screen
 * meters) and the D-063 per-run budget of the route target
 * (`runBudgetMicroUsd`, integer micro-USD mirroring the canonical 1e-6 cost
 * precision).
 */
export interface TokenCostAnalytics {
  routeId: AiRouteId;
  /** Canonical provider id of the active route target. */
  provider: string;
  /** Canonical model id of the active route target. */
  model: string;
  promptTokens: number | null;
  completionTokens: number | null;
  /** Derived sum of the two readings, or `null` when both are absent. */
  totalTokens: number | null;
  resource: BudgetResource;
  window: BudgetWindow;
  /** Positive integer allowance for the window. */
  tokenCeiling: number;
  /** Derived totalTokens / tokenCeiling, or `null` when unmeasured. */
  consumedRatio: number | null;
  /** Derived from `consumedRatio` via the canonical soft ratio (D-063). */
  pressure: BudgetPressure;
  /** Integer micro-USD from the canonical tariff; `null` when unmeasured. */
  costMicroUsd: number | null;
  /** The route target's D-063 per-run budget as integer micro-USD. */
  runBudgetMicroUsd: number;
}

/** The canonical D-064 proposal lifecycle states. */
export type ProposalState =
  | 'PROPOSED'
  | 'IN_REVIEW'
  | 'ACCEPTED'
  | 'REJECTED'
  | 'MODIFIED_BY_HUMAN';

/** D-026 provenance of the latest mutation on a proposal. */
export type ProposalMutation = 'AI_GENERATED' | 'HUMAN_ENTERED';

/** One AI proposal draft and its D-060/D-064 lifecycle state. */
export interface AiProposalDraft {
  /** Canonical durable id form `aiprop|<pid>` (see the header note). */
  id: string;
  titleFa: string;
  routeId: AiRouteId;
  state: ProposalState;
  /** ISO-8601 instant the draft was proposed. */
  submittedAtUtc: string;
  /** ISO-8601 instant of the human decision; non-null exactly for a terminal state. */
  decidedAtUtc: string | null;
  lastMutation: ProposalMutation;
}

/**
 * Actions that would cross the read-only boundary (D-171 §5.5/§6).
 *
 * Every one is rendered DISABLED: running an agent route calls a provider,
 * querying the memory layer needs an external connection, and connecting the
 * layer is the D-045 owner gate itself. None of them may originate from this
 * interface, and a disabled control always states why (fail-closed).
 */
export type AiOpsControlId = 'RUN_AGENT_ROUTE' | 'QUERY_MEMORY' | 'CONNECT_MEMORY_LAYER';

/** One gated control. `blockedReasonFa` is non-optional. */
export interface AiOpsControlSpec {
  id: AiOpsControlId;
  titleFa: string;
  descriptionFa: string;
  enabled: boolean;
  /** Persian reason the control is unavailable. Never empty. */
  blockedReasonFa: string;
}

/**
 * The boundary state every control is judged against.
 *
 * Both flags are always false in this phase: the interface owns no provider
 * call path and holds no credential (D-171 §5.5 constraints / §6).
 */
export interface AiOpsProviderGate {
  providerCallPathConnected: boolean;
  credentialPresent: boolean;
}

/** Derived roll-up of the snapshot. */
export interface AiOpsOverview {
  memoryState: MemoryConnectionState;
  routesMeasured: number;
  routesUnmeasured: number;
  worstBudgetPressure: BudgetPressure;
  /** PROPOSED + IN_REVIEW. */
  proposalsAwaitingDecision: number;
  /** ACCEPTED + REJECTED + MODIFIED_BY_HUMAN. */
  proposalsDecided: number;
  /** True when any cost row reads WARNING or EXCEEDED. */
  hasBudgetAlert: boolean;
}

/** Everything the `/ai-engine` screen renders in one request. */
export interface AiOpsSnapshot {
  /** ISO-8601 instant this snapshot describes (fixed literal for the mock). */
  generatedAt: string;
  scenario: string;
  provenance: Provenance;
  /**
   * Which seam produced the snapshot. Only the deterministic mock exists today;
   * no live canonical read surface for AI ops has been wired (Phase 27.7
   * follow-up), and the memory layer itself is PLANNED (D-142).
   */
  sourceMode: 'MOCK' | 'LIVE';
  memory: MemoryLayerStatus;
  routes: AgentRouteObservability[];
  cost: TokenCostAnalytics[];
  proposals: AiProposalDraft[];
  controls: AiOpsControlSpec[];
  providerGate: AiOpsProviderGate;
  summary: AiOpsOverview;
}

/** The swap seam the page depends on, so a live source can replace the mock. */
export interface AiOpsDataSource {
  load(): Promise<AiOpsSnapshot>;
}

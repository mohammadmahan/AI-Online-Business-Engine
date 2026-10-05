/**
 * Telemetry contracts for the Unified Web Control Plane (D-171).
 *
 * These types describe MEASUREMENTS, not decisions: a probe either produced a
 * value at a known instant, or it did not. There is deliberately no default and
 * no "healthy" fallback anywhere in this module — an absent measurement is
 * `unknown` or `unavailable` with a null instant, never a zero that a reader
 * could mistake for a reading (D-171 §2.2, fail-closed).
 */

/** The infrastructure surfaces the control plane reports on (D-171 §5.1). */
export type ServiceId = 'postgres' | 'dokploy' | 'n8n' | 'walrus';

/**
 * Where a reported value came from.
 *
 * - `live`        — a real probe produced it during this request
 * - `mock`        — a deterministic sample; NOT evidence, never rendered PASS
 * - `unavailable` — no value exists because nothing is connected
 */
export type Provenance = 'live' | 'mock' | 'unavailable';

/**
 * Health of one service.
 *
 * `unknown` and `unavailable` are first-class outcomes, not error codes: they
 * are exactly what an honest probe reports before live wiring exists, and the
 * UI must be able to render them without implying success.
 */
export type HealthState = 'ok' | 'degraded' | 'unavailable' | 'unknown';

/** A single measured — or deliberately unmeasured — value. */
export interface Metric {
  /** Persian label; the primary carrier of meaning. */
  label: string;
  /** English code, kept for traceability. */
  code: string;
  /** Formatted value, or `null` when the value was never measured. */
  value: string | null;
  /** Optional unit suffix, already localised for display. */
  unit?: string;
}

/** Health payload for one infrastructure service. */
export interface ServiceHealth {
  id: ServiceId;
  title: string;
  /** English status/service code, shown alongside the Persian title. */
  code: string;
  state: HealthState;
  provenance: Provenance;
  /** Persian explanation of the state. Never empty. */
  detail: string;
  metrics: Metric[];
  /** ISO-8601 instant of the last measurement, or `null` when never measured. */
  lastMeasuredAt: string | null;
}

/** A change against the previous comparison window. */
export interface Trend {
  direction: 'up' | 'down' | 'flat';
  /** Magnitude in percent; always >= 0. */
  deltaPercent: number;
  /** Persian label of the comparison window, e.g. «نسبت به دیروز». */
  comparison: string;
}

/** Roll-up of a whole snapshot; drives the page-level alert strip. */
export interface TelemetrySummary {
  total: number;
  ok: number;
  degraded: number;
  unavailable: number;
  unknown: number;
  /** True when at least one service is not `ok`. */
  hasAlert: boolean;
  /** Highest-severity state present, so the strip can pick one badge. */
  worst: HealthState;
}

/**
 * ── Phase 27.6 — Telemetry, container health & pipeline gates ──────────────
 *
 * These mirror the CANONICAL deployment vocabulary rather than inventing one:
 *
 *   - the ten gates are the Cutover Verification Matrix V-01..V-09
 *     (`local/scripts/verify_cutover_readiness.py`, D-145, documented in
 *     `docs/deployment/stage-e-cutover-fingerprint-binding.md` §2) plus the
 *     Stage-F single-use owner authorization V-10
 *     (`docs/deployment/stage-f-authorization.md` §7, D-146/D-147). The
 *     verifier emits `PASS` / `FAIL` and exit code 2 = "cannot assess"; the
 *     control plane presents `FAIL` as `BLOCKED`, "cannot assess" as
 *     `EVALUATING`, and V-10's refusal semantics as `BYPASS_PREVENTED`.
 *   - containers are the surfaces the owner directive names (postgres, n8n,
 *     redis, dokploy, walrus); `containerRef` carries the concrete service
 *     name where a manifest defines one (Stage D topology names `redis` and
 *     `postgres-ssot`; the local rehearsal stack names `engine-local-*`), and
 *     is `null` when no service exists yet (Walrus is PLANNED, D-142).
 *
 * Fail-closed rules encoded in the types: metrics exist only when a probe
 * produced them (`metricsState: 'LIVE'`), a `DOWN` or `UNKNOWN` surface can
 * therefore never carry readable CPU/memory, and a gate is `passes: true` only
 * when its status IS `PASS` — the build-time guard rejects any other pairing.
 */

/** The five container surfaces this screen reports on (owner directive). */
export type ContainerId = 'postgres' | 'n8n' | 'redis' | 'dokploy' | 'walrus';

/**
 * Container state. `UNKNOWN` is first-class: an unprobed container is never
 * shown as healthy just because no failure was reported (D-171 §2.2).
 */
export type ContainerStatus = 'HEALTHY' | 'DEGRADED' | 'DOWN' | 'UNKNOWN';

/**
 * Whether a probe produced readings for this container. Derived from the
 * status, never typed independently: only HEALTHY/DEGRADED may be `LIVE`.
 */
export type MetricsState = 'LIVE' | 'UNAVAILABLE';

/** A measured container reading. Present exactly when `metricsState` is LIVE. */
export interface ContainerMetrics {
  /** 0..100. */
  cpuPercent: number;
  memoryUsedMb: number;
  memoryLimitMb: number;
  /** Whole seconds since the container started. */
  uptimeSeconds: number;
}

/** An active container incident; required for DEGRADED and DOWN. */
export interface ContainerIncident {
  severity: 'DEGRADED' | 'DOWN';
  /** Persian explanation. Never empty. */
  noteFa: string;
  /** ISO-8601 instant the incident was raised (fixed literal in the mock). */
  raisedAtUtc: string;
}

/** One container as the health grid renders it. */
export interface ContainerHealth {
  id: ContainerId;
  /** Persian title. */
  titleFa: string;
  /**
   * Concrete container/service reference from a manifest, or `null` when no
   * service exists yet. Never invented.
   */
  containerRef: string | null;
  status: ContainerStatus;
  /** Derived: `LIVE` exactly for HEALTHY/DEGRADED. */
  metricsState: MetricsState;
  /** Non-null exactly when `metricsState` is `LIVE`. */
  metrics: ContainerMetrics | null;
  /** Published port mapping as declared, or `null` when none is published. */
  portMapping: string | null;
  /** ISO-8601 instant of the last probe, or `null` when never probed. */
  lastProbeUtc: string | null;
  /** Persian description of what this surface is and how it is known. */
  detailFa: string;
  /** Non-null exactly for DEGRADED and DOWN. */
  incident: ContainerIncident | null;
  provenance: Provenance;
}

/** The canonical cutover verification matrix ids. */
export type GateId =
  | 'V-01'
  | 'V-02'
  | 'V-03'
  | 'V-04'
  | 'V-05'
  | 'V-06'
  | 'V-07'
  | 'V-08'
  | 'V-09'
  | 'V-10';

/**
 * Gate state.
 *
 * - `PASS`             — verifiable evidence is present and FRESH;
 * - `BLOCKED`          — the verifier returned FAIL (cutover gated);
 * - `EVALUATING`       — no verdict yet (exit 2 / "cannot assess") or the
 *                        evidence is stale; never green;
 * - `BYPASS_PREVENTED` — a bypass attempt was refused (V-10 semantics).
 */
export type GateStatus = 'PASS' | 'BLOCKED' | 'EVALUATING' | 'BYPASS_PREVENTED';

/** Evidence freshness. Stale evidence is labelled, never silently green. */
export type EvidenceStaleness = 'FRESH' | 'STALE';

/** The evidence a PASS decision rests on. */
export interface GateEvidence {
  /** Evidence reference (a hash/id) — never a secret value (D-124). */
  reference: string;
  staleness: EvidenceStaleness;
}

/** The refusal/failure record a non-PASS gate must carry. */
export interface GateAudit {
  /** Persian reason. Never empty. */
  reasonFa: string;
  /** D-121 trace id. Never a credential. */
  traceId: string;
  /** Logical-clock instant of the record (D-093 precedent). */
  atLogical: string;
}

/** One gate of the V-01..V-10 matrix. */
export interface PipelineGate {
  id: GateId;
  /** Persian title, translated from the canonical matrix. */
  titleFa: string;
  /** Persian description of what the gate proves. */
  descriptionFa: string;
  status: GateStatus;
  /**
   * True only when the gate has verifiable PASS evidence. The build-time guard
   * rejects any gate whose `passes` disagrees with its status, so a BLOCKED
   * gate can never render as passing.
   */
  passes: boolean;
  evidence: GateEvidence | null;
  audit: GateAudit | null;
  /** ISO-8601 instant of the last evaluation, or `null` when never evaluated. */
  lastEvaluatedUtc: string | null;
}

/** Queue pressure, derived from depth/backlog against fixed thresholds. */
export type QueuePressure = 'OK' | 'WARN' | 'CRITICAL' | 'UNKNOWN';

/** Redis broker telemetry (depth + throughput). */
export interface RedisQueueTelemetry {
  /** Queue depth, or `null` when unreadable (broker down / not probed). */
  depth: number | null;
  throughputPerMin: number | null;
  /** Derived from `depth` against `warnAtDepth` / `criticalAtDepth`. */
  pressure: QueuePressure;
  warnAtDepth: number;
  criticalAtDepth: number;
}

/** n8n workflow-execution telemetry. */
export interface N8nQueueTelemetry {
  active: number | null;
  waiting: number | null;
  failedLast24h: number | null;
  /** Derived from waiting/failed counts against the thresholds below. */
  pressure: QueuePressure;
  warnAtWaiting: number;
  criticalAtWaiting: number;
}

/** Everything the queue monitor renders. */
export interface QueueTelemetry {
  redis: RedisQueueTelemetry;
  n8n: N8nQueueTelemetry;
}

/**
 * Emergency actions of the override panel (D-171 §5.4/§6).
 *
 * All three are rendered DISABLED: forcing a gate, restarting a container or
 * flushing a queue would bypass the owner gate, so each requires a single-use
 * owner token (D-146) AND the signed write path — neither of which this phase
 * holds.
 */
export type TelemetryActionId =
  | 'FORCE_GATE_PASS'
  | 'RESTART_CONTAINER'
  | 'FLUSH_QUEUE';

/** One gated emergency action. `blockedReasonFa` is non-optional. */
export interface TelemetryActionSpec {
  id: TelemetryActionId;
  titleFa: string;
  descriptionFa: string;
  requiresSecondConfirmation: boolean;
  enabled: boolean;
  /** Persian reason the action is unavailable. Never empty. */
  blockedReasonFa: string;
}

/** The gate state every emergency action is judged against. */
export interface TelemetryWriteGate {
  /** A single-use owner token is present. Always false in this phase (D-146). */
  tokenPresent: boolean;
  /** The signed canonical/webhook write path is reachable. Always false here. */
  signaturePathConnected: boolean;
}

/** Derived roll-up of the snapshot; the summary strip renders exactly this. */
export interface TelemetryOverview {
  containersHealthy: number;
  containersDegraded: number;
  containersDown: number;
  containersUnknown: number;
  gatesPass: number;
  gatesBlocked: number;
  gatesEvaluating: number;
  gatesBypassPrevented: number;
  /** Highest-severity container state present (DOWN > DEGRADED > UNKNOWN > HEALTHY). */
  worstContainer: ContainerStatus;
  /** Highest-severity queue pressure present (CRITICAL > WARN > UNKNOWN > OK). */
  worstQueuePressure: QueuePressure;
}

/** Everything the telemetry screen renders in one request. */
export interface TelemetrySnapshot {
  /** ISO-8601 instant this snapshot describes (fixed literal for the mock). */
  generatedAt: string;
  scenario: string;
  provenance: Provenance;
  containers: ContainerHealth[];
  gates: PipelineGate[];
  queues: QueueTelemetry;
  actions: TelemetryActionSpec[];
  writeGate: TelemetryWriteGate;
  summary: TelemetryOverview;
}

/**
 * The single swap seam for live wiring.
 *
 * The page depends on this interface only, so replacing the deterministic mock
 * with live probes requires no component changes.
 */
export interface TelemetryDataSource {
  load(): Promise<TelemetrySnapshot>;
}

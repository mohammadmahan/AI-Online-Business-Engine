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

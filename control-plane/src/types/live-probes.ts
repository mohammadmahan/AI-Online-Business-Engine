/**
 * Read-only probe contracts for the live telemetry source (D-171 §5.5, Phase 27.7).
 *
 * A probe is an OBSERVATION, never a decision: it records what a single
 * server-side request to a configured endpoint saw — its latency, a digest of
 * the raw payload and the instant it concluded — or, when it could not assess
 * the surface at all, an `UNKNOWN` result carrying the Persian reason. There is
 * deliberately no default and no "healthy" fallback: an absent measurement is
 * `UNKNOWN`, never a fabricated zero (D-171 §2.2).
 *
 * No credential, token or raw network handle ever appears in these objects:
 * the seam carries only serialized results, and the endpoint label is stripped
 * to `host + pathname` so a token embedded in a query string is never echoed.
 */

import type { ContainerId } from '@/types/telemetry';

/**
 * Probe outcome. The vocabulary is the container-health taxonomy the UI
 * already renders, so a live reading maps onto it without a translation table.
 */
export type ProbeStatus = 'HEALTHY' | 'DEGRADED' | 'DOWN' | 'UNKNOWN';

/**
 * Which path produced a probe's status (Phase 27.7 corrective).
 *
 * - `sidecar`   — the response carried a structurally validated canonical
 *                 verdict body and its verdict is rendered exactly
 *                 (`HEALTHY` / `DEGRADED` / `DOWN` / `UNKNOWN`);
 * - `transport` — the seam assessed the surface from the transport facts
 *                 alone: HTTP semantics without a canonical body, timeout,
 *                 refused connection or an unusable endpoint.
 *
 * The field makes the seam's decision path explicit and type-safe instead of
 * inferring it from the status alone, so the UI and the build-time guard can
 * distinguish "the producer said UNKNOWN" from "nothing was assessable".
 */
export type ProbeVerdictSource = 'sidecar' | 'transport';

/** One completed (or attempted) read-only probe. Serialisable by construction. */
export interface ProbeResult {
  containerId: ContainerId;
  status: ProbeStatus;
  /** End-to-end latency in whole milliseconds; `null` when never connected. */
  latencyMs: number | null;
  /** SHA-256 hex of the raw response payload; `null` when no body was received. */
  payloadDigest: string | null;
  /** ISO-8601 instant the probe concluded. */
  probedAtUtc: string;
  /**
   * Persian explanation. Non-empty exactly when the status is not `HEALTHY` —
   * a failed or refused probe always states why. Bounded and free of control
   * characters: a canonical verdict reason is accepted only after structural
   * validation, so a stack trace or credential-shaped blob cannot cross.
   */
  reasonFa: string;
  /** Which decision path produced `status` (see `ProbeVerdictSource`). */
  verdictSource: ProbeVerdictSource;
  /**
   * `host + pathname` of the probed endpoint, or `null` when no endpoint is
   * configured. Never a token, query string or credential.
   */
  endpointLabel: string | null;
}

/** Probe records for the queue surfaces, when their endpoints are configured. */
export interface QueueProbeRecords {
  redis: ProbeResult | null;
  n8n: ProbeResult | null;
}

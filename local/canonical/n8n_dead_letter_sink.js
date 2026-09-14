// n8n dead-letter sink — canonical D-052 terminal-route router.
// ============================================================================
// Authority: docs/standards/n8n-idempotency-and-retries.md §2–3 (D-052
//            matrix, dead-letter route), D-026 (provenance boundary),
//            D-050 (human-only decisions).
//
// Single source of truth: this exact file content is embedded BYTE-IDENTICAL
// into the M3/M4 global error-router workflow's Code node, AFTER the failure
// taxonomy module (whose hoisted `D052` table it reuses inside the workflow).
// Standalone under Node it requires the taxonomy directly. The M4 test suite
// executes this file and asserts parity with the embedded copy.
//
// D-026 boundary (deliberate): this module NEVER builds provenance. The
// D-026 provenance record is attached by canonical Python tooling
// (local/scripts/dead_letter_bridge.py) when the dead-letter payload is
// materialized into the HITL verification queue — provenance belongs to the
// canonical layer, never to the n8n runtime.
//
// Terminal routes per D-052 §2:
//   A — transient .............. retry_backoff (NOT dead-lettered; the
//                                exponential-backoff policy of the class
//                                applies; only terminal Class-A exhaustion
//                                would re-enter here as E → human review)
//   B — data invariant ......... dead_letter_hitl
//   C — authentication ......... dead_letter_hitl
//   D — authority violation .... quarantine_and_hitl (dead-lettered AND
//                                flagged for workflow quarantine)
//   E — unknown/ambiguous ...... dead_letter_hitl
// ============================================================================

'use strict';

// Reuse the canonical D-052 table: direct require under Node (standalone /
// CI), the hoisted taxonomy variable inside the concatenated workflow embed.
var __SINK_D052 = null;
try {
  if (typeof require === 'function') {
    __SINK_D052 = require('./n8n_failure_taxonomy.js').D052;
  }
} catch (e) { /* embedded context: no module resolution — fall through */ }
if (!__SINK_D052 && typeof D052 !== 'undefined') { __SINK_D052 = D052; }
if (!__SINK_D052) { throw new Error('dead-letter sink: D-052 table unavailable'); }

function routeFailure(logLine) {
  logLine = logLine || {};
  var details = logLine.error_details || {};
  var cls = details.failure_class || logLine.error_class || 'E';
  if (!__SINK_D052[cls]) { cls = 'E'; }
  var policy = __SINK_D052[cls];

  if (cls === 'A') {
    // Transient: the class's exponential-backoff policy governs; the HITL
    // queue is NOT the first response to a retryable failure.
    return { route: 'retry_backoff', dead_letter: null,
             retry_policy: policy.retry_policy,
             backoff_seconds: policy.backoff_seconds };
  }

  var deadLetter = {
    queue_type: 'HITL_DEAD_LETTER',
    failure_class: cls,
    failure_name: policy.name,
    retry_policy: policy.retry_policy,
    route: cls === 'D' ? 'quarantine_and_hitl' : 'dead_letter_hitl',
    origin_workflow_id: String(details.origin_workflow_id || 'unknown'),
    origin_workflow_name: String(details.origin_workflow_name || 'unknown'),
    origin_execution_id: String(logLine.execution_id || 'unknown'),
    // Already redacted by the taxonomy redactor — carried verbatim.
    sanitized_reason: String(details.error_message || ''),
    idempotency_key: String(logLine.idempotency_key || ''),
    timestamp_utc: String(logLine.timestamp_utc || new Date().toISOString()),
    requires_human_intervention: true
  };
  return { route: deadLetter.route, dead_letter: deadLetter };
}

if (typeof module !== 'undefined' && module && module.exports) {
  module.exports = { routeFailure: routeFailure };
}

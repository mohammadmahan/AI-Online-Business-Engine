// n8n failure taxonomy — canonical D-052 classifier + D-045 redactor.
// ============================================================================
// Authority: docs/standards/n8n-idempotency-and-retries.md §2 (D-052 matrix),
//            docs/standards/n8n-logging-and-redaction.md §1–2 (log schema,
//            redaction mandate). Traceability: D-052, D-045, D-026, D-027.
//
// Single source of truth: this exact file content is embedded BYTE-IDENTICAL
// into the M3 global error-router workflow's Code node
// (local/n8n/workflows/GREEN-OPS-ERROR-GLOBAL_FAILURE_ROUTER.json). The test
// suite (local/tests/test_n8n_error_router_m3.py) executes THIS file with the
// real Node binary and asserts parity with the embedded copy — the workflow
// therefore runs the same logic CI tests, not a drifted inline copy.
//
// Self-contained on purpose: no imports/exports, plain `module.exports` —
// runnable under Node and inside an n8n Code node (both are V8/Node).
//
// D-052 retry policy encoded here (do not change without a decision record):
//   A — transient/network ............ retryable (exponential backoff,
//                                      3 attempts: 2s → 8s → 30s)
//   B — data invariant/schema ........ NEVER retried → dead-letter + HITL
//                                      verification queue (D-026 provenance)
//   C — authentication/secrets ....... NEVER retried → halt + infra flag
//   D — authority violation (RED w/o human approval marker) → abort +
//                                      quarantine, never auto-resolved
//   E — unknown/ambiguous ............ NEVER blindly retried → deterministic
//                                      marker reconciliation (at most one
//                                      re-execution), then human review
// ============================================================================

'use strict';

var D052 = {
  A: { name: 'Transient/network',      retry_policy: 'exponential_backoff', max_attempts: 3, backoff_seconds: [2, 8, 30], retryable: true  },
  B: { name: 'Data invariant/schema',  retry_policy: 'never_retry',         max_attempts: 0, backoff_seconds: [],         retryable: false },
  C: { name: 'Authentication/secrets', retry_policy: 'never_retry',         max_attempts: 0, backoff_seconds: [],         retryable: false },
  D: { name: 'Authority violation',    retry_policy: 'abort',               max_attempts: 0, backoff_seconds: [],         retryable: false },
  E: { name: 'Unknown/ambiguous',      retry_policy: 'deterministic_reconciliation', max_attempts: 1, backoff_seconds: [], retryable: false }
};

// Deterministic keyword table (first match wins, evaluated in order).
// Grounded in D-052 §2 examples; extended conservatively.
var CLASSIFIER_RULES = [
  { cls: 'D', patterns: ['authority', 'red tier', 'red-tier', 'without approval',
                         'hitl approval required', 'quarantine'] },
  { cls: 'C', patterns: ['credential', 'authentication', 'unauthorized', 'auth',
                         '401', '403', 'expired token', 'api key', 'apikey',
                         'signature'] },
  { cls: 'B', patterns: ['schema', 'syntax error', 'invariant', 'invalid vocabulary',
                         'integrity error', 'not null', 'foreign key',
                         'duplicate key', 'check constraint', 'validation'] },
  { cls: 'A', patterns: ['timeout', 'timed out', 'etimedout', 'econnrefused',
                         'econnreset', 'connection reset', 'eai_again',
                         'socket hang up', '502', '503', '504', '429',
                         'rate limit', 'temporarily unavailable'] }
];

function classifyD052(rawMessage) {
  var msg = String(rawMessage || '').toLowerCase();
  if (!msg) { return 'E'; }
  for (var i = 0; i < CLASSIFIER_RULES.length; i++) {
    var rule = CLASSIFIER_RULES[i];
    for (var j = 0; j < rule.patterns.length; j++) {
      if (msg.indexOf(rule.patterns[j]) !== -1) { return rule.cls; }
    }
  }
  return 'E';
}

// Redacts secret-bearing material per the M1 logging standard §2
// ("Strictly redacted"): connection strings with credentials, bearer/API
// tokens, URL query tokens (api_key/access_token/token), passwords in
// query-string or key=value form, and Authorization headers.
var REDACTIONS = [
  // scheme://user:password@host…  → scheme://[REDACTED]@host…
  { re: /([a-z][a-z0-9+.-]*:\/\/)[^@\/\s]+@/gi, sub: '$1[REDACTED]@' },
  // Authorization: Bearer xyz / Basic xyz / Token xyz
  { re: /(authorization\s*[:=]\s*)(bearer|basic|token)\s+[A-Za-z0-9._~+/=-]+/gi, sub: '$1$2 [REDACTED]' },
  // URL query tokens: api_key=…, access_token=…, token=…, key=…
  { re: /(api[_-]?key|access[_-]?token|token|key)=(?!%5B)\S+/gi, sub: '$1=[REDACTED]' },
  // Standalone bearer tokens not preceded by "authorization"
  { re: /bearer\s+[A-Za-z0-9._~+/=-]{8,}/gi, sub: 'Bearer [REDACTED]' },
  // password / secret / passwd in key=value or key: value forms
  { re: /((?:password|passwd|secret)[a-z0-9_]{0,20}\s*[:=]\s*)\S+/gi, sub: '$1[REDACTED]' }
];

function redactSecrets(text) {
  var out = String(text == null ? '' : text);
  for (var i = 0; i < REDACTIONS.length; i++) {
    out = out.replace(REDACTIONS[i].re, REDACTIONS[i].sub);
  }
  return out;
}

// Builds the engine.log.v1 error line (logging standard §1) from an n8n
// error-trigger payload. `errData` = the raw error-trigger item;
// `executionId` = safe execution identifier ('' when unavailable).
function buildErrorLog(errData, executionId) {
  errData = errData || {};
  var exec = errData.execution || {};
  var wf = errData.workflow || {};
  var err = exec.error || {};
  var rawMessage = err.message || err.description || 'Unknown error';

  var failureClass = classifyD052(rawMessage);
  var safeMessage = redactSecrets(rawMessage);

  return {
    schema: 'engine.log.v1',
    workflow_id: 'GREEN-OPS-ERROR-GLOBAL_FAILURE_ROUTER',
    execution_id: String(executionId || 'unknown'),
    timestamp_utc: new Date().toISOString(),
    trigger_event: { source_system: 'n8n', event_id: String(exec.id || executionId || 'unknown'), type: 'WORKFLOW_ERROR' },
    idempotency_key: '',
    actor: 'N8N_ERROR_HOOK',
    tier_reached: 'GREEN',
    status: 'FAILED',
    error_class: failureClass,
    entity_refs: [{ type: 'workflow', id: String(wf.name || wf.id || 'unknown') }],
    error_details: {
      origin_workflow_id: String(wf.id || 'unknown'),
      origin_workflow_name: String(wf.name || 'unknown'),
      failure_class: failureClass,
      error_message: safeMessage,
      retryable: D052[failureClass].retryable,
      retry_policy: D052[failureClass].retry_policy
    }
  };
}

module.exports = { D052: D052, CLASSIFIER_RULES: CLASSIFIER_RULES,
                   classifyD052: classifyD052, REDACTIONS: REDACTIONS,
                   redactSecrets: redactSecrets, buildErrorLog: buildErrorLog };

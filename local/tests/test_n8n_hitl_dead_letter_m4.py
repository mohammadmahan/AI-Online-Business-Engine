"""M4 contract tests — HITL dead-letter routing (Phase 5 closeout).

Unlike a test that re-implements routing inline, this suite exercises the
SHIPPED canonical modules and the real bridge:

  1. D-052 terminal routes, executed under Node against
     local/canonical/n8n_dead_letter_sink.js (A retries, B/C/E
     dead-letter, D quarantines + dead-letters) — including the
     requires_human_intervention / queue_type payloads.
  2. Embed parity: the sink (and taxonomy) are embedded byte-identically
     in the router workflow's Code node; the generator is deterministic.
  3. End-to-end bridge: a synthetic <<<DEADLETTER>>> line (exactly what
     the router emits) is materialized by dead_letter_bridge into the
     REAL VerificationQueue with D-026 provenance (EXTERNAL_SYNC),
     dedupes on re-ingestion, and the item then carries a human decision
     through the ordinary review path (D-050 — the bridge never decides).

Authority: docs/standards/n8n-idempotency-and-retries.md §2–3 (D-052),
           D-026 provenance, D-028 boundary, D-050 human authority.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL = os.path.dirname(HERE)
ROOT = os.path.dirname(LOCAL)
for p in (LOCAL, os.path.join(LOCAL, "canonical"),
          os.path.join(LOCAL, "services"), os.path.join(LOCAL, "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

WF_PATH = os.path.join(ROOT, "local", "n8n", "workflows",
                       "GREEN-OPS-ERROR-GLOBAL_FAILURE_ROUTER.json")
SINK_PATH = os.path.join(ROOT, "local", "canonical", "n8n_dead_letter_sink.js")
TAX_PATH = os.path.join(ROOT, "local", "canonical", "n8n_failure_taxonomy.js")
GENERATOR = os.path.join(ROOT, "local", "scripts",
                         "generate_error_router_workflow.js")
BRIDGE = os.path.join(ROOT, "local", "scripts", "dead_letter_bridge.py")

SINK_END = ("=== END canonical dead-letter sink — source: "
            "local/canonical/n8n_dead_letter_sink.js ===")

T_END = "=== END canonical failure taxonomy — source: local/canonical/n8n_failure_taxonomy.js ==="


def _node_json(script_body, argv=()):
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as f:
        f.write(script_body)
        tmp = f.name
    try:
        proc = subprocess.run(["node", tmp, *argv],
                              capture_output=True, text=True, timeout=60)
    finally:
        os.unlink(tmp)
    if proc.returncode != 0:
        raise AssertionError("node probe failed:\n" + proc.stderr)
    for line in proc.stdout.splitlines():
        if line.startswith("<<<JSON>>>"):
            return json.loads(line[len("<<<JSON>>>"):])
    raise AssertionError("no JSON output from node probe:\n" + proc.stdout)


def _route(message):
    """Run the real sink + taxonomy under Node for one error message."""
    body = (
        "const sink = require(" + json.dumps(SINK_PATH) + ");\n"
        "const tax = require(" + json.dumps(TAX_PATH) + ");\n"
        "const log = tax.buildErrorLog(\n"
        "  { execution: { error: { message: process.argv[2] } },\n"
        "    workflow: { id: 'wf-1', name: 'M4_TEST_WORKFLOW' } }, 'exec-1');\n"
        "const r = sink.routeFailure(log);\n"
        "console.log('<<<JSON>>>' + JSON.stringify(r));\n"
    )
    return _node_json(body, [message])


def _router_final_item(payload, execution_id="exec-1"):
    """Execute the FULL embedded router Code-node body (modules + tail) with
    n8n's $input/$execution stubbed, returning the workflow's return item."""
    with open(WF_PATH, encoding="utf-8") as f:
        js_code = json.load(f)["nodes"][1]["parameters"]["jsCode"]
    body = js_code.replace(
        "const __errData = $input.first().json;",
        "const __errData = JSON.parse(process.argv[2]);")
    body = body.replace(
        "const __executionId = (typeof $execution !== 'undefined' && $execution && $execution.id) ? String($execution.id) : '';",
        "const __executionId = process.argv[3];")
    # capture the return value instead of returning from module scope
    body = body.replace("return [{ json: __line }];",
                        "console.log('<<<JSON>>>' + JSON.stringify({ kind: 'log', line: __line }));")
    body = body.replace(
        "return [{ json: Object.assign({}, __line, { dead_letter: __route.dead_letter }) }];",
        "console.log('<<<JSON>>>' + JSON.stringify({ kind: 'log+dl', line: __line, dead_letter: __route.dead_letter }));")
    return _node_json(body, [json.dumps(payload), execution_id])


class TestD052TerminalRoutes(unittest.TestCase):
    """The instruction's five intents, executed against the real sink."""

    def test_transient_class_a_not_routed_to_hitl(self):
        r = _route("ETIMEDOUT: Connection reset by peer")
        self.assertEqual(r["route"], "retry_backoff")
        self.assertIsNone(r["dead_letter"],
                          "transient Class A must not dead-letter to HITL")

    def test_schema_class_b_routed_to_hitl(self):
        r = _route("Schema violation: missing mandatory sku_id")
        self.assertEqual(r["route"], "dead_letter_hitl")
        dl = r["dead_letter"]
        self.assertEqual(dl["failure_class"], "B")
        self.assertTrue(dl["requires_human_intervention"])
        self.assertEqual(dl["queue_type"], "HITL_DEAD_LETTER")

    def test_credential_class_c_routed_to_hitl(self):
        r = _route('Credential with ID postgres-canonical-local does not exist')
        dl = r["dead_letter"]
        self.assertEqual(r["route"], "dead_letter_hitl")
        self.assertEqual(dl["failure_class"], "C")
        self.assertTrue(dl["requires_human_intervention"])

    def test_authority_class_d_routed_to_hitl_and_quarantined(self):
        r = _route("RED tier violation: forbidden autonomous action")
        dl = r["dead_letter"]
        self.assertEqual(dl["failure_class"], "D")
        self.assertEqual(r["route"], "quarantine_and_hitl")
        self.assertTrue(dl["requires_human_intervention"])

    def test_unknown_class_e_routed_to_hitl(self):
        r = _route("Completely unexpected unhandled exception thrown")
        dl = r["dead_letter"]
        self.assertEqual(r["route"], "dead_letter_hitl")
        self.assertEqual(dl["failure_class"], "E")
        self.assertTrue(dl["requires_human_intervention"])

    def test_dead_letter_carries_redacted_reason_and_origin(self):
        # Terminal-class vector (auth failure) carrying a credential-bearing
        # connection string — the reason must arrive already redacted.
        r = _route("auth failed for postgres://engine:secret@db:5432/x")
        dl = r["dead_letter"]
        self.assertEqual(dl["failure_class"], "C")
        self.assertNotIn("secret", dl["sanitized_reason"])
        self.assertIn("[REDACTED]@", dl["sanitized_reason"])
        self.assertEqual(dl["origin_workflow_name"], "M4_TEST_WORKFLOW")
        self.assertEqual(dl["origin_execution_id"], "exec-1")


class TestRouterWorkflowM4(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with open(WF_PATH, encoding="utf-8") as f:
            cls.data = json.load(f)
        cls.js_code = cls.data["nodes"][1]["parameters"]["jsCode"]

    def test_sink_embedded_byte_identically(self):
        with open(SINK_PATH, encoding="utf-8") as f:
            sink = f.read()
        start = self.js_code.index(
            "=== BEGIN canonical dead-letter sink (byte-identical embed) ===")
        end = self.js_code.index(SINK_END) + len(SINK_END)
        self.assertIn(sink, self.js_code[start:end])

    def test_taxonomy_still_embedded_byte_identically(self):
        with open(TAX_PATH, encoding="utf-8") as f:
            tax = f.read()
        start = self.js_code.index(
            "=== BEGIN canonical failure taxonomy (byte-identical embed) ===")
        end = self.js_code.index(T_END) + len(T_END)
        self.assertIn(tax, self.js_code[start:end])

    def test_generator_deterministic(self):
        with open(WF_PATH, "rb") as f:
            before = f.read()
        subprocess.run(["node", GENERATOR], check=True, timeout=60,
                       capture_output=True)
        with open(WF_PATH, "rb") as f:
            self.assertEqual(before, f.read())

    def test_router_emits_deadletter_only_for_terminal_classes(self):
        # Class A: log line, no dead-letter in the returned item
        out = _router_final_item(
            {"execution": {"error": {"message": "timeout"}},
             "workflow": {"id": "1", "name": "W"}})
        self.assertEqual(out["kind"], "log")
        self.assertEqual(out["line"]["error_class"], "A")
        # Class B: dead-letter attached and identical to sink output
        out = _router_final_item(
            {"execution": {"error": {"message": "schema mismatch"}},
             "workflow": {"id": "1", "name": "W"}})
        self.assertEqual(out["kind"], "log+dl")
        self.assertEqual(out["dead_letter"]["failure_class"], "B")
        self.assertEqual(out["dead_letter"]["queue_type"], "HITL_DEAD_LETTER")

    def test_no_hardcoded_secrets(self):
        blob = json.dumps(self.data).lower()
        for pattern in ("postgres://engine", '"password":', "bearer sk-live"):
            self.assertNotIn(pattern, blob)


class TestBridgeEndToEnd(unittest.TestCase):
    """Synthetic router stdout → bridge → REAL queue → human decision."""

    DEADLETTER = {
        "queue_type": "HITL_DEAD_LETTER",
        "failure_class": "B",
        "failure_name": "Data invariant/schema",
        "retry_policy": "never_retry",
        "route": "dead_letter_hitl",
        "origin_workflow_id": "wf-9",
        "origin_workflow_name": "GREEN-CATALOG-MANUAL-EXAMPLE",
        "origin_execution_id": "exec-42",
        "sanitized_reason": "invalid vocabulary term supplied",
        "idempotency_key": "sha256:deadbeef",
        "timestamp_utc": "2026-09-14T10:00:00.000Z",
        "requires_human_intervention": True
    }

    def _bridge_env(self, tmp):
        return dict(os.environ,
                    VQ_QUEUE=os.path.join(tmp, "queue.json"))

    def _run_bridge(self, tmp, extra_args=()):
        # Feed the bridge the synthetic log line via stdin-like argv:
        # the bridge's parse path is exercised directly (unit level) and
        # through its public functions — no docker dependency in tests.
        import importlib.util
        spec = importlib.util.spec_from_file_location("dlb", BRIDGE)
        dlb = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(dlb)
        return dlb

    def test_parse_and_materialize_into_real_queue(self):
        dlb = self._run_bridge(tempfile.mkdtemp())
        line = "2026-09-14T10:00:01.000Z [stdout] <<<DEADLETTER>>>" \
               + json.dumps(self.DEADLETTER)
        records, malformed = dlb.parse_deadletters(line)
        self.assertEqual(malformed, 0)
        self.assertEqual(len(records), 1)

        # REAL VerificationQueue + REAL provenance, isolated temp paths
        import verification_tool as vt
        from sync_engine import ProvenanceEngine
        tmp = tempfile.mkdtemp(prefix="m4bridge-")
        prov = ProvenanceEngine(path=os.path.join(tmp, "prov.json"))
        queue = vt.VerificationQueue(
            queue_path=os.path.join(tmp, "queue.json"), provenance=prov)
        report = dlb.materialize(records, queue)
        self.assertEqual(report["enqueued"], 1)
        self.assertEqual(report["pending"], 1)

        item = queue.load_pending()[0]
        self.assertEqual(item["code"], "WORKFLOW_FAILURE_CLASS_B")
        self.assertEqual(item["failure_class"], "B")
        self.assertEqual(item["item_key"], "n8n|sha256:deadbeef")
        self.assertEqual(item["origin_workflow_name"],
                         "GREEN-CATALOG-MANUAL-EXAMPLE")
        # D-026 provenance: EXTERNAL_SYNC record attributable to the
        # n8n workflow actor — exists before any human decides.
        types = [r["source_type"] for r in prov.records]
        self.assertIn("EXTERNAL_SYNC", types)
        actors = {r["actor"] for r in prov.records}
        self.assertIn("n8n-error-router", actors)

        # Human decides through the ordinary path (D-050); the bridge
        # exposes no decision API of its own.
        decided = queue.review_item(0, approved=False, reviewer="owner")
        self.assertEqual(decided["review_status"], "HUMAN_REJECTED")

    def test_reingestion_deduplicates(self):
        dlb = self._run_bridge(tempfile.mkdtemp())
        line = "x <<<DEADLETTER>>>" + json.dumps(self.DEADLETTER)
        records, _ = dlb.parse_deadletters(line)
        import verification_tool as vt
        from sync_engine import ProvenanceEngine
        tmp = tempfile.mkdtemp(prefix="m4bridge2-")
        prov = ProvenanceEngine(path=os.path.join(tmp, "prov.json"))
        queue = vt.VerificationQueue(
            queue_path=os.path.join(tmp, "queue.json"), provenance=prov)
        dlb.materialize(records, queue)
        report = dlb.materialize(records, queue)   # same logs again
        self.assertEqual(report["enqueued"], 0)
        self.assertEqual(report["deduplicated"], 1)
        self.assertEqual(report["pending"], 1)

    def test_malformed_line_not_silently_dropped(self):
        dlb = self._run_bridge(tempfile.mkdtemp())
        records, malformed = dlb.parse_deadletters(
            "<<<DEADLETTER>>>{not json at all")
        self.assertEqual(records, [])
        self.assertEqual(malformed, 1)

    def test_class_a_payload_rejected_as_terminal(self):
        dlb = self._run_bridge(tempfile.mkdtemp())
        bad = dict(self.DEADLETTER, failure_class="A")
        item = dlb.dead_letter_to_review_item(bad)
        self.assertEqual(item["failure_class"], "E",
                         "a Class-A payload must never enter the "
                         "dead-letter queue as A (A retries per D-052)")

    def test_bridge_has_no_decision_api(self):
        dlb = self._run_bridge(tempfile.mkdtemp())
        public = [n for n in dir(dlb) if not n.startswith("_")]
        for forbidden in ("review_item", "approve", "reject",
                          "auto_resolve", "decide"):
            self.assertNotIn(forbidden, public,
                             "D-050: the bridge must never decide")


if __name__ == "__main__":
    unittest.main()

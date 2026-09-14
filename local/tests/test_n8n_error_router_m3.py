"""M3 contract validator — GREEN-OPS-ERROR-GLOBAL_FAILURE_ROUTER.

Two layers, mirroring the M2 approach but closing its main gap (logic that
lives only inside an unexecuted Code-node string):

  1. Static workflow-JSON contract checks (naming, tier, triggers,
     connections, no embedded secrets, byte-identical embed of the
     canonical taxonomy module).
  2. Executed behavior tests: the embedded Code-node body is run by the
     REAL Node binary (V8, same runtime family as the n8n Code node) with
     real node-execution semantics, and its engine.log.v1 output is
     asserted against the D-052 failure matrix and the D-045 redaction
     mandate — including the M2 credential refusal as a live Class C vector.

Authority: docs/standards/n8n-idempotency-and-retries.md §2 (D-052),
           docs/standards/n8n-logging-and-redaction.md §1–2 (D-045),
           docs/standards/n8n-conventions.md (naming/tier/isolation).
"""

import datetime
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
CANONICAL = os.path.join(ROOT, "local", "canonical")
WF_PATH = os.path.join(ROOT, "local", "n8n", "workflows",
                       "GREEN-OPS-ERROR-GLOBAL_FAILURE_ROUTER.json")
CORE_PATH = os.path.join(CANONICAL, "n8n_failure_taxonomy.js")
GENERATOR = os.path.join(ROOT, "local", "scripts",
                         "generate_error_router_workflow.js")

WF_NAME = "GREEN-OPS-ERROR-GLOBAL_FAILURE_ROUTER"
EMBED_BEGIN = "=== BEGIN canonical failure taxonomy (byte-identical embed) ==="
EMBED_END = "=== END canonical failure taxonomy — source: local/canonical/n8n_failure_taxonomy.js ==="

# Secret patterns that must never appear in the workflow definition.
# NOTE: the bare string "postgres://" is deliberately NOT forbidden here —
# the D-045 redactor legitimately references it in its own substitution
# regex; what is forbidden is any *concrete* credential material.
FORBIDDEN_SECRETS = ("engine-local-only", "postgres://engine",
                     '"password":', "Bearer sk-live")

REQUIRED_LOG_KEYS = ("schema", "workflow_id", "execution_id", "timestamp_utc",
                     "trigger_event", "actor", "tier_reached", "status",
                     "error_class", "entity_refs")

# (raw error message, expected D-052 class) — incl. D/C/B precedence cases
CLASSIFY_VECTORS = [
    ("connection timeout after 30000 ms", "A"),
    ("upstream returned 503 service unavailable", "A"),
    ("check constraint \"size_term_code_check\" violated", "B"),
    ("invalid vocabulary term supplied", "B"),
    ('Credential with ID "postgres-canonical-local" does not exist', "C"),
    ("401 unauthorized while calling external api", "C"),
    ("RED tier action requested without approval", "D"),
    ("authority violation: quarantine requested", "D"),
    # precedence: rule tables are evaluated in D → C → B → A order
    ("authority violation: credential missing", "D"),
    ("auth failed during validation", "C"),
    ("syntax error after timeout", "B"),
    # E: empty and unrecognized
    ("", "E"),
    ("the flurb quintuplicated unexpectedly", "E"),
]


def _extract_embedded_code(js_code):
    start = js_code.index(EMBED_BEGIN)
    end = js_code.index(EMBED_END)
    return js_code[start + len(EMBED_BEGIN):end]


def _run_embedded_code(js_code, payload, execution_id="test-exec-1"):
    """Execute the embedded Code-node body under real Node, mirroring n8n's
    $input/$execution helpers, and return the emitted engine.log.v1 dict."""
    # cut after the embedded canonical module; the n8n tail ($input/$execution
    # references) is exercised on the live instance, the module itself here.
    body = js_code[:js_code.index(EMBED_END) + len(EMBED_END)]
    wrapper = body + ("\n"
        "const __payload = JSON.parse(process.argv[2]);\n"
        "const __line = buildErrorLog(__payload, process.argv[3]);\n"
        "console.log('<<<JSON>>>' + JSON.stringify(__line));\n"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as f:
        f.write(wrapper)
        tmp = f.name
    try:
        proc = subprocess.run(
            ["node", tmp, json.dumps(payload), execution_id],
            capture_output=True, text=True, timeout=60)
    finally:
        os.unlink(tmp)
    if proc.returncode != 0:
        raise AssertionError("embedded code failed under node:\n"
                             + proc.stderr)
    for line in proc.stdout.splitlines():
        if line.startswith("<<<JSON>>>"):
            return json.loads(line[len("<<<JSON>>>"):])
    raise AssertionError("embedded code produced no JSON line:\n" + proc.stdout)


def _taxonomy_json(expression):
    """Evaluate a JS expression against the executed canonical taxonomy
    module under the real Node binary and return the parsed result."""
    js = ("const m = require('" + CORE_PATH + "');\n"
          "console.log('<<<JSON>>>' + JSON.stringify(" + expression + "));\n")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as f:
        f.write(js)
        tmp = f.name
    try:
        proc = subprocess.run(["node", tmp], capture_output=True, text=True,
                              timeout=60)
    finally:
        os.unlink(tmp)
    if proc.returncode != 0:
        raise AssertionError("taxonomy expression failed:\n" + proc.stderr)
    for line in proc.stdout.splitlines():
        if line.startswith("<<<JSON>>>"):
            return json.loads(line[len("<<<JSON>>>"):])
    raise AssertionError("no output from taxonomy expression")


class TestN8nErrorRouterM3(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with open(WF_PATH, encoding="utf-8") as f:
            cls.data = json.load(f)
        cls.code_nodes = [n for n in cls.data.get("nodes", [])
                          if n.get("type") == "n8n-nodes-base.code"]
        cls.js_code = cls.code_nodes[0]["parameters"]["jsCode"]

    # -- conventions standard ------------------------------------------

    def test_workflow_name_and_tier(self):
        self.assertEqual(self.data.get("name"), WF_NAME)
        self.assertTrue(WF_NAME.startswith("GREEN-"),
                        "error router must state its true (highest) tier")

    def test_tags_present(self):
        tags = {t.get("name") for t in self.data.get("tags", [])}
        self.assertTrue({"GREEN", "OPS", "ERROR-ROUTER"} <= tags)
        # milestone tag advances with the workflow's evolution (M3 -> M4)
        self.assertTrue(any(t.startswith("PHASE5-M") for t in tags),
                        "workflow must carry its phase-5 milestone tag")

    def test_workflow_has_required_id(self):
        self.assertTrue(self.data.get("id"), "workflow-level id required "
                        "for n8n import in this n8n version")

    def test_single_error_trigger(self):
        trig = [n for n in self.data.get("nodes", [])
                if n.get("type") == "n8n-nodes-base.errorTrigger"]
        self.assertEqual(len(trig), 1)

    def test_trigger_wired_to_classifier(self):
        conns = self.data.get("connections", {})
        targets = [t["node"] for t in
                   conns.get("Error Trigger", {}).get("main", [[]])[0]]
        self.assertEqual(len(targets), 1)
        self.assertTrue(targets[0].startswith("Classify"),
                        "trigger must feed the classify/redact/route node")

    def test_no_credential_nodes(self):
        for node in self.data.get("nodes", []):
            self.assertNotIn("credentials", node,
                             "error router must carry no credential references")

    def test_no_hardcoded_secrets(self):
        blob = json.dumps(self.data).lower()
        for pattern in FORBIDDEN_SECRETS:
            self.assertNotIn(pattern, blob,
                             f"embedded credential pattern: {pattern}")

    def test_workflow_not_active(self):
        self.assertFalse(self.data.get("active", True))

    # -- canonical embed & generator parity ------------------------------

    def test_embedded_code_is_byte_identical_to_canonical_module(self):
        with open(CORE_PATH, encoding="utf-8") as f:
            core = f.read()
        embedded = _extract_embedded_code(self.js_code)
        self.assertIn(core, embedded,
                      "workflow must embed the canonical taxonomy module "
                      "byte-identically (CI-tested logic == runtime logic)")

    def test_generator_reproduces_workflow_deterministically(self):
        with open(WF_PATH, "rb") as f:
            before = f.read()
        subprocess.run(["node", GENERATOR], check=True, timeout=60,
                       capture_output=True)
        with open(WF_PATH, "rb") as f:
            after = f.read()
        self.assertEqual(before, after,
                         "generator output must be deterministic and in "
                         "sync with the committed workflow")

    def test_embedded_code_parses_under_node(self):
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                         encoding="utf-8") as f:
            f.write(self.js_code.replace("$input", "({first:()=>({json:{}})})")
                             .replace("$execution", "({id:'x'})"))
            tmp = f.name
        try:
            proc = subprocess.run(["node", "--check", tmp],
                                  capture_output=True, text=True, timeout=60)
        finally:
            os.unlink(tmp)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    # -- D-052 classification (executed, not just string-matched) --------

    def test_classification_vectors_executed(self):
        for raw, expected in CLASSIFY_VECTORS:
            line = _run_embedded_code(
                self.js_code,
                {"execution": {"error": {"message": raw}}, "workflow": {}})
            self.assertEqual(line["error_class"], expected,
                             f"class({raw!r}) should be {expected}")

    def test_retryable_matrix_executed(self):
        cases = {"A": True, "B": False, "C": False, "D": False, "E": False}
        for cls, retryable in cases.items():
            msg = {"A": "timeout", "B": "schema mismatch", "C": "401",
                   "D": "authority violation", "E": "mystery"}[cls]
            line = _run_embedded_code(
                self.js_code,
                {"execution": {"error": {"message": msg}}, "workflow": {}})
            self.assertEqual(line["error_details"]["retryable"], retryable,
                             f"class {cls} retryable must be {retryable} "
                             f"(D-052 matrix)")

    def test_retry_policy_metadata_present(self):
        d052 = _taxonomy_json("m.D052")
        self.assertEqual(d052["A"]["retry_policy"],
                         "exponential_backoff")
        self.assertEqual(d052["A"]["backoff_seconds"], [2, 8, 30])
        self.assertEqual(d052["E"]["retry_policy"],
                         "deterministic_reconciliation")
        for cls in ("B", "C", "D"):
            self.assertEqual(d052[cls]["retry_policy"], "never_retry"
                             if cls != "D" else "abort")
        # executable rules table exists and is ordered D → C → B → A
        order = _taxonomy_json("m.CLASSIFIER_RULES.map(r => r.cls)")
        self.assertEqual(order, ["D", "C", "B", "A"])

    # -- D-045 redaction (executed) ---------------------------------------

    def test_redaction_connection_string_executed(self):
        line = _run_embedded_code(
            self.js_code,
            {"execution": {"error": {"message":
                "connect ECONNREFUSED postgres://engine:engine-local-only"
                "@db:5432/business_engine_local"}},
             "workflow": {}})
        msg = line["error_details"]["error_message"]
        self.assertNotIn("engine-local-only", msg)
        self.assertIn("[REDACTED]@", msg)

    def test_redaction_bearer_token_executed(self):
        line = _run_embedded_code(
            self.js_code,
            {"execution": {"error": {"message":
                "Authorization: Bearer abc123def456ghi789 rejected"}},
             "workflow": {}})
        msg = line["error_details"]["error_message"]
        self.assertNotIn("abc123def456ghi789", msg)
        self.assertIn("[REDACTED]", msg)

    def test_redaction_url_query_tokens_executed(self):
        line = _run_embedded_code(
            self.js_code,
            {"execution": {"error": {"message":
                "webhook failed: https://hooks.example.com/?api_key=sk123abc&x=1"}},
             "workflow": {}})
        msg = line["error_details"]["error_message"]
        self.assertNotIn("sk123abc", msg)
        self.assertIn("api_key=[REDACTED]", msg)

    def test_redaction_preserves_permitted_tracing_fields(self):
        line = _run_embedded_code(
            self.js_code,
            {"execution": {"error": {"message":
                "variant sale for P90001 SKU-BK-M resolved variant_sale=490000"}},
             "workflow": {}})
        msg = line["error_details"]["error_message"]
        self.assertIn("P90001", msg)   # canonical Product ID — permitted
        self.assertIn("490000", msg)   # resolved amount — permitted
        self.assertIn("variant_sale", msg)  # D-048 tier name — permitted

    # -- engine.log.v1 shape (logging standard §1) ------------------------

    def test_log_line_schema_and_required_keys(self):
        line = _run_embedded_code(
            self.js_code,
            {"execution": {"error": {"message": "timeout"}},
             "workflow": {"id": "wf-1", "name": "GREEN-OPS-MANUAL-CANONICAL_DB_SMOKE"}})
        for key in REQUIRED_LOG_KEYS:
            self.assertIn(key, line)
        self.assertEqual(line["schema"], "engine.log.v1")
        self.assertEqual(line["status"], "FAILED")
        self.assertEqual(line["tier_reached"], "GREEN")
        self.assertEqual(line["trigger_event"]["type"], "WORKFLOW_ERROR")
        for ref in line["entity_refs"]:
            self.assertIsInstance(ref, dict)
            self.assertIn("type", ref)
            self.assertIn("id", ref)
        self.assertEqual(line["entity_refs"][0]["id"],
                         "GREEN-OPS-MANUAL-CANONICAL_DB_SMOKE")

    def test_log_timestamp_is_iso8601_utc(self):
        line = _run_embedded_code(
            self.js_code,
            {"execution": {"error": {"message": "timeout"}}, "workflow": {}})
        ts = line["timestamp_utc"]
        parsed = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
        self.assertEqual(parsed.utcoffset(), datetime.timedelta(0))

    def test_origin_workflow_captured_and_redacted_message_not_mutated_input(self):
        payload = {"execution": {"error": {"message": "timeout"}},
                   "workflow": {"id": "42", "name": "SOME-WORKFLOW"}}
        line = _run_embedded_code(self.js_code, payload)
        self.assertEqual(line["error_details"]["origin_workflow_id"], "42")
        self.assertEqual(line["error_details"]["origin_workflow_name"],
                         "SOME-WORKFLOW")
        # input payload must not be mutated by the builder
        self.assertEqual(payload["workflow"]["name"], "SOME-WORKFLOW")


if __name__ == "__main__":
    unittest.main()

"""Phase 5 live wiring — webhook contracts & dispatcher tests (offline).

Pins the core-side n8n live-automation seam added in this batch:

  - `canonical/n8n_webhook_contracts.py`: HMAC-SHA256 verification
    (constant-time, exact raw bytes, fail-closed on missing secret
    reference), bounded/strict event parsing, deterministic D-027-lineage
    event keys, and the injected-handler dispatcher with exactly-once
    idempotency (dispatched → skipped_duplicate; distinct event_id →
    distinct key; handler errors recorded, never silent).
  - `scripts/validate_n8n_live.py`: manifest reachability contract and
    the D-045 credential gates (API probe disabled unless the owner
    flag + key exist; no secret material printed).

No network, no wall clock, no real credentials — the secret in every
test is a drill-local fixture value.
"""
import json
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "local" / "scripts" / "validate_n8n_live.py"
MANIFEST = REPO / "local" / "infra" / "docker-compose.yml"

sys.path.insert(0, str(REPO / "local"))
sys.path.insert(0, str(SCRIPT.parent))

from canonical.n8n_webhook_contracts import (  # noqa: E402
    MAX_PAYLOAD_BYTES, N8nEventDispatcher, N8nWebhookError, event_key,
    mock_webhook_payload, parse_event, sign_payload, verify_hmac_header,
    WEBHOOK_SECRET_ENV,
)

SECRET = "battery-drill-secret-fixture"


def _dispatch_pair():
    seen, recorded = set(), []

    def record(k):
        seen.add(k)
        recorded.append(k)

    d = N8nEventDispatcher(
        handlers={"workflow.completed": lambda e: {"applied": True}},
        seen_keys=lambda k: k in seen, record_key=record)
    return d


class TestHmacVerification(unittest.TestCase):

    def setUp(self):
        self.ev = mock_webhook_payload()
        self.raw = json.dumps(self.ev).encode("utf-8")
        self.sig = sign_payload(self.raw, SECRET)

    def test_round_trip(self):
        verify_hmac_header(self.raw, self.sig, SECRET)  # no raise

    def test_tampered_body_rejected(self):
        with self.assertRaises(N8nWebhookError):
            verify_hmac_header(self.raw + b" ", self.sig, SECRET)

    def test_wrong_secret_rejected(self):
        with self.assertRaises(N8nWebhookError):
            verify_hmac_header(self.raw, sign_payload(self.raw, "x"), SECRET)

    def test_malformed_headers_rejected(self):
        for hdr in ("sha256=zzzz", "sha256=" + "a" * 63, "sha256=", "",
                    "token=abc", None):
            with self.assertRaises(N8nWebhookError):
                verify_hmac_header(self.raw, hdr, SECRET)

    def test_non_bytes_body_rejected(self):
        with self.assertRaises(N8nWebhookError):
            verify_hmac_header("not-bytes", self.sig, SECRET)

    def test_fail_closed_without_any_secret(self):
        saved = os.environ.pop(WEBHOOK_SECRET_ENV, None)
        try:
            with self.assertRaises(N8nWebhookError):
                verify_hmac_header(self.raw, self.sig)  # no secret anywhere
        finally:
            if saved is not None:
                os.environ[WEBHOOK_SECRET_ENV] = saved

    def test_env_secret_resolved_when_not_passed(self):
        saved = os.environ.get(WEBHOOK_SECRET_ENV)
        os.environ[WEBHOOK_SECRET_ENV] = SECRET
        try:
            verify_hmac_header(self.raw, self.sig)  # resolves from env
        finally:
            if saved is None:
                os.environ.pop(WEBHOOK_SECRET_ENV, None)
            else:
                os.environ[WEBHOOK_SECRET_ENV] = saved


class TestEventParsing(unittest.TestCase):

    def test_valid_event_parses(self):
        raw = json.dumps(mock_webhook_payload()).encode()
        parsed = parse_event(raw)
        self.assertEqual(parsed["event_type"], "workflow.completed")
        self.assertEqual(parsed["payload"], {"ok": True})

    def test_rejections(self):
        ev = mock_webhook_payload()
        cases = [
            ("invalid json", b"{nope"),
            ("non-object", b"[1]"),
            ("missing keys", b'{"event_type":"ops.ping"}'),
            ("extra keys", json.dumps({**ev, "x": 1}).encode()),
            ("bad type", json.dumps({**ev, "event_type": "other"}).encode()),
            ("empty workflow_ref",
             json.dumps({**ev, "workflow_ref": "  "}).encode()),
            ("long workflow_ref",
             json.dumps({**ev, "workflow_ref": "w" * 121}).encode()),
            ("payload array", json.dumps({**ev, "payload": []}).encode()),
            ("oversized", b"x" * (MAX_PAYLOAD_BYTES + 1)),
        ]
        for name, body in cases:
            with self.assertRaises(N8nWebhookError, msg=name):
                parse_event(body)

    def test_all_declared_event_types_parse(self):
        for t in ("workflow.completed", "workflow.failed", "hitl.request",
                  "ops.ping"):
            raw = json.dumps(mock_webhook_payload(event_type=t)).encode()
            self.assertEqual(parse_event(raw)["event_type"], t)


class TestDispatcherIdempotency(unittest.TestCase):

    def test_key_deterministic_and_distinct(self):
        e1 = mock_webhook_payload()
        e2 = mock_webhook_payload(event_id="ev-0002")
        k1a, k1b = event_key(e1), event_key(e1)
        self.assertEqual(k1a, k1b, "same delivery ⇒ same key")
        self.assertNotEqual(k1a, event_key(e2),
                            "distinct event_id ⇒ distinct key")

    def test_dispatched_then_skipped(self):
        d = _dispatch_pair()
        ev = mock_webhook_payload()
        r1 = d.dispatch([ev], logical_now="T1")
        r2 = d.dispatch([ev], logical_now="T2")
        self.assertEqual(r1["results"][0]["verdict"], "dispatched")
        self.assertEqual(r2["results"][0]["verdict"], "skipped_duplicate")

    def test_handler_error_recorded_batch_continues(self):
        def boom(e):
            raise RuntimeError("downstream")

        d = N8nEventDispatcher(
            handlers={"workflow.completed": boom,
                      "ops.ping": lambda e: {"pong": True}},
            seen_keys=lambda k: False, record_key=lambda k: None)
        bad = mock_webhook_payload()
        good = mock_webhook_payload(event_type="ops.ping", event_id="p1")
        r = d.dispatch([bad, good], logical_now="T1")
        self.assertEqual(r["results"][0]["verdict"], "handler_error")
        self.assertIn("downstream", r["results"][0]["detail"])
        self.assertEqual(r["results"][1]["verdict"], "dispatched")

    def test_no_handler_is_explicit_not_silent(self):
        d = N8nEventDispatcher(handlers={},
                               seen_keys=lambda k: False,
                               record_key=lambda k: None)
        r = d.dispatch([mock_webhook_payload()], logical_now="T1")
        self.assertEqual(r["results"][0]["verdict"], "no_handler")

    def test_unknown_handler_type_rejected_at_construction(self):
        with self.assertRaises(N8nWebhookError):
            N8nEventDispatcher(handlers={"bogus": lambda e: {}},
                               seen_keys=lambda k: False,
                               record_key=lambda k: None)


class TestValidateScript(unittest.TestCase):

    def test_offline_mode_green(self):
        proc = subprocess.run([sys.executable, str(SCRIPT)],
                              capture_output=True, text=True, cwd=str(REPO))
        self.assertEqual(proc.returncode, 0,
                         f"offline verification failed:\n{proc.stdout[-300:]}")
        self.assertIn("OFFLINE VERIFIED", proc.stdout)
        self.assertIn("skipped_duplicate", proc.stdout)

    def test_manifest_contract_terms(self):
        text = MANIFEST.read_text(encoding="utf-8")
        self.assertIn("127.0.0.1:15678:5678", text,
                      "n8n must stay loopback-published locally")
        self.assertIn("/healthz", text)
        self.assertIn("canonical-db", text)

    def test_credential_gate_is_fail_closed(self):
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("N8N_API_PROBE", text)
        self.assertIn("N8N_API_KEY", text)
        self.assertIn("D-045", text)
        # The script never prints key material — no f-string embeds the
        # key variable into output.
        for line in text.splitlines():
            if "print(" in line and "key" in line.lower():
                self.assertNotRegex(line, r'f"[^"]*\{key\}')
                self.assertNotRegex(line, r"f'[^']*\{key\}")


if __name__ == "__main__":
    unittest.main()

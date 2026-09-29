"""Stage C gate-runner battery (offline — all transports injectable).

Pins the sequential fail-closed orchestration of
`local/scripts/stage_c_runbook.py`:

  - SEQUENCE      — G1..G6 run in order; the green path reaches G6 and
    emits the token; a FAIL or CANNOT_ASSESS gate aborts the sequence
    there (later gates never execute).
  - FAIL-CLOSED   — malformed/secret-leaking env (G1), a preflight
    refusal (G2), a manifest isolation violation (G3), a stack that is
    down or partial (G4), and a failing acceptance suite (G5) each
    abort with the right exit class (1 = FINDINGS, 2 = CANNOT_ASSESS).
  - NO TOKEN      — the attestation token is written ONLY on unanimous
    pass; any other outcome writes nothing.
  - ZERO LEAK     — run report and token carry findings and key NAMES,
    never secret values (D-045/D-124).
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "local" / "scripts"))

import stage_c_runbook as rb  # noqa: E402
import stage_c_acceptance as acc  # noqa: E402

TEMPLATE = REPO / ".env.staging.template"
MANIFEST = REPO / "local" / "infra" / "compose.staging.yml"
GRANTS = REPO / "docs" / "deployment" / "stage-c-owner-grants.md"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def acceptance_ok() -> dict:
    return {"schema_version": "stage_c.acceptance_run.v1", "ok": True,
            "verdict": "ACCEPTED",
            "probes": [{"name": "probe", "verdict": "PASS"}] * 10,
            "failing": []}


def green_kwargs(env_text: str, manifest_text: str,
                 grants_text: str) -> dict:
    return dict(
        env_text=env_text,
        manifest_text=manifest_text,
        grants_text=grants_text,
        preflight_fn=lambda env, env_name="staging": {"ok": True},
        stack_fn=lambda: list(acc.SANCTIONED_CONTAINERS),
        acceptance_fn=acceptance_ok,
        grants_verify_fn=lambda text: {
            "ok": False, "verdict": "NOT_AUTHORIZED", "signed_count": 0,
            "rows": {}, "findings": []},
        write_fn=lambda path, text: None,
        candidate_commit_fn=lambda: "testcommit",
    )


def run_green(**overrides) -> dict:
    kw = green_kwargs(_read(TEMPLATE), _read(MANIFEST), _read(GRANTS))
    kw.update(overrides)
    return rb.run_gates(**kw)


def gate_ids(res: dict) -> list:
    return [g["gate"] for g in res["gates"]]


class GreenSequence(unittest.TestCase):
    def test_all_six_gates_run_in_order_and_emit_token(self):
        seen = []
        captured = {}

        def write_capture(path, text):
            seen.append(path)
            captured["blob"] = text

        res = run_green(write_fn=write_capture)
        self.assertEqual(gate_ids(res),
                         ["G1", "G2", "G3", "G4", "G5", "G6"])
        self.assertEqual(res["verdict"], "READY")
        self.assertTrue(res["attestation_emitted"])
        self.assertEqual(len(seen), 1)

        token = json.loads(captured["blob"])
        self.assertEqual(token["schema_version"],
                         "stage_c.runbook_attestation.v1")
        self.assertEqual(token["candidate_commit"], "testcommit")
        self.assertFalse(token["owner_grants"]["authorized"])
        self.assertIn("TECHNICAL CLEARANCE ONLY",
                      token["owner_grants"]["note"])
        self.assertEqual(len(token["bindings"]), 3)
        self.assertIn("attestation_digest", token)
        self.assertIn("attestation_digest", captured["blob"])

    def test_acceptance_json_captured_verbatim(self):
        res = run_green()
        self.assertEqual(res["acceptance_run"], acceptance_ok())

    def test_report_shape_matches_audit_conventions(self):
        res = run_green()
        self.assertEqual(res["schema_version"], "stage_c.runbook_run.v1")
        self.assertEqual(res["compatible_with"],
                         "qa.launch_attestation.v1")
        for g in res["gates"]:
            for field in ("gate", "name", "verdict", "detail"):
                self.assertIn(field, g)

    def test_grants_authorized_note_flips_when_signed(self):
        def signed(text):
            return {"ok": True, "verdict": "AUTHORIZED",
                    "signed_count": 12, "rows": {}, "findings": []}

        captured = {}

        def write_capture(path, text):
            captured["blob"] = text

        run_green(grants_verify_fn=signed, write_fn=write_capture)
        token = json.loads(captured["blob"])
        self.assertTrue(token["owner_grants"]["authorized"])
        self.assertIn("fully signed",
                      token["owner_grants"]["note"])


class PerGateAbort(unittest.TestCase):
    def test_g1_malformed_env_aborts_before_g2(self):
        res = run_green(env_text="this is not KEY=VALUE\n")
        self.assertEqual(gate_ids(res), ["G1"])
        self.assertEqual(res["verdict"], "FINDINGS")
        self.assertFalse(res["attestation_emitted"])

    def test_g1_missing_contract_key_aborts(self):
        bad = "\n".join(line for line in _read(TEMPLATE).splitlines()
                        if not line.startswith("N8N_URL="))
        res = run_green(env_text=bad)
        self.assertEqual(gate_ids(res), ["G1"])
        self.assertIn("N8N_URL", res["gates"][0]["detail"])

    def test_g1_secret_shaped_value_aborts(self):
        bad = _read(TEMPLATE).replace(
            "CANONICAL_DB_PASSWORD=<GENERATE_SECURE_PASSWORD>",
            "CANONICAL_DB_PASSWORD=sk-abcdefghijklmnopqrstuvwxyz")
        res = run_green(env_text=bad)
        self.assertEqual(gate_ids(res), ["G1"])
        self.assertEqual(res["verdict"], "FINDINGS")
        self.assertIn("secret-shaped", res["gates"][0]["detail"])

    def test_g1_ai_key_aborts(self):
        res = run_green(env_text=_read(TEMPLATE)
                        + "AI_CREDENTIAL_REF=x\n")
        self.assertEqual(gate_ids(res), ["G1"])
        self.assertEqual(res["verdict"], "FINDINGS")
        self.assertIn("G-B4", res["gates"][0]["detail"])

    def test_g2_preflight_refusal_aborts(self):
        def refuse(env, env_name="staging"):
            from canonical.runtime_preflight import PreflightError
            raise PreflightError(
                "missing mandatory key: CANONICAL_DB_HOST")

        res = run_green(preflight_fn=refuse)
        self.assertEqual(gate_ids(res), ["G1", "G2"])
        self.assertEqual(res["verdict"], "FINDINGS")
        self.assertIn("CANONICAL_DB_HOST", res["gates"][-1]["detail"])
        self.assertFalse(res["attestation_emitted"])

    def test_g3_manifest_violation_aborts(self):
        bad = _read(MANIFEST).replace("    internal: true\n", "")
        res = run_green(manifest_text=bad)
        self.assertEqual(gate_ids(res), ["G1", "G2", "G3"])
        self.assertEqual(res["verdict"], "FINDINGS")
        self.assertFalse(res["attestation_emitted"])

    def test_g4_stack_down_aborts_cannot_assess(self):
        res = run_green(stack_fn=lambda: [])
        self.assertEqual(gate_ids(res), ["G1", "G2", "G3", "G4"])
        self.assertEqual(res["verdict"], "CANNOT_ASSESS")
        self.assertFalse(res["attestation_emitted"])

    def test_g4_partial_stack_names_the_gap(self):
        partial = [c for c in acc.SANCTIONED_CONTAINERS
                   if c != "engine-local-n8n"]
        res = run_green(stack_fn=lambda: partial)
        self.assertEqual(res["verdict"], "CANNOT_ASSESS")
        self.assertIn("engine-local-n8n", res["gates"][-1]["detail"])

    def test_g5_acceptance_failure_aborts(self):
        res = run_green(acceptance_fn=lambda: {
            "ok": False, "verdict": "FINDINGS", "probes": [],
            "failing": ["mysql_woo"]})
        self.assertEqual(gate_ids(res),
                         ["G1", "G2", "G3", "G4", "G5"])
        self.assertEqual(res["verdict"], "FINDINGS")
        self.assertIn("mysql_woo", res["gates"][-1]["detail"])
        self.assertFalse(res["attestation_emitted"])

    def test_g5_cannot_assess_aborts(self):
        res = run_green(acceptance_fn=lambda: {
            "ok": False, "verdict": "CANNOT_ASSESS", "probes": [],
            "failing": ["stack_identity"]})
        self.assertEqual(res["verdict"], "CANNOT_ASSESS")
        self.assertFalse(res["attestation_emitted"])

    def test_token_never_emitted_on_any_failure_path(self):
        failure_cases = {
            "g1_malformed": {"env_text": "garbage\n"},
            "g3_manifest": {"manifest_text": _read(MANIFEST).replace(
                "    internal: true\n", "")},
            "g4_stack": {"stack_fn": lambda: []},
            "g5_acceptance": {"acceptance_fn": lambda: {
                "ok": False, "verdict": "FINDINGS", "probes": [],
                "failing": ["x"]}},
        }
        for case, overrides in failure_cases.items():
            with self.subTest(case=case):
                res = run_green(**overrides)
                self.assertFalse(res["attestation_emitted"])
                self.assertNotIn("attestation_path", res)
                self.assertNotEqual(res["verdict"], "READY")


class ZeroLeak(unittest.TestCase):
    def test_reports_carry_no_secret_values(self):
        res = run_green()
        blob = json.dumps(res)
        for frag in ("hunter2", "engine-local-media-only", "sk-live",
                     "AKIA", "BEGIN PRIVATE"):
            self.assertNotIn(frag, blob)

    def test_token_carries_digests_not_values(self):
        captured = {}

        def write_capture(path, text):
            captured["blob"] = text

        run_green(write_fn=write_capture)
        token = json.loads(captured["blob"])
        self.assertNotIn("CANONICAL_DB_PASSWORD",
                         json.dumps(token["gates"]))
        for value in token["bindings"].values():
            self.assertEqual(len(value), 64)  # SHA-256 hex digests only


class CliContract(unittest.TestCase):
    def test_main_emits_real_token_on_green_path(self):
        import stage_c_acceptance as acc2
        if len(acc2.stack_containers()) != 5:
            self.skipTest("engine-local rehearsal stack not running")
        with tempfile.TemporaryDirectory() as td:
            token_path = Path(td) / "token.json"
            rc = rb.main(["--attestation-path", str(token_path)])
            self.assertEqual(rc, 0)
            self.assertTrue(token_path.exists())
            token = json.loads(
                token_path.read_text(encoding="utf-8"))
            self.assertEqual(token["schema_version"],
                             "stage_c.runbook_attestation.v1")
            self.assertNotIn("engine-local-media-only",
                             json.dumps(token))

    def test_main_exit_2_on_missing_env_artifact(self):
        rc = rb.main(["--env", "/nonexistent/env.template"])
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()

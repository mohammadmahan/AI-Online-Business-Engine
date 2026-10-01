"""Stage D — offline rehearsal battery (hermetic).

Pins `local/scripts/stage_d_rehearsal.py` — runbook steps 2–3 as ONE
fail-closed command over COMMITTED surfaces:

  PASS PATH     — the default committed example envelope yields
                  REHEARSAL_PASS: render, byte-identical re-render,
                  pre-flight HOLDS 7/7 (D1..D7).
  DETERMINISM   — two full rehearsals produce byte-identical JSON
                  payloads (clock-free, path-free summary).
  FAIL-CLOSED   — a missing envelope file, a missing/blank required
                  key, a generator refusal, a determinism break, and a
                  pre-flight violation all refuse with the exit-2
                  REHEARSAL_FAIL class; required-key NAMES are masked
                  (D-124); no partial artifacts survive.
  ZERO-LEAK     — stdout/report text passes the deep_redact belt
                  (injected secret shapes come out [REDACTED]); the
                  D-045 entropy scan is clean over the script and the
                  names-only example envelope.
  PURITY        — the rehearsal imports no subprocess/socket/urllib
                  and never touches os.environ; the repo tree gains
                  no artifact from a rehearsal run.
"""
from __future__ import annotations

import ast as _ast
import io
import json
import re
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "local" / "scripts"))
sys.path.insert(0, str(REPO / "local" / "infra" / "dokploy"))

import stage_d_rehearsal as rh  # noqa: E402
from stage_d_compose_generator import GenerationResult  # noqa: E402
from canonical.security_worker import entropy_scan  # noqa: E402

SCRIPT = REPO / "local" / "scripts" / "stage_d_rehearsal.py"
ENVELOPE = REPO / "local" / "infra" / "dokploy" / "stage_d_mock.env.example"
D_NAMES = ["D1_service_census", "D2_backend_internal",
           "D3_zero_published_ports", "D4_edge_exclusivity",
           "D5_probe_parity", "D6_strict_credential_refs",
           "D7_named_volumes"]


def _captured_main(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = rh.main(argv)
    return rc, out.getvalue(), err.getvalue()


class RehearsalHappyPath(unittest.TestCase):
    def test_default_envelope_full_pass(self):
        summary = rh.run_rehearsal(ENVELOPE)
        self.assertTrue(summary["ok"])
        self.assertEqual(summary["verdict"], "REHEARSAL_PASS")
        self.assertEqual([s["name"] for s in summary["steps"]],
                         ["D-144_generate", "render_determinism",
                          "preflight_manifest_holds_7_of_7"])
        self.assertTrue(all(s["verdict"] == "PASS"
                            for s in summary["steps"]))
        self.assertTrue(summary["deterministic"])

    def test_preflight_census_is_full_and_green(self):
        summary = rh.run_rehearsal(ENVELOPE)
        self.assertEqual(summary["preflight_verdict"], "HOLDS")
        self.assertEqual([c["name"] for c in summary["checks"]],
                         D_NAMES)
        self.assertTrue(all(c["verdict"] == "PASS"
                            for c in summary["checks"]))
        self.assertEqual(summary["findings"], [])

    def test_cli_json_schema_and_exit_zero(self):
        rc, out, _ = _captured_main(["--json"])
        self.assertEqual(rc, 0)
        payload = json.loads(out)
        self.assertEqual(payload["schema_version"],
                         "stage_d.rehearsal.v1")
        self.assertEqual(payload["compatible_with"],
                         "qa.launch_attestation.v1")
        self.assertTrue(payload["ok"])
        # context-proof display: the 64-hex fingerprint is masked in
        # EVERY import context (D-124), never only when a belt gets it
        self.assertEqual(payload["env_fingerprint"],
                         "<env-fingerprint>")

    def test_cli_text_mode(self):
        rc, out, _ = _captured_main([])
        self.assertEqual(rc, 0)
        self.assertIn("STAGE D OFFLINE REHEARSAL", out)
        self.assertIn("REHEARSAL_PASS", out)
        self.assertIn("NOT a deployment authorization", out)


class Determinism(unittest.TestCase):
    def test_two_full_rehearsals_identical(self):
        a = json.dumps(rh.run_rehearsal(ENVELOPE), sort_keys=True)
        b = json.dumps(rh.run_rehearsal(ENVELOPE), sort_keys=True)
        self.assertEqual(a, b)

    def test_cli_output_byte_identical(self):
        _, out1, _ = _captured_main(["--json"])
        _, out2, _ = _captured_main(["--json"])
        self.assertEqual(out1, out2)

    def test_fingerprint_is_stable_64hex_at_api_level(self):
        fp = rh.run_rehearsal(ENVELOPE)["env_fingerprint"]
        self.assertTrue(re.fullmatch(r"[0-9a-f]{64}", fp))
        self.assertEqual(
            fp, rh.run_rehearsal(ENVELOPE)["env_fingerprint"])


class FailClosedRefusals(unittest.TestCase):
    def test_missing_envelope_file_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "nope.env"
            summary = rh.run_rehearsal(missing)
        self.assertFalse(summary["ok"])
        self.assertEqual(summary["verdict"], "REHEARSAL_FAIL")
        self.assertEqual(summary["steps"][0]["name"], "envelope")
        self.assertIn("not found", summary["steps"][0]["detail"])

    def test_missing_required_key_masked_not_named(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = Path(tmp) / "partial.env"
            env.write_text("CANONICAL_DB_NAME=__MOCK__\n",
                           encoding="utf-8")
            rc, out, _ = _captured_main(["--envelope", str(env),
                                         "--json"])
        self.assertEqual(rc, 2)
        self.assertIn("CAN***", out)
        self.assertIn("RED***", out)
        self.assertNotIn("REDIS_PASSWORD", out)
        self.assertNotIn("CANONICAL_DB_USER", out)
        self.assertNotIn("CANONICAL_DB_PASSWORD", out)

    def test_blank_value_counts_as_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = Path(tmp) / "blank.env"
            env.write_text(
                "CANONICAL_DB_NAME=__MOCK__\n"
                "CANONICAL_DB_USER=__MOCK__\n"
                "CANONICAL_DB_PASSWORD=__MOCK__\n"
                "REDIS_PASSWORD=   \n", encoding="utf-8")
            rc, out, _ = _captured_main(["--envelope", str(env),
                                         "--json"])
        self.assertEqual(rc, 2)
        self.assertIn("RED***", out)

    def _swap_generator(self, replacement):
        old = rh.StageDComposeGenerator
        rh.StageDComposeGenerator = replacement
        self.addCleanup(setattr, rh, "StageDComposeGenerator", old)

    def test_generator_refusal_is_fail_closed(self):
        class _Stub:
            def generate(self, images, env):
                return GenerationResult("CANNOT_GENERATE", "",
                                        ("missing secret CAN***",),
                                        "fp")
        self._swap_generator(_Stub)
        rc, out, _ = _captured_main(["--json"])
        self.assertEqual(rc, 2)
        payload = json.loads(out)
        self.assertEqual(payload["steps"][0]["name"],
                         "D-144_generate")
        self.assertFalse(payload["deterministic"])

    def test_determinism_break_is_fail_closed(self):
        class _Stub:
            calls = 0

            def generate(self, images, env):
                _Stub.calls += 1
                text = f"services: {{}} # render {_Stub.calls}"
                return GenerationResult("RENDERED", text, (), "fp")
        self._swap_generator(_Stub)
        rc, out, _ = _captured_main(["--json"])
        self.assertEqual(rc, 2)
        payload = json.loads(out)
        self.assertEqual(payload["steps"][0]["name"],
                         "render_determinism")
        self.assertFalse(payload["deterministic"])

    def test_preflight_violation_is_fail_closed(self):
        def _stub_main(argv):
            print(json.dumps({"ok": False, "verdict": "VIOLATIONS",
                              "checks": [], "failing":
                              ["D3_zero_published_ports"]}))
            return 1
        old = rh.pf
        rh.pf = types.SimpleNamespace(main=_stub_main)
        self.addCleanup(setattr, rh, "pf", old)
        rc, out, _ = _captured_main(["--json"])
        self.assertEqual(rc, 2)
        payload = json.loads(out)
        self.assertEqual(payload["steps"][0]["name"],
                         "preflight_manifest")
        self.assertIn("D3_zero_published_ports",
                      payload["findings"])

    def test_unparsable_preflight_output_is_fail_closed(self):
        def _stub_main(argv):
            print("not json at all")
            return 0
        old = rh.pf
        rh.pf = types.SimpleNamespace(main=_stub_main)
        self.addCleanup(setattr, rh, "pf", old)
        rc, out, _ = _captured_main(["--json"])
        self.assertEqual(rc, 2)
        self.assertIn("unparsable", out)


class ZeroLeakAndPurity(unittest.TestCase):
    def test_deep_redact_belt_covers_injected_secret(self):
        class _Stub:
            def generate(self, images, env):
                return GenerationResult(
                    "CANNOT_GENERATE", "",
                    ("password=supersecret-value-123",), "fp")
        old = rh.StageDComposeGenerator
        rh.StageDComposeGenerator = _Stub
        try:
            rc, out, _ = _captured_main(["--json"])
        finally:
            rh.StageDComposeGenerator = old
        self.assertEqual(rc, 2)
        self.assertNotIn("supersecret-value-123", out)
        self.assertIn("[REDACTED]", out)

    def test_example_envelope_is_names_only(self):
        text = ENVELOPE.read_text(encoding="utf-8")
        values = [line.split("=", 1)[1].strip()
                  for line in text.splitlines()
                  if line.strip() and not line.startswith("#")
                  and "=" in line]
        self.assertTrue(values)
        self.assertTrue(all(v == "__MOCK__" for v in values))

    def test_mock_values_never_reach_the_manifest(self):
        env = rh._build_envelope(ENVELOPE)
        result = rh.StageDComposeGenerator().generate(
            rh.MOCK_IMAGE_REFS, env)
        self.assertEqual(result.verdict, "RENDERED")
        self.assertNotIn("__MOCK__", result.manifest)

    def test_d045_entropy_scan_clean(self):
        report = entropy_scan([str(SCRIPT), str(ENVELOPE)])
        self.assertTrue(report["clean"])
        self.assertEqual(report["flagged"], [])

    def test_ast_purity_no_process_network_environ(self):
        tree = _ast.parse(SCRIPT.read_text(encoding="utf-8"))
        banned = {"subprocess", "socket", "urllib", "requests",
                  "http", "ftplib"}
        for node in _ast.walk(tree):
            if isinstance(node, _ast.Import):
                for alias in node.names:
                    self.assertNotIn(alias.name.split(".")[0], banned)
            elif isinstance(node, _ast.ImportFrom):
                self.assertNotIn((node.module or "").split(".")[0],
                                 banned)
            elif isinstance(node, _ast.Attribute):
                self.assertNotIn(node.attr, {"environ", "getenv"})

    def test_rehearsal_leaves_no_repo_artifacts(self):
        watch = REPO / "local" / "infra" / "dokploy"
        before = {p.name for p in watch.iterdir()}
        rc, _, _ = _captured_main(["--json"])
        after = {p.name for p in watch.iterdir()}
        self.assertEqual(rc, 0)
        self.assertEqual(after - before, set())


if __name__ == "__main__":
    unittest.main()

"""Stage C grant-gate integration battery (offline).

Pins the fail-closed chaining of `verify_stage_c_grants.py` into the
deployment pipeline:

  - LAUNCH ATTESTATION — `launch_attestation.py --check-stage-c` folds
    an unsigned SC-1..SC-12 checklist into the verdict as an explicit
    `SC-GRANTS` blocker (GO downgraded to NO_GO); the flag is additive:
    absent flag leaves the D-138 attestation semantics untouched, and a
    NO_GO is never upgraded by the gate.
  - PROBE GATES — `validate_vps_target.py --require-grants` and
    `validate_vps_readiness.py --require-grants` refuse (exit 2) before
    ANY probe work when the checklist is unsigned or unreadable
    (SC_GRANTS_ARTIFACT overrides the artifact path); with a fully
    signed artifact the gate prints AUTHORIZED and the probe proceeds.
  - RUNBOOK SCAFFOLD — `docs/deployment/stage-c-runbook.md` orchestrates
    the authoritative G1–G6 taxonomy with an append-only log that
    starts EMPTY.
"""
from __future__ import annotations

import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "local" / "scripts"))

import launch_attestation as la  # noqa: E402
import validate_vps_target as tgt  # noqa: E402
import validate_vps_readiness as vps  # noqa: E402

GRANTS_DOC = REPO / "docs" / "deployment" / "stage-c-owner-grants.md"
RUNBOOK = REPO / "docs" / "deployment" / "stage-c-runbook.md"
TARGET_SCRIPT = REPO / "local" / "scripts" / "validate_vps_target.py"

SIG_HEADER = "| # | Granted by (name) | Date | Evidence reference | Notes |\n"
SIG_SEPARATOR = "|---|-------------------|------|--------------------|-------|\n"


def signed_artifact_text() -> str:
    rows = "\n".join(
        f"| SC-{i} | Owner Name | 2026-09-29 | evidence-{i} | |"
        for i in range(1, 13))
    return ("\n## 3. Signature block\n\n" + SIG_HEADER + SIG_SEPARATOR
            + rows + "\n\n## 4. Gate exit criteria\n")


def go_attestation() -> dict:
    return {"launch_verdict": "GO", "blockers": [],
            "attestation_hash": "x" * 64, "candidate_commit": "test",
            "config_fingerprint": "f" * 64, "approval_state": "unsigned",
            "health_report": {"overall": "PASS", "probes": []}}


class LaunchAttestationStageCGate(unittest.TestCase):
    def test_flag_downgrades_go_with_sc_grants_blocker(self):
        with mock.patch.object(la, "run_attestation",
                               return_value=go_attestation()), \
             mock.patch.object(la, "stack_up", return_value=True):
            rc = la.main(["--check-stage-c"])
        self.assertEqual(rc, 1)  # NO_GO ⇒ rc 1

    def test_no_go_verdict_gains_no_duplicate_blocker(self):
        att = dict(go_attestation(), launch_verdict="NO_GO",
                   blockers=["BAC-001"])
        with mock.patch.object(la, "run_attestation", return_value=att), \
             mock.patch.object(la, "stack_up", return_value=True), \
             contextlib.redirect_stdout(io.StringIO()) as out, \
             contextlib.redirect_stderr(io.StringIO()) as err:
            rc = la.main(["--check-stage-c"])
        self.assertEqual(rc, 1)
        self.assertIn("DENIED", err.getvalue())
        # the gate never mutates an existing NO_GO's blocker set — it
        # only downgrades a GO verdict
        self.assertIn("blockers: BAC-001", out.getvalue())
        self.assertNotIn("SC-GRANTS", out.getvalue())

    def test_flag_absent_leaves_attestation_semantics_untouched(self):
        with mock.patch.object(la, "run_attestation",
                               return_value=go_attestation()), \
             mock.patch.object(la, "stack_up", return_value=True):
            rc = la.main([])
        self.assertEqual(rc, 0)

    def test_unreadable_grant_artifact_fails_closed_rc2(self):
        # the refusal happens at the gate, so the attestation itself is
        # mocked — the branch must not depend on a live stack or a
        # composed GO (deterministic, fast)
        with mock.patch.object(la, "run_attestation",
                               return_value=go_attestation()) as ra, \
             mock.patch.object(la, "stack_up", return_value=True), \
             mock.patch.dict(os.environ,
                             {"SC_GRANTS_ARTIFACT": "/nonexistent/g.md"}):
            with contextlib.redirect_stderr(io.StringIO()):
                rc = la.main(["--check-stage-c"])
        self.assertEqual(rc, 2)
        ra.assert_called_once()  # attestation composed, then gate refused


class TargetProbeGate(unittest.TestCase):
    def test_unsigned_checklist_refuses_before_any_probe(self):
        with mock.patch("sys.argv",
                        ["validate_vps_target.py", "--require-grants"]), \
             mock.patch.object(tgt, "offline_mode") as om, \
             mock.patch.object(tgt, "probe_mode") as pm, \
             contextlib.redirect_stdout(io.StringIO()) as out:
            with self.assertRaises(SystemExit) as ctx:
                tgt.main()
        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("grants incomplete", out.getvalue())
        om.assert_not_called()
        pm.assert_not_called()

    def test_unreadable_artifact_refuses_rc2(self):
        with mock.patch("sys.argv",
                        ["validate_vps_target.py", "--require-grants"]), \
             mock.patch.dict(os.environ,
                             {"SC_GRANTS_ARTIFACT": "/nonexistent/g.md"}), \
             contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                tgt.main()
        self.assertEqual(ctx.exception.code, 2)

    def test_signed_checklist_authorizes_and_probe_runs(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "signed.md"
            path.write_text(signed_artifact_text(), encoding="utf-8")
            env = dict(os.environ, SC_GRANTS_ARTIFACT=str(path))
            with mock.patch.dict(os.environ, env), \
                 mock.patch("sys.argv",
                            ["validate_vps_target.py", "--require-grants"]), \
                 mock.patch.object(tgt, "offline_mode", return_value=True), \
                 mock.patch.object(tgt, "probe_mode"), \
                 contextlib.redirect_stdout(io.StringIO()) as out:
                with self.assertRaises(SystemExit) as ctx:
                    tgt.main()
        self.assertEqual(ctx.exception.code, 0)
        self.assertIn("AUTHORIZED (12/12 signed)", out.getvalue())

    def test_without_flag_the_offline_harness_is_unchanged(self):
        with mock.patch("sys.argv", ["validate_vps_target.py"]), \
             contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                tgt.main()
        self.assertEqual(ctx.exception.code, 0)

    def test_real_cli_refuses_unsigned_rc2(self):
        r = subprocess.run([sys.executable, str(TARGET_SCRIPT),
                            "--require-grants"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn("grants incomplete", r.stdout)


class ReadinessProbeGate(unittest.TestCase):
    def _run_main(self, argv) -> tuple:
        out = io.StringIO()
        with mock.patch("sys.argv", argv), \
             contextlib.redirect_stdout(out):
            try:
                vps.main()
                code = None
            except SystemExit as e:
                code = e.code
        return code, out.getvalue()

    def test_unsigned_checklist_refuses_before_any_ssh(self):
        calls = []
        with mock.patch.object(vps, "ssh_run",
                               side_effect=lambda *a, **k:
                               calls.append(a) or (0, "", "")):
            code, out = self._run_main(
                ["validate_vps_readiness.py", "--host", "h",
                 "--user", "op", "--require-grants"])
        self.assertEqual(code, 2)
        self.assertIn("grants incomplete", out)
        self.assertEqual(calls, [])  # zero SSH attempts

    def test_signed_gate_authorized_then_probe_proceeds(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "signed.md"
            path.write_text(signed_artifact_text(), encoding="utf-8")
            env = dict(os.environ, SC_GRANTS_ARTIFACT=str(path))
            calls = []
            with mock.patch.dict(os.environ, env), \
                 mock.patch.object(vps, "ssh_run",
                                   side_effect=lambda *a, **k:
                                   calls.append(a) or (2, "", "stub-unreachable")):
                code, out = self._run_main(
                    ["validate_vps_readiness.py", "--host", "h",
                     "--user", "op", "--require-grants"])
        self.assertIn("AUTHORIZED (12/12 signed)", out)
        self.assertTrue(calls)  # the probe attempted SSH — past the gate
        self.assertEqual(code, 2)  # stub host unreachable ⇒ CANNOT ASSESS
        self.assertIn("SSH login failed", out)

    def test_unreadable_artifact_refuses_rc2(self):
        with mock.patch.dict(os.environ,
                             {"SC_GRANTS_ARTIFACT": "/nonexistent/g.md"}):
            code, out = self._run_main(
                ["validate_vps_readiness.py", "--host", "h",
                 "--user", "op", "--require-grants"])
        self.assertEqual(code, 2)
        self.assertIn("unreadable", out)
        self.assertIn("unreadable", out)


class RunbookScaffold(unittest.TestCase):
    def test_scaffold_exists_with_authoritative_gate_taxonomy(self):
        self.assertTrue(RUNBOOK.exists())
        text = RUNBOOK.read_text(encoding="utf-8")
        self.assertIn("## 1. Gate-to-grant cross-walk", text)
        for gate in ("G1", "G2", "G3", "G4", "G5", "G6"):
            self.assertIn(gate, text)
        self.assertIn("docs/runbooks/dokploy-vps-provisioning.md", text)

    def test_log_starts_empty_and_is_append_only(self):
        text = RUNBOOK.read_text(encoding="utf-8")
        self.assertIn("append-only", text.lower())
        self.assertIn("| | | | | |", text)  # the empty log row

    def test_scaffold_documents_all_six_execution_phases(self):
        text = RUNBOOK.read_text(encoding="utf-8")
        for phase in ("P1", "P2", "P3", "P4", "P5", "P6"):
            self.assertIn(phase, text)
        self.assertIn("run_staging_smoke_tests.py", text)


if __name__ == "__main__":
    unittest.main()

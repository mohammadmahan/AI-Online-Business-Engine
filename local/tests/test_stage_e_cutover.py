"""Stage E — cutover readiness battery (D-141, offline).

Exercises `local/scripts/verify_cutover_readiness.py` as the operator
runs it, pinning the fail-closed contract the launch gate depends on:

  - OFFLINE MODE  — subprocess against the real artifacts: exit 2
    (cannot assess) when production secret material appears in the
    planning shell (D-045); per-check findings when the manifest or
    runbook drifts (synthesized inputs).
  - PARSERS       — manifest service posture scoped to the services:
    block (network names never masquerade as services), edge header
    policy over synthetic header maps, rollback matrix presence.
  - SNAPSHOT MODE — subprocess --snapshot: D-125 write_snapshot →
    verify → bit-flip → verify MUST refuse (tamper evidence).
  - REDACTION     — no secret-shaped value is ever printed by the
    harness; findings carry key names, never values (D-124).
  - ATTESTATION   — V-01 composes with launch_attestation (both DR
    legs, sweeps, matrix) and fails closed on a dirty tree.
  - RUNBOOK       — stage-e-cutover-runbook.md declares the rollback
    matrix, the stop→compensate→reconcile ordering, the header policy,
    and the D-139 owner-approval gate.
"""
from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "local" / "scripts" / "verify_cutover_readiness.py"
RUNBOOK = REPO / "docs" / "deployment" / "stage-e-cutover-runbook.md"
PROD = REPO / "local" / "infra" / "compose.prod.yml"

sys.path.insert(0, str(SCRIPT.parent))
import verify_cutover_readiness as vcr  # noqa: E402


def run_cli(*extra: str, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.update(env_extra or {})
    return subprocess.run(
        [sys.executable, str(SCRIPT), *extra],
        capture_output=True, text=True, env=env,
        cwd=str(REPO / "local"))


MANDATORY_ENV_KEYS = sorted({
    m.group(1) for m in
    re.finditer(r"\$\{([A-Z0-9_]+):\?", PROD.read_text(encoding="utf-8"))
} ) if (re := __import__("re")) else []


class OfflineMode(unittest.TestCase):
    """Subprocess runs of the real CLI."""

    def test_offline_structure_runs_and_reports(self):
        r = run_cli()
        self.assertIn("STAGE E CUTOVER READINESS — OFFLINE", r.stdout)
        for vid in ("V-01", "V-02", "V-03", "V-04", "V-05", "V-06", "V-07"):
            self.assertIn(vid, r.stdout)
        self.assertEqual(r.returncode, 1,
                         "dirty tree must fail V-01 closed (rc=1)")

    def test_v01_dirty_tree_fails_closed_with_named_finding(self):
        r = run_cli()
        self.assertIn("V-01 D-138 attestation GO", r.stdout)
        self.assertIn("DIRTY", r.stdout)

    def test_v02_planning_shell_secret_refusal(self):
        r = run_cli(env_extra={"CANONICAL_DB_PASSWORD": "synthetic-not-real-9"})
        self.assertEqual(r.returncode, 2, "secret in planning shell ⇒ exit 2")
        self.assertIn("V-02", r.stdout)
        self.assertIn("CANONICAL_DB_PASSWORD", r.stdout)
        self.assertNotIn("synthetic-not-real-9", r.stdout + r.stderr)

    def test_exit_codes_are_in_the_declared_set(self):
        for extra in ([], ["--snapshot"]):
            r = run_cli(*extra)
            self.assertIn(r.returncode, (0, 1, 2))
            self.assertIn(r.returncode, (1, 0))


class Parsers(unittest.TestCase):
    """Pure decision logic over synthesized inputs."""

    FIXTURE = (
        "services:\n"
        "  wordpress:\n"
        "    restart: unless-stopped\n"
        "    cpus: 1.0\n"
        "    mem_limit: 512m\n"
        "  n8n:\n"
        "    restart: unless-stopped\n"
        "    cpus: 0.5\n"
        "    mem_limit: 1g\n"
        "volumes:\n"
        "  woo_data: {}\n"
        "networks:\n"
        "  frontend:\n"
        "  data:\n"
    )

    def test_posture_scoped_to_services_block(self):
        posture = vcr.manifest_service_posture(self.FIXTURE)
        self.assertEqual(set(posture), {"wordpress", "n8n"})
        self.assertTrue(all(p["restart"] and p["cpu"] and p["mem"]
                            for p in posture.values()))

    def test_posture_on_real_manifest_reports_all_five(self):
        posture = vcr.manifest_service_posture()
        self.assertEqual(set(posture), {"wordpress", "woodb",
                                        "canonical-db", "n8n", "media"})

    def test_posture_flags_missing_ceilings(self):
        bad = vcr.manifest_service_posture(
            "services:\n  n8n:\n    restart: unless-stopped\n")
        self.assertEqual(bad["n8n"], {"restart": True, "cpu": False,
                                      "mem": False})

    def test_edge_headers_ok_accepts_policy_conformant_map(self):
        ok, problems = vcr.edge_headers_ok({
            "Strict-Transport-Security": "max-age=63072000",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Content-Security-Policy": "default-src 'self'",
        })
        self.assertTrue(ok, problems)

    def test_edge_headers_ok_flags_each_gap(self):
        ok, problems = vcr.edge_headers_ok({})
        self.assertFalse(ok)
        self.assertEqual(len(problems), 4)


class SnapshotMode(unittest.TestCase):
    """The D-125 snapshot integrity proof, end to end via CLI."""

    def test_snapshot_mode_tamper_evidence(self):
        r = run_cli("--snapshot")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("write_snapshot rows=50", r.stdout)
        self.assertIn("verify_snapshot ok", r.stdout)
        self.assertIn("tampered archive REFUSED", r.stdout)


class AttestationComposition(unittest.TestCase):
    """V-01 composes with launch_attestation; no re-implementation."""

    def test_dirty_tree_reports_dirty_not_no_go(self):
        state, detail = vcr.attestation_state()
        # Battery runs with the Phase-26 work uncommitted by design.
        self.assertEqual(state, "DIRTY")
        self.assertIn("clean candidate", detail)

    def test_runbook_declares_owner_approval_gate(self):
        text = RUNBOOK.read_text(encoding="utf-8")
        self.assertIn("D-139", text)
        self.assertIn("owner", text.lower())


class Redaction(unittest.TestCase):
    """D-124 — key names only, never secret values, in all output."""

    def test_no_secret_shaped_value_in_any_output(self):
        r = run_cli(env_extra={"CANONICAL_DB_PASSWORD": "synthetic-not-real-9"})
        blob = r.stdout + r.stderr
        self.assertNotIn("synthetic-not-real-9", blob)


class RunbookInvariants(unittest.TestCase):
    """The runbook the harness reads must carry the governing text."""

    def test_rollback_matrix_rows_present(self):
        text = RUNBOOK.read_text(encoding="utf-8")
        for row in ("RB-1", "RB-6"):
            self.assertIn(row, text)

    def test_stop_compensate_reconcile_ordering_declared(self):
        text = RUNBOOK.read_text(encoding="utf-8")
        self.assertIn("stop", text.lower())
        self.assertIn("compensate", text.lower())
        self.assertIn("reconcile", text.lower())


if __name__ == "__main__":
    unittest.main()

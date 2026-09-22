"""Stage F/G — authorization gate & acceptance battery (D-141, offline).

Exercises the Stage F gate mode of `verify_cutover_readiness.py` and
pins the Stage G acceptance specification's rules:

  - CLI            — `--stage-f` runs the real gate: D-045 leak
    refusal (exit 2), matrix/runbook integrity PASS, unsigned rows
    FAIL (the honest default until the owner signs).
  - FAIL-CLOSED    — a truncated matrix raises; an empty or absent
    execution log means ZERO signatures (never an assumed pass); a
    forged log entry must carry the exact `SF-n | signed | ...`
    shape to count.
  - D-138 BINDING  — the Stage E edge report folds into MON-001 as
    monitoring evidence: findings or an unassessable edge are
    NEGATIVE evidence; absence of a report stays backward-compatible.
  - STAGE G RULES  — the acceptance spec declares GA-1..GA-7, the
    two-consecutive-cycle rule, REJECTED-on-any-FAIL fail-closed
    semantics, and the rollback interlock.
  - REDACTION      — no secret value ever reaches gate output
    (D-124); findings carry key names only.
"""
from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "local" / "scripts" / "verify_cutover_readiness.py"
STAGE_F_DOC = REPO / "docs" / "deployment" / "stage-f-authorization.md"
STAGE_G_DOC = REPO / "docs" / "deployment" / "stage-g-acceptance.md"
RUNBOOK = REPO / "docs" / "deployment" / "stage-e-cutover-runbook.md"

sys.path.insert(0, str(SCRIPT.parent))
import verify_cutover_readiness as vcr  # noqa: E402

sys.path.insert(0, str(REPO / "local"))
from canonical.launch_evidence import EvidenceCollector  # noqa: E402


def run_cli(*extra: str, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.update(env_extra or {})
    return subprocess.run(
        [sys.executable, str(SCRIPT), *extra],
        capture_output=True, text=True, env=env,
        cwd=str(REPO / "local"))


class StageFCLIMode(unittest.TestCase):
    """The real gate, run as the operator runs it."""

    def test_stage_f_mode_structure_and_expected_failures(self):
        r = run_cli("--stage-f")
        self.assertIn("STAGE F — AUTHORIZATION GATE", r.stdout)
        for fid in ("F-1", "F-2", "F-3", "F-4"):
            self.assertIn(fid, r.stdout)
        # F-1/F-2/F-4 structural checks pass on the committed docs
        self.assertIn("F-1 sign-off matrix integrity", r.stdout)
        # F-3 MUST fail: nothing has been signed (no cutover authorized)
        self.assertIn("F-3 owner sign-offs", r.stdout)
        self.assertIn("unsigned", r.stdout)
        self.assertIn("NOT SATISFIED", r.stdout)

    def test_stage_f_mode_exit_code_is_findings(self):
        r = run_cli("--stage-f")
        self.assertEqual(r.returncode, 1,
                         "unsigned gate ⇒ rc=1 (findings), never 0")

    def test_stage_f_secret_in_shell_refuses_before_evaluation(self):
        r = run_cli("--stage-f",
                    env_extra={"CANONICAL_DB_PASSWORD": "synthetic-not-real-9"})
        self.assertEqual(r.returncode, 2, "D-045 leak ⇒ exit 2")
        self.assertIn("F-4", r.stdout)
        self.assertIn("CANONICAL_DB_PASSWORD", r.stdout)
        self.assertNotIn("synthetic-not-real-9", r.stdout + r.stderr)
        self.assertNotIn("F-1", r.stdout, "checklist must not be evaluated")


class StageFFailClosed(unittest.TestCase):
    """Checklist integrity and signature parsing fail closed."""

    def test_truncated_matrix_raises(self):
        partial = "\n".join(
            STAGE_F_DOC.read_text(encoding="utf-8").splitlines()[:14])
        with self.assertRaises(ValueError):
            vcr.stage_f_checklist(partial)

    def test_matrix_parses_seven_rows_with_owner_and_binding(self):
        rows = vcr.stage_f_checklist()
        self.assertEqual(set(rows), {f"sf-{i}" for i in range(1, 8)})
        for k, v in rows.items():
            self.assertTrue(v["item"], k)
            self.assertTrue(v["owner"], k)
            self.assertTrue(v["binding"], k)

    def test_runbook_entry_window_maps_to_six_items(self):
        rows = vcr.runbook_signoff_rows()
        self.assertEqual(len(rows), 6)
        self.assertTrue(any("SSH" in r for r in rows))
        self.assertTrue(any("token" in r for r in rows))
        self.assertFalse(any("Post-window" in r for r in rows),
                         "rotation execution is SF-7, not an entry item")

    def test_empty_execution_log_means_zero_signatures(self):
        self.assertEqual(vcr.signed_entries(""), {})
        self.assertEqual(vcr.signed_entries("SF-1 | pending |\n"), {})

    def test_forged_or_malformed_entries_do_not_count(self):
        log = ("SF-1 | signed-by-me\n"          # wrong shape
               "SF-2 | signed | owner | 2026-09-22 | ref\n"  # correct
               "SF3 | signed | owner | 2026-09-22 | ref\n")  # bad id
        signed = vcr.signed_entries(log)
        self.assertEqual(set(signed), {"SF-2"})

    def test_unsigned_rows_are_listed_not_assumed(self):
        signed = vcr.signed_entries(
            "SF-1 | signed | owner | 2026-09-22 | ref\n")
        unsigned = [f"SF-{i}" for i in range(1, 8) if f"SF-{i}" not in signed]
        self.assertEqual(unsigned, [f"SF-{i}" for i in range(2, 8)])


class D138EdgeEvidenceBinding(unittest.TestCase):
    """Stage E edge probe folds into MON-001 as monitoring evidence."""

    def setUp(self):
        self.collector = EvidenceCollector(
            "0" * 40, {"env": "staging", "capture": False,
                       "payment_capture_enabled": False,
                       "shipping_purchase_enabled": False})

    def test_edge_findings_are_negative_evidence(self):
        rec = self.collector.monitoring_evidence(
            {"probes": {"pg": {"verdict": "PASS"}}},
            edge_report={"assessable": True,
                         "findings": ["HSTS max-age below policy"]})
        self.assertEqual(rec.outcome, "negative")
        self.assertIn("edge_findings", rec.detail)

    def test_unassessable_edge_is_negative_not_assumed(self):
        rec = self.collector.monitoring_evidence(
            {"probes": {}},
            edge_report={"assessable": False, "findings": []})
        self.assertEqual(rec.outcome, "negative")
        self.assertIn("CANNOT_ASSESS", rec.detail)

    def test_green_edge_keeps_positive_verdict(self):
        rec = self.collector.monitoring_evidence(
            {"probes": {"pg": {"verdict": "PASS"}}},
            edge_report={"assessable": True, "findings": []})
        self.assertEqual(rec.outcome, "positive")
        self.assertIn("edge=PASS", rec.detail)

    def test_absent_report_is_backward_compatible(self):
        rec = self.collector.monitoring_evidence(
            {"probes": {"pg": {"verdict": "PASS"}}})
        self.assertEqual(rec.outcome, "positive")
        self.assertNotIn("edge", rec.detail)

    def test_run_attestation_accepts_edge_report_parameter(self):
        import inspect
        import launch_attestation as la
        sig = inspect.signature(la.run_attestation)
        self.assertIn("edge_report", sig.parameters)

    def test_failing_probe_still_dominates(self):
        rec = self.collector.monitoring_evidence(
            {"probes": {"pg": {"verdict": "FAIL"}}},
            edge_report={"assessable": True, "findings": []})
        self.assertEqual(rec.outcome, "negative")


class StageGSpecRules(unittest.TestCase):
    """The acceptance specification must pin the fail-closed rules."""

    @classmethod
    def setUpClass(cls):
        cls.text = STAGE_G_DOC.read_text(encoding="utf-8")

    def test_all_seven_probe_ids_declared(self):
        for i in range(1, 8):
            self.assertIn(f"GA-{i}", self.text)

    def test_explicit_verdicts_and_no_partial_acceptance(self):
        self.assertIn("ACCEPTED", self.text)
        self.assertIn("REJECTED", self.text)
        self.assertIn("no partial acceptance", self.text.lower())

    def test_two_consecutive_cycles_required(self):
        self.assertIn("Two consecutive green cycles", self.text)
        self.assertIn("flakiness is not acceptance",
                      self.text.lower())

    def test_any_fail_or_cannot_assess_is_rejected(self):
        self.assertIn("Any FAIL or CANNOT_ASSESS", self.text)

    def test_rollback_interlock_preserves_rb_ordering(self):
        self.assertIn("RB-1..RB-6", self.text)
        self.assertIn("stop → compensate\n→ reconcile", self.text)

    def test_fresh_evidence_rule_for_recovery_probe(self):
        self.assertIn("GA-7", self.text)
        self.assertIn("does not satisfy GA-7", self.text)

    def test_no_secret_material_in_document(self):
        self.assertNotIn("synthetic-drill-only", self.text)


class Redaction(unittest.TestCase):
    """D-124 — findings carry key names, never values."""

    def test_stage_f_output_redacts_secret_values(self):
        r = run_cli("--stage-f",
                    env_extra={"N8N_ENCRYPTION_KEY": "synthetic-not-real-8"})
        self.assertNotIn("synthetic-not-real-8", r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()

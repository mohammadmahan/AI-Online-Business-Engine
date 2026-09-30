"""Stage C owner-grants readiness-audit battery (offline).

Pins `local/scripts/stage_c_grants_audit.py` over the committed
signable checklist:

  - the committed artifact audits READY with the machine verifier's
    standing verdict exactly NOT_AUTHORIZED (0/12) — the required
    fail-closed answer while unsigned;
  - every structural defect class fails closed: a missing §2 or §3
    row (slot census), an incomplete §2 matrix row, a half-filled or
    value-bearing §3 signature row (nothing is pre-signed), a
    pre-fill without its RATIFICATION-PENDING note, and a missing
    structural anchor;
  - `--simulate-sign` proves the AUTHORIZED side (12/12) over a
    synthetic fully-signed copy while the REAL artifact stays
    byte-identical (zero mutation, D-045);
  - the fail-closed execution chain holds: the grants verifier
    refuses (rc 1) on the standing artifact;
  - zero-leak: audit verdicts carry row ids and structural markers —
    never signature or credential values (D-045/D-124).
"""
from __future__ import annotations

import io
import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "local" / "scripts"))

import stage_c_grants_audit as ga  # noqa: E402
import verify_stage_c_grants as vsg  # noqa: E402

ARTIFACT = REPO / "docs" / "deployment" / "stage-c-owner-grants.md"


def _read() -> str:
    return ARTIFACT.read_text(encoding="utf-8")


class CommittedArtifactAudit(unittest.TestCase):
    def test_committed_artifact_audits_ready(self):
        rep = ga.audit_readiness(_read())
        self.assertTrue(rep["ok"])
        self.assertEqual(rep["verdict"], "READY")
        self.assertEqual(len(rep["checks"]), 6)
        self.assertEqual(rep["failing"], [])

    def test_machine_verifier_standing_verdict_is_fail_closed(self):
        rep = ga.audit_readiness(_read())
        mv = rep["machine_verifier"]
        self.assertEqual(mv["verdict"], "NOT_AUTHORIZED")
        self.assertEqual(mv["signed_count"], 0)
        self.assertFalse(mv["ok"])
        self.assertTrue(rep["checks"][5]["name"] == "A6_fail_closed_verdict")
        self.assertEqual(rep["checks"][5]["verdict"], "PASS")

    def test_simulate_sign_reaches_authorized_without_mutation(self):
        before = ARTIFACT.read_bytes()
        sim = ga.simulate_sign(_read())
        self.assertTrue(sim["verifier_ok"])
        self.assertEqual(sim["verifier_verdict"], "AUTHORIZED")
        self.assertEqual(sim["signed_count"], 12)
        self.assertFalse(sim["artifact_mutated"])
        self.assertEqual(ARTIFACT.read_bytes(), before)

    def test_grants_verifier_refuses_the_standing_artifact(self):
        self.assertEqual(vsg.main([]), 1)  # fail closed, non-zero


class StructuralDefectsFailClosed(unittest.TestCase):
    def _audit(self, text: str) -> dict:
        return ga.audit_readiness(text)

    def test_missing_signature_row_fails_census(self):
        text = "\n".join(l for l in _read().splitlines()
                         if not l.startswith("| SC-12 |"))
        rep = self._audit(text)
        self.assertEqual(rep["verdict"], "NOT_READY")
        self.assertIn("A2_slot_census", rep["failing"])

    def test_missing_matrix_row_fails_census(self):
        lines = _read().splitlines()
        drop = next(i for i, l in enumerate(lines)
                    if l.startswith("| SC-5 ") and "DNS" in l)
        rep = self._audit("\n".join(lines[:drop] + lines[drop + 1:]))
        self.assertIn("A2_slot_census", rep["failing"])

    def test_incomplete_matrix_row_fails(self):
        text = _read().replace(
            "| SC-3 | Firewall surface — UFW/SSH hardening baseline; "
            "ports 18080 or the approved proxy surface | §21.6.1 | "
            "signed row naming the approved port set | host-bound | "
            "host replacement |",
            "| SC-3 | Firewall surface | §21.6.1 | | | |")
        rep = self._audit(text)
        self.assertIn("A3_matrix_completeness", rep["failing"])

    def test_half_filled_signature_row_is_flagged(self):
        rep = self._audit(_read().replace(
            "| SC-1 | | | | |", "| SC-1 | Someone | | | |"))
        self.assertIn("A4_signature_rows_wellformed", rep["failing"])

    def test_value_bearing_pending_row_is_flagged(self):
        rep = self._audit(_read().replace(
            "| SC-9 | | | | RATIFICATION-PENDING — decision pre-filled: "
            "`MANUAL` |",
            "| SC-9 | Owner | 2026-09-29 | manual-decision | "
            "RATIFICATION-PENDING |"))
        self.assertIn("A4_signature_rows_wellformed", rep["failing"])

    def test_missing_pending_note_breaks_prefill_coherence(self):
        rep = self._audit(_read().replace(
            "| SC-8 | | | | RATIFICATION-PENDING — decision pre-filled: "
            "`TUNNEL` |",
            "| SC-8 | | | | |"))
        self.assertIn("A5_prefill_coherence", rep["failing"])

    def test_missing_structure_anchor_fails(self):
        rep = self._audit(_read().replace("## 3. Signature block",
                                          "## 3. Signatures"))
        self.assertIn("A1_structure_marks", rep["failing"])


class CliContract(unittest.TestCase):
    def test_cli_ready_rc0(self):
        r = subprocess.run(
            [sys.executable, str(REPO / "local" / "scripts"
                                 / "stage_c_grants_audit.py")],
            capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        self.assertIn("READY", r.stdout)
        self.assertIn("NOT_AUTHORIZED (0/12 signed)", r.stdout)

    def test_cli_simulate_flag_authorized(self):
        r = subprocess.run(
            [sys.executable, str(REPO / "local" / "scripts"
                                 / "stage_c_grants_audit.py"),
             "--simulate-sign", "--json"],
            capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        payload = json.loads(r.stdout)
        self.assertEqual(payload["simulated_signoff"]
                         ["verifier_verdict"], "AUTHORIZED")

    def test_cli_missing_artifact_rc2(self):
        r = subprocess.run(
            [sys.executable, str(REPO / "local" / "scripts"
                                 / "stage_c_grants_audit.py"),
             "--artifact", "/nonexistent/grants.md"],
            capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn("unreadable", r.stdout)


class ZeroLeak(unittest.TestCase):
    def test_reports_carry_no_signature_or_credential_values(self):
        rep = ga.audit_readiness(_read())
        blob = json.dumps(rep)
        for frag in ("Owner Name", "2026-09-30", "evidence-SC",
                     "engine-local-media-only", "AKIA", "sk-live",
                     "BEGIN PRIVATE"):
            self.assertNotIn(frag, blob)


if __name__ == "__main__":
    unittest.main()

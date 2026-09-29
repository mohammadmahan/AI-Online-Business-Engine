"""Stage C — owner-grant checklist battery (D-141 ladder, offline).

Pins the fail-closed contract of `local/scripts/verify_stage_c_grants.py`
over the §3 signature block of
`docs/deployment/stage-c-owner-grants.md`:

  - CLI            — exit 1 while any row is unsigned or
    RATIFICATION-PENDING (the honest default until the owner signs);
    exit 0 only on a fully-signed artifact; exit 2 on a missing
    artifact.
  - FAIL-CLOSED    — structural defects (missing signature section,
    missing header, ragged separator, wrong row count, out-of-order
    ids) are verdicts, never crashes.
  - DATE RULE      — a signature date must be ISO YYYY-MM-DD; prose
    dates refuse.
  - NOT A GRANT    — a pre-filled decision row is not a grant: only
    name + date + evidence turns a row SIGNED; a completed signature
    block dominates a RATIFICATION-PENDING note.
  - D-045          — verifier verdict output carries no secret-shaped
    material.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "local" / "scripts"))

import verify_stage_c_grants as vsg  # noqa: E402

ARTIFACT = REPO / "docs" / "deployment" / "stage-c-owner-grants.md"
SCRIPT = REPO / "local" / "scripts" / "verify_stage_c_grants.py"

SIG_HEADER = "| # | Granted by (name) | Date | Evidence reference | Notes |\n"
SIG_SEPARATOR = "|---|-------------------|------|--------------------|-------|\n"


def signed_row(rid: str, notes: str = "") -> str:
    return f"| {rid} | Owner Name | 2026-09-29 | runbook log entry | {notes} |"


def artifact_text(rows) -> str:
    header = (
        "# Stage C Owner Authorization — Signable Grant Checklist\n"
        "\n"
        "## 2. Sign-off matrix\n"
        "\n"
        "| # | Grant item | Source | Grant form | Binding | Expiry |\n"
        "|---|------------|--------|------------|---------|--------|\n"
    )
    matrix = "\n".join(
        f"| {rid} | item {rid} | §21.6 | form | bound | exp |" for rid in rows)
    sig = "\n".join(rows)
    tail = "\n\n## 4. Gate exit criteria\n\n- rules here\n"
    return (header + matrix
            + "\n\n## 3. Signature block\n\n" + SIG_HEADER + SIG_SEPARATOR
            + sig + tail)


SIGNED_ALL = artifact_text([signed_row(f"SC-{i}") for i in range(1, 13)])


class StructuralDefects(unittest.TestCase):
    def test_missing_signature_section_is_structural_defect(self):
        text = SIGNED_ALL.replace("## 3. Signature block", "## 3. Renamed")
        res = vsg.verify_grants(text)
        self.assertFalse(res["ok"])
        self.assertEqual(res["verdict"], "STRUCTURAL_DEFECT")

    def test_missing_header_is_structural_defect(self):
        text = SIGNED_ALL.replace(SIG_HEADER, "")
        res = vsg.verify_grants(text)
        self.assertFalse(res["ok"])
        self.assertEqual(res["verdict"], "STRUCTURAL_DEFECT")

    def test_ragged_separator_is_structural_defect(self):
        text = SIGNED_ALL.replace(SIG_SEPARATOR, "not-a-separator\n")
        row_ids, err = vsg.parse_signature_block(text)
        self.assertIsNone(row_ids)
        self.assertIn("separator", err)

    def test_wrong_row_count_refuses(self):
        rows = [signed_row(f"SC-{i}") for i in range(1, 12)]
        res = vsg.verify_grants(artifact_text(rows))
        self.assertFalse(res["ok"])
        self.assertTrue(any(f["status"] == "MALFORMED" for f in res["findings"]))

    def test_out_of_order_ids_refuse(self):
        ids = ["SC-1", "SC-2", "SC-3", "SC-4", "SC-5", "SC-6", "SC-7",
               "SC-8", "SC-9", "SC-10", "SC-12", "SC-11"]
        res = vsg.verify_grants(artifact_text([signed_row(i) for i in ids]))
        self.assertFalse(res["ok"])
        self.assertTrue(any("expected row SC-12" in f["reason"]
                            for f in res["findings"]))

    def test_empty_block_has_zero_signed_rows(self):
        rows = [f"| SC-{i} | | | | |" for i in range(1, 13)]
        res = vsg.verify_grants(artifact_text(rows))
        self.assertEqual(res["signed_count"], 0)
        self.assertFalse(res["ok"])


class RowSemantics(unittest.TestCase):
    def test_all_signed_is_authorized(self):
        res = vsg.verify_grants(SIGNED_ALL)
        self.assertTrue(res["ok"])
        self.assertEqual(res["verdict"], "AUTHORIZED")
        self.assertEqual(res["signed_count"], 12)

    def test_completed_signature_dominates_pending_note(self):
        rows = [signed_row(f"SC-{i}",
                           "RATIFICATION-PENDING" if i == 8 else "")
                for i in range(1, 13)]
        res = vsg.verify_grants(artifact_text(rows))
        self.assertTrue(res["ok"])
        self.assertEqual(res["rows"]["SC-8"]["status"], "SIGNED")

    def test_pre_fill_without_signature_is_pending(self):
        rows = [f"| SC-{i} | | | | "
                f"{'RATIFICATION-PENDING — decision pre-filled: X' if i == 8 else ''} |"
                for i in range(1, 13)]
        res = vsg.verify_grants(artifact_text(rows))
        self.assertFalse(res["ok"])
        self.assertEqual(res["rows"]["SC-8"]["status"], "PENDING")
        self.assertIn("not yet ratified", res["rows"]["SC-8"]["reason"])

    def test_prose_date_refuses(self):
        rows = [signed_row(f"SC-{i}") for i in range(1, 13)]
        rows[4] = ("| SC-5 | Owner Name | signed on the 29th of September "
                   "| runbook | |")
        res = vsg.verify_grants(artifact_text(rows))
        self.assertEqual(res["rows"]["SC-5"]["status"], "UNSIGNED")
        self.assertIn("YYYY-MM-DD", res["rows"]["SC-5"]["reason"])

    def test_missing_evidence_refuses(self):
        rows = [signed_row(f"SC-{i}") for i in range(1, 13)]
        rows[9] = "| SC-10 | Owner Name | 2026-09-29 | | |"
        res = vsg.verify_grants(artifact_text(rows))
        self.assertFalse(res["ok"])
        self.assertEqual(res["rows"]["SC-10"]["status"], "UNSIGNED")
        self.assertIn("evidence", res["rows"]["SC-10"]["reason"])

    def test_absent_row_is_unsigned_finding(self):
        ids = ["SC-1", "SC-2", "SC-3", "SC-4", "SC-5", "SC-6", "SC-7",
               "SC-8", "SC-9", "SC-10", "SC-12", "SC-12"]
        rows = [signed_row(i) for i in ids]
        rows[11] = "| SC-12 | Owner Name | 2026-11-11 | ev | |"
        res = vsg.verify_grants(artifact_text(rows))
        self.assertFalse(res["ok"])
        self.assertTrue(any(f["id"] == "SC-11" and f["status"] == "UNSIGNED"
                            for f in res["findings"]))


class CommittedArtifact(unittest.TestCase):
    def test_committed_artifact_is_honestly_unsigned(self):
        self.assertTrue(ARTIFACT.exists())
        res = vsg.verify_grants(ARTIFACT.read_text(encoding="utf-8"))
        self.assertFalse(res["ok"])
        self.assertEqual(res["verdict"], "NOT_AUTHORIZED")
        self.assertEqual(res["signed_count"], 0)
        self.assertEqual({f["id"] for f in res["findings"]},
                         {f"SC-{i}" for i in range(1, 13)})
        pending = {rid for rid, row in res["rows"].items()
                   if row["status"] == "PENDING"}
        self.assertEqual(pending, {"SC-7", "SC-8", "SC-9", "SC-11", "SC-12"})

    def test_cli_exit_0_on_fully_signed_artifact(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "signed.md"
            path.write_text(SIGNED_ALL, encoding="utf-8")
            rc = subprocess.run(
                [sys.executable, str(SCRIPT), "--artifact", str(path)],
                capture_output=True, text=True)
        self.assertEqual(rc.returncode, 0)
        self.assertIn("AUTHORIZED", rc.stdout)

    def test_cli_exit_1_on_committed_artifact(self):
        rc = subprocess.run([sys.executable, str(SCRIPT)],
                            capture_output=True, text=True)
        self.assertEqual(rc.returncode, 1)
        self.assertIn("NOT READY", rc.stdout)

    def test_cli_exit_2_on_missing_artifact(self):
        rc = subprocess.run(
            [sys.executable, str(SCRIPT),
             "--artifact", "/nonexistent/stage-c-grants.md"],
            capture_output=True, text=True)
        self.assertEqual(rc.returncode, 2)

    def test_output_redaction_shape(self):
        res = vsg.verify_grants(ARTIFACT.read_text(encoding="utf-8"))
        blob = str(res)
        self.assertNotIn("sk-", blob)
        self.assertNotIn("AKIA", blob)
        self.assertNotIn("BEGIN PRIVATE", blob)


if __name__ == "__main__":
    unittest.main()

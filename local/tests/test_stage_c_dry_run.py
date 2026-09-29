"""Stage C dry-run harness battery (offline, zero mutation).

Pins the G1–G6 simulated clearance of `local/scripts/stage_c_dry_run.py`:

  - HONEST DEFAULT  — over the COMMITTED artifacts (unsigned grants +
    placeholder template) the verdict is CANNOT_CLEAR with exit 1; the
    failing checks are exactly the grant-dependent gates (G1, G2, G4).
  - FAIL-CLOSED     — an unreadable artifact exits 2; a template with a
    real secret value, a routable URL while SC-5 is unsigned, an AI_*
    key (G-B4), an uncommented BACKUP_* key without SC-6/SC-7, or a
    mutated manifest (extra published port / non-internal data network /
    renamed volume) all refuse.
  - TWO-SIDED GATES — with a fully signed fixture (and a template whose
    SC-5 URLs and BACKUP_* block are filled), the verdict is CLEAR with
    exit 0.
  - D-045           — reports carry no secret values; the six
    DEPLOY-SECRET keys must be exact <GENERATE_SECURE_PASSWORD>
    placeholders.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "local" / "scripts"))

import stage_c_dry_run as dr  # noqa: E402
import verify_stage_c_grants as vsg  # noqa: E402

TEMPLATE = REPO / ".env.staging.template"
MANIFEST = REPO / "local" / "infra" / "compose.staging.yml"
GRANTS = REPO / "docs" / "deployment" / "stage-c-owner-grants.md"
SCRIPT = REPO / "local" / "scripts" / "stage_c_dry_run.py"

SIG_HEADER = "| # | Granted by (name) | Date | Evidence reference | Notes |\n"
SIG_SEPARATOR = "|---|-------------------|------|--------------------|-------|\n"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def signed_grants_text() -> str:
    rows = "\n".join(
        f"| SC-{i} | Owner Name | 2026-09-29 | installer v2.19.0 evidence-{i} | |"
        for i in range(1, 13))
    return ("\n## 3. Signature block\n\n" + SIG_HEADER + SIG_SEPARATOR
            + rows + "\n\n## 4. Gate exit criteria\n")


def filled_template_text() -> str:
    return (_read(TEMPLATE)
            .replace("http://staging-wordpress-placeholder.invalid",
                     "https://staging.example-granted-host.com")
            + ("BACKUP_S3_ENDPOINT=<SET-AFTER-GRANT:SC-7>\n"
               "BACKUP_S3_BUCKET=<SET-AFTER-GRANT:SC-7>\n"
               "BACKUP_CREDENTIAL_REF=unset-staging-backup-credentials\n"))


def report_of(tmp: Path, tpl: str, man: str, grants: str) -> dict:
    (tmp / "t.env").write_text(tpl, encoding="utf-8")
    (tmp / "m.yml").write_text(man, encoding="utf-8")
    (tmp / "g.md").write_text(grants, encoding="utf-8")
    return dr.verify(_read(tmp / "t.env"), _read(tmp / "m.yml"),
                     _read(tmp / "g.md"))


class CommittedArtifacts(unittest.TestCase):
    def test_committed_state_is_honestly_cannot_clear(self):
        res = dr.verify(_read(TEMPLATE), _read(MANIFEST), _read(GRANTS))
        self.assertFalse(res["ok"])
        self.assertEqual(res["verdict"], "CANNOT_CLEAR")
        failed = {c["gate"] for c in res["checks"] if c["verdict"] == "FAIL"}
        self.assertEqual(failed, {"G1", "G2", "G4"})
        # G3/VOL/ENV must all pass on the committed manifest+template —
        # the harness validates the Stage B artifacts as-shipped
        for gate in ("G3", "VOL", "ENV", "G5", "G6"):
            self.assertEqual(res["gates"][gate]["verdict"], "PASS")

    def test_g6_consistent_while_unsigned(self):
        res = dr.verify(_read(TEMPLATE), _read(MANIFEST), _read(GRANTS))
        g6 = [c for c in res["checks"] if c["gate"] == "G6"]
        self.assertTrue(all(c["verdict"] == "PASS" for c in g6))
        self.assertIn("stays commented", g6[0]["detail"])

    def test_g5_placeholder_rule_holds_while_unsigned(self):
        res = dr.verify(_read(TEMPLATE), _read(MANIFEST), _read(GRANTS))
        g5 = [c for c in res["checks"] if c["gate"] == "G5"]
        self.assertTrue(all(c["verdict"] == "PASS" for c in g5))


class FullySignedPath(unittest.TestCase):
    def test_signed_fixture_clears(self):
        with tempfile.TemporaryDirectory() as td:
            res = report_of(Path(td), filled_template_text(),
                            _read(MANIFEST), signed_grants_text())
        self.assertTrue(res["ok"])
        self.assertEqual(res["verdict"], "CLEAR")
        self.assertEqual(res["summary"]["checks_failed"], 0)
        self.assertIn("SC-5", vsg.verify_grants(signed_grants_text())["rows"])

    def test_signed_but_placeholder_urls_still_refuse(self):
        with tempfile.TemporaryDirectory() as td:
            res = report_of(Path(td), _read(TEMPLATE),
                            _read(MANIFEST), signed_grants_text())
        self.assertFalse(res["ok"])
        g5 = [c for c in res["checks"] if c["gate"] == "G5"]
        self.assertTrue(any(c["verdict"] == "FAIL" for c in g5))


class TamperedArtifacts(unittest.TestCase):
    def test_real_secret_value_refuses(self):
        bad = _read(TEMPLATE).replace(
            "CANONICAL_DB_PASSWORD=<GENERATE_SECURE_PASSWORD>",
            "CANONICAL_DB_PASSWORD=hunter2-real-password")
        with tempfile.TemporaryDirectory() as td:
            res = report_of(Path(td), bad, _read(MANIFEST), _read(GRANTS))
        self.assertFalse(res["ok"])
        env_fail = [c for c in res["checks"]
                    if c["name"].startswith("DEPLOY-SECRET")]
        self.assertTrue(env_fail and env_fail[0]["verdict"] == "FAIL")

    def test_secret_shaped_value_refuses(self):
        bad = _read(TEMPLATE).replace(
            "MINIO_ROOT_PASSWORD=<GENERATE_SECURE_PASSWORD>",
            "MINIO_ROOT_PASSWORD=" + "a1b2" * 16)
        with tempfile.TemporaryDirectory() as td:
            res = report_of(Path(td), bad, _read(MANIFEST), _read(GRANTS))
        self.assertFalse(res["ok"])
        leak = [c for c in res["checks"] if "secret-shaped" in c["name"]]
        self.assertTrue(leak and leak[0]["verdict"] == "FAIL")

    def test_ai_key_refuses_gb4(self):
        bad = _read(TEMPLATE) + "AI_CREDENTIAL_REF=some-ref\n"
        with tempfile.TemporaryDirectory() as td:
            res = report_of(Path(td), bad, _read(MANIFEST), _read(GRANTS))
        self.assertFalse(res["ok"])
        gb4 = [c for c in res["checks"] if "AI_*" in c["name"]]
        self.assertTrue(gb4 and gb4[0]["verdict"] == "FAIL")

    def test_uncommented_backup_refuses_without_grant(self):
        bad = _read(TEMPLATE) + "BACKUP_S3_BUCKET=early-bucket\n"
        with tempfile.TemporaryDirectory() as td:
            res = report_of(Path(td), bad, _read(MANIFEST), _read(GRANTS))
        self.assertFalse(res["ok"])
        self.assertTrue(any("BACKUP_" in c["detail"]
                            for c in res["checks"]))

    def test_backup_allowed_once_sc6_sc7_signed(self):
        tpl = filled_template_text()
        with tempfile.TemporaryDirectory() as td:
            res = report_of(Path(td), tpl, _read(MANIFEST),
                            signed_grants_text())
        self.assertTrue(res["ok"])  # BACKUP_* admitted under the grant

    def test_extra_published_port_refuses(self):
        bad = _read(MANIFEST).replace(
            '      - "18080:80"',
            '      - "18080:80"\n      - "19000:9000"')
        with tempfile.TemporaryDirectory() as td:
            res = report_of(Path(td), _read(TEMPLATE), bad, _read(GRANTS))
        self.assertFalse(res["ok"])
        self.assertTrue(any("published port" in c["name"]
                            and c["verdict"] == "FAIL"
                            for c in res["checks"]))

    def test_non_internal_data_network_refuses(self):
        bad = _read(MANIFEST).replace("    internal: true\n", "")
        with tempfile.TemporaryDirectory() as td:
            res = report_of(Path(td), _read(TEMPLATE), bad, _read(GRANTS))
        self.assertFalse(res["ok"])
        self.assertTrue(any("internal" in c["name"]
                            and c["verdict"] == "FAIL"
                            for c in res["checks"]))

    def test_renamed_volume_refuses(self):
        bad = _read(MANIFEST).replace("  canonical_data: {}",
                                      "  canonical_data2: {}")
        with tempfile.TemporaryDirectory() as td:
            res = report_of(Path(td), _read(TEMPLATE), bad, _read(GRANTS))
        self.assertFalse(res["ok"])
        self.assertTrue(any(c["gate"] == "VOL" and c["verdict"] == "FAIL"
                            for c in res["checks"]))


class CliContract(unittest.TestCase):
    def test_exit_1_on_committed_state(self):
        r = subprocess.run([sys.executable, str(SCRIPT)],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("CANNOT_CLEAR", r.stdout)

    def test_exit_0_on_signed_fixture(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            (td / "t.env").write_text(filled_template_text(), encoding="utf-8")
            (td / "g.md").write_text(signed_grants_text(), encoding="utf-8")
            r = subprocess.run(
                [sys.executable, str(SCRIPT),
                 "--env", str(td / "t.env"),
                 "--grants-artifact", str(td / "g.md")],
                capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        self.assertIn("CLEAR", r.stdout)

    def test_exit_2_on_missing_artifact(self):
        r = subprocess.run(
            [sys.executable, str(SCRIPT), "--manifest", "/nonexistent/m.yml"],
            capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)

    def test_json_schema_shape(self):
        r = subprocess.run([sys.executable, str(SCRIPT), "--json"],
                           capture_output=True, text=True)
        payload = json.loads(r.stdout)
        self.assertEqual(payload["schema_version"],
                         "stage_c.dry_run_clearance.v1")
        self.assertEqual(payload["compatible_with"],
                         "qa.launch_attestation.v1")
        for probe in payload["checks"]:
            self.assertIn(probe["verdict"], ("PASS", "FAIL"))
            for field in ("gate", "name", "verdict", "detail"):
                self.assertIn(field, probe)

    def test_reports_carry_no_secret_values(self):
        res = dr.verify(_read(TEMPLATE), _read(MANIFEST), _read(GRANTS))
        blob = json.dumps(res)
        self.assertNotIn("hunter2", blob)
        self.assertNotIn("AKIA", blob)
        self.assertNotIn("BEGIN PRIVATE", blob)
        self.assertNotIn("sk-live", blob)


if __name__ == "__main__":
    unittest.main()

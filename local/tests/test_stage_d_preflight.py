"""Stage D pre-flight battery (offline, parse-only).

Pins `local/scripts/stage_d_preflight.py` — the Stage D preparation
gate over the D-144 compose contract (Dokploy plan §37/§55):

  - the committed canonical template AND the canonical rendered
    manifest both verify HOLDS (7/7 checks);
  - every refusal class fails closed with a named finding: a missing
    D-144 service, a non-internal `backend`, a published port on a
    data service, a second `edge` attach, a healthcheck losing its
    probe-parity token, a loose `$VAR`/`${VAR}` credential form, a
    missing strict reference contract, and a volume-census drift;
  - multiple violations accumulate (fail-closed, never first-only);
  - a structurally unusable surface is CANNOT-ASSESS (exit 2 class);
  - the CLI emits `stage_d.verdict.v1` JSON and honors 0/1/2;
  - zero-leak (D-124) and AST purity (no subprocess/socket/urllib/os
    imports — the verifier is a pure parser).
"""
from __future__ import annotations

import ast as _ast
import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "local" / "scripts"))

import stage_d_preflight as pf  # noqa: E402

SCRIPT = REPO / "local" / "scripts" / "stage_d_preflight.py"
TEMPLATE_TEXT = pf.TEMPLATE.read_text(encoding="utf-8")


def _verify_template(text: str) -> dict:
    return pf.verify("template", text)


class CommittedSurfacesHold(unittest.TestCase):
    def test_template_mode_holds(self):
        rep = pf.verify("template", TEMPLATE_TEXT)
        self.assertTrue(rep["ok"])
        self.assertEqual(rep["verdict"], "HOLDS")
        self.assertEqual([c["name"] for c in rep["checks"]],
                         ["D1_service_census", "D2_backend_internal",
                          "D3_zero_published_ports", "D4_edge_exclusivity",
                          "D5_probe_parity", "D6_strict_credential_refs",
                          "D7_named_volumes"])
        self.assertEqual(rep["failing"], [])

    def test_canonical_rendered_manifest_holds(self):
        rep = pf.verify("manifest",
                        pf.DEFAULT_MANIFEST.read_text(encoding="utf-8"))
        self.assertTrue(rep["ok"])
        self.assertEqual(rep["verdict"], "HOLDS")

    def test_verify_is_deterministic(self):
        a = pf.verify("template", TEMPLATE_TEXT)
        b = pf.verify("template", TEMPLATE_TEXT)
        self.assertEqual(json.dumps(a, sort_keys=True),
                         json.dumps(b, sort_keys=True))


class RefusalClasses(unittest.TestCase):
    def _lines(self) -> list:
        return TEMPLATE_TEXT.splitlines()

    def test_missing_service_fails_census(self):
        lines = self._lines()
        i = next(i for i, l in enumerate(lines)
                 if l.strip() == "app-orchestrator:")
        j = next(i for i, l in enumerate(lines)
                 if l.strip() == "telemetry-circuit:")
        rep = _verify_template("\n".join(lines[:i] + lines[j:]) + "\n")
        self.assertFalse(rep["ok"])
        self.assertIn("D1_service_census", rep["failing"])
        self.assertIn("app-orchestrator", rep["checks"][0]["detail"])

    def test_non_internal_backend_fails(self):
        rep = _verify_template(
            TEMPLATE_TEXT.replace("    internal: true\n", ""))
        self.assertIn("D2_backend_internal", rep["failing"])

    def test_published_port_on_data_service_fails(self):
        lines = self._lines()
        i = next(i for i, l in enumerate(lines)
                 if l.strip() == "postgres-ssot:")
        lines.insert(i + 1, '    ports:')
        lines.insert(i + 2, '      - "5432:5432"')
        rep = _verify_template("\n".join(lines) + "\n")
        self.assertIn("D3_zero_published_ports", rep["failing"])
        self.assertIn("postgres-ssot", rep["checks"][2]["detail"])

    def test_second_edge_attach_fails_exclusivity(self):
        lines = self._lines()
        i = next(i for i, l in enumerate(lines)
                 if l.strip() == "telemetry-circuit:")
        j = next(j for j in range(i, len(lines))
                 if lines[j].strip() == "networks:")
        lines.insert(j + 2, "      - edge")
        rep = _verify_template("\n".join(lines) + "\n")
        self.assertIn("D4_edge_exclusivity", rep["failing"])
        self.assertIn("telemetry-circuit", rep["checks"][3]["detail"])

    def test_healthcheck_losing_probe_token_fails_parity(self):
        rep = _verify_template(TEMPLATE_TEXT.replace("pg_isready",
                                                     "pg_fakecheck"))
        self.assertIn("D5_probe_parity", rep["failing"])
        self.assertIn("postgres-ssot", rep["checks"][4]["detail"])

    def test_loose_credential_form_fails(self):
        rep = _verify_template(TEMPLATE_TEXT.replace(
            "${CANONICAL_DB_NAME:?Stage D required — canonical SSOT "
            "database name}",
            "${CANONICAL_DB_NAME}", 1))
        self.assertIn("D6_strict_credential_refs", rep["failing"])
        self.assertIn("CANONICAL_DB_NAME", rep["checks"][5]["detail"])

    def test_no_strict_refs_at_all_fails(self):
        import re as _re
        stripped = _re.sub(r"\$\{[A-Z_][A-Z0-9_]*:\?[^}]*\}",
                           "REDACTED", TEMPLATE_TEXT)
        rep = _verify_template(stripped)
        self.assertIn("D6_strict_credential_refs", rep["failing"])

    def test_volume_census_drift_fails(self):
        rep = _verify_template(
            TEMPLATE_TEXT.replace("  redis_data: {}\n", ""))
        self.assertIn("D7_named_volumes", rep["failing"])

    def test_multiple_violations_accumulate(self):
        text = TEMPLATE_TEXT.replace("    internal: true\n", "") \
            .replace("pg_isready", "pg_fakecheck") \
            .replace("  redis_data: {}\n", "")
        rep = _verify_template(text)
        self.assertFalse(rep["ok"])
        self.assertGreaterEqual(len(rep["failing"]), 3)
        self.assertIn("D2_backend_internal", rep["failing"])
        self.assertIn("D5_probe_parity", rep["failing"])
        self.assertIn("D7_named_volumes", rep["failing"])


class CannotAssess(unittest.TestCase):
    def test_serviceless_surface_raises(self):
        with self.assertRaises(pf.StageDPreflightError):
            pf.verify("manifest", "# nothing here\n")

    def test_unreadable_surface_raises(self):
        with self.assertRaises(pf.StageDPreflightError):
            pf._surface_text("manifest", Path("/nonexistent/manifest.yml"))

    def test_cli_garbage_manifest_rc2(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            bad = Path(td) / "m.yml"
            bad.write_text("# nothing here\n", encoding="utf-8")
            r = subprocess.run(
                [sys.executable, str(SCRIPT), "--mode", "manifest",
                 "--manifest", str(bad)],
                capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn("no services parsed", r.stdout + r.stderr)


class CliContract(unittest.TestCase):
    def _run(self, *argv: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(SCRIPT), *argv],
                              capture_output=True, text=True)

    def test_template_mode_rc0_holds(self):
        r = self._run("--mode", "template")
        self.assertEqual(r.returncode, 0)
        self.assertIn("HOLDS", r.stdout)

    def test_manifest_mode_rc0_holds(self):
        r = self._run("--mode", "manifest")
        self.assertEqual(r.returncode, 0)
        self.assertIn("HOLDS", r.stdout)

    def test_json_payload_schema(self):
        r = self._run("--mode", "template", "--json")
        self.assertEqual(r.returncode, 0)
        payload = json.loads(r.stdout)
        self.assertEqual(payload["schema_version"], "stage_d.verdict.v1")
        self.assertEqual(payload["compatible_with"],
                         "qa.launch_attestation.v1")
        self.assertEqual(payload["mode"], "template")
        self.assertTrue(payload["ok"])
        self.assertEqual(len(payload["checks"]), 7)


class ZeroLeakAndPurity(unittest.TestCase):
    def test_reports_carry_no_secret_material(self):
        rep = pf.verify("template", TEMPLATE_TEXT)
        blob = json.dumps(rep)
        for frag in ("sk-", "BEGIN PRIVATE", "postgres://", "redis://:",
                     "AKIA", "ghp_"):
            self.assertNotIn(frag, blob)

    def test_verifier_is_ast_pure(self):
        tree = _ast.parse(SCRIPT.read_text(encoding="utf-8"))
        imported = set()
        for node in _ast.walk(tree):
            if isinstance(node, _ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, _ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        for forbidden in ("subprocess", "socket", "urllib", "http",
                          "requests", "os"):
            self.assertNotIn(forbidden, imported)


if __name__ == "__main__":
    unittest.main()

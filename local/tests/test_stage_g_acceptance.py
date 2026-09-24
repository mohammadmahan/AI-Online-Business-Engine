"""Stage G acceptance executor battery (D-149, offline).

Exercises `local/scripts/run_stage_g_acceptance.py` against the REAL
committed Stage D artifacts with INJECTED providers (no sockets, no
subprocess, no files in the core):

  ENTRY GATE   — PREFLIGHT_CLEARED required; blocked/absent/mismatched
                 pre-flight aborts before any ACC check;
  ACC-01..03   — structure/isolation/parity, env schema, hardening
                 baseline — green on the shipped manifest, each
                 tamper class refused;
  ACC-04       — canonical report artifact + deterministic SHA-256
                 acceptance fingerprint;
  REDACTION    — no canary/credential material in reports or audit
                 copies (D-124);
  AST AUDIT    — zero unmanaged sockets/subprocess in the core.
"""
from __future__ import annotations

import ast
import json
import pathlib
import sys
import unittest

REPO = pathlib.Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "local" / "scripts"
SRC = REPO / "local" / "src"
for p in (str(SCRIPTS), str(SRC), str(REPO / "local"),
          str(REPO / "local" / "canonical")):
    if p not in sys.path:
        sys.path.insert(0, p)

from run_stage_g_acceptance import (  # noqa: E402
    ACCEPTED, REPORT_SCHEMA, REJECTED, StageGAcceptanceRunner,
    manifest_hash_of,
)
from stage_g_preflight_validator import (  # noqa: E402
    PREFLIGHT_BLOCKED, PREFLIGHT_CLEARED, bundle_hash_of,
)

EXECUTOR = SCRIPTS / "run_stage_g_acceptance.py"
MANIFEST = (REPO / "local" / "infra" / "dokploy" /
            "docker-compose.dokploy.yaml").read_text(encoding="utf-8")
TEMPLATE = (REPO / "local" / "infra" / "dokploy" /
            "dokploy_compose_template.yaml").read_text(encoding="utf-8")
CANARY = "sk-canaryvalue1234567890abcdef"


def make_bundle(hash_it: bool = True) -> dict:
    b = {"schema": "cutover.bundle.v1", "verdict": "READY_FOR_CUTOVER",
         "candidate_manifest_sha256": "7" * 64,
         "session_id": "cutover-session-01", "target_env": "staging",
         "observed_tick": 100,
         "steps": [{"step": "stage_c", "ok": True,
                    "detail": "host ready",
                    "findings": ["stage_c:PASS"]}],
         "stage_f_token_id": "af99db52fa4cc55e", "abort_reason": ""}
    if hash_it:
        b["bundle_hash"] = bundle_hash_of(b)
    return b


class Harness:
    def __init__(self, manifest: str = MANIFEST, template: str = TEMPLATE,
                 preflight: str = PREFLIGHT_CLEARED,
                 bundle: dict = None) -> None:
        self.reports: list = []
        self.bundle = bundle
        b = bundle or {}
        self.runner = StageGAcceptanceRunner(
            clock=lambda: 200, audit_sink=self.reports.append,
            preflight_verdict=lambda: {
                "verdict": preflight,
                "bundle_sha256": b.get("bundle_hash", "") if b else ""},
            manifest_provider=lambda: manifest,
            template_provider=lambda: template,
            bundle_provider=(lambda: b) if bundle is not None else None)


class TestEntryGate(unittest.TestCase):

    def test_01_blocked_preflight_aborts_immediately(self):
        r = Harness(preflight=PREFLIGHT_BLOCKED).runner.run()
        self.assertEqual(r.verdict, REJECTED)
        self.assertEqual(len(r.checks), 1)
        self.assertEqual(r.checks[0][0], "PREFLIGHT")
        self.assertIn("not authorized", r.checks[0][2])

    def test_02_absent_preflight_aborts(self):
        for bad in (None, {}, {"verdict": "garbage"}):
            r = Harness(preflight=bad).runner.run() if bad is not None \
                else Harness(preflight={"verdict": None}).runner.run()
            self.assertEqual(r.verdict, REJECTED)

    def test_03_preflight_provider_exception_aborts(self):
        def boom():
            raise RuntimeError("verdict file unreadable")
        r = Harness().runner.__class__(
            clock=lambda: 0, audit_sink=lambda d: None,
            preflight_verdict=boom,
            manifest_provider=lambda: MANIFEST,
            template_provider=lambda: TEMPLATE).run()
        self.assertEqual(r.verdict, REJECTED)
        self.assertIn("unavailable", r.checks[0][2])

    def test_04_bundle_mismatch_at_gate_refused(self):
        other = make_bundle()
        # the pre-flight cleared a DIFFERENT bundle hash than the one
        # presented — the executor must refuse the binding
        h = Harness(bundle=other)
        h.runner = StageGAcceptanceRunner(
            clock=lambda: 200, audit_sink=h.reports.append,
            preflight_verdict=lambda: {
                "verdict": PREFLIGHT_CLEARED,
                "bundle_sha256": "e" * 64},
            manifest_provider=lambda: MANIFEST,
            template_provider=lambda: TEMPLATE,
            bundle_provider=lambda: other)
        r = h.runner.run()
        self.assertEqual(r.verdict, REJECTED)
        self.assertIn("BUNDLE", [c[0] for c in r.checks])


class TestAccChecks(unittest.TestCase):

    def test_05_shipped_manifest_accepts(self):
        r = Harness().runner.run()
        self.assertEqual(r.verdict, ACCEPTED, r.checks)
        self.assertEqual([c[0] for c in r.checks],
                         ["ACC-01", "ACC-02", "ACC-03", "ACC-04"])

    def test_06_backend_port_publication_refused(self):
        bad = MANIFEST.replace(
            "    restart: unless-stopped\n    security_opt:",
            "    ports:\n      - \"5432:5432\"\n"
            "    restart: unless-stopped\n    security_opt:", 1)
        r = Harness(manifest=bad).runner.run()
        self.assertEqual(r.verdict, REJECTED)
        acc01 = next(c[2] for c in r.checks if c[0] == "ACC-01")
        self.assertIn("postgres-ssot declares ports", acc01)

    def test_07_loose_var_form_refused(self):
        bad = MANIFEST.replace("${CANONICAL_DB_NAME:?",
                               "$CANONICAL_DB_NAME:?", 1)
        r = Harness(manifest=bad).runner.run()
        self.assertEqual(r.verdict, REJECTED)
        acc01 = next(c[2] for c in r.checks if c[0] == "ACC-01")
        self.assertIn("non-strict variable form", acc01)

    def test_08_unknown_env_reference_refused(self):
        bad = MANIFEST.replace("${CANONICAL_DB_NAME:?",
                               "${MYSTERY_VAR:?", 1)
        r = Harness(manifest=bad).runner.run()
        self.assertEqual(r.verdict, REJECTED)
        acc02 = next(c[2] for c in r.checks if c[0] == "ACC-02")
        self.assertIn("MYSTERY_VAR", acc02)

    def test_09_secret_shaped_literal_refused(self):
        bad = MANIFEST.replace(
            "TZ: Asia/Tehran",
            "TZ: Asia/Tehran\n      API_KEY: \"" + CANARY + "\"", 1)
        r = Harness(manifest=bad).runner.run()
        self.assertEqual(r.verdict, REJECTED)
        acc02 = next(c[2] for c in r.checks if c[0] == "ACC-02")
        self.assertIn("secret-shaped literal", acc02)

    def test_10_missing_ceilings_refused(self):
        bad = MANIFEST.replace("    mem_limit: 512m\n    cpus: 1.0\n",
                               "", 1)
        r = Harness(manifest=bad).runner.run()
        self.assertEqual(r.verdict, REJECTED)
        acc03 = next(c[2] for c in r.checks if c[0] == "ACC-03")
        self.assertIn("postgres-ssot missing resource ceilings", acc03)

    def test_11_lost_read_only_rootfs_refused(self):
        bad = MANIFEST.replace(
            "    tmpfs:\n      - /tmp\n      - /var/run/postgresql\n"
            "    read_only: true\n", "", 1)
        r = Harness(manifest=bad).runner.run()
        self.assertEqual(r.verdict, REJECTED)
        acc03 = next(c[2] for c in r.checks if c[0] == "ACC-03")
        self.assertIn("read-only rootfs", acc03)

    def test_12_host_bind_mount_refused(self):
        bad = MANIFEST.replace(
            "      - canonical_data:/var/lib/postgresql/data",
            "      - /host/secrets:/var/lib/postgresql/data", 1)
        r = Harness(manifest=bad).runner.run()
        self.assertEqual(r.verdict, REJECTED)
        acc03 = next(c[2] for c in r.checks if c[0] == "ACC-03")
        self.assertIn("non-declared volume", acc03)

    def test_13_template_drift_refused(self):
        # rename a template service: the manifest no longer contains
        # that service, so the template-binding comparison fails
        bad = TEMPLATE.replace("  telemetry-circuit:",
                               "  telemetry-circuit-renamed:", 1)
        r = Harness(template=bad).runner.run()
        self.assertEqual(r.verdict, REJECTED)
        acc01 = next(c[2] for c in r.checks if c[0] == "ACC-01")
        self.assertIn("drifted from bound template", acc01)

    def test_14_edge_dependency_cycle_refused(self):
        bad = MANIFEST.replace(
            "      REDIS_PASSWORD: ${REDIS_PASSWORD:?Stage D required — redis broker password (secret envelope injects the value)}\n",
            "      REDIS_PASSWORD: ${REDIS_PASSWORD:?Stage D required — redis broker password (secret envelope injects the value)}\n"
            "      APP_CALLBACK: ${APP_CALLBACK:?Stage D required — app callback}\n", 1)
        r = Harness(manifest=bad).runner.run()
        self.assertEqual(r.verdict, REJECTED)
        acc02 = next(c[2] for c in r.checks if c[0] == "ACC-02")
        self.assertIn("APP_CALLBACK", acc02)


class TestReportArtifact(unittest.TestCase):

    def test_15_fingerprint_deterministic_and_drift_sensitive(self):
        r1 = Harness().runner.run()
        r2 = Harness().runner.run()
        self.assertEqual(r1.acceptance_fingerprint,
                         r2.acceptance_fingerprint)
        r3 = Harness(manifest=MANIFEST + "\n# drift\n").runner.run()
        self.assertNotEqual(r1.acceptance_fingerprint,
                            r3.acceptance_fingerprint)

    def test_16_report_shape_and_hashes(self):
        r = Harness().runner.run()
        d = r.to_dict()
        self.assertEqual(set(d), {"schema", "verdict",
                                  "manifest_sha256", "template_sha256",
                                  "bundle_sha256", "checks",
                                  "observed_tick"})
        self.assertEqual(d["schema"], REPORT_SCHEMA)
        self.assertTrue(all(len(d[k]) == 64 for k in
                            ("manifest_sha256", "template_sha256")))

    def test_17_bundle_binding_recorded(self):
        b = make_bundle()
        r = Harness(bundle=b).runner.run()
        self.assertEqual(r.bundle_sha256, b["bundle_hash"])


class TestRedactionAndAst(unittest.TestCase):

    def test_18_no_material_in_reports_or_audit(self):
        h = Harness()
        r = h.runner.run()
        for blob in (json.dumps(r.to_dict()), json.dumps(h.reports)):
            self.assertNotIn(CANARY, blob)
            self.assertNotIn("password", blob.lower())
            self.assertNotIn("postgres://", blob)
        self.assertTrue(all(isinstance(x, dict) for x in h.reports))

    def test_19_ast_no_sockets_subprocess(self):
        tree = ast.parse(EXECUTOR.read_text(encoding="utf-8"))
        banned = {"socket", "subprocess", "ssl", "http", "urllib",
                  "requests", "ftplib"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    self.assertNotIn(a.name.split(".")[0], banned,
                                     f"banned import: {a.name}")
            elif isinstance(node, ast.ImportFrom):
                root = (node.module or "").split(".")[0]
                self.assertNotIn(root, banned,
                                 f"banned import-from: {node.module}")
            elif isinstance(node, ast.Call):
                fn = node.func
                if isinstance(fn, ast.Name) and fn.id == "open":
                    self.fail("direct open() in acceptance core")
                if isinstance(fn, ast.Attribute) and \
                        fn.attr in ("system", "popen", "connect"):
                    self.fail(f"banned call: .{fn.attr}()")

    def test_20_doc_covers_acc_rules_and_handoff(self):
        doc = (REPO / "docs" / "deployment" /
               "stage-g-acceptance-execution.md").read_text(
                   encoding="utf-8")
        for token in ("ACC-01", "ACC-02", "ACC-03", "ACC-04",
                      "PREFLIGHT_CLEARED", "acceptance fingerprint",
                      "D-139", "remediation"):
            self.assertIn(token, doc)


if __name__ == "__main__":
    unittest.main()

"""Stage E — cutover fingerprint-binding wire battery (D-145, offline).

Pins the V-08/V-09 rules `verify_cutover_readiness.py` enforces over
the Stage D artifacts (D-144), entirely offline and injected:

  V-08 BINDING   — VERIFY on matching bytes; MISMATCH on one-byte
                   tampering; NO_ENVELOPE / NO_MANIFEST / MALFORMED all
                   fail closed; isolation re-asserted on the bound bytes
                   (ports on backend, edge attachment, loose $VAR).
  V-09 PARITY    — every generated service healthcheck maps onto an
                   `infra_health_probe.py` semantic; a missing check or
                   off-contract command fails closed.
  CLI            — the real offline mode goes green on the committed
                   (manifest, envelope) pair and fails closed when the
                   manifest is tampered on disk.
  REDACTION      — canary values never reach reports (D-124): the
                   envelope carries hashes only.
  AST            — the cutover harness gains no new network imports in
                   its offline path (the opt-in --edge probe remains
                   the only networked surface).
"""
from __future__ import annotations

import ast
import os
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "local" / "scripts" / "verify_cutover_readiness.py"
MANIFEST = REPO / "local" / "infra" / "dokploy" / "docker-compose.dokploy.yaml"
ENVELOPE = REPO / "local" / "infra" / "dokploy" / "stage_d_fingerprint.envelope"
TEMPLATE = REPO / "local" / "infra" / "dokploy" / "dokploy_compose_template.yaml"
DOC = REPO / "docs" / "deployment" / "stage-e-cutover-fingerprint-binding.md"

sys.path.insert(0, str(SCRIPT.parent))
sys.path.insert(0, str(REPO / "local" / "infra" / "dokploy"))
import verify_cutover_readiness as vcr  # noqa: E402

CANARY = "sk-canaryvalue1234567890abcdef"


def run_cli(*extra: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), *extra],
                          capture_output=True, text=True,
                          cwd=str(REPO / "local"))


def committed_texts() -> tuple[str, str]:
    return (MANIFEST.read_text(encoding="utf-8"),
            ENVELOPE.read_text(encoding="utf-8"))


def envelope_with(hash_hex: str) -> str:
    return f"manifest_sha256: {hash_hex}\nbound_for: test\n"


class TestV08FingerprintBinding(unittest.TestCase):
    def test_01_committed_manifest_verifies_against_envelope(self):
        verdict, detail = vcr.manifest_fingerprint()
        self.assertEqual(verdict, "VERIFY", detail)
        self.assertIn("matches envelope", detail)

    def test_02_deterministic_generation_reproduces_bound_bytes(self):
        """The generator is deterministic: re-rendering from the same
        template + pins must reproduce the exact bound hash."""
        import re as _re
        from stage_d_compose_generator import StageDComposeGenerator
        g = StageDComposeGenerator(template_text=TEMPLATE.read_text(encoding="utf-8"))
        slots = {"postgres-ssot": "POSTGRES_IMAGE", "redis": "REDIS_IMAGE",
                 "app-orchestrator": "APP_IMAGE",
                 "telemetry-circuit": "TELEMETRY_IMAGE"}
        man_text = MANIFEST.read_text(encoding="utf-8")
        imgs = {}
        for svc, slot in slots.items():
            block = man_text.split(f"  {svc}:\n", 1)[1]  # service header,
            # not the depends_on mapping (which has 6-space indentation)
            imgs[slot] = _re.search(r"image: (\S+)", block).group(1)
        self.assertEqual(len(imgs), 4)
        r = g.generate(imgs, {"CANONICAL_DB_NAME": "x", "CANONICAL_DB_USER": "x",
                              "CANONICAL_DB_PASSWORD": "x", "REDIS_PASSWORD": "x"})
        self.assertEqual(r.verdict, "RENDERED")
        self.assertEqual(vcr.sha256_text(r.manifest),
                         vcr.sha256_text(MANIFEST.read_text(encoding="utf-8")))

    def test_03_single_byte_tampering_is_a_mismatch(self):
        manifest, _ = committed_texts()
        tampered = manifest.replace("internal: true", "internal: false", 1)
        verdict, _ = vcr.manifest_fingerprint(tampered,
                                              envelope_with(vcr.sha256_text(manifest)))
        self.assertEqual(verdict, "MISMATCH")

    def test_04_missing_envelope_and_manifest_fail_closed(self):
        # the committed artifacts exist, so force the file-read branches
        # via patched paths to prove the fail-closed verdicts
        saved = (vcr.STAGE_D_MANIFEST, vcr.STAGE_D_ENVELOPE)
        try:
            vcr.STAGE_D_MANIFEST = Path("/nonexistent/manifest.yaml")
            self.assertEqual(vcr.manifest_fingerprint()[0], "NO_MANIFEST")
            vcr.STAGE_D_MANIFEST, _ = saved
            vcr.STAGE_D_ENVELOPE = Path("/nonexistent/envelope")
            self.assertEqual(vcr.manifest_fingerprint()[0], "NO_ENVELOPE")
        finally:
            vcr.STAGE_D_MANIFEST, vcr.STAGE_D_ENVELOPE = saved
        self.assertEqual(vcr.manifest_fingerprint(
            "m", "no hash row here")[0], "MALFORMED")

    def test_05_isolation_re_asserted_on_bound_bytes(self):
        ok, problems = vcr.manifest_isolation_ok()
        self.assertTrue(ok, problems)
        # a backend service gaining ports: is refused
        manifest, _ = committed_texts()
        bad = manifest.replace(
            "    volumes:\n      - canonical_data:/var/lib/postgresql/data",
            "    ports:\n      - \"5432:5432\"\n    volumes:\n"
            "      - canonical_data:/var/lib/postgresql/data", 1)
        ok, problems = vcr.manifest_isolation_ok(bad)
        self.assertFalse(ok)
        self.assertTrue(any("postgres-ssot" in p and "ports" in p
                            for p in problems))

    def test_06_loose_var_form_refused_at_cutover_layer(self):
        manifest, _ = committed_texts()
        bad = manifest.replace("${REDIS_PASSWORD:?", "$REDIS_PASSWORD:?", 1)
        ok, problems = vcr.manifest_isolation_ok(bad)
        self.assertFalse(ok)
        self.assertTrue(any("non-strict" in p for p in problems))


class TestV09ProbeParity(unittest.TestCase):
    def test_07_generated_manifest_passes_parity(self):
        ok, problems = vcr.manifest_probe_parity()
        self.assertTrue(ok, problems)

    def test_08_missing_healthcheck_fails_closed(self):
        manifest, _ = committed_texts()
        start = manifest.index("  postgres-ssot:")
        end = manifest.index("  redis:")
        block = manifest[start:end]
        stripped = "\n".join(l for l in block.splitlines()
                             if "healthcheck" not in l
                             and "pg_isready" not in l
                             and not l.strip().startswith(("test:", "interval:",
                                                           "timeout:", "retries:")))
        bad = manifest[:start] + stripped + "\n" + manifest[end:]
        ok, problems = vcr.manifest_probe_parity(bad)
        self.assertFalse(ok)
        self.assertTrue(any("postgres-ssot" in p and "no healthcheck" in p
                            for p in problems))

    def test_09_off_contract_check_fails_closed(self):
        manifest, _ = committed_texts()
        bad = manifest.replace("pg_isready", "pg_ready_madeup", 1)
        ok, problems = vcr.manifest_probe_parity(bad)
        self.assertFalse(ok)
        self.assertTrue(any("probe contract" in p for p in problems))


class TestCLIWiringAndRedaction(unittest.TestCase):
    def test_10_offline_mode_includes_v08_v09_pass(self):
        r = run_cli()
        self.assertIn("[PASS] V-08", r.stdout)
        self.assertIn("[PASS] V-09", r.stdout)
        self.assertIn("matches envelope", r.stdout)

    def test_11_tampered_manifest_on_disk_fails_closed(self):
        original = MANIFEST.read_bytes()
        try:
            MANIFEST.write_bytes(original + b"\n# drift\n")
            r = run_cli()
            self.assertEqual(r.returncode, 1)
            self.assertIn("[FAIL] V-08", r.stdout)
            self.assertIn("MISMATCH", r.stdout)
        finally:
            MANIFEST.write_bytes(original)

    def test_12_reports_never_contain_secret_shaped_values(self):
        manifest, envelope = committed_texts()
        # canary cannot be in the committed artifacts (hashes only), and
        # the report renders none of the manifest body anyway
        r = run_cli()
        self.assertNotIn(CANARY, r.stdout)
        self.assertNotIn(CANARY, r.stderr)
        self.assertNotIn(CANARY, manifest)
        self.assertNotIn(CANARY, envelope)
        self.assertNotIn("POSTGRES_PASSWORD", r.stdout.split("V-08")[-1])

    def test_13_envelope_carries_no_secret_material(self):
        env_text = ENVELOPE.read_text(encoding="utf-8")
        self.assertNotIn(CANARY, env_text)
        for banned in ("PASSWORD=", "password=", "sk-", "BEGIN"):
            self.assertNotIn(banned, env_text)


class TestASTBoundary(unittest.TestCase):
    def test_14_offline_path_gains_no_network_imports(self):
        tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
        top_imports = set()
        for node in tree.body:  # module level only — --edge keeps its
            if isinstance(node, ast.Import):  # local, opt-in imports
                top_imports.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                top_imports.add(node.module.split(".")[0])
        banned = {"socket", "ssl", "http", "urllib", "urllib3", "requests",
                  "ftplib", "smtplib", "paramiko", "asyncio"}
        self.assertEqual(top_imports & banned, set())

    def test_15_binding_doc_covers_full_matrix(self):
        doc = DOC.read_text(encoding="utf-8")
        for token in ("V-01", "V-09", "manifest_sha256", "MISMATCH",
                      "fail closed", "D-139"):
            self.assertIn(token, doc)


if __name__ == "__main__":
    unittest.main()

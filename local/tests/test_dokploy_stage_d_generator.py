"""Stage D — compose generator battery (D-144, offline/hermetic).

Exercises `local/infra/dokploy/stage_d_compose_generator.py` entirely
with an injected template + injected environment (zero sockets, zero
subprocess in the generator core, zero clock):

  DETERMINISM    — identical inputs render byte-identical manifests.
  ISOLATION      — backend services (postgres/redis/telemetry) refuse
                   ports: and edge attachment; the app is the sole edge
                   surface (F-2/F-3).
  STRICT REFS    — any non-`${VAR:?…}` variable form is a refusal (F-1);
                   the shipped template must itself satisfy the
                   contract it enforces.
  SECRETS        — missing required variables fail closed with MASKED
                   keys; values are never emitted to stdout, stderr,
                   reports, or rendered artifacts (D-124).
  AST AUDIT      — the generator imports no network/socket/process
                   module and never reads os.environ.
"""
from __future__ import annotations

import ast
import io
import json
import os
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
GENERATOR = REPO / "local" / "infra" / "dokploy" / "stage_d_compose_generator.py"
TEMPLATE = REPO / "local" / "infra" / "dokploy" / "dokploy_compose_template.yaml"
DOC = REPO / "docs" / "deployment" / "stage-d-compose-architecture.md"

sys.path.insert(0, str(GENERATOR.parent))
sys.path.insert(0, os.path.join(os.getcwd(), "local"))
sys.path.insert(0, os.getcwd())

import stage_d_compose_generator as gen  # noqa: E402

CANARY = "sk-canaryvalue1234567890abcdef"
DIGEST = "@sha256:" + "a" * 64

IMAGES_OK = {
    "POSTGRES_IMAGE": "postgres:16-alpine" + DIGEST,
    "REDIS_IMAGE": "redis:7-alpine" + DIGEST,
    "APP_IMAGE": "ghcr.io/org/app:1.0.0" + DIGEST,
    "TELEMETRY_IMAGE": "prom/prometheus:v2.0.0" + DIGEST,
}
ENV_OK = {
    "CANONICAL_DB_NAME": "engine_prod",
    "CANONICAL_DB_USER": "engine_prod",
    "CANONICAL_DB_PASSWORD": CANARY,      # value must NEVER leak
    "REDIS_PASSWORD": "redis-canary-98765",
}


def rendered(g: gen.StageDComposeGenerator, images=None, env=None):
    r = g.generate(images or IMAGES_OK, env or ENV_OK)
    return r


class StageDGeneratorBase(unittest.TestCase):
    def setUp(self):
        self.g = gen.StageDComposeGenerator(
            template_text=TEMPLATE.read_text(encoding="utf-8"))


class TestDeterministicGeneration(StageDGeneratorBase):
    def test_01_valid_config_renders_manifest(self):
        r = rendered(self.g)
        self.assertEqual(r.verdict, "RENDERED")
        self.assertIn("postgres-ssot:", r.manifest)
        self.assertIn("app-orchestrator:", r.manifest)
        self.assertIn("${CANONICAL_DB_PASSWORD:?", r.manifest)

    def test_02_byte_identical_output_for_identical_inputs(self):
        a = rendered(self.g).manifest
        b = rendered(self.g).manifest
        self.assertEqual(a, b)

    def test_03_fingerprint_binds_values_without_exposing_them(self):
        env = dict(ENV_OK)
        env["CANONICAL_DB_PASSWORD"] = "rotated-value-000"
        r1 = rendered(self.g)
        r2 = rendered(self.g, env=env)
        self.assertNotEqual(r1.env_fingerprint, r2.env_fingerprint)
        self.assertNotIn("rotated-value-000", r2.report())
        self.assertNotIn(CANARY, r2.report())

    def test_04_digest_pinning_enforced(self):
        loose = dict(IMAGES_OK)
        loose["APP_IMAGE"] = "ghcr.io/org/app:latest"
        r = rendered(self.g, images=loose)
        self.assertEqual(r.verdict, "RENDERED")  # warning, not refusal
        self.assertTrue(any(f.startswith("warning:") for f in r.findings))
        # missing slot is a hard failure
        missing = dict(IMAGES_OK)
        del missing["TELEMETRY_IMAGE"]
        r = rendered(self.g, images=missing)
        self.assertEqual(r.verdict, "CANNOT_GENERATE")
        self.assertIn("TELEMETRY_IMAGE", r.findings[0])


class TestIsolationContract(StageDGeneratorBase):
    def test_05_backend_services_declare_no_ports(self):
        r = rendered(self.g)
        self.assertEqual(r.verdict, "RENDERED")
        block = r.manifest.split("  postgres-ssot:")[1].split("  app-orchestrator:")[0]
        redis_block = r.manifest.split("  redis:")[1].split("  app-orchestrator:")[0]
        self.assertNotIn("ports:", block)
        self.assertNotIn("ports:", redis_block)

    def test_06_backend_services_never_attach_edge(self):
        g = gen.StageDComposeGenerator(template_text=
            TEMPLATE.read_text(encoding="utf-8").replace(
                "      - backend\n    restart: unless-stopped",
                "      - backend\n      - edge\n    restart: unless-stopped"))
        r = g.generate(IMAGES_OK, ENV_OK)
        self.assertEqual(r.verdict, "REFUSED")
        self.assertTrue(any("edge" in f for f in r.findings))

    def test_07_port_publication_on_backend_refused(self):
        g = gen.StageDComposeGenerator(template_text=
            TEMPLATE.read_text(encoding="utf-8").replace(
                "    networks:\n      - backend\n    restart: unless-stopped\n    security_opt:\n      - no-new-privileges:true\n    mem_limit: 512m\n    cpus: 1.0\n    healthcheck:\n      test: [\"CMD-SHELL\", \"pg_isready",
                "    ports:\n      - \"5432:5432\"\n    networks:\n      - backend\n    restart: unless-stopped\n    security_opt:\n      - no-new-privileges:true\n    mem_limit: 512m\n    cpus: 1.0\n    healthcheck:\n      test: [\"CMD-SHELL\", \"pg_isready"))
        r = g.generate(IMAGES_OK, ENV_OK)
        self.assertEqual(r.verdict, "REFUSED")

    def test_08_app_is_sole_edge_surface(self):
        r = rendered(self.g)
        edge_sections = [m.start() for m in
                         __import__("re").finditer(r"- edge", r.manifest)]
        self.assertEqual(len(edge_sections), 1)  # only app-orchestrator


class TestStrictSecretContract(StageDGeneratorBase):
    def test_09_template_itself_satisfies_strict_refs(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        loose = gen._LOOSE_SUB.findall(text)
        # `$$VAR` healthcheck escapes are legitimate compose syntax and
        # excluded by the pattern; anything else is a template defect.
        self.assertEqual(loose, [], f"loose variable forms in template: {loose}")
        self.assertIn("$$POSTGRES_USER", text)  # escape form survives

    def test_10_loose_ref_in_rendered_output_refused(self):
        g = gen.StageDComposeGenerator(template_text=
            TEMPLATE.read_text(encoding="utf-8").replace(
                "${REDIS_PASSWORD:?", "$REDIS_PASSWORD:?"))
        r = g.generate(IMAGES_OK, ENV_OK)
        self.assertEqual(r.verdict, "REFUSED")

    def test_11_missing_secrets_fail_closed_with_masked_keys(self):
        env = dict(ENV_OK)
        del env["CANONICAL_DB_PASSWORD"]
        env["REDIS_PASSWORD"] = "   "  # blank == missing
        buf_out, buf_err = io.StringIO(), io.StringIO()
        with redirect_stdout(buf_out), redirect_stderr(buf_err):
            rc = gen.main(["--images",
                           ",".join(f"{k}={v}" for k, v in IMAGES_OK.items()),
                           "--env",
                           ",".join(f"{k}={v}" for k, v in env.items()),
                           "--report"])
        self.assertEqual(rc, 2)
        report = buf_out.getvalue()
        self.assertIn("CANNOT_GENERATE", report)
        # keys are masked, values never present
        self.assertNotIn("CANONICAL_DB_PASSWORD", report)
        self.assertNotIn("REDIS_PASSWORD", report)
        self.assertNotIn(CANARY, report)
        self.assertNotIn("redis-canary-98765", report)


class TestCanaryRedaction(StageDGeneratorBase):
    def test_12_canary_never_reaches_stdout_stderr_or_artifact(self):
        buf_out, buf_err = io.StringIO(), io.StringIO()
        with redirect_stdout(buf_out), redirect_stderr(buf_err):
            rc = gen.main(["--images",
                           ",".join(f"{k}={v}" for k, v in IMAGES_OK.items()),
                           "--env",
                           ",".join(f"{k}={v}" for k, v in ENV_OK.items())])
        self.assertEqual(rc, 0)
        self.assertNotIn(CANARY, buf_out.getvalue())
        self.assertNotIn(CANARY, buf_err.getvalue())
        self.assertNotIn("redis-canary-98765", buf_out.getvalue())

    def test_13_secret_shaped_literal_in_value_is_refused_redacted(self):
        r = rendered(self.g)  # values flow through fingerprint only
        self.assertNotIn(CANARY, r.report())
        f = gen.deep_redact(f"boom: postgres://u:{CANARY}@h/db")
        self.assertNotIn(CANARY, f)
        self.assertIn("[REDACTED]", f)

    def test_14_report_fingerprint_is_the_only_value_trace(self):
        r = rendered(self.g)
        rep = json.loads(r.report())
        self.assertEqual(rep["verdict"], "RENDERED")
        self.assertNotIn("manifest", rep)  # body only on explicit request
        self.assertEqual(len(rep["env_fingerprint"]), 64)


class TestASTAndDocContract(StageDGeneratorBase):
    def test_15_no_network_or_process_imports_in_generator(self):
        tree = ast.parse(GENERATOR.read_text(encoding="utf-8"))
        banned = {"socket", "ssl", "http", "urllib", "urllib3", "requests",
                  "ftplib", "smtplib", "asyncio", "subprocess",
                  "multiprocessing", "paramiko", "docker"}
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imported.add(node.module.split(".")[0])
        self.assertEqual(imported & banned, set())

    def test_16_generator_never_touches_os_environ(self):
        # code-level check: no os.environ ACCESS (the docstring mention
        # of the design rule is not an access)
        tree = ast.parse(GENERATOR.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "environ":
                self.fail("generator accesses os.environ")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                    and node.func.attr in ("getenv", " environ"):
                self.fail("generator reads environment via getenv")

    def test_17_probe_parity_names_present_in_template(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        for token in ("pg_isready", "ping | grep -q PONG",
                      "/healthz/worker", "/-/healthy"):
            self.assertIn(token, text)
        for svc in ("postgres-ssot", "redis", "app-orchestrator",
                    "telemetry-circuit"):
            self.assertIn(f"  {svc}:", text)

    def test_18_architecture_doc_matches_generator_contract(self):
        doc = DOC.read_text(encoding="utf-8")
        for token in ("backend", "internal: true", "${VAR:?reason}",
                      "CANNOT_GENERATE", "stage_d_compose_generator.py"):
            self.assertIn(token, doc)


if __name__ == "__main__":
    unittest.main()

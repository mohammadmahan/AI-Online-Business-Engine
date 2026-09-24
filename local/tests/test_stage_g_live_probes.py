"""Stage G live probes battery (D-150, offline).

Exercises `local/scripts/verify_stage_g_live_probes.py` with INJECTED
executors (no sockets, no subprocess, no files in the core) and a REAL
D-149 acceptance report as the entry-gate material:

  GATE         — missing/invalid/REJECTED/tampered acceptance reports
                 abort before any probe executes;
  GA-1..GA-7   — healthy-stack acceptance plus each fail-closed path
                 (crash loop, SSOT down, broker exposed/unauthed, app
                 unresponsive, stale heartbeat, published port, log
                 leakage, unwired executor, transport exception);
  REDACTION    — canaries never reach reports or audit copies;
  AST AUDIT    — zero sockets/subprocess in the core.
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
for p in (str(SCRIPTS), str(SRC), str(REPO / "local")):
    if p not in sys.path:
        sys.path.insert(0, p)

from run_stage_g_acceptance import StageGAcceptanceRunner  # noqa: E402
from verify_stage_g_live_probes import (  # noqa: E402
    ACCEPTANCE_SCHEMA, HEARTBEAT_MAX_AGE, PROBES_ACCEPTED,
    PROBES_REJECTED, StageGLiveProbeRunner,
)

ENGINE = SCRIPTS / "verify_stage_g_live_probes.py"
MANIFEST = (REPO / "local" / "infra" / "dokploy" /
            "docker-compose.dokploy.yaml").read_text(encoding="utf-8")
TEMPLATE = (REPO / "local" / "infra" / "dokploy" /
            "dokploy_compose_template.yaml").read_text(encoding="utf-8")
CANARY = "sk-canaryvalue1234567890abcdef"
SERVICES = ("postgres-ssot", "redis", "app-orchestrator",
            "telemetry-circuit")


def healthy_executors(**overrides):
    base = {
        "container_status": lambda: {
            s: {"healthy": True, "restarts": 0} for s in SERVICES},
        "pg_roundtrip": lambda: True,
        "redis_ping": lambda: {"pong": True, "auth_required": True,
                               "ttl_ok": True, "exposed": False},
        "app_loopback": lambda: True,
        "worker_heartbeat": lambda: {"registered": True, "age": 5},
        "published_ports": lambda: {s: [] for s in SERVICES},
        "output_streams": lambda: {"stdout": "all good", "stderr": ""},
    }
    base.update(overrides)
    return base


class Harness:
    def __init__(self, executors: dict = None, acceptance: dict = None):
        self.reports: list = []
        self.runner = StageGLiveProbeRunner(
            clock=lambda: 300, audit_sink=self.reports.append,
            **(executors or healthy_executors()))
        self.acceptance = acceptance if acceptance is not None \
            else self.make_acceptance()

    @staticmethod
    def make_acceptance() -> dict:
        acc = StageGAcceptanceRunner(
            clock=lambda: 200, audit_sink=lambda d: None,
            preflight_verdict=lambda: {"verdict": "PREFLIGHT_CLEARED",
                                       "bundle_sha256": ""},
            manifest_provider=lambda: MANIFEST,
            template_provider=lambda: TEMPLATE).run()
        d = acc.to_dict()
        d["acceptance_fingerprint"] = acc.acceptance_fingerprint
        return d


class TestEntryGate(unittest.TestCase):

    def test_01_missing_or_malformed_acceptance_aborts(self):
        for bad in (None, {}, {"schema": "other"}, "not-a-dict"):
            r = Harness(acceptance=bad).runner.run(bad)
            self.assertEqual(r.verdict, PROBES_REJECTED)
            self.assertEqual(r.probes[0][0], "GATE")
            self.assertEqual(len(r.probes), 1)  # no probe executed

    def test_02_rejected_acceptance_aborts(self):
        acc = Harness.make_acceptance()
        acc["verdict"] = "REJECTED"
        r = Harness(acceptance=acc).runner.run(acc)
        self.assertEqual(r.verdict, PROBES_REJECTED)
        self.assertIn("never cleared", r.probes[0][2])

    def test_03_fingerprint_mismatch_aborts(self):
        acc = Harness.make_acceptance()
        r = Harness(acceptance=acc).runner.run(
            acc, expected_manifest="a" * 64)
        self.assertEqual(r.verdict, PROBES_REJECTED)
        self.assertIn("different deployment", r.probes[0][2])

    def test_04_tampered_acceptance_fingerprint_aborts(self):
        acc = Harness.make_acceptance()
        acc["verdict"] = "REJECTED"  # tamper AFTER fingerprinting
        acc["acceptance_fingerprint"] = acc["acceptance_fingerprint"]
        r = Harness(acceptance=acc).runner.run(acc)
        self.assertEqual(r.verdict, PROBES_REJECTED)
        gate = r.probes[0][2]
        self.assertTrue("TAMPERED" in gate or "never cleared" in gate)


class TestProbes(unittest.TestCase):

    def test_05_full_pass_on_healthy_stack(self):
        h = Harness()
        r = h.runner.run(h.acceptance,
                         expected_manifest=h.acceptance["manifest_sha256"])
        self.assertEqual(r.verdict, PROBES_ACCEPTED)
        self.assertEqual([p[0] for p in r.probes],
                         ["GA-1", "GA-2", "GA-3", "GA-4", "GA-5",
                          "GA-6", "GA-7"])

    def test_06_crash_loop_fails_ga1(self):
        ex = healthy_executors(
            container_status=lambda: {
                "postgres-ssot": {"healthy": True, "restarts": 9},
                "redis": {"healthy": True, "restarts": 0}})
        r = Harness(executors=ex).runner.run(Harness.make_acceptance())
        ga1 = next(p for p in r.probes if p[0] == "GA-1")
        self.assertFalse(ga1[1])
        self.assertIn("restart-loop", ga1[2])

    def test_07_ssot_down_fails_ga2(self):
        ex = healthy_executors(pg_roundtrip=lambda: False)
        r = Harness(executors=ex).runner.run(Harness.make_acceptance())
        self.assertEqual(r.verdict, PROBES_REJECTED)

    def test_08_transport_exception_fails_closed(self):
        def boom():
            raise TimeoutError("pg unreachable")
        ex = healthy_executors(pg_roundtrip=boom)
        r = Harness(executors=ex).runner.run(Harness.make_acceptance())
        ga2 = next(p for p in r.probes if p[0] == "GA-2")
        self.assertFalse(ga2[1])
        self.assertIn("transport failure: TimeoutError", ga2[2])
        self.assertNotIn("pg unreachable", ga2[2])  # payload never leaks

    def test_09_exposed_or_unauthed_broker_fails_ga3(self):
        ex = healthy_executors(
            redis_ping=lambda: {"pong": True, "auth_required": False,
                                "ttl_ok": True, "exposed": True})
        r = Harness(executors=ex).runner.run(Harness.make_acceptance())
        ga3 = next(p for p in r.probes if p[0] == "GA-3")
        self.assertFalse(ga3[1])
        self.assertIn("auth not enforced", ga3[2])
        self.assertIn("externally exposed", ga3[2])

    def test_10_stale_or_unregistered_heartbeat_fails_ga5(self):
        for hb in ({"registered": False, "age": 0},
                   {"registered": True, "age": HEARTBEAT_MAX_AGE + 1},
                   {"registered": True, "age": "soon"}):
            ex = healthy_executors(worker_heartbeat=lambda: hb)
            r = Harness(executors=ex).runner.run(Harness.make_acceptance())
            ga5 = next(p for p in r.probes if p[0] == "GA-5")
            self.assertFalse(ga5[1], hb)

    def test_11_published_port_breaches_ga6(self):
        ex = healthy_executors(
            published_ports=lambda: {"postgres-ssot": ["5432:5432"],
                                     "redis": [], "app-orchestrator": [],
                                     "telemetry-circuit": []})
        r = Harness(executors=ex).runner.run(Harness.make_acceptance())
        ga6 = next(p for p in r.probes if p[0] == "GA-6")
        self.assertFalse(ga6[1])
        self.assertIn("postgres-ssot publishes", ga6[2])

    def test_12_log_leakage_fails_ga7(self):
        ex = healthy_executors(
            output_streams=lambda: {
                "stdout": "connected with password=hunter22222222",
                "stderr": ""})
        r = Harness(executors=ex).runner.run(Harness.make_acceptance())
        ga7 = next(p for p in r.probes if p[0] == "GA-7")
        self.assertFalse(ga7[1])
        self.assertIn("secret-shaped", ga7[2])

    def test_13_unwired_executor_fails_closed(self):
        ex = healthy_executors()
        ex["pg_roundtrip"] = None
        r = Harness(executors=ex).runner.run(Harness.make_acceptance())
        ga2 = next(p for p in r.probes if p[0] == "GA-2")
        self.assertFalse(ga2[1])
        self.assertIn("executor not wired", ga2[2])

    def test_14_secret_in_probe_detail_flips_probe(self):
        # a malicious/broken executor leaks a canary through its payload
        ex = healthy_executors(
            app_loopback=lambda: f"ok {CANARY}")
        r = Harness(executors=ex).runner.run(Harness.make_acceptance())
        ga4 = next(p for p in r.probes if p[0] == "GA-4")
        self.assertFalse(ga4[1])
        self.assertIn("secret-shaped", ga4[2])
        self.assertNotIn(CANARY, ga4[2])


class TestReportAndRedaction(unittest.TestCase):

    def test_15_digest_deterministic_and_drift_sensitive(self):
        r1 = Harness().runner.run(Harness.make_acceptance())
        r2 = Harness().runner.run(Harness.make_acceptance())
        self.assertEqual(r1.probe_digest, r2.probe_digest)
        ex = healthy_executors(pg_roundtrip=lambda: False)
        r3 = Harness(executors=ex).runner.run(Harness.make_acceptance())
        self.assertNotEqual(r1.probe_digest, r3.probe_digest)

    def test_16_report_shape_and_bindings(self):
        acc = Harness.make_acceptance()
        r = Harness().runner.run(acc,
                                 expected_manifest=acc["manifest_sha256"])
        d = r.to_dict()
        self.assertEqual(set(d), {"schema", "verdict", "manifest_sha256",
                                  "acceptance_fingerprint", "probes",
                                  "observed_tick"})
        self.assertEqual(d["schema"], "stage_g_live_probe_report.v1")
        self.assertEqual(d["manifest_sha256"], acc["manifest_sha256"])
        self.assertEqual(d["acceptance_fingerprint"],
                         acc["acceptance_fingerprint"])

    def test_17_exactly_one_audit_per_run(self):
        h = Harness()
        h.runner.run(h.acceptance)
        self.assertEqual(len(h.reports), 1)
        h.runner.run(None)  # abort also audits exactly one
        self.assertEqual(len(h.reports), 2)

    def test_18_no_canary_in_any_report(self):
        ex = healthy_executors(
            output_streams=lambda: {"stdout": CANARY, "stderr": ""})
        h = Harness(executors=ex)
        h.runner.run(h.acceptance)
        for blob in (json.dumps(h.reports),):
            self.assertNotIn(CANARY, blob)
            self.assertNotIn("hunter22222222", blob)


class TestAst(unittest.TestCase):

    def test_19_no_sockets_subprocess_in_engine(self):
        tree = ast.parse(ENGINE.read_text(encoding="utf-8"))
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
                    self.fail("direct open() in probe core")
                if isinstance(fn, ast.Attribute) and \
                        fn.attr in ("system", "popen", "connect"):
                    self.fail(f"banned call: .{fn.attr}()")

    def test_20_doc_covers_ga_rules_and_handoff(self):
        doc = (REPO / "docs" / "deployment" /
               "stage-g-live-probes.md").read_text(encoding="utf-8")
        for token in ("GA-1", "GA-2", "GA-3", "GA-4", "GA-5", "GA-6",
                      "GA-7", "probe_digest", "D-112", "D-139",
                      "executor"):
            self.assertIn(token, doc)


if __name__ == "__main__":
    unittest.main()

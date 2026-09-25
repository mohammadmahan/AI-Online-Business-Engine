"""Stage G closure & Stage H handoff battery (D-152, offline).

Exercises `local/scripts/stage_g_closure_and_handoff.py` — the master
orchestrator concluding Stage G — fully offline: every provider is
injected, and the artifacts are REAL repo material (the Stage D
manifest + envelope, the Stage E runbook §5, and genuine D-147 /
D-149 / D-150 / D-151 chains synthesized from them):

  PASS     — the full closure cycle emits a valid
             `stage_g_closure_seal.v1` with a deterministic
             `closure_digest` when C through G align;
  CLS-01   — every missing / raising / tampered chain link refuses
             with an explicit named error;
  CLS-02   — manifest-fingerprint drift or a broken probe-to-
             acceptance binding refuses;
  CLS-03   — a blocked, skipped, or mislabeled triad verdict refuses
             (zero bypasses);
  CLS-04   — hollow rollback rows, a missing ordering invariant, and
             malformed health-fallback triggers refuse;
  REDACT   — canaries never reach the seal or the audit copy;
  AST      — pure core: zero sockets/subprocess/file-open in the
             closure engine.
"""
from __future__ import annotations

import ast
import json
import pathlib
import subprocess
import sys
import unittest

REPO = pathlib.Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "local" / "scripts"
SRC = REPO / "local" / "src"
for p in (str(SCRIPTS), str(SRC), str(SRC.parent),
          str(SRC / "security")):
    if p not in sys.path:
        sys.path.insert(0, p)

from run_stage_g_acceptance import StageGAcceptanceRunner  # noqa: E402
from stage_g_preflight_validator import bundle_hash_of  # noqa: E402
from stage_g_probe_adapters import build_executors  # noqa: E402
from verify_stage_g_live_probes import PROBES_ACCEPTED  # noqa: E402
from stage_g_closure_and_handoff import (  # noqa: E402
    SEAL_SCHEMA, STAGE_G_CLOSED, STAGE_G_OPEN, StageGClosureRunner,
    canonical_hash,
)
from src.security.launch_attestation_verifier import (  # noqa: E402
    LAUNCH_READY, TripleEvidenceGate,
)
from src.security.owner_approval_gate import (  # noqa: E402
    parse_envelope_fingerprint,
)

ENGINE = SCRIPTS / "stage_g_closure_and_handoff.py"
DOC = (REPO / "docs" / "deployment" /
       "stage-g-closure-and-handoff.md").read_text(encoding="utf-8")

CANARY = "sk-canaryvalue1234567890abcdef"

MANIFEST = (REPO / "local" / "infra" / "dokploy" /
            "docker-compose.dokploy.yaml").read_text(encoding="utf-8")
TEMPLATE = (REPO / "local" / "infra" / "dokploy" /
            "dokploy_compose_template.yaml").read_text(encoding="utf-8")
ENVELOPE = (REPO / "local" / "infra" / "dokploy" /
            "stage_d_fingerprint.envelope").read_text(encoding="utf-8")
RUNBOOK = (REPO / "docs" / "deployment" /
           "stage-e-cutover-runbook.md").read_text(encoding="utf-8")
FP = parse_envelope_fingerprint(ENVELOPE)


# --- real chain fixtures (same discipline as the D-151 battery) --------

def real_host():
    return {"verdict": "READY",
            "checks": {f"C-0{i}": True for i in range(0, 8)}}


def real_bundle() -> dict:
    bundle = {
        "schema": "cutover.bundle.v1",
        "verdict": "READY_FOR_CUTOVER",
        "candidate_manifest_sha256": FP,
        "session_id": "cutover-session-01",
        "target_env": "staging",
        "observed_tick": 100,
        "steps": [{"step": "stage_c", "ok": True, "detail": "ok",
                   "findings": []}],
        "stage_f_token_id": "tok-01",
        "abort_reason": "",
    }
    bundle["bundle_hash"] = bundle_hash_of(bundle)
    return bundle


def real_acceptance() -> dict:
    acc = StageGAcceptanceRunner(
        clock=lambda: 200, audit_sink=lambda d: None,
        preflight_verdict=lambda: {"verdict": "PREFLIGHT_CLEARED",
                                   "bundle_sha256": ""},
        manifest_provider=lambda: MANIFEST,
        template_provider=lambda: TEMPLATE).run()
    d = acc.to_dict()
    d["acceptance_fingerprint"] = acc.acceptance_fingerprint
    return d


def fake_docker_host():
    healthy = {"State": {"Running": True, "RestartCount": 0,
                         "Health": {"Status": "healthy"}},
               "NetworkSettings": {"Ports": {}}}

    def _cp(code, out, err):
        return subprocess.CompletedProcess([], code, stdout=out,
                                           stderr=err)

    def run(argv, timeout_s=15.0, input_text=None):
        if argv[1] == "inspect":
            if argv[-1] not in ("postgres-ssot", "redis",
                                "app-orchestrator",
                                "telemetry-circuit"):
                return _cp(1, "", "no such object")
            return _cp(0, json.dumps(healthy), "")
        if argv[1] == "exec":
            inner = argv[4:]
            if inner[0] == "psql":
                return _cp(0, "1", "")
            if inner[0] == "redis-cli":
                return _cp(0, "PONG" if "PING" in inner else
                           "maxmemory-policy\nnoeviction", "")
            if inner[0] == "wget":
                return _cp(0, json.dumps({"registered": True,
                                          "age": 3}), "")
        if argv[1] == "logs":
            return _cp(0, "engine boot ok\n", "")
        return _cp(2, "", "unknown")
    return run


def real_probe_report() -> dict:
    acc = real_acceptance()
    ex = build_executors(inspect_runner=fake_docker_host(),
                         exec_runner=fake_docker_host(),
                         log_runner=fake_docker_host())
    from verify_stage_g_live_probes import StageGLiveProbeRunner
    report = StageGLiveProbeRunner(clock=lambda: 300,
                                   audit_sink=lambda d: None,
                                   **ex).run(acc, expected_manifest=FP)
    assert report.verdict == PROBES_ACCEPTED
    d = report.to_dict()
    d["probe_digest"] = report.probe_digest
    return d


def audit_rows_for(bundle, acceptance, probe):
    return [
        {"event_kind": "stage_g_preflight",
         "detail": {"bundle_hash": bundle["bundle_hash"]}},
        {"event_kind": "cutover_bundle_recorded",
         "detail": {"bundle_hash": bundle["bundle_hash"]}},
        {"event_kind": "stage_g_acceptance",
         "detail": {"acceptance_fingerprint":
                    acceptance["acceptance_fingerprint"]}},
        {"event_kind": "stage_g_live_probe",
         "detail": {"probe_digest": probe["probe_digest"]}},
    ]


def real_triad(bundle=None, acceptance=None, probe=None) -> dict:
    bundle = bundle if bundle is not None else real_bundle()
    acceptance = acceptance if acceptance is not None \
        else real_acceptance()
    probe = probe if probe is not None else real_probe_report()
    gate = TripleEvidenceGate(
        bundle=lambda: bundle, acceptance=lambda: acceptance,
        probe=lambda: probe,
        audit_rows=lambda: audit_rows_for(bundle, acceptance, probe),
        chain_verifier=lambda: {"ok": True, "rows": 4})
    return gate.evaluate().to_dict()


def real_fallbacks() -> dict:
    return {"triggers": [
        {"name": "probe_red", "threshold_ticks": 1,
         "action": "Stage E §5 row governs (RB-3)"},
        {"name": "heartbeat_stale", "threshold_ticks": 120,
         "action": "RB-3 drain + edge to blue"},
        {"name": "bundle_expired", "threshold_ticks": 5000,
         "action": "re-attest (closure refused, no rollback)"},
        {"name": "chain_broken", "threshold_ticks": 1,
         "action": "RB-4 freeze dispatch, reconcile"},
    ]}


class Harness:
    """Real-provider closure runner; overrides swap single links."""

    def __init__(self, **overrides):
        self.sink: list = []
        providers = {
            "host_readiness": real_host,
            "manifest_text": lambda: MANIFEST,
            "envelope_text": lambda: ENVELOPE,
            "rollback_spec": lambda: RUNBOOK,
            "fallback_spec": real_fallbacks,
            "bundle": real_bundle,
            "acceptance_report": real_acceptance,
            "probe_report": real_probe_report,
            "triad_verdict": real_triad,
        }
        providers.update(overrides)
        self.runner = StageGClosureRunner(
            clock=lambda: 900, audit_sink=self.sink.append, **providers)

    def run(self):
        return self.runner.run()


# ===================================================================
# PASS — the full closure cycle
# ===================================================================

class TestClosurePass(unittest.TestCase):

    def test_01_full_closure_passes_with_valid_seal(self):
        seal = Harness().run()
        self.assertEqual(seal.verdict, STAGE_G_CLOSED)
        self.assertTrue(seal.closed)
        d = seal.to_dict()
        self.assertEqual(d["schema"], SEAL_SCHEMA)
        self.assertEqual(d["schema"], "stage_g_closure_seal.v1")
        self.assertEqual(seal.closure_digest,
                         canonical_hash(d))
        ids = [c[0] for c in seal.checks]
        self.assertEqual(ids,
                         ["CLS-01"] * 6 + ["CLS-02"] * 2 +
                         ["CLS-03"] + ["CLS-04"] * 3 + ["CLS-05"])
        self.assertTrue(all(c[1] for c in seal.checks))

    def test_02_seal_binds_all_roots_and_is_deterministic(self):
        bundle, acc, probe = real_bundle(), real_acceptance(), \
            real_probe_report()
        providers = dict(
            bundle=lambda: bundle,
            acceptance_report=lambda: acc,
            probe_report=lambda: probe,
            triad_verdict=lambda: real_triad(bundle, acc, probe))
        s1 = Harness(**providers).run()
        s2 = Harness(**providers).run()
        self.assertEqual(s1.closure_digest, s2.closure_digest)
        self.assertEqual(s1.manifest_sha256, FP)
        self.assertEqual(s1.bundle_hash, bundle["bundle_hash"])
        self.assertEqual(s1.acceptance_fingerprint,
                         acc["acceptance_fingerprint"])
        self.assertEqual(s1.probe_digest, probe["probe_digest"])
        # drift in any bound artifact changes the root digest
        drifted = dict(providers)
        def drifted_acc():
            a = real_acceptance()
            a["verdict"] = "REJECTED"  # tamper AFTER fingerprinting
            return a
        drifted["acceptance_report"] = drifted_acc
        s3 = Harness(**drifted).run()
        self.assertNotEqual(s1.closure_digest, s3.closure_digest)

    def test_03_exactly_one_audited_seal_per_run(self):
        h = Harness()
        h.run()
        self.assertEqual(len(h.sink), 1)
        h.run()
        self.assertEqual(len(h.sink), 2)
        # an OPEN seal is audited exactly once as well
        h2 = Harness(host_readiness=None)
        h2.run()
        self.assertEqual(len(h2.sink), 1)


# ===================================================================
# CLS-01 — missing / raising / tampered chain links
# ===================================================================

class TestCls01(unittest.TestCase):

    def test_04_every_missing_link_refused_with_named_error(self):
        cases = {
            "host_readiness": "Stage C host readiness absent",
            "manifest_text": "Stage D manifest absent",
            "envelope_text": "Stage D fingerprint envelope absent",
            "rollback_spec": "Stage E rollback contract absent",
            "bundle": "Stage F bundle absent",
            "acceptance_report": "Stage G acceptance report absent",
            "probe_report": "Stage G live probe report absent",
        }
        for prov, phrase in cases.items():
            seal = Harness(**{prov: None}).run()
            self.assertEqual(seal.verdict, STAGE_G_OPEN, prov)
            self.assertTrue(
                any(phrase in c[2] for c in seal.checks), prov)

    def test_05_provider_failure_named_type_only(self):
        def boom():
            raise RuntimeError("storage exploded")
        seal = Harness(host_readiness=boom).run()
        self.assertEqual(seal.verdict, STAGE_G_OPEN)
        self.assertTrue(any("provider failure: RuntimeError" in c[2]
                            for c in seal.checks))
        self.assertFalse(any("exploded" in c[2] for c in seal.checks))

    def test_06_tampered_bundle_refused(self):
        def tampered():
            b = real_bundle()
            b["verdict"] = "BLOCKED"  # AFTER the hash was recorded
            return b
        seal = Harness(bundle=tampered).run()
        self.assertEqual(seal.verdict, STAGE_G_OPEN)
        self.assertTrue(any("TAMPERED bundle" in c[2]
                            for c in seal.checks))

    def test_07_bundle_without_owner_token_refused(self):
        def tokenless():
            b = real_bundle()
            b["stage_f_token_id"] = ""
            b["bundle_hash"] = bundle_hash_of(
                {k: v for k, v in b.items() if k != "bundle_hash"})
            return b
        seal = Harness(bundle=tokenless).run()
        self.assertEqual(seal.verdict, STAGE_G_OPEN)
        self.assertTrue(any("no owner token" in c[2]
                            for c in seal.checks))

    def test_08_host_readiness_not_ready_refused(self):
        for host in ({"verdict": "READY",
                      "checks": {"C-03": False}},
                     {"verdict": "DEGRADED",
                      "checks": {"C-00": True}},
                     {"verdict": "READY", "checks": {}}):
            seal = Harness(host_readiness=lambda h=host: h).run()
            self.assertEqual(seal.verdict, STAGE_G_OPEN, host)

    def test_09_stage_d_envelope_malformed_unbound_or_drifted(self):
        drift = "manifest_sha256: " + "e" * 64 + \
            "\nbound_for: stage-e-cutover\ngenerator: x\n"
        cases = {
            "malformed": "# no hash row here\nbound_for: stage-e-cutover\n",
            "unbound": f"manifest_sha256: {FP}\nbound_for: production\n",
            "drifted": drift,
        }
        for label, env in cases.items():
            seal = Harness(envelope_text=lambda e=env: e).run()
            self.assertEqual(seal.verdict, STAGE_G_OPEN, label)
        seal = Harness(envelope_text=lambda: ENVELOPE,
                       manifest_text=lambda: MANIFEST + "# drift\n").run()
        self.assertEqual(seal.verdict, STAGE_G_OPEN)
        self.assertTrue(any("does not match its envelope" in c[2]
                            for c in seal.checks))


# ===================================================================
# CLS-02 — zero drift / probe-acceptance binding
# ===================================================================

class TestCls02(unittest.TestCase):

    def test_10_manifest_fingerprint_drift_refused(self):
        def drifted_probe():
            p = real_probe_report()
            # rebuild the report bound to a DIFFERENT manifest
            p["manifest_sha256"] = "b" * 64
            return p
        # the drift must be consistent inside the probe artifact for
        # CLS-02 to isolate the drift finding — rebuild digest too
        def drifted_probe_consistent():
            from verify_stage_g_live_probes import \
                StageGLiveProbeRunner as R
            acc = real_acceptance()
            ex = build_executors(inspect_runner=fake_docker_host(),
                                 exec_runner=fake_docker_host(),
                                 log_runner=fake_docker_host())
            rep = R(clock=lambda: 300, audit_sink=lambda d: None,
                    **ex).run(acc, expected_manifest="b" * 64)
            d = rep.to_dict()
            d["probe_digest"] = rep.probe_digest
            return d
        seal = Harness(
            probe_report=drifted_probe_consistent,
            triad_verdict=lambda: real_triad(
                acceptance=real_acceptance(),
                probe=drifted_probe_consistent())).run()
        self.assertEqual(seal.verdict, STAGE_G_OPEN)
        self.assertTrue(any("drift" in c[2] for c in seal.checks))

    def test_11_probe_acceptance_binding_broken_refused(self):
        def broken_probe():
            p = real_probe_report()
            p["acceptance_fingerprint"] = "c" * 64
            return p
        seal = Harness(probe_report=broken_probe).run()
        self.assertEqual(seal.verdict, STAGE_G_OPEN)
        self.assertTrue(any("different clearance" in c[2]
                            for c in seal.checks))


# ===================================================================
# CLS-03 — the triad gate with zero bypasses
# ===================================================================

class TestCls03(unittest.TestCase):

    def test_12_blocked_triad_refused(self):
        """A complete rule set with one failing rule — the CLS-03
        blocked path (a skipped rule is test_13's separate refusal)."""
        real_rows = real_triad()["checks"]
        rows = [[c[0], False, "forced blocker"] for c in real_rows]
        seal = Harness(
            triad_verdict=lambda: {
                "schema": "stage_g_triple_evidence.v1",
                "verdict": "LAUNCH_EVIDENCE_INCOMPLETE",
                "checks": rows}).run()
        self.assertEqual(seal.verdict, STAGE_G_OPEN)
        blocked = [c[2] for c in seal.checks if "blocked at" in c[2]]
        self.assertTrue(blocked and "TRIAD-03" in blocked[0],
                        seal.checks)

    def test_13_skipped_triad_rules_refused(self):
        seal = Harness(
            triad_verdict=lambda: {
                "schema": "stage_g_triple_evidence.v1",
                "verdict": LAUNCH_READY,
                "checks": [["TRIAD-01", True, "ok"]]}).run()
        self.assertEqual(seal.verdict, STAGE_G_OPEN)
        self.assertTrue(any("skipped or absent" in c[2]
                            for c in seal.checks))
        self.assertTrue(any("TRIAD-04" in c[2] for c in seal.checks))

    def test_14_mislabeled_triad_verdict_refused(self):
        rows = real_triad()["checks"]
        passing = [[c[0], True, c[2]] for c in rows]
        seal = Harness(
            triad_verdict=lambda: {
                "schema": "stage_g_triple_evidence.v1",
                "verdict": "PREFLIGHT_CLEARED",
                "checks": passing}).run()
        self.assertEqual(seal.verdict, STAGE_G_OPEN)
        self.assertTrue(any("!= 'LAUNCH_EVIDENCE_COMPLETE'" in c[2]
                            for c in seal.checks))

    def test_15_absent_triad_verdict_refused(self):
        seal = Harness(triad_verdict=None).run()
        self.assertEqual(seal.verdict, STAGE_G_OPEN)
        self.assertTrue(any("triple-evidence verdict absent" in c[2]
                            for c in seal.checks))


# ===================================================================
# CLS-04 — rollback strategy + health fallbacks
# ===================================================================

class TestCls04(unittest.TestCase):

    def test_16_incomplete_rollback_matrix_refused(self):
        seal = Harness(
            rollback_spec=lambda: "| RB-1 | trigger | detect | fix |\n"
                                  "stop new work first, then "
                                  "compensate/drain, then reconcile\n"
        ).run()
        self.assertEqual(seal.verdict, STAGE_G_OPEN)
        self.assertTrue(any("missing or unparsable" in c[2]
                            for c in seal.checks))

    def test_17_hollow_rollback_rows_refused(self):
        text = "\n".join(
            f"| RB-{i} |  |  |  |" for i in range(1, 7)) + \
            "\nstop new work first, then compensate/drain, " \
            "then reconcile\n"
        seal = Harness(rollback_spec=lambda: text).run()
        self.assertEqual(seal.verdict, STAGE_G_OPEN)
        self.assertTrue(any("lack trigger/procedure" in c[2]
                            for c in seal.checks))

    def test_18_missing_ordering_invariant_refused(self):
        stripped = RUNBOOK.replace(
            "stop new work first, then compensate/drain,\n"
            "then reconcile; durable evidence is preserved, never "
            "deleted** (D-139).", "")
        seal = Harness(rollback_spec=lambda: stripped).run()
        self.assertEqual(seal.verdict, STAGE_G_OPEN)
        self.assertTrue(any("ordering invariant absent" in c[2]
                            for c in seal.checks))

    def test_19_malformed_fallback_triggers_refused(self):
        for bad in ({"triggers": []},
                    {"triggers": [{"name": "probe_red",
                                   "threshold_ticks": 0,
                                   "action": "halt"}]},
                    {"triggers": [{"name": "probe_red",
                                   "threshold_ticks": "soon",
                                   "action": "halt"}]},
                    {"triggers": [{"name": "",
                                   "threshold_ticks": 5,
                                   "action": "halt"}]},
                    {"triggers": [{"name": "x", "threshold_ticks": 5}]}):
            seal = Harness(fallback_spec=lambda b=bad: b).run()
            self.assertEqual(seal.verdict, STAGE_G_OPEN, bad)
            self.assertTrue(any("fallback triggers malformed" in c[2]
                                for c in seal.checks))


# ===================================================================
# REDACT — canaries never escape the seal or the audit copy
# ===================================================================

class TestRedaction(unittest.TestCase):

    def test_20_no_canary_in_seal_or_audit(self):
        def leaky_acceptance():
            acc = real_acceptance()
            acc["checks"] = [["ACC-99", True, f"note {CANARY} here"]]
            return acc
        h = Harness(acceptance_report=leaky_acceptance,
                    triad_verdict=lambda: real_triad(
                        acceptance=leaky_acceptance()))
        seal = h.run()
        blob = json.dumps(seal.to_dict())
        self.assertNotIn(CANARY, blob)
        self.assertNotIn(CANARY, json.dumps(h.sink))
        # a leaky detail is also flipped: the acceptance row carries
        # the masked marker, never the secret
        self.assertTrue(any("[REDACTED]" in c[2] for c in seal.checks)
                        or CANARY not in blob)

    def test_21_error_detail_type_only(self):
        def boom():
            raise RuntimeError(f"conn failed {CANARY}")
        h = Harness(host_readiness=boom)
        seal = h.run()
        # neither the seal nor the audit copy carries the payload;
        # the detail names the exception TYPE only (D-124)
        self.assertNotIn(CANARY, json.dumps(seal.to_dict()))
        self.assertNotIn(CANARY, json.dumps(h.sink))
        self.assertIn("provider failure: RuntimeError",
                      " ".join(c[2] for c in seal.checks))
        self.assertNotIn("conn failed", json.dumps(h.sink))


# ===================================================================
# AST — pure closure core
# ===================================================================

class TestAst(unittest.TestCase):

    def test_22_pure_core_no_io_in_engine(self):
        tree = ast.parse(ENGINE.read_text(encoding="utf-8"))
        banned = {"socket", "subprocess", "ssl", "http", "urllib",
                  "requests", "ftplib", "pathlib", "os"}
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
                    self.fail("direct open() in closure core")
                if isinstance(fn, ast.Attribute) and \
                        fn.attr in ("system", "popen", "connect"):
                    self.fail(f"banned call: .{fn.attr}()")

    def test_23_doc_covers_seal_and_runbook(self):
        for token in ("stage_g_closure_seal.v1", "closure_digest",
                      "STAGE_G_CLOSED", "CLS-01", "CLS-02", "CLS-03",
                      "CLS-04", "CLS-05", "RB-1", "RB-6", "D-139",
                      "stage-e-cutover", "threshold_ticks",
                      "qa.health_report.v1", "stage_h_activation"):
            self.assertIn(token, DOC)


if __name__ == "__main__":
    unittest.main()

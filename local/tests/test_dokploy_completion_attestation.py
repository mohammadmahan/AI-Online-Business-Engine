"""Dokploy completion attestation battery (D-154, offline).

Exercises `local/scripts/dokploy_completion_attestation.py` fully
offline — every provider injected, every artifact REAL repo material
(the same authentic Stage C→H chain the D-152/D-153 batteries proved:
real Stage D manifest+envelope, real Stage F gate token, real D-149
acceptance runner, real D-150 probe runner over fake docker executors,
real D-151 triad gate, real D-152 closure seal, real D-153 executor
activation record):

  PASS   — the complete chain ⇒ INFRASTRUCTURE_COMPLETE with a valid
           `dokploy.completion_attestation.v1`;
  DEP-01 — any lifecycle stage missing, forged or altered ⇒ refusal
           naming the stage;
  DEP-02 — digest drift between stages ⇒ refusal;
  DEP-03 — unrooted commitments / broken D-112 chain ⇒ refusal;
  DEP-04 — Live-Wiring (Phases 5–18) entry-point readiness failures ⇒
           refusal;
  DEP-05 — exactly one canonical certificate per run, deterministic
           digest, refusal path emits INFRASTRUCTURE_INCOMPLETE;
  REDACT — signing key and canaries never reach the certificate or
           the audit copy; public commitments survive;
  AST    — pure core (no socket/subprocess/network), zero banned
           imports or calls.
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
from verify_stage_g_live_probes import (  # noqa: E402
    PROBES_ACCEPTED, StageGLiveProbeRunner,
)
from stage_g_closure_and_handoff import (  # noqa: E402
    StageGClosureRunner, canonical_hash,
)
from stage_h_cutover_executor import (  # noqa: E402
    CUTOVER_EXECUTED, StageHCutoverExecutor,
)
from src.security.launch_attestation_verifier import (  # noqa: E402
    TripleEvidenceGate,
)
from src.security.owner_approval_gate import (  # noqa: E402
    OwnerApprovalGate, TokenDraft, mint_token,
    parse_envelope_fingerprint,
)
from dokploy_completion_attestation import (  # noqa: E402
    ATTESTATION_SCHEMA, CUTOVER_EXECUTED, INFRA_COMPLETE,
    INFRA_INCOMPLETE, LIVE_WIRING_PHASES,
    CompletionAttestation, DokployCompletionAttestor, canonical_hash,
    recompute_digest,
)

ENGINE = SCRIPTS / "dokploy_completion_attestation.py"

CANARY = "sk-canaryvalue1234567890abcdef"
SIGNING_KEY = "stage-f-owner-signing-key-0123456789abcdef"
SESSION = "cutover-session-01"
TARGET = "staging"
SERVICES = ("postgres-ssot", "redis", "app-orchestrator",
            "telemetry-circuit")

MANIFEST = (REPO / "local" / "infra" / "dokploy" /
            "docker-compose.dokploy.yaml").read_text(encoding="utf-8")
TEMPLATE = (REPO / "local" / "infra" / "dokploy" /
            "dokploy_compose_template.yaml").read_text(encoding="utf-8")
ENVELOPE = (REPO / "local" / "infra" / "dokploy" /
            "stage_d_fingerprint.envelope").read_text(encoding="utf-8")
RUNBOOK = (REPO / "docs" / "deployment" /
           "stage-e-cutover-runbook.md").read_text(encoding="utf-8")
FP = parse_envelope_fingerprint(ENVELOPE)


# --- the authentic Stage C→H chain (D-152/D-153 battery discipline) ----

def real_host():
    return {"verdict": "READY",
            "checks": {f"C-0{i}": True for i in range(0, 8)}}


def real_bundle() -> dict:
    bundle = {
        "schema": "cutover.bundle.v1",
        "verdict": "READY_FOR_CUTOVER",
        "candidate_manifest_sha256": FP,
        "session_id": SESSION,
        "target_env": TARGET,
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
            if argv[-1] not in SERVICES:
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
    report = StageGLiveProbeRunner(clock=lambda: 300,
                                   audit_sink=lambda d: None,
                                   **ex).run(acc, expected_manifest=FP)
    assert report.verdict == PROBES_ACCEPTED
    d = report.to_dict()
    d["probe_digest"] = report.probe_digest
    return d


def real_triad(bundle, acceptance, probe) -> dict:
    rows = [
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
    gate = TripleEvidenceGate(
        bundle=lambda: bundle, acceptance=lambda: acceptance,
        probe=lambda: probe,
        audit_rows=lambda: rows,
        chain_verifier=lambda: {"ok": True, "rows": 4})
    return gate.evaluate().to_dict()


def real_fallbacks() -> dict:
    return {"triggers": [
        {"name": "probe_red", "threshold_ticks": 1,
         "action": "Stage E §5 row governs (RB-3)"},
        {"name": "heartbeat_stale", "threshold_ticks": 120,
         "action": "RB-3 drain + edge to blue"},
        {"name": "bundle_expired", "threshold_ticks": 5000,
         "action": "re-attest (closure refused)"},
        {"name": "chain_broken", "threshold_ticks": 1,
         "action": "RB-4 freeze dispatch, reconcile"},
    ]}


class MemoryReplayStore:
    def __init__(self):
        self.burned = set()

    def consume(self, key: str) -> bool:
        if key in self.burned:
            return False
        self.burned.add(key)
        return True


def real_target_state() -> dict:
    return {s: {"running": True, "healthy": True, "restarts": 0,
                "ports": []} for s in SERVICES}


def real_probes() -> dict:
    return {"edge_smoke": True, "worker_ready": True, "ssot_rw": True}


def real_draft(now: int) -> TokenDraft:
    return TokenDraft(manifest_sha256=FP, session_id=SESSION,
                      target_env=TARGET, issued_tick=now - 10,
                      expires_tick=now + 500,
                      nonce=f"completion-{now}")


def real_approval(now: int) -> dict:
    draft = real_draft(now)
    token = mint_token(SIGNING_KEY, draft)
    gate = OwnerApprovalGate(
        signing_key=SIGNING_KEY,
        replay_store=MemoryReplayStore(),
        clock=lambda: now,
        audit_sink=lambda d: None,
        manifest_sha256=FP)
    verdict = gate.evaluate(token, draft, SESSION, TARGET, ENVELOPE)
    assert verdict.gate == "GO"
    return {"verdict": verdict.to_dict(), "draft": draft}


def real_activation(now: int = 1000):
    """Run the REAL D-153 executor through the REAL D-152 closure
    runner. Returns (record_dict, seal_dict, closure_rows)."""
    bundle, acc, probe = real_bundle(), real_acceptance(), \
        real_probe_report()
    triad = real_triad(bundle, acc, probe)
    runner = StageGClosureRunner(
        clock=lambda: 900, audit_sink=lambda d: None,
        host_readiness=real_host,
        manifest_text=lambda: MANIFEST,
        envelope_text=lambda: ENVELOPE,
        rollback_spec=lambda: RUNBOOK,
        fallback_spec=real_fallbacks,
        bundle=lambda: bundle,
        acceptance_report=lambda: acc,
        probe_report=lambda: probe,
        triad_verdict=lambda: triad)
    seal = runner.run()
    assert seal.closed
    seal_d = seal.to_dict()
    seal_d["closure_digest"] = seal.closure_digest
    closure_rows = [{"event_kind": "stage_g_closure",
                     "detail": {"closure_digest":
                                seal_d["closure_digest"]}}]
    approval = real_approval(now)
    sink: list = []
    executor = StageHCutoverExecutor(
        clock=lambda: now, audit_sink=sink.append,
        seal_provider=lambda: seal_d,
        audit_rows=lambda: closure_rows,
        approval_verdict=lambda: approval["verdict"],
        token_draft=lambda: vars(approval["draft"]),
        target_state=real_target_state,
        transition=lambda: {"active": True, "via": "dokploy"},
        post_activation_probes=real_probes)
    record = executor.run()
    assert record.verdict == CUTOVER_EXECUTED
    rec_d = record.to_dict()
    rec_d["activation_digest"] = record.activation_digest
    # mirror the production rooting: the activation commitment lands
    # in the D-112 ledger
    closure_rows.append({"event_kind": "stage_h_activation",
                         "detail": {
                             "activation_digest":
                             rec_d["activation_digest"],
                             "manifest_sha256":
                             rec_d["manifest_sha256"],
                             "closure_digest":
                             rec_d["closure_digest"],
                             "token_id": rec_d["token_id"]}})
    return rec_d, seal_d, closure_rows


def real_ledger(bundle, acc, probe, seal, activation) -> list:
    return [
        {"event_kind": "stage_g_preflight",
         "detail": {"bundle_hash": bundle["bundle_hash"]}},
        {"event_kind": "cutover_bundle_recorded",
         "detail": {"bundle_hash": bundle["bundle_hash"]}},
        {"event_kind": "stage_g_acceptance",
         "detail": {"acceptance_fingerprint":
                    acc["acceptance_fingerprint"]}},
        {"event_kind": "stage_g_live_probe",
         "detail": {"probe_digest": probe["probe_digest"]}},
        {"event_kind": "stage_g_closure",
         "detail": {"closure_digest": seal["closure_digest"]}},
        {"event_kind": "stage_h_activation",
         "detail": {"activation_digest":
                    activation["activation_digest"]}},
    ]


def real_readiness() -> dict:
    return {
        "runtime_profile_verified": True,
        "phases": [{"phase": num, "name": name,
                    "entry_point":
                    "canonical." + name.split()[0].lower() + "_engine",
                    "present": True, "verified": True,
                    "wired": True, "detail": "ready"}
                   for num, name in LIVE_WIRING_PHASES],
    }


def chain_ok(rows: int = 6) -> dict:
    return {"ok": True, "rows": rows}


# --- the shared authentic chain (deterministic: fixed logical clocks) ---

_CHAIN: dict = {}


def the_chain() -> dict:
    if not _CHAIN:
        activation, seal, rows = real_activation(1000)
        bundle, acc, probe = real_bundle(), real_acceptance(), \
            real_probe_report()
        _CHAIN.update(activation=activation, seal=seal,
                      closure_rows=rows, bundle=bundle, acc=acc,
                      probe=probe, triad=real_triad(bundle, acc,
                                                    probe),
                      ledger=real_ledger(bundle, acc, probe, seal,
                                         activation))
    return _CHAIN


# --- the wired harness ---------------------------------------------------

class Harness:
    """Fully wired attestor over the authentic chain; overrides swap
    providers (None = provider absent). `fresh=True` builds an
    independent second chain (determinism checks)."""

    def __init__(self, now: int = 2000, fresh: bool = False,
                 **overrides):
        self.now = now
        self.sink: list = []
        if fresh:
            self.bundle, self.acc, self.probe = \
                real_bundle(), real_acceptance(), real_probe_report()
            self.triad = real_triad(self.bundle, self.acc, self.probe)
            self.activation, self.seal, self.closure_rows = \
                real_activation(now)
            self.ledger = real_ledger(self.bundle, self.acc,
                                      self.probe, self.seal,
                                      self.activation)
        else:
            c = the_chain()
            self.bundle = c["bundle"]
            self.acc = c["acc"]
            self.probe = c["probe"]
            self.triad = c["triad"]
            self.activation = c["activation"]
            self.seal = c["seal"]
            self.closure_rows = c["closure_rows"]
            self.ledger = c["ledger"]
        providers = {
            "host_readiness": real_host,
            "manifest_text": lambda: MANIFEST,
            "envelope_text": lambda: ENVELOPE,
            "bundle": lambda: self.bundle,
            "acceptance_report": lambda: self.acc,
            "probe_report": lambda: self.probe,
            "triad_verdict": lambda: self.triad,
            "seal": lambda: self.seal,
            "activation_record": lambda: self.activation,
            "audit_rows": lambda: self.ledger,
            "chain_verifier": lambda: chain_ok(len(self.ledger)),
            "live_wiring_readiness": real_readiness,
        }
        providers.update(overrides)
        self.attestor = DokployCompletionAttestor(
            clock=lambda: self.now, audit_sink=self.sink.append,
            **providers)

    def run(self) -> CompletionAttestation:
        return self.attestor.run()


# ===================================================================
# PASS — the full completion attestation
# ===================================================================

class TestCompletionPass(unittest.TestCase):

    def test_01_full_chain_completes(self):
        h = Harness()
        cert = h.run()
        self.assertEqual(cert.verdict, INFRA_COMPLETE)
        self.assertTrue(cert.complete)
        d = cert.to_dict()
        self.assertEqual(d["schema"], ATTESTATION_SCHEMA)
        self.assertEqual(d["schema"],
                         "dokploy.completion_attestation.v1")
        self.assertEqual(d["manifest_sha256"], FP)
        self.assertEqual(d["bundle_hash"], h.bundle["bundle_hash"])
        self.assertEqual(d["acceptance_fingerprint"],
                         h.acc["acceptance_fingerprint"])
        self.assertEqual(d["probe_digest"], h.probe["probe_digest"])
        self.assertEqual(d["closure_digest"],
                         h.seal["closure_digest"])
        self.assertEqual(d["activation_digest"],
                         h.activation["activation_digest"])
        ids = [c[0] for c in cert.checks]
        self.assertTrue(all(i in ids for i in
                            ("DEP-01", "DEP-02", "DEP-03", "DEP-04",
                             "DEP-05")))
        self.assertTrue(all(c[1] for c in cert.checks))
        self.assertTrue(d["chain"]["anchored"])
        self.assertTrue(d["chain"]["zero_breaks"])
        self.assertEqual(len(d["chain"]["anchors"]), 5)
        self.assertTrue(d["live_wiring"]["runtime_profile_verified"])
        self.assertEqual(d["live_wiring"]["phases_ready"],
                         len(LIVE_WIRING_PHASES))

    def test_02_certificate_digest_deterministic(self):
        c1 = Harness(now=3000, fresh=True).run()
        c2 = Harness(now=3000, fresh=True).run()
        self.assertEqual(c1.attestation_digest,
                         c2.attestation_digest)
        self.assertEqual(c1.attestation_digest,
                         canonical_hash(c1.to_dict()))

    def test_03_exactly_one_audited_certificate_per_run(self):
        h = Harness()
        h.run()
        h.run()
        self.assertEqual(len(h.sink), 2)
        # the audit copy keeps the public commitments (restored after
        # deep redaction)
        self.assertEqual(h.sink[-1]["manifest_sha256"], FP)
        self.assertEqual(h.sink[-1]["closure_digest"],
                         h.seal["closure_digest"])
        self.assertEqual(h.sink[-1]["activation_digest"],
                         h.activation["activation_digest"])

    def test_04_recompute_helper_matches_producers(self):
        h = Harness()
        self.assertEqual(recompute_digest(h.bundle),
                         h.bundle["bundle_hash"])
        self.assertEqual(recompute_digest(h.acc),
                         h.acc["acceptance_fingerprint"])
        self.assertEqual(recompute_digest(h.probe),
                         h.probe["probe_digest"])
        self.assertEqual(recompute_digest(h.seal),
                         h.seal["closure_digest"])
        self.assertEqual(recompute_digest(h.activation),
                         h.activation["activation_digest"])
        self.assertEqual(recompute_digest({}), "")
        self.assertEqual(recompute_digest(
            {"bundle_hash": "x", "probe_digest": "y"}), "")


# ===================================================================
# DEP-01 — missing / forged / altered stages
# ===================================================================

class TestDep01Chain(unittest.TestCase):

    def test_05_missing_host_readiness_refused(self):
        cert = Harness(host_readiness=None).run()
        self.assertEqual(cert.verdict, INFRA_INCOMPLETE)
        self.assertTrue(any("Stage C host readiness absent" in c[2]
                            for c in cert.checks))

    def test_06_failing_host_check_refused(self):
        def degraded():
            host = real_host()
            host["checks"]["C-03"] = False
            return host
        cert = Harness(host_readiness=degraded).run()
        self.assertEqual(cert.verdict, INFRA_INCOMPLETE)
        self.assertTrue(any("not READY or has failing checks" in c[2]
                            for c in cert.checks))

    def test_07_tampered_manifest_refused(self):
        cert = Harness(manifest_text=lambda: MANIFEST + "\n# drift\n"
                       ).run()
        self.assertEqual(cert.verdict, INFRA_INCOMPLETE)
        self.assertTrue(any("does not match its envelope" in c[2]
                            for c in cert.checks))

    def test_08_unbound_envelope_refused(self):
        env = ENVELOPE.replace("bound_for: stage-e-cutover",
                               "bound_for: other-target")
        cert = Harness(envelope_text=lambda: env).run()
        self.assertEqual(cert.verdict, INFRA_INCOMPLETE)
        self.assertTrue(any("not bound for stage-e-cutover" in c[2]
                            for c in cert.checks))

    def test_09_forged_bundle_hash_refused(self):
        def forged():
            b = dict(the_chain()["bundle"])
            b["observed_tick"] = b["observed_tick"] + 1
            return b
        cert = Harness(bundle=forged).run()
        self.assertEqual(cert.verdict, INFRA_INCOMPLETE)
        self.assertTrue(any("TAMPERED bundle" in c[2]
                            for c in cert.checks))

    def test_10_bundle_without_owner_token_refused(self):
        def unauthorized():
            b = dict(the_chain()["bundle"])
            b["stage_f_token_id"] = ""
            return b
        cert = Harness(bundle=unauthorized).run()
        self.assertEqual(cert.verdict, INFRA_INCOMPLETE)
        self.assertTrue(any("no Stage F owner token" in c[2]
                            for c in cert.checks))

    def test_11_altered_acceptance_report_refused(self):
        def altered():
            a = dict(the_chain()["acc"])
            a["checks"] = a["checks"][:-1]  # drop one check
            return a
        cert = Harness(acceptance_report=altered).run()
        self.assertEqual(cert.verdict, INFRA_INCOMPLETE)
        self.assertTrue(any("ALTERED report" in c[2]
                            for c in cert.checks))

    def test_12_altered_probe_report_refused(self):
        def altered():
            p = dict(the_chain()["probe"])
            p["observed_tick"] = p["observed_tick"] + 1
            return p
        cert = Harness(probe_report=altered).run()
        self.assertEqual(cert.verdict, INFRA_INCOMPLETE)
        self.assertTrue(any("ALTERED report" in c[2]
                            for c in cert.checks))

    def test_13_incomplete_triad_refused(self):
        def broken_triad():
            t = json.loads(json.dumps(the_chain()["triad"]))
            t["checks"] = [c for c in t["checks"]
                           if c[0] != "TRIAD-03"]
            return t
        cert = Harness(triad_verdict=broken_triad).run()
        self.assertEqual(cert.verdict, INFRA_INCOMPLETE)
        self.assertTrue(any("skipped or absent" in c[2]
                            for c in cert.checks))

    def test_14_open_seal_refused(self):
        def open_seal():
            s = dict(the_chain()["seal"])
            s["verdict"] = "STAGE_G_OPEN"
            s["closure_digest"] = canonical_hash(
                {k: v for k, v in s.items() if k != "closure_digest"})
            return s
        cert = Harness(seal=open_seal).run()
        self.assertEqual(cert.verdict, INFRA_INCOMPLETE)
        self.assertTrue(any("Stage G is OPEN" in c[2]
                            for c in cert.checks))

    def test_15_altered_seal_refused(self):
        def altered():
            s = dict(the_chain()["seal"])
            s["observed_tick"] = s["observed_tick"] + 1
            return s
        cert = Harness(seal=altered).run()
        self.assertEqual(cert.verdict, INFRA_INCOMPLETE)
        self.assertTrue(any("ALTERED seal" in c[2]
                            for c in cert.checks))

    def test_16_aborted_activation_refused(self):
        def aborted():
            r = dict(the_chain()["activation"])
            r["verdict"] = "CUTOVER_ABORTED"
            r["activation_digest"] = recompute_digest(r)
            return r
        cert = Harness(activation_record=aborted).run()
        self.assertEqual(cert.verdict, INFRA_INCOMPLETE)
        self.assertTrue(any("not ACTIVE" in c[2]
                            for c in cert.checks))

    def test_17_missing_stage_names_its_blocker(self):
        h = Harness(acceptance_report=None)
        cert = h.run()
        self.assertEqual(cert.verdict, INFRA_INCOMPLETE)
        self.assertTrue(any("Stage G acceptance report absent" in c[2]
                            for c in cert.checks))
        # the certificate still carries every other digest slot
        self.assertEqual(cert.to_dict()["bundle_hash"],
                         h.bundle["bundle_hash"])


# ===================================================================
# DEP-02 — digest drift
# ===================================================================

class TestDep02Drift(unittest.TestCase):

    def test_18_manifest_drift_in_bundle_refused(self):
        def drifted():
            b = dict(the_chain()["bundle"])
            b["candidate_manifest_sha256"] = "b" * 64
            b["bundle_hash"] = bundle_hash_of(b)
            return b
        cert = Harness(bundle=drifted).run()
        self.assertEqual(cert.verdict, INFRA_INCOMPLETE)
        self.assertTrue(any("fingerprint drift across the lifecycle"
                            in c[2] for c in cert.checks))

    def test_19_manifest_drift_in_activation_refused(self):
        def drifted():
            r = dict(the_chain()["activation"])
            r["manifest_sha256"] = "c" * 64
            r["activation_digest"] = recompute_digest(r)
            return r
        cert = Harness(activation_record=drifted).run()
        self.assertEqual(cert.verdict, INFRA_INCOMPLETE)
        self.assertTrue(any("fingerprint drift across the lifecycle"
                            in c[2] for c in cert.checks))

    def test_20_configuration_digest_drift_refused(self):
        def drifted():
            a = dict(the_chain()["acc"])
            a["acceptance_fingerprint"] = "d" * 64
            return a
        cert = Harness(acceptance_report=drifted).run()
        self.assertEqual(cert.verdict, INFRA_INCOMPLETE)
        self.assertTrue(any("configuration digest drift" in c[2]
                            for c in cert.checks))

    def test_21_probe_unbound_from_acceptance_refused(self):
        def unbound():
            p = dict(the_chain()["probe"])
            p["acceptance_fingerprint"] = "e" * 64
            p["probe_digest"] = recompute_digest(p)
            return p
        cert = Harness(probe_report=unbound).run()
        self.assertEqual(cert.verdict, INFRA_INCOMPLETE)
        self.assertTrue(any("not bound to THIS acceptance report"
                            in c[2] for c in cert.checks))


# ===================================================================
# DEP-03 — D-112 anchoring
# ===================================================================

class TestDep03Chain(unittest.TestCase):

    def test_22_broken_chain_refused(self):
        cert = Harness(chain_verifier=lambda: {
            "ok": False, "broken_at_seq": 4,
            "reason": "chain_mismatch"}).run()
        self.assertEqual(cert.verdict, INFRA_INCOMPLETE)
        self.assertTrue(any("BROKEN at seq 4" in c[2]
                            for c in cert.checks))

    def test_23_unrooted_closure_refused(self):
        cert = Harness(audit_rows=lambda: [
            r for r in the_chain()["ledger"]
            if r["event_kind"] != "stage_g_closure"]).run()
        self.assertEqual(cert.verdict, INFRA_INCOMPLETE)
        self.assertTrue(any("stage_g_closure missing from the D-112"
                            in c[2] for c in cert.checks))

    def test_24_unrooted_activation_refused(self):
        cert = Harness(audit_rows=lambda: [
            r for r in the_chain()["ledger"]
            if r["event_kind"] != "stage_h_activation"]).run()
        self.assertEqual(cert.verdict, INFRA_INCOMPLETE)
        self.assertTrue(any("stage_h_activation missing" in c[2]
                            for c in cert.checks))

    def test_25_empty_ledger_refused(self):
        cert = Harness(audit_rows=lambda: [],
                       chain_verifier=lambda: {"ok": True,
                                               "rows": 0}).run()
        self.assertEqual(cert.verdict, INFRA_INCOMPLETE)
        self.assertTrue(any("carries no rows" in c[2]
                            for c in cert.checks))

    def test_26_missing_verifier_fails_closed(self):
        cert = Harness(chain_verifier=None).run()
        self.assertEqual(cert.verdict, INFRA_INCOMPLETE)
        self.assertTrue(any("chain verifier absent" in c[2]
                            for c in cert.checks))


# ===================================================================
# DEP-04 — Live-Wiring readiness (Phases 5–18)
# ===================================================================

class TestDep04LiveWiring(unittest.TestCase):

    def test_27_missing_readiness_refused(self):
        cert = Harness(live_wiring_readiness=None).run()
        self.assertEqual(cert.verdict, INFRA_INCOMPLETE)
        self.assertTrue(any("Live-Wiring readiness absent" in c[2]
                            for c in cert.checks))

    def test_28_phase_not_wired_refused(self):
        def unwired():
            lw = real_readiness()
            lw["phases"][7]["wired"] = False  # Phase 12 Payment
            return lw
        cert = Harness(live_wiring_readiness=unwired).run()
        self.assertEqual(cert.verdict, INFRA_INCOMPLETE)
        self.assertTrue(any("not ready" in c[2] and "phase 12" in c[2]
                            for c in cert.checks))

    def test_29_phase_absent_from_census_refused(self):
        def missing():
            lw = real_readiness()
            lw["phases"] = lw["phases"][:-1]  # Phase 18 gone
            return lw
        cert = Harness(live_wiring_readiness=missing).run()
        self.assertEqual(cert.verdict, INFRA_INCOMPLETE)
        self.assertTrue(any("absent from the readiness census"
                            in c[2] for c in cert.checks))

    def test_30_unverified_runtime_profile_refused(self):
        def unverified():
            lw = real_readiness()
            lw["runtime_profile_verified"] = False
            return lw
        cert = Harness(live_wiring_readiness=unverified).run()
        self.assertEqual(cert.verdict, INFRA_INCOMPLETE)
        self.assertTrue(any("runtime profile not verified" in c[2]
                            for c in cert.checks))

    def test_31_census_covers_phases_5_to_18(self):
        self.assertEqual([p for p, _ in LIVE_WIRING_PHASES],
                         list(range(5, 19)))


# ===================================================================
# DEP-05 — the certificate artifact
# ===================================================================

class TestDep05Certificate(unittest.TestCase):

    def test_32_refusal_emits_incomplete_certificate(self):
        h = Harness(activation_record=None)
        cert = h.run()
        self.assertEqual(cert.verdict, INFRA_INCOMPLETE)
        self.assertEqual(len(h.sink), 1)
        self.assertEqual(h.sink[-1]["schema"], ATTESTATION_SCHEMA)
        self.assertTrue(any("INFRASTRUCTURE_INCOMPLETE" in c[2]
                            for c in cert.checks))

    def test_33_record_frozen_and_digest_bound(self):
        cert = Harness().run()
        d = cert.to_dict()
        before = cert.attestation_digest
        d["verdict"] = "MUTATED"
        self.assertEqual(cert.attestation_digest, before)
        self.assertEqual(json.loads(json.dumps(cert.to_dict()))
                         ["verdict"], INFRA_COMPLETE)


# ===================================================================
# REDACT — no secrets in certificate or audit outputs
# ===================================================================

class TestRedaction(unittest.TestCase):

    def test_34_no_key_or_canary_in_outputs(self):
        def leaky_readiness():
            lw = real_readiness()
            lw["phases"][0]["detail"] = (
                f"ready {SIGNING_KEY} {CANARY}")
            return lw
        h = Harness(live_wiring_readiness=leaky_readiness)
        cert = h.run()
        blob = json.dumps(cert.to_dict())
        audit = json.dumps(h.sink)
        for secret in (SIGNING_KEY, CANARY):
            self.assertNotIn(secret, blob)
            self.assertNotIn(secret, audit)

    def test_35_public_commitments_survive_redaction(self):
        h = Harness()
        cert = h.run()
        audit = h.sink[-1]
        for field, want in (("manifest_sha256", FP),
                            ("bundle_hash",
                             cert.to_dict()["bundle_hash"]),
                            ("closure_digest",
                             h.seal["closure_digest"]),
                            ("activation_digest",
                             h.activation["activation_digest"])):
            self.assertEqual(audit[field], want)


# ===================================================================
# AST — pure core, zero external surface
# ===================================================================

class TestAst(unittest.TestCase):

    def test_36_core_pure_no_io_or_network(self):
        tree = ast.parse(ENGINE.read_text(encoding="utf-8"))
        banned = {"socket", "urllib", "requests", "ssl", "http",
                  "subprocess", "os", "asyncio"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    self.assertNotIn(
                        a.name.split(".")[0], banned,
                        f"banned import: {a.name}")
            elif isinstance(node, ast.ImportFrom):
                root = (node.module or "").split(".")[0]
                self.assertNotIn(root, banned,
                                 f"banned import-from: {node.module}")
            if isinstance(node, ast.Call):
                fn = node.func
                if isinstance(fn, ast.Attribute) and \
                        fn.attr in ("system", "popen", "Popen",
                                    "connect", "urlopen"):
                    self.fail(f"banned call: .{fn.attr}()")

    def test_37_no_shell_or_spawn_anywhere(self):
        tree = ast.parse(ENGINE.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and node.arg == "shell":
                self.fail("shell= keyword present")
            if isinstance(node, ast.Call) and \
                    isinstance(node.func, ast.Attribute) and \
                    node.func.attr == "run":
                self.fail(".run() spawn-style call in the pure core")

    def test_38_doc_and_engine_carry_the_contract(self):
        text = ENGINE.read_text(encoding="utf-8")
        for token in ("DEP-01", "DEP-02", "DEP-03", "DEP-04",
                      "DEP-05", ATTESTATION_SCHEMA,
                      "INFRASTRUCTURE_COMPLETE", "deep_redact",
                      "injected", "D-112", "D-124", "Live Wiring",
                      "service ignition"):
            self.assertIn(token, text)


if __name__ == "__main__":
    unittest.main()

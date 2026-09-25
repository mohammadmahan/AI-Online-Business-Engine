"""Stage H cutover executor battery (D-153, offline).

Exercises `local/scripts/stage_h_cutover_executor.py` fully offline —
every provider injected, every artifact REAL repo material (the D-152
seal synthesized from the Stage D manifest/envelope + the genuine
D-147/D-149/D-150/D-151 chains, the Stage F token minted and verified
through the REAL `owner_approval_gate`):

  PASS     — aligned seal + fresh unspent token + healthy target ⇒
             CUTOVER_EXECUTED with a valid immutable
             `stage_h_activation_record.v1`;
  H-01     — missing / OPEN / altered / unrooted seal ⇒ immediate
             refusal, zero side-effects;
  H-02     — stale / invalid / replayed / divergently-bound token ⇒
             immediate refusal;
  H-03     — down services, restart loops, unmapped ports ⇒ refusal;
  H-04     — failed/unconfirmed transition ⇒ abort, no record lie;
  H-05     — critical-window anomaly ⇒ ROLLBACK_ARMED with the RB-1
             payload (engine never executes it);
  REDACT   — signing key, nonce and canaries never reach records or
             audit copies;
  AST      — adapter uses direct argv only (no shell keywords, no
             Popen/system), bounded timeouts; executor core pure.
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
    STAGE_G_CLOSED, StageGClosureRunner, canonical_hash,
)
from stage_h_cutover_executor import (  # noqa: E402
    CRITICAL_WINDOW_TICKS, CUTOVER_ABORTED, CUTOVER_EXECUTED,
    DokployStateAdapter, RECORD_SCHEMA, ROLLBACK_ARMED,
    StageHCutoverExecutor,
)
from src.security.launch_attestation_verifier import (  # noqa: E402
    TripleEvidenceGate,
)
from src.security.owner_approval_gate import (  # noqa: E402
    OwnerApprovalGate, TokenDraft, mint_token,
    parse_envelope_fingerprint,
)

ENGINE = SCRIPTS / "stage_h_cutover_executor.py"
DOC = (REPO / "docs" / "deployment" /
       "stage-h-cutover-runbook.md").read_text(encoding="utf-8")

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


# --- the real Stage C→G chain (same discipline as D-152) --------------

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


def audit_rows_for(bundle, acceptance, probe, extra=None):
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
    return rows + list(extra or [])


def real_triad(bundle, acceptance, probe) -> dict:
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
         "action": "re-attest (closure refused)"},
        {"name": "chain_broken", "threshold_ticks": 1,
         "action": "RB-4 freeze dispatch, reconcile"},
    ]}


def real_seal(closure_rows: list) -> dict:
    """Run the REAL D-152 closure runner and return the seal dict."""
    bundle, acc, probe = real_bundle(), real_acceptance(), \
        real_probe_report()
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
        triad_verdict=lambda: real_triad(bundle, acc, probe))
    seal = runner.run()
    assert seal.closed
    d = seal.to_dict()
    d["closure_digest"] = seal.closure_digest
    # the closure row must be in the chain for H-01 rooting
    closure_rows.append({"event_kind": "stage_g_closure",
                         "detail": {"closure_digest":
                                    d["closure_digest"]}})
    return d


def real_target_state() -> dict:
    return {s: {"running": True, "healthy": True, "restarts": 0,
                "ports": []} for s in SERVICES}


def real_probes() -> dict:
    return {"edge_smoke": True, "worker_ready": True, "ssot_rw": True}


def real_draft(now: int) -> TokenDraft:
    return TokenDraft(manifest_sha256=FP, session_id=SESSION,
                      target_env=TARGET, issued_tick=now - 10,
                      expires_tick=now + 500,
                      nonce=f"h-cutover-{now}")


def real_approval(rows: list, now: int) -> dict:
    """Run the REAL Stage F gate (mints + evaluates + burns once)."""
    draft = real_draft(now)
    token = mint_token(SIGNING_KEY, draft)
    gate = OwnerApprovalGate(
        signing_key=SIGNING_KEY,
        replay_store=MemoryReplayStore(),
        clock=lambda: now,
        audit_sink=lambda d: rows.append(d),
        manifest_sha256=FP)
    verdict = gate.evaluate(token, draft, SESSION, TARGET, ENVELOPE)
    assert verdict.gate == "GO"
    return {"verdict": verdict.to_dict(), "draft": draft,
            "token": token}


class MemoryReplayStore:
    def __init__(self):
        self.burned = set()

    def consume(self, key: str) -> bool:
        if key in self.burned:
            return False
        self.burned.add(key)
        return True


class Harness:
    """Wired executor with the real chain; overrides swap providers."""

    def __init__(self, now: int = 1000, **overrides):
        self.now = now
        self.sink: list = []
        self.closure_rows: list = []
        self.approval = real_approval(self.closure_rows, now)
        self.seal = real_seal(self.closure_rows)
        providers = {
            "seal_provider": lambda: self.seal,
            "audit_rows": lambda: self.closure_rows,
            "approval_verdict": lambda: self.approval["verdict"],
            "token_draft": lambda: vars(self.approval["draft"]),
            "target_state": real_target_state,
            "transition": lambda: {"active": True, "via": "dokploy"},
            "post_activation_probes": real_probes,
        }
        providers.update(overrides)
        self.executor = StageHCutoverExecutor(
            clock=lambda: self.now, audit_sink=self.sink.append,
            **providers)

    def run(self):
        return self.executor.run()


# ===================================================================
# PASS — the successful cutover
# ===================================================================

class TestCutoverPass(unittest.TestCase):

    def test_01_aligned_seal_and_token_execute(self):
        h = Harness()
        rec = h.run()
        self.assertEqual(rec.verdict, CUTOVER_EXECUTED)
        d = rec.to_dict()
        self.assertEqual(d["schema"], RECORD_SCHEMA)
        self.assertEqual(d["schema"], "stage_h_activation_record.v1")
        self.assertEqual(d["manifest_sha256"], FP)
        self.assertEqual(d["closure_digest"],
                         h.seal["closure_digest"])
        self.assertEqual(rec.activation_digest, canonical_hash(d))
        ids = [c[0] for c in rec.checks]
        self.assertEqual(ids, ["H-01", "H-02", "H-03", "H-03",
                               "H-04", "H-05"])
        self.assertTrue(all(c[1] for c in rec.checks))

    def test_02_record_immutable_and_deterministic(self):
        a = Harness(now=2000)
        r1 = a.run()
        b = Harness(now=2000)
        r2 = b.run()
        self.assertEqual(r1.activation_digest, r2.activation_digest)
        self.assertEqual(a.sink[-1]["closure_digest"],
                         a.seal["closure_digest"])
        self.assertEqual(a.sink[-1]["token_id"],
                         r1.to_dict()["token_id"])

    def test_03_exactly_one_audited_record_per_run(self):
        h = Harness()
        h.run()
        self.assertEqual(len(h.sink), 1)
        h.run()
        self.assertEqual(len(h.sink), 2)


# ===================================================================
# H-01 — the closure seal
# ===================================================================

class TestH01Seal(unittest.TestCase):

    def test_04_missing_seal_refused(self):
        rec = Harness(seal_provider=None).run()
        self.assertEqual(rec.verdict, CUTOVER_ABORTED)
        self.assertTrue(any("closure seal absent" in c[2]
                            for c in rec.checks))

    def test_05_open_seal_refused(self):
        def open_seal():
            s = dict(real_seal([]))
            s["verdict"] = "STAGE_G_OPEN"
            s["closure_digest"] = canonical_hash(
                {k: v for k, v in s.items() if k != "closure_digest"})
            return s
        rec = Harness(seal_provider=open_seal).run()
        self.assertEqual(rec.verdict, CUTOVER_ABORTED)
        self.assertTrue(any("Stage G is OPEN" in c[2]
                            for c in rec.checks))

    def test_06_altered_seal_refused(self):
        def altered():
            s = dict(real_seal([]))
            # tamper a field AFTER the digest was recorded — verdict
            # stays CLOSED so the digest-recomputation path fires
            s["observed_tick"] = s["observed_tick"] + 1
            return s
        rec = Harness(seal_provider=altered).run()
        self.assertEqual(rec.verdict, CUTOVER_ABORTED)
        self.assertTrue(any("ALTERED" in c[2] for c in rec.checks))

    def test_07_unrooted_seal_refused(self):
        rec = Harness(audit_rows=lambda: []).run()
        self.assertEqual(rec.verdict, CUTOVER_ABORTED)
        self.assertTrue(any("not rooted in the D-112" in c[2]
                            for c in rec.checks))

    def test_08_refusal_has_zero_side_effects(self):
        h = Harness(seal_provider=None,
                    transition=lambda: {"active": True})
        rec = h.run()
        self.assertEqual(rec.verdict, CUTOVER_ABORTED)
        # the transition provider was NEVER invoked
        self.assertEqual(len(h.sink), 1)  # only the abort record
        self.assertFalse(any(c[0] == "H-04" for c in rec.checks))


# ===================================================================
# H-02 — the owner token
# ===================================================================

class TestH02Token(unittest.TestCase):

    def test_09_stale_token_refused(self):
        def stale():
            return {"gate": "NO_GO", "reason": "token_expired",
                    "token_id": "0123456789abcdef",
                    "manifest_sha256": FP,
                    "detail": "expired", "findings": []}
        rec = Harness(approval_verdict=stale).run()
        self.assertEqual(rec.verdict, CUTOVER_ABORTED)
        self.assertTrue(any("!= 'GO'" in c[2] for c in rec.checks))
        self.assertTrue(any("stale" in c[2] for c in rec.checks))

    def test_10_window_not_covering_activation_refused(self):
        def short_draft():
            d = dict(vars(real_draft(1000)))
            d["issued_tick"] = 0
            d["expires_tick"] = 500  # activation at 1000 is outside
            return d
        rec = Harness(token_draft=short_draft).run()
        self.assertEqual(rec.verdict, CUTOVER_ABORTED)
        self.assertTrue(any("does not cover the activation tick" in c[2]
                            for c in rec.checks))

    def test_11_divergent_fingerprint_refused(self):
        def divergent_draft():
            d = dict(vars(real_draft(1000)))
            d["manifest_sha256"] = "b" * 64
            return d
        rec = Harness(token_draft=divergent_draft).run()
        self.assertEqual(rec.verdict, CUTOVER_ABORTED)
        self.assertTrue(any("DIFFERENT deployment" in c[2]
                            for c in rec.checks))

    def test_12_absent_verdict_refused(self):
        rec = Harness(approval_verdict=None).run()
        self.assertEqual(rec.verdict, CUTOVER_ABORTED)
        self.assertTrue(any("owner approval verdict absent" in c[2]
                            for c in rec.checks))

    def test_13_replay_through_the_real_gate_refused(self):
        """The real gate burns the nonce at GO; a second evaluate is
        a replay arriving as NO_GO — the executor must refuse."""
        rows: list = []
        draft = real_draft(1000)
        token = mint_token(SIGNING_KEY, draft)
        store = MemoryReplayStore()
        gate = OwnerApprovalGate(signing_key=SIGNING_KEY,
                                 replay_store=store, clock=lambda: 1000,
                                 audit_sink=lambda d: rows.append(d),
                                 manifest_sha256=FP)
        first = gate.evaluate(token, draft, SESSION, TARGET, ENVELOPE)
        self.assertEqual(first.gate, "GO")
        replay = gate.evaluate(token, draft, SESSION, TARGET,
                               ENVELOPE)
        self.assertEqual(replay.gate, "NO_GO")
        h = Harness(now=1000,
                    approval_verdict=lambda: replay.to_dict(),
                    token_draft=lambda: vars(draft))
        rec = h.run()
        self.assertEqual(rec.verdict, CUTOVER_ABORTED)
        self.assertTrue(any("stale, spent" in c[2] for c in rec.checks))


# ===================================================================
# H-03/H-04 — environment + transition
# ===================================================================

class TestH03H04(unittest.TestCase):

    def test_14_down_service_refused(self):
        def degraded():
            st = real_target_state()
            st["redis"]["healthy"] = False
            return st
        rec = Harness(target_state=degraded).run()
        self.assertEqual(rec.verdict, CUTOVER_ABORTED)
        self.assertTrue(any("target state unhealthy" in c[2]
                            for c in rec.checks))

    def test_15_unmapped_port_exposure_refused(self):
        def exposed():
            st = real_target_state()
            st["postgres-ssot"]["ports"] = ["0.0.0.0:55432:5432/tcp"]
            return st
        rec = Harness(target_state=exposed).run()
        self.assertEqual(rec.verdict, CUTOVER_ABORTED)
        self.assertTrue(any("unmapped port exposure" in c[2]
                            for c in rec.checks))

    def test_16_failed_transition_aborts_without_a_lie(self):
        rec = Harness(transition=lambda: {"active": False}).run()
        self.assertEqual(rec.verdict, CUTOVER_ABORTED)
        self.assertTrue(any("transition failed or unconfirmed" in c[2]
                            for c in rec.checks))
        self.assertFalse(any(c[0] == "H-05" for c in rec.checks))

    def test_17_transition_exception_aborts(self):
        def boom():
            raise RuntimeError("dokploy api down")
        rec = Harness(transition=boom).run()
        self.assertEqual(rec.verdict, CUTOVER_ABORTED)
        self.assertTrue(any("provider failure: RuntimeError" in c[2]
                            for c in rec.checks))


# ===================================================================
# H-05 — the critical window & the rollback payload
# ===================================================================

class TestH05Rollback(unittest.TestCase):

    def test_18_probe_failure_arms_the_rollback_payload(self):
        def flapping():
            return {"edge_smoke": True, "worker_ready": False,
                    "ssot_rw": True}
        h = Harness(post_activation_probes=flapping)
        rec = h.run()
        self.assertEqual(rec.verdict, ROLLBACK_ARMED)
        ids = [c[0] for c in rec.checks]
        self.assertIn("ROLLBACK", ids)
        rb = next(c for c in rec.checks if c[0] == "ROLLBACK")
        self.assertIn("RB-1", rb[2])
        self.assertIn("operator executes", rb[2])

    def test_19_payload_shape_is_the_rb1_contract(self):
        p = StageHCutoverExecutor.rollback_payload(
            "probe failure", "d" * 64, ["worker_ready"], 4242)
        self.assertEqual(p["schema"], "stage_h_rollback_payload.v1")
        self.assertEqual(p["row"], "RB-1")
        self.assertEqual(p["closure_digest"], "d" * 64)
        self.assertIn("stop new work first", p["ordering"])
        self.assertIn("edge gateway back to blue", p["procedure"])
        self.assertEqual(p["failed_probes"], ["worker_ready"])
        self.assertEqual(p["observed_tick"], 4242)

    def test_20_unwatchable_window_arms_rollback(self):
        """After the transition, an unwatchable window is NOT an
        abort (the state change already happened) — it arms the
        rollback payload: fail-closed, never a silent pass."""
        rec = Harness(post_activation_probes=None).run()
        self.assertEqual(rec.verdict, ROLLBACK_ARMED)
        self.assertTrue(any("unwatchable, fail closed" in c[2]
                            for c in rec.checks))
        self.assertTrue(any(c[0] == "ROLLBACK" for c in rec.checks))


# ===================================================================
# REDACT — key, nonce and canaries never escape
# ===================================================================

class TestRedaction(unittest.TestCase):

    def test_21_no_key_nonce_or_canary_in_records_or_audit(self):
        def leaky_probes():
            return {"edge_smoke": f"ok {SIGNING_KEY} {CANARY}",
                    "worker_ready": False}
        h = Harness(post_activation_probes=leaky_probes,
                    transition=lambda: {"active": True})
        rec = h.run()
        blob = json.dumps(rec.to_dict())
        audit = json.dumps(h.sink)
        for secret in (SIGNING_KEY, CANARY,
                       h.approval["draft"].nonce):
            self.assertNotIn(secret, blob)
            self.assertNotIn(secret, audit)
        # public commitments survive in the audit copy
        self.assertEqual(h.sink[-1]["closure_digest"],
                         h.seal["closure_digest"])
        self.assertEqual(h.sink[-1]["manifest_sha256"], FP)

    def test_22_adapter_error_text_is_redacted(self):
        def noisy(argv):
            return subprocess.CompletedProcess(
                [], 1, "", f"auth failed {CANARY} at host x")
        ad = DokployStateAdapter(runner=noisy)
        with self.assertRaises(Exception) as ctx:
            ad.target_state()
        self.assertNotIn(CANARY, str(ctx.exception))


# ===================================================================
# AST — argv isolation, zero shell, pure core
# ===================================================================

class TestAst(unittest.TestCase):

    def test_23_adapter_direct_argv_only(self):
        tree = ast.parse(ENGINE.read_text(encoding="utf-8"))
        shell_strings = 0
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and node.arg == "shell":
                self.fail("shell= keyword present")
            if isinstance(node, ast.Call):
                fn = node.func
                if isinstance(fn, ast.Attribute) and \
                        fn.attr in ("system", "popen", "Popen"):
                    self.fail(f"banned process call: .{fn.attr}()")
                if isinstance(fn, ast.Attribute) and \
                        fn.attr == "run" and \
                        isinstance(fn.value, ast.Name) and \
                        fn.value.id == "subprocess":
                    kws = {k.arg for k in node.keywords}
                    self.assertIn("timeout", kws,
                                  "subprocess.run without timeout")
                    shell_strings += 1
        self.assertLessEqual(shell_strings, 2)

    def test_24_executor_core_is_pure(self):
        tree = ast.parse(ENGINE.read_text(encoding="utf-8"))
        # the core (StageHCutoverExecutor) must not import socket/urllib
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    self.assertNotIn(
                        a.name.split(".")[0],
                        {"socket", "urllib", "requests", "ssl", "http"},
                        f"banned import: {a.name}")
            elif isinstance(node, ast.ImportFrom):
                root = (node.module or "").split(".")[0]
                self.assertNotIn(
                    root, {"socket", "urllib", "requests", "ssl",
                           "http"},
                    f"banned import-from: {node.module}")

    def test_25_doc_covers_the_runbook_contract(self):
        for token in ("stage_h_activation_record.v1", "H-01", "H-02",
                      "H-03", "H-04", "H-05", "CUTOVER_ABORTED",
                      "ROLLBACK_ARMED", "stage_h_rollback_payload.v1",
                      "RB-1", "activation_digest", "mint_token",
                      "TokenDraft", "CRITICAL_WINDOW_TICKS",
                      "DokployStateAdapter", "D-139", "D-146", "D-152",
                      "zero side-effects", "OwnerApprovalGate"):
            self.assertIn(token, DOC)


if __name__ == "__main__":
    unittest.main()

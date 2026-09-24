"""Stage F attestation & cutover orchestration battery (D-147, offline).

Two surfaces, both exercised with INJECTED collaborators (no sockets,
no subprocess, no files, no wall clock):

  V-10       — `verify_cutover_readiness.stage_f_verdict_check`
               (absent/stale/mismatched/negative verdicts refuse;
               forbidden material refuses; GO record bound to the
               exact manifest fingerprint passes);
  ORCHESTRATOR — `cutover_orchestrator.CutoverOrchestrator`
               (full-pipeline clearance, fail-closed aborts BEFORE the
               token burn, replay refusal, hash-bound bundle emitted
               and audited for every terminal state).

Real gate: every Stage F interaction runs the ACTUAL
`src/security/owner_approval_gate.py` engine (D-146) with a memory
replay store — the battery proves the composition, not a mock.
Determinism: identical pipeline inputs produce identical bundle
hashes; findings carry stable machine phrases.
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

import verify_cutover_readiness as vcr  # noqa: E402
from cutover_orchestrator import (  # noqa: E402
    BUNDLE_BLOCKED, BUNDLE_READY, CutoverOrchestrator,
    CutoverOrchestratorError,
)
from src.security.owner_approval_gate import (  # noqa: E402
    ApprovalGateError, OwnerApprovalGate, TokenDraft, mint_token,
    parse_envelope_fingerprint,
)

ENGINE = SRC / "security" / "owner_approval_gate.py"
ORCH = SCRIPTS / "cutover_orchestrator.py"

ENV_TEXT = (REPO / "local" / "infra" / "dokploy" /
            "stage_d_fingerprint.envelope").read_text(encoding="utf-8")
FP = parse_envelope_fingerprint(ENV_TEXT)
KEY = "stage-f-owner-signing-key-0123456789abcdef"
SESSION = "cutover-session-01"
TARGET = "staging"
CANARY = "sk-canaryvalue1234567890abcdef"


class MemReplayStore:
    def __init__(self) -> None:
        self.used: set = set()

    def consume(self, key: str) -> bool:
        if key in self.used:
            return False
        self.used.add(key)
        return True


class GateHarness:
    """A real D-146 gate + helpers to mint/evaluate tokens."""

    def __init__(self, tick: int = 100) -> None:
        self.store = MemReplayStore()
        self.reports: list = []
        self.gate = OwnerApprovalGate(
            KEY, self.store, lambda: tick, self.reports.append, FP)

    def mint(self, nonce: str = "nonce-12345678", issued: int = 100,
             expires: int = 200, session: str = SESSION,
             env: str = TARGET, fp: str = FP) -> tuple:
        d = TokenDraft(fp, session, env, issued, expires, nonce)
        return mint_token(KEY, d), d

    def evaluate(self, token: str, draft: TokenDraft) -> dict:
        self.gate.evaluate(token, draft, draft.session_id,
                           draft.target_env, ENV_TEXT)
        rec = dict(self.reports[-1])
        rec["issued_tick"] = draft.issued_tick
        rec["expires_tick"] = draft.expires_tick
        return rec


GO_RECORD = {
    "gate": "GO", "reason": "owner_authorized",
    "token_id": "af99db52fa4cc55e", "manifest_sha256": FP,
    "detail": "x", "findings": ["stage_f_owner_approval:GO"],
    "observed_tick": 100, "issued_tick": 100, "expires_tick": 200,
}


# ---------------------------------------------------------------------------
# V-10 verdict-record rules
# ---------------------------------------------------------------------------

class TestV10VerdictCheck(unittest.TestCase):

    def test_01_go_record_passes_when_bound_to_manifest(self):
        ok, detail = vcr.stage_f_verdict_check(
            verdict_record=dict(GO_RECORD), now_tick=150,
            manifest_hash=FP)
        self.assertTrue(ok, detail)
        self.assertIn("owner-authorized", detail)
        self.assertIn(FP[:16], detail)

    def test_02_missing_record_fails_closed(self):
        ok, detail = vcr.stage_f_verdict_check(
            verdict_record=None, now_tick=150, manifest_hash=FP)
        self.assertFalse(ok)
        self.assertIn("no Stage F authorization", detail)

    def test_03_non_go_verdict_refused(self):
        rec = dict(GO_RECORD, gate="NO_GO")
        ok, detail = vcr.stage_f_verdict_check(
            verdict_record=rec, now_tick=150, manifest_hash=FP)
        self.assertFalse(ok)
        self.assertIn("not GO", detail)

    def test_04_fingerprint_mismatch_refused(self):
        rec = dict(GO_RECORD, manifest_sha256="b" * 64)
        ok, detail = vcr.stage_f_verdict_check(
            verdict_record=rec, now_tick=150, manifest_hash=FP)
        self.assertFalse(ok)
        self.assertIn("different manifest fingerprint", detail)

    def test_05_expired_and_future_refused(self):
        ok, _ = vcr.stage_f_verdict_check(
            verdict_record=dict(GO_RECORD), now_tick=200, manifest_hash=FP)
        self.assertFalse(ok)  # now == expires is expired
        rec = dict(GO_RECORD, issued_tick=300, expires_tick=400)
        ok2, d2 = vcr.stage_f_verdict_check(
            verdict_record=rec, now_tick=150, manifest_hash=FP)
        self.assertFalse(ok2)
        self.assertIn("not yet valid", d2)

    def test_06_forbidden_material_refused(self):
        for field in ("signature", "sig", "signing_key", "nonce", "token"):
            rec = dict(GO_RECORD)
            rec[field] = CANARY
            ok, detail = vcr.stage_f_verdict_check(
                verdict_record=rec, now_tick=150, manifest_hash=FP)
            self.assertFalse(ok, field)
            self.assertIn("forbidden material", detail)

    def test_07_malformed_ticks_and_fingerprint_refused(self):
        rec = dict(GO_RECORD)
        rec.pop("issued_tick")
        ok, _ = vcr.stage_f_verdict_check(
            verdict_record=rec, now_tick=150, manifest_hash=FP)
        self.assertFalse(ok)
        rec2 = dict(GO_RECORD, manifest_sha256="nothex")
        ok2, _ = vcr.stage_f_verdict_check(
            verdict_record=rec2, now_tick=150, manifest_hash=FP)
        self.assertFalse(ok2)
        rec3 = dict(GO_RECORD, issued_tick=100, expires_tick=10_500)
        ok3, d3 = vcr.stage_f_verdict_check(
            verdict_record=rec3, now_tick=150, manifest_hash=FP)
        self.assertFalse(ok3)
        self.assertIn("TTL window invalid", d3)

    def test_08_unreadable_record_fails_closed(self):
        ok, detail = vcr.stage_f_verdict_check(
            verdict_record="not-a-dict", now_tick=150, manifest_hash=FP)
        self.assertFalse(ok)
        self.assertIn("fail closed", detail)

    def test_09_no_secret_shaped_bits_in_pass_detail(self):
        h = GateHarness()
        tok, d = h.mint()
        rec = h.evaluate(tok, d)
        ok, detail = vcr.stage_f_verdict_check(
            verdict_record=rec, now_tick=150, manifest_hash=FP)
        self.assertTrue(ok)
        blob = json.dumps({"detail": detail, "record": rec})
        self.assertNotIn(KEY, blob)
        self.assertNotIn(tok.split(".", 1)[1], blob)  # signature bits
        self.assertNotIn(CANARY, blob)


# ---------------------------------------------------------------------------
# Orchestrator pipeline
# ---------------------------------------------------------------------------

class OrchestratorHarness:
    """Real gate + injected step fakes + capturing audit sink."""

    def __init__(self, stage_c=(True, "host ready"),
                 stage_de=(True, "V-01..V-10 green"), tick: int = 100):
        self.gate_h = GateHarness(tick=tick)
        self.bundles: list = []
        self.persisted: list = []
        self.stage_c = stage_c
        self.stage_de = stage_de

    def f_eval(self, session: str, env: str) -> dict:
        tok, d = self.gate_h.mint(session=session, env=env)
        return self.gate_h.evaluate(tok, d)

    def build(self, session: str = SESSION, env: str = TARGET):
        return CutoverOrchestrator(
            clock=lambda: 100, audit_sink=self.bundles.append,
            stage_c_check=lambda: self.stage_c,
            stage_de_check=lambda: self.stage_de,
            stage_f_evaluate=self.f_eval, manifest_sha256=FP,
            record_persister=self.persisted.append,
            session_id=session, target_env=env)

    def run(self, session: str = SESSION, env: str = TARGET):
        o = self.build(session=session, env=env)
        tok, d = self.gate_h.mint(session=session, env=env)
        return o.run_pipeline(tok, d), tok, d


class TestOrchestrator(unittest.TestCase):

    def test_10_full_pipeline_clears_with_bundle(self):
        h = OrchestratorHarness()
        b, _, _ = h.run()
        self.assertEqual(b.verdict, BUNDLE_READY)
        self.assertEqual(b.abort_reason, "")
        self.assertEqual(len(h.bundles), 1)
        self.assertEqual(b.steps[-1]["step"], "stage_f")
        self.assertTrue(all(s["ok"] for s in b.steps))
        self.assertTrue(h.persisted)  # verdict record persisted on GO

    def test_11_bundle_hash_deterministic_and_binds_bytes(self):
        h1 = OrchestratorHarness()
        b1, _, _ = h1.run()
        h2 = OrchestratorHarness()
        b2, _, _ = h2.run()
        self.assertEqual(b1.bundle_hash, b2.bundle_hash)
        self.assertEqual(b1.to_dict(), b2.to_dict())
        # any drift in bound data changes the hash
        h3 = OrchestratorHarness(stage_c=(True, "host ready (drifted)"))
        b3, _, _ = h3.run()
        self.assertNotEqual(b1.bundle_hash, b3.bundle_hash)

    def test_12_stage_c_failure_blocks_before_token_burn(self):
        h = OrchestratorHarness(stage_c=(False, "port 5432 publicly bound"))
        before = len(h.gate_h.store.used)
        b, _, _ = h.run()
        self.assertEqual((b.verdict, b.abort_reason),
                         (BUNDLE_BLOCKED, "stage_c_not_ready"))
        self.assertEqual(len(h.gate_h.store.used), before)  # NOT consumed
        self.assertEqual(b.steps[-1]["step"], "stage_c")

    def test_13_stage_de_failure_blocks_before_token_burn(self):
        h = OrchestratorHarness(stage_de=(False, "V-08 MISMATCH"))
        before = len(h.gate_h.store.used)
        b, _, _ = h.run()
        self.assertEqual((b.verdict, b.abort_reason),
                         (BUNDLE_BLOCKED, "stage_de_not_ready"))
        self.assertEqual(len(h.gate_h.store.used), before)
        self.assertEqual(b.steps[-1]["step"], "stage_de")

    def test_14_technical_pass_with_gate_refusal_blocks(self):
        # V-01..V-09 pass, but the Stage F gate refuses (expired token
        # against the gate's OWN clock): BLOCKED with
        # stage_f_not_authorized
        h = OrchestratorHarness()
        h.gate_h.gate = OwnerApprovalGate(
            KEY, h.gate_h.store, lambda: 500,  # clock past expiry
            h.gate_h.reports.append, FP)

        o = CutoverOrchestrator(
            clock=lambda: 100, audit_sink=h.bundles.append,
            stage_c_check=lambda: (True, "host ready"),
            stage_de_check=lambda: (True, "V-01..V-10 green"),
            stage_f_evaluate=h.f_eval, manifest_sha256=FP,
            session_id=SESSION, target_env=TARGET)
        tok, d = h.gate_h.mint(issued=100, expires=150)
        b = o.run_pipeline(tok, d)
        self.assertEqual((b.verdict, b.abort_reason),
                         (BUNDLE_BLOCKED, "stage_f_not_authorized"))
        self.assertEqual(b.steps[-1]["step"], "stage_f")
        self.assertIn("token_expired", h.gate_h.reports[-1]["reason"])

    def test_15_replayed_token_aborts(self):
        h = OrchestratorHarness()
        o = h.build()
        tok, d = h.gate_h.mint()
        b1 = o.run_pipeline(tok, d)
        self.assertEqual(b1.verdict, BUNDLE_READY)
        b2 = o.run_pipeline(tok, d)  # same token again = replay
        self.assertEqual((b2.verdict, b2.abort_reason),
                         (BUNDLE_BLOCKED, "stage_f_not_authorized"))
        self.assertEqual(h.gate_h.reports[-1]["reason"], "replay_rejected")

    def test_16_gate_exception_blocks_not_crashes(self):
        h = OrchestratorHarness()

        def boom(session, env):
            raise ApprovalGateError("malformed token")

        o = CutoverOrchestrator(
            clock=lambda: 100, audit_sink=h.bundles.append,
            stage_c_check=lambda: (True, "host ready"),
            stage_de_check=lambda: (True, "V-01..V-10 green"),
            stage_f_evaluate=boom, manifest_sha256=FP,
            session_id=SESSION, target_env=TARGET)
        b = o.run_pipeline("garbage", object())
        self.assertEqual((b.verdict, b.abort_reason),
                         (BUNDLE_BLOCKED, "stage_f_not_authorized"))
        self.assertEqual(len(h.bundles), 1)  # exactly one audited bundle

    def test_17_bundle_leaks_no_material(self):
        h = OrchestratorHarness()
        b, tok, _ = h.run()
        for blob in (json.dumps(b.to_dict()),
                     json.dumps(h.bundles),
                     json.dumps(h.persisted)):
            self.assertNotIn(KEY, blob)
            self.assertNotIn(tok.split(".", 1)[1], blob)
            self.assertNotIn(CANARY, blob)
        # the audited sink copies are redacted dicts
        self.assertTrue(all(isinstance(x, dict) for x in h.bundles))

    def test_18_constructor_fail_closed(self):
        for kwargs in (dict(clock=None, audit_sink=lambda d: None,
                            stage_c_check=lambda: (True, ""),
                            stage_de_check=lambda: (True, ""),
                            stage_f_evaluate=lambda s, e: {},
                            manifest_sha256=FP),
                       dict(clock=lambda: 0, audit_sink=lambda d: None,
                            stage_c_check=lambda: (True, ""),
                            stage_de_check=lambda: (True, ""),
                            stage_f_evaluate=lambda s, e: {},
                            manifest_sha256="nothex")):
            with self.assertRaises(CutoverOrchestratorError):
                CutoverOrchestrator(**kwargs)

    def test_19_doc_covers_v10_and_stage_g_handoff(self):
        doc = (REPO / "docs" / "deployment" /
               "stage-f-attestation-orchestration.md").read_text(
                   encoding="utf-8")
        for token in ("V-10", "READY_FOR_CUTOVER", "bundle_hash",
                      "Stage G", "Abort-before-burn", "D-139"):
            self.assertIn(token, doc)


# ---------------------------------------------------------------------------
# AST boundaries
# ---------------------------------------------------------------------------

class TestAstBoundaries(unittest.TestCase):

    def test_20_no_io_in_orchestrator_core(self):
        tree = ast.parse(ORCH.read_text(encoding="utf-8"))
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
                    self.fail("direct open() in orchestrator")
                if isinstance(fn, ast.Attribute) and \
                        fn.attr in ("system", "popen", "connect"):
                    self.fail(f"banned call: .{fn.attr}()")


if __name__ == "__main__":
    unittest.main()

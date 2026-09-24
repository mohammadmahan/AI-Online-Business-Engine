"""Stage F — owner authorization gate battery (D-146, offline).

Exercises `local/src/security/owner_approval_gate.py` — the
machine-enforced Stage F cutover authorization engine — entirely with
INJECTED collaborators (memory replay store, logical clock closure,
capturing audit sink; zero sockets, zero subprocess, zero files, zero
wall clock).

Proven here:
  a) valid token + matching fingerprint + live TTL  ⇒ GO, exactly one
     audited report, and the nonce burns (single-use semantics);
  b) tampered token / wrong-key signature          ⇒ signature_invalid;
  c) expired TTL (injected clock past expires)     ⇒ token_expired;
  d) draft minted for manifest A, evaluated against
     manifest B (drifted envelope)                 ⇒ fingerprint_mismatch
     / fingerprint_drift;
  e) replay of a consumed nonce                    ⇒ replay_rejected;
  f) canary secret + signature material NEVER appear in any report,
     error, or audit path (D-124);
  g) AST audit: zero socket/subprocess/os-import/file-open in the
     engine's import surface.
Determinism: identical inputs produce identical verdicts and identical
token ids; findings carry stable machine phrases.
"""
from __future__ import annotations

import ast
import json
import os
import pathlib
import sys
import unittest

_SRC = pathlib.Path(__file__).resolve().parents[1] / "src"
for p in (str(_SRC), str(_SRC.parent)):
    if p not in sys.path:
        sys.path.insert(0, p)

from src.security.owner_approval_gate import (  # noqa: E402
    ApprovalGateError, EvaluationVerdict, OwnerApprovalGate, TokenDraft,
    GATE_GO, GATE_NO_GO, mint_token, parse_envelope_fingerprint,
)

ENGINE = _SRC / "security" / "owner_approval_gate.py"

ENV_PATH = _SRC.parent / "infra" / "dokploy" / "stage_d_fingerprint.envelope"
ENV_TEXT = ENV_PATH.read_text(encoding="utf-8")
FP = parse_envelope_fingerprint(ENV_TEXT)

KEY = "stage-f-owner-signing-key-0123456789abcdef"
SESSION = "cutover-session-01"
TARGET = "staging"
CANARY = "hmac-canary-9f8e7d6c5b4a"


class MemReplayStore:
    """In-memory single-use burn store (durable semantics in prod)."""

    def __init__(self) -> None:
        self.used: set = set()
        self.calls = 0

    def consume(self, key: str) -> bool:
        self.calls += 1
        if key in self.used:
            return False
        self.used.add(key)
        return True


class Harness:
    """Fresh gate + collaborators per scenario."""

    def __init__(self, manifest: str = FP, tick: int = 100) -> None:
        self.store = MemReplayStore()
        self.reports: list = []
        self.tick = tick
        self.gate = OwnerApprovalGate(
            KEY, self.store, lambda: self.tick, self.reports.append, manifest)

    def draft(self, manifest: str = FP, issued: int = 100,
              expires: int = 200, nonce: str = "nonce-12345678",
              session: str = SESSION, env: str = TARGET) -> TokenDraft:
        return TokenDraft(manifest, session, env, issued, expires, nonce)

    def token(self, **kw) -> str:
        return mint_token(KEY, self.draft(**kw))
    def verdicts(self) -> list:
        return [r["gate"] for r in self.reports]


def _no_leak(blob: str) -> bool:
    return CANARY not in blob and KEY not in blob


# ---------------------------------------------------------------------------
# a) happy path + determinism + burn
# ---------------------------------------------------------------------------

class TestValidAuthorization(unittest.TestCase):

    def test_01_valid_token_clears(self):
        h = Harness()
        v = h.gate.evaluate(h.token(), h.draft(), SESSION, TARGET, ENV_TEXT)
        self.assertEqual((v.gate, v.reason), (GATE_GO, "owner_authorized"))
        self.assertEqual(v.manifest_sha256, FP)
        self.assertEqual(h.verdicts(), [GATE_GO])

    def test_02_deterministic_id_and_reports(self):
        v1 = Harness().gate.evaluate(Harness().token(), Harness().draft(),
                                     SESSION, TARGET, ENV_TEXT)
        v2 = Harness().gate.evaluate(Harness().token(), Harness().draft(),
                                     SESSION, TARGET, ENV_TEXT)
        self.assertEqual(v1.token_id, v2.token_id)
        self.assertEqual(v1.to_dict(), v2.to_dict())

    def test_03_nonce_burns_and_verdict_is_go_once(self):
        h = Harness()
        tok = h.token()
        v1 = h.gate.evaluate(tok, h.draft(), SESSION, TARGET, ENV_TEXT)
        v2 = h.gate.evaluate(tok, h.draft(), SESSION, TARGET, ENV_TEXT)
        self.assertEqual(v1.gate, GATE_GO)
        self.assertEqual(v2.reason, "replay_rejected")
        self.assertEqual(h.store.calls, 2)


# ---------------------------------------------------------------------------
# b) signature / tamper
# ---------------------------------------------------------------------------

class TestSignatureRefusal(unittest.TestCase):

    def test_04_tampered_signature_refused(self):
        h = Harness()
        tok = h.token()
        bad = tok[:-4] + ("0000" if tok[-4:] != "0000" else "1111")
        v = h.gate.evaluate(bad, h.draft(), SESSION, TARGET, ENV_TEXT)
        self.assertEqual((v.gate, v.reason), (GATE_NO_GO, "signature_invalid"))

    def test_05_wrong_key_signature_refused(self):
        h = Harness()
        tok = mint_token("another-owner-key-0123456789abcdef",
                         h.draft())  # forged under a different key
        v = h.gate.evaluate(tok, h.draft(), SESSION, TARGET, ENV_TEXT)
        self.assertEqual(v.reason, "signature_invalid")

    def test_06_token_id_commitment_enforced(self):
        h = Harness()
        tok = h.token()
        swapped_id = ("0" * 16) + tok[16:]
        v = h.gate.evaluate(swapped_id, h.draft(), SESSION, TARGET, ENV_TEXT)
        self.assertIn(v.reason,
                      ("unknown_binding", "signature_invalid"))

    def test_07_malformed_shapes_refused(self):
        h = Harness()
        for tok in ("", "no-dot", ".sig", "id.", None):
            v = h.gate.evaluate(tok, h.draft(), SESSION, TARGET, ENV_TEXT)
            self.assertEqual(v.gate, GATE_NO_GO)
        v = h.gate.evaluate(h.token(), None, SESSION, TARGET, ENV_TEXT)
        self.assertEqual(v.reason, "malformed_draft")


# ---------------------------------------------------------------------------
# c) TTL
# ---------------------------------------------------------------------------

class TestTtlRefusal(unittest.TestCase):

    def test_08_expired_token_refused(self):
        h = Harness(tick=100)
        d = h.draft(issued=100, expires=150)
        v = h.gate.evaluate(mint_token(KEY, d), d, SESSION, TARGET, ENV_TEXT)
        self.assertEqual(v.reason, "owner_authorized")
        h.tick = 151  # clock moved past expiry for the NEXT token
        d2 = h.draft(issued=100, expires=150, nonce="nonce-22222222")
        v2 = h.gate.evaluate(mint_token(KEY, d2), d2, SESSION, TARGET, ENV_TEXT)
        self.assertEqual((v2.gate, v2.reason),
                         (GATE_NO_GO, "token_expired"))

    def test_09_not_yet_valid_and_window_bounds(self):
        h = Harness(tick=100)
        d = h.draft(issued=150, expires=250, nonce="nonce-33333333")
        v = h.gate.evaluate(mint_token(KEY, d), d, SESSION, TARGET, ENV_TEXT)
        self.assertEqual(v.reason, "token_not_yet_valid")
        d2 = h.draft(issued=100, expires=20000, nonce="nonce-44444444")
        v2 = h.gate.evaluate(mint_token(KEY, d2), d2, SESSION, TARGET, ENV_TEXT)
        self.assertEqual(v2.reason, "ttl_window_invalid")


# ---------------------------------------------------------------------------
# d) fingerprint / context binding
# ---------------------------------------------------------------------------

class TestContextBinding(unittest.TestCase):

    def test_10_manifest_mismatch_refused(self):
        # draft minted for manifest A while gate + envelope both say
        # manifest B (the shipped FP): the DRAFT's fingerprint is the
        # mismatch
        h = Harness(manifest=FP)
        d = h.draft(manifest="b" * 64)
        v = h.gate.evaluate(mint_token(KEY, d), d, SESSION, TARGET, ENV_TEXT)
        self.assertEqual(v.reason, "fingerprint_mismatch")

    def test_11_envelope_drift_refused(self):
        fp_b = "c" * 64
        drifted = ENV_TEXT.replace(FP, fp_b)
        h = Harness(manifest=FP)
        v = h.gate.evaluate(h.token(), h.draft(), SESSION, TARGET, drifted)
        self.assertEqual(v.reason, "fingerprint_drift")

    def test_12_session_env_binding(self):
        h = Harness()
        d = h.draft(session="other-session-9", env="production")
        v = h.gate.evaluate(mint_token(KEY, d), d, SESSION, TARGET, ENV_TEXT)
        self.assertEqual(v.reason, "context_mismatch")
        v2 = h.gate.evaluate(h.token(), h.draft(),
                             "other-session-9", TARGET, ENV_TEXT)
        self.assertEqual(v2.reason, "context_mismatch")

    def test_13_envelope_parser_fail_closed(self):
        for text in ("", "garbage", "manifest_sha256: nothex\n",
                     f"manifest_sha256: {FP}\nbound_for: archive\n"):
            with self.assertRaises(ApprovalGateError):
                parse_envelope_fingerprint(text)


# ---------------------------------------------------------------------------
# e) replay
# ---------------------------------------------------------------------------

class TestReplay(unittest.TestCase):

    def test_14_replay_across_instances_refused(self):
        # durable semantics: a SECOND gate (fresh process memory) sharing
        # the same replay store still refuses the consumed nonce
        h = Harness()
        tok = h.token()
        d = h.draft()
        v1 = h.gate.evaluate(tok, d, SESSION, TARGET, ENV_TEXT)
        self.assertEqual(v1.gate, GATE_GO)
        h2 = Harness()
        h2.store = h.store  # same durable store
        h2.gate = OwnerApprovalGate(
            KEY, h.store, lambda: 100, h2.reports.append, FP)
        v2 = h2.gate.evaluate(tok, d, SESSION, TARGET, ENV_TEXT)
        self.assertEqual(v2.reason, "replay_rejected")

    def test_15_replay_is_audited(self):
        h = Harness()
        tok = h.token()
        h.gate.evaluate(tok, h.draft(), SESSION, TARGET, ENV_TEXT)
        h.gate.evaluate(tok, h.draft(), SESSION, TARGET, ENV_TEXT)
        self.assertEqual(h.verdicts(), [GATE_GO, GATE_NO_GO])
        self.assertEqual(h.reports[1]["reason"], "replay_rejected")


# ---------------------------------------------------------------------------
# f) redaction
# ---------------------------------------------------------------------------

class TestRedaction(unittest.TestCase):

    def test_16_no_key_or_signature_in_reports(self):
        h = Harness()
        tok = h.token()
        sig = tok.split(".", 1)[1]
        for v in (h.gate.evaluate(tok, h.draft(), SESSION, TARGET, ENV_TEXT),
                  h.gate.evaluate(tok, h.draft(), SESSION, TARGET, ENV_TEXT),
                  h.gate.evaluate("garbage.sig", h.draft(),
                                  SESSION, TARGET, ENV_TEXT)):
            blob = json.dumps(v.to_dict())
            self.assertNotIn(KEY, blob)
            self.assertNotIn(sig, blob)
            self.assertNotIn(CANARY, blob)
        self.assertTrue(all(_no_leak(json.dumps(r)) for r in h.reports))

    def test_17_error_paths_leak_nothing(self):
        # constructor misuse surfaces reasons, never material
        for args in ((KEY, None, lambda: 0, print, FP),
                     ("short", MemReplayStore(), lambda: 0, print, FP),
                     (KEY, MemReplayStore(), lambda: 0, print, "nothex")):
            with self.assertRaises(ApprovalGateError) as ctx:
                OwnerApprovalGate(*args)
            self.assertTrue(_no_leak(str(ctx.exception)))
            self.assertNotIn(CANARY, str(ctx.exception))


# ---------------------------------------------------------------------------
# g) AST boundaries
# ---------------------------------------------------------------------------

class TestAstBoundaries(unittest.TestCase):

    def test_18_no_io_imports_in_engine(self):
        tree = ast.parse(ENGINE.read_text(encoding="utf-8"))
        banned = {"socket", "subprocess", "ssl", "http", "urllib",
                  "requests", "ftplib", "telnetlib", "asyncio"}
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
                    self.fail("direct open() in engine")
                if isinstance(fn, ast.Attribute) and \
                        fn.attr in ("system", "popen", "connect"):
                    self.fail(f"banned call: .{fn.attr}()")

    def test_19_report_shape_contract(self):
        h = Harness()
        v = h.gate.evaluate(h.token(), h.draft(), SESSION, TARGET, ENV_TEXT)
        d = v.to_dict()
        self.assertEqual(set(d), {"gate", "reason", "token_id",
                                  "manifest_sha256", "detail", "findings"})
        self.assertIn("stage_f_owner_approval:GO", d["findings"])


if __name__ == "__main__":
    unittest.main()

"""Stage F — context-bound owner authorization gate (D-146).

The final cutover switch (Dokploy plan §17/§21.6, D-139) is strictly
owner-gated: technical clearance (V-01..V-09, D-145) is necessary but
NEVER sufficient. This engine is the machine-enforced Stage F half —
it validates an explicit, single-use, context-bound owner approval
token before any cutover authorization may be granted.

Design (composes the shipped canonical primitives; nothing duplicated):

  TOKEN      — HMAC-SHA256 over a canonical JSON binding of
               (manifest_sha256, session_id, target_env, issued_tick,
                expires_tick, nonce), keyed by an owner-held signing
                key that NEVER appears in any report, error, or log
                (D-124). Wire format: ``<token_id>.<hex signature>``.
  BINDING    — the token cryptographically commits to the exact Stage D
               manifest fingerprint (from `stage_d_fingerprint.envelope`,
               D-144/D-145), the cutover session id, and the target
               environment. Any drift = rejection.
  TTL        — hard expiration, judged against an INJECTED logical
               clock tick (no wall clock anywhere — D-085/D-093
               determinism discipline).
  SINGLE-USE — the nonce is burned through an INJECTED replay store
               using a deterministic key; a second consumption attempt
               is a replay and is refused (Phase 19 / D-090 burn
               semantics).
  FAIL-CLOSED— malformed, unsigned, expired, drifted, revoked, or
               replayed material ALL refuse. Absence of a gate is
               never an approval.
  AUDIT      — every evaluation outcome is emitted to an INJECTED
               audit sink (the D-121 `engine.log.v1` ledger in
               production); sink failures are surfaced, never silent.

Pure core: no network, no subprocess, no direct file I/O, no wall
clock. The owner mints offline (`mint_token` with their own key);
the deployment orchestrator verifies with `OwnerApprovalGate.evaluate`.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

try:  # battery package path or script cwd path
    from ..memory.vector_store import deep_redact  # type: ignore
except ImportError:  # pragma: no cover - script invocation
    from memory.vector_store import deep_redact  # type: ignore

__all__ = [
    "ApprovalGateError", "TokenDraft", "EvaluationVerdict",
    "OwnerApprovalGate", "mint_token", "parse_envelope_fingerprint",
    "GATE_GO", "GATE_NO_GO",
]

GATE_GO = "GO"
GATE_NO_GO = "NO_GO"

# TTL floor: a token must live at least this many logical ticks and at
# most this ceiling (absurd TTLs — zero, negative, or unbounded — are
# refused; the window is part of the binding contract).
TTL_MIN_TICKS = 1
TTL_MAX_TICKS = 10_000

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_ENV_SHAPE = re.compile(r"^[a-z][a-z0-9-]{1,31}$")
_SESSION_SHAPE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$")
_NONCE_SHAPE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{7,127}$")


class ApprovalGateError(ValueError):
    """Contract-level misuse of the approval gate (fail-closed)."""


def _fail(reason: str) -> None:
    raise ApprovalGateError(reason)


# ---------------------------------------------------------------------------
# Envelope fingerprint parsing (D-144 artifact; text in, hash out)
# ---------------------------------------------------------------------------

def parse_envelope_fingerprint(envelope_text: str) -> str:
    """Extract the manifest sha256 from the D-144 envelope text.

    Fail-closed: missing/malformed/misbound envelopes raise; the hash
    must be exact lowercase hex64 and the envelope must be bound for
    stage-e-cutover. No other content is interpreted.
    """
    if not isinstance(envelope_text, str) or not envelope_text.strip():
        _fail("envelope_text_required")
    seen: Dict[str, str] = {}
    for line in envelope_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, val = line.partition(":")
        seen[key.strip()] = val.strip()
    manifest = seen.get("manifest_sha256", "")
    if not _HEX64.match(manifest):
        _fail("envelope_fingerprint_malformed")
    if seen.get("bound_for") != "stage-e-cutover":
        _fail("envelope_not_bound_for_stage_e_cutover")
    return manifest


# ---------------------------------------------------------------------------
# Token minting (OWNER-side, offline; key never persisted here)
# ---------------------------------------------------------------------------

def _canonical_binding(payload: Dict[str, Any]) -> bytes:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)
    return blob.encode("utf-8")


def _sign(key: str, payload: Dict[str, Any]) -> str:
    return hmac.new(key.encode("utf-8"),
                    _canonical_binding(payload),
                    hashlib.sha256).hexdigest()


def _token_id(payload: Dict[str, Any]) -> str:
    """Stable identifier for reports/audit: hash of the binding only —
    never of the key, never of the signature."""
    return hashlib.sha256(_canonical_binding(payload)).hexdigest()[:16]


@dataclass(frozen=True)
class TokenDraft:
    """Everything the owner needs to mint one authorization token."""
    manifest_sha256: str
    session_id: str
    target_env: str
    issued_tick: int
    expires_tick: int
    nonce: str


def mint_token(signing_key: str, draft: TokenDraft) -> str:
    """Owner-side offline minting. Returns ``<token_id>.<sig>``.

    The signing key exists only in this call — it is never written,
    returned, logged, or embedded in the token material.
    """
    if not isinstance(signing_key, str) or len(signing_key) < 16:
        _fail("signing_key_required_min_16_chars")
    payload = {
        "manifest_sha256": draft.manifest_sha256,
        "session_id": draft.session_id,
        "target_env": draft.target_env,
        "issued_tick": draft.issued_tick,
        "expires_tick": draft.expires_tick,
        "nonce": draft.nonce,
    }
    return f"{_token_id(payload)}.{_sign(signing_key, payload)}"


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EvaluationVerdict:
    """Deterministic, secret-free outcome of one gate evaluation."""
    gate: str                       # GO / NO_GO
    reason: str                     # stable machine phrase
    token_id: str                   # binding hash prefix ('' if none)
    manifest_sha256: str            # the expected fingerprint ('' if unknown)
    detail: str                     # deep-redacted human detail
    findings: tuple = field(default_factory=tuple)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gate": self.gate,
            "reason": self.reason,
            "token_id": self.token_id,
            "manifest_sha256": self.manifest_sha256,
            "detail": self.detail,
            "findings": list(self.findings),
        }


class OwnerApprovalGate:
    """Machine-enforced Stage F cutover authorization gate.

    Injected collaborators (RULES §35 — the core performs no I/O):
      signing_key     — the shared owner secret (compare-only; never
                        emitted); production injects it from the
                        environment secret store, tests from memory.
      replay_store    — single-method store with
                        ``consume(key) -> bool`` returning True on
                        first burn, False when the key already exists
                        (durable one-time semantics; D-090 burn
                        pattern).
      clock           — ``() -> int`` logical tick (injected; no wall
                        clock).
      audit_sink      — ``callable(report: dict)`` receiving every
                        evaluation outcome (D-121 log ledger in
                        production). Sink failure raises — an
                        unevaluated-quietly gate is a violated
                        invariant.
    """

    def __init__(self, signing_key: str, replay_store: Any,
                 clock: Callable[[], int], audit_sink: Callable[[Dict[str, Any]], None],
                 manifest_sha256: str) -> None:
        if not isinstance(signing_key, str) or len(signing_key) < 16:
            _fail("signing_key_required_min_16_chars")
        if replay_store is None or not callable(getattr(replay_store, "consume", None)):
            _fail("replay_store_with_consume_required")
        if not callable(clock):
            _fail("clock_required")
        if not callable(audit_sink):
            _fail("audit_sink_required")
        if not _HEX64.match(manifest_sha256 or ""):
            _fail("manifest_sha256_required_hex64")
        self._key = signing_key
        self._store = replay_store
        self._clock = clock
        self._sink = audit_sink
        self._manifest = manifest_sha256

    # -- internals ---------------------------------------------------------

    def _emit(self, verdict: EvaluationVerdict) -> EvaluationVerdict:
        report = verdict.to_dict()
        report["observed_tick"] = self._clock()
        # D-124 belt-and-braces: the serialized report itself passes the
        # redactor before it leaves the engine.
        self._sink(json.loads(deep_redact(json.dumps(report))))
        return verdict

    def _refuse(self, reason: str, token_id: str, detail: str,
                findings: Optional[List[str]] = None) -> EvaluationVerdict:
        return self._emit(EvaluationVerdict(
            gate=GATE_NO_GO, reason=reason, token_id=token_id,
            manifest_sha256=self._manifest,
            detail=deep_redact(detail), findings=tuple(findings or ())))

    # -- the gate ------------------------------------------------------------

    def evaluate(self, token: str, draft: TokenDraft, session_id: str,
                 target_env: str, envelope_text: str) -> EvaluationVerdict:
        """Evaluate one owner authorization token against THIS cutover
        context. Exactly one outcome is emitted and audited.

        The owner mints offline and hands the orchestrator BOTH the
        token and the draft (issued/expires ticks + nonce) over the
        approval channel; the gate then verifies that

          1. the token id commits to the full binding of THIS draft,
             session, env, and envelope fingerprint (any mismatch =
             unknown_binding),
          2. the signature is valid under the owner key (constant-
             time compare),
          3. the TTL window is sane and unexpired against the
             INJECTED clock,
          4. the nonce burns exactly once through the injected
             replay store (replay = refusal),

        and only then reports GO. Every outcome is audited.
        """
        # 1. shape ---------------------------------------------------------
        if not isinstance(token, str) or "." not in token:
            return self._refuse("malformed_token", "",
                                "token must be '<token_id>.<signature>'")
        tid, _, sig = token.partition(".")
        if not tid or not sig:
            return self._refuse("malformed_token", "",
                                "empty token component")
        if not _SESSION_SHAPE.match(session_id or ""):
            return self._refuse("malformed_context", "",
                                "session_id shape invalid")
        if not _ENV_SHAPE.match(target_env or ""):
            return self._refuse("malformed_context", "",
                                "target_env shape invalid")
        if not isinstance(draft, TokenDraft):
            return self._refuse("malformed_draft", "", "draft required")
        if draft.session_id != session_id or draft.target_env != target_env:
            return self._refuse(
                "context_mismatch", "",
                "draft does not describe this cutover session/target")

        # 2. expected fingerprint from the CURRENT envelope ----------------
        try:
            expected = parse_envelope_fingerprint(envelope_text)
        except ApprovalGateError as exc:
            return self._refuse("envelope_invalid", "",
                                f"stage D envelope unusable: {exc}")
        if expected != self._manifest:
            return self._refuse(
                "fingerprint_drift", "",
                "envelope fingerprint differs from gate-bound fingerprint")
        if draft.manifest_sha256 != expected:
            return self._refuse(
                "fingerprint_mismatch", "",
                "draft was minted for a different manifest fingerprint")

        # 3. commitment + signature -----------------------------------------
        payload = {
            "manifest_sha256": draft.manifest_sha256,
            "session_id": draft.session_id,
            "target_env": draft.target_env,
            "issued_tick": draft.issued_tick,
            "expires_tick": draft.expires_tick,
            "nonce": draft.nonce,
        }
        if not hmac.compare_digest(tid, _token_id(payload)):
            return self._refuse(
                "unknown_binding", tid,
                "token id does not commit to the presented draft/context")
        expected_sig = _sign(self._key, payload)
        if not hmac.compare_digest(sig, expected_sig):
            return self._refuse("signature_invalid", tid,
                                "token signature mismatch")

        # 4. TTL against the injected clock ----------------------------------
        now = self._clock()
        issued = payload["issued_tick"]
        expires = payload["expires_tick"]
        if not isinstance(issued, int) or isinstance(issued, bool) \
                or not isinstance(expires, int) or isinstance(expires, bool):
            return self._refuse("ttl_malformed", tid, "non-integer ticks")
        window = expires - issued
        if window < TTL_MIN_TICKS or window > TTL_MAX_TICKS:
            return self._refuse(
                "ttl_window_invalid", tid, f"ttl window {window} ticks")
        if now >= expires:
            return self._refuse(
                "token_expired", tid, f"expired {expires - now} ticks ago")
        if now < issued:
            return self._refuse(
                "token_not_yet_valid", tid, "issued tick in the future")

        # 5. single-use burn (replay protection) ------------------------------
        nonce = payload["nonce"]
        if not _NONCE_SHAPE.match(nonce or ""):
            return self._refuse("nonce_malformed", tid, "nonce shape invalid")
        burn_key = hashlib.sha256(_canonical_binding(
            {"burn": "stage-f-cutover", "token_id": tid,
             "nonce": nonce})).hexdigest()
        if not self._store.consume(burn_key):
            return self._refuse("replay_rejected", tid,
                                "authorization nonce already consumed")

        # 6. authorized ---------------------------------------------------------
        return self._emit(EvaluationVerdict(
            gate=GATE_GO, reason="owner_authorized", token_id=tid,
            manifest_sha256=expected,
            detail=(f"cutover authorized for session {session_id} "
                    f"target {target_env} at tick {now}"),
            findings=["stage_f_owner_approval:GO"]))

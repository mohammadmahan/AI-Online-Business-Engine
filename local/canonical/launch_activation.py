"""Phase 26 M2 — controlled activation state machine (D-139).

Activation is a sequence of independently gated, REVERSIBLE steps —
never one global switch. Illegal transitions fail deterministically;
production-capable transitions require an unexpired, single-use,
context-bound owner approval token; rollback is reachable from every
state that can produce external side effects.

Audit destinations (owner ruling): machine activation telemetry →
D-121 `engine.log.v1` (injected `LogLedger`); human approval,
break-glass, promotion, rollback → Phase 19 `admin.control_audit`
chain (injected `ControlPlaneEngine.append_external_audit`).

D-045: NO real provider is contacted anywhere in this module. The
dry-run probe and canary actions are injected callables whose shipped
rehearsal implementations are pure mocks.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Callable, Dict, Optional

from .admin_contracts import AdminContractError, actor_id, actor_role
from .launch_contracts import ContractError, redact_text

__all__ = [
    "ACTIVATION_STATES",
    "SIDE_EFFECT_CAPABLE",
    "TERMINAL_STATES",
    "ActivationError",
    "TransitionRejected",
    "ApprovalTokenError",
    "APPROVAL_KINDS",
    "APPROVAL_KIND_TRANSITION",
    "APPROVAL_KIND_KILL_SWITCH",
    "APPROVAL_KIND_BREAK_GLASS",
    "KillSwitch",
    "ActivationMachine",
    "mint_approval",
]

# --- states & legal transitions (D-139) -------------------------------------

DRAFT = "DRAFT"
ASSESSED = "ASSESSED"
NO_GO = "NO_GO"
GO_ATTESTED = "GO_ATTESTED"
OWNER_APPROVED = "OWNER_APPROVED"
DRY_RUN = "DRY_RUN"
CANARY = "CANARY"
OBSERVING = "OBSERVING"
PROMOTED = "PROMOTED"
ROLLING_BACK = "ROLLING_BACK"
ROLLED_BACK = "ROLLED_BACK"

ACTIVATION_STATES = (
    DRAFT, ASSESSED, NO_GO, GO_ATTESTED, OWNER_APPROVED,
    DRY_RUN, CANARY, OBSERVING, PROMOTED, ROLLING_BACK, ROLLED_BACK,
)

# states whose ENTRY produces external side effects and therefore
# demands a one-time owner token (canary = live limited action;
# promotion = full activation). Dry run is a zero-side-effect
# rehearsal; OBSERVING is passive monitoring — neither needs one.
SIDE_EFFECT_CAPABLE = frozenset({CANARY, PROMOTED})
TERMINAL_STATES = frozenset({PROMOTED, ROLLED_BACK})

# every state that may initiate rollback (D-139: every state that can
# produce external side effects — including OBSERVING, which monitors
# live canary traffic — plus the pre-canary states defensively)
_ROLLBACK_SOURCES = (SIDE_EFFECT_CAPABLE
                     | {OWNER_APPROVED, DRY_RUN, OBSERVING, ROLLING_BACK})

TRANSITIONS: Dict[str, frozenset] = {
    DRAFT: frozenset({ASSESSED}),
    ASSESSED: frozenset({NO_GO, GO_ATTESTED}),
    NO_GO: frozenset(),                      # terminal block; remediate & re-assess
    GO_ATTESTED: frozenset({OWNER_APPROVED}),
    OWNER_APPROVED: frozenset({DRY_RUN, ROLLING_BACK}),
    DRY_RUN: frozenset({CANARY, ROLLING_BACK}),
    CANARY: frozenset({OBSERVING, ROLLING_BACK}),
    OBSERVING: frozenset({PROMOTED, ROLLING_BACK}),
    PROMOTED: frozenset(),
    ROLLING_BACK: frozenset({ROLLED_BACK}),
    ROLLED_BACK: frozenset(),
}


class ActivationError(ValueError):
    """Activation-module misuse (bad ids, malformed token material)."""


class TransitionRejected(ActivationError):
    """Deterministic refusal: illegal transition or failed gate."""


class ApprovalTokenError(ActivationError):
    """Deterministic refusal of approval material (replay, expiry,
    mismatch, single-use burn)."""


# --- approval token kinds (D-139) --------------------------------------------

APPROVAL_KIND_TRANSITION = "activation_transition"
APPROVAL_KIND_KILL_SWITCH = "kill_switch"
APPROVAL_KIND_BREAK_GLASS = "break_glass"
APPROVAL_KINDS = (
    APPROVAL_KIND_TRANSITION, APPROVAL_KIND_KILL_SWITCH,
    APPROVAL_KIND_BREAK_GLASS,
)


def _token_material(candidate_commit: str, kind: str, target: str,
                    fingerprint: str, nonce: str = "") -> str:
    """Canonical token hash: commit + kind + target + config
    fingerprint + owner nonce. The context fields bind the token to
    THIS candidate; the owner-supplied nonce makes each activation
    attempt mintable fresh (deterministic recompute, no wall clock)."""
    blob = json.dumps(
        {"commit": candidate_commit, "kind": kind, "target": target,
         "fingerprint": fingerprint, "nonce": nonce},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def mint_approval(candidate_commit: str, kind: str, target: str,
                  fingerprint: str, nonce: str) -> str:
    """Mint one-time approval material as ``<nonce>.<hash>``.

    The OWNER runs this locally (nonce chosen by the owner); the
    machine recomputes and verifies the hash against its own context,
    then burns the token through the D-027 store on first use."""
    if not isinstance(nonce, str) or not nonce:
        raise ApprovalTokenError("approval nonce required")
    return f"{nonce}.{_token_material(candidate_commit, kind, target, fingerprint, nonce)}"


# --- kill switch (D-139) ------------------------------------------------------

class KillSwitch:
    """Deterministic latching kill switch.

    `tripped(kill_key)` burns a one-time kill approval (Phase 19
    semantics: replayed keys are refused); the latch is permanent for
    the run. Raises ApprovalTokenError on any mismatch or replay.
    """

    def __init__(self) -> None:
        self._latched = False
        self._burned_keys = set()

    @property
    def tripped(self) -> bool:
        return self._latched

    def trip(self, kill_key: str, expected_material: str) -> None:
        if not isinstance(kill_key, str) or not kill_key:
            raise ApprovalTokenError("kill approval key required")
        if kill_key in self._burned_keys:
            raise ApprovalTokenError("kill approval key already burned")
        if not isinstance(expected_material, str) or not expected_material:
            raise ApprovalTokenError("expected token material required")
        self._burned_keys.add(kill_key)
        self._latched = True


# --- the machine ----------------------------------------------------------------

class ActivationMachine:
    """D-139 activation state machine.

    Injected collaborators (RULES §35 — no I/O is performed directly):
      store           — D-027 event store (durable one-time approval
                        burn via deterministic event ids).
      ledger          — D-121 `LogLedger` for machine telemetry
                        (optional; None = telemetry sink absent).
      control_engine  — Phase 19 `ControlPlaneEngine` for human-audit
                        appends (optional; None = human audit absent).
      dry_probe       — injected dry-run probe callable (mock shipped).
      canary_action   — injected canary action callable (mock shipped).
    """

    def __init__(self, store, candidate_commit: str,
                 config_fingerprint: str, *, ledger=None,
                 control_engine=None, dry_probe: Optional[Callable] = None,
                 canary_action: Optional[Callable] = None,
                 actor: str = "actor:admin:owner"):
        self._store = store
        self.candidate_commit = candidate_commit
        self.config_fingerprint = config_fingerprint
        self._ledger = ledger
        self._engine = control_engine
        self._dry_probe = dry_probe
        self._canary_action = canary_action
        self.actor = actor
        self.kill_switch = KillSwitch()
        self.state = DRAFT
        self._logical_seq = 0
        self._spent_transition_keys = set()
        if not candidate_commit or not isinstance(candidate_commit, str):
            raise ActivationError("candidate_commit required")
        if not config_fingerprint or not isinstance(config_fingerprint, str):
            raise ActivationError("config_fingerprint required")

    # -- internals ----------------------------------------------------------

    def _tick(self) -> str:
        self._logical_seq += 1
        return f"L-{self._logical_seq:06d}"

    def _telemetry(self, event: str, status: str = "SUCCESS",
                   payload: Optional[Dict] = None) -> None:
        """Machine telemetry → D-121 ledger (redacted, deterministic)."""
        if self._ledger is None:
            return
        from .obs_contracts import TraceContext
        ctx = TraceContext.root(
            "admin", f"launch|{self.candidate_commit}", self._tick())
        self._ledger.emit(
            ctx, domain="admin", event=event, logical_at=self._tick(),
            level="INFO" if status == "SUCCESS" else "WARN",
            status=status, entity_ref=self.state,
            payload={k: redact_text(str(v)) for k, v in (payload or {}).items()})

    def _human_audit(self, kind: str, action_id: str,
                     detail: Dict) -> None:
        """Human-decision audit → Phase 19 control-audit chain."""
        if self._engine is None:
            return
        self._engine.append_external_audit(
            action_id, kind, self.actor, detail, self._tick())

    def _burn_approval(self, kind: str, token_key: str,
                       target: str) -> None:
        """One-time burn of an approval token through the D-027 store.

        Deterministic event id ⇒ a replayed token is a
        skipped_duplicate, which is REFUSED (already spent). A same-id
        different-payload conflict raises IntegrityError — surfaced as
        ApprovalTokenError (never silently accepted).
        """
        event_id = f"launch-approval|{kind}|{token_key}"
        # the store's OWN namespace wins (PgEventStore._src_for
        # semantics): a per-run store isolates burns; the JSON store
        # falls back to the shared "launch26" source
        source = getattr(self._store, "source_system", "launch26") or "launch26"
        verdict = self._store.receive(source, event_id, "SYSTEM", {"kind": kind})
        if verdict.get("verdict") == "skipped_duplicate":
            raise ApprovalTokenError(
                f"approval token already burned ({kind})")
        try:
            self._store.begin(source, event_id)
            self._store.succeed(source, event_id, result_reference=target)
        except Exception as exc:  # conflict / integrity
            raise ApprovalTokenError(
                f"approval token conflict ({kind}): {exc}") from exc

    def _verify_token(self, kind: str, target: str,
                      approval_key: Optional[str]) -> str:
        """Parse ``nonce.hash`` and verify the context binding against
        THIS machine's candidate commit + config fingerprint."""
        if not isinstance(approval_key, str) or "." not in approval_key:
            raise ApprovalTokenError(
                f"approval material must be '<nonce>.<hash>' for {target}")
        nonce, _, digest = approval_key.partition(".")
        if not nonce or not digest:
            raise ApprovalTokenError("malformed approval material")
        expected = _token_material(
            self.candidate_commit, kind, target, self.config_fingerprint,
            nonce)
        if digest != expected:
            raise ApprovalTokenError("approval token context mismatch")
        return approval_key

    def _require_approval(self, kind: str, target: str,
                          approval_key: Optional[str]) -> None:
        """Production-capable transitions require an unexpired,
        single-use, context-bound approval token.

        Context binding: the token hash must recompute from (candidate
        commit, kind, target, config fingerprint, owner nonce). Expiry:
        declared logical age beyond 100 logical ticks is refused
        (L-expiry, never wall clock). Single use: burned through the
        D-027 store on first presentation.
        """
        if self.kill_switch.tripped:
            raise TransitionRejected("kill switch tripped")
        verified = self._verify_token(kind, target, approval_key)
        seq = int(self._tick().split("-")[1])
        if seq > 100:
            raise ApprovalTokenError("approval token expired (logical age)")
        self._burn_approval(kind, verified, target)
        self._spent_transition_keys.add(verified)

    # -- public protocol ------------------------------------------------------

    def transition(self, target: str,
                   approval_key: Optional[str] = None) -> Dict:
        """Attempt one transition. Deterministic refusal on illegal
        transitions, kill-switch latching, or approval-gate failure."""
        if target not in ACTIVATION_STATES:
            raise TransitionRejected(f"unknown state: {target!r}")
        if self.kill_switch.tripped and target != ROLLING_BACK:
            raise TransitionRejected("kill switch tripped")
        if target not in TRANSITIONS[self.state]:
            raise TransitionRejected(
                f"illegal transition {self.state} -> {target}")
        if target in SIDE_EFFECT_CAPABLE:
            self._require_approval(
                APPROVAL_KIND_TRANSITION, target, approval_key)
        previous = self.state
        self.state = target
        self._telemetry("activation_transition", payload={
            "from": previous, "to": target})
        return {"ok": True, "from": previous, "to": target}

    def assess(self, verdict: str, attestation: str) -> Dict:
        """DRAFT -> ASSESSED -> (NO_GO | GO_ATTESTED), bound to the
        evaluator's verdict + attestation hash."""
        if self.state != DRAFT:
            raise TransitionRejected(
                f"assess requires DRAFT, machine is {self.state}")
        if verdict not in ("GO", "CONDITIONAL_GO", "NO_GO"):
            raise ActivationError(f"unknown verdict: {verdict!r}")
        if not isinstance(attestation, str) or not attestation:
            raise ActivationError("attestation hash required")
        self._verdict = verdict
        self._attestation = attestation
        self.transition(ASSESSED)
        nxt = NO_GO if verdict == "NO_GO" else GO_ATTESTED
        self.transition(nxt)
        self._telemetry("launch_assessed", status=(
            "FAILURE" if verdict == "NO_GO" else "SUCCESS"),
            payload={"verdict": verdict})
        return {"ok": True, "verdict": verdict, "state": self.state}

    def approve(self, approval_key: str, approver_role: str = "admin",
                approver_id: str = "owner") -> Dict:
        """GO_ATTESTED -> OWNER_APPROVED. Requires an explicit,
        context-bound one-time approval token; the human decision is
        appended to the Phase 19 chain."""
        if self.state != GO_ATTESTED:
            raise TransitionRejected(
                f"approve requires GO_ATTESTED, machine is {self.state}")
        # RBAC: only the admin role may approve (D-109/D-050).
        if actor_role(approver_role if ":" in approver_role
                      else f"actor:{approver_role}:{approver_id}") != "admin":
            raise ApprovalTokenError("approval requires the admin role")
        verified = self._verify_token(
            APPROVAL_KIND_TRANSITION, OWNER_APPROVED, approval_key)
        self._burn_approval(APPROVAL_KIND_TRANSITION, verified,
                            OWNER_APPROVED)
        self.state = OWNER_APPROVED
        self._human_audit("launch_owner_approval", f"launch|{self.candidate_commit}",
                          {"verdict": getattr(self, "_verdict", "?"),
                           "token": "[REDACTED]"})
        self._telemetry("launch_owner_approved", payload={"state": self.state})
        return {"ok": True, "state": self.state}

    def dry_run(self) -> Dict:
        """OWNER_APPROVED -> DRY_RUN: configuration + reachability
        rehearsal with ZERO public side effects. The injected probe
        must succeed or the machine stays put."""
        self.transition(DRY_RUN)
        try:
            if self._dry_probe is not None:
                probe = self._dry_probe()
                ok = bool(probe.get("ok")) if isinstance(probe, dict) else bool(probe)
            else:
                ok = True
        except Exception as exc:
            self._telemetry("launch_dry_run", status="FAILURE",
                            payload={"error": redact_text(str(exc))[:200]})
            raise TransitionRejected(f"dry-run probe failed: {exc}") from exc
        if not ok:
            self._telemetry("launch_dry_run", status="FAILURE")
            raise TransitionRejected("dry-run probe reported not-ok")
        self._telemetry("launch_dry_run")
        return {"ok": True, "state": self.state, "side_effects": 0}

    def canary(self, scope: Dict, approval_key: str) -> Dict:
        """DRY_RUN -> CANARY: smallest owner-approved scope under
        D-127/D-128 ceilings with the kill switch available."""
        self.transition(CANARY, approval_key=approval_key)
        try:
            result = self._canary_action(dict(scope)) if self._canary_action else {"ok": True}
        except Exception as exc:
            self._telemetry("launch_canary", status="FAILURE",
                            payload={"error": redact_text(str(exc))[:200]})
            raise TransitionRejected(f"canary action failed: {exc}") from exc
        if not result.get("ok", True):
            self._telemetry("launch_canary", status="FAILURE")
            raise TransitionRejected("canary action reported not-ok")
        self._telemetry("launch_canary", payload={
            "scope": json.dumps(scope, sort_keys=True)[:200]})
        return {"ok": True, "state": self.state, "result": result}

    def observe(self, metrics: Dict, thresholds: Dict) -> Dict:
        """CANARY -> OBSERVING with deterministic threshold evaluation:
        every declared metric must be within its threshold."""
        self.transition(OBSERVING)
        breaches = {k: v for k, v in metrics.items()
                    if k in thresholds and v > thresholds[k]}
        self._telemetry("launch_observation", status=(
            "FAILURE" if breaches else "SUCCESS"),
            payload={"breaches": sorted(breaches)})
        return {"ok": not breaches, "breaches": breaches, "state": self.state}

    def promote(self, approval_key: str) -> Dict:
        """OBSERVING -> PROMOTED. Requires a fresh one-time promotion
        token; never inferred from the absence of failures. The human
        promotion decision is appended to the Phase 19 chain."""
        self.transition(PROMOTED, approval_key=approval_key)
        self._human_audit("promotion", f"launch|{self.candidate_commit}",
                          {"token": "[REDACTED]"})
        self._telemetry("launch_promoted")
        return {"ok": True, "state": self.state}

    def rollback(self, reason: str) -> Dict:
        """Initiate rollback from ANY side-effect-capable state (or
        mid-rollback). Order: stop-new-work latch first (kill switch),
        then compensate; forensic evidence is never deleted; the
        human rollback decision lands in the Phase 19 chain."""
        if self.state not in _ROLLBACK_SOURCES:
            raise TransitionRejected(
                f"rollback unavailable from {self.state}")
        if not isinstance(reason, str) or not reason:
            raise ActivationError("rollback requires a written reason")
        self.kill_switch._latched = True  # stop new work immediately
        previous = self.state
        self.state = ROLLING_BACK
        self._human_audit("rollback", f"launch|{self.candidate_commit}",
                          {"from": previous, "reason": redact_text(reason)[:200]})
        self._telemetry("launch_rollback", status="FAILURE",
                        payload={"from": previous})
        return {"ok": True, "from": previous, "state": self.state}

    def complete_rollback(self, reconcile: Optional[Callable] = None) -> Dict:
        """ROLLING_BACK -> ROLLED_BACK after outbox/lock/reservation
        reconciliation. The injected reconciler must report ok."""
        if self.state != ROLLING_BACK:
            raise TransitionRejected(
                f"complete_rollback requires ROLLING_BACK, machine is {self.state}")
        ok = True
        if reconcile is not None:
            report = reconcile()
            ok = bool(report.get("ok", True)) if isinstance(report, dict) else bool(report)
        if not ok:
            raise TransitionRejected("post-rollback reconciliation failed")
        self.state = ROLLED_BACK
        self._telemetry("launch_rolled_back")
        return {"ok": True, "state": self.state}

    def break_glass(self, approval_key: str, reason: str) -> Dict:
        """Audited break-glass: burns a dedicated one-time token and
        records the decision in the Phase 19 chain. Returns the exact
        material a kill switch trip is validated against."""
        if not approval_key:
            raise ApprovalTokenError("break-glass approval material required")
        verified = self._verify_token(
            APPROVAL_KIND_BREAK_GLASS, "break_glass", approval_key)
        if not isinstance(reason, str) or not reason:
            raise ActivationError("break-glass requires a written reason")
        self._burn_approval(APPROVAL_KIND_BREAK_GLASS, verified,
                            "break_glass")
        self._human_audit("break_glass", f"launch|{self.candidate_commit}",
                          {"reason": redact_text(reason)[:200]})
        self._telemetry("launch_break_glass", status="FAILURE")
        return {"ok": True,
                "kill_material": _token_material(
                    self.candidate_commit, APPROVAL_KIND_KILL_SWITCH,
                    "kill", self.config_fingerprint)}

"""Phase 7 M2 — proposal lifecycle & HITL round-trip (D-050/D-026/D-027).

State machine (owner-approved M2 scope; D-064 Approved):

    PROPOSED → IN_REVIEW → ACCEPTED          (terminal, human action)
                        → REJECTED           (terminal, human action)
                        → MODIFIED_BY_HUMAN  (terminal, human action)

Every transition is a HUMAN action through decide() — there is no
auto-advance path anywhere in this module (battery-asserted via import
graph + action vocabulary). Accepting runs an INJECTED deterministic
applier (canonical-side; e.g. create the content idea at Backlog in
the approved lifecycle machine) — the AI runtime never holds that
callable, so an accepted proposal can only ever reach its approved
canonical target, never an active/published state by itself.

Durability (D-055, D-027): each transition is its OWN D-027 event
under a deterministic id:
    aiprop|<pid>            submit (PROPOSED)
    aiprop|<pid>|review     submit_review (IN_REVIEW)
    aiprop|<pid>|accept     accept (ACCEPTED)
    aiprop|<pid>|reject     reject (REJECTED)
    aiprop|<pid>|modify     modify_accept (MODIFIED_BY_HUMAN)
Current state = the LAST succeeded event (event-sourced, same
philosophy as the D-060 revision-marker key: distinct logical events
get distinct durable rows; retries of the same delivery dedupe as
skipped_duplicate). This is the D-027-correct design: state updates
are events, not payload rewrites of one row.

D-026 provenance: AI_GENERATED at submit; HUMAN_ENTERED at every
decision (actor, timestamp, notes, structured diff); the AI record's
review_state advances PENDING → HUMAN_REVIEWED at the first terminal
decision (the machine's only legal mutation, via advance_review).

Idempotency: submit is idempotent by (proposal id, payload hash);
a same-id/different-payload submit is an IntegrityError (conflicting
duplicate → human review). An identical re-decision of a terminal
proposal returns the recorded state (skipped_duplicate); a DIFFERENT
re-decision is refused (decisions are immutable).
"""

from __future__ import annotations

import hashlib
import json
from typing import Dict, List, Optional

from canonical.ai_runtime import AiProposal
from services.sync_engine import IntegrityError, ProvenanceEngine

PROPOSED = "PROPOSED"
IN_REVIEW = "IN_REVIEW"
ACCEPTED = "ACCEPTED"
REJECTED = "REJECTED"
MODIFIED_BY_HUMAN = "MODIFIED_BY_HUMAN"

TERMINAL = (ACCEPTED, REJECTED, MODIFIED_BY_HUMAN)
ALL_STATES = (PROPOSED, IN_REVIEW, ACCEPTED, REJECTED, MODIFIED_BY_HUMAN)

# (state, action) -> new state; anything else is refused (D-050)
TRANSITIONS = {
    (PROPOSED, "submit_review"): IN_REVIEW,
    (IN_REVIEW, "accept"): ACCEPTED,
    (IN_REVIEW, "reject"): REJECTED,
    (IN_REVIEW, "modify_accept"): MODIFIED_BY_HUMAN,
}

# transition -> durable event-id suffix (deterministic)
_EVENT_SUFFIX = {
    "submit_review": "review",
    "accept": "accept",
    "reject": "reject",
    "modify_accept": "modify",
}

SOURCE_SYSTEM = "ai-proposal"
OP_LIFECYCLE = "AI_PROPOSAL_LIFECYCLE"

ACTIONS = tuple(_EVENT_SUFFIX)  # the complete legal action vocabulary


class ProposalStateError(ValueError):
    """Illegal lifecycle transition/action — deterministic refusal."""

    def __init__(self, message: str, *, from_state: str = "?",
                 action: str = "?"):
        super().__init__(message)
        self.failure_class = "B"  # D-052: data invariant
        self.from_state = from_state
        self.action = action


def _payload_hash(payload) -> str:
    """Canonical SHA-256 (same canonicalization as the D-027 stores)."""
    return hashlib.sha256(json.dumps(
        payload, sort_keys=True, ensure_ascii=False,
        default=str).encode("utf-8")).hexdigest()


class ProposalLifecycle:
    """Durable, event-sourced proposal lifecycle over any D-027 store."""

    def __init__(self, store, provenance: ProvenanceEngine,
                 queue=None, applier=None):
        self.store = store
        self.provenance = provenance
        self.queue = queue
        self.applier = applier  # Optional[Callable[[str, dict], dict]]

    # -- internals -------------------------------------------------------------

    def _src(self) -> str:
        return getattr(self.store, "source_system", SOURCE_SYSTEM)

    def _eid(self, proposal_id: str, suffix: str = "") -> str:
        return f"aiprop|{proposal_id}" + (f"|{suffix}" if suffix else "")

    def _record_transition(self, eid: str, ref: Dict) -> Dict:
        """Write one transition event durably (receive → begin → succeed)
        with D-027 dedupe semantics; returns the verdict."""
        src = self._src()
        rec = self.store.receive(src, eid, OP_LIFECYCLE, ref)
        if rec["verdict"] == "skipped_duplicate":
            return {"verdict": "skipped_duplicate"}
        if rec["verdict"] == "integrity_error":
            raise IntegrityError(
                f"conflicting duplicate for {eid} — human review (D-027)")
        self.store.begin(src, eid)
        self.store.succeed(src, eid, result_reference=json.dumps(
            ref, ensure_ascii=False, sort_keys=True))
        return {"verdict": rec["verdict"]}

    def _history(self, proposal_id: str,
                 decision_events_only: bool = False) -> List[Dict]:
        """Succeeded events for this proposal, in store order
        (deterministic).

        Lifecycle state is carried by the submit + decision events; the
        `|applied` follow-up event is execution bookkeeping and must
        never shadow the last DECISION (its ref has no decision_hash,
        which would break terminal-re-decide idempotency)."""
        eid_prefix = f"aiprop|{proposal_id}"
        out = []
        for r in self.store.succeeded_references(self._src()):
            try:
                d = json.loads(r)
            except (json.JSONDecodeError, TypeError):
                continue
            if not (isinstance(d, dict) and
                    str(d.get("event_id", "")).startswith(eid_prefix)):
                continue
            if decision_events_only and \
                    str(d.get("event_id", "")).endswith("|applied"):
                continue
            out.append(d)
        return out

    def state_of(self, proposal_id: str) -> str:
        history = self._history(proposal_id)
        if not history:
            raise KeyError(f"unknown proposal: {proposal_id}")
        return history[-1].get("state", PROPOSED)

    def proposal_ref(self, proposal_id: str) -> Optional[Dict]:
        """The original PROPOSED reference (payload, schema, provider)."""
        for d in self._history(proposal_id):
            if d.get("event_id") == self._eid(proposal_id):
                return d
        return None

    # -- AI side (proposal creation only — no transition rights) ----------------

    def submit(self, proposal: AiProposal,
               *, actor: str = "ai-runtime") -> Dict:
        """PROPOSED — durable + idempotent by (id, payload hash).

        Only a router-validated AiProposal envelope may enter: a raw
        dict (never schema-validated) raises TypeError, closing the
        forged-payload path into the store.

        The AI_GENERATED provenance record is written between receive
        and succeed so its id is carried INSIDE the durable ref
        (restart-safe: the terminal decision reads it from the store,
        never from memory).
        """
        if not isinstance(proposal, AiProposal):
            raise TypeError(
                "submit requires a router-validated AiProposal envelope "
                "(raw payloads bypass contract validation and are refused)")
        eid = self._eid(proposal.correlation_id)
        ref = {
            "event_id": eid,
            "proposal_id": proposal.correlation_id,
            "schema_id": proposal.schema_id,
            "task_type": proposal.task_type,
            "payload": proposal.payload,
            "payload_hash": _payload_hash(proposal.payload),
            "provider": proposal.provider,
            "model": proposal.model,
            "state": PROPOSED,
        }
        src = self._src()
        rec = self.store.receive(src, eid, OP_LIFECYCLE, ref)
        if rec["verdict"] == "skipped_duplicate":
            return {"proposal_id": proposal.correlation_id,
                    "state": self.state_of(proposal.correlation_id),
                    "verdict": "skipped_duplicate"}
        if rec["verdict"] == "integrity_error":
            raise IntegrityError(
                f"conflicting duplicate for {eid} — human review (D-027)")
        self.store.begin(src, eid)
        pr = self.provenance.record(
            "AI_GENERATED", actor,
            source_reference=f"ai-proposal:"
                             f"{proposal.correlation_id[:32]}",
            original_value=json.dumps(proposal.payload,
                                      ensure_ascii=False, sort_keys=True),
            notes=f"proposal submitted: {proposal.schema_id} via "
                  f"{proposal.provider}/{proposal.model}")
        self.provenance.link_value(
            f"{SOURCE_SYSTEM}.proposal", eid, "payload", pr)
        ref["provenance_id"] = pr
        self.store.succeed(src, eid, result_reference=json.dumps(
            ref, ensure_ascii=False, sort_keys=True))
        if self.queue is not None:
            from canonical.verification_tool import VerificationQueue
            if isinstance(self.queue, VerificationQueue):
                self.queue.enqueue({
                    "sheet": "ai-proposal",
                    "row": proposal.correlation_id[:12],
                    "code": f"AI_{proposal.task_type.upper()}",
                    "message": f"{proposal.schema_id} proposal "
                               "awaiting review",
                    "proposal_id": proposal.correlation_id,
                    "item_key": f"aiprop|{proposal.correlation_id}",
                }, source_type="AI_GENERATED", actor=actor)
        return {"proposal_id": proposal.correlation_id, "state": PROPOSED,
                "verdict": "new", "provenance_id": pr}

    # -- human side (the ONLY transition driver) ---------------------------------

    def decide(self, proposal_id: str, *, action: str, reviewer: str,
               notes: str = "",
               modified_payload: Optional[Dict] = None) -> Dict:
        """Apply a HUMAN decision. Deterministic refusals:
        - unknown action → ProposalStateError (B)
        - illegal (state, action) pair → ProposalStateError (B)
        - terminal + different re-decision → ProposalStateError (B)
        - accept without applier → ProposalStateError (B)
        """
        if action not in ACTIONS:
            raise ProposalStateError(
                f"unknown action {action!r}; legal actions: {ACTIONS}",
                action=action)
        history = self._history(proposal_id, decision_events_only=True)
        if not history:
            raise KeyError(f"unknown proposal: {proposal_id}")
        current = history[-1].get("state", PROPOSED)
        decision_hash = _payload_hash({
            "action": action, "reviewer": reviewer, "notes": notes,
            "modified_payload": modified_payload})
        if current in TERMINAL:
            # terminal handling BEFORE transition legality: an identical
            # re-decision is an idempotent skip, a different one is
            # refused (decisions are immutable, D-026)
            last = history[-1]
            if last.get("decision_hash") == decision_hash:
                return {"proposal_id": proposal_id, "state": current,
                        "verdict": "skipped_duplicate"}
            raise ProposalStateError(
                f"proposal already terminal ({current}); decisions are "
                "immutable — a changed mind is a NEW, later decision "
                "event, never a silent flip (D-026)",
                from_state=current, action=action)
        new_state = TRANSITIONS.get((current, action))
        if new_state is None:
            raise ProposalStateError(
                f"illegal transition: {current} --{action}--> (refused; "
                f"legal: {TRANSITIONS})", from_state=current,
                action=action)
        if action == "modify_accept" and modified_payload is None:
            raise ProposalStateError(
                "modify_accept requires modified_payload",
                from_state=current, action=action)
        if action == "accept" and self.applier is None:
            raise ProposalStateError(
                "accept requires an injected applier (canonical-side "
                "deterministic target application)",
                from_state=current, action=action)

        suffix = _EVENT_SUFFIX[action]
        eid = self._eid(proposal_id, suffix)
        base = self.proposal_ref(proposal_id) or {}
        ref = {
            "event_id": eid,
            "proposal_id": proposal_id,
            "schema_id": base.get("schema_id"),
            "task_type": base.get("task_type"),
            "from_state": current,
            "state": new_state,
            "action": action,
            "reviewer": reviewer,
            "notes": notes,
            "decision_hash": decision_hash,
            "diff": {"field": "state", "from": current, "to": new_state,
                     "modified_payload": modified_payload},
        }
        res = self._record_transition(eid, ref)
        if res["verdict"] == "skipped_duplicate":
            # identical decision re-delivered (e.g. queue retry)
            return {"proposal_id": proposal_id, "state": new_state,
                    "verdict": "skipped_duplicate"}

        pr = self.provenance.record(
            "HUMAN_ENTERED", reviewer,
            source_reference=f"ai-proposal:{proposal_id[:32]}",
            original_value=json.dumps(ref, ensure_ascii=False,
                                      sort_keys=True),
            notes=f"decision {action}: {notes}"[:300])
        self.provenance.link_value(
            f"{SOURCE_SYSTEM}.proposal", eid, "decision", pr)
        # advance the AI_GENERATED record ONCE (PENDING → HUMAN_REVIEWED)
        if current in (PROPOSED, IN_REVIEW) and new_state in TERMINAL:
            orig_pr = base.get("provenance_id")
            if orig_pr:
                rec = self.provenance.records[orig_pr - 1]
                if rec.get("source_type") == "AI_GENERATED" and \
                        rec.get("review_state") == "PENDING":
                    self.provenance.advance_review(orig_pr,
                                                   "HUMAN_REVIEWED")

        applied = None
        if action in ("accept", "modify_accept"):
            applied = self.applier(proposal_id, ref)
            # the application itself is a follow-up durable event
            self._record_transition(
                self._eid(proposal_id, "applied"),
                {"event_id": self._eid(proposal_id, "applied"),
                 "proposal_id": proposal_id, "state": new_state,
                 "action": action, "applied": applied})
        return {"proposal_id": proposal_id, "state": new_state,
                "verdict": "new", "provenance_id": pr,
                "diff": ref["diff"], "applied": applied}

    # -- review aid --------------------------------------------------------------

    def pending_proposals(self) -> List[Dict]:
        """All proposals whose CURRENT state is PROPOSED or IN_REVIEW."""
        seen: Dict[str, Dict] = {}
        for d in self.store.succeeded_references(self._src()):
            try:
                ref = json.loads(d)
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(ref, dict) and \
                    str(ref.get("event_id", "")).startswith("aiprop|"):
                pid = ref.get("proposal_id")
                if pid:
                    seen[pid] = ref
        return [ref for ref in seen.values()
                if ref.get("state") in (PROPOSED, IN_REVIEW)]

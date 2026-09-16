"""Phase 8 M4 — HITL review inbox & bulk action orchestrator (D-068).

A centralized service over the EXISTING ProposalLifecycle +
VerificationQueue — no new authority surface: every decision still
flows through the human-only `decide()` with an explicit reviewer
(D-064/D-050). Guarantees:

  - deterministic inbox from durable store data only;
  - single approve / reject / edit_approve wrappers;
  - bulk_decide: per-item independence (each item completes or fails
    with its recorded error; a failure never aborts the rest and never
    leaves a half-applied item); identical re-decisions inside a bulk
    call are skipped_duplicate (M2 idempotency, unchanged); conflicting
    re-decisions are refused per item;
  - human edits re-validated through the D-062 contract BEFORE
    acceptance (Class-B refusal with provenance on invalid edits —
    never silently applied);
  - every decision emits a D-065 hitl_decision observability record
    and D-026 provenance (written by the lifecycle).
"""

import json
from typing import Dict, List, Optional

from canonical.ai_contracts import validate_ai_output
from canonical.ai_proposal_lifecycle import (
    ACCEPTED, IN_REVIEW, MODIFIED_BY_HUMAN, PROPOSED, REJECTED,
    ProposalLifecycle, ProposalStateError)
from canonical.ai_observability import (
    AiObservabilityCollector, hitl_decision_record)

ACTION_TO_STATE = {"accept": ACCEPTED, "reject": REJECTED,
                   "modify_accept": MODIFIED_BY_HUMAN}
# states an inbox item may sit in
_INBOX_STATES = (PROPOSED, IN_REVIEW)


class HitlServiceError(ValueError):
    """Service misuse (Class-B): unknown action / bad request shape."""


class HitlReviewService:
    """Review inbox + bulk orchestrator over the proposal lifecycle."""

    def __init__(self, lifecycle: ProposalLifecycle,
                 collector: Optional[AiObservabilityCollector] = None,
                 actor: str = "hitl-service"):
        self.lifecycle = lifecycle
        self.collector = collector
        self.actor = actor

    # -- inbox ----------------------------------------------------------------

    def inbox(self) -> List[Dict]:
        """Deterministic listing of pending proposals (durable data
        only — no in-process memory required for correctness)."""
        items = []
        for ref in self.lifecycle.pending_proposals():
            items.append({
                "proposal_id": ref.get("proposal_id"),
                "state": ref.get("state"),
                "task_type": ref.get("task_type"),
                "schema_id": ref.get("schema_id"),
                "provider": ref.get("provider"),
                "model": ref.get("model"),
                "template_id": ref.get("template_id"),
                "template_hash": ref.get("template_hash"),
            })
        items.sort(key=lambda i: (i["task_type"] or "",
                                  i["proposal_id"]))
        return items

    # -- single actions --------------------------------------------------------

    def _observe(self, item: Dict, res: Dict, action: str,
                 reviewer: str) -> None:
        if self.collector is None:
            return
        try:
            self.collector.record(
                correlation_id=item.get("proposal_id", "n/a"),
                stage="hitl_decision", task_type=item.get("task_type", ""),
                status=str(res.get("state", "")),
                provider=item.get("provider", ""),
                model=item.get("model", ""),
                template_id=item.get("template_id", ""),
                template_hash=item.get("template_hash", ""),
                hitl_decision=hitl_decision_record(action),
                notes=f"reviewer={reviewer}; "
                      f"verdict={res.get('verdict', 'new')}")
        except Exception:
            pass  # observability must never break a decision

    def approve(self, proposal_id: str, *, reviewer: str,
                notes: str = "") -> Dict:
        return self._decide(proposal_id, "accept", reviewer, notes)

    def reject(self, proposal_id: str, *, reviewer: str,
               notes: str = "") -> Dict:
        return self._decide(proposal_id, "reject", reviewer, notes)

    def edit_approve(self, proposal_id: str, modified_payload: Dict, *,
                     reviewer: str, notes: str = "") -> Dict:
        ref = self.lifecycle.proposal_ref(proposal_id)
        if ref is None:
            raise KeyError(f"unknown proposal: {proposal_id}")
        schema_id = ref.get("schema_id")
        validation = validate_ai_output(schema_id, modified_payload)
        if not validation.get("valid"):
            raise HitlServiceError(
                f"human edit failed the {schema_id} contract (Class B, "
                f"never silently applied): {validation.get('errors')}")
        return self._decide(proposal_id, "modify_accept", reviewer,
                            notes, modified_payload=modified_payload)

    def _decide(self, proposal_id: str, action: str, reviewer: str,
                notes: str = "", modified_payload: Optional[Dict] = None
                ) -> Dict:
        ref = self.lifecycle.proposal_ref(proposal_id)
        if ref is None:
            raise KeyError(f"unknown proposal: {proposal_id}")
        res = self.lifecycle.decide(
            proposal_id, action=action, reviewer=reviewer,
            notes=notes, modified_payload=modified_payload)
        self._observe(ref, res, action, reviewer)
        return dict(res, action=action, reviewer=reviewer)

    # -- bulk orchestration ------------------------------------------------------

    def bulk_decide(self, decisions: List[Dict], *, reviewer: str
                    ) -> Dict:
        """Process an explicit list of decision items with per-item
        independence.

        Each item: {"proposal_id", "action", "notes"?, "modified_" +
        "payload"?} with action in approve|reject|edit_approve (the
        lifecycle's submit_review is deliberately NOT exposed here —
        the inbox drives terminal human decisions). Returns per-item
        results; the batch NEVER aborts on individual failures and
        never leaves a half-applied item (each lifecycle decision is
        one durable event).
        """
        if not isinstance(reviewer, str) or not reviewer.strip():
            raise HitlServiceError(
                "bulk_decide requires a non-empty reviewer (human-only "
                "decisions, D-050/D-064)")
        results: List[Dict] = []
        summary = {"decided": 0, "skipped_duplicate": 0, "failed": 0}
        for idx, item in enumerate(decisions):
            pid = item.get("proposal_id")
            action = item.get("action")
            try:
                if action == "approve":
                    res = self.approve(pid, reviewer=reviewer,
                                       notes=item.get("notes", ""))
                elif action == "reject":
                    res = self.reject(pid, reviewer=reviewer,
                                      notes=item.get("notes", ""))
                elif action == "edit_approve":
                    res = self.edit_approve(
                        pid, item.get("modified_payload"),
                        reviewer=reviewer,
                        notes=item.get("notes", ""))
                else:
                    raise HitlServiceError(
                        f"unknown bulk action {action!r} at item {idx} "
                        f"(legal: approve|reject|edit_approve)")
            except (HitlServiceError, ProposalStateError, KeyError) as exc:
                results.append({"index": idx, "proposal_id": pid,
                                "action": action, "ok": False,
                                "error": str(exc),
                                "error_class": "B"})
                summary["failed"] += 1
                continue
            ok = res.get("verdict") != "skipped_duplicate"
            results.append({"index": idx, "proposal_id": pid,
                            "action": action, "ok": True,
                            "state": res.get("state"),
                            "verdict": res.get("verdict")})
            if res.get("verdict") == "skipped_duplicate":
                summary["skipped_duplicate"] += 1
            else:
                summary["decided"] += 1
        return {"reviewer": reviewer, "results": results,
                "summary": summary}

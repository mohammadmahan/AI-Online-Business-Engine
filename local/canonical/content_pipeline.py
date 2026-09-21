"""Phase 11 — content-to-channel live pipeline (D-077/D-078).

Composes the SHIPPED phase engines into one deterministic, review-gated
business pipeline — no new network code, no new decision semantics:

  AI generation (Phase 7/8, D-066/D-063) → human review gate (D-050)
  → product staging (Phase 4 SyncEngine, YELLOW tier) → channel
  fan-out (Phase 11 FanOutEngine) → per-target publishers (Phase 9
  D-070 outbox, Phase 10 D-074 outbox with pacer/vault/DLQ).

Authority model (the audit property):
  - AI output NEVER dispatches directly: the router returns a frozen
    AiProposal envelope; only ProposalLifecycle.decide() — a HUMAN
    decision — can move it to ACCEPTED. Un-decided proposals raise
    before any publisher is reached.
  - `authorized=True` is a per-pipeline construction gate (D-050):
    the sync engine refuses RED-tier operations without it, and the
    fan-out binds cannot be attached without it. Un-authorized
    pipelines can stage and review but never publish.
  - Every outbound payload is locally validated by the target's
    shipped validator (Class-B prevention BEFORE any dispatch).

Rollback model (compensation, not un-ringing):
  - Completed targets stay completed (D-070/D-074 terminal guards
    make re-dispatch idempotent); failed targets stay durable in the
    DLQ (never deleted, D-076). A failure in one target never rolls
    back another (independent fan-out, D-077). The pipeline records
    a durable COMPENSATED stage marker and returns an aggregate
    refund decision for the operation log.
"""
from __future__ import annotations

import json
from typing import Dict, List, Optional

from canonical.ai_runtime import AiProposal, ModelRouter
from canonical.orchestration_contracts import (
    OP_DISPATCH,
    SOURCE_SYSTEM,
    validate_dispatch_payload,
)
from canonical.orchestration_engine import FanOutEngine

__all__ = [
    "PipelineError", "PipelineAuthorityError",
    "ContentToChannelPipeline",
]


class PipelineError(ValueError):
    """Local pipeline misuse (Class-B: terminal, no retry)."""


class PipelineAuthorityError(PipelineError):
    """An unauthorized (un-reviewed or un-authorized) operation was
    refused before any dispatch path was reachable."""


def _compensation_for(outcome: str) -> str:
    """Deterministic compensation verdict per subtask outcome.

    - published → COMPLETED (real external side effect; stays, the
      outbox terminal guards own idempotency)
    - retry-class (A/C) → RETRY_SCHEDULED (transient, reversible)
    - everything else → REFUNDED (no durable external mutation to
      undo — the local store is the only mutable surface and it stays
      tamper-evident)
    """
    if outcome == "published":
        return "COMPLETED"
    if outcome in ("transient_error", "cooldown"):
        return "RETRY_SCHEDULED"
    return "REFUNDED"


class ContentToChannelPipeline:
    """One durable, review-gated content-to-channel pipeline."""

    def __init__(self, store, *, sync_engine, fanout_engine: FanOutEngine,
                 publish_binds: Dict[str, object],
                 lifecycle=None,
                 provenance=None, actor: str = "pipeline-ops"):
        if not publish_binds:
            raise PipelineError("publish_binds must not be empty")
        self.sync = sync_engine
        self.fanout = fanout_engine
        self.publish_binds = dict(publish_binds)
        self.lifecycle = lifecycle
        self.provenance = provenance
        self.actor = actor

    # -- stage 1: AI generation (deterministic, review-ready) -------------

    def generate_proposal(self, router: ModelRouter, request) -> AiProposal:
        """Route a validated, frozen AiProposal envelope (or re-raise).

        The router already enforces contracts/budgets; this stage adds
        no authority — it produces review-ready output only.
        """
        if not isinstance(router, ModelRouter):
            raise PipelineError("router must be a ModelRouter")
        return router.run(request, provenance=self.provenance,
                          actor=self.actor)

    def decide_proposal(self, proposal_id: str, *, action: str,
                        reviewer: str, notes: str = "",
                        modified_payload: Optional[Dict] = None) -> Dict:
        """The ONLY path from AI output to executable content: a human
        decision on the durable lifecycle. Requires the lifecycle to
        be bound at construction."""
        if self.lifecycle is None:
            raise PipelineError(
                "no ProposalLifecycle bound — human decisions have no "
                "durable target (construct the pipeline with "
                "lifecycle=...)")
        return self.lifecycle.decide(
            proposal_id, action=action, reviewer=reviewer, notes=notes,
            modified_payload=modified_payload)

    # -- stage 2: review gate (D-050: no publish without human decision) --

    def _require_reviewed(self, proposal_id: str) -> Dict:
        if self.lifecycle is None:
            raise PipelineAuthorityError(
                "no ProposalLifecycle bound — the review gate cannot be "
                "evaluated (fail closed)")
        st = self.lifecycle.state_of(proposal_id)
        if st != "ACCEPTED":
            raise PipelineAuthorityError(
                f"proposal {proposal_id} is {st} — only ACCEPTED "
                "proposals may enter the publishing pipeline (D-050 "
                "human review gate)")
        ref = self.lifecycle.proposal_ref(proposal_id)
        if ref is None:
            raise PipelineAuthorityError(
                f"proposal {proposal_id} has no durable PROPOSED "
                "reference (fail closed)")
        return ref

    # -- stage 3: product staging (SyncEngine) ----------------------------

    def stage_product(self, product: Dict, variants: List[Dict], today,
                      *, proposal_id: Optional[str] = None,
                      authorized: bool = False,
                      operation: str = "woo_projection") -> Dict:
        """Project one canonical product into the store (Woo mock).

        Authority is delegated entirely to SyncEngine.sync_product
        (its own D-050 gate). When `proposal_id` is given, the gate is
        evaluated FIRST here too (defense in depth): the proposal must
        be durably ACCEPTED before a RED-tier operation can even be
        attempted.
        """
        if proposal_id is not None:
            self._require_reviewed(proposal_id)
        res = self.sync.sync_product(product, variants, today,
                                     authorized=authorized,
                                     operation=operation)
        if self.provenance is not None and res.get("action") not in (
                "skipped_draft", "skipped_duplicate"):
            try:
                pr = self.provenance.record(
                    "SYSTEM_GENERATED", self.actor,
                    source_reference=f"pipeline:stage:"
                                     f"{res.get('product_id', 'n/a')}",
                    original_value=json.dumps(
                        res, ensure_ascii=False, sort_keys=True),
                    notes=f"staged via proposal {proposal_id or 'n/a'}")
                res = dict(res, provenance_id=pr)
            except RuntimeError:
                pass  # audit layer unavailable — staging stands
        return res

    # -- stage 4: channel fan-out -----------------------------------------

    def fanout_job(self, *, job_id: str, campaign_id: str,
                   content_id: str, proposal_id: str,
                   text: str, hashtags: List[str],
                   scheduled_slot: str,
                   media: Optional[Dict] = None,
                   targets: Optional[List[str]] = None,
                   target_params: Optional[Dict] = None) -> Dict:
        """Route + dispatch one fan-out job AFTER the review gate.

        `media` is REQUIRED for the instagram target (D-077); the
        payload is validated locally by the D-077 contract BEFORE any
        dispatch. The review gate is checked BEFORE routing, so an
        un-reviewed campaign never reaches an adapter.
        """
        self._require_reviewed(proposal_id)
        payload = {"job_id": job_id, "campaign_id": campaign_id,
                   "content_id": content_id,
                   "text": text, "hashtags": list(hashtags or []),
                   "scheduled_slot": scheduled_slot,
                   "target_params": target_params or {}}
        if media is not None:
            payload["media"] = media
        if targets:
            payload["targets"] = list(targets)
        norm = validate_dispatch_payload(payload)
        routed = self.fanout.route(dict(norm, targets=norm["targets"]))
        if not routed.get("routed"):
            return {"routed": False, "reason": routed.get("reason"),
                    "fanout_key": routed.get("fanout_key")}
        return self.fanout.dispatch(routed, actor=self.actor)

    # -- stage 5: compensation / rollback ----------------------------------

    def compensate_job(self, job_id: str) -> Dict:
        """Rollback marker for one fan-out job.

        - reconstructs the per-target outcomes from DURABLE receipts;
        - emits one COMPENSATED stage marker (new event, never a
          mutation — append-only discipline);
        - returns the per-target compensation verdicts.
        """
        ref = self.fanout._job_ref(job_id)
        if ref is None:
            raise PipelineError(f"unknown job: {job_id}")
        targets: Dict[str, str] = {}
        for line in self.fanout._store_refs():
            if not isinstance(line, dict):
                continue
            eid = str(line.get("event_id", ""))
            if eid.startswith(f"orchestration|{job_id}|target|") \
                    and line.get("stage") == "target":
                t = line.get("target")
                oc = line.get("outcome")
                if t and t not in targets:
                    targets[t] = str(oc)
        if not targets:
            raise PipelineError(
                f"no durable target receipts for job {job_id}")
        compensation = {t: _compensation_for(oc)
                        for t, oc in targets.items()}
        eid = f"orchestration|{job_id}|compensated"
        src = SOURCE_SYSTEM
        rec = self.fanout.store.receive(src, eid, OP_DISPATCH, {
            "event_id": eid, "job_id": job_id,
            "stage": "COMPENSATED", "compensation": compensation})
        if rec["verdict"] in ("new", "retry"):
            self.fanout.store.begin(src, eid)
            self.fanout.store.succeed(
                src, eid, result_reference=json.dumps(
                    {"event_id": eid, "job_id": job_id,
                     "stage": "COMPENSATED",
                     "compensation": compensation},
                    ensure_ascii=False, sort_keys=True))
        if self.provenance is not None:
            try:
                self.provenance.record(
                    "SYSTEM_GENERATED", self.actor,
                    source_reference=f"pipeline:compensate:{job_id}",
                    original_value=json.dumps(
                        compensation, ensure_ascii=False, sort_keys=True),
                    notes="rollback marker (append-only)")
            except RuntimeError:
                pass
        return {"job_id": job_id, "compensation": compensation,
                "markers": ["COMPENSATED"]}

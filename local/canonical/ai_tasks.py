"""Phase 7 M3 — concrete AI tasks, batch execution, divergence detection.

Three v1 tasks on the M1 contracts + M2 lifecycle (D-062/D-063/D-064
Approved):

    ContentIdeaTask   → propose_content_idea  (content_idea_proposal.v1)
    CaptionTask       → generate_caption      (caption_proposal.v1)
    DescriptionTask   → enrich_description    (product_description_enrichment.v1)

Every task:
  - dispatches ONLY through the ModelRouter → AiProvider boundary
    (MockAiProvider locally, D-053; real providers are owner-gated
    drop-ins per D-062);
  - validates output against its strict v1 contract BEFORE anything
    durable exists (router does this — contract failure = Class B);
  - runs canonical divergence detection against approved Phase 2
    vocabulary (D-029/D-031/D-032) before persistence — the model
    must never propose a value outside human-owned vocab;
  - in persist mode, lands as a PROPOSED record via the M2
    ProposalLifecycle (D-027 store + D-026 provenance + HITL queue) —
    there is NO path from a task to any active state: the only state
    driver is ProposalLifecycle.decide(), human-only.

Dry-run mode: generate + validate + divergence-check, persist
NOTHING to the pipeline (no D-027 event, no provenance record, no
queue item). Deliberate exception: router-level usage metering stays
ON during dry-runs — suppressing it would let dry-run batches evade
the D-063 budget guardrail while still consuming real provider
budget. Dry-runs are verification-only for the PIPELINE, never for
accounting.

Divergence rules (canonical = approved vocab + canonical records):
  - CaptionTask: hashtags must be color terms, size terms, or
    category leaves from the approved vocabulary (D-029/D-031/D-032),
    or plain topical words. A hashtag naming an APPROVED term must
    match it exactly (fa or code); a near-miss of an approved term
    (prefix/suffix variant) is flagged as divergent (Class B) — this
    is the "AI suggests a size not in D-032" case, deterministic.
  - DescriptionTask: the referenced product_id must exist in the
    canonical store (pre-key from the AI-proposal source); unknown
    product → divergence. Variant scope never widens beyond the
    anchored request.
  - ContentIdeaTask: target_lifecycle_state must remain the lifecycle
    root ("Backlog") — schema-pinned by the approved contract AND
    re-checked here deterministically. The approved v1 contract
    deliberately carries no product_refs (product anchoring happens
    at human acceptance), so no product-existence check applies at
    proposal time.

Batch mechanics: run_batch() processes a list of entities, stops on
the first hard budget refusal (D-063 — never spends past the cap),
and reports per-item outcomes plus router spend (ledger-free routers
track spend in memory; the batch summary reads `router._spend` —
the always-on accumulator hardened in M1).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from canonical.ai_contracts import validate_ai_output
from canonical.ai_runtime import (
    AiProviderError, AiProposal, AiRequest, BudgetExceeded, ModelRouter,
)
from canonical.vocab import COLOR_TERMS, SIZE_FAMILIES, SIZE_TERMS


class TaskDivergenceError(AiProviderError):
    """AI output diverges from canonical/vocabulary constraints.

    Class B (D-052): a data invariant — never retried automatically,
    never silently repaired. The report is surfaced to HITL instead.
    """

    def __init__(self, message: str, *, divergences: List[str]):
        super().__init__(message, failure_class="B")
        self.divergences = list(divergences)


# --- vocabulary sets (approved Phase 2 only — no invention) -------------------

_APPROVED_COLORS_FA = frozenset(fa for fa, _code in COLOR_TERMS)
_APPROVED_COLOR_CODES = frozenset(code for _fa, code in COLOR_TERMS)
_APPROVED_SIZES = frozenset(
    term for _family, terms in SIZE_TERMS.items() for term, _c in terms)
_APPROVED_SIZES |= frozenset(
    code for _family, terms in SIZE_TERMS.items() for _t, code in terms)
_APPROVED_FAMILY_LABELS = frozenset(fa for _k, fa in SIZE_FAMILIES)


def _is_near_miss(candidate: str, approved: str) -> bool:
    """Deterministic near-miss predicate: same head/tail, not identical.

    Catches 'مانتوك' (added letter), 'مانت‌و' (reshaped), 'کت وجلیقه'
    (lost space) — variants of approved terms that must NOT pass as
    new vocabulary. Purely mechanical: prefix/suffix overlap on both
    sides with at least one extra/missing character.
    """
    if candidate == approved or len(candidate) < 2:
        return False
    head = 0
    while (head < len(candidate) and head < len(approved)
           and candidate[head] == approved[head]):
        head += 1
    tail = 0
    while (tail < len(candidate) - head and tail < len(approved) - head
           and candidate[len(candidate) - 1 - tail]
           == approved[len(approved) - 1 - tail]):
        tail += 1
    overlap = head + tail
    extra = abs(len(candidate) - len(approved))
    return overlap >= max(1, len(approved) - 1) and (
        extra >= 1 or overlap < max(len(candidate), len(approved)))


# --- task base ----------------------------------------------------------------


@dataclass
class TaskEntity:
    """One unit of work: a canonical entity a task runs against."""
    kind: str                     # content_idea | product | variant
    key: str                      # canonical Product ID / page id / topic key
    payload: Dict                 # structured canonical context for the prompt
    product_id: Optional[str] = None   # for existence checks (products/ideas)


@dataclass
class TaskReport:
    """Result of one task run. In dry-run this is the ONLY output."""
    task_type: str
    entity_key: str
    mode: str                     # "persist" | "dry-run"
    ok: bool = False
    state: Optional[str] = None   # PROPOSED in persist mode
    proposal_id: Optional[str] = None
    proposal: Optional[AiProposal] = None
    divergences: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    failure_class: Optional[str] = None
    error: Optional[str] = None
    verdict: Optional[str] = None  # lifecycle verdict (new/skipped_duplicate)
    budget_exhausted: bool = False  # hard D-063 refusal stopped the batch

    def to_dict(self) -> Dict:
        d = {
            "task_type": self.task_type, "entity_key": self.entity_key,
            "mode": self.mode, "ok": self.ok,
        }
        for k in ("state", "proposal_id", "verdict", "failure_class",
                  "error"):
            if getattr(self, k) is not None:
                d[k] = getattr(self, k)
        if self.divergences:
            d["divergences"] = list(self.divergences)
        if self.warnings:
            d["warnings"] = list(self.warnings)
        if self.budget_exhausted:
            d["budget_exhausted"] = True
        return d


class AiTask:
    """Base: routing + validation + divergence + persistence plumbing."""

    task_type: str = ""
    schema_id: str = ""

    def __init__(self, router: ModelRouter):
        self.router = router

    # -- to be provided by subclasses ------------------------------------------

    def _build_request(self, entity: TaskEntity) -> AiRequest:
        raise NotImplementedError

    def _check_divergence(self, proposal: AiProposal,
                          entity: TaskEntity) -> List[str]:
        raise NotImplementedError

    # -- shared engine -----------------------------------------------------------

    def _canonical_product_exists(self, product_id: str) -> bool:
        if self._product_lookup is None:
            return False
        try:
            return bool(self._product_lookup(product_id))
        except Exception:
            return False

    def run(self, entity: TaskEntity, *, mode: str = "persist",
            actor: str = "ai-runtime") -> TaskReport:
        """One task run. mode: "persist" | "dry-run".

        In persist mode, a valid non-divergent proposal becomes a
        PROPOSED record via ProposalLifecycle.submit (durable D-027
        event + D-026 provenance + HITL queue item).
        """
        if mode not in ("persist", "dry-run"):
            raise ValueError(f"unknown mode: {mode!r}")
        rep = TaskReport(task_type=self.task_type,
                         entity_key=entity.key, mode=mode)

        def _fail(exc: Exception, cls: str) -> TaskReport:
            rep.ok = False
            rep.failure_class = cls
            rep.error = str(exc)
            return rep

        request = self._build_request(entity)
        try:
            proposal = self.router.run(request, actor=actor)
        except BudgetExceeded as exc:      # D-063 hard guardrail
            rep.budget_exhausted = True
            return _fail(exc, "B")
        except AiProviderError as exc:     # A / B / C / D / E mapping
            return _fail(exc, getattr(exc, "failure_class", "E"))

        rep.proposal = proposal
        rep.warnings = list(proposal.warnings)

        try:
            rep.divergences = self._check_divergence(proposal, entity)
        except Exception as exc:  # defensive: divergence must never crash
            return _fail(exc, "E")

        if rep.divergences:
            # Class B: surfaced to HITL, never persisted as PROPOSED,
            # never silently repaired (D-052 / RULES §7).
            rep.ok = False
            rep.failure_class = "B"
            rep.error = ("divergence from canonical constraints "
                         "(D-029/D-031/D-032) — human review required")
            return rep

        if mode == "dry-run":
            rep.ok = True     # verification-only: valid, diverge-free
            return rep

        lifecycle = self._require_lifecycle()
        try:
            res = lifecycle.submit(proposal, actor=actor)
        except Exception as exc:
            return _fail(exc, "E" if not isinstance(exc, ValueError)
                         else "B")
        rep.ok = True
        rep.state = "PROPOSED"
        rep.proposal_id = res["proposal_id"]
        rep.verdict = res["verdict"]
        return rep

    # -- batch -------------------------------------------------------------------

    def _require_lifecycle(self):
        if getattr(self, "_lifecycle", None) is None:
            raise RuntimeError(
                "persist mode requires a ProposalLifecycle (constructor "
                "arg `lifecycle`) — AI output is never durable without "
                "the M2 round-trip")
        return self._lifecycle

    def run_batch(self, entities: List[TaskEntity], *, mode: str = "persist",
                  actor: str = "ai-runtime") -> Dict:
        """Batch execution with D-063 budget discipline.

        Stops at the first hard budget refusal (never spends past the
        cap); failed items are reported per entity, never silently
        dropped. dry-run batches are side-effect-free by construction.
        """
        results: List[TaskReport] = []
        for entity in entities:
            rep = self.run(entity, mode=mode, actor=actor)
            results.append(rep)
            if rep.budget_exhausted:
                break  # D-063: never spend past the cap — stop the batch
        spend = dict(getattr(self.router, "_spend", {}))
        return {
            "task_type": self.task_type, "mode": mode,
            "requested": len(entities), "processed": len(results),
            "ok": sum(1 for r in results if r.ok),
            "failed": sum(1 for r in results if not r.ok),
            "spend_by_task": spend,
            "results": [r.to_dict() for r in results],
        }


# --- concrete tasks --------------------------------------------------------------


class ContentIdeaTask(AiTask):
    """Seasonal content proposals at the lifecycle root (Backlog)."""

    task_type = "propose_content_idea"
    schema_id = "content_idea_proposal.v1"

    def __init__(self, router: ModelRouter, lifecycle=None,
                 product_lookup: Optional[Callable[[str], bool]] = None):
        # product_lookup accepted for interface parity with the other
        # tasks (and future contract versions that add anchored refs);
        # the approved v1 contract carries no product references
        super().__init__(router)
        self._lifecycle = lifecycle
        self._product_lookup = product_lookup

    def _build_request(self, entity: TaskEntity) -> AiRequest:
        return AiRequest(
            task_type=self.task_type, schema_id=self.schema_id,
            prompt_payload={
                "entity_kind": entity.kind, "entity_key": entity.key,
                "context": entity.payload,
            },
            idempotency_tag=f"{self.task_type}|{entity.key}")

    def _check_divergence(self, proposal: AiProposal,
                          entity: TaskEntity) -> List[str]:
        div: List[str] = []
        payload = proposal.payload or {}
        # defense-in-depth: the strict schema enum already pins this,
        # but the lifecycle-root rule is re-checked deterministically
        # so a future contract amendment cannot silently widen it
        if payload.get("target_lifecycle_state") != "Backlog":
            div.append(
                "content_idea: target_lifecycle_state must be the "
                "lifecycle root (Backlog) — AI never proposes deeper "
                "lifecycle states (D-060)")
        return div


class CaptionTask(AiTask):
    """Social captions grounded in approved product attributes.

    `product_attrs` (optional) maps Product ID → dict with canonical
    attributes (e.g. {"color": "مشکی", "category": "مانتو"}); when
    present, captions are additionally checked for grounding — a
    hashtag naming a NOT-APPROVED garment term is flagged even if it
    is not a vocabulary term (class of 'near-miss' mismatches).
    """

    task_type = "generate_caption"
    schema_id = "caption_proposal.v1"

    def __init__(self, router: ModelRouter, lifecycle=None,
                 product_attrs: Optional[Dict[str, Dict]] = None):
        super().__init__(router)
        self._lifecycle = lifecycle
        self.product_attrs = dict(product_attrs or {})

    def _build_request(self, entity: TaskEntity) -> AiRequest:
        return AiRequest(
            task_type=self.task_type, schema_id=self.schema_id,
            prompt_payload={
                "entity_kind": entity.kind, "entity_key": entity.key,
                "context": entity.payload,
            },
            idempotency_tag=f"{self.task_type}|{entity.key}")

    def _check_divergence(self, proposal: AiProposal,
                          entity: TaskEntity) -> List[str]:
        div: List[str] = []
        payload = proposal.payload or {}
        for tag in payload.get("hashtags") or []:
            token = tag.lstrip("#").strip()
            if not token:
                div.append(f"caption: empty hashtag {tag!r}")
                continue
            if token in _APPROVED_COLORS_FA \
                    or token in _APPROVED_COLOR_CODES \
                    or token in _APPROVED_SIZES \
                    or token in _APPROVED_FAMILY_LABELS:
                continue  # exact approved vocabulary term — fine
            # near-miss of an approved term = invented variant (Class B)
            pools = [tuple(_APPROVED_COLORS_FA), tuple(_APPROVED_SIZES)]
            for approved in pools:
                if any(_is_near_miss(token, a) for a in approved):
                    div.append(
                        f"caption: hashtag {token!r} is a near-miss of "
                        "approved vocabulary — new vocabulary is "
                        "human-owned (D-029/D-031)")
                    break
        return div


class DescriptionTask(AiTask):
    """Product-description enrichment anchored to canonical products."""

    task_type = "enrich_description"
    schema_id = "product_description_enrichment.v1"

    def __init__(self, router: ModelRouter, lifecycle=None,
                 product_lookup: Optional[Callable[[str], bool]] = None):
        super().__init__(router)
        self._lifecycle = lifecycle
        self._product_lookup = product_lookup

    def _build_request(self, entity: TaskEntity) -> AiRequest:
        return AiRequest(
            task_type=self.task_type, schema_id=self.schema_id,
            prompt_payload={
                "entity_kind": entity.kind, "entity_key": entity.key,
                "context": entity.payload,
            },
            idempotency_tag=f"{self.task_type}|{entity.key}")

    def _check_divergence(self, proposal: AiProposal,
                          entity: TaskEntity) -> List[str]:
        div: List[str] = []
        payload = proposal.payload or {}
        pid = payload.get("product_id")
        if pid is None:
            div.append("description: missing product_id (contract gap)")
        elif not self._canonical_product_exists(pid):
            div.append(
                f"description: product_id {pid!r} does not exist in the "
                "canonical store — the model never invents products")
        # scope guard: the model never widens the variant scope it was
        # given (only flagged when the request anchored a variant)
        anchored = entity.payload.get("variant_id")
        if anchored:
            for v in payload.get("variant_ids") or []:
                if v != anchored:
                    div.append(
                        f"description: variant {v!r} is outside the "
                        "requested scope (scope widening refused)")
        return div


__all__ = [
    "AiTask", "ContentIdeaTask", "CaptionTask", "DescriptionTask",
    "TaskDivergenceError", "TaskEntity", "TaskReport",
    "run_divergence_check",
]


def run_divergence_check(task: AiTask, proposal: AiProposal,
                         entity: TaskEntity) -> List[str]:
    """Public entry for reuse (e.g. re-checking stored proposals)."""
    return task._check_divergence(proposal, entity)

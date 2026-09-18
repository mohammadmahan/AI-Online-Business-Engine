"""Phase 25 M2 — reconciliation & self-healing primitives (D-135).

Pure orchestration of RECOVERY over the established durable
surfaces; every backend/reader is injected (RULES §35):

  - `reclaim_stranded` — stranded-lock sweep: an acquired lock row
    with no recorded outcome is reclaimed deterministically (the
    crashed holder loses it; no phantom rows before or after).
  - `rebuild_from_refs` — crash-restart reconstitution: state is
    rebuilt ONLY from durable D-027 `succeeded_references` rows
    (no in-process cache is consulted or required).
  - `play_flow_with_recovery` — D-134 flow-level recovery: a Class-A
    stage failure is retried under the D-126 `RetryPolicy`
    (replay of the whole flow — every engine is idempotent by
    D-027, so replay re-verifies instead of duplicating);
    Class-B/C/D/E are terminal at flow level (no auto-retry).

No I/O imports.
"""
from __future__ import annotations

import json
from typing import Callable, Dict, List, Optional

from canonical.e2e_contracts import ConductorError
from canonical.e2e_conductor import FlowConductor, FlowResult
from canonical.resilience import RetryPolicy, run_with_retry

__all__ = [
    "reclaim_stranded", "rebuild_from_refs",
    "play_flow_with_recovery", "replay_outbox",
]


def reclaim_stranded(locks, keys: List[str], *, claimant: str,
                     max_held: Optional[int] = None,
                     held_for: Optional[Dict[str, int]] = None) -> Dict:
    """Sweep stranded locks: an acquired row with no `outcome` key
    (and, when `max_held` is given, held longer than it) is
    finalized as `reclaimed`. Deterministic; idempotent (a second
    sweep over the same keys finds nothing stranded)."""
    reclaimed: List[str] = []
    live: List[str] = []
    for key in keys:
        row = locks.get(key)
        if not row:
            continue  # vanished rows are never resurrected (D-070)
        if row.get("outcome"):
            live.append(key)
            continue
        if max_held is not None:
            held = int((held_for or {}).get(key, 0))
            if held <= max_held:
                live.append(key)
                continue
        locks.finalize(key, {
            "outcome": "reclaimed",
            "reclaimed_by": claimant,
            "original_claim": row,
        })
        reclaimed.append(key)
    return {"reclaimed": reclaimed, "live": live,
            "phantom_rows": 0}


def rebuild_from_refs(refs: List[str]) -> Dict:
    """Reconstitute flow state purely from durable result_reference
    rows (JSON strings written by the engines). Unknown rows are
    skipped; malformed JSON rows are skipped (they are evidence for
    the audit trail, not state)."""
    state: Dict = {"events": 0, "orders": {}}
    for raw in refs:
        try:
            ref = json.loads(raw)
        except (TypeError, ValueError):
            continue
        state["events"] += 1
        okey = ref.get("order_key") if isinstance(ref, dict) else None
        if okey and ref.get("state"):
            state["orders"][okey] = ref["state"]
    return state


def play_flow_with_recovery(conductor: FlowConductor, initial: Dict,
                            *, policy: RetryPolicy,
                            classify: Optional[Callable] = None,
                            on_retry: Optional[Callable] = None) -> Dict:
    """Run the flow; on failure classify the stage error (D-052) and
    retry ONLY Class-A by replaying the flow (idempotent engines).
    Non-retryable classes return immediately with their verdict."""
    def attempt(n: int):
        # Same flow ⇒ same root trace (trace derivation uses the flow
        # seed, NOT the attempt number); the attempt number rides in
        # the context (audit metadata) and in each stage's causal
        # chain — so retries are replay, never a new identity.
        seed = dict(initial, attempt_no=n)
        result = conductor.run(seed)
        if result.ok:
            return result
        # the failing stage's audited record carries the error class
        last = result.stages[-1]
        err_cls = (last.get("record", {}).get("payload", {})
                   .get("error_class"))
        raise StageFailure(err_cls or "E",
                           last.get("stage", "unknown"))

    clock: List[int] = []
    verdict = run_with_retry(policy, attempt, clock=clock,
                             classify=classify)
    out = {"outcome": verdict["outcome"],
           "attempts": verdict["attempts"],
           "failure_class": verdict["failure_class"],
           "backoff_total": verdict["backoff_total"],
           "clock": list(clock)}
    if verdict["ok"]:
        res: FlowResult = verdict["result"]
        out["flow"] = {"ok": res.ok, "stages": len(res.stages),
                       "outputs": res.outputs}
    return out


def replay_outbox(store, source_system: str, effect: Callable) -> Dict:
    """Outbox reconciliation (D-135): the D-027 store IS the outbox.
    Re-run `effect(result_reference)` for every durable succeeded
    event; exactly-once semantics come from the engine behind the
    effect (its D-027 dedup returns `skipped_duplicate` on replay).
    Effect exceptions are collected, never swallowed silently."""
    refs = store.succeeded_references(source_system)
    ok, errors = 0, []
    for ref in refs:
        try:
            effect(ref)
            ok += 1
        except Exception as exc:  # noqa: BLE001 — evidence, not silence
            errors.append({"ref": str(ref)[:120],
                           "error_class": (getattr(exc, "failure_class",
                                                  None) or "E"),
                           "error": str(exc)[:200]})
    return {"source_system": source_system, "refs": len(refs),
            "effects_ok": ok, "errors": errors}


class StageFailure(Exception):
    """Carries the audited D-052 class of a failed flow stage so the
    retry policy can route it (A retries; B/C/E terminal; D
    quarantine)."""

    def __init__(self, failure_class: str, stage: str):
        super().__init__(f"stage {stage} failed (class {failure_class})")
        self.failure_class = failure_class
        self.stage = stage

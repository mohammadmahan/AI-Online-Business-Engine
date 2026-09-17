"""Phase 18 M3 — decision dispatcher & ingestion bridge (D-107).

Two seams, zero cross-module imports:

  - `HitlIngestionBridge`: consumes Phase 17 DISPATCHED_TO_HITL
    insights through an INJECTED `insight_source` callable (the
    caller wires the analyst vault read) and opens exactly one
    INSIGHT_REVIEW ticket per insight — idempotent via the engine's
    ingest_key dedup. The hitl module never imports analyst modules.
  - `HitlDispatcher`: applies APPROVED/MODIFIED resolutions by
    invoking INJECTED command dispatchers keyed by queue_type
    (INSIGHT_REVIEW → analyst recommendation apply; PUBLISH_GATE →
    Phase 15 slot unblock; ORDER_OVERRIDE → Phase 12 OMS
    compensation; ASSET_FLAG → Phase 16 asset flag). Idempotency
    (D-107): the applied gate is a D-027 exactly-once event — a
    repeated approval/rejection signal produces ZERO duplicate
    side-effects. Dispatcher failures are recorded, never silent.

Pure command shapes (`command_for`) make the downstream contract
explicit without coupling to any downstream module. No network, no
AI SDKs, no wall clock.
"""

from typing import Callable, Dict, List, Optional

from canonical.hitl_contracts import (
    QT_ASSET_FLAG,
    QT_INSIGHT_REVIEW,
    QT_ORDER_OVERRIDE,
    QT_PUBLISH_GATE,
    ST_APPROVED,
    ST_MODIFIED,
)
from canonical.hitl_engine import HitlEngine


# --- command shapes (pure — the downstream contract) --------------------------------

_COMMAND_BY_QUEUE = {
    QT_INSIGHT_REVIEW: "apply_analyst_recommendation",
    QT_PUBLISH_GATE: "unblock_publishing_slot",
    QT_ORDER_OVERRIDE: "oms_compensation",
    QT_ASSET_FLAG: "apply_asset_flag",
}


def command_for(ticket: Dict) -> Dict:
    """The command a downstream dispatcher receives for this ticket:
    explicit, queue-typed, carrying the resolution + any reviewer
    payload override (D-105 MODIFIED semantics)."""
    return {
        "command": _COMMAND_BY_QUEUE.get(ticket["queue_type"]),
        "queue_type": ticket["queue_type"],
        "ticket_id": ticket["ticket_id"],
        "payload_ref": ticket["payload_ref"],
        "decision": ticket["resolution_status"],
        "payload": ticket.get("payload", {}),
        "payload_override": ticket.get("payload_override"),
        "reviewer_actor_id": ticket.get("reviewer_actor_id"),
    }


# --- ingestion bridge (Phase 17 → HITL) ------------------------------------------------

class HitlIngestionBridge:
    """`insight_source` is an INJECTED callable returning candidate
    dicts shaped {insight_key, status, ...} — typically the Phase 17
    vault read. Only DISPATCHED_TO_HITL candidates become tickets;
    re-running is idempotent (engine-side ingest_key dedup)."""

    def __init__(self, hitl_engine: HitlEngine,
                 insight_source: Callable[[], List[Dict]]):
        self._engine = hitl_engine
        self._source = insight_source

    def ingest(self, logical_now: str) -> Dict:
        candidates = []
        for row in self._source():
            if isinstance(row, dict) and \
                    row.get("status") == "DISPATCHED_TO_HITL" and \
                    row.get("insight_key"):
                candidates.append(row["insight_key"])
        if not candidates:
            return {"created": [], "duplicated": [],
                    "candidates": 0, "ingest_instant": logical_now}
        res = self._engine.ingest_insight_tickets(candidates,
                                                  logical_now)
        res["candidates"] = len(candidates)
        return res


# --- dispatcher ---------------------------------------------------------------------------

class HitlDispatcher:
    """D-107: resolution → downstream command, exactly once.

    `dispatchers` maps queue_type → INJECTED callable(ticket) that
    performs the real side-effect. The applied gate is a D-027
    exactly-once event per ticket: duplicate approval/rejection
    signals hit the gate and produce zero duplicate side-effects.
    """

    def __init__(self, hitl_engine: HitlEngine,
                 dispatchers: Optional[Dict[str, Callable]] = None):
        self._engine = hitl_engine
        self._dispatchers = dict(dispatchers or {})

    def register_dispatcher(self, queue_type: str,
                            fn: Callable) -> None:
        self._dispatchers[queue_type] = fn

    def apply_resolution(self, ticket_id: str) -> Dict:
        t = self._engine.ticket(ticket_id)
        if t is None:
            return {"ok": False, "reason": "unknown_ticket"}
        if t["resolution_status"] not in (ST_APPROVED, ST_MODIFIED):
            return {"ok": False, "reason": "nothing_to_apply",
                    "status": t["resolution_status"]}
        fn = self._dispatchers.get(t["queue_type"])
        if fn is None:
            return {"ok": False, "reason": "no_dispatcher",
                    "queue_type": t["queue_type"]}
        # exactly-once gate (D-107): a lost race / repeated signal
        # means the action already ran — zero duplicate side-effects
        ref = {"kind": "resolution_applied", "ticket_id": ticket_id,
               "decision": t["resolution_status"],
               "queue_type": t["queue_type"]}
        if not self._engine._record(
                self._engine._eid("applied", ticket_id), ref):
            return {"ok": True, "already_applied": True,
                    "dispatched": False}
        try:
            result = fn(command_for(t))
        except Exception as exc:  # recorded, never silent
            self._engine._record(self._engine._eid(
                "apply_failed", ticket_id), {
                "kind": "resolution_apply_failed",
                "ticket_id": ticket_id,
                "error": str(exc)[:300]})
            return {"ok": False, "reason": "dispatcher_raised",
                    "detail": str(exc)[:300]}
        return {"ok": True, "dispatched": True,
                "command": _COMMAND_BY_QUEUE[t["queue_type"]],
                "result": result if isinstance(result, dict) else None}

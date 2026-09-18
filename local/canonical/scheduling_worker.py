"""Phase 15 M3 — due scanner & fan-out bridge (D-095).

Reads DUE posts from DURABLE store data only (ingest_seq order),
marks them DUE, and bridges each to the injected Phase 11
FanOutEngine via route() + dispatch(); dispatch receipts are consumed
and recorded as scheduling events. The scheduler NEVER publishes
directly and NEVER re-implements platform semantics (D-052/D-077
belong to the publishers). The clock is injected: scan(now_iso=...)
— production passes a real clock at exactly one boundary; tests pass
constants. A bridge failure is recorded and the scanner moves on —
independent-post discipline (D-077 spirit).
"""

import json
from typing import Dict, List, Optional

from canonical.scheduling_contracts import (
    OP_SCHEDULE,
    REF_KIND_POST,
    REF_KIND_RECEIPT,
    REF_KIND_TRANSITION,
    ST_CANCELLED,
    ST_DISPATCHED,
    ST_DUE,
    ST_SCHEDULED,
    SchedulingContractError,
    TR_DUE,
    TR_DISPATCH,
    is_due,
)
from canonical.scheduling_engine import SchedulingEngine


class FanOutBridge:
    """Provider-neutral bridge to the Phase 11 FanOutEngine. The
    engine is INJECTED; this module never imports a vendor module."""

    def __init__(self, fanout_engine):
        self.engine = fanout_engine

    def send(self, post_ref: Dict, actor: str = "scheduling-ops"
             ) -> Dict:
        """route() + dispatch(). Returns
        {"dispatched": bool, "detail": {...}} — bridge failures are
        recorded outcomes, never raised into the scanner loop."""
        payload = {
            "job_id": post_ref["post_id"],
            "content_ref": post_ref.get("content_ref"),
            "targets": list(post_ref.get("targets", [])),
            "source": "scheduling",
            "scheduled_for": post_ref.get("scheduled_for"),
        }
        try:
            routed = self.engine.route(payload, actor=actor)
            if not routed.get("routed"):
                return {"dispatched": False,
                        "detail": {"reason":
                                   routed.get("reason", "not_routed")}}
            result = self.engine.dispatch(routed, actor=actor)
            return {"dispatched": True,
                    "detail": {
                        "job_id": routed.get("job_id"),
                        "aggregate": result.get("aggregate"),
                        "outcomes": result.get("outcomes", {}),
                    }}
        except Exception as exc:  # bridge failure — record, move on
            return {"dispatched": False,
                    "detail": {"reason": "bridge_error",
                               "error": str(exc)[:200]}}


class DueScanner:
    """D-095 reconciliation-style due scanner."""

    def __init__(self, engine: SchedulingEngine,
                 bridge: Optional[FanOutBridge] = None):
        self.engine = engine
        self.bridge = bridge

    # -- durable reads -----------------------------------------------------

    def _scheduled_posts(self) -> List[Dict]:
        """All scheduled posts, in DURABLE ingest order. Only the
        latest schedule event per post wins (re-schedules append)."""
        posts: Dict[str, Dict] = {}
        for ref in self.engine._refs():
            if ref.get("kind") != REF_KIND_POST:
                continue
            posts[ref["post_id"]] = ref
        return list(posts.values())

    def _post_state(self, post_id: str) -> Dict:
        state = {"status": ST_SCHEDULED, "scheduled_for": None}
        for ref in self.engine._refs():
            if ref.get("post_id") != post_id:
                continue
            if ref.get("kind") == REF_KIND_POST:
                state["scheduled_for"] = ref.get("scheduled_for")
            elif ref.get("kind") == REF_KIND_TRANSITION:
                to = ref.get("to_status")
                if to == ST_DUE:
                    state["status"] = ST_DUE
                elif to in (ST_DISPATCHED, ST_CANCELLED):
                    state["status"] = to
        return state

    # -- scan -----------------------------------------------------------------

    def scan(self, now_iso: str, limit: int = 100) -> Dict:
        """One scan pass at the INJECTED instant. Marks due posts and
        bridges them to fan-out. Deterministic order (ingest_seq).

        D-095/D-096 fix (Phase 21 regression net): `limit` bounds the
        WORK considered this pass — it must apply AFTER terminal posts
        are skipped, never before. Applying it to the raw ref list lets
        already-dispatched posts from prior runs consume the entire
        budget on an accumulating durable store and starve fresh posts
        (observed live: 15k+ events, every new post beyond the first
        100 refs never scanned)."""
        summary = {"marked_due": 0, "dispatched": 0,
                   "bridge_failed": 0, "skipped_terminal": 0,
                   "not_due": 0, "over_limit": 0}
        for post in self._scheduled_posts():
            if summary["marked_due"] + summary["dispatched"] \
                    + summary["bridge_failed"] \
                    + summary["not_due"] >= limit:
                summary["over_limit"] += 1
                continue
            pid = post["post_id"]
            state = self._post_state(pid)
            if state["status"] in (ST_DISPATCHED, ST_CANCELLED):
                summary["skipped_terminal"] += 1
                continue
            if state["status"] == ST_DUE:
                # due from a prior pass but not yet dispatched —
                # re-attempt the bridge (idempotent on the engine side)
                pass
            elif not is_due(state["scheduled_for"], now_iso):
                summary["not_due"] += 1
                continue
            else:
                res = self.engine._transition(
                    pid, TR_DUE, ST_DUE, {"now": now_iso}, 0)
                if not res.get("ok"):
                    summary["skipped_terminal"] += 1
                    continue
                summary["marked_due"] += 1
            # bridge to fan-out (D-095) — never publish here
            if self.bridge is None:
                continue
            outcome = self.bridge.send(post)
            receipt = {"kind": REF_KIND_RECEIPT, "post_id": pid,
                       "dispatched": outcome["dispatched"],
                       "detail": outcome["detail"],
                       "scheduled_for": state["scheduled_for"]}
            self.engine._record(
                self.engine._eid("receipt", pid,
                                 self._receipt_seq(pid)), receipt)
            if outcome["dispatched"]:
                res = self.engine._transition(
                    pid, TR_DISPATCH, ST_DISPATCHED,
                    {"receipt": outcome["detail"]}, 0)
                if res.get("ok"):
                    summary["dispatched"] += 1
            else:
                summary["bridge_failed"] += 1
        return summary

    def _receipt_seq(self, post_id: str) -> int:
        n = 0
        for ref in self.engine._refs():
            if ref.get("post_id") == post_id and \
                    ref.get("kind") == REF_KIND_RECEIPT:
                n += 1
        return n

    # -- reconciliation (D-096) --------------------------------------------------

    def reconcile(self, now_iso: str) -> Dict:
        """Prove the calendar is derivable from durable data alone:
        rebuild states and count what the next scan would do."""
        due, pending, terminal = 0, 0, 0
        for post in self._scheduled_posts():
            state = self._post_state(post["post_id"])
            if state["status"] in (ST_DISPATCHED, ST_CANCELLED):
                terminal += 1
            elif state["status"] == ST_DUE or \
                    is_due(state["scheduled_for"], now_iso):
                due += 1
            else:
                pending += 1
        return {"due": due, "pending": pending, "terminal": terminal}


class SchedulingError(RuntimeError):
    """Raised only for engine misuse (e.g. scan without a bridge when
    the caller demanded dispatch)."""

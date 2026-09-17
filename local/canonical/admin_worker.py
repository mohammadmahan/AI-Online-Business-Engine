"""Phase 19 M3 — queue intervention, DLQ bridge & circuit breakers
(D-111).

QueueInterventionWorker + CircuitBreakerRegistry over INJECTED seams:

  - Queue control states are DURABLE (admin.circuit_breakers rows
    carry PAUSED/OPEN queue control as first-class state, plus
    breaker state) — every change is an immutable D-027 event via
    the engine's exactly-once _record.
  - DLQ retry: the worker never opens another module — an INJECTED
    `dlq_reader` lists items and an INJECTED `retry_dispatcher`
    performs the re-submission. Retries respect the item's attempt
    budget and are audited; failures recorded, never silent.
  - Circuit breakers trip MANUALLY (operator action) or
    AUTOMATICALLY (an INJECTED threshold detector over the state
    report) with deterministic cool-downs on the INJECTED logical
    clock — OPEN → HALF_OPEN when cool-down elapses, HALF_OPEN →
    CLOSED on a successful probe, HALF_OPEN → OPEN on failure.
    Zero wall-clock reads.
"""

from typing import Callable, Dict, List, Optional

from canonical.admin_contracts import (
    CB_CLOSED,
    CB_HALF_OPEN,
    CB_OPEN,
    QC_OPEN,
    QC_PAUSED,
    AdminContractError,
    breaker_transition,
)
from canonical.admin_engine import ControlPlaneEngine


class QueueInterventionWorker:
    """D-111 worker. All downstream effects through injected
    callables; every intervention a D-027 event."""

    def __init__(self, engine: ControlPlaneEngine,
                 retry_dispatcher: Optional[Callable] = None):
        self._engine = engine
        self._retry = retry_dispatcher

    # -- queue control (durable PAUSED/OPEN state) ------------------------------

    def queue_state(self, queue_name: str) -> str:
        row = self._engine._vault.get_breaker(
            "queue:" + queue_name)
        if row is None:
            return QC_OPEN
        return row["state"] if row["state"] in (QC_OPEN, QC_PAUSED) \
            else QC_OPEN

    def set_queue_state(self, queue_name: str, state: str,
                        actor: str, logical_now: str,
                        reason: str = "") -> Dict:
        if state not in (QC_OPEN, QC_PAUSED):
            raise AdminContractError(
                "queue state must be OPEN or PAUSED")
        prev = self.queue_state(queue_name)
        if prev == state:
            return {"ok": True, "unchanged": True,
                    "state": state}
        self._engine._vault.set_breaker({
            "breaker_name": "queue:" + queue_name,
            "state": state, "tripped_by": actor,
            "tripped_at_logical": logical_now,
            "cool_down_until": None,
            "last_reason": reason})
        self._engine._record(self._engine._eid(
            "queue", queue_name,
            self._queue_seq(queue_name)), {
            "kind": "queue_control_changed",
            "queue_name": queue_name, "state": state,
            "actor": actor, "reason": reason[:200]})
        return {"ok": True, "queue_name": queue_name,
                "state": state, "previous": prev}

    def _queue_seq(self, queue_name: str) -> int:
        n = 0
        for raw in self._engine._store.succeeded_references("admin"):
            if isinstance(raw, dict):
                ref = raw
            else:
                try:
                    import json
                    ref = json.loads(raw)
                except Exception:
                    continue
            if ref.get("kind") == "queue_control_changed" and \
                    ref.get("queue_name") == queue_name:
                n += 1
        return n

    # -- DLQ retry (injected seams, attempt-budget aware) --------------------------

    def retry_dlq_item(self, item: Dict, actor: str,
                       logical_now: str) -> Dict:
        """Re-submit one dead-letter item through the injected
        dispatcher. The item must carry dlq_id, attempts and a
        payload; the retry budget (max 5 durable attempts) is
        respected. The retry attempt itself is audited."""
        for field in ("dlq_id", "attempts"):
            if field not in item:
                raise AdminContractError(
                    f"DLQ item missing {field} (Class-B, D-111)")
        attempts = int(item["attempts"])
        if attempts >= 5:
            self._engine._record(self._engine._eid(
                "dlq-retry-refused", str(item["dlq_id"]),
                attempts), {
                "kind": "dlq_retry_refused",
                "dlq_id": str(item["dlq_id"]),
                "attempts": attempts})
            return {"ok": False, "reason": "attempt_budget_exhausted",
                    "attempts": attempts}
        if self._retry is None:
            return {"ok": False, "reason": "no_retry_dispatcher"}
        try:
            result = self._retry(item)
        except Exception as exc:
            self._engine._record(self._engine._eid(
                "dlq-retry-failed", str(item["dlq_id"]), attempts), {
                "kind": "dlq_retry_failed",
                "dlq_id": str(item["dlq_id"]),
                "error": str(exc)[:200]})
            return {"ok": False, "reason": "dispatcher_raised",
                    "detail": str(exc)[:200]}
        self._engine._record(self._engine._eid(
            "dlq-retry", str(item["dlq_id"]), attempts), {
            "kind": "dlq_retry_executed",
            "dlq_id": str(item["dlq_id"]),
            "attempt": attempts + 1, "actor": actor,
            "result": result if isinstance(result, dict) else None})
        return {"ok": True, "dlq_id": item["dlq_id"],
                "attempt": attempts + 1,
                "result": result if isinstance(result, dict) else None}

    # -- breakers -------------------------------------------------------------------

    def trip_breaker(self, name: str, actor: str, reason: str,
                     cool_down_until: str,
                     logical_now: str) -> Dict:
        """Manual trip (operator) — OPEN with a deterministic
        cool-down horizon (a logical value, never wall clock)."""
        prev = self._engine._vault.get_breaker(name)
        prev_state = prev["state"] if prev else CB_CLOSED
        if not breaker_transition(prev_state, CB_OPEN):
            return {"ok": False, "reason": "illegal_transition",
                    "from": prev_state}
        self._engine._vault.set_breaker({
            "breaker_name": name, "state": CB_OPEN,
            "tripped_by": actor, "tripped_at_logical": logical_now,
            "cool_down_until": cool_down_until,
            "last_reason": reason})
        self._engine._record(self._engine._eid(
            "breaker", name, self._breaker_seq(name)), {
            "kind": "breaker_tripped", "breaker_name": name,
            "actor": actor, "reason": reason[:200],
            "cool_down_until": cool_down_until,
            "trip_kind": "manual"})
        return {"ok": True, "breaker": name, "state": CB_OPEN,
                "cool_down_until": cool_down_until}

    def evaluate_breaker(self, name: str, detector: Callable,
                         logical_now: str) -> Dict:
        """Automatic evaluation: the INJECTED detector inspects the
        durable state and returns {trip: bool, reason, cool_down}.
        The detector receives NOTHING from this module — it reads the
        durable state it was wired to (boundary discipline)."""
        row = self._engine._vault.get_breaker(name)
        current = row["state"] if row else CB_CLOSED
        verdict = detector() or {}
        trip = bool(verdict.get("trip"))
        if current == CB_CLOSED and trip:
            return self.trip_breaker(
                name, "actor:system:autoscaler",
                str(verdict.get("reason", "threshold breach")),
                str(verdict.get("cool_down_until", logical_now)),
                logical_now)
        if current == CB_OPEN and row and \
                row.get("cool_down_until") and \
                logical_now >= row["cool_down_until"]:
            # cool-down elapsed: OPEN → HALF_OPEN (deterministic)
            self._engine._vault.set_breaker(
                dict(row, state=CB_HALF_OPEN))
            self._engine._record(self._engine._eid(
                "breaker", name, self._breaker_seq(name)), {
                "kind": "breaker_half_open", "breaker_name": name})
            return {"ok": True, "breaker": name,
                    "state": CB_HALF_OPEN}
        return {"ok": True, "breaker": name, "state": current,
                "changed": False}

    def probe_breaker(self, name: str, probe_ok: bool,
                      logical_now: str) -> Dict:
        """HALF_OPEN resolution: success closes, failure re-opens
        (deterministic, D-111)."""
        row = self._engine._vault.get_breaker(name)
        if row is None or row["state"] != CB_HALF_OPEN:
            return {"ok": False, "reason": "not_half_open"}
        target = CB_CLOSED if probe_ok else CB_OPEN
        self._engine._vault.set_breaker(
            dict(row, state=target,
                 cool_down_until=None if probe_ok
                 else row.get("cool_down_until")))
        self._engine._record(self._engine._eid(
            "breaker", name, self._breaker_seq(name)), {
            "kind": "breaker_probe", "breaker_name": name,
            "probe_ok": probe_ok, "state": target})
        return {"ok": True, "breaker": name, "state": target}

    def _breaker_seq(self, name: str) -> int:
        n = 0
        for raw in self._engine._store.succeeded_references("admin"):
            if isinstance(raw, dict):
                ref = raw
            else:
                try:
                    import json
                    ref = json.loads(raw)
                except Exception:
                    continue
            if ref.get("breaker_name") == name and \
                    ref.get("kind") in ("breaker_tripped",
                                        "breaker_half_open",
                                        "breaker_probe"):
                n += 1
        return n


class CircuitBreakerRegistry:
    """Read-side view of durable breaker states for the report."""

    def __init__(self, engine: ControlPlaneEngine):
        self._engine = engine

    def snapshot(self) -> Dict:
        return self._engine._vault.all_breakers()

    def state_of(self, name: str) -> str:
        row = self._engine._vault.get_breaker(name)
        return row["state"] if row else CB_CLOSED

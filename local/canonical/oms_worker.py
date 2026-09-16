"""Phase 12 M3 — OMS reconciliation worker (D-084).

Boot/recovery scanner over the durable event store only: finds
`FULFILLING` orders whose fulfillment receipt is missing past the
configurable TTL and auto-cancels them deterministically
(`fulfillment_ttl_expired`), releasing reserved stock (D-082) and
recording D-026 provenance. COMPLETED orders are never touched; the
worker never invents fulfillment facts.

TTL semantics: the placement/transition event carries the durable
timestamps (`placed_at` from the caller, recorded at transition);
TTL comparison uses the ORDER's own recorded clock fields — no
wall-clock read enters any key or stored value.
"""

import time
from typing import Dict, List, Optional

from canonical.oms_contracts import (
    CANCELLED,
    COMPLETED,
    FULFILLING,
    fulfillment_ttl_expired_reason,
)
from canonical.oms_engine import OmsEngine


class ReconciliationReport:
    def __init__(self):
        self.terminal: List[str] = []
        self.in_flight: List[str] = []
        self.expired: List[str] = []
        self.fulfilled_pending_completion: List[str] = []
        self.anomalies: List[Dict] = []

    def as_dict(self) -> Dict:
        return {
            "terminal": list(self.terminal),
            "in_flight": list(self.in_flight),
            "expired": list(self.expired),
            "fulfilled_pending_completion":
                list(self.fulfilled_pending_completion),
            "anomalies": list(self.anomalies),
        }


class OmsReconciliationWorker:
    """D-084 TTL reconciliation over one OmsEngine."""

    def __init__(self, engine: OmsEngine,
                 ttl_seconds: float = 24 * 3600.0,
                 clock=time.time):
        self.engine = engine
        self.ttl_seconds = ttl_seconds
        self._clock = clock  # injectable for deterministic tests

    def _orders(self) -> Dict[str, Dict]:
        orders: Dict[str, Dict] = {}
        for ref in self.engine._refs():
            eid = str(ref.get("event_id", ""))
            if eid.startswith("oms|order|") and "|" not in \
                    eid[len("oms|order|"):]:
                orders.setdefault(ref.get("order_key", ""),
                                  ref)
        return orders

    def scan_and_reconcile(self, *, actor: str = "oms-reconciler",
                           auto_cancel: bool = True) -> Dict:
        """Scan every durable order; auto-cancel expired FULFILLING.

        auto_cancel=False is a dry audit pass (HITL review first).
        """
        report = ReconciliationReport()
        now = self._clock()
        for order_key, placement in sorted(self._orders().items()):
            state = self.engine.state(order_key)
            if state in (COMPLETED, CANCELLED, "REFUNDED"):
                report.terminal.append(order_key)
                continue
            if state == FULFILLING:
                # fulfilled with receipt → awaiting operator completion
                if self.engine.has_receipt(order_key):
                    report.fulfilled_pending_completion.append(order_key)
                    continue
                # TTL check against the order's own recorded clock
                placed_at = str(placement.get("placed_at", ""))
                age = self._age_seconds(placed_at, now)
                if age is None:
                    report.anomalies.append({
                        "order_key": order_key,
                        "reason": "unparsable placed_at — HITL review",
                    })
                    continue
                if age < self.ttl_seconds:
                    report.in_flight.append(order_key)
                    continue
                # TTL expired: deterministic auto-cancel (D-084)
                if auto_cancel:
                    res = self.engine.transition(
                        order_key, CANCELLED, actor=actor,
                        reason=fulfillment_ttl_expired_reason())
                    if res.get("transitioned"):
                        report.expired.append(order_key)
                    else:
                        report.anomalies.append({
                            "order_key": order_key,
                            "reason": f"cancel refused: "
                                      f"{res.get('reason')}",
                        })
                else:
                    report.in_flight.append(order_key)
            elif state in ("PLACED", "VALIDATED"):
                report.in_flight.append(order_key)
            else:
                report.anomalies.append({
                    "order_key": order_key,
                    "reason": f"unknown durable state {state!r}",
                })
        return report.as_dict()

    @staticmethod
    def _age_seconds(placed_at: str, now: float) -> Optional[float]:
        """Age of the order from its recorded ISO placed_at. Returns
        None when unparsable (flagged for HITL, never guessed)."""
        try:
            from datetime import datetime, timezone
            t0 = datetime.fromisoformat(
                placed_at.replace("Z", "+00:00"))
            if t0.tzinfo is None:
                t0 = t0.replace(tzinfo=timezone.utc)
            return now - t0.timestamp()
        except (ValueError, AttributeError):
            return None

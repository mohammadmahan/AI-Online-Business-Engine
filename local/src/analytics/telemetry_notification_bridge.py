"""Phase 17/18 — telemetry alerts → D-089 human notification bridge.

Part A of the alerting wiring: `TelemetryCircuit` alerts are mapped
onto the canonical D-089 notification boundary (validated, deduped,
durable QUEUED records) so anomalies reach a human.

Discipline:
  - Canonical composition: the D-089 contract and engine are used
    AS SHIPPED — events pass `validate_notification` before anything
    is queued (Class-B before queueing), dedup via the D-090 vault
    claim, recipients stay opaque local user references (D-045:
    no address is invented or harvested).
  - Deterministic mapping: anomaly class → (template, priority,
    channel) is a fixed table; severity ordering follows the D-089
    priority matrix (missing/malformed telemetry = HIGH — the
    fail-closed condition IS the anomaly).
  - Coalescing while latched: while the circuit stays latched open,
    repeated breaches collapse onto ONE logical alert per metric
    (`event_key` carries metric + latch epoch, not the tick), so
    the D-090 dedup and the D-090 frequency caps do the spam
    control. A `reset()` starts a new epoch (new logical alerts).
  - Fail-closed delivery: transport/queue failures are surfaced as
    structured `BridgeReport`s — an alert is NEVER reported
    delivered when its enqueue failed; the circuit's own latch
    semantics are unchanged.
  - D-124: every variable passes `deep_redact` before the event is
    built; no payload values beyond metric name/value/threshold/
    verdict/epoch ever enter the notification.
"""
from __future__ import annotations

from typing import Callable, Dict, List, Optional

from canonical.notification_contracts import (
    CH_IN_APP,
    NotificationContractError,
    PR_CRITICAL,
    PR_HIGH,
    ST_DUPLICATE_BLOCKED,
    ST_POLICY_DEFERRED,
    ST_QUEUED,
)
from canonical.notification_engine import NotificationEngine

try:  # package-relative (battery) or script (cwd=local)
    from local.src.memory.vector_store import deep_redact  # type: ignore
except ImportError:  # pragma: no cover - script path
    from src.memory.vector_store import deep_redact  # type: ignore

__all__ = ["BridgeReport", "TelemetryNotificationBridge",
           "OPERATOR_RECIPIENT"]


# Opaque local operator reference — configuration-shaped, never a
# harvested address (D-045). Delivery routing stays owner-configured
# in the channel adapters.
OPERATOR_RECIPIENT = "operator:oncall"

TEMPLATE_ID = "system.health.v1"


class BridgeReport:
    """Structured outcome of one bridge attempt (fail-closed)."""

    __slots__ = ("alert_id", "metric", "ok", "status", "detail")

    def __init__(self, alert_id: str, metric: str, ok: bool,
                 status: str, detail: str):
        self.alert_id = alert_id
        self.metric = metric
        self.ok = ok
        self.status = status
        self.detail = detail

    def as_dict(self) -> Dict[str, object]:
        return {"alert_id": self.alert_id, "metric": self.metric,
                "ok": self.ok, "status": self.status,
                "detail": self.detail}


def _severity(metric: str, value: float) -> str:
    """Fixed two-tier table (D-089 priority matrix):
    missing/malformed telemetry (value < 0 sentinel) — the
    observability surface itself is dead — pages CRITICAL (bypasses
    quiet hours); any threshold breach pages HIGH. Deterministic."""
    if value < 0:
        return PR_CRITICAL
    return PR_HIGH


class TelemetryNotificationBridge:
    """Sink adapter: `TelemetryCircuit(alert_sink=bridge.as_sink())`.

    `engine` is the shipped `NotificationEngine` (validate → policy →
    vault → durable QUEUED). `occurred_at_of(tick)` converts the
    circuit's logical tick into the event's recorded ISO timestamp —
    INJECTED, never the wall clock (D-085)."""

    def __init__(self, engine: NotificationEngine,
                 occurred_at_of: Callable[[int], str],
                 recipient: str = OPERATOR_RECIPIENT):
        if not callable(occurred_at_of):
            raise ValueError("occurred_at_of_required")
        self._engine = engine
        self._occurred_at_of = occurred_at_of
        self._recipient = recipient
        self._epoch = 0  # bumped by on_circuit_reset()
        self.reports: List[BridgeReport] = []

    # -- lifecycle hooks ------------------------------------------------------

    def on_circuit_reset(self) -> None:
        """New logical epoch after an operator `TelemetryCircuit.reset()`
        so re-breaches of the same metric alert again (never silently
        swallowed by the old epoch's dedup key)."""
        self._epoch += 1

    # -- sink -----------------------------------------------------------------

    def as_sink(self) -> Callable[[object], BridgeReport]:
        """Returns the callable to hand to `TelemetryCircuit`."""
        return self.notify

    def notify(self, alert: object) -> BridgeReport:
        """Map one alert onto the D-089 boundary and enqueue it.
        Returns a structured report; NEVER marks delivered on failure."""
        alert_id = getattr(alert, "alert_id", "unknown")
        metric = getattr(alert, "metric", "unknown")
        value = float(getattr(alert, "value", -1.0))
        threshold = float(getattr(alert, "threshold", 0.0))
        raised_at = int(getattr(alert, "raised_at", 0))
        detail = str(getattr(alert, "detail", ""))
        verdict = ("missing_or_malformed" if value < 0 else "breach")

        variables = {
            "component": deep_redact(f"telemetry.{metric}"),
            "detail": deep_redact(
                f"{verdict} epoch={self._epoch} "
                f"value={value:.4f} threshold={threshold:.4f} "
                f"detail={detail}"),
        }
        event = {
            "recipient": self._recipient,
            "channel": CH_IN_APP,
            "priority": _severity(metric, value),
            "template_id": TEMPLATE_ID,
            "event_key": f"telemetry:{metric}:epoch{self._epoch}",
            "occurred_at": self._occurred_at_of(raised_at),
            "variables": variables,
        }
        try:
            decision = self._engine.enqueue(event)
        except NotificationContractError as e:
            report = BridgeReport(alert_id, metric, False,
                                  "rejected", f"class_b:{e}")
            self.reports.append(report)
            return report
        except Exception as e:  # noqa: BLE001 - fail closed
            report = BridgeReport(alert_id, metric, False,
                                  "transport_error",
                                  f"degraded:{type(e).__name__}")
            self.reports.append(report)
            return report
        status = decision.get("status", "unknown")
        # QUEUED = dispatched to the durable queue; POLICY_DEFERRED =
        # deterministically held (quiet hours/cap); DUPLICATE_BLOCKED
        # = the desired coalescing while latched (the alert is
        # already pending). Only these are healthy outcomes.
        ok = status in (ST_QUEUED, ST_POLICY_DEFERRED,
                        ST_DUPLICATE_BLOCKED)
        report = BridgeReport(alert_id, metric, ok, status,
                              decision.get("reason", ""))
        self.reports.append(report)
        return report

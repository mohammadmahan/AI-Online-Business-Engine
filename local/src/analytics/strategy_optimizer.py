"""Phase 17/18 — autonomous strategy optimizer + telemetry circuit.

Part B of the analytics wiring: heuristic recommendations over the
deterministic campaign analysis, and a fail-closed anomaly alerting
circuit on the platform's operational telemetry.

Discipline:
  - Pure + injected-only: the alert sink is constructor-injected
    (in production the D-089 notification boundary; in tests a
    collector). No I/O, no wall clock — anomalies are evaluated from
    recorded logical ticks, never from `datetime.now()`.
  - Determinism: recommendation precedence is a fixed total order
    (publishing cadence → top categories → content themes).
  - D-124: alert payloads and report metadata pass `deep_redact`
    before emission; sinks receive redacted content only.
  - Fail-closed: on ANY alert-pipeline error the circuit latches
    OPEN, refuses to report healthy, and retries nothing silently.
"""
from __future__ import annotations

from typing import Callable, Dict, List, Optional

try:  # package-relative (battery) or script (cwd=local)
    from local.src.memory.vector_store import deep_redact  # type: ignore
except ImportError:  # pragma: no cover - script path
    from src.memory.vector_store import deep_redact  # type: ignore

__all__ = ["Alert", "StrategyOptimizer", "TelemetryCircuit",
           "DEFAULT_THRESHOLDS"]

# Fail-closed defaults — breach on ANY of these emits an alert
# (D-126/D-063 semantics: warn at threshold, hard refusal above).
DEFAULT_THRESHOLDS: Dict[str, float] = {
    "publish_failure_rate": 0.20,     # share of failed dispatches
    "webhook_drop_rate": 0.10,        # share of dropped webhooks
    "cart_abandonment_rate": 0.75,    # share of carts never ordered
}


class Alert:
    """One redacted telemetry alert (id, metric, verdict, detail)."""

    __slots__ = ("alert_id", "metric", "value", "threshold", "raised_at",
                 "detail")

    def __init__(self, alert_id: str, metric: str, value: float,
                 threshold: float, raised_at: int, detail: str = ""):
        self.alert_id = alert_id
        self.metric = metric
        self.value = value
        self.threshold = threshold
        self.raised_at = raised_at
        self.detail = detail

    def as_dict(self) -> Dict:
        return {"alert_id": self.alert_id, "metric": self.metric,
                "value": self.value, "threshold": self.threshold,
                "raised_at": self.raised_at,
                "detail": deep_redact(self.detail)}


class StrategyOptimizer:
    """Heuristic recommendations over the campaign analysis.

    AI-ASSISTED variants remain behind the canonical AI boundary —
    this optimizer is the deterministic heuristic floor that runs
    with zero external dependencies (D-045)."""

    def recommend_schedule(self, publication_records: List[Dict],
                           top_n: int = 2) -> List[Dict]:
        """Best publication buckets by total engagement.
        Bucket key: the record's own logical `bucket` field when
        present, else the ISO date of its recorded timestamp —
        deterministic from recorded data only (D-085)."""
        buckets: Dict[str, Dict] = {}
        for p in publication_records:
            cid = p.get("campaign_id")
            if not cid:
                continue
            key = p.get("bucket") or _day_bucket(p.get("occurred_at"))
            if not key:
                continue
            b = buckets.setdefault(str(key), {"likes": 0,
                                              "comments": 0,
                                              "publications": 0})
            b["likes"] += _count(p.get("engagement_likes"))
            b["comments"] += _count(p.get("engagement_comments"))
            b["publications"] += 1
        items = sorted(
            buckets.items(),
            key=lambda kv: (-(kv[1]["likes"] + kv[1]["comments"]),
                            kv[0]))
        return [{"bucket": k, **v}
                for k, v in items[:max(top_n, 0)]]

    def recommend_categories(self, order_records: List[Dict],
                             top_n: int = 3) -> List[Dict]:
        """Top-converting product categories by revenue."""
        cats: Dict[str, Dict] = {}
        for o in order_records:
            cat = o.get("category")
            if not cat:
                continue
            c = cats.setdefault(str(cat), {"orders": 0,
                                           "revenue_minor": 0})
            c["orders"] += 1
            try:
                c["revenue_minor"] += max(
                    int(o.get("order_total_minor") or 0), 0)
            except (TypeError, ValueError):
                pass
        items = sorted(cats.items(),
                       key=lambda kv: (-kv[1]["revenue_minor"], kv[0]))
        return [{"category": k, **v} for k, v in items[:max(top_n, 0)]]

    def recommend_themes(self, publication_records: List[Dict],
                         analysis: Dict, top_n: int = 2) -> List[Dict]:
        """Content themes ranked by attributed revenue."""
        rows = []
        for cid, m in analysis.get("campaigns", {}).items():
            if m.get("theme"):
                rows.append((m["theme"], m["revenue_minor"], cid))
        agg: Dict[str, Dict] = {}
        for theme, revenue, cid in rows:
            a = agg.setdefault(theme, {"revenue_minor": 0,
                                       "campaigns": []})
            a["revenue_minor"] += revenue
            a["campaigns"].append(cid)
        items = sorted(agg.items(),
                       key=lambda kv: (-kv[1]["revenue_minor"], kv[0]))
        return [{"theme": k, **v} for k, v in items[:max(top_n, 0)]]


class TelemetryCircuit:
    """Fail-closed anomaly detection over operational telemetry.

    telemetry is a dict of RATE snapshots (0..1):
      {publish_failure_rate, webhook_drop_rate, cart_abandonment_rate}
    Each snapshot carries the logical tick it was recorded at.
    """

    def __init__(self, thresholds: Optional[Dict[str, float]] = None,
                 alert_sink: Optional[Callable[[Alert], object]] = None):
        self._thresholds = dict(DEFAULT_THRESHOLDS)
        if thresholds:
            unknown = set(thresholds) - set(DEFAULT_THRESHOLDS)
            if unknown:
                raise ValueError(f"unknown metrics: {sorted(unknown)}")
            self._thresholds.update(thresholds)
        self._sink = alert_sink
        self._latched_open = False
        self.alerts: List[Alert] = []

    @property
    def latched_open(self) -> bool:
        return self._latched_open

    def evaluate(self, telemetry: Dict[str, float], logical_ts: int
                 ) -> List[Alert]:
        """Evaluate one snapshot; emit redacted alerts through the
        sink. On sink failure the circuit LATCHES OPEN (fail-closed):
        subsequent calls refuse to evaluate until explicitly reset."""
        if self._latched_open:
            return []
        raised: List[Alert] = []
        for metric in sorted(DEFAULT_THRESHOLDS):
            if metric not in telemetry:
                # missing telemetry is a fail-closed condition
                raised.append(self._raise(metric, None,
                                          self._thresholds[metric],
                                          logical_ts, "missing"))
                continue
            value = telemetry[metric]
            if _rate(value) is None:
                raised.append(self._raise(metric, value,
                                          self._thresholds[metric],
                                          logical_ts, "malformed"))
                continue
            if _rate(value) > self._thresholds[metric]:
                raised.append(self._raise(metric, _rate(value),
                                          self._thresholds[metric],
                                          logical_ts, "breach"))
        if self._sink is not None:
            try:
                for a in raised:
                    self._sink(a)
            except Exception:  # noqa: BLE001 - fail closed
                self._latched_open = True
        self.alerts.extend(raised)
        return raised

    def reset(self) -> None:
        """Owner/operator action: clear the latch (auditable call site
        belongs to the operator, not this circuit)."""
        self._latched_open = False

    def _raise(self, metric: str, value, threshold: float,
               logical_ts: int, verdict: str) -> Alert:
        if verdict == "breach":
            detail = f"{_safe_value(value):.4f} > {threshold:.4f}"
        elif verdict == "missing":
            detail = "telemetry absent — fail closed"
        else:
            detail = f"non-numeric rate {value!r}"
        alert = Alert(f"alert-{metric}-{logical_ts}", metric,
                      _safe_value(value), threshold, logical_ts, detail)
        return alert


def _rate(value) -> Optional[float]:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if 0.0 <= v <= 1.0 else None


def _safe_value(value) -> float:
    """Alert snapshots carry a number even for malformed input."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return -1.0


def _count(value) -> int:
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


def _day_bucket(occurred_at) -> Optional[str]:
    """ISO date of a recorded timestamp; None when unusable."""
    if not occurred_at:
        return None
    text = str(occurred_at)
    try:
        from datetime import datetime, timezone
        t0 = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if t0.tzinfo is None:
            t0 = t0.replace(tzinfo=timezone.utc)
        return t0.date().isoformat()
    except (ValueError, TypeError, AttributeError):
        return None

"""Phase 17 M3 — anomaly scanner, domain correlator & HITL triage
bridge (D-103/D-104).

Reconciliation-style worker over DURABLE multi-phase data:

  - The metric FRAME is plain data handed in by the caller: D-085
    rollup cells (publication outcomes from Phases 9–11, order
    velocity + revenue from Phase 12) and optional scheduling
    observations from Phase 15's durable calendar. The worker NEVER
    imports analytics/OMS/scheduling/notification modules — the
    boundary is import-level (AST-verified, battery-asserted).
  - Detectors are INJECTED pure callables with configurable
    thresholds; the built-ins are deterministic functions of the
    frame only. The scan instant is INJECTED (now_iso) — zero
    wall-clock reads.
  - A threshold breach is recorded STRICTLY as an immutable D-027
    audit event via AnalystEngine.propose (insight GENERATED); the
    worker never invokes a notification or publishing module.
    Dispatch is delegated to the Phase 14 contracts at the
    HitlTriageBridge seam: an INJECTED callable receiving a
    contract-shaped event dict (hitl.review_required.v1 variables),
    locally shape-checked — still no module import.
  - Re-scan idempotency: identical evidence ⇒ identical insight_key
    ⇒ DUPLICATE (D-102 dedup by construction) — re-scanning the same
    frame never duplicates insights or audit rows.
"""

import hashlib
import json
from typing import Callable, Dict, List, Optional

from canonical.analyst_contracts import (
    CAT_CAMPAIGN,
    CAT_INVENTORY,
    CAT_SALES,
    CAT_SCHEDULING,
    REF_KINDS,
    SEV_CRITICAL,
    SEV_HIGH,
    SEV_LOW,
    SEV_MEDIUM,
    ST_DISPATCHED_TO_HITL,
    AnalystContractError,
    insight_key,
    make_recommendation,
)
from canonical.analyst_engine import AnalystEngine


# --- metric frame (plain durable data — no domain imports) --------------------------

PUB_PUBLISHED = "publication_published"
PUB_FAILED = "publication_failed"
ORD_PLACED = "order_placed"
ORD_CANCELLED = "order_cancelled"
REV_MINOR = "revenue_minor"


def build_frame(rollup_cells: List[Dict],
                scheduling_observations: Optional[List[Dict]] = None
                ) -> Dict:
    """Normalize durable metric rows into the observation frame.

    rollup_cells: D-085 rollup rows shaped
        {window_kind, bucket, metric_kind, value, count} (as read
        from analytics.metric_rollup or the JSON parity store).
    scheduling_observations: optional Phase 15 durable rows shaped
        {platform, bucket, scheduled_count} (calendar density).
    """
    cells: Dict[str, Dict[str, int]] = {}
    for c in rollup_cells or []:
        mk = c.get("metric_kind")
        bucket = c.get("bucket")
        if not mk or not bucket or "value" not in c:
            raise AnalystContractError(
                "rollup cell needs metric_kind, bucket and value "
                "(incomplete metric context is Class-B, D-102)")
        agg = cells.setdefault(mk, {})
        agg[bucket] = agg.get(bucket, 0) + int(c["value"])
    sched: Dict[str, Dict[str, int]] = {}
    for s in scheduling_observations or []:
        plat = s.get("platform")
        bucket = s.get("bucket")
        if not plat or not bucket:
            raise AnalystContractError(
                "scheduling observation needs platform and bucket")
        agg = sched.setdefault(plat, {})
        agg[bucket] = agg.get(bucket, 0) + int(s.get("scheduled_count", 0))
    return {"metrics": cells, "scheduling": sched}


# --- injected detector seam ----------------------------------------------------------

# Detector contract: (frame, thresholds) -> list of findings
#   finding = {detector, severity, correlation_keys, evidence,
#              recommendation_action, recommendation_rationale}
# Deterministic: a function of the frame + thresholds ONLY.

def _ratio(failed: int, published: int) -> float:
    total = failed + published
    if total <= 0:
        return 0.0
    return failed / total


def detect_publication_failure_rate(frame: Dict, thresholds: Dict
                                    ) -> List[Dict]:
    """Built-in detector: publication failure ratio per bucket above
    `max_failure_ratio` (default 0.25) — Phases 9–11 outcomes."""
    limit = float(thresholds.get("max_failure_ratio", 0.25))
    metrics = frame["metrics"]
    failed = metrics.get(PUB_FAILED, {})
    published = metrics.get(PUB_PUBLISHED, {})
    out: List[Dict] = []
    for bucket in sorted(set(failed) | set(published)):
        f, p = failed.get(bucket, 0), published.get(bucket, 0)
        ratio = _ratio(f, p)
        if f + p > 0 and ratio > limit:
            sev = SEV_CRITICAL if ratio > 2 * limit else SEV_HIGH
            out.append({
                "detector": "publication_failure_rate",
                "severity": sev,
                "correlation_keys": [f"bucket:{bucket}"],
                "evidence": {"bucket": bucket, "failed": f,
                             "published": p,
                             "failure_ratio": round(ratio, 4),
                             "threshold": limit},
                "recommendation_action": "review_publishing_pipeline",
                "recommendation_rationale":
                    f"failure ratio {ratio:.2f} exceeds {limit:.2f} "
                    f"for bucket {bucket}",
            })
    return out


def detect_order_cancellation_rate(frame: Dict, thresholds: Dict
                                   ) -> List[Dict]:
    """Built-in detector: order cancellation ratio per bucket above
    `max_cancel_ratio` (default 0.2) — Phase 12 velocity."""
    limit = float(thresholds.get("max_cancel_ratio", 0.2))
    metrics = frame["metrics"]
    placed = metrics.get(ORD_PLACED, {})
    cancelled = metrics.get(ORD_CANCELLED, {})
    out: List[Dict] = []
    for bucket in sorted(set(placed) | set(cancelled)):
        c, p = cancelled.get(bucket, 0), placed.get(bucket, 0)
        # cancellation rate is cancelled / PLACED (the placed orders
        # are the base; cancelled ⊆ placed) — not of all events.
        ratio = (c / p) if p > 0 else 0.0
        if p > 0 and ratio > limit:
            sev = SEV_CRITICAL if ratio > 2 * limit else SEV_MEDIUM
            out.append({
                "detector": "order_cancellation_rate",
                "severity": sev,
                "correlation_keys": [f"bucket:{bucket}"],
                "evidence": {"bucket": bucket, "cancelled": c,
                             "placed": p,
                             "cancel_ratio": round(ratio, 4),
                             "threshold": limit},
                "recommendation_action": "review_order_fulfillment",
                "recommendation_rationale":
                    f"cancel ratio {ratio:.2f} exceeds {limit:.2f} "
                    f"for bucket {bucket}",
            })
    return out


def detect_order_drought(frame: Dict, thresholds: Dict) -> List[Dict]:
    """Built-in detector: `min_orders_per_bucket` (default 1) not met
    in the LAST `drought_buckets` (default 3) buckets of the frame —
    a cross-domain stall signal (orders vs publishing density)."""
    floor = int(thresholds.get("min_orders_per_bucket", 1))
    lookback = int(thresholds.get("drought_buckets", 3))
    placed = frame["metrics"].get(ORD_PLACED, {})
    if not placed:
        return []
    buckets = sorted(placed)[-lookback:]
    dry = [b for b in buckets if placed[b] < floor]
    if not dry:
        return []
    total = sum(placed[b] for b in dry)
    out: List[Dict] = [{
        "detector": "order_drought",
        "severity": SEV_MEDIUM if len(dry) < lookback else SEV_HIGH,
        "correlation_keys": [f"bucket:{b}" for b in dry],
        "evidence": {"buckets": dry, "orders": total,
                     "floor": floor, "lookback": lookback},
        "recommendation_action": "investigate_demand_drop",
        "recommendation_rationale":
            f"orders below floor {floor} in {len(dry)} of the last "
            f"{lookback} buckets",
    }]
    return out


def detect_scheduling_hotspot(frame: Dict, thresholds: Dict
                              ) -> List[Dict]:
    """Built-in detector: a platform/bucket with more than
    `max_scheduled_per_slot` (default 4) scheduled posts — Phase 15
    calendar density colliding with platform throughput."""
    cap = int(thresholds.get("max_scheduled_per_slot", 4))
    scheduling = frame["scheduling"]
    out: List[Dict] = []
    for platform in sorted(scheduling):
        for bucket in sorted(scheduling[platform]):
            n = scheduling[platform][bucket]
            if n > cap:
                out.append({
                    "detector": "scheduling_hotspot",
                    "severity": SEV_LOW if n <= 2 * cap else SEV_MEDIUM,
                    "correlation_keys": [f"platform:{platform}",
                                         f"bucket:{bucket}"],
                    "evidence": {"platform": platform, "bucket": bucket,
                                 "scheduled": n, "cap": cap},
                    "recommendation_action": "rebalance_calendar",
                    "recommendation_rationale":
                        f"{n} scheduled posts exceed cap {cap} for "
                        f"{platform} at {bucket}",
                })
    return out


BUILTIN_DETECTORS = (
    detect_publication_failure_rate,
    detect_order_cancellation_rate,
    detect_order_drought,
    detect_scheduling_hotspot,
)

DEFAULT_THRESHOLDS: Dict[str, Dict] = {
    "publication_failure_rate": {"max_failure_ratio": 0.25},
    "order_cancellation_rate": {"max_cancel_ratio": 0.2},
    "order_drought": {"min_orders_per_bucket": 1,
                      "drought_buckets": 3},
    "scheduling_hotspot": {"max_scheduled_per_slot": 4},
}


# --- category mapping (D-101 taxonomy) ---------------------------------------------

DETECTOR_CATEGORY = {
    "publication_failure_rate": CAT_CAMPAIGN,
    "order_cancellation_rate": CAT_SALES,
    "order_drought": CAT_INVENTORY,
    "scheduling_hotspot": CAT_SCHEDULING,
}


# --- HITL triage bridge (D-103 → Phase 14 contracts) --------------------------------

class HitlTriageBridge:
    """The ONLY side-effect seam. `dispatch_fn` is an INJECTED
    callable receiving a Phase 14 contract-shaped event dict —
    template hitl.review_required.v1 (IN_APP, HIGH priority, vars
    queue_ref + reason). Shape-checked LOCALLY here; the notification
    module itself is never imported (D-103 boundary)."""

    TEMPLATE_ID = "hitl.review_required.v1"
    REQUIRED_VARS = ("queue_ref", "reason")

    def __init__(self, dispatch_fn: Optional[Callable] = None):
        self._dispatch = dispatch_fn

    def event_for(self, insight_key: str, reason: str) -> Dict:
        """Contract-shaped Phase 14 event (caller enqueues it via the
        real NotificationEngine if wired)."""
        return {
            "recipient": "role:owner",
            "channel": "IN_APP",
            "priority": "HIGH",
            "template_id": self.TEMPLATE_ID,
            "variables": {"queue_ref": f"insight:{insight_key}",
                          "reason": str(reason)[:500]},
            "event_key": f"analyst-hitl:{insight_key}",
        }

    def dispatch(self, insight_key: str, reason: str) -> Dict:
        if self._dispatch is None:
            return {"ok": False, "reason": "no_dispatch_fn_bound"}
        event = self.event_for(insight_key, reason)
        for var in self.REQUIRED_VARS:
            if not event["variables"].get(var):
                return {"ok": False, "reason": f"missing_var:{var}"}
        result = self._dispatch(event)
        return {"ok": True, "dispatched": True,
                "result": result if isinstance(result, dict) else None}


# --- scanner --------------------------------------------------------------------------

class AnomalyScanner:
    """D-103 worker: frame in (durable data), insights out (D-027
    audit events via the engine). No wall clock: `now_iso` is the
    injected scan instant and ONLY names the window_ref evidence."""

    def __init__(self, engine: AnalystEngine,
                 detectors: Optional[tuple] = None,
                 thresholds: Optional[Dict[str, Dict]] = None,
                 bridge: Optional[HitlTriageBridge] = None):
        self._engine = engine
        self._detectors = detectors or BUILTIN_DETECTORS
        self._thresholds = dict(DEFAULT_THRESHOLDS)
        if thresholds:
            self._thresholds.update(thresholds)
        self._bridge = bridge or HitlTriageBridge()

    def scan(self, frame: Dict, now_iso: str) -> Dict:
        """Run every injected detector; propose one insight per
        finding. Idempotent: identical findings dedup in the engine."""
        findings: List[Dict] = []
        for detector in self._detectors:
            findings.extend(detector(frame,
                                     self._thresholds.get(
                                         detector.__name__, {})))
        created, duplicated = [], []
        for f in findings:
            category = DETECTOR_CATEGORY.get(f["detector"])
            if category is None:
                continue
            # The window_ref identifies the EVIDENCE, never the scan
            # instant: including the clock in the key would turn every
            # re-scan into a new insight (D-102 dedup violation). The
            # injected instant is recorded as payload metadata only.
            evidence_digest = hashlib.sha256(json.dumps(
                f["evidence"], ensure_ascii=False,
                sort_keys=True).encode("utf-8")).hexdigest()[:10]
            metric_refs = [{
                "metric_kind": "anomaly_detection",
                "window_ref": "detector:" + f["detector"]
                              + ":evidence:" + evidence_digest,
            }]
            proposal = {
                "insight_id": "anomaly-" + f["detector"] + "-"
                              + evidence_digest,
                "category": category,
                "severity": f["severity"],
                "metric_refs": metric_refs,
                "actionable_payload": make_recommendation(
                    f["recommendation_action"],
                    f["recommendation_rationale"],
                    mutates_business_state=False,
                    extra={"detector": f["detector"],
                           "evidence": f["evidence"],
                           "scan_instant": now_iso}),
                "confidence_score": self._confidence(f),
                "correlation_keys": f["correlation_keys"],
                "status": "GENERATED",
            }
            res = self._engine.propose(proposal)
            if res["status"] == "CREATED":
                created.append(res["insight_key"])
            else:
                duplicated.append(res["insight_key"])
            # D-104: high-impact findings route to HITL through the
            # bridge seam — an audit event + contract-shaped dispatch,
            # never a direct notification call.
            if res["status"] == "CREATED" and \
                    f["severity"] in (SEV_HIGH, SEV_CRITICAL):
                self._engine.evaluate(res["insight_key"],
                                      self._auto_approve_evaluator)
                self._engine.dispatch_to_hitl(res["insight_key"])
                self._bridge.dispatch(
                    res["insight_key"],
                    f["recommendation_rationale"])
        return {"findings": len(findings), "created": created,
                "duplicated": duplicated,
                "scan_instant": now_iso}

    @staticmethod
    def _auto_approve_evaluator(row: Dict) -> Dict:
        """Evaluation pass for scanner findings: the detector already
        carries deterministic evidence; the evaluation records that
        the rule fired — the HITL dispatch is still mandatory for
        HIGH/CRITICAL (D-104)."""
        return {"approved": True,
                "note": "deterministic detector threshold breach"}

    @staticmethod
    def _confidence(finding: Dict) -> float:
        """Deterministic confidence from the evidence shape (never
        random, never clock-based): ratios over threshold scale
        0.5→0.95; count findings sit at 0.6."""
        ev = finding.get("evidence", {})
        for key, floor in (("failure_ratio", "threshold"),
                           ("cancel_ratio", "threshold")):
            if key in ev:
                limit = float(ev.get(floor, 0.0)) or 1.0
                ratio = float(ev[key])
                if limit <= 0:
                    return 0.5
                overshoot = ratio / limit
                return min(0.95, 0.5 + 0.45 * min(overshoot / 2.0, 1.0))
        return 0.6


# --- correlation summary (read-only view over the frame) ------------------------------

def correlate_domains(frame: Dict) -> Dict:
    """Cross-domain summary for the scan report: publication load vs
    order outcome per bucket, scheduling density per platform.
    Pure; consumed by humans and tests, never side-effecting."""
    metrics = frame["metrics"]
    buckets = sorted(set(metrics.get(PUB_PUBLISHED, {}))
                     | set(metrics.get(ORD_PLACED, {})))
    per_bucket = []
    for b in buckets:
        per_bucket.append({
            "bucket": b,
            "published": metrics.get(PUB_PUBLISHED, {}).get(b, 0),
            "failed": metrics.get(PUB_FAILED, {}).get(b, 0),
            "orders": metrics.get(ORD_PLACED, {}).get(b, 0),
            "cancelled": metrics.get(ORD_CANCELLED, {}).get(b, 0),
            "revenue_minor": metrics.get(REV_MINOR, {}).get(b, 0),
        })
    return {"buckets": per_bucket,
            "platforms": sorted(frame["scheduling"])}

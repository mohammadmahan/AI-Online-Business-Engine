"""Phase 17 M1 — canonical insight contracts (D-101/D-104).

Pure, dependency-free shapes and rules for the AI business analyst:

  - `BusinessInsight`: the canonical insight (category, severity,
    metric_refs, actionable_payload, confidence_score,
    correlation_keys, status) with a DETERMINISTIC identity — the
    insight key is SHA-256 over (category, correlation_keys,
    metric_refs); identical evidence ⇒ identical insight (D-102
    dedup by construction).
  - Lifecycle (D-101): GENERATED → EVALUATED →
    DISPATCHED_TO_HITL | AUTO_ACCEPTED | DISMISSED, with SUPERSEDED
    as a marker reachable from any non-terminal state. Transitions
    are validated PURELY (no I/O); durability is the engine's job.
  - D-104 boundary: HIGH/CRITICAL severity insights are structurally
    non-auto-acceptable — `can_auto_accept` returns False for them,
    so no caller can reach AUTO_ACCEPTED with human-unreviewable
    impact.
  - Class-B validation (D-102): incomplete metric contexts (missing
    refs/windows), confidence outside [0, 1], unknown categories or
    severities, and non-dict payloads are rejected BEFORE any
    durable write.

No network, no AI SDKs, no wall clock: evaluators are injected
pure functions; the wall clock never enters any key or decision.
"""

import hashlib
import json
from typing import Dict, List, Optional, Tuple

# --- categories (D-101 taxonomy) ------------------------------------------------

CAT_SALES = "sales_performance"
CAT_CONTENT = "content_performance"
CAT_INVENTORY = "inventory_velocity"
CAT_SCHEDULING = "scheduling_density"
CAT_CAMPAIGN = "campaign_attribution"

CATEGORIES = (CAT_SALES, CAT_CONTENT, CAT_INVENTORY,
              CAT_SCHEDULING, CAT_CAMPAIGN)

# --- severity -------------------------------------------------------------------

SEV_LOW = "LOW"
SEV_MEDIUM = "MEDIUM"
SEV_HIGH = "HIGH"
SEV_CRITICAL = "CRITICAL"
SEVERITIES = (SEV_LOW, SEV_MEDIUM, SEV_HIGH, SEV_CRITICAL)

# severities that structurally REQUIRE human review (D-104)
HITL_SEVERITIES = (SEV_HIGH, SEV_CRITICAL)


class AnalystContractError(Exception):
    """Class-B rejection — invalid insight before any durable write."""


# --- lifecycle (D-101) ------------------------------------------------------------

ST_GENERATED = "GENERATED"
ST_EVALUATED = "EVALUATED"
ST_DISPATCHED_TO_HITL = "DISPATCHED_TO_HITL"
ST_AUTO_ACCEPTED = "AUTO_ACCEPTED"
ST_DISMISSED = "DISMISSED"
ST_SUPERSEDED = "SUPERSEDED"

# Fully terminal: no outgoing edge of any kind.
TERMINAL_STATES = (ST_AUTO_ACCEPTED, ST_DISMISSED)
# Soft-terminal: normal edges end here, but a waiting-for-human
# insight may still be superseded by newer evidence (D-101).
SOFT_TERMINAL_STATES = (ST_DISPATCHED_TO_HITL,)

# GENERATED → EVALUATED is the only forward edge from GENERATED.
# From EVALUATED the human/system decision picks the outcome.
LEGAL_EDGES = {
    (ST_GENERATED, ST_EVALUATED),
    (ST_EVALUATED, ST_DISPATCHED_TO_HITL),
    (ST_EVALUATED, ST_AUTO_ACCEPTED),
    (ST_EVALUATED, ST_DISMISSED),
}
# SUPERSEDED is reachable from any non-terminal state — including
# insights sitting in the HITL queue (D-101: "any non-terminal").
SUPERSEDABLE = (ST_GENERATED, ST_EVALUATED, ST_DISPATCHED_TO_HITL)


def is_transition_legal(current: str, target: str) -> bool:
    if current == target:
        return False
    if target == ST_SUPERSEDED:
        return current in SUPERSEDABLE
    return (current, target) in LEGAL_EDGES


# --- shapes -----------------------------------------------------------------------

_REQUIRED = ("insight_id", "category", "severity", "metric_refs",
             "actionable_payload", "confidence_score",
             "correlation_keys", "status")


def validate_insight(insight: Dict) -> Dict:
    """Class-B validation BEFORE any durable write (D-102)."""
    if not isinstance(insight, dict):
        raise AnalystContractError("insight must be a dict")
    missing = [k for k in _REQUIRED if k not in insight]
    if missing:
        raise AnalystContractError(
            f"insight missing required fields: {sorted(missing)}")
    if not isinstance(insight["insight_id"], str) or \
            not insight["insight_id"]:
        raise AnalystContractError("insight_id must be a non-empty string")
    if len(insight["insight_id"]) > MAX_INSIGHT_ID_LEN:
        raise AnalystContractError(
            f"insight_id exceeds {MAX_INSIGHT_ID_LEN} chars (D-114)")
    payload = insight["actionable_payload"]
    if isinstance(payload, dict) and \
            len(json.dumps(payload, ensure_ascii=False)) > MAX_ACTIONABLE_PAYLOAD_JSON:
        raise AnalystContractError(
            f"actionable_payload exceeds {MAX_ACTIONABLE_PAYLOAD_JSON} "
            "JSON chars (D-114)")
    if insight["category"] not in CATEGORIES:
        raise AnalystContractError(
            f"category must be one of {sorted(CATEGORIES)} (D-101)")
    if insight["severity"] not in SEVERITIES:
        raise AnalystContractError(
            f"severity must be one of {sorted(SEVERITIES)} (D-101)")
    if insight["status"] not in (ST_GENERATED, ST_EVALUATED):
        raise AnalystContractError(
            "a NEW insight may only enter as GENERATED or EVALUATED")
    score = insight["confidence_score"]
    if not isinstance(score, (int, float)) or isinstance(score, bool) \
            or not (0.0 <= float(score) <= 1.0):
        raise AnalystContractError(
            "confidence_score must be a number in [0, 1] (D-102)")
    validate_metric_refs(insight["metric_refs"])
    validate_correlation_keys(insight["correlation_keys"])
    if not isinstance(insight["actionable_payload"], dict):
        raise AnalystContractError("actionable_payload must be a dict")
    return insight


def validate_metric_refs(refs) -> List[Dict]:
    """Incomplete metric context = Class-B (D-102): every ref needs
    a metric kind and a window identifier."""
    if not isinstance(refs, list) or not refs:
        raise AnalystContractError(
            "metric_refs must be a non-empty list (incomplete metric "
            "context is a Class-B rejection, D-102)")
    if len(refs) > MAX_METRIC_REFS:
        raise AnalystContractError(
            f"metric_refs exceeds {MAX_METRIC_REFS} entries (D-114)")
    for r in refs:
        if not isinstance(r, dict) or not r.get("metric_kind") \
                or not r.get("window_ref"):
            raise AnalystContractError(
                "each metric_ref needs metric_kind and window_ref "
                "(D-102)")
    return refs


def validate_correlation_keys(keys) -> Tuple[str, ...]:
    if not isinstance(keys, (list, tuple)) or not keys:
        raise AnalystContractError(
            "correlation_keys must be a non-empty sequence (D-101)")
    out = []
    for k in keys:
        if not isinstance(k, str) or not k:
            raise AnalystContractError(
                "correlation keys must be non-empty strings")
        out.append(k)
    if len(out) > MAX_CORRELATION_KEYS:
        raise AnalystContractError(
            f"correlation_keys exceeds {MAX_CORRELATION_KEYS} "
            "entries (D-114)")
    return tuple(out)


# --- deterministic identity (D-101/D-102) -------------------------------------------

# declared input bounds (D-114 hardening re-audit)
MAX_INSIGHT_ID_LEN = 128
MAX_METRIC_REFS = 64
MAX_CORRELATION_KEYS = 32
MAX_ACTIONABLE_PAYLOAD_JSON = 8192

def insight_key(category: str, correlation_keys, metric_refs) -> str:
    """SHA-256 over (category, correlation_keys, metric_refs).
    Deterministic: identical evidence ⇒ identical insight (D-102
    dedup by construction). Never wall-clock, never generator state."""
    payload = json.dumps(
        {"category": category,
         "correlation_keys": sorted(validate_correlation_keys(
             correlation_keys)),
         "metric_refs": sorted(
             json.dumps(r, ensure_ascii=False, sort_keys=True)
             for r in validate_metric_refs(metric_refs))},
        ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# --- D-104 HITL boundary ---------------------------------------------------------------

def requires_hitl(insight: Dict) -> bool:
    """HIGH/CRITICAL severity — or a payload flagged as state-mutating —
    structurally requires human review (D-104)."""
    if insight.get("severity") in HITL_SEVERITIES:
        return True
    return bool(insight.get("actionable_payload", {}).get(
        "mutates_business_state"))


def can_auto_accept(insight: Dict) -> bool:
    """AUTO_ACCEPT is structurally unreachable for HITL-required
    insights (D-104): the engine battery-asserts this never lies."""
    return not requires_hitl(insight)


# --- durable reference kinds (D-104 audit) -------------------------------------------

REF_KINDS = {
    "generated": "insight_generated",
    "evaluated": "insight_evaluated",
    "hitl": "insight_dispatched_to_hitl",
    "auto": "insight_auto_accepted",
    "dismissed": "insight_dismissed",
    "superseded": "insight_superseded",
}

SOURCE_SYSTEM = "analyst"


def make_recommendation(action: str, rationale: str,
                        mutates_business_state: bool = False,
                        extra: Optional[Dict] = None) -> Dict:
    """Canonical Recommendation shape carried in actionable_payload."""
    if not action or not rationale:
        raise AnalystContractError(
            "recommendation needs action and rationale")
    rec = {"action": action, "rationale": rationale,
           "mutates_business_state": bool(mutates_business_state)}
    if extra:
        rec.update(extra)
    return rec

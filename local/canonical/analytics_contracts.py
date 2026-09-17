"""Phase 13 M1 — analytics contracts (D-085).

Canonical metric-event classification, windowing, and rollup math —
pure functions only (no I/O, no adapters, no network), mirroring the
D-069/D-073/D-077/D-081 contract discipline.

CQRS boundary (D-085): these types describe the READ model only.
Nothing here writes to any domain table. Windows are parsed from
each event payload's OWN recorded `occurred_at` ISO timestamp — the
wall clock is never read, never stored, never part of a key.
"""

import re
from typing import Dict, List, Optional

SOURCE_SYSTEM = "analytics"

WINDOW_HOURLY = "hourly"
WINDOW_DAILY = "daily"
WINDOW_MONTHLY = "monthly"
WINDOWS = (WINDOW_HOURLY, WINDOW_DAILY, WINDOW_MONTHLY)

# metric kinds (D-085 taxonomy)
MK_PUBLICATION_PUBLISHED = "publication_published"
MK_PUBLICATION_FAILED = "publication_failed"
MK_ORDER_PLACED = "order_placed"
MK_ORDER_COMPLETED = "order_completed"
MK_ORDER_CANCELLED = "order_cancelled"
MK_REVENUE_MINOR = "revenue_minor"

METRIC_KINDS = (MK_PUBLICATION_PUBLISHED, MK_PUBLICATION_FAILED,
                MK_ORDER_PLACED, MK_ORDER_COMPLETED,
                MK_ORDER_CANCELLED, MK_REVENUE_MINOR)

# metric kinds that SUM values vs COUNT events
_SUM_KINDS = (MK_REVENUE_MINOR,)

# platform sub-outcomes classified as a SERVED publication
# (mirrors the Phase 9/10/11 outcome vocabulary)
_PUBLISHED_OUTCOMES = ("published", "duplicate_publish_blocked")
_FAILED_OUTCOMES = ("terminal_reject", "rejected_class_b",
                    "retries_exhausted", "chat_unreachable",
                    "token_expired", "queue_frozen",
                    "target_dispatch_crashed")

_ISO_RE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}))?")


class AnalyticsContractError(ValueError):
    """Class-B carrier: local contract violation — never projected."""

    failure_class = "B"


# --- windowing (D-085: from the event's own timestamp) ---------------------

def parse_occurred_at(value: str) -> Dict:
    """Parse an ISO-8601 timestamp recorded by the producing domain.
    Returns {iso, hour_key, day_key, month_key}. Raises Class-B when
    unparsable — the caller flags it, never guesses."""
    if not isinstance(value, str):
        raise AnalyticsContractError(
            "occurred_at must be an ISO-8601 string (D-085)")
    m = _ISO_RE.match(value.strip())
    if not m:
        raise AnalyticsContractError(
            f"occurred_at {value!r} unparsable (D-085)")
    year, month, day, hour, minute = m.group(1, 2, 3, 4, 5)
    return {
        "iso": value.strip(),
        "hour_key": f"{year}-{month}-{day}T{hour}",
        "day_key": f"{year}-{month}-{day}",
        "month_key": f"{year}-{month}",
    }


def window_key(occurred_at: str, window: str) -> str:
    """Deterministic bucket key for one window granularity."""
    if window not in WINDOWS:
        raise AnalyticsContractError(
            f"window must be one of {list(WINDOWS)} (D-085)")
    parts = parse_occurred_at(occurred_at)
    return {WINDOW_HOURLY: parts["hour_key"],
            WINDOW_DAILY: parts["day_key"],
            WINDOW_MONTHLY: parts["month_key"]}[window]


# --- event → metric classification (D-085) -----------------------------------

def classify_event(source_system: str, ref: Dict) -> Optional[Dict]:
    """Classify one durable succeeded event into zero or one metric
    record. Returns None for events that carry no metric (e.g. HITL
    chatter, notion sync bookkeeping).

    The classifier reads only the durable ref payload — domain
    modules are never imported, never called (D-087 boundary).
    """
    if not isinstance(ref, dict):
        return None
    occurred = ref.get("occurred_at")
    if not occurred:
        return None  # metric events MUST carry their own timestamp
    parts = parse_occurred_at(occurred)
    base = {
        "occurred_at": parts["iso"],
        "hour_key": parts["hour_key"],
        "day_key": parts["day_key"],
        "month_key": parts["month_key"],
        "campaign_id": (str(ref["campaign_id"])
                        if ref.get("campaign_id") else None),
    }

    src = str(source_system)
    eid = str(ref.get("event_id", ""))

    # publication outcomes (Phases 9/10/11)
    if src in ("instagram", "telegram") and \
            eid.startswith((f"{src}|transition|", f"{src}|publish|")):
        outcome = ref.get("outcome") or ref.get("state")
        if outcome in _PUBLISHED_OUTCOMES:
            return dict(base, kind=MK_PUBLICATION_PUBLISHED, value=1,
                        platform=src)
        if outcome in _FAILED_OUTCOMES:
            return dict(base, kind=MK_PUBLICATION_FAILED, value=1,
                        platform=src)
        return None  # in-flight outcomes carry no metric

    # order outcomes (Phase 12)
    if src == "oms":
        if eid.startswith("oms|order|") and \
                "|" not in eid[len("oms|order|"):]:
            return dict(base, kind=MK_ORDER_PLACED, value=1)
        if eid.startswith("oms|transition|"):
            state = ref.get("state")
            if state == "COMPLETED":
                value = 0
                try:
                    value = int(ref.get("order_total_minor") or 0)
                except (TypeError, ValueError):
                    value = 0
                return [dict(base, kind=MK_ORDER_COMPLETED, value=1),
                        dict(base, kind=MK_REVENUE_MINOR,
                             value=max(value, 0))]
            if state == "CANCELLED":
                return dict(base, kind=MK_ORDER_CANCELLED, value=1)
        return None
    return None


# --- rollup math (D-085) -----------------------------------------------------

def new_rollup() -> Dict:
    """Empty rollup accumulator: kind → {bucket → aggregate}."""
    return {k: {} for k in METRIC_KINDS}


def add_metric(rollup: Dict, metric: Dict,
               window: str = WINDOW_DAILY) -> None:
    """Fold one metric record into the rollup for the given window.
    Counts accumulate; revenue sums. Deterministic — no clock."""
    kind = metric["kind"]
    if kind not in METRIC_KINDS:
        raise AnalyticsContractError(
            f"unknown metric kind {kind!r} (D-085)")
    bucket = window_key(metric["occurred_at"], window)
    cell = rollup[kind].setdefault(
        bucket, {"count": 0, "sum": 0, "last_seq": 0})
    cell["count"] += 1
    cell["sum"] += int(metric.get("value") or 0)


def finalize_rollup(rollup: Dict) -> Dict:
    """Deterministic serialized form: every bucket's aggregate is
    (value=sum for sum-kinds, count otherwise), sorted by bucket."""
    out: Dict[str, Dict] = {}
    for kind in METRIC_KINDS:
        cells = rollup[kind]
        if not cells:
            continue
        use_sum = kind in _SUM_KINDS
        out[kind] = {
            b: {"value": (c["sum"] if use_sum else c["count"]),
                "count": c["count"]}
            for b, c in sorted(cells.items())
        }
    return out


def merge_rollups(a: Dict, b: Dict) -> Dict:
    """Deterministic merge of two raw rollup accumulators (used by
    rebuild tests to prove incremental == full replay). Returns a RAW
    accumulator — serialization is finalize_rollup's job, and callers
    may keep merging; finalize only at the edge."""
    merged = new_rollup()
    for src in (a, b):
        for kind, cells in src.items():
            if kind not in merged:
                continue
            for bucket, cell in cells.items():
                dst = merged[kind].setdefault(
                    bucket, {"count": 0, "sum": 0, "last_seq": 0})
                dst["count"] += cell.get("count", 0)
                dst["sum"] += cell.get("sum", 0)
                dst["last_seq"] = max(dst["last_seq"],
                                      cell.get("last_seq", 0))
    return merged


def window_hash(kind: str, window: str, start: str, end: str,
                cursor: int) -> str:
    """D-088 deterministic report identity: SHA-256 over (report kind,
    window granularity, bounds, source cursor). Same inputs ⇒ same
    hash ⇒ idempotent generation."""
    import hashlib
    if window not in WINDOWS:
        raise AnalyticsContractError(
            f"window must be one of {list(WINDOWS)} (D-088)")
    material = "\x1f".join([
        "analytics-report-v1", str(kind), window,
        str(start), str(end), str(int(cursor)),
    ])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()

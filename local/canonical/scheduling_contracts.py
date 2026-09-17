"""Phase 15 M1 — scheduling contracts (D-093).

Canonical ScheduledPost schema, lifecycle state machine, slot
arithmetic, and conflict vocabulary — pure functions only (no I/O,
no adapters, no network), mirroring the D-069/D-073/D-077/D-081/
D-085/D-089 contract discipline.

The injectable clock is the ONLY time source (D-093): every
comparison takes an explicit `now_iso` argument; the wall clock is
never read, never stored, never part of a key (D-085/D-086
precedent). Slots derive from the producer's own `scheduled_for` by
pure arithmetic.
"""

import hashlib
import re
from typing import Dict, Optional, Tuple

SOURCE_SYSTEM = "scheduling"
OP_SCHEDULE = "schedule"

# --- lifecycle (D-093) -------------------------------------------------------

ST_SCHEDULED = "SCHEDULED"
ST_DUE = "DUE"
ST_DISPATCHED = "DISPATCHED"
ST_CANCELLED = "CANCELLED"
ST_RESCHEDULED = "RESCHEDULED"   # a recorded SCHEDULED→SCHEDULED revision

# legal edges of the state machine
LEGAL_EDGES: Dict[str, Tuple[str, ...]] = {
    ST_SCHEDULED: (ST_DUE, ST_CANCELLED, ST_RESCHEDULED),
    ST_DUE: (ST_DISPATCHED, ST_CANCELLED),
    ST_DISPATCHED: (),   # immutable (D-096)
    ST_CANCELLED: (),    # terminal (D-096)
}
TERMINAL = (ST_DISPATCHED, ST_CANCELLED)
# RESCHEDULED is a revision marker: the post REMAINS SCHEDULED with a
# new scheduled_for; the transition records the prior value

_IMMUTABLE = (ST_DISPATCHED, ST_CANCELLED)


class SchedulingContractError(ValueError):
    """Local Class-B rejection — the post never reaches the calendar."""


def is_transition_legal(current: str, target: str) -> bool:
    # RESCHEDULED is a revision marker, not a source state — it is not
    # a LEGAL_EDGES key, so test it BEFORE the key guard
    if target == ST_RESCHEDULED:
        return current == ST_SCHEDULED
    if current not in LEGAL_EDGES or target not in LEGAL_EDGES:
        return False
    return target in LEGAL_EDGES[current]


def is_mutable(status: str) -> bool:
    """D-096: only pre-DISPATCHED posts are mutable."""
    return status not in _IMMUTABLE


# --- identity (D-093) ---------------------------------------------------------

_POST_ID_RE = re.compile(r"^[A-Za-z0-9_.:@-]{1,128}$")
_ISO_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?"
    r"(Z|[+-]\d{2}:\d{2})$")


def schedule_idempotency_key(content_ref: str, targets: Tuple[str, ...],
                             scheduled_for: str) -> str:
    """SHA-256 over (content_ref, sorted targets, scheduled_for).
    Re-planning the same content for the same window collapses;
    a different window is a different plan."""
    material = "\x1f".join([
        "schedule-v1", content_ref,
        "\x1e".join(sorted(targets)), scheduled_for,
    ])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


# --- validation (D-093) -------------------------------------------------------

def validate_scheduled_post(post: Dict) -> Dict:
    """Strict local validation; returns the post unchanged on success.
    Raises SchedulingContractError (Class-B) before the calendar."""
    if not isinstance(post, dict):
        raise SchedulingContractError("post must be a dict")

    post_id = post.get("post_id")
    if not isinstance(post_id, str) or not _POST_ID_RE.match(post_id):
        raise SchedulingContractError(
            "post_id must be 1-128 chars of [A-Za-z0-9_.:@-]")

    content_ref = post.get("content_ref")
    if not isinstance(content_ref, str) or \
            not _POST_ID_RE.match(content_ref):
        raise SchedulingContractError(
            "content_ref must be a 1-128 char local reference")

    targets = post.get("targets")
    if not isinstance(targets, (list, tuple)) or not targets:
        raise SchedulingContractError(
            "targets must be a non-empty list (Phase 11 destination "
            "matrix — final platform authority stays with the fan-out "
            "validators, D-077)")
    if len(set(targets)) != len(targets):
        raise SchedulingContractError("targets must be unique")

    scheduled_for = post.get("scheduled_for")
    if not isinstance(scheduled_for, str) or \
            not _ISO_RE.match(scheduled_for):
        raise SchedulingContractError(
            "scheduled_for must be an ISO-8601 timestamp with offset "
            "(the planner's own instant — never read from the clock)")

    status = post.get("status", ST_SCHEDULED)
    if status not in LEGAL_EDGES:
        raise SchedulingContractError(
            f"status must be one of {sorted(LEGAL_EDGES)}")
    return post


# --- slot arithmetic (D-094) — pure, no clock ---------------------------------

SLOT_GRANULARITY_MINUTES = 15  # slot bucket size; the minimum gap


def slot_bucket(scheduled_for: str,
                gap_minutes: int = SLOT_GRANULARITY_MINUTES) -> str:
    """Floor the instant to its gap bucket: 'YYYY-MM-DDTHH:MM' where
    MM is a multiple of gap. Pure arithmetic on the given instant —
    the wall clock is never consulted (D-094)."""
    if gap_minutes < 1 or gap_minutes > 1440:
        raise SchedulingContractError(
            "gap_minutes must be 1..1440")
    if 1440 % gap_minutes != 0:
        raise SchedulingContractError(
            "gap_minutes must divide 1440 (slot buckets repeat daily)")
    m = re.match(r"^(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2})", scheduled_for)
    if not m:
        raise SchedulingContractError(
            "scheduled_for must be ISO-8601 with offset")
    date, hour, minute = m.group(1), int(m.group(2)), int(m.group(3))
    minute = (minute // gap_minutes) * gap_minutes
    return f"{date}T{hour:02d}:{minute:02d}"


def slot_lock_key(platform: str, scheduled_for: str,
                  gap_minutes: int = SLOT_GRANULARITY_MINUTES) -> str:
    """PK-as-lock key: (platform, bucket). Two posts whose instants
    floor to the same bucket on the same platform conflict (D-094)."""
    return f"{platform}\x1f{slot_bucket(scheduled_for, gap_minutes)}"


def minutes_between(iso_a: str, iso_b: str) -> float:
    """Signed minutes a→b using each instant's own offset — pure
    datetime arithmetic on supplied values (no clock)."""
    from datetime import datetime
    da = datetime.fromisoformat(iso_a.replace("Z", "+00:00"))
    db = datetime.fromisoformat(iso_b.replace("Z", "+00:00"))
    return (db - da).total_seconds() / 60.0


# --- due semantics (D-095) — pure, clock injected ------------------------------

def is_due(scheduled_for: str, now_iso: str) -> bool:
    """A post is due when its own scheduled_for <= now (both supplied
    instants; the clock never enters this function)."""
    return minutes_between(now_iso, scheduled_for) <= 0


# --- event/ref vocabulary -------------------------------------------------------

REF_KIND_POST = "scheduled_post"
REF_KIND_TRANSITION = "post_transition"
REF_KIND_RECEIPT = "dispatch_receipt"
REF_KIND_CONFLICT = "slot_conflict"

TR_SCHEDULE = "schedule"
TR_DUE = "due"
TR_DISPATCH = "dispatch"
TR_CANCEL = "cancel"
TR_RESCHEDULE = "reschedule"

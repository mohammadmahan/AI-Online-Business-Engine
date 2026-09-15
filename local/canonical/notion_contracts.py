"""Phase 6 M2 — Notion mock data contracts (canonical module).

Implements the D-060 (Approved, amended 2026-09-15) contracts for the
Notion Business OS integration, ahead of any real Notion connection:

  1. Content-idea lifecycle state machine (D-060 approved extended
     form): Backlog → Researching → Draft → Review → Approved →
     Scheduled → Published, plus terminal Rejected (from any
     pre-Approved state) and terminal Archived (from Published or
     Rejected). Terminal states are final — no outgoing transitions.

  2. D-027 idempotency-key derivation with the D-060 refined formula:
         SHA256(source_system + page_id + event_type + revision_marker)
     serialized deterministically as '|'-joined UTF-8 (frozen by test
     vectors).    material fields, raising ValueError for any '|' — so the
    delimiter is unambiguous by construction.

    The revision_marker is the source-provided revision identifier carried in the event payload — never wall-clock time —
     so a retry of the same delivery yields the same key (dedupe
     intact) while distinct revisions yield distinct keys (no silent
     drop of repeated transitions such as Draft → Review → Draft →
     Review).

  3. Payload contract validation for mock Notion events
     (Content Ideas / Campaigns / Incidents). The revision marker is
     abstracted behind NOTION_REVISION_MARKER_FIELDS + the
     RevisionMarkerResolver interface: the real source field is
     UNVERIFIED (owner-gated pending Notion API connectivity
     verification per D-060) and is plugged in by editing that
     constant — no call-site changes.

No network, no credentials (D-045/D-053). Mirrors the spec at
docs/phases/phase-06-notion-business-os.md; a doc/module drift test
keeps them consistent.
"""

from __future__ import annotations

import hashlib
import re
from typing import Dict, FrozenSet, List, Optional

# ---------------------------------------------------------------------------
# 1) Lifecycle state machine (D-060 approved extended form)
# ---------------------------------------------------------------------------

BACKLOG = "Backlog"
RESEARCHING = "Researching"
DRAFT = "Draft"
REVIEW = "Review"
APPROVED = "Approved"
SCHEDULED = "Scheduled"
PUBLISHED = "Published"
REJECTED = "Rejected"      # terminal — reachable from any pre-Approved state
ARCHIVED = "Archived"      # terminal — reachable from Published or Rejected

PRE_APPROVED_STATES: FrozenSet[str] = frozenset({BACKLOG, RESEARCHING, DRAFT, REVIEW})

CONTENT_IDEA_TRANSITIONS: Dict[str, FrozenSet[str]] = {
    BACKLOG: frozenset({RESEARCHING, DRAFT, REVIEW, REJECTED}),
    RESEARCHING: frozenset({DRAFT, REVIEW, REJECTED}),
    DRAFT: frozenset({REVIEW, BACKLOG, REJECTED}),
    REVIEW: frozenset({APPROVED, DRAFT, BACKLOG, REJECTED}),
    APPROVED: frozenset({SCHEDULED}),
    SCHEDULED: frozenset({PUBLISHED}),
    PUBLISHED: frozenset({ARCHIVED}),
    REJECTED: frozenset({ARCHIVED}),   # terminal-but-chaining edge into Archived (D-060)
    ARCHIVED: frozenset(),             # terminal — no outgoing edges
}

CONTENT_IDEA_STATES: FrozenSet[str] = frozenset(CONTENT_IDEA_TRANSITIONS)

# Failure classes, aligned with the D-052 taxonomy vocabulary used by the
# n8n failure classifier: lifecycle violations are data-invariant (B)
# problems — never retried, routed to human review.
CLASS_B = "B"
CLASS_E = "E"


class LifecycleViolation(ValueError):
    """Deterministic violation of the state machine.

    failure_class: 'B' for unauthorized transitions between KNOWN
    states (data-invariant); 'E' for unknown/ambiguous states (the
    conservative route — human review — mirroring D-061's stance).
    """

    def __init__(self, message: str, *, current: str, target: str,
                 failure_class: str = CLASS_B):
        super().__init__(message)
        self.failure_class = failure_class
        self.current_state = current
        self.target_state = target


def validate_transition(current: str, target: str) -> None:
    """Assert `current -> target` is approved; raise LifecycleViolation otherwise.

    Unknown states (either side) are Class E — unknown/ambiguous, the
    conservative route (human review), mirroring D-061's design stance.
    """
    if current not in CONTENT_IDEA_STATES or target not in CONTENT_IDEA_STATES:
        raise LifecycleViolation(
            f"unknown lifecycle state: current={current!r} target={target!r}",
            current=current,
            target=target,
            failure_class=CLASS_E,
        )
    if target not in CONTENT_IDEA_TRANSITIONS[current]:
        raise LifecycleViolation(
            f"unauthorized transition: {current} -> {target}",
            current=current,
            target=target,
        )


# ---------------------------------------------------------------------------
# 2) D-027 / D-060 idempotency-key derivation
# ---------------------------------------------------------------------------

KEY_SEPARATOR = "|"


def notion_idempotency_key(
    page_id: str,
    event_type: str,
    revision_marker: str,
    *,
    source_system: str = "notion",
) -> str:
    """SHA256 over the '|'-joined key material (D-060 refined formula).

    Serialization is deliberate and frozen by test vectors: the D-060
    formula's '+' is conceptual — a delimiter prevents ambiguous
    concatenations, and key-material fields may NOT contain the
    delimiter itself (ValueError), so ('a|b','c') can never collide
    with ('a','b|c'). Changing the serialization or the formula
    requires a decision-record amendment and vector regeneration.
    """
    parts = (source_system, str(page_id), str(event_type), str(revision_marker))
    for part in parts:
        if KEY_SEPARATOR in part:
            raise ValueError(
                f"key-material field contains delimiter {KEY_SEPARATOR!r}: {part!r}"
            )
    material = KEY_SEPARATOR.join(parts)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# 3) Mock Notion payload contract
# ---------------------------------------------------------------------------

SUPPORTED_EVENT_TYPES: FrozenSet[str] = frozenset(
    {"status_changed", "content_idea_updated", "campaign_updated", "incident_updated"}
)

# The verified revision-marker source field is UNVERIFIED (owner-gated,
# D-060) and must be ADDED to this list only after the Notion API
# connectivity verification runs — adjusting ONLY this constant, with
# tests updated in the same change. Wall-clock time (last_edited_time)
# is NEVER key material per D-060 and must not be listed here.
NOTION_REVISION_MARKER_FIELDS: List[str] = [
    "revision_marker",      # mock contract field (canonical mock payloads)
]

_REQUIRED_KEYS = ("page_id", "event_type", "revision_marker")
_PAGE_ID_RE = re.compile(r"^[0-9a-fA-F-]{16,64}$")


class PayloadContractError(ValueError):
    """Deterministic Class-B payload violation (missing/invalid contract keys)."""

    def __init__(self, message: str, *, failure_class: str = CLASS_B):
        super().__init__(message)
        self.failure_class = failure_class


class RevisionMarkerResolver:
    """Interface abstracting the (currently unverified) marker source.

    Resolution order: explicit override → payload['revision_marker'] →
    the first candidate field present in the payload (priority order =
    NOTION_REVISION_MARKER_FIELDS). Raises PayloadContractError when no
    candidate exists — a payload without any revision identity can
    never be deduplicated safely.
    """

    def resolve(self, payload: Dict, explicit_marker: Optional[str] = None) -> str:
        if explicit_marker is not None:
            marker = str(explicit_marker).strip()
            if not marker:
                raise PayloadContractError("explicit revision_marker is blank")
            return marker
        for field in NOTION_REVISION_MARKER_FIELDS:
            if field in payload and str(payload[field]).strip():
                return str(payload[field]).strip()
        raise PayloadContractError(
            "no revision marker found in payload "
            f"(candidates: {', '.join(NOTION_REVISION_MARKER_FIELDS)})"
        )


def validate_mock_payload(payload: Dict, *, resolver: Optional[RevisionMarkerResolver] = None) -> str:
    """Validate a mock Notion event payload; return its idempotency key.

    Contract (mirror of the fixtures in local/tests/fixtures/notion/):
      - page_id: non-empty hex/dash identifier (16–64 chars)
      - event_type: one of SUPPORTED_EVENT_TYPES
      - revision_marker: resolvable via RevisionMarkerResolver
      - object: 'content_idea' | 'campaign' | 'incident'
      - current/target lifecycle states (status_changed events) are
        validated against the D-060 state machine.

    Wall-clock timestamps are rejected as key material by construction:
    if a payload tries to pass `last_edited_time`-derived markers that
    is permitted ONLY as a change-detection candidate — the register
    (D-060) still gates the verified source field.
    """
    if not isinstance(payload, dict):
        raise PayloadContractError("payload must be a JSON object")
    resolver = resolver or RevisionMarkerResolver()

    for key in _REQUIRED_KEYS:
        # page_id/event_type must be direct keys; revision_marker may come
        # from any candidate field via the resolver.
        if key != "revision_marker" and key not in payload:
            raise PayloadContractError(f"missing required key: {key}")

    page_id = str(payload.get("page_id", "")).strip()
    if not page_id or not _PAGE_ID_RE.match(page_id):
        raise PayloadContractError("invalid page_id (expected hex/dash identifier)")

    event_type = str(payload.get("event_type", "")).strip()
    if event_type not in SUPPORTED_EVENT_TYPES:
        raise PayloadContractError(f"unsupported event_type: {event_type!r}")

    obj = payload.get("object")
    if obj not in ("content_idea", "campaign", "incident"):
        raise PayloadContractError(f"unsupported object: {obj!r}")

    marker = resolver.resolve(payload)

    if event_type == "status_changed":
        current = payload.get("current_state")
        target = payload.get("target_state")
        if not current or not target:
            raise PayloadContractError(
                "status_changed payloads require current_state and target_state"
            )
        validate_transition(str(current), str(target))

    return notion_idempotency_key(page_id, event_type, marker)


# ---------------------------------------------------------------------------
# 4) Spec-mirror constants (drift-checked against the phase-06 doc)
# ---------------------------------------------------------------------------

# The doc block in docs/phases/phase-06-notion-business-os.md §4 lists
# these exact states; test_phase6_notion_m2 keeps the two in lockstep.
LIFECYCLE_DOC_STATES = (
    BACKLOG, RESEARCHING, DRAFT, REVIEW, APPROVED, SCHEDULED, PUBLISHED,
    REJECTED, ARCHIVED,
)

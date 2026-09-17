"""Phase 18 M1 — canonical HITL contracts (D-105/D-108).

Pure, dependency-free shapes and rules for the Human-In-The-Loop
approval engine:

  - `HitlReviewTicket`: ticket_id, queue_type, payload_ref,
    required_role, resolution_status, reviewer_actor_id, feedback,
    created_at_logical / decided_at_logical (deterministic logical
    clock values, NEVER wall clock).
  - Lifecycle (D-105): PENDING_REVIEW → CLAIMED → APPROVED |
    REJECTED | MODIFIED | ESCALATED | EXPIRED. ESCALATED is an
    escalation LOOP: the engine re-queues a fresh PENDING_REVIEW
    ticket with an elevated role — the escalated ticket itself is
    terminal-but-superseded-by-design. EXPIRED is reachable ONLY
    from the deterministic sweep (never from a reviewer action).
  - `ReviewAction` (what a reviewer submits) and `Resolution`
    (the durable outcome) with strict validation: claims require
    an actor; approvals/rejections/modifications require a claim;
    MODIFIED requires a payload_override dict; EXPIRED is never a
    reviewer action.
  - Mock local actors only (D-045): `role:*` / `agent:*` reference
    strings — no auth backends, no network, no real identities.

No network, no AI SDKs, no wall clock.
"""

from typing import Dict, Optional, Tuple

# --- queue types (D-105) -----------------------------------------------------------

QT_INSIGHT_REVIEW = "INSIGHT_REVIEW"
QT_PUBLISH_GATE = "PUBLISH_GATE"
QT_ORDER_OVERRIDE = "ORDER_OVERRIDE"
QT_ASSET_FLAG = "ASSET_FLAG"
QUEUE_TYPES = (QT_INSIGHT_REVIEW, QT_PUBLISH_GATE,
               QT_ORDER_OVERRIDE, QT_ASSET_FLAG)


class HitlContractError(Exception):
    """Class-B rejection — invalid ticket/action before any durable
    write."""


# --- lifecycle (D-105) ---------------------------------------------------------------

ST_PENDING_REVIEW = "PENDING_REVIEW"
ST_CLAIMED = "CLAIMED"
ST_APPROVED = "APPROVED"
ST_REJECTED = "REJECTED"
ST_MODIFIED = "MODIFIED"
ST_ESCALATED = "ESCALATED"
ST_EXPIRED = "EXPIRED"

TERMINAL_STATES = (ST_APPROVED, ST_REJECTED, ST_MODIFIED,
                   ST_ESCALATED, ST_EXPIRED)

# reviewer decisions from CLAIMED (EXPIRED deliberately absent —
# it is sweep-only, D-105)
REVIEW_DECISIONS = (ST_APPROVED, ST_REJECTED, ST_MODIFIED,
                    ST_ESCALATED)

LEGAL_EDGES = {
    (ST_PENDING_REVIEW, ST_CLAIMED),
    (ST_CLAIMED, ST_APPROVED),
    (ST_CLAIMED, ST_REJECTED),
    (ST_CLAIMED, ST_MODIFIED),
    (ST_CLAIMED, ST_ESCALATED),
    # sweep-only edge (validated in the engine with the logical clock)
    (ST_PENDING_REVIEW, ST_EXPIRED),
    (ST_CLAIMED, ST_EXPIRED),
}


def is_transition_legal(current: str, target: str) -> bool:
    if current == target:
        return False
    return (current, target) in LEGAL_EDGES


# roles (D-105): which reviewer class may resolve a ticket
ROLE_ANY = "any"
ROLE_OWNER = "owner"
ROLE_PUBLISHER = "publisher"
ROLE_OPS = "ops"
ROLE_ESCALATION = "escalation"  # only escalation targets use this
REQUIRED_ROLES = (ROLE_ANY, ROLE_OWNER, ROLE_PUBLISHER, ROLE_OPS,
                  ROLE_ESCALATION)

# role elevation order for escalations (deterministic)
ESCALATION_TARGET = {
    ROLE_ANY: ROLE_OPS,
    ROLE_OPS: ROLE_OWNER,
    ROLE_PUBLISHER: ROLE_OWNER,
    ROLE_OWNER: ROLE_ESCALATION,
}


def can_actor_resolve(required_role: str, actor: str) -> bool:
    """Mock local role discipline (D-045): an actor is a `role:*` or
    `agent:*` reference; resolution requires the ticket's role."""
    if not isinstance(actor, str) or ":" not in actor:
        return False
    actor_role = actor.split(":", 1)[1]
    if required_role == ROLE_ANY:
        return actor_role in (ROLE_OWNER, ROLE_PUBLISHER, ROLE_OPS)
    return actor_role == required_role


# --- ticket shape ---------------------------------------------------------------------

_REQUIRED = ("ticket_id", "queue_type", "payload_ref",
             "required_role", "resolution_status")


def validate_ticket(ticket: Dict) -> Dict:
    if not isinstance(ticket, dict):
        raise HitlContractError("ticket must be a dict")
    missing = [k for k in _REQUIRED if k not in ticket]
    if missing:
        raise HitlContractError(
            f"ticket missing required fields: {sorted(missing)}")
    if not isinstance(ticket["ticket_id"], str) or \
            not ticket["ticket_id"]:
        raise HitlContractError("ticket_id must be a non-empty string")
    if ticket["queue_type"] not in QUEUE_TYPES:
        raise HitlContractError(
            f"queue_type must be one of {sorted(QUEUE_TYPES)} (D-105)")
    if ticket["required_role"] not in REQUIRED_ROLES:
        raise HitlContractError(
            f"required_role must be one of {sorted(REQUIRED_ROLES)}")
    if ticket["resolution_status"] not in (ST_PENDING_REVIEW,
                                           ST_CLAIMED):
        raise HitlContractError(
            "a NEW ticket may only enter as PENDING_REVIEW or CLAIMED")
    if not isinstance(ticket["payload_ref"], str) or \
            not ticket["payload_ref"]:
        raise HitlContractError("payload_ref must be a non-empty string")
    reviewer = ticket.get("reviewer_actor_id")
    if ticket["resolution_status"] == ST_CLAIMED:
        if not isinstance(reviewer, str) or ":" not in reviewer:
            raise HitlContractError(
                "a CLAIMED ticket must carry a reviewer actor ref")
    elif reviewer is not None:
        raise HitlContractError(
            "a PENDING_REVIEW ticket must not carry a reviewer")
    for k in ("created_at_logical",):
        if not isinstance(ticket.get(k), str) or not ticket[k]:
            raise HitlContractError(
                f"{k} must be a non-empty logical clock value")
    return ticket


# --- actions & resolutions -------------------------------------------------------------

def validate_action(action: Dict) -> Dict:
    """A ReviewAction: what a reviewer submits against a CLAIMED
    ticket. EXPIRED is never a reviewer action (D-105)."""
    if not isinstance(action, dict):
        raise HitlContractError("action must be a dict")
    decision = action.get("decision")
    if decision not in REVIEW_DECISIONS:
        raise HitlContractError(
            f"decision must be one of {sorted(REVIEW_DECISIONS)} "
            "(EXPIRED is sweep-only, D-105)")
    actor = action.get("reviewer_actor_id")
    if not isinstance(actor, str) or ":" not in actor:
        raise HitlContractError(
            "reviewer_actor_id must be a role:/agent: reference")
    if decision == ST_MODIFIED and \
            not isinstance(action.get("payload_override"), dict):
        raise HitlContractError(
            "MODIFIED requires a payload_override dict (D-105)")
    if decision != ST_MODIFIED and "payload_override" in action:
        raise HitlContractError(
            "payload_override is only valid for MODIFIED")
    return action


def resolution_from_action(action: Dict) -> Dict:
    """The durable Resolution derived from a validated action."""
    validate_action(action)
    return {
        "decision": action["decision"],
        "reviewer_actor_id": action["reviewer_actor_id"],
        "payload_override": action.get("payload_override"),
        "feedback_notes": str(action.get("feedback_notes", ""))[:2000],
    }

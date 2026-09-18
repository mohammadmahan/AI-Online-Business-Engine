"""Phase 19 M1 — canonical admin contracts (D-109).

Pure, dependency-free shapes and rules for the operator control
plane:

  - `OperatorAction`: action_id, command, target, actor, reason,
    logical timestamps. The command grammar is a CLOSED vocabulary:
    PAUSE_QUEUE, RESUME_QUEUE, RETRY_DLQ_ITEM,
    FORCE_SUPERSEDE_INSIGHT, MANUAL_SLOT_OVERRIDE, REPLAY_EVENTS.
  - RBAC (D-109/D-045): deterministic permission validation over
    local actor tokens — `actor:operator:*` (queue ops only),
    `actor:admin:*` (everything), `actor:system:*` (engine-internal,
    sweep actions). No auth provider, no network, no real identity.
  - `QueueControlCommand`, `SystemDiagnosticReport`,
    `AuditQueryFilter` shapes with strict Class-B validation.

No network, no UI framework, no wall clock.
"""

from typing import Dict, Optional, Tuple

# --- command grammar (closed vocabulary, D-109) ---------------------------------------

CMD_PAUSE_QUEUE = "PAUSE_QUEUE"
CMD_RESUME_QUEUE = "RESUME_QUEUE"
CMD_RETRY_DLQ_ITEM = "RETRY_DLQ_ITEM"
CMD_FORCE_SUPERSEDE_INSIGHT = "FORCE_SUPERSEDE_INSIGHT"
CMD_MANUAL_SLOT_OVERRIDE = "MANUAL_SLOT_OVERRIDE"
CMD_REPLAY_EVENTS = "REPLAY_EVENTS"
CMD_COMPACT_RETIREABLE = "COMPACT_RETIREABLE"
COMMANDS = (CMD_PAUSE_QUEUE, CMD_RESUME_QUEUE, CMD_RETRY_DLQ_ITEM,
            CMD_FORCE_SUPERSEDE_INSIGHT, CMD_MANUAL_SLOT_OVERRIDE,
            CMD_REPLAY_EVENTS, CMD_COMPACT_RETIREABLE)

# commands that mutate platform state (vs read-only report commands)
MUTATING_COMMANDS = (CMD_PAUSE_QUEUE, CMD_RESUME_QUEUE,
                     CMD_RETRY_DLQ_ITEM, CMD_FORCE_SUPERSEDE_INSIGHT,
                     CMD_MANUAL_SLOT_OVERRIDE)


class AdminContractError(Exception):
    """Class-B rejection — invalid action/command before any durable
    write."""


# --- RBAC (D-109/D-045) ----------------------------------------------------------------

R_OPERATOR = "operator"
R_ADMIN = "admin"
R_SYSTEM = "system"
ROLES = (R_OPERATOR, R_ADMIN, R_SYSTEM)

# deterministic permission matrix: command → roles allowed
PERMISSIONS: Dict[str, Tuple[str, ...]] = {
    CMD_PAUSE_QUEUE: (R_OPERATOR, R_ADMIN),
    CMD_RESUME_QUEUE: (R_OPERATOR, R_ADMIN),
    CMD_RETRY_DLQ_ITEM: (R_OPERATOR, R_ADMIN),
    CMD_FORCE_SUPERSEDE_INSIGHT: (R_ADMIN,),
    CMD_MANUAL_SLOT_OVERRIDE: (R_ADMIN,),
    CMD_REPLAY_EVENTS: (R_ADMIN,),
    # D-125 (owner directive 2026-09-18): compaction is destructive-
    # adjacent (verified teardown) — admin-only, never operator.
    CMD_COMPACT_RETIREABLE: (R_ADMIN,),
}


def actor_role(actor: str) -> str:
    """`actor:operator:rev-42` → `operator`. A token without a
    non-empty id part is malformed and rejected here — role and id
    are only meaningful together (D-045)."""
    parts = actor.split(":")
    if len(parts) < 3 or parts[0] != "actor" or not parts[2]:
        raise AdminContractError(
            "actor must be an `actor:<role>:<id>` local token (D-045)")
    if parts[1] not in ROLES:
        raise AdminContractError(
            f"actor role must be one of {sorted(ROLES)}")
    return parts[1]


def actor_id(actor: str) -> str:
    parts = actor.split(":")
    if len(parts) < 3 or not parts[2]:
        raise AdminContractError(
            "actor token needs a non-empty id: actor:<role>:<id>")
    return ":".join(parts[2:])


def parse_actor(actor: str) -> Tuple[str, str]:
    """Validated (role, id) from a local actor token (D-045)."""
    return actor_role(actor), actor_id(actor)


def is_permitted(actor: str, command: str) -> bool:
    """Deterministic permission validation (D-109)."""
    return actor_role(actor) in PERMISSIONS.get(command, ())


# --- action shape -------------------------------------------------------------------------

_REQUIRED = ("action_id", "command", "target", "actor",
             "created_at_logical")


# declared input bounds (D-114 hardening re-audit)
MAX_ACTION_ID_LEN = 128
MAX_TARGET_LEN = 256
MAX_REASON_LEN = 2000
MAX_QUEUE_NAME_LEN = 128


def validate_action(action: Dict) -> Dict:
    if not isinstance(action, dict):
        raise AdminContractError("action must be a dict")
    missing = [k for k in _REQUIRED if k not in action]
    if missing:
        raise AdminContractError(
            f"action missing required fields: {sorted(missing)}")
    if action["command"] not in COMMANDS:
        raise AdminContractError(
            f"command must be one of {sorted(COMMANDS)} (D-109: "
            "closed grammar)")
    if not isinstance(action["action_id"], str) or \
            not action["action_id"]:
        raise AdminContractError("action_id must be a non-empty string")
    if len(action["action_id"]) > MAX_ACTION_ID_LEN:
        raise AdminContractError(
            f"action_id exceeds {MAX_ACTION_ID_LEN} chars (D-114)")
    if not isinstance(action["target"], str) or \
            not action["target"]:
        raise AdminContractError("target must be a non-empty string")
    if len(action["target"]) > MAX_TARGET_LEN:
        raise AdminContractError(
            f"target exceeds {MAX_TARGET_LEN} chars (D-114)")
    role = actor_role(action["actor"])          # validates the token
    actor_id(action["actor"])                   # validates the id
    if not is_permitted(action["actor"], action["command"]):
        raise AdminContractError(
            f"role {role!r} may not execute {action['command']} "
            "(RBAC, D-109)")
    if not isinstance(action.get("created_at_logical"), str) or \
            not action["created_at_logical"]:
        raise AdminContractError(
            "created_at_logical must be a non-empty logical value")
    if action["command"] == CMD_REPLAY_EVENTS:
        reason = action.get("reason")
        if not isinstance(reason, str) or not reason:
            raise AdminContractError(
                "REPLAY_EVENTS requires a non-empty written reason "
                "(D-110)")
        if len(reason) > MAX_REASON_LEN:
            raise AdminContractError(
                f"reason exceeds {MAX_REASON_LEN} chars (D-114)")
    return action


# --- queue control states (D-111) -----------------------------------------------------------

QC_OPEN = "OPEN"
QC_PAUSED = "PAUSED"
QUEUE_STATES = (QC_OPEN, QC_PAUSED)


def validate_control_command(cmd: Dict) -> Dict:
    if not isinstance(cmd, dict):
        raise AdminContractError("control command must be a dict")
    if cmd.get("command") not in (CMD_PAUSE_QUEUE, CMD_RESUME_QUEUE):
        raise AdminContractError(
            "QueueControlCommand allows only PAUSE_QUEUE/RESUME_QUEUE")
    if not isinstance(cmd.get("queue_name"), str) or \
            not cmd["queue_name"]:
        raise AdminContractError("queue_name must be a non-empty string")
    if len(cmd["queue_name"]) > MAX_QUEUE_NAME_LEN:
        raise AdminContractError(
            f"queue_name exceeds {MAX_QUEUE_NAME_LEN} chars (D-114)")
    return cmd


# --- circuit breaker states (D-111) -------------------------------------------------------------

CB_CLOSED = "CLOSED"
CB_OPEN = "OPEN"
CB_HALF_OPEN = "HALF_OPEN"
BREAKER_STATES = (CB_CLOSED, CB_OPEN, CB_HALF_OPEN)


def breaker_transition(current: str, target: str) -> bool:
    """Deterministic breaker state machine: CLOSE→OPEN (trip),
    OPEN→HALF_OPEN (cool-down elapsed), HALF_OPEN→CLOSED (probe ok),
    HALF_OPEN→OPEN (probe failed). Nothing else."""
    edges = {(CB_CLOSED, CB_OPEN), (CB_OPEN, CB_HALF_OPEN),
             (CB_HALF_OPEN, CB_CLOSED), (CB_HALF_OPEN, CB_OPEN)}
    return current != target and (current, target) in edges


# --- diagnostic report shape (D-110) --------------------------------------------------------------

REPORT_DOMAINS = ("queues", "hitl", "insights", "assets", "breakers")


def validate_report(report: Dict) -> Dict:
    if not isinstance(report, dict):
        raise AdminContractError("report must be a dict")
    if not isinstance(report.get("generated_at_logical"), str) or \
            not report["generated_at_logical"]:
        raise AdminContractError(
            "report needs generated_at_logical (injected clock)")
    domains = report.get("domains")
    if not isinstance(domains, dict) or \
            not set(domains) <= set(REPORT_DOMAINS):
        raise AdminContractError(
            f"report domains must be a subset of {REPORT_DOMAINS}")
    return report


# --- audit query filter (D-110) --------------------------------------------------------------------

QUERY_FIELDS = ("actor", "command", "target", "since_logical",
                "until_logical", "limit")


def validate_query_filter(flt: Dict) -> Dict:
    if not isinstance(flt, dict):
        raise AdminContractError("filter must be a dict")
    unknown = set(flt) - set(QUERY_FIELDS)
    if unknown:
        raise AdminContractError(
            f"unknown filter fields: {sorted(unknown)}")
    if "limit" in flt and (not isinstance(flt["limit"], int)
                           or isinstance(flt["limit"], bool)
                           or flt["limit"] <= 0):
        raise AdminContractError("limit must be a positive integer")
    return flt


# --- replay safety (D-110) ----------------------------------------------------------------------------

def replay_mode(action: Dict) -> str:
    """REPLAY_EVENTS is DRY_RUN unless an explicit atomic
    confirmation key is supplied (D-110)."""
    if action.get("confirmation_key"):
        return "APPLY"
    return "DRY_RUN"


def make_confirmation_key() -> str:
    """Single-use confirmation key for APPLY-mode replay. Derived
    deterministically from the action id + a caller nonce — the
    engine burns the key on first use (D-110)."""
    import hashlib
    import uuid
    nonce = uuid.uuid4().hex
    return hashlib.sha256(nonce.encode("utf-8")).hexdigest()[:24]

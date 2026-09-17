"""Phase 14 M1 — notification contracts (D-089).

Canonical NotificationEvent schema, versioned template registry with
declared required variables, priority matrix, and STRICT LOCAL
validation — pure functions only (no I/O, no adapters, no network),
mirroring the D-069/D-073/D-077/D-081/D-085 contract discipline.

Local prevention (D-052): an invalid notification is a Class-B
rejection BEFORE anything is queued — no dispatch path is ever
reached with a malformed payload. Recipients are opaque local user
references; no address is invented or harvested (D-045). The wall
clock is never read; deferral windows are computed from the event's
own recorded timestamps (D-085/D-086 precedent).
"""

import hashlib
import re
from typing import Dict, List, Optional, Tuple

SOURCE_SYSTEM = "notifications"

# --- channels (D-089) --------------------------------------------------------

CH_IN_APP = "IN_APP"
CH_EMAIL = "EMAIL"
CH_SMS = "SMS"
CH_WEBHOOK = "WEBHOOK"
CHANNELS = (CH_IN_APP, CH_EMAIL, CH_SMS, CH_WEBHOOK)

# --- priority matrix (D-089) -------------------------------------------------

PR_LOW = "LOW"
PR_NORMAL = "NORMAL"
PR_HIGH = "HIGH"
PR_CRITICAL = "CRITICAL"
PRIORITIES = (PR_LOW, PR_NORMAL, PR_HIGH, PR_CRITICAL)

# quiet hours apply to these priorities only; CRITICAL bypasses policy
_QUIET_HOURS_PRIORITIES = (PR_LOW, PR_NORMAL)
# max deliveries per recipient per rolling window (per priority class)
_FREQUENCY_CAPS = {PR_LOW: 20, PR_NORMAL: 20, PR_HIGH: 10, PR_CRITICAL: 50}
_FREQUENCY_WINDOW_HOURS = 24

# quiet hours are expressed as whole hours in the event's own tz-aware
# timestamp; a notification whose priority is policy-gated and whose
# local hour falls inside the window is deferred, not dropped
QUIET_START_HOUR = 22  # inclusive
QUIET_END_HOUR = 7     # exclusive


class NotificationContractError(ValueError):
    """Local Class-B rejection — the payload never reaches a queue."""


# --- versioned template registry (D-089) -------------------------------------
# declaration only — bodies live with the producing domain or channel
# adapter; the contract enforces the VARIABLE CONTRACT, not prose.

TEMPLATES: Dict[str, Dict] = {
    "order.fulfillment.v1": {
        "channels": (CH_IN_APP, CH_EMAIL, CH_WEBHOOK),
        "min_priority": PR_NORMAL,
        "required_vars": ("order_ref", "state"),
    },
    "order.cancelled.v1": {
        "channels": (CH_IN_APP, CH_EMAIL),
        "min_priority": PR_NORMAL,
        "required_vars": ("order_ref",),
    },
    "order.shipped.v1": {
        "channels": (CH_IN_APP, CH_EMAIL, CH_SMS),
        "min_priority": PR_NORMAL,
        "required_vars": ("order_ref",),
    },
    "hitl.review_required.v1": {
        "channels": (CH_IN_APP, CH_EMAIL, CH_WEBHOOK),
        "min_priority": PR_HIGH,
        "required_vars": ("queue_ref", "reason"),
    },
    "dlq.item_admitted.v1": {
        "channels": (CH_IN_APP, CH_WEBHOOK),
        "min_priority": PR_HIGH,
        "required_vars": ("dedup_key", "failure_reason"),
    },
    "campaign.published.v1": {
        "channels": (CH_IN_APP, CH_WEBHOOK),
        "min_priority": PR_LOW,
        "required_vars": ("campaign_id", "targets"),
    },
    "system.health.v1": {
        "channels": (CH_IN_APP, CH_WEBHOOK),
        "min_priority": PR_LOW,
        "required_vars": ("component", "detail"),
    },
}

_TEMPLATE_RE = re.compile(r"^[a-z0-9_]+(\.[a-z0-9_]+)+\.v\d+$")
_VARNAME_RE = re.compile(r"^[a-z_][a-z0-9_]{0,63}$")
_RECIPIENT_RE = re.compile(r"^[A-Za-z0-9_.:@-]{1,128}$")
_ISO_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?"
    r"(Z|[+-]\d{2}:\d{2})$")

# channel-specific payload requirements (strict local boundaries)
CHANNEL_REQUIREMENTS: Dict[str, Tuple[str, ...]] = {
    CH_EMAIL: ("subject",),
    CH_WEBHOOK: ("endpoint_ref",),
    CH_SMS: ("phone_ref",),
    CH_IN_APP: (),
}

MAX_BODY_VARS = 64


def template_ids() -> Tuple[str, ...]:
    return tuple(sorted(TEMPLATES))


def required_vars(template_id: str) -> Tuple[str, ...]:
    return TEMPLATES[template_id]["required_vars"]


# --- validation (D-089) ------------------------------------------------------

def validate_notification(event: Dict) -> Dict:
    """Strict local validation. Returns the event unchanged on success;
    raises NotificationContractError (Class-B) before queueing."""
    if not isinstance(event, dict):
        raise NotificationContractError("notification must be a dict")

    recipient = event.get("recipient")
    if not isinstance(recipient, str) or not _RECIPIENT_RE.match(recipient):
        raise NotificationContractError(
            "recipient must be an opaque local user reference "
            "(1-128 chars of [A-Za-z0-9_.:@-])")

    channel = event.get("channel")
    if channel not in CHANNELS:
        raise NotificationContractError(
            f"channel must be one of {list(CHANNELS)} (D-089)")

    priority = event.get("priority", PR_NORMAL)
    if priority not in PRIORITIES:
        raise NotificationContractError(
            f"priority must be one of {list(PRIORITIES)} (D-089)")

    template_id = event.get("template_id")
    if not isinstance(template_id, str) or \
            not _TEMPLATE_RE.match(template_id):
        raise NotificationContractError(
            "template_id must match name.vN (e.g. order.fulfillment.v1)")
    if template_id not in TEMPLATES:
        raise NotificationContractError(
            f"unknown template {template_id!r} — not in the versioned "
            "registry (D-089)")

    tmpl = TEMPLATES[template_id]
    if channel not in tmpl["channels"]:
        raise NotificationContractError(
            f"template {template_id} does not support channel {channel}")
    if PRIORITIES.index(priority) < PRIORITIES.index(tmpl["min_priority"]):
        raise NotificationContractError(
            f"template {template_id} requires priority >= "
            f"{tmpl['min_priority']}")

    variables = event.get("variables")
    if not isinstance(variables, dict):
        raise NotificationContractError("variables must be a dict")
    if len(variables) > MAX_BODY_VARS:
        raise NotificationContractError(
            f"too many variables (>{MAX_BODY_VARS})")
    for name in variables:
        if not _VARNAME_RE.match(name):
            raise NotificationContractError(
                f"invalid variable name {name!r}")
    for req in tmpl["required_vars"]:
        if req not in variables:
            raise NotificationContractError(
                f"template {template_id} requires variable {req!r} "
                "— missing required variable (Class-B before queueing, "
                "D-089)")
    for req in CHANNEL_REQUIREMENTS[channel]:
        if req not in variables:
            raise NotificationContractError(
                f"channel {channel} requires variable {req!r}")

    occurred_at = event.get("occurred_at")
    if not isinstance(occurred_at, str) or not _ISO_RE.match(occurred_at):
        raise NotificationContractError(
            "occurred_at must be an ISO-8601 timestamp with offset "
            "(the producer's own record — never the wall clock)")

    return event


def dedup_key(event: Dict) -> str:
    """D-090 identity: SHA-256 over (recipient, channel, template,
    logical event key). The producer supplies `event_key` — the one
    logical identity of this alert (e.g. order ref + transition);
    retries of the SAME logical alert collapse; distinct alerts don't.
    No wall clock, no payload hash (variables may be reformatted)."""
    validate_notification(event)
    logical = event.get("event_key")
    if not isinstance(logical, str) or not logical or len(logical) > 256:
        raise NotificationContractError(
            "event_key must be a non-empty string (<=256 chars) — the "
            "logical identity of this alert")
    material = "\x1f".join([
        "notification-v1", event["recipient"], event["channel"],
        event["template_id"], logical,
    ])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


# --- policy guards (D-090) — pure functions of payload + durable ledger ------

def _local_hour(occurred_at: str) -> int:
    """Hour in the timestamp's own offset — pure string math, no clock."""
    m = re.match(r"^\d{4}-\d{2}-\d{2}T(\d{2}):", occurred_at)
    hour = int(m.group(1))
    m_off = re.search(r"([+-])(\d{2}):(\d{2})$", occurred_at)
    if m_off:
        sign = 1 if m_off.group(1) == "+" else -1
        hour = (hour + sign * int(m_off.group(2))) % 24
    return hour


def in_quiet_hours(occurred_at: str) -> bool:
    h = _local_hour(occurred_at)
    if QUIET_START_HOUR > QUIET_END_HOUR:  # window wraps midnight
        return h >= QUIET_START_HOUR or h < QUIET_END_HOUR
    return QUIET_START_HOUR <= h < QUIET_END_HOUR


def policy_decision(event: Dict,
                    recent_deliveries: int) -> Dict:
    """Quiet hours + frequency cap, evaluated BEFORE the vault claim.
    `recent_deliveries` = count from the DURABLE ledger for this
    recipient within the frequency window (caller queries the store;
    this function stays pure). Returns a deterministic decision dict —
    never raises for policy reasons; only contract errors raise."""
    validate_notification(event)
    priority = event.get("priority", PR_NORMAL)
    if priority == PR_CRITICAL:
        return {"verdict": "allow", "reason": "critical_bypass"}
    if priority in _QUIET_HOURS_PRIORITIES and \
            in_quiet_hours(event["occurred_at"]):
        return {"verdict": "defer", "reason": "quiet_hours"}
    cap = _FREQUENCY_CAPS[priority]
    if recent_deliveries >= cap:
        return {"verdict": "defer", "reason": "frequency_cap",
                "cap": cap, "window_hours": _FREQUENCY_WINDOW_HOURS}
    return {"verdict": "allow", "reason": "policy_ok"}


# --- status vocabulary (D-092) -----------------------------------------------

ST_PENDING = "PENDING"
ST_QUEUED = "QUEUED"
ST_DISPATCHED = "DISPATCHED"
ST_DELIVERED = "DELIVERED"
ST_FAILED = "FAILED"
ST_POLICY_DEFERRED = "POLICY_DEFERRED"
ST_DUPLICATE_BLOCKED = "DUPLICATE_BLOCKED"

# outcomes recorded by adapters/dispatcher (D-092 aggregation inputs)
OUT_DELIVERED = "delivered"
OUT_PERMANENT_FAILURE = "permanent_failure"
OUT_TRANSIENT_FAILURE = "transient_failure"
OUT_RATE_LIMITED = "rate_limited"
OUT_POLICY_DEFERRED = "policy_deferred"
OUT_DUPLICATE_BLOCKED = "duplicate_blocked"

TERMINAL_OK = (OUT_DELIVERED,)
TERMINAL_BAD = (OUT_PERMANENT_FAILURE,)

# D-052 classification for the worker
CLASS_TRANSIENT = "A"
CLASS_CONTRACT = "B"
CLASS_THROTTLE = "C"

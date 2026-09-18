"""Phase 25 M1 — end-to-end stage contracts (D-133). Pure.

The MASTER_PLAN §13 Phase 25 flow as ten declared stages. Each
stage has a declared input envelope and output envelope; the
conductor enforces them so cross-stage payloads never gain
undeclared keys (zero schema mutation) and the D-121 trace context
traverses every stage unchanged.

No I/O imports: stage implementations are injected (RULES §35).
"""
from __future__ import annotations

from typing import Dict, FrozenSet, Tuple

__all__ = [
    "STAGES", "STAGE_ENVELOPES", "ConductorError",
    "StageEnvelope", "validate_envelope", "check_context",
]


class ConductorError(Exception):
    """Conductor contract misuse (bad stage wiring/envelope)."""


class StageEnvelope:
    """Declared read/write key sets for one stage."""

    __slots__ = ("reads", "writes")

    def __init__(self, reads: FrozenSet, writes: FrozenSet):
        if not reads or not writes:
            raise ConductorError(
                "stage envelope reads/writes must be non-empty")
        object.__setattr__(self, "reads", reads)
        object.__setattr__(self, "writes", writes)

    def __setattr__(self, name, value):  # immutable
        raise ConductorError("StageEnvelope is immutable")


# The MASTER_PLAN §13 Phase 25 flow, in order.
STAGES: Tuple[str, ...] = (
    "LEAD_CAPTURE",
    "CONVERSATION",
    "PRODUCT_DISCOVERY",
    "CART_ORDER",
    "PAYMENT_INTENT",
    "PAYMENT_VERIFICATION",
    "INVENTORY_RESERVATION",
    "SHIPPING_INTENT",
    "NOTIFICATION_DISPATCH",
    "ANALYTICS_PROJECTION",
)

# Declared envelopes: keys a stage MAY read from the flow context and
# keys it MUST produce. Declarations are data — the conductor never
# hardcodes stage internals.
STAGE_ENVELOPES: Dict[str, "StageEnvelope"] = {
    "LEAD_CAPTURE": StageEnvelope(
        reads=frozenset({"channel"}),
        writes=frozenset({"lead_id", "contact_ref"}),
    ),
    "CONVERSATION": StageEnvelope(
        reads=frozenset({"lead_id", "contact_ref", "message"}),
        writes=frozenset({"intent", "cart_draft"}),
    ),
    "PRODUCT_DISCOVERY": StageEnvelope(
        reads=frozenset({"cart_draft"}),
        writes=frozenset({"product_refs"}),
    ),
    "CART_ORDER": StageEnvelope(
        reads=frozenset({"product_refs", "lead_id"}),
        writes=frozenset({"order_key", "order_state"}),
    ),
    "PAYMENT_INTENT": StageEnvelope(
        reads=frozenset({"order_key"}),
        writes=frozenset({"payment_ref"}),
    ),
    "PAYMENT_VERIFICATION": StageEnvelope(
        reads=frozenset({"payment_ref", "order_key"}),
        writes=frozenset({"payment_verdict"}),
    ),
    "INVENTORY_RESERVATION": StageEnvelope(
        reads=frozenset({"order_key", "payment_verdict"}),
        writes=frozenset({"inventory_state"}),
    ),
    "SHIPPING_INTENT": StageEnvelope(
        reads=frozenset({"order_key", "inventory_state"}),
        writes=frozenset({"shipping_ref"}),
    ),
    "NOTIFICATION_DISPATCH": StageEnvelope(
        reads=frozenset({"order_key", "shipping_ref", "lead_id"}),
        writes=frozenset({"notification_outcome"}),
    ),
    "ANALYTICS_PROJECTION": StageEnvelope(
        reads=frozenset({"order_key"}),
        writes=frozenset({"projection_summary"}),
    ),
}


def validate_envelope(stage: str, produced: Dict) -> None:
    """A stage's output may contain ONLY its declared write keys."""
    env = STAGE_ENVELOPES.get(stage)
    if env is None:
        raise ConductorError(f"undeclared stage: {stage}")
    extra = set(produced) - set(env.writes)
    if extra:
        raise ConductorError(
            f"schema mutation at {stage}: undeclared output keys "
            f"{sorted(extra)} (D-133 zero-mutation rule)")


def check_context(context: Dict) -> None:
    """The trace context keys must survive every stage unchanged."""
    for key in ("trace_id", "correlation_id"):
        if not context.get(key):
            raise ConductorError(
                f"trace context lost `{key}` (D-133 unbroken-trace rule)")

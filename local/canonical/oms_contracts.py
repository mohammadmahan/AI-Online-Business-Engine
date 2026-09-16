"""Phase 12 M1 — OMS order contract (D-081/D-082).

Canonical Order schema + lifecycle state machine + `client_order_id`
SHA-256 idempotency, mirroring the pure-function discipline of the
D-069/D-073/D-077 contract modules: no I/O, no adapter, no network.

Identifier discipline (D-014/D-015/D-017): line items bind to
owner-assigned canonical Product ID / Variant ID and the SKU as a
separate concept — the OMS never derives one from another and never
invents an ID. Pricing is plain integers (minor units) so no float
arithmetic ever touches money.

Payment is a boundary (D-083): `payment_status` accepts only the
pending/unpaid markers — no gateway fields exist anywhere.
"""

import hashlib
import re
from typing import Dict, List, Optional

SOURCE_SYSTEM = "oms"
OP_ORDER = "order_transition"

# --- lifecycle (D-081) ----------------------------------------------------

PLACED = "PLACED"
VALIDATED = "VALIDATED"
FULFILLING = "FULFILLING"
COMPLETED = "COMPLETED"
CANCELLED = "CANCELLED"
REFUNDED = "REFUNDED"

ORDER_STATES = (PLACED, VALIDATED, FULFILLING, COMPLETED,
                CANCELLED, REFUNDED)
TERMINAL_STATES = (COMPLETED, CANCELLED, REFUNDED)

# (from, to) — strict, no implicit jumps (D-081). COMPLETED→REFUNDED is
# the single audit-legal exit from a terminal state; every other
# terminal has no outgoing edge.
ALLOWED_TRANSITIONS = {
    (PLACED, VALIDATED),
    (VALIDATED, FULFILLING),
    (FULFILLING, COMPLETED),
    (PLACED, CANCELLED),
    (VALIDATED, CANCELLED),
    (FULFILLING, CANCELLED),
    (COMPLETED, REFUNDED),
}

# Terminal states from which NO transition may ever leave (CANCELLED,
# REFUNDED). COMPLETED is a special terminal: exactly one audited
# exit (REFUNDED) is whitelisted above.
_ABSOLUTE_TERMINALS = (CANCELLED, REFUNDED)

# Payment markers (D-083): boundary only — never a gateway
PAYMENT_STATUSES = ("pending", "unpaid")


class OmsContractError(ValueError):
    """Class-B carrier: local contract violation — never persisted."""

    failure_class = "B"


def _strict_int(value, what: str) -> int:
    """Strict integer coercion for money and quantities: floats are
    REJECTED (a truncated 10.5 is not money), bools are rejected, and
    digit strings are accepted for transport formats. Money and stock
    counts are exact — silent truncation is a defect, not a feature."""
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise OmsContractError(f"{what} must be an integer (D-081)")
    if isinstance(value, str):
        if not re.fullmatch(r"-?\d+", value.strip()):
            raise OmsContractError(f"{what} must be an integer (D-081)")
        return int(value.strip())
    return int(value)


# --- SKU mapping (D-082): the ONLY stock identity -------------------------

def stock_key(variant_ref: Dict) -> str:
    """Deterministic stock identity for a line item.

    The SKU is the stock-keeping identity (D-082), but it must travel
    WITH its canonical Variant ID so the binding stays explicit
    (D-017: SKU is never the internal identity — it is never used to
    *look up* a variant here, only to key the inventory row that was
    seeded from the canonical mapping registry).
    """
    vid = str(variant_ref.get("variant_id") or "")
    sku = str(variant_ref.get("sku") or "")
    if not vid or not sku:
        raise OmsContractError(
            "line item requires both variant_id and sku "
            "(D-017/D-082 — no identity may be derived from the other)")
    material = f"oms-stock-v1\x1f{vid}\x1f{sku}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


# --- line items -----------------------------------------------------------

def _validate_line_item(raw, index: int) -> Dict:
    if not isinstance(raw, dict):
        raise OmsContractError(f"line_items[{index}] must be a dict")
    for key in ("product_id", "variant_id", "sku", "quantity",
                "unit_price_minor"):
        if key not in raw or raw[key] in (None, ""):
            raise OmsContractError(
                f"line_items[{index}] missing {key} (D-081)")
    product_id = str(raw["product_id"]).strip()
    variant_id = str(raw["variant_id"]).strip()
    sku = str(raw["sku"]).strip()
    if not re.fullmatch(r"[A-Za-z0-9._-]{3,64}", product_id):
        raise OmsContractError(
            f"line_items[{index}] product_id malformed (D-017/D-081)")
    if not re.fullmatch(r"[A-Za-z0-9._-]{3,64}", variant_id):
        raise OmsContractError(
            f"line_items[{index}] variant_id malformed (D-017/D-081)")
    if not re.fullmatch(r"[A-Za-z0-9._-]{3,64}", sku):
        raise OmsContractError(
            f"line_items[{index}] sku malformed (D-017/D-081)")
    quantity = _strict_int(raw["quantity"],
                           f"line_items[{index}] quantity")
    if quantity < 1:
        raise OmsContractError(
            f"line_items[{index}] quantity must be >= 1 (D-081)")
    unit_price = _strict_int(
        raw["unit_price_minor"],
        f"line_items[{index}] unit_price_minor")
    if unit_price < 0:
        raise OmsContractError(
            f"line_items[{index}] unit_price_minor must be >= 0 (D-081)")
    key = stock_key({"variant_id": variant_id, "sku": sku})
    return {"product_id": product_id, "variant_id": variant_id,
            "sku": sku, "quantity": quantity,
            "unit_price_minor": unit_price, "stock_key": key}


# --- order contract --------------------------------------------------------

ORDER_REQUIRED = ("order_id", "client_order_id", "customer_ref",
                  "line_items", "placed_at")


def validate_order(order) -> Dict:
    """Validate + normalize one order (D-081). Pure/local: raises
    OmsContractError (Class-B) BEFORE any persistence."""
    if not isinstance(order, dict):
        raise OmsContractError("order must be a dict (D-081)")
    for key in ORDER_REQUIRED:
        if key not in order or order[key] in (None, ""):
            raise OmsContractError(f"order missing {key} (D-081)")
    order_id = str(order["order_id"]).strip()
    if not re.fullmatch(r"[A-Za-z0-9._-]{3,64}", order_id):
        raise OmsContractError(
            "order_id must match [A-Za-z0-9._-]{3,64} (D-081)")
    client_order_id = str(order["client_order_id"]).strip()
    if not re.fullmatch(r"[A-Za-z0-9._-]{8,120}", client_order_id):
        raise OmsContractError(
            "client_order_id must match [A-Za-z0-9._-]{8,120} (D-081)")
    customer_ref = str(order["customer_ref"]).strip()
    if not customer_ref:
        raise OmsContractError("customer_ref must be non-empty (D-081)")
    raw_items = order["line_items"]
    if not isinstance(raw_items, (list, tuple)) or not raw_items:
        raise OmsContractError(
            "line_items must be a non-empty list (D-081)")
    items: List[Dict] = [_validate_line_item(x, i)
                         for i, x in enumerate(raw_items)]
    # duplicate variant lines collapse deterministically — same variant
    # twice means one line with summed quantity (prevents oversell
    # under reservation splitting)
    merged: Dict[str, Dict] = {}
    for item in items:
        existing = merged.get(item["stock_key"])
        if existing is None:
            merged[item["stock_key"]] = dict(item)
        else:
            if existing["unit_price_minor"] != item["unit_price_minor"]:
                raise OmsContractError(
                    f"conflicting unit price for variant "
                    f"{existing['variant_id']} (D-081)")
            existing["quantity"] += item["quantity"]
    payment_status = str(order.get("payment_status") or "pending").strip()
    if payment_status not in PAYMENT_STATUSES:
        raise OmsContractError(
            f"payment_status {payment_status!r} not allowed — payment "
            f"is a boundary, markers only {list(PAYMENT_STATUSES)} "
            "(D-083)")
    tax_minor = _strict_int(order.get("tax_minor") or 0,
                            "tax_minor")
    if tax_minor < 0:
        raise OmsContractError("tax_minor must be >= 0 (D-081)")
    total_minor = sum(i["quantity"] * i["unit_price_minor"]
                      for i in merged.values()) + tax_minor
    return {
        "order_id": order_id,
        "client_order_id": client_order_id,
        "order_key": order_idempotency_key(client_order_id),
        "customer_ref": customer_ref,
        "line_items": [merged[k] for k in sorted(merged)],
        "payment_status": payment_status,
        "tax_minor": tax_minor,
        "total_minor": total_minor,
        "currency": str(order.get("currency") or "IRT"),
        "placed_at": str(order["placed_at"]),
    }


def order_idempotency_key(client_order_id: str) -> str:
    """D-081 duplicate protection: deterministic SHA-256 over the
    caller-supplied client_order_id. Same client order → same key →
    D-027 replay semantics; no wall-clock input ever."""
    material = f"oms-order-v1\x1f{client_order_id}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


# --- transitions ------------------------------------------------------------

def validate_transition(from_state: str, to_state: str) -> None:
    """Strict state machine (D-081): raises on any edge not in
    ALLOWED_TRANSITIONS. CANCELLED/REFUNDED are absolute terminals
    (no outgoing edge); COMPLETED's only exit is the audited
    COMPLETED→REFUNDED edge whitelisted above."""
    if from_state not in ORDER_STATES or to_state not in ORDER_STATES:
        raise OmsContractError(
            f"unknown order state {from_state!r}→{to_state!r} (D-081)")
    if from_state in _ABSOLUTE_TERMINALS:
        raise OmsContractError(
            f"terminal state {from_state} has no outgoing transitions "
            "(D-081)")
    if (from_state, to_state) not in ALLOWED_TRANSITIONS:
        raise OmsContractError(
            f"transition {from_state}→{to_state} not allowed (D-081)")


# --- D-082 inventory contract ------------------------------------------------

RESERVED = "reserved"
RELEASED = "released"
INSUFFICIENT_STOCK = "insufficient_stock"


class InventoryStore:
    """Provider-neutral inventory boundary (D-082).

    Implementations: `oms_engine.PgInventory` (live, row-lock) and
    `oms_engine.JsonInventory` (offline parity). This base class only
    fixes the contract: reserve/release are atomic and durable;
    over-sell returns `insufficient_stock`, never a partial
    reservation.
    """

    def reserve(self, stock_key: str, quantity: int, order_ref: Dict):
        raise NotImplementedError

    def release(self, stock_key: str, quantity: int, order_ref: Dict):
        raise NotImplementedError

    def available(self, stock_key: str) -> int:
        raise NotImplementedError


def fulfillment_ttl_expired_reason() -> str:
    """D-084 fixed terminal reason — the worker never invents facts."""
    return "fulfillment_ttl_expired"

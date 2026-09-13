"""Identifier rules and conceptual mapping-registry / event-store
operations — D-014 / D-015 / D-017 / D-026 / D-027 / D-046.

Pure logic only; persistence is in the PostgreSQL schema (schema.sql).
AI never issues any identifier (D-017).
"""

import re
import uuid
from datetime import datetime, timezone
from typing import Optional

try:                       # package mode (local.canonical.identifiers)
    from . import vocab
except ImportError:        # flat mode (tests.py / scripts)
    import vocab

# --- Identifier formats (approved; never issued by AI) ------------------

PRODUCT_ID_RE = re.compile(r"^P[0-9]{5}$")
SKU_RE = re.compile(r"^P[0-9]{5}(?:-[A-Z0-9]{1,4})*$")  # P00001[-CC][-SS]
UUID4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


def is_valid_product_id(pid: str) -> bool:
    """Product ID: exactly P + five digits (D-014)."""
    return bool(PRODUCT_ID_RE.match(pid or ""))


def is_valid_variant_id(vid: str) -> bool:
    """Variant ID: canonical lowercase hyphenated UUIDv4 (D-017)."""
    return bool(UUID4_RE.match(vid or ""))


def new_variant_id() -> str:
    """Variant IDs are created by approved deterministic tooling only."""
    return str(uuid.uuid4())


def is_valid_sku(sku: str) -> bool:
    """SKU: D-014 format — Product ID + active-axis D-032 codes.

    Every axis segment must be an APPROVED D-032 code (color or any
    family's size code). This is what keeps historical-format examples
    like `P00001-BLK-M` (BLK is not the approved code for مشکی) from
    passing: format alone is not enough.
    """
    if not SKU_RE.match(sku or ""):
        return False
    parts = sku.split("-")
    if len(parts) > 3:            # product + at most 2 axis codes
        return False
    approved = approved_axis_codes()
    return all(seg in approved for seg in parts[1:])


def approved_axis_codes() -> set:
    """All approved D-032 codes (colors + all size families)."""
    codes = {c for _, c in vocab.COLOR_TERMS}
    for terms in vocab.SIZE_TERMS.values():
        codes |= {c for _, c in terms}
    return codes


# --- Provenance (D-026): five source types, append-only -----------------

SOURCE_TYPES = (
    "HUMAN_ENTERED",
    "SYSTEM_GENERATED",
    "AI_GENERATED",
    "IMPORTED",
    "EXTERNAL_SYNC",
)

REVIEW_STATES = ("PENDING", "HUMAN_REVIEWED", "HUMAN_VERIFIED")


def validate_provenance(rec: dict) -> list:
    errors = []
    if rec.get("source_type") not in SOURCE_TYPES:
        errors.append(f"source_type must be one of {SOURCE_TYPES}")
    if not rec.get("actor"):
        errors.append("actor is required")
    if rec.get("review_state") not in REVIEW_STATES:
        errors.append(f"review_state must be one of {REVIEW_STATES}")
    return errors


def provenance_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --- Event store (D-027) -------------------------------------------------

EVENT_STATUSES = (
    "received", "processing", "succeeded", "failed", "skipped_duplicate",
)
TERMINAL_EVENT_STATUSES = ("succeeded", "skipped_duplicate")


def classify_event_repeat(
    existing_status: str,
    existing_payload_hash: str,
    incoming_payload_hash: str,
) -> str:
    """Deterministic D-027 repeat classification.

    - identical repeat of a terminal event → skipped_duplicate
    - same key, different payload → integrity error (human review)
    - non-terminal existing event → retryable (same event ID)
    """
    if existing_status in TERMINAL_EVENT_STATUSES:
        if existing_payload_hash == incoming_payload_hash:
            return "skipped_duplicate"
        return "integrity_error"  # conflicting duplicate → human review
    return "retry"  # received/processing/failed: retryable under same ID


# --- Mapping registry (D-046) -------------------------------------------

REGISTRY_ENTRY_TYPES = (
    "product", "variation", "category", "color_term", "size_term",
    "media_reference",
)
REGISTRY_STATUSES = ("active", "stale", "orphaned")


def classify_registry_hit(
    active_entry_exists: bool,
    deterministic_lookup_found: bool,
) -> str:
    """Second-guard classification before any create (D-046 §2.6).

    - no active entry + lookup miss → normal pre-create path
    - active entry + lookup hit → consistent (idempotent no-op path)
    - lookup hit WITHOUT an active entry → duplicate-resource conflict
      (never silent adoption)
    - active entry but lookup miss → stale candidate (re-link = human
      review)
    """
    if active_entry_exists and deterministic_lookup_found:
        return "consistent"
    if active_entry_exists and not deterministic_lookup_found:
        return "stale"
    if not active_entry_exists and deterministic_lookup_found:
        return "duplicate_resource_conflict"
    return "missing"  # normal pre-create path


def is_valid_mapping_entry(entry_type: str, status: str) -> bool:
    return (
        entry_type in REGISTRY_ENTRY_TYPES and status in REGISTRY_STATUSES
    )


# --- Vocabulary resolution (D-019/D-032): exact matching only -----------

def resolve_color(display_value: str) -> Optional[str]:
    """Exact-match color display value → D-032 code. No fuzzy matching."""
    for term, code in vocab.COLOR_TERMS:
        if display_value == term:
            return code
    return None


def resolve_size(family_key: str, display_value: str) -> Optional[str]:
    """Exact-match (family, size term) → D-032 code, family-scoped.

    Numeric 42 and Pants Waist 42 are different terms in different
    families even though their codes are textually identical (D-020).
    """
    if family_key not in vocab.SIZE_TERMS:
        return None
    for term, code in vocab.SIZE_TERMS[family_key]:
        if display_value == term:
            return code
    return None

"""Canonical price resolution — D-024 / D-025, verbatim.

Precedence (D-024 rule 4; D-048 Option A materializes exactly this):

    valid variant sale
    → valid product sale
    → variant override
    → product list price

This module never mutates canonical inputs and never invents a price.
"""

from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass(frozen=True)
class PriceInputs:
    """Canonical price inputs (numeric Toman integers, D-010/RULES §11).

    None means NOT_PROVIDED. Sale validity end is inclusive: a sale is
    valid when valid_until is None (no expiry) or valid_until >= today.
    """

    list_price: Optional[int] = None          # product list price
    variant_override: Optional[int] = None    # variant price override
    product_sale: Optional[int] = None        # product-level sale price
    product_sale_until: Optional[date] = None
    variant_sale: Optional[int] = None        # variant-level sale price
    variant_sale_until: Optional[date] = None


@dataclass(frozen=True)
class PriceResolution:
    """The deterministic D-024 rule-4 outcome for one variant/simple product."""

    effective: Optional[int]      # resolved selling price (None = unresolved)
    source: str                   # which precedence tier supplied it
    unresolved_reason: Optional[str] = None


def _sale_valid(sale: Optional[int], until: Optional[date], today: date) -> bool:
    if sale is None:
        return False
    return until is None or until >= today


def resolve_effective_price(p: PriceInputs, today: date) -> PriceResolution:
    """Resolve the effective price per D-024 rule 4 exactly.

    Validation (D-038 pre-write rules) is separate — see validate().
    """
    # 1. valid variant sale
    if _sale_valid(p.variant_sale, p.variant_sale_until, today):
        return PriceResolution(p.variant_sale, "variant_sale")
    # 2. valid product sale — applies to the variant's applicable base
    #    (override if set, else list price) per D-024 rule 4.
    if _sale_valid(p.product_sale, p.product_sale_until, today):
        base = p.variant_override if p.variant_override is not None else p.list_price
        if base is None:
            return PriceResolution(
                None, "unresolved",
                "valid product sale exists but no applicable base price",
            )
        return PriceResolution(p.product_sale, "product_sale")
    # 3. variant override
    if p.variant_override is not None:
        return PriceResolution(p.variant_override, "variant_override")
    # 4. product list price
    if p.list_price is not None:
        return PriceResolution(p.list_price, "list_price")
    return PriceResolution(None, "unresolved", "no base price (list/override)")


def validate_price(p: PriceInputs, today: date) -> list:
    """D-038/D-024/D-025 pre-write validation. Returns a list of error strings.

    - numeric integers only (enforced by typing + explicit check here)
    - sale < applicable base; sale >= base rejected, never clamped
    - zero/negative prices invalid
    - expired sales ignored (not errors)
    - missing base price = unresolved (surfaced, never guessed)
    """
    errors = []

    for name, v in (
        ("list_price", p.list_price),
        ("variant_override", p.variant_override),
        ("product_sale", p.product_sale),
        ("variant_sale", p.variant_sale),
    ):
        if v is not None and (not isinstance(v, int) or isinstance(v, bool) or v <= 0):
            errors.append(f"{name}: must be a positive integer (got {v!r})")

    # Sale >= applicable base is invalid (D-025).
    for sale_name, sale, base_name, base in (
        ("product_sale", p.product_sale, "list_price", p.list_price),
        (
            "variant_sale",
            p.variant_sale,
            "applicable base (override else list)",
            p.variant_override if p.variant_override is not None else p.list_price,
        ),
    ):
        if sale is not None and base is not None and sale >= base:
            errors.append(f"{sale_name}: sale price must be < {base_name}")

    # Unresolved effective price (e.g. missing list price with no
    # override) is surfaced, never guessed (D-024 rule 5, D-021).
    r = resolve_effective_price(p, today)
    if r.effective is None:
        errors.append(f"effective price unresolved: {r.unresolved_reason}")
    elif r.effective <= 0:
        errors.append(f"effective price must be > 0 (got {r.effective})")

    return errors


# --- D-048 Option A: Woo display-field projection -----------------------

def project_to_woo(p: PriceInputs, today: date) -> dict:
    """Materialize the canonical resolution into the Woo display fields.

    D-048 Option A: approved tooling computes the canonical resolution
    and writes it into the fields Woo actually displays, at every
    affected change. Base/list and override canonical inputs are NEVER
    mutated. Woo's native fallback cannot express D-024 precedence
    (product sale does not cascade onto overridden variations), so the
    projection sets variation-level display fields explicitly.
    """
    r = resolve_effective_price(p, today)

    if r.effective is None:
        # Unresolved: nothing is written (never guessed, D-024 rule 5).
        return {
            "regular_price": None,
            "sale_price": None,
            "resolved": False,
            "source": r.source,
            "unresolved_reason": r.unresolved_reason,
        }

    if r.source == "variant_sale":
        return {
            "regular_price": str(
                p.variant_override if p.variant_override is not None else p.list_price
            ),
            "sale_price": str(p.variant_sale),
            "resolved": True,
            "source": r.source,
        }
    if r.source == "product_sale":
        # The product-level sale, materialized on the variation display
        # fields so Woo shows it despite its non-cascading fallback.
        return {
            "regular_price": str(r.effective),
            "sale_price": None,
            "resolved": True,
            "source": r.source,
        }
    # variant_override or list_price: plain displayed price.
    return {
        "regular_price": str(r.effective),
        "sale_price": None,
        "resolved": True,
        "source": r.source,
    }

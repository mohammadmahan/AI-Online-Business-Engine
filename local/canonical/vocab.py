"""Registry v1 seed data — OWNER-APPROVED values only (D-031 / D-032).

This module is the single source of truth for the local vocabulary
seed. It contains EXACTLY the values approved by the human owner in
Phase 2.5 Batches 1–2:

- Categories: 2 primaries + 12 women's + 8 men's leaves (D-031).
- Colors: 25 canonical Persian terms with D-032 O/I/L-safe SKU codes.
- Size families: alpha / numeric / pants_waist with D-032 codes.

Nothing here may be added, renamed, or reorganized without a new
explicit owner decision (D-031). No aliases, no equivalence links,
no shoe family. AI never creates vocabulary (D-019).
"""

# --- Categories (D-031, verbatim) -------------------------------------

PRIMARY_CATEGORIES = ("پوشاک زنانه", "پوشاک مردانه")

WOMENS_LEAVES = (
    "مانتو", "شومیز", "بلوز و تاپ", "تیشرت", "پیراهن", "شلوار",
    "دامن", "ست و لباس دو تکه", "هودی و سویشرت", "ژاکت و بافت",
    "کت و جلیقه", "لباس مجلسی",
)

MENS_LEAVES = (
    "تیشرت", "پیراهن", "پولوشرت", "شلوار", "شلوارک", "هودی و سویشرت",
    "ژاکت و بافت", "کت و جلیقه",
)

# (primary, leaf) pairs — duplicate leaf names are DISTINCT terms
# scoped to their primary (D-031; D-033 دسته‌بندی اصلی + زیردسته).
CATEGORY_PAIRS = tuple(
    ("پوشاک زنانه", leaf) for leaf in WOMENS_LEAVES
) + tuple(
    ("پوشاک مردانه", leaf) for leaf in MENS_LEAVES
)

# --- Colors (D-031 terms + D-032 codes, verbatim incl. the
# --- owner-corrected O/I/L-safe BK / BU / YW) --------------------------

COLOR_TERMS = (
    ("مشکی", "BK"), ("سفید", "WHT"), ("طوسی", "GRY"), ("ذغالی", "CHR"),
    ("طوسی روشن", "GY1"), ("کرم", "CRM"), ("بژ", "BEG"),
    ("قهوه‌ای", "BRN"), ("نسکافه‌ای", "NCF"), ("سرمه‌ای", "NVY"),
    ("آبی", "BU"), ("آبی روشن", "BU1"), ("آبی نفتی", "PTB"),
    ("سبز", "GRN"), ("سبز زیتونی", "VGR"), ("سبز تیره", "DGN"),
    ("قرمز", "RED"), ("زرشکی", "BRG"), ("صورتی", "PNK"),
    ("صورتی روشن", "PK1"), ("بنفش", "PRP"), ("نارنجی", "RNG"),
    ("زرد", "YW"), ("خاکی", "KHK"), ("شتری", "CAM"),
)

# --- Sizes (D-031 terms + D-032 family-scoped codes) -------------------

SIZE_FAMILIES = (
    ("alpha", "حروفی"),
    ("numeric", "عددی"),
    ("pants_waist", "کمر"),
)

SIZE_TERMS = {
    "alpha": (
        ("XS", "XS"), ("S", "S"), ("M", "M"), ("L", "LG"),
        ("XL", "XG"), ("XXL", "XXG"), ("3XL", "3XG"), ("4XL", "4XG"),
    ),
    "numeric": tuple((str(n), str(n)) for n in range(34, 56, 2)),
    "pants_waist": tuple((str(n), str(n)) for n in range(28, 46, 2)),
}

# Human-readable family display names (D-033 خانواده سایز values map
# through these; see excel.py).
FAMILY_LABELS = dict(SIZE_FAMILIES)

# --- Tracked code conflicts (owner clarification required) -------------
#
# D-030 rule 1: size codes must never contain O, I, or L in any
# position ("no exception is created"). The owner-approved D-032
# mapping L → LG contains the letter L, so the concrete approved
# record and the governance rule contradict each other for exactly
# this one code. Per the SAFETY-STOP rule this implementation does
# NOT silently resolve it: the code is represented here exactly as
# owner-approved (D-032 is the authoritative record of approved
# values) but the database seed gate refuses to insert it until the
# owner either amends D-030's wording (recorded owner exception) or
# approves a replacement code. Nothing is invented here.
CODE_CONFLICTS = {
    ("alpha", "L", "LG"):
        "D-030 rule 1 forbids 'L' in size codes; D-032 (owner-approved "
        "2026-09-12) maps L → LG. Owner clarification required: amend "
        "D-030 with a recorded exception OR approve an L-free "
        "replacement code. Blocked at the DB seed gate meanwhile.",
}


def blocked_seed_terms():
    """Approved terms whose D-032 code fails the D-030 gate.

    Returns a tuple of (family_key, display_fa, code, reason).
    """
    out = []
    for (family, term, code), reason in CODE_CONFLICTS.items():
        if not code_is_oil_safe(code):
            out.append((family, term, code, reason))
    return tuple(out)


# --- Seed invariants (verified by tests / seed_check) ------------------

EXPECTED_COUNTS = {
    "primary_categories": 2,
    "category_pairs": 20,   # 12 women's + 8 men's
    "colors": 25,
    "size_families": 3,
    "size_terms": 8 + 11 + 9,
}


def code_is_oil_safe(code: str) -> bool:
    """D-030 / D-014 rule 7: uppercase Latin ASCII, no O, I, or L."""
    if not code or not all(c.isascii() and c.isalnum() for c in code):
        return False
    return code == code.upper() and not any(c in "OIL" for c in code)

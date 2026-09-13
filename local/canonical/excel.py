"""D-033 workbook validation (semantic layer).

Validates parsed `product-master.xlsx` rows against the approved
contract: 28 product columns + 10 variant columns, exact controlled
vocabularies, D-024/D-025 price rules, D-014/D-017 identifier rules,
D-021 required-field policy, and D-028 duplicate/consistency checks.

Missing-value semantics (D-028): blank = NOT_PROVIDED;
explicit `نامشخص` = UNKNOWN; invalid = rejected. Never silently
transformed into one another.
"""

from datetime import date, datetime
from typing import Optional

try:                       # package mode (local.canonical.excel)
    from . import identifiers as ident
    from . import prices as pricing
    from . import vocab
except ImportError:        # flat mode (tests.py / scripts)
    import identifiers as ident
    import prices as pricing
    import vocab

UNKNOWN_TOKEN = "نامشخص"          # explicit UNKNOWN (D-028/D-033)
PRODUCT_STATUS_MAP = {            # exact canonical mapping (D-033)
    "پیش‌نویس": "draft",
    "فعال": "active",
    "بایگانی": "archived",
}
PUBLICATION_STATUS_MAP = {
    "منتشرنشده": "unpublished",
    "در بررسی": "in_review",
    "منتشرشده": "published",
    "برداشته‌شده": "withdrawn",
}
FAMILY_TOKEN_MAP = {label: key for key, label in vocab.SIZE_FAMILIES}

PRODUCT_COLUMNS = (
    "شناسه محصول", "نام محصول", "نام انگلیسی", "دسته‌بندی اصلی",
    "زیردسته", "برند", "جنس", "طرح", "مدل", "فصل", "کاربرد",
    "نوع یقه", "نوع آستین", "قد لباس", "نوع بسته‌شدن", "نوع فیت",
    "توضیح کوتاه", "توضیحات", "عنوان سئو", "توضیح سئو", "پیوند سئو",
    "قیمت پایه (تومان)", "قیمت فروش ویژه (تومان)",
    "تاریخ پایان فروش ویژه", "تصاویر", "وضعیت محصول", "وضعیت انتشار",
    "تاریخ ایجاد",
)
VARIANT_COLUMNS = (
    "شناسه تنوع", "شناسه محصول", "کد کالا (SKU)", "رنگ",
    "خانواده سایز", "سایز", "قیمت تنوع (تومان)",
    "قیمت فروش ویژه تنوع (تومان)", "تاریخ پایان فروش ویژه تنوع",
    "وضعیت تنوع",
)


def _blank(v) -> bool:
    return v is None or (isinstance(v, str) and v.strip() == "")


def _text(v):
    if _blank(v):
        return None
    s = str(v).strip()
    return "UNKNOWN" if s == UNKNOWN_TOKEN else s


def _int_toman(v) -> Optional[int]:
    """Numeric Toman integers only; formatted strings rejected (D-010)."""
    if _blank(v):
        return None
    if isinstance(v, bool):
        raise ValueError("boolean is not a price")
    if isinstance(v, int):
        return v
    if isinstance(v, float) and v.is_integer():
        return int(v)
    if isinstance(v, str):
        s = v.strip()
        if not s.isdigit():          # rejects '590,000' / '590,000 تومان'
            raise ValueError(f"formatted/non-numeric price rejected: {v!r}")
        return int(s)
    raise ValueError(f"non-numeric price rejected: {v!r}")


def _date(v) -> Optional[date]:
    if _blank(v):
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v).strip())


def _cell_or_none(v):
    return None if _blank(v) else str(v).strip()


class RowError:
    def __init__(self, sheet: str, row_index: int, code: str, message: str):
        self.sheet, self.row_index, self.code, self.message = (
            sheet, row_index, code, message)

    def __repr__(self):
        return (f"[{self.sheet}#{self.row_index}] {self.code}: "
                f"{self.message}")


class ValidatedWorkbook:
    """Deterministic dry-run result: errors + normalized records.

    Construction never writes anything (dry-run per D-028); promotion
    is a separate explicit human action.
    """

    def __init__(self):
        self.errors = []
        self.products = []
        self.variants = []

    @property
    def ok(self) -> bool:
        return not self.errors

    def err(self, sheet, idx, code, msg):
        self.errors.append(RowError(sheet, idx, code, msg))


def validate_workbook(product_rows, variant_rows, today: date,
                      existing=None) -> ValidatedWorkbook:
    """Validate parsed sheets. `existing` = identifiers already stored.

    product_rows/variant_rows: list of dicts keyed by the D-033 Persian
    column names. Duplicate/consistency checks per D-028 §12.
    """
    wb = ValidatedWorkbook()
    existing = existing or {}
    seen_products, seen_variants, seen_skus = {}, {}, {}
    seen_combos = set()  # (product_id, color_code, size_code) active combos
    products_by_id = {}

    for i, row in enumerate(product_rows, start=2):  # header = row 1
        pid = _cell_or_none(row.get("شناسه محصول"))
        if not ident.is_valid_product_id(pid or ""):
            wb.err("محصولات", i, "INVALID_PRODUCT_ID",
                   f"شناسه محصول {pid!r} is not P+5 digits")
            continue
        name = _text(row.get("نام محصول"))
        if not name or name == "UNKNOWN":
            wb.err("محصولات", i, "MISSING_REQUIRED",
                   "نام محصول is required")
            continue
        if pid in seen_products or pid in existing.get("product_ids", ()):
            wb.err("محصولات", i, "DUPLICATE_PRODUCT_ID",
                   f"{pid} appears more than once")
            continue

        primary = _cell_or_none(row.get("دسته‌بندی اصلی"))
        leaf = _cell_or_none(row.get("زیردسته"))
        if primary not in vocab.PRIMARY_CATEGORIES:
            wb.err("محصولات", i, "UNKNOWN_CATEGORY",
                   f"primary category {primary!r} is not approved")
            continue
        if (primary, leaf) not in vocab.CATEGORY_PAIRS:
            wb.err("محصولات", i, "UNKNOWN_CATEGORY",
                   f"leaf {leaf!r} is not approved under {primary!r} "
                   "(primary-scoped; wrong-primary leaf is INVALID)")

        try:
            list_price = _int_toman(row.get("قیمت پایه (تومان)"))
            product_sale = _int_toman(row.get("قیمت فروش ویژه (تومان)"))
        except ValueError as e:
            wb.err("محصولات", i, "INVALID_PRICE", str(e))
            continue
        p = pricing.PriceInputs(
            list_price=list_price,
            product_sale=product_sale,
            product_sale_until=_date(row.get("تاریخ پایان فروش ویژه")),
        )
        # Product-level check (variants validate their own full inputs).
        if product_sale is not None and list_price is None:
            wb.err("محصولات", i, "INVALID_PRICE",
                   "sale price requires قیمت پایه")
        for e in pricing.validate_price(p, today):
            wb.err("محصولات", i, "INVALID_PRICE", e)

        status = PRODUCT_STATUS_MAP.get(
            _cell_or_none(row.get("وضعیت محصول")) or "")
        if status is None:
            wb.err("محصولات", i, "INVALID_STATUS",
                   f"وضعیت محصول {_cell_or_none(row.get('وضعیت محصول'))!r}")
            continue
        pub = PUBLICATION_STATUS_MAP.get(
            _cell_or_none(row.get("وضعیت انتشار")) or "")
        if pub is None:
            wb.err("محصولات", i, "INVALID_STATUS",
                   f"وضعیت انتشار {_cell_or_none(row.get('وضعیت انتشار'))!r}")
            continue
        try:
            created = _date(row.get("تاریخ ایجاد"))
        except ValueError:
            wb.err("محصولات", i, "INVALID_DATE", "تاریخ ایجاد invalid")
            continue
        if created is None:
            wb.err("محصولات", i, "MISSING_REQUIRED",
                   "تاریخ ایجاد is required (D-021)")
            continue

        raw_media = _cell_or_none(row.get("تصاویر")) or ""
        rec = {
            "product_id": pid,
            "name": name,
            "name_en": _text(row.get("نام انگلیسی")),
            "primary_category": primary,
            "leaf_category": leaf,
            "attributes": {k: _text(row.get(k)) for k in (
                "برند", "جنس", "طرح", "مدل", "فصل", "کاربرد",
                "نوع یقه", "نوع آستین", "قد لباس", "نوع بسته‌شدن",
                "نوع فیت")},
            "short_description": _text(row.get("توضیح کوتاه")),
            "description": _text(row.get("توضیحات")),
            "seo_title": _text(row.get("عنوان سئو")),
            "seo_description": _text(row.get("توضیح سئو")),
            # SEO slug language gate OPEN (D-016.M): stored verbatim,
            # no normalization invented.
            "seo_slug": _cell_or_none(row.get("پیوند سئو")),
            "list_price": list_price,
            "product_sale": product_sale,
            "product_sale_until": p.product_sale_until,
            "media_refs": [m for m in
                           (x.strip() for x in raw_media.split("|"))
                           if m],
            "status": status,
            "publication_status": pub,
            "created_date": created,
        }
        if status == "active" and pub == "published" and not rec["media_refs"]:
            wb.err("محصولات", i, "PUBLICATION_MINIMUM",
                   "تصاویر: ≥1 media reference required to publish (D-021)")
        seen_products[pid] = i
        products_by_id[pid] = rec
        wb.products.append(rec)

    for i, row in enumerate(variant_rows, start=2):
        vid = _cell_or_none(row.get("شناسه تنوع"))
        if vid is not None and not ident.is_valid_variant_id(vid):
            wb.err("تنوع‌ها", i, "INVALID_VARIANT_ID",
                   f"شناسه تنوع {vid!r} is not canonical UUIDv4")
            continue
        if vid is not None and (vid in seen_variants
                                or vid in existing.get("variant_ids", ())):
            wb.err("تنوع‌ها", i, "DUPLICATE_VARIANT_ID",
                   f"Variant ID {vid} appears more than once")
            continue
        pid = _cell_or_none(row.get("شناسه محصول"))
        if pid not in seen_products:
            wb.err("تنوع‌ها", i, "ORPHAN_VARIANT",
                   f"شناسه محصول {pid!r} has no محصولات row in this "
                   "workbook (never silently merged)")
            continue

        color_raw = _cell_or_none(row.get("رنگ"))
        family_raw = _cell_or_none(row.get("خانواده سایز"))
        size_raw = _cell_or_none(row.get("سایز"))
        color_code = None
        size_code = None
        family_key = None
        active_axes = []

        if color_raw is not None:
            color_code = ident.resolve_color(color_raw)
            if color_code is None:
                wb.err("تنوع‌ها", i, "UNKNOWN_VOCABULARY",
                       f"رنگ {color_raw!r} is not an approved color "
                       "(never auto-created; D-019)")
                continue
            active_axes.append("color")

        if family_raw is not None or size_raw is not None:
            family_key = FAMILY_TOKEN_MAP.get(family_raw or "")
            if family_key is None:
                wb.err("تنوع‌ها", i, "UNKNOWN_SIZE_FAMILY",
                       f"خانواده سایز {family_raw!r} is not approved")
                continue
            size_code = ident.resolve_size(family_key, size_raw or "")
            if size_code is None:
                # Distinguish: term exists in another family (family
                # mismatch — INVALID) vs term unknown everywhere
                # (UNKNOWN_VOCABULARY — never auto-created, D-019).
                in_other = any(
                    size_raw == t
                    for fam, terms in vocab.SIZE_TERMS.items()
                    if fam != family_key for t, _ in terms)
                if in_other:
                    wb.err("تنوع‌ها", i, "SIZE_FAMILY_MISMATCH",
                           f"سایز {size_raw!r} does not belong to family "
                           f"{family_key!r} (family-scoped; D-020)")
                else:
                    wb.err("تنوع‌ها", i, "UNKNOWN_VOCABULARY",
                           f"سایز {size_raw!r} is not approved in family "
                           f"{family_key} (family-scoped; never converted)")
                continue
            active_axes.append("size")

        sku = _cell_or_none(row.get("کد کالا (SKU)"))
        if sku is not None:
            if not ident.is_valid_sku(sku):
                wb.err("تنوع‌ها", i, "INVALID_SKU",
                       f"SKU {sku!r} violates D-014 format or uses "
                       "non-approved codes")
                continue
            expected_axes = [c for c in (color_code, size_code) if c]
            expected = pid + "".join("-" + c for c in expected_axes)
            if sku != expected:
                wb.err("تنوع‌ها", i, "SKU_MISMATCH",
                       f"SKU {sku!r} does not match active axes "
                       f"(expected {expected!r}; D-014 rule 6)")
                continue
            if sku in seen_skus or sku in existing.get("skus", ()):
                wb.err("تنوع‌ها", i, "DUPLICATE_SKU",
                       f"SKU {sku} already exists")
                continue

        combo = (pid, color_code, size_code)
        if combo in seen_combos:
            wb.err("تنوع‌ها", i, "DUPLICATE_VARIANT_COMBINATION",
                   f"active-axis combination {combo} is duplicated "
                   "(D-014 rule 11; never merged)")
            continue

        try:
            override = _int_toman(row.get("قیمت تنوع (تومان)"))
            vsale = _int_toman(row.get("قیمت فروش ویژه تنوع (تومان)"))
        except ValueError as e:
            wb.err("تنوع‌ها", i, "INVALID_PRICE", str(e))
            continue
        prod = products_by_id[pid]
        vp = pricing.PriceInputs(
            list_price=prod["list_price"],
            variant_override=override,
            product_sale=prod["product_sale"],
            product_sale_until=prod["product_sale_until"],
            variant_sale=vsale,
            variant_sale_until=_date(
                row.get("تاریخ پایان فروش ویژه تنوع")),
        )
        for e in pricing.validate_price(vp, today):
            wb.err("تنوع‌ها", i, "INVALID_PRICE", e)

        vstatus = PRODUCT_STATUS_MAP.get(
            _cell_or_none(row.get("وضعیت تنوع")) or "")
        if vstatus is None:
            wb.err("تنوع‌ها", i, "INVALID_STATUS",
                   f"وضعیت تنوع {_cell_or_none(row.get('وضعیت تنوع'))!r}")
            continue

        seen_combos.add(combo)
        seen_variants[vid] = i
        if sku:
            seen_skus[sku] = i
        wb.variants.append({
            "variant_id": vid,        # None → tooling generates (D-033)
            "product_id": pid,
            "sku": sku,               # None → tooling derives
            "color_code": color_code,
            "size_family": family_key,
            "size_code": size_code,
            "price_override": override,
            "variant_sale": vsale,
            "variant_sale_until": vp.variant_sale_until,
            "status": vstatus,
            "active_axes": active_axes,
        })

    return wb

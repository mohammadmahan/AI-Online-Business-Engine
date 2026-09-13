#!/usr/bin/env python3
"""Generate the local Excel test fixture workbook per D-033:
`product-master.xlsx` with sheets محصولات / تنوع‌ها / راهنما / گزینه‌ها,
containing the full D-028 test matrix (§13). Fictional data only;
approved vocabulary only.

Writes local/fixtures/product-master.xlsx (gitignored volume area is
NOT used — fixtures are tracked) and a JSON summary of the expected
validation outcomes per row-group for the test harness.

Uses openpyxl if available; otherwise falls back to writing the
fixture as JSON (local/fixtures/product-master.json) so the semantic
test matrix is still executable without the dependency — the .xlsx
rendering is produced once openpyxl is installed.
"""
import json
import os
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE)))
sys.path.insert(0, os.path.dirname(HERE))

from canonical import excel as xl  # noqa: E402
from canonical import vocab  # noqa: E402

FIXTURE_DIR = os.path.join(os.path.dirname(HERE), "fixtures")
TODAY = date(2026, 9, 13)

P_COLS = list(xl.PRODUCT_COLUMNS)
V_COLS = list(xl.VARIANT_COLUMNS)


def p_row(**kw):
    row = {c: None for c in P_COLS}
    row.update(kw)
    return row


def v_row(**kw):
    row = {c: None for c in V_COLS}
    row.update(kw)
    return row


def build_product_rows():
    rows = []
    # --- valid simple product (zero active axes) ------------------------
    rows.append(p_row(**{
        "شناسه محصول": "P90001", "نام محصول": "شال تستی ساده",
        "دسته‌بندی اصلی": "پوشاک زنانه", "زیردسته": "شومیز",
        "قیمت پایه (تومان)": 150000,
        "تصاویر": "https://media.local/p90001-1.jpg",
        "وضعیت محصول": "فعال", "وضعیت انتشار": "منتشرنشده",
        "تاریخ ایجاد": TODAY,
    }))
    # --- valid variable product (color + size) --------------------------
    rows.append(p_row(**{
        "شناسه محصول": "P90002", "نام محصول": "تیشرت تستی",
        "دسته‌بندی اصلی": "پوشاک مردانه", "زیردسته": "تیشرت",
        "قیمت پایه (تومان)": 300000,
        "قیمت فروش ویژه (تومان)": 250000,
        "تاریخ پایان فروش ویژه": TODAY + timedelta(days=30),
        "تصاویر": "https://media.local/p90002-1.jpg|"
                  "https://media.local/p90002-2.jpg",
        "وضعیت محصول": "فعال", "وضعیت انتشار": "در بررسی",
        "تاریخ ایجاد": TODAY,
    }))
    # --- invalid category (leaf under wrong primary) ---------------------
    rows.append(p_row(**{
        "شناسه محصول": "P90003", "نام محصول": "دامن تستی",
        "دسته‌بندی اصلی": "پوشاک مردانه",   # wrong primary for دامن
        "زیردسته": "دامن",
        "قیمت پایه (تومان)": 200000, "تصاویر": "https://media.local/x.jpg",
        "وضعیت محصول": "فعال", "وضعیت انتشار": "منتشرنشده",
        "تاریخ ایجاد": TODAY,
    }))
    # --- invalid price (sale >= base) -------------------------------------
    rows.append(p_row(**{
        "شناسه محصول": "P90004", "نام محصول": "پیراهن تستی",
        "دسته‌بندی اصلی": "پوشاک مردانه", "زیردسته": "پیراهن",
        "قیمت پایه (تومان)": 500000, "قیمت فروش ویژه (تومان)": 500000,
        "تصاویر": "https://media.local/x.jpg",
        "وضعیت محصول": "فعال", "وضعیت انتشار": "منتشرنشده",
        "تاریخ ایجاد": TODAY,
    }))
    # --- duplicate Product ID (same as P90002) ----------------------------
    rows.append(p_row(**{
        "شناسه محصول": "P90002", "نام محصول": "تیشرت تکراری",
        "دسته‌بندی اصلی": "پوشاک مردانه", "زیردسته": "تیشرت",
        "قیمت پایه (تومان)": 300000, "تصاویر": "https://media.local/x.jpg",
        "وضعیت محصول": "فعال", "وضعیت انتشار": "منتشرنشده",
        "تاریخ ایجاد": TODAY,
    }))
    # --- UNKNOWN optional field (نام انگلیسی = نامشخص) — NOT an error -----
    rows.append(p_row(**{
        "شناسه محصول": "P90005", "نام محصول": "هودی تستی",
        "نام انگلیسی": "نامشخص",
        "دسته‌بندی اصلی": "پوشاک زنانه", "زیردسته": "هودی و سویشرت",
        "قیمت پایه (تومان)": 850000, "تصاویر": "https://media.local/x.jpg",
        "وضعیت محصول": "فعال", "وضعیت انتشار": "منتشرنشده",
        "تاریخ ایجاد": TODAY,
    }))
    # --- NOT_PROVIDED (descriptions blank; valid — D-021 non-blockers) ----
    rows.append(p_row(**{
        "شناسه محصول": "P90006", "نام محصول": "شلوار تستی",
        "دسته‌بندی اصلی": "پوشاک مردانه", "زیردسته": "شلوار",
        "قیمت پایه (تومان)": 650000,
        "توضیح کوتاه": None, "توضیحات": None,   # blank = NOT_PROVIDED
        "تصاویر": "https://media.local/x.jpg",
        "وضعیت محصول": "فعال", "وضعیت انتشار": "منتشرنشده",
        "تاریخ ایجاد": TODAY,
    }))
    # --- missing list price (unresolved → surfaced) ------------------------
    rows.append(p_row(**{
        "شناسه محصول": "P90007", "نام محصول": "مانتو بدون قیمت",
        "دسته‌بندی اصلی": "پوشاک زنانه", "زیردسته": "مانتو",
        "قیمت پایه (تومان)": None,
        "تصاویر": "https://media.local/x.jpg",
        "وضعیت محصول": "پیش‌نویس", "وضعیت انتشار": "منتشرنشده",
        "تاریخ ایجاد": TODAY,
    }))
    # --- formatted price string (rejected, D-010) --------------------------
    rows.append(p_row(**{
        "شناسه محصول": "P90008", "نام محصول": "بلوز فرمت‌دار",
        "دسته‌بندی اصلی": "پوشاک زنانه", "زیردسته": "شومیز",
        "قیمت پایه (تومان)": "590,000",
        "تصاویر": "https://media.local/x.jpg",
        "وضعیت محصول": "فعال", "وضعیت انتشار": "منتشرنشده",
        "تاریخ ایجاد": TODAY,
    }))
    # --- invalid Product ID format -----------------------------------------
    rows.append(p_row(**{
        "شناسه محصول": "P90", "نام محصول": "شناسه بد",
        "دسته‌بندی اصلی": "پوشاک زنانه", "زیردسته": "مانتو",
        "قیمت پایه (تومان)": 100000, "تصاویر": "https://media.local/x.jpg",
        "وضعیت محصول": "فعال", "وضعیت انتشار": "منتشرنشده",
        "تاریخ ایجاد": TODAY,
    }))
    return rows


def build_variant_rows():
    rows = []
    # valid variants for P90002 (color + size axes)
    rows.append(v_row(**{
        "شناسه محصول": "P90002", "کد کالا (SKU)": "P90002-BK-M",
        "رنگ": "مشکی", "خانواده سایز": "حروفی", "سایز": "M",
        "وضعیت تنوع": "فعال",
    }))
    rows.append(v_row(**{
        "شناسه محصول": "P90002", "کد کالا (SKU)": "P90002-WHT-XG",
        "رنگ": "سفید", "خانواده سایز": "حروفی", "سایز": "XL",
        "قیمت تنوع (تومان)": 280000,     # variant override
        "وضعیت تنوع": "فعال",
    }))
    # valid numeric-family variant with variant-level sale
    rows.append(v_row(**{
        "شناسه محصول": "P90006", "کد کالا (SKU)": "P90006-KHK-42",
        "رنگ": "خاکی", "خانواده سایز": "عددی", "سایز": "42",
        "قیمت تنوع (تومان)": 620000,
        "قیمت فروش ویژه تنوع (تومان)": 570000,
        "تاریخ پایان فروش ویژه تنوع": TODAY + timedelta(days=10),
        "وضعیت تنوع": "فعال",
    }))
    # pants-waist 44 on the waist-family product P90007: family-scoped
    # distinct terms across products (P90007 is a draft, so pricing
    # checks skip; the numeric-42 vs waist-44 distinction is preserved
    # across products, per D-020 rule 3 — one family per product).
    rows.append(v_row(**{
        "شناسه محصول": "P90007", "کد کالا (SKU)": "P90007-KHK-44",
        "رنگ": "خاکی", "خانواده سایز": "کمر", "سایز": "44",
        "وضعیت تنوع": "فعال",
    }))
    # invalid color (not approved; must NOT be auto-created)
    rows.append(v_row(**{
        "شناسه محصول": "P90002", "رنگ": "فیروزه‌ای",
        "خانواده سایز": "حروفی", "سایز": "S", "وضعیت تنوع": "فعال",
    }))
    # invalid size family
    rows.append(v_row(**{
        "شناسه محصول": "P90002", "رنگ": "مشکی",
        "خانواده سایز": "کفشی", "سایز": "42", "وضعیت تنوع": "فعال",
    }))
    # size not in selected family (alpha 42 → SIZE_FAMILY_MISMATCH)
    rows.append(v_row(**{
        "شناسه محصول": "P90002", "رنگ": "مشکی",
        "خانواده سایز": "حروفی", "سایز": "42", "وضعیت تنوع": "فعال",
    }))
    # SKU mismatch vs active axes (SKU says M but size is L → LRG per
    # D-057)
    rows.append(v_row(**{
        "شناسه محصول": "P90002", "کد کالا (SKU)": "P90002-BK-M",
        "رنگ": "مشکی", "خانواده سایز": "حروفی", "سایز": "L",
        "وضعیت تنوع": "فعال",
    }))
    # duplicate SKU (exact repeat of the first P90002-BK-M row)
    rows.append(v_row(**{
        "شناسه محصول": "P90002", "کد کالا (SKU)": "P90002-BK-M",
        "رنگ": "مشکی", "خانواده سایز": "حروفی", "سایز": "M",
        "وضعیت تنوع": "فعال",
    }))
    # duplicate active-axis combination (مشکی + M again), SKU blank
    # (tooling would derive it) → combination check fires
    rows.append(v_row(**{
        "شناسه محصول": "P90002", "رنگ": "مشکی",
        "خانواده سایز": "حروفی", "سایز": "M", "وضعیت تنوع": "فعال",
    }))
    # orphan variant (parent product row missing from this workbook)
    rows.append(v_row(**{
        "شناسه محصول": "P99999", "رنگ": "مشکی", "وضعیت تنوع": "فعال",
    }))
    # invalid SKU (GRY approved, but L is not an approved code —
    # the alpha code for L is LRG per D-057)
    rows.append(v_row(**{
        "شناسه محصول": "P90002", "کد کالا (SKU)": "P90002-GRY-L",
        "رنگ": "طوسی", "خانواده سایز": "حروفی", "سایز": "XL",
        "وضعیت تنوع": "فعال",
    }))
    # invalid variant sale (sale >= override)
    rows.append(v_row(**{
        "شناسه محصول": "P90006", "رنگ": "سرمه‌ای",
        "خانواده سایز": "عددی", "سایز": "40",
        "قیمت تنوع (تومان)": 600000,
        "قیمت فروش ویژه تنوع (تومان)": 600000,
        "وضعیت تنوع": "فعال",
    }))
    return rows


def expected_codes():
    """The deterministic outcome profile of the fixture matrix."""
    return {
        "INVALID_PRODUCT_ID": 1,       # P90
        "DUPLICATE_PRODUCT_ID": 1,     # second P90002
        "UNKNOWN_CATEGORY": 1,         # دامن under مردانه
        "INVALID_PRICE": 5,            # P90004 sale>=base; P90007
                                       # unresolved; P90008 formatted;
                                       # P90007's variant inherits no
                                       # base → also unresolved
                                       # (D-024 rule 5); variant
                                       # sale>=override on P90006
        "UNKNOWN_VOCABULARY": 1,       # فیروزه‌ای
        "UNKNOWN_SIZE_FAMILY": 1,      # کفشی
        "SIZE_FAMILY_MISMATCH": 1,     # alpha 42
        "INVALID_SKU": 1,              # P90002-GRY-L (L not a code)
        "SKU_MISMATCH": 1,             # SKU says M, size is L→LRG
        "DUPLICATE_SKU": 1,            # exact repeat of P90002-BK-M
        "DUPLICATE_VARIANT_COMBINATION": 1,
        "ORPHAN_VARIANT": 1,
    }


def main() -> int:
    os.makedirs(FIXTURE_DIR, exist_ok=True)
    product_rows = build_product_rows()
    variant_rows = build_variant_rows()

    wb = xl.validate_workbook(product_rows, variant_rows, TODAY)
    codes = {}
    for e in wb.errors:
        codes[e.code] = codes.get(e.code, 0) + 1

    print("Fixture validation profile:")
    exp = expected_codes()
    all_ok = True
    for code, want in exp.items():
        got = codes.get(code, 0)
        mark = "OK " if got == want else "FAIL"
        if got != want:
            all_ok = False
        print(f"  [{mark}] {code}: {got} (expected {want})")
    extras = {k: v for k, v in codes.items() if k not in exp}
    if extras:
        print(f"  [note] additional error codes: {extras}")

    summary = {
        "generated_for": "product-master.xlsx (D-033)",
        "sheets": ["محصولات", "تنوع‌ها", "راهنما", "گزینه‌ها"],
        "today": TODAY.isoformat(),
        "product_rows": len(product_rows),
        "variant_rows": len(variant_rows),
        "validation_errors": codes,
        "expected_profile": exp,
        "all_expected_matched": all_ok,
        "valid_products": [p["product_id"] for p in wb.products],
        "valid_variants": len(wb.variants),
    }
    with open(os.path.join(FIXTURE_DIR, "fixture-summary.json"), "w",
              encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    # JSON row source (executable without openpyxl)
    with open(os.path.join(FIXTURE_DIR, "product-master.json"), "w",
              encoding="utf-8") as f:
        json.dump({"products": product_rows, "variants": variant_rows},
                  f, ensure_ascii=False, indent=2, default=str)

    # .xlsx rendering when openpyxl exists
    try:
        from openpyxl import Workbook
    except ImportError:
        print("openpyxl not installed — wrote JSON fixture source; "
              ".xlsx rendering deferred (pip install openpyxl).")
        return 0 if all_ok else 1

    wbk = Workbook()
    ws = wbk.active
    ws.title = "محصولات"
    ws.append(P_COLS)
    for r in product_rows:
        ws.append([r[c] for c in P_COLS])
    wsv = wbk.create_sheet("تنوع‌ها")
    wsv.append(V_COLS)
    for r in variant_rows:
        wsv.append([r[c] for c in V_COLS])
    wsg = wbk.create_sheet("راهنما")
    wsg.append(["راهنمای فروشنده"])
    wsg.append(["یک محصول = یک ردیف در محصولات؛ یک تنوع = یک ردیف در تنوع‌ها."])
    wsg.append(["شناسه محصول را خودتان وارد کنید؛ شناسه تنوع را وارد نکنید."])
    wsg.append(["رنگ و سایز را از مقادیر تاییدشده برگزینید."])
    wsg.append(["قیمت‌ها عددی و به تومان است."])
    wsg.append(["خانه خالی = ارائه‌نشده؛ نامشخص = نامشخص (UNKNOWN)."])
    wsg.append(["این فایل ورودی است، نه پایگاه‌داده نهایی."])
    wso = wbk.create_sheet("گزینه‌ها")
    wso.append(["دسته‌بندی اصلی", "زیردسته", "رنگ", "کد رنگ",
                "خانواده سایز", "سایز", "کد سایز"])
    for prim, leaf in vocab.CATEGORY_PAIRS:
        wso.append([prim, leaf, None, None, None, None, None])
    for term, code in vocab.COLOR_TERMS:
        wso.append([None, None, term, code, None, None, None])
    for fam_key, fam_label in vocab.SIZE_FAMILIES:
        for term, code in vocab.SIZE_TERMS[fam_key]:
            wso.append([None, None, None, None, fam_label, term, code])
    out = os.path.join(FIXTURE_DIR, "product-master.xlsx")
    wbk.save(out)
    print(f"Wrote {out}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())

# Phase 2.5 — Business Data Configuration

Status: **Batch 1 — Approved and recorded (2026-09-12); Batch 2 —
Approved and recorded (2026-09-12); Batch 3 — Approved and recorded
(2026-09-12)**

---

## Purpose

Record the **owner-approved business data configuration** that sits on
top of the closed Phase 2 decision set (D-014–D-030, commit `4dc3fa1`):
the approved category structure, the concrete Registry v1 values, and
the approved product-attribute set.

**Every value in this document is OWNER-APPROVED configuration** —
supplied and approved by the human owner. Nothing here is
AI-generated, AI-suggested-then-defaulted, or invented: the AI's role
was limited to recording and structuring exactly what the owner
approved.

This batch is still **specification/configuration only**. No backend
code, database schema, APIs, WooCommerce integration, n8n workflows,
Instagram integration, payment/shipping integration, or production
infrastructure is started. Phase 3 remains closed.

## Relationship to the Phase 2 decisions

- **Governance unchanged:** D-019 (vocabulary governance), D-029
  (registry v1 structure), and D-030 (size-code governance) continue
  to apply verbatim. This batch *populates owner-approved values*; it
  does not alter any rule.
- **Category** is a controlled vocabulary and is now populated.
  Category is **NOT a variant-defining axis** (D-018: exactly
  {Color, Size} — unchanged).
- **Variant model unchanged** (D-018): a variant is a unique
  combination of the product's active variant-defining axes; Color +
  Size is the normal case; one axis alone applies if only it varies;
  zero axes = simple product. Inseam remains deferred. No attribute
  other than Color/Size creates variants.
- **Registry v1 unchanged in composition** (D-029): exactly
  `color`, `size`, `category`. No other attribute is promoted.
- **SKU codes are owner-approved** (Batch 2, D-032: O/I/L-safe; the
  owner corrected the initial BLK/BLU/YLW). AI must never assign or
  invent them (D-014 rule 12, D-017 rule 7); approved deterministic
  tooling may derive SKU strings from approved Product ID + approved
  codes. Product ID / Variant ID / SKU rules (D-014/D-015) remain
  unchanged.

## 1. Approved category structure

**Primary categories (2):**

1. پوشاک زنانه
2. پوشاک مردانه

**Women's subcategories (12):**

مانتو · شومیز · بلوز و تاپ · تیشرت · پیراهن · شلوار · دامن ·
ست و لباس دو تکه · هودی و سویشرت · ژاکت و بافت · کت و جلیقه ·
لباس مجلسی

**Men's subcategories (8):**

تیشرت · پیراهن · پولوشرت · شلوار · شلوارک · هودی و سویشرت ·
ژاکت و بافت · کت و جلیقه

Rules:

- These concrete category values are **OWNER-APPROVED**; the category
  portion of the Registry v1 concrete-values gate is thereby resolved.
- Do **not** add, remove, rename, merge, or reorganize categories.
- Future category changes require a new explicit owner decision
  (D-019 governance: humans create terms; variant-defining vocabulary
  rules are unaffected — category carries no SKU code).
- Note: تیشرت، پیراهن، شلوار، هودی و سویشرت، ژاکت و بافت، کت و جلیقه
  appear under both primaries; they are **separate terms per primary**
  (a category term belongs to exactly one primary), not shared terms.

## 2. Approved color vocabulary (25 terms)

The following are the owner-approved **canonical Color terms**
(Persian canonical display values):

مشکی · سفید · طوسی · ذغالی · طوسی روشن · کرم · بژ · قهوه‌ای ·
نسکافه‌ای · سرمه‌ای · آبی · آبی روشن · آبی نفتی · سبز · سبز زیتونی ·
سبز تیره · قرمز · زرشکی · صورتی · صورتی روشن · بنفش · نارنجی · زرد ·
خاکی · شتری

Rules:

- These are canonical display values. **No English labels are
  invented** (English display labels remain optional per D-029 and are
  added only if the owner later justifies them).
- **No aliases are created**; the alias registry remains empty —
  aliases are added only by a future explicit owner decision (D-019
  rule 5 governs their use). No synonyms are inferred (e.g., none for
  مشکی/سیاه or طوسی/خاکستری).
- **SKU codes (Batch 2 — OWNER-APPROVED):** one canonical code per
  color term; uppercase Latin ASCII; no O, I, or L (D-014 rule 7,
  D-030); no duplicate codes; immutable once referenced; no
  alternative codes; no additional colors.
- **Owner correction (2026-09-12):** the owner's initial proposal
  contained `BLK`, `BLU`, `YLW` — each containing the letter `L`,
  which D-014 rule 7 forbids. The owner reviewed the conflict and
  approved the O/I/L-safe replacements `BK`, `BU`, `YW`; D-014 and
  D-030 remain fully intact (no exception was created):

  | Color term | SKU code |
  | --- | --- |
  | مشکی | BK |
  | سفید | WHT |
  | طوسی | GRY |
  | ذغالی | CHR |
  | طوسی روشن | GY1 |
  | کرم | CRM |
  | بژ | BEG |
  | قهوه‌ای | BRN |
  | نسکافه‌ای | NCF |
  | سرمه‌ای | NVY |
  | آبی | BU |
  | آبی روشن | BU1 |
  | آبی نفتی | PTB |
  | سبز | GRN |
  | سبز زیتونی | VGR |
  | سبز تیره | DGN |
  | قرمز | RED |
  | زرشکی | BRG |
  | صورتی | PNK |
  | صورتی روشن | PK1 |
  | بنفش | PRP |
  | نارنجی | RNG |
  | زرد | YW |
  | خاکی | KHK |
  | شتری | CAM |

## 3. Approved size families

**A) Alpha (8 values):** XS · S · M · L · XL · XXL · 3XL · 4XL

**B) Numeric (11 values):** 34 · 36 · 38 · 40 · 42 · 44 · 46 · 48 ·
50 · 52 · 54

**C) Pants Waist (9 values):** 28 · 30 · 32 · 34 · 36 · 38 · 40 · 42 ·
44

**Shoe size is NOT included** — footwear is outside the current
initial product scope.

**Size SKU codes (Batch 2 — OWNER-APPROVED):** Numeric and Pants
Waist codes equal their canonical values; Alpha codes use a separate
O/I/L-safe canonical code with the display label unchanged (D-020
rule 4 — display stays conventional `L`, `XL`):

| Family | Approved code mapping |
| --- | --- |
| Alpha | XS→XS · S→S · M→M · L→LG · XL→XG · XXL→XXG · 3XL→3XG · 4XL→4XG |
| Numeric | 34→34 · 36→36 · 38→38 · 40→40 · 42→42 · 44→44 · 46→46 · 48→48 · 50→50 · 52→52 · 54→54 |
| Pants Waist | 28→28 · 30→30 · 32→32 · 34→34 · 36→36 · 38→38 · 40→40 · 42→42 · 44→44 |

Rules:

- These are the owner-approved **size terms** within their families
  (D-020 multi-family architecture). Family context remains
  product-level configuration; the size term belongs to the variant.
- **Size codes are family-scoped** (D-030 rule 7): Numeric 42 and
  Pants Waist 42 are **different terms in different families** even
  though their codes are textually identical. No family terms are
  merged.
- **No equivalence links** between families are created (Alpha,
  Numeric, Pants Waist, or future families); no automatic or inferred
  size conversion; cross-family conversion stays human-curated only
  (D-020 rule 7).
- Family-scoped semantics from D-020/D-030 are preserved.
- Note: `34`/`36`/`38`/`40`/`42`/`44` appear in both Numeric and
  Pants Waist; they are **distinct terms scoped to their family**
  (family-scoped namespace, D-030 rule 7) — not shared terms.

## 4. Approved product attributes

**General / product-level attributes (8):**

| Persian | English reference |
| --- | --- |
| برند | Brand |
| جنس | Material |
| رنگ | Color |
| سایز | Size |
| طرح | Pattern |
| مدل | Style |
| فصل | Season |
| کاربرد | Usage |

**Garment-specific attributes (5):**

| Persian | English reference |
| --- | --- |
| نوع یقه | Collar |
| نوع آستین | Sleeve |
| قد لباس | Length |
| نوع بسته‌شدن | Closure |
| نوع فیت | Fit |

Rules:

- **Color and Size are the variant-defining axes** (D-018 —
  unchanged). All other attributes above are **product-level
  attributes** unless a future owner decision explicitly changes
  this.
- No variants are created from Material, Pattern, Style, Season,
  Usage, Collar, Sleeve, Length, Closure, or Fit. Products differing
  only by product-level attributes are separate products (D-018
  rule 4).
- **Fit is recorded as a product-level attribute** (نوع فیت) in this
  batch. It is not promoted into Registry v1 (D-029 composition is
  unchanged); when the owner later wants consistency control over it,
  that is a separate promotion decision (D-019 governance applies).
- The English column above is a **documentation reference label for
  this configuration record** (matching the project's established
  English attribute names, e.g. MASTER_PLAN §4 and D-021/D-029), not
  invented customer-facing display labels. Storefront-facing labels
  remain Persian/RTL-first (D-002).
- This batch approves the **attribute list** only; concrete value
  lists for the non-registry attributes (material values, pattern
  values, …) are **not** approved or invented here.

## 4a. Batch 2 — SKU examples (illustrative only)

Examples document the resulting shape; **no actual products or SKUs
are created in production data** and no runtime SKU generation is
implemented:

- Two-axis product: `P00001-BK-M`, `P00001-WHT-XG`, `P00002-BRN-42`
- One-axis product (Color only): `P00003-BK`
- Simple product (zero active axes): `P00004`

The suffix uses exactly the active variant-defining axes in canonical
order Color, then Size (D-018 rule 6), with the owner-approved codes
from sections 2 and 3.

## 5. Data-entry principle

The human seller enters **human-readable values** — for example
Color: `مشکی`, Size: `XL`. The seller is never required to know or
manually enter SKU codes.

The future deterministic system may resolve:

- `مشکی` → approved Color term → approved SKU code
- `XL` → approved Size term → approved SKU code

However:

- SKU-code resolution is **not implemented** (no runtime generation;
  the codes themselves are approved — D-032);
- AI must never assign or invent SKU codes (D-014 rule 12, D-017
  rule 7);
- Product ID / Variant ID / SKU rules (D-014/D-015) remain unchanged.
- This resolution path is exactly the D-019 exact-alias/exact-term
  model plus the D-032-approved codes — no new mechanism is
  introduced. Its **physical realization** (seller enters `مشکی`/`XL`
  in the workbook; approved tooling derives the SKU) is specified in
  Batch 3, decision D-033.

## 6. AI authority (unchanged)

All Phase 2 AI restrictions are preserved; nothing is weakened.

AI **may**: propose, recommend, draft, enrich, summarize, suggest
attribute values.

AI **may NOT**: create/activate/modify/delete registry terms, assign
SKU codes, create Product IDs, create Variant IDs, execute lifecycle
transitions, publish products, execute imports, or resolve business
exceptions autonomously. (Authority matrix: `DATA_MODEL.md` §13.7.)

## 7. Gate status (after Batches 1–3)

**Closed — Batch 1 (owner approval recorded 2026-09-12):**

- Concrete **category values** (2 primaries + 12 women's + 8 men's)
  — portion of register item 3 / D-016.C.
- Concrete **color terms** (25, display values) — portion of register
  item 3 / D-016.C.
- Concrete **size terms** (Alpha/8, Numeric/11, Pants Waist/9) —
  portion of register item 15 / D-016.D.
- Approved product-attribute list (product-level set + Fit as
  product-level).

**Closed — Batch 2 (owner approval recorded 2026-09-12, incl. the
owner's O/I/L-safe code corrections; D-032):**

- **Color SKU-code mappings** — 25 owner-approved O/I/L-safe codes
  (section 2; `BK`/`BU`/`YW` per the owner correction).
- **Size SKU-code mappings** — Alpha (separate O/I/L-safe codes,
  display labels unchanged), Numeric, and Pants Waist (canonical
  value = code), family-scoped (section 3).

**Closed — Batch 3 (owner approval recorded 2026-09-12; D-033):**

- **Physical Excel sheet/column mapping** — the Product Master
  workbook contract (`product-master.xlsx`; sheets محصولات، تنوع‌ها،
  راهنما، گزینه‌ها; exact columns, types, required/optional,
  canonical value mappings, validation, import mapping, provenance)
  is specified in
  `docs/phases/phase-02-5-excel-master-template.md` and recorded as
  decision D-033. This closes the D-028 physical-mapping dependency.

**Still OPEN (explicitly not closed by Batches 1–3):**

- Color aliases and size aliases (registry remains empty; added only
  by a future explicit owner decision)
- Size equivalence mappings between families (owner-curated,
  D-020 rule 7)
- Data-entry language decision (register item 4) — Batches 1–3 add
  **no** general resolution: they record owner-approved Persian
  canonical values and the seller-enters-readable-values principle
  for these vocabularies only; the general data-entry language
  decision (descriptions, SEO, operational fields) remains open
- SEO slug language (D-016.M)
- Inventory design constraints (D-016.I)
- Phase 3+ integration decisions (register rows 5–12)
- Promotion of brand/material/pattern/style/season/usage/collar/
  sleeve/length/closure/fit into controlled vocabularies (separate
  owner decisions; Registry v1 composition unchanged per D-029)

## References

- `DECISIONS.md` — D-014, D-015, D-017, D-018, D-019, D-020, D-024,
  D-025, D-026, D-028, D-029, D-030, D-031, D-032, D-033 (all
  Approved; meanings unchanged)
- `docs/phases/phase-02-5-excel-master-template.md` — the Batch 3
  physical workbook contract (normative annex of D-033)
- `DATA_MODEL.md` — §6 (taxonomy/registry), §6.2 (size system),
  §6.4 (Excel import contract), §13 (consolidated logical model)
- `docs/phases/phase-02-product-data-system.md` — closed Phase 2
  decision set and import specification

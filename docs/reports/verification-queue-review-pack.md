# Verification Queue — Owner Review Pack

Generated: 2026-09-14T12:26:15+00:00

- Queue total: **16** items (1 decided, **15 pending your decision**)
- Data source: `local/volumes/verification/queue.json` (runtime state, gitignored)
- Decision tool: `python3 local/canonical/verification_tool.py review --index N --approve|--reject --reviewer <your-name>`

> **How to use this pack:** each item shows its TRUE queue index — pass exactly that number to `--index`. Decisions are immutable (D-026 append-only): they are recorded in place with your reviewer identity and D-026 provenance. The guidance below restates the approved decisions; when in doubt, **reject** — corrections flow through the source workbook and re-import, never through silent canonical rewrites.

## INVALID_PRICE — 4 item(s)

**Guidance (INVALID_PRICE):** A price violates D-024/D-025 (sale >= applicable base, zero/negative, formatted string, or sale without a base). Approving nothing here fixes data; instead correct the SOURCE (workbook) and re-import — the corrected run is a new D-027 event. Rejecting the row keeps canonical clean.

### Item — queue index `1`

- Sheet/row: محصولات / row 5
- Message: product_sale: sale price must be < list_price
- Queued at: 2026-09-14T10:22:27+00:00

```json
{
  "sheet": "محصولات",
  "row": 5,
  "code": "INVALID_PRICE",
  "message": "product_sale: sale price must be < list_price"
}
```

**Decision (owner):** ☐ approve ☐ reject — rationale: ____________

### Item — queue index `3`

- Sheet/row: محصولات / row 9
- Message: effective price unresolved: no base price (list/override)
- Queued at: 2026-09-14T10:22:27+00:00

```json
{
  "sheet": "محصولات",
  "row": 9,
  "code": "INVALID_PRICE",
  "message": "effective price unresolved: no base price (list/override)"
}
```

**Decision (owner):** ☐ approve ☐ reject — rationale: ____________

### Item — queue index `4`

- Sheet/row: محصولات / row 10
- Message: formatted/non-numeric price rejected: '590,000'
- Queued at: 2026-09-14T10:22:27+00:00

```json
{
  "sheet": "محصولات",
  "row": 10,
  "code": "INVALID_PRICE",
  "message": "formatted/non-numeric price rejected: '590,000'"
}
```

**Decision (owner):** ☐ approve ☐ reject — rationale: ____________

### Item — queue index `15`

- Sheet/row: تنوع‌ها / row 14
- Message: variant_sale: sale price must be < applicable base (override else list)
- Queued at: 2026-09-14T10:22:27+00:00

```json
{
  "sheet": "تنوع‌ها",
  "row": 14,
  "code": "INVALID_PRICE",
  "message": "variant_sale: sale price must be < applicable base (override else list)"
}
```

**Decision (owner):** ☐ approve ☐ reject — rationale: ____________

## DUPLICATE_PRODUCT_ID — 1 item(s)

**Guidance (DUPLICATE_PRODUCT_ID):** The same Product ID appears more than once (D-028 §12). Identifiers are immutable and never auto-merged; one row is right, the rest are corrected in the source workbook.

### Item — queue index `2`

- Sheet/row: محصولات / row 6
- Message: P90002 appears more than once
- Queued at: 2026-09-14T10:22:27+00:00

```json
{
  "sheet": "محصولات",
  "row": 6,
  "code": "DUPLICATE_PRODUCT_ID",
  "message": "P90002 appears more than once"
}
```

**Decision (owner):** ☐ approve ☐ reject — rationale: ____________

## INVALID_PRODUCT_ID — 1 item(s)

**Guidance (INVALID_PRODUCT_ID):** Not P+5 digits (D-014 rule 1). Identifiers are human/approved-tooling issued only (D-014) — AI never assigns one. Reject and supply the correct ID in the workbook.

### Item — queue index `5`

- Sheet/row: محصولات / row 11
- Message: شناسه محصول 'P90' is not P+5 digits
- Queued at: 2026-09-14T10:22:27+00:00

```json
{
  "sheet": "محصولات",
  "row": 11,
  "code": "INVALID_PRODUCT_ID",
  "message": "شناسه محصول 'P90' is not P+5 digits"
}
```

**Decision (owner):** ☐ approve ☐ reject — rationale: ____________

## ORPHAN_VARIANT — 2 item(s)

**Guidance (ORPHAN_VARIANT):** The variant's Product ID has no محصولات row in the same workbook (D-028 §12: never silently merged). Decide whether the product row is missing from this workbook (reject here, fix workbook) or the Product ID is mistyped (reject, correct the identifier — IDs are never auto-corrected).

### Item — queue index `6`

- Sheet/row: تنوع‌ها / row 5
- Message: شناسه محصول 'P90007' has no محصولات row in this workbook (never silently merged)
- Queued at: 2026-09-14T10:22:27+00:00

```json
{
  "sheet": "تنوع‌ها",
  "row": 5,
  "code": "ORPHAN_VARIANT",
  "message": "شناسه محصول 'P90007' has no محصولات row in this workbook (never silently merged)"
}
```

**Decision (owner):** ☐ approve ☐ reject — rationale: ____________

### Item — queue index `13`

- Sheet/row: تنوع‌ها / row 12
- Message: شناسه محصول 'P99999' has no محصولات row in this workbook (never silently merged)
- Queued at: 2026-09-14T10:22:27+00:00

```json
{
  "sheet": "تنوع‌ها",
  "row": 12,
  "code": "ORPHAN_VARIANT",
  "message": "شناسه محصول 'P99999' has no محصولات row in this workbook (never silently merged)"
}
```

**Decision (owner):** ☐ approve ☐ reject — rationale: ____________

## UNKNOWN_VOCABULARY — 1 item(s)

**Guidance (UNKNOWN_VOCABULARY):** Value is not among the owner-approved terms (D-019: no auto-vocabulary creation, no aliases). Reject here; either correct the value to an approved term or bring a new term as an owner decision (D-031 governance).

### Item — queue index `7`

- Sheet/row: تنوع‌ها / row 6
- Message: رنگ 'فیروزه\u200cای' is not an approved color (never auto-created; D-019)
- Queued at: 2026-09-14T10:22:27+00:00

```json
{
  "sheet": "تنوع‌ها",
  "row": 6,
  "code": "UNKNOWN_VOCABULARY",
  "message": "رنگ 'فیروزه\\u200cای' is not an approved color (never auto-created; D-019)"
}
```

**Decision (owner):** ☐ approve ☐ reject — rationale: ____________

## UNKNOWN_SIZE_FAMILY — 1 item(s)

**Guidance (UNKNOWN_SIZE_FAMILY):** خانواده سایز is not one of حروفی/عددی/کمر (D-031). Reject; fix the family label — never invent a family.

### Item — queue index `8`

- Sheet/row: تنوع‌ها / row 7
- Message: خانواده سایز 'کفشی' is not approved
- Queued at: 2026-09-14T10:22:27+00:00

```json
{
  "sheet": "تنوع‌ها",
  "row": 7,
  "code": "UNKNOWN_SIZE_FAMILY",
  "message": "خانواده سایز 'کفشی' is not approved"
}
```

**Decision (owner):** ☐ approve ☐ reject — rationale: ____________

## SIZE_FAMILY_MISMATCH — 1 item(s)

**Guidance (SIZE_FAMILY_MISMATCH):** The size exists but not in the selected family (D-020: family-scoped; numeric 42 ≠ pants-waist 42; no conversion). Reject; correct family OR size in the workbook.

### Item — queue index `9`

- Sheet/row: تنوع‌ها / row 8
- Message: سایز '42' does not belong to family 'alpha' (family-scoped; D-020)
- Queued at: 2026-09-14T10:22:27+00:00

```json
{
  "sheet": "تنوع‌ها",
  "row": 8,
  "code": "SIZE_FAMILY_MISMATCH",
  "message": "سایز '42' does not belong to family 'alpha' (family-scoped; D-020)"
}
```

**Decision (owner):** ☐ approve ☐ reject — rationale: ____________

## SKU_MISMATCH — 1 item(s)

**Guidance (SKU_MISMATCH):** SKU does not match Product ID + active-axis codes (D-014 rule 6; D-032 codes incl. D-057 LRG). SKUs are derived by approved tooling — reject and let tooling derive, or fix the axis values.

### Item — queue index `10`

- Sheet/row: تنوع‌ها / row 9
- Message: SKU 'P90002-BK-M' does not match active axes (expected 'P90002-BK-LRG'; D-014 rule 6)
- Queued at: 2026-09-14T10:22:27+00:00

```json
{
  "sheet": "تنوع‌ها",
  "row": 9,
  "code": "SKU_MISMATCH",
  "message": "SKU 'P90002-BK-M' does not match active axes (expected 'P90002-BK-LRG'; D-014 rule 6)"
}
```

**Decision (owner):** ☐ approve ☐ reject — rationale: ____________

## DUPLICATE_SKU — 1 item(s)

**Guidance (DUPLICATE_SKU):** SKU already exists (D-028 §12). SKU is unique business data (never an identity key, D-046). Reject; resolve the duplicate at the source.

### Item — queue index `11`

- Sheet/row: تنوع‌ها / row 10
- Message: SKU P90002-BK-M already exists
- Queued at: 2026-09-14T10:22:27+00:00

```json
{
  "sheet": "تنوع‌ها",
  "row": 10,
  "code": "DUPLICATE_SKU",
  "message": "SKU P90002-BK-M already exists"
}
```

**Decision (owner):** ☐ approve ☐ reject — rationale: ____________

## DUPLICATE_VARIANT_COMBINATION — 1 item(s)

**Guidance (DUPLICATE_VARIANT_COMBINATION):** Same Product ID + active Color + active Size appears twice (D-014 rule 11: never merged). Reject; one variant is real, the duplicate is a workbook error.

### Item — queue index `12`

- Sheet/row: تنوع‌ها / row 11
- Message: active-axis combination ('P90002', 'BK', 'M') is duplicated (D-014 rule 11; never merged)
- Queued at: 2026-09-14T10:22:27+00:00

```json
{
  "sheet": "تنوع‌ها",
  "row": 11,
  "code": "DUPLICATE_VARIANT_COMBINATION",
  "message": "active-axis combination ('P90002', 'BK', 'M') is duplicated (D-014 rule 11; never merged)"
}
```

**Decision (owner):** ☐ approve ☐ reject — rationale: ____________

## INVALID_SKU — 1 item(s)

**Guidance (INVALID_SKU):** Deterministic validation surfaced this item (D-028). Reject unless the source data is confirmed correct; corrections happen in the source workbook and re-import as a new event — canonical values are never silently overwritten.

### Item — queue index `14`

- Sheet/row: تنوع‌ها / row 13
- Message: SKU 'P90002-GRY-L' violates D-014 format or uses non-approved codes
- Queued at: 2026-09-14T10:22:27+00:00

```json
{
  "sheet": "تنوع‌ها",
  "row": 13,
  "code": "INVALID_SKU",
  "message": "SKU 'P90002-GRY-L' violates D-014 format or uses non-approved codes"
}
```

**Decision (owner):** ☐ approve ☐ reject — rationale: ____________

---

*Generated by `local/scripts/make_review_pack.py`; regenerate after each decision round. Tooling never decides (D-050).*

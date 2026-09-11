# DATA MODEL

Conceptual data model for the AI-First Online Business Engine.

**Status:** Approved direction from `MASTER_PLAN.md` §4–§8 and
`PROJECT_RULES.md` §6–§13. This is a **conceptual** model only: it does
not define a physical schema, a database engine, or a WooCommerce field
mapping. Those are Phase 2 / Phase 3 work and remain open decisions.

---

## 1. Entities

The normalized conceptual model contains:

- **Product** — the general product definition
- **Variant** — a real, independently sellable combination of a product
- **Media** — images and other media attached to products
- **Options / Taxonomy** — controlled vocabularies (categories, colors, sizes, …)

## 2. Relationships

```text
Product 1 --- 0..n Variant
Product 1 --- 0..n Media
Product n --- n Taxonomy terms (category, color, size, ...)
Variant  n --- n Taxonomy terms (color, size, ...)
```

Rules:

- A Product may have **zero variants**. A product without variants must
  never be forced into artificial variants (MASTER_PLAN §4, RULES §9).
- A Variant belongs to exactly one Product.
- Variant-level prices and inventory are supported; product-level
  information is not duplicated inside Variants.

## 3. Product

Fields (from MASTER_PLAN §4; all optional unless explicitly marked
required — "truly required" fields are an open decision):

| Field | Notes |
| --- | --- |
| Product ID | Internal identifier |
| Name | |
| Brand | |
| Main category | Taxonomy term |
| Subcategory | Taxonomy term |
| Product status | Lifecycle state |
| Price | Numeric Toman (see §8) |
| Previous price | Numeric Toman |
| Discount | Derived or explicit; never invented by AI |
| Material / fabric | |
| Color | Taxonomy term (product-level default; variant-level overrides) |
| Size | Taxonomy term (product-level default; variant-level overrides) |
| Pattern | |
| Model / form | |
| Style | Taxonomy term |
| Season | Taxonomy term |
| Usage | Taxonomy term |
| Collar | Taxonomy term |
| Sleeve | Taxonomy term |
| Length | Taxonomy term |
| Closure | Taxonomy term |
| Stretch | |
| Fabric thickness | |
| Suitable-for | Taxonomy term |
| Description | |
| Short description | |
| SEO title | |
| SEO description | |
| Keywords | |
| Main image | Reference to Media |
| Additional media | References to Media |
| Product URL | |
| Publication status | |
| Created / updated dates | |
| Internal notes | Never customer-facing |

Incomplete products are valid. Do not block product creation over
optional fields; never fill missing optional fields with guesses.

## 4. Variant

Fields (from MASTER_PLAN §4):

| Field | Notes |
| --- | --- |
| Variant ID | Internal identifier |
| Product ID | Owning product |
| SKU | Unique; see §9 |
| Color | Taxonomy term |
| Size | Taxonomy term |
| Price | Numeric Toman; may differ per variant |
| Sale price | Numeric Toman |
| Stock quantity | Verified data only |
| Stock status | Derived from verified stock |
| Barcode | |
| Weight | |
| Status | Lifecycle state |

## 5. Media

Fields (from MASTER_PLAN §4):

| Field | Notes |
| --- | --- |
| Media ID | |
| Product ID | Owning product |
| Media type | |
| URL | |
| Alt text | Required for accessibility |
| Display order | |
| Source | Where the media came from |
| Created date | |
| Status | |

## 6. Options / Taxonomy

Planned vocabularies (MASTER_PLAN §4): categories, colors, sizes,
fabrics, styles, seasons, uses, collar types, sleeve types, length
types, closure types.

- Controlled vocabulary is used where consistency matters.
- Unknown / unprovided values are always preserved as explicit states —
  the vocabulary must never force a guess.

The concrete value lists for each vocabulary are an **open decision**
(Phase 2).

## 7. Data integrity & provenance

Missing-value states (RULES §6, MASTER_PLAN §5):

- `UNKNOWN` — looked for, not determinable
- `NOT_PROVIDED` — the source did not supply it

Provenance states (RULES §7, MASTER_PLAN §5):

- `AI_GENERATED` — AI output, not yet human-reviewed
- `HUMAN_REVIEWED` — accepted by a human; may still contain AI content
- `HUMAN_VERIFIED` — confirmed by a human against a trusted source

Hard rules:

- AI must never invent: material, color, size, measurements, price,
  discount, stock, shipping time, payment status, order status, or
  customer information.
- AI inference must never be presented as verified fact.
- Every AI-generated field must remain distinguishable as
  `AI_GENERATED` until a human changes its state.

## 8. Pricing

- Currency: **Iranian Toman**.
- Store prices as numbers: `590000`.
- Never store formatted strings (`590,000 تومان`) as the primary stored
  value. Formatting happens at display time only.
- Production prices are never changed automatically without explicit
  authorization and auditability. AI may only *recommend* price changes
  (Yellow tier).

## 9. SKU

- Every independently stocked/sold variant needs a unique SKU.
- SKUs are unique, deterministic, stable; never silently reused; a
  duplicate SKU is a blocking data-integrity error; production changes
  require human approval (RULES §10, MASTER_PLAN §4).
- **Provisional pattern:** `P0001-BLK-M`.
- **Status: OPEN.** The final production convention must be explicitly
  approved before any inventory automation.

## 10. Inventory

- WooCommerce is the transactional inventory Source of Truth.
- Inventory operations use verified data only; AI never estimates
  actual stock.
- Operations are idempotent; duplicate events never double-decrement;
  changes are auditable; retry and recovery are safe (RULES §12).

## 11. Customer & order data

- Transactional customer and order state belongs to WooCommerce (or a
  verified transactional provider).
- Notion may hold operational references but is never the transactional
  source of truth.
- Customer data minimization: collect only what is necessary; no
  unneeded duplication; minimize operational copies in Notion; expose
  customer data to AI only when necessary (RULES §28).

## 12. Open decisions (Phase 2)

| # | Decision | Notes |
| --- | --- | --- |
| 1 | Final SKU convention | Provisional `P0001-BLK-M`; approval gates inventory automation |
| 2 | Truly required product fields | Currently everything except ID/name (+ price) is treated as optional |
| 3 | Taxonomy value lists | Colors, sizes, fabrics, styles, seasons, uses, collar, sleeve, length, closure |
| 4 | WooCommerce field mapping | Conceptual model → WooCommerce concrete mapping (Phase 3) |
| 5 | Data-entry language | Persian / English / bilingual for product data |

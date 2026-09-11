# DATA MODEL

Conceptual data model for the AI-First Online Business Engine.

**Status:** Approved direction from `MASTER_PLAN.md` §4–§8 and
`PROJECT_RULES.md` §6–§13; SKU convention and identifier separation
approved via D-014 / D-015 / D-017; variant-defining attributes,
vocabulary governance, size system (architecture), and required-field
policy approved via D-018 / D-019 / D-020 / D-021 in `DECISIONS.md`.
This is a **conceptual** model only: it does not define a physical
schema, a database engine, or a WooCommerce field mapping. Those are
Phase 2 / Phase 3 work and remain open decisions.

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
required — the required-field policy is approved via D-021; see §12):

| Field | Notes |
| --- | --- |
| Product ID | Business-facing product identifier; = D-014 product code (D-015, D-017) |
| Name | |
| Brand | |
| Main category | Taxonomy term |
| Subcategory | Taxonomy term |
| Product status | Lifecycle state |
| Price | Numeric Toman (see §8) |
| Previous price | Numeric Toman |
| Discount | Derived or explicit; never invented by AI |
| Material / fabric | |
| Color | Taxonomy term; **variant-defining axis** (D-018); product-level default, variant-level value |
| Size | Taxonomy term; **variant-defining axis** (D-018); size family belongs to product config (D-020); product-level default, variant-level value |
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
| Variant ID | Internal identifier; opaque UUIDv4 (D-017) |
| Product ID | Owning product |
| SKU | Unique; see §9 |
| Color | Taxonomy term; required iff Color axis is active for the product (D-018, D-021) |
| Size | Taxonomy term; required iff Size axis is active (D-018, D-021); from the product's declared size family (D-020) |
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
- The concrete value lists for each vocabulary are an **open decision**
  (registry v1 contents — register item 3).

### 6.1 Vocabulary governance (D-019 — APPROVED)

Each controlled attribute has a closed registry of **Attribute Terms**:

| Term field | Notes |
| --- | --- |
| Attribute | Owning vocabulary (color, size, pattern, …) |
| Canonical code | Only for variant-defining vocabularies bearing SKU codes (Color, Size per D-018); must avoid O/I/L (D-014 rule 7) |
| Canonical value/slug | Registry identity |
| Display label | Customer/staff-facing label (e.g., Persian); display stays conventional (L, XL) independently of the SKU code (D-020) |
| Aliases | Alternative spellings/transliterations for input normalization |
| Status | Active / deprecated (never deleted; deprecated remains resolvable) |
| Provenance | D-011 states |
| Created / updated | Timestamps |
| Notes | |

Rules (D-019):

- Humans (owner/delegated staff) create terms via approved tooling;
  variant-defining-vocabulary terms require owner approval.
- AI may **propose** a term into a human review queue (`AI_GENERATED`);
  AI may never create, activate, modify, or delete a term, and may
  reference only existing active terms.
- Normalization: exact alias matching after case/whitespace
  normalization; **no fuzzy matching, no similarity guessing**.
- Unmapped provided values are retained and human-reviewed; never
  discarded or auto-mapped; the vocabulary never forces a guess.

### 6.2 Size system (D-020 — APPROVED, architecture)

- Size is a controlled Attribute Term (D-019) with a `size family`
  classification and optional sort order.
- Families: alpha/letter; numeric; pants/waist; shoe;
  future/brand-specific when genuinely required. No universal system
  is forced.
- **The size family/system context belongs to the product-level
  configuration**; the size term belongs to the variant.
- Canonical size term (registry identity + SKU code) and
  customer-facing display value remain distinguishable; display stays
  conventional (L, XL) regardless of code.
- Measurements are reference data (per term or product) — never
  invented; `NOT_PROVIDED` when absent.
- Brand-specific sizing uses measurement/display context, not a
  separate vocabulary per brand.
- Cross-family conversion is human-curated only; AI never invents
  conversions.
- SKU codes avoid O/I/L (D-014 rule 7); the O/I/L-safe Size-code
  convention is an **open owner approval gate** — mappings not
  finalized.

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
- `HUMAN_VERIFIED` information cannot be silently overwritten by AI;
  only humans change `HUMAN_*` states.

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

### 9.1 Final convention — D-014 (APPROVED, 2026-09-11)

- Product code: five-digit numeric sequence from the beginning —
  `P00001`, `P00002`, `P00003`, … (the earlier four-digit `P0001`
  provisional form is NOT the final standard).
- Variant SKU: product code + canonical attribute suffix, e.g.
  `P00001-BLK-M`.
- Simple product without variants: SKU = product code, e.g. `P00002`.
- Character set: uppercase Latin ASCII only.
- Attribute suffix codes come only from controlled vocabularies;
  humans and AI must not invent arbitrary attribute codes. Attribute
  registries avoid visually confusable letters (O, I, L); product
  numbering remains numeric.
- Structured attributes remain authoritative; the SKU suffix is only a
  compact human/warehouse readability aid. Category and brand are
  never encoded into the SKU.
- SKU is frozen at creation. If a SKU was created incorrectly: do NOT
  rename it; deactivate the incorrect product/variant and create a new
  correct product/variant with a new identifier/SKU.
- The same color + size combination must not exist twice under one
  product; duplicates are data errors and must be rejected. A `-2`
  suffix exists only as an emergency safety valve for exceptional
  collision/disambiguation — never as normal variant numbering.
- Product codes are assigned by humans or approved deterministic
  tooling. AI must NEVER autonomously assign or invent a SKU.
- SKU and barcode/EAN are separate concepts; the SKU must not be used
  as the barcode; barcode/EAN has its own field and lifecycle.
- Five-digit numbering is the initial standard; business logic must
  not depend on digit count — identifiers are opaque and must not be
  parsed for meaning.
- SKUs are never silently reused for another product/variant.

### 9.2 Identifiers — Product ID / Variant ID / SKU (D-015, D-017 — APPROVED)

- **Product ID** — stable business-facing product identifier,
  human-readable (`P00001`), stable, category-agnostic, not derived
  from the product name.
- **Variant ID** — separate stable internal identifier for a variant;
  must NOT be the SKU; opaque and system-safe. Its exact physical
  representation/generation mechanism is a later implementation
  decision (no UUID or database-specific format chosen now).
- **SKU** — business/inventory identifier; human-readable; used for
  WooCommerce/inventory/Excel/n8n references; immutable after creation.
- **The SKU is NOT the internal database identity of a variant.** SKU
  parsing must never be used as the source of attribute truth —
  structured attributes (see §6) are authoritative.
- Product ID is the canonical name for the D-014 product code — one
  identifier, not two (D-017).
- Product ID format: `P` + five-digit zero-padded sequence; immutable;
  never reused; issued only by humans or approved deterministic
  tooling (D-017).
- Variant ID format: UUIDv4, canonical lowercase hyphenated; opaque;
  issued at variant creation by approved deterministic tooling;
  immutable; never reused (D-017).
- AI must never issue, assign, invent, or transform Product IDs,
  Variant IDs, or SKUs (D-017; extends D-014 rule 12).
- Product IDs and SKUs share one uniqueness namespace (structurally
  collision-free).
- Identifier-based import idempotency (D-017): products keyed by
  Product ID; variants by Variant ID (SKU fallback); identical
  re-import = no-op; conflicting payload = human review, never a
  silent overwrite. Event-level idempotency remains open (D-016.K).

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

Status and ownership of these decisions are tracked in `DECISIONS.md`
(D-014 SKU convention: **Approved**; D-015 identifier separation:
**Approved**; D-017 identifier policy: **Approved**; D-018
variant-defining attributes: **Approved**; D-019 vocabulary governance:
**Approved**; D-020 size-system architecture: **Approved**, size-code
gate open; D-021 required-field policy: **Approved**; D-016:
open-decision register).

| # | Decision | Notes |
| --- | --- | --- |
| 1 | ~~Final SKU convention~~ | Resolved: D-014 **Approved** — see §9.1 |
| 2 | Truly required product fields | Resolved: D-021 **Approved** — creation/publication minimums; AI enrichment bounds |
| 3 | Taxonomy value lists | Governance approved (D-019); **registry v1 contents open** (D-016.C) |
| 4 | WooCommerce field mapping | Open (Phase 3): conceptual model → WooCommerce concrete mapping |
| 5 | Data-entry language | Open (Phase 2): Persian / English / bilingual for product data |
| 6 | Size system | Architecture approved (D-020, multi-family); size-code gate + concrete values open |
| 7 | Variant-defining attributes | Resolved: D-018 **Approved** — {Color, Size}, per-axis applicability |
| 8 | Price/discount model | Open (D-016.G/H): default + variant override + sale behavior |
| 9 | Provenance mechanism | Open (D-016.J): states fixed, physical storage deferred |
| 10 | Import idempotency + Excel import scope | Identifier keying approved (D-017); event-level policy open (D-016.K); Excel scope open (D-016.L) |

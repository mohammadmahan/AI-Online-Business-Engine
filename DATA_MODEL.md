# DATA MODEL

Conceptual data model for the AI-First Online Business Engine.

**Status:** Approved direction from `MASTER_PLAN.md` §4–§8 and
`PROJECT_RULES.md` §6–§13; SKU convention and identifier separation
approved via D-014 / D-015 / D-017; variant-defining attributes,
vocabulary governance, size system (architecture), and required-field
policy approved via D-018 / D-019 / D-020 / D-021; product and publication
status state machines approved via D-022 / D-023; price, discount,
provenance, and event-idempotency models approved via D-024 / D-025 /
D-026 / D-027; the Excel import contract, registry v1 structure, and
size-code governance approved via D-028 / D-029 / D-030 in
`DECISIONS.md`.
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
| Product status | Lifecycle state (see §3.1, D-022) |
| Price | Numeric Toman (see §8) |
| Previous price | Numeric Toman |
| Discount | Expressed as an explicit sale price (D-025); never a stored percentage; never invented by AI |
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
| Publication status | Storefront visibility; separate from product status (see §3.2, D-023) |
| Created / updated dates | |
| Internal notes | Never customer-facing |

Incomplete products are valid. Do not block product creation over
optional fields; never fill missing optional fields with guesses.

### 3.1 Product status (D-022 — APPROVED)

The product lifecycle state machine. **Product status is a separate
concept from publication status (§3.2) and is never replaced by it.**

States:

| State | Meaning |
| --- | --- |
| `draft` | Exists, work-in-progress; incomplete products valid (RULES §8); never sellable; never published |
| `active` | Usable product; entry = human approval of the draft + all D-021 publication checks passing; not directly customer-visible by itself (visibility is publication, §3.2) |
| `archived` | Deactivated / no longer offered; not sellable; nothing deleted; identifiers, SKU, and history fully preserved |

Allowed transitions (complete set):

| From → To | Authority | Notes |
| --- | --- | --- |
| `draft → active` | Human; or approved deterministic tooling **only** when all D-021 publication checks pass | every variant must satisfy the variant creation minimum, else blocked |
| `active → draft` | Human; approved deterministic tooling only on explicit per-product human instruction | review rejection returns here (publication → `unpublished`) |
| `active → archived` | Human; approved deterministic tooling only on explicit per-product human instruction | variants stop being sellable together with the product |
| `archived → draft` | Human-only | explicit restore decision |

Forbidden transitions: `draft → archived` (no side-step — review via
`active` first); `archived → active` (never — reactivation is via
`draft → active` with full checks).

AI authority: AI may **suggest/prepare** a transition (provenance-
tagged, logged); AI may **never execute** any lifecycle transition and
may never move a product to or out of `archived`.

Variant behavior: variants mirror the product lifecycle; variants are
never left sellable while their product is `draft` or `archived`; no
per-variant archival cascade is created; the D-021 variant creation
minimum is enforced at `draft → active`.

### 3.2 Publication status (D-023 — APPROVED)

The storefront-visibility state machine, **independent of product
status; publication status is never a substitute for product status.**

States:

| State | Meaning |
| --- | --- |
| `unpublished` | Default at creation; not visible |
| `in_review` | Being checked against the D-021 publication minimum |
| `published` | Publicly visible / sellable |
| `withdrawn` | Intentionally unpublished after having been published |

Allowed transitions (complete set):

| From → To | Authority | Notes |
| --- | --- | --- |
| `unpublished → in_review` | Human; or approved deterministic tooling (checks-only) | |
| `in_review → unpublished` | Human; or approved deterministic tooling | rejection / withdrawal from review |
| `in_review → published` | **Red tier — explicit human approval**; approved deterministic tooling executes only after that approval, all checks passing | publication gate below |
| `published → withdrawn` | **Red tier — explicit human approval**; tooling only on explicit human instruction | intentional unpublish |
| `published → in_review` | Human; or approved deterministic tooling | re-review before a material change |
| `withdrawn → in_review` | Human; or approved deterministic tooling | re-publication preparation |

Forbidden transitions: `unpublished → published` (no bypassing
review); `withdrawn → published` (no direct re-publish — re-enter
review first).

Publication checks (gate for any `→ published`; exactly D-021): Name;
Main category; resolvable price; ≥1 media image; valid publication
status; all variants satisfy the variant creation minimum; product
status must be `active` (§3.1). **Description and short description
are NOT blockers.** `UNKNOWN` values are surfaced to human review and
do not automatically block (a future field-specific safety hard-block
may be approved separately; none exists now). Inventory is
verified-data-only; missing stock stays `NOT_PROVIDED`; AI never
estimates stock.

AI authority: AI may prepare review submissions and suggest
transitions (Yellow tier, provenance-tagged); AI may **never execute**
publish or unpublish.

### 3.3 Lifecycle edge cases (D-022 / D-023)

1. **Created but incomplete** — valid in `draft`; creation is never
   blocked by optional fields (RULES §8, D-021).
2. **No variants (simple product)** — valid at every status; SKU =
   Product ID (D-014 rule 4); publication gate unchanged.
3. **One incomplete variant** — blocks `draft → active` and any
   `→ published` (variant creation minimum, D-021); never
   auto-corrected or guessed.
4. **Active variant, publication incomplete** — the product may be
   `active` while publication stays `unpublished`/`in_review`; product
   status never substitutes for publication status.
5. **Unpublished after being published** — `published → withdrawn`
   (human-approved); re-publication only via `withdrawn → in_review →
   published`.
6. **Archived product** — not sellable; nothing deleted;
   identifiers/SKU/history preserved (D-014 rule 14, D-017).
7. **Publishing an archived product** — forbidden directly
   (`archived → active` is forbidden); restore via `archived → draft →
   active` with full checks, then publication review.
8. **Data changes after publication** — routine edits allowed;
   material changes go through `published → in_review` re-review;
   every change is logged (RULES §27).
9. **Price becomes unresolved after publication** — the publication
   checks are surfaced for human decision (withdrawal or correction);
   the price is never auto-guessed or auto-changed (RULES §11).
10. **Required publication data removed after publication** — surfaced
    for human decision; never silently kept public without required
    data (RULES §24: no hidden failure).
11. **UNKNOWN optional/safety-relevant attributes** — surfaced to
    human review; do not automatically block publication (D-021 rule
    5); a future field-specific hard-block may be approved
    separately.
12. **Zero active axes (simple product)** — valid (D-018); SKU =
    Product ID; duplicate rule vacuously satisfied.
13. **One active axis** — valid (e.g. color-only); SKU `P00001-BLK`;
    duplicate checks over active axes only (D-018).
14. **Color + Size variants** — both axes active; SKU `P00001-BLK-M`;
    duplicate color+size combinations rejected (D-014 rule 11).

## 4. Variant

Fields (from MASTER_PLAN §4):

| Field | Notes |
| --- | --- |
| Variant ID | Internal identifier; opaque UUIDv4 (D-017) |
| Product ID | Owning product |
| SKU | Unique; see §9 |
| Color | Taxonomy term; required iff Color axis is active for the product (D-018, D-021) |
| Size | Taxonomy term; required iff Size axis is active (D-018, D-021); from the product's declared size family (D-020) |
| Price | Numeric Toman; may differ per variant (variant override, D-024) |
| Sale price | Numeric Toman; optional; discount representation per D-025 |
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
- SKU codes avoid O/I/L (D-014 rule 7); size-code governance is
  approved via D-030 (uppercase Latin ASCII, no O/I/L in any
  position, owner-approved, frozen once referenced, one code per
  active term, family-scoped namespace); **concrete size-code
  mappings are owner-approved via D-032** (Alpha uses separate
  O/I/L-safe codes — L→LG, XL→XG, XXL→XXG, 3XL→3XG, 4XL→4XG —
  with display labels unchanged; Numeric/Pants Waist use
  canonical value = code); size-equivalence mappings remain
  human-curated/open.

### 6.3 Registry v1 structure (D-029 — APPROVED; concrete values OPEN)

- **Required vocabularies in v1:** `color` and `size`
  (variant-defining, SKU-code-bearing, D-018) and `category`
  (product-level).
- **Deferred vocabularies** (promotable later by owner decision):
  pattern, style, season, usage, collar, sleeve, length, closure,
  suitable-for, brand, material — remain free/product-level optional
  attributes for now.
- **Entry fields (per D-019):** attribute; canonical code (only for
  variant-defining vocabularies; O/I/L-safe per D-030); canonical
  value/slug (lowercase Latin, unique, stable); **Persian display
  label (required)**; optional English label where justified;
  aliases; status (active/deprecated, never deleted); provenance
  (D-011/D-026); created/updated timestamps; notes.
- **Governance unchanged from D-019:** humans create terms
  (variant-defining terms need owner approval); AI proposes only;
  exact alias normalization; no fuzzy matching; unmapped values
  retained and human-reviewed.
- **Concrete category/color/size terms: owner-approved via D-031
  Batch 1** (recorded in
  `docs/phases/phase-02-5-business-data-configuration.md`). Color/size
  **SKU-code mappings: owner-approved via D-032 Batch 2**
  (O/I/L-safe; color `BK`/`BU`/`YW` per the owner correction).
  **Aliases remain OPEN and owner-gated**.

### 6.4 Excel import contract (D-028 — APPROVED)

Excel is an input/import surface, **never a Source of Truth** and
never a transactional store (D-006, RULES §13). Full rules in
`DECISIONS.md` (D-028); key points:

- One workbook, mapped to the semantic fields of this model; the
  **physical sheet/column mapping is owner-approved via D-033**
  (Batch 3): workbook `product-master.xlsx`, sheets محصولات / تنوع‌ها /
  راهنما / گزینه‌ها, exact columns and mappings specified in
  `docs/phases/phase-02-5-excel-master-template.md`.
- One product = one product row + zero or more variant rows; simple
  products need no variant rows; variant rows carry all active axes.
- Import never issues Product IDs (human-supplied only); never
  issues Variant IDs or SKUs (approved deterministic tooling derives
  omitted SKUs after human confirmation); AI never generates any
  identifier.
- Prices: numeric Toman mapped 1:1 to the D-024 fields with D-024
  validation at import; formatted strings rejected.
- Vocabulary/size resolution: exact alias matching against active
  terms within the declared family (D-019/D-020); unmapped values
  retained and human-reviewed — never auto-added to any registry.
- Missing → `NOT_PROVIDED`; unknown → `UNKNOWN` (surfaced, not
  auto-blocking); invalid → rejected with row-level errors, never
  auto-corrected; duplicates (IDs, SKUs, active-axis combinations)
  rejected, nothing silently merged.
- Every imported value carries `IMPORTED` provenance (D-026) with
  workbook/batch reference; each run is itself a D-027 event
  (one (source system, event ID) per batch).
- **Dry-run first:** full validation without writes; only a human
  promotes a dry-run to an actual import; partial failure writes
  nothing; re-import follows D-017 (identical = no-op; conflict =
  human review). Updates beyond the D-017 re-import path are not an
  Excel feature.
- **Explicitly NOT supported:** creating/modifying vocabulary terms;
  issuing identifiers; writing inventory/stock; order/customer/
  payment/shipping data; fuzzy matching or AI-guessed values;
  becoming a persistent store; silent overwrites.

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

## 8. Pricing (D-024 / D-025 — APPROVED)

- Currency: **Iranian Toman** (D-010).
- Store prices as numbers: `590000`.
- Never store formatted strings (`590,000 تومان`) as the primary stored
  value. Formatting happens at display time only.

### 8.1 Price model (D-024 — APPROVED)

Minimal three-field model:

| Field | Level | Notes |
| --- | --- | --- |
| List price | Product | Required; numeric Toman; the reference/base price |
| Variant override | Variant | Optional; required when a variant's price differs from the product list price |
| Sale price (+ optional validity end) | Product or Variant | Optional; the discount representation (§8.2) |

**Effective price (deterministic):** effective sale price (variant-
level sale if set and valid, else product-level sale if set and
valid) → variant override (if set) →
list price. If no base price exists, the
effective price is **unresolved** — never guessed, never invented
(RULES §6); unresolved price blocks publication (D-021). A sale price
must be lower than the effective base price (override, else list);
sale ≥ base is a validation error.

- Historical price changes are recorded in an immutable price-change
  log (who/when/old → new, with provenance); current fields hold only
  current values; log details are implementation-deferred.
- AI may recommend a price change (Yellow tier); AI never creates or
  changes a price; production price changes are Red tier (RULES §11,
  §32).

### 8.2 Discount model (D-025 — APPROVED)

- A discount is *expressed* as an explicit **sale price** — never as a
  live percentage computed over the base price; the base/list price
  field is never silently changed by a discount.
- Scope: product level or variant level, following the same precedence
  as prices (variant-level sale price overrides product-level).
- Fixed final price (Toman) only; display percentages may be computed
  for presentation, never stored as the mechanism.
- Validity: optional `sale price validity end`; expired sale prices
  are ignored (never extended automatically). No start-date scheduling
  in the initial model.
- Active = set and valid; removing/expiring a sale price reverts the
  effective price to the base price.
- Invalid discounts (sale ≥ effective base price; effective price zero
  or negative) are validation errors — rejected, never clamped.
  Negative prices and over-100% are impossible by construction.
- Exactly one effective sale price per product/variant — the most
  specific **valid** one (variant-level if set and valid, else
  product-level); no stacking; an invalid/expired variant sale falls
  back to the product-level sale, then to the base price.
- AI may suggest a discount (Yellow tier); AI never creates, changes,
  or executes a discount (Red tier, RULES §32).
- Out of scope (future phases): coupons, campaigns, loyalty,
  customer-specific pricing, promotional engines.

## 8a. Provenance mechanism (D-026 — APPROVED)

Per-value provenance metadata for important product data (mechanism
for the D-011 states):

- **Scope:** attributes, price fields, media, descriptions/SEO drafts,
  taxonomy references — wherever origin matters.
- **Recorded per value:** source type (exactly one of `HUMAN_ENTERED`,
  `SYSTEM_GENERATED`, `AI_GENERATED`, `IMPORTED`, `EXTERNAL_SYNC`);
  actor/source identity (no secrets); timestamp; review state (D-011
  states, where relevant); optional source reference (import
  file/batch, external record); optional original/source value where
  normalization was applied.
- **No confidence scores** — none is justified by existing documents.
- **Append-only and immutable:** new provenance entries supersede old
  ones, never overwrite them.
- **AI-originated values remain distinguishable:** source type stays
  `AI_GENERATED`; human review raises the review state only and never
  erases the origin; only humans change `HUMAN_*` states.
- **Imported values retain source provenance** (`IMPORTED` + source
  reference; original value kept where normalization applied).
- **No secrets in provenance** (RULES §16, §27).
- **Provenance ≠ audit history:** provenance answers "where did this
  value come from"; event/audit history (RULES §27) is a separate
  concern; no audit-log system is designed here.

## 8b. Event-level idempotency (D-027 — APPROVED)

Duplicate suppression for webhook/retry/scheduled events; **distinct
from and complementary to identifier-based import idempotency
(§9.2, D-017)** — identifier keying resolves *what* is written;
event idempotency resolves *whether an event runs again*.

Conceptual record per processed event:

| Field | Notes |
| --- | --- |
| Source system | Which system sent the event |
| Event ID | Stable source event ID; when absent, deterministic hash of (operation type, target identifier, timestamp, payload) |
| Operation type | What the event does |
| Received timestamp | When received |
| Processing status | `received` → `processing` → `succeeded` / `failed` / `skipped_duplicate` |
| Result / reference | Outcome reference where applicable |

Rules:

- **Uniqueness key:** (source system, event ID). Repeat with identical
  payload → skipped and logged; repeat with conflicting payload →
  data-integrity error, flagged for human review, never silently
  reprocessed (mirrors D-017).
- **Terminal states** (`succeeded`, `skipped_duplicate`) are never
  re-entered; retries are safe while non-terminal or after `failed`.
- **Failure handling:** failures are logged and flagged (RULES §24);
  partial failures reported honestly (RULES §41).
- **Retention:** long enough per RULES §27; concrete period is an
  implementation decision, deferred.
- No database structures, provider behavior, or distributed-systems
  machinery is defined here.

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
**Approved**; D-020 size-system architecture and D-030 size-code
governance: **Approved** (concrete mappings open); D-021 required-field
policy: **Approved**; D-022 product status and D-023 publication status
state machines: **Approved**; D-024 price model, D-025 discount model,
D-026 provenance mechanism, D-027 event-level idempotency, D-028
Excel import contract, and D-029 registry v1 structure: **Approved**;
D-016: open-decision register).

| # | Decision | Notes |
| --- | --- | --- |
| 1 | ~~Final SKU convention~~ | Resolved: D-014 **Approved** — see §9.1 |
| 2 | Truly required product fields | Resolved: D-021 **Approved** — creation/publication minimums; AI enrichment bounds |
| 3 | Taxonomy value lists | Governance (D-019) + v1 structure (D-029) **Approved**; concrete terms **owner-approved via D-031 Batch 1**; SKU-code mappings **resolved via D-032 Batch 2** (O/I/L-safe); aliases open (D-016.C) |
| 4 | WooCommerce field mapping | Open (Phase 3): conceptual model → WooCommerce concrete mapping |
| 5 | Data-entry language | Open (Phase 2): Persian / English / bilingual for product data |
| 6 | Size system | Architecture (D-020) + size-code governance (D-030) **Approved**; size terms owner-approved (D-031 Batch 1); concrete code mappings resolved (D-032 Batch 2, family-scoped) |
| 7 | Variant-defining attributes | Resolved: D-018 **Approved** — {Color, Size}, per-axis applicability |
| 8 | Price/discount model | Resolved: D-024 / D-025 **Approved** — see §8 |
| 9 | Provenance mechanism | Resolved: D-026 **Approved** — see §8a; physical storage deferred to implementation |
| 10 | Import idempotency | Resolved: D-027 **Approved** (event-level, §8b) + D-017 (identifier-based, §9.2); Excel import contract per D-028 (§6.4) |
| 11 | Product/publication status state machines | Resolved: D-022 / D-023 **Approved** — see §3.1 / §3.2 |
| 12 | Excel import scope | Resolved: D-028 **Approved** — see §6.4; physical sheet/column mapping resolved by D-033 (physical contract in `docs/phases/phase-02-5-excel-master-template.md`) |
| 13 | Registry v1 structure / values | Structure resolved: D-029 **Approved** — see §6.3; concrete values remain OPEN and owner-gated |
| 14 | Size-code governance / mappings | Governance resolved: D-030 **Approved** — see §6.2/§6.3; concrete mappings **resolved via D-032 Batch 2** (owner-approved, O/I/L-safe, family-scoped) |

## 13. Consolidated logical model (Phase 2 — implementation-ready)

This section consolidates the decision set D-014–D-030 into one
coherent logical model: entities, relationships, identity, missing-
value semantics, import/idempotency, provenance, authority, and the
implementation-deferred boundary. It is implementation-ready at the
logical level — a developer could build the product-data backend from
this model plus the referenced detail sections without inventing
business rules. No entity, field, or rule here is new business logic;
each traces to D-014–D-030. Physical representation is deliberately
deferred (§13.8).

### 13.1 Entity catalog

| Entity | Purpose | Stable identity | Key constraints | Authority | Detail |
| --- | --- | --- | --- | --- | --- |
| Product | General product definition | Product ID (`P#####`), immutable, never reused | Creation minimum (D-021); lifecycle (D-022); publication (D-023); publication minimum incl. resolvable price (D-021/D-024) | Human / approved tooling; AI never issues IDs | §3, §3.1, §3.2, §9.2 |
| Product Variant | Real, independently sellable combination | Variant ID (UUIDv4), immutable, never reused | One parent product; (product, active axes) unique (D-014 rule 11); SKU unique (RULES §10); creation minimum (D-021) | Tool-issued IDs; human data entry; AI never issues IDs | §4, §9.2 |
| Price | Numeric Toman price fields: list price, variant override | — (fields on Product/Variant) | D-024 precedence; numeric Toman (D-010); no conversion logic; no engine | Human; AI recommends only | §8.1 |
| Sale price / discount | Optional sale price + validity end (product- or variant-level) | — (fields on Product/Variant) | sale < effective base; no zero/negative; no stored percentage; no stacking; no engine (D-025) | Human; AI suggests only | §8.2 |
| Controlled Vocabulary Term | Canonical value in a closed registry | (vocabulary, canonical slug); canonical code where applicable | Persian label required; code O/I/L-safe (variant-defining only); active/deprecated, never deleted; exact-alias resolution | Human-owned; owner approval for variant-defining; AI proposes only | §6.1, §6.3, D-029 |
| Size family / size term | Size-system classification | Size term = vocabulary term + family | Family context on product; term on variant; family-scoped code namespace; no auto-conversion | Human-curated equivalence only; D-030 governance | §6.2, D-030 |
| Provenance record | Origin of a value | (value, version), append-only | Source type ∈ {HUMAN_ENTERED, SYSTEM_GENERATED, AI_GENERATED, IMPORTED, EXTERNAL_SYNC}; review state (D-011); no secrets | Written by the system performing the change; humans advance review state | §8a, D-026 |
| Import run / event | One Excel import execution | (source system, event ID) | D-027 status machine; run provenance (workbook ref, timestamps, counts, approver) | Human-promoted; tool executes; AI never executes | §6.4, §8b, D-028 |
| Idempotency record | Duplicate suppression for events | = the event record (§8b) | Identifier-level idempotency is a constraint on identity keys, not a separate entity | — | §8b, §9.2 |
| Publication status | Storefront visibility | — (state on Product) | D-023 states/transitions; Red tier for publish/unpublish | Human; tool per D-023; AI never executes | §3.2 |
| Product lifecycle status | Lifecycle state | — (state on Product) | D-022 states/transitions; variants mirror | Human; tool per D-022; AI never executes | §3.1 |

### 13.2 Consolidated relationships

```text
Product 1 ─── 0..n Variant
Product 1 ─── 1 Price (list)          Variant 1 ─── 0..1 Price override
Product/Variant ─── 0..1 Sale price (+ optional validity end)
Product/Variant ─── n..n Vocabulary Term (category, color, size, …)
Variant ─── 0..1 Color term (iff Color axis active)
Variant ─── 0..1 Size term (iff Size axis active; family from Product)
Value ─── 1..n Provenance record (append-only; supersede, never overwrite)
Import run ─── n imported values (IMPORTED provenance)
Import run ─── 1 event idempotency record (D-027)
Product ─── 1 product status (D-022) ; 1 publication status (D-023)
```

No physical relational schema is implied; these are logical
relationships only.

### 13.3 Identity model

**Product ID ≠ Variant ID ≠ SKU ≠ internal database identity** (D-014,
D-015, D-017 — see §9.2):

- **Product ID** — `P` + five digits, uppercase Latin ASCII, immutable,
  never reused; issued by humans or approved deterministic tooling;
  AI never creates or assigns it.
- **Variant ID** — UUIDv4 canonical lowercase hyphenated; immutable,
  never reused; the internal identity of a variant; issued by approved
  deterministic tooling; AI never creates or assigns it.
- **SKU** — business/inventory identifier; immutable after creation;
  D-014 rules (suffix = active axes in Color → Size order, D-018);
  never the database primary identity; AI never creates or assigns it.
- **Internal database identity** — owned by the future database
  technology; not defined in Phase 2 (implementation-deferred).

### 13.4 Missing-value semantics

| State | Meaning | Handling |
| --- | --- | --- |
| `NOT_PROVIDED` | The source did not supply the value | Preserved as-is; never guessed (RULES §8) |
| `UNKNOWN` | Searched for but not determinable | Preserved; surfaced to human review; does not automatically block publication (D-021 rule 5) |
| `INVALID` | Supplied, but structurally or business-rule invalid | Rejected at validation with a row/field-level error; never auto-corrected, never clamped (D-028 rule 13) |

These three states are distinct and are never silently transformed
into one another (D-011, D-021, D-028).

### 13.5 Import / idempotency model

Two separate mechanisms, never merged (D-017, D-027, D-028):

- **A) Identifier-level idempotency** — products keyed by Product ID;
  variants by Variant ID (SKU fallback where Variant ID is absent).
  Identical re-import = no-op; conflicting payload = human review,
  never a silent overwrite (D-017 rule 10, §9.2).
- **B) Event-level idempotency** — one record per event: source
  system, event ID, operation type, received timestamp, processing
  status (`received` → `processing` → `succeeded` / `failed` /
  `skipped_duplicate`), result/reference. Terminal states are never
  re-entered (D-027, §8b).
- **One import run is one event**; the rows inside it still obey the
  identifier-level rules (D-028 rules 16–17).

### 13.6 Import provenance

Excel import produces `IMPORTED` provenance (D-026, D-028 rule 8):

- source reference = workbook/batch;
- original/source value retained where normalization was applied;
- import event/run reference (D-027 event ID).

Excel is **input only**. Excel is **not**: a Source of Truth, a
transactional database, an inventory database, or an order database
(D-006, RULES §13).

### 13.7 Authority matrix

| Operation | Human | Approved deterministic tooling | AI |
| --- | --- | --- | --- |
| Create product / enter product data | Yes | Yes (import, D-028) | Drafts/suggestions only (D-021) |
| Issue Product ID | Yes | Yes (approved) | Never (D-014 rule 12, D-017) |
| Issue Variant ID | — | Yes (approved) | Never (D-017) |
| Construct / issue SKU | Yes (per D-014) | Yes (approved, after human confirmation) | Never (D-014 rule 12) |
| Create vocabulary term | Yes (owner approval for variant-defining) | No | Propose only (D-019) |
| Assign size code | Yes (owner) | Derive/validate candidates (D-030) | Propose only (D-030) |
| Lifecycle transitions | Yes | Per D-022 (checks-only for draft→active) | Suggest only; never execute (D-022) |
| Publication transitions | Yes (Red tier) | Per D-023 (never publish/unpublish) | Suggest only; never execute (D-023) |
| Production price changes | Yes (Red tier) | Execute after approval | Recommend only (RULES §11, §32) |
| Excel import execution | Promotes dry-run | Executes after promotion | Never executes; may prepare/summarize (D-028) |
| Resolve import exceptions | Yes | No | No (D-028 rule 19) |

### 13.8 Implementation-deferred boundary

The following are **not** decided in Phase 2 and must not be inferred
from this model:

- SQL database engine / ORM / exact table names / indexes
- UUID implementation library
- Excel parser library / API implementation / storage format
- Infrastructure, caching, queues
- Physical transaction mechanism (atomicity is a logical requirement
  of the import contract, D-028 rule 20; the mechanism is deferred)
- Price-change-log physical shape (D-024 rule 9)
- Provenance physical storage (D-026)
- Event-record retention period (D-027 rule 7)
- Physical Excel sheet/column mapping ~~(D-028 rule 1)~~ — resolved
  via D-033 (owner-approved physical contract;
  `docs/phases/phase-02-5-excel-master-template.md`); the template
  **file** is produced at the implementation task
- Concrete size-code mappings ~~(D-030)~~ — resolved via D-032
  (owner-approved); color/size aliases and any further vocabulary
  promotions remain open (D-029/D-031)

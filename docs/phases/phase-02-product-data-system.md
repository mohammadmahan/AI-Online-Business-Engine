# Phase 2 — Product Data System

Status: **In progress**

---

## Purpose

Design and specify the Product Data System: the product/variant model,
identifiers, taxonomy, media, validation, import/export, and Excel
import preparation — per MASTER_PLAN §13 (Phase 2). Documentation and
decision-recording only in this phase; no implementation, no schemas,
no code.

Entry condition (Phase 1 exit):

- Architecture foundation created and approved (commit `e6d85ca`).
- D-014 Final SKU convention resolved: **Approved** (2026-09-11).

## Scope

- Finalize the logical product/variant model on top of
  `DATA_MODEL.md`.
- Record and apply decisions D-014 (SKU convention), D-015
  (identifier separation), D-017 (identifier policy), D-018
  (variant-defining attributes), D-019 (vocabulary governance), D-020
  (size-system policy), and D-021 (required-field policy); resolve the
  remaining D-016 open items.
- Controlled-vocabulary registry v1 (colors, sizes, categories, other
  controlled fields as needed).
- Product/publication status state machines — **D-022/D-023
  approved** (see below).
- Price/discount model definition (no implementation).
- Provenance mechanism definition (states fixed; storage deferred).
- Import idempotency policy; Excel import specification (and template
  only if approved — D-016.L).
- Phase 2 final review, then commit only after human approval.

## D-014 — Final SKU convention (APPROVED)

1. SKU convention: product code + canonical attribute suffix.
2. Product code: five-digit numeric sequence from the beginning —
   `P00001`, `P00002`, `P00003`, …; the four-digit `P0001` provisional
   form is not the final standard.
3. Variant SKU: product code + canonical attribute suffix,
   e.g. `P00001-BLK-M`.
4. Simple product without variants: SKU = product code, e.g. `P00002`.
5. Character set: uppercase Latin ASCII only.
6. Attribute suffix codes come only from controlled vocabularies;
   humans and AI must not invent arbitrary attribute codes.
7. Attribute-code registries avoid visually confusable letters such as
   O, I, L; product numbering remains numeric.
8. Structured attributes remain authoritative; the SKU suffix is only
   a compact human/warehouse readability aid.
9. Category and brand are NEVER encoded into the SKU.
10. SKU is frozen at creation. Incorrect SKU: do NOT rename;
    deactivate the incorrect product/variant and create a new correct
    product/variant with a new identifier/SKU.
11. Duplicate color + size combinations under one product are data
    errors and must be rejected; a `-2` suffix exists only as an
    emergency safety valve, never as normal variant numbering.
12. Product codes are assigned by humans or approved deterministic
    tooling; AI must NEVER autonomously assign or invent a SKU.
13. SKU and barcode/EAN are separate concepts; the SKU must not be
    used as the barcode.
14. SKU remains stable and is never silently reused.
15. Five-digit numbering is the initial standard; business logic must
    not depend on digit count — identifiers are opaque and must not be
    parsed for meaning.

## Product ID / Variant ID / SKU separation (D-015, D-017 — APPROVED)

- **Product ID** — stable business-facing product identifier,
  human-readable (`P00001`), stable, category-agnostic, not derived
  from the product name. It is the canonical name for the D-014
  product code; issued only by humans or approved deterministic
  tooling; immutable; never reused.
- **Variant ID** — separate stable internal identifier for a variant;
  must NOT be the SKU; opaque and system-safe: **UUIDv4**, canonical
  lowercase hyphenated form; issued only by approved deterministic
  tooling at variant creation; immutable; never reused.
- **SKU** — business/inventory identifier; human-readable; used for
  WooCommerce/inventory/Excel/n8n references; immutable after creation.
- The SKU is NOT the internal database identity of a variant; SKU
  parsing is never the source of attribute truth.
- AI must never issue, assign, invent, or transform Product IDs,
  Variant IDs, or SKUs. Identifier-based import idempotency is
  approved (D-017); event-level idempotency remains open (D-016.K).

## Variant-defining attributes, vocabularies, size system, required fields (D-018–D-021 — APPROVED)

### D-018 — Variant-defining attributes (APPROVED)

- Set: exactly {Color, Size}; per-axis applicability — an axis is
  active only when it genuinely varies across sellable variants;
  non-varying axes are omitted, never guessed; a simple product has
  zero active axes (SKU = Product ID); products differing only by
  product-level attributes are separate products; duplicate checks run
  over active axes only.
- SKU contains exactly the active axes in canonical order Color, then
  Size: `P00001` (simple), `P00001-BLK` (color-only), `P00001-BLK-M`
  (color + size).
- No new axes in Phase 2; inseam/jeans length remains deferred.

### D-019 — Controlled-vocabulary governance (APPROVED; registry v1 contents OPEN)

- Each controlled attribute has a registry of Attribute Terms:
  attribute; canonical code where applicable; canonical value/slug;
  display label; aliases; status (active/deprecated, never deleted);
  provenance; created/updated timestamps; notes.
- Humans (owner/delegated staff) create terms; variant-defining
  vocabulary terms require owner approval.
- AI may propose a term but may never create, activate, modify, or
  delete one; AI references only existing active terms.
- Normalization: exact alias matching after case/whitespace
  normalization; no fuzzy matching; no similarity guessing; unmapped
  provided values are retained for human review.
- No concrete value lists are created by this decision — registry v1
  contents remain owner-supplied and owner-gated.

### D-020 — Size-system policy (APPROVED, architecture; size-code gate OPEN)

- Multi-family size architecture (alpha/letter; numeric; pants/waist;
  shoe; future/brand-specific families when genuinely required); no
  universal size system is forced.
- The size family/system context belongs to the product-level
  configuration; the size term belongs to the variant.
- Canonical size term (registry identity + SKU code) and
  customer-facing display value remain distinguishable; display may
  stay conventional (L, XL).
- Measurements are reference data, never invented. Brand-specific
  sizing uses measurement/display context, not a separate vocabulary
  per brand. Cross-family conversion is human-curated only; AI never
  invents conversions.
- SKU codes avoid O/I/L (D-014 rule 7) — no L exception is created.
  A deterministic O/I/L-safe Size-code convention is a separate OPEN
  owner approval gate; mappings are not finalized.

### D-021 — Required-field policy (APPROVED)

- Product creation minimum: Product ID, Name, Product status, Created
  date.
- Variant creation minimum: Variant ID, Product ID, SKU, all active
  variant-defining attributes, Variant status.
- Publication minimum: Name, Main category, resolvable price, at
  least one media image, valid publication status, all variants valid.
  Description and short description are NOT publication blockers.
- Inventory: nothing required at creation; stock is verified data;
  missing stock stays `NOT_PROVIDED`; AI never estimates stock.
- `UNKNOWN` does not automatically block publication — it is surfaced
  to human review (a future field-specific safety rule may block, but
  none is created now).
- AI enrichment: may draft description, short description, SEO title,
  SEO description, keywords, category/attribute suggestions (Yellow
  tier, provenance-tagged); may NOT create identifiers, prices,
  discounts, stock, vocabulary terms, shipping/payment/order facts, or
  guessed attribute values.

## Product/publication status state machines (D-022, D-023 — APPROVED)

Two separate state machines; **publication status is never a
substitute for product status.**

### D-022 — Product status state machine (APPROVED)

- States: `draft` (exists, incomplete allowed, not sellable),
  `active` (usable; entry = human approval + all D-021 publication
  checks passing), `archived` (deactivated; never deleted; history
  preserved).
- Allowed transitions: `draft → active`; `active → draft`; `active →
  archived`; `archived → draft`.
- Forbidden: `draft → archived` (no side-step); `archived → active`
  (no direct reactivation; restore via `draft` with full checks).
- Authority: humans; `draft → active` may also be executed by
  approved deterministic tooling when all publication checks pass;
  other tool-assisted transitions only on explicit per-product human
  instruction.
- AI: may suggest/prepare (provenance-tagged); may **never execute**
  a lifecycle transition or touch `archived`.
- Variants mirror the product lifecycle; never sellable while their
  product is `draft`/`archived`.

### D-023 — Publication status state machine (APPROVED)

- States: `unpublished` (default), `in_review`, `published`,
  `withdrawn` (intentionally unpublished after having been
  published).
- Allowed transitions: `unpublished → in_review`;
  `in_review → unpublished`; `in_review → published`;
  `published → withdrawn`; `published → in_review` (re-review);
  `withdrawn → in_review` (re-publication preparation).
- Forbidden: `unpublished → published` (no review bypass);
  `withdrawn → published` (no direct re-publish).
- Publication checks (any `→ published`), exactly D-021: Name; Main
  category; resolvable price; ≥1 media image; valid publication
  status; all variants valid; product status `active` (D-022).
  Description/short description are NOT blockers; `UNKNOWN` is
  surfaced to human review, not automatically blocking; inventory is
  verified-data-only; AI never estimates stock.
- Authority: `in_review → published` and `published → withdrawn` are
  **Red tier — explicit human approval**; deterministic tooling may
  run checks and move into/out of review.
- AI: may prepare submissions and suggest transitions; may **never
  execute** publish or unpublish.

## Remaining open decisions

All remaining Phase 2 decisions are **OPEN** (D-016 and the
still-open items in the `DECISIONS.md` open-decision register — the
register is the authoritative list); none may be resolved silently:

- Concrete controlled-vocabulary registry v1 value lists — D-016.C
  (governance approved via D-019; contents owner-supplied)
- Size-code convention avoiding O/I/L — explicit owner approval gate
  (per D-020); concrete size-family values also owner-supplied
- Price model (default + variant override + sale behavior) — D-016.G
- Discount model (sale-price direction preferred, NOT approved) — D-016.H
- Inventory design constraints (already-approved rules remain: WooCommerce
  SoT, verified, idempotent, auditable, AI never estimates) — D-016.I
- Provenance mechanism (states fixed; storage deferred) — D-016.J
- Import idempotency strategy — D-016.K
- Excel import scope (spec only vs spec + template) — D-016.L
- SEO slug language — D-016.M

## Implementation sequence

1. Finalize Product/Variant identifier policy — resolved: D-017
   **Approved** (Product ID = product code; Variant ID = UUIDv4; AI
   never issues identifiers).
2. Finalize variant-defining attributes — resolved: D-018
   **Approved** ({Color, Size}, per-axis applicability).
3. Finalize minimum required product fields — resolved: D-021
   **Approved** (creation/publication minimums; AI enrichment bounds).
4. Design controlled-vocabulary registry v1 — governance resolved:
   D-019 **Approved**; concrete registry v1 contents still open.
5. Resolve size system — architecture resolved: D-020 **Approved**
   (multi-family); O/I/L-safe size-code gate still open.
6. Define product/publication status state machines — resolved:
   D-022 **Approved** (draft/active/archived) and D-023 **Approved**
   (unpublished/in_review/published/withdrawn); publication is Red
   tier.
7. Define price/discount model.
8. Define provenance mechanism.
9. Define import idempotency policy.
10. Decide Excel import scope.
11. Consolidate the logical data model.
12. Produce Excel import specification/template if approved.
13. Perform Phase 2 final review.
14. Commit Phase 2 foundation only after human approval.

## Exit criteria

- [ ] All remaining D-016 items resolved or explicitly deferred with
      owner approval
- [ ] Logical data model consolidated in `DATA_MODEL.md`
- [ ] Controlled-vocabulary registry v1 defined (if approved in scope)
- [ ] Excel import specification complete (scope per D-016.L)
- [ ] Cross-references valid; no secrets; no contradictions
- [ ] Phase 2 final review passed
- [ ] Foundation committed (with explicit human approval)

## Explicit Phase 3 boundary

The following are out of scope for Phase 2 and are NOT started:

- No WooCommerce field mapping
- No WooCommerce configuration
- No n8n workflows
- No payment integration
- No shipping integration
- No production database implementation
- No production credentials

## References

- `MASTER_PLAN.md` §13 (Project Phases — Phase 2), §16 (Current Status)
- `PROJECT_RULES.md` §8–§13 (product, variant, SKU, price, inventory,
  WooCommerce rules)
- `DECISIONS.md` — D-014 (Approved), D-015 (Approved), D-017
  (Approved), D-018 (Approved), D-019 (Approved), D-020 (Approved),
  D-021 (Approved), D-016 (Open)
- `DATA_MODEL.md` — §3.1/§3.2 (status state machines), §9 (SKU), §9.2
  (Identifiers)

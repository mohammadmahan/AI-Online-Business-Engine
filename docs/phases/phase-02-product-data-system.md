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
- Price/discount model — **D-024/D-025 approved** (see below).
- Provenance mechanism — **D-026 approved** (see below).
- Import idempotency policy — **D-027 approved** (see below); Excel
  import contract — **D-028 approved** (see below), with the physical
  sheet/column mapping and template question resolved at the
  specification task (D-016.L scope approved; template decision
  folds into task 12).
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

## Price, discount, provenance, event idempotency (D-024–D-027 — APPROVED)

### D-024 — Price model (APPROVED)

- Minimal three-field model (numeric Iranian Toman, D-010): **list
  price** (required, product level), **variant override** (optional;
  required when the variant differs), **sale price** (optional, with
  optional validity end).
- Effective price (deterministic): effective sale price (variant-level
  sale if set and valid, else product-level sale if set and valid) →
  variant override → list price. No base price → effective price is
  **unresolved** — never guessed (RULES §6); blocks publication
  (D-021).
- Sale price must be lower than the effective base price; sale ≥ base
  is a validation error.
- History: immutable price-change log (who/when/old → new, with
  provenance); details implementation-deferred.
- AI may recommend a price change (Yellow tier); never create or
  change one (production price changes are Red tier, RULES §11/§32).

### D-025 — Discount model (APPROVED)

- Sale-price-based: a discount is an explicit sale price; the base
  price field is never silently changed by a discount; no percentage
  is stored as the mechanism (display percentages computed only).
- Product or variant level, price precedence; fixed final price only;
  optional validity end; expired = ignored (never auto-extended).
- Invalid discounts (sale ≥ effective base; effective price zero or
  negative) are validation errors — rejected, never clamped; negative
  prices and over-100% impossible by construction.
- One effective sale price per product/variant — the most specific
  valid one (variant-level if set and valid, else product-level); an
  invalid/expired variant sale falls back to the product-level sale,
  then to the base price; no stacking.
- AI may suggest only; never creates/changes/executes.
- Out of scope (future): coupons, campaigns, loyalty, customer-specific
  pricing, promotional engines.

### D-026 — Provenance mechanism (APPROVED)

- Per-value provenance: source type (exactly one of `HUMAN_ENTERED`,
  `SYSTEM_GENERATED`, `AI_GENERATED`, `IMPORTED`, `EXTERNAL_SYNC`);
  actor/source identity (no secrets); timestamp; review state (D-011
  states); optional source reference; optional original value where
  normalization applied.
- No confidence scores (not justified by existing documents).
- Append-only/immutable — new entries supersede, never overwrite.
- AI-originated values stay `AI_GENERATED`-origin until a human raises
  the review state; origin is never erased; only humans change
  `HUMAN_*` states.
- Imported values retain source provenance; no secrets stored;
  provenance ≠ audit history (no audit-log system designed here).

### D-027 — Event-level idempotency (APPROVED)

- Distinct from identifier-based import idempotency (D-017): that
  resolves *what* is written; this resolves *whether an event runs
  again*.
- Record per event: source system; event ID (or deterministic hash of
  operation type, target identifier, timestamp, payload when the
  source supplies none); operation type; received timestamp;
  processing status; result/reference.
- Uniqueness key (source system, event ID): identical repeat → skip
  and log; conflicting payload → data-integrity error, human review,
  never silently reprocessed.
- Status flow `received` → `processing` → `succeeded` / `failed` /
  `skipped_duplicate`; terminal states never re-entered; retries safe
  while non-terminal or after `failed`.
- Failures logged and flagged (RULES §24, §41); retention deferred
  (implementation decision).

## Excel import, registry v1, size-code governance (D-028–D-030 — APPROVED)

### D-028 — Excel import contract (APPROVED)

- Excel is an input/import surface — **never a Source of Truth**, never
  a store (D-006, RULES §13). One workbook = the owner's Product
  Master file; the contract is stated over the semantic fields of
  `DATA_MODEL.md` (no physical column names invented — the mapping is
  confirmed once at the specification task).
- One product = one product row + zero or more variant rows; simple
  products need no variant rows; variant rows carry all active axes.
- Excel never manufactures identifiers: Product IDs are human-
  supplied column values only; Variant IDs (UUIDv4) and SKUs come
  only from approved deterministic tooling (omitted SKUs derived
  from structured attributes after human confirmation); AI never
  generates any identifier.
- Prices: numeric Toman mapped 1:1 to D-024 fields; D-024 validation
  runs at import; formatted strings rejected, not parsed.
- Resolution: exact alias matching against active terms (D-019);
  size inputs resolve within the declared family (D-020); unmapped
  values retained and human-reviewed — never silently becoming new
  vocabulary or size terms.
- Missing → `NOT_PROVIDED`; unknown → `UNKNOWN` (surfaced, not
  auto-blocking); invalid → row-level rejection, never auto-corrected;
  duplicates (Product IDs, Variant IDs/SKUs, active-axis combinations)
  rejected, nothing silently merged.
- Every imported value carries `IMPORTED` provenance (D-026); each
  run is a D-027 event (one (source system, event ID) per batch).
- **Dry-run first** (full validation, no writes); only a human
  promotes a dry-run to an actual import; every exception path routes
  to human review; AI may prepare/suggest but never executes an
  import or resolves an exception.
- Partial failure writes nothing; per-row honest reporting (RULES
  §24, §41); re-import follows D-017 (identical = no-op; conflict =
  human review); updates beyond the D-017 re-import path are not an
  Excel feature (future tool concern, Phase 19 class).
- **Explicitly NOT supported:** creating/modifying vocabulary terms;
  issuing identifiers; writing inventory/stock; order/customer/
  payment/shipping data; coupons; fuzzy matching or AI-guessed
  values; becoming a persistent store or second database; silent
  overwrites.

### D-029 — Controlled-vocabulary registry v1, structure (APPROVED; values OPEN)

- **Required in v1:** `color`, `size` (variant-defining,
  SKU-code-bearing) and `category` (product-level).
- **Deferred** until the owner promotes them: pattern, style, season,
  usage, collar, sleeve, length, closure, suitable-for, brand,
  material — free/product-level optional attributes for now.
- Entry fields per D-019, confirmed: canonical code (variant-defining
  only; O/I/L-safe per D-030); canonical value/slug (lowercase Latin,
  unique, stable); **Persian display label required**; English label
  optional where justified; aliases; active/deprecated (never
  deleted); provenance; timestamps; notes.
- Governance unchanged from D-019: humans create (variant-defining
  terms need owner approval); AI proposes only; exact alias
  normalization; no fuzzy matching; unmapped values retained and
  human-reviewed.
- **Concrete registry values remain OPEN and owner-gated** — none are
  invented here.

### D-030 — Size-code governance (APPROVED; concrete mappings OPEN)

- Uppercase Latin ASCII; `O`, `I`, `L` forbidden in any position
  (D-014 rule 7 — no exception is created).
- Owner creates and approves codes; deterministic tooling may
  derive/validate candidates; AI proposes only, never assigns.
- Codes frozen once referenced (deprecate + recreate, never rename);
  one canonical code per active term; aliases resolve to the term,
  not to a second code; namespace scoped within the size family.
- Registry collisions rejected at proposal/validation; SKU
  collisions handled only by the D-014 `-2` emergency valve.
- **Concrete size-code mappings remain an open owner sub-decision** —
  until approved, no size code can be issued for any term.

## Excel import specification (Task 12 — implementation-ready; physical mapping OPEN)

Implementation-ready specification turning D-028 into a deterministic
import procedure. The **physical sheet/column mapping is an OPEN
dependency**: no Product Master workbook exists in this repository
(verified), so no physical sheet names, column names, or headers are
invented or claimed as verified. The owner supplies the workbook; the
mapping-confirmation checklist below is then executed once, and the
result is recorded in task 12's outcome.

### A) Semantic import contract (fixed; independent of physical layout)

| Semantic field | Product row | Variant row | Required | Rules |
| --- | --- | --- | --- | --- |
| Product ID | ✔ | (parent reference) | No* | Human-supplied only; absent → human assignment before completion (D-028 rule 4) |
| Variant ID | — | — | Never in Excel | Tool-issued (UUIDv4) for genuinely new variants (D-028 rule 5) |
| SKU | (simple products) | ✔ | No* | D-014 convention validated if present; omitted → derived by approved tooling after human confirmation (D-028 rule 6) |
| Name | ✔ | — | Yes | Publication minimum (D-021) |
| Main category | ✔ | — | No* | Resolves via Category vocabulary (D-019/D-029); publication minimum (D-021) |
| Color term | (default) | ✔ iff Color axis active | Axis-dependent | Exact-alias resolution (D-019) |
| Size term | (default) | ✔ iff Size axis active | Axis-dependent | Exact-alias resolution within declared family (D-020) |
| Size family | ✔ | — | No* | Product-level context (D-020) |
| List price | ✔ | — | No* | Numeric Toman (D-010/D-024); required for publication (D-021) |
| Variant price override | — | ✔ | No | Numeric Toman (D-024) |
| Sale price (+ validity end) | ✔ | ✔ | No | D-024/D-025 validation at import |
| Product status | ✔ | — | No* | Defaults `draft` (D-022); import never activates |
| Publication status | ✔ | — | No* | Import-created products enter as `unpublished` (D-023); import never publishes |
| Media references | ✔ | — | No | References only; media itself is not imported |
| Description / SEO drafts | ✔ | — | No | Accepted as provenance-tagged content (D-026) |
| Inventory / stock | — | — | — | **Not accepted** (verified data only, RULES §12) |

`No*` = accepted but not required at import; lifecycle/publication
minimums still gate their transitions later (D-021/D-022/D-023).

### B) Physical mapping confirmation checklist (owner workbook)

1. Confirm the workbook file and version (owner-provided).
2. Record each physical **sheet name** and its role
   (products / variants / other).
3. Record each physical **column header** per sheet against the
   semantic fields above; note exact spelling, order, and any merged
   or derived columns.
4. Confirm the product/variant **row structure** (how a variant row
   references its product).
5. Record **examples only where actually present** in the workbook —
   none are invented.
6. Record the numeric format of price cells (must be numeric Toman,
   not formatted text).
7. Record the result in the task-12 outcome and treat it as the
   authoritative mapping thereafter.

### C) Validation pipeline (deterministic order)

1. Workbook/schema validation (structure, readable numeric cells).
2. Row-structure validation (product vs variant rows; parent
   references).
3. Required-field validation (per the contract above; D-021 minimums).
4. Identifier validation (Product ID format/charset; no AI issuance).
5. SKU validation (D-014: charset, suffix axes = active axes in Color
   → Size order; uniqueness).
6. Vocabulary resolution (exact alias matching, active terms only,
   D-019).
7. Size-family resolution (declared family; no auto-conversion,
   D-020).
8. Variant-combination validation (duplicate active-axis combinations
   rejected, D-014 rule 11/D-018 rule 5).
9. Price validation (numeric Toman; D-024/D-025 rules).
10. Provenance preparation (IMPORTED records, D-026).
11. Duplicate/idempotency checks (D-017 identifier level; D-027 event
    level for the run).
12. Dry-run report (no writes).
13. **Human promotion** (explicit; AI may summarize/suggest, never
    promote).
14. Write (single deterministic application of the promoted result).

No AI decision occurs silently inside validation; every step is
deterministic and logged.

### D) Error classes (every error actionable; no auto-correction)

| Class | Deterministic handling |
| --- | --- |
| Missing required field | Row rejected at step 3; human supplies the value; never guessed (D-021) |
| Missing optional field | `NOT_PROVIDED`; row proceeds (RULES §8) |
| Unknown value | `UNKNOWN` preserved; surfaced to review; not auto-blocking (D-021 rule 5) |
| Invalid value (structure/business rule) | Rejected with row/column error; never auto-corrected or clamped (D-028 rule 13) |
| Duplicate in workbook or vs existing data | Affected rows rejected; nothing silently merged (D-028 rule 14) |
| Conflicting existing record (re-import) | Flagged for human review; never a silent overwrite (D-017) |
| Unresolved vocabulary value | Raw value retained on the row; routed to human review queue; never auto-added to the registry (D-019/D-028 rule 9) |
| Unresolved size value | Retained; human-reviewed; never auto-converted (D-020) |
| Invalid SKU | Rejected; corrected by human or re-derived by approved tooling after confirmation; never renamed in place (D-014 rule 10) |
| Invalid price | Rejected (D-024/D-025 validation); never clamped |
| Invalid lifecycle/publication state value | Rejected; import never sets `active`/`published` (D-022/D-023) |
| Invalid variant combination | Rejected (duplicate active-axis combination, D-018 rule 5) |

### E) Dry-run, partial failure, re-import

- **Dry-run:** validates everything, writes nothing, produces a
  deterministic report: errors, warnings, and the records that would
  be **created / updated (no-op or flagged) / skipped /
  rejected**. Only an explicit human promotes a dry-run to an actual
  import (D-028 rules 18–19).
- **Partial failure:** a failed actual import writes nothing (D-028
  rule 20). Atomicity is a **logical requirement**; the physical
  transaction mechanism is implementation-deferred (DATA_MODEL §13.8).
- **Re-import matrix (deterministic; never silently merged):**

| Scenario | Behavior |
| --- | --- |
| Identical workbook / repeated event | Event skipped and logged (D-027) |
| Same identifiers + same values | Identifier-level no-op (D-017) |
| Same identifiers + changed values | Flagged for human review; never a silent overwrite (D-017) |
| Duplicate SKU (within workbook or vs existing) | Rows rejected as data-integrity errors (RULES §10, D-028 rule 14) |
| Duplicate active-axis combination | Rows rejected (D-014 rule 11) |
| Changed immutable identifier (attempted Product ID / Variant ID rename) | Rejected — identifiers are immutable and never reused (D-017); a genuinely new record gets a new identifier |
| Attempted SKU rename | Rejected — SKU is frozen at creation (D-014 rule 10); deactivate + recreate instead |

## Task 13 — Phase 2 final review (2026-09-12)

Full audit of D-014–D-030 against the consolidated model (DATA_MODEL
§13) and this specification. Result: **PASS — no contradictions; no
new business rules invented; all open owner gates preserved.** Key
verifications: Product ID ≠ Variant ID ≠ SKU (§13.3); AI never assigns
identifiers, never creates vocabulary terms, never assigns size
codes, never executes lifecycle/import transitions (§13.7); no fuzzy
or confidence-based matching anywhere (all occurrences are
prohibitions); UNKNOWN ≠ NOT_PROVIDED ≠ INVALID (§13.4); D-024/D-025
price precedence incl. variant-sale fallback intact; publication
requires a resolvable effective price; provenance append-only; event
idempotency ≠ identifier idempotency (§13.5); Excel never a Source of
Truth and never writes without human promotion; failed import writes
nothing; no inventory/order model, no pricing engine, no new
lifecycle states, no concrete vocabulary values, no concrete size
mappings. Remaining open items are exactly the owner-gated set below
— none closed.

## Remaining open decisions

All remaining Phase 2 decisions are **OPEN** (D-016 and the
still-open items in the `DECISIONS.md` open-decision register — the
register is the authoritative list); none may be resolved silently:

- Concrete controlled-vocabulary registry v1 values (colors, sizes,
  categories) — D-016.C (structure approved via D-029; values
  owner-supplied)
- Concrete size-code mappings (O/I/L-safe) — per D-020 + D-030;
  owner-supplied; concrete size-family values also owner-supplied
- Inventory design constraints (already-approved rules remain: WooCommerce
  SoT, verified, idempotent, auditable, AI never estimates) — D-016.I
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
7. Define price/discount model — resolved: D-024 **Approved**
   (three-field model, deterministic effective price) and D-025
   **Approved** (sale-price discounts, no engine).
8. Define provenance mechanism — resolved: D-026 **Approved** (per-
   value provenance tuple; append-only; storage deferred).
9. Define import idempotency policy — resolved: D-027 **Approved**
   (event-level, (source, event ID) key; complements D-017).
10. Decide Excel import scope — resolved: D-028 **Approved** (input-
    only contract over semantic fields; dry-run first; human-approved
    exceptions; physical sheet/column mapping confirmed at the
    specification task; template decision folds into task 12).
11. Consolidate the logical data model.
12. Produce Excel import specification/template if approved.
13. Perform Phase 2 final review.
14. Commit Phase 2 foundation only after human approval.

## Exit criteria

- [ ] All remaining D-016 items resolved or explicitly deferred with
      owner approval
- [ ] Logical data model consolidated in `DATA_MODEL.md`
- [ ] Controlled-vocabulary registry v1 defined (if approved in scope)
- [ ] Excel import specification complete (contract per D-028;
      physical sheet/column mapping confirmed against the owner's
      workbook; template produced if approved in task 12)
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
  D-021 (Approved), D-022/D-023 (Approved), D-024–D-030 (Approved;
  D-029 structure + D-030 governance with concrete values/mappings
  open), D-016 (Open)
- `DATA_MODEL.md` — §3.1/§3.2 (status state machines), §6.1–§6.4
  (taxonomy governance, size system, registry v1, Excel import), §8
  (Pricing), §8a (Provenance), §8b (Event idempotency), §9 (SKU),
  §9.2 (Identifiers)

# DECISIONS

Decision log for the AI-First Online Business Engine.

Purpose: every architectural and business-relevant decision is recorded
here with its status and source, so that nothing is ever decided
silently (PROJECT_RULES §4). The human owner has final authority over
major decisions (PROJECT_RULES §3).

## Conventions

- IDs are sequential: `D-001`, `D-002`, …
- Status values: `Approved` | `Open` | `Superseded`.
- **Approved** = decided in/through the approved planning documents or
  by the human owner. **Open** = not yet decided; the placeholder does
  not count as a decision.
- Sources reference `MASTER_PLAN.md` / `PROJECT_RULES.md` sections.
- Major architecture changes follow STOP → EXPLAIN → APPROVAL and add a
  new row here.

## Decision index

| ID | Decision | Status |
| --- | --- | --- |
| D-001 | Reusable AI-first engine direction | Approved |
| D-002 | Initial business scope | Approved |
| D-003 | WooCommerce = ecommerce Source of Truth | Approved |
| D-004 | n8n = automation/orchestration layer | Approved |
| D-005 | Notion = Business Operating System (non-transactional) | Approved |
| D-006 | Excel = import/cleanup tool only | Approved |
| D-007 | Freebuff = development/custom-tool layer | Approved |
| D-008 | AI Runtime = API-based AI services within autonomy tiers | Approved |
| D-009 | Instagram = initial acquisition/communication channel | Approved |
| D-010 | Currency: numeric Iranian Toman | Approved |
| D-011 | Provenance and missing-data states | Approved |
| D-012 | Integration preference + provider boundaries | Approved |
| D-013 | Documentation set and environment direction | Approved |
| D-014 | Final SKU convention | **Approved** |
| D-015 | Product ID / Variant ID / SKU separation | Approved |
| D-016 | Phase 2 open-decision register | Open |
| D-017 | Product/Variant identifier policy | **Approved** |
| D-018 | Variant-defining attributes | **Approved** |
| D-019 | Controlled-vocabulary governance | **Approved** (registry v1 contents open) |
| D-020 | Size-system policy | **Approved** (size-code gate open) |
| D-021 | Required-field policy | **Approved** |
| D-022 | Product status state machine | **Approved** |
| D-023 | Publication status state machine | **Approved** |
| D-024 | Price model | **Approved** |
| D-025 | Discount model | **Approved** |
| D-026 | Provenance mechanism | **Approved** |
| D-027 | Event-level idempotency | **Approved** |

## D-001 — Reusable AI-first engine direction

- **Status:** Approved
- **Decision:** Build a reusable, AI-first Online Business Engine:
  correctness, security, simplicity, low cost, modularity, portability,
  observability, automation. Build on existing mature technology; do
  not rebuild mature systems without a strong reason.
- **Rationale:** The goal is the most reliable business system that
  uses AI where AI provides real value — not the most complicated AI
  system.
- **Source:** MASTER_PLAN §1–§2, §17; PROJECT_RULES §1, §5, §44

## D-002 — Initial business scope

- **Status:** Approved
- **Decision:** First implementation is an Iranian online clothing
  business (women's and men's clothing). Market: Iran; language:
  Persian/Farsi; UI: RTL-first; currency: Iranian Toman; product count
  variable and scalable.
- **Rationale:** Concrete first business for the engine; architecture
  must be reusable for other businesses with minimal change.
- **Source:** MASTER_PLAN §1

## D-003 — WooCommerce = ecommerce Source of Truth

- **Status:** Approved
- **Decision:** WooCommerce is the transactional Source of Truth for
  products, variants, SKUs, prices, inventory, orders, customers,
  coupons, and store state. Notion and Excel must not replace it.
- **Rationale:** Mature ecommerce system; transactional integrity,
  inventory, orders, and payments are its core competence.
- **Source:** MASTER_PLAN §3–§4, §7–§8; PROJECT_RULES §5, §12–§13

## D-004 — n8n = automation/orchestration layer

- **Status:** Approved
- **Decision:** n8n is the automation/orchestration layer: webhooks,
  scheduled jobs, API integration, transformations, AI orchestration,
  retries, idempotency, errors, notifications. Every workflow defines
  name, purpose, trigger, inputs, outputs, error handling, retry
  strategy, idempotency, logging, credentials, and required approvals.
  Prefer small, composable workflows without hidden side effects.
- **Rationale:** Mature orchestration tool; avoids custom glue code.
- **Source:** MASTER_PLAN §3–§4; PROJECT_RULES §5, §14

## D-005 — Notion = Business Operating System (non-transactional)

- **Status:** Approved
- **Decision:** Notion is the Business Operating System: dashboards,
  SOPs, documentation, knowledge, content calendar, ideas, review
  queues, reports. It is never the source of truth for inventory,
  payment, order state, stock, or critical product availability.
- **Rationale:** Knowledge/management strength; not a transactional
  database.
- **Source:** MASTER_PLAN §3–§4, §8; PROJECT_RULES §13

## D-006 — Excel = import/cleanup tool only

- **Status:** Approved
- **Decision:** Excel (incl. the Product Master Excel structure) is an
  import/management and cleanup tool, not the permanent production
  database and never a source of truth.
- **Rationale:** Practical for initial data entry and cleaning; wrong
  tool for transactional truth.
- **Source:** PROJECT_RULES §13; MASTER_PLAN §16

## D-007 — Freebuff = development/custom-tool layer

- **Status:** Approved
- **Decision:** Freebuff is the development and custom application
  layer: internal tools, dashboards, utilities, adapters, tests,
  refactoring, custom interfaces. It does not replace WooCommerce or
  n8n by default.
- **Rationale:** Custom development only with a clear reason (RULES
  §36); keeps the build focus on mature systems.
- **Source:** MASTER_PLAN §3–§4; PROJECT_RULES §17, §36

## D-008 — AI Runtime = API-based AI services within autonomy tiers

- **Status:** Approved
- **Decision:** Runtime AI uses API-based AI services for
  classification, extraction, content drafts, customer/sales
  assistance, analysis, and recommendations — restricted to the
  Green/Yellow/Red autonomy tiers, with schema validation of structured
  output before it affects business systems. AI never invents facts and
  never estimates actual stock.
- **Rationale:** AI value with hard integrity boundaries.
- **Source:** MASTER_PLAN §3–§5, §9; PROJECT_RULES §6–§7, §32–§33
- **Open sub-decision:** Which AI provider(s) — Phase 7.

## D-009 — Instagram = initial acquisition/communication channel

- **Status:** Approved
- **Decision:** Instagram is the initial customer acquisition and
  communication channel. Official Meta/Instagram APIs and supported
  integrations are preferred; unofficial browser automation only when
  justified and reviewed.
- **Rationale:** Market reality of the target audience; official APIs
  are the reliable, sustainable path.
- **Source:** MASTER_PLAN §1, §3–§4; PROJECT_RULES §15, §29
- **Open sub-decision:** Exact API surface and account setup — Phase 9.

## D-010 — Currency: numeric Iranian Toman

- **Status:** Approved
- **Decision:** All prices stored numerically in Iranian Toman (e.g.
  `590000`). Formatted strings (`590,000 تومان`) never as the primary
  stored value; currency represented separately when necessary.
  Production prices never changed automatically without authorization;
  AI may only recommend.
- **Source:** MASTER_PLAN §6; PROJECT_RULES §11

## D-011 — Provenance and missing-data states

- **Status:** Approved
- **Decision:** Missing data is `UNKNOWN` or `NOT_PROVIDED`. AI output
  provenance is `AI_GENERATED` / `HUMAN_REVIEWED` / `HUMAN_VERIFIED`.
  AI inference is never presented as verified fact; product attributes
  are optional unless explicitly required; incomplete products are
  valid.
- **Source:** MASTER_PLAN §5; PROJECT_RULES §6–§8

## D-012 — Integration preference + provider boundaries

- **Status:** Approved
- **Decision:** Integration preference: official API → mature
  supported integration → reliable open-source adapter → custom adapter
  → browser automation (justified and reviewed only). Providers sit
  behind replaceable boundaries: `AIProvider`, `PaymentProvider`,
  `ShippingProvider`, `InstagramProvider`.
- **Source:** PROJECT_RULES §15, §34–§35

## D-013 — Documentation set and environment direction

- **Status:** Approved
- **Decision:** Project contains `MASTER_PLAN.md`, `PROJECT_RULES.md`,
  `README.md`, `ARCHITECTURE.md`, `DATA_MODEL.md`, `SECURITY.md`,
  `DECISIONS.md`, `TODO.md`, `docs/`. Environments follow Development →
  Testing/Staging → Production; high-risk changes additionally pass
  Review → Approval. Documentation is updated whenever architecture,
  data ownership, APIs, security, deployment, workflows, or business
  rules change.
- **Source:** MASTER_PLAN §11–§12; PROJECT_RULES §18, §37, §43

## D-014 — Final SKU convention

- **Status:** **Approved** (2026-09-11, human owner)
- **Decision:** Candidate 1 + safety valve, with these final rules:
  1. **SKU convention:** product code + canonical attribute suffix.
  2. **Product code:** five-digit numeric sequence from the beginning —
     `P00001`, `P00002`, `P00003`, … The four-digit `P0001` form is
     explicitly NOT the final standard.
  3. **Variant SKU:** product code + canonical attribute suffix,
     e.g. `P00001-BLK-M`.
  4. **Simple product without variants:** SKU = product code,
     e.g. `P00002`.
  5. **Character set:** uppercase Latin ASCII only.
  6. **Attribute codes:** color/size suffix codes come only from
     controlled vocabularies; humans and AI must not invent arbitrary
     attribute codes.
  7. **Confusable characters:** attribute-code registries avoid
     visually confusable letters such as O, I, L. Product numbering
     remains numeric (`P00001`, `P00002`, …).
  8. **Structured attributes remain authoritative:** color, size,
     category, brand, and all other attributes are stored as structured
     data outside the SKU; the suffix is only a compact human/warehouse
     readability aid.
  9. **Category and brand** are NEVER encoded into the SKU.
  10. **SKU immutability:** frozen at creation. If a SKU was created
      incorrectly: do NOT rename the existing SKU; deactivate the
      incorrect product/variant; create a new correct product/variant
      with a new identifier/SKU.
  11. **Duplicate variant combination:** the same color + size
      combination must not exist twice under one product; duplicates
      are data errors and must be rejected. A `-2` suffix may exist
      only as an emergency safety valve for an exceptional collision/
      disambiguation case — never as a normal variant-numbering
      mechanism.
  12. **SKU issuance:** product codes are assigned by humans or
      approved deterministic tooling. AI must NEVER autonomously assign
      or invent a SKU.
  13. **Barcode:** SKU and barcode/EAN are separate concepts; the SKU
      must NOT be used as the barcode; barcode/EAN has its own field
      and lifecycle.
  14. **Stability:** SKU remains stable and is never silently reused
      for another product/variant.
  15. **Width/scalability:** five-digit numbering is the initial
      standard; business logic must not depend on digit count —
      identifiers are opaque and must not be parsed for meaning.
- **Rationale:** Deterministic and typeable for humans (Excel entry,
  picking, support), automation-safe for n8n/WooCommerce/Excel,
  category-agnostic for reuse across businesses; structured attributes
  stay the single source of truth so the SKU never becomes a second
  one; the AI-invention risk is closed by the controlled-vocabulary
  rule (6) and the AI-never-assigns rule (12).
- **Source:** MASTER_PLAN §4; PROJECT_RULES §10; approved Phase 2
  Design Review (Candidate 1 + safety valve); human owner approval of
  the final convention (2026-09-11).
- **Approval gate:** Satisfied — this resolves the gate "must be
  approved before inventory automation."

## D-015 — Product ID / Variant ID / SKU separation

- **Status:** **Approved** (2026-09-11, human owner)
- **Decision:** Three separate concepts, never conflated:
  - **Product ID** — stable business-facing product identifier;
    human-readable (`P00001`); stable; category-agnostic; not derived
    from the product name.
  - **Variant ID** — separate stable internal identifier for a
    variant; must NOT be the SKU; opaque and system-safe. The exact
    physical representation/generation mechanism remains a later
    implementation decision (no UUID or database-specific ID format is
    chosen now).
  - **SKU** — business/inventory identifier; human-readable; used for
    WooCommerce/inventory/Excel/n8n references (e.g. `P00001-BLK-M`);
    immutable after creation (D-014).
  The SKU is NOT the internal database identity of a variant.
- **Rationale:** Decouples stable identity (which must never change)
  from the business-readable SKU (which encodes readability, not
  identity) and from technical IDs owned by WooCommerce; keeps the
  deactivate-and-recreate correction path (D-014 rule 10) safe.
- **Source:** Approved Phase 2 Design Review (identifier policy);
  MASTER_PLAN §4; PROJECT_RULES §9–§10; human owner approval
  (2026-09-11).

## D-016 — Phase 2 open-decision register

- **Status:** **Open** — this entry records; it approves nothing.
  Every item below remains open and must not be treated as decided.
- **Decision:** Record the Phase 2 decision surface explicitly:
  - A. **Variant-defining attributes** — RESOLVED: D-018 **Approved**
    (2026-09-11, exactly {Color, Size}, per-axis applicability).
  - B. **Minimum required product fields** — RESOLVED: D-021
    **Approved** (2026-09-11, creation/publication minimums).
  - C. **Controlled vocabularies** — PARTIALLY RESOLVED: governance
    architecture approved via D-019 (2026-09-11); concrete registry v1
    contents remain OPEN and owner-gated. Registries will eventually
    include at least colors, sizes, categories, and other controlled
    fields as needed; final values are not invented.
  - D. **Size system** — PARTIALLY RESOLVED: D-020 multi-family
    architecture approved (2026-09-11); the O/I/L-safe size-code
    convention and concrete family values remain OPEN (candidates:
    letter sizes, Iranian/numeric sizes, or other business-specific
    sizing; not chosen).
  - E. **Product status state machine** — OPEN; candidate states
    `draft` / `active` / `archived` are documented only; no WooCommerce
    mapping yet.
  - F. **Publication status** — OPEN; no unnecessary states unless
    justified.
  - G. **Price model** — OPEN; the final decision must define product
    default price, optional variant override, and sale-price behavior;
    not implemented.
  - H. **Discount model** — OPEN; a sale-price model is the preferred
    direction but is NOT approved.
  - I. **Inventory** — OPEN for Phase 2 design. Already-approved
    constraints remain in force (D-003, RULES §12): WooCommerce is the
    transactional Source of Truth; inventory must be verified;
    mutations must be idempotent and auditable; AI must never estimate
    stock. No inventory implementation in Phase 2.
  - J. **Provenance mechanism** — OPEN. The approved states remain
    UNKNOWN, NOT_PROVIDED, AI_GENERATED, HUMAN_REVIEWED,
    HUMAN_VERIFIED (D-011); the physical storage mechanism is not
    chosen yet.
  - K. **Import idempotency** — OPEN; future Excel/import design must
    have a deterministic idempotency strategy.
  - L. **Excel import scope** — OPEN; Phase 2 must still decide:
    specification only, or specification + reusable Excel template.
  - M. **SEO slug language** — OPEN/deferred; no URL slug
    implementation now.
- **Rationale:** Prevents silent decisions (PROJECT_RULES §4) and gives
  Phase 2 an explicit, ordered decision backlog.
- **Source:** Approved Phase 2 Design Review; human owner instruction
  to record as open (2026-09-11).

## D-017 — Product/Variant identifier policy

- **Status:** **Approved** (2026-09-11, human owner)
- **Decision:** The identifier policy (IP), finalizing Phase 2 Task 1:
  1. **Product ID canonical name:** Product ID is the canonical name
     for the D-014 product code — one identifier, not two concepts.
  2. **Product ID format:** `P` + five-digit zero-padded sequence —
     `P00001`, `P00002`, … (uppercase Latin ASCII; width carries no
     meaning, D-014 rule 15).
  3. **Product ID issuance/immutability:** immutable, never reused;
     issued only by humans or approved deterministic tooling.
  4. **Variant ID separation:** a separate internal identity, distinct
     from Product ID and SKU (extends D-015).
  5. **Variant ID format:** opaque; **UUIDv4** in canonical lowercase
     hyphenated form.
  6. **Variant ID issuance/immutability:** immutable, never reused;
     issued only by approved deterministic tooling.
  7. **AI authority:** AI must never issue, assign, invent, or
     transform Product IDs, Variant IDs, or SKUs (extends D-014
     rule 12 to all identifiers).
  8. **SKU:** remains governed by all approved D-014 rules; the SKU is
     never the internal identity of a variant (D-015).
  9. **Permanently distinct concepts:** Product ID, Variant ID, and
     SKU remain separate forever.
  10. **Import idempotency:** identifier-based import idempotency is
      approved (products keyed by Product ID; variants by Variant ID,
      SKU fallback where Variant ID is absent; identical re-import =
      no-op; conflicting payload = flagged for human review, never a
      silent overwrite; new rows receive tool-issued IDs, written back
      and logged). Event-level idempotency (webhooks/retries/
      scheduled) remains open under D-016.K.
- **Complementary policy rules** (approved with the proposal):
  uniqueness domain — Product IDs and SKUs share one namespace
  (structurally collision-free: bare `P#####` vs suffixed variant
  SKUs); lifecycle — creation order Product ID → Variant ID → SKU,
  deactivate + recreate for suffix-invalidating corrections, no
  renaming/recycling, history retains original identifiers;
  duplicate color+size (and the final variant-defining set once
  D-016.A is approved) rejected as data errors; the `-2` valve is
  emergency-only with human approval; import batches are
  pre-validated as a whole.
- **Resolves:** DECISIONS register item 14 (Variant ID generation
  mechanism). Partially informs item 21 (D-016.K): identifier-based
  keying is settled; event-level idempotency remains open.
- **Alternatives considered:** sequential `V#####` Variant IDs
  (rejected — second quasi-readable code, central counter, violates
  opacity); UUIDv7/ULID (acceptable alternative — compatible swap at
  implementation); derived composite IDs (rejected — violates D-015,
  collides with deactivate+recreate); WooCommerce internal ID as
  Variant ID (rejected — platform-owned; mapping is Phase 3 work).
- **Rationale:** Zero-coordination issuance and universal library
  support for internal identity; readability stays where it belongs
  (SKU); closes the AI-invention surface for all identifiers; keeps
  the D-014 rule 10 correction path safe.
- **Source:** Approved Phase 2 Task 1 Identifier Policy proposal;
  D-014, D-015; MASTER_PLAN §4; PROJECT_RULES §9–§10, §25, §32;
  human owner approval (2026-09-11).

## D-018 — Variant-defining attributes

- **Status:** **Approved** (2026-09-11, human owner)
- **Decision:** The initial variant-defining set is exactly
  {Color, Size}, with per-axis applicability:
  1. **Variant-defining set:** Color and Size only. No other attribute
     defines variants in the initial clothing system.
  2. **Per-axis applicability:** an axis is **active** for a product
     only when it genuinely varies across sellable variants; a
     non-varying axis is omitted, never guessed (an axis that does not
     vary is simply inactive — `UNKNOWN`/`NOT_PROVIDED` values never
     define variants).
  3. **Simple product:** zero active axes; SKU = Product ID (D-014
     rule 4).
  4. **Separate products:** products differing only by product-level
     attributes (material, cut/fit, style, …) are separate products,
     never variants of one product.
  5. **Duplicate prevention:** the D-014 rule 11 duplicate check runs
     over the product's **active** axes only (a color-only product
     rejects duplicate colors; a color+size product rejects duplicate
     color+size combinations).
  6. **SKU axes (clarification of D-014 rules 3/11, approved):** the
     SKU suffix contains exactly the active variant-defining axes in
     canonical order **Color, then Size** — `P00001` (simple),
     `P00001-BLK` (color-only), `P00001-BLK-M` (color + size).
  7. **No new axes in Phase 2:** inseam/jeans length remains deferred;
     adding or removing an axis is a major decision (STOP → EXPLAIN →
     APPROVAL) because it changes SKU shape and duplicate rules.
     "Variant-defining" is a registry-level flag per vocabulary (see
     D-019).
- **Rationale:** Matches real clothing sellability (color and size are
  the only axes that create independently stocked/sold items), avoids
  artificial variants (RULES §9) and guessed values (RULES §8), keeps
  SKU suffixes short and duplicate checks well-defined.
- **Source:** Phase 2 Task 2 design; MASTER_PLAN §4; PROJECT_RULES
  §8–§9; D-014 rules 3/4/11; human owner approval (2026-09-11).

## D-019 — Controlled-vocabulary governance

- **Status:** **Approved** (governance architecture) — **registry v1
  concrete contents remain OPEN** and owner-gated.
- **Decision:** Each controlled attribute has a closed registry of
  **Attribute Terms**, governed as follows:
  1. **Term fields:** attribute (owning vocabulary); canonical code
     (only where applicable — variant-defining vocabularies bearing
     SKU codes); canonical value/slug; display label; aliases; status
     (active/deprecated); provenance (D-011 states); created/updated
     timestamps; notes.
  2. **Human authority:** the human owner or delegated staff create
     terms via approved tooling, logged and auditable. Terms for
     **variant-defining** vocabularies (SKU-code-bearing) additionally
     require owner approval.
  3. **No deletion:** terms are never deleted — deprecation only;
     deprecated terms remain resolvable (protects frozen SKUs, D-014
     rules 10/14).
  4. **AI authority:** AI may **propose** a term (with evidence) into
     a human review queue as `AI_GENERATED`; AI may never create,
     activate, modify, or delete a term. AI filling attribute values
     may reference only existing **active** terms.
  5. **Normalization:** exact alias matching after basic
     case/whitespace normalization. **No fuzzy matching; no
     similarity-based guessing.**
  6. **Unmapped values:** unmapped provided values are never discarded
     and never auto-mapped — the raw value is retained and sent for
     human review. The vocabulary never forces a guess; missing values
     remain `UNKNOWN`/`NOT_PROVIDED` (D-011).
  7. **No concrete lists:** no color/size/material/brand values are
     created by this decision. Registry v1 contents are owner-supplied
     and approved separately.
- **Resolves:** the governance architecture of D-016.C. The concrete
  registry v1 value lists remain **open** (see register item 3).
- **Source:** Phase 2 Task 4 design; MASTER_PLAN §4; PROJECT_RULES
  §6–§8, §32–§33; D-011, D-014 rule 6, D-017; human owner approval
  (2026-09-11).

## D-020 — Size-system policy

- **Status:** **Approved** (architecture) — **Size-code convention
  (O/I/L-safe) remains an explicit OPEN owner approval gate.**
- **Decision:** Multi-family size architecture:
  1. **Size is a controlled Attribute Term** (D-019 model) with a
     `size family` classification and optional sort order.
  2. **Families:** alpha/letter; numeric; pants/waist; shoe;
     future/brand-specific families when genuinely required. No single
     universal size system is forced.
  3. **Level split:** the size **family/system context belongs to the
     product-level configuration** (a product declares which family it
     uses); the **size term belongs to the variant**.
  4. **Canonical vs display:** the canonical size term (registry
     identity + SKU code) and the customer-facing display value remain
     distinguishable. Display labels may remain conventional (L, XL),
     regardless of the canonical code.
  5. **Measurements:** size measurements (cm/inch tables) are
     reference data attached to terms or products — never invented;
     `NOT_PROVIDED` when absent.
  6. **Brand-specific sizing:** uses product/brand measurement and
     display context rather than automatically creating a separate
     vocabulary per brand; a genuinely different sellable fit is a
     different product (D-018 rule 4).
  7. **Cross-family conversion:** human-curated equivalence only; AI
     must never invent conversions. Optional, owner-gated.
  8. **Canonicalization:** size inputs resolve through the Size
     registry's exact-match normalization (D-019 rule 5) to one active
     term within the product's declared family; values outside the
     family or unmapped are retained and human-reviewed, never
     auto-converted.
  9. **SKU codes must avoid O/I/L (D-014 rule 7):** no exception is
     created. Display labels stay conventional (L, XL), but SKU codes
     use a separate safe canonical code. A deterministic Size-code
     convention avoiding O/I/L is to be proposed and approved as a
     separate owner gate — mappings are NOT finalized in this
     decision.
- **Rationale:** Respects real-world clothing sizing diversity without
  forcing one system; keeps SKUs rule-compliant and unambiguous; keeps
  identity (term) separate from display.
- **Source:** Phase 2 Task 5 design; MASTER_PLAN §4; PROJECT_RULES
  §6, §8; D-014 rule 7, D-018, D-019; human owner approval
  (2026-09-11).
- **Open sub-gate:** Size-code convention avoiding O/I/L (new owner
  approval required before any size-code mapping is finalized).

## D-021 — Required-field policy

- **Status:** **Approved** (2026-09-11, human owner)
- **Decision:** Minimal creation minimums; a real publication minimum;
  verified-data-only inventory; strictly bounded AI enrichment.
  1. **Product creation minimum:** Product ID; Name; Product status
     (default `draft`); Created date. Nothing else is required to
     create a product.
  2. **Variant creation minimum:** Variant ID; Product ID (parent);
     SKU; all **active** variant-defining attributes (D-018); Variant
     status.
  3. **Publication minimum** (before public visibility): Name; Main
     category; resolvable price (mechanism per D-016.G, open); at
     least one media image; valid publication status (values per
     D-016.F, open); all variants satisfy the variant creation
     minimum. **Description and short description are NOT publication
     blockers.**
  4. **Inventory:** no inventory field is required at creation; stock
     is verified data only; missing stock remains `NOT_PROVIDED`; AI
     never estimates stock (RULES §12, D-016.I constraints).
  5. **UNKNOWN handling:** `UNKNOWN` does not automatically block
     publication — it is surfaced to human review. A future
     field-specific safety rule may explicitly block publication, but
     none is created now.
  6. **AI enrichment (Yellow tier, provenance-tagged):** AI may draft
     description, short description, SEO title, SEO description,
     keywords, and category/attribute suggestions (human review before
     customer/production exposure). AI may NOT create identifiers,
     prices, discounts, stock, vocabulary terms, shipping/payment/
     order facts, or guessed attribute values.
  7. **Missing required fields:** a required field missing at input
     blocks only the relevant lifecycle transition (e.g., publish);
     it never receives a guessed value (RULES §8).
- **Rationale:** A field being useful does not make it required;
  blocking capture over optional data creates junk data and guesses;
  data-quality burden is enforced at the moment it matters
  (publication), without inventing values.
- **Source:** Phase 2 Task 3 design; MASTER_PLAN §4–§5; PROJECT_RULES
  §6–§8, §12, §32–§33; D-011, D-017, D-018; human owner approval
  (2026-09-11).
- **Open dependencies:** price mechanism (D-016.G), publication status
  values (D-016.F) — referenced but not resolved here.

## D-022 — Product status state machine

- **Status:** **Approved** (2026-09-12, human owner)
- **Decision:** Minimal, deterministic product lifecycle state
  machine; **Product status is a separate concept from publication
  status (D-023) and is never replaced by it.**
  1. **States (exactly three):**
     - `draft` — exists, work-in-progress. Incomplete products are
       valid here (RULES §8); not structurally checked; never
       sellable; never published.
     - `active` — usable product. Entry = human approval of the
       draft + all D-021 publication checks passing. Not directly
       customer-visible/sellable by itself (that is publication,
       D-023).
     - `archived` — deactivated/no longer offered. Not sellable;
       nothing is deleted; history (identifiers, SKU, provenance) is
       fully preserved.
  2. **Allowed transitions (complete set):** `draft → active`;
     `active → archived`; `archived → draft`; `active → draft`.
  3. **Forbidden transitions:** `draft → archived` (no side-step —
     review/deactivate first via `active`); `archived → active`
     (never; no direct reactivation).
  4. **Transition authority:**
     - `draft → active`: human action, OR approved deterministic
       tooling only when all D-021 publication checks pass
       (deterministic, governed).
     - `active → draft`, `active → archived`: human action; approved
       deterministic tooling may execute only when explicitly
       instructed by a human for that specific product.
     - `archived → draft`: human-only (explicit restore decision).
  5. **AI authority:** AI may **suggest/prepare** a transition (e.g.
     mark a product ready for review) — suggestion only, logged with
     provenance; AI may **never execute** any lifecycle transition.
     AI may never move a product to or out of `archived`.
  6. **No new states:** no `deleted`, no `pending-review` state on the
     product (review is publication's `in_review`, D-023). Rejection
     of a review candidate = product returns to `draft` (via the
     `active → draft` transition) and publication returns to
     `unpublished`.
  7. **Variant behavior on product transitions:** the D-021 variant
     creation minimum stays intact. `draft → active`: every variant
     must satisfy the variant creation minimum (transition blocked
     otherwise). `active → archived`: the product's variants stop
     being sellable together with the product — no per-variant
     archival cascade is created. `archived → draft` / `active →
     draft` (edits): variant states mirror the product; variants are
     never left sellable while their product is `draft` or
     `archived`.
  8. **Audit/provenance:** every transition is logged (who/what,
     when, from → to, reason where given; RULES §27). AI-originated
     suggestions carry `AI_GENERATED` provenance; human decisions
     are `HUMAN_*`; provenance is never overwritten by a
     transition.
- **Resolves:** D-016.E / register item 16.
- **Rationale:** Smallest state set that covers the project's own
  lifecycle needs (draft/active/archived, per D-016.E candidates);
  keeps sellability where it belongs (publication, D-023); preserves
  human authority and auditability per RULES §3, §27, §32.
- **Source:** D-016.E candidates; D-021; MASTER_PLAN §4; PROJECT_RULES
  §3, §27, §32; human owner approval (2026-09-12).

## D-023 — Publication status state machine

- **Status:** **Approved** (2026-09-12, human owner)
- **Decision:** Minimal publication-visibility state machine,
  **independent of product status (D-022); publication status is
  never a substitute for product status.**
  1. **States (exactly four):**
     - `unpublished` — default at creation; not visible.
     - `in_review` — being prepared/checked against the D-021
       publication minimum.
     - `published` — publicly visible/sellable.
     - `withdrawn` — intentionally unpublished after having been
       published.
  2. **Allowed transitions (complete set):** `unpublished →
     in_review`; `in_review → unpublished` (rejection/withdrawal
     from review); `in_review → published` (approval); `published →
     withdrawn` (intentional unpublish); `published → in_review`
     (re-review of a published product before a material change);
     `withdrawn → in_review` (re-publication preparation).
  3. **Forbidden transitions:** `unpublished → published` (no
     bypassing review); `withdrawn → published` (no direct
     re-publish — re-enter review).
  4. **Publication checks (gate for any `→ published` transition),
     exactly D-021:** Name; Main category; resolvable price; ≥1
     media image; valid publication status; all variants satisfy the
     variant creation minimum; product status must be `active`
     (D-022). **Description/short description are NOT blockers;
     `UNKNOWN` values are surfaced to human review and do not
     automatically block** (D-021); a future field-specific
     safety hard-block may be approved separately, none exists now.
     Inventory: verified-data-only; missing stock stays
     `NOT_PROVIDED`; AI never estimates stock.
  5. **Transition authority:**
     - `unpublished → in_review`: human action, OR approved
       deterministic tooling (checks-only, deterministic, governed).
     - `in_review → published`: **Red tier — explicit human
       approval**; approved deterministic tooling may execute only
       after that approval, with all checks passing.
     - `published → withdrawn`: **Red tier — explicit human
       approval** (deterministic tooling only on explicit human
       instruction).
     - `in_review → unpublished`, `published → in_review`,
       `withdrawn → in_review`: human action or approved
       deterministic tooling.
  6. **AI authority:** AI may prepare review submissions and
     suggest transitions (Yellow tier, provenance-tagged); AI may
     **never execute** publish or unpublish.
  7. **Audit/provenance:** every transition logged (RULES §27); AI
     suggestions carry `AI_GENERATED`; human approvals are `HUMAN_*`.
- **Resolves:** D-016.F / register item 17.
- **Rationale:** Smallest set covering not-published / being-reviewed
  / published / intentionally-unpublished without extra states;
  enforces D-021 minimums at the moment of visibility; keeps human
  authority over public exposure (Red tier per RULES §32).
- **Source:** D-016.F; D-021 publication minimum; D-022; MASTER_PLAN
  §4; PROJECT_RULES §32–§33; human owner approval (2026-09-12).

## D-024 — Price model

- **Status:** **Approved** (2026-09-12, human owner)
- **Decision:** Minimal three-field price model, currency per D-010
  (numeric Iranian Toman):
  1. **List price** (required): numeric Toman, stored as a number
     (never a formatted string). The reference/base price of a
     product.
  2. **Variant override** (optional): numeric Toman; required when a
     variant's price differs from the product list price.
  3. **Sale price** (optional): numeric Toman, plus optional `sale
     price validity end` (timestamp). A sale price may also be set at
     the variant level (optional variant-level sale override).
  4. **Effective/resolvable price** (deterministic): the effective
     sale price — the variant-level sale if set and valid, else the
     product-level sale if set and valid (the same precedence as
     prices, D-025 rule 2); else `variant override` if set; else
     `list price`.
  5. **Missing/unresolved price:** if no base price exists (list
     price absent and no override), the effective price is
     **unresolved** — it is never guessed, never invented (RULES §6,
     D-021). An unresolved price is surfaced for human attention and
     blocks publication (resolvable price is a publication minimum,
     D-021).
  6. **Conflict semantics:** there is no true conflict — precedence is
     fixed (sale → override → list). A sale price must be lower than
     the effective base price (override, else list); a sale price ≥
     the base price is a validation error.
  7. **Authoritative price at publication:** the effective price (rule
     4) is what publication requires to be resolvable; the effective
     price is what the storefront would sell at.
  8. **AI authority:** AI may *recommend* a price change (Yellow
     tier, RULES §11); AI may never create or change a price.
     Production price changes are Red tier (RULES §32).
  9. **History:** historical price changes are represented by an
     immutable price-change log (when changed, by whom, old value →
     new value, provenance of the change); current price fields hold
     only current values. Log details are implementation-deferred.
  10. **Currency/unit semantics:** numeric Toman only (D-010); no
      currency conversion logic in this model.
- **Resolves:** D-016.G / register item 18.
- **Rationale:** Smallest deterministic model that answers
  default/override/missing/conflict/publication questions without a
  pricing engine; keeps discount separation (D-025) and publication
  resolvability (D-021) intact; respects the Red-tier rule for price
  changes (RULES §11, §32).
- **Source:** MASTER_PLAN §4, §6; PROJECT_RULES §6, §11, §32; D-010,
  D-021; human owner approval (2026-09-12).

## D-025 — Discount model

- **Status:** **Approved** (2026-09-12, human owner)
- **Decision:** Sale-price-based discounts; no discount engine:
  1. **Representation:** a discount is *expressed* as an explicit
     **sale price** (D-024 field 3), never as a live percentage
     computed over the base price; the numeric base/list price field
     is never silently changed by a discount.
  2. **Scope:** discounts are set at product level or variant level,
     following the same precedence as prices (variant-level sale
     price overrides product-level).
  3. **Type:** fixed final price (Toman) only — no percentage field
     is required in the initial model (display percentages may be
     computed for presentation, never stored as the mechanism).
  4. **Validity:** optional `sale price validity end` (D-024); no
     start-date scheduling in the initial model (a future start
     timestamp may be added by owner approval if needed).
  5. **Active/inactive:** a sale price is active when set and valid;
     removing it (or expiry) falls back per rule 8's fixed order (the
     other sale level if valid, else the base price) — never a stored
     state change of the base price.
  6. **Invalid discounts:** a sale price that is ≥ the effective base
     price, or that would make the effective price zero or negative,
     is a validation error — rejected, never clamped.
  7. **Negative prices/over-100%:** impossible by construction (rule
     6); there is no percentage to exceed 100%.
  8. **Multiple discounts / precedence:** there is exactly one
     effective sale price per product/variant — the most specific
     valid one: variant-level sale if set and valid, else
     product-level sale if set and valid; when neither is set and
     valid, the item sells at its base price. No stacking; the
     precedence is exactly this fixed order.
  9. **AI authority:** AI may *suggest* a discount (Yellow tier); AI
     may never create, change, or execute a discount — production
     price-affecting changes are Red tier (RULES §6, §32).
  10. **Out of scope (future phases):** coupons, campaigns, loyalty,
      customer-specific pricing, promotional engines — not designed
      here.
- **Resolves:** D-016.H / register item 19 (sale-price direction now
  approved).
- **Rationale:** The preferred sale-price direction (D-016.H) made
  deterministic and minimal: one optional field + validity, fixed
  precedence, hard validation bounds; no engine, no coupons, no
  stacking; base price integrity preserved.
- **Source:** MASTER_PLAN §4, §6; PROJECT_RULES §6, §11, §32; D-010,
  D-024, D-021; human owner approval (2026-09-12).

## D-026 — Provenance mechanism

- **Status:** **Approved** (2026-09-12, human owner)
- **Decision:** Per-value provenance metadata (mechanism for the
  D-011 states), kept conceptual and implementation-agnostic:
  1. **Scope:** provenance attaches to important product data values
     (attributes, price fields, media, descriptions/SEO drafts,
     taxonomy references) — wherever origin matters.
  2. **Recorded per value:**
     - **Source type** — exactly one of: `HUMAN_ENTERED`,
       `SYSTEM_GENERATED`, `AI_GENERATED`, `IMPORTED`,
       `EXTERNAL_SYNC`.
     - **Actor/source identity** — which human/tool/system produced
       the value (no secrets stored).
     - **Timestamp** — when the value was produced.
     - **Review state** — the D-011 verification states
       (`AI_GENERATED` / `HUMAN_REVIEWED` / `HUMAN_VERIFIED`),
       where relevant.
     - **Source reference** (optional) — where available (import
       file/batch, external record reference).
     - **Original/source value** (optional) — the pre-normalization
       value, where normalization was applied.
  3. **No confidence scores:** none is justified by existing project
     documents; not added.
  4. **Immutability/auditability:** provenance records are append-only
     and immutable — a new provenance entry supersedes (never
     overwrites) an old one; history remains answerable.
  5. **AI-generated values remain distinguishable:** an AI-originated
     value carries `AI_GENERATED` source/review state until a human
     changes the review state (D-011); human review never erases the
     origin (source type stays `AI_GENERATED` while the review state
     may rise).
  6. **Imported values retain source provenance:** `IMPORTED` values
     record their source reference (e.g., import batch); normalization
     keeps the original value where relevant.
  7. **No secrets in provenance:** actor identity never includes
     credentials or secrets (RULES §16, §27).
  8. **Provenance vs audit history:** provenance answers "where did
     this value come from"; the event/audit history (RULES §27) is a
     separate concern. This decision defines provenance only — no
     audit-log system is designed here.
- **Resolves:** D-016.J / register item 20 (mechanism now defined;
  physical storage stays implementation-deferred).
- **Rationale:** D-011 fixed the *states*; this decision fixes the
  *record shape and rules* minimally — five source types, review
  states per D-011, append-only immutability, and the human/AI
  distinction preserved — without designing an audit-log system or
  choosing storage.
- **Source:** MASTER_PLAN §5; PROJECT_RULES §6–§7, §16, §27; D-011;
  human owner approval (2026-09-12).

## D-027 — Event-level idempotency

- **Status:** **Approved** (2026-09-12, human owner)
- **Decision:** Minimal event-idempotency model for repeated
  webhook/retry/scheduled events; **distinct from and complementary
  to the identifier-based import idempotency approved in D-017**:
  1. **Event/request identifier:** a stable source event ID; where
     the source supplies none, a deterministic hash of (operation
     type, target identifier, timestamp, payload) serves as the
     identifier.
  2. **Recorded per event:** source system; event ID; operation
     type; received timestamp; processing status; result/reference.
  3. **Duplicate detection:** the pair (source system, event ID) is
     the uniqueness key. A repeat with identical payload is skipped
     and logged (no repeated effect). A repeat with a conflicting
     payload is a data-integrity error — flagged for human review,
     never silently reprocessed (mirrors D-017's conflict rule).
  4. **Processing status:** `received` → `processing` → `succeeded` /
     `failed` / `skipped_duplicate`. Terminal states (`succeeded`,
     `skipped_duplicate`) are never re-entered.
  5. **Retry behavior:** retries are safe by design — a retry of a
     non-terminal event (`received`/`processing`) or after `failed`
     re-uses the same (source system, event ID) key; a
     terminal-succeeded event is never re-executed.
  6. **Failure handling:** a `failed` event is logged with its error
     (RULES §24 — never hidden), flagged for retry or human review;
     partial-failure reporting is honest (RULES §41).
  7. **Retention:** long enough to answer duplicate/success questions
     per RULES §27; the concrete retention period is an
     implementation decision, deferred.
  8. **No implementation specifics:** no database structures, no
     provider behavior, no distributed-systems machinery beyond this
     conceptual model.
- **Resolves:** D-016.K / register item 21 (event-level policy now
  defined; identifier-based keying was already approved via D-017).
- **Rationale:** RULES §25 requires that webhook/retry/scheduled
  events never create harmful duplicate effects; the (source, event
  ID) key + terminal-state model is the smallest deterministic design
  that satisfies it, stays consistent with D-017's identifier keying
  (which resolves *what* is written; this resolves *whether an event
  runs again*), and defers all implementation choices.
- **Source:** PROJECT_RULES §12, §24–§25, §27, §41; MASTER_PLAN §7;
  D-017; human owner approval (2026-09-12).

---

## Open decision register

| # | Decision | Status | Blocking | Target phase |
| --- | --- | --- | --- | --- |
| 1 | ~~Final SKU convention~~ — resolved: D-014 **Approved** | Resolved | — | 2 (done) |
| 2 | ~~Truly required product fields~~ — resolved: D-021 **Approved** | Resolved | — | 2 (done) |
| 3 | Taxonomy value lists — governance approved (D-019); concrete registry v1 contents still open | Open | Product data entry | 2 |
| 4 | Data-entry language for product data | Open | Product data entry | 2 |
| 5 | WooCommerce field mapping (conceptual → WooCommerce) | Open | WooCommerce foundation | 3 |
| 6 | WooCommerce hosting / VPS | Open | Store setup | 3–4 |
| 7 | n8n deployment model (cloud vs self-hosted) | Open | n8n foundation | 5 |
| 8 | Secret-management tooling | Open | First credential | 5 |
| 9 | AI provider(s) | Open | AI Runtime | 7 |
| 10 | Iranian payment provider | Open | Payment go-live | 12 |
| 11 | Iranian shipping provider | Open | Shipping go-live | 13 |
| 12 | Instagram API surface / account setup | Open | Instagram integration | 9 |
| 13 | ~~Variant-defining attributes~~ — resolved: D-018 **Approved** ({color, size}, per-axis applicability) | Resolved | — | 2 (done) |
| 14 | ~~Variant ID generation mechanism~~ — resolved: D-017 **Approved** (UUIDv4) | Resolved | — | 2 (done) |
| 15 | Size system — architecture resolved: D-020 **Approved** (multi-family); size-code convention avoiding O/I/L remains an open approval gate; concrete values owner-supplied | Open (partially resolved) | Vocabulary registry v1; size-code gate | 2 |
| 16 | ~~Product status state machine~~ — resolved: D-022 **Approved** (draft/active/archived) | Resolved | — | 2 (done) |
| 17 | ~~Publication status values~~ — resolved: D-023 **Approved** (unpublished/in_review/published/withdrawn) | Resolved | — | 2 (done) |
| 18 | ~~Price model~~ — resolved: D-024 **Approved** (list price + variant override + sale price; effective price precedence) | Resolved | — | 2 (done) |
| 19 | ~~Discount model~~ — resolved: D-025 **Approved** (sale-price-based; no engine; no coupons) | Resolved | — | 2 (done) |
| 20 | ~~Provenance mechanism~~ — resolved: D-026 **Approved** (per-value provenance tuple; append-only; storage deferred) | Resolved | — | 2 (done) |
| 21 | ~~Import idempotency strategy~~ — resolved: D-027 **Approved** (event-level) + D-017 (identifier-based) | Resolved | — | 2 (done) |
| 22 | Excel import scope: spec only vs spec + template (D-016.L) | Open | Phase 2 scope | 2 |
| 23 | SEO slug language (D-016.M) | Open/deferred | Product URLs | 2 or 3 |

Nothing in this register may be resolved silently (PROJECT_RULES §4).
Only the human owner approves decisions; D-014, D-015, D-017, D-018,
D-019 (governance), D-020 (architecture), D-021, D-022, D-023, D-024,
D-025, D-026, and D-027 are approved; D-016 and every item not marked
Resolved above remain open — including registry v1 contents (item 3)
and the size-code approval gate (item 15).

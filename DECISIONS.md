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
| 16 | Product status state machine (candidates: draft/active/archived — D-016.E) | Open | Product lifecycle rules | 2 |
| 17 | Publication status values (D-016.F) | Open | Product lifecycle rules | 2 |
| 18 | Price model: default + variant override + sale behavior (D-016.G) | Open | Pricing rules | 2 |
| 19 | Discount model (sale-price direction preferred, not approved — D-016.H) | Open | Pricing rules | 2 |
| 20 | Provenance storage mechanism (states fixed, storage open — D-016.J) | Open | Product data entry | 2 |
| 21 | Import idempotency strategy (D-016.K) — identifier keying approved via D-017; event-level policy still open | Open | Excel import specification | 2 |
| 22 | Excel import scope: spec only vs spec + template (D-016.L) | Open | Phase 2 scope | 2 |
| 23 | SEO slug language (D-016.M) | Open/deferred | Product URLs | 2 or 3 |

Nothing in this register may be resolved silently (PROJECT_RULES §4).
Only the human owner approves decisions; D-014, D-015, D-017, D-018,
D-019 (governance), D-020 (architecture), and D-021 are approved;
D-016 and every item not marked Resolved above remain open — including
registry v1 contents (item 3) and the size-code approval gate (item
15).

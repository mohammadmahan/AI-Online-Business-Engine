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
| D-028 | Excel import contract | **Approved** |
| D-029 | Controlled-vocabulary registry v1 (structure) | **Approved** (concrete values open) |
| D-030 | Size-code governance (O/I/L-safe) | **Approved** (concrete mappings open) |
| D-031 | Business data configuration — Batch 1 (store structure) | **Approved** (2026-09-12, owner) |
| D-032 | Business data configuration — Batch 2 (color/size SKU-code mappings) | **Approved** (2026-09-12, owner; incl. O/I/L-safe code corrections) |
| D-033 | Product Master Excel template — physical workbook contract | **Approved** (2026-09-12, owner) |
| D-034 | WooCommerce identity mapping & mapping registry | **Approved** (2026-09-12, owner) |
| D-035 | Simple vs variable product-type mapping | **Approved** (2026-09-12, owner) |
| D-036 | WooCommerce category mapping | **Approved** (2026-09-12, owner) |
| D-037 | WooCommerce attribute architecture & size-family strategy | **Approved** (2026-09-12, owner) |
| D-038 | WooCommerce price mapping | **Approved** (divergence sub-gate resolved via D-048) |
| D-039 | Lifecycle & publication projection | **Approved** (2026-09-12, owner) |
| D-040 | Media mapping | **Approved** (storage sub-decision open) |
| D-041 | Inventory boundary (Phase 3) | **Approved** (D-016.I remains open) |
| D-042 | Synchronization boundary & n8n responsibility split | **Approved** (2026-09-12, owner) |
| D-043 | WooCommerce API contract (conceptual) | **Approved** (implementation-time verification points) |
| D-044 | Sync idempotency & error handling | **Approved** (2026-09-12, owner) |
| D-045 | Security & credentials boundary | **Approved** (2026-09-12, owner) |
| D-046 | WooCommerce mapping registry (conceptual design) | **Approved** (2026-09-12, owner) |
| D-047 | Field-level sync contract & CRUD contract | **Approved** (2026-09-12, owner) |
| D-048 | Price-sync architecture — canonical-layer projection (D-038 sub-gate resolution) | **Approved** (2026-09-13, owner — Option A) |
| D-049 | Media storage direction | **Approved** (provider deferred to Phase 4) |
| D-050 | Green/Yellow/Red authority matrix for Woo operations | **Approved** (2026-09-12, owner) |
| D-051 | Non-registry attribute representation | **Approved** (2026-09-12, owner) |
| D-052 | Test/sandbox strategy | **Approved** (2026-09-12, owner; execution in Batch 3+) |
| D-053 | Local-first development environment + Local → Staging → Production promotion model | **Approved** (2026-09-13, owner directive) |
| D-054 | Local runtime technology — Docker Compose stack | **Approved** (2026-09-13, owner) |
| D-055 | Canonical project data storage — relational application database (PostgreSQL) | **Approved** (2026-09-13, owner) |
| D-056 | Local media — S3-compatible object-storage emulator (D-049 local equivalent) | **Approved** (2026-09-13, owner) |

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
  - E. **Product status state machine** — RESOLVED: D-022 **Approved**
    (2026-09-12; `draft`/`active`/`archived`; no WooCommerce mapping
    yet — that is Phase 3 work).
  - F. **Publication status** — RESOLVED: D-023 **Approved**
    (2026-09-12; `unpublished`/`in_review`/`published`/`withdrawn`;
    no unnecessary states added).
  - G. **Price model** — RESOLVED: D-024 **Approved** (2026-09-12;
    list price + variant override + sale price; deterministic
    effective price; no pricing engine).
  - H. **Discount model** — RESOLVED: D-025 **Approved** (2026-09-12;
    sale-price-based; no engine; no coupons).
  - I. **Inventory** — OPEN for Phase 2 design. Already-approved
    constraints remain in force (D-003, RULES §12): WooCommerce is the
    transactional Source of Truth; inventory must be verified;
    mutations must be idempotent and auditable; AI must never estimate
    stock. No inventory implementation in Phase 2.
  - J. **Provenance mechanism** — RESOLVED: D-026 **Approved**
    (2026-09-12; per-value provenance tuple; append-only; physical
    storage mechanism not chosen yet — implementation-deferred).
  - K. **Import idempotency** — RESOLVED: D-027 **Approved**
    (2026-09-12; event-level) with D-017 (identifier-based) and D-028
    (import contract).
  - L. **Excel import scope** — RESOLVED: D-028 **Approved**
    (2026-09-12; specification + reusable template); physical
    sheet/column mapping resolved by D-033 (Batch 3).
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
- **Open sub-gate:** ~~Size-code convention avoiding O/I/L~~ —
  resolved by D-032 (owner-approved concrete mappings, incl.
  O/I/L-safe alpha codes); size-equivalence mappings remain open.

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
- **Open dependencies (since resolved):** price mechanism (D-024),
  publication status values (D-023) — referenced here; resolved by
  later decisions.

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

## D-028 — Excel import contract

- **Status:** **Approved** (2026-09-12, human owner)
- **Decision:** The deterministic scope and rules for importing the
  existing Product Master Excel template into the product data
  system. Excel is an input/import surface, **never a Source of
  Truth** and never a transactional store (D-006, RULES §13).
  1. **Input surface:** exactly one workbook — the owner's existing
     Product Master Excel file. Physical sheet/column names are
     confirmed once against the owner's actual workbook at the
     Excel-import specification task (Phase 2 task 12); until that
     mapping is confirmed, this contract is stated over the semantic
     fields of the conceptual model (`DATA_MODEL.md` §3–§8) and
     invents no column names.
  2. **Accepted data:** product-level fields and variant-level fields
     of the conceptual model only — identifiers, name, category,
     attributes (Color/Size per D-018), size-family context (D-020),
     prices per D-024/D-025, media references, descriptions/SEO
     drafts. Not accepted: inventory/stock values (verified data
     only — never seeded from Excel), order/customer/payment/
     shipping data, coupons, credentials.
  3. **Product-level vs variant-level rows:** one product may occupy
     **one product row plus zero or more variant rows**. Simple
     products (zero active axes, D-018) need no variant rows. Variant
     rows carry all active variant-defining attribute values.
  4. **Product ID handling:** import **never issues** Product IDs.
     Accepted only as an explicit, human-supplied column value; rows
     without one are flagged for human assignment (by humans or
     approved deterministic tooling, D-017) before import completes.
  5. **Variant ID handling:** never present in Excel and never
     issued by import; Variant IDs (UUIDv4, D-017) are generated by
     approved deterministic tooling at import for genuinely new
     variant rows.
  6. **SKU handling:** never generated by Excel or import from
     parsed values. Either supplied per the D-014 convention (and
     validated: charset, suffix axes = active axes in Color → Size
     order, D-018 rule 6) or omitted — omitted SKUs are derived by
     approved deterministic tooling from the structured attributes
     after human confirmation. AI never generates a SKU.
  7. **Price handling:** numeric Toman per D-024/D-025 (D-010). List
     price / variant override / sale price (+ optional validity end)
     map 1:1 to the D-024 fields; the D-024 validation rules (sale <
     effective base; no zero/negative) run at validation time.
     Formatted price strings are rejected, not parsed.
  8. **Provenance:** every imported value records `IMPORTED`
     provenance per D-026 (source reference = workbook/batch; the
     original cell value is retained where normalization applied).
  9. **Vocabulary resolution (D-019):** color/size/attribute inputs
     resolve by exact alias matching after case/whitespace
     normalization, against active terms only. **No fuzzy matching;
     no similarity guessing.** Unmapped provided values are never
     discarded and never auto-added to any registry — the raw value
     is retained on the row and routed to the human review queue.
  10. **Size resolution (D-020):** size inputs resolve within the
      row's declared size family (product-level context); values
      outside the family or unmapped are retained and human-reviewed,
      never auto-converted.
  11. **Missing values:** absent optional cells are `NOT_PROVIDED`
      (never guessed, RULES §8). Missing required fields block only
      the affected record's import, never receive guessed values
      (D-021).
  12. **Unknown values:** explicit `UNKNOWN` is preserved as
      `UNKNOWN`; unknown values are surfaced to human review and do
      not automatically block (D-021 rule 5).
  13. **Invalid values:** malformed data (bad number format, wrong
      charset, price-rule violations) is rejected at validation with
      a row-level error — never auto-corrected, never clamped.
  14. **Duplicates:** duplicate Product IDs, duplicate Variant
      Identifiers/SKUs, and duplicate active variant-defining
      combinations (D-014 rule 11, D-018 rule 5) within a workbook or
      against existing data are data-integrity errors — the affected
      rows are rejected; nothing is silently merged.
  15. **Row-level validation:** every row is validated
      deterministically before any write; validation errors are
      reported per row with column, reason, and suggested human
      action. The invalid rows are excluded; valid rows are not
      blocked by unrelated invalid rows.
  16. **Idempotent re-import (D-017):** products keyed by Product ID;
      variants by Variant ID (SKU fallback). Identical re-import =
      no-op; conflicting payload = flagged for human review, never a
      silent overwrite; new rows receive tool-issued IDs, written
      back and logged.
  17. **Event idempotency (D-027):** each import run is itself an
      event under the D-027 model — one (source system, event ID) per
      run/batch; a repeated batch file with identical content is
      skipped and logged, not reprocessed.
  18. **Dry-run/preview:** imports run first in a **dry-run mode**
      that performs the full validation and reports the would-be
      result without writing. Only a human may promote a dry-run
      result to an actual import.
  19. **Human approval boundary:** the import run itself and every
      exception path (unmapped values, ID assignment, conflicting
      re-import, rejected rows) route to **human review**; AI may
      prepare/suggest but never executes an import or resolves an
      exception.
  20. **Partial failure:** a failed run writes nothing; failures are
      reported honestly per row (RULES §24, §41) with a re-runnable
      corrected batch — never partial silent commits.
  21. **Import provenance:** each run records its own provenance
      (workbook reference, timestamp, row counts, human approver).
  22. **Updates to existing records:** allowed only under the D-017
      re-import rules (identical = no-op; conflict = human review);
      bulk field updates outside that path are **not** an Excel
      import feature — they are a future, separately approved tool
      concern (Phase 19 class).
  23. **Explicitly NOT supported:** creating/modifying vocabulary
      terms (D-019); issuing any identifier (D-014 rule 12, D-017);
      writing inventory/stock; order/customer/payment/shipping data;
      fuzzy matching or AI-guessed values; becoming a persistent
      data store or second database; silent overwrites.
- **Resolves:** D-016.L / register item 22.
- **Rationale:** Turns the approved pieces (D-014/D-017 identifiers,
  D-019 resolution, D-020 size context, D-024/D-025 prices, D-026
  provenance, D-027 event idempotency) into one deterministic import
  contract — input-only Excel, human-approved exceptions, dry-run
  preview, honest partial-failure handling — without making Excel a
  store or inventing a parser, UI, or physical column names.
- **Source:** PROJECT_RULES §6–§8, §13, §23–§25, §41; MASTER_PLAN §4,
  §6; D-006, D-010, D-014, D-017–D-020, D-024–D-027; human owner
  approval (2026-09-12).

## D-029 — Controlled-vocabulary registry v1 (structure)

- **Status:** **Approved** (structure) — **concrete registry values
  remain OPEN and owner-gated** (colors, sizes, categories, other
  controlled fields).
- **Decision:** The minimum registry set and entry shape for Phase 2,
  finalizing the concrete-v1 layer on top of D-019's governance
  architecture:
  1. **Required vocabularies in v1:**
     - `color` — variant-defining (SKU-code-bearing; D-018).
     - `size` — variant-defining (SKU-code-bearing; D-018); entries
       additionally carry the D-020 `size family` classification.
     - `category` (main/subcategory) — product-level.
  2. **Deferred (not part of v1):** pattern, style, season, usage,
     collar, sleeve, length, closure, suitable-for, brand, material
     — remain free/product-level optional attributes until the owner
     promotes a vocabulary for consistency reasons; promotion is an
     owner decision (D-019 governance applies unchanged).
  3. **Entry fields (per D-019, confirmed):** attribute; canonical
     code (only for variant-defining vocabularies; O/I/L-safe per
     D-014 rule 7 / D-030); canonical value/slug; **Persian display
     label (required)**; English display label **optional** (only
     where operationally justified); aliases; status
     (active/deprecated — never deleted); provenance (D-011 states;
     D-026 record); created/updated timestamps; notes.
  4. **Code requirements:** uppercase Latin ASCII; O/I/L forbidden
     (D-014 rule 7, D-030); unique within their vocabulary; codes
     for variant-defining vocabularies require owner approval.
  5. **Canonical value/slug:** lowercase Latin slug, unique per
     vocabulary, stable once referenced.
  6. **Persian display label:** required for every term (the store
     is Persian/RTL-first, D-002).
  7. **English display label:** optional, only where genuinely
     justified (e.g., internal ops tooling); not auto-generated.
  8. **Aliases:** alternative spellings/transliterations for input
     normalization; exact-match only (D-019 rule 5); no fuzzy
     matching.
  9. **Status:** active/deprecated; deprecation preserves
     resolvability of historical SKUs/values (D-014 rule 14); never
     deleted.
  10. **Provenance/timestamps:** every term carries D-011 provenance
      (D-026 record shape) and created/updated timestamps.
  11. **Ownership:** humans (owner/delegated staff) create terms;
      variant-defining-vocabulary terms require owner approval; AI
      may propose into the review queue, never create/activate/
      modify/delete (D-019 rules 2–4, unchanged).
  12. **Normalization:** exact alias matching after basic
      case/whitespace normalization; no fuzzy matching; no
      similarity guessing; unmapped values retained and
      human-reviewed (D-019 rules 5–6, unchanged).
- **NOT included:** any concrete color/size/category value list.
  Concrete registry v1 **values remain OPEN and owner-gated** — the
  owner supplies/approves them; AI invents none.
- **Resolves:** the structure portion of D-016.C / register item 3;
  the concrete-value portion of item 3 remains **open**.
- **Rationale:** Separates registry architecture (now deterministic)
  from owner-owned values (never invented); keeps v1 minimal (three
  vocabularies the Phase 2 model actually requires) with explicit
  deferral of the rest; all governance rules carry over from D-019
  unchanged.
- **Source:** D-019; MASTER_PLAN §4; PROJECT_RULES §6–§8, §32–§33;
  D-002, D-014 rule 7, D-018, D-020, D-026; human owner approval
  (2026-09-12).

## D-030 — Size-code governance (O/I/L-safe)

- **Status:** **Approved** (governance) — **concrete size-code
  mappings remain OPEN and owner-gated** (no mapping is finalized or
  invented here).
- **Decision:** The generation/governance rule that guarantees size
  codes avoid O/I/L, closing D-020's open sub-gate at the governance
  level:
  1. **Forbidden characters:** size codes must never contain `O`,
     `I`, or `L` in any position (D-014 rule 7; no exception is
     created).
  2. **Charset:** uppercase Latin ASCII only (D-014 rule 5); no
     digits in size codes unless a future owner-approved mapping
     requires them.
  3. **Ownership/approval:** size codes are created and approved by
     the human owner (variant-defining vocabulary rule, D-019);
     deterministic tooling may derive/validate candidates; AI may
     **propose** codes into the review queue — AI never assigns a
     code (D-014 rule 12, D-017 rule 7).
  4. **Immutability:** a size code is frozen once referenced by an
     approved term/SKU (D-014 rule 10); corrections follow the
     deactivate + recreate path — an existing term never gets its
     code renamed in place.
  5. **New code for an existing term:** if a term needs a different
     code, the term is deprecated with its code preserved and a new
     term (with the new code) is created; historical SKUs remain
     resolvable via the deprecated term (D-014 rule 14, D-019 rule 3).
  6. **Aliases never share a code:** one canonical code per active
     term; aliases resolve to the term, not to a second code.
  7. **Family context:** the code namespace is scoped within the
     size family (D-020); the same code string may exist in two
     families only if the owner approves it explicitly, and SKUs
     remain unambiguous because the variant's term is unique within
     its product's declared family.
  8. **SKU interaction:** the size code occupies the size position of
     the D-018 suffix (Color, then Size); collision handling is the
     D-014 `-2` emergency valve only — never a numbering scheme.
  9. **Collision handling (registry):** a proposed code colliding
     with an active term in the same family is rejected at
     proposal/validation time; the human chooses a different code.
  10. **No concrete mappings:** no letter↔code value list is created
      by this decision. Concrete size-code mappings (e.g., for alpha
      sizes) remain **OPEN and owner-gated**; until approved, size
      codes simply cannot be issued for any term.
- **Resolves:** the governance portion of D-020's open sub-gate
  (size-code convention); the **concrete size-code mappings remain
  OPEN** as a separate owner sub-decision (register item 15).
- **Rationale:** D-014 rule 7 makes O/I/L avoidance mandatory; this
  decision fixes who may create codes, how collisions and
  corrections work, and how codes interact with SKUs — deterministically
  — while leaving every concrete mapping to the owner (nothing
  invented).
- **Source:** D-014 rules 5/7/10/12/14; D-017; D-018 rule 6; D-019,
  D-020; PROJECT_RULES §10, §32; human owner approval (2026-09-12).

## D-031 — Business data configuration — Batch 1 (store structure)

- **Status:** **Approved** (2026-09-12, human owner)
- **Decision:** The owner-approved concrete business configuration,
  recorded in full in
  `docs/phases/phase-02-5-business-data-configuration.md`:
  1. **Category structure:** 2 primary categories (پوشاک زنانه،
      پوشاک مردانه) with 12 women's and 8 men's subcategories as
      listed in the Phase 2.5 document. Category is a controlled
      vocabulary (Registry v1) and is **NOT variant-defining**. No
      category may be added, removed, renamed, merged, or
      reorganized; future category changes require a new explicit
      owner decision.
  2. **Variant model unchanged:** variant-defining attributes remain
      exactly {Color, Size} (D-018); per-axis applicability; zero
      active axes = simple product; inseam remains deferred; no
      other attribute creates variants.
  3. **Registry v1 composition unchanged:** exactly `color`, `size`,
      `category` (D-029). Brand, material, pattern, style, season,
      usage, collar, sleeve, length, closure, and fit remain outside
      Registry v1; promotion is a separate owner decision each.
  4. **Color vocabulary:** 25 owner-approved canonical Persian terms
      (مشکی، سفید، طوسی، ذغالی، طوسی روشن، کرم، بژ، قهوه‌ای،
      نسکافه‌ای، سرمه‌ای، آبی، آبی روشن، آبی نفتی، سبز، سبز زیتونی،
      سبز تیره، قرمز، زرشکی، صورتی، صورتی روشن، بنفش، نارنجی، زرد،
      خاکی، شتری). No English labels invented; no aliases invented;
      **no SKU codes assigned** — the color-code mapping remains an
      explicit owner-gated task (D-030/D-014 rule 7).
  5. **Size families:** owner-approved terms in three families —
      Alpha (XS, S, M, L, XL, XXL, 3XL, 4XL); Numeric (34–54 step 2,
      11 values); Pants Waist (28–44 step 2, 9 values). Shoe size
      excluded (footwear outside initial scope). No size-code
      mappings; no equivalence links; no cross-family conversion.
      Family-scoped semantics per D-020/D-030.
  6. **Approved product attributes:** 8 general/product-level
      (برند/Brand, جنس/Material, رنگ/Color, سایز/Size, طرح/Pattern,
      مدل/Style, فصل/Season, کاربرد/Usage) and 5 garment-specific
      (نوع یقه/Collar, نوع آستین/Sleeve, قد لباس/Length,
      نوع بسته‌شدن/Closure, نوع فیت/Fit). Color and Size remain the
      only variant-defining axes; all others are product-level
      unless a future owner decision changes this. Fit is recorded
      as a product-level attribute, not promoted into Registry v1.
      The approved list covers attribute names only — no concrete
      value lists for non-registry attributes are approved or
      invented.
  7. **Data-entry principle:** the human seller enters human-readable
      values (e.g., مشکی، XL); the future deterministic system may
      resolve term → approved SKU code. The mapping is **not**
      implemented or invented now; AI must never assign or invent
      SKU codes; D-014/D-015 identifier rules are unchanged.
  8. **AI authority unchanged:** all Phase 2 restrictions preserved
      (propose/recommend/draft/enrich/summarize/suggest only —
      never create/activate/modify/delete terms, assign codes or
      identifiers, execute transitions, publish, import, or resolve
      exceptions).
- **Resolves:** the concrete **category values**, **color terms**
  (display values), and **size terms** portions of the Registry v1
  concrete-values gate (register items 3 and 15). The color/size
  **SKU-code mappings**, size equivalence mappings, color/size
  aliases, physical Excel mapping, general data-entry language,
  SEO slug, inventory constraints, and Phase 3+ decisions remain
  **OPEN**.
- **Rationale:** Owner-supplied configuration closes the value-gates
  that Phase 2 deliberately left owner-gated, without inventing any
  code mapping, alias, English label, or new rule; all D-014–D-030
  governance applies unchanged to the approved values.
- **Source:** Human owner approval of the Batch 1 Business Data
  Configuration proposal (2026-09-12); D-014–D-030;
  `docs/phases/phase-02-5-business-data-configuration.md`.

---

## D-032 — Business data configuration — Batch 2 (color/size SKU-code mappings)

- **Status:** **Approved** (2026-09-12, human owner) — a concrete,
  owner-approved **realization** of the D-014/D-030 governance rules;
  no governance rule is altered.
- **Decision:**
  1. **Color codes (25):** owner-approved one-to-one canonical color
     term → SKU code — BK, WHT, GRY, CHR, GY1, CRM, BEG, BRN, NCF,
     NVY, BU, BU1, PTB, GRN, VGR, DGN, RED, BRG, PNK, PK1, PRP, RNG,
     YW, KHK, CAM (order follows the D-031 color list).
  2. **Owner O/I/L correction:** the owner's initial proposal used
     `BLK`, `BLU`, `YLW` (each containing `L`, forbidden by D-014
     rule 7). The owner reviewed the conflict and approved the
     O/I/L-safe replacements `BK`, `BU`, `YW`. D-014 and D-030 remain
     fully intact — **no exception or deviation was created**.
  3. **Size codes (family-scoped):** Alpha — XS→XS, S→S, M→M,
     L→LG, XL→XG, XXL→XXG, 3XL→3XG, 4XL→4XG (separate O/I/L-safe
     codes per D-020 rule 9; display labels remain `L`, `XL`, per
     D-020 rule 4); Numeric — 34→34 … 54→54; Pants Waist — 28→28 …
     44→44 (canonical value = code; digits permitted via an
     owner-approved mapping, D-030 rule 2). Numeric 42 and Pants
     Waist 42 remain **distinct terms in distinct families**.
  4. **No aliases and no equivalence links** are created; the alias
     registry stays empty and cross-family conversion stays
     human-curated only (D-019 rule 5, D-020 rule 7).
  5. **SKU examples are illustrative only** (P00001-BK-M,
     P00001-WHT-XG, P00002-BRN-42, P00003-BK, P00004); no products,
     SKUs, or runtime generation are created.
  6. **Governance unchanged (D-014/D-030):** codes immutable once
     referenced; one code per active term; family-scoped namespace;
     collisions rejected; the D-014 `-2` valve is the only collision
     mechanism; AI may validate but never assign/create/change/delete
     an approved code; approved deterministic tooling may derive SKU
     strings from approved Product ID + approved codes and validate
     uniqueness.
- **Resolves:** the color and size **SKU-code mappings** portions of
  register items 3 and 15. **Remaining open:** color/size aliases,
  size-equivalence mappings, physical Excel mapping, general
  data-entry language, SEO slug, inventory constraints, promotion of
  non-v1 attributes, Phase 3+ decisions.
- **Rationale:** Closes the last value-gates of the product-data
  vocabulary with owner-approved, rule-compliant codes; the L
  conflicts in the initial proposal were caught by the batch's own
  validation and resolved by the owner rather than silently deviating
  from D-014/D-030.
- **Source:** Human owner approval of Batch 2 (2026-09-12), including
  the explicit O/I/L-safe replacement decision; D-014, D-020, D-030,
  D-031; `docs/phases/phase-02-5-business-data-configuration.md`.

---

## D-033 — Product Master Excel template (physical workbook contract)

- **Status:** **Approved** (2026-09-12, human owner) — the concrete
  physical realization of the D-028 semantic import contract; no
  semantic rule is altered.
- **Decision:** the Product Master workbook is `product-master.xlsx`
  with exactly four sheets — `محصولات` (one row per product),
  `تنوع‌ها` (one row per variant), `راهنما` (Persian seller guide,
  never imported), `گزینه‌ها` (approved controlled values + dropdown
  backing, never imported). The **normative column list, order, data
  types, required/optional status, canonical value mappings,
  validation behavior, import mapping, and provenance behavior are
  specified in full in
  `docs/phases/phase-02-5-excel-master-template.md`** (owner-approved
  via this decision) and summarized here:
  1. **Products sheet (28 columns):** Product ID (`P00001`, human
     input, required), name (required), optional name/brand/material/
     pattern/style/season/usage/collar/sleeve/length/closure/fit/
     descriptions/SEO (deferred optional), primary category + leaf
     category (both controlled, required — two columns because
     identical leaf names exist under both primaries as separate
     Batch 1 terms), D-024 product price fields (list price required-
     if, product sale price + validity optional), media references
     (`|`-separated; ≥1 required for publication), product status +
     publication status (exact Persian→canonical mapping), created
     date (required). **Color/Size are not product-level columns**
     (variant axes live on the variants sheet only).
  2. **Variants sheet (10 columns):** Variant ID (blank at input →
     approved deterministic tooling generates canonical UUIDv4 after
     human promotion; if present, validated, never reused), Product
     ID (required, must match a product row), SKU (blank → tooling
     derives per D-014/D-032; if present, validated, never
     auto-corrected), Color term, Size family + Size term (exact
     active-term matching; size must belong to the selected family),
     D-024 variant override + D-025 variant sale + validity, variant
     status (mirrors product lifecycle, D-022 rule 7).
  3. **Active axes are read from the rows deterministically** (D-018):
     an axis is active iff at least one variant row fills it, and then
     every row of the product must fill it consistently; zero variant
     rows = simple product; duplicate active-axis combinations are
     rejected (D-014 rule 11).
  4. **Blank = `NOT_PROVIDED`; exact `نامشخص` = `UNKNOWN`; invalid
     content = rejected** — the D-028/D-021 three-state semantics,
     preserved exactly.
  5. **Prices:** numeric Toman only (D-010); formatted strings
     rejected; sale < applicable base enforced; precedence per
     D-024/D-025 unchanged.
  6. **Statuses:** exact Persian↔canonical mapping (پیش‌نویس/فعال/
     بایگانی; منتشرنشده/در بررسی/منتشرشده/برداشته‌شده); no new
     statuses; publication honored only through the D-023 path with
     the human dry-run promotion as the human-approved transition.
  7. **Vocabularies:** exact Batch 1 values only (categories
     primary-scoped; 25 colors with D-032 codes; 3 size families with
     D-032 codes); no aliases, no equivalence mappings, no fuzzy
     matching, no automatic vocabulary creation.
  8. **No inventory/stock column exists.** D-016.I stays open.
  9. **Import:** one run = one D-027 event; per-row D-017 identifier
     idempotency (distinct mechanisms); every value gets `IMPORTED`
     provenance (D-026) with workbook/sheet/row/column reference;
     dry-run first; human promotion; partial failure writes nothing.
- **Resolves:** the **physical Excel sheet/column mapping** (the last
  open portion of D-016.L / register item 22; previously pending the
  owner workbook). **Not resolved:** aliases, size-equivalence
  mappings, SEO slug language, general data-entry language (the
  Persian workbook UI is batch-scoped, not a project-wide decision),
  inventory constraints, promotion of non-v1 attributes, Phase 3+
  decisions.
- **Rationale:** Makes the D-028 contract concretely implementable
  without inventing the owner's original column names: the owner
  approved this Persian/RTL-first physical layout as the authoritative
  template contract. The two-column category encoding is the faithful
  physical representation of the approved Batch 1 tree (separate terms
  per primary), not a new concept.
- **Source:** Human owner approval of Batch 3 (2026-09-12); D-028 and
  its import specification; D-010, D-014, D-015, D-017–D-022, D-024,
  D-025, D-031, D-032;
  `docs/phases/phase-02-5-excel-master-template.md`.

## D-034 — WooCommerce identity mapping & mapping registry

- **Status:** **Approved** (2026-09-12, human owner)
- **Decision:** The five identifiers are mapped, never conflated
  (extends D-014/D-015/D-017 to the WooCommerce context; normative
  design in `docs/phases/phase-03-1-woocommerce-foundation.md` §2):
  1. **Product ID** (`P00001`) — ours, business-facing, immutable;
     stored in Woo for reference; **not** the Woo product ID.
  2. **Variant ID** (UUIDv4) — ours, internal identity, immutable;
     **not** the SKU and **not** the Woo variation ID.
  3. **SKU** — ours, business/inventory identifier; stored in Woo's
     `sku` field; never Woo's internal identity.
  4. **WooCommerce product ID** — platform-owned numeric, generated
     by Woo at creation.
  5. **WooCommerce variation ID** — platform-owned numeric, generated
     by Woo at creation.
  A conceptual **mapping registry** connects them one-to-one:
  Product ID ↔ Woo product ID; Variant ID ↔ Woo variation ID; color
  term ↔ `pa_color` term ID; family-scoped size term ↔
  `pa_size-{family}` term ID; category term (primary + leaf) ↔ Woo
  category ID. The registry is written only by approved deterministic
  tooling at first successful creation/read-back; conflicts route to
  human review; it is never hand-maintained, never fuzzy-matched, and
  **does not exist yet** — it is a Phase 3 implementation requirement.
  Woo numeric IDs are internal technical identifiers, never our
  business identity, never renumbered/reassigned; lost linkages are
  repaired by human decision, not silently.
- **Rationale:** Preserves D-015/D-017 identity separation at the
  WooCommerce boundary; the registry is the smallest deterministic
  mechanism that prevents duplicate creation and identity drift.
- **Source:** D-003, D-014, D-015, D-017; PROJECT_RULES §13, §25;
  human owner approval (2026-09-12).

## D-035 — Simple vs variable product-type mapping

- **Status:** **Approved** (2026-09-12, human owner)
- **Decision:** Exactly two WooCommerce product types, mapped
  deterministically from the D-018 active axes (foundation doc §3):
  1. **Zero active axes** → Woo type `simple`; SKU = Product ID.
  2. **≥ 1 active axis** (Color only, Size only, or Color + Size) →
     Woo type `variable` with the corresponding attribute(s) and one
     variation per active-axis combination.
  A single-variation variable product stays `variable` (no demotion
  heuristic). Each of our variants maps 1:1 to a Woo variation,
  keyed through the D-034 registry. Product-level-only differences
  are separate products (D-018 rule 4) and separate Woo products. No
  third product type exists; non-Color/Size attributes never create
  variations.
- **Rationale:** Faithful, deterministic realization of D-018/D-031
  in WooCommerce's native model without new concepts.
- **Source:** D-018, D-031; MASTER_PLAN §4; human owner approval
  (2026-09-12).

## D-036 — WooCommerce category mapping

- **Status:** **Approved** (2026-09-12, human owner)
- **Decision:** The exact Batch 1 tree (D-031) maps to a two-level
  WooCommerce product-category hierarchy (foundation doc §4): the two
  primaries (پوشاک زنانه، پوشاک مردانه) are top-level categories;
  each of the 12 women's and 8 men's leaves is a child category under
  its own primary. **Duplicate leaf names stay distinguishable**
  (تیشرت زنانه vs تیشرت مردانه) — separate child categories under
  separate parents; no leaf is merged or shared across primaries. The
  D-033 columns map 1:1 (دسته‌بندی اصلی → parent; زیردسته →
  primary-scoped child); a leaf under the wrong primary is INVALID.
  No extra categories; no runtime category creation (the seed is the
  owner-approved D-031 tree). Category is not a variant-defining axis
  and creates no Woo attribute.
- **Rationale:** The simplest faithful mapping that preserves the
  owner-approved term structure exactly.
- **Source:** D-031, D-018, D-033; human owner approval (2026-09-12).

## D-037 — WooCommerce attribute architecture & size-family strategy

- **Status:** **Approved** (2026-09-12, human owner)
- **Decision:** WooCommerce attribute architecture (foundation doc
  §5):
  1. **Color:** one global attribute `pa_color` with the 25
     owner-approved terms (D-031); variation-defining; term display
     name = Persian canonical value; term slug = lowercase D-032
     code; the D-032 code remains our canonical code; the Woo term ID
     is a mapped technical id (registry).
  2. **Size:** **one global attribute per approved family** —
     `pa_size-alpha`, `pa_size-numeric`, `pa_size-waist` — because a
     single shared size attribute would collapse Numeric 42 and Pants
     Waist 42 into one term and destroy the D-020/D-032 family-scoped
     semantics. A product uses exactly the attribute of its declared
     family (product-level context, D-020 rule 3); Numeric 42 and
     Pants Waist 42 remain distinct Woo terms; no merge, no
     equivalence, no automatic conversion. Alpha slugs are the
     lowercase D-032 codes (`lg`, `xg`, …); display names stay
     conventional (`L`, `XL`) per D-020 rule 4.
  3. **Size Family** is **not** a customer-facing attribute — it
     remains internal mapping/context that selects which size
     attribute a product uses.
  4. **All other approved attributes** (Brand, Material, Pattern,
     Style, Season, Usage, Collar, Sleeve, Length, Closure, Fit) are
     **not** created as Woo global attributes now — their Woo
     representation is an **OPEN** decision, because promotion into
     controlled vocabularies is a separate owner decision (D-019/
     D-031); only Color and Size are variation attributes (D-018).
  5. Latin slugs are internal identifiers, **not** the SEO URL
     decision (D-016.M stays open). Runtime term creation does not
     exist; terms are seeded from the owner-approved registries
     (D-019: humans create, AI proposes only).
- **Rationale:** Preserves family-scoped size semantics in a platform
  whose attributes are flat; keeps variation-defining and
  informational attributes strictly separated; invents no vocabulary.
- **Source:** D-018, D-020, D-029, D-031, D-032; D-014 rule 7;
  human owner approval (2026-09-12).

## D-038 — WooCommerce price mapping

- **Status:** **Approved** — the price-divergence sub-gate is now
  **resolved via D-048** (Option A, owner-approved 2026-09-13);
  D-024/D-025 semantics are untouched.
- **Decision:** Field mapping (foundation doc §6; numeric Toman,
  D-010): our list price → Woo `regular_price` (product); variant
  override → variation `regular_price`; sale price (+ validity end) →
  `sale_price` (+ sale-end field; no start-date field is used —
  D-025 has no start scheduling). Pre-write validation: numeric
  integers only, formatted strings rejected; sale < applicable base;
  sale ≥ base rejected, never clamped; zero/negative effective price
  invalid; expired sales ignored; unresolved base price never written
  or guessed; AI never creates/changes a production price (Red tier).
  **Known divergence (documented, not hidden):** our D-024 effective
  precedence is *valid variant sale → valid product sale → variant
  override → product list price*; Woo's native fallback for a
  variation commonly does not cascade a parent-level sale onto
  variations carrying their own prices, so the case "product-level
  sale + variant override + no variant sale" can display differently.
  Candidate resolutions — ~~OPEN owner sub-gate~~ **resolved via
  D-048 (owner-approved 2026-09-13): A** — approved tooling
  materializes the canonical resolution into the displayed fields at
  each affected change (base fields never mutated); **B)** config
  constraint and **C)** accept Woo-native display were the
  alternatives, not chosen. The divergence case is now resolved
  deterministically per D-048. Exact Woo native behavior is an
  implementation-time verification point.
- **Rationale:** Maps D-024/D-025 1:1 without changing them; names
  the real platform conflict instead of hiding it.
- **Source:** D-010, D-024, D-025; PROJECT_RULES §11, §32; human
  owner approval (2026-09-12).

## D-039 — Lifecycle & publication projection

- **Status:** **Approved** (2026-09-12, human owner)
- **Decision:** Our D-022/D-023 state machines **remain canonical**;
  WooCommerce's single post `status` field cannot represent both, so
  Woo receives a **projection** (foundation doc §7):
  `draft` → no Woo record yet (creation at entry to `active`);
  `active` + `unpublished`/`in_review` → hidden record;
  `active` + `published` → published (only after the Red-tier human
  approval, executed by approved tooling);
  `active` + `withdrawn` → hidden, preserved;
  `archived` (any publication) → hidden, preserved, **never
  deleted** (deletion is destructive, RULES §22). No new business
  state is invented; a native Woo status is never claimed equivalent
  to a D-022/D-023 state — it is a projection of one. Woo transitions
  execute only after the corresponding human-approved canonical
  transition; forbidden canonical transitions are impossible in the
  projection. AI never executes transitions. Field-level projection
  (status vs visibility fields per Woo version) is an
  implementation-time verification point; the contract above is
  normative.
- **Rationale:** Keeps the approved state machines authoritative
  while producing a deterministic, human-gated rendering into Woo.
- **Source:** D-022, D-023, D-021; PROJECT_RULES §22, §32; human
  owner approval (2026-09-12).

## D-040 — Media mapping

- **Status:** **Approved** — media **storage sub-decision OPEN**.
- **Decision:** D-033 media references map to WooCommerce product
  images (foundation doc §8): first reference → primary/featured
  image; remaining references → gallery in the given
  (`|`-separated) order. Alt text: deterministic default = product
  name; richer alt text may come from Media records/AI suggestions
  (Yellow tier, provenance-tagged); nothing invented. References
  stay **references, not binaries**: whether the implementation
  uploads binaries into the Woo media library or attaches external
  URLs is an **OPEN storage decision** (no provider chosen, nothing
  uploaded, no media infrastructure in this batch). Media sync runs
  via approved tooling after human promotion, like all writes. The
  D-021 publication minimum (≥ 1 image) is unaffected.
- **Rationale:** Completes the publication-minimum path to the
  storefront without choosing storage prematurely.
- **Source:** D-021, D-026, D-033; human owner approval (2026-09-12).

## D-041 — Inventory boundary (Phase 3)

- **Status:** **Approved** (the boundary) — **D-016.I remains OPEN**;
  no inventory architecture is designed here.
- **Decision:** Phase 3 establishes only (foundation doc §9):
  1. **Where inventory will eventually be read:** WooCommerce
     (transactional inventory Source of Truth, D-003, RULES §12).
  2. **What may eventually write it:** only approved deterministic
     tooling through idempotent, auditable flows (future phase);
     never AI; never Excel (the D-033 workbook has no stock columns).
  3. **What Phase 3 Batch 1 does NOT implement:** stock
     synchronization, stock fields at sync time, stock writes,
     order/stock event handling. No stock field is added to the Excel
     contract; D-016.I is not closed.
- **Rationale:** Fixes the boundary without pre-empting the still-
  open inventory design.
- **Source:** D-003, D-016.I, D-028, D-033; PROJECT_RULES §12; human
  owner approval (2026-09-12).

## D-042 — Synchronization boundary & n8n responsibility split

- **Status:** **Approved** (2026-09-12, human owner)
- **Decision:** Responsibility split unchanged (D-003/D-004/D-005):
  Product Master = canonical business data; n8n = orchestration only
  (triggers, sequencing, retries, event records, error routing,
  notifications — never a data store, never a source of truth);
  WooCommerce = transactional execution; AI = proposal/enrichment
  (Yellow tier); Human = business-critical authority. Sync directions
  are **explicit per field — no default bidirectional field sync**
  (foundation doc §11):
  1. **Product Master → Woo:** identity, taxonomy, attributes,
     prices, descriptions/SEO, media refs, publication projection —
     authoritative source = Product Master; trigger = human-promoted
     sync run (D-027 event); full pre-write validation; Red tier for
     publish and price-affecting writes; conflicts → human review,
     never silent overwrite.
  2. **Woo → Product Master:** created Woo IDs only (registry
     write-back) — technical facts, automatic and logged; duplicates
     → human review.
  3. **Woo → operational views (future):** stock, orders, customers
     as read-only references (minimization, RULES §28).
  4. **Woo → Product Master field sync of PM-owned fields:** **not
     permitted**; Woo-side manual edits of PM-owned fields are
     divergences — detected on read-back comparison and routed to
     human review; no silent overwrite in either direction.
  Woo-owned transactional fields (stock, orders, customers, coupons)
  are never written by Product Master flows (D-041, D-016.I open).
- **Rationale:** Prevents silent bidirectional drift; keeps each
  system's authority exactly where the approved architecture put it.
- **Source:** D-003–D-007, D-017, D-027, D-041; PROJECT_RULES §13,
  §14, §25, §28; human owner approval (2026-09-12).

## D-043 — WooCommerce API contract (conceptual)

- **Status:** **Approved** as a conceptual contract — exact endpoint
  versions and field-level API details are **implementation-time
  verification points**; no API is called and no code is written in
  this batch.
- **Decision:** Required resource areas and their contracts (official
  WooCommerce REST API family, D-012 ladder; foundation doc §10):
  products (create/update/read), variations (batch create/update/
  read), product categories (one-time seed/read), product attributes
  (one-time seed/read), attribute terms (one-time seed/read), media
  (upload or reference per D-040). Every write is idempotent under
  D-027 (one event per operation) and keyed by the D-034 registry
  (create only if the registry shows no linkage, with deterministic
  lookup as second guard). Source-of-truth direction per D-042
  (business fields ours → Woo; Woo IDs back to the registry). Human
  approval: record creation follows human-promoted flows; **delete is
  Red tier / destructive (RULES §22)** — prefer hide/archive over
  delete. Error behavior per D-044. **No credentials exist and none
  are requested in this batch.**
- **Rationale:** Fixes the integration surface and its guarantees
  without writing code or inventing provider specifics.
- **Source:** D-012, D-017, D-027, D-034, D-042; PROJECT_RULES §15,
  §22, §25; human owner approval (2026-09-12).

## D-044 — Sync idempotency & error handling

- **Status:** **Approved** (2026-09-12, human owner)
- **Decision:**
  1. **Identifier-level (D-017):** Product ID / Variant ID / SKU stay
     the identity keys of our data; Woo identifiers are mapped via
     the D-034 registry; creates run only when the registry shows no
     existing linkage; duplicates are flagged, never merged; SKU is
     never Woo's internal identity and never a fuzzy-match key.
  2. **Event-level (D-027):** every sync operation is an event with a
     (source system, event ID) key; identical repeats skipped and
     logged; conflicting repeats are integrity errors → human review;
     terminal states never re-entered. The two mechanisms remain
     distinct and complementary.
  3. **Error classification (foundation doc §12):** retryable —
     Woo/network unavailability, timeout-before-response, ambiguous
     timeout (retry only after read-back reconciliation, never blind
     re-create), rate limiting (respect provider backoff), partial
     response; non-retryable — authentication failure (halt, human
     fixes credentials), our validation failure (human corrects the
     data), duplicate/conflicting resource (human review, no silent
     adoption), malformed response, immutable identifier mismatch
     (integrity error, never silently relinked). Retry counts/backoff
     are set per workflow at Phase 5 — no arbitrary numbers invented
     here. Human review exists for every data-integrity conflict;
     errors are never hidden (RULES §24, §41).
- **Rationale:** Extends the approved idempotency decisions to the
  WooCommerce boundary with deterministic, honest failure behavior.
- **Source:** D-017, D-027, D-034; PROJECT_RULES §24–§25, §41; human
  owner approval (2026-09-12).

## D-045 — Security & credentials boundary

- **Status:** **Approved** (2026-09-12, human owner)
- **Decision:** The credential boundary for the WooCommerce/n8n
  integration (no secrets exist yet; none requested in this batch;
  RULES §16–§18, §27 restated for this context):
  1. Future secrets — WooCommerce API credentials, n8n credentials,
     hosting credentials (Phase 4), external API credentials — are
     **never** stored in Git, Markdown/docs, Excel, AI prompts, logs,
     or hard-coded workflow nodes.
  2. Stored only via environment/secret-management at implementation
     time; the secret-management tooling selection remains register
     row 8 (OPEN).
  3. **Least privilege:** read-only credentials where possible;
     write credentials only for approved flows; Freebuff and AI
     agents never receive unrestricted production credentials.
  4. Separate credentials per environment (development/staging/
     production; RULES §18); no experimental code against production.
  5. Exposure → STOP and report immediately; rotate when appropriate.
  No secret-management implementation happens in this batch.
- **Rationale:** Applies the project's standing security rules to the
  Phase 3 integration surface before any credential exists.
- **Source:** PROJECT_RULES §16–§18, §27; SECURITY.md §1–§3; human
  owner approval (2026-09-12).

## D-046 — WooCommerce mapping registry (conceptual design)

- **Status:** **Approved** (2026-09-12, human owner)
- **Decision:** The complete conceptual design of the D-034 mapping
  registry (normative in
  `docs/phases/phase-03-2-woocommerce-sync-architecture.md` §2):
  1. **Entry types / authority:** Product (Product ID ↔ Woo product
     ID); Variation (Variant ID ↔ Woo variation ID); Category
     (primary+leaf term ↔ Woo category ID); Color term (↔ `pa_color`
     term ID); Size term (family-scoped pair ↔ `pa_size-{family}`
     term ID); Media reference (↔ Woo attachment ID). The canonical
     side is always authoritative; Woo IDs are technical facts
     written back after creation; entries are never derived by fuzzy
     name matching.
  2. **Uniqueness:** one active entry per canonical key, and a Woo ID
     in at most one active entry per type (both directions enforced;
     violations are MAPPING_CONFLICT integrity errors). The SKU is
     stored as **data, not identity** — the SKU→Variant ID
     association is derived and validated, never the lookup key
     (D-015/D-017 unchanged).
  3. **Field classes:** immutable (canonical key, creation
     timestamp); write-once (Woo ID/slug at creation — changed only
     through the stale-recovery flow); mutable metadata (status
     active/stale/orphaned, last-verified, notes).
  4. **Creation:** approved deterministic tooling only, inside a
     human-promoted sync flow; categories/terms pre-seeded from the
     owner-approved registries (D-031/D-032) by create-if-absent on
     exact keys; products/variations create only on registry miss;
     D-027 event per creation; D-026 provenance per entry.
  5. **Updates:** Woo IDs never updated in place — replacement goes
     through stale + human review + a new entry; metadata maintained
     by tooling, logged.
  6. **Lookup:** exact key → single active entry; no fuzzy matching,
     no name search, no confidence scoring; deterministic second
     guard (read Woo by stored external reference) before any create;
     a hit without a registry entry = duplicate-resource conflict →
     human review, never silent adoption.
  7. **Missing/stale/conflicting/orphaned states:** missing = normal
     pre-create path; stale = entry marked (never deleted), re-link
     after human review; conflicting = integrity error → human
     review, never silently re-linked; orphaned = flagged for human
     decision (hide/preserve by default; destructive cleanup needs
     explicit approval, RULES §22).
  8. **Provenance/idempotency:** entries carry D-026 provenance
     (append-only); the registry is the identifier-level (D-017) half
     of operational idempotency — distinct from D-027 event-level.
- **Rationale:** The complete deterministic linkage model that makes
  duplicate prevention and safe reconciliation possible; physical
  storage technology remains implementation-deferred.
- **Source:** D-014, D-015, D-017, D-026, D-027, D-034, D-042, D-044;
  PROJECT_RULES §10, §22, §25; human owner approval (2026-09-12).

## D-047 — Field-level sync contract & CRUD contract

- **Status:** **Approved** (2026-09-12, human owner)
- **Decision:** The field-level synchronization contract and the
  product/variation CRUD contract, as specified in full in
  `docs/phases/phase-03-2-woocommerce-sync-architecture.md` §3–§4
  and §7:
  1. **Field-level rules** for every synced field group (identity,
     names, descriptions, categories, Color, Size, prices/sale
     prices, lifecycle, publication, media, inventory, SEO,
     non-registry attributes): canonical owner, Woo projection,
     direction (always PM → Woo; Woo IDs back to the registry),
     allowed write actor (approved deterministic tooling), Woo-side
     manual edits not allowed (divergence → review queue, canonical
     value preserved, optional human-authorized re-projection —
     never silent overwrite, never Woo-as-truth), UNKNOWN/
     NOT_PROVIDED behavior preserved per field, AI may
     propose/draft/suggest only (Yellow, provenance-tagged),
     deterministic tooling executes only within human-promoted flows,
     approval = run promotion (Red tier where the field is
     publication- or price-affecting). **No default bidirectional
     sync anywhere** (D-042). Inventory is Woo-owned; PM never
     writes stock (D-041). SEO slug stays unprojected while the
     language gate is open (D-016.M).
  2. **CRUD contract:** Create/Update/Read Product, Create/Update/
     Read Variation, hide/withdraw/archive behavior — each with
     preconditions, canonical validation, registry lookup, D-027
     idempotency key, payload validation, post-write read-back
     verification, failure handling per D-044, compensation concept
     (hide + flag; **no destructive delete by default**, RULES §22),
     and audit/provenance. `draft` products have no Woo record (D-039);
     reads are verification/reconciliation only — never a source of
     business truth.
- **Rationale:** One deterministic, per-field operational contract
  implementing D-042's direction rules without opening any
  bidirectional drift surface.
- **Source:** D-021–D-023, D-026, D-027, D-034–D-045; PROJECT_RULES
  §22, §24–§25, §32; human owner approval (2026-09-12).

## D-048 — Price-sync architecture (D-038 sub-gate resolution)

- **Status:** **Approved** (2026-09-13, human owner) — **Option A:
  canonical-layer projection.**
- **Decision:** Resolves the D-038 open sub-gate with
  **Option A — canonical-layer projection ("materialize at sync")**:
  approved deterministic tooling computes the D-024/D-025 effective
  price resolution and writes it into the WooCommerce fields Woo
  actually displays (variation `sale_price`/`regular_price`) at every
  affected change; base/list and override fields are never mutated;
  sale-expiry is handled by deterministic scheduled re-projection
  (surfaced, logged, bounded — never silent). Full problem analysis,
  candidate comparison (A/B/C), and consequences:
  `docs/phases/phase-03-2-woocommerce-sync-architecture.md` §1.
- **Why this is a technical consequence, not a new business rule**
  (stated explicitly per the batch instruction): D-003 + D-024/D-025
  already fix the canonical price resolution as ours, and D-042
  already fixes the direction (PM → Woo projection, never Woo → PM
  for PM-owned fields). Option A changes no price value, no
  precedence, and no approval tier — it only chooses *where* the
  approved resolution is rendered. Option B would invent a new
  business restriction (owner-gated); Option C would knowingly
  display a price contradicting D-024 (a hidden failure on a Red-tier
  value, RULES §24/§41). The owner gate is limited to confirming this
  architectural reading.
- **Consequences if approved:** Woo price fields for PM-owned
  products become projections (never canonical, never hand-edited as
  truth — Woo-side price edits are Red-tier divergences); canonical
  inputs unchanged; every price-affecting write stays Red tier inside
  human-promoted flows; AI never executes; D-038's pre-write
  validation unchanged; exact Woo sale-date field semantics verified
  at implementation.
- **Owner approval (2026-09-13):** Option A approved as recorded;
  alternatives B (config constraint) and C (accept Woo-native display
  with human review) were not chosen. D-024/D-025 remain untouched.
- **Source:** D-010, D-024, D-025, D-038, D-042, D-044; PROJECT_RULES
  §11, §24, §32, §41; batch design (2026-09-12); owner approval of
  Option A (2026-09-13).

## D-049 — Media storage direction

- **Status:** **Approved** (2026-09-12, human owner) — architectural
  direction approved; the concrete **provider/hosting decision remains
  OPEN** (Phase 4, register row 6).
- **Decision:** Architectural direction = **external/object storage +
  Woo references** (options and analysis:
  `docs/phases/phase-03-2-woocommerce-sync-architecture.md` §9).
  Media binaries live in dedicated object storage independent of the
  WordPress install; WooCommerce holds references (featured + gallery
  per D-040). Rationale: media stays portable across store
  migrations/rebuilds (D-001 reusability, RULES §35), the backup/
  restore story stays clean (MASTER_PLAN §10), and image-heavy
  catalogs do not burden WP-instance disk/bandwidth (relevant for
  Iranian hosting constraints). Woo Media Library was rejected as the
  primary store (media entangled with the WP instance; migration/
  restore burden), and the hybrid option was rejected (two sources of
  truth for media). No storage is set up in this batch; file identity
  and duplicate prevention (content-hash dedupe), alt text (D-040),
  and CDN choices are implementation-phase decisions under Phase 4.
- **Source:** D-001, D-040, D-033; MASTER_PLAN §10; PROJECT_RULES §35;
  human owner approval of the direction (2026-09-12).

## D-050 — Green/Yellow/Red authority matrix for WooCommerce operations

- **Status:** **Approved** (2026-09-12, human owner)
- **Decision:** The operational tier classification for Woo
  operations (`docs/phases/phase-03-2-woocommerce-sync-architecture.md`
  §8):
  1. **Green (autonomous):** reads; deterministic validation;
     registry/safe lookups; dry-run computation; conflict/diff
     detection and reconciliation *reporting*.
  2. **Yellow (monitored):** reversible non-destructive projections
     (hidden-record creation/updates; category/attribute/metadata
     data on hidden records); low-risk metadata updates; alt-text and
     AI-proposed enrichments queued for human review.
  3. **Red (explicit human authorization):** publication projection
     (`published`); withdrawal; **any price-affecting write** (list/
     override/sale projections); inventory-changing operations
     (future); destructive delete; archive/reactivate execution; any
     operation resolving a critical conflict.
  Rules: media attachment to *hidden* records = Yellow; media changes
  affecting a `published` record = Red. When an operation spans
  tiers, the highest tier applies. AI remains propose/prepare-only;
  approved tooling executes Red operations only inside human-promoted
  flows.
- **Rationale:** Makes the abstract RULES §32 tiers concrete and
  checkable per WooCommerce operation without granting AI or tooling
  any new authority.
- **Source:** MASTER_PLAN §9; PROJECT_RULES §32–§33; D-022, D-023,
  D-039, D-042; human owner approval (2026-09-12).

## D-051 — Non-registry attribute representation

- **Status:** **Approved** (2026-09-12, human owner)
- **Decision:** The Woo representation of the product-level attributes
  outside Registry v1 — Brand, Material, Pattern, Style, Season,
  Usage, Collar, Sleeve, Length, Closure, Fit:
  1. **Canonical:** each remains a canonical structured product field
     (free text, outside Registry v1 — D-029/D-031 unchanged; **no
     new controlled vocabulary is created automatically**).
  2. **Woo representation: product meta** (meta/custom fields on the
     product record) — **not** global attributes (that would imply
     store-wide vocabularies and D-019 term governance the owner has
     not granted) and **not** per-product custom attributes (would
     scatter representation); one deterministic meta representation
     with provenance-tagged values.
  3. **Promotion path unchanged:** a future owner decision promoting
     an attribute into a controlled vocabulary can then move its Woo
     representation to a global attribute (D-019/D-029 governance
     applies).
  4. **Color and Size unchanged:** exactly the D-037 variation-
     defining global attributes; nothing here touches them.
  5. Values never invented: NOT_PROVIDED = field omitted; AI may
     suggest values (Yellow, provenance-tagged).
- **Rationale:** Closes the representation question without creating
  vocabularies or expanding variation semantics.
- **Source:** D-018, D-019, D-029, D-031, D-037; human owner approval
  (2026-09-12).

## D-052 — Test/sandbox strategy

- **Status:** **Approved** (2026-09-12, human owner) — the strategy is
  approved; **execution belongs to Batch 3+** and precedes any real
  connection.
- **Decision:** The safe testing strategy before any real Woo
  connection
  (`docs/phases/phase-03-2-woocommerce-sync-architecture.md` §11):
  1. Local/unit validation of canonical data and payload builders
     (D-021/D-024/D-025/D-033 rules) — no network.
  2. Deterministic mock Woo responses covering the D-043 resource
     areas with deliberate success/failure/duplicate/timeout/malformed
     cases per the D-044 classes.
  3. A separate isolated staging Woo instance (RULES §18) with
     throwaway credentials — never production.
  4. Clearly-named test fixtures inside staging only; never real
     business data.
  5. Failure simulation: unavailable, auth failure, validation
     failure, timeout-before-response, ambiguous timeout (read-back
     reconciliation), rate limiting, partial batch, malformed
     response.
  6. Duplicate-event simulation: identical (source, event ID) →
     skipped_duplicate; conflicting payload → integrity error;
     double-create attempts blocked by the registry.
  7. Conflict simulation across the D-044 classes (§6) → correct
     review-queue routing, no silent resolution.
  8. Price-divergence simulation: the D-048 case + expiry
     re-projection window.
  9. Rollback/compensation tests: hide-and-flag compensation;
     registry stale/recreate flows.
  10. **Production-readiness gate:** all of the above green + human
      review of the test report before any production credential
      exists (RULES §23, §43).
- **Source:** PROJECT_RULES §18, §23, §43; D-043, D-044; human owner
  approval (2026-09-12).

## D-053 — Local-first development environment & promotion model

- **Status:** **Approved** (2026-09-13, owner directive: the project is
  now explicitly LOCAL-FIRST).
- **Decision:** All Phase 3 implementation and testing happens first in
  a **local development environment** (macOS development machine:
  WordPress + WooCommerce, database, n8n, project services, mock/test
  services), then promotes along **Local → Staging → Production**
  without redesign ("change configuration, not business logic").
  Normative design: `docs/phases/phase-03-3-local-development-
environment.md`. Business rules, canonical schemas/contracts, sync/
  CRUD/idempotency/conflict contracts (incl. **D-048 Option A**
  projection behaviour), validation, authority tiers, adapter
  interfaces, and log format are **identical across environments**;
  URLs, credentials, storage provider, seed/test data, observability
  settings, and sizing are **per-environment**. A local development
  stack is development tooling (D-007, RULES §18/§43, MASTER_PLAN
  §11) — it does **not** open Phase 4: no hosting/VPS selection, no
  production infrastructure, and staging/production env files are
  created only in their own phases.
- **Rationale:** Directly implements the owner directive and the
  approved environment-separation ladder; makes promotion a
  configuration change rather than a redesign.
- **Source:** D-001, D-007, D-012, D-013, D-042, D-047, D-050, D-052;
  MASTER_PLAN §11/§16; PROJECT_RULES §18, §43; owner directive
  (2026-09-13).

## D-054 — Local runtime technology (Docker Compose)

- **Status:** **Approved** (2026-09-13, human owner).
- **Decision:** **Docker Compose** is the default local
  runtime: one declarative stack for `wordpress` (with WooCommerce),
  `woodb` (MySQL/MariaDB), `canonical-db` (per D-055), `n8n`, the
  media store (per D-056), and the `mock-woo` adapter; named volumes
  (`woo_data`, `canonical_data`, `n8n_data`, `media_data`); shared
  internal network; **localhost-only** published ports; documented
  destroy/recreate reset. Alternatives analyzed and rejected: native
  macOS installs (host drift, manual version pinning, poor reset/
  portability for 6+ cooperating services) and a remote dev VPS
  (Phase 4 hosting territory; violates local-first). Optimizes for
  reproducibility, easy reset, portability, similarity to future
  server deployment, and low operational complexity (RULES §44).
  The Compose stack and local scaffolding were implemented in Phase 3
  Batch 4 (`local/infra/docker-compose.yml`; `local/README.md`) after
  this approval.
- **Source:** D-007, D-013, D-053; PROJECT_RULES §18, §44; batch
  design (2026-09-13); owner approval (2026-09-13).

## D-055 — Canonical project data storage (relational application
 database)

- **Status:** **Approved** (2026-09-13, human owner; database
  architecture per RULES §4 approval flow).
- **Decision:** Canonical project data (Product Master
  entities, mapping registry, event/idempotency store, provenance)
  is stored in a **relational application database — PostgreSQL** —
  locally, as **logically separate schemas in one physical local
  instance** (staging/production may separate instances later without
  schema change). Rejected alternatives: structured local files
  (cannot enforce the approved D-046 bidirectional uniqueness, D-027
  atomic (source, event ID) keying, or D-026 append-only semantics
  without hand-building a database — RULES §5) and WooCommerce as
  canonical (**forbidden** — contradicts D-003/D-042: Woo is the
  projection target, never our canonical store). The approved
  uniqueness/idempotency/provenance constraints are enforced natively
  by the database. This choice changes no business rule — it only
  fixes the physical mechanism for the already-approved logical
  model (DATA_MODEL §13); the initial physical schema was implemented
  in Phase 3 Batch 4 (`local/db/schema.sql`).
- **Source:** D-015, D-017, D-026, D-027, D-034, D-046; DATA_MODEL
  §13; PROJECT_RULES §4, §5, §21; batch design (2026-09-13); owner
  approval (2026-09-13).

## D-056 — Local media storage (S3-compatible emulator)

- **Status:** **Approved** (2026-09-13, human owner).
- **Decision:** The local equivalent of the approved
  D-049 media direction is an **S3-compatible object-storage emulator
  (e.g. MinIO)** inside the local stack, behind the same adapter
  boundary the real Phase 4 provider will use — swapping emulator →
  real provider later changes only endpoint/credential configuration,
  never business logic (RULES §35). Woo holds references (featured +
  gallery per D-040); binaries never enter Git. Rejected: direct Woo
  media library even locally (would contradict the approved D-049
  direction and bake in a second pattern) and a plain filesystem
  (loses the object-API surface). Content-hash dedupe and file
  identity are implementation details (D-049 notes); the **real
  production media provider remains OPEN/Phase 4 (owner-gated)** —
  this decision covers the local emulator only.
- **Source:** D-033, D-040, D-049, D-053, D-054; PROJECT_RULES §35,
  §16; batch design (2026-09-13); owner approval (2026-09-13).

## D-057 — Size-code conflict resolution: Alpha L → `LRG`

- **Status:** **Approved** (2026-09-13, human owner) — formal
  resolution of the D-030 ↔ D-032 conflict tracked as register
  row 24; supersedes the D-032 Alpha-L **code only** (the display
  label stays `L` per D-020 rule 4; every other D-032 mapping is
  unchanged).
- **Decision:** The canonical SKU code for Alpha size **L** is
  **`LRG`** — uppercase Latin ASCII, one code per the active term,
  deprecate-and-replace per D-030 rule 5.
- **Owner rationale:** `LRG` eliminates the ambiguous single
  character `L` while avoiding collision with the `LG` brand prefix
  or variant tokens.
- **Honest governance note (recorded by implementation, 2026-09-13):**
  D-030 rule 1 forbids `O`, `I`, or `L` **in any position** ("no
  exception is created"), and `LRG` itself contains `L` in position
  1 — so under the rule's literal wording this code is **not**
  O/I/L-safe. It is implemented as an **explicit, auditable owner
  sanction** (`OWNER_SANCTIONED_CODES` in `local/canonical/vocab.py`,
  citing this decision) — the strict validator is untouched and
  nothing was silently rewritten. A **D-030 wording clarification**
  (e.g. the prohibition targeting the standalone confusable
  characters) is recommended as a non-blocking owner follow-up;
  until then D-057 and D-030 coexist exactly as recorded here.
- **Mechanism:** D-030 rule 5 (deprecate + replace). The superseded
  code `LG` was never referenced by any real product/SKU (no
  production data exists), so the replacement is clean — no
  migration, no alias, no equivalence link. The governance guard in
  `local/canonical/vocab.py` (`CODE_CONFLICTS`) is now empty and the
  O/I/L seed gate remains armed for any future conflict. The full
  **28/28 size vocabulary now seeds**; Alpha-L sync is unblocked.
- **Source:** D-014 rule 7, D-020 rule 4, D-030 rules 1 & 5, D-032;
  owner instruction (2026-09-13).

## D-058 — Phase 4 infrastructure gates: formal owner deferral

- **Status:** **Approved** (2026-09-14, human owner, via System
  Architecture Strategy instruction) — overall disposition
  **DEFERRED (local-first development strategy)**.
- **Decision:** All seven Phase 4 infrastructure gates (G1 hosting/VPS,
  G2 WP/Woo instance model, G3 media provider, G4 backups, G5
  domain/DNS/SSL, G6 observability, G7 environment promotion — as
  defined in `docs/phases/phase-04-infrastructure-brief.md`) are
  **deferred until product operational validation concludes**. No
  production infrastructure is provisioned; nothing local closes a
  production gate (D-053: the local stack is not staging).
- **Rationale (owner):** the core engine, live-DB integration, and the
  HITL verification loop with D-026 provenance are 100% operational
  locally; hosting procurement adds no value until the product is
  operationally validated.
- **Consequences:** register items 6 (hosting/VPS), the media-provider
  sub-gate of item 5, and item 8 (secret tooling) remain **Open** —
  deferral is scheduling, not resolution. Reopening trigger: owner
  concludes operational validation; the brief's suggested order then
  applies (G1+G2 → G5 → G3 → G4 → G6/G7). Each reopened gate still
  requires its own decision record.
- **Closure evidence:** `docs/reports/
  phase-4-infrastructure-gates-status.md` (exit criteria all PASSED
  2026-09-14: stack 5/5 healthy, smoke 12/12, 105+32 tests with 0
  skipped, queue 0 pending of 16 with attributed provenance).

## D-059 — Phase 5 naming & sequencing: n8n Foundation vs content platform

- **Status:** **Approved — Option A** (2026-09-14, human owner):
  execute the plan's **Phase 5 = n8n Foundation first**; Workstream B
  (content creation & posting automation) remains **deferred to its
  proper later phases** (Phase 15, with Phase 9 surfaces).
- **Situation:** MASTER_PLAN §13 defines **Phase 5 = n8n Foundation**.
  The kickoff instruction titled Phase 5 "Content Creation & Posting
  Automation Platform" — a real workstream that per the plan belongs
  to Phase 15 (Marketing Automation) with Phase 9 surfaces, and which
  **depends on the n8n foundation** (TODO: "n8n workflows — blocked,
  Phase 5").
- **Recorded:** kickoff roadmap at `docs/reports/
  phase-5-kickoff-and-roadmap.md` — Phase 5 (n8n foundation, M1–M4,
  design-first, local-only) plus the content platform as
  **Workstream B (PROPOSED)** with its five pillars and four
  milestones preserved verbatim in intent; M1 execution spec at
  `docs/reports/phase-5-m1-n8n-foundation-spec.md`.
- **Owner options:** ~~A (recommended)~~ **APPROVED** — plan's
  Phase 5 first, Workstream B opens Phase 15; B — run Workstream B's
  schema/template work in parallel, deferring its
  orchestration/adapters (not chosen); C — amend MASTER_PLAN §13
  renumbering (not chosen).
- **Constraints:** local-only, no credentials, no external
  connections; AI authority boundaries unchanged.

## D-060 — HITL/incident system of record & Notion integration boundaries

- **Status:** **Approved — Option A** (2026-09-15, human owner;
  amended same day — lifecycle extension + idempotency-key
  refinement): the canonical PostgreSQL layer remains the durable
  system of record for HITL/incidents and their D-026 provenance;
  Notion receives a mirror/view. The content-idea lifecycle is
  approved in its extended form (see Owner gates below).
- **Situation:** Phase 6 (Notion Business OS) kickoff draft proposed
  Notion as "the single source of truth for business state" and a
  `Notion Page ID + Last Updated Timestamp` idempotency key. Both
  conflict with approved architecture: canonical business data is
  PostgreSQL (D-055; D-048 Option A), and a last-updated timestamp in
  a D-027 key makes the key different on every edit — dedupe silently
  fails (same defect class fixed in the Phase 5 M1 review).
- **Disposition (Option A, APPROVED):** Notion = Business
  OS / knowledge layer (SOPs, ideas, calendar, dashboards, review
  *surfaces*); canonical PostgreSQL remains the durable system of
  record for HITL/incidents and their D-026 provenance; Notion
  receives a mirror/view. Idempotency key (refined 2026-09-15):
  `SHA256('notion' + page_id + event_type + revision_marker)` where
  `revision_marker` is the source-provided revision identifier
  carried in the event payload — NOT wall-clock time. The plain
  `(page_id, event_type)` key collapsed legitimate repeated
  transitions (Draft → Review → Draft → Review: the second Review
  event would be silently dropped); the marker keeps retry dedupe
  intact (a retry of the same delivery yields the same marker, while
  distinct revisions yield distinct keys). The marker's concrete
  source field is **owner-gated pending Notion API connectivity
  verification** and unverified until that check runs;
  `last_edited_time` remains change-detection metadata only, never
  key material. No n8n
  write-back to Notion by default — any future write-back carries its
  own D-050 tier classification and human-approval marker.
- **Option B (not chosen):** the Notion database itself is the
  HITL/incident record with sync-back into canonical tooling — weaker
  integrity guarantees, split provenance, added sync-conflict surface.
- **Recorded:** kickoff roadmap at `docs/reports/
  phase-6-kickoff-and-roadmap.md` (entity sketches, authority matrix,
  milestones M1–M4, corrected gates).
- **Owner gates:** ~~ruling on Option A vs B~~ **APPROVED (Option A,
  2026-09-15)**; ~~content-idea lifecycle~~ **APPROVED — extended
  form**: `Backlog → Researching → Draft → Review → Approved →
  Scheduled → Published`, plus terminal `Rejected` (reachable from
  any pre-Approved state) and terminal `Archived` (reachable from
  Published or Rejected). Rationale: Approved is not time-bound, so
  `Scheduled` is required before a publishing queue can act; without
  terminal Rejected/Archived, items accumulate in Review indefinitely
  and the HITL queue grows without bound. Revision-marker source
  field: owner-gated pending Notion API connectivity verification.
  Any future Notion workspace/credential creation remains
  owner-gated (D-045/D-053) — no workspace automation in this phase
  until explicitly opened.

## D-061 — Postgres undefined_table classification (D-052 taxonomy)

- **Status:** **Accepted — observation registered, no logic change**
  (2026-09-15, human owner via batch instruction).
- **Situation:** Phase 5/6 drill observation: Postgres
  `undefined_table` errors (e.g. `relation … does not exist`) carry
  no D-052 Class-B keywords, so the canonical classifier
  (`local/canonical/n8n_failure_taxonomy.js`) conservatively routes
  them to Class E (unknown/ambiguous → deterministic reconciliation
  → human review).
- **Decision:** keep `undefined_table` in **Class E (human review)**.
- **Rationale:** safe-by-default — Class E never blind-retries and
  always surfaces for human review; Class-B keywords stay reserved
  for genuine data-invariant violations. No change to the
  parity-embedded workflow logic (byte-identical embeds and their
  tests remain untouched).
- **Candidate extension (future batch only):** logged as a candidate
  Class-B extension for a future batch; no shipped-logic change now.
  If live-router telemetry later shows undefined_table volume that
  justifies Class-B routing, propose the classifier extension as a
  new decision record (with parity tests and embed regeneration).

## D-062 — AI runtime: provider-neutral router + strict output contracts

- **Status:** **Approved** (2026-09-15, owner-approved; drafted 2026-09-15
  Freebuff Phase 7 M1)
- **Situation:** Phase 7 needs a model/AI-provider integration layer
  (MASTER_PLAN §13). Without a boundary, vendor SDKs would leak into
  canonical code, model output would flow unvalidated into business
  flows, and credentials would sprawl.
- **Proposal:** adopt the RULES §35 provider-neutral pattern for AI:
  an `AiProvider` interface with `MockAiProvider` as the local
  implementation (D-053); a deterministic pure-data routing policy
  (task → provider/model/schema/budget); and strict, versioned JSON
  Schema contracts for every AI output that may enter a canonical flow
  (`additionalProperties:false` everywhere; unknown schema keywords
  are load-time errors — contract drift cannot silently widen).
  Initial contracts: `content_idea_proposal.v1`, `caption_proposal.v1`,
  `product_description_enrichment.v1` (frozen fixture parity-pinned).
  Validation failure of model output = D-052 Class B (never silently
  repaired). No credentials exist or are requested (D-045).
- **Consequences:** real OpenAI/Anthropic/local-model adapters become
  drop-in `AiProvider` implementations with zero structural rewrites;
  contract changes require fixture + amendment.

## D-063 — AI cost accounting and budget guardrails

- **Status:** **Approved** (2026-09-15, owner-approved; drafted 2026-09-15
  Freebuff Phase 7 M1)
- **Situation:** AI calls cost money and can runaway; the project has
  no mechanism yet to meter or cap them.
- **Proposal:** static tariff table per (provider, model); unknown
  tariff ⇒ cost 0 + explicit `unknown_tariff` flag (never guessed);
  append-only usage ledger (every call: tokens, cost estimate,
  latency, status, correlation id — local JSON now, PostgreSQL mirror
  later, D-055); per-task budgets with deterministic pre-dispatch
  enforcement: ≥80% soft ⇒ `budget_warning` on the response, 100% hard
  ⇒ refusal BEFORE the provider call (Class-B guardrail); local
  token-bucket rate limiter, refusals Class A (retryable) per D-052's
  429 mapping. Spend tracking is always active (tested), never
  ledger-gated.
- **Consequences:** overrun becomes structurally impossible without a
  budget change; tariff updates are config changes, not code.

## D-064 — AI proposals: authority pipeline and HITL integration

- **Status:** **Approved** (2026-09-15, owner-approved; drafted 2026-09-15
  Freebuff Phase 7 M1)
- **Situation:** D-050 defines tiers for actions; Phase 7 needs the
  concrete pipeline that keeps AI output proposal-only.
- **Proposal:** AI output leaves the runtime ONLY as an `AiProposal`
  envelope (schema id + validated payload + provider/model + usage +
  cost + D-026 `AI_GENERATED` provenance id + correlation id);
  proposals enqueue into the existing HITL VerificationQueue
  (D-028/D-060 surface); approval is a human review-state advance;
  no Red operation (Woo projection, price, publication, vocabulary
  mutation) is reachable from the AI runtime module — asserted by an
  import-graph test in `test_phase7_ai_runtime_m1.py` that fails the
  battery if the boundary erodes.
- **Consequences:** prompt injection / model misbehavior blast radius
  is one rejected HITL item; M2 wires the approve/reject round-trip.

## D-065 — Unified AI observability and audit trail

- **Status:** **Approved** (2026-09-16, owner-approved)
- **Situation:** Phase 7 metered usage per call (D-063 ledger) but
  there is no unified, correlation-keyed view across the proposal
  lifecycle, and no cost reporting for HITL outcomes.
- **Decision:** structured JSON observability records (schema
  `ai.observe.v1`) keyed by one `correlation_id` end-to-end (provider
  call → validation → divergence → lifecycle transition → HITL
  decision → canonical apply); metrics: `prompt_tokens`,
  `completion_tokens`, `latency_ms`, `estimated_cost_usd`,
  `divergence_rate`, `hitl_decision` (approve / reject / edit / none);
  collector is append-only and persisted in the local observability
  store; a cost-report view aggregates per task/provider/day. The AI
  surface gains NO write path to publication or Woo resources — the
  collector is called BY the deterministic pipeline, never BY the
  model output.
- **Consequences:** every AI action is reconstructable and cost-
  attributable from logs alone; observability is read-only for the AI
  surface (battery-asserted); correlation ids ride inside AiProposal
  envelopes and lifecycle events, not invented by the model.

## D-066 — Owner-gated live provider connectivity and budget quarantine

- **Status:** **Approved** (2026-09-16, owner-approved; connectivity
  itself remains OFF until the owner supplies credentials)
- **Situation:** D-062 left live providers as drop-in interfaces; row 9
  of the register gates actual vendor selection. Phase 8 needs the
  concrete adapters and the safe-enablement path WITHOUT touching
  credentials (D-045: none exist, none requested).
- **Decision:** official OpenAI/Anthropic adapters under the D-062
  `AiProvider` interface; activation requires BOTH `AI_LIVE_ENABLED=true`
  AND a valid API key present in the environment — otherwise the
  adapter refuses to construct. Automatic isolation: missing key or a
  401/429-style provider error causes graceful fallback to the local
  MockAiProvider (observability records the fallback; tests never
  stop). Budget quarantine: when daily spend reaches the configured
  cap the router HALTS (BUDGET_EXCEEDED_HALT, Class-B guardrail
  refusal) BEFORE any dispatch — already the D-063 property, now the
  named production behavior. Network clients are injectable and are
  mocked in tests: zero network leakage in the battery (D-053).
- **Consequences:** enabling live AI is a configuration + owner
  action, never a code change; fallback is observable and idempotent;
  no secret ever enters Git, docs, prompts, or logs (D-045).

## D-067 — Prompt and template versioning registry

- **Status:** **Approved** (2026-09-16, owner-approved)
- **Situation:** prompts currently live inside task code; quality
  regression and reproducibility need versioned, hashed templates
  separate from executable code.
- **Decision:** prompts/templates move to a versioned registry
  (`local/templates/`, semver-tagged `vX.Y.Z` directories); the
  registry enforces strict JSON-Schema templates (same D-062 subset),
  monotonic semver (no overwrite of a shipped version), and content
  hashes; every `AiRequest`/`AiProposal` carries `template_id` +
  `template_hash` so any proposal is reproducible and quality
  regressions are attributable to a template change. Template
  activation (which version a task routes to) is deterministic
  configuration, not model choice.
- **Consequences:** changing a prompt is a registry commit with a new
  version, never an edit to shipped logic; the router refuses
  unregistered template ids (Class-B); hash mismatches fail loudly.

## D-068 — HITL review inbox and bulk action orchestrator

- **Status:** **Approved** (2026-09-16, owner-approved)
- **Situation:** M2–M3 Phase 7 decisions are one-at-a-time through
  `ProposalLifecycle.decide()`; at proposal volume the owner needs a
  review inbox with bulk operations that respect idempotency and the
  divergence guardrails.
- **Decision:** a centralized `HitlReviewService` over the existing
  lifecycle + VerificationQueue (no new authority surface): lists a
  deterministic review inbox; supports single AND bulk
  approve/reject/edit with per-item idempotency (identical re-decision
  = skipped_duplicate, conflicting re-decision refused — the M2
  semantics, unchanged); bulk operations are all-or-nothing per item
  (each item independently decided or left pending — never partially
  applied state); human edits are re-validated through the D-062
  contracts + divergence guardrails before acceptance; every decision
  records D-026 provenance with the acting reviewer. No auto-advance:
  the service can never decide without an explicit reviewer.
- **Consequences:** bulk review is auditable and replayable; the M2
  terminal-immutability guarantee is preserved verbatim; the service
  is the single entry point used by M4 end-to-end integration.

## D-073 — Telegram content & formatting contract

- **Status:** **Approved** (2026-09-16, owner-approved)
- **Situation:** MASTER_PLAN Phase 10 calls for official Telegram
  Bot API integration; Telegram's formatting and payload rules are
  stricter and more heterogeneous than other channels (per-type
  caption/text limits, album batching, MarkdownV2 escaping), so the
  contract must be validated LOCALLY before dispatch.
- **Decision:** implement Telegram Bot API media payload schemas for
  Text, Photo, Video, Document, and MediaGroup (album ≤ 10 items);
  strict local parsing/escaping for MarkdownV2 and HTML before any
  network call; local constraint enforcement — caption ≤ 1024 chars
  for media, text ≤ 4096 chars, album ≤ 10 items, file size ≤ 50 MB
  (Bot API limit), chat_id and media required per type. Invalid
  payloads are rejected locally as Class-B prevention — a payload
  that cannot be valid never consumes Bot API quota.
- **Consequences:** formatting regressions surface as local Class-B
  errors instead of silent mojibake at Telegram; the contract is
  testable end-to-end on the mock adapter; no credential exists and
  none is requested (D-045).

## D-074 — Telegram idempotency vault and rate-limit engine

- **Status:** **Approved** (2026-09-16, owner-approved)
- **Situation:** double-posting to a Telegram chat (owner channel /
  customer groups) is a public, visible failure; Telegram also
  enforces hard rate limits (global ~30 msgs/sec, per-chat ~1 msg/sec
  with 429 `retry_after`), so a dispatcher that ignores pacing gets
  throttled and drops posts.
- **Decision:** deterministic `telegram_publish_idempotency_key` =
  SHA-256 over (chat_id, content_id, media_hash, text_hash,
  scheduled_slot); atomic PostgreSQL-backed exclusive lock table
  `telegram.publish_lock` (PK-as-lock, same semantics as D-070)
  preventing double-dispatch under concurrency or dispatcher
  restart; built-in rate pacer enforcing global 30 msgs/sec and
  per-chat 1 msg/sec via token-bucket pacing BEFORE dispatch — the
  pacer schedules, it never drops.
- **Consequences:** absolute double-post protection across restarts
  and concurrent dispatchers; bot never exceeds Telegram pacing;
  retry dedup stays intact while deliberate re-publication remains
  possible via a distinct scheduled_slot.

## D-075 — Owner-gated Telegram Bot API adapter and token boundary

- **Status:** **Approved** (2026-09-16, owner-approved)
- **Situation:** the Bot API token IS the credential and appears in
  every Bot API URL (`bot<token>/…`); naive logging leaks it, so the
  boundary must be structural, not advisory.
- **Decision:** `MockTelegramAdapter` with deterministic test
  controls (429 with retry_after, migrate-to-supergroup 400,
  bot-kicked/blocked 403, chat-not-found 400, timeout); \
  `LiveTelegramAdapter` behind `TELEGRAM_LIVE_ENABLED=true` + token
  presence, with injectable HTTP transport (zero network in tests);
  automatic redaction of `bot<token>` URL patterns, raw tokens, and
  `Authorization` material from every log, URL, error trace, and
  observability record (D-045/D-065).
- **Consequences:** live sending is impossible without owner action;
  all failure modes are reproducible locally; a token can never
  reach a log through an adapter error path.

## D-076 — Telegram publishing outbox and DLQ classifier

- **Status:** **Approved** (2026-09-16, owner-approved)
- **Situation:** publishing must survive process restarts and
  Telegram-side transients without duplicating or dropping posts;
  Telegram's error taxonomy maps cleanly onto D-052.
- **Decision:** transactional outbox on the canonical D-027 event
  store (same pattern as D-072); error classification aligned with
  D-052 — Class-A (network timeout / 5xx) exponential backoff retry;
  Class-B (invalid parse mode, malformed payload, local contract
  violation) terminal reject to DLQ without retry; Class-C (429 /
  `retry_after`) dynamic pause honoring Telegram's exact value, then
  requeue; Class-E (bot blocked/kicked, token revoked, chat not
  found) queue freeze + HITL alert (D-026 provenance-linked). Every
  outcome is durably recorded; unrecoverable failures land in the
  DLQ with redacted audit entries.
- **Consequences:** no silent drops; retry storms impossible;
  Telegram pacing feedback (retry_after) is respected exactly;
  recovery from Class-E requires a human decision.

## D-101 — Canonical insight contract and analyst state machine

- **Status:** **Approved** (2026-09-17, owner-approved)
- **Situation:** Phases 12/13 produce durable metrics (orders,
  revenue, publication outcomes) but nothing turns them into
  decision-grade business insight; ad-hoc conclusions would lack
  provenance and could bypass human authority.
- **Decision:** a canonical `BusinessInsight` — insight_id,
  category, severity, metric_refs, actionable_payload,
  confidence_score, correlation_keys, status — plus a `Recommendation`
  shape carried in the payload. Lifecycle GENERATED → EVALUATED →
  then DISPATCHED_TO_HITL | AUTO_ACCEPTED | DISMISSED, with
  SUPERSEDED as a marker reachable from any non-terminal state when
  a later insight covers the same correlation keys. Every transition
  is a D-027 event with full provenance. Derivation is deterministic:
  rule evaluation over DURABLE metrics and snapshots only, injected
  evaluators, zero wall-clock reads.
- **Consequences:** every recommendation traceable to the exact
  metric windows that produced it; the AI-analyst boundary stays
  inside D-050 (the analyst proposes, only humans or explicitly
  auto-accept-safe rules decide).

## D-102 — Analyst engine and rule evaluation vault

- **Status:** **Approved** (2026-09-17, owner-approved)
- **Situation:** insight evaluation must never mutate business state
  in the same step that generates it, and duplicate insights over
  the same evidence must collapse deterministically.
- **Decision:** `AnalystEngine` with STRICT separation between rule
  evaluation (pure: metrics in, insight proposal out) and decision
  application (durable: dedup, status, audit). Insight idempotency =
  SHA-256 over (category, correlation_keys, metric window refs);
  atomic dedup via PostgreSQL `analytics.business_insight` unique
  constraint with a JSON parity backend. Incomplete metric contexts
  (missing refs, empty windows) and negative/over-unity confidence
  scores are Class-B rejections BEFORE any durable write.
- **Consequences:** evaluation is testable without storage;
  re-deriving the same insight is idempotent, not a new row.

## D-103 — Cross-domain correlator and anomaly detection worker

- **Status:** **Approved** (2026-09-17, owner-approved)
- **Situation:** publishing engagement (Phase 9–11), scheduling
  density (Phase 15) and order velocity (Phase 12) live in separate
  event streams; anomalies spanning them need a reconciliation-style
  worker that cannot silently fire business actions.
- **Decision:** an `AnomalyScanner` aggregating durable multi-phase
  metrics with INJECTED deterministic detectors and configurable
  thresholds. A threshold breach is recorded STRICTLY as an immutable
  D-027 audit event (insight GENERATED) — the worker NEVER invokes
  notification or publishing modules; dispatch is delegated to the
  Phase 14 contracts at a separate boundary. No wall clock: the scan
  instant is injected; windows come from durable event data.
- **Consequences:** the analyst observes and proposes only;
  side-effectful channels stay behind their own contracts (AST-
  verified import boundary).

## D-105 — Canonical HITL contract and review state machine

- **Status:** **Approved** (2026-09-17, owner-approved)
- **Situation:** Phase 17 routes insights to DISPATCHED_TO_HITL and
  Phases 11/12/15 need human gates, but there is no canonical review
  ticket: decisions live in chat threads and vanish.
- **Decision:** a canonical `HitlReviewTicket` — ticket_id,
  queue_type (INSIGHT_REVIEW | PUBLISH_GATE | ORDER_OVERRIDE |
  ASSET_FLAG), payload_ref, required_role, resolution_status,
  reviewer_actor_id, review decision data, feedback_notes — with
  the lifecycle PENDING_REVIEW → CLAIMED → APPROVED | REJECTED |
  MODIFIED | ESCALATED | EXPIRED. MODIFIED carries the reviewer's
  changed payload; ESCALATED re-queues as a fresh PENDING_REVIEW
  ticket with elevated role (an escalation LOOP, not a terminal);
  EXPIRED is decided by the deterministic sweep, never by a
  reviewer. Every transition is an immutable D-027 event.
- **Consequences:** every human decision becomes durable,
  attributable, and reconstructible; nothing is decided in a
  sidebar.

## D-106 — HITL ledger engine and claim lock vault

- **Status:** **Approved** (2026-09-17, owner-approved)
- **Situation:** two reviewers must never apply resolutions to the
  same ticket concurrently; ticket rows need atomic claim locks
  like every other exactly-once boundary in this system.
- **Decision:** `HitlEngine` over PostgreSQL `hitl.review_tickets`
  (PK-as-lock claim: exactly one CLAIMED winner) and
  `hitl.review_ledger` (append-only decision history) with a JSON
  parity backend. Ingestion consumes Phase 17 DISPATCHED_TO_HITL
  insights (INSIGHT_REVIEW queue) plus PUBLISH_GATE / ORDER_OVERRIDE
  / ASSET_FLAG producers. Expiration and escalation sweeps run on an
  INJECTED logical clock evaluator — zero wall-clock reads.
- **Consequences:** multi-reviewer races resolve to exactly one
  claimant; sweeps are deterministic and testable.

## D-107 — Decision dispatcher and platform action bridge

- **Status:** **Approved** (2026-09-17, owner-approved)
- **Decision:** on APPROVED/MODIFIED the `HitlDispatcher` emits
  downstream commands — apply the analyst recommendation (Phase 17
  insight), unblock a Phase 15 publishing slot, trigger a Phase 12
  OMS compensation — STRICTLY through injected command dispatchers
  keyed by queue_type; no direct cross-module imports. Resolution
  application is idempotent: a duplicate approval/rejection signal
  for an already-resolved ticket produces zero duplicate side-
  effects (the ledger already carries the decision).
- **Consequences:** a human approval executes the action exactly
  once, no matter how often the signal repeats.

## D-109 — Canonical admin contract and operator action protocol

- **Status:** **Approved** (2026-09-17, owner-approved)
- **Situation:** operators currently intervene by editing volumes
  or running ad-hoc scripts — invisible, unaudited, and outside
  every governance boundary built since Phase 5.
- **Decision:** a canonical `OperatorAction` (action_id, command,
  target, actor, reason, logical timestamps, confirmation key) plus
  `SystemDiagnosticReport`, `AuditQueryFilter`, and
  `QueueControlCommand` shapes. The command grammar is a CLOSED
  vocabulary: PAUSE_QUEUE, RESUME_QUEUE, RETRY_DLQ_ITEM,
  FORCE_SUPERSEDE_INSIGHT, MANUAL_SLOT_OVERRIDE, REPLAY_EVENTS.
  RBAC is deterministic over local actor tokens
  (`actor:operator:*` < `actor:admin:*`; `actor:system:*` for the
  engine itself) — D-045 compliant, zero external auth providers,
  no network.
- **Consequences:** every intervention becomes a validated,
  permission-checked, durably-audited action instead of an
  invisible manual mutation.

## D-110 — Control plane engine and state observation vault

- **Status:** **Approved** (2026-09-17, owner-approved)
- **Decision:** `ControlPlaneEngine` over PostgreSQL
  `admin.operator_actions` (PK-as-lock application guard) and
  `admin.control_audit` (hash-chained operator ledger) with a JSON
  parity backend. A consolidated read facade aggregates durable
  state across domains through INJECTED read callables — DLQ items
  (Phases 10/14), open HITL tickets (Phase 18), HITL-routed
  insights (Phase 17), asset registry counts (Phase 16) — with zero
  cross-module imports. REPLAY_EVENTS runs strictly in dry-run
  (read-only) mode unless an explicit atomic confirmation key is
  supplied; the key is single-use and recorded in the audit.
- **Consequences:** one observable dashboard of queue/HITL/insight/
  asset state from durable data only; replay cannot silently
  mutate history.

## D-111 — Queue management, DLQ intervention and circuit breakers

- **Status:** **Approved** (2026-09-17, owner-approved)
- **Decision:** a `QueueInterventionWorker` providing safe DLQ item
  retries (attempt budget respected, retries recorded as D-027
  events) and deterministic PAUSE/RESUME queue control states.
  Circuit breakers trip manually (operator command) or
  automatically (threshold breach evaluated by an INJECTED detector
  over the durable state report) with deterministic cool-down
  periods on the injected logical clock — no wall-clock reads.
  Downstream interventions emit strictly as immutable D-027 events
  via injected dispatch callables; the worker imports no domain
  module.
- **Consequences:** a tripped breaker is a first-class durable
  state with deterministic recovery, not a silent config flip.

## D-113 — Canonical threat model and security control registry

- **Status:** **Approved** (2026-09-17, owner-approved)
- **Situation:** nineteen phases of controls exist, but the threat
  assumptions behind them were implicit; controls without a mapped
  threat and a named test are claims, not guarantees.
- **Decision:** a canonical `ThreatModel` (threat_id, phase,
  category, description, controls) and `SecurityControl` registry
  mapping every threat category to the concrete module + test
  artifact that neutralizes it. The canonical taxonomy: credential
  leakage (D-045), replay attacks (Phase 19 confirmation keys),
  ledger tampering (Phases 18/19 hash chains), race-condition
  injection (Phases 12/15/17/18/19 exactly-once locks),
  oversized/malformed payloads (all contract layers), enumeration
  and probing via error surfaces. Rule: NO CONTROL WITHOUT A TEST —
  the registry is battery-verified.
- **Consequences:** security posture is a durable, inspectable,
  test-backed artifact rather than folklore.
- **Verification (M4, 2026-09-17):** registry battery-backed —
  every threat category carries ≥1 control, every control names its
  test artifact (asserted in the Phase 20 suite); threat→control→test
  mapping table in `docs/phases/phase-20-security-hardening.md` §3.

## D-114 — Input hardening and contract-level defense in depth

- **Status:** **Approved** (2026-09-17, owner-approved)
- **Situation:** every contract layer validates shape and
  vocabulary, but none enforces size/depth/charset bounds uniformly,
  and JSON duplicate-key or unicode-confusable inputs could slip
  semantic validation.
- **Decision:** a system-wide `InputHardeningGate` applied at
  contract entry points: strict size limits (payload bytes, id/ref
  lengths), character-set and shape enforcement, JSON depth/width
  limits, duplicate-key rejection, and unicode-confusable
  (homoglyph) rejection with NFC canonicalization before validation.
  All prior contract validators (Phases 9–19) are re-audited
  against these bounds; discovered gaps are defects fixed in-batch
  and recorded.
- **Consequences:** malformed inputs are rejected deterministically
  at the gate, before semantic validation or storage.
- **Verification (M4, 2026-09-17):** re-audit found SIX unbounded
  validator surfaces (oms, analytics, scheduling, analyst, hitl,
  admin) — all hardened with declared + enforced bounds
  (11/11 modules clean). Gate battery: size/charset/control/
  confusable/depth/width/duplicate-key all proven; scope clarified —
  module validators guarantee BOUNDS, the gate rejects
  charset/controls at system entry points (layered defense).

## D-115 — Ledger and replay defense escalation

- **Status:** **Approved** (2026-09-17, owner-approved)
- **Decision:** the Phase 18/19 hash chains gain deterministic
  chain-head ATTESTATIONS — a signed-style (hash) commitment over
  (chain head hash, length, logical stamp) recomputed incrementally
  and verifiable in O(1) against the full chain walk, readable
  through the Phase 19 facade. Replay-key burn records are
  chain-anchored (already burned keys cannot be forged unburned —
  the burn evidence lives in the tamper-evident ledger).
  Administrative rate limiting: deterministic budget counters on
  repeated DLQ retries and repeated failed RBAC attempts with
  configurable lockout thresholds and audited lockouts, all on the
  injected logical clock.
- **Consequences:** fast tamper detection, forge-proof burn
  evidence, and deterministic abuse containment.
- **Verification (M4, 2026-09-17):** attestation upgraded to **v2**
  during verification — the v1 (head/length) fold was blind to
  interior-row payload mutation (a vault edit keeps the stored
  row_hash). v2 folds the FULL ROW of every position:
  mutation/swap/truncate/append each detected, proven offline and
  on live PG (`admin.control_audit` tamper test with byte-exact
  restore). Burns chain-anchored (audited, forge-refusal tested);
  lockout counters deterministic on the logical clock
  (arming/expiry/race-tested).

## D-116 — Security audit sweep and boundary re-verification

- **Status:** **Approved** (2026-09-17, owner-approved)
- **Decision:** the standing AST audit is extended into a full
  recursive sweep: every canonical module scanned for dynamic
  `eval`/`exec`, `subprocess`/`os.system`, `pickle`/`marshal`
  deserialization, `requests`/`urllib`/`socket` network imports,
  `random` non-determinism, and bare `except:` swallowing — with
  an explicit allowlist (test-only Docker guards, the established
  patterns). Secret scanning gains Shannon-entropy analysis over
  the full repository; D-045 re-verified: zero real credentials.
  All controls local, deterministic, test-proven.
- **Consequences:** the sweep is itself a test artifact — executed
  in the battery, not a manual ritual.
- **Verification (M4, 2026-09-17):** extended AST sweep CLEAN
  (0 findings in canonical modules; 20 subprocess uses confirmed
  confined to test harnesses); secret-entropy scan CLEAN (0 flags,
  92 files) after fixing two detector false positives (`re.compile`
  vs bare `compile`, UPPER_SNAKE identifiers) and allowlisting the
  Phase 9–11 synthetic mock-token prefixes; D-045 re-verified —
  zero real credentials.

## D-117 — Formal state-machine invariant auditing across phases

- **Status:** **Approved** (2026-09-17, owner-approved)
- **Situation:** Phases 12/15/17/18/19 each test their own state
  machine in isolation; no artifact proves the edge matrices stay
  closed (every illegal edge rejected, every legal edge accepted)
  or that terminal states have no exits — a regression in any one
  matrix currently surfaces only if that phase's own tests change.
- **Decision:** a cross-phase invariant battery asserts, for EVERY
  state machine (OMS orders, scheduling posts, business insights,
  HITL tickets, scheduling circuit breakers):
  (1) the legal-edge matrix is exactly the declared set;
  (2) every undeclared (from, to) pair is rejected or refused;
  (3) terminal states have no outgoing edges;
  (4) state-affecting engine calls against the LIVE PG store leave
  the durable row count unchanged when refused (no partial writes);
  (5) crash between a durable write and its audit append is
  reconciled by the attestation (D-115) without operator action.
  The battery runs in every regression pass.
- **Consequences:** edge-matrix drift in any phase fails CI-style
  battery runs immediately; state machines can no longer regress
  silently.
- **Verification (Phase 21 closeout, 2026-09-18):** battery-proven
  — all five matrices asserted closed; live-PG refused-write
  row-count checks green; terminal states exit-less.

## D-118 — Deterministic fault injection & local chaos discipline

- **Status:** **Approved** (2026-09-17, owner-approved)
- **Situation:** rollback, retry and recovery paths exist across
  the engines, but most are exercised only on the happy path; real
  failures arrive unannounced and must not corrupt durable state.
- **Decision:** a deterministic fault-injection toolkit (no
  monkeypatching of shippable modules, no randomness, no wall
  clock) injects failures at INJECTED seams only:
  handler/dispatcher exceptions (Phase 19 execute path),
  transient-then-success dispatch sequences (retry ladders),
  mid-transaction aborts on the live PG store (crash between
  begin and succeed leaves NO succeeded row), and concurrent
  reader/writer contention on the HITL ledger and control-audit
  chains. Every injection asserts three invariants: clean rollback
  (durable state unchanged or advanced atomically), audit truth
  (the failure is recorded, never silent), and ledger integrity
  (attestation + verify_chain still pass after recovery).
- **Consequences:** recovery paths are battery-proven; chaos runs
  are reproducible and CI-safe (fully local, deterministic).
- **Verification (Phase 21 closeout, 2026-09-18):** chaos battery
  green — handler/dispatcher exceptions isolated, transient
  dispatch retried-then-deduped, mid-transaction PG abort leaves
  no succeeded row (recovery completes, dedupe holds), 8-thread
  HITL-ledger contention and 8-thread live slot-lock race each
  exactly-one-winner with attestation/verify_chain intact.

## D-119 — Automated fuzz hardening of D-114 entry points

- **Status:** **Approved** (2026-09-17, owner-approved)
- **Situation:** the D-114 gate and validators are hand-tested on
  curated bad inputs; a fuzzer can find the inputs humans miss
  (length-boundary off-by-ones, deep type confusion, absurdly
  nested JSON, multibyte confusables).
- **Decision:** a DETERMINISTIC mutational fuzzer (seeded corpus,
  fixed mutation ladder, no randomness) hammers all D-114 entry
  points — InputHardeningGate string/identifier/JSON, plus the six
  hardened prior-phase validators — with generated adversarial
  payloads. Invariants: ANY outcome is either a deterministic
  Class-B/InputRejected rejection or clean acceptance; never an
  unhandled exception type, a hang (each case executes under a
  step-budget), or observable state mutation. Corpus and expected
  verdicts are frozen as fixtures; the corpus grows only by
  owner-approved additions.
- **Verification (Phase 21 closeout, 2026-09-18):** 585
  deterministic cases run CLEAN after the fuzzer found and the
  engine fixed 2 real D-114 gaps (lone-surrogate
  `UnicodeEncodeError` leak; silent acceptance of `Cs` codepoints);
  corpus + verdicts frozen as fixtures.
- **Consequences:** entry points are adversarially exercised on
  every run; zero-skip discipline extends to negative-space
  coverage.

## D-121 — Local structured event log ledger (engine.log.v1)

- **Status:** **Approved** (2026-09-18, owner-approved)
- **Situation:** MASTER_PLAN Phase 22 requires structured logs,
  workflow monitoring and audit events; the Phase 8 `ai.observe.v1`
  collector covers only the AI surface, so operational subsystems
  (analytics, HITL, dispatch, security, scheduling) still log in
  ad-hoc shapes, and no cross-subsystem causal identifier exists.
- **Decision:** a canonical operational log record
  (`engine.log.v1`) — required fields: `schema_version`,
  `trace_id`, `causal_chain_id`, `logical_at`, `domain`, `event`,
  `level`, `status` — emitted as append-only JSONL with an optional
  durable vault reusing the D-027 event-store transport (deterministic
  row keys, no wall clock anywhere). `trace_id`/`causal_chain_id` are
  DETERMINISTIC identifiers derived from causal inputs (domain,
  entity ref, logical sequence) — never `time.time_ns()`; child
  events chain by carrying the parent causal id forward. Every
  payload passes D-114 sanitization at the log boundary (size caps,
  charset, credential-marker redaction, no raw PII/secrets). The
  Phase 8 AI surface remains `ai.observe.v1`, unchanged.
- **Consequences:** any subsystem event is traceable across engines
  without wall-clock correlation; log tampering is detectable via
  append-only storage; zero-leak logging is enforced structurally.
- **Verification (Phase 22 closeout, 2026-09-18):** battery-proven —
  deterministic ids (same inputs ⇒ same ids), chain propagation
  across sink re-instantiation, JSONL append-only round-trip,
  durable vault dedupe (`skipped_duplicate` on re-emission) with
  exact trace-scoped counts on live PG.

## D-122 — Deterministic metrics registry & localhost-only exposition

- **Status:** **Approved** (2026-09-18, owner-approved)
- **Situation:** state-machine throughput, slot-lock contention,
  ledger verification latency and circuit-breaker trips are today
  only observable as test counts; there is no live operational
  readout, and external APM agents are forbidden (D-045).
- **Decision:** a zero-dependency metrics registry — monotone
  counters, gauges, and histograms with FIXED logical bucket edges —
  updated deterministically via explicit `incr`/`observe` calls on
  the logical timeline (never wall-clock sampling). A stdlib
  `http.server` exporter bound strictly to 127.0.0.1 serves the
  Prometheus text exposition format; metric names and label sets
  are DECLARED in a bounded registry (no unbounded cardinality, no
  raw payload values or PII in labels). Nothing outside loopback
  can scrape it; no external telemetry endpoint exists.
- **Consequences:** counters/histograms are reproducible in tests
  (same logical inputs → same exposition); the local exporter is
  inspectable by the operator console without any network exposure.
- **Verification (Phase 22 closeout, 2026-09-18):** battery-proven —
  monotonicity enforced (negative/zero increments Class-B),
  byte-identical exposition across instances, fixed bucket edges,
  cardinality caps, exporter bound to 127.0.0.1 serving exactly
  `exposition()` with 404 off-path (loopback scrape via curl).

## D-123 — Composable health probes & the qa.health_report.v1 attestation

- **Status:** **Approved** (2026-09-18, owner-approved)
- **Situation:** stack health is checked ad hoc in shell one-liners;
  there is no deterministic, machine-readable readiness artifact an
  operator (or the Phase 19 control plane) can query.
- **Decision:** a probe is a deterministic callable returning
  `{name, ok, verdict, detail, checked_at_logical}` (verdict ∈
  PASS / DEGRADED / FAIL — degraded is an EXPLICIT verdict, never a
  silent pass); probes compose into a registry that renders
  `qa.health_report.v1` — a versioned, machine-readable JSON
  attestation. Shipped probes: live-PG reachability + schema
  presence, ledger attestation validity (D-115 fold over the
  Phase 18/19 chains), scheduled-post queue depth vs declared
  threshold, and circuit-breaker states (D-111). Probes receive
  everything injected (no engine imports); the CLI renders the
  report deterministically via the logical clock.
- **Consequences:** health is an artifact, not a claim; the report
  is auditable, diffable, and consumable by the control plane.
- **Verification (Phase 22 closeout, 2026-09-18):** battery-proven —
  PASS/DEGRADED/FAIL semantics (degraded explicit), threshold
  ordering guard, report shape validation, worst-of aggregation;
  live CLI renders a real attestation: pg_schema PASS,
  ledger_integrity PASS (D-115 fold over the Phase 19 chain),
  breaker_states DEGRADED on durable residue (honest reporting).

## D-124 — Zero-leak telemetry discipline (logs, metrics, probes)

- **Status:** **Approved** (2026-09-18, owner-approved)
- **Situation:** logs and metrics are the classic leak channels
  (connection strings, bearer tokens, customer references in
  labels); D-045 forbids any of them reaching storage or output.
- **Decision:** every string that reaches a log record, a metric
  label, or a probe detail passes the D-114 gate AND the telemetry
  redaction list (`postgres://`, `bearer `, `api_key`, `password=`,
  `authorization:`) plus an explicit PII denylist; non-conforming
  values are replaced with the fixed marker `[REDACTED]` — never
  silently truncated into ambiguity. Observability modules import
  NO engine modules — they observe via injected read callables,
  preserving the established import-level boundary discipline —
  and the leakage battery is part of every regression pass.
- **Consequences:** telemetry is safe by construction; any future
  leak channel must first defeat a battery-asserted gate.
- **Verification (Phase 22 closeout, 2026-09-18):** battery-proven —
  credential markers in details/payloads/metric labels all render
  as `[REDACTED]` (exposition text verified marker-free), PII
  payload keys redacted, control chars rejected Class-B, oversized
  fields marked `…[TRUNC]`, probe details pass the same gate.

## D-125 — Deterministic retention, compaction & verified-freeze archives

- **Status:** **Approved** (2026-09-18, owner-approved; drafted Phase 23 M0)
- **Situation:** durable tables grow unboundedly (event_record
  20,561 rows measured 2026-09-18; breaker residue 82/82 non-CLOSED
  and climbing with every battery run); growth is a cost and
  read-path performance liability, but naive deletion would break
  D-096/D-112/D-115 tamper-evidence.
- **Decision:** retention by STATE, not age — only terminal rows
  (terminal processing_status, resolved tickets, superseded slot
  locks) are eligible; verified-freeze snapshot (JSONL archive +
  full-set attestation fold — an archive that doesn't verify is
  refused Class-B and NOTHING is removed); one-batch teardown then
  live-chain re-verify (any mismatch halts the compactor fail-closed);
  every run appends a manifest to security.hardening_audit;
  compaction is never used to weaken evidence — it exists so the
  evidence stays affordable. Read-path cost: declared idempotent
  indexes + keyset-paginated reads (no OFFSET scans).
- **Consequences:** storage bounded, tamper-evidence intact, every
  compaction audited; read paths stop degrading with history size.
- **Owner directives (2026-09-18 approval):** compaction is
  OPERATOR-TRIGGERED via the Phase 19 control plane
  (`COMPACT_RETIREABLE`), with optional automated hooks during
  declared maintenance windows only.
- **Verification (Decision-ledger drill, 2026-09-19):** the
  hash-chained human decision ledger is declared NOT teardown-
  eligible (compact() refuses the surface — row removal would
  break the chain permanently); disaster treatment is full
  verified-freeze archive + atomic rehydration via the
  `decision_ledger_drill.py` operator command. Chain re-verifies
  with identical head hash after a full-chain loss; decided-vs-
  happened consistency reconciles every decision row against the
  D-027 store. Suite-found defect fixed: PgEventStore.get_record
  dropped its explicit source_system (read-path twin of the
  Phase 9 finding). Suite 7/7 ×2; battery 877/877 ×2 green.
- **Verification (Phase 23 closeout, 2026-09-18):** battery-proven —
  forgery detection (byte flip / dropped line / reordered row),
  fail-closed (write failure and count mismatch ⇒ zero deletes,
  parse failure ⇒ Class-B), live COMPACT_RETIREABLE run (active
  lock survives, inactive removed, manifests recorded, Phase 19
  chain attestation verified UNCHANGED after compaction); indexes
  applied live; keyset pages ordered + disjoint. In-batch catch:
  slot-lock boolean-parse defect (PG `true` vs `True`/`t`) — first
  live run archived-then-removed all 210 slot_lock rows including
  actives; archive preserved full evidence; parser fixed, re-proven
  live, pinned in the M4 suite.

## D-126 — Resilience envelope: breaker hygiene, bounded retries, deterministic backoff

- **Status:** **Approved** (2026-09-18, owner-approved; drafted Phase 23 M0)
- **Situation:** breaker rows accumulate (82/82 non-CLOSED residue);
  retry/backoff is ad hoc per engine; the psql transport has no
  declared concurrency ceiling, so upstream degradation can exhaust
  connections instead of failing deterministically.
- **Decision:** breaker rows tied to resolved incidents (or beyond a
  declared logical horizon) become D-125-compactable; a shared
  deterministic `RetryPolicy` (logical backoff `base*2^(attempt-1)`,
  jitter FORBIDDEN, classes bound to D-052: A retryable, B/C/E
  terminal, D quarantined) and `BudgetedExecutor` (refuses when the
  retry/failure budget is exhausted) unify engine behavior; the psql
  transport gains a semaphore ceiling with bounded-queue fast-fail
  (deterministic Class-A verdict, zero hangs — chaos-proven).
- **Consequences:** one retry semantic across engines; breaker
  residue governed; degradation is deterministic, never a cascade.
- **Verification (Phase 23 closeout, 2026-09-18):** battery-proven —
  backoff `base·2^(attempt−1)` jitter-free; D-052 routing (A
  retries-then-exhausts, B/C/E terminal, D quarantine, explicit
  `failure_class` wins); BudgetedExecutor refuses with zero
  attempts; transport ceiling drains 24 contenders via queueing and
  fast-fails saturated waits deterministically (Class-A, no hangs).

## D-127 — Platform resource-budget envelopes

- **Status:** **Approved** (2026-09-18, owner-approved; drafted Phase 23 M0)
- **Situation:** D-063 guards AI spend only; container CPU/memory,
  LLM token quotas per batch, and API-call budgets on green/yellow
  paths have no owner-approved bounds — "cost control" exists for
  exactly one resource class (MASTER_PLAN §13 Phase 23 mandate).
- **Decision:** canonical `ResourceBudget` (named resource, limit,
  window per_run/per_logical_day, scope green/yellow) + deterministic
  `BudgetLedger` (append-only consumption rows on the logical
  timeline) with D-063-identical enforcement: ≥80% ⇒
  `budget_warning`, 100% ⇒ refusal BEFORE the consuming call,
  always active, never ledger-gated. D-063's AI meter writes through
  to the same ledger — one consumption record for ALL resource
  classes; defaults are declared dummies (D-045-safe), real limits
  are owner config.
- **Consequences:** overrun of any budget structurally impossible
  without an owner-approved config change; AI + platform spend
  visible in one ledger.
- **Owner directives (2026-09-18 approval):** canonical suites use
  the declared dummy baselines; ALL resource bounds are
  environment-configurable (no hard-coded real limits).
- **Verification (Phase 23 closeout, 2026-09-18):** battery-proven —
  ≥80% warning, hard refusal BEFORE the consuming call with the
  ledger unchanged, exact-boundary consume allowed, env overrides
  (incl. negative ⇒ Class-B), D-063 write-through (one event ⇒
  tokens + calls), batch stop-at-first-refusal, scopes independent,
  red scope refuses to exist (D-050).

## D-128 — Phase 23 verification battery (chaos × compaction × quota)

- **Status:** **Approved** (2026-09-18, owner-approved; drafted Phase 23 M0)
- **Situation:** the new failure modes (mid-compaction crash,
  archive forgery, quota exhaustion mid-batch, pool saturation) need
  battery-proven closure.
- **Decision:** `local/tests/test_phase23_resilience.py` — offline +
  live-PG classes: compaction edges (empty set, active rows present,
  snapshot-verify failure ⇒ nothing removed, mid-teardown crash ⇒
  fail-closed + audited), archive forgery (flipped byte ⇒ verify
  fails), breaker hygiene, retry vectors, pool-saturation chaos
  (deterministic refusal, zero hangs), quota exhaustion (hard
  refusal pre-call, soft warning at 80%); full regression + census
  reconcile; two consecutive green runs.
- **Consequences:** the new surfaces close under the same
  zero-skip discipline as every prior phase.
- **Verification (Phase 23 closeout, 2026-09-18):** suite 20/20
  zero-skip (17 offline + 3 live-PG); battery 770/770 two
  consecutive green runs; census reconciles exactly (T1=666 ·
  T2=46 · T3=51 · T4=7, 30 modules).

## D-129 — Model & provider neutrality contract (AiProvider v2)

- **Status:** **Approved** (2026-09-18, owner-approved; drafted Phase 24 M0)
- **Situation:** the `AiProvider` boundary (Phases 7–8) is enforced
  by convention, not by a battery; provider conformance, identical
  token accounting, and zero provider-payload leakage into
  canonical state are unproven properties.
- **Decision:** `ProviderContract` in
  `canonical/portability.py` — deterministic `name`; schema-
  compatible `generate` for every declared schema id; token
  accounting always present and WRITE-THROUGH to the D-127 ledger
  via the D-063 collector path; failures carry D-052 classes, never
  bare SDK types; provider metadata only in observability records
  (D-124 extension). `assert_provider_conformance` battery-proves
  any implementation (mock live-tested; live adapters via owner-
  gated fixtures — conformance ≠ live compatibility).
- **Consequences:** adding a provider = one interface + one harness
  pass; non-conforming providers surface as battery failures —
  lock-in becomes structurally visible.
- **Verification (Phase 24 closeout, 2026-09-18):**
  `assert_provider_conformance` proven for the shipped set —
  MockAiProvider, the OpenAI/Anthropic-compatible adapters, and
  FallbackProvider under a DECLARED composite-members rule (a
  fallback honestly reports the responding engine; the composite
  name is declared, not checked against it). Write-through proven
  into the D-127 ledger: exact token/call metering and hard
  refusal at 100% before dispatch. Conformance gap in the mock's
  usage envelope (missing `estimated_cost`) found by the harness
  and fixed in the provider.

## D-130 — Storage & database abstraction boundaries

- **Status:** **Approved** (2026-09-18, owner-approved; drafted Phase 24 M0)
- **Situation:** JSON/PG parity is proven per-phase ad hoc; blob
  ops have an ABC but no conformance contract; ANSI-SQL portability
  is implied, never declared or enforced.
- **Decision:** `BackendPair` + `assert_backend_parity`
  — the SAME operation script runs against both factories of each
  declared pair (event store, slot locks, notification locks) and
  normalized verdicts must match; `MediaStoreContract` declares
  put/get/delete/list/stat semantics with deterministic addressing
  and zero wall-clock metadata (`LocalObjectStore` conforms; S3-
  compatible remotes are drop-in, owner-gated); SQL portability is
  AST-enforced — vendor idioms confined to the declared transport
  + schema files, domain modules pure.
- **Consequences:** backend/vendor swaps become parity-harness
  passes; hermetic memory backends remain the canonical offline
  tier.
- **Verification (Phase 24 closeout, 2026-09-18):** all four
  declared pairs (event store, slot locks, notification locks,
  media) run mode=both parity with ZERO divergences, live-PG
  included. The harness caught a real envelope divergence: JSON
  slot-lock `claim` returned the full internal row as `holder`
  while PG returned the declared shape — JSON conformed (consumers
  read `post_id` only; Phase 15 battery verified unaffected).
  `LocalObjectStore` gained `list()` per the standardized blob
  surface and passes media conformance.

## D-131 — Pluggable integration adapters (channels & tooling)

- **Status:** **Approved** (2026-09-18, owner-approved; drafted Phase 24 M0)
- **Situation:** Instagram/Telegram/mock adapters and notification
  channels are injectable but lack a declared interchange protocol
  (registry, health, hot-swap semantics) and an isolation guarantee
  against vendor literals leaking into canonical workflows.
- **Decision:** `ChannelAdapterContract` — deterministic
  `name`, mock/live variant pairs with IDENTICAL envelope shapes,
  D-052 failure classes, hot-swap = registry rebind with a
  deterministic verdict (`swapped_from`/`swapped_to`/
  `swapped_at_logical`) audited via the D-121 log ledger.
  Battery-asserted isolation: ZERO channel-name literals in
  canonical workflow modules (extended D-116 AST rule); external
  tooling consumes only canonical contracts/facades.
- **Consequences:** a new channel is one adapter + one registry
  entry + one conformance pass; vendor tentacles in canonical code
  are structurally impossible to merge unnoticed.
- **Verification (Phase 24 closeout, 2026-09-18):** hot-swap
  registry rebind emits deterministic verdict rows through the
  SHIPPED `LogLedger` emitter (D-121 `engine.log.v1` shape,
  D-124 redaction gate — no foreign row shape invented). The D-131
  confinement rule joined the D-116 extended sweep as an allowlist
  of declared homes (adapter modules, channel contracts, fuzz
  corpus, scanner table); planted violations in canonical workflow
  code are caught. Two analytics literals were relocated to their
  single contracts home with the publication-channel vs OMS-domain
  distinction preserved (Phase 13 battery re-verified 28/28).

## D-132 — Portability & port-swapping verification battery

- **Status:** **Approved** (2026-09-18, owner-approved; drafted Phase 24 M0)
- **Situation:** the neutrality claims of D-129..D-131 need the
  same zero-skip closure as every prior phase.
- **Decision:** `local/tests/test_phase24_portability.py`
  — provider conformance + token write-through into D-127, backend
  parity across all declared pairs (offline always, live-PG while
  the stack is up), media conformance, hot-swap verdicts, simulated
  provider lockout ⇒ deterministic D-066 fallback + observability,
  workflow-isolation AST rules, zero-secret boundary checks; full
  battery ×2 green, census reconcile, sweeps CLEAN.
- **Consequences:** replaceability becomes a tested, regression-
  pinned property of the platform.
- **Verification (Phase 24 closeout, 2026-09-18):**
  `test_phase24_portability.py` 26/26 zero-skip (offline + live-PG
  E2E: parity mode=both against the real store, lockout fallback
  with exact ledger metering, hot-swap audit rows). FULL battery
  **796/796, two consecutive green runs + one census run, zero
  warnings**; ladder 46/46; census reconciles exactly
  (T1=694 · T2=44 · T3=51 · T4=7 = 796, 31 modules); entropy CLEAN
  (122 files); canonical AST gate green; stack 5/5 healthy;
  `git diff --check` PASS.

## D-133 — End-to-end business flow orchestration conductor

- **Status:** **Approved** (2026-09-18, owner-approved same-day)
- **Situation:** every phase engine is battery-proven in isolation,
  but the MASTER_PLAN §13 Phase 25 flow — Instagram lead →
  conversation → discovery → cart/order → payment → verification →
  inventory → shipping → notification → analytics — has never been
  executed as ONE traced flow with failure/recovery at every step.
- **Decision:** `canonical/e2e_conductor.py` +
  `canonical/e2e_contracts.py` — a PURE 10-stage conductor (all
  adapters/stores injected, RULES §35) over declared stage
  envelopes; a D-121 `TraceContext` root created at lead capture
  traverses every stage unchanged; each stage emits
  `engine.log.v1` audit rows; cross-stage payloads never gain
  undeclared keys (harness-asserted zero schema mutation).
- **Consequences:** the platform's headline promise (lead-to-
  analytics) becomes a deterministic, auditable execution unit;
  any boundary regression surfaces as a stage-contract failure.
- **Verification (Phase 25 closeout, 2026-09-18):** conductor
  proven: ten stages under ONE unbroken root trace (ten distinct
  causal ids), zero-schema-mutation guard rejects rogue keys,
  strict stage binding (missing AND unknown stages rejected),
  audited FAILURE path. Harness-forced design fix: the D-052 class
  is classified AT the stage boundary (explicit `.failure_class`
  wins, else the canonical message classifier) — the audited class
  is what recovery routes on, never the exception type name; the
  root trace ids are injected into the flow context so the
  unbroken-trace guard is checkable in data.

## D-134 — Deterministic chaos & fault-injection ladder

- **Status:** **Approved** (2026-09-18, owner-approved same-day)
- **Situation:** phases proved fault handling locally (retry
  ladders, budget refusals, dead-letters, breaker rows), but never
  at every boundary of ONE end-to-end flow.
- **Decision:** structured, reproducible injections via
  the Phase 21 `FaultScript` at each lifecycle boundary — channel
  outage (Class-A retry recovery), AI budget refusal at 100%
  (pre-dispatch, zero provider calls), media-store fault at fan-out
  (fail-closed + HITL, no phantom publication), lock contention
  (deterministic refusal, no double-claim), payment-verify failure
  (order failed path, inventory RESTORED, failure notice,
  analytics outcome). Every scenario asserts the exact D-052
  class, breaker engagement observed by the D-123 probe, exact-
  ledger rollback, and recovery to completion via retry/replay —
  all clocks logical (D-085/D-093/D-121).
- **Consequences:** failure/recovery stops being per-phase lore
  and becomes a pinned, regression-proofed flow property.
- **Verification (Phase 25 closeout, 2026-09-18):** all five
  scenarios pinned with `FaultScript` reproducibility over the
  REAL engines: Class-A outage recovers by replay (attempt 2,
  jitter-free backoff, end state byte-equal to the happy path incl.
  inventory); D-127 exhaustion refuses pre-dispatch (zero provider
  invocation, flow stopped at the boundary, NOT replay-recoverable
  — terminal at flow level); media fault fails closed; delivery-
  lock contention leaves the original claim byte-untouched;
  payment-verification failure → CANCELLED, inventory RESTORED
  (8→10), failure notice via the real D-089 template registry.

## D-135 — Automated state reconciliation & self-healing

- **Status:** **Approved** (2026-09-18, owner-approved same-day)
- **Situation:** durable-only reconstruction is asserted per phase
  (Phase 6/17 idempotency, Phase 23 compaction); interrupted-
  process scenarios across the full flow are not yet exercised.
- **Decision:** outbox reconciliation (fault between
  durable event write and downstream effect → replay from D-027
  with exactly-once semantics via idempotency keys);
  stranded-lock sweeps (crashed holder reclaimed deterministically,
  zero phantom records); compaction recovery (cold start after
  interrupted compaction re-verifies archive attestation and
  re-runs idempotently); process-crash simulation at any stage
  boundary → restart from DURABLE stores only, zero data loss,
  exact ledger dedup.
- **Consequences:** crash-resilience becomes an executable
  guarantee, not a design note; recovery is always replay, never
  manual state surgery.
- **Verification (Phase 25 closeout, 2026-09-18):** stranded-lock
  sweep idempotent with zero phantom rows and no resurrection of
  vanished rows; state rebuilds from durable refs only (malformed
  rows skipped as evidence, parseable unknowns counted);
  exactly-once outbox replay proven on the JSON store AND the live
  PG store; conflicting duplicate → `IntegrityError` (human
  review, D-027).

## D-136 — Full-spectrum verification battery & acceptance gates

- **Status:** **Approved** (2026-09-18, owner-approved same-day)
- **Situation:** the T4 census tier exists (7 tests) but no
  multi-stage full-flow battery over offline-hermetic AND live-PG
  environments.
- **Decision:** `tests/test_phase25_full_system.py`
  with an offline-hermetic E2E class (full 10-stage flow on
  JSON/memory backends + mock adapters: happy path + every D-134
  fault + D-135 reconciliation scenario) and a live-PG E2E class
  (same scenarios against real PostgreSQL, runs while the stack is
  up, never skipped). Acceptance gates: zero skips; battery ×2
  consecutive green + census reconciles exactly; ladder green;
  AST/entropy/bounds CLEAN; `git diff --check` PASS; stack 5/5.
- **Consequences:** Phase 26 (Launch) inherits a machine-checked
  end-to-end acceptance surface instead of a manual checklist.
- **Verification (Phase 25 closeout, 2026-09-18):**
  `test_phase25_full_system.py` 18/18 zero-skip (15 offline + 3
  live-PG E2E: the FULL ten-stage flow persisted through the real
  `PgEventStore` — order VALIDATED, inventory 10→8; live outbox
  replay exactly-once; conflicting duplicate → IntegrityError).
  FULL battery **814/814, two consecutive green runs + one census
  run, zero warnings**; ladder 46/46; census reconciles exactly
  (T1=706 · T2=44 · T3=54 · T4=10 = 814, 32 modules); AST CLEAN
  (68 files); entropy CLEAN (112 files); `git diff --check` PASS;
  stack 5/5 healthy.

## D-137 — Launch readiness control matrix

- **Status:** **Approved** (2026-09-19, owner-approved same-day with all six rulings: no real production activation by implementation; missing operational evidence always NO_GO, never an assumed pass; activation sequence preflight→dry run→limited canary→observation→explicit promotion→rollback on breach approved; audit destinations D-121 engine.log.v1 for machine telemetry + Phase 19 admin.control_audit for human approvals/break-glass; final commit establishes a launch CANDIDATE only — live activation requires a separate explicit one-time owner authorization)
- **Situation:** MASTER_PLAN §13 gates Phase 26 (Launch) on nine
  check domains — security, backups, payment, inventory, shipping,
  monitoring, escalation, end-to-end, recovery — but no canonical,
  machine-verifiable control matrix exists; readiness today is
  implicit in scattered battery/sweep evidence.
- **Decision:** one canonical, versioned control matrix
  covering all nine domains. Every control: stable id (`SEC-*`,
  `BAK-*`, `PAY-*`, `INV-*`, `SHP-*`, `MON-*`, `ESC-*`, `E2E-*`),
  owner ROLE (configuration, never hard-coded identities), severity,
  mandatory flag, declared evidence kind + reference, remediation
  guidance. States: `PASS` / `FAIL` / `BLOCKED` / `NOT_APPLICABLE` —
  **missing, stale, malformed, or unknown evidence is never a pass**;
  it evaluates as `BLOCKED` and fails the verdict closed. Anchors
  (compose, never duplicate): Phase 20 sweeps + D-114 (security),
  D-125 verified-freeze + restore-rehearsal (backup — a backup is
  valid only after a successful restore), Phase 12 verify path +
  D-027 idempotent callbacks + Phase 25-proven negative verdicts
  (payments; capture disabled until owner activation), D-082/D-084
  (inventory), Phase 24 provider-neutral intent boundary (shipping;
  no purchase pre-approval), D-123/D-121/D-124 (monitoring), Phase 19
  RBAC + runbook refs + audited break-glass (escalation), Phase 25
  suite/census/ladder tied to the exact candidate commit (E2E +
  recovery). Evidence-validity model: commit-bound, configuration-
  bound, logically-expiring, and human-attested classes; staleness
  computed from declared logical horizons — never wall clock.
- **Verification (Decision-ledger drill, 2026-09-19):** the
  hash-chained human decision ledger is declared NOT teardown-
  eligible (compact() refuses the surface — row removal would
  break the chain permanently); disaster treatment is full
  verified-freeze archive + atomic rehydration via the
  `decision_ledger_drill.py` operator command. Chain re-verifies
  with identical head hash after a full-chain loss; decided-vs-
  happened consistency reconciles every decision row against the
  D-027 store. Suite-found defect fixed: PgEventStore.get_record
  dropped its explicit source_system (read-path twin of the
  Phase 9 finding). Suite 7/7 ×2; battery 877/877 ×2 green.
- **Verification (Phase 26 closeout, 2026-09-19):** shipped
  and battery-attested. Suite 46/46 zero-skip (43 offline +
  3 live-PG) x3 consecutive green; battery 860/860 x2 green,
  zero warnings; ladder 46/46; census reconciles exactly
  (T1=710 - T2=46 - T3=56 - T4=13 = 860, 33 modules); AST /
  entropy / channel sweeps CLEAN; stack 5/5 healthy. Live-leg
  defects fixed in-batch: explicit audit_seq insert with
  ::bigint cast, None-sentinel parity (PG vs JSON vault);
  rehearsal debris pruned, Phase 19-23 chain history intact
  (rows 1-432, verify_chain ok). Result: launch CANDIDATE
  only - no activation performed.
- **Verification (Operator drill, 2026-09-19):** the resilience
  drill is now the `resilience_drill.py` operator command
  (six-stage lifecycle, CLI/JSON status dashboard, run-scoped
  isolation, fail-closed on every fault path — verified by fault
  injection). Drill evidence feeds the D-137 matrix as real
  BAC-001 rehearsal evidence (a FAILED drill blocks BAC-001 ⇒
  NO_GO). Suite 10/10 ×2; battery 870/870 ×2 green.
- **Verification (Resilience drill, 2026-09-19):** catastrophic-
  recovery drill shipped and PASSED — a real D-027 store flow
  archived with the D-125 verified-freeze primitives, PROVEN
  destroyed, restored only after archive re-verification, then
  fold- and store-verified byte-equal; forged and missing
  archives fail closed with the Class-B CompactionError
  (4/4 x2 consecutive green, zero skips; `EV-BAC-001` evidence
  bound to the candidate commit + config fingerprint).

## D-138 — Deterministic Go/No-Go attestation

- **Status:** **Approved** (2026-09-19, owner-approved same-day with all six rulings: no real production activation by implementation; missing operational evidence always NO_GO, never an assumed pass; activation sequence preflight→dry run→limited canary→observation→explicit promotion→rollback on breach approved; audit destinations D-121 engine.log.v1 for machine telemetry + Phase 19 admin.control_audit for human approvals/break-glass; final commit establishes a launch CANDIDATE only — live activation requires a separate explicit one-time owner authorization)
- **Situation:** launch decisions need a deterministic, immutable,
  fail-closed verdict derived from the D-137 matrix, bound to the
  exact candidate commit and configuration, with no silent passes.
- **Decision:** a PURE canonical evaluator over the
  matrix producing `GO` (all mandatory controls PASS, no blockers),
  `CONDITIONAL_GO` (only for explicitly declared limited-scope /
  non-production activation — never silently full production), or
  `NO_GO` (any mandatory FAIL/BLOCKED/stale/unevaluable). Properties:
  fail closed; stable finding ordering; identical inputs ⇒
  byte-identical output; evidence bound to candidate commit +
  configuration fingerprint (secrets excluded, D-124); machine +
  human reports generated from ONE canonical result; durable
  attestation hash over (matrix version, candidate commit, config
  fingerprint, evidence references, findings, verdict, approval
  state); any source change, config change, expiry, or failed recheck
  invalidates a prior attestation. A technical GO is necessary but
  NOT sufficient — explicit owner approval remains mandatory.

- **Verification (Phase 26 closeout, 2026-09-19):** shipped
  and battery-attested. Suite 46/46 zero-skip (43 offline +
  3 live-PG) x3 consecutive green; battery 860/860 x2 green,
  zero warnings; ladder 46/46; census reconciles exactly
  (T1=710 - T2=46 - T3=56 - T4=13 = 860, 33 modules); AST /
  entropy / channel sweeps CLEAN; stack 5/5 healthy. Live-leg
  defects fixed in-batch: explicit audit_seq insert with
  ::bigint cast, None-sentinel parity (PG vs JSON vault);
  rehearsal debris pruned, Phase 19-23 chain history intact
  (rows 1-432, verify_chain ok). Result: launch CANDIDATE
  only - no activation performed.
- **Verification (Resilience drill, 2026-09-19):** catastrophic-
  recovery drill shipped and PASSED — a real D-027 store flow
  archived with the D-125 verified-freeze primitives, PROVEN
  destroyed, restored only after archive re-verification, then
  fold- and store-verified byte-equal; forged and missing
  archives fail closed with the Class-B CompactionError
  (4/4 x2 consecutive green, zero skips; `EV-BAC-001` evidence
  bound to the candidate commit + config fingerprint).

- **Verification (DR closeout, 2026-09-19):** binding made fail-closed
  on BOTH legs — a production GO requires a fresh green
  transactional restore drill AND a fresh green decision-ledger
  consistency pass. Five negative paths pinned by battery
  (`test_phase26_dr_closeout.py`): no drill → BLOCKED; consistency
  missing → NO_GO; consistency failed → NO_GO; drill failed →
  NO_GO; forged/missing off-host copy → attestation failure. The
  BAC-001 evidence record carries the combined verdict + drill
  provenance. First-cut fail-open holes (missing/failed consistency
  passing; stale restore_ok) caught and fixed.

## D-139 — Controlled activation, canary & rollback protocol

- **Status:** **Approved** (2026-09-19, owner-approved same-day with all six rulings: no real production activation by implementation; missing operational evidence always NO_GO, never an assumed pass; activation sequence preflight→dry run→limited canary→observation→explicit promotion→rollback on breach approved; audit destinations D-121 engine.log.v1 for machine telemetry + Phase 19 admin.control_audit for human approvals/break-glass; final commit establishes a launch CANDIDATE only — live activation requires a separate explicit one-time owner authorization)
- **Situation:** production activation must be a sequence of
  independently gated, reversible steps — never one global switch —
  with tested rollback at every side-effect-capable state.
- **Decision:** activation state machine `DRAFT →
  ASSESSED → (NO_GO | GO_ATTESTED) → OWNER_APPROVED → DRY_RUN →
  CANARY → OBSERVING → PROMOTED`, with `ROLLING_BACK → ROLLED_BACK`
  reachable from every side-effect-capable state and illegal
  transitions failing deterministically. Preflight (candidate
  identity, clean tree, attestation validity, restore evidence,
  monitoring/escalation) → dry run (config + reachability, ZERO
  public side effects) → limited canary (smallest owner-approved
  scope under D-127/D-128 ceilings, kill-switch available) →
  observation (declared thresholds) → promotion (explicit one-time
  owner approval token with Phase 19 confirmation-key semantics:
  replay/expiry/mismatch/consumed rejected; absence of failures
  never infers approval) → rollback (stop-new-work first, compensate
  second; forensic evidence preserved; outbox/lock/reservation
  reconciliation; post-rollback state report). Audit destinations:
  machine readiness/activation telemetry → D-121 `engine.log.v1`;
  human approval, break-glass, promotion → Phase 19
  `admin.control_audit` hash-chained chain. NO real activation in
  M0 or before explicit one-time owner authorization.

- **Verification (Phase 26 closeout, 2026-09-19):** shipped
  and battery-attested. Suite 46/46 zero-skip (43 offline +
  3 live-PG) x3 consecutive green; battery 860/860 x2 green,
  zero warnings; ladder 46/46; census reconciles exactly
  (T1=710 - T2=46 - T3=56 - T4=13 = 860, 33 modules); AST /
  entropy / channel sweeps CLEAN; stack 5/5 healthy. Live-leg
  defects fixed in-batch: explicit audit_seq insert with
  ::bigint cast, None-sentinel parity (PG vs JSON vault);
  rehearsal debris pruned, Phase 19-23 chain history intact
  (rows 1-432, verify_chain ok). Result: launch CANDIDATE
  only - no activation performed.
- **Verification (Resilience drill, 2026-09-19):** catastrophic-
  recovery drill shipped and PASSED — a real D-027 store flow
  archived with the D-125 verified-freeze primitives, PROVEN
  destroyed, restored only after archive re-verification, then
  fold- and store-verified byte-equal; forged and missing
  archives fail closed with the Class-B CompactionError
  (4/4 x2 consecutive green, zero skips; `EV-BAC-001` evidence
  bound to the candidate commit + config fingerprint).

## D-140 — Launch verification battery & operational evidence pack

- **Status:** **Approved** (2026-09-19, owner-approved same-day with all six rulings: no real production activation by implementation; missing operational evidence always NO_GO, never an assumed pass; activation sequence preflight→dry run→limited canary→observation→explicit promotion→rollback on breach approved; audit destinations D-121 engine.log.v1 for machine telemetry + Phase 19 admin.control_audit for human approvals/break-glass; final commit establishes a launch CANDIDATE only — live activation requires a separate explicit one-time owner authorization)
- **Verification (Phase 26 closeout, 2026-09-19):** shipped
  and battery-attested. Suite 46/46 zero-skip (43 offline +
  3 live-PG) x3 consecutive green; battery 860/860 x2 green,
  zero warnings; ladder 46/46; census reconciles exactly
  (T1=710 - T2=46 - T3=56 - T4=13 = 860, 33 modules); AST /
  entropy / channel sweeps CLEAN; stack 5/5 healthy. Live-leg
  defects fixed in-batch: explicit audit_seq insert with
  ::bigint cast, None-sentinel parity (PG vs JSON vault);
  rehearsal debris pruned, Phase 19-23 chain history intact
  (rows 1-432, verify_chain ok). Result: launch CANDIDATE
  only - no activation performed.
- **Verification (Operator drill, 2026-09-19):** the resilience
  drill is now the `resilience_drill.py` operator command
  (six-stage lifecycle, CLI/JSON status dashboard, run-scoped
  isolation, fail-closed on every fault path — verified by fault
  injection). Drill evidence feeds the D-137 matrix as real
  BAC-001 rehearsal evidence (a FAILED drill blocks BAC-001 ⇒
  NO_GO). Suite 10/10 ×2; battery 870/870 ×2 green.
- **Verification (Resilience drill, 2026-09-19):** catastrophic-
  recovery drill shipped and PASSED — a real D-027 store flow
  archived with the D-125 verified-freeze primitives, PROVEN
  destroyed, restored only after archive re-verification, then
  fold- and store-verified byte-equal; forged and missing
  archives fail closed with the Class-B CompactionError
  (4/4 x2 consecutive green, zero skips; `EV-BAC-001` evidence
  bound to the candidate commit + config fingerprint).
- **Situation:** the launch verdict itself needs a dedicated,
  zero-skip battery and a durable, machine-readable evidence pack
  generated from canonical results only.
- **Decision:** `tests/test_phase26_launch.py` covering:
  matrix schema/completeness; fail-closed handling of missing,
  stale, malformed, contradictory evidence; deterministic verdicts;
  exact commit + config-fingerprint binding; secret-redacted
  evidence; approval-token expiry/mismatch/one-time-use/replay
  rejection; dry-run side-effect prohibition; canary ceilings +
  kill-switch; rollback ordering + post-rollback reconciliation;
  backup-to-restore PROOF (not backup presence); alert-routing and
  escalation verification; offline-hermetic + live-PG coverage per
  repository conventions; full battery ×2 green, zero skips/warnings/
  flakes; exact census + ladder; clean AST/entropy/diff; healthy
  stack. The evidence pack (canonical-generated): candidate commit,
  secrets-free config fingerprint, matrix version, per-control
  verdicts + evidence refs, aggregate verdict, open blockers +
  remediation, backup/restore rehearsal result, monitoring/escalation
  readiness, canary/rollback rehearsal result, approval state,
  attestation hash, battery + census summary. Completion produces a
  LAUNCH CANDIDATE + readiness verdict — it does not launch; live
  activation requires a separate explicit one-time owner
  authorization.

- **Verification (DR closeout, 2026-09-19):** unified attestation
  shipped (`local/scripts/launch_attestation.py`) —
  `qa.launch_attestation.v1` + `qa.health_report.v1` probes
  (transactional drill, decision-ledger drill + consistency,
  AST/entropy, stack, worktree) with a deterministic attestation
  hash. Live run: GO — both DR legs RECOVERED, 533 decisions
  reconciled, sweeps CLEAN. Battery 891/891 ×2 green, zero
  warnings; census T1=769 · T2=44 · T3=68 · T4=10 = 891 (36
  modules); ladder 46/46.

## D-120 — Test-suite taxonomy, deterministic reporting & no-skip gate

- **Status:** **Approved** (2026-09-17, owner-approved)
- **Situation:** the battery has grown to 700+ tests across
  phases; without a declared tier taxonomy, reports cannot state
  what a green run actually covered.
- **Decision:** the suite is organized into four declared tiers —
  T1 Unit (pure contracts/validators), T2 Subsystem Ladder
  (cross-module local engines), T3 Local-PG Integration (live
  containers), T4 Full E2E (multi-engine flows) — and the QA
  toolkit emits a machine-readable tier report (counts per tier,
  skip census MUST be zero, wall-free runtime metrics). A run is
  green only if: zero skipped, zero failures, deterministic seeds
  verified (same seed = same verdicts), and the tier report
  reconciles with the discovery census. The report is a durable
  battery artifact, not a manual claim.
- **Consequences:** every green run carries an auditable coverage
  statement; skip-creep and flaky nondeterminism are structurally
  visible.
- **Verification (Phase 21 closeout, 2026-09-18):** census
  reconciles exactly (724/724 across 28 modules) — T1=629 ·
  T2=46 · T3=42 live-PG · T4=7; zero skips; TWO consecutive
  green battery runs after fixing the last nondeterminism source
  (test race-key collision vs the durable `slot_lock` ledger).

## D-112 — Operator audit ledger and cryptographic verification

- **Status:** **Approved** (2026-09-17, owner-approved)
- **Decision:** every administrative action, manual override, and
  configuration mutation appends to `admin.control_audit` — an
  append-only, SHA-256 hash-chained ledger matching the Phase 18
  standard (prev-hash linkage, sequence validation,
  `verify_chain` tamper detection). Actors are local token refs
  only; zero UI/frontend framework coupling — the control plane is
  a callable facade a thin client may bind to later.
- **Consequences:** "who pressed what, when (logically), with what
  authority, and what changed" is durably answerable and tamper-
  evident.

## D-108 — Audit provenance, ledger parity and security boundaries

- **Status:** **Approved** (2026-09-17, owner-approved)
- **Decision:** the review ledger is TAMPER-EVIDENT: each ledger
  row carries the hash of the previous row for its ticket (SHA-256
  chain), the original AI proposal, reviewer overrides, reasoning,
  and applied actions; `verify_chain` detects any mutation of
  durable decision history. Actors are mock local role references
  only (D-045): no auth backends, no network, no real identities.
- **Consequences:** "who decided what, on which evidence, and what
  ran as a result" is answerable from durable data, and silently
  editing that history is detectable.

## D-104 — Recommendation auditing, HITL boundary and ledger parity

- **Status:** **Approved** (2026-09-17, owner-approved)
- **Situation:** high-impact recommendations could alter business
  state; the system must make human review structurally unavoidable
  exactly where impact is high.
- **Decision:** recommendations whose severity is HIGH or CRITICAL
  (or whose actionable_payload mutates business state) MUST carry a
  HITL review flag and can only reach DISPATCHED_TO_HITL — AUTO_ACCEPT
  is structurally unreachable for them (enforced in code and
  battery-asserted). Every generated insight, evaluation pass, and
  status transition is an immutable D-027 event; the complete
  decision ledger and historical rationale rebuild from durable
  events alone (D-104 ledger parity with D-096/D-100 precedent).
- **Consequences:** no business-altering logic executes without
  human approval; the audit answers "why did the analyst propose
  this?" from durable data.

## D-097 — Canonical media asset and content version contract

- **Status:** **Approved** (2026-09-17, owner-approved)
- **Situation:** campaigns and posts need immutable, content-
  addressed media with versioned content; without a contract every
  domain would invent its own file tracking and lose lineage.
- **Decision:** canonical `MediaAsset` (asset_id, checksum =
  SHA-256 content-addressable hash, mime_type, file_size_bytes,
  storage_uri_reference, metadata) and `ContentVersion` (content_id,
  monotonically increasing version_number, asset_id, parent_version_id,
  metadata). Assets are PURELY content-addressed: one checksum = one
  asset (deduplication by construction). Content versions are
  strictly APPEND-ONLY — an update spawns the next version
  (v1 → v2 → v3); no version is ever mutated; the version graph
  (parent links) must stay a single chain per content_id. Binaries
  live behind the Phase 3 MediaStore abstraction (D-049/D-056) —
  the engine stores only references.
- **Consequences:** byte-identical uploads collapse to one asset;
  full historical content state is reconstructible from the version
  chain; storage stays provider-neutral.

## D-098 — Asset storage vault and deduplication engine

- **Status:** **Approved** (2026-09-17, owner-approved)
- **Situation:** concurrent registrations of the same or conflicting
  assets must resolve deterministically, and corrupt/oversized/
  mime-mismatched uploads must never reach storage.
- **Decision:** atomic registration via PostgreSQL unique
  constraints — `assets.media_asset` PK on checksum,
  `assets.content_version` unique on (content_id, version_number) —
  with a JSON parity vault for offline work. Class-B validation
  BEFORE storage: checksum mismatch (declared vs computed), size
  over the configured cap, mime outside the allow-list, or declared
  mime contradicting detected content signatures is rejected
  locally. The vault never deletes binaries; deletion happens only
  through D-100 quarantine semantics.
- **Consequences:** exactly-one asset per checksum under
  concurrency; invalid uploads rejected before touching storage.

## D-099 — Media variant generator and processing pipeline bridge

- **Status:** **Approved** (2026-09-17, owner-approved)
- **Status note:** pure derivation contract — no external
  transcoder is called directly.
- **Decision:** variant derivation is a deterministic, injected
  processor (provider-neutral bridge, RULES §35): a variant spec
  (kind, parameters) applied to a parent asset yields the same
  variant reference every time — idempotent by derivation key
  SHA-256(parent checksum, kind, canonical parameters). Variant
  lifecycle PENDING_DERIVATION → PROCESSING → READY | FAILED is
  recorded on the D-027 store; re-derivation of an existing READY
  variant is a no-op returning the same reference; a FAILED variant
  may be re-attempted (new attempt, durable attempt count).
- **Consequences:** processing farms can be added later without
  contract changes; retries never duplicate variants.

## D-100 — Asset lifecycle, garbage-collection quarantine and audit vault

- **Status:** **Approved** (2026-09-17, owner-approved)
- **Situation:** unreferenced assets must not be hard-deleted in a
  rush, and every asset action must be auditable.
- **Decision:** soft-delete and quarantine: an asset with no
  referencing content version enters QUARANTINED with a
  configurable retention cooldown measured by the INJECTED clock
  (deterministic — never wall-clock); only assets whose cooldown has
  elapsed AND remain unreferenced become GC-ELIGIBLE, and actual
  binary removal is out of scope for this phase (the record stays,
  flagged). Every upload, version increment, derivation, and
  quarantine action is a D-027 event; historical reconstruction —
  the full content state at any past version — rebuilds from
  durable events alone.
- **Consequences:** no data loss by construction; the audit trail
  answers "what did content X look like at v2?" from durable data.

## D-093 — Scheduled post contract and calendar model

- **Status:** **Approved** (2026-09-17, owner-approved)
- **Situation:** campaigns (Phase 11) publish immediately when
  invoked; the business needs a content calendar — posts planned for
  future release windows — without coupling the calendar to any
  platform or to wall-clock reads.
- **Decision:** a canonical `ScheduledPost` (content ref, target
  matrix = Phase 11 destinations, `scheduled_for` as the producer's
  own ISO instant, idempotency key) with lifecycle `SCHEDULED → DUE →
  DISPATCHED` plus `CANCELLED` (from SCHEDULED/DUE) and
  `RESCHEDULED` (SCHEDULED→SCHEDULED revision, full provenance of
  prior time kept). The injectable clock is the ONLY time source —
  the wall clock never enters any key, bucket, or comparison
  (D-085/D-086 precedent). Every transition is a D-027 event with
  D-026 provenance; the calendar snapshot view is rebuildable from
  durable events alone.
- **Consequences:** scheduling is platform-neutral and
  restart-reconstructible; adding destinations requires no calendar
  change.

## D-094 — Slot conflict prevention and calendar guard

- **Status:** **Approved** (2026-09-17, owner-approved)
- **Situation:** two posts scheduled into the same platform slot
  inside a minimum gap would race at publish time and burn platform
  rate budgets (D-074/D-069 pacer) on avoidable conflicts.
- **Decision:** per-platform slot locking with a configurable
  minimum gap: reservation is a PostgreSQL PK-as-lock
  (`scheduling.slot_lock`, D-070/D-092 precedent) keyed
  (platform, slot bucket); the slot bucket derives from
  `scheduled_for` by pure arithmetic — never the wall clock. A
  conflicting schedule attempt is a deterministic `slot_conflict`
  rejection (Class-B before dispatch) that leaves existing slots
  untouched. JSON parity backend mirrors the semantics offline.
- **Consequences:** the pacer's rate budget is reserved by the
  calendar, not discovered at dispatch; conflicts surface at
  scheduling time where they are cheap to fix.

## D-095 — Due-scanner worker and fan-out bridge

- **Status:** **Approved** (2026-09-17, owner-approved)
- **Situation:** due posts must reach the Phase 11 FanOutEngine
  exactly once, in deterministic order, without the scheduler ever
  re-implementing publishing.
- **Decision:** the due scanner reads DUE posts from durable store
  data only, ordered by `ingest_seq`, and compares each
  `scheduled_for` against the INJECTED clock (`now_iso()` supplied
  by the caller — tests pass a constant; production passes a real
  clock at exactly one boundary). A due post is bridged to
  `FanOutEngine.route()` + `dispatch()`; dispatch receipts are
  consumed and recorded as scheduling events. The scheduler NEVER
  publishes directly, never retries platform semantics (D-052/D-077
  belong to the publishers), and never advances a post past DUE on a
  bridge failure — the failure is recorded and the scanner moves on
  (independent-post discipline, D-077 spirit).
- **Consequences:** one boundary owns time; one module owns
  platform dispatch; the calendar stays a thin, deterministic layer.

## D-096 — Reschedule, cancellation and audit vault

- **Status:** **Approved** (2026-09-17, owner-approved)
- **Situation:** plans change before release; audit demands the full
  history, not the latest state.
- **Decision:** only pre-DISPATCHED posts are mutable: RESCHEDULED
  and CANCELLED are recorded transitions with full provenance (who,
  when per the injected clock, prior value kept) — dispatched and
  other terminal posts are IMMUTABLE and any mutation attempt is a
  recorded deterministic rejection. On reschedule the old slot lock
  is superseded (never reused) and a new slot is claimed; the slot
  ledger therefore audits the complete reservation history. All
  scheduling events live on the D-027 store; the calendar snapshot
  view is rebuilt from durable events alone (no in-process state
  required for correctness).
- **Consequences:** complete what/when/who audit; restart parity of
  the calendar view; no path can alter a dispatched post.

## D-089 — Canonical notification contract and multi-channel schema

- **Status:** **Approved** (2026-09-17, owner-approved)
- **Situation:** OMS fulfillment transitions, HITL queue movements,
  and campaign fan-outs need user-facing alerts across several
  channels; without a contract each producer would invent its own
  payload shape and every channel adapter would re-implement
  validation.
- **Decision:** one universal `NotificationEvent` (recipient,
  channel ∈ {IN_APP, EMAIL, SMS, WEBHOOK}, priority ∈ {LOW, NORMAL,
  HIGH, CRITICAL}, template_id, payload variables, deduplication_key)
  is validated LOCALLY before anything is queued — unknown channel,
  unknown priority, missing template, or a variable that fails the
  template's declared requirements is a Class-B rejection before any
  dispatch (local prevention, D-052). Templates are versioned records
  with declared required variables; recipients are opaque local user
  references — no addresses are invented or harvested by the engine.
  The event carries NO credentials and the contract never reads
  environment state (D-045).
- **Consequences:** producers depend only on the contract; adding a
  channel = one template set + one adapter binding, no producer
  changes.

## D-090 — Idempotent delivery vault, policy guards and independent fan-out

- **Status:** **Approved** (2026-09-17, owner-approved)
- **Situation:** the same logical alert must be delivered at most
  once per channel even across worker restarts and concurrent
  dispatchers, and quiet-hours / frequency-capping policies must be
  enforced deterministically.
- **Decision:** a `NotificationVault` keyed by
  `deduplication_key` (SHA-256 over event identity + channel)
  provides strict idempotency — the winner claims via a PostgreSQL
  PK-as-lock (`notifications.delivery_lock`); losers record a
  deterministic `duplicate_blocked` outcome and never dispatch.
  Policy guards run BEFORE the vault claim: quiet hours and per-
  recipient frequency caps are pure functions of the payload's own
  timestamps plus the durable delivery ledger — never wall-clock.
  Channel fan-out is INDEPENDENT (D-077 discipline): a failure in
  SMS never blocks, rolls back, or marks IN_APP/WEBHOOK outcomes.
- **Consequences:** restart-safe exactly-once-per-channel delivery;
  policy violations surface as recorded deterministic outcomes
  (`policy_deferred`), not silent drops.

## D-091 — Notification outbox and queue worker with backoff and DLQ

- **Status:** **Approved** (2026-09-17, owner-approved)
- **Situation:** dispatch must be reliable and non-blocking even
  when a channel adapter is slow or down, mirroring the Phase 12
  receipt model and the Phase 9/10 classification.
- **Decision:** a transactional outbox on the D-027 event store —
  enqueue is an event; the worker drains pending notifications with
  per-channel adapters behind the provider-neutral boundary. Transient
  errors (Class-A) retry with exponential backoff capped by a
  configurable max-attempts; contract-invalid payloads (Class-B) go
  straight to the dead-letter queue with the recorded reason; per-
  recipient rate-limit backoff (Class-C semantics) honors the
  indicated wait; permanently failing notifications end in the DLQ
  and materialize a HITL review record (D-028/D-050) — no automatic
  resolution.
- **Consequences:** at-least-once enqueue + exactly-once-per-channel
  claim = end-to-end exactly-once; no loss on restart; DLQ grows
  only with genuine failures and is always human-actionable.

## D-092 — Notification delivery audit and status tracking

- **Status:** **Approved** (2026-09-17, owner-approved)
- **Situation:** alert delivery must be auditable and reconstructible
  from durable state, like every other domain.
- **Decision:** every dispatch attempt, receipt, and failure reason
  is a D-027 event with D-026 provenance (actor = the dispatcher,
  review state = system-generated). Delivery status aggregates over
  the deterministic lifecycle `PENDING → QUEUED → DISPATCHED →
  DELIVERED | FAILED | POLICY_DEFERRED | DUPLICATE_BLOCKED` with
  FAILED terminal only after DLQ admission; every persisted string
  passes through the established redaction discipline (D-045). The
  status view is rebuilt from durable store data only — no in-process
  cache is required for correctness.
- **Consequences:** the full delivery story of any notification is
  reconstructible after restart from the event store alone.

## D-085 — Canonical analytics model, CQRS boundary and deterministic aggregation

- **Status:** **Approved** (2026-09-16, owner-approved)
- **Situation:** Phases 7–12 produce events across publishing,
  orders, and HITL; the platform needs a read-side analytics model
  decoupled from the transactional write path, with aggregation
  that never depends on wall-clock reads.
- **Decision:** analytics is a **read-side projection (CQRS)** over
  the D-027 store: canonical metric events (publication reach /
  engagement, order placement / conversion, revenue) are derived
  ONLY from durable succeeded events — the projection never writes
  back to domain tables. Aggregation windows (hourly / daily /
  monthly) are computed deterministically from each event's OWN
  recorded ISO timestamp field (`occurred_at` carried in the event
  payload) — no wall-clock read enters any key or bucket. Money
  stays strict integer minor units (D-081 discipline). The read
  model lives in the `analytics` PG schema (JSON parity store for
  offline tests) and may be discarded and rebuilt at any time
  without losing canonical state.
- **Consequences:** analytics queries can never corrupt the
  transactional model; rebuilding the projection is a safe,
  repeatable operation; window boundaries are reproducible.

## D-086 — Snapshot engine and incremental projection via ingest_seq

- **Status:** **Approved** (2026-09-16, owner-approved)
- **Situation:** re-aggregating the whole event history on every
  query does not scale; snapshots must be consistent with the
  durable event ordering and restart-safe.
- **Decision:** the projection engine records a durable **cursor**
  = the D-027 store's monotonic `ingest_seq` (the Phase-7 audit
  ordering key; received_at is never trusted). Snapshots are
  materialized projection states keyed by window; an incremental
  pass consumes only events with `ingest_seq > cursor` and then
  advances the cursor atomically with the snapshot write. Rebuild
  = reset cursor to 0 and replay — deterministic, identical
  output. A partial pass that fails before the snapshot write
  leaves the cursor unchanged (no lost events, no double-count).
- **Consequences:** snapshots are eventually consistent with the
  store, exactly-once per event under retries, and safe across
  restarts; heavy queries read snapshots, not raw events.

## D-087 — Cross-domain correlator without hard domain coupling

- **Status:** **Approved** (2026-09-16, owner-approved)
- **Situation:** connecting publication performance (Phases 9–11)
  to order outcomes (Phase 12) must not couple the publishing and
  OMS domains through direct calls.
- **Decision:** correlation is computed **in the read model only**:
  publication events carry an optional `campaign_id` and order
  events carry an optional `source_campaign_id` — both populated by
  their own domains at write time if the caller supplies one. The
  correlator joins those two streams through the shared value
  (campaign_id) over a configurable attribution window (events
  after a publication, within N hours, deterministic from the
  recorded timestamps). No publishing module ever calls OMS code
  and vice versa; a missing campaign_id is simply an unattributed
  row, never an error. Attribution output is a projection table,
  recomputable by rebuild.
- **Consequences:** domains stay decoupled (one shared string
  field, zero imports); attribution is reproducible and auditable;
  unattributed conversions remain visible instead of dropped.

## D-088 — Analytics export surface and report audit vault

- **Status:** **Approved** (2026-09-16, owner-approved)
- **Situation:** reports must be reproducible, auditable, and safe
  to re-generate; no credential or customer-identifying data may
  leak through exports.
- **Decision:** export renders a projection snapshot to **JSON or
  CSV** deterministically; a report is identified by a SHA-256
  `window_hash` over (report kind, window bounds, source cursor)
  — identical inputs yield a byte-identical report, so generation
  is idempotent (same hash returns the stored report; changed
  inputs produce a new hash). Every generation/request is appended
  to a report audit vault (D-026-aligned: actor, kind, window,
  hash, row count, generated-from cursor). Exports contain only
  aggregated metrics — no customer identifiers, no credentials,
  no tokens (D-045); the CSV dialect is fixed (UTF-8, header row,
  comma, RFC-quoted) so output is reproducible byte-for-byte.
- **Consequences:** a report can be re-generated and verified
  against its hash at any time; the audit trail proves what was
  produced, when, and from which durable state.


- **Status:** **Approved** (2026-09-16, owner-approved)
- **Situation:** Phase 12 introduces order management; orders need a
  canonical schema (line items, customer ref, pricing, tax,
  fulfillment status), a strict state machine, and duplicate-order
  protection aligned with the D-014/D-015/D-017 identifier
  discipline and the D-027 event store.
- **Decision:** the canonical `Order` carries an owner-assigned
  `order_id`, a caller-supplied `client_order_id`, line items bound
  to canonical Product ID / Variant ID / SKU (D-017 — SKU is never
  the internal identity), pricing per line and per order, tax, and
  fulfillment status. Lifecycle: `PLACED → VALIDATED → FULFILLING →
  COMPLETED`, with `CANCELLED` reachable from any pre-COMPLETED
  state and `REFUNDED` reachable only from COMPLETED (terminal
  states immutable). Duplicate protection: SHA-256 idempotency key
  over `client_order_id` — the same client_order_id replays the
  same order deterministically (skipped_duplicate), a conflicting
  payload under the same key is an integrity error / human review
  (D-027 semantics, never silently reprocessed).
- **Consequences:** order state is reconstructible from the durable
  event store alone; duplicate checkout traffic cannot create
  duplicate orders; payment stays out of scope (D-083).

## D-082 — Inventory abstraction and atomic reservation guardrails

- **Status:** **Approved** (2026-09-16, owner-approved)
- **Situation:** over-selling must be impossible under concurrency;
  stock lives behind an abstraction so the future WooCommerce stock
  projection (Phase 3) or another provider can be swapped in
  without changing order logic.
- **Decision:** inventory is a provider-neutral boundary
  (`InventoryStore`) tracking stock levels keyed by SKU, with
  atomic **reservation on entry to `VALIDATED`** and release on
  `CANCELLED`/`REFUNDED`. The live implementation uses PostgreSQL
  row-level locking (`UPDATE ... WHERE stock >= qty` guarded
  conditional write on `oms.inventory`) so concurrent reservations
  serialize at the row: over-sell returns a deterministic
  `insufficient_stock` outcome, never a partial reservation. A
  JSON parity store covers offline tests. Reservation state is
  durable and restart-safe.
- **Consequences:** no oversell by construction; the Woo stock
  projection remains a drop-in provider; reservation release is
  explicit and audited (D-026).

## D-083 — Payment-neutral boundary and fulfillment fan-out integration

- **Status:** **Approved** (2026-09-16, owner-approved)
- **Situation:** no payment gateway exists or is authorized (D-045);
  orders still need to flow to fulfillment and customer
  notification today.
- **Decision:** payment is a boundary, not a module: orders carry a
  `payment_status` limited to `pending` / `unpaid` markers with NO
  gateway logic, NO payment credentials, and NO payment webhooks —
  any future provider is a drop-in behind the boundary. Fulfillment
  notifications integrate with the Phase 11 `FanOutEngine`:
  order-transition events may dispatch confirmation/status messages
  through the same D-077 destination matrix and platform vaults;
  the OMS never talks to a platform adapter directly and a
  notification failure NEVER blocks or corrupts the order
  transition (independent fan-out, D-077/D-078).
- **Consequences:** payment can be added later without redesign;
  order state and notification state are independently
  reconstructible; the Phase 11 anti-race and vault isolation apply
  unchanged.

## D-084 — Order audit trail and TTL reconciliation vault

- **Status:** **Approved** (2026-09-16, owner-approved)
- **Situation:** orders must have an immutable transition audit and
  abandoned in-flight orders must not accumulate forever.
- **Decision:** every order transition is a D-027 event
  (`oms|transition|...`) with the D-026 provenance actor — append-
  only, reconstructible, no in-place mutation. A reconciliation
  worker scans `FULFILLING` orders whose fulfillment receipt is
  missing past a configurable TTL (default owner-tunable, no
  wall-clock in key material) and auto-cancels them deterministically
  with `CANCELLED` + reason `fulfillment_ttl_expired`, releasing
  reserved stock (D-082) and recording provenance. The worker never
  touches COMPLETED orders and never invents fulfillment facts.
- **Consequences:** the audit is tamper-evident by construction;
  stuck orders converge to a bounded terminal state; stock is
  returned to sellable inventory automatically.


- **Status:** **Approved** (2026-09-16, owner-approved)
- **Situation:** Phases 9–10 each publish to one platform through
  their own adapter/vault/outbox; campaigns need one universal
  content representation dispatched to an arbitrary target set
  (e.g. `["instagram", "telegram"]`) without the orchestrator
  re-implementing platform rules.
- **Decision:** a single `fanout_dispatch` payload carries the
  universal representation (campaign/content ids, media descriptor,
  text, hashtag plan, schedule window, target list). A per-target
  **destination matrix** binds each target to its Phase 9/10
  transform + validation + publish entry points. Target transforms
  are platform-conforming and local: Instagram keeps its D-069
  validators (aspect ratio, caption ≤ 2200, hashtags ≤ 30);
  Telegram keeps its D-073 validators (MarkdownV2/HTML escaping,
  caption ≤ 1024 / text ≤ 4096, album ≤ 10). A target that cannot
  be adapted fails **locally, before any dispatch**, without
  affecting sibling targets.
- **Consequences:** independent fan-out — one platform's failure
  never rolls back or corrupts another's publication; adding a
  future platform = one matrix row, no engine change.

## D-078 — Orchestration lifecycle, partial-success model and receipts

- **Status:** **Approved** (2026-09-16, owner-approved)
- **Situation:** multi-target dispatch cannot reuse the single-
  platform state machines; the aggregate needs its own deterministic
  lifecycle with a partial-success semantics that never loses the
  per-platform truth.
- **Decision:** `FanOutLifecycle` state machine
  `PENDING → ROUTED → DISPATCHING → SUCCESS | PARTIAL_SUCCESS |
  FAILED`, with `CANCELLED` reachable from PENDING/ROUTED via
  explicit human action (D-080). Sub-publications stay in their own
  Phase 9/10 machines; the aggregate derives its state **only**
  from durable sub-task terminal states (strict deterministic
  aggregation: all published → SUCCESS; ≥1 published and ≥1
  failed/terminal-rejected → PARTIAL_SUCCESS; none published and ≥1
  terminal failure with nothing pending → FAILED). Every sub-task
  outcome is a D-027 event (`fanout|<job>|<target>`); the job record
  carries sub-task ids, target receipts and outcome events — full
  D-026 provenance on every transition.
- **Consequences:** aggregate state is always reconstructible from
  durable data (restart-safe); partial success is a first-class
  outcome, never silently upgraded or downgraded.

## D-079 — Coordinated publishing schedule and cross-platform anti-race lock

- **Status:** **Approved** (2026-09-16, owner-approved)
- **Situation:** simultaneous or staggered multi-channel release
  windows invite double-triggering across workers, which platform
  vaults alone cannot prevent (they guard one platform's key, not
  the campaign-level dispatch).
- **Decision:** each fan-out job carries a coordinated release
  window (`release_at` + optional per-target stagger seconds);
  dispatch is gated on the window per target. A campaign-level
  **anti-race lock** (`orchestration.fanout_lock`, PK-as-lock on
  the canonical PostgreSQL instance, same semantics as the D-070/
  D-074 platform locks) guarantees exactly one dispatcher claim per
  job, while each platform keeps its own idempotency vault
  isolation (D-070/D-074 unchanged). Orchestration state updates
  are written transactionally through the canonical D-027 store.
- **Consequences:** no cross-worker duplicate fan-out; staggered
  windows are deterministic; platform-level idempotency remains
  independently enforced beneath the campaign lock.

## D-080 — Fan-out resiliency, HITL cancellation and reconciliation worker

- **Status:** **Approved** (2026-09-16, owner-approved)
- **Situation:** partial failures and restarts demand retry that is
  surgical (never re-publish a succeeded target), human control
  over not-yet-started targets, and a recovery path that repairs
  the aggregate view from durable state after crashes.
- **Decision:** retry coordination is platform-aware — retry
  re-dispatches **only** targets whose sub-task is retryable
  (failed / terminal-rejected-but-retriggerable per that platform's
  rules) and never re-triggers a PUBLISHED target (its receipt is
  the skip proof). `cancel(job_id, targets)` is a HITL action
  (D-026 provenance, actor recorded) that marks unstarted targets
  CANCELLED; started/published targets cannot be cancelled. A
  reconciliation worker scans in-flight jobs on boot/recovery and
  re-derives aggregate state strictly from the durable sub-task
  records — no in-process memory is authoritative.
- **Consequences:** retries never duplicate published work;
  cancellation is bounded and auditable; crash recovery is a
  deterministic re-derivation, not a guess.

## D-069 — Instagram media & publishing contract and state machine

- **Status:** **Approved** (2026-09-16, owner-approved)
- **Situation:** MASTER_PLAN Phase 9 calls for official Meta
  integration; publishing needs a deterministic contract BEFORE any
  network work, and Phase 3 D-051 media direction means Instagram
  publishes media already handled by the media abstraction.
- **Decision:** implement the Meta Graph API two-step async container
  workflow as an explicit state machine:
  `MEDIA_CREATE → CONTAINER_STATUS (poll until READY/ERROR) →
  MEDIA_PUBLISH → PUBLISHED`, with `FAILED` reachable from any
  non-terminal state and terminal states immutable. Media constraints
  are validated LOCALLY before any network dispatch: aspect ratio ∈
  {1:1, 4:5, 16:9}, caption ≤ 2200 chars, hashtags ≤ 30, media_ref
  required. Invalid payloads are rejected locally as Class-B
  prevention — no network call is ever made for a payload that cannot
  be valid.
- **Consequences:** the workflow is testable end-to-end on mock
  adapters; contract violations never consume API quota; state is
  reconstructable from the D-027 event store.

## D-070 — Anti-duplicate publishing guard and idempotency vault

- **Status:** **Approved** (2026-09-16, owner-approved)
- **Situation:** double-publishing to a live Instagram account is the
  worst-case harm of this phase; network retries and concurrent
  dispatchers can both trigger repeats.
- **Decision:** a deterministic `publish_idempotency_key` =
  SHA256(`content_id` + `media_hash` + `caption_hash` +
  `scheduled_slot`) is computed for every publish attempt; an
  EXCLUSIVE publishing lock on that key is acquired in the canonical
  PostgreSQL store (D-055) BEFORE network initiation — the lock row is
  created transactionally and a second acquirer of the same key is a
  terminal `duplicate_publish_blocked` outcome, never a second
  publish. The key lives in the D-027 event store so retries,
  restarts, and concurrent dispatchers all resolve to the same
  verdict. The scheduled_slot makes distinct deliberate re-publications
  addressable without weakening retry dedup.
- **Consequences:** absolute double-publish protection under retry OR
  concurrency; the guard is enforced by the canonical store, not by
  in-process memory; audit trail records every blocked duplicate.

## D-071 — Owner-gated live Graph API adapter and token boundary

- **Status:** **Approved** (2026-09-16, owner-approved; connectivity
  itself remains OFF until the owner supplies credentials)
- **Situation:** D-066 established the enablement pattern for AI
  providers; Instagram requires the identical discipline for the Meta
  Graph API.
- **Decision:** `InstagramAdapter` interface with pluggable
  transports (zero network in tests); a high-fidelity
  `MockInstagramAdapter` (deterministic container lifecycle, scripted
  failures); live `GraphApiAdapter` gated behind `INSTAGRAM_LIVE_ENABLED=true`
  AND required env keys, else deterministic Class-B refusal. All
  access tokens are redacted from logs, errors, and observability
  records (D-045); no credential exists, none is requested.
- **Consequences:** enabling live publishing is configuration + owner
  action, never a code change; the mock exercises the full contract
  including failure paths.

## D-072 — Outbox publishing queue and DLQ error classifier

- **Status:** **Approved** (2026-09-16, owner-approved)
- **Situation:** publish attempts must survive crashes between steps
  and must never retry what can never succeed.
- **Decision:** transactional Outbox pattern — queued posts are
  durable rows/events in the canonical store before any dispatch; a
  worker claims one item at a time and advances the D-069 state
  machine. Error classification: Class-A transient network →
  exponential backoff (retry budget bounded); Class-B schema/media
  invalid → terminal reject WITHOUT retry; Class-C rate limit/429 →
  cooldown queue (retry after cooldown, not immediately); Class-E
  token expired → FREEZE the queue and alert (never loop). Unrecoverable
  failures route to a Dead-Letter Queue with a full audit record
  (D-026 provenance) and never silently disappear.
- **Consequences:** crash-safe, quota-safe publishing; every terminal
  failure is auditable in the DLQ; the classifier reuses the D-052
  classes so operations stay uniform across phases.

## Open decision register

| # | Decision | Status | Blocking | Target phase |
| --- | --- | --- | --- | --- |
| 1 | ~~Final SKU convention~~ — resolved: D-014 **Approved** | Resolved | — | 2 (done) |
| 2 | ~~Truly required product fields~~ — resolved: D-021 **Approved** | Resolved | — | 2 (done) |
| 3 | Controlled-vocabulary registry v1 — structure resolved (D-029); concrete values **owner-approved via D-031 Batch 1** (2+12+8 categories; 25 color terms; size terms in 3 families); color/size SKU-code mappings **resolved via D-032 Batch 2** (O/I/L-safe); **aliases remain open** | Open (partially resolved) | Aliases | 2 |
| 4 | Data-entry language for product data | Open | Product data entry | 2 |
| 5 | ~~WooCommerce field mapping (conceptual → WooCommerce)~~ — resolved via D-034–D-043 (identity/type/category/attribute/price/lifecycle/media mapping + API contract; foundation design in `docs/phases/phase-03-1-woocommerce-foundation.md`) and operationalized via D-046–D-052 (registry design, sync/CRUD contracts, authority matrix, media direction, non-registry representation, test strategy — `docs/phases/phase-03-2-woocommerce-sync-architecture.md`); remaining sub-gate ~~D-048 price-sync proposal~~ resolved (owner-approved 2026-09-13, Option A); media provider (Phase 4) | Open (partially resolved) | Media provider (Phase 4) | 3 (design done) |
| 6 | WooCommerce hosting / VPS | Open | Store setup | 3–4 |
| 7 | n8n deployment model (cloud vs self-hosted) | Open | n8n foundation | 5 |
| 8 | Secret-management tooling | Concept resolved: D-045 + Batch 2 extension (environment separation, reference-based credentials, rotation concept, redaction, Git/prompt exclusion — `docs/phases/phase-03-2-woocommerce-sync-architecture.md` §12); concrete tooling selection **Open** | First credential | 5 |
| 9 | AI provider(s) — concrete vendor/model selection (OpenAI / Anthropic / local) + credentials; D-062 makes selection a drop-in `AiProvider`, D-045 gates credentials | Open | Owner selection + connectivity milestone | 7 |
| 10 | Iranian payment provider | Open | Payment go-live | 12 |
| 11 | Iranian shipping provider | Open | Shipping go-live | 13 |
| 12 | Instagram API surface / account setup | Open | Instagram integration | 9 |
| 13 | ~~Variant-defining attributes~~ — resolved: D-018 **Approved** ({color, size}, per-axis applicability) | Resolved | — | 2 (done) |
| 14 | ~~Variant ID generation mechanism~~ — resolved: D-017 **Approved** (UUIDv4) | Resolved | — | 2 (done) |
| 15 | Size system — architecture (D-020), size-code governance (D-030), size **terms** (D-031 Batch 1), and concrete size-code mappings (D-032 Batch 2, O/I/L-safe, family-scoped) **Approved**; size-equivalence mappings remain an open owner sub-decision | Open (partially resolved) | Size-equivalence mappings (if ever needed) | 2 |
| 16 | ~~Product status state machine~~ — resolved: D-022 **Approved** (draft/active/archived) | Resolved | — | 2 (done) |
| 17 | ~~Publication status values~~ — resolved: D-023 **Approved** (unpublished/in_review/published/withdrawn) | Resolved | — | 2 (done) |
| 18 | ~~Price model~~ — resolved: D-024 **Approved** (list price + variant override + sale price; effective price precedence) | Resolved | — | 2 (done) |
| 19 | ~~Discount model~~ — resolved: D-025 **Approved** (sale-price-based; no engine; no coupons) | Resolved | — | 2 (done) |
| 20 | ~~Provenance mechanism~~ — resolved: D-026 **Approved** (per-value provenance tuple; append-only; storage deferred) | Resolved | — | 2 (done) |
| 21 | ~~Import idempotency strategy~~ — resolved: D-027 **Approved** (event-level) + D-017 (identifier-based) | Resolved | — | 2 (done) |
| 22 | ~~Excel import scope~~ — resolved: D-028 **Approved** (one workbook; dry-run; human-approved exceptions; no IDs/SKUs/inventory from Excel); physical mapping resolved by D-033 | Resolved | — | 2 (done) |
| 23 | SEO slug language (D-016.M) | Open/deferred | Product URLs | 2 or 3 |
| 24 | ~~D-030 ↔ D-032 conflict — size code `LG`~~ — **RESOLVED (2026-09-13, owner): D-057** — the canonical Alpha-L code is now `LRG` (explicit owner sanction; deprecate+replace per D-030 rule 5; `LG` was never referenced by real data; a D-030 wording clarification is recommended — see D-057's honest governance note). Seed gate clear: **28/28 size terms seed**; Alpha-L sync unblocked | Resolved (sanctioned) | D-030 wording clarification (non-blocking) | 3 (done) |
| 25 | ~~AI runtime contracts (router, output schemas, cost guardrails, proposal pipeline)~~ — **D-062 / D-063 / D-064 (Approved 2026-09-15)**; extended by **D-065–D-068 (Approved 2026-09-16)**: unified observability (D-065), owner-gated live adapters + budget quarantine (D-066), template versioning registry (D-067), HITL review inbox + bulk orchestrator (D-068); live credentials still gated by D-045 and register row 9 | Approved | — | 7–8 (done) |
| 26 | ~~Instagram API surface / account setup~~ (see row 12) — publishing **architecture** resolved via **D-069–D-072 (Approved 2026-09-16)**: 2-step container workflow contract, anti-duplicate idempotency vault, owner-gated Graph API adapter + token redaction, outbox + DLQ error classifier; live Meta connectivity/credentials remain owner-gated (D-045) | Approved (architecture) | Meta account + credentials (owner) | 9 (architecture done) |
| 27 | Cross-platform fan-out orchestration — **D-077–D-080 (Approved 2026-09-16)**: universal dispatch contract + destination matrix (D-077), `FanOutLifecycle` with partial-success model + receipts (D-078), coordinated release windows + campaign-level anti-race lock `orchestration.fanout_lock` (D-079), retry isolation, HITL cancellation, reconciliation worker (D-080); live platform connectivity remains owner-gated per D-045/D-071/D-075 | Approved | — | 11 (architecture done) |
| 28 | Order management system — **D-081–D-084 (Approved 2026-09-16)**: order contract + lifecycle `PLACED → VALIDATED → FULFILLING → COMPLETED` with CANCELLED/REFUNDED terminals and client_order_id SHA-256 idempotency (D-081), provider-neutral inventory with atomic PG row-lock reservation — no oversell (D-082), payment-neutral boundary + Phase 11 fan-out notification integration (D-083), immutable transition audit + TTL auto-cancel reconciliation vault (D-084); payment gateway and live credentials remain owner-gated per D-045 | Approved | — | 12 (architecture done) |
| 29 | Analytics, reporting & metrics engine — **D-085–D-088 (Approved 2026-09-16)**: CQRS read-side projections over the D-027 store with deterministic windowing from recorded event timestamps, no wall-clock keys (D-085), incremental snapshots keyed by the monotonic ingest_seq cursor — exactly-once, rebuild-safe (D-086), cross-domain campaign→revenue correlator joined on shared campaign_id with zero domain imports (D-087), idempotent JSON/CSV export keyed by window hash + report audit vault, aggregates only — no customer data (D-088) | Approved | — | 13 (architecture done) |
| 30 | Notification system & user alerts — **D-089–D-092 (Approved 2026-09-17)**: universal NotificationEvent contract with local Class-B validation before queueing (D-089); deduplication_key vault + PG PK-as-lock, pure-function quiet-hours/frequency guards, independent per-channel fan-out (D-090); transactional outbox worker with exponential backoff and HITL-materializing DLQ (D-091); full delivery audit on the D-027 store with restart-reconstructible status tracking (D-092). |
| 31 | Content calendar & scheduling engine — **D-093–D-096 (Approved 2026-09-17)**: canonical ScheduledPost lifecycle SCHEDULED → DUE → DISPATCHED (+CANCELLED/RESCHEDULED, full provenance) with the injectable clock as the only time source (D-093); per-platform PK-as-lock slot reservations with configurable minimum gap, slot_conflict = Class-B before dispatch (D-094); due scanner from durable data ordered by ingest_seq bridging to the Phase 11 FanOutEngine — scheduler never publishes (D-095); only pre-DISPATCHED posts mutable, slot ledger audits full reservation history, calendar view rebuilds from durable events alone (D-096). |
| 32 | Content versioning & media assets — **D-097–D-100 (Approved 2026-09-17)**: canonical MediaAsset/ContentVersion with SHA-256 content-addressable dedup and append-only version chains (D-097); atomic PG-constraint registration (PK checksum, unique (content_id, version_number)) with Class-B pre-storage validation and JSON parity (D-098); deterministic idempotent variant derivation behind a provider-neutral bridge (D-099); quarantine with injected-clock retention cooldown, full D-027 audit and historical version reconstruction from durable events (D-100). |
| 33 | AI business analyst & decision engine — **D-101–D-104 (Approved 2026-09-17)**: canonical BusinessInsight/Recommendation with GENERATED → EVALUATED → DISPATCHED_TO_HITL/AUTO_ACCEPTED/DISMISSED (+SUPERSEDED) lifecycle, deterministic pure rule evaluation over durable Phase 12/13 metrics, SHA-256 insight dedup over (category, correlation keys, window refs) in `analytics.business_insight`, injected anomaly detectors recorded strictly as D-027 audit events, and a structurally enforced HITL boundary for HIGH/CRITICAL severity (auto-accept unreachable; full ledger rebuildable from durable events alone). |
| 34 | HITL approval engine & decision ledger — **D-105–D-108 (Approved 2026-09-17)**: canonical HitlReviewTicket with PENDING_REVIEW → CLAIMED → APPROVED/REJECTED/MODIFIED/ESCALATED/EXPIRED lifecycle (escalation re-queues, expiry only via deterministic sweep), PK-as-lock atomic claims over `hitl.review_tickets` + append-only hash-chained `hitl.review_ledger`, ingestion of Phase 17 DISPATCHED_TO_HITL insights, idempotent command dispatch through injected queue-type dispatchers, tamper-evident chain verification, mock local actors only (D-045). |
| 35 | Internal tools & operator control plane — **D-109–D-112 (Approved 2026-09-17)**: closed command grammar (PAUSE/RESUME_QUEUE, RETRY_DLQ_ITEM, FORCE_SUPERSEDE_INSIGHT, MANUAL_SLOT_OVERRIDE, REPLAY_EVENTS) with deterministic local-token RBAC, ControlPlaneEngine over `admin.operator_actions` (PK-as-lock) + hash-chained `admin.control_audit` (Phase 18 tamper standard), an injected-read multi-domain state facade (DLQ/HITL/insights/assets), replay strictly dry-run unless a single-use confirmation key is supplied, DLQ retries + circuit breakers with deterministic logical-clock cool-downs, and zero cross-module imports (D-045/D-027 discipline). |
| 36 | Security hardening & threat model — **D-113–D-116 (Approved 2026-09-17)**: canonical threat taxonomy (credential leakage D-045, replay attacks, ledger tampering, race injection, oversized/malformed payloads, error-surface probing) mapped control-to-test with no untested claims; a system-wide InputHardeningGate (size/charset/depth limits, duplicate-key + homoglyph rejection, NFC canonicalization); chain-head attestations over the Phase 18/19 hash chains with O(1) verification and chain-anchored replay-key burns; deterministic rate limits + lockouts on the injected clock; and a repository-wide extended AST + entropy sweep as a battery-executed test artifact. |
| 37 | Testing & quality engineering — **D-117–D-120 (Approved 2026-09-17)**: formal state-machine invariant auditing across all five Phase 12–19 machines (edge matrices closed, terminals exitless, refused writes leave zero partial rows on live PG, crash-reconciled attestation); deterministic fault injection & local chaos at injected seams only (handler/dispatcher exceptions, transient dispatch, mid-transaction PG aborts, ledger contention — with clean-rollback, audit-truth and ledger-integrity invariants); seeded mutational fuzz hardening of every D-114 entry point (deterministic Class-B or clean acceptance, never unhandled exceptions/hangs/mutation); and a four-tier suite taxonomy (Unit → Subsystem Ladder → Local-PG Integration → Full E2E) with machine-readable reports and a zero-skip gate. |
| 38 | Observability & health telemetry — **D-121–D-124 (Approved 2026-09-18)**: local structured event log ledger (`engine.log.v1` JSONL + durable D-027-backed vault, deterministic trace/causal-chain ids, D-114 sanitization at the log boundary); deterministic metrics registry with localhost-only Prometheus text exposition (bounded declared cardinality, logical-timeline updates); composable health probes with the machine-readable `qa.health_report.v1` attestation (PG reachability/schema, ledger attestation validity, queue depth, breaker states); and zero-leak telemetry discipline (redaction + PII denylist + fixed `[REDACTED]` marker, battery-enforced, no engine imports from observability modules). |
| 42 | Launch readiness, Go/No-Go attestation & controlled activation — **D-137–D-140 (Approved 2026-09-19, all six owner rulings applied)**: canonical versioned control matrix over the nine MASTER_PLAN launch domains with fail-closed states (missing/stale evidence is never a pass); deterministic pure Go/No-Go evaluator with commit+config-bound attestation hashing (GO necessary but not sufficient); controlled activation state machine (preflight → dry run → canary → observation → promotion → rollback) with one-time owner-approval tokens, canary ceilings, kill-switch, and reconciliation-preserving rollback; launch verification battery + canonical evidence pack — candidate, never silent live activation.
| 41 | Full system test & E2E failure/recovery ladder — **D-133–D-136 (Proposed 2026-09-18)**: pure 10-stage end-to-end conductor over declared stage envelopes with unbroken D-121 trace context and zero schema mutation; deterministic chaos ladder at every boundary (channel outage, AI budget refusal, media fault, lock contention, payment-verify failure) asserting exact D-052 classes, breaker engagement, exact-ledger rollback, and replay-to-completion recovery; automated state reconciliation (outbox replay, stranded-lock sweeps, compaction recovery, crash-restart from durable stores only); full-spectrum offline-hermetic + live-PG E2E battery with zero-skip acceptance gates.
| 40 | Vendor lock-in & neutral portability — **D-129–D-132 (Approved 2026-09-18)**: provider-neutrality contract with token-accounting write-through and conformance harness; storage/database parity boundaries (BackendPair harness, MediaStoreContract, AST-enforced SQL portability); pluggable channel-adapter interchange protocol with hot-swap registry and workflow-isolation AST rule; portability & port-swapping verification battery.
| 39 | Resilience & cost optimization — **D-125–D-128 (Approved 2026-09-18)**: deterministic retention/compaction with verified-freeze archives (state-based eligibility, attestation-verified snapshots, fail-closed teardown, hardening_audit manifests, declared indexes + keyset reads — tamper-evidence NEVER weakened); a shared resilience envelope (D-052-bound retry policy with logical backoff, budgeted executor, psql transport concurrency ceiling with deterministic fast-fail); platform resource-budget envelopes extending D-063 semantics (≥80% warn / 100% pre-dispatch refusal, per_run/per_logical_day windows, green/yellow scopes, single consumption ledger with AI write-through); and a chaos × compaction × quota verification battery. |

Nothing in this register may be resolved silently (PROJECT_RULES §4).
Only the human owner approves decisions; D-014, D-015, D-017, D-018,
D-019 (governance), D-020 (architecture), D-021, D-022, D-023, D-024,
D-025, D-026, D-027, D-028, D-029 (structure), D-030 (governance),
D-031 (business data configuration, Batch 1), D-032 (business data
configuration, Batch 2), D-033 (physical Excel contract),D-034–D-045 (Phase 3 Batch 1 — WooCommerce foundation mapping and
integration contract), D-046, D-047, D-049, D-050, D-051, D-052
(Phase 3 Batch 2 — sync architecture), and D-053 (Phase 3 Batch 3 —
local-first development environment and promotion model) are approved,
including
**D-048 — Option A: canonical-layer price projection (owner-approved
2026-09-13)**; **D-054 (local runtime), D-055 (canonical database),
D-056 (local media emulator) are owner-approved (2026-09-13)**;
**D-062, D-063, D-064 (2026-09-15) and D-065, D-066, D-067, D-068
(2026-09-16) are owner-approved**;
D-016 and every item not marked
Resolved above remains open — including the color/size aliases
(item 3), the size-equivalence mappings
(item 15), and the media
provider selection (Phase 4).

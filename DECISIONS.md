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
  - A. **Variant-defining attributes** — proposed {color, size} — OPEN
    pending final Phase 2 validation.
  - B. **Minimum required product fields** — OPEN.
  - C. **Controlled vocabularies** — OPEN for Phase 2 implementation;
    initial registries will eventually include at least colors, sizes,
    categories, and other controlled fields as needed; final values
    are not invented yet.
  - D. **Size system** — OPEN (letter sizes, Iranian/numeric sizes, or
    other business-specific sizing; not chosen).
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

---

## Open decision register

| # | Decision | Status | Blocking | Target phase |
| --- | --- | --- | --- | --- |
| 1 | ~~Final SKU convention~~ — resolved: D-014 **Approved** | Resolved | — | 2 (done) |
| 2 | Truly required product fields | Open | Product validation rules | 2 |
| 3 | Taxonomy value lists (colors, sizes, fabrics, …) | Open | Product data entry | 2 |
| 4 | Data-entry language for product data | Open | Product data entry | 2 |
| 5 | WooCommerce field mapping (conceptual → WooCommerce) | Open | WooCommerce foundation | 3 |
| 6 | WooCommerce hosting / VPS | Open | Store setup | 3–4 |
| 7 | n8n deployment model (cloud vs self-hosted) | Open | n8n foundation | 5 |
| 8 | Secret-management tooling | Open | First credential | 5 |
| 9 | AI provider(s) | Open | AI Runtime | 7 |
| 10 | Iranian payment provider | Open | Payment go-live | 12 |
| 11 | Iranian shipping provider | Open | Shipping go-live | 13 |
| 12 | Instagram API surface / account setup | Open | Instagram integration | 9 |
| 13 | Variant-defining attributes (proposed: color, size — D-016.A) | Open | Variant model finalization | 2 |
| 14 | Variant ID generation mechanism (deferred by D-015) | Open | Variant implementation | 2–3 |
| 15 | Size system (letter vs Iranian/numeric — D-016.D) | Open | Vocabulary registry v1 | 2 |
| 16 | Product status state machine (candidates: draft/active/archived — D-016.E) | Open | Product lifecycle rules | 2 |
| 17 | Publication status values (D-016.F) | Open | Product lifecycle rules | 2 |
| 18 | Price model: default + variant override + sale behavior (D-016.G) | Open | Pricing rules | 2 |
| 19 | Discount model (sale-price direction preferred, not approved — D-016.H) | Open | Pricing rules | 2 |
| 20 | Provenance storage mechanism (states fixed, storage open — D-016.J) | Open | Product data entry | 2 |
| 21 | Import idempotency strategy (D-016.K) | Open | Excel import specification | 2 |
| 22 | Excel import scope: spec only vs spec + template (D-016.L) | Open | Phase 2 scope | 2 |
| 23 | SEO slug language (D-016.M) | Open/deferred | Product URLs | 2 or 3 |

Nothing in this register may be resolved silently (PROJECT_RULES §4).
Only the human owner approves decisions; D-014 and D-015 are approved,
D-016 and every item above remain open.

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
| D-014 | Final SKU convention | **Open** |

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

- **Status:** **Open**
- **Decision:** Not decided. The provisional pattern `P0001-BLK-M`
  (product code + color code + size code) is a placeholder only.
- **Constraints:** SKUs must be unique, deterministic, stable, never
  silently reused; duplicate SKUs are a blocking data-integrity error;
  production changes require human approval. Products without variants
  need no artificial variants.
- **Rationale for openness:** The convention determines long-lived
  identifiers and must be approved explicitly by the human owner.
- **Approval gate:** Must be approved **before inventory automation**
  (MASTER_PLAN §4, PROJECT_RULES §10). Expected resolution: Phase 2.

---

## Open decision register

| # | Decision | Status | Blocking | Target phase |
| --- | --- | --- | --- | --- |
| 1 | Final SKU convention (D-014) | Open | Inventory automation | 2 |
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

Nothing in this register may be resolved silently (PROJECT_RULES §4).

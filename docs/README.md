# docs/

Documentation index for the AI-First Online Business Engine.

Root-level documents (`README.md`, `ARCHITECTURE.md`, `DATA_MODEL.md`,
`SECURITY.md`, `DECISIONS.md`, `TODO.md`, `MASTER_PLAN.md`,
`PROJECT_RULES.md`) are the primary references. This directory holds
supporting material: shared vocabulary and per-phase working documents.

## Contents

| Path | Purpose |
| --- | --- |
| [glossary.md](glossary.md) | Shared vocabulary: entities, provenance states, autonomy tiers, conventions. |
| [phases/](phases/) | Per-phase scope, entry/exit criteria, and Definition-of-Done tracking. |
| [phases/phase-01-project-architecture.md](phases/phase-01-project-architecture.md) | Phase 1 — Project Architecture. |
| [phases/phase-02-product-data-system.md](phases/phase-02-product-data-system.md) | Phase 2 — Product Data System (closed; decision set D-014–D-030). |
| [phases/phase-02-5-business-data-configuration.md](phases/phase-02-5-business-data-configuration.md) | Phase 2.5 — Business Data Configuration (owner-approved store structure, Batches 1–3). |
| [phases/phase-02-5-excel-master-template.md](phases/phase-02-5-excel-master-template.md) | Phase 2.5 — Product Master Excel template: physical workbook contract (D-033). |
| [phases/phase-03-1-woocommerce-foundation.md](phases/phase-03-1-woocommerce-foundation.md) | Phase 3 — WooCommerce Foundation: identity/type/category/attribute/price/lifecycle/media/inventory mapping, API/n8n/security/idempotency contracts (D-034–D-045). |
| [phases/phase-03-2-woocommerce-sync-architecture.md](phases/phase-03-2-woocommerce-sync-architecture.md) | Phase 3 — WooCommerce Sync Architecture: mapping registry, field-level sync + CRUD contracts, price-sync resolution (D-048 Option A, approved), authority matrix, media direction, non-registry attributes, test strategy (D-046–D-052). |
| [phases/phase-03-3-local-development-environment.md](phases/phase-03-3-local-development-environment.md) | Phase 3 — Local Development Environment: local-first architecture (D-053), Docker Compose runtime (D-054), canonical PostgreSQL database (D-055), local media emulator (D-056) — all owner-approved; D-048 price-projection test matrix, Excel test matrix, promotion contract. Batch 4 scaffolding implemented under `local/` (guide: `local/README.md`). |

## Conventions

- Documentation is written in English. Product/customer-facing language is
  Persian / RTL-first; that requirement applies to future storefront work,
  not to project documentation.
- Documents must not contain secrets, credentials, or customer data
  (see `SECURITY.md`).
- Documentation must be updated when architecture, data ownership, API
  behavior, security, deployment, workflow behavior, or important business
  rules change (`PROJECT_RULES.md` §37). Documentation must never become
  silently false.
- Directories are created only when they have real content; no empty
  placeholder directories.

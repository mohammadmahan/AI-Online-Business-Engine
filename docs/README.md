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
| [roadmap/LOCAL_STOREFRONT_E2E_TRACK.md](roadmap/LOCAL_STOREFRONT_E2E_TRACK.md) | **LSE (D-174, 2026-11-12)** — local/offline verification track over the already implemented fashion storefront: repeatable system-Chrome E2E, fail-closed/no-DB checks, responsive/RTL and basic accessibility guards, synthetic checkout and merchant reconciliation. Tasks LSE-01…LSE-06 COMPLETED 2026-11-12; no production, credential or provider authorization. |
| [roadmap/MULTI_CARRIER_SHIPPING_TRACK.md](roadmap/MULTI_CARRIER_SHIPPING_TRACK.md) | **MCS (D-175, 2026-11-12)** — owner-approved local three-carrier registry (Iran Post, Tipax, local courier), configuration-only all/subset/single modes, eligibility/quote, immutable carrier persistence, admin visibility and sandbox adapter contract. Real carrier credentials/API/go-live remain owner-gated. |
| [roadmap/FASHION_ECOMMERCE_ROADMAP.md](roadmap/FASHION_ECOMMERCE_ROADMAP.md) | E-Commerce & Social Publishing track (**D-172**, approved 2026-10-10): the **authoritative execution plan** for the fashion commerce stack — architecture, Phase 1 catalog schema, Phases 1–6, derived API contract set, UI/UX requirements, owner rulings G-1…G-6. **Phases 1–5 IMPLEMENTED & VERIFIED offline** in `commerce/` and `local/`; **Phase 6 build artifacts COMPLETE**; **G0 is ACCEPTED / RESOLVED by direct owner sign-off (D-173, 2026-11-12)**, so **B1–B6 are unblocked for local/offline preparation only**. Production deployment, credentials and live providers remain unauthorized (D-045 / D-139); local-only G-5 MinIO implemented and loopback-verified with its **local** flag closed, production media provider open and unselected; no provisioning, connection, credential or activation. |
| [phases/](phases/) | Per-phase scope, entry/exit criteria, and Definition-of-Done tracking. |
| [deployment/dokploy-plan.md](deployment/dokploy-plan.md) | Work package “Dokploy Deployment Integration” (D-141 **Approved**; Stages A–H **VERIFIED** offline/local): optional/replaceable deployment layer — architecture, environments, release governance, security, backup model, stages A–H, risks, exit strategy, official references. Nothing is deployed or production-activated. |
| [deployment/local-pilot-readiness.md](deployment/local-pilot-readiness.md) | **v1.0 (2026-11-09, commit `5c82312`)** — developer-operated loopback-only synthetic pilot: **GO**; real-customer/live-provider pilot **NO-GO**; production activation **NO-GO**. Evidence, operating procedure, limitations and stop conditions. |
| [runbooks/dokploy-deployment.md](runbooks/dokploy-deployment.md) | PLANNED deployment runbook: preconditions, onboarding, promotion gates, rollback, stop conditions. |
| [runbooks/dokploy-disaster-recovery.md](runbooks/dokploy-disaster-recovery.md) | PLANNED DR runbook: backup architecture, server-loss/corruption/migration/credential scenarios, restoration-evidence requirements. |
| [runbooks/dokploy-exit-plan.md](runbooks/dokploy-exit-plan.md) | PLANNED exit runbook (Stage H): configuration provenance map, exit drill, verification requirements. |
| [phases/phase-01-project-architecture.md](phases/phase-01-project-architecture.md) | Phase 1 — Project Architecture. |
| [phases/phase-02-product-data-system.md](phases/phase-02-product-data-system.md) | Phase 2 — Product Data System (closed; decision set D-014–D-030). |
| [phases/phase-02-5-business-data-configuration.md](phases/phase-02-5-business-data-configuration.md) | Phase 2.5 — Business Data Configuration (owner-approved store structure, Batches 1–3). |
| [phases/phase-02-5-excel-master-template.md](phases/phase-02-5-excel-master-template.md) | Phase 2.5 — Product Master Excel template: physical workbook contract (D-033). |
| [phases/phase-03-1-woocommerce-foundation.md](phases/phase-03-1-woocommerce-foundation.md) | Phase 3 — WooCommerce Foundation: identity/type/category/attribute/price/lifecycle/media/inventory mapping, API/n8n/security/idempotency contracts (D-034–D-045). |
| [phases/phase-03-2-woocommerce-sync-architecture.md](phases/phase-03-2-woocommerce-sync-architecture.md) | Phase 3 — WooCommerce Sync Architecture: mapping registry, field-level sync + CRUD contracts, price-sync resolution (D-048 Option A, approved), authority matrix, media direction, non-registry attributes, test strategy (D-046–D-052). |
| [phases/phase-03-3-local-development-environment.md](phases/phase-03-3-local-development-environment.md) | Phase 3 — Local Development Environment: local-first architecture (D-053), Docker Compose runtime (D-054), canonical PostgreSQL database (D-055), local media emulator (D-056) — all owner-approved; D-048 price-projection test matrix, Excel test matrix, promotion contract. Batch 4 scaffolding implemented under `local/` (guide: `local/README.md`). |
| [phases/phase-06-notion-business-os.md](phases/phase-06-notion-business-os.md) | Phase 6 — Notion Business OS (closed at foundation level; D-060 Approved — Option A, D-061): lifecycle machine, revision-marker idempotency, D-027 ingestion, provider-neutral adapter/poller, conformance matrix A–H; live Notion connectivity owner-gated/deferred. |
| [phases/phase-07-ai-runtime.md](phases/phase-07-ai-runtime.md) | Phase 7 — AI Runtime (M1): provider-neutral model router, strict JSON-Schema output contracts, cost/budget guardrails, D-050 proposal pipeline; D-062–D-064 Proposed; mock providers only, credentials owner-gated. |

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

## Generated graph

`graphify-out/` is a **gitignored generated artifact**, not a source of truth.
The generator is `graphify` (documented in
`docs/standards/graph-hygiene-and-exclusions.md`) and is refreshed with
`graphify update .`. The report’s “Graph Freshness” header names the commit it
was built from; compare that value with `git rev-parse HEAD`. A subsequent
documentation-only commit can legitimately make the graph one commit behind.

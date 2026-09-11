# TODO

Living task list for the AI-First Online Business Engine.

- Conventions: `[ ]` open, `[x]` done. Completed items stay until the
  phase closes.
- Required reading before work: `MASTER_PLAN.md`, `PROJECT_RULES.md`,
  relevant docs, then this file (`PROJECT_RULES.md` §2).

---

## Phase 1 — Project Architecture (closed)

Status: **Complete** (foundation committed in `e6d85ca`); scope in
`docs/phases/phase-01-project-architecture.md`

- [x] Validate planning documents (`MASTER_PLAN.md`, `PROJECT_RULES.md`)
- [x] Create `README.md`
- [x] Create `ARCHITECTURE.md`
- [x] Create `DATA_MODEL.md`
- [x] Create `SECURITY.md`
- [x] Create `DECISIONS.md`
- [x] Create `TODO.md`
- [x] Create `docs/` structure (`docs/README.md`, `docs/glossary.md`,
      `docs/phases/phase-01-project-architecture.md`)
- [x] SKU strategy review → recorded as **D-014 (Approved)** in
      `DECISIONS.md`; final convention approved by the human owner
      (see D-014 / D-015)
- [x] Self-review pass: valid Markdown, no secrets, cross-references
      valid, Definition of Done checked per file
- [x] Commit the foundation (explicit human approval; commit `e6d85ca`)

## Phase 2 — Product Data System (current)

Scope from MASTER_PLAN §13: product/variant model, SKU, taxonomy,
media, validation, import/export, Excel import preparation. Decisions
D-014 (SKU convention) and D-015 (identifier separation) are
**Approved**; the remaining Phase 2 decisions are open (D-016,
`DECISIONS.md` register items 13–23).

Ordered tasks (none completed yet — do not treat as done until
verified):

- [x] ~~SKU strategy~~ — resolved: D-014 **Approved** (2026-09-11)
- [ ] 1. Finalize Product/Variant identifier policy (D-015 recorded;
       variant ID generation mechanism open)
- [ ] 2. Finalize variant-defining attributes (proposed: color, size —
       D-016.A)
- [ ] 3. Finalize minimum required product fields (D-016.B)
- [ ] 4. Design controlled-vocabulary registry v1 (D-016.C)
- [ ] 5. Resolve size system (D-016.D)
- [ ] 6. Define product/publication status state machines (D-016.E/F)
- [ ] 7. Define price/discount model (D-016.G/H)
- [ ] 8. Define provenance mechanism (D-016.J)
- [ ] 9. Define import idempotency policy (D-016.K)
- [ ] 10. Decide Excel import scope (D-016.L)
- [ ] 11. Consolidate the logical data model
- [ ] 12. Produce Excel import specification/template if approved
- [ ] 13. Perform Phase 2 final review
- [ ] 14. Commit Phase 2 foundation only after human approval

Standing constraints (always apply):

- No API keys or credentials in the repository, ever.
- No production infrastructure.
- SKU convention is approved (D-014); SKU issuance remains human/approved
  tooling only — AI never assigns or invents a SKU.
- No major architectural decisions outside `DECISIONS.md` (STOP →
  EXPLAIN → APPROVAL).

## Blocked / do-not-start

Forbidden until their phase begins (MASTER_PLAN §16). Do not start
these even if they seem helpful:

- [ ] Phase 3 — WooCommerce foundation (no WordPress/WooCommerce work,
      no field mapping, no configuration)
- [ ] Phase 4 — Infrastructure (no hosting, DNS, backups setup)
- [ ] Phase 5 — n8n foundation (no workflows, no credentials)
- [ ] Phase 6 — Notion Business OS (no Notion workspace automation)
- [ ] Phase 7+ — AI Runtime, Instagram, payment, shipping integrations

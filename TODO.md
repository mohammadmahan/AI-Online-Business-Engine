# TODO

Living task list for the AI-First Online Business Engine.

- Conventions: `[ ]` open, `[x]` done. Completed items stay until the
  phase closes.
- Required reading before work: `MASTER_PLAN.md`, `PROJECT_RULES.md`,
  relevant docs, then this file (`PROJECT_RULES.md` §2).

---

## Phase 1 — Project Architecture (current)

Status: **In progress** — scope in
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
- [ ] SKU strategy review → recorded as **D-014 (Open)** in
      `DECISIONS.md`; final approval is a Phase 2 gate
- [ ] Self-review pass: valid Markdown, no secrets, cross-references
      valid, Definition of Done checked per file
- [ ] Commit the foundation (**requires explicit human approval**)

## Blocked / do-not-start

Forbidden until their phase begins and the foundation is approved
(MASTER_PLAN §16). Do not start these even if they seem helpful:

- [ ] Phase 2 — Product Data System (blocked on Phase 1 exit criteria)
- [ ] Phase 3 — WooCommerce foundation (no WordPress/WooCommerce work)
- [ ] Phase 4 — Infrastructure (no hosting, DNS, backups setup)
- [ ] Phase 5 — n8n foundation (no workflows, no credentials)
- [ ] Phase 6 — Notion Business OS (no Notion workspace automation)
- [ ] Phase 7+ — AI Runtime, Instagram, payment, shipping integrations

Standing constraints (always apply):

- No API keys or credentials in the repository, ever.
- No production infrastructure.
- No finalized SKU convention without explicit approval (D-014).
- No major architectural decisions outside `DECISIONS.md` (STOP →
  EXPLAIN → APPROVAL).

## Phase 2 — Product Data System (preview, not started)

Scope from MASTER_PLAN §13 Phase 2: product/variant model concretization,
SKU strategy approval (resolves D-014), taxonomy value lists, media,
validation, import/export, Excel import preparation. Open decisions to
resolve: SKU convention, truly required product fields, taxonomy lists,
data-entry language (`DECISIONS.md` register items 1–4).

Entry condition: Phase 1 exit criteria met and foundation approved.

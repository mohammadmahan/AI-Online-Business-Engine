# Phase 1 — Project Architecture

Status: **In progress**

---

## Scope

Create and validate the project's architectural documentation and
development foundation. Documentation only — no systems are built,
connected, or configured in this phase.

Entry condition (from MASTER_PLAN §13, Phase 0):

- Business definition, technology choices, and planning documents exist.
- Git repository exists.

All content is derived from the approved `MASTER_PLAN.md` and
`PROJECT_RULES.md`. No new architectural decisions are introduced; open
items are recorded explicitly as open.

## Deliverables

- [x] `README.md` — repository entry point and documentation index
- [x] `ARCHITECTURE.md` — target architecture, system roles, source-of-truth matrix
- [x] `DATA_MODEL.md` — conceptual data model and integrity rules
- [x] `SECURITY.md` — security baseline and safety rules
- [x] `DECISIONS.md` — decision log (approved decisions + open decisions)
- [x] `TODO.md` — living task list
- [x] `docs/` — supporting documentation structure (this directory)

## Explicit exclusions (forbidden in this phase)

- No WooCommerce build or WordPress installation
- No n8n workflows
- No Instagram, payment, or shipping connections
- No production infrastructure
- No API keys or credentials anywhere
- No finalized SKU convention (recorded as open)
- No application code
- No changes to `MASTER_PLAN.md` or `PROJECT_RULES.md`

## Exit criteria

- [ ] All deliverables exist, are valid Markdown, and contain no secrets
- [ ] Every approved decision is documented in `DECISIONS.md` with its source
- [ ] Every unresolved decision is explicitly recorded as open
- [ ] Cross-references between documents are valid
- [ ] Definition of Done (PROJECT_RULES §38) satisfied for each file
- [ ] Foundation committed to Git (with explicit human approval for the commit)

## Next phase entry condition

Phase 2 — Product Data System (product/variant model, SKU strategy
approval, taxonomy, media, validation, import/export, Excel import
preparation) may start only after Phase 1 exit criteria are met and the
foundation is approved.

## References

- `MASTER_PLAN.md` §12 (Project Documentation), §13 (Project Phases),
  §14 (Definition of Done), §16 (Current Status)
- `PROJECT_RULES.md` §2 (Read Before Work), §38 (Definition of Done)

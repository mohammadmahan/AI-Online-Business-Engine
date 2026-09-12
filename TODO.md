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
D-014 (SKU convention), D-015 (identifier separation), D-017
(identifier policy), D-018 (variant-defining attributes), D-019
(vocabulary governance), D-020 (size-system architecture), D-021
(required-field policy), D-022 (product status state machine),
D-023 (publication status state machine), D-024 (price model), D-025
(discount model), D-026 (provenance mechanism), D-027 (event-level
idempotency), D-028 (Excel import contract), D-029 (registry v1
structure), and D-030 (size-code governance) are **Approved**; the
remaining Phase 2 open items include registry v1 concrete values
(D-016.C), concrete size-code mappings (D-020/D-030), and SEO slug
language (D-016.M).

Ordered tasks (tasks 1–10 resolved via D-017–D-021, D-022/D-023,
D-024–D-027, and D-028–D-030 — do not treat
other items as done until verified):

- [x] ~~SKU strategy~~ — resolved: D-014 **Approved** (2026-09-11)
- [x] 1. Finalize Product/Variant identifier policy — **D-017
       Approved** (2026-09-11): Product ID = product code (`P00001`…),
       Variant ID = opaque UUIDv4, AI never issues identifiers;
       event-level idempotency still open (D-016.K)
- [x] 2. Finalize variant-defining attributes — **D-018 Approved**
       (2026-09-11): exactly {Color, Size}, per-axis applicability,
       SKU suffix = active axes (Color, then Size)
- [x] 3. Finalize minimum required product fields — **D-021 Approved**
       (2026-09-11): minimal creation minimums, publication minimum,
       verified-data-only inventory, bounded AI enrichment
- [x] 4. Design controlled-vocabulary registry v1 — governance
       **D-019 Approved**; v1 structure **D-029 Approved** (required:
       color, size, category); concrete registry v1 values remain OPEN
       and owner-supplied
- [x] 5. Resolve size system — architecture **D-020 Approved**
       (multi-family); size-code governance **D-030 Approved**
       (O/I/L-safe); concrete size-code mappings remain an explicit
       OPEN owner sub-decision
- [x] 6. Define product/publication status state machines —
       **D-022 / D-023 Approved** (2026-09-12): product lifecycle
       `draft`/`active`/`archived`; publication `unpublished`/
       `in_review`/`published`/`withdrawn`; publication transitions are
       Red-tier (human approval); AI may suggest, never execute
- [x] 7. Define price/discount model — **D-024 / D-025 Approved**
       (2026-09-12): three-field minimal price model (list price,
       variant override, optional sale price with explicit validity);
       sale-price-only discounts, no discount engine; AI suggests
       only, Red tier applies to production changes
- [x] 8. Define provenance mechanism — **D-026 Approved**
       (2026-09-12): per-value provenance tuple (source, actor,
       timestamp, review state, optional source ref + raw value),
       immutable/append-only; five source types; provenance ≠ audit log
- [x] 9. Define import idempotency policy — **D-027 Approved**
       (2026-09-12): event-level idempotency via (source system, event
       ID) unique key with terminal processing states; safe retries;
       distinct from identifier-based idempotency (D-017)
- [x] 10. Decide Excel import scope — **D-028 Approved**
       (2026-09-12): input-only contract over semantic fields (the
       physical sheet/column mapping is confirmed at the specification
       task); dry-run first; human-approved exceptions; Excel never
       issues IDs/SKUs and never writes inventory
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

# Phase 2 — Product Data System

Status: **In progress**

---

## Purpose

Design and specify the Product Data System: the product/variant model,
identifiers, taxonomy, media, validation, import/export, and Excel
import preparation — per MASTER_PLAN §13 (Phase 2). Documentation and
decision-recording only in this phase; no implementation, no schemas,
no code.

Entry condition (Phase 1 exit):

- Architecture foundation created and approved (commit `e6d85ca`).
- D-014 Final SKU convention resolved: **Approved** (2026-09-11).

## Scope

- Finalize the logical product/variant model on top of
  `DATA_MODEL.md`.
- Record and apply decisions D-014 (SKU convention), D-015
  (identifier separation), and D-017 (identifier policy); resolve the
  remaining D-016 open items.
- Controlled-vocabulary registry v1 (colors, sizes, categories, other
  controlled fields as needed).
- Product/publication status state machines (candidates only).
- Price/discount model definition (no implementation).
- Provenance mechanism definition (states fixed; storage deferred).
- Import idempotency policy; Excel import specification (and template
  only if approved — D-016.L).
- Phase 2 final review, then commit only after human approval.

## D-014 — Final SKU convention (APPROVED)

1. SKU convention: product code + canonical attribute suffix.
2. Product code: five-digit numeric sequence from the beginning —
   `P00001`, `P00002`, `P00003`, …; the four-digit `P0001` provisional
   form is not the final standard.
3. Variant SKU: product code + canonical attribute suffix,
   e.g. `P00001-BLK-M`.
4. Simple product without variants: SKU = product code, e.g. `P00002`.
5. Character set: uppercase Latin ASCII only.
6. Attribute suffix codes come only from controlled vocabularies;
   humans and AI must not invent arbitrary attribute codes.
7. Attribute-code registries avoid visually confusable letters such as
   O, I, L; product numbering remains numeric.
8. Structured attributes remain authoritative; the SKU suffix is only
   a compact human/warehouse readability aid.
9. Category and brand are NEVER encoded into the SKU.
10. SKU is frozen at creation. Incorrect SKU: do NOT rename;
    deactivate the incorrect product/variant and create a new correct
    product/variant with a new identifier/SKU.
11. Duplicate color + size combinations under one product are data
    errors and must be rejected; a `-2` suffix exists only as an
    emergency safety valve, never as normal variant numbering.
12. Product codes are assigned by humans or approved deterministic
    tooling; AI must NEVER autonomously assign or invent a SKU.
13. SKU and barcode/EAN are separate concepts; the SKU must not be
    used as the barcode.
14. SKU remains stable and is never silently reused.
15. Five-digit numbering is the initial standard; business logic must
    not depend on digit count — identifiers are opaque and must not be
    parsed for meaning.

## Product ID / Variant ID / SKU separation (D-015, D-017 — APPROVED)

- **Product ID** — stable business-facing product identifier,
  human-readable (`P00001`), stable, category-agnostic, not derived
  from the product name. It is the canonical name for the D-014
  product code; issued only by humans or approved deterministic
  tooling; immutable; never reused.
- **Variant ID** — separate stable internal identifier for a variant;
  must NOT be the SKU; opaque and system-safe: **UUIDv4**, canonical
  lowercase hyphenated form; issued only by approved deterministic
  tooling at variant creation; immutable; never reused.
- **SKU** — business/inventory identifier; human-readable; used for
  WooCommerce/inventory/Excel/n8n references; immutable after creation.
- The SKU is NOT the internal database identity of a variant; SKU
  parsing is never the source of attribute truth.
- AI must never issue, assign, invent, or transform Product IDs,
  Variant IDs, or SKUs. Identifier-based import idempotency is
  approved (D-017); event-level idempotency remains open (D-016.K).

## Remaining open decisions

All remaining Phase 2 decisions are **OPEN** (D-016 and `DECISIONS.md`
register items 13–23); none may be resolved silently:

- Variant-defining attributes (proposed: color, size) — D-016.A
- Minimum required product fields — D-016.B
- Controlled vocabularies / registry v1 — D-016.C
- Size system (letter vs Iranian/numeric vs business-specific) — D-016.D
- Product status state machine (candidates: draft / active /
  archived; no WooCommerce mapping) — D-016.E
- Publication status values — D-016.F
- Price model (default + variant override + sale behavior) — D-016.G
- Discount model (sale-price direction preferred, NOT approved) — D-016.H
- Inventory design constraints (already-approved rules remain: WooCommerce
  SoT, verified, idempotent, auditable, AI never estimates) — D-016.I
- Provenance mechanism (states fixed; storage deferred) — D-016.J
- Import idempotency strategy — D-016.K
- Excel import scope (spec only vs spec + template) — D-016.L
- SEO slug language — D-016.M

## Implementation sequence

1. Finalize Product/Variant identifier policy — resolved: D-017
   **Approved** (Product ID = product code; Variant ID = UUIDv4; AI
   never issues identifiers).
2. Finalize variant-defining attributes.
3. Finalize minimum required product fields.
4. Design controlled-vocabulary registry v1.
5. Resolve size system.
6. Define product/publication status state machines.
7. Define price/discount model.
8. Define provenance mechanism.
9. Define import idempotency policy.
10. Decide Excel import scope.
11. Consolidate the logical data model.
12. Produce Excel import specification/template if approved.
13. Perform Phase 2 final review.
14. Commit Phase 2 foundation only after human approval.

## Exit criteria

- [ ] All remaining D-016 items resolved or explicitly deferred with
      owner approval
- [ ] Logical data model consolidated in `DATA_MODEL.md`
- [ ] Controlled-vocabulary registry v1 defined (if approved in scope)
- [ ] Excel import specification complete (scope per D-016.L)
- [ ] Cross-references valid; no secrets; no contradictions
- [ ] Phase 2 final review passed
- [ ] Foundation committed (with explicit human approval)

## Explicit Phase 3 boundary

The following are out of scope for Phase 2 and are NOT started:

- No WooCommerce field mapping
- No WooCommerce configuration
- No n8n workflows
- No payment integration
- No shipping integration
- No production database implementation
- No production credentials

## References

- `MASTER_PLAN.md` §13 (Project Phases — Phase 2), §16 (Current Status)
- `PROJECT_RULES.md` §8–§13 (product, variant, SKU, price, inventory,
  WooCommerce rules)
- `DECISIONS.md` — D-014 (Approved), D-015 (Approved), D-017
  (Approved), D-016 (Open)
- `DATA_MODEL.md` — §9 (SKU), §9.2 (Identifiers)

# Phase 3.2 — WooCommerce Sync Architecture (Batch 2 design)

Status: **Batch 2 — design recorded (2026-09-12); D-046/D-048/
D-049/D-050/D-051/D-052 Approved (D-048 Option A owner-approved
2026-09-13); D-047 Approved (Deferred to Batch 3+)**

---

## Purpose

Turn the Batch 1 foundation contract (D-034–D-045,
`docs/phases/phase-03-1-woocommerce-foundation.md`) into the complete
operational sync architecture: the D-038 price-divergence resolution,
the mapping registry, the field-level sync contract, the CRUD
contract, idempotency/conflict/divergence handling, the Green/Yellow/
Red authority matrix, the media-storage and non-registry-attribute
architectures, the test/sandbox strategy, and the credential
structure.

This batch remains **design/specification only**: no production code,
no WooCommerce connection, no credentials, no webhooks, no workflows,
no databases, no infrastructure, no commit, no push.

## 1. D-038 price-sync architecture — resolution (D-048)

### 1.1 The problem

Our canonical effective-price precedence (D-024 rule 4) is:

```text
valid variant sale → valid product sale → variant override → list price
```

WooCommerce's native model cannot express this precedence in one
place: a variation sells at its own `sale_price` else its own
`regular_price`; a parent-level sale does not reliably cascade onto
variations that carry their own prices; there is no notion of
"override + inherited sale". The divergence case — **product-level
sale active + variant override set + no variant-level sale** — would
display the override price while canonical D-024 resolution sells the
overridden base at the product-level sale. A silent display
divergence on price is unacceptable (price = Red tier, RULES §32).

### 1.2 Candidate options (from D-038; unchanged set)

| Option | Mechanism | Advantages | Disadvantages |
| --- | --- | --- | --- |
| **A) Canonical-layer projection** ("materialize at sync") | Approved deterministic tooling computes the D-024/D-025 effective resolution and writes it into the Woo fields Woo actually displays (variation `sale_price`/`regular_price`), at every affected change; base/list fields are never mutated | Exact canonical display everywhere; deterministic; uses Woo primitives only; no plugin; works with scheduled-sale expiry via re-sync | Woo's own price fields become *projections*, not independent truths; requires disciplined sync (and expiry re-projection when a sale validity end passes) |
| **B) Config constraint** | Product-level sales allowed only on products without variant price overrides | Zero projection complexity | Business restriction the owner has not approved; rejects a legitimate pricing pattern; pushes complexity onto the seller's data entry |
| **C) Accept Woo-native display** | Let Woo display what it displays; surface divergences for human review | No sync machinery for this case | Price display can contradict canonical resolution — a hidden failure (RULES §24/§41) on a Red-tier value; constant noise for humans |

### 1.3 Recommendation — Option A (canonical-layer projection)

**Why A is the technical consequence of already-approved architecture,
not a new business decision:** D-003 makes Woo the transactional SoT
*for the data it owns transactionally* — but D-024/D-025 already fix
the canonical price resolution *ours*, and D-042 already fixes the
direction (PM → Woo projection, never Woo → PM for PM-owned fields).
A projection that renders the canonical resolution into Woo's display
fields is the only option consistent with both: B invents a new
business restriction (owner-gated), and C knowingly displays a price
that contradicts the approved precedence. Option A changes no price
value, no precedence rule, and no approval rule — it only chooses
*where* the approved resolution is rendered. It is therefore recorded
as **Approved** (owner confirmation of this architectural reading,
2026-09-13); no business rule is altered by it.

### 1.4 Exact consequences of Option A

1. Woo price fields for PM-owned products become **projections**;
   they are never treated as canonical truth and are never hand-edited
   as such ( Woo-side manual price edits = divergence, §7).
2. The base/list and override fields in our layer remain the only
   canonical price inputs; the projection never mutates them.
3. Sale-expiry handling: when a sale validity end passes, the
   canonical resolution changes deterministically; a scheduled
   re-projection (deterministic tooling) refreshes the Woo fields.
   Until the re-projection runs, Woo may display the expired price —
   the dry-run/reconciliation flow surfaces this as a bounded,
   logged window; no silent state change occurs.
4. Every price-affecting write remains **Red tier**: computed by
   approved tooling from canonical data, executed only within the
   human-promoted sync flow; AI never executes it.
5. Pre-write validation (D-038) is unchanged and runs against the
   canonical resolution before any projection.
6. Implementation-time verification: exact Woo sale-date field
   semantics per version (already noted in D-038/D-043).

### 1.5 Owner approval

D-048 — "Option A: canonical-layer projection (materialize at sync)"
— was **owner-approved 2026-09-13**, closing the D-038 sub-gate.
Alternatives B and C were not chosen; D-024/D-025 are untouched.

## 2. Mapping registry — complete conceptual design (D-046)

The registry (D-034) is the authoritative linkage between canonical
identifiers/terms and their Woo counterparts. Conceptual design; the
physical store (table/document) is implementation-deferred.

### 2.1 Entry types and direction of authority

| Entry | Canonical (authoritative) side | Woo (mapped) side | Notes |
| --- | --- | --- | --- |
| Product | Product ID (`P00001`) | Woo product ID | SKU is *not* the key; see 2.2 |
| Variation | Variant ID (UUIDv4) | Woo variation ID | SKU rides on the variation record, not as identity |
| Category | canonical category term (primary + leaf pair) | Woo category ID | one entry per Batch 1 term |
| Color term | canonical color term / D-032 code | Woo `pa_color` term ID (+ slug) | |
| Size term | canonical (family, size term) pair / D-032 code | Woo `pa_size-{family}` term ID (+ slug) | family-scoped key |
| Media reference | canonical reference (URL/ref) | Woo attachment ID | created per D-049 flow |

**Authoritative side:** always the canonical layer. Woo IDs are
technical facts written back into the registry after creation — they
never redefine identity, and a registry entry is never *derived* by
fuzzy name matching.

### 2.2 Uniqueness and keys

- One active entry per canonical key: Product ID; Variant ID;
  (primary, leaf) category pair; color term; (family, size) pair;
  media reference (+ product).
- Uniqueness is bidirectional: a Woo ID may appear in **at most one
  active entry per entry type** — two canonical records pointing at
  one Woo record is a `MAPPING_CONFLICT` (§6).
- The SKU is stored on entries as **data, not identity**: SKU →
  Variant ID is a derived, validated association (the SKU is unique
  in our layer by RULES §10), never the lookup key and never the
  internal identity (D-015/D-017 unchanged).

### 2.3 Field classes

| Field class | Examples | Mutability |
| --- | --- | --- |
| Immutable | canonical key (Product ID, Variant ID, term identity); creation timestamp | never changed; corrections = deactivate + recreate (mirrors D-014 rule 10/D-030 rule 5) |
| Write-once on creation | Woo ID, Woo slug at creation time | set once; changed only through the stale-mapping recovery flow (2.7) |
| Mutable metadata | last-verified timestamp, status (active/stale/orphaned), notes | maintained by tooling |

### 2.4 Creation rules

1. Only approved deterministic tooling creates entries, inside a
   human-promoted sync flow.
2. Creation follows the approved seed flows: categories/terms are
   pre-seeded from the owner-approved registries (D-031/D-032) via
   create-if-absent by exact key; products/variations create Woo
   records only when no active entry exists (deterministic lookup as
   second guard), then write the returned Woo ID back.
3. Every creation is a D-027 event; every entry carries D-026
   provenance (actor = approved tooling on behalf of the promoting
   human; source reference = the sync event).

### 2.5 Update rules

- Woo IDs are never updated in place. If a Woo record must be
  replaced (never by us deleting it — §4.7), the old entry is
  marked `stale`/`orphaned` and a **new** entry is created for the
  new Woo ID after human review.
- Mutable metadata (status, last-verified) is updated by tooling,
  logged.

### 2.6 Lookup rules

- Lookup is **exact key → single active entry**. No fuzzy matching,
  no name-based search, no confidence scoring (D-019 rule 5 carries
  over).
- Before any create, tooling runs the deterministic second guard:
  read Woo by our stored external reference (SKU on products/
  variations; exact slug on terms; exact parent+child on categories).
  A hit without a registry entry is a duplicate-resource conflict —
  human review, never silent adoption.

### 2.7 Missing, stale, conflicting, orphaned mappings

| State | Meaning | Detection | Handling |
| --- | --- | --- | --- |
| **Missing** | canonical record exists, no active registry entry | lookup miss | normal pre-create path (create Woo record + entry) inside a promoted flow; creation never happens outside one |
| **Stale** | entry exists, but read-back shows the Woo record missing/irrecoverably changed | post-write/read-back verification | entry marked stale (never deleted); re-linking to a new Woo record requires human review, then a new entry |
| **Conflicting** | two active entries (or a registry entry and a deterministic lookup) point at the same canonical key or the same Woo ID | uniqueness check at write time; read-back comparison | integrity error → human review; nothing silently re-linked or merged |
| **Orphaned** | Woo record exists whose registry entry's canonical record was deactivated/archived or corrected | read-back reconciliation | no Woo deletion by default (D-039: hide/preserve); orphan flagged for human decision (hide, keep, or — explicitly approved — destructive cleanup) |

### 2.8 Human-review conditions

Any of: conflicting state; stale/orphaned re-link; duplicate-resource
hit on the second guard; attempted identifier change; registry
repair after a lost linkage (D-034). AI may summarize/analyze — never
resolve (D-034, §8 of the foundation doc).

### 2.9 Provenance & idempotency relationship

- Every entry carries D-026 provenance (source type
  `SYSTEM_GENERATED` for tooling writes; actor = the promoting human
  recorded with the event); append-only corrections.
- The registry is the **identifier-level** half of the operational
  idempotency model (D-017): "is there already a Woo record for this
  canonical key?" — while D-027 answers "should this event run
  again?". The two remain distinct mechanisms (D-044).

## 3. Field-level sync contract (D-047)

Per-field rules. Direction `PM → Woo` = canonical projection; no
default bidirectional sync anywhere (D-042). "Woo manual edit
allowed?" = whether a Woo-side change is an accepted workflow — if
no, it is a divergence (§7).

| Field group | Canonical owner | Woo projection | Direction | Write actor | Woo manual edit allowed? | Divergence behavior | UNKNOWN / NOT_PROVIDED | AI propose? | Tooling execute? | Approval |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Product ID / Variant ID / SKU | PM | reference field / `sku` | PM → Woo (+ Woo IDs back to registry) | approved tooling | no (SKU immutable, D-014) | integrity conflict → human review | n/a | no | yes (post-promotion) | promotion of the sync run; identifier writes never AI |
| Name | PM | `name` | PM → Woo | approved tooling | no | divergence → review queue | UNKNOWN/NOT_PROVIDED → surface; name is a D-021 publication minimum, so `published` cannot be projected without it | yes (Yellow) | yes | run promotion |
| English name | PM | custom/meta field | PM → Woo | approved tooling | no | divergence → review queue | `نامشخص` → UNKNOWN preserved, surfaced | yes (Yellow) | yes | run promotion |
| Description / short description | PM | `description` / `short_description` | PM → Woo | approved tooling | tolerated but non-authoritative; not read back as truth | divergence → review queue; canonical value never overwritten by Woo content | empty = NOT_PROVIDED (valid; not a publication blocker, D-021) | **yes — AI may draft (Yellow, `AI_GENERATED` provenance; human review before exposure)** | yes (post-promotion) | run promotion |
| Primary + leaf category | PM | product categories (two-level, D-036) | PM → Woo | approved tooling | no | category conflict → review queue | NOT_PROVIDED → category missing blocks `published` projection (D-021) | may suggest category (Yellow) | yes | run promotion |
| Color | PM (registry term) | `pa_color` term on variation | PM → Woo | approved tooling | no | attribute-term conflict → review | unknown color impossible in canonical layer (D-019 queue); never fuzzy-matched | may suggest (Yellow) | yes | run promotion |
| Size + family | PM (registry, family-scoped) | `pa_size-{family}` term | PM → Woo | approved tooling | no | attribute-term conflict → review | same as Color | may suggest (Yellow) | yes | run promotion |
| List price | PM | product `regular_price` | PM → Woo | approved tooling | **no — Red tier** | price divergence → review queue; never silent | missing = unresolved price; blocks `published` projection (D-021) | may recommend only (Yellow; never creates/changes) | yes (post-approval) | **Red tier** — human-promoted price-affecting flow |
| Variant override | PM | variation `regular_price` | PM → Woo | approved tooling | no | as above | absent = inherit list price (D-024) | recommend only | yes | Red tier |
| Sale prices (+ validity end) | PM | `sale_price` + sale-end fields; **projection per D-048 Option A** | PM → Woo | approved tooling | no | price divergence → review | absent = no sale; expired = deterministically re-projected (§1.4.3) | suggest only (D-025) | yes | Red tier |
| Lifecycle (D-022) | PM | Woo record existence/projection (D-039) | PM → Woo | approved tooling | no | lifecycle divergence → review | n/a | may suggest/prepare only; **never executes** | yes, per D-022 authority rules | per D-022 (archived moves human-only) |
| Publication (D-023) | PM | status/visibility projection (D-039) | PM → Woo | approved tooling | no | publication divergence → review; **never silently overwritten** | n/a | may prepare submissions; never publishes | yes, only after Red-tier approval | **Red tier** |
| Media references | PM | featured + gallery, in order (D-040) | PM → Woo | approved tooling | tolerated; order/primary from canonical | media divergence → review; canonical order never adopted from Woo | no reference = blocks `published` projection (≥1, D-021) | may suggest alt text (Yellow) | yes | run promotion |
| Alt text | PM (Media) | image alt | PM → Woo | approved tooling | tolerated, non-authoritative | divergence → review | absent → deterministic default = product name (D-040) | yes (Yellow, provenance-tagged) | yes | run promotion |
| Inventory / stock | **Woo (future transactional SoT)** | stock fields | Woo-owned; **PM never writes** | future inventory flows only | yes — Woo is authoritative | inventory divergence: PM does not police Woo stock; only future verified read flows (D-041, D-016.I open) | no stock field exists in the Excel contract | **never estimates** | future flows only | future phase (D-041) |
| SEO title / description | PM | Woo SEO fields (via SEO plugin/meta — representation deferred) | PM → Woo | approved tooling | tolerated, non-authoritative | divergence → review | NOT_PROVIDED = empty; never invented | **yes — AI may draft (Yellow)** | yes | run promotion |
| SEO slug | PM (language **OPEN**, D-016.M) | none projected until the gate closes | — | — | — | — | field stays empty/deferred; no normalization rules invented | may draft suggestions | no (gate open) | owner gate (open) |
| Non-registry attributes (Brand, Material, …) | PM | per D-051: product **meta** (custom attributes only for variation-required axes — none today beyond Color/Size) | PM → Woo | approved tooling | tolerated, non-authoritative | divergence → review | NOT_PROVIDED = field omitted; never invented | may suggest values (Yellow) | yes | run promotion |

Blanket rules: no field is bidirectionally synced by default; Woo-side
edits of PM-owned fields never become canonical truth (D-042 rule 4);
every write is a D-027 event with D-026 provenance; AI may propose/
draft/suggest only, never execute.

## 4. Product / variation CRUD contract (D-047)

Conceptual operations (no implementation). For every operation:

**Common pipeline:** preconditions → canonical validation (D-021/
D-024/D-025 rules) → registry lookup (D-046) → D-027 event opened →
payload built from canonical data → write → post-write verification
(read-back: Woo ID, key fields, status) → registry update → event
closed. Canonical data is the *input*; the Woo projection is the
*output*; nothing reads Woo back as business truth except Woo IDs.

### 4.1 Create Product
- **Preconditions:** canonical product exists in `active` (D-039: no
  Woo record exists in `draft`); publication projection target state
  is hidden; D-021 publication checks evaluated if `published` is
  ever targeted (they gate only the later projection, not creation).
- **Idempotency:** registry miss + deterministic second guard (§2.6);
  one D-027 event; retry-safe (same event ID → same single create).
- **Payload:** identity references, name, category, attributes,
  projected prices, descriptions, media; validated pre-write.
- **Failure:** validation → correct canonical data (human); Woo
  error → D-044 classes; partial ambiguity (timeout after write?) →
  read-back reconciliation **before** any re-create (never blind
  re-create).
- **Rollback/compensation:** a wrong product record is hidden and
  flagged (never deleted by default); compensation = set hidden +
  registry entry marked stale after review.

### 4.2 Update Product
- **Preconditions:** active registry entry; changed canonical fields
  computed by diff (canonical vs last projected snapshot).
- **Idempotency:** update keyed by (canonical Product ID, event ID);
  identical repeat = skip (D-027).
- **Failure/verification:** as common pipeline; read-back verifies
  each projected field; mismatch → divergence class (§6).

### 4.3 Read Product
- **Purpose:** verification and reconciliation only — never a source
  of canonical truth (D-042). Green tier.

### 4.4 Create Variation(s)
- **Preconditions:** parent product record exists and is registered;
  variant satisfies the D-021 variant creation minimum; no duplicate
  active-axis combination (D-014 rule 11); variation-defining
  attributes exactly the product's active axes (D-035).
- **Idempotency:** per-variant registry keying (Variant ID); batch
  creates are individually keyed so partial batch outcomes are
  reconcilable.
- **Failure:** per-variant errors reported honestly (RULES §41);
  ambiguous outcomes reconciled by read-back.

### 4.5 Update Variation
- Same as 4.2 with per-variant keys; price fields projected per the
  D-048 resolution (Red tier when price-affecting).

### 4.6 Read Variation
- Verification/reconciliation only. Green tier.

### 4.7 Hide / withdraw / archive
- `withdrawn`/`in_review`/`unpublished` → Woo record set hidden
  (D-039 projection); `archived` → hidden, record preserved; Woo-side
  delete is **never** a default action — destructive delete requires
  explicit human approval (RULES §22) and is out of scope for normal
  flows.

## 5. Idempotency + duplicate prevention — operational model (D-044
extension, recorded within it)

Combined D-017 + D-027 practice:

| Threat | Protection |
| --- | --- |
| Duplicate product creation | registry keying (D-017) + deterministic second guard + one D-027 event per create |
| Duplicate variation creation | per-variant registry keying; batch operations individually keyed |
| Repeated webhook/event delivery | (source system, event ID) uniqueness; identical repeat → `skipped_duplicate`, logged (D-027) |
| Retry after timeout | same event ID re-used; non-terminal/failed events retryable; **ambiguous write outcome → read-back reconciliation before any re-create** |
| Partial success (batch) | per-item keys make every item independently reconcilable; partial outcomes reported honestly (RULES §41); nothing silently re-run |
| Unknown Woo response | treated as ambiguous: read-back reconciliation; no retry that could double-create until state is known |
| Conflicting identifier mappings | registry uniqueness (both directions) → integrity error → human review |
| SKU as identity | **never** — SKU is a business identifier and validated data on entries; identity is Product ID/Variant ID via the registry (D-015/D-017) |

## 6. Conflict detection — deterministic classes (D-044 extension)

| Class | Detection | Severity | Automatic action | Human review | Recovery path |
| --- | --- | --- | --- | --- | --- |
| Identifier conflict (our immutable ID changed/reused) | canonical comparison | critical | none — operation blocked | yes | deactivate + recreate per D-014 rule 10 |
| Mapping conflict (registry ↔ Woo disagreement) | registry uniqueness + read-back | critical | none | yes | stale + recreate entry after review (§2.7) |
| SKU conflict (duplicate/non-compliant) | canonical validation + Woo read-back | critical | blocked | yes | D-014 correction path |
| Category conflict (wrong primary/leaf, missing term) | exact pair validation | major | row/operation rejected | yes | owner-approved registry change only (D-031) |
| Attribute-term conflict (unknown term, family mismatch) | exact term validation | major | rejected | yes | D-019 queue (human adds term); never auto-created |
| Price divergence (projected ≠ canonical resolution; Woo manual price edit) | read-back comparison | **critical (Red tier)** | none — surfaced | yes | re-projection after review/correction |
| Lifecycle divergence (Woo record state ≠ D-022 projection) | read-back | major | none | yes | re-projection after review |
| Publication divergence (Woo visible ≠ canonical publication state) | read-back | **critical** | none — surfaced | yes | re-projection after review; visibility reverted only through the D-023 authority path |
| Media divergence (missing image, reordered gallery) | read-back | minor | re-projection allowed (non-price, non-visibility) | only if repeated | canonical order restored by tooling |
| Inventory divergence | future verified read flows | deferred | none | future (D-041) | future phase |
| Unknown/unresolved state (ambiguous response, unknown field) | pipeline | major | reconcile by read-back; no write | yes if unresolved | human investigation |

AI never silently resolves any authoritative conflict; it may only
analyze and summarize (foundation doc §15).

## 7. Woo-side divergence handling (D-047)

When a Woo field owned by the canonical layer is manually changed in
Woo:

1. **Detection:** read-back comparison during verification/
   reconciliation flows (not continuous surveillance — no production
   mechanism designed here).
2. **Preservation:** the canonical value is never adopted from Woo
   and never silently overwritten by Woo content; the canonical layer
   keeps its value as truth.
3. **Review queue/event:** every detected divergence produces a
   review event with field, canonical value, Woo value, timestamps,
   provenance.
4. **Controlled reconciliation (optional):** a human may authorize a
   re-projection; approved tooling then restores the canonical value
   (this is the only sanctioned way Woo-side edits are corrected).
5. **No silent overwrite:** neither direction ever overwrites
   silently; Woo-side edits are never adopted as canonical truth
   (D-042 rule 4).

## 8. Green / Yellow / Red authority matrix (D-050)

Final proposed matrix for WooCommerce operations (extends the
approved tiers; RULES §32):

| Tier | Operations |
| --- | --- |
| **Green (autonomous)** | reads; deterministic validation; registry/safe lookups; dry-run computation; conflict/diff detection reporting; reconciliation *reporting* |
| **Yellow (monitored)** | reversible non-destructive projections (hidden-record creation/updates, metadata, category/attribute data on hidden records); low-risk metadata updates; alt-text drafts; AI-proposed enrichments queued for review |
| **Red (explicit human authorization)** | publication projection (`published`); withdrawal; **any price-affecting write** (list/override/sale projections); inventory-changing operations (future); destructive delete; archive/reactivate execution; any operation resolving a critical conflict |

Notes: media attachment to *hidden* records = Yellow; media changes
affecting a `published` record = Red (visibility-affecting). When an
operation spans tiers, the **highest** tier applies. AI remains
propose/prepare-only everywhere; tooling executes Red operations only
inside human-promoted flows.

## 9. Media storage decision (D-049)

Options analyzed:

| Option | Advantages | Disadvantages |
| --- | --- | --- |
| **External/object storage + Woo references** | media independent of the WP install; clean backup/restore story; CDN potential; simplest future portability (media survives store migrations); small WP uploads dir | requires the storage decision + hardening (Phase 4 territory); Woo must serve external URLs (supported); one more system to secure |
| **Woo Media Library (local uploads)** | zero extra systems; native admin UX; alt text managed in-place | media entangled with the WP instance (backup/migration burden); Iranian hosting disk/bandwidth constraints on image-heavy catalogs; larger restore surface |
| **Hybrid** | flexibility | two sources of truth for media — violates the project's single-authority pattern; most operational complexity |

Context: Iranian hosting (disk/bandwidth cost and reliability for an
image-heavy clothing catalog), backup simplicity (MASTER_PLAN §10),
CDN potential, file identity (references + dedupe by content hash at
implementation), alt text (D-040), future portability (D-001
reusability; vendor lock-in RULES §35).

**Recommendation: External/object storage + Woo references** — media
stays canonical-independent, portable, and cheap to back up; Woo holds
references, exactly matching the D-033/D-040 "references, not
binaries" model. The concrete provider/hosting decision remains with
Phase 4 (register row 6) — this batch records the architectural
direction only. **Owner approval of the direction is requested**
(recorded in D-049 as Approved-with-open-provider, per the batch's
approval of the doc); no storage is set up.

## 10. Non-registry attributes (D-051)

Resolution for Brand, Material, Pattern, Style, Season, Usage,
Collar, Sleeve, Length, Closure, Fit:

- **Canonical:** each remains a canonical structured product field
  (free-text, outside Registry v1 — D-029/D-031 unchanged; no new
  controlled vocabulary is created automatically).
- **Woo representation: product meta** (custom/meta fields attached
  to the product record), not global attributes — global attributes
  would imply store-wide vocabularies and term governance (D-019
  queues, owner approvals) that the owner has not granted; custom
  attributes would scatter representation per product; meta keeps one
  deterministic representation with exact provenance-tagged values.
- **Promotion path unchanged:** if the owner later promotes an
  attribute into a controlled vocabulary, its Woo representation can
  then move to a global attribute (separate owner decision each,
  D-019/D-029).
- **Color and Size behavior unchanged:** exactly as approved
  (variation-defining global attributes per D-037); nothing in this
  section touches them.
- Free-text values never invented: NOT_PROVIDED = field omitted;
  AI may suggest values (Yellow, provenance-tagged).

## 11. Test / sandbox strategy (D-052)

Safe testing design before any real Woo connection (no connection or
credential is created in this batch):

1. **Local/unit validation:** pure-function validation of canonical
   data and payload builders (D-021/D-024/D-025/D-033 rules) — no
   network.
2. **Mock Woo responses:** a deterministic fake covering the D-043
   resource areas, including deliberate success/failure/duplicate/
   timeout/malformed responses per the D-044 classes.
3. **Staging/test Woo environment:** a separate isolated Woo instance
   (environment separation, RULES §18) with its own throwaway
   credentials; never production.
4. **Test data:** test products/variations created inside the
   staging store only; clearly-named fixtures; never real business
   data.
5. **Failure simulation:** Woo unavailable, auth failure, validation
   failure, timeout-before-response, ambiguous timeout (reconcile
   path), rate limiting, partial batch, malformed response.
6. **Duplicate-event simulation:** identical (source, event ID)
   deliveries → skipped_duplicate; conflicting payloads → integrity
   error; double-create attempts blocked by the registry.
7. **Conflict simulation:** mapping/SKU/category/term/price/
   lifecycle/publication conflicts (§6) → correct review-queue
   routing, no silent resolution.
8. **Price-divergence simulation:** the D-048 divergence case →
   projection produces the canonical resolution; expiry re-projection
   window behaves as specified.
9. **Rollback/compensation tests:** hide-and-flag compensation after
   wrong creates; registry stale/recreate flows.
10. **Production-readiness gate:** all of the above green + human
    review of the test report before any production credential ever
    exists (RULES §23, §43).

## 12. Credential / secret structure (D-045 extension, recorded within
it)

Conceptual contract only (no secrets created or requested):

- **Environment separation:** development / staging / production each
  with their own Woo base URL and credentials; no cross-environment
  reuse (RULES §18).
- **Woo base URL:** configuration value per environment, held with
  the secret material, never hard-coded in docs/workflows; **no real
  URL exists in this repository.**
- **API credential references:** flows reference credentials by
  *name/reference* (e.g. a secret-manager key), never by value;
  n8n credential references and OpenAI/AI-provider credential
  references work identically.
- **Secret rotation:** rotation is a planned operation (scheduled +
  after any suspected exposure, RULES §16); rotation procedure is
  defined when infrastructure exists (Phase 4/5).
- **Least privilege:** read-only credentials for verification flows;
  write credentials only for approved sync flows; separate
  credentials per environment (D-045).
- **Logging redaction:** logs never contain secrets; credential
  values redacted by construction (RULES §27).
- **Git exclusion:** secrets never enter the repository (any file,
  any history — RULES §16, §19).
- **Freebuff prompt exclusion:** credentials never enter AI prompts
  or agent context (D-045; foundation doc §14).

## References

- Batch 1 foundation: `docs/phases/phase-03-1-woocommerce-foundation.md`
  (D-034–D-045)
- `DECISIONS.md` — D-014–D-033 (product data + configuration),
  D-034–D-045 (foundation), D-046–D-052 (this batch)
- `DATA_MODEL.md` — §3 (statuses), §8 (pricing), §9 (SKU/identifiers),
  §13 (logical model)
- `PROJECT_RULES.md` — §12–§18, §22–§25, §27, §32–§33, §41, §43

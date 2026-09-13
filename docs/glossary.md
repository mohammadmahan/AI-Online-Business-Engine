# Glossary

Shared vocabulary for the AI-First Online Business Engine project.
Terms are defined once here and referenced everywhere else.

---

## Business context

**Iranian Toman** — The project's initial currency. Prices are stored
numerically (for example `590000`), never as formatted strings such as
`590,000 تومان`. Formatting to Persian text happens only at display
time. (MASTER_PLAN §6, PROJECT_RULES §11)

**RTL-first** — The future storefront UI is designed right-to-left /
Persian first. Applies to customer-facing products, not to project
documentation.

**Product Master Excel** — The seller-facing input workbook
(`product-master.xlsx`, physical contract per D-033: sheets محصولات،
تنوع‌ها، راهنما، گزینه‌ها). Excel is an import/cleanup and management
tool only. It is never the production database and never a source of
truth. (PROJECT_RULES §13)

---

## Data model

**Product** — The general product definition. Most attributes are
optional; incomplete products are valid and must not be blocked.

**Variant** — A real, independently sellable and independently stocked
combination of a product (for example Black / L). Products without
variants must never be forced into artificial variants. Variant-level
prices and inventory are supported. Variant-defining axes are Color and
Size, active only where they genuinely vary (D-018); products differing
only by product-level attributes are separate products.

**Product ID** — The stable business-facing product identifier.
Human-readable (`P00001`), stable, category-agnostic, not derived from
the product name. Distinct from WooCommerce's internal numeric ID. It
is the canonical name for the D-014 product code: `P` + five-digit
zero-padded sequence, issued only by humans or approved deterministic
tooling, immutable, never reused. (D-015, D-017)

**Variant ID** — A separate stable internal identifier for a variant.
Must NOT be the SKU; opaque and system-safe: **UUIDv4**, canonical
lowercase hyphenated form. Issued only by approved deterministic
tooling at variant creation; immutable; never reused. (D-015, D-017)

**SKU** — Stock Keeping Unit. The business/inventory identifier:
human-readable, used for WooCommerce/inventory/Excel/n8n references.
Per D-014 (Approved): five-digit product code (`P00001`) plus canonical
attribute suffix for variants (`P00001-BLK-M`); a simple product
without variants uses its product code as SKU (`P00002`). Uppercase
Latin ASCII only; suffix codes come only from controlled vocabularies;
category and brand are never encoded; frozen at creation (correction =
deactivate + recreate, never rename); duplicate color+size combinations
are rejected as data errors (`-2` exists only as an emergency safety
valve); never silently reused; **AI must never assign or invent a
SKU**; never used as the barcode; identifiers are opaque — business
logic must not parse meaning from digit count. **The SKU is not the
internal database identity of a variant** — structured attributes are
the authoritative source of attribute truth, never SKU parsing.
D-017 reaffirms that Product ID, Variant ID, and SKU remain
permanently distinct and that AI never issues, assigns, invents, or
transforms any identifier. (D-014, D-015, D-017)

**Attribute** — A named product or variant characteristic (e.g. color,
size, fabric). Product attributes are optional unless explicitly
required; incomplete products are valid. (PROJECT_RULES §8)

**Attribute Term** — A single canonical value within an attribute's
controlled vocabulary: a Latin code where applicable (e.g. `BLK`)
plus a display label (e.g. Persian color name), with aliases, a
lifecycle state (active/deprecated, never deleted), and provenance
(D-011 states). Suffix codes in SKUs may come only from Attribute
Terms. Governance per D-019: humans create terms; AI may propose but
never create/activate/modify/delete; exact alias normalization only —
no fuzzy matching; unmapped values retained for human review.

**Controlled Vocabulary** — The closed registry of allowed Attribute
Terms for a field (colors, sizes, categories, …). Used where
consistency matters; unknown/unprovided values are preserved as
explicit states — the vocabulary must never force a guess. Governance
architecture approved (D-019); v1 structure approved (D-029 —
required vocabularies: color, size, category); concrete category,
color, and size terms **owner-approved via D-031 Batch 1** (see
`docs/phases/phase-02-5-business-data-configuration.md`); color/size
**SKU-code mappings owner-approved via D-032 Batch 2** (O/I/L-safe);
**aliases remain open** (register item 3) and owner-gated.

**Barcode / EAN** — The external trade identifier printed on goods.
Separate from the SKU: it has its own field and lifecycle, and the SKU
must not be used as the barcode. (D-014 rule 13)

**Provenance** — The tracking of how a piece of information came to
exist: who/what produced it and its verification state. AI-generated
information must always carry provenance (`AI_GENERATED`) and cannot
be presented as verified fact; only humans set `HUMAN_*` states, and
`HUMAN_VERIFIED` information cannot be silently overwritten by AI.
(PROJECT_RULES §7, D-011)

**Variant-defining attribute** — An attribute whose values combine to
form real, independently sellable/stocked variants. Approved initial
set: {Color, Size}, with per-axis applicability — an axis is active
only when it genuinely varies; a simple product has zero active axes
and SKU = Product ID (D-018).

**Active axis** — A variant-defining attribute that genuinely varies
for a given product. SKU suffix contains exactly the active axes in
canonical order Color, then Size: `P00001` (simple), `P00001-BLK`
(color-only), `P00001-BLK-M` (color + size). Duplicate checks run over
active axes only (D-018).

**Size family** — The size-system classification (alpha/letter,
numeric, pants/waist, shoe, future/brand-specific) declared at product
level; the specific size term belongs to the variant. Canonical size
term (registry identity + SKU code) and customer-facing display value
remain distinguishable; measurements are reference data, never
invented (D-020).

**Size-code convention (O/I/L-safe)** — Governance approved (D-030):
size codes are uppercase Latin ASCII, never contain `O`/`I`/`L` in any
position (D-014 rule 7 — no exception), owner-created and
owner-approved, frozen once referenced (deprecate + recreate, never
rename), family-scoped. Size **terms** are owner-approved (D-031
Batch 1: Alpha/8, Numeric/11, Pants Waist/9; shoe excluded);
concrete mappings are **owner-approved via D-032 Batch 2** (Alpha
uses separate O/I/L-safe codes — L→LG, XL→XG, XXL→XXG, 3XL→3XG,
4XL→4XG; Numeric/Pants Waist use canonical value = code). Display
may stay conventional (L, XL) regardless of the canonical code.
(D-014 rule 7, D-020, D-030, D-031)

**Owner-approved configuration** — Concrete business values (category
structure, color terms, size terms/families, product-attribute list)
supplied and approved by the human owner (D-031), recorded in
`docs/phases/phase-02-5-business-data-configuration.md`. Distinct
from AI-generated or AI-suggested content: the AI's role in producing
these records was limited to structuring exactly what the owner
approved — no value was invented, defaulted, or auto-filled.
Governance for future changes of these values is D-019 plus an
explicit owner decision.

**Required field / publication minimum** — Minimal required-field
policy (D-021): product creation minimum (Product ID, Name, Product
status, Created date); variant creation minimum (Variant ID, Product
ID, SKU, active variant-defining attributes, Variant status);
publication minimum (Name, Main category, resolvable price, ≥1 media
image, valid publication status, all variants valid). Description and
short description are not publication blockers. Missing required
fields block only the relevant lifecycle transition and never receive
guessed values. AI may draft descriptions/SEO/keywords/suggestions
(Yellow tier, provenance-tagged) but may never create identifiers,
prices, discounts, stock, vocabulary terms, shipping/payment/order
facts, or guessed attribute values.

**Product status** — The product lifecycle state machine (D-022):
`draft` (exists, incomplete allowed, not sellable), `active` (usable;
structurally valid; required for publication), `archived`
(deactivated; never deleted). Rejection of a review candidate returns
it to `draft` — no separate stored state. Transitions are human
actions (draft → active may be executed by approved deterministic
tooling when all publication checks pass); archived products can never
reactivate directly. Variant status mirrors the product's lifecycle.
**Publication status is a separate state machine (see below) and is
never a substitute for product status.** (D-022)

**Publication status** — The storefront-visibility state machine
(D-023), independent of product status: `unpublished` (default),
`in_review` (being checked against the D-021 publication minimum),
`published` (publicly visible/sellable), `withdrawn`
(intentionally unpublished after having been published). Publishing is
Red tier: **explicit human approval** plus all D-021 publication
minimums plus product status `active` are required; AI may prepare
review submissions and suggest transitions but may never execute
publish or unpublish. Deterministic tooling may run the checks and
move `unpublished` → `in_review`; it may never publish or unpublish.
(D-023)

**List price / variant price / effective price** — The minimal
three-field price model (D-024): `list price` (numeric Toman;
required; the reference/base price), optional `variant override`
(required when the variant's price differs from the product's), and
optional `sale price` with optional `sale price validity end`
(timestamp). Effective price = the effective sale price (variant-level
sale if set and valid, else product-level sale if set and valid),
otherwise variant override if set, otherwise list price. Deterministic,
variant-aware, and resolvable per D-021; the resolvable price is a
publication minimum. AI may draft a recommendation (Yellow tier,
provenance-tagged) but never creates or changes a price. (D-024)

**Sale price** — An optional, explicitly stored selling price (D-024,
D-025). The approved discount model is sale-price-based: a discount is
*expressed* as an explicit sale price, never as a live computed
percentage — the numeric base price field is never silently changed by
a discount. Sale price is optional, must be lower than the effective
base price, must never make the effective price negative or zero, and
may carry an optional validity end (after which it is ignored — never
extended automatically). Exactly one effective sale price applies per
product/variant: the most specific valid one (variant-level if set and
valid, else product-level); an invalid/expired variant sale falls back
to the product-level sale, then to the base price. (D-024, D-025)

**Event-level idempotency** — Duplicate suppression for webhook,
retry, and scheduled events (D-027), distinct from identifier-based
import idempotency (D-017). Conceptual model: each processed event is
recorded with a **source system**, a **source event ID** (stable ID
from the source; when absent, a deterministic hash of operation type,
target identifier, timestamp, and payload), the **operation type**, a
received timestamp, and a **processing status** (`received` →
`processing` → `succeeded`/`failed`/`skipped_duplicate` — terminal
states are never re-entered). The pair (source system, event ID) is
the uniqueness key; a repeat with identical payload is skipped and
logged; a repeat with a conflicting payload is a data-integrity error
— flagged for human review, never silently reprocessed. Safe-retry
rule: an operation may be retried only while its status is
non-terminal (`received`/`processing`) or after `failed`; a
terminal-succeeded event is never re-executed. Retention is an
implementation decision, deferred. (D-027)

**Excel import contract** — The approved scope for importing the
Product Master Excel workbook (D-028): Excel is an input/import
surface, never a Source of Truth and never a store. One product = one
product row plus zero or more variant rows; import never issues any
identifier (Product IDs are human-supplied; Variant IDs/SKUs come only
from approved deterministic tooling); prices map 1:1 to D-024 with
D-024 validation; vocabulary/size resolution is exact-match against
active terms (D-019/D-020); missing values stay `NOT_PROVIDED`,
unknown stay `UNKNOWN`, invalid values are rejected per row with no
auto-correction; duplicates are rejected, never silently merged.
Every imported value carries `IMPORTED` provenance (D-026); each run
is a D-027 event; **dry-run first**, and only a human promotes a
dry-run to an actual import. Re-import follows D-017. (D-028; the
physical realization is the D-033 workbook contract —
`docs/phases/phase-02-5-excel-master-template.md`: blank =
`NOT_PROVIDED`, exact `نامشخص` = `UNKNOWN`, invalid = rejected.)

**Dry-run (import preview)** — The mandatory first stage of an Excel
import (D-028): full deterministic validation and a would-be-result
report with **no writes**. Only an explicit human promotion turns a
dry-run result into an actual import.

**Registry v1 (structure)** — The approved minimal vocabulary set for
Phase 2 (D-029): `color` and `size` (variant-defining,
SKU-code-bearing) and `category` (product-level). Other attributes
are deferred until the owner promotes them. Entries carry: canonical
code (variant-defining only, O/I/L-safe per D-030), canonical
value/slug, required Persian display label, optional English label,
aliases, active/deprecated status, provenance, timestamps, notes.
Governance is D-019's, unchanged: humans create, AI proposes only,
exact alias matching, no fuzzy matching. **Concrete registry values
(colors, sizes, categories) remain OPEN and owner-gated.** (D-029)

**Size-code governance** — The O/I/L-safe generation rules for size
codes (D-030): uppercase Latin ASCII; `O`, `I`, `L` forbidden in any
position (D-014 rule 7, no exception); codes owner-created and
owner-approved; AI proposes only, never assigns; frozen once
referenced (correction = deprecate + recreate, never rename); one
canonical code per active term (aliases resolve to the term, not to
another code); namespace scoped within the size family; registry
collisions rejected at proposal time; SKU collisions handled only by
the D-014 `-2` emergency valve. **Concrete size-code mappings are
owner-approved via D-032 Batch 2**; size-equivalence mappings remain
an open owner sub-decision. (D-030)

**Provenance source types** — The five origins a value's provenance
may record (D-026): `HUMAN_ENTERED` (a human entered the value),
`SYSTEM_GENERATED` (deterministic tooling produced it),
`AI_GENERATED` (AI produced it — always paired with the D-011 review
state until a human raises it), `IMPORTED` (arrived via an import,
with a source reference such as a file/batch), `EXTERNAL_SYNC`
(arrived via a verified external-system sync). Provenance records are
append-only; AI origin is never erased; no secrets are stored.
(D-011, D-026)

Missing information states (PROJECT_RULES §6, MASTER_PLAN §5) — two
distinct states, never conflated:

- `UNKNOWN` — Searched for, not determinable.
- `NOT_PROVIDED` — Source did not supply the value.
- `INVALID` — Supplied, but structurally or business-rule invalid
  (e.g., malformed number, price-rule violation). Rejected at
  validation with a row/field-level error; never auto-corrected,
  never clamped (D-028 rule 13). `UNKNOWN` ≠ `NOT_PROVIDED` ≠
  `INVALID` — the three are never silently transformed into one
  another.

Provenance states (PROJECT_RULES §7, MASTER_PLAN §5):

- `AI_GENERATED` — Produced by AI; has not passed human review.
- `HUMAN_REVIEWED` — Seen and accepted by a human; may still contain AI
  content.
- `HUMAN_VERIFIED` — Confirmed by a human against a trusted source.
  Stronger than `HUMAN_REVIEWED`; cannot be silently overwritten by AI.

Core rule: AI must never invent material, color, size, measurements,
price, discount, stock, shipping time, payment status, order status, or
customer information. AI inference must never be presented as verified
fact.

---

## Human-in-the-loop autonomy tiers

(MASTER_PLAN §9, PROJECT_RULES §32)

- **Green — autonomous.** Classification, formatting, drafts, internal
  summaries, low-risk transformations. No human gate required.
- **Yellow — monitored.** Customer reply drafts, product descriptions,
  lead classification, marketing drafts, recommendations. Human review
  happens before customer/production exposure; the activity is logged.
- **Red — human approval.** Refunds, financial actions, production price
  changes, credential changes, security changes, destructive operations,
  permanent deletion, high-impact disputes, high-risk production
  deployment. AI execution is forbidden without explicit human approval.

---

## Architecture

**Source of Truth** — The single authoritative system for a category of
data. For this project, WooCommerce is the transactional source of truth
for products, variants, SKUs, prices, inventory, orders, customers,
coupons, and store state. Notion and Excel are explicitly not sources of
truth for transactional data.

**Business Operating System (Notion)** — Dashboards, SOPs,
documentation, knowledge, content planning, ideas, review queues, and
reports. Never inventory, payment, or order state.

**Orchestration layer (n8n)** — Webhooks, scheduled jobs, API
integration, data transformation, AI orchestration, retries,
idempotency, error handling, notifications.

**AI Runtime** — API-based AI services used for classification,
extraction, content drafts, customer/sales assistance, analysis, and
recommendations — within the Green/Yellow/Red autonomy tiers.

**Development/custom-tool layer (Freebuff)** — Internal tools,
dashboards, utilities, adapters, tests, refactoring, and custom
interfaces. Does not replace WooCommerce or n8n by default.

**Provider boundary** — A vendor-agnostic interface that keeps
integrations replaceable. Planned boundaries (PROJECT_RULES §35):
`AIProvider`, `PaymentProvider`, `ShippingProvider`, `InstagramProvider`.

---

## WooCommerce integration (Phase 3)

Terms introduced by the Phase 3 Batch 1 foundation design (D-034–D-045;
normative design in
`docs/phases/phase-03-1-woocommerce-foundation.md`). None of these
replace existing terms — they map them into WooCommerce.

**WooCommerce Product ID** — WooCommerce's own numeric identifier for
a product record, generated by WooCommerce at creation. A platform-
owned **internal technical identifier**: never our business identity,
never renumbered or reassigned, and never confused with our Product ID
(which is stored in Woo only as a reference). (D-034)

**WooCommerce Variation ID** — WooCommerce's numeric identifier for a
variation record, generated by WooCommerce at creation. Platform-owned
technical identifier, mapped to our Variant ID through the mapping
registry; never a replacement for the Variant ID or the SKU. (D-034)

**Global Attribute** — A store-wide WooCommerce product attribute
shared across products (e.g. `pa_color`). In this project exactly the
approved variation-defining vocabularies become global attributes:
`pa_color` plus one size attribute per approved family
(`pa_size-alpha`, `pa_size-numeric`, `pa_size-waist`). (D-037)

**Attribute Term** — See the data-model definition above. In
WooCommerce, a term of a global attribute: display name = the Persian
canonical value; slug = the lowercase D-032 code. The Woo term ID is a
mapped technical id recorded in the mapping registry — it is never
confused with our canonical code. (D-034, D-037)

**Variation** — WooCommerce's representation of one sellable variant
of a variable product. Maps 1:1 to our Variant, keyed through the
mapping registry (never by name matching). (D-034, D-035)

**Simple Product** — A WooCommerce product of type `simple`: the
projection of our product with zero active variant-defining axes;
SKU = Product ID. (D-035)

**Variable Product** — A WooCommerce product of type `variable` with
one or more variation-defining attributes and one variation per
active-axis combination: the projection of our product with ≥ 1
active axis. A single-variation variable product stays `variable`
(no demotion heuristic). (D-035)

**Synchronization** — The human-promoted, event-idempotent flows that
project canonical Product Master data into WooCommerce (business
fields) and write created Woo identifiers back into the mapping
registry. Directions are explicit per field; there is **no default
bidirectional field sync**, and Woo-owned transactional fields (stock,
orders, customers, coupons) are never written by sync flows. (D-042,
D-044)

**Mapping Registry** — The conceptual one-to-one registry connecting
our identifiers/taxonomy terms to their WooCommerce counterparts
(Product ID ↔ Woo product ID; Variant ID ↔ Woo variation ID; color/
size/category terms ↔ Woo term/category IDs). Written only by approved
deterministic tooling at first successful creation/read-back; never
hand-maintained, never fuzzy-matched; conflicts route to human review.
It is a **Phase 3 implementation requirement** — it does not exist
yet. (D-034)

**Projection (WooCommerce)** — The deterministic rendering of our
canonical D-022/D-023 lifecycle and publication states into
WooCommerce's status/visibility fields (draft → no record yet;
active+unpublished/in_review/withdrawn → hidden; active+published →
published; archived → hidden, preserved, never deleted). The canonical
states remain ours; a native Woo status is never claimed equivalent to
a canonical state. (D-039)

**Canonical-layer price projection** — The approved D-048 resolution
of the D-038 price-divergence sub-gate (owner-approved 2026-09-13,
Option A): approved deterministic
tooling computes the D-024/D-025 effective-price resolution and writes
it into the WooCommerce fields Woo actually displays, at every
affected change; base/list and override fields are never mutated;
sale expiry is handled by deterministic scheduled re-projection. Woo
price fields for PM-owned products become projections — never
canonical truth, never hand-edited as such (Woo-side price edits are
Red-tier divergences). **Approved — Option A.** (D-024, D-038, D-048)

**Mapping registry (registry states)** — The complete D-046 design of
the D-034 registry: entries for product/variation/category/color/
size/media linkages with the canonical side always authoritative;
uniqueness enforced in both directions (one active entry per
canonical key; a Woo ID in at most one active entry per type); the
SKU stored as data, never identity; fields classified immutable /
write-once (Woo ID, changed only via stale-recovery) / mutable
metadata. States: **missing** (normal pre-create path), **stale**
(Woo record lost/changed — entry marked, re-link after human review),
**conflicting** (integrity error → human review, never silently
re-linked), **orphaned** (flagged for human decision; hide/preserve
by default). Lookup is exact-key only; a deterministic read-back
second guard runs before any create. (D-034, D-046)

**Sync contract / CRUD contract** — The D-047 operational contracts:
field-level sync rules for every field group (canonical owner, Woo
projection, one-way direction, allowed write actor, Woo-manual-edit
= divergence → review queue, UNKNOWN/NOT_PROVIDED behavior, AI
proposes / deterministic tooling executes within human-promoted
flows, approval tier) and the product/variation CRUD pipeline
(preconditions → canonical validation → registry lookup → D-027
event → payload validation → write → read-back verification →
registry update), with hide-and-flag compensation and **no
destructive delete by default** (RULES §22). No default
bidirectional sync anywhere (D-042). (D-047)

**Woo-operation authority matrix** — The D-050 Green/Yellow/Red
classification for WooCommerce operations: Green = reads, validation,
lookups, dry-runs, detection/reporting; Yellow = reversible
non-destructive projections on hidden records, low-risk metadata,
enrichment queues; Red = publication projection, withdrawal, any
price-affecting write, inventory-changing operations (future),
destructive delete, archive/reactivate execution, critical-conflict
resolution. Highest tier applies when an operation spans tiers; AI
remains propose-only. (D-050)

**Non-registry attribute representation** — The D-051 resolution for
Brand, Material, Pattern, Style, Season, Usage, Collar, Sleeve,
Length, Closure, Fit: canonical free-text structured fields (outside
Registry v1; no vocabulary created automatically) projected into Woo
as product meta — not global attributes and not per-product custom
attributes. Promotion into a controlled vocabulary (and then a global
attribute) stays a separate owner decision. Color and Size untouched
(D-037). (D-051)

**Local-first development environment** — The D-053 owner directive
(2026-09-13): all Phase 3 implementation/testing happens first in a
local environment (WordPress+Woo, databases, n8n, mock/test services
on the development machine), then promotes **Local → Staging →
Production** without redesign: business rules, canonical
schemas/contracts, sync/idempotency/conflict contracts (incl. D-048
Option A), validation, authority tiers, adapter interfaces, and log
format stay identical across environments; URLs, credentials,
storage provider, seed data, and observability settings are
per-environment. A local stack is development tooling — it does not
open Phase 4 production infrastructure. (D-053)

**Mock WooCommerce adapter** — The D-052 layer-2 local fake
implementing the same interface contract as the future real Woo
adapter (D-043 resource areas under the D-047 CRUD contract), with
deterministic failure injection for every D-044 error class. Business
logic is written against the interface, so the real adapter is a
drop-in replacement; no real Woo connection exists locally. (D-052,
D-053)

**Canonical project database (D-055)** — The approved local
storage for canonical data: a relational application database
(PostgreSQL) holding the Product Master entities, the mapping
registry, the event/idempotency store, and provenance as logically
separate schemas. Files cannot enforce the approved uniqueness/
idempotency/append-only constraints; WooCommerce-as-canonical is
forbidden (D-003/D-042). **Approved (2026-09-13, owner); initial
schema implemented in `local/db/schema.sql`.** (D-055)

**Local media emulator (D-056)** — The approved local equivalent of
the D-049 object-storage direction: an S3-compatible emulator behind
the same adapter boundary as the future real Phase 4 provider;
swapping it changes only endpoint/credential configuration, never
business logic. **Approved (2026-09-13, owner); the real provider
stays Phase 4.** (D-056)

---

## Process

**Phase** — A numbered stage of the roadmap (Phase 0 – Phase 28) defined
in MASTER_PLAN §13.

**Definition of Done** — A meaningful task is done when: correct
implementation exists; relevant tests/checks pass; failure cases are
considered; security is considered; documentation is updated when
needed; Git state is understandable; required approval exists; no known
critical failure is hidden. (PROJECT_RULES §38, MASTER_PLAN §14)

**STOP → EXPLAIN → APPROVAL** — The mandatory sequence for major
architecture changes (database, ecommerce source of truth,
authentication, payment, security, infrastructure, API strategy, data
ownership, major vendor dependency, production deployment).
(PROJECT_RULES §4)

**Destructive operation** — Deleting database data, customer records,
products, files; dropping tables; resetting production; revoking
credentials; rewriting Git history; replacing production configuration.
Requires explicit human approval. (PROJECT_RULES §22)

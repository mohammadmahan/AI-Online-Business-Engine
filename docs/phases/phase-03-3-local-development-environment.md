# Phase 3.3 — Local Development Environment (Batch 3 design)

Status: **Batch 3 design recorded (2026-09-13); D-053/D-054/D-055/
D-056 all owner-approved (2026-09-13); Batch 4 scaffolding
implemented under `local/` (2026-09-13 — see `local/README.md`)**

---

## Purpose

Design and prepare the complete **local development environment** so
the ecommerce automation system can be implemented and tested locally
first, then promoted to Staging and Production **without redesigning
the system** ("change configuration, not business logic").

This batch is **design/specification only**: no production code, no
container/runtime installation, no real WooCommerce connection, no
credentials, no secrets, no production hosting, no commit, no push.

## 0. Relationship to the approved architecture

- Architecture unchanged (D-001–D-013): **WooCommerce = transactional
  ecommerce Source of Truth**; n8n = orchestration; Notion = Business
  OS; AI = intelligence/enrichment; Excel = input-only (D-006);
  Freebuff = development/custom-tool layer (D-007).
- **D-048 is Approved (Option A: canonical-layer price projection)**;
  the price-projection test design below verifies it exactly as
  approved. D-014–D-052 are all preserved; nothing here rewrites a
  business rule.
- **Scope boundary vs the blocked-phase list:** a *local development*
  environment is development tooling (D-007, MASTER_PLAN §11
  "Development → Testing/Staging → Production", RULES §18). It is
  **not** Phase 4 production infrastructure: no hosting is selected,
  no VPS is bought or configured, no DNS/domain/SSL/backup production
  setup happens. `TODO.md` keeps Phase 4 blocked.
- The owner has explicitly directed **local-first** development
  (2026-09-13); this batch records that directive as D-053 and designs
  the environment around it.

## 1. Local-first architecture (D-053 — Approved)

```text
LOCAL (macOS, this batch)  →  STAGING (isolated, later)  →  PRODUCTION (Phase 4)
     Docker Compose stack        same contracts, real          same contracts,
     mock/test services first    isolated Woo instance         real provider
```

Layered responsibilities (unchanged from D-042/D-047):

1. **Canonical business layer (ours, local):** Product Master data,
   registries, D-024/D-025 price fields, D-022/D-023 states,
   provenance, mapping registry, event store.
2. **Transactional projection layer (Woo, local):** WordPress +
   WooCommerce receiving projections only; owns transactional state.
3. **Orchestration (n8n, local):** triggers, sequencing, retries,
   event records, error routing — never a data store.
4. **Test/mock layer:** the mock WooCommerce adapter and deterministic
   fixtures that make the whole loop runnable offline.
5. **AI (local):** stubbed/mocked until Phase 7; proposals only.

What is **local-only**: mock adapter, fixtures, media emulator,
throwaway local credentials, test dataset, reset tooling.
What is **environment-independent**: the decision set, canonical
schemas/contracts, sync/CRUD contracts, validation, authority tiers,
adapter interfaces, logging format (§19 promotion contract).

## 2. Component architecture

| Component | Purpose | Owner | Depends on | Persistent data | Configuration | Communication | Failure behavior | Exists in staging/production? |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **WordPress + WooCommerce** | transactional projection target (D-003) | Woo owns its transactional state; business fields are projections (D-042) | Woo database | its DB (§5) | WP config via env; locale/currency/permalinks (§5) | HTTP REST (D-043) from tooling/n8n | restart-safe; recreation = reset tooling | yes (real instance) |
| **Woo database (MySQL/MariaDB)** | WordPress/Woo persistence | Woo | WordPress | Woo tables + uploads | env (local creds only) | WP internal | recreate from seed; **never canonical** | yes |
| **Canonical project database** (D-055, approved) | Product Master data, registries, provenance | ours | — | products, variants, vocabularies, prices, states, provenance (D-026) | env DSN (local only) | app/tooling + n8n via approved flows | recreate from seed fixtures | yes (schema identical) |
| **Mapping registry** (D-046) | canonical ↔ Woo ID linkage | ours | canonical DB | registry entries (§7) | in canonical DB | tooling reads/writes inside promoted flows | stale/orphan/conflict per D-046 §2.7 | yes (schema identical) |
| **Event/idempotency store** (D-027) | event-level idempotency | ours | canonical DB | event records (§8) | in canonical DB | all write flows | duplicate/conflict per D-027 | yes (schema identical) |
| **n8n** | orchestration only (D-042) | n8n instance owner | canonical DB, Woo, (AI later) | workflow definitions, execution logs | env URLs + credential *references* (D-045) | HTTP/webhooks on the compose network | workflow-level retries; never invents data | yes (deployment model = register row 7, unchanged) |
| **Mock WooCommerce adapter** (§9) | offline Woo simulation per D-052 | ours (test tooling) | canonical DB (fixtures) | fixture-driven state | env `MOCK_*` switches | same interface as the real adapter (D-043/D-047) | simulates every D-044 error class | **no** — local test layer only |
| **Local media storage** (D-056, approved) | local equivalent of the D-049 object store | ours | — | image files + content hashes | env endpoint/keys (local only) | S3-compatible API; Woo holds references (D-049) | recreate from fixtures | staging/production = **real provider** (Phase 4, owner-gated) behind the same interface |
| **Logging/observability** (§17) | structured local logs | ours | all components | log files (not in Git) | env LOG_* | stdout/file per compose service | log loss never blocks a flow; never hides errors (RULES §24) | format identical; aggregation differs (Phase 22) |

## 3. Local runtime technology (D-054 — Approved)

Comparison:

| Option | Reproducibility | Easy reset | Portability | Similarity to server deployment | Complexity | Fit |
| --- | --- | --- | --- | --- | --- | --- |
| **Docker Compose** (recommended) | high — one declarative file pins versions of WP, Woo DB, n8n, canonical DB, media emulator | high — destroy volumes + recreate from seed | high — same file later informs staging | high — container model matches typical VPS deployment | low-moderate — one file, no orchestration beyond Compose | **best fit** |
| Native macOS installs (Homebrew WP/PHP/MySQL, n8n via npm) | low — host drift, version pinning manual | low — cleanup scattered across the host | low — machine-specific | low | high operational surface for 6+ cooperating services | rejected |
| Remote dev VPS as "local" | moderate | moderate | moderate | high | requires hosting = Phase 4 territory; violates local-first and the blocked-phase boundary | rejected for now |

**Recommendation: Docker Compose** as the default local runtime — one
declarative stack for WordPress+Woo, Woo database, canonical database,
n8n, media emulator, and the mock adapter, with named volumes for
persistent data and a documented destroy/recreate reset. Nothing is
installed in this batch; the Compose *file itself* is safe local
scaffolding **after** the owner approves D-054–D-056 (§22).
Conceptual services and volumes (design, not infrastructure):
`wordpress` (with the Woo plugin), `woodb` (MySQL/MariaDB, volume
`woo_data`), `canonical-db` (per D-055, volume `canonical_data`),
`n8n` (volume `n8n_data`), `media` (per D-056, volume `media_data`),
`mock-woo` (stateless, fixture-seeded), shared internal network,
localhost-only published ports (§18).

## 4. Environment configuration (extends D-045; no secrets exist)

Structure: `.env.example` (committed, placeholder values only) —
`.env.local` / `.env.staging` / `.env.production` (**gitignored,
never committed**; staging/production files created only in their own
phases). Real secret values never enter Git, Markdown, Excel, AI
prompts, or logs (RULES §16; D-045).

| Category | Keys (conceptual) | Notes |
| --- | --- | --- |
| Application environment | `APP_ENV=local/staging/production` | selects defaults; never changes business logic (§19) |
| Woo database connection | `WOO_DB_*` | local throwaway values only |
| Canonical database connection | `CANONICAL_DB_*` | per D-055 if approved |
| WordPress/WooCommerce URL | `WORDPRESS_URL`, `WOOCOMMERCE_URL` (+ REST namespace at implementation) | local loopback values; **no real production URL exists anywhere in this repository** |
| n8n URL | `N8N_URL` | compose-internal hostname locally |
| API credential references | `WOO_CREDENTIAL_REF`, `N8N_CREDENTIAL_REF` | **references/names only** (D-045 §12); values live in the environment's secret store; local values are throwaway |
| AI credential references | `AI_CREDENTIAL_REF` | no AI provider configured (register row 9 open); local AI is stubbed |
| Storage configuration | `MEDIA_ENDPOINT`, `MEDIA_BUCKET`, `MEDIA_CREDENTIAL_REF` | local emulator per D-056; real provider = Phase 4 |
| Logging configuration | `LOG_LEVEL`, `LOG_FORMAT` | §17 |

## 5. Local WordPress + WooCommerce design

- **Stack:** WordPress + WooCommerce plugin in Compose; the exact
  plugin/version pinning and Woo version are implementation-time
  choices recorded in the Compose file later.
- **Permalinks:** pretty permalinks enabled (REST API readiness); exact
  slug scheme verified at implementation (SEO slug language stays OPEN,
  D-016.M — permalinks here are internal store structure, not the SEO
  decision).
- **REST API readiness:** local REST keys created inside the local
  instance only (throwaway, least privilege per D-045: a local
  read/write key for the approved sync flows; no production key).
- **Webhook readiness:** Woo webhooks may target n8n over the shared
  Compose network (localhost delivery works container-to-container);
  no production webhook endpoints exist (§18).
- **Cron:** WP-CRON disabled for determinism; scheduled behaviour
  (sale-expiry re-projection per D-048 §1.4.3) triggered by explicit
  local scheduling in the test harness — deterministic and observable.
- **Timezone:** store timezone Tehran (`Asia/Tehran`); date handling
  stored UTC-side in our canonical layer per D-024 timestamp semantics.
- **Currency = Iranian Toman (D-010):** numeric Toman; formatted-string
  prices never stored (RULES §11). The exact Woo currency
  configuration mechanism (custom currency code/symbol) is an
  **implementation-time verification point** — not invented here.
- **Persian/RTL readiness:** `fa_IR` locale + RTL store view is the
  seller/storefront expectation (MASTER_PLAN §1); the concrete
  localization approach is an implementation-time verification point.
  Project documentation remains English (docs/README convention).
- **Product/variation structure:** exactly D-035 — zero active axes →
  `simple`; ≥1 axis → `variable` with one variation per active-axis
  combination; no third type.
- **Category structure:** exactly the D-036 two-level seed of D-031
  (2 primaries; 12 + 8 children; duplicate leaf names separate under
  their own primary). Seeded once by approved tooling from the
  owner-approved registry — no runtime category creation.
- **Color attribute:** `pa_color` with the 25 owner-approved terms
  (Persian display; Latin slug = lowercase D-032 code; D-037).
- **Size-family attributes:** `pa_size-alpha`, `pa_size-numeric`,
  `pa_size-waist` with the D-032 family-scoped codes (D-037) — the
  family-scoped semantics survive locally by construction.
- **Canonical rule:** the local Woo database is **never canonical**
  (D-003/D-042); it is the same projection target as any later
  environment. Nothing in this section invents business vocabulary;
  only D-031/D-032 owner-approved values are seeded.

## 6. Local database responsibility split

Four distinct stores; never collapsed:

1. **WordPress/WooCommerce database** — Woo's own persistence
   (posts/meta/tables). Transactional projection layer. Never our
   canonical store (D-003, D-042).
2. **Canonical project data** — Product Master entities: products,
   variants, registry v1 vocabularies, price fields, lifecycle/
   publication states, media references (DATA_MODEL §13 logical
   model).
3. **Mapping registry** — the D-046 linkage store (§7).
4. **Event/idempotency store + provenance store** — D-027 events
   (§8) and D-026 provenance records (append-only).

**Canonical storage mechanism — analysis (D-055 — Approved):**

| Option | Verdict | Reason |
| --- | --- | --- |
| Structured local files (JSON/YAML) | rejected | D-046 requires bidirectional uniqueness constraints, D-027 requires atomic (source, event ID) keying with terminal states, D-026 requires append-only records; files cannot enforce these under concurrent flows without rebuilding a database by hand (RULES §5: do not rebuild mature systems) |
| WooCommerce as canonical | **forbidden** | contradicts D-003/D-042: Woo is the projection target; our identifiers, states, and provenance do not exist there as authority |
| **Application database (relational)** | **recommended** | native enforcement of the approved uniqueness/idempotency/provenance constraints; mature; the same schema concept promotes local → staging → production unchanged |

Recommendation: **one relational application database (PostgreSQL)
locally**, holding canonical data, the mapping registry, event store,
and provenance as **logically separate schemas** in one physical
instance locally; staging/production may separate instances later
without schema change. This is a **database-architecture** decision →
RULES §4 requires explicit owner approval; recorded as **D-055
Proposed**. Nothing is provisioned until approved.

## 7. Mapping registry — local implementation plan (D-046 realized)

Physical design deferred until D-055 is approved; the logical plan:

- **Registry entries** (one table per entry type, or one typed table —
  exact shape at implementation): `entry_type` (product/variation/
  category/color_term/size_term/media_reference); canonical key
  columns (`product_id`, `variant_id`, `(primary, leaf)` pair, color
  term, `(family, size)` pair, media reference); `woo_id`; `woo_slug`;
  `status` (`active`/`stale`/`orphaned`); `created_at` (immutable);
  `last_verified_at`; `notes`.
- **Uniqueness (both directions, D-046 §2.2):** one active entry per
  canonical key; a Woo ID in at most one active entry per type —
  enforced as partial unique constraints over active rows; violations
  = `MAPPING_CONFLICT` integrity error → human review.
- **SKU is data, not identity (D-015/D-017):** stored as a validated
  column on variation entries; never a lookup key; never unique-
  enforced as identity.
- **Lifecycle/creation/update/lookup:** exactly D-046 §2.3–§2.6 —
  immutable canonical key + created_at; write-once Woo ID/slug; tooling
  creates entries only inside human-promoted flows; exact-key lookup;
  deterministic second guard (read Woo by stored external reference)
  before any create.
- **Orphan/conflict detection & recovery:** read-back reconciliation
  flags stale/orphaned/conflicting states (D-046 §2.7); re-links need
  human review; no destructive cleanup without explicit approval
  (RULES §22).
- **Idempotency:** identifier-level half of the model (D-017); every
  creation carries a D-027 event reference and D-026 provenance.
- **Classification:** logical design = this document; physical
  implementation = **deferred** behind D-055 (and is safe local
  scaffolding only after that approval).

## 8. Event + idempotency store (D-027 realized)

Logical store (in the canonical database per D-055):

| Field | Notes |
| --- | --- |
| `source_system` + `event_id` | **composite unique key** — the D-027 identity |
| `operation_type` | create/update/read-project/hide/project-prices/seed/… |
| `received_at` | timestamp |
| `processing_status` | `received` → `processing` → `succeeded` \| `failed` \| `skipped_duplicate` (D-027 states, unchanged) |
| `result_reference` | created Woo ID(s), registry entry, or error class reference |
| `payload_hash` | detects *conflicting* repeats: same key + different payload = integrity error → human review; same key + same payload = `skipped_duplicate` (logged) |
| retry metadata | attempts, last error class (D-044 classes); backoff values set per workflow at Phase 5 |

Rules: terminal states are never re-entered; retries reuse the same
event ID; ambiguous outcomes are reconciled by read-back **before** any
re-create (D-044); the store is the event-level half of idempotency —
**distinct from** the identifier-level registry (D-046 §2.9) and from
identifier idempotency (D-017). **Test reset:** local-only purge/reseed
via the reset tooling (§15); reset tooling never exists against
staging/production data.

## 9. Mock WooCommerce adapter (D-052 layer 2 realized)

A deterministic fake implementing the **same interface contract** as
the future real adapter — the D-043 resource areas under the D-047
CRUD contract: create/update/read product; create/update/read
variation; categories; attributes; attribute terms; media; inventory
**reads** (read-only, D-041 boundary — the mock implements no stock
writes).

Simulated behaviours (fixture-driven, deterministic):

- success paths for every resource area;
- API errors per the D-044 classes: Woo unavailable, authentication
  failure, validation failure, duplicate resource, conflicting
  resource, timeout-before-response, ambiguous timeout (write happened,
  response lost), rate limiting, partial response, malformed response,
  partial batch success;
- duplicate-response and duplicate-delivery scenarios for D-027
  testing.

Boundary rule (RULES §35 provider pattern): the mock and the real
adapter implement one interface; business logic, sync contracts, and
tests are written against the interface — the real adapter is a
drop-in replacement. **No connection to any real WooCommerce instance
is created in this batch or in the mock.**

## 10. Price-projection test environment (D-048 verification)

Deterministic local tests asserting that the canonical D-024/D-025
resolution is **materialized into the mock Woo display fields**
(`sale_price`/`regular_price` per D-048 Option A) for every case:

| # | Canonical inputs | Expected canonical resolution | Asserted Woo projection |
| --- | --- | --- | --- |
| 1 | valid variant sale | variant sale | variation `sale_price` = variant sale; base fields untouched |
| 2 | valid product sale, no variant override | product sale on list | displayed price = product sale |
| 3 | variant override, no sales | override | variation `regular_price` = override |
| 4 | list price only | list | product `regular_price` = list |
| 5 | **product sale + variant override, no variant sale** (the D-048 divergence case) | product sale applied to the override | displayed = product-sale-adjusted override — **not** the bare override (this is exactly what Option A fixes) |
| 6 | variant sale + product sale | variant sale wins (D-024 rule 4) | displayed = variant sale |
| 7 | expired product sale (+ override) | expired ignored → override | displayed = override |
| 8 | expired variant sale (+ product sale) | product sale | displayed = product sale |
| 9 | invalid sale (sale ≥ base) | rejected at validation | nothing written; error surfaced (never clamped) |
| 10 | missing base/list price | **unresolved** (D-024 rule 5) | nothing written; surfaced; never guessed |
| 11 | zero / negative effective price | invalid | rejected |

Also asserted: expiry re-projection (case 7/8 after the validity end
passes → scheduled deterministic re-projection, bounded logged window);
**canonical input values are never modified to satisfy Woo fallback
behaviour** (D-048 §1.4.2); every projection is a Red-tier write inside
a human-promoted flow with a D-027 event.

## 11. Local media (D-049 local equivalent)

Options: local filesystem directory vs **S3-compatible object-storage
emulator** vs direct Woo media library.

- Direct Woo media: rejected even locally — it would contradict the
  approved D-049 direction (external/object storage + Woo references)
  and bake a second pattern into the code.
- Plain filesystem: workable but loses the object-API surface the real
  provider (Phase 4) will present.
- **Recommended: S3-compatible emulator** (e.g. MinIO) in the Compose
  stack: the same API surface as the future real provider; the adapter
  boundary means swapping emulator → real provider later changes only
  endpoint/credential configuration — never business logic (RULES §35).

File identity/duplicate prevention: content-hash dedupe at
implementation (D-049 notes); Woo holds references (featured + gallery
per D-040); binaries never stored in Git; no real provider selected;
**D-056 Approved** — the emulator choice is part of the approved local
stack approval, the production provider stays Phase 4/owner-gated.

## 12. n8n local architecture (D-042/D-047 orchestration surface)

Conceptual workflows only — **no workflow is created** (n8n foundation
remains Phase 5; `TODO.md` keeps it blocked):

| Workflow (concept) | Deterministic logic | AI role | Human role | Woo execution |
| --- | --- | --- | --- | --- |
| product import | Excel validation pipeline (D-028/D-033) → dry-run report | none | reviews dry-run; promotes | none |
| canonical write | writes validated records to canonical DB post-promotion; D-026 provenance | none | promotion | none |
| Woo projection | registry lookup → payload build (D-047) → write → read-back | none | promotes the run | yes |
| price projection | D-024/D-025 resolution → D-048 materialization; scheduled expiry re-projection | none | promotes price-affecting runs (Red) | yes |
| media processing | reference → local object store → Woo reference (D-040) | alt-text drafts (Yellow, queued) | promotion | yes |
| event handling | D-027 keying, status transitions | none | — | — |
| retry | D-044 classes: bounded retry for retryable; read-back reconciliation for ambiguous | none | — | yes (retry) |
| conflict handling | D-044/§6 class detection → review queue | may analyze/summarize | **decides** | none |
| human approval | approval step gating Red operations (D-050) | may prepare/summarize | approves | only after approval |
| error notification | alert on failure classes (RULES §24) | may draft summaries | reads | none |

Hard separation: deterministic workflow logic, AI proposal logic,
human approval, and Woo execution are distinct stages; **AI never
silently executes Red operations** (D-050/RULES §32) and never sits in
the execution path of a Red step.

## 13. AI runtime boundary (local)

AI may (Yellow tier, provenance-tagged `AI_GENERATED`, human review
before exposure): enrich product descriptions; propose categories/
attributes/SEO content; analyze errors; suggest actions (RULES §32,
foundation doc §15 — unchanged). AI may **not**: invent SKUs, Product
IDs, Variant IDs, prices, stock, order/payment/shipping facts; create/
activate/modify/delete controlled vocabulary; publish; change prices;
execute lifecycle transitions; silently resolve conflicts; execute Red
operations (§12; D-050).

Local treatment: the AI runtime is **stubbed/mocked** until Phase 7 —
no AI provider is selected (register row 9 open), no AI credentials
exist or are requested, no real AI calls occur in the local stack. The
AI boundary is enforced structurally (separate proposal stage, §12),
not by prompt discipline alone (RULES §33: validate AI output before
it affects business systems).

## 14. Excel import local testing (`product-master.xlsx`)

Fixture workbook with exactly the approved sheets **محصولات / تنوع‌ها /
راهنما / گزینه‌ها** (D-033) and the approved values only. Test matrix
(D-028 semantics): valid import; invalid row; duplicate Product ID;
duplicate Variant ID; duplicate SKU; wrong category hierarchy (leaf
under wrong primary); invalid color; invalid size family; size not in
selected family; invalid price (string/non-numeric/sale ≥ base/zero/
negative); `نامشخص` → UNKNOWN surfaced, non-blocking (D-021); blank →
NOT_PROVIDED; partial failure = **no write** (D-028); dry-run writes
nothing; human promotion required; re-import — identical event →
`skipped_duplicate` (D-027), same identifiers + changed values → new
event + human-visible diff, duplicate variant combination rejected
(D-014 rule 11). The template file itself and the import runner are
**safe local scaffolding after the pending approvals** (§22); no
production import exists.

## 15. Testing strategy (extends D-052)

Layers: 1 unit tests (canonical rules) · 2 schema/validation tests ·
3 mapping-registry tests (uniqueness/lookup/stale/orphan/conflict) ·
4 price-resolution tests (§10 matrix) · 5 idempotency tests (D-017 +
D-027, §8) · 6 mock Woo tests (§9) · 7 n8n workflow tests (deterministic
nodes; Phase 5+) · 8 integration tests (import → canonical → mock Woo)
· 9 end-to-end local tests (workbook in → store projected, human
promotion steps included) · 10 failure-injection tests (every D-044
class; RULES §23 list).

**Reset strategy:** one documented destroy/recreate flow — tear down
the Compose stack, wipe named volumes, recreate from seed fixtures
(canonical data, registry seed, vocabulary seed, fixture workbook).
Safe because every store is local and fixture-derived; destructive
reset is **impossible to point at** staging/production (different
environment files, different hosts; reset tooling is local-only, §18).

## 16. Local test data (fictional, deterministic)

Fictional products only; **only D-031/D-032 approved vocabulary** is
used (no new colors/sizes/categories; no aliases; no equivalence). All
fixture identifiers are created by the seeding tooling (approved
deterministic tooling, local only) — fixture data is not a new ID
authority (D-017 unchanged):

- `P90001` — simple product (zero active axes)
- `P90002` — color-only variable product
- `P90003` — size-only variable product (Numeric family)
- `P90004` — color + size variable product
- `P90005` — multiple colors on one product
- `P90006` — size-family coverage across products (Numeric + Pants
  Waist, family-scoped distinction exercised)
- `P90007` — discounted product (valid product-level sale, D-024/D-025)
- `P90008` — variant price override product
- `P90009` — conflicting fixture (duplicate SKU scenario for §15 layer
  10)
- `P90010` — invalid fixture (invalid color → vocabulary rejection
  path)

Plus per-case price fixtures for the §10 matrix. Fixtures are named,
documented, and never real business data.

## 17. Observability (local)

Structured JSON logs; every important operation exposes: correlation/
event ID (D-027), operation, source system, entity reference (Product
ID/Variant ID/registry entry), status, error class (D-044), timestamp
(RULES §27 fields). Local aggregation = compose logs + per-service
files (not in Git). **Never logged:** API secrets, tokens, passwords,
credential references' values, personal customer data (none exists
locally by design). Log format is part of the promotion contract (§19);
aggregation/alerting differs per environment (Phase 22).

## 18. Local security baseline (D-045 applied)

- `.gitignore` (to be added with the scaffolding): `.env.local`,
  `.env.staging`, `.env.production`, secrets/, media/volumes, Woo
  uploads, logs. Only `.env.example` is committable.
- Secret separation: local credentials are throwaway, per-environment,
  reference-based (D-045 §12); least privilege (local Woo key scoped
  to the sync flows; n8n local auth).
- Localhost-only published ports; services communicate on the internal
  Compose network; no service exposed beyond the machine.
- No real customer data, no real payment data, no production
  credentials, no production webhook endpoints — none exist and none
  may be created locally (RULES §18).
- Safe test reset per §15; destructive resets limited to local volumes.
- Exposure of any future secret → STOP and report (RULES §16).

## 19. Environment promotion contract (D-053)

**Must remain identical across local/staging/production** ("change
configuration, not business logic"):

- business rules = the decision set D-001–D-052 (plus any later
  owner-approved decisions) — identical;
- canonical schemas/contracts = DATA_MODEL §13 logical model and its
  physical realization (if D-055 is approved) — identical;
- sync/CRUD/idempotency/conflict contracts = D-042/D-044/D-046/D-047/
- D-048 Option A projection behaviour — identical;
- validation pipelines and authority tiers (Green/Yellow/Red, D-050) —
  identical;
- adapter interfaces (Woo adapter, media store, future providers,
  RULES §35) — identical;
- logging record format (§17) — identical.

**Allowed to change per environment:** URLs/endpoints; credentials
(per-environment, reference-based); storage provider (local emulator →
real Phase 4 provider); test/seed data (local fixtures only — never
promoted); observability settings (log level/destinations; Phase 22);
environment flags; resource sizing.

Promotion gates: local green (§15 layers 1–9) → human review of the
test report (D-052 layer 10) → staging with isolated real Woo +
throwaway credentials (RULES §18) → owner approval → production
(Phase 4; RULES §43). No redesign at any step.

## 20. Decisions recorded (this batch)

| ID | Decision | Status |
| --- | --- | --- |
| **D-053** | Local-first development environment + Local → Staging → Production promotion model | **Approved** (2026-09-13, owner directive "explicitly LOCAL-FIRST"; directly implements RULES §18/§43, MASTER_PLAN §11, D-013) |
| **D-054** | Local runtime technology: Docker Compose stack (WordPress+Woo, Woo DB, canonical DB, n8n, media emulator, mock adapter; named volumes; localhost-only) | **Approved** (2026-09-13, owner) |
| **D-055** | Canonical project data storage: relational application database (PostgreSQL) holding canonical data + mapping registry + event store + provenance as separate schemas | **Approved** (2026-09-13, owner) |
| **D-056** | Local media: S3-compatible object-storage emulator behind the D-049 adapter boundary (real provider stays Phase 4, owner-gated) | **Approved** (2026-09-13, owner) |

Nothing is marked Approved beyond what the owner has already directed
or directly supported by existing approved decisions.

## 21. TODO and documentation

`TODO.md` gains the Batch 3 section (design completed; implementation
items queued behind the D-054–D-056 approvals). `DATA_MODEL.md` notes
the local-environment design and the D-055 proposal in its status and
open-decisions rows. `docs/glossary.md` gains the new Batch 3 terms.
`docs/README.md` indexes this document.

## 22. Implementation boundary

- **A. Design only (this batch, done):** everything in this document.
- **B. Safe local scaffolding (after D-054–D-056 approval):** Compose
  file + `.gitignore` + `.env.example`; canonical schema + seeding of
  registries/fixtures; mock Woo adapter; local media emulator config;
  price-projection test harness; Excel fixture workbook + test matrix;
  logging scaffolding; reset tooling.
- **C. Implementation deferred:** real Woo connection (after staging
  gate); real media provider (Phase 4); n8n workflow creation
  (Phase 5); AI runtime (Phase 7); inventory flows (D-016.I open);
  production hosting/DNS/SSL/backups (Phase 4); payment/shipping/
  Instagram (their phases).
- **D. Owner approval required before Batch 4:** D-054 (Compose
  stack), D-055 (canonical database), D-056 (media emulator) — then
  scaffolding may begin. No real WooCommerce connection, no real n8n
  production deployment, no real credentials, no production hosting,
  no real customer/payment/order data at any point.

## References

- Batch 1 foundation: `docs/phases/phase-03-1-woocommerce-foundation.md`
  (D-034–D-045); Batch 2 sync architecture:
  `docs/phases/phase-03-2-woocommerce-sync-architecture.md`
  (D-046–D-052)
- `MASTER_PLAN.md` §3, §10–§11, §13 (Phases 3–5), §16;
  `PROJECT_RULES.md` §5, §14–§18, §22–§27, §32, §35, §41, §43–§44
- `DECISIONS.md` — D-003, D-006, D-007, D-010, D-013, D-014–D-052,
  D-053–D-056 (this batch)
- `DATA_MODEL.md` §13 (logical model, authority, deferred boundary);
  `docs/phases/phase-02-5-excel-master-template.md` (D-033 workbook)

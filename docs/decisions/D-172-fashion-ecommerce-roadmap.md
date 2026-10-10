# D-172 — Fashion E-Commerce & Social Publishing Track (roadmap adoption)

- **Decision ID:** D-172
- **Title:** Fashion E-Commerce & Social Publishing track — adoption of the Fashion E-Commerce roadmap
- **Status:** **Approved**
- **Authority:** Mohammad (مالک پروژه — تنها مرجع تصویب، `PROJECT_RULES.md` §3)
- **Date:** 2026-10-10
- **Scope:** project scope **expansion** (owner-directed): a full fashion/apparel
  storefront, merchant admin panel, fashion AI copywriting engine, and
  multi-channel social automation
- **Siblings:** `DECISIONS.md` (ledger register row 73),
  [`docs/roadmap/FASHION_ECOMMERCE_ROADMAP.md`](../roadmap/FASHION_ECOMMERCE_ROADMAP.md),
  `MASTER_PLAN.md` §13 / §16, `TODO.md` §Forward previews

---

## 1. Decision summary

By explicit direction and approval from the owner, the project scope is expanded
to incorporate a full-fledged **Fashion & Apparel E-Commerce storefront**,
**Merchant Admin Panel**, **Fashion AI Copywriting Engine**, and **Multi-Channel
Social Automation** (Telegram / Instagram).

`docs/roadmap/FASHION_ECOMMERCE_ROADMAP.md` is adopted as the **authoritative
single source of truth** for the E-Commerce & Social Publishing track: its six
phases, its database schema, its API contract set and its UI/UX requirements
govern all subsequent work on that track, and every future development prompt on
the track must cite the roadmap's Phase and Section so that drift from the
approved specification is visible immediately.

This decision **records and adopts a plan**. It authorizes **no execution**: it
provisions nothing, installs nothing, connects nothing and deploys nothing.

## 2. What is adopted (scope of the roadmap)

| Phase | Track deliverable |
| --- | --- |
| Phase 1 | Database Architecture & Fashion Catalog Core — categories, products, product_variants (color/size matrix, `sku`, per-variant stock, price override), product_images, orders / order_items / customers |
| Phase 2 | Merchant Admin Panel (mobile-first) — multi-image ingestion with compression, matrix variant generator, inline stock/price grid, low-stock badges, order status transitions + tracking code, printable packing slip, coupon/discount management |
| Phase 3 | Customer Storefront (Next.js Server Components) — collections and carousels, faceted size/color/price/availability filtering, PDP gallery with per-color image switching, per-variant size disabling, size-chart modal, slide-over cart, OTP phone checkout, shipping-method selection |
| Phase 4 | Fashion AI Engine & Copywriting Hub — caption generation with tone presets (Luxury / Casual / Trendy), Telegram announcement text, SEO meta description and web copy, plus hashtag/trend intelligence |
| Phase 5 | Multi-Channel Social Automation — Telegram photo-album post assembly with an inline buy button; Instagram Graph API container publishing with a peak-hours scheduling queue |
| Phase 6 | Payment, Notification & Production Launch — Iranian payment gateway adapter with callback verification and idempotent order update, SMS adapter (OTP / order confirmation / tracking), containerized build verification, staging readiness and production cutover checklist |

The roadmap's derived **API contract set** (AC-1…AC-10) and **UI/UX
requirements** are recorded in the roadmap document itself.

## 3. Authority boundaries preserved (unchanged by this decision)

- **No execution authority.** Nothing is provisioned, installed, connected,
  configured or deployed; no phase is started.
- **No credentials.** No live payment, SMS, Telegram, Instagram, AI or storage
  credential exists or is requested (D-045); provider selection stays with the
  owner (open decisions 9/10/11 + the new SMS selection).
- **Production activation** remains the sole owner-gated act (D-139).
- **SSOT and event integrity.** The engine/plane never becomes an authority; no
  direct SSOT write from a presentation surface; event-level idempotency
  (D-026/D-027) and the canonical order lifecycle (D-081–D-084) stand.
- **Zero-leak discipline.** Deep redaction of credentials, tokens, PAN and
  customer PII (D-114/D-124); memory/log copies carry publications only.
- **Money.** Integer Iranian Toman (D-010); no floating-point money anywhere.
- **Channel reuse, not duplication.** Publishing continues on the existing
  Instagram (D-069–D-072), Telegram (D-073–D-076) and fan-out (D-077–D-080)
  seams; the roadmap adds copy generation and scheduling, not a second dispatch
  path.
- **Portability.** Provider-neutral seams are retained so storage, database,
  AI and channel providers stay swappable (D-129–D-132, Phase 24).

## 4. Owner sub-decisions — G-1, G-2 and G-3 RESOLVED (2026-10-10)

The scope expansion touched standing decisions. Per `PROJECT_RULES.md` §2 step
10 and §4 they were recorded as **open** at adoption; the owner has now ruled,
and the rulings are recorded here rather than left in the roadmap alone.

| # | Sub-decision | Status |
| --- | --- | --- |
| G-1 | Catalog source of truth | **RESOLVED — owner ruling 2026-10-10** |
| G-2 | Supabase vs the canonical PostgreSQL (D-055) | **RESOLVED — owner ruling 2026-10-10** |
| G-3 | Drizzle/Prisma vs the canonical data layer | **RESOLVED — owner ruling 2026-10-10** |
| G-4 | Provider selections (payment 10, shipping 11, SMS, AI 9) | **OPEN** — owner act, live credentials do not exist (D-045) |
| G-5 | Storefront media storage | **OPEN** — not blocking: Phase 1 keeps the columns provider-agnostic |
| G-6 | Channel publishing on the canonical seams | **OPEN as a build-time constraint** — publishing must keep using D-069–D-072 / D-073–D-076 / D-077–D-080 |

### 4.1 G-1 — catalog SSOT (RESOLVED)

**Owner ruling (Mohammad, 2026-10-10):** the native PostgreSQL / Supabase schema
defined in [`docs/roadmap/FASHION_ECOMMERCE_ROADMAP.md`](../roadmap/FASHION_ECOMMERCE_ROADMAP.md)
is hereby designated the **sole Authoritative Single Source of Truth (SSOT)** for
the Fashion E-Commerce track. The previous dependency on WooCommerce as the
ecommerce SSOT (**D-003**) and the related legacy sync patterns (D-034–D-048)
are **SUPERSEDED for this track**.

Scope of the supersession, stated rather than assumed:

- The supersession is **scoped to the E-Commerce & Social Publishing track**.
  It is recorded as a dated amendment, never an erasure (`PROJECT_RULES.md` §2.1);
  D-003's historical row is left intact and has been annotated with a pointer to
  this ruling so no reader meets a silent contradiction.
- The roadmap's Phase 1 tables are therefore the **owning** catalog model — not a
  projection, and not a parallel store.
- **Nothing is dismantled.** No WooCommerce code path, mapping registry or sync
  contract is removed, disabled or refactored by this ruling; the deployed Stage
  B stack is untouched. Retiring the WooCommerce integration itself is a
  separate owner decision this ruling does not take.
- Any future WooCommerce bridge must be authored as an explicit, one-way
  integration against this SSOT — never as a second source of truth.

### 4.2 G-2 — database instance (RESOLVED)

**Owner ruling:** the fashion schema lives on the **canonical PostgreSQL
instance** (D-055); **Supabase is a hosting choice for that one instance, not a
second database**. The single-SSOT rule stands, and the local-first promotion
model (D-053) with local parity still binds: the local container stack remains
the development target, staging and production are reached by promotion, and no
environment may diverge in schema.

The track's tables occupy their own `commerce` namespace inside that instance,
so the engine's schemas (`canonical`, `registry`, `events`, `provenance`, `oms`,
`hitl`, `admin`, `analytics`, …) and the fashion catalog are addressable and
blast-radius separated without a second database.

### 4.3 G-3 — schema and migration authority (RESOLVED)

**Owner ruling:** schema definitions and migrations for this track are managed
with **Drizzle ORM** against the canonical PostgreSQL/Supabase instance,
aligned with D-055 and clean database-management principles.

Recorded boundary with the existing data layer (no overlap, one database):

- Drizzle owns the **`commerce` namespace** — its schema, its migrations and its
  generated SQL. `drizzle.config.ts` pins `schemaFilter: ['commerce']` so a
  fashion migration can never render against, or mutate, an engine schema.
- The engine schemas stay owned by `local/db/schema.sql` (D-055) and are applied
  by `local/scripts/apply_schema.py`; this track does not adopt them and does not
  edit them.
- Migration history is committed (generated SQL + journal) so no environment can
  drift unnoticed; applying a migration to any shared environment remains an
  owner-gated act (D-045/D-139).

### 4.4 Remaining open items

- **G-4 — provider selections** (payment decision 10, shipping decision 11, SMS
  provider, AI provider decision 9) remain owner acts; the roadmap names
  candidates only and no credential exists or is requested.
- **G-5 — storefront media storage.** Phase 1 deliberately keeps the contract
  provider-agnostic: `product_images` carries `storage_path` + `public_url` and
  nothing in the code binds a storage SDK, so the D-049/D-056 direction and the
  Phase 24 `MediaStoreContract` swappability (D-129–D-132) are preserved until
  the owner selects a provider.
- **G-6 — channel publishing.** Unchanged as a build-time constraint: publishing
  keeps using the canonical seams (D-069–D-072, D-073–D-076, D-077–D-080) so
  there is exactly one dispatch path per channel.

No item in this list may be resolved silently; each requires its own owner
ruling, recorded as a dated amendment.

## 5. Deliverables in this change

| Artifact | Change |
| --- | --- |
| [`docs/roadmap/FASHION_ECOMMERCE_ROADMAP.md`](../roadmap/FASHION_ECOMMERCE_ROADMAP.md) | **New** — the adopted roadmap (architecture, Phase 1 schema, Phases 1–6, derived API contract set AC-1…AC-10, UI/UX requirements, governance alignment) |
| [`docs/decisions/D-172-fashion-ecommerce-roadmap.md`](D-172-fashion-ecommerce-roadmap.md) | **New** — this companion record |
| `DECISIONS.md` | Ledger register row 73 appended (append-only; existing rows untouched) |
| `MASTER_PLAN.md` | §13 work-package reference + §16 completed-track entry naming the roadmap as the authoritative execution plan for the E-Commerce & Social Publishing track |
| `TODO.md` | Forward-preview entry pointing at the roadmap and the standing owner gates |
| `docs/README.md` | Documentation index row for `docs/roadmap/` |

Nothing else was changed: no code, no manifest, no schema, no dependency, no
environment file, no credential.

### 5.1 Phase 1 implementation — `commerce/` (2026-10-10, same day, owner-authorized)

After the G-1/G-2/G-3 rulings the owner authorized immediate Phase 1 execution
(roadmap §1.1–§1.5). The data core is a new `commerce/` package — the E-Commerce
track's own home, kept separate from `control-plane/` because the control plane
is a read-only presentation surface and must never own the SSOT (D-171 §2.1):

| Artifact | Purpose |
| --- | --- |
| `commerce/src/db/schema/{schema,enums,catalog,ordering,relations,index}.ts` | Drizzle table/enum/relation definitions for `categories`, `products`, `product_variants`, `product_images`, `customers`, `orders`, `order_items` in the `commerce` namespace |
| `commerce/src/contracts/{catalog,ordering,index}.ts` | Typed read models, raw insert models and write payloads for every entity (§1.1–§1.5) |
| `commerce/drizzle/0000_sharp_ogun.sql` + `drizzle/meta/*` | The generated migration and its journal (committed history) |
| `commerce/src/db/index.ts` | Inert client factory — no connection string, no connection at import, fails closed when called without one |
| `commerce/drizzle.config.ts`, `commerce/package.json`, `commerce/tsconfig.json`, `commerce/.env.example`, `commerce/README.md` | Toolchain, scripts and the environment contract (placeholders only) |

Roadmap fidelity notes: nullability follows the roadmap's explicit `nullable`
markers, with absence inferred only where the lifecycle requires it
(`orders.payment_ref_id`, `orders.tracking_code`); money and stock are integers
(`bigint` Toman, D-010); a plain UNIQUE already is an index, so §1.1/§1.2's
"unique, index" is realised once, not twice.

### 5.2 Phase 2 implementation — merchant admin panel (2026-10-10, same day, owner-authorized)

Phase 2 (roadmap §2.1–§2.4) is delivered inside the same `commerce/` package as
the track's admin surface, on the D-171 §3 design system (one token layer, RTL
Persian-first, `next/font`-self-hosted Vazirmatn, the same raw-hex ESLint gate,
non-colour-dependent state as tone + Persian label + Latin status code).

| Artifact | Purpose |
| --- | --- |
| `commerce/src/app/{layout,globals.css,page}.tsx`, `commerce/src/app/admin/**` | The panel shell and its five routes (`/admin`, `/admin/products/new`, `/admin/inventory`, `/admin/orders`, `/admin/orders/[id]/slip`, `/admin/promotions`), all `force-dynamic` |
| `commerce/src/components/admin/variant-matrix-generator.tsx`, `image-uploader.tsx`, `product-ingestion-form.tsx` | §2.1 smart ingestion: colour × size matrix, browser-side compression with aspect-ratio locking, order/primary media, one submit |
| `commerce/src/components/admin/inventory-workspace.tsx` | §2.2 inline stock/price grid with threshold badges and low/out/inactive filters |
| `commerce/src/components/admin/order-workspace.tsx`, `packing-slip.tsx`, `print-button.tsx` | §2.3 status transitions, tracking-code modal, printable packing slip |
| `commerce/src/components/admin/coupon-manager.tsx` | §2.4 promotions: PERCENT/FIXED, min spend, expiry, usage limit, activation |
| `commerce/src/lib/{variant-matrix,inventory-rules,order-rules,coupon-rules,validation,format,color-palette,image,utils}.ts` | The PURE rules and display helpers, shared by the browser and the server so a badge, a dropdown option and a refusal can never disagree |
| `commerce/src/server/{repository,repository-memory,db-context,media}.ts` | The persistence seam (one Postgres implementation + a deterministic test double), the fail-closed connection gate and the media seam |
| `commerce/src/server/services/{products,inventory,orders,coupons}.ts` + `commerce/src/server/actions/*.ts` | The four services (validating, repository-injected) and their server actions |
| `commerce/src/lib/color-palette.ts` | The apparel colour palette as CATALOG DATA (the only JS/TS file the raw-hex rule exempts, because a garment colour is not a design token) |
| `commerce/drizzle/0001_right_rocket_racer.sql` + `drizzle/meta/0001_snapshot.json` + `_journal.json` | The §2.4 storage migration: the `commerce.discount_type` enum and the `coupons` table (12 columns, UNIQUE code, 6 CHECK constraints, 2 indexes) |
| `commerce/{eslint.config.mjs,next.config.mjs,postcss.config.mjs,tsconfig.test.json}` + `commerce/test/*` | Toolchain and the native `npm test` harness (no new dependency: `tsc` → `.test-build/`, `node --test`, a resolution hook) |

Roadmap fidelity and the two honest limits:

- **§2.3 tracking code → “automated SMS trigger to the buyer”.** The SMS adapter
  is a Phase 6 deliverable and **G-4 is still OPEN**, so recording the code is
  implemented and the notification is NOT faked: the panel states after a
  successful save that the SMS is not yet active.
- **§2.1 image upload.** **G-5 (media storage) is still OPEN**, so the uploader
  compresses, previews, orders and primary-flags in the browser, and
  `src/server/media.ts` resolves to `null`; a submission carrying pending image
  bytes is **REFUSED with its reason** instead of creating a product whose
  gallery points at nothing. A merchant can attach an externally hosted image by
  path + URL today, and a product with no images is created normally (media is
  optional, §1.4).
- **Coupons have no dedicated §1 table.** As with the media contract, §2.4's
  coupon table is derived from the roadmap section that requires it and is owned
  by Drizzle in the `commerce` namespace — schema in `db/schema/promotions.ts`,
  migration `0001` (enum + table + constraints + indexes) committed so no
  environment can drift silently (G-3); the redemption arithmetic stays in the
  Phase 3/6 checkout write path and must be idempotent per order (D-027).
- **Display state is derived, never stored.** Low-stock badges, coupon states
  (`ACTIVE`/`INACTIVE`/`EXPIRED`/`EXHAUSTED`) and packing-slip totals are
  computed at read time, so an expired coupon or a drifted order total cannot be
  rendered as something it is not.
- **Fail-closed panel.** With no `DATABASE_URL` every route states that nothing
  is connected (`DB_NOT_CONFIGURED`) instead of rendering zeros that would read
  as measurements; the deterministic in-memory repository is a TEST DOUBLE only
  and is wired into no route.

## 6. Verification performed

**Adoption change (2026-10-10):**

- The roadmap document contains all six phases, the Phase 1 schema, the API
  contract set and the UI/UX requirements, and it is reachable from
  `MASTER_PLAN.md`, the ledger and the documentation index.
- The ledger's register table remains a valid table and its existing content is
  unchanged apart from the appended row (append-only discipline, §2.1).
- Repository documentation checks that read `DECISIONS.md` still pass
  (`local/tests/test_phase6_notion_m2.py` — 24/24, exit 0).
- Tree hygiene: committed as one atomic documentation commit, tree clean after.

**Phase 1 implementation (2026-10-10):**

- `npm run typecheck` (`tsc --noEmit`) — **exit 0**, no diagnostics.
- `npm run db:generate` — **exit 0**, exactly the seven roadmap tables
  (categories 7 cols, products 14, product_variants 9, product_images 7,
  customers 7, orders 11, order_items 5) with their indexes and foreign keys.
- `npm run db:check` — **exit 0** (`Everything's fine`), migration journal
  consistent with the schema snapshot.
- **Live DDL validation against PostgreSQL 16.15** (the same `postgres:16-alpine`
  image the local stack uses, digest `sha256:cf78e766…`): the generated
  migration applied with `ON_ERROR_STOP` (exit 0) into a throwaway container with
  no published ports, yielding 7 tables, 2 enums, 80 constraints and 23 indexes
  in schema `commerce`. It then behaved as specified: defaults `DRAFT` /
  `PENDING` / `is_active` true / `is_primary` false; **ten refusal cases each
  refused** (stock < 0, base_price < 0, quantity = 0, duplicate matrix row,
  duplicate sku, duplicate product slug, duplicate customer phone, deleting a
  variant referenced by an order line, deleting a category in use, unknown
  column); and the deletion semantics verified — order → order_items CASCADE
  (1 → 0), variant → image `SET NULL` (image kept, binding cleared),
  product → variants + images CASCADE with the category retained. Container
  removed afterwards; nothing was provisioned, connected or left behind.
- Committed as one atomic commit with the working tree clean afterwards.

**Phase 2 implementation (2026-10-10):**

- `npm run verify` — `tsc --noEmit` **exit 0**; `eslint .` **exit 0 with zero
  warnings** (the raw-hex design gate included, exempting only the catalog
  colour palette, the payload fixtures and the specs that assert colour
  normalisation); `npm test` **91/91 pass, 0 fail** across 20 suites
  (`node --test` over compiled output — no test dependency added). Coverage is
  negative-first: money/stock/hex/slug/SKU/coupon bounds, instant parsing,
  duplicate SKU and duplicate colour × size refusal, single-primary enforcement,
  the matrix row ceiling, HTML escaping of merchant text, the four order
  transitions that must be refused, tracking only in `PROCESSING`/`SHIPPED`, the
  four derived coupon states, inventory badge/filter/summary thresholds, slip
  reconciliation (including the drifted case), and the fail-closed DB gate —
  including that a driver error message is never echoed to the panel.
- `npm run db:generate` — **exit 0**, generating `drizzle/0001_right_rocket_racer.sql`
  for exactly the one new table (`coupons` 12 columns, 2 indexes) plus the
  `discount_type` enum, leaving the seven Phase 1 tables untouched; `npm run
  db:check` — **exit 0** (`Everything's fine`), journal and snapshot consistent.
  The migration was **not applied to any environment** (no server available, and
  applying it anywhere shared remains an owner-gated act per D-045/D-139).
- `npm run build` — **exit 0**, seven routes as expected (`/`, `/_not-found`,
  `/admin`, `/admin/inventory`, `/admin/orders`, `/admin/orders/[id]/slip`,
  `/admin/products/new`, `/admin/promotions`), with the panel routes dynamic.
- **Browser verification** on the dev server (1280×900, `next dev`): the shell
  and all five admin routes render RTL Persian with the unconfigured-database
  banner and no fabricated rows; the matrix generator produced
  `MANTO-KETI-LENIN-36-1`, `MANTO-KETI-LENIN-38-1`, `MANTO-KETI-LENIN-36-2`,
  `MANTO-KETI-LENIN-38-2` from مشکی+کرم × 36+38 with editable SKU cells; the
  inventory grid showed `IN_STOCK`/`LOW_STOCK`/`OUT_OF_STOCK` with matching
  filter counts; the order list offered exactly `SHIPPED`/`CANCELLED` for a
  `PROCESSING` order and reported the shipped one as terminal; the tracking
  modal opened with its hint and both action buttons; both packing-slip states
  rendered (consistent totals, and the drift warning when the stored total
  disagrees); and all four coupon states rendered with their tone and Latin
  code. Each client→server-action path (stock, price, tracking code, coupon
  create) round-tripped through the real action and displayed the fail-closed
  refusal in its own row or banner — no optimistic success, no console errors.
- **Stated limits (not claimed as verified):** the environment had **no
  PostgreSQL server binary and no running Docker daemon**, so the Postgres
  repository implementation, the generated DDL and the `notFound()` 404 for an
  unknown order id are NOT live-verified in this change; the service layer is
  verified against the deterministic memory repository (which models identity,
  joins, mutations and counters, but not the database's CHECK/UNIQUE
  constraints — those remain Phase 1's live-DDL evidence), and no migration was
  applied to any environment. The browser pass ran against a fixture surface
  that was deleted before the commit; the shipped routes were re-verified in
  their fail-closed state after its removal.
- Tree hygiene: the temporary browser-verification route was removed, the dev
  server stopped, and nothing was provisioned, connected or credentialled.

## 7. References

- [`docs/roadmap/FASHION_ECOMMERCE_ROADMAP.md`](../roadmap/FASHION_ECOMMERCE_ROADMAP.md) — the adopted plan.
- `PROJECT_RULES.md` §2/§2.1/§3/§4, §37 (documentation must never become silently false).
- `MASTER_PLAN.md` §13 (Project Phases), §14 (Definition of Done), §16 (Current Status).
- Standing boundaries: D-003, D-010, D-026/D-027, D-034–D-056, D-045, D-069–D-092, D-114/D-124, D-129–D-132, D-139.
- Related tracks: D-141 (Dokploy), D-169/D-170 (Live Wiring closeout), D-171 (unified web control plane).

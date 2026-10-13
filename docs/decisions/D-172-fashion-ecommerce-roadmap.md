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
| `commerce/src/components/admin/order-workspace.tsx`, `packing-slip.tsx`, `print-button.tsx`, `commerce/src/components/ui/dialog.tsx` | §2.3 status transitions behind an irreversible-action confirmation, tracking-code modal, printable packing slip |
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
- **Every irreversible action is confirmed.** The roadmap's merchant-panel
  requirement asks for a confirmation on each irreversible action. In this
  lifecycle every transition is one-way (no back-edges, no self-transitions), so
  each status change opens a confirmation carrying the target state as a Persian
  label + Latin code, with cancellation in the destructive style; cancelling the
  dialog writes nothing. The copy claimed no audit record, because none was
  written yet (see the limitation below). **[Superseded 2026-10-13 — the Phase 4
  transition block appended to §6 added `order_status_history`, so an audit
  record IS written now and the copy states it; the sentence is left intact as
  history per §2.1 and its false half is corrected at the cause.**]
- **Display state is derived, never stored.** Low-stock badges, coupon states
  (`ACTIVE`/`INACTIVE`/`EXPIRED`/`EXHAUSTED`) and packing-slip totals are
  computed at read time, so an expired coupon or a drifted order total cannot be
  rendered as something it is not.
- **Fail-closed panel.** With no `DATABASE_URL` every route states that nothing
  is connected (`DB_NOT_CONFIGURED`) instead of rendering zeros that would read
  as measurements; the deterministic in-memory repository is a TEST DOUBLE only
  and is wired into no route.

### 5.3 Phase 3 implementation — customer storefront (2026-10-12, owner-authorized)

The customer half of the track, in the same `commerce/` package and on the same
design system. One structural change to the existing surface: the document shell
(`app/layout.tsx`) now owns only language, direction, font, tokens and the skip
link, and the merchant chrome moved to `app/admin/layout.tsx` — so a customer
never sees the merchant navigation and the storefront never shows the connection
badge (`robots: noindex` moved with it; the storefront is a public shop).

- **§3.1 Homepage & collections** — hero, category circles and three rails.
  Every rail is derived from a real read and hides itself when empty: «جدیدها»
  is the read path's own newest-first order, «پیشنهادهای تخفیف‌دار» are products
  that actually carry a discount price (a "featured" badge is never invented),
  and «پرفروش‌ها» is quantity shipped with cancelled orders excluded.
- **§3.2 Catalog & real-time filtering** — `catalog-browser` (client) filters by
  category, size, colour, price range, availability and free text, with sort and
  pagination; facets are DERIVED from the published cards, so a size nobody
  stocks is never offered, and the facet derivation, filtering, paging and the
  "nothing matched" copy are pure functions in `@/lib/catalog-filters` under
  test.
- **§3.3 Product detail page** — gallery viewer, colour selector that re-scopes
  the gallery to that colour's photos with the product gallery as the fallback
  (never an empty gallery), colour × size matrix with out-of-stock variants
  disabled, stock as a LEVEL (raw quantities never reach the browser),
  centimetre size-chart modal, related products from the same category. The
  merchant's `description_html` is deliberately NOT rendered to customers — the
  description is rendered from `descriptionRaw` as escaped text, because
  sanitizing merchant-authored HTML is a separate decision and shipping it
  unsanitized would be a stored-XSS surface.
- **§3.2/§3.4 Cart** — a pure cart module (`@/lib/cart-rules`: merge, cap,
  remove, parse, serialize) plus an external store (`@/lib/cart-store`) read
  through `useSyncExternalStore`. `localStorage` is untrusted input, so the
  parser is fail-closed (malformed blob → empty cart, malformed line dropped,
  quantity clamped, duplicates collapsed) and the stored price is display data
  only. The store models storage as what it is — state React does not own — so
  the server render and the hydrating client render agree and a `hydrated` flag
  distinguishes "no basket yet" from "an empty basket" (the effect + `setState`
  shape this replaced was also a cascading render on every mount and is
  rejected by the project's lint gate).
- **§3.4 Checkout** — `checkout-form` validates the customer block with the same
  `@/lib/validation` rules the server applies, PRE-FLIGHTS the cart
  (`checkCartAvailabilityAction`, non-authoritative) and reports a price the
  server disagrees with before submitting, then calls `placeOrderAction`.
  Totals are computed server-side inside the transaction and the discount is
  never predicted by the browser. An order also CONSUMES the stock of its lines
  atomically in that same transaction, and a cancellation returns it exactly
  once, so the "last piece" cannot be sold twice — see §6 (this arrived with the
  live pass, not with the first cut of this phase).
- **§3.4 Payment adapter** — `src/server/payments/gateway.ts` defines the
  fail-closed gateway interface and `MockPaymentGateway`, which answers
  `UNAVAILABLE`; the order is written as `PENDING` and the customer is told
  nothing was charged. This is the seam the Phase 6 live provider plugs into
  (G-4 / open decision 10); no credential exists or is requested.
- **Open, stated rather than faked** — OTP verification is NOT implemented (SMS
  provider unselected, G-4; a mock code field would be worse than none), image
  zoom / swipe gestures and live payment capture remain Phase 6 work, and mobile
  gesture behaviour was not device-tested.

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
- **RTL modal centring (defect found and fixed during this pass).** The modal
  primitive centred itself with the logical `start-1/2` inset plus a physical
  `-translate-x-1/2`; in RTL that resolves to `right: 50%` and the transform then
  pushes the dialog further left — measured in the browser at `left: -128px`,
  i.e. partly off-screen and clipped. Centring is now physical
  (`left-1/2 -translate-x-1/2`), measured after the fix at `left: 384` / `right:
  896` in a 1280 px viewport (exact centre), close button inside the box, for
  both the status-change and tracking-code dialogs.
- **Merchant-panel confirmation (added after the first pass).** Selecting a
  status no longer writes immediately; it opens a confirmation whose copy comes
  from the pure `transitionConfirmation` rule (5 new tests: cancellation is
  destructive and states finality, forward moves confirm without the danger
  style, every reachable target is described, and the copy never implies an
  audit record). **[Superseded 2026-10-13: that last assertion was inverted when
  the record began to exist — the rule now NAMES the history it writes and must
  still promise nothing else; the sentence is left intact as history per
  §2.1.]** Browser-verified: choosing a status opens the dialog before any
  write, انصراف closes it with **no** message and no request, and confirming
  round-trips through the real server action (refused by the fail-closed gate)
  with the dialog closing so the refusal is visible on the row.
- **Remaining gap against the roadmap's merchant-panel requirement, stated
  rather than papered over:** the confirmation half is implemented, the
  **auditable record is not** — a status change only moves the row's
  `updated_at`, and the `commerce` namespace has no audit table (§1 enumerated
  none, and enrolling the track in the engine's canonical provenance
  (D-026/D-027) is a schema decision, not an inference). The confirmation copy
  says exactly that. Likewise the low-stock threshold is currently the
  `LOW_STOCK_THRESHOLD` constant plus a per-product override seam, not yet
  merchant-configurable. **[Half of this gap CLOSED 2026-10-13 by the Phase 4
  transition block appended to §6: migration `0002` adds
  `commerce.order_status_history` and every status change now appends its
  record (previous status, new status, actor, time) in the same transaction, so
  the "auditable record is not implemented" half no longer holds and the
  confirmation copy states the record instead. The block's own text is left
  intact as history per §2.1. Still open from it: the low-stock threshold, and
  the engine-provenance question (D-026/D-027), which this work neither made nor
  implied — the trail is a track-local table.]**
- Tree hygiene: the temporary browser-verification routes were removed, the dev
  server stopped, and nothing was provisioned, connected or credentialled.

### Phase 2 hardening — live PostgreSQL pass (2026-10-10, owner-authorized)

**Why:** §6 above recorded an explicit limitation — Phase 2's writes were verified
against the in-memory repository and unit-level rules, but never against a live
PostgreSQL instance. That gap is now closed with a re-runnable harness, without
changing any infrastructure stage and without a credential of any kind.

**Harness (opt-in by construction):** `commerce/docker-compose.db.yml` —
PostgreSQL **16.15** (`postgres:16-alpine`, the same version and image Phase 1's
DDL validation used; digest `sha256:721873c3…`, linux/arm64, versus the
`sha256:cf78e766…` Phase 1 recorded for the other architecture), own named
network and volume, published on **127.0.0.1:55432 only**, no `restart:` policy,
and no hook in the repository that starts it. Operator commands:
`db:up` · `db:down` · `db:migrate` · `db:reset` · `smoke:db`.

**Evidence — migrations 0000 + 0001 apply cleanly:**
`COMMERCE_DATABASE_URL=… npm run db:migrate` → *migrations applied successfully*;
`schema commerce` = 8 tables (the seven roadmap tables plus the §2.4 `coupons`
table) + 3 enums; Drizzle journal `drizzle.__drizzle_migrations` = 2 rows. The
smoke suite re-proves this on every run: it drops schema `commerce`, clears the
journal rows (the table itself is kept — dropping only `commerce` would leave
Drizzle believing 0000/0001 were applied while the namespace was empty), and
re-applies both migrations through the committed `drizzle/` folder.

**Evidence — the Postgres repository path, end to end:** `npm run smoke:db` →
**22/22 pass, exit 0, twice consecutively** (`# tests 22 · # pass 22 · # fail 0`).
The suite drives the REAL `createPostgresRepository` (never the memory double)
and reads every result back from PostgreSQL, so a service that reported success
without writing would fail it: category + product graph (4 variants, 2 images,
counts computed by PostgreSQL), inline stock and price edits (including
clearing an override), coupon creation with state DERIVED from the stored row
(`ACTIVE` → `INACTIVE` → `ACTIVE` → `EXHAUSTED`, `EXPIRED` taking precedence),
and the §2.3 lifecycle (PENDING → PAID → PROCESSING → SHIPPED with tracking
recorded, PENDING → CANCELLED, packing-slip totals reconciling against the
stored amount and flagging a deliberate drift).

**Evidence — refusals refuse:** each of these was executed live and refused by
the stated gate, with the stored row verified unchanged afterwards — stock < 0
(service validation AND `product_variants_stock_non_negative`, 23514),
`base_price` < 0 (service AND `products_base_price_non_negative`),
duplicate `(product_id, size, color_name)` (`product_variants_matrix_unique`,
23505), duplicate SKU (`product_variants_sku_unique`), duplicate coupon code
(service CONFLICT AND `coupons_code_unique`), PERCENT 0/150 (service AND
`coupons_percent_within_range`), `used_count` < 0
(`coupons_used_count_non_negative`), `quantity = 0`
(`order_items_quantity_positive`), an unknown status label (PostgreSQL 22P02),
and illegal/terminal transitions (PENDING→SHIPPED, a self-transition,
SHIPPED→CANCELLED) refused by `canTransition` with the row provably unmoved.

**Two real defects found by the live pass and fixed (they were invisible to the
in-memory double):**

- `listProducts()` reported `variantCount` = 0 and `imageCount` = 0 for every
  product, and `listOrders()` reported `itemCount` = 0 for every order. Drizzle
  renders column references inside a raw `sql` chunk **unqualified**, so the
  correlated subquery became `where "product_id" = "id"` — both names bound to
  the subquery's OWN table (`product_variants.product_id = product_variants.id`),
  a condition that is never true, while the rows sat in the table. Both read
  models now aggregate over LEFT JOINs (`count(distinct …)` so two one-to-many
  joins cannot multiply each other, `coalesce(sum(…), 0)` for an order without
  lines) and are pinned by live assertions in the suite.

**Fail-closed behaviour and guards, all measured:**
`COMMERCE_DATABASE_URL` absent → the suite SKIPs with a named reason and exit 0
(no target is guessed); a non-loopback target → SKIP with its named reason
(staging/production stay out of reach); `db:reset` — the one destructive command
— refused for `127.0.0.1:5432` (a canonical local instance), for
`staging.internal`, and with no URL, exiting 1 in each case, and acting only on
`127.0.0.1:55432`, where it dropped the 8-table schema, cleared the 2 journal
rows and re-applied both migrations.

**Separation and regression surface:** `npm run verify` exit 0 (typecheck, lint,
**97 tests / 23 suites**, `db:check`) with the live suite skipping by name; with
the harness up, `npm test` exit 0 (**119 tests / 28 suites**). `build` exit 0,
with `.next/static` containing no `createPostgresRepository`, `db-context`,
`drizzle-orm` or connection string (the server build contains them, so the check
is not vacuous). A new static boundary test fails any `'use client'` module that
value-imports `@/db` or `@/server` outside the `@/server/actions/*` edge, while
allowing the type-only imports the panel already uses.

**Boundaries honoured:** no Stage C, provisioning, staging or production step was
taken or changed; no credential was created, requested or introduced (the compose
password is the disposable container's own literal, published nowhere but
loopback); no migration was applied outside the disposable harness; the one
destructive command is guarded by loopback+port rather than by an environment
variable alone. This block is appended to §6 and rewrites none of its history;
`commerce/README.md`'s Phase 1-era "Not started: Phases 2–6" line was corrected
because Phase 2 is implemented and now live-verified (§37: documentation must
never be silently false).

### Phase 3 verification — customer storefront (2026-10-12, owner-authorized)

Appended to §6; nothing above is rewritten (append-only, §2.1).

**Static and unit surface.** `npm run verify` **exit 0** — `typecheck` no
diagnostics, `lint` **0 problems** (0 errors, 0 warnings), `npm test` **146
tests / 37 suites, 146 pass / 0 fail**, `db:check` "Everything's fine".
The 49 new tests are the pure modules and the new store: catalog facets,
filtering/paging and the "nothing matched" copy; cart merge/cap/remove and the
fail-closed `localStorage` parser (non-JSON, non-array, malformed lines dropped,
quantity clamped, duplicates collapsed, a hand-edited price parsed but never
trusted); money arithmetic and coupon eligibility; the centimetre size chart; the
shipping table incl. the refusal of an unknown method id; the payment gateway's
refusal paths; and the cart STORE against a stubbed `window` — server snapshot
empty, stable and never the live one, adoption of a stored basket through the
parser on the first subscription, every mutation persisted and notified, the
cross-tab `storage` event adopting another tab's basket while ignoring unrelated
keys, and a full clear emptying the basket.

**Boundary and bundle.** The client/server separation test still passes and now
covers the storefront tree (no `'use client'` module value-imports `@/db` or
`@/server` outside the `@/server/actions/*` edge). `npm run build` **exit 0**:
`/`, `/catalog`, `/checkout`, `/products/[slug]` all dynamic (`ƒ`, correct for a
shop whose stock and prices move), the four admin routes and the packing-slip
route intact, `/_not-found` static.

**Browser pass (dev server, 2026-10-12).** `/`, `/catalog`, `/checkout` and
`/admin` return 200 with `lang="fa"` and `dir="rtl"` on the document. With no
canonical connection configured, every data surface renders the fail-closed
notice and `/checkout` renders **no form at all**; the storefront header, cart
drawer and footer are present, and the admin shell states «تنظیم‌نشده» up front.
The cart was exercised end-to-end through the real UI: a basket seeded into
`commerce.cart.v1` was adopted after hydration (badge «سبد خرید، ۳ کالا»), the
drawer opened and listed the line with its display-only subtotal, and the
«افزودن یک عدد» control wrote quantity 4 back to `localStorage` while the badge
became ۴ — i.e. the store's persist-and-notify path, not just its render path.
The dev console was clean throughout (no hydration error, no warning).

**D-172 Phase 3 — hydration defence, verified at the mechanism.** The root
layout's `suppressHydrationWarning` on `<html>` and `<body>` (present in `HEAD`)
was re-checked against the installed React, because the failure mode it guards is
an extension injecting `cz-shortcut-listen` and similar attributes between HTML
parse and hydration. `node_modules/react-dom`'s `diffHydratedProperties`
contains the gate
`0 < extraAttributes.size && !0 !== props.suppressHydrationWarning &&
warnForExtraAttributes(...)` — the extra-attribute difference is reported
**unless that element's props** carry the flag (the gate is per element, not per
subtree, which is why it is set on both tags and nowhere else), and React 19.3's
hydration error text names "a browser extension installed which messes with the
HTML before React loaded" as one of its causes. The rendered markup carries the
flag on both tags (`suppressHydrationWarning: true` in the served HTML and flight
payload), and the browser console is clean.

**Attempted and INCONCLUSIVE (recorded, not claimed as a pass).** A local proxy
that injects `cz-shortcut-listen` into the served HTML — the extension scenario
itself — was built to A/B the console with and without the flag; the proxied
origin never hydrated under the Turbopack dev server (`window.__next_f` present,
no React fibre on any host node, controls inert), so the comparison produced no
signal either way. The mechanism-level proof above is what stands; the proxy was
not added to the repository.

**Container and test-stack state (this pass).** `npm run db:down` was attempted
and reported the Docker API unreachable (the Colima VM is not running), which is
consistent with the observed state: no `postgres`/`dockerd` process, no listener
on `127.0.0.1:55432` or `:5432`, no `engine-staging-*` container — there was no
test container to stop, and none is left behind. The harness remains strictly
opt-in by construction (no `restart:` policy, no hook in the repository runs
`db:up`; it is an explicit operator command only), and the live suite proved it
at runtime by SKIPPING with its named reason (`COMMERCE_DATABASE_URL not set — no
target is guessed; fail-closed`). The staging stack lives in
`local/infra/compose.staging.yml`, is referenced by no commerce script, test or
build path, and was not started or touched.

**Boundaries honoured:** no deployment, provisioning, connection, migration or
credential of any kind; no environment was changed; the one local service started
is the commerce dev server on loopback (plus the throwaway proxy, since killed);
the storefront renders fail-closed rather than an empty shop while the canonical
database is absent.

### Phase 3 live storefront pass — the funnel against real PostgreSQL (2026-10-12, owner-authorized)

Appended to §6; nothing above is rewritten (append-only, §2.1). This CLOSES the
gap the previous block recorded ("no live PostgreSQL was available in this
environment"), and it is the second live pass on this track after the Phase 2
hardening pass.

**Harness.** The local Colima VM was started for this pass only, then
`npm run db:up` → `commerce-db-harness-postgres` healthy → `npm run db:migrate`
applied both committed migrations to schema `commerce` on **PostgreSQL 16.15**
(schema = 8 tables, `drizzle.__drizzle_migrations` = 2 rows). Teardown is
recorded under "Boundaries" below. Tenancy target stayed where it belongs:
loopback only, `127.0.0.1:55432`.

**The suite.** `commerce/src/__tests__/live-db/phase3-storefront-live.test.ts`
drives the REAL repository through the whole customer funnel and asserts against
rows read back from the database, never against a service's word: §3.1 category
counts (a DRAFT product is never counted, listed or readable by slug) and the
rails; §3.2 facets derived from published ACTIVE variants only (a deactivated
variant disappears from sizes, colours and the matrix), category/size/colour/
price-range/availability filters, and search; §3.3 PDP levels (`IN`/`LOW`/`OUT`
derived from stored quantities), price resolution (override > discount > base),
the gallery order and the fact that **no raw quantity crosses the read model**;
§3.3/§3.4 the optimistic pre-flight (per-line level, availability and server
price, no write); §3.4 the real order — `PENDING` row, `order_items` with the
server-resolved unit price, coupon applied with its usage counter incremented in
the same transaction, Persian-digit phone/postal normalised to ASCII in the
customer row, `payment_ref_id` NULL; the refusals (empty cart, bad phone/postal,
unknown shipping method, unknown coupon, quantity above the per-line ceiling)
each with its own code and provably writing nothing. Evidence: `npm run smoke:db`
→ **41/41 pass, exit 0, twice consecutively** (22 Phase 2 + 19 Phase 3 subtests),
with each file resetting the schema and re-applying both migrations, so the run
is re-runnable by construction.

**Two REAL defects the live pass found — both fixed here, neither visible to the
in-memory double or to typecheck.**

1. **Every checkout failed at the row lock (SQLSTATE 42601).** `placeOrder`
   locked the variant rows with `for update of "commerce"."product_variants"`,
   and PostgreSQL refuses a QUALIFIED name in the `OF` list ("FOR UPDATE must
   specify unqualified relation names"). Drizzle renders this schema-bound table
   qualified, so the statement was a syntax error before it could write anything:
   the entire storefront checkout — the one path that must not fail — could never
   have succeeded against a real server, and the fail-closed wrapper reported it
   as a generic `UNEXPECTED`. Fix: the lock is taken with a SINGLE-TABLE
   `select … for update` on `product_variants` (no `OF` clause is needed to lock
   one relation), and the product columns the pricing needs are read in a second
   statement. Behaviour is unchanged — only variant rows are locked, so catalog
   rows stay writeable — and the live suite now exercises it on every run.
2. **Nothing consumed stock, so the last piece could be sold twice.** The
   availability check refused on a shortage but no write ever decremented
   anything; the only stock write path in the track was the merchant's absolute
   `updateStock`. The owner ruled on this pass: implement the reservation. An
   order now consumes stock **inside its own transaction** with a conditional
   `update … set stock_quantity = stock_quantity - n where id = … and
   stock_quantity >= n` — check-and-consume as ONE statement, backed by the
   column's `stock_quantity >= 0` CHECK — and a mismatch throws so the whole
   transaction rolls back into the ordinary `STOCK_INSUFFICIENT` refusal rather
   than committing a partial decrement. `updateOrderStatus(CANCELLED)` returns the
   order's lines in the same transaction, guarded by `previous !== 'CANCELLED'`,
   so a cancellation restocks exactly once. Coupon usage is deliberately NOT
   refunded on cancellation (the conservative direction for a discount counter),
   and that is asserted rather than left implicit. Both repository
   implementations carry the rule (the Postgres one plus the memory double, whose
   stored order lines now keep the variant binding the restock needs).

**Concurrency — the property the double cannot show.** For a variant with ONE
piece left, two orders were submitted simultaneously through the real service: the
row lock serialises them, the loser re-reads the committed stock and is refused,
and the database ends with exactly one order and zero stock. That test is in the
suite, so "atomic" is measured rather than asserted.

**Harness correction this pass required.** `phase3-storefront-live.test.ts` and
`phase2-live.test.ts` share ONE database and each resets it, so `smoke:db` now
runs the live directory with `--test-concurrency=1`; without it node:test runs the
two files in parallel processes and the second `drop schema` truncates the first
suite's fixtures mid-run.

**Offline half.** `commerce/src/server/services/checkout.test.ts` was added so the
reservation rule is not only proven against a server that has to be started by
hand: 9 tests over the in-memory double cover line normalisation, the totals, the
coupon counter, the reservation, the oversell refusal, the restock-exactly-once
rule, the refusals writing nothing, and a mock AUTHORIZED reference that still
leaves the order `PENDING`. `npm run verify` → **exit 0** (typecheck, lint **0
problems**, **155 tests / 40 suites**, `db:check`), with both live suites skipping
by name when `COMMERCE_DATABASE_URL` is absent; `npm run build` → **exit 0** with
the same eleven routes.

**Boundaries honoured on this pass:** the only services started were the local
Colima VM (for the harness) and the commerce dev server on loopback; the harness
was torn down with `npm run db:down` (container and network removed) and the VM
was returned to the **stopped** state it was found in. The `engine-staging-*`
containers came up on the Docker daemon's own `restart: unless-stopped` policy
when the VM booted; they publish **no host ports** (so they cannot shadow the
harness, `5432`, or a dev server), their restart policy was left alone — stopping
them by hand would have silently disabled that policy — and they went down with
the VM. No deployment, provisioning, migration outside the disposable harness, or
credential; nothing was pushed.

### Phase 3 CLOSE-OUT — reservation policy ratified, funnel guarded offline, inventory reconciliation asserted (2026-10-12, owner-authorized)

Appended to §6; nothing above is rewritten (append-only, §2.1). This block
**closes Phase 3**: it promotes the rules the live pass discovered into stated
policy, and it moves the guard on those rules from a suite that needs a database
to the suite that runs on every `npm test`.

**1. The inventory reservation policy is ratified (this is the rule of record).**
The live pass implemented it; this block states it, so it cannot be re-litigated
as an accident of implementation:

| # | Rule | Why |
| --- | --- | --- |
| a | Placing an order consumes its lines' stock **atomically**, in the same transaction as the `PENDING` order row | A `PENDING` order must not exist without the pieces it reserved; the last piece must not be sellable twice |
| b | A transition to `CANCELLED` returns **exactly** the quantities that order consumed, **once** | Restock must be exact and idempotent; the guard is the previous status, and `CANCELLED` is terminal |
| c | A redeemed coupon is **not** refunded — the usage counter keeps the redemption | The conservative direction for a discount counter: a code cannot be re-spent by cancelling |

The policy is written into the persistence seam's own contract rather than only
into prose: the `placeOrder` doc block on `CommerceRepository`
(`commerce/src/server/repository.ts`) now states (a)–(c) explicitly. The stale
comment it replaced claimed the opposite — that the path did NOT decrement stock
and that reservation belonged to a later phase — which is exactly the kind of
silently-false documentation `PROJECT_RULES.md` §37 forbids.

**2. Merchant inventory reconciliation is now asserted, not assumed.** The
owner's question behind this block was whether `/admin/inventory` reflects what
customers did. It does, and the assertion is against the panel's OWN rules rather
than against a quantity read by hand: `commerce/src/__tests__/funnel.test.ts`
places an order and then evaluates `inventorySummary`, `stockState` and
`filterInventory` (the functions `inventory-workspace.tsx` renders from) over a
fresh `listInventory()`. The basket is fixture-chosen so the order crosses two
thresholds at once — one line takes a variant from 4 to 2 (into low stock) and
another from 2 to 0 (sold out) — so the grid must show `OUT_OF_STOCK` on the
emptied row, `LOW_STOCK` on the reduced one, the «ناموجود» chip must list exactly the empty rows, and after
the cancellation **every** opening quantity must be back with the summary
returned to its pre-order state. The same read also proves the customer side
agrees: the sold-out colour can no longer be chosen and the colour that was bought
down reads «موجودی محدود».

**3. The customer funnel is guarded hermetically — eight stages, on every
`npm test`.** New suite `commerce/src/__tests__/funnel.test.ts` walks the journey
in the order a customer meets it: catalog read and facet narrowing (a DRAFT
product is invisible on every read path) → PDP colour × size matrix (a sellable
colour opens, the sold-out cell stays visible and disabled, a colour with no such
size is a different state) → cart lines produced by `toCartLine` and stored in the
real drawer store, including the `localStorage` round trip and the merge/stepper
semantics → the pre-flight check warning about an over-quantity that cannot be
bought, while writing nothing → `placeCheckoutOrder` writing the `PENDING` order
with server-computed totals, the coupon applied and the stock consumed → the
merchant grid reconciling → cancellation restoring stock exactly once with the
coupon counter untouched → and finally the REAL `placeOrderAction` entry point
refusing `DB_NOT_CONFIGURED` with no canonical connection, so the fail-closed gate
is proven at the surface the browser actually calls. It runs on the in-memory
double and a stubbed `localStorage`: no browser, no database, no network.

**4. The PDP's selection rules became a pure module so the funnel test could be a
real guard.** `commerce/src/lib/variant-selection.ts` now owns: which colour opens
(the first SELLABLE one — falling back to the first, so a sold-out product still
shows its own selector instead of an empty one), which sizes are DISABLED rather
than hidden, what the badge may claim before a size is picked (the colour's own
aggregate, and `OUT` rather than a reassuring `IN` when nothing is sellable), the
quantity cap per level, the colour-scoped gallery, and the cart line with its
clamp. `variant-selection.test.ts` pins each of those, and
`product-experience.tsx` keeps only state and markup. Behaviour is
equivalence-preserving: the same functions drive the same branches the component
had inline.

**5. One harness gap was found and closed.** `next` ships real extensionless
subpath files and declares **no** `exports` map, so `import … from 'next/cache'`
— which every storefront server action needs — is unresolvable to Node's own ESM
resolver, which is what the offline suite runs under. The test resolver
(`commerce/test/alias-resolver.mjs`) now retries a FAILED bare specifier as
`X.js` (CommonJS resolution's own rule), as a fallback only: anything that already
resolved keeps resolving the same way, and the original error is re-raised when
the retry fails too. Without it, no offline test could reach a server action, and
stage 8 of the funnel guard would not exist.

**Evidence after these changes (all re-run on the final tree):**

- `npm run verify` → **exit 0** — `tsc --noEmit`, `eslint .` **0 problems**,
  `npm test` **176/176 pass across 46 suites** (both live suites skipping by name
  with `COMMERCE_DATABASE_URL` absent, as designed), `drizzle-kit check`
  (`Everything's fine`).
- `npm run build` → **exit 0**, the same eleven routes, all storefront routes
  dynamic.
- `npm run smoke:db` → **41/41 pass, exit 0** on PostgreSQL 16.15 in the
  disposable loopback harness (`commerce-db-harness-postgres`, migrations
  re-applied per file), re-run AFTER this block's changes to confirm the offline
  additions did not disturb the live path.
- **Boundaries.** Colima was started for the live re-run and the harness torn down
  afterwards (`db:down`; container, network and Colima returned to the stopped
  state they were found in). No deployment, no provisioning, no migration outside
  the disposable harness, no credential, nothing pushed.

**Phase 3 status: CLOSED.** Open items carried forward unchanged (they are the
owner's, and no item here resolves one silently): OTP/SMS and the payment and
shipping providers (**G-4**, decisions 10/11), storefront media storage (**G-5**),
the missing audit record for order transitions, image zoom / swipe gestures, and
device testing of the PDP on a phone.

### Phase 4 TRANSITION — order audit trail + payment-callback ingress seam (2026-10-13, owner-authorized)

Appended to §6; nothing above is rewritten (append-only, §2.1). This is the
groundwork the Phase 4 AI engine and the §6.1 payment path both need, delivered
BEFORE either: an auditable order state machine and a fail-closed ingress for
asynchronous provider callbacks. It **closes one item the Phase 3 close-out
carried forward** — "the missing audit record for order transitions" — and it
starts NO part of the AI engine (Phase 4 remains unstarted). No provider is
selected, and the callback endpoint therefore processes nothing today.

**1. The order state machine now has an audit trail, and it is transactional.**
New table `commerce.order_status_history` (migration `0002`) with a closed enum
`order_status_source`:

| Column | Meaning |
| --- | --- |
| `order_id` | the order the transition belongs to (`on delete cascade`, like its line items) |
| `from_status` | the status it left — `NULL` **only** for the row that records the order's CREATION |
| `to_status` | the status it reached; one row per status an order reaches |
| `source` | WHO asked: `STOREFRONT` · `MERCHANT_PANEL` · `PAYMENT_CALLBACK` · `SYSTEM` |
| `metadata` | optional facts with no column of their own (a gateway reference, a provider event id) — never customer PII |
| `created_at` | the transition's instant |

The row is appended by the SAME transaction that changes the order — order
creation (`from_status` null → `PENDING`, source `STOREFRONT`) and every
transition alike. A status change therefore cannot commit without its trail, and
a refused change leaves no row (nor a restock). Two CHECKs defend the record's
meaning rather than its shape: `from_status <> to_status` (nothing changed, so
nothing may be recorded) and "an origin-less row may only be the opening
`PENDING` row" (a later transition may not present itself as the order's
beginning). What this table deliberately is NOT: a general activity log (order
lines, the coupon counter and `updated_at` are not duplicated here), and
recording a tracking code writes NO row, because `tracking_code` is an attribute
of the parcel rather than a status.

**2. The trigger source is REQUIRED and the repeat is a NO-OP.**
`updateOrderStatus(orderId, status, trigger)` and `transitionOrder(repo, orderId,
next, trigger)` both take a `{ source, metadata? }` argument with no default: a
default would silently attribute a machine's transition to the merchant panel,
which is precisely the fact an audit trail exists to get right. A transition to
the status the order is already in writes nothing and reports success at the
repository (the service still refuses it with a clear message for the panel), so
a retried caller cannot restock twice or append a second row.

**3. Idempotency moved to the storage layer.** `unique (order_id, to_status)`
encodes what this lifecycle guarantees — no back-edges, and a transition to the
current status is refused before any write — so a provider callback replayed ten
times cannot append a second row claiming the same status even if the code above
it were wrong. This is an ASSUMPTION ABOUT THE LIFECYCLE recorded as a
constraint: a future phase that legitimately adds a back-edge (a refund
returning `PAID` to `PENDING`, say) must drop the index in its own reviewed
migration. The live suite proves the constraint bites by provoking a real
`23505` and asserting the whole transaction — status move included — rolled back.

**4. `POST /api/webhooks/payment` is the async ingress seam (fail-closed
scaffold).** `commerce/src/app/api/webhooks/payment/route.ts` is a three-line
shim (`runtime = 'nodejs'`) over `handlePaymentWebhook`, which is where the
behaviour and its tests live. The pipeline refuses in a fixed order, cheapest and
most authoritative first:

| Stage | Refusal | Answer |
| --- | --- | --- |
| seam configured | no secret in `COMMERCE_PAYMENT_WEBHOOK_SECRET` | `503` `WEBHOOK_NOT_CONFIGURED` — there is NO unverified mode, not even locally |
| authentic | missing / malformed / mismatched HMAC-SHA256 over the RAW body | `401`, compared in constant time |
| bounded | body over 64 KiB | `413` (measured only AFTER authentication) |
| well-formed | unparseable JSON, or a payload outside the contract | `400` |
| connected | no canonical connection | `503` `DB_NOT_CONFIGURED` |
| known + legal | unknown order / lifecycle-illegal move | `404` / `409` |

The authenticated path dispatches through the SAME transition service the
merchant panel uses, so the lifecycle map, the restock rule and the audit row are
the already-governed ones, and the callback's own row carries the provider
event id and reference in `metadata`. A REPLAY is answered `200 { duplicate: true }` and writes nothing: a provider that sees an error retries forever,
and retrying forever is how an endpoint becomes an outage. A callback may assert
only `PAID` or `CANCELLED` — `PROCESSING` and `SHIPPED` describe a parcel and are
merchant acts, so accepting them would let a provider drive fulfilment. The
signing scheme is provider-neutral ON PURPOSE: the provider is still **G-4** /
decision 10, every Iranian gateway signs differently, and choosing one here would
be inventing a credential's contract before the credential exists. Phase 6.1
adapts this seam to the real scheme rather than replacing the seam.

**5. Evidence after these changes (all re-run on the final tree).**

- `npm run verify` → **exit 0** — `tsc --noEmit`, `eslint .` **0 problems**,
  `npm test` **194/194 pass across 51 suites** (the live suites skipping by name
  with `COMMERCE_DATABASE_URL` absent, as designed), `drizzle-kit check`.
- `npm run build` → **exit 0**, twelve routes, `/api/webhooks/payment` present
  and dynamic.
- `npm run smoke:db` → **54/54 pass, exit 0, twice consecutively** — 22 Phase 2 +
  19 Phase 3 + 13 Phase 4-transition subtests. The new file
  (`phase4-audit-live.test.ts`) reads the trail back with SQL and proves: the
  migration's table/enum/cascade/unique index/CHECKs; the three refusals at the
  DATABASE (`23514` twice, `23505`); the storefront's opening row written with
  its order; that a REFUSED checkout writes no row at all; the merchant row and
  the cancellation row; a REAL `23505` provoked by hand that rolls the status
  move back; the cascade with the order; the callback answering `503` with no
  secret and writing nothing; `PAID` storing the reference and appending the
  `PAYMENT_CALLBACK` row; a replay answering `duplicate: true` with no second row;
  a cancelling callback returning the stock exactly once; a forged signature
  refused; and a fulfilment status refused.
- A refusal matrix over REAL HTTP against a running `next start`: unsigned → `503`
  `WEBHOOK_NOT_CONFIGURED` with no secret; with a secret, unsigned →
  `SIGNATURE_MISSING` `401`, forged → `SIGNATURE_MISMATCH` `401`; correctly
  signed but unconnected → `503` `DB_NOT_CONFIGURED`; signed and connected against
  the harness → `ORDER_NOT_FOUND` `404` for an unknown id, `INVALID_EVENT` `400`
  for a forbidden status, `INVALID_JSON` `400` for a truncated body; `GET` →
  `405`. The same running server also ACCEPTED a correctly signed `PAID` delivery
  for a real order in the harness — `200 { duplicate: false }`, after which SQL
  showed `orders.status = PAID` with `payment_ref_id` stored and a
  `PAYMENT_CALLBACK` row `PENDING → PAID` carrying `{ eventId, reference }` — and
  answered the identical delivery replayed `200 { duplicate: true }` with no third
  row. So the success path is proven over the real interface too, not only through
  the injected-repository tests. The server was started for this check and stopped
  afterwards.
- **Boundaries.** Colima was started for the live re-runs and the harness torn
  down afterwards (`db:down`; container, network and VM returned to the stopped
  state they were found in). No deployment, no provisioning, no migration outside
  the disposable harness, no provider, no credential, nothing pushed.

**Phase 4 status: transition scope DELIVERED and verified; the AI engine itself
NOT started.** Open items unchanged and undecided by this block: the AI provider
(**G-4** / decision 9), the payment provider (decision 10) and therefore the real
callback scheme, the SMS provider, media storage (**G-5**), the audit trail's
panel surface (it exists and is tested, but no screen shows it yet), the audit of
anything OTHER than an order status (a product archive/publish, a stock or price
edit and a coupon edit are still unrecorded, so the merchant-panel requirement
"every irreversible action leaves an auditable record" is met for the ORDER
lifecycle and not yet for the catalog surface), and its
possible enrolment in the engine's canonical provenance — which remains an owner
schema decision and is NOT implied by adding a track-local table.

## 7. References

- [`docs/roadmap/FASHION_ECOMMERCE_ROADMAP.md`](../roadmap/FASHION_ECOMMERCE_ROADMAP.md) — the adopted plan.
- `PROJECT_RULES.md` §2/§2.1/§3/§4, §37 (documentation must never become silently false).
- `MASTER_PLAN.md` §13 (Project Phases), §14 (Definition of Done), §16 (Current Status).
- Standing boundaries: D-003, D-010, D-026/D-027, D-034–D-056, D-045, D-069–D-092, D-114/D-124, D-129–D-132, D-139.
- Related tracks: D-141 (Dokploy), D-169/D-170 (Live Wiring closeout), D-171 (unified web control plane).

# Master Roadmap: AI-Powered Fashion E-Commerce Platform

- Status: APPROVED & ACTIVE
- Owner: Mohammad
- Authority: `PROJECT_RULES.md` §3 (only the human owner approves decisions);
  adopted by **D-172** (Approved 2026-10-10, owner-directed)
- Track: **E-Commerce & Social Publishing** — this document is the
  **authoritative execution plan** for that track (`MASTER_PLAN.md` §13/§16;
  `DECISIONS.md` ledger row 73)
- Companion record: [D-172](../decisions/D-172-fashion-ecommerce-roadmap.md)
- Stack Alignment: Next.js (App Router), Supabase / PostgreSQL, Drizzle/Prisma, Tailwind CSS, Shadcn UI, Redis Queue, n8n Automation Engine.

> **Boundary (unchanged by this roadmap).** This document grants **no
> execution authority**: nothing is provisioned, installed, connected or
> deployed by adopting it, no live credential exists or is requested (D-045),
> and production activation remains the sole owner-gated act (D-139). The
> owner sub-decisions this scope expansion raised were recorded as open at
> adoption and have since been **ruled**: **G-1, G-2 and G-3 are RESOLVED**
> (owner rulings, 2026-10-10 — see *Governance alignment & owner rulings*
> below and D-172 §4); **G-4, G-5 and G-6 remain open**. Nothing was resolved
> silently (`PROJECT_RULES.md` §2 step 10, §4).
>
> **Phase 1 (this document's §1.1–§1.5) is IMPLEMENTED** — the schema and the
> typed contracts live in `commerce/`, with the generated migration committed
> (D-172 §5.1). No phase is deployed: the track remains build-without-activation,
> and no environment beyond a throwaway validation container has ever seen this
> schema.

---

## Architecture Overview

Flow:
[Merchant Admin Portal] (Product Input, Size/Color Matrix, Media Upload)
  -> [Supabase PostgreSQL] (E-Commerce Catalog, Inventory, Orders)
  -> [Webhook Trigger to AI Engine]
       -> 1. Fashion Copywriting & Caption Generation
       -> 2. SEO & Trend Hashtag Optimization
       -> [Social Distribution Queue]
            -> Telegram Channel (Rich Photo Album + Buy Button)
            -> Instagram Graph API (Publishing Pipeline)

[Customer Storefront] reads Realtime Catalog, One-Page Checkout, Payment Gateway.

---

## Phase 1: Database Architecture & Fashion Catalog Core
Objective: Implement relational schema in PostgreSQL supporting apparel variants, sizes, colors, and inventory.

### 1.1 Categories Table (categories)
- id (uuid, PK)
- name (varchar, e.g., مانتو، شومیز، شلوار)
- slug (varchar, unique, index)
- parent_id (uuid, self-referential FK for subcategories)
- description (text, nullable)
- created_at, updated_at (timestamptz)

### 1.2 Products Table (products)
- id (uuid, PK)
- category_id (uuid, FK -> categories.id)
- title (varchar, e.g., مانتو کتی لنین بهاره)
- slug (varchar, unique, index)
- base_price (bigint, in Tomans)
- discount_price (bigint, nullable)
- description_raw (text, raw merchant description)
- description_html (text, rich formatted)
- fabric_type (varchar, e.g., مازراتی، لنین، کرپ)
- season (varchar, e.g., بهاره، تابستانه)
- care_instructions (text, nullable)
- status (enum: 'DRAFT', 'PUBLISHED', 'ARCHIVED')
- created_at, updated_at (timestamptz)

### 1.3 Variants Table (product_variants)
- id (uuid, PK)
- product_id (uuid, FK -> products.id, cascade delete)
- sku (varchar, unique barcode/identifier)
- color_name (varchar, e.g., کرم، مشکی، نسکافه‌ای)
- color_hex (varchar, e.g., #F5F5DC)
- size (varchar, e.g., 36, 38, 40, FreeSize)
- stock_quantity (int, default 0)
- price_override (bigint, nullable)
- is_active (boolean, default true)

### 1.4 Images Table (product_images)
- id (uuid, PK)
- product_id (uuid, FK -> products.id, cascade delete)
- variant_id (uuid, FK -> product_variants.id, nullable)
- storage_path (text, Supabase Storage key)
- public_url (text)
- display_order (int, default 0)
- is_primary (boolean, default false)

### 1.5 Orders & Fulfillment Tables (orders, order_items, customers)
- orders: id, customer_id, total_amount, discount_amount, shipping_amount, status ('PENDING', 'PAID', 'PROCESSING', 'SHIPPED', 'CANCELLED'), payment_ref_id, shipping_address, tracking_code.
- order_items: id, order_id, variant_id, quantity, unit_price.
- customers: id, phone_number (unique), full_name, address, postal_code.

---

## Phase 2: Merchant Admin Panel (Mobile-First UX)
Objective: Frictionless management interface for boutique owners.

### 2.1 Smart Product Ingestion
- Clean multi-image uploader with auto-compression and aspect ratio locking.
- Fast Matrix Generator: Select colors + select size range -> auto-generate variant rows.
- Raw text input or voice note transcript field for AI ingestion.

### 2.2 Inventory & Inline Management
- Grid view with inline editing for stock and pricing without page refresh.
- Threshold-based low-stock visual badges.

### 2.3 Order Fulfillment & Shipping
- Order list with status transition dropdowns.
- Postal tracking code input with automated SMS trigger to the buyer.
- Printable packing slip view.

### 2.4 Promotions & Discounts
- Percentage and fixed-amount coupon codes with expiry dates and minimum spend limits.

---

## Phase 3: Customer Storefront (High-Conversion UX)
Objective: Modern, ultrafast e-commerce storefront utilizing Next.js Server Components.

### 3.1 Homepage & Collections
- Responsive hero section and visual story-style category circles.
- Featured, New Arrivals, and Best-Selling carousels.

### 3.2 Catalog & Real-Time Filtering
- Faceted search: Instant filtering by size, color palette, price slider, and availability.
- Infinite scroll / responsive pagination.

### 3.3 Product Detail Page (PDP)
- Swipeable high-res photo gallery with zoom capability.
- Dynamic color selector updating primary image preview.
- Interactive Size Selector with automatic disabled state for out-of-stock variants.
- Modal Size Chart Guide with garment measurements in centimeters.

### 3.4 One-Step Frictionless Checkout
- Slide-over Cart Drawer.
- Mobile-friendly checkout: Phone number OTP verification (no mandatory passwords).
- Shipping method selection (Express Courier, Standard Post, Tipax).

#### Phase 3 completion record (2026-10-12) — §3.1–§3.4 IMPLEMENTED & VERIFIED

Appended; the section text above is the specification and is **not** rewritten
(append-only, `PROJECT_RULES.md` §2.1). Full evidence in `D-172` §5.3 and §6.

- **§3.1 Homepage & collections.** Hero + category circles + three rails
  (جدیدها، پیشنهادهای تخفیف‌دار، پرفروش‌ها), each derived from real reads and
  **hidden when empty** — no invented "featured" badge and no rail of
  placeholders. Best-sellers are quantity shipped with cancelled orders
  excluded.
- **§3.2 Catalog & real-time filtering.** Faceted by category, size, colour and
  a price range, plus availability and search; facets are **derived from the
  published cards**, so a size nobody stocks is never offered. Filtering and
  paging run in the browser (instant, no round trip); an empty result says so and
  offers a way back.
- **§3.3 Product detail page.** Client-side gallery viewer, colour selector that
  re-scopes the gallery to that colour's photos, an interactive colour × size
  matrix with **out-of-stock variants disabled** (never silently rejected at
  checkout), stock stated as a LEVEL (موجود / موجودی محدود / ناموجود — raw
  quantities never leave the server), a size-chart modal in centimetres, and a
  related-products rail from the same category via the public read path.
- **§3.4 One-step checkout.** Slide-over cart drawer; persistent cart
  (`localStorage`, read through an external store so the server render and the
  hydrating client render agree); customer form validated with the same rules the
  server applies (Persian phone/address/postal); coupon applied server-side
  against the existing promotions service; order breakdown (subtotal, discount,
  shipping, total); shipping method selection (پست پیشتاز، پیک، تیپاکس).
  The order is persisted through a server action as `PENDING`.
- **Payment adapter interface (roadmap §3.4 → Phase 6 prerequisite).**
  `MockPaymentGateway` implements the fail-closed gateway interface and answers
  `UNAVAILABLE` — the customer is told nothing was charged and the order exists as
  `PENDING` (AC-8: never a faked status). Selecting the live Iranian provider
  stays the owner's Phase 6 decision (**G-4** / open decision 10).
- **Still open, stated rather than faked:** phone-number **OTP** verification was
  **not** built — it needs the SMS provider selection (G-4) and a mock code entry
  would be worse than none; the number is validated and stored as the customer
  identity. Live payment capture, image zoom and swipe gestures remain Phase 6 /
  follow-up work; the gallery is client-side navigation, and mobile gestures were
  not device-tested.
- **Fail-closed states (§3.3 of the roadmap's UI/UX requirements).** With no
  canonical connection the storefront renders *«در این لحظه نمایش داده نمی‌شود»*
  on every data surface and **no checkout form at all**, rather than an empty shop
  or an order it cannot write. Grid/PDP loading skeletons and empty states for
  search and cart are in place.
- **Evidence.** `npm run verify` exit 0 (typecheck, lint **0 problems**,
  **146 tests / 37 suites** pass, `db:check`); `npm run build` exit 0 with every
  storefront route dynamic (`/`, `/catalog`, `/checkout`, `/products/[slug]`) and
  the admin routes intact; browser-verified on the dev server (RTL — `lang="fa"`
  and `dir="rtl"` on the document, the cart adopted from `localStorage` after
  hydration → badge «سبد خرید، ۳ کالا»، the drawer's quantity control writing
  quantity 4 back and updating the badge, a clean console). **No live PostgreSQL was available in
  this environment** (Docker daemon down), so the storefront's data paths are
  covered by the memory-double suites and the opt-in live smoke suite stayed
  SKIPPED with its named reason; the live storefront read path is therefore
  **not** yet exercised end-to-end against a real server.

#### Phase 3 live pass — the funnel against real PostgreSQL (2026-10-12, same day)

Appended; the record above is not rewritten (append-only). It CLOSES the gap its
own last bullet stated. Details and the full evidence trail are in `D-172` §6.

- `commerce/src/__tests__/live-db/phase3-storefront-live.test.ts` drives the real
  repository through §3.1 category counts and rails, §3.2 faceting/filtering/
  availability, §3.3 PDP levels, price resolution and the gallery, and §3.4 the
  order write — asserting against rows read back from PostgreSQL, not against a
  service's return value. `npm run smoke:db` → **41/41 pass, exit 0, twice
  consecutively** on PostgreSQL 16.15 (the disposable loopback harness), with
  both live files resetting and re-applying the committed migrations per run.
- **Two real defects were found and fixed by that pass.** (1) `placeOrder` locked
  its rows with `for update of "commerce"."product_variants"`, which PostgreSQL
  refuses (42601) — so **every** checkout failed at the lock before writing
  anything; the lock is now a single-table `for update` on `product_variants`.
  (2) **Nothing consumed stock**, so the last piece could be sold repeatedly; per
  the owner's ruling on this pass, an order now consumes stock atomically inside
  its own transaction and a cancellation returns it exactly once (both repository
  implementations). Two simultaneous buyers of one remaining piece are proven to
  yield exactly one order and zero stock.
- **Storefront checkout (§3.4) therefore has one behaviour the specification
  above did not spell out:** stock is RESERVED at checkout, not at payment
  capture, and released on cancellation. Coupon usage is not refunded.
- Offline half added so the rule survives without a server:
  `src/server/services/checkout.test.ts` (9 tests over the in-memory double).
  `npm run verify` → exit 0 (**155 tests / 40 suites**, lint 0 problems);
  `npm run build` → exit 0.

#### Phase 3 CLOSE-OUT — policy ratified, funnel guarded on every `npm test` (2026-10-12, same day)

Appended; nothing above is rewritten (append-only, `PROJECT_RULES.md` §2.1). With
this block **Phase 3 is closed**. Full evidence in `D-172` §5.3/§6.

- **The inventory reservation policy is RATIFIED as the track's rule** — the
  behaviour the live pass discovered is no longer an implementation detail:
  (a) placing an order **consumes** its lines' stock atomically, in the same
  transaction as the `PENDING` order row, so an order can never exist without the
  pieces it reserved; (b) a transition to `CANCELLED` returns **exactly** the
  quantities that order consumed, **once** (the restock is guarded by the
  previous status, and `CANCELLED` is terminal); (c) a redeemed coupon is **not**
  refunded — the usage counter stays where the redemption put it. The policy is
  stated in the persistence seam's own contract (`placeOrder`,
  `CommerceRepository`) rather than in prose only, and every clause is asserted in
  one place or another (a–b live and offline, c live).
- **Merchant inventory reconciliation is now an asserted property, not an
  assumption.** The customer funnel test drives a real order through the
  in-memory repository and then reads the merchant grid's OWN rules
  (`inventorySummary`, `stockState`, `filterInventory` — the functions the panel
  renders from): the bought-out variant reads `OUT_OF_STOCK`/«ناموجود» and the
  reduced one crosses into `LOW_STOCK` immediately, the «ناموجود» chip lists
  exactly the empty rows, the storefront's own colour selector agrees with the
  grid from the same stock read, and a cancellation returns the grid to its
  pre-order state with the coupon counter untouched.
- **Browser-level checkout funnel guard, hermetically.**
  `commerce/src/__tests__/funnel.test.ts` walks the customer journey in eight
  stages — catalog → facet filter → PDP colour × size matrix → cart line in the
  persisted drawer store (`localStorage` round trip included) → pre-flight
  warning → `placeCheckoutOrder` → order row → merchant grid → cancellation —
  and ends by driving the REAL `placeOrderAction` entry point to prove the
  funnel refuses loudly (`DB_NOT_CONFIGURED`) rather than faking an order when
  no canonical connection is configured. No browser, no database, no network:
  it runs on every `npm test`.
- **The PDP's selection rules were extracted to be testable.**
  `commerce/src/lib/variant-selection.ts` holds which colour opens (the first
  SELLABLE one, falling back to the first so a sold-out product still shows its
  selector), which sizes are disabled rather than hidden, what the badge may
  claim before a size is picked, the quantity cap per level, the colour-scoped
  gallery and the cart line itself; `variant-selection.test.ts` pins them, and
  the product page keeps only state and markup. This is what makes the funnel
  guard above a real guard rather than a rendered component's side effect.
- **Evidence.** `npm run verify` → exit 0 (typecheck, lint **0 problems**,
  **176 tests / 46 suites**, `db:check`); `npm run build` → exit 0 with the same
  eleven routes; `npm run smoke:db` against the disposable loopback harness →
  **41/41 pass, exit 0** (re-run after these changes). One harness gap was
  closed on the way: `next` ships extensionless subpath files and declares no
  `exports` map, so the test resolver now retries a failed bare specifier as
  `X.js` — without that, no test could import a server action that calls
  `revalidatePath`.
- **Phase 4 readiness.** Nothing in the AI copywriting hub depends on an open
  item here: its inputs are the merchant's `description_raw` (already stored,
  with `description_html` reserved as its target) and the product facts already
  read by `@/server/services/products`. What Phase 4 still needs from the owner
  is the AI provider selection (**G-4** / decision 9) — unchanged, and no
  credential exists or is requested.

**Phase 3 open items carried forward (unchanged, not silently resolved):** OTP
verification (SMS provider, G-4), live payment capture (decision 10), media
storage (G-5), the missing audit record for order transitions, image zoom/swipe
gestures, and device testing of the PDP on a phone.

#### Phase 4 TRANSITION — order audit trail and the payment-callback ingress seam (2026-10-13)

Appended; nothing above is rewritten (append-only, `PROJECT_RULES.md` §2.1). This
is the GROUNDWORK Phase 4 and §6.1 both need, taken before the AI engine and the
provider selections, and it **closes one carried-forward item**: the "missing
audit record for order transitions" listed directly above is now implemented and
verified. **Phase 4 itself (the copywriting engine) is NOT started.**

- **The order state machine has an audit trail.** New table
  `commerce.order_status_history` (migration `0002`, alongside a closed enum
  `order_status_source`): one row per status an order REACHES — previous status
  (`NULL` only for the creation row), new status, WHO asked (`STOREFRONT` ·
  `MERCHANT_PANEL` · `PAYMENT_CALLBACK` · `SYSTEM`), optional `metadata` for facts
  with no column of their own, and a timestamp. It is not a general activity log:
  line items, the coupon counter and `updated_at` are not duplicated, and
  recording a tracking code writes NO row because it is not a status change.
- **The audit row is written by the same transaction as the move.** Order creation
  (`PENDING`, source `STOREFRONT`) and every transition append their row inside the
  one transaction that changes the order, so a status change cannot commit without
  its trail and a REFUSED change leaves neither a row nor a restock. The trigger
  source is a REQUIRED argument on the write path — a default would silently
  attribute a machine's move to the merchant panel, which is the one fact an audit
  trail exists to get right.
- **Idempotency is enforced at the storage layer, not only in code.**
  `unique (order_id, to_status)` reflects this one-way lifecycle: an order reaches
  a given status at most once, so a retried callback cannot append a second row
  even if the code above it were wrong. A repeat asked of the repository is a
  documented NO-OP (success, nothing written: no second restock, no second row).
  The index is an assumption about the lifecycle and a future phase adding a
  back-edge must drop it in its own reviewed migration.
- **The async payment/notification callback now has an ingress seam.**
  `POST /api/webhooks/payment` exists as a three-line shim over a tested
  pipeline, refusing in a fixed order: no secret configured → `503` (there is NO
  unverified mode, not even locally); missing, malformed or mismatched
  HMAC-SHA256 signature over the RAW body → `401` (constant-time comparison);
  oversized body → `413`; unparseable JSON or a payload outside the contract →
  `400`; no canonical connection → `503`; unknown order → `404`; a
  lifecycle-illegal move → `409`. A valid delivery dispatches through the SAME
  transition service the merchant panel uses — so the lifecycle map, the restock
  and the audit row are the governed ones — and a REPLAY is answered
  `200 { duplicate: true }` writing nothing, because a provider that sees an error
  retries forever. A callback may assert only `PAID` or `CANCELLED`: `PROCESSING`
  and `SHIPPED` are merchant acts about a parcel, and accepting them would let a
  provider drive fulfilment. The signing scheme is provider-neutral ON PURPOSE
  (the provider is **G-4** / decision 10); Phase 6.1 adapts this seam to the real
  one rather than replacing it, and the secret lives in
  `COMMERCE_PAYMENT_WEBHOOK_SECRET` — unset today, and unset means refuse.
- **Evidence.** `npm run verify` → exit 0 (typecheck, lint **0 problems**,
  **194 tests / 51 suites**, `db:check`); `npm run build` → exit 0 with twelve
  routes (`/api/webhooks/payment` present); `npm run smoke:db` → **54/54 pass,
  exit 0, twice consecutively** (22 Phase 2 + 19 Phase 3 + 13 Phase 4-transition),
  including a REAL `23505` provoked by hand to prove the status move ROLLS BACK
  when its audit row cannot be written, the three audit CHECKs and the unique
  index refused at the database, and the callback path persisting its row against
  real PostgreSQL. Over real HTTP against a running `next start`: unsigned `503`
  with no secret, `SIGNATURE_MISSING` / `SIGNATURE_MISMATCH` `401` with one,
  `DB_NOT_CONFIGURED` `503` when signed but unconnected, `ORDER_NOT_FOUND` `404`
  when connected, `INVALID_EVENT` / `INVALID_JSON` `400`, `405` on GET — and the
  same server ACCEPTED a correctly signed `PAID` delivery for a real order in the
  harness (`200 { duplicate: false }`), after which SQL showed that order `PAID`
  with its `payment_ref_id` stored and a `PAYMENT_CALLBACK` row (`PENDING →
  PAID`) carrying `{ eventId, reference }`; the identical delivery replayed
  answered `duplicate: true` with no third row. The server was started for this
  check and stopped afterwards.
- **Scope honesty — what this does NOT audit.** The merchant-panel requirement
  above ("every irreversible action … leaves an auditable record") now holds for
  ORDER transitions only. A PRODUCT status change (archive/publish), a stock or
  price edit and a coupon edit are still unrecorded, so the requirement is met
  for the order lifecycle and NOT yet for the catalog surface; that gap is named
  here instead of being implied away by the existence of the audit table.
- **Phase 4 readiness (the AI hub).** Unchanged inputs — the merchant's
  `description_raw` (stored, with `description_html` reserved as its target) and
  the product facts already read by `@/server/services/products`. What the phase
  still needs from the owner is the AI provider selection (**G-4** / decision 9);
  no credential exists or is requested. The audit trail gives Phase 4/6 a place to
  attribute an automated move to (`SYSTEM`) instead of inventing one.

---

## Phase 4: Fashion AI Engine & Copywriting Hub
Objective: Transform raw product attributes into marketing assets.

### 4.1 Fashion Copywriting Engine
- Prompt pipeline taking fabric_type, season, title, and raw notes to generate:
  - Engaging Instagram caption with tone presets (Luxury, Casual, Trendy).
  - Clean Telegram announcement text.
  - SEO-optimized meta description and web copy.

### 4.2 Trend & Hashtag Intelligence
- Auto-generation of targeted niche fashion hashtags based on garment category and season.

#### Phase 4 §4.1 completion record (2026-10-20) — §4.1 IMPLEMENTED & VERIFIED (offline); §4.2 NOT started

Appended; the section text above is the specification and is **not** rewritten
(append-only, `PROJECT_RULES.md` §2.1). Full record in `D-172` §5.4 and §6.

- **The pipeline exists** — `local/canonical/fashion_copy.py`: a structured brief
  (`fabric_type`, `season`, `title`, raw seller `notes`, optional `product_id` and
  a tone preset) is rendered through versioned templates into ONE request per
  channel and dispatched through the existing AI runtime (`ModelRouter` →
  `AiProvider`), never a direct provider call. `dry-run` is the default and
  persists nothing; `persist` lands every output as `PROPOSED` through the M2
  proposal lifecycle (queue + provenance), and the module has **no** publication
  surface at all.
- **Instagram caption + tone presets (Luxury/Casual/Trendy)** — the channel
  **reuses** the approved `generate_caption` task and `caption_proposal.v1`
  contract (G-6, one dispatch path per channel); the preset is request-side input
  rendered from `fashion_instagram_caption@v1.0.0`, so no new caption contract and
  no forked vocabulary rule were introduced.
- **Telegram announcement** — `telegram_announcement.v1` / task
  `fashion_telegram_announcement`: plain text + CTA + hashtags, validated against
  the **channel's own 4096-character cap** with the CTA and hashtag suffix counted,
  so a length refusal cannot surface for the first time at publish (D-073).
- **SEO copy** — `seo_copy.v1` / task `fashion_seo_copy`: meta description
  (50–160 characters), web copy and 1–15 keywords.
- **Contract-first, never repaired (D-062/D-052)** — both contracts are strict
  (`additionalProperties: false`), versioned, pinned to the frozen fixture, and
  each template's `response_contract` must stay byte-equal to the registry; an
  out-of-contract model output raises `OutputValidationError` (Class B).
- **Deterministic guards (AC-4/AC-5, D-029/D-031/D-032)** — hashtags and SEO
  keywords pass the ONE shared `check_hashtag_vocabulary` guard; a price, link or
  discount token that does **not** appear in the brief is a divergence (quoting a
  price the seller stated is allowed, inventing one is not); the composed Telegram
  text is checked against the cap. Divergence → Class B, nothing persisted.
- **Still open, stated rather than implied done** — §4.2 hashtag/trend intelligence
  is not started; no merchant-panel or storefront caller of this engine exists yet;
  no live model was called, so copy quality across real providers is unproven; the
  output is a proposal, and publishing remains Phase 5.
- **Evidence** — `python3 -m unittest local.tests.test_phase4_fashion_copy` →
  **48 tests, OK**; full sweep `python3 -m unittest discover -s local/tests -p
  "test_*.py"` → **2487 tests, 3 failures**, all three the known
  live-PostgreSQL-dependent tests that fail identically on the untouched HEAD
  (verified by stashing the change). No deployment, provisioning, provider or
  credential.

#### Phase 4 §4.2 completion record (2026-10-20) — §4.2 IMPLEMENTED & VERIFIED (offline)

Appended; the section text above stays as written and is **not** rewritten
(append-only, `PROJECT_RULES.md` §2.1). Full record in `D-172` §5.5 and §6.

- **The pipeline exists** — `local/canonical/fashion_trends.py`: a structured
  `TrendBrief` (`garment_category`, `season`, optional `fabric_type`, raw seller
  notes, optional `product_id`) becomes ONE `trend_hashtag_set.v1` proposal of
  5–30 tags on the new `fashion_trend_hashtags` routing key, rendered from
  `fashion_trend_hashtags@v1.0.0` (template_id + hash on the request, D-067) and
  dispatched through the existing runtime — never a direct provider call.
- **“Based on garment category and season” is CHECKED, not prompted.** The tags
  must be partitioned into `category_tags` / `season_tags` / `niche_tags`; the
  groups must be disjoint, share their union with `hashtags` and account for
  every tag exactly once. `category_tags` must contain the merchant's own
  category and `season_tags` the merchant's own season after deterministic
  normalisation — and the comparison is equality, so «مانتوپاییزی» does not
  satisfy «مانتو», nor «پاییزی» satisfy «پاییز».
- **One vocabulary rule, no fork.** Every tag passes the shared
  `check_hashtag_vocabulary` (D-029/D-031/D-032). Its new optional `allow`
  parameter carries the merchant's own stated category/season/fabric: a fact the
  seller wrote is not model-authored vocabulary, so the fabric «کرپ» is not
  treated as a misspelling of the colour «کرم» — while the same token, for a
  brief that never stated it, is still refused. `allow` is exact-match only and
  defaults to empty, so every pre-existing caller is unchanged.
- **Invented facts stay refused (AC-4/AC-5)** — `check_invented_facts` is
  REUSED (never copied); a price, link or discount token absent from the brief
  is Class B. Tags are stored unhashed; whitespace and an inner `#` are refused,
  because a hashtag is one unbroken token that the composer renders once.
- **HITL boundary** — `dry-run` is the default and persists nothing; `persist`
  lands a `PROPOSED` item through the M2 lifecycle (event + provenance + queue),
  repeats are idempotent on
  `fashion-trend/<product_id|brief>/<season>/<category>[/<fabric>]`, and the
  module has **no** publication surface (AST-asserted).
- **Still open, stated rather than implied done** — no merchant-panel or
  storefront caller; no publishing (Phase 5); no live model was called, so
  hashtag quality across real providers is unproven; the AI provider (G-4 /
  decision 9) remains the owner's open decision.
- **Evidence** — `python3 -m unittest
  local.tests.test_phase4_fashion_trends` → **52 tests, OK**; targeted §4.1 +
  phase7 `m1..m4`/`m4_stdlib` + phase8 observability → **190 tests, OK** (15
  pre-existing live-DB skips); full sweep → **2539 tests**, the same three known
  live-PostgreSQL failures as HEAD. No deployment, provisioning, provider or
  credential.

#### Phase 4 provider gate — fail-closed runtime wiring (2026-10-20) — VERIFIED offline

Appended; the section text above is the specification and is **not** rewritten
(append-only, `PROJECT_RULES.md` §2.1). Full record in `D-172` §5.6 and §6.

- **Anchor, stated rather than assumed.** This roadmap has **no Phase 4 §4.3**: it
  defines §4.1 (copywriting) and §4.2 (trend/hashtag intelligence) only, and the
  `§4.3` in `D-172` is the **G-3 schema-authority ruling**, not a Phase 4
  section. The work recorded here is the open `TODO.md` item **“Phase 4 provider
  gate”** — filling a section number that does not exist would have been an
  invented task.
- **What the gate is.** `local/canonical/ai_provider_gate.py` is the single
  answer to *which provider may serve a fashion task, on whose authority, and
  with what remaining budget*. It does **not** select a provider (decision 9 /
  G-4 stays OPEN), constructs no adapter, names no vendor, opens no socket and
  reads no environment variable.
- **Deny by default.** A provider must be DECLARED in the catalogue (only the
  local `mock` is declared by default) and REGISTERED on the router; otherwise it
  is refused by name. `mock` is the only ungated class. A `live` class needs a
  recorded `OwnerDecision` covering both the task and the provider (unexpired,
  with a reference and an approver), an injected credential-**presence**
  predicate for a declared variable name, a positive declared budget, and a
  non-production environment (live AI is production-blocked, D-045). The routed
  schema must be a registered contract.
- **Consent is a record, not a flag.** An env flag plus a key can still be
  required by the D-066 adapter construction gate; it is **not sufficient** to
  serve a fashion task. The gate's default presence predicate answers `False`
  for everything.
- **Budget/rate stay the router's.** `ai_runtime` gained read-only views
  (`TokenBucket.available()`, `ModelRouter.budget_state()`,
  `rate_limit_available`, `rate_limit_capacity`); enforcement remains in
  `ModelRouter._guardrails` (D-063). `preflight()` dispatches nothing and
  consumes no token. Refusals are stable codes, with `RATE_LIMITED` Class A and
  the rest Class B.
- **Wiring, not replacement.** `guarded_router()` returns a NEW router whose
  policy contains only gate-approved tasks; `wire_fashion_engines()` binds the
  §4.1 and §4.2 engines to it unchanged; `strict` (default) refuses a partially
  wired surface. Decisions are frozen, timestamp-free, value-free records
  (`ai.provider_gate.v1`) suitable for an audit sink.
- **Still open, stated rather than implied done** — no provider is selected and no
  live adapter is wired; nothing was contacted. Phase 5 publishing and any
  merchant/storefront caller remain unbuilt.
- **Evidence** — `python3 -m unittest local.tests.test_phase4_provider_gate` →
  **57 tests, OK**; targeted §4.1/§4.2 + phase7 `m1..m4`/`m4_stdlib` + phase8
  observability → **298 tests, OK** (15 pre-existing live-DB skips); full sweep →
  **2596 tests** with the same three known live-PostgreSQL failures as HEAD. No
  deployment, provisioning, credential or network call.

---

## Phase 5: Multi-Channel Social Automation
Objective: One-click publishing across key Iranian e-commerce social channels.

### 5.1 Telegram Channel Publisher
- Automated post assembly: Image group + formatted caption + inline keyboard with direct purchase link.
- Webhook trigger via n8n pipeline or direct Telegram Bot API.

#### Phase 5 §5.1 completion record (2026-10-20) — post assembly + HITL pipeline IMPLEMENTED & VERIFIED (offline); §5.2 NOT started

Appended; the section text above is the specification and is **not** rewritten
(append-only, `PROJECT_RULES.md` §2.1). Full record in `D-172` §5.7 and §6.

- **The join exists** — `local/canonical/fashion_social_bundler.py`: a structured
  brief (§4.1 `FashionBrief` + §4.2 `TrendBrief` + the merchant's own media list,
  both channel slots, optional `purchase_url`) is dispatched through the SAME
  runtime for both engines and composed into ONE strict, versioned
  `social_bundle_proposal.v1` — Telegram (single photo **or** 2–10-item album,
  caption, slot), Instagram (media ref + content hash, caption with the CTA line,
  aspect ratio, slot), the tag set, the SEO block, both engines' provenance, and an
  `approval` block **schema-pinned to `required: true` / `state: PROPOSED`**. An
  auto-publishing bundle is therefore not representable, let alone reachable.
- **“Image group + formatted caption + purchase link”** — one merchant media list
  decides `photo` vs `mediagroup` (the channel's own 2..10 album rule), the caption
  is composed as copy + CTA line + the §4.2 tags, and the purchase URL may appear
  ONLY if it is the merchant's own `purchase_url`. The caption's own §4.1 hashtags
  are deliberately dropped: one post carries ONE tag set, and a tag outside the
  §4.2 set is a Class-B refusal.
- **Channel contracts, not conventions** — every composed string is re-validated by
  `telegram_contracts` / `instagram_contracts` BEFORE a proposal exists, so a
  caption/album/size problem can never surface for the first time at publish.
- **HITL is the existing M2 lifecycle** — `persist` lands `PROPOSED` (D-027 event +
  D-026 provenance + verification-queue item), repeats are idempotent on a
  deterministic `bundle_key`, `dry-run` persists nothing, and
  `hand_off_to_outbox()` is the ONLY escape: `ACCEPTED` state, bundle schema,
  unmodified `payload_hash`, `approval.required: true` and at least one outbox are
  ALL required, after which it enqueues through the canonical
  `TelegramOutboxPublisher` / `InstagramOutboxPublisher` seams and never calls
  their send path. `pending_bundles()` is the durable merchant review list.
- **No publication surface (AST-asserted)** — no network import, no
  adapter/publisher import, no credential/environment read, no
  `publish`/`send`/`dispatch` verb, no `os` import; channel identity comes from the
  ONE D-077 registry (`orchestration_contracts.KNOWN_TARGETS`) so the D-131
  channel-isolation sweep stays clean.
- **Still open, stated rather than implied done** — the canonical Telegram
  publisher has **no inline-keyboard field**, so the inline buy button of §5.1 is
  carried as a validated CTA **line** and the keyboard is a named gap of the
  publisher seam; the §5.1 webhook trigger remains the existing n8n/direct-publisher
  seam (the outbox queue is what it consumes) and nothing is triggered here; §5.2
  is NOT started — the bundle only produces the per-channel `scheduled_slot` that
  the peak-hours queue will consume; no live channel was called and no credential
  exists (D-045).
- **Evidence** — `python3 -m unittest local.tests.test_phase5_social_bundler` →
  **85 tests, OK**; targeted §4.1/§4.2/provider-gate + §5.1 → **240 tests, OK**;
  `full_security_sweep` → `clean: true` (AST 185 files / 0 findings; entropy
  0 flagged; bounds 11 modules; channel isolation 0 findings). No deployment,
  provisioning, network call or credential.

### 5.2 Instagram Business Publisher
- Image preparation and container publishing via Meta Graph API.
- Scheduled publishing queue for peak customer engagement hours.

#### Phase 5 §5.2 completion record (2026-10-22) — peak-hours queue IMPLEMENTED & VERIFIED (offline); container publishing REUSED

Appended; the section text above is the specification and is **not** rewritten
(append-only, `PROJECT_RULES.md` §2.1). Full record in `D-172` §5.8 and §6.

- **Container publishing was not rebuilt.** `InstagramOutboxPublisher.publish()`
  already drives the D-069 two-step workflow (`create_media_container` →
  `container_status` → `publish_container`) through the injected adapter under
  the D-070 vault and D-072 classifier, with `GraphApiAdapter` behind its D-045
  construction gate and `MockInstagramAdapter` for offline runs. §5.2's first
  bullet is therefore met by reuse (G-6), not by a second implementation.
- **The missing half is the queue** — `local/canonical/instagram_publish_queue.py`
  decides WHEN an already-accepted post goes out: a merchant-owned
  `PeakHoursPolicy` (explicit UTC offset, 15-minute aligned windows, ordered and
  non-overlapping, **no invented default**) selects the next peak slot with pure
  deterministic arithmetic (no wall clock, no timezone database), the slot is
  claimed through the REAL `SchedulingEngine` (D-093/D-094), and at the caller's
  `now_iso` the post is enqueued into the REAL durable Instagram outbox (D-072)
  and marked DISPATCHED. The queue never calls `publish()`, imports no adapter
  and opens no socket.
- **HITL is shared, not duplicated** — `approved_bundle_payload()` (extracted
  from §5.1's hand-off) is the single acceptance gate: ACCEPTED state, bundle
  schema, intact `payload_hash`, `approval.required: true`. The queue re-checks
  it at release time, so a stale acceptance cannot publish.
- **Fail-closed** — a D-094 conflicted post is never released (the calendar keeps
  its conflict row as the record); foreign calendar entries are untouched; an
  outbox refusal leaves the post DUE rather than falsely DISPATCHED; repeats are
  no-ops; cancellation is refused after DISPATCHED.
- **Still open, stated rather than implied done** — no live Meta Graph API call
  was made and none exists on this path (D-045): the live adapter remains behind
  its construction gate; the peak windows themselves are the merchant's business
  input, not a value this repository assumes; §5.1's inline-keyboard gap is
  unchanged; Phase 6 is NOT started.
- **Evidence** — `python3 -m unittest local.tests.test_phase5_instagram_queue` →
  **25 tests OK**; targeted §5.1/§5.2 + phase9 Instagram + phase11 orchestration
  + phase15 scheduling + phase14 wiring → **252 tests OK** (10 pre-existing env
  skips); full sweep → 2729 tests with the same three known live-PostgreSQL
  baseline failures as untouched HEAD; `full_security_sweep` → `clean: true`
  (AST 188 files / 0 findings; entropy 0 flagged; channel isolation 0 findings).

#### Phase 5 closure record (2026-10-22) — §5.1 inline keyboard gap CLOSED; Phase 5 100% complete

Appended; the specification above and the two completion records are **not**
rewritten (append-only, `PROJECT_RULES.md` §2.1). The sentences that call the
inline keyboard an open gap (§5.1's “Still open” bullet and §5.2's “§5.1's
inline-keyboard gap is unchanged”) are superseded for that gap ONLY by this
record. Full record in `D-172` §5.9 and §6.

- **The last named gap is closed.** §5.1's first bullet requires “image group +
  formatted caption + **inline keyboard with direct purchase link**”; §5.1 shipped
  the first two and carried the third as a caption line because the canonical
  Telegram payload had no keyboard field. `telegram_contracts` now has a
  first-class, strictly validated `inline_keyboard` (rows of URL buttons; 8 rows
  / 3 per row / 64-char label / 2048-char URL; `callback_data`, `web_app` and
  `login_url` are not representable), and the bundler emits it from the
  merchant's own `purchase_url` while KEEPING the caption CTA line as the
  fallback.
- **URL hygiene is fail-closed before any dispatch** — public `http(s)` domain
  only (no userinfo, IP literal, `localhost` or single-label host), no
  control/interior whitespace, no bot-token material, no credential-shaped query
  parameter, and the bundler pins every button to the exact `purchase_url`, so a
  foreign domain is refused.
- **Backwards compatible at both seams** — the D-074 idempotency key extends with
  a keyboard digest only when a keyboard exists (pre-keyboard payloads keep their
  exact historical key), and empty keyboards pass no argument to the adapter, so
  pre-keyboard adapters still serve every button-less payload. `sendMediaGroup`
  takes no keyboard in the Bot API, so an album is followed by exactly ONE
  `sendMessage` with the first button's own label and the keyboard.
- **HITL unchanged** — the keyboard is inside the bundle artifact and its
  `payload_hash`, so the M2 acceptance gate and §5.2's release-time re-check
  already cover it; nothing auto-publishes.
- **Still open, stated rather than implied done** — no live Telegram or Instagram
  call, token or credential exists or is requested (D-045); the §5.1 webhook
  trigger remains the existing n8n/direct-publisher seam; Phase 6 is NOT started
  and stays owner-gated behind the payment (open decision 10), shipping (open
  decision 11) and SMS provider selections.
- **Evidence** — `python3 -m unittest local.tests.test_phase5_telegram_keyboard`
  → **23 tests OK**; targeted §5.1/§5.2 + `test_phase10_telegram` → **240 tests
  OK** (2 pre-existing env skips) and `test_phase20_security` → 38 OK (5 skips);
  `compileall` exit 0; `full_security_sweep` → `clean: true` (AST 189 files /
  0 findings; entropy 0 flagged; channel isolation 0 findings); full sweep →
  **2752 tests** with the same three known live-PostgreSQL failures as HEAD.

---

## Phase 6: Payment, Notification & Production Launch
Objective: Financial settlement and deployment hardening.

### 6.1 Payment Gateway Integration
- Iranian payment gateway adapter (ZarinPal / Shaparak IPG) with callback verification and idempotent order updating.

#### §6.1 progress record (2026-10-23) — adapter + DURABLE authority store; the browser-return route is NOT built

Direct owner instruction, in-session. Build-only: nothing was provisioned, no
live database was migrated, nothing was connected, and no credential exists
(D-045). **The §6.1 bullet is NOT complete** — see *Open* below.

- **Provider (supersedes AC-8's "provider UNSELECTED" clause).** Register row 10
  is RESOLVED: **ZarinPal is the primary provider**. AC-8's statement that the
  provider is unselected is superseded for that clause only; its contract —
  server-verified callback, canonical lifecycle, integer Toman, idempotent update
  — is unchanged and is what the adapter implements.
- **Seam reused, not duplicated.** `commerce/src/server/payments/zarinpal.ts`
  implements the EXISTING `PaymentGateway` (`authorize()` = request step,
  `verifyCallback()` = verify step) behind an injected `ZarinPalTransport`. No new
  route, no second dispatch path, and the order write path is unchanged from the
  mock it replaces.
- **The authority lives on the order row (G-1).** A redirect provider issues an
  `authority` at request time and requires the AMOUNT at verify time, but the
  callback carries only the authority. The adapter previously remembered that
  pair in an in-process LRU cache, which works only until the process restarts or
  a second instance answers the callback — at which point a real payment exists
  at the provider and this side has forgotten what it was for. The pair is now
  persisted: `commerce.orders.payment_provider` / `payment_authority` /
  `payment_amount` (migration `commerce/drizzle/0003_sturdy_machine_man.sql`,
  Drizzle-owned per G-3), with `orders_payment_authority_unique`,
  `orders_payment_authorization_complete` (all three or none) and
  `orders_payment_amount_positive`. New port
  `commerce/src/server/payments/authority-store.ts` with the production binding
  `createRepositoryPaymentAuthorizationStore(resolve)`; the repository gained
  `recordPaymentAuthorization` (PENDING-guarded update) and
  `findPaymentAuthorization` (field-narrowed read). The adapter now imports no
  database, so its tests need no connection.
- **Request ≠ paid.** `recordPaymentAuthorization` never touches `status` or
  `payment_ref_id`. An unknown or non-`PENDING` order answers `false` and the
  adapter then refuses to redirect; a save failure is `ZARINPAL_STORE_ERROR` →
  `UNAVAILABLE`; an authority already bound to another order violates the unique
  index and throws rather than guessing which order the money belongs to.
  `payment_amount` is the REQUESTED amount, deliberately separate from
  `total_amount`, in integer Toman, converted to Rial exactly once (`tomanToRial`).
- **Verify reads the store.** Read error → `UNAVAILABLE`; missing or invalid
  record → `DECLINED`; a matching record is confirmed with the provider for that
  amount. A replay re-asks the provider (code 101) instead of replaying a cached
  verdict, so no verdict can outlive the payment; idempotent order updating stays
  where it already was — provider 101 plus the `order_status_history` unique
  `(order_id, to_status)` guard on the webhook pipeline.
- **Verification (offline).** `npm test` → **221 tests / 54 suites, 0 fail**,
  including the new `commerce/src/server/repository-memory.test.ts` (6 tests)
  which drives the storage contract through the REAL checkout path — persist and
  read back with `status` / `payment_ref_id` untouched, wrong-provider miss,
  unknown order, post-`CANCELLED` refusal, retry supersede, one-authority-two-
  orders refusal — and the rebuilt adapter suite (persistence across instances, a
  verify from a gateway that never issued the request, save-failure refusal,
  store-read-error vs unknown-authority, invalid amount, provider re-ask on
  replay). `npm run typecheck` exit 0; `npm run lint` 0 problems;
  `npm run db:check` → "Everything's fine". No live-database run: the new columns
  are exercised by the migration only when an operator migrates (not done here).
- **Open — why §6.1 is not closed.** (a) ZarinPal returns the CUSTOMER'S BROWSER
  with a plain `GET ?Authority=…&Status=OK|NOK`, which carries no HMAC and so
  cannot be received by the signed `POST /api/webhooks/payment`; the route behind
  `ZARINPAL_CALLBACK_URL` must still be written, resolving the order through
  `findPaymentAuthorization` and then driving the SAME transition service. (b)
  `createZarinPalGatewayFromEnv` is bound in no route yet — the mock still
  answers — so `ZARINPAL_MERCHANT_ID` / `ZARINPAL_CALLBACK_URL` /
  `ZARINPAL_SANDBOX` are read by nothing in production. (c) No sandbox
  round-trip has been run and no credential exists (D-045); activation remains
  owner-gated (D-139), and **G0** (owner review of the fashion Phase 5 closure
  records) is still outstanding.

### 6.2 SMS Notification System
- SMS provider adapter (Kavenegar / MelliSMS) for OTP login, order confirmation, and postal tracking notifications.
- **Build record (2026-10-23 — adapter only; nothing sent, no credential).**
  `local/canonical/sms_adapter.py` implements the SMS channel BEHIND the
  existing seam: `SmsAdapter` is the canonical `ChannelAdapter` narrowed to
  `CH_SMS`, bound into the unchanged `NotificationWorker` through
  `sms_channel_binding()` — no new queue, no second dispatch path, no change to
  the order write path (decision row 74; D-089–D-092). `MockSmsAdapter` is the
  DEFAULT (records, sends nothing); `KavenegarSmsAdapter` is live only behind
  `SMS_LIVE_ENABLED=true` + `KAVENEGAR_API_KEY` + an INJECTED transport
  (canonical code opens no socket, D-116). OTP rides Kavenegar's
  `verify/lookup` with the code as a provider-side template token (never
  free text); order confirmation and tracking ride `sms/send` with a locally
  rendered Persian body. A missing template registration, missing sender line,
  unusable `phone_ref` or unmapped template is a permanent Class-B refusal that
  lands in the DLQ — never a guessed body, never a silent drop. **The sealed
  contract registry was not touched:** `checkout.otp.v1`, `order.confirmed.v1`
  and `order.tracking.v1` are declared in `PENDING_REGISTRY_ADMISSION` but NOT
  added to `TEMPLATES`, because the Phase-17 attestation hashes the template
  count and admitting them moves the sealed **D-168** phase-18 chain digest
  (checked in a pristine worktree: the module alone leaves it byte-identical,
  the registry change breaks `test_007`). `order.shipped.v1` is already
  SMS-capable and the adapter appends the tracking code to that body when the
  producer supplies it, so postal tracking is deliverable today. Verified
  offline: `local/tests/test_fashion_phase6_sms_adapter.py` (35 tests) plus the
  full `local/tests` sweep.
- **Open — why §6.2 is not closed.** (a) No credential, sender line or
  registered provider template exists (D-045), so no sandbox round-trip has
  been run and the delivery-report contract remains owner-supplied and
  unimplemented. (b) Owner re-attestation of the D-168 chain digest is required
  to admit the three §6.2 templates; until then OTP and order-confirmation
  events are rejected as unknown templates before queueing. (c) No producer
  emits these events yet: the storefront OTP step (§3.4) and the §2.3 buyer SMS
  trigger are still unbuilt, and the phone is stored as the customer identity
  only.

### 6.3 Deployment & Staging Hardening
- Containerized build verification on local stack, staging deployment readiness, and production cutover checklist.

---

## API Contracts

The flow above implies the following contracts. They are a **derived reading of
the approved flow**, not a new authority: no endpoint here is implemented by
this roadmap, every mutating path stays behind the same owner gates, and the
canonical channel/order/notification seams already specified in the decision
ledger are **reused, not duplicated** (AC-5…AC-9).

| # | Contract | Producer → Consumer | Transport / boundary | Idempotency & safety |
|---|---|---|---|---|
| AC-1 | Catalog write (product, variant matrix, images, stock) | Merchant Admin Panel → catalog database | Server-side write through the canonical service layer; the storefront never writes | One write per merchant action; stock writes are variant-scoped |
| AC-2 | Product publication event (`status → PUBLISHED`) | Catalog database → n8n | Signed n8n webhook trigger (D-004/D-155) carrying product id, revision and target channels | Keyed by product revision — a replayed event is a no-op (D-027) |
| AC-3 | Copy-generation request (`fabric_type`, `season`, `title`, raw notes → Instagram caption + Telegram text + SEO meta/web copy) | n8n → Fashion AI engine (Phase 4) | Internal task call on the AI runtime seam (D-062–D-068); provider credentials stay behind D-045 | Deterministic request key per product revision; output is a proposal, never a publication decision |
| AC-4 | Social distribution enqueue | Fashion AI engine → distribution queue | Durable queue record (Redis/queue): media refs, caption, hashtags, purchase link, target channels, `scheduled_at` | The queue item is the unit of exactly-once dispatch; a duplicate enqueue is suppressed |
| AC-5 | Telegram publication | Distribution worker → Telegram Bot API | `sendMediaGroup` + inline keyboard buy button, on the existing Telegram publisher/ingress seam (D-073–D-076) | SHA-256 publish-idempotency vault + rate pacer; live credentials owner-gated (D-045) |
| AC-6 | Instagram publication | Distribution worker → Meta Graph API | Container create → bounded status poll → publish, on the existing Instagram seam (D-069–D-072) | Publish lock is absolute; usage guard + D-052 error classification; live credentials owner-gated (D-045) |
| AC-7 | Storefront catalog read | Storefront (React Server Components) → catalog read model | Server-side read-only; no client-side write path | Fail-closed: absent or stale evidence renders UNKNOWN/STALE, never a fabricated value |
| AC-8 | Checkout → payment authorisation → order state | Storefront → payment gateway adapter → orders | Server-verified gateway callback; order transitions follow the canonical lifecycle (D-081–D-084) | Callback verification + idempotent order update; money is integer Toman (D-010); provider UNSELECTED (open decision 10) |
| AC-9 | Notification dispatch (OTP, order confirmation, tracking code) | Order/AI services → SMS adapter | Notification contract on the existing notification seam (D-089–D-092) with per-channel fan-out | Deduplication key per event; failed sends go to the DLQ, never silently dropped; provider selection owner-gated |
| AC-10 | Order fulfilment update (status transition, tracking code) | Merchant Admin Panel → orders | Server-side transition through the canonical order lifecycle | Illegal transitions refused; tracking code attached to the fulfilment record, never to a payment record |

Cross-cutting contract rules: every mutating request is server-authorized and
audited on the canonical event store (D-026/D-027); every response and log is
redacted (D-114/D-124); no customer PII, credential, token or PAN appears in a
URL, in client storage or in a log line; and nothing in this contract set may
bypass the owner gates on credentials and activation (D-045/D-139).

---

## UI/UX Requirements

### Cross-cutting (both storefront and merchant panel)
- **RTL Persian-first.** Layout, typography and number formatting are Persian /
  RTL by default; product and customer-facing language is Persian.
- **Design system.** Tailwind CSS with semantic tokens and Shadcn UI / Radix
  primitives; no raw hex in components; token-only color usage (D-171 §3).
- **Accessibility.** WCAG 2.2 AA: text contrast ≥ 4.5:1, non-text/controls
  ≥ 3:1, visible focus indicator, non-color-dependent state (icon + Persian
  label + status code), `prefers-reduced-motion` honoured.
- **Type & numerals.** Body ≥ 16px with 1.5 line-height; Persian numerals in
  prose, Latin numerals only for identifiers and money (D-171 §3, D-010).
- **Fail-closed surfaces.** A panel that has no data says so («بدون داده» /
  UNKNOWN) instead of showing zeros that read as real measurements.
- **Mobile-first.** The merchant panel is designed phone-first (boutique owners
  work from a phone); tap targets ≥ 44×44 pt with ≥ 8px spacing.
- **Performance.** Storefront routes are server-rendered (Next.js Server
  Components); the product grid and filters must stay responsive on mobile
  networks, with images sized and compressed at upload (Phase 2.1).

### Storefront-specific
- Filter and PDP interactions must never require a full page reload
  (faceted filtering, color-driven image swap, size availability states).
- Out-of-stock variants are visibly disabled, not silently rejected at
  checkout.
- Checkout collects nothing that is not required to fulfil the order: phone
  (OTP), name, address, postal code, shipping method.

### Merchant-panel-specific
- Inline editing of stock and price without a page refresh, with the previous
  value recoverable; low stock is flagged at a configurable threshold.
- Every irreversible action (archive, cancel, publish) carries a confirmation
  and leaves an auditable record.

---

## Governance alignment & owner rulings

Recorded so that no conflict is resolved silently (`PROJECT_RULES.md` §2.10,
§4). The rulings below are the owner's, dated, and applied as amendments —
never as rewrites of the decisions they touch (§2.1).

| # | Item | Existing decision it touches | Status |
|---|---|---|---|
| G-1 | Catalog source of truth: is the fashion `products` / `product_variants` / `orders` schema the SSOT, or does WooCommerce remain the ecommerce SSOT with this storefront as a surface over it? | **D-003** (WooCommerce = ecommerce SSOT) + D-034–D-048 (mapping & sync contract) | **RESOLVED 2026-10-10 (owner ruling):** the roadmap schema is the **sole SSOT** for this track; D-003 and the legacy sync patterns are **SUPERSEDED for the Fashion E-Commerce track** (D-172 §4.1). Nothing is dismantled — the scope is the track, and retiring the WooCommerce integration is a separate decision |
| G-2 | Database: is **Supabase** the hosting of the one canonical PostgreSQL database, or a second database? | **D-055** (canonical PostgreSQL = SSOT) | **RESOLVED 2026-10-10 (owner ruling):** the **single canonical instance**; Supabase is a hosting choice for it, not a second database. D-053 local-first promotion and parity still bind; the track's tables live in their own `commerce` namespace (D-172 §4.2) |
| G-3 | Data layer: **Drizzle/Prisma** vs the existing canonical data layer — who owns schema definitions and migrations? | D-055, D-053 (local → staging → production) | **RESOLVED 2026-10-10 (owner ruling):** **Drizzle ORM** owns this track's schema and migrations (`schemaFilter: ['commerce']`); the engine schemas stay owned by `local/db/schema.sql` (D-055). One database, no overlapping ownership, one migration path (D-172 §4.3) |
| G-4 | Provider selections (all still open): payment (decision 10), shipping (decision 11), SMS provider (new), AI provider (decision 9) | open decisions 9/10/11, D-045 | **OPEN** — owner act; Phase 6.1/6.2 name candidate providers only and no live credential exists or is requested |
| G-5 | Media storage for the storefront's `storage_path` / `public_url` | D-049/D-056 (media direction + local emulator), Phase 24 `MediaStoreContract` | **OPEN, not blocking** — the Phase 1 contract stays provider-agnostic (paths and URLs only, no storage SDK bound), keeping the swappability of D-129–D-132 intact until the owner selects a provider |
| G-6 | Channel publishing: reuse the canonical Instagram/Telegram publishers | D-069–D-072, D-073–D-076, D-077–D-080 | **OPEN as a build-time constraint** — the roadmap adds copy generation and scheduling; publishing must stay on the existing seams so there is exactly one dispatch path per channel |

**Footnote (recorded 2026-10-23), additive — the table cells above are not
rewritten.** G-4's **SMS provider** now has a decision identity:
**`DECISIONS.md` Open decision register row 74** (now **Selected 2026-10-23**;
no `D-###` ledger id). The “(new)” wording preserved in the G-4 cell is
historical. Its companions are unchanged: payment = register row 10, shipping =
register row 11, AI provider = register row 9.

**G-4 STATUS UPDATE 2026-10-23 — two of the four selections are CLOSED; the
table cells above are not rewritten.** The owner ruled **payment = ZarinPal
(primary)** and **SMS = Kavenegar (primary)**, each adapted behind the seam it
already had — `commerce/src/server/payments/gateway.ts` (`PaymentGateway`) for
payment, `local/canonical/notification_worker.py` (`ChannelAdapter`) for SMS —
so this is an adapter selection: provider swappable, no new or second dispatch
path, order write path unchanged. **G-4 therefore remains OPEN only for the
shipping provider (register row 11) and the AI provider (register row 9)**;
shipping stays mock-only with no carrier integration. Roadmap §6.1/§6.2 are
unblocked for build.

---

## Execution Protocol
All future development prompts shall explicitly cite the Phase and Section of this document (e.g., "Implement Phase 1, Section 1.2 Products Table") to ensure strict compliance and zero drift from approved specifications.

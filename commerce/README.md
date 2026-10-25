# commerce/ — E-Commerce & Social Publishing track (D-172)

The fashion commerce stack: the **Phase 1 catalog schema** and its typed
contracts implemented against the canonical PostgreSQL instance, the **Phase 2
merchant admin panel** (`/admin`) and the **Phase 3 customer storefront**
(`/`, `/catalog`, `/products/[slug]`, `/checkout`).

- **Plan of record:** [`docs/roadmap/FASHION_ECOMMERCE_ROADMAP.md`](../docs/roadmap/FASHION_ECOMMERCE_ROADMAP.md)
  (Phase 1 = §1.1–§1.5; every change on this track must cite its Phase/Section)
- **Decision:** [`D-172`](../docs/decisions/D-172-fashion-ecommerce-roadmap.md) —
  owner rulings **G-1** (this schema is the sole SSOT for the track; D-003 is
  superseded *for this track only*), **G-2** (one canonical PostgreSQL instance,
  Supabase as its hosting — never a second database), **G-3** (Drizzle owns this
  track's schema and migrations)

## Why this package exists separately

`control-plane/` is a **read-only presentation surface** and must never own or
write the SSOT (D-171 §2.1). The commerce track's data model therefore lives
here, in its own package, in its own `commerce` PostgreSQL namespace — one
database, separated ownership, no overlapping migration authority.

| Domain | Owner |
| --- | --- |
| `commerce` namespace (this package) | `commerce/drizzle.config.ts` → `drizzle/` |
| `canonical`, `registry`, `events`, `provenance`, `oms`, `hitl`, `admin`, … | `local/db/schema.sql` (D-055), applied by `local/scripts/apply_schema.py` |

`schemaFilter: ['commerce']` is pinned in the Drizzle config so a fashion
migration can never render against — or mutate — an engine schema.

## Layout

```
src/db/schema/   schema.ts (namespace) · enums.ts · catalog.ts (§1.1–§1.4)
                 ordering.ts (§1.5, incl. the order_status_history audit table)
                 promotions.ts (§2.4) · relations.ts · index.ts
src/db/index.ts  inert client factory (no connection string, no import-time I/O)
src/contracts/   typed read models, raw insert models and write payloads
                 (incl. storefront.ts — the customer surface's view of them)
src/lib/         pure rules shared by both surfaces: validation, variant matrix,
                 inventory/order/coupon rules, cart + cart store, catalog
                 filters, checkout arithmetic, variant selection (the PDP's
                 colour × size matrix), shipping, size chart, display copy
src/server/      db-context (fail-closed gate) · repository.ts (Postgres impl) ·
                 repository-memory.ts (test double) · services/ (read + write
                 paths) · actions/ (the 'use server' edge) · payments/ (the gateway
                 iface, the ZarinPal adapter, the durable authority store and the
                 webhook signature gate) · notifications/ (the order-confirmation
                 outbox dispatcher, the SMS port with its mock/Kavenegar adapters
                 and the operator trigger)
src/app/         (storefront)/ — the customer surface · admin/ — the merchant panel
                 api/webhooks/payment — the signed async callback endpoint
                 api/payments/zarinpal/callback — the browser return (shim only)
                 api/internal/notifications/dispatch — the outbox trigger (shim)
                 healthz — the fail-closed readiness probe (shim)
src/components/  ui/ (primitives) · admin/ · storefront/
drizzle/         generated migration SQL + journal (committed, never hand-edited)
```

## Commands

```bash
npm ci                 # install (lockfile committed)
npm run dev            # dev server (both surfaces)
npm run typecheck      # tsc --noEmit                      — offline
npm run lint           # eslint .                          — offline
npm test               # compiles src/**/*.test.ts to .test-build and runs node --test
npm run db:generate    # regenerate SQL from the schema    — offline
npm run db:check       # journal/schema consistency        — offline
npm run verify         # typecheck + lint + test + db:check — offline
npm run build          # production build                  — offline
npm run db:migrate     # APPLY migrations — needs DATABASE_URL, owner-gated
npm run db:studio      # inspect — needs DATABASE_URL, owner-gated
```

The test harness adds no dependency: `tsc` (already installed) compiles the
tests and `node --test` runs them, with `test/alias-resolver.mjs` mapping the
`@/…` alias at load time (and retrying a bare dependency subpath as `X.js` when
Node cannot resolve it — `next` ships extensionless files and no `exports` map).
The live suite (`npm run smoke:db`) is separate and opt-in — see below.

`generate` / `check` never open a connection. Only `migrate` / `studio` read
`DATABASE_URL`, and the callback endpoint reads
`COMMERCE_PAYMENT_WEBHOOK_SECRET` (unset today, and unset means the endpoint
refuses every callback with `503` rather than accepting an unsigned one); see
`.env.example` for the placeholder contract. **No credential
is stored in this repository** (D-045/D-124), and applying a migration to any
shared environment is an owner-gated act (D-139) — the local canonical
PostgreSQL container from `local/infra/docker-compose.yml` (D-053/D-054) is the
development target.

## Data conventions

- **Money and stock are integers.** Prices and amounts are `bigint` in integer
  Iranian Toman (D-010); no floating point anywhere. Stock and quantities are
  `integer` with `CHECK` guards (`stock_quantity >= 0`, `quantity > 0`), matching
  the canonical schema's house style.
- **Identifiers** are `uuid` generated by PostgreSQL (`gen_random_uuid()`;
  PostgreSQL 13+, the local stack runs 16).
- **Nullability** follows the roadmap's explicit `nullable` markers. Absence is
  inferred only where the lifecycle requires it: `orders.payment_ref_id` (before
  payment) and `orders.tracking_code` (before shipment).
- **A UNIQUE constraint is already an index**, so §1.1/§1.2's "unique, index" is
  realised once, never as a duplicate index.
- **Deletion semantics:** `products → variants/images` CASCADE,
  `orders → order_items` CASCADE, `product_images.variant_id → SET NULL`
  (media survives a variant removal), and `customers`/`product_variants`/
  `categories` are `RESTRICT`-protected so order and catalog history is never
  cascaded away.
- **Matrix integrity:** `(product_id, size, color_name)` is unique — the Phase 2.1
  variant generator cannot produce duplicates, and `sku` is globally unique.

## Live database harness (opt-in, disposable)

The Phase 2 write paths are verified against a REAL PostgreSQL 16 server through
`docker-compose.db.yml` — a throwaway container published on **127.0.0.1:55432
only**, with its own network and volume. Nothing auto-starts it (no `restart:`
policy, no hook in the repository); every step is an explicit operator command:

| command | what it does |
| --- | --- |
| `npm run db:up` | starts the harness and waits for its healthcheck |
| `npm run db:down` | stops it, keeping the volume |
| `npm run db:migrate` | applies the committed migrations (`COMMERCE_DATABASE_URL`) |
| `npm run db:reset` | drops schema `commerce` + the migration journal, then re-applies 0000–0004 |
| `npm run db:seed` | loads `scripts/seed-catalog.sql` — the local demo catalog (3 categories, 3 products, 15 variants) |
| `npm run smoke:db` | runs the live suites serially (migrations, §2.1–§2.4 writes and refusals, §3.1–§3.4 storefront funnel, the audit trail + callback seam) |

```bash
export COMMERCE_DATABASE_URL=postgresql://commerce_smoke:commerce_smoke_local_only@127.0.0.1:55432/commerce_smoke
npm run db:up && npm run db:migrate && npm run smoke:db
```

`db:seed` is development convenience, not a migration and not test fixture data:
`scripts/seed-catalog.sql` is **insert-only** — every statement skips a row that is
already present (category slug / product slug / variant sku), so a second run
inserts nothing and rewrites no price, stock, description or category. It also
does not restore values a checkout or an edit has changed; `db:reset` + `db:seed`
is the way back to the pristine demo catalog. `scripts/seed-catalog.mjs` validates
that its target is loopback:55432 **before it connects** and runs the file in one
transaction, so a shared database is out of reach and a failed seed changes
nothing. It carries **no** `product_images` rows — media storage is still the open
G-5 decision, so the catalog ships without dead URLs — and `smoke:db` never depends
on it: the live suites drop and re-apply the schema themselves.

The suites SKIP with a named reason when `COMMERCE_DATABASE_URL` is absent (they
never guess a target: an absent configuration is a refusal, not a pass) and
refuse a non-loopback target, so staging and production stay out of reach. All
three live files share this one database and each resets the `commerce` schema
and re-applies the committed migrations in `before()`, so `smoke:db` passes
`--test-concurrency=1`: in parallel processes the second `drop schema` would
truncate the first suite's fixtures mid-run.
`db:reset` — the one destructive command — refuses anything that is not
loopback:55432. The credentials in the compose file are the disposable
container's own literals; no real credential exists in this repository.

## Verification status

Phase 1: `typecheck` exit 0 · `drizzle-kit generate` produces exactly the seven
roadmap tables · `drizzle-kit check` exit 0 · generated DDL applied and probed on
PostgreSQL 16.15 (the local-stack image) in a throwaway container with no
published ports: 7 tables, 2 enums, 80 constraints, 23 indexes, 10/10 refusal
cases refused, cascades and `SET NULL` confirmed.

Phase 2 (§2.1–§2.4): `npm run verify` exit 0 (typecheck, lint, 97 tests in 23
suites, `db:check`) · `build` exit 0 · **live PostgreSQL 16.15 pass** —
migrations 0000 + 0001 applied through the project's own toolchain (8 tables in
schema `commerce`, 3 enums, journal at 2 rows), then `npm run smoke:db`
**22/22 pass, exit 0, twice consecutively** against the real Postgres repository:
product graph writes, stock/price edits, coupon state derivation, the order
lifecycle, and every refusal path (stock < 0, base_price < 0, duplicate
matrix cell, duplicate SKU, duplicate coupon code, percent > 100, unknown enum
label, quantity 0, and illegal/terminal order transitions — each verified to
leave the stored row untouched). The live pass also found and fixed two real
defects the in-memory tests could not see: `listProducts()` reported
`variantCount`/`imageCount` = 0 and `listOrders()` reported `itemCount` = 0 for
every row, because Drizzle renders column references inside a raw `sql` chunk
unqualified (`where "product_id" = "id"` bound both names to the subquery's own
table — a condition that is never true). Both read models now aggregate over
LEFT JOINs and are pinned by live assertions. Details in D-172 §6.

Phase 3 (§3.1–§3.4, customer storefront): `npm run verify` exit 0 (typecheck,
lint 0 problems, **155 tests in 40 suites**, `db:check`) · `build` exit 0 with
`/`, `/catalog`, `/checkout` and `/products/[slug]` dynamic · browser-verified on
the dev server (RTL, the fail-closed notice on every data surface and **no
checkout form at all** with no canonical connection, and the cart exercised
end-to-end: a seeded basket adopted after hydration, the drawer listing it, and a
quantity change written back to `localStorage`). With no connection the
storefront still refuses rather than rendering an empty shop.

Phase 3 **live pass** (with the harness below up): `npm run smoke:db` → **41/41
pass, exit 0, twice consecutively** — 22 Phase 2 subtests plus 19 in
`src/__tests__/live-db/phase3-storefront-live.test.ts`, which drives the real
repository through the whole customer funnel (category counts and rails, facet
derivation and every filter, PDP stock levels and price resolution, the order
write with its items, coupon counter and normalised customer row, the refusals)
and asserts against rows read back from PostgreSQL. It also proves the two
properties the in-memory double cannot: an order **consumes** stock atomically in
its own transaction (returned exactly once on cancellation, coupon usage not
refunded), and two simultaneous buyers of the LAST piece yield exactly one order
and zero stock. That pass found and fixed two real defects — a `for update of
"commerce"."product_variants"` lock clause PostgreSQL refuses (42601), which had
made **every** checkout fail before it could write, and the complete absence of
stock consumption. `smoke:db` runs the live directory with
`--test-concurrency=1` because both live files share one database and each resets
it. Details in D-172 §5.3 and §6.

Phase 3 **close-out** (same day, after the live pass): the reservation policy the
live pass discovered is now the track's stated rule (**a** an order consumes its
lines' stock atomically with the `PENDING` row, **b** a cancellation returns
exactly those quantities once, **c** a redeemed coupon is not refunded), written
into the `placeOrder` contract on `CommerceRepository` rather than only into
prose. Two new offline suites guard it on every `npm test`: `src/lib/
variant-selection.ts` (+ its tests) holds the PDP's colour × size rules — which
colour opens, which sizes are disabled instead of hidden, the level the badge may
claim, the cap, the gallery scope and the cart line — and
`src/__tests__/funnel.test.ts` walks the whole journey in eight stages (catalog →
facets → matrix → persisted cart drawer → pre-flight → order → **merchant grid
reconciliation** → cancellation), ending by driving the real `placeOrderAction`
to prove it refuses `DB_NOT_CONFIGURED` instead of faking an order. The merchant
side is asserted through the panel's own rules (`inventorySummary`, `stockState`,
`filterInventory`), so an order that empties a variant is shown as «ناموجود» on
`/admin/inventory` immediately and a cancellation returns the grid to its
pre-order state. Evidence on the final tree: `npm run verify` exit 0 (typecheck,
lint 0 problems, **176 tests / 46 suites**), `npm run build` exit 0 (same eleven
routes), `npm run smoke:db` **41/41 exit 0** against the loopback harness.

Phase 4 **transition** — the order audit trail and the payment-callback ingress
seam: `commerce.order_status_history` (migration `0002`) records every status an
order reaches — previous status, new status, WHO asked (`STOREFRONT` ·
`MERCHANT_PANEL` · `PAYMENT_CALLBACK` · `SYSTEM`) and optional metadata — appended
by the SAME transaction that moves the order, so a status change cannot commit
without its row and a refused one leaves nothing. `POST /api/webhooks/payment`
(`src/app/api/webhooks/payment/route.ts`) is the async callback endpoint, and it
refuses in a fixed order: no secret configured → `503`; no/forged/mismatched
HMAC-SHA256 signature over the raw body → `401`; unparseable or out-of-contract
payload → `400`; no canonical connection → `503`; unknown order → `404`; a
lifecycle-illegal move → `409`. A REPLAY is answered `200 { duplicate: true }` and
writes nothing, because a provider that sees an error retries forever. The
provider is still an open owner decision (G-4 / decision 10), so the endpoint
processes nothing today. Evidence: `npm run verify` exit 0 (**194 tests / 51
suites**), `npm run build` exit 0 (twelve routes, `/api/webhooks/payment` present),
`npm run smoke:db` **54/54 exit 0, twice consecutively** (22 Phase 2 + 19 Phase 3
+ 13 Phase 4-transition subtests — including a REAL `23505` provoked by hand to
prove the status move rolls back when its audit row cannot be written), plus a
refusal matrix exercised over real HTTP against a running `next start`: unsigned
`503` with no secret, `SIGNATURE_MISSING`/`SIGNATURE_MISMATCH` `401` with one,
`DB_NOT_CONFIGURED` `503` when signed but unconnected, `ORDER_NOT_FOUND` `404`
when connected, `INVALID_EVENT`/`INVALID_JSON` `400`, `405` on GET — and the same
server accepting a correctly signed `PAID` delivery for a real harness order
(`200`, `orders.status = PAID` + `payment_ref_id` + the `PAYMENT_CALLBACK` audit
row in SQL), then answering the identical delivery `duplicate: true` with no
third row.

**Not started:** the Phase 4 AI engine itself and Phases 5–6 (copywriting, social
automation, payment/SMS/launch). Open items, unchanged and recorded: media
storage (G-5) is still unselected so a submission with pending image bytes is
refused with its reason; the §2.3 buyer SMS stays a Phase 6 adapter (G-4), so
checkout has **no OTP** — the phone number is validated and stored as the customer
identity; payment is a fail-closed `MockPaymentGateway` that answers `UNAVAILABLE`
and leaves the order `PENDING`, and there is no provider-specific webhook scheme
yet because there is no provider; the audit trail is written and read back by
tests but has **no panel surface** yet, and it covers ORDER transitions only — a
product status change (archive/publish), a stock/price edit and a coupon edit are
still unrecorded; image zoom / swipe gestures and mobile
gesture behaviour remain untested on a device; and stock is now reserved at
checkout rather than at payment capture, which is the owner's ruling on the Phase
3 live pass (a cancelled order restocks; coupon usage is not refunded). Nothing is
deployed; no credential exists or is requested (D-045/D-139).

Phase 6 **payment, notification and packaging** (§6.1–§6.3) — this supersedes the
“Phases 5–6 not started” sentence of the Phase 4 record above, for §6.1–§6.3
only; the Phase 4 AI engine and Phase 5 social automation remain separate tracks
with their own records.

- **§6.1 payment.** `src/server/payments/zarinpal.ts` implements the EXISTING
  `PaymentGateway` (`authorize()` = request step, `verifyCallback()` = verify
  step) over an injected transport; the `authority → amount` pair is persisted on
  the order row (`payment_provider` / `payment_authority` / `payment_amount`,
  migration `0003`) behind `authority-store.ts`, so a callback verifies in a
  process that never issued the request. `GET /api/payments/zarinpal/callback`
  asks the provider for the amount PERSISTED at request time (Toman → Rial once,
  never the query string) and applies the move through the SAME
  `applyPaymentCallback` pipeline the signed webhook uses — one write path, one
  audit vocabulary, one idempotency boundary, and concurrent duplicates converge
  to one `PAID` row.
- **§6.2 notification.** The `PAID` transaction also enqueues one
  `commerce.notification_outbox` row (migration `0004`; UNIQUE
  `(order_id, kind, channel)`, `ON CONFLICT DO NOTHING`), so a provider outage
  can never fail a payment. `src/server/notifications/` holds the dispatcher
  (claim `PENDING → SENDING` under `FOR UPDATE SKIP LOCKED`, bounded retries,
  stale-lease reclaim), the `SmsChannel` port with `MockSmsChannel` as the
  DEFAULT and `KavenegarSmsChannel` live only behind credentials, and the
  operator trigger `POST /api/internal/notifications/dispatch` (bearer token,
  constant-time compare, `no-store`, counts only). The queue stores **no phone
  number and no body** — both are resolved at dispatch. There is **no
  scheduler**: a cron or operator call drains the queue, and not calling it is
  safe.
- **§6.3 packaging.** `Dockerfile` (digest-pinned `node:20-alpine`, `standalone`
  runner, `USER node`, `node -e` probe), `.dockerignore`, and
  `docker-compose.local.yml` (loopback `127.0.0.1:13000`, `read_only`,
  `cap_drop: [ALL]`, `no-new-privileges`, tmpfs `/tmp` + `/app/.next/cache`,
  512 MiB / 1.0 CPU, every env reference `${VAR:-}`). `GET /healthz` answers
  **200** only when the canonical database resolves `SELECT 1`, and **503**
  `db_unconfigured` / `db_unreachable` otherwise, with `no-store` on every
  answer. Every unset variable refuses rather than degrading — see
  `.env.example` for the names and the refusal each one produces.
- **Evidence.** `npm run verify` → **298 tests / 74 suites, 0 fail** (lint 0,
  typecheck exit 0, `db:check` clean); `npm run smoke:db` → **68 / 0** against the
  disposable loopback harness with migrations 0000–0004; `docker build` → rc=0,
  292 MB, every Phase 6 route in the shipped route table; the container runs
  healthy under the hardened posture with `/healthz` 200, `db_unconfigured` 503
  and `db_unreachable` 503 reproduced in-image; the dispatch endpoint answers
  503/401/405 in-image and drains a real row exactly once (`claimed 1 / sent 1`,
  then `claimed 0`); `SMS_LIVE_ENABLED=true` without a key is a hard
  `SMS_LIVE_MODE_MISSING_CREDENTIAL` refusal that claims nothing.
- **Not done, owner-gated.** No credential exists (D-045), so **no** payment or
  SMS has ever reached a provider; nothing is deployed (D-139); the sealed
  template registry is untouched (D-168), which governs the canonical worker and
  the unbuilt OTP step, not this app's own bodies; the image is not pinned into
  any deployment manifest (G-5/C-8). Cutover status, clause by clause:
  [`docs/deployment/phase-6-cutover-checklist.md`](../docs/deployment/phase-6-cutover-checklist.md)
  — **build/artifact GO, production activation NO-GO**.

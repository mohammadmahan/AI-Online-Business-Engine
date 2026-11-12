# Multi-Carrier Shipping Track (MCS)

- **Status:** COMPLETE (local/offline) — owner-approved, 2026-11-12
- **Parent program:** D-172 fashion commerce, Phase 3 checkout + Phase 6 fulfilment
- **Parent gate:** G0 ACCEPTED / RESOLVED (D-173); B1–B6 local/offline preparation
- **Owner decision:** D-175 (three-carrier local registry and selection policy;
  real carrier integration remains owner-gated)
- **Implementation home:** `commerce/`
- **Verification base:** `main` at `0929f473e70bde6e8c92f3142c3aee6572aeebce`
- **Canonical checklist:** this document (tasks `MCS-01`…`MCS-08`)

This is an implementation track over the existing checkout/order surfaces. It
does not create a second OMS, replace the canonical Phase 12 shipping boundary,
or authorize a live carrier.

---

## 1. Purpose and position

The owner approved three customer-visible shipping choices — **Iran Post**,
**Tipax**, and **local courier** — that must be:

- selectable at checkout only when enabled and eligible for the destination and
  parcel;
- ordered by declarative priority, with the first eligible option preselected;
- changeable to any subset, or exactly one carrier, through configuration only;
- stored immutably on the order and visible to the merchant;
- priced by one server-authoritative rule, with the displayed price guaranteed
  to equal the stored price;
- fail closed with a clear Persian message when no carrier is eligible;
- backed by one adapter seam with a local sandbox implementation per carrier.

This sits inside the existing D-172 Phase 3 checkout/order implementation and
Phase 6 fulfilment surface. It is **not** a new checkout, order table, payment
path, dispatch path, OMS, or Phase 12 replacement.

---

## 2. Verified baseline

### 2.1 What already exists

| Area | Verified current state |
| --- | --- |
| Checkout choice | `commerce/src/lib/shipping.ts` exports a hardcoded `SHIPPING_METHODS` array: `POST_PISHTAZ` (45,000), `EXPRESS_COURIER` (90,000), `TIPAX_PAY_ON_DELIVERY` (0). |
| Checkout UI | `checkout-form.tsx` renders every method, preselects `POST_PISHTAZ`, and treats an unknown id as `0` only in the local display variable; the server refuses it. |
| Server validation | `server/services/checkout.ts` and `repository.ts` call `shippingAmountFor(id)`; unknown ids return `SHIPPING_UNKNOWN`. |
| Order storage | `orders.shipping_amount` exists. **No `carrier_id`/`carrier_name` column exists**, so the chosen carrier itself is not persisted. |
| Admin | `/admin/orders` shows status, total, tracking code and print link; it does not show the chosen carrier. |
| Parcel data | Commerce has **no per-product weight or dimensions**. The current selection does not validate weight, dimensions or destination coverage. |
| Payment | Local mock / fail-closed `UNAVAILABLE`; unchanged by this track. |
| Canonical Phase 12 | `local/scripts/live_wiring_phase12_igniter.py` contains `SandboxCarrier`, deterministic `shipment_key`/`parcel_hash`, capability caps and `Phase12Attestation`. It is a **Python canonical dry-run boundary**, not the commerce checkout path, and it performs no live booking. |
| E2E | `commerce/scripts/check-storefront-e2e.mjs` covers the checkout journey but does not assert carrier options, eligibility, preselection or persistence. |
| Provider status | Decision-register row 11 (shipping provider) was OPEN. Real credentials, API calls and deployment remain gated by D-045/D-139. |

### 2.2 What is missing

1. A declarative carrier registry (enablement, priority, coverage, limits,
   pricing, ETA, capabilities).
2. Eligibility and quote computation from address + estimated parcel.
3. Configuration-only modes: all / subset / exactly one.
4. Persistence of the chosen carrier on the order and admin visibility.
5. A local adapter contract + sandbox adapter per carrier, with typed failure,
   timeout and no cross-carrier fallback.
6. Automated coverage for the three configuration modes and negative paths.

### 2.3 Known constraint: parcel weight

Commerce has no SKU weight/dimension columns. MCS therefore uses a **declared
parcel-estimation policy** in the registry (`packagingGrams`, `gramsPerItem`,
fixed parcel dimensions). This is local, deterministic and validated against
carrier limits; it is not a claim that an item weighs exactly that. Per-SKU
weights can replace the estimator later through the same request shape without
changing checkout, persistence or adapters.

### 2.4 Relationship to the canonical shipping boundary

The TypeScript adapter seam in `commerce/` is a **merchant/storefront adapter
boundary for local sandbox use**, not a second OMS and not a re-implementation
of Phase 12. It mirrors the canonical parcel identity rules:

- `parcelHash` covers weight, dimensions and declared value only; the address is
  never part of parcel identity or any hash;
- `shipmentKey(orderId, carrierId, parcelHash)` is deterministic SHA-256;
- no shipment is persisted, booked, labelled or sent by checkout in this track.

`Phase12Attestation`, `SandboxCarrier` and the canonical OMS remain unchanged
and owner-gated. No commerce code calls them and no Python code is modified.

---

## 3. Scope

### In scope

- Declarative registry for the three approved carriers using the existing stable
  shipping method ids:
  - `POST_PISHTAZ` → Iran Post / پست ایران
  - `TIPAX_PAY_ON_DELIVERY` → Tipax / تیپاکس
  - `EXPRESS_COURIER` → local courier / پیک محلی
- Enable/disable, priority, nationwide/city coverage, weight/dimension limits,
  flat/per-kg/free/COD pricing, ETA and capability flags.
- Pure eligibility/quote functions shared by browser display and server write.
- Configuration environment surface and startup validation.
- `orders.carrier_id` + `orders.carrier_name` (nullable for legacy orders).
- Checkout rendering only eligible carriers, first eligible preselected, no-
  eligible fail-closed state.
- Admin order list carrier column with legacy fallback.
- Adapter contract, deterministic parcel/shipment hashing, three sandbox
  adapters, timeout/retry taxonomy and tests.
- Unit, live-local and browser E2E coverage; documentation/evidence.

### Explicit non-goals

- Real Iran Post/Tipax/local-courier API calls, credentials, contracts, label
  purchase, pickup booking, barcode issuance or tracking polling.
- Any production/staging deployment, DNS/TLS, secrets or provider activation.
- Changing payment, SMS, AI, media or notification behavior.
- Creating a second order/shipment/OMS table or a second status lifecycle.
- Automatic carrier fallback after an adapter failure.
- Per-SKU weight/dimension authoring UI (future extension; estimator documented).
- Redesigning the checkout or admin panel.
- Backfilling historical orders with a guessed carrier.

---

## 4. Carrier registry model

`commerce/src/lib/shipping.ts` owns the client-safe types, default registry,
validation and pure quote functions.

### 4.1 Carrier record

| Field | Contract |
| --- | --- |
| `id` | Stable uppercase identifier; equals the persisted shipping method id. |
| `name` | Persian display name. |
| `enabled` | Base enablement; environment may override. |
| `priority` | Positive integer; lower first. |
| `coverage` | `NATIONWIDE` or `CITIES` with a non-empty list of province/city names matched against the free-text address. |
| `limits` | `maxWeightGrams`, `maxLengthCm`, `maxWidthCm`, `maxHeightCm` — positive integers. |
| `pricing` | `FLAT(amount)`, `PER_KG(base, perKg)`, `FREE`, or `CASH_ON_DELIVERY`; integer Toman only. |
| `deliveryEstimate` | `minDays`, `maxDays`, Persian label. |
| `capabilities` | `tracking`, `barcode`, `cashOnDelivery`, `pickupPoint` booleans. |
| `description` | Customer-facing Persian explanation. |

### 4.2 Parcel policy

Registry-level `parcelPolicy` declares `packagingGrams`, `gramsPerItem`,
`lengthCm`, `widthCm`, `heightCm` and `maxItems`. The estimate is:

```
weightGrams = packagingGrams + totalQuantity * gramsPerItem
dimensions  = configured parcel dimensions
```

An empty/oversized cart fails closed before any carrier is offered.

### 4.3 Default three-carrier registry

| id | Name | Priority | Coverage | Limits | Pricing | Capabilities |
| --- | --- | --- | --- | --- | --- | --- |
| `POST_PISHTAZ` | پست ایران (پیشتاز) | 10 | nationwide | 30 kg, 150 cm axes | flat 45,000 | tracking, barcode |
| `TIPAX_PAY_ON_DELIVERY` | تیپاکس | 20 | nationwide | 30 kg, 150 cm axes | COD (0 in order) | tracking, barcode, COD |
| `EXPRESS_COURIER` | پیک محلی | 30 | Tehran/Karaj/Alborz/Shahriar/Eslamshahr | 15 kg, 100 cm axes | flat 90,000 | tracking, pickup point |

The values are local commercial placeholders, not carrier quotations. They are
data, not UI logic; the owner can change them without touching checkout.

---

## 5. Selection policy

1. Compute the estimated parcel from cart quantity.
2. Filter to `enabled` carriers.
3. Filter by destination coverage and parcel limits.
4. Sort by `priority` ascending, then stable id.
5. Preselect the first eligible carrier.
6. If the customer changes address/cart and the selected carrier is no longer
   eligible, select the new first eligible carrier.
7. If none are eligible, render exactly:
   **«هیچ روش ارسالی برای این نشانی و سبد خرید موجود نیست.»**
   and disable submission. The server independently refuses with
   `SHIPPING_INELIGIBLE`.
8. An unknown id is `SHIPPING_UNKNOWN`; a known but disabled carrier is
   `SHIPPING_DISABLED`. Neither is ever priced as zero or replaced silently.

### 5.1 Three modes through configuration only

`COMMERCE_SHIPPING_ENABLED` is a comma-separated id list:

| Mode | Configuration |
| --- | --- |
| All three | variable unset → registry defaults (all enabled) |
| Subset | `COMMERCE_SHIPPING_ENABLED=POST_PISHTAZ,TIPAX_PAY_ON_DELIVERY` |
| Exactly one | `COMMERCE_SHIPPING_ENABLED=EXPRESS_COURIER` |
| None (negative test/emergency) | `COMMERCE_SHIPPING_ENABLED=none` |

`COMMERCE_SHIPPING_PRIORITY` optionally reorders known ids. Any unknown id,
duplicate id, malformed value or invalid full JSON override is a startup
configuration error; the checkout surface then fails closed with a clear notice.

Full pricing/coverage/limits changes can be supplied as
`COMMERCE_SHIPPING_CONFIG_JSON` (validated object). The resolved public config is
passed from the server page to the client, so the browser and the write path
read one snapshot. The server still recomputes eligibility and price from that
same snapshot before writing.

---

## 6. Price and persistence contract

- The browser never submits a price. It submits only the carrier id.
- The server recomputes the quote from its resolved config, the submitted
  shipping address and the cart quantities.
- `orders.shipping_amount` stores the server quote; `orders.total_amount`
  includes it.
- The checkout success response reports the stored totals. The displayed
  shipping amount is replaced by the server result on success.
- New columns:
  - `orders.carrier_id varchar(64) null`
  - `orders.carrier_name varchar(255) null`
  - CHECK: both null or both non-empty.
- New orders always write both. Historical rows remain valid with NULL and are
  displayed as **«ثبت‌نشده (سفارش قدیمی)»**.
- No update path changes `carrier_id`/`carrier_name`/`shipping_amount` after
  placement. The order lifecycle only changes status/tracking. A live test
  asserts the stored pair survives transitions.
- Admin `/admin/orders` adds a **حامل** column using the stored snapshot, never
  a re-derived current registry label. Packing slip shows the stored carrier.

---

## 7. Adapter contract

`commerce/src/server/shipping/carrier-adapter.ts`:

### 7.1 Request

```
{
  orderId: string,
  carrierId: string,
  shipmentKey: string,        // deterministic SHA-256
  parcel: {
    weightGrams: number,      // integer, 1..100000
    lengthCm, widthCm, heightCm, // integer, 1..150
    declaredValueToman: number   // integer, 0..10^12
  },
  destination: { address: string } // used by the operation, never hashed
}
```

### 7.2 Response

Success: `{ ok: true, carrierId, trackingNumber, barcode, labelReference,
pickupPoint?, dryRun: true }`.

Failure: `{ ok: false, error: { kind, code, retryable, message } }` where `kind`
is `TIMEOUT | TRANSPORT | REFUSED | INVALID_REQUEST | NOT_CONFIGURED`.

### 7.3 Rules

- Every adapter implements one interface: `createShipment(request)`.
- `sandboxCarrierFor(id)` returns Iran Post, Tipax or local-courier sandbox.
- No adapter performs network I/O, reads a credential or writes a shipment row.
- Timeout default 15 s, injectable for tests; retries only `TIMEOUT`/`TRANSPORT`,
  maximum 2, with bounded backoff. `REFUSED`, `INVALID_REQUEST` and
  `NOT_CONFIGURED` are not retried.
- An adapter failure is returned to the caller. There is **no fallback** to
  another carrier: the chosen carrier is part of the order intent.
- `parcelHash` and `shipmentKey` mirror D-162's address-free identity rules.

---

## 8. Configuration surface

| Concern | Location |
| --- | --- |
| Carrier base data (names, coverage, limits, pricing, ETA, capabilities, parcel policy) | `commerce/src/lib/shipping.ts` default registry |
| Enablement | `COMMERCE_SHIPPING_ENABLED` |
| Priority | `COMMERCE_SHIPPING_PRIORITY` |
| Full validated override | `COMMERCE_SHIPPING_CONFIG_JSON` |
| Startup validation | `commerce/src/instrumentation.ts` → `getShippingConfig()` |
| Runtime resolution | `commerce/src/server/shipping/config.ts` |
| Public snapshot to browser | checkout server page prop |

Missing enablement means defaults (all three). Missing full JSON means defaults.
Invalid JSON/list/priorities throws a named `ShippingConfigError` at startup.
The checkout page catches a runtime resolution failure and renders the
fail-closed notice instead of a form. No credential is read.

---

## 9. Ordered tasks

| ID | Task | Depends on |
| --- | --- | --- |
| MCS-01 | Baseline, canonical track document and decision/register reconciliation | — |
| MCS-02 | Registry, validation, parcel estimate, quote/eligibility pure module + unit tests | MCS-01 |
| MCS-03 | Order schema/migration, repository persistence, legacy fallback + live tests | MCS-02 |
| MCS-04 | Server-authoritative checkout validation and dynamic client selection | MCS-02/03 |
| MCS-05 | Adapter contract, parcel/shipment hashes, three sandbox adapters, retry/timeout tests | MCS-02 |
| MCS-06 | Admin order list and packing-slip carrier display | MCS-03 |
| MCS-07 | E2E extension for three carriers, preselection, persistence; config-mode tests | MCS-04/06 |
| MCS-08 | Full verification, evidence, docs close-out, commit/push | MCS-03…07 |

### MCS-01 — baseline and canonical record

- **Objective:** verify the baseline and document scope, decisions and config.
- **Affected:** governance docs only.
- **Prerequisites:** current Git state; shipping/checkout/order documents read.
- **Artifacts:** this document; D-175; updates to `MASTER_PLAN.md`, `TODO.md`,
  `docs/README.md`, fashion roadmap, decision register row 11 (additive note).
- **Verification:** links resolve; row 11 history not rewritten; no code edit.
- **Acceptance:** current implementation, gap, gates and task order are explicit.
- **Evidence:** baseline commit, contradiction list, doc paths.

### MCS-02 — registry and pure selection/quote

- **Objective:** one client-safe registry and pure functions for validation,
  parcel estimate, eligibility, priority and quote.
- **Affected:** `lib/shipping.ts`, `contracts/storefront.ts`, tests.
- **Prerequisites:** MCS-01.
- **Artifacts:** registry types/defaults; `validateShippingConfig`;
  `resolveShippingConfig` variants; `estimateParcel`; `quoteShipping`;
  `eligibleShippingOptions`; compatibility exports for existing callers.
- **Verification:** unit tests for schema validation, every price model,
  coverage, limits, priority, unknown/disabled, all/subset/one modes.
- **Acceptance:** all three modes proven; invalid config refuses; unknown id
  never returns 0.
- **Evidence:** test names/counts and exact commands.

### MCS-03 — order persistence and legacy handling

- **Objective:** persist the chosen carrier snapshot and recompute the price
  server-side.
- **Affected:** `db/schema/ordering.ts`, migration `0008`, `repository.ts`,
  memory repository, `PlaceOrderInput`, live tests.
- **Prerequisites:** MCS-02.
- **Artifacts:** nullable `carrier_id`/`carrier_name`, paired CHECK, inserts,
  list/detail reads, legacy NULL display value.
- **Verification:** migration applies; live order stores carrier + amount; a
  transition does not change them; legacy row renders without error.
- **Acceptance:** stored carrier equals the selected eligible carrier; amount
  equals the quote; old rows remain valid.
- **Evidence:** migration name, live test results.

### MCS-04 — checkout selection and server authority

- **Objective:** render eligible carriers dynamically and prevent an ineligible
  or stale selection from being submitted.
- **Affected:** checkout server page, `checkout-form.tsx`, checkout service,
  repository validation, unit tests.
- **Prerequisites:** MCS-02/03.
- **Artifacts:** server config prop, eligibility UI, no-eligible notice,
  disabled submit, dynamic preselection, refusal mapping.
- **Verification:** unit tests for service refusal; E2E for three options and
  order placement; no-eligible unit test.
- **Acceptance:** only eligible options appear; first is preselected; server
  rejects disabled/ineligible/unknown ids; display price equals stored price.
- **Evidence:** unit/live/E2E output.

### MCS-05 — adapter seam and sandboxes

- **Objective:** define one adapter contract and three local sandbox adapters
  with deterministic identity, timeout, retry and failure taxonomy.
- **Affected:** `server/shipping/*`, tests.
- **Prerequisites:** MCS-02.
- **Artifacts:** request/response types, `parcelHash`, `shipmentKey`,
  `SandboxCarrier`, per-carrier factories, retry wrapper.
- **Verification:** parcel invariant tests, hash determinism/address exclusion,
  one test per carrier, timeout/retry/refusal/no-fallback tests.
- **Acceptance:** no network/credential; no fallback; retry only transient.
- **Evidence:** test count; no live endpoint.

### MCS-06 — admin and packing-slip visibility

- **Objective:** show the stored carrier to the merchant.
- **Affected:** `OrderListItem`, admin table, packing slip.
- **Prerequisites:** MCS-03.
- **Artifacts:** carrier column and legacy label; slip line.
- **Verification:** component/read-model tests or live list assertion; E2E
  asserts the synthetic order shows the carrier.
- **Acceptance:** stored snapshot is shown, not a re-derived label.
- **Evidence:** E2E/admin output.

### MCS-07 — E2E and configuration modes

- **Objective:** extend the existing storefront check, not create another
  harness.
- **Affected:** `commerce/scripts/check-storefront-e2e.mjs`, tests.
- **Prerequisites:** MCS-04/06.
- **Artifacts:** fill Tehran address, assert three eligible radios in priority
  order, first checked, select local courier, place order, assert admin carrier.
- **Verification:** `npm run check:e2e`; `config.test.ts` covers all/subset/one.
- **Acceptance:** default E2E green; each config mode has an automated test.
- **Evidence:** E2E 59/59; 7 environment-config tests.

### MCS-08 — close-out

- **Objective:** run the full local gate, reconcile docs/evidence and commit.
- **Affected:** whole track.
- **Prerequisites:** MCS-03…07.
- **Artifacts:** status/evidence updates; focused commit.
- **Verification:** typecheck, lint, all tests, `db:check`, live suite, build,
  E2E, fail-closed, `git diff --check`, secret/scope review.
- **Acceptance:** no failed applicable check; skipped checks named; docs match
  measured behavior.
- **Evidence:** exact command results and commit hash.

---

## 10. Dependency map

```
MCS-01
  └── MCS-02
        ├── MCS-03 ── MCS-06
        │     └── MCS-04 ── MCS-07
        └── MCS-05
MCS-03 + MCS-04 + MCS-05 + MCS-06 + MCS-07
  └── MCS-08
```

MCS-05 is independent of persistence/checkout after MCS-02. MCS-06 can proceed
with MCS-03. MCS-07 needs checkout + admin.

---

## 11. Test strategy

| Layer | Command | Coverage |
| --- | --- | --- |
| Registry/quote unit | `npm test` | validation, modes, coverage, weight/dimensions, price models, priority, no eligible, unknown/disabled |
| Checkout service unit | `npm test` | server refuses ineligible/disabled; quote passed to write |
| Adapter unit | `npm test` | three sandboxes, hashes, parcel invariants, timeout, retry, no fallback |
| Live PostgreSQL | `npm run smoke:db` | carrier columns, stored amount, immutability across transition, legacy NULL |
| Build | `npm run build` | instrumentation/registry bundle, 23+ routes |
| E2E | `npm run check:e2e` | three options, priority/pre-selection, order carrier, admin carrier |
| Fail-closed | `npm run check:e2e:fail-closed` | no-DB checkout still no form; shipping config independent |
| Static | `npm run verify` | typecheck/lint/tests/db:check |

Configuration-mode automated tests:

1. all: no `COMMERCE_SHIPPING_ENABLED`; three eligible in priority order;
2. subset: `POST_PISHTAZ,EXPRESS_COURIER`; Tipax absent, local courier eligible
   for Tehran;
3. exactly one: `EXPRESS_COURIER`; only local courier, preselected once eligible;
4. no eligible: all disabled or destination outside coverage → explicit refusal.

No real carrier endpoint is ever contacted. Timeout tests use an injected local
delay, not a network socket.

---

## 12. Data, security and owner gates

- Only synthetic local checkout data; no real customer data.
- No carrier credential, API key, token, phone, address or customer PII is added
  to source, docs, logs, fixtures or prompts.
- `parcelHash`/`shipmentKey` exclude the address; tests assert this.
- Sandbox adapters perform no network I/O and do not persist shipments.
- Real carrier credentials, contracts, API calls, label purchase, tracking
  polling, production media/payment/SMS/AI and deployment remain **owner-gated**
  by D-045, D-139 and the relevant provider decisions. D-175 selects the local
  three-carrier registry only; it does not activate any carrier.
- A production carrier adapter must be separately reviewed; it may not bypass
  the adapter interface, timeout/retry taxonomy or no-fallback rule.

---

## 13. Definition of done, reporting and pause conditions

**Done when:** MCS-01…MCS-08 are DONE or BLOCKED with a named reason; all three
configuration modes and negative paths are automated; the default E2E and
fail-closed checks pass; docs match measured behavior; diff is clean and
secret-free; fast-forward commit/push succeeds if policy permits.

**Report:** baseline, doc/task list, outcomes, files, exact commands/counts,
configuration-mode tests, blocked items, owner gates, commit/push, next task.

**Pause and ask the owner if:**

- implementing eligibility requires real province/city data or per-SKU weights
  beyond the documented estimator;
- a check would require a real carrier endpoint, credential or production
  deployment;
- schema change threatens existing orders/data without a safe additive path;
- the canonical Phase 12 boundary must be modified or wired;
- documentation contains conflicting owner rulings that cannot be reconciled
  additively.

---

## 14. Evidence log

Append-only; filled as tasks complete.

- **2026-11-12 — MCS-01:** baseline verified at
  `0929f473e70bde6e8c92f3142c3aee6572aeebce`; working tree clean except
  `.cloud-attachments/`. Existing hardcoded methods, missing carrier
  persistence, missing eligibility and separate canonical Phase 12 sandbox
  classified. No code changed.
- **2026-11-12 — MCS-02:** `shipping.test.ts` 11/11 (all/subset/single/none,
  priority, coverage, parcel limits, PER_KG, invalid config);
  `server/shipping/config.test.ts` 7/7 over an explicit env map, covering
  unset/subset/single/none, priority, unknown id, malformed JSON and a full
  validated override. Invalid startup config exits the server (exit 1).
- **2026-11-12 — MCS-03:** migration `0008_giant_glorian.sql` applied by
  `db:reset`; live PostgreSQL suite 88/88 (26 suites). A placed order stores
  `carrier_id`/`carrier_name` with its quote; the pair survives a lifecycle
  transition; a legacy NULL row remains readable.
- **2026-11-12 — MCS-04:** checkout service tests refuse ineligible, disabled
  and unknown carriers without writing; the page passes the resolved snapshot;
  the form preselects the first eligible option and disables submit when none
  exist. Displayed price is replaced by the server result on success.
- **2026-11-12 — MCS-05:** `carrier-adapter.test.ts` 7/7 — deterministic
  address-free parcel hash, invalid parcel refusal, one sandbox per carrier,
  mismatched-carrier refusal, timeout, transient retry and no fallback after a
  refusal. No network I/O.
- **2026-11-12 — MCS-06:** admin order table adds «حامل» from the stored
  snapshot; packing slip prints the same line; legacy orders show
  «ثبت‌نشده (سفارش قدیمی)». E2E asserts the carrier in `/admin/orders`.
- **2026-11-12 — MCS-07:** `check:e2e` 59/59 on a fresh migrated+seeded
  harness: three eligible radios in priority order, first preselected, choice
  changeable, order placed, admin shows the carrier. All three configuration
  modes plus `none` are covered by the environment tests.
- **2026-11-12 — MCS-08:** `npm run verify` green (offline 572/572, 132
  suites); `db:check` clean; `npm run build` green (22 routes; the pre-existing
  `src/server/media/serve.ts:88` Turbopack tracing warning remains); live DB
  88/88; `check:e2e` 59/59; `check:e2e:fail-closed` 13/13; HTTP status 3/3
  against the DB-backed server; invalid `COMMERCE_SHIPPING_ENABLED` exits 1
  before serving. All local; no carrier endpoint, credential or deployment.

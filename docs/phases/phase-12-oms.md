# Phase 12 — Order Management System (OMS)

- Date: 2026-09-16
- Authority: MASTER_PLAN §13 Phase 12 + **D-081..D-084 (all Approved)**
- Scope discipline: local-first (D-053); no payment gateway logic, no
  payment credentials, no live store connection (D-045); the Woo
  order projection is NOT this phase — WooCommerce remains the
  transactional/projection layer, never canonical.

## 1. Objective

Give the platform a canonical, event-sourced order lifecycle: orders
flow `PLACED → VALIDATED → FULFILLING → COMPLETED` with terminal
`CANCELLED` / `REFUNDED`, stock cannot be oversold under concurrency,
payment is a boundary (pending markers only), and fulfillment
notifications ride the existing Phase 11 fan-out machinery.

## 2. Decision table

| Decision | Content | Module |
|---|---|---|
| D-081 | Order schema (line items bound to Product ID / Variant ID / SKU per D-017), lifecycle state machine, `client_order_id` SHA-256 idempotency | `oms_contracts.py` |
| D-082 | Provider-neutral `InventoryStore`, atomic PG row-lock reservation on VALIDATED entry, JSON parity store, deterministic `insufficient_stock` | `oms_contracts.py` / `oms_engine.py` |
| D-083 | Payment-neutral boundary (`pending`/`unpaid` markers only), fulfillment notifications via Phase 11 `FanOutEngine` — notification failure never blocks the order | `oms_engine.py` |
| D-084 | Immutable D-027 transition audit + D-026 provenance; TTL reconciliation auto-cancels orphaned `FULFILLING` orders (`fulfillment_ttl_expired`) and releases stock | `oms_worker.py` |

## 3. Architecture flow

```
place_order (validated contract)
  → D-027 receive/begin/succeed  [oms|order|<client_key>]   (D-081)
  → transition PLACED → VALIDATED
      → InventoryStore.reserve(sku, qty)   atomic row lock (D-082)
  → transition VALIDATED → FULFILLING
      → fulfillment task dispatched (mock/local; receipt required)
  → transition FULFILLING → COMPLETED  (receipt recorded)
      ↘ notifications: FanOutEngine.dispatch(...) (D-083, isolated)
CANCELLED / REFUNDED → release_reservations (D-082) + audit (D-084)
worker: scan FULFILLING past TTL without receipt → CANCELLED (D-084)
```

## 4. State machine (D-081)

| From | To | Guard |
|---|---|---|
| PLACED | VALIDATED | inventory reservation succeeds |
| VALIDATED | FULFILLING | fulfillment accepted |
| FULFILLING | COMPLETED | fulfillment receipt present |
| PLACED/VALIDATED/FULFILLING | CANCELLED | not already terminal |
| COMPLETED | REFUNDED | terminal, audit-only path |
| COMPLETED/CANCELLED/REFUNDED | * | immutable (no outgoing) |

## 5. Milestones

| Milestone | Content | Status |
|---|---|---|
| M1 | Order/LineItem contracts, SKU binding, transitions, idempotency key | done |
| M2 | OMS engine: transitions, reservation, row locks, `oms.inventory` schema | done |
| M3 | Worker: TTL reconciliation, stock release, Phase 11 notification bridge | done |
| M4 | Live-PG E2E suite, AST audit, full regression | done |

## 6. Security boundaries

- No network imports; the only vendor-facing surfaces remain the
  Phase 9/10/11 adapters and the FanOutEngine boundary.
- No payment module, no payment env reads; `os.environ` access = 0
  in Phase 12 modules.
- All IDs owner-assigned or caller-supplied; the OMS never invents
  Product ID / Variant ID / SKU (D-014/D-017).
- Every persisted payload passes platform redaction where a
  notification fan-out is involved (Phase 11 guarantee).

## 7. Verification record (2026-09-16)

- M1–M4 complete; suite `local/tests/test_phase12_oms.py`:
  **37/37 OK** (offline + live-PG E2E with the REAL `PgInventory`
  guarded UPDATE).
- Full battery: **498/498 OK, zero skips**; ladder 46/46 OK;
  containers 5/5 healthy.
- AST audit on the three Phase 12 modules + test suite: **CLEAN** —
  no network imports, no platform/price/publication references, no
  payment-gateway code paths, `os.environ` access = 0.
- Secret scan CLEAN; `git diff --check` PASS.

Defects found and fixed during M4 (all caught by the suite):

1. **Money floats silently truncated** — `int(10.5)` accepted a
   float price as 10 minor units. Money/quantities now use a strict
   integer coercion (`_strict_int`): floats and bools are Class-B,
   digit strings accepted for transport.
2. **Dead notification bridge** — `_notify` built payloads with
   `targets=[]` and short-circuited before the fan-out boundary,
   making D-083 integration unreachable. Destinations are now
   caller-configured (`notification_targets`); the OMS never invents
   them; with none configured the bridge is an explicit no-op.
3. **Partial-reservation rollback hole** — multi-line orders that
   failed on a later line released only DURABLE ledger entries; lines
   reserved earlier in the same call were missed. Rollback now tracks
   in-call reservations (ledger entries plus this call's lines).
4. **PG integer parameter cast** — seeded/reserved quantities arrived
   as text; the guarded UPDATE now casts `::int` explicitly at the
   boundary.
5. **Provenance surface mismatch** — engine called a nonexistent
   keyword surface; corrected to the real D-026 `record(source_type,
   actor, source_reference, notes)` signature.

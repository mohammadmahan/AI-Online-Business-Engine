# Phase 10 Live Wiring Report — Multi-channel Order Orchestration (D-160)

**Attestation:** `phase10.live_wiring_attestation.v1`
**Verdict:** `PHASE10_IGNITED` (sandbox / dry-run, zero payment boundaries crossed)
**Upstream:** `phase9.live_wiring_attestation.v1` (D-159) — digest `820440dd…`,
rooted in the D-112 ledger row kind `phase9_live_wiring_attestation`, chain intact.
**Engine:** `local/scripts/live_wiring_phase10_igniter.py` (ORD-01..ORD-05)
**Battery:** `local/tests/test_live_wiring_phase10.py` — 48 tests, ×2 green
**Governance:** D-045 / D-077 / D-078 / D-080 / D-081–D-084 / D-114 / D-124 / D-139 /
D-154 / D-159 / §17 / §21.8. Chain: D-154 → D-155 → D-156 → D-157 → D-158 → D-159 → **D-160**.

---

## 1. Upstream attestation verification (ORD-01)

The Phase 9 attestation is verified **before any order-processing or
state-allocation call**: schema, `PHASE9_IGNITED` verdict, manifest binding, and
the D-159 attestation's canonical bytes recomputed and matched against the
SHA-256 commitment rooted in the D-112 ledger (`phase9_live_wiring_attestation`),
with the full chain integrity check delegated to the injected verifier. Every
refusal class (absent / raised / wrong schema / incomplete verdict / drifted
digest / unrooted / broken chain) provably leaves the OMS stack untouched — the
battery asserts the engine factory is never invoked on refusal.

## 2. Runtime profile & seams (ORD-02)

The injected census must mark `runtime_profile_verified` and Phases **5, 6, 7, 8
and 9** present + VERIFIED + WIRED. Four repo-real order seams are asserted
importable and pinned to the D-154 `ENTRY_POINTS` registry:

| Seam | Module | Registry pin |
|---|---|---|
| OMS engine | `canonical.oms_engine` | `ENTRY_POINTS[11]` |
| Order contracts | `canonical.oms_contracts` | `ENTRY_POINTS[12]` |
| OMS worker | `canonical.oms_worker` | supporting (exempt) |
| D-027 event store | `services.sync_engine` | supporting (exempt) |

Any mismatch refuses as **registry drift** before ORD-03 runs.

## 3. Multi-channel idempotency & locking matrix (ORD-03)

| Invariant | Mechanism | Evidence |
|---|---|---|
| Channel origin tagging | `telegram` / `instagram_dm` / `web_store` carried on the order | survives the REAL validator; probe order originates from the Phase 9 Telegram ingress format |
| Idempotency locking | D-081 `order_idempotency_key` = SHA-256 over `client_order_id` — no wall clock | key deterministic (64 hex); identical replay → `skipped_duplicate`; conflicting payload under the same token → `IntegrityError` (human review, D-027/D-081) |
| Currency | whitelist `IRR` / `IRT` | anything else refused |
| Price integrity | strict-integer minor units, ≥ 0, D-114 ceiling `10¹²`, total = Σ(quantity × unit_price) + tax | floats, negatives and ceiling breaches refused through the REAL `validate_order` |
| Discount bounds | allowlist gate (`SPRING10`) + `MAX_DISCOUNT_PCT = 20` | an unapproved code is refused outright; the D-081 money path contains **no discount arithmetic** — the total is line-item sums + tax, so no code can silently alter money |
| Error classes | Class-B contract refusals never retried; Class-A transients bounded at ≤ 2 with a 15 s per-operation timeout | out-of-order state edges (`PLACED→COMPLETED`) refused by the state machine |

## 4. Synthetic order lifecycle trace (ORD-04)

Multi-item order (`ord-phase10-01`, 2 lines, IRT, total **450,000 minor**)
through the **real offline OMS stack** (`OmsEngine` over `EventStore` /
`JsonInventory` / `_ReservationLedger`, all scratch-backed):

| Step | Result | Telemetry |
|---|---|---|
| START | ok | channel `telegram`, 2 items |
| LOCK | ok | place → `PLACED`; identical replay → `skipped_duplicate` (exclusive, not value-blind) |
| VALIDATE | ok | total 450000 minor, currency IRT |
| RESERVE | ok | PLACED→VALIDATED fires the real D-082 reservation; insufficient stock refuses atomically (no partial reservation) |
| TRANSITION | ok | PLACED→VALIDATED→CANCELLED; CANCELLED releases every reservation (D-082/D-084 release guard), zero locks held |
| EVENT_PROBE | ok | **real D-083 fan-out boundary driven** (below) |
| VERIFY | ok | payment-boundary audit over the live D-027 records — clean |
| CLEANUP | ok | data-minimized artifact round-trip, deletion, zero residue |

**The D-083 notification fan-out boundary is exercised for real, not mocked:**
a schema-compliant notification event is routed through the boundary's
`route()` (validates + adapts the target through the D-077 destination matrix)
and `dispatch()` (writes the durable per-target receipt) of the **real
`canonical.orchestration_engine.FanOutEngine`**. The publish binds are
**publisher-less** (`{"telegram": None}`) so every outcome is
`no_publisher_bound` — the boundary runs while being *structurally incapable*
of channel egress. The synthetic target params are `chat_id: 1` with the fixed
marker text `[phase10-probe] order status update`; no customer identity exists
anywhere in the payload. 7 durable receipts verified in the shared scratch
event store.

**Cycle timing:** full ignition ≈ 55 ms including the authentic five-phase
upstream chain build; the ORD-04 cycle alone is ≈ **36.25 ms** in-process.
Deterministic summary hash `53e0ba4c…`; attestation digest is byte-stable
across runs.

## 5. Rate/volume guardrails

`LIMITS`: Class-A retries ≤ 2 · per-operation timeout 15 s (D-151) ·
`max_line_items` 100 (D-114) · soft-reservation probes ≤ 10 per cycle.
The OMS never invents destinations: notification targets are injected, and the
probe configures none — the only fan-out traffic is the publisher-less probe.

## 6. Security posture

- **Payment is a boundary (D-083):** the VERIFY audit scans the *live* D-027
  event records of the store the engine drives for gateway markers
  (`gateway`, `payment_url`, `checkout`, `charge`); any hit fails the run.
  `payment_status` is a closed marker set (`pending`), and no payment field
  exists anywhere in the probe surface.
- **D-124 redaction:** customer_ref, phones, addresses, payment tokens are
  never emitted; the battery scrubs every output (attestation, audit sink,
  check strings) for canaries and PII; only hashes, counts, state names,
  verdicts and step telemetry escape.
- **D-079 lock hygiene (incident + fix):** the default fan-out lock claims keys
  *permanently* in live PostgreSQL (`orchestration.fanout_lock`) or the shared
  `local/volumes/orchestration/fanout_lock.json`. Recon probes during engine
  development claimed 2 PG rows; these were **purged (DELETE 2, keys matched
  exactly, 4 pre-existing rows untouched)** before commit, and the engine was
  re-architected to inject an **ephemeral process-local D-079 parity lock**
  (`_EphemeralFanOutLock`) — identical INSERT-once semantics, zero durable
  footprint. The battery asserts the probe never holds `_PgFanOutLock` /
  `_JsonFanOutLock` and that no probe key leaks into the shared lock file.
- **Purity (AST-pinned):** no network/db/shell imports or calls in the engine;
  injected engine/store/fanout/scratch transports only.

## 7. Verification & battery

- New battery **48/48 ×2** (pass, ORD-01..04 refusal classes, boundary-drive
  proof, lock-hygiene proof, emission contract, redaction scrubs, AST audits).
- Full regression **1870/1870 ×2 consecutive green across 76 modules**
  (1822 + 48), zero bad, zero skipped, per-chunk counts identical across runs
  and machine-reconciled to the module census.
- **Invocation contract:** the battery must run from the repository **root**
  (`python3 -m unittest local.tests.…`): the `publishing.instagram` seam and
  several batteries import `local.src.…` absolute paths, which resolve only
  with the repo root on `sys.path`. Running from `local/` fails unrelated
  modules — this is an environment contract, not a code regression.
- **Reliability fix (suite-found):** `canonical/portability_bindings.py` and
  `telegram_publisher.py` insert `local/canonical` onto `sys.path` **at import
  time**, which makes the chain builders' bare `import tests.…` resolve to the
  legacy `canonical/tests.py` module when heavy canonical modules load first
  (exactly what this battery does). All chain builders
  (`test_live_wiring_phase6/7/8/9/10.py`) now evict the poisoned path entries
  and purge any shadowed legacy `tests` module before their sibling import.

## 8. Handover to Phase 11 — Payment Gateway & Settlement Wiring

Verified and inherited by Phase 11:

- The D-083 notification boundary is *proven* with durable receipts — Phase 11
  publisher binds plug into exactly that surface (`publish_binds`).
- The OMS transition machine already gates `COMPLETED` on a
  `fulfillment_receipt` (D-084) and `REFUNDED`/`CANCELLED` release all
  reservations — the settlement loop can be added without new state-machine
  seams.
- Payment remains markers-only (`pending`); **no gateway field exists anywhere
  in the Phase 10 surface**.

Phase 11 entry criteria: gateway adapter behind an injected transport (D-045
owner gate), zero live charge capability in probe mode, settlement idempotency
keyed on the D-081 `client_order_id` lock, and settlement receipts recorded
into the D-084 fulfillment surface.

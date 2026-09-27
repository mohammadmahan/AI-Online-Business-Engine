# Phase 12 Live Wiring Report — Shipping & Orchestration Engine (D-162)

**Attestation:** `phase12.shipping_wiring_attestation.v1`
**Verdict:** `PHASE12_IGNITED` (sandbox / dry-run, zero carrier bookings)
**Upstream:** `phase11.payment_wiring_attestation.v1` (D-161) — digest `9fcbc70f…`,
rooted in the D-112 ledger row kind `phase11_payment_wiring_attestation`, chain intact.
**Engine:** `local/scripts/live_wiring_phase12_igniter.py` (SHP-01..SHP-05)
**Battery:** `local/tests/test_live_wiring_phase12.py` — 43 tests, ×2 green
**Governance:** D-045 / D-053 / D-081–D-084 / D-114 / D-124 / D-139 / D-154 /
D-161 / §17 / §21.8. Chain: D-154 → … → D-160 → D-161 → **D-162**.

---

## 1. Upstream attestation verification (SHP-01)

The Phase 11 attestation is verified **before any carrier call is even
constructible**: schema (`phase11.payment_wiring_attestation.v1`), the
`PHASE11_IGNITED` verdict, the manifest binding, and the D-161 attestation's
canonical bytes recomputed and matched against the SHA-256 commitment rooted in
the D-112 ledger (`phase11_payment_wiring_attestation`), with full chain
integrity delegated to the injected verifier. Every refusal class (absent /
raised / wrong schema / incomplete verdict / drifted digest / unrooted / broken
chain) provably leaves the carrier unused — the battery asserts the sandbox
carrier's `create_shipment` is never invoked on refusal, and no OMS stack is
allocated.

## 2. Runtime profile & seams (SHP-02)

The injected census must mark `runtime_profile_verified` and Phases **5–11**
present + VERIFIED + WIRED. The repo-real seams are asserted importable and
pinned to the D-154 `ENTRY_POINTS` registry:

| Seam | Module | Registry pin |
|---|---|---|
| Orchestration / shipping spine | `canonical.orchestration_engine` | `ENTRY_POINTS[13]` ("Shipping") |
| OMS engine | `canonical.oms_engine` | `ENTRY_POINTS[11]` |
| Order contracts | `canonical.oms_contracts` | `ENTRY_POINTS[12]` |
| D-027 event store | `services.sync_engine` | supporting (exempt) |

The **load-bearing pin** is asserted twice: the per-seam registry-consistency
loop *and* an explicit defense-in-depth check that registry slot 13 binds
exactly `canonical.orchestration_engine` (the D-154 cross-walk). Any mismatch
refuses as **registry drift** / **cross-walk drift** before SHP-03 runs.

## 3. Carrier capability & parcel matrix (SHP-03)

| Invariant | Mechanism | Evidence |
|---|---|---|
| Capability cap | `CARRIER_CAPS = ("sandbox", "dry_run", "tracking_query")` | a carrier advertising or being asked for `live_ship` (or any unknown capability) is refused outright — the booking path is structurally unreachable in probe mode; the real shipping provider remains UNSELECTED (open decision 11, D-045/D-139) |
| Shipment idempotency | deterministic `shipment_key(client_order_id, carrier_id, parcel_hash)` = SHA-256, no wall clock, replay-resistant | identical key for identical inputs across runs; the D-027 store adjudicates: identical replay → `skipped_duplicate`, forged payload under the same key → `IntegrityError` |
| Parcel identity | `parcel_hash` over (weight, dimensions, declared value) only | **addresses are never part of parcel identity** — no address enters any hash or record |
| Parcel invariants | `_validate_parcel`: strict-integer weight ≥ 1 g under the 100 kg ceiling, per-dimension 1..150 cm strict integers, declared value strict integer ≥ 0 under the D-114 ceiling 10¹² | floats, negatives, zero, over-ceiling and missing/extra dimension axes refuse with exact reasons (battery enforces the classification across 10 invalid-parcel classes) |
| Fault containment | injected `SandboxCarrier` fault classes — `timeout`, `partition`, `refuse`, `live_ship` | each fails CLOSED with a typed Class-A/B error, no state mutation, no retry storm (Class-A retries ≤ 2, 15 s per-operation timeout) |

## 4. Dry-run shipping cycle trace (SHP-04)

Synthetic order `ord-phase12-01` (client `phase10-probe-clt-0001`, channel
`telegram`, IRT, 2 kg parcel, declared value **450,000 minor**) through the
real offline OMS stack and the real D-083 fan-out boundary:

| Step | Result | Telemetry |
|---|---|---|
| START | ok | cycle id `phase12-shipping-probe-0001`, parcel 2,000 g |
| AUTH | ok | capability profile enforced (§3); any live-ship attempt refused |
| CREATE | ok | sandbox label invoked **exactly once** (`create_calls == 1`); deterministic sandbox label `dry_run: true` with derived tracking number |
| SHIP | ok | D-027 shipment idempotency proven (replay → `skipped_duplicate`, forged payload → `IntegrityError`) |
| STATE | ok | OMS lifecycle PLACED → VALIDATED → FULFILLING → COMPLETED with the fulfillment receipt carrying the **shipment id** — receipt-once via transition refs (below) |
| TRACK | ok | tracking event through the REAL `FanOutEngine` (below) |
| VERIFY | ok | shipping-marker sweep over the live store records — clean |
| CLEANUP | ok | `phase12-scratch:shipping` artifact deleted, zero residue |

**Receipt-once via transition refs (the D-084 invariant):** the fulfillment
receipt lives **inside the COMPLETED transition ref**
(`oms|transition|<key>` carries `fulfillment_receipt`) — it is *not* a
separate `oms|receipt|` event. Phase 12 binds the receipt to the *shipment*:
the receipt payload carries the sandbox `shipment_id`, exactly **one** ref
carries the fulfillment receipt, and a second `COMPLETED` transition is
refused.

**Tracking event emission is real, not mocked:** the tracking event is routed
through the real `canonical.orchestration_engine.FanOutEngine` with
**publisher-less binds** (`{"telegram": None}` — structurally incapable of
channel egress) under an **ephemeral process-local D-079 lock**
(`_EphemeralFanOutLock` — INSERT-once parity semantics, zero durable
footprint). Outcomes are `no_publisher_bound`; durable per-target receipts are
verified in `store.succeeded_references("orchestration")`.

**Cycle timing:** the SHP-01..SHP-05 ignition cycle ≈ **54 ms** in-process
including the battery's authentic upstream chain build — real
D-161 → D-160 → … → D-154. Attestation digest `ff9beb306fd472d1…`, byte-stable
across runs.

## 5. Rate/volume guardrails

`LIMITS`: Class-A retries ≤ 2 · per-operation timeout 15 s (D-151) ·
`max_tracking_events` 5 per cycle. The engine never invents destinations:
fan-out targets are injected, and the probe configures none — the only fan-out
traffic is the publisher-less tracking probe.

## 6. Security posture

- **Shipping is a boundary (D-083):** the VERIFY audit scans the *live*
  `store.records` for shipping markers (`live_ship`, `label_secret`,
  `auth_code`, `pan`, `card_number`, `carrier_secret`) — any hit fails the run
  — and requires `create_calls == 1` (exactly one sandbox label, no replay
  re-booking). The sandbox carrier books nothing, holds no credentials, and
  can never advertise `live_ship` through the capability gate.
- **D-124 redaction:** customer refs, addresses, carrier tokens and label
  secrets are never emitted; the battery scrubs every output (attestation,
  audit sink, check strings) for canaries and PII; only hashes, counts, state
  names, verdicts and step telemetry escape.
- **D-079 lock hygiene:** the tracking probe holds only the ephemeral
  process-local lock; the battery inherits the D-160/D-161 discipline — the
  probe never claims `_PgFanOutLock` / `_JsonFanOutLock` and no probe key
  leaks into the shared lock file (zero durable lock claims).
- **Purity (AST-pinned):** no network/db/shell imports or calls in the engine;
  injected carrier/engine/store/fanout/scratch transports only.

## 7. Verification & battery

- New battery **43/43 ×2** (SHP-01..04 refusal classes, capability cap,
  slot-13 cross-walk drift, shipment idempotency trio, receipt-once via
  transition refs, boundary fan-out drive, parcel invariants, money-marker
  sweep, emission contract, redaction scrubs, AST audits).
- Full regression **1955/1955 ×2 consecutive green across 78 modules**
  (1912 + 43), zero bad, zero skipped, per-chunk counts identical across runs
  and reconciled to the untouched-module invariant (the 77 pre-existing
  modules still carry exactly 1912 tests).
- **Invocation contract:** the battery must run from the repository **root**
  (`python3 -m unittest local.tests.…`): the `publishing.instagram` seam and
  several batteries import `local.src.…` absolute paths, which resolve only
  with the repo root on `sys.path` (environment contract, not a regression).
- **Heavy-chunk note:** the live-PG cluster (test_phase10_telegram /
  test_phase11_orchestration(+e2e) / test_phase12_oms, ≈ 512 s) and
  test_phase26_dr_closeout (≈ 430 s) dominate wall-clock; run in small groups
  to stay inside command timeouts.

## 8. Handover to Phase 13 — Commerce & workspace sync

Verified and inherited by Phase 13:

- The orchestration spine is *verified, not opened*: `CARRIER_CAPS` contains
  no booking capability, and the shipping loop closes entirely inside the
  sandbox store.
- The D-083 fan-out boundary now carries three proven probe classes
  (order/settlement/tracking events) with publisher-less binds — real
  publishers plug into exactly that surface.
- The registry path forward is explicit: slot 14 (CRM, `commerce.
  sync_orchestrator`, CRM-not-needed rule), 15 (Marketing Automation,
  `canonical.scheduling_engine`), 16–18 (Analytics, Analyst, HITL).

Phase 13 entry criteria: remaining service wiring under the same fail-closed
attestation recursion (per `dokploy-plan.md` and the D-154 transition). Real
shipping purchase additionally requires the owner's shipping provider
selection (open decision 11) and remains behind the D-045 owner gate and
D-139 activation authority.

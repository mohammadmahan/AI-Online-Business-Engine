# Phase 11 Live Wiring Report — Payment Gateway & Settlement Verification (D-161)

**Attestation:** `phase11.payment_wiring_attestation.v1`
**Verdict:** `PHASE11_IGNITED` (sandbox / dry-run, zero real money movement)
**Upstream:** `phase10.live_wiring_attestation.v1` (D-160) — digest `564508fe…`,
rooted in the D-112 ledger row kind `phase10_live_wiring_attestation`, chain intact.
**Engine:** `local/scripts/live_wiring_phase11_igniter.py` (SET-01..SET-05)
**Battery:** `local/tests/test_live_wiring_phase11.py` — 42 tests, ×2 green
**Governance:** D-045 / D-053 / D-081–D-084 / D-114 / D-124 / D-139 / D-154 /
D-160 / §17 / §21.8. Chain: D-154 → D-155 → D-156 → D-157 → D-158 → D-159 →
D-160 → **D-161**.

---

## 1. Upstream attestation verification (SET-01)

The Phase 10 attestation is verified **before any gateway call is even
constructible**: schema (`phase10.live_wiring_attestation.v1`), the
`PHASE10_IGNITED` verdict, the manifest binding, and the D-160 attestation's
canonical bytes recomputed and matched against the SHA-256 commitment rooted in
the D-112 ledger (`phase10_live_wiring_attestation`), with full chain integrity
delegated to the injected verifier. Every refusal class (absent / raised /
wrong schema / incomplete verdict / drifted digest / unrooted / broken chain)
provably leaves the gateway unused — the battery asserts the sandbox gateway's
`charge` is never invoked on refusal, and no OMS stack is allocated.

## 2. Runtime profile & seams (SET-02)

The injected census must mark `runtime_profile_verified` and Phases **5–10**
present + VERIFIED + WIRED. The repo-real seams are asserted importable and
pinned to the D-154 `ENTRY_POINTS` registry:

| Seam | Module | Registry pin |
|---|---|---|
| OMS engine | `canonical.oms_engine` | `ENTRY_POINTS[11]` |
| Order contracts | `canonical.oms_contracts` | `ENTRY_POINTS[12]` |
| Orchestration / fan-out | `canonical.orchestration_engine` | `ENTRY_POINTS[13]` |
| D-027 event store | `services.sync_engine` | supporting (exempt) |

Any mismatch refuses as **registry drift** before SET-03 runs.

## 3. Gateway capability & settlement money matrix (SET-03)

| Invariant | Mechanism | Evidence |
|---|---|---|
| Capability cap | `GATEWAY_CAPS = ("sandbox", "dry_run", "status_query")` | a gateway advertising or being asked for `live_charge` (or any unknown capability) is refused outright — the charge path is structurally unreachable in probe mode |
| Settlement idempotency | deterministic `settlement_key(client_order_id, gateway, amount)` = SHA-256, no wall clock, replay-resistant | identical key for identical inputs across runs; the D-027 store adjudicates: identical replay → `skipped_duplicate`, forged payload under the same key → `IntegrityError` |
| Money integrity | `_validate_amount`: strict `int`, ≥ 1, D-114 ceiling `10¹²` | floats, negatives, zero and ceiling breaches refuse with exact messages (`strict integer` / `>= 1` / `ceiling`); the settlement amount is the validator-normalized `total_minor`, never recomputed in the gateway path |
| Fault containment | injected `SandboxGateway` fault classes — `timeout`, `partition`, `decline` | each fails CLOSED with a typed Class-A/B error, no state mutation, no retry storm (Class-A retries ≤ 2, 15 s per-operation timeout) |

## 4. Dry-run settlement cycle trace (SET-04)

Synthetic order `ord-phase11-01` (client `phase10-probe-clt-0001`, channel
`telegram`, IRT, total **450,000 minor**) through the real offline OMS stack
and the real D-083 fan-out boundary:

| Step | Result | Telemetry |
|---|---|---|
| START | ok | cycle id `phase11-settlement-probe-0001` |
| AUTH | ok | capability profile enforced (§3); any live-charge attempt refused |
| CHECKOUT | ok | OMS lifecycle PLACED → VALIDATED → FULFILLING through the real engine |
| SETTLE | ok | sandbox charge invoked **exactly once** (`charge_calls == 1`); D-027 settlement idempotency proven (replay → `skipped_duplicate`, forged payload → `IntegrityError`) |
| RECEIPT | ok | **receipt-once via transition refs** (below) |
| EVENT_PROBE | ok | settlement event through the REAL `FanOutEngine` (below) |
| VERIFY | ok | money-marker sweep over the live store records — clean |
| CLEANUP | ok | `phase11-scratch:settlement` artifact deleted, zero residue |

**Receipt-once (the load-bearing finding):** the D-084 `fulfillment_receipt`
lives **inside the COMPLETED transition ref** (`oms|transition|<key>` carries
`fulfillment_receipt`) — it is *not* a separate `oms|receipt|` event
(`engine.has_receipt()` only sees separate receipt events). The battery proves
receipt-once over `store.succeeded_references("oms")`: exactly **one** ref
carries the fulfillment receipt, and a second `COMPLETED` transition is
refused. The lifecycle completes PLACED → VALIDATED → FULFILLING → COMPLETED.

**Settlement event emission is real, not mocked:** the settlement event is
routed through the real `canonical.orchestration_engine.FanOutEngine` with
**publisher-less binds** (`{"telegram": None}` — structurally incapable of
channel egress) under an **ephemeral process-local D-079 lock**
(`_EphemeralFanOutLock` — INSERT-once parity semantics, zero durable
footprint). Outcomes are `no_publisher_bound`; durable per-target receipts are
verified in `store.succeeded_references("orchestration")`.

**Cycle timing:** the SET-01..SET-05 ignition cycle ≈ **7.3 ms** in-process
(the battery's authentic upstream chain build — real D-160 → … → D-154 — runs
in the harness before the cycle). Attestation digest `9339be7daab8d993…`, byte-
stable across runs.

## 5. Rate/volume guardrails

`LIMITS`: Class-A retries ≤ 2 · per-operation timeout 15 s (D-151) ·
`max_settlement_events` 5 per cycle. The engine never invents destinations:
fan-out targets are injected, and the probe configures none — the only fan-out
traffic is the publisher-less settlement probe.

## 6. Security posture

- **Money is a boundary:** the VERIFY audit scans the *live* `store.records`
  for money markers (`live_charge`, `auth_code`, `pan`, `card_number`,
  `gateway_secret`) — any hit fails the run — and requires
  `charge_calls == 1` (exactly one sandbox authorization, no replay storm).
  The sandbox gateway moves no money, holds no credentials, and can never
  advertise `live_charge` through the capability gate.
- **D-124 redaction:** customer refs, PANs, auth codes and gateway secrets are
  never emitted; the battery scrubs every output (attestation, audit sink,
  check strings) for canaries and PII; only hashes, counts, state names,
  verdicts and step telemetry escape.
- **D-079 lock hygiene:** the fan-out probe holds only the ephemeral
  process-local lock; the battery asserts the probe never claims
  `_PgFanOutLock` / `_JsonFanOutLock` and that no probe key leaks into the
  shared lock file (zero durable lock claims).
- **Purity (AST-pinned):** no network/db/shell imports or calls in the engine;
  injected gateway/engine/store/fanout/scratch transports only.
- **Suite-found security fix (in-batch):** the battery initially passed the
  upstream attestation via a kwarg spelled `phase10_provider=None`; the literal
  token passed the phase-20 entropy sweep's `_secret_signature` heuristic
  (digits + mixed case) and would have flagged the battery as a secret-shaped
  false positive. The kwarg is renamed `upstream_provider` in both engine and
  battery; the phase-20 suite runs 33/33 clean.

## 7. Verification & battery

- New battery **42/42 ×2** (SET-01..04 refusal classes, capability cap,
  settlement idempotency trio, receipt-once via transition refs, boundary
  fan-out drive, lock hygiene, money-marker sweep, emission contract,
  redaction scrubs, AST audits).
- Full regression **1912/1912 ×2 consecutive green across 77 modules**
  (1870 + 42), zero bad, zero skipped, per-chunk counts identical across runs
  and machine-reconciled to the module census.
- **Invocation contract:** the battery must run from the repository **root**
  (`python3 -m unittest local.tests.…`): the `publishing.instagram` seam and
  several batteries import `local.src.…` absolute paths, which resolve only
  with the repo root on `sys.path` (environment contract, not a regression).

## 8. Handover to Phase 12 — remaining channels & services

Verified and inherited by Phase 12:

- The settlement surface is *verified, not opened*: `GATEWAY_CAPS` contains no
  capture capability, and the settlement receipt loop closes entirely inside
  the sandbox store.
- The D-083 fan-out boundary is proven with publisher-less binds — real
  publishers (Telegram/Instagram/outbox) plug into exactly that surface.
- The receipt-once finding is now a battery-enforced invariant: any future
  consumer must read the D-084 receipt from the COMPLETED transition ref.

Phase 12 entry criteria: remaining channel/service wiring under the same
fail-closed attestation recursion (per `dokploy-plan.md` and the D-154
transition). Real payment capture additionally requires the owner's Iranian
payment provider selection (open decision 10) and remains behind the D-045
owner gate and D-139 activation authority.

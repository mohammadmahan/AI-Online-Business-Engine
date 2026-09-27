# Phase 14 Live Wiring Report — Scheduling Engine (D-164)

**Attestation:** `phase14.scheduling_wiring_attestation.v1`
**Verdict:** `PHASE14_IGNITED` (dry-run, zero dispatches, zero durable lock claims)
**Upstream:** `phase12.shipping_wiring_attestation.v1` (D-162) — digest `788534378f4c75db…`
(battery-built chain), rooted in the D-112 ledger row kind
`phase12_shipping_wiring_attestation`, chain intact.
**Slot-14 prelude:** D-163 closed registry slot 14 **CRM-not-needed** — the three
pillars (WooCommerce D-034–D-045 + `commerce.sync_orchestrator`, Notion D-156,
n8n D-155) already satisfy customer/order lifecycle needs; slot 14 resolves to
the existing facade, no CRM is built or ignited.
**Engine:** `local/scripts/live_wiring_phase14_igniter.py` (SCH-01..SCH-05)
**Battery:** `local/tests/test_live_wiring_phase14.py` — 44 tests, ×2 green
**Governance:** D-045 / D-093–D-096 / D-114 / D-124 / D-139 / D-154 / D-163 /
D-162 / §17 / §21.8. Chain: D-154 → … → D-161 → D-162 → **(D-163)** → **D-164**.

---

## 1. Upstream attestation verification (SCH-01)

The Phase 12 attestation is verified **before any calendar call**: schema
(`phase12.shipping_wiring_attestation.v1`), the `PHASE12_IGNITED` verdict, the
manifest binding, and the D-162 attestation's canonical bytes recomputed and
matched against the SHA-256 commitment rooted in the D-112 ledger
(`phase12_shipping_wiring_attestation`), with full chain integrity delegated to
the injected verifier. Every refusal class (absent / raised / wrong schema /
incomplete verdict / drifted digest / unrooted / broken chain) provably leaves
the calendar untouched — the battery asserts the store factory is never
invoked and the engine is never constructed on refusal.

## 2. Runtime profile & seams (SCH-02)

The injected census must mark `runtime_profile_verified` and Phases **5–12**
present + VERIFIED + WIRED (slot 14/Phase 13 is deliberately **not** required —
D-163 closed it). The repo-real seams are asserted importable and pinned to
the D-154 `ENTRY_POINTS` registry:

| Seam | Module | Registry pin |
|---|---|---|
| Scheduling engine | `canonical.scheduling_engine` | `ENTRY_POINTS[15]` ("Marketing Automation") |
| Scheduling contracts | `canonical.scheduling_contracts` | supporting (exempt) |
| Scheduling worker | `canonical.scheduling_worker` | supporting (exempt) |
| Orchestration / fan-out | `canonical.orchestration_engine` | `ENTRY_POINTS[13]` |
| D-027 event store | `services.sync_engine` | supporting (exempt) |

The **load-bearing pin** is the slot-15 cross-walk check: the D-154 cross-walk
binds registry slot 15 to `canonical.scheduling_engine` (slot 14 was
dispositioned by D-163). Any mismatch refuses as **registry drift** /
**cross-walk drift** before SCH-03 runs.

## 3. Scheduling contracts & invariants (SCH-03) — through the REAL validator

| Invariant | Mechanism | Evidence |
|---|---|---|
| Post contracts | REAL `validate_scheduled_post`: post_id/content_ref patterns, non-empty unique targets within `MAX_TARGETS_PER_POST` (D-114), ISO-8601 `scheduled_for` supplied by the planner — never read from the clock (D-093) | 7 rejection classes enforced with named reasons (`post_id` / `content_ref` / `targets` / `unique` / `exceeds` / `ISO-8601` / `status must be one`); a conforming probe post passes |
| Idempotency | `schedule_idempotency_key(content_ref, sorted targets, scheduled_for)` = SHA-256, clock-free | deterministic across runs; a different window yields a different key (replay-attack resistance) |
| Slot arithmetic | `slot_bucket` / `slot_lock_key` floor every instant into 15-minute (platform, bucket) keys — pure, no clock | instants 10:07 and 10:09 collapse to one key; different platforms never collide |
| Due semantics | `is_due(scheduled_for, now_iso)` — both instants supplied, pure | boundary (`<=`) and ordering proven |
| Probe envelope | `PROBE_ENVELOPE = ("plan", "slot_query", "calendar_view")` | **no dispatch/publish capability exists in the probe** — publishing stays with the owner-gated D-070/D-076 publishers and D-139 |

## 4. Dry-run scheduling cycle trace (SCH-04)

Two synthetic posts (`phase14-probe-0001` at 10:07, `phase14-probe-0002`
content variant) over the REAL `SchedulingEngine` (D-093/D-094/D-096) on the
REAL D-027 parity `EventStore` with the **ephemeral** slot backend:

| Step | Result | Telemetry |
|---|---|---|
| START | ok | cycle id `phase14-scheduling-probe-0001` |
| AUTH | ok | envelope plan/slot_query/calendar_view; dispatch owner-gated |
| SCHEDULE | ok | durable SCHEDULED ref; identical re-schedule → `retried` (same key); conflicting payload under the same post_id → `IntegrityError` |
| SLOTS | ok | post B in the same (telegram, 10:00 bucket) → durable `SLOT_CONFLICT` (post NOT scheduled); reschedule A→10:22 claims the NEW slot first, supersedes the old (ledger keeps the row); the freed 10:00 slot is re-claimed by B |
| TRANSITIONS | ok | A: SCHEDULED→DUE (supplied instant)→CANCELLED; terminal immutability — cancel AND reschedule on CANCELLED refuse (`immutable_CANCELLED`) |
| FANOUT | ok | due-notification through the REAL `FanOutEngine`, publisher-less binds (`no_publisher_bound`), ephemeral D-079 lock, durable receipt verified |
| CALENDAR | ok | view rebuilt from DURABLE events alone matches the driven lifecycle exactly — **zero drift** (A: CANCELLED+rescheduled at 10:22; B: SCHEDULED) |
| VERIFY | ok | publish-marker sweep over the live store records — clean; slot backend asserted ephemeral |
| CLEANUP | ok | `phase14-scratch:schedule` artifact deleted, zero residue |

**Lock hygiene (the D-079 discipline, third application):** the slot-lock
default backend claims keys in live PostgreSQL (`scheduling.slot_lock`) or the
shared `local/volumes/scheduling/slot_locks.json`. The probe injects
`_EphemeralSlotLocks` — claim/supersede/history semantics identical to
`_JsonSlotLocks`, ZERO durable footprint — and the VERIFY step refuses any
non-ephemeral backend (battery-proven with a file-backed `_JsonSlotLocks`
swap-in).

**Cycle timing:** the SCH-01..SCH-05 ignition cycle ≈ **60 ms** in-process
(including the battery's authentic upstream chain build — real
D-162 → D-161 → … → D-154). Attestation digest `29b3c5df6a62b152…`,
byte-stable across runs.

## 5. Rate/volume guardrails

`LIMITS`: Class-A retries ≤ 2 · per-operation timeout 15 s (D-151) ·
15-minute slot granularity (D-094) · `max_fanout_events` 5 per cycle. The
engine never invents destinations: fan-out targets are injected, and the probe
configures none — the only fan-out traffic is the publisher-less due probe.

## 6. Security posture

- **Publishing is a boundary:** the VERIFY audit scans the *live*
  `store.records` for publish markers (`live_dispatch`, `webhook_secret`,
  `auth_code`, `pan`, `card_number`, `carrier_secret`) — any hit fails the
  run. The probe schedules; it never dispatches.
- **No wall clock (D-093):** every instant (`scheduled_for`, `now_iso`) is
  supplied by the producer; the engine core performs no clock reads.
- **D-124 redaction:** content payloads, customer refs and channel tokens are
  never emitted; the battery scrubs every output for canaries; only hashes,
  counts, status names, verdicts and step telemetry escape.
- **D-079 lock hygiene:** both the fan-out lock and the slot backend are
  ephemeral process-local objects; no probe key reaches PG or any shared file.
- **Purity (AST-pinned):** no network/db/shell imports or calls in the engine;
  injected store/lock/fanout transports only.

## 7. Verification & battery

- New battery **44/44 ×2** (SCH-01..04 refusal classes, slot-15 cross-walk
  drift, REAL-validator rejection matrix, ephemeral-backend semantics +
  swap-in refusal, direct contract probes: due boundary, terminal edges,
  standalone engine lifecycle, key determinism, emission contract, redaction
  scrubs, AST audits).
- Full regression **1999/1999 ×2 consecutive green across 79 modules**
  (1955 + 44), zero bad, zero skipped, per-chunk counts identical across runs
  and reconciled to the untouched-module invariant (the 78 pre-existing
  modules still carry exactly 1955 tests).
- **Invocation contract:** the battery must run from the repository **root**
  (`python3 -m unittest local.tests.…`) — environment contract, not a
  regression. Heavy chunks: the live-PG cluster (≈ 518 s) and
  `test_phase26_dr_closeout` (≈ 437 s) dominate wall-clock.

## 8. Handover to Phase 15 — Analytics (registry slot 16)

Verified and inherited by Phase 15:

- The calendar spine is *verified, not opened*: no dispatch capability exists
  in the probe surface, and the scheduling worker's live due-loop remains
  behind the owner gate.
- The D-083 fan-out boundary now carries four proven probe classes
  (order/settlement/tracking/due-reminder events) with publisher-less binds.
- The remaining registry path is explicit: slot 16 (Analytics,
  `canonical.analytics_engine`, D-085–D-088 read-side), 17 (AI Business
  Analyst, `canonical.analyst_engine`), 18 (HITL, `canonical.ai_hitl_service`).

Phase 15 entry criteria: remaining service wiring under the same fail-closed
attestation recursion (per `dokploy-plan.md` and the D-154 transition). The
D-163 disposition stands: no CRM exists or is planned; slot 14 remains bound
to the existing `commerce.sync_orchestrator` facade.

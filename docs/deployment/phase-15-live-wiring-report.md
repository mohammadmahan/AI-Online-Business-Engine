# Phase 15 Live Wiring Report — Analytics Engine (D-165)

**Attestation:** `phase15.analytics_wiring_attestation.v1`
**Verdict:** `PHASE15_IGNITED` (dry-run, read-only, zero egress, zero durable footprint)
**Upstream:** `phase14.scheduling_wiring_attestation.v1` (D-164) — digest `a3cd491ebdb61ef2…`
(battery-built chain), rooted in the D-112 ledger row kind
`phase14_scheduling_wiring_attestation`, chain intact.
**Engine:** `local/scripts/live_wiring_phase15_igniter.py` (ANA-01..ANA-05)
**Battery:** `local/tests/test_live_wiring_phase15.py` — 44 tests, ×2 green
**Governance:** D-045 / D-085–D-088 / D-114 / D-124 / D-139 / D-154 / D-163 /
D-164 / §17 / §21.8. Chain: D-154 → … → D-162 → D-164 → **D-165**.

---

## 1. Upstream attestation verification (ANA-01)

The Phase 14 attestation is verified **before any engine call**: schema
(`phase14.scheduling_wiring_attestation.v1`), the `PHASE14_IGNITED` verdict,
the manifest binding, and the D-164 attestation's canonical bytes recomputed
and matched against the SHA-256 commitment rooted in the D-112 ledger
(`phase14_scheduling_wiring_attestation`), with full chain integrity delegated
to the injected verifier. Every refusal class (absent / raised / wrong schema /
incomplete verdict / drifted digest / unrooted / broken chain) provably leaves
the analytics surface untouched — the battery asserts the event stream is
never read on refusal (a counting `events_source` records ZERO calls).

## 2. Runtime profile & seams (ANA-02)

The injected census must mark `runtime_profile_verified` and Phases
**5–12 and 14** present + VERIFIED + WIRED (slot 14/CRM is deliberately **not**
a census row — D-163; Phase 14 is the program label for registry slot 15).
The repo-real seams are asserted importable and pinned to the D-154
`ENTRY_POINTS` registry:

| Seam | Module | Registry pin |
|---|---|---|
| Analytics engine | `canonical.analytics_engine` | `ENTRY_POINTS[16]` ("Analytics") |
| Analytics contracts | `canonical.analytics_contracts` | supporting (exempt) |
| Analytics worker | `canonical.analytics_worker` | supporting (exempt) |
| Scheduling engine | `canonical.scheduling_engine` | `ENTRY_POINTS[15]` |
| Orchestration engine | `canonical.orchestration_engine` | `ENTRY_POINTS[13]` |
| D-027 event store | `services.sync_engine` | supporting (exempt) |

The **load-bearing pin** is the slot-16 cross-walk check: the D-154 cross-walk
binds registry slot 16 to `canonical.analytics_engine`. Any mismatch refuses
as **registry drift** / **cross-walk drift** before ANA-03 runs.

## 3. Analytics contracts & invariants (ANA-03) — through the REAL contracts

| Invariant | Mechanism | Evidence |
|---|---|---|
| Windowing purity | `parse_occurred_at` / `window_key`: ISO-8601 from the EVENT's own recorded instant — never the clock (D-085) | conforming instants (with offset and `Z`) parse to hour/day/month keys; `unparsable`, non-string and over-bound (`> 64` chars, D-114) refuse with named reasons; unknown windows refuse |
| Classifier | `classify_event` over the durable ref payload only (D-087: no domain imports) | publication `published`/`duplicate_publish_blocked` → `publication_published`; `terminal_reject` → `publication_failed`; in-flight outcomes → None; `oms|order|<id>` → `order_placed`; COMPLETED transition → `order_completed` + `revenue_minor` (dual metric, value = the order total); CANCELLED → `order_cancelled`; nested/foreign ids → None; a malformed metric payload raises Class-B |
| Rollup math | `add_metric` / `finalize_rollup` / `merge_rollups` | counts accumulate, revenue sums (150,000 over two folds), finalize/merge deterministic |
| Report identity | D-088 `window_hash(kind, window, bounds, cursor)` | same inputs ⇒ same hash (idempotent generation); a different cursor ⇒ different hash |

## 4. Dry-run analytics cycle trace (ANA-04)

A six-event synthetic stream (2 publications, 1 order-placed, 1 COMPLETED
transition with revenue 450,000 minor, 1 CANCELLED transition, 1 in-flight
outcome) over the REAL `ProjectionEngine` (D-086) with the injected
`events_source` adapter and the **ephemeral** in-memory cursor store:

| Step | Result | Telemetry |
|---|---|---|
| START | ok | cycle id `phase15-analytics-probe-0001` |
| AUTH | ok | read-only envelope: analytics consumes durable events and produces aggregates; it NEVER writes to any domain, warehouse or platform (D-087 boundary) |
| INGEST | ok | incremental fold: 5 metrics consumed (the in-flight event classifies to None but still advances the cursor), cursor 0 → 16; daily snapshot: 2 published / 1 placed / 1 completed / **450,000 minor revenue**; hourly (`2026-09-20T09`) and monthly (`2026-09`) buckets fold the same events |
| IDEMPOTENT | ok | re-consume after the cursor advance is a no-op (from_cursor == 16) — exactly-once |
| FLAG | ok | a malformed metric payload (unparsable `occurred_at`) is **quarantined** (payload hashed, never stored) and **never advances the cursor** (held at 16) — D-085 "flag, never guess", fail-closed |
| REBUILD | ok | `rebuild()` from zero byte-matches the incremental rollups — **incremental == full replay, zero drift** (D-086) |
| REPORT | ok | D-088 `window_hash` generated (64-hex, idempotent) |
| VERIFY | ok | cursor backend asserted ephemeral; egress-marker sweep clean |
| CLEANUP | ok | `phase15-scratch:analytics` artifact deleted, zero residue |

**Ephemeral discipline:** the analytics cursor default backend persists to
`local/volumes/analytics/projection.json` (or live PG). The probe injects
`_EphemeralCursorStore` — `get_cursor`/`advance`/`reset`/`rollups` semantics
identical to `_JsonCursorStore` plus the malformed-event register, ZERO
durable footprint — and a **fail-closed entry gate refuses any non-ephemeral
backend before any engine work** (battery-proven with a fully functional
foreign store: every data check passes, the gate still refuses by class).

**Cycle timing:** the ANA-01..ANA-05 ignition cycle ≈ **71 ms** in-process
(including the battery's authentic upstream chain build — real
D-164 → D-162 → … → D-154). Attestation digest `22e973f5084bdfc7…`,
byte-stable across runs.

## 5. Security posture

- **No egress (D-087/D-085):** the engine reads only the injected synthetic
  stream and writes only the ephemeral in-memory store; no warehouse, no
  external analytics platform, no vendor module import. The VERIFY step
  sweeps the aggregates for egress markers; the battery scrubs every output
  for canaries.
- **No wall clock (D-085):** every instant is the event's own recorded
  `occurred_at`; the core performs no clock reads.
- **D-124 redaction:** campaign ids appear as hashes; the malformed-quarantine
  record carries a payload hash and reason only — the raw payload never
  escapes (battery-asserted, including for the `"garbage"` literal).
- **Purity (AST-pinned):** no network/db/shell imports or calls in the engine;
  injected source/store transports only.

## 6. Verification & battery

- New battery **44/44 ×2** (ANA-01..04 refusal classes, slot-16 cross-walk
  drift, slot-14-not-required census proof, REAL-contract rejection matrix,
  classifier purity + dual-metric + cancelled-class probes, revenue
  sum/count fold, report identity, malformed quarantine with cursor held,
  rebuild determinism, non-ephemeral gate refusal, cleanup refusal, emission
  contract, redaction scrubs, AST audits).
- Full regression **2043/2043 ×2 consecutive green across 80 modules**
  (1999 + 44), zero bad, zero skipped, per-chunk counts identical across runs
  and reconciled to the untouched-module invariant (the 79 pre-existing
  modules still carry exactly 1999 tests).
- **Invocation contract:** the battery must run from the repository **root**
  (`python3 -m unittest local.tests.…`) — environment contract, not a
  regression. Heavy chunks: the live-PG cluster (≈ 526 s) and
  `test_phase26_dr_closeout` (≈ 446 s) dominate wall-clock.

## 7. Handover to Phase 16 — AI Business Analyst (registry slot 17)

Verified and inherited by Phase 16:

- The analytics read-side is *verified, not opened*: the projection loop is
  read-only, ephemeral, and exactly-once — the analyst consumes the same
  D-085/D-086 aggregates, never raw domains (D-087 boundary).
- The D-088 report identity (`window_hash`) is the stable join key for
  analyst insights and HITL evidence.
- The remaining registry path is explicit: slot 17 (AI Business Analyst,
  `canonical.analyst_engine`), 18 (HITL, `canonical.ai_hitl_service`) — the
  final two ignitions of the program.

Phase 16 entry criteria: remaining service wiring under the same fail-closed
attestation recursion (per `dokploy-plan.md` and the D-154 transition). The
D-163 disposition stands: no CRM exists or is planned; slot 14 remains bound
to the existing `commerce.sync_orchestrator` facade.

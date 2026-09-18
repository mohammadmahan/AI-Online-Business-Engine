# Phase 25 — Full System Test & E2E Failure/Recovery Ladder (D-133–D-136)

- Status: **specification (M0) — decisions PROPOSED, pending owner
  approval; implementation gated on approval**
- Discipline: local-first (D-053), design-first, zero-skip testing;
  strictly localhost/air-gapped (D-045) — mock payment/shipping/
  channel gateways only, no real credentials; deterministic
  chronology (injected logical clocks only — D-085/D-093/D-121
  precedent); every prior-phase boundary respected (Phases 0–24),
  including the Phase 24 portability contracts and the Phase 20
  AST gates.

## 0. Governance reconciliation

- Baseline: Phase 24 closed at `058bc8a` (battery 796/796 ×2 green
  + census run, zero warnings; census T1=694 · T2=44 · T3=51 ·
  T4=7 = 796 across 31 modules; ladder 46/46).
- MASTER_PLAN §13 authority: **Phase 25 = Full System Test** — the
  end-to-end flow `Instagram lead → conversation → product
  discovery → cart/order → payment → payment verification →
  inventory → shipping → notification → analytics`, with
  **failures and recovery tested at every important step**.
- New decisions D-133..D-136 registered as **Proposed**; nothing
  below them resolves silently (D-064 rule). D-117..D-124 and
  D-125..D-132 remain Approved and untouched.

## 1. D-133 — End-to-end business flow orchestration (Proposed)

`canonical/e2e_conductor.py` (+ `canonical/e2e_contracts.py`): a
PURE cross-phase conductor — every adapter/store injected
(RULES §35); the conductor imports no vendor, service, or I/O
module.

- **Declared stage pipeline** (each stage a named contract with a
  declared input/output envelope, pinned via the Phase 24
  conformance style):
  1. `LEAD_CAPTURE` — Instagram mock adapter (Phase 9 pair)
  2. `CONVERSATION` — dialogue/discovery turn (mock NLU; Phase 9
     mock channel)
  3. `PRODUCT_DISCOVERY` — canonical product lookup (Phase 3/12
     stores)
  4. `CART_ORDER` — OmsEngine cart → order (Phase 12)
  5. `PAYMENT` — mock gateway intent (no real PSP)
  6. `PAYMENT_VERIFICATION` — deterministic verify/fail verdict
  7. `INVENTORY` — reservation/consume or restore (Phase 12)
  8. `SHIPPING` — mock fulfillment record
  9. `NOTIFICATION` — NotificationEngine dispatch (Phase 14)
  10. `ANALYTICS` — ProjectionEngine incremental pass → D-085
      rollups (Phases 13/17 frame read)
- **Unbroken trace context:** a D-121 `TraceContext` root is
  created at lead capture; `trace_id`/`correlation_id` traverse
  every stage call unchanged; each stage emits `engine.log.v1`
  records. Battery asserts: same root ids end-to-end, zero schema
  mutation of the context, and every stage boundary audited.
- **Zero schema mutation:** stage envelopes are declared data;
  cross-stage payloads never gain undeclared keys (harness-
  asserted).

## 2. D-134 — Deterministic chaos & fault-injection ladder (Proposed)

Structured, reproducible failures via the Phase 21
`qa_toolkit.FaultScript` schedule at each lifecycle boundary:

| Boundary | Injection | Expected deterministic outcome |
|---|---|---|
| Channel adapters | transient connection outage (Class-A shape) | RetryPolicy recovers; flow completes; attempts audited |
| AI stage | D-127 budget refusal at 100% | pre-dispatch refusal, zero provider calls, order flow pauses cleanly, no partial state |
| Media store | LocalObjectStore fault at fan-out | fan-out fail-closed, dead-letter/HITL materialization, no phantom publication |
| Locks | contention/timeout on fan-out + slot locks | deterministic refusal verdicts; no double-claim |
| Payment verify | verification failure verdict | order → failed path; inventory RESTORED; notification = failure notice; analytics records the outcome |

Every scenario asserts: the exact D-052 class, correct fallback/
circuit-breaker engagement (D-123 probe observes real breaker
rows), transactional rollback leaving ledgers exactly-consistent,
and **recovery to completion via retry/replay** — never manual
state surgery. All clocks logical (D-085/D-093/D-121).

## 3. D-135 — Automated state reconciliation & self-healing (Proposed)

- **Outbox reconciliation:** a fault injected BETWEEN the durable
  event write and the downstream effect leaves an "undispatched"
  event; the reconciler replays from the D-027 store with exactly-
  once semantics (idempotency keys ⇒ `skipped_duplicate` on
  re-delivery; no duplicate side effects).
- **Stranded-lock sweeps:** a holder that "crashes" between claim
  and release leaves a lock; the sweep reclaims it deterministically;
  zero phantom records before/after.
- **Compaction recovery:** cold start after an interrupted Phase 23
  compaction (snapshot written, teardown not) re-verifies the
  archive attestation and re-runs idempotently; a torn transaction
  rolls back fail-closed (Phase 23 semantics re-proven at flow
  level).
- **Process-crash simulation:** interruption at any stage boundary
  → restart reconstructs state from DURABLE stores only (no
  in-process cache required for correctness — the Phase 6/17
  invariant), zero data loss, ledger dedup exact.

## 4. D-136 — Full-spectrum battery & acceptance gates (Proposed)

`tests/test_phase25_full_system.py`, declaring the established T4
census convention:

- **Offline hermetic E2E class:** the full 10-stage flow on
  JSON/memory backends + mock adapters — happy path, plus EVERY
  D-134 fault scenario and D-135 reconciliation scenario.
- **Live-PG E2E class:** the same scenarios against the real
  PostgreSQL store (runs while the stack is up; never skipped).
- **Acceptance gates:** zero skips; full battery green TWICE
  consecutively (+ census run reconciling exactly); ladder green;
  AST/entropy/bounds sweeps CLEAN; `git diff --check` PASS;
  stack 5/5 healthy.

## 5. Milestone plan

| MS | Content | Proof |
|---|---|---|
| M0 | This spec + D-133..D-136 Proposed + TODO row | owner approval |
| M1 | `e2e_contracts.py` + `e2e_conductor.py` (pure conductor, stage envelopes, trace propagation) | offline happy-path diag: 10 stages, one trace |
| M2 | Fault ladder wiring + reconciliation/sweep routines | chaos diag incl. live-PG leg |
| M3 | `test_phase25_full_system.py` (offline + live-PG classes) | suite green, zero skips |
| M4 | Battery ×2 + census + sweeps + docs + commit/push | gates of §4 all PASS |

## 6. Owner decision points

1. **Approve / amend D-133..D-136** (registered as Proposed).
2. **Flow scope:** the 10 stages above are MASTER_PLAN's exact
   list; payment/shipping are mock-gateway intents (no real PSP,
   D-045). Confirm or trim.
3. **Conductor placement:** canonical (pure) with injected service
   adapters, per RULES §35 — same pattern as every engine.

## 7. Verification record (M4 closeout, 2026-09-18)

- **Governance:** D-133–D-136 flipped Proposed → **Approved** per
  the owner's execution order; flow scope confirmed as the
  MASTER_PLAN ten-stage list with mock gateways (D-045).
- **M1 (conductor):** `canonical/e2e_contracts.py` +
  `canonical/e2e_conductor.py` — pure, zero I/O imports. Proven:
  ten stages under ONE unbroken root trace (ten distinct causal
  ids), zero-schema-mutation guard rejects rogue keys, strict
  stage binding (missing AND unknown stages rejected), audited
  FAILURE path. The harness forced a real design fix: the D-052
  class is now classified AT the stage boundary (explicit
  `.failure_class` wins, else the canonical message classifier) —
  the audited class is what recovery routes on, never the
  exception type name. The root trace ids are injected into the
  flow context so the unbroken-trace guard is checkable in data.
- **M2 (fault ladder & recovery):** all five D-134 scenarios pinned
  with `FaultScript` reproducibility: Class-A outage recovers by
  REPLAY (attempt 2, jitter-free backoff, end state byte-equal to
  the happy path incl. inventory); D-127 exhaustion refuses
  PRE-dispatch (zero provider invocation, flow stopped exactly at
  the boundary, order PLACED, inventory untouched; the refused
  logical event meters its tokens row per the shipped
  `consume_llm` shape; NOT replay-recoverable — terminal at flow
  level); media fault fails closed (no notification work at all);
  delivery-lock contention — the original claim survives
  byte-untouched and the flow yields; payment-verification failure
  → order CANCELLED, inventory RESTORED (8→10), failure notice
  queued through the real D-089 template registry. D-135: the
  stranded-lock sweep is idempotent with zero phantom rows and
  never resurrects vanished rows; state rebuilds from durable refs
  only; outbox replay is exactly-once on the JSON store AND the
  live PG store.
- **M3 (battery):** `tests/test_phase25_full_system.py` — 15
  offline tests + 3 live-PG E2E. Live leg: the FULL ten-stage flow
  persisted through the real `PgEventStore` (order VALIDATED,
  inventory 10→8), live outbox replay exactly-once
  (`skipped_duplicate` verdict on re-delivery), and a conflicting
  duplicate → `IntegrityError` (human review, D-027).
- **M4 (gates):** FULL battery **814/814, two consecutive green
  runs + one census run, zero warnings**. Ladder 46/46. Census
  reconciles exactly: **T1=706 · T2=44 · T3=54 · T4=10 = 814
  (32 modules), green=True**. AST sweep CLEAN (68 canonical files);
  entropy CLEAN (112 files); `git diff --check` PASS; stack 5/5
  healthy.
- **Test-side lessons pinned in the battery:** (1)
  `succeeded_references()` matches on an event-id PREFIX (D-027
  parity contract) — per-source isolation requires event_id-prefix
  filtering in assertions; (2) budget assertions read `consumed()`
  row semantics, not row counts (a refused logical event still
  meters its first resource); (3) analytics metric eids must be
  deterministic across replays — the harness adopted the OMS's own
  durable ids (`oms|order|<key>`), so replay reaches a FIXED POINT
  (no new events, cursor motionless) instead of double-projecting.

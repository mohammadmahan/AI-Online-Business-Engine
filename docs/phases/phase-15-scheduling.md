# Phase 15 — Content Calendar & Scheduling Engine (D-093–D-096)

- Status: **implemented (M1–M4), owner-approved decisions**
- Discipline: local-first (D-053), design-first, zero-skip testing;
  injectable clock is the only time source; the scheduler never
  publishes — it bridges to the Phase 11 FanOutEngine.

## 1. Objective

Let campaigns and content plans be scheduled for future release
windows with per-platform slot guarantees, deterministic due
detection, exactly-once bridging to fan-out, and a fully auditable,
restart-reconstructible calendar.

## 2. Decision table

| Decision | Content | Module |
|---|---|---|
| D-093 | `ScheduledPost` (content_ref, targets = Phase 11 matrix, scheduled_for producer ISO, idempotency key); lifecycle SCHEDULED → DUE → DISPATCHED + CANCELLED / RESCHEDULED with full provenance; injectable clock only | `scheduling_contracts.py` |
| D-094 | Per-platform slot locks (`scheduling.slot_lock` PG PK-as-lock, JSON parity); configurable minimum gap; slot bucket from pure arithmetic on scheduled_for; `slot_conflict` = Class-B before dispatch | `scheduling_engine.py` |
| D-095 | Due scanner: durable data only, ingest_seq order, injected `now_iso()`; bridges DUE posts to `FanOutEngine.route()+dispatch()`; consumes receipts; never publishes, never retries platform semantics | `scheduling_worker.py` |
| D-096 | Only pre-DISPATCHED posts mutable; RESCHEDULED supersedes the slot (ledger keeps history); immutable audit trail on D-027; calendar view rebuilds from durable events alone | engine + worker |

## 3. Architecture flow

```
producer (campaign planner / content pipeline)
        │  ScheduledPost (validated locally, D-093)
        ▼
SchedulingEngine.schedule ──► slot lock claim (D-094)
        │                       │ slot_conflict (Class-B, recorded)
        ▼                       ▼
  SCHEDULED (durable event, slot reserved)
        │
        ▼
DueScanner.scan (injected now_iso, ingest_seq order)
        │  scheduled_for <= now ⇒ DUE
        ▼
bridge: FanOutEngine.route() + dispatch()   ← Phase 11
        │  receipts consumed (never re-implemented)
        ▼
DISPATCHED (durable) — calendar view rebuilt from events alone
```

## 4. Security boundaries

- Zero network in canonical modules; the fan-out engine and its
  publishers are injected and remain behind their own boundaries.
- No credentials, no `os.environ`; redaction inherited from store
  discipline (D-045).
- The scheduler writes ONLY scheduling events/rows; platform
  publishing semantics belong exclusively to Phase 9/10/11.

## 5. Milestones

| Milestone | Content | Status |
|---|---|---|
| M1 | Contracts: schema, lifecycle, slot rules, conflict vocabulary | done |
| M2 | Engine: slot locks (PG + JSON parity), schedule events, calendar view | done |
| M3 | Worker: due scanner, fan-out bridge, receipts, reconciliation | done |
| M4 | Suite incl. live-PG E2E, AST audit, full regression, docs | done |

## 6. Verification record (M4 closeout, 2026-09-17)

- Suite `local/tests/test_phase15_scheduling.py`: **24/24 OK, zero
  skipped** (21 offline across M1–M3 + 3 live-PG E2E: real
  `PgEventStore` + real PG `scheduling.slot_lock`; 8-thread
  single-winner slot claim; schedule→conflict→reschedule→reclaim
  chain; due-scan → DISPATCHED with fresh-engine restart parity).
- Full battery **576/576 OK, zero skips**; ladder 46/46 OK;
  containers 5/5 healthy (live layer ran, not skipped).
- AST audit CLEAN — zero network imports, zero publishing-module
  imports in canonical scheduling modules (the D-095 boundary is
  import-level verified), zero decision verbs, zero `os.environ`;
  the only `subprocess` is the test-only `_stack_up()` Docker guard
  (Phase 9/10/13/14 pattern). Secret scan CLEAN;
  `git diff --check` PASS.

### Defects exposed and fixed in-batch

1. **M1:** `is_transition_legal` checked the LEGAL_EDGES key guard
   BEFORE the RESCHEDULED special case — since RESCHEDULED is a
   revision marker (not a source state, hence not a key), the
   SCHEDULED→RESCHEDULED edge was unreachable. Fixed ordering;
   edge matrix now fully tested (6 legal / 6 illegal).
2. **M2:** superseded slots blocked re-claim forever (the old row
   kept `claim()` losing) and reschedule recorded its transition
   even when the NEW slot conflicted. Redesigned: slot rows carry
   `active` (inactive rows stay as ledger history and are
   re-claimable, D-096), and reschedule claims new slots FIRST —
   a conflicting reschedule changes nothing (D-094).
3. **M2:** transition event ids were per-(post, transition) and
   collided on retried reschedules (D-027 conflicting-duplicate).
   Now attempt-unique via a durable reschedule count; `_record`
   never swallows IntegrityError (conflicting duplicates must
   surface, D-027).
4. **M4 (test premises):** 09:20 floors to bucket 09:15, not 09:00
   (offline fixture used the wrong slot); live tests initially used
   fixed platforms/instant-absolute assertions, which collide with
   prior runs on the shared durable ledger — switched to run-scoped
   platforms and delta-based assertions (Phase 13/14 precedent).

### Owner gates (standing)

- No platform endpoints or credentials (D-045) — none exist, none
  requested; the fan-out engine and publishers are injected.
- Phase 15 passing does NOT prove live platform compatibility.
- Nothing leaves the local stack; slot buckets are pure arithmetic
  on producer-supplied instants (no wall-clock reads).

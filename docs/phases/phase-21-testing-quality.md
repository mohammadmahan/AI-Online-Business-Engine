# Phase 21 — Testing & Quality Engineering (D-117–D-120)

- Status: **in execution (M1–M4), owner-approved decisions**
- Discipline: local-first (D-053), zero-skip, zero-stub,
  deterministic; no external network, no new dependencies, no wall
  clock in any decision, mock/local actors only (D-045).

## 1. Objective

Turn the 702-test battery into a formally verified quality system:
cross-phase state-machine invariants, deterministic chaos/fault
injection at injected seams, seeded fuzz hardening of every D-114
entry point, and a declared test taxonomy with machine-readable
reporting.

## 2. Decision table

| Decision | Content | Test artifact |
|---|---|---|
| D-117 | Cross-phase state-machine invariant auditing (5 machines) | `test_phase21_qa.TestM2Invariants` |
| D-118 | Deterministic fault injection & local chaos discipline | `test_phase21_qa.TestM3Chaos` |
| D-119 | Seeded mutational fuzz hardening of D-114 entry points | `test_phase21_qa.TestM4Fuzz` |
| D-120 | Four-tier suite taxonomy + machine-readable QA report + zero-skip gate | `test_phase21_qa.TestM1Taxonomy` |

## 3. Architecture flow

```
qa_toolkit (M1: pure, deterministic)
  ├─ TierReport / build_tier_report .... D-120 machine-readable census
  ├─ StateMachineAudit ................. D-117 closed-edge-matrix prover
  ├─ FaultInjector / FlakyDispatch ..... D-118 failure seams (injected callables)
  └─ SeedCorpus / mutate / fuzz_entry .. D-119 deterministic mutational fuzzer
        │
        ▼
test_phase21_qa.py (M2–M4)
  ├─ T2 invariants over oms/scheduling/analyst/hitl/admin matrices
  ├─ T3 chaos: live PG aborts, races, attestation reconciliation
  └─ T4 fuzz: gate + six hardened validators, frozen verdict fixtures
```

## 4. Security boundaries

- Faults are injected ONLY at injected callables (handlers,
  dispatchers, vault seams) — shippable modules are never
  monkeypatched at runtime.
- The fuzzer is pure stdlib, seeded, and step-budgeted: no
  randomness, no hangs, no network, no filesystem side effects.
- Chaos tests restore any tampered live-PG row byte-exactly
  (Phase 20 precedent) and verify chain integrity after recovery.
- Zero AST-relevant imports in `qa_toolkit.py` (no os/time/random).

## 5. Milestones

- **M1** — `local/canonical/qa_toolkit.py`: tier taxonomy +
  report builder (D-120), state-machine audit primitives (D-117),
  deterministic fault injectors (D-118), seeded fuzzer (D-119).
- **M2** — Invariant battery: all five edge matrices proven closed;
  live-PG refused-write row-count checks.
- **M3** — Chaos battery: handler/dispatcher exceptions, transient
  dispatch, mid-transaction PG aborts, ledger contention —
  clean-rollback + audit-truth + ledger-integrity invariants.
- **M4** — Fuzz battery over all D-114 entry points with frozen
  verdict fixtures; full regression; verification record below.

## 6. Verification record (M4 closeout, 2026-09-18)

**Battery:** 724/724 OK, zero skipped — two CONSECUTIVE full-battery
runs green (zero-flake claim). Ladder 46/46 OK.

**Tier census (D-120, derived from discovery output, reconciles exactly
724 = 724 across 28 test modules):**

| Tier | Tests |
|---|---|
| T1_UNIT | 631 |
| T2_SUBSYSTEM_LADDER | 44 (`test_ladder` non-E2E classes) |
| T3_LOCAL_PG_INTEGRATION | 42 (`*LivePgE2E` classes) |
| T4_FULL_E2E | 7 (`*EndToEnd` classes: L11 flow ×2, n8n bridge ×5) |

Machine-readable artifact: `docs/reports/phase-21-tier-report.json`
(schema `qa.tier_report.v1`, generated from the final green run).

Exact per-module census is derivable at any time:
`python3 -c "import sys; sys.path[:0]=['local','local/scripts'];
from canonical.qa_toolkit import build_census; print(build_census(open('BATTERY_LOG').read()))"`.

**Fuzz (D-119):** 585 deterministic cases over the D-114
`InputHardeningGate` — found and fixed 2 real gaps: lone-surrogate
payloads crashed the gate with `UnicodeEncodeError` (unhandled
exception leak) and `Cs` (surrogate) category codepoints were silently
accepted. Both closed in `security_engine.py`.

**Chaos (D-118):** handler/dispatcher exceptions, transient dispatch,
mid-transaction PG aborts (no succeeded row, recovery completes,
dedupe holds), 8-thread ledger contention (exactly-one-winner),
8-thread live slot-lock race (exactly-one-winner).

**Defects the Phase 21 net caught in shipped phases (fixed + pinned):**

1. **D-095/D-096 DueScanner starvation** (`scheduling_worker.scan`):
   `limit` was applied to the raw ref list BEFORE the terminal skip;
   on the accumulating durable store (15k+ events) already-dispatched
   posts consumed the whole work budget and new posts starved.
   Fixed: limit bounds WORK considered per pass. Pinned offline
   (`TestRegressionPins.test_phase15_scan_limit_bounds_work_not_refs`),
   mutation-checked (old slicing → late post starves forever).
2. **Phase 15 live race key collision**
   (`test_phase15_scheduling.py`): the concurrent slot-claim race
   derived its bucket from `run_id[:2]` (2 hex chars); the durable
   `scheduling.slot_lock` ledger (rows never deleted, D-096) accumulates
   active buckets across battery runs, so a later run sharing a 2-char
   prefix lost ALL races (observed: intermittent `0 != 1` failures).
   Fixed: full run id in the bucket; mechanism reproduced
   deterministically against a leftover bucket (0 winners old-shape,
   1 winner fixed-shape) and pinned live-PG
   (`TestM3Chaos.test_live_pg_slot_lock_race_key_isolation`).
3. **D-114 entry-point lint pollution:** 5 unclosed file handles
   (Phases 4/7/8/12 tests) interleaved `ResourceWarning` lines between
   test locators and results, breaking clean output parsing. All fixed
   with context managers; battery output is now warning-free.

**Audit gates:** extended AST sweep CLEAN (84 files, 0 canonical
findings; subprocess confined to test tooling), secret-entropy scan
CLEAN (94 files, 0 flags), bounds re-audit CLEAN (11/11 modules),
`git diff --check` PASS, stack 5/5 containers healthy.

**Known observation (not a defect):** `time.time_ns()` event-ID
components remain in Phases 9–11 publishers (`instagram_publisher`,
`telegram_publisher`, `orchestration_engine`). These are ROW IDs for
unique storage, not idempotency keys (D-027 keys are revision-marker
based) and not lock state — recorded for a future deterministic-ID
cleanup batch, no behavior change made in Phase 21.

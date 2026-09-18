# Phase 23 — Resilience & Cost Optimization (D-125–D-128)

- Status: **specification (M0) — decisions PROPOSED, pending owner
  approval; implementation gated on approval**
- Discipline: local-first (D-053), design-first, zero-skip testing;
  strictly localhost/air-gapped (D-045); deterministic chronology
  (injected logical clocks only — D-085/D-086/D-093/D-121 precedent);
  immutable-ledger guarantees are NEVER weakened (D-096/D-112/D-115).

## 0. Governance reconciliation (read this first)

- MASTER_PLAN §13 defines Phase 23 as **"Cost Control"**: *before
  adding a paid service, evaluate existing capabilities, open source,
  self-hosting, n8n, Freebuff, total cost, maintenance, and lock-in.*
  This spec implements that mandate for PLATFORM resources and
  extends it to resilience, per the owner's kickoff instruction.
- **Live evidence driving the design (measured 2026-09-18):**
  `events.event_record` = **20,561 rows**; `admin.control_audit` =
  320; `security.hardening_audit` = 74; `scheduling.slot_lock` = 210;
  `admin.circuit_breakers` = **82/82 non-CLOSED** (up from 74 at
  Phase 22 closeout — one battery day grew residue by 8). Durable
  residue grows with every battery run and is currently unbounded.
- **Boundary preserved:** Phases 18/19 ledgers and Phase 20
  attestations are TAMPER-EVIDENT evidence surfaces. Nothing in this
  phase deletes or rewrites an attested chain row. Retention is
  achieved by *snapshot + verified-freeze + archive + safe teardown*,
  never by mutation.
- **Registration discipline:** D-125–D-128 are recorded as
  **Proposed** in `DECISIONS.md` (register row 39) per the D-064
  reconciliation rule — nothing above/below the register resolves
  silently. Implementation (M1–M4) starts only after owner approval.

## 1. Decision table (PROPOSED)

### D-125 — Deterministic retention, compaction & verified-freeze archives

- **Situation:** durable tables grow unboundedly (event_record 20.5k
  rows and climbing with every battery run); unbounded growth is a
  cost and performance liability (the Phase 15 starvation defect was
  exactly a growth-path bug). But naive deletion would break the
  tamper-evident guarantees (D-096 rows never deleted; D-112/D-115
  chain integrity).
- **Decision (PROPOSED):**
  1. **Eligibility by STATE, not age** — compaction candidates are
     rows whose lifecycle is TERMINAL and whose downstream consumers
     are done: `event_record` rows with terminal `processing_status`
     (`succeeded`/`skipped_duplicate`/`terminal_failure`), resolved
     HITL tickets, superseded slot-lock rows (`active = false`).
     Active/contested rows are NEVER eligible.
  2. **Verified-freeze snapshot** — before any teardown, the
     eligible set is snapshotted to an immutable archive record
     (JSONL under `local/volumes/archive/` + row-count + full-set
     attestation fold). The archive is ONLY accepted if
     `ChainHeadAttestation.verify` over the snapshotted set matches
     the computed fold — a snapshot that doesn't verify is refused
     (Class-B), nothing is removed.
  3. **Teardown then re-verify** — after a verified snapshot, the
     eligible rows are removed in ONE deterministic batch, and the
     LIVE chain attestation is recomputed: remaining-chain verify
     must still pass. Any verify failure is a Class-B incident and
     halts the compactor (fail-closed).
  4. **Runbook ledger row** — every compaction run appends a
     manifest (eligible count, snapshot path, fold value, removed
     count, logical stamps) to the Phase 20 `security.hardening_audit`
     vault — compaction is itself audited, chain-anchored.
  5. **Read-path cost optimization** — declared deterministic
     indexes for the hot queries (event lookups by
     `(source_system, event_id)` already PK; add
     `(processing_status)` partial index for pending scans; slot_lock
     `(platform, active)` for contention checks), plus
     keyset-paginated read helpers (no `OFFSET` scans) in the store
     layer. Index creation is idempotent and declared in schema
     migrations.
- **Consequences:** storage stays bounded without weakening a single
  tamper-evidence guarantee; the archive is itself verifiable; every
  compaction leaves an audit trail; read paths stop degrading as
  history grows.

### D-126 — Resilience envelope: breaker hygiene, bounded retries, deterministic backoff

- **Situation:** the Phase 19 breaker rows accumulate (82/82
  non-CLOSED residue — every live test leaves rows); retry/backoff
  behavior is per-engine ad hoc; there is no shared resilience
  envelope, so fault-tolerance guarantees can drift per subsystem.
- **Decision (PROPOSED):**
  1. **Breaker lifecycle closure (governance cleanup):** breaker rows
     whose associated incident is RESOLVED (or older than a
     declared logical horizon with no recurrence) are eligible for
     the D-125 compactor (snapshot + verified-freeze + teardown).
     The breaker probe (D-123) continues to report DEGRADED honestly
     on live residue until compaction runs — no masking.
  2. **Shared resilience primitives** (`local/canonical/resilience.py`):
     a deterministic `RetryPolicy` (max attempts, logical-backoff
     schedule `base * 2^(attempt-1)` on the logical clock, jitter
     FORBIDDEN, retry classes bound to the D-052 taxonomy: Class A
     retryable, B/C/E terminal, D quarantined) and a deterministic
     `BudgetedExecutor` wrapper that refuses dispatch when the
     caller's retry/failure budget is exhausted.
  3. **Connection/throttle hardening:** the psql transport gains a
     declared concurrency ceiling (semaphore, deterministic ordering)
     and bounded-queue semantics — under simulated upstream
     degradation, requests queue and then fail FAST with a
     deterministic Class-A verdict instead of exhausting connections.
     Chaos battery proves: N > ceiling contenders ⇒ exactly the
     ceiling in flight, the rest refused deterministically, zero
     hangs, ledger/state integrity intact.
- **Consequences:** one retry/backoff semantic across engines;
  breaker residue becomes governed; upstream degradation degrades
  deterministically instead of cascading.

### D-127 — Platform resource-budget envelopes (cost control, Phase 23 §13 mandate)

- **Situation:** D-063 guards AI spend only. Platform resources —
  local container CPU/memory shares, LLM token quotas per batch,
  API-call budgets per green/yellow path — have no owner-approved
  bounds, so "cost control" exists for exactly one resource class.
- **Decision (PROPOSED):**
  1. `local/canonical/budget_contracts.py`: a canonical
     `ResourceBudget` shape — named resource (`llm_tokens`,
     `llm_calls`, `api_calls`, `container_cpu_seconds`,
     `container_memory_mb`), numeric limit, window kind
     (`per_run` | `per_logical_day`), scope (`green`/`yellow` —
     RED paths never execute autonomously anyway per D-050).
  2. `local/canonical/budget_engine.py`: a deterministic
     `BudgetLedger` (append-only consumption rows on the logical
     timeline; no wall clock) with pre-dispatch enforcement
     EXACTLY mirroring D-063 semantics: ≥80% soft ⇒ `budget_warning`;
     100% hard ⇒ refusal BEFORE the consuming call (Class-B
     guardrail). D-063's AI meter writes through to this ledger
     (single consumption record for ALL resource classes).
  3. Declared defaults in config (dummy local values, D-045-safe);
     enforcement is always active (tested), never ledger-gated —
     the D-063 property.
- **Consequences:** every consumable resource class has the same
  guardrail semantics; overrun of any budget is structurally
  impossible without an owner-approved config change; AI spend and
  platform spend are visible in ONE ledger.

### D-128 — Phase 23 verification battery (chaos × compaction × quota)

- **Situation:** new failure modes (mid-compaction crash, archive
  forgery, quota exhaustion mid-batch, pool saturation) need
  battery-proven closure, not prose.
- **Decision (PROPOSED):** `local/tests/test_phase23_resilience.py`
  with offline + live-PG classes covering: compaction edge cases
  (empty eligible set, active rows present, snapshot verify
  failure ⇒ nothing removed, mid-teardown crash ⇒ fail-closed +
  audited), archive-forgery attempts (flipped byte in snapshot ⇒
  verify fails), breaker-hygiene compaction, retry-policy vectors
  (class mapping, backoff schedule, budget exhaustion),
  pool-saturation chaos (deterministic refusal, zero hangs), and
  quota-exhaustion (hard refusal before the consuming call; soft
  warning at 80%; cross-resource independence). Full regression +
  tier census reconcile exactly; two consecutive green runs for the
  zero-flake claim.

## 2. Architecture

```
D-125 compactor (deterministic worker)
  eligible-set query (state-based) ──> snapshot JSONL ──> attestation fold verify
        │ verified                                          │ mismatch ⇒ Class-B, halt
        ▼                                                   ▼
  one-batch teardown ──> re-verify live chain ──> hardening_audit manifest row
  (+ declared indexes / keyset reads in the store layer)

D-126 resilience.py
  engines ──> RetryPolicy(D-052 class map, logical backoff) ──> BudgetedExecutor
  psql transport ──> concurrency ceiling (semaphore) ──> queue ──> fast-fail

D-127 budget_engine.py
  any consuming call ──> BudgetLedger.consume ──> <80% ok / ≥80% warn / 100% refuse
  D-063 AI meter ──write-through──▶ single consumption ledger
```

## 3. Milestones (implementation gated on D-125..D-128 approval)

- **M1 (Compaction & retention):** `local/canonical/compaction.py`
  (eligible-set queries, verified-freeze snapshot, teardown +
  re-verify, manifest rows) + `local/db/schema.sql` index block +
  keyset read helpers. Live-PG E2E on the real 20.5k-row store.
- **M2 (Resilience envelope):** `local/canonical/resilience.py`
  (RetryPolicy, BudgetedExecutor) + psql-transport concurrency
  ceiling + breaker-hygiene compaction integration.
- **M3 (Budget engine):** `local/canonical/budget_contracts.py` +
  `budget_engine.py` + D-063 write-through + declared defaults.
- **M4 (Battery & closure):** `test_phase23_resilience.py`,
  full battery ×2 green, tier census, AST/entropy/bounds sweeps,
  docs (verification record, MASTER_PLAN, TODO, DECISIONS notes),
  commit + push.

## 4. Verification gates (same as every phase)

- Zero-skip battery; two consecutive green runs; census reconciles
  exactly; extended AST sweep + secret-entropy scan + bounds
  re-audit CLEAN; `git diff --check` PASS; stack 5/5 healthy;
  live-layer tests run (not skipped) while Colima/Docker is up.

## 5. Open items for the owner

1. **Approve / amend D-125..D-128** (registered as Proposed).
2. Compaction cadence preference: per-battery-run automatic vs
   operator-triggered via the Phase 19 control plane
   (`COMPACT_RETIREABLE` as a new admin command is the natural
   home — owner call).
3. Default budget numbers for D-127 (declared dummies now; real
   limits are owner config).

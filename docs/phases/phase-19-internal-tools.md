# Phase 19 — Internal Tools, Operator Console & Admin Control Plane (D-109–D-112)

- Status: **implemented (M1–M4), owner-approved decisions**
- Discipline: local-first (D-053), design-first, zero-skip testing;
  local-token RBAC only (D-045) — no auth providers, no network, no
  UI framework coupling; zero wall-clock (D-093/D-101/D-105/D-106
  precedent); immutable D-027 audit + hash-chained operator ledger
  (Phase 18 tamper standard).

## 1. Objective

Give operators a governed control plane: every intervention — queue
pause/resume, DLQ retry, insight supersede, slot override, replay —
becomes a validated, permission-checked, durably-audited action
with deterministic recovery semantics, replacing invisible manual
mutations of volumes and scripts.

## 2. Decision table

| Decision | Content | Module |
|---|---|---|
| D-109 | `OperatorAction`/`SystemDiagnosticReport`/`AuditQueryFilter`/`QueueControlCommand`; closed 6-command grammar; local-token RBAC | `admin_contracts.py` |
| D-110 | `ControlPlaneEngine`: `admin.operator_actions` PK-as-lock + `admin.control_audit` chain; injected-read state facade; replay dry-run-by-default with single-use confirmation key | `admin_engine.py` |
| D-111 | `QueueInterventionWorker`: safe DLQ retries, pause/resume states, manual+automatic circuit breakers with logical-clock cool-downs | `admin_worker.py` |
| D-112 | Hash-chained operator audit ledger, `verify_chain` tamper detection, zero UI coupling | `admin_engine.py` |

## 3. Architecture flow

```
operator (actor:operator:* / actor:admin:*)
        │  OperatorAction {command, target, reason}
        ▼
RBAC check (deterministic local tokens)  ── Class-B on failure
        ▼
ControlPlaneEngine.execute
        │  admin.operator_actions  (PK-as-lock: one application)
        │  admin.control_audit     (hash-chained, append-only)
        ▼
injected command handlers per command kind
    PAUSE_QUEUE / RESUME_QUEUE   → queue control states
    RETRY_DLQ_ITEM               → DLQ re-submission (worker)
    FORCE_SUPERSEDE_INSIGHT      → insight supersede command
    MANUAL_SLOT_OVERRIDE         → slot override command
    REPLAY_EVENTS                → dry-run report UNLESS
                                   single-use confirmation key
        ▼
SystemDiagnosticReport (aggregated durable state via injected reads:
    notifications DLQ · HITL tickets · HITL insights · assets)
CircuitBreaker: manual trip | threshold trip (injected detector)
    → OPEN with deterministic logical-clock cool-down → HALF_OPEN → CLOSED
```

## 4. Security boundaries

- Local-token RBAC only (`actor:operator:*`, `actor:admin:*`,
  `actor:system:*`) — deterministic permission validation, no auth
  backend, no network (D-045/D-109).
- Zero cross-module imports: the state facade consumes injected read
  callables; interventions emit D-027 events via injected dispatch
  (AST-verified).
- Replay safety (D-110): dry-run/read-only unless a single-use
  confirmation key is supplied; the key burns on use and its burn is
  audited.
- Zero wall-clock: circuit-breaker cool-downs and report stamps use
  injected logical clock values only.
- `admin.control_audit` hash chain — `verify_chain` detects any
  mutation of operator history (D-112, Phase 18 standard).

## 5. Milestones

| Milestone | Content | Status |
|---|---|---|
| M1 | Contracts: action schemas, command grammar, RBAC, diagnostic models | done |
| M2 | Engine: action ledger, audit chain, state facade, replay safety, schema | done |
| M3 | Worker: DLQ retry bridge, queue control, circuit breakers, diagnostic sweeps | done |
| M4 | Suite incl. live-PG multi-operator races, AST audit, regression, docs | done |

## 6. Verification record (M4 closeout, 2026-09-17)

- Suite `local/tests/test_phase19_admin.py`: **24/24 OK, zero
  skipped** (20 offline across M1–M3 + 4 live-PG E2E on real
  `PgEventStore` + real PG `admin.operator_actions`/
  `control_audit`/`circuit_breakers`: execute→apply with on-PG
  chain verification, **8-thread identical-action race (exactly one
  APPLIED, seven DUPLICATE)**, single-use replay-key burn on live
  PG, queue-control/breaker restart parity).
- Full battery **669/669 OK, zero skips**; ladder 46/46 OK;
  containers 5/5 healthy (live layer ran, not skipped).
- AST audit **CLEAN** — 0 network imports, 0 AI SDKs, 0 UI/frontend
  framework couplings (flask/django/fastapi scanned), 0
  cross-domain module imports (every domain read is an injected
  callable — the D-110 boundary is import-verified), 0
  `time`/`datetime`, 0 `os.environ`; local-token RBAC only
  (D-045). Secret scan CLEAN; `git diff --check` PASS.
- Durable state after the run: 14 APPLIED / 8 RECEIVED (race
  losers) action rows, 4 burned replay keys, breaker rows in OPEN
  and CLOSED — full operator trail on live PG.

### Defects exposed and fixed in-batch

1. **Engine (report integrity):** a failed injected reader wrote a
   `None` cell into the report's `domains` map, violating the
   validated domain contract; failed readers now contribute ONLY
   to `reader_errors` (error isolation kept, domain set clean).
2. **Contracts (RBAC hole, test-exposed):** `actor_role` accepted
   tokens with a missing/empty id (`actor:admin`) — role and id are
   only meaningful together; the token parser now demands
   `actor:<role>:<non-empty id>`.
3. **Contracts (replay governance):** the REPLAY reason check was
   expressed with an ambiguous chained condition; rewritten as an
   explicit non-empty-string requirement (None and "" both
   rejected).
4. **Engine (replay semantics, diag-exposed):** the replay handler
   envelope did not carry the computed mode, so a handler could not
   distinguish DRY_RUN from APPLY — the envelope now carries
   `mode`.
5. **Engine (single-use scope, diag-exposed):** the replay key burn
   was per action id, so the SAME key re-submitted under a NEW
   action id would apply twice — burns are now recorded in the
   hash-chained audit (`replay_key_burned` rows) and enforced per
   KEY VALUE globally.
6. **Engine (crash):** `verify_chain` referenced an undefined name
   on its success path — caught by the diag before any commit.
7. **Test premises:** the live race/repaly tests registered no
   handlers (clean `no_handler` refusals, not applications) —
   handlers now registered per-engine; the replay-reason test
   relied on the fixture default reason instead of the None/"“
   cases.

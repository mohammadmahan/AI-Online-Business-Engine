# Phase 18 — HITL Approval Engine & Decision Ledger (D-105–D-108)

- Status: **implemented (M1–M4), owner-approved decisions**
- Discipline: local-first (D-053), design-first, zero-skip testing;
  mock local actors only (D-045) — no auth backends, no network;
  zero wall-clock (D-093/D-101/D-103 precedent); immutable D-027
  audit with tamper-evident decision ledger.

## 1. Objective

Give Phase 17's DISPATCHED_TO_HITL insights — and every other human
gate in the platform (publishing slots, order overrides, asset
flags) — a canonical, durable, attributable review path: claim →
decide → apply, exactly once, with a tamper-evident ledger of what
was proposed, who decided, why, and what ran as a result.

## 2. Decision table

| Decision | Content | Module |
|---|---|---|
| D-105 | Canonical `HitlReviewTicket`/`ReviewAction`/`Resolution`; lifecycle PENDING_REVIEW → CLAIMED → APPROVED / REJECTED / MODIFIED / ESCALATED / EXPIRED | `hitl_contracts.py` |
| D-106 | `HitlEngine`: PG PK-as-lock claims (`hitl.review_tickets`), append-only `hitl.review_ledger`, Phase 17 ingestion, injected logical-clock sweeps | `hitl_engine.py` |
| D-107 | `HitlDispatcher`: idempotent downstream commands via injected queue-type dispatchers — no cross-module imports | `hitl_dispatcher.py` |
| D-108 | Tamper-evident hash-chained ledger; verification of decision history; mock actors only | `hitl_engine.py` |

## 3. Architecture flow

```
Phase 17 DISPATCHED_TO_HITL insights / PUBLISH_GATE / ORDER_OVERRIDE /
ASSET_FLAG producers
        │  ingest (idempotent by payload_ref+queue_type)
        ▼
hitl.review_tickets (PENDING_REVIEW)
        │  claim()  ── PK-as-lock: exactly one CLAIMED winner
        ▼
CLAIMED (reviewer_actor_id bound)
        │  resolve(APPROVED | REJECTED | MODIFIED | ESCALATED)
        │      · MODIFIED carries the reviewer's changed payload
        │      · ESCALATED re-queues as fresh PENDING_REVIEW (elevated role)
        ▼
hitl.review_ledger (append-only, SHA-256 hash chain per ticket)
        │  dispatcher.apply (idempotent)
        ▼
injected command dispatchers keyed by queue_type:
    INSIGHT_REVIEW → analyst insight resolution (Phase 17 vault)
    PUBLISH_GATE   → slot unblock (Phase 15 contract command)
    ORDER_OVERRIDE → OMS compensation (Phase 12 contract command)
    ASSET_FLAG     → asset lifecycle (Phase 16 contract command)
sweep(logical_clock): stale PENDING_REVIEW/CLAIMED → EXPIRED (deterministic)
```

## 4. Security boundaries

- Mock local actors only (`role:owner`, `agent:analyst` — D-045);
  no auth backend, no network imports, no credentials.
- Zero wall-clock: expiry/escalation decided by an INJECTED logical
  clock evaluator over durable `created_at_logical` values.
- No imports of analyst/notification/publishing/OMS/assets modules;
  downstream effects are injected callables (AST-verified).
- Every ticket transition an immutable D-027 event; ledger rows are
  hash-chained — `verify_chain` detects tampering (D-108).

## 5. Milestones

| Milestone | Content | Status |
|---|---|---|
| M1 | Contracts: ticket schema, review state machine, roles, action validation | done |
| M2 | Engine: claim locks, ticket vault, ledger vault, sweeps, schema | done |
| M3 | Dispatcher: ingestion bridge, idempotent resolution application | done |
| M4 | Suite incl. live-PG multi-reviewer races, AST audit, regression, docs | done |

## 6. Verification record (M4 closeout, 2026-09-17)

- Suite `local/tests/test_phase18_hitl.py`: **22/22 OK, zero
  skipped** (18 offline across M1–M3 + 4 live-PG E2E on real
  `PgEventStore` + real PG `hitl.review_tickets`/`review_ledger`:
  claim→resolve→apply chain with hash-chain verification, **8-thread
  multi-reviewer claim race (exactly one winner)**, insight-ingestion
  idempotency, expiry sweep + restart parity).
- Full battery **645/645 OK, zero skips**; ladder 46/46 OK;
  containers 5/5 healthy (live layer ran, not skipped).
- AST audit **CLEAN** — 0 network imports, 0 AI SDKs, 0
  cross-domain module imports (analyst/notification/publishing/
  OMS/assets are all injected callables — the D-107 boundary is
  import-verified), 0 wall-clock (`time`/`datetime`) imports, 0
  `os.environ`; mock local actors only (D-045). Secret scan
  CLEAN; `git diff --check` PASS.
- Durable state after the run: live PG tickets in every lifecycle
  state (PENDING_REVIEW / CLAIMED / MODIFIED / EXPIRED), ledger
  chains verified.

### Defects exposed and fixed in-batch

1. **Engine (live-layer, transport):** the psql transport renders
   every parameter as a text constant, so a Python `None` bound to
   a nullable jsonb column arrived as the invalid token `None` —
   every live insert failed. Optional jsonb now emits a literal
   SQL NULL keyword chosen by control flow (never interpolated
   data). No precedent existed: earlier engines only insert
   NOT-NULL jsonb.
2. **Engine (determinism):** insight-ingestion ticket ids used
   builtin `hash()` — process-randomized across restarts, breaking
   idempotent re-ingest after a restart. Replaced with a SHA-256
   digest of the insight key (Phase 17 precedent).
3. **Engine (parity gap, diag-exposed):** `_JsonVault` lacked
   `max_ledger_seq` — caught by the offline diag before any commit.
4. **Test premise:** the ingestion diag assumed `candidates`
   counts all source rows; it correctly counts only HITL-ready
   rows (non-DISPATCHED_TO_HITL are filtered by the bridge).

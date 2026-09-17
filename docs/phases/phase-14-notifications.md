# Phase 14 — Notification System & User Alerts (D-089–D-092)

- Status: **implemented (M1–M4), owner-approved decisions**
- Discipline: local-first (D-053), design-first, zero-skip testing;
  no real email/SMS/webhook endpoints, no credentials (D-045), no
  wall-clock keys (D-085/D-086 precedent), event-sourced audit.

## 1. Objective

Deliver a notification layer that lets other domains (OMS
fulfillment, HITL queue movements, campaign fan-outs) request user
alerts through a single validated contract, delivered at-most-once
per channel with policy guards, retries with backoff, a DLQ that
materializes human review, and a fully reconstructible delivery
audit.

## 2. Decision table

| Decision | Content | Module |
|---|---|---|
| D-089 | Universal NotificationEvent (recipient, channel ∈ {IN_APP, EMAIL, SMS, WEBHOOK}, priority ∈ {LOW..CRITICAL}, template_id, payload variables, deduplication_key); versioned templates with declared required variables; strict LOCAL Class-B validation before queueing | `notification_contracts.py` |
| D-090 | NotificationVault — SHA-256 deduplication_key, PG PK-as-lock `notifications.delivery_lock`, deterministic `duplicate_blocked` for losers; pure-function quiet-hours + frequency caps from payload timestamps + durable ledger; INDEPENDENT per-channel fan-out | `notification_engine.py` |
| D-091 | Transactional outbox on the D-027 store; worker drains with exponential backoff for transient (Class-A), immediate DLQ for contract-invalid (Class-B), wait-honoring for rate-limit (Class-C); DLQ materializes HITL review (D-028/D-050) | `notification_worker.py` |
| D-092 | Every attempt/receipt/failure is a D-027 event with D-026 provenance; status lifecycle `PENDING → QUEUED → DISPATCHED → DELIVERED | FAILED | POLICY_DEFERRED | DUPLICATE_BLOCKED`; redaction on every persisted string; restart-reconstructible from durable data only | engine + worker |

## 3. Architecture flow

```
producer domain (OMS / HITL / fan-out)
        │  NotificationEvent (validated locally, D-089)
        ▼
NotificationEngine.enqueue ──► policy guards (quiet hours, cap, D-090)
        │                             │ policy_deferred (recorded)
        ▼                             ▼
  NotificationVault.claim (dedup, PK-as-lock)
        │ duplicate_blocked (recorded)
        ▼
outbox event on D-027 store (status=QUEUED)
        │
        ▼
NotificationWorker.drain ──► channel adapter (provider-neutral)
        │  Class-A retry w/ backoff · Class-B DLQ · Class-C wait
        ▼
attempt/receipt events + D-026 provenance (D-092)
        │ terminal FAILED ⇒ DLQ + HITL review record
        ▼
status view rebuilt from durable store data
```

## 4. Security boundaries

- Zero network in canonical modules: channel adapters are injected;
  the local adapter records outcomes, the live-shaped adapter is a
  drop-in behind the same interface (mock/live pattern, RULES §35).
- No credentials, no `os.environ` reads, no addresses harvested —
  recipients are opaque local references.
- Every persisted string passes `redact()` (token/secret patterns).
- The engine writes ONLY notification events/rows; no domain tables.

## 5. Milestones

| Milestone | Content | Status |
|---|---|---|
| M1 | Contracts: schema, priority matrix, template registry, local validation | done |
| M2 | Engine: vault, claim/lock, policy guards, enqueue, status view | done |
| M3 | Worker: outbox drain, backoff scheduler, DLQ, reconciliation scan | done |
| M4 | Suite incl. live-PG E2E, AST audit, full regression, docs | done |

## 6. Verification record (M4 closeout, 2026-09-17)

- Suite `local/tests/test_phase14_notifications.py`: **26/26 OK,
  zero skipped** (22 offline across M1–M3 + 4 live-PG E2E through
  the real `PgEventStore`, real PG `delivery_lock`, real PG
  `dead_letter`).
- Full battery **552/552 OK, zero skips**; ladder 46/46 OK;
  containers 5/5 healthy (live layer ran, not skipped).
- AST audit CLEAN: zero network imports in canonical modules, zero
  decision verbs, zero `os.environ` (the only hits were the
  test-only `_stack_up()` Docker guard and the docstring sentence
  stating the absence). Secret scan CLEAN; `git diff --check` PASS.

### Defects exposed by the suite and fixed in-batch

1. `_PgDLQ.items()` demanded ≥7 line segments for a 6-field row —
   every DLQ read returned empty while admits silently accumulated
   (rows were written, never visible). Fixed to the real 6-field
   shape; live DLQ rows verified visible.
2. Transient outcomes parked notifications at DISPATCHED and never
   advanced the durable attempt counter — the retry ladder stalled
   (pass 2 never re-dispatched, exhaustion never reached the DLQ).
   Fixed: transient/rate-limited receipts return the notification to
   QUEUED for its next attempt (the receipt IS the DISPATCHED
   transition record) and EVERY outcome advances the lock row's
   attempt_no (restart-safe ladder).
3. Terminal stickiness: a late transient receipt could demote a
   DELIVERED/FAILED notification in the status view, and
   `record_outcome` echoed the demotion. Fixed: terminal outcomes
   settle the vault verdict; late non-terminal receipts never demote
   (view or return value).
4. Template registry had no SMS-capable template (design gap):
   added `order.shipped.v1` (IN_APP/EMAIL/SMS).
5. Register row 30 was initially written by overwriting row 29's
   prefix (str_replace match error) — restored byte-identical from
   git HEAD and inserted row 30 properly; verified by diff.

### Owner gates (standing)

- No real EMAIL/SMS/WEBHOOK endpoints, no provider credentials
  (D-045) — none exist, none requested. Channel adapters are
  injected behind the provider-neutral interface; the local adapters
  record outcomes deterministically.
- Phase 14 passing does NOT prove live provider compatibility.
- No notification ever leaves the local stack.

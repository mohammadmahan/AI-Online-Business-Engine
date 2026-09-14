# n8n Idempotency, Retries, and Webhook Contract

- Authority: Phase 5 M1 / **D-059 Approved (Option A)**
- Traceability: **D-017 (identifier idempotency), D-027 (event
  idempotency)**, D-052 (failure classes), D-026 (provenance of
  handling decisions)

---

## 1. Webhook ingestion & the idempotency key (D-027)

**Key derivation rule (corrected):** the idempotency key must be
deterministic for the *logical event* — **a timestamp must never be an
ingredient**, otherwise every retry of the same delivery produces a
different key and dedupe silently fails (the exact failure D-027
exists to prevent).

```
idempotency_key = SHA256( source_system + event_id + event_type )
```

- `source_system + event_id` is the D-027 uniqueness pair; `event_type`
  is included so the same ID from different pipelines cannot collide.
- Webhook workflows must record the key into the append-only D-027
  event store (canonical `events` schema; executable JSON store until
  Docker-only state is retired) **before processing**.
- Verdicts mirror D-027 exactly:
  - new → process;
  - identical repeat → **HTTP 200/204, cached/static response, no
    action re-executed** (`skipped_duplicate`);
  - same key, different payload hash → **HTTP 409, integrity error,
    human review** — never silently reprocessed;
  - non-terminal previous attempt (timeout/unknown) → deterministic
    reconciliation per D-052 (marker lookup), not blind re-execution.

## 2. D-052 failure classes & n8n retry policy

| Class | Definition | Retry policy | Terminal route |
|---|---|---|---|
| **A — Transient/network** | timeout, 429, 502/503/504, connection reset | exponential backoff: 3 attempts (2s → 8s → 30s), then terminal | failure path + warning log |
| **B — Data invariant/schema** | missing mandatory keys, invalid vocabulary, price/sale rule violation, schema mismatch | **never retried** | Dead-letter → HITL verification queue (D-026 provenance) |
| **C — Authentication/secrets** | 401/403, expired token, missing credential reference | **never retried** | halt + infrastructure flag, high-priority alert |
| **D — Authority violation** | attempted RED execution without the human approval marker | **abort immediately** | quarantine workflow, critical alert, owner review |
| **E — Unknown/ambiguous** | partial success, malformed response, outcome unverifiable | deterministic reconciliation (marker lookup) — at most one re-execution | if still ambiguous → human review (never auto-adopt) |

Notes:
- Retries must reuse the **same idempotency key** — a retry is the same
  logical event, not a new one.
- "Unknown response" after a timeout is Class E: check for the
  deterministic marker (e.g. mapping-registry entry or event-store
  reference) before any re-create attempt (D-044 pattern).

## 3. Dead letter & fallback

- Terminal Class B/C/E failures must pipe the **full payload + error
  class + idempotency key** to the local failure path — the HITL
  verification queue — never silently dropped.
- Each dead-lettered item gets D-026 provenance (`source_type` per
  origin, actor = the workflow identity) so handling decisions remain
  attributable.
- The queue — not the workflow — is where correction decisions happen;
  workflows never "fix" business data on their own authority.

# Phase 10 — Telegram Platform Integration (Bot API Publishing)

- Date: 2026-09-16
- Authority: MASTER_PLAN §13 Phase 10 + **D-073 / D-074 / D-075 / D-076 (all owner-approved, 2026-09-16)**
- Strategy: **local-first** (D-053) — mock adapter only, zero network,
  zero credentials. Live Bot API connectivity is a separate owner-gated
  milestone (D-045).
- Discipline: design/contract-first, zero-skip tests, provider-neutral
  boundaries (RULES §35, the mock-Woo/mock-Notion/mock-Instagram
  pattern).

---

## 1. Objective

Give the platform a deterministic, idempotent, rate-aware Telegram
publishing path for owner channels and customer groups:

1. Content contract validated **locally** (formatting + payload
   constraints) before any dispatch.
2. Absolute double-post protection under retries, restarts, and
   concurrent dispatchers.
3. Telegram pacing respected (global 30 msgs/sec, per-chat 1 msg/sec,
   429 `retry_after` honored exactly).
4. Failures classified per D-052 and routed deterministically (retry /
   cooldown / DLQ / freeze + HITL).

## 2. Scope discipline

- No real Bot API connection, no bot token, no chat ids from any real
  account. Phase 10 passing does NOT prove live Telegram
  compatibility.
- Publishing never mutates canonical product/price data; the AI
  surface has no path into this module (no decision verbs, no AI
  imports).
- Media is referenced by id from the media abstraction (D-051/D-049);
  no media binaries flow through this phase.

## 3. Governance

| Decision | Content |
|---|---|
| **D-073** | Content & formatting contract: Text/Photo/Video/Document/MediaGroup schemas; MarkdownV2 + HTML strict escaping; local constraints (caption ≤ 1024, text ≤ 4096, album ≤ 10, file ≤ 50 MB). |
| **D-074** | Idempotency vault (SHA-256 over chat_id+content_id+media_hash+text_hash+scheduled_slot) + `telegram.publish_lock` PK-as-lock + token-bucket rate pacer (30/s global, 1/s per chat). |
| **D-075** | Owner-gated adapter: Mock with deterministic failure controls; Live behind `TELEGRAM_LIVE_ENABLED` + token; `bot<token>` redaction everywhere. |
| **D-076** | Transactional outbox on D-027 + D-052-aligned classifier: A backoff / B terminal DLQ / C `retry_after` cooldown / E freeze + HITL alert. |

## 4. Architecture

```
enqueue (contract check, local)          D-073
   → outbox row (D-027 store)            D-076
   → worker picks due item
       → vault acquire (PG PK lock)      D-074
       → pacer acquire (token bucket)    D-074
       → adapter.sendMessage/sendPhoto/
         sendVideo/sendDocument/
         sendMediaGroup                  D-075
       → outcome recorded durably:
            published | duplicate_publish_blocked |
            retry_scheduled (A) | cooldown (C) |
            dead_lettered (B) | queue_frozen (E)
```

## 5. Modules

- `local/canonical/telegram_contracts.py` — payload schemas, escaping,
  constraint validators, state machine (pure, zero I/O).
- `local/canonical/telegram_adapter.py` — `TelegramAdapter` interface,
  `MockTelegramAdapter` (deterministic failure controls),
  `LiveTelegramAdapter` (injectable transport, construction gate),
  `RatePacer` (token bucket), `redact()`.
- `local/canonical/telegram_publisher.py` — idempotency vault on
  `telegram.publish_lock`, outbox enqueue/pending/worker, classifier,
  backoff/cooldown/freeze, DLQ, D-026 provenance links.
- `local/db/schema.sql` — `telegram.publish_lock` (live-migrated).

## 6. Error classification (D-076 / D-052)

| Class | Trigger | Handling |
|---|---|---|
| A | network timeout, 5xx | exponential backoff, durable retry_count |
| B | invalid parse mode, malformed payload, local contract violation | terminal reject → DLQ, no retry |
| C | 429 with `retry_after` | dynamic pause honoring Telegram's exact value → requeue |
| E | bot blocked/kicked (403), token revoked, chat not found | queue freeze + HITL alert + provenance |

## 7. Milestones

- **M1 — Contracts & parsing rules (D-073):** schemas, MarkdownV2/HTML
  escape validators, constraint checkers; tests.
- **M2 — Bot API adapters & rate pacer (D-075/D-074):** mock + live
  adapters, pacer (global + per-chat buckets), redaction; tests.
- **M3 — Vault & outbox worker (D-074/D-076):** atomic PG locking,
  classifier, retry worker, DLQ; tests incl. concurrency.
- **M4 — E2E & verification:** live-PG integration suite, AST security
  audit, full regression battery, docs.

## 8. Security & boundaries

- No credential exists; none is requested (D-045). Live sending cannot
  occur without owner action (`TELEGRAM_LIVE_ENABLED` + token).
- `redact()` strips `bot<token>` URL forms, bare tokens, and
  Authorization headers from every error, log line, and DLQ entry.
- AST audit gates: no network imports in shipped modules; the only
  `os.environ` access is the D-075 construction gate.

## 9. Verification record (M4 closure, 2026-09-16)

- **Phase 10 suite:** 51/51 OK — contracts/escaping/constraints
  (M1), adapters + gate + redaction + pacer (M2), vault/outbox/
  classifier/DLQ incl. 10-thread concurrency + audit reconstruction
  (M3), live-PG E2E (M4).
- **Live E2E proven:** full publish on the live D-055 store;
  duplicate re-publish (fresh publisher = simulated restart) →
  `duplicate_publish_blocked`; distinct scheduled_slot → distinct
  key → publishes; audit reconstruction from durable store data only.
- **Defects found by the suite and fixed in-batch:**
  1. Concurrent dispatchers collided on one attempt event id →
     blocked dispatches now record under a unique
     `telegram|blocked|…|time_ns()` id (D-027 identity), while the
     winner records the canonical attempt event.
  2. A terminal (PUBLISHED/FAILED) key could re-dispatch after a
     restart (the vault alone covers only PUBLISHED) → hard durable
     terminal guard now precedes dispatch, keyed on transition
     events.
  3. Pacer slots were consumed by vault losers → reservation now
     happens only after a successful claim.
- **AST security audit: CLEAN** — zero banned imports (no network
  surface in shipped modules), zero Woo/price/publication references,
  zero decision verbs; `os.environ` access only inside the D-075
  live-adapter gate; every error/DLQ/provenance string passes through
  `redact()` (bot-token patterns) before persistence.
- **Deferred (owner-gated, D-045):** live Telegram Bot API
  connectivity, real bot token, real chat ids. Phase 10 passing does
  NOT prove live Telegram compatibility.

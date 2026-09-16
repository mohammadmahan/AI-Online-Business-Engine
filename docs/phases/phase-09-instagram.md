# Phase 9 — Instagram Integration (Publishing Pipeline)

- Date: 2026-09-16
- Authority: MASTER_PLAN §13 Phase 9 + **D-069 / D-070 / D-071 / D-072 (all Approved, 2026-09-16)**
- Discipline: local-first (D-053), zero-skip tests, deterministic event handling (D-027), D-052 error classes, D-045 credential redaction.
- Milestone plan: **M1–M4 executed in ONE coherent batch** per the owner instruction.

---

## 1. Objective

Implement the Instagram publishing pipeline end-to-end WITHOUT any
live Meta connection: the publishing contract and state machine
(D-069), absolute double-publish protection (D-070), the owner-gated
adapter boundary (D-071), and the crash-safe outbox with DLQ (D-072) —
all proven by tests against deterministic mocks and the live
PostgreSQL store.

## 2. Components

| Component | Module | Decision |
|---|---|---|
| Media/publish contract + state machine + local validators | `local/canonical/instagram_contracts.py` | D-069 |
| Idempotency vault, outbox worker, error classifier, DLQ | `local/canonical/instagram_publisher.py` | D-070 / D-072 |
| Mock + live Graph API adapters, container poller | `local/canonical/instagram_adapter.py` | D-071 |
| Full test suite incl. live-PG E2E | `local/tests/test_phase9_instagram.py` | — |

## 3. D-069 — Publishing state machine & local validation

States: `PENDING → MEDIA_CREATE → CONTAINER_STATUS → MEDIA_PUBLISH →
PUBLISHED`; `FAILED` is reachable from any non-terminal state;
`PUBLISHED` and `FAILED` are terminal and immutable (state
reconstruction is possible from D-027 events alone).

Two-step async workflow (Meta Graph API):
1. `MEDIA_CREATE` — create a media container (image/video + caption).
2. `CONTAINER_STATUS` — poll `status_code` until `FINISHED` (ready) or
   `ERROR`/`EXPIRED`; bounded polls, deterministic backoff.
3. `MEDIA_PUBLISH` — publish the finished container id.

Local validators run BEFORE any network dispatch:
- `aspect_ratio` ∈ {(1,1), (4,5), (16,9)} (exact integer ratios);
- caption length ≤ 2200 chars; hashtags ≤ 30 (each starting with `#`);
- `media_ref` required (D-051: media lives in the media abstraction;
  Instagram references it, never owns it);
- `content_id` required and caller-supplied (the model/AI never
  invents it, RULES §3).

Class-B local prevention: an invalid payload is rejected without a
single network call.

## 4. D-070 — Idempotency vault & double-publish guard

- `publish_idempotency_key = sha256(content_id, media_hash,
  caption_hash, scheduled_slot)` — deterministic, recomputable after
  crashes/restarts.
- The vault is the canonical PostgreSQL store (D-055): an exclusive
  lock row per key is inserted transactionally BEFORE any network
  call; a second acquisition of the same key returns the terminal
  `duplicate_publish_blocked` verdict with the original attempt's
  reference — under network retry AND concurrent dispatchers.
- `scheduled_slot` is caller-supplied (e.g. a calendar slot id), so a
  deliberate future re-publication gets a new key while all retries of
  one attempt share theirs.
- JSON-store parity for offline tests; live-PG proof in M4.

## 5. D-071 — Adapter boundary & token redaction

- `InstagramAdapter` interface: `create_media_container`,
  `container_status`, `publish_container` — pluggable transport,
  identical to the D-066 pattern.
- `MockInstagramAdapter`: deterministic container lifecycle
  (`IN_PROGRESS → FINISHED`), scriptable failure injection (timeout,
  error status, rate limit, publish failure).
- `GraphApiAdapter`: live, gated behind `INSTAGRAM_LIVE_ENABLED=true`
  AND `INSTAGRAM_ACCESS_TOKEN`/`INSTAGRAM_BUSINESS_ID`; otherwise
  deterministic Class-B refusal. The default transport raises (owner-
  gated production wiring), tests inject fakes.
- Token redaction: every error/observability path passes through a
  redaction helper that replaces token material before anything is
  logged or persisted (D-045).

## 6. D-072 — Outbox, classifier, DLQ

- Outbox: queued posts are durable D-027 events (`instagram|publish|…`)
  in the canonical store BEFORE dispatch; the worker claims an item,
  advances the state machine, and records each transition.
- Classifier (D-052-aligned):
  - **Class-A** transient network → exponential backoff, bounded
    retries;
  - **Class-B** schema/media invalid → terminal reject, NO retry;
  - **Class-C** rate limit/429 → cooldown queue (re-eligible only
    after the cooldown);
  - **Class-E** token expired → freeze the whole queue + alert record
    (never loop, never drop).
- DLQ: unrecoverable failures land in the dead-letter queue with a
  full audit record (error class, attempt history, D-026 provenance)
  — nothing vanishes silently.

## 7. Milestones

- **M1 — Contracts & pre-publish validation (D-069):** state machine,
  validators, local Class-B prevention; tests.
- **M2 — Adapters & polling (D-071):** mock/live adapters, bounded
  container-status poller, timeout handling, redaction; tests.
- **M3 — Vault & outbox publisher (D-070/D-072):** key derivation,
  exclusive locking, worker, classifier, backoff/cooldown/freeze, DLQ;
  tests incl. concurrency + retry dedup.
- **M4 — E2E & verification:** full pipeline on the live PostgreSQL
  store; AST security audit; documentation updates.

## 8. Security & boundaries

- No credential exists; none is requested (D-045). Live publishing
  cannot occur without owner action.
- The pipeline references media by id from the media abstraction
  (D-051/D-049) — no media binaries flow through this phase.
- Publishing never mutates canonical product/price data; the AI
  surface has no path into this module (no decision verbs, no AI
  imports).

## 9. Verification record (M4 closure, 2026-09-16)

- **Phase 9 suite:** 24/24 OK — contracts/validators (M1), adapters +
  poller + redaction (M2), vault/outbox/classifier/DLQ incl.
  concurrency and retry dedup (M3), live-PG E2E (M4).
- **Live E2E proven:** full publish on the live D-055 store;
  duplicate re-publish (fresh publisher = simulated restart) →
  `duplicate_publish_blocked`; distinct scheduled_slot → distinct
  key → publishes; audit reconstruction from durable store data only
  (D-027 `succeeded_references`, insertion order via `ingest_seq`).
- **Cross-batch audit fix (store):** `PgEventStore` pinned its
  constructor `source_system` and silently re-keyed every operation —
  the method-level argument was ignored, so per-source isolation
  broke (publisher rows landed under `notion`; conflict-detection and
  audit scoping were wrong). Fixed by threading the method-level
  `source_system` through `receive/begin/succeed/fail/
  mark_skipped_duplicate/_get/_guarded_update`; the constructor value
  is now only a fallback. Phase 6/7 consumers re-verified: 122/122 OK.
- **AST security audit: CLEAN** — zero banned imports (no network
  surface), zero Woo/price/publication references, zero decision
  verbs; `os.environ` access only inside the D-071 live-adapter gate.
- **Deferred (owner-gated, D-045):** live Instagram Graph API
  connectivity, real access tokens, real media. Phase 9 passing does
  NOT prove live Meta API compatibility.

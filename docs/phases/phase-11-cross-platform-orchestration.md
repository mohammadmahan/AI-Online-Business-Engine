# Phase 11 — Cross-Platform Orchestration & Publication Fan-Out

- Status: **Complete (architecture + local execution, owner-approved D-077–D-080)**
- Date: 2026-09-16
- Authority: MASTER_PLAN §13 Phase 11; governance per D-026/D-027/D-045/
  D-050/D-052 and the platform contracts D-069..D-076.
- Scope discipline: strictly local (D-053). No real Instagram/Meta or
  Telegram traffic is introduced by this phase — Phase 11 orchestrates
  the **local** Phase 9/10 publisher modules behind their existing
  owner-gated adapters. No new credentials exist and none are requested.

---

## 1. Objective

Dispatch one piece of campaign content to an arbitrary set of
destinations (Instagram, Telegram, …) with:

- one universal content representation (no platform jargon in the core),
- per-target adaptation through the existing platform contracts,
- independent per-platform execution (no cross-platform rollback),
- a deterministic aggregate lifecycle with a first-class
  partial-success outcome,
- campaign-level anti-race protection + platform-level idempotency,
- surgical retry, human cancellation, and crash reconciliation.

## 2. Decision table

| Decision | Content | Module |
|---|---|---|
| D-077 | Universal `fanout_dispatch` payload + destination matrix + local target transforms | `orchestration_contracts.py` |
| D-078 | `FanOutLifecycle` aggregate state machine, deterministic aggregation, receipts/provenance | `orchestration_engine.py` |
| D-079 | Coordinated release windows + `orchestration.fanout_lock` anti-race lock (PG PK-as-lock) | `orchestration_engine.py` |
| D-080 | Retry isolation, HITL cancellation, reconciliation worker | `orchestration_worker.py` |

## 3. Architecture

```
fanout_dispatch payload (universal)
        │  local validation (Class-B before any dispatch)
        ▼
FanOutOrchestrator.enqueue ──► D-027 outbox event  fanout|<job_id>
        │                     (orchestration row survives crashes)
        ▼
dispatch(job) — claims orchestration.fanout_lock (D-079, PG)
        │  per-target gate: release window (simultaneous/staggered)
        ▼
DESTINATION MATRIX (D-077) — per target:
   transform (universal → platform payload, local)
   validate  (D-069 / D-073 local rules)
   publish   (Phase 9 InstagramOutboxPublisher / Phase 10
              TelegramOutboxPublisher — their own vaults/outboxes)
        │
        ├─ per-target sub-task event: fanout|<job>|<target> (D-027)
        ▼
aggregate(job) — strictly derived from durable sub-task terminal
states → SUCCESS | PARTIAL_SUCCESS | FAILED (D-078)
```

### 3.1 Universal payload (D-077)

```
{
  "job_id": "<uuid or deterministic id>",
  "campaign_id": "...",
  "content_id": "...",
  "media": {"kind": "photo|video|document|none",
             "bytes_hash": "sha256...", "aspect_ratio": "1:1|4:5|16:9"},
  "text": "...",
  "hashtags": ["..."],              # planned, platform-adjusted
  "scheduled_slot": "2026-09-16T12:00:00+00:00",
  "release_at": "...", "stagger_s": {"telegram": 0, "instagram": 0},
  "targets": ["telegram", "instagram"]
}
```

Target transforms (local, pure): Instagram keeps D-069 validators
(aspect ratio ∈ {1:1, 4:5, 16:9}, caption ≤ 2200, hashtags ≤ 30 —
hashtag overage truncated locally with provenance); Telegram keeps
D-073 (MarkdownV2/HTML escaping, caption ≤ 1024 / text ≤ 4096,
album ≤ 10, file ≤ 50 MB). A target that cannot be represented fails
**before dispatch** and never touches siblings.

### 3.2 Aggregate state machine (D-078)

```
PENDING → ROUTED → DISPATCHING → SUCCESS | PARTIAL_SUCCESS | FAILED
                ↘ CANCELLED (HITL, unstarted targets only — D-080)
```

Deterministic aggregation from sub-task terminal states only:
- all targets PUBLISHED → `SUCCESS`
- ≥1 PUBLISHED and ≥1 FAILED/REJECTED/CANCELLED → `PARTIAL_SUCCESS`
- none PUBLISHED and no target still dispatchable → `FAILED`

Sub-task states come exclusively from the durable per-target events
(`fanout|<job>|<target>`); platform-internal states (container
polling, cooldowns) remain inside Phase 9/10 modules.

### 3.3 Anti-race + schedule (D-079)

`orchestration.fanout_lock` (schema `orchestration`, PK-as-lock on
`job_id`) guarantees exactly one dispatcher claim per job across
workers/restarts. `release_at` + per-target `stagger_s` gate each
target's dispatch deterministically. Platform vaults (D-070/D-074)
remain the final per-platform idempotency layer — two independent
guards, two levels.

### 3.4 Resiliency (D-080)

- `retry(job_id, targets)`: re-dispatches **only** non-published,
  retryable targets; a PUBLISHED target's receipt is its skip proof.
- `cancel(job_id, targets)`: HITL-only (actor in provenance),
  unstarted targets → CANCELLED; started/published targets refuse.
- `reconcile()`: boot/recovery scanner re-derives each in-flight
  job's aggregate state from durable sub-task records only — no
  in-process memory is authoritative.

## 4. Error model

Classification stays inside the platform publishers (D-052 aligned).
The orchestrator consumes **outcomes** (published / failed / blocked /
cooldown / frozen) and never re-implements retry semantics: a
platform retry is "ask that platform's publisher again"; the
platform's own Class-A/C machinery applies. Class-E platform freezes
surface as a blocked target and hold the aggregate in DISPATCHING
until resolved or cancelled.

## 5. Milestones

| Milestone | Content | Status |
|---|---|---|
| M1 | Universal schema, destination matrix, transforms | done |
| M2 | Orchestrator, aggregate machine, fan-out lock, schema | done |
| M3 | Reconciliation worker, retry isolation, cancellation | done |
| M4 | Live-PG E2E suite, AST audit, full regression | done |

## 6. Security boundaries

- No network imports; adapters remain the only vendor-facing surface.
- `os.environ` appears nowhere in Phase 11 modules (gates already
  live in the D-071/D-075 adapters).
- No Woo/price/publication imports; no decision verbs on engine
  surfaces; cancellation is the single HITL action and is provenance-
  recorded.
- All persisted payloads pass platform redaction (`redact()` of the
  target platform) before durable writes.

## 7. Verification record (2026-09-16)

- M1–M4 complete; suite `local/tests/test_phase11_orchestration.py`:
  **50/50 OK** (offline + live-PG E2E through the REAL Phase 9/10
  publishers and vaults).
- Full battery: **461/461 OK, zero skips**; ladder 46/46 OK.
- AST audit on the three Phase 11 modules + test suite: **CLEAN** —
  no network imports, no Woo/price/publication references, no
  decision verbs, `os.environ` access = 0.
- Secret scan CLEAN; `git diff --check` PASS; stack 5/5 healthy.

Defects found and fixed during M4 (all caught by the suite):

1. **Lifecycle event reconstruction** — stage names were recorded
   lowercase while the rank table used aggregate-state vocabulary;
   `_job_ref` never matched, so restart reconstruction returned
   None/DISPATCHING. Ranks now use the lowercase lifecycle-stage
   vocabulary with `aggregate|N` prefix tolerance.
2. **Aggregate event collision** — all aggregate observations shared
   one deterministic event id, so a second (changed) observation hit
   D-027's conflicting-duplicate path. Aggregates are now sequenced
   per job (`aggregate|N`, N derived from durable aggregate events —
   restart-safe, not wall-clock).
3. **Lost no-publisher receipts** — the `no_publisher_bound` path
   `continue`d before persisting the per-target receipt. Receipts are
   now written for EVERY outcome path.
4. **Cancel semantics** — terminally REJECTED targets were treated
   as untouchable. Only PUBLISHED/duplicate-blocked targets are
   served-immutably; rejection is not publication, so rejected and
   unstarted targets are cancellable (D-080).

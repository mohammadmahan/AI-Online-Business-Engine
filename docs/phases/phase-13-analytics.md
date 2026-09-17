# Phase 13 — Analytics, Reporting & Metrics Engine

- Date: 2026-09-16
- Authority: MASTER_PLAN §13 Phase 13 + **D-085..D-088 (all Approved)**
- Scope discipline: local-first (D-053); read-side projections only —
  analytics never writes back to domain tables; no credentials, no
  customer-identifying data in any export (D-045/D-088).

## 1. Objective

Give the platform a CQRS read model over the D-027 event store:
publication engagement (Phases 9–11), order outcomes and revenue
(Phase 12), and their correlation, aggregated into deterministic
windows, materialized as incremental snapshots, and exported as
reproducible JSON/CSV reports with an audit vault.

## 2. Decision table

| Decision | Content | Module |
|---|---|---|
| D-085 | Canonical metric events + rollups; CQRS boundary (projection never writes to domain tables); hourly/daily/monthly windows from each event's own `occurred_at` — zero wall-clock | `analytics_contracts.py` |
| D-086 | Incremental projection via the monotonic `ingest_seq` cursor; exactly-once per event; atomic cursor+snapshot advance; rebuild = replay from 0 | `analytics_engine.py` |
| D-087 | Campaign→revenue correlator joined on shared `campaign_id` (publication events) and `source_campaign_id` (order events) — zero domain imports, configurable attribution window, unattributed rows preserved | `analytics_worker.py` |
| D-088 | Idempotent JSON/CSV export keyed by SHA-256 `window_hash` (kind + window + cursor); report audit vault (actor, kind, window, hash, row count) | `analytics_worker.py` |

## 3. Architecture flow

```
D-027 store (succeeded events, ordered by ingest_seq)
  → ProjectionEngine.incremental_pass()
      cursor (analytics.cursor)  →  new events with ingest_seq > cursor
      each event → typed metric record (D-085 validator)
      windowed aggregation (hour/day/month from occurred_at)
      snapshot write + cursor advance (atomic, D-086)
  → Snapshots:
      analytics.metric_rollup   (kind × window × bucket)
      analytics.campaign_attribution (D-087 join)
  → Correlator: publications ∋ campaign_id  ⟕  orders ∋ source_campaign_id
  → Exporter: window_hash → JSON/CSV + report audit vault (D-088)
```

## 4. Metric taxonomy (D-085)

| Metric kind | Source events (source_system) | Value |
|---|---|---|
| `publication_published` | instagram / telegram (outcome published, duplicate_publish_blocked) | count |
| `publication_failed` | instagram / telegram (terminal_reject, retries_exhausted, …) | count |
| `order_placed` | oms (order events) | count |
| `order_completed` / `order_cancelled` | oms (transitions) | count |
| `revenue_minor` | oms (COMPLETED transitions carry order total) | sum (integer minor units) |

Windows: `hourly` (YYYY-MM-DDTHH), `daily` (YYYY-MM-DD), `monthly`
(YYYY-MM) — all parsed from the event payload's own `occurred_at`
field (recorded by the producing domain); none from wall-clock.

## 5. Milestones

| Milestone | Content | Status |
|---|---|---|
| M1 | Metric schemas, windowing, rollup math, event→metric classification | done |
| M2 | Projection engine, ingest_seq cursor, snapshots (PG + JSON parity) | done |
| M3 | Correlator (D-087), exporter + audit vault (D-088) | done |
| M4 | Live-PG E2E suite, AST audit, full regression | done |

## 6. Security boundaries

- The projection consumes succeeded events and writes ONLY to the
  `analytics` schema / parity files — zero writes to domain tables.
- No platform adapters, no network imports; `os.environ` access = 0.
- Exports are aggregates only: no customer refs, no credentials, no
  tokens; every string passes through before persisting (D-088).
- Deterministic outputs: same events + same window ⇒ byte-identical
  report (verified by suite).

## 7. Verification record (M4 closeout, 2026-09-17)

- Suite: `local/tests/test_phase13_analytics.py` — **28/28 OK, zero
  skipped** (24 offline + 4 live-PG E2E through real `PgEventStore` →
  `_PgCursorStore` → `PgReportVault` on the live stack).
- Full battery: **526/526 OK, zero skips** (`unittest discover
  local/tests`); ladder 46/46 OK. Containers 5/5 healthy.
- AST audit: CLEAN — zero network imports, zero platform/price/
  publication module refs (the string `publication_*` is the D-085
  metric vocabulary the read-model consumes by design), zero decision
  verbs, zero `os.environ` in canonical modules; the only `subprocess`
  is the test-only `_stack_up()` Docker guard (Phase 9/10 pattern).
- Secret scan CLEAN; `git diff --check` PASS.

### Defects exposed by the suite and fixed in-batch

1. `_PgCursorStore.advance()` wrote the WHOLE three-grain finalized
   dict into every per-grain snapshot row ⇒ `rollups()` returned
   double-nested state and every live incremental pass silently wiped
   prior rollups (offline JSON store unaffected — the bug was live-only).
   Fixed: each `analytics.snapshot` row stores its own grain's state
   (`jsonb_each` split); stale garbage rows cleared; full live rebuild
   folds the real 7 256-event history correctly.
2. `analytics.metric_rollup` (D-085 CQRS query table) was a write
   orphan — defined in schema, deleted by reset, written by nobody.
   Fixed: the atomic cursor-advance statement now also upserts its
   cells derived from the committed snapshot (cursor + snapshots +
   rollup cells move together, single statement).
3. `merge_rollups` double-finalized (crashed on empty kinds) and
   dropped `last_seq`; now returns a raw composable accumulator —
   `finalize_rollup` stays the single serialization edge.
4. `PgReportVault` missing `import sys` (NameError on first use).
5. Two live tests had invalid premises for a SHARED append-only store
   (stale snapshot vs fresh full replay; absolute bucket revenue).
   Rewritten to sound invariants: rebuild↔rebuild byte-determinism,
   and per-run revenue DELTA ≥ the run's own emitted total.

Owner-gated as before (D-045): no analytics data leaves the local
stack; exports are local files/tables only.

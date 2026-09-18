# Phase 22 — Observability & Health Telemetry (D-121–D-124)

- Status: **in progress (M1–M4)**
- Discipline: local-first (D-053), design-first, zero-skip testing;
  strictly localhost/air-gapped (D-045) — no remote collectors, no
  external APM agents, no wall-clock keys (D-085/D-086/D-093
  precedent), event-sourced and deterministic throughout.

## 1. Objective

Make the platform's operational state OBSERVABLE without making it
EXPOSED: structured event logging across all core subsystems,
deterministic operational metrics with a localhost-only Prometheus
exposition, and composable health probes that render a machine-readable
attestation — all local, deterministic, zero-leak, and battery-proven.

## 2. Decision table

| Decision | Content |
|---|---|
| D-121 | Local structured event log ledger (`engine.log.v1`): append-only JSONL + durable D-027-backed vault; deterministic trace/causal-chain ids; D-114 sanitization at the log boundary |
| D-122 | Deterministic metrics registry (counters/gauges/histograms, fixed logical buckets) + zero-dependency Prometheus text exporter bound to 127.0.0.1; declared bounded cardinality |
| D-123 | Composable health probes (`PASS`/`DEGRADED`/`FAIL`) + machine-readable `qa.health_report.v1` attestation (PG, ledger attestation, queue depth, breakers) |
| D-124 | Zero-leak telemetry discipline: D-114 gate + credential redaction + PII denylist + fixed `[REDACTED]` marker; no engine imports from observability modules |

## 3. Architecture flow

```
subsystem event ──> engine.log.v1 emitter ──> D-114 sanitize ──┬─> JSONL sink (append-only)
     (domain, event, entity)        deterministic trace/causal └─> durable vault (D-027 transport)

engine incr/observe ──> metrics registry ──> text exposition ──> http.server @ 127.0.0.1:<port>
   (logical timeline)      (declared names)   (Prometheus fmt)

probe registry ──> composable probes (injected reads) ──> qa.health_report.v1 ──> CLI / control plane
```

## 4. Security boundaries

- Observability modules import NO engine modules — they observe via
  injected read callables (RULES §35 boundary discipline); the AST
  sweep stays clean and the leakage battery enforces D-124.
- The metrics exporter binds strictly to 127.0.0.1 (battery-asserted);
  labels carry declared enum/status values only — never payloads,
  ids-with-secrets, or PII.
- Everything passes the Phase 20 `InputHardeningGate`/redaction path;
  nothing writes outside `local/volumes/` parity dirs or the canonical
  DB. Zero network egress; the exporter accepts loopback scrapes only.

## 5. Milestones

- **M1** — `local/canonical/obs_contracts.py`: `engine.log.v1` record
  shape, deterministic trace/causal id derivation, `TraceContext`
  propagation, JSONL sink + durable vault, D-114/redaction at the
  boundary, policy error taxonomy (Class-B).
- **M2** — `local/canonical/obs_metrics.py`: deterministic
  counters/gauges/histograms (fixed buckets), bounded registry,
  Prometheus text exposition, loopback-only stdlib exporter.
- **M3** — `local/canonical/obs_health.py`: probe protocol +
  shipped probes (PG reachability/schema, ledger attestation validity,
  queue depth, breaker states), `qa.health_report.v1` rendering, CLI.
- **M4** — `local/tests/test_phase22_observability.py`: leakage
  battery (zero PII/secrets in logs/labels/details), counter
  monotonicity, trace propagation across sinks, exposition-format
  compliance, loopback binding, live-PG vault + probes; full
  regression; verification record below.

## 6. Verification record (M4 closeout, 2026-09-18)

**Battery:** 750/750 OK, zero skipped, zero ResourceWarnings —
TWO consecutive full-battery runs green. Ladder 46/46. Tier census
reconciles exactly (750 = 750 across 29 modules): T1=649 · T2=46 ·
T3=48 live-PG · T4=7.

**Suite:** `test_phase22_observability.py` 26/26 zero-skip — 21
offline (unit tier) + 5 live-PG E2E (durable vault dedupe +
trace-scoped counting with run-scoped ids; live pg_schema probe
PASS; ledger-integrity probe over the real Phase 19 control-audit
chain PASS; tamper-detection fold semantics; operator CLI renders a
real `qa.health_report.v1` with overall DEGRADED/PASS and pg +
ledger probes green).

**Metric inventory (declared registry, D-122):** counters (monotone,
positive-int increments only), gauges, histograms with FIXED bucket
edges — declared names `[a-z_]+`, ≤8 labels, ≤64 label-value sets
per metric, no undeclared labels; exposition is byte-identical for
identical registry state (sorted, `# HELP`/`# TYPE`, `le="+Inf"`).
Exporter: stdlib HTTP, bind hardcoded to 127.0.0.1, port 0 =
OS-assigned, serves exactly `exposition()`, 404 off-path; verified
via the local tooling channel (curl).

**Log ledger inventory (D-121):** `engine.log.v1` — 8 required
fields, 7 declared domains, 4 levels, 4 statuses; `TraceContext`
(root/child) deterministic SHA-256 ids over causal inputs; JSONL
append-only sink + `PgLogVault` (D-027 transport, key
`log|<trace>|<causal>`, re-emission ⇒ `skipped_duplicate`);
boundary = redaction → marked truncation → D-114 gate (control
chars/confusables are Class-B, oversize is marked `…[TRUNC]`).

**Zero-leak proof (D-124):** battery covers credential markers in
details/payloads/labels (all → `[REDACTED]`), PII payload keys,
control chars (rejected), oversized fields (marked), exposition
text (no marker spans survive); probe details pass the same gate.

**Defects found and fixed in-batch:**
1. **Sanitize ordering** — the log boundary gated (rejected) before
   truncating, so oversized fields raised instead of being marked;
   reordered redact → truncate → gate.
2. **Vault key blind spot** — the durable key embedded only the
   causal id, making trace-scoped counts unmatchable (child ids are
   derived hashes); key now embeds `trace|causal`.
3. **Layer boundary** — the exporter initially lived in canonical;
   the Phase 20 sweep battery flagged `http.server` there and it
   was moved to `local/services/metrics_exporter.py` (canonical =
   pure logic, services = I/O) — the sweep net doing exactly its
   job across phases.
4. **Vault dedupe test vs durable state** — fixed ids collided with
   rows from the previous suite run (`skipped_duplicate` on first
   write); made run-scoped (the Phase 21 lesson, applied).
5. Stray quote syntax error in `queue_depth` threshold guard.

**Live attestation (operator CLI):** `python3
local/canonical/obs_health.py` → pg_schema PASS, ledger_integrity
PASS, breaker_states DEGRADED (74 non-closed breaker rows from
prior live test runs — honest durable-state reporting, bounded
detail). rc=0.

**Audit gates:** extended AST sweep CLEAN (88 files, 0 findings),
secret-entropy scan CLEAN (98 files, 0 flags), bounds re-audit
CLEAN (11/11), `git diff --check` PASS, stack 5/5 healthy.

**Standing owner gate:** strictly localhost (D-045/D-122) — the
exporter serves loopback only and no external collector, APM, or
alerting endpoint exists; Phase 22 passing does NOT prove
compatibility with real observability infrastructure (Prometheus
server, Grafana, on-call tooling).

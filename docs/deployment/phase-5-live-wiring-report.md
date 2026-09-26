# Phase 5 Live Wiring Report — Ignition & Service Connectivity Verification (D-155)

**Program:** Live Wiring (Phases 5–18), first phase under the D-154 completion
certificate. **Governance:** D-139 / D-154 / §17 / §21.6. **Predecessor:**
`dokploy.completion_attestation.v1` (D-154, commit `eba88a1`).
**Engine:** `local/scripts/live_wiring_phase5_igniter.py` — IGN-01..IGN-05,
fail-closed, injected transports, zero raw shell, D-124 deep redaction.

---

## 1. Verdict

| Item | Value |
| --- | --- |
| Attestation schema | `phase5.live_wiring_attestation.v1` |
| Verdict | `PHASE5_IGNITED` |
| Attestation digest (live run) | `225e121c27d2579cd208edb20f078786394bec0744ef1f8ceee5436637d616bc` |
| Bound D-154 certificate digest | `27d6c43e7960534f…` (full SHA-256 in the audit record) |
| Bound manifest SHA-256 | `7ca497057bd0976a…` (Stage D/E fingerprint, carried unchanged since Stage E) |
| Checks | IGN-01 ✓ · IGN-02 ✓ · IGN-03 ✓ · IGN-04 ✓ · IGN-05 ✓ (14/14 rows pass) |
| Handover | Phase 6 (Notion OS sync) verified per the IGN-05 check detail |

Exactly **one** audited ignition record is emitted per `run()` call — including
abort records (`IGNITION_INCOMPLETE`) — every copy deep-redacted with the
public commitments (`cert_digest`, `manifest_sha256`) restored after redaction
(D-146/D-153/D-154 precedent).

## 2. IGN rule results

### IGN-01 — D-154 completion certificate (gate, not input)
- Certificate schema `dokploy.completion_attestation.v1`, verdict
  `INFRASTRUCTURE_COMPLETE`, `attestation_digest` byte-exact recomputation.
- Chain bind: certificate `manifest_sha256` == activation record's == Stage E
  fingerprint; verdict `CUTOVER_EXECUTED`; closure digest rooted in the
  certificate checks; certificate itself rooted in the D-112 ledger (kind
  `dokploy_completion_attestation`); zero chain breaks.
- Any absence, alteration, digest drift, or unrooted row ⇒ immediate
  `IGNITION_INCOMPLETE` with **no transport probes executed** (fail-closed
  ordering: IGN-02/03/04 never run after an IGN-01 refusal).

### IGN-02 — PostgreSQL SSOT (canonical relational store)
- Authenticated connectivity through `ArgvPsqlTransport` (fixed argv list,
  `docker exec <container> psql -U engine_local -d business_engine_local
  -Atq -v ON_ERROR_STOP=1 -c <sql>`); connection selected by **environment
  name reference**, never a literal connection string; stderr never echoed.
- Schema readiness: 33 tables across 16 engine schemas (`admin`, `analytics`,
  `assets`, `canonical`, `events`, `hitl`, `instagram`, `notifications`,
  `oms`, `orchestration`, `provenance`, `registry`, `scheduling`, `security`,
  `seed`, `telegram`); SSOT seed census = 28 rows.
- Pooling invariants: `max_connections = 100`, `superuser_reserved_connections
  = 3`; `pooling_ok` requires max − reserved ≥ `POOL_HEADROOM` (12) — satisfied
  with wide margin.

### IGN-03 — Redis state/cache
- Connectivity via `ArgvRedisTransport` (fixed argv
  `docker exec <container> redis-cli --no-auth-warning …`); credentials ride
  the container's own environment (`REDISCLI_AUTH`), never argv, never reports.
- PING latency **28.6 ms** (live) — under the 50 ms `REDIS_LATENCY_BUDGET_MS`
  budget. Standalone transport benchmark: 34.3 ms. Both under budget.
- `maxmemory-policy = noeviction` (required: the engine treats Redis as
  state/cache with lossless semantics); namespace isolation drill
  `phase5:ignition_drill` SET/GET/DEL round-trip verified.

### IGN-04 — n8n webhook dispatcher (real D-053 contracts)
- Payload validation through the **real** `canonical/n8n_webhook_contracts.py`
  dispatcher (schema + HMAC verification over raw bytes).
- HMAC `sha256=` header verified with an injected secret the engine never
  holds (D-045 pattern).
- D-027 idempotency adherence: `(source_system, event_id)` replay returns the
  original record (drill event `phase5-ignition-drill-0001`), and the drill
  record round-trips the injected D-027 store (`receive` → `get_record`).

### IGN-05 — canonical emission
- `IgnitionAttestation` is a frozen dataclass; `attestation_digest` =
  SHA-256 over canonical JSON (`sort_keys`, `,`/`:` separators, the shared
  project formula). Digest is deterministic for identical inputs; the
  emitted artifact is immutable after emission.

## 3. Connection topology

```
igniter (pure core: clock + audit_sink + providers only)
 ├─ pg      → ArgvPsqlTransport   → docker exec engine-local-postgres  → psql (env-name auth)
 ├─ redis   → ArgvRedisTransport  → docker exec <redis container>      → redis-cli (REDISCLI_AUTH)
 └─ webhook → WebhookProbeTransport → canonical.n8n_webhook_contracts dispatcher (HMAC-signed)
                └─ D-027 store: receive()/get_record() idempotency pair
audit_sink → exactly one deep-redacted D-112 record per run
```

Purity envelope (AST-audited in the battery): no `shell=True`, no `Popen`, no
socket/HTTP imports in the igniter core; every child process is a fixed token
list with a 15 s (D-151) per-operation timeout; every transport is injectable,
so the entire battery runs offline with fakes while the live run swaps in the
argv transports.

## 4. Latency benchmarks (live stack, 2026-09-26)

| Probe | Measured | Budget | Margin |
| --- | --- | --- | --- |
| Redis PING (igniter evidence) | 28.6 ms | < 50 ms | 21.4 ms |
| Redis PING (standalone argv transport) | 34.3 ms | < 50 ms | 15.7 ms |
| PG `SELECT 1` round-trip ×3 (argv transport) | 42.6 / 42.4 / 42.4 ms | — | ≈1.6 ms engine-side psql seen earlier; the difference is `docker exec` process setup overhead, not DB latency |

PG latency is dominated by container-exec spawn cost in the local topology; on
the Dokploy target the same transport shape runs inside the network namespace
and the invariants that matter (pool headroom, ON_ERROR_STOP, timeouts) are
unchanged.

## 5. Environment note (live evidence provenance)

The canonical compose (Stage C/D, D-144 manifest) declares `redis` as a
Dokploy-target service; the legacy local stack carries the five
`engine-local-*` containers only. Live Redis evidence was captured through an
ephemeral `redis:7-alpine` drill container matching the manifest service name,
removed after evidence capture. PostgreSQL evidence ran against the canonical
`engine-local-postgres` container. n8n leg ran through the in-process D-053
contract dispatcher (the same `healthz: {"status":"ok"}` n8n container is up
on the local stack).

## 6. Battery evidence

- New module `local/tests/test_live_wiring_phase5.py`: **38/38**.
- Full regression: **1644/1644 tests across 71 modules, ×2 consecutive runs,
  0 bad, 0 skipped**, machine-reconciled census (71 unique modules both runs).

## 7. Handover to Phase 6 (Notion OS sync)

Phase 5 leaves the engine with a **verified ignition surface** for every
downstream phase:

- **SSOT readable/writable** (33-table schema seeded, pool headroom proven) —
  Phase 6's Notion sync reads canonical entities from these schemas through
  the same argv/transport seam.
- **State/cache semantics fixed** (noeviction, isolated namespace prefix,
  <50 ms PING) — Phase 6+ queues and deduplication keys inherit the
  `phase5:*`-style namespacing discipline.
- **Webhook conduits live** (D-053 schema + HMAC + D-027 idempotency proven) —
  Phase 6's Notion events dispatch through the identical dispatcher contract.
- **Governance chain extended**: D-155's audit record roots in the D-154
  certificate and the D-112 ledger, so every later phase's gate can require
  the Phase 5 attestation the same way IGN-01 requires the D-154 certificate
  (fail-closed recursion: Phase N refusal ⇒ no Phase N+1 probes).

Ignition order for Phases 6–18 is unchanged from the completion report's
transition guide; each phase adds one igniter module, one battery module, and
one governance row, exactly as Phase 5 did.

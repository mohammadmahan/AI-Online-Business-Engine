# Phase 5 Gate Report — n8n Foundation

- Date: 2026-09-14
- Authority: MASTER_PLAN §13 Phase 5 / **D-059 Approved (Option A)**
- Scope discipline: local-first (D-053) — no external connections, no
  credentials created, no production n8n deployment.
- Gate status: **PASSED for the Phase 5 scope** — with two owner
  activation steps pending (§5). Those steps gate *execution*, not
  *foundation*; the D-059 acceptance criteria concern the foundation.

---

## 1. Scope & objective

Phase 5 established the operating rules, execution tiers, error
routing, idempotency boundaries, and the local n8n runtime baseline
**before** any business automation is introduced (MILESTONE discipline
of D-059 Option A: plan's Phase 5 first; content/posting workstream
deferred to its proper later phases).

## 2. Milestone audit & deliverables

### M1 — Standards, governance & idempotency
| Artifact | Content |
|---|---|
| `docs/standards/n8n-conventions.md` | Naming grammar `[TIER]-[DOMAIN]-[TRIGGER]-[ACTION]` (true-highest-tier rule), secret isolation (D-045), D-050 tier mapping, validity checklist |
| `docs/standards/n8n-idempotency-and-retries.md` | D-027 deterministic key `SHA256(source_system + event_id + event_type)` (timestamp never an ingredient), D-052 failure matrix A–E with retry policies, dead-letter route |
| `docs/standards/n8n-logging-and-redaction.md` | `engine.log.v1` schema, redaction mandate (leak = rotate + review), permitted-tracing list, D-053 local-only log sink |
| `local/n8n/README.md` | Verified runtime facts (`engine-local-n8n`, `infra_n8n_data`, `infra_default`, 127.0.0.1:15678), export-or-it-didn't-happen discipline |

### M2 — Sandbox smoke workflow
- `GREEN-OPS-MANUAL-CANONICAL_DB_SMOKE.json` — manual trigger →
  read-only query against the real D-055 schema (`seed.size_family`) →
  `engine.log.v1` line. Imported into the live n8n; ships inactive.
- Boundary proven live: the Postgres node refuses execution until the
  owner creates the credential in the UI — no secrets in Git (D-045).
- 7 automated contract tests.

### M3 — Global failure router & redaction
- `GREEN-OPS-ERROR-GLOBAL_FAILURE_ROUTER.json` — Error Trigger →
  classify + redact → `engine.log.v1` failure line. Imported into the
  live n8n; ships inactive.
- `local/canonical/n8n_failure_taxonomy.js` — canonical D-052
  classifier + D-045 redactor; embedded byte-identically (parity
  test-enforced) and executed under the real Node runtime in CI,
  including the M2 credential refusal as a live Class C vector.
- 21 automated tests (13 executed, not string-greps).

### M4 — Dead-letter routing → HITL (this closeout)
- `local/canonical/n8n_dead_letter_sink.js` — canonical terminal-route
  router: **A** → `retry_backoff` (never dead-letters); **B/C/E** →
  `dead_letter_hitl`; **D** → `quarantine_and_hitl`. Embedded
  byte-identically in the router (regenerated; re-imported live).
- Router emit contract: terminal classes emit a tagged
  `<<<DEADLETTER>>>` line on the container stdout — the D-053 local log
  sink; no new service, no host mounts, no credentials.
- `local/scripts/dead_letter_bridge.py` — canonical-layer bridge:
  parses tagged lines from `docker logs`, materializes each dead-letter
  as a HITL verification-queue item (item key `n8n|<idempotency_key>`,
  idempotent re-ingestion; malformed lines counted, never silently
  dropped) with **D-026 provenance** (`EXTERNAL_SYNC`, actor
  `n8n-error-router`). Enqueue-only: no decision API exists on it
  (test-enforced, D-050).
- 16 automated tests, including end-to-end: synthetic router output →
  bridge → **real** `VerificationQueue` → D-026 records → human
  decision through the ordinary review path.

## 3. Verification evidence (2026-09-14)

```
Discovery battery (local/tests):  117/117 OK — 0 skipped
  (ladder 46 · M3 21 · M4 16 · M2 7 · edge 16 · queue 11)
Canonical unit suite:             32/32 OK
Live-DB smoke:                    12 passed, 0 skipped, 0 failed
Live n8n: /healthz → 200; both workflows imported (list verified)
git diff --check:                 PASS
```

## 4. Decision traceability

| Standard / behavior | Anchor |
|---|---|
| Credential isolation, no secrets in Git/workflows | D-045 |
| Event idempotency keys, dedupe verdicts | D-017 / D-027 |
| Failure classes A–E, retry vs dead-letter vs quarantine | D-052 |
| GREEN/YELLOW/RED authority tiers; RED needs human approval | D-050 |
| Provenance on queued items and decisions | D-026 |
| Local-only runtime, no external endpoints | D-053 / D-054 |
| Price data read-only in workflows (never a price source) | D-048 |
| Local-first sequencing (plan's Phase 5 before workstreams) | D-059 |

## 5. Owner activation checklist (gates execution, not the gate)

1. Open `http://127.0.0.1:15678` → **Credentials** → create
   `Postgres Canonical Local` (type: Postgres; host
   `engine-local-postgres`, port 5432, database `business_engine_local`
   — values from the local `.env`, never committed).
2. **Settings → Error workflow** → select
   `GREEN-OPS-ERROR-GLOBAL_FAILURE_ROUTER`.
3. Execute `GREEN-OPS-MANUAL-CANONICAL_DB_SMOKE` once (click Execute) —
   expect the engine.log.v1 line with the live size-family count.
4. Periodically run the bridge to materialize dead-letters into the
   review queue:
   `python3 local/scripts/dead_letter_bridge.py --since 24h`
   then review: `python3 local/canonical/verification_tool.py report`.

## 6. Explicitly deferred (later phases, unchanged)

- Production n8n deployment, external endpoints/webhooks (G5-adjacent;
  D-058 deferral stands).
- YELLOW/RED workflows: sync engine projection, publishing, anything
  price- or inventory-changing.
- Content/posting workstream (deferred per D-059 Option A).
- Multi-instance n8n, external monitoring/alerting (Phase 6+).

## 7. Conclusion

All acceptance criteria set by the M1 spec and D-059 Option A are met:
standards exist and are enforced by executable contract tests; two
workflows are live-imported, validated, and inactive-by-design; the
D-052 terminal route terminates in the human review queue with
attributable provenance. **Phase 5 is formally closed at the
foundation level; activation is a 5-minute owner step (§5).**

---

## 8. Addendum (2026-09-20) — Live automation wiring (core side)

The core-engine half of live n8n automation is now implemented and
battery-attested (roadmap §2 step 8 scope), completing the seam the
foundation-level closure pointed at:

- **Webhook contracts** (`local/canonical/n8n_webhook_contracts.py`,
  pure/deterministic): HMAC-SHA256 webhook-signature verification over
  exact raw bytes (constant-time compare; fail-closed on an unset
  `N8N_WEBHOOK_SECRET` reference — D-045 pattern, no default secret
  exists); strict bounded event parsing (`event_type` enum:
  `workflow.completed` / `workflow.failed` / `hitl.request` /
  `ops.ping`, ≤64 KiB, exact key set); deterministic D-027-lineage
  event keys (SHA256 over event_type + workflow_ref + event_id —
  same delivery ⇒ same key, distinct event ⇒ distinct key, no wall
  clock).
- **Event dispatcher** (`N8nEventDispatcher`): core-engine ↔ n8n
  event wiring with INJECTED handlers (RULES §35) and exactly-once
  idempotency via the key store (dispatched → `skipped_duplicate`);
  handler failures are recorded per-event, never silent, and never
  abort the batch.
- **Live verification script** (`local/scripts/validate_n8n_live.py`):
  OFFLINE mode validates the manifest reachability contract (n8n
  image, loopback `127.0.0.1:15678→5678`, `/healthz` healthcheck,
  canonical-db dependency) plus the full webhook-contract drill;
  LIVE mode probes the RUNNING local container (`/healthz` → 200
  verified against the live stack) and re-runs the contract drill;
  an authenticated n8n API round-trip is available ONLY behind the
  explicit owner flag `N8N_API_PROBE=true` + `N8N_API_KEY`
  (D-045 credential gate — skipped by design otherwise, key material
  never printed).
- **Battery** — `local/tests/test_phase5_live_wiring.py` (18 tests,
  ×2 green): HMAC round-trip/tamper/malformed/fail-closed, parsing
  rejections, dispatcher idempotency and error semantics, and the
  validation script's contract terms including the credential gate.

Live workflow activation remains the owner step described in §5;
no secret exists or is required for the verified paths.

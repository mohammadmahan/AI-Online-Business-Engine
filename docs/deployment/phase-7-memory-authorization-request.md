# Phase 7 Memory Authorization Request — Walrus (D-142)

**Type:** request for owner authorization. **Status:** OPEN — awaiting owner acts.
**This document amends no decision and grants nothing.** It is a request record under
`docs/deployment/`, not a governance source. Where it disagrees with
`MASTER_PLAN.md`, `TODO.md` or `DECISIONS.md`, those documents win.

**Prepared:** 2026-10-24 · **Repository state:** `main` at `585ef76`, clean tree.

---

## 1. Correction of framing

There is **no "Phase 7: AI Intelligence & Shared Memory Layer"** in this repository.
The naming collision matters, because it makes already-shipped work look like
unstarted work and gated work look unstarted:

| Claim | Canonical record |
|---|---|
| Phase 7 is the AI Runtime | `MASTER_PLAN.md` §13 — `### Phase 7 --- AI Runtime` (model routing, structured outputs, validation, cost control, provenance, logging, approval gates) |
| Phase 7 is closed | `TODO.md` — `[x] Phase 7 — AI Runtime … CLOSED at foundation level (2026-09-16), M1–M4 complete`; M4 report `docs/reports/PHASE_7_GATE_REPORT.md` |
| Walrus/MemWal is not a phase | `DECISIONS.md` **D-142** — a post-baseline work item, register row **44** |
| The memory foundation already ships | `DECISIONS.md` D-142 verification block (2026-09-22); `MASTER_PLAN.md` Stage H + D-142 foundation paragraph |
| Its only remaining item is connectivity | `TODO.md` — `[ ] Work item — Portable multi-agent shared-memory layer (MemWal)`: *"Remaining: Walrus/relayer connectivity … owner-gated (D-045)"* |

## 2. Implemented state (offline, no credential, no connection)

| Artefact | Role |
|---|---|
| `local/src/memory/vector_store.py` | pgvector-compatible SSOT store: pinned DDL, HNSW index hook, injected `executor(sql, params)`, deterministic summarisation pruning, deep redaction on **write and read** |
| `local/src/memory/memwal_adapter.py` | Portable `memwal.wal.v1` hash-chained JSONL, `verify_wal` tamper detection, offline-first sync with transparent `pending_remote` fallback that never raises to the agent, D-125 snapshot composition |
| `local/src/memory/memwal_transport.py` | Transport seam contract: deterministic idempotency keys, bounded chunking, D-044-shaped error taxonomy, redaction re-assertion, non-raising verdicts |
| `local/src/ai/memory_interceptor.py` | Context in (`prompt_payload["memory_context"]`), interactions/summaries out, D-127 `memory_ops` metering, zero-blockage degradation |
| `local/src/ai/campaign_winner_context.py` | Bounded Phase 7/8 winner-prompt adapter |
| `local/src/commerce/support_memory_bridge.py` | Support retrieval; template fallback; memory never order-authority |
| `local/src/analytics/campaign_correlator.py` | Winning-campaign summaries into the memory write path + WAL |

Battery: `local.tests.test_stage_h_and_memwal` (27) + `local.tests.test_memory_ai_integration` (17)
+ `local.tests.test_memwal_transport_conformance` — all hermetic, injected executors/transports only.

**Walrus/relayer is NOT connected. No MemWal SDK is installed. No credential exists.**

## 3. The five-link authorization chain

Each link is a separate owner act. No link implies the next.

### Link 1 — Register row 8: secret-management tooling

- **Authority:** `DECISIONS.md` register row 8 — concrete tooling selection **Open**, gate "First credential".
- **Why it blocks:** D-045 stores secrets "via environment/secret-management at implementation time; the secret-management tooling selection remains register row 8 (OPEN)". Without a selected store there is no lawful custody location for a MemWal key.
- **Owner decides:** named tooling; per-environment separation; rotation owner.
- **Unlocks:** custody for *any* credential (payment, SMS, AI, Walrus) — broader than this request.
- **Does not grant:** no credential is created; no connectivity.

### Link 2 — D-058 / G1 hosting

- **Authority:** `DECISIONS.md` D-058 — the seven Phase 4 gates, including G1 hosting/VPS, **DEFERRED (local-first)**.
- **Why it blocks:** D-141 Stage C requires provisioning a staging host "per approved G1 path" (`docs/deployment/dokploy-plan.md`, stage table).
- **Owner decides:** keep the deferral (Walrus stays blocked), or approve G1 for staging only.
- **Does not grant:** any production resource.

### Link 3 — D-141 Stage C

- **Authority:** `DECISIONS.md` D-141 — approved for planning + Stage A; **B–H gated by separate per-stage owner authorizations**. Stage C status: `PLANNED`.
- **Why it blocks:** D-142's status line gates implementation "behind Dokploy staging/production stabilization (**D-141 stages C+**)".
- **Owner decides — five separate grants:** VPS provisioning · installer execution · firewall ports · GitHub connection · staging DNS. Per the plan, "Stage C/F gate columns are summaries, not grants."
- **Acceptance:** staging serves the stack from the approved manifest; battery-compatible checks pass against staging; deploy identity recorded.
- **Does not grant:** production data import, production DNS, auto-deploy to production.

### Link 4 — Dedicated D-142 integration work authorization

- **Authority:** `DECISIONS.md` D-142 status — gated behind "a dedicated future work authorization".
- **Owner decides:** scope boundary (transport adapter, ignition/verification evidence, report), acceptance criteria, and whether the established live-wiring attestation pattern applies.
- **Does not grant:** connectivity or credentials — D-045 still governs both.
- **Note:** this is the link under which any further *offline* seam work becomes authorised work rather than invented work.

### Link 5 — D-045 connectivity and credential custody

- **Authority:** `DECISIONS.md` D-045 items 1–4 — never in Git, docs, Excel, AI prompts, logs, or hard-coded workflow nodes; environment/secret management only; least privilege; separate credentials per environment; exposure ⇒ stop and report.
- **Owner decides:** MemWal account/delegated key issuance, endpoint/relayer target, environment (staging only), rotation owner, exposure-response owner.
- **Agent-side commitment:** the key is never requested in chat, printed, committed, or written to a tracked file.

### Optional governance amendment (owner's choice, not a bypass)

D-142 couples connectivity to **D-141 stages C+**. That coupling is a recorded
governance choice, not a technical dependency — a memory relayer needs no staging
VPS. If the owner intends Walrus to proceed independently, the lawful route is an
**append-only amendment to D-142** decoupling the two. Absent that amendment,
Links 2–3 remain mandatory even though they are unrelated to memory.

## 4. Forbidden until every link exists

- No `@mysten-incubation/memwal` install, no Walrus/relayer request of any kind.
- No credential in Git, env files, logs, prompts, or documentation.
- No fabricated memory status or counts in the control plane (`NOT_CONNECTED` with
  zero namespaces/bytes remains the only truthful render — D-171 §5.5).
- No memory write becoming business truth or approval authority (D-026/D-027).
- No rewriting D-142's append-only status line.

## 5. Verification commands (offline)

```bash
python3 -m unittest local.tests.test_stage_h_and_memwal \
                   local.tests.test_memory_ai_integration \
                   local.tests.test_memwal_transport_conformance
```

The live pgvector proof (`test_memory_vector_store_live.py`) follows the repository's
established live-tier convention: it runs when a pgvector-capable PostgreSQL answers
on `127.0.0.1:55433`, and skips with an honest reason otherwise. The tracked
`local/infra/docker-compose.yml` pins `postgres:16-alpine`, which has **no `vector`
extension**; no tracked infrastructure file was modified for this request.

## 6. Sources

`MASTER_PLAN.md` §13 (Phases 4, 7, 24) and the Stage H + D-142 paragraphs ·
`TODO.md` D-142 work item and Phase 7 closure records · `DECISIONS.md` D-045, D-058,
D-141, D-142 (and register rows 8 and 44) · `docs/deployment/dokploy-plan.md`
stage table · `docs/decisions/D-171-unified-web-control-plane.md` §5.5.

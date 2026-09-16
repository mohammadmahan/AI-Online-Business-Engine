# Phase 7 Gate Report — AI Runtime (M1–M4)

- Date: 2026-09-16
- Authority: MASTER_PLAN §13 Phase 7 + **D-062 / D-063 / D-064 (all Approved, 2026-09-15)**
- Gate Status: **PASSED** — all milestones M1–M4 complete; zero-skip discipline held throughout.
- Audit executor: Phase 7 M4 audit suite (`local/tests/test_phase7_ai_runtime_m4.py`, 23 tests).

---

## 1. Scope closed by Phase 7

| Milestone | Commit | Content |
|---|---|---|
| M1 — contracts & router | `6916e04` | Provider-neutral router, 3 strict JSON-Schema contracts, D-063 cost guardrails, D-052 failure mapping, `AiProposal` envelope, authority no-execution assertion |
| M2 — proposal lifecycle & HITL round-trip | `5f3cab7` | Durable event-sourced state machine on D-027 stores (JSON + live PostgreSQL), human-only `decide()`, D-026 provenance on every decision, terminal immutability, 4 defects found & fixed pre-ship |
| M3 — concrete tasks & batch logic | `bbd16fe` | `ContentIdeaTask` / `CaptionTask` / `DescriptionTask` on the boundary; dry-run & batch modes; divergence detection against D-032 vocabulary + canonical products; budget-stopped batches |
| M4 — gate report & audit | *this commit* | Static path audit, dynamic conformance proof, cost-ledger audit, D-045 boundary audit, live-store durability proof, frozen-envelope hardening |

## 2. Full test metrics (zero-skip verified)

```
M4 audit suite:        24/24 OK  (6 static path · 5 dynamic conformance ·
                                  5 cost-ledger · 5 provider boundary ·
                                  3 live PG incl. rapid-ingest ordering)
Phase 7 total:       100/100 OK  (31 M1 + 25 M2 + 20 M3 + 24 M4)
Full discovery battery: 294/294 OK — 0 skipped (4 grep "skipped" hits are
                        test NAMES, all ran ok — verified via verbose grep)
Test ladder:          46/46 OK · Live smoke: 12/12 (5/5 containers healthy)
git diff --check:      PASS · secret scan: clean (all hits = banned-token
                        lists / the stdlib module name "secrets" / policy prose)
```

Live PostgreSQL layers ran on the up Colima stack; nothing was skipped.

## 3. Governance alignment (D-062 / D-063 / D-064 — all Approved)

- **D-062 (router & strict contracts):** provider-neutral `AiProvider` boundary; strict JSON-Schema subset validator; permissive schemas and unknown keywords are load-time errors; code contracts pinned to `local/tests/fixtures/ai/schemas.json` — drift fails the battery (re-proven in M4).
- **D-063 (cost guardrails):** token-bucket limiter (refusal = Class A), soft 80% warning, hard 100% refusal **before dispatch** (zero marginal provider calls — proven by call counting), append-only usage ledger. M4 audit adds: every call metered including failed-but-billed validation failures; provider errors zero-cost; budgets fire **without** a ledger (safety property independent of persistence).
- **D-064 (proposal pipeline / HITL boundary):** `PROPOSED → IN_REVIEW → ACCEPTED / REJECTED / MODIFIED_BY_HUMAN` — every transition a durable D-027 event + D-026 provenance; decision verbs exist **only** on the lifecycle, never on provider/router/tasks (AST-asserted); proposals land `PROPOSED` only.

## 4. Security / Red-path boundary verification

**Static (AST over the four shipped modules):**
- Import roots ⊆ stdlib ∪ {canonical, services}; forbidden roots (mock_woo, notion_adapter, media_store, woo, prices, requests, urllib, http, socket, subprocess, …): **zero hits**.
- No integration module referenced in any string constant.
- Public surface of `AiProvider`/`MockAiProvider`/`ModelRouter`/tasks carries no execution verb (`decide/publish/execute/approve/reject/advance/apply`).
- No `os.environ` access, no credential material (`api_key/apikey/secret/bearer/authorization`), no `openai`/`anthropic` attribute access, no production endpoint strings.
- Shipped contracts == pinned fixture (byte-frozen).

**Dynamic (behavioral proof):**
- Accepted proposal reaches **only** its registered canonical target (registry-scoped applier; unregistered target raises and the raise is *observed*, not swallowed).
- Forced provider failure ⇒ zero pipeline side effects (no D-027 event, no provenance, no queue item, no spend).
- Router envelope is **tamper-evident** (M4 hardening: `AiProposal` is now `frozen=True` — post-validation mutation raises `FrozenInstanceError`; codebase-wide scan confirmed nothing mutates envelopes).
- HITL queue never holds decision records (deterministic scan of all queue items across a full lifecycle).
- Conflicting re-delivery (same correlation id, different payload) refused with `IntegrityError` — **offline and on live PostgreSQL**.
- Restart safety on live PG: fresh lifecycle instances reconstruct state from the durable store; terminal re-decision is idempotent (`skipped_duplicate`); applier runs exactly once.

**Live-store durability defect found and FIXED in M4 (the significant audit result):**
- **Symptom:** the Phase 6 row-D conformance test failed intermittently in the full battery (`Review -> Review` during reconstruction).
- **Reproduction:** a 60-iteration rapid-ingest probe failed 2/60 on the live store.
- **Root cause:** `received_at` is wall-clock (`now()`), and the Colima VM clock stepped backward (NTP/host sync) under rapid successive ingests — a row ingested *later* persisted an *earlier* `received_at`. `ORDER BY received_at, event_id` therefore reordered genuinely sequential events, and event-sourced lifecycle reconstruction broke.
- **Fix (schema + both stores):** monotonic insertion sequence — `events.event_record.ingest_seq bigserial` on PostgreSQL, durable `receive_seq` counter on the JSON store; `succeeded_references()` orders by it (with a fallback for pre-`ingest_seq` stores). `received_at` demoted to audit metadata, never an ordering key. Verified 0/60 on both stores post-fix; regression test added (`test_rapid_ingest_reconstruction_is_monotonic_on_live_store`, 12 rapid chains on live PG).

## 5. Cost-ledger audit results

- Ledger persists entry-by-entry; the file view equals the in-memory history (append-only shape).
- Budget refusal bound proven: spend ≤ budget + one call (guardrail checks before dispatch).
- Dry-run metering (M3, re-verified): usage metering stays ON during dry-runs so batches cannot evade budget accounting; pipeline persistence is what dry-run suppresses.

## 6. Deferred live-provider connectivity audit (explicitly NOT done)

- **No real AI provider (OpenAI/Anthropic/local server) was contacted in Phase 7.** No credential exists, none was created, none was requested (D-045).
- The provider boundary is plug-and-play by construction: real adapters are drop-in `AiProvider` implementations registered in the routing policy — no module change required. Routing to an unregistered provider fails deterministically as **Class B config error** — never a network attempt.
- The default routing policy ships `mock`-only. Real provider selection is a **separate owner-gated decision** (register row 9).
- **M4 passing does not prove live AI-provider compatibility.** Structured-output modes, real token accounting, and real tariff tables remain unverified until the owner approves a provider and credentials.

## 7. Readiness criteria for Phase 8

Phase 7 is closed at foundation level. Phase 8 may open when:
1. Owner approves the next-phase scope (per MASTER_PLAN §13 sequence).
2. Standing gates remain: no AI-proposed content is auto-applied; all external credentials owner-gated; Red operations human-only.
3. Carry-forward owner-gated items: AI provider selection + credentials (row 9); real Notion connectivity (Phase 6 gate); real Woo connectivity (Phase 4 gate); Phase 4 infrastructure gates (D-058 deferral).

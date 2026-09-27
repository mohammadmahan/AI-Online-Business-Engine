# Phase 16 Live Wiring Report — Analyst Service (D-166)

**Attestation:** `phase16.analyst_wiring_attestation.v1`
**Verdict:** `PHASE16_IGNITED` (dry-run, injected pure evaluator, zero LLM/lake contact, zero durable footprint)
**Upstream:** `phase15.analytics_wiring_attestation.v1` (D-165) — digest `4f807900f19ef297…`
(battery-built chain), rooted in the D-112 ledger row kind
`phase15_analytics_wiring_attestation`, chain intact.
**Engine:** `local/scripts/live_wiring_phase16_igniter.py` (ANL-01..ANL-05)
**Battery:** `local/tests/test_live_wiring_phase16.py` — 44 tests, ×2 green
**Governance:** D-045 / D-101–D-104 / D-114 / D-124 / D-139 / D-142 / D-154 /
D-163 / D-165 / §17 / §21.8. Chain: D-154 → … → D-164 → D-165 → **D-166**.

---

## 1. Upstream attestation verification (ANL-01)

The Phase 15 attestation is verified **before any engine call**: schema
(`phase15.analytics_wiring_attestation.v1`), the `PHASE15_IGNITED` verdict,
the manifest binding, and the D-165 attestation's canonical bytes recomputed
and matched against the SHA-256 commitment rooted in the D-112 ledger
(`phase15_analytics_wiring_attestation`), with full chain integrity delegated
to the injected verifier. Every refusal class (absent / raised / wrong schema /
incomplete verdict / drifted digest / unrooted / broken chain) provably leaves
the analyst surface untouched — the battery asserts the stack factory is
never invoked and the engine is never constructed on refusal.

## 2. Runtime profile & seams (ANL-02)

The injected census must mark `runtime_profile_verified` and Phases **5–12,
14 and 15** present + VERIFIED + WIRED (slot 14/CRM is deliberately **not** a
census row — D-163). The repo-real seams are asserted importable and pinned
to the D-154 `ENTRY_POINTS` registry:

| Seam | Module | Registry pin |
|---|---|---|
| Analyst engine | `canonical.analyst_engine` | `ENTRY_POINTS[17]` ("AI Business Analyst") |
| Analyst contracts | `canonical.analyst_contracts` | supporting (exempt) |
| Analyst worker | `canonical.analyst_worker` | supporting (exempt) |
| Analytics engine | `canonical.analytics_engine` | `ENTRY_POINTS[16]` |
| D-027 event store | `services.sync_engine` | supporting (exempt) |

The **load-bearing pin** is the slot-17 cross-walk check: the D-154
cross-walk binds registry slot 17 to `canonical.analyst_engine`. Any mismatch
refuses as **registry drift** / **cross-walk drift** before ANL-03 runs.

## 3. Analyst contracts & invariants (ANL-03) — through the REAL validator

| Invariant | Mechanism | Evidence |
|---|---|---|
| Invalid-request refusals | REAL `validate_insight`: missing fields, unknown categories/severities, confidence outside [0, 1] (bool excluded), incomplete metric contexts, empty correlation keys, non-dict payloads, illegal entry statuses — all Class-B BEFORE any durable write (D-102/D-114) | 10 invalid-request classes enforced with named reasons; both conforming probe insights pass |
| Deterministic identity | `insight_key` = SHA-256 over (category, sorted correlation_keys, sorted metric_refs) — no wall clock, no generator state | identical evidence in different ORDER yields the SAME key; a changed correlation key yields a DIFFERENT key (dedup collision surface closed) |
| Lifecycle edge matrix | `is_transition_legal` over D-101 edges | 6 legal edges pass (incl. SUPERSEDED from GENERATED and from the HITL queue); 6 illegal edges refuse (terminals exitless — SUPERSEDED from AUTO_ACCEPTED refused) |
| D-104 HITL boundary | `requires_hitl` / `can_auto_accept` | HIGH severity ⇒ HITL-bound; LOW with a `mutates_business_state` payload ⇒ HITL-bound; LOW non-mutating ⇒ auto-acceptable; the canonical `make_recommendation` shape enforced |

## 4. Dry-run analyst cycle trace (ANL-04)

Four synthetic insights over the REAL `AnalystEngine` (D-101/D-102/D-104) on
the REAL D-027 parity `EventStore` with the **ephemeral** in-process vault and
an **injected pure evaluator** (the mock intelligence — deterministic, no AI
SDK):

| Step | Result | Telemetry |
|---|---|---|
| START | ok | cycle id `phase16-analyst-probe-0001` |
| AUTH | ok | evaluator injected-pure; data provider synthetic D-142-shaped fixtures; **llm_providers: none** |
| PROPOSE | ok | 2 insights durable CREATED; an identical-evidence re-propose under a different incidental `insight_id` → durable `DUPLICATE` with exactly one dedup audit row (evidence-keyed dedup, D-102) |
| EVALUATE | ok | pure verdicts applied durably (2 × EVALUATED); a double evaluation refuses with `not_evaluable` (the GENERATED→EVALUATED edge is closed behind you) |
| BOUNDARY | ok | D-104 driven both ways: HIGH auto-accept **structurally refused** (`hitl_required_boundary`) → dispatched to HITL; LOW auto-accepted; a state-mutating payload at LOW severity also refused |
| SUPERSEDE | ok | the HITL-queued insight superseded by newer evidence (SUPERSEDED, ledger history kept); superseding a terminal (AUTO_ACCEPTED) insight **refused** (terminal exitless) |
| LEDGER | ok | chain-of-thought integrity: the HIGH insight's durable rationale rebuilds from D-027 events alone as generated → evaluated → dispatched_to_hitl → superseded; 4 vault rows, end-states `{EVALUATED, SUPERSEDED, AUTO_ACCEPTED}` all represented |
| INVALID | ok | 4 invalid analysis requests refuse Class-B with **zero durable rows added** (zero-partial-write) |
| VERIFY | ok | sandbox-marker sweep (`api_key`, `llm_provider`, `openai`, `anthropic`, `data_lake`, …) clean; vault asserted ephemeral |
| CLEANUP | ok | `phase16-scratch:analyst` artifact deleted, zero residue |

**Sandbox discipline:** the analyst vault default backend persists to
`local/volumes/analyst/insights.json` (or live PG). The probe injects
`_EphemeralVault` — `insert_insight`/`get_insight`/`set_status`/
`all_insights` semantics identical to `_JsonVault`, ZERO durable footprint —
and the VERIFY step refuses any non-ephemeral vault by class (battery-proven
with a fully functional foreign vault: every data check passes, the class
check still refuses). NO real LLM provider is contacted and NO historical
data lake is read — the data fixtures are pure in-process shapes conforming
to the D-142 record discipline (ids as hashes, no content payloads).

**Cycle timing:** the ANL-01..ANL-05 ignition cycle ≈ **83 ms** in-process
(including the battery's authentic upstream chain build — real
D-165 → D-164 → … → D-154). Attestation digest `2c5fb7998575e7fc…`,
byte-stable across runs.

## 5. Security posture

- **D-104 HITL boundary is structural, not advisory:** HIGH/CRITICAL severity
  and state-mutating payloads are non-auto-acceptable BY CONSTRUCTION
  (`can_auto_accept` cannot return True for them); the battery asserts the
  engine refuses both auto-accept paths.
- **No AI provider, no lake:** the evaluator is an injected pure function;
  the VERIFY sweep scans the durable event stream for LLM/lake/credential
  markers — any hit fails the run.
- **D-124 redaction:** recommendation payloads beyond the canonical
  Recommendation shape, customer identity and provider tokens never enter any
  emitted record; the battery scrubs every output for canaries.
- **Purity (AST-pinned):** no network/db/shell imports or calls in the
  engine; injected store/vault transports only.

## 6. Verification & battery

- New battery **44/44 ×2** (ANL-01..04 refusal classes, slot-17 cross-walk
  drift, slot-14-not-required census proof, REAL-validator rejection matrix,
  direct contract probes: identity, edge matrix, D-104 boundary,
  recommendation shape, confidence bounds, evaluator contract, durable audit
  kinds, emission contract, redaction scrubs, AST audits).
- Full regression **2087/2087 ×2 consecutive green across 81 modules**
  (2043 + 44), zero bad, zero skipped, per-chunk counts identical across runs
  and reconciled to the untouched-module invariant (the 80 pre-existing
  modules still carry exactly 2043 tests).
- **Invocation contract:** the battery must run from the repository **root**
  (`python3 -m unittest local.tests.…`) — environment contract, not a
  regression. Heavy chunks: the live-PG cluster (≈ 540 s) and
  `test_phase26_dr_closeout` (≈ 455 s) dominate wall-clock.

## 7. Handover to Phase 17 — HITL service (registry slot 18)

Verified and inherited by Phase 17:

- The analyst surface is *verified, not opened*: insights reach
  `DISPATCHED_TO_HITL` but no HITL service is wired yet — Phase 17 ignites
  exactly that consumption edge (`canonical.ai_hitl_service`).
- The D-104 boundary guarantees the HITL queue only ever receives
  human-reviewable insights; the durable rationale (generated → evaluated →
  dispatched) is the evidence pack the HITL service renders.
- The final registry path is explicit: slot 18 (HITL,
  `canonical.ai_hitl_service`) — the last ignition — then the program-level
  completion reconciliation.

Phase 17 entry criteria: remaining service wiring under the same fail-closed
attestation recursion (per `dokploy-plan.md` and the D-154 transition). The
D-163 disposition stands: no CRM exists or is planned; slot 14 remains bound
to the existing `commerce.sync_orchestrator` facade.

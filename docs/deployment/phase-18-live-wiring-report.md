# Phase 18 Live Wiring Report — HITL Service Ignition (D-168)

**Attestation:** `phase18.hitl_wiring_attestation.v1`
**Verdict:** `PHASE18_IGNITED` (dry-run, reviewer interfaces isolated, zero
human-notification or dashboard egress, zero durable footprint)
**Upstream:** `phase17.notification_wiring_attestation.v1` (D-167) — digest
`048952dc580d9add…` (battery-built chain), rooted in the D-112 ledger row
kind `phase17_notification_wiring_attestation`, chain intact.
**Engine:** `local/scripts/live_wiring_phase18_igniter.py` (HIT-01..HIT-05)
**Battery:** `local/tests/test_live_wiring_phase18.py` — 44 tests, ×2 green
**Governance:** D-045 / D-050 / D-064 / D-068 / D-079 / D-105–D-108 /
D-114 / D-124 / D-154 / D-163 / D-166 / D-167 / §17 / §21.8. Chain:
D-154 → … → D-166 → D-167 → **D-168**.

> **Registry milestone.** Phase 17 verified the notification engine while
> *asserting* (not taking) slot 18. Phase 18 ignites exactly the D-154
> binding: **registry slot 18 = `canonical.ai_hitl_service` is now TAKEN** —
> the final registry ignition of the Live Wiring program. Slots 5–18 are all
> VERIFIED/WIRED (slot 14 remains closed CRM-not-needed, D-163); the
> program-level completion reconciliation is the next milestone.

---

## 1. Upstream attestation verification (HIT-01)

The Phase 17 attestation is verified **before any engine call**: schema
(`phase17.notification_wiring_attestation.v1`), the `PHASE17_IGNITED`
verdict, the manifest binding, and the D-167 attestation's canonical bytes
recomputed and matched against the SHA-256 commitment rooted in the D-112
ledger (`phase17_notification_wiring_attestation`), with full chain
integrity delegated to the injected verifier. Every refusal class (absent /
raised / wrong schema / incomplete verdict / drifted digest / unrooted /
broken chain) provably leaves the HITL surface untouched — the battery
asserts the stack factory is never invoked and the engine is never
constructed on refusal.

## 2. Runtime profile & the slot-18 registry pin (HIT-02)

The injected census must mark `runtime_profile_verified` and Phases **5–12,
14, 15, 16 and 17** present + VERIFIED + WIRED (slot 14/CRM is deliberately
**not** a census row — D-163). The repo-real seams are asserted importable
and pinned to the D-154 `ENTRY_POINTS` registry:

| Seam | Module | Registry pin |
|---|---|---|
| **HITL service** | `canonical.ai_hitl_service` | **`ENTRY_POINTS[18]` — TAKEN (load-bearing)** |
| HITL ledger engine | `canonical.hitl_engine` | supporting (D-105/D-106/D-108 core) |
| HITL contracts | `canonical.hitl_contracts` | supporting |
| D-027 event store | `services.sync_engine` | supporting (exempt) |

The **load-bearing pin** is the slot-18 seam check: `ENTRY_POINTS[18]` must
equal the repo seam `canonical.ai_hitl_service` exactly as the D-154
cross-walk and the Phase 17 registry fact require. Any drift, absence or
reassignment refuses as **registry drift** before HIT-03 runs
(battery-proven). The PASS run's profile records the pin as
*"slot 18 = canonical.ai_hitl_service (D-154) — TAKEN by this phase (the
final registry ignition)"*.

## 3. HITL contracts & invariants (HIT-03) — through the REAL validators

| Invariant | Mechanism | Evidence |
|---|---|---|
| Ticket-shape gate (fail-closed) | REAL `validate_ticket` | missing required fields, illegal queue types, illegal roles, a CLAIMED ticket without a reviewer ref, a PENDING ticket carrying one, D-114 bounds (`ticket_id` > 128, `payload_ref` > 256), missing logical creation instant — all Class-B **before any durable write** |
| ReviewAction gate (fail-closed) | REAL `validate_action` | **EXPIRED is never a reviewer action** (sweep-only, D-105), illegal decisions, non-`role:`/`agent:` actor refs, MODIFIED without a `payload_override` dict, `payload_override` on a non-MODIFIED decision, D-114 feedback bounds (> 2000 chars) |
| Lifecycle edge matrix | REAL `is_transition_legal` / `LEGAL_EDGES` | 7 legal edges pass (incl. both sweep-only expiry edges); 7 illegal edges refuse (PENDING→APPROVED skip-claim, self-edges, terminal exits — EXPIRED is terminal); terminal vocabulary stable |
| Mock role discipline (D-045) | REAL `can_actor_resolve` | `role:*`/`agent:*` refs only; ROLE_ANY admits owner/publisher/ops but not unknown roles; a wrong role on a pinned ticket refuses; bare names refuse |
| Deterministic escalation ladder | REAL `ESCALATION_TARGET` | any→ops, ops→owner, publisher→owner, owner→escalation |

No probe copies: every gate is the imported `canonical.hitl_contracts`
module (D-105/D-108).

## 4. Dry-run review cycle trace (HIT-04)

Five synthetic tickets over the REAL `HitlEngine` (D-105/D-106/D-108) on the
REAL D-027 parity `EventStore` with the **ephemeral** in-process vault and
**NO reviewer-notification channel bound** (durable tickets + the
hash-chained ledger are the deliverable; reviewers are mock role refs only):

| Step | Result | Telemetry |
|---|---|---|
| START | ok | cycle id `phase18-hitl-probe-0001`, vault backend ephemeral-in-process |
| AUTH | ok | reviewer signals: **none** (no channel bound); reviewers `role:*` mock refs only (D-045); **egress: 0** |
| INGEST | ok | the analyst boundary edge (D-166/D-167 handover): a DISPATCHED_TO_HITL insight enters INSIGHT_REVIEW (deterministic SHA-256-derived ticket id, owner role); re-ingestion → `duplicated` (idempotent via `analyst:{insight_key}`); 3 direct-producer tickets (publish gate, order override, expiry probe); a same-id recreation → `DUPLICATE` |
| CLAIM | ok | atomic claim discipline: a wrong-role actor (`role:publisher` on an owner ticket) → `role_forbidden`; the rightful claimant wins → CLAIMED; a second claimant → `not_claimable` (exactly-once claim) |
| RESOLVE | ok | the ingested insight → APPROVED by its claimant; a re-resolve → `not_resolvable` (CLAIMED-only); an EXPIRED reviewer action → **Class-B** (sweep-only); the order override → MODIFIED with the `payload_override` stored durably |
| ESCALATE | ok | the escalated publish-gate ticket: owner → ESCALATED (`escalated_to: escalation` per the ladder); `requeue_escalated` opens the fresh elevated child (PENDING_REVIEW, `required_role: escalation`) — idempotent on requeue; the child is claimed and APPROVED under the elevated role — the escalation LOOP closes |
| SWEEP | ok | deterministic expiration from an INJECTED pure clock evaluator (`created <= L0003`): the stale ticket → EXPIRED durably; resolved/escalated tickets untouched; **no wall clock anywhere** |
| INVALID | ok | 5 malformed payloads refuse Class-B (2 malformed tickets, 3 malformed actions) with **zero ledger rows added** and the open-ticket registry unchanged — fail-closed asserted against durable state |
| LEDGER | ok | the D-108 tamper-evident chains verify for all 5 tickets: exactly 5 durable rows (4 resolutions + 1 expiry), kinds `{resolution, expiry}` |
| VERIFY | ok | egress-marker sweep (`smtp`, `sendmail`, `api_key`, `twilio`, `webhook_url`, `auth_code`, `pan`, `card_number`) clean; the durable store carries ONLY `hitl::` rows (zero cross-surface leakage); vault asserted `_EphemeralHitlVault` **by class** |
| CLEANUP | ok | `phase18-scratch:hitl` artifact deleted, zero residue |

**Vault discipline (D-079 hazard, 5th application):** the HITL vault default
backend claims rows in **live PG** (`hitl.review_tickets` /
`hitl.review_ledger`) or the shared `local/volumes/hitl` JSON files. The
probe injects `_EphemeralHitlVault` — insert/claim/update/get/ledger
semantics identical to `_JsonVault`, ZERO durable footprint — and VERIFY
refuses any non-ephemeral vault by class (battery-proven with a fully
functional file-backed vault: every data check passes, the class check still
refuses, fail-closed). No reviewer-notification emitter exists in the probe;
there is nothing to intercept at the human-surface boundary because no
emitter is reachable.

**Cycle timing:** the HIT-01..HIT-05 ignition cycle ≈ **110 ms** in-process
(including the battery's authentic upstream chain build — real
D-167 → D-166 → … → D-154). Attestation digest `0026f4c94a11872a…`
(full: `0026f4c94a11872af2f433d2f50c997726b5a6ba78fad43f7a6b519138bd779f`),
byte-stable across runs; cycle summary hash `f8cbf5f42d373914…`.

## 5. Security posture

- **Reviewer isolation is structural, not advisory:** the probe binds NO
  notification/dashboard emitter — there is no code path that could reach a
  human surface; decisions live exclusively in durable tickets, the
  append-only ledger and D-027 receipts. The VERIFY step asserts zero
  reviewer signals and sweeps the durable stream for egress markers.
- **Human-only authority is preserved:** every resolution flows through the
  engine's CLAIMED-only, claimant-matched, role-checked path; the mock
  `role:*`/`agent:*` actors are local references (D-045) — no auth backend,
  no real identity, no address is invented or harvested; the battery scrubs
  every output for email/URL/identity markers.
- **D-108 tamper-evidence:** each ticket's ledger is hash-chained (each row
  carries the previous row's hash); `verify_chain` recomputes and compares —
  any mutation of durable decision history is detectable.
- **D-124 redaction:** deep redaction runs over every check detail and the
  emitted attestation with the public commitments (`phase17_digest`,
  `manifest_sha256`) restored after redaction; canary scrubs green.
- **Purity (AST-pinned):** no network/db/shell imports or spawn calls in the
  engine; injected store/vault transports only; no wall clock in the core
  (sweeps evaluate an injected pure clock over durable logical timestamps).

## 6. Verification & battery

- New battery **44/44 ×2** (HIT-01 refusal classes with the zero-engine-call
  proof, slot-18 registry-pin drift, slot-14-not-required census proof,
  REAL-validator rejection matrices (ticket + action), direct contract
  probes: lifecycle matrix, role discipline, escalation ladder, direct
  engine cycle over the REAL store — claim race, escalation loop, expiry
  sweep, tamper-evident chains —, emission contract, redaction scrubs, AST
  purity audits).
- Full regression **2175/2175 ×2 consecutive green across 83 modules**
  (2131 + 44), zero bad, zero skipped (the 82 pre-existing modules still
  carry exactly 2131). Heavy chunks: the live-PG cluster (≈ 595 s) and
  `test_phase26_dr_closeout` (≈ 460 s) dominate wall-clock; the full-suite
  invocation is ≈ 25 min.
- **Invocation contract:** the battery must run from the repository **root**
  (`python3 -m unittest local.tests.…`) — environment contract, not a
  regression. Engine-local Docker stack verified healthy (5/5 containers)
  before the live-PG chunks.

## 7. Program completion boundary — the Live Wiring registry is fully ignited

Verified and inherited by the completion reconciliation:

- **Every registry slot is now dispositioned:** slots 5–13 and 15–17
  VERIFIED/WIRED by Phases 5–16 (D-155–D-166), slot 14 closed
  CRM-not-needed (D-163), and slot 18 TAKEN by this phase (D-168) — the
  final ignition.
- **The HITL convergence point is live in dry-run:** dispatched analyst
  insights (D-166) ingest into INSIGHT_REVIEW idempotently; admitted DLQ
  items (D-091) and every other queue type enter through the same
  fail-closed `create_ticket` gate; every decision lands in the D-108
  tamper-evident ledger. The review surface is verified, NOT opened — no
  human notification channel exists and none may be bound until an owner-
  gated phase explicitly injects one.
- **The next milestone is program-level:** the Live Wiring completion
  reconciliation (all-slot census against the D-154 certificate, the full
  attestation chain D-154 → … → D-168 re-verified), then the standing
  owner gates: controlled activation (D-139) and the open provider
  decisions 10/11.

The D-163 disposition stands: no CRM exists or is planned; slot 14 remains
bound to the existing `commerce.sync_orchestrator` facade.

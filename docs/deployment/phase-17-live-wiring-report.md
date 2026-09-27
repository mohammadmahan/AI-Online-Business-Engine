# Phase 17 Live Wiring Report — Notification Engine (D-167)

**Attestation:** `phase17.notification_wiring_attestation.v1`
**Verdict:** `PHASE17_IGNITED` (dry-run, dispatch intercepted at the harness
boundary, zero email/SMS/push/webhook egress, zero durable footprint)
**Upstream:** `phase16.analyst_wiring_attestation.v1` (D-166) — digest
`a74345de22bcb30f…` (battery-built chain), rooted in the D-112 ledger row kind
`phase16_analyst_wiring_attestation`, chain intact.
**Engine:** `local/scripts/live_wiring_phase17_igniter.py` (NTF-01..NTF-05)
**Battery:** `local/tests/test_live_wiring_phase17.py` — 44 tests, ×2 green
**Governance:** D-045 / D-052 / D-070 / D-079 / D-089–D-092 / D-124 / D-154 /
D-160 / D-163 / D-166 / §17 / §21.8. Chain: D-154 → … → D-165 → D-166 →
**D-167**.

> **Registry deviation (recorded per the D-160 precedent).** The Phase 17
> tasking named "Registry Slot 18 Notification bound to
> `canonical.notification_engine`". The D-154 cross-walk in fact binds slot 18
> to `canonical.ai_hitl_service` (HITL); the notification surface
> (Phase 14 build record, D-089–D-092) carries **no dedicated registry slot**.
> The notification engine was verified exactly as asked — but slot 18 was
> **not** read or reassigned: NTF-02 asserts the slot-18 registry fact against
> the live D-154 `ENTRY_POINTS` and refuses on any drift from
> `canonical.ai_hitl_service`. The ignition therefore honors the standing
> registry instead of silently rewriting it; the slot-18 (HITL) ignition
> remains its own future phase.

---

## 1. Upstream attestation verification (NTF-01)

The Phase 16 attestation is verified **before any engine call**: schema
(`phase16.analyst_wiring_attestation.v1`), the `PHASE16_IGNITED` verdict, the
manifest binding, and the D-166 attestation's canonical bytes recomputed and
matched against the SHA-256 commitment rooted in the D-112 ledger
(`phase16_analyst_wiring_attestation`), with full chain integrity delegated to
the injected verifier. Every refusal class (absent / raised / wrong schema /
incomplete verdict / drifted digest / unrooted / broken chain) provably leaves
the notification surface untouched — the battery asserts the stack factory is
never invoked and the engine is never constructed on refusal.

## 2. Runtime profile & seams (NTF-02)

The injected census must mark `runtime_profile_verified` and Phases **5–12,
14, 15 and 16** present + VERIFIED + WIRED (slot 14/CRM is deliberately **not**
a census row — D-163). The repo-real seams are asserted importable and pinned
to the D-154 `ENTRY_POINTS` registry:

| Seam | Module | Registry pin |
|---|---|---|
| Notification engine | `canonical.notification_engine` | no dedicated slot (D-089–D-092 build record) |
| Notification contracts | `canonical.notification_contracts` | no dedicated slot (supporting) |
| Notification worker | `canonical.notification_worker` | no dedicated slot (supporting) |
| D-027 event store | `services.sync_engine` | supporting (exempt) |

The **load-bearing pin** is the slot-18 registry fact: the D-154 cross-walk
binds registry slot 18 to `canonical.ai_hitl_service`. Any mismatch — slot 18
absent, drifted, or reassigned to the notification engine — refuses as
**"drifted from the D-154 cross-walk"** before NTF-03 runs (battery-proven in
both directions). This phase pins the seams that exist and leaves slot 18
exactly where the registry holds it.

## 3. Notification contracts & invariants (NTF-03) — through the REAL validator

| Invariant | Mechanism | Evidence |
|---|---|---|
| Contact-metadata gate (fail-closed) | REAL `validate_notification` channel requirements | EMAIL without `subject`, SMS without `phone_ref`, WEBHOOK without `endpoint_ref` — all Class-B **before any queueing** (D-089/D-052); refusal names the missing variable |
| Invalid-class refusal matrix | REAL validator | bad recipient (charset/length), unknown channel, unknown priority, unknown template, template↔channel mismatch (`order.cancelled.v1`×SMS), min-priority floor (`LOW` on a NORMAL-floor template), missing `variables`, missing required template variable, non-ISO `occurred_at` — all refused with named reasons, zero rows |
| D-090 dedup identity | `dedup_key` = SHA-256 over (recipient, channel, template, logical `event_key`) | deterministic (hex64, stable across calls); a changed event key or changed recipient yields a DIFFERENT key — retries of the SAME logical alert collapse, distinct alerts do not; no wall clock, no payload hash |
| Priority policy (pure) | `policy_decision(event, recent_deliveries)` | 14:00 NORMAL → allow; 23:30 NORMAL → defer `quiet_hours` (22–07 local window, event's own offset); 23:30 CRITICAL → `critical_bypass`; 999 recent deliveries → defer `frequency_cap`; no clock read anywhere |
| D-092 outcome vocabulary | `ST_*` / `OUT_*` constants | QUEUED / DELIVERED / FAILED / DUPLICATE_BLOCKED / POLICY_DEFERRED stable; delivered & permanent_failure terminal, transient & rate_limited return to QUEUED |

The registry is REAL: 7 versioned templates across 4 channels
(`order.fulfillment.v1`, `order.cancelled.v1`, `order.shipped.v1`,
`hitl.review_required.v1`, `dlq.item_admitted.v1`, `campaign.published.v1`,
`system.health.v1`), enforced through the imported contracts — not a probe
copy.

## 4. Dry-run notification cycle trace (NTF-04)

Six synthetic notifications over the REAL `NotificationEngine`
(D-089/D-090/D-092) on the REAL D-027 parity `EventStore` with the
**ephemeral** in-process claim backend and **no dispatch transport bound at
all** (the queued records and D-027 receipts are the deliverable):

| Step | Result | Telemetry |
|---|---|---|
| START | ok | cycle id `phase17-notification-probe-0001`, lock backend ephemeral-in-process |
| AUTH | ok | dispatch intercepted (no transport bound); channels exercised as schemas only — no email/SMS/push; **egress: 0** |
| ENQUEUE | ok | probe alert durable QUEUED via the exactly-once vault claim (dedup key returned) |
| DEDUP | ok | a same-logical-alert retry → durable DUPLICATE_BLOCKED (`notifications\|dup\|…\|0` receipt row in the ledger; the loser NEVER dispatches); a distinct logical alert on the same template enqueues independently |
| PRIORITY | ok | a NORMAL alert inside the quiet window → durably POLICY_DEFERRED (`reason: quiet_hours`); a CRITICAL `hitl.review_required.v1` alert at the same timestamp → QUEUED (quiet-hours bypass) |
| OUTCOMES | ok | delivered → DELIVERED (terminal); a **late transient receipt after DELIVERED holds DELIVERED** (terminal stickiness); transient → QUEUED → delivered → DELIVERED retry ladder |
| STATUS | ok | the durable status view rebuilds dedup_key → status from store data alone, matching the driven history exactly (zero drift); the dup receipt is durable ledger evidence |
| INVALID | ok | 6 invalid notifications (missing contact metadata ×3, unknown template, illegal priority, malformed recipient) refuse Class-B with **zero durable rows added** — the fail-closed gate is asserted against the rebuilt view |
| DLQ | ok | a permanent_failure outcome maps the notification to FAILED (the DLQ admission signal, D-091); the canonical DLQ template `dlq.item_admitted.v1` itself enqueues through the same gates (min HIGH, IN_APP/WEBHOOK) |
| VERIFY | ok | egress-marker sweep over the durable event stream (`smtp`, `sendmail`, `api_key`, `twilio`, `webhook_url`, `auth_code`, `pan`, `card_number`) clean; lock backend asserted `_EphemeralNotificationLocks` **by class** |
| CLEANUP | ok | `phase17-scratch:notifications` artifact deleted, zero residue |

**Sandbox discipline (D-079 hazard, 4th application):** the notification lock
default backend claims keys in **live PG** (`notifications.delivery_lock`) or
the shared `local/volumes/notifications/delivery_locks.json`. The probe
injects `_EphemeralNotificationLocks` — acquire/finalize/get semantics
identical to `_JsonLocks`, ZERO durable footprint — and VERIFY refuses any
non-ephemeral backend by class (battery-proven with a fully functional
file-backed backend: every data check passes, the class check still refuses,
fail-closed). No provider adapter exists in the probe; there is nothing to
intercept at the provider boundary because no provider is reachable.

**Cycle timing:** the NTF-01..NTF-05 ignition cycle ≈ **93 ms** in-process
(including the battery's authentic upstream chain build — real
D-166 → D-165 → … → D-154). Attestation digest `048952dc580d9add…`
(full: `048952dc580d9add47293335cd72cb49526aa6894c96e23bf4eff1e4f99bf826`),
byte-stable across runs; cycle summary hash `5446c437ab596ef0…`.

## 5. Security posture

- **Interception is structural, not advisory:** the engine is constructed
  with NO dispatch transport — there is no code path in the probe that could
  emit email/SMS/push/webhook traffic; outcomes are recorded as D-027
  receipts exactly as the worker would record provider results.
- **Exactly-once delivery protection holds under probe:** the vault claim is
  acquired before any QUEUED record; the blocked retry is durable evidence
  (`DUPLICATE_BLOCKED`), and the status view keeps the winner's terminal
  state — the loser never dispatches.
- **D-124 redaction:** channel contact metadata (`subject`, `phone_ref`,
  `endpoint_ref`) is validated as PRESENT-OR-REFUSE and never echoed into any
  emitted record; deep redaction runs over every check detail and the emitted
  attestation with the public commitments (`phase16_digest`,
  `manifest_sha256`) restored after redaction; the battery scrubs every
  output for canaries and channel-secret markers.
- **Purity (AST-pinned):** no network/db/shell imports or spawn calls in the
  engine; injected store/lock transports only; no wall clock in the core
  (every instant is the event's own recorded timestamp — quiet hours and
  frequency windows computed from event data).

## 6. Verification & battery

- New battery **44/44 ×2** (NTF-01 refusal classes with the zero-engine-call
  proof, slot-18 registry-fact drift both directions, slot-14-not-required
  census proof, REAL-validator rejection matrix, direct contract probes:
  contact metadata, dedup identity, policy matrix, quiet-hours window,
  template discipline, direct engine cycle over the REAL store, emission
  contract, redaction scrubs, AST purity audits).
- Full regression **2131/2131 ×2 consecutive green across 82 modules**
  (2087 + 44), zero bad, zero skipped; per-chunk counts identical across runs
  and reconciled to the untouched-module invariant (the 81 pre-existing
  modules still carry exactly 2087 tests). Chunk layout (module 18 = the new
  battery): 531 / 297 / 206 / 98 / 154 / 71 / 14 / 72 / 231 / 200 / 213 / 44.
  Heavy chunks: the live-PG cluster (≈ 549 s) and `test_phase26_dr_closeout`
  (≈ 457 s) dominate wall-clock; the full-suite invocation is ≈ 24 min.
- **Invocation contract:** the battery must run from the repository **root**
  (`python3 -m unittest local.tests.…`) — environment contract, not a
  regression.
- Engine-local Docker stack verified healthy (5/5 containers) before the
  live-PG chunks — the 13 live-PG tests skip silently otherwise.

## 7. Handover to Phase 18 — HITL service (registry slot 18)

Verified and inherited by the next phase:

- The notification surface is *verified, not opened*: alerts are enqueued,
  policy-gated, dedup-protected and receipted in dry-run; no channel adapter
  is bound and none may be until a wiring phase explicitly injects one behind
  the provider-neutral `ChannelAdapter` boundary (D-091).
- The DLQ contract is proven at the gate level: permanent failures map to
  FAILED and `dlq.item_admitted.v1` (min HIGH) is the canonical alert
  template — the DLQ→HITL materialization edge (D-028/D-050) is the natural
  seam where the notification surface meets slot 18.
- The final registry path is unchanged and now doubly confirmed: slot 18
  (HITL, `canonical.ai_hitl_service`) is the last ignition, under the D-154
  mapping — this phase asserted the fact rather than reassigning the slot.

Phase 18 entry criteria: ignite the HITL service over the Phase 16 analyst
boundary (dispatched insights) with the same fail-closed attestation
recursion, then the program-level completion reconciliation. The D-163
disposition stands: no CRM exists or is planned; slot 14 remains bound to the
existing `commerce.sync_orchestrator` facade.

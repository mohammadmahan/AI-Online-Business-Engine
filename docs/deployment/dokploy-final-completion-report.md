# Dokploy Deployment Track — Final Completion Report & Transition to Live Wiring

**Task:** D-154 — Dokploy Final Deployment Completion Attestation &
Transition to Live Wiring
**Date:** 2026-09-25
**Status:** Infrastructure provisioning program (Stages B–H) CLOSED.
Live Wiring (Phases 5–18) READY TO IGNITE — every ignition step
remains owner-gated (D-045/D-139, plan §17/§21.6).

---

## 1. The completion certificate

`local/scripts/dokploy_completion_attestation.py` synthesizes the
entire lifecycle into the canonical
**`dokploy.completion_attestation.v1`** — an immutable certificate
whose SHA-256 **`attestation_digest`** binds every stage digest, the
D-112 anchoring summary, and the Phase 5–18 readiness census into one
verifiable declaration. Exactly one audited certificate is emitted
per run, including refusals (which declare
`INFRASTRUCTURE_INCOMPLETE` with the failing check named).

| Field | Bound commitment |
| --- | --- |
| `manifest_sha256` | The Stage D compose manifest fingerprint (the deployment identity) |
| `bundle_hash` | The D-147 owner-authorized cutover bundle |
| `acceptance_fingerprint` | The D-149 Stage G acceptance clearance |
| `probe_digest` | The D-150 live-probe execution evidence |
| `closure_digest` | The D-152 Stage G closure seal (Stage H entry root) |
| `activation_digest` | The D-153 Stage H activation record |
| `chain` | D-112 anchoring: zero breaks + all five stage commitments rooted |
| `live_wiring` | The Phase 5–18 entry-point readiness census, runtime-profile-verified |

Attestation rules (all fail-closed; every refusal names its blocker):

- **DEP-01 — lifecycle chain:** each Stage C→H artifact is present
  AND re-verified against its own engine's checks (host READY,
  manifest⇔envelope binding for `stage-e-cutover`, bundle
  hash-verifying with its Stage F owner token, ACCEPTED + PROBES_
  ACCEPTED + LAUNCH_EVIDENCE_COMPLETE, seal STAGE_G_CLOSED, record
  CUTOVER_EXECUTED). Missing, forged, altered, or unbound stages
  refuse by name.
- **DEP-02 — zero drift:** ONE manifest SHA-256 across envelope,
  manifest bytes, bundle, acceptance, probe, seal and activation
  record; the configuration-digest chain recomputed byte-exactly
  from first principles; the probe-to-acceptance binding intact.
- **DEP-03 — D-112 anchoring:** the chain verifier (the real
  `ControlPlaneEngine.verify_chain()`) reports zero breaks, and all
  five stage commitments appear in the ledger rows.
- **DEP-04 — Live-Wiring readiness:** every Phase 5–18 entry point
  present + verified + wired, bound to the verified runtime profile.
- **DEP-05 — certificate:** the canonical artifact with the
  `attestation_digest` declares `INFRASTRUCTURE_COMPLETE` and READY
  FOR SERVICE IGNITION — a declaration only; it never executes
  anything.

Purity: AST-pinned pure core — injected providers, zero sockets,
zero subprocess, zero wall clock; deep redaction (D-124) over checks
and embedded summaries with the public digest commitments restored;
the readiness census is data-minimized to structural fields.

---

## 2. Stage B→H closure — what the track delivered

| Stage | Decision | Artifact | Engine (fail-closed rules) |
| --- | --- | --- | --- |
| B | D-141 | `docs/deployment/dokploy-plan.md` + runbooks | Governed, documentation-first integration plan; staged adoption A–H |
| C | D-143 | `stage_c_runbook_validator.py`, VC-01..VC-14 | Host prerequisites: OS/kernel/Docker floors, gateway-port collisions, public-binding refusals, G1–G5 owner attestations |
| D | D-144 | `stage_d_compose_generator.py` | GENERATED compose manifest; `backend` network `internal: true`, zero published ports; sole edge attachment on `app-orchestrator`; `${VAR:?}` secret references only |
| E | D-145 | `verify_cutover_readiness.py` V-01..V-09 | Cutover matrix incl. V-08 byte-exact manifest fingerprint envelope binding and V-09 healthcheck⇔`infra_health_probe` parity |
| F | D-146/D-147 | `owner_approval_gate.py`, `cutover_orchestrator.py` | Single-use context-bound HMAC owner token (TTL, nonce burn, replay refusal); V-01..V-10 ordered transaction → immutable `cutover.bundle.v1` |
| G | D-148–D-152 | preflight, acceptance, live-probe, adapter, triad, closure engines | G-01..G-04 preflight, ACC-01..04 acceptance, GA-1..GA-7 live probes, TRIAD-01..04 triple evidence, CLS-01..05 closure seal |
| H | D-153 | `stage_h_cutover_executor.py` | H-01..H-05: seal + owner token + environment assertions → ACTIVE transition + `stage_h_activation_record.v1` + critical-window rollback payload |

**The cryptographic continuum:** every stage consumes the previous
stage's digest and emits its own over canonical bytes —

```
host(C) → manifest(D) ⇔ envelope(D)
        → bundle_hash(E/F, embeds manifest fingerprint + owner token)
        → acceptance_fingerprint(G, embeds manifest + template + bundle)
        → probe_digest(G, embeds manifest + acceptance fingerprint)
        → closure_digest(G, embeds all of the above)
        → activation_digest(H, embeds manifest + closure_digest + token)
        → ATTESTATION_DIGEST (embeds everything + D-112 anchoring)
```

Drift anywhere breaks every downstream digest — zero drift is not
asserted, it is RECOMPUTED.

---

## 3. Verified runtime profile (the ignition baseline)

The certificate binds Live-Wiring readiness to THIS evidence:

- 5/5 engine-local stack healthy (postgres, mysql, n8n, minio,
  wordpress) with healthchecks mirroring `infra_health_probe.py`
  semantics (D-144);
- `infra_health_probe.py`: pg_exec, redis_ping, worker_heartbeat,
  telemetry_state, `deploy_verdict()`;
- `canonical/obs_health.py` ProbeRegistry + `seed_registry.py` q()
  (host psql → `docker exec engine-local-postgres psql -U
  engine_local -d business_engine_local`);
- `launch_attestation.py run_attestation()` renders **GO** over the
  D-121 evidence + D-112 chain + D-151 triad;
- Stage H activation executed with zero unmapped port exposure
  (backend services publish NOTHING; the edge terminates 80/443).

---

## 4. Transition guide — Live Wiring (Phases 5–18)

### 4.1 What ignition means

Infrastructure provisioning proved the stack runs, is isolated, is
observed, and is rollback-armed. **Ignition** connects the
application seams to that stack — credentials leave the owner-gated
envelope, webhooks start receiving, adapters start calling — under
the SAME governance: each phase's first live connection is an owner
decision (D-045), each external call rides an injected transport
with a deterministic mock fallback, and nothing the engine does is
self-authorizing.

### 4.2 The services ignition order

Phase 5 (n8n Foundation) first — it owns the credential vault,
webhook conventions, error routing, retries, idempotency and
logging every later phase consumes:

1. **Phase 5 — n8n Foundation** → `canonical.n8n_webhook_contracts`
   (D-053–D-056): webhook contracts, HMAC auth, deterministic
   dispatcher, error routing, HITL dead-letters; point the live n8n
   instance at the attested stack and run the opt-in live probe.
2. **Phase 6 — Notion Business OS** → `canonical.notion_contracts`
   + `src/integrations/notion_adapter.py` (D-060 seam): the
   D-045-gated `LiveNotionClient` (byte-equal mapping, 3 req/s pacer,
   token redaction) ignites read-only first.
3. **Phases 7–8 — AI Runtime & AI Product Manager** →
   `canonical.ai_runtime`, `canonical.ai_proposal_lifecycle`
   (D-062/D-066 seam): DeepSeek + local-Ollama adapters,
   ProviderChain with terminal mock fallback, budget ceilings
   (D-063), prompt-template registry; live AI credentials remain
   D-045-gated.
4. **Phases 9–10 — Instagram & Telegram** →
   `src/publishing/instagram.py`, `canonical.telegram_ingress` /
   `telegram_publisher.py` (D-069..D-072, D-073..D-076): Graph API
   state machine + Bot API contracts on the D-075/D-076 seams;
   `*_LIVE_ENABLED` gates stay closed until the owner flips them.
5. **Phases 11–12 — Order Management (repo record D-081–D-084) &
   Cross-Platform Orchestration** → `canonical.oms_engine`,
   `canonical.orchestration_engine`: the transactional outbox, the
   fan-out lifecycle, PG PK-as-lock anti-race, reconciliation
   worker — the business engine's durable spine.
6. **Phases 13–16 — Commerce & workspace sync, scheduling** →
   `src/commerce/sync_orchestrator.py`,
   `canonical.scheduling_engine`, `canonical.notification_engine`,
   `canonical.budget_engine`: WooCommerce/Notion facades, content
   calendar, notifications, payment ceilings.
7. **Phases 17–18 — Analytics, AI Business Analyst, HITL** →
   `canonical.analytics_engine`, `canonical.analyst_engine`,
   `canonical.ai_hitl_service`: the learning loop closes — campaign
   correlation feeds Phase 7/8 prompts; HITL approval queues gate
   every dispatch.

### 4.3 Entry-point readiness registry (DEP-04)

The attestor ships the canonical census
(`ENTRY_POINTS` + `LIVE_WIRING_PHASES`); the wired readiness
provider reports each `{phase, name, entry_point, present, verified,
wired}`. The certificate refuses unless all 14 phases report ready
AND `runtime_profile_verified` is true.

> **Phase-number cross-walk (MASTER_PLAN §13 ↔ repository records).**
> From Phase 10 onward the two numberings diverge; the registry binds
> each phase number to the repository's REAL seam, and the closure
> report is authoritative for the mapping:
>
> | Phase | MASTER_PLAN §13 label | Repository seam (ignition module) |
> | --- | --- | --- |
> | 5 | n8n Foundation | `canonical.n8n_webhook_contracts` |
> | 6 | Notion Business OS | `canonical.notion_contracts` |
> | 7 | AI Runtime | `canonical.ai_runtime` |
> | 8 | AI Product Manager | `canonical.ai_proposal_lifecycle` |
> | 9 | Instagram | `src/publishing/instagram.py` |
> | 10 | AI Sales Agent | `canonical.telegram_ingress` (Telegram = repo Phase 10 record) |
> | 11 | Order Management | `canonical.oms_engine` (repo Phase 12 record, D-081–D-084) |
> | 12 | Payment | `canonical.oms_contracts` (payment verification inside the OMS spine) |
> | 13 | Shipping | `canonical.orchestration_engine` (repo Phase 11 record) |
> | 14 | CRM | `src/commerce/sync_orchestrator.py` (CRM-not-needed rule: separate CRM only if Woo+Notion+n8n are insufficient) |
> | 15 | Marketing Automation | `canonical.scheduling_engine` |
> | 16 | Analytics | `canonical.analytics_engine` |
> | 17 | AI Business Analyst | `canonical.analyst_engine` |
> | 18 | Human-in-the-Loop | `canonical.ai_hitl_service` |

### 4.4 How the hardened infrastructure carries the phases

- **Isolation → Phase 5/9/10 webhooks:** the backend network has no
  published ports; webhooks terminate at the edge attachment only.
  Every ingress contract (n8n HMAC, Telegram secret-token
  verification) was built against exactly this topology.
- **Probe parity → Phase 5–18 health:** every container healthcheck
  maps onto an `infra_health_probe.py` semantic (V-09), so the
  per-phase live probes reuse the same registry
  (`wire_into_registry`) rather than inventing new health surfaces.
- **Owner tokens → every ignition step:** the D-146 single-use token
  pattern generalizes: each phase's first live connection mints a
  context-bound token (scope = the phase's resource fingerprint),
  burns the nonce once, and lands the decision in the D-112 chain.
- **Rollback posture → every phase:** the Stage E RB-1..RB-6 matrix
  and the Stage H rollback payload remain armed during Live Wiring;
  a red probe in any phase arms the same atomic payload — stop new
  work, compensate/drain, reconcile.
- **SSOT & ledger:** every phase writes through the D-055
  PostgreSQL SSOT and appends evidence to the D-112 chain — the
  completion certificate's anchoring discipline is the SAME
  discipline each phase's evidence uses.

### 4.5 Ignition checklist (per phase)

1. Owner mints the phase's D-145-style context token (fingerprint of
   the phase's resource/config bundle).
2. Flip the phase's `*_LIVE_ENABLED` gate; run the phase's opt-in
   live probe (read-only first).
3. Watch the critical window with the existing probe registry; a red
   probe arms the RB-1 rollback payload.
4. Append the phase's ignition evidence to the D-112 chain; the
   completion certificate remains re-computable at any time by
   re-running the attestor over the live chain.

---

## 5. Governance — what stays owner-gated

- **D-045:** every external credential/connection stays behind an
  explicit owner gate; the certificate contains no credentials.
- **D-139:** the burn-token kill switch remains the sole runtime
  activation authority; the engine never mutates the live stack on
  its own authority.
- **Plan §17/§21.6:** per-stage/per-phase owner authorization; the
  completion certificate AUTHORIZES NOTHING — it is evidence.
- **Re-attestation:** the attestor is re-runnable at any time over
  the live D-112 chain; drift between a stored certificate and a
  fresh re-run is itself a finding.

## 6. Verification record

- Battery `test_dokploy_completion_attestation.py` **38/38 ×2** —
  full pass across the authentic Stage C→H chain (real Stage D
  manifest+envelope, real Stage F gate mint→evaluate→burn, real
  D-149/D-150/D-151/D-152/D-153 producers); rejection of every
  missing/forged/altered stage, digest drift, unrooted commitments,
  broken chains, Live-Wiring readiness failures; redaction scrubs;
  AST purity audits.
- Full regression **1606/1606 ×2 consecutive green across 70
  modules** (1568 + 38), zero skips, census machine-reconciled
  identical.
- Register: DECISIONS.md D-154 (row 56); TODO.md Stage H entry;
  dokploy-plan.md §47.

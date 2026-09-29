# Launch Candidate Handoff — Infrastructure Deployment & Staging Orchestration

**Date:** 2026-09-29 · **Handoff trigger:** owner sign-off on the D-169 Live Wiring
Program closeout record (attestation digest `c30d3047d28d6c69…`, 17/17 rule checks
PASS) — recorded as **D-170**. The Live Wiring track (Phases 5–18) is OFFICIALLY
CLOSED. This document specifies the operational prerequisites for the next phase:
**Infrastructure Deployment & Staging orchestration (Dokploy Stage C rollout and
beyond).**

---

## 1. What is being handed off

The verified, sealed **Launch Candidate**: the engine-local system with the full
Live Wiring program (registry slots 5–18) dispositioned and program-verified.

| Item | Value |
| --- | --- |
| Program attestation | `live_wiring.completion_reconciliation.v1` — verdict `PROGRAM_RECONCILED` |
| Attestation digest | `c30d3047d28d6c69e4cbdf0cc9738a2a71440d63bab9b55d062ded033007c5d7` (byte-stable) |
| Chain digest | `97d88f42e826211c011889daef1261ada8f4ee85de57f5486201cb2052b13457` |
| Chain verified | D-154 → … → D-168, 14 attestation digests byte-exact, rooted in the D-112 ledger, linkage unbroken |
| Slot census | 12 rows (5–12, 15–18) VERIFIED/WIRED; slot 14 SEALED (D-163, CRM-not-needed); slot 18 LOCKED to `canonical.ai_hitl_service` (D-168) |
| Invariants | zero durable footprint · HITL-only rows · ZERO human-surface egress · egress-marker sweep clean · AST purity |
| Closeout report | `docs/deployment/phase-19-reconciliation-report.md` |

**Deployment tooling state:** Dokploy Stages A–B VERIFIED; Stages C–H READY
(runbooks + harnesses proven offline/local, `local/infra/dokploy/` artifacts
committed). **Nothing installed, provisioned, connected, or deployed.** Optional
nightly cron drift-check tool REJECTED by owner disposition (D-170) — the engine
stays a sealed Launch Candidate with zero unnecessary tooling drift.

## 2. Verified state at handoff

- Repository tree **clean and in sync** with `origin/main` at `fb0890c`.
- Full regression **2226/2226 ×2 green across 84 modules**, zero fails, zero skips
  (2175 Live-Wiring + 50 reconciliation + 1 clean-tree GO counter-pin, `eaefa3b`).
- Engine-local stack 5/5 healthy (postgres, n8n, minio, mysql, wordpress).
- V-01..V-09 cutover verification matrix green (technical clearance only).

## 3. Operational prerequisites — Stage C (VPS provisioning)

Execution is **owner-gated at every step**: per-item grants per plan §21.6
(D-141); D-139 remains the sole production-activation authority. The
**authoritative signable grant checklist** is
`docs/deployment/stage-c-owner-grants.md` (SC-1..SC-12 — the atomic
enumeration; §21.6 item 1 expands into six separate per-item grants). The
following list is the collapsed summary of the same grants:

1. **VPS authorization** — provision the host and connect it to the program.
2. **Installer grant** — run the pinned Dokploy installer on the target host.
3. **Firewall authorization** — apply the UFW/SSH hardening baseline.
4. **GitHub connect** — authorize repository connectivity from staging.
5. **Staging DNS** — delegate the staging hostname.
6. **Backup credentials** — supply credentials for the volume backup/retention
   template (`docs/deployment/staging-volume-backup-policy.md`).
7. **RPO/RTO approval** — sign off the staging recovery objectives.
8. **Operator-access & webhook decisions** — who may touch the VPS; which
   webhooks exist.
9. **Edition pinning** — fix the Dokploy edition.

**Host floors** (`docs/deployment/stage-c-readiness.md`, derived from the
validated 3328 MiB / 4.0 CPU ceilings): ≥ 6 GiB RAM, ≥ 2 vCPU, ≥ 40 GB disk,
cgroup v2, Docker ≥ 24; UFW/SSH baselines; a 9-key credential inventory with
D-045 fail-closed secret hygiene (no real secret values in the planning shell).

**Stage C execution order** (all fail-closed, exit 0/1/2):
1. `local/scripts/validate_vps_target.py` — offline plan verification, then the
   opt-in READ-ONLY SSH target probe behind a pinned command allowlist.
2. `local/scripts/validate_vps_readiness.py` — battery-pinned read-only probe.
3. `docs/runbooks/dokploy-vps-provisioning.md` — G1–G6 owner gates, pinned
   installer, initial security config, rollback; verification log starts EMPTY
   and fills only with executed evidence.

## 4. Post-provisioning ladder (each stage gated on the previous)

| Stage | Gate | Key instruments |
| --- | --- | --- |
| D — staging deploy | health-gated per-tier launch, abort gates | `stage-d-staging-runbook.md`, `bootstrap_staging.py` (transport guard: only `engine-staging-*` DB targets), `run_staging_smoke_tests.py` |
| E — cutover readiness | V-01..V-09 fail-closed; DIRTY tree refuses; `--edge` probe folds into D-138 MON-001 | `verify_cutover_readiness.py`, `stage-e-cutover-runbook.md` (RB-1..RB-6 rollback matrix) |
| F — authorization gate | SF-1..SF-7 blocking owner authorizations; single-use commit-bound tokens (D-146/D-147); honest default unsigned ⇒ rc 1 | `owner_approval_gate.py`, `verify_cutover_readiness.py --stage-f`, `cutover_orchestrator.py` (`cutover.bundle.v1`) |
| G — acceptance | GA-1..GA-7 probes, two-cycle ACCEPTED/REJECTED protocol, rollback interlock; requires a READY bundle **plus** an explicit owner command; nonce burn survives restarts (D-148) | `stage-g-acceptance.md`, `stage_g_preflight_validator.py`, `pg_replay_store.py` |
| H — vendor exit | I1–I5 zero-lock-in invariants; prove-before-teardown | `stage-h-vendor-exit.md`, `verify_vendor_exit.py` |

## 5. Standing invariants at handoff (unchanged)

- **GitHub push ≠ production authorization.** Release governance holds.
- **D-139 is the sole activation authority** (preflight → dry run → canary →
  observation → promotion — a separate, explicit, one-time owner decision).
- **D-045 secret hygiene:** no live credentials exist or are requested at this
  boundary; every channel verified-NOT-opened.
- **Provider decisions 10/11 remain open:** Iranian payment and shipping
  provider selection is required before payment-capture / shipping-purchase
  go-live.
- Fail-closed posture on every ignition path; local-first sandbox isolation
  (D-053); backups supplement (never replace) D-125/drills; mandatory exit
  drill preserves the Phase 24 lock-in goals.

## 6. Reference artifacts

- Plans/runbooks: `docs/deployment/dokploy-plan.md`,
  `docs/deployment/stage-c-owner-grants.md` (SC-1..SC-12 signable grants),
  `docs/runbooks/dokploy-{deployment,disaster-recovery,exit-plan}.md`,
  `docs/runbooks/dokploy-vps-provisioning.md`,
  `docs/deployment/stage-c-readiness.md`, `docs/deployment/stage-d-staging-runbook.md`,
  `docs/deployment/stage-e-cutover-runbook.md`,
  `docs/deployment/stage-e-cutover-fingerprint-binding.md`,
  `docs/deployment/stage-f-authorization.md`,
  `docs/deployment/stage-f-attestation-orchestration.md`,
  `docs/deployment/stage-g-acceptance.md`, `docs/deployment/stage-h-vendor-exit.md`,
  `docs/runbooks/staging-disaster-recovery.md`.
- Infrastructure: `local/infra/compose.staging.yml`, `local/infra/compose.prod.yml`,
  `local/infra/dokploy/` (stage map, SSOT/redis env contracts, orchestrator skeleton).
- Verifiers: `validate_staging_compose.py`, `validate_vps_target.py`,
  `validate_vps_readiness.py`, `validate_staging_health.py`,
  `validate_dokploy_runtime.py`, `runtime_preflight.py`,
  `verify_cutover_readiness.py`, `cutover_orchestrator.py`,
  `stage_g_preflight_validator.py`, `verify_vendor_exit.py`.

# Stage C Runbook — Deployment Orchestration Scaffold (G1–G6)

**Status: SCAFFOLD — not executed.** Every step below is owner-gated; this
document orchestrates the stage and inherits the authoritative G1–G6 gate
definitions from `docs/runbooks/dokploy-vps-provisioning.md` §0 verbatim
(it defines them; this file sequences them end-to-end and binds each to
its SC grant). Execution begins ONLY when the machine grant gate passes:
`python3 local/scripts/verify_stage_c_grants.py` → exit 0 (all twelve
SC-1..SC-12 rows signed in
`docs/deployment/stage-c-owner-grants.md`).

**Nothing here touches production activation** — that is D-139's sole,
separate authority. D-045 holds throughout: credential values never enter
this repository or the planning shell.

## 1. Gate-to-grant cross-walk

The provisioning runbook's G1–G6 gates and the grant checklist are the
same authorizations at two levels of detail:

| Gate | Provisioning-runbook definition | Grant rows | Pre-filled value |
|------|--------------------------------|------------|------------------|
| G1 | VPS provisioning (provider, size, region) | SC-1 + SC-11 | sizing 4 vCPU / 8 GB RAM / 50 GB NVMe |
| G2 | Installer execution (pinned) | SC-2 + SC-10 | — version pin open |
| G3 | Firewall ports opening | SC-3 | 18080 or approved proxy surface |
| G4 | GitHub connection (read-scoped) | SC-4 | read-only, this repo only |
| G5 | Staging DNS record | SC-5 | — hostname open |
| G6 | S3/backup credentials | SC-6 + SC-7 | RPO 6h/24h · RTO 2h/4h · retention 30/8/6 + 14d |

Non-gate decisions riding the same checklist: SC-8 operator access model
(pre-filled `TUNNEL`), SC-9 deploy trigger model (pre-filled `MANUAL`),
SC-12 stateful-service choice (pre-filled `DOCKER_NAMED_VOLUMES`).

## 2. Pre-execution gate chain (all fail-closed, exit 0/1/2)

**Single entry point:** `local/scripts/stage_c_runbook.py` executes the
chain sequentially (G1 env lint → G2 preflight clearance → G3 network
boundary → G4 stack ping → G5 acceptance suite → G6 attestation token
on unanimous pass) and aborts at the first non-pass gate. The steps
below document what each stage runs; the runner automates steps 1–5.

1. **Grant gate** — `verify_stage_c_grants.py` must exit 0.
2. **Dry-run clearance** — `local/scripts/stage_c_dry_run.py` simulates
   the G1–G6 sequence over three artifacts (grants checklist, staging
   manifest, the fill-in `.env.staging.template`): env-contract keys,
   strict D-045 placeholders, the G-B4 no-AI-credential rule,
   one-published-port / internal-`data` isolation, named-volume
   declarations, and SC-5/SC-7 value consistency. Emits
   `stage_c.dry_run_clearance.v1` (probe-compatible with
   `qa.launch_attestation.v1`); exit 0 required; mutates nothing.
3. **Stage acceptance rehearsal** — `local/scripts/stage_c_acceptance.py`
   probes all five planes on the sanctioned engine-local rehearsal
   stack (schema readiness, read-only event-store, MySQL/Woo ping, the
   MediaStoreContract round-trip with zero residue, tunnel-only n8n
   health with public-exposure refusal, decision-ledger
   consistency-only) — synthetic data only, stack-identity guarded,
   `stage_c.acceptance_run.v1` emission; exit 0 required.
4. **Target validation** — `validate_vps_target.py --require-grants`
   (offline plan verification; add `--host` only for the opt-in read-only
   SSH probe). With the flag, an unsigned checklist refuses the run
   (exit 2) before any check executes.
5. **Readiness probe** — `validate_vps_readiness.py --require-grants
   --host <HOST> --user <ADMIN_USER>` (read-only, battery-pinned
   no-mutation guarantee; the grant gate precedes any SSH attempt).
6. **Provisioning execution** — `docs/runbooks/dokploy-vps-provisioning.md`
   §4→§8 under its G1–G6 owner messages; the verification log there (§9,
   append-only) and the log in §4 below fill only with executed evidence.

## 3. Execution phases

| Phase | Scope | Gates | Key evidence |
|-------|-------|-------|--------------|
| P1 Host bootstrap | provider/size/region per SC-1+SC-11; UFW + SSH hardening baseline | G1, G3 | provisioning-runbook §2–§3 log rows |
| P2 Dokploy pin install | pinned installer per SC-2; edition + §18 2FA/audit re-verification per SC-10 | G2 | §5 install log, edition string |
| P3 Network & tunnel setup | firewall surface live, GitHub read-connect, DNS record; operator access per SC-8 (`TUNNEL`) | G3, G4, G5 | §6 security-config rows, DNS record ref |
| P4 Named volumes | per SC-12 `DOCKER_NAMED_VOLUMES`; restore preconditions per `staging-volume-backup-policy.md` (destination absent, consumers stopped) | — (SC-12) | volume plan vs `compose.staging.yml` |
| P5 S3 backup integration | isolated minimum-permission credentials (key NAMES only, SC-6); schedule/retention per SC-7; supplement-only vs D-125 (upload ≠ restoration evidence) | G6 | secret-store receipt (names only), schedule config |
| P6 Staging dry-run | launch the staging stack on the host; label-based smoke suite `run_staging_smoke_tests.py` (21/21) must pass; host parity vs `stage-d-staging-runbook.md` health gates | — | smoke output, dry-run report |

Failure at any phase = STOP (§10 stop conditions of the provisioning
runbook): remediation is a separate, owner-gated action; a phase never
self-heals by improvising outside its grant.

## 4. Verification log (append-only — starts EMPTY)

| Phase | Gate(s) | Date | Operator | Evidence reference |
|-------|---------|------|----------|--------------------|
| | | | | |
| | | | | |

A row with no date, operator, and evidence reference is not evidence.
This log plus the provisioning runbook's §9 log form the Stage C evidence
set that Stage D's health gates consume.

## 5. Rollback / removal

Host-level removal follows `docs/runbooks/dokploy-vps-provisioning.md` §8
(pinned uninstall path, host returned to pre-stage state). Per-phase abort
leaves executed phases in place pending an owner decision — partial state
is never silently torn down or silently kept.

## 6. References

- `docs/runbooks/dokploy-vps-provisioning.md` — authoritative G1–G6
  definitions, §4 pre-install validation, §5 install, §8 rollback, §10
  stop conditions.
- `docs/deployment/stage-c-owner-grants.md` — SC-1..SC-12 signable
  checklist (the machine gate's artifact).
- `docs/deployment/stage-c-readiness.md` — host floors derived from the
  validated manifest.
- `docs/deployment/staging-volume-backup-policy.md` — SC-7 schedule and
  SC-12 restore preconditions.
- `.env.staging.template` — the Stage C fill-in environment template
  (strict placeholders, grant annotations; validated by the dry run).
- `local/scripts/verify_stage_c_grants.py`,
  `local/scripts/stage_c_dry_run.py`,
  `local/scripts/stage_c_acceptance.py`,
  `local/scripts/stage_c_runbook.py` (the sequential G1–G6 runner,
  token `stage_c.runbook_attestation.v1`),
  `local/scripts/validate_vps_target.py`,
  `local/scripts/validate_vps_readiness.py` — the fail-closed gate chain.
- Decisions: D-141 (planning + Stages A–B), D-169/D-170 (Launch Candidate
  handoff), D-139 (production activation — untouched by this stage).

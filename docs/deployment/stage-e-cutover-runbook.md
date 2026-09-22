# Runbook: Production Cutover (Stage E — PLANNED, execution owner-gated)

- Work package: **Dokploy Deployment Integration** (D-141, Approved).
- Status: **PLANNED readiness artifact.** Nothing has been deployed,
  cut over, or promoted. This runbook and
  `local/scripts/verify_cutover_readiness.py` are the Stage E
  deliverables; execution requires the per-item owner authorizations
  in `docs/deployment/dokploy-plan.md` §17/§21.6 **and** a D-138
  verdict of GO bound to the exact candidate commit.
- Prerequisites: Stage C host gates passed (`validate_vps_target.py`,
  `validate_vps_readiness.py` exit 0); Stage D staging rehearsal green
  (`run_staging_smoke_tests.py` 10/10 synthetic + stack mode);
  production manifest `local/infra/compose.prod.yml` (§24 validated).

## 0. Authority gates (binding)

- **D-045:** every live credential is handed to the host by the owner
  at deploy time only — never committed, never echoed, never stored in
  the repository. The cutover harness refuses to run while real
  production secret values are present in the operator shell.
- **D-139:** a technical GO is *necessary but not sufficient*.
  Production activation requires preflight → dry run → limited canary
  → observation → an explicit, single-use, context-bound owner
  promotion approval → rollback readiness at every step. Absence of
  failures is never approval.
- **D-141:** SSH/host provisioning, DNS, TLS domains, and backup
  destinations each remain separate owner authorizations.
- **D-138:** the launch attestation (`local/scripts/launch_attestation.py`)
  must report **GO** for the exact candidate commit; a stale or failed
  recheck voids the cutover (fail closed).

## 1. Preflight (all must pass before any container transition)

| # | Check | Evidence |
|---|---|---|
| P-1 | Candidate commit recorded; working tree clean; artifact identity = commit | `git rev-parse HEAD`, `git status --short` |
| P-2 | D-138 attestation GO for this commit (fresh, not stale) | `launch_attestation.py` output + attestation hash |
| P-3 | Backup/restore rehearsal green **and fresh** (D-125) | `resilience_drill` result in the attestation |
| P-4 | Cutover readiness harness exits 0 | `verify_cutover_readiness.py [--stack]` |
| P-5 | Monitoring + escalation available (D-123 probes, Phase 19 audit chain) | attestation monitoring controls |
| P-6 | Owner promotion token issued for THIS commit (single-use) | Phase 19 control-audit record |

## 2. Backup before cutover (D-125; a backup is not valid until a restore has succeeded)

1. `write_snapshot` a point-in-time archive of every durable surface
   from the live PostgreSQL SSOT (canonical drill surfaces only —
   hash-chained `admin.control_audit` is NEVER teardown-eligible; it is
   fully snapshot + rehydrate per D-125/26).
2. `verify_snapshot` the archive (fold re-derivation).
3. Copy the archive **off-host** through the Phase 24
   `MediaStoreContract` boundary (decision-ledger leg already does this).
4. Rehearse restore from THAT archive (Stage D pattern). Until the
   restore folds equal, the backup does not exist as evidence.
5. Declare RPO/RTO for this cutover in the promotion record.

## 3. Transition (honest zero-downtime statement)

- Ordinary `docker compose up -d` recreation is **NOT zero-downtime**.
- Zero-downtime is achieved **only** via the blue/green project swap:
  bring the green stack up under a separate compose project name
  (`COMPOSE_PROJECT_NAME=<candidate>`), wait for 5/5 healthy, switch
  the edge gateway (Traefik/Dokploy) to the green services, keep blue
  stopped (not removed) for the observation window.
- No published host ports on the data plane (manifest §24 verified);
  the edge is the only public surface.
- During cutover the canary ceiling applies (D-127 hard refusal active;
  kill-switch reachable from every step).

## 4. Post-cutover smoke verification

1. `run_staging_smoke_tests.py` synthetic suite against the production
   configuration (mock providers only until each live flag is
   owner-authorized separately under D-045).
2. `--edge` probe: HTTPS redirect + security headers (below).
3. D-123 health probes green; D-121 log ledger appending; Phase 19
   chain verify `ok`.
4. Outbox reconciler (D-080) shows zero stranded receipts.

### Edge header policy (validated by `verify_cutover_readiness.py --edge`)

| Header | Required value |
|---|---|
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` (max-age ≥ 31536000) |
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` or `SAMEORIGIN` |
| `Content-Security-Policy` | present (non-empty) |
| HTTP → HTTPS | 301/308 redirect to https |

These headers are applied at the Traefik/Dokploy edge (plan §8, §22);
the offline harness verifies the *declaration* in this runbook, the
`--edge` mode verifies the *live edge*.

## 5. Rollback Matrix (deterministic triggers; rollback BEFORE cleanup)

| # | Trigger (breach) | Detection | Procedure | Post-verification |
|---|---|---|---|---|
| RB-1 | Any post-cutover smoke check fails | exit ≠ 0 from smoke harness | edge gateway back to blue; green stack `stop` (keep volumes); re-run §4 against blue | smoke green on blue; incident logged to D-121 ledger |
| RB-2 | Edge headers/redirect regress | `--edge` probe exit ≠ 0 | revert edge config to last attested values; re-probe | `--edge` exit 0 |
| RB-3 | D-123 probe red / D-121 ledger stalled | probe registry verdict | stop new work (kill-switch), edge to blue, drain | probes green; zero stranded locks after sweep |
| RB-4 | Outbox/ledger inconsistency or stranded locks | D-080 sweep + chain verify | freeze dispatch (kill-switch), edge to blue, run reconciliation; no forensic deletion | `verify_chain ok`, reconcile report empty |
| RB-5 | Budget breach (D-063/D-127) | budget pacer / hard refusal events | kill-switch; edge to blue if external calls were live | ledger attestation fold unchanged |
| RB-6 | Data corruption suspected | restore drill mismatch | **owner break-glass only**: restore latest verified archive per §2; never on auto | fold-equal verification + incident record |

Ordering invariant: **stop new work first, then compensate/drain,
then reconcile; durable evidence is preserved, never deleted** (D-139).

## 6. Owner signoff checklist (credential handoffs under D-045)

- [ ] Host SSH + sudo granted to operator role for the window only
- [ ] Production secret set injected at deploy time (9 `${VAR:?}` keys — `.env.example` §prod)
- [ ] DNS/TLS domain authorization for the production domain
- [ ] Off-host backup destination credentials (Phase 24 MediaStore)
- [ ] Promotion approval token issued (single-use, commit-bound) — Phase 19 control-audit recorded
- [ ] Break-glass contacts acknowledged
- [ ] Post-window: rotate any credential that transited the operator shell

## 7. Stop conditions (fail closed)

A missing, stale, malformed, negative, or unbindable evidence item is
`NO-GO` — never an assumed pass. The harness
(`verify_cutover_readiness.py`) exits 1 on any finding, 2 when it
cannot assess (missing prerequisites or unreachable edge), and refuses
to run at all while production secret values are present in the
environment (D-045 hygiene).

## 8. References

- Official Dokploy documentation (reviewed 2026-09-22):
  https://docs.dokploy.com — Traefik edge, domain/SSL, deployment
  behaviors; limitations recorded in plan §8/§13.
- Internal: plan §22 (Stage C), §25 (sizing), §26 (Stage D record);
  `docs/deployment/stage-c-readiness.md`; Stage D runbook.

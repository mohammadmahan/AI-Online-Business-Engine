# Stage C Owner Authorization — Signable Grant Checklist (SC-1..SC-12)

**Date issued:** 2026-09-29 · **Status: UNSIGNED** (honest default — an
unsigned checklist blocks Stage C, fail closed) · **Authority:** D-141
(planning + Stages A–B only), plan §17/§21.6 · **Candidate:** `a5e5b67`
(pre-Stage-C technical clearance V-01..V-09 green, see
`docs/deployment/launch-candidate-handoff.md`).

This is the formal, atomic enumeration of the §21.6 Stage C gate checklist.
The Launch Candidate handoff collapses the same requirements into a
nine-line summary; **this artifact is authoritative** — one row per
individually-granted owner decision (§21.6 item 1 expands into six separate
authorizations, SC-1..SC-6).

## 1. Authority and scope

- **What this authorizes:** STAGING infrastructure execution only (Stage C
  VPS provisioning and the staging ladder that follows). It never
  authorizes production activation — **D-139 remains the sole, separate,
  one-time activation authority**, and a GitHub push is not an
  authorization (release governance, plan §17).
- **Fail-closed rules:**
  - Stage C execution (probes and runbook alike) begins only when **every
    row below is signed**. A row with no name, date, and evidence reference
    is unsigned.
  - Each grant is individually revocable; revoking any row suspends Stage C
    at the next gate.
  - Secret values never appear in this artifact or the repository —
    receipts list key NAMES only (D-045).
- **Execution order once fully signed:**
  `validate_vps_target.py` (offline + opt-in read-only SSH probe) →
  `validate_vps_readiness.py` (read-only) →
  `docs/runbooks/dokploy-vps-provisioning.md` under its G1–G6 owner gates —
  the runbook verification log starts EMPTY and fills only with executed
  evidence.

## 2. Sign-off matrix

Every row is blocking: unsigned ⇒ Stage C fails closed.

| # | Grant item | Source | Grant form / evidence | Binding | Expiry / rotation |
|---|------------|--------|----------------------|---------|-------------------|
| SC-1 | VPS provisioning authorized (host acquisition) | §21.6.1 | signed row + provisioning-runbook G1 log entry | window-bound | provisioning window |
| SC-2 | Installer execution — pinned Dokploy installer version only | §21.6.1 | version string recorded in the row + pinned-installer runbook log | version-bound | version change |
| SC-3 | Firewall surface — UFW/SSH hardening baseline; ports 18080 or the approved proxy surface | §21.6.1 | signed row naming the approved port set | host-bound | host replacement |
| SC-4 | GitHub connection authorized from staging | §21.6.1 | signed row + connectivity probe evidence | config-bound | credential rotation |
| SC-5 | Staging DNS delegation | §21.6.1 | registrar/DNS-provider authorization record | domain-bound | 30 days |
| SC-6 | S3/backup credentials supplied (key NAMES only — never values) | §21.6.1 | secret-store receipt listing key names only (D-045) | config-bound | credential rotation |
| SC-7 | RPO/RTO values approved (§21.4 proposals) | §21.6.2 | approved values recorded in the row | plan-bound | plan revision |
| SC-8 | n8n staging operator access model: SSH tunnel (default) vs staging-scoped authenticated domain | §21.6.3, §19 Q8 | decision recorded: `TUNNEL` or `DOMAIN` | decision-bound | Stage C completion |
| SC-9 | Staging deploys: manual-only (default) vs webhook-triggered | §21.6.4, §19 Q8 | decision recorded: `MANUAL` or `WEBHOOK` | decision-bound | Stage C completion |
| SC-10 | Dokploy edition/version pinned (§19 Q5); 2FA/audit capability re-verified against the selected version (§18) | §21.6.5 | edition string + §18 re-verification note | version-bound | edition change |
| SC-11 | Staging host sizing ≥ 2 GB RAM / 30 GB disk floor — the 5-service stack may want more | §21.6.6, §19 Q4 | chosen size recorded; meets or exceeds floors | plan-bound | sizing revision |
| SC-12 | Stateful-service management choice, informed by §21.4 | §21.6.7, §19 Q2 | choice recorded with rationale | decision-bound | Stage C completion |

## 3. Signature block

| # | Granted by (name) | Date | Evidence reference | Notes |
|---|-------------------|------|--------------------|-------|
| SC-1 | | | | |
| SC-2 | | | | |
| SC-3 | | | | |
| SC-4 | | | | |
| SC-5 | | | | |
| SC-6 | | | | |
| SC-7 | | | | |
| SC-8 | | | | |
| SC-9 | | | | |
| SC-10 | | | | |
| SC-11 | | | | |
| SC-12 | | | | |

## 4. Gate exit criteria

- All twelve rows signed ⇒ Stage C is authorized; execution follows the
  order in §1 and every stage remains health-gated and abort-able.
- Stage F authorization (SF-1..SF-7, `stage-f-authorization.md`) is a
  separate, later gate — signing this checklist does NOT pre-authorize it.
- Provider decisions 10/11 (Iranian payment / shipping selection) remain
  open and untouched by this artifact.
- The D-139 activation state machine consumes nothing from this checklist.

## 5. References

- `docs/deployment/dokploy-plan.md` — §17 (release governance), §18
  (2FA/audit), §19 Q2/Q4/Q5/Q8, §21.4 (RPO/RTO proposals), §21.6 (gate
  checklist).
- `docs/deployment/launch-candidate-handoff.md` — verified-state handoff and
  collapsed grant summary.
- `docs/deployment/stage-f-authorization.md` — the later cutover
  authorization gate (SF-1..SF-7).
- `docs/runbooks/dokploy-vps-provisioning.md` — the Stage C runbook these
  grants unlock (G1–G6 gates).
- Decisions: D-141 (Dokploy planning + Stages A–B), D-145/D-146 (V-08/V-09,
  Stage F gate), D-169/D-170 (program closeout and sign-off).

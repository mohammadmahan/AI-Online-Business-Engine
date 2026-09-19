# Runbook: Dokploy Deployment (PLANNED — not yet executable)

- Status: **PLANNED.** This runbook describes procedures that will be
  performed **only after** D-141 approval and the per-stage owner
  authorizations listed in `docs/deployment/dokploy-plan.md` §17.
  Nothing here has been run; no environment exists.
- Authority: `docs/deployment/dokploy-plan.md` (D-141 Proposed),
  Phase 4 brief G1 (hosting gate open), D-139 activation protocol.
- Companions: `dokploy-disaster-recovery.md`,
  `dokploy-exit-plan.md`.

## 0. Preconditions (all must hold — fail closed)

1. D-141 **Approved** by owner.
2. The specific stage's owner authorizations granted (plan §17):
   VPS provisioning, installer execution, firewall ports, GitHub
   connection, credentials, DNS — each separately.
3. Staging compose overlay exists in Git, secret-free, validated by
   the local compose parity check (Stage B exit).
4. Host pre-flight recorded: ≥2GB RAM / 30GB disk (documented
   minimum), ports 80/443/3000 free, Docker present or installer
   will add it, distro on the documented supported list.
5. No production credentials exist anywhere in the target
   environment (D-045); staging uses synthetic data only.

## 1. Environment preparation (Stage C — PLANNED)

1. Provision the approved VPS; record host identity in the
   environment inventory (never secrets).
2. Open ONLY the required ports: 80/443 (Traefik), 3000 (UI — to be
   locked down to VPN/admin IPs immediately after setup).
3. Install Dokploy using the **pinned-version** installer from the
   official GitHub release (documented pattern:
   `https://github.com/Dokploy/dokploy/releases/download/<tag>/install.sh`)
   — never an unpinned latest from the website without review; record
   the version and installer hash in the deployment log (D-121).
4. Create the admin account; immediately: enforce the strongest
   available authentication for the selected edition (2FA/passkeys on
   paid plans — verify in Stage A), restrict UI exposure.
5. Create the staging **project** and **environment** scoping.

## 2. Application onboarding (Stage C — PLANNED)

1. Import the staging compose overlay from Git (staging branch/commit
   pinned by the approval flow).
2. Set environment variables ONLY via the Dokploy environment editor
   — documented behavior: variables are written to a `.env` beside
   the compose file and are **not auto-injected**; either declare
   `env_file` or reference `${VAR}` explicitly in the overlay. The
   overlay must state which pattern it uses (Stage B).
3. Volumes: named volumes only (backup eligibility). Volume names
   will be prefixed by Dokploy as `{appName}_{volumeName}` — record
   the effective names for the DR runbook.
4. Domains/TLS: staging hostnames via Traefik; no production domain
   touches staging.
5. Deploy; record commit SHA + artifact identity into the D-121 log
   ledger (deploy event), per plan §10.5.

## 3. Deploy, redeploy, update (PLANNED)

- Trigger: manual/CLI or staging-scoped webhook only. **Production
  auto-deploy is forbidden** by the release-governance design; a
  GitHub push is never a production authorization.
- Verify after every deploy: service health via the project's
  D-123-compatible probes (not only the Dokploy dashboard), deploy
  identity recorded, no unexpected volume recreation.
- Cancellation: queued deployments can be canceled (documented);
  in-progress ones cannot — plan maintenance accordingly.

## 4. Production promotion (Stage F — PLANNED; D-139 governs)

1. Gate 1 — CI green on the exact commit; artifact identity
   immutable and staged-validated.
2. Gate 2 — D-138 evaluator verdict **GO** for the candidate
   (missing/stale/negative evidence fails closed).
3. Gate 3 — **D-139 one-time owner approval token**, minted and
   burned through the existing activation machinery; recorded in the
   Phase 19 control-audit chain. A Dokploy UI action is never the
   approval.
4. Only then: production deploy of the verified artifact; identity
   (SHA + digest/definition hash) recorded.
5. Post-deploy: run the observability parity checks and record
   `qa.health_report.v1` entry.

## 5. Rollback (application — PLANNED)

- Prefer redeploying the previous verified artifact.
- Application rollback and database rollback are **separate**
  procedures (see DR runbook §4); never combine them implicitly.
- Untested rollback is unsafe by definition: Stage D must rehearse
  rollback with the actual application and database versions before
  any production reliance.

## 6. Stop conditions (any step)

- Any governance control (D-045/D-050/D-053/D-121/D-125/D-137/D-139)
  would be weakened → STOP, report to owner.
- Evidence for a gate is missing, stale, malformed, or negative →
  promotion fails closed.
- Dokploy behavior contradicts the documented assumptions here →
  STOP, re-verify against current official docs, update plan §18
  review date before proceeding.

# Runbook: Dokploy Exit Drill (Stage H — PLANNED, verification procedure)

- Work package: **Dokploy Deployment Integration** (D-141, Approved).
- Status: **PLANNED drill procedure.** No staging host exists. This
  runbook is the executable verification companion to
  `docs/runbooks/dokploy-exit-plan.md` (which maps what lives where
  and why exit is mandatory): it proves **zero vendor lock-in** by
  demonstrating the staging stack runs from plain Docker Compose with
  the Dokploy UI/agent/control plane REMOVED from the path.
- Lock-in rationale (Phase 24, D-129–D-132): a deployment layer that
  cannot be exited is a dependency; this drill is therefore
  **mandatory before Stage E** and re-runs after any significant
  deployment-layer change (exit-plan §5 cadence).

## 1. Drill invariants (what "pass" means)

- I1 — **Manifest self-sufficiency:** `compose.staging.yml` carries no
  deployment-layer fields (no labels, no provider-specific extensions,
  no UI-only settings) and resolves with the plain Docker CLI.
- I2 — **Independence:** with no Dokploy control plane present, the
  full stack comes up from `docker compose -f compose.staging.yml up`
  and serves its health surface.
- I3 — **Data survival:** existing named volumes are consumed as-is —
  a layer migration must not require data migration.
- I4 — **Parity:** the plain-compose deployment passes the same health
  drill used under the layer (`validate_staging_health.py --live`)
  — same probes, same isolation invariants (data internal, gateway-less;
  frontend touches WordPress only).
- I5 — **Reversibility:** after the drill, Dokploy can be reinstalled
  and reattach to the same volumes (exit-plan §3 step-back) — or the
  host can be retired cleanly (§4 of the exit plan).

## 2. Prerequisites

- Staging host exists with the stack deployed (Stage C complete).
- Current backup of all volumes taken and verified off-host
  (staging-disaster-recovery.md §1) — the drill destroys nothing, but
  every host operation starts from a known-good backup.
- Owner awareness logged (this drill changes how the staging stack is
  served; it does not touch production or any data).

## 3. Procedure

1. **Baseline health under the layer:** run
   `python3 local/scripts/validate_staging_health.py --live --host … --user …`
   → exit 0 expected. Record output (the I4 comparison baseline).
2. **Manifest self-sufficiency (I1):** on the host,
   `docker compose -f compose.staging.yml config -q` must pass with the
   plain CLI; locally, the battery's
   `TestStagingManifestStageB`/network tests already assert
   layer-independence fields. Record versions: `docker --version`,
   `docker compose version`.
3. **Remove Dokploy from the serving path (I2):** stop and remove ONLY
   the Dokploy control plane and its Traefik wrapper
   (`dokploy-postgres`, Dokploy app container, its Traefik instance) —
   NOT the compose project containers:
   ```bash
   docker ps --format '{{.Names}}' | grep -Ei 'dokploy|traefik'   # enumerate first
   docker stop <dokploy-control-plane containers>
   docker rm   <dokploy-control-plane containers>
   ```
   Leave application volumes and the compose project untouched (I3).
   Control-plane data volumes may be kept for the reinstall step (I5).
4. **Bring the stack up independently:**
   ```bash
   docker compose -f compose.staging.yml up -d
   ```
   Wait for health; then re-run the health drill (step 1 command) —
   exit 0 expected WITHOUT any Dokploy component running. NOTE: without
   Traefik there is no TLS termination/ingress — in-network and
   localhost probes still pass (that is the point: the app plane is
   independent of the ingress plane). Public serving during the drill
   gap is either accepted (staging) or the owner supplies a plain
   compose-level proxy — both are recorded.
5. **Verify parity & isolation (I4):** health drill exit 0; additionally
   confirm the Dokploy control plane containers are absent from the
   frontend network attachment list (they were never on it).
6. **Prove reversibility (I5):** reinstall Dokploy from the pinned
   installer (runbook §5), reattach/verify the compose project, run the
   health drill once more → exit 0. OR, if exiting permanently: skip
   reinstall and decommission per exit-plan §4. Record which path.
7. **Evidence:** append to this runbook's verification log (§5):
   timestamps, docker versions, `docker ps` before/after, health drill
   outputs, and the I1–I5 checklist with results. A missing evidence
   item = drill FAILED.

## 4. Failure handling

Any invariant failing → STOP; restore serving under the layer
(reinstall/reattach), take a fresh backup, and file the finding. The
drill never trades availability for proof on staging beyond the
announced window, and NEVER runs against production (Stage F gates
production changes behind D-139; the production exit drill is a
separate owner-authorized exercise after staging success).

## 5. Verification log (append-only, operator-maintained)

```
# date | host | docker version | I1..I5 results | evidence refs | operator
# (empty — nothing executed yet; entries only after owner-gated execution)
```

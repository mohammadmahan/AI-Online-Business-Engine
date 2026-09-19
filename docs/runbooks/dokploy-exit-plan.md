# Runbook: Dokploy Exit Plan (PLANNED — not yet executable)

- Status: **PLANNED.** The exit drill is **Stage H** of
  `docs/deployment/dokploy-plan.md` and is mandatory: adopting an
  optional deployment layer that cannot be exited cleanly would
  violate the project's lock-in-reduction goals (Phase 24,
  D-129–D-132) and the architecture principle of building on
  replaceable primitives.
- Guarantee being proven: **the stack remains deployable and
  recoverable WITHOUT Dokploy** — identical data (fold-verified),
  identical topology, no data loss.
- Companions: `dokploy-plan.md`, `dokploy-disaster-recovery.md`.

## 1. What lives where (configuration provenance map)

| Setting class | Location | Reproducible from Git? |
|---|---|---|
| Compose service definitions, volume topology, health checks | Git (`local/infra/docker-compose.yml` + staging overlay from Stage B) | **Yes — always** |
| Environment variables | Dokploy environment editor → written to `.env` beside the compose file (documented behavior; not auto-injected — overlay declares `env_file` or `${VAR}` refs) | No (secret-bearing) — inventory list (names only) kept in Git; values recreated from the secret system during recovery |
| Domains / TLS | Dokploy domains + Traefik (env config, not code — Phase 4 brief G5) | No — recorded in environment inventory; recreated at provider |
| Deploy triggers / webhooks | Dokploy settings | Names only in Git; recreated in Dokploy |
| Backup schedules / destinations | Dokploy → S3 destinations | Schedule definitions in Git (names/cron, no credentials) |
| Business logic / contracts / schemas | Git (canonical code + `local/db/schema.sql`) | **Yes — always** |

**Lock-in rule (enforced from Stage B):** no business logic in
Dokploy UI-only settings or Dokploy-specific scripts; everything
load-bearing lives in Git or the documented environment inventory.
Dokploy-embedded configuration is, by definition, configuration the
exit drill must be able to recreate.

## 2. Exit prerequisites

1. Stage H owner authorization (plan §17 — the drill is itself
   gated because it runs against real environments).
2. Latest restore-verified backups for every data surface (DR
   runbook §1 table) in off-host S3 destinations with credentials
   at hand (securely, never in Git).
3. The environment inventory (names-only) current: services,
   volumes with their effective `{appName}_{volumeName}` names,
   env-var name list, domains, schedules.
4. A clean target host (or the local Colima stack for a
   local-fidelity drill) WITHOUT Dokploy installed.

## 3. Exit drill procedure (PLANNED)

1. **Stop the managed stack** (Dokploy stop of all services).
2. **Recreate from Git only:** clone the repository at the recorded
   deploy commit; run the compose overlay with
   `docker compose -f <overlay> up -d` — the same primitive Dokploy
   itself orchestrates.
3. **Restore data** from the off-host backups into fresh named
   volumes using the documented preconditions (target volume absent,
   containers stopped; volume naming per compose project prefix).
4. **Reapply environment variables** from the secret system into
   `.env` (the documented Dokploy mechanism doubles as the exit
   mechanism — the same file, without Dokploy).
5. **Recreate TLS/domains** at the replacement edge (plain Traefik/
   reverse proxy per Phase 4 brief G5) — or run local-only ports if
   the drill targets local fidelity.
6. **Verify identity, not appearance:**
   - decision-ledger `verify_chain()` +
     `decision_ledger_drill.py --consistency-only` → `ok: true`
   - transactional store verification (drills) on the restored data
   - battery-compatible health probes green
   - canonical fold equality where snapshots are involved
   - D-123-style probes and a `qa.health_report.v1` entry recorded
7. **Verdict:** PASS requires every check green with the new
   evidence pack; a PASS proves Dokploy is removable at that commit
   with that data. Any FAIL is a lock-in defect — logged against the
   risk register (plan §15 R12) and re-drilled after the fix.

## 4. Post-exit state

- Dokploy leaves behind only containers, images, volumes, and its
  own control plane data — all of which the drill replaces or
  ignores. No project data format, schema, or code depends on
  Dokploy artifacts (compose overlays are plain Compose; the D-056
  media adapter and every storage contract are Dokploy-neutral).
- The stack then runs exactly as the local-first architecture always
  assumed: Docker primitives + Git + the project's own recovery
  machinery (D-125/drills/attestation).

## 5. Cadence

The exit drill is repeated after any material change in the
deployment topology (new service, new volume, new domain) and at
least before each major version promotion — keeping the exit path
proven, not theoretical.

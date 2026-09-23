# Dokploy Infrastructure Bridge (D-141 work package)

Stages B–H provisioning artifacts and the orchestration/verification
bridge for the optional Dokploy deployment layer. Governing documents:

- Plan: `docs/deployment/dokploy-plan.md` (stages A–H, §17/§21.6
  per-stage owner authorizations)
- Production manifest: `local/infra/compose.prod.yml`
  (D-141 runtime-hardening record, §24)
- Exit/DR procedures: `docs/runbooks/` (vendor exit, DR, restore)

## Standing boundary

These artifacts PREPARE provisioning; they do not perform it. Stage C+
execution (host provisioning, Dokploy install, DNS, credentials,
activation) requires the per-item owner authorizations in the plan and
remains gated by D-139 for production. No credentials are stored here:
every secret is a `${VAR:?…}` fail-closed reference (G-B1/D-045).

## Stage map (this directory)

| Stage | Scope | Artifact |
|-------|-------|----------|
| B | Database & core state (PostgreSQL SSOT volumes, health, WAL archiving params, pooling boundary) | `compose.prod.yml` (`canonical-db`) + `postgres-ssot.env.example` |
| C | Redis cache & broker (AUTH, eviction, persistence) | `redis.env.example` (Redis service added when the worker tier lands — see stage D note) |
| D | Application core & workers (engine, worker pools, sync daemons; limits, probes) | `deploy_orchestrator.sh` stage gates + `compose.prod.yml` hardening baseline |
| E | Telemetry & monitoring sinks → D-089 escalation | `TelemetryNotificationBridge` (wired 2026-09-22) + health probe telemetry checks |
| F/G | Reverse proxy, SSL & routing | Gateway-attach contract: `frontend` network is `attachable: true`; TLS/headers are deployment-layer config (vendor-neutral, not encoded in compose) |
| H | Orchestration & health verification | `deploy_orchestrator.sh` + `local/src/infra/infra_health_probe.py` |

### Stage C/D note (Redis)

The D-045/D-042 boundary keeps orchestration out of the canonical
core; the current worker tier (Phase 19 control plane, D-070/D-091
outbox workers) runs **in-process against the PostgreSQL SSOT** and
needs no broker today. Redis is therefore declared as configuration
(`redis.env.example`) with its secure-by-default parameters pinned
(AUTH required, `noeviction` for durable queues, AOF persistence),
and its service is added to the manifest only when a component
actually requires it — not speculatively.

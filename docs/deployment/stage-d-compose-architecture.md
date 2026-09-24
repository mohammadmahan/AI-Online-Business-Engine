# Stage D — Pre-deployment Compose Architecture & Secret Envelope (D-144)

- Work package: **Dokploy Deployment Integration** (D-141, Approved).
- Status: **SPECIFICATION + hermetic generator — nothing deployed.**
  Real deployment remains owner-gated (D-139, plan §17/§21.6). The
  generator produces a manifest; it never contacts Docker, a network,
  or a host.
- Machine enforcement: `local/infra/dokploy/stage_d_compose_generator.py`
  + `local/tests/test_dokploy_stage_d_generator.py`.
- Siblings: `dokploy_compose_template.yaml` (canonical template),
  `stage-c-host-prerequisites.md` (Stage C gate), `compose.prod.yml`
  (hardening lineage this contract inherits).

## 1. Purpose and non-goals

Stage D turns the verified template into the exact manifest a
deployment layer will consume — deterministically, fail-closed, and
without ever letting a credential value pass through the generator.
It is a *configuration engine*, not a deployment tool: it does not
run `docker compose up`, provision anything, or contact any daemon.

## 2. Service topology

| Service | Role | Networks | Ports published | Volumes |
|---|---|---|---|---|
| `postgres-ssot` | PostgreSQL SSOT (D-055 lineage) | `backend` only | **none** | `canonical_data` |
| `redis` | Broker / transient cache (AUTH, noeviction, AOF) | `backend` only | **none** | `redis_data` |
| `app-orchestrator` | App core / worker pools / sync daemons | `backend` + `edge` | none on host — gateway-routable via `edge` | — |
| `telemetry-circuit` | Metrics/log seam wired to D-089 | `backend` only | **none** | — |

Image slots (`{{POSTGRES_IMAGE}}`, `{{REDIS_IMAGE}}`, `{{APP_IMAGE}}`,
`{{TELEMETRY_IMAGE}}`) must be substituted with digest-pinned refs; the
generator refuses to emit a half-pinned manifest and warns on any
non-digest pin.

## 3. Network isolation matrix

| From \ To | `backend` (internal) | `edge` | Host / public |
|---|---|---|---|
| postgres-ssot | ✓ | ✗ | ✗ (never; SSH tunnel = owner decision) |
| redis | ✓ | ✗ | ✗ (never) |
| app-orchestrator | ✓ | ✓ (sole surface) | only via gateway 80/443 |
| telemetry-circuit | ✓ | ✗ | ✗ (scraped internally) |
| Gateway/Traefik | ✗ | ✓ (routes `edge` only) | 80/443 terminate HERE |

- `backend` is `internal: true`: no outbound route to the host or
  internet — SSOT and broker are unreachable from outside the bridge
  by construction (carries Stage C VC-07 into the manifest layer).
- TLS terminates at the Dokploy/Traefik gateway. No container ever
  publishes 80/443; `app-orchestrator` is the only `edge` attach.

## 4. Secret injection sequence (D-045/D-124)

1. **Owner** stores per-environment values in the deployment layer's
   secret envelope (Dokploy environment settings or an external secret
   manager). Values NEVER appear in Git, the template, the generator
   invocation, logs, or reports.
2. **Generator** validates PRESENCE of
   `CANONICAL_DB_NAME/USER/PASSWORD`, `REDIS_PASSWORD` in the injected
   env (`--env-file` or injected mapping — never `os.environ`); a
   missing key is a `CANNOT_GENERATE` failure naming only **masked
   keys** (`can***1a2b3d4e` form).
3. **Render** substitutes the strict `${VAR:?reason}` references
   as-is; Docker performs interpolation at deploy time inside the
   daemon. Any non-strict `$VAR`/`${VAR}`/`$(VAR)` form is a REFUSAL.
4. **Emit** writes the manifest plus an optional report containing the
   env **fingerprint** (sha256 over `NAME=sha256(value)` pairs) and
   findings — all redaction-passed. The same input renders the same
   bytes every time (deterministic output, diff-stable).

Hard refusal (F-4): any secret-shaped literal (`sk-…`, PEM headers,
`postgres://user:pass@`, `redis://:pass@`, `key=value` shapes) in a
value is rejected with the value redacted.

## 5. Healthcheck ↔ probe parity

Manifest healthchecks mirror `local/src/infra/infra_health_probe.py`
probe semantics so a deployment-gate probe maps 1:1 onto a container
check: `pg_ssot` (SELECT-1 readiness via `pg_isready`), `redis_broker`
(PING→PONG with AUTH), worker heartbeat (`/healthz/worker`), telemetry
circuit state (`/-/healthy`; circuit must not be latched OPEN). A
container whose check fails cannot pass the Stage D→E gate.

## 6. Resource constraints

Ceilings inherit `compose.prod.yml` sizing (validated locally in the
prodcheck project): postgres 512m/1.0 CPU, redis 256m/0.5,
app-orchestrator 1g/1.0, telemetry 256m/0.5; `no-new-privileges:true`
and read-only rootfs + tmpfs on the stateful services. Totals fit the
Stage C host floor (§2 of `stage-c-host-prerequisites.md`).

## 7. Rollback procedure (manifest layer)

1. Re-generate from the previous pinned template/images (the env
   fingerprint identifies the exact inputs used).
2. `docker compose -f docker-compose.dokploy.yaml up -d` re-applies
   the prior state; named volumes (`canonical_data`, `redis_data`) are
   NEVER dropped — data outlives every manifest rollback.
3. If the SSOT schema moved, restore from the latest D-125 verified
   archive per `docs/runbooks/staging-disaster-recovery.md` — manifest
   rollback never substitutes for data recovery.
4. Post-rollback verification: the Stage B–H health probe
   (`infra_health_probe.py`) must be all-green before traffic resumes;
   findings are fail-closed.
5. Application rollback (previous image digest) and database rollback
   are SEPARATE procedures; backward-compatible schema changes are
   mandatory precisely so these two can be independent (Dokploy plan
   §7 release-governance requirements).

## 8. Verification and exit codes

- `RENDERED` (0) — manifest emitted; findings may carry `warning:`
  lines (e.g., non-digest pin) but nothing critical.
- `REFUSED` (1) — contract violation: loose `$VAR` forms, backend
  service on `edge`, ports on backend services, missing image slots
  handled as CANNOT.
- `CANNOT_GENERATE` (2) — missing image slots, unresolved template
  slots, unreadable template, missing required secrets.

## 9. Unresolved owner decisions

- Concrete image refs (registry + digests) for the app and telemetry
  services — the slots stay unpinned until the owner picks artifacts.
- Secret-envelope tool selection (open register row 8) — the contract
  is tool-agnostic today.
- Whether telemetry exposition should later get an authenticated edge
  route (currently internal-only, scraping via app).

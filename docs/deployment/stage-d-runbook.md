# Stage D Runbook — Pre-Deployment Manifest Flow (D-144 / D-141, plan §26/§37)

**Status: SCAFFOLD — preparation phase.** Stage D is the manifest
layer: a candidate manifest is GENERATED from the canonical template
(D-144, never hand-written), statically verified, rehearsed against a
local candidate, and only then handed to Stage E cutover. **No host
exists, no remote mutation, no live VPS deployment is authorized** —
real deployment stays owner-gated under the signed SC-1..SC-12
checklist (0/12, fail closed) and D-139. Nothing in this runbook
touches a remote system; every step runs locally and mutates nothing
outside the local rehearsal project.

The authoritative artifacts this runbook sequences:
`docs/deployment/stage-d-compose-architecture.md` (topology, isolation
matrix, secret-injection sequence, rollback), the canonical template
`local/infra/dokploy/dokploy_compose_template.yaml`, and the
hermetic generator `local/infra/dokploy/stage_d_compose_generator.py`.

## 1. Scope and boundaries

Stage D answers ONE question: *is there a complete, fail-closed
manifest a deployment layer can consume, and is a local rehearsal of
it healthy?* It does NOT authorize deployment. The pre-flight chain:

| # | Step | Surface | Failure class |
|---|------|---------|---------------|
| 1 | Template integrity | `stage_d_preflight.py --mode template` | exit 2 |
| 2 | Manifest generation (D-144) | `stage_d_compose_generator.py` | exit 1/2 |
| 3 | Manifest contract verification | `stage_d_preflight.py --mode manifest` | exit 1/2 |
| 4 | Local rehearsal (staging manifest lineage) | `bootstrap_staging.py` + `run_staging_smoke_tests.py` | exit 1/2 |
| 5 | Composite gate | `launch_attestation.py --check-stage-c` | exit 1/2 |

Step 4's lineage: the Dokploy manifest contract (D-144 isolation +
probe parity) descends from the already-verified local staging
manifest, so the **smoke harness runs against the local staging stack
as the rehearsal leg** (`run_staging_smoke_tests.py` 21/21 pinned);
it does NOT run against the rendered Dokploy manifest (a real
deployment-layer manifest has no local stack behind it yet). The
rehearsal proves the lineage contract (five-plane health + schema +
smoke), not the rendered manifest's runtime — the rendered manifest's
runtime execution is Stage E/cutover territory, owner-gated.

Step 5's composite gate consumes the standing Stage C clearance chain
(grants + token); a Stage D rehearsal never weakens it.

## 1.1 Secret envelope (D-045/D-124)

No credential VALUE exists at Stage D preparation: the generator
validates PRESENCE of the four required secrets from an injected env
file that is never committed (gitignored), values never appear in
Git, logs, reports, or fingerprints (sha256 fingerprint binding
only). If a real envelope file ever exists locally, it lives outside
Git; this runbook never instructs creating one — the deployment
layer's secret envelope supplies values at deploy time.

## 2. Application stack topology (D-144)

| Service | Role | Networks | Host ports | Volumes |
|---|---|---|---|---|
| `postgres-ssot` | PostgreSQL SSOT (D-055 lineage) | `backend` only | **none** | `canonical_data` |
| `redis` | Broker / transient cache (AUTH, noeviction, AOF) | `backend` only | **none** | `redis_data` |
| `app-orchestrator` | App core / worker pools / sync daemons | `backend` + `edge` | none (gateway-routable via `edge`) | — |
| `telemetry-circuit` | Metrics/log seam (D-089 boundary) | `backend` only | **none** | — |

`backend` is `internal: true` — no outbound route; `edge` carries only
the app; 80/443 terminate at the Dokploy/Traefik gateway, never on a
container. Healthchecks mirror `infra_health_probe.py` semantics
(V-09 parity): `pg_ssot` (pg_isready SELECT-1), `redis_broker`
(PING→PONG with AUTH), worker heartbeat (`/healthz/worker`),
telemetry circuit (`/-/healthy`).

## 3. Deployment flow (operator steps)

### Step 1 — Template integrity (pre-flight mode `template`)

```bash
python3 local/scripts/stage_d_preflight.py --mode template --json
```

Asserts the canonical template carries the D-144 contract (services,
networks, zero published ports on data services, V-09 probe-parity
healthchecks, `${VAR:?}` strict credential references, named
volumes). Exit 0 required before anything downstream is trusted.

### Step 2 — Generate the candidate manifest (D-144)

```bash
python3 local/infra/dokploy/stage_d_compose_generator.py \
  --images POSTGRES_IMAGE=<digest-pinned> REDIS_IMAGE=<digest-pinned> \
           APP_IMAGE=<digest-pinned> TELEMETRY_IMAGE=<digest-pinned> \
  --env-file <uncommitted envelope> --out <candidate manifest>
```

Deterministic byte-identical render for identical inputs. Missing
image pins or missing required secrets refuse with exit 2, masked
keys only.

### Step 3 — Verify the candidate manifest (pre-flight mode `manifest`)

```example
python3 local/scripts/stage_d_preflight.py --mode manifest \
  --manifest <candidate manifest> --json
```

Asserts the rendered manifest against the same contract: services
complete, `backend` internal, zero published ports on the three data
services, app sole edge attach, V-09 probe parity, strict `${VAR:?}`
credential references, named volumes. `stage_d.verdict.v1` JSON,
machine-readable.

#### Steps 2–3 as one offline rehearsal (committed surfaces, deterministic)

The render→verify loop is codified as a single fail-closed command —
four synthetic digest-pinned slots, the committed names-only envelope
`local/infra/dokploy/stage_d_mock.env.example` (`__MOCK__` values,
never real credentials), temp-only artifacts, a byte-identical
re-render proof, and pre-flight HOLDS 7/7 — or exit 2:

```bash
python3 local/scripts/stage_d_rehearsal.py --json
```

`stage_d.rehearsal.v1` JSON, machine-readable. A pass is evidence
machinery, NOT a deployment authorization: SC-1..SC-12 remain
owner-gated at 0/12.

### Step 4 — Local rehearsal (lineage contract)

The preflight reads ONLY the process environment — it never reads
secrets from containers, images, or the stack. Before running it,
export the 9 mandatory staging runtime keys from the operator-held,
gitignored env file (`local/infra/.env.staging`; maintained by the
operator outside git — never committed, never echoed):

```bash
set -a; . local/infra/.env.staging; set +a   # operator-maintained, gitignored

python3 local/scripts/bootstrap_staging.py --check
python3 local/scripts/run_staging_smoke_tests.py            # canonical 11
python3 local/scripts/run_staging_smoke_tests.py --stack    # full 22/22
```

The staging lineage is the rehearsal surface: five-plane health,
13/13 schemas, synthetic-only smoke (22/22 pinned — 11 canonical +
11 stack). The bootstrap preflight runs against the operator-exported
staging env (9 mandatory runtime keys; values never printed, D-124).
Read-only checks; label-based stack checks need no secret env.
Exit 0 required. Executed 2026-09-30 (plan §57): preflight 9/9
resolved, 13/13 schemas, smoke 22/22 — all green. Governance note:
that run resolved the keys in-process from the running containers
(values never printed; no committed code extracts secrets from
containers); the documented and required workflow going forward is
the operator export above. Re-run executed 2026-10-01 (plan §57)
through exactly that export — `local/infra/.env.staging` sourced,
values never printed: exit 0, preflight 9/9 resolved, 13/13 schemas,
stack untouched. Evidence hardened 2026-10-02 (plan §57): the DB
role credential was rotated so the exported env authenticates the
RUNNING database over real TCP (positive + negative auth controls),
removing the trust-only caveat; exit 0, 9/9 keys, 13/13 schemas.

### Step 5 — Composite gate

```bash
python3 local/scripts/launch_attestation.py --check-stage-c
```

The standing Stage C clearance (grants 0/12 ⇒ SC-GRANTS blocker;
token leg) composed with the D-138 attestation. Exit contract 0/1/2.
Executed 2026-09-30 (plan §57): grants audit READY 6/6 with the
machine verifier standing at NOT_AUTHORIZED 0/12 (the required
fail-closed answer), Stage D rehearsal REHEARSAL_PASS, composite
verdict NO_GO with the SOLE blocker SC-GRANTS — Stage D readiness
does not move the authorization state; live activation stays
owner-gated (D-139).

## 4. Gating prerequisites (fail closed)

- Template + manifest contract green (steps 1–3) — a contract
  violation refuses the flow with non-zero exit.
- Local rehearsal green (step 4) — a degraded rehearsal is negative
  evidence.
- Stage C clearance standing (step 5) — an unsigned SC-1..SC-12
  checklist blocks with SC-GRANTS; a findings-bearing token blocks
  with SC-RUNBOOK.
- Nothing in this flow provisions, deploys, or mutates a remote
  system. **Stage D external execution (remote host, DNS, real
  deployment) remains owner-gated per plan §17** — no exception.

## 5. Recovery and rollback (manifest layer)

Manifest rollback ≠ data recovery: named volumes (`canonical_data`,
`redis_data`) are NEVER dropped — data outlives every manifest
rollback (D-125 archives govern the data plane; restore drills are
the proof, upload ≠ restoration evidence). Rollback = re-generate
from the previous pinned inputs (the env fingerprint identifies the
exact inputs), re-verify (step 3), re-rehearse (step 4). App vs DB
rollback kept separate per `stage-d-compose-architecture.md` §7.

## 6. Exit criteria → Stage E

Stage D preparation exits when steps 1–4 are green and the composite
gate reports the standing clearance state. Handoff to Stage E
(`stage-e-cutover-runbook.md`) carries: the verified candidate
manifest + its env fingerprint, the rehearsal evidence, and the
standing clearance state. Cutover remains owner-gated
(`stage-f-authorization.md`, SF-1..SF-7 — signing SC-1..SC-12 does
NOT pre-authorize Stage F).

## 7. References

- `docs/deployment/stage-d-compose-architecture.md` — D-144
  architecture SSOT (topology, isolation matrix, secret-injection
  sequence, rollback §7).
- `local/infra/dokploy/dokploy_compose_template.yaml` +
  `stage_d_compose_generator.py` — the canonical template and its
  hermetic renderer (F-1..F-4 fail-closed invariants).
- `local/scripts/stage_d_preflight.py` — the Stage D pre-flight
  verifier (template/manifest modes; `stage_d.verdict.v1`).
- `local/scripts/bootstrap_staging.py`, `run_staging_smoke_tests.py`
  — the local rehearsal harnesses (plan §26, executed).
- `docs/deployment/stage-e-cutover-runbook.md`,
  `stage-f-authorization.md` — the owner-gated next stages.
- `docs/deployment/dokploy-plan.md` §26 (Stage D execution record),
  §37 (D-144 configuration engine), §54 (Stage C milestone record).
- Decisions: D-141 (planning), D-144 (generated configuration),
  D-145 (V-08/V-09), D-169/D-170 (program closeout).

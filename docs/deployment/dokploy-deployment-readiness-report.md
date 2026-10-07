# Dokploy Deployment Readiness Report — Phase B

**Infrastructure Reconnaissance & Manifest Validation** · 2026-10-07

| | |
|---|---|
| Mode | **Zero-mutation reconnaissance** — no manifest, config, env file, source file or protected artifact was modified |
| Baseline | `3f12a25` (`3f12a25f5b07b9ce1620031606be5ef930a94290`), working tree clean at start **and** at end |
| Owner directive | Mohammad — *"Prepare the project for Dokploy staging deployment (Phase B)"* |
| Authority | D-141 (Approved 2026-09-20) · D-139 remains the sole production-activation authority · D-045 credential gate · PROJECT_RULES §2.1/§23/§38/§41/§42 |

---

## 0. Documentation-anchor reconciliation (reported, not invented)

The directive cites three documentation anchors. **None of them exists as a heading on disk.** Per PROJECT_RULES §2 step 10 and §4, that is recorded here rather than silently substituted:

| Cited anchor | Status on disk | Real anchor |
|---|---|---|
| `MASTER_PLAN.md §Phase B (Infrastructure Baseline & Dokploy Staging)` | **absent** — the string `Phase B` appears **0 times** in `MASTER_PLAN.md` | §13 post-baseline work package **"Dokploy Deployment Integration"** (line 868; D-141, *"**Stage B VERIFIED** — secret-free staging manifest"*); §13 `### Phase 4 --- Infrastructure` (line 1098 — the open G1 hosting gate, D-058 deferral stands); §16 Current Status (line 1283) — *"handoff to Infrastructure Deployment & Staging orchestration"* |
| `TODO.md §Phase B` | **absent** — 0 matches | `## Active Phase — Infrastructure Deployment & Staging Orchestration (Dokploy Stage C rollout and beyond) — handoff ACTIVE` (line 560) + the Dokploy work-package block (line 1855), where *"**Stage B VERIFIED**"* / *"Stage B amendment"* are recorded |
| `DECISIONS.md §Infrastructure & Deployment` | **absent** — 0 matches | **D-141 — "Optional deployment-management layer (Dokploy): governed integration plan"** (line 3390) and its decision-ledger row **43** (line 6320) |

**Mapping used for this report:** the directive's "Phase B" = **D-141 Stage B** (staging preparation), already recorded VERIFIED 2026-09-20 and amended the same day. This report re-validates that record with live evidence and audits the surfaces Stage B never covered.

---

## 1. Manifest coverage matrix

| Artifact | Scope | Services | Status |
|---|---|---|---|
| `local/infra/docker-compose.yml` | local development | `wordpress`, `woodb`, `canonical-db`, `n8n`, `media`, `mock-woo` (profile `deferred`, off) | present · every published port bound to `127.0.0.1` |
| `local/infra/compose.staging.yml` | **Stage B staging** | 5 (+ deferred `mock-woo`) | **`VALID` rc=0** — digest-pinned, fail-closed, internal `data` network |
| `local/infra/compose.prod.yml` | production runtime hardening | `wordpress`, `woodb`, `canonical-db`, `n8n`, `media` | present · **zero published ports**, `no-new-privileges` everywhere, read-only rootfs where the image supports it |
| `local/infra/dokploy/dokploy_compose_template.yaml` | Stage D **template** | `postgres-ssot`, `redis`, `app-orchestrator`, `telemetry-circuit` | present · `{{POSTGRES_IMAGE}}`/`{{REDIS_IMAGE}}`/`{{APP_IMAGE}}`/`{{TELEMETRY_IMAGE}}` slots |
| `local/infra/dokploy/docker-compose.dokploy.yaml` | Stage D **rendered** | same 4 | rendered, but **carries placeholder digests** (`aaaa…`, `bbbb…`, `cccc…`, `dddd…`) → **not deployable as-is** |
| `local/infra/dokploy/stage_d_fingerprint.envelope` | Stage E binding | — | `manifest_sha256: 7ca497057bd0976a5ebc94c8b90dc38cd5fcef9cc911fe99568c6f806c055928` (any regeneration invalidates this binding, fail-closed by design) |
| `local/infra/dokploy/{postgres-ssot,redis}.env.example` | Stage B/C provisioning contracts | — | present · names only, zero values |
| `control-plane/` (**D-171**) | the unified web control plane | **none** | **NO container manifest of any kind** |
| Traefik / Dokploy ingress config | reverse proxy, TLS, routing | — | **intentionally not committed** — vendor-neutral gateway-attach contract (`frontend`/`edge` networks); TLS/headers are deployment-layer config |
| `.dockerignore` | build-context hygiene | — | **absent everywhere in the repository** |

Verified by full-tree search (`find` for `Dockerfile*`, `docker-compose*.y*ml`, `compose*.y*ml`, `.dockerignore`, `*traefik*`, `*dokploy*`) and by `git ls-files | grep -i 'dockerfile\|dockerignore'` → **NONE**.

---

## 2. Container-hardening findings

**Non-root execution.** Declared `user:` exists in exactly **one** service across all manifests — `n8n: "1000:1000"` in `compose.prod.yml` (line 169, runtime-validated). `postgres`, `mysql`, `minio`, `nginx`/`apache` (WordPress) rely on the upstream images dropping privileges internally, which is legitimate but **not declared**; `compose.prod.yml`'s own header states "non-root execution users (**documented per image**)" — the documentation is in the comments, not in a `user:` key. WordPress is explicitly **not** `read_only: true` and the file says so honestly ("the image entrypoint completes its first-run volume initialization as root … weakening it silently would be dishonest").

**Port exposure.** `compose.prod.yml`: **zero** `ports:` keys. `compose.staging.yml`: exactly one (`wordpress` → `18080:80`, the sole published surface). `local/infra/docker-compose.yml`: seven, all `127.0.0.1`-bound. Stage D template: **zero** `ports:` keys — routing is via the `edge` network only.

**Network definitions.** Stage B amendment topology is real and enforced: `data` (`driver: bridge`, `internal: true`) carries every stateful plane plus its consumers; `frontend` carries WordPress only and is `attachable: true` in production so the gateway proxy can join. Stage D: `backend` (`internal: true`) for `postgres-ssot` + `redis` + `app-orchestrator` + `telemetry-circuit`; `edge` for `app-orchestrator` **only**.

**Health checks.** Every service in every manifest declares a `healthcheck`. Startup ordering is fail-closed where it matters: `wordpress → woodb` (`service_healthy`), `n8n → canonical-db`, `app-orchestrator → postgres-ssot + redis`. Not gated: `media`, `telemetry-circuit`, `mock-woo`.

**Fail-closed secret contract (proven, not asserted).** Every credential-bearing variable is `${VAR:?message}`. Live evidence this run:

```
python3 local/scripts/validate_staging_compose.py            → exit 0
  [OK] docker CLI + compose plugin available
  [OK] schema valid — 5 services resolved
  [OK] fail-closed proven for all 6 deploy secrets
  [OK] digest pins, restart policies, healthchecks verified
  [OK] exposure model verified (wordpress sole surface, no loopback/gateway conflicts)
  [OK] network isolation verified (data internal, frontend wordpress-only)
  [OK] named volumes verified
  [OK] env contract complete: 30 documented
  VALID: staging manifest + env contract consistent

python3 local/scripts/validate_dokploy_runtime.py --gate   → exit 0
  [OK] full contract resolves (9 keys)
  [OK] missing CANONICAL_DB_HOST refuses startup (fail-closed)
  [OK] missing CANONICAL_DB_PORT refuses startup (fail-closed)
  [OK] missing CANONICAL_DB_PASSWORD refuses startup (fail-closed)
  [OK] missing MEDIA_ENDPOINT refuses startup (fail-closed)
  [OK] missing N8N_URL refuses startup (fail-closed)
  [OK] prohibited WORDPRESS_DEBUG refuses startup (D-045/D-124)
  [OK] prohibited AI_LIVE_ENABLED refuses startup (D-045/D-124)
  [OK] short secret refuses; value withheld in message
  [OK] readiness READY when all probes green
  [OK] missing evidence → NOT_READY ×3
  GATE VERIFIED
```

---

## 3. §41 disposition (no hidden failure)

**Satisfied where it can be proven locally, with three honest caveats:**

1. **`wordpress`'s health check is a no-op.** `test: ["CMD", "php", "-r", "exit(0);"]` returns 0 unconditionally in all three manifests. It is not a lie about a *dependency* (nothing uses it as a gate; `wordpress` itself is gated by `woodb`), but it can never detect a broken WordPress — it would report healthy on a wedged container. Flagged, not fixed: changing it is a manifest mutation outside this reconnaissance and outside Stage B scope.
2. **`media`'s health check is probably non-convergent.** `test: ["CMD-SHELL", "mc ready local || exit 1"]` invokes `mc`, the **MinIO client**, which is not part of the `minio/minio` server image; if absent, the check fails forever and the container reports permanently unhealthy. **Unverifiable here** (no Docker daemon, no image pull) — recorded as *needs verification*, never as a confirmed defect. Nothing gates on `media` health today, so the impact is a false signal, not a silent degradation.
3. **Health-based restart is absent.** `restart: unless-stopped` restarts on *exit*, not on health-check failure. A container that goes unhealthy without exiting stays up; nothing in the compose topology self-heals it. The platform's health surface is therefore `infra_health_probe.py` + the D-089 telemetry escalation, not Docker itself.

**Absent infrastructure is reported as absent, never as a pass** (§41): Docker daemon, local PostgreSQL (`127.0.0.1:55432`), the probe sidecar (`127.0.0.1:8088`) and all live-stack paths are unavailable in this environment; ~67 infra-gated Python modules remain unexercised and no live-stack claim is made anywhere in this report.

---

## 4. Environment configuration surface

| File | Tracked | Role | Secret material |
|---|---|---|---|
| `.env.example` | ✅ | local contract; 6 production-injected keys listed **empty** so the `${VAR:?}` contract is provable without a value | none |
| `.env.staging.example` | ✅ | Stage B promotion contract, 30 variables; the 6 deploy secrets are `<SET-BY-DEPLOYMENT-LAYER>` placeholders | none |
| `.env.staging.template` | ✅ | Stage C fill-in artifact; strict placeholders `<GENERATE_SECURE_PASSWORD>` / `<SET-AFTER-GRANT:SC-n>` | none |
| `local/infra/dokploy/postgres-ssot.env.example` | ✅ | WAL-archiving + SSOT identity; `CANONICAL_DB_PASSWORD=` empty | none |
| `local/infra/dokploy/redis.env.example` | ✅ | AUTH / `noeviction` / AOF contract; `REDIS_PASSWORD=` empty | none |
| `local/infra/dokploy/stage_d_mock.env.example` | ✅ | rehearsal envelope — literal `__MOCK__` placeholders only | none |
| `local/infra/.env.staging` | ❌ gitignored (`.gitignore:4`) | real staging file | not read, not printed |
| `control-plane/.env.local` | ❌ gitignored (`control-plane/.gitignore:10`) | control-plane local env | **untouched — md5 `5f5baf669ba3e725494a8a429869bc31`, unchanged before and after this audit** |

**Zero-secret proof:** `git ls-files | grep -i '\.env'` returns only `.example`/`.template` files. A value-shaped scan of every tracked env file (lines matching `^[A-Z0-9_]+=.+` and not a placeholder, host, port, currency, region, timezone, path or enum) returned **4 hits, all non-secret**: `CANONICAL_DB_PORT=55432`, `CANONICAL_DB_HOST=canonical-db`, `WORDPRESS_DB_HOST=woodb:3306`, `WOO_REST_NAMESPACE=wc/v3`. No `.env*` file has ever appeared in a commit.

**Secrets Dokploy must supply at cutover** (names only, never values): `WORDPRESS_DB_PASSWORD`, `MYSQL_PASSWORD`, `MYSQL_ROOT_PASSWORD`, `N8N_ENCRYPTION_KEY`, `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`, `CANONICAL_DB_NAME`, `CANONICAL_DB_USER`, `CANONICAL_DB_PASSWORD`, `REDIS_PASSWORD` — plus the SC-6/SC-7 backup keys for the P5 integration.

---

## 5. Gaps (ranked)

| ID | Gap | Severity | Blocks |
|---|---|---|---|
| **G-1** | **The control plane (`control-plane/`, D-171) has no container manifest at all** — no `Dockerfile`, no service entry in any compose manifest, no health endpoint (`src/app/` has the 7 canonical routes only; no `route.ts`/`healthz`), and `next.config.mjs` has no `output: 'standalone'`. | **High** | Any Dokploy deployment *of the control plane*. It does **not** block the existing D-141 Stage B stack |
| **G-2** | Rendered `docker-compose.dokploy.yaml` carries placeholder digests at lines 31/59/84/121 → not deployable; regenerating it also invalidates the Stage E fingerprint binding. | **High** (for Stage D+) | Stage D/E cutover only |
| **G-3** | No `.dockerignore` anywhere. A build context added later would sweep in `node_modules/`, `.next/`, `.test-build/` — and, absent an explicit ignore line, `control-plane/.env.local` (a D-045 hygiene hazard, not currently a leak). | Medium | Future builds |
| **G-4** | No Traefik/Dokploy ingress definition committed | **By design** — gateway-attach contract. Not a defect; a cutover **step**, not a fix | — |
| **G-5** | `wordpress` health check is a constant-true no-op (§3.1) | Medium | Honest health reporting |
| **G-6** | `media` health check probably cannot converge (§3.2) | Low–Medium | Honest health reporting |
| **G-7** | No health-based restart / self-healing (§3.3) | Medium | Unattended operation |
| **G-8** | Rendered `docker-compose.dokploy.yaml` still carries the template's own header — *"TEMPLATE, not a deployable manifest"* — because the generator copies the header verbatim. Cosmetic, but misleading on a rendered artifact. | Low | — |
| **G-9** | No manifest entry for the probe **sidecar** (`127.0.0.1:8088`) that the control plane's live surfaces read. The control plane fails **closed** without it (UNKNOWN / «بدون داده») — correct behaviour — but staging will show no live data until a sidecar service is defined. | Medium | Live-data rendering in staging |

---

## 6. Required Dokploy service topology

Two topologies exist on disk and must not be conflated:

**(a) Stage B/C staging stack — `local/infra/compose.staging.yml`** (what the directive calls "Phase B")

```
Dokploy control plane  ── management interface: firewall-only, never public (plan §19)
        │
Traefik / gateway  ─── attaches `frontend` at deploy time; TLS terminates here
        │
   ┌────┴──────────────────────────────────────────────┐
   │ frontend (bridge, attachable)  →  wordpress ONLY  │  published 18080 until the proxy owns 80/443
   ├───────────────────────────────────────────────────┤
   │ data (bridge, internal: true) — no egress          │
   │   woodb (mysql, no ports) ← canonical-db ← n8n     │
   │   media (minio, no ports) · mock-woo (off-profile) │
   └───────────────────────────────────────────────────┘
Persistent volumes: woo_data · woo_data_db · canonical_data · n8n_data · media_data
```

**(b) Stage D target — `local/infra/dokploy/docker-compose.dokploy.yaml`**

```
edge (gateway-routable)  →  app-orchestrator ONLY
backend (internal: true) →  app-orchestrator · postgres-ssot · redis · telemetry-circuit
Volumes: canonical_data · redis_data
```

**Sequencing note for the owner:** the two topologies are **mutually exclusive as written** — (a) has no `app-orchestrator`/`redis`, (b) has no WordPress/MySQL/n8n/media. `stage_d_compose_generator.py` fails any service-set drift from its own base, so (b) is not an evolution of (a); they are separate deployment targets. Any staging deploy that must serve both the storefront stack **and** the engine core needs a topology decision that does not exist on disk yet.

---

## 7. Phase B cutover steps (exact)

Derived from `docs/deployment/stage-c-runbook.md` §2–§3 and `dokploy-plan.md` §21.6/§22. **Nothing below has been executed.**

1. **Grant gate (SC-1…SC-12)** — `python3 local/scripts/verify_stage_c_grants.py` must exit 0. Unsigned checklist = explicit `SC-GRANTS` blocker folded into the launch verdict. Signable rows: `docs/deployment/stage-c-owner-grants.md`.
2. **Dry-run clearance** — `local/scripts/stage_c_dry_run.py` over the filled `.env.staging` (from `.env.staging.template`).
3. **Stage acceptance rehearsal** — `local/scripts/stage_c_acceptance.py`.
4. **Target validation** — `local/scripts/validate_vps_target.py --require-grants`.
5. **Readiness probe** — `local/scripts/validate_vps_readiness.py --require-grants` (read-only; exit 0/1/2).
6. **Composite launch attestation** — `local/scripts/launch_attestation.py` (clean tree + both DR legs + edge report). **Note:** on this machine it returns `NO_GO` with blockers `['BAC-001','MON-001']` purely because the local Docker stack is down; that is an *absent-environment* signal, not a failure (§41) — recorded as such in `test_stage_e_cutover.py`.
7. **Pre-deploy manifest validation** — `python3 local/scripts/validate_staging_compose.py` → **`VALID` rc=0** (re-run immediately before deploy; it also performs bidirectional env-contract drift detection).
8. **Provisioning execution (owner-gated, G1–G6)** — `docs/runbooks/dokploy-vps-provisioning.md`: P1 host bootstrap (UFW + SSH hardening) → P2 pinned Dokploy install (+2FA/audit re-verification per SC-10) → P3 network/tunnel/DNS → P4 named volumes (SC-12) → P5 S3 backup integration (SC-6/SC-7, supplement-only vs D-125) → P6 staging dry-run (`run_staging_smoke_tests.py`, 21/21) → attach Traefik to `frontend`.
9. **Post-deploy assertions** — the VERIFICATION LOG in `stage-c-runbook.md` §4 **starts EMPTY** and is append-only; a stage is not closed until its rows exist.
10. **Rollback** — `stage-c-runbook.md` §5 / `docs/runbooks/dokploy-disaster-recovery.md`.

**Before step 8 for the control plane specifically:** G-1 must be closed first (a container manifest + a health endpoint + a service entry), and G-9 decided (sidecar present or explicitly absent). Neither is in Stage B scope.

---

## 8. Baseline gate results (this run)

| Gate | Command (cwd `control-plane`) | Exit | Evidence |
|---|---|---|---|
| Unit tests | `npm test` | **0** | `# tests 89 · # pass 89 · # fail 0 · # suites 17 · # skipped 0` (~97 ms) |
| Types | `npm run typecheck` | **0** | `tsc --noEmit`, no output |
| Lint | `npm run lint` | **0** | `eslint .`, no output |
| Contrast | `npm run check:contrast` | **0** | 82 source files scanned · 0 raw hex outside the token layer · 114 permitted token definitions · **52 enforced pairings, 0 violations** |
| Live verdicts | `npm run check:live-verdicts` | **0** | `✓ live verdict seam: 30/30 cases passed` |
| View isolation | `npm run check:view-isolation` | **0** | 7/7 routes · **0 leaks** (`/dashboard` 11 gated 4/4 · `/automations` 11 5/5 · `/hitl-queue` 8 2/2 · `/orders` 9 1/1 · `/inventory` 10 3/3 · `/ai-engine` 5 1/1 · `/settings` 5 1/1) |
| Build | `npm run build` | **0** | `✓ Compiled successfully` · route table unchanged (`○ /`, `○ /_not-found`, `○ /ai-engine`, `ƒ /automations`, `○ /dashboard`, `○ /hitl-queue`, `○ /inventory`, `○ /orders`, `○ /settings`) |
| Staging manifest | `python3 local/scripts/validate_staging_compose.py` | **0** | `VALID: staging manifest + env contract consistent` |
| Production pre-flight | `python3 local/scripts/validate_dokploy_runtime.py --gate` | **0** | `GATE VERIFIED` (10 refusal cases) |
| Routing contract | `curl` against the dev server | — | `GET /` → **307** `Location: /dashboard` · `/webhooks`, `/logs`, `/webhooks/foo`, `/logs/2026` → **404** |

`check:view-isolation` required the dev server; it was restarted for this run (launchd `com.freebuff.preview-b7576189`, `next dev --webpack -p 3000`, listener on `*:3000`) and answered **200** before the gate ran.

---

## 9. Verdict

- **D-141 Stage B staging artifacts: READY.** `compose.staging.yml` validates clean, all six deploy secrets are proven fail-closed, the network isolation contract holds, digest pins and health checks are present, and the env contract is complete at 30 variables with zero secret material committed. Nothing about Stage B regressed.
- **Stage D manifest: NOT READY** — placeholder digests (G-2). **Control plane (D-171): NOT READY** — no container manifest, no health endpoint (G-1).
- **Zero mutation confirmed.** 13 audited artifacts re-hashed identically after the audit, including `control-plane/.env.local` (`5f5baf669ba3e725494a8a429869bc31`), `compose.staging.yml` (`7348342e…`), `compose.prod.yml` (`1d7a9162…`), `docker-compose.dokploy.yaml` (`d4f7b4a8…`) and all four env templates.
- **Gates open and unchanged:** production activation, any provisioning or live credential, and owner review of each phase completion record (D-139/D-045). GitHub push is not production authorization.

**No fix was applied.** G-1 is an architecture decision (containerization strategy for `control-plane`) that PROJECT_RULES §3/§4 reserve for the owner, and G-2/G-5/G-6/G-9 are manifest mutations outside a reconnaissance. This report records them; it does not silently repair them.

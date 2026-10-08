# Control-Plane Container Manifest — Specification (D-171, Stage C→D seam)

**Status: SPECIFICATION ONLY — no container manifest is committed.** `control-plane/`
still has no `Dockerfile` and no `.dockerignore`; the absence is gap **G-1** of the
Dokploy readiness report, which is an architecture decision reserved to the owner
(PROJECT_RULES §3/§4). This document is the artifact that decision needs: exact
content, measured evidence, and the alignment analysis. Authoring date 2026-10-08,
measured on this host. Nothing here deploys, publishes, or changes the running app.

---

## 1. Measured baseline (facts, not assumptions)

| Fact | Value | How measured |
| --- | --- | --- |
| Framework | Next **16.3.8**, React **19.3.0** | `control-plane/package.json` |
| Runtime dependencies | `next`, `react`, `react-dom`, `@radix-ui/react-dialog`, `@radix-ui/react-slot`, `lucide-react` (6) | same |
| Lockfile | `package-lock.json`, 252 092 bytes → `npm ci` is reproducible | `ls -l` |
| Node contract | **none declared** (no `engines`, no `packageManager`, no `.nvmrc`); local dev Node **v20.16.0**; `@types/node` 20.19.43 | `package.json`, `node --version` |
| `output` in `next.config.mjs` | **absent** → standalone output is *not* enabled today | `cat next.config.mjs` |
| Base image | `node:20-alpine` = **49 031 620 bytes (46.8 MiB)**, `node --version` → **v20.20.2** | `docker image inspect`, `docker run` |
| Base image digest | `node@sha256:fb4cd12c85ee03686f6af5362a0b0d56d50c58a04632e6c0fb8363f609372293` — an **OCI image index** (`application/vnd.oci.image.index.v1+json`), i.e. a multi-arch pin: amd64 `sha256:afdf9821…`, arm64 `sha256:d63c3876…` | `docker image inspect` + Docker Hub registry `Docker-Content-Digest` |
| Route surface | 7 pages + `/_not-found`; `/automations` **ƒ dynamic**, 6 **○ static** | `npm run build` route table |
| HTTP API surface | **zero** route handlers, zero `'use server'` | `find src/app -name route.ts`, grep |
| Build-relevant tracked files | `package.json`, `package-lock.json`, `next.config.mjs`, `postcss.config.mjs`, `tsconfig.json`, `src/` (82 files) | `git ls-files` |
| No `public/` directory | confirmed absent | `ls public` |

### 1.1 Payload measurement (the "no bloat" evidence)

`NEXT_PRIVATE_STANDALONE=true npm run build` → **rc=0** (the private flag is used only
to measure; the committed config is untouched):

| Content | Size |
| --- | --- |
| `.next/standalone` (server + traced `node_modules`) | **49 MB** |
| `.next/static` | **880 KB** |
| `server.js` (runner entrypoint) | 7 365 bytes |
| *contrast:* full `node_modules` | 501 MB |
| *contrast:* full `.next` | 254 MB |

Inside the standalone payload: `@img` **27 MB**, `next` 16 MB, `react-dom` 1.4 MB,
`sharp` 892 KB, `react` 104 KB. `next/image` is **not imported anywhere in `src/`**,
so the 27 MB image-optimizer payload currently ships unused — a trimming candidate
that requires its own verification (§7).

**Consequence:** the standalone pattern is what keeps the image out of the 500 MB+
class; a naive `COPY . .` plus `npm ci` would push ~755 MB of build context content
into the image.

---

## 2. Runtime payload verification (measured, not assumed)

The payload was exercised directly, including under the hardened posture the
deployment manifests demand.

| Check | Command shape | Result |
| --- | --- | --- |
| Boots and serves | `node .next/standalone/server.js` (PORT=3100) | `/dashboard` **200** in ~1 s; `/` **307**; `/_next/static/chunks/05n9nq78q_5h6.js` **200** |
| Read-only rootfs + `tmpfs /tmp`, non-root | `docker run --read-only --tmpfs /tmp -u node …` | `/dashboard` **200**, static **200** |
| Read-only rootfs, **no** tmpfs | `--read-only -u node …` | `/dashboard` **200**, static **200** |
| Hardened maximum | `--read-only --cap-drop ALL --security-opt no-new-privileges:true -u node`, no tmpfs | **all 8 routes**: `/` 307, `/dashboard` `/ai-engine` `/automations` `/hitl-queue` `/inventory` `/orders` `/settings` **200**; **0** error lines in the container log |
| Rootfs genuinely read-only | `docker exec … touch /app/x` | `touch: /app/x: Read-only file system` |
| Healthcheck through Docker's engine | `--health-cmd "node -e \"fetch('http://127.0.0.1:3230/dashboard').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))\"" --health-interval 2s` | `starting` → `starting` → **`healthy`** (health log `rc=0`), ~4 s |
| `wget` availability (Stage D probe style) | `docker run --rm node:20-alpine sh -c 'command -v wget'` | `/usr/bin/wget` present |

The static-asset check is load-bearing: it proves the `COPY .next/static` step in §3
is required, not cosmetic.

**Caveats, stated plainly:** arm64 only; no gateway/proxy in front; no image-optimizer
request exercised (no `next/image` usage exists); `CP_*` probe env was unset (the
fail-closed defaults); and **`docker build` was never run**, because no Dockerfile is
committed. §3's manifest is therefore a specification whose build must be verified at
implementation time — a container probe that "should" work has already failed once in
this program (the MinIO `mc ready local` probe under `read_only: true`).

---

## 3. Dockerfile specification

Target path when authorized: `control-plane/Dockerfile`.

```dockerfile
# syntax=docker/dockerfile:1.7
# Multi-arch index pin (verified against the registry 2026-10-08):
#   node:20-alpine -> sha256:fb4cd12c85ee03686f6af5362a0b0d56d50c58a04632e6c0fb8363f609372293
# Floating tags are refused by the deployment contract (Stage D digest rule).
ARG NODE_IMAGE=node:20-alpine@sha256:fb4cd12c85ee03686f6af5362a0b0d56d50c58a04632e6c0fb8363f609372293

# --- stage 1: dependencies (cacheable on the lockfile alone) ------------------
FROM ${NODE_IMAGE} AS deps
WORKDIR /app
COPY package.json package-lock.json ./
# Scripts are deliberately NOT skipped: Next/sharp resolution relies on them.
RUN npm ci --no-audit --no-fund

# --- stage 2: build ----------------------------------------------------------
FROM deps AS builder
COPY . .
# Requires `output: 'standalone'` in next.config.mjs (see §3.1)
RUN npm run build

# --- stage 3: runtime (no npm, no package manager cache, no sources) ---------
FROM ${NODE_IMAGE} AS runner
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
WORKDIR /app
COPY --from=builder --chown=node:node /app/.next/standalone ./
COPY --from=builder --chown=node:node /app/.next/static ./.next/static
# `public/` does not exist yet; add when it does:
# COPY --from=builder --chown=node:node /app/public ./public
USER node
EXPOSE 3000
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=6 \
  CMD node -e "fetch('http://127.0.0.1:'+(process.env.PORT||3000)+'/dashboard').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["node", "server.js"]
```

Layer rationale (each point is a size or correctness decision):

1. **Lockfile-only `COPY` in `deps`** — the dependency layer is reused until
   `package-lock.json` changes, so app edits do not reinstall 500 MB of modules.
2. **No `npm ci` in the runner stage** — the standalone output already contains its
   traced `node_modules`; installing again would double the payload for nothing.
3. **Runner = base + 49 MB payload + 0.88 MB static** — no sources, no `tsconfig`,
   no eslint, no test artifacts, no `.test-build`.
4. **`--chown=node:node`** — the image's built-in `node` user (uid 1000) owns the
   payload, so `USER node` can read everything; verified to serve under `-u node`.
5. **Healthcheck uses `node -e` only** — no `wget`/`curl` dependency, so the probe
   survives even if the base is later swapped for a distroless variant. §2 proves it
   converges through Docker's own health engine.
6. **Digest pin at the top, single source** — one `ARG`, used by all three stages.

### 3.1 Required prerequisite (a config change, not a container file)

`next.config.mjs` must gain `output: 'standalone'`. Without it `next build` emits no
standalone folder. This is a one-line, behavior-additive change to a protected file
and must be made deliberately with the standard gates (§6).

---

## 4. `.dockerignore` specification

Target path when authorized: `control-plane/.dockerignore`. Purpose: keep the build
context small **and** keep local values out of every layer (D-124).

```dockerignore
.git
.gitignore
node_modules
.next
.test-build
next-env.d.ts
tsconfig.tsbuildinfo
.env
.env.*
*.log
coverage
test
scripts
eslint.config.mjs
tsconfig.test.json
```

Deliberately **not** ignored: `package.json`, `package-lock.json`, `next.config.mjs`,
`postcss.config.mjs` (Tailwind v4 runs through `@tailwindcss/postcss`), `tsconfig.json`,
`src/`. `test/`, `scripts/` and the test tsconfig are build-irrelevant for the
production server and stay out of the image.

---

## 5. Health contract — a required addition

**Today there is no health endpoint:** the app has zero route handlers, so nothing
answers `/api/health`. Options:

| Option | Change | Notes |
| --- | --- | --- |
| **A (recommended)** add `src/app/api/health/route.ts` | new app route | returns `200` + `{"status":"ok"}` with `Cache-Control: no-store`; no internals, no version, no probe data (fail-closed disclosure posture). Then point both the Docker `HEALTHCHECK` and the compose healthcheck at it. |
| B (interim) probe `/dashboard` | none | works today (§2) but couples container health to a full UI render and to the dashboard's own dependencies. |
| C probe `/` | none | returns **307**, not 200 — an unhealthy-looking code for a probe unless it follows redirects. |

Option A is a control-plane source change and must run the full gate battery (§6)
before it is claimed as working.

---

## 6. Runtime contract and environment

| Variable | Class | Value / rule |
| --- | --- | --- |
| `PORT`, `HOSTNAME`, `NODE_ENV`, `NEXT_TELEMETRY_DISABLED` | non-secret, image-level | `3000`, `0.0.0.0`, `production`, `1` |
| `CP_PROBE_ENDPOINTS` | non-secret | JSON map `{"postgres": "http://…/healthz", …}` |
| `CP_PROBE_TOKENS` | **SECRET** | JSON bearer-token map; injected by the deployment secret envelope at runtime, never baked into a layer, never in Git or logs (D-045/D-124) |
| `CP_PROBE_TIMEOUT_MS`, `CP_PROBE_SLOW_MS` | non-secret | integer budgets for probe calls |
| `CP_TELEMETRY_MODE=LIVE` | non-secret | selects the server-side read-only telemetry source |
| `CP_*_SCENARIO` | non-secret, **local-dev only** | scenario switches for mock data; must be **unset** in a deployed container |

Fail-closed behaviour confirmed in code: an unconfigured endpoint leaves the verdict
explicitly unknown (`وضعیت نامشخص`) rather than guessing.

**No data-store credentials.** `package.json` contains no PostgreSQL/Redis client, and
the app has no route handlers or server actions — the D-171 read-only surface holds no
database credentials at all. Its container therefore needs **no** access to the
internal `backend` network of Stage D (postgres-ssot/redis); it reaches the engine
only over HTTP through `CP_PROBE_ENDPOINTS`. This is the strongest security property
of the manifest and should not be traded away for convenience.

**Networking:** zero `ports:` in any deployment manifest — the gateway is the only
surface, mirroring the Stage B "wordpress sole surface" and Stage D edge-exclusivity
rules. Local verification may publish on `127.0.0.1` only.

**Resource ceilings:** mirror the Stage D floors (`mem_limit` 256–512m, `cpus` 0.5–1.0)
plus `read_only: true`, `security_opt: [no-new-privileges:true]`, and `cap_drop: [ALL]`
— all four proven survivable in §2.

---

## 7. Dokploy (Stage D) alignment — one blocking architectural finding

Read directly from `local/infra/dokploy/stage_d_compose_generator.py` (D-144):

1. **Exactly four image slots** are rendered: `POSTGRES_IMAGE`, `REDIS_IMAGE`,
   `APP_IMAGE`, `TELEMETRY_IMAGE`. Every one must be an immutable digest pin
   (`<name>[:<tag>]@sha256:<64 lowercase hex>`); floating tags are refused.
2. **A fifth slot cannot be added by editing the template alone.** After substituting
   the four known slots, the generator rejects any remaining placeholder:
   `if "{{" in text: raise ComposeGeneratorError("unresolved template slots remain — fail closed")`
   → `CANNOT_GENERATE`. A `{{CONTROL_PLANE_IMAGE}}` placeholder would break rendering
   of the *whole* manifest, not just its own service.
3. **Edge attachment is exclusive.** `_EDGE_ALLOWED = ("app-orchestrator",)` and any
   other service attaching `edge` is refused (finding F-3); `_BACKEND_ONLY`
   (postgres-ssot, redis, telemetry-circuit) must be backend-only with zero `ports:`.
   A browser-facing control plane needs `edge`, so it cannot join Stage D's topology
   without amending that ruling.
4. Stage D's healthcheck semantics (`/healthz/worker`, `/healthz/telemetry` on
   `app-orchestrator:8080`) are the **canonical engine's** contract; the Next.js
   control plane serves `:3000` with a different route surface and has no slot
   semantics there.

**Route A (recommended, no Stage D change).** Ship the control plane as its own
Dokploy application with its own manifest that mirrors Stage D's posture verbatim:
digest-pinned image, zero published ports, `read_only: true`, `cap_drop: [ALL]`,
`no-new-privileges`, memory/CPU ceilings, fail-closed `${VAR:?}` env references, and
the §5 healthcheck. The four-slot lineage, its tests, and edge exclusivity stay pinned
and untouched; D-171 remains a separate surface, consistent with its read-only charter.

**Route B (requires an explicit owner ruling).** Extend Stage D itself: add the slot
and service to the template, register it in `REQUIRED_IMAGE_SLOTS`, extend the
topology tuples, and update the Stage D generator tests — including a decision on two
edge-attached services.

Both routes require, at deploy time: the built image **digest-pinned** (no floating
tags), secrets through the envelope, a build from a clean committed tree, and a
re-proof of the container healthcheck inside the deployed environment.

### 7.1 Image size budget

| Component | Measured |
| --- | --- |
| Base `node:20-alpine` | 46.8 MiB |
| `.next/standalone` | 49 MB |
| `.next/static` | 0.88 MB |
| **Uncompressed total, before layer dedup** | **≈ 97 MB** |

Optional trims, each needing its own verification and an owner decision:

- **sharp/@img (27 MB, 55 % of the payload)** — unused today (no `next/image`
  imports). Dropping it is a config-level question, not a Dockerfile trick; verify by
  rebuilding and re-running §2 before claiming the saving.
- **Distroless base** — would remove the shell and `wget`; the §3 healthcheck
  survives (`node -e`), the Stage D-style `wget` probes would not.
- Trimming `next`'s internals is not supported and is not proposed.

---

## 8. Open items (decisions, not tasks)

| # | Item | Owner |
| --- | --- | --- |
| 1 | **G-1**: authorize `control-plane/Dockerfile` + `.dockerignore` from §3/§4 (this document is the specification; nothing is committed) | owner |
| 2 | Add the `/api/health` route (§5 option A) with the full gate battery | owner |
| 3 | Route A vs Route B for the Dokploy seam (§7) — Route B also amends edge exclusivity | owner |
| 4 | Decide on the 27 MB sharp payload trim (§7.1) | owner |
| 5 | Verify the actual `docker build` + deployed-healthcheck convergence once a manifest exists — §2's evidence is for the *payload*, not for a built image | next implementation step |

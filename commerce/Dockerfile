# syntax=docker/dockerfile:1.7
#
# Commerce surface container (D-172 / fashion §6.3 G-1) — materialized from the
# RATIFIED pattern in `docs/deployment/control-plane-container-spec.md` §3, so
# this repository ships ONE Next.js image shape instead of two dialects.
#
# Deployment posture the image is built for (proven survivable in the spec's §2
# and re-asserted by `docker-compose.local.yml`): read_only rootfs,
# cap_drop: [ALL], no-new-privileges, non-root (`node`).
#
# The base is pinned to an OCI *index* digest, never a floating tag: `node:20-
# alpine` resolves to a multi-arch index that also serves amd64 and arm64
# children, so a retag upstream can never silently change this runtime. Stage D
# refuses floating tags for its slots and this image follows the same rule when
# its reference is eventually pinned into a manifest (§6.3 G-8 / C-8).

ARG NODE_IMAGE=node:20-alpine@sha256:fb4cd12c85ee03686f6af5362a0b0d56d50c58a04632e6c0fb8363f609372293

# --- stage 1: dependencies ----------------------------------------------------
# Only the lockfile is copied, so this layer survives every source edit and the
# install is never repeated for a code change.
FROM ${NODE_IMAGE} AS deps
WORKDIR /app
COPY package.json package-lock.json ./
# Scripts are deliberately NOT skipped: Next.js resolution relies on them.
RUN npm ci --no-audit --no-fund

# --- stage 2: build -----------------------------------------------------------
FROM deps AS builder
COPY . .
# `next.config.mjs` declares `output: 'standalone'`, so this emits
# `.next/standalone` (the runner payload). A build without that flag produces no
# runnable server and the runner stage would fail loudly — never silently.
#
# The build reads NO credential: every storefront/admin page is dynamic and the
# data paths fail closed at request time (D-171 §2.2), so an image can be
# produced with no `DATABASE_URL` in the builder environment.
RUN npm run build

# --- stage 3: runtime ---------------------------------------------------------
# Nothing crosses from the builder except the traced server and static assets:
# no sources, no tsconfig, no eslint, no `.test-build`, no package-manager cache.
FROM ${NODE_IMAGE} AS runner

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
WORKDIR /app

COPY --from=builder --chown=node:node /app/.next/standalone ./
COPY --from=builder --chown=node:node /app/.next/static ./.next/static
# `public/` does not exist in this track yet; add the copy when it does:
# COPY --from=builder --chown=node:node /app/public ./public

USER node
EXPOSE ${PORT}

# Probe is `node -e` only — no curl/wget dependency, so it keeps working under a
# hardened rootfs and cannot be broken by a base swap that drops a shell utility.
#
# `/healthz` is the app's own fail-closed readiness contract: 200 only when a
# canonical connection is configured AND answers `SELECT 1`; 503 when the
# configuration is absent or the database is unreachable (it never discloses
# driver text, a version or probe data). Consequence, deliberately chosen: a
# container with no `DATABASE_URL` reports UNHEALTHY instead of a false healthy —
# this surface cannot serve anything without its database, so claiming otherwise
# would be the exact "absent configuration is a pass" error D-171 §2.2 forbids.
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=6 \
  CMD node -e "fetch('http://127.0.0.1:'+(process.env.PORT||3000)+'/healthz').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

CMD ["node", "server.js"]

# syntax=docker/dockerfile:1.7
#
# Control-plane container (D-171) — materialized from
# `docs/deployment/control-plane-container-spec.md` (G-1, owner-authorized).
#
# Deployment posture this image is built for (all four proven in the spec,
# §2, and re-proven per build by the run in §"Build & Run verification"):
#   read_only: true, cap_drop: [ALL], no-new-privileges, non-root (`node`).
#
# The base is pinned to an OCI *index* digest, not a tag: `node:20-alpine`
# resolves to a multi-arch index whose digest also serves amd64 and arm64
# children, so a floating tag can never silently change the runtime. The
# Stage D contract refuses floating tags for its own slots and this image
# follows the same rule when its reference is pinned into a manifest.

ARG NODE_IMAGE=node:20-alpine@sha256:fb4cd12c85ee03686f6af5362a0b0d56d50c58a04632e6c0fb8363f609372293

# --- stage 1: dependencies ----------------------------------------------------
# Only the lockfile is copied, so this layer survives every source edit and the
# dependency install is never repeated for a code change.
FROM ${NODE_IMAGE} AS deps
WORKDIR /app
COPY package.json package-lock.json ./
# Scripts are deliberately NOT skipped: Next.js resolution relies on them.
# The sizes are reported by the build so the runtime payload stays auditable.
RUN npm ci --no-audit --no-fund

# --- stage 2: build ----------------------------------------------------------
FROM deps AS builder
COPY . .
# Emits `.next/standalone` because next.config.mjs declares
# `output: 'standalone'`; a build without it produces no runner payload.
RUN npm run build

# --- stage 3: runtime --------------------------------------------------------
# Nothing from the builder survives except the traced server + static assets:
# no sources, no test artifacts, no package manager cache, no npm install.
FROM ${NODE_IMAGE} AS runner

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
WORKDIR /app

COPY --from=builder --chown=node:node /app/.next/standalone ./
COPY --from=builder --chown=node:node /app/.next/static ./.next/static
# `public/` does not exist yet; add the copy when it does:
# COPY --from=builder --chown=node:node /app/public ./public

USER node
EXPOSE ${PORT}

# Probe is `node -e` only — no curl/wget dependency, so the image keeps working
# under a hardened rootfs and the check does not depend on a shell utility that
# a future base swap could remove. `/api/health` is dependency-free and
# discloses nothing (no version, no probe data).
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=6 \
  CMD node -e "fetch('http://127.0.0.1:'+(process.env.PORT||3000)+'/api/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

CMD ["node", "server.js"]

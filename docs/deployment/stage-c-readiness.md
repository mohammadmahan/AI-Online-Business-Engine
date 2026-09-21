# Stage C Readiness Report — Target Host Sizing & Pre-Provisioning Baseline

- Work package: **Dokploy Deployment Integration** (D-141, Approved).
- Status: **PLANNED readiness artifact.** No host exists, nothing has been
  provisioned. This report and the harness
  (`local/scripts/validate_vps_target.py`) are the Stage C sizing
  deliverables; execution requires the per-item owner authorizations in
  `docs/deployment/dokploy-plan.md` §17/§21.6 and the runbook
  `docs/runbooks/dokploy-vps-provisioning.md` §0.
- Sibling procedures: the host probe
  (`local/scripts/validate_vps_readiness.py`) verifies OS/SSH/ports on an
  already-provisioned host; this report sizes the host **before** it is
  provisioned and the target harness re-verifies the full runtime
  envelope (Docker ≥ 24, cgroup v2, subnets, volume layout).

## 1. Authority gates (binding)

- **D-139:** production activation is a separately owner-authorized,
  gated sequence. Stage C provisioning produces a *staging* host only;
  nothing here authorizes Production activation.
- **D-141:** every external action (VPS provisioning, installer
  execution, firewall changes, DNS, GitHub app connection, backup
  credentials) requires its own explicit owner authorization — the
  checklists below are the authorization inventory.
- **D-045:** no live credentials exist in this repository. All secret
  material is injected at deploy time via `${VAR:?}` references; the
  harness never accepts, stores, or transmits secret values.
- Nothing in this stage runs unless a human owner executes it. All
  probes are **read-only**: the harness mutates nothing on any host.

## 2. Resource footprint (derived from the validated `compose.prod.yml`)

The manifest is the single source for these numbers (validated
empirically in the D-141 §24 record: isolated up → hardening inspect →
seam writability → gateway-less egress → SSOT migration 13/13).

### 2.1 Container resource ceilings (hard limits in the manifest)

| Service | Image (digest-pinned) | Memory limit | CPU limit |
|---|---|---|---|
| wordpress | `wordpress:6.5-php8.3-apache` @ digest | 512 MiB | 1.0 |
| woodb | `mysql:8.0` @ digest | 1 GiB | 1.0 |
| canonical-db | `postgres:16-alpine` @ digest | 512 MiB | 1.0 |
| n8n | `n8nio/n8n` @ digest | 1 GiB | 0.5 |
| media | `minio/minio` @ digest | 256 MiB | 0.5 |
| **Total** | **5 services** | **3.25 GiB (3328 MiB)** | **4.0 CPUs** |

### 2.2 Derived host baseline

- **vCPU:** the sum of CPU ceilings is 4.0; a 2 vCPU floor is the
  minimum viable host (limits are ceilings, not reservations), **4
  vCPU recommended** so concurrent image pulls / migrations / health
  probes do not contend.
- **Memory:** 3.25 GiB of container ceilings + host OS (~0.5 GiB) +
  Dokploy control plane (containerized Docker/Traefik stack, ~0.5–1
  GiB observed class) + peak in-container usage above limits being
  impossible ⇒ **6 GiB floor, 8 GiB recommended**. Swap: 2 GiB
  swapfile recommended (cgroup-v2 memory+swap accounting), never as a
  substitute for RAM.
- **Disk:** image budget ≈ **8 GB** (wordpress ~0.6, mysql ~0.6,
  postgres ~0.25, n8n ~0.5, minio ~0.15, plus dokploy/traefik and
  build layers ⇒ ~4–5 GB images + headroom); named volumes for
  PGDATA/datadir/media/n8n start near zero and grow with data; logs
  and pull-cache need headroom ⇒ **40 GB floor (matches the runbook's
  30 GB Dokploy floor plus project volumes), 80 GB recommended**.
- **Disk I/O:** the two databases (MySQL, PostgreSQL) are the only
  latency-sensitive writers; SSD-class storage is **required**
  (runbook floor), tens of MB/s sustained is sufficient at this scale.
- **Kernel:** cgroup v2 unified hierarchy is **required** — the
  manifest's `mem_limit`/`cpus` and the swap accounting depend on it
  (harness check C-04). Docker engine **≥ 24.x** with the compose v2
  plugin (**required**, harness C-03).
- **Architecture:** x86_64 (all pinned digests resolved for
  `linux/amd64`).

## 3. Network & security posture

- **Ingress:** ports **80/443 only**, terminating at the single
  frontend surface (WordPress in the validated topology; the Dokploy
  gateway/Traefik when adopted). Port 3000 is the Dokploy UI and must
  be **closed to the public internet** (tunnel or admin-IP allowlist).
- **Internal isolation:** the `data` network is `internal: true`
  (verified gateway-less: no default route, no egress). Only
  WordPress joins `frontend` + `data`; woodb/canonical-db/n8n/media
  are data-network-only. Databases are **never** port-published.
- **Firewall (UFW) baseline** — deny incoming, allow outgoing, allow
  22 (admin source-limited), 80, 443; explicitly deny 3000 from
  non-admin sources. Docker's iptables bypass is a known class of
  finding: the harness reports published-port drift (currently zero
  ports published) and UFW state.
- **SSH hardening:** key-only auth (`PasswordAuthentication no`),
  `PermitRootLogin no`, non-root sudo admin user (runbook §2 steps).
- **Secrets posture:** 9 mandatory `${VAR:?}` references in the prod
  manifest (WORDPRESS_DB_PASSWORD, MYSQL_PASSWORD, MYSQL_ROOT_PASSWORD,
  CANONICAL_DB_NAME/USER/PASSWORD, N8N_ENCRYPTION_KEY,
  MINIO_ROOT_USER/PASSWORD) — all fail-closed, all injected at deploy,
  none committed. §6 is the activation credential checklist.

## 4. Volume layout

| Volume (named) | Consumer | Content |
|---|---|---|
| woo_data | wordpress | WordPress/Woo files |
| woo_data_db | woodb (mysql) | MySQL datadir (+ socket tmpfs seam) |
| canonical_data | canonical-db (postgres) | SSOT data — D-125 backup scope |
| n8n_data | n8n | workflow state (durable) |
| media_data | media (minio) | object storage — off-host archive target |
| (tmpfs) /home/node/.cache | n8n | uid-1000-owned, non-durable by design |

Backup/retention mapping to the D-125 drill requirements lives in
`docs/deployment/staging-volume-backup-policy.md`.

## 5. Harness: `local/scripts/validate_vps_target.py`

Two strictly separated modes (exit 0 pass / 1 findings / 2 cannot
assess; all output redacted per D-124):

- **OFFLINE (default):** pure synthesis, no host contacted —
  environment-variable schema (references only, refuses
  secret-shaped values per D-045), required volume path plan against
  the manifest, Docker engine ≥ 24.x + compose v2 constraint table,
  and **subnet-collision detection** between the manifest's declared
  networks and a set of disallowed/overlapping CIDRs (host VPN, admin
  net, Dokploy defaults).
- **TARGET PROBE (opt-in `--host`):** SSH batch-mode, **read-only**
  commands only (an allowlist pins every permitted remote command —
  same discipline as `validate_vps_readiness.py`): OS/CPU/RAM/disk,
  docker engine + compose version, cgroup v2 detection, UFW state,
  80/443/3000 listeners, and a re-check of subnet overlap against the
  host's live docker networks. Emits PASS/FAIL per check with
  actionable remediation text.

## 6. Credential checklist (dry-run → live activation ONLY)

To be provided **per-item, per-environment** by the owner; never
committed:

| Credential | Consumer | Stage gating |
|---|---|---|
| VPS provider API/SSH key | provisioning | Stage C owner authorization |
| GitHub deploy key / app | Dokploy builds | separate owner authorization |
| WORDPRESS_DB_PASSWORD | wordpress→woodb | deploy env |
| MYSQL_PASSWORD / MYSQL_ROOT_PASSWORD | woodb | deploy env |
| CANONICAL_DB_NAME/USER/PASSWORD | canonical-db | deploy env |
| N8N_ENCRYPTION_KEY | n8n | deploy env |
| MINIO_ROOT_USER/PASSWORD | media | deploy env |
| Off-host (S3-compatible) backup keys | D-125 archive | Stage D/F authorization |
| Platform live keys (Woo/IG/AI/Telegram) | D-045 adapters | **explicit** RED-tier owner gates |

## 7. Exit criteria

Stage C is complete when: (1) this report's floor is met by the chosen
host, (2) `validate_vps_target.py --host …` returns exit 0, (3)
`validate_vps_readiness.py` returns exit 0, and (4) each §6 row has its
explicit owner authorization recorded — in that order. Fail-closed: any
missing evidence blocks Stage D, never assumes a pass.

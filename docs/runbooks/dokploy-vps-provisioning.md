# Runbook: Dokploy VPS Provisioning & Installation (Stage C — PLANNED)

- Work package: **Dokploy Deployment Integration** (D-141, Approved).
- Status: **PLANNED readiness artifact.** No host exists, nothing has
  been provisioned or installed. This runbook plus
  `local/scripts/validate_vps_readiness.py` are the Stage C readiness
  deliverables — execution requires the per-item owner authorizations
  in `docs/deployment/dokploy-plan.md` §17/§21.6.
- Sibling procedures: `docs/runbooks/dokploy-deployment.md` (app
  onboarding), `docs/runbooks/dokploy-disaster-recovery.md`,
  `docs/runbooks/dokploy-exit-plan.md`.

## 0. Owner authorization gates (fail closed — verify BEFORE anything)

Each item is a **separate, explicit owner authorization** (§21.6);
none is implied by this runbook existing:

| # | Gate | Evidence of grant |
|---|---|---|
| G1 | VPS provisioning (provider, size, region) | owner message naming provider/size/region |
| G2 | Installer execution (internet-downloaded) | owner approval of the exact pinned version below |
| G3 | Firewall ports opening | owner-approved port list (this runbook's table) |
| G4 | GitHub connection (read-scoped) | owner approval of scope = the one repo, read-only |
| G5 | Staging DNS record | owner-approved hostname |
| G6 | S3/backup credentials | owner approval of bucket + prefix scope |

Also confirm from §19/§21.6: RPO/RTO approved · n8n access model
(SSH-tunnel default) · webhook decision (manual-only default) ·
edition/version pinned · host sizing · stateful-service management
choice. **Any missing gate → stop.**

## 1. System requirements (host)

| Item | Requirement | Source/rationale |
|---|---|---|
| OS | Ubuntu 22.04 LTS (or another Dokploy-documented supported distro) | official installation docs (§18, reviewed 2026-09-20) |
| RAM | ≥ 2 GB documented floor; **4 GB recommended** for the 5-service staging stack + builds | §19 Q4 |
| Disk | ≥ 30 GB documented floor; **60 GB recommended** (images ×6 + volumes + build cache) | §19 Q4 |
| Arch | x86_64 or arm64 (multi-arch index pins in `compose.staging.yml` cover both) | F-8 |
| Region/sanctions | per the Phase 4 G1 brief's open provider question — owner decision, unchanged | D-058 deferral stands |
| Provider | any; the manifest is provider-neutral (D-129/D-130) — exit drill (Stage H) does not depend on it | Phase 24 |

## 2. Firewall & port plan (G3 scope)

| Port | Service | Exposure rule |
|---|---|---|
| 22 | SSH | restricted to admin source IP(s); key-only (below) |
| 80 | Traefik (HTTP→HTTPS) | public — required for staging domain TLS |
| 443 | Traefik (HTTPS) | public — staging app surface |
| 3000 | **Dokploy UI** | **NEVER public** — allowlist admin IP(s) only (§11) |
| 18080 | WordPress raw (staging manifest) | **closed by default** — decided at Stage C onboarding; the Traefik domain path is preferred |

UFW baseline (execute on the host, after G3 grant):

```bash
ufw default deny incoming
ufw default allow outgoing
ufw allow from <ADMIN_IP> to any port 22 proto tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow from <ADMIN_IP> to any port 3000 proto tcp
ufw enable
```

## 3. SSH hardening (before installer)

1. Create the admin user; authorize **key-only** access.
2. `/etc/ssh/sshd_config`: `PasswordAuthentication no`,
   `PermitRootLogin no`, `PubkeyAuthentication yes` → restart sshd.
3. Keep the provider's recovery console as break-glass; record its
   access path in the owner's password manager (never in Git).
4. From the admin machine: `ssh -o BatchMode=yes <user>@<host> true`
   must succeed without a password before proceeding.

## 4. Pre-install validation (READ-ONLY probe — no changes)

Run from the admin machine **before** any install:

```bash
python3 local/scripts/validate_vps_readiness.py \
  --host <STAGING_HOST> --user <ADMIN_USER> \
  [--key ~/.ssh/staging_ed25519] [--port 22]
```

Checks (all read-only: `cat /etc/os-release`, `free -m`, `df -BG`,
`ss -tlnp`, `sshd -T`, `grep` on sshd_config, `command -v docker`,
`docker --version`, `docker compose version`, `ufw status`): reachability · OS in supported set · RAM/disk floors ·
ports 80/443/3000 free (or Dokploy already present) · SSH hardened
(password auth off, root login off) · Docker + compose plugin
presence (report-only) · UFW active. **Exit 0 = ready, 1 = finding,
2 = connectivity/environment problem.** The script never mutates the
host; installing/fixing is the operator's separate, gated action.

## 5. Dokploy installation (G2 — clean, pinned, Docker-based)

Official method (reviewed 2026-09-20, §18): the installer runs the
Dokploy Docker container with a Postgres control plane and Traefik on
the host; ports 80/443/3000 must be free.

- **Pin the version** (`export DOKPLOY_VERSION=<x.y.z>` — the exact
  value is an owner-approved Stage C input; never `latest` for a
  governed deployment).
- Fetch the installer over HTTPS, **review it**, then execute:

```bash
curl -fsSL https://dokploy.com/install.sh -o /tmp/dokploy-install.sh
less /tmp/dokploy-install.sh            # human review before executing
bash /tmp/dokploy-install.sh
```

- Record in the verification log: pinned version, installer content
  hash, install timestamp, resulting container list.

## 6. Initial security configuration (immediately after install)

1. **Bootstrap admin account** from the UI (port 3000, via the
   admin-IP allowlist) — create the owner admin, enable 2FA/passkey
   **if the selected edition supports it** (paid plans per §18);
   otherwise record the compensating control (IP allowlist + short
   session policy) as the documented residual risk.
2. Complete any forced first-run setup before exposing anything.
3. Generate the **staging-scoped webhook** only if the owner approved
   webhooks (default: manual deploys); treat the URL as a credential.
4. Connect GitHub with **read scope on this repository only** (G4).
5. Configure the S3 backup destination with **separate
   minimum-privilege credentials** (G6), per
   `staging-volume-backup-policy.md`; `canonical_data` schedule first.
6. Turn OFF any production/auto-deploy toggles; staging only.

## 7. Post-install acceptance (gate to app onboarding)

- [ ] `validate_vps_readiness.py` exits 0.
- [ ] UI reachable ONLY from the allowlisted admin IP (probe from a
      non-allowlisted network must fail).
- [ ] 80/443 serve Traefik's default response; nothing else public
      (`ss -tlnp` reviewed against the port table).
- [ ] Dokploy control plane containers healthy; version matches pin.
- [ ] Install record (version, hash, timestamp, containers) appended
      to the runbook's verification log section below.

## 8. Rollback / removal (host-level)

Dokploy is a Docker deployment — removal is container/volume teardown,
not host surgery: stop and remove the Dokploy containers and their
volumes (control-plane DB + `/etc/dokploy`), leave Traefik decision to
the owner (it may be reused), and re-run
`validate_vps_readiness.py` expecting a clean, Dokploy-free host.
Application volumes/data are untouched by control-plane removal. The
full exit procedure is `dokploy-exit-plan.md` (Stage H); no deletion
of any project data is authorized by this runbook.

## 9. Verification log (append-only, operator-maintained)

```
# date | action | version | evidence (hashes, outputs) | operator
# (empty — nothing executed yet; entries only after owner-gated execution)
```

## 10. Stop conditions

Any of: a gate from §0 unmet · installer hash/version mismatch · a
readiness check fails and the fix would exceed the granted scope ·
evidence cannot be produced · security posture degrades (new public
port, password SSH). **Stop and report; never improvise a fix that
widens access.**

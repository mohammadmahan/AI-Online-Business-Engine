# Stage C — VPS Host Prerequisites Specification (D-143)

- Work package: **Dokploy Deployment Integration** (D-141, Approved).
- Status: **SPECIFICATION — machine-enforced by
  `local/infra/dokploy/stage_c_runbook_validator.py` (VC-01..VC-14).
  Nothing provisioned; execution remains owner-gated per
  `docs/deployment/dokploy-plan.md` §17/§21.6 and the G1–G6 gates in
  `docs/runbooks/dokploy-vps-provisioning.md`.**
- Siblings: `docs/deployment/stage-c-readiness.md` (sizing derivation
  from the validated manifest), `docs/runbooks/dokploy-vps-provisioning.md`
  (the owner-gated procedure), `local/scripts/validate_vps_target.py`
  (offline plan verification + opt-in READ-ONLY SSH probe). This
  document is the *host-prerequisites contract* those harnesses
  enforce; where numbers overlap they MUST stay in sync (drift is a
  battery failure).

## 1. Scope and non-goals

Defines what a host MUST look like **before** the Dokploy installer is
allowed to run (runbook §5), and how each requirement is checked. It
does NOT authorize provisioning, installation, DNS changes, or any
live action — every execution step requires its per-item owner
authorization (§6 here, G-gates in the runbook).

## 2. Host sizing and OS baseline (VC-01..VC-05)

| Dimension | Floor | Recommended | Source / check |
|---|---|---|---|
| OS family | Debian 12 / Ubuntu 22.04+ | Ubuntu 24.04 LTS | VC-01 (`os_pretty_name`) |
| Kernel | 5.10 | current LTS | VC-02 (`kernel_release`) |
| vCPU | 2 | 4 | `stage-c-readiness.md` §2.2 (SSH probe C-02) |
| RAM | 6 GiB | 8 GiB | manifest ceilings 3328 MiB + host overhead |
| Root disk | 40 GB | 80 GB | images + volumes + logs + D-125 archives |
| Docker Engine | ≥ 24.0 | latest stable | VC-03 (`docker_version_text`) |
| Compose | v2 plugin | — | VC-04 (`docker_compose_ok`) |
| cgroup | v2 unified | — | VC-05 (`cgroup_controllers` contains `cpu`) |

Rationale for the Docker/cgroup floors: the hardened
`local/infra/compose.prod.yml` sets CPU/memory ceilings on every
container; these require cgroup v2 and a recent engine. A host that
cannot report these facts cleanly is **CANNOT_ASSESS** (fail-closed) —
an unparseable observation is never treated as a pass.

## 3. Port boundary contract (VC-06, VC-07)

| Port | Role | Required state |
|---|---|---|
| 80 | HTTP gateway / ACME challenge | FREE before install; afterwards bound ONLY by the gateway/proxy container |
| 443 | HTTPS gateway / TLS termination | FREE before install; afterwards gateway-only |
| 3000 | Dokploy management UI | **NEVER publicly bound** — internal-network or loopback/VPN reachability only |
| 5432 | PostgreSQL SSOT | **NEVER publicly bound** — data network internal only |
| 6379 | Redis broker/cache | **NEVER publicly bound** — data network internal only |

- VC-06 fails closed if 80/443 are pre-bound by any unmanaged process
  (collision ⇒ the installer or gateway cannot own the TLS surface).
- VC-07 fails closed on any public binding (`0.0.0.0`, `::`, `*`) of
  3000/5432/6379; a loopback-only binding degrades to a **warning** and
  must be justified by the operator in the verification log.

## 4. Firewall policy (UFW) (VC-08..VC-10)

1. **UFW active** (VC-08) — `sudo ufw status verbose` shows
   `Status: active`. Hosts without a verifiable firewall profile are
   NOT_READY (firewall facts must be *parseable UFW output*, not
   assurances).
2. **Default incoming deny** (VC-09) — `Default: deny (incoming)`;
   `drop`/`reject` accepted, anything else fails closed.
3. **Ingress allowlist ⊆ {22, 80, 443}** (VC-10) — application ports
   (3000/5432/6379 and every internal service) must NEVER appear as
   public ALLOW rules; reachability for administration goes through
   SSH (22) or an owner-approved VPN, not through opened ports.
4. **Egress** — default allow; outbound restrictions (if the owner
   adds them) must be documented here first and mirrored in the
   validator before enforcement, never the reverse.
5. iptables-equivalent setups are out of scope for VC-08..VC-10:
   if UFW is not the management layer, the owner must extend the
   validator with an equivalent adapter BEFORE provisioning (no
   "iptables looks fine" verbal passes).

## 5. Installer isolation and TLS termination (VC-12, VC-13)

- **Pinned installer** (VC-12): `DOKPLOY_INSTALLER_REF` must be a
  pinned semver tag (`vX.Y.Z`). `latest`, branch names, and bare URLs
  are refused — an unpinned internet-downloaded installer is a supply-
  chain hazard (runbook G2 requires the same pin).
- **Installer isolation:** the installer runs from the pinned ref in a
  clean session; no other setup scripts run concurrently; the host has
  no pre-existing containers from other projects (verified by the SSH
  probe before install).
- **TLS termination:** terminates at the gateway layer in front of
  Dokploy (ports 80/443 only); ACME HTTP-01 requires port 80 reachable
  before certificate issuance; certificates auto-renew behind the
  gateway. `DOKPLOY_DOMAIN` (VC-13) must be a bare hostname — no
  scheme, path, userinfo, or whitespace; credential material in the
  domain value is a hard refusal.
- **DNS (G5):** the domain's A/AAAA record pointing at the host is an
  owner-authorized change — it happens AFTER this validator passes,
  never before.

## 6. Owner sign-off attestations (VC-14) and evidence validity

The validator requires explicit attestation strings for the five
provisioning gates before verdict READY:

| Gate | Attestation key | Meaning |
|---|---|---|
| G1 | `G1_HOST` | VPS provisioned / approved for provisioning |
| G2 | `G2_INSTALLER` | pinned installer ref approved to run |
| G3 | `G3_FIREWALL` | UFW plan approved to apply |
| G4 | `G4_SSH` | SSH hardening applied / approved |
| G5 | `G5_DNS` | DNS change approved |

Evidence-validity model (mirrors D-138): the report binds the
environment **fingerprint** (sha256 over sorted `NAME=sha256(value)`
pairs — no values ever leave the host); any change to the planning
environment, host facts, or validator invalidates the previous READY
verdict and it must be re-earned. Attestations are owner-issued
strings (name + date or token reference), never inferred from
silence.

## 7. Secret handling (D-124/D-045)

- Planning-env **values are never read out, stored, printed, or
  transmitted**; findings carry variable NAMES and presence booleans
  only.
- Every finding detail passes `deep_redact` before leaving the
  validator — even an operator pasting a secret into a facts file
  cannot leak it through a report.
- The facts JSON consumed by the CLI is the only file input; an
  unparseable file yields exit 2 (CANNOT_ASSESS), never a guess.

## 8. Verdicts and exit codes

| Verdict | Exit | Meaning |
|---|---|---|
| `READY` | 0 | all VC-01..VC-14 satisfied (warnings allowed, none critical) |
| `NOT_READY` | 1 | ≥ 1 critical finding — provisioning must not proceed |
| `CANNOT_ASSESS` | 2 | host observations missing/unparseable — fail-closed |

Usage (dry-run, no sockets):
`python3 local/infra/dokploy/stage_c_runbook_validator.py --facts-file FACTS.json --json`

## 9. Official references

- Dokploy docs — requirements & installation (reviewed 2026-09-20 for
  D-141; re-verify before any real install): system requirements,
  Docker-based installer, port 3000 management surface, domain/HTTPS
  handling.
- `docs/runbooks/dokploy-vps-provisioning.md` §1–§5 (G1–G6 gates,
  UFW/SSH hardening, pinned installer).
- `docs/deployment/stage-c-readiness.md` §2 (derived sizing floors —
  must equal the numbers in §2 here).

## 10. Unresolved owner decisions

- VPN vs exposed-SSH administration posture (affects VC-10 exceptions —
  currently NONE are allowed).
- Egress restriction policy (§4.4) — default allow until owner rules.
- Host provider choice / budget ceiling — required before G1.

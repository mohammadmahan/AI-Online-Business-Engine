#!/usr/bin/env python3
"""validate_vps_readiness.py — Stage C pre-install VPS probe (D-141).

READ-ONLY readiness verification of a staging VPS BEFORE Dokploy
installation. Every check runs over SSH in non-interactive batch mode
and MUTATES NOTHING — the script never installs packages, never edits
config, never opens ports. Fixing findings is the operator's separate,
owner-gated action (docs/runbooks/dokploy-vps-provisioning.md §0/§4).

Checks:
  1. CONNECTIVITY  — SSH batch-mode login works (key auth, no prompt).
  2. OS            — distribution is in the Dokploy-documented supported
                     set (Ubuntu/Debian families per official docs,
                     reviewed 2026-09-20).
  3. RESOURCES     — RAM ≥ 2 GB floor (4 GB recommended) and disk ≥ 30 GB
                     floor (60 GB recommended) on the root filesystem.
  4. PORTS         — 80/443/3000 free, or Dokploy/Traefik already bound
                     (idempotent re-run support).
  5. SSH HARDENING — PasswordAuthentication and PermitRootLogin are off.
  6. DOCKER        — Docker + compose plugin presence (report-only;
                     absence is a finding, not a mutation trigger).
  7. UFW           — firewall active (report-only finding if not).

Exit codes: 0 = ready · 1 = one or more findings · 2 = connectivity or
environment problem (cannot assess). Secrets: the key PATH may be
passed; no credentials are read, stored, or transmitted anywhere.

Usage:
  python3 local/scripts/validate_vps_readiness.py \
      --host <HOST> --user <ADMIN_USER> [--key <KEY_PATH>] [--port 22]
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys

RAM_FLOOR_MB = 2000        # official documentation floor
RAM_RECOMMENDED_MB = 4000
DISK_FLOOR_GB = 30         # official documentation floor
DISK_RECOMMENDED_GB = 60
CHECK_PORTS = (80, 443, 3000)
OK_OS_IDS = {"ubuntu", "debian", "raspbian", "linuxmint"}
OK_OS_LIKE = ("ubuntu", "debian")
OK_DOKPLOY_LISTENERS = ("traefik", "dokploy")


class Findings:
    def __init__(self) -> None:
        self.items: list[tuple[str, str, str]] = []  # (status, check, detail)

    def ok(self, check: str, detail: str) -> None:
        self.items.append(("OK  ", check, detail))
        print(f"  [OK  ] {check}: {detail}")

    def finding(self, check: str, detail: str) -> None:
        self.items.append(("FAIL", check, detail))
        print(f"  [FAIL] {check}: {detail}")

    def blocked(self, check: str, detail: str) -> None:
        self.items.append(("ENV ", check, detail))
        print(f"  [ENV ] {check}: {detail}")

    @property
    def failed(self) -> bool:
        return any(s == "FAIL" for s, _, _ in self.items)


def ssh_run(args, user: str, host: str, port: int, key, timeout: int,
            cmd: str) -> tuple[int, str, str]:
    ssh_cmd = [
        "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
        "-o", "StrictHostKeyChecking=accept-new", "-o", "LogLevel=ERROR",
        "-p", str(port),
    ]
    if key:
        ssh_cmd += ["-i", str(key)]
    ssh_cmd += [f"{user}@{host}", cmd]
    try:
        proc = subprocess.run(ssh_cmd, capture_output=True, text=True,
                              timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, "", f"ssh timed out after {timeout}s"
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--host", required=True, help="staging VPS hostname/IP")
    ap.add_argument("--user", required=True, help="admin SSH user")
    ap.add_argument("--key", default=None, help="SSH private key PATH")
    ap.add_argument("--port", type=int, default=22)
    ap.add_argument("--timeout", type=int, default=20,
                    help="per-command SSH timeout seconds")
    args = ap.parse_args()

    print(f"=== VPS readiness probe (Stage C, D-141) — {args.user}@{args.host}:{args.port} ===")
    print("Mode: READ-ONLY — this script mutates nothing on the host.")

    f = Findings()

    # 1. connectivity ------------------------------------------------------
    rc, out, err = ssh_run(args, args.user, args.host, args.port, args.key,
                           args.timeout, "true")
    if rc != 0:
        print(f"  [ENV ] connectivity: SSH login failed rc={rc}: "
              f"{(err or out)[:200]}")
        print("=== CANNOT ASSESS (exit 2) — fix connectivity, rerun ===")
        sys.exit(2)
    f.ok("connectivity", "SSH batch-mode login succeeded (key auth)")

    def run(cmd: str) -> tuple[int, str]:
        rc, out, err = ssh_run(args, args.user, args.host, args.port,
                               args.key, args.timeout, cmd)
        return rc, (out if rc == 0 else f"{out} {err}".strip())

    # 2. OS ------------------------------------------------------------------
    rc, out = run("cat /etc/os-release 2>/dev/null | head -5")
    m_id = re.search(r'^ID=("?)([\w\-]+)\1', out, re.M)
    m_like = re.search(r'^ID_LIKE=("?)([\w\- ]+)\1', out, re.M)
    os_id = (m_id.group(2).lower() if m_id else "")
    os_like = (m_like.group(2).lower() if m_like else "")
    if os_id in OK_OS_IDS or any(l in os_like for l in OK_OS_LIKE):
        f.ok("os", f"{os_id or 'unknown'} (ID_LIKE={os_like or 'none'}) "
                   f"— in documented supported set")
    else:
        f.finding("os", f"{os_id or 'unknown'} (ID_LIKE={os_like or 'none'}) "
                        f"— verify against current official docs")

    # 3. resources -------------------------------------------------------------
    rc, out = run("free -m | awk '/^Mem:/{print $2}'")
    try:
        ram_mb = int(out)
    except ValueError:
        ram_mb = -1
    if ram_mb >= RAM_RECOMMENDED_MB:
        f.ok("ram", f"{ram_mb} MB ≥ recommended {RAM_RECOMMENDED_MB} MB")
    elif ram_mb >= RAM_FLOOR_MB:
        f.finding("ram", f"{ram_mb} MB meets documented floor "
                         f"{RAM_FLOOR_MB} MB but is below recommended "
                         f"{RAM_RECOMMENDED_MB} MB (5-service staging stack)")
    else:
        f.finding("ram", f"{ram_mb} MB below documented floor "
                         f"{RAM_FLOOR_MB} MB")

    rc, out = run("df -BG / | awk 'NR==2{print $4}' | tr -d G")
    try:
        disk_gb = int(out)
    except ValueError:
        disk_gb = -1
    if disk_gb >= DISK_RECOMMENDED_GB:
        f.ok("disk", f"{disk_gb} GB available ≥ recommended "
                     f"{DISK_RECOMMENDED_GB} GB")
    elif disk_gb >= DISK_FLOOR_GB:
        f.finding("disk", f"{disk_gb} GB meets documented floor "
                          f"{DISK_FLOOR_GB} GB but is below recommended "
                          f"{DISK_RECOMMENDED_GB} GB (images+volumes+cache)")
    else:
        f.finding("disk", f"{disk_gb} GB below documented floor "
                          f"{DISK_FLOOR_GB} GB")

    # 4. ports 80/443/3000 ---------------------------------------------------
    rc, out = run("ss -tlnp 2>/dev/null || netstat -tlnp 2>/dev/null")
    for port in CHECK_PORTS:
        listeners = [ln for ln in out.splitlines()
                     if re.search(rf"[:.]{port}\s", ln)]
        named = ", ".join(
            ln.split("users:")[0][-30:] for ln in listeners[:2]
        ) if listeners else ""
        if not listeners:
            f.ok(f"port {port}", "free")
        elif any(k in out.lower() for k in OK_DOKPLOY_LISTENERS) and \
                any(k in ln.lower() for k in OK_DOKPLOY_LISTENERS
                    for ln in listeners):
            f.ok(f"port {port}", f"bound by dokploy/traefik (idempotent rerun): {named}")
        else:
            f.finding(f"port {port}",
                      f"bound by another process: {named} — free it or "
                      f"identify it before install")

    # 5. SSH hardening --------------------------------------------------------
    rc, out = run("sshd -T 2>/dev/null | grep -iE '^(passwordauthentication|permitrootlogin)'")
    if rc != 0:
        rc2, out2 = run("grep -riE '^\\s*(PasswordAuthentication|PermitRootLogin)\\s+yes' /etc/ssh/sshd_config /etc/ssh/sshd_config.d/ 2>/dev/null")
        if rc2 == 0 and out2:
            f.finding("ssh-hardening", f"explicit yes-configuration found: {out2[:120]}")
        else:
            f.finding("ssh-hardening",
                      "sshd -T unavailable and no explicit yes-config found — "
                      "verify manually before proceeding")
    else:
        pw = re.search(r"passwordauthentication\s+(\S+)", out, re.I)
        pr = re.search(r"permitrootlogin\s+(\S+)", out, re.I)
        pw_ok = pw and pw.group(1).lower() == "no"
        pr_ok = pr and pr.group(1).lower() == "no"
        if pw_ok and pr_ok:
            f.ok("ssh-hardening", "PasswordAuthentication=no, PermitRootLogin=no")
        else:
            f.finding("ssh-hardening",
                      f"passwordauthentication={pw.group(1) if pw else '?'}, "
                      f"permitrootlogin={pr.group(1) if pr else '?'} — "
                      f"harden before install")

    # 6. docker ------------------------------------------------------------------
    rc, out = run("command -v docker && docker --version")
    if rc == 0:
        f.ok("docker", out.splitlines()[-1][:80])
        rc, out = run("docker compose version")
        if rc == 0:
            f.ok("docker-compose", out.splitlines()[0][:80])
        else:
            f.finding("docker-compose", "compose plugin missing")
    else:
        f.finding("docker", "not installed — install as a separate gated action")

    # 7. ufw ----------------------------------------------------------------------
    rc, out = run("ufw status 2>/dev/null | head -1")
    if rc == 0 and "active" in out.lower():
        f.ok("ufw", "firewall active")
    elif rc == 0:
        f.finding("ufw", "firewall present but INACTIVE — enable per runbook §2")
    else:
        f.finding("ufw", "ufw unavailable — verify host firewall manually")

    # verdict ------------------------------------------------------------------------
    print("=== Readiness verdict ===")
    n_fail = sum(1 for s, _, _ in f.items if s == "FAIL")
    if f.failed:
        print(f"NOT READY: {n_fail} finding(s). Fix as separate owner-gated "
              f"actions; rerun until exit 0. Nothing was modified.")
        sys.exit(1)
    print("READY: all checks passed. Provisioning/install may proceed only "
          "under the runbook §0 owner gates. Nothing was modified.")
    sys.exit(0)


if __name__ == "__main__":
    main()

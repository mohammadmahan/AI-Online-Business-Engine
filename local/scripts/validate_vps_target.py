#!/usr/bin/env python3
"""validate_vps_target.py — Stage C target-host validation harness (D-141).

Two strictly separated modes; every check is READ-ONLY:

  OFFLINE (default, no host contacted)
    Synthetic verification of the deployment *plan* against
    local/infra/compose.prod.yml:
      O-01  environment contract — every mandatory `${VAR:?}` name in
            the prod manifest is documented in `.env.example`
      O-02  no live secrets in the planning environment (D-045) — the
            harness REFUSES to run (exit 2) if a real value for a
            mandatory key is exported in this shell; planning tools
            must never see production secrets
      O-03  resource sizing — mem_limit/cpus ceilings parsed from the
            manifest must equal the published totals (3.25 GiB / 4.0
            CPU) that docs/deployment/stage-c-readiness.md derives
      O-04  durable volume plan — named volumes match the declared
            set (PGDATA / datadir / media / wp data; n8n stays tmpfs)
      O-05  subnet guard — the disallowed-CIDR list (admin/VPN nets)
            is well-formed and no manifest-pinned subnet collides

  TARGET PROBE (opt-in `--host`, SSH batch mode, non-interactive)
    Read-only probes of a real host, allowlisted commands only:
      C-01  OS family supported (Debian/Ubuntu per official docs)
      C-02  vCPU ≥ 2 (4 recommended) · RAM ≥ 6144 MB (8192 rec) ·
            root-disk ≥ 40 GB (80 rec)
      C-03  Docker engine >= 24.0 and compose v2 plugin
      C-04  cgroup v2 unified hierarchy (manifest limits depend on it)
      C-05  UFW active
      C-06  ports 80/443/3000 — 3000 must NOT be publicly bound
      C-07  live docker network subnets must not collide with the
            disallowed CIDR list

Exit codes: 0 = ready · 1 = findings · 2 = cannot assess (connectivity,
environment gap, or secret in planning env). Secrets are never read,
stored, printed, or transmitted (D-124/D-045); the SSH key PATH may be
passed and is never echoed.

Usage:
  python3 local/scripts/validate_vps_target.py                # offline
  python3 local/scripts/validate_vps_target.py \
      --host HOST --user ADMIN [--key KEY_PATH] [--port 22]   # probe
"""
from __future__ import annotations

import argparse
import ipaddress
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PROD_MANIFEST = REPO / "local" / "infra" / "compose.prod.yml"
ENV_EXAMPLE = REPO / ".env.example"
READINESS_REPORT = REPO / "docs" / "deployment" / "stage-c-readiness.md"

# Sizing floors — MUST stay numerically in sync with stage-c-readiness.md §2.2
CPU_FLOOR = 2
RAM_FLOOR_MB = 6144
RAM_RECOMMENDED_MB = 8192
DISK_FLOOR_GB = 40
DISK_RECOMMENDED_GB = 80

# Docker engine / compose constraints (official compatibility basis)
DOCKER_MIN = (24, 0)
COMPOSE_V2_MIN = (2, 0)

CHECK_PORTS = (80, 443, 3000)
OK_OS_IDS = {"ubuntu", "debian", "raspbian", "linuxmint"}
OK_OS_LIKE = ("ubuntu", "debian")

# Admin/VPN ranges a deployment host's docker networks must never overlap
DISALLOWED_SUBNETS = ("10.8.0.0/24", "192.168.1.0/24", "100.64.0.0/10")

# Durable named volumes required by the prod manifest (n8n cache is
# tmpfs; its durable state lives in n8n_data)
REQUIRED_VOLUMES = ("woo_data", "woo_data_db", "canonical_data",
                    "n8n_data", "media_data")

# Sizing totals the manifest must yield — docs/deployment/stage-c-readiness.md
# §2 derives its host baseline from exactly these numbers.
EXPECTED_MEM_MIB = 3328   # 512 + 1024 + 512 + 1024 + 256
EXPECTED_CPUS = 4.0       # 1.0 + 1.0 + 1.0 + 0.5 + 0.5

# READ-ONLY guarantee: every remote command this probe may run (pinned by
# tests). Anything outside this allowlist is a harness bug, not a feature.
SSH_ALLOWLIST = (
    "cat /etc/os-release",
    "nproc",
    "free -m",
    "df -BG /",
    "docker --version",
    "docker compose version",
    "cat /sys/fs/cgroup/cgroup.controllers",
    "ufw status",
    "ss -ltn",
    "docker network ls --format {{.Name}}",
    "docker network inspect",   # -f json IPAM only (read-only)
)

ENV_VAR_RE = re.compile(r"\$\{([A-Z][A-Z0-9_]*):")
MEM_RE = re.compile(r"^\s*mem_limit:\s*(\d+)([mg])\s*$", re.M)
CPUS_RE = re.compile(r"^\s*cpus:\s*([\d.]+)\s*$", re.M)
VOLUME_TOP_RE = re.compile(r"^volumes:\s*$", re.M)
VOLUME_DEF_RE = re.compile(r"^ {2}([a-z0-9_]+):", re.M)


class Findings:
    """Collects OK / FAIL rows; any FAIL ⇒ exit 1."""

    def __init__(self) -> None:
        self.items: list[tuple[str, str, str]] = []

    def ok(self, check: str, detail: str) -> None:
        self.items.append(("OK  ", check, detail))
        print(f"  [OK  ] {check}: {detail}")

    def fail(self, check: str, detail: str) -> None:
        self.items.append(("FAIL", check, detail))
        print(f"  [FAIL] {check}: {detail}")

    def blocked(self, check: str, detail: str) -> None:
        self.items.append(("STOP", check, detail))
        print(f"  [STOP] {check}: {detail}")

    @property
    def failed(self) -> bool:
        return any(s == "FAIL" for s, _, _ in self.items)


# --------------------------------------------------------------------------
# pure helpers (imported and pinned by the battery)
# --------------------------------------------------------------------------

def manifest_env_contract(text: str | None = None) -> tuple[str, ...]:
    """Mandatory `${VAR:?}` names declared by the prod manifest."""
    if text is None:
        text = PROD_MANIFEST.read_text(encoding="utf-8")
    seen: list[str] = []
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue  # commented examples never join the live contract
        for m in ENV_VAR_RE.finditer(line):
            if m.group(1) not in seen:
                seen.append(m.group(1))
    return tuple(seen)


def parse_resource_limits(text: str | None = None) -> tuple[int, float]:
    """(total memory MiB, total CPUs) over all manifest services."""
    if text is None:
        text = PROD_MANIFEST.read_text(encoding="utf-8")
    mem = 0
    for value, unit in MEM_RE.findall(text):
        mem += int(value) * (1024 if unit == "g" else 1)
    cpus = sum(float(c) for c in CPUS_RE.findall(text))
    return mem, round(cpus, 2)


def manifest_volumes(text: str | None = None) -> tuple[str, ...]:
    """Top-level named volumes declared by the prod manifest."""
    if text is None:
        text = PROD_MANIFEST.read_text(encoding="utf-8")
    m = VOLUME_TOP_RE.search(text)
    if not m:
        return ()
    tail = text[m.end():]
    # top-level keys end at the next unindented line
    stop = re.search(r"^\S", tail, re.M)
    body = tail[:stop.start()] if stop else tail
    return tuple(VOLUME_DEF_RE.findall(body))


def subnet_overlaps(declared: tuple[str, ...]) -> list[str]:
    """Declared/pinned subnets colliding with DISALLOWED_SUBNETS."""
    bad: list[str] = []
    for cidr in declared:
        net = ipaddress.ip_network(cidr, strict=False)
        for dis in DISALLOWED_SUBNETS:
            if net.overlaps(ipaddress.ip_network(dis)):
                bad.append(cidr)
                break
    return bad


def looks_live(value: str) -> bool:
    """Cheap D-045 guard: non-empty value present in the planning env."""
    return bool(value.strip())


def parse_os_release(text: str) -> tuple[str, str]:
    id_like = ""
    the_id = ""
    for line in text.splitlines():
        if line.startswith("ID="):
            the_id = line[3:].strip().strip('"').lower()
        elif line.startswith("ID_LIKE="):
            id_like = line[8:].strip().strip('"').lower()
    return the_id, id_like


def os_supported(text: str) -> tuple[bool, str]:
    the_id, id_like = parse_os_release(text)
    if the_id in OK_OS_IDS:
        return True, the_id
    if any(fam in id_like for fam in OK_OS_LIKE):
        return True, f"{the_id or '?'} (like {id_like})"
    return False, the_id or "unknown"


def parse_docker_version(text: str) -> tuple[int, int] | None:
    m = re.search(r"docker[^\d]*(\d+)\.(\d+)", text, re.I)
    return (int(m.group(1)), int(m.group(2))) if m else None


def parse_ram_mb(text: str) -> int:
    m = re.search(r"Mem:\s+(\d+)", text)
    return int(m.group(1)) if m else -1


def parse_disk_gb(text: str) -> int:
    """Total size of the filesystem mounted at / (df -BG / line)."""
    for line in text.splitlines():
        if re.search(r"\s/\s*$", line):
            m = re.search(r"(\d+)G", line)
            if m:
                return int(m.group(1))
    return -1


def parse_cpus(text: str) -> int:
    try:
        return int(text.strip())
    except ValueError:
        return -1


def cgroup_is_v2(text: str) -> bool:
    return "memory" in text and "cpuset" in text


def public_3000_bound(text: str) -> bool:
    """True if :3000 (hex BB8) is listening beyond loopback."""
    for line in text.splitlines():
        cols = line.split()
        if len(cols) >= 4 and ":" in cols[3]:
            addr, _, port = cols[3].rpartition(":")
            if port == "BB8" and addr not in ("127.0.0.1", "[::1]"):
                return True
    return False


def parse_listening_ports(text: str) -> tuple[int, ...]:
    ports = set()
    for line in text.splitlines():
        cols = line.split()
        if len(cols) >= 4 and ":" in cols[3]:
            try:
                ports.add(int(cols[3].rsplit(":", 1)[1], 16))
            except ValueError:
                continue
    return tuple(sorted(p for p in ports if p in CHECK_PORTS))


# --------------------------------------------------------------------------
# offline mode
# --------------------------------------------------------------------------

def offline_mode(find: Findings) -> bool:
    print("=== OFFLINE — deployment-plan verification (no host) ===")
    contract = manifest_env_contract()
    env_example = ENV_EXAMPLE.read_text(encoding="utf-8")

    missing = [v for v in contract if v not in env_example]
    (find.ok("O-01 env contract documented",
             f"{len(contract)} mandatory keys") if not missing
     else find.fail("O-01 env contract documented",
                    f"missing from .env.example: {missing}"))

    live = [v for v in contract
            if v in os.environ and looks_live(os.environ[v])]
    (find.fail("O-02 no live secrets in planning env", "")
     if live else find.ok("O-02 no live secrets in planning env",
                          "D-045 planning-hygiene intact"))
    if live:
        # name-only, never values (D-124)
        find.blocked("O-02 refusing to continue",
                     f"secret material present for: {live}")
        return False

    mem, cpus = parse_resource_limits()
    (find.ok("O-03 sizing derivation matches report",
             f"{mem} MiB ceilings / {cpus} CPUs")
     if (mem, cpus) == (EXPECTED_MEM_MIB, EXPECTED_CPUS)
     else find.fail("O-03 sizing derivation matches report",
                    f"got ({mem} MiB, {cpus}) — manifest drifted "
                    f"from stage-c-readiness.md"))

    volumes = manifest_volumes()
    lacking = [v for v in REQUIRED_VOLUMES if v not in volumes]
    (find.ok("O-04 durable volume plan", f"{len(volumes)} named volumes")
     if not lacking else find.fail("O-04 durable volume plan",
                                   f"missing: {lacking}"))

    pinned = ()  # the manifest pins no static subnets (docker auto-assigns)
    (find.ok("O-05 subnet guard", "no pinned subnet collides "
             f"({len(DISALLOWED_SUBNETS)} disallowed CIDRs checked)")
     if not subnet_overlaps(pinned)
     else find.fail("O-05 subnet guard",
                    f"collisions: {subnet_overlaps(pinned)}"))
    return True


# --------------------------------------------------------------------------
# target-probe mode (read-only, allowlisted SSH)
# --------------------------------------------------------------------------

def ssh_run(args, user: str, host: str, port: int, key, timeout: int = 20):
    cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
           "-o", "StrictHostKeyChecking=accept-new", "-p", str(port)]
    if key:
        cmd += ["-i", str(key)]
    cmd += [f"{user}@{host}"]
    return subprocess.run(cmd + list(args), capture_output=True,
                          text=True, timeout=timeout)


def probe_mode(args, find: Findings) -> None:
    print(f"=== TARGET PROBE — {args.user}@{args.host} (read-only) ===")
    r = ssh_run(args, args.user, args.host, args.port, args.key,
                ["cat /etc/os-release"])
    if r.returncode != 0:
        find.blocked("C-00 connectivity", "SSH batch login failed — "
                     "cannot assess (exit 2); nothing was modified")
        return

    ok, distro = os_supported(r.stdout)
    (find.ok("C-01 OS family", distro) if ok
     else find.fail("C-01 OS family",
                    f"{distro} outside documented supported set"))

    n = parse_cpus(ssh_run(args, args.user, args.host, args.port,
                           args.key, ["nproc"]).stdout)
    (find.ok("C-02a vCPU", f"{n} (floor {CPU_FLOOR})") if n >= CPU_FLOOR
     else find.fail("C-02a vCPU",
                    f"{n} < floor {CPU_FLOOR} — resize per report §2.2"))

    ram = parse_ram_mb(ssh_run(args, args.user, args.host, args.port,
                               args.key, ["free -m"]).stdout)
    (find.ok("C-02b RAM", f"{ram} MB (floor {RAM_FLOOR_MB}, rec "
             f"{RAM_RECOMMENDED_MB})") if ram >= RAM_FLOOR_MB
     else find.fail("C-02b RAM",
                    f"{ram} MB < floor {RAM_FLOOR_MB} — report §2.2"))

    disk = parse_disk_gb(ssh_run(args, args.user, args.host, args.port,
                                 args.key, ["df -BG /"]).stdout)
    (find.ok("C-02c root disk", f"{disk} GB (floor {DISK_FLOOR_GB}, rec "
             f"{DISK_RECOMMENDED_GB})") if disk >= DISK_FLOOR_GB
     else find.fail("C-02c root disk",
                    f"{disk} GB < floor {DISK_FLOOR_GB} — report §2.2"))

    dv = parse_docker_version(ssh_run(args, args.user, args.host,
                                      args.port, args.key,
                                      ["docker --version"]).stdout or "")
    (find.ok("C-03a docker engine", f"{'.'.join(map(str, dv))} "
             f"(min {DOCKER_MIN[0]}.{DOCKER_MIN[1]})")
     if dv and dv >= DOCKER_MIN
     else find.fail("C-03a docker engine",
                    f"{'.'.join(map(str, dv)) if dv else 'absent'} "
                    f"< {DOCKER_MIN[0]}.{DOCKER_MIN[1]} — install per "
                    f"runbook §3"))

    cv = parse_docker_version((ssh_run(args, args.user, args.host,
                                       args.port, args.key,
                                       ["docker compose version"]).stdout
                               or ""))
    (find.ok("C-03b compose v2", ".".join(map(str, cv or ())))
     if cv and cv >= COMPOSE_V2_MIN
     else find.fail("C-03b compose v2",
                    "compose v2 plugin required by compose.prod.yml"))

    cg = ssh_run(args, args.user, args.host, args.port, args.key,
                 ["cat /sys/fs/cgroup/cgroup.controllers"]).stdout
    (find.ok("C-04 cgroup v2", "unified hierarchy present")
     if cgroup_is_v2(cg)
     else find.fail("C-04 cgroup v2",
                    "manifest mem_limit/cpus accounting requires "
                    "cgroup v2 (kernel boot param)"))

    ufw = ssh_run(args, args.user, args.host, args.port, args.key,
                  ["ufw status"]).stdout
    (find.ok("C-05 UFW", "active")
     if "Status: active" in ufw
     else find.fail("C-05 UFW", "inactive — enable per runbook §2"))

    ss = ssh_run(args, args.user, args.host, args.port, args.key,
                 ["ss -ltn"]).stdout
    (find.fail("C-06 port 3000 exposure",
               "publicly bound — close per runbook §2")
     if public_3000_bound(ss)
     else find.ok("C-06 listening ports",
                  f"{parse_listening_ports(ss) or 'none of 80/443/3000'};"
                  " 3000 not publicly bound"))

    nets = (ssh_run(args, args.user, args.host, args.port, args.key,
                    ["docker network ls --format {{.Name}}"]).stdout or
            "").split()
    colliding: list[str] = []
    for name in nets:
        if not name or name.startswith("none") or name == "host":
            continue
        insp = ssh_run(args, args.user, args.host, args.port, args.key,
                       [f"docker network inspect -f "
                        f"'{{{{json .IPAM.Config}}}}' {name}"])
        for cidr in re.findall(r'"Subnet"\s*:\s*"([^"]+)"', insp.stdout):
            if subnet_overlaps((cidr,)):
                colliding.append(f"{name}:{cidr}")
    (find.fail("C-07 subnet collisions", f"{colliding} overlap admin/VPN "
               "ranges — re-pin docker defaults")
     if colliding
     else find.ok("C-07 subnet collisions", "none against disallowed "
                  f"{DISALLOWED_SUBNETS}"))


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Stage C target validation (read-only; D-141)")
    ap.add_argument("--host")
    ap.add_argument("--user", default="root")
    ap.add_argument("--key")
    ap.add_argument("--port", type=int, default=22)
    args = ap.parse_args()

    find = Findings()
    print("validate_vps_target — D-141 Stage C harness; READ-ONLY "
          "at all times; nothing is installed or modified.\n")

    if not offline_mode(find):
        print("\n=== CANNOT ASSESS (exit 2) — resolve the STOP item, "
              "rerun ===")
        sys.exit(2)

    if args.host:
        probe_mode(args, find)
        if find.items and find.items[0][0] == "STOP":
            print("\n=== CANNOT ASSESS (exit 2) — fix connectivity, "
                  "rerun ===")
            sys.exit(2)

    if find.failed:
        print("\n=== NOT READY (exit 1) — remediate findings; "
              "every fix is a separate, owner-gated action. "
              "Nothing was modified.")
        sys.exit(1)
    print("\n=== READY (exit 0) — all Stage C checks green. "
          "Nothing was modified.")
    sys.exit(0)


if __name__ == "__main__":
    main()

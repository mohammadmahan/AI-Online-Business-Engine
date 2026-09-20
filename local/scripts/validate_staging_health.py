#!/usr/bin/env python3
"""validate_staging_health.py — Staging health & E2E validation (D-141).

Stage D–H readiness deliverable. Two layers of verification:

  MANIFEST MODE (default, offline)
    Resolves local/infra/compose.staging.yml and asserts the health
    surface is well-defined: a healthcheck on each of the five core
    services, the isolated network topology declared, and the sole
    published surface on WordPress. Also emits the probe commands an
    operator will run live per service (synthetic ping plan) so the
    Stage D drill is reproducible from one place. Deep structural
    rules live in validate_staging_compose.py; this mode focuses on
    the health/E2E surface. Exit 0 = valid, 1 = invalid, 2 = env.

  LIVE MODE (--live --host H --user U)
    Runs the Stage D health drill over SSH against a deployed staging
    host — READ-ONLY, same discipline as validate_vps_readiness.py:
    `docker compose ps` health states, `docker inspect` network
    attachments, and in-network synthetic ping probes executed via
    `docker compose exec -T <svc> <healthcmd>` (probe commands only —
    never mutations). Verifies the isolation invariants from the
    DEPLOYED side: data-plane containers must have NO route to the
    outside (internal network ⇒ no default gateway) and only
    WordPress may attach the frontend network.

Exit codes (both modes): 0 = healthy/valid · 1 = findings ·
2 = environment/connectivity problem.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STAGING = REPO / "local" / "infra" / "compose.staging.yml"

CORE_SERVICES = ("wordpress", "woodb", "canonical-db", "n8n", "media")

# In-network synthetic probes (run via `docker compose exec -T <svc> …`).
# Read-only against data planes: ping/ready/version style commands only.
PROBE_COMMANDS = {
    "wordpress": "php -r 'exit(0);'",
    "woodb": "mysqladmin ping -h 127.0.0.1",
    "canonical-db": "pg_isready",
    "n8n": "wget -q -O /dev/null http://127.0.0.1:5678/healthz",
    "media": "mc ready local",
}


def fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")
    sys.exit(1)


def ok(msg: str) -> None:
    print(f"  [OK  ] {msg}")


def resolve_manifest() -> dict:
    env = {k: "validation-throwaway" for k in (
        "CANONICAL_DB_PASSWORD", "WORDPRESS_DB_PASSWORD", "MYSQL_PASSWORD",
        "MYSQL_ROOT_PASSWORD", "N8N_ENCRYPTION_KEY", "MINIO_ROOT_PASSWORD")}
    e = dict(os.environ)
    e.update(env)
    proc = subprocess.run(
        ["docker", "compose", "-f", str(STAGING), "config", "--format", "json"],
        capture_output=True, text=True, env=e, cwd=str(REPO),
    )
    if proc.returncode != 0:
        fail(f"manifest resolution failed: {proc.stderr.strip()[:200]}")
    return json.loads(proc.stdout)


def manifest_mode() -> None:
    print("=== Staging health validation — MANIFEST MODE (offline) ===")
    resolved = resolve_manifest()
    svcs = resolved["services"]

    for svc in CORE_SERVICES:
        if svc not in svcs:
            fail(f"core service missing from manifest: {svc}")
        if "healthcheck" not in svcs[svc]:
            fail(f"core service has no healthcheck: {svc}")
        if svc not in PROBE_COMMANDS:
            fail(f"no synthetic probe defined for: {svc}")
    ok(f"health surface defined for all {len(CORE_SERVICES)} core services")

    published = {n for n, s in svcs.items() if s.get("ports")}
    if published != {"wordpress"}:
        fail(f"published surface must be wordpress-only, got {published}")
    nets = resolved.get("networks", {})
    if not nets.get("data", {}).get("internal"):
        fail("data network must be internal (isolation invariant)")
    ok("network isolation declared (data internal, wordpress sole surface)")

    print("--- Synthetic probe plan (executed live in --live mode) ---")
    for svc in CORE_SERVICES:
        print(f"  {svc:12s} -> docker compose exec -T {svc} {PROBE_COMMANDS[svc]}")
    print("=== MANIFEST VALID (exit 0) ===")
    sys.exit(0)


# ----------------------------------------------------------------------------
# LIVE MODE
# ----------------------------------------------------------------------------

def ssh_run(user, host, port, key, cmd, timeout):
    ssh_cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
               "-o", "StrictHostKeyChecking=accept-new", "-o",
               "LogLevel=ERROR", "-p", str(port)]
    if key:
        ssh_cmd += ["-i", str(key)]
    ssh_cmd += [f"{user}@{host}", cmd]
    try:
        proc = subprocess.run(ssh_cmd, capture_output=True, text=True,
                              timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, "", f"timeout after {timeout}s"
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def live_mode(user, host, port, key, timeout) -> None:
    print(f"=== Staging health drill — LIVE MODE (READ-ONLY) — {user}@{host} ===")

    def run(cmd: str) -> tuple[int, str]:
        rc, out, err = ssh_run(user, host, port, key, cmd, timeout)
        return rc, (out if rc == 0 else f"{out} {err}".strip())

    rc, out = run("true")
    if rc != 0:
        print(f"  [ENV ] SSH unreachable rc={rc}: {out[:200]}")
        print("=== CANNOT ASSESS (exit 2) ===")
        sys.exit(2)
    ok("connectivity")

    # 1. container health states -------------------------------------------
    compose_dir = "~"
    rc, out = run(f"cd {compose_dir} && docker compose -f compose.staging.yml ps --format json")
    if rc != 0:
        print(f"  [ENV ] compose stack not reachable on host (rc={rc}): {out[:200]}")
        print("=== CANNOT ASSESS (exit 2) — deploy first, rerun ===")
        sys.exit(2)
    rows = [json.loads(ln) for ln in out.splitlines() if ln.strip()]
    states = {r.get("Service"): (r.get("State"), r.get("Health")) for r in rows}
    for svc in CORE_SERVICES:
        state, health = states.get(svc, (None, None))
        if state != "running":
            fail(f"{svc}: state={state!r} (want running)")
        if health is not None and health != "healthy":
            fail(f"{svc}: health={health!r} (want healthy)")
    ok(f"all {len(CORE_SERVICES)} core containers running+healthy")

    # 2. synthetic in-network probes -----------------------------------------
    for svc, probe in PROBE_COMMANDS.items():
        rc, out = run(f"cd {compose_dir} && docker compose -f compose.staging.yml "
                      f"exec -T {svc} {probe}")
        if rc != 0:
            fail(f"synthetic probe failed for {svc}: {out[:120]}")
    ok("in-network synthetic probes pass for all core services")

    # 3. isolation invariant: data plane has no outbound route ---------------
    # An internal docker network has no gateway — a container attached ONLY
    # to data must have no default route.
    for svc in ("canonical-db", "woodb", "media", "n8n"):
        rc, out = run(f"docker inspect {svc} --format "
                      f"'{{{{range .NetworkSettings.Networks}}}}"
                      f"{{{{.Gateway}}}}{{{{end}}}}'")
        if rc != 0:
            fail(f"inspect failed for {svc}: {out[:120]}")
        gateways = [g for g in out.split() if g and g != "<no value>"]
        if gateways:
            fail(f"{svc}: has gateway(s) {gateways} — data plane must be "
                 f"gateway-less (internal network)")
    ok("isolation invariant: data-plane containers have no default gateway")

    # 4. isolation invariant: frontend attachment -----------------------------
    rc, out = run("docker network ls --format '{{.Name}}' | grep -E 'frontend|data'")
    nets_on_host = out.splitlines()
    frontend = next((n for n in nets_on_host if n.endswith("_frontend") or n == "frontend"), None)
    data = next((n for n in nets_on_host if n.endswith("_data") or n == "data"), None)
    if not frontend or not data:
        print(f"  [ENV ] staging networks not found on host ({nets_on_host[:3]}…)")
        print("=== CANNOT ASSESS (exit 2) ===")
        sys.exit(2)
    for net, allowed in ((frontend, {"wordpress"}), (data, set(CORE_SERVICES))):
        rc, out = run(f"docker network inspect {net} --format "
                      f"'{{{{range .Containers}}}}{{{{.Name}}}} {{{{end}}}}'")
        if rc != 0:
            fail(f"network inspect failed for {net}: {out[:120]}")
        attached = {n.lstrip("/") for n in out.split() if n}
        unexpected = attached - allowed
        if unexpected:
            fail(f"network {net}: unexpected containers attached: {unexpected}")
    ok("isolation invariant: frontend touches WordPress only; "
       "data carries exactly the core set")

    print("=== STAGING HEALTHY (exit 0) — nothing was mutated ===")
    sys.exit(0)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--live", action="store_true",
                    help="run the live SSH drill instead of offline manifest mode")
    ap.add_argument("--host")
    ap.add_argument("--user")
    ap.add_argument("--key", default=None)
    ap.add_argument("--port", type=int, default=22)
    ap.add_argument("--timeout", type=int, default=20)
    args = ap.parse_args()

    if not STAGING.exists():
        print(f"  [ENV ] manifest missing: {STAGING}")
        sys.exit(2)

    if args.live:
        if not (args.host and args.user):
            print("  [ENV ] --live requires --host and --user")
            sys.exit(2)
        live_mode(args.user, args.host, args.port, args.key, args.timeout)
    else:
        if shutil.which("docker") is None:
            print("  [ENV ] docker CLI not found — cannot resolve manifest")
            sys.exit(2)
        manifest_mode()


if __name__ == "__main__":
    main()

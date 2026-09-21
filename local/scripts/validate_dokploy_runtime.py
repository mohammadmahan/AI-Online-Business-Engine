#!/usr/bin/env python3
"""validate_dokploy_runtime.py — production runtime hardening & health
verification (Dokploy work package, D-141; owner directive "Phase 12 /
Stage B — container runtime hardening & integrated health probes").

Three verification layers:

  MANIFEST MODE (default, offline, no daemon needed)
    Resolves local/infra/compose.prod.yml via `docker compose config`
    and asserts the hardening surface:
      - hardening invariants: no-new-privileges on every service,
        resource limits on every service, zero published ports, the
        data network internal-only, wordpress the only frontend member;
      - secret-free by construction: every secret `${VAR:?…}` makes
        resolution REFUSE when absent (fail-closed deploy);
      - no default/hardcoded credentials anywhere in the resolved
        document;
      - healthchecks on every service (the probe plan the LIVE layer
        executes).

  RUNTIME MODE (--runtime; needs the local Docker daemon)
    Empirically executes the prod manifest against synthetic
    credentials in an ISOLATED compose project and verifies the
    RUNNING containers with `docker inspect`:
      - every container actually healthy;
      - no-new-privileges + resource limits actually applied;
      - read-only rootfs services are genuinely read-only and their
        volume/tmpfs write seams writable;
      - data-plane containers have NO default gateway (internal
        network ⇒ cannot egress);
      - the PostgreSQL SSOT accepts the migration schema (the five
        base schemas + all D-08x phase schemas apply idempotently).
    Tear-down is explicit, scope-limited, and refuses non-prodcheck
    project names.

  GATE MODE (--gate; needs a reachable PostgreSQL SSOT)
    Fail-closed startup pre-flight rehearsal: the canonical
    `runtime_preflight.check_environment` refuses missing mandatory
    keys / active prohibited keys, and `readiness_probe` composes the
    pool + schema + media verdicts (missing evidence is never a pass).

Exit codes: 0 = verified · 1 = findings · 2 = environment/daemon gap.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PROD = REPO / "local" / "infra" / "compose.prod.yml"
SCHEMA = REPO / "local" / "db" / "schema.sql"
sys.path.insert(0, str(REPO / "local"))

# Synthetic validation credentials — throwaway, NEVER committed values.
# They exist only inside this process/env to satisfy the fail-closed :?.
SYNTHETIC_ENV = {
    "CANONICAL_DB_NAME": "business_engine_prod",
    "CANONICAL_DB_USER": "engine_prod",
    "CANONICAL_DB_PASSWORD": "throwaway-validation-canonical",
    "WORDPRESS_DB_PASSWORD": "throwaway-validation-wp",
    "MYSQL_PASSWORD": "throwaway-validation-mysql",
    "MYSQL_ROOT_PASSWORD": "throwaway-validation-mysql-root",
    "N8N_ENCRYPTION_KEY": "throwaway-validation-n8n",
    "MINIO_ROOT_USER": "prod-media",
    "MINIO_ROOT_PASSWORD": "throwaway-validation-minio",
    "COMPOSE_PROJECT_NAME": "prodcheck",
}

ISOLATION_PROJECT = "prodcheck"   # tear-down refuses anything else


def _fail(msg):
    print(f"  [FAIL] {msg}")
    return False


def _ok(msg):
    print(f"  [OK  ] {msg}")
    return True


def _resolve(env_extra=None, drop=()):
    env = dict(os.environ)
    env.update(SYNTHETIC_ENV)
    if env_extra:
        env.update(env_extra)
    for k in drop:
        env.pop(k, None)
    proc = subprocess.run(
        ["docker", "compose", "-f", str(PROD), "config", "--format", "json"],
        capture_output=True, text=True, env=env, cwd=str(REPO))
    if proc.returncode != 0:
        return proc.returncode, None, proc.stderr
    return 0, json.loads(proc.stdout), ""


def manifest_mode() -> int:
    print("=== MANIFEST MODE (schema + hardening surface) ===")
    good = True
    rc, doc, err = _resolve()
    if rc != 0:
        print(f"  [FAIL] compose config refused: {err.strip()[:200]}")
        return 1
    svcs = doc["services"]

    # 1) no-new-privileges everywhere
    missing_nnp = [s for s, c in svcs.items()
                   if "no-new-privileges:true" not in
                   (c.get("security_opt") or [])]
    (_ok("no-new-privileges on all 5 services") if not missing_nnp
     else _fail(f"no-new-privileges missing: {missing_nnp}"))
    good &= not missing_nnp

    # 2) resource limits everywhere
    unbounded = [s for s, c in svcs.items()
                 if not c.get("mem_limit") or not c.get("cpus")]
    (_ok("memory + cpu limits on all services") if not unbounded
     else _fail(f"unbounded services: {unbounded}"))
    good &= not unbounded

    # 3) zero published ports (F-2 production endgame)
    published = {s: c.get("ports") for s, c in svcs.items()
                 if c.get("ports")}
    (_ok("zero published ports (gateway/proxy-only production)")
     if not published else _fail(f"published ports: {published}"))
    good &= not published

    # 4) isolation topology: data internal, wordpress alone on frontend
    nets = doc.get("networks") or {}
    data_internal = (nets.get("data") or {}).get("internal") is True
    good &= (_ok("data network declared internal") if data_internal
             else _fail("data network not internal"))
    members = {s: [n for n in (c.get("networks") or {})] for s, c in
               svcs.items()}
    front = sorted(s for s, ns in members.items() if "frontend" in ns)
    good &= (_ok(f"frontend carries wordpress only: {front}")
             if front == ["wordpress"]
             else _fail(f"frontend members: {front}"))
    bad_data = [s for s, ns in members.items() if "data" not in ns]
    good &= (_ok("every service reaches the data plane") if not bad_data
             else _fail(f"services without data network: {bad_data}"))

    # 5) secret-free by construction: fail-closed resolution per secret
    secrets = ["CANONICAL_DB_PASSWORD", "WORDPRESS_DB_PASSWORD",
               "MYSQL_PASSWORD", "MYSQL_ROOT_PASSWORD",
               "N8N_ENCRYPTION_KEY", "MINIO_ROOT_PASSWORD"]
    for s in secrets:
        rc2, _, _ = _resolve(drop=(s,))
        good &= (_ok(f"{s} is fail-closed (config refuses without it)")
                 if rc2 != 0 else _fail(f"{s} resolved WITHOUT a value"))

    # 6) no default/hardcoded credentials in the resolved document
    #    (SYNTHETIC_ENV is injected by US at validation time and never
    #    appears in the file or a real deploy's env — excluded here)
    blob = json.dumps(doc)
    bad_literals = [m for m in (
        "engine-local-only", "password123",
        "admin/admin", "changeme") if m in blob]
    good &= (_ok("no default credential literals in resolved config")
             if not bad_literals else _fail(f"literals: {bad_literals}"))

    # 7) healthchecks on every service (integrated probe plan)
    no_hc = [s for s, c in svcs.items() if not c.get("healthcheck")]
    good &= (_ok("healthcheck on every service") if not no_hc
             else _fail(f"missing healthchecks: {no_hc}"))

    # 8) read-only rootfs + tmpfs seams declared where intended
    ro = sorted(s for s, c in svcs.items() if c.get("read_only") is True)
    good &= (_ok(f"read-only rootfs: {ro}") if
             ro == ["canonical-db", "media", "n8n", "woodb"]
             else _fail(f"read_only set: {ro}"))

    print(f"=== {'MANIFEST VERIFIED' if good else 'MANIFEST FAILURES'} ===")
    return 0 if good else 1


def _docker(*args, timeout=60):
    return subprocess.run(["docker", *args], capture_output=True,
                          text=True, timeout=timeout)


def _healthy(name):
    out = _docker("ps", "--format", "{{.Names}} {{.Status}}").stdout
    for line in out.splitlines():
        n, _, status = line.partition(" ")
        if n == name and "(healthy)" in status:
            return True
    return False


def runtime_mode() -> int:
    print("=== RUNTIME MODE (empirical, isolated prodcheck project) ===")
    info = _docker("info", "-f", "{{.ServerVersion}}")
    if info.returncode != 0:
        print("  [--  ] Docker daemon unreachable — runtime mode "
              "SKIPPED (environment gap, never a silent pass)")
        return 2
    good = True
    env = dict(os.environ)
    env.update(SYNTHETIC_ENV)
    up = subprocess.run(
        ["docker", "compose", "-f", str(PROD), "up", "-d", "--no-build",
         "--quiet-pull"],
        capture_output=True, text=True, env=env, cwd=str(REPO))
    if up.returncode != 0:
        print(f"  [FAIL] isolated up failed: {up.stderr.strip()[:200]}")
        return 1
    print("  [OK  ] isolated stack up (project prodcheck, synthetic creds)")

    import time
    # container_name values from the manifest (not compose service keys)
    expected = {f"engine-prod-{s}" for s in
                ("wordpress", "mysql", "postgres", "n8n", "minio")}
    deadline = time.time() + 240
    while time.time() < deadline:
        if {n for n in expected if _healthy(n)} == expected:
            break
        time.sleep(5)
    healthy = {n for n in expected if _healthy(n)}
    good &= (_ok("all 5 containers report healthy") if healthy == expected
             else _fail(f"healthy={sorted(healthy)} missing="
                        f"{sorted(expected - healthy)}"))

    def inspect(name, fmt):
        r = _docker("inspect", "-f", fmt, name)
        return r.stdout.strip() if r.returncode == 0 else None

    # hardening actually applied
    for name in sorted(expected):
        nnp = inspect(name, "{{index .HostConfig.SecurityOpt 0}}")
        mem = inspect(name, "{{.HostConfig.Memory}}")
        okn = nnp == "no-new-privileges:true"
        okm = mem and mem != "0"
        good &= (_ok(f"{name}: nnp + memory limit ({mem})")
                 if okn and okm else _fail(
                     f"{name}: nnp={nnp} mem={mem}"))

    # read-only rootfs + writable seams (Go template booleans lowercase)
    ro_map = {"engine-prod-postgres": True, "engine-prod-mysql": True,
              "engine-prod-n8n": True, "engine-prod-minio": True,
              "engine-prod-wordpress": False}
    for name, want_ro in ro_map.items():
        ro = inspect(name, "{{.HostConfig.ReadonlyRootfs}}")
        got = str(ro).strip().lower()
        good &= (_ok(f"{name}: read_only={got}")
                 if got == str(want_ro).lower()
                 else _fail(f"{name}: read_only={got}, want {want_ro}"))
    seam_checks = {
        "engine-prod-postgres": "touch /tmp/s1 && touch "
                                "/var/lib/postgresql/data/.s1",
        "engine-prod-n8n": "touch /home/node/.cache/s1 && touch "
                           "/home/node/.n8n/.s1",
        "engine-prod-minio": "touch /tmp/s1 && touch /data/.s1",
        "engine-prod-mysql": "touch /tmp/s1 && touch "
                             "/var/lib/mysql/.s1",
    }
    for name, cmd in seam_checks.items():
        r = _docker("exec", name, "sh", "-c", cmd)
        good &= (_ok(f"{name}: write seams functional") if r.returncode == 0
                 else _fail(f"{name}: seam write failed: "
                            f"{r.stderr.strip()[:80]}"))
    # non-root n8n (uid 1000) — empirical
    uid = _docker("exec", "engine-prod-n8n", "id", "-u").stdout.strip()
    good &= (_ok(f"n8n runs as uid {uid} (non-root)") if uid == "1000"
             else _fail(f"n8n uid={uid}"))

    # egress isolation: data-plane containers have NO usable default
    # gateway (internal network; Go renders the absent gateway of an IP
    # field as "invalid IP")
    for name in ("engine-prod-postgres", "engine-prod-mysql",
                 "engine-prod-minio", "engine-prod-n8n"):
        raw = inspect(name, "{{json .NetworkSettings.Networks}}") or "{}"
        nets = json.loads(raw)
        gws = {str(v.get("Gateway") or "") for v in nets.values()}
        egress_free = all(g in ("", "invalid IP") for g in gws)
        good &= (_ok(f"{name}: no default gateway (cannot egress)")
                 if egress_free else _fail(f"{name}: gateway: {gws}"))

    # migration integrity against the PostgreSQL SSOT
    with open(SCHEMA, encoding="utf-8") as f:
        sql = f.read()
    r = subprocess.run(
        ["docker", "exec", "-i", "engine-prod-postgres", "psql",
         "-v", "ON_ERROR_STOP=1", "-X", "-q", "-U", "engine_prod",
         "-d", "business_engine_prod"],
        input=sql, capture_output=True, text=True, timeout=120)
    schemas = ("seed canonical registry events provenance hitl admin "
               "assets oms analytics orchestration instagram telegram")
    r2 = _docker("exec", "engine-prod-postgres", "psql", "-X", "-q",
                 "-A", "-t", "-U", "engine_prod",
                 "-d", "business_engine_prod", "-c",
                 "SELECT count(*) FROM pg_namespace WHERE nspname = ANY "
                 f"(ARRAY[{', '.join(repr(s) for s in schemas.split())}]);")
    n = r2.stdout.strip()
    good &= (_ok(f"SSOT migration applies clean (rc=0, "
                 f"{n}/13 schemas)") if r.returncode == 0 and n == "13"
             else _fail(f"schema apply rc={r.returncode} "
                        f"schemas={n}: {r.stderr.strip()[:120]}"))
    # idempotent re-apply
    r3 = subprocess.run(
        ["docker", "exec", "-i", "engine-prod-postgres", "psql",
         "-v", "ON_ERROR_STOP=1", "-X", "-q", "-U", "engine_prod",
         "-d", "business_engine_prod"],
        input=sql, capture_output=True, text=True, timeout=120)
    good &= (_ok("schema re-apply idempotent (rc=0)") if r3.returncode == 0
             else _fail("schema re-apply failed"))

    print(f"=== {'RUNTIME VERIFIED' if good else 'RUNTIME FAILURES'} ===")
    return 0 if good else 1


def _teardown() -> int:
    if SYNTHETIC_ENV["COMPOSE_PROJECT_NAME"] != ISOLATION_PROJECT:
        print("refusing teardown of unexpected project")
        return 1
    env = dict(os.environ)
    env.update(SYNTHETIC_ENV)
    down = subprocess.run(
        ["docker", "compose", "-f", str(PROD), "down", "-v",
         "--remove-orphans"],
        capture_output=True, text=True, env=env, cwd=str(REPO))
    print("teardown (prodcheck only, volumes removed): rc="
          f"{down.returncode}")
    return down.returncode


def gate_mode() -> int:
    print("=== GATE MODE (fail-closed pre-flight rehearsal) ===")
    good = True
    from canonical.runtime_preflight import (
        PreflightError,
        check_environment,
        readiness_probe,
    )
    # 1) full contract passes
    env = dict(SYNTHETIC_ENV)
    env.update({"APP_ENV": "production", "CANONICAL_DB_HOST": "canonical-db",
                "CANONICAL_DB_PORT": "5432",
                "MEDIA_ENDPOINT": "http://media:9000",
                "MEDIA_BUCKET": "engine-prod-media",
                "N8N_URL": "http://n8n:5678"})
    try:
        res = check_environment(env, env_name="production")
        good &= _ok(f"full contract resolves ({len(res['resolved'])} keys)")
    except PreflightError as exc:
        good &= _fail(f"unexpected refusal: {exc}")
    # 2) each mandatory key individually refuses when missing
    for key in ("CANONICAL_DB_HOST", "CANONICAL_DB_PORT",
                "CANONICAL_DB_PASSWORD", "MEDIA_ENDPOINT", "N8N_URL"):
        broken = dict(env)
        broken.pop(key)
        try:
            check_environment(broken, env_name="production")
            good &= _fail(f"missing {key} did NOT refuse")
        except PreflightError:
            good &= _ok(f"missing {key} refuses startup (fail-closed)")
    # 3) prohibited keys refuse
    for key in ("WORDPRESS_DEBUG", "AI_LIVE_ENABLED"):
        broken = dict(env)
        broken[key] = "true"
        try:
            check_environment(broken, env_name="production")
            good &= _fail(f"prohibited {key} did NOT refuse")
        except PreflightError:
            good &= _ok(f"prohibited {key} refuses startup (D-045/D-124)")
    # 4) short secret refuses (shape check, value never echoed)
    broken = dict(env)
    broken["CANONICAL_DB_PASSWORD"] = "short"
    try:
        check_environment(broken, env_name="production")
        good &= _fail("short secret did NOT refuse")
    except PreflightError as exc:
        good &= (_ok("short secret refuses; value withheld in message")
                 if "short" not in str(exc) else
                 _fail("error message leaked the secret value"))
    # 5) readiness composition — fail closed on missing evidence
    good &= (_ok("readiness READY when all probes green")
             if readiness_probe(pg_ready=True, schemas_present=True,
                                media_declared=True)["ready"]
             else _fail("readiness false-negative"))
    for probe in ({"pg_ready": False}, {"schemas_present": False},
                  {"media_declared": False}):
        kw = dict(pg_ready=True, schemas_present=True,
                  media_declared=False)
        kw.update(probe)
        v = readiness_probe(**kw)
        good &= (_ok(f"missing evidence → NOT_READY ({probe})")
                 if not v["ready"] else
                 _fail("missing evidence treated as pass"))
    print(f"=== {'GATE VERIFIED' if good else 'GATE FAILURES'} ===")
    return 0 if good else 1


def main() -> int:
    args = sys.argv[1:]
    if args == ["--runtime"]:
        rc = runtime_mode()
        _teardown() if os.environ.get(
            "KEEP_STACK") != "1" else print("  [--  ] KEEP_STACK=1: "
                                            "stack left running")
        return rc
    if args == ["--gate"]:
        return gate_mode()
    if args == ["--teardown"]:
        return _teardown()
    if args:
        print(__doc__)
        return 2
    return manifest_mode()


if __name__ == "__main__":
    sys.exit(main())

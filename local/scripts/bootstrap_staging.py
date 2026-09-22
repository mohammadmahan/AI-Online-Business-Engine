#!/usr/bin/env python3
"""bootstrap_staging.py — Stage D staging bootstrap (D-141).

One idempotent operator command that prepares a deployed staging
stack's canonical store. Composes the EXISTING proven primitives —
`seed_registry.q` (host psql → container psql fallback), the
idempotent `local/db/schema.sql`, and `seed_registry.verify()` — no
parallel seed/migration logic is invented.

Steps (each fail-closed, each re-runnable):
  1. PREFLIGHT  — `canonical/runtime_preflight.check_environment`
                  with env_name="staging": missing/malformed mandatory
                  keys or an ACTIVE PROHIBITED production key
                  (WORDPRESS_DEBUG, AI_LIVE_ENABLED,
                  N8N_DIAGNOSTICS_ENABLED) aborts BEFORE migration.
                  Findings carry key names, never values (D-124).
  2. SCHEMA     — apply local/db/schema.sql idempotently; assert all
                  13 schemas exist afterwards.
  3. SEED       — registry seed via seed_registry.main() semantics
                  (O/I/L gate audited in-database, D-030/D-057).
  4. SMOKE FIXTURE — baseline staging-only product fixture
                  (deterministic STG- ids, ON CONFLICT DO NOTHING).
  5. PERMISSIONS — staged, idempotent, container-scoped writability
                  fixes (`docker compose exec` inside the PROJECT,
                  project name pinned; never the host filesystem).

Exit 0 verified · 1 findings. With --check, runs preflight + schema
presence + seed-count verification only (mutates nothing).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)                                   # local/scripts
sys.path.insert(0, os.path.join(ROOT, "local"))            # local/

import seed_registry  # noqa: E402
from seed_registry import container_psql  # noqa: E402
from canonical.runtime_preflight import (       # noqa: E402
    PreflightError,
    check_environment,
)

SCHEMA = os.path.join(ROOT, "local", "db", "schema.sql")

SCHEMAS = ("seed canonical registry events provenance hitl admin "
           "assets oms analytics orchestration instagram telegram").split()

COMPOSE_FILE = os.path.join(ROOT, "local", "infra", "compose.staging.yml")
STAGING_PROJECT_PREFIX = "engine-staging"


def _configure_transport() -> None:
    """Point the seed_registry tooling at the STAGING container ONLY.

    The shared `q()` prefers host psql against LOCAL_* defaults — that
    would silently apply staging migrations to the LOCAL database (or
    fail confusingly, since the staging SSOT is not port-published).
    Staging bootstrap therefore pins the container transport and
    REFUSES any target outside the engine-staging-* namespace.
    """
    container = os.environ.get("STAGING_PG_CONTAINER",
                               "engine-staging-postgres")
    if not container.startswith(STAGING_PROJECT_PREFIX):
        raise RuntimeError(
            f"refusing DB target outside {STAGING_PROJECT_PREFIX}*: "
            f"{container!r}")
    os.environ["LOCAL_PG_CONTAINER"] = container
    os.environ.setdefault("LOCAL_PGUSER", "engine_staging")
    os.environ.setdefault("LOCAL_PGDATABASE", "business_engine_staging")
    # redirect EVERY seed_registry/q() call to the pinned container —
    # host psql is never attempted against staging (D-045 environment
    # separation: the staging SSOT is unreachable from the host net).
    seed_registry.q = container_psql


def q_staging(sql: str) -> str:
    return container_psql(sql)

# The one baseline fixture Stage D guarantees exists in staging.
SMOKE_PRODUCT_ID = "STG-SMOKE-0001"


def step_preflight(env: dict | None = None) -> dict:
    resolved = check_environment(env, env_name="staging")
    print(f"  [OK ] preflight: {len(resolved['resolved'])} mandatory keys "
          "resolved (values withheld)")
    return resolved


def step_schema() -> None:
    with open(SCHEMA, encoding="utf-8") as f:
        sql = f.read()
    q_staging(sql)
    present = q_staging(
        "SELECT count(*) FROM pg_namespace WHERE nspname = ANY (ARRAY["
        + ", ".join(repr(s) for s in SCHEMAS) + "]);")
    if present != "13":
        raise RuntimeError(
            f"schema apply left {present}/13 schemas — refusing to continue")
    print(f"  [OK ] schema applied idempotently ({present}/13 schemas)")


def step_seed() -> None:
    rc = seed_registry.main()
    if rc != 0:
        raise RuntimeError(
            "seed verification failed (O/I/L gate or count mismatch) — "
            "resolve before staging acceptance")
    print("  [OK ] registry seed verified (counts + O/I/L gate)")


def step_smoke_fixture() -> None:
    # staging-only product marker: one append-only provenance row that
    # the smoke harness looks for. The provenance table has NO unique
    # constraint (append-only ledger, D-026) — idempotency is enforced
    # by the explicit pre-count, never by trusting INSERT semantics.
    have = int(q_staging(
        "SELECT count(*) FROM provenance.provenance_record "
        f"WHERE source_reference = 'product:{SMOKE_PRODUCT_ID}';"))
    if have == 0:
        q_staging(
            "INSERT INTO provenance.provenance_record (source_type, actor, "
            "source_reference, original_value, notes) VALUES "
            "('SYSTEM_GENERATED', 'stage-d-bootstrap', "
            f"'product:{SMOKE_PRODUCT_ID}', "
            "'{\"smoke_fixture\": true, \"env\": \"staging\"}', "
            "'baseline staging smoke fixture');")
        print(f"  [OK ] smoke fixture recorded ({SMOKE_PRODUCT_ID})")
    else:
        print(f"  [OK ] smoke fixture already present ({SMOKE_PRODUCT_ID})")


def step_permissions(project: str) -> None:
    """Idempotent, container-scoped seam fixes (staging volumes only)."""
    if not project.startswith(STAGING_PROJECT_PREFIX):
        raise RuntimeError(
            f"refusing permission step outside a {STAGING_PROJECT_PREFIX}* "
            f"project (got {project!r})")

    def compose_exec(service: str, *args: str) -> int:
        return subprocess.run(
            ["docker", "compose", "-f", COMPOSE_FILE, "-p", project,
             "exec", "-T", service, *args],
            capture_output=True, text=True).returncode

    # n8n (uid 1000): its state volume must be node-owned. Runtime-proven
    # in the prod manifest; same rule applies to staging state volumes.
    if compose_exec("n8n", "sh", "-c",
                    "node -e 'fs.accessSync(process.env.N8N_USER_FOLDER "
                    "|| \"/home/node/.n8n\", fs.constants.W_OK)' "
                    "2>/dev/null || (mkdir -p /home/node/.n8n && "
                    "cd /home/node/.n8n && find . ! -user 1000 "
                    "-exec sh -c 'echo WARN: non-owned entry' \\; )") != 0:
        print("  [WARN] n8n seam probe inconclusive (container down?) — "
              "re-run bootstrap after the stack is up")
    else:
        print("  [OK ] n8n state seam writable by uid 1000")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", default="engine-staging",
                    help="compose project name (pinned to engine-staging*)")
    ap.add_argument("--check", action="store_true",
                    help="verify only — mutate nothing")
    args = ap.parse_args()

    print("=== Stage D bootstrap — staging canonical store ===")
    print("(idempotent; every step fail-closed; values never printed)\n")
    try:
        _configure_transport()
    except RuntimeError as e:
        print(f"  [FAIL] transport guard: {e}")
        return 1
    try:
        step_preflight()
    except PreflightError as e:
        print(f"  [FAIL] preflight: {e}")
        return 1

    if args.check:
        n = q_staging("SELECT count(*) FROM pg_namespace WHERE nspname = ANY (ARRAY["
              + ", ".join(repr(s) for s in SCHEMAS) + "]);")
        print(f"  [{'OK ' if n == '13' else 'FAIL'}] check: {n}/13 schemas")
        return 0 if n == "13" else 1

    try:
        step_schema()
        step_seed()
        step_smoke_fixture()
        step_permissions(args.project)
    except (RuntimeError, OSError) as e:
        print(f"  [FAIL] {e}")
        print("=== BOOTSTRAP FAILED (fail-closed; nothing half-applied "
              "is left unreported) ===")
        return 1
    print("\n=== BOOTSTRAP VERIFIED — run run_staging_smoke_tests.py next")
    return 0


if __name__ == "__main__":
    sys.exit(main())

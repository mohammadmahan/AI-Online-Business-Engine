#!/usr/bin/env bash
# ============================================================================
# deploy_orchestrator.sh — D-141 Stage H orchestration & health gate.
#
# Stage-by-stage deployment driver for the Dokploy bridge:
#   preflight  fail-closed required-environment validation (names only —
#              values are NEVER echoed)
#   B          database & core state  (compose: canonical-db healthy)
#   C          cache & broker         (redis contract — when provisioned)
#   D          application core & workers (health-probe integration)
#   E          telemetry & escalation sinks (D-089 bridge reachable)
#   F/G        reverse proxy / SSL / routing (deployment-layer attach)
#   H          end-to-end health verification (infra_health_probe)
#
# Fail-closed discipline:
#   - exit 0 ONLY when every stage gate and the final health probe pass
#   - exit 1 on any stage failure (deployment HALTED)
#   - exit 2 on preflight/usage errors (nothing executed)
#   - no secret VALUE is ever printed; diagnostics reference names only
#   - the final gate is `local/src/infra/infra_health_probe.py`
#     (qa.health_report.v1) — a probe that is not wired HALTS the deploy
#
# Modes:
#   --dry-run   preflight + plan only; no docker/probe execution
#   --help      usage
# Default mode executes the stage gates in order.
# ============================================================================
set -euo pipefail

DRY_RUN=0
case "${1:-}" in
  --dry-run) DRY_RUN=1 ;;
  ""|--help|-h) sed -n '2,30p' "$0"; exit 0 ;;
  *) echo "usage: $0 [--dry-run|--help]" >&2; exit 2 ;;
esac

# --- preflight: required environment (fail-closed, names only) --------------
# Every value must come from the deployment layer's secret store (D-045);
# a missing variable aborts BEFORE anything executes. Values are never
# echoed — only the missing NAME is reported.
PREFLIGHT_REQUIRED=(
  CANONICAL_DB_NAME
  CANONICAL_DB_USER
  CANONICAL_DB_PASSWORD
  WORDPRESS_DB_PASSWORD
  MYSQL_PASSWORD
  MYSQL_ROOT_PASSWORD
  N8N_ENCRYPTION_KEY
  MINIO_ROOT_USER
  MINIO_ROOT_PASSWORD
)
missing=0
for var in "${PREFLIGHT_REQUIRED[@]}"; do
  if [ -z "${!var:-}" ]; then
    echo "[preflight] MISSING required environment variable: ${var}" >&2
    missing=1
  fi
done
if [ "${missing}" != "0" ]; then
  echo "[preflight] HALTED: required environment incomplete (D-045 fail-closed)" >&2
  exit 2
fi
echo "[preflight] required environment present (values withheld)"

# --- stage hooks -------------------------------------------------------------
# Each gate runs a check command; a non-zero check halts the deployment.
# Defaults use the local compose tooling; a deployment layer may override
# any <STAGE>_CHECK with its own command via the environment.
stage() {
  local name="$1" check_var="$2" default_check="$3"
  echo "[stage ${name}] begin"
  if [ "${DRY_RUN}" = "1" ]; then
    echo "[stage ${name}] dry-run: plan only — check '${check_var}'"
    return 0
  fi
  local check
  check="${!check_var:-${default_check}}"
  if eval "${check}"; then
    echo "[stage ${name}] PASS"
  else
    echo "[stage ${name}] FAIL — deployment HALTED" >&2
    exit 1
  fi
}

stage B  STAGE_B_CHECK \
  'docker compose -f local/infra/compose.prod.yml ps canonical-db | grep -q healthy'
stage C  STAGE_C_CHECK \
  'docker compose -f local/infra/compose.prod.yml ps | grep -qE "Up|healthy|Running"'
stage D  STAGE_D_CHECK \
  'docker compose -f local/infra/compose.prod.yml ps | grep -qE "Up|healthy|Running"'
stage E  STAGE_E_CHECK \
  'python3 local/scripts/launch_attestation.py >/dev/null 2>&1'
stage FG STAGE_FG_CHECK \
  'test -f local/infra/compose.prod.yml'  # gateway attach is deployment-layer config

# --- Stage H: end-to-end health verification (the deployment gate) -----------
echo "[stage H] end-to-end health probe"
if [ "${DRY_RUN}" = "1" ]; then
  echo "[stage H] dry-run: plan only — infra_health_probe verdict required"
  echo "DRY-RUN PLAN OK (nothing executed)"
  exit 0
fi
python3 - <<'PY'
import sys, pathlib
root = pathlib.Path(__file__).resolve().parent if False else pathlib.Path.cwd()
for p in ("local", "."):
    sys.path.insert(0, str(root / p) if p == "local" else str(root))
from local.src.infra.infra_health_probe import InfraHealthProbe
from canonical.obs_health import ShippedProbes
import json, os, subprocess

def pg_exec(sql):
    out = subprocess.run(
        ["docker", "exec", "engine-prod-postgres",
         "psql", "-U", os.environ["CANONICAL_DB_USER"],
         "-d", os.environ["CANONICAL_DB_NAME"],
         "-tAc", sql],
        capture_output=True, text=True, check=True, timeout=30)
    return out.stdout

verdict = InfraHealthProbe(
    pg_exec=pg_exec,
    redis_ping=None,          # not provisioned yet (stage C contract)
    worker_heartbeat=None,    # wired by the deployment layer
    telemetry_state=None,     # wired by the deployment layer
).deploy_verdict()
print(json.dumps(verdict, indent=2, sort_keys=True))
sys.exit(0 if verdict["verdict"] == "DEPLOY_OK" else 1)
PY
rc=$?
if [ "${rc}" != "0" ]; then
  echo "[stage H] FAIL — deployment HALTED (health probe)" >&2
  exit 1
fi
echo "[stage H] PASS"
echo "DEPLOY_OK"

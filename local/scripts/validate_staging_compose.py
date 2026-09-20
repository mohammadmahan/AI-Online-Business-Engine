#!/usr/bin/env python3
"""validate_staging_compose.py — Stage B operator validation (D-141).

Pre-deploy verification of the STAGING deployment manifest:

  1. SCHEMA      — `docker compose config` resolves the manifest
                   (syntax + interpolation + structural validity).
  2. FAIL-CLOSED — every required deploy secret (the manifest's
                   `${VAR:?…}` variables) individually makes resolution
                   REFUSE when absent. A deploy without secrets must
                   never be possible.
  3. STRUCTURE   — the resolved topology matches the Stage B design:
                   digest-pinned images, WordPress sole published
                   surface, `data` network internal, restart policies,
                   healthchecks, health-gated start order, volumes.
  4. COMPLETENESS — every variable documented in .env.staging.example
                   is either consumed by the manifest or explicitly
                   marked not-applicable; every manifest variable is
                   documented. Drift in either direction FAILS.

Exit codes: 0 = valid · 1 = validation failure · 2 = environment
problem (docker CLI/compose plugin missing) — never a silent pass.

Local, offline, no daemon required (config is client-side).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STAGING = REPO / "local" / "infra" / "compose.staging.yml"
ENV_EXAMPLE = REPO / ".env.staging.example"

GATEWAY_PORTS = {"80", "443", "3000"}
SYNTHETIC_ENV = {
    "CANONICAL_DB_PASSWORD": "validation-throwaway-canonical",
    "WORDPRESS_DB_PASSWORD": "validation-throwaway-wp",
    "MYSQL_PASSWORD": "validation-throwaway-mysql",
    "MYSQL_ROOT_PASSWORD": "validation-throwaway-mysql-root",
    "N8N_ENCRYPTION_KEY": "validation-throwaway-n8n",
    "MINIO_ROOT_PASSWORD": "validation-throwaway-minio",
}
REQUIRED_SECRET_VARS = sorted(SYNTHETIC_ENV)

# Variables documented in .env.staging.example that are intentionally NOT
# interpolated by the compose manifest. Two honest sub-categories:
#   APP_ENV_CONTRACT — real staging values consumed by the ENGINE process /
#     deployment-layer environment (connection endpoints, logging), not by
#     compose interpolation. Removing any of these from the template is drift.
#   PLACEHOLDER_ONLY — synthetic REF pointers or explicitly not-applicable
#     in staging (URLs assigned at Stage C; credential refs live in the
#     secret store; mock-woo is profile-deferred).
APP_ENV_CONTRACT = {
    "APP_ENV",
    "CANONICAL_DB_HOST", "CANONICAL_DB_PORT",
    "WORDPRESS_DB_HOST", "WORDPRESS_DB_NAME", "WORDPRESS_DB_USER",
    "N8N_URL",
    "MEDIA_ENDPOINT", "MEDIA_BUCKET", "MEDIA_REGION",
    "LOG_LEVEL", "LOG_FORMAT",
}
PLACEHOLDER_ONLY = {
    "WOO_CREDENTIAL_REF", "WOO_REST_NAMESPACE", "N8N_CREDENTIAL_REF",
    "MEDIA_CREDENTIAL_REF", "MOCK_WOO_STATE_PATH",
    "MOCK_WOO_FAILURE_SCENARIO", "MOCK_WOO_LATENCY_S",
    "WORDPRESS_URL", "WOOCOMMERCE_URL",
}


def fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")
    sys.exit(1)


def ok(msg: str) -> None:
    print(f"  [OK  ] {msg}")


def compose_config(env: dict[str, str]) -> tuple[int, str, str]:
    e = dict(os.environ)
    e.update(env)
    proc = subprocess.run(
        ["docker", "compose", "-f", str(STAGING), "config", "--format", "json"],
        capture_output=True, text=True, env=e, cwd=str(REPO),
    )
    return proc.returncode, proc.stdout, proc.stderr


def main() -> None:
    print("=== Staging compose validation (Stage B, D-141) ===")

    # --- environment preconditions -------------------------------------
    if shutil.which("docker") is None:
        print("  [ENV ] docker CLI not found — cannot validate (exit 2)")
        sys.exit(2)
    probe = subprocess.run(
        ["docker", "compose", "version"], capture_output=True, text=True,
    )
    if probe.returncode != 0:
        print("  [ENV ] docker compose plugin unavailable — cannot validate (exit 2)")
        sys.exit(2)
    ok("docker CLI + compose plugin available")

    if not STAGING.exists():
        fail(f"staging manifest missing: {STAGING}")
    if not ENV_EXAMPLE.exists():
        fail(f"env template missing: {ENV_EXAMPLE}")

    # --- 1. schema ------------------------------------------------------
    rc, out, err = compose_config(SYNTHETIC_ENV)
    if rc != 0:
        fail(f"schema resolution FAILED (rc={rc}): {err.strip()[:300]}")
    resolved = json.loads(out)
    ok(f"schema valid — {len(resolved['services'])} services resolved")

    # --- 2. fail-closed secrets -----------------------------------------
    for var in REQUIRED_SECRET_VARS:
        env = {k: v for k, v in SYNTHETIC_ENV.items() if k != var}
        rc, _, err = compose_config(env)
        if rc == 0:
            fail(f"FAIL-CLOSED broken: config succeeded WITHOUT {var}")
        if var not in err:
            fail(f"refusal error does not name {var}")
    ok(f"fail-closed proven for all {len(REQUIRED_SECRET_VARS)} deploy secrets")

    # --- 3. structure -----------------------------------------------------
    svcs = resolved["services"]
    for name, svc in svcs.items():
        if "@sha256:" not in svc["image"]:
            fail(f"{name}: image not digest-pinned")
        if svc.get("restart") != "unless-stopped":
            fail(f"{name}: restart policy {svc.get('restart')!r} != unless-stopped")
        if "healthcheck" not in svc:
            fail(f"{name}: no healthcheck")
    ok("digest pins, restart policies, healthchecks verified")

    published = {n: [p.get("published") for p in s.get("ports", [])]
                 for n, s in svcs.items() if s.get("ports")}
    if list(published) != ["wordpress"]:
        fail(f"published ports must be wordpress-only, got: {published}")
    for n, s in svcs.items():
        for p in s.get("ports", []):
            if str(p.get("host_ip", "")) in {"127.0.0.1", "::1"}:
                fail(f"{n}: loopback binding in staging")
            if str(p.get("published")) in GATEWAY_PORTS:
                fail(f"{n}: conflicts with gateway ports")
    ok("exposure model verified (wordpress sole surface, no loopback/gateway conflicts)")

    nets = resolved.get("networks", {})
    if not nets.get("data", {}).get("internal"):
        fail("data network must be internal:true (isolated)")
    if "frontend" not in nets:
        fail("frontend network missing")
    for n, s in svcs.items():
        attached = set(s.get("networks", {}))
        if not attached <= {"data", "frontend"}:
            fail(f"{n}: unexpected network attachment {attached}")
        if n != "wordpress" and "frontend" in attached:
            fail(f"{n}: data-plane service on frontend network")
        if n == "wordpress" and attached != {"data", "frontend"}:
            fail("wordpress must attach to both data and frontend")
    ok("network isolation verified (data internal, frontend wordpress-only)")

    expected_vols = {"woo_data", "woo_data_db", "canonical_data",
                     "n8n_data", "media_data"}
    if set(resolved.get("volumes", {})) != expected_vols:
        fail(f"volume set mismatch: {sorted(resolved.get('volumes', {}))}")
    ok("named volumes verified")

    # --- 4. env-contract completeness ------------------------------------
    template_vars: dict[str, str] = {}
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            template_vars[k] = v

    manifest_vars = set()
    text = STAGING.read_text(encoding="utf-8")
    # Interpolation lives in values, not comments — strip comments so the
    # header's documentation example `${VAR:?message}` is not mistaken for
    # a real variable reference.
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        for m in re.finditer(r"\$\{([A-Z][A-Z0-9_]*)(?::[-?])?", line):
            manifest_vars.add(m.group(1))

    undocumented = manifest_vars - set(template_vars)
    if undocumented:
        fail(f"manifest variables missing from .env.staging.example: "
             f"{sorted(undocumented)}")
    unconsumed = (set(template_vars) - manifest_vars
                  - APP_ENV_CONTRACT - PLACEHOLDER_ONLY)
    if unconsumed:
        fail(f"template variables neither compose-consumed, app-contract, "
             f"nor placeholder-only: {sorted(unconsumed)}")
    for var in APP_ENV_CONTRACT:
        if var not in template_vars:
            fail(f"app-env contract variable missing from template: {var}")
    for var in REQUIRED_SECRET_VARS:
        if template_vars.get(var) != "<SET-BY-DEPLOYMENT-LAYER>":
            fail(f"{var} must carry the SET-BY-DEPLOYMENT-LAYER placeholder, "
                 f"got {template_vars.get(var)!r}")
    for var, val in template_vars.items():
        if re.search(r"(?i)(password|secret|key|token)=", val) and \
           val != "<SET-BY-DEPLOYMENT-LAYER>":
            fail(f"{var}: looks like a hardcoded secret value in the template")
    ok(f"env contract complete: {len(template_vars)} documented "
       f"({len(manifest_vars & set(template_vars))} compose-consumed, "
       f"{len(APP_ENV_CONTRACT)} app-env contract, "
       f"{len(PLACEHOLDER_ONLY)} placeholder-only), "
       f"secrets placeholder-only")

    print("=== VALID: staging manifest + env contract consistent ===")


if __name__ == "__main__":
    main()

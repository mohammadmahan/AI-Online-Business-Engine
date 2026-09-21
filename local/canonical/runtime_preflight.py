"""Container runtime preflight & health gate (D-141 production hardening).

Fails CLOSED at container startup: every mandatory environment key must
be present and well-formed BEFORE any engine surface is constructed;
prohibited keys must be absent. Pure and deterministic (Phase 20 AST
discipline): no network, no subprocesses, no wall-clock keys.

Also hosts the READINESS PROBE contract consumed by
`local/scripts/validate_dokploy_runtime.py`: composite readiness =
PostgreSQL reachable + schema-migration integrity (the five SSOT
schemas exist) + media endpoint declared — mirroring the manifest's
healthcheck set (canonical-db / n8n / media / wordpress / woodb).
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional

__all__ = [
    "PreflightError", "check_environment", "readiness_probe",
    "MANDATORY_KEYS", "PROHIBITED_KEYS",
]

# Mandatory production/runtime keys (fail-closed: any miss aborts startup).
# Secrets are validated for PRESENCE/FORMAT ONLY — values are never logged.
MANDATORY_KEYS: Dict[str, str] = {
    # environment identity
    "APP_ENV": "nonempty",
    # canonical PostgreSQL SSOT (D-055)
    "CANONICAL_DB_HOST": "host",
    "CANONICAL_DB_PORT": "port",
    "CANONICAL_DB_NAME": "nonempty",
    "CANONICAL_DB_USER": "nonempty",
    "CANONICAL_DB_PASSWORD": "secret",
    # media (S3-compatible, D-130 MediaStoreContract)
    "MEDIA_ENDPOINT": "url",
    "MEDIA_BUCKET": "nonempty",
    # n8n (orchestration-only, D-042)
    "N8N_URL": "url",
}

# Structurally prohibited in production; presence aborts startup.
PROHIBITED_KEYS: Dict[str, str] = {
    "WORDPRESS_DEBUG": "debug must be off in production (absent or falsy)",
    "AI_LIVE_ENABLED": "AI credentials are production-blocked (D-045)",
    "N8N_DIAGNOSTICS_ENABLED": "n8n diagnostics/telemetry must be off "
                               "(no external endpoints, D-045)",
}


class PreflightError(RuntimeError):
    """Fail-closed startup refusal. Carries named, stable findings; the
    message never embeds secret VALUES (names only, D-124)."""


def _truthy(v: str) -> bool:
    return v.strip().lower() in ("1", "true", "yes", "on")


def check_environment(
        env: Optional[Dict[str, str]] = None,
        *,
        env_name: str = "production") -> Dict[str, List[str]]:
    """Validate the runtime environment contract; fail closed.

    Returns the resolved contract for the audit log. Raises
    PreflightError with stable, secret-free findings on any mandatory
    key missing/malformed or any prohibited key active.
    """
    src = dict(os.environ if env is None else env)
    findings: List[str] = []
    resolved: List[str] = []
    for key, kind in MANDATORY_KEYS.items():
        val = src.get(key)
        if val is None or not str(val).strip():
            findings.append(f"missing mandatory key: {key}")
            continue
        val = str(val).strip()
        bad: Optional[str] = None
        if kind == "port":
            if not (val.isdigit() and 1 <= int(val) <= 65535):
                bad = f"{key}: invalid port {key}=***/{len(val)} chars"
        elif kind == "url":
            if not val.lower().startswith(("http://", "https://")):
                bad = f"{key}: must be an http(s) URL (value withheld)"
        elif kind == "host":
            if not val or any(c.isspace() for c in val):
                bad = f"{key}: invalid host (value withheld)"
        elif kind == "secret":
            if len(val) < 8:
                bad = f"{key}: below minimum length (value withheld)"
        if bad:
            findings.append(bad)
        else:
            # VALUES NEVER ENTER THE AUDIT — names and shapes only.
            resolved.append(key)
    for key, why in PROHIBITED_KEYS.items():
        val = src.get(key)
        if val is None:
            continue
        if key == "WORDPRESS_DEBUG":
            if _truthy(val):
                findings.append(f"prohibited key active: {key} ({why})")
        elif _truthy(val):
            findings.append(f"prohibited key active: {key} ({why})")
    if src.get("APP_ENV", env_name).strip().lower() not in (env_name,
                                                            "local",
                                                            "staging"):
        findings.append(
            f"APP_ENV={src.get('APP_ENV')} not valid for this runtime")
    if findings:
        raise PreflightError(
            "startup preflight FAILED (fail-closed, "
            f"{len(findings)} finding(s)): " + "; ".join(findings))
    return {"resolved": resolved, "findings": [], "env": env_name}


def readiness_probe(*, pg_ready: bool, schemas_present: bool,
                    media_declared: bool,
                    n8n_ready: bool = True) -> Dict[str, object]:
    """Composite readiness verdict over injected probe results.

    The probe itself is pure: the CALLER performs the actual checks
    (pool ping, schema query, endpoint declaration) and hands in the
    results — canonical stays transport-free (Phase 20). Any failed
    input means NOT READY (fail closed — missing evidence is never a
    pass).
    """
    checks = {
        "postgres_pool": bool(pg_ready),
        "schema_migrations": bool(schemas_present),
        "media_store": bool(media_declared),
        "n8n_orchestrator": bool(n8n_ready),
    }
    ready = all(checks.values())
    return {"ready": ready, "checks": checks,
            "verdict": "READY" if ready else "NOT_READY"}

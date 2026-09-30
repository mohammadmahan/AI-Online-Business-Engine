"""Stage D pre-flight verification (operator command) — preparation
phase (D-144 lineage; Dokploy plan §37/§55).

Verifies that a Stage D compose surface carries the D-144 contract
BEFORE any deployment-layer consumption. Two modes over ONE contract,
both parse-only and fail closed:

  --mode template  — the canonical template
                     (`local/infra/dokploy/dokploy_compose_template.yaml`)
                     carries: the four D-144 services (postgres-ssot,
                     redis, app-orchestrator, telemetry-circuit), the
                     `backend` internal + `edge` network pair, ZERO
                     published ports on the three data services, V-09
                     probe-parity healthchecks (every check maps onto
                     an `infra_health_probe.py` semantic), strict
                     `${VAR:?reason}` credential references (loose
                     $VAR / ${VAR} forms refused), and the named
                     volumes (canonical_data, redis_data)
  --mode manifest  — the SAME checks against any candidate manifest
                     (typically generator output); a rendered or
                     hand-altered manifest that loses ANY invariant
                     refuses with named findings — configuration
                     drift is caught before a deployment layer ever
                     sees it

Fail-closed contract (exit 0/1/2): 0 = contract HOLDS · 1 = contract
VIOLATIONS (named findings) · 2 = the surface is unreadable or
structurally unusable (cannot assess). The image-slot placeholders
(`{{POSTGRES_IMAGE}}` / digest placeholders) are a template-mode
given and are NOT manifest findings — image pinning is the
generator's own gate (F-series), verified there.

AST-pure parse: no subprocess, no network, no os.environ. Zero-leak
(D-124): findings carry service names and structural markers — never
values.

Usage:
  python3 local/scripts/stage_d_preflight.py [--mode {template,manifest}]
      [--manifest PATH] [--json]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

SCHEMA = "stage_d.verdict.v1"

TEMPLATE = (ROOT / "local" / "infra" / "dokploy"
            / "dokploy_compose_template.yaml")
DEFAULT_MANIFEST = (ROOT / "local" / "infra" / "dokploy"
                    / "docker-compose.dokploy.yaml")

# D-144 contract vocabulary
EXPECTED_SERVICES = ("postgres-ssot", "redis", "app-orchestrator",
                     "telemetry-circuit")
DATA_SERVICES = ("postgres-ssot", "redis", "telemetry-circuit")
EDGE_SERVICE = "app-orchestrator"
EXPECTED_NETWORKS = ("backend", "edge")
EXPECTED_VOLUMES = ("canonical_data", "redis_data")

# V-09 probe-parity vocabulary (verify_cutover_readiness.py lineage):
# every data service's healthcheck must map onto an
# infra_health_probe semantic via these command tokens.
PROBE_PARITY = {
    "postgres-ssot": "pg_isready",
    "redis": "redis-cli",
    "app-orchestrator": "/healthz/worker",
    "telemetry-circuit": "/-/healthy",
}

_STRICT_SUB_RE = re.compile(r"\$\{[A-Z_][A-Z0-9_]*:\?[^}]*\}")
_LOOSE_SUB_RE = re.compile(
    r"(?<!\$)\$\([A-Z_][A-Z0-9_]*\)"
    r"|(?<!\$)\$\{[A-Z_][A-Z0-9_]*\}"
    r"|(?<!\$)\$[A-Z_][A-Z0-9_]*")
# image-slot placeholders are template-mode givens, not contract
# findings (the generator owns pin enforcement)
_PLACEHOLDER_RE = re.compile(r"\{\{[A-Z_]+_IMAGE\}\}")


class StageDPreflightError(RuntimeError):
    """The surface is unreadable or structurally unusable (exit 2)."""


# --------------------------------------------------------------------------
# structural parse (house-style regex-structural, template vocabulary)
# --------------------------------------------------------------------------
def _parse_compose(text: str) -> Dict:
    """Structural parse of a Stage D compose surface: services (with
    ports/networks/healthcheck blocks), networks (with internal flag),
    declared volumes."""
    services: Dict[str, Dict] = {}
    networks: Dict[str, str] = {}
    volumes: List[str] = []
    section = None          # services | networks | volumes
    current = None
    in_healthcheck = False
    current_net = None
    env_items: List[str] = []

    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if re.match(r"^\S", line):          # top-level key
            key = stripped.split(":")[0].strip()
            section = key if key in ("services", "networks", "volumes") \
                else None
            current = None
            in_healthcheck = False
            current_net = None
            continue
        if section == "volumes":
            m = re.match(r"^  ([a-z0-9_]+):", line)
            if m:
                volumes.append(m.group(1))
            continue
        if section == "networks":
            m = re.match(r"^  ([a-z0-9_]+):", line)
            if m:
                current_net = m.group(1)
                networks[current_net] = ""
            elif current_net and stripped.startswith("internal:"):
                networks[current_net] = "internal"
            continue
        if section == "services":
            m = re.match(r"^  ([a-z0-9\-]+):\s*$", line)
            if m and not line.startswith("    "):
                current = m.group(1)
                services.setdefault(current, {
                    "ports": [], "networks": [], "healthcheck": "",
                    "env": []})
                in_healthcheck = False
                continue
            if current is None:
                continue
            if stripped == "healthcheck:":
                in_healthcheck = True
                continue
            if in_healthcheck:
                if re.match(r"^      test:", line) or \
                        re.match(r"^      - ", line):
                    services[current]["healthcheck"] += " " + stripped
                continue
            pm = re.match(r'^- "?(\d+(?:\.\d+)*:\d+)', stripped)
            if pm:
                services[current]["ports"].append(pm.group(1))
                continue
            nm = re.match(r"^-\s+([a-z0-9_]+)$", stripped)
            if nm and nm.group(1) in ("backend", "edge"):
                services[current]["networks"].append(nm.group(1))
                continue
            if stripped.startswith("- ") and ":" in stripped:
                env_items.append(stripped[2:])
                services[current]["env"].append(stripped[2:])
                continue
    return {"services": services, "networks": networks,
            "volumes": volumes, "env_items": env_items}


# --------------------------------------------------------------------------
# the contract checks
# --------------------------------------------------------------------------
def _check(checks: List[Dict], name: str, ok: bool, ok_detail: str,
           fail_detail: str) -> None:
    checks.append({"name": name, "verdict": "PASS" if ok else "FAIL",
                   "detail": ok_detail if ok else fail_detail,
                   "checked_at_logical": ""})


def check_contract(man: Dict, text: str, checks: List[Dict]) -> None:
    svc = man["services"]

    # D1 — service census
    missing = [s for s in EXPECTED_SERVICES if s not in svc]
    _check(checks, "D1_service_census", not missing,
           f"all {len(EXPECTED_SERVICES)} D-144 services present",
           f"services missing: {missing}")

    # D2 — backend internal
    _check(checks, "D2_backend_internal",
           man["networks"].get("backend") == "internal",
           "`backend` network is internal (no egress)",
           f"`backend` internal flag missing — networks declared: "
           f"{sorted(man['networks'])}")

    # D3 — data services publish nothing
    exposed = {s: svc[s]["ports"] for s in DATA_SERVICES
               if s in svc and svc[s]["ports"]}
    _check(checks, "D3_zero_published_ports", not exposed,
           "postgres-ssot / redis / telemetry-circuit publish ZERO ports",
           f"data services with published ports: {exposed}")

    # D4 — edge attachment exclusivity
    on_edge = sorted(s for s, d in svc.items() if "edge" in d["networks"])
    _check(checks, "D4_edge_exclusivity",
           on_edge == [EDGE_SERVICE]
           and EDGE_SERVICE in svc
           and "backend" in svc.get(EDGE_SERVICE, {}).get("networks", []),
           f"only {EDGE_SERVICE} attaches `edge` (backend + edge)",
           f"`edge` attach set {on_edge} — expected exactly "
           f"[{EDGE_SERVICE!r}] (backend + edge)")

    # D5 — V-09 probe parity
    no_parity = [s for s, token in PROBE_PARITY.items()
                 if s in svc and token not in svc[s]["healthcheck"]]
    _check(checks, "D5_probe_parity", not no_parity,
           "every service healthcheck maps onto an "
           "infra_health_probe semantic (V-09)",
           f"healthchecks without a probe-parity token: {no_parity}")

    # D6 — strict credential references
    strict = _STRICT_SUB_RE.findall(text)
    loose = [m for m in _LOOSE_SUB_RE.findall(text)]
    _check(checks, "D6_strict_credential_refs", not loose and strict,
           f"{len(strict)} strict ${{VAR:?}} credential references, "
           "zero loose $-forms",
           f"loose $-forms present ({len(loose)}): "
           f"{sorted(set(loose))[:6]} — credentials may only appear "
           f"as ${{VAR:?reason}} (D-045)"
           if loose else "no strict credential references found — the "
           "surface carries no D-045 secret contract")

    # D7 — named volumes
    declared = sorted(v for v in man["volumes"])
    _check(checks, "D7_named_volumes",
           declared == sorted(EXPECTED_VOLUMES),
           "named volumes match the D-144 contract "
           f"{sorted(EXPECTED_VOLUMES)}",
           f"volume declarations {declared} vs contract "
           f"{sorted(EXPECTED_VOLUMES)}")


def _surface_text(mode: str, manifest: Optional[Path]) -> str:
    path = TEMPLATE if mode == "template" else (manifest or
                                                DEFAULT_MANIFEST)
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as e:
        raise StageDPreflightError(f"{mode} surface unreadable: {e}")


def verify(mode: str, text: str) -> Dict:
    checks: List[Dict] = []
    man = _parse_compose(text)
    if not man["services"]:
        raise StageDPreflightError(
            "no services parsed — the surface is structurally unusable")
    check_contract(man, text, checks)
    bad = [c for c in checks if c["verdict"] != "PASS"]
    return {"schema_version": SCHEMA,
            "compatible_with": "qa.launch_attestation.v1",
            "ok": not bad,
            "verdict": "HOLDS" if not bad else "VIOLATIONS",
            "mode": mode,
            "checks": checks,
            "failing": [c["name"] for c in bad]}


def render(report: Dict) -> str:
    lines = [f"=== STAGE D PRE-FLIGHT ({report['mode']} mode) — "
             "D-144 contract ==="]
    for c in report["checks"]:
        mark = "ok  " if c["verdict"] == "PASS" else "FAIL"
        lines.append(f"  [{mark}] {c['name']:<26} {c['detail']}")
    lines.append(f"verdict {report['verdict']} — "
                 f"{len(report['checks']) - len(report['failing'])}/"
                 f"{len(report['checks'])} green")
    if report["ok"]:
        lines.append("D-144 contract HOLDS — the surface is ready for "
                     "the Stage D flow (deployment itself remains "
                     "owner-gated).")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Stage D pre-flight verification (fail closed, "
                    "parse-only).")
    ap.add_argument("--mode", choices=("template", "manifest"),
                    default="template")
    ap.add_argument("--manifest", default=str(DEFAULT_MANIFEST),
                    help="candidate manifest for --mode manifest")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    try:
        text = _surface_text(args.mode, Path(args.manifest))
        report = verify(args.mode, text)
    except StageDPreflightError as e:
        if args.json:
            print(json.dumps({"ok": False, "verdict": "UNREADABLE",
                              "error": str(e)}))
        else:
            print(f"[FAIL] {e}")
        return 2

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render(report))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

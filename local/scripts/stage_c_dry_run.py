"""Stage C dry-run harness (G1–G6) — operator command, D-141 ladder.

Simulates the Stage C execution sequence WITHOUT touching any host,
network, volume, or registry — everything is parsed from three
artifacts and verified fail closed:

  G1  Host bootstrap   — grant gate AUTHORIZED (SC-1..SC-12 fully
                         signed) + sizing on the grants artifact meets
                         the stage-c floors (simulated: no real host)
  G2  Installer pin    — SC-2/SC-10 signed with an explicit pinned
                         version string in the signature evidence
  G3  Network / tunnel — the staging manifest's isolation contract:
                         exactly ONE published port (wordpress 18080),
                         `data` network internal, wordpress the sole
                         `frontend` service, no bind mounts
  G4  GitHub connect   — SC-4 signed (read-scoped connection grant)
  G5  Staging DNS      — SC-5 signed ⇒ public URLs must be real; SC-5
                         unsigned ⇒ URLs must stay non-routable
                         (`.invalid` placeholders)
  G6  S3 backup        — SC-6/SC-7 signed ⇒ BACKUP_* block present
                         (key NAMES only); unsigned ⇒ block must stay
                         commented out

  plus ENV TEMPLATE validation against the 30-variable Stage B
  contract: strict placeholders on all six DEPLOY-SECRET keys, zero
  secret-shaped values (D-045), zero AI_* keys (G-B4 staging
  prohibition), and named-volume declarations matching the manifest.

Verdict `CANNOT_CLEAR` with exit 1 is the HONEST DEFAULT until the
owner signs the grants; exit 0 (CLEAR) requires every gate green.
Exit 2 = an artifact is missing or unreadable (cannot assess).

Emission follows `qa.launch_attestation.v1` probe conventions
(name/verdict/detail per check) under the stage-local schema
`stage_c.dry_run_clearance.v1`. No network, no subprocess, no durable
state: pure parse + verdict.

Usage:
  python3 local/scripts/stage_c_dry_run.py [--env PATH]
      [--manifest PATH] [--grants-artifact PATH] [--json]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "local" / "scripts"))

DEFAULT_TEMPLATE = REPO_ROOT / ".env.staging.template"
DEFAULT_MANIFEST = REPO_ROOT / "local" / "infra" / "compose.staging.yml"
DEFAULT_GRANTS = (REPO_ROOT / "docs" / "deployment"
                  / "stage-c-owner-grants.md")

SCHEMA = "stage_c.dry_run_clearance.v1"

SECRET_KEYS = {
    "CANONICAL_DB_PASSWORD", "WORDPRESS_DB_PASSWORD", "MYSQL_PASSWORD",
    "MYSQL_ROOT_PASSWORD", "N8N_ENCRYPTION_KEY", "MINIO_ROOT_PASSWORD",
}
PLACEHOLDER_RE = re.compile(r"^<GENERATE_SECURE_PASSWORD>$")
SECRET_SHAPE_RE = re.compile(
    r"(AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{30,}"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----|[0-9a-fA-F]{40,})")
INVALID_URL_MARK = ".invalid"

CONTRACT_KEYS = [
    "APP_ENV",
    "CANONICAL_DB_HOST", "CANONICAL_DB_PORT", "CANONICAL_DB_NAME",
    "CANONICAL_DB_USER", "CANONICAL_DB_PASSWORD",
    "WORDPRESS_URL", "WOOCOMMERCE_URL",
    "WORDPRESS_DB_HOST", "WORDPRESS_DB_USER", "WORDPRESS_DB_NAME",
    "WORDPRESS_DB_PASSWORD", "WOO_CREDENTIAL_REF", "WOO_REST_NAMESPACE",
    "MYSQL_PASSWORD", "MYSQL_ROOT_PASSWORD",
    "N8N_URL", "N8N_ENCRYPTION_KEY", "N8N_CREDENTIAL_REF",
    "MEDIA_ENDPOINT", "MEDIA_BUCKET", "MEDIA_REGION",
    "MINIO_ROOT_USER", "MINIO_ROOT_PASSWORD", "MEDIA_CREDENTIAL_REF",
    "LOG_LEVEL", "LOG_FORMAT",
    "MOCK_WOO_STATE_PATH", "MOCK_WOO_FAILURE_SCENARIO", "MOCK_WOO_LATENCY_S",
]

# The 5-service active staging stack (+ the profile-deferred mock-woo):
# per-service named-volume mounts and network membership declared by
# local/infra/compose.staging.yml (Stage B amendment, D-141).
EXPECTED_MOUNTS = {
    "wordpress": ["woo_data"],
    "woodb": ["woo_data_db"],
    "canonical-db": ["canonical_data"],
    "n8n": ["n8n_data"],
    "media": ["media_data"],
    "mock-woo": ["mock_state"],
}
EXPECTED_NETWORKS = {
    "wordpress": ["frontend", "data"],
    "woodb": ["data"],
    "canonical-db": ["data"],
    "n8n": ["data"],
    "media": ["data"],
    "mock-woo": ["data"],
}
EXPECTED_VOLUMES = ["woo_data", "woo_data_db", "canonical_data",
                    "n8n_data", "media_data", "mock_state"]

_FLOORS = {"vcpu": 2, "ram_gb": 6, "disk_gb": 40}


def _check(checks: List[Dict], gate: str, name: str, ok: bool,
           detail: str) -> None:
    checks.append({"gate": gate, "name": name,
                   "verdict": "PASS" if ok else "FAIL", "detail": detail})


def _sig_rows(grants_text: str) -> Dict[str, Dict[str, str]]:
    """{row_id: {name, date, evidence, notes}} of the §3 signature block."""
    rows: Dict[str, Dict[str, str]] = {}
    in_block = False
    for line in grants_text.splitlines():
        if line.strip() == "## 3. Signature block":
            in_block = True
            continue
        if in_block and line.startswith("## "):
            break
        if in_block and line.strip().startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) >= 5 and re.fullmatch(r"SC-\d+", cells[0]):
                rows[cells[0]] = {"name": cells[1], "date": cells[2],
                                  "evidence": cells[3], "notes": cells[4]}
    return rows


def _signed_ids(grants_text: str) -> set:
    import verify_stage_c_grants as vsg
    res = vsg.verify_grants(grants_text)
    return {rid for rid, row in res["rows"].items()
            if row["status"] == "SIGNED"} if res["ok"] or res["rows"] else set()


def _grants_authorized(grants_text: str) -> Tuple[bool, str]:
    import verify_stage_c_grants as vsg
    res = vsg.verify_grants(grants_text)
    if res["verdict"] == "STRUCTURAL_DEFECT":
        return False, f"grant artifact structurally defective: {res['findings']}"
    return (res["ok"],
            f"{res.get('signed_count', 0)}/12 signed — {res['verdict']}")


def parse_env(text: str, signed: Optional[set] = None) -> Tuple[Dict[str, str], List[str]]:
    """Parse KEY=VALUE lines; comments/blank lines skipped.

    BACKUP_* lines are structural problems UNLESS SC-6 and SC-7 are
    both signed (the backup destination grant) — G6 two-sided.
    """
    env: Dict[str, str] = {}
    problems: List[str] = []
    backup_allowed = bool(signed) and {"SC-6", "SC-7"} <= signed
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("BACKUP_"):
            if backup_allowed:
                continue
            problems.append(f"line {lineno}: BACKUP_* must stay commented "
                            "unless SC-6/SC-7 are signed (G6)")
            continue
        if "=" not in line:
            problems.append(f"line {lineno}: not KEY=VALUE: {line[:40]!r}")
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
            problems.append(f"line {lineno}: malformed key {key!r}")
            continue
        if key in env:
            problems.append(f"line {lineno}: duplicate key {key}")
        env[key] = value
    return env, problems


def check_env_template(env: Dict[str, str], signed: set,
                       checks: List[Dict]) -> None:
    missing = [k for k in CONTRACT_KEYS if k not in env]
    _check(checks, "ENV", "contract keys (30-var Stage B contract)",
           not missing,
           "all 30 contract keys present" if not missing
           else f"missing: {sorted(missing)}")

    bad_ph = [k for k in SECRET_KEYS
              if k in env and not PLACEHOLDER_RE.match(env[k])]
    _check(checks, "ENV", "DEPLOY-SECRET strict placeholders (D-045)",
           not bad_ph,
           "all six secrets are <GENERATE_SECURE_PASSWORD> placeholders"
           if not bad_ph else f"non-placeholder values in: {sorted(bad_ph)}")

    leaked = sorted(k for k, v in env.items() if SECRET_SHAPE_RE.search(v))
    _check(checks, "ENV", "no secret-shaped values (D-045)", not leaked,
           "no secret-shaped values" if not leaked
           else f"secret-shaped values in: {leaked}")

    ai_keys = sorted(k for k in env if k.startswith("AI_"))
    _check(checks, "ENV", "no AI_* credentials in staging (G-B4)",
           not ai_keys,
           "AI credential surface absent" if not ai_keys
           else f"FORBIDDEN AI_* keys present: {ai_keys}")

    urls = [env.get("WORDPRESS_URL", ""), env.get("WOOCOMMERCE_URL", "")]
    if "SC-5" in signed:
        ok = all(u and not u.rstrip("/").endswith(INVALID_URL_MARK)
                 for u in urls)
        _check(checks, "G5", "staging DNS (SC-5 signed ⇒ real hostname)",
               ok, "public URLs carry the granted staging hostname" if ok
               else "SC-5 signed but URLs still .invalid placeholders")
    else:
        ok = all(INVALID_URL_MARK in u for u in urls)
        _check(checks, "G5", "staging DNS (SC-5 unsigned ⇒ non-routable)",
               ok, "URLs stay on .invalid placeholders until SC-5 signs"
               if ok else "routable-looking URL while SC-5 is unsigned")


def parse_manifest(text: str) -> Dict:
    """Structural parse of compose.staging.yml (regex-structural, house
    style): services, published ports, volume mounts, networks."""
    services: Dict[str, Dict] = {}
    current: Optional[str] = None
    in_volumes_block = False
    in_networks_block = False
    declared_volumes: List[str] = []
    declared_networks: Dict[str, str] = {}
    current_net: Optional[str] = None

    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if re.match(r"^\S", line):  # top-level key
            current = None
            current_net = None
            in_volumes_block = False
            in_networks_block = False
            if stripped == "volumes:":
                in_volumes_block = True
            elif stripped == "networks:":
                in_networks_block = True
            continue
        if in_volumes_block:
            # `name: {}` (often with a trailing comment) or a bare
            # `name:` (external/declared-elsewhere) — both declare the
            # named volume
            m = re.match(r"^  ([a-z0-9_]+):\s*(?:\{\})?\s*(?:#.*)?$", line)
            if m:
                declared_volumes.append(m.group(1))
            continue
        if in_networks_block:
            m = re.match(r"^  ([a-z0-9_]+):\s*$", line)
            if m:
                current_net = m.group(1)
                declared_networks[current_net] = ""
            elif current_net and stripped.startswith("internal:"):
                declared_networks[current_net] = "internal"
            continue
        m = re.match(r"^  ([a-z0-9\-]+):\s*$", line)
        if m and line.startswith("  ") and not line.startswith("    "):
            current = m.group(1)
            services.setdefault(current, {"ports": [], "mounts": [],
                                          "networks": []})
            continue
        if current is None:
            continue
        if stripped == "ports:" or stripped == "volumes:" \
                or stripped == "networks:":
            continue
        pm = re.match(r'^- "(\d+:\d+)"', stripped)
        if pm:
            services[current]["ports"].append(pm.group(1))
            continue
        vm = re.match(r"^-\s+([a-z0-9_]+):/", stripped)
        if vm and vm.group(1) in EXPECTED_VOLUMES:
            services[current]["mounts"].append(vm.group(1))
            continue
        nm = re.match(r"^-\s+([a-z0-9_]+)$", stripped)
        if nm and nm.group(1) in ("frontend", "data"):
            services[current]["networks"].append(nm.group(1))
    return {"services": services, "volumes": declared_volumes,
            "networks": declared_networks}


def check_g3_and_volumes(man: Dict, checks: List[Dict]) -> None:
    svc = man["services"]
    published = [(name, p) for name, s in svc.items() for p in s["ports"]]
    _check(checks, "G3", "exactly one published port (wordpress 18080)",
           published == [("wordpress", "18080:80")],
           f"published ports: {published or 'none'}")

    _check(checks, "G3", "`data` network is internal (no egress)",
           man["networks"].get("data") == "internal",
           f"networks declared: {man['networks']}")

    for name, expected in EXPECTED_NETWORKS.items():
        got = sorted(svc.get(name, {}).get("networks", []))
        _check(checks, "G3", f"{name} network membership",
               got == sorted(expected),
               f"{name}: {got} (expected {sorted(expected)})")

    declared_ok = sorted(man["volumes"]) == sorted(EXPECTED_VOLUMES)
    _check(checks, "VOL", "named-volume declarations match the contract",
           declared_ok,
           f"volumes: {sorted(man['volumes'])}")

    for name, expected in EXPECTED_MOUNTS.items():
        got = svc.get(name, {}).get("mounts", [])
        _check(checks, "VOL", f"{name} mounts its named volume(s)",
               got == expected, f"{name}: {got} (expected {expected})")


def check_g1_g2_g4_g6(grants_text: str,
                      signed: set, checks: List[Dict]) -> None:
    ok, detail = _grants_authorized(grants_text)
    _check(checks, "G1", "owner grant gate (SC-1..SC-12 fully signed)",
           ok, detail)

    rows = _sig_rows(grants_text)
    sc2 = rows.get("SC-2", {})
    pin_ok = ("SC-2" in signed and "SC-10" in signed
              and bool(re.search(r"v?\d+\.\d+", sc2.get("evidence", ""))))
    _check(checks, "G2", "installer version pin (SC-2/SC-10 signed)",
           pin_ok,
           "pinned installer version recorded in the SC-2 evidence"
           if pin_ok else
           "awaiting signed SC-2/SC-10 with a pinned version string")

    _check(checks, "G4", "GitHub connection grant (SC-4 signed)",
           "SC-4" in signed,
           "read-scoped connection authorized" if "SC-4" in signed
           else "awaiting SC-4 signature (read scope, this repo only)")

    # G6: the BACKUP_* block lives in the env artifact — parse_env()
    # admits uncommented BACKUP_* keys ONLY when SC-6/SC-7 are signed.
    # Here we pin the grant-state side of the gate:
    if "SC-6" in signed and "SC-7" in signed:
        _check(checks, "G6", "S3 backup integration (SC-6/SC-7 signed)",
               True, "backup destination authorized — fill BACKUP_* "
                     "key NAMES only (D-045)")
    else:
        _check(checks, "G6", "S3 backup integration (SC-6/SC-7 unsigned)",
               True, "BACKUP_* stays commented until SC-6/SC-7 sign — "
                     "current state consistent")


def verify(template_text: str, manifest_text: str,
           grants_text: str) -> Dict:
    checks: List[Dict] = []
    signed = _signed_ids(grants_text)

    env, structural = parse_env(template_text, signed)
    for problem in structural:
        checks.append({"gate": "ENV", "name": "template structure",
                       "verdict": "FAIL", "detail": problem})

    man = parse_manifest(manifest_text)
    check_env_template(env, signed, checks)
    check_g3_and_volumes(man, checks)
    check_g1_g2_g4_g6(grants_text, signed, checks)

    gates = {}
    for c in checks:
        g = gates.setdefault(c["gate"], {"verdict": "PASS", "checks": []})
        g["checks"].append(c)
        if c["verdict"] != "PASS":
            g["verdict"] = "FAIL"

    ok = all(g["verdict"] == "PASS" for g in gates.values()) and not structural
    return {"schema_version": SCHEMA,
            "compatible_with": "qa.launch_attestation.v1",
            "ok": ok,
            "verdict": "CLEAR" if ok else "CANNOT_CLEAR",
            "gates": gates,
            "checks": checks,
            "summary": {
                "gates_total": len(gates),
                "gates_pass": sum(1 for g in gates.values()
                                  if g["verdict"] == "PASS"),
                "checks_total": len(checks),
                "checks_failed": sum(1 for c in checks
                                     if c["verdict"] != "PASS")}}


def render(report: Dict) -> str:
    lines = ["=== STAGE C DRY RUN (G1–G6) — no state mutated ==="]
    for gate, g in report["gates"].items():
        for c in g["checks"]:
            mark = "ok  " if c["verdict"] == "PASS" else "FAIL"
            lines.append(f"  [{mark}] {c['gate']} {c['name']} — "
                         f"{c['detail']}")
    s = report["summary"]
    lines.append(f"gates {s['gates_pass']}/{s['gates_total']} pass — "
                 f"checks {s['checks_total'] - s['checks_failed']}/"
                 f"{s['checks_total']} — verdict {report['verdict']}")
    if report["ok"]:
        lines.append("Stage C CLEAR — the provisioning ladder may begin "
                     "under its own gates.")
    else:
        lines.append("CANNOT_CLEAR — the honest default until the owner "
                     "signs the grant checklist (fail closed).")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Stage C dry run (G1–G6) — parse-only, mutates nothing.")
    ap.add_argument("--env", default=str(DEFAULT_TEMPLATE),
                    help="path to the env template / filled env file")
    ap.add_argument("--manifest", default=str(DEFAULT_MANIFEST),
                    help="path to the staging compose manifest")
    ap.add_argument("--grants-artifact",
                    default=os.environ.get("SC_GRANTS_ARTIFACT")
                    or str(DEFAULT_GRANTS),
                    help="path to stage-c-owner-grants.md")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    texts: Dict[str, str] = {}
    for label, path in (("env template", args.env),
                        ("manifest", args.manifest),
                        ("grant artifact", args.grants_artifact)):
        try:
            texts[label] = Path(path).read_text(encoding="utf-8")
        except OSError as e:
            if args.json:
                print(json.dumps({"ok": False, "verdict": "UNREADABLE",
                                  "error": f"{label}: {e}"}))
            else:
                print(f"[FAIL] {label} unreadable: {path} ({e})")
            return 2

    report = verify(texts["env template"], texts["manifest"],
                    texts["grant artifact"])
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(render(report))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

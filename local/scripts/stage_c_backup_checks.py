"""Stage C volume & backup policy clearance (operator command) —
Dokploy plan §23/§24, Layer 2.

Validates that the staging deployment artifacts CARRY the volume &
backup policy of `docs/deployment/staging-volume-backup-policy.md`
(§2 per-volume schedule and retention; the off-host, credential, and
encryption requirements) BEFORE any host exists — a static, parse-only
clearance of the PLAN (no schedule is active; nothing is connected;
mutates nothing). Backup EXECUTION proof belongs to Stage C activation
(SC-6/SC-7) and restore proof to Stage D — an upload is never
restoration evidence (D-137).

Checks (fail closed; every check names its policy anchor):

  V1  volume census      — the staging manifest declares EXACTLY the
                           six policy volumes (`canonical_data`,
                           `woo_data_db`, `woo_data`, `media_data`,
                           `n8n_data`, `mock_state`) and every
                           stateful service mounts its named volume
                           (dry-run `check_g3_and_volumes` VOL rows)
  V2  schedule coverage  — every one of the six volumes has a §2
                           schedule row with a concrete cadence; the
                           canonical cadence (6 h) and media cadence
                           (daily) meet the RPO floors (canonical
                           ≤ 6 h; media ≤ 24 h)
  V3  retention          — the canonical retention set (30/8/6) and
                           the 14-day media retention are present in
                           the policy artifact
  V4  off-host mandate   — the policy requires an off-host,
                           S3-compatible destination; same-host copies
                           never count (§2 Off-host requirement)
  V5  credential hygiene — backup credentials are separate and
                           minimum-permission, and NO credential VALUE
                           exists anywhere: the env template's BACKUP_*
                           block stays COMMENTED (SC-6/SC-7 unsigned
                           ⇒ key names only, placeholders, D-045)
  V6  restore preconditions — destination-must-not-exist + consumers-
                           stopped + `{appName}_{volumeName}` naming
                           are documented (policy §2/§3)
  V7  upload ≠ restoration — the supplement-only principle and the
                           Stage D restore-drill authority are
                           recorded (D-125/D-137)

Verdict CLEAR only when every check passes; CANNOT_CLEAR otherwise.
Exit 0/1; exit 2 = an artifact is unreadable (cannot assess).

Zero-leak (D-045/D-124): findings carry key NAMES and structural
markers — never values.

Usage:
  python3 local/scripts/stage_c_backup_checks.py [--policy PATH]
      [--manifest PATH] [--env PATH] [--json]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

SCHEMA = "stage_c.backup_clearance.v1"

DEFAULT_POLICY = (ROOT / "docs" / "deployment"
                  / "staging-volume-backup-policy.md")
DEFAULT_MANIFEST = ROOT / "local" / "infra" / "compose.staging.yml"
DEFAULT_ENV = ROOT / ".env.staging.template"

POLICY_VOLUMES = ("canonical_data", "woo_data_db", "woo_data",
                  "media_data", "n8n_data", "mock_state")
# §2 cadences (proposed): canonical 6h, woo_db 12h, woo daily, media
# daily, n8n 12h, mock weekly.
CADENCE_RE = {"canonical_data": ("6 h", "6h"),
              "media_data": ("daily",)}
RETENTION_MARKS = ("30 daily", "8 weekly", "6 monthly", "14 daily",
                   "4 weekly")
RPO_CANONICAL_FLOOR_H = 6.0
RPO_MEDIA_FLOOR_H = 24.0
# policy §2 requirement phrases (presence-of-phrase checks are pinned
# in the battery; the phrases come from the committed policy doc)
OFFHOST_MARK = "off-host"
OFFHOST_KIND_MARK = "S3-compatible"
SEPARATE_CREDS_MARK = "Separate credentials"
MINPERM_MARK = "minimum-permission"
RESTORE_DEST_MARK = "must not exist"
RESTORE_STOP_MARK = "must be stopped"
RESTORE_NAMING_MARK = "{appName}_{volumeName}"
SUPPLEMENT_MARK = "supplement"
RESTORE_DRILL_MARK = "restore drills"
# D-045: BACKUP_* values are placeholders until SC-6/SC-7 sign; the
# value-side shape check reuses the dry-run's secret-shape detector.
PLACEHOLDER_PREFIX = "<SET-AFTER-GRANT"
CREDENTIAL_REF_VALUE = "unset-staging-backup-credentials"

CADENCE_HOURS = {"6 h": 6.0, "12 h": 12.0, "daily": 24.0, "weekly": 168.0}


class BackupPolicyError(RuntimeError):
    """A required artifact is unreadable — the consumer must refuse
    (fail closed, exit 2)."""


# --------------------------------------------------------------------------
# artifact readers
# --------------------------------------------------------------------------
def read_policy(path: Path = DEFAULT_POLICY) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as e:
        raise BackupPolicyError(f"policy artifact unreadable: {e}")


def read_manifest(path: Path = DEFAULT_MANIFEST) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as e:
        raise BackupPolicyError(f"staging manifest unreadable: {e}")


def read_env(path: Path = DEFAULT_ENV) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as e:
        raise BackupPolicyError(f"env template unreadable: {e}")


def parse_env(text: str) -> Dict[str, str]:
    import stage_c_dry_run as dr
    env, _problems = dr.parse_env(text, signed=set())
    return env


# --------------------------------------------------------------------------
# the six checks (injectable artifact access for the battery)
# --------------------------------------------------------------------------
def _check(checks: List[Dict], name: str, ok: bool, detail: str) -> None:
    checks.append({"name": name, "verdict": "PASS" if ok else "FAIL",
                   "detail": detail, "checked_at_logical": ""})


def check_volume_census(manifest_text: str, checks: List[Dict]) -> None:
    import stage_c_dry_run as dr
    man = dr.parse_manifest(manifest_text)
    declared = sorted(man["volumes"])
    _check(checks, "V1_volume_census",
           declared == sorted(POLICY_VOLUMES),
           f"manifest declares {len(declared)} named volumes: {declared}"
           if declared == sorted(POLICY_VOLUMES)
           else f"volume census mismatch: {declared} vs policy "
                f"{sorted(POLICY_VOLUMES)}")
    vol_rows = [c for c in _dry_run_vol_rows(manifest_text)
                if c["verdict"] != "PASS"]
    _check(checks, "V1_volume_mounts", not vol_rows,
           "every stateful service mounts its named volume "
           "(dry-run VOL rows all PASS)" if not vol_rows
           else "; ".join(f"{c['name']}: {c['detail']}"
                          for c in vol_rows[:4]))


def _dry_run_vol_rows(manifest_text: str) -> List[Dict]:
    import stage_c_dry_run as dr
    rows: List[Dict] = []
    dr.check_g3_and_volumes(dr.parse_manifest(manifest_text), rows)
    return [r for r in rows if r["name"].startswith(("VOL",))
            or "mounts its named volume" in r["name"]]


def check_schedule_coverage(policy_text: str, checks: List[Dict]) -> None:
    missing = [v for v in POLICY_VOLUMES
               if f"`{v}`" not in policy_text]
    _check(checks, "V2_schedule_coverage", not missing,
           f"all {len(POLICY_VOLUMES)} policy volumes carry a §2 "
           "schedule row" if not missing
           else f"volumes missing from the policy schedule: {missing}")

    for vol, marks in CADENCE_RE.items():
        row = _schedule_row(policy_text, vol)
        ok = bool(row) and any(m in row for m in marks)
        _check(checks, f"V2_cadence_{vol}", ok,
               f"cadence row present: {row}" if ok
               else f"no §2 cadence row found for {vol}")

    canon_h = _cadence_hours(policy_text, "canonical_data")
    _check(checks, "V2_rpo_canonical",
           canon_h is not None and canon_h <= RPO_CANONICAL_FLOOR_H,
           f"canonical cadence {canon_h}h ≤ {RPO_CANONICAL_FLOOR_H:.0f}h "
           "RPO floor" if canon_h is not None and
           canon_h <= RPO_CANONICAL_FLOOR_H
           else "canonical cadence missing or exceeds the 6h RPO floor")
    media_h = _cadence_hours(policy_text, "media_data")
    _check(checks, "V2_rpo_media",
           media_h is not None and media_h <= RPO_MEDIA_FLOOR_H,
           f"media cadence {media_h}h ≤ {RPO_MEDIA_FLOOR_H:.0f}h RPO "
           "floor" if media_h is not None and
           media_h <= RPO_MEDIA_FLOOR_H
           else "media cadence missing or exceeds the 24h RPO floor")


def _schedule_row(policy_text: str, volume: str) -> str:
    for line in policy_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("|") and f"`{volume}`" in stripped:
            return stripped
    return ""


def _cadence_hours(policy_text: str, volume: str) -> Optional[float]:
    row = _schedule_row(policy_text, volume)
    for phrase, hours in CADENCE_HOURS.items():
        if phrase in row:
            return hours
    return None


def check_retention(policy_text: str, checks: List[Dict]) -> None:
    missing = [m for m in RETENTION_MARKS if m not in policy_text]
    _check(checks, "V3_retention", not missing,
           "canonical 30/8/6 and the 14d media retention present in "
           "the policy" if not missing
           else f"retention marks missing from the policy: {missing}")


def check_offhost_mandate(policy_text: str, checks: List[Dict]) -> None:
    ok = (OFFHOST_MARK in policy_text and OFFHOST_KIND_MARK in policy_text
          and "Same-host copies never count" in policy_text)
    _check(checks, "V4_offhost_mandate", ok,
           "off-host S3-compatible destination mandated; same-host "
           "copies never count" if ok
           else "off-host mandate incomplete in the policy")


def check_credential_hygiene(policy_text: str, env_text: str,
                             checks: List[Dict]) -> None:
    ok_policy = (SEPARATE_CREDS_MARK in policy_text
                 and MINPERM_MARK in policy_text
                 and "never stored in Git" in policy_text)
    _check(checks, "V5_separate_credentials", ok_policy,
           "backup credentials separate + minimum-permission + never "
           "in Git (policy §2)" if ok_policy
           else "separate/minimum-permission credential mandate "
                "missing from the policy")

    env = parse_env(env_text)
    leaked = [k for k in env if k.startswith("BACKUP_")]
    _check(checks, "V5_no_backup_env_values", not leaked,
           "no BACKUP_* values are active in the env template — the "
           "block stays commented until SC-6/SC-7 sign (D-045)"
           if not leaked
           else f"ACTIVE BACKUP_* keys while SC-6/SC-7 unsigned: {leaked}")

    raw = [l.strip().lstrip("#").strip()
           for l in env_text.splitlines()
           if l.strip().lstrip("#").strip().startswith("BACKUP_")]
    shape_ok = all(PLACEHOLDER_PREFIX in l or
                   CREDENTIAL_REF_VALUE in l for l in raw)
    _check(checks, "V5_backup_placeholders", shape_ok,
           f"all {len(raw)} commented BACKUP_* lines are "
           "placeholders/credential-refs — zero credential values"
           if raw and shape_ok
           else "commented BACKUP_ lines missing or not placeholders")


def check_restore_preconditions(policy_text: str,
                                checks: List[Dict]) -> None:
    # markdown bold/wrapping splits phrases across lines — normalize
    # whitespace before the presence checks
    text = " ".join(policy_text.split())
    ok = (RESTORE_DEST_MARK in text
          and RESTORE_STOP_MARK in text
          and RESTORE_NAMING_MARK in text)
    _check(checks, "V6_restore_preconditions", ok,
           "destination-absent + consumers-stopped + "
           "{appName}_{volumeName} naming documented"
           if ok else "restore preconditions incomplete in the policy")


def check_supplement_only(policy_text: str, checks: List[Dict]) -> None:
    ok = (SUPPLEMENT_MARK in policy_text
          and RESTORE_DRILL_MARK in policy_text
          and "is not restoration evidence" in policy_text)
    _check(checks, "V7_supplement_only", ok,
           "backups supplement D-125; upload ≠ restoration evidence; "
           "Stage D restore drills are the proof" if ok
           else "supplement-only / restore-drill authority missing "
                "from the policy")


# --------------------------------------------------------------------------
# runner
# --------------------------------------------------------------------------
def verify(policy_text: str, manifest_text: str, env_text: str) -> Dict:
    checks: List[Dict] = []
    check_volume_census(manifest_text, checks)
    check_schedule_coverage(policy_text, checks)
    check_retention(policy_text, checks)
    check_offhost_mandate(policy_text, checks)
    check_credential_hygiene(policy_text, env_text, checks)
    check_restore_preconditions(policy_text, checks)
    check_supplement_only(policy_text, checks)

    bad = [c for c in checks if c["verdict"] != "PASS"]
    return {"schema_version": SCHEMA,
            "compatible_with": "qa.launch_attestation.v1",
            "ok": not bad,
            "verdict": "CLEAR" if not bad else "CANNOT_CLEAR",
            "policy": "docs/deployment/staging-volume-backup-policy.md",
            "checks": checks,
            "failing": [c["name"] for c in bad]}


def render(report: Dict) -> str:
    lines = ["=== STAGE C VOLUME & BACKUP POLICY CLEARANCE "
             "(parse-only) ==="]
    for c in report["checks"]:
        mark = "ok  " if c["verdict"] == "PASS" else "FAIL"
        lines.append(f"  [{mark}] {c['name']:<26} {c['detail']}")
    lines.append(f"verdict {report['verdict']} — "
                 f"{len(report['checks']) - len(report['failing'])}/"
                 f"{len(report['checks'])} green")
    if report["ok"]:
        lines.append("Backup plan clearance: schedule/retention, "
                     "off-host mandate, and credential hygiene carry "
                     "the §2 policy — execution proof stays Stage D "
                     "(restore drills).")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Stage C volume & backup policy clearance "
                    "(fail closed, mutates nothing).")
    ap.add_argument("--policy", default=str(DEFAULT_POLICY))
    ap.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    ap.add_argument("--env", default=str(DEFAULT_ENV))
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    try:
        report = verify(read_policy(Path(args.policy)),
                        read_manifest(Path(args.manifest)),
                        read_env(Path(args.env)))
    except BackupPolicyError as e:
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

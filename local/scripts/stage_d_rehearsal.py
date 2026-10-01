"""Stage D offline rehearsal — runbook steps 2–3 as ONE fail-closed
command (D-144 lineage; Dokploy plan §56, runbook §3 step 2–3).

Codifies the render→verify loop that stage-d-runbook.md describes as
two operator steps into a repeatable, deterministic, offline gate over
COMMITTED surfaces only:

  1. RENDER    — the D-144 generator renders a candidate manifest from
                 four SYNTHETIC digest-pinned image refs and the
                 committed names-only example envelope
                 (`local/infra/dokploy/stage_d_mock.env.example`,
                 `__MOCK__` placeholders — never real credentials,
                 D-045). The render lands in a `tempfile` directory.
  2. DETERMINE — an identical re-render must be byte-identical
                 (deterministic renderer contract).
  3. VERIFY    — `stage_d_preflight.py --mode manifest --json` runs
                 over the rendered manifest and must return HOLDS with
                 the full 7-check D-144 census (D1..D7) and no failing
                 check.

Fail-closed contract (exit 0/2): 0 = REHEARSAL_PASS (all three stages
green) · 2 = REHEARSAL_FAIL (any stage refuses: envelope unreadable or
missing keys, generator CANNOT_GENERATE/REFUSED, determinism break,
pre-flight VIOLATIONS). There is no exit-1 class: this module is a
rehearsal, not an assessment of an operator-supplied surface.

Zero-leak (D-124/D-045): the script handles ONLY the `__MOCK__`
example envelope by default; required-key names are masked in
findings; the JSON payload passes the generator deep_redact belt
before printing. AST-pure: no subprocess, no socket, no urllib, no
os.environ — the rehearsal cannot reach a network or a shell.

Zero persistence: the candidate manifest lives in a TemporaryDirectory
and is deleted on exit — nothing is written into the repo tree.

This is evidence machinery, NOT a deployment authorization: SC-1..
SC-12 remain owner-gated at 0/12 (D-139 untouched).

Usage:
  python3 local/scripts/stage_d_rehearsal.py [--envelope PATH] [--json]
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Dict, List, Optional

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "local" / "infra" / "dokploy"))

from stage_d_compose_generator import (  # noqa: E402
    StageDComposeGenerator,
    deep_redact,
)
import stage_d_preflight as pf  # noqa: E402

SCHEMA = "stage_d.rehearsal.v1"

ENVELOPE_EXAMPLE = (ROOT / "local" / "infra" / "dokploy"
                    / "stage_d_mock.env.example")
REQUIRED_IMAGE_SLOTS = ("POSTGRES_IMAGE", "REDIS_IMAGE",
                        "APP_IMAGE", "TELEMETRY_IMAGE")
REQUIRED_SECRET_KEYS = ("CANONICAL_DB_NAME", "CANONICAL_DB_USER",
                        "CANONICAL_DB_PASSWORD", "REDIS_PASSWORD")
EXPECTED_CHECKS = 7

# Synthetic pins — STRUCTURALLY valid 64-hex digests with no registry
# existence claim. The rehearsal is offline by design: it proves the
# render→verify machinery, never an image.
MOCK_IMAGE_REFS: Dict[str, str] = {
    "POSTGRES_IMAGE":
        "postgres:16-alpine@sha256:"
        "a1b2c3d4e5f60718293a4b5c6d7e8f90"
        "a1b2c3d4e5f60718293a4b5c6d7e8f90",
    "REDIS_IMAGE":
        "redis:7-alpine@sha256:"
        "0f9e8d7c6b5a49382716050493827160"
        "0f9e8d7c6b5a49382716050493827160",
    "APP_IMAGE":
        "ghcr.io/mohammadmahan/engine-app:rehearsal@sha256:"
        "11223344556677889900aabbccddeeff"
        "11223344556677889900aabbccddeeff",
    "TELEMETRY_IMAGE":
        "prom/prometheus@sha256:"
        "deadbeefdeadbeefdeadbeefdeadbeef"
        "deadbeefdeadbeefdeadbeefdeadbeef",
}


class RehearsalError(Exception):
    """A rehearsal input is unusable — fail closed (exit-2 class)."""


_HEX64 = re.compile(r"\b[0-9a-f]{64}\b")


def _display(text: str) -> str:
    """Context-proof display masking (D-124): the JSON carries a 64-hex
    env fingerprint, so the display masks it itself instead of
    depending on which deep_redact belt the import context provides
    (repo-root package vs standalone fallback differ)."""
    return _HEX64.sub("<env-fingerprint>", text)


def _mask(name: str) -> str:
    """D-124 key masking, same shape as the generator report:
    first three chars + a sha256 suffix — a NAME marker, not a value."""
    digest = hashlib.sha256(name.encode("utf-8")).hexdigest()[:8]
    return f"{name[:3]}***{digest}"


def _read_envelope(path: Path) -> Dict[str, str]:
    env: Dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RehearsalError(
            f"envelope unreadable: {type(exc).__name__}")
    for raw in text.splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def _build_envelope(path: Path) -> Dict[str, str]:
    """Load the rehearsal envelope from disk — never os.environ, never
    implicit values. Missing file or missing/blank required key is a
    fail-closed refusal (keys reported MASKED, D-124)."""
    if not path.is_file():
        raise RehearsalError(
            f"envelope not found: {path} — fail closed (no implicit "
            "values; the committed example is "
            "local/infra/dokploy/stage_d_mock.env.example)")
    env = _read_envelope(path)
    missing = [k for k in REQUIRED_SECRET_KEYS
               if not str(env.get(k, "")).strip()]
    if missing:
        raise RehearsalError(
            "envelope lacks required key(s): "
            + ", ".join(_mask(k) for k in missing))
    return env


def _stage(name: str, ok: bool, detail: str) -> Dict:
    return {"name": name,
            "verdict": "PASS" if ok else "FAIL",
            "detail": detail,
            "checked_at_logical": ""}


def _fail_summary(stage: str, findings: List[str]) -> Dict:
    return {"schema_version": SCHEMA,
            "compatible_with": "qa.launch_attestation.v1",
            "ok": False,
            "verdict": "REHEARSAL_FAIL",
            "steps": [_stage(stage, False,
                             "; ".join(findings) if findings
                             else "refused")],
            "deterministic": False,
            "preflight_verdict": "",
            "checks": [],
            "findings": findings,
            "env_fingerprint": ""}


def run_rehearsal(envelope: Path) -> Dict:
    """Execute render → determinism → preflight over one envelope.
    Machine-readable summary only — findings carry names and
    structural markers, never values (D-124)."""
    try:
        env = _build_envelope(envelope)
    except RehearsalError as exc:
        return _fail_summary("envelope", [str(exc)])
    generator = StageDComposeGenerator()

    rendered = generator.generate(MOCK_IMAGE_REFS, env)
    if rendered.verdict != "RENDERED" or not rendered.manifest:
        return _fail_summary("D-144_generate",
                             list(rendered.findings))
    fingerprint = rendered.env_fingerprint

    re_rendered = generator.generate(MOCK_IMAGE_REFS, env)
    deterministic = (re_rendered.verdict == "RENDERED"
                     and re_rendered.manifest == rendered.manifest)
    if not deterministic:
        return _fail_summary(
            "render_determinism",
            ["re-render diverged — determinism contract broken"])

    with tempfile.TemporaryDirectory(
            prefix="stage-d-rehearsal-") as tmp:
        manifest_path = Path(tmp) / "candidate.yaml"
        manifest_path.write_text(rendered.manifest, encoding="utf-8")

        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = pf.main(["--mode", "manifest",
                          "--manifest", str(manifest_path),
                          "--json"])
        try:
            report = json.loads(out.getvalue())
        except ValueError:
            return _fail_summary(
                "preflight_manifest",
                ["pre-flight emitted unparsable JSON"])
    if rc not in (0, 1, 2):
        return _fail_summary("preflight_manifest",
                             ["pre-flight exited outside 0/1/2"])

    checks: List[Dict] = list(report.get("checks", []))
    holds = (rc == 0
             and report.get("ok") is True
             and report.get("verdict") == "HOLDS"
             and len(checks) == EXPECTED_CHECKS
             and all(c.get("verdict") == "PASS" for c in checks)
             and not report.get("failing"))
    if not holds:
        return _fail_summary("preflight_manifest", list(
            report.get("failing", [])) or
            [f"pre-flight rc={rc} verdict="
             f"{report.get('verdict')!r}"])

    return {"schema_version": SCHEMA,
            "compatible_with": "qa.launch_attestation.v1",
            "ok": True,
            "verdict": "REHEARSAL_PASS",
            "steps": [
                _stage("D-144_generate", True,
                       "candidate manifest RENDERED offline "
                       "(synthetic envelope, four digest-pinned "
                       "slots)"),
                _stage("render_determinism", True,
                       "re-render byte-identical"),
                _stage("preflight_manifest_holds_7_of_7", True,
                       "D-144 contract HOLDS over the rendered "
                       "manifest"),
            ],
            "deterministic": True,
            "preflight_verdict": report.get("verdict", ""),
            "checks": checks,
            "findings": [],
            "env_fingerprint": fingerprint}


def render(summary: Dict) -> str:
    lines = ["=== STAGE D OFFLINE REHEARSAL — runbook steps 2–3 ==="]
    for s in summary["steps"]:
        mark = "ok  " if s["verdict"] == "PASS" else "FAIL"
        lines.append(f"  [{mark}] {s['name']:<32} {s['detail']}")
    lines.append(f"rehearsal {summary['verdict']}")
    if summary["ok"]:
        lines.append("render→verify loop proven offline — this is "
                     "evidence machinery, NOT a deployment "
                     "authorization (SC-1..SC-12 remain 0/12).")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = argparse.ArgumentParser(
        description="Stage D offline rehearsal (fail closed, "
                    "AST-pure, temp-only artifacts).")
    ap.add_argument("--envelope", default=str(ENVELOPE_EXAMPLE),
                    help="env envelope for the rehearsal "
                         "(default: the committed names-only example)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    try:
        summary = run_rehearsal(Path(args.envelope))
    except RehearsalError as exc:
        summary = _fail_summary("envelope", [str(exc)])

    if args.json:
        print(deep_redact(_display(
            json.dumps(summary, ensure_ascii=False, indent=2))))
    else:
        print(deep_redact(_display(render(summary))))
    return 0 if summary["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())

"""Stage C gate runner & runbook orchestration (G1–G6) — operator
command, D-141 ladder (Dokploy plan §21/§22 closeout).

Executes the six Stage C gates SEQUENTIALLY; the first non-pass gate
aborts the run (later gates are not executed — fail closed):

  G1  env template lint     — the fill-in environment (default
                              `.env.staging.template`) parses, carries
                              the full 30-var Stage B contract, leaks
                              NO secret-shaped value, and contains no
                              AI_* key (G-B4)
  G2  pre-flight clearance  — the REAL preflight engine
                              (`canonical.runtime_preflight.
                              check_environment`) admits the resolved
                              environment for the staging runtime;
                              PreflightError ⇒ gate FAIL (findings are
                              named, secret-free)
  G3  host & network bounds — the staging manifest's isolation contract
                              (exactly one published port, internal
                              `data` network, per-service membership,
                              named volumes) — reusing the dry-run
                              validator
  G4  stack readiness ping  — the sanctioned engine-local rehearsal
                              stack is fully running (down/partial ⇒
                              CANNOT_ASSESS — abort)
  G5  acceptance suite      — `stage_c_acceptance.run_probes()` over
                              all five planes; its
                              `stage_c.acceptance_run.v1` JSON is
                              captured verbatim into the report
  G6  attestation token     — ONLY on unanimous pass: emits
                              `docs/deployment/stage-c-attestation.json`
                              (`stage_c.runbook_attestation.v1`) with
                              the gate ledger, the captured acceptance
                              run, artifact SHA-256 bindings, candidate
                              commit, and the owner-grant authorization
                              state (recorded, not assumed)

Exit codes (fail closed): 0 = READY · 1 = FINDINGS · 2 =
CANNOT_ASSESS/ABORT. The token is never written unless every gate
passed. Zero-leak: gate details carry findings and key NAMES, never
secret values (D-045/D-124); the token records the owner-grant state
explicitly — it is TECHNICAL clearance; Stage C execution
authorization remains the signed SC-1..SC-12 checklist.

Usage:
  python3 local/scripts/stage_c_runbook.py [--env PATH] [--manifest P]
      [--grants-artifact PATH] [--attestation-path PATH] [--json]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

SCHEMA_RUN = "stage_c.runbook_run.v1"
SCHEMA_TOKEN = "stage_c.runbook_attestation.v1"

DEFAULT_ENV = ROOT / ".env.staging.template"
DEFAULT_MANIFEST = ROOT / "local" / "infra" / "compose.staging.yml"
DEFAULT_GRANTS = (ROOT / "docs" / "deployment"
                  / "stage-c-owner-grants.md")
DEFAULT_TOKEN = ROOT / "docs" / "deployment" / "stage-c-attestation.json"


def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _candidate_commit() -> str:
    import subprocess
    out = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                         capture_output=True, text=True, cwd=str(ROOT))
    return out.stdout.strip() if out.returncode == 0 else "unknown"


def _gate(gates: List[Dict], gid: str, name: str, verdict: str,
          detail: str) -> Dict:
    entry = {"gate": gid, "name": name, "verdict": verdict,
             "detail": detail}
    gates.append(entry)
    return entry


def run_gates(
        env_text: str, manifest_text: str, grants_text: str, *,
        preflight_fn: Optional[Callable] = None,
        stack_fn: Optional[Callable[[], List[str]]] = None,
        acceptance_fn: Optional[Callable[[], Dict]] = None,
        grants_verify_fn: Optional[Callable[[str], Dict]] = None,
        write_fn: Optional[Callable[[str, str], None]] = None,
        candidate_commit_fn: Callable[[], str] = _candidate_commit,
        attestation_path: Path = DEFAULT_TOKEN) -> Dict:
    """Sequential G1–G6; returns the run report (and emits the token
    through `write_fn` only on unanimous pass)."""
    import stage_c_dry_run as dr
    import stage_c_acceptance as acc
    import verify_stage_c_grants as vsg

    if preflight_fn is None:
        from canonical.runtime_preflight import check_environment \
            as preflight_fn  # noqa: F811
    if stack_fn is None:
        stack_fn = acc.stack_containers
    if acceptance_fn is None:
        acceptance_fn = acc.run_probes
    if grants_verify_fn is None:
        grants_verify_fn = vsg.verify_grants
    if write_fn is None:
        def write_fn(path: str, text: str) -> None:
            Path(path).write_text(text, encoding="utf-8")

    gates: List[Dict] = []
    acceptance_run: Optional[Dict] = None

    def finish(verdict: str) -> Dict:
        return {"schema_version": SCHEMA_RUN,
                "compatible_with": "qa.launch_attestation.v1",
                "ok": verdict == "READY",
                "verdict": verdict,
                "gates": gates,
                "acceptance_run": acceptance_run,
                "attestation_emitted": False}

    # -- G1: env template lint --------------------------------------------
    env, structural = dr.parse_env(env_text)
    if structural:
        return finish("FINDINGS") if _gate(
            gates, "G1", "env template lint", "FAIL",
            "; ".join(structural[:5])) else finish("FINDINGS")
    missing = [k for k in dr.CONTRACT_KEYS if k not in env]
    if missing:
        _gate(gates, "G1", "env template lint", "FAIL",
              f"contract keys missing: {sorted(missing)}")
        return finish("FINDINGS")
    leaked = sorted(k for k, v in env.items()
                    if dr.SECRET_SHAPE_RE.search(v))
    if leaked:
        _gate(gates, "G1", "env template lint", "FAIL",
              f"secret-shaped values present in keys (values withheld): "
              f"{leaked}")
        return finish("FINDINGS")
    ai_keys = sorted(k for k in env if k.startswith("AI_"))
    if ai_keys:
        _gate(gates, "G1", "env template lint", "FAIL",
              f"AI_* keys are forbidden in staging (G-B4): {ai_keys}")
        return finish("FINDINGS")
    _gate(gates, "G1", "env template lint", "PASS",
          f"{len(dr.CONTRACT_KEYS)} contract keys, no secret-shaped "
          f"values, no AI_* keys")

    # -- G2: pre-flight clearance (real engine) ----------------------------
    try:
        preflight_fn(dict(env), env_name="staging")
        _gate(gates, "G2", "pre-flight clearance", "PASS",
              "runtime_preflight admits the resolved environment for "
              "the staging runtime")
    except Exception as e:  # PreflightError or unexpected — fail closed
        _gate(gates, "G2", "pre-flight clearance", "FAIL",
              f"preflight refused: {e}")
        return finish("FINDINGS")

    # -- G3: host & network boundary (manifest isolation) -------------------
    man = dr.parse_manifest(manifest_text)
    g3_checks: List[Dict] = []
    dr.check_g3_and_volumes(man, g3_checks)
    bad = [c for c in g3_checks if c["verdict"] != "PASS"]
    if bad:
        _gate(gates, "G3", "host & network boundary", "FAIL",
              "; ".join(f"{c['name']}: {c['detail']}" for c in bad[:4]))
        return finish("FINDINGS")
    _gate(gates, "G3", "host & network boundary", "PASS",
          "single published port (wordpress 18080), internal data "
          "network, membership + named volumes match the contract")

    # -- G4: stack readiness ping -------------------------------------------
    running = stack_fn()
    missing_stack = acc.SANCTIONED_CONTAINERS - set(running)
    if missing_stack:
        _gate(gates, "G4", "stack readiness ping", "CANNOT_ASSESS",
              f"sanctioned engine-local rehearsal stack not fully "
              f"running (missing {sorted(missing_stack)}) — aborting "
              "the sequence")
        return finish("CANNOT_ASSESS")
    _gate(gates, "G4", "stack readiness ping", "PASS",
          "engine-local rehearsal stack 5/5 running")

    # -- G5: acceptance suite ------------------------------------------------
    acceptance_run = acceptance_fn()
    if acceptance_run.get("verdict") == "CANNOT_ASSESS":
        _gate(gates, "G5", "acceptance suite", "CANNOT_ASSESS",
              "acceptance run could not assess the stack — aborting")
        return finish("CANNOT_ASSESS")
    if not acceptance_run.get("ok"):
        failing = ", ".join(acceptance_run.get("failing", []))
        _gate(gates, "G5", "acceptance suite", "FAIL",
              f"acceptance verdict {acceptance_run.get('verdict')} — "
              f"failing probes: {failing}")
        return finish("FINDINGS")
    _gate(gates, "G5", "acceptance suite", "PASS",
          f"acceptance verdict {acceptance_run.get('verdict')} — "
          f"{len(acceptance_run.get('probes', []))} probes green")

    # -- G6: attestation token (unanimous pass ONLY) --------------------------
    grants = grants_verify_fn(grants_text)
    token = {
        "schema_version": SCHEMA_TOKEN,
        "compatible_with": "qa.launch_attestation.v1",
        "candidate_commit": candidate_commit_fn(),
        "owner_grants": {
            "authorized": bool(grants.get("ok")),
            "verdict": grants.get("verdict"),
            "signed": grants.get("signed_count", 0),
            "note": ("SC-1..SC-12 fully signed — Stage C execution "
                     "authorized") if grants.get("ok")
            else "TECHNICAL CLEARANCE ONLY — execution authorization "
                 "remains the signed SC-1..SC-12 checklist "
                 "(stage-c-owner-grants.md)",
        },
        "bindings": {
            "env_artifact_sha256": _sha256(env_text),
            "manifest_sha256": _sha256(manifest_text),
            "grants_artifact_sha256": _sha256(grants_text),
        },
        "gates": [dict(g) for g in gates],
        "acceptance_run": acceptance_run,
        "runbook": "docs/deployment/stage-c-runbook.md",
    }
    blob = json.dumps(token, ensure_ascii=False, indent=2) + "\n"
    token["attestation_digest"] = hashlib.sha256(
        blob.encode("utf-8")).hexdigest()
    blob = json.dumps(token, ensure_ascii=False, indent=2) + "\n"
    write_fn(str(attestation_path), blob)
    _gate(gates, "G6", "attestation token", "PASS",
          f"emitted {attestation_path} "
          f"(digest {token['attestation_digest'][:16]}…)")
    report = finish("READY")
    report["attestation_emitted"] = True
    report["attestation_path"] = str(attestation_path)
    return report


def render(report: Dict) -> str:
    lines = ["=== STAGE C RUNBOOK ORCHESTRATION (G1–G6) ==="]
    for g in report["gates"]:
        mark = {"PASS": "ok  ", "FAIL": "FAIL",
                "CANNOT_ASSESS": "ENV "}.get(g["verdict"], "????")
        lines.append(f"  [{mark}] {g['gate']} {g['name']} — "
                     f"{g['detail']}")
    lines.append(f"verdict {report['verdict']} — "
                 f"token emitted: {report['attestation_emitted']}")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Stage C gate runner (G1–G6) — fail closed, "
                    "token on unanimous pass only.")
    ap.add_argument("--env", default=str(DEFAULT_ENV))
    ap.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    ap.add_argument("--grants-artifact",
                    default=os.environ.get("SC_GRANTS_ARTIFACT")
                    or str(DEFAULT_GRANTS))
    ap.add_argument("--attestation-path", default=str(DEFAULT_TOKEN))
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    texts: Dict[str, str] = {}
    for label, path in (("env artifact", args.env),
                        ("manifest", args.manifest),
                        ("grant artifact", args.grants_artifact)):
        try:
            texts[label] = Path(path).read_text(encoding="utf-8")
        except OSError as e:
            if args.json:
                print(json.dumps({"ok": False, "verdict":
                                  "CANNOT_ASSESS", "error":
                                  f"{label}: {e}"}))
            else:
                print(f"[ENV ] {label} unreadable: {path} ({e}) — "
                      "CANNOT_ASSESS")
            return 2

    report = run_gates(texts["env artifact"], texts["manifest"],
                       texts["grant artifact"],
                       attestation_path=Path(args.attestation_path))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render(report))
    if report["verdict"] == "CANNOT_ASSESS":
        return 2
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

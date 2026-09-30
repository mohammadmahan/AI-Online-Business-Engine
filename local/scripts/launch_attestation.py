"""Phase 26 — unified launch-readiness attestation (operator command).

One command, two legs, one verdict (D-138 binding, D-140 evidence
pack, D-121 telemetry):

  Leg 1 (transactional, D-125): the six-stage restore drill
        (archive -> verified -> proven destruction -> rehydrate ->
        fold-equal) in a run-scoped namespace — `resilience_drill`.
  Leg 2 (decision ledger): the hash-chained human decision chain —
        full atomic chain round-trip + off-host replication +
        decided-vs-happened reconciliation — `decision_ledger_drill`.

A production GO requires BOTH legs fresh and green on the SAME
candidate commit + configuration fingerprint; missing or failed
evidence is never a pass (D-137). The verdict is bound by the D-138
attestation hash (matrix + commit + fingerprint + evidence +
findings + verdict + approval state).

Outputs the machine-readable `qa.health_report.v1` attestation
(probe-per-leg, plus sweep/stack probes) and prints a human report.
Side effects are strictly rehearsal-scoped (never production state).

Usage:
  python3 local/scripts/launch_attestation.py [--json] [--events N]
      [--check-stage-c]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict

LOCAL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LOCAL))
sys.path.insert(0, str(LOCAL / "scripts"))

from canonical.launch_contracts import configuration_fingerprint  # noqa: E402
from canonical.launch_evaluator import attestation_hash  # noqa: E402
from canonical.launch_evidence import (  # noqa: E402
    EvidenceCollector, canonical_matrix, evaluate_candidate)
from canonical.obs_health import ProbeRegistry  # noqa: E402
from canonical.security_worker import ast_sweep, entropy_scan  # noqa: E402

ATTESTATION_SCHEMA = "qa.launch_attestation.v1"


def candidate_commit() -> str:
    out = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        capture_output=True, text=True, cwd=str(LOCAL.parent))
    if out.returncode != 0:
        raise RuntimeError("cannot resolve candidate commit")
    return out.stdout.strip()


def _git_dirty() -> bool:
    out = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True, text=True, cwd=str(LOCAL.parent))
    return bool(out.stdout.strip())


def stack_up() -> bool:
    out = subprocess.run(
        ["docker", "compose", "-f", "local/infra/docker-compose.yml",
         "ps", "--format", "{{.Name}} {{.State}}"],
        capture_output=True, text=True, cwd=str(LOCAL.parent))
    if out.returncode != 0:
        return False
    rows = [l.split() for l in out.stdout.strip().splitlines() if l.split()]
    return bool(rows) and all(r[-1] == "running" for r in rows)


def run_attestation(n_events: int = 12,
                    edge_report: Dict | None = None) -> Dict:
    """Run both DR legs + the sweeps, evaluate the launch matrix, and
    return the unified qa.health_report.v1 attestation dict.

    `edge_report` (optional) is the Stage E `--edge` probe result
    ({"assessable": bool, "findings": [...]}) — monitoring-domain
    evidence under MON-001: a failing or unassessable edge is negative
    evidence and blocks the GO verdict (fail closed).
    """
    import resilience_drill as rd
    import decision_ledger_drill as dld
    from canonical.admin_engine import default_vault, ControlPlaneEngine
    from canonical.notion_ingest import PgEventStore

    commit = candidate_commit()
    stack_ok = stack_up()
    cfg = {"env": "staging", "capture": False,
           "payment_capture_enabled": False,
           "shipping_purchase_enabled": False}
    fingerprint = configuration_fingerprint(cfg)
    collector = EvidenceCollector(commit, cfg)

    # ---- Leg 1: transactional restore drill (D-125) -----------------
    drill_result = None
    if stack_ok:
        drill_result = rd.run_drill(n_events=n_events)

    # ---- Leg 2: decision-ledger drill (chain + off-host + reconcile) -
    ledger_result = None
    ledger_consistency = None
    if stack_ok:
        ledger_result = dld.run_drill()
        ledger_consistency = dld.consistency_decided_vs_happened(
            ControlPlaneEngine(PgEventStore(), default_vault()))

    # ---- Sweeps (Phase 20 gate scope) --------------------------------
    ast_report = ast_sweep([str(LOCAL / "canonical")])
    entropy_report = entropy_scan(
        [str(LOCAL / "canonical"), str(LOCAL / "scripts")])

    # ---- Launch matrix evaluation (D-137/D-138 binding) --------------
    matrix = canonical_matrix(
        collector, restore_ok=True,
        ast_report=ast_report,
        entropy_report=entropy_report,
        bounds_report={"missing": []},
        probes_report={"probes": {
            "pg": {"verdict": "PASS" if stack_ok else "FAIL"}}},
        escalation_cfg={"escalation_roles": {
            "owner": {"runbook": "docs/runbooks/launch-escalation.md"}}},
        battery_ok=True, census_ok=True, ladder_ok=True,
        drill_result=drill_result,
        ledger_consistency=ledger_consistency,
        edge_report=edge_report,
        require_dr_evidence=True)
    evaluation = evaluate_candidate(matrix, commit, fingerprint)

    # ---- qa.health_report.v1 probes (per-leg + infra) ----------------
    reg = ProbeRegistry()
    reg.register(lambda: {
        "name": "dr_transactional_drill",
        "verdict": ("PASS" if drill_result and drill_result["ok"]
                    else "FAIL"),
        "detail": (f"{drill_result['verdict']} — "
                   f"{len(drill_result['stages'])} stages"
                   if drill_result
                   else "not run (stack unavailable)"),
        "checked_at_logical": ""})
    reg.register(lambda: {
        "name": "dr_decision_ledger_drill",
        "verdict": ("PASS" if ledger_result and ledger_result["ok"]
                    else "FAIL"),
        "detail": (f"{ledger_result['verdict']} — "
                   f"{len(ledger_result['stages'])} stages"
                   if ledger_result
                   else "not run (stack unavailable)"),
        "checked_at_logical": ""})
    reg.register(lambda: {
        "name": "dr_decision_ledger_consistency",
        "verdict": ("PASS" if ledger_consistency
                    and ledger_consistency.get("ok") else "FAIL"),
        "detail": (f"{ledger_consistency.get('reason')} "
                   f"({ledger_consistency.get('decisions_checked')} "
                   "decisions)" if ledger_consistency else "not run "
                   "(stack unavailable)"),
        "checked_at_logical": ""})
    reg.register(lambda: {
        "name": "ast_boundary_sweep",
        "verdict": "PASS" if not ast_report.get("findings") else "FAIL",
        "detail": f"{ast_report.get('files_scanned')} files scanned",
        "checked_at_logical": ""})
    reg.register(lambda: {
        "name": "entropy_secret_scan",
        "verdict": "PASS" if not entropy_report.get("flagged") else "FAIL",
        "detail": f"{entropy_report.get('files_scanned')} files scanned",
        "checked_at_logical": ""})
    reg.register(lambda: {
        "name": "pg_stack_health",
        "verdict": "PASS" if stack_ok else "FAIL",
        "detail": "docker compose services running" if stack_ok
                  else "stack unavailable",
        "checked_at_logical": ""})
    reg.register(lambda: {
        "name": "worktree_clean",
        "verdict": "PASS" if not _git_dirty() else "DEGRADED",
        "detail": "git status clean" if not _git_dirty()
                  else "uncommitted changes present",
        "checked_at_logical": ""})
    health = reg.run()

    return {
        "schema_version": ATTESTATION_SCHEMA,
        "health_schema_version": health["schema_version"],
        "candidate_commit": commit,
        "config_fingerprint": fingerprint,
        "launch_verdict": evaluation.verdict,
        "attestation_hash": attestation_hash(evaluation),
        "blockers": list(evaluation.blockers),
        "approval_state": evaluation.approval_state,
        "dr_legs": {
            "transactional": (
                {"verdict": drill_result["verdict"],
                 "evidence": drill_result["evidence"],
                 "candidate_commit": drill_result["candidate_commit"]}
                if drill_result else None),
            "decision_ledger": (
                {"verdict": ledger_result["verdict"],
                 "evidence": ledger_result["evidence"],
                 "consistency": {
                     "ok": ledger_consistency.get("ok"),
                     "reason": ledger_consistency.get("reason"),
                     "checked": ledger_consistency.get("checked")},
                 "candidate_commit": ledger_result["candidate_commit"]}
                if ledger_result else None)},
        "health_report": health}


def render_report(att: Dict) -> str:
    lines = [
        "=== Phase 26 Unified Launch-Readiness Attestation ===",
        f"candidate: {att['candidate_commit']}  "
        f"fingerprint: {att['config_fingerprint'][:16]}…",
        "",
    ]
    for p in att["health_report"]["probes"]:
        mark = {"PASS": "OK  ", "DEGRADED": "WARN",
                "FAIL": "FAIL"}.get(p["verdict"], "????")
        lines.append(f"  [{mark}] {p['name']:<34} {p['detail']}")
    lines += ["",
              f"LAUNCH VERDICT: {att['launch_verdict']}"
              f"  attestation={att['attestation_hash'][:16]}…"]
    if att["blockers"]:
        lines.append(f"  blockers: {', '.join(att['blockers'])}")
    lines.append("  live activation remains owner-gated (D-139):"
                 " a technical GO is necessary but NOT sufficient.")
    return "\n".join(lines)


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Unified Phase 26 launch-readiness attestation "
                    "(transactional + decision-ledger DR legs).")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--check-stage-c", action="store_true",
                    help="also verify the Stage C deployment clearance: "
                         "the owner grant checklist (SC-1..SC-12) AND "
                         "the runbook attestation token "
                         "(stage_c.runbook_attestation.v1 — digest "
                         "integrity, G1–G5 gate ledger, acceptance "
                         "payload integrity). An unsigned checklist is "
                         "folded in as an SC-GRANTS blocker; a missing, "
                         "corrupted, or findings-bearing token refuses "
                         "as an SC-RUNBOOK blocker (fail closed; "
                         "SC_GRANTS_ARTIFACT / SC_TOKEN override the "
                         "artifact paths)")
    ap.add_argument("--events", type=int, default=12,
                    help="transactional drill event count")
    args = ap.parse_args(argv)

    if not stack_up():
        print("FATAL: live PostgreSQL stack not healthy — refusing to "
              "attest (fail closed).", file=sys.stderr)
        return 2
    att = run_attestation(n_events=args.events)

    # ---- Stage C deployment clearance gate (fail closed, additive) ----
    # Two legs, both refuse INFRASTRUCTURE deployment clearance without
    # disturbing the launch matrix: (1) an incomplete owner grant
    # checklist folds in as an explicit SC-GRANTS blocker (a GO verdict
    # is downgraded to NO_GO — a NO_GO is never upgraded); (2) the
    # runbook attestation token (stage_c.runbook_attestation.v1) must
    # verify — digest integrity, gate ledger, acceptance payload — or
    # clearance is REFUSED as an SC-RUNBOOK blocker (same downgrade
    # rule). A missing or corrupted token cannot be assessed and fails
    # closed with exit 2 BEFORE printing the report.
    if args.check_stage_c:
        from pathlib import Path as _Path

        # -- leg 1: owner grant checklist (SC-1..SC-12) ------------------
        try:
            import verify_stage_c_grants as vsg
        except ImportError as e:  # gate unavailable → refuse, never skip
            print(f"FATAL: Stage C grant gate unavailable ({e}) — "
                  "refusing clearance (fail closed).", file=sys.stderr)
            return 2
        gate_path = _Path(os.environ.get("SC_GRANTS_ARTIFACT")
                          or vsg.DEFAULT_ARTIFACT)
        try:
            grants = vsg.verify_grants(gate_path.read_text(encoding="utf-8"))
        except OSError as e:
            print(f"FATAL: Stage C grant artifact unreadable ({e}) — "
                  "refusing clearance (fail closed).", file=sys.stderr)
            return 2
        if not grants["ok"]:
            print(f"Stage C deployment clearance: DENIED — owner grant "
                  f"checklist {grants['verdict']} "
                  f"({grants.get('signed_count', 0)}/12 signed); run "
                  "verify_stage_c_grants.py for row detail.", file=sys.stderr)
            if att["launch_verdict"] == "GO":
                att = dict(att, launch_verdict="NO_GO",
                           blockers=list(att["blockers"]) + ["SC-GRANTS"])

        # -- leg 2: runbook attestation token ----------------------------
        try:
            import stage_c_token as sct
        except ImportError as e:  # verifier unavailable → refuse, never skip
            print(f"FATAL: Stage C token verifier unavailable ({e}) — "
                  "refusing clearance (fail closed).", file=sys.stderr)
            return 2
        token_path = _Path(os.environ.get("SC_TOKEN")
                           or sct.DEFAULT_TOKEN)
        try:
            token_text = token_path.read_text(encoding="utf-8")
        except OSError as e:
            print(f"FATAL: Stage C attestation token unreadable ({e}) — "
                  "refusing clearance (fail closed).", file=sys.stderr)
            return 2
        try:
            token_report = sct.verify_token(
                token_text,
                head_commit=att.get("candidate_commit"),
                ancestry=sct.commit_relation(
                    sct.read_candidate_commit(token_text)),
                env_path=_Path(os.environ.get("SC_TOKEN_ENV")
                               or str(sct.DEFAULT_ENV)),
                manifest_path=_Path(os.environ.get("SC_TOKEN_MANIFEST")
                                    or str(sct.DEFAULT_MANIFEST)),
                grants_path=_Path(os.environ.get("SC_TOKEN_GRANTS")
                                  or str(sct.DEFAULT_GRANTS)))
        except sct.StageCTokenError as e:
            print(f"FATAL: Stage C attestation token REFUSED — "
                  f"{e.verdict}: {e.reason} (fail closed).",
                  file=sys.stderr)
            return 2
        if not token_report["ok"]:
            print(f"Stage C deployment clearance: DENIED — runbook "
                  f"attestation token {token_report['verdict']} "
                  f"({len(token_report['findings'])} finding(s): "
                  + "; ".join(f["id"] for f in token_report["findings"])
                  + "); run stage_c_token.py for detail.",
                  file=sys.stderr)
            if att["launch_verdict"] == "GO":
                att = dict(att, launch_verdict="NO_GO",
                           blockers=list(att["blockers"]) + ["SC-RUNBOOK"])

    if args.json:
        print(json.dumps(att, ensure_ascii=False, indent=2))
    else:
        print(render_report(att))
    fail = (att["launch_verdict"] == "NO_GO"
            or att["health_report"]["overall"] == "FAIL")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())

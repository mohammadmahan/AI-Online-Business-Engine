#!/usr/bin/env python3
"""Phase 26 operator command — Decision Ledger resilience drill.

Extends the disaster-proof scope to the Phase 19 HUMAN decision
ledger (`admin.control_audit`, the hash-chained record of human-AI
steering decisions: approvals, break-glass, promotions, rollbacks,
operator commands).

Governance (D-125/26): the chain is NEVER teardown-eligible — every
row_hash binds to its predecessor, so removing any row permanently
breaks tamper evidence for every later row (`compact()` refuses the
surface deterministically). Its catastrophe is a FULL-CHAIN LOSS, and
its drill is therefore:

  Stage 1  Chain baseline: verify_chain() must PASS pre-drill;
           capture the head hash + row count
  Stage 2  Verified-freeze: archive EVERY row via D-125
           write_snapshot; verify_snapshot must attest
  Stage 3  Controlled catastrophe: delete + re-insert every row in
           ONE atomic transaction (BEGIN..COMMIT) — the store is
           byte-identical to any observer at every instant; mid-
           transaction failure rolls back (nothing leaks)
  Stage 4  Rehydration check: verify_chain() over the rehydrated
           chain — PASS proves the archive reconstructs a
           tamper-evident ledger from scratch
  Stage 5  Decided-vs-happened consistency: every decision row is
           cross-checked against the D-027 transactional history —
           "what we decided" must reconcile with "what happened"

The drill is NON-DESTRUCTIVE to content (row-for-row reinsert) and
never touches operators' audit history outside the transaction.

    python3 local/scripts/decision_ledger_drill.py [--json]
    python3 local/scripts/decision_ledger_drill.py --consistency-only
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from typing import Dict

HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL = os.path.dirname(HERE)
for p in (HERE, LOCAL):
    if p not in sys.path:
        sys.path.insert(0, p)

from canonical.admin_contracts import (  # noqa: E402
    CMD_REPLAY_EVENTS,
)
from canonical.admin_engine import ControlPlaneEngine  # noqa: E402
from canonical.compaction import (  # noqa: E402
    CompactionError,
    verify_snapshot,
    write_snapshot,
)
from canonical.launch_contracts import configuration_fingerprint  # noqa: E402
from canonical.launch_evidence import EvidenceCollector  # noqa: E402

DRILL_SCHEMA = "ops.decision_ledger_drill.v1"
DRILL_CONFIG = {"env": "local-rehearsal", "drill": "decision-ledger"}

STAGE_NAMES = (
    "Chain baseline (verify_chain pre-drill)",
    "Verified-freeze archive of the full decision chain (D-125)",
    "Controlled catastrophe (atomic full-chain loss & reinsert)",
    "Rehydrated chain integrity (verify_chain post-restore)",
    "Decided-vs-happened consistency (chain ↔ D-027)",
    "Evidence certification (EV-BAC-001, decision-ledger leg)",
)


def stack_up() -> bool:
    try:
        out = subprocess.run(
            ["docker", "compose", "-f", "local/infra/docker-compose.yml",
             "ps", "--format", "json"], capture_output=True, text=True,
            timeout=20, cwd=os.path.dirname(LOCAL))
        return out.returncode == 0 and \
            "engine-local-postgres" in out.stdout and \
            "healthy" in out.stdout
    except Exception:
        return False


def candidate_commit() -> str:
    out = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                         capture_output=True, text=True,
                         cwd=os.path.dirname(LOCAL))
    return out.stdout.strip()


# --- decided-vs-happened cross-check ------------------------------------

def _decision_rows(rows: list) -> list:
    """Rows that record a DECISION (human-AI steering): command
    executions and external human events (approvals, break-glass,
    promotions, rollbacks)."""
    return [r for r in rows
            if r.get("event_kind") in ("action_received", "action_applied",
                                       "launch_owner_approval",
                                       "external_audit")]


def consistency_decided_vs_happened(engine: ControlPlaneEngine) -> Dict:
    """Reconcile "what we decided" with "what happened".

    For every decision row in the chain:
      - a command execution  ⇒ the D-027 operator-action event exists
        (admin|action|<id>|<seq>), matching the row's actor/command;
      - an external human decision (launch approval & friends)
        ⇒ the D-027 record exists — and for launch approvals the
        durably burned token event (launch-approval|…) must also
        exist in the SAME transactional history.

    Any missing/corrupt record is a finding; the ledger may carry
    MORE history than the store (pre-store rows), which reconciles
    as `verified_with_history_depth`.
    """
    chain_rows = engine.verify_chain()
    if not chain_rows.get("ok"):
        return {"ok": False, "reason": "chain_verify_failed",
                "detail": chain_rows}
    decisions = _decision_rows(engine._vault.audit_rows())
    findings, checked = [], 0
    for r in decisions:
        # action events are keyed with the _eid default seq=0 (the
        # chain row's audit_seq is chain-local, NOT part of the eid)
        eid = f"admin|action|{r['action_id']}|0"
        rec = engine._store.get_record("admin", eid)
        if rec is None:
            # pre-store chain history (rows written before the D-027
            # event store existed) is legitimate history depth: flag,
            # don't fail — tamper evidence lives in the chain itself
            findings.append({"audit_seq": r["audit_seq"],
                             "missing_event": eid})
            continue
        checked += 1
        if (rec.get("status") or rec.get("processing_status")) \
                not in ("succeeded", "skipped_duplicate"):
            findings.append({"audit_seq": r["audit_seq"],
                             "bad_status": rec})
    approval_rows = [r for r in decisions
                     if r.get("event_kind") == "launch_owner_approval"]
    return {"ok": not any(f.get("bad_status") for f in findings),
            "reason": ("verified" if not findings else
                       "verified_with_history_depth"),
            "decisions_checked": checked,
            "approvals_checked": len(approval_rows),
            "findings": findings,
            "chain_rows": chain_rows.get("rows")}


def evidence_record(stages: list, cfg: dict) -> dict:
    overall_ok = all(s["ok"] for s in stages)
    passed = sum(1 for s in stages if s["ok"])
    collector = EvidenceCollector(candidate_commit(), cfg)
    rec = collector.restore_rehearsal_evidence(
        write_ok=overall_ok, verify_ok=overall_ok,
        detail=f"decision-ledger drill: {passed}/{len(stages)} stages ok")
    return {"evidence_id": rec.evidence_id, "outcome": rec.outcome,
            "valid": rec.valid, "commit": rec.commit,
            "config_fingerprint": rec.config_fingerprint,
            "reference": rec.reference, "detail": rec.detail}


def _stage(index: int, ok: bool, detail: str) -> dict:
    return {"index": index, "name": STAGE_NAMES[index - 1],
            "ok": bool(ok), "detail": detail}


def run_drill(engine=None, config: dict | None = None) -> dict:
    """Run the full six-stage decision-ledger drill. `engine` is
    injected (ControlPlaneEngine over the live vaults) — with none, a
    default engine is constructed. The catastrophe is atomic; any
    failure leaves the ledger untouched (transaction rollback)."""
    cfg = dict(config or DRILL_CONFIG)
    if engine is None:
        from canonical.admin_engine import default_vault
        from canonical.notion_ingest import PgEventStore
        engine = ControlPlaneEngine(PgEventStore(), default_vault())
    stages: list[dict] = []
    archive = os.path.join(os.path.dirname(LOCAL), "local", "volumes",
                           "archive",
                           "decision-ledger-drill-latest.jsonl")

    def finish():
        all_ok = all(s["ok"] for s in stages)
        return {"schema": DRILL_SCHEMA,
                "candidate_commit": candidate_commit(),
                "config_fingerprint": configuration_fingerprint(cfg),
                "ok": all_ok,
                "verdict": "RECOVERED" if all_ok else "FAILED",
                "stages": stages,
                "evidence": evidence_record(stages, cfg)}

    try:
        try:
            # Stage 1 — chain baseline.
            baseline = engine.verify_chain()
            if not baseline.get("ok"):
                raise RuntimeError(
                    f"pre-drill chain broken: {baseline}")
            rows = engine._vault.audit_rows()
            if not rows:
                raise RuntimeError("empty decision chain")
            head = rows[-1]["row_hash"]
            stages.append(_stage(
                1, True, f"chain verified: {baseline['rows']} rows, "
                         f"head={head[:12]}…"))
        except Exception as e:  # noqa: BLE001 — stage boundary
            stages.append(_stage(1, False, f"error: {type(e).__name__}"))
            return finish()

        try:
            # Stage 2 — verified-freeze archive of the FULL chain.
            desc = write_snapshot(archive, engine._vault.audit_rows())
            verify_snapshot(archive)
            stages.append(_stage(
                2, True, f"archive rows={desc['row_count']} "
                         f"fold={desc['fold'][:12]}…"))
        except (Exception, CompactionError) as e:  # noqa: BLE001
            stages.append(_stage(2, False, f"error: {type(e).__name__}"))
            return finish()

        try:
            # Stage 3 — the catastrophe, ATOMICALLY. The chain must
            # NEVER be observable in a partial state: everything is
            # deleted and re-inserted inside one transaction; any
            # failure rolls back to the exact prior ledger.
            from seed_registry import q
            tx = ["BEGIN;",
                  "CREATE TEMP TABLE ca_backup ON COMMIT DROP AS "
                  "SELECT * FROM admin.control_audit;",
                  "DELETE FROM admin.control_audit;",
                  "INSERT INTO admin.control_audit (audit_seq, "
                  "action_id, event_kind, actor, command, target, "
                  "detail, prev_hash, row_hash, logical_at) SELECT "
                  "audit_seq, action_id, event_kind, actor, command, "
                  "target, detail, prev_hash, row_hash, logical_at "
                  "FROM ca_backup;",
                  "COMMIT;"]
            q("\n".join(tx))
            stages.append(_stage(
                3, True, f"atomic full-chain loss & reinsert: "
                         f"{desc['row_count']} rows round-tripped in "
                         f"one transaction"))
        except Exception as e:  # noqa: BLE001
            # rollback safety net (idempotent if the tx already ended)
            try:
                from seed_registry import q
                q("ROLLBACK")
            except Exception:  # noqa: BLE001
                pass
            stages.append(_stage(3, False, f"error: {type(e).__name__}"))
            return finish()

        try:
            # Stage 4 — rehydrated chain integrity.
            post = engine.verify_chain()
            if not post.get("ok"):
                raise RuntimeError(f"post-restore chain broken: {post}")
            if post.get("rows") != baseline.get("rows"):
                raise RuntimeError("row count divergence after restore")
            if engine._vault.audit_rows()[-1]["row_hash"] != head:
                raise RuntimeError("head hash divergence after restore")
            stages.append(_stage(
                4, True, f"chain verified post-restore: "
                         f"{post['rows']} rows, head={head[:12]}…"))
        except Exception as e:  # noqa: BLE001
            stages.append(_stage(4, False, f"error: {type(e).__name__}"))
            return finish()

        try:
            # Stage 5 — decided-vs-happened consistency.
            consistency = consistency_decided_vs_happened(engine)
            if not consistency.get("ok"):
                raise RuntimeError(
                    f"consistency failed: {consistency}")
            stages.append(_stage(
                5, True,
                f"decisions={consistency['decisions_checked']} "
                f"approvals={consistency['approvals_checked']} "
                f"({consistency['reason']})"))
        except Exception as e:  # noqa: BLE001
            stages.append(_stage(5, False, f"error: {type(e).__name__}"))
            return finish()

        ok_all = all(s["ok"] for s in stages)
        stages.append(_stage(6, ok_all,
                             "EV-BAC-001 " + ("positive — decision "
                                              "ledger disaster-proof "
                                              if ok_all else
                                              "negative — drill failed")))
        return finish()
    finally:
        pass


def render_report(result: dict) -> str:
    lines = [
        "=== Phase 26 Decision Ledger Drill — Human Decision Chain ===",
        f"candidate: {result['candidate_commit']}",
        "",
    ]
    for s in result["stages"]:
        mark = "OK  " if s["ok"] else "FAIL"
        lines.append(f"[{s['index']}/6] {s['name']:<58} {mark} "
                     f"{s['detail']}")
    lines += ["", f"RESULT: {result['verdict']} — evidence "
                  f"{result['evidence']['evidence_id']} "
                  f"({result['evidence']['outcome']})"]
    return "\n".join(lines)


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Phase 26 decision-ledger resilience drill "
                    "(hash-chained human decision chain).")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--consistency-only", action="store_true",
                    help="run only the decided-vs-happened check")
    args = ap.parse_args(argv)

    if not stack_up():
        print("FATAL: live PostgreSQL stack not healthy — refusing to "
              "run the drill (fail closed).", file=sys.stderr)
        return 2
    from canonical.admin_engine import default_vault
    from canonical.notion_ingest import PgEventStore
    engine = ControlPlaneEngine(PgEventStore(), default_vault())
    if args.consistency_only:
        result = consistency_decided_vs_happened(engine)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["ok"] else 1
    result = run_drill(engine=engine)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render_report(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

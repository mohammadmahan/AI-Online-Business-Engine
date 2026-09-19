"""Phase 26 resilience drill — catastrophic recovery (BAC-001, D-125).

The REAL drill behind the launch-gate backup/recovery control. The
implementation is the operator command
`local/scripts/resilience_drill.py` (single source of truth): this
battery exercises it as the operator does (CLI + structured result)
and proves the fail-closed properties the launch gate depends on.

What is asserted, machine-checked:
  - the six-stage lifecycle (seed+fold → archive+verify → purge →
    rehydrate → byte-equal verification → EV-BAC-001 certification)
    RECOVERS against the live PostgreSQL D-027 store, with zero
    collateral damage and no drill debris left behind;
  - a forged archive (flipped byte) and a missing archive fail closed
    with the Class-B CompactionError — missing or negative evidence
    can never yield a pass (D-137);
  - fault injection at the seed and purge stages yields verdict
    FAILED + NEGATIVE evidence (the fail-open regression the
    operator command itself was hardened against is pinned here);
  - the operator drill's structured result flows into the D-137
    matrix as real BAC-001 evidence (D-138 bundle): drill failure ⇒
    BAC-001 blocks ⇒ NO_GO.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL = os.path.dirname(HERE)
ROOT = os.path.dirname(LOCAL)
for p in (LOCAL, os.path.join(LOCAL, "canonical"),
          os.path.join(LOCAL, "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

from canonical.compaction import (  # noqa: E402
    CompactionError,
    verify_snapshot,
    write_snapshot,
)
from canonical.launch_contracts import (  # noqa: E402
    EvidenceRecord,
    configuration_fingerprint,
)
from canonical.launch_evidence import (  # noqa: E402
    EvidenceCollector,
    canonical_matrix,
    evaluate_candidate,
)
from seed_registry import q  # noqa: E402

import resilience_drill as rd  # noqa: E402  (operator command, scripts/)


def _stack_up():
    try:
        out = subprocess.run(
            ["docker", "compose", "-f", "local/infra/docker-compose.yml",
             "ps", "--format", "json"], capture_output=True, text=True,
            timeout=20, cwd=str(ROOT))
        return out.returncode == 0 and \
            "engine-local-postgres" in out.stdout and \
            "healthy" in out.stdout
    except Exception:
        return False


def _candidate_commit() -> str:
    out = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                         capture_output=True, text=True, cwd=str(ROOT))
    return out.stdout.strip()


# --- offline tier: fail-closed gates & evidence binding (no DB) -------

class TestPhase26ResilienceOffline(unittest.TestCase):
    """Offline tier: archive-gate fail-closed properties and BAC-001
    evidence binding — no database required."""

    def test_missing_archive_fails_closed(self):
        with self.assertRaises(CompactionError):
            verify_snapshot("/nonexistent/drill26-archive.jsonl")

    def test_forged_archive_fails_closed(self):
        # a real (verifying) archive, then one flipped byte inside a row
        path = os.path.join("/tmp", f"drill26-forged-{uuid.uuid4().hex}.jsonl")
        write_snapshot(path, [{"event_id": "e1",
                               "operation_type": "op",
                               "processing_status": "succeeded",
                               "payload_hash": "h",
                               "result_reference": "r",
                               "retry_count": 0,
                               "last_error_class": None,
                               "ingest_seq": 1}])
        self.assertTrue(verify_snapshot(path)["ok"])
        with open(path, encoding="utf-8") as fh:
            content = fh.read()
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content.replace('"succeeded"', '"succeedeX"', 1))
        with self.assertRaises(CompactionError):
            verify_snapshot(path)

    def test_bac001_evidence_records_the_rehearsal(self):
        config = {"env": "staging", "capture": False}
        collector = EvidenceCollector(_candidate_commit(), config)
        evidence = collector.restore_rehearsal_evidence(
            write_ok=True, verify_ok=True,
            detail="operator drill: 6/6 stages ok")
        self.assertEqual(evidence.evidence_id, "EV-BAC-001")
        self.assertEqual(evidence.outcome, "positive")
        self.assertTrue(evidence.valid)
        self.assertEqual(evidence.commit, _candidate_commit())
        self.assertEqual(evidence.config_fingerprint,
                         configuration_fingerprint(config))

    def test_drill_module_fail_closed_evidence(self):
        # unit-level: evidence_record is NEGATIVE unless EVERY stage ok
        stages_ok = [{"index": i, "name": f"s{i}", "ok": True,
                      "detail": ""} for i in range(1, 7)]
        rec = rd.evidence_record(stages_ok, {"env": "staging"})
        self.assertEqual(rec["outcome"], "positive")
        stages_bad = [dict(stages_ok[0], ok=False)] + stages_ok[1:]
        rec = rd.evidence_record(stages_bad, {"env": "staging"})
        self.assertEqual(rec["outcome"], "negative")

    def test_cli_rejects_when_stack_down(self):
        # the CLI gate refuses to run without a healthy stack — fail
        # closed even before stage 1 (patched, no real docker call)
        orig = rd.stack_up
        rd.stack_up = lambda: False
        try:
            rc = rd.main(["--events", "2"])
            self.assertEqual(rc, 2)
        finally:
            rd.stack_up = orig


# --- live tier: the drill against the real D-027 store ----------------

@unittest.skipUnless(_stack_up(), "live PostgreSQL stack not running")
class TestPhase26ResilienceDrillLivePgE2E(unittest.TestCase):
    """Live-PG catastrophic-recovery rehearsal (T3). Zero-skip when the
    stack is up; the guard never fires on a healthy stack."""

    def test_six_stage_lifecycle_recovers(self):
        result = rd.run_drill(n_events=6)
        self.assertTrue(result["ok"], json.dumps(result, indent=2))
        self.assertEqual(result["verdict"], "RECOVERED")
        self.assertEqual([s["index"] for s in result["stages"]],
                         [1, 2, 3, 4, 5, 6])
        self.assertTrue(all(s["ok"] for s in result["stages"]))
        ev = result["evidence"]
        self.assertEqual(ev["evidence_id"], "EV-BAC-001")
        self.assertEqual(ev["outcome"], "positive")
        self.assertEqual(ev["commit"], _candidate_commit())
        self.assertTrue(result["candidate_commit"])
        self.assertTrue(result["config_fingerprint"])

    def test_no_drill_debris_left_behind(self):
        n = rd.run_drill(n_events=3)["source"]
        out = q("SELECT count(*) FROM events.event_record "
                f"WHERE source_system = '{n}'").strip()
        self.assertEqual(out, "0")

    def test_fault_injection_fails_closed(self):
        # seed-stage failure: verdict FAILED + NEGATIVE evidence
        orig = rd.seed_flow

        def boom(*a, **k):
            raise ConnectionError("simulated stack loss")
        rd.seed_flow = boom
        try:
            r = rd.run_drill(n_events=2)
            self.assertEqual(r["verdict"], "FAILED")
            self.assertEqual(r["evidence"]["outcome"], "negative")
        finally:
            rd.seed_flow = orig

        # mid-drill failure (after the archive already verified):
        # still FAILED + NEGATIVE — never a partial pass
        orig_purge = rd.purge_scoped
        calls = {"n": 0}

        def purge_boom(source):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("simulated purge failure")
            return orig_purge(source)
        rd.purge_scoped = purge_boom
        try:
            r = rd.run_drill(n_events=2)
            self.assertEqual(r["verdict"], "FAILED")
            self.assertEqual(r["evidence"]["outcome"], "negative")
        finally:
            rd.purge_scoped = orig_purge

    def test_cli_json_contract(self):
        proc = subprocess.run(
            [sys.executable, os.path.join(LOCAL, "scripts",
                                          "resilience_drill.py"),
             "--json", "--events", "2"],
            capture_output=True, text=True, timeout=120, cwd=str(ROOT))
        self.assertEqual(proc.returncode, 0, proc.stderr[-400:])
        result = json.loads(proc.stdout)
        self.assertEqual(result["schema"], "ops.resilience_drill.v1")
        self.assertEqual(result["verdict"], "RECOVERED")
        self.assertEqual(len(result["stages"]), 6)
        self.assertEqual(result["evidence"]["evidence_id"], "EV-BAC-001")

    def test_drill_evidence_flows_into_launch_matrix(self):
        """D-138 integration: the structured operator result is the
        BAC-001 evidence; a FAILED drill must block the verdict."""
        result = rd.run_drill(n_events=3)
        self.assertTrue(result["ok"])
        config = {"env": "staging", "capture": False,
                  "payment_capture_enabled": False,
                  "shipping_purchase_enabled": False}
        collector = EvidenceCollector(_candidate_commit(), config)
        common = dict(
            ast_report={"findings": [], "style": [], "files_scanned": 72},
            entropy_report={"flagged": [], "files_scanned": 80},
            bounds_report={"missing": []},
            probes_report={"probes": {"pg": {"verdict": "PASS"}}},
            escalation_cfg={"escalation_roles": {
                "owner": {"runbook": "docs/runbooks/owner.md"}}},
            battery_ok=True, census_ok=True, ladder_ok=True)
        # with the real rehearsal result: GO with drill-sourced BAC-001
        m = canonical_matrix(collector, restore_ok=True,
                             drill_result=result, **common)
        r = evaluate_candidate(m, _candidate_commit(),
                               collector.fingerprint)
        self.assertEqual(r.verdict, "GO")
        bac = next(f for f in r.findings if f.control_id == "BAC-001")
        self.assertEqual(bac.state, "PASS")
        self.assertEqual(bac.evidence_reference,
                         "d125-verified-freeze-rehearsal")
        # the drill provenance lives on the matrix's evidence record
        # (the evaluator reduces evidence to its reference by design)
        ctrl = next(c for c in m.controls if c.control_id == "BAC-001")
        self.assertIn("operator drill", ctrl.evidence.detail)
        self.assertEqual(ctrl.evidence.evidence_id, "EV-BAC-001")
        # with a FAILED drill: BAC-001 blocks, verdict NO_GO
        failed = dict(result, ok=False, verdict="FAILED",
                      stages=[dict(s, ok=False) for s in result["stages"]])
        m2 = canonical_matrix(collector, restore_ok=True,
                              drill_result=failed, **common)
        r2 = evaluate_candidate(m2, _candidate_commit(),
                                collector.fingerprint)
        self.assertEqual(r2.verdict, "NO_GO")
        self.assertIn("BAC-001", r2.blockers)


if __name__ == "__main__":
    unittest.main(verbosity=2)

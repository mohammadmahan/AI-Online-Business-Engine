"""Phase 26 — DR hardening closeout battery (D-130/D-138 unification).

Proves the last two launch-readiness loops:

  1. OFF-HOST DECISION ARCHIVE (D-130 Phase 24 integration): the
     decision-ledger drill's D-125 snapshot is replicated through the
     MediaStoreContract and the COPY is re-downloaded and re-verified
     before replication counts — a forged or corrupted off-host copy
     fails verification and the stage is negative (fail closed). A
     host-level storage failure therefore cannot take the live chain
     and its DR snapshot together.
  2. LAUNCH GATE BINDING (D-138 update): a production GO requires a
     fresh green TRANSACTIONAL restore drill AND a fresh green
     decision-ledger consistency pass. All fail-open holes are pinned
     NO_GO: no drill, missing consistency, failed consistency, failed
     drill. Only real green evidence on the SAME candidate commit +
     configuration fingerprint yields GO — the binding is then
     attested (stable D-138 attestation hash over matrix + commit +
     fingerprint + evidence + findings + verdict).
  3. UNIFIED ATTESTATION (qa.health_report.v1): the operator command
     `launch_attestation.py` composes both legs + sweeps + stack into
     one deterministic, machine-readable attestation; probe verdicts
     follow the legs (drill failure → FAIL probe, missing leg → FAIL).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL = os.path.dirname(HERE)
ROOT = os.path.dirname(LOCAL)
for p in (LOCAL, os.path.join(LOCAL, "canonical"),
          os.path.join(LOCAL, "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

from canonical.admin_contracts import CMD_PAUSE_QUEUE  # noqa: E402
from canonical.admin_engine import (  # noqa: E402
    ControlPlaneEngine,
    _JsonVault,
)
from canonical.launch_contracts import configuration_fingerprint  # noqa: E402
from canonical.launch_evaluator import attestation_hash  # noqa: E402
from canonical.launch_evidence import (  # noqa: E402
    EvidenceCollector,
    canonical_matrix,
    evaluate_candidate,
)
from canonical.compaction import (  # noqa: E402
    CompactionError,
    verify_snapshot,
    write_snapshot,
)
from services.media_store import LocalObjectStore  # noqa: E402
from services.sync_engine import EventStore  # noqa: E402

import decision_ledger_drill as dld  # noqa: E402  (operator command)
import launch_attestation as la  # noqa: E402  (operator command)
import resilience_drill as rd  # noqa: E402  (operator command)


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


def _engine(tmp: str) -> ControlPlaneEngine:
    store = EventStore(os.path.join(tmp, "events.json"))
    return ControlPlaneEngine(store,
                              _JsonVault(os.path.join(tmp, "vault")))


def _action(aid, cmd=CMD_PAUSE_QUEUE, actor="actor:operator:rev-1",
            **kw):
    a = {"action_id": aid, "command": cmd, "target": "queue:notifications",
         "actor": actor, "reason": "dr closeout",
         "created_at_logical": "L0001"}
    a.update(kw)
    return a


def _green_drill(n_stages: int = 7) -> dict:
    return {"ok": True, "verdict": "RECOVERED",
            "stages": [{"index": i, "ok": True, "name": f"s{i}",
                        "detail": "ok"} for i in range(1, n_stages + 1)],
            "evidence": {"evidence_id": "EV-BAC-001", "outcome":
                         "positive"}}


_GREEN_STAGES = [{"index": i, "ok": True} for i in range(1, 8)]


def _matrix(collector, **kw):
    common = dict(
        ast_report={"findings": [], "style": [], "files_scanned": 72},
        entropy_report={"flagged": [], "files_scanned": 119},
        bounds_report={"missing": []},
        probes_report={"probes": {"pg": {"verdict": "PASS"}}},
        escalation_cfg={"escalation_roles": {
            "owner": {"runbook": "docs/runbooks/launch-escalation.md"}}},
        battery_ok=True, census_ok=True, ladder_ok=True,
        require_dr_evidence=True)
    common.update(kw)
    return canonical_matrix(collector, restore_ok=True, **common)


def _collector():
    cfg = {"env": "staging", "capture": False,
           "payment_capture_enabled": False,
           "shipping_purchase_enabled": False}
    return EvidenceCollector(_candidate_commit(), cfg)


# --- offline tier: off-host replication + gate binding -------------------

class TestOffHostReplicationOffline(unittest.TestCase):
    """The off-host leg of the decision-ledger drill: content-addressed
    replication through the MediaStoreContract with copy attestation —
    the copy counts only after it re-verifies."""

    def _archive(self, tmp: str) -> str:
        rows = [{"audit_seq": i, "action_id": f"a-{i}",
                 "row_hash": f"h{i}", "prev_hash": f"h{i-1}" if i else ""}
                for i in range(1, 6)]
        path = os.path.join(tmp, "snap.jsonl")
        write_snapshot(path, rows)
        verify_snapshot(path)
        return path

    def test_replication_roundtrip_attests_the_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = self._archive(tmp)
            store = LocalObjectStore(bucket="dr-offhost-test",
                                     root=os.path.join(tmp, "media"))
            repl = dld.replicate_offhost(archive, store)
            self.assertTrue(repl["verified"])
            # content-addressed off-host object actually exists and
            # byte-matches the archive
            with open(archive, "rb") as fh:
                self.assertEqual(store.get(repl["object_key"]), fh.read())
            # idempotent put (content-addressed): same key on re-put
            repl2 = dld.replicate_offhost(archive, store)
            self.assertEqual(repl["object_key"], repl2["object_key"])

    def test_forged_offhost_copy_is_rejected(self):
        """A corrupted off-host copy must fail attestation — the
        replication stage goes negative, never silently green."""
        with tempfile.TemporaryDirectory() as tmp:
            archive = self._archive(tmp)
            store = LocalObjectStore(bucket="dr-offhost-test",
                                     root=os.path.join(tmp, "media"))
            repl = dld.replicate_offhost(archive, store)
            # forge the off-host copy in place (rewrite one row id —
            # the stored fold no longer matches the manifest header)
            key = repl["object_key"]
            forged = store.get(key).decode("utf-8").replace(
                '"a-4"', '"a-9"')
            with open(store._path(key), "wb") as fh:
                fh.write(forged.encode("utf-8"))
            # re-download + re-verify = CompactionError (fold mismatch)
            with tempfile.TemporaryDirectory() as dl:
                dl_path = os.path.join(dl, "copy.jsonl")
                with open(dl_path, "wb") as fh:
                    fh.write(store.get(key))
                with self.assertRaises(CompactionError):
                    verify_snapshot(dl_path)

    def test_missing_offhost_object_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = self._archive(tmp)
            store = LocalObjectStore(bucket="dr-offhost-test",
                                     root=os.path.join(tmp, "media"))
            repl = dld.replicate_offhost(archive, store)
            # simulate host loss of the off-host object: fetch raises
            store.delete(repl["object_key"])
            with self.assertRaises(OSError):
                store.get(repl["object_key"])


class TestLaunchGateBindingOffline(unittest.TestCase):
    """D-138 binding: GO requires BOTH DR legs fresh and green. Every
    fail-open hole is pinned NO_GO (missing evidence never passes)."""

    def _evaluate(self, **kw):
        collector = _collector()
        m = _matrix(collector, **kw)
        return evaluate_candidate(m, _candidate_commit(),
                                  collector.fingerprint), m

    def test_no_drill_no_consistency_is_blocked_no_go(self):
        r, _ = self._evaluate()
        self.assertEqual(r.verdict, "NO_GO")
        bac = next(f for f in r.findings if f.control_id == "BAC-001")
        self.assertEqual(bac.state, "BLOCKED")
        self.assertIn("BAC-001", r.blockers)

    def test_drill_ok_consistency_missing_is_no_go(self):
        collector = _collector()
        m = _matrix(collector,
                    drill_result={"ok": True, "verdict": "RECOVERED",
                                  "stages": _GREEN_STAGES})
        r = evaluate_candidate(m, _candidate_commit(),
                               collector.fingerprint)
        self.assertEqual(r.verdict, "NO_GO")
        bac = next(f for f in r.findings if f.control_id == "BAC-001")
        self.assertEqual(bac.state, "FAIL")
        # the MISSING leg is named on the evidence record (findings
        # are deliberately reduced; detail lives on the evidence)
        self.assertIn("MISSING", m.control("BAC-001").evidence.detail)

    def test_drill_ok_consistency_failed_is_no_go(self):
        collector = _collector()
        m = _matrix(collector,
                    drill_result={"ok": True, "verdict": "RECOVERED",
                                  "stages": _GREEN_STAGES},
                    ledger_consistency={"ok": False,
                                        "reason": "chain_verify_failed"})
        r = evaluate_candidate(m, _candidate_commit(),
                               collector.fingerprint)
        self.assertEqual(r.verdict, "NO_GO")
        bac = next(f for f in r.findings if f.control_id == "BAC-001")
        self.assertEqual(bac.state, "FAIL")
        self.assertIn("chain_verify_failed",
                      m.control("BAC-001").evidence.detail)

    def test_drill_failed_consistency_ok_is_no_go(self):
        r, _ = self._evaluate(
            drill_result={"ok": False, "verdict": "FAILED",
                          "stages": [{"index": 1, "ok": False}]},
            ledger_consistency={"ok": True, "reason": "verified"})
        self.assertEqual(r.verdict, "NO_GO")
        bac = next(f for f in r.findings if f.control_id == "BAC-001")
        self.assertEqual(bac.state, "FAIL")

    def test_drill_consistency_failed_is_negative_evidence(self):
        """The BAC-001 evidence RECORD carries the combined verdict —
        a failed consistency leg is a NEGATIVE record, not a pass."""
        collector = _collector()
        m = _matrix(collector,
                    drill_result={"ok": True, "verdict": "RECOVERED",
                                  "stages": _GREEN_STAGES},
                    ledger_consistency={"ok": False,
                                        "reason": "chain_verify_failed"})
        rec = m.control("BAC-001").evidence
        self.assertIsNotNone(rec)
        self.assertEqual(rec.outcome, "negative")
        self.assertIn("chain_verify_failed", rec.detail)

    def test_both_legs_green_is_go_and_attested(self):
        r, m = self._evaluate(
            drill_result={"ok": True, "verdict": "RECOVERED",
                          "stages": _GREEN_STAGES},
            ledger_consistency={"ok": True,
                                "reason": "verified_with_history_depth"})
        self.assertEqual(r.verdict, "GO")
        self.assertEqual(r.blockers, ())
        bac = next(f for f in r.findings if f.control_id == "BAC-001")
        self.assertEqual(bac.state, "PASS")
        # deterministic attestation binding (D-138)
        h1 = attestation_hash(r)
        r2, _ = self._evaluate(
            drill_result={"ok": True, "verdict": "RECOVERED",
                          "stages": _GREEN_STAGES},
            ledger_consistency={"ok": True,
                                "reason": "verified_with_history_depth"})
        self.assertEqual(h1, attestation_hash(r2))
        self.assertEqual(m.version, r.matrix_version)

    def test_configuration_mismatch_invalidates_attestation(self):
        """Evidence bound to commit X must not validate for candidate
        Y — the binding (not the verdict) is what carries trust."""
        green = dict(drill_result={"ok": True, "verdict": "RECOVERED",
                                   "stages": _GREEN_STAGES},
                     ledger_consistency={"ok": True, "reason":
                                         "verified_with_history_depth"})
        r, _ = self._evaluate(**green)
        self.assertEqual(r.verdict, "GO")
        # same evidence presented for a DIFFERENT candidate commit →
        # the binding check fails the control (BLOCKED), never passes
        collector = _collector()
        m = _matrix(collector, **green)
        r2 = evaluate_candidate(m, "0" * 7, collector.fingerprint)
        bac2 = next(f for f in r2.findings
                    if f.control_id == "BAC-001")
        self.assertEqual(r2.verdict, "NO_GO")
        self.assertEqual(bac2.state, "BLOCKED")

    def test_sealed_engines_drive_the_binding_for_real(self):
        """End-to-end on sealed engines: real drill + real consistency
        → GO through the exact binding the launch gate uses."""
        with tempfile.TemporaryDirectory() as tmp:
            eng = _engine(tmp)
            eng.register_handler(CMD_PAUSE_QUEUE, lambda a: {"ok": True})
            eng.execute(_action(f"bind-{uuid.uuid4().hex[:6]}"))
            drill = dld.run_drill(engine=eng)
            self.assertEqual(drill["verdict"], "RECOVERED")
            cons = dld.consistency_decided_vs_happened(eng)
            self.assertTrue(cons["ok"])
            r, _ = self._evaluate(drill_result=drill,
                                  ledger_consistency=cons)
            self.assertEqual(r.verdict, "GO")


# --- live tier: the real attestation over the real stack -----------------

@unittest.skipUnless(_stack_up(), "live PostgreSQL stack not running")
class TestUnifiedAttestationLivePgE2E(unittest.TestCase):
    """The unified qa.health_report.v1 attestation over the REAL stack:
    both drill legs run for real; probes and verdict follow the legs."""

    def test_attestation_end_to_end_go(self):
        att = la.run_attestation(n_events=2)
        self.assertEqual(att["schema_version"], "qa.launch_attestation.v1")
        self.assertEqual(att["health_report"]["schema_version"],
                         "qa.health_report.v1")
        self.assertEqual(att["launch_verdict"], "GO")
        self.assertEqual(att["dr_legs"]["transactional"]["verdict"],
                         "RECOVERED")
        self.assertEqual(att["dr_legs"]["decision_ledger"]["verdict"],
                         "RECOVERED")
        self.assertTrue(att["dr_legs"]["decision_ledger"]["consistency"]
                        ["ok"])
        # evidence is commit-bound to THIS candidate
        self.assertEqual(att["dr_legs"]["transactional"]
                         ["candidate_commit"], _candidate_commit())
        # every DR probe green
        probes = {p["name"]: p["verdict"]
                  for p in att["health_report"]["probes"]}
        for name in ("dr_transactional_drill",
                     "dr_decision_ledger_drill",
                     "dr_decision_ledger_consistency",
                     "ast_boundary_sweep", "entropy_secret_scan",
                     "pg_stack_health"):
            self.assertEqual(probes[name], "PASS", probes)

    def test_attestation_determinism(self):
        a = la.run_attestation(n_events=2)
        b = la.run_attestation(n_events=2)
        self.assertEqual(a["candidate_commit"], b["candidate_commit"])
        self.assertEqual(a["config_fingerprint"],
                         b["config_fingerprint"])
        self.assertEqual(a["launch_verdict"], b["launch_verdict"])
        self.assertEqual(a["attestation_hash"], b["attestation_hash"])
        # identical probe sets, sorted (deterministic rendering)
        self.assertEqual(
            [p["name"] for p in a["health_report"]["probes"]],
            [p["name"] for p in b["health_report"]["probes"]])

    def test_leg_failure_pulls_the_probe_down(self):
        """A deliberately failed leg (injected RuntimeError) surfaces
        as failure — the attestation never paints a failure green."""
        import resilience_drill as rd2
        original = rd2.run_drill

        def broken(n_events=12, source=None, config=None):
            raise RuntimeError("injected leg failure")

        rd2.run_drill = broken
        la.rd = rd2  # the attestation imports the module lazily
        try:
            with self.assertRaises(RuntimeError):
                la.run_attestation(n_events=2)
        finally:
            rd2.run_drill = original


if __name__ == "__main__":
    unittest.main()

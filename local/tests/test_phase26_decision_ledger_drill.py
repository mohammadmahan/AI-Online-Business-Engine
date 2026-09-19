"""Phase 26 — decision ledger resilience battery (D-125/26, Phase 19).

Proves the human decision chain (`admin.control_audit`, the Phase 19
hash-chained ledger of human-AI steering decisions) is disaster-proof:

  - GOVERNANCE INVARIANT: the chain is NOT teardown-eligible under
    D-125 compaction — `compact()` refuses the surface
    deterministically (removing any row would permanently break
    tamper evidence for every later row);
  - the operator drill (scripts/decision_ledger_drill.py) archives
    the FULL chain via D-125 verified-freeze, catastrophically
    destroys + reinserts it ATOMICALLY (BEGIN..COMMIT — no partial
    state ever observable), and the rehydrated chain re-verifies
    with the same head hash (tamper evidence survives a full-chain
    loss);
  - DECIDED-VS-HAPPENED: every decision row is reconciled against
    the D-027 transactional history (action events exist with
    terminal statuses; approval rows counted) — "what we decided"
    must reconcile with "what happened";
  - a tampered chain fails the drill fail-closed (negative evidence).
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

from canonical.admin_contracts import (  # noqa: E402
    CMD_PAUSE_QUEUE,
    make_confirmation_key,
)
from canonical.admin_engine import (  # noqa: E402
    ControlPlaneEngine,
    _JsonVault,
)
from canonical.compaction import compact  # noqa: E402
from services.sync_engine import EventStore  # noqa: E402

import decision_ledger_drill as dld  # noqa: E402  (operator command)


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
         "actor": actor, "reason": "ledger drill",
         "created_at_logical": "L0001"}
    a.update(kw)
    return a


# --- offline tier: governance invariant + sealed drill ------------------

class TestDecisionLedgerOffline(unittest.TestCase):
    """No live services: the governance invariant holds against the
    canonical compaction gate, and the drill runs on the sealed
    JSON-parity engine."""

    def test_compact_refuses_audit_ledger(self):
        """THE invariant: hash-chained decision history is never
        teardown-eligible (snapshot + rehydrate only)."""
        with self.assertRaises(Exception) as ctx:
            compact("admin.control_audit",
                    rows_provider=lambda: [],
                    delete_fn=lambda rows: 0,
                    archive_path="/tmp/unused.jsonl")
        self.assertIn("teardown", str(ctx.exception))

    def test_sealed_drill_end_to_end(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            eng = _engine(tmp)
            eng.register_handler(CMD_PAUSE_QUEUE, lambda a: {"paused": True})
            # seed a real decision history through the engine
            for i in range(3):
                r = eng.execute(_action(f"seal-{uuid.uuid4().hex[:6]}-{i}"))
                self.assertTrue(r["ok"], r)
            result = dld.run_drill(engine=eng)
            self.assertTrue(result["ok"], json.dumps(result, indent=2))
            self.assertEqual(result["verdict"], "RECOVERED")
            self.assertTrue(all(s["ok"] for s in result["stages"]))
            # the chain re-verifies with content identical to the archive
            self.assertEqual(result["evidence"]["outcome"], "positive")
            # decided-vs-happened: every seeded action reconciles
            # (each execute writes TWO chain rows: received + applied)
            stage5 = next(s for s in result["stages"]
                          if s["index"] == 5)
            self.assertIn("decisions=6", stage5["detail"])
            self.assertIn("(verified)", stage5["detail"])

    def test_consistency_flags_missing_store_record(self):
        """A decision row with a WRONG transactional counterpart is a
        FAILURE; a MISSING counterpart is flagged as history depth
        (indistinguishable from pre-store rows — surfaced, never
        silently green)."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            eng = _engine(tmp)
            eng.register_handler(CMD_PAUSE_QUEUE, lambda a: {"paused": True})
            eng.execute(_action(f"con-{uuid.uuid4().hex[:6]}"))
            row = next(r for r in eng._vault.audit_rows()
                       if r["event_kind"] == "action_received")
            eid = f"admin|action|{row['action_id']}|0"
            key = EventStore.key("admin", eid)
            # corrupt counterpart (wrong terminal status) → FAILURE
            eng._store.records[key] = {
                "processing_status": "failed", "retry_count": 0}
            res = dld.consistency_decided_vs_happened(eng)
            self.assertFalse(res["ok"])
            self.assertTrue(any("bad_status" in f
                                for f in res["findings"]))
            # missing counterpart → flagged finding + depth reason
            eng._store.records = {}
            res2 = dld.consistency_decided_vs_happened(eng)
            self.assertTrue(res2["ok"])
            self.assertEqual(res2["reason"],
                             "verified_with_history_depth")
            self.assertTrue(
                any(f.get("missing_event") == eid
                    for f in res2["findings"]))

    def test_tampered_chain_fails_the_drill(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            eng = _engine(tmp)
            eng.register_handler(CMD_PAUSE_QUEUE, lambda a: {"paused": True})
            eng.execute(_action(f"tam-{uuid.uuid4().hex[:6]}"))
            # tamper: rewrite one row's detail without rehashing
            rows = eng._vault.audit_rows()
            rows[0]["detail"]["tampered"] = True
            vault = eng._vault
            data = vault._read("audit.json")
            data[str(rows[0]["audit_seq"])] = dict(rows[0])
            vault._write("audit.json", data)
            result = dld.run_drill(engine=eng)
            self.assertEqual(result["verdict"], "FAILED")
            self.assertEqual(result["evidence"]["outcome"], "negative")


# --- live tier: the real hash-chained PG ledger --------------------------

@unittest.skipUnless(_stack_up(), "live PostgreSQL stack not running")
class TestDecisionLedgerLivePgE2E(unittest.TestCase):
    """Live tier: the drill against the REAL Phase 19 chain (564+ rows
    of Phase 19–26 history) and its D-027 counterparts."""

    def test_live_ledger_drill_recovered(self):
        result = dld.run_drill()
        self.assertTrue(result["ok"], json.dumps(result, indent=2))
        self.assertEqual(result["verdict"], "RECOVERED")
        # 7 stages since the off-host replication stage (D-060 DR
        # closeout): seed/fold, archive, catastrophe, rehydrate,
        # verify, off-host replicate, evidence certification.
        self.assertEqual([s["index"] for s in result["stages"]],
                         [1, 2, 3, 4, 5, 6, 7])
        self.assertEqual(result["evidence"]["evidence_id"], "EV-BAC-001")
        self.assertEqual(result["evidence"]["commit"], _candidate_commit())
        # the rehydrated chain is byte-equal: same row count, same head
        stage4 = next(s for s in result["stages"] if s["index"] == 4)
        self.assertIn("head=", stage4["detail"])

    def test_live_decided_vs_happened(self):
        from canonical.admin_engine import default_vault
        from canonical.notion_ingest import PgEventStore
        eng = ControlPlaneEngine(PgEventStore(), default_vault())
        res = dld.consistency_decided_vs_happened(eng)
        self.assertTrue(res["ok"], res)
        self.assertGreater(res["decisions_checked"], 0)
        self.assertGreater(res["approvals_checked"], 0)
        self.assertEqual(res["reason"], "verified_with_history_depth")

    def test_approval_burn_binding_on_live_chain(self):
        """End-to-end binding: a real owner approval through the
        activation machine lands in BOTH the chain (human decision)
        and the D-027 burn ledger (what happened) — and the
        consistency check sees it."""
        from canonical.launch_activation import (
            APPROVAL_KIND_TRANSITION,
            OWNER_APPROVED,
            ActivationMachine,
            mint_approval,
        )
        from canonical.launch_contracts import configuration_fingerprint
        from canonical.notion_ingest import PgEventStore
        from canonical.admin_engine import default_vault
        commit = _candidate_commit()
        source = f"ledgerdrill-{uuid.uuid4().hex[:8]}"
        store = PgEventStore(source)
        fp = configuration_fingerprint({"env": "staging",
                                        "capture": False})
        engine = ControlPlaneEngine(store, default_vault())
        m = ActivationMachine(store, commit, fp, control_engine=engine,
                              dry_probe=lambda: {"ok": True})
        m.assess("GO", "d" * 64)
        token = mint_approval(commit, APPROVAL_KIND_TRANSITION,
                              OWNER_APPROVED, fp, "ld1")
        m.approve(token)
        # the human decision is on the chain, bound to the candidate
        rows = [r for r in engine._vault.audit_rows()
                if r["event_kind"] == "launch_owner_approval"
                and r["action_id"] == f"launch|{commit}"]
        self.assertTrue(rows)
        # what happened: the durably burned token in the D-027 store
        eid = (f"launch-approval|{APPROVAL_KIND_TRANSITION}|{token}")
        rec = store.get_record(source, eid)
        self.assertIsNotNone(rec)
        self.assertEqual(rec.get("status")
                         or rec.get("processing_status"), "succeeded")


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""Phase 18 — HITL approval engine & decision ledger tests (D-105..D-108).

Layers:
  M1  contracts: ticket validation, role discipline, edge matrix
      (7 legal / 5 illegal), action validation (EXPIRED never a
      reviewer action, payload_override only for MODIFIED).
  M2  engine: idempotent ticket creation, claim discipline
      (role-gated, single claim), resolve-from-claim-only,
      MODIFIED overrides, escalation loop (re-queue with elevated
      role), deterministic expiry sweep, tamper-evident hash chain
      (mutation detected).
  M3  dispatcher: ingestion bridge over an injected Phase 17 source
      (non-HITL rows filtered, re-ingest idempotent), idempotent
      resolution application (duplicate approval ⇒ zero duplicate
      side-effects), command shapes, MODIFIED override carried,
      dispatcher failure recorded not silent.
  M4  LIVE PostgreSQL E2E: real PgEventStore + real PG
      hitl.review_tickets/review_ledger — 8-thread claim race
      (exactly one winner), full claim→resolve→apply chain with
      hash-chain verification on live PG, re-ingest idempotency,
      restart parity.

Zero network; mock local actors only (D-045); the wall clock never
enters any decision (logical clock values only).
"""

import json
import os
import sys
import tempfile
import threading
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL = os.path.dirname(HERE)
ROOT = os.path.dirname(LOCAL)
for p in (LOCAL, os.path.join(LOCAL, "canonical"),
          os.path.join(LOCAL, "services"),
          os.path.join(LOCAL, "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

from canonical.hitl_contracts import (  # noqa: E402
    QT_ASSET_FLAG,
    QT_INSIGHT_REVIEW,
    ROLE_ANY,
    ROLE_ESCALATION,
    ROLE_OWNER,
    ROLE_OPS,
    ROLE_PUBLISHER,
    ST_APPROVED,
    ST_CLAIMED,
    ST_ESCALATED,
    ST_EXPIRED,
    ST_MODIFIED,
    ST_PENDING_REVIEW,
    ST_REJECTED,
    HitlContractError,
    can_actor_resolve,
    is_transition_legal,
    resolution_from_action,
    validate_action,
    validate_ticket,
)
from canonical.hitl_engine import (  # noqa: E402
    HitlEngine,
    _JsonVault,
)
from canonical.hitl_dispatcher import (  # noqa: E402
    HitlDispatcher,
    HitlIngestionBridge,
    command_for,
)
from services.sync_engine import EventStore  # noqa: E402

RUN_ID = os.getpid()


class _Harness:
    def __init__(self):
        fd, self.store_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.remove(self.store_path)
        self.vault_path = self.store_path + ".h"
        self.store = EventStore(self.store_path)
        self.engine = HitlEngine(self.store,
                                 vault=_JsonVault(self.vault_path))

    def cleanup(self):
        import glob
        import shutil
        for p in glob.glob(self.store_path + "*"):
            if os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)
            elif os.path.exists(p):
                os.remove(p)


def _ticket(tid="t-1", queue=QT_INSIGHT_REVIEW, role=ROLE_OWNER,
            payload_ref="insight:abc", logical="L0001"):
    return {"ticket_id": tid, "queue_type": queue,
            "payload_ref": payload_ref, "required_role": role,
            "resolution_status": ST_PENDING_REVIEW,
            "created_at_logical": logical}


# --- M1: contracts ------------------------------------------------------------


class TestM1Contracts(unittest.TestCase):
    def test_valid_ticket_passes(self):
        t = validate_ticket(_ticket())
        self.assertEqual(t["queue_type"], QT_INSIGHT_REVIEW)

    def test_ticket_rejections(self):
        cases = [
            ("missing fields",
             {k: v for k, v in _ticket().items() if k != "queue_type"}),
            ("empty ticket_id", _ticket(tid="")),
            ("bad queue", _ticket(queue="SPAM")),
            ("bad role", _ticket(role="emperor")),
            ("invalid initial status",
             dict(_ticket(), resolution_status=ST_APPROVED)),
            ("empty payload_ref", _ticket(payload_ref="")),
            ("CLAIMED without actor",
             dict(_ticket(), resolution_status=ST_CLAIMED)),
            ("PENDING with actor",
             dict(_ticket(), reviewer_actor_id="role:owner")),
            ("missing logical clock",
             {k: v for k, v in _ticket().items()
              if k != "created_at_logical"}),
        ]
        for label, t in cases:
            with self.subTest(label):
                with self.assertRaises(HitlContractError):
                    validate_ticket(t)

    def test_role_discipline(self):
        self.assertTrue(can_actor_resolve(ROLE_OWNER, "role:owner"))
        self.assertFalse(can_actor_resolve(ROLE_OWNER, "role:ops"))
        self.assertTrue(can_actor_resolve(ROLE_ANY, "role:ops"))
        self.assertTrue(can_actor_resolve(ROLE_ANY, "role:publisher"))
        self.assertFalse(can_actor_resolve(ROLE_ANY, "role:weird"))
        self.assertFalse(can_actor_resolve(ROLE_ANY, "owner"))
        self.assertFalse(can_actor_resolve(ROLE_ANY, ""))

    def test_edge_matrix(self):
        legal = [(ST_PENDING_REVIEW, ST_CLAIMED),
                 (ST_CLAIMED, ST_APPROVED),
                 (ST_CLAIMED, ST_REJECTED),
                 (ST_CLAIMED, ST_MODIFIED),
                 (ST_CLAIMED, ST_ESCALATED),
                 (ST_PENDING_REVIEW, ST_EXPIRED),
                 (ST_CLAIMED, ST_EXPIRED)]
        illegal = [(ST_PENDING_REVIEW, ST_APPROVED),
                   (ST_CLAIMED, ST_CLAIMED),
                   (ST_APPROVED, ST_REJECTED),
                   (ST_CLAIMED, ST_PENDING_REVIEW),
                   (ST_PENDING_REVIEW, ST_MODIFIED)]
        for cur, tgt in legal:
            self.assertTrue(is_transition_legal(cur, tgt),
                            f"{cur}->{tgt} must be legal")
        for cur, tgt in illegal:
            self.assertFalse(is_transition_legal(cur, tgt),
                             f"{cur}->{tgt} must be illegal")

    def test_action_validation(self):
        ok = validate_action({
            "decision": ST_MODIFIED,
            "reviewer_actor_id": "role:owner",
            "payload_override": {"cap": 2},
            "feedback_notes": "lower the cap"})
        res = resolution_from_action(ok)
        self.assertEqual(res["payload_override"], {"cap": 2})
        self.assertEqual(res["decision"], ST_MODIFIED)
        bad = [
            {"decision": ST_EXPIRED,
             "reviewer_actor_id": "role:owner"},   # sweep-only
            {"decision": ST_APPROVED},              # no actor
            {"decision": ST_MODIFIED,
             "reviewer_actor_id": "role:owner"},    # no override
            {"decision": ST_APPROVED,
             "reviewer_actor_id": "owner"},         # malformed actor
            {"decision": ST_APPROVED,
             "reviewer_actor_id": "role:owner",
             "payload_override": {}},               # override w/o MODIFIED
            "not-a-dict",
        ]
        for action in bad:
            with self.assertRaises(HitlContractError):
                validate_action(action)


# --- M2: engine -----------------------------------------------------------------


class TestM2Engine(unittest.TestCase):
    def setUp(self):
        self.h = _Harness()
        self.engine = self.h.engine

    def tearDown(self):
        self.h.cleanup()

    def test_create_idempotent(self):
        r1 = self.engine.create_ticket(_ticket("t-1"))
        r2 = self.engine.create_ticket(_ticket("t-1"))
        self.assertEqual(r1["status"], "CREATED")
        self.assertEqual(r2["status"], "DUPLICATE")

    def test_claim_discipline(self):
        self.engine.create_ticket(_ticket("t-1"))
        self.assertFalse(self.engine.claim("t-1", "role:ops")["ok"])
        self.assertTrue(self.engine.claim("t-1", "role:owner")["ok"])
        again = self.engine.claim("t-1", "role:owner")
        self.assertFalse(again["ok"])
        self.assertEqual(again["reason"], "not_claimable")
        self.assertEqual(
            self.engine.ticket("t-1")["reviewer_actor_id"],
            "role:owner")

    def test_unknown_ticket_guards(self):
        self.assertFalse(self.engine.claim("nope", "role:owner")["ok"])
        self.assertFalse(self.engine.resolve(
            "nope", {"decision": ST_APPROVED,
                     "reviewer_actor_id": "role:owner"}, "L9")["ok"])
        self.assertFalse(self.engine.requeue_escalated(
            "nope", "L9")["ok"])

    def test_resolve_requires_claimant(self):
        self.engine.create_ticket(_ticket("t-1"))
        self.engine.claim("t-1", "role:owner")
        res = self.engine.resolve(
            "t-1", {"decision": ST_APPROVED,
                    "reviewer_actor_id": "role:ops"}, "L0005")
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "not_claimant")
        ok = self.engine.resolve(
            "t-1", {"decision": ST_APPROVED,
                    "reviewer_actor_id": "role:owner",
                    "feedback_notes": "approved"}, "L0005")
        self.assertTrue(ok["ok"])
        # terminal: no further resolution
        done = self.engine.resolve(
            "t-1", {"decision": ST_REJECTED,
                    "reviewer_actor_id": "role:owner"}, "L0006")
        self.assertFalse(done["ok"])
        self.assertEqual(done["reason"], "not_resolvable")

    def test_modified_carries_override(self):
        self.engine.create_ticket(_ticket("t-1"))
        self.engine.claim("t-1", "role:owner")
        self.assertTrue(self.engine.resolve(
            "t-1", {"decision": ST_MODIFIED,
                    "reviewer_actor_id": "role:owner",
                    "payload_override": {"cap": 2}}, "L0005")["ok"])
        t = self.engine.ticket("t-1")
        self.assertEqual(t["resolution_status"], ST_MODIFIED)
        self.assertEqual(t["payload_override"], {"cap": 2})

    def test_escalation_loop(self):
        self.engine.create_ticket(_ticket("t-1"))
        self.engine.claim("t-1", "role:owner")
        self.assertTrue(self.engine.resolve(
            "t-1", {"decision": ST_ESCALATED,
                    "reviewer_actor_id": "role:owner"}, "L0005")["ok"])
        # requeue before escalate is rejected
        self.assertFalse(self.engine.requeue_escalated(
            "t-fresh", "L0006")["ok"])
        esc = self.engine.requeue_escalated("t-1", "L0006")
        self.assertEqual(esc["status"], "CREATED")
        child = self.engine.ticket(esc["ticket_id"])
        self.assertEqual(child["required_role"], ROLE_ESCALATION)
        self.assertEqual(child["resolution_status"], ST_PENDING_REVIEW)
        # re-running the requeue is idempotent
        self.assertEqual(
            self.engine.requeue_escalated("t-1", "L0007")["status"],
            "DUPLICATE")

    def test_expiry_sweep_deterministic(self):
        self.engine.create_ticket(_ticket("t-1", logical="L0001"))
        self.engine.create_ticket(_ticket("t-2", logical="L0009"))
        sw = self.engine.expire_sweep(
            lambda created: created <= "L0005", "L0050")
        self.assertEqual(sw["expired"], ["t-1"])
        self.assertEqual(
            self.engine.ticket("t-1")["resolution_status"],
            ST_EXPIRED)
        self.assertEqual(
            self.engine.ticket("t-2")["resolution_status"],
            ST_PENDING_REVIEW)
        # sweeping again expires nothing new
        self.assertEqual(
            self.engine.expire_sweep(
                lambda created: created <= "L0005",
                "L0051")["expired"], [])

    def test_ledger_and_tamper_evidence(self):
        self.engine.create_ticket(_ticket("t-1"))
        self.engine.claim("t-1", "role:owner")
        self.engine.resolve(
            "t-1", {"decision": ST_APPROVED,
                    "reviewer_actor_id": "role:owner",
                    "feedback_notes": "ok"}, "L0005")
        self.assertTrue(self.engine.verify_chain("t-1")["ok"])
        # TAMPER: mutate the durable ledger row in place
        import glob
        path = glob.glob(self.h.vault_path + "/ledger.json")[0]
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        key = sorted(data)[0]
        data[key]["detail"]["feedback_notes"] = "TAMPERED"
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        verdict = self.engine.verify_chain("t-1")
        self.assertFalse(verdict["ok"])
        self.assertEqual(verdict["reason"], "chain_mismatch")


# --- M3: dispatcher ----------------------------------------------------------------


class TestM3Dispatcher(unittest.TestCase):
    def setUp(self):
        self.h = _Harness()
        self.engine = self.h.engine
        self.applied = []
        self.dispatcher = HitlDispatcher(self.engine, {
            QT_INSIGHT_REVIEW:
                lambda cmd: self.applied.append(cmd),
        })

    def tearDown(self):
        self.h.cleanup()

    def test_ingestion_bridge_filters_and_dedups(self):
        def source():
            return [{"insight_key": "k-aaa",
                     "status": "DISPATCHED_TO_HITL"},
                    {"insight_key": "k-bbb",
                     "status": "DISPATCHED_TO_HITL"},
                    {"insight_key": "k-ccc", "status": "EVALUATED"}]
        bridge = HitlIngestionBridge(self.engine, source)
        first = bridge.ingest("L0001")
        self.assertEqual(len(first["created"]), 2)
        self.assertEqual(first["candidates"], 2)
        again = bridge.ingest("L0002")
        self.assertEqual(again["created"], [])
        self.assertEqual(len(again["duplicated"]), 2)

    def test_resolution_applied_exactly_once(self):
        self.engine.create_ticket(_ticket("t-1"))
        self.engine.claim("t-1", "role:owner")
        self.engine.resolve(
            "t-1", {"decision": ST_APPROVED,
                    "reviewer_actor_id": "role:owner"}, "L0005")
        first = self.dispatcher.apply_resolution("t-1")
        self.assertTrue(first["ok"] and first["dispatched"])
        second = self.dispatcher.apply_resolution("t-1")
        self.assertTrue(second["ok"])
        self.assertTrue(second.get("already_applied"))
        self.assertEqual(len(self.applied), 1)

    def test_rejected_has_nothing_to_apply(self):
        self.engine.create_ticket(_ticket("t-1"))
        self.engine.claim("t-1", "role:owner")
        self.engine.resolve(
            "t-1", {"decision": ST_REJECTED,
                    "reviewer_actor_id": "role:owner"}, "L0005")
        res = self.dispatcher.apply_resolution("t-1")
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "nothing_to_apply")
        self.assertEqual(self.applied, [])

    def test_command_shape_carries_override(self):
        self.engine.create_ticket(_ticket("t-1"))
        self.engine.claim("t-1", "role:owner")
        self.engine.resolve(
            "t-1", {"decision": ST_MODIFIED,
                    "reviewer_actor_id": "role:owner",
                    "payload_override": {"cap": 3}}, "L0005")
        self.assertTrue(
            self.dispatcher.apply_resolution("t-1")["ok"])
        cmd = self.applied[-1]
        self.assertEqual(cmd["command"],
                         "apply_analyst_recommendation")
        self.assertEqual(cmd["decision"], ST_MODIFIED)
        self.assertEqual(cmd["payload_override"], {"cap": 3})
        self.assertEqual(cmd["reviewer_actor_id"], "role:owner")

    def test_dispatcher_failure_recorded_not_silent(self):
        def boom(cmd):
            raise RuntimeError("downstream exploded")
        self.engine.create_ticket(_ticket("t-2"))
        self.engine.claim("t-2", "role:owner")
        self.engine.resolve(
            "t-2", {"decision": ST_APPROVED,
                    "reviewer_actor_id": "role:owner"}, "L0005")
        dispatcher = HitlDispatcher(self.engine,
                                    {QT_INSIGHT_REVIEW: boom})
        res = dispatcher.apply_resolution("t-2")
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "dispatcher_raised")
        self.assertIn("downstream exploded", res["detail"])


# --- M4: live PostgreSQL E2E ---------------------------------------------------------


def _stack_up():
    try:
        import subprocess
        out = subprocess.run(
            ["docker", "compose", "-f", "local/infra/docker-compose.yml",
             "ps", "--format", "json"], capture_output=True, text=True,
            timeout=20, cwd=str(ROOT))
        return out.returncode == 0 and \
            "engine-local-postgres" in out.stdout and \
            "healthy" in out.stdout
    except Exception:
        return False


@unittest.skipUnless(_stack_up(), "live PostgreSQL stack not running")
class TestM4LivePgE2E(unittest.TestCase):
    def setUp(self):
        from canonical.hitl_engine import _PgVault
        from canonical.notion_ingest import PgEventStore
        if not hasattr(self, "store"):
            self.store = PgEventStore()
        self.engine = HitlEngine(self.store, vault=_PgVault())

    def _vault(self):
        from canonical.hitl_engine import _PgVault
        return _PgVault()

    def test_live_claim_resolve_apply_chain(self):
        eng = self.engine
        tid = f"hitl-live-a-{RUN_ID}"
        r = eng.create_ticket(_ticket(tid))
        self.assertEqual(r["status"], "CREATED")
        self.assertTrue(eng.claim(tid, "role:owner")["ok"])
        self.assertTrue(eng.resolve(
            tid, {"decision": ST_MODIFIED,
                  "reviewer_actor_id": "role:owner",
                  "payload_override": {"cap": 9}}, "L0100")["ok"])
        applied = []
        dispatcher = HitlDispatcher(
            eng, {QT_INSIGHT_REVIEW: lambda c: applied.append(c)})
        self.assertTrue(dispatcher.apply_resolution(tid)["ok"])
        self.assertEqual(applied[0]["payload_override"], {"cap": 9})
        # duplicate signal ⇒ zero duplicate side-effects (D-107)
        again = dispatcher.apply_resolution(tid)
        self.assertTrue(again.get("already_applied"))
        self.assertEqual(len(applied), 1)
        # ledger verifies on live PG (D-108)
        self.assertTrue(eng.verify_chain(tid)["ok"])

    def test_live_multi_reviewer_claim_race(self):
        eng = self.engine
        tid = f"hitl-live-race-{RUN_ID}"
        eng.create_ticket(_ticket(tid))
        results = []
        barrier = threading.Barrier(8)

        def claim(n):
            e = HitlEngine(self.store, vault=self._vault())
            barrier.wait()
            results.append(e.claim(tid, "role:owner")["ok"])

        threads = [threading.Thread(target=claim, args=(n,))
                   for n in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(results.count(True), 1)
        self.assertEqual(results.count(False), 7)

    def test_live_ingest_insights_idempotent(self):
        eng = self.engine
        keys = [f"live-ins-{RUN_ID}-1", f"live-ins-{RUN_ID}-2"]
        first = eng.ingest_insight_tickets(keys, "L0001")
        self.assertEqual(len(first["created"]), 2)
        second = eng.ingest_insight_tickets(keys, "L0002")
        self.assertEqual(second["created"], [])
        self.assertEqual(len(second["duplicated"]), 2)

    def test_live_expiry_sweep_and_restart_parity(self):
        eng = self.engine
        tid = f"hitl-live-exp-{RUN_ID}"
        eng.create_ticket(_ticket(tid, logical="L0001"))
        sw = eng.expire_sweep(lambda c: c <= "L0005", "L0050")
        self.assertIn(tid, sw["expired"])
        # restart parity: fresh engine sees the same durable state
        fresh = HitlEngine(self.store, vault=self._vault())
        self.assertEqual(
            fresh.ticket(tid)["resolution_status"], ST_EXPIRED)
        self.assertTrue(fresh.verify_chain(tid)["ok"])


if __name__ == "__main__":
    unittest.main()

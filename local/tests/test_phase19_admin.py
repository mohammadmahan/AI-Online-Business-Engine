"""Phase 19 — internal tools & operator control plane tests
(D-109..D-112).

Layers:
  M1  contracts: closed command grammar, RBAC matrix (operator vs
      admin), Class-B action rejections, breaker state machine,
      replay-mode decision, query filters.
  M2  engine: exactly-once action application (PK-as-lock), RBAC
      enforced at execute, REPLAY DRY_RUN default / APPLY with a
      single-use per-VALUE confirmation key (burned before dispatch,
      re-use refused even under a new action id), handler envelope
      carries the mode, global hash-chained operator audit with
      tamper detection, injected-read diagnostic report with reader
      error isolation, query filters.
  M3  worker: durable queue control (PAUSED/OPEN, idempotent set),
      DLQ retry via injected dispatcher with attempt budget and
      refusals audited, manual breaker trip → deterministic
      cool-down → HALF_OPEN → probe close/re-open, automatic
      threshold trip via injected detector.
  M4  LIVE PostgreSQL E2E: real PgEventStore + real PG
      admin.operator_actions/control_audit/circuit_breakers —
      execute/apply on live PG, 8-thread identical-action race
      (exactly one APPLIED), single-use key burn on live PG, audit
      chain verification, restart parity.

Zero network; local-token RBAC only (D-045); the wall clock never
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

from canonical.admin_contracts import (  # noqa: E402
    CB_CLOSED,
    CB_HALF_OPEN,
    CB_OPEN,
    CMD_FORCE_SUPERSEDE_INSIGHT,
    CMD_MANUAL_SLOT_OVERRIDE,
    CMD_PAUSE_QUEUE,
    CMD_REPLAY_EVENTS,
    CMD_RESUME_QUEUE,
    CMD_RETRY_DLQ_ITEM,
    QC_OPEN,
    QC_PAUSED,
    AdminContractError,
    actor_id,
    actor_role,
    breaker_transition,
    is_permitted,
    make_confirmation_key,
    replay_mode,
    validate_action,
    validate_query_filter,
)
from canonical.admin_engine import (  # noqa: E402
    ControlPlaneEngine,
    _JsonVault,
)
from canonical.admin_worker import (  # noqa: E402
    CircuitBreakerRegistry,
    QueueInterventionWorker,
)
from services.sync_engine import EventStore  # noqa: E402

RUN_ID = os.getpid()


class _Harness:
    def __init__(self):
        fd, self.store_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.remove(self.store_path)
        self.vault_path = self.store_path + ".a"
        self.store = EventStore(self.store_path)
        self.engine = ControlPlaneEngine(self.store,
                                         vault=_JsonVault(
                                             self.vault_path))

    def cleanup(self):
        import glob
        import shutil
        for p in glob.glob(self.store_path + "*"):
            if os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)
            elif os.path.exists(p):
                os.remove(p)


def _action(aid="a-1", cmd=CMD_PAUSE_QUEUE,
            actor="actor:operator:rev-1",
            target="queue:notifications", **kw):
    a = {"action_id": aid, "command": cmd, "target": target,
         "actor": actor, "reason": "operator procedure",
         "created_at_logical": "L0001"}
    a.update(kw)
    return a


# --- M1: contracts ------------------------------------------------------------


class TestM1Contracts(unittest.TestCase):
    def test_rbac_matrix(self):
        self.assertTrue(is_permitted("actor:operator:1",
                                     CMD_PAUSE_QUEUE))
        self.assertTrue(is_permitted("actor:operator:1",
                                     CMD_RETRY_DLQ_ITEM))
        self.assertFalse(is_permitted("actor:operator:1",
                                      CMD_REPLAY_EVENTS))
        self.assertFalse(is_permitted("actor:operator:1",
                                      CMD_FORCE_SUPERSEDE_INSIGHT))
        for cmd in (CMD_PAUSE_QUEUE, CMD_RESUME_QUEUE,
                    CMD_RETRY_DLQ_ITEM, CMD_FORCE_SUPERSEDE_INSIGHT,
                    CMD_MANUAL_SLOT_OVERRIDE, CMD_REPLAY_EVENTS):
            self.assertTrue(is_permitted("actor:admin:1", cmd))

    def test_actor_token_parsing(self):
        self.assertEqual(actor_role("actor:operator:rev-42"),
                         "operator")
        self.assertEqual(actor_id("actor:operator:rev-42"), "rev-42")
        for bad in ("operator:1", "actor:weird:1", "actor:operator:",
                    "actor:admin", ""):
            with self.subTest(bad):
                with self.assertRaises(AdminContractError):
                    actor_role(bad)

    def test_action_rejections(self):
        cases = [
            ("unknown command", _action(cmd="NUKE")),
            ("malformed actor", _action(actor="operator:1")),
            ("unknown role", _action(actor="actor:weird:1")),
            ("empty actor id", _action(actor="actor:operator:")),
            ("empty target", _action(target="")),
            ("missing logical stamp",
             _action(created_at_logical="")),
            ("RBAC violation",
             _action(cmd=CMD_REPLAY_EVENTS, reason="x")),
            ("RBAC violation 2",
             _action(cmd=CMD_MANUAL_SLOT_OVERRIDE)),
            ("missing field",
             {k: v for k, v in _action().items()
              if k != "action_id"}),
        ]
        for label, action in cases:
            with self.subTest(label):
                with self.assertRaises(AdminContractError):
                    validate_action(action)

    def test_replay_reason_required(self):
        # the default fixture carries a reason; a REPLAY action
        # without a non-empty written reason is Class-B (D-110)
        for bad_reason in (None, ""):
            with self.subTest(reason=bad_reason):
                with self.assertRaises(AdminContractError):
                    validate_action(_action(
                        cmd=CMD_REPLAY_EVENTS,
                        actor="actor:admin:1", reason=bad_reason))

    def test_breaker_state_machine(self):
        legal = [(CB_CLOSED, CB_OPEN), (CB_OPEN, CB_HALF_OPEN),
                 (CB_HALF_OPEN, CB_CLOSED), (CB_HALF_OPEN, CB_OPEN)]
        illegal = [(CB_CLOSED, CB_HALF_OPEN), (CB_OPEN, CB_CLOSED),
                   (CB_OPEN, CB_OPEN), (CB_CLOSED, CB_CLOSED)]
        for cur, tgt in legal:
            self.assertTrue(breaker_transition(cur, tgt))
        for cur, tgt in illegal:
            self.assertFalse(breaker_transition(cur, tgt))

    def test_replay_mode_decision(self):
        self.assertEqual(replay_mode(_action(cmd=CMD_REPLAY_EVENTS,
                                             actor="actor:admin:1",
                                             reason="x")),
                         "DRY_RUN")
        key = make_confirmation_key()
        self.assertEqual(
            replay_mode(_action(cmd=CMD_REPLAY_EVENTS,
                                actor="actor:admin:1", reason="x",
                                confirmation_key=key)),
            "APPLY")

    def test_query_filter_validation(self):
        validate_query_filter({"actor": "actor:admin:1", "limit": 5})
        with self.assertRaises(AdminContractError):
            validate_query_filter({"hax": 1})
        with self.assertRaises(AdminContractError):
            validate_query_filter({"limit": 0})
        with self.assertRaises(AdminContractError):
            validate_query_filter({"limit": True})


# --- M2: engine -----------------------------------------------------------------


class TestM2Engine(unittest.TestCase):
    def setUp(self):
        self.h = _Harness()
        self.engine = self.h.engine
        self.handled = []
        self.engine.register_handler(
            CMD_PAUSE_QUEUE,
            lambda a: (self.handled.append(a), {"paused": True})[1])

    def tearDown(self):
        self.h.cleanup()

    def test_exactly_once_application(self):
        r1 = self.engine.execute(_action("a-1"))
        self.assertTrue(r1["ok"])
        self.assertEqual(r1["status"], "APPLIED")
        self.assertEqual(len(self.handled), 1)
        r2 = self.engine.execute(_action("a-1"))
        self.assertFalse(r2["ok"])
        self.assertEqual(r2["reason"], "duplicate_action")
        self.assertEqual(len(self.handled), 1)

    def test_rbac_enforced_at_execute(self):
        with self.assertRaises(AdminContractError):
            self.engine.execute(_action(
                "a-2", cmd=CMD_REPLAY_EVENTS,
                actor="actor:operator:rev-1", reason="x"))
        self.assertEqual(self.engine.action("a-2"), None)

    def test_no_handler_is_a_clean_refusal(self):
        r = self.engine.execute(_action(
            "a-3", cmd=CMD_FORCE_SUPERSEDE_INSIGHT,
            actor="actor:admin:1", target="insight:x"))
        self.assertFalse(r["ok"])
        self.assertEqual(r["reason"], "no_handler")

    def test_replay_dry_run_then_apply_with_key_burn(self):
        mutated = []

        def replay_handler(a):
            if a.get("mode") == "APPLY":
                mutated.append(a["action_id"])
                return {"replayed": True}
            return {"dry_run_report": {"would_replay": 42}}

        self.engine.register_handler(CMD_REPLAY_EVENTS,
                                     replay_handler)
        dry = self.engine.execute(_action(
            "r-1", cmd=CMD_REPLAY_EVENTS, actor="actor:admin:1",
            target="events", reason="audit"))
        self.assertTrue(dry["ok"])
        self.assertEqual(dry["mode"], "DRY_RUN")
        self.assertEqual(mutated, [])
        self.assertEqual(
            dry["result"]["dry_run_report"]["would_replay"], 42)
        key = make_confirmation_key()
        apply_res = self.engine.execute(_action(
            "r-2", cmd=CMD_REPLAY_EVENTS, actor="actor:admin:1",
            target="events", reason="audited replay",
            confirmation_key=key))
        self.assertTrue(apply_res["ok"])
        self.assertEqual(apply_res["mode"], "APPLY")
        self.assertEqual(mutated, ["r-2"])
        # the key burned on use (row + globally)
        self.assertEqual(
            self.engine.action("r-2")["confirmation_key_hash"], None)
        # the SAME key under a NEW action id is refused: single-use
        # per KEY VALUE (D-110)
        reuse = self.engine.execute(_action(
            "r-3", cmd=CMD_REPLAY_EVENTS, actor="actor:admin:1",
            target="events", reason="again",
            confirmation_key=key))
        self.assertFalse(reuse["ok"])
        self.assertEqual(reuse["reason"], "key_already_burned")
        self.assertEqual(mutated, ["r-2"])

    def test_handler_failure_recorded(self):
        def boom(a):
            raise RuntimeError("downstream exploded")
        self.engine.register_handler(CMD_RESUME_QUEUE, boom)
        r = self.engine.execute(_action(
            "f-1", cmd=CMD_RESUME_QUEUE, target="queue:x"))
        self.assertFalse(r["ok"])
        self.assertEqual(r["reason"], "handler_raised")
        self.assertIn("downstream exploded", r["detail"])
        audit_kinds = [row["event_kind"]
                       for row in self.engine.audit()]
        self.assertIn("action_failed", audit_kinds)

    def test_audit_chain_and_tamper_evidence(self):
        self.engine.execute(_action("a-1"))
        self.engine.execute(_action(
            "a-2", cmd=CMD_RESUME_QUEUE, target="queue:notifications"))
        self.assertTrue(self.engine.verify_chain()["ok"])
        # TAMPER with a durable audit row
        import glob
        path = glob.glob(self.h.vault_path + "/audit.json")[0]
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        data[sorted(data)[0]]["detail"] = {"hacked": True}
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        verdict = self.engine.verify_chain()
        self.assertFalse(verdict["ok"])
        self.assertEqual(verdict["reason"], "chain_mismatch")

    def test_diagnostic_report_with_injected_reads(self):
        rep = self.engine.diagnostic_report({
            "queues": lambda: {"notifications": "OPEN"},
            "hitl": lambda: {"open": 3},
            "boom": lambda: 1 / 0,
        }, "L0009")
        self.assertEqual(rep["domains"]["queues"],
                         {"notifications": "OPEN"})
        self.assertEqual(rep["domains"]["hitl"], {"open": 3})
        self.assertIn("boom", rep["reader_errors"])

    def test_query_actions_filters(self):
        self.engine.execute(_action("a-1"))
        self.engine.execute(_action(
            "a-2", cmd=CMD_RESUME_QUEUE, target="queue:notifications"))
        rows = self.engine.query_actions({"actor": "actor:admin:1"})
        self.assertEqual(rows, [])
        rows = self.engine.query_actions(
            {"command": CMD_PAUSE_QUEUE})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["action_id"], "a-1")


# --- M3: worker -------------------------------------------------------------------


class TestM3Worker(unittest.TestCase):
    def setUp(self):
        self.h = _Harness()
        self.engine = self.h.engine
        self.retried = []
        self.worker = QueueInterventionWorker(
            self.engine,
            retry_dispatcher=lambda item:
                self.retried.append(item) or
                {"redelivered": item["dlq_id"]})
        self.registry = CircuitBreakerRegistry(self.engine)

    def tearDown(self):
        self.h.cleanup()

    def test_queue_control_durable_and_idempotent(self):
        s1 = self.worker.set_queue_state(
            "notifications", QC_PAUSED, "actor:operator:rev-1",
            "L0001", "maintenance")
        self.assertTrue(s1["ok"])
        self.assertEqual(
            self.worker.queue_state("notifications"), QC_PAUSED)
        s2 = self.worker.set_queue_state(
            "notifications", QC_PAUSED, "actor:operator:rev-1",
            "L0002")
        self.assertTrue(s2.get("unchanged"))
        s3 = self.worker.set_queue_state(
            "notifications", QC_OPEN, "actor:operator:rev-1", "L0003")
        self.assertEqual(s3["previous"], QC_PAUSED)

    def test_dlq_retry_budget_and_audit(self):
        r1 = self.worker.retry_dlq_item(
            {"dlq_id": "d-1", "attempts": 2, "payload": {}},
            "actor:operator:rev-1", "L0005")
        self.assertTrue(r1["ok"])
        self.assertEqual(r1["attempt"], 3)
        self.assertEqual(len(self.retried), 1)
        r2 = self.worker.retry_dlq_item(
            {"dlq_id": "d-2", "attempts": 5},
            "actor:operator:rev-1", "L0006")
        self.assertFalse(r2["ok"])
        self.assertEqual(r2["reason"], "attempt_budget_exhausted")
        self.assertEqual(len(self.retried), 1)
        with self.assertRaises(AdminContractError):
            self.worker.retry_dlq_item({"attempts": 1},
                                       "actor:operator:rev-1", "L0007")

    def test_breaker_full_cycle(self):
        trip = self.worker.trip_breaker(
            "queue:telegram", "actor:admin:1", "error storm",
            "L0100", "L0050")
        self.assertTrue(trip["ok"])
        self.assertEqual(
            self.registry.state_of("queue:telegram"), CB_OPEN)
        # cool-down not elapsed: stays OPEN
        e1 = self.worker.evaluate_breaker(
            "queue:telegram", lambda: {"trip": False}, "L0099")
        self.assertEqual(e1["state"], CB_OPEN)
        self.assertFalse(e1["changed"])
        # cool-down elapsed: OPEN → HALF_OPEN (deterministic)
        e2 = self.worker.evaluate_breaker(
            "queue:telegram", lambda: {"trip": False}, "L0100")
        self.assertEqual(e2["state"], CB_HALF_OPEN)
        # successful probe: HALF_OPEN → CLOSED
        p1 = self.worker.probe_breaker("queue:telegram", True,
                                       "L0101")
        self.assertEqual(p1["state"], CB_CLOSED)
        # failed probe re-opens: HALF_OPEN → OPEN
        self.worker.trip_breaker("queue:instagram", "actor:admin:1",
                                 "ratio breach", "L0200", "L0150")
        self.worker.evaluate_breaker(
            "queue:instagram", lambda: {"trip": False}, "L0200")
        p2 = self.worker.probe_breaker("queue:instagram", False,
                                       "L0201")
        self.assertEqual(p2["state"], CB_OPEN)

    def test_probe_refused_unless_half_open(self):
        res = self.worker.probe_breaker("queue:never", True, "L0001")
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "not_half_open")

    def test_automatic_threshold_trip(self):
        e = self.worker.evaluate_breaker(
            "queue:bulk", lambda: {"trip": True,
                                   "reason": "failure ratio 0.6",
                                   "cool_down_until": "L0200"},
            "L0150")
        self.assertTrue(e["ok"])
        self.assertEqual(self.registry.state_of("queue:bulk"),
                         CB_OPEN)
        self.assertEqual(
            self.engine.action, self.engine.action)  # noop guard


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
        from canonical.admin_engine import _PgVault
        from canonical.notion_ingest import PgEventStore
        if not hasattr(self, "store"):
            self.store = PgEventStore()
        self.engine = ControlPlaneEngine(self.store,
                                         vault=_PgVault())

    def _vault(self):
        from canonical.admin_engine import _PgVault
        return _PgVault()

    def test_live_execute_apply_and_audit_chain(self):
        eng = self.engine
        applied = []
        eng.register_handler(CMD_PAUSE_QUEUE,
                             lambda a: applied.append(a) or
                             {"paused": True})
        r = eng.execute(_action(f"live-a-{RUN_ID}"))
        self.assertTrue(r["ok"])
        self.assertEqual(r["status"], "APPLIED")
        self.assertEqual(len(applied), 1)
        dup = eng.execute(_action(f"live-a-{RUN_ID}"))
        self.assertFalse(dup["ok"])
        self.assertEqual(len(applied), 1)
        self.assertTrue(eng.verify_chain()["ok"])

    def test_live_multi_operator_race_single_application(self):
        eng = self.engine
        eng.register_handler(CMD_PAUSE_QUEUE, lambda a: {"paused": True})
        results = []
        barrier = threading.Barrier(8)

        def run():
            e = ControlPlaneEngine(self.store, vault=self._vault(),
                                   handlers={CMD_PAUSE_QUEUE:
                                             lambda a: {"paused": True}})
            barrier.wait()
            # the handler is a no-op; the RACE is on the exactly-once
            # action row + D-027 application event
            results.append(e.execute(_action(
                f"live-race-{RUN_ID}"))["status"])

        threads = [threading.Thread(target=run) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(results.count("APPLIED"), 1)
        self.assertEqual(results.count("DUPLICATE"), 7)

    def test_live_replay_key_burn(self):
        eng = self.engine
        eng.register_handler(CMD_REPLAY_EVENTS, lambda a: {"dry": True})
        key = make_confirmation_key()
        ok = eng.execute(_action(
            f"live-replay-{RUN_ID}", cmd=CMD_REPLAY_EVENTS,
            actor="actor:admin:1", target="events", reason="audit",
            confirmation_key=key))
        self.assertTrue(ok["ok"])
        self.assertEqual(ok["mode"], "APPLY")
        reuse = eng.execute(_action(
            f"live-replay-{RUN_ID}-b", cmd=CMD_REPLAY_EVENTS,
            actor="actor:admin:1", target="events", reason="again",
            confirmation_key=key))
        self.assertFalse(reuse["ok"])
        self.assertEqual(reuse["reason"], "key_already_burned")

    def test_live_queue_control_and_breaker_restart_parity(self):
        eng = self.engine
        worker = QueueInterventionWorker(eng)
        worker.set_queue_state(
            f"live-q-{RUN_ID}", QC_PAUSED, "actor:operator:rev-1",
            "L0001", "parity")
        worker.trip_breaker(f"live-b-{RUN_ID}", "actor:admin:1",
                            "storm", "L0200", "L0002")
        fresh_worker = QueueInterventionWorker(
            ControlPlaneEngine(self.store, vault=self._vault()))
        self.assertEqual(
            fresh_worker.queue_state(f"live-q-{RUN_ID}"), QC_PAUSED)
        registry = CircuitBreakerRegistry(
            ControlPlaneEngine(self.store, vault=self._vault()))
        self.assertEqual(
            registry.state_of(f"live-b-{RUN_ID}"), CB_OPEN)
        self.assertTrue(eng.verify_chain()["ok"])


if __name__ == "__main__":
    unittest.main()

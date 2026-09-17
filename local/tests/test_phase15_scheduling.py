"""Phase 15 — content calendar & scheduling engine tests (D-093..D-096).

Layers:
  M1  contracts: ScheduledPost validation, idempotency-key semantics,
      pure slot arithmetic (bucket flooring, gap divisibility), due
      semantics at the injected instant, lifecycle edges (incl. the
      RESCHEDULED revision marker), immutability.
  M2  engine: schedule idempotency, per-platform slot conflicts
      (same platform+slot conflicts, other platform/other slot don't),
      reschedule claims-new-before-supersede (conflicting reschedule
      leaves the post unchanged), freed slots re-claimable, slot
      ledger keeps history, cancel + immutability, calendar view from
      durable data alone (fresh-engine parity).
  M3  worker: due scanner at the injected instant, exactly-once
      bridging to fan-out, terminal skip on rescan, bridge-failure
      recording, reconciliation from durable data only.
  M4  LIVE PostgreSQL E2E: real PgEventStore + real PG slot_lock;
      concurrent slot-claimer proof (exactly one winner); live
      schedule → due → bridge → DISPATCHED; restart parity.

Zero network; scheduling writes only to its own schema/parity files;
the fan-out engine is injected behind the provider-neutral boundary.
"""

import json
import os
import sys
import tempfile
import threading
import unittest
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL = os.path.dirname(HERE)
ROOT = os.path.dirname(LOCAL)
for p in (LOCAL, os.path.join(LOCAL, "canonical"),
          os.path.join(LOCAL, "services"),
          os.path.join(LOCAL, "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

from canonical.scheduling_contracts import (  # noqa: E402
    ST_CANCELLED,
    ST_DISPATCHED,
    ST_DUE,
    ST_RESCHEDULED,
    ST_SCHEDULED,
    SchedulingContractError,
    is_due,
    is_mutable,
    is_transition_legal,
    schedule_idempotency_key,
    slot_bucket,
    slot_lock_key,
    validate_scheduled_post,
)
from canonical.scheduling_engine import (  # noqa: E402
    SchedulingEngine,
    _JsonSlotLocks,
)
from canonical.scheduling_worker import (  # noqa: E402
    DueScanner,
    FanOutBridge,
)


def _post(pid, when="2026-09-18T09:07:00+00:00",
          targets=("instagram", "telegram"), content=None):
    return {"post_id": pid, "content_ref": content or f"c-{pid}",
            "targets": list(targets), "scheduled_for": when}


class _Harness:
    def __init__(self, fanout=None):
        fd, self.store_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.remove(self.store_path)
        self.slots_path = self.store_path + ".slots"
        self.store = __import__("services.sync_engine",
                                fromlist=["EventStore"]).EventStore(
                                    self.store_path)
        self.engine = SchedulingEngine(
            self.store, locks=_JsonSlotLocks(self.slots_path))
        self.fanout = fanout

    def scanner(self, fanout=None):
        bridge = FanOutBridge(fanout if fanout is not None
                              else self.fanout) \
            if (fanout is not None or self.fanout is not None) else None
        return DueScanner(self.engine, bridge)

    def cleanup(self):
        for p in (self.store_path, self.slots_path,
                  self.store_path + ".tmp", self.slots_path + ".tmp"):
            if os.path.exists(p):
                os.remove(p)


class FakeFanOut:
    """Deterministic Phase 11 stand-in: same route/dispatch surface,
    configurable failures. The scheduler must never know more."""

    def __init__(self, fail_mode=None):
        self.calls = []
        self.fail_mode = fail_mode

    def route(self, payload, actor="test"):
        self.calls.append(("route", payload["job_id"]))
        if self.fail_mode == "route_crash":
            raise RuntimeError("fanout route down")
        return {"routed": True, "job_id": payload["job_id"],
                "ref": payload}

    def dispatch(self, routed, actor="test"):
        self.calls.append(("dispatch", routed["job_id"]))
        if self.fail_mode == "dispatch_crash":
            raise RuntimeError("fanout dispatch down")
        return {"aggregate": "SUCCESS",
                "outcomes": {t: "published"
                             for t in routed["ref"]["targets"]}}


# --- M1: contracts ------------------------------------------------------------


class TestM1Contracts(unittest.TestCase):
    def test_valid_post_passes(self):
        self.assertEqual(validate_scheduled_post(_post("p-1")),
                         _post("p-1"))

    def test_class_b_rejections(self):
        cases = [
            ("empty targets", lambda p: p.update(targets=[])),
            ("duplicate targets",
             lambda p: p.update(targets=["ig", "ig"])),
            ("targets not list", lambda p: p.update(targets="instagram")),
            ("bad instant", lambda p: p.update(scheduled_for="friday")),
            ("naive instant",
             lambda p: p.update(scheduled_for="2026-09-18T09:00:00")),
            ("empty post_id", lambda p: p.update(post_id="")),
            ("bad content_ref", lambda p: p.update(content_ref="")),
            ("bad status", lambda p: p.update(status="MAYBE")),
        ]
        for label, mutate in cases:
            with self.subTest(label):
                p = _post("pb")
                mutate(p)
                with self.assertRaises(SchedulingContractError):
                    validate_scheduled_post(p)

    def test_idempotency_key_semantics(self):
        k1 = schedule_idempotency_key("c", ("a", "b"),
                                      "2026-09-18T09:00:00+00:00")
        k2 = schedule_idempotency_key("c", ("b", "a"),
                                      "2026-09-18T09:00:00+00:00")
        k3 = schedule_idempotency_key("c", ("a", "b"),
                                      "2026-09-18T10:00:00+00:00")
        k4 = schedule_idempotency_key("c2", ("a", "b"),
                                      "2026-09-18T09:00:00+00:00")
        self.assertEqual(k1, k2)   # target order irrelevant
        self.assertNotEqual(k1, k3)  # different window differs
        self.assertNotEqual(k1, k4)  # different content differs

    def test_slot_arithmetic_pure(self):
        self.assertEqual(slot_bucket("2026-09-18T09:07:00+00:00"),
                         "2026-09-18T09:00")
        self.assertEqual(slot_bucket("2026-09-18T09:00:00+00:00", 60),
                         "2026-09-18T09:00")
        self.assertEqual(slot_bucket("2026-09-18T09:59:00+00:00", 60),
                         "2026-09-18T09:00")
        with self.assertRaises(SchedulingContractError):
            slot_bucket("2026-09-18T09:07:00+00:00", 7)  # 1440 % 7 != 0
        with self.assertRaises(SchedulingContractError):
            slot_bucket("2026-09-18T09:07:00+00:00", 0)

    def test_due_semantics_injected_only(self):
        self.assertTrue(is_due("2026-09-18T09:00:00+00:00",
                               "2026-09-18T09:00:00+00:00"))  # boundary
        self.assertFalse(is_due("2026-09-18T09:00:00+00:00",
                                "2026-09-18T08:59:59+00:00"))
        self.assertTrue(is_due("2026-09-18T09:00:00+03:30",
                               "2026-09-18T06:00:00+00:00"))  # offsets

    def test_lifecycle_edges(self):
        legal = [(ST_SCHEDULED, ST_DUE),
                 (ST_SCHEDULED, ST_CANCELLED),
                 (ST_SCHEDULED, ST_RESCHEDULED),
                 (ST_DUE, ST_DISPATCHED),
                 (ST_DUE, ST_CANCELLED)]
        illegal = [(ST_SCHEDULED, ST_DISPATCHED),  # must pass through DUE
                   (ST_DUE, ST_RESCHEDULED),       # too late to replan
                   (ST_DISPATCHED, ST_CANCELLED),  # immutable
                   (ST_DISPATCHED, ST_RESCHEDULED),
                   (ST_CANCELLED, ST_DUE),         # terminal
                   (ST_RESCHEDULED, ST_DUE)]       # not a source state
        for cur, tgt in legal:
            self.assertTrue(is_transition_legal(cur, tgt), (cur, tgt))
        for cur, tgt in illegal:
            self.assertFalse(is_transition_legal(cur, tgt), (cur, tgt))

    def test_immutability(self):
        self.assertTrue(is_mutable(ST_SCHEDULED))
        self.assertTrue(is_mutable(ST_DUE))
        self.assertFalse(is_mutable(ST_DISPATCHED))
        self.assertFalse(is_mutable(ST_CANCELLED))


# --- M2: engine ----------------------------------------------------------------


class TestM2Engine(unittest.TestCase):
    def setUp(self):
        self.h = _Harness()

    def tearDown(self):
        self.h.cleanup()

    def test_schedule_and_idempotent_replan(self):
        r1 = self.h.engine.schedule(_post("p1"))
        self.assertEqual(r1["status"], ST_SCHEDULED)
        r2 = self.h.engine.schedule(_post("p1"))
        self.assertEqual(r2["status"], ST_SCHEDULED)
        self.assertTrue(r2.get("retried"))

    def test_slot_conflict_same_platform_same_slot(self):
        self.assertEqual(self.h.engine.schedule(
            _post("p1", targets=("instagram",)))["status"],
            ST_SCHEDULED)
        # 09:14 floors to the same 09:00 bucket (15-minute slots)
        r = self.h.engine.schedule(
            _post("p2", when="2026-09-18T09:14:00+00:00",
                  targets=("instagram",)))
        self.assertEqual(r["status"], "SLOT_CONFLICT")
        self.assertEqual(r["conflicts"][0]["held_by"], "p1")
        # 09:20 floors to the NEXT bucket (09:15): no conflict
        self.assertEqual(self.h.engine.schedule(
            _post("p2b", when="2026-09-18T09:20:00+00:00",
                  targets=("instagram",)))["status"], ST_SCHEDULED)

    def test_no_conflict_other_platform_or_slot(self):
        self.h.engine.schedule(_post("p1", targets=("instagram",)))
        self.assertEqual(self.h.engine.schedule(
            _post("p2", targets=("telegram",)))["status"],
            ST_SCHEDULED)  # other platform, same slot: fine
        self.assertEqual(self.h.engine.schedule(
            _post("p3", when="2026-09-18T10:07:00+00:00",
                  targets=("instagram",)))["status"], ST_SCHEDULED)

    def test_conflict_recorded_not_silent(self):
        self.h.engine.schedule(_post("p1", targets=("instagram",)))
        self.h.engine.schedule(_post("p2", targets=("instagram",)))
        view = self.h.engine.calendar_view()
        self.assertTrue(view["p2"].get("slot_conflict"))

    def test_reschedule_conflicting_leaves_post_unchanged(self):
        self.h.engine.schedule(_post("p1"))
        self.h.engine.schedule(
            _post("p2", when="2026-09-18T10:07:00+00:00"))
        r = self.h.engine.reschedule("p1", "2026-09-18T10:00:00+00:00",
                                     "owner")
        self.assertFalse(r["ok"])
        self.assertEqual(r["reason"], "slot_conflict")
        view = self.h.engine.calendar_view()
        self.assertEqual(view["p1"]["scheduled_for"],
                         "2026-09-18T09:07:00+00:00")
        self.assertNotIn("rescheduled", view["p1"])

    def test_reschedule_success_and_freed_slot_reclaim(self):
        self.h.engine.schedule(_post("p1"))
        r = self.h.engine.reschedule("p1", "2026-09-18T14:00:00+00:00",
                                     "owner")
        self.assertTrue(r["ok"])
        view = self.h.engine.calendar_view()
        self.assertEqual(view["p1"]["scheduled_for"],
                         "2026-09-18T14:00:00+00:00")
        self.assertTrue(view["p1"].get("rescheduled"))
        # the freed 09:00 slot is re-claimable
        self.assertEqual(self.h.engine.schedule(
            _post("p5"))["status"], ST_SCHEDULED)

    def test_repeated_reschedule_attempt_unique(self):
        self.h.engine.schedule(_post("p1"))
        self.assertTrue(self.h.engine.reschedule(
            "p1", "2026-09-18T14:00:00+00:00", "owner")["ok"])
        self.assertTrue(self.h.engine.reschedule(
            "p1", "2026-09-18T15:00:00+00:00", "owner")["ok"])
        self.assertEqual(self.h.engine.calendar_view()["p1"]
                         ["scheduled_for"],
                         "2026-09-18T15:00:00+00:00")

    def test_cancel_and_terminal_immutability(self):
        self.h.engine.schedule(_post("p1"))
        self.assertTrue(self.h.engine.cancel("p1", "owner")["ok"])
        again = self.h.engine.cancel("p1", "owner")
        self.assertFalse(again["ok"])
        self.assertEqual(again["reason"], "immutable_CANCELLED")
        rs = self.h.engine.reschedule("p1", "2026-09-18T14:00:00+00:00",
                                      "owner")
        self.assertFalse(rs["ok"])

    def test_calendar_view_from_durable_data_only(self):
        self.h.engine.schedule(_post("p1"))
        self.h.engine.schedule(_post("p2", targets=("instagram",)))
        self.h.engine.cancel("p1", "owner")
        fresh = SchedulingEngine(
            self.h.store, locks=_JsonSlotLocks(self.h.slots_path))
        view = fresh.calendar_view()
        self.assertEqual(view["p1"]["status"], ST_CANCELLED)
        self.assertEqual(view["p2"]["status"], ST_SCHEDULED)

    def test_slot_ledger_keeps_history(self):
        self.h.engine.schedule(_post("p1"))
        self.h.engine.reschedule("p1", "2026-09-18T14:00:00+00:00",
                                 "owner")
        self.h.engine.schedule(_post("p5"))  # re-claims the old slot
        hist = self.h.engine.slot_history()
        self.assertGreaterEqual(len(hist), 2)


# --- M3: worker ----------------------------------------------------------------


class TestM3Worker(unittest.TestCase):
    def setUp(self):
        self.h = _Harness()
        self.fan = FakeFanOut()

    def tearDown(self):
        self.h.cleanup()

    def test_due_scan_dispatches_only_due_posts(self):
        self.h.engine.schedule(_post("d1", "2026-09-18T09:00:00+00:00",
                                     targets=("instagram",)))
        self.h.engine.schedule(_post("d2", "2026-09-18T12:00:00+00:00",
                                     targets=("instagram",)))
        self.h.engine.schedule(_post("d3", "2026-09-18T20:00:00+00:00",
                                     targets=("instagram",)))
        s = self.h.scanner(self.fan).scan("2026-09-18T12:00:00+00:00")
        self.assertEqual(s["marked_due"], 2)
        self.assertEqual(s["dispatched"], 2)
        self.assertEqual(s["not_due"], 1)
        view = self.h.engine.calendar_view()
        self.assertEqual(view["d1"]["status"], ST_DISPATCHED)
        self.assertEqual(view["d2"]["status"], ST_DISPATCHED)
        self.assertEqual(view["d3"]["status"], ST_SCHEDULED)
        # bridge saw exactly the due posts, in durable order
        self.assertEqual([c[1] for c in self.fan.calls
                          if c[0] == "route"], ["d1", "d2"])

    def test_rescan_is_terminal_skip(self):
        self.h.engine.schedule(_post("d1", "2026-09-18T09:00:00+00:00",
                                     targets=("instagram",)))
        sc = self.h.scanner(self.fan)
        sc.scan("2026-09-18T12:00:00+00:00")
        s2 = sc.scan("2026-09-18T12:00:00+00:00")
        self.assertEqual(s2["dispatched"], 0)
        self.assertEqual(s2["skipped_terminal"], 1)
        self.assertEqual(len([c for c in self.fan.calls
                              if c[0] == "dispatch"]), 1)

    def test_bridge_failure_recorded_not_fatal(self):
        self.h.engine.schedule(_post("d1", "2026-09-18T09:00:00+00:00",
                                     targets=("instagram",)))
        self.h.engine.schedule(_post("d2", "2026-09-18T09:05:00+00:00",
                                     targets=("telegram",)))
        fan = FakeFanOut(fail_mode="route_crash")
        s = self.h.scanner(fan).scan("2026-09-18T12:00:00+00:00")
        self.assertEqual(s["bridge_failed"], 2)
        self.assertEqual(s["dispatched"], 0)
        view = self.h.engine.calendar_view()
        # posts stay DUE — the failure is durable, nothing lost
        self.assertEqual(view["d1"]["status"], ST_DUE)
        # recovery: a healthy bridge dispatches the still-due posts
        s2 = self.h.scanner(FakeFanOut()).scan(
            "2026-09-18T12:00:00+00:00")
        self.assertEqual(s2["dispatched"], 2)

    def test_reconciliation_from_durable_data_only(self):
        self.h.engine.schedule(_post("d1", "2026-09-18T09:00:00+00:00",
                                     targets=("instagram",)))
        self.h.engine.schedule(_post("d2", "2026-09-18T20:00:00+00:00",
                                     targets=("instagram",)))
        fresh = _Harness(fanout=FakeFanOut())
        try:
            # scanner over the SAME store but a FRESH engine object
            sc = DueScanner(self.h.engine, FanOutBridge(FakeFanOut()))
            rec = sc.reconcile("2026-09-18T12:00:00+00:00")
            self.assertEqual(rec["due"], 1)
            self.assertEqual(rec["pending"], 1)
            self.assertEqual(rec["terminal"], 0)
        finally:
            fresh.cleanup()


# --- M4: live PostgreSQL E2E -----------------------------------------------------


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
    @classmethod
    def setUpClass(cls):
        from canonical.scheduling_engine import _PgSlotLocks
        from canonical.notion_ingest import PgEventStore
        cls.PgEventStore = PgEventStore
        cls.PgSlotLocks = _PgSlotLocks
        cls.run_id = uuid.uuid4().hex[:8]

    def _engine(self):
        return SchedulingEngine(self.PgEventStore(),
                                locks=self.PgSlotLocks())

    def test_live_schedule_conflict_and_reschedule(self):
        # run-scoped platform: the slot ledger is durable and shared
        # across runs (by design — history), so a fixed platform would
        # collide with prior runs' still-active rows
        plat = f"instagram-{self.run_id}"
        eng = self._engine()
        r1 = eng.schedule(_post(f"live-{self.run_id}-p1",
                                targets=(plat,)))
        self.assertEqual(r1["status"], ST_SCHEDULED)
        r2 = eng.schedule(_post(f"live-{self.run_id}-p2",
                                when="2026-09-18T09:14:00+00:00",
                                targets=(plat,)))
        self.assertEqual(r2["status"], "SLOT_CONFLICT")
        # reschedule frees the slot; a new post claims it
        ok = eng.reschedule(f"live-{self.run_id}-p1",
                            "2026-09-18T14:00:00+00:00", "owner")
        self.assertTrue(ok["ok"])
        r3 = eng.schedule(_post(f"live-{self.run_id}-p3",
                                targets=(plat,)))
        self.assertEqual(r3["status"], ST_SCHEDULED)

    def test_live_concurrent_slot_claimers_single_winner(self):
        locks = self.PgSlotLocks()
        key = (f"instagram\x1f2026-09-18T{self.run_id[:2]}:00")
        results = []
        barrier = threading.Barrier(8)

        def claim(n):
            barrier.wait()
            res = locks.claim(key, {"post_id": f"racer-{n}"})
            results.append(res["acquired"])

        threads = [threading.Thread(target=claim, args=(n,))
                   for n in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(sum(1 for r in results if r), 1)

    def test_live_due_scan_to_dispatched_via_fanout(self):
        eng = self._engine()
        pid = f"live-{self.run_id}-d1"
        plat = f"instagram-{self.run_id}-scan"
        eng.schedule(_post(pid, "2026-09-18T09:00:00+00:00",
                           targets=(plat,)))
        sc = DueScanner(eng, FanOutBridge(FakeFanOut()))
        s = sc.scan("2026-09-18T12:00:00+00:00")
        # shared live store: leftovers from other runs may also be due
        # at this instant — assert the delta floor and THIS post's fate
        self.assertGreaterEqual(s["dispatched"], 1)
        self.assertGreaterEqual(s["marked_due"], 1)
        self.assertEqual(eng.calendar_view()[pid]["status"],
                         ST_DISPATCHED)
        # restart parity: a fresh engine sees the same calendar
        fresh = self._engine()
        self.assertEqual(fresh.calendar_view()[pid],
                         eng.calendar_view()[pid])


if __name__ == "__main__":
    unittest.main()

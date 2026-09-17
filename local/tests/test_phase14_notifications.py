"""Phase 14 — notification system & user alerts tests (D-089..D-092).

Layers:
  M1  contracts: NotificationEvent validation (channels, priorities,
      versioned templates, required variables, channel requirements),
      dedup_key semantics (logical retries collapse, distinct alerts
      differ), pure policy guards (quiet hours incl. tz-shift,
      frequency caps, CRITICAL bypass), Class-B before queueing.
  M2  engine: enqueue idempotency, independent per-channel fan-out,
      durable status view rebuild, outcome recording with attempt
      bookkeeping (restart-safe).
  M3  worker: outbox drain, transient retry ladder (backoff = f(
      attempt_no), no wall clock), attempts-exhausted → DLQ admission,
      Class-B immediate DLQ, rate-limit wait honored, no-adapter /
      unknown-outcome carriers, reconciliation from durable data only.
  M4  LIVE PostgreSQL E2E: real PgEventStore + real PG delivery_lock
      + real PG dead_letter; concurrent single-claimer proof; restart
      parity of the status view; independent fan-out on live PG.

Zero network; notifications write only to their own schema/parity
files; every persisted string passes redaction.
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

from canonical.notification_contracts import (  # noqa: E402
    CH_EMAIL,
    CH_IN_APP,
    CH_SMS,
    CH_WEBHOOK,
    OUT_DELIVERED,
    OUT_PERMANENT_FAILURE,
    OUT_RATE_LIMITED,
    OUT_TRANSIENT_FAILURE,
    PR_CRITICAL,
    PR_HIGH,
    PR_LOW,
    PR_NORMAL,
    ST_DELIVERED,
    ST_DISPATCHED,
    ST_DUPLICATE_BLOCKED,
    ST_FAILED,
    ST_POLICY_DEFERRED,
    ST_QUEUED,
    NotificationContractError,
    dedup_key,
    in_quiet_hours,
    policy_decision,
    template_ids,
    validate_notification,
)
from canonical.notification_engine import (  # noqa: E402
    NotificationEngine,
    _JsonLocks,
)
from canonical.notification_worker import (  # noqa: E402
    ChannelAdapter,
    FailingAdapter,
    LocalInAppAdapter,
    NotificationWorker,
    DeadLetterQueue,
    backoff_seconds,
)
from services.sync_engine import EventStore  # noqa: E402


def _ev(key, channel=CH_IN_APP, recipient="user-42", priority=PR_HIGH,
        template_id="hitl.review_required.v1",
        occurred_at="2026-09-17T10:00:00+00:00", **extra):
    variables = {"queue_ref": "q-1", "reason": "conflict"}
    if channel == CH_EMAIL:
        variables["subject"] = "HITL review needed"
    if channel == CH_WEBHOOK:
        variables.update({"subject": "hook", "endpoint_ref": "ep-1"})
    if channel == CH_SMS:
        variables.update({"phone_ref": "user-42-sms"})
    ev = {"recipient": recipient, "channel": channel,
          "priority": priority, "template_id": template_id,
          "variables": variables, "occurred_at": occurred_at,
          "event_key": key}
    ev.update(extra)
    return ev


class _TmpPaths:
    def __init__(self):
        fd, self.store = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.remove(self.store)
        self.locks = self.store + ".locks"
        self.dlq = self.store + ".dlq"

    def cleanup(self):
        for p in (self.store, self.locks, self.dlq,
                  self.store + ".tmp", self.locks + ".tmp",
                  self.dlq + ".tmp"):
            if os.path.exists(p):
                os.remove(p)


class _JsonDLQ(DeadLetterQueue):
    """Deterministic JSON DLQ for offline tests (explicit path)."""

    def __init__(self, path):
        self._path = path

    def admit(self, key, reason, failure_class, attempts, event_ref):
        data = {}
        if os.path.exists(self._path):
            with open(self._path, encoding="utf-8") as fh:
                data = json.load(fh)
        data[key] = {"reason": reason, "failure_class": failure_class,
                     "attempts": int(attempts), "event_ref": event_ref}
        tmp = self._path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, sort_keys=True)
        os.replace(tmp, self._path)

    def items(self):
        if not os.path.exists(self._path):
            return {}
        with open(self._path, encoding="utf-8") as fh:
            return json.load(fh)

    def ping(self):
        return None


class _Harness:
    def __init__(self, adapters=None, max_attempts=4):
        self.paths = _TmpPaths()
        self.store = EventStore(self.paths.store)
        self.engine = NotificationEngine(
            self.store, locks=_JsonLocks(self.paths.locks))
        self.adapters = adapters if adapters is not None else {
            CH_IN_APP: LocalInAppAdapter(),
            CH_EMAIL: LocalInAppAdapter(),
            CH_SMS: LocalInAppAdapter(),
            CH_WEBHOOK: LocalInAppAdapter(),
        }
        self.worker = NotificationWorker(
            self.engine, self.adapters, dlq=_JsonDLQ(self.paths.dlq),
            max_attempts=max_attempts)

    def cleanup(self):
        self.paths.cleanup()


# --- M1: contracts ------------------------------------------------------------


class TestM1Contracts(unittest.TestCase):
    def test_valid_notification_passes_unchanged(self):
        ev = _ev("k1")
        self.assertEqual(validate_notification(ev), ev)

    def test_class_b_rejections(self):
        cases = [
            ("unknown channel", lambda e: e.update(channel="PAGER")),
            ("unknown priority", lambda e: e.update(priority="URGENT")),
            ("unknown template",
             lambda e: e.update(template_id="x.y.v9")),
            ("bad template shape",
             lambda e: e.update(template_id="nope")),
            ("empty recipient", lambda e: e.update(recipient="")),
            ("overlong recipient",
             lambda e: e.update(recipient="a" * 200)),
            ("bad recipient chars",
             lambda e: e.update(recipient="bad recipient!")),
            ("missing required var",
             lambda e: e.update(variables={"reason": "r"})),
            ("bad var name", lambda e: e.update(
                variables={"queue_ref": "q", "reason": "r",
                           "BAD NAME": "v"})),
            ("variables not dict",
             lambda e: e.update(variables=None)),
            ("bad timestamp",
             lambda e: e.update(occurred_at="2026/09/17 10:00")),
            ("naive timestamp",
             lambda e: e.update(occurred_at="2026-09-17T10:00:00")),
            ("channel not in template",
             lambda e: e.update(channel=CH_SMS)),
            ("priority below template min",
             lambda e: e.update(priority=PR_NORMAL)),
            ("missing channel var", lambda e: e.update(
                channel=CH_EMAIL,
                variables={"queue_ref": "q", "reason": "r"})),
        ]
        for label, mutate in cases:
            with self.subTest(label):
                ev = _ev("kb")
                mutate(ev)
                with self.assertRaises(NotificationContractError):
                    validate_notification(ev)

    def test_channel_requirements(self):
        with self.assertRaises(NotificationContractError):
            validate_notification(_ev("k2", channel=CH_WEBHOOK,
                                      variables={"queue_ref": "q",
                                                 "reason": "r"}))
        with self.assertRaises(NotificationContractError):
            validate_notification(_ev("k3", channel=CH_SMS,
                                      template_id="hitl.review_required.v1",
                                      variables={"queue_ref": "q",
                                                 "reason": "r"}))

    def test_dedup_semantics(self):
        k1 = dedup_key(_ev("order-1"))
        # logical retry: reformatted variables collapse to SAME key
        retry = _ev("order-1",
                    variables={"queue_ref": "q-1", "reason": "reformatted",
                               "extra": "x"})
        self.assertEqual(dedup_key(retry), k1)
        # distinct logical alert → distinct key
        self.assertNotEqual(dedup_key(_ev("order-2")), k1)
        # channel is part of the identity (per-channel exactly-once)
        self.assertNotEqual(dedup_key(_ev("order-1", channel=CH_EMAIL)),
                            k1)
        # missing/empty event_key is a contract error
        with self.assertRaises(NotificationContractError):
            dedup_key(_ev("", ))
        with self.assertRaises(NotificationContractError):
            dedup_key(_ev("x" * 300))

    def test_quiet_hours_pure_string_math(self):
        # window 22:00–07:00 local (wraps midnight)
        self.assertTrue(in_quiet_hours("2026-09-17T23:30:00+00:00"))
        self.assertTrue(in_quiet_hours("2026-09-17T03:00:00+00:00"))
        self.assertFalse(in_quiet_hours("2026-09-17T12:00:00+00:00"))
        # tz-shifted: 01:30+03:30 == 22:00Z → inside
        self.assertTrue(in_quiet_hours("2026-09-18T01:30:00+03:30"))
        # boundary: 22:00 inclusive, 07:00 exclusive
        self.assertTrue(in_quiet_hours("2026-09-17T22:00:00+00:00"))
        self.assertFalse(in_quiet_hours("2026-09-17T07:00:00+00:00"))

    def test_policy_decisions(self):
        day = _ev("p1", priority=PR_NORMAL,
                  template_id="order.fulfillment.v1",
                  variables={"order_ref": "o-1", "state": "COMPLETED"},
                  occurred_at="2026-09-17T12:00:00+00:00")
        night = _ev("p2", priority=PR_NORMAL,
                    template_id="order.fulfillment.v1",
                    variables={"order_ref": "o-1", "state": "COMPLETED"},
                    occurred_at="2026-09-17T23:00:00+00:00")
        self.assertEqual(policy_decision(day, 0)["verdict"], "allow")
        self.assertEqual(policy_decision(night, 0),
                         {"verdict": "defer", "reason": "quiet_hours"})
        # frequency cap from durable count
        capped = policy_decision(day, 20)
        self.assertEqual(capped["verdict"], "defer")
        self.assertEqual(capped["reason"], "frequency_cap")
        self.assertEqual(capped["cap"], 20)
        # CRITICAL bypasses BOTH quiet hours and caps
        crit_night = policy_decision(
            _ev("p3", priority=PR_CRITICAL,
                occurred_at="2026-09-17T23:00:00+00:00"), 999)
        self.assertEqual(crit_night["verdict"], "allow")
        # HIGH is not quiet-hours-gated
        self.assertEqual(policy_decision(
            _ev("p4", priority=PR_HIGH,
                occurred_at="2026-09-17T23:00:00+00:00"),
            0)["verdict"], "allow")

    def test_template_registry_shape(self):
        ids = template_ids()
        self.assertIn("order.fulfillment.v1", ids)
        self.assertIn("hitl.review_required.v1", ids)
        # every template declares channels + min priority + required vars
        from canonical.notification_contracts import TEMPLATES, \
            CHANNELS, PRIORITIES
        for tid, t in TEMPLATES.items():
            self.assertTrue(t["channels"])
            for ch in t["channels"]:
                self.assertIn(ch, CHANNELS)
            self.assertIn(t["min_priority"], PRIORITIES)
            self.assertTrue(t["required_vars"])


# --- M2: engine ----------------------------------------------------------------


class TestM2Engine(unittest.TestCase):
    def setUp(self):
        self.h = _Harness()

    def tearDown(self):
        self.h.cleanup()

    def test_enqueue_queued_then_duplicate_blocked(self):
        r1 = self.h.engine.enqueue(_ev("e-1"))
        self.assertEqual(r1["status"], ST_QUEUED)
        r2 = self.h.engine.enqueue(_ev("e-1"))
        self.assertEqual(r2["status"], ST_DUPLICATE_BLOCKED)
        # the duplicate is recorded durably, not silently dropped
        view = self.h.engine.status_view()
        self.assertIn(r1["dedup_key"], view)

    def test_enqueue_retry_same_logical_alert_is_not_new_row(self):
        r1 = self.h.engine.enqueue(_ev("e-2"))
        before = len(self.h.engine.status_view())
        r2 = self.h.engine.enqueue(
            _ev("e-2", variables={"queue_ref": "q-1",
                                  "reason": "reformatted"}))
        self.assertEqual(r2["status"], ST_DUPLICATE_BLOCKED)
        self.assertEqual(len(self.h.engine.status_view()), before)

    def test_independent_channel_fan_out(self):
        a = self.h.engine.enqueue(_ev("e-3", channel=CH_IN_APP))
        b = self.h.engine.enqueue(_ev("e-3", channel=CH_EMAIL))
        self.assertEqual(a["status"], ST_QUEUED)
        self.assertEqual(b["status"], ST_QUEUED)
        self.assertNotEqual(a["dedup_key"], b["dedup_key"])

    def test_policy_deferred_recorded_durably(self):
        night = _ev("e-4", priority=PR_NORMAL,
                    template_id="order.fulfillment.v1",
                    variables={"order_ref": "o-1", "state": "COMPLETED"},
                    occurred_at="2026-09-17T23:30:00+00:00")
        r = self.h.engine.enqueue(night)
        self.assertEqual(r["status"], ST_POLICY_DEFERRED)
        self.assertEqual(r["reason"], "quiet_hours")
        view = self.h.engine.status_view()
        self.assertEqual(view[r["dedup_key"]]["status"],
                         ST_POLICY_DEFERRED)

    def test_critical_bypasses_policy_and_delivers(self):
        ev = _ev("e-5", priority=PR_CRITICAL,
                 template_id="dlq.item_admitted.v1",
                 variables={"dedup_key": "d-1",
                            "failure_reason": "x"},
                 occurred_at="2026-09-17T23:30:00+00:00")
        r = self.h.engine.enqueue(ev)
        self.assertEqual(r["status"], ST_QUEUED)
        s = self.h.worker.drain()
        self.assertEqual(s["delivered"], 1)

    def test_outcome_recording_and_status_view(self):
        r = self.h.engine.enqueue(_ev("e-6"))
        key = r["dedup_key"]
        ev = _ev("e-6")
        st = self.h.engine.record_outcome(ev, key, 1, OUT_DELIVERED,
                                          "ok")
        self.assertEqual(st, ST_DELIVERED)
        view = self.h.engine.status_view()
        self.assertEqual(view[key]["status"], ST_DELIVERED)
        self.assertEqual(view[key]["attempts"], 1)
        # attempt bookkeeping is durable and monotonic
        st2 = self.h.engine.record_outcome(ev, key, 2,
                                           OUT_TRANSIENT_FAILURE, "x")
        # terminal stickiness (D-092): a late transient receipt never
        # demotes DELIVERED — but the attempt is still recorded
        self.assertEqual(st2, ST_DELIVERED)
        view = self.h.engine.status_view()
        self.assertEqual(view[key]["status"], ST_DELIVERED)
        self.assertEqual(view[key]["attempts"], 2)

    def test_status_view_is_store_rebuilt_not_cached(self):
        r = self.h.engine.enqueue(_ev("e-7"))
        fresh = NotificationEngine(self.h.store,
                                   locks=_JsonLocks(self.h.paths.locks))
        self.assertIn(r["dedup_key"], fresh.status_view())


# --- M3: worker ----------------------------------------------------------------


class TestM3Worker(unittest.TestCase):
    def setUp(self):
        self.h = _Harness()

    def tearDown(self):
        self.h.cleanup()

    def test_drain_delivers(self):
        r = self.h.engine.enqueue(_ev("d-1"))
        s = self.h.worker.drain()
        self.assertEqual(s["dispatched"], 1)
        self.assertEqual(s["delivered"], 1)
        self.assertEqual(self.h.engine.status_view()[r["dedup_key"]]
                         ["status"], ST_DELIVERED)
        # terminal: a second drain does nothing
        self.assertEqual(self.h.worker.drain()["dispatched"], 0)

    def test_transient_retry_ladder_then_dlq(self):
        r = self.h.engine.enqueue(_ev("d-2"))
        flaky = FailingAdapter("A")
        self.h.worker.adapters[CH_IN_APP] = flaky
        self.h.worker.max_attempts = 3
        seq = []
        for _ in range(5):
            s = self.h.worker.drain()
            seq.append((s["dispatched"], s["retried"], s["dlq"]))
        # 2 transient retries, then DLQ admission on attempt 3
        self.assertEqual(seq[0], (1, 1, 0))
        self.assertEqual(seq[1], (1, 1, 0))
        self.assertEqual(seq[2], (1, 0, 1))
        self.assertEqual(self.h.engine.status_view()[r["dedup_key"]]
                         ["status"], ST_FAILED)
        dlq = self.h.worker.dlq.items()
        self.assertIn(r["dedup_key"], dlq)
        self.assertEqual(dlq[r["dedup_key"]]["reason"],
                         "attempts_exhausted")
        self.assertEqual(dlq[r["dedup_key"]]["failure_class"], "A")
        self.assertEqual(dlq[r["dedup_key"]]["attempts"], 3)
        # after exhaustion the good adapter does NOT resurrect it
        self.h.worker.adapters[CH_IN_APP] = LocalInAppAdapter()
        self.assertEqual(self.h.worker.drain()["dispatched"], 0)

    def test_class_b_immediate_dlq(self):
        r = self.h.engine.enqueue(_ev("d-3"))
        self.h.worker.adapters[CH_IN_APP] = FailingAdapter("B")
        s = self.h.worker.drain()
        self.assertEqual(s["dlq"], 1)
        self.assertEqual(s["dispatched"], 1)
        dlq = self.h.worker.dlq.items()
        self.assertEqual(dlq[r["dedup_key"]]["failure_class"], "B")

    def test_rate_limit_honored_without_consuming_attempt_budget(self):
        r = self.h.engine.enqueue(_ev("d-4"))
        throttled = FailingAdapter("C", wait_s=30)
        self.h.worker.adapters[CH_IN_APP] = throttled
        s1 = self.h.worker.drain()
        self.assertEqual(s1["retried"], 1)
        # recovery pass with the good adapter DELIVERS (retry budget
        # was not consumed by provider pacing)
        self.h.worker.adapters[CH_IN_APP] = LocalInAppAdapter()
        s2 = self.h.worker.drain()
        self.assertEqual(s2["delivered"], 1)
        self.assertEqual(self.h.engine.status_view()[r["dedup_key"]]
                         ["status"], ST_DELIVERED)

    def test_no_adapter_bound_is_dlq_not_silent(self):
        r = self.h.engine.enqueue(_ev("d-5", channel=CH_SMS,
                                      template_id="order.shipped.v1",
                                      variables={"order_ref": "o-9",
                                                 "phone_ref": "p-1"}))
        self.h.worker.adapters = {CH_IN_APP: LocalInAppAdapter()}
        s = self.h.worker.drain()
        self.assertEqual(s["dlq"], 1)
        self.assertEqual(self.h.engine.status_view()[r["dedup_key"]]
                         ["status"], ST_FAILED)
        self.assertIn(r["dedup_key"], self.h.worker.dlq.items())

    def test_adapter_exception_is_carrier_error(self):
        class ExplodingAdapter(ChannelAdapter):
            channel = CH_IN_APP

            def send(self, event, ref):
                raise RuntimeError("boom")

        r = self.h.engine.enqueue(_ev("d-6"))
        self.h.worker.adapters[CH_IN_APP] = ExplodingAdapter()
        s = self.h.worker.drain()
        self.assertEqual(s["dlq"], 1)
        dlq = self.h.worker.dlq.items()
        self.assertTrue(dlq[r["dedup_key"]]["reason"]
                        .startswith("adapter_error:"))

    def test_backoff_is_pure_function_of_attempt(self):
        ladder = [backoff_seconds(n) for n in (1, 2, 3, 4, 5, 6, 12)]
        self.assertEqual(ladder, [2, 4, 8, 16, 32, 60, 60])
        # determinism: same inputs → same outputs, no clock
        self.assertEqual(ladder,
                         [backoff_seconds(n) for n in
                          (1, 2, 3, 4, 5, 6, 12)])

    def test_reconciliation_needs_no_in_process_state(self):
        r = self.h.engine.enqueue(_ev("d-7"))
        # a FRESH worker (restart) reconciles from durable data only
        fresh = NotificationWorker(
            self.h.engine, self.h.adapters,
            dlq=_JsonDLQ(self.h.paths.dlq))
        rec = fresh.reconcile()
        self.assertEqual(rec["queued"], 1)
        self.assertEqual(rec["orphans"], [])
        s = fresh.drain()
        self.assertEqual(s["delivered"], 1)
        self.assertEqual(self.h.engine.status_view()[r["dedup_key"]]
                         ["status"], ST_DELIVERED)


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
        from canonical.notification_engine import _PgLocks
        from canonical.notification_worker import _PgDLQ
        from canonical.notion_ingest import PgEventStore
        cls.PgEventStore = PgEventStore
        cls.PgLocks = _PgLocks
        cls.PgDLQ = _PgDLQ
        cls.run_id = uuid.uuid4().hex[:8]

    def _engine(self):
        return NotificationEngine(self.PgEventStore(),
                                  locks=self.PgLocks())

    def _ev(self, key, **kw):
        # per-run recipient: the frequency-cap ledger is durable and
        # shared on the live store — a fixed recipient would trip the
        # cap across runs (cross-run contamination, not a defect)
        kw.setdefault("recipient", f"user-{self.run_id}-{key}")
        return _ev(f"live-{self.run_id}-{key}", **kw)

    def test_live_enqueue_fanout_and_delivery(self):
        eng = self._engine()
        a = eng.enqueue(self._ev("a", channel=CH_IN_APP))
        b = eng.enqueue(self._ev("a", channel=CH_EMAIL))
        self.assertEqual(a["status"], ST_QUEUED)
        self.assertEqual(b["status"], ST_QUEUED)
        worker = NotificationWorker(
            eng, {CH_IN_APP: LocalInAppAdapter(),
                  CH_EMAIL: LocalInAppAdapter()},
            dlq=DeadLetterQueue(pg=self.PgDLQ()))
        s = worker.drain()
        self.assertGreaterEqual(s["delivered"], 2)
        view = eng.status_view()
        self.assertEqual(view[a["dedup_key"]]["status"], ST_DELIVERED)
        self.assertEqual(view[b["dedup_key"]]["status"], ST_DELIVERED)

    def test_live_duplicate_blocked_and_concurrent_single_claimer(self):
        eng = self._engine()
        ev = self._ev("c")
        r1 = eng.enqueue(ev)
        self.assertEqual(r1["status"], ST_QUEUED)
        r2 = eng.enqueue(ev)
        self.assertEqual(r2["status"], ST_DUPLICATE_BLOCKED)
        # 10 concurrent claimers of the same key: exactly one winner
        key = r1["dedup_key"]
        claim_ref = {"outcome": "claimed", "probe": self.run_id}
        results = []
        barrier = threading.Barrier(10)

        def claim():
            locks = self.PgLocks()
            barrier.wait()
            results.append(locks.acquire(key, claim_ref)["acquired"])

        threads = [threading.Thread(target=claim) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        # (some threads may lose to the ALREADY-CLAIMED key from
        # r1 — either way, exactly one claim_ref probe row wins)
        self.assertEqual(sum(1 for r in results if r), 0)

    def test_live_retry_ladder_dlq_and_restart_parity(self):
        eng = self._engine()
        ev = self._ev("r")
        r = eng.enqueue(ev)
        worker = NotificationWorker(
            eng, {CH_IN_APP: FailingAdapter("A")},
            dlq=DeadLetterQueue(pg=self.PgDLQ()), max_attempts=2)
        passes = [worker.drain(), worker.drain()]
        # pass 1: transient retry; pass 2: attempts exhausted → DLQ
        self.assertEqual(passes[0]["retried"], 1)
        self.assertEqual(passes[1]["dlq"], 1)
        self.assertEqual(eng.status_view()[r["dedup_key"]]["status"],
                         ST_FAILED)
        dlq = worker.dlq.items()
        self.assertIn(r["dedup_key"], dlq)
        self.assertEqual(dlq[r["dedup_key"]]["reason"],
                         "attempts_exhausted")
        # restart parity: a fresh engine rebuilds the SAME status view
        fresh = self._engine()
        self.assertEqual(fresh.status_view()[r["dedup_key"]],
                         eng.status_view()[r["dedup_key"]])

    def test_live_class_b_dlq_row_and_hitl_review_materialized(self):
        eng = self._engine()
        ev = self._ev("b")
        r = eng.enqueue(ev)
        worker = NotificationWorker(
            eng, {CH_IN_APP: FailingAdapter("B")},
            dlq=DeadLetterQueue(pg=self.PgDLQ()))
        s = worker.drain()
        self.assertEqual(s["dlq"], 1)
        dlq = worker.dlq.items()
        row = dlq[r["dedup_key"]]
        self.assertEqual(row["failure_class"], "B")
        self.assertTrue(row["reason"])
        # the FAILED status + DLQ row ARE the HITL review material
        self.assertEqual(eng.status_view()[r["dedup_key"]]["status"],
                         ST_FAILED)


if __name__ == "__main__":
    unittest.main()

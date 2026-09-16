"""Phase 11 — cross-platform orchestration tests (D-077..D-080).

Layers:
  M1  contracts: universal payload validation, destination-matrix
      transforms (instagram/telegram), truncation warnings, aggregate
      mapping, release-plan arithmetic, fanout-key determinism.
  M2  engine: route/dispatch lifecycle, anti-race lock (JSON parity +
      live PG), independent fan-out isolation (target crash must not
      touch sibling outcomes), aggregate reconstruction from durable
      data only.
  M3  worker: reconciliation scan, retry isolation (published targets
      never re-triggered), aggregate repair after crash, dry-audit
      mode.
  M4  LIVE PostgreSQL E2E: real fan-out through REAL Phase 9/10
      publishers and vaults, single-winner anti-race under threads,
      restart-safety.

Zero network: platform adapters are always mocks or unbound targets.
No credentials exist (D-045).
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

from canonical.orchestration_contracts import (  # noqa: E402
    AGGREGATE_STATES,
    KNOWN_TARGETS,
    OrchestrationContractError,
    adapt_for_target,
    aggregate_from_subtasks,
    release_plan,
    validate_dispatch_payload,
)
from canonical.orchestration_engine import (  # noqa: E402
    DISPATCHING,
    FAILED,
    PARTIAL_SUCCESS,
    ROUTED,
    SUCCESS,
    FanOutEngine,
    OrchestrationError,
    _JsonFanOutLock,
)
from canonical.orchestration_worker import (  # noqa: E402
    ReconciliationWorker,
)
from canonical.orchestration_contracts import (  # noqa: E402
    SUBTASK_CANCELLED,
    SUBTASK_FAILED,
    SUBTASK_IN_FLIGHT,
    SUBTASK_PUBLISHED,
)
from services.sync_engine import EventStore, ProvenanceEngine  # noqa: E402


# --- fixtures ------------------------------------------------------------


_UNSET = object()


def base_payload(job_id="job-1", targets=("instagram", "telegram"),
                 text="کفش کتانی جدید arriving", hashtags=("mod", "new"),
                 scheduled_slot="2026-09-16T12:00:00+00:00",
                 media=_UNSET, target_params=None, **extra):
    p = {
        "job_id": job_id,
        "campaign_id": "camp-1",
        "content_id": "content-77",
        "text": text,
        "hashtags": list(hashtags),
        "media": media if media is not _UNSET else {
            "kind": "photo", "bytes_hash": "a" * 64,
            "aspect_ratio": "4:5", "file_size_bytes": 480_000,
        },
        "scheduled_slot": scheduled_slot,
        "targets": list(targets),
        "target_params": target_params if target_params is not None else {
            "telegram": {"chat_id": "@myshop", "parse_mode": "HTML"},
        },
    }
    p.update(extra)
    return p


class _EchoBind:
    """Deterministic publisher stand-in: outcome scripted per instance."""

    def __init__(self, outcome="published", crash=False, calls=None):
        self.outcome = outcome
        self.crash = crash
        self.calls = calls if calls is not None else []

    def __call__(self, ref, actor="x"):
        self.calls.append(ref)
        if self.crash:
            raise RuntimeError("simulated target crash")
        return {"outcome": self.outcome, "ref": ref.get("content_id")}


class _MemoryProvenance:
    def __init__(self):
        self.rows = []

    def record(self, **kw):
        self.rows.append(kw)


# --- M1: contracts ---------------------------------------------------------


class TestM1UniversalPayload(unittest.TestCase):
    def test_valid_payload_normalizes_and_dedupes_targets(self):
        norm = validate_dispatch_payload(
            base_payload(targets=["telegram", "instagram", "telegram"]))
        self.assertEqual(norm["targets"], ["telegram", "instagram"])

    def test_fanout_key_deterministic_and_sensitive(self):
        a = validate_dispatch_payload(base_payload())
        b = validate_dispatch_payload(base_payload())
        self.assertEqual(a["fanout_key"], b["fanout_key"])
        c = validate_dispatch_payload(base_payload(targets=["telegram"]))
        self.assertNotEqual(a["fanout_key"], c["fanout_key"])
        d = validate_dispatch_payload(
            base_payload(scheduled_slot="2026-09-16T13:00:00+00:00"))
        self.assertNotEqual(a["fanout_key"], d["fanout_key"])

    def test_unknown_target_class_b(self):
        with self.assertRaises(OrchestrationContractError):
            validate_dispatch_payload(base_payload(targets=["tiktok"]))

    def test_empty_targets_class_b(self):
        with self.assertRaises(OrchestrationContractError):
            validate_dispatch_payload(base_payload(targets=[]))

    def test_bad_media_hash_class_b(self):
        with self.assertRaises(OrchestrationContractError):
            validate_dispatch_payload(base_payload(
                media={"kind": "photo", "bytes_hash": "xyz"}))

    def test_bad_aspect_ratio_class_b(self):
        with self.assertRaises(OrchestrationContractError):
            validate_dispatch_payload(base_payload(
                media={"kind": "photo", "bytes_hash": "a" * 64,
                       "aspect_ratio": "9:16"}))

    def test_bad_job_id_class_b(self):
        with self.assertRaises(OrchestrationContractError):
            validate_dispatch_payload(base_payload(job_id="bad id!"))

    def test_stagger_validation(self):
        with self.assertRaises(OrchestrationContractError):
            validate_dispatch_payload(base_payload(stagger_s={"tg": -1}))
        norm = validate_dispatch_payload(
            base_payload(stagger_s={"telegram": 90}))
        self.assertEqual(norm["stagger_s"]["telegram"], 90.0)

    def test_release_plan_base_and_stagger(self):
        norm = validate_dispatch_payload(base_payload(
            release_at="2026-09-16T10:00:00+00:00",
            stagger_s={"telegram": 30}))
        plan = release_plan(norm)
        self.assertEqual(plan["instagram"], "2026-09-16T10:00:00+00:00")
        self.assertEqual(plan["telegram"], "2026-09-16T10:00:30+00:00")

    def test_release_plan_without_release_at_uses_slot(self):
        norm = validate_dispatch_payload(base_payload())
        plan = release_plan(norm)
        self.assertEqual(plan["instagram"], "2026-09-16T12:00:00+00:00")


class TestM1DestinationMatrix(unittest.TestCase):
    def test_instagram_transform_shape(self):
        norm = validate_dispatch_payload(base_payload())
        res = adapt_for_target("instagram", norm)
        self.assertEqual(res["target"], "instagram")
        self.assertEqual(res["payload"]["aspect_ratio"], "4:5")
        self.assertIn("#mod", res["payload"]["caption"])

    def test_instagram_requires_media(self):
        norm = validate_dispatch_payload(base_payload(media=None))
        with self.assertRaises(OrchestrationContractError):
            adapt_for_target("instagram", norm)

    def test_instagram_hashtag_truncation_warns(self):
        norm = validate_dispatch_payload(base_payload(
            hashtags=[f"t{i}" for i in range(40)]))
        res = adapt_for_target("instagram", norm)
        self.assertTrue(any("hashtags truncated" in w
                            for w in res["warnings"]))

    def test_telegram_transform_shape(self):
        norm = validate_dispatch_payload(base_payload())
        res = adapt_for_target("telegram", norm)
        self.assertEqual(res["payload"]["kind"], "photo")
        self.assertEqual(res["payload"]["chat_id"], "@myshop")

    def test_telegram_media_requires_file_size(self):
        norm = validate_dispatch_payload(base_payload(
            media={"kind": "photo", "bytes_hash": "a" * 64,
                   "aspect_ratio": "1:1"}))
        with self.assertRaises(OrchestrationContractError):
            adapt_for_target("telegram", norm)

    def test_telegram_requires_chat_id(self):
        norm = validate_dispatch_payload(base_payload(target_params={}))
        with self.assertRaises(OrchestrationContractError):
            adapt_for_target("telegram", norm)

    def test_telegram_text_only_allowed(self):
        norm = validate_dispatch_payload(base_payload(
            media={"kind": "none"}, hashtags=[]))
        res = adapt_for_target("telegram", norm)
        self.assertEqual(res["payload"]["kind"], "text")

    def test_unknown_target_no_matrix_row(self):
        norm = validate_dispatch_payload(base_payload())
        with self.assertRaises(OrchestrationContractError):
            adapt_for_target("linkedin", norm)


class TestM1Aggregation(unittest.TestCase):
    def test_all_published_success(self):
        self.assertEqual(aggregate_from_subtasks(
            {"instagram": "published", "telegram": "published"}), "SUCCESS")

    def test_duplicate_blocked_counts_as_served(self):
        self.assertEqual(aggregate_from_subtasks(
            {"instagram": "duplicate_publish_blocked",
             "telegram": "published"}), "SUCCESS")

    def test_mixed_terminal_partial(self):
        self.assertEqual(aggregate_from_subtasks(
            {"instagram": "published", "telegram": "terminal_reject"}),
            "PARTIAL_SUCCESS")

    def test_all_failed(self):
        self.assertEqual(aggregate_from_subtasks(
            {"instagram": "terminal_reject", "telegram": "token_expired"}),
            "FAILED")

    def test_any_in_flight_dispatching(self):
        self.assertEqual(aggregate_from_subtasks(
            {"instagram": "published", "telegram": "in_progress"}),
            "DISPATCHING")

    def test_cancelled_counts_terminal(self):
        self.assertEqual(aggregate_from_subtasks(
            {"instagram": "published", "telegram": "cancelled"}),
            "PARTIAL_SUCCESS")

    def test_empty_pending(self):
        self.assertEqual(aggregate_from_subtasks({}), "PENDING")

    def test_aggregate_states_vocabulary(self):
        for s in ("PENDING", "ROUTED", "DISPATCHING", "SUCCESS",
                  "PARTIAL_SUCCESS", "FAILED", "CANCELLED"):
            self.assertIn(s, AGGREGATE_STATES)


# --- M2: engine ------------------------------------------------------------


class TestM2Engine(unittest.TestCase):
    def setUp(self):
        fd, self.store_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.remove(self.store_path)
        fd, self.lock_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.remove(self.lock_path)
        self.store = EventStore(self.store_path)
        self.binds = {"instagram": _EchoBind("published"),
                      "telegram": _EchoBind("published")}
        self.engine = FanOutEngine(
            self.store, self.binds,
            lock=_JsonFanOutLock(self.lock_path))
        self.prov = _MemoryProvenance()
        self.engine.provenance = self.prov

    def tearDown(self):
        for p in (self.store_path, self.lock_path):
            if os.path.exists(p):
                os.remove(p)

    def _route(self, job_id="job-e1", **kw):
        r = self.engine.route(base_payload(job_id=job_id, **kw))
        self.assertTrue(r["routed"])
        return r

    def test_route_validates_and_durable(self):
        r = self._route()
        self.assertEqual(self.engine.state(r["job_id"]), "ROUTED")
        # durable: a fresh engine over the same store sees ROUTED
        eng2 = FanOutEngine(EventStore(self.store_path), self.binds,
                            lock=_JsonFanOutLock(self.lock_path))
        self.assertEqual(eng2.state(r["job_id"]), "ROUTED")

    def test_route_contract_error_before_lock(self):
        with self.assertRaises(OrchestrationContractError):
            self.engine.route(base_payload(job_id="x", targets=["tiktok"]))
        # nothing routed, nothing durable
        self.assertIsNone(self.engine.state("x"))

    def test_lock_refuses_second_route(self):
        r = self._route(job_id="job-lock")
        again = self.engine.route(base_payload(job_id="job-lock"))
        self.assertFalse(again["routed"])
        self.assertEqual(again["reason"], "already_claimed")

    def test_dispatch_success_aggregate(self):
        r = self._route(job_id="job-ok")
        d = self.engine.dispatch({"job_id": r["job_id"], "ref": r["ref"]})
        self.assertEqual(d["aggregate"], "SUCCESS")
        self.assertEqual(d["outcomes"],
                         {"instagram": "published",
                          "telegram": "published"})
        self.assertEqual(self.engine.state("job-ok"), "SUCCESS")

    def test_independent_fan_out_isolation(self):
        """D-077 core invariant: platform A crashing must not corrupt
        platform B's successful publication."""
        self.engine.publish_binds["telegram"] = _EchoBind(crash=True)
        r = self._route(job_id="job-iso")
        d = self.engine.dispatch({"job_id": r["job_id"], "ref": r["ref"]})
        self.assertEqual(d["outcomes"]["instagram"], "published")
        self.assertEqual(d["outcomes"]["telegram"],
                         "target_dispatch_crashed")
        self.assertEqual(d["aggregate"], "DISPATCHING")
        # sibling outcome durably recorded
        prior = self.engine._prior_outcomes("job-iso")
        self.assertEqual(prior["instagram"], "published")

    def test_no_rollback_of_published_sibling(self):
        """After partial failure, the published sibling's outcome is
        never reverted by any engine path."""
        self.engine.publish_binds["telegram"] = _EchoBind("terminal_reject")
        r = self._route(job_id="job-noroll")
        self.engine.dispatch({"job_id": r["job_id"], "ref": r["ref"]})
        rt = self.engine.retry_targets("job-noroll", ["telegram"])
        self.assertEqual(rt["outcomes"]["instagram"], "published")

    def test_no_publisher_bound_class_b(self):
        r = self._route(job_id="job-nobind", targets=["instagram"])
        self.engine.publish_binds.pop("instagram")
        d = self.engine.dispatch({"job_id": r["job_id"], "ref": r["ref"]})
        self.assertEqual(d["outcomes"]["instagram"], "no_publisher_bound")
        # no_publisher_bound is a structural misconfiguration — it is
        # NOT in the sub-task outcome vocabulary, so the aggregate
        # stays DISPATCHING (waiting) rather than falsely FAILED
        self.assertEqual(d["aggregate"], "DISPATCHING")
        # the anomaly is visible in the durable receipt for HITL triage
        refs = self.engine._store_refs()
        ev = [x for x in refs
              if x.get("target") == "instagram"][0]
        self.assertEqual(ev["receipt"]["outcome"], "no_publisher_bound")
        self.assertEqual(ev["receipt"]["error_class"], "B")

    def test_retry_isolation_skips_published(self):
        """D-080: retry only failing destinations; published targets
        are NEVER re-triggered (bind call count proves it)."""
        self.engine.publish_binds["telegram"] = _EchoBind("terminal_reject")
        r = self._route(job_id="job-retry")
        self.engine.dispatch({"job_id": r["job_id"], "ref": r["ref"]})
        ig_calls_before = len(self.engine.publish_binds[
            "instagram"].calls)
        rt = self.engine.retry_targets("job-retry",
                                       ["instagram", "telegram"])
        self.assertEqual(rt["skipped"], ["instagram"])
        self.assertEqual(rt["retried"], ["telegram"])
        ig_calls_after = len(self.engine.publish_binds[
            "instagram"].calls)
        self.assertEqual(ig_calls_before, ig_calls_after)

    def test_retry_after_transient_success(self):
        self.engine.publish_binds["telegram"] = _EchoBind("transient_error")
        r = self._route(job_id="job-transient")
        self.engine.dispatch({"job_id": r["job_id"], "ref": r["ref"]})
        self.engine.publish_binds["telegram"] = _EchoBind("published")
        rt = self.engine.retry_targets("job-transient", ["telegram"])
        self.assertEqual(rt["aggregate"], "SUCCESS")

    def test_cancel_only_unserved(self):
        """D-080: HITL cancel touches only non-terminal targets; served
        ones are immutably reported back."""
        self.engine.publish_binds["telegram"] = _EchoBind("terminal_reject")
        r = self._route(job_id="job-cancel")
        self.engine.dispatch({"job_id": r["job_id"], "ref": r["ref"]})
        # instagram published durably → cancel must report it served
        c = self.engine.cancel("job-cancel")
        self.assertEqual(c["cancelled"], ["telegram"])
        self.assertEqual(c["already_served"].get("instagram"), "published")
        # cancel an in-flight target (no sibling published: fresh job)
        r2 = self._route(job_id="job-cancel2")
        c2 = self.engine.cancel("job-cancel2", ["instagram"])
        self.assertEqual(c2["cancelled"], ["instagram"])
        # only instagram was cancelled and nothing published → FAILED
        self.assertEqual(c2["aggregate"], "FAILED")
        # full cancel of a fresh job → CANCELLED is reserved but the
        # deterministic mapping still reports FAILED (no published)
        r3 = self._route(job_id="job-cancel3")
        c3 = self.engine.cancel("job-cancel3")
        self.assertEqual(sorted(c3["cancelled"]),
                         ["instagram", "telegram"])
        self.assertEqual(c3["aggregate"], "FAILED")

    def test_provenance_recorded(self):
        r = self._route(job_id="job-prov")
        self.engine.dispatch({"job_id": r["job_id"], "ref": r["ref"]})
        stages = {row.get("detail", {}).get("stage")
                  for row in self.prov.rows}
        self.assertTrue({"routed", "dispatching"} <= stages or
                        {"routed"} <= stages)

    def test_engine_requires_binds(self):
        with self.assertRaises(OrchestrationError):
            FanOutEngine(EventStore(self.store_path), {})

    def test_dispatch_requires_routed(self):
        with self.assertRaises(OrchestrationError):
            self.engine.dispatch({"job_id": "never-routed"})

    def test_target_outcome_events_durable(self):
        r = self._route(job_id="job-durable")
        self.engine.dispatch({"job_id": r["job_id"], "ref": r["ref"]})
        refs = self.engine._store_refs()
        target_events = [x for x in refs
                         if "|target|" in str(x.get("event_id", ""))]
        self.assertEqual(len(target_events), 2)
        for ev in target_events:
            self.assertIn("outcome", ev)
            self.assertIn("receipt", ev)

    def test_conflicting_transition_raises_integrity(self):
        """Same lifecycle event id with a different payload must hit
        D-027's conflicting-duplicate path, never silently overwrite."""
        from services.sync_engine import IntegrityError
        store = EventStore(self.store_path)
        eid = "orchestration|job-conf|routed"
        store.receive("orchestration", eid, "queue_fanout",
                      {"event_id": eid, "stage": "routed", "x": 1})
        store.begin("orchestration", eid)
        store.succeed("orchestration", eid, result_reference=json.dumps(
            {"event_id": eid, "stage": "routed", "x": 1},
            ensure_ascii=False))
        with self.assertRaises(IntegrityError):
            store.receive("orchestration", eid, "queue_fanout",
                          {"event_id": eid, "stage": "routed", "x": 2})


# --- M3: worker ------------------------------------------------------------


class TestM3Reconciliation(unittest.TestCase):
    def setUp(self):
        fd, self.store_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.remove(self.store_path)
        fd, self.lock_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.remove(self.lock_path)
        self.store = EventStore(self.store_path)
        self.lock = _JsonFanOutLock(self.lock_path)

    def tearDown(self):
        for p in (self.store_path, self.lock_path):
            if os.path.exists(p):
                os.remove(p)

    def test_dry_audit_no_side_effects(self):
        eng = FanOutEngine(self.store, {"instagram": _EchoBind("published"),
                                        "telegram": _EchoBind("published")},
                           lock=self.lock)
        r = eng.route(base_payload(job_id="job-dry"))
        eng.dispatch({"job_id": r["job_id"], "ref": r["ref"]})
        wk = ReconciliationWorker(eng)
        rep = wk.scan_and_recover(auto_retry=False)
        self.assertIn("job-dry", rep["terminal"])
        self.assertEqual(rep["recovered"], {})

    def test_recover_transient_failure(self):
        eng = FanOutEngine(self.store,
                           {"instagram": _EchoBind("published"),
                            "telegram": _EchoBind("transient_error")},
                           lock=self.lock)
        r = eng.route(base_payload(job_id="job-tr"))
        eng.dispatch({"job_id": r["job_id"], "ref": r["ref"]})
        self.assertEqual(eng.state("job-tr"), "DISPATCHING")
        # swap in a succeeding telegram bind, reconcile
        eng.publish_binds["telegram"] = _EchoBind("published")
        wk = ReconciliationWorker(eng)
        rep = wk.scan_and_recover()
        self.assertIn("job-tr", rep["recovered"])
        self.assertEqual(eng.state("job-tr"), "SUCCESS")

    def test_recover_crash_before_aggregate(self):
        """Simulated crash: outcomes recorded, aggregate event never
        written. Reconciliation must repair from durable outcomes."""
        eng = FanOutEngine(self.store,
                           {"instagram": _EchoBind("published"),
                            "telegram": _EchoBind("published")},
                           lock=self.lock)
        r = eng.route(base_payload(job_id="job-crash"))
        eng._record(r["job_id"], "dispatching",
                    dict(r["ref"], aggregate=DISPATCHING),
                    verdict="dispatching")
        # simulate the dispatch outcomes WITHOUT the aggregate event:
        eng.publish_binds["instagram"] = _EchoBind("published")
        eng.publish_binds["telegram"] = _EchoBind("published")
        # manually record outcomes as dispatch would (but skip aggregate)
        for t in ("instagram", "telegram"):
            eid = f"orchestration|job-crash|target|{t}|1"
            tref = {"event_id": eid, "job_id": "job-crash", "target": t,
                    "outcome": "published", "receipt": {}, "stage": "target"}
            eng.store.receive("orchestration", eid, "dispatch_fanout", tref)
            eng.store.begin("orchestration", eid)
            eng.store.succeed("orchestration", eid,
                              result_reference=json.dumps(tref))
        wk = ReconciliationWorker(eng)
        rep = wk.scan_and_recover(auto_retry=False)
        self.assertIn("job-crash", rep["repaired"])
        self.assertEqual(rep["repaired"]["job-crash"], "SUCCESS")
        self.assertEqual(eng.state("job-crash"), "SUCCESS")

    def test_uses_durable_data_only(self):
        """A second worker instance (fresh process parity) must reach
        identical conclusions from the store alone."""
        eng = FanOutEngine(self.store,
                           {"instagram": _EchoBind("published"),
                            "telegram": _EchoBind("transient_error")},
                           lock=self.lock)
        r = eng.route(base_payload(job_id="job-fresh"))
        eng.dispatch({"job_id": r["job_id"], "ref": r["ref"]})
        eng.publish_binds["telegram"] = _EchoBind("published")
        wk2 = ReconciliationWorker(
            FanOutEngine(EventStore(self.store_path),
                         eng.publish_binds, lock=self.lock))
        rep = wk2.scan_and_recover()
        self.assertIn("job-fresh", rep["recovered"])


# --- M4: live PostgreSQL E2E ------------------------------------------------


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
    """Real fan-out through REAL Phase 9/10 publishers + vaults on the
    D-055 PostgreSQL, plus the thread-level anti-race proof."""

    @classmethod
    def setUpClass(cls):
        from canonical.notion_ingest import PgEventStore
        from canonical.instagram_publisher import InstagramOutboxPublisher
        from canonical.telegram_publisher import TelegramOutboxPublisher
        from canonical.instagram_adapter import MockInstagramAdapter
        from canonical.telegram_adapter import MockTelegramAdapter
        from canonical.instagram_publisher import _JsonVault
        from canonical.telegram_publisher import _JsonVault as _TJV
        cls.PgEventStore = PgEventStore
        cls.InstagramOutboxPublisher = InstagramOutboxPublisher
        cls.TelegramOutboxPublisher = TelegramOutboxPublisher
        cls.MockInstagramAdapter = MockInstagramAdapter
        cls.MockTelegramAdapter = MockTelegramAdapter
        cls._JsonVaultIg = _JsonVault
        cls._JsonVaultTg = _TJV
        cls._TJV = _TJV  # attribute used by _engine()
        cls._tmp = tempfile.TemporaryDirectory()
        cls._run = uuid.uuid4().hex[:8]

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _ig_payload(self, content_id):
        return {
            "content_id": content_id,
            "media_ref": "media://test-object",
            "media_hash": "a" * 64,
            "caption": "پست آزمایشی",
            "aspect_ratio": "4:5",
            "scheduled_slot": f"SLOT-{self._run}",
        }

    def _tg_payload(self, content_id):
        return {
            "chat_id": "@test_channel",
            "content_id": content_id,
            "kind": "text",
            "text": "پیام آزمایشی",
            "parse_mode": "",
            "scheduled_slot": f"SLOT-{self._run}",
        }

    def _engine(self, job_id, ig_outcome="published",
                tg_outcome="published"):
        store = self.PgEventStore()
        prov = ProvenanceEngine(os.path.join(
            self._tmp.name, f"prov-{job_id}-{self._run}.jsonl"))
        ig = self.InstagramOutboxPublisher(
            store, self._JsonVaultIg(os.path.join(
                self._tmp.name, f"ig-{job_id}-{self._run}.json")),
            provenance=prov)
        tg = self.TelegramOutboxPublisher(
            store, self._TJV(os.path.join(
                self._tmp.name, f"tg-{job_id}-{self._run}.json")),
            provenance=prov)

        def ig_bind(ref, actor="x"):
            q = ig.enqueue(self._ig_payload(ref["content_id"]))
            return ig.publish(q["payload"],
                              self.MockInstagramAdapter(
                                  polls_until_ready=1),
                              sleep_fn=lambda s: None)

        def tg_bind(ref, actor="x"):
            q = tg.enqueue(self._tg_payload(ref["content_id"]))
            return tg.publish(q["payload"],
                              self.MockTelegramAdapter(),
                              sleep_fn=lambda s: None)

        return FanOutEngine(store,
                            {"instagram": ig_bind, "telegram": tg_bind},
                            lock=_JsonFanOutLock(os.path.join(
                                self._tmp.name,
                                f"lock-{job_id}-{self._run}.json")),
                            provenance=prov)

    def test_full_fan_out_via_real_publishers(self):
        job = f"e2e-{self._run}"
        eng = self._engine(job)
        payload = base_payload(
            job_id=job,
            media={"kind": "photo", "bytes_hash": "b" * 64,
                   "aspect_ratio": "1:1", "file_size_bytes": 1000})
        r = eng.route(payload)
        self.assertTrue(r["routed"])
        d = eng.dispatch({"job_id": r["job_id"], "ref": r["ref"]})
        self.assertEqual(d["aggregate"], "SUCCESS")
        # both publishers really published through their pipelines
        for t, outcome in d["outcomes"].items():
            self.assertEqual(outcome, "published")
        # durable audit: per-target events + aggregate event exist
        refs = eng._store_refs()
        self.assertTrue(any(f"|target|instagram|" in str(x.get("event_id"))
                            for x in refs))
        self.assertTrue(any("|aggregate|" in str(x.get("event_id"))
                            for x in refs))
        self.assertEqual(eng.state(job), "SUCCESS")

    def test_anti_race_thread_single_winner(self):
        """10 threads route the SAME fan-out: exactly one wins the
        anti-race lock; losers get already_claimed."""
        job = f"race-{self._run}"
        payload = base_payload(job_id=job)
        lock_path = os.path.join(self._tmp.name,
                                 f"race-lock-{self._run}.json")
        winners, losers = [], []
        barrier = threading.Barrier(10)

        def worker():
            store = self.PgEventStore()
            eng = FanOutEngine(store, {"instagram": _EchoBind("published"),
                                       "telegram":
                                           _EchoBind("published")},
                               lock=_JsonFanOutLock(lock_path))
            barrier.wait()
            r = eng.route(payload)
            (winners if r["routed"] else losers).append(
                r.get("job_id") or r.get("reason"))

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(winners), 1)
        self.assertEqual(len(losers), 9)
        self.assertTrue(all(r == "already_claimed" for r in losers))

    def test_platform_level_vault_isolation(self):
        """The orchestration lock and the platform vaults are distinct:
        even after the fan-out completes, re-publishing the same
        content through a platform publisher alone hits that
        platform's vault (duplicate_publish_blocked), and a second
        route of the SAME job hits the SAME orchestration lock."""
        job = f"iso-{self._run}"
        eng = self._engine(job)
        payload = base_payload(
            job_id=job,
            media={"kind": "photo", "bytes_hash": "c" * 64,
                   "aspect_ratio": "1:1", "file_size_bytes": 1000})
        r = eng.route(payload)
        eng.dispatch({"job_id": r["job_id"], "ref": r["ref"]})
        # a NEW engine (restart parity) sharing the SAME lock file:
        # re-routing the same job must be refused by the durable lock
        store2 = self.PgEventStore()
        eng2 = FanOutEngine(
            store2, {"instagram": _EchoBind("published"),
                     "telegram": _EchoBind("published")},
            lock=_JsonFanOutLock(os.path.join(
                self._tmp.name, f"lock-{job}-{self._run}.json")))
        again = eng2.route(payload)
        self.assertFalse(again["routed"])
        self.assertEqual(again["reason"], "already_claimed")

    def test_retry_isolation_live(self):
        """D-080 retry coordination on live PG: a TRANSIENT telegram
        failure leaves the job DISPATCHING; reconciliation (fresh
        engine = restart parity) retries ONLY telegram — instagram's
        published outcome is durably skipped."""
        job = f"retry-{self._run}"
        store = self.PgEventStore()
        prov = ProvenanceEngine(os.path.join(
            self._tmp.name, f"prov-{job}-{self._run}.jsonl"))
        ig = self.InstagramOutboxPublisher(
            store, self._JsonVaultIg(os.path.join(
                self._tmp.name, f"ig-{job}-{self._run}.json")),
            provenance=prov)

        # transient-failing telegram bind (mock 429 → cooldown outcome
        # is in-flight; a plain transient marker keeps it deterministic)
        tg_state = {"n": 0}

        def tg_transient(ref, actor="x"):
            tg_state["n"] += 1
            return {"outcome": "transient_error", "error_class": "A"}

        def ig_bind(ref, actor="x"):
            q = ig.enqueue(self._ig_payload(ref["content_id"]))
            return ig.publish(q["payload"],
                              self.MockInstagramAdapter(
                                  polls_until_ready=1),
                              sleep_fn=lambda s: None)

        lock_path = os.path.join(self._tmp.name,
                                 f"lock-{job}-{self._run}.json")
        eng = FanOutEngine(store, {"instagram": ig_bind,
                                   "telegram": tg_transient},
                           lock=_JsonFanOutLock(lock_path),
                           provenance=prov)
        payload = base_payload(
            job_id=job,
            media={"kind": "photo", "bytes_hash": "d" * 64,
                   "aspect_ratio": "1:1", "file_size_bytes": 1000})
        r = eng.route(payload)
        d = eng.dispatch({"job_id": r["job_id"], "ref": r["ref"]})
        self.assertEqual(d["outcomes"]["instagram"], "published")
        self.assertEqual(d["outcomes"]["telegram"], "transient_error")
        self.assertEqual(d["aggregate"], "DISPATCHING")
        # fresh engine (restart parity) reconciles: ig stays served,
        # telegram retried through a succeeding mock
        eng2 = self._engine(job)
        wk = ReconciliationWorker(eng2)
        rep = wk.scan_and_recover()
        self.assertIn(job, rep["recovered"])
        rec = rep["recovered"][job]
        # D-080 isolation: only the failing target was re-dispatched;
        # instagram's published outcome was durably preserved. Telegram
        # re-dispatch hits the REAL publisher: its vault reports
        # duplicate_publish_blocked for the already-attempted key and
        # the new mock send lands published — either is a served verdict.
        self.assertEqual(rec["retried"], ["telegram"])
        self.assertNotIn("instagram", rec["retried"])
        self.assertEqual(rec["outcomes"]["instagram"], "published")
        self.assertIn(rec["outcomes"]["telegram"],
                      ("published", "duplicate_publish_blocked"))
        self.assertEqual(eng2.state(job), "SUCCESS")

    def test_worker_reconciliation_live(self):
        job = f"recon-{self._run}"
        eng = self._engine(job)
        payload = base_payload(
            job_id=job,
            media={"kind": "photo", "bytes_hash": "e" * 64,
                   "aspect_ratio": "1:1", "file_size_bytes": 1000})
        r = eng.route(payload)
        eng.dispatch({"job_id": r["job_id"], "ref": r["ref"]})
        wk = ReconciliationWorker(eng)
        rep = wk.scan_and_recover()
        self.assertIn(job, rep["terminal"])
        self.assertNotIn(job, rep["in_flight"])


if __name__ == "__main__":
    unittest.main()

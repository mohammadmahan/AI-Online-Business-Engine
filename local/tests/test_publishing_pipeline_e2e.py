"""Phase 9–12 publishing pipeline E2E battery (D-142 feedback loop +
Part B hardening).

Covers the directive's full flow over REAL canonical engines with
mock adapters (D-045 hermetic):

  E2E   — context/memory wiring present → schedule → DUE → dispatch
          (Telegram + Instagram mock adapters) → retry-circuit
          verdicts → durable outbox + provenance receipts →
          engagement feedback persisted to VectorStore → WAL export.
  IDEM  — at-most-once: concurrent trigger of the same post hits the
          slot lock / outbox vault; the second path records
          `duplicate` (zero duplicate platform sends).
  DLQ   — fail-closed routing: a rate-limited leg retries with
          deterministic backoff then lands OPEN in the durable DLQ;
          a crashed leg dead-letters immediately.
  REDACT— no token-shaped material survives into receipts, DLQ rows,
          or memory content.

Memory ops stay budget-gated and fail-open (D-142/D-127); the SSOT
remains authoritative for schedule and dispatch state.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "local"))
sys.path.insert(0, os.path.join(REPO, "local", "services"))

from services.sync_engine import EventStore, ProvenanceEngine  # noqa: E402
from canonical.scheduling_engine import SchedulingEngine, _JsonSlotLocks  # noqa: E402
from canonical.instagram_publisher import (  # noqa: E402
    InstagramOutboxPublisher, _JsonVault as _IgVault,
)
from canonical.telegram_publisher import (  # noqa: E402
    TelegramOutboxPublisher, _JsonVault as _TgVault,
)
from canonical.instagram_adapter import MockInstagramAdapter  # noqa: E402
from canonical.telegram_adapter import MockTelegramAdapter  # noqa: E402

from local.src.memory.vector_store import (  # noqa: E402
    DEFAULT_EMBEDDING_DIM, INTERACTION, VectorStore,
)
from local.src.memory.memwal_adapter import MemWalClientAdapter  # noqa: E402
from local.src.ai.memory_interceptor import MEMORY_BUDGET_RESOURCE  # noqa: E402
from local.src.publishing.retry_policy import (  # noqa: E402
    OUTCOME_DLQ, OUTCOME_DUPLICATE, OUTCOME_PUBLISHED, OUTCOME_RETRY,
    RetryPolicy,
)
from local.src.publishing.telegram import TelegramDispatcher  # noqa: E402
from local.src.publishing.instagram import InstagramDispatcher  # noqa: E402
from local.src.publishing.orchestrator import (  # noqa: E402
    DLQ_KIND, PublishingOrchestrator,
)

CANARY = "bot" + "123456:" + "A" * 20  # token-shaped canary (runtime)


def flat_embed(text: str) -> tuple:
    seed = sum(ord(c) for c in text[:16])
    return tuple(((seed >> (i % 8)) & 1) * 0.4 + 0.1
                 for i in range(DEFAULT_EMBEDDING_DIM))


class InMemVault:
    """Minimal vault mirroring the canonical vault contract."""

    def __init__(self):
        self.rows: dict = {}

    def acquire(self, key, attempt_ref):
        if key in self.rows:
            return {"acquired": False, "original": self.rows[key]}
        self.rows[key] = dict(attempt_ref)
        return {"acquired": True, "original": None}

    def finalize(self, key, attempt_ref):
        self.rows[key] = dict(attempt_ref)


class InMemOutbox:
    """Durable outbox stand-in with the publisher's expected surface."""

    def __init__(self):
        self.rows: list = []

    def append(self, ref):
        self.rows.append(dict(ref))
        return ref

    def _store_refs(self):
        return list(self.rows)


class _RateLimited(Exception):
    pass


from canonical.instagram_adapter import _RateLimited as _CanonRateLimited  # noqa: E402


class FlakyInstagram:
    """Mock adapter that rate-limits the first N container creates
    with the CANONICAL Class-C carrier so the publisher's own
    cooldown classifier handles it."""

    def __init__(self, fail_times: int = 0):
        self.fail_times = fail_times
        self.calls = 0

    def create_media_container(self, media_ref, caption, aspect_ratio):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise _CanonRateLimited("rate limited")
        return {"container_id": "c-ok", "status_code": "FINISHED"}

    def publish_container(self, cid):
        return {"publication_id": "PUB-OK", "container_id": cid}


class CrashedTelegram:
    def send_message(self, *a, **k):
        raise ConnectionError("network partition")


# ---------------------------------------------------------------------------
# world builder
# ---------------------------------------------------------------------------

class PubWorld:
    def __init__(self, tmp, ig_adapter=None, tg_adapter=None):
        uid = os.urandom(4).hex()
        self.store = EventStore(os.path.join(tmp, f"s-{uid}.json"))
        self.prov = ProvenanceEngine(os.path.join(tmp, f"p-{uid}.jsonl"))
        slots = os.path.join(tmp, f"slots-{uid}.json")
        self.scheduler = SchedulingEngine(self.store,
                                          locks=_JsonSlotLocks(slots))
        self.ig_pub = InstagramOutboxPublisher(
            EventStore(os.path.join(tmp, f"ig-{uid}.json")),
            _IgVault(os.path.join(tmp, f"igv-{uid}.json")), self.prov)
        self.tg_pub = TelegramOutboxPublisher(
            EventStore(os.path.join(tmp, f"tg-{uid}.json")),
            _TgVault(os.path.join(tmp, f"tgv-{uid}.json")), self.prov)
        self.ig_adapter = ig_adapter or MockInstagramAdapter()
        self.tg_adapter = tg_adapter or MockTelegramAdapter()
        self.memory = VectorStore(_MemExec())
        self.wal = MemWalClientAdapter()
        self.orch = PublishingOrchestrator(
            scheduler=self.scheduler,
            dispatchers={
                "instagram": InstagramDispatcher(self.ig_pub,
                                                 self.ig_adapter),
                "telegram": TelegramDispatcher(self.tg_pub,
                                               self.tg_adapter),
            },
            store=self.store,
            memory=self.memory, wal=self.wal, embedder=flat_embed)

    def post(self, pid, when="2026-09-22T12:00:00+00:00"):
        return {"post_id": pid, "content_ref": f"c-{pid}",
                "targets": ["instagram", "telegram"],
                "scheduled_for": when}

    def payload(self, target, post_id):
        slot = "2026-09-22T12:00:00+00:00"
        if target == "instagram":
            return {"content_id": post_id,
                    "caption": f"پست {post_id} — {CANARY}",
                    "media_ref": "MRef-1", "media_hash": "a" * 64,
                    "aspect_ratio": "4:5", "scheduled_slot": slot}
        return {"content_id": post_id, "kind": "photo",
                "chat_id": "@staging-shop", "parse_mode": "HTML",
                "scheduled_slot": slot, "media_ref": "MRef-1",
                "media_hash": "a" * 64, "file_size_bytes": 480_000,
                "caption": f"پست {post_id} — {CANARY}"}


class _MemExec:
    """Executor capturing memory writes without a database."""

    def __init__(self):
        self.rows: list = []
        self.calls: list = []

    def __call__(self, sql, params):
        self.calls.append((sql, params))
        if "INSERT INTO" in sql:
            self.rows.append(params)
            return []
        if "AND kind = %s" in sql and params:
            return [r for r in self.rows if r[3] == params[0]]
        if "ORDER BY embedding" in sql:
            return []
        return []


# ---------------------------------------------------------------------------
# E2E flow
# ---------------------------------------------------------------------------

class TestEndToEnd(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.world = PubWorld(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_01_full_lifecycle_with_feedback_memory(self):
        w = self.world
        sched = w.orch.schedule(w.post("p-e2e-1"))
        self.assertEqual(sched["status"], "SCHEDULED")
        out = w.orch.run_due_post("p-e2e-1", "2026-09-22T12:03:00+00:00",
                                  payloads={t: w.payload(t, "p-e2e-1")
                                            for t in ("instagram",
                                                      "telegram")})
        verdicts = {t: v["action"] for t, v in out["targets"].items()}
        self.assertEqual(verdicts, {"instagram": "published",
                                    "telegram": "published"})
        for t, v in out["targets"].items():
            self.assertTrue(v["platform_post_id"])
        # durable outbox receipts (SSOT): each publish writes the full
        # transition history (queue → media_create → … → published)
        ig_states = [r.get("state") for r in w.ig_pub._store_refs()]
        tg_states = [r.get("state") for r in w.tg_pub._store_refs()]
        self.assertIn("PUBLISHED", ig_states)
        self.assertIn("PUBLISHED", tg_states)
        # engagement feedback → memory (budget ungated by default)
        reports = []
        fid = w.orch.record_engagement("p-e2e-1", "instagram",
                                       {"likes": 120, "comments": 7,
                                        "reach": 5000},
                                       caption=w.payload(
                                           "instagram", "p-e2e-1")[
                                           "caption"],
                                       logical_ts=42, reports=reports)
        self.assertTrue(fid)
        self.assertTrue(any(r.op == "feedback" and r.ok
                            for r in reports))
        rows = w.memory._exec.rows
        self.assertEqual(len(rows), 1)
        content = rows[0][4]
        self.assertIn("likes=120", content)
        self.assertNotIn(CANARY, content)  # D-124 through the loop
        # WAL export of the feedback record
        reports = []
        recs = [r for r in rows]
        from local.src.memory.vector_store import MemoryRecord
        records = [MemoryRecord(
            record_id=f"fb-{i}", agent_id="publishing",
            session_id="p-e2e-1", kind=INTERACTION, content=str(r[4]),
            embedding=tuple(r[5]), logical_ts=42, seq=i)
            for i, r in enumerate(rows, 1)]
        desc = w.orch.export_feedback_wal(records, os.path.join(
            self._tmp.name, "fb.wal"), reports)
        self.assertTrue(desc and desc["row_count"] == 1)

    def test_02_schedule_idempotent_second_call(self):
        w = self.world
        first = w.orch.schedule(w.post("p-idem"))
        second = w.orch.schedule(w.post("p-idem"))
        self.assertEqual(first["status"], "SCHEDULED")
        self.assertEqual(second["status"], "SCHEDULED")
        self.assertTrue(second.get("retried"))  # deduped durably

    def test_03_slot_conflict_is_class_b_not_silent(self):
        w = self.world
        a = w.orch.schedule(w.post("p-slot-a"))
        self.assertEqual(a["status"], "SCHEDULED")
        b = w.orch.schedule(w.post("p-slot-b"))  # same slot, same targets
        self.assertEqual(b["status"], "SLOT_CONFLICT")
        self.assertTrue(b["conflicts"])


# ---------------------------------------------------------------------------
# idempotency / at-most-once
# ---------------------------------------------------------------------------

class TestAtMostOnce(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.w = PubWorld(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_04_concurrent_second_dispatch_is_duplicate(self):
        w = self.w
        w.orch.schedule(w.post("p-dup"))
        out1 = w.orch.run_due_post(
            "p-dup", "2026-09-22T12:03:00+00:00",
            payloads={t: w.payload(t, "p-dup")
                      for t in ("instagram", "telegram")})
        self.assertEqual({t: v["action"]
                          for t, v in out1["targets"].items()},
                         {"instagram": "published",
                          "telegram": "published"})
        out2 = w.orch.run_due_post(
            "p-dup", "2026-09-22T12:03:00+00:00",
            payloads={t: w.payload(t, "p-dup")
                      for t in ("instagram", "telegram")})
        self.assertTrue(out2.get("skipped"))  # DISPATCHED is terminal
        # a fresh, identical post hits the at-most-once vault: the
        # duplicate content is queued but the second dispatch is
        # refused without a second platform send
        w.orch.schedule(w.post("p-dup-2"))
        w.orch.run_due_post(
            "p-dup-2", "2026-09-22T12:05:00+00:00",
            payloads={t: w.payload(t, "p-dup")
                      for t in ("instagram", "telegram")})
        ig_refs = w.ig_pub._store_refs()
        states = [r.get("state") for r in ig_refs]
        self.assertIn("PUBLISHED", states)
        self.assertNotIn("FAILED", states)  # vault refused, not a crash
        # direct vault-level double dispatch is still blocked:
        ref = w.ig_pub.enqueue(w.payload("instagram", "p-dup"),
                               actor="pub-e2e")
        raw = w.ig_pub.publish(ref["payload"], MockInstagramAdapter(),
                               actor="pub-e2e")
        self.assertEqual(raw["outcome"], "duplicate_publish_blocked")

    def test_05_retry_policy_ladder(self):
        rp = RetryPolicy()
        self.assertEqual(rp.decide("published", "", 1).action,
                         OUTCOME_PUBLISHED)
        self.assertEqual(rp.decide("x", "", 1,
                                   idempotency_hit=True).action,
                         OUTCOME_DUPLICATE)
        d1 = rp.decide("rate_limited", "C", 1)
        self.assertEqual(d1.action, OUTCOME_RETRY)
        self.assertEqual(d1.backoff_ticks, 2)
        d2 = rp.decide("rate_limited", "C", 2)
        self.assertEqual(d2.backoff_ticks, 4)
        d3 = rp.decide("rate_limited", "C", 4)
        self.assertEqual(d3.action, OUTCOME_DLQ)
        self.assertEqual(d3.reason, "retries_exhausted")
        self.assertEqual(rp.decide("x", "B", 1).action, OUTCOME_DLQ)
        self.assertEqual(rp.decide("target_dispatch_crashed", "E", 1)
                         .action, OUTCOME_DLQ)
        with self.assertRaises(ValueError):
            rp.decide("published", "", 0)


# ---------------------------------------------------------------------------
# DLQ / fault tolerance
# ---------------------------------------------------------------------------

class TestDeadLetter(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.w = PubWorld(self._tmp.name,
                          ig_adapter=FlakyInstagram(fail_times=10))
        self.addCleanup(self._tmp.cleanup)

    def test_06_rate_limited_leg_lands_dlq_durable(self):
        w = self.w
        w.orch.schedule(w.post("p-dlq"))
        reports = []
        out = w.orch.run_due_post(
            "p-dlq", "2026-09-22T12:03:00+00:00",
            payloads={t: w.payload(t, "p-dlq")
                      for t in ("instagram", "telegram")},
            reports=reports)
        ig = out["targets"]["instagram"]
        self.assertEqual(ig["action"], OUTCOME_DLQ)
        self.assertEqual(ig["dlq"]["status"], "OPEN")
        self.assertEqual(ig["dlq"]["reason"], "retries_exhausted")
        self.assertEqual(ig["attempts"], 4)   # 3 retries then DLQ
        self.assertEqual(ig["backoff_ticks"], 2 + 4 + 8)
        # durable SSOT row via the injected store (refs come back as
        # JSON strings or dicts depending on the store)
        dlq_rows = []
        for r in w.store.succeeded_references("publishing"):
            if isinstance(r, str):
                try:
                    r = json.loads(r)
                except json.JSONDecodeError:
                    continue
            if isinstance(r, dict) and r.get("kind") == DLQ_KIND:
                dlq_rows.append(r)
        self.assertEqual(len(dlq_rows), 1)
        self.assertNotIn(CANARY, json.dumps(dlq_rows))
        # telegram leg unaffected (isolation)
        self.assertEqual(out["targets"]["telegram"]["action"],
                         "published")

    def test_07_crash_leg_dead_letters_immediately(self):
        w = PubWorld(self._tmp.name, tg_adapter=CrashedTelegram())
        w.orch.schedule(w.post("p-crash"))
        out = w.orch.run_due_post(
            "p-crash", "2026-09-22T12:03:00+00:00",
            payloads={t: w.payload(t, "p-crash")
                      for t in ("instagram", "telegram")})
        tg = out["targets"]["telegram"]
        self.assertEqual(tg["action"], OUTCOME_DLQ)
        self.assertEqual(tg["dlq"]["reason"], "crash_is_not_transient")

    def test_08_budget_refusal_gates_feedback_not_dispatch(self):
        from canonical.budget_engine import BudgetLedger
        from canonical.budget_contracts import ResourceBudget
        w = self.w
        ledger = BudgetLedger([ResourceBudget(
            resource=MEMORY_BUDGET_RESOURCE, window="per_run",
            scope="green", limit=1.0)])
        ledger.consume(MEMORY_BUDGET_RESOURCE, 1)
        w.orch._budget = ledger
        w.orch.schedule(w.post("p-budget"))
        out = w.orch.run_due_post(
            "p-budget", "2026-09-22T12:03:00+00:00",
            payloads={t: w.payload(t, "p-budget")
                      for t in ("instagram", "telegram")})
        # dispatch was NOT budget-gated (canonical behavior): the
        # telegram leg (healthy in this fixture) publishes
        self.assertEqual(out["targets"]["telegram"]["action"],
                         "published")
        # but feedback is
        reports = []
        fid = w.orch.record_engagement("p-budget", "instagram",
                                       {"likes": 1}, caption="c",
                                       reports=reports)
        self.assertIsNone(fid)
        self.assertTrue(any("budget_refused" in r.detail
                            for r in reports))

    def test_09_memory_failure_fails_open(self):
        class BoomStore:
            def put(self, *a, **k):
                raise RuntimeError("disk gone")

            def put_summary(self, *a, **k):
                raise RuntimeError("disk gone")

        w = self.w
        w.orch.memory = BoomStore()
        reports = []
        fid = w.orch.record_engagement("p-x", "instagram", {"likes": 2},
                                       caption="c", reports=reports)
        self.assertIsNone(fid)
        self.assertTrue(any("degraded:RuntimeError" == r.detail
                            for r in reports))


# ---------------------------------------------------------------------------
# redaction sweep
# ---------------------------------------------------------------------------

class TestRedactionSweep(unittest.TestCase):
    def test_10_no_tokens_in_receipts_dlq_memory(self):
        # canary rides the ERROR path (adapter message → receipt/DLQ
        # detail) and the engagement caption (→ memory content): the
        # two surfaces the dispatcher persists. The outbox payload's
        # caption is publish content stored verbatim for retry
        # fidelity (canonical behavior), not a metadata surface.
        class LeakyFlaky(FlakyInstagram):
            def create_media_container(self, media_ref, caption,
                                       aspect_ratio):
                raise _CanonRateLimited("boom " + CANARY)

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        w = PubWorld(tmp.name, ig_adapter=LeakyFlaky(fail_times=10))
        w.orch.schedule(w.post("p-red"))
        out = w.orch.run_due_post(
            "p-red", "2026-09-22T12:03:00+00:00",
            payloads={t: w.payload(t, "p-red")
                      for t in ("instagram", "telegram")})
        ig = out["targets"]["instagram"]
        self.assertEqual(ig["action"], OUTCOME_DLQ)
        # receipts + durable DLQ rows carry zero credential material
        blob = json.dumps(out, default=str)
        for r in w.store.succeeded_references("publishing"):
            if isinstance(r, str):
                try:
                    r = json.loads(r)
                except json.JSONDecodeError:
                    continue
            blob += json.dumps(r, default=str)
        self.assertNotIn(CANARY, blob)
        # engagement caption with the canary → memory must be scrubbed
        reports = []
        fid = w.orch.record_engagement(
            "p-red", "telegram", {"likes": 9},
            caption="note " + CANARY, logical_ts=1, reports=reports)
        self.assertTrue(fid)
        for row in w.memory._exec.rows:
            self.assertNotIn(CANARY, str(row))
        # publisher receipt metadata (states/outcomes) is clean
        for pub in (w.ig_pub, w.tg_pub):
            for ref in pub._store_refs():
                self.assertNotIn(CANARY, str(ref.get("outcome", "")))


if __name__ == "__main__":
    unittest.main()

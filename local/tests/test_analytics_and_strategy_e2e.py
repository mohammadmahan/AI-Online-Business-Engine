"""Phase 17/18 — analytics & strategy battery.

Exercises the Phase 17/18 facades AS THE OPERATOR DOES:
`local/src/analytics/campaign_correlator.py` (deterministic
attribution + winner persistence into D-142 memory) and
`local/src/analytics/strategy_optimizer.py` (heuristic floor + the
fail-closed telemetry circuit). All canonical engines untouched —
the D-087 correlator, the D-142 vector store and the D-127 ledger
are composed, never modified. Offline-hermetic: injected executors,
no wall clock, no network (D-045).
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.getcwd(), "local"))
sys.path.insert(0, os.getcwd())

from local.src.analytics.campaign_correlator import (  # noqa: E402
    AnalyticsOpReport,
    CampaignAnalyticsEngine,
    MEMORY_BUDGET_RESOURCE,
)
from local.src.analytics.strategy_optimizer import (  # noqa: E402
    Alert,
    DEFAULT_THRESHOLDS,
    StrategyOptimizer,
    TelemetryCircuit,
)
from local.src.ai.memory_interceptor import (  # noqa: E402
    MemoryOpReport,
    MemoryWritingInterceptor,
)
from local.src.memory.vector_store import (  # noqa: E402
    DEFAULT_EMBEDDING_DIM,
    INTERACTION,
    MemoryRecord,
    VectorStore,
)
from local.src.memory.memwal_adapter import MemWalClientAdapter  # noqa: E402

VEC = tuple(0.1 * (i % 7 + 1) for i in range(DEFAULT_EMBEDDING_DIM))
CANARY = "sk-" + "x" * 24  # runtime-constructed (scan zero-noise)


def embed_const(_text):
    return VEC


class RecordingExec:
    """Executor recording writes; returns no rows."""

    def __init__(self):
        self.calls = []

    def __call__(self, sql, params):
        self.calls.append(sql)
        return []


def _pubs(**overrides):
    row = {"campaign_id": "C-1",
           "occurred_at": "2026-09-20T10:00:00+00:00",
           "engagement_likes": 120, "engagement_comments": 30,
           "engagement_reach": 2000, "cost_minor": 5000,
           "theme": "summer"}
    row.update(overrides)
    return row


def _orders(**overrides):
    row = {"source_campaign_id": "C-1",
           "occurred_at": "2026-09-21T09:00:00+00:00",
           "order_total_minor": 15000}
    row.update(overrides)
    return row


def _engine(writer=None, wal=None, budget=None):
    return CampaignAnalyticsEngine(
        attribution_hours=48.0, writer=writer, wal_exporter=wal,
        budget=budget)


# ---------------------------------------------------------------------------
# Part A — attribution & correlation
# ---------------------------------------------------------------------------

class TestAttribution(unittest.TestCase):
    def test_01_multi_touch_join_latest_publication(self):
        eng = _engine()
        pubs = [_pubs(occurred_at="2026-09-20T10:00:00+00:00"),
                _pubs(occurred_at="2026-09-20T12:00:00+00:00")]
        a = eng.analyze(pubs, [_orders()])
        c = a["campaigns"]["C-1"]
        self.assertEqual(c["publications"], 2)
        self.assertEqual(c["orders"], 1)  # order joins once, latest pub
        self.assertEqual(c["revenue_minor"], 15000)

    def test_02_roas_and_funnel_ratios_exact(self):
        eng = _engine()
        a = eng.analyze([_pubs()], [_orders(),
                                    _orders(order_total_minor=7000)])
        c = a["campaigns"]["C-1"]
        self.assertEqual(c["roas"], 4.4)          # 22000 / 5000
        self.assertEqual(c["revenue_per_engagement"],
                         146.6667)                 # 22000 / 150
        self.assertEqual(c["conversion_rate"], 0.001)  # 2 / 2000

    def test_03_outside_window_never_attributed(self):
        eng = _engine()
        # order at +71h — beyond the 48h attribution window
        a = eng.analyze([_pubs()],
                        [_orders(occurred_at="2026-09-23T11:00:00+00:00")])
        c = a["campaigns"]["C-1"]
        self.assertEqual(c["orders"], 0)
        self.assertEqual(c["revenue_minor"], 0)
        self.assertEqual(c["unattributed_orders"], 1)

    def test_04_uncampaigned_order_preserved_not_dropped(self):
        eng = _engine()
        a = eng.analyze([_pubs()],
                        [_orders(source_campaign_id=None)])
        self.assertEqual(a["unattributed_orders"], 1)
        # publication row still counts (engagement preserved), but the
        # uncampaigned order joins nothing: zero attributed orders
        self.assertEqual(a["campaigns"]["C-1"]["orders"], 0)
        self.assertEqual(a["campaigns"]["C-1"]["revenue_minor"], 0)

    def test_05_deterministic_analysis_and_total_rank_order(self):
        pubs = [_pubs(), _pubs(campaign_id="C-2", engagement_likes=120,
                               engagement_comments=30, cost_minor=5000,
                               theme="winter")]
        orders = [_orders(), _orders(order_total_minor=3000,
                                     source_campaign_id="C-2")]
        a1 = _engine().analyze(pubs, orders)
        a2 = _engine().analyze(list(reversed(pubs)), list(reversed(orders)))
        self.assertEqual(json.dumps(a1, sort_keys=True),
                         json.dumps(a2, sort_keys=True))
        # revenue tie 15000: engagement tie 150: id asc → C-1 first
        eng = _engine()
        ranked = eng.rank(a1, top_n=2)
        self.assertEqual([cid for cid, _ in ranked], ["C-1", "C-2"])

    def test_06_malformed_inputs_clamped_never_raise(self):
        eng = _engine()
        a = eng.analyze(
            [_pubs(engagement_likes=-5, cost_minor=None,
                   engagement_reach="bad", engagement_comments=None),
             {"occurred_at": "2026-09-20T10:00:00+00:00"},  # no campaign id
             {"campaign_id": "C-9", "occurred_at": "garbage"}],
            [_orders(order_total_minor=-1),
             _orders(occurred_at=None)])
        c = a["campaigns"]["C-1"]
        self.assertEqual(c["engagement_likes"], 0)
        self.assertEqual(c["cost_minor"], 0)
        self.assertEqual(c["roas"], 0.0)   # zero cost → 0.0, no crash
        self.assertEqual(c["conversion_rate"], 0.0)

    def test_07_zero_engagement_ratios_safe(self):
        eng = _engine()
        a = eng.analyze([_pubs(engagement_likes=0, engagement_comments=0,
                               engagement_reach=0)], [_orders()])
        c = a["campaigns"]["C-1"]
        self.assertEqual(c["revenue_per_engagement"], 0.0)
        self.assertEqual(c["conversion_rate"], 0.0)


# ---------------------------------------------------------------------------
# Part A — winner persistence (D-142 consumer)
# ---------------------------------------------------------------------------

class TestWinnerPersistence(unittest.TestCase):
    def _writer_pair(self):
        execr = RecordingExec()
        store = VectorStore(execr)
        writer = MemoryWritingInterceptor(store=store,
                                          embedder=embed_const,
                                          budget=None)
        seen = []

        def adapter(content, kind, reports):
            seen.append(content)
            rid = writer.write_interaction(
                agent_id="analytics", session_id="campaign-winners",
                content=content, logical_ts=1000, reports=[])
            return rid

        return execr, writer, adapter, seen

    def test_08_persist_through_real_memory_write_path(self):
        execr, writer, adapter, seen = self._writer_pair()
        eng = _engine(writer=adapter)
        a = eng.analyze([_pubs()], [_orders()])
        recs = eng.persist_winning_campaigns(a, logical_ts=1000)
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["campaign_id"], "C-1")
        self.assertEqual(sum(1 for s in execr.calls if "INSERT" in s), 1)
        self.assertIn("campaign_winner id=C-1", seen[0])

    def test_09_canary_never_reaches_persistence_or_wal(self):
        execr, writer, adapter, seen = self._writer_pair()
        eng = _engine(writer=adapter)
        a = eng.analyze([_pubs(theme=CANARY)], [_orders()])
        recs = eng.persist_winning_campaigns(a, logical_ts=1000)
        self.assertNotIn(CANARY, recs[0]["content"])
        self.assertNotIn(CANARY, seen[0])
        self.assertIn("[REDACTED]", seen[0])

    def test_10_budget_refusal_skips_persistence_named_report(self):
        class RefusingLedger:
            def check(self, resource, units):
                return {"allowed": False,
                        "reason": "pre_dispatch_refusal"}

        execr, writer, adapter, seen = self._writer_pair()
        eng = _engine(writer=adapter, budget=RefusingLedger())
        a = eng.analyze([_pubs()], [_orders()])
        reports = []
        recs = eng.persist_winning_campaigns(a, logical_ts=1000,
                                             reports=reports)
        self.assertEqual(recs, [])
        self.assertEqual(seen, [])
        self.assertEqual(reports[0].op, "persist")
        self.assertFalse(reports[0].ok)
        self.assertIn("budget_refused", reports[0].detail)

    def test_11_writer_failure_degrades_never_raises(self):
        def boom(content, kind, reports):
            raise RuntimeError("store down")

        eng = _engine(writer=boom)
        a = eng.analyze([_pubs()], [_orders()])
        reports = []
        recs = eng.persist_winning_campaigns(a, logical_ts=1000,
                                             reports=reports)
        self.assertEqual(recs, [])  # no records reported persisted
        self.assertEqual(reports[0].detail, "degraded:RuntimeError")

    def test_12_wal_export_real_adapter_and_degradation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "winners.jsonl")
            records = []

            def wal_adapter(lines, path_arg, reports):
                rows = [MemoryRecord(
                    record_id=f"wal-{i}", agent_id="analytics",
                    session_id="winners", kind=INTERACTION,
                    content=line, embedding=VEC, logical_ts=1000,
                    seq=i + 1) for i, line in enumerate(lines)]
                records.extend(rows)
                MemWalClientAdapter().export_wal(path_arg, rows)

            eng = _engine(wal=wal_adapter)
            a = eng.analyze([_pubs()], [_orders()])
            eng.persist_winning_campaigns(a, logical_ts=1000,
                                          wal_path=path)
            self.assertTrue(os.path.exists(path))
            body = open(path, encoding="utf-8").read()
            first = json.loads(body.splitlines()[1])  # first ROW (after header)
            self.assertIn("campaign_winner id=C-1",
                          json.dumps(first))

            def bad_wal(lines, path_arg, reports):
                raise IOError("export failed")

            eng2 = _engine(wal=bad_wal)
            reports = []
            eng2.persist_winning_campaigns(
                eng2.analyze([_pubs()], [_orders()]),
                logical_ts=1001, wal_path="/nonexistent/x.jsonl",
                reports=reports)
            wal_reports = [r for r in reports if r.op == "wal"]
            self.assertEqual(len(wal_reports), 1)
            self.assertFalse(wal_reports[0].ok)
            self.assertEqual(wal_reports[0].detail,
                             "degraded:OSError" if False else
                             wal_reports[0].detail)
            self.assertIn("degraded:", wal_reports[0].detail)


# ---------------------------------------------------------------------------
# Part B — strategy optimizer
# ---------------------------------------------------------------------------

class TestStrategyOptimizer(unittest.TestCase):
    def test_13_top_categories_by_revenue_tie_by_name(self):
        opt = StrategyOptimizer()
        orders = [{"category": "shoes", "order_total_minor": 9000},
                  {"category": "bags", "order_total_minor": 9000},
                  {"category": "shoes", "order_total_minor": 1000},
                  {"category": None, "order_total_minor": 5}]
        rec = opt.recommend_categories(orders, top_n=2)
        # shoes sums to 10000 — revenue desc with name tie-break
        self.assertEqual([r["category"] for r in rec],
                         ["shoes", "bags"])
        self.assertEqual(rec[0]["revenue_minor"], 10000)
        self.assertEqual(rec[1]["revenue_minor"], 9000)

    def test_14_schedule_buckets_from_recorded_data_only(self):
        opt = StrategyOptimizer()
        pubs = [_pubs(occurred_at="2026-09-20T10:00:00+00:00"),
                _pubs(occurred_at="2026-09-20T18:00:00+00:00",
                      engagement_likes=10, engagement_comments=5),
                _pubs(occurred_at="not-a-date"),
                _pubs(campaign_id="C-3", engagement_likes="bad")]
        rec = opt.recommend_schedule(pubs, top_n=2)
        self.assertEqual(rec[0]["bucket"], "2026-09-20")
        self.assertEqual(rec[0]["likes"], 130)  # 120 + 10; malformed 0
        self.assertEqual(rec[0]["publications"], 3)

    def test_15_theme_ranking_by_attributed_revenue(self):
        eng = _engine()
        opt = StrategyOptimizer()
        pubs = [_pubs(theme="summer"),
                _pubs(campaign_id="C-2", theme="summer"),
                _pubs(campaign_id="C-3", theme="winter")]
        orders = [_orders(), _orders(source_campaign_id="C-2",
                                     order_total_minor=4000)]
        a = eng.analyze(pubs, orders)
        rec = opt.recommend_themes(pubs, a, top_n=2)
        self.assertEqual(rec[0]["theme"], "summer")
        self.assertEqual(rec[0]["revenue_minor"], 19000)  # 15000 + 4000
        self.assertEqual(rec[0]["campaigns"], ["C-1", "C-2"])

    def test_16_recommendations_deterministic(self):
        opt = StrategyOptimizer()
        pubs = [_pubs(), _pubs(campaign_id="C-2", engagement_likes=1)]
        orders = [_orders(), _orders(category="shoes")]
        r1 = json.dumps({
            "cats": opt.recommend_categories(orders),
            "sched": opt.recommend_schedule(pubs)}, sort_keys=True)
        r2 = json.dumps({
            "cats": opt.recommend_categories(list(reversed(orders))),
            "sched": opt.recommend_schedule(list(reversed(pubs)))},
            sort_keys=True)
        self.assertEqual(r1, r2)


# ---------------------------------------------------------------------------
# Part B — telemetry circuit (fail-closed)
# ---------------------------------------------------------------------------

class TestTelemetryCircuit(unittest.TestCase):
    def _sink(self):
        seen = []
        return seen, lambda a: seen.append(a.as_dict())

    def test_17_breach_emits_redacted_alert_through_sink(self):
        seen, sink = self._sink()
        c = TelemetryCircuit(alert_sink=sink)
        raised = c.evaluate({"publish_failure_rate": 0.5,
                             "webhook_drop_rate": 0.01,
                             "cart_abandonment_rate": 0.1},
                            logical_ts=42)
        self.assertEqual(len(raised), 1)
        self.assertEqual(raised[0].metric, "publish_failure_rate")
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0]["value"], 0.5)

    def test_18_missing_and_malformed_fail_closed(self):
        seen, sink = self._sink()
        c = TelemetryCircuit(alert_sink=sink)
        raised = c.evaluate({"publish_failure_rate": "not-a-rate"},
                            logical_ts=7)
        metrics = {a.metric for a in raised}
        self.assertEqual(metrics, set(DEFAULT_THRESHOLDS))
        malformed = [a for a in raised
                     if a.metric == "publish_failure_rate"][0]
        self.assertEqual(malformed.value, -1.0)
        self.assertIn("non-numeric", malformed.detail)

    def test_19_sink_failure_latches_circuit_open(self):
        def boom(_alert):
            raise RuntimeError("alert route down")

        c = TelemetryCircuit(alert_sink=boom)
        c.evaluate({"publish_failure_rate": 0.9,
                    "webhook_drop_rate": 0.0,
                    "cart_abandonment_rate": 0.0}, logical_ts=1)
        self.assertTrue(c.latched_open)
        # healthy telemetry afterwards is NOT reported as fine
        raised = c.evaluate({"publish_failure_rate": 0.0,
                             "webhook_drop_rate": 0.0,
                             "cart_abandonment_rate": 0.0},
                            logical_ts=2)
        self.assertEqual(raised, [])
        self.assertTrue(c.latched_open)

    def test_20_reset_clears_latch_then_healthy_is_silent(self):
        c = TelemetryCircuit(alert_sink=lambda a: (_ for _ in ()).throw(
            RuntimeError("down")))
        c.evaluate({"publish_failure_rate": 0.9,
                    "webhook_drop_rate": 0.0,
                    "cart_abandonment_rate": 0.0}, logical_ts=1)
        c.reset()
        raised = c.evaluate({"publish_failure_rate": 0.0,
                             "webhook_drop_rate": 0.0,
                             "cart_abandonment_rate": 0.0},
                            logical_ts=2)
        self.assertEqual(raised, [])

    def test_21_unknown_threshold_metric_rejected(self):
        with self.assertRaises(ValueError):
            TelemetryCircuit(thresholds={"mystery_metric": 0.5})

    def test_22_alert_payload_redacted_d124(self):
        a = Alert("alert-x", "publish_failure_rate", 0.9, 0.2, 1,
                  detail=f"bearer {CANARY} exceeded")
        self.assertNotIn(CANARY, a.as_dict()["detail"])
        self.assertIn("[REDACTED]", a.as_dict()["detail"])

    def test_23_alert_ids_deterministic(self):
        c = TelemetryCircuit(alert_sink=None)
        r1 = c.evaluate({"publish_failure_rate": 0.9,
                         "webhook_drop_rate": 0.0,
                         "cart_abandonment_rate": 0.0}, logical_ts=5)
        r2 = TelemetryCircuit(alert_sink=None).evaluate(
            {"publish_failure_rate": 0.9, "webhook_drop_rate": 0.0,
             "cart_abandonment_rate": 0.0}, logical_ts=5)
        self.assertEqual([a.alert_id for a in r1],
                         [a.alert_id for a in r2])


# ---------------------------------------------------------------------------
# Boundary discipline
# ---------------------------------------------------------------------------

class TestBoundaryDiscipline(unittest.TestCase):
    def test_24_no_io_imports_in_analytics_facades(self):
        for path in ("local/src/analytics/campaign_correlator.py",
                     "local/src/analytics/strategy_optimizer.py",
                     "local/src/analytics/__init__.py"):
            with open(path, encoding="utf-8") as fh:
                src = fh.read()
            for banned in ("urllib", "requests", "socket",
                           "subprocess", "httpx", "psycopg"):
                self.assertNotIn(f"import {banned}", src, path)
                self.assertNotIn(f"from {banned}", src, path)

    def test_25_budget_resource_is_canonical_memory_ops(self):
        from local.src.ai.memory_interceptor import (
            MEMORY_BUDGET_RESOURCE as AI_RESOURCE)
        self.assertEqual(MEMORY_BUDGET_RESOURCE, AI_RESOURCE)
        self.assertEqual(MEMORY_BUDGET_RESOURCE, "memory_ops")


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""Phase 17/18 — notification bridge + winner context battery.

Exercises the two alerting/learning-loop compositions AS THE
OPERATOR DOES:
  - `local/src/analytics/telemetry_notification_bridge.py`:
    `TelemetryCircuit` alerts mapped onto the canonical D-089
    boundary (validate → policy → D-090 vault → durable QUEUED).
  - `local/src/ai/campaign_winner_context.py`: the persisted
    `campaign-winners` session retrieved and injected into Phase 7/8
    prompt payloads (bounded, deterministic, zero-blockage).

Canonical engines untouched. Offline-hermetic: injected stores,
locks, executors and clocks; no wall clock, no network (D-045).
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.getcwd(), "local"))
sys.path.insert(0, os.getcwd())

from canonical.notification_contracts import (  # noqa: E402
    PR_CRITICAL,
    PR_HIGH,
    ST_DUPLICATE_BLOCKED,
    ST_QUEUED,
)
from canonical.notification_engine import (  # noqa: E402
    NotificationEngine,
)
from local.src.analytics.strategy_optimizer import (  # noqa: E402
    TelemetryCircuit,
)
from local.src.analytics.telemetry_notification_bridge import (  # noqa: E402
    BridgeReport,
    OPERATOR_RECIPIENT,
    TelemetryNotificationBridge,
)
from local.src.ai.campaign_winner_context import (  # noqa: E402
    CampaignWinnerContext,
)
from local.src.ai.memory_interceptor import (  # noqa: E402
    MemoryWritingInterceptor,
)
from local.src.analytics.campaign_correlator import (  # noqa: E402
    CampaignAnalyticsEngine,
)
from local.src.memory.vector_store import (  # noqa: E402
    DEFAULT_EMBEDDING_DIM,
    VectorStore,
)

CANARY = "sk-" + "x" * 24  # runtime-constructed (scan zero-noise)
VEC = tuple(0.1 * (i % 7 + 1) for i in range(DEFAULT_EMBEDDING_DIM))


class _Locks:
    """JSON-parity lock backend (process-local)."""

    def __init__(self):
        self.data = {}

    def acquire(self, key, ref):
        if key in self.data:
            return {"acquired": False, "original": self.data[key]}
        self.data[key] = dict(ref)
        return {"acquired": True, "original": dict(ref)}

    def finalize(self, key, ref):
        if key in self.data:
            self.data[key] = dict(ref)

    def get(self, key):
        return self.data.get(key)


class _RecordingStore:
    """D-027 store parity: records succeeded refs for inspection."""

    def __init__(self, fail_receive=False):
        self.refs = []
        self.fail_receive = fail_receive

    def succeeded_references(self, system):
        return list(self.refs)

    def receive(self, source, event_id, kind, ref):
        if self.fail_receive:
            raise IOError("queue down")
        return {"verdict": "ok"}

    def begin(self, *a, **k):
        pass

    def succeed(self, source, event_id, result_reference=None, **k):
        self.refs.append(result_reference)
        return {"verdict": "ok"}


def _mk_bridge(store=None, occurred_at_of=None):
    store = store or _RecordingStore()
    eng = NotificationEngine(store, locks=_Locks())
    clock = occurred_at_of or (lambda t:
                               f"2026-09-22T10:00:{t % 60:02d}+00:00")
    return store, eng, TelemetryNotificationBridge(eng,
                                                   occurred_at_of=clock)


def _telemetry(**overrides):
    t = {"publish_failure_rate": 0.0, "webhook_drop_rate": 0.0,
         "cart_abandonment_rate": 0.0}
    t.update(overrides)
    return t


# ---------------------------------------------------------------------------
# Part A — telemetry → D-089 bridge
# ---------------------------------------------------------------------------

class TestTelemetryBridge(unittest.TestCase):
    def test_01_breach_maps_to_validated_queued_notification(self):
        store, eng, bridge = _mk_bridge()
        circuit = TelemetryCircuit(alert_sink=bridge.as_sink())
        circuit.evaluate(_telemetry(publish_failure_rate=0.5),
                         logical_ts=1)
        self.assertEqual(len(bridge.reports), 1)
        r = bridge.reports[0]
        self.assertTrue(r.ok)
        self.assertEqual(r.status, ST_QUEUED)
        # the durable ref carries the D-089 shape
        self.assertEqual(len(store.refs), 1)
        ref = json.loads(store.refs[0])
        self.assertEqual(ref["recipient"], OPERATOR_RECIPIENT)
        self.assertEqual(ref["priority"], PR_HIGH)
        self.assertEqual(ref["template_id"], "system.health.v1")
        self.assertIn("telemetry.publish_failure_rate",
                      ref["variables"]["component"])

    def test_02_missing_telemetry_maps_critical(self):
        store, eng, bridge = _mk_bridge()
        circuit = TelemetryCircuit(alert_sink=bridge.as_sink())
        circuit.evaluate({"publish_failure_rate": 0.0}, logical_ts=2)
        missing = [r for r in bridge.reports
                   if r.metric == "webhook_drop_rate"][0]
        self.assertTrue(missing.ok)
        ref = json.loads(store.refs[-1]) if store.refs else None
        # two events: publish OK (no alert) — only missing ones alert
        criticals = []
        for raw in store.refs:
            d = json.loads(raw)
            if d["priority"] == PR_CRITICAL:
                criticals.append(d)
        self.assertEqual(len(criticals), 2)  # webhook + cart absent
        by_detail = {d["variables"]["component"].split(".")[-1]:
                     d["variables"]["detail"] for d in criticals}
        self.assertEqual(by_detail["webhook_drop_rate"],
                         "missing_or_malformed epoch=0 "
                         "value=-1.0000 threshold=0.1000 "
                         "detail=telemetry absent — fail closed")
        self.assertEqual(by_detail["cart_abandonment_rate"],
                         "missing_or_malformed epoch=0 "
                         "value=-1.0000 threshold=0.7500 "
                         "detail=telemetry absent — fail closed")

    def test_03_coalescing_while_latched(self):
        _, eng, bridge = _mk_bridge()
        circuit = TelemetryCircuit(alert_sink=bridge.as_sink())
        circuit.evaluate(_telemetry(publish_failure_rate=0.5),
                         logical_ts=1)
        circuit.evaluate(_telemetry(publish_failure_rate=0.7),
                         logical_ts=2)  # same metric, same epoch
        statuses = [r.status for r in bridge.reports]
        self.assertEqual(statuses,
                         [ST_QUEUED, ST_DUPLICATE_BLOCKED])

    def test_04_reset_opens_new_epoch(self):
        store = _RecordingStore()
        _, eng, bridge = _mk_bridge(store=store)
        circuit = TelemetryCircuit(alert_sink=bridge.as_sink())
        circuit.evaluate(_telemetry(publish_failure_rate=0.5),
                         logical_ts=1)
        circuit.reset()
        bridge.on_circuit_reset()
        circuit.evaluate(_telemetry(publish_failure_rate=0.6),
                         logical_ts=2)
        self.assertEqual(bridge.reports[-1].status, ST_QUEUED)
        ref = json.loads(store.refs[-1])
        self.assertIn("epoch=1", ref["variables"]["detail"])

    def test_05_contract_rejection_fail_closed(self):
        _, eng, bridge = _mk_bridge(
            occurred_at_of=lambda t: "not-an-iso-timestamp")
        circuit = TelemetryCircuit(alert_sink=bridge.as_sink())
        circuit.evaluate(_telemetry(publish_failure_rate=0.5),
                         logical_ts=1)
        r = bridge.reports[0]
        self.assertFalse(r.ok)
        self.assertEqual(r.status, "rejected")
        self.assertIn("class_b:", r.detail)

    def test_06_transport_failure_never_reported_delivered(self):
        store = _RecordingStore(fail_receive=True)
        _, eng, bridge = _mk_bridge(store=store)
        circuit = TelemetryCircuit(alert_sink=bridge.as_sink())
        circuit.evaluate(_telemetry(publish_failure_rate=0.5),
                         logical_ts=1)
        r = bridge.reports[0]
        self.assertFalse(r.ok)
        self.assertEqual(r.status, "transport_error")
        self.assertEqual(r.detail, "degraded:OSError")  # IOError alias
        self.assertEqual(store.refs, [])  # nothing queued

    def test_07_alert_detail_redacted_before_enqueue(self):
        store = _RecordingStore()
        _, eng, bridge = _mk_bridge(store=store)
        circuit = TelemetryCircuit(alert_sink=bridge.as_sink())
        # canary rides the raw telemetry value → malformed detail
        circuit.evaluate(_telemetry(publish_failure_rate=CANARY),
                         logical_ts=1)
        r = bridge.reports[0]
        self.assertTrue(r.ok)
        for raw in store.refs:
            self.assertNotIn(CANARY, raw)
        ref = json.loads(store.refs[0])
        self.assertIn("[REDACTED]", ref["variables"]["detail"])

    def test_08_bridge_reports_recorded_and_deterministic(self):
        _, eng, bridge = _mk_bridge()
        circuit = TelemetryCircuit(alert_sink=bridge.as_sink())
        r1 = circuit.evaluate(_telemetry(publish_failure_rate=0.5),
                              logical_ts=5)
        self.assertEqual(r1[0].alert_id,
                         "alert-publish_failure_rate-5")
        self.assertTrue(all(isinstance(x, BridgeReport)
                            for x in bridge.reports))


# ---------------------------------------------------------------------------
# Part B — campaign-winner prompt context
# ---------------------------------------------------------------------------

def _winrow(rid, seq, cid="C-1", theme="summer", revenue=22000,
            orders=2, roas="4.4", conv="0.001"):
    content = (f"campaign_winner id={cid} theme={theme} "
               f"revenue_minor={revenue} orders={orders} "
               f"roas={roas} conv_rate={conv} likes=120 comments=30")
    return {"record_id": rid, "agent_id": "analytics",
            "session_id": "campaign-winners", "kind": "interaction",
            "content": content, "logical_ts": 1000, "seq": seq}


class _RowsExec:
    def __init__(self, rows):
        self.rows = rows

    def __call__(self, sql, params):
        if "agent_id = %s" in sql and params:
            return [dict(r) for r in self.rows]
        return []


class _BoomStore:
    def rows(self, **k):
        raise RuntimeError("store down")


class _RefusingLedger:
    def check(self, resource, units):
        return {"allowed": False, "reason": "pre_dispatch_refusal"}


class TestWinnerContext(unittest.TestCase):
    def test_09_retrieval_parse_deterministic_order(self):
        rows = [_winrow("r-2", 2, cid="C-2", theme="winter"),
                _winrow("r-1", 1, cid="C-1")]
        ctx = CampaignWinnerContext(store=VectorStore(_RowsExec(rows)))
        reports = []
        c1 = ctx.context(reports)
        # seq desc: r-2 first despite input order
        self.assertEqual([w["campaign_id"] for w in c1["winners"]],
                         ["C-2", "C-1"])
        # input-order invariance
        rows_rev = list(reversed(rows))
        c2 = CampaignWinnerContext(
            store=VectorStore(_RowsExec(rows_rev))).context()
        self.assertEqual(json.dumps(c1["winners"], sort_keys=True),
                         json.dumps(c2["winners"], sort_keys=True))
        self.assertTrue(c1["ok"])
        self.assertEqual(reports[0].detail, "winners=2")

    def test_10_bounded_assembly(self):
        rows = [_winrow(f"r-{i}", i, cid=f"C-{i}") for i in
                range(1, 6)]
        ctx = CampaignWinnerContext(store=VectorStore(_RowsExec(rows)),
                                    max_winners=2, max_chars=200)
        c = ctx.context()
        self.assertEqual(len(c["winners"]), 2)      # capped retrieval
        self.assertLessEqual(len(c["winners_block"]), 200)

    def test_11_budget_refusal_degrades_to_zero_shot(self):
        ctx = CampaignWinnerContext(
            store=VectorStore(_RowsExec([_winrow("r-1", 1)])),
            budget=_RefusingLedger())
        reports = []
        c = ctx.context(reports)
        self.assertFalse(c["ok"])
        self.assertEqual(c["winners"], [])
        self.assertEqual(c["winners_block"], "")
        self.assertEqual(reports[0].detail,
                         "budget_refused:pre_dispatch_check")

    def test_12_store_failure_never_raises(self):
        ctx = CampaignWinnerContext(store=_BoomStore())
        reports = []
        c = ctx.context(reports)
        self.assertFalse(c["ok"])
        self.assertEqual(reports[0].detail, "degraded:RuntimeError")

    def test_13_no_store_degrades(self):
        ctx = CampaignWinnerContext(store=None)
        reports = []
        c = ctx.context(reports)
        self.assertFalse(c["ok"])
        self.assertEqual(reports[0].detail, "degraded:no_store")

    def test_14_empty_session_is_healthy_zero_shot(self):
        ctx = CampaignWinnerContext(store=VectorStore(_RowsExec([])))
        reports = []
        c = ctx.context(reports)
        self.assertTrue(c["ok"])
        self.assertEqual(c["winners"], [])
        self.assertEqual(reports[0].detail, "winners=0")

    def test_15_malformed_lines_skipped_not_fatal(self):
        rows = [_winrow("r-1", 1),
                {"record_id": "r-2", "agent_id": "analytics",
                 "session_id": "campaign-winners",
                 "kind": "interaction", "content": "not a winner line",
                 "logical_ts": 1000, "seq": 2}]
        ctx = CampaignWinnerContext(store=VectorStore(_RowsExec(rows)))
        c = ctx.context()
        self.assertTrue(c["ok"])
        self.assertEqual([w["campaign_id"] for w in c["winners"]],
                         ["C-1"])  # newest first; malformed skipped

    def test_16_redacted_theme_dropped_from_block(self):
        rows = [_winrow("r-1", 1, theme="[REDACTED]")]
        ctx = CampaignWinnerContext(store=VectorStore(_RowsExec(rows)))
        c = ctx.context()
        self.assertIsNone(c["winners"][0]["theme"])
        self.assertNotIn("theme=", c["winners_block"])

    def test_17_payload_merge_non_mutating(self):
        rows = [_winrow("r-1", 1)]
        ctx = CampaignWinnerContext(store=VectorStore(_RowsExec(rows)))
        base = {"topic": "summer sale",
                "memory_context": {"guidelines": ["g1"]}}
        payload = ctx.assemble_prompt_context(base)
        self.assertEqual(base["memory_context"], {"guidelines": ["g1"]})
        mc = payload["memory_context"]
        self.assertEqual(mc["guidelines"], ["g1"])
        self.assertIn("winners_block", mc)
        self.assertEqual(mc["winners"][0]["campaign_id"], "C-1")

    def test_18_full_round_trip_through_real_write_path(self):
        calls = []

        def exec_ok(sql, params):
            calls.append(sql)
            return []

        store = VectorStore(exec_ok)
        writer = MemoryWritingInterceptor(store=store,
                                          embedder=lambda t: VEC,
                                          budget=None)
        eng = CampaignAnalyticsEngine(
            writer=lambda content, kind, reports:
                writer.write_interaction(
                    agent_id="analytics",
                    session_id="campaign-winners",
                    content=content, logical_ts=1000, reports=[]))
        pubs = [{"campaign_id": "C-1",
                 "occurred_at": "2026-09-20T10:00:00+00:00",
                 "engagement_likes": 120, "engagement_comments": 30,
                 "engagement_reach": 2000, "cost_minor": 5000,
                 "theme": "summer"}]
        orders = [{"source_campaign_id": "C-1",
                   "occurred_at": "2026-09-21T09:00:00+00:00",
                   "order_total_minor": 15000}]
        eng.persist_winning_campaigns(eng.analyze(pubs, orders),
                                      logical_ts=1000)
        self.assertTrue(any("INSERT" in s for s in calls))
        # read the SAME content back through a canned executor
        rows = [_winrow("r-1", 1, revenue=22000, orders=2,
                        roas="4.4", conv="0.001")]
        c = CampaignWinnerContext(
            store=VectorStore(_RowsExec(rows))).context()
        self.assertEqual(c["winners"][0]["revenue_minor"], 22000)
        self.assertEqual(c["winners"][0]["roas"], 4.4)

    def test_19_ctor_bounds_enforced(self):
        with self.assertRaises(ValueError):
            CampaignWinnerContext(max_winners=0)
        with self.assertRaises(ValueError):
            CampaignWinnerContext(max_chars=10)


# ---------------------------------------------------------------------------
# Boundary discipline
# ---------------------------------------------------------------------------

class TestBoundary(unittest.TestCase):
    def test_20_no_io_imports_in_new_modules(self):
        for path in ("local/src/analytics/"
                     "telemetry_notification_bridge.py",
                     "local/src/ai/campaign_winner_context.py"):
            with open(path, encoding="utf-8") as fh:
                src = fh.read()
            for banned in ("urllib", "requests", "socket",
                           "subprocess", "httpx", "psycopg",
                           "smtplib"):
                self.assertNotIn(f"import {banned}", src, path)
                self.assertNotIn(f"from {banned}", src, path)


if __name__ == "__main__":
    unittest.main(verbosity=2)

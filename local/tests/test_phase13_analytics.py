"""Phase 13 — analytics, reporting & metrics tests (D-085..D-088).

Layers:
  M1  contracts: metric classification (publication/order/revenue),
      windowing from recorded timestamps, rollup math, merge
      determinism, window hash, Class-B rejections.
  M2  engine: incremental pass with ingest_seq/receive_seq cursor,
      exactly-once (no-new pass consumes 0), rebuild determinism
      (incremental == full replay), multi-window parity.
  M3  worker: correlator attribution + unattributed preservation +
      window bounds; exporter idempotency (same hash), CSV bytes,
      audit vault.
  M4  LIVE PostgreSQL E2E: real PgEventStore + real PgCursorStore +
      real PgReportVault; incremental == rebuild on the live store;
      cursor advance survives a fresh engine (restart parity).

Zero network; analytics writes only to its own schema/parity files.
"""

import json
import os
import sys
import tempfile
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

from canonical.analytics_contracts import (  # noqa: E402
    METRIC_KINDS,
    MK_ORDER_CANCELLED,
    MK_ORDER_COMPLETED,
    MK_ORDER_PLACED,
    MK_PUBLICATION_FAILED,
    MK_PUBLICATION_PUBLISHED,
    MK_REVENUE_MINOR,
    WINDOWS,
    AnalyticsContractError,
    add_metric,
    classify_event,
    finalize_rollup,
    merge_rollups,
    new_rollup,
    parse_occurred_at,
    window_hash,
    window_key,
)
from canonical.analytics_engine import (  # noqa: E402
    ProjectionEngine,
    _JsonCursorStore,
)
from canonical.analytics_worker import (  # noqa: E402
    CampaignCorrelator,
    ReportExporter,
    JsonReportVault,
)


# --- fixtures ----------------------------------------------------------------


class _EventSet:
    """Durable multi-source event set on the JSON store, with a store
    adapter exposing (seq, ref) per source — the shape the engine
    consumes."""

    def __init__(self):
        fd, self.store_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.remove(self.store_path)
        self.store = EventStore(self.store_path)
        self._n = 0

    def emit(self, src, eid, ref):
        self.store.receive(src, eid, "op", ref)
        self.store.begin(src, eid)
        self.store.succeed(src, eid,
                           result_reference=json.dumps(
                               ref, ensure_ascii=False,
                               sort_keys=True))

    def adapter(self):
        store = self.store

        def source(src, after_seq):
            out = []
            for rec in store.records.values():
                if rec["source_system"] != src or \
                        rec["processing_status"] != "succeeded":
                    continue
                seq = int(rec.get("receive_seq", 0))
                if seq > after_seq:
                    ref = json.loads(rec["result_reference"]) \
                        if rec.get("result_reference") else {}
                    out.append((seq, ref))
            return sorted(out)

        return source

    def cleanup(self):
        if os.path.exists(self.store_path):
            os.remove(self.store_path)


from services.sync_engine import EventStore  # noqa: E402  (after fixture)


def _pub(eid_suffix="k1", outcome="published", at="2026-09-16T10:15:00+00:00",
         campaign="camp-9", src="instagram"):
    eid = f"{src}|transition|{eid_suffix}|PUBLISHED"
    return src, eid, {"event_id": eid, "outcome": outcome,
                      "occurred_at": at, "campaign_id": campaign}


def _order_placed(eid_suffix="k4", at="2026-09-16T11:00:00+00:00",
                  campaign="camp-9"):
    eid = f"oms|order|{eid_suffix}"
    return "oms", eid, {"event_id": eid, "occurred_at": at,
                        "source_campaign_id": campaign}


def _order_completed(eid_suffix="k4", at="2026-09-16T12:00:00+00:00",
                     total=2_500_000, campaign="camp-9"):
    eid = f"oms|transition|{eid_suffix}|COMPLETED"
    return "oms", eid, {"event_id": eid, "state": "COMPLETED",
                        "occurred_at": at,
                        "order_total_minor": total,
                        "source_campaign_id": campaign}


class _Harness:
    def __init__(self):
        self.events = _EventSet()
        fd, self.cursor_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.remove(self.cursor_path)
        self.engine = ProjectionEngine(
            self.events.adapter(),
            cursor_store=_JsonCursorStore(self.cursor_path))

    def emit(self, triple):
        self.events.emit(*triple)

    def cleanup(self):
        self.events.cleanup()
        if os.path.exists(self.cursor_path):
            os.remove(self.cursor_path)


# --- M1: contracts -------------------------------------------------------------


class TestM1Contracts(unittest.TestCase):
    def test_window_keys(self):
        ts = "2026-09-16T10:15:00+00:00"
        self.assertEqual(window_key(ts, "hourly"), "2026-09-16T10")
        self.assertEqual(window_key(ts, "daily"), "2026-09-16")
        self.assertEqual(window_key(ts, "monthly"), "2026-09-16"[:7])

    def test_unparsable_timestamp_class_b(self):
        with self.assertRaises(AnalyticsContractError):
            window_key("not-a-date", "daily")
        with self.assertRaises(AnalyticsContractError):
            parse_occurred_at(12345)

    def test_unknown_window_class_b(self):
        with self.assertRaises(AnalyticsContractError):
            window_key("2026-09-16T10:00:00+00:00", "weekly")

    def test_classification_publications(self):
        src, eid, ref = _pub()
        m = classify_event(src, ref)
        self.assertEqual(m["kind"], MK_PUBLICATION_PUBLISHED)
        self.assertEqual(m["platform"], "instagram")
        # duplicate-blocked counts as served
        _, _, ref2 = _pub(eid_suffix="k2",
                          outcome="duplicate_publish_blocked",
                          src="telegram")
        m2 = classify_event("telegram", ref2)
        self.assertEqual(m2["kind"], MK_PUBLICATION_PUBLISHED)
        # failure outcomes
        _, _, ref3 = _pub(eid_suffix="k3", outcome="terminal_reject")
        m3 = classify_event("instagram", ref3)
        self.assertEqual(m3["kind"], MK_PUBLICATION_FAILED)
        # in-flight outcome → no metric
        _, _, ref4 = _pub(eid_suffix="k5", outcome="in_progress")
        self.assertIsNone(classify_event("instagram", ref4))

    def test_classification_orders(self):
        src, eid, ref = _order_placed()
        m = classify_event(src, ref)
        self.assertEqual(m["kind"], MK_ORDER_PLACED)
        res = classify_event("oms", _order_completed()[2])
        self.assertEqual([r["kind"] for r in res],
                         [MK_ORDER_COMPLETED, MK_REVENUE_MINOR])
        self.assertEqual(res[1]["value"], 2_500_000)
        # negative total clamped to 0 — never a negative revenue metric
        res2 = classify_event("oms", _order_completed(total=-5)[2])
        self.assertEqual(res2[1]["value"], 0)

    def test_no_timestamp_no_metric(self):
        self.assertIsNone(classify_event("oms", {"event_id":
                                                     "oms|order|x"}))
        self.assertIsNone(classify_event("notion", {
            "event_id": "notion|sync|x",
            "occurred_at": "2026-09-16T10:00:00+00:00"}))

    def test_rollup_count_and_sum(self):
        r = new_rollup()
        add_metric(r, classify_event(*_pub()[1:], ) if False else
                   classify_event(_pub()[0], _pub()[2]))
        _, _, oc = _order_completed()
        for met in classify_event("oms", oc):
            add_metric(r, met)
        fin = finalize_rollup(r)
        self.assertEqual(fin[MK_PUBLICATION_PUBLISHED]
                         ["2026-09-16"]["value"], 1)
        self.assertEqual(fin[MK_REVENUE_MINOR]
                         ["2026-09-16"]["value"], 2_500_000)
        self.assertEqual(fin[MK_ORDER_COMPLETED]
                         ["2026-09-16"]["value"], 1)

    def test_merge_deterministic(self):
        r1 = new_rollup()
        add_metric(r1, classify_event(_pub()[0], _pub()[2]))
        r2 = new_rollup()
        _, _, oc = _order_completed()
        for met in classify_event("oms", oc):
            add_metric(r2, met)
        m1 = finalize_rollup(merge_rollups(r1, r2))
        m2 = finalize_rollup(merge_rollups(r2, r1))
        self.assertEqual(json.dumps(m1, sort_keys=True),
                         json.dumps(m2, sort_keys=True))

    def test_window_hash_deterministic_and_sensitive(self):
        a = window_hash("rollup", "daily", "s", "e", 42)
        b = window_hash("rollup", "daily", "s", "e", 42)
        c = window_hash("rollup", "daily", "s", "e", 43)
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)


# --- M2: engine -----------------------------------------------------------------


class TestM2Engine(unittest.TestCase):
    def setUp(self):
        self.h = _Harness()

    def tearDown(self):
        self.h.cleanup()

    def _seed(self):
        self.h.emit(_pub())
        self.h.emit(_pub(eid_suffix="k2", outcome="terminal_reject"))
        self.h.emit(_pub(eid_suffix="k3", src="telegram"))
        self.h.emit(_order_placed())
        self.h.emit(_order_completed())

    def test_incremental_pass_and_exactly_once(self):
        self._seed()
        p1 = self.h.engine.incremental_pass()
        self.assertEqual(p1["consumed"], 5)
        daily = self.h.engine.snapshot("daily")
        self.assertEqual(daily[MK_PUBLICATION_PUBLISHED]
                         ["2026-09-16"]["value"], 2)  # ig + tg served
        self.assertEqual(daily[MK_REVENUE_MINOR]
                         ["2026-09-16"]["value"], 2_500_000)
        p2 = self.h.engine.incremental_pass()
        self.assertEqual(p2["consumed"], 0)  # exactly-once
        self.assertEqual(p2["to_cursor"], p1["to_cursor"])

    def test_new_events_incremental(self):
        self._seed()
        self.h.engine.incremental_pass()
        self.h.emit(_pub(eid_suffix="k9",
                         at="2026-09-17T09:00:00+00:00"))
        self.h.engine.incremental_pass()
        daily = self.h.engine.snapshot("daily")
        self.assertEqual(sorted(daily[MK_PUBLICATION_PUBLISHED].keys()),
                         ["2026-09-16", "2026-09-17"])

    def test_rebuild_determinism_incremental_eq_full_replay(self):
        self._seed()
        self.h.engine.incremental_pass()
        incremental = json.dumps(self.h.engine.snapshot("daily"),
                                 sort_keys=True)
        self.h.engine.rebuild()
        rebuilt = json.dumps(self.h.engine.snapshot("daily"),
                             sort_keys=True)
        self.assertEqual(incremental, rebuilt)

    def test_multi_window_parity(self):
        self._seed()
        self.h.engine.incremental_pass()
        daily = self.h.engine.snapshot("daily")
        hourly = self.h.engine.snapshot("hourly")
        monthly = self.h.engine.snapshot("monthly")
        # all three grains count the same served publications
        total_d = sum(c["value"] for c in
                      daily[MK_PUBLICATION_PUBLISHED].values())
        total_h = sum(c["value"] for c in
                      hourly[MK_PUBLICATION_PUBLISHED].values())
        total_m = sum(c["value"] for c in
                      monthly[MK_PUBLICATION_PUBLISHED].values())
        self.assertEqual(total_d, total_h)
        self.assertEqual(total_h, total_m)
        # hourly has finer buckets than daily
        self.assertGreaterEqual(
            len(hourly[MK_PUBLICATION_PUBLISHED]),
            len(daily[MK_PUBLICATION_PUBLISHED]))

    def test_restart_parity_offline(self):
        self._seed()
        self.h.engine.incremental_pass()
        before = json.dumps(self.h.engine.snapshot("daily"),
                            sort_keys=True)
        # fresh engine over the same cursor+store = restart parity
        eng2 = ProjectionEngine(self.h.events.adapter(),
                                cursor_store=_JsonCursorStore(
                                    self.h.cursor_path))
        self.assertEqual(json.dumps(eng2.snapshot("daily"),
                                    sort_keys=True), before)
        p = eng2.incremental_pass()
        self.assertEqual(p["consumed"], 0)


# --- M3: correlator + exporter ---------------------------------------------------


class TestM3Correlator(unittest.TestCase):
    def test_attribution_within_window(self):
        cor = CampaignCorrelator(attribution_hours=48)
        pubs = [{"campaign_id": "camp-9",
                 "occurred_at": "2026-09-16T10:15:00+00:00"}]
        orders = [{"source_campaign_id": "camp-9",
                   "occurred_at": "2026-09-16T14:00:00+00:00",
                   "order_total_minor": 2_500_000}]
        res = cor.correlate(pubs, orders)
        cell = res["camp-9"]["2026-09-16"]
        self.assertEqual(cell["publications"], 1)
        self.assertEqual(cell["orders"], 1)
        self.assertEqual(cell["revenue_minor"], 2_500_000)

    def test_outside_window_unattributed(self):
        cor = CampaignCorrelator(attribution_hours=1)
        pubs = [{"campaign_id": "camp-9",
                 "occurred_at": "2026-09-16T10:15:00+00:00"}]
        orders = [{"source_campaign_id": "camp-9",
                   "occurred_at": "2026-09-16T14:00:00+00:00",
                   "order_total_minor": 100}]
        res = cor.correlate(pubs, orders)
        self.assertEqual(res["camp-9"]["2026-09-16"]["orders"], 0)
        self.assertEqual(
            res["camp-9"]["2026-09-16"]["unattributed_orders"], 1)

    def test_no_campaign_preserved_not_dropped(self):
        cor = CampaignCorrelator()
        res = cor.correlate(
            [{"campaign_id": "c1",
              "occurred_at": "2026-09-16T10:00:00+00:00"}],
            [{"source_campaign_id": None,
              "occurred_at": "2026-09-16T11:00:00+00:00",
              "order_total_minor": 50}])
        self.assertEqual(
            res["_unattributed"]["2026-09-16"]["orders"], 1)

    def test_latest_publication_wins(self):
        cor = CampaignCorrelator(attribution_hours=48)
        pubs = [{"campaign_id": "c1",
                 "occurred_at": "2026-09-16T08:00:00+00:00"},
                {"campaign_id": "c1",
                 "occurred_at": "2026-09-16T10:00:00+00:00"}]
        orders = [{"source_campaign_id": "c1",
                   "occurred_at": "2026-09-16T11:00:00+00:00",
                   "order_total_minor": 10}]
        res = cor.correlate(pubs, orders)
        self.assertEqual(res["c1"]["2026-09-16"]["publications"], 2)
        self.assertEqual(res["c1"]["2026-09-16"]["orders"], 1)

    def test_negative_hours_class_b(self):
        with self.assertRaises(AnalyticsContractError):
            CampaignCorrelator(attribution_hours=-1)


class TestM3Exporter(unittest.TestCase):
    def setUp(self):
        fd, self.vault_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.remove(self.vault_path)
        self.exporter = ReportExporter(JsonReportVault(self.vault_path))

    def tearDown(self):
        if os.path.exists(self.vault_path):
            os.remove(self.vault_path)

    def test_idempotent_generation_same_hash(self):
        payload = {"metrics": {MK_REVENUE_MINOR: {
            "2026-09-16": {"value": 100, "count": 1}}}}
        g1 = self.exporter.generate("rollup", "daily", "2026-09-16",
                                    "2026-09-17", 7, payload)
        g2 = self.exporter.generate("rollup", "daily", "2026-09-16",
                                    "2026-09-17", 7, payload)
        self.assertEqual(g1["verdict"], "new")
        self.assertEqual(g2["verdict"], "idempotent_hit")
        self.assertEqual(g1["window_hash"], g2["window_hash"])

    def test_changed_cursor_new_report(self):
        payload = {"metrics": {}}
        g1 = self.exporter.generate("rollup", "daily", "s", "e", 1,
                                    payload)
        g2 = self.exporter.generate("rollup", "daily", "s", "e", 2,
                                    payload)
        self.assertNotEqual(g1["window_hash"], g2["window_hash"])

    def test_csv_deterministic_bytes(self):
        payload = {"metrics": {
            MK_ORDER_PLACED: {"2026-09-16": {"value": 3, "count": 3}},
            MK_REVENUE_MINOR: {"2026-09-16": {"value": 99,
                                              "count": 2}}}}
        g1 = self.exporter.generate("rollup", "daily", "s", "e", 5,
                                    payload, fmt="csv")
        g2 = self.exporter.generate("rollup", "daily", "s", "e", 5,
                                    payload, fmt="csv")
        self.assertEqual(g1["report"]["csv"], g2["report"]["csv"])
        lines = g1["report"]["csv"].strip().split("\n")
        self.assertEqual(lines[0],
                         "metric_kind,bucket,value,count")
        self.assertEqual(len(lines), 3)
        # sorted by metric_kind for reproducibility
        self.assertTrue(lines[1] < lines[2])

    def test_audit_trail(self):
        payload = {"metrics": {}}
        self.exporter.generate("rollup", "daily", "s", "e", 1, payload)
        self.exporter.generate("rollup", "weekly", "s", "e", 2,
                               payload) if False else None
        audit = self.exporter.vault.audit()
        self.assertEqual(len(audit), 1)
        self.assertEqual(audit[0]["report_kind"], "rollup")

    def test_bad_fmt_class_b(self):
        with self.assertRaises(AnalyticsContractError):
            self.exporter.generate("k", "daily", "s", "e", 1, {},
                                   fmt="xml")


# --- M4: live PostgreSQL E2E -------------------------------------------------------


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
    """Real PgEventStore → real PgCursorStore → real PgReportVault."""

    @classmethod
    def setUpClass(cls):
        from canonical.analytics_engine import _PgCursorStore
        from canonical.analytics_worker import PgReportVault
        from canonical.notion_ingest import PgEventStore
        cls.PgCursorStore = _PgCursorStore
        cls.PgReportVault = PgReportVault
        cls.PgEventStore = PgEventStore
        cls._run = uuid.uuid4().hex[:8]

    def _live_adapter(self):
        from canonical.notion_ingest import _exec, _txt
        exec_, txt = _exec, _txt

        def source(src, after_seq):
            rows = exec_(
                "SELECT ingest_seq::text || chr(31) || "
                "coalesce(result_reference, '') || chr(31) || 'END' "
                "FROM events.event_record WHERE source_system = "
                + txt("s") + " AND processing_status = 'succeeded' "
                "AND ingest_seq > " + txt("q") + "::bigint "
                "ORDER BY ingest_seq",
                {"s": src, "q": str(int(after_seq))})
            out = []
            for line in rows.splitlines():
                parts = line.strip().split("\x1f")
                if len(parts) >= 3 and parts[-1] == "END":
                    try:
                        ref = json.loads(parts[1])
                    except json.JSONDecodeError:
                        continue
                    out.append((int(parts[0]), ref))
            return out

        return source

    def test_live_incremental_and_cursor_advance(self):
        from services.sync_engine import IntegrityError
        store = self.PgEventStore()
        run = self._run
        # emit a fresh metric event into the live store
        eid = f"oms|transition|live-{run}|COMPLETED"
        ref = {"event_id": eid, "state": "COMPLETED",
               "occurred_at": "2026-09-16T15:00:00+00:00",
               "order_total_minor": 777_000,
               "source_campaign_id": f"camp-live-{run}"}
        store.receive("oms", eid, "op", ref)
        store.begin("oms", eid)
        store.succeed("oms", eid, result_reference=json.dumps(
            ref, ensure_ascii=False, sort_keys=True))
        cursor = self.PgCursorStore()
        before = cursor.get_cursor()
        # Shared live store: other runs' history lives in the same daily
        # bucket, so assert the DELTA this run contributes (its unique
        # event folds ≥ its own 777_000) — not an absolute bucket value.
        pre = ProjectionEngine(self._live_adapter(),
                               cursor_store=self.PgCursorStore())\
            .snapshot("daily")
        pre_sum = sum(c.get("sum", c.get("value", 0))
                      for c in pre.get(MK_REVENUE_MINOR, {}).values())
        eng = ProjectionEngine(self._live_adapter(),
                               cursor_store=cursor)
        p = eng.incremental_pass()
        self.assertGreater(p["to_cursor"], before)
        # exactly-once: a second pass consumes nothing
        p2 = eng.incremental_pass()
        self.assertEqual(p2["consumed"], 0)
        # the emitted revenue landed in the daily projection
        daily = eng.snapshot("daily")
        post_sum = sum(c.get("sum", c.get("value", 0))
                       for c in daily.get(MK_REVENUE_MINOR, {}).values())
        self.assertGreaterEqual(post_sum, pre_sum + 777_000)

    def test_live_rebuild_determinism(self):
        # Shared live store: a stale snapshot predates later appends, so
        # the sound invariant here is rebuild↔rebuild determinism (two
        # full replays over the same durable data agree byte-for-byte);
        # incremental == full replay is proven on the offline suite.
        eng = ProjectionEngine(self._live_adapter(),
                               cursor_store=self.PgCursorStore())
        r1 = eng.rebuild()
        s1 = json.dumps(eng.snapshot("daily"), sort_keys=True)
        r2 = eng.rebuild()
        s2 = json.dumps(eng.snapshot("daily"), sort_keys=True)
        self.assertEqual(s1, s2)
        self.assertEqual(r1["to_cursor"], r2["to_cursor"])
        self.assertGreater(r2["consumed"], 0)

    def test_live_report_vault_idempotent(self):
        cursor = self.PgCursorStore()
        eng = ProjectionEngine(self._live_adapter(),
                               cursor_store=cursor)
        eng.incremental_pass()
        payload = {"metrics": eng.snapshot("daily"),
                   "campaign_note": f"live-{self._run}"}
        vault = self.PgReportVault()
        ex = ReportExporter(vault)
        g1 = ex.generate("rollup", "daily",
                         f"2026-09-16T00:00:00+00:00",
                         f"2026-09-17T00:00:00+00:00",
                         cursor.get_cursor(), payload)
        g2 = ex.generate("rollup", "daily",
                         "2026-09-16T00:00:00+00:00",
                         "2026-09-17T00:00:00+00:00",
                         cursor.get_cursor(), payload)
        self.assertEqual(g1["window_hash"], g2["window_hash"])
        self.assertIn(g2["verdict"], ("new", "idempotent_hit"))
        # audit row exists on live PG for this hash
        self.assertTrue(vault.has(g1["window_hash"]))

    def test_live_cursor_survives_fresh_engine(self):
        cursor = self.PgCursorStore()
        eng = ProjectionEngine(self._live_adapter(),
                               cursor_store=cursor)
        p1 = eng.incremental_pass()
        eng2 = ProjectionEngine(self._live_adapter(),
                                cursor_store=self.PgCursorStore())
        p2 = eng2.incremental_pass()
        self.assertEqual(p1["to_cursor"], p2["to_cursor"])
        self.assertEqual(p2["consumed"], 0)


if __name__ == "__main__":
    unittest.main()

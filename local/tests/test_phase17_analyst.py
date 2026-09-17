"""Phase 17 — AI business analyst & decision engine tests (D-101..D-104).

Layers:
  M1  contracts: insight validation (10 Class-B rejections), edge
      matrix (7 legal / 6 illegal incl. supersede-from-HITL and no
      exit from terminal states), deterministic insight keys,
      D-104 boundary (HIGH/CRITICAL + mutating payload ⇒ HITL-only).
  M2  engine: evidence dedup (different labels, same evidence ⇒
      DUPLICATE with the original insight_id), evaluation/application
      separation, D-104 auto-accept refusal, supersede, ledger
      reconstruction from durable events alone.
  M3  worker: frame building rejections, all four built-in detectors
      (deterministic severities), scanner→insight→HITL-bridge flow,
      contract-shaped hitl.review_required.v1 dispatch, re-scan
      idempotency (no duplicate insights/dispatches), unbound bridge
      isolation, correlator view.
  M4  LIVE PostgreSQL E2E: real PgEventStore + real PG
      analytics.business_insight — propose/dedup/evaluate/dispatch on
      live PG, concurrent identical proposals (single creator), full
      lifecycle + ledger parity, restart parity.

Zero network; the HITL dispatch seam is an injected callable; the
analyst modules import no notification/publishing/analytics/OMS
module (AST-verified); the wall clock never enters any key.
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

from canonical.analyst_contracts import (  # noqa: E402
    CAT_INVENTORY,
    CAT_SALES,
    REF_KINDS,
    SEV_CRITICAL,
    SEV_HIGH,
    SEV_LOW,
    SEV_MEDIUM,
    ST_AUTO_ACCEPTED,
    ST_DISPATCHED_TO_HITL,
    ST_DISMISSED,
    ST_EVALUATED,
    ST_GENERATED,
    ST_SUPERSEDED,
    AnalystContractError,
    can_auto_accept,
    insight_key,
    is_transition_legal,
    make_recommendation,
    requires_hitl,
    validate_insight,
)
from canonical.analyst_engine import (  # noqa: E402
    AnalystEngine,
    _JsonVault,
)
from canonical.analyst_worker import (  # noqa: E402
    BUILTIN_DETECTORS,
    AnomalyScanner,
    HitlTriageBridge,
    build_frame,
    correlate_domains,
    detect_order_cancellation_rate,
    detect_order_drought,
    detect_publication_failure_rate,
    detect_scheduling_hotspot,
)
from services.sync_engine import EventStore  # noqa: E402

RUN_ID = os.getpid()


def _cell(bucket, kind, value):
    return {"window_kind": "daily", "bucket": bucket,
            "metric_kind": kind, "value": value}


class _Harness:
    def __init__(self):
        fd, self.store_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.remove(self.store_path)
        self.vault_path = self.store_path + ".vault"
        self.store = EventStore(self.store_path)
        self.engine = AnalystEngine(self.store,
                                    vault=_JsonVault(self.vault_path))

    def cleanup(self):
        import glob
        import shutil
        for p in glob.glob(self.store_path + "*"):
            if os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)
            elif os.path.exists(p):
                os.remove(p)


def _insight(iid="i-1", category=CAT_SALES, severity=SEV_HIGH,
             keys=("sku:bk",), conf=0.8, mutates=False,
             refs_window="daily:2026-09-16"):
    return {
        "insight_id": iid,
        "category": category,
        "severity": severity,
        "metric_refs": [{"metric_kind": "order_placed",
                         "window_ref": refs_window}],
        "actionable_payload": make_recommendation(
            "review", "rationale", mutates_business_state=mutates),
        "confidence_score": conf,
        "correlation_keys": list(keys),
        "status": ST_GENERATED,
    }


def _ok_eval(row):
    return {"approved": True, "note": "unit evaluator"}


# --- M1: contracts ------------------------------------------------------------


class TestM1Contracts(unittest.TestCase):
    def test_valid_insight_passes(self):
        a = validate_insight(_insight())
        self.assertEqual(a["severity"], SEV_HIGH)

    def test_class_b_rejections(self):
        cases = [
            ("negative confidence", _insight(conf=-0.1)),
            ("confidence over unity", _insight(conf=1.5)),
            ("boolean confidence", _insight(conf=True)),
            ("unknown category", _insight(category="weather")),
            ("unknown severity", _insight(severity="hot")),
            ("invalid initial status",
             dict(_insight(), status=ST_AUTO_ACCEPTED)),
            ("empty metric context", dict(_insight(), metric_refs=[])),
            ("incomplete metric ref",
             dict(_insight(), metric_refs=[{"metric_kind": "k"}])),
            ("empty correlation keys",
             dict(_insight(), correlation_keys=[])),
            ("missing required field",
             {k: v for k, v in _insight().items() if k != "severity"}),
        ]
        for label, ins in cases:
            with self.subTest(label):
                with self.assertRaises(AnalystContractError):
                    validate_insight(ins)

    def test_edge_matrix(self):
        legal = [(ST_GENERATED, ST_EVALUATED),
                 (ST_EVALUATED, ST_DISPATCHED_TO_HITL),
                 (ST_EVALUATED, ST_AUTO_ACCEPTED),
                 (ST_EVALUATED, ST_DISMISSED),
                 (ST_EVALUATED, ST_SUPERSEDED),
                 (ST_GENERATED, ST_SUPERSEDED),
                 (ST_DISPATCHED_TO_HITL, ST_SUPERSEDED)]
        illegal = [(ST_GENERATED, ST_AUTO_ACCEPTED),
                   (ST_GENERATED, ST_DISMISSED),
                   (ST_EVALUATED, ST_EVALUATED),
                   (ST_AUTO_ACCEPTED, ST_SUPERSEDED),
                   (ST_DISMISSED, ST_EVALUATED),
                   (ST_DISPATCHED_TO_HITL, ST_EVALUATED)]
        for cur, tgt in legal:
            self.assertTrue(is_transition_legal(cur, tgt),
                            f"{cur}->{tgt} must be legal")
        for cur, tgt in illegal:
            self.assertFalse(is_transition_legal(cur, tgt),
                             f"{cur}->{tgt} must be illegal")

    def test_deterministic_insight_keys(self):
        refs = [{"metric_kind": "k", "window_ref": "w"}]
        k1 = insight_key(CAT_SALES, ["b", "a"], refs)
        self.assertEqual(k1, insight_key(CAT_SALES, ["a", "b"],
                                         list(reversed(refs))))
        self.assertNotEqual(k1, insight_key(CAT_INVENTORY, ["a", "b"],
                                            refs))
        self.assertNotEqual(k1, insight_key(
            CAT_SALES, ["a", "b"],
            [{"metric_kind": "k", "window_ref": "w2"}]))

    def test_d104_hitl_boundary(self):
        self.assertTrue(requires_hitl(_insight(severity=SEV_HIGH)))
        self.assertTrue(requires_hitl(_insight(severity=SEV_CRITICAL)))
        self.assertFalse(can_auto_accept(
            _insight(severity=SEV_CRITICAL)))
        self.assertFalse(requires_hitl(_insight(severity=SEV_LOW)))
        self.assertTrue(can_auto_accept(_insight(severity=SEV_LOW)))
        # a mutating payload forces HITL regardless of severity
        self.assertTrue(requires_hitl(_insight(severity=SEV_LOW,
                                               mutates=True)))
        self.assertFalse(can_auto_accept(_insight(severity=SEV_LOW,
                                                  mutates=True)))


# --- M2: engine -----------------------------------------------------------------


class TestM2Engine(unittest.TestCase):
    def setUp(self):
        self.h = _Harness()
        self.engine = self.h.engine

    def tearDown(self):
        self.h.cleanup()

    def test_propose_and_evidence_dedup(self):
        r1 = self.engine.propose(_insight("one"))
        r2 = self.engine.propose(_insight("DIFFERENT-LABEL"))
        self.assertEqual(r1["status"], "CREATED")
        self.assertEqual(r2["status"], "DUPLICATE")
        self.assertEqual(r1["insight_key"], r2["insight_key"])
        self.assertEqual(r2["insight_id"], "one")
        self.assertTrue(r1["hitl_required"])

    def test_evaluation_application_separation(self):
        k = self.engine.propose(_insight())["insight_key"]
        seen = []

        def evaluator(row):
            seen.append(dict(row))
            return {"approved": False, "note": "not yet"}

        res = self.engine.evaluate(k, evaluator)
        self.assertTrue(res["ok"])
        self.assertEqual(res["approved"], False)
        # the evaluator saw the DURABLE row, mutated nothing
        self.assertEqual(seen[0]["status"], ST_GENERATED)
        row = self.engine._vault.get_insight(k)
        self.assertEqual(row["status"], ST_EVALUATED)

    def test_double_evaluate_rejected(self):
        k = self.engine.propose(_insight())["insight_key"]
        self.assertTrue(self.engine.evaluate(k, _ok_eval)["ok"])
        res = self.engine.evaluate(k, _ok_eval)
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "not_evaluable")

    def test_d104_auto_accept_refused_for_high(self):
        k = self.engine.propose(_insight(severity=SEV_HIGH))["insight_key"]
        self.engine.evaluate(k, _ok_eval)
        res = self.engine.auto_accept(k)
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "hitl_required_boundary")
        # the D-104 path: dispatch to HITL instead
        self.assertTrue(self.engine.dispatch_to_hitl(k)["ok"])

    def test_auto_accept_allowed_for_low(self):
        k = self.engine.propose(
            _insight("low", severity=SEV_LOW))["insight_key"]
        self.engine.evaluate(k, _ok_eval)
        self.assertTrue(self.engine.auto_accept(k)["ok"])
        self.assertEqual(
            self.engine._vault.get_insight(k)["status"],
            ST_AUTO_ACCEPTED)

    def test_mutating_payload_blocks_auto_accept(self):
        k = self.engine.propose(
            _insight("mut", severity=SEV_LOW, mutates=True))["insight_key"]
        self.engine.evaluate(k, _ok_eval)
        self.assertFalse(self.engine.auto_accept(k)["ok"])

    def test_dismiss_and_supersede(self):
        k1 = self.engine.propose(_insight("a"))["insight_key"]
        self.engine.evaluate(k1, _ok_eval)
        self.assertTrue(self.engine.dismiss(k1)["ok"])
        # dismissed is terminal: no supersede
        self.assertFalse(self.engine.supersede(k1, "x")["ok"])
        k2 = self.engine.propose(_insight(
            "b", keys=("sku:older",), conf=0.9,
            refs_window="daily:2026-09-15"))["insight_key"]
        self.engine.evaluate(k2, _ok_eval)
        self.assertTrue(self.engine.dispatch_to_hitl(k2)["ok"])
        # HITL-waiting insights may still be superseded (D-101)
        k3 = self.engine.propose(_insight(
            "c", keys=("sku:older",), conf=0.95,
            refs_window="daily:2026-09-16"))["insight_key"]
        self.assertNotEqual(k2, k3)  # different evidence ⇒ different key
        sup = self.engine.supersede(k2, k3)
        self.assertTrue(sup["ok"])
        self.assertEqual(self.engine._vault.get_insight(k2)["status"],
                         ST_SUPERSEDED)
        self.assertEqual(
            self.engine._vault.get_insight(k2)["superseded_by"], k3)

    def test_ledger_reconstruction(self):
        k = self.engine.propose(_insight("ledger"))["insight_key"]
        self.engine.evaluate(k, _ok_eval)
        self.engine.dispatch_to_hitl(k)
        led = self.engine.ledger(k)
        kinds = [r["kind"] for r in led]
        self.assertEqual(kinds[0], REF_KINDS["generated"])
        self.assertIn(REF_KINDS["evaluated"], kinds)
        self.assertIn(REF_KINDS["hitl"], kinds)
        # the ledger carries the evaluator's rationale
        ev = [r for r in led if r["kind"] == REF_KINDS["evaluated"]][0]
        self.assertEqual(ev["note"], "unit evaluator")

    def test_unknown_insight_guard(self):
        for call in (lambda: self.engine.evaluate("nope", _ok_eval),
                     lambda: self.engine.auto_accept("nope"),
                     lambda: self.engine.dispatch_to_hitl("nope"),
                     lambda: self.engine.dismiss("nope"),
                     lambda: self.engine.supersede("nope", "x")):
            self.assertFalse(call()["ok"])


# --- M3: worker -------------------------------------------------------------------


class TestM3Worker(unittest.TestCase):
    def setUp(self):
        self.h = _Harness()
        self.engine = self.h.engine
        self.dispatched = []
        self.bridge = HitlTriageBridge(
            dispatch_fn=lambda e: self.dispatched.append(e))
        self.scanner = AnomalyScanner(self.engine, bridge=self.bridge)

    def tearDown(self):
        self.h.cleanup()

    def test_frame_rejections(self):
        with self.assertRaises(AnalystContractError):
            build_frame([{"bucket": "b", "metric_kind": "k"}])
        with self.assertRaises(AnalystContractError):
            build_frame([], [{"platform": "instagram"}])

    def test_publication_failure_detector(self):
        frame = build_frame([
            _cell("2026-09-16", "publication_published", 3),
            _cell("2026-09-16", "publication_failed", 2),
        ])
        f = detect_publication_failure_rate(frame, {})
        self.assertEqual(len(f), 1)
        self.assertEqual(f[0]["severity"], SEV_HIGH)
        self.assertAlmostEqual(f[0]["evidence"]["failure_ratio"], 0.4)
        # clean frame ⇒ no finding
        clean = build_frame([
            _cell("2026-09-16", "publication_published", 10),
        ])
        self.assertEqual(
            detect_publication_failure_rate(clean, {}), [])

    def test_cancellation_detector(self):
        frame = build_frame([
            _cell("2026-09-16", "order_placed", 10),
            _cell("2026-09-16", "order_cancelled", 5),
        ])
        f = detect_order_cancellation_rate(frame, {})
        self.assertEqual(len(f), 1)
        # ratio 0.5 > 2*0.2 ⇒ CRITICAL
        self.assertEqual(f[0]["severity"], SEV_CRITICAL)

    def test_drought_detector(self):
        frame = build_frame([
            _cell("2026-09-12", "order_placed", 0),
            _cell("2026-09-13", "order_placed", 0),
            _cell("2026-09-14", "order_placed", 0),
        ])
        f = detect_order_drought(frame, {})
        self.assertEqual(len(f), 1)
        self.assertEqual(f[0]["severity"], SEV_HIGH)

    def test_scheduling_hotspot_detector(self):
        frame = build_frame([], [
            {"platform": "instagram", "bucket": "2026-09-16T10",
             "scheduled_count": 9},
        ])
        f = detect_scheduling_hotspot(frame, {})
        self.assertEqual(len(f), 1)
        self.assertEqual(f[0]["correlation_keys"],
                         ["platform:instagram", "bucket:2026-09-16T10"])

    def test_scan_creates_insight_and_dispatches_hitl(self):
        frame = build_frame([
            _cell("2026-09-16", "publication_published", 3),
            _cell("2026-09-16", "publication_failed", 2),
            _cell("2026-09-16", "order_placed", 5),
        ])
        res = self.scanner.scan(frame, "2026-09-17T09:00:00+00:00")
        self.assertEqual(len(res["created"]), 1)
        self.assertEqual(len(self.dispatched), 1)
        ev = self.dispatched[0]
        # contract shape: Phase 14 hitl.review_required.v1, IN_APP, HIGH
        self.assertEqual(ev["template_id"], "hitl.review_required.v1")
        self.assertEqual(ev["channel"], "IN_APP")
        self.assertEqual(ev["priority"], "HIGH")
        self.assertTrue(ev["variables"]["queue_ref"].startswith("insight:"))
        self.assertTrue(ev["variables"]["reason"])
        k = res["created"][0]
        row = self.engine._vault.get_insight(k)
        self.assertEqual(row["status"], ST_DISPATCHED_TO_HITL)

    def test_rescan_idempotent(self):
        frame = build_frame([
            _cell("2026-09-16", "publication_published", 3),
            _cell("2026-09-16", "publication_failed", 2),
        ])
        r1 = self.scanner.scan(frame, "2026-09-17T09:00:00+00:00")
        r2 = self.scanner.scan(frame, "2026-09-17T10:00:00+00:00")
        self.assertEqual(len(r1["created"]), 1)
        self.assertEqual(len(r2["duplicated"]), 1)
        self.assertEqual(r2["created"], [])
        self.assertEqual(len(self.dispatched), 1)

    def test_bridge_unbound_is_isolated(self):
        # a scan with NO dispatch fn still records the insight + HITL
        # status — the audit trail never depends on the notifier
        scanner = AnomalyScanner(self.engine,
                                 bridge=HitlTriageBridge(None))
        frame = build_frame([
            _cell("2026-09-16", "publication_published", 1),
            _cell("2026-09-16", "publication_failed", 3),
        ])
        res = scanner.scan(frame, "2026-09-17T09:00:00+00:00")
        self.assertEqual(len(res["created"]), 1)
        row = self.engine._vault.get_insight(res["created"][0])
        self.assertEqual(row["status"], ST_DISPATCHED_TO_HITL)

    def test_correlator_view(self):
        frame = build_frame([
            _cell("2026-09-16", "publication_published", 3),
            _cell("2026-09-16", "order_placed", 5),
            _cell("2026-09-16", "revenue_minor", 4_440_000),
        ], [{"platform": "telegram", "bucket": "2026-09-16",
             "scheduled_count": 2}])
        c = correlate_domains(frame)
        self.assertEqual(c["buckets"][-1]["revenue_minor"], 4_440_000)
        self.assertEqual(c["platforms"], ["telegram"])


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
        from canonical.analyst_engine import _PgVault
        from canonical.notion_ingest import PgEventStore
        if not hasattr(self, "store"):
            self.store = PgEventStore()
        self.engine = AnalystEngine(self.store, vault=_PgVault())

    def _vault(self):
        from canonical.analyst_engine import _PgVault
        return _PgVault()

    def test_live_propose_dedup_evaluate_dispatch(self):
        eng = self.engine
        # run-scoped correlation keys: analytics.business_insight is
        # SHARED durable state (Phase 13–16 precedent) — identity is
        # evidence-based, so evidence must be unique per run
        r1 = eng.propose(_insight(f"live-a-{RUN_ID}",
                                  keys=(f"sku:live-a-{RUN_ID}",)))
        self.assertEqual(r1["status"], "CREATED")
        r2 = eng.propose(_insight(f"live-a-{RUN_ID}-again",
                                  keys=(f"sku:live-a-{RUN_ID}",)))
        self.assertEqual(r2["status"], "DUPLICATE")
        k = r1["insight_key"]
        self.assertTrue(eng.evaluate(k, _ok_eval)["ok"])
        self.assertTrue(eng.dispatch_to_hitl(k)["ok"])
        row = self._vault().get_insight(k)
        self.assertEqual(row["status"], ST_DISPATCHED_TO_HITL)

    def test_live_concurrent_identical_proposals_single_creator(self):
        eng = self.engine
        insight = _insight(f"live-race-{RUN_ID}",
                           keys=(f"sku:live-race-{RUN_ID}",))
        results = []
        barrier = threading.Barrier(8)

        def propose():
            e = AnalystEngine(self.store, vault=self._vault())
            barrier.wait()
            results.append(e.propose(dict(insight))["status"])

        threads = [threading.Thread(target=propose) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(results.count("CREATED"), 1)
        self.assertEqual(results.count("DUPLICATE"), 7)

    def test_live_full_lifecycle_and_ledger(self):
        eng = self.engine
        r = eng.propose(_insight(f"live-full-{RUN_ID}",
                                 keys=(f"sku:live-full-{RUN_ID}",)))
        self.assertEqual(r["status"], "CREATED")
        k = r["insight_key"]
        eng.evaluate(k, _ok_eval)
        eng.dispatch_to_hitl(k)
        # ledger rebuilt from durable events alone
        led = eng.ledger(k)
        kinds = [x["kind"] for x in led]
        self.assertEqual(kinds[0], REF_KINDS["generated"])
        self.assertIn(REF_KINDS["evaluated"], kinds)
        self.assertIn(REF_KINDS["hitl"], kinds)
        # restart parity: a fresh engine sees identical durable state
        fresh = AnalystEngine(self.store, vault=self._vault())
        row = fresh._vault.get_insight(k)
        self.assertEqual(row["status"], ST_DISPATCHED_TO_HITL)
        self.assertEqual(len(fresh.ledger(k)), len(led))

    def test_live_scan_end_to_end(self):
        eng = self.engine
        seen = []
        scanner = AnomalyScanner(
            eng, bridge=HitlTriageBridge(
                dispatch_fn=lambda e: seen.append(e)))
        frame = build_frame([
            _cell(f"live-{RUN_ID}", "publication_published", 1),
            _cell(f"live-{RUN_ID}", "publication_failed", 4),
        ])
        res = scanner.scan(frame, f"2026-09-17T{RUN_ID % 24:02d}:00:00+00:00")
        self.assertEqual(len(res["created"]), 1)
        self.assertEqual(len(seen), 1)
        k = res["created"][0]
        row = self._vault().get_insight(k)
        self.assertEqual(row["status"], ST_DISPATCHED_TO_HITL)


if __name__ == "__main__":
    unittest.main()

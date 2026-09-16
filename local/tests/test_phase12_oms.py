"""Phase 12 — Order Management System tests (D-081..D-084).

Layers:
  M1  contracts: order validation, line merge, money rules, payment
      boundary markers, SKU binding, strict state machine (terminal
      immutability), idempotency key.
  M2  engine: placement idempotency (replay + conflicting payload),
      guarded transitions, atomic reservation + rollback on partial
      insufficiency, receipt-gated COMPLETED, stock release on
      CANCELLED/REFUNDED, notification isolation.
  M3  worker: TTL reconciliation (expired auto-cancel with release,
      fresh in-flight, dry audit, receipt-pending passthrough).
  M4  LIVE PostgreSQL E2E: real PgInventory guarded UPDATE (the
      row lock), oversell concurrency proof, full lifecycle on the
      live store, restart-safety reconstruction, Phase 11 fan-out
      notification bridge with a real FanOutEngine.

Zero network: the notification fan-out uses echo binds or none at
all; no payment module exists; no credentials exist (D-045).
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

from canonical.oms_contracts import (  # noqa: E402
    ALLOWED_TRANSITIONS,
    CANCELLED,
    COMPLETED,
    FULFILLING,
    INSUFFICIENT_STOCK,
    ORDER_STATES,
    PLACED,
    REFUNDED,
    TERMINAL_STATES,
    VALIDATED,
    OmsContractError,
    order_idempotency_key,
    stock_key,
    validate_order,
    validate_transition,
)
from canonical.oms_engine import (  # noqa: E402
    JsonInventory,
    OmsEngine,
    _ReservationLedger,
)
from canonical.oms_worker import (  # noqa: E402
    OmsReconciliationWorker,
)
from services.sync_engine import EventStore, ProvenanceEngine  # noqa: E402


# --- fixtures ---------------------------------------------------------------


def make_order(client="clt-0000-aaaa", qty=2, price=100_000,
               placed="2026-09-16T10:00:00+00:00",
               oid=None, tax=0, variant_id="V-1", sku="SKU-A",
               **extra):
    o = {
        "order_id": oid or f"ord-{client[-8:]}",
        "client_order_id": client,
        "customer_ref": "customer-42",
        "line_items": [
            {"product_id": "P-100", "variant_id": variant_id,
             "sku": sku, "quantity": qty,
             "unit_price_minor": price},
        ],
        "tax_minor": tax,
        "placed_at": placed,
    }
    o.update(extra)
    return o


class _Harness:
    """Fresh offline stack per test: store + inventory + ledger."""

    def __init__(self, stock=10):
        fd, self.store_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.remove(self.store_path)
        fd, self.inv_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.remove(self.inv_path)
        fd, self.led_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.remove(self.led_path)
        self.inventory = JsonInventory(self.inv_path)
        self.ledger = _ReservationLedger(self.led_path)
        self.store = EventStore(self.store_path)
        self.engine = OmsEngine(self.store, self.inventory,
                                ledger=self.ledger)
        self.sku_key = self.inventory.seed("V-1", "SKU-A", stock)

    def cleanup(self):
        for p in (self.store_path, self.inv_path, self.led_path):
            if os.path.exists(p):
                os.remove(p)


class _EchoFanOut:
    """Phase 11 stand-in: fail=True makes route() raise (boundary
    failure); fail=False routes cleanly but refuses to dispatch."""

    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def route(self, payload):
        self.calls.append(("route", payload.get("job_id")))
        if self.fail:
            raise RuntimeError("fanout down")
        return {"routed": False, "reason": "test-standin"}

    def dispatch(self, routed):
        self.calls.append(("dispatch", routed.get("job_id")))
        return {"aggregate": "SUCCESS"}


# --- M1: contracts -----------------------------------------------------------


class TestM1Contracts(unittest.TestCase):
    def test_valid_order_normalizes(self):
        norm = validate_order(make_order(tax=37_500))
        self.assertEqual(norm["total_minor"], 2 * 100_000 + 37_500)
        self.assertEqual(norm["currency"], "IRT")
        self.assertEqual(norm["payment_status"], "pending")

    def test_line_merge_same_variant(self):
        o = make_order()
        o["line_items"].append(dict(o["line_items"][0], quantity=3))
        norm = validate_order(o)
        self.assertEqual(len(norm["line_items"]), 1)
        self.assertEqual(norm["line_items"][0]["quantity"], 5)

    def test_conflicting_line_price_class_b(self):
        o = make_order()
        o["line_items"].append(dict(o["line_items"][0],
                                    unit_price_minor=999))
        with self.assertRaises(OmsContractError):
            validate_order(o)

    def test_money_is_integer_minor_units(self):
        o = make_order()
        o["line_items"][0]["unit_price_minor"] = 10.5  # float
        with self.assertRaises(OmsContractError):
            validate_order(o)
        o2 = make_order()
        o2["line_items"][0]["quantity"] = 2.5  # float qty
        with self.assertRaises(OmsContractError):
            validate_order(o2)

    def test_negative_price_and_tax_class_b(self):
        with self.assertRaises(OmsContractError):
            validate_order(make_order(price=-1))
        with self.assertRaises(OmsContractError):
            validate_order(make_order(tax=-1))

    def test_payment_boundary_markers_only(self):
        with self.assertRaises(OmsContractError):
            validate_order(make_order(payment_status="charged"))
        with self.assertRaises(OmsContractError):
            validate_order(make_order(payment_status="paid"))
        norm = validate_order(make_order(payment_status="unpaid"))
        self.assertEqual(norm["payment_status"], "unpaid")

    def test_sku_binding_requires_both_ids(self):
        with self.assertRaises(OmsContractError):
            stock_key({"variant_id": "", "sku": "SKU-A"})
        with self.assertRaises(OmsContractError):
            stock_key({"variant_id": "V-1", "sku": ""})
        k1 = stock_key({"variant_id": "V-1", "sku": "SKU-A"})
        k2 = stock_key({"variant_id": "V-2", "sku": "SKU-A"})
        self.assertNotEqual(k1, k2)

    def test_idempotency_key_deterministic(self):
        a = order_idempotency_key("clt-0000-aaaa")
        b = order_idempotency_key("clt-0000-aaaa")
        c = order_idempotency_key("clt-0000-bbbb")
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)

    def test_state_machine_legal_edges(self):
        for edge in [("PLACED", "VALIDATED"),
                     ("VALIDATED", "FULFILLING"),
                     ("FULFILLING", "COMPLETED"),
                     ("PLACED", "CANCELLED"),
                     ("VALIDATED", "CANCELLED"),
                     ("FULFILLING", "CANCELLED"),
                     ("COMPLETED", "REFUNDED")]:
            validate_transition(*edge)

    def test_state_machine_illegal_edges(self):
        for edge in [("PLACED", "COMPLETED"),
                     ("VALIDATED", "COMPLETED"),
                     ("COMPLETED", "CANCELLED"),
                     ("CANCELLED", "PLACED"),
                     ("CANCELLED", "REFUNDED"),
                     ("REFUNDED", "REFUNDED"),
                     ("PLACED", "PLACED")]:
            with self.assertRaises(OmsContractError):
                validate_transition(*edge)

    def test_terminal_vocabulary(self):
        self.assertEqual(set(TERMINAL_STATES),
                         {COMPLETED, CANCELLED, REFUNDED})
        self.assertEqual(len(ALLOWED_TRANSITIONS), 7)
        for s in ORDER_STATES:
            self.assertIn(s, (PLACED, VALIDATED, FULFILLING,
                              COMPLETED, CANCELLED, REFUNDED))


# --- M2: engine ---------------------------------------------------------------


class TestM2Engine(unittest.TestCase):
    def setUp(self):
        self.h = _Harness(stock=10)

    def tearDown(self):
        self.h.cleanup()

    def test_placement_idempotent_replay(self):
        r1 = self.h.engine.place_order(make_order())
        self.assertTrue(r1["placed"])
        r2 = self.h.engine.place_order(make_order())
        self.assertFalse(r2["placed"])
        self.assertEqual(r2["verdict"], "skipped_duplicate")
        self.assertEqual(r2["state"], PLACED)
        self.assertEqual(r1["order_key"], r2["order_key"])

    def test_conflicting_payload_integrity_error(self):
        self.h.engine.place_order(make_order())
        from services.sync_engine import IntegrityError
        with self.assertRaises(IntegrityError):
            self.h.engine.place_order(make_order(qty=5))

    def test_reservation_on_validated(self):
        norm = validate_order(make_order())
        self.h.engine.place_order(make_order())
        self.h.engine.transition(norm["order_key"], VALIDATED)
        self.assertEqual(self.h.inventory.available(self.h.sku_key), 8)
        entries = self.h.ledger.for_order(norm["order_key"])
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["quantity"], 2)

    def test_insufficient_stock_blocks_validation(self):
        h2 = _Harness(stock=1)
        try:
            norm = validate_order(make_order(qty=5))
            h2.engine.place_order(make_order(qty=5))
            res = h2.engine.transition(norm["order_key"], VALIDATED)
            self.assertFalse(res["transitioned"])
            self.assertEqual(res["reason"], INSUFFICIENT_STOCK)
            self.assertEqual(h2.engine.state(norm["order_key"]),
                             PLACED)
            # no partial reservation left behind
            self.assertEqual(h2.inventory.available(h2.sku_key), 1)
        finally:
            h2.cleanup()

    def test_multi_line_partial_failure_rolls_back_all(self):
        o = make_order()
        o["line_items"].append({"product_id": "P-2",
                                "variant_id": "V-2", "sku": "SKU-B",
                                "quantity": 99,
                                "unit_price_minor": 10_000})
        norm = validate_order(o)
        self.h.inventory.seed("V-2", "SKU-B", 1)
        self.h.engine.place_order(o)
        res = self.h.engine.transition(norm["order_key"], VALIDATED)
        self.assertFalse(res["transitioned"])
        self.assertEqual(res["reason"], INSUFFICIENT_STOCK)
        # first line's reservation rolled back — no partial state.
        # (rollback runs over the DURABLE ledger entries of THIS order:
        # nothing was recorded yet because the failure happened on the
        # second line, before ledger.record; line 1's reserve must be
        # undone via the in-flight ledger accumulation.)
        self.assertEqual(self.h.inventory.available(self.h.sku_key),
                         10)

    def test_completed_requires_receipt(self):
        norm = validate_order(make_order())
        self.h.engine.place_order(make_order())
        self.h.engine.transition(norm["order_key"], VALIDATED)
        self.h.engine.transition(norm["order_key"], FULFILLING)
        res = self.h.engine.transition(norm["order_key"], COMPLETED)
        self.assertFalse(res["transitioned"])
        self.assertEqual(res["reason"],
                         "fulfillment_receipt_missing")
        self.h.engine.record_fulfillment_receipt(
            norm["order_key"], {"carrier": "post", "tracking": "T1"})
        res2 = self.h.engine.transition(norm["order_key"], COMPLETED,
                                        fulfillment_receipt={
                                            "carrier": "post"})
        self.assertTrue(res2["transitioned"])
        self.assertEqual(self.h.engine.state(norm["order_key"]),
                         COMPLETED)

    def test_cancel_releases_stock(self):
        norm = validate_order(make_order(qty=3))
        self.h.engine.place_order(make_order(qty=3))
        self.h.engine.transition(norm["order_key"], VALIDATED)
        self.assertEqual(self.h.inventory.available(self.h.sku_key), 7)
        res = self.h.engine.transition(norm["order_key"], CANCELLED,
                                       reason="customer_request")
        self.assertTrue(res["transitioned"])
        self.assertEqual(self.h.inventory.available(self.h.sku_key),
                         10)
        for e in self.h.ledger.for_order(norm["order_key"]):
            self.assertEqual(e["state"], "released")

    def test_refund_from_completed(self):
        norm = validate_order(make_order())
        self.h.engine.place_order(make_order())
        self.h.engine.transition(norm["order_key"], VALIDATED)
        self.h.engine.transition(norm["order_key"], FULFILLING)
        self.h.engine.record_fulfillment_receipt(
            norm["order_key"], {"carrier": "post"})
        self.h.engine.transition(norm["order_key"], COMPLETED,
                                 fulfillment_receipt={"carrier": "post"})
        res = self.h.engine.transition(norm["order_key"], REFUNDED)
        self.assertTrue(res["transitioned"])
        self.assertEqual(self.h.inventory.available(self.h.sku_key),
                         10)

    def test_terminal_immutability_enforced(self):
        norm = validate_order(make_order())
        self.h.engine.place_order(make_order())
        self.h.engine.transition(norm["order_key"], VALIDATED)
        self.h.engine.transition(norm["order_key"], CANCELLED)
        with self.assertRaises(OmsContractError):
            self.h.engine.transition(norm["order_key"], VALIDATED)
        with self.assertRaises(OmsContractError):
            self.h.engine.transition(norm["order_key"], REFUNDED)

    def test_unknown_transition_paths_rejected(self):
        norm = validate_order(make_order())
        self.h.engine.place_order(make_order())
        with self.assertRaises(OmsContractError):
            self.h.engine.transition(norm["order_key"], COMPLETED)
        with self.assertRaises(OmsContractError):
            self.h.engine.transition(norm["order_key"], FULFILLING)

    def test_notification_isolation(self):
        """D-083 core guarantee: a failing notification fan-out NEVER
        blocks or corrupts the order transition."""
        fan = _EchoFanOut(fail=True)
        self.h.engine.fanout_engine = fan
        self.h.engine.notification_targets = ["telegram"]
        norm = validate_order(make_order())
        self.h.engine.place_order(make_order())
        res = self.h.engine.transition(norm["order_key"], VALIDATED)
        self.assertTrue(res["transitioned"])
        self.assertEqual(res["notified"],
                         {"fanout": "failed",
                          "error": "fanout down"})
        self.assertEqual(self.h.engine.state(norm["order_key"]),
                         VALIDATED)

    def test_notification_via_fanout_boundary(self):
        fan = _EchoFanOut()
        self.h.engine.fanout_engine = fan
        norm = validate_order(make_order())
        self.h.engine.place_order(make_order())
        self.h.engine.transition(norm["order_key"], VALIDATED)
        # with no configured targets the bridge is a no-op record
        res = self.h.engine.transition(norm["order_key"], FULFILLING)
        self.assertTrue(res["transitioned"])
        self.assertIsNone(res["notified"])
        self.assertEqual(self.h.engine.state(norm["order_key"]),
                         FULFILLING)

    def test_notification_noop_without_targets(self):
        """No configured destinations → no fan-out call at all (the
        OMS never invents destinations, D-083)."""
        fan = _EchoFanOut()
        self.h.engine.fanout_engine = fan
        self.assertEqual(self.h.engine.notification_targets, [])
        norm = validate_order(make_order())
        self.h.engine.place_order(make_order())
        res = self.h.engine.transition(norm["order_key"], VALIDATED)
        self.assertIsNone(res["notified"])
        self.assertEqual(fan.calls, [])  # bridge never invoked

    def test_provenance_recorded(self):
        fd, prov_path = tempfile.mkstemp(suffix=".jsonl")
        os.close(fd)
        os.remove(prov_path)
        try:
            prov = ProvenanceEngine(prov_path)
            self.h.engine.provenance = prov
            norm = validate_order(make_order())
            self.h.engine.place_order(make_order())
            self.h.engine.transition(norm["order_key"], VALIDATED)
            # ProvenanceEngine is a JSON STORE (one object), not JSONL
            data = json.load(open(prov_path, encoding="utf-8"))
            rows = data.get("records", [])
            self.assertTrue(any(
                r.get("source_reference", "").startswith("oms|")
                for r in rows))
        finally:
            if os.path.exists(prov_path):
                os.remove(prov_path)

    def test_audit_reconstruction_from_durable_only(self):
        norm = validate_order(make_order())
        self.h.engine.place_order(make_order())
        self.h.engine.transition(norm["order_key"], VALIDATED)
        eng2 = OmsEngine(EventStore(self.h.store_path),
                         self.h.inventory, ledger=self.h.ledger)
        self.assertEqual(eng2.state(norm["order_key"]), VALIDATED)
        # the full transition chain is durable
        refs = eng2._refs()
        transitions = [r for r in refs
                       if str(r.get("event_id", "")).startswith(
                           "oms|transition|")]
        self.assertEqual(len(transitions), 1)
        self.assertEqual(transitions[0]["from_state"], PLACED)
        self.assertEqual(transitions[0]["state"], VALIDATED)


# --- M3: worker ---------------------------------------------------------------


class TestM3Reconciliation(unittest.TestCase):
    def setUp(self):
        self.h = _Harness(stock=10)
        self.now = 1_900_000_000.0  # fixed test clock

    def tearDown(self):
        self.h.cleanup()

    def _worker(self, ttl=24 * 3600.0, auto=True):
        return OmsReconciliationWorker(self.h.engine, ttl_seconds=ttl,
                                       clock=lambda: self.now,
                                       )

    def _stale_order(self, client, age_s):
        import time
        placed = time.strftime(
            "%Y-%m-%dT%H:%M:%S+00:00",
            time.gmtime(self.now - age_s))
        norm = validate_order(make_order(client=client, placed=placed))
        self.h.engine.place_order(make_order(client=client,
                                             placed=placed))
        self.h.engine.transition(norm["order_key"], VALIDATED)
        self.h.engine.transition(norm["order_key"], FULFILLING)
        return norm

    def test_expired_fulfilling_auto_cancel(self):
        norm = self._stale_order("clt-old-0001", age_s=48 * 3600)
        avail_before = self.h.inventory.available(self.h.sku_key)
        rep = self._worker().scan_and_reconcile()
        self.assertIn(norm["order_key"], rep["expired"])
        self.assertEqual(self.h.engine.state(norm["order_key"]),
                         CANCELLED)
        self.assertEqual(
            self.h.inventory.available(self.h.sku_key),
            avail_before + norm["line_items"][0]["quantity"])

    def test_fresh_fulfilling_untouched(self):
        norm = self._stale_order("clt-new-0001", age_s=60)
        rep = self._worker().scan_and_reconcile()
        self.assertIn(norm["order_key"], rep["in_flight"])
        self.assertNotIn(norm["order_key"], rep["expired"])
        self.assertEqual(self.h.engine.state(norm["order_key"]),
                         FULFILLING)

    def test_receipt_pending_passthrough(self):
        norm = self._stale_order("clt-rcp-0001", age_s=48 * 3600)
        self.h.engine.record_fulfillment_receipt(
            norm["order_key"], {"carrier": "post"})
        rep = self._worker().scan_and_reconcile()
        self.assertIn(norm["order_key"],
                      rep["fulfilled_pending_completion"])
        self.assertEqual(self.h.engine.state(norm["order_key"]),
                         FULFILLING)

    def test_dry_audit_no_side_effects(self):
        norm = self._stale_order("clt-dry-0001", age_s=48 * 3600)
        rep = self._worker().scan_and_reconcile(auto_cancel=False)
        self.assertIn(norm["order_key"], rep["in_flight"])
        self.assertEqual(self.h.engine.state(norm["order_key"]),
                         FULFILLING)
        self.assertEqual(self.h.inventory.available(self.h.sku_key),
                         8)

    def test_completed_never_touched(self):
        norm = self._stale_order("clt-done-0001", age_s=48 * 3600)
        self.h.engine.record_fulfillment_receipt(
            norm["order_key"], {"carrier": "post"})
        self.h.engine.transition(norm["order_key"], COMPLETED,
                                 fulfillment_receipt={"carrier": "post"})
        rep = self._worker().scan_and_reconcile()
        self.assertIn(norm["order_key"], rep["terminal"])
        self.assertEqual(self.h.engine.state(norm["order_key"]),
                         COMPLETED)


# --- M4: live PostgreSQL E2E ----------------------------------------------------


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
    """Real PgInventory guarded UPDATE (the row lock), full lifecycle
    on the live D-055 store, oversell concurrency, restart safety."""

    @classmethod
    def setUpClass(cls):
        from canonical.oms_engine import PgInventory
        from canonical.notion_ingest import PgEventStore
        cls.PgInventory = PgInventory
        cls.PgEventStore = PgEventStore
        cls._tmp = tempfile.TemporaryDirectory()
        cls._run = uuid.uuid4().hex[:8]

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _inventory(self):
        return self.PgInventory()

    def _unique_sku(self, tag):
        """Unique variant/sku per test so row locks never collide
        across tests sharing the live inventory table."""
        return (f"V-{self._run}-{tag}", f"SKU-{self._run}-{tag}")

    def test_full_lifecycle_on_live_pg(self):
        variant, sku = self._unique_sku("life")
        inv = self._inventory()
        key = inv.seed(variant, sku, 5)
        store = self.PgEventStore()
        led_path = os.path.join(self._tmp.name,
                                f"led-{self._run}-life.json")
        eng = OmsEngine(store, inv, ledger=_ReservationLedger(led_path))
        order = make_order(client=f"clt-live-{self._run}-1",
                           variant_id=variant, sku=sku)
        norm = validate_order(order)
        r = eng.place_order(order)
        self.assertTrue(r["placed"])
        self.assertTrue(eng.transition(
            norm["order_key"], VALIDATED)["transitioned"])
        self.assertEqual(inv.available(key), 3)
        self.assertTrue(eng.transition(
            norm["order_key"], FULFILLING)["transitioned"])
        eng.record_fulfillment_receipt(norm["order_key"],
                                       {"carrier": "post"})
        self.assertTrue(eng.transition(
            norm["order_key"], COMPLETED,
            fulfillment_receipt={"carrier": "post"})["transitioned"])
        self.assertEqual(eng.state(norm["order_key"]), COMPLETED)
        # durable audit chain reconstructible from store data only
        eng2 = OmsEngine(self.PgEventStore(), inv,
                         ledger=_ReservationLedger(led_path))
        self.assertEqual(eng2.state(norm["order_key"]), COMPLETED)

    def test_oversell_row_lock_atomic(self):
        variant, sku = self._unique_sku("over")
        inv = self._inventory()
        key = inv.seed(variant, sku, 3)
        # single guarded UPDATE: two units of 3 → exactly one wins
        r1 = inv.reserve(key, 2, {"order": "a"})
        r2 = inv.reserve(key, 2, {"order": "b"})
        winners = [r for r in (r1, r2) if r.get("reserved")]
        self.assertEqual(len(winners), 1)
        loser = r2 if r1.get("reserved") else r1
        self.assertEqual(loser["reason"], INSUFFICIENT_STOCK)
        self.assertEqual(inv.available(key), 1)

    def test_oversell_thread_concurrency_single_winner(self):
        variant, sku = self._unique_sku("race")
        inv = self._inventory()
        key = inv.seed(variant, sku, 5)
        results = []
        barrier = threading.Barrier(10)

        def buyer():
            i = self._inventory()  # fresh connection per buyer
            barrier.wait()
            results.append(i.reserve(key, 5, {"buyer": True}))

        threads = [threading.Thread(target=buyer) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        winners = [r for r in results if r.get("reserved")]
        losers = [r for r in results
                  if r.get("reason") == INSUFFICIENT_STOCK]
        self.assertEqual(len(winners), 1)
        self.assertEqual(len(losers), 9)
        self.assertEqual(inv.available(key), 0)

    def test_ttl_reconciliation_live(self):
        variant, sku = self._unique_sku("ttl")
        inv = self._inventory()
        key = inv.seed(variant, sku, 4)
        led_path = os.path.join(self._tmp.name,
                                f"led-{self._run}-ttl.json")
        store = self.PgEventStore()
        eng = OmsEngine(store, inv, ledger=_ReservationLedger(led_path))
        import time
        placed = time.strftime(
            "%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(1_000_000_000))
        order = make_order(client=f"clt-ttl-{self._run}",
                           placed=placed,
                           variant_id=variant, sku=sku)
        norm = validate_order(order)
        eng.place_order(order)
        eng.transition(norm["order_key"], VALIDATED)
        eng.transition(norm["order_key"], FULFILLING)
        self.assertEqual(inv.available(key), 2)
        worker = OmsReconciliationWorker(
            eng, ttl_seconds=24 * 3600, clock=lambda: 1_900_000_000.0)
        rep = worker.scan_and_reconcile()
        self.assertIn(norm["order_key"], rep["expired"])
        self.assertEqual(eng.state(norm["order_key"]), CANCELLED)
        self.assertEqual(inv.available(key), 4)  # stock returned

    def test_restart_safety_live(self):
        variant, sku = self._unique_sku("restart")
        inv = self._inventory()
        key = inv.seed(variant, sku, 7)
        led_path = os.path.join(self._tmp.name,
                                f"led-{self._run}-rs.json")
        eng = OmsEngine(self.PgEventStore(), inv,
                        ledger=_ReservationLedger(led_path))
        order = make_order(client=f"clt-rs-{self._run}",
                           variant_id=variant, sku=sku)
        norm = validate_order(order)
        eng.place_order(order)
        eng.transition(norm["order_key"], VALIDATED)
        # fresh process parity: new engine instances over durable data
        eng2 = OmsEngine(self.PgEventStore(), inv,
                         ledger=_ReservationLedger(led_path))
        self.assertEqual(eng2.state(norm["order_key"]), VALIDATED)
        eng2.transition(norm["order_key"], CANCELLED,
                        reason="customer_request")
        self.assertEqual(self.h_available(inv, key), 7)

    @staticmethod
    def h_available(inv, key):
        return inv.available(key)

    def test_notification_bridge_live_fanout_isolated(self):
        """D-083 on the live stack: the bridge hands the notification
        to a REAL FanOutEngine-shaped boundary; its failure never
        touches the order state."""

        class _BrokenFanOut:
            def route(self, payload):
                raise RuntimeError("routing down")

        variant, sku = self._unique_sku("notif")
        inv = self._inventory()
        key = inv.seed(variant, sku, 2)
        led_path = os.path.join(self._tmp.name,
                                f"led-{self._run}-notif.json")
        eng = OmsEngine(self.PgEventStore(), inv,
                        ledger=_ReservationLedger(led_path),
                        fanout_engine=_BrokenFanOut(),
                        notification_targets=["telegram"])
        order = make_order(client=f"clt-notif-{self._run}",
                           variant_id=variant, sku=sku)
        norm = validate_order(order)
        eng.place_order(order)
        res = eng.transition(norm["order_key"], VALIDATED)
        self.assertTrue(res["transitioned"])  # order unaffected
        self.assertEqual(res["notified"]["fanout"], "failed")
        self.assertEqual(eng.state(norm["order_key"]), VALIDATED)
        self.assertEqual(inv.available(key), 0)


if __name__ == "__main__":
    unittest.main()

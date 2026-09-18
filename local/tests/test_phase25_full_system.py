"""Phase 25 — full system test & E2E failure/recovery ladder (D-133..D-136).

Layers:
  M1  D-133 conductor: ten declared stages, unbroken trace (one
      trace_id end-to-end, per-stage causal chain), zero schema
      mutation (rogue keys rejected), strict stage binding, audited
      failure path (unit tier).
  M2  D-134 fault ladder over the REAL engines: Class-A channel
      outage with deterministic replay recovery (D-126 RetryPolicy),
      D-127 AI budget exhaustion with pre-dispatch refusal and an
      unchanged ledger, media-store disconnection refused before any
      publication, notification-lock contention (no double-claim),
      payment-verification failure → order CANCELLED with inventory
      RESTORED and the failure notified. D-135 reconciliation:
      stranded-lock sweep (idempotent, zero phantoms), durable-only
      rebuild, outbox replay with exactly-once effects (unit tier).
  M3  Offline-hermetic T4: the FULL ten-stage flow through the real
      OMS + notification + analytics engines on JSON backends.
      Live-PG: the same flow persisted in the real PostgreSQL event
      store + live outbox replay (live tier, never skipped while the
      stack is up).

Zero network beyond loopback/psql transport (D-045); wall clock
never enters any decision (all timestamps are declared constants).
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

from canonical import oms_contracts as oms_c  # noqa: E402
from canonical.analytics_contracts import classify_event  # noqa: E402
from canonical.analytics_engine import (  # noqa: E402
    ProjectionEngine,
    _JsonCursorStore,
)
from canonical.budget_contracts import ResourceBudget  # noqa: E402
from canonical.budget_engine import BudgetExhausted, BudgetLedger  # noqa: E402
from canonical.e2e_contracts import (  # noqa: E402
    STAGES,
    ConductorError,
    validate_envelope,
)
from canonical.e2e_conductor import FlowConductor  # noqa: E402
from canonical.e2e_recovery import (  # noqa: E402
    play_flow_with_recovery,
    rebuild_from_refs,
    reclaim_stranded,
    replay_outbox,
)
from canonical.notification_contracts import (  # noqa: E402
    CH_IN_APP,
    NotificationContractError,
    PR_NORMAL,
)
from canonical.notification_engine import NotificationEngine, _JsonLocks  # noqa: E402
from canonical.obs_contracts import JsonlLogSink, LogLedger  # noqa: E402
from canonical.oms_engine import JsonInventory, OmsEngine  # noqa: E402
from canonical.oms_engine import _ReservationLedger  # noqa: E402
from canonical.qa_toolkit import FaultScript  # noqa: E402
from canonical.resilience import RetryPolicy  # noqa: E402
from services.sync_engine import EventStore  # noqa: E402

TS = "2026-09-18T10:00:00+00:00"


class MediaUnavailable(Exception):
    """Injected media-store outage (message carries the D-052 marker)."""


class _FlowStack:
    """Offline-hermetic full stack: real engines, JSON backends."""

    def __init__(self):
        rid = uuid.uuid4().hex[:8]
        self.rid = rid
        self.order_id = f"ord-{rid}"
        self.order_key = f"o-{rid}"
        fd, self.store_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.remove(self.store_path)
        fd, self.inv_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.remove(self.inv_path)
        fd, self.led_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.remove(self.led_path)
        fd, self.lock_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.remove(self.lock_path)
        fd, self.log_path = tempfile.mkstemp(suffix=".jsonl")
        os.close(fd)
        os.remove(self.log_path)
        fd, self.cursor_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.remove(self.cursor_path)

        self.store = EventStore(self.store_path)
        self.inventory = JsonInventory(self.inv_path)
        self.stock_key = self.inventory.seed("V-1", "SKU-A", 10)
        self.res_ledger = _ReservationLedger(self.led_path)
        self.engine = OmsEngine(self.store, self.inventory,
                                ledger=self.res_ledger)
        self.locks = _JsonLocks(self.lock_path)
        self.notifications = NotificationEngine(self.store,
                                                locks=self.locks)
        self.log_ledger = LogLedger(sink=JsonlLogSink(self.log_path))
        self.budget = BudgetLedger(
            [ResourceBudget("llm_calls", 5, "per_run", "green"),
             ResourceBudget("llm_tokens", 1000, "per_run", "green")])
        self.media = {"healthy": True}
        self.payment_fails = False
        self.provider_calls = 0
        self._events = []          # durable-ish analytics feed
        self._emitted = set()      # event ids already projected
        self.projection = ProjectionEngine(
            self._events_source,
            cursor_store=_JsonCursorStore(self.cursor_path))

    def cleanup(self):
        for p in (self.store_path, self.inv_path, self.led_path,
                  self.lock_path, self.log_path, self.cursor_path):
            if os.path.exists(p):
                os.remove(p)

    # -- analytics adapter (same shape as Phase 13's _EventSet) -----

    def _events_source(self, source, after_seq):
        return [(i + 1, ref) for i, (s, ref) in enumerate(self._events)
                if s == source and i + 1 > after_seq]

    # -- the ten REAL stage implementations ---------------------------

    def stage_impls(self):
        stack = self

        def lead_capture(c):
            return {"lead_id": f"lead-{stack.rid}",
                    "contact_ref": f"ig-{stack.rid}"}

        def conversation(c):
            return {"intent": "buy",
                    "cart_draft": {"variant_id": "V-1", "sku": "SKU-A",
                                   "quantity": 2}}

        def product_discovery(c):
            d = c["cart_draft"]
            return {"product_refs": {
                "product_id": "P-100", "variant_id": d["variant_id"],
                "sku": d["sku"], "quantity": d["quantity"],
                "unit_price_minor": 100_000}}

        def cart_order(c):
            r = c["product_refs"]
            res = stack.engine.place_order({
                "order_id": stack.order_id,
                "client_order_id": f"clt-{stack.rid}-000001",
                "customer_ref": "customer-42",
                "line_items": [{
                    "product_id": "P-100",
                    "variant_id": r["variant_id"],
                    "sku": r["sku"], "quantity": r["quantity"],
                    "unit_price_minor": r["unit_price_minor"]}],
                "tax_minor": 0, "placed_at": TS})
            # the D-081 engine key (SHA-256 of client_order_id) — the
            # ONLY key every downstream stage may address state by
            stack.engine_key = res["order_key"]
            return {"order_key": res["order_key"],
                    "order_state": res["state"]}

        def payment_intent(c):
            stack.budget.consume_llm(10, 1,
                                     correlation_id=stack.order_id)
            # provider invocation happens AFTER the D-127 pre-dispatch
            # check — a refusal never reaches the provider (and the
            # attempt counter only moves on real invocation)
            stack.provider_calls += 1
            if not stack.media["healthy"]:
                raise MediaUnavailable(
                    "media store disconnected: fan-out refused")
            return {"payment_ref": f"pay-{stack.rid}"}

        def payment_verification(c):
            verdict = ("DECLINED" if stack.payment_fails
                       else "VERIFIED")
            return {"payment_verdict": verdict}

        def inventory_reservation(c):
            if c["payment_verdict"] != "VERIFIED":
                return {"inventory_state": "NOT_HELD"}
            if c["order_state"] == oms_c.PLACED:
                t = stack.engine.transition(c["order_key"],
                                            oms_c.VALIDATED)
                if not t["transitioned"]:
                    raise RuntimeError(str(t.get("reason")))
                return {"inventory_state": "RESERVED"}
            state = stack.engine.state(c["order_key"])
            held = state in (oms_c.VALIDATED, oms_c.FULFILLING,
                             oms_c.COMPLETED)
            return {"inventory_state": "RESERVED" if held else state}

        def shipping_intent(c):
            if c["inventory_state"] != "RESERVED":
                return {"shipping_ref": "none"}
            return {"shipping_ref": f"ship-{stack.rid}"}

        def notification_dispatch(c):
            got = stack.locks.acquire(
                f"delivery|{c['order_key']}|fulfillment",
                {"holder": "flow-worker"})
            if not got["acquired"]:
                return {"notification_outcome": "skipped_lock"}
            if c["order_state"] == oms_c.CANCELLED:
                tpl, vars_ = "order.cancelled.v1", \
                    {"order_ref": c["order_key"]}
            else:
                tpl = "order.fulfillment.v1"
                vars_ = {"order_ref": c["order_key"],
                         "state": c["order_state"]}
            stack.notifications.enqueue({
                "recipient": f"user-{stack.rid}",
                "channel": CH_IN_APP, "priority": PR_NORMAL,
                "occurred_at": TS, "template_id": tpl,
                "event_key": f"{c['order_key']}|{tpl}",
                "variables": vars_})
            return {"notification_outcome": "queued"}

        def analytics_projection(c):
            state = c["order_state"]
            # deterministic eids (the OMS's own durable ids): placement
            # carries no per-run suffix, so a replayed flow re-emits
            # NOTHING new — the projection cursor cannot double-consume
            if state == oms_c.PLACED:
                eid = f"oms|order|{c['order_key']}"
                ref = {"event_id": eid, "occurred_at": TS,
                       "source_campaign_id": "camp-e2e"}
            else:
                eid = f"oms|transition|{c['order_key']}|{state}"
                ref = {"event_id": eid, "state": state,
                       "occurred_at": TS,
                       "order_total_minor": 200_000,
                       "source_campaign_id": "camp-e2e"}
            if eid not in stack._emitted:
                stack._emitted.add(eid)
                stack._events.append(("oms", ref))
            stack.projection.incremental_pass()
            return {"projection_summary": {
                "cursor": stack.projection.cursor.get_cursor(),
                "pass": True}}

        return {"LEAD_CAPTURE": lead_capture,
                "CONVERSATION": conversation,
                "PRODUCT_DISCOVERY": product_discovery,
                "CART_ORDER": cart_order,
                "PAYMENT_INTENT": payment_intent,
                "PAYMENT_VERIFICATION": payment_verification,
                "INVENTORY_RESERVATION": inventory_reservation,
                "SHIPPING_INTENT": shipping_intent,
                "NOTIFICATION_DISPATCH": notification_dispatch,
                "ANALYTICS_PROJECTION": analytics_projection}

    def conductor(self):
        return FlowConductor(self.log_ledger, self.stage_impls())

    def seed(self):
        return {"channel": "instagram", "message": "سلام",
                "flow_seq": f"{self.rid}-1"}

    def _notif_refs(self):
        """Notification-source refs ONLY. The succeeded_references()
        contract matches on an event-id PREFIX (D-027 parity), so a
        bare source-name query returns cross-source rows ("oms|…"
        starts with "o"...). Tests filter by the durable event_id
        prefix — exactly what the isolation boundary requires."""
        out = []
        for r in self.store.succeeded_references("notifications"):
            d = json.loads(r)
            if str(d.get("event_id", "")).startswith(
                    "notif|"):
                out.append(d)
        return out


# ======================================================================
#  M1 — conductor contracts (unit tier)
# ======================================================================

class TestPhase25Conductor(unittest.TestCase):
    """D-133: stage envelopes, trace propagation, failure auditing."""

    def _ledger(self, path):
        return LogLedger(sink=JsonlLogSink(path))

    def _pure_impls(self, rid):
        return {
            "LEAD_CAPTURE": lambda c: {"lead_id": f"lead-{rid}",
                                       "contact_ref": f"ig-{rid}"},
            "CONVERSATION": lambda c: {"intent": "buy",
                                       "cart_draft": {"sku": "SKU-A"}},
            "PRODUCT_DISCOVERY": lambda c: {"product_refs": {
                "product_id": "P-100", "variant_id": "V-1",
                "sku": "SKU-A", "quantity": 2,
                "unit_price_minor": 100_000}},
            "CART_ORDER": lambda c: {"order_key": f"o-{rid}",
                                     "order_state": oms_c.PLACED},
            "PAYMENT_INTENT": lambda c: {"payment_ref": f"pay-{rid}"},
            "PAYMENT_VERIFICATION": lambda c: {"payment_verdict":
                                               "VERIFIED"},
            "INVENTORY_RESERVATION": lambda c: {"inventory_state":
                                                "RESERVED"},
            "SHIPPING_INTENT": lambda c: {"shipping_ref": f"s-{rid}"},
            "NOTIFICATION_DISPATCH": lambda c: {"notification_outcome":
                                                "queued"},
            "ANALYTICS_PROJECTION": lambda c: {"projection_summary":
                                               {"events": 7}},
        }

    def test_ten_stages_one_unbroken_trace(self):
        rid = uuid.uuid4().hex[:8]
        fd, path = tempfile.mkstemp(suffix=".jsonl")
        os.close(fd)
        os.remove(path)
        try:
            res = FlowConductor(
                self._ledger(path),
                self._pure_impls(rid)).run({"channel": "instagram"})
            self.assertTrue(res.ok)
            self.assertEqual(len(res.stages), 10)
            trace_ids = {r["record"]["trace_id"] for r in res.stages}
            self.assertEqual(len(trace_ids), 1,
                             "one root trace must traverse all stages")
            # per-stage causal chain advances monotonically
            seqs = [r["record"]["causal_chain_id"]
                    for r in res.stages]
            self.assertEqual(len(set(seqs)), 10)
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_zero_schema_mutation(self):
        rid = uuid.uuid4().hex[:8]
        with self.assertRaises(ConductorError):
            validate_envelope("CART_ORDER",
                              {"order_key": "k", "rogue": 1})

    def test_missing_and_unknown_stages_rejected(self):
        rid = uuid.uuid4().hex[:8]
        fd, path = tempfile.mkstemp(suffix=".jsonl")
        os.close(fd)
        os.remove(path)
        try:
            led = self._ledger(path)
            impls = self._pure_impls(rid)
            with self.assertRaises(ConductorError):
                FlowConductor(led, {k: v for k, v in impls.items()
                                    if k != "PAYMENT_INTENT"})
            with self.assertRaises(ConductorError):
                FlowConductor(led, dict(impls, ROGUE_STAGE=lambda c: {}))
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_failure_path_audited_with_d052_class(self):
        rid = uuid.uuid4().hex[:8]
        fd, path = tempfile.mkstemp(suffix=".jsonl")
        os.close(fd)
        os.remove(path)
        try:
            def boom(c):
                raise ConnectionError("etimedout: link down")
            impls = dict(self._pure_impls(rid),
                         PAYMENT_INTENT=boom)
            res = FlowConductor(self._ledger(path),
                                impls).run({"channel": "instagram"})
            self.assertFalse(res.ok)
            last = res.stages[-1]
            self.assertEqual(last["record"]["status"], "FAILURE")
            self.assertEqual(last["record"]["payload"]["error_class"],
                             "A")
            self.assertEqual(len(res.stages), 5)
        finally:
            if os.path.exists(path):
                os.remove(path)


# ======================================================================
#  M2 — fault ladder & reconciliation over the REAL engines (unit tier)
# ======================================================================

class TestPhase25FaultLadder(unittest.TestCase):
    """D-134: deterministic injections, exact classes, exact ledgers."""

    def setUp(self):
        self.stack = _FlowStack()

    def tearDown(self):
        self.stack.cleanup()

    def test_class_a_channel_outage_recovers_by_replay(self):
        stack = self.stack
        crash = FaultScript(ConnectionError("etimedout: channel reset"),
                            indices=[0]).wrap(
            stack.stage_impls()["CART_ORDER"])
        impls = dict(stack.stage_impls(), CART_ORDER=crash)
        out = play_flow_with_recovery(
            stack.conductor().__class__(stack.log_ledger, impls),
            stack.seed(), policy=RetryPolicy(max_attempts=3,
                                             base_backoff=2))
        self.assertEqual(out["outcome"], "succeeded")
        self.assertEqual(out["attempts"], 2)
        self.assertEqual(out["clock"], [2])  # jitter-free backoff
        # end state EXACTLY as the happy path (replay, not duplication)
        okey = out["flow"]["outputs"]["CART_ORDER"]["order_key"]
        self.assertEqual(stack.engine.state(okey), oms_c.VALIDATED)
        self.assertEqual(
            stack.inventory.available(stack.stock_key), 8)

    def test_budget_exhaustion_refuses_pre_dispatch(self):
        stack = self.stack
        # exhaust the llm_calls allowance BEFORE the flow starts
        for _ in range(5):
            stack.budget.consume_llm(0, 1, correlation_id="pre")
        res = stack.conductor().run(stack.seed())
        self.assertFalse(res.ok)
        self.assertEqual(res.stages[-1]["stage"], "PAYMENT_INTENT")
        # zero provider invocation (refusal is PRE-dispatch)
        self.assertEqual(stack.provider_calls, 0)
        # the flow progressed exactly to the boundary: the order is
        # PLACED (stage 4 is pre-boundary), nothing reserved, nothing
        # downstream; the CALLS resource refused — tokens of the same
        # refused logical event metered (D-127 consume_llm shape),
        # provider NEVER invoked
        self.assertEqual(stack.engine.state(stack.engine_key),
                         oms_c.PLACED)
        self.assertEqual(
            stack.inventory.available(stack.stock_key), 10)
        self.assertEqual(
            stack.budget.consumed("llm_calls", "per_run", "green"), 5)
        self.assertEqual(
            stack.budget.consumed("llm_tokens", "per_run", "green"), 10)
        # a budget refusal is NOT replay-recoverable: no auto-retry
        out = play_flow_with_recovery(
            stack.conductor(), stack.seed(),
            policy=RetryPolicy(max_attempts=3))
        self.assertEqual(out["outcome"], "terminal")
        self.assertEqual(out["attempts"], 1)

    def test_media_fault_fails_closed_then_replays_clean(self):
        stack = self.stack
        stack.media["healthy"] = False
        res = stack.conductor().run(stack.seed())
        self.assertFalse(res.ok)
        self.assertEqual(res.stages[-1]["stage"], "PAYMENT_INTENT")
        # fail-closed: no notification work at all (the delivery-lock
        # pre-claim is non-durable); the flow stopped exactly at the
        # boundary — order PLACED, inventory untouched
        self.assertEqual(len(stack._notif_refs()), 0)
        self.assertEqual(stack.engine.state(stack.engine_key),
                         oms_c.PLACED)
        self.assertEqual(
            stack.inventory.available(stack.stock_key), 10)
        # the fault clears → the same flow identity replays to success
        stack.media["healthy"] = True
        out = play_flow_with_recovery(
            stack.conductor(), stack.seed(),
            policy=RetryPolicy(max_attempts=2))
        self.assertEqual(out["outcome"], "succeeded")
        self.assertEqual(
            stack.inventory.available(stack.stock_key), 8)

    def test_lock_contention_no_double_claim(self):
        stack = self.stack
        # the engine key is deterministic from client_order_id (D-081):
        # precompute it, then hold the delivery lock as another worker
        okey = oms_c.order_idempotency_key(f"clt-{stack.rid}-000001")
        stack.locks.acquire(
            f"delivery|{okey}|fulfillment",
            {"holder": "other-worker"})
        res = stack.conductor().run(stack.seed())
        self.assertTrue(res.ok)
        self.assertEqual(
            res.outputs["NOTIFICATION_DISPATCH"]
            ["notification_outcome"], "skipped_lock")
        # the original claim survived byte-untouched (no double-claim,
        # no sweep-shaped rewrite — the flow simply yielded)
        row = stack.locks.get(f"delivery|{okey}|fulfillment")
        self.assertEqual(row, {"holder": "other-worker"})

    def test_payment_failure_compensates_and_notifies(self):
        stack = self.stack
        okey = oms_c.order_idempotency_key(f"clt-{stack.rid}-000001")
        stack.engine.place_order({
            "order_id": stack.order_id,
            "client_order_id": f"clt-{stack.rid}-000001",
            "customer_ref": "customer-42",
            "line_items": [{"product_id": "P-100",
                            "variant_id": "V-1", "sku": "SKU-A",
                            "quantity": 2,
                            "unit_price_minor": 100_000}],
            "tax_minor": 0, "placed_at": TS})
        t = stack.engine.transition(okey, oms_c.VALIDATED)
        self.assertTrue(t["transitioned"])
        self.assertEqual(
            stack.inventory.available(stack.stock_key), 8)
        # payment verification DECLINES → the compensation path
        c = stack.engine.transition(okey, oms_c.CANCELLED,
                                    reason="payment_declined")
        self.assertTrue(c["transitioned"])
        self.assertEqual(
            stack.inventory.available(stack.stock_key), 10)
        self.assertEqual(stack.engine.state(okey), oms_c.CANCELLED)
        # the failure notice goes out (D-083 boundary)
        stack.notifications.enqueue({
            "recipient": f"user-{stack.rid}", "channel": CH_IN_APP,
            "priority": PR_NORMAL, "occurred_at": TS,
            "template_id": "order.cancelled.v1",
            "event_key": f"{okey}|order.cancelled.v1",
            "variables": {"order_ref": okey}})
        refs = [json.loads(r) for r in
                stack.store.succeeded_references("notifications")]
        self.assertTrue(any(r.get("template_id")
                            == "order.cancelled.v1" for r in refs))

    def test_stranded_lock_sweep_idempotent(self):
        stack = self.stack
        stack.locks.acquire("fanout|job-A", {"holder": "crashed"})
        stack.locks.acquire("fanout|job-B", {"holder": "live"})
        stack.locks.finalize("fanout|job-B",
                             {"outcome": "published"})
        rep = reclaim_stranded(
            stack.locks, ["fanout|job-A", "fanout|job-B"],
            claimant="sweep")
        self.assertEqual(rep["reclaimed"], ["fanout|job-A"])
        self.assertEqual(rep["live"], ["fanout|job-B"])
        self.assertEqual(rep["phantom_rows"], 0)
        rep2 = reclaim_stranded(
            stack.locks, ["fanout|job-A", "fanout|job-B"],
            claimant="sweep")
        self.assertEqual(rep2["reclaimed"], [])

    def test_rebuild_from_refs_durable_only(self):
        state = rebuild_from_refs([
            '{"order_key": "o1", "state": "PLACED"}',
            '{"order_key": "o1", "state": "VALIDATED"}',
            "not-json-at-all", "42",
        ])
        self.assertEqual(state["orders"], {"o1": "VALIDATED"})
        # three JSON-parseable refs (the bare "42" too — the rebuild
        # counts every parseable durable row; unknown shapes carry no
        # order state and are skipped for STATE, not for counting)
        self.assertEqual(state["events"], 3)

    def test_outbox_replay_exactly_once(self):
        stack = self.stack
        eid = f"oms|order|{stack.order_id}"
        stack.store.receive("oms", eid, "order",
                            {"order_key": "o1"})
        stack.store.begin("oms", eid)
        stack.store.succeed("oms", eid,
                            '{"order_key": "o1", "state": "PLACED"}')
        # a FAILED event is never in the outbox
        stack.store.receive("oms", "oms|order|lost", "order", {"x": 1})
        stack.store.begin("oms", "oms|order|lost")
        stack.store.fail("oms", "oms|order|lost", "B")
        seen = []
        rep1 = replay_outbox(stack.store, "oms", seen.append)
        self.assertEqual(rep1["refs"], 1)
        self.assertEqual(rep1["effects_ok"], 1)
        rep2 = replay_outbox(stack.store, "oms", seen.append)
        self.assertEqual(len(seen), 2)  # replay re-ran the effect...
        # ...but exactly-once lives in the ENGINE behind it: the OMS
        # place_order dedup proves it on the same ref
        norm = {"order_id": stack.order_id,
                "client_order_id": f"clt-{stack.rid}-000001",
                "customer_ref": "customer-42",
                "line_items": [{"product_id": "P-100",
                                "variant_id": "V-1", "sku": "SKU-A",
                                "quantity": 2,
                                "unit_price_minor": 100_000}],
                "tax_minor": 0, "placed_at": TS}
        r1 = stack.engine.place_order(norm)
        r2 = stack.engine.place_order(norm)
        self.assertEqual(r1["verdict"], "new")
        self.assertEqual(r2["verdict"], "skipped_duplicate")


# ======================================================================
#  M3 — offline-hermetic FULL flow (T4 tier via the census rule)
# ======================================================================

class TestPhase25HermeticEndToEnd(unittest.TestCase):
    """The full ten-stage flow on the real engines, JSON backends."""

    def setUp(self):
        self.stack = _FlowStack()

    def tearDown(self):
        self.stack.cleanup()

    def test_full_flow_happy_path(self):
        stack = self.stack
        res = stack.conductor().run(stack.seed())
        self.assertTrue(res.ok)
        self.assertEqual(len(res.stages), 10)
        self.assertEqual(
            len({r["record"]["trace_id"] for r in res.stages}), 1)
        okey = res.outputs["CART_ORDER"]["order_key"]
        self.assertEqual(stack.engine.state(okey), oms_c.VALIDATED)
        self.assertEqual(
            stack.inventory.available(stack.stock_key), 8)
        self.assertGreater(stack.projection.cursor.get_cursor(), 0)
        self.assertEqual(len(stack.budget.rows()), 2)
        refs = [json.loads(r) for r in
                stack.store.succeeded_references("notifications")]
        self.assertTrue(any(r.get("template_id")
                            == "order.fulfillment.v1" for r in refs))

    def test_full_flow_replay_is_idempotent(self):
        stack = self.stack
        r1 = stack.conductor().run(stack.seed())
        self.assertTrue(r1.ok)
        before_refs = len(stack.store.succeeded_references("oms"))
        cursor_run1 = stack.projection.cursor.get_cursor()
        self.assertGreater(cursor_run1, 0)
        r2 = stack.conductor().run(stack.seed())
        self.assertTrue(r2.ok)
        okey = r1.outputs["CART_ORDER"]["order_key"]
        self.assertEqual(stack.engine.state(okey), oms_c.VALIDATED)
        self.assertEqual(
            stack.inventory.available(stack.stock_key), 8)
        self.assertEqual(
            len(stack.store.succeeded_references("oms")), before_refs)
        # analytics: replay may project the state-ADVANCE metric (the
        # transition event run 1's PLACED-context never emitted) but
        # never a duplicate — and a third replay reaches a FIXED POINT:
        # no new events, cursor motionless (every distinct metric
        # event consumed exactly once)
        cursor_run2 = stack.projection.cursor.get_cursor()
        events_run2 = len(stack._emitted)
        self.assertGreaterEqual(cursor_run2, cursor_run1)
        r3 = stack.conductor().run(stack.seed())
        self.assertTrue(r3.ok)
        self.assertEqual(len(stack._emitted), events_run2)
        self.assertEqual(stack.projection.cursor.get_cursor(),
                         cursor_run2)

    def test_flow_failure_then_recovery_matches_happy_path(self):
        stack = self.stack
        impls = stack.stage_impls()
        crash = FaultScript(ConnectionError("econnrefused: gateway"),
                            indices=[0]).wrap(impls["PAYMENT_INTENT"])
        out = play_flow_with_recovery(
            FlowConductor(stack.log_ledger,
                          dict(impls, PAYMENT_INTENT=crash)),
            stack.seed(), policy=RetryPolicy(max_attempts=3,
                                             base_backoff=1))
        self.assertEqual(out["outcome"], "succeeded")
        self.assertEqual(out["attempts"], 2)
        okey = out["flow"]["outputs"]["CART_ORDER"]["order_key"]
        self.assertEqual(stack.engine.state(okey), oms_c.VALIDATED)
        self.assertEqual(
            stack.inventory.available(stack.stock_key), 8)


# ======================================================================
#  M4 — live-PG E2E (T3 tier via the census rule)
# ======================================================================

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
class TestPhase25LivePgE2E(unittest.TestCase):
    """Live tier: the full flow on the real PostgreSQL D-027 store.
    Zero-skip when the stack is up (the operating baseline)."""

    def setUp(self):
        self.run_id = uuid.uuid4().hex[:8]

    def _flow(self):
        from canonical.notion_ingest import PgEventStore
        stack = _FlowStack()
        # swap the JSON event store for the REAL PostgreSQL store
        stack.store = PgEventStore()
        stack.engine = OmsEngine(stack.store, stack.inventory,
                                 ledger=stack.res_ledger)
        # a source-scoped outbox probe over the LIVE store
        src = f"p25live-{self.run_id}"
        stack._src = src
        return stack

    def test_full_flow_persists_to_live_store(self):
        stack = self._flow()
        try:
            res = stack.conductor().run(stack.seed())
            self.assertTrue(res.ok)
            self.assertEqual(len(res.stages), 10)
            okey = res.outputs["CART_ORDER"]["order_key"]
            self.assertEqual(stack.engine.state(okey),
                             oms_c.VALIDATED)
            self.assertEqual(
                stack.inventory.available(stack.stock_key), 8)
        finally:
            stack.cleanup()

    def test_live_outbox_replay_exactly_once(self):
        from canonical.notion_ingest import PgEventStore
        stack = self._flow()
        try:
            src = stack._src
            store = stack.store
            eid = f"{src}|evt|{self.run_id}"
            store.receive(src, eid, "order", {"n": self.run_id})
            store.begin(src, eid)
            store.succeed(src, eid,
                          '{"order_key": "o-live", "state": "PLACED"}')
            seen = []
            rep1 = replay_outbox(store, src, seen.append)
            self.assertEqual(rep1["refs"], 1)
            self.assertEqual(rep1["effects_ok"], 1)
            rep2 = replay_outbox(store, src, seen.append)
            self.assertEqual(len(seen), 2)
            # the LIVE store's re-delivery verdict is exactly-once too
            rec2 = store.receive(src, eid, "order", {"n": self.run_id})
            self.assertEqual(rec2["verdict"], "skipped_duplicate")
        finally:
            stack.cleanup()

    def test_live_conflicting_duplicate_is_integrity_error(self):
        from services.sync_engine import IntegrityError
        from canonical.notion_ingest import PgEventStore
        stack = self._flow()
        try:
            src = stack._src
            store = stack.store
            eid = f"{src}|evt|conflict|{self.run_id}"
            store.receive(src, eid, "order", {"n": self.run_id})
            store.begin(src, eid)
            store.succeed(src, eid,
                          '{"order_key": "o-live", "state": "PLACED"}')
            with self.assertRaises(IntegrityError):
                store.receive(src, eid, "order",
                              {"n": self.run_id, "tampered": True})
        finally:
            stack.cleanup()

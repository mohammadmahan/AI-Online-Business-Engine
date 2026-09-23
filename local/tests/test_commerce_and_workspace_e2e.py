"""Phase 13–16 commerce & workspace sync — E2E battery.

Covers the Phase 13/14/15/16 facade layer composing the canonical
engines (D-081/D-082 OMS, D-027 store, D-060 Notion contracts, D-142
memory):

  Part A — CommerceSyncOrchestrator: WooCommerce webhook ingestion with
  HMAC fail-closed verification, idempotent order intake into the
  canonical OMS lifecycle, outbound transition sync with D-052 error
  classification, refund routing through the lifecycle.
  Part B — NotionReplicationAdapter: injected-provider fail-closed
  submission through the canonical ingest path, backpressure,
  redacted payload builders.
  Part C — SupportKnowledgeIndex / SupportMemoryBridge: knowledge
  embedding with pre-embedding redaction, semantic retrieval, SSOT
  order context, deterministic template fallback on any failure,
  D-127 budget gating, zero secret leakage.

Everything hermetic: no network, no wall clock, no credentials.
"""
from __future__ import annotations

import hashlib
import hmac
import importlib
import json
import os
import queue
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
for p in (os.path.join(REPO, "local"), os.path.join(REPO, "local",
                                                    "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

from services.sync_engine import EventStore  # noqa: E402
from canonical.oms_engine import JsonInventory, OmsEngine  # noqa: E402
from canonical.oms_contracts import (  # noqa: E402
    OmsContractError, REFUNDED,
)
from canonical.budget_engine import BudgetLedger  # noqa: E402
from canonical.budget_contracts import ResourceBudget  # noqa: E402

from src.commerce.sync_orchestrator import (  # noqa: E402
    CommerceSyncOrchestrator, NotionReplicationService, WooWebhookError,
    _payload_fingerprint,
)
from src.integrations.notion_adapter import (  # noqa: E402
    NotionFacadeError, NotionReplicationAdapter,
)
from src.commerce.support_memory_bridge import (  # noqa: E402
    SupportKnowledgeIndex, SupportMemoryBridge,
)
from src.memory.vector_store import (  # noqa: E402
    DEFAULT_EMBEDDING_DIM, VectorStore,
)

_WOO_SECRET = "whsec_" + "t" * 24
_CANARY = "sk-" + "x" * 24


def _sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), body,
                    hashlib.sha256).hexdigest()


def _embed(text: str):
    h = hashlib.sha256(text.encode("utf-8")).digest()
    raw = (h * ((DEFAULT_EMBEDDING_DIM // len(h)) + 1))[:DEFAULT_EMBEDDING_DIM]
    return [b / 255.0 for b in raw]


def _woo_payload(**over) -> dict:
    p = {
        "order_id": "W1001", "client_order_id": "W1001001",
        "customer_ref": "cust-77", "placed_at": "2026-09-22T00:00:00Z",
        "line_items": [{"product_id": "prod-1", "variant_id": "variant-1",
                        "sku": "SKU-001", "quantity": 2,
                        "unit_price_minor": 950}],
    }
    p.update(over)
    return p


def _signed(payload: dict, secret: str = _WOO_SECRET):
    body = json.dumps(payload, sort_keys=True).encode("utf-8")
    return body, _sign(secret, body)


class _Stack:
    """Fresh hermetic OMS stack per test."""

    def __init__(self, stock: int = 10):
        tmp = tempfile.mkdtemp(prefix="commerce-e2e-")
        self.store = EventStore(os.path.join(tmp, "events.json"))
        self.inventory = JsonInventory(os.path.join(tmp, "inv.json"))
        self.inventory.seed("variant-1", "SKU-001", stock)
        self.oms = OmsEngine(self.store, self.inventory)


class _MirrorExec:
    """In-process executor mirroring VectorStore's parameterized SQL —
    an pg-mirror good enough for hermetic KNN + rows()."""

    def __init__(self):
        self.rows: dict = {}

    def __call__(self, sql, params):
        if "INSERT INTO" in sql or "DELETE FROM" in sql:
            if "INSERT INTO" in sql:
                self.rows[params[0]] = dict(zip(
                    ("record_id", "agent_id", "session_id", "kind",
                     "content", "embedding", "logical_ts", "seq"), params))
            return []
        if "ORDER BY embedding" in sql:
            vals = sorted(
                self.rows.values(),
                key=lambda r: sum((a - b) ** 2 for a, b in zip(
                    r["embedding"], params[0])))
            return [dict(r, distance=0.0) for r in vals[:params[-1]]]
        out = list(self.rows.values())
        if "AND kind = %s" in sql:
            out = [r for r in out if r["kind"] == params[0]]
        return out


# ---------------------------------------------------------------------------
# Part A — WooCommerce webhooks (Phase 13)
# ---------------------------------------------------------------------------

class TestWooWebhooks(unittest.TestCase):
    def test_01_unverified_webhook_refused(self):
        s = _Stack()
        orch = CommerceSyncOrchestrator(s.oms, secret=_WOO_SECRET)
        with self.assertRaises(WooWebhookError):
            orch.ingest_order_webhook(_woo_payload())  # no proof offered
        bad_body, _ = _signed(_woo_payload())
        with self.assertRaises(WooWebhookError):
            orch.ingest_order_webhook(
                _woo_payload(), raw_body=bad_body, signature="0" * 64)
        self.assertIsNone(s.oms.state("W1001"))

    def test_02_verified_accept_enters_oms_lifecycle(self):
        s = _Stack()
        orch = CommerceSyncOrchestrator(s.oms, secret=_WOO_SECRET)
        body, sig = _signed(_woo_payload())
        r = orch.ingest_order_webhook(_woo_payload(),
                                      raw_body=body, signature=sig)
        self.assertTrue(r["accepted"])
        self.assertEqual(r["outcome"], "accepted")
        self.assertEqual(r["state"], "PLACED")
        self.assertEqual(s.oms.state(r["order_key"]), "PLACED")

    def test_03_replay_is_duplicate_never_second_mutation(self):
        s = _Stack()
        orch = CommerceSyncOrchestrator(s.oms, secret=_WOO_SECRET)
        body, sig = _signed(_woo_payload())
        r1 = orch.ingest_order_webhook(_woo_payload(),
                                       raw_body=body, signature=sig)
        r2 = orch.ingest_order_webhook(_woo_payload(),
                                       raw_body=body, signature=sig)
        self.assertTrue(r1["accepted"])
        self.assertEqual(r2["outcome"], "duplicate")
        # exactly one durable order event (result_reference rows are
        # the persisted JSON blobs of succeeded oms events)
        refs = s.store.succeeded_references("oms")
        order_rows = [r for r in refs
                      if isinstance(r, str) and "oms|order|" in r]
        self.assertEqual(len(order_rows), 1)

    def test_04_conflicting_payload_same_order_id(self):
        s = _Stack()
        orch = CommerceSyncOrchestrator(s.oms, secret=_WOO_SECRET)
        body, sig = _signed(_woo_payload())
        orch.ingest_order_webhook(_woo_payload(), raw_body=body,
                                  signature=sig)
        bad = _woo_payload(line_items=[dict(
            _woo_payload()["line_items"][0], quantity=99)])
        b2, s2 = _signed(bad)
        r = orch.ingest_order_webhook(bad, raw_body=b2, signature=s2)
        self.assertFalse(r["accepted"])
        self.assertEqual(r["outcome"], "conflict")

    def test_05_malformed_payload_rejected(self):
        s = _Stack()
        orch = CommerceSyncOrchestrator(s.oms, secret=_WOO_SECRET)
        body, sig = _signed(_woo_payload(line_items=[]))
        with self.assertRaises(WooWebhookError):
            orch.ingest_order_webhook(_woo_payload(line_items=[]),
                                      raw_body=body, signature=sig)
        body2, sig2 = _signed(_woo_payload(order_id="x"))
        r2 = orch.ingest_order_webhook(_woo_payload(order_id="x"),
                                       raw_body=body2, signature=sig2)
        self.assertEqual(r2["outcome"], "invalid")

    def test_06_fingerprint_is_order_intent_stable(self):
        a = _payload_fingerprint(_woo_payload())
        b = _payload_fingerprint(_woo_payload(placed_at="other-time"))
        self.assertEqual(a, b)  # addressing fields only
        c = _payload_fingerprint(_woo_payload(line_items=[dict(
            _woo_payload()["line_items"][0], quantity=5)]))
        self.assertNotEqual(a, c)


# ---------------------------------------------------------------------------
# Part A — SSOT → Woo transitions (Phase 13/15)
# ---------------------------------------------------------------------------

class TestOutboundTransitions(unittest.TestCase):
    def test_07_full_lifecycle_with_failing_transport(self):
        s = _Stack()
        calls = []

        def boom(req):
            calls.append(req)
            raise ConnectionError(
                f"net down token={_CANARY}")

        orch = CommerceSyncOrchestrator(s.oms, secret=_WOO_SECRET,
                                        transport=boom)
        body, sig = _signed(_woo_payload())
        acc = orch.ingest_order_webhook(_woo_payload(),
                                        raw_body=body, signature=sig)
        key = acc["order_key"]
        rt = orch.push_transition_to_woo(key, "VALIDATED")
        self.assertTrue(rt["transitioned"])
        self.assertTrue(rt["sync_outcome"].startswith("sync_failed:"))
        self.assertEqual(s.oms.state(key), "VALIDATED")  # SSOT committed
        self.assertNotIn(_CANARY, str(rt["sync_detail"]))  # D-124
        rf = orch.push_transition_to_woo(key, "FULFILLING")
        self.assertEqual(s.oms.state(key), "FULFILLING")
        rc = orch.push_transition_to_woo(
            key, "COMPLETED",
            fulfillment_receipt={"carrier": "t", "tracking": "TRK-1"})
        self.assertEqual(s.oms.state(key), "COMPLETED")
        rr = orch.push_refund(key)
        self.assertEqual(rr["transitioned"], True)
        self.assertEqual(rr["state"], REFUNDED)
        self.assertTrue(rr["sync_outcome"].startswith("sync_failed:"))

    def test_08_illegal_transition_raises_canonical_class_b(self):
        s = _Stack()
        orch = CommerceSyncOrchestrator(s.oms, secret=_WOO_SECRET)
        body, sig = _signed(_woo_payload())
        acc = orch.ingest_order_webhook(_woo_payload(),
                                        raw_body=body, signature=sig)
        with self.assertRaises(OmsContractError):
            orch.push_transition_to_woo(acc["order_key"], "COMPLETED")

    def test_09_transport_success_reports_synced(self):
        s = _Stack()
        seen = []

        def ok(req):
            seen.append(req)
            return {"status": 200}

        orch = CommerceSyncOrchestrator(s.oms, secret=_WOO_SECRET,
                                        transport=ok)
        body, sig = _signed(_woo_payload())
        acc = orch.ingest_order_webhook(_woo_payload(),
                                        raw_body=body, signature=sig)
        rt = orch.push_transition_to_woo(acc["order_key"], "VALIDATED")
        self.assertTrue(rt["synced_to_woo"])
        self.assertEqual(rt["sync_outcome"], "synced")
        self.assertEqual(len(seen), 1)
        self.assertNotIn(_WOO_SECRET, seen[0].decode("utf-8"))

    def test_10_no_transport_is_honest_degradation(self):
        s = _Stack()
        orch = CommerceSyncOrchestrator(s.oms, secret=_WOO_SECRET)
        body, sig = _signed(_woo_payload())
        acc = orch.ingest_order_webhook(_woo_payload(),
                                        raw_body=body, signature=sig)
        rt = orch.push_transition_to_woo(acc["order_key"], "VALIDATED")
        self.assertTrue(rt["transitioned"])
        self.assertFalse(rt["synced_to_woo"])
        self.assertEqual(rt["sync_outcome"], "degraded:no_transport")

    def test_11_inventory_guard_blocks_validation(self):
        s = _Stack(stock=1)
        orch = CommerceSyncOrchestrator(s.oms, secret=_WOO_SECRET)
        body, sig = _signed(_woo_payload())  # wants 2, stock 1
        acc = orch.ingest_order_webhook(_woo_payload(),
                                        raw_body=body, signature=sig)
        rt = orch.push_transition_to_woo(acc["order_key"], "VALIDATED")
        self.assertFalse(rt["transitioned"])
        self.assertEqual(rt["reason"], "insufficient_stock")
        self.assertEqual(s.oms.state(acc["order_key"]), "PLACED")


# ---------------------------------------------------------------------------
# Part B — Notion workspace replication (Phase 14)
# ---------------------------------------------------------------------------

class TestNotionReplication(unittest.TestCase):
    def test_12_no_provider_refuses_d045(self):
        a = NotionReplicationAdapter()  # offline builder-only adapter
        p = a.build_order_payload(
            {"order_id": "W-1", "state": "PLACED",
             "customer_ref": "cust-9", "line_items": [{}]},
            page_id="aabbccddeeff0011", marker="m-1")
        with self.assertRaises(NotionFacadeError):
            a.submit(p)
        with self.assertRaises(NotionFacadeError):
            a.poll_cycle()

    def test_13_payload_builders_canonical_shape_redacted(self):
        a = NotionReplicationAdapter()
        p = a.build_order_payload(
            {"order_id": "W-1", "state": "PLACED",
             "customer_ref": "cust-9", "line_items": [{}, {}]},
            page_id="aabbccddeeff0011", marker="m-1")
        self.assertEqual(p["event_type"], "campaign_updated")
        self.assertEqual(p["object"], "campaign")
        self.assertEqual(p["page_id"], "aabbccddeeff0011")
        blob = json.dumps(p)
        self.assertNotIn(_CANARY, blob)
        with self.assertRaises(NotionFacadeError):
            a.build_task_payload({"title": "t"}, page_id="nope", marker="m")
        a.build_catalog_payload({"sku": "S-1", "title": "T", "stock": 3},
                                page_id="aabbccddeeff0011", marker="m-2")

    def test_14_submit_via_canonical_ingest_idempotent(self):
        tmp = tempfile.mkdtemp(prefix="commerce-e2e-")
        store = EventStore(os.path.join(tmp, "events.json"))
        a = NotionReplicationAdapter(provider=object(), store=store)
        p = a.build_order_payload(
            {"order_id": "W-1", "state": "PLACED",
             "customer_ref": "cust-9", "line_items": [{}]},
            page_id="aabbccddeeff0011", marker="m-1")
        r1 = a.submit(p)
        self.assertEqual(r1["status"], "succeeded")
        self.assertTrue(r1["accepted"])
        r2 = a.submit(p)
        self.assertEqual(r2["status"], "skipped_duplicate")

    def test_15_backpressure_fails_closed(self):
        tmp = tempfile.mkdtemp(prefix="commerce-e2e-")
        store = EventStore(os.path.join(tmp, "events.json"))
        q = queue.Queue()
        a = NotionReplicationAdapter(provider=object(), store=store,
                                     queue=q, max_queue=2)
        p = a.build_order_payload(
            {"order_id": "W-1", "state": "PLACED"},  # type: ignore
            page_id="aabbccddeeff0011", marker="m-1")
        # (order_ref lacks line_items — fine for the builder)
        q.put({"full": True})
        q.put({"full": True})
        r = a.submit(p)
        self.assertEqual(r["reason"], "backpressure")
        self.assertFalse(r["accepted"])

    def test_16_poll_delegates_to_canonical_poller(self):
        class _Provider:
            def fetch_events(self, batch_size=100, **kw):
                return []

        a = NotionReplicationAdapter(provider=_Provider())
        r = a.poll_cycle()
        self.assertEqual(r["ingested"], [])
        svc = NotionReplicationService(poller=a.poller())
        self.assertEqual(svc.poll()["ingested"], [])
        self.assertEqual(svc.backlog(), 0)


# ---------------------------------------------------------------------------
# Part C — support memory bridge (Phase 16 × D-142)
# ---------------------------------------------------------------------------

class _BridgeHarnessMixin:
    """Hermetic support-bridge harness shared by test classes.
    (Mixin only — contributes no tests of its own.)"""

    def _bridge(self, stack=None, budget=None, order_lookup=None,
                router=None):
        store = VectorStore(_MirrorExec())
        kb = SupportKnowledgeIndex(store, _embed, budget)
        bridge = SupportMemoryBridge(store=store, embedder=_embed,
                                     order_lookup=order_lookup,
                                     budget=budget, router=router)
        return store, kb, bridge


class TestSupportMemoryBridge(_BridgeHarnessMixin, unittest.TestCase):

    def test_17_kb_ingest_and_semantic_retrieval(self):
        _, kb, bridge = self._bridge()
        out = kb.ingest([
            {"kind": "faq", "title": "Returns",
             "content": "Return window is 7 days."},
            {"kind": "product", "title": "Widget",
             "content": "Widget Pro water resistant."},
            {"kind": "policy", "title": "Shipping",
             "content": "Free shipping over 500k."},
        ], logical_ts=42)
        self.assertEqual(out["written"], 3)
        res = bridge.resolve("What is the return window?",
                             logical_ts=43)
        self.assertEqual(res["source"], "knowledge")
        self.assertIn("7 days", res["response"])

    def test_18_order_context_flows_into_resolution(self):
        seen = {}

        def lookup(ref):
            seen["ref"] = ref
            return [{"order_key": "ok-1", "state": "COMPLETED",
                     "order_id": "W-1"}]

        _, _, bridge = self._bridge(order_lookup=lookup)
        res = bridge.resolve("Where is my order?",
                             customer_ref="cust-77", logical_ts=1)
        self.assertEqual(seen["ref"], "cust-77")
        self.assertEqual(res["order_context"]["count"], 1)
        self.assertEqual(res["order_context"]["orders"][0]["state"],
                         "COMPLETED")

    def test_19_vector_failure_degrades_to_template(self):
        class Boom:
            def query(self, *a, **k):
                raise RuntimeError("boom")

        res = SupportMemoryBridge(store=Boom(), embedder=_embed).resolve(
            "hi?", customer_ref="c1")
        self.assertEqual(res["source"], "template")
        reports = res.get("reports", [])
        self.assertTrue(any(not r.ok and "degraded:RuntimeError"
                            in r.detail for r in reports))

    def test_20_order_lookup_failure_degrades_not_raises(self):
        def boom(ref):
            raise RuntimeError("oms down")

        _, _, bridge = self._bridge(order_lookup=boom)
        res = bridge.resolve("where is my order?", customer_ref="c1",
                             logical_ts=1)
        self.assertIn(res["source"], ("template", "knowledge"))
        self.assertTrue(any(r.op == "order_context" and not r.ok
                            for r in res["reports"]))

    def test_21_budget_refusal_gates_memory_hops(self):
        budget = BudgetLedger([ResourceBudget("memory_ops", 0.5,
                                              "per_run")])
        store, kb, bridge = self._bridge(budget=budget)
        out = kb.ingest([{"kind": "faq", "title": "T",
                          "content": "c"}], logical_ts=1)
        self.assertEqual(out["written"], 0)
        self.assertEqual(out["skipped"], 1)
        res = bridge.resolve("anything", logical_ts=2)
        self.assertEqual(res["source"], "template")
        self.assertTrue(any("budget_refused" in r.detail
                            for r in res["reports"]))

    def test_22_canary_never_reaches_vector_persistence(self):
        store, kb, _ = self._bridge()
        kb.ingest([{"kind": "faq", "title": "Leak",
                    "content": f"secret {_CANARY} inside"}], logical_ts=1)
        blob = json.dumps(list(store._exec.rows.values()))
        self.assertNotIn(_CANARY, blob)

    def test_23_router_receives_redacted_context(self):
        captured = {}

        def router(ctx):
            captured.update(ctx)
            return {"response": "routed", "source": "router"}

        _, kb, bridge = self._bridge(router=router)
        kb.ingest([{"kind": "faq", "title": "F",
                    "content": f"answer {_CANARY} stripped"}], logical_ts=1)
        bridge.resolve("help", customer_ref="c9", session_id="s",
                       logical_ts=2)
        self.assertEqual(captured["session_id"], "s")
        blob = json.dumps(captured, default=str)
        self.assertNotIn(_CANARY, blob)


# ---------------------------------------------------------------------------
# Part C — SSOT authority check (Phase 15)
# ---------------------------------------------------------------------------

class TestSsotAuthority(_BridgeHarnessMixin, unittest.TestCase):
    """Phase 15 authority check (shares the hermetic bridge harness)."""

    def test_24_memory_is_never_order_authority(self):
        """Order context comes from the injected SSOT lookup only; a
        poisoned knowledge base cannot fabricate order state."""
        def lookup(ref):
            return [{"order_key": "k", "state": "COMPLETED",
                     "order_id": "W-9"}]

        _, kb, bridge = self._bridge(order_lookup=lookup)
        kb.ingest([{"kind": "fulfillment", "title": "Lie",
                    "content": "order W-9 is CANCELLED"}], logical_ts=1)
        res = bridge.resolve("status of order W-9?", customer_ref="c1",
                             logical_ts=2)
        orders = res["order_context"]["orders"]
        self.assertEqual(orders[0]["state"], "COMPLETED")


if __name__ == "__main__":
    unittest.main()

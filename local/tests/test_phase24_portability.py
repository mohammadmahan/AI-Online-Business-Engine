"""Phase 24 — portability & port-swapping verification battery (D-132).

Layers:
  T1  D-129 provider conformance: shipped mock + metered variants,
      bare-SDK failure rejection, envelope drift rejection, negative
      usage rejection, D-127 write-through exactness (refusals cost
      zero, budget refusal type) — offline, deterministic.
  T2  D-130 media conformance: deterministic content addressing,
      round-trips, declared envelope (head merges declared fields,
      wall-clock storage fields pruned), put/get/delete/list matrix —
      offline over a temp-rooted LocalObjectStore.
  T3  D-131 channel registry: registration/binding validation,
      deterministic swap verdicts (logical ticks, no wall clock),
      mock/live envelope-shape parity (value drift OK, key drift
      rejected), D-121 audit records through the SHIPPED LogLedger
      (D-114-sanitized, enum-valid), hot_swap fail-closed ordering —
      offline.
  T4  D-131 channel/vendor isolation AST rule: the real canonical tree
      is clean; planted violations (function body + nested branch) are
      caught; declared homes are skipped — offline.
  T5  D-130 backend parity: the four declared pairs run BOTH legs
      against the live stack (zero-skip while Colima/Docker is up) —
      JSON parity vs real PostgreSQL; divergence = failure.
  T6  D-129 simulated provider lockout: dead 'live' primary over the
      D-066 mock fallback, observability records the isolation, the
      D-127 ledger meters the fallback exactly once — offline.

Zero network beyond loopback/psql transport (D-045); no wall clock in
any decision (D-085/D-093/D-121 precedent); run-scoped keys against
durable ledgers (the Phase 21 lesson).
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

from canonical import portability as P  # noqa: E402
from canonical import portability_bindings as B  # noqa: E402
from canonical import portability_channels as CH  # noqa: E402
from canonical.ai_runtime import (  # noqa: E402
    AiProviderError,
    AiRequest,
    MockAiProvider,
)
from canonical.budget_engine import BudgetExhausted  # noqa: E402
from canonical.obs_contracts import (  # noqa: E402
    JsonlLogSink,
    LogLedger,
    TraceContext,
)

RUN_TAG = uuid.uuid4().hex[:10]


def _req(schema_id="content_idea_proposal.v1", payload=None):
    return AiRequest(task_type=schema_id, schema_id=schema_id,
                     prompt_payload=payload or {})


# ============================================================================
# T1 — D-129 provider conformance + write-through
# ============================================================================

class TestT1ProviderConformance(unittest.TestCase):
    def test_shipped_mock_conforms(self):
        P.assert_provider_conformance(MockAiProvider())

    def test_metered_mock_conforms_and_meters_exactly(self):
        lk = B.provider_lockout_pair()
        p = lk["provider"]
        P.assert_provider_conformance(p)
        before = lk["ledger"].consumed("llm_tokens", "per_run", "green")
        r = p.generate(_req())
        after = lk["ledger"].consumed("llm_tokens", "per_run", "green")
        usage = r.usage
        self.assertEqual(after - before,
                         usage["prompt_tokens"] + usage["completion_tokens"])

    def test_bare_sdk_failure_rejected(self):
        class Bare(MockAiProvider):
            name = "mock"

            def generate(self, request):
                raise RuntimeError("raw SDK explosion")

        with self.assertRaises(P.PortabilityViolation) as ctx:
            P.assert_provider_conformance(Bare())
        self.assertIn("D-052", str(ctx.exception))

    def test_envelope_drift_rejected(self):
        class DriftName(MockAiProvider):
            name = "mock"

            def generate(self, request):
                resp = MockAiProvider.generate(self, request)
                resp.provider = "other"
                return resp

        with self.assertRaises(P.PortabilityViolation):
            P.assert_provider_conformance(DriftName())

    def test_negative_usage_rejected(self):
        class Negative(MockAiProvider):
            name = "mock"

            def generate(self, request):
                resp = MockAiProvider.generate(self, request)
                usage = dict(resp.usage)
                usage["prompt_tokens"] = -5
                resp.usage = usage
                return resp

        with self.assertRaises(P.PortabilityViolation):
            P.assert_provider_conformance(Negative())

    def test_write_through_refusal_costs_zero(self):
        from canonical.budget_contracts import ResourceBudget
        ledger = B.BudgetLedger(budgets=[
            ResourceBudget(resource="llm_calls", limit=2,
                           window="per_run", scope="green"),
            ResourceBudget(resource="llm_tokens", limit=10_000_000,
                           window="per_run", scope="green"),
        ])

        class Tiny(P.AiMeteredProvider):
            name = "tiny"

            def __init__(self):
                super().__init__()
                self._inner = MockAiProvider()
                self.ledger = ledger

            def _generate(self, request):
                return self._inner.generate(request)

        p = Tiny()
        p.generate(_req())
        p.generate(_req())
        with self.assertRaises(BudgetExhausted):
            p.generate(_req())
        self.assertEqual(ledger.consumed("llm_calls", "per_run", "green"),
                         2.0)


# ============================================================================
# T2 — D-130 media conformance
# ============================================================================

class TestT2MediaConformance(unittest.TestCase):
    def test_local_object_store_conforms(self):
        store = B.local_object_store()
        v = P.assert_media_conformance(store, blob=b"p24-battery-blob")
        self.assertTrue(v["deterministic_address"])
        self.assertTrue(v["get"])
        self.assertTrue(v["delete"])

    def test_wall_clock_pruned_from_metadata(self):
        store = B.local_object_store()
        res = store.put(b"clock-prune", "text/plain", {"k": "v"})
        with open(store._path(res["object_key"]) + ".meta.json",
                  encoding="utf-8") as fh:
            raw = json.load(fh)
        self.assertNotIn("stored_at", raw)
        self.assertEqual(set(raw),
                         {"content_type", "size", "metadata"})

    def test_head_declared_shape(self):
        store = B.local_object_store()
        res = store.put(b"head-shape", "application/json", {"a": 1})
        head = store.head(res["object_key"])
        self.assertEqual(head["content_type"], "application/json")
        self.assertEqual(head["size"], len(b"head-shape"))
        self.assertEqual(head["a"], 1)

    def test_list_matrix(self):
        store = B.local_object_store()
        r1 = store.put(b"list-1", "text/plain")
        self.assertIn(r1["object_key"], store.list())
        store.delete(r1["object_key"])
        self.assertNotIn(r1["object_key"], store.list())


# ============================================================================
# T3 — D-131 channel registry & hot-swap
# ============================================================================

class _ProbeChan(CH.ChannelAdapterContract):
    channel = "probe"

    def dispatch(self, target, envelope):
        return {"channel": self.channel,
                "routed_to": str(target.get("id")),
                "status": "SENT"}

    def health(self):
        return {"status": "ok"}


class _ProbeChanLive(_ProbeChan):
    channel = "probe"

    def dispatch(self, target, envelope):
        d = dict(super().dispatch(target, envelope))
        d["routed_to"] = "live:" + d["routed_to"]  # value drift only
        return d


class _ProbeChanShapeDrift(_ProbeChanLive):
    channel = "probe"

    def dispatch(self, target, envelope):
        d = super().dispatch(target, envelope)
        d["provider_ref"] = "X"  # extra key = shape drift
        return d


class TestT3ChannelRegistry(unittest.TestCase):
    def test_registration_validation(self):
        reg = CH.ChannelRegistry()
        reg.register("probe_mock", _ProbeChan())
        with self.assertRaises(P.PortabilityError):
            reg.register("Bad Name", _ProbeChan())

    def test_bind_requires_matching_channel(self):
        reg = CH.ChannelRegistry()
        reg.register("probe_mock", _ProbeChan())
        with self.assertRaises(P.PortabilityError):
            reg.bind("other", "probe_mock")
        with self.assertRaises(P.PortabilityError):
            reg.bind("probe", "unregistered")

    def test_swap_verdicts_deterministic(self):
        reg = CH.ChannelRegistry()
        reg.register("probe_mock", _ProbeChan())
        reg.register("probe_live", _ProbeChanLive())
        v1 = reg.bind("probe", "probe_mock")
        v2 = reg.bind("probe", "probe_live")
        v3 = reg.bind("probe", "probe_mock")
        self.assertEqual((v1.swapped_at_logical,
                          v2.swapped_at_logical,
                          v3.swapped_at_logical), (1, 2, 3))
        self.assertEqual(v2.swapped_from, "probe_mock")
        self.assertEqual(v2.swapped_to, "probe_live")
        # identical rebinds on a fresh registry are byte-identical
        reg2 = CH.ChannelRegistry()
        reg2.register("probe_mock", _ProbeChan())
        reg2.register("probe_live", _ProbeChanLive())
        reg2.bind("probe", "probe_mock")
        v2b = reg2.bind("probe", "probe_live")
        self.assertEqual(v2b, v2)

    def test_envelope_parity_value_drift_ok_key_drift_rejected(self):
        CH.assert_channel_envelope_parity(_ProbeChan(), _ProbeChanLive(),
                                          {"id": "t1"}, {"k": "v"})
        with self.assertRaises(P.PortabilityViolation):
            CH.assert_channel_envelope_parity(
                _ProbeChan(), _ProbeChanShapeDrift(), {"id": "t1"},
                {"k": "v"})

    def test_hot_swap_audits_through_shipped_ledger(self):
        reg = CH.ChannelRegistry()
        reg.register("probe_mock", _ProbeChan())
        reg.register("probe_live", _ProbeChanLive())
        path = os.path.join(tempfile.mkdtemp(prefix="p24-ledger-"),
                            f"{RUN_TAG}.jsonl")
        ledger = LogLedger(sink=JsonlLogSink(path))
        ctx = TraceContext.root("dispatch", f"portability-{RUN_TAG}", "0")
        v = CH.hot_swap(reg, "probe", "probe_live", ctx,
                        "p24-logical-001", log_ledger=ledger)
        self.assertEqual(v.swapped_to, "probe_live")
        with open(path, encoding="utf-8") as fh:
            rows = [json.loads(l) for l in fh]
        self.assertEqual(len(rows), 1)
        rec = rows[0]
        self.assertEqual(rec["schema_version"], "engine.log.v1")
        self.assertEqual(rec["domain"], "dispatch")
        self.assertEqual(rec["event"], "channel_swap")
        self.assertEqual(rec["payload"]["swapped_to"], "probe_live")
        self.assertEqual(rec["payload"]["swap_seq"], 1)
        self.assertEqual(rec["logical_at"], "p24-logical-001")

    def test_audit_failure_cannot_unswap(self):
        reg = CH.ChannelRegistry()
        reg.register("probe_mock", _ProbeChan())
        reg.register("probe_live", _ProbeChanLive())
        reg.bind("probe", "probe_mock")

        class Boom:
            def emit(self, *a, **kw):
                raise RuntimeError("audit sink down")

        with self.assertRaises(RuntimeError):
            CH.hot_swap(reg, "probe", "probe_live",
                        TraceContext.root("dispatch", "x", "0"), "t",
                        log_ledger=Boom())
        # the rebind survived — auditing is downstream of swapping
        self.assertEqual(reg.active_variant("probe"), "probe_live")


# ============================================================================
# T4 — D-131 channel/vendor isolation AST rule
# ============================================================================

class TestT4ChannelIsolationSweep(unittest.TestCase):
    def test_canonical_tree_is_clean(self):
        from canonical.security_worker import channel_isolation_scan
        rep = channel_isolation_scan(
            [os.path.join(LOCAL, "canonical")])
        self.assertTrue(rep["files_scanned"] > 50)
        self.assertEqual(rep["findings"], [])

    def test_planted_violation_is_caught(self):
        from canonical.security_worker import channel_isolation_scan
        d = tempfile.mkdtemp(prefix="p24-sweep-")
        a = os.path.join(d, "workflow_module.py")
        with open(a, "w", encoding="utf-8") as fh:
            fh.write("def route(payload):\n"
                     "    if payload.get('t') == 'telegram':\n"
                     "        return 1\n"
                     "    return 0\n")
        rep = channel_isolation_scan([d])
        self.assertFalse(rep["clean"])
        self.assertEqual(rep["findings"][0]["detail"], "'telegram'")

    def test_home_modules_are_skipped(self):
        from canonical.security_worker import channel_isolation_scan
        d = tempfile.mkdtemp(prefix="p24-sweep2-")
        with open(os.path.join(d, "telegram_contracts.py"), "w",
                  encoding="utf-8") as fh:
            fh.write("NAME = 'telegram'\n")
        rep = channel_isolation_scan([d])
        self.assertTrue(rep["clean"])


# ============================================================================
# T6 — D-129/D-066 simulated provider lockout
# ============================================================================

class TestT6ProviderLockout(unittest.TestCase):
    def test_lockout_falls_back_and_meters_once(self):
        lk = B.provider_lockout_pair()
        v = B.lockout_probe(lk["provider"], "content_idea_proposal.v1")
        self.assertEqual(v["fallbacks_used"], 1)
        self.assertEqual(v["responded_by"], "mock")
        self.assertTrue(v["schema_parsed"])
        self.assertEqual(v["ledger_calls"], 1.0)

    def test_class_b_never_masked(self):
        lk = B.provider_lockout_pair()
        p = lk["provider"]

        class StrictPrimary(MockAiProvider):
            name = "strict"

            def generate(self, request):
                raise AiProviderError("authority violation",
                                      failure_class="D")

        p.primary = StrictPrimary()
        with self.assertRaises(AiProviderError) as ctx:
            p.generate(_req())
        self.assertEqual(ctx.exception.failure_class, "D")

    def test_lockout_conforms(self):
        lk = B.provider_lockout_pair()
        P.assert_provider_conformance(lk["provider"])


# ============================================================================
# live-stack guard (T5)
# ============================================================================

def _stack_up():
    import subprocess
    try:
        out = subprocess.run(
            ["docker", "compose", "-f", "local/infra/docker-compose.yml",
             "ps", "--format", "json"], capture_output=True, text=True,
            timeout=20, cwd=ROOT)
        return out.returncode == 0 and \
            "engine-local-postgres" in out.stdout and \
            "healthy" in out.stdout
    except Exception:
        return False


@unittest.skipUnless(_stack_up(), "live PostgreSQL stack not running")
class TestT5BackendParityLivePg(unittest.TestCase):
    """The four declared D-130 pairs, BOTH legs, against real PG."""

    def test_slot_locks_pair(self):
        pair = B.slot_locks_pair(RUN_TAG + "-t5a", _stack_up)
        out = P.assert_backend_parity(
            pair, ctx={"slot": f"2026-09-18T{RUN_TAG[:2]}"})
        self.assertEqual(out["mode"], "both")

    def test_delivery_locks_pair(self):
        pair = B.delivery_locks_pair(RUN_TAG + "-t5b", _stack_up)
        out = P.assert_backend_parity(pair, ctx={})
        self.assertEqual(out["mode"], "both")

    def test_analytics_cursor_pair(self):
        pair = B.analytics_cursor_pair(RUN_TAG + "-t5c", _stack_up)
        out = P.assert_backend_parity(pair, ctx={})
        self.assertEqual(out["mode"], "both")

    def test_oms_inventory_pair(self):
        pair = B.inventory_pair(RUN_TAG + "-t5d", _stack_up)
        out = P.assert_backend_parity(pair, ctx={})
        self.assertEqual(out["mode"], "both")


if __name__ == "__main__":
    unittest.main(verbosity=2)

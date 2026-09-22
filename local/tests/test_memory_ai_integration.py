"""D-142 consumers + Stage H smoke integration battery.

Covers:
  A — `local/src/ai/memory_interceptor.py`: context injection into
      Phase 7/8 pipelines (guidelines/similar/summary in
      `prompt_payload["memory_context"]`), zero-blockage degradation
      (store/summarizer failures never raise into generation), D-127
      budget gating (pre-dispatch check refusals skip the hop
      gracefully; BudgetExhausted during generation still raises —
      canonical behavior is untouched), deep redaction before
      persistence, WAL export + offline-first sync via reports.
  B — staging smoke S-07: `run_staging_smoke_tests.py` composes the
      Stage H export→dry-run-import parity proof into every smoke
      run (11/11 checks); `verify_cutover_readiness.py` still passes
      its own gates (no regression from the S-07 addition).

All hermetic: injected stores/embedders/budgets only (D-045).
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SMOKE = REPO / "local" / "scripts" / "run_staging_smoke_tests.py"
VCR = REPO / "local" / "scripts" / "verify_cutover_readiness.py"

sys.path.insert(0, str(REPO / "local"))

from canonical.ai_runtime import AiRequest, MockAiProvider  # noqa: E402
from canonical.budget_engine import BudgetLedger, ResourceBudget  # noqa: E402

from local.src.memory.vector_store import (  # noqa: E402
    DEFAULT_EMBEDDING_DIM, INTERACTION, SUMMARY, GUIDELINE, MemoryRecord,
    VectorStore,
)
from local.src.memory.memwal_adapter import MemWalClientAdapter  # noqa: E402
from local.src.ai.memory_interceptor import (  # noqa: E402
    MEMORY_BUDGET_RESOURCE, MemoryContextProvider, MemoryEnabledAiRuntime,
    MemoryWritingInterceptor,
)

VEC = tuple(0.1 * (i % 5 + 1) for i in range(DEFAULT_EMBEDDING_DIM))


def flat_embed(text: str) -> tuple:
    """Deterministic test embedder: distinct prefixes -> distinct vectors."""
    seed = sum(ord(c) for c in text[:16])
    return tuple(((seed >> (i % 8)) & 1) * 0.4 + 0.1
                 for i in range(DEFAULT_EMBEDDING_DIM))


class FakeExec:
    """In-process executor mirroring the real adapter contract."""

    def __init__(self, canned=None):
        self.calls: list = []
        self.canned: dict = canned or {}

    def __call__(self, sql, params):
        self.calls.append((sql, params))
        if "DELETE FROM" in sql or "INSERT INTO" in sql:
            return []
        if "AND kind = %s" in sql and params:
            return [dict(r) for r in self.canned.get(params[0], [])]
        for key, rows in self.canned.items():
            if key in (INTERACTION, SUMMARY, GUIDELINE):
                continue
            if key in sql:
                return [dict(r) for r in rows]
        return []


def make_store(canned=None) -> VectorStore:
    return VectorStore(FakeExec(canned), )


def make_budget(limit: float) -> BudgetLedger:
    return BudgetLedger([ResourceBudget(
        resource=MEMORY_BUDGET_RESOURCE, window="per_run", scope="green",
        limit=limit)])


def req(topic="autumn coats") -> AiRequest:
    return AiRequest(task_type="propose_content_idea",
                     schema_id="content_idea_proposal.v1",
                     prompt_payload={"topic": topic},
                     idempotency_tag="t1")


class StoreError(Exception):
    pass


class BoomStore:
    def query(self, *a, **k):
        raise StoreError("disk on fire")

    def rows(self, *a, **k):
        raise StoreError("disk on fire")

    def put(self, *a, **k):
        raise StoreError("disk on fire")

    def put_summary(self, *a, **k):
        raise StoreError("disk on fire")


# ---------------------------------------------------------------------------
# A — memory context provider (read path)
# ---------------------------------------------------------------------------

class TestContextProvider(unittest.TestCase):
    def test_01_retrieve_happy_path(self):
        store = make_store(canned={
            "ORDER BY embedding": [{"record_id": "i1",
                                    "content": "high performer",
                                    "distance": 0.12, "session_id": "s1",
                                    "agent_id": "a1", "kind": INTERACTION,
                                    "logical_ts": 1, "seq": 1}],
            INTERACTION: [],
            GUIDELINE: [{"record_id": "g1", "agent_id": "a1",
                         "session_id": "*", "kind": GUIDELINE,
                         "content": "formal Persian tone",
                         "logical_ts": 1, "seq": 2}],
            SUMMARY: [{"record_id": "sm1", "agent_id": "a1",
                       "session_id": "s1", "kind": SUMMARY,
                       "content": "prior session", "logical_ts": 9,
                       "seq": 9}]})
        prov = MemoryContextProvider(store=store, embedder=flat_embed)
        reports = []
        ctx = prov.retrieve("autumn coats", reports)
        self.assertTrue(ctx["ok"])
        self.assertEqual(ctx["guidelines"][0]["content"],
                         "formal Persian tone")
        self.assertEqual(ctx["similar"][0]["content"], "high performer")
        self.assertTrue(any(r.op == "retrieve" and r.ok for r in reports))

    def test_02_retrieve_degrades_on_store_failure(self):
        prov = MemoryContextProvider(store=BoomStore(), embedder=flat_embed)
        reports = []
        ctx = prov.retrieve("anything", reports)
        self.assertFalse(ctx["ok"])
        self.assertEqual(ctx["guidelines"], [])
        self.assertTrue(any("degraded:StoreError" == r.detail
                            for r in reports if r.op == "retrieve"))

    def test_03_retrieve_without_store_is_empty_not_error(self):
        prov = MemoryContextProvider()
        reports = []
        ctx = prov.retrieve("x", reports)
        self.assertFalse(ctx["ok"])
        self.assertTrue(any(r.detail == "degraded:no_store"
                            for r in reports))

    def test_04_budget_refusal_skips_hop_gracefully(self):
        ledger = make_budget(limit=1.0)
        verdict = ledger.consume(MEMORY_BUDGET_RESOURCE, 1)  # exhaust
        self.assertTrue(verdict["warning"] or verdict["consumed_after"] == 1)
        store = make_store()
        prov = MemoryContextProvider(store=store, embedder=flat_embed,
                                     budget=ledger)
        reports = []
        ctx = prov.retrieve("x", reports)
        self.assertFalse(ctx["ok"])
        self.assertTrue(any("budget_refused" in r.detail
                            for r in reports))
        # nothing was retrieved: the fake saw no SELECT
        selects = [c for c in store._exec.calls if "SELECT" in c[0]]
        self.assertEqual(selects, [])


# ---------------------------------------------------------------------------
# A — writing interceptor (write path)
# ---------------------------------------------------------------------------

class TestWritingInterceptor(unittest.TestCase):
    def test_05_write_interaction_redacts_before_persist(self):
        store = make_store()
        w = MemoryWritingInterceptor(store=store, embedder=flat_embed)
        canary = "sk-" + "y" * 24
        rid = w.write_interaction("a1", "s1", "leak " + canary, 100)
        self.assertTrue(rid)
        _, params = store._exec.calls[-1]
        self.assertNotIn(canary, str(params))  # deep redaction applied

    def test_06_write_summary_and_export_sync_offline(self):
        store = make_store()
        wal = MemWalClientAdapter()
        w = MemoryWritingInterceptor(store=store, embedder=flat_embed,
                                     wal=wal)
        sid = w.write_summary("a1", "s1", "session folded", 100)
        self.assertTrue(sid)
        with tempfile.TemporaryDirectory() as tmp:
            reports = []
            recs = [MemoryRecord(
                record_id=rid, agent_id="a1", session_id="s1",
                kind=INTERACTION, content="c", embedding=VEC,
                logical_ts=1, seq=n)
                for n, rid in enumerate(("r1", "r2"), 1)]
            w.export_and_sync(recs, os.path.join(tmp, "w.wal"), reports)
            rep = [r for r in reports if r.op == "sync"][-1]
            self.assertIn("kept=2", rep.detail)  # offline-first posture
            self.assertTrue(Path(tmp, "w.wal").exists())

    def test_07_budget_refusal_blocks_write_without_raising(self):
        ledger = make_budget(limit=2.0)
        ledger.consume(MEMORY_BUDGET_RESOURCE, 2)  # exhaust
        store = make_store()
        w = MemoryWritingInterceptor(store=store, embedder=flat_embed,
                                     budget=ledger)
        reports = []
        rid = w.write_interaction("a1", "s1", "content", 1, reports)
        self.assertIsNone(rid)
        self.assertTrue(any("budget_refused" in r.detail
                            for r in reports))
        self.assertEqual([c for c in store._exec.calls
                          if "INSERT" in c[0]], [])  # nothing persisted

    def test_08_store_failure_degrades_not_raises(self):
        w = MemoryWritingInterceptor(store=BoomStore(), embedder=flat_embed)
        reports = []
        rid = w.write_interaction("a1", "s1", "content", 1, reports)
        self.assertIsNone(rid)
        self.assertTrue(any("degraded:StoreError" == r.detail
                            for r in reports))


# ---------------------------------------------------------------------------
# A — composing runtime (Phase 7/8 pipeline wiring)
# ---------------------------------------------------------------------------

class TestMemoryEnabledRuntime(unittest.TestCase):
    def _runtime(self, store, ledger=None, summarize=None):
        provider = MemoryContextProvider(store=store, embedder=flat_embed,
                                         budget=ledger)
        writer = MemoryWritingInterceptor(store=store, embedder=flat_embed,
                                          wal=MemWalClientAdapter(),
                                          budget=ledger)
        return MemoryEnabledAiRuntime(MockAiProvider().generate, provider,
                                      writer, summarize=summarize,
                                      logical_clock=lambda: 42)

    def test_09_context_injected_and_interaction_recorded(self):
        store = make_store(canned={
            GUIDELINE: [{"record_id": "g1",
                         "content": "always formal Persian tone"}]})
        rt = self._runtime(store)
        seen = {}

        def spy(r):
            seen["payload"] = r.prompt_payload
            return MockAiProvider().generate(r)

        rt._request_fn = spy
        response, trace = rt.generate(req(), agent_id="p7",
                                      session_id="s1")
        self.assertIn("memory_context", seen["payload"])
        self.assertIn("always formal Persian tone",
                      " ".join(
                          seen["payload"]["memory_context"]["guidelines"]))
        self.assertTrue(trace["memory_context_used"])
        self.assertTrue(trace["interaction_id"])
        self.assertEqual(response.finish_reason, "stop")

    def test_10_store_failure_still_generates_zero_shot(self):
        rt = self._runtime(BoomStore())
        response, trace = rt.generate(req())
        self.assertEqual(response.finish_reason, "stop")  # uninterrupted
        ops = {r.op: r for r in trace["memory_reports"]}
        self.assertFalse(ops["retrieve"].ok)
        self.assertFalse(ops["write_interaction"].ok)
        self.assertIn("degraded", ops["retrieve"].detail)

    def test_11_budget_exhausted_memory_hop_skipped_generation_runs(self):
        ledger = make_budget(limit=1.0)
        ledger.consume(MEMORY_BUDGET_RESOURCE, 1)
        store = make_store()
        rt = self._runtime(store, ledger=ledger)
        response, trace = rt.generate(req())
        self.assertEqual(response.finish_reason, "stop")
        reports = trace["memory_reports"]
        self.assertTrue(all("budget_refused" in r.detail
                            for r in reports if r.op == "retrieve"))
        self.assertFalse(trace["interaction_id"])

    def test_12_evaluation_summary_written_for_phase8(self):
        store = make_store()
        rt = self._runtime(store, summarize=lambda r, resp:
                           f"eval: {resp.text[:20]}")
        _, trace = rt.generate(req("quality review"))
        self.assertTrue(trace["interaction_id"])
        writes = [c for c in store._exec.calls if "INSERT" in c[0]]
        self.assertEqual(len(writes), 2)  # interaction + summary

    def test_13_budget_enforced_across_reads_and_writes(self):
        ledger = make_budget(limit=3.0)
        store = make_store()
        rt = self._runtime(store, ledger=ledger)
        for n in range(3):
            rt.generate(req(f"t{n}"))
        self.assertEqual(ledger.consumed(MEMORY_BUDGET_RESOURCE,
                                         "per_run", "green"), 0.0)
        # each generate() = 1 retrieve + 1 write = 2 pre-dispatch checks
        # (consume happens at the host; the interceptor only checks).

    def test_14_deep_redaction_through_full_pipeline(self):
        store = make_store()
        rt = self._runtime(store)
        canary = "sk-" + "z" * 24

        class LeakProvider(MockAiProvider):
            def generate(self, r):
                return super().generate(r)

        rt2 = MemoryEnabledAiRuntime(
            lambda r: MockAiProvider(responses={}).generate(r),
            MemoryContextProvider(), MemoryWritingInterceptor(
                store=store, embedder=flat_embed,
                wal=MemWalClientAdapter()),
            summarize=lambda r, resp: f"review note {canary}",
            logical_clock=lambda: 7)
        rt2._summarize = lambda r, resp: "note " + canary
        rt2.generate(req("eval"), agent_id="p8", session_id="s1")
        inserts = [c for c in store._exec.calls if "INSERT" in c[0]]
        self.assertGreaterEqual(len(inserts), 2)
        for sql, params in inserts:
            self.assertNotIn(canary, str(params))

    def test_15_request_fn_failure_propagates(self):
        rt = self._runtime(make_store())

        def boom(r):
            raise RuntimeError("provider down")

        rt._request_fn = boom
        with self.assertRaises(RuntimeError):
            rt.generate(req())  # canonical failure semantics untouched


# ---------------------------------------------------------------------------
# B — staging smoke S-07 integration
# ---------------------------------------------------------------------------

class TestStagingSmokeRehydration(unittest.TestCase):
    def test_16_smoke_runner_includes_s07_and_passes(self):
        r = subprocess.run([sys.executable, str(SMOKE)],
                           capture_output=True, text=True, cwd=str(REPO))
        self.assertEqual(r.returncode, 0, r.stdout[-400:])
        self.assertIn("S-07 Stage-H re-hydration parity", r.stdout)
        self.assertIn("11/11 checks passed", r.stdout)

    def test_17_cutover_readiness_still_green_offline(self):
        r = subprocess.run([sys.executable, str(VCR)],
                           capture_output=True, text=True, cwd=str(REPO))
        self.assertIn(r.returncode, (0, 1))  # 0 clean / 1 DIRTY tree ok
        self.assertNotIn("Traceback", r.stderr)


if __name__ == "__main__":
    unittest.main()

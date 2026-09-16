"""Phase 7 M3 — concrete AI tasks & batch execution tests.

Contract under test: local/canonical/ai_tasks.py

Layers:
  1. Offline task tests (JSON EventStore / temp dirs, no stack):
     contract compliance of all three tasks, dry-run side-effect
     freeness, persist-mode PROPOSED landing, idempotency.
  2. Divergence detection: near-miss vocabulary (D-029/D-031/D-032),
     unknown product refs, scope widening — all Class B, none
     persisted.
  3. Batch + budget (D-063): batch summaries, hard-refusal stop with
     NO provider dispatch past the cap, spend accounting on dry-runs.
  4. Authority boundary: no Woo/Notion/publication edges from the
     task layer (AST-scanned), proposals can only land as PROPOSED.
  5. Live PostgreSQL round-trips (stack up): task → PROPOSED on the
     real D-055 store → HITL queue → human accept (applier runs);
     divergent output persists nothing on the live store.
"""

import json
import os
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOCAL = HERE.parent
ROOT = LOCAL.parent
for p in (str(LOCAL), str(LOCAL / "canonical"), str(LOCAL / "services")):
    if p not in sys.path:
        sys.path.insert(0, p)

from canonical.ai_contracts import validate_ai_output  # noqa: E402
from canonical.ai_proposal_lifecycle import (  # noqa: E402
    ACCEPTED, IN_REVIEW, PROPOSED, ProposalLifecycle)
from canonical.ai_runtime import (  # noqa: E402
    AiRequest, MockAiProvider, ModelRouter, TARIFFS)
from canonical.ai_tasks import (  # noqa: E402
    CaptionTask, ContentIdeaTask, DescriptionTask, TaskEntity)
from canonical.verification_tool import VerificationQueue  # noqa: E402
from services.sync_engine import EventStore, ProvenanceEngine  # noqa: E402

KNOWN_PRODUCT = "a1b2c3d4-1111-4222-a333-444444444444"


def _make_stack(tmp):
    prov = ProvenanceEngine(os.path.join(tmp, "prov.jsonl"))
    store = EventStore(os.path.join(tmp, "events.jsonl"))
    queue = VerificationQueue(os.path.join(tmp, "queue.json"))
    life = ProposalLifecycle(store, prov, queue=queue,
                             applier=lambda pid, ref: {"ok": True})
    return prov, store, queue, life


def _entity(key="ent-1", **extra):
    return TaskEntity(kind="product", key=key,
                      payload={"color": "مشکی", "category": "مانتو",
                               **extra}, product_id=KNOWN_PRODUCT)


class OfflineTaskTests(unittest.TestCase):
    """Contract compliance + dry-run/persist semantics (no stack)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        self.router = ModelRouter({"mock": MockAiProvider()})
        self.prov, self.store, self.queue, self.life = \
            _make_stack(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    def test_all_three_tasks_produce_contract_valid_output(self):
        for task, entity in (
                (ContentIdeaTask(self.router),
                 TaskEntity(kind="content_idea", key="topic-1",
                            payload={"season": "پاییز"})),
                (CaptionTask(self.router), _entity()),
                (DescriptionTask(self.router,
                                 product_lookup=lambda pid: True),
                 _entity(variant_id="11111111-2222-4333-a444-555555555555")),
        ):
            rep = task.run(entity, mode="dry-run")
            self.assertTrue(rep.ok, f"{task.task_type}: {rep.error}")
            self.assertIsNotNone(rep.proposal)
            v = validate_ai_output(task.schema_id, rep.proposal.payload)
            self.assertTrue(v["valid"],
                            f"{task.task_type} payload violates contract")

    def test_dry_run_has_zero_pipeline_side_effects(self):
        idea = ContentIdeaTask(self.router, lifecycle=self.life)
        ent = TaskEntity(kind="content_idea", key="topic-dr",
                         payload={"season": "پاییز"})
        rep = idea.run(ent, mode="dry-run")
        self.assertTrue(rep.ok)
        # nothing durable: no events, no provenance, no queue items
        self.assertEqual(list(self.life.store.records.values())
                         if hasattr(self.life.store, "records") else [],
                         [])
        self.assertEqual(self.prov.records, [])
        self.assertEqual(self.queue.load_pending(), [])

    def test_dry_run_does_not_consume_the_idempotency_slot(self):
        task = CaptionTask(self.router, lifecycle=self.life)
        ent = _entity(key="ent-dr")
        self.assertTrue(task.run(ent, mode="dry-run").ok)
        rep = task.run(ent, mode="persist")
        self.assertTrue(rep.ok)
        self.assertEqual(rep.verdict, "new")
        self.assertEqual(self.life.state_of(rep.proposal_id), PROPOSED)

    def test_persist_mode_lands_proposed_with_queue_and_provenance(self):
        task = CaptionTask(self.router, lifecycle=self.life)
        rep = task.run(_entity(key="ent-p1"), mode="persist")
        self.assertTrue(rep.ok, rep.error)
        self.assertEqual(rep.state, "PROPOSED")
        self.assertEqual(self.life.state_of(rep.proposal_id), PROPOSED)
        # D-026: one AI_GENERATED provenance record, pending review
        ai_recs = [r for r in self.prov.records
                    if r.get("source_type") == "AI_GENERATED"]
        self.assertEqual(len(ai_recs), 1)
        self.assertEqual(ai_recs[0]["review_state"], "PENDING")
        # HITL: exactly one pending item keyed to the proposal
        pending = self.queue.load_pending()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].get("proposal_id"), rep.proposal_id)

    def test_persist_is_idempotent_by_deterministic_tag(self):
        task = DescriptionTask(self.router, lifecycle=self.life,
                               product_lookup=lambda pid: True)
        ent = _entity(key="ent-idem")
        r1 = task.run(ent, mode="persist")
        r2 = task.run(ent, mode="persist")
        self.assertTrue(r1.ok and r2.ok)
        self.assertEqual(r1.verdict, "new")
        self.assertEqual(r2.verdict, "skipped_duplicate")
        self.assertEqual(r1.proposal_id, r2.proposal_id)
        # exactly ONE durable PROPOSED event and ONE queue item
        pending = self.queue.load_pending()
        self.assertEqual(len(pending), 1)
        ai_recs = [r for r in self.prov.records
                    if r.get("source_type") == "AI_GENERATED"]
        self.assertEqual(len(ai_recs), 1)

    def test_persist_without_lifecycle_is_refused(self):
        task = CaptionTask(self.router)   # no lifecycle injected
        with self.assertRaises(RuntimeError):
            task.run(_entity(key="ent-nolc"), mode="persist")


class DivergenceTests(unittest.TestCase):
    """AI output vs canonical vocabulary/records — Class B, no persist."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        self.prov, self.store, self.queue, self.life = \
            _make_stack(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    def _caption(self, hashtags):
        router = ModelRouter({"mock": MockAiProvider(responses={
            "caption_proposal.v1": json.dumps(
                {"caption_fa": "کت پاییزی جدید رسید",
                 "hashtags": hashtags,
                 "alt_text": "مدل با کت پاییزی در نور طبیعی"},
                ensure_ascii=False)})})
        return CaptionTask(router, lifecycle=self.life)

    def test_exact_approved_terms_pass(self):
        task = self._caption(["#مشکی", "#پاییز", "#M"])
        rep = task.run(_entity(key="ent-ok"), mode="dry-run")
        self.assertTrue(rep.ok, rep.divergences)
        self.assertEqual(rep.divergences, [])

    def test_near_miss_vocabulary_is_flagged_class_b(self):
        # 'مشکیه' is a near-miss of approved color 'مشکی' — the model
        # must never mint vocabulary variants (D-029/D-031/D-032)
        task = self._caption(["#مشکیه"])
        rep = task.run(_entity(key="ent-nm"), mode="persist")
        self.assertFalse(rep.ok)
        self.assertEqual(rep.failure_class, "B")
        self.assertTrue(any("near-miss" in d for d in rep.divergences))
        # nothing was persisted (no PROPOSED record exists)
        self.assertEqual(self.prov.records, [])
        self.assertEqual(self.queue.load_pending(), [])

    def test_unknown_product_in_description_is_flagged(self):
        router = ModelRouter({"mock": MockAiProvider()})
        task = DescriptionTask(router, lifecycle=self.life,
                               product_lookup=lambda pid: False)
        rep = task.run(_entity(key="ent-unk"), mode="persist")
        self.assertFalse(rep.ok)
        self.assertEqual(rep.failure_class, "B")
        self.assertTrue(any("does not exist" in d
                            for d in rep.divergences))
        self.assertEqual(self.prov.records, [])

    def test_known_product_passes_and_scope_widening_is_flagged(self):
        vid = "11111111-2222-4333-a444-555555555555"
        router = ModelRouter({"mock": MockAiProvider()})
        task = DescriptionTask(router, lifecycle=self.life,
                               product_lookup=lambda pid: True)
        ok = task.run(_entity(key="ent-kn", variant_id=vid),
                      mode="dry-run")
        self.assertTrue(ok.ok, ok.divergences)
        # mock adds no variants beyond scope; force one via responses
        wide = ModelRouter({"mock": MockAiProvider(responses={
            "product_description_enrichment.v1": json.dumps({
                "product_id": KNOWN_PRODUCT,
                "variant_ids": [vid,
                                "99999999-8888-4777-a666-777777777777"],
                "description_fa": "توضیحات غنی‌شده برای محصول آزمایشی",
                "seo_title_fa": "مانتو پاییزی زنانه | خرید آنلاین",
                "seo_keywords": ["مانتو پاییزی", "خرید مانتو"],
                "rationale": "توضیحات فعلی کوتاه بود و غنی‌سازی لازم داشت",
            }, ensure_ascii=False)})})
        task2 = DescriptionTask(wide, lifecycle=self.life,
                                product_lookup=lambda pid: True)
        rep = task2.run(_entity(key="ent-wide", variant_id=vid),
                        mode="dry-run")
        self.assertFalse(rep.ok)
        self.assertTrue(any("outside the requested scope" in d
                            for d in rep.divergences))

    def test_content_idea_off_root_state_is_flagged(self):
        # schema-enum drift probe: a provider that emits a deeper
        # lifecycle state fails the strict contract (Class B at the
        # router). The task layer ALSO re-checks the pin deterministically
        # — asserted here by bypassing the router with a raw envelope.
        router = ModelRouter({"mock": MockAiProvider(responses={
            "content_idea_proposal.v1": json.dumps(
                {"title": "کمپین پاییزی کت و جلیقه",
                 "target_lifecycle_state": "Review",
                 "rationale": "بر اساس تقویم محتوایی فصل پاییز"},
                ensure_ascii=False)})})
        task = ContentIdeaTask(router, lifecycle=self.life)
        with self.assertRaises(Exception) as ctx:
            task.run(TaskEntity(kind="content_idea", key="topic-x",
                                payload={"season": "پاییز"}),
                     mode="persist")
        self.assertIn("contract", str(ctx.exception))
        # nothing persisted by the failed dispatch
        self.assertEqual(self.prov.records, [])
        # defense-in-depth pin: a non-Backlog state can never pass the
        # task-layer check either (direct divergence check on a forged
        # envelope proves the deterministic re-check, not just schema)
        from canonical.ai_runtime import AiProposal
        forged = AiProposal(
            schema_id="content_idea_proposal.v1",
            task_type="propose_content_idea",
            payload={"title": "کمپین پاییزی کت و جلیقه",
                     "target_lifecycle_state": "Review",
                     "rationale": "بر اساس تقویم محتوایی فصل پاییز"},
            provider="mock", model="mock-1",
            usage={"prompt_tokens": 1, "completion_tokens": 1},
            cost={"cost_usd": 0.0, "unknown_tariff": False},
            provenance_id=None, correlation_id="forged-probe")
        div = task._check_divergence(forged, TaskEntity(
            kind="content_idea", key="forged", payload={}))
        self.assertTrue(any("Backlog" in d for d in div))


class BatchBudgetTests(unittest.TestCase):
    """Batch mechanics + D-063 guardrails during batch execution."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def _caption_task(self, budget=None):
        router = ModelRouter({"mock": MockAiProvider()},
                             budgets=budget or {})
        prov = ProvenanceEngine(os.path.join(self.tmp, "prov.jsonl"))
        life = ProposalLifecycle(
            EventStore(os.path.join(self.tmp, "events.jsonl")), prov,
            applier=lambda pid, ref: {"ok": True})
        return router, CaptionTask(router, lifecycle=life)

    def test_batch_processes_all_and_reports_summary(self):
        router, task = self._caption_task()
        ents = [_entity(key=f"ent-{i}") for i in range(4)]
        summary = task.run_batch(ents, mode="persist")
        self.assertEqual(summary["requested"], 4)
        self.assertEqual(summary["processed"], 4)
        self.assertEqual(summary["ok"], 4)
        self.assertEqual(summary["failed"], 0)
        # spend is tracked even at the zero tariff (mock is free)
        self.assertIn("generate_caption", summary["spend_by_task"])

    def test_hard_budget_refusal_stops_batch_without_dispatch(self):
        router, task = self._caption_task(budget={"generate_caption": 0.5})
        # tariff so each call costs exactly 0.18 (M1 probe pattern);
        # the probe call itself is part of the router's spend ledger
        probe = router.run(AiRequest(
            task_type="generate_caption", schema_id="caption_proposal.v1",
            prompt_payload=_entity(key="probe").payload,
            idempotency_tag="probe"))
        tokens = probe.usage["completion_tokens"]
        TARIFFS[("mock", "mock-1")] = {
            "input": 0.0, "output": 0.18 / (tokens / 1000.0)}
        try:
            provider = router.providers["mock"]
            ents = [_entity(key=f"ent-{i}") for i in range(6)]
            summary = task.run_batch(ents, mode="persist")
            # probe calibrated the tariff at 0.0 cost; batch entities
            # 1-3 spend 0.54 ≥ 0.5 → entity 4 refused pre-dispatch
            self.assertEqual(summary["processed"], 4)
            self.assertEqual(summary["ok"], 3)
            self.assertEqual(summary["failed"], 1)
            stop = summary["results"][-1]
            self.assertTrue(stop.get("budget_exhausted"))
            self.assertEqual(stop.get("failure_class"), "B")
            # guardrail fired BEFORE dispatch: probe + 3 generations
            self.assertEqual(len(provider.calls), 4)
            self.assertGreaterEqual(
                summary["spend_by_task"]["generate_caption"], 0.5)
        finally:
            TARIFFS[("mock", "mock-1")] = {"input": 0.0, "output": 0.0}

    def test_dry_run_batch_meters_spend_but_persists_nothing(self):
        router, task = self._caption_task()
        ents = [_entity(key=f"ent-{i}") for i in range(3)]
        summary = task.run_batch(ents, mode="dry-run")
        self.assertEqual(summary["ok"], 3)
        # spend accumulator runs per call regardless of tariff value
        self.assertIn("generate_caption", summary["spend_by_task"])
        # and nothing durable exists anywhere
        pending = task._lifecycle.queue.load_pending() \
            if task._lifecycle.queue else []
        self.assertEqual(pending, [])


class AuthorityBoundaryTests(unittest.TestCase):
    """The task layer can never execute Red operations or self-advance."""

    def test_no_woo_notion_or_publication_edges_in_task_module(self):
        import ast as _ast
        import canonical.ai_tasks as mod
        tree = _ast.parse(
            Path(mod.__file__).read_text(encoding="utf-8"))
        literals = "\n".join(
            n.value for n in _ast.walk(tree)
            if isinstance(n, _ast.Constant) and isinstance(n.value, str))
        for forbidden in ("mock_woo", "notion_adapter", "woocommerce",
                          "publish", "publication", "price"):
            self.assertNotIn(forbidden, literals)

    def test_task_surface_has_no_decision_or_advance_verbs(self):
        for cls in (ContentIdeaTask, CaptionTask, DescriptionTask):
            for name in dir(cls):
                if name.startswith("_"):
                    continue
                self.assertNotIn("decide", name.lower())
                self.assertNotIn("advance", name.lower())
                self.assertNotIn("approve", name.lower())
                self.assertNotIn("publish", name.lower())

    def test_tasks_cannot_be_constructed_with_state_changing_power(self):
        # the ONLY lifecycle method tasks hold is the full M2 machine;
        # there is no task-side path around decide() — assert the
        # machine's driver is still the human-only entry point
        self.assertTrue(callable(ProposalLifecycle.decide))
        for cls in (ContentIdeaTask, CaptionTask, DescriptionTask):
            self.assertFalse(hasattr(cls, "decide"))
            self.assertFalse(hasattr(cls, "accept"))
            self.assertFalse(hasattr(cls, "reject"))


def _stack_up():
    try:
        import subprocess
        out = subprocess.run(
            ["docker", "compose", "-f", "local/infra/docker-compose.yml",
             "ps", "--format", "json"], capture_output=True, text=True,
            timeout=20, cwd=str(ROOT))
        if out.returncode != 0 or "engine-local-postgres" not in out.stdout:
            return False
        return '"Health": "healthy"' in out.stdout or \
            "healthy" in out.stdout
    except Exception:
        return False


@unittest.skipUnless(_stack_up(), "live PostgreSQL stack not running")
class LivePostgresRoundTripTests(unittest.TestCase):
    """Task → PROPOSED on the real D-055 store → human accept."""

    @classmethod
    def setUpClass(cls):
        scripts = str(LOCAL / "scripts")
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        from canonical.notion_ingest import PgEventStore
        cls.PgEventStore = PgEventStore
        cls._tmp = tempfile.TemporaryDirectory()
        cls.prov = ProvenanceEngine(
            os.path.join(cls._tmp.name, "prov.jsonl"))
        cls.life = ProposalLifecycle(
            cls.PgEventStore(), cls.prov,
            applier=lambda pid, ref: {"ok": True})

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _caption_task(self):
        return CaptionTask(ModelRouter({"mock": MockAiProvider()}),
                           lifecycle=self.life)

    def test_task_lands_proposed_on_live_store_and_accepts(self):
        tag = f"live-{uuid.uuid4().hex[:8]}"
        task = self._caption_task()
        rep = task.run(_entity(key=tag), mode="persist")
        self.assertTrue(rep.ok, rep.error)
        self.assertEqual(self.life.state_of(rep.proposal_id), PROPOSED)
        res = self.life.decide(rep.proposal_id, action="submit_review",
                               reviewer="owner", notes="M3 live review")
        self.assertEqual(res["state"], IN_REVIEW)
        res = self.life.decide(rep.proposal_id, action="accept",
                               reviewer="owner", notes="M3 live accept")
        self.assertEqual(res["state"], ACCEPTED)
        self.assertEqual(res["verdict"], "new")

    def test_live_persist_is_idempotent_across_task_runs(self):
        tag = f"live-{uuid.uuid4().hex[:8]}"
        task = self._caption_task()
        r1 = task.run(_entity(key=tag), mode="persist")
        r2 = task.run(_entity(key=tag), mode="persist")
        self.assertEqual(r1.verdict, "new")
        self.assertEqual(r2.verdict, "skipped_duplicate")

    def test_divergent_output_persists_nothing_on_live_store(self):
        tag = f"live-{uuid.uuid4().hex[:8]}"
        router = ModelRouter({"mock": MockAiProvider(responses={
            "caption_proposal.v1": json.dumps(
                {"caption_fa": "کت پاییزی جدید رسید",
                 "hashtags": ["#مشکیه"],
                 "alt_text": "مدل با کت پاییزی در نور طبیعی"},
                ensure_ascii=False)})})
        task = CaptionTask(router, lifecycle=self.life)
        before = len(self.life.store.succeeded_references("ai-proposal"))
        rep = task.run(_entity(key=tag), mode="persist")
        self.assertFalse(rep.ok)
        self.assertEqual(rep.failure_class, "B")
        after = len(self.life.store.succeeded_references("ai-proposal"))
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()

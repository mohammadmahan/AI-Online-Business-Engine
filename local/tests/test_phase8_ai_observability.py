"""Phase 8 — full test suite (D-065..D-068, milestones M1–M4).

Layers:
  M1  observability: record shape validation, append-only, cost
      report aggregation, D-045 redaction, no-AI-write-path.
  M2  live adapters: enablement gate closed by default, D-052
      failure mapping over INJECTED transports (zero network),
      graceful fallback with observable D-065 record, budget
      quarantine naming (BUDGET_EXCEEDED_HALT halt-before-dispatch).
  M3  templates: registry load + strict contract validation,
      semver monotonicity/immutability, hash pinning + drift
      failure, deterministic render, unknown-id refusal, request
      bridge reproducibility.
  M4  HITL service: deterministic inbox, single + bulk decisions
      (per-item independence, idempotent re-decisions, per-item
      failure isolation), divergence-guarded human edits, D-065
      hitl_decision records, E2E on the live PostgreSQL store.

Zero-network discipline: no test constructs a live adapter without
AI_LIVE_ENABLED set AND an injected transport; no socket is ever
created (AST-asserted by the Phase 7 static suite over ai_providers_live).
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
for p in (str(HERE), str(LOCAL), str(LOCAL / "canonical"),
          str(LOCAL / "services"), str(LOCAL / "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

from canonical.ai_observability import (  # noqa: E402
    AiObservabilityCollector, ObservabilityError, SCHEMA_VERSION,
    content_hash, divergence_rate, hitl_decision_record)
from canonical.ai_providers_live import (  # noqa: E402
    AnthropicProvider, FallbackProvider, OpenAiProvider,
    BUDGET_EXCEEDED_HALT, live_enabled, register_live_provider,
    require_live_key, with_live_fallback)
from canonical.ai_runtime import (  # noqa: E402
    AiProviderError, AiRequest, BudgetExceeded, MockAiProvider,
    ModelRouter, TARIFFS)
from canonical.ai_templates import (  # noqa: E402
    TemplateEngine, TemplateError, TemplateRegistry, render_into_request)
from canonical.ai_hitl_service import (  # noqa: E402
    HitlReviewService, HitlServiceError)
from canonical.ai_proposal_lifecycle import (  # noqa: E402
    ACCEPTED, PROPOSED, REJECTED, ProposalLifecycle)
from services.sync_engine import EventStore, ProvenanceEngine  # noqa: E402


def make_router(**kw):
    return ModelRouter({"mock": MockAiProvider()}, **kw)


def make_proposal(router, tag, task_type="propose_content_idea",
                  schema_id="content_idea_proposal.v1"):
    return router.run(AiRequest(
        task_type=task_type, schema_id=schema_id,
        prompt_payload={"topic": f"phase8-{tag}"},
        idempotency_tag=f"p8-{tag}"))


def ok_transport_openai(resp=None):
    def transport(request_dict):
        return {"content": json.dumps(
            MockAiProvider.MOCK_OUTPUTS["caption_proposal.v1"],
            ensure_ascii=False),
            "model": "gpt-4o-mini",
            "prompt_tokens": 12, "completion_tokens": 30,
            "latency_ms": 7, "finish_reason": "stop"}
    return transport


def failing_transport(exc):
    def transport(request_dict):
        raise exc
    return transport


def class_c_transport():
    def transport(request_dict):
        raise AiProviderError("401 invalid api key", failure_class="C")
    return transport


def class_a_transport():
    def transport(request_dict):
        raise AiProviderError("429 rate limit exceeded", failure_class="A")
    return transport


# ---------------------------------------------------------------------------
# M1 — observability (D-065)
# ---------------------------------------------------------------------------

class ObservabilityTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self._tmp.name, "obs.jsonl")
        self.col = AiObservabilityCollector(self.path)
        self.addCleanup(self._tmp.cleanup)

    def _rec(self, cid="c-1", **kw):
        base = dict(correlation_id=cid, stage="provider_call",
                    task_type="generate_caption", status="ok")
        base.update(kw)
        return self.col.record(**base)

    def test_record_shape_and_persistence(self):
        rec = self._rec(prompt_tokens=11, completion_tokens=7,
                        latency_ms=5, estimated_cost_usd=0.02,
                        provider="mock", model="mock-1")
        self.assertEqual(rec["schema_version"], SCHEMA_VERSION)
        self.assertEqual(rec["hitl_decision"], "none")
        persisted = []
        with open(self.path, encoding="utf-8") as f:
            for l in f:
                persisted.append(json.loads(l))
        self.assertEqual(persisted, self.col.records())
        self.assertEqual(persisted, self.col.records())

    def test_malformed_records_refused_class_b(self):
        with self.assertRaises(ObservabilityError):
            self.col.record(correlation_id="x", stage="wat",
                            task_type="t", status="ok")
        with self.assertRaises(ObservabilityError):
            self.col.record(correlation_id="", stage="lifecycle",
                            task_type="t", status="ok")
        with self.assertRaises(ObservabilityError):
            self.col.record(correlation_id="x", stage="lifecycle",
                            task_type="t", status="ok",
                            hitl_decision="maybe")
        with self.assertRaises(ObservabilityError):
            self.col.record(correlation_id="x", stage="lifecycle",
                            task_type="t", status="ok", latency_ms=-1)

    def test_redaction_guard_d045(self):
        with self.assertRaises(ObservabilityError):
            self.col.record(correlation_id="postgres://u:p@h/db",
                            stage="lifecycle", task_type="t",
                            status="ok")
        with self.assertRaises(ObservabilityError):
            self.col.record(correlation_id="x", stage="lifecycle",
                            task_type="t", status="ok",
                            notes="Bearer abc.def.ghi")

    def test_cost_report_aggregation(self):
        self._rec("a", task_type="generate_caption",
                  estimated_cost_usd=0.10, prompt_tokens=100,
                  completion_tokens=50)
        self._rec("b", task_type="generate_caption",
                  estimated_cost_usd=0.05, prompt_tokens=50,
                  completion_tokens=25)
        self._rec("c", task_type="propose_content_idea",
                  estimated_cost_usd=0.20)
        self._rec("d", stage="hitl_decision",
                  task_type="generate_caption", status="ACCEPTED",
                  hitl_decision="approve")
        rep = self.col.cost_report()
        self.assertAlmostEqual(rep["total_cost_usd"], 0.35, places=6)
        self.assertAlmostEqual(rep["by_task_type"]["generate_caption"],
                               0.15, places=6)
        self.assertEqual(rep["tokens"]["prompt"], 150)
        self.assertEqual(rep["hitl_decisions"], {"approve": 1})
        day = rep["by_day_utc"]
        self.assertAlmostEqual(sum(day.values()), 0.35, places=6)

    def test_append_only_file_view(self):
        self._rec("a")
        with open(self.path, encoding="utf-8") as f:
            first = f.read()
        self._rec("b")
        with open(self.path, encoding="utf-8") as f:
            second = f.read()
        self.assertTrue(second.startswith(first))  # lines only append

    def test_helpers(self):
        self.assertEqual(hitl_decision_record("accept"), "approve")
        self.assertEqual(hitl_decision_record("modify_accept"), "edit")
        self.assertEqual(hitl_decision_record("reject"), "reject")
        self.assertEqual(divergence_rate(1, 4), 0.25)
        self.assertEqual(divergence_rate(0, 0), 0.0)
        self.assertEqual(len(content_hash({"a": 1})), 64)

    def test_no_ai_write_path_into_reporting(self):
        # the collector is pipeline-side: the provider/mock surface
        # must not expose any reporting or recording verb
        import inspect
        from canonical.ai_runtime import AiProvider, MockAiProvider, \
            ModelRouter
        banned = ("record", "report", "cost_report", "collect")
        for cls in (AiProvider, MockAiProvider, ModelRouter):
            for name, _ in inspect.getmembers(cls, inspect.isfunction):
                if not name.startswith("_"):
                    for verb in banned:
                        self.assertNotIn(
                            verb, name.lower(),
                            f"{cls.__name__}.{name} exposes an "
                            f"observability write verb")


# ---------------------------------------------------------------------------
# M2 — live adapters & budget quarantine (D-066)
# ---------------------------------------------------------------------------

class _EnvGuard:
    """Context manager snapshotting/restoring AI env vars."""

    def __enter__(self):
        self.saved = {k: os.environ.get(k) for k in
                      ("AI_LIVE_ENABLED", "OPENAI_API_KEY",
                       "ANTHROPIC_API_KEY")}
        for k in self.saved:
            os.environ.pop(k, None)
        return self

    def __exit__(self, *exc):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class LiveAdapterGateTests(unittest.TestCase):
    def test_gate_closed_by_default(self):
        with _EnvGuard():
            self.assertFalse(live_enabled())
            with self.assertRaises(AiProviderError) as cm:
                OpenAiProvider(transport=ok_transport_openai())
            self.assertEqual(cm.exception.failure_class, "B")
            with self.assertRaises(AiProviderError):
                AnthropicProvider(transport=ok_transport_openai())

    def test_flag_without_key_refused(self):
        with _EnvGuard():
            os.environ["AI_LIVE_ENABLED"] = "true"
            with self.assertRaises(AiProviderError) as cm:
                OpenAiProvider(transport=ok_transport_openai())
            self.assertEqual(cm.exception.failure_class, "B")

    def test_key_without_flag_refused(self):
        with _EnvGuard():
            os.environ["OPENAI_API_KEY"] = "test-local-dummy"
            with self.assertRaises(AiProviderError):
                OpenAiProvider(transport=ok_transport_openai())

    def test_explicit_key_bypasses_env_gate_for_tests(self):
        # injected transport + explicit dummy key: no env, no network
        p = OpenAiProvider(transport=ok_transport_openai(),
                           api_key="test-local-dummy")
        self.assertEqual(len(p.calls), 0)

    def test_transport_mapping_d052(self):
        cases = [(class_c_transport(), "C"), (class_a_transport(), "A"),
                 (failing_transport(TimeoutError("t")), "A"),
                 (failing_transport(ConnectionError("c")), "A")]
        for transport, expected in cases:
            p = OpenAiProvider(transport=transport,
                               api_key="test-local-dummy")
            req = AiRequest(task_type="generate_caption",
                            schema_id="caption_proposal.v1",
                            prompt_payload={}, idempotency_tag="x")
            with self.assertRaises(AiProviderError) as cm:
                p.generate(req)
            self.assertEqual(cm.exception.failure_class, expected)

    def test_openai_success_over_injected_transport(self):
        p = OpenAiProvider(transport=ok_transport_openai(),
                           api_key="test-local-dummy")
        req = AiRequest(task_type="generate_caption",
                        schema_id="caption_proposal.v1",
                        prompt_payload={"c": 1}, idempotency_tag="ok1")
        resp = p.generate(req)
        self.assertIsNotNone(resp.parsed)
        self.assertIn("caption_fa", resp.parsed)
        self.assertEqual(resp.usage["prompt_tokens"], 12)
        self.assertEqual(resp.provider, "openai")

    def test_anthropic_success_over_injected_transport(self):
        def transport(rd):
            return {"content": [{"type": "text", "text": json.dumps(
                MockAiProvider.MOCK_OUTPUTS["caption_proposal.v1"],
                ensure_ascii=False)}],
                "model": "claude-sonnet-4-5",
                "usage": {"input_tokens": 9, "output_tokens": 21},
                "stop_reason": "end_turn"}
        p = AnthropicProvider(transport=transport,
                              api_key="test-local-dummy")
        resp = p.generate(AiRequest(
            task_type="generate_caption",
            schema_id="caption_proposal.v1",
            prompt_payload={}, idempotency_tag="a1"))
        self.assertEqual(resp.usage["prompt_tokens"], 9)
        self.assertEqual(resp.provider, "anthropic")

    def test_default_transport_refuses_network(self):
        # without an injected transport there is NO network path
        p = OpenAiProvider(transport=None, api_key="test-local-dummy")
        with self.assertRaises(AiProviderError) as cm:
            p.generate(AiRequest(task_type="generate_caption",
                                 schema_id="caption_proposal.v1",
                                 prompt_payload={}, idempotency_tag="n"))
        self.assertEqual(cm.exception.failure_class, "B")


class FallbackQuarantineTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.col = AiObservabilityCollector(os.path.join(
            self._tmp.name, "obs.jsonl"))
        self.addCleanup(self._tmp.cleanup)

    def _fb(self, transport):
        primary = OpenAiProvider(transport=transport,
                                 api_key="test-local-dummy")
        return with_live_fallback(primary, self.col,
                                  task_type="generate_caption")

    def test_class_c_falls_back_to_mock(self):
        fb = self._fb(class_c_transport())
        req = AiRequest(task_type="generate_caption",
                        schema_id="caption_proposal.v1",
                        prompt_payload={}, idempotency_tag="fb-c")
        resp = fb.generate(req)
        self.assertEqual(resp.provider, "mock")
        self.assertEqual(fb.fallbacks_used, 1)
        recs = self.col.records(stage="fallback")
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["error_class"], "C")
        self.assertIn("mock fallback", recs[0]["notes"])

    def test_class_a_falls_back_to_mock(self):
        fb = self._fb(class_a_transport())
        resp = fb.generate(AiRequest(
            task_type="generate_caption",
            schema_id="caption_proposal.v1",
            prompt_payload={}, idempotency_tag="fb-a"))
        self.assertEqual(resp.provider, "mock")

    def test_class_b_not_masked(self):
        # a malformed transport body parses to None — the ROUTER turns
        # that into a Class-B OutputValidationError/AiProviderError;
        # the fallback must NOT have masked it (fallbacks_used == 0)
        def bad_transport(rd):
            return {"content": "not json at all", "model": "m",
                    "prompt_tokens": 1, "completion_tokens": 1,
                    "latency_ms": 1}
        fb = self._fb(bad_transport)
        router = ModelRouter({"openai": fb})
        with self.assertRaises(AiProviderError) as cm:
            router.run(AiRequest(task_type="generate_caption",
                                 schema_id="caption_proposal.v1",
                                 prompt_payload={}, idempotency_tag="b"))
        self.assertEqual(cm.exception.failure_class, "B")
        self.assertEqual(fb.fallbacks_used, 0)

    def test_router_end_to_end_through_fallback(self):
        router = make_router()
        register_live_provider(router, self._fb(class_c_transport()),
                               "generate_caption")
        req = AiRequest(task_type="generate_caption",
                        schema_id="caption_proposal.v1",
                        prompt_payload={"c": 1},
                        idempotency_tag="fb-router")
        proposal = router.run(req)  # fell back to mock, succeeded
        self.assertEqual(proposal.provider, "mock")

    def test_budget_quarantine_named_behavior(self):
        self.assertEqual(BUDGET_EXCEEDED_HALT, "BUDGET_EXCEEDED_HALT")
        old = dict(TARIFFS)
        TARIFFS[("mock", "mock-1")] = {"input": 0.10, "output": 0.20}
        try:
            router = make_router(budgets={"generate_caption": 0.033})
            spent = 0.0
            with self.assertRaises(BudgetExceeded):
                for i in range(20):
                    router.run(AiRequest(
                        task_type="generate_caption",
                        schema_id="caption_proposal.v1",
                        prompt_payload={"c": i},
                        idempotency_tag=f"q{i}"))
                    spent = router._spend["generate_caption"]
            self.assertGreater(spent, 0)
        finally:
            TARIFFS.clear()
            TARIFFS.update(old)

    def test_unknown_tariff_flagged_not_guessed(self):
        router = ModelRouter({"openai": OpenAiProvider(
            transport=ok_transport_openai(),
            api_key="test-local-dummy")}, policy={
            "generate_caption": __import__(
                "canonical.ai_runtime", fromlist=["RouteTarget"]
            ).RouteTarget("openai", "gpt-4o-mini",
                          "caption_proposal.v1", budget_usd=1.0)})
        p = router.run(AiRequest(task_type="generate_caption",
                                 schema_id="caption_proposal.v1",
                                 prompt_payload={}, idempotency_tag="t"))
        self.assertTrue(p.cost["unknown_tariff"])
        self.assertEqual(p.cost["cost_usd"], 0.0)


# ---------------------------------------------------------------------------
# M3 — template registry (D-067)
# ---------------------------------------------------------------------------

class TemplateRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reg = TemplateRegistry(os.path.join("local", "templates"))

    def test_shipped_templates_load(self):
        for tid in ("content_idea", "generate_caption",
                    "enrich_description"):
            versions = self.reg.versions(tid)
            self.assertIn("v1.0.0", versions)
            t = self.reg.get(tid)
            # hash recorded at load == content-derived hash of the
            # template body (self-consistency, D-067)
            self.assertEqual(t["template_hash"],
                             self.reg.hash_of(tid))

    def test_contracts_match_d062_schemas(self):
        from canonical.ai_contracts import get_schema
        for tid in ("content_idea", "generate_caption",
                    "enrich_description"):
            t = self.reg.get(tid)
            self.assertEqual(t["schema_id"], get_schema(
                t["schema_id"])["title"])
            self.assertEqual(t["response_contract"],
                             get_schema(t["schema_id"]))

    def test_render_deterministic(self):
        eng = TemplateEngine(self.reg)
        ctx = {"context": "کمپین پاییز", "notes": "لایه‌بندی"}
        a = eng.render("content_idea", ctx)
        b = eng.render("content_idea", ctx)
        self.assertEqual(a[:3], b[:3])
        self.assertNotIn("{", a[0])
        self.assertEqual(a[2], self.reg.hash_of("content_idea"))

    def test_missing_context_key_refused(self):
        eng = TemplateEngine(self.reg)
        with self.assertRaises(TemplateError):
            eng.render("content_idea", {"context": "فقط یکی"})

    def test_unknown_template_refused_class_b(self):
        with self.assertRaises(TemplateError):
            self.reg.get("no_such_template")

    def test_semver_immutability_and_monotonicity(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = TemplateRegistry(os.path.join("local", "templates"))
            eng = TemplateEngine(reg)
            t = dict(reg.get("content_idea"))
            t["description"] = "changed wording — quality regression"
            # same version → refused (immutable shipped versions)
            with self.assertRaises(TemplateError):
                reg.register(t)
            # older version → refused (monotonic semver)
            t["version"] = "v0.9.0"
            with self.assertRaises(TemplateError):
                reg.register(t)
            # newer version → accepted, hash distinct
            t["version"] = "v1.1.0"
            newer = reg.register(t)
            self.assertNotEqual(newer["template_hash"],
                                reg.hash_of("content_idea", "v1.0.0"))
            self.assertEqual(reg.versions("content_idea"),
                             ["v1.0.0", "v1.1.0"])
            # default activation = highest version
            self.assertEqual(reg.get("content_idea")["version"],
                             "v1.1.0")

    def test_hash_drift_fails_loudly(self):
        reg = TemplateRegistry(os.path.join("local", "templates"))
        t = dict(reg.get("generate_caption"))
        t["prompt_text"] = "متن دستکاری‌شده"
        with self.assertRaises(TemplateError):
            # re-validate with the ORIGINAL recorded hash → mismatch
            from canonical.ai_templates import _validate_template
            bad = dict(t, template_hash=reg.hash_of("generate_caption"))
            _validate_template(bad, "<drift-test>")

    def test_request_bridge_reproducibility(self):
        eng = TemplateEngine(self.reg)
        router = make_router()
        req = AiRequest(task_type="propose_content_idea",
                        schema_id="content_idea_proposal.v1",
                        prompt_payload={"topic": "t"},
                        idempotency_tag="tpl-1")
        rendered = render_into_request(
            req, eng, "content_idea",
            {"context": "زمینه", "notes": "نکته"})
        self.assertIsNot(rendered, req)  # original untouched
        self.assertEqual(rendered.prompt_payload["template_id"],
                         "content_idea")
        self.assertEqual(rendered.prompt_payload["template_hash"],
                         self.reg.hash_of("content_idea"))
        # the route still produces a CONTRACT-VALID proposal (the
        # strict schema rejects extra fields — model output stays
        # clean; template ids travel on the request/D-065 side)
        p1 = make_proposal_router_run(router, rendered)
        self.assertNotIn("template_id", p1.payload)
        self.assertEqual(p1.schema_id, "content_idea_proposal.v1")
        # deterministic re-render → identical hash
        again = render_into_request(req, eng, "content_idea",
                                    {"context": "زمینه",
                                     "notes": "نکته"})
        self.assertEqual(again.prompt_payload["template_hash"],
                         rendered.prompt_payload["template_hash"])


def make_proposal_router_run(router, request):
    return router.run(request)


# ---------------------------------------------------------------------------
# M4 — HITL review service (D-068)
# ---------------------------------------------------------------------------

class HitlServiceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        self.col = AiObservabilityCollector(os.path.join(
            self.tmp, "obs.jsonl"))
        self.life = ProposalLifecycle(
            EventStore(os.path.join(self.tmp, "e.jsonl")),
            ProvenanceEngine(os.path.join(self.tmp, "p.jsonl")),
            applier=lambda pid, ref: {"ok": True})
        self.svc = HitlReviewService(self.life, self.col)
        self.addCleanup(self._tmp.cleanup)

    def _proposal(self, tag, submit_review=True):
        p = make_proposal(make_router(), tag)
        self.life.submit(p)
        if submit_review:
            self.life.decide(p.correlation_id,
                             action="submit_review", reviewer="owner")
        return p

    def test_inbox_deterministic_and_stateful(self):
        a = self._proposal("inb-a")
        b = self._proposal("inb-b", submit_review=False)
        inbox = self.svc.inbox()
        ids = [i["proposal_id"] for i in inbox]
        self.assertIn(a.correlation_id, ids)
        self.assertIn(b.correlation_id, ids)
        self.assertEqual([i["state"] for i in inbox
                          if i["proposal_id"] == a.correlation_id],
                         ["IN_REVIEW"])
        again = self.svc.inbox()
        self.assertEqual(ids, [i["proposal_id"] for i in again])

    def test_single_decisions(self):
        p = self._proposal("single")
        res = self.svc.approve(p.correlation_id, reviewer="owner",
                               notes="ok")
        self.assertEqual(res["state"], ACCEPTED)
        self.assertEqual(res["verdict"], "new")
        q = self._proposal("single-r")
        self.svc.reject(q.correlation_id, reviewer="owner")
        self.assertEqual(self.life.state_of(q.correlation_id), REJECTED)

    def test_bulk_all_decide(self):
        ps = [self._proposal(f"bulk{i}") for i in range(5)]
        out = self.svc.bulk_decide(
            [{"proposal_id": p.correlation_id, "action": "approve"}
             for p in ps], reviewer="owner")
        self.assertEqual(out["summary"],
                         {"decided": 5, "skipped_duplicate": 0,
                          "failed": 0})
        for p in ps:
            self.assertEqual(self.life.state_of(p.correlation_id),
                             ACCEPTED)
        self.assertEqual(self.svc.inbox(), [])

    def test_bulk_idempotent_and_conflict_refused(self):
        p = self._proposal("bulk-idem")
        first = self.svc.bulk_decide(
            [{"proposal_id": p.correlation_id, "action": "approve",
              "notes": "same"}], reviewer="owner")
        self.assertEqual(first["summary"]["decided"], 1)
        second = self.svc.bulk_decide(
            [{"proposal_id": p.correlation_id, "action": "approve",
              "notes": "same"}], reviewer="owner")
        self.assertEqual(second["summary"]["skipped_duplicate"], 1)
        # conflicting re-decision (different decision on terminal)
        conflict = self.svc.bulk_decide(
            [{"proposal_id": p.correlation_id, "action": "reject",
              "notes": "changed mind"}], reviewer="owner")
        self.assertEqual(conflict["summary"]["failed"], 1)
        self.assertIn("immutable", conflict["results"][0]["error"])
        self.assertEqual(self.life.state_of(p.correlation_id),
                         ACCEPTED)

    def test_bulk_per_item_independence(self):
        good = self._proposal("ind-good")
        unknown = "no-such-proposal-id"
        bad = self._proposal("ind-bad")
        out = self.svc.bulk_decide([
            {"proposal_id": good.correlation_id, "action": "approve"},
            {"proposal_id": unknown, "action": "approve"},
            {"proposal_id": bad.correlation_id, "action": "approve"},
        ], reviewer="owner")
        self.assertEqual(out["summary"],
                         {"decided": 2, "skipped_duplicate": 0,
                          "failed": 1})
        by_id = {r["proposal_id"]: r for r in out["results"]}
        self.assertTrue(by_id[good.correlation_id]["ok"])
        self.assertFalse(by_id[unknown]["ok"])
        self.assertEqual(by_id[unknown]["error_class"], "B")
        self.assertTrue(by_id[bad.correlation_id]["ok"])
        # no half-applied item: good + bad are terminal, unknown skipped
        self.assertEqual(self.life.state_of(good.correlation_id),
                         ACCEPTED)
        self.assertEqual(self.life.state_of(bad.correlation_id),
                         ACCEPTED)

    def test_bulk_requires_reviewer(self):
        p = self._proposal("bulk-norev")
        with self.assertRaises(HitlServiceError):
            self.svc.bulk_decide(
                [{"proposal_id": p.correlation_id,
                  "action": "approve"}], reviewer="  ")

    def test_bulk_unknown_action_refused(self):
        p = self._proposal("bulk-act")
        out = self.svc.bulk_decide(
            [{"proposal_id": p.correlation_id, "action": "publish"}],
            reviewer="owner")
        self.assertEqual(out["summary"]["failed"], 1)
        self.assertIn("publish", out["results"][0]["error"])

    def test_edit_validated_against_contract(self):
        p = self._proposal("edit")
        good = dict(MockAiProvider.MOCK_OUTPUTS[
            "content_idea_proposal.v1"])
        res = self.svc.edit_approve(p.correlation_id, good,
                                    reviewer="owner",
                                    notes="improved title")
        self.assertEqual(res["state"], "MODIFIED_BY_HUMAN")
        q = self._proposal("edit-bad")
        with self.assertRaises(HitlServiceError) as cm:
            self.svc.edit_approve(q.correlation_id,
                                  {"title": "ab"},  # too short + missing
                                  reviewer="owner")  # required fields
        self.assertIn("never silently applied",
                      str(cm.exception))
        # the invalid edit changed nothing
        self.assertEqual(self.life.state_of(q.correlation_id),
                         "IN_REVIEW")

    def test_hitl_observability_records(self):
        p = self._proposal("obs")
        self.svc.approve(p.correlation_id, reviewer="owner")
        recs = [r for r in self.col.records(stage="hitl_decision")
                if r["correlation_id"] == p.correlation_id]
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["hitl_decision"], "approve")
        self.assertEqual(recs[0]["status"], "ACCEPTED")

    def test_no_auto_advance_without_reviewer(self):
        p = self._proposal("norev", submit_review=False)
        # the service surface has NO reviewer-less decision path
        import inspect
        sig = inspect.signature(self.svc.approve)
        self.assertIn("reviewer", sig.parameters)
        self.assertTrue(sig.parameters["reviewer"].kind in
                        (inspect.Parameter.KEYWORD_ONLY,
                         inspect.Parameter.POSITIONAL_OR_KEYWORD))


# ---------------------------------------------------------------------------
# LIVE POSTGRESQL — M4 end-to-end on the durable store
# ---------------------------------------------------------------------------

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
class LiveEndToEndTests(unittest.TestCase):
    """task → router → proposal → observability → inbox → human
    decision → provenance → apply, on the live D-055 store."""

    @classmethod
    def setUpClass(cls):
        from canonical.notion_ingest import PgEventStore
        cls.PgEventStore = PgEventStore
        cls._tmp = tempfile.TemporaryDirectory()
        cls.col = AiObservabilityCollector(os.path.join(
            cls._tmp.name, "obs.jsonl"))
        cls.life = ProposalLifecycle(
            cls.PgEventStore(),
            ProvenanceEngine(os.path.join(cls._tmp.name, "p.jsonl")),
            applier=lambda pid, ref: {"ok": True})
        cls.svc = HitlReviewService(cls.life, cls.col)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_full_round_trip_on_live_store(self):
        router = make_router()
        p = make_proposal(router, f"live-{uuid.uuid4().hex[:8]}")
        self.life.submit(p)
        cid = p.correlation_id
        # the human moves PROPOSED → IN_REVIEW first (M2 lifecycle:
        # terminal decisions act on IN_REVIEW only — no auto-advance)
        self.life.decide(cid, action="submit_review", reviewer="owner")
        # restart safety: a fresh service sees the same inbox
        fresh = HitlReviewService(ProposalLifecycle(
            self.PgEventStore(), self.life.provenance,
            applier=self.life.applier), self.col)
        self.assertIn(cid, [i["proposal_id"] for i in fresh.inbox()])
        # provider_call + lifecycle observability, then decision
        self.col.record(correlation_id=cid, stage="provider_call",
                        task_type=p.task_type, status="ok",
                        provider=p.provider, model=p.model,
                        prompt_tokens=p.usage["prompt_tokens"],
                        completion_tokens=p.usage["completion_tokens"],
                        estimated_cost_usd=p.cost["cost_usd"])
        out = fresh.bulk_decide(
            [{"proposal_id": cid, "action": "approve",
              "notes": "phase8 live e2e"}], reviewer="owner")
        self.assertEqual(out["summary"]["decided"], 1)
        self.assertEqual(self.life.state_of(cid), ACCEPTED)
        # observability: provider call + hitl decision under ONE id
        stages = {r["stage"] for r in self.col.records(cid)}
        self.assertEqual(stages, {"provider_call", "hitl_decision"})
        rec = [r for r in self.col.records(cid)
               if r["stage"] == "hitl_decision"][0]
        self.assertEqual(rec["hitl_decision"], "approve")
        self.assertEqual(rec["task_type"], "propose_content_idea")
        # idempotent re-run of the same bulk decision
        again = fresh.bulk_decide(
            [{"proposal_id": cid, "action": "approve",
              "notes": "phase8 live e2e"}], reviewer="owner")
        self.assertEqual(again["summary"]["skipped_duplicate"], 1)

    def test_bulk_on_proposed_item_refused_cleanly(self):
        # inbox may list PROPOSED (awaiting review submission); a bulk
        # terminal decision on such an item fails per-item with the
        # lifecycle's illegal-transition error and changes nothing
        p = make_proposal(ModelRouter({"mock": MockAiProvider()}),
                          f"livep-{uuid.uuid4().hex[:8]}")
        self.life.submit(p)
        out = self.svc.bulk_decide(
            [{"proposal_id": p.correlation_id, "action": "approve"}],
            reviewer="owner")
        self.assertEqual(out["summary"]["failed"], 1)
        self.assertIn("illegal transition",
                      out["results"][0]["error"])
        self.assertEqual(self.life.state_of(p.correlation_id), PROPOSED)

    def test_bulk_conflict_isolation_on_live_store(self):
        a = make_proposal(ModelRouter({"mock": MockAiProvider()}),
                          f"liveb-{uuid.uuid4().hex[:8]}")
        self.life.submit(a)
        self.life.decide(a.correlation_id, action="submit_review",
                         reviewer="owner")
        out = self.svc.bulk_decide([
            {"proposal_id": a.correlation_id, "action": "approve"},
            {"proposal_id": a.correlation_id, "action": "reject"},
        ], reviewer="owner")
        self.assertEqual(out["summary"]["decided"], 1)
        self.assertEqual(out["summary"]["failed"], 1)
        self.assertEqual(self.life.state_of(a.correlation_id),
                         ACCEPTED)  # first decision stands, immutable


if __name__ == "__main__":
    unittest.main()

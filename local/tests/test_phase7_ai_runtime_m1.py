"""Phase 7 M1 — AI runtime contract and guardrail tests (offline).

Coverage:
  1. Strict schema validator: pinned positive/negative vectors per v1
     contract; strict-mode rejection of extra fields; schema-drift
     loud-failure (unknown keywords, permissive additionalProperties).
  2. MockAiProvider determinism + D-052 failure injection.
  3. ModelRouter: deterministic policy, budget soft-warning/hard
     refusal BEFORE dispatch, token-bucket Class-A limiter, unknown
     tariff flagging, schema-mismatch refusal.
  4. Usage ledger: every call recorded with cost estimate.
  5. D-050 structural no: no Red-execution path from the AI runtime;
     provenance AI_GENERATED; proposal → queue item shape.

No network, no credentials (D-045/D-053) — everything runs against
MockAiProvider.
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOCAL = HERE.parent
ROOT = LOCAL.parent
for p in (str(LOCAL), str(LOCAL / "canonical"), str(LOCAL / "services")):
    if p not in sys.path:
        sys.path.insert(0, p)

from canonical.ai_contracts import (  # noqa: E402
    SchemaError, OutputValidationError, validate_ai_output, get_schema,
    AI_OUTPUT_SCHEMAS,
)
from canonical.ai_runtime import (  # noqa: E402
    AiProviderError, AiRequest, BudgetExceeded, MockAiProvider,
    ModelRouter, TARIFFS, UsageLedger, estimate_cost,
)

_LEDGER = str(HERE / "fixtures" / "ai" / "_m1_ledger.json")
_QUEUE = str(HERE / "fixtures" / "ai" / "_m1_queue.json")
_PROV = str(HERE / "fixtures" / "ai" / "_m1_provenance.json")


def _clean():
    for p in (_LEDGER, _QUEUE, _PROV):
        if os.path.exists(p):
            os.remove(p)


def _req(task="generate_caption", schema="caption_proposal.v1",
         payload=None, tag="t1"):
    return AiRequest(task_type=task, schema_id=schema,
                     prompt_payload=payload or {"product": "کت جلیقه"},
                     idempotency_tag=tag)


# =========================================================================
# [1] Contracts: strict validator + pinned vectors
# =========================================================================


class TestSchemaValidator(unittest.TestCase):

    def test_extra_field_rejected_strict_mode(self):
        out = {"caption_fa": "کپشن معتبر برای تست", "hashtags": [],
               "alt_text": "متن جایگزین معتبر", "injected": True}
        res = validate_ai_output("caption_proposal.v1", out)
        self.assertFalse(res["valid"])
        self.assertEqual(res["failure_class"], "B")
        self.assertTrue(any("additional property" in e
                            for e in res["errors"]))

    def test_missing_required_rejected(self):
        out = {"caption_fa": "کپشن معتبر برای تست"}
        res = validate_ai_output("content_idea_proposal.v1", out)
        self.assertFalse(res["valid"])
        self.assertTrue(any("missing required" in e for e in res["errors"]))

    def test_content_idea_valid_vector(self):
        out = {"title": "کمپین پاییزی کت و جلیقه",
               "working_notes": "یادداشت",
               "target_lifecycle_state": "Backlog",
               "rationale": "دلیل معتبر و طولانی کافی"}
        self.assertTrue(validate_ai_output(
            "content_idea_proposal.v1", out)["valid"])

    def test_content_idea_non_root_state_rejected(self):
        out = {"title": "کمپین پاییزی کت و جلیقه",
               "target_lifecycle_state": "Published",
               "rationale": "دلیل معتبر و طولانی کافی"}
        res = validate_ai_output("content_idea_proposal.v1", out)
        self.assertFalse(res["valid"])
        self.assertTrue(any("not in enum" in e for e in res["errors"]))

    def test_caption_valid_vector(self):
        out = {"caption_fa": "کپشن پاییزی برای کت و جلیقه جدید",
               "hashtags": ["#پاییز"], "alt_text": "متن جایگزین معتبر"}
        self.assertTrue(validate_ai_output("caption_proposal.v1",
                                           out)["valid"])

    def test_enrichment_valid_vector(self):
        out = {
            "product_id": "a1b2c3d4-1111-4222-a333-444444444444",
            "variant_ids": [],
            "description_fa": "توضیحات فارسی معتبر و به‌اندازه کافی بلند برای تست",
            "seo_title_fa": "مانتو پاییزی زنانه",
            "seo_keywords": ["مانتو"],
            "rationale": "بهبود توضیحات کوتاه موجود"}
        self.assertTrue(validate_ai_output(
            "product_description_enrichment.v1", out)["valid"])

    def test_enrichment_bad_product_id_rejected(self):
        out = {
            "product_id": "NOT A PRODUCT ID",
            "variant_ids": [],
            "description_fa": "توضیحات فارسی معتبر و به‌اندازه کافی بلند",
            "seo_title_fa": "عنوان",
            "seo_keywords": ["کلید"],
            "rationale": "دلیل"}
        res = validate_ai_output("product_description_enrichment.v1", out)
        self.assertFalse(res["valid"])
        self.assertTrue(any("pattern" in e for e in res["errors"]))

    def test_unknown_schema_id_raises_schema_error(self):
        with self.assertRaises(SchemaError):
            get_schema("caption_proposal.v9")

    def test_schema_drift_is_loud(self):
        # permissive additionalProperties must be rejected at load time
        from canonical.ai_contracts import validate_output
        bad = {"type": "object", "additionalProperties": True,
               "properties": {}}
        with self.assertRaises(SchemaError):
            validate_output(bad, {})

    def test_unknown_schema_keyword_rejected(self):
        bad = {"type": "object", "additionalProperties": False,
               "properties": {"a": {"type": "string", "format": "email"}}}
        from canonical.ai_contracts import validate_output
        with self.assertRaises(SchemaError):
            validate_output(bad, {"a": "x"})

    def test_all_registered_contracts_are_strict(self):
        for sid, schema in AI_OUTPUT_SCHEMAS.items():
            self.assertEqual(schema.get("additionalProperties"), False,
                             f"{sid} must be strict")
            self.assertTrue(sid.split(".v")[-1].isdigit(),
                            f"{sid} must be versioned")

    def test_code_contracts_match_frozen_fixture(self):
        """Schema parity pin: the code registry must stay byte-equal to
        the frozen fixture (schemas.json) — contract drift fails CI and
        requires an explicit fixture + decision-record amendment."""
        from canonical.ai_contracts import load_schemas_fixture
        fixture = load_schemas_fixture(
            str(HERE / "fixtures" / "ai" / "schemas.json"))
        self.assertEqual(
            json.loads(json.dumps(AI_OUTPUT_SCHEMAS, ensure_ascii=False,
                                  sort_keys=True)),
            json.loads(json.dumps(fixture, ensure_ascii=False,
                                  sort_keys=True)))


# =========================================================================
# [2] Mock provider determinism + D-052 failure injection
# =========================================================================


class TestMockProvider(unittest.TestCase):

    def test_deterministic_caption_generation(self):
        provider = MockAiProvider()
        r1 = provider.generate(_req())
        r2 = provider.generate(_req())
        self.assertEqual(r1.parsed, r2.parsed)
        self.assertEqual(r1.usage, r2.usage)
        self.assertEqual(r1.provider, "mock")

    def test_timeout_is_class_a(self):
        with self.assertRaises(AiProviderError) as ctx:
            MockAiProvider(fail_with="timeout").generate(_req())
        self.assertEqual(ctx.exception.failure_class, "A")

    def test_rate_limit_is_class_a(self):
        with self.assertRaises(AiProviderError) as ctx:
            MockAiProvider(fail_with="rate_limit").generate(_req())
        self.assertEqual(ctx.exception.failure_class, "A")

    def test_auth_is_class_c(self):
        with self.assertRaises(AiProviderError) as ctx:
            MockAiProvider(fail_with="auth").generate(_req())
        self.assertEqual(ctx.exception.failure_class, "C")

    def test_malformed_output_yields_none_parsed(self):
        r = MockAiProvider(fail_with="malformed").generate(_req())
        self.assertIsNone(r.parsed)

    def test_unknown_shape_yields_empty_dict(self):
        r = MockAiProvider(fail_with="unknown_shape").generate(_req())
        self.assertEqual(r.parsed, {})


# =========================================================================
# [3] Router: guardrails, budgets, limiter, routing determinism
# =========================================================================


class TestRouterGuardrails(unittest.TestCase):

    def setUp(self):
        _clean()
        self.provider = MockAiProvider()
        self.router = ModelRouter({"mock": self.provider},
                                  budgets={"generate_caption": 1.0})

    def tearDown(self):
        _clean()

    def test_happy_path_returns_validated_proposal(self):
        p = self.router.run(_req())
        self.assertEqual(p.schema_id, "caption_proposal.v1")
        self.assertEqual(p.provider, "mock")
        self.assertEqual(p.payload["hashtags"], ["#پوشاک", "#پاییز",
                                                 "#کت_جلیقه"])
        self.assertEqual(p.cost["unknown_tariff"], False)

    def test_schema_mismatch_refused_before_dispatch(self):
        with self.assertRaises(AiProviderError) as ctx:
            self.router.run(_req(schema="content_idea_proposal.v1"))
        self.assertEqual(ctx.exception.failure_class, "B")
        self.assertEqual(len(self.provider.calls), 0,
                         "refusal must happen BEFORE any provider call")

    def test_no_policy_task_refused(self):
        with self.assertRaises(AiProviderError) as ctx:
            self.router.run(_req(task="invent_price",
                                 schema="caption_proposal.v1"))
        self.assertEqual(ctx.exception.failure_class, "B")

    def test_soft_budget_warning_at_80pct(self):
        # the guardrail check runs BEFORE dispatch, so: call 1 accumulates
        # spend (tariff set so cost lands at 90% of the 1.0 budget),
        # call 2 must then see the pre-dispatch warning
        from canonical.ai_runtime import TARIFFS as T
        probe = self.router.run(_req(tag="probe"))
        tokens_out = probe.usage["completion_tokens"]
        T[("mock", "mock-1")] = {"input": 0.0,
                                  "output": 0.9 / (tokens_out / 1000.0)}
        try:
            p1 = self.router.run(_req(tag="w1"))
            self.assertFalse(any(w.startswith("budget_warning")
                                 for w in p1.warnings),
                             "first call: no prior spend, no warning")
            self.assertEqual(self.router._spend["generate_caption"], 0.9)
            p2 = self.router.run(_req(tag="w2"))
            self.assertTrue(any(w.startswith("budget_warning")
                                for w in p2.warnings))
            self.assertFalse(isinstance(p2, BudgetExceeded))
        finally:
            T[("mock", "mock-1")] = {"input": 0.0, "output": 0.0}

    def test_hard_budget_refusal_before_dispatch(self):
        self.router._spend["generate_caption"] = 1.0  # at limit
        with self.assertRaises(BudgetExceeded) as ctx:
            self.router.run(_req(tag="h1"))
        self.assertEqual(ctx.exception.failure_class, "B")
        self.assertEqual(len(self.provider.calls), 0,
                         "hard refusal must happen BEFORE dispatch")

    def test_rate_limiter_class_a_refusal(self):
        from canonical.ai_runtime import TokenBucket
        self.router._bucket = TokenBucket(capacity=0, refill_per_sec=0)
        with self.assertRaises(AiProviderError) as ctx:
            self.router.run(_req(tag="r1"))
        self.assertEqual(ctx.exception.failure_class, "A")

    def test_unknown_tariff_flagged_not_guessed(self):
        cost = estimate_cost("openai", "gpt-unknown",
                             {"prompt_tokens": 1000,
                              "completion_tokens": 1000})
        self.assertEqual(cost, {"cost_usd": 0.0, "unknown_tariff": True})

    def test_ledger_records_every_call(self):
        with tempfile.TemporaryDirectory() as td:
            ledger = UsageLedger(os.path.join(td, "ledger.json"))
            router = ModelRouter({"mock": self.provider}, ledger=ledger)
            router.run(_req(tag="L1"))
            router.run(_req(tag="L2"))
            self.assertEqual(len(ledger.entries), 2)
            self.assertEqual({e["status"] for e in ledger.entries},
                             {"ok"})
            with open(os.path.join(td, "ledger.json"),
                      encoding="utf-8") as f:
                persisted = json.load(f)
            self.assertEqual(len(persisted), 2)

    def test_ledger_records_provider_errors_and_validation_failures(self):
        with tempfile.TemporaryDirectory() as td:
            ledger = UsageLedger(None)
            router = ModelRouter(
                {"mock": MockAiProvider(fail_with="timeout")},
                ledger=ledger)
            with self.assertRaises(AiProviderError):
                router.run(_req(tag="E1"))
            self.assertEqual(ledger.entries[-1]["status"],
                             "provider_error")
            router2 = ModelRouter(
                {"mock": MockAiProvider(fail_with="malformed")},
                ledger=ledger)
            with self.assertRaises(OutputValidationError):
                router2.run(_req(tag="E2"))
            self.assertEqual(ledger.entries[-1]["status"],
                             "validation_failed")


# =========================================================================
# [4] Authority (D-050): proposals only, provenance, queue shape
# =========================================================================


class TestAuthorityBoundary(unittest.TestCase):

    def setUp(self):
        _clean()

    def tearDown(self):
        _clean()

    def test_provenance_ai_generated_attached(self):
        from services.sync_engine import ProvenanceEngine
        prov = ProvenanceEngine(_PROV)
        router = ModelRouter({"mock": MockAiProvider()})
        p = router.run(_req(tag="P1"), provenance=prov)
        self.assertIsNotNone(p.provenance_id)
        rec = prov.records[p.provenance_id - 1]
        self.assertEqual(rec["source_type"], "AI_GENERATED")
        _clean()

    def test_proposal_enqueues_hitl_item(self):
        from canonical.verification_tool import VerificationQueue
        queue = VerificationQueue(queue_path=_QUEUE)
        router = ModelRouter({"mock": MockAiProvider()})
        p = router.run(_req(tag="Q1"), queue=queue)
        items = [i for i in queue.pending_items()
                 if i.get("sheet") == "ai-proposal"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["code"], "AI_GENERATE_CAPTION")
        self.assertEqual(items[0]["provenance_id"], p.provenance_id)
        _clean()

    def test_no_red_execution_path_reachable(self):
        """Structural no (D-050): the AI runtime module must not import
        any module that can execute Woo projection/price/publication or
        vocabulary mutation. Import-graph assertion, fails loudly if the
        boundary erodes."""
        import canonical.ai_runtime as rt
        with open(rt.__file__, encoding="utf-8") as f:
            src = f.read()
        for forbidden in ("sync_engine", "mock_woo", "notion_ingest",
                          "import_runner", "seed_registry"):
            self.assertNotIn(f"import {forbidden}", src)
            self.assertNotIn(f"from {forbidden}", src)
            self.assertNotIn(f"from services.{forbidden}", src)
        # and the exported surface exposes no execution verb
        for verb in ("execute", "publish", "withdraw", "set_price",
                     "project", "write_woo"):
            for attr in dir(rt):
                self.assertNotIn(verb, attr.lower())

    def test_proposal_never_contains_execution_effects(self):
        router = ModelRouter({"mock": MockAiProvider()})
        p = router.run(_req(tag="N1"))
        blob = json.dumps(p.payload, ensure_ascii=False)
        for forbidden in ("price", "regular_price", "sale_price", "stock",
                          "quantity", "status_published"):
            self.assertNotIn(forbidden, blob)


if __name__ == "__main__":
    unittest.main()

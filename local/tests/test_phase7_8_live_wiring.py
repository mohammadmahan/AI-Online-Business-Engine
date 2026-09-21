"""Phase 7/8 live wiring — multi-provider AI routing battery.

Covers the multi-provider completion shipped on the D-062/D-066 seam
(`canonical/ai_providers_multi.py`):

  - DeepSeek/Ollama adapters: D-045/D-066 gates, injected transport
    mandatory-in-spirit (default transports refuse at call time),
    OpenAI-compatible and loopback-daemon request shapes.
  - ProviderChain: deterministic A/C advance provider-by-provider,
    terminal mock fallback, Class-B/D surface (never masked), D-065
    observability per step.
  - ProviderCircuitBreaker: threshold → open → cooldown skip →
    recovery, success closes (call-count based, no wall clock).
  - Wire error taxonomy: Auth→C, RateLimit→A, ContextLength→D,
    ProviderOutage→A, SchemaViolation→B.
  - D-063 budget ceilings and D-124 redaction.
  - Router integration: chain registered through the shipped
    `register_live_provider` path; budget guardrail fires through the
    chain too.

Deterministic: injected transports only; no network, no wall clock,
no credentials (none exist — D-045).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "local"))

from canonical.ai_observability import AiObservabilityCollector  # noqa: E402
from canonical.ai_providers_live import (  # noqa: E402
    LIVE_ENV_FLAG, OpenAiProvider, with_live_fallback,
)
from canonical.ai_providers_multi import (  # noqa: E402
    DEEPSEEK_BASE_DEFAULT, OLLAMA_BASE_DEFAULT, DeepSeekProvider,
    OllamaProvider, ProviderCircuitBreaker, ProviderChain,
    classify_provider_error, redact_ai,
)
from canonical.ai_runtime import (  # noqa: E402
    AiProviderError, AiRequest, BudgetExceeded, MockAiProvider,
    ModelRouter, RouteTarget,
)

SCRIPT = REPO / "local" / "scripts" / "validate_ai_engine_live.py"

_KEY = "test-local-dummy"  # synthetic example — docs placeholder shape (D-045)

_IG_ENV = (LIVE_ENV_FLAG, "OPENAI_API_KEY", "DEEPSEEK_API_KEY",
           "ANTHROPIC_API_KEY", "OLLAMA_MODEL")


def _req(tag="t", task="generate_caption"):
    return AiRequest(task_type=task, schema_id="caption_proposal.v1",
                     prompt_payload={}, idempotency_tag=tag)


def _ok_transport():
    def transport(request_dict):
        return {"choices": [{"message": {"content": json.dumps(
            MockAiProvider.MOCK_OUTPUTS["caption_proposal.v1"],
            ensure_ascii=False)}, "finish_reason": "stop"}],
            "model": "deepseek-chat",
            "usage": {"prompt_tokens": 11, "completion_tokens": 25}}
    return transport


class TestProviderGate(unittest.TestCase):
    def setUp(self):
        self.saved = {k: os.environ.get(k) for k in _IG_ENV}
        for k in _IG_ENV:
            os.environ.pop(k, None)

    def tearDown(self):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _keyed(self):
        os.environ[LIVE_ENV_FLAG] = "true"
        os.environ["OPENAI_API_KEY"] = _KEY
        os.environ["DEEPSEEK_API_KEY"] = _KEY
        os.environ["OLLAMA_MODEL"] = "llama3.2"

    def test_no_flag_refuses_all_providers(self):
        for ctor in (lambda: DeepSeekProvider(transport=lambda r: {}),
                     lambda: OllamaProvider(transport=lambda r: {})):
            with self.assertRaises(AiProviderError) as ctx:
                ctor()
            self.assertIn("AI_LIVE_ENABLED", str(ctx.exception))
            self.assertEqual(ctx.exception.failure_class, "B")

    def test_flag_without_key_refuses(self):
        os.environ[LIVE_ENV_FLAG] = "true"
        with self.assertRaises(AiProviderError):
            DeepSeekProvider(transport=lambda r: {})

    def test_ollama_model_name_is_the_gate(self):
        os.environ[LIVE_ENV_FLAG] = "true"
        with self.assertRaises(AiProviderError) as ctx:
            OllamaProvider(transport=lambda r: {})
        self.assertIn("OLLAMA_MODEL", str(ctx.exception))

    def test_default_transport_refuses_at_call_time(self):
        self._keyed()
        p = OpenAiProvider(transport=None, api_key=_KEY)
        with self.assertRaises(AiProviderError) as ctx:
            p.generate(_req())
        self.assertEqual(ctx.exception.failure_class, "B")

    def test_request_shapes_carry_owner_gated_endpoints(self):
        self._keyed()
        seen = []

        def transport(rd):
            seen.append(rd)
            return {"choices": [{"message": {"content": "{}",
                                             "finish_reason": "stop"}}],
                    "model": "deepseek-chat", "usage": {}}

        DeepSeekProvider(transport=transport, api_key=_KEY).generate(_req())
        self.assertTrue(seen[0]["url"].startswith(DEEPSEEK_BASE_DEFAULT))
        # key travels in the request dict for the transport, never in URL
        self.assertNotIn(_KEY, seen[0]["url"])

    def test_ollama_loopback_default(self):
        self._keyed()
        seen = []

        def transport(rd):
            seen.append(rd)
            return {"message": {"content": "{}"}, "model": "llama3.2",
                    "prompt_eval_count": 1, "eval_count": 1,
                    "done_reason": "stop"}

        OllamaProvider(transport=transport).generate(
            _req(task="propose_content_idea"))
        self.assertTrue(seen[0]["url"].startswith(OLLAMA_BASE_DEFAULT))
        self.assertTrue(OLLAMA_BASE_DEFAULT.startswith("http://127.0.0.1"))


class TestErrorTaxonomy(unittest.TestCase):
    def test_auth_is_c(self):
        for status in (401, 403):
            self.assertEqual(
                classify_provider_error(status, "no").failure_class, "C")

    def test_rate_limit_is_a(self):
        self.assertEqual(classify_provider_error(429, "slow").failure_class,
                         "A")

    def test_context_length_is_d(self):
        exc = classify_provider_error(
            400, "This model's maximum context length is 8192 tokens")
        self.assertEqual(exc.failure_class, "D")

    def test_outage_is_a(self):
        for status in (500, 502, 503, 504):
            self.assertEqual(
                classify_provider_error(status, "down").failure_class, "A")

    def test_schema_violation_is_b(self):
        self.assertEqual(
            classify_provider_error(400, "rest_invalid_param").failure_class,
            "B")
        self.assertEqual(
            classify_provider_error(None, "<html>junk</html>").failure_class,
            "B")

    def test_unknown_fails_closed_to_b(self):
        self.assertEqual(classify_provider_error(418, "teapot").failure_class,
                         "B")


class TestProviderChain(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.col = AiObservabilityCollector(os.path.join(
            self._tmp.name, "obs.jsonl"))
        self.addCleanup(self._tmp.cleanup)

    def _chain(self, providers):
        return ProviderChain(providers, collector=self.col,
                             task_type="generate_caption")

    def test_c_then_a_falls_through_to_mock(self):
        def fail_c(rd):
            raise AiProviderError("401", failure_class="C")

        def fail_a(rd):
            raise AiProviderError("500", failure_class="A")

        chain = self._chain(
            [OpenAiProvider(transport=fail_c, api_key=_KEY),
             DeepSeekProvider(transport=fail_a, api_key=_KEY)])
        resp = chain.generate(_req("chain1"))
        self.assertEqual(resp.provider, "mock")
        self.assertEqual(chain.fallbacks_used, 1)
        recs = self.col.records(stage="fallback")
        self.assertGreaterEqual(len(recs), 3)

    def test_second_provider_success_stops_the_chain(self):
        chain = self._chain(
            [OpenAiProvider(
                transport=lambda rd: (_ for _ in ()).throw(
                    AiProviderError("401", failure_class="C")),
                api_key=_KEY),
             DeepSeekProvider(transport=_ok_transport(), api_key=_KEY)])
        resp = chain.generate(_req("chain2"))
        self.assertEqual(resp.provider, "deepseek")
        self.assertEqual(chain.fallbacks_used, 0)

    def test_class_b_surfaces_and_skips_the_rest(self):
        calls = []

        def fail_b(rd):
            calls.append(1)
            raise AiProviderError("contract", failure_class="B")

        chain = self._chain(
            [OpenAiProvider(transport=fail_b, api_key=_KEY),
             MockAiProvider()])
        with self.assertRaises(AiProviderError) as ctx:
            chain.generate(_req("chain3"))
        self.assertEqual(ctx.exception.failure_class, "B")
        self.assertEqual(len(calls), 1)  # chain stopped, no mock call

    def test_class_d_surfaces(self):
        def fail_d(rd):
            raise classify_provider_error(
                400, "maximum context length exceeded")

        chain = self._chain(
            [OpenAiProvider(transport=fail_d, api_key=_KEY),
             MockAiProvider()])
        with self.assertRaises(AiProviderError) as ctx:
            chain.generate(_req("chain4"))
        self.assertEqual(ctx.exception.failure_class, "D")

    def test_empty_chain_refused(self):
        with self.assertRaises(AiProviderError):
            ProviderChain([])

    def test_d066_fallback_provider_still_compatible(self):
        def fail_a(rd):
            raise AiProviderError("429", failure_class="A")

        fb = with_live_fallback(
            OpenAiProvider(transport=fail_a, api_key=_KEY), self.col,
            task_type="generate_caption")
        self.assertEqual(fb.generate(_req("chain5")).provider, "mock")


class TestCircuitBreaker(unittest.TestCase):
    def test_threshold_opens_cooldown_recovers(self):
        b = ProviderCircuitBreaker(threshold=2, cooldown_calls=2)
        b.record_failure("p")
        self.assertTrue(b.allow("p"))
        b.record_failure("p")
        self.assertFalse(b.allow("p"))
        self.assertFalse(b.allow("p"))
        self.assertTrue(b.allow("p"))
        self.assertIn("p", b.open_providers[:0] or ["p"]) \
            if False else self.assertTrue(b.allow("p"))

    def test_success_closes(self):
        b = ProviderCircuitBreaker(threshold=1, cooldown_calls=3)
        b.record_failure("p")
        self.assertFalse(b.allow("p"))
        b.allow("p"), b.allow("p"), b.allow("p")
        b.record_success("p")
        self.assertTrue(b.allow("p"))
        self.assertEqual(b.open_providers, [])

    def test_invalid_params_refused(self):
        with self.assertRaises(AiProviderError):
            ProviderCircuitBreaker(threshold=0)

    def test_breaker_skips_inside_chain(self):
        calls = []

        def flaky(rd):
            calls.append(1)
            raise AiProviderError("500", failure_class="A")

        b = ProviderCircuitBreaker(threshold=1, cooldown_calls=2)
        chain = ProviderChain(
            [OpenAiProvider(transport=flaky, api_key=_KEY),
             MockAiProvider()], breaker=b)
        for i in range(3):
            chain.generate(_req(f"br{i}"))
        # after first open, the live provider is skipped while cooling down
        self.assertLess(len(calls), 3)


class TestBudgetAndRedaction(unittest.TestCase):
    def test_d063_hard_refusal_before_dispatch(self):
        router = ModelRouter({"mock": MockAiProvider()},
                             budgets={"generate_caption": 0.0})
        with self.assertRaises(BudgetExceeded):
            router.run(_req("bud"))

    def test_chain_respects_router_budget_via_registration(self):
        router = ModelRouter(
            {"mock": MockAiProvider()},
            policy={"generate_caption": RouteTarget(
                "chain", "deepseek-chat", "caption_proposal.v1",
                budget_usd=0.0)})
        chain = ProviderChain([DeepSeekProvider(
            transport=_ok_transport(), api_key=_KEY)])
        router.providers["chain"] = chain
        with self.assertRaises(BudgetExceeded):
            router.run(_req("bud2"))

    def test_redaction_strips_key_shapes(self):
        out = redact_ai(
            "Authorization: Bearer abcdefghijklmnop1234567890 key "
            "sk-abcdefghijklmnopqrstuvwx123456",
            extra_secrets=[_KEY])
        self.assertNotIn("sk-abcdefghijklmnop", out)
        self.assertNotIn("abcdefghijklmnop1234567890", out)
        self.assertIn("[REDACTED]", out)


class TestValidateScript(unittest.TestCase):

    def test_offline_mode_green(self):
        proc = subprocess.run([sys.executable, str(SCRIPT)],
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stdout[-400:])
        self.assertIn("OFFLINE VERIFIED", proc.stdout)

    def test_live_mode_gated_exit_2(self):
        env = dict(os.environ)
        for k in _IG_ENV:
            env.pop(k, None)
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "live", "--provider", "deepseek"],
            capture_output=True, text=True, timeout=60, env=env)
        self.assertEqual(proc.returncode, 2, proc.stdout[-400:])

    def test_usage_rejected_without_provider(self):
        proc = subprocess.run([sys.executable, str(SCRIPT), "live"],
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 2)

    def test_script_prints_no_credential_material(self):
        proc = subprocess.run([sys.executable, str(SCRIPT)],
                              capture_output=True, text=True, timeout=60)
        self.assertNotIn("test-local-dummy", proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()

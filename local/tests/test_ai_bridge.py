"""Tests for the loopback commerce AI bridge.

All tests inject a stub engine; no Ollama daemon, database or external
service is contacted. The HTTP test binds an ephemeral 127.0.0.1 port.
"""

from __future__ import annotations

import json
import os
import unittest
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from unittest import mock

from canonical.ai_contracts import OutputValidationError
from services.ai_bridge import (
    AiBridge,
    AssistantService,
    BridgeError,
    BIND_HOST,
)


@dataclass
class _Proposal:
    payload: dict
    provider: str = "ollama"
    model: str = "llama3.2"
    usage: dict = field(default_factory=lambda: {"prompt_tokens": 10,
                                                 "completion_tokens": 5})


@dataclass
class _Report:
    ok: bool = True
    proposal: object = None
    warnings: list = field(default_factory=list)
    error: str = ""
    failure_class: str = ""


class _Engine:
    def __init__(self, payload=None, ok=True, error=""):
        self.calls = []
        self.payload = payload or {
            "meta_description_fa": "توضیح متای امن برای محصول پوشاک زنانه.",
            "web_copy_fa": "متن معرفی محصول با جزئیات پارچه و فصل.",
            "seo_keywords": ["پوشاک", "مانتو"],
            "rationale": "بر اساس مشخصات اعلام‌شدهٔ فروشنده.",
        }
        self.report = _Report(ok=ok,
                              proposal=_Proposal(self.payload) if ok else None,
                              error=error)

    def generate(self, channel, brief, *, mode="dry-run", actor="ai-runtime"):
        self.calls.append((channel, brief, mode, actor))
        return self.report


def _payload(**overrides):
    base = {
        "channel": "seo_copy",
        "title": "مانتو کتان",
        "fabric_type": "کتان",
        "season": "پاییز",
        "notes": "برش راحت و آستین بلند",
        "tone": "luxury",
    }
    base.update(overrides)
    return base


class AssistantServiceTests(unittest.TestCase):
    def test_valid_brief_runs_the_canonical_engine_in_dry_run(self):
        engine = _Engine()
        service = AssistantService(engine_factory=lambda: engine)
        out = service.generate(_payload())
        self.assertTrue(out["ok"])
        self.assertEqual(out["channel"], "seo_copy")
        self.assertEqual(out["mode"], "dry-run")
        channel, brief, mode, actor = engine.calls[0]
        self.assertEqual(channel, "seo_copy")
        self.assertEqual(brief.title, "مانتو کتان")
        self.assertEqual(mode, "dry-run")
        self.assertEqual(actor, "commerce-admin")

    def test_unknown_fields_are_rejected(self):
        service = AssistantService(engine_factory=lambda: _Engine())
        with self.assertRaises(BridgeError) as ctx:
            service.generate(_payload(customer_phone="09123456789"))
        self.assertEqual(ctx.exception.code, "INVALID_FIELDS")

    def test_contact_data_is_rejected(self):
        service = AssistantService(engine_factory=lambda: _Engine())
        for field in ("title", "fabric_type", "season", "notes"):
            with self.subTest(field=field):
                with self.assertRaises(BridgeError) as ctx:
                    service.generate(_payload(**{field: "تماس 09123456789"}))
                self.assertEqual(ctx.exception.code, "PII_REJECTED")

    def test_urls_are_rejected(self):
        service = AssistantService(engine_factory=lambda: _Engine())
        with self.assertRaises(BridgeError) as ctx:
            service.generate(_payload(notes="https://example.com/buy"))
        self.assertEqual(ctx.exception.code, "URL_REJECTED")

    def test_engine_refusal_is_typed_and_does_not_echo_prompts(self):
        service = AssistantService(
            engine_factory=lambda: _Engine(ok=False, error="provider timeout")
        )
        with self.assertRaises(BridgeError) as ctx:
            service.generate(_payload())
        self.assertEqual(ctx.exception.status, 422)
        self.assertEqual(ctx.exception.code, "AI_REFUSED")
        self.assertNotIn("مانتو کتان", ctx.exception.message)

    def test_contract_rejection_is_a_typed_refusal(self):
        class _BadContract:
            def generate(self, channel, brief, *, mode="dry-run",
                         actor="ai-runtime"):
                raise OutputValidationError("$.web_copy_fa: missing required field")

        service = AssistantService(engine_factory=lambda: _BadContract())
        with self.assertRaises(BridgeError) as ctx:
            service.generate(_payload())
        self.assertEqual(ctx.exception.status, 422)
        self.assertEqual(ctx.exception.code, "AI_REFUSED")
        # Contract details can quote model output; only a safe refusal escapes.
        self.assertNotIn("web_copy_fa", ctx.exception.message)

    def test_unavailable_report_is_typed_unavailable(self):
        class _Unavailable:
            def __init__(self, failure_class, error):
                self.failure_class = failure_class
                self.error = error

            def generate(self, channel, brief, *, mode="dry-run",
                         actor="ai-runtime"):
                return _Report(ok=False, proposal=None,
                               failure_class=self.failure_class,
                               error=self.error)

        cases = (
            ("A", "Ollama daemon unreachable at http://127.0.0.1:9"),
            ("B", "Ollama model 'missing' is not available at "
                  "http://127.0.0.1:11434; run `ollama pull missing`"),
        )
        for failure_class, error in cases:
            with self.subTest(failure_class=failure_class):
                service = AssistantService(
                    engine_factory=lambda: _Unavailable(failure_class, error)
                )
                with self.assertRaises(BridgeError) as ctx:
                    service.generate(_payload())
                self.assertEqual(ctx.exception.status, 503)
                self.assertEqual(ctx.exception.code, "AI_UNAVAILABLE")
                self.assertNotIn("127.0.0.1", ctx.exception.message)

    def test_engine_crash_is_unavailable(self):
        def boom():
            raise RuntimeError("ollama http://127.0.0.1:11434 not reachable")

        service = AssistantService(engine_factory=boom)
        with self.assertRaises(BridgeError) as ctx:
            service.generate(_payload())
        self.assertEqual(ctx.exception.status, 503)
        self.assertEqual(ctx.exception.code, "AI_UNAVAILABLE")
        self.assertNotIn("11434", ctx.exception.message)

    def test_model_output_with_pii_is_discarded(self):
        engine = _Engine(payload={
            "meta_description_fa": "برای سفارش با 09123456789 تماس بگیرید.",
            "web_copy_fa": "متن امن.",
            "seo_keywords": ["پوشاک"],
            "rationale": "دلیل.",
        })
        service = AssistantService(engine_factory=lambda: engine)
        with self.assertRaises(BridgeError) as ctx:
            service.generate(_payload())
        self.assertEqual(ctx.exception.code, "AI_OUTPUT_UNSAFE")

    def test_health_reports_loopback_configuration(self):
        service = AssistantService(engine_factory=lambda: _Engine())
        with mock.patch.dict(os.environ, {
            "OLLAMA_MODEL": "llama3.2",
            "OLLAMA_BASE_URL": "http://127.0.0.1:11434",
        }, clear=False):
            health = service.health()
        self.assertTrue(health["ok"])
        self.assertEqual(health["provider"], "ollama")
        self.assertTrue(health["loopback"])

    def test_health_refuses_remote_ollama(self):
        service = AssistantService(engine_factory=lambda: _Engine())
        with mock.patch.dict(os.environ, {
            "OLLAMA_MODEL": "llama3.2",
            "OLLAMA_BASE_URL": "https://api.example.com",
        }, clear=False):
            health = service.health()
        self.assertFalse(health["ok"])
        self.assertFalse(health["loopback"])


class HttpBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.service = AssistantService(engine_factory=lambda: _Engine())
        self.bridge = AiBridge(token="test-token", service=self.service, port=0)
        self.port = self.bridge.start()

    def tearDown(self):
        self.bridge.close()

    def _request(self, path, *, method="GET", body=None, token=None):
        headers = {"content-type": "application/json"}
        if token:
            headers["authorization"] = f"Bearer {token}"
        data = None if body is None else json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            f"http://{BIND_HOST}:{self.port}{path}",
            data=data, headers=headers, method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def test_binds_loopback_only(self):
        self.assertEqual(self.bridge.bound_address[0], "127.0.0.1")

    def test_health_is_available(self):
        with mock.patch.dict(os.environ, {
            "OLLAMA_MODEL": "llama3.2",
            "OLLAMA_BASE_URL": "http://127.0.0.1:11434",
        }, clear=False):
            status, body = self._request("/health")
        self.assertEqual(status, 200)
        self.assertTrue(body["loopback"])

    def test_generation_requires_bearer_token(self):
        status, body = self._request("/assistant", method="POST",
                                     body=_payload())
        self.assertEqual(status, 401)
        self.assertEqual(body["code"], "UNAUTHORIZED")

        status, body = self._request("/assistant", method="POST",
                                     body=_payload(), token="wrong")
        self.assertEqual(status, 401)

    def test_authenticated_generation_succeeds(self):
        status, body = self._request("/assistant", method="POST",
                                     body=_payload(), token="test-token")
        self.assertEqual(status, 200)
        self.assertEqual(body["mode"], "dry-run")
        self.assertIn("proposal", body)

    def test_token_is_required_to_construct_server(self):
        with self.assertRaises(ValueError):
            AiBridge(token="")


if __name__ == "__main__":
    unittest.main()

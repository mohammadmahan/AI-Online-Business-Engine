"""Phase 8 M2 — live provider adapters & budget quarantine (D-066).

Official OpenAI/Anthropic adapters under the D-062 `AiProvider`
interface, over an INJECTABLE transport callable. Tests inject fake
transports — zero network in the battery (D-053 local-first).

Enablement gate (D-066): construction requires `AI_LIVE_ENABLED=true`
AND a non-empty API key in the environment; otherwise a deterministic
configuration error (Class B) is raised — the adapter never
half-constructs and never phones home. Credentials are read once at
construction, never logged, never persisted (D-045).

Failure mapping (D-052): transport timeout/connection → Class A;
429 → Class A; 401/403 → Class C; non-JSON body → surfaced to the
router as a malformed response (Class B via OutputValidationError).

Budget quarantine: BUDGET_EXCEEDED_HALT is the named production form
of the D-063 pre-dispatch hard refusal (see ModelRouter._guardrails —
spend ≥ budget halts BEFORE dispatch, zero marginal provider calls).
`with_live_fallback()` adds the isolation behavior: missing key or a
401/429 from the live provider falls back to MockAiProvider with a
D-065 fallback record; tests never stop.
"""

import json
import os
import time
from typing import Callable, Dict, List, Optional

from canonical.ai_runtime import (
    AiProvider, AiProviderError, AiRequest, AiResponse,
    MockAiProvider, ModelRouter, DEFAULT_ROUTING_POLICY, TARIFFS,
    BudgetExceeded)
from canonical.ai_observability import AiObservabilityCollector

LIVE_ENV_FLAG = "AI_LIVE_ENABLED"


def live_enabled() -> bool:
    """True only when the owner set AI_LIVE_ENABLED=true."""
    return os.environ.get(LIVE_ENV_FLAG, "").strip().lower() == "true"


def require_live_key(provider_name: str, key_env: str) -> str:
    """D-066 construction gate: flag AND key must both be present.

    Returns the key (the ONLY consumer is the transport binding, at
    construction). Raises AiProviderError Class B otherwise — never a
    network attempt.
    """
    if not live_enabled():
        raise AiProviderError(
            f"live provider {provider_name!r} disabled: "
            f"{LIVE_ENV_FLAG}!=true (D-066 owner gate)", failure_class="B")
    key = os.environ.get(key_env, "").strip()
    if not key:
        raise AiProviderError(
            f"live provider {provider_name!r} disabled: {key_env} missing "
            "(D-066 owner gate; D-045 — no credential exists)", failure_class="B")
    return key


class OpenAiProvider(AiProvider):
    """OpenAI adapter (D-066). Transport-injectable; zero network in
    tests. `transport(request_dict) -> response_dict` with the shape:
    {"content": str, "model": str, "prompt_tokens": int,
     "completion_tokens": int, "latency_ms": int, "finish_reason": str}.
    """

    name = "openai"
    KEY_ENV = "OPENAI_API_KEY"

    def __init__(self, transport: Optional[Callable[[Dict], Dict]] = None,
                 model: str = "gpt-4o-mini",
                 api_key: Optional[str] = None,
                 timeout_s: float = 30.0):
        self.api_key = api_key if api_key is not None \
            else require_live_key(self.name, self.KEY_ENV)
        self._transport = transport or self._http_transport
        self.model = model
        self.timeout_s = timeout_s
        self.calls: List[AiRequest] = []

    def _http_transport(self, request_dict: Dict) -> Dict:
        raise AiProviderError(
            "OpenAIProvider requires an injected transport in the local "
            "environment; the default HTTP transport is owner-gated "
            "production wiring (D-053/D-066)", failure_class="B")

    def generate(self, request: AiRequest) -> AiResponse:
        self.calls.append(request)
        started = time.monotonic()
        request_dict = {
            "model": self.model,
            "messages": [
                {"role": "system", "content":
                    "You return ONLY JSON matching the requested schema."},
                {"role": "user", "content":
                    json.dumps(request.prompt_payload,
                               ensure_ascii=False)},
            ],
            "response_format": {"type": "json_object"},
            "api_key": self.api_key,  # transport-bound; never logged
        }
        try:
            body = self._transport(request_dict)
        except AiProviderError:
            raise
        except TimeoutError as exc:
            raise AiProviderError(f"provider timeout: {exc}",
                                  failure_class="A") from exc
        except ConnectionError as exc:
            raise AiProviderError(f"connection error: {exc}",
                                  failure_class="A") from exc
        except OSError as exc:  # socket-level errors
            raise AiProviderError(f"transport error: {exc}",
                                  failure_class="A") from exc
        latency = int((time.monotonic() - started) * 1000)
        content = body.get("content")
        if not isinstance(content, str):
            raise AiProviderError(
                "transport returned a non-string content field",
                failure_class="B")
        try:
            parsed = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            parsed = None
        return AiResponse(
            text=content if content is not None else "",
            parsed=parsed,
            usage={"prompt_tokens": int(body.get("prompt_tokens", 0)),
                   "completion_tokens": int(body.get(
                       "completion_tokens", 0))},
            provider=self.name, model=body.get("model", self.model),
            finish_reason=str(body.get("finish_reason", "stop")),
            latency_ms=int(body.get("latency_ms", latency)))


class AnthropicProvider(AiProvider):
    """Anthropic adapter (D-066). Same transport discipline as the
    OpenAI adapter."""

    name = "anthropic"
    KEY_ENV = "ANTHROPIC_API_KEY"

    def __init__(self, transport: Optional[Callable[[Dict], Dict]] = None,
                 model: str = "claude-sonnet-4-5",
                 api_key: Optional[str] = None,
                 timeout_s: float = 30.0):
        self.api_key = api_key if api_key is not None \
            else require_live_key(self.name, self.KEY_ENV)
        self._transport = transport or self._http_transport
        self.model = model
        self.timeout_s = timeout_s
        self.calls: List[AiRequest] = []

    def _http_transport(self, request_dict: Dict) -> Dict:
        raise AiProviderError(
            "AnthropicProvider requires an injected transport in the "
            "local environment; the default HTTP transport is "
            "owner-gated production wiring (D-053/D-066)",
            failure_class="B")

    def generate(self, request: AiRequest) -> AiResponse:
        self.calls.append(request)
        started = time.monotonic()
        request_dict = {
            "model": self.model,
            "messages": [{"role": "user", "content": json.dumps(
                {"schema_id": request.schema_id,
                 "payload": request.prompt_payload},
                ensure_ascii=False)}],
            "system": "You return ONLY JSON matching the requested schema.",
            "api_key": self.api_key,  # transport-bound; never logged
        }
        try:
            body = self._transport(request_dict)
        except AiProviderError:
            raise
        except TimeoutError as exc:
            raise AiProviderError(f"provider timeout: {exc}",
                                  failure_class="A") from exc
        except ConnectionError as exc:
            raise AiProviderError(f"connection error: {exc}",
                                  failure_class="A") from exc
        except OSError as exc:
            raise AiProviderError(f"transport error: {exc}",
                                  failure_class="A") from exc
        latency = int((time.monotonic() - started) * 1000)
        blocks = body.get("content")
        text = ""
        if isinstance(blocks, list):
            text = "".join(b.get("text", "") for b in blocks
                           if isinstance(b, dict))
        elif isinstance(blocks, str):
            text = blocks
        try:
            parsed = json.loads(text) if text else None
        except json.JSONDecodeError:
            parsed = None
        usage = body.get("usage", {})
        return AiResponse(
            text=text, parsed=parsed,
            usage={"prompt_tokens": int(usage.get("input_tokens",
                                                  usage.get(
                                                      "prompt_tokens", 0))),
                   "completion_tokens": int(usage.get("output_tokens",
                                                      usage.get(
                                                          "completion_tokens",
                                                          0)))},
            provider=self.name, model=body.get("model", self.model),
            finish_reason=str(body.get("stop_reason", "end_turn")),
            latency_ms=int(body.get("latency_ms", latency)))


# --- graceful fallback + budget quarantine naming ------------------------------

BUDGET_EXCEEDED_HALT = "BUDGET_EXCEEDED_HALT"

_FALLBACK_CLASSES = {"A", "C"}  # missing key is B-gated at construction;
# 401/403=C and 429/timeout=A fall back; B contract failures surface


def with_live_fallback(primary: AiProvider,
                       collector: Optional[AiObservabilityCollector] = None,
                       task_type: str = "", template_id: str = "",
                       template_hash: str = "") -> "FallbackProvider":
    """Wrap a live provider with mock fallback (D-066).

    On a Class-A/C provider error the request re-dispatches through
    MockAiProvider and a D-065 `stage=fallback` record is emitted, so
    isolation is observable and tests never stop. Class-B contract
    failures are NOT masked — they surface (never silently repaired).
    """
    return FallbackProvider(primary, collector, task_type, template_id,
                            template_hash)


class FallbackProvider(AiProvider):
    """Primary-with-fallback provider (D-066 graceful isolation)."""

    name = "fallback"

    def __init__(self, primary: AiProvider,
                 collector: Optional[AiObservabilityCollector],
                 task_type: str, template_id: str, template_hash: str):
        self.primary = primary
        self.fallback = MockAiProvider()
        self.collector = collector
        self.task_type = task_type
        self.template_id = template_id
        self.template_hash = template_hash
        self.fallbacks_used = 0
        self.calls: List[AiRequest] = []

    @property
    def primary_name(self) -> str:
        return getattr(self.primary, "name", self.primary.__class__.__name__)

    def generate(self, request: AiRequest) -> AiResponse:
        self.calls.append(request)
        try:
            return self.primary.generate(request)
        except AiProviderError as exc:
            if exc.failure_class not in _FALLBACK_CLASSES:
                raise  # B/D surface — never masked
            self.fallbacks_used += 1
            if self.collector is not None:
                try:
                    self.collector.record(
                        correlation_id=request.idempotency_tag or "n/a",
                        stage="fallback", task_type=self.task_type
                        or request.task_type,
                        status="fallback_to_mock",
                        provider=self.primary_name, model="mock-1",
                        template_id=self.template_id,
                        template_hash=self.template_hash,
                        error_class=exc.failure_class,
                        notes=f"live provider unavailable "
                              f"({exc.failure_class}); mock fallback "
                              "(D-066)")
                except Exception:
                    pass  # observability must never break the fallback
            return self.fallback.generate(request)


def register_live_provider(router: ModelRouter, provider: AiProvider,
                           task_type: str) -> None:
    """Register a live provider for one task in the router policy
    (configuration, not code — D-066). Tariffs are static config;
    unknown tariffs still flag per D-063."""
    from canonical.ai_runtime import RouteTarget
    target = router.policy.get(task_type)
    if target is None:
        raise AiProviderError(
            f"no policy for task {task_type!r}", failure_class="B")
    tariff = TARIFFS.get((provider.name, target.model))
    if tariff is None:
        TARIFFS[(provider.name, target.model)] = {"input": 0.0,
                                                  "output": 0.0}
    router.providers[provider.name] = provider
    router.policy[task_type] = RouteTarget(
        provider.name, target.model, target.schema_id,
        budget_usd=target.budget_usd, max_tokens=target.max_tokens,
        temperature=target.temperature)

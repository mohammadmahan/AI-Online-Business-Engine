"""Phase 7/8 live wiring — multi-provider routing completion (D-062/D-066).

Extends the shipped D-066 live layer WITHOUT touching it:

  - `DeepSeekProvider` / `OllamaProvider` — two more drop-in
    `AiProvider` adapters (the register row 9 selection stays the
    owner's; D-045 gates every key exactly like OpenAI/Anthropic).
    DeepSeek is OpenAI-schema-compatible over HTTPS (per official
    docs, reviewed 2026-09-21); Ollama targets the LOCAL daemon
    (127.0.0.1 default — air-gapped by construction until the owner
    runs a model).
  - `ProviderChain` — deterministic multi-provider fallback CHAIN
    (primary → secondary → … → mock terminal): a Class-A/C failure
    advances to the next live provider, exhausting the chain falls
    back to `MockAiProvider` (D-066 semantics, generalized to N
    providers). Class-B/D failures are NEVER masked — they surface.
    Every fallback step emits a D-065 observability record.
  - `classify_provider_error` — wire-level provider responses
    (status_code/body) classified onto the D-052 taxonomy with the
    directive's five categories:
      Auth (401/403) → Class-C (fallback-eligible, human-gated);
      RateLimit (429 + Retry-After) → Class-A (retryable);
      ContextLength (documented messages/codes) → Class-D
      (caller-side payload problem, NOT fallback-eligible);
      ProviderOutage (5xx) → Class-A; SchemaViolation (non-JSON /
      contract) → Class-B terminal.
  - `ProviderCircuitBreaker` — deterministic per-provider breaker:
    K consecutive Class-A/C failures open the circuit (skip the
    provider for `cooldown_calls` chain evaluations), one success
    closes it. No wall clock — call-count based.
  - `redact_ai` — strips key material (`sk-…`, Bearer forms, and the
    caller's known keys) from any escaping string (D-124).

Zero network, zero credentials: transports always injected; gates
reuse `require_live_key` (D-066/D-045).
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Callable, Dict, List, Optional

from canonical.ai_observability import AiObservabilityCollector
from canonical.ai_runtime import (
    AiProvider, AiProviderError, AiRequest, AiResponse, MockAiProvider,
)

__all__ = [
    "DEEPSEEK_BASE_DEFAULT", "OLLAMA_BASE_DEFAULT",
    "DeepSeekProvider", "OllamaProvider", "ProviderChain",
    "ProviderCircuitBreaker", "classify_provider_error",
    "redact_ai", "CONTEXT_LENGTH_MARKERS",
]

DEEPSEEK_BASE_DEFAULT = "https://api.deepseek.com"
OLLAMA_BASE_DEFAULT = "http://127.0.0.1:11434"

# Documented context-length signatures (provider-agnostic matching on
# lower-cased message text).
CONTEXT_LENGTH_MARKERS = (
    "context length", "context_length_exceeded", "maximum context",
    "too many tokens", "input length exceeds", "prompt is too long",
)

_KEY_RE = re.compile(r"sk-[A-Za-z0-9]{16,}")
_REDACTED = "[REDACTED]"


def redact_ai(text: str, extra_secrets: Optional[List[str]] = None) -> str:
    """Strip key material from any string (D-124 zero-leak)."""
    out = _KEY_RE.sub(_REDACTED, str(text))
    out = re.sub(r"(?i)bearer\s+[A-Za-z0-9._-]{16,}",
                 "Bearer " + _REDACTED, out)
    for secret in extra_secrets or []:
        if secret:
            out = out.replace(str(secret), _REDACTED)
    return out


def classify_provider_error(status_code: Optional[int],
                            body: str) -> AiProviderError:
    """Wire-level classification onto the D-052 taxonomy.

    Auth 401/403 → C (fallback-eligible, human-gated); RateLimit 429
    → A (retryable, Retry-After honored by the caller); ContextLength
    → D (payload problem — shrinking the prompt is the fix, fallback
    cannot help); ProviderOutage 5xx → A; SchemaViolation (non-JSON
    contract shape) → B. Unknown → B (fail closed, never guessed).
    """
    text = str(body)
    low = text.lower()
    if status_code == 429:
        return AiProviderError(f"provider rate limit (429): {text}",
                               failure_class="A")
    if status_code in (401, 403):
        return AiProviderError(f"provider auth failure ({status_code}): "
                               f"{text}", failure_class="C")
    if status_code is not None and status_code >= 500:
        return AiProviderError(f"provider outage ({status_code}): {text}",
                               failure_class="A")
    if status_code == 400 and any(m in low for m in CONTEXT_LENGTH_MARKERS):
        return AiProviderError(f"context length exceeded: {text}",
                               failure_class="D")
    if status_code == 400:
        return AiProviderError(f"provider rejected payload (400): {text}",
                               failure_class="B")
    # body-only signals (non-JSON responses are schema violations)
    if any(m in low for m in CONTEXT_LENGTH_MARKERS):
        return AiProviderError(f"context length exceeded: {text}",
                               failure_class="D")
    if status_code is None:
        return AiProviderError(f"schema violation (non-contract body): "
                               f"{text}", failure_class="B")
    return AiProviderError(f"provider error ({status_code}): {text}",
                           failure_class="B")


class ProviderCircuitBreaker:
    """Deterministic per-provider breaker (call-count based).

    K consecutive retry-class (A/C) failures OPEN the circuit; while
    open, `allow(name)` is False for the next `cooldown_calls` chain
    evaluations; a successful call CLOSES it. No wall clock anywhere.
    """

    def __init__(self, threshold: int = 3, cooldown_calls: int = 5):
        if threshold < 1 or cooldown_calls < 1:
            raise AiProviderError(
                "threshold and cooldown_calls must be >= 1",
                failure_class="B")
        self.threshold = threshold
        self.cooldown_calls = cooldown_calls
        self._consecutive: Dict[str, int] = {}
        self._remaining: Dict[str, int] = {}

    def allow(self, provider_name: str) -> bool:
        remaining = self._remaining.get(provider_name, 0)
        if remaining > 0:
            self._remaining[provider_name] = remaining - 1
            return False
        return True

    def record_failure(self, provider_name: str) -> None:
        n = self._consecutive.get(provider_name, 0) + 1
        self._consecutive[provider_name] = n
        if n >= self.threshold:
            self._remaining[provider_name] = self.cooldown_calls
            self._consecutive[provider_name] = 0

    def record_success(self, provider_name: str) -> None:
        self._consecutive[provider_name] = 0
        self._remaining[provider_name] = 0

    @property
    def open_providers(self) -> List[str]:
        return [k for k, v in self._remaining.items() if v > 0]


class DeepSeekProvider(AiProvider):
    """DeepSeek chat adapter (D-062 drop-in; register row 9 owner-gated).

    OpenAI-schema-compatible request/response per official docs
    (reviewed 2026-09-21); same transport discipline and gate as the
    D-066 adapters.
    """

    name = "deepseek"
    KEY_ENV = "DEEPSEEK_API_KEY"

    def __init__(self, transport: Optional[Callable[[Dict], Dict]] = None,
                 model: str = "deepseek-chat",
                 api_key: Optional[str] = None,
                 base_url: str = DEEPSEEK_BASE_DEFAULT,
                 timeout_s: float = 30.0):
        from canonical.ai_providers_live import require_live_key
        self.api_key = api_key if api_key is not None \
            else require_live_key(self.name, self.KEY_ENV)
        if transport is None:
            raise AiProviderError(
                "DeepSeekProvider requires an injected transport — "
                "direct HTTP is forbidden in this architecture "
                "(D-053/D-066)", failure_class="B")
        self._transport = transport
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.calls: List[AiRequest] = []

    def generate(self, request: AiRequest) -> AiResponse:
        self.calls.append(request)
        started = time.monotonic()
        request_dict = {
            "url": f"{self.base_url}/chat/completions",
            "model": self.model,
            "messages": [
                {"role": "system", "content":
                    "You return ONLY JSON matching the requested schema."},
                {"role": "user", "content": json.dumps(
                    request.prompt_payload, ensure_ascii=False)},
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "api_key": self.api_key,  # transport-bound; never logged
        }
        try:
            body = self._transport(request_dict)
        except AiProviderError:
            raise
        except TimeoutError as exc:
            raise AiProviderError(f"provider timeout: {exc}",
                                  failure_class="A") from exc
        except (ConnectionError, OSError) as exc:
            raise AiProviderError(f"connection error: {exc}",
                                  failure_class="A") from exc
        latency = int((time.monotonic() - started) * 1000)
        choices = body.get("choices") if isinstance(body, dict) else None
        if not isinstance(choices, list) or not choices:
            raise classify_provider_error(
                body.get("status_code") if isinstance(body, dict) else None,
                json.dumps(body, default=str)[:300])
        message = choices[0].get("message", {}) if isinstance(
            choices[0], dict) else {}
        content = message.get("content", "")
        try:
            parsed = json.loads(content) if content else None
        except json.JSONDecodeError:
            parsed = None
        usage = body.get("usage", {}) or {}
        return AiResponse(
            text=str(content),
            parsed=parsed,
            usage={"prompt_tokens": int(usage.get("prompt_tokens", 0)),
                   "completion_tokens": int(usage.get(
                       "completion_tokens", 0))},
            provider=self.name, model=body.get("model", self.model),
            finish_reason=str(choices[0].get("finish_reason", "stop")),
            latency_ms=int(body.get("latency_ms", latency)))


class OllamaProvider(AiProvider):
    """Local Ollama adapter (D-062 drop-in; localhost daemon).

    The default base URL is the loopback daemon — air-gapped by
    construction (D-045/D-053): no key exists, none is requested; the
    "credential" is the owner's decision to run a local model at all.
    A remote host requires an explicit base_url override by the owner.
    """

    name = "ollama"
    KEY_ENV = "OLLAMA_MODEL"  # the MODEL name is the enablement gate

    def __init__(self, transport: Optional[Callable[[Dict], Dict]] = None,
                 model: Optional[str] = None,
                 base_url: str = OLLAMA_BASE_DEFAULT,
                 timeout_s: float = 60.0):
        from canonical.ai_providers_live import require_live_key
        self.model = model if model is not None \
            else require_live_key(self.name, self.KEY_ENV)
        if transport is None:
            raise AiProviderError(
                "OllamaProvider requires an injected transport — "
                "direct HTTP is forbidden in this architecture "
                "(D-053/D-066)", failure_class="B")
        self._transport = transport
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.calls: List[AiRequest] = []

    def generate(self, request: AiRequest) -> AiResponse:
        self.calls.append(request)
        started = time.monotonic()
        request_dict = {
            "url": f"{self.base_url}/api/chat",
            "model": self.model,
            "messages": [
                {"role": "system", "content":
                    "You return ONLY JSON matching the requested schema."},
                {"role": "user", "content": json.dumps(
                    request.prompt_payload, ensure_ascii=False)},
            ],
            "stream": False,
            "format": "json",
            "options": {"num_predict": request.max_tokens,
                        "temperature": request.temperature},
        }
        try:
            body = self._transport(request_dict)
        except AiProviderError:
            raise
        except TimeoutError as exc:
            raise AiProviderError(f"provider timeout: {exc}",
                                  failure_class="A") from exc
        except (ConnectionError, OSError) as exc:
            raise AiProviderError(f"connection error: {exc}",
                                  failure_class="A") from exc
        latency = int((time.monotonic() - started) * 1000)
        message = body.get("message", {}) if isinstance(body, dict) else {}
        content = str(message.get("content", ""))
        try:
            parsed = json.loads(content) if content else None
        except json.JSONDecodeError:
            parsed = None
        return AiResponse(
            text=content,
            parsed=parsed,
            usage={"prompt_tokens": int(body.get("prompt_eval_count", 0)),
                   "completion_tokens": int(body.get("eval_count", 0))},
            provider=self.name, model=body.get("model", self.model),
            finish_reason=str(body.get("done_reason", "stop")),
            latency_ms=int(body.get("latency_ms", latency)))


class ProviderChain(AiProvider):
    """Deterministic multi-provider fallback chain (D-066 generalized).

    Providers are tried in order; a Class-A/C failure advances to the
    next; exhausting the chain falls back to `MockAiProvider` (the
    D-066 terminal fallback). Class-B/D failures SURFACE immediately —
    fallback cannot repair a contract or payload problem. Every step
    (and every breaker opening) is recorded to observability.
    """

    name = "chain"

    def __init__(self, providers: List[AiProvider],
                 collector: Optional[AiObservabilityCollector] = None,
                 task_type: str = "", template_id: str = "",
                 template_hash: str = "",
                 breaker: Optional[ProviderCircuitBreaker] = None):
        if not providers:
            raise AiProviderError("chain needs at least one provider",
                                  failure_class="B")
        self.providers = list(providers)
        self.collector = collector
        self.task_type = task_type
        self.template_id = template_id
        self.template_hash = template_hash
        self.breaker = breaker or ProviderCircuitBreaker()
        self.terminal = MockAiProvider()
        self.fallbacks_used = 0
        self.calls: List[AiRequest] = []

    def _provider_name(self, p: AiProvider) -> str:
        return getattr(p, "name", p.__class__.__name__)

    def _record(self, correlation_id: str, provider: str,
                error_class: str, notes: str) -> None:
        if self.collector is None:
            return
        try:
            self.collector.record(
                correlation_id=correlation_id or "n/a",
                stage="fallback", task_type=self.task_type,
                status="fallback_step", provider=provider, model="",
                template_id=self.template_id,
                template_hash=self.template_hash,
                error_class=error_class, notes=notes)
        except Exception:
            pass  # observability must never break the fallback

    def generate(self, request: AiRequest) -> AiResponse:
        self.calls.append(request)
        errors: List[str] = []
        for p in self.providers:
            pname = self._provider_name(p)
            if not self.breaker.allow(pname):
                self._record(request.idempotency_tag, pname, "A",
                             "circuit open — provider skipped (deterministic)")
                continue
            try:
                resp = p.generate(request)
            except AiProviderError as exc:
                self.breaker.record_failure(pname)
                errors.append(f"{pname}:{exc.failure_class}")
                if exc.failure_class in ("A", "C"):
                    self._record(
                        request.idempotency_tag, pname, exc.failure_class,
                        f"live provider unavailable ({exc.failure_class}); "
                        "advancing chain (D-066)")
                    continue
                raise  # B/D surface — never masked
            self.breaker.record_success(pname)
            return resp
        self.fallbacks_used += 1
        self._record(request.idempotency_tag, "chain", "A",
                     "chain exhausted; mock fallback (D-066)")
        return self.terminal.generate(request)

    @property
    def attempted(self) -> List[str]:
        return [self._provider_name(p) for p in self.providers]

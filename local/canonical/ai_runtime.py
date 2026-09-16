"""Phase 7 M1 — provider-neutral AI runtime: model router, mock
provider, cost accounting, budget guardrails, rate limiting, proposal
envelope.

Boundary discipline (RULES §35, the mock-Woo/mock-Notion pattern):
`AiProvider` is the ONLY vendor-facing interface; `MockAiProvider` is
the local implementation (D-053). Real OpenAI/Anthropic/local-model
adapters are drop-in `AiProvider` implementations — owner-gated, no
credentials exist, none are requested (D-045).

Authority pipeline (D-050): this module PRODUCES proposals only —
`AiProposal` envelopes carry AI_GENERATED provenance and land in the
HITL VerificationQueue. Nothing here can execute a Red operation:
there is no Woo/publication/price/vocabulary code path reachable from
this module (structural no by import graph, tested).

Failure mapping (D-052, phase-07 doc §4):
  - provider timeout/429/rate limit  → AiProviderError(class A)
  - credential missing/invalid        → AiProviderError(class C)
  - authority violation               → AiProviderError(class D, abort)
  - schema validation of model output → OutputValidationError (B)
  - unknown/ambiguous response        → Class E record, human review

Cost guardrails: token-bucket rate limiter per provider + per-task
budgets with soft warning (default 80%) and HARD refusal BEFORE
dispatch at 100% (Class-B guardrail refusal — refusing locally is
cheaper than the request). Unknown tariff ⇒ cost 0 + unknown_tariff
flag, never a silent guess (RULES §8 posture).
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from canonical.ai_contracts import (
    OutputValidationError,
    SchemaError,
    validate_ai_output,
)


class AiProviderError(Exception):
    """Provider-side failure carrying its D-052 class (A/C/D)."""

    def __init__(self, message: str, *, failure_class: str):
        super().__init__(message)
        self.failure_class = failure_class  # "A" | "C" | "D"


class BudgetExceeded(AiProviderError):
    """Hard budget refusal BEFORE dispatch (Class B guardrail)."""

    def __init__(self, message: str):
        super().__init__(message, failure_class="B")


# --- provider-neutral interface + mock implementation ------------------------


@dataclass(frozen=True)
class AiRequest:
    task_type: str                    # e.g. enrich_description, propose_content_idea
    schema_id: str                    # registered output contract id
    prompt_payload: Dict              # structured, serializable
    max_tokens: int = 1024
    temperature: float = 0.7
    idempotency_tag: str = ""         # caller-supplied deterministic tag
    cost_center: str = "default"


@dataclass(frozen=True)
class AiResponse:
    text: str
    parsed: Optional[Dict]
    usage: Dict                       # {prompt_tokens, completion_tokens}
    provider: str
    model: str
    finish_reason: str
    latency_ms: int


class AiProvider:
    """Provider-neutral boundary (RULES §35). Real adapters implement
    exactly this and are owner-gated additions."""

    name = "abstract"

    def generate(self, request: AiRequest) -> AiResponse:
        raise NotImplementedError


class MockAiProvider(AiProvider):
    """Deterministic local provider (D-053): scripted responses per
    schema id, deterministic token accounting (4 chars ≈ 1 token —
    documented approximation, enough for budget tests), configurable
    failure injection (timeout / rate_limit / auth / malformed /
    unknown-shape), and a scriptable parse mode."""

    name = "mock"

    def __init__(self, responses: Optional[Dict[str, str]] = None,
                 fail_with: Optional[str] = None):
        self.responses = dict(responses or {})
        self.fail_with = fail_with  # None | timeout | rate_limit | auth | malformed | unknown_shape
        self.calls: List[AiRequest] = []

    # -- canned responses -----------------------------------------------------

    MOCK_OUTPUTS: Dict[str, Dict] = {
        "content_idea_proposal.v1": {
            "title": "کمپین پاییزی کت و جلیقه",
            "working_notes": "تمرکز بر لایه‌بندی پاییزی و ترکیب رنگ گرم",
            "target_lifecycle_state": "Backlog",
            "rationale": "بر اساس تقویم محتوایی فصل پاییز پیشنهاد می‌شود",
        },
        "caption_proposal.v1": {
            "caption_fa": "کت و جلیقه پاییزی جدید رسید؛ گرم، رسمی و راحت.",
            "hashtags": ["#پوشاک", "#پاییز", "#کت_جلیقه"],
            "alt_text": "مدل با کت و جلیقه پاییزی در نور طبیعی",
        },
        "product_description_enrichment.v1": {
            "product_id": "a1b2c3d4-1111-4222-a333-444444444444",
            "variant_ids": [],
            "description_fa": "این مانتوی پاییزی از پارچه نرم و breathable دوخته شده است؛ مناسب محیط کار و مهمانی‌های روزانه.",
            "seo_title_fa": "مانتو پاییزی زنانه | خرید آنلاین",
            "seo_keywords": ["مانتو پاییزی", "مانتو زنانه", "خرید مانتو"],
            "rationale": "توضیحات فعلی کوتاه است؛ با جزئیات جنس و کاربرد غنی‌تر شد",
        },
    }

    def _fail(self):
        if self.fail_with == "timeout":
            raise AiProviderError("provider timeout after retries",
                                  failure_class="A")
        if self.fail_with == "rate_limit":
            raise AiProviderError("429 rate limit exceeded",
                                  failure_class="A")
        if self.fail_with == "auth":
            raise AiProviderError("401 credential missing/invalid",
                                  failure_class="C")
        if self.fail_with == "malformed":
            return AiResponse(
                text="this is not json at all", parsed=None,
                usage={"prompt_tokens": 10, "completion_tokens": 5},
                provider=self.name, model="mock-1", finish_reason="stop",
                latency_ms=1)
        if self.fail_with == "unknown_shape":
            return AiResponse(
                text="{}", parsed={},
                usage={"prompt_tokens": 10, "completion_tokens": 1},
                provider=self.name, model="mock-1", finish_reason="stop",
                latency_ms=1)
        return None

    def generate(self, request: AiRequest) -> AiResponse:
        self.calls.append(request)
        forced = self._fail()
        if forced is not None:
            return forced
        if request.schema_id not in self.MOCK_OUTPUTS:
            raise AiProviderError(
                f"mock provider has no scripted output for {request.schema_id}",
                failure_class="B")
        raw = self.responses.get(request.schema_id) \
            or json.dumps(self.MOCK_OUTPUTS[request.schema_id],
                          ensure_ascii=False)
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = None
        usage = {
            "prompt_tokens": max(1, len(json.dumps(
                request.prompt_payload, ensure_ascii=False)) // 4),
            "completion_tokens": max(1, len(raw) // 4),
        }
        return AiResponse(text=raw, parsed=parsed, usage=usage,
                          provider=self.name, model="mock-1",
                          finish_reason="stop", latency_ms=1)


# --- routing policy + cost model ---------------------------------------------

@dataclass(frozen=True)
class RouteTarget:
    provider: str
    model: str
    schema_id: str
    budget_usd: float
    max_tokens: int = 1024
    temperature: float = 0.7


DEFAULT_ROUTING_POLICY: Dict[str, RouteTarget] = {
    "propose_content_idea": RouteTarget(
        "mock", "mock-1", "content_idea_proposal.v1", budget_usd=0.50),
    "generate_caption": RouteTarget(
        "mock", "mock-1", "caption_proposal.v1", budget_usd=0.50),
    "enrich_description": RouteTarget(
        "mock", "mock-1", "product_description_enrichment.v1",
        budget_usd=1.00),
}

# static tariff table (USD per 1K tokens); mock is free
TARIFFS: Dict[tuple, Dict[str, float]] = {
    ("mock", "mock-1"): {"input": 0.0, "output": 0.0},
}
SOFT_BUDGET_RATIO = 0.8


def estimate_cost(provider: str, model: str, usage: Dict) -> Dict:
    tariff = TARIFFS.get((provider, model))
    if tariff is None:
        return {"cost_usd": 0.0, "unknown_tariff": True}
    cost = (usage.get("prompt_tokens", 0) / 1000.0 * tariff["input"]
            + usage.get("completion_tokens", 0) / 1000.0 * tariff["output"])
    return {"cost_usd": round(cost, 6), "unknown_tariff": False}


class TokenBucket:
    """Conservative local rate limiter (refusals = Class A, retryable)."""

    def __init__(self, capacity: int = 30, refill_per_sec: float = 1.0):
        self.capacity = capacity
        self.tokens = float(capacity)
        self.refill_per_sec = refill_per_sec
        self._last = time.monotonic()

    def acquire(self) -> bool:
        now = time.monotonic()
        self.tokens = min(self.capacity,
                          self.tokens + (now - self._last) * self.refill_per_sec)
        self._last = now
        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False


class UsageLedger:
    """Append-only local usage ledger (gitignored runtime state; later
    mirrored into the D-055 canonical store)."""

    def __init__(self, path: Optional[str] = None):
        self.path = path
        self.entries: List[Dict] = []

    def record(self, **kw) -> Dict:
        correlation = kw.pop("correlation_id", None) or str(uuid.uuid4())
        entry = {"occurred_at": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                              time.gmtime()),
                 "correlation_id": correlation, **kw}
        self.entries.append(entry)
        if self.path:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.entries, f, ensure_ascii=False, indent=2)
        return entry

    def total_cost(self, task_type: Optional[str] = None) -> float:
        return round(sum(e["cost_usd"] for e in self.entries
                         if task_type is None
                         or e["task_type"] == task_type), 6)


# --- runtime (routing + guardrails + proposals) -------------------------------


@dataclass(frozen=True)
class AiProposal:
    """The ONLY way AI output leaves this module: a review-ready
    envelope (D-050). No execution path exists — approval happens in
    the HITL VerificationQueue by a human (M2 wires the round-trip).

    Frozen (M4 audit hardening): once validated, an envelope is
    tamper-evident — any post-validation mutation raises
    FrozenInstanceError instead of silently changing reviewed content."""
    schema_id: str
    task_type: str
    payload: Dict
    provider: str
    model: str
    usage: Dict
    cost: Dict
    provenance_id: Optional[int]
    correlation_id: str
    warnings: List[str] = field(default_factory=list)

    def to_queue_item(self) -> Dict:
        return {
            "sheet": "ai-proposal",
            "row": self.correlation_id[:12],
            "code": f"AI_{self.task_type.upper()}",
            "message": f"{self.schema_id} proposal from {self.provider}/{self.model}",
            "schema_id": self.schema_id,
            "payload": self.payload,
            "provenance_id": self.provenance_id,
            "item_key": f"ai|{self.schema_id}|{self.correlation_id}",
        }


class ModelRouter:
    """Deterministic task→provider routing with budget + rate guardrails.

    spend tracking starts at zero per router instance; pass a
    `UsageLedger` to persist every call (M2 mirrors into PostgreSQL).
    """

    def __init__(self, providers: Dict[str, AiProvider],
                 policy: Optional[Dict[str, RouteTarget]] = None,
                 ledger: Optional[UsageLedger] = None,
                 budgets: Optional[Dict[str, float]] = None,
                 bucket_capacity: int = 30):
        self.providers = providers
        self.policy = dict(policy or DEFAULT_ROUTING_POLICY)
        self.ledger = ledger
        self.budgets = dict(budgets or {})
        self._spend: Dict[str, float] = {}
        self._bucket = TokenBucket(capacity=bucket_capacity)

    def _guardrails(self, request: AiRequest,
                    target: RouteTarget) -> List[str]:
        warnings: List[str] = []
        budget = self.budgets.get(request.task_type,
                                  target.budget_usd)
        spent = self._spend.get(request.task_type, 0.0)
        if spent >= budget:
            raise BudgetExceeded(
                f"hard budget refusal: task {request.task_type} spent "
                f"${spent:.4f} of ${budget:.4f} — dispatch blocked "
                "(guardrail, Class B)")
        if spent >= SOFT_BUDGET_RATIO * budget:
            warnings.append(
                f"budget_warning: ${spent:.4f} of ${budget:.4f} "
                f"(≥{int(SOFT_BUDGET_RATIO * 100)}% soft limit)")
        if not self._bucket.acquire():
            raise AiProviderError(
                "local rate limit: token bucket exhausted",
                failure_class="A")
        return warnings

    def _require_registered(self, provider_name: str) -> None:
        if provider_name not in self.providers:
            raise AiProviderError(
                f"routing policy references unknown provider "
                f"{provider_name!r}", failure_class="B")

    def run(self, request: AiRequest,
            provenance=None, queue=None,
            actor: str = "ai-runtime") -> AiProposal:
        """Route → guardrails → generate → validate → envelope.

        Raises AiProviderError (A/C/D), BudgetExceeded (B guardrail),
        OutputValidationError (B contract), SchemaError (programmer).
        Never returns unvalidated model text.
        """
        if request.task_type not in self.policy:
            raise AiProviderError(
                f"no routing policy for task {request.task_type!r}",
                failure_class="B")
        target = self.policy[request.task_type]
        self._require_registered(target.provider)
        # contract must exist and be well-formed BEFORE any dispatch
        from canonical.ai_contracts import get_schema
        get_schema(request.schema_id)
        if request.schema_id != target.schema_id:
            raise AiProviderError(
                f"schema mismatch: task routes to {target.schema_id} "
                f"but request says {request.schema_id}",
                failure_class="B")
        warnings = self._guardrails(request, target)
        provider = self.providers[target.provider]
        try:
            response = provider.generate(request)
        except AiProviderError:
            if self.ledger:
                self.ledger.record(
                    task_type=request.task_type, provider=target.provider,
                    model=target.model, tokens_in=0, tokens_out=0,
                    cost_usd=0.0, latency_ms=0, status="provider_error",
                    unknown_tariff=False,
                    correlation_id=request.idempotency_tag or None)
            raise
        cost = estimate_cost(response.provider, response.model,
                             response.usage)
        validation = validate_ai_output(request.schema_id, response.parsed)
        if not validation["valid"]:
            if self.ledger:
                self.ledger.record(
                    task_type=request.task_type,
                    provider=response.provider, model=response.model,
                    tokens_in=response.usage["prompt_tokens"],
                    tokens_out=response.usage["completion_tokens"],
                    cost_usd=cost["cost_usd"], latency_ms=response.latency_ms,
                    status="validation_failed",
                    unknown_tariff=cost["unknown_tariff"],
                    correlation_id=request.idempotency_tag or None)
            raise OutputValidationError(
                "AI output failed its contract (Class B, never silently "
                f"repaired): {validation['errors']}",
                errors=validation["errors"])
        # provenance (D-026): AI_GENERATED, best-effort audit attachment
        pr_id = None
        if provenance is not None:
            try:
                pr = provenance.record(
                    "AI_GENERATED", actor,
                    source_reference=f"ai:{request.task_type}:"
                                     f"{request.idempotency_tag or 'n/a'}",
                    original_value=json.dumps(response.parsed,
                                              ensure_ascii=False,
                                              sort_keys=True),
                    notes=f"ai proposal via {response.provider}/"
                          f"{response.model}")
                # ProvenanceEngine.record returns the int id
                pr_id = pr if isinstance(pr, int) else \
                    (pr.get("provenance_id") if isinstance(pr, dict)
                     else getattr(pr, "provenance_id", None))
            except RuntimeError:
                pr_id = None  # audit layer unavailable — proposal stands
        correlation = request.idempotency_tag or str(uuid.uuid4())
        # spend tracking is ALWAYS active (budget guardrails are a
        # safety property, not a persistence feature — the M1 test
        # suite caught this when it was ledger-gated)
        self._spend[request.task_type] = round(
            self._spend.get(request.task_type, 0.0) + cost["cost_usd"], 6)
        if self.ledger:
            self.ledger.record(
                task_type=request.task_type, provider=response.provider,
                model=response.model,
                tokens_in=response.usage["prompt_tokens"],
                tokens_out=response.usage["completion_tokens"],
                cost_usd=cost["cost_usd"], latency_ms=response.latency_ms,
                status="ok", unknown_tariff=cost["unknown_tariff"],
                correlation_id=correlation)
        proposal = AiProposal(
            schema_id=request.schema_id, task_type=request.task_type,
            payload=response.parsed, provider=response.provider,
            model=response.model, usage=dict(response.usage),
            cost=cost, provenance_id=pr_id, correlation_id=correlation,
            warnings=warnings)
        if queue is not None:
            from canonical.verification_tool import VerificationQueue
            if isinstance(queue, VerificationQueue):
                queue.enqueue(proposal.to_queue_item(),
                              source_type="AI_GENERATED", actor=actor)
        return proposal

"""Phase 24 — vendor lock-in & neutral portability layer (D-129/D-130).

Pure contracts + harnesses: NO I/O libraries, no vendor imports — the
module itself must conform to the boundaries it declares (battery-
asserted).

  D-129  assert_provider_conformance + BudgetLedger write-through
  D-130  OperationMatrix / BackendPair / assert_backend_parity
         MediaStoreContract conformance (over portability_contracts)
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple

from canonical.ai_runtime import (
    AiProvider,
    AiProviderError,
    AiRequest,
    BudgetExceeded,
)
from canonical.budget_engine import BudgetLedger
from canonical.portability_contracts import (
    MEDIA_OPS,
    MediaStoreContract,
    MediaStoreContractError,
    normalize,
    run_media_script,
)

__all__ = [
    "PortabilityError", "PortabilityViolation", "ProviderContract",
    "TOKEN_KEYS", "AiMeteredProvider", "assert_provider_conformance",
    "OperationMatrix", "BackendPair", "assert_backend_parity",
    "assert_media_conformance", "MEDIA_OPS", "MediaStoreContract",
]

_PROVIDER_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,39}$")

#: usage keys every provider MUST report — the accounting the D-127
#: write-through consumes. Extra keys are allowed; these are mandatory.
TOKEN_KEYS = ("prompt_tokens", "completion_tokens", "estimated_cost")


class PortabilityError(Exception):
    """Harness failure to build/run a conformance or parity run."""


class PortabilityViolation(AssertionError):
    """A declared contract was violated (battery failure)."""


# ============================================================================
# D-129 — model & provider neutrality
# ============================================================================

@dataclass(frozen=True)
class ProviderContract:
    """Declared checklist every ``AiProvider`` implementation must pass."""

    #: schema ids the provider must answer with schema-compatible output
    required_schema_ids: Tuple[str, ...] = (
        "content_idea_proposal.v1",
        "caption_proposal.v1",
        "product_description_enrichment.v1",
    )
    #: canonical failure classes a provider may surface (D-052)
    allowed_failure_classes: Tuple[str, ...] = ("A", "B", "C", "D", "E")


def _probe_failure_class(exc: BaseException) -> Optional[str]:
    """Extract the D-052 class from provider failures."""
    if isinstance(exc, BudgetExceeded):
        return "B"
    if isinstance(exc, AiProviderError):
        cls = getattr(exc, "failure_class", None)
        return cls if cls in ("A", "C", "D", "E") else None
    return None  # bare non-AiProviderError types violate the contract


class _ConformanceProbe:
    def __init__(self, provider: AiProvider, contract: ProviderContract):
        self.provider = provider
        self.contract = contract
        self.failures: list = []

    def _fail(self, msg: str) -> None:
        self.failures.append(msg)

    def run(self) -> None:
        from canonical.ai_contracts import validate_ai_output

        p = self.provider
        name = getattr(p, "name", None)
        if not isinstance(name, str) or not _PROVIDER_NAME_RE.match(name):
            self._fail(f"name {name!r} is not a declared lowercase "
                       f"identifier (D-129)")
            return

        for schema_id in self.contract.required_schema_ids:
            req = AiRequest(task_type=schema_id, schema_id=schema_id,
                            prompt_payload={})
            try:
                resp = p.generate(req)
            except Exception as exc:  # noqa: BLE001 — harness classifies
                cls = _probe_failure_class(exc)
                if cls is None:
                    self._fail(f"{schema_id}: failure surfaced as "
                               f"{type(exc).__name__} without a D-052 "
                               f"class (bare SDK type)")
                elif cls not in self.contract.allowed_failure_classes:
                    self._fail(f"{schema_id}: failure class {cls!r} not "
                               f"allowed by contract")
                continue

            if resp is None:
                self._fail(f"{schema_id}: generate returned None")
                continue
            # the RESPONDING engine must be a declared name: simple
            # providers answer under their own name; composites
            # (fallback/router) declare `composite_members` and answer
            # under a member's name — an undeclared responder is the
            # real bug class this check pins.
            members = getattr(p, "composite_members", None) or ()
            if getattr(resp, "provider", "") not in ({name} | set(members)):
                self._fail(f"{schema_id}: response.provider "
                           f"{resp.provider!r} is not a declared "
                           f"responder (name={name!r}, "
                           f"composite_members={sorted(members)!r})")
            if resp.parsed is not None:
                try:
                    validate_ai_output(schema_id, resp.parsed)
                except Exception as exc:  # noqa: BLE001
                    self._fail(f"{schema_id}: parsed output fails schema: "
                               f"{exc}")
            usage = getattr(resp, "usage", None)
            if not isinstance(usage, dict):
                self._fail(f"{schema_id}: usage is not a dict")
                continue
            for key in TOKEN_KEYS:
                if key not in usage:
                    self._fail(f"{schema_id}: usage missing {key!r}")
            for key in TOKEN_KEYS:
                v = usage.get(key)
                if isinstance(v, bool) or not isinstance(v, (int, float)):
                    self._fail(f"{schema_id}: usage[{key!r}] not numeric "
                               f"({v!r})")
                elif key in ("prompt_tokens", "completion_tokens") \
                        and v < 0:
                    self._fail(f"{schema_id}: usage[{key!r}] negative")
            if not isinstance(getattr(resp, "text", None), str):
                self._fail(f"{schema_id}: text is not str")
            if not isinstance(getattr(resp, "model", ""), str):
                self._fail(f"{schema_id}: model is not str")
            if not isinstance(getattr(resp, "finish_reason", ""), str):
                self._fail(f"{schema_id}: finish_reason is not str")
            if not isinstance(getattr(resp, "latency_ms", 0), int) \
                    or isinstance(getattr(resp, "latency_ms", 0), bool):
                self._fail(f"{schema_id}: latency_ms is not int")

        # determinism: identical input ⇒ identical token accounting
        req = AiRequest(task_type=self.contract.required_schema_ids[0],
                        schema_id=self.contract.required_schema_ids[0],
                        prompt_payload={})
        try:
            r1, r2 = p.generate(req), p.generate(req)
            if r1.usage != r2.usage:
                self._fail("determinism: same input yielded different usage")
        except Exception:  # noqa: BLE001 — failing providers reported above
            pass


def assert_provider_conformance(provider: AiProvider,
                                contract: Optional[ProviderContract] = None,
                                ) -> None:
    """Battery-prove a provider against the D-129 checklist.

    Raises ``PortabilityViolation`` listing every violation.
    """
    c = contract or ProviderContract()
    probe = _ConformanceProbe(provider, c)
    probe.run()
    if probe.failures:
        raise PortabilityViolation(
            f"provider {getattr(provider, 'name', '?')!r} violates the "
            f"D-129 provider contract:\n  "
            + ";\n  ".join(probe.failures))


class AiMeteredProvider(AiProvider):
    """D-129 write-through adapter: every successful ``generate`` meters
    the D-127 ``BudgetLedger`` (llm_tokens + llm_calls) BEFORE the
    response is returned; refused calls cost zero and raise BudgetExceeded.

    Subclasses implement ``_generate``; canonical tasks keep calling
    ``generate`` unchanged.
    """

    name = "abstract"

    def _generate(self, request: AiRequest) -> "AiResponseLike":
        raise NotImplementedError

    def generate(self, request: AiRequest):
        resp = self._generate(request)
        usage = getattr(resp, "usage", None) or {}
        tokens = usage.get("prompt_tokens", 0)
        completion = usage.get("completion_tokens", 0)
        self.ledger.consume_llm(
            tokens=int(tokens) + int(completion),
            calls=1,
            scope="green",
            correlation_id=getattr(request, "cost_center", "default"),
        )
        return resp


# ============================================================================
# D-130 — backend parity
# ============================================================================

@dataclass(frozen=True)
class OperationMatrix:
    """Declared op matrix a backend family must satisfy. Verdicts are
    normalized and compared across the pair."""

    ops: Dict[str, Callable[[Any, Dict], Any]]
    setup: Optional[Callable[[Dict], None]] = None
    teardown: Optional[Callable[[Dict], None]] = None


@dataclass(frozen=True)
class BackendPair:
    """A declared backend family with two interchangeable factories."""

    name: str
    offline_factory: Callable[[], Any]
    live_factory: Callable[[], Any]
    matrix: OperationMatrix
    live_ready: Callable[[], bool] = staticmethod(lambda: True)


def _norm_exc(exc: BaseException) -> Dict[str, str]:
    return {"__error__": type(exc).__name__}


def _run_leg(matrix: OperationMatrix, factory: Callable[[], Any],
             ctx: Dict) -> Dict[str, Any]:
    backend = factory()
    if matrix.setup:
        matrix.setup(ctx)
    try:
        verdicts: Dict[str, Any] = {}
        for op_name, op in sorted(matrix.ops.items()):
            try:
                verdicts[op_name] = normalize(op(backend, ctx))
            except Exception as exc:  # noqa: BLE001
                verdicts[op_name] = normalize(_norm_exc(exc))
        return verdicts
    finally:
        if matrix.teardown:
            matrix.teardown(ctx)


def assert_backend_parity(pair: BackendPair,
                          ctx: Optional[Dict] = None) -> Dict[str, Any]:
    """Run the SAME script against both factories; verdicts must match.

    Returns the verdict map; divergence raises ``PortabilityViolation``.
    When ``live_ready()`` is False the harness returns ``offline_only``
    mode (the battery asserts live readiness separately — zero-skip).
    """
    if not isinstance(pair.name, str) \
            or not _PROVIDER_NAME_RE.match(pair.name):
        raise PortabilityError(f"backend pair name {pair.name!r} invalid")
    ctx = ctx if ctx is not None else {}
    off = _run_leg(pair.matrix, pair.offline_factory, ctx)
    if not pair.live_ready():
        return {"pair": pair.name, "mode": "offline_only",
                "verdicts": off, "divergences": []}
    live = _run_leg(pair.matrix, pair.live_factory, ctx)
    divergences = []
    for op_name in sorted(set(off) | set(live)):
        if off.get(op_name) != live.get(op_name):
            divergences.append({"op": op_name,
                                "offline": off.get(op_name),
                                "live": live.get(op_name)})
    if divergences:
        detail = "; ".join(f"{d['op']}: offline={d['offline']!r} "
                           f"live={d['live']!r}" for d in divergences)
        raise PortabilityViolation(
            f"backend pair {pair.name!r} diverged:\n  {detail}")
    return {"pair": pair.name, "mode": "both", "verdicts": off,
            "divergences": []}


def assert_media_conformance(store: Any, **kwargs) -> Dict[str, Any]:
    """Assert a store satisfies the D-130 media contract; returns the
    verdict map (raises ``MediaStoreContractError`` on violation)."""
    verdicts = run_media_script(store, **kwargs)
    problems = []
    if not verdicts.get("deterministic_address"):
        problems.append("deterministic_address")
    if verdicts.get("get") is not True:
        problems.append("get round-trip")
    if verdicts.get("head_size_matches") is not True:
        problems.append("head size")
    if verdicts.get("delete") is not True:
        problems.append("delete")
    if verdicts.get("delete_missing") is not True:
        problems.append("delete-missing returns False")
    if verdicts.get("get_after_delete") != "missing":
        problems.append("get-after-delete must raise")
    if problems:
        raise MediaStoreContractError(
            f"{type(store).__name__} violates the D-130 media contract: "
            f"{', '.join(problems)}")
    return verdicts

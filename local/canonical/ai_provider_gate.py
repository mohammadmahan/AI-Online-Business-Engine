"""Phase 4 — fashion AI provider gate and runtime wiring (D-172 / D-139).

The Phase 4 engines (`fashion_copy.py`, `fashion_trends.py`) are
deliberately provider-agnostic: they accept a `ModelRouter` and know
nothing about which provider serves it. That was right for §4.1/§4.2,
but it left one question unanswered at the seam:

    WHICH provider is allowed to serve a fashion task, right now, and
    on whose authority?

This module answers it in ONE deterministic, offline, fail-closed place.

What it is NOT
--------------
  - It does not SELECT a provider. Decision 9 / G-4 (the AI provider
    choice) is the owner's and remains OPEN; nothing here names a
    vendor, constructs an adapter, opens a socket, or reads an
    environment variable.
  - It does not replace the router's guardrails. `ModelRouter` keeps
    the D-063 budget refusal and the local rate limiter; the gate
    reports the SAME numbers through public read-only views
    (`budget_state`, `rate_limit_available`) so wiring and preflight
    cannot drift from enforcement.
  - It does not weaken the D-066 construction gate in
    `ai_providers_live.py`. An environment flag plus a key is still
    necessary for a live adapter to exist — it is simply NOT
    sufficient to serve a fashion task.

The rule the gate enforces
--------------------------
1. DENY BY DEFAULT. A provider must be DECLARED in the catalogue
   (mock only, unless the caller declares more) and REGISTERED in the
   router. Anything undeclared is refused by name, not guessed.
2. MOCK IS THE ONLY UNGATED CLASS. `mock` is local, deterministic and
   free; every other class is `live` and needs an owner decision.
3. LIVE NEEDS A RECORDED OWNER DECISION. `OwnerDecision` carries the
   decision reference (decision 9 / D-139 vocabulary), who approved
   it, the provider names and task types it covers, and an optional
   expiry. A boolean env flag is configuration, not consent.
4. PRODUCTION REFUSES LIVE ENTIRELY. `runtime_preflight.py` already
   treats AI live enablement as production-blocked (D-045); the gate
   encodes the same refusal instead of relying on a separate check.
5. CREDENTIAL PRESENCE IS INJECTED, NEVER READ. The gate asks a
   caller-supplied predicate whether the named variable is present;
   it never touches the process environment, never receives a value,
   and its audit records carry variable NAMES only.
6. STRUCTURE IS VERIFIED, NOT ASSUMED. The routed schema must be a
   registered contract, the provider must actually be registered, and
   a non-zero budget must be declared before a task can be wired.

Wiring
------
`guarded_router()` returns a NEW `ModelRouter` whose policy contains
only the tasks the gate allowed, so `FashionCopywritingEngine` and
`FashionTrendEngine` run unchanged on a router that cannot route a
denied task. `wire_fashion_engines()` builds both engines over it.
`strict=True` (the default) refuses to build a partially-wired surface.

Every decision is a frozen `GateDecision` with a stable code and a
JSON-serialisable, timestamp-free, value-free record — so a gate
refusal is auditable and reproducible instead of a log line.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from typing import Callable, Dict, Iterable, List, Optional, Tuple, Union

from canonical.ai_contracts import AI_OUTPUT_SCHEMAS
from canonical.ai_runtime import (AiProviderError, MockAiProvider,
                                  ModelRouter)

# --- stable identifiers -------------------------------------------------------

GATE_SCHEMA = "ai.provider_gate.v1"
PROVIDER_CLASS_MOCK = "mock"
PROVIDER_CLASS_LIVE = "live"
PROVIDER_CLASSES = (PROVIDER_CLASS_MOCK, PROVIDER_CLASS_LIVE)

ENVIRONMENT_LOCAL = "local"
ENVIRONMENT_PRODUCTION = "production"

#: The four Phase 4 tasks this gate exists for (§4.1 three channels +
#: §4.2 tag sets). Nothing outside this tuple is wired by default.
FASHION_TASKS = (
    "generate_caption",              # §4.1 Instagram caption (G-6 reuse)
    "fashion_telegram_announcement",  # §4.1 Telegram announcement
    "fashion_seo_copy",              # §4.1 SEO copy
    "fashion_trend_hashtags",        # §4.2 trend/hashtag intelligence
)

# decision codes — stable, asserted by the battery
ALLOWED_MOCK = "ALLOWED_MOCK"
ALLOWED_LIVE = "ALLOWED_LIVE"
TASK_NOT_ROUTED = "TASK_NOT_ROUTED"
PROVIDER_UNDECLARED = "PROVIDER_UNDECLARED"
PROVIDER_CLASS_UNKNOWN = "PROVIDER_CLASS_UNKNOWN"
PROVIDER_NOT_REGISTERED = "PROVIDER_NOT_REGISTERED"
SCHEMA_UNREGISTERED = "SCHEMA_UNREGISTERED"
OWNER_DECISION_MISSING = "OWNER_DECISION_MISSING"
OWNER_DECISION_EXPIRED = "OWNER_DECISION_EXPIRED"
TASK_OUTSIDE_OWNER_SCOPE = "TASK_OUTSIDE_OWNER_SCOPE"
PROVIDER_OUTSIDE_OWNER_SCOPE = "PROVIDER_OUTSIDE_OWNER_SCOPE"
LIVE_BLOCKED_IN_PRODUCTION = "LIVE_BLOCKED_IN_PRODUCTION"
CREDENTIAL_UNAVAILABLE = "CREDENTIAL_UNAVAILABLE"
BUDGET_NOT_DECLARED = "BUDGET_NOT_DECLARED"
BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
RATE_LIMITED = "RATE_LIMITED"


class GateConfigError(ValueError):
    """Malformed catalogue/decision/environment input (Class B).

    Raised at CONSTRUCTION: a gate built from contradictory
    configuration must not exist at all (fail closed), rather than
    refuse every task later for the wrong reason.
    """

    failure_class = "B"


class ProviderGateError(AiProviderError):
    """A wiring/preflight refusal surfaced as a typed error (Class B).

    Carries the frozen decision(s) that refused, so the caller can
    report WHICH rule fired instead of parsing a message.
    """

    def __init__(self, message: str, *, decisions: Iterable = (),
                 decision=None):
        super().__init__(message, failure_class="B")
        self.decisions = tuple(decisions)
        self.decision = decision


# --- declarations -------------------------------------------------------------


@dataclass(frozen=True)
class ProviderDeclaration:
    """What a provider IS, as configuration (never a credential).

    `key_env` is a variable NAME (e.g. an env key), never a value: it is
    metadata the gate hands to the presence predicate and prints in
    audit records.
    """

    name: str
    provider_class: str
    key_env: str = ""
    models: Tuple[str, ...] = ()
    notes: str = ""

    def validated(self) -> "ProviderDeclaration":
        name = str(self.name or "").strip()
        if not name:
            raise GateConfigError("provider declaration needs a name")
        if self.provider_class not in PROVIDER_CLASSES:
            raise GateConfigError(
                f"provider {name!r}: unknown class "
                f"{self.provider_class!r}; expected {PROVIDER_CLASSES}")
        key_env = str(self.key_env or "").strip()
        models = tuple(str(m).strip() for m in (self.models or ())
                       if str(m).strip())
        if self.provider_class == PROVIDER_CLASS_MOCK:
            if name != "mock":
                raise GateConfigError(
                    f"provider {name!r}: the mock class is the local "
                    "`mock` provider only")
            if key_env:
                raise GateConfigError(
                    "provider 'mock': a local provider carries no key "
                    "variable")
        else:
            if not key_env:
                raise GateConfigError(
                    f"provider {name!r}: a live class must name the "
                    "variable its adapter reads (name only, no value)")
            if not models:
                raise GateConfigError(
                    f"provider {name!r}: a live class must declare at "
                    "least one model id")
        return ProviderDeclaration(name=name,
                                   provider_class=self.provider_class,
                                   key_env=key_env, models=models,
                                   notes=str(self.notes or ""))


def default_catalogue() -> Dict[str, ProviderDeclaration]:
    """The ONLY provider enabled without an owner decision: local mock."""
    return {"mock": ProviderDeclaration("mock", PROVIDER_CLASS_MOCK,
                                        models=("mock-1",))}


# --- owner decision -----------------------------------------------------------


@dataclass(frozen=True)
class OwnerDecision:
    """A recorded owner approval to serve named tasks on named providers.

    This is the D-139 / decision-9 vocabulary expressed as data: a
    reference, an approver, an explicit provider and task scope, and an
    optional expiry. It is NOT a credential and carries no token.
    """

    decision_ref: str
    approved_by: str
    providers: Tuple[str, ...]
    task_types: Tuple[str, ...]
    expires_on: Optional[str] = None
    note: str = ""

    def validated(self) -> "OwnerDecision":
        ref = str(self.decision_ref or "").strip()
        who = str(self.approved_by or "").strip()
        providers = tuple(str(p).strip() for p in (self.providers or ())
                          if str(p).strip())
        tasks = tuple(str(t).strip() for t in (self.task_types or ())
                      if str(t).strip())
        if not ref:
            raise GateConfigError("owner decision needs a decision_ref")
        if not who:
            raise GateConfigError(
                f"owner decision {ref!r}: needs an approver")
        if not providers:
            raise GateConfigError(
                f"owner decision {ref!r}: no provider in scope")
        if not tasks:
            raise GateConfigError(
                f"owner decision {ref!r}: no task type in scope")
        expiry = str(self.expires_on).strip() if self.expires_on else None
        if expiry:
            try:
                date.fromisoformat(expiry)
            except ValueError as exc:
                raise GateConfigError(
                    f"owner decision {ref!r}: expires_on must be an ISO "
                    f"date (YYYY-MM-DD), got {expiry!r}") from exc
        return OwnerDecision(decision_ref=ref, approved_by=who,
                             providers=providers, task_types=tasks,
                             expires_on=expiry,
                             note=str(self.note or ""))

    def fingerprint(self) -> str:
        """Deterministic, value-free identity of this decision.

        Stable across runs and machines (sorted canonical JSON), so an
        audit record can be matched to a decision without persisting the
        decision body or any credential.
        """
        body = json.dumps({
            "decision_ref": self.validated().decision_ref,
            "approved_by": self.validated().approved_by,
            "providers": list(self.validated().providers),
            "task_types": list(self.validated().task_types),
            "expires_on": self.validated().expires_on,
        }, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]

    def expired(self, today: Optional[date] = None) -> bool:
        expiry = self.validated().expires_on
        if not expiry:
            return False
        return (today or date.today()) > date.fromisoformat(expiry)


# --- decision -----------------------------------------------------------------


@dataclass(frozen=True)
class GateDecision:
    """One frozen gate verdict (wiring or preflight phase)."""

    allowed: bool
    code: str
    phase: str
    task_type: str
    provider: str = ""
    model: str = ""
    schema_id: str = ""
    detail: str = ""
    failure_class: str = ""
    warnings: Tuple[str, ...] = ()
    owner_decision_ref: str = ""
    owner_fingerprint: str = ""
    environment: str = ""

    def to_dict(self) -> Dict:
        """JSON-serialisable record: stable, timestamp-free, no values."""
        rec: Dict = {
            "schema_version": GATE_SCHEMA,
            "phase": self.phase,
            "task_type": self.task_type,
            "provider": self.provider,
            "model": self.model,
            "schema_id": self.schema_id,
            "allowed": self.allowed,
            "code": self.code,
            "environment": self.environment,
        }
        for key, value in (("detail", self.detail),
                           ("failure_class", self.failure_class),
                           ("owner_decision_ref", self.owner_decision_ref),
                           ("owner_fingerprint", self.owner_fingerprint)):
            if value:
                rec[key] = value
        if self.warnings:
            rec["warnings"] = list(self.warnings)
        return rec


# --- gate ---------------------------------------------------------------------


def _never_present(_name: str) -> bool:
    """Default presence predicate: NOTHING is present (fail closed).

    The gate never reads the environment itself; a deployment that
    wants a live route must inject a predicate that checks presence
    without handing over the value.
    """
    return False


class ProviderGate:
    """Deny-by-default provider gate for the Phase 4 fashion tasks."""

    def __init__(self, router: ModelRouter, *,
                 owner_decisions: Union[OwnerDecision,
                                        Iterable[OwnerDecision],
                                        None] = None,
                 catalogue: Optional[Dict[str, ProviderDeclaration]] = None,
                 credential_present: Optional[Callable[[str], bool]] = None,
                 environment: str = ENVIRONMENT_LOCAL,
                 today: Optional[date] = None,
                 audit: Optional[Callable[[Dict], None]] = None):
        if not isinstance(router, ModelRouter):
            raise GateConfigError(
                "provider gate needs a ModelRouter (the M1 dispatch "
                "boundary); got "
                f"{type(router).__name__}")
        self.router = router
        self.environment = str(environment or ENVIRONMENT_LOCAL).strip() \
            .lower()
        if self.environment not in (ENVIRONMENT_LOCAL,
                                    ENVIRONMENT_PRODUCTION):
            raise GateConfigError(
                f"unknown environment {environment!r}; expected "
                f"{(ENVIRONMENT_LOCAL, ENVIRONMENT_PRODUCTION)}")
        self.today = today
        self.credential_present = credential_present or _never_present
        self.audit = audit
        self.decisions: List[GateDecision] = []

        declared = default_catalogue() if catalogue is None else dict(
            catalogue)
        self.catalogue: Dict[str, ProviderDeclaration] = {}
        for name, decl in declared.items():
            clean = decl.validated()
            if clean.name != str(name).strip():
                raise GateConfigError(
                    f"catalogue key {name!r} does not match the "
                    f"declaration name {clean.name!r}")
            self.catalogue[clean.name] = clean

        if owner_decisions is None:
            owner = ()
        elif isinstance(owner_decisions, OwnerDecision):
            owner = (owner_decisions,)
        else:
            owner = tuple(owner_decisions)
        self.owner_decisions: Tuple[OwnerDecision, ...] = tuple(
            d.validated() for d in owner)

    # -- internals -------------------------------------------------------------

    def _record(self, decision: GateDecision) -> GateDecision:
        self.decisions.append(decision)
        if self.audit is not None:
            self.audit(decision.to_dict())
        return decision

    def _decision(self, *, allowed: bool, code: str, phase: str,
                  task_type: str, target=None, detail: str = "",
                  failure_class: str = "", warnings: Tuple[str, ...] = (),
                  owner: Optional[OwnerDecision] = None) -> GateDecision:
        return self._record(GateDecision(
            allowed=allowed, code=code, phase=phase,
            task_type=task_type,
            provider=(target.provider if target is not None else ""),
            model=(target.model if target is not None else ""),
            schema_id=(target.schema_id if target is not None else ""),
            detail=detail, failure_class=failure_class,
            warnings=warnings,
            owner_decision_ref=(owner.decision_ref if owner else ""),
            owner_fingerprint=(owner.fingerprint() if owner else ""),
            environment=self.environment,
        ))

    def _scope_refusal(self, task_type: str, provider: str
                       ) -> Tuple[str, str]:
        """Closest true reason no owner decision covers (task, provider)."""
        if not self.owner_decisions:
            return (OWNER_DECISION_MISSING,
                    "no owner decision is recorded for non-mock "
                    "providers (decision 9 / G-4 stays open)")
        tasks_seen = False
        providers_seen = False
        for decision in self.owner_decisions:
            has_task = task_type in decision.task_types
            has_provider = provider in decision.providers
            tasks_seen = tasks_seen or has_task
            providers_seen = providers_seen or has_provider
            if has_task and has_provider:
                if decision.expired(self.today):
                    return (OWNER_DECISION_EXPIRED,
                            f"owner decision {decision.decision_ref!r} "
                            f"expired on {decision.expires_on}")
        if tasks_seen and not providers_seen:
            return (PROVIDER_OUTSIDE_OWNER_SCOPE,
                    f"provider {provider!r} is outside every recorded "
                    "owner decision")
        if providers_seen and not tasks_seen:
            return (TASK_OUTSIDE_OWNER_SCOPE,
                    f"task {task_type!r} is outside every recorded "
                    "owner decision")
        return (TASK_OUTSIDE_OWNER_SCOPE,
                f"no recorded owner decision covers task {task_type!r} "
                f"on provider {provider!r}")

    def _matching_decision(self, task_type: str, provider: str
                           ) -> Optional[OwnerDecision]:
        for decision in self.owner_decisions:
            if (task_type in decision.task_types
                    and provider in decision.providers
                    and not decision.expired(self.today)):
                return decision
        return None

    # -- wiring-time verdict ---------------------------------------------------

    def decide(self, task_type: str) -> GateDecision:
        """Structural verdict: may this task be wired to its route at all?"""
        target = self.router.policy.get(task_type)
        if target is None:
            return self._decision(
                allowed=False, code=TASK_NOT_ROUTED, phase="wiring",
                task_type=task_type, failure_class="B",
                detail="the router has no routing policy for this task")

        declaration = self.catalogue.get(target.provider)
        if declaration is None:
            return self._decision(
                allowed=False, code=PROVIDER_UNDECLARED, phase="wiring",
                task_type=task_type, target=target, failure_class="B",
                detail=f"provider {target.provider!r} is not declared in "
                       "the gate catalogue (deny by default)")

        if target.provider not in self.router.providers:
            return self._decision(
                allowed=False, code=PROVIDER_NOT_REGISTERED,
                phase="wiring", task_type=task_type, target=target,
                failure_class="B",
                detail=f"provider {target.provider!r} is routed but not "
                       "registered on the router")

        if target.schema_id not in AI_OUTPUT_SCHEMAS:
            return self._decision(
                allowed=False, code=SCHEMA_UNREGISTERED, phase="wiring",
                task_type=task_type, target=target, failure_class="B",
                detail=f"schema {target.schema_id!r} is not a registered "
                       "AI contract")

        if declaration.provider_class == PROVIDER_CLASS_MOCK:
            # construction pinned the mock class to the name `mock`, so
            # reaching here means the route really is the local provider
            return self._decision(
                allowed=True, code=ALLOWED_MOCK, phase="wiring",
                task_type=task_type, target=target,
                detail="local deterministic provider — offline by "
                       "construction")

        # live class: every additional rule must pass
        if self.environment == ENVIRONMENT_PRODUCTION:
            return self._decision(
                allowed=False, code=LIVE_BLOCKED_IN_PRODUCTION,
                phase="wiring", task_type=task_type, target=target,
                failure_class="B",
                detail="live AI enablement is production-blocked (D-045 / "
                       "runtime preflight)")

        owner = self._matching_decision(task_type, target.provider)
        if owner is None:
            code, detail = self._scope_refusal(task_type, target.provider)
            return self._decision(
                allowed=False, code=code, phase="wiring",
                task_type=task_type, target=target, failure_class="B",
                detail=detail)

        if not self.credential_present(declaration.key_env):
            return self._decision(
                allowed=False, code=CREDENTIAL_UNAVAILABLE,
                phase="wiring", task_type=task_type, target=target,
                failure_class="B", owner=owner,
                detail=f"variable {declaration.key_env} is not present "
                       "(presence is injected; the gate never reads it)")

        if float(target.budget_usd) <= 0:
            return self._decision(
                allowed=False, code=BUDGET_NOT_DECLARED, phase="wiring",
                task_type=task_type, target=target, failure_class="B",
                owner=owner,
                detail="a live route needs a positive declared budget "
                       "(D-063)")

        return self._decision(
            allowed=True, code=ALLOWED_LIVE, phase="wiring",
            task_type=task_type, target=target, owner=owner,
            detail="owner decision + presence + declared budget")

    # -- per-dispatch preflight ------------------------------------------------

    def preflight(self, task_type: str) -> GateDecision:
        """Readiness verdict: the same route, with live budget/rate state.

        This NEVER dispatches and never consumes a token: it reads the
        router's public read-only views, so wiring cannot disagree with
        the guardrail that actually refuses.
        """
        wiring = self.decide(task_type)
        if not wiring.allowed:
            return self._record(GateDecision(
                allowed=False, code=wiring.code, phase="preflight",
                task_type=task_type, provider=wiring.provider,
                model=wiring.model, schema_id=wiring.schema_id,
                detail=wiring.detail, failure_class=wiring.failure_class,
                warnings=wiring.warnings,
                owner_decision_ref=wiring.owner_decision_ref,
                owner_fingerprint=wiring.owner_fingerprint,
                environment=wiring.environment))

        target = self.router.policy[task_type]
        state = self.router.budget_state(task_type)
        if state["budget_usd"] <= 0:
            return self._record(GateDecision(
                allowed=False, code=BUDGET_NOT_DECLARED,
                phase="preflight", task_type=task_type,
                provider=target.provider, model=target.model,
                schema_id=target.schema_id, failure_class="B",
                detail="the resolved budget for this task is not positive",
                owner_decision_ref=wiring.owner_decision_ref,
                owner_fingerprint=wiring.owner_fingerprint,
                environment=self.environment))
        if state["exhausted"]:
            return self._record(GateDecision(
                allowed=False, code=BUDGET_EXHAUSTED, phase="preflight",
                task_type=task_type, provider=target.provider,
                model=target.model, schema_id=target.schema_id,
                failure_class="B",
                detail=(f"spent {state['spent_usd']:.4f} of "
                        f"{state['budget_usd']:.4f} — the router's "
                        "pre-dispatch refusal stands (D-063)"),
                owner_decision_ref=wiring.owner_decision_ref,
                owner_fingerprint=wiring.owner_fingerprint,
                environment=self.environment))

        warnings: Tuple[str, ...] = ()
        if state["soft_limit"]:
            warnings = (f"budget_warning: {state['spent_usd']:.4f} of "
                        f"{state['budget_usd']:.4f}",)

        if self.router.rate_limit_available() < 1:
            return self._record(GateDecision(
                allowed=False, code=RATE_LIMITED, phase="preflight",
                task_type=task_type, provider=target.provider,
                model=target.model, schema_id=target.schema_id,
                failure_class="A", warnings=warnings,
                detail="local token bucket exhausted — retryable (Class A)",
                owner_decision_ref=wiring.owner_decision_ref,
                owner_fingerprint=wiring.owner_fingerprint,
                environment=self.environment))

        return self._record(GateDecision(
            allowed=True, code=wiring.code, phase="preflight",
            task_type=task_type, provider=target.provider,
            model=target.model, schema_id=target.schema_id,
            warnings=warnings,
            owner_decision_ref=wiring.owner_decision_ref,
            owner_fingerprint=wiring.owner_fingerprint,
            environment=self.environment))

    # -- inspection ------------------------------------------------------------

    def plan(self, tasks: Iterable[str] = FASHION_TASKS
             ) -> Tuple[GateDecision, ...]:
        """Wiring verdicts for a task set (never raises on a refusal)."""
        return tuple(self.decide(task) for task in tasks)

    @property
    def refusals(self) -> Tuple[GateDecision, ...]:
        return tuple(d for d in self.decisions if not d.allowed)

    # -- wiring ----------------------------------------------------------------

    def guarded_router(self, tasks: Iterable[str] = FASHION_TASKS,
                       *, strict: bool = True) -> ModelRouter:
        """A router that can route ONLY the tasks this gate allowed.

        `strict` (default) refuses to build a partially wired surface:
        the first refused task raises with every refusal attached, so a
        typo in a routing policy cannot silently shrink the surface.
        """
        requested = tuple(tasks)
        decisions = self.plan(requested)
        refused = tuple(d for d in decisions if not d.allowed)
        if strict and refused:
            summary = "; ".join(f"{d.task_type}:{d.code}"
                                for d in refused)
            raise ProviderGateError(
                f"provider gate refused {len(refused)} of "
                f"{len(requested)} task(s) — {summary}", decisions=refused)

        policy = {}
        providers = {}
        for decision in decisions:
            if not decision.allowed:
                continue
            target = self.router.policy[decision.task_type]
            policy[decision.task_type] = target
            providers[target.provider] = \
                self.router.providers[target.provider]
        budgets = {task: self.router.budgets[task]
                   for task in policy if task in self.router.budgets}
        guarded = ModelRouter(providers, policy=policy,
                              ledger=self.router.ledger, budgets=budgets,
                              bucket_capacity=self.router.rate_limit_capacity)
        # D-063 spend is an ACCOUNTING accumulator for (task, provider),
        # not for a router object: sharing it keeps a gate preflight on
        # this router honest about dispatches made through the guarded
        # one. Dropping it would let wiring report a fresh budget while
        # the wired engine was already spending.
        guarded._spend = self.router._spend
        return guarded


# --- engine wiring ------------------------------------------------------------


@dataclass(frozen=True)
class FashionWiring:
    """Both Phase 4 engines bound to one guarded router."""

    router: ModelRouter
    copy: object
    trends: object
    decisions: Tuple[GateDecision, ...]


def wire_fashion_engines(gate: ProviderGate, *,
                         tasks: Iterable[str] = FASHION_TASKS,
                         lifecycle=None, strict: bool = True) -> FashionWiring:
    """Build §4.1 + §4.2 engines over a gate-approved router.

    The engines are untouched: they receive the same `ModelRouter`
    interface they always did, and the ONLY thing that changed is that
    the router cannot route a task the gate refused. Imports are local
    so the gate module stays cheap to import and free of cycles.
    """
    router = gate.guarded_router(tasks, strict=strict)
    from canonical.fashion_copy import FashionCopywritingEngine
    from canonical.fashion_trends import FashionTrendEngine
    return FashionWiring(
        router=router,
        copy=FashionCopywritingEngine(router, lifecycle=lifecycle),
        trends=FashionTrendEngine(router, lifecycle=lifecycle),
        decisions=gate.plan(tasks),
    )


def offline_gate(**kwargs) -> ProviderGate:
    """The documented offline gate: local mock only, no owner decision.

    This is what tests and dry-runs use. It cannot reach a network by
    construction — the only registered provider is the deterministic
    mock and the catalogue declares nothing else.
    """
    kwargs.setdefault("environment", ENVIRONMENT_LOCAL)
    return ProviderGate(ModelRouter({"mock": MockAiProvider()}), **kwargs)


__all__ = [
    "ALLOWED_LIVE",
    "ALLOWED_MOCK",
    "BUDGET_EXHAUSTED",
    "BUDGET_NOT_DECLARED",
    "CREDENTIAL_UNAVAILABLE",
    "ENVIRONMENT_LOCAL",
    "ENVIRONMENT_PRODUCTION",
    "FASHION_TASKS",
    "FashionWiring",
    "GATE_SCHEMA",
    "GateConfigError",
    "GateDecision",
    "LIVE_BLOCKED_IN_PRODUCTION",
    "OWNER_DECISION_EXPIRED",
    "OWNER_DECISION_MISSING",
    "OwnerDecision",
    "PROVIDER_CLASS_LIVE",
    "PROVIDER_CLASS_MOCK",
    "PROVIDER_CLASS_UNKNOWN",
    "PROVIDER_NOT_REGISTERED",
    "PROVIDER_OUTSIDE_OWNER_SCOPE",
    "PROVIDER_UNDECLARED",
    "ProviderDeclaration",
    "ProviderGate",
    "ProviderGateError",
    "RATE_LIMITED",
    "SCHEMA_UNREGISTERED",
    "TASK_NOT_ROUTED",
    "TASK_OUTSIDE_OWNER_SCOPE",
    "default_catalogue",
    "offline_gate",
    "wire_fashion_engines",
]

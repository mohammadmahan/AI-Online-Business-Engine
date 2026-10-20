"""Phase 4 — provider gate & fashion runtime wiring tests (D-172 / D-139).

Subject: `local/canonical/ai_provider_gate.py`

The gate is the seam between "the engines are provider-agnostic" and
"no provider may serve them without an owner decision". The battery
below pins that seam from every side:

  1. CONFIGURATION: declarations and owner decisions are validated at
     construction, so a contradictory gate cannot exist.
  2. DENY BY DEFAULT: undeclared / unregistered / mismatched / unknown
     schema all refuse with a stable code, and the local mock is the
     only class that needs no owner decision.
  3. OWNER DECISION: a non-mock class needs a recorded decision that
     covers BOTH the task and the provider, is unexpired, and whose
     credential variable is present — an env flag is not consent, and
     the gate never reads the environment itself.
  4. PRODUCTION refuses live unconditionally (D-045 / preflight).
  5. BUDGET & RATE: preflight reports the router's OWN state
     (D-063) without dispatching or consuming a token.
  6. WIRING: `guarded_router` / `wire_fashion_engines` give the §4.1
     and §4.2 engines a router that cannot route a refused task, and
     strict wiring refuses a partial surface instead of shrinking it.
  7. HYGIENE: no network, no environment read, no credential material
     in any string constant, no publication verb, approved imports.
"""

import ast
import json
import os
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOCAL = HERE.parent
for p in (str(LOCAL), str(LOCAL / "canonical"), str(LOCAL / "services")):
    if p not in sys.path:
        sys.path.insert(0, p)

from canonical import ai_provider_gate as gate_mod  # noqa: E402
from canonical.ai_provider_gate import (  # noqa: E402
    ALLOWED_LIVE, ALLOWED_MOCK, BUDGET_EXHAUSTED, BUDGET_NOT_DECLARED,
    CREDENTIAL_UNAVAILABLE, ENVIRONMENT_LOCAL, ENVIRONMENT_PRODUCTION,
    FASHION_TASKS, GATE_SCHEMA, GateConfigError, LIVE_BLOCKED_IN_PRODUCTION,
    OWNER_DECISION_EXPIRED, OWNER_DECISION_MISSING, OwnerDecision,
    PROVIDER_CLASS_LIVE, PROVIDER_CLASS_MOCK, PROVIDER_NOT_REGISTERED,
    PROVIDER_OUTSIDE_OWNER_SCOPE,
    PROVIDER_UNDECLARED, ProviderDeclaration, ProviderGate,
    ProviderGateError, RATE_LIMITED, SCHEMA_UNREGISTERED, TASK_NOT_ROUTED,
    TASK_OUTSIDE_OWNER_SCOPE, default_catalogue, offline_gate,
    wire_fashion_engines)
from canonical.ai_runtime import (  # noqa: E402
    AiProvider, AiProviderError, AiResponse, MockAiProvider, ModelRouter,
    RouteTarget)

GATE_MODULE = LOCAL / "canonical" / "ai_provider_gate.py"

SEO_PAYLOAD = {
    "meta_description_fa": "مانتو پاییزی زنانه با پارچه کرپ نرم و دوخت "
                           "تمیز؛ مناسب محیط کار و دورهمی.",
    "web_copy_fa": "مانتو پاییزی با پارچه کرپ نرم، فرم ایستاده و دوخت "
                   "تمیز؛ ترکیبی آراسته برای روزهای کاری.",
    "seo_keywords": ["مانتو پاییزی", "مانتو کرپ"],
    "rationale": "کلیدواژه فصل و جنس پارچه در متن و توضیح متا پوشش داده شد",
}

TREND_PAYLOAD = {
    "hashtags": ["مانتو", "مانتو_پاییزی", "پاییز", "پوشاک_پاییزی",
                 "استایل_پاییزی", "مانتو_کرپ"],
    "category_tags": ["مانتو", "مانتو_پاییزی"],
    "season_tags": ["پاییز", "پوشاک_پاییزی"],
    "niche_tags": ["استایل_پاییزی", "مانتو_کرپ"],
    "rationale": "دستهٔ مانتو با فصل پاییز و هشتگ تخصصی ترکیب شد",
}


class _StubProvider(AiProvider):
    """Deterministic, offline stand-in for an owner-selected adapter."""

    name = "stub-live"

    def __init__(self):
        self.calls = []

    def generate(self, request):
        self.calls.append(request)
        if request.schema_id == "trend_hashtag_set.v1":
            parsed = TREND_PAYLOAD
        elif request.schema_id == "seo_copy.v1":
            parsed = SEO_PAYLOAD
        else:
            raise AssertionError(f"unexpected schema {request.schema_id}")
        return AiResponse(text=json.dumps(parsed, ensure_ascii=False),
                          parsed=parsed,
                          usage={"prompt_tokens": 10,
                                 "completion_tokens": 10},
                          provider=self.name, model="stub-1",
                          finish_reason="stop", latency_ms=1)


def _mock_router(**kwargs):
    return ModelRouter({"mock": MockAiProvider()}, **kwargs)


def _mixed_router(provider_name="stub-live", model="stub-1",
                  budget=0.5, schema="seo_copy.v1"):
    """Mock everywhere, with `fashion_seo_copy` routed to the stub."""
    stub = _StubProvider()
    router = ModelRouter({"mock": MockAiProvider(),
                          provider_name: stub})
    router.policy = dict(router.policy)
    router.policy["fashion_seo_copy"] = RouteTarget(
        provider_name, model, schema, budget_usd=budget)
    return router, stub


def _live_decl(name="stub-live", key_env="STUB_KEY"):
    return ProviderDeclaration(name, PROVIDER_CLASS_LIVE,
                               key_env=key_env, models=("stub-1",))


def _catalogue(*decls):
    catalogue = default_catalogue()
    for decl in decls:
        catalogue[decl.name] = decl
    return catalogue


def _decision(**over):
    payload = {
        "decision_ref": "decision-9",
        "approved_by": "owner",
        "providers": ("stub-live",),
        "task_types": ("fashion_seo_copy",),
    }
    payload.update(over)
    return OwnerDecision(**payload)


# =========================================================================
# 1. CONFIGURATION (fail closed at construction)
# =========================================================================


class CatalogueTests(unittest.TestCase):

    def test_default_catalogue_is_the_local_mock_only(self):
        cat = default_catalogue()
        self.assertEqual(sorted(cat), ["mock"])
        self.assertEqual(cat["mock"].provider_class, PROVIDER_CLASS_MOCK)
        self.assertEqual(cat["mock"].key_env, "")

    def test_mock_declaration_cannot_claim_another_name(self):
        with self.assertRaises(GateConfigError):
            ProviderDeclaration("vendor", PROVIDER_CLASS_MOCK).validated()

    def test_mock_declaration_cannot_carry_a_key_variable(self):
        with self.assertRaises(GateConfigError):
            ProviderDeclaration("mock", PROVIDER_CLASS_MOCK,
                                key_env="SOME_KEY").validated()

    def test_live_declaration_needs_a_variable_name_and_a_model(self):
        with self.assertRaises(GateConfigError):
            ProviderDeclaration("stub-live", PROVIDER_CLASS_LIVE,
                                models=("stub-1",)).validated()
        with self.assertRaises(GateConfigError):
            ProviderDeclaration("stub-live", PROVIDER_CLASS_LIVE,
                                key_env="STUB_KEY").validated()

    def test_unknown_provider_class_is_refused(self):
        with self.assertRaises(GateConfigError):
            ProviderDeclaration("x", "cloud").validated()

    def test_catalogue_key_must_match_the_declaration(self):
        with self.assertRaises(GateConfigError):
            ProviderGate(_mock_router(),
                         catalogue={"other": _live_decl()})

    def test_gate_requires_a_model_router(self):
        with self.assertRaises(GateConfigError):
            ProviderGate(object())

    def test_unknown_environment_is_refused(self):
        with self.assertRaises(GateConfigError):
            ProviderGate(_mock_router(), environment="staging-ish")


class OwnerDecisionTests(unittest.TestCase):

    def test_decision_requires_every_field(self):
        for bad in ({"decision_ref": " "}, {"approved_by": ""},
                    {"providers": ()}, {"task_types": ()}):
            with self.assertRaises(GateConfigError, msg=str(bad)):
                _decision(**bad).validated()

    def test_expiry_must_be_an_iso_date(self):
        with self.assertRaises(GateConfigError):
            _decision(expires_on="next week").validated()

    def test_expiry_boundary(self):
        expiry = "2026-10-20"
        today = date(2026, 10, 20)
        self.assertFalse(_decision(expires_on=expiry).expired(today))
        self.assertTrue(_decision(expires_on=expiry).expired(
            today + timedelta(days=1)))

    def test_no_expiry_never_expires(self):
        self.assertFalse(_decision().expired(date(2099, 1, 1)))

    def test_fingerprint_is_stable_scoped_and_short(self):
        a = _decision().fingerprint()
        b = _decision().fingerprint()
        self.assertEqual(a, b)
        self.assertEqual(len(a), 16)
        self.assertNotEqual(a, _decision(task_types=(
            "fashion_seo_copy", "fashion_trend_hashtags")).fingerprint())
        self.assertNotEqual(a, _decision(decision_ref="decision-9-b").fingerprint())

    def test_fingerprint_carries_no_credential_surface(self):
        # a decision is data about consent, not a token: nothing that
        # looks like key material can appear in its identity
        fp = _decision().fingerprint()
        self.assertNotIn("STUB_KEY", fp)
        self.assertNotIn("key", fp.lower())


# =========================================================================
# 2. OFFLINE GATE (mock only, no owner decision)
# =========================================================================


class OfflineGateTests(unittest.TestCase):

    def test_every_fashion_task_is_allowed_on_mock(self):
        gate = offline_gate()
        for decision in gate.plan():
            self.assertTrue(decision.allowed, decision.code)
            self.assertEqual(decision.code, ALLOWED_MOCK)
            self.assertEqual(decision.provider, "mock")
            self.assertEqual(decision.environment, ENVIRONMENT_LOCAL)

    def test_plan_covers_exactly_the_four_phase4_tasks(self):
        gate = offline_gate()
        self.assertEqual(tuple(d.task_type for d in gate.plan()),
                         FASHION_TASKS)
        self.assertEqual(len(FASHION_TASKS), 4)

    def test_unknown_task_is_refused_not_guessed(self):
        decision = offline_gate().decide("fashion_video_script")
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.code, TASK_NOT_ROUTED)
        self.assertEqual(decision.failure_class, "B")

    def test_decisions_are_appended_and_auditable(self):
        records = []
        gate = offline_gate(audit=records.append)
        gate.decide("fashion_seo_copy")
        gate.preflight("fashion_seo_copy")
        # each phase is its own record: one wiring verdict, then the
        # wiring re-read plus the preflight verdict
        self.assertEqual([d.phase for d in gate.decisions],
                         ["wiring", "wiring", "preflight"])
        self.assertEqual(len(records), 3)
        for rec in records:
            self.assertEqual(rec["schema_version"], GATE_SCHEMA)
            self.assertEqual(rec["task_type"], "fashion_seo_copy")
            self.assertIn("allowed", rec)
            self.assertNotIn("occurred_at", rec)  # deterministic records
            json.dumps(rec)  # serialisable

    def test_decisions_are_deterministic(self):
        a = offline_gate().decide("fashion_trend_hashtags").to_dict()
        b = offline_gate().decide("fashion_trend_hashtags").to_dict()
        self.assertEqual(a, b)

    def test_guarded_router_contains_only_allowed_tasks(self):
        router = offline_gate().guarded_router()
        self.assertEqual(sorted(router.policy), sorted(FASHION_TASKS))
        self.assertEqual(sorted(router.providers), ["mock"])
        for target in router.policy.values():
            self.assertEqual(target.provider, "mock")

    def test_wiring_builds_both_engines_and_runs_offline(self):
        wiring = wire_fashion_engines(offline_gate())
        self.assertEqual(len(wiring.decisions), 4)
        self.assertTrue(all(d.allowed for d in wiring.decisions))

        from canonical.fashion_copy import FashionBrief
        from canonical.fashion_trends import TrendBrief
        pack = wiring.copy.generate_pack(
            FashionBrief(title="مانتو پاییزی", fabric_type="کرپ",
                         season="پاییز"))
        self.assertTrue(pack.ok, [r.error for r in pack.reports.values()])
        trend = wiring.trends.generate(
            TrendBrief(garment_category="مانتو", season="پاییز",
                       fabric_type="کرپ"))
        self.assertTrue(trend.ok, trend.divergences)

    def test_preflight_is_allowed_without_consuming_the_bucket(self):
        router = _mock_router()
        router._bucket.refill_per_sec = 0.0  # deterministic window
        gate = ProviderGate(router)
        before = router.rate_limit_available()
        decision = gate.preflight("fashion_seo_copy")
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.code, ALLOWED_MOCK)
        self.assertEqual(decision.phase, "preflight")
        self.assertEqual(router.rate_limit_available(), before)


# =========================================================================
# 3. DENY BY DEFAULT
# =========================================================================


class DenyByDefaultTests(unittest.TestCase):

    def test_undeclared_provider_is_refused(self):
        router, _stub = _mixed_router()
        decision = ProviderGate(router).decide("fashion_seo_copy")
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.code, PROVIDER_UNDECLARED)
        self.assertIn("stub-live", decision.detail)

    def test_declared_but_unregistered_provider_is_refused(self):
        router = _mock_router()
        router.policy = dict(router.policy)
        router.policy["fashion_seo_copy"] = RouteTarget(
            "stub-live", "stub-1", "seo_copy.v1", budget_usd=0.5)
        decision = ProviderGate(router, catalogue=_catalogue(
            _live_decl())).decide("fashion_seo_copy")
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.code, PROVIDER_NOT_REGISTERED)

    def test_unregistered_schema_is_refused(self):
        router, _stub = _mixed_router(schema="not_a_contract.v1")
        decision = ProviderGate(router, catalogue=_catalogue(
            _live_decl())).decide("fashion_seo_copy")
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.code, SCHEMA_UNREGISTERED)

    def test_a_live_class_cannot_masquerade_as_mock(self):
        # catalogue declares the name 'mock' as a live class: the local
        # exemption must not apply to it
        router = _mock_router()
        declaration = ProviderDeclaration("mock", PROVIDER_CLASS_LIVE,
                                          key_env="STUB_KEY",
                                          models=("mock-1",))
        gate = ProviderGate(router, catalogue={"mock": declaration},
                            credential_present=lambda name: True)
        decision = gate.decide("fashion_seo_copy")
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.code, OWNER_DECISION_MISSING)

    def test_a_declaration_cannot_be_reclassified_after_the_fact(self):
        # frozen declarations + construction validation mean a provider
        # cannot be re-labelled as the local class later
        declaration = _live_decl()
        with self.assertRaises(Exception):
            declaration.provider_class = PROVIDER_CLASS_MOCK


# =========================================================================
# 4. OWNER DECISION (consent is a record, not an env flag)
# =========================================================================


class OwnerDecisionGateTests(unittest.TestCase):

    def _gate(self, *, decisions=(), present=None, environment=ENVIRONMENT_LOCAL,
              today=None, router=None, budget=0.5):
        router = router or _mixed_router(budget=budget)[0]
        return ProviderGate(
            router, owner_decisions=decisions, catalogue=_catalogue(
                _live_decl()),
            credential_present=present, environment=environment,
            today=today)

    def test_live_without_a_decision_is_refused(self):
        decision = self._gate(present=lambda name: True).decide(
            "fashion_seo_copy")
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.code, OWNER_DECISION_MISSING)
        self.assertEqual(decision.failure_class, "B")

    def test_a_credential_alone_is_not_consent(self):
        # presence True, no decision: still refused (D-139)
        decision = self._gate(present=lambda name: True).decide(
            "fashion_seo_copy")
        self.assertFalse(decision.allowed)

    def test_task_outside_the_decision_scope_is_refused(self):
        decision = self._gate(
            decisions=[_decision(task_types=("fashion_trend_hashtags",))],
            present=lambda name: True).decide("fashion_seo_copy")
        self.assertEqual(decision.code, TASK_OUTSIDE_OWNER_SCOPE)

    def test_provider_outside_the_decision_scope_is_refused(self):
        decision = self._gate(
            decisions=[_decision(providers=("other-vendor",))],
            present=lambda name: True).decide("fashion_seo_copy")
        self.assertEqual(decision.code, PROVIDER_OUTSIDE_OWNER_SCOPE)

    def test_expired_decision_is_refused(self):
        decision = self._gate(
            decisions=[_decision(expires_on="2026-01-01")],
            present=lambda name: True, today=date(2026, 10, 20)).decide(
                "fashion_seo_copy")
        self.assertEqual(decision.code, OWNER_DECISION_EXPIRED)

    def test_missing_variable_is_refused(self):
        decision = self._gate(
            decisions=[_decision()], present=None).decide(
                "fashion_seo_copy")
        self.assertEqual(decision.code, CREDENTIAL_UNAVAILABLE)
        self.assertIn("STUB_KEY", decision.detail)

    def test_full_allow_path_reports_owner_and_fingerprint(self):
        owner = _decision()
        decision = self._gate(decisions=[owner],
                              present=lambda name: name == "STUB_KEY"
                              ).decide("fashion_seo_copy")
        self.assertTrue(decision.allowed, decision.detail)
        self.assertEqual(decision.code, ALLOWED_LIVE)
        self.assertEqual(decision.owner_decision_ref, "decision-9")
        self.assertEqual(decision.owner_fingerprint, owner.fingerprint())
        self.assertEqual(decision.failure_class, "")

    def test_a_valid_decision_after_an_expired_one_is_used(self):
        gate = self._gate(
            decisions=[_decision(decision_ref="old",
                                 expires_on="2026-01-01"),
                       _decision(decision_ref="new")],
            present=lambda name: True, today=date(2026, 10, 20))
        decision = gate.decide("fashion_seo_copy")
        self.assertTrue(decision.allowed, decision.detail)
        self.assertEqual(decision.owner_decision_ref, "new")

    def test_live_route_without_a_declared_budget_is_refused(self):
        router, _stub = _mixed_router(budget=0.0)
        decision = ProviderGate(
            router, owner_decisions=_decision(),
            catalogue=_catalogue(_live_decl()),
            credential_present=lambda name: True).decide("fashion_seo_copy")
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.code, BUDGET_NOT_DECLARED)

    def test_production_refuses_live_even_with_full_consent(self):
        decision = self._gate(
            decisions=[_decision()], present=lambda name: True,
            environment=ENVIRONMENT_PRODUCTION).decide("fashion_seo_copy")
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.code, LIVE_BLOCKED_IN_PRODUCTION)

    def test_production_still_allows_the_local_mock(self):
        gate = ProviderGate(_mock_router(),
                            environment=ENVIRONMENT_PRODUCTION)
        decision = gate.decide("fashion_trend_hashtags")
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.code, ALLOWED_MOCK)

    def test_authorized_live_route_runs_end_to_end(self):
        router, stub = _mixed_router()
        gate = ProviderGate(
            router, owner_decisions=_decision(),
            catalogue=_catalogue(_live_decl()),
            credential_present=lambda name: True)
        wiring = wire_fashion_engines(gate)
        from canonical.fashion_copy import FashionBrief
        pack = wiring.copy.generate_pack(
            FashionBrief(title="مانتو پاییزی", fabric_type="کرپ",
                         season="پاییز"))
        self.assertTrue(pack.ok, [r.error for r in pack.reports.values()])
        self.assertEqual(pack.reports["seo_copy"].proposal.provider,
                         "stub-live")
        self.assertGreaterEqual(len(stub.calls), 1)


# =========================================================================
# 5. BUDGET & RATE (read the router's own state, never re-implement it)
# =========================================================================


class BudgetAndRateTests(unittest.TestCase):

    def test_zero_resolved_budget_refuses_at_preflight(self):
        router = _mock_router(budgets={})
        router.budgets["fashion_seo_copy"] = 0.0
        decision = ProviderGate(router).preflight("fashion_seo_copy")
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.code, BUDGET_NOT_DECLARED)

    def test_exhausted_budget_refuses_before_dispatch(self):
        router = _mock_router()
        router._spend["fashion_seo_copy"] = 0.5
        decision = ProviderGate(router).preflight("fashion_seo_copy")
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.code, BUDGET_EXHAUSTED)
        self.assertEqual(decision.failure_class, "B")
        self.assertIn("0.5000", decision.detail)

    def test_soft_limit_is_surfaced_as_a_warning_not_a_refusal(self):
        router = _mock_router()
        router._spend["fashion_seo_copy"] = 0.4  # 80% of 0.50
        decision = ProviderGate(router).preflight("fashion_seo_copy")
        self.assertTrue(decision.allowed, decision.detail)
        self.assertTrue(any("budget_warning" in w
                            for w in decision.warnings), decision.warnings)

    def test_rate_limit_refusal_is_class_a_and_retryable(self):
        router = _mock_router(bucket_capacity=1)
        router._bucket.refill_per_sec = 0.0
        gate = ProviderGate(router)
        self.assertTrue(gate.preflight("fashion_seo_copy").allowed)
        # consume the single token through the router itself
        from canonical.ai_runtime import AiRequest
        router.run(AiRequest(task_type="fashion_seo_copy",
                            schema_id="seo_copy.v1",
                            prompt_payload={}, idempotency_tag="rate"))
        decision = gate.preflight("fashion_seo_copy")
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.code, RATE_LIMITED)
        self.assertEqual(decision.failure_class, "A")

    def test_budget_state_is_the_router_s_own_view(self):
        router = _mock_router()
        state = router.budget_state("fashion_seo_copy")
        self.assertEqual(state["budget_usd"], 0.5)
        self.assertFalse(state["exhausted"])
        self.assertFalse(state["soft_limit"])
        self.assertEqual(router.rate_limit_capacity, 30)


# =========================================================================
# 6. WIRING (strict surface, partial surface only on request)
# =========================================================================


class WiringTests(unittest.TestCase):

    def _partially_denied_gate(self):
        router, _stub = _mixed_router()
        return ProviderGate(router, catalogue=_catalogue(_live_decl()))

    def test_strict_wiring_refuses_a_partial_surface(self):
        gate = self._partially_denied_gate()
        with self.assertRaises(ProviderGateError) as ctx:
            wire_fashion_engines(gate)
        self.assertIn("fashion_seo_copy:OWNER_DECISION_MISSING",
                      str(ctx.exception))
        self.assertEqual(ctx.exception.failure_class, "B")
        self.assertEqual(len(ctx.exception.decisions), 1)

    def test_partial_wiring_is_explicit_when_requested(self):
        gate = self._partially_denied_gate()
        router = gate.guarded_router(strict=False)
        self.assertNotIn("fashion_seo_copy", router.policy)
        self.assertIn("fashion_trend_hashtags", router.policy)
        # a refused task is not silently routable on the guarded router
        from canonical.ai_runtime import AiRequest
        with self.assertRaises(AiProviderError):
            router.run(AiRequest(task_type="fashion_seo_copy",
                                schema_id="seo_copy.v1",
                                prompt_payload={}))

    def test_guarded_router_inherits_budgets_ledger_and_capacity(self):
        from canonical.ai_runtime import UsageLedger
        ledger = UsageLedger()
        router = _mock_router(budgets={"fashion_seo_copy": 0.25},
                             ledger=ledger, bucket_capacity=7)
        guarded = ProviderGate(router).guarded_router()
        self.assertEqual(guarded.budgets, {"fashion_seo_copy": 0.25})
        self.assertIs(guarded.ledger, ledger)
        self.assertEqual(guarded.rate_limit_capacity, 7)

    def test_guarded_router_shares_d063_spend_accounting(self):
        router = _mock_router()
        router._spend["fashion_seo_copy"] = 0.1
        guarded = ProviderGate(router).guarded_router()
        self.assertEqual(guarded.budget_state("fashion_seo_copy")
                         ["spent_usd"], 0.1)
        guarded._spend["fashion_seo_copy"] = 0.2
        self.assertEqual(router.budget_state("fashion_seo_copy")
                         ["spent_usd"], 0.2)

    def test_wiring_decisions_are_a_frozen_snapshot(self):
        wiring = wire_fashion_engines(offline_gate())
        self.assertIsInstance(wiring.decisions, tuple)
        self.assertEqual(len(wiring.decisions), 4)
        with self.assertRaises(Exception):
            wiring.decisions[0].allowed = False  # frozen dataclass

    def test_refusals_property_exposes_only_denials(self):
        gate = self._partially_denied_gate()
        gate.plan()
        self.assertEqual([d.code for d in gate.refusals],
                         [OWNER_DECISION_MISSING])


# =========================================================================
# 7. HYGIENE: no network, no environment read, no credential material
# =========================================================================


class HygieneTests(unittest.TestCase):

    FORBIDDEN_MODULES = {"requests", "urllib", "http", "socket",
                         "aiohttp", "httpx", "subprocess"}
    BANNED_STRINGS = ("api_key", "apikey", "secret", "bearer",
                      "authorization")
    PUBLICATION_VERBS = ("publish", "approve", "send", "post_")

    def _tree(self):
        return ast.parse(GATE_MODULE.read_text(encoding="utf-8"))

    def test_no_network_or_process_import_surface(self):
        for node in ast.walk(self._tree()):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotIn(alias.name.split(".")[0],
                                     self.FORBIDDEN_MODULES,
                                     f"surface: {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                self.assertNotIn((node.module or "").split(".")[0],
                                 self.FORBIDDEN_MODULES,
                                 f"surface: {node.module}")

    def test_no_environment_read(self):
        source = GATE_MODULE.read_text(encoding="utf-8")
        for token in ("os.environ", "getenv", "os.getenv"):
            self.assertNotIn(token, source)
        for node in ast.walk(self._tree()):
            if isinstance(node, ast.Attribute):
                self.assertNotEqual(node.attr, "environ")

    def test_no_credential_material_in_any_string_constant(self):
        for node in ast.walk(self._tree()):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                low = node.value.lower()
                for token in self.BANNED_STRINGS:
                    self.assertNotIn(
                        token, low,
                        f"credential-adjacent string {token!r}: "
                        f"{node.value[:80]!r}")

    def test_no_publication_verb_on_the_gate_surface(self):
        # `decide` here is a PERMISSION verdict, not a lifecycle
        # decision; the human-only lifecycle decide() stays in
        # ProposalLifecycle. Publication verbs must not exist at all.
        for node in ast.walk(self._tree()):
            if isinstance(node, ast.FunctionDef):
                self.assertFalse(
                    node.name.startswith(self.PUBLICATION_VERBS),
                    f"publication surface: {node.name}")
        for name in dir(ProviderGate):
            if name.startswith("__"):
                continue
            self.assertFalse(name.startswith(self.PUBLICATION_VERBS),
                             f"publication surface: {name}")

    def test_module_imports_only_approved_collaborators(self):
        modules = set()
        for node in ast.walk(self._tree()):
            if isinstance(node, ast.ImportFrom):
                modules.add(node.module or "")
        self.assertEqual(modules, {
            "__future__",
            "dataclasses",
            "datetime",
            "typing",
            "canonical.ai_contracts",
            "canonical.ai_runtime",
            # local imports inside wire_fashion_engines(): the two Phase 4
            # engines this gate exists to wire
            "canonical.fashion_copy",
            "canonical.fashion_trends",
        })

    def test_the_gate_never_receives_or_echoes_a_value(self):
        # the presence predicate is asked for a NAME; a sentinel value
        # can never appear in a decision record because it is never passed
        sentinel = "SHOULD-NEVER-APPEAR"
        asked = []

        def present(name):
            asked.append(name)
            return True

        router, _stub = _mixed_router()
        gate = ProviderGate(router, owner_decisions=_decision(),
                            catalogue=_catalogue(_live_decl()),
                            credential_present=present)
        record = gate.decide("fashion_seo_copy").to_dict()
        self.assertEqual(asked, ["STUB_KEY"])
        self.assertNotIn(sentinel, json.dumps(record))
        self.assertEqual(
            sorted(record),
            sorted(["schema_version", "phase", "task_type", "provider",
                    "model", "schema_id", "allowed", "code", "environment",
                    "detail", "owner_decision_ref", "owner_fingerprint"]))

    def test_default_presence_predicate_is_fail_closed(self):
        from canonical.ai_provider_gate import _never_present
        self.assertFalse(_never_present("ANY_KEY"))
        self.assertFalse(_never_present(""))


if __name__ == "__main__":
    unittest.main()

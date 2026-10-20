"""Phase 4 §4.2 — Trend & Hashtag Intelligence tests (D-172 / roadmap §4.2).

Contract under test: local/canonical/fashion_trends.py

Layers:
  1. Contract registry: `trend_hashtag_set.v1` is registered, strict,
     versioned, pinned to the frozen fixture, and the scripted mock
     output validates against it.
  2. Template parity: `fashion_trend_hashtags@v1.0.0` resolves, binds
     the SAME schema id as the routing policy, carries the brief facts
     in its prompt and its response_contract does not drift.
  3. Brief identity: deterministic request key (AC-3), product scoping,
     and Class-B refusals BEFORE any dispatch.
  4. Grounding — the point of §4.2: the set is refused unless it
     partitions `hashtags` and anchors the merchant's OWN category and
     season, with the shared vocabulary guard and the invented-facts
     guard firing on the tag surface too.
  5. Lifecycle boundary: persist lands a PROPOSED item (queue +
     provenance + event), repeats are idempotent, dry-run persists
     nothing, and the module exposes NO publication surface.
  6. Provider neutrality: works through any `AiProvider`; the shipped
     routing key is mock-only and offline.
"""

import ast
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOCAL = HERE.parent
for p in (str(LOCAL), str(LOCAL / "canonical"), str(LOCAL / "services")):
    if p not in sys.path:
        sys.path.insert(0, p)

from canonical import fashion_trends as ft  # noqa: E402
from canonical.ai_contracts import (  # noqa: E402
    AI_OUTPUT_SCHEMAS, OutputValidationError, load_schemas_fixture,
    validate_ai_output)
from canonical.ai_proposal_lifecycle import (  # noqa: E402
    PROPOSED, ProposalLifecycle)
from canonical.ai_runtime import (  # noqa: E402
    DEFAULT_ROUTING_POLICY, AiProvider, AiProviderError, AiResponse,
    MockAiProvider, ModelRouter, RouteTarget)
from canonical.ai_tasks import (  # noqa: E402
    TaskEntity, check_hashtag_vocabulary)
from canonical.ai_templates import TemplateRegistry  # noqa: E402
from canonical.verification_tool import VerificationQueue  # noqa: E402
from services.sync_engine import EventStore, ProvenanceEngine  # noqa: E402

CANON = LOCAL / "canonical"
TEMPLATES = LOCAL / "templates"
TREND_MODULE = CANON / "fashion_trends.py"

_BRIEF = {
    "garment_category": "مانتو",
    "season": "پاییز",
    "fabric_type": "کرپ",
    "notes": "فرم ایستاده و دوخت تمیز",
}


def _brief(**over):
    return ft.TrendBrief(**{**_BRIEF, **over})


def _entity(**over):
    return _brief(**over).entity()


def _set(**over):
    """A valid, grounded tag set for the default brief (مانتو/پاییز)."""
    payload = {
        "hashtags": ["مانتو", "مانتو_پاییزی", "پاییز", "پوشاک_پاییزی",
                     "استایل_پاییزی", "مانتو_کرپ"],
        "category_tags": ["مانتو", "مانتو_پاییزی"],
        "season_tags": ["پاییز", "پوشاک_پاییزی"],
        "niche_tags": ["استایل_پاییزی", "مانتو_کرپ"],
        "rationale": "دستهٔ مانتو با فصل پاییز و هشتگ تخصصی ترکیب شد",
    }
    payload.update(over)
    return payload


def _make_stack(tmp):
    prov = ProvenanceEngine(os.path.join(tmp, "prov.jsonl"))
    store = EventStore(os.path.join(tmp, "events.jsonl"))
    queue = VerificationQueue(os.path.join(tmp, "queue.json"))
    life = ProposalLifecycle(store, prov, queue=queue,
                             applier=lambda pid, ref: {"ok": True})
    return prov, store, queue, life


def _router(payload=None, **over):
    if payload is None:
        return ModelRouter({"mock": MockAiProvider()})
    return ModelRouter({"mock": MockAiProvider(
        responses={"trend_hashtag_set.v1": json.dumps(
            payload, ensure_ascii=False)}, **over)})


def _engine(lifecycle=None, payload=None, **over):
    return ft.FashionTrendEngine(_router(payload, **over),
                                 lifecycle=lifecycle)


class _AdaptiveProvider(AiProvider):
    """Provider-neutral stub that builds a grounded set from the REQUEST.

    Proves the engine depends on the M1 `AiProvider` boundary only — no
    import of, or assumption about, the mock.
    """

    name = "stub"

    def __init__(self, fail_with=None):
        self.calls = []
        self.fail_with = fail_with

    def generate(self, request):
        self.calls.append(request)
        if self.fail_with == "timeout":
            raise AiProviderError("provider timeout after retries",
                                  failure_class="A")
        facts = request.prompt_payload
        # a hashtag is ONE unbroken token: the merchant's own words are
        # normalized exactly as the composer would render them
        category = ft.normalize_tag(facts.get("garment_category"))
        season = ft.normalize_tag(facts.get("season"))
        fabric = ft.normalize_tag(facts.get("fabric_type"))
        category_tags = [category, f"استایل_{category}"]
        season_tags = [season, f"پوشاک_{season}"]
        niche_tags = [f"{category}_{season}", f"ترند_{season}"]
        if fabric:
            niche_tags.append(f"پارچه_{fabric}")
        parsed = {
            "hashtags": category_tags + season_tags + niche_tags,
            "category_tags": category_tags,
            "season_tags": season_tags,
            "niche_tags": niche_tags,
            "rationale": (f"دستهٔ {category} در فصل {season} با هشتگ‌های "
                          "تخصصی پوشش داده شد"),
        }
        raw = json.dumps(parsed, ensure_ascii=False)
        return AiResponse(text=raw, parsed=parsed,
                          usage={"prompt_tokens": 12,
                                 "completion_tokens": 12},
                          provider=self.name, model="stub-1",
                          finish_reason="stop", latency_ms=1)


_STUB_POLICY = {
    ft.TASK_TYPE: RouteTarget("stub", "stub-1", ft.SCHEMA_ID,
                              budget_usd=1.0),
}


# =========================================================================
# 1. CONTRACT (strict, versioned, fixture pin, mock script)
# =========================================================================


class ContractRegistryTests(unittest.TestCase):

    def test_contract_is_registered_strict_and_versioned(self):
        self.assertIn(ft.SCHEMA_ID, AI_OUTPUT_SCHEMAS)
        schema = AI_OUTPUT_SCHEMAS[ft.SCHEMA_ID]
        self.assertIs(schema["additionalProperties"], False)
        self.assertEqual(schema["title"], ft.SCHEMA_ID)
        self.assertEqual(sorted(schema["required"]), sorted(
            ["hashtags", "category_tags", "season_tags", "niche_tags",
             "rationale"]))

    def test_tag_and_group_bounds_are_pinned(self):
        props = AI_OUTPUT_SCHEMAS[ft.SCHEMA_ID]["properties"]
        self.assertEqual(props["hashtags"]["minItems"], ft.MIN_TAGS)
        self.assertEqual(props["hashtags"]["maxItems"], ft.MAX_TAGS)
        self.assertEqual(props["hashtags"]["items"]["maxLength"], 60)
        self.assertEqual(props["category_tags"]["minItems"], 1)
        self.assertEqual(props["season_tags"]["minItems"], 1)
        self.assertEqual(props["niche_tags"]["minItems"], 0)

    def test_registry_matches_frozen_fixture(self):
        fixture = load_schemas_fixture(
            str(HERE / "fixtures" / "ai" / "schemas.json"))
        self.assertEqual(AI_OUTPUT_SCHEMAS, fixture,
                         "contract drift: shipped schemas differ from the "
                         "pinned fixture")

    def test_mock_provider_has_a_valid_script_for_the_contract(self):
        self.assertIn(ft.SCHEMA_ID, MockAiProvider.MOCK_OUTPUTS)
        result = validate_ai_output(ft.SCHEMA_ID,
                                    MockAiProvider.MOCK_OUTPUTS[ft.SCHEMA_ID])
        self.assertTrue(result["valid"], result)

    def test_mock_script_is_grounded_for_the_default_brief(self):
        payload = MockAiProvider.MOCK_OUTPUTS[ft.SCHEMA_ID]
        self.assertEqual(ft.check_hashtag_set(payload, _entity()), [])


# =========================================================================
# 2. TEMPLATE PARITY (D-067: template and contract travel together)
# =========================================================================


class TemplateParityTests(unittest.TestCase):

    def setUp(self):
        self.registry = TemplateRegistry(str(TEMPLATES))

    def test_template_binds_the_registered_contract(self):
        t = self.registry.get(ft.TEMPLATE_ID)
        self.assertEqual(t["schema_id"], ft.SCHEMA_ID)
        self.assertEqual(t["version"], "v1.0.0")
        self.assertEqual(
            json.loads(json.dumps(t["response_contract"], sort_keys=True)),
            json.loads(json.dumps(AI_OUTPUT_SCHEMAS[ft.SCHEMA_ID],
                                  sort_keys=True)),
            "template response_contract drifted from the registry")
        self.assertEqual(len(t["template_hash"]), 64)

    def test_policy_routes_the_template_schema(self):
        target = DEFAULT_ROUTING_POLICY[ft.TASK_TYPE]
        self.assertEqual(target.schema_id, ft.SCHEMA_ID)
        self.assertEqual(target.provider, "mock")
        self.assertEqual(ft.TEMPLATE_ID, ft.TASK_TYPE)

    def test_prompt_embeds_brief_facts_and_template_identity(self):
        info = _engine().preview_prompt(_brief())
        self.assertEqual(info["template_id"], ft.TEMPLATE_ID)
        self.assertEqual(info["schema_id"], ft.SCHEMA_ID)
        self.assertEqual(len(info["template_hash"]), 64)
        for value in (_BRIEF["garment_category"], _BRIEF["season"],
                      _BRIEF["fabric_type"], _BRIEF["notes"]):
            self.assertIn(value, info["prompt"])

    def test_preview_does_not_dispatch(self):
        provider = MockAiProvider()
        engine = ft.FashionTrendEngine(ModelRouter({"mock": provider}))
        engine.preview_prompt(_brief())
        self.assertEqual(provider.calls, [])

    def test_rendered_prompt_is_byte_identical_across_engines(self):
        self.assertEqual(_engine().preview_prompt(_brief()),
                         _engine().preview_prompt(_brief()))

    def test_brief_facts_change_the_rendered_prompt(self):
        a = _engine().preview_prompt(_brief())
        b = _engine().preview_prompt(_brief(season="تابستان"))
        self.assertNotEqual(a["prompt"], b["prompt"])
        # the TEMPLATE hash pins the template, not the context
        self.assertEqual(a["template_hash"], b["template_hash"])


# =========================================================================
# 3. BRIEF IDENTITY + INPUT REFUSALS (AC-3, Class B before dispatch)
# =========================================================================


class BriefIdentityTests(unittest.TestCase):

    def test_key_is_deterministic_and_scoped(self):
        self.assertEqual(_brief().key(), _brief().key())
        self.assertTrue(_brief().key().startswith("fashion-trend/brief/"))
        self.assertEqual(_brief().key(),
                         "fashion-trend/brief/پاییز/مانتو/کرپ")
        entity = _brief().entity()
        self.assertIsInstance(entity, TaskEntity)
        self.assertEqual(entity.kind, "fashion_trend")
        self.assertEqual(entity.key, _brief().key())

    def test_product_id_scopes_the_key(self):
        pid = "a1b2c3d4-1111-4222-a333-444444444444"
        scoped = _brief(product_id=pid)
        self.assertEqual(scoped.key(),
                         f"fashion-trend/{pid}/پاییز/مانتو/کرپ")
        self.assertNotEqual(scoped.key(), _brief().key())
        self.assertEqual(scoped.context()["product_id"], pid)
        self.assertNotIn("product_id", _brief().context())

    def test_context_carries_only_the_brief_facts(self):
        self.assertEqual(_brief().context(), {
            "garment_category": "مانتو", "season": "پاییز",
            "fabric_type": "کرپ", "notes": _BRIEF["notes"]})

    def test_invalid_briefs_are_class_b_refusals_before_any_dispatch(self):
        provider = MockAiProvider()
        engine = ft.FashionTrendEngine(ModelRouter({"mock": provider}))
        for bad in ({"garment_category": " "}, {"garment_category": "م"},
                    {"season": ""}, {"garment_category": "م" * 61},
                    {"season": "پ" * 41}, {"notes": "x" * 2001},
                    {"garment_category": 123},
                    {"garment_category": "ء"}):
            with self.assertRaises(ft.TrendInputError, msg=str(bad)):
                engine.generate(_brief(**bad))
        self.assertEqual(provider.calls, [])
        self.assertEqual(ft.TrendInputError.failure_class, "B")

    def test_product_id_is_bounded(self):
        for bad in ({"product_id": "p" * 65}, {"product_id": 7}):
            with self.assertRaises(ft.TrendInputError, msg=str(bad)):
                _brief(**bad).validated()

    def test_normalize_tag_collapses_separators(self):
        self.assertEqual(ft.normalize_tag("#مانتو پاییزی"),
                         "مانتو_پاییزی")
        self.assertEqual(ft.normalize_tag("مانتو\u200cپاییزی"),
                         "مانتو_پاییزی")
        self.assertEqual(ft.normalize_tag("  #مانتو-پاییزی "),
                         "مانتو_پاییزی")
        self.assertEqual(ft.normalize_tag(None), "")


# =========================================================================
# 4. GROUNDING — "based on garment category and season" is CHECKED
# =========================================================================


class GroundingTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        self.prov, self.store, self.queue, self.life = \
            _make_stack(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    def _assert_class_b(self, payload, message, **brief_over):
        rep = _engine(self.life, payload).generate(
            _brief(**brief_over), mode="persist")
        self.assertFalse(rep.ok, rep.divergences)
        self.assertEqual(rep.failure_class, "B")
        self.assertTrue(any(message in d for d in rep.divergences),
                        rep.divergences)
        self.assertEqual(self.prov.records, [])
        self.assertEqual(self.queue.load_pending(), [])
        self.assertEqual(list(self.store.records.values()), [])
        return rep

    def test_happy_path_is_grounded_and_proposed(self):
        rep = _engine(self.life).generate(_brief(), mode="persist")
        self.assertTrue(rep.ok, rep.divergences)
        self.assertEqual(rep.state, "PROPOSED")
        payload = rep.proposal.payload
        self.assertEqual(
            set(payload["hashtags"]),
            set(payload["category_tags"]) | set(payload["season_tags"])
            | set(payload["niche_tags"]))
        self.assertIn("مانتو", payload["category_tags"])
        self.assertIn("پاییز", payload["season_tags"])

    def test_missing_category_anchor_is_class_b(self):
        rep = self._assert_class_b(
            _set(category_tags=["مانتو_پاییزی"],
                 hashtags=["مانتو_پاییزی", "پاییز", "پوشاک_پاییزی",
                           "استایل_پاییزی", "مانتو_کرپ"],
                 niche_tags=["استایل_پاییزی", "مانتو_کرپ"]),
            "never contains the merchant's own category")

    def test_missing_season_anchor_is_class_b(self):
        self._assert_class_b(
            _set(season_tags=["پاییزی"],
                 hashtags=["مانتو", "مانتو_پاییزی", "پاییزی",
                           "استایل_پاییزی", "مانتو_کرپ"]),
            "never contains the merchant's own season")

    def test_a_near_token_does_not_satisfy_the_anchor(self):
        # 'مانتوپاییزی' is not 'مانتو' — grounding compares normalized
        # equality, never a substring
        self._assert_class_b(
            _set(category_tags=["مانتوپاییزی"],
                 hashtags=["مانتوپاییزی", "پاییز", "پوشاک_پاییزی",
                           "استایل_پاییزی", "مانتو_کرپ"],
                 niche_tags=["استایل_پاییزی", "مانتو_کرپ"]),
            "never contains the merchant's own category")

    def test_ungrouped_tag_is_class_b(self):
        self._assert_class_b(
            _set(hashtags=_set()["hashtags"] + ["بوت_پاییزی"]),
            "do not partition")

    def test_dropped_tag_is_class_b(self):
        self._assert_class_b(
            _set(hashtags=_set()["hashtags"][:-1]),
            "do not partition")

    def test_tag_in_two_groups_is_class_b(self):
        self._assert_class_b(
            _set(niche_tags=["استایل_پاییزی", "مانتو_کرپ", "پاییز"]),
            "more than one group")

    def test_duplicate_tag_is_class_b(self):
        tags = _set()["hashtags"] + ["مانتو"]
        self._assert_class_b(_set(hashtags=tags), "duplicate hashtags")

    def test_whitespace_inside_a_tag_is_class_b(self):
        self._assert_class_b(
            _set(hashtags=["مانتو", "مانتو پاییزی", "پاییز",
                           "پوشاک_پاییزی", "استایل_پاییزی", "مانتو_کرپ"],
                 category_tags=["مانتو", "مانتو پاییزی"]),
            "contains whitespace")

    def test_hash_inside_a_tag_is_class_b(self):
        self._assert_class_b(
            _set(hashtags=["مانتو", "ما#نتو", "پاییز", "پوشاک_پاییزی",
                           "استایل_پاییزی", "مانتو_کرپ"],
                 category_tags=["مانتو", "ما#نتو"]),
            "contains a '#'")

    def test_one_character_tag_is_class_b(self):
        self._assert_class_b(
            _set(hashtags=["مانتو", "#ا", "پاییز", "پوشاک_پاییزی",
                           "استایل_پاییزی"],
                 category_tags=["مانتو", "#ا"]),
            "too short")

    def test_near_miss_of_approved_vocabulary_is_class_b(self):
        # 'کرمی' is a near-miss of the approved colour 'کرم'; it is not
        # a fact the merchant stated, so the shared guard fires
        self._assert_class_b(
            _set(hashtags=_set()["hashtags"] + ["کرمی"],
                 niche_tags=["استایل_پاییزی", "مانتو_کرپ", "کرمی"]),
            "near-miss")

    def test_invented_price_in_the_rationale_is_class_b(self):
        self._assert_class_b(
            _set(rationale="این ست با تخفیف ۹۹۰,۰۰۰ تومان عرضه می‌شود"),
            "AC-4/AC-5")

    def test_invented_link_in_the_rationale_is_class_b(self):
        self._assert_class_b(
            _set(rationale="برای خرید به https://shop.example/mano بروید"),
            "AC-4/AC-5")

    def test_price_quoted_from_the_brief_is_allowed(self):
        notes = "قیمت ۲۵۰,۰۰۰ تومان"
        rep = _engine(self.life, _set(
            rationale="قیمت ۲۵۰,۰۰۰ تومان را خود فروشنده اعلام کرده است")
        ).generate(_brief(notes=notes), mode="persist")
        self.assertTrue(rep.ok, rep.divergences)

    def test_merchant_stated_fabric_is_not_treated_as_invented(self):
        # 'کرپ' sits one letter from the approved colour 'کرم'; it is
        # the seller's own fabric fact, so the narrow `allow` rule lets
        # it through — and ONLY while the brief states it
        rep = _engine(self.life).generate(_brief(), mode="persist")
        self.assertTrue(rep.ok, rep.divergences)
        self.assertIn("کرپ", rep.proposal.payload["niche_tags"])

        # the same tag set, for a brief that never stated the fabric:
        # the identical token is now model-authored vocabulary
        tag = "کرپ"
        without_fabric = _engine(self.life, _set(
            hashtags=_set()["hashtags"] + [tag],
            niche_tags=_set()["niche_tags"] + [tag],
        )).generate(_brief(fabric_type=""), mode="persist")
        self.assertFalse(without_fabric.ok)
        self.assertTrue(any("near-miss" in d
                            for d in without_fabric.divergences),
                        without_fabric.divergences)

    def test_the_shared_guard_keeps_its_conservative_default(self):
        # documenting the rule itself: with no `allow`, no exemption —
        # the optional parameter does not weaken any existing caller
        self.assertTrue(check_hashtag_vocabulary(["کرمی"], channel="t"))
        self.assertTrue(check_hashtag_vocabulary(["کرپ"], channel="t"))
        self.assertEqual(
            check_hashtag_vocabulary(["کرپ"], channel="t", allow=["کرپ"]),
            [])

    def test_contract_bounds_are_never_repaired(self):
        # 4 tags / 31 tags: the CONTRACT refuses before the guard runs
        for tags in (_set()["hashtags"][:4],
                     _set()["hashtags"] + [f"تگ_{i}" for i in range(25)]):
            with self.assertRaises(OutputValidationError):
                _engine(self.life, _set(hashtags=tags)).generate(
                    _brief(), mode="persist")
        self.assertEqual(self.queue.load_pending(), [])
        self.assertEqual(self.prov.records, [])

    def test_dry_run_persists_nothing_but_calls_the_model(self):
        provider = MockAiProvider()
        engine = ft.FashionTrendEngine(ModelRouter({"mock": provider}),
                                       lifecycle=self.life)
        rep = engine.generate(_brief())
        self.assertTrue(rep.ok, rep.divergences)
        self.assertEqual(rep.mode, "dry-run")
        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(self.prov.records, [])
        self.assertEqual(self.queue.load_pending(), [])


# =========================================================================
# 5. HITL LIFECYCLE BOUNDARY (D-158/D-050 — PROPOSED is terminal here)
# =========================================================================


class LifecycleBoundaryTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        self.prov, self.store, self.queue, self.life = \
            _make_stack(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    def test_persist_lands_one_proposed_item(self):
        engine = _engine(self.life)
        rep = engine.generate(_brief(), mode="persist")
        self.assertTrue(rep.ok, rep.divergences)
        self.assertEqual(rep.verdict, "new")
        self.assertEqual(self.life.state_of(rep.proposal_id), PROPOSED)
        pending = self.queue.load_pending()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["code"],
                         f"AI_{ft.TASK_TYPE.upper()}")
        self.assertEqual(len(self.prov.records), 1)

    def test_repeat_persist_is_idempotent(self):
        engine = _engine(self.life)
        first = engine.generate(_brief(), mode="persist")
        second = engine.generate(_brief(), mode="persist")
        self.assertTrue(first.ok and second.ok)
        self.assertEqual(second.verdict, "skipped_duplicate")
        self.assertEqual(len(self.queue.load_pending()), 1)
        self.assertEqual(len(self.prov.records), 1)

    def test_different_seasons_are_different_records(self):
        provider = _AdaptiveProvider()
        engine = ft.FashionTrendEngine(
            ModelRouter({"stub": provider}, policy=_STUB_POLICY),
            lifecycle=self.life)
        a = engine.generate(_brief(season="پاییز"), mode="persist")
        b = engine.generate(_brief(season="زمستان"), mode="persist")
        self.assertTrue(a.ok and b.ok, (a.divergences, b.divergences))
        self.assertNotEqual(a.proposal_id, b.proposal_id)
        self.assertEqual(len(self.queue.load_pending()), 2)
        self.assertNotEqual(a.entity_key, b.entity_key)

    def test_persist_without_a_lifecycle_fails_closed(self):
        with self.assertRaises(RuntimeError) as ctx:
            _engine().generate(_brief(), mode="persist")
        self.assertIn("ProposalLifecycle", str(ctx.exception))

    def test_report_is_json_serializable(self):
        rep = _engine().generate(_brief())
        blob = json.dumps(rep.to_dict(), ensure_ascii=False)
        self.assertIn(ft.TASK_TYPE, blob)
        self.assertTrue(rep.to_dict()["ok"])


# =========================================================================
# 6. AUTHORITY / HYGIENE: no network, no credentials, no publication edge
# =========================================================================


class AuthorityBoundaryTests(unittest.TestCase):

    FORBIDDEN_MODULES = {"requests", "urllib", "http", "socket",
                         "aiohttp", "httpx"}
    PUBLICATION_VERBS = ("publish", "approve", "accept", "decide",
                         "send", "post_")

    def test_no_network_import_surface(self):
        tree = ast.parse(TREND_MODULE.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotIn(alias.name.split(".")[0],
                                     self.FORBIDDEN_MODULES,
                                     f"network surface: {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                self.assertNotIn((node.module or "").split(".")[0],
                                 self.FORBIDDEN_MODULES,
                                 f"network surface: {node.module}")

    def test_no_environment_or_credential_access(self):
        source = TREND_MODULE.read_text(encoding="utf-8")
        for token in ("os.environ", "getenv", "API_KEY", "api_key",
                      "Authorization", "Bearer"):
            self.assertNotIn(token, source)
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                self.assertNotEqual(node.attr, "environ")

    def test_no_publication_verb_in_the_engine_surface(self):
        tree = ast.parse(TREND_MODULE.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                self.assertFalse(
                    node.name.startswith(self.PUBLICATION_VERBS),
                    f"publication surface leaked into the engine: "
                    f"{node.name}")
        for name in dir(ft.FashionTrendEngine):
            if name.startswith("__"):
                continue
            self.assertFalse(name.startswith(self.PUBLICATION_VERBS),
                             f"publication surface on the engine: {name}")

    def test_module_imports_only_approved_collaborators(self):
        tree = ast.parse(TREND_MODULE.read_text(encoding="utf-8"))
        modules = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                modules.add(node.module or "")
        self.assertEqual(modules, {
            "__future__",
            "dataclasses",
            "typing",
            "canonical.ai_runtime",
            "canonical.ai_tasks",
            "canonical.ai_templates",
            "canonical.fashion_copy",
        })

    def test_the_shared_guards_are_reused_not_forked(self):
        import canonical.ai_tasks as tasks
        self.assertIs(ft.check_hashtag_vocabulary,
                      tasks.check_hashtag_vocabulary)
        import canonical.fashion_copy as fc
        self.assertIs(ft.check_invented_facts, fc.check_invented_facts)


# =========================================================================
# 7. PROVIDER NEUTRALITY (D-045: no provider is baked in)
# =========================================================================


class ProviderNeutralityTests(unittest.TestCase):

    def test_shipped_policy_is_offline_mock_only(self):
        target = DEFAULT_ROUTING_POLICY[ft.TASK_TYPE]
        self.assertEqual(target.provider, "mock")
        self.assertEqual(target.model, "mock-1")

    def test_engine_runs_on_any_ai_provider(self):
        provider = _AdaptiveProvider()
        engine = ft.FashionTrendEngine(
            ModelRouter({"stub": provider}, policy=_STUB_POLICY))
        rep = engine.generate(_brief())
        self.assertTrue(rep.ok, rep.divergences)
        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(rep.proposal.provider, "stub")
        self.assertEqual(rep.proposal.model, "stub-1")

    def test_grounding_holds_for_any_category_and_season(self):
        provider = _AdaptiveProvider()
        engine = ft.FashionTrendEngine(
            ModelRouter({"stub": provider}, policy=_STUB_POLICY))
        for category, season in (("شلوار", "تابستان"),
                                 ("کت و جلیقه", "زمستان"),
                                 ("شومیز", "بهار")):
            rep = engine.generate(_brief(garment_category=category,
                                        season=season,
                                        fabric_type=""))
            self.assertTrue(rep.ok, (category, rep.divergences))
            payload = rep.proposal.payload
            self.assertIn(ft.normalize_tag(category),
                          [ft.normalize_tag(t)
                           for t in payload["category_tags"]])
            self.assertIn(ft.normalize_tag(season),
                          [ft.normalize_tag(t)
                           for t in payload["season_tags"]])

    def test_batch_covers_multiple_briefs(self):
        provider = _AdaptiveProvider()
        engine = ft.FashionTrendEngine(
            ModelRouter({"stub": provider}, policy=_STUB_POLICY))
        summary = engine.generate_batch([
            _brief(garment_category="شلوار", season="تابستان"),
            _brief(garment_category="شومیز", season="بهار"),
        ])
        self.assertEqual(summary["requested"], 2)
        self.assertEqual(summary["processed"], 2)
        self.assertEqual(summary["ok"], 2)
        self.assertTrue(summary["all_ok"])
        self.assertEqual(len(provider.calls), 2)
        self.assertIn(ft.TASK_TYPE, summary["spend_by_task"])

    def test_a_failing_item_does_not_abort_the_batch(self):
        # the static mock script is grounded for مانتو/پاییز only, so
        # the second brief is refused — and the report says so
        engine = _engine()
        summary = engine.generate_batch([
            _brief(), _brief(garment_category="شلوار", season="تابستان"),
        ])
        self.assertEqual(summary["requested"], 2)
        self.assertEqual(summary["processed"], 2)
        self.assertEqual(summary["ok"], 1)
        self.assertEqual(summary["failed"], 1)
        self.assertFalse(summary["all_ok"])

    def test_provider_failure_maps_to_a_failed_report_not_a_crash(self):
        engine = ft.FashionTrendEngine(ModelRouter(
            {"stub": _AdaptiveProvider(fail_with="timeout")},
            policy=_STUB_POLICY))
        rep = engine.generate(_brief())
        self.assertFalse(rep.ok)
        self.assertEqual(rep.failure_class, "A")
        self.assertIn("timeout", rep.error or "")


if __name__ == "__main__":
    unittest.main()

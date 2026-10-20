"""Phase 4 §4.1 — Fashion copywriting engine tests (D-172 / AC-3).

Contract under test: local/canonical/fashion_copy.py

Layers:
  1. Contract registry: telegram_announcement.v1 / seo_copy.v1 are
     registered, strict, versioned, pinned to the frozen fixture, and
     the Telegram length literal is re-asserted against the D-073
     publisher constant (no silent drift).
  2. Template parity: the three shipped templates resolve in the
     registry, bind the SAME schema id as the routing policy, and their
     response_contract is byte-equal to the registered contract.
  3. Tone presets: deterministic rendering, normalization, refusal of
     unknown tones BEFORE dispatch, and the tone flowing end-to-end
     into the model request (provider-agnostic stub, not just mocks).
  4. Channel output: all three channels produce contract-valid copy on
     the deterministic mock; the Telegram text (incl. CTA + hashtags)
     respects the channel cap; over-cap / invented price / invented
     link / near-miss keyword are Class B and persist NOTHING.
  5. Lifecycle boundary: persist mode lands three PROPOSED items (queue
     + provenance + events), repeats are idempotent, dry-run is
     side-effect free, and the module exposes NO publication surface.
  6. Provider neutrality: the engine works with any AiProvider through
     the routing policy; the shipped defaults are mock-only/offline.
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
ROOT = LOCAL.parent
for p in (str(LOCAL), str(LOCAL / "canonical"), str(LOCAL / "services")):
    if p not in sys.path:
        sys.path.insert(0, p)

from canonical import fashion_copy as fc  # noqa: E402
from canonical.ai_contracts import (  # noqa: E402
    AI_OUTPUT_SCHEMAS, load_schemas_fixture, validate_ai_output)
from canonical.ai_proposal_lifecycle import (  # noqa: E402
    PROPOSED, ProposalLifecycle)
from canonical.ai_runtime import (  # noqa: E402
    DEFAULT_ROUTING_POLICY, AiProvider, AiResponse, MockAiProvider,
    ModelRouter, RouteTarget)
from canonical.ai_tasks import (  # noqa: E402
    CaptionTask, TaskEntity, check_hashtag_vocabulary)
from canonical.ai_templates import TemplateRegistry  # noqa: E402
from canonical.telegram_contracts import MAX_TEXT_CHARS as TG_MAX  # noqa: E402
from canonical.verification_tool import VerificationQueue  # noqa: E402
from services.sync_engine import EventStore, ProvenanceEngine  # noqa: E402

CANON = LOCAL / "canonical"
TEMPLATES = LOCAL / "templates"
FASHION_MODULE = CANON / "fashion_copy.py"

_BRIEF = {
    "title": "مانتو پاییزی",
    "fabric_type": "کرپ",
    "season": "پاییز",
    "notes": "فرم ایستاده و دوخت تمیز",
}


def _brief(**over):
    return fc.FashionBrief(**{**_BRIEF, **over})


def _entity(**over):
    return _brief(**over).entity()


def _make_stack(tmp):
    prov = ProvenanceEngine(os.path.join(tmp, "prov.jsonl"))
    store = EventStore(os.path.join(tmp, "events.jsonl"))
    queue = VerificationQueue(os.path.join(tmp, "queue.json"))
    life = ProposalLifecycle(store, prov, queue=queue,
                             applier=lambda pid, ref: {"ok": True})
    return prov, store, queue, life


def _router(responses=None):
    return ModelRouter({"mock": MockAiProvider(responses=responses)})


def _engine(lifecycle=None, responses=None):
    return fc.FashionCopywritingEngine(
        _router(responses=responses), lifecycle=lifecycle)


def _tg_payload(**over):
    payload = {
        "announcement_fa": "مانتو پاییزی جدید رسید؛ پارچه کرپ نرم با فرم "
                           "ایستاده.",
        "hashtags": ["#پاییز", "#پوشاک"],
        "cta_fa": "برای مشاوره سایز پیام دهید",
    }
    payload.update(over)
    return payload


def _seo_payload(**over):
    payload = {
        "meta_description_fa": "مانتو پاییزی زنانه با پارچه کرپ نرم و دوخت "
                               "تمیز؛ مناسب محیط کار و دورهمی.",
        "web_copy_fa": "مانتو پاییزی با پارچه کرپ نرم، فرم ایستاده و دوخت "
                       "تمیز؛ ترکیبی آراسته برای روزهای کاری.",
        "seo_keywords": ["مانتو پاییزی", "مانتو کرپ"],
        "rationale": "کلیدواژه فصل و جنس پارچه در متن و توضیح متا "
                     "پوشش داده شد",
    }
    payload.update(over)
    return payload


def _caption_payload(**over):
    payload = {
        "caption_fa": "کت و جلیقه پاییزی جدید رسید؛ گرم و راحت.",
        "hashtags": ["#پاییز", "#پوشاک"],
        "alt_text": "مدل با کت و جلیقه پاییزی در نور طبیعی",
    }
    payload.update(over)
    return payload


class _StubProvider(AiProvider):
    """Provider-neutral stub: echoes the request tone into the copy.

    Proves the engine depends on the M1 `AiProvider` boundary only —
    nothing in the engine imports or assumes the mock.
    """

    name = "stub"

    def __init__(self, payloads=None):
        self.calls = []
        self.payloads = dict(payloads or {})

    def generate(self, request):
        self.calls.append(request)
        tone = request.prompt_payload.get("tone", "?")
        parsed = self.payloads.get(request.schema_id) or {
            "caption_proposal.v1": {
                "caption_fa": f"کپشن با لحن {tone} برای این محصول",
                "hashtags": ["#پاییز"],
                "alt_text": f"تصویر محصول با لحن {tone}",
            },
            "telegram_announcement.v1": {
                "announcement_fa": f"اعلام کانال با لحن {tone}",
                "hashtags": ["#پاییز"],
                "cta_fa": "پیام دهید",
            },
            "seo_copy.v1": _seo_payload(),
        }[request.schema_id]
        raw = json.dumps(parsed, ensure_ascii=False)
        return AiResponse(text=raw, parsed=parsed,
                          usage={"prompt_tokens": 12,
                                 "completion_tokens": 12},
                          provider=self.name, model="stub-1",
                          finish_reason="stop", latency_ms=1)


_STUB_POLICY = {
    spec["task_type"]: RouteTarget("stub", "stub-1", spec["schema_id"],
                                  budget_usd=1.0)
    for spec in fc.CHANNELS.values()
}


# =========================================================================
# 1. CONTRACTS (strict, versioned, cap parity, fixture pin)
# =========================================================================


class ContractRegistryTests(unittest.TestCase):

    NEW_SCHEMAS = ("telegram_announcement.v1", "seo_copy.v1")

    def test_new_channels_are_registered_and_strict(self):
        for sid in self.NEW_SCHEMAS:
            self.assertIn(sid, AI_OUTPUT_SCHEMAS)
            schema = AI_OUTPUT_SCHEMAS[sid]
            self.assertIs(schema["additionalProperties"], False)
            self.assertEqual(schema["title"], sid)

    def test_telegram_cap_parity_with_publisher_contract(self):
        # the literal in ai_contracts mirrors D-073's MAX_TEXT_CHARS —
        # a drift here would let the model emit text the publisher
        # refuses, so parity is re-asserted from BOTH sides
        self.assertEqual(TG_MAX, 4096)
        self.assertEqual(fc.TELEGRAM_TEXT_MAX, TG_MAX)
        schema = AI_OUTPUT_SCHEMAS["telegram_announcement.v1"]
        self.assertEqual(
            schema["properties"]["announcement_fa"]["maxLength"], TG_MAX)

    def test_seo_meta_and_keyword_bounds(self):
        props = AI_OUTPUT_SCHEMAS["seo_copy.v1"]["properties"]
        self.assertEqual(props["meta_description_fa"]["minLength"], 50)
        self.assertEqual(props["meta_description_fa"]["maxLength"], 160)
        self.assertEqual(props["seo_keywords"]["minItems"], 1)
        self.assertEqual(props["seo_keywords"]["maxItems"], 15)

    def test_registry_matches_frozen_fixture(self):
        fixture = load_schemas_fixture(
            str(HERE / "fixtures" / "ai" / "schemas.json"))
        self.assertEqual(AI_OUTPUT_SCHEMAS, fixture,
                         "contract drift: shipped schemas differ from the "
                         "pinned fixture")

    def test_mock_provider_scripts_exist_for_every_new_channel(self):
        for sid in self.NEW_SCHEMAS:
            self.assertIn(sid, MockAiProvider.MOCK_OUTPUTS)
            v = validate_ai_output(sid, MockAiProvider.MOCK_OUTPUTS[sid])
            self.assertTrue(v["valid"], f"{sid} mock output: {v}")


# =========================================================================
# 2. TEMPLATE PARITY (D-067: template and contract travel together)
# =========================================================================


class TemplateParityTests(unittest.TestCase):

    def setUp(self):
        self.registry = TemplateRegistry(str(TEMPLATES))

    def test_every_channel_template_binds_its_registered_contract(self):
        for channel, spec in fc.CHANNELS.items():
            t = self.registry.get(spec["template_id"])
            self.assertEqual(t["schema_id"], spec["schema_id"],
                             f"{channel}: template/schema mismatch")
            self.assertEqual(t["version"], "v1.0.0")
            self.assertEqual(
                json.loads(json.dumps(t["response_contract"], sort_keys=True)),
                json.loads(json.dumps(AI_OUTPUT_SCHEMAS[spec["schema_id"]],
                                      sort_keys=True)),
                f"{channel}: template response_contract drifted from the "
                "registered contract")
            self.assertEqual(len(t["template_hash"]), 64)

    def test_policy_routes_the_template_schema_per_channel(self):
        for channel, spec in fc.CHANNELS.items():
            target = DEFAULT_ROUTING_POLICY[spec["task_type"]]
            self.assertEqual(target.schema_id, spec["schema_id"], channel)
            self.assertEqual(target.provider, "mock")

    def test_instagram_caption_reuses_the_approved_caption_channel(self):
        # G-6: one dispatch path per channel — no second caption contract
        self.assertTrue(issubclass(fc.FashionInstagramCaptionTask,
                                   CaptionTask))
        self.assertEqual(fc.FashionInstagramCaptionTask.task_type,
                         CaptionTask.task_type)
        self.assertEqual(fc.FashionInstagramCaptionTask.schema_id,
                         CaptionTask.schema_id)
        self.assertEqual(fc.CHANNELS["instagram_caption"]["schema_id"],
                         CaptionTask.schema_id)

    def test_prompts_embed_brief_facts_and_template_identity(self):
        prompts = _engine().preview_prompts(_brief())
        for channel, info in prompts.items():
            self.assertIn(_BRIEF["title"], info["prompt"], channel)
            self.assertIn(_BRIEF["fabric_type"], info["prompt"], channel)
            self.assertIn(_BRIEF["season"], info["prompt"], channel)
            self.assertIn(_BRIEF["notes"], info["prompt"], channel)
            self.assertEqual(info["template_id"], fc.CHANNELS[channel]
                             ["template_id"])
            self.assertEqual(len(info["template_hash"]), 64)

    def test_unknown_channel_is_refused(self):
        with self.assertRaises(fc.FashionInputError):
            _engine().task("instagram_story")

    def test_all_channel_tasks_subclass_the_task_base(self):
        from canonical.ai_tasks import AiTask
        for channel, spec in fc.CHANNELS.items():
            task = _engine().task(channel)
            self.assertIsInstance(task, AiTask, channel)
            self.assertEqual(task.schema_id, spec["schema_id"])


# =========================================================================
# 3. TONE PRESETS (deterministic config, never model-chosen)
# =========================================================================


class TonePresetTests(unittest.TestCase):

    def test_three_presets_and_default(self):
        self.assertEqual(sorted(fc.TONE_PRESETS),
                         ["casual", "luxury", "trendy"])
        self.assertEqual(fc.DEFAULT_TONE, "luxury")
        self.assertEqual(fc.FashionBrief(**_BRIEF).validated().tone,
                         "luxury")

    def test_tone_is_normalized(self):
        b = _brief(tone="  Luxury ")
        self.assertEqual(b.validated().tone, "luxury")
        self.assertEqual(b.tone_preset.slug, "luxury")

    def test_unknown_tone_refused_before_any_dispatch(self):
        provider = MockAiProvider()
        engine = fc.FashionCopywritingEngine(ModelRouter({"mock": provider}))
        with self.assertRaises(fc.FashionInputError):
            engine.generate_pack(_brief(tone="dramatic"))
        self.assertEqual(provider.calls, [])
        self.assertEqual(fc.FashionInputError.failure_class, "B")

    def test_invalid_brief_fields_are_class_b_refusals(self):
        for bad in ({"title": " "}, {"fabric_type": ""},
                    {"season": ""}, {"title": "ا" * 201},
                    {"notes": "x" * 2001}):
            with self.assertRaises(fc.FashionInputError, msg=str(bad)):
                _brief(**bad).validated()

    def test_tone_changes_the_rendered_prompt_deterministically(self):
        engine = _engine()
        prompts = {}
        for tone in ("luxury", "casual", "trendy"):
            info = engine.preview_prompts(_brief(tone=tone))[
                "instagram_caption"]
            prompts[tone] = info
            self.assertIn(fc.TONE_PRESETS[tone].label_fa, info["prompt"])
            self.assertIn(fc.TONE_PRESETS[tone].guidance_fa, info["prompt"])
            self.assertIn(f"کد لحن: {tone}", info["prompt"])
        texts = [p["prompt"] for p in prompts.values()]
        hashes = [p["template_hash"] for p in prompts.values()]
        self.assertEqual(len(set(texts)), 3, "tones must change the prompt")
        # template hash pins the TEMPLATE, not the context — identical
        self.assertEqual(len(set(hashes)), 1)

    def test_same_tone_is_byte_identical_across_engines(self):
        a = _engine().preview_prompts(_brief(tone="trendy"))
        b = _engine().preview_prompts(_brief(tone="trendy"))
        self.assertEqual(a, b)

    def test_tone_flows_to_the_provider_for_every_channel(self):
        # end-to-end through the M1 boundary: the tone reaches the model
        # request on all three channels, and returns in the copy
        for tone in ("luxury", "casual", "trendy"):
            provider = _StubProvider()
            engine = fc.FashionCopywritingEngine(
                ModelRouter({"stub": provider}, policy=_STUB_POLICY))
            pack = engine.generate_pack(_brief(tone=tone))
            self.assertTrue(pack.ok, [r.error for r in pack.reports.values()])
            self.assertEqual(len(provider.calls), 3)
            caption = pack.channel("instagram_caption")
            self.assertEqual(caption["caption_fa"],
                             f"کپشن با لحن {tone} برای این محصول")
            self.assertIn(tone, pack.channel("telegram_announcement")
                          ["announcement_fa"])
            self.assertIn(f"لحن {tone}", pack.channel("instagram_caption")
                          ["alt_text"])

    def test_entity_key_is_tone_independent_but_idempotency_tag_is_not(self):
        a = _entity(tone="luxury")
        b = _entity(tone="trendy")
        self.assertEqual(a.key, b.key)
        task = _engine().task("instagram_caption")
        ra = task._build_request(a)
        rb = task._build_request(b)
        self.assertNotEqual(ra.idempotency_tag, rb.idempotency_tag)
        self.assertIn("|trendy", rb.idempotency_tag)


# =========================================================================
# 4. CHANNEL OUTPUT + DIVERGENCE (AC-3 / AC-4 / AC-5 / D-073)
# =========================================================================


class SharedGuardTests(unittest.TestCase):
    """D-029/D-031/D-032: ONE vocabulary rule, no per-channel fork."""

    def test_all_three_channels_call_the_shared_guard(self):
        from unittest import mock
        with mock.patch("canonical.fashion_copy.check_hashtag_vocabulary",
                        return_value=[]) as guard:
            pack = _engine().generate_pack(_brief())
            self.assertTrue(pack.ok, [r.error
                                      for r in pack.reports.values()])
        self.assertEqual(guard.call_count, 3)
        self.assertEqual(sorted(c.kwargs["channel"] for c in
                                guard.call_args_list),
                         sorted(fc.CHANNEL_ORDER))
        seo_call = [c for c in guard.call_args_list
                    if c.kwargs["channel"] == "seo_copy"][0]
        self.assertEqual(seo_call.kwargs["noun"], "keyword")

    def test_guard_is_the_same_function_object_as_the_caption_task(self):
        import canonical.ai_tasks as tasks
        self.assertIs(fc.check_hashtag_vocabulary,
                      tasks.check_hashtag_vocabulary)


class BriefIdentityTests(unittest.TestCase):
    """AC-3: the request key is deterministic (and product-scoped)."""

    def test_key_is_deterministic(self):
        self.assertEqual(_brief().key(), _brief().key())
        self.assertTrue(_brief().key().startswith("fashion/brief/"))
        self.assertIsInstance(_brief().entity(), TaskEntity)
        self.assertEqual(_brief().entity().kind, "fashion_item")

    def test_product_id_scopes_the_key(self):
        pid = "a1b2c3d4-1111-4222-a333-444444444444"
        scoped = _brief(product_id=pid)
        self.assertEqual(scoped.key(), f"fashion/{pid}/پاییز/کرپ/مانتو_پاییزی")
        self.assertNotEqual(scoped.key(), _brief().key())
        self.assertEqual(scoped.context()["product_id"], pid)
        self.assertNotIn("product_id", _brief().context())

    def test_product_id_is_bounded(self):
        for bad in ({"product_id": "p" * 65},
                    {"product_id": 123}):
            with self.assertRaises(fc.FashionInputError, msg=str(bad)):
                _brief(**bad).validated()


class ChannelOutputTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        self.prov, self.store, self.queue, self.life = \
            _make_stack(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    def _telegram(self, **over):
        return fc.FashionTelegramTask(
            _router({"telegram_announcement.v1": json.dumps(
                _tg_payload(**over), ensure_ascii=False)}),
            lifecycle=self.life)

    def _seo(self, **over):
        return fc.FashionSeoTask(
            _router({"seo_copy.v1": json.dumps(
                _seo_payload(**over), ensure_ascii=False)}),
            lifecycle=self.life)

    def _caption(self, **over):
        return fc.FashionInstagramCaptionTask(
            _router({"caption_proposal.v1": json.dumps(
                _caption_payload(**over), ensure_ascii=False)}),
            lifecycle=self.life)

    def test_all_channels_produce_contract_valid_copy(self):
        engine = fc.FashionCopywritingEngine(_router(), lifecycle=self.life)
        pack = engine.generate_pack(_brief(), mode="persist")
        self.assertTrue(pack.ok, {k: r.error
                                  for k, r in pack.reports.items()})
        for channel, report in pack.reports.items():
            spec = fc.CHANNELS[channel]
            v = validate_ai_output(spec["schema_id"],
                                   report.proposal.payload)
            self.assertTrue(v["valid"], f"{channel}: {v}")
            self.assertEqual(report.state, "PROPOSED")

    def test_dry_run_persists_nothing_but_still_calls_the_model(self):
        provider = MockAiProvider()
        engine = fc.FashionCopywritingEngine(
            ModelRouter({"mock": provider}), lifecycle=self.life)
        pack = engine.generate_pack(_brief())
        self.assertTrue(pack.ok)
        self.assertEqual(len(provider.calls), 3)
        self.assertEqual(self.prov.records, [])
        self.assertEqual(self.queue.load_pending(), [])
        self.assertEqual(list(self.store.records.values()), [])

    def test_telegram_render_matches_publisher_shape_and_cap(self):
        rep = self._telegram().run(_entity(), mode="dry-run")
        self.assertTrue(rep.ok, rep.divergences)
        payload = rep.proposal.payload
        rendered = fc.telegram_render(payload["announcement_fa"],
                                      payload["hashtags"],
                                      payload.get("cta_fa", ""))
        self.assertEqual(
            rendered,
            payload["announcement_fa"] + "\n\n" + payload["cta_fa"]
            + "\n\n" + " ".join(payload["hashtags"]))
        self.assertLessEqual(len(rendered), TG_MAX)

    def test_over_cap_telegram_is_class_b_and_not_persisted(self):
        rep = self._telegram(
            announcement_fa="ا" * 4000,
            cta_fa="ب" * 100).run(_entity(), mode="persist")
        self.assertFalse(rep.ok)
        self.assertEqual(rep.failure_class, "B")
        self.assertTrue(any("channel cap" in d for d in rep.divergences),
                        rep.divergences)
        self.assertEqual(self.prov.records, [])
        self.assertEqual(self.queue.load_pending(), [])


    def test_invented_price_and_link_are_class_b(self):
        rep = self._telegram(
            announcement_fa="مانتو پاییزی با قیمت ۲۵۰,۰۰۰ تومان رسید",
            cta_fa="سفارش از https://shop.example/mano").run(
                _entity(), mode="persist")
        self.assertFalse(rep.ok)
        self.assertEqual(rep.failure_class, "B")
        joined = " ".join(rep.divergences)
        self.assertIn("AC-4/AC-5", joined)
        self.assertIn("تومان", joined)
        self.assertIn("https://shop.example/mano", joined)
        self.assertEqual(self.prov.records, [])
        self.assertEqual(self.queue.load_pending(), [])

    def test_price_quoted_from_the_brief_is_allowed(self):
        # the seller stated the price — quoting is not invention
        rep = self._telegram(
            announcement_fa="مانتو پاییزی با قیمت ۲۵۰,۰۰۰ تومان رسید"
        ).run(_entity(notes="قیمت ۲۵۰,۰۰۰ تومان"), mode="dry-run")
        self.assertTrue(rep.ok, rep.divergences)

    def test_near_miss_hashtag_on_instagram_is_class_b(self):
        # 'مشکیه' is a near-miss of the approved color 'مشکی' — the
        # shared guard must fire on the fashion caption too
        rep = self._caption(hashtags=["#مشکیه"]).run(
            _entity(), mode="persist")
        self.assertFalse(rep.ok)
        self.assertEqual(rep.failure_class, "B")
        self.assertTrue(any("near-miss" in d for d in rep.divergences))
        self.assertEqual(self.queue.load_pending(), [])

    def test_seo_keyword_near_miss_is_class_b(self):
        rep = self._seo(seo_keywords=["مشکیه"]).run(
            _entity(), mode="persist")
        self.assertFalse(rep.ok)
        self.assertEqual(rep.failure_class, "B")
        self.assertTrue(any("keyword" in d and "near-miss" in d
                            for d in rep.divergences), rep.divergences)
        self.assertEqual(self.prov.records, [])

    def test_seo_invented_price_is_class_b(self):
        rep = self._seo(
            web_copy_fa="مانتو پاییزی کرپ با قیمت ۹۹۰,۰۰۰ تومان؛ "
                        "همین حالا سفارش دهید.").run(_entity(),
                                                    mode="dry-run")
        self.assertFalse(rep.ok)
        self.assertEqual(rep.failure_class, "B")
        self.assertTrue(any("AC-4/AC-5" in d for d in rep.divergences))

    def test_seo_meta_out_of_bounds_is_a_contract_failure(self):
        from canonical.ai_contracts import OutputValidationError
        for meta in ("مانتو پاییزی", "م" * 161):
            with self.assertRaises(OutputValidationError, msg=meta[:10]):
                self._seo(meta_description_fa=meta).run(
                    _entity(), mode="persist")
        self.assertEqual(self.queue.load_pending(), [])
        self.assertEqual(self.prov.records, [])

    def test_telegram_batch_covers_multiple_briefs(self):
        task = fc.FashionTelegramTask(_router(), lifecycle=self.life)
        entities = [_brief(title=f"مانتو پاییزی {i}").entity()
                    for i in range(3)]
        summary = task.run_batch(entities, mode="dry-run")
        self.assertEqual(summary["requested"], 3)
        self.assertEqual(summary["processed"], 3)
        self.assertEqual(summary["ok"], 3)
        self.assertEqual(summary["failed"], 0)
        self.assertIn("fashion_telegram_announcement",
                      summary["spend_by_task"])

    def test_caption_task_still_accepts_a_fashion_brief_entity(self):
        # the approved CaptionTask keeps working with a fashion payload
        # (no regression from sharing the vocabulary guard)
        rep = CaptionTask(_router()).run(_entity(), mode="dry-run")
        self.assertTrue(rep.ok, rep.error)


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

    def test_persist_lands_three_proposed_items(self):
        engine = fc.FashionCopywritingEngine(_router(), lifecycle=self.life)
        pack = engine.generate_pack(_brief(), mode="persist")
        self.assertTrue(pack.ok)
        self.assertEqual(len(pack.reports), 3)
        for channel, rep in pack.reports.items():
            self.assertEqual(rep.verdict, "new", channel)
            self.assertEqual(self.life.state_of(rep.proposal_id), PROPOSED)
        pending = self.queue.load_pending()
        self.assertEqual(len(pending), 3)
        self.assertEqual(len(self.prov.records), 3)
        codes = sorted(item["code"] for item in pending)
        self.assertEqual(codes, sorted(
            f"AI_{spec['task_type'].upper()}"
            for spec in fc.CHANNELS.values()))

    def test_repeat_persist_is_idempotent(self):
        engine = fc.FashionCopywritingEngine(_router(), lifecycle=self.life)
        first = engine.generate_pack(_brief(), mode="persist")
        self.assertTrue(first.ok)
        second = engine.generate_pack(_brief(), mode="persist")
        self.assertTrue(second.ok)
        for channel, rep in second.reports.items():
            self.assertEqual(rep.verdict, "skipped_duplicate", channel)
        self.assertEqual(len(self.queue.load_pending()), 3)
        self.assertEqual(len(self.prov.records), 3)

    def test_persist_without_a_lifecycle_fails_closed(self):
        # AiTask refuses to make AI output durable without the M2
        # round-trip — no silent side channel, no orphan proposal
        with self.assertRaises(RuntimeError) as ctx:
            _engine().generate("telegram_announcement", _brief(),
                               mode="persist")
        self.assertIn("ProposalLifecycle", str(ctx.exception))

    def test_pack_report_is_json_serializable(self):
        pack = _engine().generate_pack(_brief())
        blob = json.dumps(pack.to_dict(), ensure_ascii=False)
        self.assertIn("instagram_caption", blob)
        self.assertTrue(pack.to_dict()["ok"])
        self.assertEqual(pack.to_dict()["mode"], "dry-run")


# =========================================================================
# 6. AUTHORITY / HYGIENE: no network, no credentials, no publication edge
# =========================================================================


class AuthorityBoundaryTests(unittest.TestCase):

    FORBIDDEN_MODULES = {"requests", "urllib", "http", "socket",
                         "aiohttp", "httpx"}
    PUBLICATION_VERBS = ("publish", "approve", "accept", "decide",
                         "send", "post_")

    def test_no_network_import_surface(self):
        tree = ast.parse(FASHION_MODULE.read_text(encoding="utf-8"))
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
        source = FASHION_MODULE.read_text(encoding="utf-8")
        for token in ("os.environ", "getenv", "API_KEY", "api_key",
                      "Authorization", "Bearer"):
            self.assertNotIn(token, source)
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                self.assertNotEqual(node.attr, "environ")

    def test_no_publication_verb_in_the_engine_surface(self):
        tree = ast.parse(FASHION_MODULE.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                self.assertFalse(
                    node.name.startswith(self.PUBLICATION_VERBS),
                    f"publication surface leaked into the engine: "
                    f"{node.name}")
        for name in dir(fc.FashionCopywritingEngine):
            if name.startswith("__"):
                continue
            self.assertFalse(name.startswith(self.PUBLICATION_VERBS),
                             f"publication surface on the engine: {name}")

    def test_module_imports_only_approved_collaborators(self):
        tree = ast.parse(FASHION_MODULE.read_text(encoding="utf-8"))
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
            "canonical.telegram_contracts",
        })


# =========================================================================
# 7. PROVIDER NEUTRALITY (D-045: no provider is baked in)
# =========================================================================


class ProviderNeutralityTests(unittest.TestCase):

    def test_shipped_policy_is_offline_mock_only(self):
        for spec in fc.CHANNELS.values():
            target = DEFAULT_ROUTING_POLICY[spec["task_type"]]
            self.assertEqual(target.provider, "mock", spec["task_type"])

    def test_engine_runs_on_any_ai_provider(self):
        provider = _StubProvider()
        engine = fc.FashionCopywritingEngine(
            ModelRouter({"stub": provider}, policy=_STUB_POLICY))
        pack = engine.generate_pack(_brief())
        self.assertTrue(pack.ok, [r.error for r in pack.reports.values()])
        self.assertEqual(len(provider.calls), 3)
        self.assertEqual(pack.reports["seo_copy"].proposal.provider, "stub")
        self.assertEqual(pack.reports["seo_copy"].proposal.model, "stub-1")

    def test_provider_failure_maps_to_a_failed_report_not_a_crash(self):
        engine = fc.FashionCopywritingEngine(ModelRouter(
            {"mock": MockAiProvider(fail_with="timeout")}))
        rep = engine.generate("seo_copy", _brief())
        self.assertFalse(rep.ok)
        self.assertEqual(rep.failure_class, "A")
        self.assertIn("timeout", rep.error or "")

    def test_contract_violation_is_never_repaired(self):
        from canonical.ai_contracts import OutputValidationError
        provider = _StubProvider(payloads={"seo_copy.v1": {
            "meta_description_fa": "کوتاه",
            "web_copy_fa": "م" * 60,
            "seo_keywords": ["مانتو"],
            "rationale": "دلیل کافی برای این کار",
        }})
        engine = fc.FashionCopywritingEngine(
            ModelRouter({"stub": provider}, policy=_STUB_POLICY))
        with self.assertRaises(OutputValidationError):
            engine.generate("seo_copy", _brief())


if __name__ == "__main__":
    unittest.main()

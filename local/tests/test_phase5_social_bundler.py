"""Phase 5 §5.1 — Social bundler & HITL pipeline tests (D-172 / roadmap §5.1).

Contract under test: local/canonical/fashion_social_bundler.py

Layers:
  1. Contract: `social_bundle_proposal.v1` is strict, versioned, and
     refuses a payload that is not approval-gated.
  2. Brief identity: every Class-B input problem (media, slots, channel
     ids, aspect ratio, cross-brief mismatch) is refused BEFORE any
     dispatch, and `validated()` is idempotent and normalizing.
  3. Composition: §4.1 copy + §4.2 tags become ONE bundle — album vs
     single photo, CTA line, one tag set (the copy's own hashtags are
     not smuggled in), media order preserved.
  4. Determinism/idempotency: the bundle key is a pure function of the
     brief; persist-mode repeats land ONE PROPOSED proposal.
  5. Fail-closed: off-set hashtags, foreign links, invented prices and
     upstream channel failures refuse the bundle and persist nothing.
  6. Hand-off: ONLY an ACCEPTED bundle of the right schema, with an
     untampered payload that declares `approval.required`, and with at
     least one outbox, may be enqueued — and the enqueued payloads pass
     the canonical Telegram/Instagram contracts.
  7. No publication surface: AST-asserted (no network import, no
     credential/env access, no publish/send verb, no adapter import),
     and channel identity is taken from the ONE D-077 registry rather
     than re-typed (D-131 channel isolation stays clean).
  8. Review surface: `pending_bundles()` is durable, ordered and empties
     once a human decides.
"""

import ast
import copy
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

from canonical import fashion_social_bundler as fsb  # noqa: E402
from canonical.ai_proposal_lifecycle import (  # noqa: E402
    ACCEPTED, IN_REVIEW, PROPOSED, ProposalLifecycle, ProposalStateError)
from canonical.ai_runtime import (  # noqa: E402
    AiProposal, MockAiProvider, ModelRouter)
from canonical.fashion_copy import FashionBrief  # noqa: E402
from canonical.fashion_trends import TrendBrief  # noqa: E402
from canonical.instagram_contracts import (  # noqa: E402
    MAX_HASHTAGS as IG_HASHTAG_MAX,
    validate_publish_payload as validate_instagram)
from canonical.telegram_contracts import (  # noqa: E402
    validate_publish_payload as validate_telegram)
from canonical.verification_tool import VerificationQueue  # noqa: E402
from services.sync_engine import EventStore, ProvenanceEngine  # noqa: E402

MODULE = LOCAL / "canonical" / "fashion_social_bundler.py"
URL = "https://shop.example/p/man.to"
HASH_A = "a" * 16
HASH_B = "b" * 16


def _images(count: int = 2):
    return tuple(
        fsb.MediaItem(media_ref=f"media/store/{i + 1:02d}.jpg",
                      media_hash=HASH_A if i == 0 else f"{i:016d}",
                      file_size_bytes=120_000 + i)
        for i in range(count))


def _brief(**over):
    base = dict(
        copy=FashionBrief(title="مانتو پاییزی", fabric_type="کرپ",
                          season="پاییز", notes="فرم ایستاده و دوخت تمیز"),
        trends=TrendBrief(garment_category="مانتو", season="پاییز",
                          fabric_type="کرپ"),
        images=_images(),
        telegram_chat_id=-1001234567890,
        telegram_slot="2026-10-21T18:00Z",
        instagram_slot="2026-10-21T20:00Z",
        purchase_url=URL,
        include_link_in_text=True,
    )
    base.update(over)
    return fsb.SocialBundleBrief(**base)


def _router(responses=None, fail_with=None):
    return ModelRouter({"mock": MockAiProvider(responses, fail_with=fail_with)})


def _bundler(responses=None, lifecycle=None, fail_with=None):
    return fsb.FashionSocialBundler(_router(responses, fail_with=fail_with),
                                    lifecycle=lifecycle)


def _stack(tmp):
    prov = ProvenanceEngine(os.path.join(tmp, "prov.jsonl"))
    store = EventStore(os.path.join(tmp, "events.jsonl"))
    queue = VerificationQueue(os.path.join(tmp, "queue.json"))
    life = ProposalLifecycle(store, prov, queue=queue,
                             applier=lambda pid, ref: {"ok": True})
    return prov, store, queue, life


def _accepted(bundler, life, brief=None):
    """Bundle → submit_review → accept. Returns the persist report."""
    report = bundler.bundle(brief or _brief(), mode="persist")
    assert report.ok, report.errors
    life.decide(report.proposal_id, action="submit_review",
                reviewer="owner", notes="checked")
    life.decide(report.proposal_id, action="accept", reviewer="owner",
                notes="approved")
    return report


class _RecordingOutbox:
    """Outbox stub that records what it was handed (never sends)."""

    def __init__(self, validator):
        self.validator = validator
        self.items = []

    def enqueue(self, payload, *, actor="outbox"):
        norm = self.validator(payload)  # raises on a contract violation
        self.items.append({"actor": actor, "payload": norm})
        return {"queued": True, "publish_key": f"k{len(self.items)}",
                "payload": norm}


class _TamperingBundler(fsb.FashionSocialBundler):
    """Appends text AFTER composition to prove the bundler's own guards."""

    def __init__(self, router, *, extra_caption="", extra_text="", **kw):
        super().__init__(router, **kw)
        self.extra_caption = extra_caption
        self.extra_text = extra_text

    def _instagram_caption(self, copy, hashtags, brief):
        return super()._instagram_caption(copy, hashtags, brief) \
            + self.extra_caption

    def _telegram_text(self, copy, hashtags, brief):
        return super()._telegram_text(copy, hashtags, brief) + self.extra_text


class _StubLifecycle:
    """Minimal lifecycle stand-in for hand-off guard tests."""

    def __init__(self, state, ref):
        self._state = state
        self._ref = ref

    def state_of(self, bundle_id):
        if self._state is None:
            raise KeyError(bundle_id)
        return self._state

    def proposal_ref(self, bundle_id):
        return self._ref


# --- 1. contract --------------------------------------------------------------


class BundleContractTests(unittest.TestCase):
    def setUp(self):
        self.report = _bundler().bundle(_brief())
        self.assertTrue(self.report.ok, self.report.errors)
        self.payload = self.report.payload

    def test_contract_accepts_composed_payload(self):
        self.assertEqual(fsb.validate_bundle_payload(self.payload), [])

    def test_contract_is_registered_and_versioned(self):
        self.assertEqual(fsb.BUNDLE_SCHEMA, "social_bundle_proposal.v1")
        self.assertEqual(fsb.SOCIAL_BUNDLE_V1["title"], fsb.BUNDLE_SCHEMA)
        self.assertFalse(fsb.SOCIAL_BUNDLE_V1["additionalProperties"])

    def test_contract_refuses_missing_approval(self):
        bad = copy.deepcopy(self.payload)
        del bad["approval"]
        self.assertTrue(fsb.validate_bundle_payload(bad))

    def test_contract_refuses_approval_not_required(self):
        bad = copy.deepcopy(self.payload)
        bad["approval"]["required"] = False
        self.assertTrue(fsb.validate_bundle_payload(bad))

    def test_contract_refuses_non_proposed_state(self):
        bad = copy.deepcopy(self.payload)
        bad["approval"]["state"] = ACCEPTED
        self.assertTrue(fsb.validate_bundle_payload(bad))

    def test_contract_refuses_extra_property(self):
        bad = copy.deepcopy(self.payload)
        bad["auto_publish"] = True
        self.assertTrue(fsb.validate_bundle_payload(bad))

    def test_contract_refuses_hashtags_beyond_channel_cap(self):
        bad = copy.deepcopy(self.payload)
        bad["hashtags"] = [f"tag{i}" for i in range(IG_HASHTAG_MAX + 1)]
        self.assertTrue(fsb.validate_bundle_payload(bad))

    def test_contract_refuses_bad_bundle_key(self):
        bad = copy.deepcopy(self.payload)
        bad["bundle_key"] = "not-a-hash"
        self.assertTrue(fsb.validate_bundle_payload(bad))

    def test_contract_refuses_bad_aspect_ratio(self):
        bad = copy.deepcopy(self.payload)
        bad["instagram"]["aspect_ratio"] = "3:2"
        self.assertTrue(fsb.validate_bundle_payload(bad))

    def test_payload_hash_is_canonical(self):
        other = copy.deepcopy(self.payload)
        other["telegram"]["text"] = other["telegram"]["text"] + " "
        self.assertNotEqual(fsb.payload_hash(self.payload),
                            fsb.payload_hash(other))
        self.assertEqual(fsb.payload_hash(self.payload),
                         fsb.payload_hash(copy.deepcopy(self.payload)))


# --- 2. brief validation ------------------------------------------------------


class BriefValidationTests(unittest.TestCase):
    def _refuses(self, **over):
        with self.assertRaises(ValueError):
            _brief(**over).validated()

    def test_refuses_no_images(self):
        self._refuses(images=())

    def test_refuses_more_than_ten_images(self):
        self._refuses(images=_images(11))

    def test_accepts_ten_images(self):
        self.assertEqual(len(_brief(images=_images(10)).validated().images), 10)

    def test_refuses_blank_media_ref(self):
        self._refuses(images=(fsb.MediaItem(" ", HASH_A, 1000),))

    def test_refuses_short_media_hash(self):
        self._refuses(images=(fsb.MediaItem("media/x.jpg", "abc", 1000),))

    def test_refuses_unknown_media_type(self):
        self._refuses(images=(fsb.MediaItem("media/x.jpg", HASH_A, 1000,
                                            type="gif"),))

    def test_refuses_non_positive_size(self):
        self._refuses(images=(fsb.MediaItem("media/x.jpg", HASH_A, 0),))

    def test_refuses_zero_chat_id(self):
        self._refuses(telegram_chat_id=0)

    def test_refuses_bare_string_chat_id(self):
        self._refuses(telegram_chat_id="channel")

    def test_accepts_at_channel_and_negative_id(self):
        self.assertEqual(
            _brief(telegram_chat_id="@shop").validated().telegram_chat_id,
            "@shop")
        self.assertEqual(
            _brief(telegram_chat_id=-100123).validated().telegram_chat_id,
            -100123)

    def test_refuses_blank_slot(self):
        self._refuses(instagram_slot="   ")

    def test_refuses_overlong_slot(self):
        self._refuses(telegram_slot="x" * 65)

    def test_refuses_unknown_aspect_ratio(self):
        self._refuses(instagram_aspect_ratio="9:16")

    def test_refuses_non_http_purchase_url(self):
        self._refuses(purchase_url="shop.example/p/1")

    def test_refuses_cta_without_url(self):
        self._refuses(purchase_url="", include_link_in_text=True)

    def test_refuses_season_mismatch(self):
        self._refuses(trends=TrendBrief(garment_category="مانتو",
                                        season="زمستان", fabric_type="کرپ"))

    def test_refuses_fabric_mismatch(self):
        self._refuses(trends=TrendBrief(garment_category="مانتو",
                                        season="پاییز", fabric_type="پشم"))

    def test_refuses_product_id_mismatch(self):
        self._refuses(
            copy=FashionBrief(title="مانتو پاییزی", fabric_type="کرپ",
                              season="پاییز", product_id="aaaa1111-2222"),
            trends=TrendBrief(garment_category="مانتو", season="پاییز",
                              fabric_type="کرپ", product_id="bbbb3333-4444"))

    def test_refuses_overlong_content_id(self):
        self._refuses(content_id="c" * 81)

    def test_derives_content_id_when_absent(self):
        clean = _brief(content_id="").validated()
        self.assertTrue(clean.content_id.startswith("fashion-"))
        self.assertNotIn(" ", clean.content_id)

    def test_keeps_explicit_content_id(self):
        self.assertEqual(_brief(content_id="sku-42").validated().content_id,
                         "sku-42")

    def test_validation_is_idempotent_and_strips(self):
        clean = _brief(telegram_slot="  slot-1  ").validated()
        self.assertEqual(clean.telegram_slot, "slot-1")
        self.assertEqual(clean, clean.validated())

    def test_bundle_refuses_before_dispatch(self):
        provider = MockAiProvider()
        bundler = fsb.FashionSocialBundler(ModelRouter({"mock": provider}))
        with self.assertRaises(ValueError):
            bundler.bundle(_brief(images=()))
        self.assertEqual(provider.calls, [])


# --- 3. composition -----------------------------------------------------------


class CompositionTests(unittest.TestCase):
    def test_dry_run_succeeds_offline(self):
        report = _bundler().bundle(_brief())
        self.assertTrue(report.ok, report.errors)
        self.assertEqual(report.mode, "dry-run")
        self.assertIsNone(report.state)
        self.assertEqual(len(report.bundle_key), 32)

    def test_two_images_form_a_media_group(self):
        report = _bundler().bundle(_brief())
        self.assertEqual(report.payload["telegram"]["kind"], "mediagroup")
        self.assertEqual(len(report.payload["telegram"]["media"]), 2)

    def test_one_image_is_a_photo_post(self):
        report = _bundler().bundle(_brief(images=_images(1)))
        self.assertEqual(report.payload["telegram"]["kind"], "photo")

    def test_media_order_is_preserved(self):
        report = _bundler().bundle(_brief(images=_images(3)))
        refs = [m["media_ref"] for m in report.payload["telegram"]["media"]]
        self.assertEqual(refs, ["media/store/01.jpg", "media/store/02.jpg",
                                "media/store/03.jpg"])

    def test_caption_carries_cta_and_the_trend_tags(self):
        report = _bundler().bundle(_brief())
        caption = report.payload["instagram"]["caption"]
        self.assertIn(f"برای خرید: {URL}", caption)
        for tag in report.payload["hashtags"]:
            self.assertIn(f"#{tag}", caption)

    def test_telegram_text_carries_announcement_cta_link_tags(self):
        report = _bundler().bundle(_brief())
        text = report.payload["telegram"]["text"]
        self.assertIn("مانتو پاییزی جدید رسید", text)
        self.assertIn("برای سفارش و مشاوره سایز پیام دهید", text)
        self.assertIn(URL, text)
        self.assertIn("#مانتو", text)

    def test_caption_omits_link_when_not_requested(self):
        report = _bundler().bundle(_brief(include_link_in_text=False))
        self.assertNotIn(URL, report.payload["instagram"]["caption"])
        self.assertNotIn(URL, report.payload["telegram"]["text"])

    def test_one_tag_set_only(self):
        """The §4.1 caption's OWN hashtags never leak into the bundle."""
        report = _bundler().bundle(_brief())
        caption = report.payload["instagram"]["caption"]
        self.assertNotIn("#کت_جلیقه", caption)
        used = set(fsb._HASHTAG_RE.findall(caption))
        self.assertEqual(used, {f"#{t}" for t in report.payload["hashtags"]})

    def test_tag_order_follows_the_trend_proposal(self):
        report = _bundler().bundle(_brief())
        self.assertEqual(report.payload["hashtags"][0], "مانتو")
        self.assertEqual(report.payload["hashtags"][2], "پاییز")

    def test_source_provenance_names_both_engines(self):
        source = _bundler().bundle(_brief()).payload["source"]
        self.assertEqual(source["copy_schema"], "caption_proposal.v1")
        self.assertEqual(source["trend_schema"], "trend_hashtag_set.v1")
        self.assertEqual(source["copy_provider"], "mock")
        self.assertEqual(source["trend_provider"], "mock")

    def test_seo_block_is_carried_from_the_copy_pack(self):
        seo = _bundler().bundle(_brief()).payload["seo"]
        self.assertGreaterEqual(len(seo["meta_description_fa"]), 50)
        self.assertTrue(seo["seo_keywords"])

    def test_product_id_scopes_the_payload(self):
        pid = "a1b2c3d4-1111-4222-a333-444444444444"
        report = _bundler().bundle(_brief(
            copy=FashionBrief(title="مانتو پاییزی", fabric_type="کرپ",
                              season="پاییز", product_id=pid),
            trends=TrendBrief(garment_category="مانتو", season="پاییز",
                              fabric_type="کرپ", product_id=pid)))
        self.assertEqual(report.payload["product_id"], pid)


# --- 4. determinism and idempotency ------------------------------------------


class DeterminismTests(unittest.TestCase):
    def test_same_brief_same_key_and_payload(self):
        a = _bundler().bundle(_brief())
        b = _bundler().bundle(_brief())
        self.assertEqual(a.bundle_key, b.bundle_key)
        self.assertEqual(a.payload, b.payload)

    def test_media_change_changes_the_key(self):
        a = _bundler().bundle(_brief())
        b = _bundler().bundle(_brief(images=(
            fsb.MediaItem("media/store/01.jpg", HASH_B, 120_000),)))
        self.assertNotEqual(a.bundle_key, b.bundle_key)

    def test_slot_change_changes_the_key(self):
        a = _bundler().bundle(_brief())
        b = _bundler().bundle(_brief(instagram_slot="2026-10-22T20:00Z"))
        self.assertNotEqual(a.bundle_key, b.bundle_key)

    def test_url_change_changes_the_key(self):
        a = _bundler().bundle(_brief())
        b = _bundler().bundle(_brief(purchase_url=URL + "-v2"))
        self.assertNotEqual(a.bundle_key, b.bundle_key)

    def test_proposal_id_is_derived_from_the_key(self):
        report = _bundler().bundle(_brief())
        self.assertEqual(report.proposal_id,
                         f"social-bundle|{report.bundle_key}")

    def test_persist_repeat_lands_one_proposed_proposal(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, _, life = _stack(tmp)
            bundler = _bundler(lifecycle=life)
            first = bundler.bundle(_brief(), mode="persist")
            second = bundler.bundle(_brief(), mode="persist")
            self.assertTrue(first.ok and second.ok, first.errors + second.errors)
            self.assertEqual(first.proposal_id, second.proposal_id)
            self.assertEqual(life.state_of(first.proposal_id), PROPOSED)
            self.assertEqual(len(bundler.pending_bundles()), 1)
            self.assertEqual(len([i for i in life.pending_proposals()
                                  if i.get("proposal_id")
                                  == first.proposal_id]), 1)

    def test_dry_run_persists_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, queue, life = _stack(tmp)
            report = _bundler(lifecycle=life).bundle(_brief())
            self.assertTrue(report.ok)
            self.assertEqual(life.pending_proposals(), [])
            self.assertEqual(queue.load_pending(), [])

    def test_persist_requires_a_lifecycle(self):
        with self.assertRaises(fsb.SocialBundleError):
            _bundler().bundle(_brief(), mode="persist")

    def test_unknown_mode_is_refused(self):
        with self.assertRaises(fsb.SocialBundleError):
            _bundler().bundle(_brief(), mode="publish")


# --- 5. fail-closed composition ----------------------------------------------


class FailClosedTests(unittest.TestCase):
    def test_off_set_hashtag_is_refused(self):
        bundler = _TamperingBundler(_router(), extra_caption="\n\n#ترند_جدید")
        report = bundler.bundle(_brief())
        self.assertFalse(report.ok)
        self.assertTrue(any("not in the §4.2 trend set" in e
                            for e in report.errors), report.errors)

    def test_off_set_hashtag_in_telegram_is_refused(self):
        bundler = _TamperingBundler(_router(), extra_text="\n#کد_تخفیف")
        report = bundler.bundle(_brief())
        self.assertFalse(report.ok)

    def test_foreign_link_is_refused(self):
        bundler = _TamperingBundler(_router(),
                                    extra_caption="\nhttps://evil.example/x")
        report = bundler.bundle(_brief())
        self.assertFalse(report.ok)
        self.assertTrue(any("purchase_url" in e for e in report.errors),
                        report.errors)

    def test_invented_price_is_refused(self):
        bundler = _TamperingBundler(_router(), extra_caption="\nفقط ۹۹۰,۰۰۰ تومان")
        report = bundler.bundle(_brief())
        self.assertFalse(report.ok)
        self.assertTrue(any("canonical facts" in e for e in report.errors),
                        report.errors)

    def test_copy_channel_failure_is_refused(self):
        report = _bundler(fail_with="timeout").bundle(_brief())
        self.assertFalse(report.ok)
        self.assertIsNone(report.payload)

    def test_refusal_persists_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, _, life = _stack(tmp)
            bundler = _TamperingBundler(_router(), extra_caption="\n#غیرمرتبط",
                                       lifecycle=life)
            report = bundler.bundle(_brief(), mode="persist")
            self.assertFalse(report.ok)
            self.assertEqual(life.pending_proposals(), [])

    def test_composed_payload_is_always_approval_gated(self):
        payload = _bundler().bundle(_brief()).payload
        self.assertIs(payload["approval"]["required"], True)
        self.assertEqual(payload["approval"]["state"], PROPOSED)


# --- 6. hand-off --------------------------------------------------------------


class HandoffTests(unittest.TestCase):
    def test_unknown_bundle_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, _, life = _stack(tmp)
            bundler = _bundler(lifecycle=life)
            with self.assertRaises(fsb.BundleNotApproved):
                bundler.hand_off_to_outbox(
                    "social-bundle|deadbeef", lifecycle=life,
                    telegram_outbox=_RecordingOutbox(validate_telegram))

    def test_proposed_bundle_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, _, life = _stack(tmp)
            bundler = _bundler(lifecycle=life)
            report = bundler.bundle(_brief(), mode="persist")
            with self.assertRaises(fsb.BundleNotApproved) as ctx:
                bundler.hand_off_to_outbox(
                    report.proposal_id, lifecycle=life,
                    telegram_outbox=_RecordingOutbox(validate_telegram))
            self.assertEqual(ctx.exception.state, PROPOSED)

    def test_in_review_bundle_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, _, life = _stack(tmp)
            bundler = _bundler(lifecycle=life)
            report = bundler.bundle(_brief(), mode="persist")
            life.decide(report.proposal_id, action="submit_review",
                        reviewer="owner")
            with self.assertRaises(fsb.BundleNotApproved) as ctx:
                bundler.hand_off_to_outbox(
                    report.proposal_id, lifecycle=life,
                    instagram_outbox=_RecordingOutbox(validate_instagram))
            self.assertEqual(ctx.exception.state, IN_REVIEW)

    def test_rejected_bundle_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, _, life = _stack(tmp)
            bundler = _bundler(lifecycle=life)
            report = bundler.bundle(_brief(), mode="persist")
            life.decide(report.proposal_id, action="submit_review",
                        reviewer="owner")
            life.decide(report.proposal_id, action="reject", reviewer="owner")
            with self.assertRaises(fsb.BundleNotApproved):
                bundler.hand_off_to_outbox(
                    report.proposal_id, lifecycle=life,
                    telegram_outbox=_RecordingOutbox(validate_telegram))

    def test_no_outbox_is_a_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, _, life = _stack(tmp)
            bundler = _bundler(lifecycle=life)
            report = _accepted(bundler, life)
            with self.assertRaises(fsb.BundleNotApproved):
                bundler.hand_off_to_outbox(report.proposal_id, lifecycle=life)

    def test_accepted_bundle_reaches_both_outboxes(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, _, life = _stack(tmp)
            bundler = _bundler(lifecycle=life)
            report = _accepted(bundler, life)
            tg = _RecordingOutbox(validate_telegram)
            ig = _RecordingOutbox(validate_instagram)
            res = bundler.hand_off_to_outbox(
                report.proposal_id, lifecycle=life,
                telegram_outbox=tg, instagram_outbox=ig)
            self.assertEqual(res["state"], ACCEPTED)
            self.assertEqual(res["bundle_key"], report.bundle_key)
            self.assertEqual(sorted(res["queued"]), ["instagram", "telegram"])
            self.assertEqual(len(tg.items), 1)
            self.assertEqual(len(ig.items), 1)
            self.assertEqual(tg.items[0]["payload"]["chat_id"],
                             -1001234567890)
            self.assertEqual(tg.items[0]["payload"]["kind"], "mediagroup")
            self.assertEqual(
                ig.items[0]["payload"]["caption"],
                report.payload["instagram"]["caption"])

    def test_hand_off_queues_only_the_requested_channel(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, _, life = _stack(tmp)
            bundler = _bundler(lifecycle=life)
            report = _accepted(bundler, life)
            tg = _RecordingOutbox(validate_telegram)
            res = bundler.hand_off_to_outbox(
                report.proposal_id, lifecycle=life, telegram_outbox=tg)
            self.assertEqual(sorted(res["queued"]), ["telegram"])
            self.assertEqual(len(tg.items), 1)

    def test_tampered_payload_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, _, life = _stack(tmp)
            bundler = _bundler(lifecycle=life)
            report = _accepted(bundler, life)
            path = os.path.join(tmp, "events.jsonl")
            text = Path(path).read_text(encoding="utf-8")
            self.assertIn(URL, text)
            Path(path).write_text(text.replace(URL, URL + "-tampered"),
                                  encoding="utf-8")
            # a fresh store on the same path sees the edited bytes
            fresh = ProposalLifecycle(
                EventStore(path),
                ProvenanceEngine(os.path.join(tmp, "prov.jsonl")),
                applier=lambda pid, ref: {"ok": True})
            with self.assertRaises(fsb.BundleNotApproved) as ctx:
                bundler.hand_off_to_outbox(
                    report.proposal_id, lifecycle=fresh,
                    telegram_outbox=_RecordingOutbox(validate_telegram))
            self.assertIn("tampered", str(ctx.exception))

    def test_other_schema_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, _, life = _stack(tmp)
            bundler = _bundler(lifecycle=life)
            proposal = _proposal("caption_proposal.v1", {"caption_fa": "متن"})
            life.submit(proposal)
            life.decide(proposal.correlation_id, action="submit_review",
                        reviewer="owner")
            life.decide(proposal.correlation_id, action="accept",
                        reviewer="owner")
            with self.assertRaises(fsb.BundleNotApproved) as ctx:
                bundler.hand_off_to_outbox(
                    proposal.correlation_id, lifecycle=life,
                    telegram_outbox=_RecordingOutbox(validate_telegram))
            self.assertIn("not social_bundle_proposal.v1", str(ctx.exception))

    def test_payload_without_approval_flag_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, _, life = _stack(tmp)
            payload = _bundler().bundle(_brief()).payload
            payload["approval"] = {"required": False, "state": PROPOSED}
            proposal = _proposal(fsb.BUNDLE_SCHEMA, payload,
                                 cid="social-bundle|ungated")
            life.submit(proposal)
            life.decide(proposal.correlation_id, action="submit_review",
                        reviewer="owner")
            life.decide(proposal.correlation_id, action="accept",
                        reviewer="owner")
            bundler = _bundler(lifecycle=life)
            with self.assertRaises(fsb.BundleNotApproved) as ctx:
                bundler.hand_off_to_outbox(
                    proposal.correlation_id, lifecycle=life,
                    telegram_outbox=_RecordingOutbox(validate_telegram))
            self.assertIn("approval.required", str(ctx.exception))

    def test_stub_state_without_ref_is_refused(self):
        bundler = _bundler()
        with self.assertRaises(fsb.BundleNotApproved):
            bundler.hand_off_to_outbox(
                "social-bundle|x", lifecycle=_StubLifecycle(ACCEPTED, None),
                telegram_outbox=_RecordingOutbox(validate_telegram))

    def test_hand_off_never_calls_a_send_path(self):
        """The outbox stub has no send method — and none is attempted."""
        with tempfile.TemporaryDirectory() as tmp:
            _, _, _, life = _stack(tmp)
            bundler = _bundler(lifecycle=life)
            report = _accepted(bundler, life)
            tg = _RecordingOutbox(validate_telegram)
            bundler.hand_off_to_outbox(report.proposal_id, lifecycle=life,
                                       telegram_outbox=tg)
            self.assertFalse(hasattr(tg, "send"))
            self.assertFalse(hasattr(tg, "publish"))
            self.assertEqual(tg.items[0]["actor"], "social-bundler")


def _proposal(schema_id, payload, cid="test|proposal"):
    return AiProposal(
        schema_id=schema_id, task_type="fashion_social_bundle",
        payload=payload, provider="test", model="deterministic",
        usage={"prompt_tokens": 0, "completion_tokens": 0,
               "estimated_cost": 0.0},
        cost={"cost_usd": 0.0, "unknown_tariff": False},
        provenance_id=None, correlation_id=cid)


# --- 7. no publication surface ------------------------------------------------


class NoPublicationSurfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MODULE.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def test_no_network_imports(self):
        banned = {"socket", "requests", "urllib", "urllib3", "http",
                  "httpx", "aiohttp", "ssl", "ftplib", "smtplib"}
        for node in ast.walk(self.tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                self.assertNotIn(name.split(".")[0], banned, name)

    def test_no_adapter_or_publisher_import(self):
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                self.assertNotIn("publisher", node.module)
                self.assertNotIn("_adapter", node.module)
                self.assertNotIn("_live", node.module)

    def test_no_credential_or_environment_access(self):
        self.assertNotIn("os.environ", self.source)
        self.assertNotIn("getenv", self.source)
        self.assertNotIn("import os", self.source)

    def test_no_publish_or_send_verb(self):
        verbs = {"publish", "send", "dispatch", "post", "upload", "approve"}
        for node in ast.walk(self.tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.assertNotIn(node.name.lower(), verbs)

    def test_bundler_exposes_no_publish_attribute(self):
        bundler = _bundler()
        for name in ("publish", "send", "dispatch", "approve", "auto_publish"):
            self.assertFalse(hasattr(bundler, name), name)

    def test_channel_vocabulary_comes_from_the_one_registry(self):
        """D-131: channel identity is NOT re-typed in this module."""
        from canonical.orchestration_contracts import KNOWN_TARGETS
        self.assertEqual((fsb.INSTAGRAM, fsb.TELEGRAM), KNOWN_TARGETS)
        literals = [n.value.strip().lower() for n in ast.walk(self.tree)
                    if isinstance(n, ast.Constant)
                    and isinstance(n.value, str)]
        self.assertNotIn("instagram", literals)
        self.assertNotIn("telegram", literals)

    def test_channel_isolation_scan_is_clean(self):
        from canonical.security_worker import channel_isolation_scan
        rep = channel_isolation_scan([str(MODULE)])
        self.assertEqual(rep["findings"], [])
        self.assertTrue(rep["clean"])

    def test_hand_off_is_the_only_public_escape(self):
        public = {n for n in dir(fsb.FashionSocialBundler)
                  if not n.startswith("_")}
        self.assertEqual(public, {"bundle", "hand_off_to_outbox",
                                  "pending_bundles"})


# --- 8. review surface --------------------------------------------------------


class ReviewSurfaceTests(unittest.TestCase):
    def test_pending_bundles_is_orderable_and_durable(self):
        with tempfile.TemporaryDirectory() as tmp:
            prov, store, _, life = _stack(tmp)
            bundler = _bundler(lifecycle=life)
            early = bundler.bundle(_brief(), mode="persist")
            late = bundler.bundle(
                _brief(telegram_slot="2026-10-22T09:00Z"), mode="persist")
            rows = bundler.pending_bundles()
            self.assertEqual([r["proposal_id"] for r in rows],
                             [early.proposal_id, late.proposal_id])
            self.assertEqual(rows[0]["channels"], ["telegram", "instagram"])
            self.assertEqual(rows[0]["telegram_slot"], "2026-10-21T18:00Z")
            # a restart must not lose the queue
            fresh = ProposalLifecycle(store, prov)
            self.assertEqual(len(_bundler(lifecycle=fresh).pending_bundles()),
                             2)

    def test_pending_bundles_empties_after_a_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, _, life = _stack(tmp)
            bundler = _bundler(lifecycle=life)
            report = bundler.bundle(_brief(), mode="persist")
            life.decide(report.proposal_id, action="submit_review",
                        reviewer="owner")
            self.assertEqual(bundler.pending_bundles()[0]["state"], IN_REVIEW)
            life.decide(report.proposal_id, action="accept", reviewer="owner")
            self.assertEqual(bundler.pending_bundles(), [])

    def test_pending_bundles_ignores_foreign_proposals(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, _, life = _stack(tmp)
            life.submit(_proposal("caption_proposal.v1", {"caption_fa": "متن"}))
            self.assertEqual(_bundler(lifecycle=life).pending_bundles(), [])

    def test_pending_bundles_requires_a_lifecycle(self):
        with self.assertRaises(fsb.SocialBundleError):
            _bundler().pending_bundles()


if __name__ == "__main__":
    unittest.main()

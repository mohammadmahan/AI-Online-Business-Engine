"""Phase 5 §5.1 — Telegram inline keyboard contract & bundler seam (D-172).

Closes the named §5.1 gap: the buy button was a caption line because the
canonical Telegram payload had no keyboard field. This suite pins the new
`inline_keyboard` seam end to end, offline:

  1. Contract: URL-only rows, public http(s) domains, no userinfo/IP/
     localhost, no bot-token material, no credential-shaped query
     parameters, explicit row/button/text/URL bounds, and an optional
     `allowed_urls` pin so only the merchant's own purchase URL passes.
  2. Idempotency: the D-074 key EXTENDS with the keyboard digest only
     when a keyboard exists, so every pre-keyboard payload keeps its
     exact historical key.
  3. Bundler: a purchase URL yields BOTH the caption CTA (fallback) and
     the structured keyboard; no URL yields no keyboard; the artifact
     still validates against `social_bundle_proposal.v1`; HITL refuses
     a non-ACCEPTED release; repeated persists stay one PROPOSED item.
  4. Dispatch: photo/text carry `reply_markup`; an album (sendMediaGroup
     takes no keyboard in the Bot API) is followed by ONE CTA message
     with the same keyboard; legacy adapters keep working for
     button-less payloads.
"""

import os
import pathlib
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
LOCAL = HERE.parent
for p in (str(LOCAL), str(LOCAL / "canonical"), str(LOCAL / "services")):
    if p not in sys.path:
        sys.path.insert(0, p)

from canonical import fashion_social_bundler as fsb  # noqa: E402
from canonical.ai_proposal_lifecycle import (  # noqa: E402
    ProposalLifecycle)
from canonical.ai_runtime import MockAiProvider, ModelRouter  # noqa: E402
from canonical.fashion_copy import FashionBrief  # noqa: E402
from canonical.fashion_trends import TrendBrief  # noqa: E402
from canonical.telegram_adapter import MockTelegramAdapter  # noqa: E402
from canonical.telegram_contracts import (  # noqa: E402
    TelegramContractError, keyboard_hash, publish_idempotency_key,
    validate_button_url, validate_inline_keyboard,
    validate_publish_payload)
from canonical.telegram_publisher import TelegramOutboxPublisher  # noqa: E402
from canonical.verification_tool import VerificationQueue  # noqa: E402
from services.sync_engine import EventStore, ProvenanceEngine  # noqa: E402

URL = "https://shop.example/p/man.to"
HASH_A = "a" * 16


def _payload(**over):
    base = {
        "chat_id": "@myshop",
        "content_id": "POST-1",
        "kind": "photo",
        "parse_mode": "",
        "scheduled_slot": "2026-10-21T18:00Z",
        "media_ref": "media/store/01.jpg",
        "media_hash": HASH_A,
        "file_size_bytes": 120_000,
        "caption": "مانتو پاییزی",
    }
    base.update(over)
    return base


def _keyboard(label="خرید", url=URL):
    return [[{"text": label, "url": url}]]


def _images(count=2):
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


def _stack(tmp):
    prov = ProvenanceEngine(os.path.join(tmp, "prov.jsonl"))
    store = EventStore(os.path.join(tmp, "events.jsonl"))
    queue = VerificationQueue(os.path.join(tmp, "queue.json"))
    life = ProposalLifecycle(store, prov, queue=queue,
                             applier=lambda pid, ref: {"ok": True})
    return store, life


class _Outbox:
    def __init__(self):
        self.enqueued = []

    def enqueue(self, payload, *, actor="x"):
        self.enqueued.append(dict(payload))
        return {"queued": True, "publish_key": "k", "payload": dict(payload)}


# ===================================================================
# 1. Contract
# ===================================================================

class KeyboardContractTests(unittest.TestCase):

    def test_01_valid_keyboard_is_normalized(self):
        rows = validate_inline_keyboard([
            [{"text": "  خرید  ", "url": " " + URL + " "}],
            [{"text": "پشتیبانی", "url": "https://shop.example/help"}],
        ])
        self.assertEqual(rows, [
            [{"text": "خرید", "url": URL}],
            [{"text": "پشتیبانی", "url": "https://shop.example/help"}],
        ])

    def test_02_absent_or_empty_is_legal(self):
        for value in (None, [], ()):
            self.assertEqual(validate_inline_keyboard(value), [])

    def test_03_structural_refusals(self):
        cases = {
            "dict": {"a": 1},
            "empty row": [[]],
            "too many rows": [[{"text": "a", "url": URL}]] * 9,
            "too many per row": [[{"text": "a", "url": URL},
                                   {"text": "b", "url": URL},
                                   {"text": "c", "url": URL},
                                   {"text": "d", "url": URL}]],
            "button not dict": [["click"]],
            "callback_data": [[{"text": "a", "url": URL,
                                "callback_data": "x"}]],
            "empty text": [[{"text": "  ", "url": URL}]],
            "long text": [[{"text": "x" * 65, "url": URL}]],
            "control char": [[{"text": "a\x00b", "url": URL}]],
        }
        for name, value in cases.items():
            with self.subTest(name=name):
                with self.assertRaises(TelegramContractError):
                    validate_inline_keyboard(value)

    def test_04_url_scheme_and_shape_refusals(self):
        bad = (
            "javascript:alert(1)",
            "tg://resolve?domain=x",
            "mailto:shop@example.com",
            "/relative/path",
            "https://user:pass@shop.example/p",
            "https://127.0.0.1/p",
            "https://localhost/p",
            "https://shop/p",
            "https://shop.example/p ay",
            "https://shop.example/p\n?x=1",
            "https://shop.example:99999/p",
            "https://shop.example/" + "a" * 2100,
            "",
        )
        for url in bad:
            with self.subTest(url=url[:40]):
                with self.assertRaises(TelegramContractError):
                    validate_button_url(url)

    def test_05_token_and_credential_material_is_refused(self):
        bad = (
            "https://shop.example/p?token=abc",
            "https://shop.example/p?access_token=abc",
            "https://shop.example/p?api_key=abc",
            "https://shop.example/p?api_secret=abc",
            "https://shop.example/p?session_id=abc",
            "https://shop.example/p?next=1&signature=deadbeef",
            "https://shop.example/bot123456:ABCDEFGHIJKLMNOPQRSTUVWXYZ012345",
        )
        for url in bad:
            with self.subTest(url=url[:50]):
                with self.assertRaises(TelegramContractError):
                    validate_button_url(url)

    def test_06_ordinary_query_parameters_are_allowed(self):
        url = "https://shop.example/p/man.to?color=black&size=M"
        self.assertEqual(validate_button_url(url), url)

    def test_06b_outer_whitespace_is_trimmed_not_rejected(self):
        self.assertEqual(validate_button_url(f"  {URL}\n"), URL)

    def test_07_allowed_urls_pin_refuses_foreign_domains(self):
        self.assertEqual(validate_button_url(URL, allowed_urls={URL}), URL)
        with self.assertRaises(TelegramContractError):
            validate_button_url("https://evil.example/p",
                                allowed_urls={URL})

    def test_08_payload_carries_the_keyboard(self):
        norm = validate_publish_payload(_payload(inline_keyboard=_keyboard()))
        self.assertEqual(norm["inline_keyboard"], _keyboard())
        text = validate_publish_payload(_payload(
            kind="text", text="سلام", inline_keyboard=_keyboard()))
        self.assertEqual(text["inline_keyboard"], _keyboard())

    def test_09_payload_refuses_a_foreign_url_when_pinned(self):
        with self.assertRaises(TelegramContractError):
            validate_publish_payload(
                _payload(inline_keyboard=_keyboard(
                    url="https://evil.example/p")),
                allowed_urls={URL})

    def test_10_keyboard_hash_is_deterministic(self):
        a = keyboard_hash(_keyboard())
        b = keyboard_hash(_keyboard())
        c = keyboard_hash(_keyboard(label="سفارش"))
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)
        self.assertEqual(len(a), 64)

    def test_11_legacy_idempotency_key_is_unchanged(self):
        import hashlib
        legacy_material = "|".join(("@myshop", "POST-1", HASH_A,
                                    "h", "slot"))
        legacy = hashlib.sha256(
            legacy_material.encode("utf-8")).hexdigest()
        self.assertEqual(
            publish_idempotency_key("@myshop", "POST-1", HASH_A, "h",
                                    "slot"), legacy)
        self.assertEqual(
            publish_idempotency_key("@myshop", "POST-1", HASH_A, "h",
                                    "slot", ""), legacy)
        with_kb = publish_idempotency_key(
            "@myshop", "POST-1", HASH_A, "h", "slot",
            keyboard_hash(_keyboard()))
        self.assertNotEqual(with_kb, legacy)

    def test_12_payload_key_changes_only_when_the_keyboard_does(self):
        from canonical.telegram_contracts import key_from_payload
        plain = key_from_payload(_payload())
        again = key_from_payload(_payload())
        with_kb = key_from_payload(_payload(inline_keyboard=_keyboard()))
        other = key_from_payload(_payload(inline_keyboard=_keyboard(
            label="سفارش")))
        self.assertEqual(plain, again)
        self.assertNotEqual(plain, with_kb)
        self.assertNotEqual(with_kb, other)


# ===================================================================
# 2. Bundler generation + HITL
# ===================================================================

class BundlerKeyboardTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="tgkb-")
        self.addCleanup(lambda: __import__("shutil").rmtree(
            self.tmp, ignore_errors=True))
        self.store, self.lifecycle = _stack(self.tmp)
        router = ModelRouter({"mock": MockAiProvider()})
        self.bundler = fsb.FashionSocialBundler(router,
                                                lifecycle=self.lifecycle)

    def test_20_purchase_url_yields_both_caption_cta_and_keyboard(self):
        report = self.bundler.bundle(_brief(), mode="dry-run")
        self.assertTrue(report.ok, report.errors)
        tg = report.payload["telegram"]
        self.assertEqual(tg["inline_keyboard"], [[{
            "text": "برای سفارش و مشاوره سایز پیام دهید", "url": URL}]])
        # the fallback caption CTA line is still present
        self.assertIn(URL, tg["text"])
        # the artifact is still the strict §5.1 contract
        self.assertEqual(fsb.validate_bundle_payload(report.payload), [])

    def test_21_no_purchase_url_means_no_keyboard(self):
        report = self.bundler.bundle(
            _brief(purchase_url="", include_link_in_text=False),
            mode="dry-run")
        self.assertTrue(report.ok, report.errors)
        self.assertEqual(report.payload["telegram"]["inline_keyboard"], [])
        self.assertNotIn("برای خرید", report.payload["telegram"]["text"])

    def test_22_keyboard_is_deterministic_and_persist_is_idempotent(self):
        first = self.bundler.bundle(_brief(), mode="dry-run")
        second = self.bundler.bundle(_brief(), mode="dry-run")
        self.assertEqual(first.payload, second.payload)
        self.assertEqual(first.bundle_key, second.bundle_key)
        persisted = self.bundler.bundle(_brief(), mode="persist")
        again = self.bundler.bundle(_brief(), mode="persist")
        self.assertTrue(persisted.ok, persisted.errors)
        self.assertEqual(persisted.proposal_id, again.proposal_id)
        self.assertEqual(len(self.bundler.pending_bundles()), 1)

    def test_23_hand_off_carries_the_keyboard_after_acceptance(self):
        report = self.bundler.bundle(_brief(), mode="persist")
        self.assertTrue(report.ok, report.errors)
        with self.assertRaises(fsb.BundleNotApproved):
            self.bundler.hand_off_to_outbox(
                report.proposal_id, lifecycle=self.lifecycle,
                telegram_outbox=_Outbox())
        self.lifecycle.decide(report.proposal_id, action="submit_review",
                              reviewer="owner", notes="checked")
        self.lifecycle.decide(report.proposal_id, action="accept",
                              reviewer="owner", notes="approved")
        outbox = _Outbox()
        res = self.bundler.hand_off_to_outbox(
            report.proposal_id, lifecycle=self.lifecycle,
            telegram_outbox=outbox)
        self.assertEqual(
            outbox.enqueued[0]["inline_keyboard"],
            [[{"text": "برای سفارش و مشاوره سایز پیام دهید",
               "url": URL}]])
        self.assertEqual(res["state"], "ACCEPTED")

    def test_24_single_photo_and_album_both_carry_the_keyboard(self):
        single = self.bundler.bundle(_brief(images=_images(1)),
                                     mode="dry-run")
        album = self.bundler.bundle(_brief(), mode="dry-run")
        self.assertEqual(single.payload["telegram"]["kind"], "photo")
        self.assertEqual(album.payload["telegram"]["kind"], "mediagroup")
        self.assertEqual(len(single.payload["telegram"]["inline_keyboard"]),
                         1)
        self.assertEqual(len(album.payload["telegram"]["inline_keyboard"]),
                         1)


# ===================================================================
# 3. Dispatch through the canonical publisher
# ===================================================================

def _publisher(tmp):
    store = EventStore(os.path.join(tmp, "tg-events.json"))
    vault = os.path.join(tmp, "tg-vault.json")
    from canonical.telegram_publisher import _JsonVault
    return TelegramOutboxPublisher(store, _JsonVault(vault))


class PublisherKeyboardTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="tgpub-")
        self.addCleanup(lambda: __import__("shutil").rmtree(
            self.tmp, ignore_errors=True))

    def _enqueue(self, payload):
        pub = _publisher(self.tmp)
        queued = pub.enqueue(payload)
        return pub, queued

    def test_30_photo_carries_reply_markup(self):
        pub, queued = self._enqueue(_payload(inline_keyboard=_keyboard()))
        adapter = MockTelegramAdapter()
        res = pub.publish(queued["payload"], adapter)
        self.assertEqual(res["outcome"], "published")
        self.assertEqual(
            adapter.calls[0]["payload"]["reply_markup"],
            {"inline_keyboard": _keyboard()})

    def test_31_album_sends_album_then_one_cta_message(self):
        items = [{"type": "photo", "media_ref": f"media/{i}.jpg",
                  "file_size_bytes": 1000} for i in (1, 2)]
        pub, queued = self._enqueue(_payload(
            kind="mediagroup", items=items, inline_keyboard=_keyboard()))
        adapter = MockTelegramAdapter()
        res = pub.publish(queued["payload"], adapter)
        self.assertEqual(res["outcome"], "published")
        self.assertEqual([c["method"] for c in adapter.calls],
                         ["sendMediaGroup", "sendMessage"])
        self.assertNotIn("reply_markup", adapter.calls[0]["payload"])
        cta = adapter.calls[1]["payload"]
        self.assertEqual(cta["text"], "خرید")
        self.assertEqual(cta["reply_markup"]["inline_keyboard"],
                         _keyboard())

    def test_32_album_without_keyboard_is_one_call(self):
        items = [{"type": "photo", "media_ref": f"media/{i}.jpg",
                  "file_size_bytes": 1000} for i in (1, 2)]
        pub, queued = self._enqueue(_payload(kind="mediagroup", items=items))
        adapter = MockTelegramAdapter()
        pub.publish(queued["payload"], adapter)
        self.assertEqual([c["method"] for c in adapter.calls],
                         ["sendMediaGroup"])

    def test_33_legacy_adapter_only_sees_buttonless_payloads(self):
        class LegacyAdapter:
            def __init__(self):
                self.calls = []

            def send_text(self, chat_id, text, parse_mode=""):
                self.calls.append((chat_id, text, parse_mode))
                return {"message_id": 1}

        pub, queued = self._enqueue(_payload(kind="text", text="سلام"))
        adapter = LegacyAdapter()
        res = pub.publish(queued["payload"], adapter)
        self.assertEqual(res["outcome"], "published")
        self.assertEqual(len(adapter.calls), 1)

    def test_34_keyboard_changes_the_idempotency_key(self):
        pub_a, plain = self._enqueue(_payload())
        pub_b, with_kb = self._enqueue(_payload(
            inline_keyboard=_keyboard()))
        self.assertNotEqual(plain["publish_key"], with_kb["publish_key"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

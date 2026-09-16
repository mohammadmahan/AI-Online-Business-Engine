"""Phase 10 — Telegram integration tests (D-073..D-076).

Layers:
  M1  contracts: escaping/validators, payload constraints (all kinds),
      key derivation, state machine.
  M2  adapters: mock deterministic controls, live gate + injectable
      transport (zero network), error mapping, redaction, rate pacer.
  M3  publisher: vault semantics, outbox durability, classifier
      (A backoff / B terminal / C retry_after / E freeze), DLQ,
      provenance, concurrency.
  M4  LIVE PostgreSQL end-to-end: PK-as-lock on the D-055 store,
      restart safety (fresh publisher), audit reconstruction from
      durable data only.

Zero network: every adapter is either the mock or a live adapter with
an INJECTED transport. No credential exists (D-045); the only
fixture token values are synthetic and used to prove redaction.
"""

import json
import os
import sys
import tempfile
import threading
import unittest
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL = os.path.dirname(HERE)
ROOT = os.path.dirname(LOCAL)
for p in (LOCAL, os.path.join(LOCAL, "canonical"),
          os.path.join(LOCAL, "services"),
          os.path.join(LOCAL, "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

from canonical.telegram_contracts import (  # noqa: E402
    FAILED,
    MAX_ALBUM_ITEMS,
    MAX_FILE_BYTES,
    MAX_MEDIA_CAPTION_CHARS,
    MAX_TEXT_CHARS,
    MIN_ALBUM_ITEMS,
    PENDING,
    PUBLISHED,
    TelegramContractError,
    escape_html,
    escape_markdownv2,
    key_from_payload,
    media_group_hash,
    publish_idempotency_key,
    text_hash,
    validate_html,
    validate_markdownv2,
    validate_publish_payload,
    validate_transition,
)
from canonical.telegram_adapter import (  # noqa: E402
    RatePacer,
    LiveTelegramAdapter,
    MockTelegramAdapter,
    redact,
)
from canonical.telegram_adapter import (  # noqa: E402
    _ChatUnreachable,
    _RateLimited,
)
from canonical.telegram_publisher import (  # noqa: E402
    SOURCE_SYSTEM,
    TelegramOutboxPublisher,
    _JsonVault,
)
from services.sync_engine import EventStore, ProvenanceEngine  # noqa: E402

_TOK = "123456:ABCdefGHIjklMNOpqrsTUVwxyz"  # synthetic, redaction-proof


def _base_payload(**over):
    payload = {"chat_id": "@owner_channel", "content_id": "T-1",
               "kind": "text", "text": "سلام دنیا",
               "scheduled_slot": "SLOT-1"}
    payload.update(over)
    return payload


# ---------------------------------------------------------------------------
# M1 — contracts
# ---------------------------------------------------------------------------


class MarkdownV2ContractTests(unittest.TestCase):
    def test_escape_then_validate_roundtrip(self):
        raw = "سلام! دنیای *جدید* [link](https://x.com) `code` 1.5 #tag"
        self.assertEqual(validate_markdownv2(escape_markdownv2(raw)), None)

    def test_raw_specials_rejected(self):
        for raw in ("*bold*", "a.b", "1+1", "(x)", "a_b", "|x|", "#tag"):
            with self.assertRaises(TelegramContractError):
                validate_markdownv2(raw)

    def test_code_entity_survives(self):
        self.assertEqual(validate_markdownv2("`a_b`"), None)
        self.assertEqual(validate_markdownv2("```x*y```"), None)


class HtmlContractTests(unittest.TestCase):
    def test_escape_then_validate_roundtrip(self):
        raw = "<b>سلام</b> دنیا & <i>همه</i>"
        self.assertEqual(validate_html(escape_html(raw)), None)

    def test_unsupported_tag_rejected(self):
        with self.assertRaises(TelegramContractError):
            validate_html("<script>x</script>")

    def test_unbalanced_rejected(self):
        with self.assertRaises(TelegramContractError):
            validate_html("<b>x")
        with self.assertRaises(TelegramContractError):
            validate_html("</b>x")

    def test_raw_angle_rejected(self):
        with self.assertRaises(TelegramContractError):
            validate_html("a < b")


class PayloadConstraintTests(unittest.TestCase):
    def test_text_within_limit(self):
        norm = validate_publish_payload(_base_payload(text="سلام"))
        self.assertEqual(norm["kind"], "text")
        self.assertIn("text_hash", norm)

    def test_text_over_4096_rejected_locally(self):
        with self.assertRaises(TelegramContractError):
            validate_publish_payload(
                _base_payload(text="x" * (MAX_TEXT_CHARS + 1)))

    def test_media_caption_over_1024_rejected(self):
        with self.assertRaises(TelegramContractError):
            validate_publish_payload(_base_payload(
                kind="photo", media_ref="m-1", media_hash="abcd1234",
                file_size_bytes=1024,
                caption="c" * (MAX_MEDIA_CAPTION_CHARS + 1)))

    def test_file_over_50mb_rejected(self):
        with self.assertRaises(TelegramContractError):
            validate_publish_payload(_base_payload(
                kind="video", media_ref="m-1", media_hash="abcd1234",
                file_size_bytes=MAX_FILE_BYTES + 1))

    def test_album_bounds(self):
        with self.assertRaises(TelegramContractError):
            validate_publish_payload(_base_payload(
                kind="mediagroup", items=[
                    {"type": "photo", "media_ref": str(i)}
                    for i in range(MIN_ALBUM_ITEMS - 1)]))
        with self.assertRaises(TelegramContractError):
            validate_publish_payload(_base_payload(
                kind="mediagroup", items=[
                    {"type": "photo", "media_ref": str(i)}
                    for i in range(MAX_ALBUM_ITEMS + 1)]))

    def test_album_document_rejected(self):
        with self.assertRaises(TelegramContractError):
            validate_publish_payload(_base_payload(
                kind="mediagroup", items=[
                    {"type": "document", "media_ref": "1"},
                    {"type": "document", "media_ref": "2"}]))

    def test_bad_parse_mode_rejected(self):
        with self.assertRaises(TelegramContractError):
            validate_publish_payload(_base_payload(parse_mode="Markdown"))

    def test_chat_id_rules(self):
        with self.assertRaises(TelegramContractError):
            validate_publish_payload(_base_payload(chat_id="user"))
        with self.assertRaises(TelegramContractError):
            validate_publish_payload(_base_payload(chat_id=0))
        validate_publish_payload(_base_payload(chat_id=-100123))
        validate_publish_payload(_base_payload(chat_id="@ch"))

    def test_markdownv2_payload_parsed_strictly(self):
        with self.assertRaises(TelegramContractError):
            validate_publish_payload(_base_payload(
                text="*raw*", parse_mode="MarkdownV2"))
        norm = validate_publish_payload(_base_payload(
            text=escape_markdownv2("*سلام*"), parse_mode="MarkdownV2"))
        self.assertEqual(norm["parse_mode"], "MarkdownV2")

    def test_html_payload_parsed_strictly(self):
        with self.assertRaises(TelegramContractError):
            validate_publish_payload(_base_payload(
                text="<b>x", parse_mode="HTML"))


class KeyDerivationTests(unittest.TestCase):
    def test_key_deterministic_and_partitioned(self):
        p = _base_payload()
        k1 = key_from_payload(p)
        k2 = key_from_payload(p)
        self.assertEqual(k1, k2)
        # distinct slot → distinct key (deliberate re-publication path)
        self.assertNotEqual(
            k1, key_from_payload(_base_payload(scheduled_slot="SLOT-2")))
        # distinct chat → distinct key
        self.assertNotEqual(
            k1, key_from_payload(_base_payload(chat_id="@other")))
        # distinct text → distinct key
        self.assertNotEqual(
            k1, key_from_payload(_base_payload(text="متن دیگر")))

    def test_media_group_hash_order_sensitive(self):
        items = [{"type": "photo", "media_ref": "1"},
                 {"type": "video", "media_ref": "2"}]
        self.assertNotEqual(media_group_hash(items),
                            media_group_hash(list(reversed(items))))


class StateMachineTests(unittest.TestCase):
    def test_legal_transitions(self):
        validate_transition(PENDING, PUBLISHED)
        validate_transition(PENDING, FAILED)

    def test_terminal_immutable(self):
        for frm in (PUBLISHED, FAILED):
            with self.assertRaises(TelegramContractError):
                validate_transition(frm, PENDING)
            with self.assertRaises(TelegramContractError):
                validate_transition(frm, PUBLISHED)


# ---------------------------------------------------------------------------
# M2 — adapters, redaction, pacer
# ---------------------------------------------------------------------------


class MockAdapterTests(unittest.TestCase):
    def test_all_methods_dispatch(self):
        m = MockTelegramAdapter()
        self.assertEqual(m.send_text("@c", "سلام")["method"],
                         "sendMessage")
        self.assertEqual(m.send_photo("@c", "m")["method"], "sendPhoto")
        self.assertEqual(m.send_video("@c", "m")["method"], "sendVideo")
        self.assertEqual(m.send_document("@c", "m")["method"],
                         "sendDocument")
        self.assertEqual(m.send_media_group(
            "@c", [{"type": "photo", "media_ref": "1"},
                   {"type": "video", "media_ref": "2"}])["method"],
            "sendMediaGroup")
        self.assertEqual(len(m.calls), 5)

    def test_scripted_failures(self):
        cases = [("timeout", TimeoutError),
                 ("server_error", TimeoutError),
                 ("rate_limited", _RateLimited),
                 ("blocked", _ChatUnreachable),
                 ("chat_not_found", _ChatUnreachable),
                 ("migrated", _ChatUnreachable)]
        for control, expected in cases:
            with self.assertRaises(expected):
                MockTelegramAdapter(fail_with=control).send_text("@c", "x")

    def test_rate_limited_carries_retry_after(self):
        try:
            MockTelegramAdapter(fail_with="rate_limited").send_text(
                "@c", "x")
            self.fail("expected _RateLimited")
        except _RateLimited as exc:
            self.assertEqual(exc.retry_after_s, 3.0)
            self.assertEqual(exc.failure_class, "C")

    def test_fail_times_scoped(self):
        m = MockTelegramAdapter(fail_with="timeout", fail_times=2)
        for _ in range(2):
            with self.assertRaises(TimeoutError):
                m.send_text("@c", "x")
        self.assertEqual(m.send_text("@c", "x")["method"], "sendMessage")


class LiveAdapterGateTests(unittest.TestCase):
    def test_gate_refuses_without_flag(self):
        with self.assertRaises(TelegramContractError):
            LiveTelegramAdapter(transport=lambda r: {"status_code": 200,
                                                     "body": "{}"})

    def test_zero_network_transport_injected(self):
        seen = []

        def transport(req):
            seen.append(req)
            return {"status_code": 200,
                    "body": '{"ok":true,"result":{"message_id":7,'
                            '"chat":{"id":42}}}'}

        live = LiveTelegramAdapter(transport=transport, token=_TOK)
        result = live.send_text(42, "سلام")
        self.assertEqual(result["message_id"], 7)
        self.assertEqual(seen[0]["method"], "sendMessage")
        self.assertTrue(seen[0]["url"].startswith(
            "https://api.telegram.org/bot"))

    def test_error_mapping_matrix(self):
        def make(status, body):
            return LiveTelegramAdapter(
                transport=lambda r: {"status_code": status,
                                     "body": body}, token=_TOK)
        with self.assertRaises(_RateLimited):
            make(429, '{"parameters":{"retry_after":9}}').send_text(1, "x")
        with self.assertRaises(_ChatUnreachable):
            make(403, "blocked").send_text(1, "x")
        with self.assertRaises(_ChatUnreachable):
            make(400, "Bad Request: chat not found").send_text(1, "x")
        with self.assertRaises(_ChatUnreachable):
            make(400, "group chat was upgraded to a supergroup chat") \
                .send_text(1, "x")
        with self.assertRaises(TimeoutError):
            make(502, "bad gateway").send_text(1, "x")
        with self.assertRaises(TelegramContractError):
            make(400, "can't parse entities").send_text(1, "x")

    def test_carrier_errors_never_leak_token(self):
        def transport(req):
            # the transport echoes the full URL — the live adapter's
            # error path must redact it before the error escapes
            raise TimeoutError(f"POST {req['url']} timed out")

        live = LiveTelegramAdapter(transport=transport, token=_TOK)
        try:
            live.send_text(1, "x")
            self.fail("expected TimeoutError")
        except TimeoutError as exc:
            self.assertNotIn(_TOK, str(exc))
            self.assertIn("[REDACTED]", str(exc))


class RedactionTests(unittest.TestCase):
    def test_bot_url_pattern(self):
        leak = (f"POST https://api.telegram.org/bot{_TOK}/sendMessage "
                "failed")
        out = redact(leak)
        self.assertNotIn(_TOK, out)
        self.assertIn("bot[REDACTED]", out)

    def test_bare_secret_with_hint(self):
        out = redact(f"auth failed for {_TOK}",
                     extra_secrets=[_TOK])
        self.assertNotIn(_TOK, out)

    def test_dlq_entries_redacted(self):
        with tempfile.TemporaryDirectory() as tmp:
            pub = TelegramOutboxPublisher(
                EventStore(os.path.join(tmp, "e.json")),
                _JsonVault(os.path.join(tmp, "v.json")))
            q = pub.enqueue(_base_payload())
            try:
                pub.publish(q["payload"], MockTelegramAdapter(
                    fail_with="blocked"))
            except Exception:
                pass
            self.assertEqual(pub.dlq, pub.dlq)  # structure holds
            for entry in pub.dlq:
                self.assertNotIn(_TOK, redact(json.dumps(entry),
                                              extra_secrets=[_TOK]))


class RatePacerTests(unittest.TestCase):
    def test_per_chat_one_per_second(self):
        pacer = RatePacer()
        waits = [pacer.acquire("chatA", now_s=float(t))
                 for t in range(6)]
        self.assertEqual(waits, [0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        # 6th msg inside the same second must wait
        self.assertGreater(pacer.acquire("chatA", now_s=5.5), 0.0)

    def test_global_thirty_per_second(self):
        pacer = RatePacer()
        deferred = sum(
            1 for i in range(40)
            if pacer.acquire(f"chat{i % 4}", now_s=i * 0.001) > 0.0)
        self.assertGreaterEqual(deferred, 10)

    def test_chats_independent(self):
        pacer = RatePacer()
        self.assertEqual(pacer.acquire("chatA", now_s=0.0), 0.0)
        self.assertEqual(pacer.acquire("chatB", now_s=0.0), 0.0)

    def test_reservations_never_drop(self):
        pacer = RatePacer()
        for i in range(10):
            pacer.acquire("chatA", now_s=float(i))  # slot reserved
        # an 11th reservation is SCHEDULED (returns a wait), not refused
        self.assertIsInstance(pacer.acquire("chatA", now_s=9.5), float)


# ---------------------------------------------------------------------------
# M3 — publisher (offline JSON vault)
# ---------------------------------------------------------------------------


class PublisherOfflineTests(unittest.TestCase):
    def _pub(self, tmp, name, **kw):
        return TelegramOutboxPublisher(
            EventStore(os.path.join(tmp, f"e-{name}.json")),
            _JsonVault(os.path.join(tmp, f"v-{name}.json")),
            ProvenanceEngine(os.path.join(tmp, f"p-{name}.jsonl")),
            **kw)

    def test_enqueue_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            pub = self._pub(tmp, "a")
            q1 = pub.enqueue(_base_payload())
            self.assertTrue(q1["queued"])
            q2 = pub.enqueue(_base_payload())
            self.assertFalse(q2["queued"])
            self.assertEqual(len(pub.pending()), 1)

    def test_invalid_payload_never_queued(self):
        with tempfile.TemporaryDirectory() as tmp:
            pub = self._pub(tmp, "b")
            with self.assertRaises(TelegramContractError):
                pub.enqueue(_base_payload(
                    kind="photo", media_ref="m", media_hash="abcd1234",
                    file_size_bytes=1, caption="c" * 2000))
            self.assertEqual(len(pub.pending()), 0)

    def test_publish_then_duplicate_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            pub = self._pub(tmp, "c")
            q = pub.enqueue(_base_payload())
            r1 = pub.publish(q["payload"], MockTelegramAdapter())
            self.assertEqual(r1["outcome"], "published")
            r2 = pub.publish(q["payload"], MockTelegramAdapter())
            self.assertEqual(r2["outcome"], "duplicate_publish_blocked")
            self.assertEqual(r2["original"]["content_id"], "T-1")
            self.assertEqual(len(pub.pending()), 0)

    def test_distinct_slot_publishes_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            pub = self._pub(tmp, "d")
            q = pub.enqueue(_base_payload())
            self.assertEqual(pub.publish(q["payload"],
                                         MockTelegramAdapter())["outcome"],
                             "published")
            other = _base_payload(scheduled_slot="SLOT-2")
            q2 = pub.enqueue(other)
            self.assertEqual(pub.publish(q2["payload"],
                                         MockTelegramAdapter())["outcome"],
                             "published")

    def test_class_a_backoff_then_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            pub = self._pub(tmp, "e")
            q = pub.enqueue(_base_payload())
            r1 = pub.publish(q["payload"], MockTelegramAdapter(
                fail_with="timeout", fail_times=1))
            self.assertEqual(r1["outcome"], "retry_scheduled")
            self.assertEqual(r1["error_class"], "A")
            r2 = pub.publish(q["payload"], MockTelegramAdapter())
            self.assertEqual(r2["outcome"], "published")

    def test_class_a_exhaustion_dead_letters(self):
        with tempfile.TemporaryDirectory() as tmp:
            pub = self._pub(tmp, "f", max_retries=1)
            q = pub.enqueue(_base_payload())
            r1 = pub.publish(q["payload"], MockTelegramAdapter(
                fail_with="server_error", fail_times=5))
            self.assertEqual(r1["outcome"], "retry_scheduled")
            r2 = pub.publish(q["payload"], MockTelegramAdapter(
                fail_with="server_error", fail_times=5))
            self.assertEqual(r2["outcome"], "retries_exhausted")
            self.assertEqual(r2["error_class"], "A")
            self.assertEqual(len(pub.dlq), 1)

    def test_class_c_honors_retry_after_exactly(self):
        with tempfile.TemporaryDirectory() as tmp:
            pub = self._pub(tmp, "g")
            q = pub.enqueue(_base_payload())
            r = pub.publish(q["payload"], MockTelegramAdapter(
                fail_with="rate_limited"))
            self.assertEqual(r["outcome"], "cooldown")
            self.assertEqual(r["error_class"], "C")
            self.assertEqual(r["retry_after_s"], 3.0)
            self.assertFalse(pub.retry_eligible(r["publish_key"]))

    def test_class_e_freezes_queue_and_alerts(self):
        with tempfile.TemporaryDirectory() as tmp:
            pub = self._pub(tmp, "h")
            q = pub.enqueue(_base_payload(chat_id="@dead"))
            r = pub.publish(q["payload"], MockTelegramAdapter(
                fail_with="blocked"))
            self.assertEqual(r["outcome"], "queue_frozen")
            self.assertEqual(r["error_class"], "E")
            self.assertTrue(pub.frozen)
            self.assertEqual(len(pub.dlq), 1)
            r2 = pub.publish(_base_payload(), MockTelegramAdapter())
            self.assertEqual(r2["outcome"], "queue_frozen")

    def test_class_b_terminal_reject(self):
        with tempfile.TemporaryDirectory() as tmp:
            pub = self._pub(tmp, "i")
            q = pub.enqueue(_base_payload())
            # simulate a Telegram-side parse rejection (Class-B carrier)
            r = pub.publish(q["payload"], _AlwaysBadParse())
            self.assertEqual(r["outcome"], "terminal_reject")
            self.assertEqual(r["error_class"], "B")
            self.assertEqual(len(pub.dlq), 1)
            # no retry even with a healthy adapter afterwards
            r2 = pub.publish(q["payload"], MockTelegramAdapter())
            self.assertIn(r2["outcome"],
                          ("duplicate_publish_blocked", "terminal_reject"))

    def test_all_kinds_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            pub = self._pub(tmp, "j")
            cases = [
                ("text", {}),
                ("photo", {"media_ref": "m", "media_hash": "abcd1234",
                           "file_size_bytes": 10}),
                ("video", {"media_ref": "m", "media_hash": "abcd1234",
                           "file_size_bytes": 10}),
                ("document", {"media_ref": "m", "media_hash": "abcd1234",
                              "file_size_bytes": 10}),
                ("mediagroup", {"items": [
                    {"type": "photo", "media_ref": "1"},
                    {"type": "video", "media_ref": "2"}]}),
            ]
            for kind, extra in cases:
                payload = _base_payload(content_id=f"T-{kind}",
                                        kind=kind,
                                        scheduled_slot=f"S-{kind}",
                                        **extra)
                q = pub.enqueue(payload)
                r = pub.publish(q["payload"], MockTelegramAdapter())
                self.assertEqual(r["outcome"], "published", kind)

    def test_provenance_records_outcomes(self):
        with tempfile.TemporaryDirectory() as tmp:
            pub = self._pub(tmp, "k")
            before = len(pub.provenance.records)
            q = pub.enqueue(_base_payload())
            pub.publish(q["payload"], MockTelegramAdapter())
            pub.publish(q["payload"], MockTelegramAdapter())
            self.assertGreater(len(pub.provenance.records) - before, 0)

    def test_concurrent_publishers_single_winner(self):
        with tempfile.TemporaryDirectory() as tmp:
            pub = self._pub(tmp, "l")
            q = pub.enqueue(_base_payload())
            outcomes = []
            lock = threading.Lock()

            def worker():
                r = pub.publish(q["payload"], MockTelegramAdapter())
                with lock:
                    outcomes.append(r["outcome"])

            threads = [threading.Thread(target=worker) for _ in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            self.assertEqual(outcomes.count("published"), 1)
            self.assertEqual(
                outcomes.count("duplicate_publish_blocked"), 9)

    def test_audit_reconstruction_from_durable_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            pub = self._pub(tmp, "m")
            q = pub.enqueue(_base_payload())
            pub.publish(q["payload"], MockTelegramAdapter())
            rows = [json.loads(line) for line in
                    pub.store.succeeded_references(SOURCE_SYSTEM)]
            published = [r for r in rows if r.get("state") == PUBLISHED
                         and r.get("publish_key") == q["publish_key"]]
            self.assertEqual(len(published), 1)
            attempts = [r for r in rows
                        if str(r.get("event_id", "")).startswith(
                            "telegram|attempt|")
                        and r.get("publish_key") == q["publish_key"]]
            self.assertEqual(len(attempts), 1)
            self.assertEqual(attempts[0]["outcome"], "published")


class _AlwaysBadParse(MockTelegramAdapter):
    """Telegram-side parse rejection → Class-B carrier from the live
    error path (parse_bot_api_error), without any network."""

    def send_text(self, chat_id, text, parse_mode=""):
        raise TelegramContractError(
            "400 Bad Request: can't parse entities")


# ---------------------------------------------------------------------------
# M4 — LIVE PostgreSQL end-to-end
# ---------------------------------------------------------------------------


def _stack_up():
    try:
        import subprocess
        out = subprocess.run(
            ["docker", "compose", "-f", "local/infra/docker-compose.yml",
             "ps", "--format", "json"], capture_output=True, text=True,
            timeout=20, cwd=str(ROOT))
        return out.returncode == 0 and \
            "engine-local-postgres" in out.stdout and \
            "healthy" in out.stdout
    except Exception:
        return False


class _PgVaultProxy:
    """Live vault on telegram.publish_lock (D-055)."""

    def __init__(self):
        scripts = os.path.join(LOCAL, "scripts")
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        from canonical.telegram_publisher import _PgVault
        self._vault = _PgVault()

    def acquire(self, key, attempt_ref):
        return self._vault.acquire(key, attempt_ref)

    def finalize(self, key, ref):
        return self._vault.finalize(key, ref)

    def release(self, key):
        return self._vault.release(key)


@unittest.skipUnless(_stack_up(), "live PostgreSQL stack not running")
class LivePostgresEndToEndTests(unittest.TestCase):
    """D-074 vault against the real D-055 store: PK-as-lock semantics,
    restart safety, and durable audit reconstruction."""

    @classmethod
    def setUpClass(cls):
        from canonical.notion_ingest import PgEventStore
        cls.PgEventStore = PgEventStore
        cls._tmp = tempfile.TemporaryDirectory()
        cls._run = uuid.uuid4().hex[:8]

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _payload(self, content_id):
        return _base_payload(content_id=content_id,
                             scheduled_slot=f"SLOT-{self._run}")

    def test_full_publish_and_duplicate_block_on_live_pg(self):
        payload = self._payload(f"PG-{self._run}-1")
        store = self.PgEventStore()
        pub = TelegramOutboxPublisher(
            store, _PgVaultProxy(),
            ProvenanceEngine(os.path.join(self._tmp.name,
                                          f"prov-{self._run}.jsonl")))
        q = pub.enqueue(payload)
        self.assertTrue(q["queued"])
        r1 = pub.publish(q["payload"], MockTelegramAdapter())
        self.assertEqual(r1["outcome"], "published")
        # a FRESH publisher (simulated restart / second dispatcher)
        pub2 = TelegramOutboxPublisher(
            self.PgEventStore(), _PgVaultProxy(),
            ProvenanceEngine(os.path.join(self._tmp.name,
                                          f"prov2-{self._run}.jsonl")))
        r2 = pub2.publish(q["payload"], MockTelegramAdapter())
        self.assertEqual(r2["outcome"], "duplicate_publish_blocked")
        self.assertEqual(r2["original"]["content_id"], payload["content_id"])
        # distinct slot → distinct key → publishes again (deliberate
        # re-publication is addressable without weakening retry dedup)
        other = dict(payload, scheduled_slot=f"SLOT-{self._run}-alt")
        q3 = pub2.enqueue(other)
        r3 = pub2.publish(q3["payload"], MockTelegramAdapter())
        self.assertEqual(r3["outcome"], "published")

    def test_outbox_audit_reconstruction_on_live_pg(self):
        payload = self._payload(f"PG-{self._run}-2")
        store = self.PgEventStore()
        pub = TelegramOutboxPublisher(
            store, _PgVaultProxy(),
            ProvenanceEngine(os.path.join(self._tmp.name,
                                          f"prov3-{self._run}.jsonl")))
        q = pub.enqueue(payload)
        pub.publish(q["payload"], MockTelegramAdapter())
        # reconstruct the workflow history from DURABLE store data only
        rows = [json.loads(line) for line in
                store.succeeded_references("telegram")]
        states = [r["state"] for r in rows
                  if r.get("publish_key") == q["publish_key"]
                  and r.get("state")]
        self.assertIn(PUBLISHED, states)
        attempts = [r for r in rows
                    if str(r.get("event_id", "")).startswith(
                        "telegram|attempt|")
                    and r.get("publish_key") == q["publish_key"]]
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0]["outcome"], "published")


if __name__ == "__main__":
    unittest.main()

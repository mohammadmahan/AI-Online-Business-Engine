"""Phase 10 live wiring — Telegram ingress & egress composition tests.

Pins the live-wiring seam added in this batch (D-073..D-077 compose):

  - `canonical/telegram_ingress.py`: webhook secret-token verification
    (fail-closed env reference, constant-time compare, Telegram
    charset/length rules), bounded metadata-minimizing update parsing,
    at-least-once dedup with the long-poll offset contract, egress
    metadata redaction, and the outbound composition through the
    SHIPPED publisher pipeline (D-027/D-074/D-076).
  - `scripts/validate_telegram_live.py`: offline contract drill + the
    opt-in live getMe probe behind the D-075 gate (exit 2 when closed).

No network, no wall clock, no real credentials — all secrets are
drill-local fixture values.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "local" / "scripts" / "validate_telegram_live.py"

sys.path.insert(0, str(REPO / "local"))
sys.path.insert(0, str(SCRIPT.parent))

from canonical.telegram_adapter import (  # noqa: E402
    LIVE_ENV_FLAG, MockTelegramAdapter, RatePacer, redact,
)
from canonical.telegram_contracts import (  # noqa: E402
    TelegramContractError,
)
from canonical.telegram_ingress import (  # noqa: E402
    MAX_UPDATE_BYTES, TelegramIngress, TelegramIngressError,
    dispatch_outbound, parse_update, redact_chat_record,
    update_key, verify_webhook_secret_token, WEBHOOK_SECRET_ENV,
    WEBHOOK_SECRET_HEADER,
)
from canonical.telegram_publisher import (  # noqa: E402
    TelegramOutboxPublisher, _JsonVault,
)
from services.sync_engine import EventStore  # noqa: E402

SECRET = "battery-drill-Secret_1"


def _upd(uid=41, with_profile=True):
    msg = {"message_id": 7, "chat": {"id": -100200}, "text": "hello"}
    if with_profile:
        msg["from"] = {"id": 111, "first_name": "Leak",
                       "username": "leaky", "language_code": "en"}
    return {"update_id": uid, "message": msg}


def _ingress():
    seen, rec = set(), []

    def record(k):
        seen.add(k)
        rec.append(k)

    return TelegramIngress(seen_keys=lambda k: k in seen,
                           record_key=record), seen


def _publisher():
    tmp = tempfile.mkdtemp(prefix="tg-battery-")
    return TelegramOutboxPublisher(
        EventStore(path=os.path.join(tmp, "ev.json")),
        vault=_JsonVault(os.path.join(tmp, "vault.json")),
        pacer=RatePacer())


class TestWebhookSecret(unittest.TestCase):

    def test_round_trip(self):
        verify_webhook_secret_token(SECRET, secret=SECRET)

    def test_mismatch_rejected(self):
        with self.assertRaises(TelegramIngressError):
            verify_webhook_secret_token("other", secret=SECRET)

    def test_missing_header_rejected(self):
        for hdr in (None, ""):
            with self.assertRaises(TelegramIngressError):
                verify_webhook_secret_token(hdr, secret=SECRET)

    def test_telegram_charset_and_length_rules(self):
        # The HEADER value must match the configured secret; the charset
        # rule is enforced on the CONFIGURED reference (env path). A
        # passed-in secret of invalid shape is validated here too.
        for hdr, cfg in (("with.dot", "with.dot"), ("x" * 257, "x" * 257),
                         ("bad secret!", SECRET),
                         ("", SECRET), (None, SECRET)):
            with self.assertRaises(TelegramIngressError,
                                   msg=repr((hdr, cfg))):
                verify_webhook_secret_token(hdr, secret=cfg)
        # The env-reference path validates the configured secret itself.
        saved = os.environ.get(WEBHOOK_SECRET_ENV)
        os.environ[WEBHOOK_SECRET_ENV] = "invalid secret!"
        try:
            with self.assertRaises(TelegramIngressError):
                verify_webhook_secret_token("invalid secret!")
        finally:
            if saved is None:
                os.environ.pop(WEBHOOK_SECRET_ENV, None)
            else:
                os.environ[WEBHOOK_SECRET_ENV] = saved

    def test_fail_closed_without_env_reference(self):
        saved = os.environ.pop(WEBHOOK_SECRET_ENV, None)
        try:
            with self.assertRaises(TelegramIngressError):
                verify_webhook_secret_token(SECRET)  # no secret anywhere
        finally:
            if saved is not None:
                os.environ[WEBHOOK_SECRET_ENV] = saved

    def test_env_reference_resolved(self):
        saved = os.environ.get(WEBHOOK_SECRET_ENV)
        os.environ[WEBHOOK_SECRET_ENV] = SECRET
        try:
            verify_webhook_secret_token(SECRET)  # resolves from env
        finally:
            if saved is None:
                os.environ.pop(WEBHOOK_SECRET_ENV, None)
            else:
                os.environ[WEBHOOK_SECRET_ENV] = saved

    def test_documented_header_name(self):
        self.assertEqual(
            WEBHOOK_SECRET_HEADER, "x-telegram-bot-api-secret-token")


class TestUpdateParsing(unittest.TestCase):

    def test_minimal_surface_and_metadata_dropped(self):
        surface = parse_update(json.dumps(_upd()).encode())
        self.assertEqual(surface["update_id"], 41)
        self.assertEqual(surface["chat_id"], -100200)
        self.assertEqual(surface["user_id"], 111)
        self.assertEqual(surface["text"], "hello")
        blob = json.dumps(surface)
        for leaked in ("Leak", "leaky", "en"):
            self.assertNotIn(leaked, blob,
                             "profile metadata must never surface")

    def test_oversized_rejected(self):
        with self.assertRaises(TelegramIngressError):
            parse_update(b"x" * (MAX_UPDATE_BYTES + 1))

    def test_malformed_rejected(self):
        for body in (b"{nope", b"[1]", b'{"update_id": -1}',
                     b'{"update_id": true}', b'{"update_id": 1}',
                     b'{"update_id": "x"}'):
            with self.assertRaises(TelegramIngressError, msg=body):
                parse_update(body)

    def test_callback_query_surface(self):
        upd = {"update_id": 9, "callback_query": {
            "id": "cb", "from": {"id": 5, "username": "u"},
            "data": "do=thing"}}
        surface = parse_update(json.dumps(upd).encode())
        self.assertEqual(surface["kind"], "callback_query")
        self.assertEqual(surface["data"], "do=thing")
        self.assertNotIn("username", json.dumps(surface))

    def test_dedup_key_deterministic(self):
        self.assertEqual(update_key(parse_update(json.dumps(_upd()).encode())),
                         update_key(parse_update(json.dumps(_upd()).encode())))
        self.assertNotEqual(
            update_key(parse_update(json.dumps(_upd(42)).encode())),
            update_key(parse_update(json.dumps(_upd(43)).encode())))


class TestIngressService(unittest.TestCase):

    def test_accepted_then_skipped_and_offset(self):
        ing, _ = _ingress()
        raw = json.dumps(_upd()).encode()
        r1 = ing.ingest_webhook(raw, secret_header=SECRET, secret=SECRET)
        r2 = ing.ingest_webhook(raw, secret_header=SECRET, secret=SECRET)
        self.assertEqual(r1["verdict"], "accepted")
        self.assertEqual(r2["verdict"], "skipped_duplicate")
        self.assertEqual(ing.next_offset([r1]), 42)

    def test_webhook_rejects_bad_secret_before_parsing(self):
        ing, seen = _ingress()
        raw = json.dumps(_upd()).encode()
        before = len(seen)
        with self.assertRaises(TelegramIngressError):
            ing.ingest_webhook(raw, secret_header="wrong", secret=SECRET)
        self.assertEqual(len(seen), before,
                         "a rejected delivery must never be recorded")

    def test_long_poll_batch_and_empty_offset(self):
        ing, _ = _ingress()
        batch = [_upd(41), _upd(42, with_profile=False)]
        res = ing.ingest_long_poll(batch)
        self.assertEqual([r["verdict"] for r in res["results"]],
                         ["accepted", "accepted"])
        self.assertEqual(res["next_offset"], 43)
        empty = ing.ingest_long_poll([])
        self.assertEqual(empty["next_offset"], 0)


class TestEgressComposition(unittest.TestCase):

    def test_published_duplicate_blocked_invalid_rejected(self):
        pub = _publisher()
        adapter = MockTelegramAdapter()
        payload = {"chat_id": 12345, "content_id": "c-1", "kind": "text",
                   "scheduled_slot": "slot-0001",
                   "parse_mode": "MarkdownV2", "text": "hello \\- world"}
        r1 = dispatch_outbound(pub, payload, adapter)
        self.assertEqual((r1["stage"], r1["verdict"]),
                         ("publish", "published"))
        self.assertIsNotNone(r1.get("message_id"))
        r2 = dispatch_outbound(pub, payload, adapter)
        self.assertEqual((r2["stage"], r2["verdict"]),
                         ("enqueue", "blocked"))
        with self.assertRaises(TelegramContractError):
            dispatch_outbound(pub, {"chat_id": 12345,
                                    "content_id": "c-2", "kind": "text",
                                    "scheduled_slot": "slot-0002",
                                    "parse_mode": "MarkdownV2",
                                    "text": "_bold.x_ "}, adapter)

    def test_redact_chat_record_keeps_ids_drops_profiles(self):
        clean = redact_chat_record({"chat_id": 12345, "user_id": 111,
                                    "first_name": "Leak",
                                    "username": "leaky",
                                    "from": {"id": 111,
                                             "username": "leaky"}})
        blob = json.dumps(clean)
        self.assertNotIn("leaky", blob)
        self.assertNotIn("Leak", blob)
        self.assertEqual(clean["chat_id"], 12345)
        self.assertEqual(clean["user_id"], 111)
        self.assertEqual(clean["from"], {"id": 111})

    def test_token_redaction_still_active(self):
        token = "123456:ABC-DEF1234ghIkl-zyx57W2P1s"  # synthetic example — Telegram docs placeholder shape, never a real credential (D-045)
        self.assertIn("[REDACTED]",
                      redact(f"https://api.telegram.org/bot{token}/x"))


class TestValidateScript(unittest.TestCase):

    def test_offline_mode_green(self):
        proc = subprocess.run([sys.executable, str(SCRIPT)],
                              capture_output=True, text=True, cwd=str(REPO))
        self.assertEqual(proc.returncode, 0,
                         f"offline drill failed:\n{proc.stdout[-300:]}")
        self.assertIn("OFFLINE VERIFIED", proc.stdout)
        self.assertIn("skipped_duplicate", proc.stdout)

    def test_live_gate_closed_exits_2(self):
        env = {k: v for k, v in os.environ.items()
               if k not in (LIVE_ENV_FLAG, "TELEGRAM_BOT_TOKEN")}
        proc = subprocess.run([sys.executable, str(SCRIPT), "--live"],
                              capture_output=True, text=True, cwd=str(REPO),
                              env=env)
        self.assertEqual(proc.returncode, 2,
                         "closed gate must be exit 2, never a probe")
        self.assertIn("GATE", proc.stdout)

    def test_no_hardcoded_token_in_script(self):
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertNotRegex(
            text, r"bot\d+:[A-Za-z0-9_-]{20,}",
            "the script must never embed a bot-token literal")


if __name__ == "__main__":
    unittest.main()

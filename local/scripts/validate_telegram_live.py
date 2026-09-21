#!/usr/bin/env python3
"""validate_telegram_live.py — Phase 10 live wiring verification (D-073..D-077).

Two modes:

  OFFLINE (default)
    No connectivity, no credentials:
      1. Adapter gate contract — LiveTelegramAdapter refuses without
         TELEGRAM_LIVE_ENABLED/TELEGRAM_BOT_TOKEN (D-075/D-045,
         fail-closed), Mock adapter is the deterministic local path.
      2. Ingress drill — webhook secret verification (round-trip,
         mismatch, charset, fail-closed), bounded metadata-minimizing
         update parsing, at-least-once dedup (accepted →
         skipped_duplicate), long-poll offset contract.
      3. Egress drill — dispatch_outbound through the SHIPPED
         publisher (durable JSON store): published → duplicate
         blocked → invalid payload local Class-B.
      4. Environment/manifest requirements report — which env vars
         the live path requires (names only; values never read from
         files or printed).
    Exit 0 = contracts valid.

  LIVE (--live)
    Opt-in reachability probe against the REAL Telegram Bot API:
      - GATED: requires TELEGRAM_LIVE_ENABLED=true AND
        TELEGRAM_BOT_TOKEN in the environment (D-075/D-045). Without
        them the script REFUSES (exit 2) — it never falls back to a
        default token and never reads files for credentials.
      - Performs a single getMe round-trip through the injected
        transport (read-only; no messages sent), reporting the bot
        username; token material is redacted from any output.
    Exit 0 = reachable · 1 = API findings · 2 = gate closed/unreachable.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "local"))

from canonical.telegram_adapter import (  # noqa: E402
    LIVE_ENV_FLAG, MockTelegramAdapter, RatePacer, redact,
    require_live_keys, TelegramAdapter,
)
from canonical.telegram_contracts import TelegramContractError  # noqa: E402
from canonical.telegram_ingress import (  # noqa: E402
    MAX_UPDATE_BYTES, TelegramIngress, TelegramIngressError,
    dispatch_outbound, parse_update, redact_chat_record,
    verify_webhook_secret_token, WEBHOOK_SECRET_ENV,
)
from canonical.telegram_publisher import (  # noqa: E402
    TelegramOutboxPublisher, _JsonVault,
)
from services.sync_engine import EventStore  # noqa: E402

REQUIRED_LIVE_ENV = (LIVE_ENV_FLAG, "TELEGRAM_BOT_TOKEN")
OPTIONAL_ENV = (WEBHOOK_SECRET_ENV,)


def ok(msg: str) -> None:
    print(f"  [OK  ] {msg}")


def fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")
    sys.exit(1)


def _publisher(tmp: str) -> TelegramOutboxPublisher:
    return TelegramOutboxPublisher(
        EventStore(path=os.path.join(tmp, "ev.json")),
        vault=_JsonVault(os.path.join(tmp, "vault.json")),
        pacer=RatePacer())


def gate_contract() -> None:
    saved = {k: os.environ.get(k) for k in REQUIRED_LIVE_ENV}
    for k in REQUIRED_LIVE_ENV:
        os.environ.pop(k, None)
    try:
        require_live_keys()
        fail("live gate opened without flag+token — fail-open")
    except TelegramContractError:
        ok("adapter gate fail-closed without "
           "TELEGRAM_LIVE_ENABLED/TELEGRAM_BOT_TOKEN (D-075/D-045)")
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v
    # mock is the deterministic local path and works with zero creds
    adapter = MockTelegramAdapter()
    out = adapter.send_text(123, "hi")
    if out.get("message_id") is None:
        fail("mock adapter not deterministic")
    ok("deterministic mock adapter: local round-trip with zero "
       "credentials")


def ingress_drill() -> None:
    secret = "offline-drill-Secret_1"
    upd = {"update_id": 41, "message": {
        "message_id": 7, "chat": {"id": -100200},
        "from": {"id": 111, "username": "leaky", "first_name": "Leak"},
        "text": "hello", "photo": [{"file_id": "f"}]}}
    raw = json.dumps(upd).encode()

    verify_webhook_secret_token(secret, secret=secret)
    for hdr, sec in (("wrong", secret), (secret, "other")):
        try:
            verify_webhook_secret_token(hdr, secret=sec)
            fail("webhook secret mismatch accepted")
        except TelegramIngressError:
            pass
    for bad in (None, "", "bad secret!", "x" * 257):
        try:
            verify_webhook_secret_token(bad, secret=secret)
            fail(f"webhook secret {bad!r:.20} accepted")
        except TelegramIngressError:
            pass
    ok("webhook secret verification: round-trip, mismatch, charset, "
       "length all enforced")

    saved = os.environ.get(WEBHOOK_SECRET_ENV)
    os.environ.pop(WEBHOOK_SECRET_ENV, None)
    try:
        verify_webhook_secret_token(secret)  # no secret anywhere
        fail("ingress fail-open without env secret")
    except TelegramIngressError:
        ok(f"fail-closed: {WEBHOOK_SECRET_ENV} unset → ingress refuses")
    finally:
        if saved is not None:
            os.environ[WEBHOOK_SECRET_ENV] = saved

    surface = parse_update(raw)
    if surface["chat_id"] != -100200 or not surface["has_media"]:
        fail("update surface parsed incorrectly")
    blob = json.dumps(surface)
    if "leaky" in blob or "Leak" in blob:
        fail("profile metadata leaked into the delivery surface")
    try:
        parse_update(b"x" * (MAX_UPDATE_BYTES + 1))
        fail("oversized update accepted")
    except TelegramIngressError:
        pass
    ok("update parsing: bounded, metadata-minimizing "
       "(ids kept, names/usernames dropped)")

    seen, rec = set(), []

    def record(k):
        seen.add(k)
        rec.append(k)

    ing = TelegramIngress(seen_keys=lambda k: k in seen,
                          record_key=record)
    r1 = ing.ingest_webhook(raw, secret_header=secret, secret=secret)
    r2 = ing.ingest_webhook(raw, secret_header=secret, secret=secret)
    if r1["verdict"] != "accepted" or \
       r2["verdict"] != "skipped_duplicate":
        fail("ingress dedup broken")
    if ing.next_offset([r1]) != 42:
        fail("long-poll offset contract broken")
    try:
        ing.ingest_webhook(raw, secret_header="wrong", secret=secret)
        fail("webhook ingress accepted a bad secret")
    except TelegramIngressError:
        pass
    ok("ingress at-least-once: accepted → skipped_duplicate; offset "
       "= max(update_id)+1; bad secret rejected")


def egress_drill() -> None:
    import tempfile
    tmp = tempfile.mkdtemp(prefix="tg-drill-")
    pub = _publisher(tmp)
    adapter = MockTelegramAdapter()
    payload = {"chat_id": 12345, "content_id": "c-1", "kind": "text",
               "scheduled_slot": "slot-0001", "parse_mode": "MarkdownV2",
               "text": "hello \\- world"}
    r1 = dispatch_outbound(pub, payload, adapter)
    if r1["stage"] != "publish" or r1["verdict"] != "published":
        fail(f"outbound dispatch broken: {r1}")
    r2 = dispatch_outbound(pub, payload, adapter)
    if r2["stage"] != "enqueue" or r2["verdict"] != "blocked":
        fail(f"duplicate delivery not blocked: {r2}")
    try:
        # Raw MarkdownV2 specials must be escaped; `_bold_x_` leaves raw
        # dots inside bold — invalid per D-073 → local Class-B reject.
        dispatch_outbound(pub, {"chat_id": 12345, "content_id": "c-2",
                                "kind": "text",
                                "scheduled_slot": "slot-0002",
                                "parse_mode": "MarkdownV2",
                                "text": "_bold.x_ "}, adapter)
        fail("invalid payload accepted — local Class-B prevention broken")
    except TelegramContractError:
        pass
    # metadata hygiene on the egress side
    record = {"chat_id": 12345, "user_id": 111, "first_name": "Leak",
              "username": "leaky", "text": "hello"}
    clean = redact_chat_record(record)
    if "Leak" in json.dumps(clean) or "leaky" in json.dumps(clean):
        fail("redact_chat_record leaked profile metadata")
    if clean.get("chat_id") != 12345 or clean.get("user_id") != 111:
        fail("redact_chat_record dropped delivery ids")
    ok("egress: published → duplicate blocked → invalid payload "
       "local Class-B; metadata redaction keeps ids, drops profiles")

    # redaction of token material (shipped redact, verified here)
    token = "123456:ABC-DEF1234ghIkl-zyx57W2P1s"  # synthetic example — Telegram docs placeholder shape, never a real credential (D-045)
    if "[REDACTED]" not in redact(f"https://api.telegram.org/bot{token}/x"):
        fail("token redaction broken")
    ok("token redaction active for any log/observability surface")


def env_report() -> None:
    print("--- Environment requirements (names only; values never "
          "read from files) ---")
    for name, role in (
        (LIVE_ENV_FLAG, "live adapter enable flag (D-075)"),
        ("TELEGRAM_BOT_TOKEN", "bot token — live only (D-045)"),
        (WEBHOOK_SECRET_ENV, "webhook shared secret (ingress)"),
    ):
        state = "SET" if os.environ.get(name) else "unset"
        print(f"  {name:26s} [{state}] {role}")
    ok("fail-closed everywhere: every live path requires its env "
       "reference; nothing defaults")


def offline_mode() -> None:
    print("=== Telegram live wiring — OFFLINE contract verification ===")
    gate_contract()
    ingress_drill()
    egress_drill()
    env_report()
    print("=== OFFLINE VERIFIED (exit 0) ===")
    sys.exit(0)


def live_mode() -> None:
    print("=== Telegram LIVE probe (opt-in, read-only getMe) ===")
    try:
        require_live_keys()   # D-075/D-045 gate — raises if closed
    except TelegramContractError as exc:
        print(f"  [GATE] live probe unavailable: {exc}")
        print("=== CANNOT PROBE (exit 2) — set TELEGRAM_LIVE_ENABLED=true "
              "and TELEGRAM_BOT_TOKEN to authorize ===")
        sys.exit(2)
    token = os.environ["TELEGRAM_BOT_TOKEN"].strip()

    import urllib.error
    import urllib.request

    def transport(request: dict) -> dict:
        req = urllib.request.Request(
            request["url"],
            data=json.dumps(request.get("json") or {}).encode(),
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return {"status_code": resp.status,
                        "body": resp.read(65536).decode("utf-8", "replace")}
        except urllib.error.HTTPError as exc:
            return {"status_code": exc.code,
                    "body": exc.read(65536).decode("utf-8", "replace")}

    from canonical.telegram_adapter import LiveTelegramAdapter
    adapter = LiveTelegramAdapter(transport=transport)
    try:
        # getMe through the adapter's call path (read-only; no message)
        result = adapter._call("getMe", {})
    except Exception as exc:
        print(f"  [FAIL] getMe failed: {redact(str(exc), extra_secrets=[token])}")
        sys.exit(1)
    ok(f"Bot API reachable — bot username: {result.get('username')!r} "
       f"(id {result.get('id')}); no messages sent")
    print("=== LIVE VERIFIED (exit 0) — token material never printed ===")
    sys.exit(0)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--live", action="store_true",
                    help="opt-in live Bot API probe (requires the D-075 "
                         "env gate; read-only getMe)")
    args = ap.parse_args()
    live_mode() if args.live else offline_mode()


if __name__ == "__main__":
    main()

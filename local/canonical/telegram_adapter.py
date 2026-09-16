"""Phase 10 M2 — Telegram Bot API adapter boundary (D-075/D-074).

`TelegramAdapter` interface with pluggable transports (the D-066/D-071
pattern): zero network in tests. `MockTelegramAdapter` is a
deterministic, high-fidelity local implementation with scriptable
failures (429 + retry_after, migrate-to-supergroup, bot kicked/blocked,
chat not found, timeout, 5xx). `LiveTelegramAdapter` is gated behind
TELEGRAM_LIVE_ENABLED=true AND a bot token — otherwise deterministic
Class-B refusal (D-045: no credential exists, none requested).

Token redaction (D-075/D-045): `redact()` strips `bot<token>` URL
material from a string before it can reach logs, errors, or
observability records — the token lives in every Bot API URL
(`https://api.telegram.org/bot<token>/METHOD`).

Rate pacing (D-074): `RatePacer` enforces the Telegram limits
(global 30 msgs/sec, per-chat 1 msg/sec) with a deterministic sliding
window; the pacer schedules, it never drops.
"""

import json
import os
import time
from collections import deque
from typing import Callable, Dict, List, Optional

from canonical.telegram_contracts import (
    TelegramContractError,
    validate_publish_payload,
)

LIVE_ENV_FLAG = "TELEGRAM_LIVE_ENABLED"
TOKEN_ENV = "TELEGRAM_BOT_TOKEN"
API_BASE = "https://api.telegram.org"

_REDACTED = "[REDACTED]"


def redact(text: str, extra_secrets: Optional[List[str]] = None) -> str:
    """Strip bot-token material from any string (D-075/D-045).

    Handles the `bot<token>` URL form, the bare token value when the
    caller knows it (`extra_secrets`), and JSON bodies echoing it.
    Applies to logs, error messages, and observability records.
    """
    import re
    out = str(text)
    # bot<token> URL/path form: bot123456:ABC-DEF...
    out = re.sub(r"bot\d+:[A-Za-z0-9_-]{20,}", "bot" + _REDACTED, out)
    for secret in extra_secrets or []:
        if secret:
            out = out.replace(str(secret), _REDACTED)
    return out


def live_enabled() -> bool:
    return os.environ.get(LIVE_ENV_FLAG, "").strip().lower() == "true"


def require_live_keys() -> Dict[str, str]:
    """D-075 construction gate: flag AND token present, else Class-B."""
    if not live_enabled():
        raise TelegramContractError(
            f"live Telegram adapter disabled: {LIVE_ENV_FLAG}!=true "
            "(D-075 owner gate)")
    token = os.environ.get(TOKEN_ENV, "").strip()
    if not token:
        raise TelegramContractError(
            f"live Telegram adapter disabled: {TOKEN_ENV} missing "
            "(D-075 owner gate; D-045 — no credential exists)")
    return {"bot_token": token}


# --- error carriers (classified per D-076) ---------------------------------------

class _RateLimited(Exception):
    """Class-C carrier: 429 with Telegram's retry_after."""

    failure_class = "C"

    def __init__(self, message: str, retry_after_s: float = 1.0):
        super().__init__(message)
        self.retry_after_s = retry_after_s


class _ChatUnreachable(Exception):
    """Class-E carrier: bot blocked/kicked, token revoked, chat not
    found, chat migrated — freeze + HITL alert (D-076)."""

    failure_class = "E"


class ContainerNotReady(Exception):
    """Placeholder parity with the Phase 9 classifier imports (never
    raised by Telegram — the Bot API is synchronous)."""


def parse_bot_api_error(status_code: int, body: str) -> Exception:
    """Map a Bot API error response to its D-076 carrier (deterministic).

    429 → Class-C (retry_after honored); 403 → Class-E (blocked/kicked);
    400 with chat-not-found / migrated markers → Class-E; 400 with
    parse/markup markers → Class-B (TelegramContractError); 5xx →
    Class-A (transient); other 4xx → Class-B (terminal).
    """
    low = str(body).lower()
    if status_code == 429:
        retry_after = 1.0
        try:
            parsed = json.loads(body)
            params = parsed.get("parameters", {}) or {}
            retry_after = float(params.get("retry_after", 1.0))
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
        return _RateLimited(f"429 rate limited: {body}", retry_after)
    if status_code == 403:
        return _ChatUnreachable(f"403 forbidden (bot blocked/kicked): {body}")
    if status_code == 400 and ("chat not found" in low
                               or "migrated" in low
                               or "upgraded to a supergroup" in low):
        return _ChatUnreachable(f"400 chat unreachable: {body}")
    if status_code >= 500:
        return TimeoutError(f"{status_code} server error: {body}")
    if status_code == 400 and ("parse" in low or "markdown" in low
                               or "entities" in low or "can't parse" in low):
        return TelegramContractError(
            f"parse_mode rejected by Telegram: {body}")
    return TelegramContractError(f"{status_code} bad request: {body}")


# --- adapter interface ------------------------------------------------------------

class TelegramAdapter:
    """Provider-neutral Bot API boundary (RULES §35)."""

    def send_text(self, chat_id, text: str,
                  parse_mode: str = "") -> Dict:
        raise NotImplementedError

    def send_photo(self, chat_id, media_ref: str, caption: str = "",
                   parse_mode: str = "") -> Dict:
        raise NotImplementedError

    def send_video(self, chat_id, media_ref: str, caption: str = "",
                   parse_mode: str = "") -> Dict:
        raise NotImplementedError

    def send_document(self, chat_id, media_ref: str, caption: str = "",
                      parse_mode: str = "") -> Dict:
        raise NotImplementedError

    def send_media_group(self, chat_id, items: List[Dict],
                         caption: str = "",
                         parse_mode: str = "") -> Dict:
        raise NotImplementedError


FAILURE_CONTROLS = ("timeout", "rate_limited", "blocked", "chat_not_found",
                    "migrated", "server_error")


class MockTelegramAdapter(TelegramAdapter):
    """Deterministic local Bot API (D-053): records every dispatch,
    never touches a network. Scriptable failures via `fail_with` for
    the first `fail_times` calls."""

    def __init__(self, fail_with: Optional[str] = None,
                 fail_times: int = 1):
        if fail_with is not None and fail_with not in FAILURE_CONTROLS:
            raise TelegramContractError(
                f"unknown mock failure control {fail_with!r} — "
                f"expected {FAILURE_CONTROLS}")
        self.fail_with = fail_with
        self.fail_times = fail_times
        self.calls: List[Dict] = []
        self._n = 0

    def _maybe_fail(self, method: str) -> None:
        self._n += 1
        if self.fail_with and self._n <= self.fail_times:
            self._raise_scripted(self.fail_with, method)

    @staticmethod
    def _raise_scripted(control: str, method: str) -> None:
        if control == "timeout":
            raise TimeoutError(f"{method}: connection timeout (mock)")
        if control == "rate_limited":
            raise _RateLimited(
                '429: {"ok":false,"error_code":429,'
                '"description":"Too Many Requests: retry after 3",'
                '"parameters":{"retry_after":3}}', 3.0)
        if control == "blocked":
            raise _ChatUnreachable(
                f'403: {{"ok":false,"error_code":403,'
                f'"description":"Forbidden: bot was blocked by the user"}} '
                f"({method})")
        if control == "chat_not_found":
            raise _ChatUnreachable(
                f'400: {{"ok":false,"error_code":400,'
                f'"description":"Bad Request: chat not found"}} ({method})')
        if control == "migrated":
            raise _ChatUnreachable(
                f'400: {{"ok":false,"error_code":400,"description":'
                f'"Bad Request: group chat was upgraded to a supergroup '
                f'chat"}} ({method})')
        if control == "server_error":
            raise TimeoutError(f"{method}: 502 bad gateway (mock)")

    def _finish(self, method: str, chat_id, payload: Dict) -> Dict:
        self.calls.append({"method": method, "chat_id": chat_id,
                           "payload": payload})
        return {"message_id": 1000 + self._n,
                "chat_id": chat_id,
                "method": method}

    def send_text(self, chat_id, text: str, parse_mode: str = "") -> Dict:
        self._maybe_fail("sendMessage")
        return self._finish("sendMessage", chat_id,
                            {"text": text, "parse_mode": parse_mode})

    def send_photo(self, chat_id, media_ref: str, caption: str = "",
                   parse_mode: str = "") -> Dict:
        self._maybe_fail("sendPhoto")
        return self._finish("sendPhoto", chat_id,
                            {"photo": media_ref, "caption": caption,
                             "parse_mode": parse_mode})

    def send_video(self, chat_id, media_ref: str, caption: str = "",
                   parse_mode: str = "") -> Dict:
        self._maybe_fail("sendVideo")
        return self._finish("sendVideo", chat_id,
                            {"video": media_ref, "caption": caption,
                             "parse_mode": parse_mode})

    def send_document(self, chat_id, media_ref: str, caption: str = "",
                      parse_mode: str = "") -> Dict:
        self._maybe_fail("sendDocument")
        return self._finish("sendDocument", chat_id,
                            {"document": media_ref, "caption": caption,
                             "parse_mode": parse_mode})

    def send_media_group(self, chat_id, items: List[Dict],
                         caption: str = "",
                         parse_mode: str = "") -> Dict:
        self._maybe_fail("sendMediaGroup")
        return self._finish(
            "sendMediaGroup", chat_id,
            {"media": items, "caption": caption, "parse_mode": parse_mode})


class LiveTelegramAdapter(TelegramAdapter):
    """Real Bot API adapter (D-075): construction-gated, injectable
    transport, redacted errors. The transport receives
    {"method", "url", "json"} and returns {"status_code", "body"} —
    no network happens in tests because a transport is ALWAYS injected."""

    def __init__(self, transport: Optional[Callable[[Dict], Dict]] = None,
                 token: Optional[str] = None):
        gate = require_live_keys() if token is None else {"bot_token": token}
        if transport is None:
            raise TelegramContractError(
                "LiveTelegramAdapter requires an injected transport — "
                "direct HTTP is forbidden in this architecture (D-075)")
        self._token = gate["bot_token"]
        self._transport = transport

    def _call(self, method: str, json_body: Dict) -> Dict:
        request = {"method": method,
                   "url": f"{API_BASE}/bot{self._token}/{method}",
                   "json": json_body}
        try:
            response = self._transport(request)
        except TimeoutError as exc:
            raise TimeoutError(redact(str(exc),
                                      extra_secrets=[self._token]))
        except (ConnectionError, OSError) as exc:
            raise ConnectionError(redact(str(exc),
                                         extra_secrets=[self._token]))
        status = int(response.get("status_code", 0))
        body = str(response.get("body", ""))
        if status == 200:
            try:
                parsed = json.loads(body)
            except json.JSONDecodeError:
                return {"message_id": None, "chat_id": None}
            result = parsed.get("result", {})
            if isinstance(result, list):  # media group → list of messages
                return {"message_id": result[0].get("message_id"),
                        "chat_id": result[0].get("chat", {}).get("id"),
                        "message_count": len(result)}
            return {"message_id": result.get("message_id"),
                    "chat_id": result.get("chat", {}).get("id")}
        carrier = parse_bot_api_error(status, body)
        # redact token material from the carrier message before it escapes
        if hasattr(carrier, "args") and carrier.args:
            redacted = redact(str(carrier.args[0]),
                              extra_secrets=[self._token])
            carrier.args = (redacted,) + tuple(carrier.args[1:])
        raise carrier

    def send_text(self, chat_id, text: str, parse_mode: str = "") -> Dict:
        body = {"chat_id": chat_id, "text": text}
        if parse_mode:
            body["parse_mode"] = parse_mode
        return self._call("sendMessage", body)

    def send_photo(self, chat_id, media_ref: str, caption: str = "",
                   parse_mode: str = "") -> Dict:
        body: Dict = {"chat_id": chat_id, "photo": media_ref}
        if caption:
            body["caption"] = caption
        if parse_mode:
            body["parse_mode"] = parse_mode
        return self._call("sendPhoto", body)

    def send_video(self, chat_id, media_ref: str, caption: str = "",
                   parse_mode: str = "") -> Dict:
        body: Dict = {"chat_id": chat_id, "video": media_ref}
        if caption:
            body["caption"] = caption
        if parse_mode:
            body["parse_mode"] = parse_mode
        return self._call("sendVideo", body)

    def send_document(self, chat_id, media_ref: str, caption: str = "",
                      parse_mode: str = "") -> Dict:
        body: Dict = {"chat_id": chat_id, "document": media_ref}
        if caption:
            body["caption"] = caption
        if parse_mode:
            body["parse_mode"] = parse_mode
        return self._call("sendDocument", body)

    def send_media_group(self, chat_id, items: List[Dict],
                         caption: str = "",
                         parse_mode: str = "") -> Dict:
        body: Dict = {"chat_id": chat_id,
                      "media": json.dumps(items, ensure_ascii=False)}
        if caption:
            body["caption"] = caption
        if parse_mode:
            body["parse_mode"] = parse_mode
        return self._call("sendMediaGroup", body)


# --- rate pacer (D-074) ------------------------------------------------------------

GLOBAL_RATE_PER_SEC = 30
PER_CHAT_RATE_PER_SEC = 1


class RatePacer:
    """Telegram pacing engine (D-074): global 30 msgs/sec and
    per-chat 1 msg/sec via a deterministic sliding window.

    `acquire(chat_id, now_s)` returns the seconds the caller must wait
    before dispatch (0.0 = go now) and RESERVES the slot — the pacer
    schedules, it never drops. `now_s` is injectable for deterministic
    tests; a monotonic clock is the production default.
    """

    def __init__(self, global_rate: float = GLOBAL_RATE_PER_SEC,
                 per_chat_rate: float = PER_CHAT_RATE_PER_SEC):
        self.global_rate = float(global_rate)
        self.per_chat_rate = float(per_chat_rate)
        self._global: deque = deque()
        self._chats: Dict[str, deque] = {}

    def _reserve(self, window: deque, rate: float, now_s: float) -> float:
        horizon = now_s - 1.0
        while window and window[0] <= horizon:
            window.popleft()
        if len(window) >= rate:
            wait = window[0] + 1.0 - now_s
            window.append(now_s + max(wait, 0.0))
            return max(wait, 0.0)
        window.append(now_s)
        return 0.0

    def acquire(self, chat_id, now_s: Optional[float] = None) -> float:
        if now_s is None:
            now_s = time.monotonic()
        chat_key = str(chat_id)
        if chat_key not in self._chats:
            self._chats[chat_key] = deque()
        wait_chat = self._reserve(self._chats[chat_key],
                                  self.per_chat_rate, now_s)
        wait_global = self._reserve(self._global, self.global_rate, now_s)
        return max(wait_chat, wait_global)

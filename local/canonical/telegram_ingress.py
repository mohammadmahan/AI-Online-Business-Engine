"""Phase 10 live wiring — Telegram ingress & egress wiring (D-073..D-077).

The INGRESS half of Telegram live automation, composing with the
shipped egress stack (D-074 vault/pacer, D-075 gated adapter,
D-076 retry taxonomy) — pure and deterministic, no network, no wall
clock, no credentials:

  - `verify_webhook_secret_token` — Telegram's webhook shared-secret
    check: the value configured at webhook registration arrives in the
    `X-Telegram-Bot-Api-Secret-Token` header on every update delivery.
    Fail-closed: the secret resolves ONLY from the
    `TELEGRAM_WEBHOOK_SECRET` environment reference (D-045 — no
    default exists); constant-time compare; charset/length bounded
    per Telegram's documented secret_token rules (1–256 of
    [A-Za-z0-9_-]).
  - `parse_update` — bounded, strict update parsing with METADATA
    MINIMIZATION: returns the delivery-relevant surface only
    (update_id, kind, chat_id, user_id, text/caption/data, has_media)
    and DROPS profile metadata (first/last name, username, language)
    before anything can be logged or stored. Oversized or malformed
    updates are deterministic Class-B rejects.
  - `TelegramIngress` — at-least-once delivery handling: every update
    yields a deterministic dedup key (SHA256 over update_id); the
    injected seen-store/record pair (D-027 lineage, RULES §35) makes
    repeat deliveries `skipped_duplicate`, and the long-poll offset
    contract (`next_offset`) gives the exact `offset` parameter for
    the next `getUpdates` call — confirmed progress only.
  - `redact_chat_record` — egress-side metadata hygiene: strips
    profile fields from any record dict before logging/observability
    (ids are kept — delivery requires them; names/usernames never
    leave the process).
  - `dispatch_outbound` — the egress composition seam: local
    validation and the full D-074/D-076 pipeline are the shipped
    publisher's; this facade composes enqueue → publish under the
    injected adapter + pacer and returns the publisher's verdict.

Bot-token gating for any real API call lives in the shipped adapter
(`TELEGRAM_LIVE_ENABLED` + `TELEGRAM_BOT_TOKEN`, D-075) — this module
never touches the token.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Callable, Dict, List, Optional

from canonical.telegram_contracts import TelegramContractError

__all__ = [
    "MAX_UPDATE_BYTES", "WEBHOOK_SECRET_ENV", "WEBHOOK_SECRET_HEADER",
    "verify_webhook_secret_token", "parse_update", "update_key",
    "TelegramIngress", "redact_chat_record", "dispatch_outbound",
]

MAX_UPDATE_BYTES = 128 * 1024          # bounded ingress surface
WEBHOOK_SECRET_ENV = "TELEGRAM_WEBHOOK_SECRET"
WEBHOOK_SECRET_HEADER = "x-telegram-bot-api-secret-token"

_SECRET_RE = re.compile(r"^[A-Za-z0-9_-]{1,256}$")

_MESSAGE_LIKE = ("message", "edited_message", "channel_post",
                 "edited_channel_post")
_PROFILE_FIELDS = ("first_name", "last_name", "username", "language_code")


class TelegramIngressError(TelegramContractError):
    """Ingress contract violation (Class-B: terminal reject, no retry)."""


# --- webhook shared-secret verification (D-045 fail-closed) --------------

def _secret_from_env() -> str:
    secret = os.environ.get(WEBHOOK_SECRET_ENV, "").strip()
    if not secret:
        raise TelegramIngressError(
            f"webhook secret unavailable: {WEBHOOK_SECRET_ENV} is unset "
            "(D-045: credential refs resolve from the environment's "
            "secret store; no default exists)")
    if not _SECRET_RE.match(secret):
        raise TelegramIngressError(
            "webhook secret violates Telegram's documented charset/length "
            "(1–256 of [A-Za-z0-9_-])")
    return secret


def verify_webhook_secret_token(header_value: Optional[str],
                                secret: Optional[str] = None) -> None:
    """Verify the webhook secret-token header (constant-time).

    `header_value` must equal the configured shared secret exactly.
    The effective secret — passed in or resolved from the environment
    reference — is ALWAYS validated against Telegram's documented
    charset/length rules. Missing header, unset environment reference,
    charset violation, or mismatch raises TelegramIngressError. No
    default secret exists.
    """
    if not isinstance(header_value, str) or not header_value:
        raise TelegramIngressError("webhook secret-token header missing")
    secret_val = secret if secret is not None else _secret_from_env()
    if not _SECRET_RE.match(secret_val):
        raise TelegramIngressError(
            "webhook secret violates Telegram's documented charset/length "
            "(1–256 of [A-Za-z0-9_-])")
    if not hmac_compare(header_value, secret_val):
        raise TelegramIngressError(
            "webhook secret-token verification failed")


def hmac_compare(a: str, b: str) -> bool:
    """Constant-time string equality (length-safe)."""
    import hmac as _hmac
    return _hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


# --- update parsing (bounded, metadata-minimizing) ------------------------

def parse_update(body: bytes) -> Dict:
    """Parse a Telegram update into the minimal delivery surface.

    Contract: UTF-8 JSON object with an integer `update_id` ≥ 0 and at
    most one recognized content block (message-like, callback_query).
    Profile metadata (names, username, language) is DROPPED — ids and
    content only. Oversized/malformed/foreign updates are
    TelegramIngressError (Class-B).
    """
    if not isinstance(body, (bytes, bytearray)):
        raise TelegramIngressError("update body must be bytes")
    if len(body) > MAX_UPDATE_BYTES:
        raise TelegramIngressError(
            f"update exceeds {MAX_UPDATE_BYTES} bytes (got {len(body)})")
    try:
        obj = json.loads(bytes(body).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TelegramIngressError(f"update is not valid UTF-8 JSON: {exc}")
    if not isinstance(obj, dict):
        raise TelegramIngressError("update must be a JSON object")
    uid = obj.get("update_id")
    if not isinstance(uid, int) or isinstance(uid, bool) or uid < 0:
        raise TelegramIngressError("update_id must be a non-negative integer")

    out: Dict = {"update_id": uid, "kind": None, "chat_id": None,
                 "user_id": None, "text": "", "has_media": False,
                 "data": None}

    for kind in _MESSAGE_LIKE:
        msg = obj.get(kind)
        if isinstance(msg, dict):
            chat = msg.get("chat") or {}
            sender = msg.get("from") or {}
            text = msg.get("text") or msg.get("caption") or ""
            out.update({
                "kind": kind,
                "chat_id": chat.get("id"),
                "user_id": sender.get("id"),
                "text": text if isinstance(text, str) else "",
                "has_media": any(k in msg for k in
                                 ("photo", "video", "document", "animation")),
            })
            return out

    cb = obj.get("callback_query")
    if isinstance(cb, dict):
        out.update({"kind": "callback_query",
                    "user_id": (cb.get("from") or {}).get("id"),
                    "data": cb.get("data") if
                    isinstance(cb.get("data"), str) else None})
        return out

    raise TelegramIngressError(
        "update carries no recognized content block "
        "(message/edited_message/channel_post/edited_channel_post/"
        "callback_query)")


def update_key(update: Dict) -> str:
    """Deterministic dedup key for an at-least-once update delivery."""
    return hashlib.sha256(
        f"telegram|update|{update['update_id']}".encode("utf-8")).hexdigest()


# --- ingress service (injected stores, RULES §35) --------------------------

class TelegramIngress:
    """Webhook/long-poll ingress with at-least-once deduplication.

    `seen_keys`/`record_key` are injected (D-027 store or a parity
    dict — same seam as the n8n dispatcher). `next_offset` implements
    the long-poll offset contract: the NEXT call's `offset` is
    max(confirmed update_id) + 1, so Telegram never re-delivers
    confirmed updates while unconfirmed ones still arrive.
    """

    def __init__(self, seen_keys: Callable[[str], bool],
                 record_key: Callable[[str], None]) -> None:
        self._seen = seen_keys
        self._record = record_key

    def ingest_webhook(self, raw_body: bytes,
                       secret_header: Optional[str],
                       secret: Optional[str] = None) -> Dict:
        """Full webhook ingress: verify secret → parse → dedup."""
        verify_webhook_secret_token(secret_header, secret)
        return self._ingest_parsed(parse_update(raw_body))

    def ingest_long_poll(self, updates: List[Dict]) -> Dict:
        """Ingest a getUpdates batch (already-JSON updates)."""
        if not isinstance(updates, list):
            raise TelegramIngressError("getUpdates payload must be a list")
        results = [self._ingest_parsed(u) for u in updates]
        return {"results": results,
                "next_offset": self.next_offset(results)}

    def _ingest_parsed(self, update: Dict) -> Dict:
        key = update_key(update)
        if self._seen(key):
            return {"update_id": update["update_id"], "key": key,
                    "verdict": "skipped_duplicate"}
        self._record(key)
        return {"update_id": update["update_id"], "key": key,
                "verdict": "accepted", "surface": update}

    @staticmethod
    def next_offset(ingested: List[Dict]) -> int:
        """Long-poll offset: max(update_id) + 1 over THIS batch (0 when
        empty — Telegram treats offset=0 as 'no confirmation')."""
        ids = [r["update_id"] for r in ingested]
        return (max(ids) + 1) if ids else 0


# --- egress-side metadata hygiene -------------------------------------------

def redact_chat_record(record: Dict) -> Dict:
    """Return a copy of a record with profile metadata stripped.

    Ids (chat_id/user_id) survive — delivery and dedup need them;
    names/usernames/language never leave the process (D-045 zero-leak,
    D-114 lineage).
    """
    out = dict(record)
    for field in _PROFILE_FIELDS:
        out.pop(field, None)
    sender = out.get("from")
    if isinstance(sender, dict):
        clean = {k: v for k, v in sender.items()
                 if k not in _PROFILE_FIELDS}
        out["from"] = clean
    chat = out.get("chat")
    if isinstance(chat, dict):
        out["chat"] = {k: v for k, v in chat.items()
                       if k not in _PROFILE_FIELDS}
    return out


# --- egress composition seam -------------------------------------------------

def dispatch_outbound(publisher, payload: Dict, adapter,
                      *, actor: str = "telegram-live") -> Dict:
    """Compose one outbound delivery through the shipped pipeline.

    `publisher` is the TelegramOutboxPublisher (local validation, D-027
    durable outbox, D-074 vault, D-076 retry classification, D-074
    pacer — all shipped and battery-tested); `adapter` is the injected
    TelegramAdapter (Mock for deterministic runs, Live when the owner
    gate is open). Returns the publisher's verdict; the caller applies
    redact_chat_record to any record it logs.

    Verdict mapping (publisher shapes, verified): enqueue returns
    {queued, publish_key}; publish returns {outcome, publish_key,
    message_id} with outcome ∈ {published, blocked, retry, dead_letter,
    frozen} per D-076.
    """
    enq = publisher.enqueue(payload, actor=actor)
    key = enq.get("publish_key")
    if not enq.get("queued"):
        return {"stage": "enqueue", "verdict": "blocked", "key": key}
    pending = [r for r in publisher.pending()
               if r.get("publish_key") == key]
    if not pending:
        return {"stage": "pending", "verdict": "no_pending_ref",
                "key": key}
    res = publisher.publish(pending[0], adapter)
    return {"stage": "publish", "verdict": res.get("outcome"),
            "key": res.get("publish_key", key),
            "message_id": res.get("message_id")}

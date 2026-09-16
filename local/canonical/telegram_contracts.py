"""Phase 10 M1 — Telegram content & formatting contract (D-073).

Payload schemas for the Telegram Bot API (Text, Photo, Video,
Document, MediaGroup/album), strict local MarkdownV2/HTML escaping
and validation, and LOCAL pre-dispatch constraint enforcement.

Class-B local prevention (D-073): a payload that cannot be valid is
rejected before a single network call — validators are pure functions
with zero I/O. The Bot API is SYNCHRONOUS (no container polling), so
the state machine is minimal:

    PENDING → PUBLISHED | FAILED (terminal, immutable)

Contract constants (D-073): caption ≤ 1024 chars (media), text ≤ 4096
chars, album 2..10 items, file size ≤ 50 MB (Bot API limit),
parse_mode ∈ {None, "MarkdownV2", "HTML"}. Media is REFERENCED by id
from the media abstraction (D-051/D-049) — never embedded.
"""

import hashlib
import re
from typing import Dict, List, Optional, Tuple

# --- states -------------------------------------------------------------------

PENDING = "PENDING"
PUBLISHED = "PUBLISHED"
FAILED = "FAILED"

TERMINAL = (PUBLISHED, FAILED)

TRANSITIONS = {
    (PENDING, PUBLISHED),
    (PENDING, FAILED),
}

# --- contract constants (D-073) -------------------------------------------------

MAX_TEXT_CHARS = 4096
MAX_MEDIA_CAPTION_CHARS = 1024
MIN_ALBUM_ITEMS = 2
MAX_ALBUM_ITEMS = 10
MAX_FILE_BYTES = 50 * 1024 * 1024  # 50 MB Bot API upload limit

ALLOWED_PARSE_MODES = ("", "MarkdownV2", "HTML")
MEDIA_TYPES = ("photo", "video", "document")

PAYLOAD_KINDS = ("text", "photo", "video", "document", "mediagroup")


class TelegramContractError(ValueError):
    """Contract/state violation (Class-B, terminal reject, no retry)."""

    failure_class = "B"


def validate_transition(from_state: str, to_state: str) -> None:
    """Raise TelegramContractError on an unauthorized transition."""
    if (from_state, to_state) not in TRANSITIONS:
        raise TelegramContractError(
            f"unauthorized transition: {from_state} -> {to_state} "
            f"(D-073; legal: {sorted(TRANSITIONS)})")


# --- formatting: MarkdownV2 (D-073) ----------------------------------------------

# Telegram MarkdownV2 requires escaping ALL of these outside entities:
_MDV2_SPECIALS = "_*[]()~`>#+-=|{}.!"

_MDV2_ENTITY_RE = re.compile(
    "\\\\[*_\\[\\]()~`>#+\\-=|{}.!]"   # escaped special char
    "|```[^`]*```|`[^`\n]*`"             # code fence / inline code
    "|\\[[^\\]]*\\]\\([^)]*\\)")          # [label](url) link)


def escape_markdownv2(text: str) -> str:
    """Escape every MarkdownV2 special character (D-073)."""
    out: List[str] = []
    for ch in str(text):
        out.append("\\" + ch if ch in _MDV2_SPECIALS else ch)
    return "".join(out)


def validate_markdownv2(text: str) -> None:
    """Strict local MarkdownV2 parse: every special char must be
    escaped (or part of a supported entity). Raise Class-B otherwise —
    BEFORE dispatch, never as a Telegram-side parse failure."""
    stripped = _MDV2_ENTITY_RE.sub("", str(text))
    for ch in stripped:
        if ch in _MDV2_SPECIALS:
            raise TelegramContractError(
                f"unescaped MarkdownV2 special character {ch!r} — "
                "escape_markdownv2() required (D-073 local parse)")


# --- formatting: HTML (D-073) -----------------------------------------------------

_HTML_ALLOWED_TAGS = {
    "b", "strong", "i", "em", "u", "ins", "s", "strike", "del",
    "span", "tg-spoiler", "a", "code", "pre", "blockquote",
    "tg-emoji",
}

_HTML_TAG_RE = re.compile(r"<(/?)([a-zA-Z-]+)(\s[^>]*)?>")
_HTML_ENTITY_RE = re.compile(r"&(amp|lt|gt|quot);")


def escape_html(text: str) -> str:
    """Escape HTML reserved characters (D-073)."""
    return (str(text).replace("&", "&amp;")
            .replace("<", "&lt;").replace(">", "&gt;"))


def validate_html(text: str) -> None:
    """Strict local HTML parse: only supported tags, balanced, and no
    raw & < > outside entities. Raise Class-B otherwise."""
    out = str(text)
    stack: List[str] = []
    for m in _HTML_TAG_RE.finditer(out):
        closing, tag = m.group(1) == "/", m.group(2).lower()
        if tag not in _HTML_ALLOWED_TAGS:
            raise TelegramContractError(
                f"unsupported HTML tag <{tag}> — allowed: "
                f"{sorted(_HTML_ALLOWED_TAGS)} (D-073 local parse)")
        if closing:
            if not stack or stack[-1] != tag:
                raise TelegramContractError(
                    f"unbalanced HTML tag </{tag}> (D-073 local parse)")
            stack.pop()
        elif not m.group(3) or not m.group(3).rstrip().endswith("/"):
            stack.append(tag)
    if stack:
        raise TelegramContractError(
            f"unclosed HTML tag(s) {stack} (D-073 local parse)")
    residue = _HTML_TAG_RE.sub("", out)
    residue = _HTML_ENTITY_RE.sub("", residue)
    for ch in ("&", "<", ">"):
        if ch in residue:
            raise TelegramContractError(
                f"raw {ch!r} outside entities/tags — escape_html() "
                "required (D-073 local parse)")


# --- payload validation (D-073) ---------------------------------------------------

def _clean_str(payload: Dict, key: str) -> str:
    return str(payload[key]).strip()


def _validate_media_item(item: Dict, index: int) -> Dict:
    if not isinstance(item, dict):
        raise TelegramContractError(
            f"album item {index} must be a dict (D-073)")
    kind = str(item.get("type", "")).strip()
    if kind not in ("photo", "video"):
        raise TelegramContractError(
            f"album item {index} type must be photo|video, got "
            f"{kind!r} (Telegram album rule; D-073)")
    media_ref = str(item.get("media_ref", "")).strip()
    if not media_ref:
        raise TelegramContractError(
            f"album item {index} missing media_ref (D-073)")
    size = item.get("file_size_bytes")
    if size is not None and int(size) > MAX_FILE_BYTES:
        raise TelegramContractError(
            f"album item {index} exceeds {MAX_FILE_BYTES} bytes "
            "(Bot API 50 MB limit; D-073 local reject)")
    return {"type": kind, "media_ref": media_ref,
            "file_size_bytes": None if size is None else int(size)}


def validate_publish_payload(payload: Dict) -> Dict:
    """Validate a publish payload LOCALLY (Class-B prevention).

    Required for every kind: chat_id (int or @channel), content_id,
    kind ∈ {text, photo, video, document, mediagroup},
    parse_mode ∈ {None, "", MarkdownV2, HTML}, scheduled_slot.
    Per kind: text payload needs text (≤ 4096); photo/video/document
    need media_ref + media_hash + file_size_bytes (≤ 50 MB) and
    caption ≤ 1024 when present; mediagroup needs items (2..10).
    MarkdownV2/HTML payloads are parsed STRICTLY locally.
    """
    if not isinstance(payload, dict):
        raise TelegramContractError(
            "publish payload must be a dict (D-073)")
    required = ("chat_id", "content_id", "kind", "scheduled_slot")
    missing = [k for k in required
               if k not in payload or payload[k] in (None, "")]
    if missing:
        raise TelegramContractError(
            f"publish payload missing {missing} (D-073)")

    chat_id = payload["chat_id"]
    if isinstance(chat_id, str):
        chat_id = chat_id.strip()
        if not (chat_id.startswith("@") and len(chat_id) > 1):
            raise TelegramContractError(
                "string chat_id must be an @channelname (D-073)")
    elif isinstance(chat_id, int):
        if chat_id == 0:
            raise TelegramContractError("chat_id must be non-zero")
    else:
        raise TelegramContractError(
            "chat_id must be an int or @channelname (D-073)")

    kind = str(payload["kind"]).strip()
    if kind not in PAYLOAD_KINDS:
        raise TelegramContractError(
            f"kind {kind!r} not in {PAYLOAD_KINDS} (D-073)")

    parse_mode = payload.get("parse_mode") or ""
    parse_mode = str(parse_mode)
    if parse_mode not in ALLOWED_PARSE_MODES:
        raise TelegramContractError(
            f"parse_mode {parse_mode!r} not in {ALLOWED_PARSE_MODES} "
            "(D-073 local reject)")

    content_id = _clean_str(payload, "content_id")
    if not content_id:
        raise TelegramContractError("content_id must be non-empty")
    slot = str(payload["scheduled_slot"]).strip()

    norm: Dict = {
        "chat_id": chat_id,
        "content_id": content_id,
        "kind": kind,
        "parse_mode": parse_mode,
        "scheduled_slot": slot,
        "items": [],
        "caption": "",
        "media_ref": "",
        "media_hash": "",
        "file_size_bytes": None,
    }

    if kind == "text":
        text = str(payload.get("text", ""))
        if not text.strip():
            raise TelegramContractError(
                "text payload requires non-empty text (D-073)")
        if len(text) > MAX_TEXT_CHARS:
            raise TelegramContractError(
                f"text exceeds {MAX_TEXT_CHARS} chars ({len(text)}) "
                "— local reject before dispatch")
        if parse_mode == "MarkdownV2":
            validate_markdownv2(text)
        elif parse_mode == "HTML":
            validate_html(text)
        norm["text"] = text
        norm["text_hash"] = text_hash(text)
        return norm

    if kind == "mediagroup":
        items = payload.get("items")
        if not isinstance(items, list):
            raise TelegramContractError(
                "mediagroup payload requires items list (D-073)")
        if not MIN_ALBUM_ITEMS <= len(items) <= MAX_ALBUM_ITEMS:
            raise TelegramContractError(
                f"album must have {MIN_ALBUM_ITEMS}..{MAX_ALBUM_ITEMS} "
                f"items, got {len(items)} (D-073 local reject)")
        norm["items"] = [_validate_media_item(it, i)
                         for i, it in enumerate(items)]
    else:
        media_ref = str(payload.get("media_ref", "")).strip()
        if not media_ref:
            raise TelegramContractError(
                f"{kind} payload requires media_ref (D-051 reference)")
        media_hash = str(payload.get("media_hash", "")).strip()
        if len(media_hash) < 8:
            raise TelegramContractError(
                "media_hash must be a content hash (≥8 chars) — "
                "required for the D-074 idempotency key")
        size = payload.get("file_size_bytes")
        if size is None:
            raise TelegramContractError(
                f"{kind} payload requires file_size_bytes (D-073 "
                "local size enforcement)")
        if int(size) > MAX_FILE_BYTES:
            raise TelegramContractError(
                f"file exceeds {MAX_FILE_BYTES} bytes (Bot API 50 MB "
                "limit; D-073 local reject)")
        norm["media_ref"] = media_ref
        norm["media_hash"] = media_hash
        norm["file_size_bytes"] = int(size)

    caption = str(payload.get("caption", ""))
    if caption:
        if len(caption) > MAX_MEDIA_CAPTION_CHARS:
            raise TelegramContractError(
                f"caption exceeds {MAX_MEDIA_CAPTION_CHARS} chars "
                f"({len(caption)}) — local reject before dispatch")
        if parse_mode == "MarkdownV2":
            validate_markdownv2(caption)
        elif parse_mode == "HTML":
            validate_html(caption)
    norm["caption"] = caption
    norm["text_hash"] = text_hash(caption or kind)
    return norm


def text_hash(text: str) -> str:
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


def publish_idempotency_key(chat_id, content_id: str, media_hash: str,
                            text_hash_v: str, scheduled_slot: str) -> str:
    """D-074 deterministic key: sha256(chat_id, content_id, media_hash,
    text_hash, scheduled_slot)."""
    material = "|".join((str(chat_id), str(content_id),
                         str(media_hash or ""), str(text_hash_v),
                         str(scheduled_slot)))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def key_from_payload(payload: Dict) -> str:
    """Derive the D-074 key from a validated payload (or raise)."""
    norm = validate_publish_payload(payload)
    return publish_idempotency_key(
        norm["chat_id"], norm["content_id"], norm["media_hash"],
        norm["text_hash"], norm["scheduled_slot"])


def media_group_hash(items: List[Dict]) -> str:
    """Content hash over the album composition (D-074 key material)."""
    composition = [(it["type"], it["media_ref"]) for it in items]
    return hashlib.sha256(repr(composition).encode("utf-8")).hexdigest()

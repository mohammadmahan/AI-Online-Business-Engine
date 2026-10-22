"""Phase 5 §5.1 — Social Publishing Bundler & HITL pipeline (D-172).

Roadmap §5.1 asks for *automated post assembly*: an image group, a
formatted caption and a purchase CTA, delivered through the canonical
Telegram seam. Phase 4 already produces the raw material — a §4.1 copy
pack (Instagram caption, Telegram announcement, SEO copy) and a §4.2
trend tag set — but nothing joined them into ONE reviewable artifact.

This module is that join, and nothing more:

    structured brief
      → §4.1 copy pack (dry-run)  ─┐
      → §4.2 hashtag set (dry-run) ─┴→ cross-channel consistency checks
      → ONE `social_bundle_proposal.v1`
      → HITL queue via the M2 ProposalLifecycle (PROPOSED)
      → hand-off to the canonical outbox ONLY after a human ACCEPT

Fail-closed by construction
---------------------------
  - The bundler has **no publication surface**: it never imports an
    adapter, never opens a socket, never names a provider, and never
    calls an outbox `publish()`. It can only `bundle()` and, after a
    human acceptance, `hand_off_to_outbox()`.
  - `hand_off_to_outbox()` refuses unless ALL of these hold:
    the lifecycle state is ACCEPTED (not PROPOSED, not IN_REVIEW),
    the stored payload still hashes to the recorded `payload_hash`
    (tamper-evident), the payload itself declares
    `approval.required == true`, and at least one outbox is supplied
    (a silent no-op is a refusal, not a success).
  - Every composed string is re-validated against the **channel's own
    contract** (`telegram_contracts` / `instagram_contracts`) before a
    proposal exists, so a length or shape problem is Class B here and
    never at send time.
  - No canonical fact is invented: the purchase URL must be the
    merchant's own (a different URL anywhere in the copy is refused),
    every hashtag must come from the §4.2 set, and the shared
    `check_invented_facts` guard refuses an invented price, link or
    discount (AC-4/AC-5).

Scope honesty
-------------
  - The canonical Telegram publisher (D-073) has **no inline-keyboard
    field** yet, so §5.1's "inline keyboard with direct purchase link"
    is carried as a validated CTA **line** in the caption instead, and
    the keyboard remains a named gap for the publisher seam.
  - §5.2 (Instagram scheduling queue) is not touched: the bundle
    carries a `scheduled_slot` per channel, which is the input that
    queue will consume.
  - dry-run is the default and persists nothing; persist mode lands the
    bundle as PROPOSED and still requires a human decision.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Union

from canonical.ai_contracts import validate_output
from canonical.ai_proposal_lifecycle import ACCEPTED, PROPOSED
from canonical.ai_runtime import AiProposal
from canonical.ai_tasks import TaskEntity
from canonical.fashion_copy import (FashionBrief, FashionCopywritingEngine,
                                    check_invented_facts)
from canonical.fashion_trends import FashionTrendEngine, TrendBrief
from canonical.instagram_contracts import (
    MAX_CAPTION_CHARS as IG_CAPTION_MAX, MAX_HASHTAGS as IG_HASHTAG_MAX,
    InstagramContractError, validate_publish_payload as validate_instagram)
from canonical.orchestration_contracts import KNOWN_TARGETS
from canonical.telegram_contracts import (
    MAX_BUTTON_TEXT_CHARS as TG_BUTTON_TEXT_MAX,
    MAX_MEDIA_CAPTION_CHARS as TG_CAPTION_MAX, TelegramContractError,
    validate_publish_payload as validate_telegram)

BUNDLE_SCHEMA = "social_bundle_proposal.v1"
BUNDLE_TASK = "fashion_social_bundle"
BUNDLE_PROVIDER = "fashion-bundler"
BUNDLE_MODEL = "deterministic-v1"
PROPOSAL_PREFIX = "social-bundle"

# Channel identity is NOT re-typed here: D-131 keeps channel
# literals in their home modules, so this cross-channel composer takes
# the one declared target vocabulary (D-077) instead. A new channel is
# added in its own module + that registry, nowhere here.
INSTAGRAM, TELEGRAM = KNOWN_TARGETS
CHANNELS = (TELEGRAM, INSTAGRAM)
ASPECT_RATIOS = ("1:1", "4:5", "16:9")
MAX_IMAGES = 10

# UI chrome for the buy button when the §4.1 copy pack carries no CTA.
# This is an action label, never a business fact (price/link/discount
# stay canonical — AC-4/AC-5).
PURCHASE_CTA_LABEL = "خرید"


class SocialBundleError(ValueError):
    """Invalid brief or bundling input — Class B, refused before work."""

    failure_class = "B"


class BundleNotApproved(SocialBundleError):
    """Hand-off refused: the bundle has no human acceptance (or is not
    the artifact that was accepted)."""

    def __init__(self, message: str, *, state: str = ""):
        super().__init__(message)
        self.state = state


# --- media + brief ------------------------------------------------------------


@dataclass(frozen=True)
class MediaItem:
    """One image/video the MERCHANT supplies (never model-authored)."""

    media_ref: str
    media_hash: str
    file_size_bytes: int
    type: str = "photo"

    def validated(self) -> "MediaItem":
        ref = str(self.media_ref or "").strip()
        if not ref:
            raise SocialBundleError("media_ref is required")
        digest = str(self.media_hash or "").strip()
        if len(digest) < 8:
            raise SocialBundleError(
                "media_hash must be a content hash (≥8 chars) — it is the "
                "idempotency identity of the media (D-070/D-074)")
        kind = str(self.type or "photo").strip()
        if kind not in ("photo", "video"):
            raise SocialBundleError(
                f"media type {kind!r} must be photo|video")
        try:
            size = int(self.file_size_bytes)
        except (TypeError, ValueError) as exc:
            raise SocialBundleError(
                "file_size_bytes must be an integer") from exc
        if size <= 0:
            raise SocialBundleError("file_size_bytes must be positive")
        return MediaItem(media_ref=ref, media_hash=digest,
                         file_size_bytes=size, type=kind)


@dataclass(frozen=True)
class SocialBundleBrief:
    """Everything the bundle needs, and nothing the model may invent.

    The two Phase-4 briefs are carried as-is (`copy` for §4.1, `trends`
    for §4.2) so this module never re-implements their validation.
    """

    copy: FashionBrief
    trends: TrendBrief
    images: Tuple[MediaItem, ...]
    telegram_chat_id: Union[int, str]
    telegram_slot: str
    instagram_slot: str
    instagram_aspect_ratio: str = "4:5"
    content_id: str = ""
    purchase_url: str = ""
    include_link_in_text: bool = False

    def validated(self) -> "SocialBundleBrief":
        copy = self.copy.validated()
        trends = self.trends.validated()
        if copy.season != trends.season:
            raise SocialBundleError(
                f"season mismatch: copy={copy.season!r} "
                f"trends={trends.season!r} — one post, one season")
        if copy.fabric_type and trends.fabric_type \
                and copy.fabric_type != trends.fabric_type:
            raise SocialBundleError(
                f"fabric mismatch: copy={copy.fabric_type!r} "
                f"trends={trends.fabric_type!r}")
        if copy.product_id and trends.product_id \
                and copy.product_id != trends.product_id:
            raise SocialBundleError("product_id mismatch between briefs")

        images = tuple(m.validated() for m in (self.images or ()))
        if not 1 <= len(images) <= MAX_IMAGES:
            raise SocialBundleError(
                f"a bundle needs 1..{MAX_IMAGES} images, got {len(images)}")

        chat_id = self.telegram_chat_id
        if isinstance(chat_id, bool) or not isinstance(chat_id, (int, str)):
            raise SocialBundleError(
                "telegram_chat_id must be an int or @channel name")
        if isinstance(chat_id, str):
            chat_id = chat_id.strip()
            if not (chat_id.startswith("@") and len(chat_id) > 1):
                raise SocialBundleError(
                    "string telegram_chat_id must be an @channelname")
        elif chat_id == 0:
            raise SocialBundleError("telegram_chat_id must be non-zero")

        slots: Dict[str, str] = {}
        for name, raw in (("telegram_slot", self.telegram_slot),
                          ("instagram_slot", self.instagram_slot)):
            value = str(raw or "").strip()
            if not value:
                raise SocialBundleError(f"{name} is required")
            if len(value) > 64:
                raise SocialBundleError(f"{name} exceeds 64 chars")
            slots[name] = value

        ratio = str(self.instagram_aspect_ratio or "").strip()
        if ratio not in ASPECT_RATIOS:
            raise SocialBundleError(
                f"aspect ratio {ratio!r} not in {ASPECT_RATIOS}")

        url = str(self.purchase_url or "").strip()
        if url and not url.lower().startswith(("http://", "https://")):
            raise SocialBundleError(
                "purchase_url must be an http(s) URL")
        if self.include_link_in_text and not url:
            raise SocialBundleError(
                "include_link_in_text requires a purchase_url")

        content_id = str(self.content_id or "").strip()
        if not content_id:
            scope = copy.product_id or re.sub(
                r"\s+", "-", f"{copy.title}|{copy.season}")[:40]
            content_id = f"fashion-{scope}"
        if len(content_id) > 80:
            raise SocialBundleError("content_id exceeds 80 chars")

        return SocialBundleBrief(
            copy=copy, trends=trends, images=images,
            telegram_chat_id=chat_id,
            telegram_slot=slots["telegram_slot"],
            instagram_slot=slots["instagram_slot"],
            instagram_aspect_ratio=ratio, content_id=content_id,
            purchase_url=url,
            include_link_in_text=bool(self.include_link_in_text))


# --- contract -----------------------------------------------------------------

_STRING = {"type": "string"}


def _media_schema() -> Dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["type", "media_ref", "media_hash", "file_size_bytes"],
        "properties": {
            "type": {"type": "string", "enum": ["photo", "video"]},
            "media_ref": {"type": "string", "minLength": 1,
                          "maxLength": 500},
            "media_hash": {"type": "string", "minLength": 8,
                           "maxLength": 64},
            "file_size_bytes": {"type": "integer"},
        },
    }


SOCIAL_BUNDLE_V1 = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": BUNDLE_SCHEMA,
    "type": "object",
    "additionalProperties": False,
    "required": ["bundle_key", "product_id", "hashtags", TELEGRAM,
                 INSTAGRAM, "seo", "source", "approval"],
    "properties": {
        "bundle_key": {"type": "string", "pattern": "^[0-9a-f]{32}$"},
        "product_id": {"type": "string", "minLength": 1, "maxLength": 64},
        "hashtags": {"type": "array",
                     "items": {"type": "string", "minLength": 2,
                               "maxLength": 60},
                     "minItems": 1, "maxItems": IG_HASHTAG_MAX},
        TELEGRAM: {
            "type": "object",
            "additionalProperties": False,
            "required": ["chat_id", "content_id", "kind", "scheduled_slot",
                         "text", "media"],
            "properties": {
                "chat_id": {"type": "string", "minLength": 1,
                            "maxLength": 80},
                "content_id": {"type": "string", "minLength": 1,
                               "maxLength": 80},
                "kind": {"type": "string", "enum": ["photo", "mediagroup"]},
                "scheduled_slot": {"type": "string", "minLength": 1,
                                   "maxLength": 64},
                "text": {"type": "string", "minLength": 1,
                         "maxLength": TG_CAPTION_MAX},
                # optional buy button: rows of URL buttons, URL-only
                "inline_keyboard": {
                    "type": "array",
                    "maxItems": 8,
                    "items": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 3,
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["text", "url"],
                            "properties": {
                                "text": {"type": "string", "minLength": 1,
                                         "maxLength": TG_BUTTON_TEXT_MAX},
                                "url": {"type": "string", "minLength": 1,
                                        "maxLength": 2048},
                            },
                        },
                    },
                },
                "media": {"type": "array", "items": _media_schema(),
                          "minItems": 1, "maxItems": MAX_IMAGES},
            },
        },
        INSTAGRAM: {
            "type": "object",
            "additionalProperties": False,
            "required": ["content_id", "media_ref", "media_hash", "caption",
                         "aspect_ratio", "scheduled_slot"],
            "properties": {
                "content_id": {"type": "string", "minLength": 1,
                               "maxLength": 80},
                "media_ref": {"type": "string", "minLength": 1,
                              "maxLength": 500},
                "media_hash": {"type": "string", "minLength": 8,
                               "maxLength": 64},
                "caption": {"type": "string", "minLength": 1,
                            "maxLength": IG_CAPTION_MAX},
                "aspect_ratio": {"type": "string",
                                 "enum": list(ASPECT_RATIOS)},
                "scheduled_slot": {"type": "string", "minLength": 1,
                                   "maxLength": 64},
            },
        },
        "seo": {
            "type": "object",
            "additionalProperties": False,
            "required": ["meta_description_fa", "seo_keywords"],
            "properties": {
                "meta_description_fa": {"type": "string", "minLength": 50,
                                        "maxLength": 160},
                "seo_keywords": {"type": "array",
                                 "items": {"type": "string", "minLength": 2,
                                           "maxLength": 40},
                                 "minItems": 1, "maxItems": 15},
            },
        },
        "source": {
            "type": "object",
            "additionalProperties": False,
            "required": ["copy_schema", "copy_task", "copy_provider",
                         "copy_model", "trend_schema", "trend_task",
                         "trend_provider", "trend_model"],
            "properties": {
                "copy_schema": {"type": "string", "minLength": 3,
                                "maxLength": 60},
                "copy_task": {"type": "string", "minLength": 3,
                              "maxLength": 60},
                "copy_provider": {"type": "string", "minLength": 1,
                                  "maxLength": 40},
                "copy_model": {"type": "string", "minLength": 1,
                               "maxLength": 60},
                "trend_schema": {"type": "string", "minLength": 3,
                                 "maxLength": 60},
                "trend_task": {"type": "string", "minLength": 3,
                               "maxLength": 60},
                "trend_provider": {"type": "string", "minLength": 1,
                                   "maxLength": 40},
                "trend_model": {"type": "string", "minLength": 1,
                                "maxLength": 60},
            },
        },
        "approval": {
            "type": "object",
            "additionalProperties": False,
            "required": ["required", "state"],
            "properties": {
                "required": {"type": "boolean", "enum": [True]},
                "state": {"type": "string", "enum": ["PROPOSED"]},
            },
        },
    },
}


def validate_bundle_payload(payload: Dict) -> List[str]:
    """Strict validation of a bundle payload (returns [] when valid)."""
    return validate_output(SOCIAL_BUNDLE_V1, payload) or []


def payload_hash(payload) -> str:
    """Same canonicalisation as the M2 lifecycle stores (drift-tested)."""
    return hashlib.sha256(json.dumps(
        payload, sort_keys=True, ensure_ascii=False,
        default=str).encode("utf-8")).hexdigest()


def proposal_id_for(bundle_key: str) -> str:
    return f"{PROPOSAL_PREFIX}|{bundle_key}"


def approved_bundle_payload(lifecycle, bundle_id: str):
    """The ONE human-acceptance gate for a bundle (D-026/D-172).

    Returns `(state, payload)` only when the lifecycle says ACCEPTED,
    the artifact is this bundle schema, its stored payload still hashes
    to the recorded commitment, and the payload itself declares
    `approval.required: true`. Every refusal is `BundleNotApproved`.

    Used by `hand_off_to_outbox()` and by the §5.2 publishing queue, so
    the two release paths cannot drift into different guarantees.
    """
    try:
        state = lifecycle.state_of(bundle_id)
    except KeyError as exc:
        raise BundleNotApproved(
            f"unknown bundle {bundle_id!r} — nothing was accepted") \
            from exc
    if state != ACCEPTED:
        raise BundleNotApproved(
            f"bundle {bundle_id!r} is {state}; only an ACCEPTED bundle "
            "may be released (human approval is mandatory)",
            state=state)
    ref = lifecycle.proposal_ref(bundle_id)
    if not ref:
        raise BundleNotApproved(
            "the accepted bundle has no original proposal reference",
            state=state)
    if ref.get("schema_id") != BUNDLE_SCHEMA:
        raise BundleNotApproved(
            f"proposal {bundle_id!r} is {ref.get('schema_id')!r}, not "
            f"{BUNDLE_SCHEMA} — only a social bundle may be released",
            state=state)
    payload = ref.get("payload") or {}
    if payload_hash(payload) != ref.get("payload_hash"):
        raise BundleNotApproved(
            "the stored bundle payload no longer matches its recorded "
            "hash — tampered or corrupted artifact", state=state)
    approval = payload.get("approval") or {}
    if approval.get("required") is not True:
        raise BundleNotApproved(
            "the payload does not declare approval.required=true",
            state=state)
    return state, payload


# --- report -------------------------------------------------------------------


@dataclass(frozen=True)
class BundleReport:
    ok: bool
    mode: str
    bundle_key: str = ""
    proposal_id: str = ""
    state: Optional[str] = None
    payload: Optional[Dict] = None
    errors: Tuple[str, ...] = ()

    def to_dict(self) -> Dict:
        out: Dict = {"ok": self.ok, "mode": self.mode}
        for key, value in (("bundle_key", self.bundle_key),
                           ("proposal_id", self.proposal_id),
                           ("state", self.state)):
            if value:
                out[key] = value
        if self.errors:
            out["errors"] = list(self.errors)
        return out


# --- bundler ------------------------------------------------------------------


_HASHTAG_RE = re.compile(r"#[^\s#]+")
_LINK_RE = re.compile(r"https?://\S+")


def _render_hashtags(tags: List[str]) -> List[str]:
    out: List[str] = []
    for raw in tags or []:
        token = str(raw).strip().lstrip("#").strip()
        if not token:
            continue
        rendered = f"#{token}"
        if rendered not in out:
            out.append(rendered)
    return out


class FashionSocialBundler:
    """Phase 5 §5.1 assembly: copy + tags → one HITL bundle."""

    def __init__(self, router, *, lifecycle=None):
        self.router = router
        self.lifecycle = lifecycle
        self.copy_engine = FashionCopywritingEngine(router)
        self.trend_engine = FashionTrendEngine(router)

    # -- composition -----------------------------------------------------------

    def _facts(self, brief: SocialBundleBrief) -> Dict[str, str]:
        facts = dict(brief.copy.context())
        facts.update({k: v for k, v in brief.trends.context().items()
                      if k not in facts})
        if brief.purchase_url:
            facts["purchase_url"] = brief.purchase_url
        return facts

    def _instagram_caption(self, copy: Dict, hashtags: List[str],
                           brief: SocialBundleBrief) -> str:
        parts = [str(copy.get("caption_fa", "")).strip()]
        if brief.include_link_in_text:
            parts.append(f"برای خرید: {brief.purchase_url}")
        if hashtags:
            parts.append(" ".join(hashtags))
        return "\n\n".join(p for p in parts if p)

    def _telegram_text(self, copy: Dict, hashtags: List[str],
                       brief: SocialBundleBrief) -> str:
        parts = [str(copy.get("announcement_fa", "")).strip()]
        cta = str(copy.get("cta_fa", "")).strip()
        if cta:
            parts.append(cta)
        if brief.include_link_in_text:
            parts.append(brief.purchase_url)
        if hashtags:
            parts.append(" ".join(hashtags))
        return "\n\n".join(p for p in parts if p)

    @staticmethod
    def _chat_id_text(chat_id: Union[int, str]) -> str:
        return str(chat_id).strip()

    @staticmethod
    def _chat_id_canonical(chat_id_text: str) -> Union[int, str]:
        """Back to the contract's own shape: a numeric id (channel ids are
        NEGATIVE for supergroups, so `-100…` must survive as an int) or
        the `@channelname` string."""
        value = str(chat_id_text).strip()
        digits = value[1:] if value.startswith("-") else value
        if digits.isdigit() and digits:
            return int(value)
        return value

    def _bundle_key(self, brief: SocialBundleBrief, copy_hash: str,
                    trend_hash: str) -> str:
        body = {
            "content_id": brief.content_id,
            "copy": copy_hash,
            "trend": trend_hash,
            "media": [m.media_hash for m in brief.images],
            TELEGRAM: {"chat_id": self._chat_id_text(
                brief.telegram_chat_id), "slot": brief.telegram_slot},
            INSTAGRAM: {"slot": brief.instagram_slot,
                        "ratio": brief.instagram_aspect_ratio},
            "url": brief.purchase_url,
        }
        return hashlib.sha256(json.dumps(
            body, sort_keys=True, ensure_ascii=False).encode(
                "utf-8")).hexdigest()[:32]

    # -- the one entry point ---------------------------------------------------

    def bundle(self, brief: SocialBundleBrief, *, mode: str = "dry-run",
               actor: str = "social-bundler") -> BundleReport:
        """Compose + validate + (optionally) queue ONE reviewable bundle."""
        if mode not in ("dry-run", "persist"):
            raise SocialBundleError(f"unknown mode {mode!r}")
        clean = brief.validated()

        pack = self.copy_engine.generate_pack(clean.copy, mode="dry-run")
        if not pack.ok:
            return BundleReport(ok=False, mode=mode, errors=tuple(
                f"copy channel {name}: {rep.error}"
                for name, rep in pack.reports.items() if not rep.ok))
        trend_rep = self.trend_engine.generate(clean.trends, mode="dry-run")
        if not trend_rep.ok:
            return BundleReport(ok=False, mode=mode, errors=tuple(
                trend_rep.divergences or [trend_rep.error or
                                          "trend generation failed"]))

        copy_ig = pack.channel("instagram_caption") or {}
        copy_tg = pack.channel("telegram_announcement") or {}
        copy_seo = pack.channel("seo_copy") or {}
        trend_payload = trend_rep.proposal.payload or {}

        hashtags = _render_hashtags(trend_payload.get("hashtags") or [])
        caption = self._instagram_caption(copy_ig, hashtags, clean)
        text = self._telegram_text(copy_tg, hashtags, clean)

        errors: List[str] = []

        # (a) channel contracts — the same validators the publishers use
        first = clean.images[0]
        # The buy button is generated from the MERCHANT'S OWN purchase URL
        # (never model-authored) and pinned to that exact URL at
        # validation, so no foreign domain can ride along.
        keyboard = []
        if clean.purchase_url:
            label = str(copy_tg.get("cta_fa") or "").strip()
            if not 1 <= len(label) <= TG_BUTTON_TEXT_MAX:
                label = PURCHASE_CTA_LABEL
            keyboard = [[{"text": label, "url": clean.purchase_url}]]
        try:
            tg_norm = validate_telegram({
                "chat_id": self._chat_id_canonical(
                    self._chat_id_text(clean.telegram_chat_id)),
                "content_id": clean.content_id,
                "kind": "mediagroup" if len(clean.images) >= 2 else "photo",
                "parse_mode": "",
                "scheduled_slot": clean.telegram_slot,
                "caption": text,
                "inline_keyboard": keyboard,
                "items": [{"type": m.type, "media_ref": m.media_ref,
                           "media_hash": m.media_hash,
                           "file_size_bytes": m.file_size_bytes}
                          for m in clean.images],
                "media_ref": first.media_ref,
                "media_hash": first.media_hash,
                "file_size_bytes": first.file_size_bytes,
            }, allowed_urls={clean.purchase_url} if clean.purchase_url else None)
        except TelegramContractError as exc:
            errors.append(f"telegram: {exc}")
            tg_norm = {}
        try:
            ig_norm = validate_instagram({
                "content_id": clean.content_id,
                "media_ref": first.media_ref,
                "media_hash": first.media_hash,
                "caption": caption,
                "aspect_ratio": clean.instagram_aspect_ratio,
                "scheduled_slot": clean.instagram_slot,
            })
        except InstagramContractError as exc:
            errors.append(f"instagram: {exc}")
            ig_norm = {}

        # (b) targeting consistency: no tag outside the §4.2 set
        allowed = set(hashtags)
        for channel, body in ((INSTAGRAM, caption), (TELEGRAM, text)):
            used = set(_HASHTAG_RE.findall(body))
            stray = sorted(used - allowed)
            if stray:
                errors.append(
                    f"{channel}: hashtags {stray} are not in the §4.2 trend "
                    "set — a bundle cannot smuggle untargeted tags")

        # (c) no invented canonical facts (AC-4/AC-5)
        entity = TaskEntity(kind="fashion_bundle",
                            key=f"bundle|{clean.content_id}",
                            payload=self._facts(clean))
        errors.extend(check_invented_facts(
            {"caption": caption, "text": text,
             "meta_description_fa": copy_seo.get("meta_description_fa", "")},
            entity, "social_bundle"))

        # (d) links: only the merchant's own URL may appear
        permitted = {clean.purchase_url} if clean.purchase_url else set()
        for channel, body in ((INSTAGRAM, caption), (TELEGRAM, text)):
            for link in _LINK_RE.findall(body):
                if link not in permitted:
                    errors.append(
                        f"{channel}: link {link!r} is not the merchant's "
                        "purchase_url — links are canonical facts")

        if errors:
            return BundleReport(ok=False, mode=mode, errors=tuple(errors))

        copy_proposal = pack.reports["instagram_caption"].proposal
        trend_proposal = trend_rep.proposal
        key = self._bundle_key(
            clean,
            payload_hash(copy_ig),
            payload_hash(trend_payload))
        payload = {
            "bundle_key": key,
            "product_id": clean.copy.product_id or clean.content_id,
            "hashtags": [h.lstrip("#") for h in hashtags],
            TELEGRAM: {
                "chat_id": self._chat_id_text(clean.telegram_chat_id),
                "content_id": clean.content_id,
                "kind": tg_norm["kind"],
                "scheduled_slot": clean.telegram_slot,
                "text": text,
                "inline_keyboard": tg_norm.get("inline_keyboard", []),
                "media": [{"type": m.type, "media_ref": m.media_ref,
                           "media_hash": m.media_hash,
                           "file_size_bytes": m.file_size_bytes}
                          for m in clean.images],
            },
            INSTAGRAM: {
                "content_id": ig_norm["content_id"],
                "media_ref": ig_norm["media_ref"],
                "media_hash": ig_norm["media_hash"],
                "caption": ig_norm["caption"],
                "aspect_ratio": ig_norm["aspect_ratio"],
                "scheduled_slot": ig_norm["scheduled_slot"],
            },
            "seo": {
                "meta_description_fa": copy_seo.get("meta_description_fa",
                                                   ""),
                "seo_keywords": list(copy_seo.get("seo_keywords") or []),
            },
            "source": {
                "copy_schema": copy_proposal.schema_id,
                "copy_task": copy_proposal.task_type,
                "copy_provider": copy_proposal.provider,
                "copy_model": copy_proposal.model,
                "trend_schema": trend_proposal.schema_id,
                "trend_task": trend_proposal.task_type,
                "trend_provider": trend_proposal.provider,
                "trend_model": trend_proposal.model,
            },
            "approval": {"required": True, "state": "PROPOSED"},
        }
        contract_errors = validate_bundle_payload(payload)
        if contract_errors:
            return BundleReport(ok=False, mode=mode,
                                errors=tuple(contract_errors))

        report = BundleReport(ok=True, mode=mode, bundle_key=key,
                              proposal_id=proposal_id_for(key),
                              payload=payload)
        if mode == "dry-run":
            return report
        return self._submit(report, actor=actor)

    # -- persistence (PROPOSED only) -------------------------------------------

    def _submit(self, report: BundleReport, *, actor: str) -> BundleReport:
        if self.lifecycle is None:
            raise SocialBundleError(
                "persist mode requires a ProposalLifecycle — a bundle is "
                "never durable without the HITL round-trip")
        proposal = AiProposal(
            schema_id=BUNDLE_SCHEMA, task_type=BUNDLE_TASK,
            payload=report.payload, provider=BUNDLE_PROVIDER,
            model=BUNDLE_MODEL,
            usage={"prompt_tokens": 0, "completion_tokens": 0,
                   "estimated_cost": 0.0},
            cost={"cost_usd": 0.0, "unknown_tariff": False},
            provenance_id=None, correlation_id=report.proposal_id)
        res = self.lifecycle.submit(proposal, actor=actor)
        return BundleReport(ok=True, mode="persist",
                            bundle_key=report.bundle_key,
                            proposal_id=res["proposal_id"],
                            state=res["state"], payload=report.payload)

    # -- the ONLY way out of the queue -----------------------------------------

    def hand_off_to_outbox(self, bundle_id: str, *, lifecycle,
                           telegram_outbox=None, instagram_outbox=None,
                           actor: str = "social-bundler") -> Dict:
        """Enqueue an ACCEPTED bundle into the canonical outboxes.

        Refuses unless a human accepted THIS payload. The outboxes are
        the D-073/D-069 seams; this method never calls their send path.
        """
        state, payload = approved_bundle_payload(lifecycle, bundle_id)
        if telegram_outbox is None and instagram_outbox is None:
            raise BundleNotApproved(
                "no outbox supplied — a silent no-op is not a release",
                state=state)

        queued: Dict[str, Dict] = {}
        if telegram_outbox is not None:
            queued[TELEGRAM] = telegram_outbox.enqueue(
                self._canonical_telegram(payload), actor=actor)
        if instagram_outbox is not None:
            queued[INSTAGRAM] = instagram_outbox.enqueue(
                self._canonical_instagram(payload), actor=actor)
        return {"bundle_id": bundle_id, "state": state,
                "bundle_key": payload.get("bundle_key", ""),
                "queued": queued}

    # -- review surface --------------------------------------------------------

    def pending_bundles(self, *, lifecycle=None) -> List[Dict]:
        """The merchant's review list: bundles still awaiting a human.

        Read-only and derived from the durable lifecycle history, so the
        list survives a restart and never depends on in-memory state.
        """
        life = lifecycle or self.lifecycle
        if life is None:
            raise SocialBundleError(
                "pending_bundles requires a ProposalLifecycle")
        out: List[Dict] = []
        for item in life.pending_proposals():
            proposal_id = str(item.get("proposal_id", ""))
            if not proposal_id.startswith(f"{PROPOSAL_PREFIX}|"):
                continue
            base = life.proposal_ref(proposal_id) or {}
            if base.get("schema_id") != BUNDLE_SCHEMA:
                continue
            payload = base.get("payload") or {}
            out.append({
                "proposal_id": proposal_id,
                "state": item.get("state", PROPOSED),
                "bundle_key": payload.get("bundle_key", ""),
                "content_id": (payload.get(INSTAGRAM) or {}).get(
                    "content_id", ""),
                "channels": [c for c in CHANNELS if c in payload],
                "telegram_slot": (payload.get(TELEGRAM) or {}).get(
                    "scheduled_slot", ""),
                "instagram_slot": (payload.get(INSTAGRAM) or {}).get(
                    "scheduled_slot", ""),
                "payload_hash": base.get("payload_hash", ""),
            })
        out.sort(key=lambda r: (r["telegram_slot"], r["proposal_id"]))
        return out

    @staticmethod
    def _canonical_telegram(payload: Dict) -> Dict:
        tg = payload[TELEGRAM]
        channel_payload = {
            "chat_id": FashionSocialBundler._chat_id_canonical(tg["chat_id"]),
            "content_id": tg["content_id"],
            "kind": tg["kind"],
            "parse_mode": "",
            "scheduled_slot": tg["scheduled_slot"],
            "caption": tg["text"],
        }
        if tg["kind"] == "mediagroup":
            channel_payload["items"] = [
                {"type": m["type"], "media_ref": m["media_ref"],
                 "file_size_bytes": m["file_size_bytes"]}
                for m in tg["media"]]
        else:
            media = tg["media"][0]
            channel_payload.update({
                "media_ref": media["media_ref"],
                "media_hash": media["media_hash"],
                "file_size_bytes": media["file_size_bytes"]})
        if tg.get("inline_keyboard"):
            channel_payload["inline_keyboard"] = tg["inline_keyboard"]
        return validate_telegram(channel_payload)

    @staticmethod
    def _canonical_instagram(payload: Dict) -> Dict:
        return validate_instagram(dict(payload[INSTAGRAM]))


__all__ = [
    "ASPECT_RATIOS",
    "BUNDLE_MODEL",
    "BUNDLE_PROVIDER",
    "BUNDLE_SCHEMA",
    "BUNDLE_TASK",
    "BundleNotApproved",
    "BundleReport",
    "CHANNELS",
    "FashionSocialBundler",
    "MAX_IMAGES",
    "MediaItem",
    "PROPOSAL_PREFIX",
    "SOCIAL_BUNDLE_V1",
    "SocialBundleBrief",
    "SocialBundleError",
    "payload_hash",
    "proposal_id_for",
    "validate_bundle_payload",
]

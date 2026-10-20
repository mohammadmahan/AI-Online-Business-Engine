"""Phase 4 §4.1 — Fashion Copywriting Engine (D-172 / roadmap AC-3).

One merchant-facing pipeline that turns a STRUCTURED brief

    fabric_type + season + title + raw seller notes (+ tone preset)

into the three approved copy channels:

    instagram_caption     → caption_proposal.v1        (tone presets)
    telegram_announcement → telegram_announcement.v1   (channel-capped)
    seo_copy              → seo_copy.v1                (meta + web copy)

Design constraints (all inherited, nothing re-implemented):

  - D-045/D-062: dispatch ONLY through the M1 ModelRouter → AiProvider
    boundary. This module never imports a live provider, never reads
    credentials and never builds an HTTP client — locally it runs on
    MockAiProvider, and the owner-gated live adapters are drop-ins via
    the SAME routing policy keys (`fashion_telegram_announcement`,
    `fashion_seo_copy`, and the approved `generate_caption` channel for
    Instagram).
  - G-6 (one dispatch path per channel): the Instagram channel reuses
    the APPROVED `generate_caption` task/contract — the tone preset is
    request-side input, so no second caption contract is created.
  - D-067: every prompt is rendered from the versioned template
    registry (`fashion_instagram_caption`,
    `fashion_telegram_announcement`, `fashion_seo_copy`); the request
    trail carries template_id + template_hash, so any copy is
    reproducible from (brief, template).
  - D-062/D-052: output is validated against the strict contract BEFORE
    it exists durably — a contract violation is Class B, never repaired.
  - D-029/D-031/D-032: hashtags/keywords pass the ONE shared vocabulary
    guard (`check_hashtag_vocabulary`) — new vocabulary stays
    human-owned.
  - AC-4/AC-5: the model never invents canonical facts. Price, links,
    coupon/discount tokens that do NOT appear in the brief are a
    divergence (Class B), on every channel.
  - D-158/D-050: in persist mode the copy lands as a PROPOSED record
    via the M2 ProposalLifecycle (D-027 event + D-026 provenance + HITL
    queue). There is NO path from this engine to a published state —
    the only state driver is ProposalLifecycle.decide(), human-only.
  - D-073 parity: the Telegram announcement is checked against the
    channel's own cap (`telegram_contracts.MAX_TEXT_CHARS`) including
    the CTA and hashtag suffix, so copy can never be refused at publish
    time for length.

dry-run is the default: it generates, validates and divergence-checks
the copy while persisting nothing (verification-only), so an operator
can preview all three channels without touching the HITL queue.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from canonical.ai_runtime import AiRequest, ModelRouter
from canonical.ai_tasks import (AiTask, CaptionTask, TaskEntity, TaskReport,
                                check_hashtag_vocabulary)
from canonical.ai_templates import (TemplateEngine, TemplateRegistry,
                                    render_into_request)
from canonical.telegram_contracts import MAX_TEXT_CHARS as TELEGRAM_TEXT_MAX

# --- tone presets (roadmap §4.1: Luxury / Casual / Trendy) --------------------


@dataclass(frozen=True)
class TonePreset:
    """Deterministic tone configuration — never model-chosen (D-067)."""

    slug: str
    label_fa: str
    guidance_fa: str


TONE_PRESETS: Dict[str, TonePreset] = {
    "luxury": TonePreset(
        "luxury", "لوکس",
        "جمله‌های کوتاه و آرام، تمرکز بر جنس پارچه و دوخت، بدون شعار "
        "تبلیغاتی و بدون ایموجی"),
    "casual": TonePreset(
        "casual", "خودی",
        "لحن صمیمی و روزمره، جمله‌های ساده و مستقیم، یک سؤال تعاملی "
        "کوتاه در پایان"),
    "trendy": TonePreset(
        "trendy", "ترند",
        "لحن پرانرژی و به‌روز، اشاره به استایل همین فصل و ترکیب رنگ، "
        "هشتگ‌های موضوعی بیشتر"),
}

DEFAULT_TONE = "luxury"

# channel → routing/contract/template identity
CHANNELS: Dict[str, Dict[str, str]] = {
    "instagram_caption": {
        "task_type": "generate_caption",           # approved Phase 7 channel
        "schema_id": "caption_proposal.v1",
        "template_id": "fashion_instagram_caption",
    },
    "telegram_announcement": {
        "task_type": "fashion_telegram_announcement",
        "schema_id": "telegram_announcement.v1",
        "template_id": "fashion_telegram_announcement",
    },
    "seo_copy": {
        "task_type": "fashion_seo_copy",
        "schema_id": "seo_copy.v1",
        "template_id": "fashion_seo_copy",
    },
}

CHANNEL_ORDER = ("instagram_caption", "telegram_announcement", "seo_copy")


class FashionInputError(ValueError):
    """Invalid brief (missing/oversized field, unknown tone).

    Class B (D-052): a data invariant, refused before any dispatch —
    the model is never asked to fill in what the merchant must state.
    """

    failure_class = "B"


# --- brief model --------------------------------------------------------------


@dataclass(frozen=True)
class FashionBrief:
    """Structured copywriting input (§4.1).

    `notes` is the seller's raw, unstructured text (Persian allowed);
    `tone` selects a TONE_PRESETS preset (deterministic configuration);
    `product_id` is optional and only scopes the deterministic request
    key (AC-3: per product revision) — it is never invented or widened
    by the model.
    """

    title: str
    fabric_type: str
    season: str
    notes: str = ""
    tone: str = DEFAULT_TONE
    product_id: str = ""

    def validated(self) -> "FashionBrief":
        """Return a normalized copy or raise FashionInputError (Class B)."""
        clean: Dict[str, str] = {}
        for name, raw, lo, hi in (
                ("title", self.title, 2, 200),
                ("fabric_type", self.fabric_type, 2, 60),
                ("season", self.season, 1, 40),
                ("notes", self.notes or "", 0, 2000),
                ("product_id", self.product_id or "", 0, 64),
        ):
            if not isinstance(raw, str):
                raise FashionInputError(
                    f"brief.{name} must be a string, got "
                    f"{type(raw).__name__}")
            value = raw.strip()
            if len(value) < lo:
                raise FashionInputError(
                    f"brief.{name} is required (min {lo} chars)")
            if len(value) > hi:
                raise FashionInputError(
                    f"brief.{name} exceeds {hi} chars ({len(value)})")
            clean[name] = value
        tone = str(self.tone or "").strip().lower()
        if tone not in TONE_PRESETS:
            raise FashionInputError(
                f"unknown tone {self.tone!r}; presets: "
                f"{sorted(TONE_PRESETS)}")
        return FashionBrief(title=clean["title"],
                            fabric_type=clean["fabric_type"],
                            season=clean["season"], notes=clean["notes"],
                            tone=tone, product_id=clean["product_id"])

    # -- deterministic derivations ---------------------------------------------

    @property
    def tone_preset(self) -> TonePreset:
        return TONE_PRESETS[self.validated().tone]

    def key(self) -> str:
        """Deterministic entity key (idempotency identity of the brief).

        AC-3: the request key is deterministic per product revision — the
        product id scopes it when the caller has one, and the brief facts
        keep it stable and collision-free without one.
        """
        b = self.validated()
        scope = b.product_id or "brief"
        slug = re.sub(r"\s+", "_", f"{b.season}|{b.fabric_type}|{b.title}")
        slug = slug.replace("|", "/")[:160]
        return f"fashion/{scope}/{slug}"

    def context(self) -> Dict[str, str]:
        """Canonical prompt context — the ONLY facts the model may use."""
        b = self.validated()
        preset = TONE_PRESETS[b.tone]
        facts = {
            "title": b.title, "fabric_type": b.fabric_type,
            "season": b.season, "notes": b.notes,
            "tone": preset.slug, "tone_label": preset.label_fa,
            "tone_guidance": preset.guidance_fa,
        }
        if b.product_id:
            facts["product_id"] = b.product_id
        return facts

    def entity(self) -> TaskEntity:
        return TaskEntity(kind="fashion_item", key=self.key(),
                          payload=self.context())


# --- deterministic guards -----------------------------------------------------

# Canonical facts a model must never introduce on its own (AC-4/AC-5):
# links, prices, discounts. A token that IS present in the brief (the
# seller stated it) is allowed through — the guard flags INVENTION, not
# quoting.
_INVENTED_FACT_RE = re.compile(
    r"https?://\S+|www\.\S+|t\.me/\S+"
    r"|\d[\d,٬.]*\s*(?:تومان|ریال)"
    r"|[$€]\s*\d*"
    r"|\d+\s*(?:%|٪|درصد)"
    r"|کد\s*تخفیف|تخفیف\S*",
    re.IGNORECASE)


def _iter_strings(node, path: str = "$"):
    if isinstance(node, str):
        yield path, node
    elif isinstance(node, dict):
        for k, v in node.items():
            yield from _iter_strings(v, f"{path}.{k}")
    elif isinstance(node, (list, tuple)):
        for i, v in enumerate(node):
            yield from _iter_strings(v, f"{path}[{i}]")


def check_invented_facts(payload: Dict, entity: TaskEntity,
                         channel: str) -> List[str]:
    """Flag price/link/discount tokens the model invented (Class B).

    A token found in the brief context is the merchant's own fact and
    passes; anything else is a hallucinated canonical value.
    """
    source = json.dumps(entity.payload or {}, ensure_ascii=False).lower()
    div: List[str] = []
    for path, text in _iter_strings(payload):
        for match in _INVENTED_FACT_RE.finditer(text):
            token = match.group(0).strip()
            if token.lower() not in source:
                div.append(
                    f"{channel}: {path} introduces {token!r} which is not "
                    "in the brief — price/link/discount are canonical "
                    "facts, never model-authored (AC-4/AC-5)")
    return div


def telegram_render(announcement: str, hashtags: List[str],
                    cta: str = "") -> str:
    """The exact text the D-073 publisher would send (deterministic)."""
    parts = [announcement.strip()]
    if cta:
        parts.append(cta.strip())
    if hashtags:
        parts.append(" ".join(hashtags))
    return "\n\n".join(p for p in parts if p)


def default_template_engine() -> TemplateEngine:
    """Engine over the shipped registry, resolved from THIS file (never
    from the process CWD)."""
    root = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "templates")
    return TemplateEngine(TemplateRegistry(root))


# --- channel tasks ------------------------------------------------------------


class _FashionChannelTask(AiTask):
    """Shared plumbing: template rendering + the deterministic guards."""

    channel = ""
    template_id = ""

    def __init__(self, router: ModelRouter, lifecycle=None,
                 template_engine: Optional[TemplateEngine] = None):
        super().__init__(router)
        self._lifecycle = lifecycle
        self.templates = template_engine or default_template_engine()

    # -- D-067 request rendering ----------------------------------------------

    def _build_request(self, entity: TaskEntity) -> AiRequest:
        facts = {k: str(v) for k, v in (entity.payload or {}).items()}
        tone = (facts.get("tone") or DEFAULT_TONE).strip().lower()
        preset = TONE_PRESETS.get(tone) or TONE_PRESETS[DEFAULT_TONE]
        ctx = dict(facts)
        ctx.update({
            "tone": preset.slug, "tone_label": preset.label_fa,
            "tone_guidance": preset.guidance_fa,
            "notes": facts.get("notes", ""),
            "context": json.dumps(facts, ensure_ascii=False, sort_keys=True),
        })
        base = AiRequest(
            task_type=self.task_type, schema_id=self.schema_id,
            prompt_payload={
                "entity_kind": entity.kind, "entity_key": entity.key,
                "title": facts.get("title", ""),
                "fabric_type": facts.get("fabric_type", ""),
                "season": facts.get("season", ""),
                "tone": preset.slug,
                "notes": facts.get("notes", ""),
            },
            idempotency_tag=f"{self.task_type}|{entity.key}|{preset.slug}")
        return render_into_request(base, self.templates, self.template_id,
                                   ctx)

    # -- shared divergence ----------------------------------------------------

    def _vocabulary_divergence(self, payload: Dict) -> List[str]:
        return check_hashtag_vocabulary(payload.get("hashtags") or [],
                                        channel=self.channel)

    def _check_divergence(self, proposal, entity: TaskEntity) -> List[str]:
        payload = proposal.payload or {}
        div = self._vocabulary_divergence(payload)
        div += check_invented_facts(payload, entity, self.channel)
        return div


class FashionInstagramCaptionTask(_FashionChannelTask, CaptionTask):
    """Instagram caption (tone presets) on the APPROVED caption channel.

    Subclasses the Phase 7 `CaptionTask` (same task_type + contract) and
    only adds: template rendering + the tone preset. The vocabulary
    guard is the shared one, so the caption rule cannot fork.
    """

    channel = "instagram_caption"
    task_type = CHANNELS["instagram_caption"]["task_type"]
    schema_id = CHANNELS["instagram_caption"]["schema_id"]
    template_id = CHANNELS["instagram_caption"]["template_id"]

    def __init__(self, router: ModelRouter, lifecycle=None,
                 product_attrs: Optional[Dict[str, Dict]] = None,
                 template_engine: Optional[TemplateEngine] = None):
        _FashionChannelTask.__init__(self, router, lifecycle=lifecycle,
                                     template_engine=template_engine)
        self.product_attrs = dict(product_attrs or {})


class FashionTelegramTask(_FashionChannelTask):
    """Telegram channel announcement, capped to the D-073 channel limit."""

    channel = "telegram_announcement"
    task_type = CHANNELS["telegram_announcement"]["task_type"]
    schema_id = CHANNELS["telegram_announcement"]["schema_id"]
    template_id = CHANNELS["telegram_announcement"]["template_id"]

    def _check_divergence(self, proposal, entity: TaskEntity) -> List[str]:
        div = super()._check_divergence(proposal, entity)
        payload = proposal.payload or {}
        rendered = telegram_render(
            payload.get("announcement_fa", ""),
            payload.get("hashtags") or [],
            payload.get("cta_fa", ""))
        if len(rendered) > TELEGRAM_TEXT_MAX:
            div.append(
                f"{self.channel}: rendered text is {len(rendered)} chars, "
                f"over the channel cap {TELEGRAM_TEXT_MAX} (D-073) — the "
                "publisher would refuse it")
        return div


class FashionSeoTask(_FashionChannelTask):
    """SEO meta description + web copy for the storefront."""

    channel = "seo_copy"
    task_type = CHANNELS["seo_copy"]["task_type"]
    schema_id = CHANNELS["seo_copy"]["schema_id"]
    template_id = CHANNELS["seo_copy"]["template_id"]

    def _vocabulary_divergence(self, payload: Dict) -> List[str]:
        # SEO keywords are hashtag-shaped identifiers of the same
        # human-owned vocabulary — same rule, no fork.
        return check_hashtag_vocabulary(payload.get("seo_keywords") or [],
                                        channel=self.channel,
                                        noun="keyword")


_TASK_CLASSES = {
    "instagram_caption": FashionInstagramCaptionTask,
    "telegram_announcement": FashionTelegramTask,
    "seo_copy": FashionSeoTask,
}


# --- engine -------------------------------------------------------------------


@dataclass
class CopyPack:
    """One brief → all three channels (one report per channel)."""

    brief: FashionBrief
    mode: str
    reports: Dict[str, TaskReport] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return bool(self.reports) and all(r.ok for r in self.reports.values())

    def channel(self, name: str) -> Optional[Dict]:
        rep = self.reports.get(name)
        return rep.proposal.payload if rep and rep.proposal else None

    def to_dict(self) -> Dict:
        return {
            "brief": self.brief.context(), "mode": self.mode,
            "ok": self.ok,
            "channels": {k: v.to_dict() for k, v in self.reports.items()},
        }


class FashionCopywritingEngine:
    """§4.1 copywriting pipeline — provider-agnostic, HITL-bound."""

    def __init__(self, router: ModelRouter, *, lifecycle=None,
                 template_engine: Optional[TemplateEngine] = None,
                 product_attrs: Optional[Dict[str, Dict]] = None):
        self.router = router
        self.lifecycle = lifecycle
        self.templates = template_engine or default_template_engine()
        self.product_attrs = dict(product_attrs or {})
        self._tasks: Dict[str, AiTask] = {}
        for name in CHANNEL_ORDER:
            cls = _TASK_CLASSES[name]
            if name == "instagram_caption":
                self._tasks[name] = cls(self.router,
                                        lifecycle=self.lifecycle,
                                        product_attrs=self.product_attrs,
                                        template_engine=self.templates)
            else:
                self._tasks[name] = cls(self.router,
                                        lifecycle=self.lifecycle,
                                        template_engine=self.templates)

    # -- introspection ---------------------------------------------------------

    def task(self, channel: str) -> AiTask:
        if channel not in self._tasks:
            raise FashionInputError(
                f"unknown channel {channel!r}; channels: "
                f"{list(CHANNEL_ORDER)}")
        return self._tasks[channel]

    def preview_prompts(self, brief: FashionBrief) -> Dict[str, Dict]:
        """Rendered prompts per channel (no dispatch, no spend)."""
        entity = brief.validated().entity()
        out: Dict[str, Dict] = {}
        for name in CHANNEL_ORDER:
            req = self._tasks[name]._build_request(entity)
            out[name] = {
                "task_type": req.task_type, "schema_id": req.schema_id,
                "template_id": req.prompt_payload.get("template_id"),
                "template_hash": req.prompt_payload.get("template_hash"),
                "prompt": req.prompt_payload.get("prompt"),
            }
        return out

    # -- generation ------------------------------------------------------------

    def generate(self, channel: str, brief: FashionBrief, *,
                 mode: str = "dry-run",
                 actor: str = "ai-runtime") -> TaskReport:
        """Run ONE channel. Persist mode lands a PROPOSED HITL item."""
        task = self.task(channel)
        return task.run(brief.validated().entity(), mode=mode, actor=actor)

    def generate_pack(self, brief: FashionBrief, *, mode: str = "dry-run",
                      actor: str = "ai-runtime") -> CopyPack:
        """Run all three channels for one brief (deterministic order)."""
        clean = brief.validated()
        pack = CopyPack(brief=clean, mode=mode)
        entity = clean.entity()
        for name in CHANNEL_ORDER:
            pack.reports[name] = self._tasks[name].run(
                entity, mode=mode, actor=actor)
        return pack


__all__ = [
    "CHANNELS",
    "CHANNEL_ORDER",
    "CopyPack",
    "DEFAULT_TONE",
    "FashionBrief",
    "FashionCopywritingEngine",
    "FashionInputError",
    "FashionInstagramCaptionTask",
    "FashionSeoTask",
    "FashionTelegramTask",
    "TONE_PRESETS",
    "TonePreset",
    "check_invented_facts",
    "default_template_engine",
    "telegram_render",
]

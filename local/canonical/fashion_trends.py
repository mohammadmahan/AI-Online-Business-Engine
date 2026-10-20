"""Phase 4 §4.2 — Trend & Hashtag Intelligence (D-172 / roadmap §4.2).

Roadmap §4.2 asks for ONE thing:

    auto-generation of TARGETED NICHE fashion hashtags based on
    garment category and season

so this module takes a structured ``TrendBrief``

    garment_category + season (+ optional fabric_type, raw notes,
    product_id)

and produces a ``trend_hashtag_set.v1`` proposal whose tags are split
into three groups — ``category_tags``, ``season_tags``, ``niche_tags``.

The groups are not decoration. They are what makes "based on garment
category and season" a CHECKED property instead of a hope in the prompt:

  - the three groups must PARTITION ``hashtags`` (disjoint, identical
    union) — a model cannot quietly drop or duplicate a tag;
  - ``category_tags`` must contain the merchant's OWN category and
    ``season_tags`` the merchant's OWN season, compared after
    deterministic normalisation (D-172 §4.2 grounding);
  - every tag passes the ONE shared ``check_hashtag_vocabulary`` guard
    (D-029/D-031/D-032) — new vocabulary stays human-owned;
  - the invented-facts guard (AC-4/AC-5, reused from §4.1, never
    forked) flags a price, link or discount token that the brief never
    stated.

Design constraints inherited from §4.1 (nothing re-implemented):

  - D-045/D-062: dispatch ONLY through the M1 ModelRouter → AiProvider
    boundary (`fashion_trend_hashtags` routing key). No provider name,
    no HTTP client, no credential — locally the mock provider answers,
    and a real adapter is a drop-in on the SAME key.
  - D-067: the prompt is rendered from the versioned template
    `fashion_trend_hashtags`; the request carries template_id +
    template_hash so any tag set is reproducible from (brief, template).
  - D-062/D-052: output is validated against the strict contract BEFORE
    anything durable exists; a violation is Class B, never repaired.
  - D-158/D-050: persist mode lands the set as a PROPOSED item through
    the M2 ProposalLifecycle (D-027 event + D-026 provenance + HITL
    queue). There is NO publication surface: hashtags are copy, and
    publishing is Phase 5.

dry-run is the default and persists nothing.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Dict, List, Optional

from canonical.ai_runtime import AiRequest, ModelRouter
from canonical.ai_tasks import (AiTask, TaskEntity, TaskReport,
                                check_hashtag_vocabulary)
from canonical.ai_templates import (TemplateEngine, render_into_request)
from canonical.fashion_copy import check_invented_facts, default_template_engine

# --- channel identity (§4.2) --------------------------------------------------

CHANNEL = "fashion_trend_hashtags"
TASK_TYPE = "fashion_trend_hashtags"
SCHEMA_ID = "trend_hashtag_set.v1"
TEMPLATE_ID = "fashion_trend_hashtags"

# the three groups, in the order the guard walks them
GROUP_KEYS = ("category_tags", "season_tags", "niche_tags")

MIN_TAGS = 5
MAX_TAGS = 30


class TrendInputError(ValueError):
    """Invalid brief (missing/oversized field) — Class B, refused before
    any dispatch. The model is never asked to fill in what the merchant
    must state: without a category and a season there is no targeting.
    """

    failure_class = "B"


# --- deterministic tag identity -----------------------------------------------

_TAG_SEPARATORS = re.compile(r"[\s\u200c\u200e\u200f\-]+")


def normalize_tag(value) -> str:
    """Deterministic tag identity: strip '#', collapse separators to '_'.

    ZWNJ and the RTL marks are separators on purpose — 'مانتو‌پاییزی'
    and 'مانتو پاییزی' are the SAME hashtag, so a model cannot ship
    both as if they were two tags.
    """
    token = str(value or "").strip().lstrip("#").strip()
    token = _TAG_SEPARATORS.sub("_", token)
    return token.strip("_").lower()


# --- brief model --------------------------------------------------------------


@dataclass(frozen=True)
class TrendBrief:
    """Structured trend input (§4.2).

    `garment_category` and `season` are the merchant's canonical facts —
    they are anchored literally and never invented or widened by the
    model. `notes` is the seller's raw unstructured text.
    """

    garment_category: str
    season: str
    fabric_type: str = ""
    notes: str = ""
    product_id: str = ""

    def validated(self) -> "TrendBrief":
        """Return a normalized copy or raise TrendInputError (Class B)."""
        clean: Dict[str, str] = {}
        for name, raw, lo, hi in (
                ("garment_category", self.garment_category, 2, 60),
                ("season", self.season, 1, 40),
                ("fabric_type", self.fabric_type or "", 0, 60),
                ("notes", self.notes or "", 0, 2000),
                ("product_id", self.product_id or "", 0, 64),
        ):
            if not isinstance(raw, str):
                raise TrendInputError(
                    f"trend.{name} must be a string, got "
                    f"{type(raw).__name__}")
            value = raw.strip()
            if len(value) < lo:
                raise TrendInputError(
                    f"trend.{name} is required (min {lo} chars)")
            if len(value) > hi:
                raise TrendInputError(
                    f"trend.{name} exceeds {hi} chars ({len(value)})")
            clean[name] = value
        # a category/season of separators only (" ء ") carries no fact
        if not normalize_tag(clean["garment_category"]):
            raise TrendInputError(
                "trend.garment_category must contain at least one tag "
                "character")
        if not normalize_tag(clean["season"]):
            raise TrendInputError(
                "trend.season must contain at least one tag character")
        return TrendBrief(**clean)

    # -- deterministic derivations ---------------------------------------------

    def key(self) -> str:
        """Deterministic entity key (idempotency identity of the brief).

        AC-3: the request key is deterministic per product revision —
        the product id scopes it when the caller has one, and the
        category/season keep it stable and collision-free without one.
        """
        b = self.validated()
        scope = b.product_id or "brief"
        season = re.sub(r"\s+", "_", b.season).replace("/", "_")[:60]
        category = re.sub(r"\s+", "_",
                          b.garment_category).replace("/", "_")[:80]
        parts = [season, category]
        if b.fabric_type:
            parts.append(re.sub(r"\s+", "_",
                                b.fabric_type).replace("/", "_")[:60])
        return f"fashion-trend/{scope}/" + "/".join(parts)

    def context(self) -> Dict[str, str]:
        """Canonical prompt context — the ONLY facts the model may use."""
        b = self.validated()
        facts = {
            "garment_category": b.garment_category,
            "season": b.season,
            "fabric_type": b.fabric_type,
            "notes": b.notes,
        }
        if b.product_id:
            facts["product_id"] = b.product_id
        return facts

    def entity(self) -> TaskEntity:
        return TaskEntity(kind="fashion_trend", key=self.key(),
                          payload=self.context())


# --- deterministic guards -----------------------------------------------------


def check_hashtag_set(payload: Dict, entity: TaskEntity,
                      channel: str = CHANNEL) -> List[str]:
    """The §4.2 guard: format, partition, grounding, vocabulary, facts.

    Everything here is deterministic and Class B — a tag set that does
    not target the merchant's own category and season is never
    persisted, and nothing is repaired on the model's behalf.
    """
    div: List[str] = []
    tags = list(payload.get("hashtags") or [])
    groups = {name: list(payload.get(name) or []) for name in GROUP_KEYS}

    # 1. count bounds (defense-in-depth: the contract already pins them)
    if not MIN_TAGS <= len(tags) <= MAX_TAGS:
        div.append(
            f"{channel}: {len(tags)} hashtags, outside the {MIN_TAGS}–"
            f"{MAX_TAGS} range")

    # 2. per-tag format: no '#', no inner whitespace, real characters
    for tag in tags:
        raw = str(tag or "")
        token = normalize_tag(raw)
        if "#" in raw.strip().lstrip("#"):
            div.append(
                f"{channel}: {raw!r} contains a '#' — tags are stored "
                "unhashed and rendered once by the composer")
        if any(ch.isspace() for ch in raw.strip()):
            div.append(
                f"{channel}: {raw!r} contains whitespace — a hashtag is "
                "one unbroken token (use '_' instead)")
        if not token:
            div.append(f"{channel}: empty hashtag {raw!r}")
        elif len(token) < 2:
            div.append(f"{channel}: hashtag {raw!r} is too short")
        elif len(token) > 60:
            div.append(f"{channel}: hashtag {raw!r} exceeds 60 chars")

    # 3. duplicates in the PUBLISHED list
    union = [tag for name in GROUP_KEYS for tag in groups[name]]
    union_norm = [normalize_tag(tag) for tag in union]
    tags_norm = [normalize_tag(tag) for tag in tags]
    dupes = sorted({t for t in tags_norm if tags_norm.count(t) > 1})
    if dupes:
        div.append(
            f"{channel}: duplicate hashtags {dupes} — every hashtag "
            "appears exactly once, in exactly one group")
    if len(tags_norm) != len(union_norm):
        div.append(
            f"{channel}: {len(tags_norm)} hashtags but the three groups "
            f"hold {len(union_norm)} — the groups must account for every "
            "tag exactly once")
    dupes = sorted({t for t in union_norm if union_norm.count(t) > 1})
    if dupes:
        div.append(
            f"{channel}: duplicate hashtags {dupes} across the groups")

    # 4. partition integrity: union(groups) == hashtags, disjoint
    if sorted(set(union_norm)) != sorted(set(tags_norm)):
        missing = sorted(set(union_norm) - set(tags_norm))
        extra = sorted(set(tags_norm) - set(union_norm))
        div.append(
            f"{channel}: the three groups do not partition `hashtags` "
            f"(ungrouped={extra}, not-listed={missing})")
    if len(union) != len(set(union_norm)):
        div.append(
            f"{channel}: a hashtag appears in more than one group")

    # 5. GROUNDING — the whole point of §4.2
    category = normalize_tag((entity.payload or {}).get("garment_category"))
    season = normalize_tag((entity.payload or {}).get("season"))
    category_pool = {normalize_tag(t) for t in groups["category_tags"]}
    season_pool = {normalize_tag(t) for t in groups["season_tags"]}
    if category and category not in category_pool:
        div.append(
            f"{channel}: category_tags never contains the merchant's own "
            f"category {category!r} — the set is not targeted "
            "(roadmap §4.2)")
    if season and season not in season_pool:
        div.append(
            f"{channel}: season_tags never contains the merchant's own "
            f"season {season!r} — the set is not seasonal "
            "(roadmap §4.2)")

    # 6. shared human-owned vocabulary (ONE rule, no fork). The
    # merchant's own category/season/fabric are stated FACTS, so they
    # are allowed verbatim — the guard exists to stop the MODEL from
    # minting vocabulary, not to police the seller's own words.
    facts = entity.payload or {}
    allow: List[str] = []
    for value in (facts.get("garment_category"), facts.get("season"),
                  facts.get("fabric_type")):
        if str(value or "").strip():
            allow.append(str(value).strip())
            allow.append(normalize_tag(value))
    div += check_hashtag_vocabulary(tags, channel=channel, allow=allow)
    # 7. invented canonical facts (AC-4/AC-5 — reused, never forked)
    div += check_invented_facts(payload, entity, channel)
    return div


# --- task ---------------------------------------------------------------------


class FashionTrendHashtagTask(AiTask):
    """§4.2: one targeted hashtag set per (category, season) brief."""

    task_type = TASK_TYPE
    schema_id = SCHEMA_ID

    def __init__(self, router: ModelRouter, lifecycle=None,
                 template_engine: Optional[TemplateEngine] = None):
        super().__init__(router)
        self._lifecycle = lifecycle
        self.templates = template_engine or default_template_engine()

    def _build_request(self, entity: TaskEntity) -> AiRequest:
        facts = {k: str(v) for k, v in (entity.payload or {}).items()}
        ctx = dict(facts)
        ctx["context"] = json.dumps(facts, ensure_ascii=False,
                                    sort_keys=True)
        base = AiRequest(
            task_type=self.task_type, schema_id=self.schema_id,
            prompt_payload={
                "entity_kind": entity.kind, "entity_key": entity.key,
                "garment_category": facts.get("garment_category", ""),
                "season": facts.get("season", ""),
                "fabric_type": facts.get("fabric_type", ""),
                "notes": facts.get("notes", ""),
            },
            idempotency_tag=f"{self.task_type}|{entity.key}")
        return render_into_request(base, self.templates, TEMPLATE_ID, ctx)

    def _check_divergence(self, proposal, entity: TaskEntity) -> List[str]:
        return check_hashtag_set(proposal.payload or {}, entity)


# --- engine -------------------------------------------------------------------


class FashionTrendEngine:
    """§4.2 trend intelligence — provider-agnostic, HITL-bound."""

    def __init__(self, router: ModelRouter, *, lifecycle=None,
                 template_engine: Optional[TemplateEngine] = None):
        self.router = router
        self.lifecycle = lifecycle
        self.templates = template_engine or default_template_engine()
        self.task = FashionTrendHashtagTask(self.router,
                                           lifecycle=self.lifecycle,
                                           template_engine=self.templates)

    # -- introspection ---------------------------------------------------------

    def preview_prompt(self, brief: TrendBrief) -> Dict:
        """Rendered prompt for one brief (no dispatch, no spend)."""
        entity = brief.validated().entity()
        req = self.task._build_request(entity)
        return {
            "task_type": req.task_type, "schema_id": req.schema_id,
            "template_id": req.prompt_payload.get("template_id"),
            "template_hash": req.prompt_payload.get("template_hash"),
            "prompt": req.prompt_payload.get("prompt"),
        }

    # -- generation ------------------------------------------------------------

    def generate(self, brief: TrendBrief, *, mode: str = "dry-run",
                 actor: str = "ai-runtime") -> TaskReport:
        """Run ONE brief. Persist mode lands a PROPOSED HITL item."""
        return self.task.run(brief.validated().entity(), mode=mode,
                             actor=actor)

    def generate_batch(self, briefs: List[TrendBrief], *,
                       mode: str = "dry-run",
                       actor: str = "ai-runtime") -> Dict:
        """One brief per category/season — D-063 budget discipline.

        Uses the shared AiTask.run_batch, so the batch stops at the
        first hard budget refusal and reports every item.
        """
        entities = [b.validated().entity() for b in briefs]
        summary = self.task.run_batch(entities, mode=mode, actor=actor)
        summary["all_ok"] = summary["failed"] == 0
        return summary


__all__ = [
    "CHANNEL",
    "FashionTrendEngine",
    "FashionTrendHashtagTask",
    "GROUP_KEYS",
    "MAX_TAGS",
    "MIN_TAGS",
    "SCHEMA_ID",
    "TASK_TYPE",
    "TEMPLATE_ID",
    "TrendBrief",
    "TrendInputError",
    "check_hashtag_set",
    "normalize_tag",
]

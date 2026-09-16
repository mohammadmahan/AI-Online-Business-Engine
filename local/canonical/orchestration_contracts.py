"""Phase 11 M1 — cross-platform fan-out contract (D-077).

One UNIVERSAL content representation, an arbitrary target list, and a
destination matrix binding each target to its platform transform. The
transforms are LOCAL and PURE (no I/O, no adapter, no network): an
un-adaptable target fails with Class-B before any dispatch exists —
and never touches sibling targets (independent fan-out, D-077).

Pure-function discipline (mirror of D-069/D-073 contracts): this
module imports only the two platform contract modules. The platform
PUBLISHERS are wired in orchestration_engine (M2), not here, so the
contract layer stays side-effect free and trivially testable.

Aggregate-state mapping (D-078, deterministic — consumed by M2/M3):
sub-task outcomes come from the DURABLE per-target records only.
"""

import re
from typing import Dict, List, Optional

from canonical.instagram_contracts import (
    MAX_CAPTION_CHARS as INSTAGRAM_MAX_CAPTION,
    MAX_HASHTAGS as INSTAGRAM_MAX_HASHTAGS,
    REQUIRED_ASPECT_RATIO_LABELS as INSTAGRAM_ASPECT_RATIOS,
    InstagramContractError,
    validate_publish_payload as instagram_validate,
)
from canonical.telegram_contracts import (
    MAX_MEDIA_CAPTION_CHARS as TELEGRAM_MAX_CAPTION,
    MAX_TEXT_CHARS as TELEGRAM_MAX_TEXT,
    TelegramContractError,
    validate_publish_payload as telegram_validate,
)

SOURCE_SYSTEM = "orchestration"
OP_QUEUE = "queue_fanout"
OP_DISPATCH = "dispatch_fanout"
OP_SUBTASK = "subtask_outcome"

KNOWN_TARGETS = ("instagram", "telegram")

AGGREGATE_STATES = ("PENDING", "ROUTED", "DISPATCHING",
                    "SUCCESS", "PARTIAL_SUCCESS", "FAILED", "CANCELLED")

# Sub-task outcomes considered terminal for aggregation. These mirror
# the real outcome vocabulary of the Phase 9/10 publishers.
SUBTASK_PUBLISHED = "published"
SUBTASK_FAILED = ("terminal_reject", "rejected_class_b",
                  "retries_exhausted", "chat_unreachable",
                  "token_expired", "queue_frozen")
SUBTASK_CANCELLED = "cancelled"
SUBTASK_IN_FLIGHT = ("in_progress", "retry_scheduled",
                     "transient_error", "cooldown",
                     "duplicate_publish_blocked")

UNIVERSAL_REQUIRED = ("job_id", "campaign_id", "content_id", "targets",
                      "scheduled_slot")


class OrchestrationContractError(ValueError):
    """Class-B carrier: local contract violation — never dispatched."""

    failure_class = "B"


def _req_str(payload: Dict, key: str) -> str:
    v = payload.get(key)
    if not isinstance(v, str) or not v.strip():
        raise OrchestrationContractError(
            f"{key} must be a non-empty string (D-077)")
    return v.strip()


def validate_dispatch_payload(payload: Dict) -> Dict:
    """Validate + normalize the universal fan-out payload (D-077).

    Pure/local: raises OrchestrationContractError (Class-B) on any
    violation BEFORE a job is enqueued. Returns a normalized dict.
    """
    if not isinstance(payload, dict):
        raise OrchestrationContractError(
            "fan-out payload must be a dict (D-077)")
    for key in UNIVERSAL_REQUIRED:
        if key not in payload or payload[key] in (None, ""):
            raise OrchestrationContractError(
                f"fan-out payload missing {key} (D-077)")
    job_id = _req_str(payload, "job_id")
    if not re.fullmatch(r"[A-Za-z0-9._-]{3,120}", job_id):
        raise OrchestrationContractError(
            "job_id must match [A-Za-z0-9._-]{3,120} (D-077)")
    norm: Dict = {
        "job_id": job_id,
        "campaign_id": _req_str(payload, "campaign_id"),
        "content_id": _req_str(payload, "content_id"),
        "scheduled_slot": _req_str(payload, "scheduled_slot"),
        "text": str(payload.get("text") or ""),
        "hashtags": _hashtags(payload.get("hashtags")),
        "media": _media(payload.get("media")),
        "target_params": _target_params(payload.get("target_params")),
        "release_at": payload.get("release_at") or None,
        "stagger_s": _stagger(payload.get("stagger_s")),
    }
    norm["targets"] = _targets(payload["targets"])
    # D-079 coordinated anti-race identity: deterministic function of
    # the content being fanned out + its release window — two workers
    # routing the same job compute the SAME key, so the lock decides.
    import hashlib
    key_material = "\x1f".join([
        "orchestration-fanout-v1", norm["job_id"], norm["campaign_id"],
        norm["content_id"], norm["scheduled_slot"],
        ",".join(norm["targets"]),
    ])
    norm["fanout_key"] = hashlib.sha256(
        key_material.encode("utf-8")).hexdigest()
    return norm


def _targets(raw) -> List[str]:
    if not isinstance(raw, (list, tuple)) or not raw:
        raise OrchestrationContractError(
            "targets must be a non-empty list (D-077)")
    seen: List[str] = []
    for t in raw:
        t = str(t).strip().lower()
        if t not in KNOWN_TARGETS:
            raise OrchestrationContractError(
                f"target {t!r} not in the destination matrix "
                f"{list(KNOWN_TARGETS)} (D-077)")
        if t not in seen:
            seen.append(t)  # dedupe, dispatch order preserved
    return seen


def _hashtags(raw) -> List[str]:
    if raw in (None, ""):
        return []
    if not isinstance(raw, (list, tuple)):
        raise OrchestrationContractError(
            "hashtags must be a list (D-077)")
    out: List[str] = []
    for h in raw:
        h = str(h).strip().lstrip("#").strip()
        if not h:
            continue
        if not re.fullmatch(r"[A-Za-z0-9_\u0600-\u06FF]{1,60}", h):
            raise OrchestrationContractError(
                f"invalid hashtag {h!r} (D-077)")
        if h not in out:
            out.append(h)
    return out


def _media(raw) -> Optional[Dict]:
    if raw in (None, ""):
        return None
    if not isinstance(raw, dict):
        raise OrchestrationContractError("media must be a dict (D-077)")
    kind = str(raw.get("kind") or "").strip().lower()
    if kind not in ("photo", "video", "document", "none"):
        raise OrchestrationContractError(
            "media.kind must be photo|video|document|none (D-077)")
    if kind == "none":
        return {"kind": "none"}
    bh = str(raw.get("bytes_hash") or "").strip()
    if not re.fullmatch(r"[0-9a-f]{64}", bh):
        raise OrchestrationContractError(
            "media.bytes_hash must be a sha256 hex digest (D-077)")
    out = {"kind": kind, "bytes_hash": bh}
    if kind in ("photo", "video"):
        ratio = str(raw.get("aspect_ratio") or "").strip()
        if ratio and ratio not in INSTAGRAM_ASPECT_RATIOS:
            raise OrchestrationContractError(
                f"media.aspect_ratio {ratio!r} not in "
                f"{sorted(INSTAGRAM_ASPECT_RATIOS)} (D-077)")
        out["aspect_ratio"] = ratio or None
    if raw.get("file_size_bytes") is not None:
        out["file_size_bytes"] = int(raw["file_size_bytes"])
    return out


def _target_params(raw) -> Dict[str, Dict]:
    if raw in (None, ""):
        return {}
    if not isinstance(raw, dict):
        raise OrchestrationContractError(
            "target_params must be a dict of target → params (D-077)")
    out: Dict[str, Dict] = {}
    for t, params in raw.items():
        t = str(t).strip().lower()
        if t not in KNOWN_TARGETS:
            raise OrchestrationContractError(
                f"target_params target {t!r} unknown (D-077)")
        if not isinstance(params, dict):
            raise OrchestrationContractError(
                f"target_params[{t}] must be a dict (D-077)")
        out[t] = dict(params)
    return out


def _stagger(raw) -> Dict[str, float]:
    if raw in (None, ""):
        return {}
    if not isinstance(raw, dict):
        raise OrchestrationContractError(
            "stagger_s must be a dict of target → seconds (D-079)")
    out: Dict[str, float] = {}
    for t, s in raw.items():
        t = str(t).strip().lower()
        if t not in KNOWN_TARGETS:
            raise OrchestrationContractError(
                f"stagger_s target {t!r} unknown (D-079)")
        try:
            s = float(s)
        except (TypeError, ValueError):
            raise OrchestrationContractError(
                f"stagger_s[{t}] must be a number (D-079)")
        if s < 0:
            raise OrchestrationContractError(
                f"stagger_s[{t}] must be >= 0 (D-079)")
        out[t] = s
    return out


# --- D-079 coordinated release window -----------------------------------


def release_plan(norm: Dict) -> Dict[str, str]:
    """Deterministic per-target dispatch slots (D-079).

    Base = release_at if given else scheduled_slot. Each target's slot
    is base + stagger_s[target] seconds (staggered simultaneous
    release). ISO-8601 in, ISO-8601 out; targets without a stagger get
    the base slot unchanged. Pure arithmetic — no wall-clock reads.
    """
    base = norm.get("release_at") or norm["scheduled_slot"]
    stagger = norm.get("stagger_s") or {}
    try:
        from datetime import datetime, timedelta, timezone
        t0 = datetime.fromisoformat(base.replace("Z", "+00:00"))
        if t0.tzinfo is None:
            t0 = t0.replace(tzinfo=timezone.utc)
        plan: Dict[str, str] = {}
        for t in norm["targets"]:
            plan[t] = (t0 + timedelta(
                seconds=float(stagger.get(t, 0.0)))).isoformat()
        return plan
    except ValueError as exc:
        raise OrchestrationContractError(
            f"release window base slot unparsable: {exc} (D-079)") from exc


# --- platform transforms ------------------------------------------------


def _caption_with_hashtags(text: str, hashtags: List[str]) -> str:
    parts = [text.rstrip()] if text.strip() else []
    tags = ["#" + h for h in hashtags
            if "#" + h not in (text or "")]
    if tags:
        parts.append(" ".join(tags))
    return "\n".join(parts).strip()


def _truncate(s: str, limit: int) -> str:
    return s if len(s) <= limit else s[:limit].rstrip()


def transform_for_instagram(payload: Dict) -> Dict:
    """Universal → Instagram payload (D-077 matrix row).

    Platform semantics: hashtags ≤ 30 (overage truncated deterministically,
    first-N by plan order) and caption ≤ 2200 (truncated) — each with a
    recorded warning; aspect ratio must exist for photo/video. Delegates
    final authority to the D-069 validator.
    """
    media = payload.get("media") or {}
    if media.get("kind") not in ("photo", "video"):
        raise OrchestrationContractError(
            "instagram target requires photo or video media (D-077 "
            "local prevention)")
    if not media.get("aspect_ratio"):
        raise OrchestrationContractError(
            "instagram target requires media.aspect_ratio (D-069)")
    warnings: List[str] = []
    kept = payload["hashtags"][:INSTAGRAM_MAX_HASHTAGS]
    if len(payload["hashtags"]) > INSTAGRAM_MAX_HASHTAGS:
        warnings.append(
            f"hashtags truncated to {INSTAGRAM_MAX_HASHTAGS} "
            "(D-069 limit)")
    caption = _truncate(
        _caption_with_hashtags(payload["text"], kept),
        INSTAGRAM_MAX_CAPTION)
    if len(caption) == INSTAGRAM_MAX_CAPTION and len(
            _caption_with_hashtags(payload["text"], kept)) > \
            INSTAGRAM_MAX_CAPTION:
        warnings.append(
            f"caption truncated to {INSTAGRAM_MAX_CAPTION} chars "
            "(D-069 limit)")
    adapted = {
        "content_id": payload["content_id"],
        "media_ref": f"media://{media['bytes_hash']}",
        "media_hash": media["bytes_hash"],
        "caption": caption,
        "aspect_ratio": media["aspect_ratio"],
        "scheduled_slot": payload["scheduled_slot"],
    }
    if media.get("file_size_bytes") is not None:
        adapted["file_size_bytes"] = media["file_size_bytes"]
    try:
        norm = instagram_validate(adapted)
    except InstagramContractError as exc:
        raise OrchestrationContractError(
            f"instagram adaptation rejected: {exc}") from exc
    return {"target": "instagram", "payload": norm,
            "warnings": warnings}


def transform_for_telegram(payload: Dict) -> Dict:
    """Universal → Telegram payload (D-077 matrix row).

    Platform semantics: chat_id from target_params; media none → text,
    else photo/video/document; caption ≤ 1024 (photo/video/document) or
    text ≤ 4096 — truncated with a recorded warning. Delegates final
    authority to the D-073 validator.
    """
    params = (payload.get("target_params") or {}).get("telegram") or {}
    chat_id = params.get("chat_id")
    if chat_id in (None, ""):
        raise OrchestrationContractError(
            "telegram target requires target_params.telegram.chat_id "
            "(D-073/D-077 local prevention)")
    media = payload.get("media") or {}
    kind = media.get("kind") or "none"
    if kind in ("photo", "video", "document") and \
            media.get("file_size_bytes") in (None, ""):
        raise OrchestrationContractError(
            "telegram media target requires media.file_size_bytes "
            "(D-073 local size enforcement)")
    warnings: List[str] = []
    full = _caption_with_hashtags(payload["text"], payload["hashtags"])
    if kind in ("photo", "video", "document"):
        if len(full) > TELEGRAM_MAX_CAPTION:
            warnings.append(
                f"caption truncated to {TELEGRAM_MAX_CAPTION} chars "
                "(D-073 limit)")
        adapted = {
            "chat_id": chat_id,
            "content_id": payload["content_id"],
            "kind": kind,
            "media_ref": f"media://{media['bytes_hash']}",
            "media_hash": media["bytes_hash"],
            "caption": _truncate(full, TELEGRAM_MAX_CAPTION),
            "parse_mode": params.get("parse_mode") or "",
            "scheduled_slot": payload["scheduled_slot"],
        }
        if media.get("file_size_bytes") is not None:
            adapted["file_size_bytes"] = media["file_size_bytes"]
    else:
        if len(full) > TELEGRAM_MAX_TEXT:
            warnings.append(
                f"text truncated to {TELEGRAM_MAX_TEXT} chars "
                "(D-073 limit)")
        adapted = {
            "chat_id": chat_id,
            "content_id": payload["content_id"],
            "kind": "text",
            "text": _truncate(full, TELEGRAM_MAX_TEXT),
            "parse_mode": params.get("parse_mode") or "",
            "scheduled_slot": payload["scheduled_slot"],
        }
    try:
        norm = telegram_validate(adapted)
    except TelegramContractError as exc:
        raise OrchestrationContractError(
            f"telegram adaptation rejected: {exc}") from exc
    return {"target": "telegram", "payload": norm,
            "warnings": warnings}


# D-077 destination matrix: target → adapter transform. Adding a
# platform = one row here + one publisher binding in the engine.
DESTINATION_MATRIX = {
    "instagram": transform_for_instagram,
    "telegram": transform_for_telegram,
}


def adapt_for_target(target: str, payload: Dict) -> Dict:
    """Route one target through the matrix (D-077). Pure/local."""
    fn = DESTINATION_MATRIX.get(target)
    if fn is None:
        raise OrchestrationContractError(
            f"no destination-matrix row for {target!r} (D-077)")
    return fn(payload)


# --- deterministic aggregation (D-078) ----------------------------------


def aggregate_from_subtasks(outcomes: Dict[str, str]) -> str:
    """Deterministically map sub-task outcomes → aggregate state.

    Strict mapping (D-078):
      - any in-flight / not-yet-terminal target → DISPATCHING
      - all terminal and all published → SUCCESS
      - all terminal and ≥1 published → PARTIAL_SUCCESS
      - all terminal and none published → FAILED
    `duplicate_publish_blocked` counts as PUBLISHED for aggregation:
    it means the platform vault already holds a publication for this
    exact key (retry after a crash) — re-publishing it would violate
    D-070/D-074, so the aggregate treats the target as served.
    """
    if not outcomes:
        return "PENDING"
    vals = list(outcomes.values())
    if any(v == SUBTASK_PUBLISHED or
           v == "duplicate_publish_blocked" for v in vals):
        published = sum(1 for v in vals
                        if v in (SUBTASK_PUBLISHED,
                                 "duplicate_publish_blocked"))
        if published == len(vals):
            return "SUCCESS"
        # any non-terminal sibling keeps DISPATCHING; all-terminal
        # mixed → partial success
        if all(v in SUBTASK_FAILED or v == SUBTASK_PUBLISHED or
               v == SUBTASK_CANCELLED or
               v == "duplicate_publish_blocked" for v in vals):
            return "PARTIAL_SUCCESS"
        return "DISPATCHING"
    if all(v in SUBTASK_FAILED or v == SUBTASK_CANCELLED
           for v in vals):
        return "FAILED"
    return "DISPATCHING"

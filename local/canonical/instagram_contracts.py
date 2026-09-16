"""Phase 9 M1 — Instagram media & publishing contract (D-069).

The Meta Graph API two-step async container workflow as an explicit
state machine, plus LOCAL pre-dispatch validators. Class-B local
prevention: an invalid payload is rejected before a single network
call (D-069) — validators are pure functions with zero I/O.

States (D-069):
    PENDING → MEDIA_CREATE → CONTAINER_STATUS → MEDIA_PUBLISH → PUBLISHED
    FAILED reachable from any non-terminal state; PUBLISHED/FAILED are
    terminal and immutable. Every transition is intended to be a
    durable D-027 event (the publisher records them).

Contract constants (D-069): aspect ratios {1:1, 4:5, 16:9}, caption
≤ 2200 chars, hashtags ≤ 30. Media is REFERENCED by id from the media
abstraction (D-051/D-049) — never embedded.
"""

import hashlib
import json
from typing import Dict, Optional, Tuple

# --- states -------------------------------------------------------------------

PENDING = "PENDING"
MEDIA_CREATE = "MEDIA_CREATE"
CONTAINER_STATUS = "CONTAINER_STATUS"
MEDIA_PUBLISH = "MEDIA_PUBLISH"
PUBLISHED = "PUBLISHED"
FAILED = "FAILED"

TERMINAL = (PUBLISHED, FAILED)

TRANSITIONS = {
    (PENDING, MEDIA_CREATE),
    (MEDIA_CREATE, CONTAINER_STATUS),
    (CONTAINER_STATUS, CONTAINER_STATUS),   # poll until ready (self-loop)
    (CONTAINER_STATUS, MEDIA_PUBLISH),      # container FINISHED
    (MEDIA_PUBLISH, PUBLISHED),
    (PENDING, FAILED), (MEDIA_CREATE, FAILED),
    (CONTAINER_STATUS, FAILED), (MEDIA_PUBLISH, FAILED),
}

# --- contract constants (D-069) -------------------------------------------------

ALLOWED_ASPECT_RATIOS = {(1, 1), (4, 5), (16, 9)}
MAX_CAPTION_CHARS = 2200
MAX_HASHTAGS = 30
REQUIRED_ASPECT_RATIO_LABELS = {"1:1", "4:5", "16:9"}


class InstagramContractError(ValueError):
    """Contract/state violation (Class-B, terminal reject, no retry)."""

    failure_class = "B"


def validate_transition(from_state: str, to_state: str) -> None:
    """Raise InstagramContractError on an unauthorized transition."""
    if (from_state, to_state) not in TRANSITIONS:
        raise InstagramContractError(
            f"unauthorized transition: {from_state} -> {to_state} "
            f"(D-069; legal: {sorted(TRANSITIONS)})")


def _caption_parts(caption: str) -> Tuple[str, list]:
    words = caption.split()
    hashtags = [w for w in words if w.startswith("#")]
    return caption, hashtags


def validate_publish_payload(payload: Dict) -> Dict:
    """Validate a publish payload LOCALLY (Class-B prevention).

    Required: content_id, media_ref, media_hash, caption,
    aspect_ratio ("1:1" | "4:5" | "16:9"), scheduled_slot.
    Returns a normalized dict; raises InstagramContractError otherwise.

    This is a pure function — no I/O, no adapter involvement — so an
    invalid payload can NEVER reach the network.
    """
    if not isinstance(payload, dict):
        raise InstagramContractError(
            "publish payload must be a dict (D-069)")
    required = ("content_id", "media_ref", "media_hash", "caption",
                "aspect_ratio", "scheduled_slot")
    missing = [k for k in required
               if k not in payload or payload[k] in (None, "")]
    if missing:
        raise InstagramContractError(
            f"publish payload missing {missing} (D-069)")

    content_id = str(payload["content_id"]).strip()
    if not content_id:
        raise InstagramContractError("content_id must be non-empty")
    caption = str(payload["caption"])
    if len(caption) > MAX_CAPTION_CHARS:
        raise InstagramContractError(
            f"caption exceeds {MAX_CAPTION_CHARS} chars "
            f"({len(caption)}) — local reject before dispatch")
    _, hashtags = _caption_parts(caption)
    if len(hashtags) > MAX_HASHTAGS:
        raise InstagramContractError(
            f"caption carries {len(hashtags)} hashtags; max "
            f"{MAX_HASHTAGS} — local reject before dispatch")
    ratio = str(payload["aspect_ratio"]).strip()
    if ratio not in REQUIRED_ASPECT_RATIO_LABELS:
        raise InstagramContractError(
            "aspect_ratio %r not in %s — local reject before dispatch"
            % (ratio, sorted(REQUIRED_ASPECT_RATIO_LABELS)))
    media_ref = str(payload["media_ref"]).strip()
    media_hash = str(payload["media_hash"]).strip()
    if len(media_hash) < 8:
        raise InstagramContractError(
            "media_hash must be a content hash (≥8 chars) — required "
            "for the D-070 idempotency key")
    slot = str(payload["scheduled_slot"]).strip()
    return {
        "content_id": content_id,
        "media_ref": media_ref,
        "media_hash": media_hash,
        "caption": caption,
        "caption_hash": caption_hash(caption),
        "aspect_ratio": ratio,
        "scheduled_slot": slot,
    }


def caption_hash(caption: str) -> str:
    return hashlib.sha256(caption.encode("utf-8")).hexdigest()


def publish_idempotency_key(content_id: str, media_hash: str,
                            caption_hash: str, scheduled_slot: str) -> str:
    """D-070 deterministic key: sha256(content_id, media_hash,
    caption_hash, scheduled_slot)."""
    material = "|".join((str(content_id), str(media_hash),
                         str(caption_hash), str(scheduled_slot)))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def key_from_payload(payload: Dict) -> str:
    """Derive the D-070 key from a validated payload (or raise)."""
    norm = validate_publish_payload(payload)
    return publish_idempotency_key(norm["content_id"], norm["media_hash"],
                                   norm["caption_hash"],
                                   norm["scheduled_slot"])


def parse_aspect_ratio(label: str) -> Optional[Tuple[int, int]]:
    """"4:5" → (4, 5); None if malformed. Membership against
    ALLOWED_ASPECT_RATIOS is the caller's check."""
    try:
        w, h = str(label).split(":", 1)
        return int(w), int(h)
    except (ValueError, AttributeError):
        return None


def is_allowed_ratio(label: str) -> bool:
    return parse_aspect_ratio(label) in ALLOWED_ASPECT_RATIOS

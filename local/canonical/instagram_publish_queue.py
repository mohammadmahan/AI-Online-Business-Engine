"""Phase 5 §5.2 — peak-hours Instagram publishing queue (D-172 / D-093/D-094).

The roadmap's §5.2 is two things: container publishing through the
canonical Instagram seam, and a **scheduled publishing queue for peak
customer engagement hours**. The container workflow already exists and
is REUSED, not rebuilt: `InstagramOutboxPublisher.publish()` drives
`create_media_container` → `container_status` → `publish_container`
through the injected adapter (D-069/D-072, `MockInstagramAdapter` for
offline runs, `GraphApiAdapter` behind its D-045 construction gate).

This module adds only the missing half — WHEN an accepted post goes
out — and it adds it on the same canonical seams:

    ACCEPTED social bundle                 (fashion_social_bundler)
        → peak-hours policy                (merchant-supplied windows)
        → SchedulingEngine.schedule()      (D-093/D-094 slot claim)
        → at release: outbox.enqueue()     (D-072 durable outbox)
        → the publisher's own worker sends (D-069, untouched)

Fail-closed by construction
---------------------------
  - HITL is REUSED, not re-implemented: `approved_bundle_payload()` is
    the same gate §5.1's `hand_off_to_outbox()` uses — ACCEPTED state,
    bundle schema, intact `payload_hash`, `approval.required: true` —
    and it is RE-CHECKED at release time, so a post cannot go out on a
    stale acceptance.
  - Peak windows are the MERCHANT'S numbers, passed in and validated
    (24h `HH:MM`, 15-minute aligned, ordered, non-overlapping). This
    module invents no marketing assumption and has no default window.
  - No wall clock: the caller supplies `now_iso`; slot arithmetic is
    pure and deterministic (same input → same slot), and the fixed
    UTC offset is explicit rather than a timezone database lookup.
  - No publication surface: the queue imports no adapter, opens no
    socket, reads no credential and never calls `publish()` — it only
    enqueues into the durable outbox. The publisher's vault remains the
    double-publish authority.

Scope honesty
-------------
  - "Peak hours" is a POLICY the merchant owns (e.g. Iranian evening
    traffic); hardcoding one would be a fabricated business fact.
  - The queue schedules ONE Instagram target (`targets=["instagram"]`),
    matching the §5.2 scope; Telegram keeps its D-073 path.
  - Live Graph API calls remain owner-gated (D-045); this module is
    verified against the mock adapter only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple

from canonical.fashion_social_bundler import (
    BundleNotApproved, approved_bundle_payload, proposal_id_for)
from canonical.instagram_contracts import (
    InstagramContractError, validate_publish_payload as validate_instagram)
from canonical.orchestration_contracts import KNOWN_TARGETS
from canonical.scheduling_contracts import (
    ST_DUE, ST_SCHEDULED, is_due)

POST_PREFIX = "instagram-"
CONTENT_PREFIX = "bundle-"
SLOT_MINUTES = 15
MAX_WINDOWS = 8

_HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


class PublishingQueueError(ValueError):
    """Invalid queue/policy input — Class B, refused before any write."""

    failure_class = "B"


# This module is a declared Instagram home (D-131): the literal target
# is part of the abstraction here, while the D-077 registry remains the
# source of truth for the fan-out matrix. Refuse at import if the two
# ever disagree, rather than scheduling a target the matrix rejects.
TARGET = "instagram"
if TARGET not in KNOWN_TARGETS:
    raise PublishingQueueError(
        f"{TARGET!r} is absent from the D-077 destination matrix "
        f"{list(KNOWN_TARGETS)}")


@dataclass(frozen=True)
class PeakHoursPolicy:
    """Merchant-declared engagement windows in a fixed UTC offset.

    `windows` are `(start, end)` 24h `HH:MM` pairs, START-inclusive and
    END-exclusive, aligned to the 15-minute slot granularity (D-094).
    """

    windows: Tuple[Tuple[str, str], ...]
    utc_offset_minutes: int = 210          # Iran, +03:30, no DST
    name: str = "merchant-peak-hours"

    def validated(self) -> "PeakHoursPolicy":
        if not isinstance(self.utc_offset_minutes, int) or \
                isinstance(self.utc_offset_minutes, bool):
            raise PublishingQueueError(
                "utc_offset_minutes must be an integer")
        if not -720 <= self.utc_offset_minutes <= 840:
            raise PublishingQueueError(
                "utc_offset_minutes outside the real-world range")
        windows = list(self.windows or ())
        if not windows:
            raise PublishingQueueError(
                "peak-hours windows are required — the merchant owns the "
                "engagement policy and no default is invented")
        if len(windows) > MAX_WINDOWS:
            raise PublishingQueueError(
                f"at most {MAX_WINDOWS} windows, got {len(windows)}")
        clean: List[Tuple[int, int]] = []
        for raw in windows:
            if not isinstance(raw, (tuple, list)) or len(raw) != 2:
                raise PublishingQueueError(
                    "each window must be a (start, end) pair")
            parsed = []
            for value in raw:
                if not isinstance(value, str) or not _HHMM.match(value):
                    raise PublishingQueueError(
                        f"window bound {value!r} is not 24h HH:MM")
                hh, mm = int(value[:2]), int(value[3:])
                if mm % SLOT_MINUTES:
                    raise PublishingQueueError(
                        f"window bound {value!r} is not aligned to the "
                        f"{SLOT_MINUTES}-minute slot granularity")
                parsed.append(hh * 60 + mm)
            start, end = parsed
            if start >= end:
                raise PublishingQueueError(
                    f"window {raw[0]}-{raw[1]} must start before it ends")
            clean.append((start, end))
        clean.sort()
        for (a_start, a_end), (b_start, b_end) in zip(clean, clean[1:]):
            if b_start < a_end:
                raise PublishingQueueError(
                    "peak-hours windows must not overlap")
        name = str(self.name or "").strip()
        if not name:
            raise PublishingQueueError("policy name is required")
        return PeakHoursPolicy(
            windows=tuple((f"{s // 60:02d}:{s % 60:02d}",
                           f"{e // 60:02d}:{e % 60:02d}")
                          for s, e in clean),
            utc_offset_minutes=self.utc_offset_minutes, name=name)

    @property
    def tz(self):
        return timezone(timedelta(minutes=self.utc_offset_minutes))

    @staticmethod
    def _parse(iso: str) -> datetime:
        if not isinstance(iso, str) or not iso.strip():
            raise PublishingQueueError(
                "an ISO-8601 instant with an offset is required")
        try:
            value = datetime.fromisoformat(iso.strip().replace("Z", "+00:00"))
        except ValueError as exc:
            raise PublishingQueueError(
                f"unparseable instant {iso!r}") from exc
        if value.tzinfo is None or value.utcoffset() is None:
            raise PublishingQueueError(
                f"instant {iso!r} carries no UTC offset — an instant "
                "without an offset is ambiguous")
        return value

    def _minutes(self, local: datetime) -> int:
        return local.hour * 60 + local.minute

    def is_peak(self, iso: str) -> bool:
        local = self._parse(iso).astimezone(self.tz)
        now_min = self._minutes(local)
        return any(start <= now_min < end
                   for start, end in self._int_windows())

    def _int_windows(self) -> List[Tuple[int, int]]:
        out = []
        for start, end in self.windows:
            out.append((int(start[:2]) * 60 + int(start[3:]),
                        int(end[:2]) * 60 + int(end[3:])))
        return out

    def next_slot(self, requested_iso: str) -> str:
        """The requested instant when it is inside a window; otherwise
        the NEXT window start (same day or later), in policy-local time.

        Pure function: no clock, no randomness, stable across calls.
        """
        requested = self._parse(requested_iso)
        local = requested.astimezone(self.tz).replace(microsecond=0)
        windows = self._int_windows()
        now_min = self._minutes(local)
        for start, end in windows:
            if start <= now_min < end:
                return local.isoformat()
        for day in range(0, 8):
            for start, _end in windows:
                candidate = local.replace(hour=0, minute=0, second=0) + \
                    timedelta(days=day, minutes=start)
                if candidate > local:
                    return candidate.isoformat()
        raise PublishingQueueError(
            "no peak window found within 8 days")  # unreachable: validated


class InstagramPublishQueue:
    """Durable peak-hours queue over the canonical scheduling + outbox seams."""

    def __init__(self, scheduler, outbox, peak_hours: PeakHoursPolicy,
                 *, max_per_pass: int = 50):
        if scheduler is None or outbox is None:
            raise PublishingQueueError(
                "a scheduling engine and an Instagram outbox are required")
        if not isinstance(peak_hours, PeakHoursPolicy):
            raise PublishingQueueError(
                "peak_hours must be a PeakHoursPolicy")
        self.scheduler = scheduler
        self.outbox = outbox
        self.peak_hours = peak_hours.validated()
        if not isinstance(max_per_pass, int) or \
                isinstance(max_per_pass, bool) or max_per_pass <= 0:
            raise PublishingQueueError("max_per_pass must be a positive int")
        self.max_per_pass = max_per_pass

    # -- deterministic identity ------------------------------------------------

    @staticmethod
    def post_id_for(bundle_key: str) -> str:
        key = str(bundle_key or "").strip()
        if not re.fullmatch(r"[0-9a-f]{32}", key):
            raise PublishingQueueError(
                "bundle_key must be a 32-hex digest")
        return f"{POST_PREFIX}{key}"

    @staticmethod
    def bundle_id_for(post_id: str) -> str:
        pid = str(post_id or "")
        if not pid.startswith(POST_PREFIX):
            return ""
        key = pid[len(POST_PREFIX):]
        if not re.fullmatch(r"[0-9a-f]{32}", key):
            return ""
        return proposal_id_for(key)

    # -- scheduling ------------------------------------------------------------

    def schedule_bundle(self, bundle_id: str, *, lifecycle,
                        actor: str = "instagram-queue") -> Dict:
        """Place an ACCEPTED bundle on the next peak-hours slot.

        Returns a decision dict; contract refusals raise, and a slot
        conflict is a recorded `scheduled: False` (D-094) — never a
        silent success.
        """
        _state, payload = approved_bundle_payload(lifecycle, bundle_id)
        bundle_key = str(payload.get("bundle_key", ""))
        post_id = self.post_id_for(bundle_key)
        ig = payload.get(TARGET) or {}
        try:
            validate_instagram(dict(ig))
        except InstagramContractError as exc:
            raise PublishingQueueError(
                f"stored bundle's Instagram section is not publishable: "
                f"{exc}") from exc

        requested = str(ig.get("scheduled_slot", ""))
        slot = self.peak_hours.next_slot(requested)
        post = {
            "post_id": post_id,
            "content_ref": f"{CONTENT_PREFIX}{bundle_key}",
            "targets": [TARGET],
            "scheduled_for": slot,
        }
        res = self.scheduler.schedule(post)
        if res.get("status") != ST_SCHEDULED:
            return {"scheduled": False, "post_id": post_id,
                    "bundle_id": bundle_id, "requested_slot": requested,
                    "reason": res.get("status", "refused"),
                    "conflicts": res.get("conflicts", [])}
        # the SAME instant may be re-expressed in policy-local time —
        # only a real move counts as shifted
        same_instant = (PeakHoursPolicy._parse(slot) ==
                        PeakHoursPolicy._parse(requested))
        return {"scheduled": True, "post_id": post_id,
                "bundle_id": bundle_id, "requested_slot": requested,
                "scheduled_for": slot, "shifted": not same_instant,
                "retried": bool(res.get("retried"))}

    # -- release ---------------------------------------------------------------

    def release_due(self, now_iso: str, *, lifecycle,
                    actor: str = "instagram-queue") -> Dict:
        """Enqueue every due post into the durable outbox, once.

        The acceptance is re-verified per post; a post whose bundle is
        no longer ACCEPTED is left in place and reported, never sent.
        Terminal posts are skipped, so a repeated pass is a no-op.
        """
        view = self.scheduler.calendar_view()
        due = []
        for post_id, row in view.items():
            if not post_id.startswith(POST_PREFIX):
                continue                      # foreign calendar entry
            if row.get("status") not in (ST_SCHEDULED, ST_DUE):
                continue
            if row.get("slot_conflict"):
                # D-094 rejection: the post was NEVER scheduled, so it
                # must never be released — the calendar keeps the row
                # only as the conflict record.
                continue
            if is_due(str(row.get("scheduled_for", "")), now_iso):
                due.append((str(row.get("scheduled_for", "")), post_id))
        due.sort()
        summary: Dict = {"dispatched": 0, "already_queued": 0,
                         "refused": 0, "released": [], "failures": []}
        for _slot, post_id in due[:self.max_per_pass]:
            entry = self._release_one(post_id, now_iso, lifecycle, actor)
            if entry["released"]:
                summary["released"].append(entry)
                summary["dispatched"] += 1
                if entry.get("already_queued"):
                    summary["already_queued"] += 1
            else:
                summary["refused"] += 1
                summary["failures"].append(entry)
        return summary

    def _release_one(self, post_id: str, now_iso: str, lifecycle,
                     actor: str) -> Dict:
        entry: Dict = {"post_id": post_id, "released": False}
        bundle_id = self.bundle_id_for(post_id)
        if not bundle_id:
            entry["reason"] = "unmapped_post"
            return entry
        try:
            _state, payload = approved_bundle_payload(lifecycle, bundle_id)
        except BundleNotApproved as exc:
            entry["reason"] = "not_approved"
            entry["detail"] = str(exc)
            return entry
        ig = payload.get(TARGET) or {}
        try:
            canonical = validate_instagram(dict(ig))
        except InstagramContractError as exc:
            entry["reason"] = "contract"
            entry["detail"] = str(exc)
            return entry

        state = self.scheduler.calendar_view().get(post_id, {})
        if state.get("status") == ST_SCHEDULED:
            marked = self.scheduler.mark_due(post_id, now_iso)
            if not marked.get("ok"):
                entry["reason"] = "not_due"
                entry["detail"] = marked.get("reason", "")
                return entry
        elif state.get("status") != ST_DUE:
            entry["reason"] = f"terminal_{state.get('status', 'unknown')}"
            return entry

        try:
            queued = self.outbox.enqueue(canonical, actor=actor)
        except Exception as exc:  # noqa: BLE001 — per-post refusal
            entry["reason"] = "outbox_refused"
            entry["detail"] = f"{type(exc).__name__}: {str(exc)[:160]}"
            return entry
        sealed = self.scheduler.mark_dispatched(
            post_id, actor,
            {"publish_key": queued.get("publish_key", ""),
             "queued": bool(queued.get("queued"))})
        entry.update({
            "released": True,
            "bundle_id": bundle_id,
            "publish_key": queued.get("publish_key", ""),
            "already_queued": not bool(queued.get("queued")),
            "recorded": bool(sealed.get("ok")),
        })
        if not sealed.get("ok"):
            entry["record_detail"] = sealed.get("reason", "")
        return entry

    # -- operator surface ------------------------------------------------------

    def cancel(self, post_id: str, actor: str) -> Dict:
        if not self.bundle_id_for(post_id):
            return {"cancelled": False, "reason": "foreign_post"}
        res = self.scheduler.cancel(post_id, actor)
        return {"cancelled": bool(res.get("ok")),
                "status": res.get("status", res.get("current", "")),
                "reason": res.get("reason", "")}

    def calendar(self) -> Dict[str, Dict]:
        return {pid: row for pid, row in self.scheduler.calendar_view().items()
                if pid.startswith(POST_PREFIX)}


__all__ = [
    "CONTENT_PREFIX",
    "InstagramPublishQueue",
    "MAX_WINDOWS",
    "POST_PREFIX",
    "PeakHoursPolicy",
    "PublishingQueueError",
    "SLOT_MINUTES",
    "TARGET",
]

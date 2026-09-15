"""Notion provider-neutral adapter + polling engine (Phase 6 M3).

Provider-neutral ingestion boundary (RULES §35 — the mock-Woo pattern):
a `NotionProvider` interface defines everything the polling engine and
the ingestion path may know about the source system; `MockNotionAdapter`
is the local implementation (D-053 local-first). The future live Notion
API adapter is a drop-in `NotionProvider` replacement: it must map raw
API pages into the same `NotionEvent` shape and — per D-060 — feed the
verified source field into `NOTION_REVISION_MARKER_FIELDS` (one
constant edit, zero structural rewrites).

All Notion-domain knowledge stays behind the boundary. Downstream
canonical components (`notion_contracts`, `notion_ingest`, the D-027
store) never import anything from this module, never see Notion API
shapes, and know only the abstract "source system" concept.

Polling model (event-generation, deterministic):

    poll cycle
      → provider.fetch_events(since=None, page_ids=None, batch_size=…)
      → engine validates each batch result structurally (adapter error
        boundary — a malformed batch can never crash the daemon)
      → engine converts one NotionEvent per cycle per page
      → canonical.notion_ingest.ingest_notion_event() (D-027 store,
        D-060 key, lifecycle validation, D-026 provenance, HITL on B/E)

Idempotency across cycles: per page the engine keeps the last emitted
revision marker; a page whose current marker equals the last EMITTED
one is unchanged → no event (nothing for the store to dedupe — cheaper
than skipped_duplicate by construction). A changed marker yields an
event whose D-060 key differs, so the store treats it as a new logical
event. Cycles never mutate provider state.

Engine state: the cursor file is runtime state (gitignored, like the
Woo sync-engine state under local/volumes/) — never committed.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional

from canonical.notion_ingest import (
    ingest_notion_event,
)


class AdapterErrorBoundary(Exception):
    """A malformed adapter output was captured (never crashes the daemon).

    Carries a structured record: {"error": type-name, "detail": …,
    "index": position in batch (when known)}.
    """

    def __init__(self, detail: str, *, error: str, index: Optional[int] = None,
                 payload=None):
        super().__init__(detail)
        self.record = {"error": str(error), "detail": str(detail)[:300]}
        if index is not None:
            self.record["index"] = index
        if payload is not None:
            self.record["payload"] = payload


@dataclass(frozen=True)
class NotionEvent:
    """The ONLY event shape that crosses the provider boundary.

    `marker` is the source-provided revision identifier (D-060: never
    wall-clock). `raw` carries provider-specific extras; ingestion-relevant
    fields are explicit. `page_kind` is the entity type string used by the
    mock payloads ('content_idea' | 'campaign' | 'incident').
    """

    page_id: str
    page_kind: str
    marker: str
    last_edited_time: Optional[str] = None  # change-detection metadata only
    raw: Dict = field(default_factory=dict)

    def to_payload(self, *, event_type: Optional[str] = None) -> Dict:
        """Map to the canonical mock-payload contract (M2 fixtures shape).

        Event-mapping rule (provider-neutral): a page whose raw record
        carries a lifecycle pair (current_state + target_state) emits a
        `status_changed` event (state-machine validated downstream); a
        page without a pair emits an informational `{kind}_updated`
        snapshot event — valid per SUPPORTED_EVENT_TYPES, ingested
        without lifecycle validation.
        """
        pair = ("current_state" in self.raw
                and "target_state" in self.raw)
        p = {
            "page_id": self.page_id,
            "object": self.page_kind,
            "event_type": event_type or (
                "status_changed" if pair else f"{self.page_kind}_updated"),
        }
        p.update(self.raw)
        p.setdefault("revision_marker", self.marker)
        if self.last_edited_time:
            p.setdefault("last_edited_time", self.last_edited_time)
        return p


class NotionProvider:
    """Provider-neutral interface (RULES §35).

    Live adapter contract (implementation-deferred, owner-gated):
      - map raw Notion API pages to NotionEvent; the verified revision
        source field gets registered in
        canonical.notion_contracts.NOTION_REVISION_MARKER_FIELDS (one
        constant edit — zero structural rewrites);
      - fetch_events(since, page_ids, batch_size) → List[NotionEvent];
        return [] on an empty window; raise nothing across the boundary
        except Exception (the engine's error boundary captures any
        malformed output structurally).
    """

    def fetch_events(self, since: Optional[str] = None,
                     page_ids: Optional[Iterable[str]] = None,
                     batch_size: int = 100) -> List[NotionEvent]:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Mock adapter (local implementation, D-053)
# ---------------------------------------------------------------------------

_MOCK_NOTE = ("Mock adapter state, not a live Notion workspace (D-053). "
              "revision_marker is the D-060 dedupe identity; "
              "last_edited_time is change-detection metadata only.")


class MockNotionAdapter(NotionProvider):
    """In-memory Notion simulation.

    State model (per page): {"marker", "last_edited_time", "raw",
    "deleted"} — like MockWooAdapter, persistable to a JSON state file
    for deterministic reruns. Pages move through lifecycle transitions
    via simulate_transition() (validated against the D-060 machine) and
    bump the marker; failures inside the SIMULATED source raise
    ValueError (they simulate source-side problems, not daemon crashes).
    """

    def __init__(self, state_path: str = None):
        self.state_path = state_path
        self.pages: Dict[str, dict] = {}
        if state_path and os.path.exists(state_path):
            with open(state_path, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict) or not isinstance(
                    data.get("pages"), dict):
                raise ValueError("mock Notion state file is malformed")
            self.pages = data["pages"]

    def _persist(self):
        if self.state_path:
            os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
            with open(self.state_path, "w", encoding="utf-8") as f:
                json.dump({"pages": self.pages, "note": _MOCK_NOTE},
                          f, ensure_ascii=False, indent=2)

    # -- state helpers (simulation side) ------------------------------------

    def add_page(self, page_id: str, kind: str, marker: str,
                 last_edited_time: Optional[str] = None,
                 raw: Optional[Dict] = None) -> dict:
        self._validate_marker(marker)
        self.pages[page_id] = {
            "marker": marker, "last_edited_time": last_edited_time,
            "raw": dict(raw or {}), "kind": kind, "deleted": False,
        }
        self._persist()
        return dict(self.pages[page_id])

    def simulate_transition(self, page_id: str, target: str,
                            new_marker: str) -> dict:
        """Move a content-idea page through a lifecycle transition
        (validated by the D-060 machine) and bump the marker."""
        page = self.pages.get(page_id)
        if page is None or page.get("deleted"):
            raise ValueError(f"unknown mock page: {page_id}")
        from canonical.notion_contracts import validate_transition
        # resolve the page's current state from its own raw record
        state = page["raw"].get("state", "Backlog")
        validate_transition(state, target)
        page["raw"]["state"] = target
        page["raw"]["current_state"] = state
        page["raw"]["target_state"] = target
        page["marker"] = new_marker
        self._validate_marker(new_marker)
        self._persist()
        return dict(page)

    def set_error(self, page_id: str, error: Optional[str]) -> None:
        """Inject a source-side fault for one page ('timeout' supported)."""
        page = self.pages.get(page_id)
        if page is None:
            raise ValueError(f"unknown mock page: {page_id}")
        if error is not None and error != "timeout":
            raise ValueError(f"unsupported fault: {error}")
        page["error"] = error
        self._persist()

    def delete_page(self, page_id: str) -> None:
        page = self.pages.get(page_id)
        if page is None:
            raise ValueError(f"unknown mock page: {page_id}")
        page["deleted"] = True
        self._persist()

    # -- provider side --------------------------------------------------------

    @staticmethod
    def _validate_marker(marker: str) -> None:
        if not isinstance(marker, str) or "|" in marker:
            raise ValueError(
                f"invalid revision marker: {marker!r} (no '|' allowed — "
                "D-027 key delimiter)")

    def fetch_events(self, since: Optional[str] = None,
                     page_ids: Optional[Iterable[str]] = None,
                     batch_size: int = 100) -> List[NotionEvent]:
        if batch_size < 1:
            raise ValueError("batch_size must be >= 1")
        wanted = set(page_ids) if page_ids is not None else None
        events: List[NotionEvent] = []
        for pid, page in self.pages.items():
            if wanted is not None and pid not in wanted:
                continue
            if page.get("deleted") or page.get("error") == "timeout":
                continue  # deleted/faulted pages emit nothing
            if since is not None and str(page.get("last_edited_time", "")) <= since:
                continue
            events.append(NotionEvent(
                page_id=pid,
                page_kind=page.get("kind", "content_idea"),
                marker=page["marker"],
                last_edited_time=page.get("last_edited_time"),
                raw=dict(page.get("raw") or {}),
            ))
            if len(events) >= batch_size:
                break
        return events


# ---------------------------------------------------------------------------
# Polling engine
# ---------------------------------------------------------------------------


class PollingEngine:
    """Drives provider → ingestion, cycle by cycle, behind the boundary.

    Error-boundary isolation: ANY exception or malformed output from the
    provider (missing marker, non-dict raw, adapter crash) is captured
    as a structured AdapterErrorBoundary record in the cycle result —
    the daemon never crashes on adapter misbehavior, and good pages in
    the same batch still ingest.
    """

    def __init__(self, provider: NotionProvider, store=None, *,
                 queue=None, provenance=None, cursor_path: str = None,
                 actor: str = "notion-poller"):
        self.provider = provider
        self.store = store  # None → notion_ingest builds PgEventStore()
        self.queue = queue
        self.provenance = provenance
        self.cursor_path = cursor_path
        self.actor = actor
        # page_id → last EMITTED marker (runtime state, gitignored)
        self._cursors: Dict[str, str] = {}
        # page_id → marker whose ingestion FAILED (poison list): while a
        # page's marker equals the failed marker it is NOT re-emitted —
        # D-052: Class-B/E failures are never retried automatically; a
        # genuinely corrected source (new marker) re-delivers. This is
        # the M4 audit's row-G guarantee and preserves the M3 no-data-
        # loss intent (the page is never marked "done" on failure).
        self._failed: Dict[str, str] = {}
        if cursor_path and os.path.exists(cursor_path):
            try:
                with open(cursor_path, encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    if isinstance(data.get("emitted"), dict):
                        # current format {"emitted": …, "failed": …}
                        self._cursors = {
                            k: str(v) for k, v in data["emitted"].items()
                            if isinstance(v, str)
                        }
                        self._failed = {
                            k: str(v) for k, v in (
                                data.get("failed") or {}).items()
                            if isinstance(v, str)
                        }
                    else:
                        # legacy flat format {page_id: marker}
                        self._cursors = {
                            k: str(v) for k, v in data.items()
                            if isinstance(v, str)
                        }
            except (json.JSONDecodeError, OSError):
                self._cursors, self._failed = {}, {}  # corrupt → re-emit;
                # the D-027 store dedupes any resulting repeats

    def _save_cursors(self) -> None:
        if self.cursor_path:
            os.makedirs(os.path.dirname(self.cursor_path), exist_ok=True)
            with open(self.cursor_path, "w", encoding="utf-8") as f:
                json.dump({"emitted": self._cursors,
                           "failed": self._failed},
                          f, ensure_ascii=False, indent=2)

    def poll(self, *, batch_size: int = 100) -> dict:
        """One polling cycle. Returns a structured result; never raises
        for adapter misbehavior (error boundary), only for engine-internal
        bugs (e.g. store unreachable) — which SHOULD crash a daemon.
        """
        cycle = {
            "ingested": [], "skipped_duplicate": [], "failed": [],
            "unchanged": [], "suppressed": [], "errors": [],
        }
        try:
            events = self.provider.fetch_events(batch_size=batch_size)
        except AdapterErrorBoundary as exc:
            cycle["errors"].append(exc.record)
            return cycle
        except Exception as exc:  # adapter crashed — boundary holds
            cycle["errors"].append(
                {"error": type(exc).__name__,
                 "detail": str(exc)[:300]})
            return cycle
        for idx, ev in enumerate(events):
            try:
                if not isinstance(ev, NotionEvent) or not getattr(
                        ev, "page_id", None):
                    raise AdapterErrorBoundary(
                        "adapter returned a malformed event",
                        error="malformed_event", index=idx)
                marker = str(ev.marker or "").strip()
                if not marker:
                    raise AdapterErrorBoundary(
                        "adapter event carries no revision marker",
                        error="missing_marker", index=idx)
                if self._cursors.get(ev.page_id) == marker:
                    cycle["unchanged"].append(ev.page_id)
                    continue
                if self._failed.get(ev.page_id) == marker:
                    # same failed marker re-offered: automatic retry is
                    # forbidden (D-052 B/E) — suppressed, human review
                    # owns the outcome via the HITL item
                    cycle["suppressed"].append(ev.page_id)
                    continue
                result = ingest_notion_event(
                    ev.to_payload(), store=self.store, queue=self.queue,
                    provenance=self.provenance, actor=self.actor)
                if result["status"] == "succeeded":
                    self._cursors[ev.page_id] = marker
                    self._failed.pop(ev.page_id, None)
                    cycle["ingested"].append(
                        {"page_id": ev.page_id, "event_id": result["event_id"]})
                elif result["status"] == "skipped_duplicate":
                    self._cursors[ev.page_id] = marker
                    self._failed.pop(ev.page_id, None)
                    cycle["skipped_duplicate"].append(ev.page_id)
                else:  # failed — record the poisoned marker, never auto-retry
                    self._failed[ev.page_id] = marker
                    cycle["failed"].append(
                        {"page_id": ev.page_id, "error": result.get("error", "")})
            except AdapterErrorBoundary as exc:
                cycle["errors"].append(exc.record)
            except Exception as exc:  # ingestion bug — boundary holds
                cycle["errors"].append(
                    {"error": type(exc).__name__, "detail": str(exc)[:300],
                     "page_id": getattr(ev, "page_id", None)})
        self._save_cursors()
        return cycle

"""Phase 14 — Notion workspace replication facade.

THIN composition over the shipped boundary
(`local/services/notion_adapter.py`): the Notion API provider is always
INJECTED by the caller (D-045 fail-closed — nothing here constructs a
live provider or reads credentials), ingestion flows through the
canonical `ingest_notion_event` / `NotionPoller` with its deterministic
D-052 taxonomy, and every outbound replication payload is deep-redacted
(D-124) before it is handed to the provider.

This facade adds only what the commerce workflow needs:

  - `NotionReplicationAdapter.build_order_payload()` — order-pipeline
    row → canonical `campaign` object payload (validated shape:
    page_id hex/dash 16–64, event_type ∈ SUPPORTED_EVENT_TYPES,
    revision_marker resolvable, D-060 lifecycle states) before it
    leaves the process.
  - `replicate_catalog_update()` / `replicate_task()` — payload
    builders + submit through the canonical ingest path.
  - `poll_cycle()` — one backpressured polling cycle (delegates to
    `NotionPoller.poll`, which owns cursors and the poison list).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from local.src.memory.vector_store import deep_redact

__all__ = ["NotionReplicationAdapter", "NotionFacadeError"]


class NotionFacadeError(ValueError):
    """Replication refused: no provider, malformed input, or contract
    violation. Never carries credential material."""


def _redact(x: Any) -> Any:
    return deep_redact(x) if isinstance(x, str) else x


class NotionReplicationAdapter:
    """Replicates SSOT commerce state into a Notion workspace."""

    def __init__(self, *, provider=None, store=None, queue=None,
                 provenance=None, max_queue: int = 1000):
        # D-045: provider injected. None is allowed ONLY for offline
        # payload-building; any submit/poll path refuses without one.
        self._provider = provider
        self._store = store
        self._queue = queue
        self._provenance = provenance
        self._max = int(max_queue)
        self._poller = None

    # -- payload builders (pure, usable offline) ---------------------------
    @staticmethod
    def _check_ids(page_id: str, marker: str) -> None:
        import re as _re
        if not page_id or not _re.fullmatch(r"[0-9a-fA-F-]{16,64}",
                                            page_id or ""):
            raise NotionFacadeError(
                "page_id must be a hex/dash identifier (16–64 chars)")
        if not marker or not str(marker).strip():
            raise NotionFacadeError("marker is required")

    @staticmethod
    def _page_payload(obj: str, page_id: str, marker: str,
                      props: Dict) -> Dict:
        """Canonical `campaign` object payload (ingest-contract shape).

        The canonical payload contract accepts object ∈ {content_idea,
        campaign, incident}; commerce replication rows map onto
        `campaign` (order pipelines, catalog boards, task boards are
        workspace campaigns in the D-060 lifecycle). State changes ride
        `status_changed` with current/target for the D-060 machine.
        """
        return {
            "page_id": page_id,
            "event_type": "campaign_updated",
            "object": obj,
            "revision_marker": marker,
            "properties": {k: _redact(v) for k, v in props.items()},
        }

    def build_order_payload(self, order_ref: Dict, *,
                            page_id: str, marker: str) -> Dict:
        """Order lifecycle row → canonical Notion page payload."""
        self._check_ids(page_id, marker)
        state = str(order_ref.get("state", ""))
        if not state:
            raise NotionFacadeError("order_ref carries no state")
        props = {
            "Order ID": _redact(str(order_ref.get("order_id", ""))),
            "State": state,
            "Customer": _redact(str(order_ref.get("customer_ref", ""))),
            "Items": len(order_ref.get("line_items", []) or []),
        }
        return self._page_payload("campaign", page_id, marker, props)

    def build_catalog_payload(self, product: Dict, *,
                              page_id: str, marker: str) -> Dict:
        self._check_ids(page_id, marker)
        return self._page_payload("campaign", page_id, marker, {
            "SKU": _redact(str(product.get("sku", ""))),
            "Title": _redact(str(product.get("title", ""))),
            "Stock": int(product.get("stock", 0)),
        })

    def build_task_payload(self, task: Dict, *,
                           page_id: str, marker: str) -> Dict:
        self._check_ids(page_id, marker)
        return self._page_payload("campaign", page_id, marker, {
            "Task": _redact(str(task.get("title", ""))),
            "Status": _redact(str(task.get("status", ""))),
        })

    # -- submit / poll (require an injected provider) -----------------------
    def _require_provider(self):
        if self._provider is None:
            raise NotionFacadeError(
                "no Notion provider injected — refusing (D-045)")

    def submit(self, payload: Dict) -> dict:
        """Backpressured, contract-validated submission of one payload
        through the canonical ingest path."""
        self._require_provider()
        if self._queue is not None and hasattr(self._queue, "qsize"):
            if self._queue.qsize() >= self._max:
                return {"status": "failed", "reason": "backpressure",
                        "accepted": False}
        from canonical.notion_contracts import validate_mock_payload
        validate_mock_payload(payload, check_transition=False)
        from canonical.notion_ingest import ingest_notion_event
        result = ingest_notion_event(
            payload, store=self._store, queue=self._queue,
            provenance=self._provenance, actor="notion-replication")
        result["accepted"] = result.get("status") == "succeeded"
        return result

    def poller(self):
        """Lazily built canonical poller over the injected provider."""
        self._require_provider()
        if self._poller is None:
            from services.notion_adapter import PollingEngine
            self._poller = PollingEngine(
                self._provider, self._store, queue=self._queue,
                provenance=self._provenance, actor="notion-replication")
        return self._poller

    def poll_cycle(self, *, batch_size: int = 100) -> dict:
        return self.poller().poll(batch_size=batch_size)

"""Instagram channel dispatcher (Part A).

Wraps the canonical `InstagramOutboxPublisher` (the SSOT outbox stays
the system of record) and normalizes the dispatch receipt (publication
id, outcome, redacted detail) so the orchestrator is channel-agnostic.
"""
from __future__ import annotations

from typing import Callable, Dict, Optional

from canonical.instagram_publisher import InstagramOutboxPublisher

from .receipts import normalize_receipt

__all__ = ["InstagramDispatcher"]


class InstagramDispatcher:
    platform = "instagram"

    def __init__(self, publisher: InstagramOutboxPublisher,
                 adapter: object, redactor: Optional[Callable] = None):
        self._pub = publisher
        self._adapter = adapter
        self._redact = redactor

    def dispatch(self, payload: Dict, *, actor: str = "pub-orchestrator",
                 ) -> Dict:
        ref = self._pub.enqueue(payload, actor=actor)
        raw = self._pub.publish(ref["payload"], self._adapter,
                                actor=actor)
        return normalize_receipt(raw)

"""Telegram channel dispatcher (Part A).

Wraps the canonical `TelegramOutboxPublisher` (the SSOT outbox stays
the system of record) and normalizes the dispatch receipt (message id,
outcome, redacted detail) so the orchestrator is channel-agnostic.
"""
from __future__ import annotations

from typing import Callable, Dict, Optional

from canonical.telegram_publisher import TelegramOutboxPublisher

from .receipts import normalize_receipt

__all__ = ["TelegramDispatcher"]


class TelegramDispatcher:
    platform = "telegram"

    def __init__(self, publisher: TelegramOutboxPublisher,
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

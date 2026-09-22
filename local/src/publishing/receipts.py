"""Shared receipt normalization (D-124) for the channel dispatchers.

One receipt shape for every channel: outcome, canonical error class,
platform post id when delivered, publish key, and REDACTED detail.
Credential-shaped material never survives normalization.
"""
from __future__ import annotations

from typing import Dict

try:  # battery package path or script cwd path
    from ..memory.vector_store import deep_redact  # type: ignore
except ImportError:  # pragma: no cover
    from local.src.memory.vector_store import deep_redact

__all__ = ["normalize_receipt"]


def normalize_receipt(raw: Dict) -> Dict:
    """One receipt shape for every channel: outcome, class, platform
    post id when delivered, and redacted detail."""
    outcome = raw.get("outcome", "unknown")
    return {
        "outcome": outcome,
        "error_class": raw.get("error_class", ""),
        "delivered": outcome == "published",
        "platform_post_id": (raw.get("publication_id")
                             or raw.get("message_id") or ""),
        "publish_key": raw.get("publish_key", ""),
        "detail": deep_redact(str(
            raw.get("error") or raw.get("original") or ""))[:200],
    }

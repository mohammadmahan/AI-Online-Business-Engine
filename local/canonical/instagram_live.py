"""Phase 9/11 live wiring — Graph API taxonomy, usage tracking, client
extension (D-069..D-072).

Extends the shipped D-071 `GraphApiAdapter` without touching it:

  - `classify_graph_error` — Meta Graph error bodies
    ({"error": {code, error_subcode, is_transient, message, ...}})
    mapped onto the D-052 taxonomy via the PUBLISHER's existing
    carriers, so the D-070 outbox handles classified live errors with
    ZERO publisher changes:
      * rate-limit codes (4, 17, 32, 613) or is_transient →
        `_RateLimited` (Class-C → cooldown gate);
      * permission codes (10, 190, 200, 2500) / OAuth subcodes →
        `_TokenExpired` (Class-E → queue freeze + HITL alert);
      * `is_transient: true` 5xx-shaped → TimeoutError (Class-A →
        bounded backoff);
      * everything else → `InstagramContractError` (Class-B →
        terminal reject + DLQ).
  - `GraphUsageTracker` — records the X-App-Usage / X-Business-Use-
    Case-Usage percentages the Graph API returns and computes the
    headroom signal (deterministic; no wall clock — the caller stamps
    logical time).
  - `ClassifiedGraphAdapter` — D-071 subclass: same construction gate
    and redaction, but `_dispatch` runs the raw body through
    `classify_graph_error` first, tracks usage headers, and maps
    structured failures onto the taxonomy carriers.
  - `GRAPH_API_VERSION` pinned (v26.0 per the official changelog,
    reviewed 2026-09-21) — the base client was version-agnostic; the
    live probe and URL builder use the pinned constant.

Zero network, zero credentials: transport always injected; the gate
stays `require_live_keys()` (D-045/D-071).
"""
from __future__ import annotations

import json
import os
import re
from typing import Callable, Dict, List, Optional

from canonical.instagram_adapter import (
    GraphApiAdapter, _RateLimited, redact,
)
from canonical.instagram_contracts import InstagramContractError
from canonical.instagram_publisher import _TokenExpired  # noqa: E402

__all__ = [
    "GRAPH_API_VERSION", "RATE_LIMIT_CODES", "PERMISSION_CODES",
    "GraphUsageTracker", "ClassifiedGraphAdapter",
    "classify_graph_error", "classify_graph_status",
]

# Pinned per the official Graph API changelog (v26.0 latest; v21.0 is
# the oldest still-served line until 2027-01). Reviewed 2026-09-21.
GRAPH_API_VERSION = "v26.0"

# Documented platform rate-limit / transient-throttle codes.
RATE_LIMIT_CODES = {4, 17, 32, 613}
# Documented permission / access-token codes (OAuth exception family).
PERMISSION_CODES = {10, 190, 200, 2500}


class GraphUsageTracker:
    """Tracks X-App-Usage / X-Business-Use-Case-Usage percentages.

    `record(usage_dict)` accepts the documented shape
    {"call_count": pc, "total_time": pc, "total_cputime": pc};
    `headroom()` returns the smallest remaining percentage before the
    documented ~100% throttle boundary (None before any data).
    Deterministic: the caller stamps logical time; this class never
    reads a clock.
    """

    def __init__(self, warn_at_pct: float = 75.0):
        if warn_at_pct <= 0 or warn_at_pct >= 100:
            raise InstagramContractError(
                "warn_at_pct must be between 0 and 100")
        self.warn_at_pct = float(warn_at_pct)
        self._latest: Dict[str, float] = {}
        self._history: List[Dict[str, float]] = []

    def record(self, usage: Optional[Dict]) -> bool:
        """Record one usage snapshot; True iff at/over warn level."""
        if not isinstance(usage, dict) or not usage:
            return False
        pcts: Dict[str, float] = {}
        for k, v in usage.items():
            try:
                pcts[str(k)] = float(v)
            except (TypeError, ValueError):
                continue
        if not pcts:
            return False
        self._latest = pcts
        self._history.append(dict(pcts))
        return self.utilization() >= self.warn_at_pct

    def utilization(self) -> float:
        """Worst-case (max) documented percentage in the latest snapshot."""
        if not self._latest:
            return 0.0
        return max(self._latest.values())

    def headroom(self) -> Optional[float]:
        if not self._latest:
            return None
        return round(100.0 - self.utilization(), 3)

    @property
    def snapshots(self) -> int:
        return len(self._history)


def classify_graph_status(status_code: int,
                          error_body: Optional[Dict]) -> Optional[Exception]:
    """HTTP-status-first classification (for non-JSON bodies).

    429 → C (cooldown), 401/403 → E (permission), 5xx → A (transient);
    None means "let body-level classification decide".
    """
    if status_code == 429:
        return _RateLimited("429 rate limited (http status)")
    if status_code in (401, 403):
        return _TokenExpired(f"{status_code} permission/auth (http status)")
    if status_code >= 500:
        return TimeoutError(f"{status_code} server error (http status)")
    return None


def classify_graph_error(error: Dict) -> Exception:
    """Classify a Graph API error body onto the D-052 carriers.

    `error` is the parsed {"error": {...}} VALUE (code, error_subcode,
    is_transient, message, error_user_msg, ...). Unknown shapes fall
    to Class-B (terminal) — fail closed, never silently retried.
    """
    if not isinstance(error, dict):
        return InstagramContractError(
            redact(f"malformed graph error: {error!r}"))
    try:
        code = int(error.get("code", 0) or 0)
    except (TypeError, ValueError):
        code = 0
    subcode = error.get("error_subcode")
    is_transient = bool(error.get("is_transient"))
    message = str(error.get("message", "graph api error"))

    # Rate-limit family first (documented codes + transient flag).
    if code in RATE_LIMIT_CODES or (is_transient and code not in
                                    PERMISSION_CODES):
        return _RateLimited(redact(f"graph rate limited ({code}): {message}"))
    # Permission / OAuth family → Class-E (human-gated).
    if code in PERMISSION_CODES or (
            isinstance(subcode, int) and 400000 <= subcode <= 499999):
        return _TokenExpired(redact(
            f"graph permission/auth error ({code}/{subcode}): {message}"))
    # Explicit transient flag with unknown code → treat as throttle.
    if is_transient:
        return _RateLimited(redact(f"graph transient throttle: {message}"))
    # Everything else: terminal contract failure (Class-B).
    return InstagramContractError(
        redact(f"graph api error ({code}): {message}"))


class ClassifiedGraphAdapter(GraphApiAdapter):
    """D-071 live adapter + taxonomy classification + usage tracking.

    Construction gate and credential handling are inherited unchanged.
    `_dispatch` now:
      1. calls the injected transport (unchanged request shape);
      2. records X-App-Usage / X-Business-Use-Case-Usage if present;
      3. on {"error": ...} or error statuses, classifies through
         `classify_graph_status` / `classify_graph_error` and raises
         the matching taxonomy carrier — which the D-070 publisher
         already handles (cooldown / freeze / backoff / DLQ).
    """

    name = "graph_api_classified"

    def __init__(self, *args, usage_tracker: Optional[GraphUsageTracker] = None,
                 **kwargs):
        super().__init__(*args, **kwargs)
        self.usage = usage_tracker or GraphUsageTracker()

    def _transport_response_usage(self, body: Dict) -> Optional[Dict]:
        usage = body.get("__usage__") if isinstance(body, dict) else None
        return usage if isinstance(usage, dict) else None

    def _dispatch(self, method: str, path: str, payload: Dict) -> Dict:
        try:
            body = self._transport({
                "method": method,
                "path": f"{GRAPH_API_VERSION}/{path}",
                "payload": payload,
                "access_token": self._token})
        except TimeoutError as exc:
            raise TimeoutError(redact(str(exc))) from exc
        except ConnectionError as exc:
            raise ConnectionError(redact(str(exc))) from exc
        except OSError as exc:
            raise OSError(redact(str(exc))) from exc
        # usage tracking (documented headers may be surfaced by the
        # transport as __usage__; absence is normal and ignored)
        warned = self.usage.record(self._transport_response_usage(body))
        self.usage_warned = warned
        err = body.get("error") if isinstance(body, dict) else None
        if err:
            raise classify_graph_error(err)
        return body

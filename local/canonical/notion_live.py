"""Phase 6 live wiring — Notion API client contracts (D-060/D-045).

The OUTBOUND side of Notion live integration, completing the
`NotionProvider` seam from `local/services/notion_adapter.py` (the
mock remains the local implementation, D-053). Pure and deterministic
— the transport is ALWAYS injected (D-075 pattern), so no test or
offline run ever touches a network:

  - `NotionClientContract` — provider-neutral API boundary.
  - `LiveNotionClient` — construction-gated real client:
      * `NOTION_API_KEY` resolves from the environment reference only
        (D-045: unset ⇒ refuse; no default secret anywhere);
      * token material is redacted from every escaping error string;
      * Notion's documented 3 req/sec average limit is honored by the
        deterministic `NotionPacer` (1-second sliding window, no wall
        clock in tests — injectable `now_s`);
      * `retry_after` (429/503 `Retry-After`) and exponential backoff
        are returned as DETERMINISTIC PLANS, never slept on — the
        caller (worker/script) owns waiting, keeping this module pure;
      * response status/error mapping follows the D-052 taxonomy:
        400 validation → Class-B terminal; 401/403 → Class-E
        (credential/permission, human-gated); 404 → Class-B;
        429 → Class-C (honor Retry-After); 5xx / timeout /
        connection → Class-A transient.
  - Block/page mapping — safe, structure-checked conversion between
    the Core Engine content model (D-060 content-idea fields) and
    Notion block structures (`to_notion_blocks` / `from_notion_page`);
    unknown block types and oversized payloads are rejected locally
    (Class-B) before any request is built.
  - `redact_notion` — strips integration-token material and database/
    page UUIDs from log/observability strings (D-124 zero-leak).

Deterministic local fallback: with no gate satisfied, callers use
`MockNotionAdapter` (services) — this module NEVER falls back to
network I/O on its own.
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

__all__ = [
    "NOTION_API_BASE", "NOTION_VERSION", "LIVE_ENV_FLAG", "TOKEN_ENV",
    "NOTION_RATE_LIMIT_PER_SEC", "NotionContractError",
    "NotionAuthError", "NotionRateLimited", "NotionTransientError",
    "NotionClientContract", "LiveNotionClient", "NotionPacer",
    "require_live_keys", "live_enabled", "redact_notion",
    "to_notion_blocks", "from_notion_page", "classify_notion_error",
    "backoff_plan",
]

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
LIVE_ENV_FLAG = "NOTION_LIVE_ENABLED"
TOKEN_ENV = "NOTION_API_KEY"

# Notion documented limit: an average of 3 requests per second.
NOTION_RATE_LIMIT_PER_SEC = 3.0

_REDACTED = "[REDACTED]"

# Notion object ids are 32-hex with optional dashes.
_OBJECT_ID_RE = re.compile(r"[0-9a-fA-F]{32}")
_UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}"
    r"-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{12}\b")


def _valid_object_id(value: str) -> bool:
    return bool(_OBJECT_ID_RE.fullmatch(value.replace("-", "")))


class NotionContractError(ValueError):
    """Class-B carrier — terminal reject, no retry (D-052)."""


class NotionAuthError(PermissionError):
    """Class-E carrier — credential/permission, human-gated."""


class NotionRateLimited(Exception):
    """Class-C carrier — honors `retry_after_s`."""

    def __init__(self, message: str, retry_after_s: float = 1.0):
        super().__init__(message)
        self.retry_after_s = float(retry_after_s)


class NotionTransientError(TimeoutError):
    """Class-A carrier — transient; deterministic backoff applies."""


def live_enabled() -> bool:
    return os.environ.get(LIVE_ENV_FLAG, "").strip().lower() == "true"


def require_live_keys() -> Dict[str, str]:
    """D-045 gate: resolve NOTION_API_KEY from the environment.

    Fails closed unless BOTH the explicit live flag is true AND the
    token environment reference carries a non-empty value. Never
    defaults, never echoes the token.
    """
    if not live_enabled():
        raise NotionAuthError(
            f"live Notion client disabled: {LIVE_ENV_FLAG} is not true "
            "(fail-closed; D-045/D-053)")
    token = os.environ.get(TOKEN_ENV, "").strip()
    if not token:
        raise NotionAuthError(
            f"live Notion client disabled: {TOKEN_ENV} missing or empty "
            "(fail-closed; D-045)")
    return {"api_key": token}


# --- redaction (D-124 zero-leak) --------------------------------------------

def redact_notion(text: str, extra_secrets: Optional[List[str]] = None) -> str:
    """Strip token material and object UUIDs from any string.

    Covers the `secret_…` integration-token form, caller-known secret
    values, and 32-hex (dashed or bare) object ids — Notion ids are
    workspace-internal references and are redacted from logs per the
    directive's zero-leak requirement.
    """
    out = str(text)
    out = re.sub(r"secret_[A-Za-z0-9]{20,}", _REDACTED, out)
    out = _UUID_RE.sub("[REDACTED_ID]", out)
    for secret in extra_secrets or []:
        if secret:
            out = out.replace(str(secret), _REDACTED)
    return out


# --- deterministic pacing (3 req/sec) ----------------------------------------

class NotionPacer:
    """Sliding-window pacer at Notion's documented average limit.

    `acquire(now_s)` returns the seconds the caller must wait before
    the next request (0.0 = go now) and RESERVES the slot — pacing,
    never dropping. `now_s` is injectable: production callers pass a
    monotonic clock; tests pass synthetic ticks (deterministic, no
    wall clock in this module).
    """

    def __init__(self, rate_per_sec: float = NOTION_RATE_LIMIT_PER_SEC):
        if rate_per_sec <= 0:
            raise NotionContractError("rate must be positive")
        self.rate = float(rate_per_sec)
        self._window: List[float] = []

    def acquire(self, now_s: float) -> float:
        horizon = now_s - 1.0
        while self._window and self._window[0] <= horizon:
            self._window.pop(0)
        if len(self._window) >= self.rate:
            wait = self._window[0] + 1.0 - now_s
            self._window.append(now_s + max(wait, 0.0))
            return max(wait, 0.0)
        self._window.append(now_s)
        return 0.0


# --- deterministic backoff (plan, never a sleep) ------------------------------

def backoff_plan(attempt: int, retry_after_s: Optional[float] = None,
                 base_s: float = 1.0, factor: float = 2.0,
                 max_s: float = 60.0) -> Dict[str, float]:
    """Exponential backoff as a DETERMINISTIC PLAN.

    Jitter is deliberately absent (nondeterministic in tests and
    unnecessary for a single-process pacer; D-126 precedent) — the
    rate ceiling comes from the pacer instead. `retry_after_s` (from
    a 429/503 Retry-After) floors the wait. Returns the schedule and
    the wait the caller owes for `attempt` (1-based).
    """
    if attempt < 1:
        raise NotionContractError("attempt is 1-based")
    waits: List[float] = []
    for i in range(1, attempt + 1):
        exp = min(base_s * (factor ** (i - 1)), max_s)
        if retry_after_s is not None and i == attempt:
            exp = max(exp, retry_after_s)
        waits.append(round(exp, 3))
    return {"attempt": attempt, "wait_s": waits[-1],
            "schedule": waits, "retry_after_floor_s":
                float(retry_after_s) if retry_after_s is not None else 0.0}


# --- error classification (D-052) -----------------------------------------------

def classify_notion_error(status_code: int, body: str,
                          retry_after_s: Optional[float] = None) -> Exception:
    """Map an HTTP response to the D-052-aligned carrier.

    400 validation (invalid_json/validation) → Class-B terminal;
    401/403 → Class-E credential/permission (human-gated); 404 →
    Class-B; 429 → Class-C honoring Retry-After; 5xx → Class-A
    transient; other 4xx → Class-B.
    """
    low = str(body).lower()
    if status_code == 429:
        return NotionRateLimited(
            f"429 rate limited: {body}",
            retry_after_s if retry_after_s is not None else 1.0)
    if status_code in (401, 403):
        return NotionAuthError(f"{status_code} unauthorized/forbidden: {body}")
    if status_code >= 500:
        return NotionTransientError(f"{status_code} server error: {body}")
    if status_code == 400 and ("validation" in low or "invalid" in low):
        return NotionContractError(f"400 validation rejected: {body}")
    return NotionContractError(f"{status_code} bad request: {body}")


# --- block / page mapping ------------------------------------------------------

# Content-idea model keys (D-060) → safe Notion block builders.
_MAX_BLOCKS = 100            # Notion per-request children cap
_MAX_TEXT_CHARS = 2000       # Notion rich-text per-element cap
_PARAGRAPH = "paragraph"
_HEADING_1 = "heading_1"


def _rt(text: str) -> Dict[str, Any]:
    return {"type": "text", "text": {"content": text}}


def to_notion_blocks(idea: Dict[str, str]) -> List[Dict[str, Any]]:
    """Core content model → Notion children blocks (outbound).

    Accepted keys: title (required), hypothesis, angle, notes.
    Local Class-B BEFORE any request is built: missing title,
    oversize text, wrong types, more than _MAX_BLOCKS.
    """
    if not isinstance(idea, dict):
        raise NotionContractError("idea must be an object")
    title = idea.get("title")
    if not isinstance(title, str) or not title.strip():
        raise NotionContractError("idea.title is required")
    body: List[Tuple[str, Optional[str]]] = [("title", title.strip())]
    for key in ("hypothesis", "angle", "notes"):
        val = idea.get(key)
        if val is None:
            continue
        if not isinstance(val, str):
            raise NotionContractError(f"idea.{key} must be a string")
        body.append((key, val))
    blocks: List[Dict[str, Any]] = []
    for kind, text in body:
        if len(text) > _MAX_TEXT_CHARS:
            raise NotionContractError(
                f"idea.{kind} exceeds {_MAX_TEXT_CHARS} chars")
        btype = _HEADING_1 if kind == "title" else _PARAGRAPH
        blocks.append({"object": "block", "type": btype,
                       btype: {"rich_text": [_rt(text)]}})
    if len(blocks) > _MAX_BLOCKS:
        raise NotionContractError(
            f"idea expands to {len(blocks)} blocks (max {_MAX_BLOCKS})")
    return blocks


def from_notion_page(page: Dict[str, Any]) -> Dict[str, str]:
    """Notion page → Core content model (inbound, structure-checked).

    Reads the first heading_1 (title) and subsequent paragraph
    rich_text from a `results` list of block objects (or a bare list).
    Unknown block types are SKIPPED (forward-safe); malformed rich
    text is a Class-B. Returns the plain content model — no Notion
    structures escape into the canonical store.
    """
    if isinstance(page, dict):
        results = page.get("results", page)
    else:
        results = page
    if not isinstance(results, list):
        raise NotionContractError("page payload must contain results[]")
    title: Optional[str] = None
    paragraphs: List[str] = []
    for blk in results:
        if not isinstance(blk, dict):
            raise NotionContractError("block entries must be objects")
        btype = blk.get("type")
        if btype not in (_HEADING_1, _PARAGRAPH):
            continue  # unknown/unsupported → skip, forward-safe
        payload = blk.get(btype)
        if not isinstance(payload, dict):
            raise NotionContractError(f"{btype} payload must be an object")
        rts = payload.get("rich_text")
        if not isinstance(rts, list):
            raise NotionContractError("rich_text must be a list")
        text = "".join(
            rt.get("text", {}).get("content", "")
            for rt in rts if isinstance(rt, dict))
        if btype == _HEADING_1 and title is None:
            title = text
        elif btype == _PARAGRAPH and text:
            paragraphs.append(text)
    if title is None:
        raise NotionContractError("page has no heading_1 title block")
    model: Dict[str, str] = {"title": title}
    for key, text in zip(("hypothesis", "angle", "notes"), paragraphs):
        model[key] = text
    return model


# --- client contract & live client -------------------------------------------

class NotionClientContract:
    """Provider-neutral Notion API boundary (RULES §35)."""

    def append_blocks(self, page_id: str, blocks: List[Dict]) -> Dict:
        raise NotImplementedError

    def create_page(self, database_id: str, blocks: List[Dict]) -> Dict:
        raise NotImplementedError

    def retrieve_block_children(self, block_id: str) -> Dict:
        raise NotImplementedError


class LiveNotionClient(NotionClientContract):
    """Real Notion API client — construction-gated (D-045), injectable
    transport, redacted errors, pacer- and plan-only waiting.

    The transport receives {"method", "url", "headers", "json"} and
    returns {"status_code", "body", "retry_after"} — headers carry NO
    secret in the request description the transport logs; the token
    travels in `headers` only and is redacted from every escaping
    error string. No network happens in tests because a transport is
    ALWAYS injected (D-075 discipline).
    """

    def __init__(self, transport: Optional[Callable[[Dict], Dict]] = None,
                 api_key: Optional[str] = None,
                 pacer: Optional[NotionPacer] = None,
                 clock: Optional[Callable[[], float]] = None):
        gate = require_live_keys() if api_key is None else {"api_key": api_key}
        if transport is None:
            raise NotionContractError(
                "LiveNotionClient requires an injected transport — "
                "direct HTTP is forbidden in this architecture (D-045/D-075)")
        self._api_key = gate["api_key"]
        self._transport = transport
        self._pacer = pacer or NotionPacer()
        # Production pacing uses a monotonic clock (D-074 RatePacer
        # precedent); tests inject a synthetic tick function.
        self._clock = clock or time.monotonic

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}",
                "Notion-Version": NOTION_VERSION,
                "Content-Type": "application/json"}

    def _call(self, method: str, path: str, json_body: Dict) -> Dict:
        wait = self._pacer.acquire(now_s=self._clock())
        # The pacer's verdict travels with the request; the CALLER-side
        # driver owns sleeping on it (this module stays pure).
        request = {"method": method, "url": f"{NOTION_API_BASE}{path}",
                   "headers": self._headers(), "json": json_body,
                   "pacer_wait_s": wait}
        try:
            response = self._transport(request)
        except TimeoutError as exc:
            raise NotionTransientError(redact_notion(
                str(exc), extra_secrets=[self._api_key]))
        except (ConnectionError, OSError) as exc:
            raise ConnectionError(redact_notion(
                str(exc), extra_secrets=[self._api_key]))
        status = int(response.get("status_code", 0))
        body = str(response.get("body", ""))
        if 200 <= status < 300:
            try:
                parsed = json.loads(body)
            except json.JSONDecodeError:
                raise NotionContractError(
                    f"non-JSON {status} response from Notion")
            return parsed
        carrier = classify_notion_error(
            status, body, response.get("retry_after"))
        if hasattr(carrier, "args") and carrier.args:
            redacted = redact_notion(str(carrier.args[0]),
                                     extra_secrets=[self._api_key])
            carrier.args = (redacted,) + tuple(carrier.args[1:])
        raise carrier

    @staticmethod
    def _clock() -> float:
        raise NotImplementedError  # replaced by the instance clock

    # -- contract operations --------------------------------------------------

    def append_blocks(self, page_id: str,
                      blocks: List[Dict]) -> Dict:
        if not isinstance(page_id, str) or not _valid_object_id(page_id):
            raise NotionContractError(
                "page_id must be a Notion object id (32-hex, dashes ok)")
        if not isinstance(blocks, list) or not blocks:
            raise NotionContractError("blocks must be a non-empty list")
        if len(blocks) > _MAX_BLOCKS:
            raise NotionContractError(
                f"blocks exceed {_MAX_BLOCKS} per request")
        return self._call("PATCH", f"/blocks/{page_id}/children",
                          {"children": blocks})

    def append_idea(self, page_id: str, idea: Dict[str, str]) -> Dict:
        """Map the Core content model, then append its blocks."""
        return self.append_blocks(page_id, to_notion_blocks(idea))

    def create_page(self, database_id: str,
                    blocks: List[Dict]) -> Dict:
        if not isinstance(database_id, str) or not _valid_object_id(
                database_id):
            raise NotionContractError(
                "database_id must be a Notion object id (32-hex, dashes ok)")
        if not isinstance(blocks, list) or not blocks:
            raise NotionContractError("blocks must be a non-empty list")
        if len(blocks) > _MAX_BLOCKS:
            raise NotionContractError(
                f"blocks exceed {_MAX_BLOCKS} per request")
        return self._call("POST", "/pages",
                          {"parent": {"database_id": database_id},
                           "children": blocks})

    def create_idea(self, database_id: str, idea: Dict[str, str]) -> Dict:
        """Map the Core content model, then create the page."""
        return self.create_page(database_id, to_notion_blocks(idea))

    def retrieve_block_children(self, block_id: str) -> Dict:
        if not isinstance(block_id, str) or not _valid_object_id(block_id):
            raise NotionContractError(
                "block_id must be a Notion object id (32-hex, dashes ok)")
        return self._call("GET", f"/blocks/{block_id}/children", {})

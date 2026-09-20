"""Phase 5 live wiring — n8n webhook contracts & deterministic dispatcher.

The CORE-side half of n8n live automation (D-042 boundary: n8n is
orchestration-only; the canonical store stays the single source of
truth). Pure and deterministic — no network, no wall clock, no
credentials. Canonical, so it composes with every phase's seam
discipline:

  - `N8nWebhookError` — Class-B carrier (terminal reject, no retry),
    mirroring the Telegram/Instagram contract-error pattern.
  - `verify_hmac_header` — HMAC-SHA256 verification of an n8n
    webhook-call payload against the shared secret reference, over the
    exact raw bytes. Constant-time compare; timing-safe by stdlib.
    The secret is a REFERENCE resolved by the caller (D-045: values
    live in the per-environment secret store, never in Git); a
    missing/unset reference is a fail-closed construction error.
  - `parse_event` — schema-validated ingestion of a webhook event:
    `event_type` + `workflow_ref` + `payload`, size-bounded and
    type-checked; unknown shapes are deterministic Class-B rejects.
  - `N8nEventDispatcher` — wires parsed events to INJECTED handlers
    keyed by event_type (RULES §35 seam discipline). Deterministic
    idempotency: every dispatch decision is keyed by
    SHA256(event_type + workflow_ref + event_id) — the D-027
    idempotency-key pattern (notion/instagram lineage, D-060) — so a
    repeated delivery yields the same key and the injected sink
    deduplicates; the dispatcher never fires a handler twice for one
    event_id. No wall clock anywhere: timestamps are caller-provided
    logical instants.
  - `mock_webhook_payload` / `sign_payload` — deterministic local
    fixtures for tests and offline drills (mock-first, D-053).

Live adapter enablement follows the shipped Telegram/Instagram
pattern exactly (see scripts/validate_n8n_live.py): the runtime
credential gate lives OUTSIDE this module.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from typing import Callable, Dict, List, Optional

__all__ = [
    "N8nWebhookError", "MAX_PAYLOAD_BYTES", "WEBHOOK_SECRET_ENV",
    "verify_hmac_header", "parse_event", "N8nEventDispatcher",
    "event_key", "sign_payload", "mock_webhook_payload",
]

MAX_PAYLOAD_BYTES = 64 * 1024          # bounded ingestion surface
WEBHOOK_SECRET_ENV = "N8N_WEBHOOK_SECRET"
SIGNATURE_HEADER = "x-n8n-webhook-signature"   # documented header name


class N8nWebhookError(ValueError):
    """Webhook contract violation (Class-B: terminal reject, no retry)."""


# --- HMAC verification (D-045 credential-reference pattern) ------------

def _secret_from_env() -> str:
    """Resolve the shared secret REFERENCE from the environment.
    Fail-closed: no default value exists anywhere."""
    secret = os.environ.get(WEBHOOK_SECRET_ENV, "").strip()
    if not secret:
        raise N8nWebhookError(
            f"webhook secret unavailable: {WEBHOOK_SECRET_ENV} is unset "
            "(D-045: credential refs resolve from the environment's "
            "secret store; no default exists)")
    return secret


def verify_hmac_header(raw_body: bytes, header_value: str,
                       secret: Optional[str] = None) -> None:
    """Verify an HMAC-SHA256 webhook signature over the EXACT raw bytes.

    `header_value` must be the `sha256=<hex>` form. Mismatch, malformed
    header, wrong length, or a non-hex digest raises N8nWebhookError.
    Comparison is constant-time (hmac.compare_digest).
    """
    if not isinstance(raw_body, (bytes, bytearray)):
        raise N8nWebhookError("raw body must be bytes (verify pre-decode)")
    if not isinstance(header_value, str) or not header_value:
        raise N8nWebhookError("signature header missing or empty")
    if not header_value.startswith("sha256="):
        raise N8nWebhookError("signature header must be 'sha256=<hex>'")
    hexdig = header_value[len("sha256="):].strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", hexdig):
        raise N8nWebhookError("signature digest must be 64 hex chars")
    secret_val = secret if secret is not None else _secret_from_env()
    expected = hmac.new(secret_val.encode("utf-8"), bytes(raw_body),
                        hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, hexdig):
        raise N8nWebhookError("webhook signature verification failed")


# --- event ingestion ----------------------------------------------------

_ALLOWED_TYPES = ("workflow.completed", "workflow.failed",
                  "hitl.request", "ops.ping")


def parse_event(body: bytes) -> Dict:
    """Parse and validate a webhook event from raw bytes.

    Contract: UTF-8 JSON object with exactly the keys
    `event_type` (allowed enum), `workflow_ref` (non-empty string,
    <=120 chars), `event_id` (non-empty string, <=120 chars),
    `payload` (JSON object). Size-bounded by MAX_PAYLOAD_BYTES.
    Returns the parsed dict; raises N8nWebhookError otherwise.
    """
    if not isinstance(body, (bytes, bytearray)):
        raise N8nWebhookError("event body must be bytes")
    if len(body) > MAX_PAYLOAD_BYTES:
        raise N8nWebhookError(
            f"event body exceeds {MAX_PAYLOAD_BYTES} bytes "
            f"(got {len(body)})")
    try:
        obj = json.loads(bytes(body).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise N8nWebhookError(f"event body is not valid UTF-8 JSON: {exc}")
    if not isinstance(obj, dict):
        raise N8nWebhookError("event must be a JSON object")
    required = {"event_type", "workflow_ref", "event_id", "payload"}
    missing = required - set(obj)
    if missing:
        raise N8nWebhookError(f"event missing keys: {sorted(missing)}")
    extra = set(obj) - required
    if extra:
        raise N8nWebhookError(f"event has unexpected keys: {sorted(extra)}")
    if obj["event_type"] not in _ALLOWED_TYPES:
        raise N8nWebhookError(
            f"unknown event_type {obj['event_type']!r}; "
            f"allowed: {list(_ALLOWED_TYPES)}")
    for k in ("workflow_ref", "event_id"):
        v = obj[k]
        if not isinstance(v, str) or not v.strip():
            raise N8nWebhookError(f"{k} must be a non-empty string")
        if len(v) > 120:
            raise N8nWebhookError(f"{k} exceeds 120 chars")
    if not isinstance(obj["payload"], dict):
        raise N8nWebhookError("payload must be a JSON object")
    return obj


# --- deterministic idempotency key (D-027 lineage) -----------------------

def event_key(event: Dict) -> str:
    """SHA256 over (event_type, workflow_ref, event_id).

    Deterministic: a repeated delivery of the same event yields the
    SAME key (dedup); a distinct event_id yields a distinct key.
    Wall-clock is never key material (D-060 lineage).
    """
    material = "|".join((
        event["event_type"], event["workflow_ref"], event["event_id"]))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


# --- dispatcher (injected handlers, RULES §35) ---------------------------

class N8nEventDispatcher:
    """Wires parsed n8n events to injected handlers by event_type.

    Deterministic idempotency: `dispatch` computes `event_key(event)`
    and consults the injected `seen_keys` store (a callable returning
    a key-membership truth, e.g. the D-027 store or a parity dict) and
    `record_key` (callable persisting the key). A key already present
    is SKIPPED — handlers never fire twice for one event_id. Handler
    exceptions are captured and returned per-event (recorded, never
    silent); they do not abort the batch.
    """

    def __init__(self,
                 handlers: Dict[str, Callable[[Dict], Dict]],
                 seen_keys: Callable[[str], bool],
                 record_key: Callable[[str], None]) -> None:
        unknown = set(handlers) - set(_ALLOWED_TYPES)
        if unknown:
            raise N8nWebhookError(f"handlers registered for unknown "
                                  f"event types: {sorted(unknown)}")
        self._handlers = dict(handlers)
        self._seen = seen_keys
        self._record = record_key

    def dispatch(self, events: List[Dict],
                 logical_now: str) -> Dict:
        """Dispatch a batch of parsed events. Deterministic and
        idempotent; returns a structured per-event verdict list."""
        results = []
        for ev in events:
            key = event_key(ev)
            if self._seen(key):
                results.append({"event_id": ev["event_id"],
                                "key": key, "verdict": "skipped_duplicate"})
                continue
            handler = self._handlers.get(ev["event_type"])
            if handler is None:
                results.append({"event_id": ev["event_id"], "key": key,
                                "verdict": "no_handler",
                                "detail": "no handler registered for "
                                          f"{ev['event_type']}"})
                continue
            try:
                out = handler(ev)
                self._record(key)
                results.append({"event_id": ev["event_id"], "key": key,
                                "verdict": "dispatched",
                                "handler_result": out,
                                "logical_now": logical_now})
            except Exception as exc:  # recorded, never silent
                results.append({"event_id": ev["event_id"], "key": key,
                                "verdict": "handler_error",
                                "detail": f"{type(exc).__name__}: {exc}"})
        return {"results": results, "batch_instant": logical_now}


# --- deterministic local fixtures (mock-first, D-053) ---------------------

def sign_payload(raw_body: bytes, secret: str) -> str:
    """Produce the `sha256=<hex>` signature header value for a body."""
    digest = hmac.new(secret.encode("utf-8"), bytes(raw_body),
                      hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def mock_webhook_payload(event_type: str = "workflow.completed",
                         workflow_ref: str = "GREEN-OPS-ERROR_ROUTER",
                         event_id: str = "ev-0001",
                         payload: Optional[Dict] = None) -> Dict:
    """A deterministic, contract-valid webhook event for tests/drills."""
    if event_type not in _ALLOWED_TYPES:
        raise N8nWebhookError(f"unknown event_type {event_type!r}")
    return {"event_type": event_type, "workflow_ref": workflow_ref,
            "event_id": event_id, "payload": payload or {"ok": True}}

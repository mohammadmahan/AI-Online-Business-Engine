"""Phase 13/14 — commerce state orchestrator (D-081/D-082 composing).

Bidirectional WooCommerce ⇄ PostgreSQL SSOT synchronization and the
Notion pipeline replication seam. Canonical engines are NEVER modified:
this module composes them behind one facade.

Boundary discipline (every seam, every call):

  - D-045: the WooCommerce transport and the Notion provider are
    INJECTED. Nothing here opens sockets or reads credentials.
  - PostgreSQL SSOT stays authoritative: webhook orders enter through
    the canonical `OmsEngine` lifecycle (validation, D-027 dedup by
    client_order_id, D-082 reservation guards) — raw payloads are never
    persisted as state.
  - D-124: every durable ref, receipt, outbox row and summary is
    deep-redacted before persistence.
  - Direction ⓪ order webhooks: verify (HMAC) → classify → dedup
    (sha256 of the canonical form) → OMS lifecycle. Replays return the
    original outcome; NEVER a second state mutation (at-most-once).
  - Direction ① SSOT → Woo: the OMS transition is committed FIRST;
    the HTTP call is attempted only after durability, classified via
    the D-052 taxonomy; `push_refund` routes through the canonical
    `OmsEngine.transition` so the SSOT can never drift from the
    lifecycle.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any, Callable, Dict, List, Optional

from services.sync_engine import IntegrityError

from canonical.oms_engine import OmsEngine
from canonical.oms_contracts import (
    CANCELLED, COMPLETED, OmsContractError, REFUNDED,
)
from canonical.resilience import RetryPolicy
from local.src.memory.vector_store import deep_redact

try:  # battery package path or script cwd path
    from ..memory.vector_store import deep_redact
except ImportError:  # pragma: no cover - cwd import
    from src.memory.vector_store import deep_redact

__all__ = [
    "WooWebhookError", "CommerceSyncOrchestrator", "NotionReplicationService",
]


class WooWebhookError(ValueError):
    """Webhook rejected: missing/invalid HMAC or malformed payload."""


def _redact(x: Any) -> Any:
    return deep_redact(x) if isinstance(x, str) else x


def _norm(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {k: _norm(v) for k, v in sorted(payload.items())}
    if isinstance(payload, (list, tuple)):
        return [_norm(v) for v in payload]
    return payload


def _payload_fingerprint(payload: Dict) -> str:
    """Order-addressing fingerprint: only fields that identify the
    order and its intent. A same-order address-change re-webhook is a
    DUPLICATE; a same-id different-intent payload is a CONFLICT."""
    intent = {
        "order_id": payload.get("order_id"),
        "client_order_id": payload.get("client_order_id"),
        "customer_ref": payload.get("customer_ref"),
        "line_items": payload.get("line_items"),
    }
    return hashlib.sha256(
        json.dumps(_norm(intent), ensure_ascii=False, sort_keys=True)
        .encode("utf-8")).hexdigest()


class CommerceSyncOrchestrator:
    """WooCommerce ⇄ SSOT bidirectional sync over the canonical OMS."""

    def __init__(self, oms: OmsEngine, *, transport: Optional[Callable] = None,
                 secret: str = "", classify: Optional[Callable] = None):
        self.oms = oms
        self._transport = transport      # D-045: injected only
        self._secret = secret            # for HMAC verify (test-visible)
        self._classify = classify or (lambda exc: RetryPolicy().classify(exc))

    # -- inbound webhooks -------------------------------------------------
    def verify_webhook(self, body: bytes, signature: str = "") -> bool:
        if not isinstance(body, (bytes, bytearray)) or not body:
            return False
        if not signature or not isinstance(signature, str):
            return False
        expected = hmac.new(self._secret.encode("utf-8"), bytes(body),
                            hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    def ingest_order_webhook(self, payload: Dict, *,
                             verified: bool = False,
                             signature: str = "",
                             raw_body: bytes = b"") -> Dict:
        """HMAC-verified (fail-closed) → idempotent SSOT order intake.

        Requires explicit `verified=True` OR a verifyable (raw_body,
        signature) pair — a payload alone is NEVER trusted.
        """
        if raw_body and signature:
            verified = self.verify_webhook(raw_body, signature)
        if not verified:
            raise WooWebhookError(
                "webhook rejected: HMAC verification failed (D-045)")
        if not isinstance(payload, dict) or not isinstance(
                payload.get("line_items"), list) or not payload["line_items"]:
            raise WooWebhookError("webhook payload malformed (D-081)")
        fp = _payload_fingerprint(payload)
        prior = self._fingerprint_for(payload)
        if prior is not None:
            if prior != fp:
                return {"accepted": False, "outcome": "conflict",
                        "reason": "payload_conflict_same_order_id",
                        "fingerprint": fp}
            return {"accepted": False, "outcome": "duplicate",
                    "reason": "identical_payload_already_accepted",
                    "fingerprint": fp}
        order = self._order_from_webhook(payload)
        try:
            placed = self.oms.place_order(order)
        except OmsContractError as exc:
            return {"accepted": False, "outcome": "invalid",
                    "reason": str(exc)[:300], "fingerprint": fp}
        except IntegrityError as exc:
            # D-027: a DIFFERENT canonical payload already went terminal
            # under this client_order_id — never silently reprocessed;
            # the webhook layer degrades to a deterministic conflict
            # verdict (human review owns the outcome).
            return {"accepted": False, "outcome": "conflict",
                    "reason": "ssot_conflicting_payload_under_"+
                              "client_order_id (human review, D-027)",
                    "fingerprint": fp}
        if not placed.get("placed"):
            # SSOT already holds this client_order_id (different source
            # path): same order → duplicate; SSOT-internal conflicts
            # (never expected here — the fingerprint pre-check covers
            # webhook-accepted orders) surface as conflict.
            return {"accepted": False, "outcome": "duplicate",
                    "reason": "already_in_ssot",
                    "order_key": placed.get("order_key"),
                    "fingerprint": fp}
        self._remember_fingerprint(payload, fp)
        receipt = {
            "outcome": "accepted", "error_class": "", "delivered": True,
            "platform_post_id": placed["order_id"],
            "publish_key": placed["order_key"],
            "detail": deep_redact(
                "order accepted into SSOT lifecycle")[:200],
        }
        return {"accepted": True, "outcome": "accepted",
                "order_key": placed["order_key"],
                "order_id": placed["order_id"], "state": placed["state"],
                "receipt": receipt, "fingerprint": fp}

    # -- outbound transitions ---------------------------------------------
    def push_transition_to_woo(self, order_key: str, to_state: str, *,
                               actor: str = "commerce-sync",
                               fulfillment_receipt: Optional[Dict] = None,
                               reason: Optional[str] = None) -> Dict:
        """Canonical transition FIRST (SSOT authority), then a
        best-effort classified push to the WooCommerce transport."""
        ref = self.oms.transition(
            order_key, to_state, actor=actor,
            fulfillment_receipt=fulfillment_receipt, reason=reason)
        if not ref.get("transitioned"):
            return dict(ref, synced_to_woo=False, sync_outcome="skipped",
                        sync_detail=ref.get("reason", "not_transitioned"))
        sync = self._push(order_key, to_state, ref)
        return dict(ref, **sync)

    def push_refund(self, order_key: str, *,
                    actor: str = "commerce-sync",
                    reason: Optional[str] = None) -> Dict:
        """Refunds go THROUGH the canonical lifecycle — never a raw
        HTTP call that could leave the SSOT contradicting itself."""
        return self.push_transition_to_woo(
            order_key, REFUNDED, actor=actor, reason=reason)

    def _push(self, order_key: str, to_state: str, ref: Dict) -> Dict:
        if self._transport is None:
            return {"synced_to_woo": False,
                    "sync_outcome": "degraded:no_transport"}
        detail = self._transition_detail(order_key, to_state)
        try:
            self._transport(json.dumps(
                detail, ensure_ascii=False, sort_keys=True).encode("utf-8"))
        except Exception as exc:  # noqa: BLE001 - classified, never fatal
            cls = self._classify(exc)
            return {"synced_to_woo": False,
                    "sync_outcome": f"sync_failed:{cls}",
                    "sync_detail": _redact(str(exc))[:300]}
        return {"synced_to_woo": True, "sync_outcome": "synced"}

    # -- state surface ------------------------------------------------------
    def order_state(self, order_key: str) -> Optional[str]:
        return self.oms.state(order_key)

    def oms_order_state(self, order_key: str) -> Optional[str]:
        return self.oms.state(order_key)

    # -- internals ----------------------------------------------------------
    def _transition_detail(self, order_key: str, to_state: str) -> Dict:
        d = {"event": "order.updated" if to_state != REFUNDED
             else "order.refunded",
             "order_key": order_key, "to_state": to_state,
             "source": "commerce-sync-orchestrator"}
        ref = self.oms._order_ref(order_key) or {}
        cust = ref.get("customer_ref")
        if isinstance(cust, str) and cust:
            d["customer_ref"] = cust
        return {k: _redact(v) for k, v in d.items()}

    def _order_from_webhook(self, payload: Dict) -> Dict:
        """WooCommerce webhook → canonical D-081 order contract.

        Required canonical fields (order_id, client_order_id,
        customer_ref, line_items with product_id/variant_id/sku/
        quantity/unit_price_minor, placed_at) must be present; the
        webhook may carry them natively (mapped 1:1) or the adapter
        fills deterministic defaults for the fields Woo does not
        define (placed_at at ingest, currency IRT)."""
        items = []
        for it in payload["line_items"]:
            items.append({
                "product_id": str(
                    it.get("product_id") or payload.get("order_id", "")),
                "variant_id": str(
                    it.get("variant_id") or it.get("product_id")
                    or payload.get("order_id", "")),
                "sku": str(it.get("sku") or it.get("stock_key") or ""),
                "quantity": int(it.get("quantity", 0)),
                "unit_price_minor": int(
                    it.get("unit_price_minor", it.get("unit_price", 0))),
            })
        order = {
            "order_id": str(payload.get("order_id", "")),
            "client_order_id": str(payload.get(
                "client_order_id", payload.get("order_id", ""))),
            "customer_ref": str(payload.get("customer_ref", "")),
            "line_items": items,
            "placed_at": str(payload.get(
                "placed_at") or payload.get("date_created_gmt")
                or "webhook-ingest"),
        }
        if payload.get("currency") is not None:
            order["currency"] = payload["currency"]
        return order

    # D-027-style durable dedup bookkeeping for webhook intake. The
    # SSOT store is the authority; these small ref rows keep the
    # webhook-addressing fingerprints replay-safe and auditable.
    def _fingerprint_for(self, payload: Dict) -> Optional[str]:
        try:
            refs = self.oms.store.succeeded_references("woo-webhook")
        except Exception:  # noqa: BLE001 - dedup must not break intake
            return None
        want = "order:" + str(payload.get("order_id", ""))
        for ref in refs:
            if not isinstance(ref, dict):
                continue
            eid = str(ref.get("event_id", ""))
            if not eid.startswith("woo|order|"):
                continue
            blob = str(ref.get("result_reference", ""))
            if f'"event_id": "{want}"' in blob or \
                    f'"event_id":"{want}"' in blob:
                return self._fp_from_row(blob)
        return None

    def _fp_from_row(self, blob: str) -> Optional[str]:
        try:
            d = json.loads(blob)
        except (ValueError, TypeError):
            return None
        fp = d.get("fingerprint")
        return fp if isinstance(fp, str) else None

    def _remember_fingerprint(self, payload: Dict, fp: str) -> None:
        try:
            eid = f"woo|order|order:{payload.get('order_id', '')}"
            self.oms.store.receive("woo-webhook", eid, "webhook_accept",
                                   {"fingerprint": fp})
            self.oms.store.begin("woo-webhook", eid)
            self.oms.store.succeed(
                "woo-webhook", eid,
                result_reference=json.dumps(
                    {"event_id": f"order:{payload.get('order_id', '')}",
                     "fingerprint": fp}, ensure_ascii=False,
                    sort_keys=True))
        except Exception:  # noqa: BLE001 - never break intake
            pass


class NotionReplicationService:
    """SSOT → Notion workspace replication (Phase 14 seam).

    Composes the shipped boundary (`local/services/notion_adapter.py`):
    the Notion API provider is INJECTED (D-045), ingested events enter
    through the canonical `ingest_notion_event` with its deterministic
    Class-B/E taxonomy. Backpressure is explicit: a bounded queue; a
    full queue fails closed with `backpressure` (never unbounded
    growth, never silent drops).
    """

    def __init__(self, *, poller, queue=None, max_queue: int = 1000):
        self.poller = poller            # NotionPoller (injected provider)
        self.queue = queue
        self._max = int(max_queue)

    def poll(self, *, batch_size: int = 100) -> dict:
        return self.poller.poll(batch_size=batch_size)

    def backlog(self) -> int:
        return self.queue.qsize() if hasattr(self.queue, "qsize") else 0

    def accept_replication(self, payload: Dict) -> dict:
        """Backpressure check then canonical ingestion (fail-closed)."""
        if self.queue is not None and hasattr(self.queue, "qsize"):
            if self.queue.qsize() >= self._max:
                return {"status": "failed", "reason": "backpressure",
                        "accepted": False}
        from canonical.notion_ingest import ingest_notion_event
        result = ingest_notion_event(payload, store=self.poller.store,
                                     queue=self.queue,
                                     actor="commerce-sync")
        result["accepted"] = result.get("status") == "succeeded"
        return result

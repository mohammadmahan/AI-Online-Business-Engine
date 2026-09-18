"""Phase 24 — M2 concrete bindings (D-129..D-131).

Declared pairs and audited adapters over the shipped backends. The
parity/pair FACTORIES take a caller-supplied ``run_tag`` so every
key the live-PG legs touch is run-scoped (durable ledgers are never
cleaned — the Phase 21 lesson).
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import uuid
from typing import Any, Callable, Dict, Optional, Tuple

if __name__ == "__main__" or True:  # canonical import bootstrap
    _HERE = os.path.dirname(os.path.abspath(__file__))
    _LOCAL = os.path.dirname(_HERE)
    for _p in (_LOCAL, _HERE, os.path.join(_LOCAL, "services"),
               os.path.join(_LOCAL, "scripts")):
        if _p not in sys.path:
            sys.path.insert(0, _p)

from canonical import portability as P  # noqa: E402
from canonical import portability_contracts as PC  # noqa: E402
from canonical.ai_observability import AiObservabilityCollector  # noqa: E402
from canonical.ai_providers_live import FallbackProvider  # noqa: E402
from canonical.ai_runtime import AiRequest, MockAiProvider  # noqa: E402
from canonical.analytics_engine import (  # noqa: E402
    _JsonCursorStore,
    _PgCursorStore,
)
from canonical.budget_contracts import ResourceBudget  # noqa: E402
from canonical.budget_engine import BudgetLedger  # noqa: E402
from canonical.obs_contracts import TraceContext  # noqa: E402
from canonical.oms_engine import JsonInventory, PgInventory  # noqa: E402
from canonical.scheduling_engine import _JsonSlotLocks, _PgSlotLocks  # noqa: E402
from services.media_store import LocalObjectStore  # noqa: E402

try:  # live lock backends import lazily inside engines; mirror that
    from canonical.notification_engine import _JsonLocks, _PgLocks  # noqa: E402
except Exception:  # pragma: no cover — offline environments
    _JsonLocks = _PgLocks = None

__all__ = [
    "METADATA_KEYS", "AuditingLocalObjectStore", "local_object_store",
    "slot_locks_pair", "delivery_locks_pair", "analytics_cursor_pair",
    "inventory_pair", "ALL_PARITY_PAIRS", "provider_lockout_pair",
    "lockout_probe",
]


# ============================================================================
# D-130 — audited media store binding
# ============================================================================

#: the ONLY metadata fields a conforming store may persist (D-121
#: zero-leak clause: wall-clock timestamps are not declared fields).
METADATA_KEYS = frozenset({"content_type", "size", "metadata"})


class AuditingLocalObjectStore(LocalObjectStore):
    """LocalObjectStore under the D-130 media contract: head() speaks
    the declared shape (metadata merged, wall-clock pruned) and put()
    persists only declared metadata fields."""

    def put(self, data: bytes, content_type: str,
            metadata: dict = None) -> dict:
        result = super().put(data, content_type, metadata)
        meta_path = self._path(result["object_key"]) + ".meta.json"
        try:
            with open(meta_path, encoding="utf-8") as fh:
                raw = json.load(fh)
        except (FileNotFoundError, json.JSONDecodeError):
            return result
        pruned = {k: raw[k] for k in METADATA_KEYS if k in raw}
        tmp = meta_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(pruned, fh, ensure_ascii=False, sort_keys=True)
        os.replace(tmp, meta_path)
        return result

    def head(self, object_key: str) -> dict:
        raw = super().head(object_key)
        merged = dict(raw.get("metadata", {}))
        for k in ("content_type", "size"):
            if k in raw:
                merged[k] = raw[k]
        return merged


def local_object_store(root: Optional[str] = None,
                       bucket: str = "p24-media") -> AuditingLocalObjectStore:
    return AuditingLocalObjectStore(
        root=root or tempfile.mkdtemp(prefix="p24-media-"), bucket=bucket)


# ============================================================================
# D-130 — the four declared backend parity pairs
# ============================================================================

def _tmp_json(run_tag: str, kind: str) -> str:
    return os.path.join(tempfile.mkdtemp(prefix="p24-json-"),
                        f"{run_tag}-{kind}.json")


def slot_locks_pair(run_tag: str, live_ready: Callable[[], bool]
                    ) -> P.BackendPair:
    """scheduling.slot_locks: JSON parity vs live PG (D-095/D-096)."""
    platform = "portability"
    keys = [f"{platform}\x1fp24-{run_tag}-{i}" for i in range(2)]

    def claim_first(b, ctx):
        return b.claim(keys[0], {"post_id": "post-1",
                                 "scheduled_for": ctx["slot"]})

    def claim_again(b, ctx):
        return {"acquired": b.claim(keys[0], {"post_id": "post-2",
                                              "scheduled_for": ctx["slot"]})["acquired"]}

    def supersede(b, ctx):
        b.supersede(keys[0], "post-1", (platform, keys[1]))
        return "superseded"

    def reclaim(b, ctx):
        return b.claim(keys[0], {"post_id": "post-3",
                                 "scheduled_for": ctx["slot"]})["acquired"]

    return P.BackendPair(
        name="slot_locks",
        offline_factory=lambda: _JsonSlotLocks(
            _tmp_json(run_tag, "slotlocks")),
        live_factory=_PgSlotLocks,
        matrix=P.OperationMatrix(ops={
            "claim_fresh": claim_first,
            "claim_contended": claim_again,
            "supersede": supersede,
            "reclaim_after_supersede": reclaim,
        }),
        live_ready=live_ready,
    )


def delivery_locks_pair(run_tag: str, live_ready: Callable[[], bool]
                        ) -> P.BackendPair:
    """notifications.delivery_lock: JSON parity vs live PG (D-070/D-079)."""
    if _JsonLocks is None:
        raise P.PortabilityError("notification lock backends unavailable")
    key = f"p24-{run_tag}-delivery"

    def acquire1(b, ctx):
        return b.acquire(key, {"attempt": 1, "run": run_tag})["acquired"]

    def acquire2(b, ctx):
        return b.acquire(key, {"attempt": 2, "run": run_tag})["acquired"]

    def get_before(b, ctx):
        return (b.get(key) or {}).get("attempt")

    def finalize(b, ctx):
        b.finalize(key, {"attempt": 1, "run": run_tag, "done": True})
        return "finalized"

    def get_after(b, ctx):
        return (b.get(key) or {}).get("done") is True

    return P.BackendPair(
        name="delivery_locks",
        offline_factory=lambda: _JsonLocks(_tmp_json(run_tag, "delivery")),
        live_factory=_PgLocks,
        matrix=P.OperationMatrix(ops={
            "acquire_fresh": acquire1,
            "acquire_contended": acquire2,
            "get_before_finalize": get_before,
            "finalize": finalize,
            "get_after_finalize": get_after,
        }),
        live_ready=live_ready,
    )


def analytics_cursor_pair(run_tag: str, live_ready: Callable[[], bool]
                          ) -> P.BackendPair:
    """analytics.cursor: JSON parity vs live PG (D-085/D-086)."""
    seq = 24000 + (int(uuid.uuid5(uuid.NAMESPACE_URL,
                                  "p24/" + run_tag).hex[:6], 16) % 1000)
    rollups = {"day": {"p24_metric": {"value": seq, "count": 1}}}

    def cur0(b, ctx):
        return b.get_cursor() == 0 or b.get_cursor() == seq

    def advance(b, ctx):
        b.advance(seq, rollups)
        return "advanced"

    def cur1(b, ctx):
        return b.get_cursor() == seq

    return P.BackendPair(
        name="analytics_cursor",
        offline_factory=lambda: _JsonCursorStore(
            _tmp_json(run_tag, "cursor")),
        live_factory=_PgCursorStore,
        matrix=P.OperationMatrix(ops={
            "cursor_initial": cur0,
            "advance": advance,
            "cursor_after": cur1,
        }),
        live_ready=live_ready,
    )


def inventory_pair(run_tag: str, live_ready: Callable[[], bool]
                   ) -> P.BackendPair:
    """oms.inventory: JSON parity vs live PG (D-082/D-084)."""
    variant_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "p24/" + run_tag))
    sku = f"P24-{run_tag}"

    def key_of(b, ctx):
        return b.seed(variant_id, sku, 3)

    def avail0(b, ctx):
        return b.available(ctx["key"]) == 3

    def reserve_ok(b, ctx):
        return b.reserve(ctx["key"], 2, {"order": run_tag})["reserved"]

    def reserve_over(b, ctx):
        v = b.reserve(ctx["key"], 2, {"order": run_tag})
        return v["reserved"] is False

    def release_ok(b, ctx):
        return b.release(ctx["key"], 2, {"order": run_tag})["released"]

    def release_over(b, ctx):
        v = b.release(ctx["key"], 2, {"order": run_tag})
        return v["released"] is False

    return P.BackendPair(
        name="oms_inventory",
        offline_factory=lambda: JsonInventory(
            _tmp_json(run_tag, "inventory")),
        live_factory=PgInventory,
        matrix=P.OperationMatrix(ops={
            "seed": key_of,
            "available_initial": avail0,
            "reserve_within": reserve_ok,
            "reserve_over": reserve_over,
            "release_reserved": release_ok,
            "release_over": release_over,
        }),
        live_ready=live_ready,
    )


def ALL_PARITY_PAIRS(run_tag: str, live_ready: Callable[[], bool]) -> list:
    """The declared D-130 pair set (event/locks family + inventory)."""
    return [
        slot_locks_pair(run_tag, live_ready),
        delivery_locks_pair(run_tag, live_ready),
        analytics_cursor_pair(run_tag, live_ready),
        inventory_pair(run_tag, live_ready),
    ]


# ============================================================================
# D-129 — provider lockout pair (D-066 fallback + D-127 write-through)
# ============================================================================

def provider_lockout_pair(ledger: Optional[BudgetLedger] = None,
                          collector: Optional[AiObservabilityCollector]
                          = None) -> Dict[str, Any]:
    """Locked 'live' primary over the deterministic mock fallback."""
    if ledger is None:
        ledger = BudgetLedger(budgets=[
            ResourceBudget(resource="llm_tokens", limit=10_000_000,
                           window="per_run", scope="green"),
            ResourceBudget(resource="llm_calls", limit=1_000_000,
                           window="per_run", scope="green"),
        ])

    class MeteredFallback(FallbackProvider):
        """FallbackProvider with D-129 write-through on the fallback.
        Declares its composite membership per D-129: responses come
        from the mock member (primary is dead in the lockout probe)."""

        composite_members = ("mock",)

        def __init__(self):
            super().__init__(
                primary=MockAiProvider(fail_with="timeout"),
                collector=collector, task_type="portability",
                template_id="content_idea", template_hash="p24")
            self.ledger = ledger

        def generate(self, request: AiRequest):
            before = ledger.consumed("llm_calls", "per_run", "green")
            resp = super().generate(request)
            if ledger.consumed("llm_calls", "per_run", "green") == before:
                usage = getattr(resp, "usage", None) or {}
                ledger.consume_llm(
                    tokens=int(usage.get("prompt_tokens", 0))
                    + int(usage.get("completion_tokens", 0)),
                    calls=1, scope="green",
                    correlation_id="portability")
            return resp

    return {"provider": MeteredFallback(), "ledger": ledger}


def lockout_probe(provider: Any, schema_id: str
                  ) -> Dict[str, Any]:
    """Simulated primary lockout: dispatch once, return the verdicts
    the battery pins (fallback used, observability recorded, ledger
    metered exactly once)."""
    trace = TraceContext.root("integrations", "portability-lockout", "0")
    req = AiRequest(task_type=schema_id, schema_id=schema_id,
                    prompt_payload={}, idempotency_tag=trace.trace_id)
    resp = provider.generate(req)
    verdicts = {
        "fallbacks_used": provider.fallbacks_used,
        "responded_by": resp.provider,
        "schema_parsed": resp.parsed is not None,
    }
    if provider.collector is not None:
        rows = [r for r in provider.collector.records()
                if r.get("stage") == "fallback"]
        verdicts["fallback_recorded"] = len(rows) == 1
        verdicts["fallback_status"] = rows[0].get("status") if rows else None
    verdicts["ledger_calls"] = provider.ledger.consumed(
        "llm_calls", "per_run", "green")
    return verdicts

"""Phase 16 — customer support memory bridge (D-142 consumer).

Composes the canonical support surfaces with the D-142 memory layer:

  - `SupportKnowledgeIndex` — embeds product catalogs, FAQ documents,
    return policies and fulfillment notes into the `VectorStore`
    (kinds: interaction/summary/guideline) with deep redaction before
    persistence (D-124) and budget-gated writes (D-127 `memory_ops`).
  - `SupportMemoryBridge` — resolves one customer query: semantic
    KNN over the knowledge index + real-time order/purchase context
    from the SSOT (OMS), then hands the assembled context to a router
    callback. ZERO RUNTIME DISRUPTION: every memory/SSOT lookup is
    failure-isolated — any exception degrades to a deterministic
    template response and is surfaced in `trace.reports`, never raised.

Memory is NEVER authority (D-026/D-027): retrieval is a hint; the SSOT
order state read from the OMS is the only truth used for status.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from local.src.memory.vector_store import (
    MemoryRecord, VectorStore, deep_redact,
)

try:  # battery package path (repo root on sys.path) or cwd path
    from local.src.ai.memory_interceptor import (
        MEMORY_BUDGET_RESOURCE, MemoryOpReport,
    )
except ImportError:  # pragma: no cover - cwd=local invocation
    from src.ai.memory_interceptor import (
        MEMORY_BUDGET_RESOURCE, MemoryOpReport,
    )

__all__ = ["SupportKnowledgeIndex", "SupportMemoryBridge"]


def _template_response(query: str, reason: str) -> Dict:
    """Deterministic degraded response (fail-open to templates)."""
    return {
        "response": (
            "Thank you for reaching out. A support agent will review "
            "your request shortly. (ref: template-resolution)"),
        "source": "template",
        "reason": reason,
        "query": deep_redact(str(query))[:200],
    }


class SupportKnowledgeIndex:
    """Writes support knowledge into the vector store (budget-gated)."""

    def __init__(self, store: Optional[VectorStore] = None,
                 embedder: Optional[Callable[[str], List[float]]] = None,
                 budget=None, agent_id: str = "support-kb"):
        self._store = store
        self._embedder = embedder
        self._budget = budget
        self._agent = agent_id
        self._seq = 0

    def _seq_next(self) -> int:
        self._seq += 1
        return self._seq

    def _budget_ok(self, reports: List[MemoryOpReport], op: str) -> bool:
        if self._budget is None:
            return True
        try:
            verdict = self._budget.check(MEMORY_BUDGET_RESOURCE, 1)
            if not verdict.get("allowed"):
                reports.append(MemoryOpReport(
                    op, False, "budget_refused:pre_dispatch_check"))
                return False
            return True
        except Exception as e:  # noqa: BLE001 - zero-blockage
            reports.append(MemoryOpReport(
                op, False, f"degraded:{type(e).__name__}"))
            return False

    def ingest(self, documents: List[Dict], *, logical_ts: int,
               reports: Optional[List[MemoryOpReport]] = None) -> Dict:
        """Embed + persist knowledge documents.

        Each document: {"kind": faq|product|policy|fulfillment,
        "title": …, "content": …}. Content is deep-redacted BEFORE
        embedding (never embed raw secrets — the vector itself would
        leak). Returns a per-document outcome summary.
        """
        reports = reports if reports is not None else []
        out = {"written": 0, "skipped": 0, "failed": 0}
        if self._store is None or self._embedder is None:
            reports.append(MemoryOpReport(
                "kb_ingest", False, "degraded:no_store"))
            out["skipped"] = len(documents)
            return out
        for i, doc in enumerate(documents):
            op = f"kb_ingest[{i}]"
            if not isinstance(doc, dict) or not str(doc.get("content", "")
                                                   ).strip():
                out["skipped"] += 1
                continue
            if not self._budget_ok(reports, op):
                out["skipped"] += 1
                continue
            try:
                content = deep_redact(
                    f"{doc.get('title', '')}: {doc.get('content', '')}")
                kind = "guideline" if doc.get("kind") != "fulfillment" \
                    else "interaction"
                self._seq += 1
                self._store.put(MemoryRecord(
                    record_id=f"kb-{self._agent}-{self._seq}",
                    agent_id=self._agent, session_id="*",
                    kind=kind, content=content,
                    embedding=self._embedder(content),
                    logical_ts=logical_ts, seq=self._seq))
                out["written"] += 1
            except Exception as e:  # noqa: BLE001 - zero-blockage
                reports.append(MemoryOpReport(
                    op, False, f"degraded:{type(e).__name__}"))
                out["failed"] += 1
        return out


class SupportMemoryBridge:
    """Query resolution with memory retrieval + SSOT order context."""

    def __init__(self, *, store: Optional[VectorStore] = None,
                 embedder: Optional[Callable[[str], List[float]]] = None,
                 order_lookup: Optional[Callable[[str], List[Dict]]] = None,
                 budget=None, router: Optional[Callable] = None,
                 k: int = 4):
        self._store = store
        self._embedder = embedder
        self._order_lookup = order_lookup  # fn(customer_ref) -> [order dicts]
        self._budget = budget
        self._router = router  # fn(context: dict) -> dict (Phase 16 seam)
        self._k = int(k)

    # -- context assembly (every hop failure-isolated) ----------------------
    def _budget_ok(self, reports, op) -> bool:
        if self._budget is None:
            return True
        try:
            verdict = self._budget.check(MEMORY_BUDGET_RESOURCE, 1)
            if not verdict.get("allowed"):
                reports.append(MemoryOpReport(
                    op, False, "budget_refused:pre_dispatch_check"))
                return False
            return True
        except Exception as e:  # noqa: BLE001
            reports.append(MemoryOpReport(
                op, False, f"degraded:{type(e).__name__}"))
            return False

    def _memory_hits(self, query: str, reports) -> List[Dict]:
        if self._store is None or self._embedder is None:
            return []
        if not self._budget_ok(reports, "memory_query"):
            return []
        try:
            vec = self._embedder(query)
            rows = self._store.query(vec, k=self._k)
            return [{"kind": r.get("kind"),
                     "content": r.get("content", "")} for r in rows]
        except Exception as e:  # noqa: BLE001 - zero-blockage
            reports.append(MemoryOpReport(
                "memory_query", False, f"degraded:{type(e).__name__}"))
            return []

    def _order_context(self, customer_ref: Optional[str],
                       reports) -> Dict:
        """Real-time SSOT order state + purchase history (PII-safe:
        only refs/states/ids — never addresses, contacts or payments).
        `order_lookup` is an INJECTED read-only adapter (D-045/D-142):
        the bridge never reaches into the canonical OMS directly."""
        if self._order_lookup is None or not customer_ref:
            return {}
        try:
            orders = self._order_lookup(customer_ref)
            safe = []
            for o in orders[:10]:
                safe.append({
                    "order_key": o.get("order_key", ""),
                    "state": o.get("state", ""),
                    "order_id": o.get("order_id", ""),
                })
            return {"orders": safe, "count": len(safe)}
        except Exception as e:  # noqa: BLE001 - zero-blockage
            reports.append(MemoryOpReport(
                "order_context", False, f"degraded:{type(e).__name__}"))
            return {}

    def resolve(self, query: str, *, customer_ref: Optional[str] = None,
                session_id: str = "session", logical_ts: int = 0
                ) -> Dict:
        """Resolve one support query. NEVER raises for memory/SSOT
        failures — degradation is deterministic and reported."""
        reports: List[MemoryOpReport] = []
        if self._store is None or self._embedder is None:
            return _template_response(
                query, "degraded:no_memory_configured")
        try:
            memory = self._memory_hits(query, reports)
            orders = self._order_context(customer_ref, reports)
            context = {
                "query": deep_redact(str(query))[:500],
                "memory": memory,
                "order_context": orders,
                "session_id": session_id,
                "logical_ts": logical_ts,
            }
            if self._router is not None:
                result = self._router(context)
                if isinstance(result, dict):
                    result.setdefault("source", "router")
                    result.setdefault("reports", reports)
                    return result
            # no router: deterministic template answer over retrieved
            # knowledge (memory is a hint, never authority)
            top = memory[0]["content"] if memory else ""
            answer = top if top else _template_response(
                query, "no_knowledge_match")["response"]
            return {"response": answer, "source":
                    "knowledge" if top else "template",
                    "order_context": orders,
                    "reports": reports}
        except Exception as e:  # noqa: BLE001 - final isolation net
            reports.append(MemoryOpReport(
                "resolve", False, f"degraded:{type(e).__name__}"))
            t = _template_response(query, f"degraded:{type(e).__name__}")
            t["reports"] = reports
            return t

"""Phase 7/8 — agent-memory interceptor (D-142 consumer wiring).

Sits BEHIND the canonical AI boundary and changes nothing about it:
`local.canonical.ai_runtime` stays untouched; this adapter composes
it. D-142 rules enforced:

  - Memory is NEVER authority (D-026/D-027): retrieved context is a
    hint injected into `AiRequest.prompt_payload["memory_context"]`;
    business truth and approvals stay in the canonical store.
  - Zero runtime blockage: EVERY memory operation (retrieval, write,
    WAL export, sync) is wrapped so failures degrade to the default
    zero-shot path and are reported honestly — never raised into the
    AI pipeline.
  - D-127 budget gates: both directions are metered against the
    injected `BudgetLedger` with pre-dispatch `check()` verdicts —
    exhausted budgets skip the memory hop gracefully (recorded, not
    raised) so budget refusal can never break generation either.
  - D-114/D-124: stored interaction content passes the deep redactor
    before persistence (defense in depth — the store re-redacts).

Surfaces:
  - `MemoryContextProvider`  retrieve brand guidelines / top-similarity
    interactions / latest summary for prompt synthesis (Phase 7) and
    quality-evaluation context (Phase 8).
  - `MemoryWritingInterceptor`  append completed interactions and
    evaluation summaries post-generation, with WAL export + best-effort
    MemWal sync.
  - `MemoryEnabledAiRuntime`  composing wrapper around any
    `AiProvider`/runtime callable: context in, metered memory writes
    out, honest degradation throughout.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable, Dict, List, Optional, Tuple

from canonical.ai_runtime import AiRequest, AiResponse
from canonical.budget_engine import BudgetExhausted

from local.src.memory.vector_store import (
    DEFAULT_EMBEDDING_DIM, INTERACTION, SUMMARY, MemoryRecord, VectorStore,
)
from local.src.memory.memwal_adapter import MemWalClientAdapter

try:  # package-relative (battery) or script (cwd=local)
    from ..memory.vector_store import deep_redact  # type: ignore
except ImportError:  # pragma: no cover
    from local.src.memory.vector_store import deep_redact

__all__ = [
    "MEMORY_BUDGET_RESOURCE", "MemoryContextProvider",
    "MemoryWritingInterceptor", "MemoryEnabledAiRuntime",
    "MemoryOpReport",
]

# D-127 resource name metered for ALL memory operations (reads and
# writes). Declared per-run budgets by the host; refusals skip the hop.
MEMORY_BUDGET_RESOURCE = "memory_ops"

DEFAULT_TOP_K = 3


# ---------------------------------------------------------------------------
# Degradation reporting (honest, never raised)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MemoryOpReport:
    """One memory hop's outcome. `ok=False` ALWAYS carries a reason —
    degradation is visible, never silent."""
    op: str            # retrieve | write_interaction | write_summary | sync
    ok: bool
    detail: str


def _guarded(op: str, reports: List[MemoryOpReport], fn: Callable[[], object],
             detail_ok: str) -> Tuple[bool, object]:
    """Run a memory op; ANY failure (store error, budget refusal,
    timeout) degrades to a report instead of an exception."""
    try:
        result = fn()
        reports.append(MemoryOpReport(op, True, detail_ok))
        return True, result
    except BudgetExhausted as e:
        reports.append(MemoryOpReport(op, False, f"budget_refused:{e}"))
        return False, None
    except Exception as e:  # noqa: BLE001 - zero-blockage guarantee (D-142)
        reports.append(MemoryOpReport(op, False,
                                      f"degraded:{type(e).__name__}"))
        return False, None


# ---------------------------------------------------------------------------
# Context provider (read path)
# ---------------------------------------------------------------------------

class MemoryContextProvider:
    """Retrieves memory context for prompt synthesis / evaluation.

    `embedder` is INJECTED and deterministic per host (e.g. a hashing
    embedder or the provider's own embedding endpoint behind an
    owner-authorized transport). On any failure the provider yields an
    empty context — the pipeline continues zero-shot.
    """

    def __init__(self, store: Optional[VectorStore] = None,
                 embedder: Optional[Callable[[str], Tuple[float, ...]]] = None,
                 budget: Optional[object] = None,
                 top_k: int = DEFAULT_TOP_K):
        if (store is None) != (embedder is None):
            raise ValueError("store_and_embedder_required_together")
        self._store = store
        self._embedder = embedder
        self._budget = budget
        self.top_k = top_k

    def retrieve(self, query_text: str,
                 reports: Optional[List[MemoryOpReport]] = None
                 ) -> Dict[str, object]:
        """{guidelines, similar, summary, ok} — safe by construction."""
        reports = reports if reports is not None else []
        empty = {"guidelines": [], "similar": [], "summary": None,
                 "ok": False}
        if self._store is None or self._embedder is None:
            reports.append(MemoryOpReport("retrieve", False,
                                          "degraded:no_store"))
            return empty
        if self._budget is not None:
            try:
                verdict = self._budget.check(MEMORY_BUDGET_RESOURCE, 1)
                if not verdict.get("allowed"):
                    reports.append(MemoryOpReport(
                        "retrieve", False,
                        "budget_refused:pre_dispatch_check"))
                    return empty
            except Exception as e:  # noqa: BLE001 - zero-blockage
                reports.append(MemoryOpReport(
                    "retrieve", False, f"degraded:{type(e).__name__}"))
                return empty
        try:
            vec = self._embedder(query_text)
            hits = self._store.query(vec, k=self.top_k)
            guidelines = self._store.rows(kind="guideline")
            summaries = self._store.rows(kind="summary")
        except Exception as e:  # noqa: BLE001 - zero-blockage
            reports.append(MemoryOpReport("retrieve", False,
                                          f"degraded:{type(e).__name__}"))
            return empty
        reports.append(MemoryOpReport("retrieve", True,
                                      f"hits={len(hits)}"))
        summary = summaries[-1] if summaries else None
        return {"guidelines": guidelines, "similar": hits,
                "summary": summary, "ok": True}

    def empty_context(self) -> Dict[str, object]:
        return {"guidelines": [], "similar": [], "summary": None,
                "ok": False}


# ---------------------------------------------------------------------------
# Writing interceptor (write path)
# ---------------------------------------------------------------------------

class MemoryWritingInterceptor:
    """Appends completed interactions / evaluation summaries to the
    memory surface, best-effort, behind D-127 gates."""

    def __init__(self, store: Optional[VectorStore] = None,
                 wal: Optional[MemWalClientAdapter] = None,
                 embedder: Optional[Callable[[str], Tuple[float, ...]]] = None,
                 budget: Optional[object] = None,
                 seq_start: int = 0):
        if (store is None) != (embedder is None):
            raise ValueError("store_and_embedder_required_together")
        self._store = store
        self._wal = wal
        self._embedder = embedder
        self._budget = budget
        self._seq = seq_start

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
            reports.append(MemoryOpReport(op, False,
                                          f"degraded:{type(e).__name__}"))
            return False

    def _bump_seq(self) -> int:
        self._seq += 1
        return self._seq

    def write_interaction(self, agent_id: str, session_id: str,
                          content: str, logical_ts: int,
                          reports: Optional[List[MemoryOpReport]] = None
                          ) -> Optional[str]:
        reports = reports if reports is not None else []
        if self._store is None or self._embedder is None:
            reports.append(MemoryOpReport("write_interaction", False,
                                          "degraded:no_store"))
            return None
        if not self._budget_ok(reports, "write_interaction"):
            return None
        record_id = f"mem-{agent_id}-{session_id}-{self._bump_seq()}"
        try:
            vec = self._embedder(content)
            self._store.put(MemoryRecord(
                record_id=record_id, agent_id=agent_id,
                session_id=session_id, kind=INTERACTION,
                content=deep_redact(content), embedding=vec,
                logical_ts=logical_ts, seq=self._seq))
        except Exception as e:  # noqa: BLE001 - zero-blockage
            reports.append(MemoryOpReport("write_interaction", False,
                                          f"degraded:{type(e).__name__}"))
            return None
        reports.append(MemoryOpReport("write_interaction", True, record_id))
        return record_id

    def write_summary(self, agent_id: str, session_id: str, content: str,
                      logical_ts: int,
                      reports: Optional[List[MemoryOpReport]] = None
                      ) -> Optional[str]:
        reports = reports if reports is not None else []
        if self._store is None or self._embedder is None:
            reports.append(MemoryOpReport("write_summary", False,
                                          "degraded:no_store"))
            return None
        if not self._budget_ok(reports, "write_summary"):
            return None
        record_id = f"sum-{agent_id}-{session_id}-{self._bump_seq()}"
        try:
            vec = self._embedder(content)
            self._store.put_summary(record_id, agent_id, session_id,
                                    deep_redact(content), vec,
                                    logical_ts, self._seq)
        except Exception as e:  # noqa: BLE001
            reports.append(MemoryOpReport("write_summary", False,
                                          f"degraded:{type(e).__name__}"))
            return None
        reports.append(MemoryOpReport("write_summary", True, record_id))
        return record_id

    def export_and_sync(self, records: List[MemoryRecord], path: str,
                        reports: Optional[List[MemoryOpReport]] = None
                        ) -> None:
        """WAL export + best-effort MemWal sync (offline by default)."""
        reports = reports if reports is not None else []
        if self._wal is None or not records:
            reports.append(MemoryOpReport("sync", False,
                                          "degraded:no_wal_or_empty"))
            return
        try:
            self._wal.export_wal(path, records)
        except Exception as e:  # noqa: BLE001
            reports.append(MemoryOpReport("sync", False,
                                          f"degraded:{type(e).__name__}"))
            return
        sync = self._wal.sync(records)
        reports.append(MemoryOpReport(
            "sync", not sync.degraded,
            f"pushed={sync.pushed_remote} kept={sync.kept_local} "
            f"pending={sync.pending_remote} reason={sync.reason}"))


# ---------------------------------------------------------------------------
# Composing runtime wrapper
# ---------------------------------------------------------------------------

class MemoryEnabledAiRuntime:
    """Wraps any AI provider callable with memory context in, metered
    memory writes out. The canonical boundary is untouched: the
    delegate still receives a plain `AiRequest` and returns a plain
    `AiResponse`.

    `request_fn(request) -> AiResponse` (the Phase 7/8 pipeline entry)
    is required; `summarize` (evaluation-summary builder for Phase 8)
    is optional.
    """

    def __init__(self, request_fn: Callable[[AiRequest], AiResponse],
                 provider: MemoryContextProvider,
                 writer: MemoryWritingInterceptor,
                 summarize: Optional[Callable[[AiRequest, AiResponse],
                                              str]] = None,
                 logical_clock: Optional[Callable[[], int]] = None):
        if not callable(request_fn):
            raise ValueError("request_fn_required")
        self._request_fn = request_fn
        self._provider = provider
        self._writer = writer
        self._summarize = summarize
        self._clock = logical_clock or (lambda: 0)

    def generate(self, request: AiRequest, agent_id: str = "ai-pipeline",
                 session_id: str = "default") -> Tuple[AiResponse, Dict]:
        """Run the pipeline with memory context; returns
        `(response, trace)` where trace carries every memory report —
        generation itself NEVER fails because of memory."""
        reports: List[MemoryOpReport] = []
        context = self._provider.retrieve(
            request.prompt_payload.get("topic", "") or
            request.prompt_payload.get("text", ""), reports)
        payload = dict(request.prompt_payload)
        if context.get("ok"):
            payload["memory_context"] = {
                "guidelines": [g.get("content", "") for g in
                               context.get("guidelines", [])],
                "similar": [{"content": h.get("content", ""),
                             "distance": h.get("distance")}
                            for h in context.get("similar", [])],
                "summary": (context.get("summary") or {}).get("content"),
            }
        augmented = replace(request, prompt_payload=payload)
        response = self._request_fn(augmented)

        trace: Dict[str, object] = {"memory_reports": reports,
                                    "memory_context_used": bool(
                                        context.get("ok"))}
        ts = int(self._clock())
        rid = self._writer.write_interaction(
            agent_id, session_id,
            content=f"{request.task_type}|{response.text}",
            logical_ts=ts, reports=reports)
        if rid and self._summarize is not None:
            try:
                summary_text = self._summarize(augmented, response)
            except Exception:  # noqa: BLE001 - summarizer is a hint
                summary_text = None
            if summary_text:
                self._writer.write_summary(
                    agent_id, session_id, summary_text, ts, reports)
        trace["interaction_id"] = rid
        return response, trace

"""Phase 9–12 — context-aware publishing orchestrator (Part A).

Composes the canonical engines into one flow and adds the D-142
feedback loop. NOTHING here replaces a canonical engine: the calendar
(D-093), the anti-race fan-out (D-079), the outbox vaults (D-070),
the provenance chain, and the memory layer are all injected as-is.

Flow (one scheduled post):
  1. `schedule`     — canonical SchedulingEngine claim (idempotency +
     per-platform slot locks) → durable SCHEDULED.
  2. `run_due_post` — canonical DUE transition → per-target dispatch
     through the injected channel dispatchers (mock adapters in every
     hermetic run) → normalized receipts.
  3. Retry circuit  — `retry_policy.RetryPolicy` decides
     published/duplicate/retry/dead_letter per target from the
     receipt's outcome + error class (deterministic, D-126 no-jitter);
     DLQ rows are DURABLE (SSOT store) and carry a redacted reason.
  4. Feedback       — for delivered targets, `record_engagement`
     folds platform metrics (likes/comments/reach) into a semantic
     feedback record in VectorStore (budget-gated, deep-redacted) and
     exports a MemWal WAL artifact.

D-142 rules: memory is never authority (the SSOT keeps every receipt);
memory ops are budget-gated and fail-open to the pipeline; every
persisted string passes D-124 redaction.
"""
from __future__ import annotations

import json
from typing import Callable, Dict, List, Optional

from canonical.scheduling_engine import SchedulingEngine
from canonical.scheduling_contracts import ST_DUE

from local.src.memory.vector_store import (
    DEFAULT_EMBEDDING_DIM, INTERACTION, MemoryRecord, VectorStore,
    deep_redact,
)
from local.src.memory.memwal_adapter import MemWalClientAdapter
from local.src.ai.memory_interceptor import (
    MEMORY_BUDGET_RESOURCE, MemoryOpReport,
)

from .retry_policy import (
    OUTCOME_DLQ, OUTCOME_DUPLICATE, OUTCOME_PUBLISHED, OUTCOME_RETRY,
    RetryPolicy,
)

__all__ = ["PublishingOrchestrator", "DLQ_KIND", "DLQ_STATUS_OPEN"]

DLQ_KIND = "publishing.dlq_entry"
DLQ_STATUS_OPEN = "OPEN"


class PublishingOrchestrator:
    """Multi-channel publishing with memory feedback."""

    def __init__(self, scheduler: SchedulingEngine,
                 dispatchers: Dict[str, object],
                 store=None,
                 memory: Optional[VectorStore] = None,
                 wal: Optional[MemWalClientAdapter] = None,
                 embedder: Optional[Callable[[str], tuple]] = None,
                 budget: Optional[object] = None,
                 retry: Optional[RetryPolicy] = None,
                 ssot_append: Optional[Callable[[Dict], object]] = None,
                 actor: str = "pub-orchestrator"):
        if not dispatchers:
            raise ValueError("dispatchers_required")
        self.scheduler = scheduler
        self.dispatchers = dict(dispatchers)
        self.store = store                      # durable SSOT (DLQ rows)
        self.memory = memory
        self.wal = wal
        self._embedder = embedder
        self._budget = budget
        self.retry = retry or RetryPolicy()
        self._ssot_append = ssot_append
        self._actor = actor
        self._mem_seq = 0

    # -- scheduling (canonical) ---------------------------------------------
    def schedule(self, post: Dict) -> Dict:
        return self.scheduler.schedule(post)

    # -- dispatch (canonical publishers + retry circuit) ----------------------
    def _budget_ok(self, op: str, reports: List[MemoryOpReport]) -> bool:
        if self._budget is None:
            return True
        try:
            verdict = self._budget.check(MEMORY_BUDGET_RESOURCE, 1)
            if not verdict.get("allowed"):
                reports.append(MemoryOpReport(op, False,
                                              "budget_refused:check"))
                return False
            return True
        except Exception as e:  # noqa: BLE001 - feedback never blocks
            reports.append(MemoryOpReport(op, False,
                                          f"degraded:{type(e).__name__}"))
            return False

    def _dlq(self, post_id: str, target: str, decision, receipt: Dict,
             reports: List[MemoryOpReport]) -> Dict:
        row = {
            "kind": DLQ_KIND, "post_id": post_id, "target": target,
            "status": DLQ_STATUS_OPEN,
            "attempt_no": decision.attempt_no,
            "reason": decision.reason,
            "outcome": receipt.get("outcome", ""),
            "error_class": receipt.get("error_class", ""),
            "detail": receipt.get("detail", ""),
            "publish_key": receipt.get("publish_key", ""),
        }
        written = False
        if self._ssot_append is not None:
            try:
                self._ssot_append(row)
                written = True
            except Exception as e:  # noqa: BLE001
                reports.append(MemoryOpReport(
                    "dlq", False, f"degraded:{type(e).__name__}"))
        elif self.store is not None:
            try:
                eid = f"publishing|dlq|{post_id}|{target}|" \
                      f"{decision.attempt_no}"
                rec = self.store.receive("publishing", eid, "dlq_route",
                                         row)
                if rec.get("verdict") in ("new", "retry"):
                    self.store.begin("publishing", eid)
                    self.store.succeed(
                        "publishing", eid,
                        result_reference=json.dumps(
                            row, ensure_ascii=False, sort_keys=True))
                written = True
            except Exception as e:  # noqa: BLE001
                reports.append(MemoryOpReport(
                    "dlq", False, f"degraded:{type(e).__name__}"))
        reports.append(MemoryOpReport(
            "dlq", written, f"{post_id}/{target}:{decision.reason}"))
        return row

    def run_due_post(self, post_id: str, now_iso: str,
                     payloads: Optional[Dict[str, Dict]] = None,
                     reports: Optional[List[MemoryOpReport]] = None,
                     ) -> Dict:
        """Mark DUE (canonical), dispatch every target, classify with
        the retry circuit, persist DLQ rows durably. Returns the
        per-target decision map."""
        reports = reports if reports is not None else []
        view = self.scheduler.calendar_view().get(post_id, {})
        status = view.get("status")
        if status != "SCHEDULED":
            # DISPATCHED/CANCELLED are terminal (D-096): a second
            # trigger is skipped durably — at-most-once at the post
            # level, never a re-send.
            return {"post_id": post_id, "skipped": True,
                    "reason": f"terminal_or_unknown_status:{status}"}
        due = self.scheduler.mark_due(post_id, now_iso)
        if not due.get("ok"):
            return {"post_id": post_id, "skipped": True,
                    "reason": due.get("reason", "not_due")}
        results: Dict[str, Dict] = {}
        for target, dispatcher in self.dispatchers.items():
            payload = (payloads or {}).get(target, {})
            attempt = 0
            backoff_total = 0
            while True:
                attempt += 1
                try:
                    receipt = dispatcher.dispatch(payload,
                                                  actor=self._actor)
                except Exception as exc:  # isolation, D-077 pattern
                    receipt = {"outcome": "target_dispatch_crashed",
                               "error_class": "E",
                               "error": str(exc)[:200]}
                decision = self.retry.decide(
                    receipt.get("outcome", "unknown"),
                    receipt.get("error_class", ""),
                    attempt_no=attempt,
                    idempotency_hit=receipt.get("outcome")
                    == "duplicate_publish_blocked")
                if decision.action == OUTCOME_RETRY:
                    backoff_total += decision.backoff_ticks
                    continue  # deterministic ladder; the canonical
                    # publisher's durable vault keeps attempts
                    # restart-safe and at-most-once
                break
            if decision.action == OUTCOME_DLQ:
                row = self._dlq(post_id, target, decision, receipt,
                                reports)
                results[target] = {"action": decision.action,
                                   "reason": decision.reason,
                                   "attempts": attempt,
                                   "backoff_ticks": backoff_total,
                                   "dlq": row}
            else:
                results[target] = {"action": decision.action,
                                   "reason": decision.reason,
                                   "attempts": attempt,
                                   "backoff_ticks": backoff_total,
                                   "platform_post_id":
                                       receipt.get("platform_post_id",
                                                   "")}
        return {"post_id": post_id, "targets": results}

    # -- engagement feedback into memory (D-142) ------------------------------
    def _next_seq(self) -> int:
        self._mem_seq += 1
        return self._mem_seq

    def record_engagement(self, post_id: str, target: str,
                          metrics: Dict, caption: str = "",
                          logical_ts: int = 0,
                          reports: Optional[List[MemoryOpReport]] = None,
                          ) -> Optional[str]:
        """Fold platform engagement (likes/comments/reach) into a
        semantic feedback record so future generation learns from
        top-performing posts. Budget-gated, deep-redacted, never
        raises."""
        reports = reports if reports is not None else []
        if self.memory is None or self._embedder is None:
            reports.append(MemoryOpReport("feedback", False,
                                          "degraded:no_memory"))
            return None
        if not self._budget_ok("feedback", reports):
            return None
        try:
            clean = {k: v for k, v in metrics.items()
                     if isinstance(v, (int, float)) and not isinstance(v, bool)}
            content = deep_redact(
                f"feedback|{target}|post={post_id}|"
                f"caption={caption}|metrics="
                + ",".join(f"{k}={v}" for k, v in sorted(clean.items())))
            record_id = f"fb-{target}-{post_id}-{self._next_seq()}"
            self.memory.put(MemoryRecord(
                record_id=record_id, agent_id="publishing",
                session_id=post_id, kind=INTERACTION, content=content,
                embedding=self._embedder(content),
                logical_ts=logical_ts, seq=self._next_seq()))
        except Exception as e:  # noqa: BLE001
            reports.append(MemoryOpReport("feedback", False,
                                          f"degraded:{type(e).__name__}"))
            return None
        reports.append(MemoryOpReport("feedback", True, record_id))
        return record_id

    def export_feedback_wal(self, records: List[MemoryRecord], path: str,
                            reports: Optional[List[MemoryOpReport]] = None,
                            ) -> Optional[Dict]:
        """Portable WAL export of the feedback records (best-effort)."""
        reports = reports if reports is not None else []
        if self.wal is None or not records:
            reports.append(MemoryOpReport("wal_export", False,
                                          "degraded:no_wal_or_empty"))
            return None
        try:
            desc = self.wal.export_wal(path, records)
        except Exception as e:  # noqa: BLE001
            reports.append(MemoryOpReport("wal_export", False,
                                          f"degraded:{type(e).__name__}"))
            return None
        reports.append(MemoryOpReport("wal_export", True,
                                      f"rows={desc['row_count']}"))
        return desc

"""Phase 7/8 — campaign-winner prompt context (D-142 consumer).

Part B of the analytics wiring: the `campaign-winners` memory
session persisted by `CampaignAnalyticsEngine` (commit `b4b1d1b`)
now enters Phase 7/8 prompt construction through a composing adapter.

Discipline:
  - Read-only over the D-142 store: winners are retrieved via
    `VectorStore.rows(agent_id=...)`, re-redacted on the read path
    by the store itself, and NEVER written back by this adapter
    (memory stays advisory, D-026/D-027).
  - Bounded assembly: `max_winners` caps retrieval; each winner
    contributes one fixed-size content line; `max_chars` bounds the
    joined block. Deterministic order: seq desc (newest winners
    first), record_id asc as the tie-break — a TOTAL order.
  - D-127: the assembly performs one pre-dispatch `memory_ops`
    check (same resource as the memory layer); refusal degrades to
    zero-shot context with a named report.
  - Zero-blockage: ANY failure (missing store, store error, budget
    refusal, malformed rows) degrades to a baseline context dict —
    the Phase 7/8 pipeline never raises because of memory.
  - Drop-in composition: `context()` returns the same shape as
    `MemoryContextProvider.retrieve` plus a `winners` key, so
    `MemoryEnabledAiRuntime`-style wrappers can merge both.
"""
from __future__ import annotations

import re
from typing import Callable, Dict, List, Optional, Tuple

try:  # package-relative (battery) or script (cwd=local)
    from local.src.ai.memory_interceptor import (  # type: ignore
        MEMORY_BUDGET_RESOURCE,
        MemoryOpReport,
    )
    from local.src.memory.vector_store import deep_redact  # type: ignore
except ImportError:  # pragma: no cover - script path
    from ai.memory_interceptor import (  # type: ignore
        MEMORY_BUDGET_RESOURCE,
        MemoryOpReport,
    )
    from memory.vector_store import deep_redact  # type: ignore

__all__ = ["CampaignWinnerContext", "WINNERS_AGENT_ID", "PARSE_RE"]

WINNERS_AGENT_ID = "analytics"

# The renderer contract from campaign_correlator._render:
#   campaign_winner id=<id> [theme=<t>] revenue_minor=<n> orders=<n>
#   roas=<r> conv_rate=<c> likes=<n> comments=<n>
PARSE_RE = re.compile(
    r"campaign_winner\s+id=(?P<id>\S+)"
    r"(?:\s+theme=(?P<theme>\S+))?"
    r"\s+revenue_minor=(?P<revenue>-?\d+)"
    r"\s+orders=(?P<orders>-?\d+)"
    r"\s+roas=(?P<roas>-?[\d.]+)"
    r"\s+conv_rate=(?P<conv>-?[\d.]+)"
    r"\s+likes=(?P<likes>-?\d+)"
    r"\s+comments=(?P<comments>-?\d+)")


class CampaignWinnerContext:
    """Deterministic winner-context retrieval for Phase 7/8 prompts."""

    def __init__(self, store: Optional[object] = None,
                 budget: Optional[object] = None,
                 max_winners: int = 5, max_chars: int = 1200,
                 agent_id: str = WINNERS_AGENT_ID,
                 session_id: str = "campaign-winners"):
        if max_winners < 1 or max_winners > 100:
            raise ValueError("max_winners_out_of_range")
        if max_chars < 64:
            raise ValueError("max_chars_too_small")
        self._store = store
        self._budget = budget
        self._max_winners = max_winners
        self._max_chars = max_chars
        self._agent_id = agent_id
        self._session_id = session_id

    # -- retrieval ------------------------------------------------------------

    def context(self, reports: Optional[List[MemoryOpReport]] = None
                ) -> Dict[str, object]:
        """Baseline context plus parsed winners. Safe by construction:
        returns a usable dict on every path (zero-blockage)."""
        reports = reports if reports is not None else []
        baseline: Dict[str, object] = {
            "guidelines": [], "similar": [], "summary": None,
            "winners": [], "winners_block": "", "ok": False,
        }
        if self._store is None:
            reports.append(MemoryOpReport("winner_context", False,
                                          "degraded:no_store"))
            return baseline
        if self._budget is not None:
            try:
                verdict = self._budget.check(MEMORY_BUDGET_RESOURCE, 1)
                if not verdict.get("allowed"):
                    reports.append(MemoryOpReport(
                        "winner_context", False,
                        "budget_refused:pre_dispatch_check"))
                    return baseline
            except Exception as e:  # noqa: BLE001 - zero-blockage
                reports.append(MemoryOpReport(
                    "winner_context", False,
                    f"degraded:{type(e).__name__}"))
                return baseline
        try:
            rows = self._store.rows(agent_id=self._agent_id)
        except Exception as e:  # noqa: BLE001 - zero-blockage
            reports.append(MemoryOpReport("winner_context", False,
                                          f"degraded:{type(e).__name__}"))
            return baseline

        session_rows = [r for r in rows
                        if r.get("session_id") == self._session_id]
        if not session_rows:
            reports.append(MemoryOpReport("winner_context", True,
                                          "winners=0"))
            baseline["ok"] = True
            return baseline

        # TOTAL order: seq desc, record_id asc (deterministic)
        session_rows.sort(
            key=lambda r: (-int(r.get("seq", 0)),
                           str(r.get("record_id", ""))))
        winners: List[Dict[str, object]] = []
        for r in session_rows[:self._max_winners]:
            parsed = self._parse(str(r.get("content", "")))
            if parsed is not None:
                winners.append(parsed)
        block = self._assemble(winners)
        reports.append(MemoryOpReport(
            "winner_context", True, f"winners={len(winners)}"))
        baseline.update({"winners": winners,
                         "winners_block": block, "ok": True})
        return baseline

    # -- prompt assembly --------------------------------------------------------

    def assemble_prompt_context(self, base_payload: Dict[str, object],
                                reports: Optional[List[MemoryOpReport]] = None
                                ) -> Dict[str, object]:
        """Merge winner context into a Phase 7/8 prompt payload copy.
        The input payload is NEVER mutated; the winner block rides
        under `memory_context.winners_block` so existing consumers
        keep their shape."""
        payload = dict(base_payload)
        ctx = self.context(reports)
        mc = dict(payload.get("memory_context") or {})
        if ctx.get("ok") and ctx.get("winners"):
            mc["winners_block"] = ctx["winners_block"]
            mc["winners"] = ctx["winners"]
            payload["memory_context"] = mc
        return payload

    # -- parsing (defensive, deterministic) --------------------------------------

    def _parse(self, content: str) -> Optional[Dict[str, object]]:
        """Parse one winner line. Content already passed the store's
        read-path redaction; the theme is defensively re-redacted
        before it reaches a prompt."""
        m = PARSE_RE.search(content)
        if not m:
            return None
        theme = m.group("theme")
        if theme is not None and "[REDACTED]" in theme:
            theme = None  # a redacted theme carries no signal
        try:
            return {
                "campaign_id": m.group("id"),
                "theme": theme,
                "revenue_minor": int(m.group("revenue")),
                "orders": int(m.group("orders")),
                "roas": float(m.group("roas")),
                "conv_rate": float(m.group("conv")),
                "likes": int(m.group("likes")),
                "comments": int(m.group("comments")),
            }
        except (ValueError, TypeError):
            return None

    def _assemble(self, winners: List[Dict[str, object]]) -> str:
        """Bounded joined block: fixed-size lines, hard char cap."""
        lines: List[str] = []
        used = 0
        for w in winners:
            theme = w.get("theme")
            line = (f"winner campaign={w['campaign_id']}"
                    + (f" theme={theme}" if theme else "")
                    + f" roas={w['roas']} revenue_minor="
                      f"{w['revenue_minor']} orders={w['orders']}")
            if used + len(line) > self._max_chars:
                break
            lines.append(line)
            used += len(line) + 1
        return "\n".join(lines)

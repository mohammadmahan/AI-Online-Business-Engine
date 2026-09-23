"""Phase 17/18 — campaign analytics engine (D-142 consumer wiring).

Composes the canonical D-087 `CampaignCorrelator` (publications ⟕
orders on campaign id, INSIDE the read model only) with Phase 9–12
engagement metrics into deterministic ROAS / funnel / attribution
ratios, and persists WINNING-campaign semantic summaries into the
D-142 vector store + portable WAL so future Phase 7/8 generation can
learn from top performers.

Discipline (identical to the memory interceptor):
  - Pure + injected-only: embedder, store writer, WAL exporter and
    budget ledger are constructor-injected; no I/O, no wall clock.
  - Determinism: ranking uses a TOTAL order (revenue desc,
    engagement desc, campaign_id asc) — no tie ambiguity.
  - D-124: every persisted summary passes `deep_redact` BEFORE
    embedding/persistence; reports carry ids and counters only.
  - D-127: each vector write is pre-dispatch gated on `memory_ops`;
    refusal degrades to a named report, never blocks analysis.
  - D-026/D-027: memory is never authority — analytics is read-model
    only, the SSOT stays the single source of truth.
"""
from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple

from canonical.analytics_worker import CampaignCorrelator
from canonical.budget_engine import BudgetExhausted

try:  # package-relative (battery) or script (cwd=local)
    from local.src.memory.vector_store import deep_redact  # type: ignore
except ImportError:  # pragma: no cover - script path
    from src.memory.vector_store import deep_redact  # type: ignore

__all__ = [
    "AnalyticsOpReport", "CampaignAnalyticsEngine",
    "MEMORY_BUDGET_RESOURCE",
]

MEMORY_BUDGET_RESOURCE = "memory_ops"


class AnalyticsOpReport:
    """Named outcome of one optional side effect (zero-blockage)."""

    __slots__ = ("op", "ok", "detail")

    def __init__(self, op: str, ok: bool, detail: str):
        self.op = op
        self.ok = ok
        self.detail = detail

    def as_dict(self) -> Dict[str, str]:
        return {"op": self.op, "ok": self.ok, "detail": self.detail}

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"AnalyticsOpReport({self.op}, {self.ok}, {self.detail})"


class CampaignAnalyticsEngine:
    """Deterministic campaign attribution + winner persistence."""

    def __init__(self,
                 attribution_hours: float = 48.0,
                 writer: Optional[Callable[..., object]] = None,
                 wal_exporter: Optional[Callable[..., object]] = None,
                 budget: Optional[object] = None):
        """`writer(content, kind, reports)` persists one redacted
        summary through the D-142 layer (already budget-gated);
        `wal_exporter(lines, path, reports)` exports the WAL artifact;
        `budget` is a D-127 `BudgetLedger` for the pre-dispatch check
        on the ANALYSIS side (vector writes gate themselves)."""
        self._correlator = CampaignCorrelator(
            attribution_hours=attribution_hours)
        self._writer = writer
        self._wal = wal_exporter
        self._budget = budget

    # -- deterministic metrics ------------------------------------------------

    def analyze(self, publication_records: List[Dict],
                order_records: List[Dict]) -> Dict:
        """Correlate + compute ROAS/funnel ratios per campaign.

        publication_records: {campaign_id, occurred_at, channel?,
        engagement_likes?, engagement_comments?, engagement_reach?,
        cost_minor?, theme?}
        order_records: {source_campaign_id, occurred_at,
        order_total_minor?}

        Pure arithmetic over recorded timestamps — deterministic and
        replayable (D-085/D-087 discipline)."""
        joined = self._correlator.correlate(
            publication_records, order_records)
        eng: Dict[str, Dict[str, int]] = {}
        themes: Dict[str, str] = {}
        for p in publication_records:
            cid = p.get("campaign_id")
            if not cid:
                continue
            e = eng.setdefault(cid, {"likes": 0, "comments": 0,
                                     "reach": 0, "cost_minor": 0})
            e["likes"] += _int(p.get("engagement_likes"))
            e["comments"] += _int(p.get("engagement_comments"))
            e["reach"] += _int(p.get("engagement_reach"))
            e["cost_minor"] += _int(p.get("cost_minor"))
            if p.get("theme"):
                themes[cid] = str(p["theme"])

        campaigns: Dict[str, Dict] = {}
        for cid, buckets in joined.items():
            if cid == "_unattributed":
                continue
            pubs = orders = revenue = unattr = 0
            for cell in buckets.values():
                pubs += cell["publications"]
                orders += cell["orders"]
                revenue += cell["revenue_minor"]
                unattr += cell["unattributed_orders"]
            e = eng.get(cid, {"likes": 0, "comments": 0, "reach": 0,
                              "cost_minor": 0})
            campaigns[cid] = {
                "publications": pubs,
                "orders": orders,
                "unattributed_orders": unattr,
                "revenue_minor": revenue,
                "engagement_likes": e["likes"],
                "engagement_comments": e["comments"],
                "engagement_reach": e["reach"],
                "cost_minor": e["cost_minor"],
                "theme": themes.get(cid),
                # ratios: deterministic div-by-zero policy — 0.0
                "roas": round(revenue / e["cost_minor"], 4)
                if e["cost_minor"] > 0 else 0.0,
                "revenue_per_engagement": round(
                    revenue / (e["likes"] + e["comments"]), 4)
                if (e["likes"] + e["comments"]) > 0 else 0.0,
                "conversion_rate": round(orders / e["reach"], 6)
                if e["reach"] > 0 else 0.0,
            }
        return {"campaigns": campaigns,
                "unattributed_orders": _count_unattributed(joined)}

    def rank(self, analysis: Dict, top_n: int = 3) -> List[Tuple[str, Dict]]:
        """Winners by TOTAL deterministic order: revenue desc,
        engagement desc, campaign_id asc."""
        items = list(analysis["campaigns"].items())
        items.sort(key=lambda kv: (-kv[1]["revenue_minor"],
                                   -(kv[1]["engagement_likes"]
                                     + kv[1]["engagement_comments"]),
                                   kv[0]))
        return items[:max(top_n, 0)]

    # -- winner persistence (D-142 consumer, zero-blockage) -------------------

    def persist_winning_campaigns(self, analysis: Dict, logical_ts: int,
                                  wal_path: Optional[str] = None,
                                  reports: Optional[List[AnalyticsOpReport]] = None
                                  ) -> List[Dict]:
        """Render, redact and persist the top campaigns; export WAL.
        Every side effect degrades to a named report on failure."""
        reports = reports if reports is not None else []
        if self._budget is not None:
            try:
                verdict = self._budget.check(MEMORY_BUDGET_RESOURCE, 1)
                if not verdict.get("allowed"):
                    reports.append(AnalyticsOpReport(
                        "persist", False, "budget_refused:pre_dispatch"))
                    return []
            except BudgetExhausted as e:
                reports.append(AnalyticsOpReport(
                    "persist", False, f"budget_refused:{e.resource}"))
                return []
            except Exception as e:  # noqa: BLE001 - zero-blockage
                reports.append(AnalyticsOpReport(
                    "persist", False, f"degraded:{type(e).__name__}"))
                return []
        winners = self.rank(analysis)
        records: List[Dict] = []
        lines: List[str] = []
        for cid, m in winners:
            content = deep_redact(_render(cid, m))
            records.append({"campaign_id": cid, "content": content,
                            "metrics": {k: m[k] for k in (
                                "revenue_minor", "orders", "roas",
                                "conversion_rate")}})
            lines.append(content)
        if self._writer is not None and records:
            persisted: List[Dict] = []
            try:
                for rec in records:
                    self._writer(rec["content"], "interaction", reports)
                persisted = records
                reports.append(AnalyticsOpReport(
                    "persist", True, f"records={len(records)}"))
            except Exception as e:  # noqa: BLE001 - zero-blockage
                # nothing durably persisted — say so honestly
                reports.append(AnalyticsOpReport(
                    "persist", False, f"degraded:{type(e).__name__}"))
        else:
            persisted = []
        if self._wal is not None and wal_path and lines:
            try:
                self._wal(lines, wal_path, reports)
                reports.append(AnalyticsOpReport("wal", True, wal_path))
            except Exception as e:  # noqa: BLE001 - zero-blockage
                reports.append(AnalyticsOpReport(
                    "wal", False, f"degraded:{type(e).__name__}"))
        return persisted


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _int(value) -> int:
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


def _count_unattributed(joined: Dict) -> int:
    total = 0
    for cell in joined.get("_unattributed", {}).values():
        total += cell["orders"]
    return total


def _render(cid: str, m: Dict) -> str:
    theme = f" theme={m['theme']}" if m.get("theme") else ""
    return (f"campaign_winner id={cid}{theme} "
            f"revenue_minor={m['revenue_minor']} orders={m['orders']} "
            f"roas={m['roas']} conv_rate={m['conversion_rate']} "
            f"likes={m['engagement_likes']} "
            f"comments={m['engagement_comments']}")

"""Phase 23 M3 — deterministic budget engine (D-127, approved).

`BudgetLedger`: append-only consumption rows on the LOGICAL timeline
(no wall clock) with pre-dispatch enforcement identical to D-063:

  consumed + cost < 80% of limit  ⇒ allowed, no warning
  crossing ≥ 80% of the limit     ⇒ allowed + budget_warning
  would exceed the hard limit     ⇒ REFUSED before the consuming call
                                     (Class-B guardrail); the ledger is
                                     unchanged by refusals

Enforcement is ALWAYS active (tested), never ledger-gated — the D-063
property. The Phase 7 AI cost meter (D-063) writes through via
`consume_llm`: one consumption ledger for ALL resource classes.

Ledger rows can be persisted through any injected durable sink (the
established parity/PG pattern); the in-memory store is the canonical
deterministic core.
"""

import threading
from typing import Callable, Dict, List, Optional

from canonical.budget_contracts import (
    BudgetContractError,
    ResourceBudget,
    _SOFT_RATIO,
)


class BudgetExhausted(BudgetContractError):
    """Hard-limit refusal raised by `require()` (pre-dispatch)."""


class BudgetLedger:
    def __init__(self, budgets: List[ResourceBudget],
                 sink: Optional[Callable[[Dict], None]] = None):
        self._lock = threading.Lock()
        self._budgets: Dict[tuple, ResourceBudget] = {}
        for b in budgets:
            k = b.key()
            if k in self._budgets:
                raise BudgetContractError(
                    f"duplicate budget for {k}")
            self._budgets[k] = b
        self._consumed: Dict[tuple, float] = {}
        self._rows: List[Dict] = []
        self._sink = sink

    # -- queries ------------------------------------------------------------

    def budget_for(self, resource: str, window: str, scope: str
                   ) -> Optional[ResourceBudget]:
        return self._budgets.get((resource, window, scope))

    def consumed(self, resource: str, window: str, scope: str) -> float:
        with self._lock:
            return self._consumed.get((resource, window, scope), 0.0)

    def rows(self) -> List[Dict]:
        with self._lock:
            return list(self._rows)

    # -- enforcement ----------------------------------------------------------

    def check(self, resource: str, cost, window: str = "per_run",
              scope: str = "green") -> Dict:
        """Pre-dispatch verdict WITHOUT consuming:
        {allowed, warning, consumed, limit, ratio}."""
        b = self.budget_for(resource, window, scope)
        if b is None:
            raise BudgetContractError(
                f"no budget declared for {resource}/{window}/{scope}")
        if isinstance(cost, bool) or not isinstance(cost, (int, float)) \
                or cost < 0:
            raise BudgetContractError("cost must be a non-negative number")
        with self._lock:
            used = self._consumed.get(b.key(), 0.0)
            total = used + float(cost)
            ratio = total / b.limit
            return {"allowed": total <= b.limit,
                    "warning": ratio >= _SOFT_RATIO and total <= b.limit,
                    "consumed": used, "limit": b.limit, "ratio": ratio}

    def consume(self, resource: str, cost, window: str = "per_run",
                scope: str = "green", logical_at: str = "",
                note: str = "") -> Dict:
        """Deterministic consume-or-refuse. Refusals change nothing."""
        verdict = self.check(resource, cost, window, scope)
        if not verdict["allowed"]:
            raise BudgetExhausted(
                f"hard budget exceeded for {resource}: "
                f"{verdict['consumed']}+{cost} > {verdict['limit']}")
        b = self.budget_for(resource, window, scope)
        with self._lock:
            key = b.key()
            self._consumed[key] = self._consumed.get(key, 0.0) + float(cost)
            row = {"resource": resource, "window": window, "scope": scope,
                   "cost": float(cost), "logical_at": logical_at,
                   "note": note, "warning": verdict["warning"],
                   "consumed_after": self._consumed[key]}
            self._rows.append(row)
        if self._sink is not None:
            self._sink(row)
        return row

    # -- D-063 write-through ----------------------------------------------------

    def consume_llm(self, tokens: int, calls: int = 1,
                    scope: str = "green", logical_at: str = "",
                    correlation_id: str = "") -> Dict:
        """The Phase 7 AI meter writes through: tokens AND calls are
        two resources over one logical event. Raises BudgetExhausted on
        the first hard limit — exactly D-063's pre-dispatch refusal."""
        rows = []
        if tokens:
            rows.append(self.consume("llm_tokens", tokens, "per_run",
                                     scope, logical_at,
                                     note=f"llm:{correlation_id}"))
        if calls:
            rows.append(self.consume("llm_calls", calls, "per_run",
                                     scope, logical_at,
                                     note=f"llm:{correlation_id}"))
        return {"rows": rows, "warning": any(r["warning"] for r in rows)}

    # -- batch helper -------------------------------------------------------------

    def batch(self, items: List[Dict], fn: Callable[[Dict], object],
              resource: str, cost_fn: Callable[[Dict], float],
              window: str = "per_run", scope: str = "green") -> Dict:
        """Process items until the budget refuses; deterministic
        stop-at-first-refusal semantics (no partial overruns)."""
        processed, warnings, refused_at = [], [], None
        for i, item in enumerate(items):
            cost = cost_fn(item)
            try:
                self.consume(resource, cost, window, scope)
            except BudgetExhausted as e:
                refused_at = i
                break
            out = fn(item)
            processed.append(out)
            if self.check(resource, 0, window, scope)["warning"]:
                warnings.append(i)
        return {"processed": processed, "refused_at": refused_at,
                "warnings": warnings,
                "total_items": len(items)}

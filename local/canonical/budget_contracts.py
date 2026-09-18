"""Phase 23 M3 — platform resource-budget contracts (D-127, approved).

Canonical shapes for resource budgets across ALL consumable classes
(D-063 guards AI spend; this generalizes the same guardrail semantics
to every platform resource):

  resources: llm_tokens, llm_calls, api_calls,
             container_cpu_seconds, container_memory_mb
  windows:   per_run | per_logical_day
  scopes:    green | yellow  (RED paths never execute autonomously,
             D-050 — no red budgets exist by construction)

All limits are ENV-CONFIGURABLE (owner directive 2026-09-18): the
declared baselines below are deterministic dummy values for canonical
suites; real limits come from environment parameters, never hard-coded.
"""

import os
from typing import Dict, List, Optional, Tuple

RESOURCES = ("llm_tokens", "llm_calls", "api_calls",
             "container_cpu_seconds", "container_memory_mb")
WINDOWS = ("per_run", "per_logical_day")
SCOPES = ("green", "yellow")

MAX_BUDGETS = 64

# Declared deterministic baselines (canonical-suite dummies; every one
# is overridable via PHASE23_BUDGET_<RESOURCE> env parameters).
DEFAULT_BASELINES: Dict[str, int] = {
    "llm_tokens": 100_000,
    "llm_calls": 500,
    "api_calls": 1_000,
    "container_cpu_seconds": 3_600,
    "container_memory_mb": 8_192,
}

_SOFT_RATIO = 0.8  # D-063-identical: ≥80% ⇒ budget_warning


class BudgetContractError(ValueError):
    """A malformed budget (Class-B programming error)."""


def _fail(reason: str):
    raise BudgetContractError(reason)


def env_overrides() -> Dict[str, int]:
    """Environment-configured limit overrides (deterministic read)."""
    out = {}
    for r in RESOURCES:
        raw = os.environ.get("PHASE23_BUDGET_" + r.upper())
        if raw is None:
            continue
        try:
            val = int(raw)
        except ValueError:
            _fail(f"env budget for {r} is not an integer")
        if val <= 0:
            _fail(f"env budget for {r} must be positive")
        out[r] = val
    return out


def default_budgets() -> List["ResourceBudget"]:
    """Declared baselines + env overrides, as green + yellow budgets
    (per_run windows; the canonical suite baseline)."""
    limits = dict(DEFAULT_BASELINES)
    limits.update(env_overrides())
    budgets = []
    for scope in SCOPES:
        for r in RESOURCES:
            budgets.append(ResourceBudget(r, limits[r], "per_run", scope))
    return budgets


class ResourceBudget:
    """A named, bounded, scoped resource allowance."""

    __slots__ = ("resource", "limit", "window", "scope")

    def __init__(self, resource: str, limit: float, window: str,
                 scope: str = "green"):
        if resource not in RESOURCES:
            _fail(f"unknown resource: {resource}")
        if isinstance(limit, bool) or not isinstance(limit, (int, float)) \
                or limit <= 0:
            _fail("limit must be a positive number")
        if window not in WINDOWS:
            _fail(f"unknown window: {window}")
        if scope not in SCOPES:
            _fail(f"unknown scope: {scope} (red paths are never "
                  "autonomous, D-050)")
        self.resource = resource
        self.limit = limit
        self.window = window
        self.scope = scope

    def key(self) -> Tuple[str, str, str]:
        return (self.resource, self.window, self.scope)

    def to_dict(self) -> Dict:
        return {"resource": self.resource, "limit": self.limit,
                "window": self.window, "scope": self.scope}


def validate_budget(b: Dict) -> ResourceBudget:
    """Validate a budget dict into a ResourceBudget (Class-B on any
    violation)."""
    if not isinstance(b, dict):
        _fail("budget must be a dict")
    for f in ("resource", "limit", "window"):
        if f not in b:
            _fail(f"budget missing field: {f}")
    return ResourceBudget(b["resource"], b["limit"], b["window"],
                          b.get("scope", "green"))


def soft_threshold(budget: ResourceBudget) -> float:
    """≥80% of the limit ⇒ budget_warning (D-063 semantics)."""
    return _SOFT_RATIO * budget.limit

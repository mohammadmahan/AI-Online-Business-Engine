"""Phase 23 M2 — shared resilience envelope (D-126, approved).

One deterministic retry/backoff semantic for every engine:

  - `RetryPolicy`: max attempts, LOGICAL backoff `base * 2^(attempt-1)`
    (jitter FORBIDDEN — the whole platform is deterministic), and a
    retry-classification function bound to the D-052 taxonomy:
    Class A (transient) ⇒ retry, B (schema/contract) / C (auth) /
    E (unknown) ⇒ terminal, D (authority) ⇒ quarantine. The default
    classifier accepts either a ready class letter or a message.
  - `run_with_retry(policy, fn, *, clock=None)`: executes `fn(attempt)`
    until success, the policy gives out, or a terminal class arrives.
    Returns a verdict dict; never raises past the policy (callers get
    a structured outcome). The injected `clock` accumulates logical
    backoff stamps — no wall clock anywhere.
  - `BudgetedExecutor`: wraps `run_with_retry` with a caller-owned
    budget — total attempts AND total failures; once either is
    exhausted, dispatch is refused deterministically (Class-B
    guardrail semantics: refusal happens BEFORE any new attempt).

The psql-transport concurrency ceiling lives with the transport
(`services`/`scripts` layer, injected here) — see
`local/scripts/seed_registry.bounded()`.
"""

from typing import Callable, Dict, List, Optional

from canonical.admin_contracts import AdminContractError

# D-052 class letters (mirrored — importing the JS taxonomy is not
# possible; the letters are the canonical contract)
CLASS_RETRYABLE = "A"
CLASS_TERMINAL = ("B", "C", "E")
CLASS_QUARANTINE = "D"


class ResilienceError(ValueError):
    """A resilience-envelope violation (Class-B programming error)."""


def classify_by_message(message: str) -> str:
    """Deterministic D-052 message classifier (mirror of the canonical
    n8n taxonomy keywords)."""
    m = (message or "").lower()
    if any(k in m for k in ("timeout", "econnrefused", "502", "503",
                            "connection reset", "etimedout")):
        return "A"
    if any(k in m for k in ("schema", "syntax", "invariant", "contract")):
        return "B"
    if any(k in m for k in ("credential", "auth", "401", "403",
                            "permission")):
        return "C"
    if any(k in m for k in ("authority", "forbidden", "red tier",
                            "quarantine")):
        return "D"
    return "E"


class RetryPolicy:
    """Deterministic retry contract."""

    def __init__(self, max_attempts: int = 3, base_backoff: int = 1):
        if not isinstance(max_attempts, int) or isinstance(max_attempts,
                                                           bool) \
                or max_attempts < 1:
            raise ResilienceError("max_attempts must be a positive int")
        if not isinstance(base_backoff, int) or isinstance(base_backoff,
                                                           bool) \
                or base_backoff < 0:
            raise ResilienceError("base_backoff must be a non-negative int")
        self.max_attempts = max_attempts
        self.base_backoff = base_backoff

    def backoff_for(self, attempt: int) -> int:
        """Logical backoff after a FAILED attempt (1-based):
        base * 2^(attempt-1). Jitter forbidden by construction."""
        if attempt < 1:
            raise ResilienceError("attempt starts at 1")
        return self.base_backoff * (2 ** (attempt - 1))

    def classify(self, exc: BaseException) -> str:
        """D-052 class for an exception: explicit `.failure_class`
        attribute wins (canonical errors), else message keywords."""
        explicit = getattr(exc, "failure_class", None)
        if explicit in ("A", "B", "C", "D", "E"):
            return explicit
        return classify_by_message(str(exc))


def run_with_retry(policy: RetryPolicy, fn: Callable,
                   clock: Optional[List[int]] = None,
                   classify: Optional[Callable[[BaseException], str]] = None
                   ) -> Dict:
    """Execute fn(attempt) under the policy. Verdict:
    {ok, result, attempts, backoff_total, outcome, failure_class}
    outcome ∈ succeeded | exhausted_retryable | terminal | quarantined.
    `clock` (optional list) collects the logical backoff stamps."""
    classify = classify or policy.classify
    attempts = 0
    backoff_total = 0
    last_class = None
    last_error = None
    while attempts < policy.max_attempts:
        attempts += 1
        try:
            return {"ok": True, "result": fn(attempts), "attempts": attempts,
                    "backoff_total": backoff_total, "outcome": "succeeded",
                    "failure_class": None}
        except Exception as exc:  # noqa: BLE001 — the envelope's purpose
            last_error = exc
            cls = classify(exc)
            last_class = cls
            if cls == CLASS_RETRYABLE and attempts < policy.max_attempts:
                delay = policy.backoff_for(attempts)
                backoff_total += delay
                if clock is not None:
                    clock.append(delay)
                continue
            if cls == CLASS_RETRYABLE:
                return {"ok": False, "result": None,
                        "attempts": attempts,
                        "backoff_total": backoff_total,
                        "outcome": "exhausted_retryable",
                        "failure_class": "A", "error": str(exc)}
            if cls == CLASS_QUARANTINE:
                return {"ok": False, "result": None, "attempts": attempts,
                        "backoff_total": backoff_total,
                        "outcome": "quarantined", "failure_class": "D",
                        "error": str(exc)}
            return {"ok": False, "result": None, "attempts": attempts,
                    "backoff_total": backoff_total, "outcome": "terminal",
                    "failure_class": cls, "error": str(exc)}
    # unreachable; kept for clarity
    raise ResilienceError("retry loop escaped")


class BudgetedExecutor:
    """Wraps run_with_retry with caller-owned attempt/failure budgets.
    Refusal happens BEFORE any new attempt (D-063 guardrail semantics)."""

    def __init__(self, max_total_attempts: int, max_total_failures: int):
        if max_total_attempts < 1 or max_total_failures < 0:
            raise ResilienceError("budget bounds invalid")
        self.max_total_attempts = max_total_attempts
        self.max_total_failures = max_total_failures
        self.used_attempts = 0
        self.used_failures = 0

    @property
    def exhausted(self) -> bool:
        return (self.used_attempts >= self.max_total_attempts
                or self.used_failures >= self.max_total_failures)

    def execute(self, policy: RetryPolicy, fn: Callable,
                clock: Optional[List[int]] = None) -> Dict:
        if self.exhausted:
            return {"ok": False, "result": None, "attempts": 0,
                    "backoff_total": 0, "outcome": "budget_refused",
                    "failure_class": "B",
                    "error": "retry/failure budget exhausted"}
        verdict = run_with_retry(policy, fn, clock=clock)
        self.used_attempts += verdict["attempts"]
        if not verdict["ok"]:
            self.used_failures += 1
        return verdict

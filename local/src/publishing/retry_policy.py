"""Publishing failure & retry circuit (Part B).

Deterministic exponential backoff with DLQ transitions for
rate-limited or transiently failed channel dispatches. Pure — no
clock, no network; the caller injects the attempt number and the
error class. Consistent with D-126: retries are deterministic, no
non-deterministic jitter.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

__all__ = [
    "OUTCOME_PUBLISHED", "OUTCOME_DUPLICATE", "OUTCOME_RETRY",
    "OUTCOME_DLQ", "MAX_ATTEMPTS", "BASE_BACKOFF_TICKS", "RetryDecision",
    "RetryPolicy",
]

OUTCOME_PUBLISHED = "published"
OUTCOME_DUPLICATE = "duplicate"          # at-most-once already satisfied
OUTCOME_RETRY = "retry"
OUTCOME_DLQ = "dead_letter"

MAX_ATTEMPTS = 4                # attempt 4 failing => DLQ (3 retries)
BASE_BACKOFF_TICKS = 2          # logical ticks: 2, 4, 8 (deterministic)

# error_class -> retryability (canonical D-052/D-072 taxonomy)
_RETRYABLE_CLASSES = {"C"}      # transient / rate-limit
_NON_RETRYABLE = {"B", "E"}     # terminal contract violations / crashes


@dataclass(frozen=True)
class RetryDecision:
    action: str                      # published | duplicate | retry | dead_letter
    attempt_no: int
    backoff_ticks: int               # 0 unless action == retry
    reason: str


class RetryPolicy:
    """At-most-once per publish key with a bounded deterministic retry
    ladder. `at_most_once` reflects the CANONICAL guarantee: the
    outbox vault blocks any second dispatch of the same key, so a
    `duplicate` verdict is recorded, never re-sent."""

    def __init__(self, max_attempts: int = MAX_ATTEMPTS,
                 base_backoff_ticks: int = BASE_BACKOFF_TICKS):
        if not isinstance(max_attempts, int) or max_attempts < 1 \
                or not isinstance(base_backoff_ticks, int) \
                or base_backoff_ticks < 1:
            raise ValueError("retry_policy_bounds_invalid")
        self.max_attempts = max_attempts
        self.base = base_backoff_ticks

    def decide(self, outcome: str, error_class: str = "",
               attempt_no: int = 1,
               idempotency_hit: bool = False) -> RetryDecision:
        if not isinstance(attempt_no, int) or attempt_no < 1:
            raise ValueError("attempt_no_invalid")
        if outcome == OUTCOME_PUBLISHED:
            return RetryDecision(OUTCOME_PUBLISHED, attempt_no, 0,
                                 f"published_on_attempt_{attempt_no}")
        if idempotency_hit or outcome == "duplicate_publish_blocked":
            return RetryDecision(OUTCOME_DUPLICATE, attempt_no, 0,
                                 "at_most_once_vault_guard")
        if outcome == "queue_frozen":
            return RetryDecision(OUTCOME_DLQ, attempt_no, 0,
                                 "queue_frozen_operator_gate")
        if outcome in ("target_dispatch_crashed", "unknown") \
                or error_class == "E":
            return RetryDecision(OUTCOME_DLQ, attempt_no, 0,
                                 "crash_is_not_transient")
        if error_class in _NON_RETRYABLE:
            return RetryDecision(OUTCOME_DLQ, attempt_no, 0,
                                 f"class_{error_class}_terminal")
        if error_class in _RETRYABLE_CLASSES or outcome in (
                "rate_limited", "transient_failure", "cooldown",
                "media_processing_pending"):
            if attempt_no >= self.max_attempts:
                return RetryDecision(OUTCOME_DLQ, attempt_no, 0,
                                     "retries_exhausted")
            backoff = self.base * (2 ** (attempt_no - 1))
            return RetryDecision(OUTCOME_RETRY, attempt_no, backoff,
                                 f"class_{error_class or 'C'}_transient")
        return RetryDecision(OUTCOME_DLQ, attempt_no, 0,
                             f"unclassifiable_outcome:{outcome or 'empty'}")

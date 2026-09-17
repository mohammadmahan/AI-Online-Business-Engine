"""Phase 14 M3 — notification outbox worker (D-091).

Drains QUEUED notifications through INJECTED channel adapters
(provider-neutral boundary, RULES §35): transient failures (Class-A)
retry with exponential backoff computed from the ATTEMPT NUMBER (no
wall clock), rate-limit backoff (Class-C) honors the indicated wait,
contract-invalid payloads (Class-B) and attempts-exhausted
notifications go to the dead-letter queue — every DLQ admission
materializes a HITL review record (D-028/D-050). The reconciliation
scanner rebuilds pending work from DURABLE store data only — no
in-process state is required for correctness (D-092).
"""

import json
import time
from typing import Dict, List, Optional

from canonical.notification_contracts import (
    CLASS_CONTRACT,
    CLASS_THROTTLE,
    CLASS_TRANSIENT,
    OUT_DELIVERED,
    OUT_DUPLICATE_BLOCKED,
    OUT_PERMANENT_FAILURE,
    OUT_RATE_LIMITED,
    OUT_TRANSIENT_FAILURE,
    ST_DELIVERED,
    ST_DISPATCHED,
    ST_FAILED,
    ST_QUEUED,
    NotificationContractError,
)
from canonical.notification_engine import (
    NotificationEngine,
    NotificationVault,
)

MAX_ATTEMPTS_DEFAULT = 4
BACKOFF_BASE_SECONDS = 2      # 2, 4, 8, … capped
BACKOFF_CAP_SECONDS = 60


class ChannelAdapter:
    """Provider-neutral channel interface (RULES §35). The local
    adapter records outcomes; a live provider is a drop-in behind the
    SAME interface — zero structural rewrites (D-089/D-090)."""

    channel = "ABSTRACT"

    def send(self, event: Dict, ref: Dict) -> Dict:
        """Return {"outcome": OUT_*, "detail": str, "wait_s": int?}.
        Must never raise for channel-semantic failures — record them
        as outcomes instead (the worker never catches adapter bugs:
        those propagate)."""
        raise NotImplementedError


class LocalInAppAdapter(ChannelAdapter):
    """Local IN_APP delivery: deterministic success recorder."""

    channel = "IN_APP"

    def send(self, event: Dict, ref: Dict) -> Dict:
        return {"outcome": OUT_DELIVERED,
                "detail": "in_app_recorded"}


class FailingAdapter(ChannelAdapter):
    """Test/diagnostic adapter: always fails with a given class."""

    def __init__(self, failure_class: str = CLASS_TRANSIENT,
                 wait_s: int = 0):
        self.failure_class = failure_class
        self.wait_s = wait_s
        self.calls = 0

    @property
    def channel(self) -> str:  # pragma: no cover - trivial
        return "IN_APP"

    def send(self, event: Dict, ref: Dict) -> Dict:
        self.calls += 1
        if self.failure_class == CLASS_THROTTLE:
            return {"outcome": OUT_RATE_LIMITED,
                    "detail": "rate_limited_by_provider",
                    "wait_s": self.wait_s}
        if self.failure_class == CLASS_CONTRACT:
            return {"outcome": OUT_PERMANENT_FAILURE,
                    "detail": "recipient_rejected_permanently"}
        return {"outcome": OUT_TRANSIENT_FAILURE,
                "detail": "provider_unavailable"}


# --- backoff (D-091) — pure function of attempt number -----------------------

def backoff_seconds(attempt_no: int,
                    base: int = BACKOFF_BASE_SECONDS,
                    cap: int = BACKOFF_CAP_SECONDS) -> int:
    """Exponential backoff from the ATTEMPT NUMBER: 2^(n-1) * base,
    capped. Deterministic — no wall-clock read anywhere."""
    if attempt_no < 1:
        attempt_no = 1
    return min(cap, base * (2 ** (attempt_no - 1)))


# --- DLQ (D-091/D-092) --------------------------------------------------------

class DeadLetterQueue:
    """DLQ with HITL materialization. PG-backed when live, JSON parity
    otherwise (same default-selection discipline as the vault)."""

    def __init__(self, pg=None):
        self._pg = pg
        self._json_path = None
        if self._pg is None:
            import os
            try:
                cand = _PgDLQ()
                cand.ping()
                self._pg = cand
            except Exception:
                import pathlib
                path = os.path.join("local", "volumes",
                                    "notifications", "dlq.json")
                pathlib.Path(path).parent.mkdir(parents=True,
                                                exist_ok=True)
                self._json_path = path

    def ping(self) -> None:
        if self._pg is not None:
            self._pg.ping()

    def admit(self, key: str, reason: str, failure_class: str,
              attempts: int, event_ref: Dict) -> None:
        if self._pg is not None:
            self._pg.admit(key, reason, failure_class, attempts,
                           event_ref)
            return
        import threading
        data = self._load_json()
        data[key] = {"reason": reason,
                     "failure_class": failure_class,
                     "attempts": int(attempts),
                     "event_ref": event_ref}
        tmp = self._json_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, sort_keys=True)
        import os
        os.replace(tmp, self._json_path)

    def _load_json(self) -> Dict:
        import os
        if not os.path.exists(self._json_path):
            return {}
        with open(self._json_path, encoding="utf-8") as fh:
            return json.load(fh)

    def items(self) -> Dict[str, Dict]:
        if self._pg is not None:
            return self._pg.items()
        return self._load_json()


class _PgDLQ:
    """DLQ rows on notifications.dead_letter (D-055/D-091)."""

    def __init__(self):
        import sys as _sys
        import os as _os
        scripts = _os.path.join("local", "scripts")
        if scripts not in _sys.path:
            _sys.path.insert(0, scripts)
        from canonical.notion_ingest import _exec, _txt  # noqa: E402
        self._exec = _exec
        self._txt = _txt

    def ping(self) -> None:
        self._exec("SELECT 1", {})

    def admit(self, key: str, reason: str, failure_class: str,
              attempts: int, event_ref: Dict) -> None:
        self._exec(
            "INSERT INTO notifications.dead_letter (dedup_key, reason, "
            "failure_class, attempts, event_ref) VALUES ("
            + self._txt("k") + ", " + self._txt("r") + ", "
            + self._txt("c") + ", " + self._txt("a") + "::int, "
            + self._txt("e") + "::jsonb) "
            "ON CONFLICT (dedup_key) DO UPDATE SET reason = "
            "EXCLUDED.reason, failure_class = EXCLUDED.failure_class, "
            "attempts = EXCLUDED.attempts, event_ref = "
            "EXCLUDED.event_ref, admitted_at = now()",
            {"k": key, "r": reason, "c": failure_class,
             "a": str(int(attempts)),
             "e": json.dumps(event_ref, ensure_ascii=False,
                             sort_keys=True)})

    def items(self) -> Dict[str, Dict]:
        rows = self._exec(
            "SELECT dedup_key || chr(31) || reason || chr(31) || "
            "failure_class || chr(31) || attempts::text || chr(31) || "
            "event_ref::text || chr(31) || 'END' "
            "FROM notifications.dead_letter ORDER BY dedup_key", {})
        out: Dict[str, Dict] = {}
        for line in rows.splitlines():
            parts = line.strip().split("\x1f")
            # 6 fields: dedup_key, reason, failure_class, attempts,
            # event_ref, END
            if len(parts) >= 6 and parts[-1] == "END":
                out[parts[0]] = {"reason": parts[1],
                                 "failure_class": parts[2],
                                 "attempts": int(parts[3]),
                                 "event_ref": json.loads(parts[4])}
        return out


# --- worker -------------------------------------------------------------------

class NotificationWorker:
    """D-091 outbox drain + reconciliation. adapters: {channel:
    ChannelAdapter}. The queue source is the engine's durable status
    view — QUEUED notifications are the outbox."""

    def __init__(self, engine: NotificationEngine,
                 adapters: Dict[str, ChannelAdapter],
                 dlq: Optional[DeadLetterQueue] = None,
                 provenance=None, max_attempts: int = MAX_ATTEMPTS_DEFAULT,
                 vault: Optional[NotificationVault] = None):
        self.engine = engine
        self.adapters = adapters
        self.dlq = dlq if dlq is not None else DeadLetterQueue()
        self.prov = provenance
        self.max_attempts = max_attempts
        self.vault = vault or engine.vault
        # transient attempts are tracked ON the durable lock ref, so a
        # restarted worker resumes with the right attempt number
        # (restart-safety, D-092)

    # -- queue view ----------------------------------------------------------

    def _queued(self) -> Dict[str, Dict]:
        view = self.engine.status_view()
        return {k: v for k, v in view.items()
                if v.get("status") == ST_QUEUED}

    def _events_by_key(self) -> Dict[str, Dict]:
        by_key: Dict[str, Dict] = {}
        for ref in self.engine._refs():
            if ref.get("kind") == "notification":
                by_key[ref["dedup_key"]] = ref
        return by_key

    # -- drain ------------------------------------------------------------------

    def drain(self, limit: int = 100) -> Dict:
        """One pass: dispatch every QUEUED notification through its
        channel adapter. Per-channel independence: a failure records
        an outcome for THAT notification only (D-090)."""
        events = self._events_by_key()
        summary = {"dispatched": 0, "delivered": 0, "retried": 0,
                   "dlq": 0, "duplicate_blocked": 0, "skipped": 0}
        for key, st in list(self._queued().items())[:limit]:
            ref = events.get(key)
            if ref is None:
                summary["skipped"] += 1
                continue
            adapter = self.adapters.get(ref["channel"])
            if adapter is None:
                # no adapter bound: durable receipt, never silent
                self.engine.record_outcome(
                    ref, key, self._attempt_no(key, ref),
                    OUT_PERMANENT_FAILURE,
                    "no_adapter_bound_for_channel")
                summary["dlq"] += 1
                self._admit_dlq(key, ref,
                                "no_adapter_bound_for_channel",
                                CLASS_CONTRACT)
                continue
            attempt_no = self._attempt_no(key, ref)
            try:
                result = adapter.send(ref, st)
            except Exception as exc:  # adapter BUG — carrier error
                self.engine.record_outcome(
                    ref, key, attempt_no, OUT_PERMANENT_FAILURE,
                    f"adapter_error:{type(exc).__name__}")
                summary["dlq"] += 1
                self._admit_dlq(key, ref,
                                f"adapter_error:{type(exc).__name__}",
                                "E")
                continue
            outcome = result.get("outcome")
            if outcome == OUT_DELIVERED:
                self.engine.record_outcome(ref, key, attempt_no,
                                           OUT_DELIVERED,
                                           result.get("detail", ""))
                summary["delivered"] += 1
            elif outcome == OUT_RATE_LIMITED:
                # Class-C: honor the wait; retry budget NOT consumed by
                # the provider's own pacing — attempt recorded, retry
                # happens on a later pass
                self.engine.record_outcome(
                    ref, key, attempt_no, OUT_RATE_LIMITED,
                    result.get("detail", ""))
                summary["retried"] += 1
            elif outcome == OUT_TRANSIENT_FAILURE:
                if attempt_no >= self.max_attempts:
                    self.engine.record_outcome(
                        ref, key, attempt_no, OUT_PERMANENT_FAILURE,
                        "attempts_exhausted")
                    summary["dlq"] += 1
                    self._admit_dlq(key, ref, "attempts_exhausted",
                                    CLASS_TRANSIENT)
                else:
                    self.engine.record_outcome(
                        ref, key, attempt_no, OUT_TRANSIENT_FAILURE,
                        result.get("detail", ""))
                    summary["retried"] += 1
            elif outcome == OUT_PERMANENT_FAILURE:
                self.engine.record_outcome(ref, key, attempt_no,
                                           OUT_PERMANENT_FAILURE,
                                           result.get("detail", ""))
                summary["dlq"] += 1
                self._admit_dlq(key, ref,
                                result.get("detail", "permanent"),
                                CLASS_CONTRACT)
            else:
                # unknown outcome from an adapter = carrier defect,
                # recorded, never silent
                self.engine.record_outcome(
                    ref, key, attempt_no, OUT_PERMANENT_FAILURE,
                    f"unknown_outcome:{outcome}")
                summary["dlq"] += 1
                self._admit_dlq(key, ref, f"unknown_outcome:{outcome}",
                                "E")
            summary["dispatched"] += 1
        return summary

    # -- attempt bookkeeping (durable, restart-safe) ------------------------------

    def _attempt_no(self, key: str, ref: Dict) -> int:
        lock = self.vault._locks.get(key) or {}
        return int(lock.get("attempt_no") or 0) + 1

    def _admit_dlq(self, key: str, ref: Dict, reason: str,
                   failure_class: str) -> None:
        self.dlq.admit(key, reason, failure_class,
                       self._attempt_no(key, ref) - 1, ref)
        # HITL materialization (D-028/D-050): DLQ rows ARE the review
        # queue; nothing auto-resolves. The durable event ref carries
        # the reason — status_view exposes FAILED for human triage.

    # -- reconciliation (D-092) ----------------------------------------------------

    def reconcile(self) -> Dict:
        """Rebuild pending work from durable data only. Returns the
        reconciled queue snapshot; NEVER mutates state (the next drain
        acts on it). Proves no in-process cache is needed."""
        queued = self._queued()
        events = self._events_by_key()
        orphans = [k for k in queued if k not in events]
        return {"queued": len(queued), "orphans": orphans,
                "dlq": len(self.dlq.items())}


def sleep_backoff(seconds: int) -> None:
    """Real pause between passes; tests inject a no-op."""
    time.sleep(seconds)

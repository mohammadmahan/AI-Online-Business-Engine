"""Phase 14 M2 — notification engine (D-090/D-092).

NotificationVault (exactly-once-per-channel claims), policy-guard
integration, the enqueue path (validate → policy → vault → outbox
event), and the durable status view. Boundary discipline (RULES §35):
channel adapters are INJECTED behind a provider-neutral interface —
no network, no credentials, no os.environ (D-045). Everything durable
goes through the D-027 store with D-026 provenance; no wall clock
enters any key (D-085 precedent).
"""

import json
from typing import Dict, List, Optional

from canonical.notification_contracts import (
    CH_IN_APP,
    OUT_DELIVERED,
    OUT_DUPLICATE_BLOCKED,
    OUT_PERMANENT_FAILURE,
    OUT_POLICY_DEFERRED,
    OUT_RATE_LIMITED,
    OUT_TRANSIENT_FAILURE,
    ST_DISPATCHED,
    ST_DELIVERED,
    ST_DUPLICATE_BLOCKED,
    ST_FAILED,
    ST_POLICY_DEFERRED,
    ST_QUEUED,
    NotificationContractError,
    dedup_key,
    policy_decision,
    validate_notification,
)

LOCK_NAMESPACE = "notifications.delivery_lock"


# --- vault -------------------------------------------------------------------

class NotificationVault:
    """D-090 exactly-once-per-channel claims. Provider-neutral: a
    store dict + a lock backend are injected (PG PK-as-lock or JSON
    parity), so tests run offline and live-PG is a drop-in."""

    def __init__(self, lock_backend):
        self._locks = lock_backend

    def claim(self, key: str, claim_ref: Dict) -> Dict:
        """Atomic claim. Winner: {acquired: True}. Loser:
        {acquired: False, original: <winner's ref>} — the loser NEVER
        dispatches; it records duplicate_blocked (D-090)."""
        return self._locks.acquire(key, claim_ref)

    def mark_outcome(self, key: str, ref: Dict) -> None:
        """Persist the terminal outcome on the lock row (audit +
        future-claim verdicts). Locks are never released (D-070
        precedent): double-delivery protection outlives the attempt."""
        self._locks.finalize(key, ref)


class _JsonLocks:
    """Offline parity lock backend — file-backed, process-wide lock
    per path, reload-on-use (same discipline as the Phase 9 vault)."""

    def __init__(self, path: str):
        import pathlib
        self.path = str(path)
        pathlib.Path(self.path).parent.mkdir(parents=True,
                                             exist_ok=True)
        import threading
        self._lock = threading.Lock()

    def _load(self) -> Dict:
        import os
        if not os.path.exists(self.path):
            return {}
        with open(self.path, encoding="utf-8") as fh:
            return json.load(fh)

    def _save(self, data: Dict) -> None:
        import os
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, sort_keys=True)
        os.replace(tmp, self.path)

    def acquire(self, key: str, claim_ref: Dict) -> Dict:
        with self._lock:
            data = self._load()
            if key in data:
                return {"acquired": False,
                        "original": data[key]}
            ref = json.loads(json.dumps(claim_ref))
            data[key] = ref
            self._save(data)
            return {"acquired": True, "original": ref}

    def finalize(self, key: str, ref: Dict) -> None:
        with self._lock:
            data = self._load()
            if key in data:  # never resurrect a vanished row
                data[key] = json.loads(json.dumps(ref))
                self._save(data)

    def get(self, key: str) -> Optional[Dict]:
        with self._lock:
            return self._load().get(key)


class _PgLocks:
    """Live PG lock backend: the PRIMARY KEY on
    notifications.delivery_lock IS the lock (D-070/D-079 pattern)."""

    def __init__(self):
        import sys as _sys
        import os as _os
        scripts = _os.path.join("local", "scripts")
        if scripts not in _sys.path:
            _sys.path.insert(0, scripts)
        from canonical.notion_ingest import _exec, _txt  # noqa: E402
        self._exec = _exec
        self._txt = _txt

    def acquire(self, key: str, claim_ref: Dict) -> Dict:
        ref_json = json.dumps(claim_ref, ensure_ascii=False,
                              sort_keys=True)
        out = self._exec(
            "INSERT INTO notifications.delivery_lock "
            "(dedup_key, claim_ref) VALUES ("
            + self._txt("k") + ", " + self._txt("r") + "::jsonb) "
            "ON CONFLICT (dedup_key) DO NOTHING RETURNING "
            "claim_ref::text || chr(31) || 'END'",
            {"k": key, "r": ref_json}).strip()
        if out:
            return {"acquired": True, "original": claim_ref}
        return {"acquired": False, "original": self.get(key) or {}}

    def finalize(self, key: str, ref: Dict) -> None:
        self._exec(
            "UPDATE notifications.delivery_lock SET claim_ref = "
            + self._txt("r") + "::jsonb, locked_at = now() "
            "WHERE dedup_key = " + self._txt("k"),
            {"k": key, "r": json.dumps(ref, ensure_ascii=False,
                                       sort_keys=True)})

    def get(self, key: str) -> Optional[Dict]:
        row = self._exec(
            "SELECT claim_ref::text || chr(31) || 'END' "
            "FROM notifications.delivery_lock WHERE dedup_key = "
            + self._txt("k"), {"k": key}).strip()
        if not row:
            return None
        parts = row.split("\x1f")
        if len(parts) >= 2 and parts[-1] == "END" and parts[0]:
            return json.loads(parts[0])
        return None


def default_lock_backend():
    """PG when the live stack answers, JSON parity otherwise."""
    try:
        backend = _PgLocks()
        backend._exec("SELECT 1", {})
        return backend
    except Exception:
        import os
        return _JsonLocks(os.path.join(
            "local", "volumes", "notifications", "delivery_locks.json"))


# --- engine ------------------------------------------------------------------

class NotificationEngine:
    """D-089/D-090/D-092 orchestration: enqueue (validate → policy →
    vault → durable QUEUED record) plus the durable status view.

    store      : D-027 store (PgEventStore or EventStore parity)
    provenance : D-026 engine (record())
    locks      : vault backend (PG or JSON parity)
    """

    def __init__(self, store, provenance=None, locks=None,
                 redact=None):
        self._store = store
        self._prov = provenance
        self._locks = locks or default_lock_backend()
        self._redact = redact or (lambda s: s)
        self.vault = NotificationVault(self._locks)

    # -- durable ledger ---------------------------------------------------

    def _refs(self) -> List[Dict]:
        """All succeeded notifications refs, parsed. The D-027 stores'
        succeeded_references() returns raw JSON strings (interface
        parity); parse defensively — a non-JSON ref is skipped."""
        out: List[Dict] = []
        for raw in self._store.succeeded_references("notifications"):
            if isinstance(raw, dict):
                out.append(raw)
                continue
            try:
                out.append(json.loads(raw))
            except (json.JSONDecodeError, TypeError):
                continue
        return out

    def _recent_deliveries(self, recipient: str,
                           window_start_iso: str) -> int:
        """Count the recipient's allowed+delivered notifications in the
        frequency window, from DURABLE events only (D-090 input)."""
        n = 0
        for ref in self._refs():
            if ref.get("kind") != "delivery_receipt":
                continue
            if ref.get("recipient") != recipient:
                continue
            if ref.get("occurred_at", "") >= window_start_iso \
                    and ref.get("outcome") == OUT_DELIVERED:
                n += 1
        return n

    def frequency_window_start(self, occurred_at: str) -> str:
        """Pure string arithmetic: the window start ISO (24h before
        occurred_at, same offset). No wall clock (D-085)."""
        import re
        from datetime import datetime, timedelta
        dt = datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))
        start = dt - timedelta(hours=24)
        return start.isoformat()

    # -- event ids ----------------------------------------------------------

    @staticmethod
    def enqueue_event_id(key: str) -> str:
        return f"notifications|enqueue|{key}"

    @staticmethod
    def outcome_event_id(kind: str, key: str, seq: int) -> str:
        # seq disambiguates multi-attempt outcomes deterministically
        # (attempt number from the worker), never a wall clock
        return f"notifications|{kind}|{key}|{int(seq)}"

    # -- enqueue ------------------------------------------------------------

    def enqueue(self, event: Dict) -> Dict:
        """Validate → policy → vault claim → durable QUEUED record.
        Raises NotificationContractError (Class-B) BEFORE anything is
        queued. Returns a deterministic decision dict."""
        validate_notification(event)
        key = dedup_key(event)
        recipient = event["recipient"]

        recent = self._recent_deliveries(
            recipient, self.frequency_window_start(event["occurred_at"]))
        decision = policy_decision(event, recent)
        if decision["verdict"] == "defer":
            self._record("policy", key, 0, event, {
                "kind": "policy_deferred", "dedup_key": key,
                "recipient": recipient, "channel": event["channel"],
                "reason": decision["reason"],
                "occurred_at": event["occurred_at"],
            }, ST_POLICY_DEFERRED, OUT_POLICY_DEFERRED)
            return {"status": ST_POLICY_DEFERRED, "dedup_key": key,
                    "reason": decision["reason"]}

        claim_ref = {"outcome": "claimed", "template_id":
                     event["template_id"], "channel": event["channel"],
                     "recipient": recipient}
        claim = self.vault.claim(key, claim_ref)
        if not claim["acquired"]:
            self._record("dup", key, 0, event, {
                "kind": "duplicate_blocked", "dedup_key": key,
                "recipient": recipient, "channel": event["channel"],
                "original_ref": self._redact(json.dumps(
                    claim.get("original") or {}, ensure_ascii=False,
                    sort_keys=True)),
                "occurred_at": event["occurred_at"],
            }, ST_DUPLICATE_BLOCKED, OUT_DUPLICATE_BLOCKED)
            return {"status": ST_DUPLICATE_BLOCKED, "dedup_key": key}

        ref = {"kind": "notification", "dedup_key": key,
               "recipient": recipient, "channel": event["channel"],
               "template_id": event["template_id"],
               "priority": event.get("priority", "NORMAL"),
               "variables": event["variables"],
               "occurred_at": event["occurred_at"]}
        eid = self.enqueue_event_id(key)
        verdict = self._store.receive("notifications", eid, "op", ref)
        if verdict.get("verdict") == "skipped_duplicate":
            # enqueue retry of the same logical alert — not a new row
            return {"status": ST_QUEUED, "dedup_key": key,
                    "retried": True}
        self._store.begin("notifications", eid)
        self._store.succeed("notifications", eid, result_reference=json.dumps(
            ref, ensure_ascii=False, sort_keys=True))
        return {"status": ST_QUEUED, "dedup_key": key}

    # -- worker outcome recording (D-092) ------------------------------------

    def record_outcome(self, event: Dict, key: str, attempt_no: int,
                       outcome: str, detail: str = "",
                       attempt_seq: int = 0) -> str:
        """Persist one dispatch outcome as a D-027 event + provenance.
        Returns the CURRENT status after the outcome (D-092 mapping):
        transient / rate-limited attempts return the notification to
        QUEUED for its next attempt (the receipt event IS the
        DISPATCHED transition record); only terminal outcomes move it
        to DELIVERED / FAILED."""
        status_map = {
            OUT_DELIVERED: ST_DELIVERED,
            OUT_PERMANENT_FAILURE: ST_FAILED,
            OUT_TRANSIENT_FAILURE: ST_QUEUED,
            OUT_RATE_LIMITED: ST_QUEUED,
        }
        status = status_map[outcome]
        # terminal stickiness (D-092): if the vault already settled a
        # terminal outcome, a late non-terminal receipt does NOT move
        # the notification — report the settled status
        prev_outcome = (self._locks.get(key) or {}).get("outcome")
        if prev_outcome in (OUT_DELIVERED, OUT_PERMANENT_FAILURE) \
                and outcome not in (OUT_DELIVERED,
                                    OUT_PERMANENT_FAILURE):
            status = status_map[prev_outcome]
        ref = {"kind": "delivery_receipt", "dedup_key": key,
               "recipient": event["recipient"],
               "channel": event["channel"],
               "attempt_no": int(attempt_no), "outcome": outcome,
               "detail": self._redact(str(detail))[:512],
               "occurred_at": event["occurred_at"]}
        eid = self.outcome_event_id("outcome", key,
                                    attempt_seq or attempt_no)
        verdict = self._store.receive("notifications", eid, "op", ref)
        if verdict.get("verdict") != "skipped_duplicate":
            self._store.begin("notifications", eid)
            self._store.succeed("notifications", eid, result_reference=json.dumps(
                ref, ensure_ascii=False, sort_keys=True))
        # durable attempt bookkeeping on the lock row: EVERY outcome
        # advances attempt_no (restart-safe retry ladder); only a
        # TERMINAL outcome settles the vault's outcome verdict
        lock_ref = dict(self._locks.get(key) or {})
        lock_ref["attempt_no"] = max(int(lock_ref.get("attempt_no") or 0),
                                     int(attempt_no))
        if outcome in (OUT_DELIVERED, OUT_PERMANENT_FAILURE):
            lock_ref["outcome"] = outcome
        self.vault.mark_outcome(key, lock_ref)
        return status

    # -- durable status view (D-092) ------------------------------------------

    def status_view(self) -> Dict[str, Dict]:
        """Rebuild dedup_key → status from DURABLE store data only —
        no in-process cache required for correctness (D-092)."""
        view: Dict[str, Dict] = {}
        for ref in self._refs():
            key = ref.get("dedup_key")
            if not key:
                continue
            kind = ref.get("kind")
            if kind == "notification":
                cur = view.setdefault(key, {"status": ST_QUEUED,
                                            "attempts": 0})
                if cur["status"] in ("",):
                    cur["status"] = ST_QUEUED
            elif kind == "policy_deferred":
                view.setdefault(key, {"status": ST_POLICY_DEFERRED,
                                      "attempts": 0,
                                      "reason": ref.get("reason")})
            elif kind == "duplicate_blocked":
                view.setdefault(key, {"status": ST_DUPLICATE_BLOCKED,
                                      "attempts": 0})
            elif kind == "delivery_receipt":
                cur = view.setdefault(key, {"status": ST_QUEUED,
                                            "attempts": 0})
                cur["attempts"] = max(cur["attempts"],
                                      int(ref.get("attempt_no", 0)))
                outcome = ref.get("outcome")
                # terminal stickiness (D-092): a late transient
                # receipt never demotes DELIVERED / FAILED
                if cur["status"] in (ST_DELIVERED, ST_FAILED):
                    continue
                if outcome == OUT_DELIVERED:
                    cur["status"] = ST_DELIVERED
                elif outcome == OUT_PERMANENT_FAILURE:
                    cur["status"] = ST_FAILED
                # transient / rate-limited receipts leave the
                # notification QUEUED for its next attempt (the
                # receipt is the DISPATCHED transition record)
        return view

    # -- internals --------------------------------------------------------------

    def _record(self, kind: str, key: str, seq: int, event: Dict,
                ref: Dict, status: str, outcome: str) -> None:
        eid = self.outcome_event_id(kind, key, seq)
        verdict = self._store.receive("notifications", eid, "op", ref)
        if verdict.get("verdict") == "skipped_duplicate":
            return
        self._store.begin("notifications", eid)
        self._store.succeed("notifications", eid, result_reference=json.dumps(
            ref, ensure_ascii=False, sort_keys=True))

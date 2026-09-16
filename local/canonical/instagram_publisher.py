"""Phase 9 M3 — idempotency vault, outbox publisher, error
classifier, DLQ (D-070 / D-072).

**Idempotency vault (D-070):** an EXCLUSIVE publishing lock per
`publish_idempotency_key`, enforced in the canonical store BEFORE any
network call. PostgreSQL: the PRIMARY KEY on `instagram.publish_lock`
IS the lock — a conditional INSERT … ON CONFLICT … WHERE decides
atomically between three outcomes:

  - no row / lower attempt_no and NOT published → acquired (a bounded
    D-072 retry of a failed attempt is legitimate; the new attempt_no
    comes from DURABLE attempt events, so it survives restarts);
  - row exists with outcome='published' → blocked FOREVER (absolute
    double-publish protection);
  - row exists in-flight with attempt_no ≥ ours → blocked (concurrent
    dispatcher / network retry of the SAME attempt).

JSON parity vault for offline tests (per-path lock + reload so
multiple instances sharing one file stay correct in-process).

**Outbox (D-072):** queued posts are durable D-027 events
(`instagram|publish|<key>`) BEFORE dispatch; every attempt records a
durable attempt event (`instagram|attempt|…`) and every state change a
transition event, so state is reconstructable from the store alone.

**Classifier (D-072, D-052-aligned):** Class-A transient → exponential
backoff (bounded); Class-B invalid → terminal reject, NO retry;
Class-C rate limit → cooldown gate; Class-E token expired → FREEZE the
queue + alert. Unrecoverable failures → DLQ with audit record +
D-026 provenance — nothing vanishes silently.
"""

import json
import os
import threading
import time
from typing import Callable, Dict, List, Optional

from canonical.instagram_contracts import (
    CONTAINER_STATUS, FAILED, InstagramContractError,
    MEDIA_CREATE, MEDIA_PUBLISH, PENDING, PUBLISHED,
    key_from_payload, publish_idempotency_key, validate_publish_payload)
from canonical.instagram_adapter import (
    ContainerNotReady, InstagramAdapter, MockInstagramAdapter, redact)
from canonical.instagram_adapter import _RateLimited  # noqa: E402

SOURCE_SYSTEM = "instagram"
OP_QUEUE = "queue_publish"
OP_LOCK = "publish_lock"
OP_PUBLISH = "publish_attempt"

_PATH_LOCKS: Dict[str, threading.Lock] = {}
_PATH_LOCKS_GUARD = threading.Lock()


def _path_lock(path: str) -> threading.Lock:
    with _PATH_LOCKS_GUARD:
        if path not in _PATH_LOCKS:
            _PATH_LOCKS[path] = threading.Lock()
        return _PATH_LOCKS[path]


class _TokenExpired(Exception):
    """Class-E carrier: token expired → freeze + alert."""

    failure_class = "E"


# --- vault ------------------------------------------------------------------

class _PgVault:
    """D-070 vault on the live PostgreSQL store (D-055): the PRIMARY
    KEY on instagram.publish_lock IS the lock. Uses the repo's psql
    transport (base64 params, no interpolated SQL)."""

    def __init__(self):
        import sys as _sys
        scripts = os.path.join("local", "scripts")
        if scripts not in _sys.path:
            _sys.path.insert(0, scripts)
        from canonical.notion_ingest import _exec, _txt  # noqa: E402
        self._exec = _exec
        self._txt = _txt

    def _read(self, key: str) -> Optional[Dict]:
        row = self._exec(
            "SELECT attempt_ref::text || chr(31) || 'END' "
            "FROM instagram.publish_lock WHERE publish_key = "
            + self._txt("k"), {"k": key}).strip()
        if not row:
            return None
        parts = row.split("\x1f")
        if len(parts) >= 2 and parts[-1] == "END" and parts[0]:
            return json.loads(parts[0])
        return None

    def acquire(self, key: str, attempt_ref: Dict) -> Dict:
        """Atomic conditional claim. Returns
        {"acquired": bool, "original": ref, "published": bool}."""
        ref_json = json.dumps(attempt_ref, ensure_ascii=False,
                              sort_keys=True)
        out = self._exec(
            "INSERT INTO instagram.publish_lock (publish_key, attempt_ref) "
            "VALUES (" + self._txt("k") + ", " + self._txt("r")
            + "::jsonb) "
            "ON CONFLICT (publish_key) DO UPDATE "
            "SET attempt_ref = EXCLUDED.attempt_ref, locked_at = now() "
            "WHERE (instagram.publish_lock.attempt_ref->>'outcome') "
            "IS DISTINCT FROM 'published' "
            "AND COALESCE((instagram.publish_lock.attempt_ref"
            "->>'attempt_no')::int, 0) "
            "< COALESCE(EXCLUDED.attempt_ref->>'attempt_no','0')::int "
            "RETURNING attempt_ref::text || chr(31) || 'END'",
            {"k": key, "r": ref_json}).strip()
        if out:
            return {"acquired": True, "original": attempt_ref,
                    "published": False}
        original = self._read(key) or {}
        return {"acquired": False, "original": original,
                "published": original.get("outcome") == "published"}

    def finalize(self, key: str, ref: Dict) -> None:
        """Mark the attempt PUBLISHED — permanent (D-070)."""
        self._exec(
            "UPDATE instagram.publish_lock SET attempt_ref = "
            + self._txt("r") + "::jsonb, locked_at = now() "
            "WHERE publish_key = " + self._txt("k"),
            {"k": key, "r": json.dumps(ref, ensure_ascii=False,
                                       sort_keys=True)})

    def release(self, key: str) -> None:
        # locks are NEVER released on success — double-publish
        # protection must outlive the attempt (D-070)
        return None


class _JsonVault:
    """Offline parity vault (local tests): same verdict semantics,
    file-backed. Uses a per-path module-level lock + reload so several
    instances sharing one file stay consistent in-process."""

    def __init__(self, path: str):
        self.path = path
        self.data: Dict[str, Dict] = {}
        self._reload()

    def _reload(self):
        if self.path and os.path.exists(self.path):
            with open(self.path, encoding="utf-8") as f:
                self.data = json.load(f)

    def _persist(self):
        if not self.path:
            return
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        # per-instance unique tmp: two instances may share one file —
        # a shared ".tmp" name would race across instances
        tmp = f"{self.path}.{os.getpid()}.{id(self)}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.path)

    def acquire(self, key: str, attempt_ref: Dict) -> Dict:
        with _path_lock(self.path):
            self._reload()
            existing = self.data.get(key)
            if existing is not None:
                if existing.get("outcome") == "published":
                    return {"acquired": False, "original": existing,
                            "published": True}
                if existing.get("attempt_no", 0) \
                        >= attempt_ref.get("attempt_no", 0):
                    return {"acquired": False, "original": existing,
                            "published": False}
            self.data[key] = attempt_ref
            self._persist()
            return {"acquired": True, "original": attempt_ref,
                    "published": False}

    def finalize(self, key: str, ref: Dict) -> None:
        with _path_lock(self.path):
            self._reload()
            self.data[key] = ref
            self._persist()

    def release(self, key: str) -> None:
        return None


# --- publisher -----------------------------------------------------------------

class InstagramOutboxPublisher:
    """Queues posts (D-027 durable), claims and publishes them through
    the D-069 workflow under the D-070 vault, classifying failures
    (D-072) and dead-lettering the unrecoverable."""

    def __init__(self, store, vault,
                 provenance=None, queue=None,
                 max_retries: int = 3, cooldown_s: float = 60.0):
        self.store = store
        self.vault = vault
        self.provenance = provenance
        self.queue = queue
        self.max_retries = max_retries
        self.cooldown_s = cooldown_s
        self.frozen = False
        self._cooldown_until: Dict[str, float] = {}
        self.dlq: List[Dict] = []

    # -- outbox ------------------------------------------------------------

    def enqueue(self, payload: Dict, *, actor: str = "instagram-ops"
                ) -> Dict:
        """Queue a post: local validation FIRST (Class-B prevention),
        then a durable outbox event. Returns the queued item."""
        norm = validate_publish_payload(payload)  # raises Class-B locally
        key = publish_idempotency_key(
            norm["content_id"], norm["media_hash"], norm["caption_hash"],
            norm["scheduled_slot"])
        eid = f"instagram|publish|{key}"
        ref = dict(norm, publish_key=key, state=PENDING, event_id=eid)
        rec = self.store.receive(SOURCE_SYSTEM, eid, OP_QUEUE, ref)
        if rec["verdict"] == "integrity_error":
            from services.sync_engine import IntegrityError
            raise IntegrityError(
                f"conflicting outbox duplicate for {key} — human review")
        # durable queued row: receive → succeed with the payload as ref
        # (the outbox entry must SURVIVE a crash before any dispatch)
        if rec["verdict"] in ("new", "retry"):
            self.store.begin(SOURCE_SYSTEM, eid)
            self.store.succeed(SOURCE_SYSTEM, eid,
                               result_reference=json.dumps(
                                   ref, ensure_ascii=False,
                                   sort_keys=True))
        return {"queued": rec["verdict"] in ("new", "retry"),
                "publish_key": key, "payload": ref}

    def _store_refs(self) -> List[Dict]:
        refs = []
        for line in self.store.succeeded_references(SOURCE_SYSTEM):
            try:
                ref = json.loads(line)
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(ref, dict):
                refs.append(ref)
        return refs

    def pending(self) -> List[Dict]:
        """Queued items not yet terminal (durable data only)."""
        done = set()
        items: Dict[str, Dict] = {}
        for ref in self._store_refs():
            eid = str(ref.get("event_id", ""))
            key = ref.get("publish_key")
            if eid.startswith("instagram|transition|") \
                    and ref.get("state") in (PUBLISHED, FAILED):
                done.add(key)
            elif eid.startswith("instagram|publish|") \
                    and ref.get("state") in (PENDING, MEDIA_CREATE,
                                             CONTAINER_STATUS,
                                             MEDIA_PUBLISH):
                items[key] = ref
        out = [ref for key, ref in items.items() if key not in done]
        out.sort(key=lambda r: r.get("scheduled_slot", ""))
        return out

    # -- durable attempt bookkeeping ---------------------------------------

    def _count_attempts(self, key: str) -> int:
        return sum(1 for ref in self._store_refs()
                   if str(ref.get("event_id", ""))
                   .startswith("instagram|attempt|")
                   and ref.get("publish_key") == key)

    def _record_transition(self, key: str, from_state: str, to_state: str,
                           extra: Optional[Dict] = None) -> Dict:
        eid = f"instagram|transition|{key}|{to_state}|{time.time_ns()}"
        ref = {"event_id": eid, "publish_key": key,
               "from_state": from_state, "state": to_state}
        if extra:
            ref.update(extra)
        self.store.receive(SOURCE_SYSTEM, eid, OP_PUBLISH, ref)
        self.store.succeed(SOURCE_SYSTEM, eid, result_reference=json.dumps(
            ref, ensure_ascii=False, sort_keys=True))
        return ref

    def _record_attempt(self, key: str, attempt_no: int, outcome: str,
                        extra: Optional[Dict] = None) -> Dict:
        eid = f"instagram|attempt|{key}|{attempt_no}"
        ref = {"event_id": eid, "publish_key": key,
               "attempt_no": attempt_no, "outcome": outcome}
        if extra:
            ref.update(extra)
        rec = self.store.receive(SOURCE_SYSTEM, eid, OP_PUBLISH, ref)
        if rec["verdict"] == "skipped_duplicate":
            return ref
        self.store.succeed(SOURCE_SYSTEM, eid, result_reference=json.dumps(
            ref, ensure_ascii=False, sort_keys=True))
        return ref

    def _provenance(self, actor: str, ref: Dict, outcome: str) -> None:
        if self.provenance is None:
            return
        try:
            pr = self.provenance.record(
                "SYSTEM_GENERATED", actor,
                source_reference=f"instagram-publish:"
                                 f"{str(ref.get('publish_key'))[:24]}",
                original_value=json.dumps(ref, ensure_ascii=False,
                                          sort_keys=True)[:2000],
                notes=f"instagram publish outcome={outcome}")
            self.provenance.link_value(SOURCE_SYSTEM,
                                       str(ref.get("publish_key", ""))[:64],
                                       "attempt", pr)
        except Exception:
            pass  # audit best-effort; publish state stays durable

    def _dead_letter(self, ref: Dict, error_class: str, error: str,
                     history: List[Dict]) -> Dict:
        entry = {"publish_key": ref.get("publish_key"),
                 "content_id": ref.get("content_id"),
                 "error_class": error_class,
                 "error": redact(str(error)),
                 "attempts": history,
                 "dead_lettered_at": time.strftime(
                     "%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        self.dlq.append(entry)
        if self.provenance is not None:
            try:
                pr = self.provenance.record(
                    "SYSTEM_GENERATED", "instagram-dlq",
                    source_reference=f"instagram-dlq:"
                                     f"{str(ref.get('publish_key'))[:24]}",
                    original_value=json.dumps(entry, ensure_ascii=False,
                                              sort_keys=True)[:2000],
                    notes=f"DLQ: class {error_class}")
                self.provenance.link_value(
                    SOURCE_SYSTEM, str(ref.get("publish_key", ""))[:64],
                    "dlq", pr)
            except Exception:
                pass
        return entry

    def _freeze(self, ref: Dict, error: str) -> Dict:
        self.frozen = True
        entry = {"frozen_at": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                            time.gmtime()),
                 "reason": redact(str(error)),
                 "publish_key": ref.get("publish_key")}
        if self.provenance is not None:
            try:
                self.provenance.record(
                    "SYSTEM_GENERATED", "instagram-ops",
                    source_reference="instagram-freeze",
                    original_value=json.dumps(entry,
                                              ensure_ascii=False),
                    notes="Class-E token expired — queue FROZEN + alert")
            except Exception:
                pass
        if self.queue is not None:
            try:
                self.queue.enqueue({
                    "sheet": "instagram", "row": "FREEZE",
                    "code": "INSTAGRAM_TOKEN_EXPIRED",
                    "message": "publishing queue frozen: token expired "
                               "(Class-E) — owner action required",
                    "item_key": "instagram|freeze|token"},
                    source_type="SYSTEM_GENERATED", actor="instagram-ops")
            except Exception:
                pass
        return entry

    # -- publish path ---------------------------------------------------------

    def publish(self, ref: Dict, adapter: InstagramAdapter, *,
                actor: str = "instagram-ops",
                poll_budget: int = 10,
                sleep_fn: Optional[Callable[[float], None]] = None,
                backoff_s: float = 0.0) -> Dict:
        """Attempt one publish through the full D-069 workflow.

        Vault lock is acquired BEFORE any network call. Failures are
        classified per D-072; every outcome is recorded durably.
        """
        if self.frozen:
            return {"publish_key": ref.get("publish_key"),
                    "outcome": "queue_frozen", "error_class": "E"}
        key = ref.get("publish_key") or key_from_payload(ref)
        ref = dict(validate_publish_payload(ref), publish_key=key,
                   state=ref.get("state", PENDING))
        # attempt_no derives from DURABLE attempt events (restart-safe)
        attempt_no = self._count_attempts(key) + 1
        attempt_ref = {"content_id": ref["content_id"],
                       "attempt_no": attempt_no,
                       "outcome": "in_progress",
                       "queued_event": f"instagram|publish|{key}"}
        history: List[Dict] = []
        vault = self.vault.acquire(key, attempt_ref)
        if not vault["acquired"]:
            self._record_attempt(key, attempt_no,
                                 "duplicate_publish_blocked")
            self._provenance(actor, ref, "duplicate_blocked")
            return {"publish_key": key,
                    "outcome": "duplicate_publish_blocked",
                    "original": vault["original"], "error_class": "B"}
        # dispatch
        try:
            self._record_transition(key, PENDING, MEDIA_CREATE)
            container = adapter.create_media_container(
                ref["media_ref"], ref["caption"], ref["aspect_ratio"])
            cid = container["container_id"]
            self._record_transition(key, MEDIA_CREATE, CONTAINER_STATUS,
                                    {"container_id": cid})
            from canonical.instagram_adapter import poll_until_ready
            status = poll_until_ready(adapter, cid,
                                      max_polls=poll_budget,
                                      sleep_fn=sleep_fn,
                                      backoff_s=backoff_s)
            self._record_transition(key, CONTAINER_STATUS, MEDIA_PUBLISH,
                                    {"status_code": "FINISHED"})
            pub = adapter.publish_container(cid)
            self._record_transition(key, MEDIA_PUBLISH, PUBLISHED, {
                "publication_id": pub.get("publication_id"),
                "container_id": cid})
            self.vault.finalize(key, dict(attempt_ref,
                                          outcome="published"))
            self._record_attempt(key, attempt_no, "published",
                                 {"publication_id":
                                  pub.get("publication_id")})
            self._provenance(actor, ref, "published")
            return {"publish_key": key, "outcome": "published",
                    "publication_id": pub.get("publication_id"),
                    "container_id": cid}
        except _RateLimited as exc:
            # Class-C: rate limited → cooldown gate, no immediate retry
            wait = min(exc.cooldown_s, self.cooldown_s * (2 ** attempt_no))
            self._cooldown_until[key] = time.monotonic() + wait
            self._record_attempt(key, attempt_no, "cooldown")
            self._provenance(actor, ref, "cooldown")
            return {"publish_key": key, "outcome": "cooldown",
                    "error_class": "C", "retry_after_s": wait}
        except _TokenExpired as exc:
            freeze = self._freeze(ref, exc)
            self._record_transition(key, PENDING, FAILED, {
                "outcome": "token_expired", "frozen": True})
            self._record_attempt(key, attempt_no, "token_expired")
            history.append({"attempt_no": attempt_no,
                            "outcome": "token_expired"})
            self._dead_letter(ref, "E", exc, history)
            self._provenance(actor, ref, "token_expired_frozen")
            return {"publish_key": key, "outcome": "queue_frozen",
                    "error_class": "E", "freeze": freeze}
        except InstagramContractError as exc:
            # Class-B: terminal reject, NO retry
            self._record_transition(key, PENDING, FAILED, {
                "outcome": "rejected_class_b",
                "error": redact(str(exc))[:300]})
            self._record_attempt(key, attempt_no, "rejected_class_b")
            history.append({"attempt_no": attempt_no,
                            "outcome": "rejected_class_b"})
            dl = self._dead_letter(ref, "B", exc, history)
            self._provenance(actor, ref, "rejected_class_b")
            return {"publish_key": key, "outcome": "terminal_reject",
                    "error_class": "B", "dlq": dl}
        except (TimeoutError, ConnectionError, OSError,
                ContainerNotReady) as exc:
            # Class-A: exponential backoff within a bounded retry budget
            history.append({"attempt_no": attempt_no,
                            "outcome": "transient_error",
                            "error": redact(str(exc))[:200]})
            if attempt_no > self.max_retries:
                self._record_transition(key, PENDING, FAILED, {
                    "outcome": "retries_exhausted"})
                self._record_attempt(key, attempt_no, "retries_exhausted")
                dl = self._dead_letter(ref, "A", exc, history)
                self._provenance(actor, ref, "retries_exhausted")
                return {"publish_key": key,
                        "outcome": "retries_exhausted",
                        "error_class": "A", "dlq": dl}
            backoff = backoff_s * (2 ** (attempt_no - 1)) or \
                0.5 * (2 ** (attempt_no - 1))
            self._record_attempt(key, attempt_no, "retry_scheduled",
                                 {"backoff_s": backoff})
            self._provenance(actor, ref, "retry_scheduled")
            return {"publish_key": key, "outcome": "retry_scheduled",
                    "error_class": "A", "attempt_no": attempt_no,
                    "backoff_s": backoff}

    def retry_eligible(self, key: str) -> bool:
        """Class-C cooldown gate: an item on cooldown is NOT eligible
        until its cooldown expires."""
        until = self._cooldown_until.get(key)
        return until is None or time.monotonic() >= until

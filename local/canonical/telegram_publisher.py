"""Phase 10 M3 — Telegram idempotency vault & outbox publisher
(D-074/D-076).

Same durable semantics as the Phase 9 Instagram publisher (D-070/D-072),
adapted to Telegram's error taxonomy:

  - idempotency vault: PRIMARY KEY on telegram.publish_lock IS the
    lock (D-055 SSOT; psql transport, base64 params, no interpolated
    SQL) with a file-backed offline parity vault for local tests.
  - outbox: transactional queue on the D-027 canonical event store;
    enqueue validates LOCALLY first (D-073 Class-B prevention) so an
    invalid payload never occupies an outbox slot.
  - classifier (D-076/D-052):
      Class-A  timeout / 5xx              → exponential backoff retry
      Class-B  invalid payload/parse mode → terminal reject → DLQ
      Class-C  429 + retry_after          → dynamic cooldown honoring
                                              Telegram's exact value
      Class-E  blocked/kicked/token revoked/chat not found/migrated
                                           → queue freeze + HITL alert
    Every outcome is durably recorded (attempt events + transitions)
    and provenance-linked (D-026, best-effort).
  - every error string passes through redact() BEFORE persistence —
    a bot token can never reach the event store, DLQ, or provenance.
"""

import json
import os
import sys
import threading
import time
from typing import Callable, Dict, List, Optional

from canonical.telegram_contracts import (
    FAILED,
    PENDING,
    PUBLISHED,
    TelegramContractError,
    publish_idempotency_key,
    validate_publish_payload,
    validate_transition,
)
from canonical.telegram_adapter import (
    MockTelegramAdapter,
    RatePacer,
    TelegramAdapter,
    _ChatUnreachable,
    _RateLimited,
    redact,
)

SOURCE_SYSTEM = "telegram"
OP_QUEUE = "TELEGRAM_QUEUE_PUBLISH"
OP_PUBLISH = "TELEGRAM_PUBLISH"

HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL = os.path.dirname(HERE)
ROOT = os.path.dirname(LOCAL)
for _p in (LOCAL, os.path.join(LOCAL, "canonical"),
           os.path.join(LOCAL, "services"),
           os.path.join(LOCAL, "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from services.sync_engine import EventStore, ProvenanceEngine  # noqa: E402


# --- vault ------------------------------------------------------------------

class _PgVault:
    """D-074 vault on the live PostgreSQL store (D-055): the PRIMARY
    KEY on telegram.publish_lock IS the lock."""

    def __init__(self):
        scripts = os.path.join("local", "scripts")
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        from canonical.notion_ingest import _exec, _txt  # noqa: E402
        self._exec = _exec
        self._txt = _txt

    def _read(self, key: str) -> Optional[Dict]:
        row = self._exec(
            "SELECT attempt_ref::text || chr(31) || 'END' "
            "FROM telegram.publish_lock WHERE publish_key = "
            + self._txt("k"), {"k": key}).strip()
        if not row:
            return None
        parts = row.split("\x1f")
        if len(parts) >= 2 and parts[-1] == "END" and parts[0]:
            return json.loads(parts[0])
        return None

    def acquire(self, key: str, attempt_ref: Dict) -> Dict:
        """Atomic conditional claim: a published key can never be
        re-claimed (absolute double-post protection); an in-flight or
        failed attempt only yields to a STRICTLY LATER attempt_no
        (restart-safe retries)."""
        ref_json = json.dumps(attempt_ref, ensure_ascii=False,
                              sort_keys=True)
        out = self._exec(
            "INSERT INTO telegram.publish_lock (publish_key, attempt_ref) "
            "VALUES (" + self._txt("k") + ", " + self._txt("r")
            + "::jsonb) "
            "ON CONFLICT (publish_key) DO UPDATE "
            "SET attempt_ref = EXCLUDED.attempt_ref, locked_at = now() "
            "WHERE (telegram.publish_lock.attempt_ref->>'outcome') "
            "IS DISTINCT FROM 'published' "
            "AND COALESCE((telegram.publish_lock.attempt_ref"
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
        """Mark the attempt PUBLISHED — permanent (D-074)."""
        self._exec(
            "UPDATE telegram.publish_lock SET attempt_ref = "
            + self._txt("r") + "::jsonb, locked_at = now() "
            "WHERE publish_key = " + self._txt("k"),
            {"k": key, "r": json.dumps(ref, ensure_ascii=False,
                                       sort_keys=True)})

    def release(self, key: str) -> None:
        # locks are NEVER released on success — double-post
        # protection must outlive the attempt (D-074)
        return None


_PATH_LOCKS: Dict[str, threading.Lock] = {}


def _path_lock(path: str) -> threading.Lock:
    with threading.Lock():
        if path not in _PATH_LOCKS:
            _PATH_LOCKS[path] = threading.Lock()
        return _PATH_LOCKS[path]


class _JsonVault:
    """Offline parity vault (local tests): same verdict semantics,
    file-backed, consistent across instances sharing one file."""

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


# --- publisher ----------------------------------------------------------------

class TelegramOutboxPublisher:
    """Queues posts (D-027 durable), claims and sends them through the
    Bot API under the D-074 vault + pacer, classifying failures
    (D-076) and dead-lettering the unrecoverable."""

    def __init__(self, store, vault,
                 provenance=None, queue=None,
                 max_retries: int = 3,
                 cooldown_s: float = 60.0,
                 pacer: Optional[RatePacer] = None):
        self.store = store
        self.vault = vault
        self.provenance = provenance
        self.queue = queue
        self.max_retries = max_retries
        self.cooldown_s = cooldown_s
        self.pacer = pacer or RatePacer()
        self.frozen = False
        self._cooldown_until: Dict[str, float] = {}
        self.dlq: List[Dict] = []

    # -- outbox ------------------------------------------------------------

    def enqueue(self, payload: Dict, *, actor: str = "telegram-ops"
                ) -> Dict:
        """Queue a post: local validation FIRST (D-073 Class-B
        prevention), then a durable outbox event."""
        norm = validate_publish_payload(payload)  # raises Class-B locally
        key = publish_idempotency_key(
            norm["chat_id"], norm["content_id"], norm["media_hash"],
            norm["text_hash"], norm["scheduled_slot"])
        eid = f"telegram|publish|{key}"
        ref = dict(norm, publish_key=key, state=PENDING, event_id=eid)
        rec = self.store.receive(SOURCE_SYSTEM, eid, OP_QUEUE, ref)
        from services.sync_engine import IntegrityError
        if rec["verdict"] == "integrity_error":
            raise IntegrityError(
                f"conflicting outbox duplicate for {key} — human review")
        if rec["verdict"] in ("new", "retry"):
            # durable queued row: receive → succeed with the payload as
            # ref (the outbox entry must SURVIVE a crash before dispatch)
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
        """Queued items not yet terminal (durable data only),
        deterministic order by scheduled_slot."""
        done = set()
        items: Dict[str, Dict] = {}
        for ref in self._store_refs():
            eid = str(ref.get("event_id", ""))
            key = ref.get("publish_key")
            if eid.startswith("telegram|transition|") \
                    and ref.get("state") in (PUBLISHED, FAILED):
                done.add(key)
            elif eid.startswith("telegram|publish|") \
                    and ref.get("state") == PENDING:
                items[key] = ref
        out = [ref for key, ref in items.items() if key not in done]
        out.sort(key=lambda r: r.get("scheduled_slot", ""))
        return out

    # -- durable bookkeeping -------------------------------------------------

    def _count_attempts(self, key: str) -> int:
        return sum(1 for ref in self._store_refs()
                   if str(ref.get("event_id", ""))
                   .startswith("telegram|attempt|")
                   and ref.get("publish_key") == key)

    def _terminal_state(self, key: str) -> Optional[str]:
        """Durable terminal state of a publish key, if reached
        (PUBLISHED or FAILED) — derived from transition events only."""
        for ref in self._store_refs():
            eid = str(ref.get("event_id", ""))
            if eid.startswith("telegram|transition|") \
                    and ref.get("publish_key") == key \
                    and ref.get("state") in (PUBLISHED, FAILED):
                return ref["state"]
        return None

    def _original_ref(self, key: str) -> Optional[Dict]:
        """The durable queued outbox ref for a key (the 'original'
        surfaced in duplicate-block results)."""
        for ref in self._store_refs():
            if str(ref.get("event_id", "")).startswith(
                    "telegram|publish|") \
                    and ref.get("publish_key") == key:
                return ref
        return None

    def _blocked_attempt(self, key: str, attempt_no: int) -> Dict:
        """Durable record of a blocked (loser) dispatch under a UNIQUE
        event id — concurrent losers must never collide with the
        winner's canonical attempt event (D-027 identity)."""
        eid = f"telegram|blocked|{key}|{time.time_ns()}"
        ref = {"event_id": eid, "publish_key": key,
               "attempt_no": attempt_no, "outcome":
               "duplicate_publish_blocked"}
        self.store.receive(SOURCE_SYSTEM, eid, OP_PUBLISH, ref)
        self.store.succeed(SOURCE_SYSTEM, eid, result_reference=json.dumps(
            ref, ensure_ascii=False, sort_keys=True))
        return ref

    def _record_transition(self, key: str, from_state: str, to_state: str,
                           extra: Optional[Dict] = None) -> Dict:
        validate_transition(from_state, to_state)
        eid = f"telegram|transition|{key}|{to_state}|{time.time_ns()}"
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
        eid = f"telegram|attempt|{key}|{attempt_no}"
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
                source_reference=f"telegram-publish:"
                                 f"{str(ref.get('publish_key'))[:24]}",
                original_value=redact(json.dumps(
                    ref, ensure_ascii=False, sort_keys=True))[:2000],
                notes=f"telegram publish outcome={outcome}")
            self.provenance.link_value(SOURCE_SYSTEM,
                                       str(ref.get("publish_key", ""))[:64],
                                       "attempt", pr)
        except Exception:
            pass  # audit best-effort; publish state stays durable

    def _dead_letter(self, ref: Dict, error_class: str, error: str,
                     history: List[Dict]) -> Dict:
        entry = {"publish_key": ref.get("publish_key"),
                 "content_id": ref.get("content_id"),
                 "chat_id": ref.get("chat_id"),
                 "error_class": error_class,
                 "error": redact(str(error)),
                 "attempts": history,
                 "dead_lettered_at": time.strftime(
                     "%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        self.dlq.append(entry)
        if self.provenance is not None:
            try:
                pr = self.provenance.record(
                    "SYSTEM_GENERATED", "telegram-dlq",
                    source_reference=f"telegram-dlq:"
                                     f"{str(ref.get('publish_key'))[:24]}",
                    original_value=redact(json.dumps(
                        entry, ensure_ascii=False,
                        sort_keys=True))[:2000],
                    notes=f"DLQ: class {error_class}")
                self.provenance.link_value(
                    SOURCE_SYSTEM, str(ref.get("publish_key", ""))[:64],
                    "dlq", pr)
            except Exception:
                pass
        return entry

    def _freeze(self, ref: Dict, error: str) -> Dict:
        """Class-E: freeze the whole queue + HITL alert (D-076)."""
        self.frozen = True
        entry = {"frozen_at": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                            time.gmtime()),
                 "reason": redact(str(error)),
                 "publish_key": ref.get("publish_key")}
        if self.provenance is not None:
            try:
                pr = self.provenance.record(
                    "SYSTEM_GENERATED", "telegram-ops",
                    source_reference="telegram-freeze",
                    original_value=redact(json.dumps(
                        entry, ensure_ascii=False, sort_keys=True)),
                    notes="Class-E chat unreachable — queue FROZEN "
                          "+ alert")
            except Exception:
                pass
        if self.queue is not None:
            try:
                self.queue.enqueue({
                    "sheet": "telegram", "row": "FREEZE",
                    "code": "TELEGRAM_CHAT_UNREACHABLE",
                    "message": "telegram queue frozen: chat unreachable "
                               "(Class-E) — owner action required",
                    "item_key": "telegram|freeze|chat"},
                    source_type="SYSTEM_GENERATED", actor="telegram-ops")
            except Exception:
                pass
        return entry

    # -- dispatch ------------------------------------------------------------

    def _dispatch(self, ref: Dict, adapter: TelegramAdapter) -> Dict:
        """Single Bot API call for the payload kind (adapter is ALWAYS
        one of ours — mock locally, live only after the owner gate)."""
        pm = ref.get("parse_mode", "")
        if ref["kind"] == "text":
            return adapter.send_text(ref["chat_id"], ref["text"], pm)
        if ref["kind"] == "photo":
            return adapter.send_photo(ref["chat_id"], ref["media_ref"],
                                      ref["caption"], pm)
        if ref["kind"] == "video":
            return adapter.send_video(ref["chat_id"], ref["media_ref"],
                                      ref["caption"], pm)
        if ref["kind"] == "document":
            return adapter.send_document(ref["chat_id"], ref["media_ref"],
                                         ref["caption"], pm)
        return adapter.send_media_group(ref["chat_id"], ref["items"],
                                        ref["caption"], pm)

    def publish(self, ref: Dict, adapter: TelegramAdapter, *,
                actor: str = "telegram-ops",
                sleep_fn: Optional[Callable[[float], None]] = None,
                backoff_s: float = 0.0) -> Dict:
        """Attempt one send. Vault lock is acquired BEFORE any adapter
        call; pacer reserves BEFORE the vault-marked dispatch. Failures
        are classified per D-076; every outcome is recorded durably."""
        if self.frozen:
            return {"publish_key": ref.get("publish_key"),
                    "outcome": "queue_frozen", "error_class": "E"}
        key = ref.get("publish_key") or _key_from_ref(ref)
        ref = dict(validate_publish_payload(ref), publish_key=key,
                   state=ref.get("state", PENDING))
        # DURABLE terminal guard: a key that already reached PUBLISHED
        # or FAILED must never dispatch again (D-074/D-076 — the
        # vault alone cannot cover FAILED, which is re-acquirable for
        # retries). This is a hard gate on durable state, so a
        # restarted process obeys it too.
        terminal = self._terminal_state(key)
        if terminal is not None:
            outcome = ("duplicate_publish_blocked" if terminal == PUBLISHED
                       else "terminal_reject")
            original = self._original_ref(key)
            return {"publish_key": key, "outcome": outcome,
                    "state": terminal, "original": original,
                    "error_class": "B"}
        # pacer reservation happens AFTER the vault claim (D-074):
        # losers of the claim must not consume pacer slots. attempt_no
        # is derived from DURABLE attempt events (restart-safe); the
        # per-attempt event id carries time_ns() so concurrent
        # dispatchers never collide on one id (D-027).
        attempt_no = self._count_attempts(key) + 1
        attempt_ref = {"chat_id": ref["chat_id"],
                       "content_id": ref["content_id"],
                       "attempt_no": attempt_no,
                       "outcome": "in_progress",
                       "queued_event": f"telegram|publish|{key}"}
        history: List[Dict] = []
        vault = self.vault.acquire(key, attempt_ref)
        if not vault["acquired"]:
            self._blocked_attempt(key, attempt_no)
            self._provenance(actor, ref, "duplicate_blocked")
            return {"publish_key": key,
                    "outcome": "duplicate_publish_blocked",
                    "original": vault["original"], "error_class": "B"}
        # claim WON: reserve pacer only now (losers never consume slots)
        wait = self.pacer.acquire(ref["chat_id"])
        if wait > 0 and sleep_fn is not None:
            sleep_fn(wait)
        try:
            result = self._dispatch(ref, adapter)
            self._record_transition(key, PENDING, PUBLISHED, {
                "message_id": result.get("message_id"),
                "chat_id": str(ref["chat_id"])})
            self.vault.finalize(key, dict(attempt_ref,
                                          outcome="published"))
            self._record_attempt(key, attempt_no, "published",
                                 {"message_id":
                                  result.get("message_id")})
            self._provenance(actor, ref, "published")
            return {"publish_key": key, "outcome": "published",
                    "message_id": result.get("message_id")}
        except _RateLimited as exc:
            # Class-C: honor Telegram's retry_after EXACTLY (D-076)
            wait_c = max(float(exc.retry_after_s), 0.0)
            self._cooldown_until[key] = time.monotonic() + wait_c
            self._record_attempt(key, attempt_no, "cooldown",
                                 {"retry_after_s": wait_c})
            self._provenance(actor, ref, "cooldown")
            return {"publish_key": key, "outcome": "cooldown",
                    "error_class": "C", "retry_after_s": wait_c}
        except _ChatUnreachable as exc:
            # Class-E: freeze + HITL alert (D-076)
            freeze = self._freeze(ref, exc)
            self._record_transition(key, PENDING, FAILED, {
                "outcome": "chat_unreachable", "frozen": True})
            self._record_attempt(key, attempt_no, "chat_unreachable")
            history.append({"attempt_no": attempt_no,
                            "outcome": "chat_unreachable"})
            self._dead_letter(ref, "E", exc, history)
            self._provenance(actor, ref, "chat_unreachable_frozen")
            return {"publish_key": key, "outcome": "queue_frozen",
                    "error_class": "E", "freeze": freeze}
        except TelegramContractError as exc:
            # Class-B: terminal reject, NO retry (D-076)
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
        except (TimeoutError, ConnectionError, OSError) as exc:
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
        until Telegram's retry_after has elapsed."""
        until = self._cooldown_until.get(key)
        return until is None or time.monotonic() >= until


def _key_from_ref(ref: Dict) -> str:
    norm = validate_publish_payload(ref)
    return publish_idempotency_key(
        norm["chat_id"], norm["content_id"], norm["media_hash"],
        norm["text_hash"], norm["scheduled_slot"])

"""Phase 6 — Notion ingestion path (canonical D-060 contracts → D-027 store).

Wires the M2 data contracts (local/canonical/notion_contracts.py) into
the canonical event store so a Notion payload — mock or live — flows
deterministically:

    payload
      → payload-contract validation (M2 contracts)
      → revision-marker resolution (D-060 interface; wall-clock never key material)
      → D-027/D-060 idempotency key  SHA256('notion'|page_id|event_type|marker)
      → store dedupe (D-027): identical terminal repeat → skipped_duplicate;
        same key different payload → IntegrityError → human review
      → lifecycle transition validation (status_changed events)
      → persist into events.event_record (D-055 PostgreSQL canonical store)
      → D-026 provenance linkage (best-effort; EXTERNAL_SYNC actor)
      → terminal succeeded | skipped_duplicate | failed

Failure semantics (deterministic):
  - contract violation (missing/invalid marker, bad page/type/object) →
    Class B, error_class PAYLOAD_CONTRACT
  - unauthorized transition between KNOWN states → Class B, LIFECYCLE
  - unknown/ambiguous states → Class E (human review, D-061 stance)
  - conflicting duplicate under one D-027 key → IntegrityError raised
    (after the failed delivery is durably recorded), never silent
Every failure persists a durable event row and — when a queue is
provided — materializes one HITL incident item (D-028/D-050: invalid
rows are never silently dropped).

Store contract: `PgEventStore` mirrors the local JSON `EventStore`
(services/sync_engine.py) semantics exactly — (source_system, event_id)
composite key, deterministic repeat classification via
canonical.identifiers.classify_event_repeat, terminal states never
re-entered.

Target-state durability (D-055): a status_changed event's target state
is serialized INSIDE the persisted result_reference (PostgreSQL = SSOT);
rebuild_state replays succeeded events purely from the store — no
in-process memory is required for reconstruction.

No PostgreSQL driver exists on the local host; the store executes
parameter-safe SQL through the seed_registry helper (host psql when
present, else psql inside the engine-local-postgres container). Every
value is base64-encoded into a psql variable and decoded in SQL —
values are never string-formatted into SQL text, so the path is
injection-safe by construction (D-045/D-053: local-only, no secrets).

Ingestion assumption (documented, mirrors the approved M2 fixtures): a
page with no succeeded events is treated as being at the lifecycle root
(Backlog). Unknown states route to Class E — conservative human review
(D-061 stance), never a guess.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from typing import Dict, List, Optional

import seed_registry
from canonical.identifiers import classify_event_repeat
from canonical.notion_contracts import (
    BACKLOG,
    LifecycleViolation,
    PayloadContractError,
    RevisionMarkerResolver,
    notion_idempotency_key,
    validate_mock_payload,
    validate_transition,
)
from services.sync_engine import IntegrityError

SOURCE_SYSTEM = "notion"
OP_CONTENT_IDEA = "NOTION_CONTENT_IDEA"
OP_PRE_KEY_CHECK = "NOTION_PRE_KEY_CHECK"
OP_CONFLICT = "NOTION_CONFLICT"

_ERROR_PAYLOAD_CONTRACT = "PAYLOAD_CONTRACT"
_ERROR_LIFECYCLE = "LIFECYCLE"
_ERROR_CONFLICT = "CONFLICTING_DUPLICATE"


def _payload_hash(payload) -> str:
    """Canonical SHA-256 of a JSON-serializable payload (mirrors sync_engine)."""
    return hashlib.sha256(json.dumps(
        payload, sort_keys=True, ensure_ascii=False,
        default=str).encode("utf-8")).hexdigest()


def _pre_key(payload) -> str:
    """Deterministic pre-key event id for payloads that never reach the
    D-027 key derivation (contract failures, conflicts)."""
    return "prekey|" + _payload_hash(payload)[:32]


# ---------------------------------------------------------------------------
# Parameter-safe SQL execution (psql variables + base64, never interpolation)
# ---------------------------------------------------------------------------

_VAR_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")


def _b64(value) -> str:
    return base64.b64encode(str(value).encode("utf-8")).decode("ascii")


def _txt(param: str) -> str:
    """SQL expression decoding a psql variable into text."""
    return f"convert_from(decode(:'{param}','base64'),'UTF8')"


def _exec(sql: str, params: Optional[Dict] = None) -> str:
    """Run SQL through seed_registry.q with base64 psql variables.

    Each parameter becomes a `\\set name '<base64>'` line prepended to the
    script; base64's alphabet contains no psql metacharacters, so
    arbitrary values (JSON, messages, ids) pass through safely. SQL text
    is never built by interpolation of values.
    """
    if not params:
        return seed_registry.q(sql)
    lines = []
    for name in sorted(params):
        if not _VAR_NAME_RE.match(name):
            raise ValueError(f"invalid SQL parameter name: {name!r}")
        lines.append(f"\\set {name} '{_b64(params[name])}'")
    return seed_registry.q("\n".join(lines) + "\n" + sql)


def _split_row(out: str) -> list:
    """Split a single-row, chr(31)-delimited SELECT result."""
    out = out.strip()
    if not out:
        return []
    return out.split("\x1f")


# ---------------------------------------------------------------------------
# PostgreSQL event store (D-027) — same semantics as the JSON EventStore
# ---------------------------------------------------------------------------


class PgEventStore:
    """D-027 event store backed by the canonical PostgreSQL instance
    (D-055 SSOT). Interface parity with services.sync_engine.EventStore:

      - key(source_system, event_id) → "source_system::event_id"
      - receive() → {"record": …, "verdict": new|retry|skipped_duplicate}
        (raises IntegrityError on a conflicting duplicate)
      - begin()/succeed()/fail()/mark_skipped_duplicate()
      - terminal statuses never re-entered (IntegrityError)
    """

    def __init__(self, source_system: str = SOURCE_SYSTEM):
        self.source_system = source_system

    @staticmethod
    def key(source_system: str, event_id: str) -> str:
        return f"{source_system}::{event_id}"

    # -- internal helpers ---------------------------------------------------

    def _where(self) -> str:
        return (f"source_system = {_txt('src')} "
                f"AND event_id = {_txt('eid')}")

    def _params(self, event_id: str, **extra) -> Dict:
        params = {"src": self.source_system, "eid": event_id}
        params.update(extra)
        return params

    def _get(self, event_id: str) -> Optional[dict]:
        row = _exec(
            "SELECT processing_status || chr(31) || payload_hash "
            "|| chr(31) || retry_count FROM events.event_record "
            f"WHERE {self._where()}",
            self._params(event_id),
        ).strip()
        if not row:
            return None
        status, payload_hash, retry_count = _split_row(row)
        return {"processing_status": status, "payload_hash": payload_hash,
                "retry_count": int(retry_count)}

    # -- D-027 interface ------------------------------------------------------

    def receive(self, source_system: str, event_id: str,
                operation_type: str, payload) -> dict:
        """Register/refresh an event; classify repeats deterministically.

        Raises IntegrityError on a conflicting duplicate (same key,
        different payload, terminal status) — human review, never
        silently reprocessed.
        """
        ph = _payload_hash(payload)
        inserted = _exec(
            "INSERT INTO events.event_record "
            "(source_system, event_id, operation_type, processing_status, payload_hash) "
            f"VALUES ({_txt('src')}, {_txt('eid')}, {_txt('op')}, 'received', {_txt('ph')}) "
            "ON CONFLICT (source_system, event_id) DO NOTHING "
            "RETURNING processing_status",
            self._params(event_id, op=operation_type, ph=ph),
        ).strip()
        if inserted:
            return {"record": {
                "source_system": source_system,
                "event_id": event_id,
                "operation_type": operation_type,
                "processing_status": "received",
                "payload_hash": ph,
                "retry_count": 0,
            }, "verdict": "new"}

        existing = self._get(event_id)
        if existing is None:  # raced delete — treat as new
            return self.receive(source_system, event_id, operation_type, payload)
        verdict = classify_event_repeat(
            existing["processing_status"], existing["payload_hash"], ph)
        if verdict == "integrity_error":
            raise IntegrityError(
                f"D-027 conflicting duplicate: event {event_id} already "
                "terminal with a different payload — human review "
                "required (never silently reprocessed)")
        if verdict == "retry":
            _exec(
                "UPDATE events.event_record SET processing_status = 'received', "
                f"operation_type = {_txt('op')}, retry_count = retry_count + 1, "
                "last_attempt_at = now() "
                f"WHERE {self._where()}",
                self._params(event_id, op=operation_type),
            )
            existing["retry_count"] += 1
            existing["processing_status"] = "received"
            return {"record": existing, "verdict": "retry"}
        return {"record": existing, "verdict": verdict}  # skipped_duplicate

    def begin(self, source_system: str, event_id: str):
        rec = self._get(event_id)
        if rec is None:
            raise KeyError(f"unknown event: {event_id}")
        if rec["processing_status"] in ("succeeded", "skipped_duplicate"):
            self._raise_terminal(event_id, "processing")
        self._guarded_update(event_id, "processing")
        return self._get(event_id)

    def succeed(self, source_system: str, event_id: str,
                result_reference: str):
        updated = self._guarded_update(
            event_id, "succeeded", result_reference=result_reference)
        if not updated:
            self._raise_terminal(event_id, "succeeded")

    def fail(self, source_system: str, event_id: str, error_class: str):
        updated = self._guarded_update(
            event_id, "failed", error_class=error_class)
        if not updated:
            self._raise_terminal(event_id, "failed")

    def mark_skipped_duplicate(self, source_system: str, event_id: str):
        if not self._guarded_update(event_id, "skipped_duplicate"):
            self._raise_terminal(event_id, "skipped_duplicate")

    # -- transitions ----------------------------------------------------------

    def _guarded_update(self, event_id: str, new_status: str,
                        result_reference: str = None,
                        error_class: str = None) -> bool:
        sets = ["processing_status = " + _txt("st"),
                "last_attempt_at = now()"]
        params = self._params(event_id, st=new_status)
        if result_reference is not None:
            sets.append("result_reference = " + _txt("ref"))
            params["ref"] = result_reference
        if error_class is None:
            sets.append("last_error_class = NULL")
        else:
            sets.append("last_error_class = " + _txt("ec"))
            params["ec"] = error_class
        out = _exec(
            "UPDATE events.event_record SET " + ", ".join(sets) +
            f" WHERE {self._where()} AND processing_status "
            "NOT IN ('succeeded','skipped_duplicate') "
            "RETURNING event_id",
            params,
        ).strip()
        return bool(out)

    @staticmethod
    def _raise_terminal(event_id: str, attempted: str):
        raise IntegrityError(
            f"terminal event {event_id} cannot re-enter "
            f"'{attempted}' (D-027)")


def record_provenance(provenance, store: PgEventStore, event_id: str,
                      actor: str, payload_ref: dict) -> Optional[int]:
    """Attach a D-026 provenance record + linkage (best-effort).

    Provenance is an audit layer, not the ingestion transaction: if the
    provenance store is unavailable the event still persists. Any error
    other than an unavailable store propagates (programming errors must
    not be swallowed).
    """
    if provenance is None:
        return None
    try:
        pr = provenance.record(
            "EXTERNAL_SYNC", actor,
            source_reference=f"notion::{event_id[:32]}",
            original_value=json.dumps(payload_ref, ensure_ascii=False,
                                      sort_keys=True),
            notes="notion event ingested into D-027 event store")
    except RuntimeError:
        return None  # provenance store unavailable — audit skipped
    try:
        provenance.link_value(
            "events.event_record", store.key(store.source_system, event_id),
            "payload_hash", pr)
    except RuntimeError:
        return None
    return pr


def _enqueue_incident(queue, payload, *, code: str, message: str,
                      failure_class: str, item_key: str, actor: str):
    """Materialize a Class-B/E failure into the HITL queue (D-028/D-050).

    Invalid rows are never silently dropped; the queue's own
    deterministic dedupe makes re-delivery of the same failure a no-op.
    """
    if queue is None:
        return None
    page = str(payload.get("page_id") or "?")
    return queue.enqueue({
        "sheet": "notion-ingest",
        "row": page,
        "code": code,
        "message": str(message)[:300],
        "page_id": page,
        "event_type": payload.get("event_type"),
        "failure_class": failure_class,
        "item_key": item_key,
    }, source_type="EXTERNAL_SYNC", actor=actor)


# ---------------------------------------------------------------------------
# Ingestion pipeline
# ---------------------------------------------------------------------------


def ingest_notion_event(payload: Dict, store: Optional[PgEventStore] = None,
                        *, queue=None, provenance=None,
                        actor: str = "notion-ingest") -> dict:
    """Ingest one Notion payload end-to-end. Returns a result dict:
    {"status": succeeded|skipped_duplicate|failed, "event_id": …, …}.

    Failure semantics (deterministic):
      - payload-contract violation (missing/invalid marker, bad type) →
        Class B, error_class PAYLOAD_CONTRACT
      - unauthorized transition between known states → Class B,
        error_class LIFECYCLE
      - unknown/ambiguous states → Class E (human review, D-061 stance)
      - conflicting duplicate under one D-027 key → durable failed row
        + HITL item; IntegrityError surfaces only when the caller
        re-delivers AFTER the review item exists (never silent)
    Every failure persists a durable failed event row and (when a queue
    is provided) enqueues one HITL incident item.
    """
    store = store or PgEventStore()
    # D-027 interface parity: stores MAY expose source_system (PgEventStore
    # does); the JSON local store takes it per call — default to 'notion'.
    src = getattr(store, "source_system", SOURCE_SYSTEM)
    resolver = RevisionMarkerResolver()
    raw = payload if isinstance(payload, dict) else {}

    def record_failure(op_type: str, failure_class: str, error_class: str,
                       message: str) -> dict:
        eid = _pre_key(raw)
        store.receive(src, eid, op_type, raw)
        try:
            store.fail(src, eid, error_class)
        except IntegrityError:
            pass  # terminal pre-key row already failed identically
        _enqueue_incident(
            queue, raw, code=f"NOTION_{error_class}",
            message=message, failure_class=failure_class,
            item_key=f"notion|{eid}", actor=actor)
        return {"status": "failed", "event_id": eid,
                "error_class": error_class, "failure_class": failure_class,
                "error": message}

    # 1) payload-contract validation (shape only — state-machine legality
    #    is a post-receive concern) + key derivation
    try:
        marker = resolver.resolve(raw)
        validate_mock_payload(
            raw, resolver=resolver, check_transition=False)
        page_id = str(raw.get("page_id", "")).strip()
        event_type = str(raw.get("event_type", "")).strip()
        eid = notion_idempotency_key(page_id, event_type, marker,
                                     source_system=src)
    except (PayloadContractError, ValueError) as exc:
        failure_class = getattr(exc, "failure_class", "B")
        return record_failure(OP_PRE_KEY_CHECK, failure_class,
                              _ERROR_PAYLOAD_CONTRACT, str(exc))

    record_event = {
        "page_id": page_id,
        "event_type": event_type,
        "revision_marker": marker,
        "object": raw.get("object"),
    }
    if event_type == "status_changed":
        record_event["current_state"] = str(raw.get("current_state", ""))
        record_event["target_state"] = str(raw.get("target_state", ""))

    # 2) D-027 dedupe against the canonical store
    try:
        rec = store.receive(src, eid, OP_CONTENT_IDEA,
                            record_event)
    except IntegrityError as exc:
        # First sighting of the conflict in this delivery: record the
        # failed delivery durably (pre-key) + HITL item. A repeat
        # sighting (conflict already on record) re-raises so callers
        # never mistake an unprocessed conflict for success.
        eid2 = _pre_key(raw)
        seen = _exec(
            "SELECT 1 FROM events.event_record WHERE "
            + store._where() + " "
            "AND processing_status = 'failed' "
            "AND last_error_class = " + _txt("ec"),
            store._params(eid2, ec=_ERROR_CONFLICT),
        ).strip()
        if seen:
            raise
        store.receive(store.source_system, eid2, OP_CONFLICT, raw)
        try:
            store.fail(store.source_system, eid2, _ERROR_CONFLICT)
        except IntegrityError:
            pass
        _enqueue_incident(
            queue, raw, code="NOTION_CONFLICTING_DUPLICATE",
            message=str(exc), failure_class="B",
            item_key=f"notion|conflict|{eid[:24]}", actor=actor)
        return {"status": "failed", "event_id": eid2,
                "error_class": _ERROR_CONFLICT, "failure_class": "B",
                "error": str(exc), "page_id": page_id}

    if rec["verdict"] == "skipped_duplicate":
        return {"status": "skipped_duplicate", "event_id": eid,
                "verdict": "skipped_duplicate",
                "page_id": page_id, "event_type": event_type}

    # 3) lifecycle validation (inside the open event — failures durably failed)
    store.begin(src, eid)
    if event_type == "status_changed":
        current = record_event["current_state"]
        target = record_event["target_state"]
        try:
            validate_transition(current, target)
        except LifecycleViolation as exc:
            store.fail(src, eid, _ERROR_LIFECYCLE)
            _enqueue_incident(
                queue, raw, code="NOTION_LIFECYCLE", message=str(exc),
                failure_class=exc.failure_class,
                item_key=f"notion|lifecycle|{eid[:24]}|{current}|{target}",
                actor=actor)
            return {"status": "failed", "event_id": eid,
                    "error_class": _ERROR_LIFECYCLE,
                    "failure_class": exc.failure_class,
                    "error": str(exc), "page_id": page_id}

    # 4) D-026 provenance linkage (best-effort) + terminal success
    pr = record_provenance(provenance, store, eid, actor, record_event)
    store.succeed(src, eid, result_reference=json.dumps(
        record_event, ensure_ascii=False, sort_keys=True))
    return {"status": "succeeded", "event_id": eid,
            "verdict": rec["verdict"], "page_id": page_id,
            "event_type": event_type, "provenance_id": pr}


# ---------------------------------------------------------------------------
# State reconstruction (event-sourced, deterministic, store-only)
# ---------------------------------------------------------------------------


def rebuild_state(store: PgEventStore, page_id: str) -> dict:
    """Rebuild a page's lifecycle position from succeeded events in the
    canonical store (D-055: PostgreSQL is the SSOT — reconstruction uses
    ONLY persisted data, no in-process memory).

    Deterministic: events are applied in received_at order (each ingest
    step is its own psql transaction, so timestamps never tie; event_id
    breaks any theoretical tie deterministically). The target state
    travels INSIDE each event's result_reference.

    History base (honesty rule): the chain starts at the first
    OBSERVED current_state — for pages onboarded mid-lifecycle (first
    poll of an existing workspace) the system never saw the earlier
    transitions and must not fabricate them; the Backlog root applies
    only to pages with no succeeded events (documented ingestion
    assumption above, mirroring the M2 fixtures).
    """
    rows = _exec(
        "SELECT result_reference FROM events.event_record "
        f"WHERE source_system = {_txt('src')} "
        "AND processing_status = 'succeeded' "
        "ORDER BY received_at, event_id",
        {"src": store.source_system},
    )
    targets: List[str] = []
    base: Optional[str] = None
    for line in rows.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ref = json.loads(line)
        except json.JSONDecodeError:
            continue  # non-JSON result_reference (defensive)
        if not isinstance(ref, dict) or ref.get("page_id") != page_id:
            continue
        if ref.get("event_type") == "status_changed":
            if base is None:
                cur = ref.get("current_state")
                base = cur if isinstance(cur, str) and cur else BACKLOG
            target = ref.get("target_state")
            if isinstance(target, str) and target:
                targets.append(target)
    history = [base or BACKLOG] + targets if targets else []
    current = targets[-1] if targets else BACKLOG
    for a, b in zip(history, history[1:]):
        validate_transition(a, b)  # store contents must be self-consistent
    return {"page_id": page_id, "current_state": current,
            "history": history}


# ---------------------------------------------------------------------------
# Review-queue helpers (HITL materialization for failed deliveries)
# ---------------------------------------------------------------------------


def pending_notion_incidents(queue) -> List[dict]:
    """Return the queue's pending Notion-ingest items (review aid)."""
    if queue is None:
        return []
    return [item for item in queue.pending_items()
            if item.get("sheet") == "notion-ingest"]

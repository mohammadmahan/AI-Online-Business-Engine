"""Phase 22 M1 — canonical operational log ledger (D-121/D-124).

The `engine.log.v1` record and its emitter: a structured, append-only
event log for ALL operational subsystems (analytics, HITL, dispatch,
security, scheduling, oms, admin). Design invariants:

  - DETERMINISTIC identification: `trace_id` / `causal_chain_id` are
    SHA-256 derivations over CAUSAL inputs (domain, entity ref,
    logical sequence) — never wall-clock, never `time.time_ns()`.
    Same causal inputs ⇒ same ids (battery-asserted).
  - D-114 AT THE BOUNDARY: every string that enters a record passes
    the Phase 20 InputHardeningGate plus the D-124 telemetry
    redaction list; oversized values are explicitly marked
    (`…[TRUNC]`), never silently truncated; non-conforming structure
    is a Class-B programming error (`ObservabilityContractError`).
  - NO ENGINE IMPORTS: this module observes the world via what the
    caller hands it (RULES §35 boundary discipline). The only
    cross-module dependency is the Phase 20 security engine (a
    contracts/guard layer, not an engine) and, for the DURABLE vault
    only, the D-027 store transport — injected, live-layer guarded.
  - The Phase 8 AI surface (`ai.observe.v1`) is unchanged and stays
    the AI pipeline's own collector; this ledger is the OPERATIONAL
    counterpart, not a replacement.

Schema (required fields): schema_version, trace_id, causal_chain_id,
logical_at, domain, event, level, status. Optional: entity_ref,
payload (flat scalar dict), detail.
"""

import hashlib
import json
import re
import threading
from typing import Dict, List, Optional

from canonical.security_engine import InputHardeningGate, InputRejected
from canonical.security_contracts import HardeningPolicy

SCHEMA_VERSION = "engine.log.v1"

LEVELS = ("DEBUG", "INFO", "WARN", "ERROR")
DOMAINS = ("analytics", "hitl", "dispatch", "security", "scheduling",
           "oms", "admin")
STATUSES = ("SUCCESS", "FAILURE", "DEGRADED", "SKIPPED")

# D-124 telemetry redaction list (mirrors the Phase 8 collector list
# and the n8n failure taxonomy's redaction rules).
_REDACT_MARKERS = (
    re.compile(r"postgres://[^\s]+", re.I),
    re.compile(r"bearer\s+[A-Za-z0-9._\-]+", re.I),
    re.compile(r"api_key[=:]\s*\S+", re.I),
    re.compile(r"password[=:]\s*\S+", re.I),
    re.compile(r"authorization:\s*\S+", re.I),
)
_PII_KEYS = ("email", "phone", "customer_name", "full_name", "first_name",
             "last_name", "address", "national_id", "iban", "card_number")
REDACTED = "[REDACTED]"
_TRUNC = "…[TRUNC]"

# Telemetry policy bounds (declared, D-114): log fields are shorter
# than general payloads by design — unbounded logs ARE the leak.
_LOG_POLICY = HardeningPolicy(max_payload_bytes=16384,
                              max_string_len=4096,
                              max_json_depth=2,
                              max_json_width=64,
                              max_list_items=32)
_MAX_FIELD = 512
_MAX_PAYLOAD_FIELDS = 32

_GATE = InputHardeningGate(_LOG_POLICY)


class ObservabilityContractError(ValueError):
    """A malformed telemetry record (Class-B programming error)."""


def _reject(reason: str):
    raise ObservabilityContractError(reason)


def _gate_str(value: str) -> str:
    """D-114 gate with the telemetry error taxonomy: a gate rejection
    is a boundary violation — wrapped as ObservabilityContractError so
    callers handle ONE Class-B type at the log boundary."""
    try:
        return _GATE.check_string(value)
    except InputRejected as e:
        _reject(f"input_rejected:{e}")


def _gate_id(value: str) -> str:
    try:
        return _GATE.check_identifier(value)
    except InputRejected as e:
        _reject(f"input_rejected:{e}")


def redact(value: str) -> str:
    """D-124: replace credential-shaped spans with the fixed marker.

    Deterministic and idempotent (redacting redacted text is a
    no-op) — battery-asserted.
    """
    out = value
    for pattern in _REDACT_MARKERS:
        out = pattern.sub(REDACTED, out)
    return out


def _sanitize_str(value: str) -> str:
    """Redact → explicit, marked truncation → D-114 gate.

    Truncation runs BEFORE the gate: the log boundary's declared
    semantics are that oversized values are MARKED (never silently
    truncated, never rejected for size), while control characters and
    confusables remain Class-B rejections."""
    if not isinstance(value, str):
        _reject("telemetry_string_expected")
    v = redact(value)
    if len(v) > _MAX_FIELD:
        v = v[:_MAX_FIELD - len(_TRUNC)] + _TRUNC
    v = _gate_str(v)                   # control chars/confusables → Class-B
    return v


def _sanitize_payload(payload: Optional[Dict]) -> Optional[Dict]:
    """Flat scalar payload only: depth 1, declared width cap, keys via
    the identifier gate, PII-keyed values replaced by the marker."""
    if payload is None:
        return None
    if not isinstance(payload, dict):
        _reject("payload_must_be_flat_dict")
    if len(payload) > _MAX_PAYLOAD_FIELDS:
        _reject("payload_too_wide")
    out: Dict = {}
    for k, v in payload.items():
        key = _gate_id(str(k))
        if any(p in key.lower() for p in _PII_KEYS):
            out[key] = REDACTED
            continue
        if v is None or isinstance(v, bool):
            out[key] = v
        elif isinstance(v, int):
            out[key] = v
        elif isinstance(v, float):
            out[key] = v
        elif isinstance(v, str):
            out[key] = _sanitize_str(v)
        else:
            _reject(f"payload_value_type_not_allowed:{type(v).__name__}")
    return out


# --- deterministic identification (D-121) -----------------------------------


def root_trace(domain: str, entity_ref: str, logical_seq: str) -> str:
    """Deterministic trace id from causal inputs — same inputs, same
    id, forever. `logical_seq` is the caller's logical tick/counter."""
    material = f"trace|{domain}|{entity_ref}|{logical_seq}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


class TraceContext:
    """Immutable causal chain handle: `child(event)` derives the next
    causal id from (trace, parent causal, event, seq) — propagation
    across process/sink boundaries is just carrying this dict."""

    __slots__ = ("trace_id", "causal_chain_id", "seq")

    def __init__(self, trace_id: str, causal_chain_id: str, seq: int = 0):
        if not trace_id or not causal_chain_id:
            _reject("trace_context_needs_ids")
        self.trace_id = trace_id
        self.causal_chain_id = causal_chain_id
        self.seq = int(seq)

    @classmethod
    def root(cls, domain: str, entity_ref: str, logical_seq: str
             ) -> "TraceContext":
        tid = root_trace(domain, entity_ref, logical_seq)
        return cls(tid, tid, 0)

    def child(self, event: str) -> "TraceContext":
        material = (f"causal|{self.trace_id}|{self.causal_chain_id}"
                    f"|{event}|{self.seq + 1}")
        cid = hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]
        return TraceContext(self.trace_id, cid, self.seq + 1)

    def to_dict(self) -> Dict:
        return {"trace_id": self.trace_id,
                "causal_chain_id": self.causal_chain_id, "seq": self.seq}


# --- record assembly & validation --------------------------------------------

def build_record(ctx: TraceContext, *, domain: str, event: str,
                 logical_at: str, level: str = "INFO",
                 status: str = "SUCCESS", entity_ref: Optional[str] = None,
                 payload: Optional[Dict] = None,
                 detail: Optional[str] = None) -> Dict:
    """Build + sanitize + validate one engine.log.v1 record."""
    if domain not in DOMAINS:
        _reject(f"unknown_domain:{domain}")
    if level not in LEVELS:
        _reject(f"unknown_level:{level}")
    if status not in STATUSES:
        _reject(f"unknown_status:{status}")
    if not event or not isinstance(event, str):
        _reject("event_required")
    if not logical_at or not isinstance(logical_at, str):
        _reject("logical_at_required (injected clock, never wall time)")
    rec = {
        "schema_version": SCHEMA_VERSION,
        "trace_id": ctx.trace_id,
        "causal_chain_id": ctx.causal_chain_id,
        "causal_seq": ctx.seq,
        "logical_at": _sanitize_str(logical_at),
        "domain": domain,
        "event": _gate_id(event),
        "level": level,
        "status": status,
    }
    if entity_ref is not None:
        rec["entity_ref"] = _gate_id(str(entity_ref))
    sp = _sanitize_payload(payload)
    if sp is not None:
        rec["payload"] = sp
    if detail is not None:
        rec["detail"] = _sanitize_str(detail)
    return rec


def validate_record(rec: Dict) -> Dict:
    """Structural validation (used on read-back and by the battery)."""
    if not isinstance(rec, dict):
        _reject("record_must_be_dict")
    for f in ("schema_version", "trace_id", "causal_chain_id",
              "logical_at", "domain", "event", "level", "status"):
        if f not in rec or not rec[f]:
            _reject(f"missing_required_field:{f}")
    if rec["schema_version"] != SCHEMA_VERSION:
        _reject("schema_version_mismatch")
    if rec["domain"] not in DOMAINS or rec["level"] not in LEVELS \
            or rec["status"] not in STATUSES:
        _reject("enum_field_out_of_range")
    return rec


# --- sinks (D-121): JSONL parity + durable D-027-backed vault -----------------

class JsonlLogSink:
    """Append-only JSONL file sink (local parity). Thread-safe."""

    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()

    def append(self, rec: Dict) -> None:
        line = json.dumps(rec, ensure_ascii=False, sort_keys=True)
        with self._lock:
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")

    def read_all(self) -> List[Dict]:
        try:
            with open(self.path, encoding="utf-8") as fh:
                return [json.loads(l) for l in fh if l.strip()]
        except FileNotFoundError:
            return []


class PgLogVault:
    """Durable engine.log.v1 storage over the D-027 event store
    (deterministic row key: event_id = log|<causal_chain_id>), so a
    re-emitted record dedupes instead of duplicating. Live-layer only;
    constructed lazily so offline tests never touch Docker."""

    SOURCE = "obslog"

    def __init__(self):
        from canonical.notion_ingest import PgEventStore  # noqa: E402
        self._store = PgEventStore(self.SOURCE)

    def append(self, rec: Dict) -> str:
        # Row key embeds BOTH ids: causal id dedupes re-emissions;
        # the trace prefix makes trace-scoped queries a deterministic
        # LIKE over hex characters only.
        eid = f"log|{rec['trace_id']}|{rec['causal_chain_id']}"
        verdict = self._store.receive(self.SOURCE, eid, "engine_log",
                                      rec)["verdict"]
        if verdict in ("new", "retry"):
            self._store.begin(self.SOURCE, eid)
            self._store.succeed(self.SOURCE, eid,
                                result_reference=f"log:{rec['event']}")
            return "stored"
        return verdict  # skipped_duplicate

    def count(self, trace_id: Optional[str] = None) -> int:
        from canonical.notion_ingest import _exec, _txt  # noqa: E402
        sql = ("SELECT count(*) FROM events.event_record WHERE "
               "source_system = " + _txt("s"))
        params = {"s": self.SOURCE}
        if trace_id:
            sql += (" AND event_id LIKE " + _txt("p"))
            # trace scoping uses the deterministic key prefix; the id
            # space is hex + pipes, so no LIKE escaping is needed.
            params["p"] = f"log|{trace_id}|%"
        out = _exec(sql, params).strip()
        return int(out or "0")


class LogLedger:
    """The D-121 emitter: validates, sanitizes, then fans out to the
    configured sinks (JSONL parity and/or the durable vault)."""

    def __init__(self, sink: Optional[JsonlLogSink] = None,
                 vault: Optional[PgLogVault] = None):
        self.sink = sink
        self.vault = vault
        self._lock = threading.Lock()

    def emit(self, ctx: TraceContext, *, domain: str, event: str,
             logical_at: str, level: str = "INFO",
             status: str = "SUCCESS", entity_ref: Optional[str] = None,
             payload: Optional[Dict] = None,
             detail: Optional[str] = None) -> Dict:
        rec = build_record(ctx, domain=domain, event=event,
                           logical_at=logical_at, level=level,
                           status=status, entity_ref=entity_ref,
                           payload=payload, detail=detail)
        with self._lock:
            if self.sink is not None:
                self.sink.append(rec)
            if self.vault is not None:
                rec["vault_verdict"] = self.vault.append(rec)
        return rec

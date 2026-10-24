"""D-142 — hermetic transport seam for MemWal sync (envelope contract).

The memory layer never talks to Walrus by itself. `MemWalClientAdapter`
takes an INJECTED callable and treats any failure as a degraded sync.
This module is the contract that callable must satisfy, plus the pure
machinery that makes the edge safe to build against later:

  - **Envelope, not a bare list.** `memwal.transport.v1` carries the
    format tag, positional batch metadata and - critically - a
    deterministic `idempotency_key` derived from the batch content. A
    retried batch is byte-identical, so a future relayer can recognise
    it without a second source of truth in our process.
  - **Bounded batches.** Rows are chunked by count AND canonical byte
    size; a row is never split, reordered, dropped or duplicated. A
    single row larger than the byte budget is refused as a contract
    error (fail-closed, never truncated).
  - **D-052/D-044 taxonomy.** `classify_error` maps an exception or an
    HTTP-ish status onto the approved split between retryable and
    non-retryable. No retry counts or backoff constants are defined
    here - D-044 leaves those to the owning workflow, so this module
    reports `retryable` / `requires_reconciliation` and stops.
  - **Zero-leak (D-114/D-124) re-asserted at the edge.** The adapter
    redacts on export; this module redacts AGAIN before a batch leaves
    the process, because a transport is the last place memory text is
    still readable by a third party.
  - **Never raises into the agent.** `TransportClient.send` returns a
    verdict for every outcome, including its own misuse and a remote
    that raises. The existing zero-blockage guarantee in
    `memwal_adapter.sync` therefore keeps its meaning.

Not here, by design: no HTTP client, no SDK, no socket, no credential,
no retry loop, no wall clock. `D-045` keeps the remote on the far side
of an owner authorization; this file is what can be proven offline.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

try:  # package-relative (battery) or script (cwd=local)
    from .vector_store import deep_redact
except ImportError:  # pragma: no cover - script-context alias
    from local.src.memory.vector_store import deep_redact

__all__ = [
    "ENVELOPE_FORMAT", "DEFAULT_MAX_ROWS", "DEFAULT_MAX_BYTES",
    "TransportContractError", "TransportFault", "TRANSPORT_FAULTS",
    "classify_error", "classify_status", "redact_rows", "canonical_bytes",
    "idempotency_key", "chunk_rows", "build_envelope",
    "validate_envelope", "TransportVerdict", "TransportClient",
    "EnvelopeTransport",
]

ENVELOPE_FORMAT = "memwal.transport.v1"

# Bounded batches: small enough that a relayer retry is cheap, large
# enough that a sync is not a per-row round trip. Both are ceilings,
# not targets - callers may lower them.
DEFAULT_MAX_ROWS = 50
DEFAULT_MAX_BYTES = 64 * 1024


class TransportContractError(ValueError):
    """Envelope/batch misuse (fail-closed, offline)."""


def _fail(reason: str):
    raise TransportContractError(reason)


# ---------------------------------------------------------------------------
# D-044 taxonomy
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TransportFault:
    """One classified outcome. Carries no message from the far side.

    `requires_reconciliation` marks the single dangerous case: the
    batch MAY have landed and we cannot prove it did. D-044 permits a
    retry only after a read-back, never a blind re-send.
    """
    code: str
    retryable: bool
    requires_reconciliation: bool = False


TRANSPORT_FAULTS: Dict[str, TransportFault] = {
    # -- retryable (D-044 item 3) -----------------------------------------
    "TRANSPORT_UNAVAILABLE": TransportFault("TRANSPORT_UNAVAILABLE", True),
    "TRANSPORT_TIMEOUT": TransportFault("TRANSPORT_TIMEOUT", True),
    "TRANSPORT_RATE_LIMITED": TransportFault("TRANSPORT_RATE_LIMITED", True),
    # A raised timeout proves no verdict, not "nothing happened".
    "TRANSPORT_AMBIGUOUS_TIMEOUT": TransportFault(
        "TRANSPORT_AMBIGUOUS_TIMEOUT", True, requires_reconciliation=True),
    # -- non-retryable (D-044 item 3) -------------------------------------
    "TRANSPORT_AUTH_FAILED": TransportFault("TRANSPORT_AUTH_FAILED", False),
    "TRANSPORT_VALIDATION_REFUSED": TransportFault(
        "TRANSPORT_VALIDATION_REFUSED", False),
    "TRANSPORT_CONFLICT": TransportFault("TRANSPORT_CONFLICT", False),
    "TRANSPORT_MALFORMED_RESPONSE": TransportFault(
        "TRANSPORT_MALFORMED_RESPONSE", False),
    "TRANSPORT_REMOTE_REFUSED": TransportFault(
        "TRANSPORT_REMOTE_REFUSED", False),
    "TRANSPORT_INTERNAL": TransportFault("TRANSPORT_INTERNAL", False),
}

# Status → code. Deliberately conservative: anything unknown is
# non-retryable, so an unclassified status cannot cause a retry storm.
_STATUS_CODES: Dict[int, str] = {
    400: "TRANSPORT_VALIDATION_REFUSED",
    401: "TRANSPORT_AUTH_FAILED",
    403: "TRANSPORT_AUTH_FAILED",
    408: "TRANSPORT_TIMEOUT",
    409: "TRANSPORT_CONFLICT",
    422: "TRANSPORT_VALIDATION_REFUSED",
    429: "TRANSPORT_RATE_LIMITED",
    500: "TRANSPORT_UNAVAILABLE",
    502: "TRANSPORT_UNAVAILABLE",
    503: "TRANSPORT_UNAVAILABLE",
    504: "TRANSPORT_UNAVAILABLE",
}


def _fault(code: str) -> TransportFault:
    return TRANSPORT_FAULTS.get(code, TRANSPORT_FAULTS["TRANSPORT_INTERNAL"])


def classify_status(status: int) -> TransportFault:
    """Map an HTTP-shaped status onto the D-044 split."""
    if not isinstance(status, int) or isinstance(status, bool) or status < 100:
        _fail("status_invalid")
    return _fault(_STATUS_CODES.get(status, "TRANSPORT_INTERNAL"))


def classify_error(error: BaseException) -> TransportFault:
    """Map a raised exception onto the D-044 split.

    `TimeoutError` is treated as AMBIGUOUS on purpose: after an
    exception there is no verdict, so the batch may have been applied.
    `ConnectionError` (never established) is a plain unavailability.
    Auth and validation never become retryable.
    """
    if isinstance(error, (KeyboardInterrupt, SystemExit)):
        raise error
    if isinstance(error, TimeoutError):
        return _fault("TRANSPORT_AMBIGUOUS_TIMEOUT")
    # PermissionError is an OSError subclass: auth is checked FIRST so
    # a credential failure can never be downgraded to "retry later".
    if isinstance(error, PermissionError):
        return _fault("TRANSPORT_AUTH_FAILED")
    if isinstance(error, (ConnectionError, OSError)):
        return _fault("TRANSPORT_UNAVAILABLE")
    if isinstance(error, (TransportContractError, ValueError)):
        return _fault("TRANSPORT_VALIDATION_REFUSED")
    return _fault("TRANSPORT_INTERNAL")


# ---------------------------------------------------------------------------
# Redaction at the edge
# ---------------------------------------------------------------------------

def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return deep_redact(value)
    if isinstance(value, list):
        return [_redact_value(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_redact_value(v) for v in value)
    if isinstance(value, dict):
        return {k: _redact_value(v) for k, v in value.items()}
    return value


def redact_rows(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """D-124 re-assertion on the outbound edge (defense in depth)."""
    _require_rows(rows)
    return [_redact_value(dict(row)) for row in rows]


# ---------------------------------------------------------------------------
# Canonical form, ordering, idempotency
# ---------------------------------------------------------------------------

def _require_rows(rows: Sequence[Any]) -> None:
    if not isinstance(rows, (list, tuple)) or len(rows) == 0:
        _fail("rows_required")
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            _fail(f"row_not_object:{i}")
        if not isinstance(row.get("record_id"), str) or not row["record_id"]:
            _fail(f"row_record_id_required:{i}")
        if not isinstance(row.get("seq"), int) or isinstance(row["seq"], bool):
            _fail(f"row_seq_required:{i}")


def _ordered(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Deterministic total order, independent of caller iteration."""
    return sorted((dict(r) for r in rows), key=lambda r: (r["seq"], r["record_id"]))


def canonical_bytes(payload: Any) -> bytes:
    """Stable JSON encoding: sorted keys, no insignificant whitespace."""
    return json.dumps(payload, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def idempotency_key(rows: Sequence[Dict[str, Any]],
                    namespace: str = "memwal") -> str:
    """Deterministic key over the batch body.

    Same rows ⇒ same key on any host, in any order, in any process.
    A single changed character ⇒ a different key. The namespace keeps
    two surfaces from colliding if they ever share a relayer.
    """
    _require_rows(rows)
    if not isinstance(namespace, str) or not namespace:
        _fail("namespace_required")
    body = {
        "format": ENVELOPE_FORMAT,
        "namespace": namespace,
        "rows": _ordered(rows),
    }
    return hashlib.sha256(canonical_bytes(body)).hexdigest()


# ---------------------------------------------------------------------------
# Bounded chunking
# ---------------------------------------------------------------------------

def chunk_rows(rows: Sequence[Dict[str, Any]],
               max_rows: int = DEFAULT_MAX_ROWS,
               max_bytes: int = DEFAULT_MAX_BYTES) -> List[List[Dict[str, Any]]]:
    """Split deterministically by count AND canonical size.

    Guarantees: every input row appears exactly once, in stable order,
    never split mid-row; no chunk exceeds either ceiling; a single row
    that cannot fit is refused rather than truncated.
    """
    _require_rows(rows)
    for name, value in (("max_rows", max_rows), ("max_bytes", max_bytes)):
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            _fail(f"{name}_invalid")

    ordered = _ordered(rows)
    chunks: List[List[Dict[str, Any]]] = []
    current: List[Dict[str, Any]] = []

    for row in ordered:
        row_bytes = len(canonical_bytes(row))
        if row_bytes > max_bytes:
            _fail(f"row_exceeds_batch_budget:{row['record_id']}")
        candidate = current + [row]
        if (len(candidate) > max_rows
                or len(canonical_bytes(candidate)) > max_bytes):
            chunks.append(current)
            current = [row]
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


# ---------------------------------------------------------------------------
# Envelope
# ---------------------------------------------------------------------------

def build_envelope(rows: Sequence[Dict[str, Any]], *, batch_index: int,
                   batch_count: int) -> Dict[str, Any]:
    """One `memwal.transport.v1` envelope, redacted and keyed."""
    _require_rows(rows)
    for name, value in (("batch_index", batch_index),
                        ("batch_count", batch_count)):
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            _fail(f"{name}_invalid")
    if batch_count < 1 or batch_index >= batch_count:
        _fail("batch_position_invalid")

    safe = redact_rows(rows)
    ordered = _ordered(safe)
    return {
        "format": ENVELOPE_FORMAT,
        "idempotency_key": idempotency_key(ordered),
        "batch_index": batch_index,
        "batch_count": batch_count,
        "row_count": len(ordered),
        "rows": ordered,
    }


def validate_envelope(envelope: Any) -> Dict[str, Any]:
    """Reject anything that is not a well-formed v1 envelope.

    Used by the client before a candidate transport sees it, and by
    tests pinning the wire shape. Returns the envelope for chaining.
    """
    if not isinstance(envelope, dict):
        _fail("envelope_not_object")
    if envelope.get("format") != ENVELOPE_FORMAT:
        _fail("envelope_format_mismatch")
    rows = envelope.get("rows")
    _require_rows(rows)
    expected = idempotency_key(rows)
    if envelope.get("idempotency_key") != expected:
        _fail("envelope_idempotency_key_mismatch")
    if envelope.get("row_count") != len(rows):
        _fail("envelope_row_count_mismatch")
    index, count = envelope.get("batch_index"), envelope.get("batch_count")
    if not isinstance(index, int) or not isinstance(count, int):
        _fail("envelope_batch_position_invalid")
    if count < 1 or index < 0 or index >= count:
        _fail("envelope_batch_position_invalid")
    return envelope


# ---------------------------------------------------------------------------
# Client (never raises; composes with MemWalClientAdapter)
# ---------------------------------------------------------------------------

EnvelopeTransport = Callable[[Dict[str, Any]], Dict[str, Any]]


@dataclass(frozen=True)
class TransportVerdict:
    """What the batch did. `reason` is our own vocabulary — never a
    remote message, which could echo a key or an endpoint."""
    ok: bool
    code: str
    retryable: bool
    requires_reconciliation: bool
    delivered_rows: int
    batches: int
    failed_batch: Optional[int]
    reason: str


def _verdict(fault: TransportFault, *, delivered: int = 0, batches: int = 0,
             failed_batch: Optional[int] = None,
             reason: str = "") -> TransportVerdict:
    return TransportVerdict(
        ok=False, code=fault.code, retryable=fault.retryable,
        requires_reconciliation=fault.requires_reconciliation,
        delivered_rows=delivered, batches=batches,
        failed_batch=failed_batch, reason=reason or fault.code.lower())


class TransportClient:
    """Sends memory batches as v1 envelopes; degrades, never raises.

    The candidate receives ONE envelope per batch and answers a dict
    with a boolean `ok` (optionally `code`). Everything else - a raised
    exception, a non-dict reply, a refusal - becomes a `TransportVerdict`
    so `memwal_adapter.sync` keeps its zero-blockage behaviour.
    """

    def __init__(self, remote: EnvelopeTransport, *,
                 max_rows: int = DEFAULT_MAX_ROWS,
                 max_bytes: int = DEFAULT_MAX_BYTES):
        if remote is not None and not callable(remote):
            _fail("remote_transport_not_callable")
        self._remote = remote
        self._max_rows = max_rows
        self._max_bytes = max_bytes

    def send(self, rows: Sequence[Dict[str, Any]]) -> TransportVerdict:
        """Run one logical batch. Returns a verdict for EVERY outcome."""
        try:
            chunks = chunk_rows(rows, self._max_rows, self._max_bytes)
        except TransportContractError as e:
            return _verdict(_fault("TRANSPORT_VALIDATION_REFUSED"),
                            reason=f"envelope_refused:{e}")

        if self._remote is None:
            # No transport injected is the DESIGNED offline posture, not
            # a failure: report it as such and let the caller keep rows.
            return TransportVerdict(
                ok=False, code="TRANSPORT_UNAVAILABLE", retryable=False,
                requires_reconciliation=False, delivered_rows=0,
                batches=0, failed_batch=None, reason="no_remote_injected")

        delivered = 0
        total = len(chunks)
        for index, chunk in enumerate(chunks):
            try:
                envelope = build_envelope(chunk, batch_index=index,
                                          batch_count=total)
                validate_envelope(envelope)
            except TransportContractError as e:
                return _verdict(_fault("TRANSPORT_VALIDATION_REFUSED"),
                                delivered=delivered, batches=index,
                                failed_batch=index,
                                reason=f"envelope_refused:{e}")

            try:
                reply = self._remote(envelope)
            except (KeyboardInterrupt, SystemExit):
                raise
            except BaseException as error:  # noqa: BLE001 - D-142 edge
                fault = classify_error(error)
                return _verdict(fault, delivered=delivered, batches=index,
                                failed_batch=index,
                                reason=fault.code.lower())

            if not isinstance(reply, dict) or "ok" not in reply:
                return _verdict(_fault("TRANSPORT_MALFORMED_RESPONSE"),
                                delivered=delivered, batches=index,
                                failed_batch=index,
                                reason="reply_not_a_verdict")
            if reply.get("ok") is not True:
                code = reply.get("code")
                fault = (_fault(code) if isinstance(code, str)
                         and code in TRANSPORT_FAULTS
                         else _fault("TRANSPORT_REMOTE_REFUSED"))
                return _verdict(fault, delivered=delivered, batches=index,
                                failed_batch=index,
                                reason=fault.code.lower())
            delivered += len(chunk)

        return TransportVerdict(
            ok=True, code="TRANSPORT_OK", retryable=False,
            requires_reconciliation=False, delivered_rows=delivered,
            batches=total, failed_batch=None, reason="delivered")

    def as_row_transport(self) -> Callable[[List[Dict[str, Any]]], Dict[str, Any]]:
        """Bridge to the existing `RemoteTransport` signature so
        `MemWalClientAdapter(remote=client.as_row_transport())` composes
        without changing either side. Any non-success becomes `ok=False`,
        which the adapter already degrades to `pending_remote`."""
        def _row_transport(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
            verdict = self.send(rows)
            return {
                "ok": verdict.ok,
                "code": verdict.code,
                "delivered": verdict.delivered_rows,
                "batches": verdict.batches,
                "retryable": verdict.retryable,
                "requires_reconciliation": verdict.requires_reconciliation,
            }
        return _row_transport

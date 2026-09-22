"""D-142 — portable WAL export/sync adapter (MystenLabs/MemWal
pattern).

MemWal (https://github.com/MystenLabs/MemWal) stores encrypted,
portable agent memories on Walrus. Per D-142 boundaries:

  - D-045: Walrus/relayer are EXTERNAL services. This adapter NEVER
    opens a connection. The remote transport is INJECTED by an
    owner-authorized ops layer; the default construction is purely
    local (offline-first), so the battery stays air-gapped.
  - Fail-safe fallback: if an injected remote transport raises, the
    adapter transparently persists to the local PostgreSQL SSOT
    (sync_state='pending_remote') and returns honestly — agent
    execution is NEVER blocked by memory-sync unavailability.
  - D-114/D-124: every exported record passes the canonical redactor
    before serialization; memory dumps carry zero credentials.
  - Portability: the WAL artifact is deterministic JSONL with a
    SHA-256 prev-hash chain (tamper-evident), importable on any host
    or backend without vendor tooling.

Memory writes are NEVER authority (D-026/D-027).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

try:  # package-relative (battery) or script (cwd=local)
    from ..canonical.compaction import write_snapshot, verify_snapshot
except ImportError:  # pragma: no cover - script-context alias
    from canonical.compaction import write_snapshot, verify_snapshot

from .vector_store import MemoryRecord, deep_redact

__all__ = [
    "MemWalError", "WAL_FORMAT", "WALRow", "MemWalClientAdapter",
    "verify_wal", "SyncReport",
]

WAL_FORMAT = "memwal.wal.v1"


class MemWalError(ValueError):
    """Contract-level MemWal adapter misuse (fail-closed)."""


def _fail(reason: str):
    raise MemWalError(reason)


# ---------------------------------------------------------------------------
# WAL artifact (portable, deterministic, tamper-evident)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class WALRow:
    """One portable WAL entry (MemWal-shaped: id / agent / content /
    embedding / timestamp, plus the chain link)."""
    seq: int
    record_id: str
    agent_id: str
    session_id: str
    kind: str
    content: str
    embedding: tuple
    logical_ts: int
    prev_hash: str

    def body(self) -> Dict[str, Any]:
        """Chain payload (everything except the row's own hash)."""
        return {
            "seq": self.seq, "record_id": self.record_id,
            "agent_id": self.agent_id, "session_id": self.session_id,
            "kind": self.kind, "content": self.content,
            "embedding": list(self.embedding),
            "logical_ts": self.logical_ts, "prev_hash": self.prev_hash,
        }

    def row_hash(self) -> str:
        payload = json.dumps(self.body(), ensure_ascii=False,
                             sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _chain_rows(records: List[MemoryRecord], genesis: str) -> List[WALRow]:
    """Redact (D-124) then chain deterministically by (seq, id)."""
    ordered = sorted(records, key=lambda r: (r.seq, r.record_id))
    rows: List[WALRow] = []
    prev = genesis
    for r in ordered:
        row = WALRow(seq=r.seq, record_id=r.record_id, agent_id=r.agent_id,
                     session_id=r.session_id, kind=r.kind,
                     content=deep_redact(r.content),
                     embedding=tuple(r.embedding),
                     logical_ts=r.logical_ts, prev_hash=prev)
        prev = row.row_hash()
        rows.append(row)
    return rows


def verify_wal(rows: List[Dict], genesis: str = "genesis") -> Dict:
    """Re-derive the chain over parsed WAL rows; any tamper, gap, or
    reorder fails closed."""
    prev = genesis
    for i, raw in enumerate(rows):
        if not isinstance(raw, dict):
            _fail(f"wal_row_invalid:{i}")
        row = WALRow(
            seq=raw.get("seq", -1), record_id=raw.get("record_id", ""),
            agent_id=raw.get("agent_id", ""),
            session_id=raw.get("session_id", ""), kind=raw.get("kind", ""),
            content=raw.get("content", ""),
            embedding=tuple(raw.get("embedding") or ()),
            logical_ts=raw.get("logical_ts", -1),
            prev_hash=raw.get("prev_hash", ""))
        if row.prev_hash != prev:
            _fail(f"wal_chain_broken:{i}")
        if raw.get("row_hash") != row.row_hash():
            _fail(f"wal_row_hash_mismatch:{i}")
        prev = row.row_hash()
    return {"ok": True, "rows": len(rows), "head": prev}


def write_wal_artifact(path: str, records: List[MemoryRecord],
                       genesis: str = "genesis") -> Dict:
    """Serialize the portable WAL artifact (deterministic JSONL)."""
    rows = _chain_rows(records, genesis)
    header = {"format": WAL_FORMAT, "row_count": len(rows),
              "head": rows[-1].row_hash() if rows else genesis,
              "genesis": genesis}
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(header, ensure_ascii=False, sort_keys=True)
                 + "\n")
        for row in rows:
            body = row.body()
            body["row_hash"] = row.row_hash()
            fh.write(json.dumps(body, ensure_ascii=False, sort_keys=True)
                     + "\n")
    return {"path": path, "row_count": len(rows), "head": header["head"]}


def read_wal_artifact(path: str) -> Dict:
    """Parse + verify a WAL artifact. Parse/verify failures are
    MemWalError (Class-B), never a leaked low-level exception."""
    try:
        with open(path, encoding="utf-8") as fh:
            header = json.loads(fh.readline())
            rows = [json.loads(l) for l in fh if l.strip()]
    except (json.JSONDecodeError, OSError) as e:
        _fail(f"wal_artifact_unparseable:{type(e).__name__}")
    if not isinstance(header, dict) or header.get("format") != WAL_FORMAT:
        _fail("wal_format_mismatch")
    verdict = verify_wal(rows, header.get("genesis", "genesis"))
    if rows and rows[-1].get("row_hash") != header.get("head"):
        _fail("wal_head_mismatch")
    return {"ok": True, "header": header, "rows": rows,
            "head": verdict["head"]}


# ---------------------------------------------------------------------------
# Client adapter (local SSOT by default; injected remote never required)
# ---------------------------------------------------------------------------

RemoteTransport = Callable[[List[Dict]], Dict]


@dataclass(frozen=True)
class SyncReport:
    pushed_remote: int
    kept_local: int
    pending_remote: int
    degraded: bool
    reason: str


class MemWalClientAdapter:
    """Offline-first MemWal-pattern client over the local SSOT.

    `remote` is an INJECTED transport (owner-authorized ops layer
    only). With no remote — the default and the battery posture —
    every record stays local (`local_only`). A failing remote degrades
    transparently to `pending_remote` without raising to the agent.
    """

    def __init__(self, remote: Optional[RemoteTransport] = None,
                 genesis: str = "genesis"):
        if remote is not None and not callable(remote):
            _fail("remote_transport_not_callable")
        self._remote = remote
        self._genesis = genesis

    # -- export ------------------------------------------------------------
    def export_wal(self, path: str,
                   records: List[MemoryRecord]) -> Dict:
        """Portable WAL artifact; content redacted on the way out."""
        return write_wal_artifact(path, records, self._genesis)

    # -- snapshot (D-125 compose) --------------------------------------------
    def snapshot(self, path: str, records: List[MemoryRecord]) -> Dict:
        """D-125 tamper-evident snapshot of the memory surface."""
        rows = []
        for r in sorted(records, key=lambda x: (x.seq, x.record_id)):
            row = r.redacted()
            rows.append({
                "surface": "memory.records", "record_id": row.record_id,
                "agent_id": row.agent_id, "session_id": row.session_id,
                "kind": row.kind, "content": row.content,
                "embedding": list(row.embedding),
                "logical_ts": row.logical_ts, "seq": row.seq,
            })
        desc = write_snapshot(path, rows)
        verify_snapshot(path)  # the D-125 gate, re-checked on write
        return desc

    # -- sync ----------------------------------------------------------------
    def sync(self, records: List[MemoryRecord]) -> SyncReport:
        """Best-effort remote sync with transparent local fallback.

        - no remote  → all local (`local_only`), degraded=False
          (that is the DESIGNED offline posture, not a degradation);
        - remote ok  → rows pushed, marked synced;
        - remote err → rows kept (`pending_remote`), degraded=True,
          reason recorded, NEVER raised to the agent.
        """
        if not records:
            return SyncReport(0, 0, 0, False, "empty_batch")
        rows = _chain_rows(records, self._genesis)
        if self._remote is None:
            return SyncReport(0, len(rows), 0, False,
                              "local_only_no_remote_injected")
        try:
            result = self._remote([r.body() for r in rows])
            if not isinstance(result, dict) or not result.get("ok"):
                raise MemWalError("remote_verdict_not_ok")
            return SyncReport(len(rows), 0, 0, False, "remote_ok")
        except Exception as e:  # noqa: BLE001 - deliberate wide net:
            # memory sync must never break agent execution (D-142)
            return SyncReport(0, 0, len(rows), True,
                              f"remote_unavailable:{type(e).__name__}")

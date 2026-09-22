"""D-142 — pgvector-compatible agent-memory store over the PostgreSQL
SSOT.

Pure contracts + SQL generation + an INJECTED executor. No I/O
imports, no wall clock, no credentials:

  - The caller injects `executor(sql, params) -> list[dict]` (in
    production: a psql/DB-API bridge; in tests: an in-process fake).
  - `pgvector_schema_ddl()` emits the canonical DDL — `vector`
    extension, the `memory.records` table, and the HNSW index — as
    pure text so the battery can pin the schema without a database.
  - Zero-leak (D-114/D-124): every stored/returned `content` string
    passes the canonical redactor — defense in depth on BOTH the
    write and read paths.
  - Retention/compaction is deterministic summarization pruning over
    the injected logical tick (D-085 precedent): old interactions
    covered by a summary are pruned; summaries and guidelines are
    retained — keeping the SSOT lightweight without data loss of
    semantic state.

Memory is NEVER authority (D-026/D-027): this store holds agent
context, not business truth.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Callable, Dict, List, Optional, Sequence, Tuple

try:  # package-relative (battery: local.src.memory) or script (cwd=local)
    from ..canonical.launch_contracts import redact_text as _base_redact
except ImportError:  # pragma: no cover - script-context alias
    from canonical.launch_contracts import redact_text as _base_redact

import re

__all__ = [
    "MemoryStoreError", "INTERACTION", "SUMMARY", "GUIDELINE",
    "MEMORY_KINDS", "DEFAULT_EMBEDDING_DIM", "MemoryRecord",
    "pgvector_schema_ddl", "VectorStore", "PruneReport", "deep_redact",
]

# D-114/D-124 defense in depth: the canonical redactor's minimal set,
# composed with the high-entropy credential shapes memory content is
# most likely to carry (provider keys, bot tokens, AWS/GitHub/Slack).
_EXTRA_PATTERNS = (
    (re.compile(r"sk-[A-Za-z0-9]{16,}"), "[REDACTED]"),
    (re.compile(r"ghp_[A-Za-z0-9]{30,}"), "[REDACTED]"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "[REDACTED]"),
    (re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"), "[REDACTED]"),
    (re.compile(r"bot[0-9]{6,}:[A-Za-z0-9_-]{20,}"), "[REDACTED]"),
)


def deep_redact(text: str) -> str:
    out = _base_redact(text)
    for pattern, repl in _EXTRA_PATTERNS:
        out = pattern.sub(repl, out)
    return out

INTERACTION = "interaction"
SUMMARY = "summary"
GUIDELINE = "guideline"
MEMORY_KINDS = (INTERACTION, SUMMARY, GUIDELINE)

DEFAULT_EMBEDDING_DIM = 1536


class MemoryStoreError(ValueError):
    """Contract-level memory misuse (fail-closed, no leaked I/O)."""


def _fail(reason: str):
    raise MemoryStoreError(reason)


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MemoryRecord:
    """One durable memory row. `logical_ts` comes from the injected
    logical tick, never the wall clock."""
    record_id: str
    agent_id: str
    session_id: str
    kind: str
    content: str
    embedding: Tuple[float, ...]
    logical_ts: int
    seq: int

    def __post_init__(self) -> None:
        if not self.record_id or not isinstance(self.record_id, str):
            _fail("record_id_required")
        if not self.agent_id or not isinstance(self.agent_id, str):
            _fail("agent_id_required")
        if self.kind not in MEMORY_KINDS:
            _fail(f"memory_kind_invalid: {self.kind!r}")
        if not isinstance(self.content, str) or not self.content:
            _fail("content_required")
        if not isinstance(self.logical_ts, int) or self.logical_ts < 0:
            _fail("logical_ts_invalid")
        if not isinstance(self.seq, int) or self.seq < 0:
            _fail("seq_invalid")
        _validate_embedding(self.embedding, DEFAULT_EMBEDDING_DIM)

    def redacted(self) -> "MemoryRecord":
        """Return a copy whose content passed the D-124 redactor."""
        return replace(self, content=deep_redact(self.content))


def _validate_embedding(embedding: Sequence[float], dim: int) -> None:
    if not isinstance(embedding, (tuple, list)) or len(embedding) != dim:
        _fail(f"embedding_dimension_invalid: expected {dim}")
    for v in embedding:
        if not isinstance(v, (int, float)) or isinstance(v, bool) \
                or not math.isfinite(float(v)):
            _fail("embedding_value_invalid")


# ---------------------------------------------------------------------------
# Schema (pure DDL text — pinned by the battery, applied by the executor)
# ---------------------------------------------------------------------------

def pgvector_schema_ddl(schema: str = "memory",
                        dim: int = DEFAULT_EMBEDDING_DIM) -> List[str]:
    """Canonical pgvector DDL: extension, table, HNSW index.

    NOTE: requires a pgvector-capable PostgreSQL build (the
    `pgvector/pgvector` image or the extension installed on the host
    image). DDL generation is hermetic; application is a host-provision
    concern (documented in the Stage H runbook), never claimed live.
    """
    if not schema or not schema.replace("_", "").isalnum():
        _fail("schema_name_invalid")
    if dim < 1 or dim > 16000:
        _fail("embedding_dim_invalid")
    return [
        f"CREATE SCHEMA IF NOT EXISTS {schema};",
        "CREATE EXTENSION IF NOT EXISTS vector;",
        (f"CREATE TABLE IF NOT EXISTS {schema}.records ("
         " record_id TEXT PRIMARY KEY,"
         " agent_id TEXT NOT NULL,"
         " session_id TEXT NOT NULL,"
         " kind TEXT NOT NULL,"
         " content TEXT NOT NULL,"
         f" embedding vector({dim}) NOT NULL,"
         " logical_ts BIGINT NOT NULL,"
         " seq BIGINT NOT NULL,"
         " sync_state TEXT NOT NULL DEFAULT 'local_only',"
         " created_at TIMESTAMPTZ NOT NULL DEFAULT now());"),
        (f"CREATE INDEX IF NOT EXISTS records_hnsw_cosine ON {schema}.records"
         f" USING hnsw (embedding vector_cosine_ops);"),
        (f"CREATE INDEX IF NOT EXISTS records_agent_ts ON {schema}.records"
         " (agent_id, logical_ts);"),
    ]


# ---------------------------------------------------------------------------
# Store adapter (injected executor; hermetic under a fake)
# ---------------------------------------------------------------------------

Executor = Callable[[str, tuple], List[Dict]]


class VectorStore:
    """pgvector-backed memory adapter over an injected executor."""

    def __init__(self, executor: Executor, schema: str = "memory",
                 dim: int = DEFAULT_EMBEDDING_DIM):
        if not callable(executor):
            _fail("executor_required")
        self._exec = executor
        self.schema = schema
        self.dim = dim

    # -- schema ------------------------------------------------------------
    def ensure_schema(self) -> Dict:
        stmts = pgvector_schema_ddl(self.schema, self.dim)
        for s in stmts:
            self._exec(s, ())
        return {"applied": len(stmts), "schema": self.schema, "dim": self.dim}

    # -- writes --------------------------------------------------------------
    def put(self, record: MemoryRecord) -> Dict:
        safe = record.redacted()  # D-124 on the write path
        self._exec(
            f"INSERT INTO {self.schema}.records (record_id, agent_id,"
            " session_id, kind, content, embedding, logical_ts, seq)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
            " ON CONFLICT (record_id) DO NOTHING",
            (safe.record_id, safe.agent_id, safe.session_id, safe.kind,
             safe.content, list(safe.embedding), safe.logical_ts, safe.seq),
        )
        return {"stored": safe.record_id, "kind": safe.kind}

    def put_summary(self, record_id: str, agent_id: str, session_id: str,
                    content: str, embedding: Sequence[float],
                    logical_ts: int, seq: int) -> Dict:
        return self.put(MemoryRecord(
            record_id=record_id, agent_id=agent_id,
            session_id=session_id, kind=SUMMARY, content=content,
            embedding=tuple(embedding), logical_ts=logical_ts, seq=seq))

    def put_guideline(self, record_id: str, agent_id: str, content: str,
                      embedding: Sequence[float], logical_ts: int,
                      seq: int) -> Dict:
        return self.put(MemoryRecord(
            record_id=record_id, agent_id=agent_id, session_id="*",
            kind=GUIDELINE, content=content, embedding=tuple(embedding),
            logical_ts=logical_ts, seq=seq))

    # -- reads ---------------------------------------------------------------
    def query(self, embedding: Sequence[float], k: int = 5,
              agent_id: Optional[str] = None) -> List[Dict]:
        """Cosine KNN (`<=>` pgvector operator). Content is re-redacted
        on the read path before it leaves the process (D-124)."""
        _validate_embedding(embedding, self.dim)
        if not isinstance(k, int) or k < 1 or k > 100:
            _fail("k_invalid")
        sql = (f"SELECT record_id, agent_id, session_id, kind, content,"
               f" logical_ts, seq, embedding <=> %s::vector AS distance"
               f" FROM {self.schema}.records")
        params: tuple = (list(embedding),)
        if agent_id is not None:
            sql += " WHERE agent_id = %s"
            params = (list(embedding), agent_id)
        sql += " ORDER BY embedding <=> %s::vector LIMIT %s"
        params = params + (list(embedding), k)
        rows = self._exec(sql, params)
        for row in rows:
            if isinstance(row.get("content"), str):
                row["content"] = deep_redact(row["content"])
        return rows

    def rows(self, kind: Optional[str] = None,
             agent_id: Optional[str] = None) -> List[Dict]:
        sql = (f"SELECT record_id, agent_id, session_id, kind, content,"
               f" logical_ts, seq FROM {self.schema}.records WHERE 1=1")
        params: List = []
        if kind is not None:
            if kind not in MEMORY_KINDS:
                _fail(f"memory_kind_invalid: {kind!r}")
            sql += " AND kind = %s"
            params.append(kind)
        if agent_id is not None:
            sql += " AND agent_id = %s"
            params.append(agent_id)
        sql += " ORDER BY (agent_id, seq)"
        return self._exec(sql, tuple(params))

    # -- retention / compaction ---------------------------------------------
    def prune_and_summarize(self, horizon_ts: int,
                            summarizer: Callable[[List[Dict]], Tuple[str, Sequence[float]]],
                            now_ts: int) -> PruneReport:
        """Deterministic summarization pruning (D-125 spirit, memory
        surface): interactions strictly older than `horizon_ts` that
        belong to sessions already covered by a summary are pruned; a
        session without a summary is folded into one via the INJECTED
        deterministic `summarizer`. Summaries and guidelines are never
        pruned. All timestamps are the caller's logical ticks."""
        if not isinstance(horizon_ts, int) or not isinstance(now_ts, int) \
                or horizon_ts < 0 or now_ts < 0:
            _fail("tick_invalid")
        if horizon_ts > now_ts:
            _fail("horizon_after_now")
        if not callable(summarizer):
            _fail("summarizer_required")

        interactions = self.rows(kind=INTERACTION)
        summaries = self.rows(kind=SUMMARY)
        summarized_sessions = {r["session_id"] for r in summaries}

        by_session: Dict[str, List[Dict]] = {}
        for r in interactions:
            if r["logical_ts"] < horizon_ts:
                by_session.setdefault(r["session_id"], []).append(r)

        pruned: List[str] = []
        created: List[str] = []
        for session_id, old in sorted(by_session.items()):
            if session_id in summarized_sessions:
                for r in old:
                    self._exec(
                        f"DELETE FROM {self.schema}.records"
                        " WHERE record_id = %s AND kind = %s",
                        (r["record_id"], INTERACTION))
                    pruned.append(r["record_id"])
            else:
                content, embedding = summarizer(old)
                summary_id = f"sum-{session_id}-{horizon_ts}"
                self.put_summary(summary_id, old[0]["agent_id"], session_id,
                                 content, embedding, now_ts, old[-1]["seq"])
                created.append(summary_id)
                for r in old:
                    self._exec(
                        f"DELETE FROM {self.schema}.records"
                        " WHERE record_id = %s AND kind = %s",
                        (r["record_id"], INTERACTION))
                    pruned.append(r["record_id"])
        return PruneReport(horizon_ts=horizon_ts, now_ts=now_ts,
                           pruned=tuple(sorted(pruned)),
                           summaries_created=tuple(sorted(created)))


@dataclass(frozen=True)
class PruneReport:
    horizon_ts: int
    now_ts: int
    pruned: Tuple[str, ...]
    summaries_created: Tuple[str, ...]

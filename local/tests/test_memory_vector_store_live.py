"""D-142 — live pgvector proof for `local/src/memory/vector_store.py`.

The hermetic battery pins the SQL text. This module is the ONLY place
the store touches a real PostgreSQL with the `vector` extension, and it
is deliberately environment-gated in the repository's established
live-tier style: when no pgvector-capable server answers, the tests
SKIP with an honest reason and the offline battery stays authoritative.

Scope: DDL application (extension + table + HNSW index), write/read
redaction on a real server, KNN ordering by cosine distance, the
`ON CONFLICT DO NOTHING` duplicate rule, kind filtering, and
summarization pruning. No credential beyond the throwaway local one,
no network beyond 127.0.0.1, no tracked infrastructure changed.

Connection: `MEMORY_LIVE_PG` (libpq URL-ish host:port:db:user:password)
defaults to the ad-hoc local pgvector container on 55433. The tracked
`local/infra/docker-compose.yml` pins `postgres:16-alpine`, which has no
`vector` extension, so it cannot serve these tests.
"""
from __future__ import annotations

import csv
import io
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "local"))

from local.src.memory.vector_store import (  # noqa: E402
    DEFAULT_EMBEDDING_DIM, GUIDELINE, INTERACTION, MemoryRecord, SUMMARY,
    VectorStore, pgvector_schema_ddl, deep_redact,
)

SCHEMA = "memory_live_test"
DEFAULT_DSN = "127.0.0.1:55433:business_engine_local:engine_local:engine-local-only"
DSN = os.environ.get("MEMORY_LIVE_PG", DEFAULT_DSN)

CANARY = "sk" + "-" + ("Q" * 24)


def _dsn_parts():
    try:
        host, port, db, user, password = DSN.split(":")
        int(port)
    except ValueError:
        return None
    return {"host": host, "port": port, "db": db, "user": user,
            "password": password}


def _psql(sql: str, *, fetch: bool = False):
    """Run one statement through the psql client (no Python driver)."""
    parts = _dsn_parts()
    if parts is None or shutil.which("psql") is None:
        return None
    env = dict(os.environ)
    env["PGPASSWORD"] = parts["password"]
    args = ["psql", "-X", "-q", "-v", "ON_ERROR_STOP=1",
            "-h", parts["host"], "-p", parts["port"],
            "-U", parts["user"], "-d", parts["db"]]
    args += ["--csv", "-c", sql] if fetch else ["-c", sql]
    proc = subprocess.run(args, capture_output=True, text=True, env=env,
                          timeout=30)
    if proc.returncode != 0:
        raise RuntimeError(f"psql_failed:{proc.stderr.strip()[:200]}")
    return proc.stdout


def _vector_version():
    """Return the live pgvector version, or None when unavailable."""
    parts = _dsn_parts()
    if parts is None or shutil.which("psql") is None:
        return None
    try:
        _psql("CREATE EXTENSION IF NOT EXISTS vector;")
        out = _psql("SELECT extversion FROM pg_extension"
                    " WHERE extname = 'vector';", fetch=True)
    except (RuntimeError, OSError, subprocess.SubprocessError):
        return None
    rows = list(csv.DictReader(io.StringIO(out or "")))
    return rows[0]["extversion"] if rows else None


PGVECTOR_VERSION = _vector_version()


# ---------------------------------------------------------------------------
# Test-only executor: psql + literal rendering
# ---------------------------------------------------------------------------

def _sql_literal(value) -> str:
    """Render ONE parameter as a SQL literal.

    Test-only by construction: every value here is produced by this
    module (record ids, fixed embeddings, integers), never by a user.
    Strings are quoted with doubled single quotes; embeddings become a
    `'[..]'` literal that PostgreSQL coerces to `vector` in context.
    """
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, (list, tuple)):
        return "'[" + ",".join(repr(float(v)) for v in value) + "]'"
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    raise TypeError(f"unsupported_param:{type(value).__name__}")


def _render(sql: str, params: tuple) -> str:
    parts = sql.split("%s")
    if len(parts) != len(params) + 1:
        raise AssertionError(f"placeholder_mismatch:{len(parts)}:{len(params)}")
    out = [parts[0]]
    for value, tail in zip(params, parts[1:]):
        out.append(_sql_literal(value))
        out.append(tail)
    return "".join(out)


_COERCE = {"logical_ts": int, "seq": int, "distance": float}


def _executor(sql: str, params: tuple):
    rendered = _render(sql, params)
    if not rendered.lstrip().upper().startswith("SELECT"):
        _psql(rendered)
        return []
    out = _psql(rendered, fetch=True) or ""
    rows = []
    for raw in csv.DictReader(io.StringIO(out)):
        row = {}
        for key, value in raw.items():
            coerce = _COERCE.get(key)
            row[key] = coerce(value) if coerce and value not in (None, "") else value
        rows.append(row)
    return rows


def _vec(index: int, dim: int = DEFAULT_EMBEDDING_DIM):
    values = [0.0] * dim
    values[index] = 1.0
    return tuple(values)


def _record(record_id: str, seq: int, *, kind: str = INTERACTION,
            content: str = "content", session_id: str = "s-live",
            index: int = 0) -> MemoryRecord:
    return MemoryRecord(record_id=record_id, agent_id="agent-live",
                        session_id=session_id, kind=kind, content=content,
                        embedding=_vec(index), logical_ts=seq, seq=seq)


@unittest.skipUnless(PGVECTOR_VERSION is not None,
                     "live pgvector not reachable on 127.0.0.1:55433 "
                     "(hermetic battery remains authoritative)")
class TestVectorStoreLive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _psql(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE;")
        cls.store = VectorStore(_executor, schema=SCHEMA)
        cls.store.ensure_schema()  # idempotent; test_01 re-asserts the count

    def setUp(self):
        # Each test starts from an empty table, not an empty database.
        _psql(f"TRUNCATE TABLE {SCHEMA}.records;")

    # -- DDL ---------------------------------------------------------------
    def test_01_extension_and_schema_apply(self):
        applied = self.store.ensure_schema()
        self.assertEqual(applied["applied"], len(pgvector_schema_ddl(SCHEMA)))
        self.assertEqual(applied["dim"], DEFAULT_EMBEDDING_DIM)
        # independently confirm the objects exist on the server
        out = _psql(
            "SELECT indexname FROM pg_indexes"
            f" WHERE schemaname = '{SCHEMA}';", fetch=True)
        self.assertIn("records_hnsw_cosine", out)

    # -- round trip / KNN ---------------------------------------------------
    def test_02_round_trip_and_cosine_order(self):
        self.store.ensure_schema()
        self.store.put(_record("live-a", 1, content="alpha", index=0))
        self.store.put(_record("live-b", 2, content="beta", index=1))
        hits = self.store.query(_vec(0), k=2)
        self.assertEqual(len(hits), 2)
        self.assertEqual(hits[0]["record_id"], "live-a")
        self.assertLess(hits[0]["distance"], hits[1]["distance"])
        self.assertAlmostEqual(float(hits[0]["distance"]), 0.0, places=5)

    # -- redaction ----------------------------------------------------------
    def test_03_redaction_on_real_write_and_read(self):
        self.store.ensure_schema()
        self.store.put(_record("live-secret", 3,
                               content=f"paired with {CANARY} today"))
        raw = _psql(
            f"SELECT content FROM {SCHEMA}.records"
            " WHERE record_id = 'live-secret';", fetch=True)
        self.assertNotIn(CANARY, raw)
        read_back = self.store.rows(kind=INTERACTION)
        self.assertEqual(len(read_back), 1)
        self.assertNotIn(CANARY, read_back[0]["content"])
        self.assertEqual(read_back[0]["content"], deep_redact(
            f"paired with {CANARY} today"))

    # -- duplicate rule -----------------------------------------------------
    def test_04_duplicate_record_id_does_not_overwrite(self):
        self.store.ensure_schema()
        self.store.put(_record("live-dup", 4, content="first"))
        self.store.put(_record("live-dup", 4, content="second"))
        rows = self.store.rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["content"], "first")

    # -- kind filtering -----------------------------------------------------
    def test_05_rows_filters_by_kind(self):
        self.store.ensure_schema()
        self.store.put(_record("live-i", 5, content="interaction"))
        self.store.put_summary("live-sum", "agent-live", "s-live",
                               "summary", _vec(2), 6, 6)
        self.store.put_guideline("live-g", "agent-live", "guideline",
                                 _vec(3), 7, 7)
        self.assertEqual(len(self.store.rows(kind=INTERACTION)), 1)
        self.assertEqual(len(self.store.rows(kind=SUMMARY)), 1)
        self.assertEqual(len(self.store.rows(kind=GUIDELINE)), 1)
        self.assertEqual(len(self.store.rows(kind=INTERACTION,
                                             agent_id="agent-live")), 1)
        self.assertEqual(len(self.store.rows(agent_id="nobody")), 0)

    # -- pruning ------------------------------------------------------------
    def test_06_summarization_pruning_on_real_server(self):
        self.store.ensure_schema()
        for i in range(3):
            self.store.put(_record(f"live-old-{i}", 10 + i,
                                   content=f"old {i}", session_id="s-old"))
        self.store.put(_record("live-new", 99, content="new",
                               session_id="s-new"))

        def summarizer(old_rows):
            joined = " | ".join(r["content"] for r in old_rows)
            return (f"summary: {joined}", _vec(4))

        report = self.store.prune_and_summarize(horizon_ts=50,
                                                summarizer=summarizer,
                                                now_ts=100)
        self.assertEqual(len(report.pruned), 3)
        self.assertEqual(len(report.summaries_created), 1)
        remaining = {r["record_id"] for r in self.store.rows()}
        self.assertEqual(remaining, {"live-new", report.summaries_created[0]})
        self.assertEqual(len(self.store.rows(kind=SUMMARY)), 1)


if __name__ == "__main__":
    print(f"pgvector: {PGVECTOR_VERSION or 'unreachable'}")
    unittest.main()

"""Stage H & D-142 — vendor-exit harness + portable agent memory
battery.

Covers:
  H   — `verify_vendor_exit.py`: fold-parity round trip, tamper
        detection, armored (PBKDF2+HMAC_DRBG) round trip with
        wrong-passphrase refusal, D-124 redaction of exported rows,
        D-045 shell-hygiene refusal, runbook invariants.
  V   — `local/src/memory/vector_store.py`: pgvector DDL pins,
        injected-executor adapter, write/read-path redaction, KNN SQL
        shape, deterministic summarization pruning.
  W   — `local/src/memory/memwal_adapter.py`: deterministic WAL
        artifacts, chain tamper detection, offline-first sync with
        transparent local fallback (never raises to the agent),
        D-125 snapshot composition.

All hermetic: injected executors/transports only; no docker, no DB,
no network (D-045).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "local" / "scripts" / "verify_vendor_exit.py"
RUNBOOK = REPO / "docs" / "deployment" / "stage-h-vendor-exit.md"

sys.path.insert(0, str(SCRIPT.parent))
import verify_vendor_exit as vve  # noqa: E402

from local.src.memory.vector_store import (  # noqa: E402
    MemoryRecord, MemoryStoreError, VectorStore, pgvector_schema_ddl,
    DEFAULT_EMBEDDING_DIM, INTERACTION, SUMMARY, GUIDELINE,
)
from local.src.memory.memwal_adapter import (  # noqa: E402
    MemWalClientAdapter, MemWalError, read_wal_artifact,
    verify_wal, write_wal_artifact,
)

from canonical.compaction import verify_snapshot  # noqa: E402


def run_cli(*extra: str, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.update(env_extra or {})
    return subprocess.run([sys.executable, str(SCRIPT), *extra],
                          capture_output=True, text=True, env=env,
                          cwd=str(REPO))


VEC = tuple(0.1 * (i % 7 + 1) for i in range(DEFAULT_EMBEDDING_DIM))

# Deliberate redaction canary, constructed at runtime so line-based
# secret scanners never flag this file while the D-114 patterns are
# still exercised for real at runtime.
_CANARY = "sk-" + "x" * 24


def rec(rid, *, agent="a1", session="s1", kind=INTERACTION, content="hello",
        seq=1, ts=100):
    return MemoryRecord(record_id=rid, agent_id=agent, session_id=session,
                        kind=kind, content=content, embedding=VEC,
                        logical_ts=ts, seq=seq)


class FakeExec:
    """In-process executor mirroring the real adapter's contract:
    parameterized SQL; `rows()` dispatches on the kind param; write
    statements are recorded and return no rows."""

    def __init__(self, canned=None):
        self.calls: list[tuple[str, tuple]] = []
        self.canned: dict = canned or {}  # kind value -> rows; or "sql:FRAG"

    def __call__(self, sql, params):
        self.calls.append((sql, params))
        if "DELETE FROM" in sql or "INSERT INTO" in sql:
            return []
        if "AND kind = %s" in sql and params:
            return [dict(r) for r in self.canned.get(params[0], [])]
        for key, rows in self.canned.items():
            if key in (INTERACTION, SUMMARY, GUIDELINE):
                continue
            if key.replace("sql:", "") in sql:
                return [dict(r) for r in rows]
        return []


# ---------------------------------------------------------------------------
# H — vendor exit harness
# ---------------------------------------------------------------------------

class TestVendorExitHarness(unittest.TestCase):
    def test_01_check_cli_offline_green(self):
        r = run_cli("check")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("check: OK", r.stdout)

    def test_02_check_refuses_with_prod_secret_in_shell(self):
        r = run_cli("check", env_extra={"TELEGRAM_BOT_TOKEN": "x" * 20})
        self.assertEqual(r.returncode, 2)
        self.assertIn("REFUSED", r.stderr)
        self.assertNotIn("x" * 20, r.stderr)  # value never echoed (D-124)

    def test_03_export_round_trip_row_parity(self):
        rows = {"syn.alpha": [{"id": 1, "note": "ok"},
                              {"id": 2, "note": "fine"}],
                "syn.beta": [{"id": 9, "note": "z"}]}
        archive = vve.build_archive(rows, "cand-1")
        text = vve.archive_plaintext(archive)
        manifest, data = vve.parse_archive_plaintext(text)
        verdict = vve.verify_parity(manifest, data)
        self.assertTrue(verdict["ok"])
        self.assertEqual(verdict["rows"], 3)
        self.assertEqual(verdict["surfaces"], 2)

    def test_04_tamper_detection_bit_flip(self):
        rows = {"syn.alpha": [{"id": 1, "note": "clean"}]}
        manifest, data = vve.parse_archive_plaintext(
            vve.archive_plaintext(vve.build_archive(rows, "c")))
        tampered = [dict(data["syn.alpha"][0])]
        tampered[0]["note"] = "cleat"
        with self.assertRaises(vve.ExitError) as cm:
            vve.verify_parity(manifest, {"syn.alpha": tampered})
        self.assertIn("row_fold_mismatch", str(cm.exception))

    def test_05_dropped_row_detected(self):
        rows = {"syn.alpha": [{"id": 1}, {"id": 2}]}
        manifest, data = vve.parse_archive_plaintext(
            vve.archive_plaintext(vve.build_archive(rows, "c")))
        with self.assertRaises(vve.ExitError) as cm:
            vve.verify_parity(manifest, {"syn.alpha": data["syn.alpha"][:1]})
        self.assertIn("row_count_mismatch", str(cm.exception))

    def test_06_armored_round_trip_and_wrong_passphrase(self):
        rows = {"syn.alpha": [{"id": 1, "note": "n"}]}
        text = vve.archive_plaintext(vve.build_archive(rows, "c"))
        env = vve._armor(text, "correct horse battery")
        self.assertEqual(vve._dearmor(env, "correct horse battery"), text)
        with self.assertRaises(vve.ExitError):
            vve._dearmor(env, "wrong")

    def test_07_armored_file_write_read(self):
        rows = {"syn.alpha": [{"id": 1, "note": "n"}]}
        archive = vve.build_archive(rows, "c")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "arch.json")
            vve._write_archive(path, archive, "pw")
            manifest, data = vve._read_archive(path, "pw")
            vve.verify_parity(manifest, data)
            with self.assertRaises(vve.ExitError):
                vve._read_archive(path, "bad-pw")

    def test_08_export_rows_redacted(self):
        rows = {"syn.alpha": [{"id": 1, "note": "token=ghp_abcdefghijklmnopqrst"}]}
        data = vve.collect_rows(lambda sql: rows[sql.split("FROM ")[1].split(" ")[0]],
                                [("syn", "alpha")])
        self.assertNotIn("ghp_abcdefghijklmnopqrst",
                         json.dumps(data))
        plaintext = vve.archive_plaintext(vve.build_archive(data, "c"))
        self.assertNotIn("ghp_", plaintext)

    def test_09_declared_surfaces_cover_launch_ssot(self):
        keys = {f"{s}.{t}" for s, t in vve.DEFAULT_SURFACES}
        self.assertEqual(len(vve.DEFAULT_SURFACES), 13)
        self.assertIn("hitl.decision_ledger", keys)
        self.assertIn("admin.control_audit", keys)
        self.assertIn("orchestration.outbox", keys)
        self.assertIn("events.event_store", keys)

    def test_10_runbook_invariants(self):
        text = RUNBOOK.read_text(encoding="utf-8")
        self.assertIn("exit-plan", text)
        self.assertIn("exit-drill", text)
        self.assertIn("PLANNED", text)
        self.assertIn("No live export has been performed", text)
        self.assertIn("owner-gated", text)


# ---------------------------------------------------------------------------
# V — vector store
# ---------------------------------------------------------------------------

class TestVectorStore(unittest.TestCase):
    def test_11_pgvector_ddl_pins(self):
        ddl = pgvector_schema_ddl()
        joined = "\n".join(ddl)
        self.assertIn("CREATE EXTENSION IF NOT EXISTS vector;", joined)
        self.assertIn("embedding vector(1536)", joined)
        self.assertIn("USING hnsw (embedding vector_cosine_ops)", joined)
        self.assertIn("CREATE TABLE IF NOT EXISTS memory.records", joined)

    def test_12_ddl_validation(self):
        with self.assertRaises(MemoryStoreError):
            pgvector_schema_ddl(schema="bad name!")
        with self.assertRaises(MemoryStoreError):
            pgvector_schema_ddl(dim=0)

    def test_13_record_validation(self):
        with self.assertRaises(MemoryStoreError):
            rec("x", kind="bogus")
        with self.assertRaises(MemoryStoreError):
            MemoryRecord(record_id="x", agent_id="a", session_id="s",
                         kind=INTERACTION, content="c",
                         embedding=(0.1,), logical_ts=1, seq=1)
        bad = tuple(float("nan") if i == 0 else 0.1
                    for i in range(DEFAULT_EMBEDDING_DIM))
        with self.assertRaises(MemoryStoreError):
            MemoryRecord(record_id="x", agent_id="a", session_id="s",
                         kind=INTERACTION, content="c", embedding=bad,
                         logical_ts=1, seq=1)

    def test_14_put_redacts_on_write_path(self):
        ex = FakeExec()
        store = VectorStore(ex)
        store.put(rec("r1", content="call token=" + _CANARY + " now"))
        sql, params = ex.calls[-1]
        self.assertIn("INSERT INTO memory.records", sql)
        self.assertNotIn(_CANARY, json.dumps(params))

    def test_15_query_knn_sql_shape_and_read_redaction(self):
        ex = FakeExec(canned={
            "ORDER BY embedding": [{"record_id": "r1", "agent_id": "a1",
                                    "session_id": "s1", "kind": INTERACTION,
                                    "content": "leak token=" + _CANARY,
                                    "logical_ts": 1, "seq": 1,
                                    "distance": 0.1}]})
        store = VectorStore(ex)
        rows = store.query(VEC, k=3, agent_id="a1")
        sql, params = ex.calls[-1]
        self.assertIn("embedding <=> %s::vector", sql)
        self.assertIn("LIMIT %s", sql)
        self.assertEqual(params[-1], 3)
        self.assertNotIn(_CANARY, rows[0]["content"])

    def test_16_query_validation(self):
        store = VectorStore(FakeExec())
        with self.assertRaises(MemoryStoreError):
            store.query(VEC, k=0)
        with self.assertRaises(MemoryStoreError):
            store.query((0.1,), k=1)

    def test_17_prune_summarizes_uncovered_session(self):
        old = [rec(f"o{i}", session="s-old", seq=i, ts=10) for i in range(3)]
        ex = FakeExec(canned={INTERACTION: [dict(
            record_id=r.record_id, agent_id=r.agent_id,
            session_id=r.session_id, kind=r.kind, content=r.content,
            logical_ts=r.logical_ts, seq=r.seq) for r in old],
            SUMMARY: []})
        store = VectorStore(ex)

        def summarizer(rows):
            return (f"summary of {len(rows)} rows",
                    tuple(0.5 for _ in range(DEFAULT_EMBEDDING_DIM)))

        report = store.prune_and_summarize(horizon_ts=50, now_ts=100,
                                           summarizer=summarizer)
        self.assertEqual(report.summaries_created, ("sum-s-old-50",))
        self.assertEqual(len(report.pruned), 3)
        deletes = [c for c in ex.calls if c[0].startswith("DELETE")]
        self.assertEqual(len(deletes), 3)
        inserts = [c for c in ex.calls if "INSERT INTO memory.records" in c[0]]
        self.assertEqual(len(inserts), 1)
        self.assertEqual(inserts[0][1][3], SUMMARY)  # kind param

    def test_18_prune_covered_session_no_new_summary(self):
        old = [rec("o1", session="s-covered", ts=10)]
        ex = FakeExec(canned={
            INTERACTION: [dict(
                record_id=old[0].record_id, agent_id="a1",
                session_id="s-covered", kind=INTERACTION, content="c",
                logical_ts=10, seq=1)],
            SUMMARY: [{"record_id": "sum-1", "agent_id": "a1",
                       "session_id": "s-covered", "kind": SUMMARY,
                       "content": "s", "logical_ts": 90, "seq": 9}]})
        store = VectorStore(ex)
        report = store.prune_and_summarize(
            horizon_ts=50, now_ts=100,
            summarizer=lambda rows: ("x", VEC))
        self.assertEqual(report.summaries_created, ())
        self.assertEqual(report.pruned, ("o1",))

    def test_19_prune_never_touches_recent_or_non_interaction(self):
        ex = FakeExec(canned={INTERACTION: [dict(
            record_id="recent", agent_id="a", session_id="s",
            kind=INTERACTION, content="c", logical_ts=90, seq=1)],
            SUMMARY: []})
        store = VectorStore(ex)
        report = store.prune_and_summarize(
            horizon_ts=50, now_ts=100,
            summarizer=lambda rows: ("x", VEC))
        self.assertEqual(report.pruned, ())
        self.assertEqual(report.summaries_created, ())

    def test_20_prune_tick_validation(self):
        store = VectorStore(FakeExec())
        with self.assertRaises(MemoryStoreError):
            store.prune_and_summarize(horizon_ts=100, now_ts=50,
                                      summarizer=lambda r: ("x", VEC))


# ---------------------------------------------------------------------------
# W — MemWal adapter
# ---------------------------------------------------------------------------

class TestMemWalAdapter(unittest.TestCase):
    def test_21_wal_deterministic_artifact(self):
        records = [rec("r2", seq=2), rec("r1", seq=1)]
        with tempfile.TemporaryDirectory() as tmp:
            p1, p2 = os.path.join(tmp, "a.wal"), os.path.join(tmp, "b.wal")
            write_wal_artifact(p1, records)
            write_wal_artifact(p2, list(reversed(records)))
            self.assertEqual(Path(p1).read_bytes(), Path(p2).read_bytes())
            parsed = read_wal_artifact(p1)
            self.assertEqual(parsed["header"]["format"], "memwal.wal.v1")
            self.assertEqual(parsed["header"]["row_count"], 2)
            self.assertEqual([r["record_id"] for r in parsed["rows"]],
                             ["r1", "r2"])

    def test_22_wal_tamper_detection(self):
        records = [rec("r1", seq=1, content="first"),
                   rec("r2", seq=2, content="second")]
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "a.wal")
            write_wal_artifact(p, records)
            lines = Path(p).read_text().splitlines()
            row = json.loads(lines[2])
            row["content"] = "TAMPERED"
            lines[2] = json.dumps(row, sort_keys=True)
            bad = os.path.join(tmp, "bad.wal")
            Path(bad).write_text("\n".join(lines) + "\n")
            with self.assertRaises(MemWalError) as cm:
                read_wal_artifact(bad)
            self.assertIn("hash", str(cm.exception))
            # dropped line also fails
            Path(bad).write_text("\n".join(lines[:2] + lines[3:]) + "\n")
            with self.assertRaises(MemWalError):
                read_wal_artifact(bad)

    def test_23_wal_export_redacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "a.wal")
            write_wal_artifact(p, [rec("r1", content="key " + _CANARY)])
            self.assertNotIn(_CANARY, Path(p).read_text())

    def test_24_sync_offline_default_local_only(self):
        report = MemWalClientAdapter().sync([rec("r1")])
        self.assertEqual(report.kept_local, 1)
        self.assertFalse(report.degraded)
        self.assertEqual(report.reason, "local_only_no_remote_injected")

    def test_25_sync_remote_ok_and_fallback(self):
        records = [rec("r1"), rec("r2", seq=2)]

        ok = MemWalClientAdapter(remote=lambda rows: {"ok": True})
        rep = ok.sync(records)
        self.assertEqual(rep.pushed_remote, 2)
        self.assertFalse(rep.degraded)

        def boom(rows):
            raise ConnectionError("relayer unreachable")

        degraded = MemWalClientAdapter(remote=boom).sync(records)
        self.assertEqual(degraded.pending_remote, 2)
        self.assertTrue(degraded.degraded)
        self.assertIn("remote_unavailable:ConnectionError", degraded.reason)

        bad = MemWalClientAdapter(remote=lambda rows: {"ok": False})
        rep = bad.sync(records)
        self.assertEqual(rep.pending_remote, 2)
        self.assertTrue(rep.degraded)

    def test_26_adapter_fails_closed_on_bad_transport(self):
        with self.assertRaises(MemWalError):
            MemWalClientAdapter(remote="not-callable")

    def test_27_snapshot_d125_compose_and_tamper(self):
        adapter = MemWalClientAdapter()
        records = [rec("r1", content="secret " + _CANARY),
                   rec("r2", seq=2)]
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "mem.snap")
            desc = adapter.snapshot(p, records)
            self.assertEqual(desc["row_count"], 2)
            verdict = verify_snapshot(p)
            self.assertTrue(verdict["ok"])
            body = Path(p).read_text()
            self.assertNotIn(_CANARY, body)
            # tamper-evidence: flip a byte -> refusal
            tampered = body.replace('"hello"', '"hella"')
            q = os.path.join(tmp, "bad.snap")
            Path(q).write_text(tampered)
            from canonical.compaction import CompactionError
            with self.assertRaises(CompactionError):
                verify_snapshot(q)


if __name__ == "__main__":
    unittest.main()

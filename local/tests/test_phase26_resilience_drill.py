"""Phase 26 resilience drill — catastrophic recovery (BAC-001, D-125).

The REAL drill behind the launch-gate backup/recovery control: a
run-scoped flow is seeded through the real D-027 API, snapshotted with
the D-125 verified-freeze primitives, PROVEN destroyed (counted DELETE
with RETURNING — destruction is demonstrated, never assumed), then
restored from the archive — but ONLY after the archive re-verifies
(the D-125 gate: a backup is valid only after its attestation holds;
a forged or missing archive fails closed and restores NOTHING).

What is asserted, machine-checked:
  - fold equality via the canonical D-125 fold (write_snapshot on the
    restored state must reproduce the pre-catastrophe archive's fold —
    timestamps excluded from identity, wall clock is audit metadata,
    D-085/D-093);
  - store-level equality via the real PgEventStore API (get_record /
    succeeded_references, deterministic order);
  - the scoped catastrophe touches NO other source (global row count
    of the whole event store is byte-identical across the disaster);
  - forged-archive and missing-archive restores fail closed with the
    Class-B CompactionError and restore nothing (anti-fail-open);
  - BAC-001 evidence through the shipped EvidenceCollector records the
    rehearsal as a positive, commit-bound evidence record.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL = os.path.dirname(HERE)
ROOT = os.path.dirname(LOCAL)
for p in (LOCAL, os.path.join(LOCAL, "canonical"),
          os.path.join(LOCAL, "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

from canonical.compaction import (  # noqa: E402
    CompactionError,
    verify_snapshot,
    write_snapshot,
)
from canonical.launch_contracts import configuration_fingerprint  # noqa: E402
from canonical.launch_evidence import EvidenceCollector  # noqa: E402
from canonical.notion_ingest import PgEventStore  # noqa: E402
from seed_registry import q  # noqa: E402


def _stack_up():
    try:
        out = subprocess.run(
            ["docker", "compose", "-f", "local/infra/docker-compose.yml",
             "ps", "--format", "json"], capture_output=True, text=True,
            timeout=20, cwd=str(ROOT))
        return out.returncode == 0 and \
            "engine-local-postgres" in out.stdout and \
            "healthy" in out.stdout
    except Exception:
        return False


def _candidate_commit() -> str:
    """The launch candidate this drill runs against — resolved from the
    repository itself (no hand-written hashes in evidence)."""
    out = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                         capture_output=True, text=True, cwd=str(ROOT))
    return out.stdout.strip()


# --- store row I/O (same psql discipline as PgEventStore itself) ------

# Identity + ordering columns only: received_at/last_attempt_at are
# wall-clock audit metadata and are deliberately excluded from both the
# archive fold and the restore comparison (D-085/D-093 precedent).
_ROW_COLS = ("event_id", "operation_type", "processing_status",
             "payload_hash", "result_reference", "retry_count",
             "last_error_class", "ingest_seq")


def _scoped_rows(source: str):
    """Every identity-bearing column of the scoped namespace, in
    deterministic ingest_seq order — the restore's source of truth."""
    out = q(
        "SELECT " + " || chr(31) || ".join(
            (f"{c}::text" if c in ("ingest_seq", "retry_count")
             else f"coalesce({c}, '')") for c in _ROW_COLS)
        + " || chr(31) || 'END' FROM events.event_record "
        f"WHERE source_system = '{source}' ORDER BY ingest_seq, event_id")
    rows = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\x1f")
        if parts[-1] != "END" or len(parts) != len(_ROW_COLS) + 1:
            raise RuntimeError(f"malformed row: {parts!r}")
        rows.append(dict(zip(_ROW_COLS, parts[:-1])))
    return rows


def _scoped_count(source: str) -> int:
    out = q("SELECT count(*) FROM events.event_record "
            f"WHERE source_system = '{source}'").strip()
    return int(out)


def _global_count() -> int:
    return int(q("SELECT count(*) FROM events.event_record").strip())


def _fold_of_state(source: str) -> str:
    """Canonical D-125 fold of the CURRENT scoped state, computed by the
    shipped primitives (write a temp archive, read its attested fold).
    No re-implemented fold — the canonical one is the only judge."""
    desc = write_snapshot(
        os.path.join(tempfile.gettempdir(),
                     f"drill26-fold-{uuid.uuid4().hex[:8]}.jsonl"),
        _scoped_rows(source))
    return desc["fold"]


def _purge_scoped(source: str) -> int:
    """The catastrophe: counted DELETE with RETURNING — destruction is
    demonstrated, never assumed. Scoped to the run's namespace only."""
    out = q(f"DELETE FROM events.event_record "
            f"WHERE source_system = '{source}' "
            "RETURNING source_system || chr(31) || 'END'").strip()
    return sum(1 for l in out.splitlines() if l.strip())


def _restore_from_archive(archive_path: str, source: str) -> int:
    """Restore rows from an already-VERIFIED archive into the scoped
    namespace: exactly the archived rows, original ingest_seq preserved
    (reconstruction order survives the round-trip), idempotent inserts
    (NOT EXISTS guard — a repeated restore is a no-op, D-027 parity)."""
    with open(archive_path, encoding="utf-8") as fh:
        header = json.loads(fh.readline())
        rows = [json.loads(l) for l in fh if l.strip()]
    if header.get("row_count") != len(rows):
        raise CompactionError("archive row_count mismatch")
    lines = []
    for r in rows:
        lines.append(
            "INSERT INTO events.event_record (source_system, event_id, "
            "operation_type, received_at, ingest_seq, processing_status, "
            "payload_hash, result_reference, retry_count, last_error_class, "
            "last_attempt_at) SELECT '{src}', '{eid}', '{op}', now(), "
            "{seq}, '{st}', '{ph}', {ref}, {rc}, {ec}, now() "
            "WHERE NOT EXISTS (SELECT 1 FROM events.event_record "
            "WHERE source_system = '{src}' AND event_id = '{eid}');"
            .format(src=source,
                    eid=r["event_id"].replace("'", "''"),
                    op=r["operation_type"].replace("'", "''"),
                    seq=int(r["ingest_seq"]),
                    st=r["processing_status"].replace("'", "''"),
                    ph=r["payload_hash"].replace("'", "''"),
                    ref=("NULL" if not r.get("result_reference")
                         else "'" + r["result_reference"].replace("'", "''")
                         + "'"),
                    rc=int(r.get("retry_count") or 0),
                    ec=("NULL" if not r.get("last_error_class")
                        else "'" + r["last_error_class"].replace("'", "''")
                        + "'")))
    if lines:
        q("\n".join(lines))
    return len(rows)


# --- the drill ---------------------------------------------------------

class TestPhase26ResilienceOffline(unittest.TestCase):
    """Offline tier: fail-closed archive gates and BAC-001 evidence
    binding — no database required."""

    def test_missing_archive_fails_closed(self):
        with self.assertRaises(CompactionError):
            verify_snapshot("/nonexistent/drill26-archive.jsonl")

    def test_bac001_evidence_records_the_rehearsal(self):
        # the drill itself IS the BAC-001 evidence: write+verify rehearsal
        config = {"env": "staging", "capture": False}
        collector = EvidenceCollector(_candidate_commit(), config)
        evidence = collector.restore_rehearsal_evidence(
            write_ok=True, verify_ok=True)
        self.assertEqual(evidence.evidence_id, "EV-BAC-001")
        self.assertEqual(evidence.outcome, "positive")
        self.assertTrue(evidence.valid)
        self.assertEqual(evidence.commit, _candidate_commit())
        # the record is bound to the configuration fingerprint of the
        # exact config the collector was constructed with
        self.assertEqual(evidence.config_fingerprint,
                         configuration_fingerprint(config))


@unittest.skipUnless(_stack_up(), "live PostgreSQL stack not running")
class TestPhase26ResilienceDrillLivePgE2E(unittest.TestCase):
    """Live-PG catastrophic-recovery rehearsal (T3). Zero-skip when the
    stack is up; the guard never fires on a healthy stack."""

    SOURCE = "drill26-"          # + per-run uuid suffix
    N_EVENTS = 12

    def setUp(self):
        self.source = self.SOURCE + uuid.uuid4().hex[:8]
        self.store = PgEventStore(self.source)
        # deterministic per-run namespace: durable+content-addressed
        # stores require fresh context per run (Phase 25/26 discipline)

    def tearDown(self):
        # leave no drill debris: the namespace is removed after the run
        _purge_scoped(self.source)

    def _seed_flow(self):
        """Seed a deterministic mini-flow through the REAL D-027 API —
        the same receive→begin→succeed lifecycle the live E2E battery
        exercises, plus one skipped-duplicate terminal status so the
        archive covers every status the schema allows."""
        for i in range(1, self.N_EVENTS + 1):
            eid = f"drill-event-{i:03d}"
            payload = {"seq": i, "kind": "resilience_drill",
                       "source": self.source}
            rec = self.store.receive(self.source, eid, "drill_op", payload)
            self.assertEqual(rec["verdict"], "new")
            self.store.begin(self.source, eid)
            self.store.succeed(self.source, eid,
                               result_reference=f"drill-ref-{i:03d}")
        # a deduplicated re-delivery: registered, never processed
        dup = "drill-event-dup-001"
        self.store.receive(self.source, dup, "drill_op",
                           {"seq": 0, "kind": "resilience_drill",
                            "source": self.source})
        self.store.mark_skipped_duplicate(self.source, dup)
        self.assertEqual(_scoped_count(self.source), self.N_EVENTS + 1)

    def test_catastrophic_recovery_round_trip(self):
        self._seed_flow()

        # 1. Capture the pre-catastrophe state.
        pre_rows = _scoped_rows(self.source)
        pre_fold = _fold_of_state(self.source)
        pre_refs = self.store.succeeded_references(self.source)
        self.assertEqual(len(pre_refs), self.N_EVENTS)

        # 2. Archive through the real D-125 primitives and verify.
        archive = os.path.join(tempfile.gettempdir(),
                               f"drill26-{self.source}.jsonl")
        desc = write_snapshot(archive, pre_rows)
        self.assertEqual(desc["row_count"], self.N_EVENTS + 1)
        self.assertTrue(verify_snapshot(archive)["ok"])

        # 3. THE CATASTROPHE — scoped, counted, proven.
        before_global = _global_count()
        destroyed = _purge_scoped(self.source)
        self.assertEqual(destroyed, self.N_EVENTS + 1)
        self.assertEqual(_scoped_count(self.source), 0)
        self.assertEqual(_global_count(), before_global - (self.N_EVENTS + 1))
        self.assertEqual(self.store.succeeded_references(self.source), [])

        # 4. Restore — only after the archive re-verifies (D-125 gate).
        self.assertTrue(verify_snapshot(archive)["ok"])
        restored = _restore_from_archive(archive, self.source)
        self.assertEqual(restored, self.N_EVENTS + 1)

        # 5. Verify: canonical fold equality + store-level equality.
        self.assertEqual(_fold_of_state(self.source), pre_fold)
        self.assertEqual(_fold_of_state(self.source), desc["fold"])
        self.assertEqual(self.store.succeeded_references(self.source),
                         pre_refs)
        for i in range(1, self.N_EVENTS + 1):
            eid = f"drill-event-{i:03d}"
            rec = self.store.get_record(self.source, eid)
            self.assertIsNotNone(rec, eid)
            self.assertEqual(rec["processing_status"], "succeeded")
            self.assertEqual(rec["result_reference"], f"drill-ref-{i:03d}")
            self.assertEqual(rec["retry_count"], 0)
        dup = self.store.get_record(self.source, "drill-event-dup-001")
        self.assertIsNotNone(dup)
        self.assertEqual(dup["processing_status"], "skipped_duplicate")
        # the catastrophe touched nothing outside the namespace
        self.assertEqual(_global_count(), before_global)

    def test_forged_archive_fails_closed_and_restores_nothing(self):
        self._seed_flow()
        pre_fold = _fold_of_state(self.source)
        pre_count = _scoped_count(self.source)

        archive = os.path.join(tempfile.gettempdir(),
                               f"drill26-forged-{self.source}.jsonl")
        write_snapshot(archive, _scoped_rows(self.source))
        # FORGE: flip one byte inside a row line
        with open(archive, encoding="utf-8") as fh:
            content = fh.read()
        with open(archive, "w", encoding="utf-8") as fh:
            fh.write(content.replace('"succeeded"', '"succeedeX"', 1))

        # the D-125 gate refuses the forged archive with the Class-B
        # CompactionError — never a silent partial restore
        with self.assertRaises(CompactionError):
            verify_snapshot(archive)
        self.assertEqual(_scoped_count(self.source), pre_count)
        self.assertEqual(_fold_of_state(self.source), pre_fold)


if __name__ == "__main__":
    unittest.main(verbosity=2)

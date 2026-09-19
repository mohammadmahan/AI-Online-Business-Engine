#!/usr/bin/env python3
"""Phase 26 operator command — Resilience Drill (catastrophic recovery).

Operationalizes the BAC-001 backup/recovery control as a routinely
rehearsable, run-scoped command (D-125/D-137/D-140):

    python3 local/scripts/resilience_drill.py [--events N] [--json]

Lifecycle (each stage is machine-checked; any failure fails the run
and emits NEGATIVE evidence — missing or negative evidence can never
yield a pass, D-137):

  1. Scoped seed & canonical fold capture  (real D-027 API, run-
     scoped namespace so live production state is never touched)
  2. Snapshot archiving & verification     (D-125 verified-freeze gate)
  3. Controlled scope purge                (counted DELETE..RETURNING —
     destruction is proven, never assumed)
  4. Rehydration from verified snapshot    (restore only after the
     archive re-verifies; idempotent inserts; original ingest_seq)
  5. Byte-equal fold & storage verification
  6. Evidence certification                (EV-BAC-001, commit-bound)

Pure/injected core lives here; the I/O binds are the same psql
discipline as PgEventStore itself. No wall-clock in the structured
result (deterministic; display layer adds nothing time-based).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL = os.path.dirname(HERE)
for p in (HERE, LOCAL):
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

DRILL_SCHEMA = "ops.resilience_drill.v1"
DRILL_SOURCE_PREFIX = "drill26-"
DRILL_CONFIG = {"env": "local-rehearsal", "drill": True}

STAGE_NAMES = (
    "Scoped seed & canonical fold capture",
    "Snapshot archiving & verification (D-125 gate)",
    "Controlled scope purge (destruction verification)",
    "Rehydration from verified snapshot",
    "Byte-equal fold & storage verification",
    "Evidence certification (EV-BAC-001)",
)


def stack_up() -> bool:
    try:
        out = subprocess.run(
            ["docker", "compose", "-f", "local/infra/docker-compose.yml",
             "ps", "--format", "json"], capture_output=True, text=True,
            timeout=20, cwd=os.path.dirname(LOCAL))
        return out.returncode == 0 and \
            "engine-local-postgres" in out.stdout and \
            "healthy" in out.stdout
    except Exception:
        return False


def candidate_commit() -> str:
    """The launch candidate this drill runs against — resolved from
    the repository itself (no hand-written hashes in evidence)."""
    out = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                         capture_output=True, text=True,
                         cwd=os.path.dirname(LOCAL))
    return out.stdout.strip()


# --- store row I/O (same psql discipline as PgEventStore itself) ------

# Identity + ordering columns only: received_at/last_attempt_at are
# wall-clock audit metadata and are deliberately excluded from both
# the archive fold and the restore comparison (D-085/D-093 precedent).
_ROW_COLS = ("event_id", "operation_type", "processing_status",
             "payload_hash", "result_reference", "retry_count",
             "last_error_class", "ingest_seq")


def scoped_rows(source: str) -> list:
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


def scoped_count(source: str) -> int:
    return int(q("SELECT count(*) FROM events.event_record "
                 f"WHERE source_system = '{source}'").strip())


def global_count() -> int:
    return int(q("SELECT count(*) FROM events.event_record").strip())


def fold_of_state(source: str) -> str:
    """Canonical D-125 fold of the CURRENT scoped state, computed by
    the shipped primitives (temp archive's attested fold). No
    re-implemented fold — the canonical one is the only judge."""
    desc = write_snapshot(
        os.path.join(tempfile.gettempdir(),
                     f"drill26-fold-{uuid.uuid4().hex[:8]}.jsonl"),
        scoped_rows(source))
    return desc["fold"]


def purge_scoped(source: str) -> int:
    """Counted DELETE with RETURNING — destruction is demonstrated,
    never assumed. Scoped to the namespace only."""
    out = q(f"DELETE FROM events.event_record "
            f"WHERE source_system = '{source}' "
            "RETURNING source_system || chr(31) || 'END'").strip()
    return sum(1 for l in out.splitlines() if l.strip())


def restore_from_archive(archive_path: str, source: str) -> int:
    """Restore rows from an already-VERIFIED archive into the scoped
    namespace: exactly the archived rows, original ingest_seq
    preserved (reconstruction order survives the round-trip),
    idempotent inserts (D-027 parity — a repeated restore is a
    no-op)."""
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


def seed_flow(source: str, store: PgEventStore, n_events: int) -> None:
    """Seed a deterministic mini-flow through the REAL D-027 API —
    receive→begin→succeed for every event plus one skipped-duplicate
    terminal so the archive covers every status the schema allows."""
    for i in range(1, n_events + 1):
        eid = f"drill-event-{i:03d}"
        payload = {"seq": i, "kind": "resilience_drill", "source": source}
        rec = store.receive(source, eid, "drill_op", payload)
        if rec["verdict"] != "new":
            raise RuntimeError(f"unexpected verdict {rec['verdict']!r}")
        store.begin(source, eid)
        store.succeed(source, eid, result_reference=f"drill-ref-{i:03d}")
    dup = "drill-event-dup-001"
    store.receive(source, dup, "drill_op",
                  {"seq": 0, "kind": "resilience_drill", "source": source})
    store.mark_skipped_duplicate(source, dup)


# --- the staged drill ---------------------------------------------------

def _stage(index: int, ok: bool, detail: str) -> dict:
    return {"index": index, "name": STAGE_NAMES[index - 1],
            "ok": bool(ok), "detail": detail}


def run_drill(n_events: int = 12, source: str | None = None,
              config: dict | None = None) -> dict:
    """Run the full six-stage drill in a fresh run-scoped namespace and
    return the structured, deterministic result. The namespace is
    always cleaned afterwards (safe for routine rehearsal)."""
    if n_events < 1:
        raise ValueError("n_events must be >= 1")
    src = source or (DRILL_SOURCE_PREFIX + uuid.uuid4().hex[:8])
    cfg = dict(config or DRILL_CONFIG)
    store = PgEventStore(src)
    archive = os.path.join(tempfile.gettempdir(),
                           f"drill26-{src}.jsonl")
    stages: list[dict] = []

    def finish():
        # Single source of truth: the verdict is recomputed from the
        # stages on EVERY path (the fault-injection probe caught a
        # fail-open here — a stale ok_all reported RECOVERED for a
        # failed run).
        all_ok = all(s["ok"] for s in stages)
        return {"schema": DRILL_SCHEMA, "source": src,
                "candidate_commit": candidate_commit(),
                "config_fingerprint": configuration_fingerprint(cfg),
                "ok": all_ok,
                "verdict": "RECOVERED" if all_ok else "FAILED",
                "stages": stages,
                "evidence": evidence_record(stages, cfg)}

    # Always leave no drill debris, success or failure.
    try:
        try:
            # Stage 1 — scoped seed & canonical fold capture.
            seed_flow(src, store, n_events)
            expected = n_events + 1
            if scoped_count(src) != expected:
                raise RuntimeError("seed count mismatch")
            pre_fold = fold_of_state(src)
            pre_refs = store.succeeded_references(src)
            if len(pre_refs) != n_events:
                raise RuntimeError("pre refs mismatch")
            stages.append(_stage(1, True, f"{expected} events seeded "
                                         f"({n_events} succeeded + 1 "
                                         f"skipped_duplicate)"))
        except Exception as e:  # noqa: BLE001 — stage boundary
            stages.append(_stage(1, False, f"error: {type(e).__name__}"))
            return finish()
        try:
            # Stage 2 — snapshot archiving & verification (D-125 gate).
            desc = write_snapshot(archive, scoped_rows(src))
            if desc["row_count"] != expected:
                raise RuntimeError("archive row count mismatch")
            verify_snapshot(archive)
            stages.append(_stage(2, True,
                                 f"archive rows={desc['row_count']} "
                                 f"fold={desc['fold'][:12]}…"))
        except (Exception, CompactionError) as e:  # noqa: BLE001
            stages.append(_stage(2, False, f"error: {type(e).__name__}"))
            return finish()

        try:
            # Stage 3 — controlled scope purge.
            before_global = global_count()
            destroyed = purge_scoped(src)
            if destroyed != expected or scoped_count(src) != 0:
                raise RuntimeError("purge count mismatch")
            if global_count() != before_global - expected:
                raise RuntimeError("global count mismatch after purge")
            if store.succeeded_references(src) != []:
                raise RuntimeError("scoped refs survived purge")
            stages.append(_stage(3, True,
                                 f"{destroyed} rows destroyed; store "
                                 f"{before_global} → "
                                 f"{before_global - expected}"))
        except Exception as e:  # noqa: BLE001
            stages.append(_stage(3, False, f"error: {type(e).__name__}"))
            return finish()

        try:
            # Stage 4 — rehydration from the verified snapshot.
            verify_snapshot(archive)  # the D-125 gate, re-checked
            restored = restore_from_archive(archive, src)
            if restored != expected:
                raise RuntimeError("restore count mismatch")
            stages.append(_stage(4, True, f"{restored} rows rehydrated"))
        except (Exception, CompactionError) as e:  # noqa: BLE001
            stages.append(_stage(4, False, f"error: {type(e).__name__}"))
            return finish()

        try:
            # Stage 5 — byte-equal fold & storage verification.
            if fold_of_state(src) != pre_fold:
                raise RuntimeError("fold divergence after restore")
            if fold_of_state(src) != desc["fold"]:
                raise RuntimeError("fold divergence vs archive header")
            if store.succeeded_references(src) != pre_refs:
                raise RuntimeError("refs divergence after restore")
            for i in range(1, n_events + 1):
                rec = store.get_record(src, f"drill-event-{i:03d}")
                if (rec is None or rec["processing_status"] != "succeeded"
                        or rec["result_reference"] != f"drill-ref-{i:03d}"
                        or rec["retry_count"] != 0):
                    raise RuntimeError(f"record divergence: event {i}")
            dup = store.get_record(src, "drill-event-dup-001")
            if dup is None or dup["processing_status"] != "skipped_duplicate":
                raise RuntimeError("dup record divergence")
            if global_count() != before_global:
                raise RuntimeError("collateral damage outside namespace")
            stages.append(_stage(5, True,
                                 "fold pre==post==archive; records and "
                                 "refs byte-equal; 0 collateral rows"))
        except Exception as e:  # noqa: BLE001
            stages.append(_stage(5, False, f"error: {type(e).__name__}"))
            return finish()
        finally:
            purge_scoped(src)

        ok_all = all(s["ok"] for s in stages)
        stages.append(_stage(6, ok_all,
                             "EV-BAC-001 " + ("positive — rehearsal "
                                              "verified" if ok_all
                                              else "negative — drill "
                                                   "failed")))
        return finish()
    finally:
        # Always leave no drill debris, success or failure (idempotent
        # with the stage-5 cleanup: a second purge removes 0 rows).
        try:
            purge_scoped(src)
        except Exception:  # noqa: BLE001 — best-effort cleanup
            pass


def evidence_record(stages: list, cfg: dict) -> dict:
    """Stage 6: the drill result AS the BAC-001 evidence record.

    Fail-closed: the outcome is POSITIVE only when EVERY stage passed
    — a drill that failed anywhere (even after the archive verified)
    emits NEGATIVE evidence, never a partial pass (D-137)."""
    overall_ok = all(s["ok"] for s in stages)
    collector = EvidenceCollector(candidate_commit(), cfg)
    passed = sum(1 for s in stages if s["ok"])
    rec = collector.restore_rehearsal_evidence(
        write_ok=overall_ok, verify_ok=overall_ok,
        detail=f"operator drill: {passed}/{len(stages)} stages ok")
    return {"evidence_id": rec.evidence_id, "outcome": rec.outcome,
            "valid": rec.valid, "commit": rec.commit,
            "config_fingerprint": rec.config_fingerprint,
            "reference": rec.reference, "detail": rec.detail}


def render_report(result: dict) -> str:
    """Human-readable six-stage status dashboard."""
    lines = [
        "=== Phase 26 Resilience Drill — Catastrophic Recovery ===",
        f"namespace: {result['source']}   candidate: "
        f"{result['candidate_commit']}",
        "",
    ]
    for s in result["stages"]:
        mark = "OK  " if s["ok"] else "FAIL"
        lines.append(f"[{s['index']}/6] {s['name']:<52} {mark} "
                     f"{s['detail']}")
    lines += ["", f"RESULT: {result['verdict']} — evidence "
                  f"{result['evidence']['evidence_id']} "
                  f"({result['evidence']['outcome']})"]
    return "\n".join(lines)


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Phase 26 resilience drill (BAC-001 catastrophic "
                    "recovery rehearsal, run-scoped).")
    ap.add_argument("--events", type=int, default=12,
                    help="seeded succeeded events (default 12)")
    ap.add_argument("--json", action="store_true",
                    help="emit the structured result as JSON")
    args = ap.parse_args(argv)

    if not stack_up():
        print("FATAL: live PostgreSQL stack not healthy — refusing to "
              "run the drill (fail closed).", file=sys.stderr)
        return 2
    result = run_drill(n_events=args.events)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render_report(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

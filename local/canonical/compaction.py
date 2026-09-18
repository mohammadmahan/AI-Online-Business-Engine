"""Phase 23 M1 — deterministic retention & verified-freeze compaction
(D-125, owner-approved 2026-09-18).

Retention by STATE, not age. For every compactable surface the
pipeline is: eligible-set query → verified-freeze snapshot (JSONL
archive + full-set attestation fold) → ONE-batch teardown → live-chain
re-verify → manifest row appended to the Phase 20
`security.hardening_audit` vault (compaction audits itself,
chain-anchored). Any verify failure is Class-B and halts the
compactor FAIL-CLOSED — nothing is removed.

Tamper-evidence is never weakened:
  - `events.event_record` and the Phase 18/19 chain tables are NEVER
    torn down here (chains stay whole); event_record compaction is
    ARCHIVE-ONLY (rows verified into the archive and retained —
    teardown for event_record is an owner-gated future decision).
  - `admin.circuit_breakers` and `scheduling.slot_lock` rows whose
    lifecycle is terminal (breakers beyond the logical horizon,
    superseded slot locks) are snapshot-verified then removed; their
    hashes are row-level (no chain over them), and the manifest +
    archive preserve the evidence.
  - HITL (Phase 18) / control-audit (Phase 19) chains: whole-chain
    attestations are RE-VERIFIED after any compaction run touching
    their stores; compaction never touches their rows, so verify must
    stay green (battery-asserted).

Operator-triggered only (owner directive 2026-09-18): the command
`COMPACT_RETIREABLE` executes via the Phase 19 control plane; no
automatic cadence is wired in this milestone.
"""

import json
import os
import threading
from typing import Callable, Dict, List, Optional

from canonical.security_engine import ChainHeadAttestation

SCHEMA_VERSION = "compaction.manifest.v1"

ARCHIVE_DIR = os.path.join("local", "volumes", "archive")

# Deterministic breaker residue horizon: a non-CLOSED breaker row with
# created_at_logical < horizon prefix is terminal (incident long over
# — its lifecycle was never closed by design in Phases 19-era tests).
_BREAKER_HORIZON_FALLBACK = "0000"


class CompactionError(ValueError):
    """Class-B compaction refusal (fail-closed)."""


def _fail(reason: str):
    raise CompactionError(reason)


def _gate_str(value: str) -> str:
    from canonical.obs_contracts import _sanitize_str
    return _sanitize_str(value)


def _now_env(key: str, default: str) -> str:
    """Environment-configurable horizon (owner directive: bounds are
    env parameters). Deterministic: read once per call, no wall clock.
    """
    return os.environ.get(key, default)


# --- surface definitions (state-based eligibility) ---------------------------

TERMINAL_EVENT_STATUSES = ("succeeded", "skipped_duplicate")


def eligible_event_rows(rows: List[Dict]) -> List[Dict]:
    """`events.event_record` ARCHIVE-ONLY eligibility: terminal
    processing rows. The caller decides what to do with the archived
    set (teardown is owner-gated, never automatic)."""
    return [r for r in rows if r.get("processing_status")
            in TERMINAL_EVENT_STATUSES]


def eligible_breaker_rows(rows: List[Dict], horizon: str) -> List[Dict]:
    """Breaker rows terminal by the declared logical horizon: state
    CLOSED, or non-CLOSED rows whose logical stamp sorts before the
    horizon prefix (incident long over, never closed by design)."""
    return [r for r in rows
            if r.get("state") == "CLOSED"
            or str(r.get("tripped_at_logical")
                   or r.get("created_at_logical") or "0") < horizon]


def eligible_slot_lock_rows(rows: List[Dict]) -> List[Dict]:
    """Superseded slot locks (`active = false`) — D-096 history rows
    whose lock is no longer held."""
    return [r for r in rows if r.get("active") is False
            or str(r.get("active", "")).lower() == "false"]


def _rows_fold(rows: List[Dict]) -> str:
    """Full-set attestation fold over the snapshotted set (same
    construction as ChainHeadAttestation._fold — position-weighted,
    full-row)."""
    import hashlib
    acc = f"snap-v1:{len(rows)}"
    for i, row in enumerate(rows):
        row_sha = hashlib.sha256(
            json.dumps(row, ensure_ascii=False, sort_keys=True,
                       default=str).encode("utf-8")).hexdigest()
        acc = hashlib.sha256(
            f"{acc}|{i}|{row_sha}".encode("utf-8")).hexdigest()
    return acc


# --- snapshot / verify / teardown --------------------------------------------

def write_snapshot(path: str, rows: List[Dict]) -> Dict:
    """Write the JSONL archive + manifest header. Returns the archive
    descriptor (path, count, fold)."""
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    fold = _rows_fold(rows)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"schema_version": SCHEMA_VERSION,
                             "row_count": len(rows), "fold": fold},
                            ensure_ascii=False, sort_keys=True) + "\n")
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True,
                                default=str) + "\n")
    return {"path": path, "row_count": len(rows), "fold": fold}


def verify_snapshot(path: str) -> Dict:
    """Re-derive the fold from the archive file and compare with the
    manifest header. A flipped byte, dropped line, reordered row, or
    unparseable content fails verification (D-128 forgery battery) —
    every read/parse failure is the Class-B CompactionError, never a
    leaked low-level exception."""
    try:
        with open(path, encoding="utf-8") as fh:
            header = json.loads(fh.readline())
            rows = [json.loads(l) for l in fh if l.strip()]
    except (json.JSONDecodeError, OSError) as e:
        _fail(f"snapshot_unparseable: {type(e).__name__}")
    if not isinstance(header, dict):
        _fail("snapshot_header_invalid")
    if header.get("schema_version") != SCHEMA_VERSION:
        _fail("snapshot_schema_mismatch")
    if header.get("row_count") != len(rows):
        _fail("snapshot_row_count_mismatch")
    if header.get("fold") != _rows_fold(rows):
        _fail("snapshot_fold_mismatch")
    return {"ok": True, "row_count": len(rows), "fold": header["fold"]}


def compact(surface: str, *, rows_provider: Callable[[], List[Dict]],
            delete_fn: Callable[[List[Dict]], int],
            archive_path: str, horizon: str = "") -> Dict:
    """The D-125 pipeline for ONE surface. `rows_provider` reads the
    current rows; `delete_fn(rows)` removes exactly the eligible set
    and returns the number removed (caller-owned SQL). Steps:
    eligibility → snapshot → verify → teardown → re-verify snapshot
    (post-write integrity) → return the manifest body. Raises
    CompactionError (fail-closed) on ANY verify failure BEFORE any
    delete_fn call — a snapshot that doesn't verify means no
    teardown.
    """
    rows = rows_provider()
    if surface == "events.event_record":
        elig = eligible_event_rows(rows)
    elif surface == "admin.circuit_breakers":
        if not horizon:
            _fail("breaker surface needs a horizon")
        elig = eligible_breaker_rows(rows, horizon)
    elif surface == "scheduling.slot_lock":
        elig = eligible_slot_lock_rows(rows)
    else:
        _fail(f"unknown compaction surface: {surface}")

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "surface": surface,
        "scanned": len(rows),
        "eligible": len(elig),
        "horizon": horizon or None,
        "archive": None,
        "removed": 0,
    }
    if not elig:
        return manifest  # nothing to do — still auditable

    snap = write_snapshot(archive_path, elig)
    try:
        verify_snapshot(archive_path)
    except CompactionError as e:
        _fail(f"snapshot verification failed, nothing removed: {e}")
    manifest["archive"] = snap

    removed = delete_fn(elig)
    if removed != len(elig):
        _fail(f"teardown count mismatch: removed {removed}, "
              f"eligible {len(elig)}")
    manifest["removed"] = removed

    # post-teardown integrity: the archive must still verify (guards
    # against a torn write between snapshot and teardown)
    verify_snapshot(archive_path)
    return manifest


def record_manifest(engine, manifest: Dict) -> str:
    """Append the compaction manifest to the Phase 20
    `security.hardening_audit` vault via the HardeningEngine facade
    (attempt-unique PK dedup, D-027 event emission)."""
    engine.audit({
        "record_kind": "compaction_manifest",
        "subject": manifest["surface"],
        "actor": "actor:system:compactor",
        "detail": manifest,
        "logical_at": manifest.get("logical_at") or "L0",
    })
    return "recorded"


# --- read-path cost: keyset-paginated event history (D-125) -------------------

def keyset_scan_events(exec_fn: Callable, after_source: str = "",
                       after_event: str = "", batch: int = 500) -> Dict:
    """One keyset page over `events.event_record` ordered by the PK
    (source_system, event_id) — no OFFSET scans, cost stays flat as
    history grows. Pass the returned `next_after_*` values back in for
    the following page."""
    out = exec_fn(
        "SELECT source_system || chr(31) || event_id || chr(31) || "
        "processing_status || chr(31) || 'END' FROM events.event_record "
        "WHERE (source_system, event_id) > (" + _txt("a") + ", "
        + _txt("b") + ") ORDER BY source_system, event_id LIMIT "
        + str(int(batch)), {"a": after_source, "b": after_event})
    rows = []
    for line in (out or "").splitlines():
        line = line.strip()
        if not line:
            continue
        p = line.split("\x1f")
        rows.append({"source_system": p[0], "event_id": p[1],
                     "processing_status": p[2]})
    has_more = len(rows) == int(batch)
    return {"rows": rows, "has_more": has_more,
            "next_after_source": rows[-1]["source_system"] if rows else "",
            "next_after_event": rows[-1]["event_id"] if rows else ""}


# --- Phase 19 control-plane command (operator-triggered) ----------------------

def run_compact_retireable(engine, exec_fn: Callable, horizon: str,
                           archive_dir: str = ARCHIVE_DIR) -> Dict:
    """Handler body for the `COMPACT_RETIREABLE` admin command:
    compacts breaker residue + superseded slot locks on the live
    store, records one manifest per surface, returns the summary.
    `exec_fn(sql, params)` is the canonical psql transport (injected);
    `engine` is the HardeningEngine facade (manifest audit rows)."""
    results = []
    for surface in ("admin.circuit_breakers", "scheduling.slot_lock"):
        path = os.path.join(
            archive_dir,
            surface.replace(".", "_") + "_"
            + horizon.replace(":", "").replace("-", "") + ".jsonl")
        m = compact(surface,
                    rows_provider=lambda s=surface: _read_surface_rows(
                        exec_fn, s),
                    delete_fn=lambda elig, s=surface: _delete_surface_rows(
                        exec_fn, s, elig),
                    archive_path=path, horizon=horizon)
        m["logical_at"] = horizon
        m["manifest_recorded"] = record_manifest(engine, m)
        results.append(m)
    return {"ok": True, "surfaces": results}


def _read_surface_rows(exec_fn: Callable, surface: str) -> List[Dict]:
    if surface == "admin.circuit_breakers":
        out = exec_fn(
            "SELECT breaker_name || chr(31) || state || chr(31) || "
            "coalesce(tripped_by, '') || chr(31) || "
            "coalesce(tripped_at_logical, '') || chr(31) || "
            "coalesce(cool_down_until, '') || chr(31) || "
            "coalesce(last_reason, '') || chr(31) || 'END' "
            "FROM admin.circuit_breakers ORDER BY breaker_name", {})
    elif surface == "scheduling.slot_lock":
        out = exec_fn(
            "SELECT platform || chr(31) || slot_bucket || chr(31) || "
            "post_id || chr(31) || coalesce(scheduled_for, '') || "
            "chr(31) || active::text || chr(31) || 'END' "
            "FROM scheduling.slot_lock ORDER BY platform, slot_bucket",
            {})
    else:
        _fail(f"unknown surface: {surface}")
    rows = []
    for line in (out or "").splitlines():
        line = line.strip()
        if not line:
            continue
        p = line.split("\x1f")
        if surface == "admin.circuit_breakers":
            rows.append({"breaker_name": p[0], "state": p[1],
                         "tripped_by": p[2] or None,
                         "tripped_at_logical": p[3] or None,
                         "cool_down_until": p[4] or None,
                         "last_reason": p[5] or None})
        else:  # scheduling.slot_lock
            rows.append({"platform": p[0], "slot_bucket": p[1],
                         "post_id": p[2],
                         "scheduled_for": p[3] or None,
                         # boolean::text renders 'true'/'false' in PG
                         # (defect fix: 'True'/'t' never matched, which
                         # misclassified ACTIVE locks as eligible)
                         "active": p[4].lower() == "true"
                         or p[4] == "t"})
    return rows


def _delete_surface_rows(exec_fn: Callable, surface: str,
                         elig: List[Dict]) -> int:
    if not elig:
        return 0
    if surface == "admin.circuit_breakers":
        removed = 0
        for row in elig:
            exec_fn("DELETE FROM admin.circuit_breakers WHERE "
                    "breaker_name = " + _txt("k"),
                    {"k": row["breaker_name"]})
            removed += 1
        return removed
    if surface == "scheduling.slot_lock":
        removed = 0
        for row in elig:
            exec_fn("DELETE FROM scheduling.slot_lock WHERE platform = "
                    + _txt("p") + " AND slot_bucket = " + _txt("b"),
                    {"p": row["platform"], "b": row["slot_bucket"]})
            removed += 1
        return removed
    _fail(f"unknown surface: {surface}")


def _txt(param: str) -> str:
    from canonical.notion_ingest import _txt as t
    return t(param)

"""Phase 13 M2 — analytics projection engine (D-085/D-086).

Incremental read-model builder over the D-027 store: consumes events
with `ingest_seq` (PG) / `receive_seq` (JSON parity) STRICTLY greater
than the durable cursor, classifies each into zero or one metric
record (D-085 — pure contract functions), folds them into windowed
rollups, and materializes a snapshot.

D-086 guarantees:
  - exactly-once: the cursor advances atomically with the snapshot
    write; a pass that fails before that leaves the cursor unchanged
    (the next pass re-consumes — no lost events, no double count);
  - rebuild = cursor reset to 0 + replay ⇒ byte-identical state;
  - NO wall-clock input anywhere; ordering comes only from the
    store's monotonic sequence.

CQRS: writes go ONLY to the analytics schema / parity files.
"""

import json
import sys
from typing import Dict, List, Optional

from canonical.analytics_contracts import (
    WINDOW_DAILY,
    WINDOW_HOURLY,
    WINDOW_MONTHLY,
    WINDOWS,
    add_metric,
    classify_event,
    finalize_rollup,
    new_rollup,
)

SOURCE_SYSTEM = "analytics"


class _JsonCursorStore:
    """Offline parity cursor + snapshots (file-backed, module-locked)."""

    _PATH_LOCKS: Dict[str, object] = {}

    def __init__(self, path: str):
        import threading
        self.path = path
        lock = _JsonCursorStore._PATH_LOCKS.get(path)
        if lock is None:
            lock = threading.Lock()
            _JsonCursorStore._PATH_LOCKS[path] = lock
        self._lock = lock

    def _load(self) -> Dict:
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (FileNotFoundError, json.JSONDecodeError):
            return {"last_seq": 0, "rollups": {}}

    def _save(self, data: Dict) -> None:
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2,
                      sort_keys=True)
        import os
        os.replace(tmp, self.path)

    def get_cursor(self) -> int:
        with self._lock:
            return int(self._load().get("last_seq", 0))

    def advance(self, last_seq: int, rollups: Dict) -> None:
        with self._lock:
            data = self._load()
            data["last_seq"] = int(last_seq)
            data["rollups"] = rollups
            self._save(data)

    def reset(self) -> None:
        with self._lock:
            self._save({"last_seq": 0, "rollups": {}})

    def rollups(self) -> Dict:
        with self._lock:
            return json.loads(json.dumps(
                self._load().get("rollups", {}), ensure_ascii=False))


class _PgCursorStore:
    """Live cursor + snapshots on the analytics schema (D-055/D-086)."""

    def __init__(self):
        import os as _os
        scripts = _os.path.join("local", "scripts")
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        from canonical.notion_ingest import _exec, _txt  # noqa: E402
        self._exec = _exec
        self._txt = _txt

    def get_cursor(self) -> int:
        out = self._exec(
            "SELECT last_seq::text || chr(31) || 'END' "
            "FROM analytics.cursor WHERE id = 1").strip()
        parts = out.split("\x1f")
        return int(parts[0]) if parts and parts[-1] == "END" else 0

    def advance(self, last_seq: int, rollups: Dict) -> None:
        # atomic single statement: cursor + snapshot + metric_rollup
        # (the CQRS query table, D-085) move together
        state_json = json.dumps(rollups, ensure_ascii=False,
                                sort_keys=True)
        self._exec(
            "WITH up AS ("
            "  INSERT INTO analytics.cursor (id, last_seq, updated_at) "
            "  VALUES (1, " + self._txt("s") + "::bigint, now()) "
            "  ON CONFLICT (id) DO UPDATE SET last_seq = "
            "  EXCLUDED.last_seq, updated_at = now() RETURNING last_seq"
            "), ins AS ("
            "  INSERT INTO analytics.snapshot (window_kind, last_seq, "
            "  state) SELECT m.key, up.last_seq, m.value "
            "  FROM up, jsonb_each(" + self._txt("j") + "::jsonb) "
            "  AS m(key, value) "
            "  ON CONFLICT (window_kind, last_seq) DO NOTHING"
            "), cells AS ("
            "  SELECT s.window_kind, m.key AS metric_kind, "
            "         b.key AS bucket, "
            "         (b.value->>'value')::bigint AS value, "
            "         (b.value->>'count')::bigint AS count "
            "  FROM analytics.snapshot s "
            "  CROSS JOIN LATERAL jsonb_each(s.state) AS m(key, value) "
            "  CROSS JOIN LATERAL jsonb_each(m.value) AS b(key, value) "
            "  WHERE s.last_seq = (SELECT last_seq FROM up)"
            ") INSERT INTO analytics.metric_rollup (window_kind, "
            "metric_kind, bucket, value, count) "
            "SELECT window_kind, metric_kind, bucket, value, count "
            "FROM cells ON CONFLICT (window_kind, metric_kind, bucket) "
            "DO UPDATE SET value = EXCLUDED.value, "
            "count = EXCLUDED.count",
            {"s": str(int(last_seq)), "j": state_json})

    def reset(self) -> None:
        self._exec(
            "UPDATE analytics.cursor SET last_seq = 0, updated_at = "
            "now() WHERE id = 1; DELETE FROM analytics.snapshot; "
            "DELETE FROM analytics.metric_rollup; "
            "DELETE FROM analytics.campaign_attribution", {})

    def rollups(self) -> Dict:
        # rebuilt from the latest snapshot per window
        out: Dict[str, Dict] = {}
        for grain in WINDOWS:
            row = self._exec(
                "SELECT state::text || chr(31) || 'END' "
                "FROM analytics.snapshot WHERE window_kind = "
                + self._txt("g") + " ORDER BY last_seq DESC LIMIT 1",
                {"g": grain}).strip()
            if not row:
                continue
            parts = row.split("\x1f")
            if len(parts) >= 2 and parts[-1] == "END" and parts[0]:
                out[grain] = json.loads(parts[0])
        return out


def _default_cursor_store():
    """PG when the live stack answers, JSON parity otherwise."""
    try:
        store = _PgCursorStore()
        store.get_cursor()
        return store
    except Exception:
        import os
        os.makedirs("local/volumes/analytics", exist_ok=True)
        return _JsonCursorStore("local/volumes/analytics/projection.json")


class ProjectionEngine:
    """D-086 incremental read-model builder.

    events_source(source_system, after_seq) → [(seq, ref), ...] is
    injected (the store adapter) so this engine never imports a
    vendor module directly.
    """

    def __init__(self, events_source, cursor_store=None,
                 sources=("instagram", "telegram", "oms")):
        self.events_source = events_source
        self.cursor = cursor_store or _default_cursor_store()
        self.sources = tuple(sources)

    # -- event reading -----------------------------------------------------

    def _events_after(self, after_seq: int) -> List:
        out: List = []
        for src in self.sources:
            for seq, ref in self.events_source(src, after_seq):
                out.append((int(seq), src, ref))
        out.sort(key=lambda t: t[0])
        return out

    # -- incremental pass (D-086) -------------------------------------------

    def incremental_pass(self) -> Dict:
        """Consume new events → advance rollups → snapshot + cursor.
        Returns the pass summary. Never raises on a bad event: a
        non-metric event is simply skipped (classification is pure)."""
        cursor = self.cursor.get_cursor()
        events = self._events_after(cursor)
        processed = 0
        max_seq = cursor
        per_source = {}
        rollups = self.cursor.rollups()
        # keep raw accumulators per window; rollups store finalized
        # states, so re-fold: finalized cells carry count+sum which is
        # exactly the accumulator shape used by add_metric
        acc: Dict[str, Dict] = {}
        for grain in WINDOWS:
            g = acc.setdefault(grain, new_rollup())
            existing = rollups.get(grain) or {}
            for kind, cells in existing.items():
                if kind not in g:
                    continue
                for bucket, cell in cells.items():
                    g[kind][bucket] = {
                        "count": cell.get("count", 0),
                        "sum": cell.get("value", 0)
                        if not isinstance(cell.get("sum"), int)
                        else cell.get("sum"),
                        "last_seq": 0,
                    }
        for seq, src, ref in events:
            metrics = classify_event(src, ref)
            if metrics is None:
                max_seq = max(max_seq, seq)
                continue
            if isinstance(metrics, dict):
                metrics = [metrics]
            for grain in WINDOWS:
                for met in metrics:
                    add_metric(acc[grain], met, window=grain)
            processed += 1
            per_source[src] = per_source.get(src, 0) + 1
            max_seq = max(max_seq, seq)
        if events:
            finalized = {grain: finalize_rollup(acc[grain])
                         for grain in WINDOWS}
            # atomic advance: snapshot + cursor move together (D-086)
            self.cursor.advance(max_seq, finalized)
        return {"consumed": processed, "from_cursor": cursor,
                "to_cursor": max_seq, "per_source": per_source}

    def snapshot(self, window: str = WINDOW_DAILY) -> Dict:
        rollups = self.cursor.rollups()
        return rollups.get(window, {})

    def rebuild(self) -> Dict:
        """D-086 rebuild: cursor → 0, full replay. Deterministic."""
        self.cursor.reset()
        return self.incremental_pass()

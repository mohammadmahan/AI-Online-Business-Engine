"""Phase 13 M3 — cross-domain correlator + report exporter
(D-087/D-088).

Correlator (D-087): joins the publication stream (events carrying
`campaign_id`, written by the Phase 9/10/11 domains) with the order
stream (events carrying `source_campaign_id`, written by the Phase 12
domain) INSIDE the read model only. The two domains share a string
field and nothing else — no imports, no calls, no shared mutable
state. Events without a campaign id become unattributed rows, never
errors. The attribution window is hours-after-publication,
deterministic from the events' own recorded timestamps.

Exporter (D-088): a report is identified by a SHA-256 window_hash
over (kind, grain, start, end, source cursor). Same inputs yield a
byte-identical report returned from the vault; different inputs make
a new hash. Every generation appends an audit record. CSV is fixed
dialect (UTF-8, header, comma, RFC quoting) so bytes are reproducible.
"""

import csv
import io
import json
import sys
from typing import Dict, List, Optional

from canonical.analytics_contracts import (
    MK_ORDER_COMPLETED,
    MK_PUBLICATION_PUBLISHED,
    MK_REVENUE_MINOR,
    SOURCE_SYSTEM,
    AnalyticsContractError,
    window_hash,
    window_key,
)

OP_REPORT = "report_generated"


class CampaignCorrelator:
    """D-087 read-model join: publications ⟕ orders on campaign id.

    publication_records: iterable of dicts with
      {campaign_id, occurred_at}
    order_records: iterable of dicts with
      {source_campaign_id, occurred_at, order_total_minor}
    """

    def __init__(self, attribution_hours: float = 48.0):
        if attribution_hours < 0:
            raise AnalyticsContractError(
                "attribution_hours must be >= 0 (D-087)")
        self.attribution_hours = attribution_hours

    @staticmethod
    def _ts(value: str) -> Optional[float]:
        try:
            from datetime import datetime, timezone
            t0 = datetime.fromisoformat(
                str(value).replace("Z", "+00:00"))
            if t0.tzinfo is None:
                t0 = t0.replace(tzinfo=timezone.utc)
            return t0.timestamp()
        except (ValueError, TypeError, AttributeError):
            return None

    def correlate(self, publication_records: List[Dict],
                  order_records: List[Dict]) -> Dict:
        """Deterministic attribution: each order joins the LATEST
        publication of the same campaign that occurred at-or-before
        the order and within the attribution window. Ties (same
        timestamp) resolve by campaign then bucket order — sorted
        inputs make the choice stable. Output:
        {campaign_id: {publications, orders, revenue_minor,
                       unattributed_orders}} keyed per day bucket.
        """
        pubs = sorted(
            (p for p in publication_records
             if p.get("campaign_id") and self._ts(p.get("occurred_at"))
             is not None),
            key=lambda p: (self._ts(p["occurred_at"]),
                           p["campaign_id"]))
        out: Dict[str, Dict] = {}
        win_s = self.attribution_hours * 3600.0

        def cell(campaign: str, bucket: str) -> Dict:
            return out.setdefault(campaign, {}).setdefault(
                bucket, {"publications": 0, "orders": 0,
                         "revenue_minor": 0, "unattributed_orders": 0})

        for p in pubs:
            c = cell(p["campaign_id"],
                     window_key(p["occurred_at"], "daily"))
            c["publications"] += 1

        orders_sorted = sorted(
            (o for o in order_records
             if o.get("occurred_at")
             and self._ts(o.get("occurred_at")) is not None),
            key=lambda o: self._ts(o["occurred_at"]))
        for o in orders_sorted:
            campaign = o.get("source_campaign_id")
            bucket = window_key(o["occurred_at"], "daily")
            if not campaign:
                # unattributed: preserved, never dropped (D-087)
                cell("_unattributed", bucket)["orders"] += 1
                continue
            o_ts = self._ts(o["occurred_at"])
            # LATEST publication of this campaign at-or-before the order
            best = None
            for p in pubs:
                if p["campaign_id"] != campaign:
                    continue
                p_ts = self._ts(p["occurred_at"])
                if p_ts <= o_ts and (o_ts - p_ts) <= win_s:
                    best = p
            if best is None:
                cell(campaign, bucket)["unattributed_orders"] += 1
                continue
            c = cell(campaign, bucket)
            c["orders"] += 1
            try:
                c["revenue_minor"] += max(int(o.get(
                    "order_total_minor") or 0), 0)
            except (TypeError, ValueError):
                pass
        return out


class ReportExporter:
    """D-088 idempotent report generation + audit vault.

    vault must implement: has(hash) → bool, put(record), audit()
    (PG and JSON parity implementations live here).
    """

    def __init__(self, vault):
        self.vault = vault

    # -- report identity ----------------------------------------------------

    def report_hash(self, report_kind: str, window_grain: str,
                    start: str, end: str, source_cursor: int) -> str:
        return window_hash(report_kind, window_grain, start, end,
                           source_cursor)

    # -- rendering (deterministic bytes) --------------------------------------

    def render_json(self, payload: Dict) -> str:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True,
                          indent=2)

    def render_csv(self, rows: List[Dict],
                   columns: List[str]) -> str:
        buf = io.StringIO()
        writer = csv.DictWriter(
            buf, fieldnames=columns, extrasaction="ignore",
            quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
        writer.writeheader()
        for row in sorted(rows, key=lambda r: tuple(
                str(r.get(c, "")) for c in columns)):
            writer.writerow(row)
        return buf.getvalue()

    # -- generation (idempotent, audited) --------------------------------------

    def generate(self, report_kind: str, window_grain: str,
                 start: str, end: str, source_cursor: int,
                 payload: Dict, *, actor: str = "analytics-ops",
                 fmt: str = "json") -> Dict:
        if fmt not in ("json", "csv"):
            raise AnalyticsContractError(
                "fmt must be json|csv (D-088)")
        w_hash = self.report_hash(report_kind, window_grain, start,
                                  end, source_cursor)
        if self.vault.has(w_hash):
            return {"generated": False, "verdict": "idempotent_hit",
                    "window_hash": w_hash,
                    "report": self.vault.get(w_hash)}
        report = {
            "report_kind": report_kind,
            "window_grain": window_grain,
            "window_start": start,
            "window_end": end,
            "source_cursor": int(source_cursor),
            "window_hash": w_hash,
            "payload": payload,
        }
        if fmt == "csv":
            flat = self._flatten(payload)
            report["csv"] = self.render_csv(
                flat, ["metric_kind", "bucket", "value", "count"])
        self.vault.put(report)
        return {"generated": True, "verdict": "new",
                "window_hash": w_hash, "report": report}

    @staticmethod
    def _flatten(payload: Dict) -> List[Dict]:
        rows: List[Dict] = []
        for kind, cells in (payload.get("metrics") or {}).items():
            for bucket, cell in (cells or {}).items():
                rows.append({"metric_kind": kind, "bucket": bucket,
                             "value": cell.get("value", 0),
                             "count": cell.get("count", 0)})
        return rows


# --- vault implementations (D-088) -------------------------------------------

class JsonReportVault:
    """Offline parity vault (file-backed, module-locked)."""

    _PATH_LOCKS: Dict[str, object] = {}

    def __init__(self, path: str):
        import threading
        self.path = path
        lock = JsonReportVault._PATH_LOCKS.get(path)
        if lock is None:
            lock = threading.Lock()
            JsonReportVault._PATH_LOCKS[path] = lock
        self._lock = lock

    def _load(self) -> Dict:
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (FileNotFoundError, json.JSONDecodeError):
            return {"reports": {}, "audit": []}

    def _save(self, data: Dict) -> None:
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2,
                      sort_keys=True)
        import os
        os.replace(tmp, self.path)

    def has(self, w_hash: str) -> bool:
        with self._lock:
            return w_hash in self._load().get("reports", {})

    def get(self, w_hash: str) -> Optional[Dict]:
        with self._lock:
            return self._load().get("reports", {}).get(w_hash)

    def put(self, report: Dict) -> None:
        with self._lock:
            data = self._load()
            data.setdefault("reports", {})[report["window_hash"]] = \
                report
            data.setdefault("audit", []).append({
                "window_hash": report["window_hash"],
                "report_kind": report["report_kind"],
                "window_grain": report["window_grain"],
                "window_start": report["window_start"],
                "window_end": report["window_end"],
                "source_cursor": report["source_cursor"],
                "actor": "analytics-ops",
            })
            self._save(data)

    def audit(self) -> List[Dict]:
        with self._lock:
            return list(self._load().get("audit", []))


class PgReportVault:
    """Live vault on analytics.report_audit (D-055/D-088): the report
    row IS the audit record (PK-as-hash, idempotent by construction)."""

    def __init__(self):
        import os as _os
        scripts = _os.path.join("local", "scripts")
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        from canonical.notion_ingest import _exec, _txt  # noqa: E402
        self._exec = _exec
        self._txt = _txt

    def has(self, w_hash: str) -> bool:
        out = self._exec(
            "SELECT window_hash FROM analytics.report_audit "
            "WHERE window_hash = " + self._txt("h"),
            {"h": w_hash}).strip()
        return bool(out)

    def get(self, w_hash: str) -> Optional[Dict]:
        out = self._exec(
            "SELECT report_kind || chr(31) || window_grain || chr(31) "
            "|| window_start || chr(31) || window_end || chr(31) || "
            "source_cursor::text || chr(31) || payload::text || "
            "chr(31) || 'END' FROM analytics.report_audit "
            "WHERE window_hash = " + self._txt("h"),
            {"h": w_hash}).strip()
        parts = out.split("\x1f")
        if len(parts) < 7 or parts[-1] != "END":
            return None
        return {"report_kind": parts[0], "window_grain": parts[1],
                "window_start": parts[2], "window_end": parts[3],
                "source_cursor": int(parts[4]),
                "payload": json.loads(parts[5])}

    def put(self, report: Dict) -> None:
        payload = json.dumps(
            {k: v for k, v in report.items() if k != "csv"},
            ensure_ascii=False, sort_keys=True)
        self._exec(
            "INSERT INTO analytics.report_audit (window_hash, "
            "report_kind, window_grain, window_start, window_end, "
            "source_cursor, row_count, payload) VALUES ("
            + self._txt("h") + ", " + self._txt("k") + ", "
            + self._txt("g") + ", " + self._txt("s") + ", "
            + self._txt("e") + ", " + self._txt("c") + "::bigint, "
            + self._txt("n") + "::int, " + self._txt("p")
            + "::jsonb) ON CONFLICT (window_hash) DO NOTHING",
            {"h": report["window_hash"], "k": report["report_kind"],
             "g": report["window_grain"],
             "s": report["window_start"], "e": report["window_end"],
             "c": str(int(report["source_cursor"])),
             "n": str(len((report.get("payload") or {})
                          .get("metrics", {}))),
             "p": payload})

    def audit(self) -> List[Dict]:
        out = self._exec(
            "SELECT window_hash || chr(31) || report_kind || chr(31) "
            "|| window_grain || chr(31) || 'END' "
            "FROM analytics.report_audit ORDER BY window_hash", {})
        rows = []
        for line in out.splitlines():
            parts = line.strip().split("\x1f")
            if len(parts) >= 4 and parts[-1] == "END":
                rows.append({"window_hash": parts[0],
                             "report_kind": parts[1],
                             "window_grain": parts[2]})
        return sorted(rows, key=lambda r: r["window_hash"])


def _default_vault():
    try:
        v = PgReportVault()
        v.audit()
        return v
    except Exception:
        import os
        os.makedirs("local/volumes/analytics", exist_ok=True)
        return JsonReportVault(
            "local/volumes/analytics/report_vault.json")

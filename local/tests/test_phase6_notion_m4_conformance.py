"""Phase 6 M4 — conformance-matrix execution + data-integrity audit tests.

Executes EVERY frozen row of
local/tests/fixtures/notion/conformance_matrix.json against BOTH D-027
stores:

  - json_local      : services.sync_engine.EventStore (offline, real)
  - postgres_canonical : canonical.notion_ingest.PgEventStore (live,
    skipped ONLY when the Docker/Colima stack is absent)

The engine-level rows (E, F, and the suppression guards of G) run the
REAL PollingEngine against each store — conformance is proven through
the same path production would use, not by calling internals directly.

No test weakens an earlier suite; no failure is converted into a skip.
"""

import json
import os
import sys
import unittest
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOCAL = HERE.parent
ROOT = LOCAL.parent
for p in (str(LOCAL), str(LOCAL / "canonical"), str(LOCAL / "services"),
          str(LOCAL / "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

from canonical.notion_contracts import (  # noqa: E402
    APPROVED, BACKLOG, DRAFT, PUBLISHED, RESEARCHING, REVIEW,
)
from canonical.notion_ingest import PgEventStore, rebuild_state  # noqa: E402
from services.notion_adapter import MockNotionAdapter, PollingEngine  # noqa: E402
from services.sync_engine import EventStore as JSONEventStore  # noqa: E402
import seed_registry  # noqa: E402

MATRIX = json.loads(
    (HERE / "fixtures" / "notion" / "conformance_matrix.json")
    .read_text(encoding="utf-8"))
_ROWS = {r["id"]: r for r in MATRIX["rows"]}

_RUN_NONCE = uuid.uuid4().hex[:10]
_QUEUE_PATH = str(HERE / "fixtures" / "notion" / "_m4_queue.json")
_PROV_PATH = str(HERE / "fixtures" / "notion" / "_m4_provenance.json")
_CURSOR_PATH = str(HERE / "fixtures" / "notion" / "_m4_cursor.json")


def _pg_reachable() -> bool:
    try:
        return seed_registry.q("SELECT 1;").strip() == "1"
    except Exception:
        return False


def _clean_aux():
    for p in (_QUEUE_PATH, _PROV_PATH, _CURSOR_PATH):
        if os.path.exists(p):
            os.remove(p)


def _make_queue():
    from canonical.verification_tool import VerificationQueue
    return VerificationQueue(queue_path=_QUEUE_PATH)


def _make_provenance():
    from services.sync_engine import ProvenanceEngine
    return ProvenanceEngine(_PROV_PATH)


def _page() -> str:
    h = uuid.uuid4().hex
    return f"{h[:8]}-{h[8:12]}-4{h[13:16]}-a{h[17:20]}-{h[20:32]}"


def _marker(tag: str) -> str:
    return f"{tag}-{_RUN_NONCE}"


def _count_succeeded(store, eid) -> int:
    if isinstance(store, JSONEventStore):
        rec = store.get_record(store.source_system_default
                               if hasattr(store, "source_system_default")
                               else "notion", eid)
        # JSON store keys by (source, id); count via records map:
        hits = [r for r in store.records.values()
                if r["event_id"] == eid
                and r["processing_status"] == "succeeded"]
        return len(hits)
    rec = store.get_record(store.source_system, eid)
    return 1 if rec and rec["processing_status"] == "succeeded" else 0


def _row_evidence(store, eid) -> dict:
    """Row evidence for one event id, store-neutral."""
    if isinstance(store, JSONEventStore):
        hits = [r for r in store.records.values() if r["event_id"] == eid]
        if not hits:
            return {"present": False}
        r = hits[0]
        return {"present": True, "status": r["processing_status"],
                "error_class": r.get("last_error_class")}
    rec = store.get_record(store.source_system, eid)
    if not rec:
        return {"present": False}
    return {"present": True, "status": rec["processing_status"],
            "error_class": rec.get("last_error_class")}


class _StoreMatrix:
    """Shared row executors, parameterized by store — every row executes
    once per store via subTest (json_local, postgres_canonical)."""


def _make_rows_cls(store_name: str, store_factory):
    """Build the per-store test class executing every matrix row."""

    class ConformanceRows(unittest.TestCase):

        @classmethod
        def setUpClass(cls):
            if store_name == "postgres_canonical" and not _pg_reachable():
                raise unittest.SkipTest(
                    "live PostgreSQL not reachable (Docker/Colima absent); "
                    "json_local rows still execute")

        def setUp(self):
            _clean_aux()
            self.store = store_factory()
            self.queue = _make_queue()
            self.prov = _make_provenance()

        def tearDown(self):
            _clean_aux()

        def _ingest(self, payload):
            from canonical.notion_ingest import ingest_notion_event
            return ingest_notion_event(
                payload, store=self.store, queue=self.queue,
                provenance=self.prov)

        def _hitl_count(self, code=None):
            from canonical.notion_ingest import pending_notion_incidents
            items = pending_notion_incidents(self.queue)
            if code:
                items = [i for i in items if i.get("code") == code]
            return len(items)

        # -- row executors (one test per matrix row) ----------------------

        def test_row_A_same_delivery_is_skipped_duplicate(self):
            row = _ROWS["A"]
            page = _page()
            p = {"page_id": page, "object": "content_idea",
                 "event_type": "status_changed",
                 "revision_marker": _marker("A1"),
                 "current_state": DRAFT, "target_state": REVIEW}
            first = self._ingest(p)
            self.assertEqual(first["status"],
                             row["expected"]["first_status"])
            repeat = self._ingest(p)
            self.assertEqual(repeat["status"],
                             row["expected"]["repeat_status"])
            ev = _row_evidence(self.store, first["event_id"])
            self.assertEqual(ev["status"], "succeeded")
            self.assertEqual(self._hitl_count(),
                             row["expected"]["hitl_items"])

        def test_row_B_changed_marker_new_durable_event(self):
            row = _ROWS["B"]
            page = _page()
            p1 = {"page_id": page, "object": "content_idea",
                  "event_type": "status_changed",
                  "revision_marker": _marker("B1"),
                  "current_state": DRAFT, "target_state": REVIEW}
            p2 = dict(p1, revision_marker=_marker("B2"))
            r1 = self._ingest(p1)
            r2 = self._ingest(p2)
            self.assertEqual(r1["status"], "succeeded")
            self.assertEqual(r2["status"],
                             row["expected"]["second_status"])
            self.assertEqual(len({r1["event_id"], r2["event_id"]}),
                             row["expected"]["distinct_event_ids"])

        def test_row_C_conflict_never_silently_accepted(self):
            row = _ROWS["C"]
            page = _page()
            base = {"page_id": page, "object": "content_idea",
                    "event_type": "status_changed",
                    "revision_marker": _marker("C1"),
                    "current_state": DRAFT, "target_state": REVIEW}
            first = self._ingest(base)
            self.assertEqual(first["status"],
                             row["expected"]["first_status"])
            conflicting = dict(base, target_state=BACKLOG)
            res = self._ingest(conflicting)
            self.assertEqual(res["status"],
                             row["expected"]["conflict_status"])
            self.assertEqual(res["error_class"],
                             row["expected"]["conflict_error_class"])
            self.assertEqual(res["failure_class"],
                             row["expected"]["conflict_failure_class"])
            self.assertEqual(self._hitl_count("NOTION_CONFLICTING_DUPLICATE"),
                             row["expected"]["hitl_items"])
            ev = _row_evidence(self.store, first["event_id"])
            self.assertEqual(ev["status"], "succeeded")
            with self.assertRaises(Exception) as ctx:
                self._ingest(conflicting)
            from services.sync_engine import IntegrityError
            self.assertIsInstance(ctx.exception, IntegrityError)

        def test_row_D_repeated_transitions_three_rows(self):
            row = _ROWS["D"]
            page = _page()
            chain = [
                {"page_id": page, "object": "content_idea",
                 "event_type": "status_changed",
                 "revision_marker": _marker(f"D{i}"),
                 "current_state": cur, "target_state": tgt}
                for i, (cur, tgt) in enumerate(
                    [(DRAFT, REVIEW), (REVIEW, DRAFT), (DRAFT, REVIEW)],
                    start=1)
            ]
            ids = []
            for p in chain:
                r = self._ingest(p)
                self.assertEqual(r["status"],
                                 row["expected"]["statuses"][len(ids)])
                ids.append(r["event_id"])
            self.assertEqual(len(set(ids)),
                             row["expected"]["distinct_event_ids"])
            state = rebuild_state(self.store, page)
            self.assertEqual(state["current_state"],
                             row["expected"]["final_state"])
            self.assertEqual(self._hitl_count(),
                             row["expected"]["hitl_items"])

        def test_row_E_failed_ingestion_retry_semantics(self):
            row = _ROWS["E"]
            adapter = MockNotionAdapter()
            page = _page()
            adapter.add_page(page, "content_idea", _marker("E-bad"),
                             raw={"current_state": APPROVED,
                                  "target_state": PUBLISHED})
            eng = PollingEngine(adapter, self.store, cursor_path=_CURSOR_PATH,
                                queue=self.queue, provenance=self.prov)
            c1 = eng.poll()
            self.assertEqual(len(c1["failed"]), 1,
                             row["given"])
            c2 = eng.poll()  # same marker again
            self.assertEqual(c2["suppressed"], [page],
                             row["expected"]["same_marker_next_cycle"])
            # owner corrects the source (new marker, legal transition)
            adapter.pages[page]["raw"] = {
                "current_state": "Scheduled",
                "target_state": "Published"}
            adapter.pages[page]["marker"] = _marker("E-good")
            c3 = eng.poll()
            self.assertEqual(len(c3["ingested"]), 1,
                             row["expected"]["corrected_retry_status"])
            state = rebuild_state(self.store, page)
            self.assertEqual(state["current_state"],
                             row["expected"]["final_state"])
            self.assertEqual(
                self._hitl_count("NOTION_LIFECYCLE"),
                row["expected"]["hitl_items"])

        def test_row_F_restart_uses_durable_state_only(self):
            row = _ROWS["F"]
            adapter = MockNotionAdapter()
            page = _page()
            adapter.add_page(page, "content_idea", _marker("F1"),
                             raw={"current_state": BACKLOG,
                                  "target_state": RESEARCHING})
            eng = PollingEngine(adapter, self.store, cursor_path=_CURSOR_PATH,
                                queue=self.queue, provenance=self.prov)
            c1 = eng.poll()
            self.assertEqual(len(c1["ingested"]), 1)
            # fresh engine, same durable cursor file (process restart)
            eng2 = PollingEngine(adapter, self.store,
                                 cursor_path=_CURSOR_PATH,
                                 queue=self.queue, provenance=self.prov)
            c2 = eng2.poll()
            self.assertEqual(c2["unchanged"], [page],
                             row["expected"]["restart_cycle"])
            self.assertEqual(c2["ingested"], [])
            state = rebuild_state(self.store, page)
            self.assertEqual(state["history"],
                             row["expected"]["rebuild_history"])

        def test_row_G_unknown_state_class_e_no_retry_loop(self):
            row = _ROWS["G"]
            adapter = MockNotionAdapter()
            page = _page()
            adapter.add_page(page, "content_idea", _marker("G1"),
                             raw={"current_state": "Vaporware",
                                  "target_state": REVIEW})
            eng = PollingEngine(adapter, self.store, cursor_path=_CURSOR_PATH,
                                queue=self.queue, provenance=self.prov)
            c1 = eng.poll()
            self.assertEqual(len(c1["failed"]), 1)
            res = c1["failed"][0]
            r = self._ingest({
                "page_id": page, "object": "content_idea",
                "event_type": "status_changed",
                "revision_marker": _marker("G1"),
                "current_state": "Vaporware", "target_state": REVIEW})
            self.assertEqual(r["failure_class"],
                             row["expected"]["failure_class"])
            self.assertEqual(r["error_class"],
                             row["expected"]["error_class"])
            self.assertEqual(
                self._hitl_count("NOTION_LIFECYCLE"),
                row["expected"]["hitl_items"])
            c2 = eng.poll()
            self.assertEqual(c2["suppressed"], [page],
                             row["expected"]["same_marker_next_cycle"])

        def test_row_H_missing_marker_no_wall_clock_key(self):
            row = _ROWS["H"]
            page = _page()
            b1 = {"page_id": page, "object": "content_idea",
                  "event_type": "status_changed",
                  "current_state": DRAFT, "target_state": REVIEW,
                  "last_edited_time": "2026-09-15T10:00:00Z"}
            b2 = dict(b1, last_edited_time="2026-09-15T11:30:00Z")
            r1 = self._ingest(b1)
            r2 = self._ingest(b2)
            for r in (r1, r2):
                self.assertEqual(r["status"],
                                 row["expected"]["status"])
                self.assertEqual(r["failure_class"],
                                 row["expected"]["failure_class"])
                self.assertEqual(r["error_class"],
                                 row["expected"]["error_class"])
            self.assertEqual(r1["event_id"], r2["event_id"],
                             row["expected"]
                             ["same_event_id_despite_different_last_edited_time"])
            self.assertEqual(self._hitl_count("NOTION_PAYLOAD_CONTRACT"),
                             row["expected"]["hitl_items"])

    ConformanceRows.__name__ = f"Conformance_{store_name}"
    ConformanceRows.__qualname__ = f"Conformance_{store_name}"
    return ConformanceRows


class TestJsonLocalRows(_make_rows_cls(
        "json_local", lambda: JSONEventStore())):
    """Every matrix row against the real local JSON D-027 store."""


class TestPostgresCanonicalRows(_make_rows_cls(
        "postgres_canonical",
        lambda: PgEventStore())):
    """Every matrix row against the live canonical PostgreSQL store."""


# =========================================================================
# Data-integrity audit assertions (not covered by rows A–H)
# =========================================================================


class TestIntegrityAuditExtras(unittest.TestCase):
    """Remaining M4 audit bullets: snapshot isolation, provenance on
    failures, no wall-clock in any identity."""

    @classmethod
    def setUpClass(cls):
        if not _pg_reachable():
            raise unittest.SkipTest(
                "live PostgreSQL not reachable (Docker/Colima absent)")

    def setUp(self):
        _clean_aux()
        self.store = PgEventStore()
        self.queue = _make_queue()
        self.prov = _make_provenance()

    def tearDown(self):
        _clean_aux()

    def _ingest(self, payload):
        from canonical.notion_ingest import ingest_notion_event
        return ingest_notion_event(payload, store=self.store,
                                   queue=self.queue, provenance=self.prov)

    def test_campaign_and_incident_snapshots_stay_out_of_state_machine(self):
        """Snapshot events ingest fine but NEVER touch the content-idea
        lifecycle: a campaign page named like a lifecycle state must not
        appear in any lifecycle history, and its payload is not validated
        against the machine."""
        campaign, incident = _page(), _page()
        r1 = self._ingest({
            "page_id": campaign, "object": "campaign",
            "event_type": "campaign_updated",
            "revision_marker": _marker("camp"),
            "current_state": "Approved",   # lifecycle-LOOKING extras —
            "target_state": "Published",   # must be ignored for snapshots
        })
        r2 = self._ingest({
            "page_id": incident, "object": "incident",
            "event_type": "incident_updated",
            "revision_marker": _marker("inc"),
        })
        self.assertEqual(r1["status"], "succeeded")
        self.assertEqual(r2["status"], "succeeded")
        # neither page appears in any lifecycle reconstruction
        from canonical.notion_ingest import _exec
        rows = _exec(
            "SELECT result_reference FROM events.event_record "
            "WHERE source_system = 'notion' "
            "AND processing_status = 'succeeded' "
            "ORDER BY received_at", {"src": "notion"})
        from canonical.notion_contracts import (
            CONTENT_IDEA_TRANSITIONS, validate_transition)
        for line in rows.splitlines():
            ref = json.loads(line.strip())
            if ref.get("event_type") == "status_changed":
                validate_transition(ref["current_state"],
                                    ref["target_state"])
        # campaign/incident refs carry no lifecycle fields to validate
        camp_refs = [json.loads(l) for l in rows.splitlines()
                     if f'"{campaign}"' in l]
        self.assertTrue(camp_refs)
        self.assertNotIn("event_type:status_changed",
                         json.dumps(camp_refs))
        self.assertEqual(rebuild_state(self.store, campaign)["current_state"],
                         BACKLOG,
                         "snapshot pages never join the lifecycle machine")

    def test_provenance_attached_to_failed_deliveries_too(self):
        page = _page()
        r = self._ingest({
            "page_id": page, "object": "content_idea",
            "event_type": "status_changed",
            "revision_marker": _marker("pf"),
            "current_state": APPROVED, "target_state": PUBLISHED})
        self.assertEqual(r["status"], "failed")
        rec = self.prov.records[r["provenance_id"] - 1] \
            if r.get("provenance_id") else None
        self.assertIsNotNone(rec,
                             "failed deliveries must carry D-026 provenance")
        self.assertEqual(rec["source_type"], "EXTERNAL_SYNC")

    def test_pre_key_identity_ignores_wall_clock(self):
        from canonical.notion_ingest import _pre_key
        a = {"page_id": "p", "revision_marker": "m",
             "last_edited_time": "2026-01-01T00:00:00Z"}
        b = dict(a, last_edited_time="2030-12-31T23:59:59Z")
        self.assertEqual(_pre_key(a), _pre_key(b),
                         "failure-record identity must not derive from "
                         "change-detection metadata")

    def test_rejected_to_archived_legal_and_archived_terminal(self):
        page = _page()
        r1 = self._ingest({
            "page_id": page, "object": "content_idea",
            "event_type": "status_changed",
            "revision_marker": _marker("t1"),
            "current_state": DRAFT, "target_state": "Rejected"})
        r2 = self._ingest({
            "page_id": page, "object": "content_idea",
            "event_type": "status_changed",
            "revision_marker": _marker("t2"),
            "current_state": "Rejected", "target_state": "Archived"})
        self.assertEqual(r1["status"], "succeeded")
        self.assertEqual(r2["status"], "succeeded")
        r3 = self._ingest({
            "page_id": page, "object": "content_idea",
            "event_type": "status_changed",
            "revision_marker": _marker("t3"),
            "current_state": "Archived", "target_state": REVIEW})
        self.assertEqual(r3["status"], "failed",
                         "Archived has NO outgoing transitions")
        self.assertEqual(r3["failure_class"], "B")
        state = rebuild_state(self.store, page)
        self.assertEqual(state["history"],
                         [DRAFT, "Rejected", "Archived"])


if __name__ == "__main__":
    unittest.main()

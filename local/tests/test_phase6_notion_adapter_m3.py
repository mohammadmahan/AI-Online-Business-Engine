"""Phase 6 M3 — provider-neutral Notion adapter + polling engine tests.

Boundary discipline (RULES §35, the mock-Woo pattern): every test
crosses the boundary ONLY through NotionProvider/PollingEngine — no
test reaches into provider internals to fabricate pipeline inputs.

Offline layers (no Docker): boundary isolation, event mapping,
multi-cycle idempotency against the REAL JSON EventStore —
`PollingEngine(store=JSONEventStore)` proves the engine and adapter
against the real D-027 interface, no mocks of our own code.

Live layers (Colima/Docker): multi-cycle idempotency, persistence, and
retry semantics against the LIVE PostgreSQL D-027 store (D-055) —
zero skips while the stack is up.
"""

import json
import os
import sys
import tempfile
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
    APPROVED, BACKLOG, DRAFT, PUBLISHED, REJECTED, RESEARCHING, REVIEW,
    SCHEDULED,
)
from canonical.notion_ingest import PgEventStore  # noqa: E402
from services.notion_adapter import (  # noqa: E402
    AdapterErrorBoundary, MockNotionAdapter, NotionEvent, NotionProvider,
    PollingEngine,
)
from services.sync_engine import EventStore as JSONEventStore  # noqa: E402

_RUN_NONCE = uuid.uuid4().hex[:10]

_QUEUE_PATH = str(HERE / "fixtures" / "notion" / "_m3_queue_state.json")
_PROV_PATH = str(HERE / "fixtures" / "notion" / "_m3_provenance.json")
_CURSOR_PATH = str(HERE / "fixtures" / "notion" / "_m3_cursor.json")


def _pg_reachable() -> bool:
    import seed_registry
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
    _clean_aux()
    return VerificationQueue(queue_path=_QUEUE_PATH)


def _make_provenance():
    from services.sync_engine import ProvenanceEngine
    return ProvenanceEngine(_PROV_PATH)


def _page() -> str:
    h = uuid.uuid4().hex
    return f"{h[:8]}-{h[8:12]}-4{h[13:16]}-a{h[17:20]}-{h[20:32]}"


def _marker(tag: str) -> str:
    return f"{tag}-{_RUN_NONCE}"


def _engine(provider, store, **kw):
    # NOTE: no aux cleanup here — multi-engine tests (restart semantics)
    # and pre-built queues must survive engine construction. Each test
    # class cleans in setUp instead.
    return PollingEngine(provider, store, cursor_path=_CURSOR_PATH,
                         queue=kw.get("queue"), provenance=kw.get("provenance"))


# =========================================================================
# [1] Boundary isolation — malformed provider output (offline)
# =========================================================================


class _BrokenProvider(NotionProvider):
    """Deliberately misbehaving providers for boundary tests."""

    def __init__(self, mode: str):
        self.mode = mode

    def fetch_events(self, since=None, page_ids=None, batch_size=100):
        if self.mode == "crash":
            raise RuntimeError("adapter exploded")
        if self.mode == "not-event":
            return [object()]  # malformed output
        if self.mode == "no-marker":
            return [NotionEvent(page_id=_page(), page_kind="content_idea",
                                marker="")]
        if self.mode == "half-bad":
            return [NotionEvent(page_id=_page(), page_kind="content_idea",
                                marker=_marker("good"),
                                raw={"state": "Backlog"}),
                    "not an event",
                    NotionEvent(page_id=_page(), page_kind="content_idea",
                                marker=_marker("bad"))]
        raise AssertionError(self.mode)


class TestAdapterErrorBoundary(unittest.TestCase):
    """Malformed adapter output → structured errors, daemon never crashes,
    good events in the same batch still ingest."""

    def setUp(self):
        _clean_aux()

    def tearDown(self):
        _clean_aux()

    def test_provider_crash_is_captured(self):
        eng = _engine(_BrokenProvider("crash"), JSONEventStore())
        cycle = eng.poll()
        self.assertEqual(len(cycle["errors"]), 1)
        self.assertEqual(cycle["errors"][0]["error"], "RuntimeError")
        self.assertEqual(cycle["ingested"], [])

    def test_malformed_event_is_captured(self):
        eng = _engine(_BrokenProvider("not-event"), JSONEventStore())
        cycle = eng.poll()
        self.assertEqual(len(cycle["errors"]), 1)
        self.assertEqual(cycle["errors"][0]["error"], "malformed_event")

    def test_missing_marker_is_captured(self):
        eng = _engine(_BrokenProvider("no-marker"), JSONEventStore())
        cycle = eng.poll()
        self.assertEqual(len(cycle["errors"]), 1)
        self.assertEqual(cycle["errors"][0]["error"], "missing_marker")

    def test_half_bad_batch_still_ingests_good_pages(self):
        eng = _engine(_BrokenProvider("half-bad"), JSONEventStore())
        cycle = eng.poll()
        # the string entry is boundary-captured; BOTH well-formed events
        # (one with a state pair, one informational) still ingest —
        # malformed output never blocks good ingestion
        self.assertEqual(len(cycle["ingested"]), 2, "good pages still land")
        self.assertEqual(len(cycle["errors"]), 1, "bad one captured")
        self.assertEqual(cycle["errors"][0]["error"], "malformed_event")

    def test_missing_marker_never_reaches_the_store(self):
        store = JSONEventStore()
        eng = _engine(_BrokenProvider("no-marker"), store)
        eng.poll()
        self.assertEqual(len(store.records), 0,
                         "boundary must stop malformed events before D-027")


# =========================================================================
# [2] Offline multi-cycle idempotency against the REAL JSON EventStore
# =========================================================================


class TestOfflineCycles(unittest.TestCase):
    """The engine+adapter pair against the real D-027 interface, no Docker.
    (Live PostgreSQL parity: TestLiveCycles below.)"""

    def setUp(self):
        _clean_aux()
        self.store = JSONEventStore()
        self.adapter = MockNotionAdapter()

    def tearDown(self):
        _clean_aux()

    def test_unchanged_page_emits_nothing(self):
        page = _page()
        self.adapter.add_page(page, "content_idea", _marker("m1"),
                              raw={"current_state": "Backlog",
                                   "target_state": "Researching"})
        eng = _engine(self.adapter, self.store)
        c1 = eng.poll()
        self.assertEqual(len(c1["ingested"]), 1)
        c2 = eng.poll()
        self.assertEqual(c2["unchanged"], [page])
        self.assertEqual(c2["ingested"], [])
        self.assertEqual(len(self.store.records), 1,
                         "unchanged page ⇒ no second event AT ALL")

    def test_changed_marker_yields_new_event(self):
        page = _page()
        self.adapter.add_page(page, "content_idea", _marker("v1"),
                              raw={"state": "Backlog"})
        eng = _engine(self.adapter, self.store)
        self.assertEqual(len(eng.poll()["ingested"]), 1)
        self.adapter.simulate_transition(page, RESEARCHING, _marker("v2"))
        c2 = eng.poll()
        self.assertEqual(len(c2["ingested"]), 1, "changed marker ⇒ new event")
        self.assertEqual(len(self.store.records), 2)

    def test_campaign_and_incident_pages_flow(self):
        campaign, incident = _page(), _page()
        self.adapter.add_page(campaign, "campaign", _marker("c1"),
                              raw={"title": "کمپین پاییز"})
        self.adapter.add_page(incident, "incident", _marker("i1"),
                              raw={"incident_ref": "HITL-TEST"})
        eng = _engine(self.adapter, self.store)
        cycle = eng.poll()
        self.assertEqual(len(cycle["ingested"]), 2)
        self.assertEqual(len(self.store.records), 2)

    def test_state_file_persists_and_reload_works(self):
        with tempfile.TemporaryDirectory() as td:
            state = os.path.join(td, "state.json")
            adapter = MockNotionAdapter(state_path=state)
            adapter.add_page(_page(), "content_idea", _marker("p1"))
            with open(state, encoding="utf-8") as f:
                self.assertIn("pages", json.load(f))
            MockNotionAdapter(state_path=state)  # reload must not raise

    def test_corrupt_state_file_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            state = os.path.join(td, "state.json")
            with open(state, "w", encoding="utf-8") as f:
                f.write("[]")
            with self.assertRaises(ValueError):
                MockNotionAdapter(state_path=state)

    def test_cursor_persistence_across_engine_restart(self):
        page = _page()
        self.adapter.add_page(page, "content_idea", _marker("c"),
                              raw={"current_state": "Backlog",
                                   "target_state": "Researching"})
        eng = _engine(self.adapter, self.store)
        eng.poll()
        eng2 = _engine(self.adapter, self.store)  # fresh engine, same cursor
        self.assertEqual(eng2.poll()["unchanged"], [page],
                         "restart must not re-ingest unchanged pages")

    def test_deleted_and_timeout_pages_emit_nothing(self):
        p1, p2 = _page(), _page()
        self.adapter.add_page(p1, "content_idea", _marker("d1"))
        self.adapter.add_page(p2, "campaign", _marker("t1"))
        self.adapter.delete_page(p1)
        self.adapter.set_error(p2, "timeout")
        eng = _engine(self.adapter, self.store)
        cycle = eng.poll()
        self.assertEqual(cycle["ingested"], [])
        self.assertEqual(cycle["errors"], [])

    def test_invalid_transition_is_engine_failed_not_error(self):
        """The mock simulates the source; an illegal source-side move is a
        pipeline FAILED (durable row + HITL), not an adapter error."""
        page = _page()
        queue = _make_queue()
        # Approved→Published is illegal (must pass Scheduled): the mock
        # forges the source-side pair directly (simulation authority)
        self.adapter.add_page(page, "content_idea", _marker("s1"),
                              raw={"current_state": "Approved",
                                   "target_state": "Published"})
        result = _engine(self.adapter, self.store, queue=queue).poll()
        self.assertEqual(len(result["failed"]), 1)
        incidents = [i for i in queue.pending_items()
                     if i.get("sheet") == "notion-ingest"]
        self.assertTrue(any(i.get("code") == "NOTION_LIFECYCLE"
                            for i in incidents))
        _clean_aux()


# =========================================================================
# [3] Live: multi-cycle idempotency + persistence (PostgreSQL, D-055)
# =========================================================================


class TestLiveCycles(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if not _pg_reachable():
            raise unittest.SkipTest(
                "live PostgreSQL not reachable (Docker/Colima absent); "
                "offline engine/idempotency coverage in TestOfflineCycles")

    def setUp(self):
        _clean_aux()

    def tearDown(self):
        _clean_aux()

    def _live(self, adapter, **kw):
        from canonical.notion_ingest import PgEventStore
        return PollingEngine(adapter, PgEventStore(), cursor_path=_CURSOR_PATH,
                             queue=kw.get("queue"),
                             provenance=kw.get("provenance"))

    def test_full_lifecycle_via_polling_live(self):
        adapter = MockNotionAdapter()
        page = _page()
        adapter.add_page(page, "content_idea", _marker("L1"),
                         raw={"state": "Backlog"})
        eng = self._live(adapter)
        self.assertEqual(len(eng.poll()["ingested"]), 1)
        chain = [(RESEARCHING,), (DRAFT,), (REVIEW,), (APPROVED,),
                 (SCHEDULED,), (PUBLISHED,)]
        from canonical.notion_ingest import rebuild_state
        for i, (tgt,) in enumerate(chain, start=2):
            adapter.simulate_transition(page, tgt, _marker(f"L{i}"))
            cycle = eng.poll()
            self.assertEqual(len(cycle["ingested"]), 1, f"step {i}: {cycle}")
        state = rebuild_state(PgEventStore(), page)
        self.assertEqual(state["current_state"], PUBLISHED)
        self.assertEqual(state["history"],
                         [BACKLOG, RESEARCHING, DRAFT, REVIEW, APPROVED,
                          SCHEDULED, PUBLISHED])

    def test_multi_cycle_idempotency_live(self):
        adapter = MockNotionAdapter()
        page = _page()
        adapter.add_page(page, "content_idea", _marker("M1"),
                         raw={"state": "Backlog"})
        eng = self._live(adapter)
        c1 = eng.poll()
        self.assertEqual(len(c1["ingested"]), 1)
        c2 = eng.poll()          # unchanged
        self.assertEqual(c2["unchanged"], [page])
        self.assertEqual(c2["ingested"], [])
        adapter.simulate_transition(page, RESEARCHING, _marker("M2"))
        c3 = eng.poll()
        self.assertEqual(len(c3["ingested"]), 1)
        c4 = eng.poll()          # unchanged again
        self.assertEqual(c4["unchanged"], [page])

    def test_retry_after_ingestion_failure_advances_only_on_success(self):
        """Failed ingestions do NOT advance the cursor: a fixed source
        re-delivers on the next cycle and lands (retry semantics)."""
        adapter = MockNotionAdapter()
        page = _page()
        adapter.add_page(page, "content_idea", _marker("R1"),
                         raw={"state": "Approved"})
        # forge an illegal source-side pair the engine must surface as FAILED
        adapter.pages[page]["raw"]["current_state"] = "Approved"
        adapter.pages[page]["raw"]["target_state"] = "Published"
        eng = self._live(adapter)
        c1 = eng.poll()
        self.assertEqual(len(c1["failed"]), 1)
        # owner corrects the source (simulate a fixed page at Scheduled)
        adapter.pages[page]["raw"] = {"state": "Scheduled",
                                      "current_state": "Scheduled",
                                      "target_state": "Published"}
        adapter.pages[page]["marker"] = _marker("R2")
        c2 = eng.poll()
        self.assertEqual(len(c2["ingested"]), 1,
                         "corrected page must re-deliver (cursor not advanced)")
        from canonical.notion_ingest import rebuild_state
        self.assertEqual(rebuild_state(PgEventStore(), page)["current_state"],
                         PUBLISHED)

    def test_live_cycle_with_provenance(self):
        adapter = MockNotionAdapter()
        page = _page()
        prov = _make_provenance()
        adapter.add_page(page, "content_idea", _marker("P1"),
                         raw={"state": "Backlog"})
        eng = self._live(adapter, provenance=prov)
        cycle = eng.poll()
        self.assertEqual(len(cycle["ingested"]), 1)
        self.assertEqual(prov.records[-1]["source_type"], "EXTERNAL_SYNC")
        _clean_aux()


if __name__ == "__main__":
    unittest.main()

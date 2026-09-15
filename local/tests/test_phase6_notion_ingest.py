"""Phase 6 M2+ — live integration tests: Notion contracts wired into the
D-027 event store ingestion path (PostgreSQL canonical store).

Exercises local/canonical/notion_ingest.py end-to-end against the LIVE
engine-local-postgres container (D-055 SSOT):

  1. Full lifecycle chain Backlog → … → Published persisted as distinct
     succeeded events; rebuild_state reconstructs the position purely
     from the store (D-055 — no in-process memory).
  2. The headline regression: Draft → Review → Draft → Review writes
     EXACTLY 3 distinct event records (the refined D-060 key), plus a
     byte-identical retry that lands as skipped_duplicate with NO new
     row (the M2 suite proves distinct KEYS; this proves distinct ROWS
     persisted in the store).
  3. Contract failures (missing marker) and lifecycle violations
     (Approved → Published) fail deterministically as Class B,
     persist a durable failed row, and materialize a HITL incident
     (D-028 — never silently dropped); unknown states route Class E.
  4. D-027 conflicting duplicates (same key, different payload) are
     recorded + routed to review — never silently reprocessed.
  5. D-026 provenance: every succeeded event links an EXTERNAL_SYNC
     record; retry refreshes never touch terminal rows.

Test isolation: every payload carries a UNIQUE page_id (UUIDv4 per
run) and revision markers are stamped with a run nonce, so runs are
repeatable against the shared live database without a destructive
reset — the store only ever accumulates disjoint test events.
"""

import json
import os
import subprocess
import sys
import unittest
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOCAL = HERE.parent
ROOT = LOCAL.parent
for p in (str(LOCAL), str(LOCAL / "canonical"), str(LOCAL / "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

from canonical.notion_contracts import (  # noqa: E402
    APPROVED, ARCHIVED, BACKLOG, CLASS_B, CLASS_E, DRAFT, PUBLISHED,
    REJECTED, RESEARCHING, REVIEW, SCHEDULED,
)
from services.sync_engine import IntegrityError  # noqa: E402
import seed_registry  # noqa: E402
from canonical.notion_ingest import (  # noqa: E402
    PgEventStore,
    ingest_notion_event,
    pending_notion_incidents,
    rebuild_state,
)

# --- live-DB gate (zero-skip discipline: only Docker absence skips) -------


def _pg_reachable() -> bool:
    try:
        return seed_registry.q("SELECT 1;").strip() == "1"
    except Exception:
        return False


_RUN_NONCE = uuid.uuid4().hex[:10]

_QUEUE_PATH = str(HERE / "fixtures" / "notion" / "_live_queue_state.json")
_PROV_PATH = str(HERE / "fixtures" / "notion" / "_live_provenance.json")


def _clean_aux():
    for p in (_QUEUE_PATH, _PROV_PATH):
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
    """Fresh unique page id per call (hex/dash, contract-valid)."""
    return f"{uuid.uuid4().hex[:8]}-{uuid.uuid4().hex[:4]}-4{uuid.uuid4().hex[1:11]}-a{uuid.uuid4().hex[1:11]}-{uuid.uuid4().hex[:12]}"


def _marker(tag: str) -> str:
    return f"{tag}-{_RUN_NONCE}"


def _payload(page, *, marker, current=None, target=None,
             event_type="status_changed", obj="content_idea", **extra) -> dict:
    p = {
        "page_id": page,
        "object": obj,
        "event_type": event_type,
        "revision_marker": marker,
        "last_edited_time": "2026-09-15T09:30:00Z",  # metadata only (D-060)
    }
    if current is not None:
        p["current_state"] = current
    if target is not None:
        p["target_state"] = target
    p.update(extra)
    return p


# =========================================================================
# [1] Full lifecycle persistence + store-only reconstruction
# =========================================================================


class TestLifecyclePersistence(unittest.TestCase):
    """End-to-end: canonical contracts → validated transition → durable
    succeeded row in the live PostgreSQL event store → store-only state
    reconstruction."""

    @classmethod
    def setUpClass(cls):
        if not _pg_reachable():
            raise unittest.SkipTest(
                "live PostgreSQL not reachable (Docker/Colima absent); "
                "offline contract logic covered by test_phase6_notion_m2")
        cls.store = PgEventStore()

    def test_full_lifecycle_chain_persisted_and_rebuilt(self):
        page = _page()
        # FULL approved lifecycle from the root (Backlog) to Published —
        # rebuild's documented assumption: a page with no succeeded
        # events is at the lifecycle root.
        chain = [(BACKLOG, RESEARCHING), (RESEARCHING, DRAFT),
                 (DRAFT, REVIEW), (REVIEW, APPROVED),
                 (APPROVED, SCHEDULED), (SCHEDULED, PUBLISHED)]
        for i, (cur, tgt) in enumerate(chain, start=1):
            res = ingest_notion_event(
                _payload(page, marker=_marker(f"life{i}"),
                         current=cur, target=tgt),
                store=self.store)
            self.assertEqual(res["status"], "succeeded",
                             f"step {cur}->{tgt}: {res}")
            self.assertIsNotNone(res.get("event_id"))
        state = rebuild_state(self.store, page)
        self.assertEqual(state["current_state"], PUBLISHED)
        self.assertEqual(state["history"],
                         [BACKLOG, RESEARCHING, DRAFT, REVIEW, APPROVED,
                          SCHEDULED, PUBLISHED])

    def test_page_with_no_events_is_at_backlog(self):
        state = rebuild_state(self.store, _page())
        self.assertEqual(state["current_state"], BACKLOG)
        self.assertEqual(state["history"], [])

    def test_terminal_chain_rejected_then_archived(self):
        page = _page()
        for i, (cur, tgt) in enumerate(
                [(BACKLOG, DRAFT), (DRAFT, REJECTED),
                 (REJECTED, ARCHIVED)], start=1):
            res = ingest_notion_event(
                _payload(page, marker=_marker(f"term{i}"),
                         current=cur, target=tgt),
                store=self.store)
            self.assertEqual(res["status"], "succeeded")
        state = rebuild_state(self.store, page)
        self.assertEqual(state["history"], [BACKLOG, DRAFT, REJECTED, ARCHIVED])
        self.assertEqual(state["current_state"], ARCHIVED)


# =========================================================================
# [2] D-027 dedupe on the live store: rows, not just keys
# =========================================================================


class TestEventStoreDedup(unittest.TestCase):
    """The M2 suite proved distinct KEYS; this proves distinct PERSISTED
    ROWS and true skipped_duplicate behavior on the live store."""

    @classmethod
    def setUpClass(cls):
        if not _pg_reachable():
            raise unittest.SkipTest(
                "live PostgreSQL not reachable (Docker/Colima absent)")
        cls.store = PgEventStore()

    def _count_rows_for(self, page: str) -> int:
        # the store has no page column, so the test tracks the event
        # ids it produced (state reconstruction is exercised separately
        # via rebuild_state, which needs no id list)
        ids = getattr(self, "_ids", {}).get(page, [])
        if not ids:
            return 0
        quoted = ",".join("'" + i.replace("'", "") + "'" for i in ids)
        return int(seed_registry.q(
            "SELECT count(*) FROM events.event_record WHERE "
            f"source_system = 'notion' AND event_id IN ({quoted})"
        ).strip() or "0")

    def test_repeated_transitions_persist_exactly_three_rows(self):
        page = _page()
        ids = []
        deliveries = [
            _payload(page, marker=_marker("r1"), current=DRAFT, target=REVIEW),
            _payload(page, marker=_marker("r2"), current=REVIEW, target=DRAFT),
            _payload(page, marker=_marker("r3"), current=DRAFT, target=REVIEW),
        ]
        for p in deliveries:
            res = ingest_notion_event(p, store=self.store)
            self.assertEqual(res["status"], "succeeded")
            ids.append(res["event_id"])
        self._ids = {page: ids}
        self.assertEqual(self._count_rows_for(page), 3,
                         "each revision must be a DISTINCT persisted row "
                         "(no silent drop)")
        # all three rows terminal-succeeded
        state = rebuild_state(self.store, page)
        self.assertEqual(state["current_state"], REVIEW)

    def test_identical_retry_is_idempotent_no_new_row(self):
        page = _page()
        p = _payload(page, marker=_marker("dup"), current=DRAFT, target=REVIEW)
        first = ingest_notion_event(p, store=self.store)
        self.assertEqual(first["status"], "succeeded")
        ids = [first["event_id"]]
        self._ids = {page: ids}

        retry = ingest_notion_event(p, store=self.store)
        self.assertEqual(retry["status"], "skipped_duplicate")
        self.assertEqual(retry["event_id"], first["event_id"])
        self.assertEqual(self._count_rows_for(page), 1,
                         "identical re-delivery must NOT insert a second row")

    def test_conflicting_duplicate_never_reprocessed(self):
        page = _page()
        queue = _make_queue()
        base = _payload(page, marker=_marker("cf"), current=DRAFT,
                        target=REVIEW)
        first = ingest_notion_event(base, store=self.store)
        self.assertEqual(first["status"], "succeeded")

        # same key (same page+type+marker), different payload
        conflicting = dict(base)
        conflicting["target_state"] = BACKLOG  # different transition content

        # FIRST sighting: durably recorded + routed to review (no raise —
        # the delivery is captured, the conflict is surfaced, never silent)
        res = ingest_notion_event(conflicting, store=self.store, queue=queue)
        self.assertEqual(res["status"], "failed")
        self.assertEqual(res["error_class"], "CONFLICTING_DUPLICATE")
        incidents = pending_notion_incidents(queue)
        self.assertTrue(any(i.get("code") == "NOTION_CONFLICTING_DUPLICATE"
                            for i in incidents),
                        "conflict must materialize as a HITL item")
        # the succeeded event is untouched — no silent adoption
        state = rebuild_state(self.store, page)
        self.assertEqual(state["current_state"], REVIEW)

        # REPEAT sighting (conflict already on record): IntegrityError —
        # the caller must never mistake an unprocessed conflict for success
        with self.assertRaises(IntegrityError):
            ingest_notion_event(conflicting, store=self.store, queue=queue)
        _clean_aux()

    def test_pre_key_failures_are_deterministic_rows(self):
        page = _page()
        ids = []
        res1 = ingest_notion_event(_payload(page, marker=_marker("pk")),
                                   store=self.store)
        res2 = ingest_notion_event(_payload(page, marker=_marker("pk")),
                                   store=self.store)
        self.assertEqual(res1["status"], "failed")
        self.assertEqual(res1["error_class"], "PAYLOAD_CONTRACT")
        self.assertEqual(res2["event_id"], res1["event_id"],
                         "same failed payload ⇒ same pre-key, no dup row")
        ids.append(res1["event_id"])
        self._ids = {page: ids}
        self.assertEqual(self._count_rows_for(page), 1)


# =========================================================================
# [3] Failure semantics on the live path: Class B/E + HITL materialization
# =========================================================================


class TestFailureSemantics(unittest.TestCase):
    """Invalid rows never silently dropped (D-028): durable failed row +
    one HITL incident; unknown states → Class E (D-061 stance)."""

    @classmethod
    def setUpClass(cls):
        if not _pg_reachable():
            raise unittest.SkipTest(
                "live PostgreSQL not reachable (Docker/Colima absent)")
        cls.store = PgEventStore()

    def setUp(self):
        self.queue = _make_queue()

    def tearDown(self):
        _clean_aux()

    def test_lifecycle_violation_class_b_persisted_and_queued(self):
        page = _page()
        res = ingest_notion_event(
            _payload(page, marker=_marker("viol"),
                     current=APPROVED, target=PUBLISHED),
            store=self.store, queue=self.queue)
        self.assertEqual(res["status"], "failed")
        self.assertEqual(res["failure_class"], CLASS_B)
        self.assertEqual(res["error_class"], "LIFECYCLE")
        # durable failed row in the live store
        row = seed_registry.q(
            "SELECT processing_status || '|' || last_error_class "
            "FROM events.event_record WHERE source_system = 'notion' "
            f"AND event_id = '{res['event_id'].replace(chr(39), '')}'"
        ).strip()
        self.assertEqual(row, "failed|LIFECYCLE")
        # HITL materialization (D-028)
        incidents = pending_notion_incidents(self.queue)
        self.assertTrue(any(i.get("code") == "NOTION_LIFECYCLE"
                            and i.get("failure_class") == CLASS_B
                            for i in incidents))
        # violating event contributes NOTHING to state reconstruction
        state = rebuild_state(self.store, page)
        self.assertEqual(state["current_state"], BACKLOG)
        self.assertEqual(state["history"], [])

    def test_unknown_state_routes_class_e(self):
        page = _page()
        res = ingest_notion_event(
            _payload(page, marker=_marker("unk"),
                     current="Vaporware", target=REVIEW),
            store=self.store, queue=self.queue)
        self.assertEqual(res["status"], "failed")
        self.assertEqual(res["failure_class"], CLASS_E)
        incidents = pending_notion_incidents(self.queue)
        self.assertTrue(any(i.get("code") == "NOTION_LIFECYCLE"
                            and i.get("failure_class") == CLASS_E
                            for i in incidents))

    def test_missing_marker_class_b_contract_failure(self):
        page = _page()
        bad = _payload(page, marker=_marker("mk"))
        del bad["revision_marker"]  # only candidate field (D-060 UNVERIFIED)
        res = ingest_notion_event(bad, store=self.store, queue=self.queue)
        self.assertEqual(res["status"], "failed")
        self.assertEqual(res["failure_class"], CLASS_B)
        self.assertEqual(res["error_class"], "PAYLOAD_CONTRACT")
        self.assertTrue(any(
            i.get("code") == "NOTION_PAYLOAD_CONTRACT"
            for i in pending_notion_incidents(self.queue)))

    def test_failure_redelivery_enqueues_once(self):
        page = _page()
        bad = _payload(page, marker=_marker("idem"),
                       current=APPROVED, target=PUBLISHED)
        r1 = ingest_notion_event(bad, store=self.store, queue=self.queue)
        r2 = ingest_notion_event(bad, store=self.store, queue=self.queue)
        self.assertEqual(r1["event_id"], r2["event_id"])
        self.assertEqual(r2["error_class"], "LIFECYCLE")
        incidents = [i for i in pending_notion_incidents(self.queue)
                     if i.get("code") == "NOTION_LIFECYCLE"]
        self.assertEqual(len(incidents), 1,
                         "queue dedupe: identical failure re-delivered "
                         "must not spawn duplicate HITL items")


# =========================================================================
# [4] Provenance (D-026) linkage on the live path
# =========================================================================


class TestProvenanceLinkage(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if not _pg_reachable():
            raise unittest.SkipTest(
                "live PostgreSQL not reachable (Docker/Colima absent)")
        cls.store = PgEventStore()

    def setUp(self):
        self.prov = _make_provenance()

    def tearDown(self):
        _clean_aux()

    def test_succeeded_event_links_provenance(self):
        page = _page()
        res = ingest_notion_event(
            _payload(page, marker=_marker("prov"),
                     current=RESEARCHING, target=DRAFT),
            store=self.store, provenance=self.prov)
        self.assertEqual(res["status"], "succeeded")
        self.assertIsNotNone(res.get("provenance_id"))
        rec = self.prov.records[res["provenance_id"] - 1]
        self.assertEqual(rec["source_type"], "EXTERNAL_SYNC")
        self.assertEqual(rec["actor"], "notion-ingest")
        linkage_key = f"events.event_record::notion::{res['event_id']}::payload_hash"
        self.assertIn(linkage_key, self.prov.linkages)

    def test_skipped_duplicate_appends_no_provenance(self):
        page = _page()
        p = _payload(page, marker=_marker("provskip"),
                     current=RESEARCHING, target=DRAFT)
        first = ingest_notion_event(p, store=self.store,
                                    provenance=self.prov)
        n = len(self.prov.records)
        retry = ingest_notion_event(p, store=self.store,
                                    provenance=self.prov)
        self.assertEqual(retry["status"], "skipped_duplicate")
        self.assertEqual(len(self.prov.records), n,
                         "duplicate deliveries must not append audit rows")

    def test_ingestion_survives_unavailable_provenance_store(self):
        # provenance=None is the "audit layer unavailable" case — the
        # event itself must still persist (provenance is not the
        # ingestion transaction)
        page = _page()
        res = ingest_notion_event(
            _payload(page, marker=_marker("noprov"),
                     current=BACKLOG, target=RESEARCHING),
            store=self.store, provenance=None)
        self.assertEqual(res["status"], "succeeded")
        self.assertIsNone(res.get("provenance_id"))
        state = rebuild_state(self.store, page)
        self.assertEqual(state["current_state"], RESEARCHING)


# =========================================================================
# [5] Store-level parity with the JSON EventStore (D-027 semantics)
# =========================================================================


class TestPgStoreParity(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if not _pg_reachable():
            raise unittest.SkipTest(
                "live PostgreSQL not reachable (Docker/Colima absent)")
        cls.store = PgEventStore()

    def test_terminal_row_never_reenters(self):
        page = _page()
        p = _payload(page, marker=_marker("term2"),
                     current=BACKLOG, target=RESEARCHING)
        res = ingest_notion_event(p, store=self.store)
        self.assertEqual(res["status"], "succeeded")
        eid = res["event_id"]
        with self.assertRaises(IntegrityError):
            self.store.succeed(self.store.source_system, eid, "x")
        with self.assertRaises(IntegrityError):
            self.store.begin(self.store.source_system, eid)

    def test_retry_counts_accumulate_on_nonterminal(self):
        page = _page()
        bad = _payload(page, marker=_marker("rc"), current=APPROVED,
                       target=PUBLISHED)
        r1 = ingest_notion_event(bad, store=self.store)
        r2 = ingest_notion_event(bad, store=self.store)
        self.assertEqual(r1["event_id"], r2["event_id"])
        row = seed_registry.q(
            "SELECT retry_count FROM events.event_record WHERE "
            "source_system = 'notion' "
            f"AND event_id = '{r1['event_id'].replace(chr(39), '')}'"
        ).strip()
        self.assertEqual(int(row), 1,
                         "second delivery of a failed event = retry under "
                         "the SAME id (count 1), not a new row")


if __name__ == "__main__":
    unittest.main()

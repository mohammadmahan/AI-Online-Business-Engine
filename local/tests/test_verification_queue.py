"""Verification queue (HITL) tests — Phase 4.

Invariants: D-026 append-only decisions with provenance; D-028 review
boundary (invalid rows materialize into the queue, never silently
dropped); D-050 human-only decisions (no auto-resolve path exists);
deduplicated queueing by deterministic item key.
"""

import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL = os.path.dirname(HERE)
ROOT = os.path.dirname(LOCAL)
for p in (LOCAL, os.path.join(LOCAL, "canonical"),
          os.path.join(LOCAL, "services"),
          os.path.join(LOCAL, "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

from sync_engine import ProvenanceEngine                    # noqa: E402
import verification_tool as vt                              # noqa: E402
import import_runner as runner                              # noqa: E402


class _Env:
    """Isolated queue + provenance in a temp dir."""

    def __enter__(self):
        d = tempfile.mkdtemp(prefix="vq-")
        self.prov = ProvenanceEngine(
            path=os.path.join(d, "prov.json"))
        self.queue = vt.VerificationQueue(
            queue_path=os.path.join(d, "queue.json"),
            provenance=self.prov)
        return self.queue

    def __exit__(self, *exc):
        return False


_ITEM = {"sheet": "محصولات", "row": 5, "code": "INVALID_PRICE",
         "message": "sale >= base"}


class TestQueueBasics(unittest.TestCase):

    def test_enqueue_and_pending(self):
        with _Env() as q:
            q.enqueue(_ITEM)
            self.assertEqual(len(q.pending_items()), 1)
            item = q.load_pending()[0]
            self.assertEqual(item["code"], "INVALID_PRICE")
            self.assertIsNone(item["review_status"])
            self.assertTrue(item["queued_at"])

    def test_enqueue_is_deduplicated_for_pending_items(self):
        with _Env() as q:
            q.enqueue(_ITEM)
            again = q.enqueue(dict(_ITEM))
            self.assertTrue(again.get("dedup"))
            self.assertEqual(len(q.pending_items()), 1)

    def test_enqueue_requires_deterministic_identity(self):
        with _Env() as q:
            with self.assertRaises(ValueError):
                q.enqueue({})

    def test_enqueue_report_counts(self):
        with _Env() as q:
            res = q.enqueue_report([_ITEM, dict(_ITEM),
                                    {"sheet": "تنوع‌ها", "row": 3,
                                     "code": "DUPLICATE_SKU",
                                     "message": "P90002-BK-M"}])
            self.assertEqual(res["enqueued"], 2)
            self.assertEqual(res["deduplicated"], 1)
            self.assertEqual(res["pending"], 2)


class TestHumanDecisions(unittest.TestCase):
    """D-026 append-only decisions + D-050 human authority."""

    def test_decision_stamps_in_place_and_does_not_pop(self):
        with _Env() as q:
            q.enqueue(_ITEM)
            q.enqueue({"sheet": "تنوع‌ها", "row": 9,
                       "code": "UNKNOWN_VOCABULARY", "message": "x"})
            decided = q.review_item(0, approved=True,
                                    reviewer="owner")
            self.assertEqual(decided["review_status"], "HUMAN_VERIFIED")
            self.assertEqual(decided["reviewed_by"], "owner")
            self.assertEqual(len(q.load_pending()), 2)   # never popped
            self.assertEqual(len(q.pending_items()), 1)

    def test_decision_is_immutable(self):
        with _Env() as q:
            q.enqueue(_ITEM)
            q.review_item(0, approved=False, reviewer="owner")
            with self.assertRaises(ValueError):
                q.review_item(0, approved=True, reviewer="owner")
            self.assertEqual(
                q.load_pending()[0]["review_status"], "HUMAN_REJECTED")

    def test_index_bounds(self):
        with _Env() as q:
            with self.assertRaises(IndexError):
                q.review_item(7, approved=True, reviewer="owner")

    def test_history_is_append_only(self):
        with _Env() as q:
            q.enqueue(_ITEM)
            q.review_item(0, approved=True, reviewer="owner")
            events = [(h["event"], h.get("decision"))
                      for h in q.history()]
            self.assertEqual(events, [("enqueued", None),
                                      ("reviewed", "HUMAN_VERIFIED")])

    def test_provenance_records_queue_and_decision(self):
        with _Env() as q:
            q.enqueue(_ITEM, actor="import-runner")
            q.review_item(0, approved=True, reviewer="owner")
            types = [r["source_type"] for r in q.prov.records]
            self.assertIn("IMPORTED", types)          # enqueue provenance
            self.assertIn("HUMAN_ENTERED", types)     # decision provenance
            actors = {r["actor"] for r in q.prov.records}
            self.assertIn("owner", actors)


class TestRunnerIntegration(unittest.TestCase):
    """The D-028 closed loop: invalid rows materialize into the queue."""

    def test_fixture_review_queue_materializes(self):
        with _Env() as q:
            store_dir = tempfile.mkdtemp(prefix="vqstore-")
            store = runner.CanonicalStore(
                os.path.join(store_dir, "store.json"))
            report = runner.do_dry_run(
                runner.DEFAULT_FIXTURE, store, runner.__dict__.get(
                    "_today_for_test") or __import__(
                    "datetime").date(2026, 9, 14))
            review = [{"sheet": e.sheet, "row": e.row_index,
                       "code": e.code, "message": e.message}
                      for e in report["_wb"].errors]
            res = q.enqueue_report(review, actor="import-runner")
            self.assertEqual(res["enqueued"], 16)      # all 16 error rows
            self.assertEqual(q.pending_items(),
                             q.load_pending())         # none decided yet
            # A human rejects one, approves one — queue state advances,
            # nothing is deleted.
            q.review_item(0, approved=False, reviewer="owner")
            q.review_item(1, approved=True, reviewer="owner")
            self.assertEqual(len(q.pending_items()), 14)
            self.assertEqual(len(q.load_pending()), 16)

    def test_no_auto_resolve_path_exists(self):
        """D-050: the only way to decide is review_item(approved=...)."""
        with _Env() as q:
            q.enqueue(_ITEM)
            public = [n for n in dir(q) if not n.startswith("_")]
            for forbidden in ("auto_resolve", "auto_approve",
                              "resolve_all", "approve_all"):
                self.assertNotIn(forbidden, public)


if __name__ == "__main__":
    unittest.main()

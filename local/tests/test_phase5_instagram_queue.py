"""Phase 5 §5.2 — peak-hours Instagram publishing queue (D-172).

Contract under test: `local/canonical/instagram_publish_queue.py`

Layers:
  1. Peak-hours policy: merchant-owned windows are validated (24h,
     15-minute aligned, ordered, non-overlapping), the fixed offset is
     explicit, and the slot math is a pure deterministic function.
  2. Scheduling: only an ACCEPTED, untampered bundle may be placed; the
     slot is claimed through the REAL `SchedulingEngine` (D-094), so a
     double-booked window is a recorded conflict, never a silent pass.
  3. Release: at the injected instant a due post is enqueued into the
     REAL `InstagramOutboxPublisher` (D-072), marked DISPATCHED through
     the engine, and a repeated pass is a no-op. The queue NEVER calls
     `publish()` — the adapter seam stays with the publisher.
  4. Fail-closed: a bundle whose acceptance cannot be re-verified is
     refused at release; foreign calendar entries are never touched;
     an outbox refusal leaves the post DUE (not falsely DISPATCHED).
  5. Hygiene: AST-asserted — no network import, no adapter import, no
     credential/environment access, no `publish` call; the HITL gate is
     the SAME shared function §5.1's hand-off uses.
"""

import ast
import os
import pathlib
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
LOCAL = HERE.parent
for p in (str(LOCAL), str(LOCAL / "canonical"), str(LOCAL / "services")):
    if p not in sys.path:
        sys.path.insert(0, p)

from canonical import instagram_publish_queue as ipq  # noqa: E402
from canonical.ai_proposal_lifecycle import (  # noqa: E402
    ProposalLifecycle)
from canonical.ai_runtime import MockAiProvider, ModelRouter  # noqa: E402
from canonical.fashion_copy import FashionBrief  # noqa: E402
from canonical.fashion_social_bundler import (  # noqa: E402
    BundleNotApproved, FashionSocialBundler, MediaItem,
    SocialBundleBrief)
from canonical.fashion_trends import TrendBrief  # noqa: E402
from canonical.instagram_publisher import (  # noqa: E402
    InstagramOutboxPublisher, _JsonVault)
from canonical.scheduling_engine import (  # noqa: E402
    SchedulingEngine, _JsonSlotLocks)
from canonical.verification_tool import VerificationQueue  # noqa: E402
from services.sync_engine import EventStore, ProvenanceEngine  # noqa: E402

MODULE = LOCAL / "canonical" / "instagram_publish_queue.py"
HASH_A = "a" * 16


def _router(responses=None, fail_with=None):
    return ModelRouter({"mock": MockAiProvider(responses, fail_with=fail_with)})


def _images(count: int = 2):
    return tuple(
        MediaItem(media_ref=f"media/store/{i + 1:02d}.jpg",
                  media_hash=HASH_A if i == 0 else f"{i:016d}",
                  file_size_bytes=120_000 + i)
        for i in range(count))


def _brief(**over):
    base = dict(
        copy=FashionBrief(title="مانتو پاییزی", fabric_type="کرپ",
                          season="پاییز", notes="فرم ایستاده و دوخت تمیز"),
        trends=TrendBrief(garment_category="مانتو", season="پاییز",
                          fabric_type="کرپ"),
        images=_images(),
        telegram_chat_id=-1001234567890,
        telegram_slot="2026-10-21T18:00Z",
        instagram_slot="2026-10-21T20:00Z",
        purchase_url="https://shop.example/p/man.to",
        include_link_in_text=True,
    )
    base.update(over)
    return SocialBundleBrief(**base)


class _Harness:
    """Temp-backed REAL stack: lifecycle, scheduler, outbox, queue."""

    def __init__(self, windows=(("18:00", "21:00"),), offset=210,
                 instagram_slot="2026-10-21T20:00Z"):
        self.tmp = tempfile.mkdtemp(prefix="igq-")
        self.store_path = os.path.join(self.tmp, "events.json")
        self.prov_path = os.path.join(self.tmp, "prov.jsonl")
        self.queue_path = os.path.join(self.tmp, "queue.json")
        self.outbox_path = os.path.join(self.tmp, "outbox.json")
        self.vault_path = os.path.join(self.tmp, "vault.json")
        self.store = EventStore(self.store_path)
        prov = ProvenanceEngine(self.prov_path)
        vq = VerificationQueue(self.queue_path)
        self.lifecycle = ProposalLifecycle(
            self.store, prov, queue=vq, applier=lambda pid, ref: {"ok": True})
        self.bundler = FashionSocialBundler(_router(), lifecycle=self.lifecycle)
        # Hermetic slot ledger: the default backend would probe live PG
        # and then claim in the SHARED local volume — a test must never
        # leave a permanent calendar claim behind.
        self.scheduler = SchedulingEngine(
            EventStore(os.path.join(self.tmp, "sched.json")),
            locks=_JsonSlotLocks(os.path.join(self.tmp, "slots.json")))
        self.outbox = InstagramOutboxPublisher(
            EventStore(self.outbox_path), _JsonVault(self.vault_path))
        self.policy = ipq.PeakHoursPolicy(
            windows=windows, utc_offset_minutes=offset).validated()
        self.queue = ipq.InstagramPublishQueue(
            self.scheduler, self.outbox, self.policy)
        self._instagram_slot = instagram_slot

    def accepted(self, **over) -> str:
        brief = _brief(instagram_slot=self._instagram_slot, **over)
        report = self.bundler.bundle(brief, mode="persist")
        assert report.ok, report.errors
        self.lifecycle.decide(report.proposal_id, action="submit_review",
                              reviewer="owner", notes="checked")
        self.lifecycle.decide(report.proposal_id, action="accept",
                              reviewer="owner", notes="approved")
        return report.proposal_id

    def proposed(self, **over) -> str:
        brief = _brief(instagram_slot=self._instagram_slot, **over)
        report = self.bundler.bundle(brief, mode="persist")
        assert report.ok, report.errors
        return report.proposal_id

    def cleanup(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)


class _StubOutbox:
    """Records enqueue; has NO publish method at all."""

    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def enqueue(self, payload, *, actor="x"):
        self.calls.append((dict(payload), actor))
        if self.fail:
            raise RuntimeError("outbox refused")
        return {"queued": True, "publish_key": "k-" + payload["content_id"],
                "payload": dict(payload)}


# ===================================================================
# 1. Peak-hours policy
# ===================================================================

class PeakHoursPolicyTests(unittest.TestCase):

    def test_01_windows_are_normalised_and_sorted(self):
        p = ipq.PeakHoursPolicy(windows=(("18:00", "21:00"),
                                         ("12:00", "13:00"))).validated()
        self.assertEqual(p.windows, (("12:00", "13:00"),
                                     ("18:00", "21:00")))
        self.assertEqual(p.utc_offset_minutes, 210)

    def test_02_invalid_policies_are_refused(self):
        bad = (
            {"windows": ()},
            {"windows": (("9:00", "10:00"),)},
            {"windows": (("24:00", "25:00"),)},
            {"windows": (("18:07", "19:00"),)},
            {"windows": (("21:00", "18:00"),)},
            {"windows": (("18:00", "21:00"), ("20:00", "22:00"))},
            {"windows": (("18:00", "21:00"),), "utc_offset_minutes": 10000},
            {"windows": (("18:00", "21:00"),), "utc_offset_minutes": True},
            {"windows": (("18:00", "21:00"),), "name": "  "},
        )
        for kwargs in bad:
            with self.assertRaises(ipq.PublishingQueueError, msg=kwargs):
                ipq.PeakHoursPolicy(**kwargs).validated()

    def test_03_peak_boundaries_are_start_inclusive_end_exclusive(self):
        p = ipq.PeakHoursPolicy(windows=(("18:00", "21:00"),)).validated()
        self.assertFalse(p.is_peak("2026-10-22T17:59:00+03:30"))
        self.assertTrue(p.is_peak("2026-10-22T18:00:00+03:30"))
        self.assertTrue(p.is_peak("2026-10-22T20:59:00+03:30"))
        self.assertFalse(p.is_peak("2026-10-22T21:00:00+03:30"))
        # the same instant expressed in UTC converts into the window
        self.assertTrue(p.is_peak("2026-10-22T14:30:00+00:00"))

    def test_04_next_slot_is_pure_and_shifts_forward(self):
        p = ipq.PeakHoursPolicy(windows=(("12:00", "13:00"),
                                         ("18:00", "21:00"))).validated()
        inside = "2026-10-22T19:15:00+03:30"
        self.assertEqual(p.next_slot(inside), inside)
        self.assertEqual(p.next_slot(inside), p.next_slot(inside))
        # before the first window → that window's start
        self.assertEqual(p.next_slot("2026-10-22T08:00:00+03:30"),
                         "2026-10-22T12:00:00+03:30")
        # between windows → the next window
        self.assertEqual(p.next_slot("2026-10-22T14:00:00+03:30"),
                         "2026-10-22T18:00:00+03:30")
        # after the last window → next day, first window
        self.assertEqual(p.next_slot("2026-10-22T22:30:00+03:30"),
                         "2026-10-23T12:00:00+03:30")

    def test_05_offset_is_respected(self):
        p = ipq.PeakHoursPolicy(windows=(("18:00", "21:00"),),
                                utc_offset_minutes=210).validated()
        # 15:30Z is 19:00 in +03:30 — inside; 15:30Z in +00:00 is not
        self.assertTrue(p.is_peak("2026-10-22T15:30:00+00:00"))
        utc = ipq.PeakHoursPolicy(windows=(("18:00", "21:00"),),
                                  utc_offset_minutes=0).validated()
        self.assertFalse(utc.is_peak("2026-10-22T15:30:00+00:00"))
        self.assertEqual(utc.next_slot("2026-10-22T15:30:00+00:00"),
                         "2026-10-22T18:00:00+00:00")

    def test_06_naive_or_unparseable_instants_are_refused(self):
        p = ipq.PeakHoursPolicy(windows=(("18:00", "21:00"),)).validated()
        for bad in ("2026-10-22T18:00:00", "not-a-date", "", None, 123):
            with self.assertRaises(ipq.PublishingQueueError, msg=bad):
                p.next_slot(bad)


# ===================================================================
# 2. Scheduling through the canonical calendar
# ===================================================================

class QueueScheduleTests(unittest.TestCase):

    def setUp(self):
        self.h = _Harness()
        self.addCleanup(self.h.cleanup)

    def test_10_accepted_bundle_is_scheduled_on_a_peak_slot(self):
        bundle_id = self.h.accepted()
        res = self.h.queue.schedule_bundle(bundle_id,
                                           lifecycle=self.h.lifecycle)
        self.assertTrue(res["scheduled"])
        self.assertEqual(res["post_id"],
                         "instagram-" + bundle_id.split("|", 1)[1])
        self.assertTrue(self.h.policy.is_peak(res["scheduled_for"]))
        view = self.h.queue.calendar()
        self.assertEqual(view[res["post_id"]]["status"], "SCHEDULED")
        self.assertEqual(view[res["post_id"]]["scheduled_for"],
                         res["scheduled_for"])
        # 20:00Z is 23:30 local — outside the window, so it shifted
        self.assertTrue(res["shifted"])
        self.assertEqual(res["scheduled_for"],
                         "2026-10-22T18:00:00+03:30")

    def test_11_in_window_slot_is_kept(self):
        h = _Harness(windows=(("18:00", "21:00"),),
                     instagram_slot="2026-10-21T15:00Z")  # 18:30 local
        self.addCleanup(h.cleanup)
        bundle_id = h.accepted()
        res = h.queue.schedule_bundle(bundle_id, lifecycle=h.lifecycle)
        self.assertTrue(res["scheduled"])
        self.assertFalse(res["shifted"])
        self.assertEqual(res["scheduled_for"],
                         "2026-10-21T18:30:00+03:30")

    def test_12_unaccepted_bundle_is_refused_and_nothing_is_scheduled(self):
        bundle_id = self.h.proposed()
        with self.assertRaises(BundleNotApproved):
            self.h.queue.schedule_bundle(bundle_id, lifecycle=self.h.lifecycle)
        self.assertEqual(self.h.queue.calendar(), {})

    def test_13_replay_is_idempotent(self):
        bundle_id = self.h.accepted()
        first = self.h.queue.schedule_bundle(bundle_id,
                                             lifecycle=self.h.lifecycle)
        again = self.h.queue.schedule_bundle(bundle_id,
                                             lifecycle=self.h.lifecycle)
        self.assertTrue(first["scheduled"])
        self.assertTrue(again["scheduled"])
        self.assertTrue(again["retried"])
        self.assertEqual(len(self.h.queue.calendar()), 1)

    def test_14_double_booked_peak_slot_is_a_recorded_conflict(self):
        one = self.h.accepted()
        two = self.h.accepted(
            copy=FashionBrief(title="شال پاییزی", fabric_type="کرپ",
                              season="پاییز", notes="دوخت تمیز"),
            content_id="fashion-second")
        first = self.h.queue.schedule_bundle(one, lifecycle=self.h.lifecycle)
        second = self.h.queue.schedule_bundle(two, lifecycle=self.h.lifecycle)
        self.assertTrue(first["scheduled"])
        self.assertFalse(second["scheduled"])
        self.assertEqual(second["reason"], "SLOT_CONFLICT")
        # the winner holds the only claim; the loser's row is a conflict
        # marker (never released)
        self.assertEqual(len(self.h.scheduler.slot_history()), 1)
        self.assertTrue(self.h.queue.calendar()[
            second["post_id"]].get("slot_conflict"))


# ===================================================================
# 3. Release into the durable outbox
# ===================================================================

class QueueReleaseTests(unittest.TestCase):

    def setUp(self):
        self.h = _Harness()
        self.addCleanup(self.h.cleanup)
        self.bundle_id = self.h.accepted()
        self.scheduled = self.h.queue.schedule_bundle(
            self.bundle_id, lifecycle=self.h.lifecycle)
        self.slot = self.scheduled["scheduled_for"]

    def test_20_nothing_leaves_before_the_slot(self):
        early = self.h.queue.release_due("2026-10-22T17:00:00+03:30",
                                         lifecycle=self.h.lifecycle)
        self.assertEqual(early["dispatched"], 0)
        self.assertEqual(self.h.outbox.pending(), [])

    def test_21_due_post_reaches_the_outbox_exactly_once(self):
        first = self.h.queue.release_due(self.slot,
                                         lifecycle=self.h.lifecycle)
        self.assertEqual(first["dispatched"], 1)
        self.assertEqual(first["released"][0]["post_id"],
                         self.scheduled["post_id"])
        pending = self.h.outbox.pending()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["content_id"],
                         "fashion-مانتو-پاییزی|پاییز")
        self.assertEqual(self.h.queue.calendar()[
            self.scheduled["post_id"]]["status"], "DISPATCHED")
        # a second pass is a no-op — terminal posts are skipped
        again = self.h.queue.release_due(self.slot,
                                         lifecycle=self.h.lifecycle)
        self.assertEqual(again["dispatched"], 0)
        self.assertEqual(len(self.h.outbox.pending()), 1)

    def test_22_dispatch_is_recorded_in_the_scheduling_ledger(self):
        self.h.queue.release_due(self.slot, lifecycle=self.h.lifecycle)
        history = self.h.scheduler.slot_history()
        self.assertTrue(history)
        statuses = [ref.get("to_status") for ref in
                    self.h.scheduler._refs()]
        self.assertIn("DISPATCHED", statuses)

    def test_23_release_reverifies_acceptance_for_foreign_posts(self):
        # a post that LOOKS like a queue post but maps to no accepted
        # bundle must never reach the outbox
        key = "b" * 32
        self.h.scheduler.schedule({
            "post_id": f"instagram-{key}",
            "content_ref": f"bundle-{key}",
            "targets": ["instagram"],
            "scheduled_for": "2026-10-22T19:30:00+03:30",
        })
        res = self.h.queue.release_due("2026-10-22T19:30:00+03:30",
                                       lifecycle=self.h.lifecycle)
        refused = [f for f in res["failures"]
                   if f["post_id"] == f"instagram-{key}"]
        self.assertEqual(len(refused), 1)
        self.assertEqual(refused[0]["reason"], "not_approved")
        # only the harness bundle reached the outbox
        self.assertEqual(len(self.h.outbox.pending()), 1)
        self.assertEqual(self.h.outbox.pending()[0]["content_id"],
                         "fashion-مانتو-پاییزی|پاییز")
        self.assertEqual(self.h.queue.calendar()[
            f"instagram-{key}"]["status"], "SCHEDULED")

    def test_29_conflicted_posts_are_never_released(self):
        two = self.h.accepted(
            copy=FashionBrief(title="شال پاییزی", fabric_type="کرپ",
                              season="پاییز", notes="دوخت تمیز"),
            content_id="fashion-second")
        conflicted = self.h.queue.schedule_bundle(
            two, lifecycle=self.h.lifecycle)
        self.assertEqual(conflicted["reason"], "SLOT_CONFLICT")
        res = self.h.queue.release_due(self.slot,
                                       lifecycle=self.h.lifecycle)
        self.assertEqual(res["dispatched"], 1)
        self.assertEqual(len(self.h.outbox.pending()), 1)

    def test_24_foreign_calendar_entries_are_never_touched(self):
        self.h.scheduler.schedule({
            "post_id": "telegram-direct-1",
            "content_ref": "telegram-content",
            "targets": ["telegram"],
            "scheduled_for": "2026-10-22T18:00:00+03:30",
        })
        res = self.h.queue.release_due("2026-10-22T22:00:00+03:30",
                                       lifecycle=self.h.lifecycle)
        self.assertEqual(res["dispatched"], 1)          # only the bundle
        view = self.h.scheduler.calendar_view()
        self.assertEqual(view["telegram-direct-1"]["status"], "SCHEDULED")
        self.assertNotIn("telegram-direct-1", self.h.queue.calendar())

    def test_25_outbox_refusal_leaves_the_post_due_not_dispatched(self):
        stub = _StubOutbox(fail=True)
        queue = ipq.InstagramPublishQueue(self.h.scheduler, stub,
                                          self.h.policy)
        res = queue.release_due(self.slot, lifecycle=self.h.lifecycle)
        self.assertEqual(res["dispatched"], 0)
        self.assertEqual(res["failures"][0]["reason"], "outbox_refused")
        self.assertEqual(queue.calendar()[
            self.scheduled["post_id"]]["status"], "DUE")

    def test_26_queue_never_calls_a_publish_path(self):
        stub = _StubOutbox()
        queue = ipq.InstagramPublishQueue(self.h.scheduler, stub,
                                          self.h.policy)
        queue.release_due(self.slot, lifecycle=self.h.lifecycle)
        self.assertFalse(hasattr(stub, "publish"))
        self.assertEqual(len(stub.calls), 1)

    def test_27_cancel_is_scoped_to_queue_posts(self):
        self.assertEqual(
            self.h.queue.cancel("telegram-direct-1", "owner")["reason"],
            "foreign_post")
        cancelled = self.h.queue.cancel(self.scheduled["post_id"], "owner")
        self.assertTrue(cancelled["cancelled"])
        self.assertEqual(cancelled["status"], "CANCELLED")
        # a cancelled post cannot reach the outbox at its slot
        res = self.h.queue.release_due(self.slot, lifecycle=self.h.lifecycle)
        self.assertEqual(res["dispatched"], 0)
        self.assertEqual(self.h.outbox.pending(), [])

    def test_28_dispatched_posts_are_immutable(self):
        self.h.queue.release_due(self.slot, lifecycle=self.h.lifecycle)
        res = self.h.scheduler.cancel(self.scheduled["post_id"], "owner")
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "immutable_DISPATCHED")


# ===================================================================
# 4. Hygiene / canonical reuse
# ===================================================================

class QueueHygieneTests(unittest.TestCase):

    def setUp(self):
        self.tree = ast.parse(MODULE.read_text(encoding="utf-8"))

    def test_30_no_network_or_process_imports(self):
        banned = {"socket", "http", "urllib", "requests", "ftplib",
                  "smtplib", "subprocess", "os", "asyncio"}
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotIn(alias.name.split(".")[0], banned)
            elif isinstance(node, ast.ImportFrom):
                root = (node.module or "").split(".")[0]
                self.assertNotIn(root, banned)

    def test_31_no_adapter_or_publisher_import(self):
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                self.assertNotIn("adapter", module)
                self.assertNotIn("publisher", module)
                self.assertNotIn("instagram_live", module)

    def test_32_no_publish_call_or_credential_access(self):
        source = MODULE.read_text(encoding="utf-8")
        self.assertNotIn("environ", source)
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Call):
                fn = node.func
                name = getattr(fn, "attr", getattr(fn, "id", ""))
                self.assertNotIn(name, ("publish", "publish_container",
                                        "create_media_container"))

    def test_33_the_hitl_gate_is_the_shared_bundler_function(self):
        source = MODULE.read_text(encoding="utf-8")
        self.assertIn("approved_bundle_payload", source)
        bundler = (LOCAL / "canonical" /
                   "fashion_social_bundler.py").read_text(encoding="utf-8")
        # §5.1's hand-off delegates to the same gate rather than
        # re-implementing the refusals
        handoff = bundler.split("def hand_off_to_outbox", 1)[1]
        handoff = handoff.split("def pending_bundles", 1)[0]
        self.assertIn("approved_bundle_payload(", handoff)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

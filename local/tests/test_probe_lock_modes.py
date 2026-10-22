"""Probe-safe locking in the canonical engines (D-079 / D-094).

Contract under test:

  `canonical.orchestration_engine.FanOutEngine(..., probe=True)` and
  `canonical.scheduling_engine.SchedulingEngine(..., probe=True)` are the
  ONE probe mode for the two durable lock surfaces. A probe must never
  claim a key in live PostgreSQL or the shared JSON lock file: those
  claims are permanent, so a probe would freeze the key (fan-out) or
  poison the calendar (slot ledger) for every later real run.

Layers:

  1. Mode construction: probe is explicit, bool-only, and REFUSES an
     explicit backend (the same call must not ask for two answers).
  2. Backend identity: probe selects the canonical process-local class,
     declares its backend name, and never even PROBES the durable ones
     (the default-lock factory is patched to explode).
  3. Parity semantics: INSERT-once claims, slot conflict/holder,
     supersede/re-claim and history are identical to the durable JSON
     backends — the probe is a backend swap, not a weaker guarantee.
  4. Zero durable footprint: a full fan-out cycle and a full calendar
     cycle leave no `local/volumes/**` artifact behind.
  5. Opt-in, not replacement: an explicit JSON backend still writes its
     file, so probe mode cannot silently become the only mode.
  6. Consolidation: every live-wiring igniter exposes the canonical
     classes (aliases) and no script carries a local copy any more.
"""

import ast
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
LOCAL = HERE.parent
REPO = LOCAL.parent
for p in (str(LOCAL), str(LOCAL / "canonical"), str(LOCAL / "services"),
          str(LOCAL / "scripts"), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

from canonical import orchestration_engine as oe  # noqa: E402
from canonical import scheduling_engine as se  # noqa: E402
from canonical.orchestration_contracts import (  # noqa: E402
    OrchestrationContractError)
from canonical.scheduling_contracts import (  # noqa: E402
    SchedulingContractError)
from services.sync_engine import EventStore  # noqa: E402

FANOUT_LOCK = pathlib.Path("local/volumes/orchestration/fanout_lock.json")
SLOT_LOCK = pathlib.Path("local/volumes/scheduling/slot_locks.json")


def _payload(job_id="job-probe-1"):
    return {
        "job_id": job_id,
        "campaign_id": "camp-1",
        "content_id": "content-77",
        "text": "کفش کتانی جدید",
        "hashtags": ["mod", "new"],
        "media": {"kind": "photo", "bytes_hash": "a" * 64,
                  "aspect_ratio": "4:5", "file_size_bytes": 480_000},
        "scheduled_slot": "2026-09-16T12:00:00+00:00",
        "targets": ["instagram", "telegram"],
        "target_params": {"telegram": {"chat_id": "@myshop"}},
    }


def _bind(outcome="published"):
    return lambda ref, actor="x": {"outcome": outcome,
                                   "ref": ref.get("content_id")}


def _post(post_id="probe-post-1", slot="2026-09-27T10:07:00+00:00"):
    return {"post_id": post_id, "content_ref": f"content-{post_id}",
            "targets": ["telegram"], "scheduled_for": slot}


class _TempCwd:
    """Run a test in an empty directory so durability is observable."""

    def __enter__(self):
        self._prev = os.getcwd()
        self._dir = tempfile.TemporaryDirectory()
        os.chdir(self._dir.name)
        return pathlib.Path(self._dir.name)

    def __exit__(self, *exc):
        os.chdir(self._prev)
        self._dir.cleanup()
        return False


def _store():
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    os.remove(path)
    return path, EventStore(path)


def _cleanup(path):
    """Remove the scratch store if the test actually wrote one."""
    if os.path.exists(path):
        os.remove(path)


# ===================================================================
# Fan-out probe mode
# ===================================================================

class FanOutProbeConstructionTests(unittest.TestCase):

    def test_01_probe_selects_the_canonical_ephemeral_lock(self):
        path, store = _store()
        try:
            eng = oe.FanOutEngine(store, {"telegram": None}, probe=True)
            self.assertIs(eng.probe, True)
            self.assertEqual(eng.lock_backend, "ephemeral")
            self.assertIsInstance(eng.lock, oe.EphemeralFanOutLock)
            self.assertNotIsInstance(eng.lock, oe._PgFanOutLock)
            self.assertNotIsInstance(eng.lock, oe._JsonFanOutLock)
        finally:
            _cleanup(path)

    def test_02_probe_refuses_an_explicit_lock(self):
        path, store = _store()
        try:
            for lock in (oe.EphemeralFanOutLock(),
                         oe._JsonFanOutLock("ignored.json")):
                with self.assertRaises(oe.OrchestrationError):
                    oe.FanOutEngine(store, {"telegram": None}, lock=lock,
                                    probe=True)
        finally:
            _cleanup(path)

    def test_03_probe_must_be_a_real_bool(self):
        path, store = _store()
        try:
            for value in (1, "true", None):
                with self.assertRaises(oe.OrchestrationError):
                    oe.FanOutEngine(store, {"telegram": None}, probe=value)
        finally:
            _cleanup(path)

    def test_04_probe_never_even_probes_the_durable_lock(self):
        """The default factory tries live PG first — a probe must not."""
        path, store = _store()
        try:
            with mock.patch.object(oe, "_default_lock",
                                   side_effect=AssertionError(
                                       "probe touched the durable lock")):
                eng = oe.FanOutEngine(store, {"telegram": None}, probe=True)
            self.assertEqual(eng.lock_backend, "ephemeral")
        finally:
            _cleanup(path)


class FanOutProbeSemanticsTests(unittest.TestCase):

    def test_10_claims_are_insert_once_in_memory(self):
        lock = oe.EphemeralFanOutLock()
        self.assertTrue(lock.claim("job-a", "worker-1"))
        self.assertFalse(lock.claim("job-a", "worker-2"))
        self.assertEqual(lock._claims["job-a"], "worker-1")
        self.assertTrue(lock.claim("job-b", "worker-2"))

    def test_11_probe_cycle_routes_dispatches_and_records_durably(self):
        path, store = _store()
        try:
            eng = oe.FanOutEngine(
                store, {"telegram": _bind(), "instagram": _bind()},
                probe=True)
            r = eng.route(_payload())
            self.assertTrue(r["routed"])
            self.assertEqual(eng.state(r["job_id"]), "ROUTED")
            # the anti-race claim is live for this process
            again = eng.route(_payload())
            self.assertFalse(again["routed"])
            self.assertEqual(again["reason"], "already_claimed")
            d = eng.dispatch({"job_id": r["job_id"], "ref": r["ref"]})
            self.assertEqual(d["aggregate"], "SUCCESS")
            # the D-027 events are durable even though the lock is not
            fresh = oe.FanOutEngine(store, {"telegram": None}, probe=True)
            self.assertEqual(fresh.state(r["job_id"]), "SUCCESS")
        finally:
            _cleanup(path)

    def test_12_probe_claims_do_not_leak_between_engines(self):
        path, store = _store()
        try:
            first = oe.FanOutEngine(store, {"telegram": None}, probe=True)
            second = oe.FanOutEngine(store, {"telegram": None}, probe=True)
            self.assertTrue(first.lock.claim("job-x", "a"))
            self.assertTrue(second.lock.claim("job-x", "b"))
        finally:
            _cleanup(path)


class FanOutFootprintTests(unittest.TestCase):

    def test_20_probe_cycle_leaves_no_volume_artifact(self):
        with _TempCwd() as tmp:
            path = tmp / "events.json"
            eng = oe.FanOutEngine(
                EventStore(str(path)), {"telegram": _bind()}, probe=True)
            routed = eng.route(_payload())
            eng.dispatch({"job_id": routed["job_id"], "ref": routed["ref"]})
            self.assertFalse((tmp / FANOUT_LOCK).exists())
            self.assertEqual(sorted(p.name for p in tmp.iterdir()),
                             ["events.json"])

    def test_21_explicit_json_backend_still_writes_its_file(self):
        with _TempCwd() as tmp:
            lock_path = tmp / "locks.json"
            eng = oe.FanOutEngine(
                EventStore(str(tmp / "events.json")), {"telegram": _bind()},
                lock=oe._JsonFanOutLock(str(lock_path)))
            self.assertEqual(eng.lock_backend, "json")
            self.assertTrue(eng.route(_payload())["routed"])
            self.assertTrue(lock_path.exists())


# ===================================================================
# Scheduling probe mode
# ===================================================================

class SchedulingProbeConstructionTests(unittest.TestCase):

    def test_30_probe_selects_the_canonical_ephemeral_backend(self):
        path, store = _store()
        try:
            eng = se.SchedulingEngine(store, probe=True)
            self.assertIs(eng.probe, True)
            self.assertEqual(eng.lock_backend, "ephemeral")
            self.assertIsInstance(eng._locks, se.EphemeralSlotLocks)
            self.assertNotIsInstance(eng._locks, se._PgSlotLocks)
            self.assertNotIsInstance(eng._locks, se._JsonSlotLocks)
        finally:
            _cleanup(path)

    def test_31_probe_refuses_an_explicit_backend(self):
        path, store = _store()
        try:
            for locks in (se.EphemeralSlotLocks(),
                          se._JsonSlotLocks("ignored.json")):
                with self.assertRaises(SchedulingContractError):
                    se.SchedulingEngine(store, locks=locks, probe=True)
        finally:
            _cleanup(path)

    def test_32_probe_must_be_a_real_bool(self):
        path, store = _store()
        try:
            for value in (1, "true", None):
                with self.assertRaises(SchedulingContractError):
                    se.SchedulingEngine(store, probe=value)
        finally:
            _cleanup(path)

    def test_33_probe_never_even_probes_the_durable_backend(self):
        path, store = _store()
        try:
            with mock.patch.object(se, "default_slot_locks",
                                   side_effect=AssertionError(
                                       "probe touched the slot ledger")):
                eng = se.SchedulingEngine(store, probe=True)
            self.assertEqual(eng.lock_backend, "ephemeral")
        finally:
            _cleanup(path)


class SchedulingProbeSemanticsTests(unittest.TestCase):

    def test_40_slot_conflict_names_the_holder(self):
        path, store = _store()
        try:
            eng = se.SchedulingEngine(store, probe=True)
            self.assertEqual(eng.schedule(_post())["status"], "SCHEDULED")
            clash = eng.schedule(_post(post_id="probe-post-2"))
            self.assertEqual(clash["status"], "SLOT_CONFLICT")
            self.assertEqual(clash["conflicts"][0]["held_by"],
                             "probe-post-1")
            # the conflicting post has NO slot: the calendar records the
            # rejection on its row and the ledger holds only the winner
            view = eng.calendar_view()
            self.assertTrue(view["probe-post-2"].get("slot_conflict"))
            self.assertEqual(list(eng.slot_history()), [
                se.slot_lock_key("telegram", "2026-09-27T10:07:00+00:00")])
        finally:
            _cleanup(path)

    def test_41_replay_is_idempotent(self):
        path, store = _store()
        try:
            eng = se.SchedulingEngine(store, probe=True)
            eng.schedule(_post())
            again = eng.schedule(_post())
            self.assertTrue(again.get("retried"))
            self.assertEqual(again["status"], "SCHEDULED")
        finally:
            _cleanup(path)

    def test_42_reschedule_supersedes_the_old_slot_in_history(self):
        path, store = _store()
        try:
            eng = se.SchedulingEngine(store, probe=True)
            eng.schedule(_post())
            new_slot = "2026-09-27T10:22:00+00:00"
            moved = eng.reschedule("probe-post-1", new_slot, "probe")
            self.assertTrue(moved["ok"])
            history = eng.slot_history()
            old_key = se.slot_lock_key(
                "telegram", "2026-09-27T10:07:00+00:00")
            new_key = se.slot_lock_key("telegram", new_slot)
            self.assertFalse(history[old_key]["active"])
            self.assertTrue(history[new_key]["active"])
            self.assertEqual(history[new_key]["post_id"], "probe-post-1")
        finally:
            _cleanup(path)

    def test_43_probe_backends_do_not_leak_between_engines(self):
        path, store = _store()
        try:
            se.SchedulingEngine(store, probe=True).schedule(_post())
            second = se.SchedulingEngine(store, probe=True)
            self.assertEqual(second.slot_history(), {})
        finally:
            _cleanup(path)


class SchedulingFootprintTests(unittest.TestCase):

    def test_50_probe_cycle_leaves_no_volume_artifact(self):
        with _TempCwd() as tmp:
            eng = se.SchedulingEngine(
                EventStore(str(tmp / "events.json")), probe=True)
            eng.schedule(_post())
            eng.schedule(_post(post_id="probe-post-2",
                               slot="2026-09-27T10:22:00+00:00"))
            self.assertFalse((tmp / SLOT_LOCK).exists())
            self.assertEqual(sorted(p.name for p in tmp.iterdir()),
                             ["events.json"])

    def test_51_explicit_json_backend_still_writes_its_file(self):
        with _TempCwd() as tmp:
            lock_path = tmp / "slots.json"
            eng = se.SchedulingEngine(
                EventStore(str(tmp / "events.json")),
                locks=se._JsonSlotLocks(str(lock_path)))
            self.assertEqual(eng.lock_backend, "json")
            eng.schedule(_post())
            self.assertTrue(lock_path.exists())


# ===================================================================
# Consolidation: igniters carry aliases, not copies
# ===================================================================

class ConsolidationTests(unittest.TestCase):

    def test_60_igniters_expose_the_canonical_classes(self):
        from live_wiring_phase10_igniter import (
            _EphemeralFanOutLock as p10)
        from live_wiring_phase11_igniter import (
            _EphemeralFanOutLock as p11)
        from live_wiring_phase12_igniter import (
            _EphemeralFanOutLock as p12)
        from live_wiring_phase14_igniter import (
            _EphemeralFanOutLock as p14,
            _EphemeralSlotLocks as s14)
        for alias in (p10, p11, p12, p14):
            self.assertIs(alias, oe.EphemeralFanOutLock)
        self.assertIs(s14, se.EphemeralSlotLocks)

    def test_61_no_script_keeps_a_local_copy(self):
        offenders = []
        for path in (LOCAL / "scripts").glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and node.name in (
                        "_EphemeralFanOutLock", "_EphemeralSlotLocks"):
                    offenders.append(f"{path.name}:{node.lineno}")
        self.assertEqual(offenders, [])

    def test_62_igniters_build_the_probe_mode_not_an_injected_lock(self):
        builders = ("live_wiring_phase11_igniter.py",
                    "live_wiring_phase12_igniter.py",
                    "live_wiring_phase14_igniter.py")
        for name in builders:
            source = (LOCAL / "scripts" / name).read_text(encoding="utf-8")
            self.assertIn("probe=True", source, name)
        for name in ("live_wiring_phase10_igniter.py",) + builders:
            source = (LOCAL / "scripts" / name).read_text(encoding="utf-8")
            self.assertNotIn("lock=_EphemeralFanOutLock()", source, name)

    def test_63_phase14_refuses_a_durable_slot_backend_before_the_cycle(self):
        source = (LOCAL / "scripts" /
                  "live_wiring_phase14_igniter.py").read_text(
                      encoding="utf-8")
        self.assertIn(
            "if not isinstance(self._slot_locks, _EphemeralSlotLocks):",
            source)
        self.assertIn("durable lock claims", source)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

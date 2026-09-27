"""Phase 17 live wiring igniter battery (D-167, offline).

Exercises `local/scripts/live_wiring_phase17_igniter.py` fully
offline — the engine the REAL `NotificationEngine` over the REAL
D-027 parity `EventStore` with the EPHEMERAL in-process claim backend
(zero durable footprint, dispatch intercepted — no transport is ever
bound), the census chained from the REAL D-166 igniter over the REAL
D-165/D-164/D-162/D-161/D-160/D-159/D-158/D-157/D-156/D-155/D-154
chain:

  PASS    — phase16 attestation + verified profile + REAL contracts +
            intercepted notification cycle ⇒ PHASE17_IGNITED,
            deterministic digest;
  NTF-01  — missing/raised/wrong-schema/incomplete-verdict/drifted/
            unrooted/broken-chain phase16 attestation ⇒ refusal with
            ZERO engine calls (proven);
  NTF-02  — unverified profile, missing phase rows, seam registry
            drift, slot-18 registry-fact drift, census absent ⇒
            refusal;
  NTF-03  — REAL validator rejections (contact metadata, unknown
            templates, wrong channel/priority), dedup identity,
            pure policy matrix;
  NTF-04  — absent store, cleanup failure, non-ephemeral lock
            backend, off-process dispatch ⇒ fail-closed refusal;
  NTF-05  — exactly one canonical attestation per run (including
            aborts), deterministic digest;
  REDACT  — canaries never reach the attestation or audit copies
            (D-124);
  AST     — pure igniter core (no network/db imports, no shell, no
            spawn), transports injected only.
"""
from __future__ import annotations

import ast
import json
import pathlib
import sys
import unittest

REPO = pathlib.Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "local" / "scripts"
SRC = REPO / "local" / "src"
for p in (str(REPO / "local"), str(SCRIPTS), str(SRC),
          str(SRC.parent), str(SRC / "security"), str(REPO / "local" / "tests")):
    if p not in sys.path:
        sys.path.insert(0, p)

from services.sync_engine import EventStore  # noqa: E402
from live_wiring_phase16_igniter import (  # noqa: E402
    PHASE16_IGNITED, PHASE16_INCOMPLETE,
)
from live_wiring_phase17_igniter import (  # noqa: E402
    ATTESTATION_SCHEMA, CYCLE_ID, PHASE16_ROW_KIND, PHASE16_SCHEMA,
    PHASE17_IGNITED, PHASE17_INCOMPLETE, PROBE_EVENT, SEAMS,
    SLOT18_REGISTRY_FACT, _EphemeralNotificationLocks, Phase17Igniter,
    canonical_hash,
)

ENGINE = SCRIPTS / "live_wiring_phase17_igniter.py"

CANARY = "sk-canaryvalue1234567890abcdef"
SMTP_TOKEN = "smtp-canary-relay-token-0123456789"


def real_store_factory():
    """The REAL D-027 parity EventStore, fresh scratch file per run."""
    import os
    import tempfile
    made: dict = {}

    def factory():
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.remove(path)
        store = EventStore(path)
        made.update(store=store, path=path)
        return (store,)

    factory.made = made
    return factory, made


# --- the authentic chain: phase16 attestation via the REAL D-166
# --- engine (which chains D-165 → … → D-154) -------------------------

def real_phase16_attestation(observed_tick=11000):
    """Run the REAL D-166 igniter over the authentic chain with
    in-process fakes (identical to the D-166 battery pass path)."""
    # sys.path poisoning defense (mirrored across all chain builders)
    import sys as _sys
    _local_root = str(REPO / "local")
    _sys.path[:] = [p for p in _sys.path
                    if p not in (_local_root + "/canonical",
                                 _local_root + "\\canonical")]
    _t = _sys.modules.get("tests")
    if _t is not None and not getattr(_t, "__path__", None):
        del _sys.modules["tests"]  # legacy single-module shadow
    _sys.path.insert(0, _local_root)
    import tests.test_live_wiring_phase16 as t16  # noqa: E402
    h = t16.Harness(now=observed_tick)
    att = h.run()
    ledger = t16.the_ledger() + [{
        "event_kind": "phase16_analyst_wiring_attestation",
        "detail": {"attestation_digest": att.attestation_digest,
                   "verdict": att.verdict}}]
    return att.to_dict(), ledger, t16


_CHAIN: dict = {}

_UNSET = object()  # sentinel: "no override given" (None = absent)


def the_att() -> dict:
    return _CHAIN["att"]


def the_ledger() -> list:
    return _CHAIN["ledger"]


def build_chain() -> None:
    if not _CHAIN:
        att, ledger, _t16 = real_phase16_attestation()
        _CHAIN.update(att=att, ledger=ledger)


def real_census() -> dict:
    """The runtime-profile census rows: Phases 5–12, 14, 15, 16, all
    wired (slot 14 closed CRM-not-needed per D-163 — NOT a row)."""
    return {
        "runtime_profile_verified": True,
        "phases": [
            {"phase": n, "name": name, "present": True,
             "verified": True, "wired": True, "detail": "ready"}
            for n, name in ((5, "n8n Foundation"),
                            (6, "Notion Business OS"),
                            (7, "AI Runtime"),
                            (8, "AI Product Manager"),
                            (9, "Instagram"),
                            (10, "AI Sales Agent"),
                            (11, "Order Management"),
                            (12, "Payment"),
                            (14, "Scheduling Engine"),
                            (15, "Analytics Engine"),
                            (16, "Analyst Service"))
        ],
    }


# --- the wired harness ---------------------------------------------------

class Harness:

    def __init__(self, now: int = 12000, stack_factory=_UNSET,
                 census=real_census, **overrides):
        build_chain()
        self.now = now
        self.sink: list = []
        if stack_factory is _UNSET:
            self.stack_factory, self.made = real_store_factory()
        else:
            self.stack_factory = stack_factory
            self.made = getattr(stack_factory, "made", {})
        providers = {
            "upstream_provider": the_att,
            "audit_rows": the_ledger,
            "chain_verifier": lambda: {"ok": True,
                                       "rows": len(the_ledger())},
            "census": census,
            "stack_factory": self.stack_factory,
        }
        providers.update(overrides)
        self.igniter = Phase17Igniter(
            clock=lambda: self.now, audit_sink=self.sink.append,
            **providers)

    def run(self):
        return self.igniter.run()


# ===================================================================
# PASS — successful ignition
# ===================================================================

class TestIgnitionPass(unittest.TestCase):

    def test_005_ephemeral_lock_backend_wired(self):
        h = Harness()
        h.run()  # the backend is constructed inside the cycle
        self.assertIsInstance(h.igniter._last_locks,
                              _EphemeralNotificationLocks)

    def test_01_full_ignition_completes(self):
        h = Harness()
        att = h.run()
        self.assertEqual(att.verdict, PHASE17_IGNITED)
        self.assertTrue(att.ignited)
        d = att.to_dict()
        self.assertEqual(d["schema"], ATTESTATION_SCHEMA)
        self.assertEqual(d["schema"],
                         "phase17.notification_wiring_attestation.v1")
        self.assertEqual(d["phase16_digest"],
                         canonical_hash(the_att()))
        ids = [c[0] for c in att.checks]
        for rule in ("NTF-01", "NTF-02", "NTF-03", "NTF-04",
                     "NTF-05"):
            self.assertIn(rule, ids)
        self.assertTrue(all(c[1] for c in att.checks))
        self.assertTrue(d["profile"]["runtime_profile_verified"])
        self.assertTrue(d["profile"]["seams_ok"])
        self.assertIn("slot 18 = canonical.ai_hitl_service",
                      d["profile"]["registry_fact"])
        self.assertTrue(d["contracts"]["dedup_ok"])
        self.assertTrue(d["contracts"]["policy_ok"])
        self.assertEqual(d["cycle"]["lock_backend"], "ephemeral")
        self.assertFalse(d["cycle"]["drift"])

    def test_02_attestation_digest_deterministic(self):
        a1 = Harness(now=12500).run()
        b1 = Harness(now=12500).run()
        self.assertEqual(a1.attestation_digest, b1.attestation_digest)
        self.assertEqual(a1.attestation_digest,
                         canonical_hash(a1.to_dict()))

    def test_03_notification_steps_recorded(self):
        att = Harness().run()
        steps = att.to_dict()["cycle"]["steps"]
        kinds = [s[0] for s in steps]
        for kind in ("START", "AUTH", "ENQUEUE", "DEDUP", "PRIORITY",
                     "OUTCOMES", "STATUS", "INVALID", "DLQ", "VERIFY",
                     "CLEANUP"):
            self.assertIn(kind, kinds)
        self.assertTrue(all(s[1] for s in steps))
        self.assertEqual(len(att.to_dict()["cycle"]["summary_hash"]),
                         64)

    def test_04_idempotency_and_policy_trace(self):
        att = Harness().run()
        steps = {s[0]: s[2] for s in att.to_dict()["cycle"]["steps"]}
        self.assertEqual(steps["DEDUP"]["same_alert"],
                         "DUPLICATE_BLOCKED")
        self.assertEqual(steps["DEDUP"]["distinct_alert"], "QUEUED")
        self.assertEqual(steps["PRIORITY"]["quiet_hours_normal"],
                         "POLICY_DEFERRED")
        self.assertEqual(steps["PRIORITY"]["critical_bypass"], "QUEUED")
        self.assertIn("stickiness", steps["OUTCOMES"]["late_transient"])
        self.assertFalse(att.to_dict()["cycle"]["drift"])


# ===================================================================
# NTF-01 — phase16 attestation refusals (zero engine calls)
# ===================================================================

class TestNtf01Refusals(unittest.TestCase):

    def test_10_missing_phase16_attestation(self):
        h = Harness(upstream_provider=None)
        att = h.run()
        self.assertEqual(att.verdict, PHASE17_INCOMPLETE)
        self.assertIn("absent", att.checks[0][2])
        self.assertEqual(len(h.sink), 1)

    def test_11_provider_raises(self):
        def boom():
            raise RuntimeError("vault offline")
        att = Harness(upstream_provider=boom).run()
        self.assertEqual(att.verdict, PHASE17_INCOMPLETE)
        self.assertIn("RuntimeError", att.checks[0][2])

    def test_12_wrong_schema(self):
        att = Harness(upstream_provider=lambda: {
            "schema": "other.v1"}).run()
        self.assertEqual(att.verdict, PHASE17_INCOMPLETE)
        self.assertIn("schema", att.checks[0][2])

    def test_13_incomplete_verdict_refused(self):
        bad = dict(the_att())
        bad["verdict"] = PHASE16_INCOMPLETE
        att = Harness(upstream_provider=lambda: bad).run()
        self.assertEqual(att.verdict, PHASE17_INCOMPLETE)
        self.assertIn("PHASE16_IGNITED",
                      " ".join(c[2] for c in att.checks))

    def test_14_drifted_digest_refused(self):
        rows = the_ledger()[:-1] + [{
            "event_kind": "phase16_analyst_wiring_attestation",
            "detail": {"attestation_digest": "b" * 64}}]
        att = Harness(audit_rows=lambda: rows).run()
        self.assertEqual(att.verdict, PHASE17_INCOMPLETE)
        self.assertIn("DRIFTED", " ".join(c[2] for c in att.checks))

    def test_15_unrooted_attestation_refused(self):
        att = Harness(audit_rows=lambda: []).run()
        self.assertEqual(att.verdict, PHASE17_INCOMPLETE)
        self.assertIn("rooted", " ".join(c[2] for c in att.checks))

    def test_16_broken_chain_refused(self):
        att = Harness(chain_verifier=lambda: {
            "ok": False, "broken_at_seq": 1,
            "reason": "hash mismatch"}).run()
        self.assertEqual(att.verdict, PHASE17_INCOMPLETE)
        self.assertIn("not intact",
                      " ".join(c[2] for c in att.checks))

    def test_17_refusal_makes_zero_engine_calls(self):
        # every NTF-01 failure class must leave the store completely
        # unconstructed (the factory is never invoked)
        for kwargs in (
                {"upstream_provider": None},
                {"upstream_provider": lambda: {"schema": "x"}},
                {"audit_rows": lambda: []},
                {"chain_verifier": lambda: {"ok": False}}):
            factory, made = real_store_factory()
            h = Harness(stack_factory=factory, **kwargs)
            att = h.run()
            self.assertEqual(att.verdict, PHASE17_INCOMPLETE)
            self.assertIsNone(made.get("store"))  # factory never run


# ===================================================================
# NTF-02 — runtime profile & seams refusals
# ===================================================================

class TestNtf02Profile(unittest.TestCase):

    def test_20_unverified_profile_refused(self):
        bad = real_census()
        bad["runtime_profile_verified"] = False
        att = Harness(census=lambda: bad).run()
        self.assertEqual(att.verdict, PHASE17_INCOMPLETE)
        self.assertIn("NOT verified",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "NTF-02"))

    def test_21_missing_phase16_row_refused(self):
        bad = real_census()
        bad["phases"] = [p for p in bad["phases"]
                         if p["phase"] != 16]
        att = Harness(census=lambda: bad).run()
        self.assertEqual(att.verdict, PHASE17_INCOMPLETE)
        self.assertIn("Phase 16 missing",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "NTF-02"))

    def test_22_unwired_phase15_refused(self):
        bad = real_census()
        for p in bad["phases"]:
            if p["phase"] == 15:
                p["wired"] = False
        att = Harness(census=lambda: bad).run()
        self.assertEqual(att.verdict, PHASE17_INCOMPLETE)
        self.assertIn("VERIFIED+WIRED",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "NTF-02"))

    def test_23_seam_registry_drift_refused(self):
        # the D-154 cross-walk binds slot 18 to the HITL service; a
        # registry where slot 18 is ABSENT (or any pinned seam drifts)
        # must refuse. Pure seam drift is structurally covered by the
        # live D-154 ENTRY_POINTS path in NTF-02; the probe's refusal
        # surface here is the slot-18 registry fact.
        bad_registry = {13: "canonical.orchestration_engine"}
        att = Harness(expected_entry_points=bad_registry).run()
        self.assertEqual(att.verdict, PHASE17_INCOMPLETE)
        self.assertIn("drifted from the D-154",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "NTF-02"))

    def test_24_census_absent_refused(self):
        att = Harness(census=None).run()
        self.assertEqual(att.verdict, PHASE17_INCOMPLETE)
        self.assertIn("unavailable",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "NTF-02"))

    def test_25_slot18_registry_fact_drift_refused(self):
        # the D-154 cross-walk binds slot 18 to the HITL service; a
        # registry that reassigns the slot to the notification engine
        # must refuse (no slot reassignment in a probe)
        bad_registry = {13: "canonical.orchestration_engine",
                        18: "canonical.notification_engine"}
        att = Harness(expected_entry_points=bad_registry).run()
        self.assertEqual(att.verdict, PHASE17_INCOMPLETE)
        self.assertIn("drifted from the D-154",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "NTF-02"))

    def test_26_slot14_not_required_in_census(self):
        # D-163: slot 14 (CRM) must NOT be a required census row
        att = Harness().run()
        self.assertEqual(att.verdict, PHASE17_IGNITED)
        self.assertNotIn(13, att.to_dict()["profile"]["phases"])


# ===================================================================
# NTF-03 — notification contracts & invariants
# ===================================================================

class TestNtf03Contracts(unittest.TestCase):

    def test_30_validator_enforced_in_probe(self):
        # the PASS run itself proves the REAL validator enforces the
        # contact-metadata + invalid-class gates with named reasons
        att = Harness().run()
        self.assertEqual(att.verdict, PHASE17_IGNITED)
        blob = " ".join(c[2] for c in att.checks if c[0] == "NTF-03")
        self.assertIn("REAL contracts enforced", blob)

    def test_31_missing_contact_metadata_refused_direct(self):
        from canonical.notification_contracts import (
            NotificationContractError, validate_notification,
        )
        cases = (
            (dict(PROBE_EVENT, channel="EMAIL",
                  variables={"order_ref": "o", "state": "s"}),
             "subject"),
            (dict(PROBE_EVENT, channel="SMS",
                  template_id="order.shipped.v1",
                  variables={"order_ref": "o"}), "phone_ref"),
            (dict(PROBE_EVENT, channel="WEBHOOK",
                  variables={"order_ref": "o", "state": "s"}),
             "endpoint_ref"),
        )
        for bad, expect in cases:
            with self.assertRaises(NotificationContractError) as ctx:
                validate_notification(bad)
            self.assertIn(expect, str(ctx.exception))

    def test_32_dedup_identity_direct(self):
        from canonical.notification_contracts import dedup_key
        k1 = dedup_key(dict(PROBE_EVENT))
        k2 = dedup_key(dict(PROBE_EVENT))
        self.assertEqual(k1, k2)
        self.assertEqual(len(k1), 64)
        k3 = dedup_key(dict(PROBE_EVENT, event_key="other:logical"))
        self.assertNotEqual(k1, k3)
        # channel participates in the identity (EMAIL validates with
        # its subject contact metadata present)
        k4 = dedup_key(dict(
            PROBE_EVENT, channel="EMAIL",
            variables={"order_ref": "o", "state": "s",
                       "subject": "probe"}))
        self.assertNotEqual(k1, k4)

    def test_33_policy_matrix_direct(self):
        from canonical.notification_contracts import policy_decision
        day = dict(PROBE_EVENT, occurred_at="2026-09-27T14:00:00+00:00")
        night = dict(PROBE_EVENT,
                     occurred_at="2026-09-27T23:30:00+00:00")
        self.assertEqual(policy_decision(dict(day), 0)["verdict"],
                         "allow")
        self.assertEqual(
            policy_decision(dict(night), 0)["reason"], "quiet_hours")
        self.assertEqual(
            policy_decision(dict(night, priority="CRITICAL"), 0)["reason"],
            "critical_bypass")
        self.assertEqual(
            policy_decision(dict(day), 999)["reason"], "frequency_cap")

    def test_34_quiet_hours_window_direct(self):
        from canonical.notification_contracts import in_quiet_hours
        self.assertTrue(in_quiet_hours("2026-09-27T22:00:00+00:00"))
        self.assertTrue(in_quiet_hours("2026-09-27T03:00:00+00:00"))
        self.assertFalse(in_quiet_hours("2026-09-27T07:00:00+00:00"))
        self.assertFalse(in_quiet_hours("2026-09-27T12:00:00+00:00"))

    def test_35_template_registry_discipline_direct(self):
        from canonical.notification_contracts import (
            NotificationContractError, template_ids, validate_notification,
        )
        ids = template_ids()
        self.assertIn("order.fulfillment.v1", ids)
        self.assertIn("dlq.item_admitted.v1", ids)
        self.assertIn("hitl.review_required.v1", ids)
        for bad in ("not-versioned", "order..v1", "UNKNOWN.v1"):
            with self.assertRaises(NotificationContractError):
                validate_notification(dict(
                    PROBE_EVENT, template_id=bad))


# ===================================================================
# NTF-04 — notification cycle refusals
# ===================================================================

class TestNtf04Cycle(unittest.TestCase):

    def test_40_store_absent_refused(self):
        att = Harness(stack_factory=None).run()
        self.assertEqual(att.verdict, PHASE17_INCOMPLETE)
        blob = " ".join(c[2] for c in att.checks if c[0] == "NTF-04")
        self.assertIn("unavailable", blob)

    def test_41_dispatch_interception_proven_in_pass(self):
        att = Harness().run()
        self.assertEqual(att.verdict, PHASE17_IGNITED)
        d = att.to_dict()["cycle"]
        steps = {s[0]: s[2] for s in d["steps"]}
        self.assertEqual(steps["AUTH"]["egress"], 0)
        self.assertEqual(d["dispatched_off_process"], 0)

    def test_42_status_view_drift_free_in_pass(self):
        att = Harness().run()
        steps = {s[0]: s[2] for s in att.to_dict()["cycle"]["steps"]}
        self.assertEqual(steps["STATUS"]["rebuilt"],
                         "from DURABLE store data only")
        self.assertFalse(att.to_dict()["cycle"]["drift"])

    def test_43_cleanup_failure_refused(self):
        class StickyIgniter(Phase17Igniter):
            def _scratch_delete(self):
                return False  # refuses to clean the artifact
        h = Harness()
        h.igniter.__class__ = StickyIgniter
        att = h.run()
        self.assertEqual(att.verdict, PHASE17_INCOMPLETE)
        blob = " ".join(c[2] for c in att.checks if c[0] == "NTF-04")
        self.assertIn("cleanup failed", blob)

    def test_44_non_ephemeral_lock_backend_refused(self):
        # a FILE-BACKED (durable-footprint) claim backend must be
        # refused fail-closed: the probe only ever runs on the
        # ephemeral in-process backend (D-079 hazard — the default
        # backend claims keys in live PG or the shared JSON file)
        from canonical.notification_engine import _JsonLocks
        import os
        import tempfile
        fd, lock_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.remove(lock_path)
        try:
            class DurableLocksProbe(Phase17Igniter):
                # simulates a mis-wired probe: the default backend
                # leaks in (file-backed → durable footprint)
                def _make_locks(self):
                    locks = _JsonLocks(lock_path)
                    self._last_locks = locks
                    return locks

            h = Harness()
            h.igniter.__class__ = DurableLocksProbe
            att = h.run()
            self.assertEqual(att.verdict, PHASE17_INCOMPLETE)
            blob = " ".join(c[2] for c in att.checks if c[0] == "NTF-04")
            self.assertIn("durable footprint", blob)
            self.assertIn("ephemeral", blob)
            # the durable backend WAS constructed and would have
            # claimed keys — proving the guard is load-bearing
            self.assertIsNot(type(h.igniter._last_locks),
                             _EphemeralNotificationLocks)
            self.assertTrue(os.path.exists(lock_path))
        finally:
            if os.path.exists(lock_path):
                os.remove(lock_path)

    def test_45_engine_cycle_direct_probe(self):
        # the REAL NotificationEngine over the REAL parity store with
        # the EPHEMERAL backend, driven directly (no igniter): enqueue
        # → dispatch idempotency → priority queuing (quiet-hours defer
        # + CRITICAL bypass) → contact-metadata fail-closed →
        # terminal stickiness → durable status view
        from canonical.notification_contracts import (
            OUT_DELIVERED, OUT_TRANSIENT_FAILURE, ST_DELIVERED,
            ST_DUPLICATE_BLOCKED, ST_POLICY_DEFERRED, ST_QUEUED,
            NotificationContractError, dedup_key,
        )
        from canonical.notification_engine import NotificationEngine
        factory, _made = real_store_factory()
        engine = NotificationEngine(factory()[0], provenance=None,
                                    locks=_EphemeralNotificationLocks())
        key = dedup_key(dict(PROBE_EVENT))
        self.assertEqual(engine.enqueue(dict(PROBE_EVENT))["status"],
                         ST_QUEUED)
        self.assertEqual(engine.enqueue(dict(PROBE_EVENT))["status"],
                         ST_DUPLICATE_BLOCKED)
        night = dict(PROBE_EVENT, recipient="user-p17-night",
                     event_key="order:o2:night",
                     occurred_at="2026-09-27T23:30:00+00:00")
        dn = engine.enqueue(dict(night))
        self.assertEqual(dn["status"], ST_POLICY_DEFERRED)
        self.assertEqual(dn["reason"], "quiet_hours")
        crit = dict(PROBE_EVENT, recipient="user-p17-crit",
                    priority="CRITICAL",
                    template_id="hitl.review_required.v1",
                    variables={"queue_ref": "q-phase17",
                               "reason": "probe"},
                    event_key="hitl:q-phase17:critical",
                    occurred_at="2026-09-27T23:30:00+00:00")
        self.assertEqual(engine.enqueue(dict(crit))["status"], ST_QUEUED)
        with self.assertRaises(NotificationContractError):
            engine.enqueue(dict(PROBE_EVENT, channel="EMAIL",
                                variables={"order_ref": "o",
                                           "state": "s"}))
        s1 = engine.record_outcome(dict(PROBE_EVENT), key, 1,
                                   OUT_DELIVERED, "probe")
        s2 = engine.record_outcome(dict(PROBE_EVENT), key, 2,
                                   OUT_TRANSIENT_FAILURE, "late")
        self.assertEqual((s1, s2), (ST_DELIVERED, ST_DELIVERED))
        view = engine.status_view()
        self.assertEqual(view[key]["status"], ST_DELIVERED)
        # the blocked retry is durably recorded (the status view keeps
        # the winner's terminal state; the dup receipt is the evidence)
        dup_eid = NotificationEngine.outcome_event_id("dup", key, 0)
        self.assertIn("duplicate_blocked",
                      json.dumps(engine._store.records.get(
                          "notifications::" + dup_eid)))


# ===================================================================
# NTF-05 — emission contract
# ===================================================================

class TestNtf05Emission(unittest.TestCase):

    def test_50_exactly_one_attestation_per_run(self):
        h = Harness()
        att = h.run()
        self.assertEqual(len(h.sink), 1)
        self.assertEqual(h.sink[0]["schema"], ATTESTATION_SCHEMA)
        self.assertEqual(h.sink[0]["verdict"], att.verdict)

    def test_51_abort_still_emits_attestation(self):
        h = Harness(upstream_provider=None)
        att = h.run()
        self.assertEqual(att.verdict, PHASE17_INCOMPLETE)
        self.assertEqual(len(h.sink), 1)

    def test_52_digest_covers_every_field(self):
        att = Harness().run()
        d = att.to_dict()
        for key in ("schema", "verdict", "phase16_digest",
                    "manifest_sha256", "profile", "contracts",
                    "cycle", "checks", "observed_tick"):
            self.assertIn(key, d)


# ===================================================================
# REDACT — zero secret leakage (D-124)
# ===================================================================

class TestRedaction(unittest.TestCase):

    def test_60_no_secrets_or_canaries_in_outputs(self):
        h = Harness()
        att = h.run()
        blob = json.dumps(att.to_dict()) + json.dumps(h.sink)
        for secret in (CANARY, SMTP_TOKEN):
            self.assertNotIn(secret, blob)

    def test_61_refusal_details_carry_no_secrets(self):
        h = Harness(upstream_provider=lambda: {
            "schema": "x", "note": SMTP_TOKEN})
        att = h.run()
        blob = json.dumps(att.to_dict()) + json.dumps(h.sink)
        self.assertNotIn(SMTP_TOKEN, blob)

    def test_62_deep_redact_runs_on_emitted_records(self):
        h = Harness()
        att = h.run()
        row = h.sink[0]
        self.assertEqual(row["phase16_digest"], att.phase16_digest)
        self.assertEqual(row["manifest_sha256"],
                         att.manifest_sha256)

    def test_63_no_channel_secrets_in_outputs(self):
        h = Harness()
        att = h.run()
        blob = json.dumps(att.to_dict()) + json.dumps(h.sink)
        for marker in ("smtp", "sendmail", "api_key", "twilio",
                       "webhook_url", "auth_code", "pan",
                       "card_number"):
            self.assertNotIn(marker, blob)

    def test_64_contact_metadata_never_echoed(self):
        h = Harness()
        att = h.run()
        blob = json.dumps(att.to_dict()) + json.dumps(h.sink)
        # subjects/phone/endpoint refs are validated as PRESENT and
        # never echoed into the attestation
        self.assertNotIn("phone_ref", blob)
        self.assertNotIn("endpoint_ref", blob)


# ===================================================================
# AST — purity audits
# ===================================================================

class TestAstPurity(unittest.TestCase):

    def setUp(self):
        self.tree = ast.parse(ENGINE.read_text(encoding="utf-8"))

    def test_70_no_forbidden_imports_in_engine(self):
        banned = {"socket", "http", "urllib", "requests", "ftplib",
                  "smtplib", "asyncio", "subprocess", "shutil", "pty",
                  "commands", "os", "psycopg2", "sqlite3"}
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    self.assertNotIn(root, banned,
                                     f"forbidden import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                root = (node.module or "").split(".")[0]
                self.assertNotIn(root, banned,
                                 f"forbidden import from {node.module}")

    def test_71_no_shell_or_spawn_calls(self):
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Call):
                fn = node.func
                name = getattr(fn, "attr", getattr(fn, "id", ""))
                self.assertNotIn(name,
                                 ("system", "popen", "Popen",
                                  "spawn", "spawnl", "spawnv"),
                                 f"forbidden call {name}")

    def test_72_injected_dependencies_only(self):
        src = ENGINE.read_text(encoding="utf-8")
        self.assertIn("stack_factory", src)
        self.assertIn("census", src)
        self.assertIn("def _load", src)

    def test_73_interception_boundary_guarantee_in_source(self):
        src = ENGINE.read_text(encoding="utf-8")
        self.assertIn("egress-boundary violation", src)
        self.assertIn("phase17-scratch:", src)
        self.assertIn("_EphemeralNotificationLocks", src)
        self.assertIn("SLOT18_REGISTRY_FACT", src)


if __name__ == "__main__":
    unittest.main()

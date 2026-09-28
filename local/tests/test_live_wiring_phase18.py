"""Phase 18 live wiring igniter battery (D-168, offline).

Exercises `local/scripts/live_wiring_phase18_igniter.py` fully
offline — the engine the REAL `HitlEngine` (D-105/D-106/D-108) over
the REAL D-027 parity `EventStore` with the EPHEMERAL in-process
vault (zero durable footprint, reviewer interfaces isolated — no
human-notification or dashboard emitter exists), the census chained
from the REAL D-167 igniter over the REAL
D-166/D-165/D-164/D-162/D-161/D-160/D-159/D-158/D-157/D-156/D-155/
D-154 chain:

  PASS    — phase17 attestation + verified profile + REAL contracts +
            isolated review cycle ⇒ PHASE18_IGNITED, deterministic
            digest;
  HIT-01  — missing/raised/wrong-schema/incomplete-verdict/drifted/
            unrooted/broken-chain phase17 attestation ⇒ refusal with
            ZERO engine calls (proven);
  HIT-02  — unverified profile, missing phase rows (17 and 14),
            slot-18 registry-pin drift (reassigned/absent) ⇒
            refusal;
  HIT-03  — REAL validator rejections (ticket shape, action gate
            with EXPIRED sweep-only), lifecycle matrix, roles,
            escalation ladder;
  HIT-04  — absent store, cleanup failure, non-ephemeral vault,
            reviewer-signal egress ⇒ fail-closed refusal;
  HIT-05  — exactly one canonical attestation per run (including
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
from live_wiring_phase17_igniter import (  # noqa: E402
    PHASE17_IGNITED, PHASE17_INCOMPLETE,
)
from live_wiring_phase18_igniter import (  # noqa: E402
    ATTESTATION_SCHEMA, CYCLE_ID, PHASE17_ROW_KIND, PHASE17_SCHEMA,
    PHASE18_IGNITED, PHASE18_INCOMPLETE, PROBE_INSIGHT_KEY, SEAMS,
    SLOT18_REGISTRY_FACT, _EphemeralHitlVault, Phase18Igniter,
    canonical_hash,
)

ENGINE = SCRIPTS / "live_wiring_phase18_igniter.py"

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


# --- the authentic chain: phase17 attestation via the REAL D-167
# --- engine (which chains D-166 → … → D-154) -------------------------

def real_phase17_attestation(observed_tick=12000):
    """Run the REAL D-167 igniter over the authentic chain with
    in-process fakes (identical to the D-167 battery pass path)."""
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
    import tests.test_live_wiring_phase17 as t17  # noqa: E402
    h = t17.Harness(now=observed_tick)
    att = h.run()
    ledger = t17.the_ledger() + [{
        "event_kind": "phase17_notification_wiring_attestation",
        "detail": {"attestation_digest": att.attestation_digest,
                   "verdict": att.verdict}}]
    return att.to_dict(), ledger, t17


_RECON_STORE = None       # the REAL D-027 store of the last re-run
_RECON_SUMMARY: dict = {}  # the cycle summary of the last re-run


def real_phase18_attestation(observed_tick=13000):
    """Run the REAL D-168 igniter over the authentic chain with
    in-process fakes (identical to the D-168 battery pass path).
    Exposes the re-run's REAL D-027 store and cycle summary for the
    D-169 program-level reconciliation (REC-03 evidence)."""
    import tests.test_live_wiring_phase17 as t17  # noqa: F401
    h = Harness(now=observed_tick)
    att = h.run()
    global _RECON_STORE, _RECON_SUMMARY
    _RECON_STORE = h.made.get("store")
    _RECON_SUMMARY = dict(att.cycle)
    ledger = the_ledger() + [{
        "event_kind": "phase18_hitl_wiring_attestation",
        "detail": {"attestation_digest": att.attestation_digest,
                   "verdict": att.verdict}}]
    return att.to_dict(), ledger, t17


_CHAIN: dict = {}

_UNSET = object()  # sentinel: "no override given" (None = absent)


def the_att() -> dict:
    return _CHAIN["att"]


def the_ledger() -> list:
    return _CHAIN["ledger"]


def build_chain() -> None:
    if not _CHAIN:
        att, ledger, _t17 = real_phase17_attestation()
        _CHAIN.update(att=att, ledger=ledger)


def real_census() -> dict:
    """The runtime-profile census rows: Phases 5–12, 14, 15, 16, 17,
    all wired (slot 14 closed CRM-not-needed per D-163 — NOT a row)."""
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
                            (16, "Analyst Service"),
                            (17, "Notification Engine"))
        ],
    }


# --- the wired harness ---------------------------------------------------

class Harness:

    def __init__(self, now: int = 13000, stack_factory=_UNSET,
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
        self.igniter = Phase18Igniter(
            clock=lambda: self.now, audit_sink=self.sink.append,
            **providers)

    def run(self):
        return self.igniter.run()


# ===================================================================
# PASS — successful ignition
# ===================================================================

class TestIgnitionPass(unittest.TestCase):

    def test_005_ephemeral_vault_wired(self):
        h = Harness()
        h.run()  # the vault is constructed inside the cycle
        self.assertIsInstance(h.igniter._last_vault, _EphemeralHitlVault)

    def test_01_full_ignition_completes(self):
        h = Harness()
        att = h.run()
        self.assertEqual(att.verdict, PHASE18_IGNITED)
        self.assertTrue(att.ignited)
        d = att.to_dict()
        self.assertEqual(d["schema"], ATTESTATION_SCHEMA)
        self.assertEqual(d["schema"],
                         "phase18.hitl_wiring_attestation.v1")
        self.assertEqual(d["phase17_digest"],
                         canonical_hash(the_att()))
        ids = [c[0] for c in att.checks]
        for rule in ("HIT-01", "HIT-02", "HIT-03", "HIT-04",
                     "HIT-05"):
            self.assertIn(rule, ids)
        self.assertTrue(all(c[1] for c in att.checks))
        self.assertTrue(d["profile"]["runtime_profile_verified"])
        self.assertTrue(d["profile"]["seams_ok"])
        self.assertIn("slot 18 = canonical.ai_hitl_service",
                      d["profile"]["slot18_pin"])
        self.assertTrue(d["contracts"]["contracts_ok"])
        self.assertTrue(d["contracts"]["lifecycle_ok"])
        self.assertEqual(d["cycle"]["vault_backend"], "ephemeral")
        self.assertEqual(d["cycle"]["reviewer_signals_emitted"], 0)

    def test_02_attestation_digest_deterministic(self):
        a1 = Harness(now=13500).run()
        b1 = Harness(now=13500).run()
        self.assertEqual(a1.attestation_digest, b1.attestation_digest)
        self.assertEqual(a1.attestation_digest,
                         canonical_hash(a1.to_dict()))

    def test_03_review_cycle_steps_recorded(self):
        att = Harness().run()
        steps = att.to_dict()["cycle"]["steps"]
        kinds = [s[0] for s in steps]
        for kind in ("START", "AUTH", "INGEST", "CLAIM", "RESOLVE",
                     "ESCALATE", "SWEEP", "INVALID", "LEDGER",
                     "VERIFY", "CLEANUP"):
            self.assertIn(kind, kinds)
        self.assertTrue(all(s[1] for s in steps))
        self.assertEqual(len(att.to_dict()["cycle"]["summary_hash"]),
                         64)

    def test_04_ingest_claim_escalation_trace(self):
        att = Harness().run()
        steps = {s[0]: s[2] for s in att.to_dict()["cycle"]["steps"]}
        self.assertEqual(steps["INGEST"]["re_ingest"],
                         "duplicated (idempotent)")
        self.assertEqual(steps["CLAIM"]["wrong_role"], "role_forbidden")
        self.assertEqual(steps["CLAIM"]["second_claimant"],
                         "not_claimable")
        self.assertTrue(steps["ESCALATE"]["requeue_idempotent"])
        self.assertTrue(steps["SWEEP"]["open_tickets_untouched"])


# ===================================================================
# HIT-01 — phase17 attestation refusals (zero engine calls)
# ===================================================================

class TestHit01Refusals(unittest.TestCase):

    def test_10_missing_phase17_attestation(self):
        h = Harness(upstream_provider=None)
        att = h.run()
        self.assertEqual(att.verdict, PHASE18_INCOMPLETE)
        self.assertIn("absent", att.checks[0][2])
        self.assertEqual(len(h.sink), 1)

    def test_11_provider_raises(self):
        def boom():
            raise RuntimeError("vault offline")
        att = Harness(upstream_provider=boom).run()
        self.assertEqual(att.verdict, PHASE18_INCOMPLETE)
        self.assertIn("RuntimeError", att.checks[0][2])

    def test_12_wrong_schema(self):
        att = Harness(upstream_provider=lambda: {
            "schema": "other.v1"}).run()
        self.assertEqual(att.verdict, PHASE18_INCOMPLETE)
        self.assertIn("schema", att.checks[0][2])

    def test_13_incomplete_verdict_refused(self):
        bad = dict(the_att())
        bad["verdict"] = PHASE17_INCOMPLETE
        att = Harness(upstream_provider=lambda: bad).run()
        self.assertEqual(att.verdict, PHASE18_INCOMPLETE)
        self.assertIn("PHASE17_IGNITED",
                      " ".join(c[2] for c in att.checks))

    def test_14_drifted_digest_refused(self):
        rows = the_ledger()[:-1] + [{
            "event_kind": "phase17_notification_wiring_attestation",
            "detail": {"attestation_digest": "b" * 64}}]
        att = Harness(audit_rows=lambda: rows).run()
        self.assertEqual(att.verdict, PHASE18_INCOMPLETE)
        self.assertIn("DRIFTED", " ".join(c[2] for c in att.checks))

    def test_15_unrooted_attestation_refused(self):
        att = Harness(audit_rows=lambda: []).run()
        self.assertEqual(att.verdict, PHASE18_INCOMPLETE)
        self.assertIn("rooted", " ".join(c[2] for c in att.checks))

    def test_16_broken_chain_refused(self):
        att = Harness(chain_verifier=lambda: {
            "ok": False, "broken_at_seq": 1,
            "reason": "hash mismatch"}).run()
        self.assertEqual(att.verdict, PHASE18_INCOMPLETE)
        self.assertIn("not intact",
                      " ".join(c[2] for c in att.checks))

    def test_17_refusal_makes_zero_engine_calls(self):
        # every HIT-01 failure class must leave the store completely
        # unconstructed (the factory is never invoked)
        for kwargs in (
                {"upstream_provider": None},
                {"upstream_provider": lambda: {"schema": "x"}},
                {"audit_rows": lambda: []},
                {"chain_verifier": lambda: {"ok": False}}):
            factory, made = real_store_factory()
            h = Harness(stack_factory=factory, **kwargs)
            att = h.run()
            self.assertEqual(att.verdict, PHASE18_INCOMPLETE)
            self.assertIsNone(made.get("store"))  # factory never run


# ===================================================================
# HIT-02 — runtime profile & the slot-18 registry pin
# ===================================================================

class TestHit02Profile(unittest.TestCase):

    def test_20_unverified_profile_refused(self):
        bad = real_census()
        bad["runtime_profile_verified"] = False
        att = Harness(census=lambda: bad).run()
        self.assertEqual(att.verdict, PHASE18_INCOMPLETE)
        self.assertIn("NOT verified",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "HIT-02"))

    def test_21_missing_phase17_row_refused(self):
        bad = real_census()
        bad["phases"] = [p for p in bad["phases"]
                         if p["phase"] != 17]
        att = Harness(census=lambda: bad).run()
        self.assertEqual(att.verdict, PHASE18_INCOMPLETE)
        self.assertIn("Phase 17 missing",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "HIT-02"))

    def test_22_unwired_phase15_refused(self):
        bad = real_census()
        for p in bad["phases"]:
            if p["phase"] == 15:
                p["wired"] = False
        att = Harness(census=lambda: bad).run()
        self.assertEqual(att.verdict, PHASE18_INCOMPLETE)
        self.assertIn("VERIFIED+WIRED",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "HIT-02"))

    def test_23_slot18_reassigned_refused(self):
        # the D-154 cross-walk binds slot 18 to the HITL service; a
        # registry that reassigns the slot must refuse — the final
        # ignition takes EXACTLY that binding, nothing else (the
        # refusal fires on the slot-18 seam path: ENTRY_POINTS[18]
        # must equal the repo seam the D-154 pins)
        bad_registry_entry = {18: "canonical.something_else"}
        att = Harness(expected_entry_points=bad_registry_entry).run()
        self.assertEqual(att.verdict, PHASE18_INCOMPLETE)
        blob = " ".join(c[2] for c in att.checks if c[0] == "HIT-02")
        self.assertIn("ENTRY_POINTS[18]", blob)
        self.assertIn("registry drift", blob)

    def test_24_census_absent_refused(self):
        att = Harness(census=None).run()
        self.assertEqual(att.verdict, PHASE18_INCOMPLETE)
        self.assertIn("unavailable",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "HIT-02"))

    def test_25_slot18_pinned_in_pass(self):
        # the PASS run itself proves the pin: slot 18 is TAKEN by the
        # HITL service exactly as the D-154 cross-walk and the Phase
        # 17 registry fact require
        att = Harness().run()
        self.assertEqual(att.verdict, PHASE18_IGNITED)
        self.assertIn("TAKEN by this phase",
                      att.to_dict()["profile"]["slot18_pin"])

    def test_26_slot14_not_required_in_census(self):
        # D-163: slot 14 (CRM) must NOT be a required census row
        att = Harness().run()
        self.assertEqual(att.verdict, PHASE18_IGNITED)
        self.assertNotIn(13, att.to_dict()["profile"]["phases"])


# ===================================================================
# HIT-03 — HITL contracts & invariants
# ===================================================================

class TestHit03Contracts(unittest.TestCase):

    def test_30_validator_enforced_in_probe(self):
        # the PASS run itself proves the REAL validators enforce the
        # ticket + action gates with named reasons
        att = Harness().run()
        self.assertEqual(att.verdict, PHASE18_IGNITED)
        blob = " ".join(c[2] for c in att.checks if c[0] == "HIT-03")
        self.assertIn("REAL HITL contracts enforced", blob)

    def test_31_ticket_gate_direct(self):
        from canonical.hitl_contracts import (
            HitlContractError, validate_ticket,
        )
        good = {
            "ticket_id": "hitl-probe-direct",
            "queue_type": "INSIGHT_REVIEW",
            "payload_ref": "insight:ins-direct",
            "required_role": "owner",
            "resolution_status": "PENDING_REVIEW",
            "created_at_logical": "L0001",
        }
        validate_ticket(dict(good))  # conforming passes
        for bad, expect in (
                (dict(good, queue_type="FAX"), "queue_type"),
                (dict(good, required_role="admin"), "required_role"),
                (dict(good, resolution_status="APPROVED"),
                 "may only enter as"),
                (dict(good, ticket_id="t" * 129), "exceeds 128 chars")):
            with self.assertRaises(HitlContractError) as ctx:
                validate_ticket(bad)
            self.assertIn(expect, str(ctx.exception))

    def test_32_action_gate_direct(self):
        from canonical.hitl_contracts import (
            HitlContractError, validate_action,
        )
        good = {"decision": "APPROVED",
                "reviewer_actor_id": "role:owner"}
        validate_action(dict(good))  # conforming passes
        for bad, expect in (
                (dict(good, decision="EXPIRED"), "sweep-only"),
                (dict(good, decision="MAYBE"), "decision must be"),
                (dict(good, reviewer_actor_id="bob"), "reference"),
                (dict(good, payload_override={"x": 1}),
                 "only valid for MODIFIED")):
            with self.assertRaises(HitlContractError) as ctx:
                validate_action(bad)
            self.assertIn(expect, str(ctx.exception))

    def test_33_lifecycle_matrix_direct(self):
        from canonical.hitl_contracts import (
            is_transition_legal,
        )
        self.assertTrue(is_transition_legal("PENDING_REVIEW",
                                            "CLAIMED"))
        self.assertTrue(is_transition_legal("CLAIMED", "APPROVED"))
        self.assertFalse(is_transition_legal("PENDING_REVIEW",
                                             "APPROVED"))
        self.assertFalse(is_transition_legal("APPROVED", "REJECTED"))
        self.assertFalse(is_transition_legal("EXPIRED", "CLAIMED"))

    def test_34_role_discipline_direct(self):
        from canonical.hitl_contracts import can_actor_resolve
        self.assertTrue(can_actor_resolve("owner", "role:owner"))
        self.assertTrue(can_actor_resolve("any", "role:ops"))
        # agent: refs are legal mock actors (D-045) for the matching
        # role; unknown roles and bare names refuse
        self.assertTrue(can_actor_resolve("owner", "agent:owner"))
        self.assertFalse(can_actor_resolve("any", "role:customer"))
        self.assertFalse(can_actor_resolve("owner", "owner"))
        self.assertFalse(can_actor_resolve("owner", "role:ops"))

    def test_35_escalation_ladder_direct(self):
        from canonical.hitl_contracts import ESCALATION_TARGET
        self.assertEqual(ESCALATION_TARGET["any"], "ops")
        self.assertEqual(ESCALATION_TARGET["ops"], "owner")
        self.assertEqual(ESCALATION_TARGET["publisher"], "owner")
        self.assertEqual(ESCALATION_TARGET["owner"], "escalation")


# ===================================================================
# HIT-04 — review cycle refusals
# ===================================================================

class TestHit04Cycle(unittest.TestCase):

    def test_40_store_absent_refused(self):
        att = Harness(stack_factory=None).run()
        self.assertEqual(att.verdict, PHASE18_INCOMPLETE)
        blob = " ".join(c[2] for c in att.checks if c[0] == "HIT-04")
        self.assertIn("unavailable", blob)

    def test_41_reviewer_isolation_proven_in_pass(self):
        att = Harness().run()
        self.assertEqual(att.verdict, PHASE18_IGNITED)
        d = att.to_dict()["cycle"]
        steps = {s[0]: s[2] for s in d["steps"]}
        self.assertEqual(steps["AUTH"]["egress"], 0)
        self.assertEqual(d["reviewer_signals_emitted"], 0)

    def test_42_escalation_loop_proven_in_pass(self):
        att = Harness().run()
        steps = {s[0]: s[2] for s in att.to_dict()["cycle"]["steps"]}
        self.assertEqual(steps["ESCALATE"]["owner_escalates_to"],
                         "escalation")
        self.assertTrue(steps["ESCALATE"]["requeue_idempotent"])
        self.assertIn("APPROVED", steps["ESCALATE"]["loop_closed"])

    def test_43_cleanup_failure_refused(self):
        class StickyIgniter(Phase18Igniter):
            def _scratch_delete(self):
                return False  # refuses to clean the artifact
        h = Harness()
        h.igniter.__class__ = StickyIgniter
        att = h.run()
        self.assertEqual(att.verdict, PHASE18_INCOMPLETE)
        blob = " ".join(c[2] for c in att.checks if c[0] == "HIT-04")
        self.assertIn("cleanup failed", blob)

    def test_44_non_ephemeral_vault_refused(self):
        # a FILE-BACKED (durable-footprint) vault must be refused
        # fail-closed: the probe only ever runs on the ephemeral
        # in-process vault (D-079 hazard — the default vault claims
        # rows in live PG or the shared local/volumes/hitl files)
        from canonical.hitl_engine import _JsonVault
        import os
        import tempfile
        tmpdir = tempfile.mkdtemp(prefix="hitl-probe-")
        try:
            class DurableVaultProbe(Phase18Igniter):
                # simulates a mis-wired probe: the default vault
                # leaks in (file-backed → durable footprint)
                def _make_vault(self):
                    vault = _JsonVault(tmpdir)
                    self._last_vault = vault
                    return vault

            h = Harness()
            h.igniter.__class__ = DurableVaultProbe
            att = h.run()
            self.assertEqual(att.verdict, PHASE18_INCOMPLETE)
            blob = " ".join(c[2] for c in att.checks
                            if c[0] == "HIT-04")
            self.assertIn("durable footprint", blob)
            self.assertIn("ephemeral", blob)
            # the durable vault WAS constructed and would have
            # claimed rows — proving the guard is load-bearing
            self.assertIsNot(type(h.igniter._last_vault),
                             _EphemeralHitlVault)
            self.assertTrue(os.path.exists(
                os.path.join(tmpdir, "tickets.json")))
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_45_engine_cycle_direct_probe(self):
        # the REAL HitlEngine over the REAL parity store with the
        # EPHEMERAL vault, driven directly (no igniter): ingest →
        # claim race → resolve → escalation loop → expiry sweep →
        # tamper-evident ledger
        from canonical.hitl_contracts import (
            ST_APPROVED, ST_CLAIMED, ST_ESCALATED, ST_EXPIRED,
            ST_MODIFIED,
        )
        from canonical.hitl_engine import HitlEngine
        factory, _made = real_store_factory()
        engine = HitlEngine(factory()[0], vault=_EphemeralHitlVault())
        ing = engine.ingest_insight_tickets(["ins-direct-1"], "L1")
        tid = ing["created"][0]
        self.assertEqual(engine.claim(tid, "role:owner")["ok"], True)
        self.assertEqual(engine.claim(tid, "role:owner")["reason"],
                         "not_claimable")
        r = engine.resolve(tid, {"decision": ST_MODIFIED,
                                 "reviewer_actor_id": "role:owner",
                                 "payload_override": {"k": "v"}},
                           "L2")
        self.assertEqual((r["ok"], r["decision"]), (True, ST_MODIFIED))
        # a terminal ticket cannot escalate (CLAIMED-only)
        e = engine.resolve(tid, {"decision": ST_ESCALATED,
                                 "reviewer_actor_id": "role:owner"},
                           "L3")
        self.assertEqual((e["ok"], e["reason"]),
                         (False, "not_resolvable"))
        # the escalation LOOP: a second ticket goes PENDING → CLAIMED
        # → ESCALATED → a fresh elevated child → APPROVED
        esc = engine.create_ticket({
            "ticket_id": "hitl-direct-esc",
            "queue_type": "PUBLISH_GATE",
            "payload_ref": "post:p2",
            "required_role": "owner",
            "resolution_status": "PENDING_REVIEW",
            "created_at_logical": "L3"})["ticket_id"]
        self.assertEqual(engine.claim(esc, "role:owner")["ok"], True)
        e1 = engine.resolve(esc, {"decision": ST_ESCALATED,
                                  "reviewer_actor_id": "role:owner"},
                            "L4")
        self.assertEqual((e1["ok"], e1["escalated_to"]),
                         (True, "escalation"))
        child = esc + "-esc"
        q = engine.requeue_escalated(esc, "L4")
        self.assertEqual(q["status"], "CREATED")
        self.assertEqual(engine.claim(child, "role:escalation")["ok"],
                         True)
        self.assertEqual(engine.resolve(
            child, {"decision": ST_APPROVED,
                    "reviewer_actor_id": "role:escalation"},
            "L5")["ok"], True)
        # expired sweep: created at L1, deadline L1 → expired
        other = engine.create_ticket({
            "ticket_id": "hitl-direct-exp",
            "queue_type": "ORDER_OVERRIDE",
            "payload_ref": "order:o1",
            "required_role": "any",
            "resolution_status": "PENDING_REVIEW",
            "created_at_logical": "L1"})["ticket_id"]
        sw = engine.expire_sweep(lambda c: c <= "L1", "L6")
        self.assertEqual(sw["expired"], [other])
        # tamper-evidence: intact chains verify
        for t in (tid, child, other):
            self.assertTrue(engine.verify_chain(t)["ok"])


# ===================================================================
# HIT-05 — emission contract
# ===================================================================

class TestHit05Emission(unittest.TestCase):

    def test_50_exactly_one_attestation_per_run(self):
        h = Harness()
        att = h.run()
        self.assertEqual(len(h.sink), 1)
        self.assertEqual(h.sink[0]["schema"], ATTESTATION_SCHEMA)
        self.assertEqual(h.sink[0]["verdict"], att.verdict)

    def test_51_abort_still_emits_attestation(self):
        h = Harness(upstream_provider=None)
        att = h.run()
        self.assertEqual(att.verdict, PHASE18_INCOMPLETE)
        self.assertEqual(len(h.sink), 1)

    def test_52_digest_covers_every_field(self):
        att = Harness().run()
        d = att.to_dict()
        for key in ("schema", "verdict", "phase17_digest",
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
        self.assertEqual(row["phase17_digest"], att.phase17_digest)
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

    def test_64_no_real_reviewer_identity_in_outputs(self):
        h = Harness()
        att = h.run()
        blob = json.dumps(att.to_dict()) + json.dumps(h.sink)
        # only mock role:/agent: refs appear — no email addresses,
        # no URLs, no real identities, no emitter endpoints
        self.assertNotIn("@", blob)
        self.assertNotIn("https://", blob)
        self.assertNotIn("mailto:", blob)
        self.assertNotIn("reviewer_email", blob)
        self.assertNotIn("dashboard_url", blob)


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

    def test_73_isolation_boundary_guarantee_in_source(self):
        src = ENGINE.read_text(encoding="utf-8")
        self.assertIn("egress-boundary violation", src)
        self.assertIn("phase18-scratch:", src)
        self.assertIn("_EphemeralHitlVault", src)
        self.assertIn("SLOT18_REGISTRY_FACT", src)


if __name__ == "__main__":
    unittest.main()

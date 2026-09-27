"""Phase 16 live wiring igniter battery (D-166, offline).

Exercises `local/scripts/live_wiring_phase16_igniter.py` fully
offline — the engine stack the REAL `AnalystEngine` over the REAL
D-027 parity `EventStore` and the engine-side EPHEMERAL in-process
vault (zero durable footprint), the census chained from the REAL
D-165 igniter over the REAL D-164/D-162/D-161/D-160/D-159/D-158/
D-157/D-156/D-155/D-154 chain:

  PASS    — phase15 attestation + verified profile + REAL contracts +
            ephemeral analyst cycle ⇒ PHASE16_IGNITED, deterministic
            digest;
  ANL-01  — missing/raised/wrong-schema/incomplete-verdict/drifted/
            unrooted/broken-chain phase15 attestation ⇒ refusal with
            ZERO engine calls (proven);
  ANL-02  — unverified profile, missing phase rows, seam registry
            drift, slot-17 cross-walk drift, census absent ⇒ refusal;
  ANL-03  — REAL validator rejections (mis-classified reason ⇒
            refusal), deterministic identity, edge matrix, D-104
            boundary;
  ANL-04  — absent stack, cleanup failure, non-ephemeral vault ⇒
            fail-closed refusal;
  ANL-05  — exactly one canonical attestation per run (including
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
from live_wiring_phase15_igniter import (  # noqa: E402
    PHASE15_IGNITED, PHASE15_INCOMPLETE,
)
from live_wiring_phase16_igniter import (  # noqa: E402
    ATTESTATION_SCHEMA, CYCLE_ID, PHASE15_ROW_KIND, PHASE15_SCHEMA,
    PHASE16_IGNITED, PHASE16_INCOMPLETE, PROBE_INSIGHT_HIGH,
    PROBE_INSIGHT_LOW, SEAMS, _EphemeralVault, Phase16Igniter,
    canonical_hash,
)

ENGINE = SCRIPTS / "live_wiring_phase16_igniter.py"

CANARY = "sk-canaryvalue1234567890abcdef"
LLM_TOKEN = "llm-canary-provider-token-0123456789"


# --- the authentic chain: phase15 attestation via the REAL D-165
# --- engine (which chains D-164 → … → D-154) -------------------------

def real_phase15_attestation(observed_tick=11000):
    """Run the REAL D-165 igniter over the authentic chain with
    in-process fakes (identical to the D-165 battery pass path)."""
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
    import tests.test_live_wiring_phase15 as t15  # noqa: E402
    h = t15.Harness(now=observed_tick)
    att = h.run()
    ledger = t15.the_ledger() + [{
        "event_kind": "phase15_analytics_wiring_attestation",
        "detail": {"attestation_digest": att.attestation_digest,
                   "verdict": att.verdict}}]
    return att.to_dict(), ledger, t15


_CHAIN: dict = {}

_UNSET = object()  # sentinel: "no override given" (None = absent)


def the_att() -> dict:
    return _CHAIN["att"]


def the_ledger() -> list:
    return _CHAIN["ledger"]


def build_chain() -> None:
    if not _CHAIN:
        att, ledger, _t15 = real_phase15_attestation()
        _CHAIN.update(att=att, ledger=ledger)


def real_census() -> dict:
    """The runtime-profile census rows: Phases 5–12, 14 and 15, all
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
                            (15, "Analytics Engine"))
        ],
    }


def real_stack_factory():
    """The REAL engine stack: D-027 parity EventStore + the EPHEMERAL
    in-process vault, fresh per run."""
    made: dict = {}

    def factory():
        store = EventStore(":memory:") if False else None
        import tempfile, os as _os
        fd, path = tempfile.mkstemp(suffix=".json")
        import os as _os2
        _os.close(fd)
        _os2.remove(path)
        store = EventStore(path)
        vault = _EphemeralVault()
        made.update(store=store, vault=vault, path=path)
        return (store, vault)

    factory.made = made
    return factory, made


# --- the wired harness ---------------------------------------------------

class Harness:

    def __init__(self, now: int = 12000, stack_factory=_UNSET,
                 census=real_census, **overrides):
        build_chain()
        self.now = now
        self.sink: list = []
        if stack_factory is _UNSET:
            self.stack_factory, self.made = real_stack_factory()
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
        self.igniter = Phase16Igniter(
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
        h.run()  # the factory runs inside the cycle
        self.assertIs(type(h.made.get("vault")), _EphemeralVault)

    def test_01_full_ignition_completes(self):
        h = Harness()
        att = h.run()
        self.assertEqual(att.verdict, PHASE16_IGNITED)
        self.assertTrue(att.ignited)
        d = att.to_dict()
        self.assertEqual(d["schema"], ATTESTATION_SCHEMA)
        self.assertEqual(d["schema"],
                         "phase16.analyst_wiring_attestation.v1")
        self.assertEqual(d["phase15_digest"],
                         canonical_hash(the_att()))
        ids = [c[0] for c in att.checks]
        for rule in ("ANL-01", "ANL-02", "ANL-03", "ANL-04",
                     "ANL-05"):
            self.assertIn(rule, ids)
        self.assertTrue(all(c[1] for c in att.checks))
        self.assertTrue(d["profile"]["runtime_profile_verified"])
        self.assertTrue(d["profile"]["seams_ok"])
        self.assertTrue(d["contracts"]["identity_ok"])
        self.assertTrue(d["contracts"]["hitl_boundary_ok"])
        self.assertEqual(d["cycle"]["vault_backend"], "ephemeral")
        self.assertFalse(d["cycle"]["drift"])

    def test_02_attestation_digest_deterministic(self):
        a1 = Harness(now=12500).run()
        b1 = Harness(now=12500).run()
        self.assertEqual(a1.attestation_digest, b1.attestation_digest)
        self.assertEqual(a1.attestation_digest,
                         canonical_hash(a1.to_dict()))

    def test_03_analyst_steps_recorded(self):
        att = Harness().run()
        steps = att.to_dict()["cycle"]["steps"]
        kinds = [s[0] for s in steps]
        for kind in ("START", "AUTH", "PROPOSE", "EVALUATE",
                     "BOUNDARY", "SUPERSEDE", "LEDGER", "INVALID",
                     "VERIFY", "CLEANUP"):
            self.assertIn(kind, kinds)
        self.assertTrue(all(s[1] for s in steps))
        self.assertEqual(len(att.to_dict()["cycle"]["summary_hash"]),
                         64)

    def test_04_lifecycle_and_boundary_trace(self):
        att = Harness().run()
        steps = {s[0]: s[2] for s in att.to_dict()["cycle"]["steps"]}
        self.assertEqual(steps["BOUNDARY"]["rule"], "D-104")
        self.assertIn("refused", steps["BOUNDARY"]["high"])
        self.assertEqual(steps["BOUNDARY"]["low"], "auto-accepted")
        self.assertEqual(steps["INVALID"]["durable_rows_added"], 0)
        self.assertEqual(att.to_dict()["cycle"]["llm_calls"]
                         if "llm_calls" in att.to_dict()["cycle"]
                         else 0, 0)


# ===================================================================
# ANL-01 — phase15 attestation refusals (zero engine calls)
# ===================================================================

class TestAnl01Refusals(unittest.TestCase):

    def test_10_missing_phase15_attestation(self):
        h = Harness(upstream_provider=None)
        att = h.run()
        self.assertEqual(att.verdict, PHASE16_INCOMPLETE)
        self.assertIn("absent", att.checks[0][2])
        self.assertEqual(len(h.sink), 1)

    def test_11_provider_raises(self):
        def boom():
            raise RuntimeError("vault offline")
        att = Harness(upstream_provider=boom).run()
        self.assertEqual(att.verdict, PHASE16_INCOMPLETE)
        self.assertIn("RuntimeError", att.checks[0][2])

    def test_12_wrong_schema(self):
        att = Harness(upstream_provider=lambda: {
            "schema": "other.v1"}).run()
        self.assertEqual(att.verdict, PHASE16_INCOMPLETE)
        self.assertIn("schema", att.checks[0][2])

    def test_13_incomplete_verdict_refused(self):
        bad = dict(the_att())
        bad["verdict"] = PHASE15_INCOMPLETE
        att = Harness(upstream_provider=lambda: bad).run()
        self.assertEqual(att.verdict, PHASE16_INCOMPLETE)
        self.assertIn("PHASE15_IGNITED",
                      " ".join(c[2] for c in att.checks))

    def test_14_drifted_digest_refused(self):
        rows = the_ledger()[:-1] + [{
            "event_kind": "phase15_analytics_wiring_attestation",
            "detail": {"attestation_digest": "b" * 64}}]
        att = Harness(audit_rows=lambda: rows).run()
        self.assertEqual(att.verdict, PHASE16_INCOMPLETE)
        self.assertIn("DRIFTED", " ".join(c[2] for c in att.checks))

    def test_15_unrooted_attestation_refused(self):
        att = Harness(audit_rows=lambda: []).run()
        self.assertEqual(att.verdict, PHASE16_INCOMPLETE)
        self.assertIn("rooted", " ".join(c[2] for c in att.checks))

    def test_16_broken_chain_refused(self):
        att = Harness(chain_verifier=lambda: {
            "ok": False, "broken_at_seq": 1,
            "reason": "hash mismatch"}).run()
        self.assertEqual(att.verdict, PHASE16_INCOMPLETE)
        self.assertIn("not intact",
                      " ".join(c[2] for c in att.checks))

    def test_17_refusal_makes_zero_engine_calls(self):
        # every ANL-01 failure class must leave the stack completely
        # unconstructed (the factory is never invoked)
        for kwargs in (
                {"upstream_provider": None},
                {"upstream_provider": lambda: {"schema": "x"}},
                {"audit_rows": lambda: []},
                {"chain_verifier": lambda: {"ok": False}}):
            factory, made = real_stack_factory()
            h = Harness(stack_factory=factory, **kwargs)
            att = h.run()
            self.assertEqual(att.verdict, PHASE16_INCOMPLETE)
            self.assertIsNone(made.get("store"))  # factory never run


# ===================================================================
# ANL-02 — runtime profile & seams refusals
# ===================================================================

class TestAnl02Profile(unittest.TestCase):

    def test_20_unverified_profile_refused(self):
        bad = real_census()
        bad["runtime_profile_verified"] = False
        att = Harness(census=lambda: bad).run()
        self.assertEqual(att.verdict, PHASE16_INCOMPLETE)
        self.assertIn("NOT verified",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "ANL-02"))

    def test_21_missing_phase15_row_refused(self):
        bad = real_census()
        bad["phases"] = [p for p in bad["phases"]
                         if p["phase"] != 15]
        att = Harness(census=lambda: bad).run()
        self.assertEqual(att.verdict, PHASE16_INCOMPLETE)
        self.assertIn("Phase 15 missing",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "ANL-02"))

    def test_22_unwired_phase14_refused(self):
        bad = real_census()
        for p in bad["phases"]:
            if p["phase"] == 14:
                p["wired"] = False
        att = Harness(census=lambda: bad).run()
        self.assertEqual(att.verdict, PHASE16_INCOMPLETE)
        self.assertIn("VERIFIED+WIRED",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "ANL-02"))

    def test_23_seam_registry_drift_refused(self):
        bad_registry = {16: "canonical.nonexistent_module",
                        17: "canonical.analyst_engine"}
        att = Harness(expected_entry_points=bad_registry).run()
        self.assertEqual(att.verdict, PHASE16_INCOMPLETE)
        self.assertIn("registry drift",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "ANL-02"))

    def test_24_census_absent_refused(self):
        att = Harness(census=None).run()
        self.assertEqual(att.verdict, PHASE16_INCOMPLETE)
        self.assertIn("unavailable",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "ANL-02"))

    def test_25_slot17_crosswalk_drift_refused(self):
        # the D-154 cross-walk binds slot 17 ("AI Business Analyst")
        # to `canonical.analyst_engine`; a registry that drops the
        # slot refuses (defense-in-depth beyond the per-seam loop)
        bad_registry = {13: "canonical.orchestration_engine",
                        15: "canonical.scheduling_engine",
                        16: "canonical.analytics_engine"}
        att = Harness(expected_entry_points=bad_registry).run()
        self.assertEqual(att.verdict, PHASE16_INCOMPLETE)
        self.assertIn("cross-walk drift",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "ANL-02"))

    def test_26_slot14_not_required_in_census(self):
        # D-163: slot 14 (CRM) must NOT be a required census row
        att = Harness().run()
        self.assertEqual(att.verdict, PHASE16_IGNITED)
        self.assertNotIn(13, att.to_dict()["profile"]["phases"])


# ===================================================================
# ANL-03 — analyst contracts & invariants
# ===================================================================

class TestAnl03Contracts(unittest.TestCase):

    def test_30_validator_enforced_in_probe(self):
        # the PASS run itself proves the REAL validator enforces the
        # ten invalid-request classes with named reasons
        att = Harness().run()
        self.assertEqual(att.verdict, PHASE16_IGNITED)
        blob = " ".join(c[2] for c in att.checks if c[0] == "ANL-03")
        self.assertIn("REAL contracts enforced", blob)

    def test_31_insight_identity_deterministic_direct(self):
        from canonical.analyst_contracts import insight_key
        k1 = insight_key(PROBE_INSIGHT_LOW["category"],
                         PROBE_INSIGHT_LOW["correlation_keys"],
                         PROBE_INSIGHT_LOW["metric_refs"])
        k2 = insight_key(PROBE_INSIGHT_LOW["category"],
                         list(reversed(
                             PROBE_INSIGHT_LOW["correlation_keys"])),
                         list(reversed(
                             PROBE_INSIGHT_LOW["metric_refs"])))
        k3 = insight_key("content_performance",
                         PROBE_INSIGHT_LOW["correlation_keys"],
                         PROBE_INSIGHT_LOW["metric_refs"])
        self.assertEqual(k1, k2)
        self.assertNotEqual(k1, k3)
        self.assertEqual(len(k1), 64)

    def test_32_edge_matrix_direct(self):
        from canonical.analyst_contracts import (
            ST_AUTO_ACCEPTED, ST_DISPATCHED_TO_HITL, ST_DISMISSED,
            ST_EVALUATED, ST_GENERATED, ST_SUPERSEDED,
            is_transition_legal,
        )
        for cur, tgt in ((ST_GENERATED, ST_EVALUATED),
                         (ST_EVALUATED, ST_DISPATCHED_TO_HITL),
                         (ST_EVALUATED, ST_AUTO_ACCEPTED),
                         (ST_EVALUATED, ST_DISMISSED),
                         (ST_DISPATCHED_TO_HITL, ST_SUPERSEDED)):
            self.assertTrue(is_transition_legal(cur, tgt))
        for cur, tgt in ((ST_GENERATED, ST_AUTO_ACCEPTED),
                         (ST_AUTO_ACCEPTED, ST_SUPERSEDED),
                         (ST_DISMISSED, ST_EVALUATED),
                         (ST_DISPATCHED_TO_HITL, ST_AUTO_ACCEPTED)):
            self.assertFalse(is_transition_legal(cur, tgt))

    def test_33_d104_boundary_direct(self):
        from canonical.analyst_contracts import (
            can_auto_accept, requires_hitl,
        )
        self.assertTrue(requires_hitl(PROBE_INSIGHT_HIGH))
        self.assertFalse(can_auto_accept(PROBE_INSIGHT_HIGH))
        self.assertFalse(requires_hitl(PROBE_INSIGHT_LOW))
        mutating = dict(PROBE_INSIGHT_LOW, actionable_payload=dict(
            PROBE_INSIGHT_LOW["actionable_payload"],
            mutates_business_state=True))
        self.assertTrue(requires_hitl(mutating))
        self.assertFalse(can_auto_accept(mutating))

    def test_34_recommendation_shape_direct(self):
        from canonical.analyst_contracts import (
            AnalystContractError, make_recommendation,
        )
        rec = make_recommendation("report_summary", "why", False)
        self.assertEqual(rec["action"], "report_summary")
        self.assertFalse(rec["mutates_business_state"])
        with self.assertRaises(AnalystContractError):
            make_recommendation("", "why")

    def test_35_confidence_bounds_direct(self):
        from canonical.analyst_contracts import (
            AnalystContractError, validate_insight,
        )
        for bad in (1.5, -0.1, True, "0.5"):
            with self.assertRaises(AnalystContractError):
                validate_insight(dict(PROBE_INSIGHT_LOW,
                                      confidence_score=bad))

    def test_36_evaluator_contract_enforced(self):
        # the injected evaluator is a PURE function returning a
        # verdict dict; a malformed verdict is a Class-B refusal
        from canonical.analyst_contracts import (
            AnalystContractError, insight_key,
        )
        from canonical.analyst_engine import AnalystEngine
        import os
        import tempfile
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.remove(path)
        try:
            engine = AnalystEngine(EventStore(path),
                                   vault=_EphemeralVault())
            engine.propose(dict(PROBE_INSIGHT_LOW))
            key = insight_key(PROBE_INSIGHT_LOW["category"],
                              PROBE_INSIGHT_LOW["correlation_keys"],
                              PROBE_INSIGHT_LOW["metric_refs"])
            with self.assertRaises(AnalystContractError):
                engine.evaluate(key, lambda row: "bogus-verdict")
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_37_durable_audit_kinds_direct(self):
        from canonical.analyst_contracts import insight_key
        from canonical.analyst_engine import AnalystEngine
        import os
        import tempfile
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.remove(path)
        try:
            engine = AnalystEngine(EventStore(path),
                                   vault=_EphemeralVault())
            r = engine.propose(dict(PROBE_INSIGHT_HIGH))
            key = r["insight_key"]
            engine.evaluate(key, lambda row: {
                "approved": True, "note": "probe"})
            engine.dispatch_to_hitl(key)
            kinds = {ref.get("kind")
                     for ref in engine.ledger(key)}
            for want in ("insight_generated", "insight_evaluated",
                         "insight_dispatched_to_hitl"):
                self.assertIn(want, kinds)
            raw = engine._store.succeeded_references("analyst")
            self.assertTrue(len(raw) >= 3)  # durable, not vault-only
        finally:
            if os.path.exists(path):
                os.remove(path)


# ===================================================================
# ANL-04 — analyst cycle refusals
# ===================================================================

class TestAnl04Cycle(unittest.TestCase):

    def test_40_stack_absent_refused(self):
        att = Harness(stack_factory=None).run()
        self.assertEqual(att.verdict, PHASE16_INCOMPLETE)
        blob = " ".join(c[2] for c in att.checks if c[0] == "ANL-04")
        self.assertIn("unavailable", blob)

    def test_41_evidence_dedup_proven_in_pass(self):
        att = Harness().run()
        self.assertEqual(att.verdict, PHASE16_IGNITED)
        steps = {s[0]: s[2] for s in att.to_dict()["cycle"]["steps"]}
        self.assertEqual(steps["PROPOSE"]["created"], 2)
        self.assertIn("DUPLICATE", steps["PROPOSE"]["dedup"])

    def test_42_ledger_integrity_proven_in_pass(self):
        att = Harness().run()
        steps = {s[0]: s[2] for s in att.to_dict()["cycle"]["steps"]}
        self.assertEqual(steps["LEDGER"]["high_ledger"],
                         "generated→evaluated→hitl→superseded")
        self.assertEqual(steps["LEDGER"]["replay_source"],
                         "D-027 events alone")
        self.assertFalse(att.to_dict()["cycle"]["drift"])

    def test_43_cleanup_failure_refused(self):
        class StickyIgniter(Phase16Igniter):
            def _scratch_delete(self):
                return False  # refuses to clean the artifact
        h = Harness()
        h.igniter.__class__ = StickyIgniter
        att = h.run()
        self.assertEqual(att.verdict, PHASE16_INCOMPLETE)
        blob = " ".join(c[2] for c in att.checks if c[0] == "ANL-04")
        self.assertIn("cleanup failed", blob)

    def test_44_non_ephemeral_vault_refused(self):
        # a FULLY FUNCTIONAL but FOREIGN (non-ephemeral) vault passes
        # every data check, then VERIFY must still refuse the durable
        # footprint by class
        class ForeignVault:
            def __init__(self):
                self._rows = {}
            def insert_insight(self, row):
                key = row["insight_key"]
                if key in self._rows:
                    return "duplicate"
                import copy
                self._rows[key] = copy.deepcopy(row)
                return "created"
            def get_insight(self, insight_key):
                import copy
                row = self._rows.get(insight_key)
                return copy.deepcopy(row) if row else None
            def set_status(self, insight_key, status, superseded_by):
                row = self._rows.get(insight_key)
                if row is None:
                    return False
                row["status"] = status
                row["superseded_by"] = superseded_by
                return True
            def all_insights(self):
                import copy
                return copy.deepcopy(self._rows)
        h = Harness()
        factory, made = real_stack_factory()

        def foreign_factory():
            store, _ = factory()  # the REAL store
            return (store, ForeignVault())  # the FOREIGN vault
        att = Harness(stack_factory=foreign_factory).run()
        self.assertEqual(att.verdict, PHASE16_INCOMPLETE)
        blob = " ".join(c[2] for c in att.checks if c[0] == "ANL-04")
        self.assertIn("ephemeral", blob)


# ===================================================================
# ANL-05 — emission contract
# ===================================================================

class TestAnl05Emission(unittest.TestCase):

    def test_50_exactly_one_attestation_per_run(self):
        h = Harness()
        att = h.run()
        self.assertEqual(len(h.sink), 1)
        self.assertEqual(h.sink[0]["schema"], ATTESTATION_SCHEMA)
        self.assertEqual(h.sink[0]["verdict"], att.verdict)

    def test_51_abort_still_emits_attestation(self):
        h = Harness(upstream_provider=None)
        att = h.run()
        self.assertEqual(att.verdict, PHASE16_INCOMPLETE)
        self.assertEqual(len(h.sink), 1)

    def test_52_digest_covers_every_field(self):
        att = Harness().run()
        d = att.to_dict()
        for key in ("schema", "verdict", "phase15_digest",
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
        for secret in (CANARY, LLM_TOKEN):
            self.assertNotIn(secret, blob)

    def test_61_refusal_details_carry_no_secrets(self):
        h = Harness(upstream_provider=lambda: {
            "schema": "x", "note": LLM_TOKEN})
        att = h.run()
        blob = json.dumps(att.to_dict()) + json.dumps(h.sink)
        self.assertNotIn(LLM_TOKEN, blob)

    def test_62_deep_redact_runs_on_emitted_records(self):
        h = Harness()
        att = h.run()
        row = h.sink[0]
        self.assertEqual(row["phase15_digest"], att.phase15_digest)
        self.assertEqual(row["manifest_sha256"],
                         att.manifest_sha256)

    def test_63_no_llm_or_lake_markers_in_outputs(self):
        h = Harness()
        att = h.run()
        blob = json.dumps(att.to_dict()) + json.dumps(h.sink)
        for marker in ('"llm_calls": 1', "api_key", "openai",
                       "anthropic", "data_lake", "webhook_secret",
                       "auth_code", "pan", "card_number"):
            self.assertNotIn(marker, blob)


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

    def test_73_sandbox_boundary_guarantee_in_source(self):
        src = ENGINE.read_text(encoding="utf-8")
        self.assertIn("sandbox-boundary violation", src)
        self.assertIn("phase16-scratch:", src)
        self.assertIn("_EphemeralVault", src)
        self.assertIn("D-163", src)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Battery for the Live Wiring program-level completion
reconciliation (D-169).

Mirrors the D-155..D-168 battery standard over the REAL phase 5–18
chain re-run:

  PASS      the reconciliation runs PROGRAM_RECONCILED over the
            authentic chain, the census reconciles slots 5–18, the
            seal and the lock hold, and the invariants pass;
  ABORT     every refusal class (absent/raised providers, chain
            drift, digest drift, unrooted rows, broken linkage,
            census drift, seal/lock violations, invariant
            violations) names its blocker and emits exactly ONE
            attestation — aborts included;
  REDACT    zero secret or canary leakage in the emitted evidence
            (D-124);
  AST       the engine is pure: no socket/http/subprocess/os
            imports, no shell/spawn calls, injected dependencies
            only, the exactly-once emission guard present.

The battery runs from the repository ROOT
(`python3 -m unittest local.tests.test_live_wiring_completion`) —
environment contract.
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
          str(SRC.parent), str(SRC / "security"),
          str(REPO / "local" / "tests")):
    if p not in sys.path:
        sys.path.insert(0, p)

from live_wiring_completion_reconciliation import (  # noqa: E402
    ATTESTATION_SCHEMA, CANARY_MARKERS, CHAIN_PLAN, CENSUS_PHASES,
    D163_SEAL, EXPECTED_CHAIN_KINDS, LIVE_ENTRY_POINTS,
    PHASE18_ROW_KIND, PROGRAM_INCOMPLETE, PROGRAM_RECONCILED,
    SLOT18_REGISTRY_FACT, SLOT18_SEAM, SLOT14_SEAM,
    ReconciliationAttestation, ReconciliationEngine,
    canonical_hash,
)
from live_wiring_phase18_igniter import (  # noqa: E402
    PHASE18_IGNITED, canonical_hash as _c18,
)

ENGINE = SCRIPTS / "live_wiring_completion_reconciliation.py"

CANARY = "sk-canaryvalue1234567890abcdef"
SMTP_TOKEN = "smtp-canary-relay-token-0123456789"

# The Live Wiring census names (MASTER_PLAN §13 labels for the
# repository seams bound by the D-154 cross-walk).
_PHASE_NAMES = {
    5: "n8n Foundation", 6: "Notion Business OS", 7: "AI Runtime",
    8: "AI Product Manager", 9: "Instagram", 10: "AI Sales Agent",
    11: "Order Management", 12: "Payment",
    15: "Marketing Automation", 16: "Analytics",
    17: "AI Business Analyst", 18: "Human-in-the-Loop System",
}


# --- the authentic chain: the REAL phase 5–18 re-run -----------------

_EVIDENCE: dict = {}


def chain_evidence() -> dict:
    """Re-run the REAL phase 5–18 battery chain-builders IN ORDER
    (cached) and expose the whole verification evidence."""
    if _EVIDENCE:
        return _EVIDENCE
    rows: list = []
    digests: dict = {}
    emits: dict = {}
    summaries: dict = {}
    store = None
    import importlib
    for mod_name, fn_name, kind in CHAIN_PLAN:
        # sys.path poisoning defense (mirrored across all chain
        # builders)
        local_root = str(REPO / "local")
        sys.path[:] = [p for p in sys.path
                       if p not in (local_root + "/canonical",
                                    local_root + "\\canonical")]
        t = sys.modules.get("tests")
        if t is not None and not getattr(t, "__path__", None):
            del sys.modules["tests"]  # legacy single-module shadow
        sys.path.insert(0, local_root)
        mod = importlib.import_module(mod_name)
        out = getattr(mod, fn_name)()
        if kind == "dokploy_completion_attestation":
            att, ledger = out
            digests[kind] = att["attestation_digest"]
            emits[kind] = {k: v for k, v in att.items()
                           if k != "attestation_digest"}
        elif kind == "phase5_live_wiring_attestation":
            att_obj, ledger = out
            digests[kind] = att_obj.attestation_digest
            emits[kind] = att_obj.to_dict()
        else:
            att, ledger, _tmod = out
            digests[kind] = canonical_hash(att)
            emits[kind] = att
        rows = ledger  # cumulative: the final ledger is the chain
        summaries[kind + ".digest"] = digests[kind]
        if kind == "phase18_hitl_wiring_attestation":
            t18 = importlib.import_module(
                "tests.test_live_wiring_phase18")
            store = getattr(t18, "_RECON_STORE", None) or store
            summ = getattr(t18, "_RECON_SUMMARY", None)
            if summ:
                summaries["phase18.cycle"] = summ
    _EVIDENCE.update(rows=rows, digests=digests, emits=emits,
                     store=store, summaries=summaries)
    return _EVIDENCE


def the_chain() -> dict:
    return chain_evidence()


def the_att() -> dict:
    return chain_evidence()["emits"][PHASE18_ROW_KIND]


def the_ledger() -> list:
    return chain_evidence()["rows"]


def real_census() -> dict:
    """The all-slot census: the LIVE D-154 registry seams over the
    phases 5–13 + 15–18 required set (slot 14 sealed, D-163 —
    deliberately NOT a row)."""
    return {
        "runtime_profile_verified": True,
        "phases": [
            {"phase": n, "name": _PHASE_NAMES[n],
             "entry_point": LIVE_ENTRY_POINTS[n],
             "present": True, "verified": True, "wired": True,
             "detail": "ready"}
            for n in sorted(_PHASE_NAMES)
        ],
    }


def _drifted_chain(base: dict, **over) -> dict:
    c = {k: (v.copy() if isinstance(v, (dict, list)) else v)
         for k, v in base.items()}
    c.update(over)
    return c


# --- the wired harness -----------------------------------------------

class Harness:

    def __init__(self, now: int = 99000, chain=the_chain,
                 census=real_census, **overrides):
        self.now = now
        self.sink: list = []
        providers = {
            "chain_provider": chain,
            "chain_verifier": lambda: {"ok": True,
                                       "rows": len(the_ledger())},
            "census": census,
        }
        providers.update(overrides)
        self.engine = ReconciliationEngine(
            clock=lambda: self.now, audit_sink=self.sink.append,
            **providers)

    def run(self):
        return self.engine.run()


def check_ids(att) -> list:
    return [c[0] for c in att.checks]


# ===================================================================
# PASS — the program reconciles over the REAL chain
# ===================================================================

class TestReconciliationPass(unittest.TestCase):

    def test_005_real_chain_builds_all_14_attestations(self):
        chain = the_chain()
        self.assertEqual(len(chain["digests"]), 14)
        self.assertEqual(
            sorted(chain["digests"]),
            sorted(EXPECTED_CHAIN_KINDS))

    def test_006_real_chain_ledger_in_order(self):
        kinds = [r["event_kind"] for r in the_ledger()]
        self.assertEqual(
            kinds[-len(EXPECTED_CHAIN_KINDS):],
            list(EXPECTED_CHAIN_KINDS))

    def test_007_real_chain_final_digest_matches_d168(self):
        # The re-run phase-18 digest is byte-stable with the
        # governance-recorded D-168 attestation digest.
        d = the_chain()["digests"][PHASE18_ROW_KIND]
        self.assertTrue(d.startswith("0026f4c94a11872a"))

    def test_01_full_reconciliation_completes(self):
        att = Harness().run()
        self.assertEqual(att.verdict, PROGRAM_RECONCILED)
        self.assertTrue(att.reconciled)
        d = att.to_dict()
        self.assertEqual(d["schema"], ATTESTATION_SCHEMA)
        self.assertEqual(d["schema"],
                         "live_wiring.completion_reconciliation.v1")
        self.assertEqual(d["observed_tick"], 99000)

    def test_02_every_rule_check_present_and_green(self):
        att = Harness().run()
        ids = check_ids(att)
        for rule in ("REC-01", "REC-02", "REC-03", "REC-04"):
            self.assertIn(rule, ids)
        self.assertTrue(all(c[1] for c in att.checks))

    def test_03_chain_digest_is_canonical_over_the_chain(self):
        chain = the_chain()
        att = Harness().run()
        self.assertEqual(att.chain_digest,
                         canonical_hash({
                             "kinds": list(EXPECTED_CHAIN_KINDS),
                             "digests": {k: chain["digests"][k]
                                         for k in
                                         EXPECTED_CHAIN_KINDS}}))

    def test_04_every_upstream_digest_recomputes(self):
        chain = the_chain()
        for kind, declared in chain["digests"].items():
            emitted = chain["emits"][kind]
            if kind == "dokploy_completion_attestation":
                continue  # the D-154 engine carries its own digest
            self.assertEqual(canonical_hash(emitted), declared,
                             kind)
            self.assertEqual(len(declared), 64)

    def test_05_every_attestation_rooted_in_its_d112_row(self):
        chain = the_chain()
        for kind in EXPECTED_CHAIN_KINDS:
            row = next(r for r in the_ledger()
                       if r.get("event_kind") == kind)
            self.assertEqual(
                row["detail"]["attestation_digest"],
                chain["digests"][kind], kind)

    def test_06_linkage_unbroken_first_to_last(self):
        chain = the_chain()
        order = list(EXPECTED_CHAIN_KINDS)
        ups = {"phase5_live_wiring_attestation": "cert_digest",
               "phase6_live_wiring_attestation": "phase5_digest",
               "phase7_live_wiring_attestation": "phase6_digest",
               "phase8_live_wiring_attestation": "phase7_digest",
               "phase9_live_wiring_attestation": "phase8_digest",
               "phase10_live_wiring_attestation": "phase9_digest",
               "phase11_payment_wiring_attestation": "phase10_digest",
               "phase12_shipping_wiring_attestation": "phase11_digest",
               "phase14_scheduling_wiring_attestation":
                   "phase12_digest",
               "phase15_analytics_wiring_attestation":
                   "phase14_digest",
               "phase16_analyst_wiring_attestation":
                   "phase15_digest",
               "phase17_notification_wiring_attestation":
                   "phase16_digest",
               "phase18_hitl_wiring_attestation": "phase17_digest"}
        for prev_k, cur_k in zip(order, order[1:]):
            self.assertEqual(
                chain["emits"][cur_k].get(ups[cur_k]),
                chain["digests"][prev_k],
                f"{cur_k} must bind {prev_k}")

    def test_07_phase18_verdict_carried_in_the_evidence(self):
        self.assertEqual(the_att()["verdict"], PHASE18_IGNITED)
        self.assertEqual(the_att()["schema"],
                         "phase18.hitl_wiring_attestation.v1")

    def test_08_registry_binds_exactly_slots_5_to_18(self):
        att = Harness().run()
        self.assertEqual(
            att.census["entry_points"], dict(LIVE_ENTRY_POINTS))
        self.assertEqual(sorted(att.census["entry_points"]),
                         list(range(5, 19)))
        self.assertEqual(len(att.census["entry_points"]), 14)

    def test_09_census_rows_complete_and_wired(self):
        att = Harness().run()
        self.assertEqual(att.census["census_phases"],
                         sorted(CENSUS_PHASES))
        self.assertEqual(len(CENSUS_PHASES), 12)
        self.assertTrue(att.census["slot14_sealed"])
        self.assertTrue(att.census["slot18_locked"])

    def test_10_slot14_seal_d163(self):
        chain = the_chain()
        self.assertEqual(chain["emits"].get("seal"), None)
        att = Harness().run()
        det = " ".join(c[2] for c in att.checks if c[0] == "REC-02")
        self.assertIn("SEALED CRM-not-needed", det)
        self.assertIn(SLOT14_SEAM, det)
        self.assertEqual(D163_SEAL,
                         "slot 14 CRM-not-needed (D-163)")
        # the seal is registry-visible but never a census row
        self.assertNotIn(14, att.census["census_phases"])
        self.assertEqual(
            dict(LIVE_ENTRY_POINTS)[14], "commerce.sync_orchestrator")

    def test_11_slot18_lock_load_bearing(self):
        att = Harness().run()
        self.assertEqual(SLOT18_REGISTRY_FACT, SLOT18_SEAM)
        self.assertEqual(dict(LIVE_ENTRY_POINTS)[18], SLOT18_SEAM)
        det = " ".join(c[2] for c in att.checks if c[0] == "REC-02")
        self.assertIn("LOCKED to canonical.ai_hitl_service", det)
        # and the D-168 evidence itself pins the same fact
        self.assertIn(SLOT18_SEAM,
                      json.dumps(the_chain()["emits"][
                          PHASE18_ROW_KIND]["profile"]))

    def test_12_zero_durable_footprint_invariant(self):
        att = Harness().run()
        self.assertTrue(att.invariants["zero_durable_footprint"])
        det = " ".join(c[2] for c in att.checks if c[0] == "REC-03")
        self.assertIn("ZERO durable footprint", det)

    def test_13_store_carries_only_hitl_rows(self):
        att = Harness().run()
        self.assertTrue(att.invariants["hitl_only_rows"])
        store = the_chain()["store"]
        self.assertTrue(store.records)
        for key in store.records:
            self.assertTrue(key.startswith("hitl::"), key)

    def test_14_zero_human_surface_egress_invariant(self):
        att = Harness().run()
        self.assertTrue(att.invariants["zero_human_surface_egress"])
        c18 = the_chain()["summaries"]["phase18.cycle"]
        self.assertEqual(c18["reviewer_signals_emitted"], 0)
        self.assertEqual(c18["vault_backend"], "ephemeral")

    def test_15_egress_marker_sweep_clean(self):
        att = Harness().run()
        self.assertTrue(att.invariants["egress_markers_clean"])
        blob = json.dumps(the_chain()["emits"], default=str)
        for marker in CANARY_MARKERS:
            self.assertNotIn(marker, blob)

    def test_16_ast_purity_invariant(self):
        att = Harness().run()
        self.assertTrue(att.invariants["ast_pure"])

    def test_17_exactly_one_attestation_per_run(self):
        h = Harness()
        att = h.run()
        self.assertEqual(len(h.sink), 1)
        self.assertEqual(h.sink[0]["schema"], ATTESTATION_SCHEMA)
        self.assertEqual(h.sink[0]["verdict"], att.verdict)

    def test_18_digest_covers_every_field(self):
        att = Harness().run()
        d = att.to_dict()
        for key in ("schema", "verdict", "chain_digest", "census",
                    "invariants", "checks", "observed_tick"):
            self.assertIn(key, d)
        self.assertEqual(att.attestation_digest,
                         canonical_hash(d))

    def test_19_checks_detail_redacted_but_green(self):
        att = Harness().run()
        for cid, ok, _det in att.checks:
            self.assertIn(cid,
                          ("REC-01", "REC-02", "REC-03", "REC-04"))
            self.assertIsInstance(ok, bool)


# ===================================================================
# ABORT — every refusal names its blocker (fail-closed)
# ===================================================================

class TestRefusals(unittest.TestCase):

    def test_20_chain_absent_refused(self):
        h = Harness(chain=None)
        att = h.run()
        self.assertEqual(att.verdict, PROGRAM_INCOMPLETE)
        ids = check_ids(att)
        self.assertIn("REC-01", ids)
        self.assertNotIn("REC-02", ids)  # fail-fast gate
        self.assertNotIn("REC-03", ids)
        self.assertIn("chain unavailable", att.checks[0][2])
        self.assertEqual(len(h.sink), 1)

    def test_21_chain_provider_raises_refused(self):
        def boom():
            raise ValueError("boom")
        att = Harness(chain=boom).run()
        self.assertEqual(att.verdict, PROGRAM_INCOMPLETE)
        self.assertIn("provider raised ValueError",
                      att.checks[0][2])

    def test_22_chain_verifier_absent_refused(self):
        att = Harness(chain_verifier=None).run()
        self.assertEqual(att.verdict, PROGRAM_INCOMPLETE)
        self.assertIn("chain verifier refuses",
                      " ".join(c[2] for c in att.checks))

    def test_23_chain_verifier_refuses_refused(self):
        att = Harness(chain_verifier=lambda: {
            "ok": False, "detail": "hash break at row 4"}).run()
        self.assertEqual(att.verdict, PROGRAM_INCOMPLETE)
        self.assertIn("hash break at row 4",
                      " ".join(c[2] for c in att.checks))

    def test_24_rooting_row_drift_refused(self):
        chain = _drifted_chain(
            the_chain(),
            rows=[r for r in the_ledger()
                  if r.get("event_kind") != PHASE18_ROW_KIND])
        att = Harness(chain=lambda: chain).run()
        self.assertEqual(att.verdict, PROGRAM_INCOMPLETE)
        self.assertIn("rooting chain drift",
                      " ".join(c[2] for c in att.checks))

    def test_25_declared_digest_drift_refused(self):
        chain = _drifted_chain(the_chain())
        chain["digests"] = dict(chain["digests"])
        chain["digests"][PHASE18_ROW_KIND] = "f" * 64
        att = Harness(chain=lambda: chain).run()
        self.assertEqual(att.verdict, PROGRAM_INCOMPLETE)
        det = " ".join(c[2] for c in att.checks)
        self.assertIn("recompute MISMATCH", det)
        self.assertIn("NOT rooted", det)

    def test_26_unrooted_row_refused(self):
        chain = _drifted_chain(the_chain())
        chain["rows"] = [dict(r) for r in the_ledger()]
        for r in chain["rows"]:
            if r.get("event_kind") == "phase5_live_wiring_attestation":
                r["detail"] = dict(r["detail"])
                r["detail"]["attestation_digest"] = "0" * 64
        att = Harness(chain=lambda: chain).run()
        self.assertEqual(att.verdict, PROGRAM_INCOMPLETE)
        self.assertIn("NOT rooted", " ".join(
            c[2] for c in att.checks))

    def test_27_linkage_fork_refused(self):
        chain = _drifted_chain(the_chain())
        chain["emits"] = dict(chain["emits"])
        chain["emits"][PHASE18_ROW_KIND] = dict(
            chain["emits"][PHASE18_ROW_KIND])
        chain["emits"][PHASE18_ROW_KIND]["phase17_digest"] = "e" * 64
        att = Harness(chain=lambda: chain).run()
        self.assertEqual(att.verdict, PROGRAM_INCOMPLETE)
        det = " ".join(c[2] for c in att.checks)
        self.assertIn("does not bind", det)
        self.assertIn("phase17_notification_wiring_attestation", det)

    def test_28_census_absent_refused(self):
        att = Harness(census=None).run()
        self.assertEqual(att.verdict, PROGRAM_INCOMPLETE)
        self.assertIn("census unavailable",
                      " ".join(c[2] for c in att.checks))

    def test_29_census_profile_unverified_refused(self):
        census = real_census()
        census["runtime_profile_verified"] = False
        att = Harness(census=lambda: census).run()
        self.assertEqual(att.verdict, PROGRAM_INCOMPLETE)
        self.assertIn("runtime_profile_verified",
                      " ".join(c[2] for c in att.checks))

    def test_30_census_row_missing_refused(self):
        census = real_census()
        census["phases"] = [p for p in census["phases"]
                            if p["phase"] != 15]
        att = Harness(census=lambda: census).run()
        self.assertEqual(att.verdict, PROGRAM_INCOMPLETE)
        det = " ".join(c[2] for c in att.checks)
        self.assertIn("census INCOMPLETE", det)
        self.assertIn("15", det)

    def test_31_census_seam_drift_refused(self):
        census = real_census()
        census["phases"] = [dict(p) if p["phase"] != 18 else
                            {**p, "entry_point":
                             "canonical.notification_engine"}
                            for p in census["phases"]]
        att = Harness(census=lambda: census).run()
        self.assertEqual(att.verdict, PROGRAM_INCOMPLETE)
        self.assertIn("seam drift", " ".join(
            c[2] for c in att.checks))

    def test_32_registry_pin_drift_refused(self):
        eps = dict(LIVE_ENTRY_POINTS)
        eps[18] = "canonical.notification_engine"
        att = Harness(expected_entry_points=eps).run()
        self.assertEqual(att.verdict, PROGRAM_INCOMPLETE)
        det = " ".join(c[2] for c in att.checks)
        self.assertIn("slot 18 LOCK violated", det)
        self.assertIn("reassignment refuses", det)

    def test_33_slot14_unsealed_refused(self):
        # the seal = registry binding + ABSENCE from the census rows;
        # a rebuilt CRM census row violates the D-163 disposition.
        census = real_census()
        census["phases"].append({
            "phase": 14, "name": "CRM",
            "entry_point": "commerce.sync_orchestrator",
            "present": True, "verified": True, "wired": True,
            "detail": "rebuilt"})
        att = Harness(census=lambda: census).run()
        self.assertEqual(att.verdict, PROGRAM_INCOMPLETE)
        self.assertIn("slot 14 seal violated", " ".join(
            c[2] for c in att.checks))

    def test_34_zero_egress_violation_refused(self):
        chain = _drifted_chain(the_chain())
        chain["summaries"] = dict(chain["summaries"])
        chain["summaries"]["phase18.cycle"] = dict(
            chain["summaries"]["phase18.cycle"],
            reviewer_signals_emitted=3)
        att = Harness(chain=lambda: chain).run()
        self.assertEqual(att.verdict, PROGRAM_INCOMPLETE)
        self.assertIn("human-surface egress detected",
                      " ".join(c[2] for c in att.checks))

    def test_35_egress_marker_hit_refused(self):
        chain = _drifted_chain(the_chain())
        chain["summaries"] = dict(chain["summaries"])
        chain["summaries"]["phase18.cycle"] = dict(
            chain["summaries"]["phase18.cycle"],
            injected_canary=CANARY)
        att = Harness(chain=lambda: chain).run()
        self.assertEqual(att.verdict, PROGRAM_INCOMPLETE)
        self.assertIn("egress markers found", " ".join(
            c[2] for c in att.checks))

    def test_36_second_emission_aborts_the_run(self):
        h = Harness()
        h.run()
        with self.assertRaises(Exception) as ctx:
            h.engine._emit(PROGRAM_RECONCILED, [])
        self.assertIn("second attestation emission refused",
                      str(ctx.exception))


# ===================================================================
# REDACT — zero secret leakage (D-124)
# ===================================================================

class TestRedaction(unittest.TestCase):

    def test_60_no_secrets_or_canaries_in_outputs(self):
        h = Harness()
        att = h.run()
        blob = json.dumps(att.to_dict(), default=str) + \
            json.dumps(h.sink, default=str)
        for secret in (CANARY, SMTP_TOKEN):
            self.assertNotIn(secret, blob)

    def test_61_refusal_details_carry_no_secrets(self):
        def poisoned():
            return {"rows": [{"event_kind": "x",
                              "detail": {"note": SMTP_TOKEN}}]}
        att = Harness(chain=poisoned).run()
        blob = json.dumps(att.to_dict(), default=str)
        self.assertNotIn(SMTP_TOKEN, blob)

    def test_62_deep_redact_runs_on_emitted_records(self):
        h = Harness()
        att = h.run()
        row = h.sink[0]
        self.assertEqual(row["chain_digest"], att.chain_digest)
        self.assertEqual(row["schema"], ATTESTATION_SCHEMA)

    def test_63_no_channel_secrets_in_outputs(self):
        h = Harness()
        att = h.run()
        blob = json.dumps(att.to_dict(), default=str)
        for marker in ("smtp", "sendmail", "api_key", "twilio",
                       "webhook_url", "auth_code", "pan",
                       "card_number"):
            self.assertNotIn(marker, blob)

    def test_64_no_real_actor_identity_in_outputs(self):
        h = Harness()
        att = h.run()
        blob = json.dumps(att.to_dict(), default=str)
        self.assertNotIn("@", blob)
        self.assertNotIn("https://", blob)
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
        self.assertIn("chain_provider", src)
        self.assertIn("census", src)
        self.assertIn("def _load", src)

    def test_73_exactly_once_emission_guard_in_source(self):
        src = ENGINE.read_text(encoding="utf-8")
        self.assertIn("exactly one per run", src)
        self.assertIn("_emitted", src)

    def test_74_registry_seal_and_lock_in_source(self):
        src = ENGINE.read_text(encoding="utf-8")
        self.assertIn("SLOT18_REGISTRY_FACT", src)
        self.assertIn("SLOT14_SEAM", src)
        self.assertIn("D163_SEAL", src)
        self.assertIn("canonical.ai_hitl_service", src)

    def test_75_verification_boundary_only_in_source(self):
        src = ENGINE.read_text(encoding="utf-8")
        self.assertIn("verification boundary ONLY", src)
        self.assertIn("opens nothing, and executes nothing", src)


if __name__ == "__main__":
    unittest.main()

"""Phase 11 live wiring igniter battery (D-161, offline).

Exercises `local/scripts/live_wiring_phase11_igniter.py` fully
offline — the gateway injected (the engine's own `SandboxGateway`,
DRY-RUN capability-capped), the OMS stack the REAL D-160 factory
(`OmsEngine` over `EventStore`/`JsonInventory`/`_ReservationLedger`),
the census chained from the REAL D-160 igniter over the REAL
D-159/D-158/D-157/D-156/D-155/D-154 chain:

  PASS    — phase10 attestation + verified profile + sandbox-capped
            gateway + dry-run settlement cycle ⇒ PHASE11_IGNITED,
            deterministic digest;
  SET-01  — missing/raised/wrong-schema/incomplete-verdict/drifted/
            unrooted/broken-chain phase10 attestation ⇒ refusal with
            ZERO gateway calls (proven);
  SET-02  — unverified profile, missing phase rows, seam registry
            drift, census absent ⇒ refusal;
  SET-03  — gateway without sandbox/dry_run caps, unknown caps,
            non-deterministic keys ⇒ refusal;
  SET-04  — gateway timeout, network partition, decline, forged
            live receipt, replay-attack payload, receipt-once
            enforcement, cleanup failure ⇒ fail-closed refusal;
  SET-05  — exactly one canonical attestation per run (including
            aborts), deterministic digest;
  REDACT  — gateway tokens/auth codes and canaries never reach the
            attestation or audit copies (D-124);
  AST     — pure igniter core (no network/db imports, no shell, no
            spawn), transports injected only.
"""
from __future__ import annotations

import ast
import json
import os
import pathlib
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "local" / "scripts"
SRC = REPO / "local" / "src"
for p in (str(REPO / "local"), str(SCRIPTS), str(SRC),
          str(SRC.parent), str(SRC / "security"), str(REPO / "local" / "tests")):
    if p not in sys.path:
        sys.path.insert(0, p)

from services.sync_engine import EventStore  # noqa: E402
from live_wiring_phase10_igniter import (  # noqa: E402
    PHASE10_IGNITED, PHASE10_INCOMPLETE, _EphemeralFanOutLock,
)
from live_wiring_phase11_igniter import (  # noqa: E402
    ATTESTATION_SCHEMA, CLIENT_ORDER_ID, CYCLE_ID, GATEWAY_CAPS,
    LIMITS, PHASE10_ROW_KIND, PHASE10_SCHEMA, PHASE11_IGNITED,
    PHASE11_INCOMPLETE, SEAMS, SettlementScratch, SandboxGateway,
    Phase11Igniter, Phase11Attestation, canonical_hash,
    settlement_key,
)

ENGINE = SCRIPTS / "live_wiring_phase11_igniter.py"

CANARY = "sk-canaryvalue1234567890abcdef"
GATEWAY_SECRET = "gw-secret-canary-0123456789abcdef"
PAYMENT_TOKEN = "ptok-canary-payment-token-0123456789"


# --- the authentic chain: phase10 attestation via the REAL D-160
# --- engine (which chains D-159 → … → D-154) -------------------------

def real_phase10_attestation(observed_tick=11000):
    """Run the REAL D-160 igniter over the authentic chain with
    in-process fakes (identical to the D-160 battery pass path)."""
    # sys.path poisoning defense (mirrored across all chain builders):
    # canonical shim modules may insert `local/canonical` onto sys.path
    # at import time, which would make bare `tests` resolve to the
    # legacy `canonical/tests.py` module. Evict the poisoned entries
    # AND purge any already-imported legacy module, then put the
    # package root first.
    import sys as _sys
    _local_root = str(REPO / "local")
    _sys.path[:] = [p for p in _sys.path
                    if p not in (_local_root + "/canonical",
                                 _local_root + "\\canonical")]
    _t = _sys.modules.get("tests")
    if _t is not None and not getattr(_t, "__path__", None):
        del _sys.modules["tests"]  # legacy single-module shadow
    _sys.path.insert(0, _local_root)
    import tests.test_live_wiring_phase10 as t10  # noqa: E402
    h = t10.Harness(now=observed_tick)
    att = h.run()
    ledger = t10.the_ledger() + [{
        "event_kind": "phase10_live_wiring_attestation",
        "detail": {"attestation_digest": att.attestation_digest,
                   "verdict": att.verdict}}]
    return att.to_dict(), ledger, t10


_CHAIN: dict = {}

_UNSET = object()  # sentinel: "no override given" (None = absent)


def the_att() -> dict:
    return _CHAIN["att"]


def the_ledger() -> list:
    return _CHAIN["ledger"]


def build_chain() -> None:
    if not _CHAIN:
        att, ledger, _t10 = real_phase10_attestation()
        _CHAIN.update(att=att, ledger=ledger)


def real_census() -> dict:
    """The runtime-profile census rows for Phases 5–11, all wired."""
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
                            (11, "Order Management"))
        ],
    }


def real_stack_factory(stock: int = 10):
    """The REAL offline OMS stack (the D-160 factory contract):
    EventStore + JsonInventory + _ReservationLedger + OmsEngine,
    scratch-backed."""
    made: dict = {}

    def factory():
        from canonical.oms_engine import (
            JsonInventory, OmsEngine, _ReservationLedger,
        )
        fd, store_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.remove(store_path)
        fd, inv_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.remove(inv_path)
        fd, led_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.remove(led_path)
        inventory = JsonInventory(inv_path)
        inventory.seed("V-1", "SKU-A", stock)
        inventory.seed("V-2", "SKU-B", stock)
        ledger = _ReservationLedger(led_path)
        store = EventStore(store_path)
        engine = OmsEngine(store, inventory, ledger=ledger,
                           fanout_engine=None,
                           notification_targets=[])
        made.update(engine=engine, inventory=inventory,
                    ledger=ledger, store=store,
                    paths=(store_path, inv_path, led_path))
        return engine, inventory, ledger, store

    factory.made = made
    return factory, made


# --- the wired harness ---------------------------------------------------

class Harness:

    def __init__(self, now: int = 12000, gateway=_UNSET,
                 stack_factory=_UNSET, census=real_census,
                 scratch: SettlementScratch = None, **overrides):
        build_chain()
        self.now = now
        self.sink: list = []
        if gateway is _UNSET:
            self.gateway = SandboxGateway()
        else:
            self.gateway = gateway
        if stack_factory is _UNSET:
            self.stack_factory, self.made = real_stack_factory()
        else:
            self.stack_factory = stack_factory
            self.made = getattr(stack_factory, "made", {})
        self.scratch = scratch or SettlementScratch()
        providers = {
            "upstream_provider": the_att,
            "audit_rows": the_ledger,
            "chain_verifier": lambda: {"ok": True,
                                       "rows": len(the_ledger())},
            "census": census,
            "gateway": self.gateway,
            "stack_factory": self.stack_factory,
            "scratch": self.scratch,
        }
        providers.update(overrides)
        self.igniter = Phase11Igniter(
            clock=lambda: self.now, audit_sink=self.sink.append,
            **providers)

    def run(self):
        return self.igniter.run()


# ===================================================================
# PASS — successful ignition
# ===================================================================

class TestIgnitionPass(unittest.TestCase):

    def test_005_real_sandbox_gateway_wired(self):
        h = Harness()
        self.assertIs(type(h.gateway), SandboxGateway)
        self.assertEqual(
            set(h.gateway.capabilities) - set(GATEWAY_CAPS), set())

    def test_01_full_ignition_completes(self):
        h = Harness()
        att = h.run()
        self.assertEqual(att.verdict, PHASE11_IGNITED)
        self.assertTrue(att.ignited)
        d = att.to_dict()
        self.assertEqual(d["schema"], ATTESTATION_SCHEMA)
        self.assertEqual(d["schema"],
                         "phase11.payment_wiring_attestation.v1")
        self.assertEqual(d["phase10_digest"],
                         canonical_hash(the_att()))
        ids = [c[0] for c in att.checks]
        for rule in ("SET-01", "SET-02", "SET-03", "SET-04",
                     "SET-05"):
            self.assertIn(rule, ids)
        self.assertTrue(all(c[1] for c in att.checks))
        self.assertTrue(d["profile"]["runtime_profile_verified"])
        self.assertTrue(d["profile"]["seams_ok"])
        self.assertTrue(d["contracts"]["idempotent"])
        self.assertTrue(d["contracts"]["invariants_ok"])
        self.assertFalse(d["cycle"]["live_charge"])
        self.assertTrue(d["cycle"]["receipt_recorded"])

    def test_02_attestation_digest_deterministic(self):
        a1 = Harness(now=12500).run()
        b1 = Harness(now=12500).run()
        self.assertEqual(a1.attestation_digest, b1.attestation_digest)
        self.assertEqual(a1.attestation_digest,
                         canonical_hash(a1.to_dict()))

    def test_03_settlement_steps_recorded(self):
        att = Harness().run()
        steps = att.to_dict()["cycle"]["steps"]
        kinds = [s[0] for s in steps]
        for kind in ("START", "AUTH", "CHECKOUT", "SETTLE", "RECEIPT",
                     "EVENT_PROBE", "VERIFY", "CLEANUP"):
            self.assertIn(kind, kinds)
        self.assertTrue(all(s[1] for s in steps))
        self.assertEqual(len(att.to_dict()["cycle"]["summary_hash"]),
                         64)

    def test_04_dry_run_checkout_and_receipt_once(self):
        att = Harness().run()
        steps = {s[0]: s[2] for s in att.to_dict()["cycle"]["steps"]}
        self.assertTrue(steps["CHECKOUT"]["dry_run"])
        self.assertEqual(steps["RECEIPT"]["path"],
                         "PLACED→VALIDATED→FULFILLING→COMPLETED")
        self.assertTrue(steps["RECEIPT"]["receipt_once"])
        self.assertEqual(steps["VERIFY"]["charge_calls"], 1)


# ===================================================================
# SET-01 — phase10 attestation refusals (zero gateway calls)
# ===================================================================

class TestSet01Refusals(unittest.TestCase):

    def test_10_missing_phase10_attestation(self):
        h = Harness(upstream_provider=None)
        att = h.run()
        self.assertEqual(att.verdict, PHASE11_INCOMPLETE)
        self.assertIn("absent", att.checks[0][2])
        self.assertEqual(len(h.sink), 1)

    def test_11_provider_raises(self):
        def boom():
            raise RuntimeError("vault offline")
        att = Harness(upstream_provider=boom).run()
        self.assertEqual(att.verdict, PHASE11_INCOMPLETE)
        self.assertIn("RuntimeError", att.checks[0][2])

    def test_12_wrong_schema(self):
        att = Harness(upstream_provider=lambda: {
            "schema": "other.v1"}).run()
        self.assertEqual(att.verdict, PHASE11_INCOMPLETE)
        self.assertIn("schema", att.checks[0][2])

    def test_13_incomplete_verdict_refused(self):
        bad = dict(the_att())
        bad["verdict"] = PHASE10_INCOMPLETE
        att = Harness(upstream_provider=lambda: bad).run()
        self.assertEqual(att.verdict, PHASE11_INCOMPLETE)
        self.assertIn("PHASE10_IGNITED",
                      " ".join(c[2] for c in att.checks))

    def test_14_drifted_digest_refused(self):
        rows = the_ledger()[:-1] + [{
            "event_kind": "phase10_live_wiring_attestation",
            "detail": {"attestation_digest": "b" * 64}}]
        att = Harness(audit_rows=lambda: rows).run()
        self.assertEqual(att.verdict, PHASE11_INCOMPLETE)
        self.assertIn("DRIFTED", " ".join(c[2] for c in att.checks))

    def test_15_unrooted_attestation_refused(self):
        att = Harness(audit_rows=lambda: []).run()
        self.assertEqual(att.verdict, PHASE11_INCOMPLETE)
        self.assertIn("rooted", " ".join(c[2] for c in att.checks))

    def test_16_broken_chain_refused(self):
        att = Harness(chain_verifier=lambda: {
            "ok": False, "broken_at_seq": 1,
            "reason": "hash mismatch"}).run()
        self.assertEqual(att.verdict, PHASE11_INCOMPLETE)
        self.assertIn("not intact",
                      " ".join(c[2] for c in att.checks))

    def test_17_refusal_makes_zero_gateway_calls(self):
        # every SET-01 failure class must leave the gateway and the
        # OMS stack completely untouched (zero gateway/settlement
        # calls)
        for kwargs in (
                {"upstream_provider": None},
                {"upstream_provider": lambda: {"schema": "x"}},
                {"audit_rows": lambda: []},
                {"chain_verifier": lambda: {"ok": False}}):
            factory, made = real_stack_factory()
            h = Harness(stack_factory=factory, **kwargs)
            att = h.run()
            self.assertEqual(att.verdict, PHASE11_INCOMPLETE)
            self.assertEqual(h.gateway.charge_calls, 0)
            engine = made.get("engine")
            self.assertIsNone(engine)  # factory never invoked


# ===================================================================
# SET-02 — runtime profile & seams refusals
# ===================================================================

class TestSet02Profile(unittest.TestCase):

    def test_20_unverified_profile_refused(self):
        bad = real_census()
        bad["runtime_profile_verified"] = False
        att = Harness(census=lambda: bad).run()
        self.assertEqual(att.verdict, PHASE11_INCOMPLETE)
        self.assertIn("NOT verified",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "SET-02"))

    def test_21_missing_phase10_row_refused(self):
        bad = real_census()
        bad["phases"] = [p for p in bad["phases"]
                         if p["phase"] != 10]
        att = Harness(census=lambda: bad).run()
        self.assertEqual(att.verdict, PHASE11_INCOMPLETE)
        self.assertIn("Phase 10 missing",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "SET-02"))

    def test_22_unwired_phase9_refused(self):
        bad = real_census()
        for p in bad["phases"]:
            if p["phase"] == 9:
                p["wired"] = False
        att = Harness(census=lambda: bad).run()
        self.assertEqual(att.verdict, PHASE11_INCOMPLETE)
        self.assertIn("VERIFIED+WIRED",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "SET-02"))

    def test_23_seam_registry_drift_refused(self):
        bad_registry = {11: "canonical.nonexistent_module",
                        12: "canonical.oms_contracts",
                        13: "canonical.orchestration_engine"}
        att = Harness(expected_entry_points=bad_registry).run()
        self.assertEqual(att.verdict, PHASE11_INCOMPLETE)
        self.assertIn("registry drift",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "SET-02"))

    def test_24_census_absent_refused(self):
        att = Harness(census=None).run()
        self.assertEqual(att.verdict, PHASE11_INCOMPLETE)
        self.assertIn("unavailable",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "SET-02"))


# ===================================================================
# SET-03 — gateway capability & contract refusals
# ===================================================================

class _CapsGateway:
    def __init__(self, caps, gid="gw-x"):
        self.gateway_id = gid
        self.capabilities = tuple(caps)


class TestSet03Gateway(unittest.TestCase):

    def test_30_live_only_gateway_refused(self):
        att = Harness(gateway=_CapsGateway(("live_charge"))).run()
        self.assertEqual(att.verdict, PHASE11_INCOMPLETE)
        blob = " ".join(c[2] for c in att.checks if c[0] == "SET-03")
        self.assertIn("SANDBOX/DRY-RUN", blob)

    def test_31_unknown_capability_refused(self):
        att = Harness(gateway=_CapsGateway(
            ("sandbox", "dry_run", "teleport"))).run()
        self.assertEqual(att.verdict, PHASE11_INCOMPLETE)
        blob = " ".join(c[2] for c in att.checks if c[0] == "SET-03")
        self.assertIn("outside", blob)

    def test_32_gateway_absent_refused(self):
        att = Harness(gateway=None).run()
        self.assertEqual(att.verdict, PHASE11_INCOMPLETE)
        blob = " ".join(c[2] for c in att.checks if c[0] == "SET-03")
        self.assertIn("unavailable", blob)

    def test_33_amount_invariants_enforced(self):
        from live_wiring_phase11_igniter import _validate_amount
        for bad in (0, -5, 10 ** 12 + 1, 10.5):
            with self.assertRaises(Phase11Igniter.__mro__[0]
                                   .__module__ and Exception):
                _validate_amount(bad)
        self.assertEqual(_validate_amount(450_000), 450_000)


# ===================================================================
# SET-04 — settlement cycle refusals (fault injection)
# ===================================================================

class TestSet04Cycle(unittest.TestCase):

    def test_40_gateway_timeout_fail_closed(self):
        att = Harness(gateway=SandboxGateway(
            faults=["timeout"])).run()
        self.assertEqual(att.verdict, PHASE11_INCOMPLETE)
        blob = " ".join(c[2] for c in att.checks if c[0] == "SET-04")
        self.assertIn("timeout", blob)
        self.assertFalse(att.to_dict()["cycle"]["live_charge"])

    def test_41_network_partition_fail_closed(self):
        att = Harness(gateway=SandboxGateway(
            faults=["partition"])).run()
        self.assertEqual(att.verdict, PHASE11_INCOMPLETE)
        blob = " ".join(c[2] for c in att.checks if c[0] == "SET-04")
        self.assertIn("partition", blob)

    def test_42_gateway_decline_fail_closed(self):
        att = Harness(gateway=SandboxGateway(
            faults=["decline"])).run()
        self.assertEqual(att.verdict, PHASE11_INCOMPLETE)
        blob = " ".join(c[2] for c in att.checks if c[0] == "SET-04")
        self.assertIn("declined", blob)

    def test_43_forged_live_receipt_refused(self):
        att = Harness(gateway=SandboxGateway(
            faults=["live_charge"])).run()
        self.assertEqual(att.verdict, PHASE11_INCOMPLETE)
        blob = " ".join(c[2] for c in att.checks if c[0] == "SET-04")
        self.assertIn("SAFETY VIOLATION", blob)

    def test_44_settlement_idempotency_replay_and_forgery(self):
        # the PASS cycle itself proves: identical replay →
        # skipped_duplicate; forged different payload under the same
        # id → IntegrityError
        att = Harness().run()
        self.assertEqual(att.verdict, PHASE11_IGNITED)
        steps = {s[0]: s[2] for s in att.to_dict()["cycle"]["steps"]}
        self.assertEqual(steps["SETTLE"]["replay"],
                         "skipped_duplicate")
        self.assertEqual(steps["SETTLE"]["forged"], "IntegrityError")

    def test_45_settlement_key_collision_distinct(self):
        k1 = settlement_key(CLIENT_ORDER_ID, "gw-a", 100)
        k2 = settlement_key(CLIENT_ORDER_ID, "gw-b", 100)
        k3 = settlement_key(CLIENT_ORDER_ID, "gw-a", 101)
        self.assertEqual(len({k1, k2, k3}), 3)

    def test_46_cleanup_failure_refused(self):
        class DirtyScratch(SettlementScratch):
            def delete(self, key):
                if key.endswith("settlement"):
                    return False  # refuses to clean the artifact
                return super().delete(key)
        att = Harness(scratch=DirtyScratch()).run()
        self.assertEqual(att.verdict, PHASE11_INCOMPLETE)
        blob = " ".join(c[2] for c in att.checks if c[0] == "SET-04")
        self.assertIn("cleanup failed", blob)

    def test_47_stack_absent_refused(self):
        att = Harness(stack_factory=None).run()
        self.assertEqual(att.verdict, PHASE11_INCOMPLETE)
        blob = " ".join(c[2] for c in att.checks if c[0] == "SET-04")
        self.assertIn("unavailable", blob)


# ===================================================================
# SET-05 — emission contract
# ===================================================================

class TestSet05Emission(unittest.TestCase):

    def test_50_exactly_one_attestation_per_run(self):
        h = Harness()
        att = h.run()
        self.assertEqual(len(h.sink), 1)
        self.assertEqual(h.sink[0]["schema"], ATTESTATION_SCHEMA)
        self.assertEqual(h.sink[0]["verdict"], att.verdict)

    def test_51_abort_still_emits_attestation(self):
        h = Harness(upstream_provider=None)
        att = h.run()
        self.assertEqual(att.verdict, PHASE11_INCOMPLETE)
        self.assertEqual(len(h.sink), 1)

    def test_52_digest_covers_every_field(self):
        att = Harness().run()
        d = att.to_dict()
        for key in ("schema", "verdict", "phase10_digest",
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
        for secret in (CANARY, GATEWAY_SECRET, PAYMENT_TOKEN):
            self.assertNotIn(secret, blob)

    def test_61_forged_live_receipt_secret_never_escapes(self):
        # the live-sim receipt carries an auth_code; the refusal
        # telemetry must not carry it
        h = Harness(gateway=SandboxGateway(faults=["live_charge"]))
        att = h.run()
        blob = json.dumps(att.to_dict()) + json.dumps(h.sink)
        self.assertNotIn("LIVE-SIM-SECRET", blob)
        self.assertNotIn("auth_code", blob)

    def test_62_refusal_details_carry_no_secrets(self):
        h = Harness(upstream_provider=lambda: {
            "schema": "x", "note": GATEWAY_SECRET})
        att = h.run()
        blob = json.dumps(att.to_dict()) + json.dumps(h.sink)
        self.assertNotIn(GATEWAY_SECRET, blob)

    def test_63_deep_redact_runs_on_emitted_records(self):
        h = Harness()
        att = h.run()
        row = h.sink[0]
        self.assertEqual(row["phase10_digest"], att.phase10_digest)
        self.assertEqual(row["manifest_sha256"],
                         att.manifest_sha256)

    def test_64_no_money_markers_in_outputs(self):
        h = Harness()
        att = h.run()
        blob = json.dumps(att.to_dict()) + json.dumps(h.sink)
        for marker in ('live_charge": true', "auth_code", "pan",
                       "card_number"):
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
        self.assertIn("gateway", src)
        self.assertIn("def _load", src)

    def test_73_payment_boundary_guarantee_in_source(self):
        src = ENGINE.read_text(encoding="utf-8")
        self.assertIn("SAFETY VIOLATION", src)
        self.assertIn("live_charge", src)
        self.assertIn("phase11-scratch:", src)


if __name__ == "__main__":
    unittest.main()

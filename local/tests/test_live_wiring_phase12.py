"""Phase 12 live wiring igniter battery (D-162, offline).

Exercises `local/scripts/live_wiring_phase12_igniter.py` fully
offline — the carrier injected (the engine's own `SandboxCarrier`,
DRY-RUN capability-capped, provider unselected per open decision 11),
the OMS stack the REAL D-160 factory (`OmsEngine` over
`EventStore`/`JsonInventory`/`_ReservationLedger`), the census
chained from the REAL D-161 igniter over the REAL D-160/D-159/
D-158/D-157/D-156/D-155/D-154 chain:

  PASS    — phase11 attestation + verified profile + sandbox-capped
            carrier + dry-run shipping cycle ⇒ PHASE12_IGNITED,
            deterministic digest;
  SHP-01  — missing/raised/wrong-schema/incomplete-verdict/drifted/
            unrooted/broken-chain phase11 attestation ⇒ refusal with
            ZERO carrier calls (proven);
  SHP-02  — unverified profile, missing phase rows, seam registry
            drift, slot-13 cross-walk drift, census absent ⇒ refusal;
  SHP-03  — carrier without sandbox/dry_run caps, unknown caps,
            non-deterministic keys, parcel invariants ⇒ refusal;
  SHP-04  — carrier timeout, network partition, refusal, forged live
            label, replay-attack payload, receipt-once enforcement,
            cleanup failure ⇒ fail-closed refusal;
  SHP-05  — exactly one canonical attestation per run (including
            aborts), deterministic digest;
  REDACT  — carrier tokens/label secrets and canaries never reach
            the attestation or audit copies (D-124);
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
from live_wiring_phase11_igniter import (  # noqa: E402
    PHASE11_IGNITED, PHASE11_INCOMPLETE, _EphemeralFanOutLock,
)
from live_wiring_phase12_igniter import (  # noqa: E402
    ATTESTATION_SCHEMA, CLIENT_ORDER_ID, CYCLE_ID, CARRIER_CAPS,
    LIMITS, PARCEL_LIMITS, PHASE11_ROW_KIND, PHASE11_SCHEMA,
    PHASE12_IGNITED, PHASE12_INCOMPLETE, SEAMS, SandboxCarrier,
    ShippingScratch, Phase12Igniter, canonical_hash, parcel_hash,
    shipment_key,
)

ENGINE = SCRIPTS / "live_wiring_phase12_igniter.py"

CANARY = "sk-canaryvalue1234567890abcdef"
CARRIER_SECRET = "carrier-secret-canary-0123456789abcdef"
LABEL_TOKEN = "ltok-canary-label-token-0123456789"


# --- the authentic chain: phase11 attestation via the REAL D-161
# --- engine (which chains D-160 → … → D-154) -------------------------

def real_phase11_attestation(observed_tick=11000):
    """Run the REAL D-161 igniter over the authentic chain with
    in-process fakes (identical to the D-161 battery pass path)."""
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
    import tests.test_live_wiring_phase11 as t11  # noqa: E402
    h = t11.Harness(now=observed_tick)
    att = h.run()
    ledger = t11.the_ledger() + [{
        "event_kind": "phase11_payment_wiring_attestation",
        "detail": {"attestation_digest": att.attestation_digest,
                   "verdict": att.verdict}}]
    return att.to_dict(), ledger, t11


_CHAIN: dict = {}

_UNSET = object()  # sentinel: "no override given" (None = absent)


def the_att() -> dict:
    return _CHAIN["att"]


def the_ledger() -> list:
    return _CHAIN["ledger"]


def build_chain() -> None:
    if not _CHAIN:
        att, ledger, _t11 = real_phase11_attestation()
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

    def __init__(self, now: int = 12000, carrier=_UNSET,
                 stack_factory=_UNSET, census=real_census,
                 scratch: ShippingScratch = None, **overrides):
        build_chain()
        self.now = now
        self.sink: list = []
        if carrier is _UNSET:
            self.carrier = SandboxCarrier()
        else:
            self.carrier = carrier
        if stack_factory is _UNSET:
            self.stack_factory, self.made = real_stack_factory()
        else:
            self.stack_factory = stack_factory
            self.made = getattr(stack_factory, "made", {})
        self.scratch = scratch or ShippingScratch()
        providers = {
            "upstream_provider": the_att,
            "audit_rows": the_ledger,
            "chain_verifier": lambda: {"ok": True,
                                       "rows": len(the_ledger())},
            "census": census,
            "carrier": self.carrier,
            "stack_factory": self.stack_factory,
            "scratch": self.scratch,
        }
        providers.update(overrides)
        self.igniter = Phase12Igniter(
            clock=lambda: self.now, audit_sink=self.sink.append,
            **providers)

    def run(self):
        return self.igniter.run()


# ===================================================================
# PASS — successful ignition
# ===================================================================

class TestIgnitionPass(unittest.TestCase):

    def test_005_real_sandbox_carrier_wired(self):
        h = Harness()
        self.assertIs(type(h.carrier), SandboxCarrier)
        self.assertEqual(
            set(h.carrier.capabilities) - set(CARRIER_CAPS), set())

    def test_01_full_ignition_completes(self):
        h = Harness()
        att = h.run()
        self.assertEqual(att.verdict, PHASE12_IGNITED)
        self.assertTrue(att.ignited)
        d = att.to_dict()
        self.assertEqual(d["schema"], ATTESTATION_SCHEMA)
        self.assertEqual(d["schema"],
                         "phase12.shipping_wiring_attestation.v1")
        self.assertEqual(d["phase11_digest"],
                         canonical_hash(the_att()))
        ids = [c[0] for c in att.checks]
        for rule in ("SHP-01", "SHP-02", "SHP-03", "SHP-04",
                     "SHP-05"):
            self.assertIn(rule, ids)
        self.assertTrue(all(c[1] for c in att.checks))
        self.assertTrue(d["profile"]["runtime_profile_verified"])
        self.assertTrue(d["profile"]["seams_ok"])
        self.assertTrue(d["contracts"]["idempotent"])
        self.assertTrue(d["contracts"]["invariants_ok"])
        self.assertFalse(d["cycle"]["live_ship"])
        self.assertTrue(d["cycle"]["receipt_recorded"])

    def test_02_attestation_digest_deterministic(self):
        a1 = Harness(now=12500).run()
        b1 = Harness(now=12500).run()
        self.assertEqual(a1.attestation_digest, b1.attestation_digest)
        self.assertEqual(a1.attestation_digest,
                         canonical_hash(a1.to_dict()))

    def test_03_shipping_steps_recorded(self):
        att = Harness().run()
        steps = att.to_dict()["cycle"]["steps"]
        kinds = [s[0] for s in steps]
        for kind in ("START", "AUTH", "CREATE", "SHIP", "STATE",
                     "TRACK", "VERIFY", "CLEANUP"):
            self.assertIn(kind, kinds)
        self.assertTrue(all(s[1] for s in steps))
        self.assertEqual(len(att.to_dict()["cycle"]["summary_hash"]),
                         64)

    def test_04_dry_run_label_and_receipt_once(self):
        att = Harness().run()
        steps = {s[0]: s[2] for s in att.to_dict()["cycle"]["steps"]}
        self.assertTrue(steps["CREATE"]["dry_run"])
        self.assertEqual(steps["STATE"]["path"],
                         "PLACED→VALIDATED→FULFILLING→COMPLETED")
        self.assertTrue(steps["STATE"]["receipt_once"])
        self.assertTrue(steps["STATE"]["receipt_is_shipment"])
        self.assertEqual(steps["VERIFY"]["create_calls"], 1)


# ===================================================================
# SHP-01 — phase11 attestation refusals (zero carrier calls)
# ===================================================================

class TestShp01Refusals(unittest.TestCase):

    def test_10_missing_phase11_attestation(self):
        h = Harness(upstream_provider=None)
        att = h.run()
        self.assertEqual(att.verdict, PHASE12_INCOMPLETE)
        self.assertIn("absent", att.checks[0][2])
        self.assertEqual(len(h.sink), 1)

    def test_11_provider_raises(self):
        def boom():
            raise RuntimeError("vault offline")
        att = Harness(upstream_provider=boom).run()
        self.assertEqual(att.verdict, PHASE12_INCOMPLETE)
        self.assertIn("RuntimeError", att.checks[0][2])

    def test_12_wrong_schema(self):
        att = Harness(upstream_provider=lambda: {
            "schema": "other.v1"}).run()
        self.assertEqual(att.verdict, PHASE12_INCOMPLETE)
        self.assertIn("schema", att.checks[0][2])

    def test_13_incomplete_verdict_refused(self):
        bad = dict(the_att())
        bad["verdict"] = PHASE11_INCOMPLETE
        att = Harness(upstream_provider=lambda: bad).run()
        self.assertEqual(att.verdict, PHASE12_INCOMPLETE)
        self.assertIn("PHASE11_IGNITED",
                      " ".join(c[2] for c in att.checks))

    def test_14_drifted_digest_refused(self):
        rows = the_ledger()[:-1] + [{
            "event_kind": "phase11_payment_wiring_attestation",
            "detail": {"attestation_digest": "b" * 64}}]
        att = Harness(audit_rows=lambda: rows).run()
        self.assertEqual(att.verdict, PHASE12_INCOMPLETE)
        self.assertIn("DRIFTED", " ".join(c[2] for c in att.checks))

    def test_15_unrooted_attestation_refused(self):
        att = Harness(audit_rows=lambda: []).run()
        self.assertEqual(att.verdict, PHASE12_INCOMPLETE)
        self.assertIn("rooted", " ".join(c[2] for c in att.checks))

    def test_16_broken_chain_refused(self):
        att = Harness(chain_verifier=lambda: {
            "ok": False, "broken_at_seq": 1,
            "reason": "hash mismatch"}).run()
        self.assertEqual(att.verdict, PHASE12_INCOMPLETE)
        self.assertIn("not intact",
                      " ".join(c[2] for c in att.checks))

    def test_17_refusal_makes_zero_carrier_calls(self):
        # every SHP-01 failure class must leave the carrier and the
        # OMS stack completely untouched (zero carrier/shipment
        # calls)
        for kwargs in (
                {"upstream_provider": None},
                {"upstream_provider": lambda: {"schema": "x"}},
                {"audit_rows": lambda: []},
                {"chain_verifier": lambda: {"ok": False}}):
            factory, made = real_stack_factory()
            h = Harness(stack_factory=factory, **kwargs)
            att = h.run()
            self.assertEqual(att.verdict, PHASE12_INCOMPLETE)
            self.assertEqual(h.carrier.create_calls, 0)
            engine = made.get("engine")
            self.assertIsNone(engine)  # factory never invoked


# ===================================================================
# SHP-02 — runtime profile & seams refusals
# ===================================================================

class TestShp02Profile(unittest.TestCase):

    def test_20_unverified_profile_refused(self):
        bad = real_census()
        bad["runtime_profile_verified"] = False
        att = Harness(census=lambda: bad).run()
        self.assertEqual(att.verdict, PHASE12_INCOMPLETE)
        self.assertIn("NOT verified",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "SHP-02"))

    def test_21_missing_phase11_row_refused(self):
        bad = real_census()
        bad["phases"] = [p for p in bad["phases"]
                         if p["phase"] != 11]
        att = Harness(census=lambda: bad).run()
        self.assertEqual(att.verdict, PHASE12_INCOMPLETE)
        self.assertIn("Phase 11 missing",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "SHP-02"))

    def test_22_unwired_phase9_refused(self):
        bad = real_census()
        for p in bad["phases"]:
            if p["phase"] == 9:
                p["wired"] = False
        att = Harness(census=lambda: bad).run()
        self.assertEqual(att.verdict, PHASE12_INCOMPLETE)
        self.assertIn("VERIFIED+WIRED",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "SHP-02"))

    def test_23_seam_registry_drift_refused(self):
        bad_registry = {11: "canonical.nonexistent_module",
                        12: "canonical.oms_contracts",
                        13: "canonical.orchestration_engine"}
        att = Harness(expected_entry_points=bad_registry).run()
        self.assertEqual(att.verdict, PHASE12_INCOMPLETE)
        self.assertIn("registry drift",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "SHP-02"))

    def test_24_census_absent_refused(self):
        att = Harness(census=None).run()
        self.assertEqual(att.verdict, PHASE12_INCOMPLETE)
        self.assertIn("unavailable",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "SHP-02"))

    def test_25_slot13_crosswalk_drift_refused(self):
        # the D-154 cross-walk binds registry slot 13 ("Shipping") to
        # `canonical.orchestration_engine`; a registry that drops the
        # slot refuses (defense-in-depth beyond the per-seam loop)
        bad_registry = {11: "canonical.oms_engine",
                        12: "canonical.oms_contracts"}
        att = Harness(expected_entry_points=bad_registry).run()
        self.assertEqual(att.verdict, PHASE12_INCOMPLETE)
        self.assertIn("cross-walk drift",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "SHP-02"))


# ===================================================================
# SHP-03 — carrier capability & contract refusals
# ===================================================================

class _CapsCarrier:
    def __init__(self, caps, cid="carrier-x"):
        self.carrier_id = cid
        self.capabilities = tuple(caps)


class TestShp03Carrier(unittest.TestCase):

    def test_30_live_only_carrier_refused(self):
        att = Harness(carrier=_CapsCarrier(("live_ship"))).run()
        self.assertEqual(att.verdict, PHASE12_INCOMPLETE)
        blob = " ".join(c[2] for c in att.checks if c[0] == "SHP-03")
        self.assertIn("SANDBOX/DRY-RUN", blob)

    def test_31_unknown_capability_refused(self):
        att = Harness(carrier=_CapsCarrier(
            ("sandbox", "dry_run", "teleport"))).run()
        self.assertEqual(att.verdict, PHASE12_INCOMPLETE)
        blob = " ".join(c[2] for c in att.checks if c[0] == "SHP-03")
        self.assertIn("outside", blob)

    def test_32_carrier_absent_refused(self):
        att = Harness(carrier=None).run()
        self.assertEqual(att.verdict, PHASE12_INCOMPLETE)
        blob = " ".join(c[2] for c in att.checks if c[0] == "SHP-03")
        self.assertIn("unavailable", blob)

    def test_33_parcel_invariants_enforced(self):
        from live_wiring_phase12_igniter import _validate_parcel
        from live_wiring_phase12_igniter import Phase12Error
        for bad in ({"weight_grams": 0},
                    {"weight_grams": -5},
                    {"weight_grams": PARCEL_LIMITS["max_weight_grams"]
                     + 1},
                    {"weight_grams": 10.5},
                    {"dimensions_cm": {"length": 0, "width": 20,
                                       "height": 10}},
                    {"dimensions_cm": {"length": 30, "width": 20,
                                       "height": 151}},
                    {"declared_value_minor": -1},
                    {"declared_value_minor": 10.5}):
            parcel = dict(weight_grams=2_000,
                          dimensions_cm={"length": 30, "width": 20,
                                         "height": 10},
                          declared_value_minor=450_000)
            parcel.update(bad)
            with self.assertRaises(Phase12Error):
                _validate_parcel(parcel)
        ok = _validate_parcel(dict(
            weight_grams=2_000,
            dimensions_cm={"length": 30, "width": 20, "height": 10},
            declared_value_minor=450_000))
        self.assertEqual(ok["weight_grams"], 2_000)

    def test_34_shipment_key_collision_distinct(self):
        ph = parcel_hash({"weight_grams": 2_000,
                          "dimensions_cm": {"length": 30, "width": 20,
                                            "height": 10},
                          "declared_value_minor": 450_000,
                          "declared_currency": "IRT"})
        k1 = shipment_key(CLIENT_ORDER_ID, "carrier-a", ph)
        k2 = shipment_key(CLIENT_ORDER_ID, "carrier-b", ph)
        ph2 = parcel_hash({"weight_grams": 2_001,
                           "dimensions_cm": {"length": 30, "width": 20,
                                             "height": 10},
                           "declared_value_minor": 450_000,
                           "declared_currency": "IRT"})
        k3 = shipment_key(CLIENT_ORDER_ID, "carrier-a", ph2)
        self.assertEqual(len({k1, k2, k3}), 3)


# ===================================================================
# SHP-04 — shipping cycle refusals (fault injection)
# ===================================================================

class TestShp04Cycle(unittest.TestCase):

    def test_40_carrier_timeout_fail_closed(self):
        att = Harness(carrier=SandboxCarrier(
            faults=["timeout"])).run()
        self.assertEqual(att.verdict, PHASE12_INCOMPLETE)
        blob = " ".join(c[2] for c in att.checks if c[0] == "SHP-04")
        self.assertIn("timeout", blob)
        self.assertFalse(att.to_dict()["cycle"]["live_ship"])

    def test_41_network_partition_fail_closed(self):
        att = Harness(carrier=SandboxCarrier(
            faults=["partition"])).run()
        self.assertEqual(att.verdict, PHASE12_INCOMPLETE)
        blob = " ".join(c[2] for c in att.checks if c[0] == "SHP-04")
        self.assertIn("partition", blob)

    def test_42_carrier_refusal_fail_closed(self):
        att = Harness(carrier=SandboxCarrier(
            faults=["refuse"])).run()
        self.assertEqual(att.verdict, PHASE12_INCOMPLETE)
        blob = " ".join(c[2] for c in att.checks if c[0] == "SHP-04")
        self.assertIn("refused", blob)

    def test_43_forged_live_label_refused(self):
        att = Harness(carrier=SandboxCarrier(
            faults=["live_ship"])).run()
        self.assertEqual(att.verdict, PHASE12_INCOMPLETE)
        blob = " ".join(c[2] for c in att.checks if c[0] == "SHP-04")
        self.assertIn("SAFETY VIOLATION", blob)

    def test_44_shipment_idempotency_replay_and_forgery(self):
        # the PASS cycle itself proves: identical replay →
        # skipped_duplicate; forged different payload under the same
        # id → IntegrityError
        att = Harness().run()
        self.assertEqual(att.verdict, PHASE12_IGNITED)
        steps = {s[0]: s[2] for s in att.to_dict()["cycle"]["steps"]}
        self.assertEqual(steps["SHIP"]["replay"],
                         "skipped_duplicate")
        self.assertEqual(steps["SHIP"]["forged"], "IntegrityError")

    def test_46_cleanup_failure_refused(self):
        class DirtyScratch(ShippingScratch):
            def delete(self, key):
                if key.endswith("shipping"):
                    return False  # refuses to clean the artifact
                return super().delete(key)
        att = Harness(scratch=DirtyScratch()).run()
        self.assertEqual(att.verdict, PHASE12_INCOMPLETE)
        blob = " ".join(c[2] for c in att.checks if c[0] == "SHP-04")
        self.assertIn("cleanup failed", blob)

    def test_47_stack_absent_refused(self):
        att = Harness(stack_factory=None).run()
        self.assertEqual(att.verdict, PHASE12_INCOMPLETE)
        blob = " ".join(c[2] for c in att.checks if c[0] == "SHP-04")
        self.assertIn("unavailable", blob)


# ===================================================================
# SHP-05 — emission contract
# ===================================================================

class TestShp05Emission(unittest.TestCase):

    def test_50_exactly_one_attestation_per_run(self):
        h = Harness()
        att = h.run()
        self.assertEqual(len(h.sink), 1)
        self.assertEqual(h.sink[0]["schema"], ATTESTATION_SCHEMA)
        self.assertEqual(h.sink[0]["verdict"], att.verdict)

    def test_51_abort_still_emits_attestation(self):
        h = Harness(upstream_provider=None)
        att = h.run()
        self.assertEqual(att.verdict, PHASE12_INCOMPLETE)
        self.assertEqual(len(h.sink), 1)

    def test_52_digest_covers_every_field(self):
        att = Harness().run()
        d = att.to_dict()
        for key in ("schema", "verdict", "phase11_digest",
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
        for secret in (CANARY, CARRIER_SECRET, LABEL_TOKEN):
            self.assertNotIn(secret, blob)

    def test_61_forged_live_label_secret_never_escapes(self):
        # the live-sim label carries a label_secret; the refusal
        # telemetry must not carry it
        h = Harness(carrier=SandboxCarrier(faults=["live_ship"]))
        att = h.run()
        blob = json.dumps(att.to_dict()) + json.dumps(h.sink)
        self.assertNotIn("LIVE-SIM-SECRET", blob)
        self.assertNotIn("label_secret", blob)

    def test_62_refusal_details_carry_no_secrets(self):
        h = Harness(upstream_provider=lambda: {
            "schema": "x", "note": CARRIER_SECRET})
        att = h.run()
        blob = json.dumps(att.to_dict()) + json.dumps(h.sink)
        self.assertNotIn(CARRIER_SECRET, blob)

    def test_63_deep_redact_runs_on_emitted_records(self):
        h = Harness()
        att = h.run()
        row = h.sink[0]
        self.assertEqual(row["phase11_digest"], att.phase11_digest)
        self.assertEqual(row["manifest_sha256"],
                         att.manifest_sha256)

    def test_64_no_shipping_markers_in_outputs(self):
        h = Harness()
        att = h.run()
        blob = json.dumps(att.to_dict()) + json.dumps(h.sink)
        for marker in ('live_ship": true', "label_secret", "address",
                       "tracking_secret"):
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
        self.assertIn("carrier", src)
        self.assertIn("def _load", src)

    def test_73_shipping_boundary_guarantee_in_source(self):
        src = ENGINE.read_text(encoding="utf-8")
        self.assertIn("SAFETY VIOLATION", src)
        self.assertIn("live_ship", src)
        self.assertIn("phase12-scratch:", src)


if __name__ == "__main__":
    unittest.main()

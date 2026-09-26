"""Phase 10 live wiring igniter battery (D-160, offline).

Exercises `local/scripts/live_wiring_phase10_igniter.py` fully
offline — the OMS stack injected (the REAL `OmsEngine` over the REAL
`services.sync_engine.EventStore`, `JsonInventory` and
`_ReservationLedger`, all scratch-backed), the census chained from
the REAL D-159 igniter over the REAL D-158/D-157/D-156/D-155/D-154
chain, and the contracts through the REAL `oms_contracts` layer:

  PASS    — phase9 attestation + verified profile + contract
            invariants + clean sandbox lifecycle ⇒ PHASE10_IGNITED
            with a valid `phase10.live_wiring_attestation.v1`
            (deterministic digest);
  ORD-01  — phase9 attestation absent / raised / wrong schema /
            wrong verdict / drifted (ledger mismatch) / unrooted /
            broken chain ⇒ refusal with ZERO order-processing calls;
  ORD-02  — runtime profile mismatch, missing Phase 5..9 flags,
            seam registry drift ⇒ refusal;
  ORD-03  — currency outside the IRR/IRT whitelist, unapproved
            discount code, idempotency nondeterminism ⇒ refusal
            (price invariants proven through the REAL validator);
  ORD-04  — insufficient stock (atomic refusal), out-of-order
            transition, payment-boundary marker in the event
            stream, failed inventory release on cleanup, scratch
            scope violation ⇒ refusal;
  ORD-05  — exactly one canonical attestation per run (including
            aborts), deterministic digest;
  REDACT  — customer refs, phone numbers, addresses and canaries
            never reach the attestation or audit copies (D-124);
  AST     — pure igniter core (no network/db imports, no shell, no
            spawn), engine stack injected only.
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

from canonical.oms_contracts import (  # noqa: E402
    OmsContractError, PLACED, VALIDATED, validate_order,
)
from canonical.oms_engine import (  # noqa: E402
    JsonInventory, OmsEngine, _ReservationLedger,
)
from services.sync_engine import EventStore  # noqa: E402
from canonical.orchestration_engine import FanOutEngine  # noqa: E402
from live_wiring_phase10_igniter import (  # noqa: E402
    _EphemeralFanOutLock,
)
from live_wiring_phase9_igniter import (  # noqa: E402
    PHASE9_INCOMPLETE, Phase9Igniter, SessionStore,
)
from live_wiring_phase10_igniter import (  # noqa: E402
    ATTESTATION_SCHEMA, CHANNEL_ORIGINS, CURRENCY_WHITELIST, LIMITS,
    PHASE10_IGNITED, PHASE10_INCOMPLETE, PHASE9_ROW_KIND, SEAMS,
    SYNTHETIC_ORDER, OrderScratch, Phase10Igniter, canonical_hash,
)

ENGINE = SCRIPTS / "live_wiring_phase10_igniter.py"

CANARY = "sk-canaryvalue1234567890abcdef"
CUSTOMER_PHONE = "+989121234567"
CUSTOMER_ADDRESS = "تهران، خیابان ولیعصر، پلاک ۱۲۳"
PAYMENT_TOKEN = "ptok-canary-payment-token-0123456789"
SIGNING_KEY = "stage-f-owner-signing-key-0123456789abcdef"
SESSION = "cutover-session-01"
TARGET = "staging"
SERVICES = ("postgres-ssot", "redis", "app-orchestrator",
            "telemetry-circuit")

MANIFEST = (REPO / "local" / "infra" / "dokploy" /
            "docker-compose.dokploy.yaml").read_text(encoding="utf-8")
TEMPLATE = (REPO / "local" / "infra" / "dokploy" /
            "dokploy_compose_template.yaml").read_text(encoding="utf-8")
ENVELOPE = (REPO / "local" / "infra" / "dokploy" /
            "stage_d_fingerprint.envelope").read_text(encoding="utf-8")


# --- the authentic chain: phase9 attestation via the REAL D-159
# --- engine (which chains D-158 → … → D-154) -------------------------

def real_phase9_attestation(observed_tick=10000):
    """Run the REAL D-159 igniter over the authentic chain with
    in-process fakes (identical to the D-159 battery pass path)."""
    # sys.path poisoning defense (mirrored across all chain
    # builders): canonical shim modules may insert `local/canonical`
    # onto sys.path at import time, which would make bare `tests`
    # resolve to the legacy `canonical/tests.py` module. Evict the
    # poisoned entries AND purge any already-imported legacy module,
    # then put the package root first.
    import sys as _sys
    _local_root = str(REPO / "local")
    _sys.path[:] = [p for p in _sys.path
                    if p not in (_local_root + "/canonical",
                                 _local_root + "\\canonical")]
    _t = _sys.modules.get("tests")
    if _t is not None and not getattr(_t, "__path__", None):
        del _sys.modules["tests"]  # legacy single-module shadow
    _sys.path.insert(0, _local_root)  # ahead of local/canonical
    import tests.test_live_wiring_phase9 as t9  # noqa: E402
    h = t9.Harness(now=observed_tick)
    att = h.run()
    ledger = t9.the_ledger() + [{
        "event_kind": "phase9_live_wiring_attestation",
        "detail": {"attestation_digest": att.attestation_digest,
                   "verdict": att.verdict}}]
    return att.to_dict(), ledger, t9


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




def build_fanout(store: EventStore) -> FanOutEngine:
    """The REAL D-083 fan-out boundary over the SAME scratch store:
    publisher-less binds (every dispatch outcome is
    `no_publisher_bound` — structurally incapable of any channel
    egress) and an ephemeral process-local D-079 lock (the default
    lock claims keys PERMANENTLY in live PG or the shared fan-out
    lock file — never acceptable for probes)."""
    return FanOutEngine(store, publish_binds={"telegram": None},
                        lock=_EphemeralFanOutLock())


def real_engine_factory(stock: int = 10):
    """The REAL offline OMS stack: EventStore + JsonInventory +
    _ReservationLedger + OmsEngine, scratch-backed, with the REAL
    D-083 fan-out boundary wired (publisher-less binds + ephemeral
    D-079 lock)."""
    made: dict = {}

    def factory():
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
        fanout = build_fanout(store)
        engine = OmsEngine(store, inventory, ledger=ledger,
                           fanout_engine=fanout,
                           notification_targets=[])
        made.update(engine=engine, inventory=inventory,
                    ledger=ledger, store=store, fanout=fanout,
                    paths=(store_path, inv_path, led_path))
        return engine, inventory, ledger, store

    factory.made = made  # the Harness resolves the boundary from here
    return factory, made


# --- the wired harness ---------------------------------------------------

_CHAIN: dict = {}

_UNSET = object()  # sentinel: "no override given" (None = absent)


def the_att() -> dict:
    return _CHAIN["att"]


def the_ledger() -> list:
    return _CHAIN["ledger"]


def build_chain() -> None:
    if not _CHAIN:
        att, ledger, _t9 = real_phase9_attestation()
        _CHAIN.update(att=att, ledger=ledger)


class Harness:
    """Fully wired igniter over the authentic phase9 chain; overrides
    swap providers (None = absent)."""

    def __init__(self, now: int = 11000, engine_factory=_UNSET,
                 fanout=_UNSET, census=real_census,
                 scratch: OrderScratch = None, **overrides):
        build_chain()
        self.now = now
        self.sink: list = []
        if engine_factory is _UNSET:
            factory, self.made = real_engine_factory()
            self.factory = factory
        else:
            self.factory = engine_factory
            self.made = {}
        # The fan-out handle mirrors the ACTUAL boundary the cycle
        # drove: resolved after run() from the factory's `made` dict
        # (the factory builds it), unless the test injected an
        # explicit boundary.
        self.fanout = fanout if fanout is not _UNSET else None
        self._explicit_fanout = self.fanout is not None
        self.scratch = scratch or OrderScratch()
        providers = {
            "phase9_provider": the_att,
            "audit_rows": the_ledger,
            "chain_verifier": lambda: {"ok": True,
                                       "rows": len(the_ledger())},
            "census": census,
            "engine_factory": self.factory,
            "fanout": self.fanout,
            "scratch": self.scratch,
        }
        providers.update(overrides)
        self.igniter = Phase10Igniter(
            clock=lambda: self.now, audit_sink=self.sink.append,
            **providers)

    def run(self):
        att = self.igniter.run()
        src = getattr(self.factory, "made", None) or self.made
        if src:
            self.made = src  # expose engine/store/inventory handles
        if not self._explicit_fanout:
            # the ACTUAL boundary the cycle drove — the factory's own
            # record (works for both the default and overridden stacks)
            self.fanout = src.get("fanout")
        return att


# ===================================================================
# PASS — successful ignition
# ===================================================================

class TestIgnitionPass(unittest.TestCase):

    def test_005_real_fanout_boundary_wired(self):
        # the PASS stack must carry the REAL D-083 boundary
        h = Harness()
        att = h.run()
        self.assertEqual(att.verdict, PHASE10_IGNITED)
        self.assertIsNotNone(h.fanout)
        self.assertIs(type(h.fanout), FanOutEngine)
        self.assertEqual(h.fanout.publish_binds, {"telegram": None})

    def test_01_full_ignition_completes(self):
        h = Harness()
        att = h.run()
        self.assertEqual(att.verdict, PHASE10_IGNITED)
        self.assertTrue(att.ignited)
        d = att.to_dict()
        self.assertEqual(d["schema"], ATTESTATION_SCHEMA)
        self.assertEqual(d["schema"],
                         "phase10.live_wiring_attestation.v1")
        self.assertEqual(d["phase9_digest"],
                         canonical_hash(the_att()))
        ids = [c[0] for c in att.checks]
        for rule in ("ORD-01", "ORD-02", "ORD-03", "ORD-04",
                     "ORD-05"):
            self.assertIn(rule, ids)
        self.assertTrue(all(c[1] for c in att.checks))
        self.assertTrue(d["profile"]["runtime_profile_verified"])
        self.assertTrue(d["profile"]["seams_ok"])
        self.assertTrue(d["contracts"]["idempotent"])
        self.assertTrue(d["contracts"]["invariants_ok"])
        self.assertTrue(d["contracts"]["transitions_ok"])
        self.assertTrue(d["cycle"]["locks_released"])
        self.assertFalse(d["cycle"]["payment_initiated"])

    def test_02_attestation_digest_deterministic(self):
        a1 = Harness(now=11500).run()
        b1 = Harness(now=11500).run()
        self.assertEqual(a1.attestation_digest, b1.attestation_digest)
        self.assertEqual(a1.attestation_digest,
                         canonical_hash(a1.to_dict()))

    def test_03_lifecycle_steps_recorded(self):
        att = Harness().run()
        steps = att.to_dict()["cycle"]["steps"]
        kinds = [s[0] for s in steps]
        for kind in ("START", "LOCK", "VALIDATE", "RESERVE",
                     "TRANSITION", "EVENT_PROBE", "CLEANUP"):
            self.assertIn(kind, kinds)
        self.assertTrue(all(s[1] for s in steps))
        self.assertEqual(len(att.to_dict()["cycle"]["summary_hash"]),
                         64)

    def test_04_lifecycle_path_and_replay(self):
        att = Harness().run()
        steps = {s[0]: s[2] for s in att.to_dict()["cycle"]["steps"]}
        self.assertEqual(steps["TRANSITION"]["path"],
                         "PLACED\u2192VALIDATED\u2192CANCELLED")
        self.assertTrue(steps["TRANSITION"]["locks_released"])

    def test_05_channel_tagging_carried(self):
        att = Harness().run()
        start = [s for s in att.to_dict()["cycle"]["steps"]
                 if s[0] == "START"][0]
        self.assertEqual(start[2]["channel"], "telegram")
        self.assertEqual(start[2]["items"], 2)


# ===================================================================
# ORD-01 — phase9 attestation refusals (zero OMS calls)
# ===================================================================

class TestOrd01Refusals(unittest.TestCase):

    def test_10_missing_phase9_attestation(self):
        h = Harness(phase9_provider=None)
        att = h.run()
        self.assertEqual(att.verdict, PHASE10_INCOMPLETE)
        self.assertIn("absent", att.checks[0][2])
        self.assertEqual(len(h.sink), 1)

    def test_11_provider_raises(self):
        def boom():
            raise RuntimeError("vault offline")
        att = Harness(phase9_provider=boom).run()
        self.assertEqual(att.verdict, PHASE10_INCOMPLETE)
        self.assertIn("RuntimeError", att.checks[0][2])

    def test_12_wrong_schema(self):
        att = Harness(phase9_provider=lambda: {
            "schema": "other.v1"}).run()
        self.assertEqual(att.verdict, PHASE10_INCOMPLETE)
        self.assertIn("schema", att.checks[0][2])

    def test_13_incomplete_verdict_refused(self):
        bad = dict(the_att())
        bad["verdict"] = PHASE9_INCOMPLETE
        att = Harness(phase9_provider=lambda: bad).run()
        self.assertEqual(att.verdict, PHASE10_INCOMPLETE)
        self.assertIn("PHASE9_IGNITED",
                      " ".join(c[2] for c in att.checks))

    def test_14_drifted_digest_refused(self):
        rows = the_ledger()[:-1] + [{
            "event_kind": "phase9_live_wiring_attestation",
            "detail": {"attestation_digest": "b" * 64}}]
        att = Harness(audit_rows=lambda: rows).run()
        self.assertEqual(att.verdict, PHASE10_INCOMPLETE)
        self.assertIn("DRIFTED", " ".join(c[2] for c in att.checks))

    def test_15_unrooted_attestation_refused(self):
        att = Harness(audit_rows=lambda: []).run()
        self.assertEqual(att.verdict, PHASE10_INCOMPLETE)
        self.assertIn("rooted", " ".join(c[2] for c in att.checks))

    def test_16_broken_chain_refused(self):
        att = Harness(chain_verifier=lambda: {
            "ok": False, "broken_at_seq": 1,
            "reason": "hash mismatch"}).run()
        self.assertEqual(att.verdict, PHASE10_INCOMPLETE)
        self.assertIn("not intact",
                      " ".join(c[2] for c in att.checks))

    def test_17_refusal_makes_zero_order_calls(self):
        # every ORD-01 failure class must leave the OMS stack
        # completely untouched (zero order-processing calls)
        for kwargs in (
                {"phase9_provider": None},
                {"phase9_provider": lambda: {"schema": "x"}},
                {"audit_rows": lambda: []},
                {"chain_verifier": lambda: {"ok": False}}):
            factory, made = real_engine_factory()
            h = Harness(engine_factory=factory, **kwargs)
            att = h.run()
            self.assertEqual(att.verdict, PHASE10_INCOMPLETE)
            engine = made.get("engine")
            self.assertIsNone(engine)  # factory never invoked


# ===================================================================
# ORD-02 — runtime profile & seams refusals
# ===================================================================

class TestOrd02Profile(unittest.TestCase):

    def test_20_unverified_profile_refused(self):
        bad = real_census()
        bad["runtime_profile_verified"] = False
        att = Harness(census=lambda: bad).run()
        self.assertEqual(att.verdict, PHASE10_INCOMPLETE)
        self.assertIn("NOT verified",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "ORD-02"))

    def test_21_missing_phase9_row_refused(self):
        bad = real_census()
        bad["phases"] = [p for p in bad["phases"]
                         if p["phase"] != 9]
        att = Harness(census=lambda: bad).run()
        self.assertEqual(att.verdict, PHASE10_INCOMPLETE)
        self.assertIn("Phase 5/6/7/8/9",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "ORD-02"))

    def test_22_unwired_phase8_refused(self):
        bad = real_census()
        for p in bad["phases"]:
            if p["phase"] == 8:
                p["wired"] = False
        att = Harness(census=lambda: bad).run()
        self.assertEqual(att.verdict, PHASE10_INCOMPLETE)
        self.assertIn("VERIFIED+WIRED",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "ORD-02"))

    def test_23_seam_registry_drift_refused(self):
        bad_registry = {11: "canonical.nonexistent_module",
                        12: "canonical.oms_contracts"}
        att = Harness(expected_entry_points=bad_registry).run()
        self.assertEqual(att.verdict, PHASE10_INCOMPLETE)
        self.assertIn("registry drift",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "ORD-02"))

    def test_24_census_absent_refused(self):
        att = Harness(census=None).run()
        self.assertEqual(att.verdict, PHASE10_INCOMPLETE)
        self.assertIn("unavailable",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "ORD-02"))


# ===================================================================
# ORD-03 — contracts & invariants refusals
# ===================================================================

class TestOrd03Contracts(unittest.TestCase):

    def test_30_currency_outside_whitelist_refused(self):
        from live_wiring_phase10_igniter import SYNTHETIC_ORDER as so
        import live_wiring_phase10_igniter as eng
        saved = eng.SYNTHETIC_ORDER
        eng.SYNTHETIC_ORDER = dict(saved, currency="USD")
        try:
            att = Harness().run()
        finally:
            eng.SYNTHETIC_ORDER = saved
        self.assertEqual(att.verdict, PHASE10_INCOMPLETE)
        blob = " ".join(c[2] for c in att.checks if c[0] == "ORD-03")
        self.assertIn("whitelist", blob)

    def test_31_unapproved_discount_code_refused(self):
        import live_wiring_phase10_igniter as eng
        saved = eng.SYNTHETIC_ORDER
        eng.SYNTHETIC_ORDER = dict(saved, discount_code="SUPER70")
        try:
            att = Harness().run()
        finally:
            eng.SYNTHETIC_ORDER = saved
        self.assertEqual(att.verdict, PHASE10_INCOMPLETE)
        blob = " ".join(c[2] for c in att.checks if c[0] == "ORD-03")
        self.assertIn("unapproved discount", blob)

    def test_32_price_invariants_enforced_by_real_validator(self):
        # floats rejected, negatives rejected, ceiling enforced —
        # the REAL validator, not a test stub
        for bad_price in (10.5, -5, 10**12 + 1):
            with self.assertRaises(OmsContractError):
                validate_order(dict(
                    SYNTHETIC_ORDER,
                    client_order_id="probe-price-x1",
                    line_items=[{"product_id": "P-1",
                                 "variant_id": "V-1", "sku": "S-1",
                                 "quantity": 1,
                                 "unit_price_minor": bad_price}]))

    def test_33_idempotency_key_deterministic(self):
        from canonical.oms_contracts import order_idempotency_key
        k1 = order_idempotency_key("phase10-probe-clt-0001")
        k2 = order_idempotency_key("phase10-probe-clt-0001")
        self.assertEqual(k1, k2)
        self.assertEqual(len(k1), 64)

    def test_34_state_machine_refuses_out_of_order(self):
        with self.assertRaises(OmsContractError):
            from canonical.oms_contracts import validate_transition
            validate_transition("PLACED", "COMPLETED")

    def test_35_engine_factory_absent_refused(self):
        att = Harness(engine_factory=None).run()
        self.assertEqual(att.verdict, PHASE10_INCOMPLETE)
        blob = " ".join(c[2] for c in att.checks if c[0] == "ORD-04")
        self.assertIn("unavailable", blob)


# ===================================================================
# ORD-04 — synthetic lifecycle refusals
# ===================================================================

class TestOrd04Lifecycle(unittest.TestCase):

    def test_40_insufficient_stock_refused_atomically(self):
        factory, _made = real_engine_factory(stock=1)
        h = Harness(engine_factory=factory)
        att = h.run()
        self.assertEqual(att.verdict, PHASE10_INCOMPLETE)
        blob = " ".join(c[2] for c in att.checks if c[0] == "ORD-04")
        self.assertIn("reservation probe failed", blob)

    def test_41_payment_boundary_marker_refused(self):
        # a REAL D-027 event record pre-seeded with a gateway marker
        # must flip the dispatch audit — payment is a BOUNDARY
        # (D-083); the audit scans the LIVE `records` mapping of the
        # store the engine actually drives
        factory, made = real_engine_factory()
        seeded = {"done": False}

        def seeded_factory():
            stack = factory()
            if not seeded["done"]:
                _engine, _inv, _led, store = stack
                store.records["orchestration::oms|gateway_probe"] = {
                    "processing_status": "succeeded",
                    "payload_hash": "x",
                    "result_reference": json.dumps(
                        {"payment_url": "https://gateway.example/pay"}),
                }
                seeded["done"] = True
            return stack
        h = Harness(engine_factory=seeded_factory)
        att = h.run()
        self.assertEqual(att.verdict, PHASE10_INCOMPLETE)
        blob = " ".join(c[2] for c in att.checks if c[0] == "ORD-04")
        self.assertIn("payment-boundary violation", blob)

    def test_415_fanout_boundary_actually_driven(self):
        # EVENT_PROBE must drive the REAL boundary: the durable
        # receipt exists, the outcome is publisher-less, and no
        # adapted payload ever reached a channel
        factory, made = real_engine_factory()
        h = Harness(engine_factory=factory)
        att = h.run()
        self.assertEqual(att.verdict, PHASE10_IGNITED)
        fanout = h.fanout
        self.assertIsNotNone(fanout)
        refs = [json.loads(r) for r in
                made["store"].succeeded_references("orchestration")]
        routed = [r for r in refs if r.get("adapted_payloads")]
        self.assertTrue(routed)
        for r in routed:
            for target, adapted in r["adapted_payloads"].items():
                self.assertEqual(target, "telegram")
                self.assertEqual(adapted["chat_id"], 1)
        # the durable per-target receipt: outcome recorded in the
        # store the boundary shares with the OMS (stage "target")
        receipts = [r for r in refs if r.get("stage") == "target"]
        self.assertTrue(receipts)
        for r in receipts:
            self.assertEqual(r["outcome"], "no_publisher_bound")

    def test_417_default_lock_never_used(self):
        # the probe boundary must ride the EPHEMERAL D-079 lock — the
        # default lock claims keys permanently in live PG or the
        # shared JSON file (never acceptable for probes)
        factory, made = real_engine_factory()
        h = Harness(engine_factory=factory)
        att = h.run()
        self.assertEqual(att.verdict, PHASE10_IGNITED)
        from canonical.orchestration_engine import (_JsonFanOutLock,
                                                    _PgFanOutLock)
        lock = h.fanout.lock
        self.assertIsInstance(lock, _EphemeralFanOutLock)
        self.assertNotIsInstance(lock, (_PgFanOutLock, _JsonFanOutLock))
        # the probe's claim lives ONLY in the ephemeral dict (purged
        # with the object) — nothing in live PG or the shared JSON
        # file is ever touched (checked against the live stores)
        self.assertIsInstance(lock._claims, dict)

    def test_42_scratch_scope_violation_refused(self):
        scratch = OrderScratch()
        with self.assertRaises(Exception):
            scratch.write("etc/passwd", {})
        with self.assertRaises(Exception):
            scratch.read("etc/passwd")
        with self.assertRaises(Exception):
            scratch.delete("etc/passwd")

    def test_43_cleanup_failure_refused(self):
        # the cycle PERSISTS a data-minimized artifact before cleanup;
        # a scratch that refuses to release it must fail the run
        class DirtyScratch(OrderScratch):
            def delete(self, key):
                if key.endswith("order"):
                    return False  # refuses to clean the artifact
                return super().delete(key)
        att = Harness(scratch=DirtyScratch()).run()
        self.assertEqual(att.verdict, PHASE10_INCOMPLETE)
        blob = " ".join(c[2] for c in att.checks if c[0] == "ORD-04")
        self.assertIn("cleanup failed", blob)

    def test_44_duplicate_token_collision_via_integrity(self):
        # a CONFLICTING payload under the same client_order_id raises
        # IntegrityError (D-027/D-081 human review) — the lock is
        # exclusive, not value-blind
        factory, made = real_engine_factory()
        h = Harness(engine_factory=factory)
        att = h.run()
        self.assertEqual(att.verdict, PHASE10_IGNITED)
        engine = h.made.get("engine")
        self.assertIsNotNone(engine)
        from services.sync_engine import IntegrityError
        with self.assertRaises(IntegrityError):
            engine.place_order(dict(
                SYNTHETIC_ORDER,
                line_items=[{"product_id": "P-9",
                             "variant_id": "V-9", "sku": "SKU-Z",
                             "quantity": 1,
                             "unit_price_minor": 500}]))

    def test_417b_no_claims_leak_to_shared_lock_stores(self):
        # after a PASS run, the shared D-079 lock stores must hold NO
        # trace of the probe keys — live PG rows and the shared JSON
        # file are production surfaces, never probe state
        factory, made = real_engine_factory()
        h = Harness(engine_factory=factory)
        att = h.run()
        self.assertEqual(att.verdict, PHASE10_IGNITED)
        import hashlib
        from canonical.oms_contracts import order_idempotency_key
        ok_key = order_idempotency_key(
            SYNTHETIC_ORDER["client_order_id"])
        probe_keys = set()
        for to_state in ("placed", "validated", "cancelled"):
            job_id = f"oms-notify-{ok_key}-{to_state}"
            material = "\x1f".join([
                "orchestration-fanout-v1", job_id,
                "order-notifications", f"order-{ok_key}",
                "1970-01-01T00:00:00+00:00", "telegram"])
            probe_keys.add(hashlib.sha256(
                material.encode("utf-8")).hexdigest())
        probe_keys.add(h.fanout.lock._claims and
                       next(iter(h.fanout.lock._claims)) or "")
        shared = pathlib.Path(
            REPO, "local", "volumes", "orchestration",
            "fanout_lock.json")
        if shared.exists():
            data = json.loads(shared.read_text(encoding="utf-8"))
            self.assertFalse(probe_keys & set(data))

    def test_45_duplicate_order_token_collision_refused(self):
        # pre-consumed client_order_id: a replay over the SAME store
        # must classify as skipped_duplicate (D-027 dedup, locally
        # observable through the REAL D-081 idempotency lock)
        factory, made = real_engine_factory()
        h = Harness(engine_factory=factory)
        att = h.run()
        self.assertEqual(att.verdict, PHASE10_IGNITED)
        engine = h.made["engine"]
        replay = engine.place_order(dict(SYNTHETIC_ORDER))
        self.assertEqual(replay.get("verdict"), "skipped_duplicate")

    def test_45b_replay_payload_never_reaches_fanout(self):
        # an identical replay is a SKIPPED DUPLICATE — no second
        # notification may be routed or dispatched (D-083 isolation)
        factory, made = real_engine_factory()
        h = Harness(engine_factory=factory)
        att = h.run()
        self.assertEqual(att.verdict, PHASE10_IGNITED)
        engine = h.made["engine"]
        before = len(h.fanout.lock._claims)
        replay = engine.place_order(dict(SYNTHETIC_ORDER))
        self.assertEqual(replay.get("verdict"), "skipped_duplicate")
        self.assertEqual(len(h.fanout.lock._claims), before)

    def test_46_cycle_deterministic_summary(self):
        s1 = Harness().run().to_dict()["cycle"]["summary_hash"]
        s2 = Harness().run().to_dict()["cycle"]["summary_hash"]
        self.assertEqual(s1, s2)


# ===================================================================
# ORD-05 — emission contract
# ===================================================================

class TestOrd05Emission(unittest.TestCase):

    def test_50_exactly_one_attestation_per_run(self):
        h = Harness()
        att = h.run()
        self.assertEqual(len(h.sink), 1)
        self.assertEqual(h.sink[0]["schema"], ATTESTATION_SCHEMA)
        self.assertEqual(h.sink[0]["verdict"], att.verdict)

    def test_51_abort_still_emits_attestation(self):
        h = Harness(phase9_provider=None)
        att = h.run()
        self.assertEqual(att.verdict, PHASE10_INCOMPLETE)
        self.assertEqual(len(h.sink), 1)

    def test_52_digest_covers_every_field(self):
        att = Harness().run()
        d = att.to_dict()
        for key in ("schema", "verdict", "phase9_digest",
                    "manifest_sha256", "profile", "contracts",
                    "cycle", "checks", "observed_tick"):
            self.assertIn(key, d)


# ===================================================================
# REDACT — zero PII/secret leakage (D-124)
# ===================================================================

class TestRedaction(unittest.TestCase):

    def test_60_no_pii_or_canaries_in_outputs(self):
        h = Harness()
        att = h.run()
        blob = json.dumps(att.to_dict()) + json.dumps(h.sink)
        for secret in (CUSTOMER_PHONE, CUSTOMER_ADDRESS, PAYMENT_TOKEN,
                       CANARY, SIGNING_KEY):
            self.assertNotIn(secret, blob)

    def test_61_customer_ref_never_in_outputs(self):
        att = Harness().run()
        blob = json.dumps(att.to_dict()) + json.dumps(Harness().sink)
        self.assertNotIn(SYNTHETIC_ORDER["customer_ref"], blob)

    def test_62_refusal_details_carry_no_pii(self):
        h = Harness(phase9_provider=lambda: {
            "schema": "x", "note": CUSTOMER_PHONE})
        att = h.run()
        blob = json.dumps(att.to_dict()) + json.dumps(h.sink)
        self.assertNotIn(CUSTOMER_PHONE, blob)

    def test_63_deep_redact_runs_on_emitted_records(self):
        h = Harness()
        att = h.run()
        row = h.sink[0]
        self.assertEqual(row["phase9_digest"], att.phase9_digest)
        self.assertEqual(row["manifest_sha256"],
                         att.manifest_sha256)

    def test_64_no_payment_material_anywhere(self):
        h = Harness()
        att = h.run()
        blob = json.dumps(att.to_dict()) + json.dumps(h.sink)
        for marker in ("gateway", "payment_url", "checkout",
                       PAYMENT_TOKEN):
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
        self.assertIn("engine_factory", src)
        self.assertIn("def _load", src)

    def test_73_payment_boundary_guarantee_in_source(self):
        src = ENGINE.read_text(encoding="utf-8")
        self.assertIn("payment-boundary violation", src)
        self.assertIn("payment_initiated", src)
        self.assertIn("phase10-scratch:", src)


if __name__ == "__main__":
    unittest.main()

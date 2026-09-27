"""Phase 15 live wiring igniter battery (D-165, offline).

Exercises `local/scripts/live_wiring_phase15_igniter.py` fully
offline — the event stream injected (the synthetic D-085-compliant
in-process stream), the cursor store the engine-side EPHEMERAL
in-memory backend (zero durable footprint), the census chained from
the REAL D-164 igniter over the REAL D-162/D-161/D-160/D-159/D-158/
D-157/D-156/D-155/D-154 chain:

  PASS    — phase14 attestation + verified profile + REAL contracts +
            ephemeral analytics cycle ⇒ PHASE15_IGNITED, deterministic
            digest;
  ANA-01  — missing/raised/wrong-schema/incomplete-verdict/drifted/
            unrooted/broken-chain phase14 attestation ⇒ refusal with
            ZERO engine calls (proven);
  ANA-02  — unverified profile, missing phase rows, seam registry
            drift, slot-16 cross-walk drift, census absent ⇒ refusal;
  ANA-03  — REAL validator rejections (mis-classified reason ⇒
            refusal), classifier purity, rollup determinism, D-088
            report identity;
  ANA-04  — absent stream, malformed payload handling, non-ephemeral
            cursor backend, cleanup failure ⇒ fail-closed refusal;
  ANA-05  — exactly one canonical attestation per run (including
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

from live_wiring_phase14_igniter import (  # noqa: E402
    PHASE14_IGNITED, PHASE14_INCOMPLETE,
)
from live_wiring_phase15_igniter import (  # noqa: E402
    ATTESTATION_SCHEMA, CYCLE_ID, PHASE14_ROW_KIND, PHASE14_SCHEMA,
    PHASE15_IGNITED, PHASE15_INCOMPLETE, SEAMS, SYNTHETIC_STREAM,
    _EphemeralCursorStore, Phase15Igniter, canonical_hash,
)

ENGINE = SCRIPTS / "live_wiring_phase15_igniter.py"

CANARY = "sk-canaryvalue1234567890abcdef"
WAREHOUSE_TOKEN = "wh-canary-warehouse-token-0123456789"


def synthetic_source(src: str, after: int):
    """The injected D-086 store adapter over the synthetic stream."""
    return [(ev["seq"], dict(ev["ref"]))
            for ev in SYNTHETIC_STREAM
            if ev["source"] == src and ev["seq"] > after]


# --- the authentic chain: phase14 attestation via the REAL D-164
# --- engine (which chains D-162 → … → D-154) -------------------------

def real_phase14_attestation(observed_tick=11000):
    """Run the REAL D-164 igniter over the authentic chain with
    in-process fakes (identical to the D-164 battery pass path)."""
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
    import tests.test_live_wiring_phase14 as t14  # noqa: E402
    h = t14.Harness(now=observed_tick)
    att = h.run()
    ledger = t14.the_ledger() + [{
        "event_kind": "phase14_scheduling_wiring_attestation",
        "detail": {"attestation_digest": att.attestation_digest,
                   "verdict": att.verdict}}]
    return att.to_dict(), ledger, t14


_CHAIN: dict = {}

_UNSET = object()  # sentinel: "no override given" (None = absent)


def the_att() -> dict:
    return _CHAIN["att"]


def the_ledger() -> list:
    return _CHAIN["ledger"]


def build_chain() -> None:
    if not _CHAIN:
        att, ledger, _t14 = real_phase14_attestation()
        _CHAIN.update(att=att, ledger=ledger)


def real_census() -> dict:
    """The runtime-profile census rows: Phases 5–12 + 14, all wired
    (slot 14 closed CRM-not-needed per D-163 — NOT a census row)."""
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
                            (14, "Scheduling Engine"))
        ],
    }


# --- the wired harness ---------------------------------------------------

class Harness:

    def __init__(self, now: int = 12000, events_source=synthetic_source,
                 census=real_census, **overrides):
        build_chain()
        self.now = now
        self.sink: list = []
        self.events_source = events_source
        providers = {
            "upstream_provider": the_att,
            "audit_rows": the_ledger,
            "chain_verifier": lambda: {"ok": True,
                                       "rows": len(the_ledger())},
            "census": census,
            "events_source": self.events_source,
            "cursor_store": _EphemeralCursorStore(),
        }
        providers.update(overrides)
        self.igniter = Phase15Igniter(
            clock=lambda: self.now, audit_sink=self.sink.append,
            **providers)

    def run(self):
        return self.igniter.run()


# ===================================================================
# PASS — successful ignition
# ===================================================================

class TestIgnitionPass(unittest.TestCase):

    def test_005_ephemeral_cursor_backend_wired(self):
        h = Harness()
        store = h.igniter._prov.get("cursor_store")
        self.assertIs(type(store), _EphemeralCursorStore)

    def test_01_full_ignition_completes(self):
        h = Harness()
        att = h.run()
        self.assertEqual(att.verdict, PHASE15_IGNITED)
        self.assertTrue(att.ignited)
        d = att.to_dict()
        self.assertEqual(d["schema"], ATTESTATION_SCHEMA)
        self.assertEqual(d["schema"],
                         "phase15.analytics_wiring_attestation.v1")
        self.assertEqual(d["phase14_digest"],
                         canonical_hash(the_att()))
        ids = [c[0] for c in att.checks]
        for rule in ("ANA-01", "ANA-02", "ANA-03", "ANA-04",
                     "ANA-05"):
            self.assertIn(rule, ids)
        self.assertTrue(all(c[1] for c in att.checks))
        self.assertTrue(d["profile"]["runtime_profile_verified"])
        self.assertTrue(d["profile"]["seams_ok"])
        self.assertTrue(d["contracts"]["contracts_ok"])
        self.assertTrue(d["contracts"]["report_hash_ok"])
        self.assertEqual(d["cycle"]["cursor_backend"], "ephemeral")
        self.assertFalse(d["cycle"]["drift"])

    def test_02_attestation_digest_deterministic(self):
        a1 = Harness(now=12500).run()
        b1 = Harness(now=12500).run()
        self.assertEqual(a1.attestation_digest, b1.attestation_digest)
        self.assertEqual(a1.attestation_digest,
                         canonical_hash(a1.to_dict()))

    def test_03_analytics_steps_recorded(self):
        att = Harness().run()
        steps = att.to_dict()["cycle"]["steps"]
        kinds = [s[0] for s in steps]
        for kind in ("START", "AUTH", "INGEST", "IDEMPOTENT", "FLAG",
                     "REBUILD", "REPORT", "VERIFY", "CLEANUP"):
            self.assertIn(kind, kinds)
        self.assertTrue(all(s[1] for s in steps))
        self.assertEqual(len(att.to_dict()["cycle"]["summary_hash"]),
                         64)

    def test_04_aggregates_and_time_series_buckets(self):
        att = Harness().run()
        steps = {s[0]: s[2] for s in att.to_dict()["cycle"]["steps"]}
        self.assertEqual(steps["INGEST"]["consumed"], 5)
        self.assertEqual(steps["INGEST"]["cursor"], 16)
        self.assertEqual(steps["INGEST"]["revenue_daily"], 450_000)
        self.assertIn("hourly", steps["INGEST"]["windows"])
        self.assertIn("monthly", steps["INGEST"]["windows"])
        self.assertEqual(steps["FLAG"]["cursor_held_at"], 16)
        self.assertFalse(att.to_dict()["cycle"]["drift"])


# ===================================================================
# ANA-01 — phase14 attestation refusals (zero engine calls)
# ===================================================================

class TestAna01Refusals(unittest.TestCase):

    def test_10_missing_phase14_attestation(self):
        h = Harness(upstream_provider=None)
        att = h.run()
        self.assertEqual(att.verdict, PHASE15_INCOMPLETE)
        self.assertIn("absent", att.checks[0][2])
        self.assertEqual(len(h.sink), 1)

    def test_11_provider_raises(self):
        def boom():
            raise RuntimeError("vault offline")
        att = Harness(upstream_provider=boom).run()
        self.assertEqual(att.verdict, PHASE15_INCOMPLETE)
        self.assertIn("RuntimeError", att.checks[0][2])

    def test_12_wrong_schema(self):
        att = Harness(upstream_provider=lambda: {
            "schema": "other.v1"}).run()
        self.assertEqual(att.verdict, PHASE15_INCOMPLETE)
        self.assertIn("schema", att.checks[0][2])

    def test_13_incomplete_verdict_refused(self):
        bad = dict(the_att())
        bad["verdict"] = PHASE14_INCOMPLETE
        att = Harness(upstream_provider=lambda: bad).run()
        self.assertEqual(att.verdict, PHASE15_INCOMPLETE)
        self.assertIn("PHASE14_IGNITED",
                      " ".join(c[2] for c in att.checks))

    def test_14_drifted_digest_refused(self):
        rows = the_ledger()[:-1] + [{
            "event_kind": "phase14_scheduling_wiring_attestation",
            "detail": {"attestation_digest": "b" * 64}}]
        att = Harness(audit_rows=lambda: rows).run()
        self.assertEqual(att.verdict, PHASE15_INCOMPLETE)
        self.assertIn("DRIFTED", " ".join(c[2] for c in att.checks))

    def test_15_unrooted_attestation_refused(self):
        att = Harness(audit_rows=lambda: []).run()
        self.assertEqual(att.verdict, PHASE15_INCOMPLETE)
        self.assertIn("rooted", " ".join(c[2] for c in att.checks))

    def test_16_broken_chain_refused(self):
        att = Harness(chain_verifier=lambda: {
            "ok": False, "broken_at_seq": 1,
            "reason": "hash mismatch"}).run()
        self.assertEqual(att.verdict, PHASE15_INCOMPLETE)
        self.assertIn("not intact",
                      " ".join(c[2] for c in att.checks))

    def test_17_refusal_makes_zero_engine_calls(self):
        # every ANA-01 failure class must leave the event stream
        # completely unread (zero source calls)
        calls = []

        def counting_source(src, after):
            calls.append((src, after))
            return synthetic_source(src, after)
        for kwargs in (
                {"upstream_provider": None},
                {"upstream_provider": lambda: {"schema": "x"}},
                {"audit_rows": lambda: []},
                {"chain_verifier": lambda: {"ok": False}}):
            calls.clear()
            h = Harness(events_source=counting_source, **kwargs)
            att = h.run()
            self.assertEqual(att.verdict, PHASE15_INCOMPLETE)
            self.assertEqual(calls, [])  # stream never touched


# ===================================================================
# ANA-02 — runtime profile & seams refusals
# ===================================================================

class TestAna02Profile(unittest.TestCase):

    def test_20_unverified_profile_refused(self):
        bad = real_census()
        bad["runtime_profile_verified"] = False
        att = Harness(census=lambda: bad).run()
        self.assertEqual(att.verdict, PHASE15_INCOMPLETE)
        self.assertIn("NOT verified",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "ANA-02"))

    def test_21_missing_phase14_row_refused(self):
        bad = real_census()
        bad["phases"] = [p for p in bad["phases"]
                         if p["phase"] != 14]
        att = Harness(census=lambda: bad).run()
        self.assertEqual(att.verdict, PHASE15_INCOMPLETE)
        self.assertIn("Phase 14 missing",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "ANA-02"))

    def test_22_unwired_phase12_refused(self):
        bad = real_census()
        for p in bad["phases"]:
            if p["phase"] == 12:
                p["wired"] = False
        att = Harness(census=lambda: bad).run()
        self.assertEqual(att.verdict, PHASE15_INCOMPLETE)
        self.assertIn("VERIFIED+WIRED",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "ANA-02"))

    def test_23_seam_registry_drift_refused(self):
        bad_registry = {13: "canonical.nonexistent_module",
                        15: "canonical.scheduling_engine",
                        16: "canonical.analytics_engine"}
        att = Harness(expected_entry_points=bad_registry).run()
        self.assertEqual(att.verdict, PHASE15_INCOMPLETE)
        self.assertIn("registry drift",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "ANA-02"))

    def test_24_census_absent_refused(self):
        att = Harness(census=None).run()
        self.assertEqual(att.verdict, PHASE15_INCOMPLETE)
        self.assertIn("unavailable",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "ANA-02"))

    def test_25_slot16_crosswalk_drift_refused(self):
        # the D-154 cross-walk binds slot 16 ("Analytics") to
        # `canonical.analytics_engine`; a registry that drops the
        # slot refuses (defense-in-depth beyond the per-seam loop)
        bad_registry = {13: "canonical.orchestration_engine",
                        15: "canonical.scheduling_engine"}
        att = Harness(expected_entry_points=bad_registry).run()
        self.assertEqual(att.verdict, PHASE15_INCOMPLETE)
        self.assertIn("cross-walk drift",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "ANA-02"))

    def test_26_slot14_not_required_in_census(self):
        # D-163: slot 14 (CRM) must NOT be a required census row —
        # a census carrying Phases 5-12+14 passes (real_census has
        # no phase-13/slot-14 row and the PASS path is green)
        att = Harness().run()
        self.assertEqual(att.verdict, PHASE15_IGNITED)
        self.assertNotIn(13, att.to_dict()["profile"]["phases"])


# ===================================================================
# ANA-03 — analytics contracts & invariants
# ===================================================================

class TestAna03Contracts(unittest.TestCase):

    def test_30_validator_enforced_in_probe(self):
        # the PASS run itself proves the REAL validator enforces the
        # window/classifier/rollup/hash invariants with named reasons
        att = Harness().run()
        self.assertEqual(att.verdict, PHASE15_IGNITED)
        blob = " ".join(c[2] for c in att.checks if c[0] == "ANA-03")
        self.assertIn("REAL contracts enforced", blob)

    def test_31_malformed_timestamps_refused(self):
        from canonical.analytics_contracts import (
            AnalyticsContractError, parse_occurred_at,
        )
        for bad in ("garbage", None, 12345,
                    "x" * 65):
            with self.assertRaises(AnalyticsContractError):
                parse_occurred_at(bad)
        parts = parse_occurred_at("2026-09-20T09:05:00+00:00")
        self.assertEqual(parts["day_key"], "2026-09-20")
        self.assertEqual(parts["hour_key"], "2026-09-20T09")
        self.assertEqual(parts["month_key"], "2026-09")

    def test_32_classifier_purity_direct(self):
        from canonical.analytics_contracts import (
            MK_ORDER_PLACED, MK_PUBLICATION_FAILED, classify_event,
        )
        self.assertIsNone(classify_event("notion", {
            "event_id": "notion|sync|x",
            "occurred_at": "2026-09-20T09:05:00+00:00"}))
        self.assertIsNone(classify_event("instagram", {
            "event_id": "instagram|transition|ig-9",
            "occurred_at": "2026-09-20T09:05:00+00:00",
            "outcome": "container_created"}))
        got = classify_event("telegram", {
            "event_id": "telegram|transition|tg-9",
            "occurred_at": "2026-09-20T09:05:00+00:00",
            "outcome": "terminal_reject"})
        self.assertEqual(got["kind"], MK_PUBLICATION_FAILED)
        placed = classify_event("oms", {
            "event_id": "oms|order|ord-9",
            "occurred_at": "2026-09-20T09:05:00+00:00"})
        self.assertEqual(placed["kind"], MK_ORDER_PLACED)
        self.assertIsNone(classify_event("oms", {
            "event_id": "oms|order|nested|x",
            "occurred_at": "2026-09-20T09:05:00+00:00"}))

    def test_33_report_identity_direct(self):
        from canonical.analytics_contracts import (
            WINDOW_DAILY, window_hash,
        )
        h1 = window_hash("daily-traffic", WINDOW_DAILY,
                         "2026-09-20", "2026-09-21", 15)
        h2 = window_hash("daily-traffic", WINDOW_DAILY,
                         "2026-09-20", "2026-09-21", 15)
        h3 = window_hash("daily-traffic", WINDOW_DAILY,
                         "2026-09-20", "2026-09-22", 15)
        self.assertEqual(h1, h2)
        self.assertNotEqual(h1, h3)
        self.assertEqual(len(h1), 64)

    def test_34_revenue_sums_counts_accumulate(self):
        from canonical.analytics_contracts import (
            MK_REVENUE_MINOR, WINDOW_DAILY, add_metric, finalize_rollup,
            new_rollup,
        )
        r = new_rollup()
        for total in (100_000, 50_000):
            add_metric(r, {"kind": MK_REVENUE_MINOR,
                           "occurred_at": "2026-09-20T09:05:00+00:00",
                           "value": total}, window=WINDOW_DAILY)
        fin = finalize_rollup(r)
        cell = fin[MK_REVENUE_MINOR]["2026-09-20"]
        self.assertEqual(cell["value"], 150_000)  # sums
        self.assertEqual(cell["count"], 2)        # counts

    def test_35_cancelled_orders_classify(self):
        from canonical.analytics_contracts import (
            MK_ORDER_CANCELLED, classify_event,
        )
        got = classify_event("oms", {
            "event_id": "oms|transition|ord-2",
            "occurred_at": "2026-09-21T11:00:00+00:00",
            "state": "CANCELLED"})
        self.assertEqual(got["kind"], MK_ORDER_CANCELLED)
        self.assertEqual(got["value"], 1)

    def test_36_completed_transition_yields_dual_metrics(self):
        from canonical.analytics_contracts import (
            MK_ORDER_COMPLETED, MK_REVENUE_MINOR, classify_event,
        )
        got = classify_event("oms", {
            "event_id": "oms|transition|ord-1",
            "occurred_at": "2026-09-21T10:00:00+00:00",
            "state": "COMPLETED", "order_total_minor": 450_000})
        self.assertIsInstance(got, list)
        self.assertEqual(got[0]["kind"], MK_ORDER_COMPLETED)
        self.assertEqual(got[1]["kind"], MK_REVENUE_MINOR)
        self.assertEqual(got[1]["value"], 450_000)


# ===================================================================
# ANA-04 — analytics cycle refusals
# ===================================================================

class TestAna04Cycle(unittest.TestCase):

    def test_40_stream_absent_refused(self):
        att = Harness(events_source=None).run()
        self.assertEqual(att.verdict, PHASE15_INCOMPLETE)
        blob = " ".join(c[2] for c in att.checks if c[0] == "ANA-04")
        self.assertIn("unavailable", blob)

    def test_41_malformed_payload_quarantined_cursor_held(self):
        att = Harness().run()
        self.assertEqual(att.verdict, PHASE15_IGNITED)
        steps = {s[0]: s[2] for s in att.to_dict()["cycle"]["steps"]}
        self.assertEqual(steps["FLAG"]["quarantined"], 1)
        self.assertEqual(steps["FLAG"]["cursor_held_at"], 16)
        self.assertEqual(steps["FLAG"]["payload"], "hashed-only")

    def test_42_rebuild_determinism_proven_in_pass(self):
        att = Harness().run()
        steps = {s[0]: s[2] for s in att.to_dict()["cycle"]["steps"]}
        self.assertEqual(steps["REBUILD"]["replay"],
                         "incremental == full replay")
        self.assertEqual(steps["IDEMPOTENT"]["reconsume"],
                         "no-op (cursor at 16)")

    def test_43_cleanup_failure_refused(self):
        class StickyIgniter(Phase15Igniter):
            def _scratch_delete(self):
                return False  # refuses to clean the artifact
        h = Harness()
        h.igniter.__class__ = StickyIgniter
        att = h.run()
        self.assertEqual(att.verdict, PHASE15_INCOMPLETE)
        blob = " ".join(c[2] for c in att.checks if c[0] == "ANA-04")
        self.assertIn("cleanup failed", blob)

    def test_44_non_ephemeral_cursor_backend_refused(self):
        # a FULLY FUNCTIONAL but FOREIGN (non-ephemeral) store passes
        # every data check, then VERIFY must still refuse the durable
        # footprint by class
        class ForeignStore:
            def __init__(self):
                self._data = {"last_seq": 0, "rollups": {}}
            def get_cursor(self):
                return int(self._data.get("last_seq", 0))
            def advance(self, last_seq, rollups):
                self._data["last_seq"] = int(last_seq)
                self._data["rollups"] = rollups
            def reset(self):
                self._data = {"last_seq": 0, "rollups": {}}
            def rollups(self):
                return self._data.get("rollups", {})
        h = Harness()
        ign = h.igniter
        ign._prov["cursor_store"] = ForeignStore()
        att = h.run()
        self.assertEqual(att.verdict, PHASE15_INCOMPLETE)
        blob = " ".join(c[2] for c in att.checks if c[0] == "ANA-04")
        self.assertIn("ephemeral", blob)


# ===================================================================
# ANA-05 — emission contract
# ===================================================================

class TestAna05Emission(unittest.TestCase):

    def test_50_exactly_one_attestation_per_run(self):
        h = Harness()
        att = h.run()
        self.assertEqual(len(h.sink), 1)
        self.assertEqual(h.sink[0]["schema"], ATTESTATION_SCHEMA)
        self.assertEqual(h.sink[0]["verdict"], att.verdict)

    def test_51_abort_still_emits_attestation(self):
        h = Harness(upstream_provider=None)
        att = h.run()
        self.assertEqual(att.verdict, PHASE15_INCOMPLETE)
        self.assertEqual(len(h.sink), 1)

    def test_52_digest_covers_every_field(self):
        att = Harness().run()
        d = att.to_dict()
        for key in ("schema", "verdict", "phase14_digest",
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
        for secret in (CANARY, WAREHOUSE_TOKEN):
            self.assertNotIn(secret, blob)

    def test_61_refusal_details_carry_no_secrets(self):
        h = Harness(upstream_provider=lambda: {
            "schema": "x", "note": WAREHOUSE_TOKEN})
        att = h.run()
        blob = json.dumps(att.to_dict()) + json.dumps(h.sink)
        self.assertNotIn(WAREHOUSE_TOKEN, blob)

    def test_62_deep_redact_runs_on_emitted_records(self):
        h = Harness()
        att = h.run()
        row = h.sink[0]
        self.assertEqual(row["phase14_digest"], att.phase14_digest)
        self.assertEqual(row["manifest_sha256"],
                         att.manifest_sha256)

    def test_63_no_egress_markers_in_outputs(self):
        h = Harness()
        att = h.run()
        blob = json.dumps(att.to_dict()) + json.dumps(h.sink)
        for marker in ('"egress": true', "warehouse_token",
                       "webhook_secret", "auth_code", "pan",
                       "card_number"):
            self.assertNotIn(marker, blob)

    def test_64_malformed_quarantine_carries_hash_only(self):
        h = Harness()
        att = h.run()
        blob = json.dumps(att.to_dict()) + json.dumps(h.sink)
        self.assertIn("hashed-only", blob)
        self.assertNotIn("garbage", blob)  # payload never escapes


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
        self.assertIn("events_source", src)
        self.assertIn("cursor_store", src)
        self.assertIn("def _load", src)

    def test_73_ephemeral_boundary_guarantee_in_source(self):
        src = ENGINE.read_text(encoding="utf-8")
        self.assertIn("egress-boundary violation", src)
        self.assertIn("phase15-scratch:", src)
        self.assertIn("_EphemeralCursorStore", src)
        self.assertIn("D-163", src)


if __name__ == "__main__":
    unittest.main()

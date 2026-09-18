"""Phase 20 — security hardening & threat model tests (D-113..D-116).

Layers:
  M4a contract boundary battery: the six hardened prior-phase
      validators (oms/analytics/scheduling/analyst/hitl/admin) reject
      oversized payloads, control characters and unbounded text
      deterministically (D-114 defense in depth — Class-B BEFORE any
      durable write).
  M4b InputHardeningGate: size caps, control/confusable rejection,
      NFC canonicalization, JSON depth/width caps, duplicate-key
      rejection, uniform error surfaces without internals disclosure.
  M4c chain attestation v2: position-weighted FULL-ROW fold over the
      Phase 18 (HITL ledger) and Phase 19 (control audit) chains —
      interior mutation, swap, truncation and append each detected.
  M4d deterministic rate limiter & lockout: logical-clock budgets,
      window reset, lockout arming/expiry, replay-key forge
      resistance (burns chain-anchored), audited lockouts.
  M4e automated sweeps: extended AST (D-116) + secret entropy
      (D-045) + bounds re-audit run 100% clean on the repository.
  M4f LIVE PostgreSQL E2E: real hardening-audit vault, attestation
      tamper detection over live tables (with byte-exact restore),
      8-thread lockout race, 8-thread audit-record dedup race.

Zero network; local-token actors only (D-045); the wall clock never
enters any decision (logical clock values only).
"""

import json
import os
import sys
import tempfile
import threading
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL = os.path.dirname(HERE)
ROOT = os.path.dirname(LOCAL)
for p in (LOCAL, os.path.join(LOCAL, "canonical"),
          os.path.join(LOCAL, "services"),
          os.path.join(LOCAL, "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

from canonical.security_contracts import (  # noqa: E402
    HardeningPolicy,
    MAX_JSON_DEPTH,
    MAX_JSON_WIDTH,
    MAX_LIST_ITEMS,
    MAX_PAYLOAD_BYTES,
    MAX_STRING_LEN,
    RECORD_KINDS,
    SECURITY_CONTROLS,
    SecurityContractError,
    THREAT_CATEGORIES,
    validate_policy,
    validate_record,
    validate_registry,
)
from canonical.security_engine import (  # noqa: E402
    ChainHeadAttestation,
    HardeningEngine,
    InputHardeningGate,
    InputRejected,
    RateLimiter,
    _JsonAuditVault,
    canonicalize_text,
)
from canonical.security_worker import (  # noqa: E402
    ast_sweep,
    bounds_re_audit,
    entropy_scan,
    full_security_sweep,
)

from canonical.oms_contracts import (  # noqa: E402
    MAX_CUSTOMER_REF_LEN,
    MAX_LINE_ITEMS_PER_ORDER,
    OmsContractError,
    validate_order,
)
from canonical.analytics_contracts import (  # noqa: E402
    AnalyticsContractError,
    MAX_OCCURRED_AT_LEN,
    parse_occurred_at,
)
from canonical.scheduling_contracts import (  # noqa: E402
    MAX_TARGETS_PER_POST,
    SchedulingContractError,
    validate_scheduled_post,
)
from canonical.analyst_contracts import (  # noqa: E402
    AnalystContractError,
    MAX_ACTIONABLE_PAYLOAD_JSON,
    MAX_CORRELATION_KEYS,
    MAX_INSIGHT_ID_LEN,
    MAX_METRIC_REFS,
    CAT_SALES,
    SEV_LOW,
    ST_GENERATED,
    validate_insight,
)
from canonical.hitl_contracts import (  # noqa: E402
    HitlContractError,
    MAX_FEEDBACK_NOTES_LEN,
    MAX_PAYLOAD_REF_LEN,
    MAX_TICKET_ID_LEN,
    QT_INSIGHT_REVIEW,
    ROLE_ANY,
    ST_PENDING_REVIEW,
    validate_ticket,
)
from canonical.admin_contracts import (  # noqa: E402
    CMD_PAUSE_QUEUE,
    CMD_REPLAY_EVENTS,
    AdminContractError,
    MAX_ACTION_ID_LEN,
    MAX_REASON_LEN,
    MAX_TARGET_LEN,
    make_confirmation_key,
    validate_action,
)
from canonical.admin_engine import ControlPlaneEngine, _JsonVault  # noqa: E402,E501
from services.sync_engine import EventStore  # noqa: E402

RUN_ID = os.getpid()


class _Harness:
    """Offline parity stack (Phase 19 pattern)."""

    def __init__(self):
        fd, self.store_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.remove(self.store_path)
        self.vault_path = self.store_path + ".a"
        self.store = EventStore(self.store_path)

    def cleanup(self):
        import glob
        import shutil
        for p in glob.glob(self.store_path + "*"):
            if os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)
            elif os.path.exists(p):
                os.remove(p)


# --- fixtures for the six hardened surfaces ----------------------------------


def _order(**over):
    o = {
        "order_id": "ord-1",
        "client_order_id": "client-order-0001",
        "customer_ref": "customer-local-1",
        "line_items": [{"product_id": "prd-1", "variant_id": "var-1",
                        "sku": "sku-1", "quantity": 1,
                        "unit_price_minor": 1000}],
        "placed_at": "2026-09-17T00:00:00+00:00",
        "payment_status": "pending",
    }
    o.update(over)
    return o


def _post(**over):
    p = {"post_id": "post-1", "content_ref": "content-1",
         "targets": ["instagram", "telegram"],
         "scheduled_for": "2026-09-17T09:00:00+00:00",
         "status": "SCHEDULED"}
    p.update(over)
    return p


def _insight(**over):
    i = {"insight_id": "ins-1", "category": CAT_SALES,
         "severity": SEV_LOW,
         "metric_refs": [{"metric_kind": "publication_failure_rate",
                          "window_ref": "w-1"}],
         "correlation_keys": ["domain:publication"],
         "actionable_payload": {"note": "review failure spike"},
         "confidence_score": 0.5,
         "status": ST_GENERATED}
    i.update(over)
    return i


def _ticket(**over):
    t = {"ticket_id": "tkt-1", "queue_type": QT_INSIGHT_REVIEW,
         "payload_ref": "insight:ins-1", "required_role": ROLE_ANY,
         "resolution_status": ST_PENDING_REVIEW,
         "created_at_logical": "L0001"}
    t.update(over)
    return t


def _action(aid="a-1", cmd=CMD_PAUSE_QUEUE,
            actor="actor:operator:rev-1",
            target="queue:notifications", **kw):
    a = {"action_id": aid, "command": cmd, "target": target,
         "actor": actor, "reason": "operator procedure",
         "created_at_logical": "L0001"}
    a.update(kw)
    return a


# --- M4a: the six hardened contract surfaces ---------------------------------


class TestM4ContractBoundary(unittest.TestCase):
    """D-114: every prior-phase validator refuses oversized /
    malformed input deterministically — defense in depth."""

    def test_oms_bounds(self):
        with self.assertRaises(OmsContractError):
            validate_order(_order(
                customer_ref="c" * (MAX_CUSTOMER_REF_LEN + 1)))
        with self.assertRaises(OmsContractError):
            validate_order(_order(line_items=[
                {"product_id": "prd-1", "variant_id": "var-1",
                 "sku": "sku-1", "quantity": 1,
                 "unit_price_minor": 1000}]
                * (MAX_LINE_ITEMS_PER_ORDER + 1)))
        # a legal order still passes (no over-blocking)
        validate_order(_order())

    def test_analytics_bounds(self):
        with self.assertRaises(AnalyticsContractError):
            parse_occurred_at("2" * (MAX_OCCURRED_AT_LEN + 1))
        parse_occurred_at("2026-09-17T00:00:00+00:00")

    def test_scheduling_bounds(self):
        with self.assertRaises(SchedulingContractError):
            validate_scheduled_post(_post(
                targets=[f"platform-{i}"
                         for i in range(MAX_TARGETS_PER_POST + 1)]))
        with self.assertRaises(SchedulingContractError):
            validate_scheduled_post(_post(targets=["ig", "ig"]))
        validate_scheduled_post(_post())

    def test_analyst_bounds(self):
        with self.assertRaises(AnalystContractError):
            validate_insight(_insight(
                insight_id="i" * (MAX_INSIGHT_ID_LEN + 1)))
        with self.assertRaises(AnalystContractError):
            validate_insight(_insight(metric_refs=[
                {"metric_kind": "m", "window_ref": "w"}]
                * (MAX_METRIC_REFS + 1)))
        with self.assertRaises(AnalystContractError):
            validate_insight(_insight(correlation_keys=[
                f"k{i}" for i in range(MAX_CORRELATION_KEYS + 1)]))
        big_payload = {"blob": "x" * (MAX_ACTIONABLE_PAYLOAD_JSON + 1)}
        with self.assertRaises(AnalystContractError):
            validate_insight(_insight(actionable_payload=big_payload))
        validate_insight(_insight())

    def test_hitl_bounds(self):
        with self.assertRaises(HitlContractError):
            validate_ticket(_ticket(
                ticket_id="t" * (MAX_TICKET_ID_LEN + 1)))
        with self.assertRaises(HitlContractError):
            validate_ticket(_ticket(
                payload_ref="p" * (MAX_PAYLOAD_REF_LEN + 1)))
        # an implicit slice cap is now a declared, enforced bound
        self.assertEqual(MAX_FEEDBACK_NOTES_LEN, 2000)
        validate_ticket(_ticket())

    def test_admin_bounds(self):
        with self.assertRaises(AdminContractError):
            validate_action(_action(
                aid="a" * (MAX_ACTION_ID_LEN + 1)))
        with self.assertRaises(AdminContractError):
            validate_action(_action(target="t" * (MAX_TARGET_LEN + 1)))
        with self.assertRaises(AdminContractError):
            validate_action(_action(
                cmd=CMD_REPLAY_EVENTS, actor="actor:admin:1",
                reason="r" * (MAX_REASON_LEN + 1)))
        validate_action(_action())

    def test_control_registry_battery_backed(self):
        # D-113: no control without a test artifact; every threat
        # category covered; records/policies strictly validated.
        by_threat = validate_registry()
        self.assertEqual(sorted(by_threat), sorted(THREAT_CATEGORIES))
        for c in SECURITY_CONTROLS:
            with self.subTest(control=c["control_id"]):
                self.assertTrue(
                    "test_phase20_security" in c["test_artifact"]
                    or c["test_artifact"].startswith("per-phase"),
                    c["test_artifact"])
        self.assertEqual(
            sorted(RECORD_KINDS),
            sorted(["gate_rejection", "attestation_check",
                    "rate_limit_hit", "actor_lockout", "key_burn",
                    # D-125: compaction manifests join the audited kinds
                    "compaction_manifest"]))
        with self.assertRaises(SecurityContractError):
            validate_record({"record_kind": "nope", "subject": "s",
                             "actor": "a", "logical_at": "L1"})
        with self.assertRaises(SecurityContractError):
            validate_policy({"max_string_len": 0})
        with self.assertRaises(SecurityContractError):
            validate_policy({"max_string_len": True})
        self.assertEqual(
            validate_policy({"max_list_items": 10}),
            {"max_list_items": 10})


# --- M4b: the input hardening gate --------------------------------------------


class TestM4Gate(unittest.TestCase):
    def setUp(self):
        self.gate = InputHardeningGate()

    def test_string_limits(self):
        with self.assertRaises(InputRejected):
            self.gate.check_string("x" * (MAX_STRING_LEN + 1))
        ok = self.gate.check_string("plain safe text")
        self.assertIsInstance(ok, str)

    def test_control_chars_rejected_at_the_gate(self):
        # layered defense (D-114): module validators guarantee BOUNDS;
        # the GATE is the system-wide entry point that refuses control
        # characters, confusables and charset violations — oms' own
        # validator stays bound-only by design (tested above).
        for bad, reason in (("bad\x01ref", "control_character"),
                            ("bad\x0bref", "control_character"),
                            ("p\u0430ypal", "confusable_unicode"),
                            ("hidden\u200bzwsp",
                             "invisible_or_unassigned_char")):
            with self.subTest(bad=bad[:6]):
                with self.assertRaises(InputRejected) as ctx:
                    self.gate.check_string(bad)
                self.assertEqual(ctx.exception.reason, reason)

    def test_oms_customer_ref_charset(self):
        # an oms customer_ref containing a control char is refused at
        # the system entry point (gate), not silently accepted
        with self.assertRaises(InputRejected) as ctx:
            self.gate.check_string("bad\x01ref")
        self.assertEqual(ctx.exception.reason, "control_character")

    def test_identifier_strict_charset(self):
        self.assertEqual(self.gate.check_identifier("ok:Id_1"),
                         "ok:Id_1")
        # identifier charset is stricter: no spaces or punctuation
        # outside the allowed set; confusables refused too
        with self.assertRaises(InputRejected):
            self.gate.check_identifier("bad$char")
        with self.assertRaises(InputRejected):
            self.gate.check_identifier("p\u0430ypal-clone")
        with self.assertRaises(InputRejected):
            self.gate.check_identifier("")

    def test_payload_size_caps(self):
        with self.assertRaises(InputRejected):
            self.gate.check_payload(b"x" * (MAX_PAYLOAD_BYTES + 1))
        with self.assertRaises(InputRejected):
            self.gate.check_payload(b"")
        self.assertEqual(self.gate.check_payload("abc"), b"abc")

    def test_json_depth_width_and_duplicates(self):
        deep = doc = {}
        for _ in range(MAX_JSON_DEPTH + 2):
            doc["n"] = {}
            doc = doc["n"]
        with self.assertRaises(InputRejected) as ctx:
            self.gate.parse_json(json.dumps(deep))
        self.assertEqual(ctx.exception.reason, "json_depth_exceeded")
        wide = {f"k{i}": 1 for i in range(MAX_JSON_WIDTH + 1)}
        with self.assertRaises(InputRejected):
            self.gate.parse_json(json.dumps(wide))
        with self.assertRaises(InputRejected) as ctx:
            self.gate.parse_json('{"a": 1, "a": 2}')
        self.assertEqual(ctx.exception.reason, "duplicate_json_key")
        with self.assertRaises(InputRejected):
            self.gate.parse_json("{not json")
        doc = self.gate.parse_json('{"a": {"b": [1, 2, 3]}}')
        self.assertEqual(doc["a"]["b"], [1, 2, 3])

    def test_policy_overrides(self):
        tight = InputHardeningGate(
            HardeningPolicy(max_string_len=8, max_json_depth=2,
                            max_json_width=4, max_list_items=2))
        with self.assertRaises(InputRejected):
            tight.check_string("123456789")
        with self.assertRaises(InputRejected) as ctx:
            tight.parse_json(json.dumps({"a": {"b": {"c": 1}}}))
        self.assertEqual(ctx.exception.reason, "json_depth_exceeded")
        # width cap: more keys per level than the policy allows
        with self.assertRaises(InputRejected):
            tight.parse_json(json.dumps({f"k{i}": 1
                                         for i in range(5)}))

    def test_canonicalization_is_nfc(self):
        # real codepoints: 'e' + combining acute vs precomposed 'é'
        self.assertEqual(canonicalize_text("cafe\u0301"),
                         canonicalize_text("caf\u00e9"))

    def test_error_surface_discipline(self):
        # D-113 enumeration control: rejections carry a STABLE reason
        # code only — never the offending input internals.
        for bad in ("x" * 600, "p\u0430ypal", "a\x02b"):
            with self.subTest(bad=bad[:3]):
                try:
                    self.gate.check_string(bad)
                except InputRejected as exc:
                    self.assertLess(len(str(exc)), 48)
                    self.assertNotIn(bad[:8], str(exc))


# --- M4c: chain attestation v2 --------------------------------------------------


class TestM4Attestation(unittest.TestCase):
    def _rows(self):
        return [{"audit_seq": i, "action_id": f"a-{i}",
                 "event_kind": "action_received", "actor": "actor:a:1",
                 "detail": {"n": i}, "row_hash": f"hash-{i}"}
                for i in range(1, 6)]

    def test_attestation_detects_interior_mutation(self):
        rows = self._rows()
        att = ChainHeadAttestation(lambda: rows).compute("L0100")
        self.assertTrue(ChainHeadAttestation(
            lambda: rows).verify(att, "L0101")["ok"])
        tampered = [dict(r) for r in rows]
        tampered[2]["detail"] = {"n": 999}   # interior payload edit
        verdict = ChainHeadAttestation(
            lambda: tampered).verify(att, "L0101")
        self.assertFalse(verdict["ok"])
        self.assertEqual(verdict["reason"], "attestation_mismatch")

    def test_attestation_detects_swap_truncate_append(self):
        rows = self._rows()
        att = ChainHeadAttestation(lambda: rows).compute("L0100")
        swap = [rows[1], rows[0]] + rows[2:]
        self.assertFalse(ChainHeadAttestation(
            lambda: swap).verify(att, "L0101")["ok"])
        verdict = ChainHeadAttestation(
            lambda: rows[:4]).verify(att, "L0101")
        self.assertFalse(verdict["ok"])
        self.assertEqual(verdict["reason"], "length_mismatch")
        appended = rows + [dict(rows[-1], audit_seq=6)]
        self.assertFalse(ChainHeadAttestation(
            lambda: appended).verify(att, "L0101")["ok"])

    def test_attestation_is_position_weighted(self):
        # same rows in the same order verify; ANY reordering fails —
        # the fold is order-sensitive by construction (not a set sum)
        rows = self._rows()
        att = ChainHeadAttestation(lambda: rows).compute("L0001")
        self.assertTrue(ChainHeadAttestation(
            lambda: list(rows)).verify(att, "L0002")["ok"])
        self.assertFalse(ChainHeadAttestation(
            lambda: rows[::-1]).verify(att, "L0002")["ok"])

    def test_hardening_audit_records_durable_and_idempotent(self):
        h = _Harness()
        try:
            eng = HardeningEngine(
                h.store, vault=_JsonAuditVault(h.vault_path))
            rec = {"record_kind": "gate_rejection", "subject": "s-1",
                   "actor": "actor:system:security",
                   "logical_at": "L0001",
                   "detail": {"reason": "string_too_long"}}
            r1 = eng.audit(rec)
            r2 = eng.audit(dict(rec))   # same occurrence re-reported
            self.assertEqual(r1["record_key"], r2["record_key"])
            self.assertTrue(r1["inserted"])
            self.assertFalse(r2["inserted"])
            self.assertEqual(len(eng.records()), 1)
            # a DIFFERENT occurrence gets its own key
            r3 = eng.audit(dict(rec, subject="s-2"))
            self.assertNotEqual(r1["record_key"], r3["record_key"])
            # attestation round-trip persists as audit records
            rows = self._rows()
            att = eng.attest(lambda: rows, "L0002", subject="admin")
            verdict = eng.verify(lambda: rows, att, "L0003")
            self.assertTrue(verdict["ok"])
            kinds = {r["record_kind"] for r in eng.records()}
            self.assertIn("attestation_check", kinds)
        finally:
            h.cleanup()


# --- M4d: deterministic rate limiter, lockout, replay forgery -------------------


class TestM4RateLimit(unittest.TestCase):
    def test_window_budget_and_lockout(self):
        rl = RateLimiter(threshold=3, window_logical=100)
        for i in (1, 2, 3):
            res = rl.record("op-1", "failed_rbac", f"L{i:04d}")
        self.assertTrue(res["locked_out"])
        self.assertEqual(res["lock_until_logical"], "L103")
        # while locked: refused
        self.assertFalse(rl.check("op-1", "failed_rbac",
                                  "L0050")["allowed"])
        # after the lockout horizon: allowed again
        self.assertTrue(rl.check("op-1", "failed_rbac",
                                 "L1050")["allowed"])
        # window reset: old events age out of the budget
        rl2 = RateLimiter(threshold=3, window_logical=100)
        rl2.record("op-2", "retry_dlq", "L0001")
        rl2.record("op-2", "retry_dlq", "L0002")
        self.assertTrue(rl2.check("op-2", "retry_dlq",
                                  "L0103")["allowed"])
        # zero wall-clock in the limiter's decisions: only logical
        # stamps were handed in (string args throughout)

    def test_subject_isolation(self):
        rl = RateLimiter(threshold=2, window_logical=1000)
        rl.record("op-a", "failed_rbac", "L0001")
        rl.record("op-a", "failed_rbac", "L0002")
        self.assertTrue(rl.lockout_state("op-a", "failed_rbac")
                        is not None)
        self.assertTrue(rl.record("op-b", "failed_rbac",
                                  "L0003")["allowed"])

    def test_replay_key_forge_resistance(self):
        # D-115: a burned replay key cannot be re-used under a new
        # action id — the burn lives in the tamper-evident chain.
        h = _Harness()
        try:
            eng = ControlPlaneEngine(h.store, vault=_JsonVault(
                h.vault_path))
            mutated = []
            eng.register_handler(
                CMD_REPLAY_EVENTS,
                lambda a: mutated.append(a["action_id"])
                if a.get("mode") == "APPLY" else {"dry": True})
            key = make_confirmation_key()
            ok = eng.execute(_action(
                f"fg-{RUN_ID}", cmd=CMD_REPLAY_EVENTS,
                actor="actor:admin:1", target="events",
                reason="audited", confirmation_key=key))
            self.assertTrue(ok["ok"])
            self.assertEqual(mutated, [f"fg-{RUN_ID}"])
            reuse = eng.execute(_action(
                f"fg-{RUN_ID}-b", cmd=CMD_REPLAY_EVENTS,
                actor="actor:admin:1", target="events", reason="again",
                confirmation_key=key))
            self.assertFalse(reuse["ok"])
            self.assertEqual(reuse["reason"], "key_already_burned")
            self.assertEqual(mutated, [f"fg-{RUN_ID}"])
            # the burn is CHAIN-ANCHORED (an audited row)
            burns = [r for r in eng.audit()
                     if r["event_kind"] == "replay_key_burned"]
            self.assertEqual(len(burns), 1)
            self.assertTrue(eng.verify_chain()["ok"])
        finally:
            h.cleanup()

    def test_lockout_is_audited(self):
        h = _Harness()
        try:
            eng = HardeningEngine(
                h.store, vault=_JsonAuditVault(h.vault_path))
            rl = RateLimiter(threshold=2, window_logical=100)
            rl.record("op-x", "failed_rbac", "L0001")
            trip = rl.record("op-x", "failed_rbac", "L0002")
            self.assertTrue(trip["locked_out"])
            eng.audit({"record_kind": "actor_lockout",
                       "subject": "op-x",
                       "actor": "actor:system:security",
                       "logical_at": "L0002",
                       "detail": {"kind": "failed_rbac",
                                  "lock_until_logical":
                                      trip["lock_until_logical"]}})
            self.assertEqual(
                [r["record_kind"] for r in eng.records()],
                ["actor_lockout"])
        finally:
            h.cleanup()


# --- M4e: automated sweeps must run clean ---------------------------------------


class TestM4Sweep(unittest.TestCase):
    def test_extended_ast_sweep_clean(self):
        rep = ast_sweep([os.path.join(ROOT, "local", "canonical")])
        self.assertEqual(rep["findings"], [],
                         f"AST findings: {rep['findings'][:5]}")
        self.assertTrue(rep["clean"])

    def test_entropy_scan_clean(self):
        rep = entropy_scan([os.path.join(ROOT, "local", "canonical"),
                            os.path.join(ROOT, "local", "tests")])
        self.assertEqual(rep["flagged"], [],
                         f"entropy flags: {rep['flagged'][:5]}")
        self.assertTrue(rep["clean"])

    def test_bounds_re_audit_clean(self):
        rep = bounds_re_audit(os.path.join(ROOT, "local", "canonical"))
        self.assertEqual(rep["missing_bounds"], [])
        self.assertEqual(len(rep["modules_audited"]), 11)

    def test_full_security_sweep_clean(self):
        rep = full_security_sweep(ROOT)
        self.assertTrue(rep["clean"],
                        json.dumps({k: rep[k] for k in
                                    ("ast", "entropy", "bounds")},
                                   default=str)[:400])


# --- M4f: live PostgreSQL E2E -----------------------------------------------------


def _stack_up():
    try:
        import subprocess
        out = subprocess.run(
            ["docker", "compose", "-f", "local/infra/docker-compose.yml",
             "ps", "--format", "json"], capture_output=True, text=True,
            timeout=20, cwd=str(ROOT))
        return out.returncode == 0 and \
            "engine-local-postgres" in out.stdout and \
            "healthy" in out.stdout
    except Exception:
        return False


@unittest.skipUnless(_stack_up(), "live PostgreSQL stack not running")
class TestM4LivePgE2E(unittest.TestCase):
    def setUp(self):
        from canonical.notion_ingest import PgEventStore
        if not hasattr(self, "store"):
            self.store = PgEventStore()
        self.engine = HardeningEngine(self.store,
                                      vault=self._vault())

    def _vault(self):
        from canonical.security_engine import _PgAuditVault
        return _PgAuditVault()

    def _psql(self):
        from canonical.notion_ingest import _exec, _txt
        return _exec, _txt

    def test_live_hardening_audit_durable(self):
        rec = {"record_kind": "gate_rejection",
               "subject": f"live-s-{RUN_ID}",
               "actor": "actor:system:security",
               "logical_at": "L0001",
               "detail": {"reason": "payload_too_large"}}
        r1 = self.engine.audit(rec)
        r2 = self.engine.audit(dict(rec))
        self.assertTrue(r1["inserted"])
        self.assertFalse(r2["inserted"])
        self.assertEqual(r1["record_key"], r2["record_key"])
        keys = [r["record_key"] for r in self._vault().rows()]
        self.assertEqual(keys.count(r1["record_key"]), 1)
        self.assertTrue(r1["record_key"].startswith("sec-"))

    def test_live_attestation_tamper_detect_and_restore(self):
        _exec, _txt = self._psql()
        # attest over the LIVE admin control-audit chain
        from canonical.admin_engine import _PgVault
        admin_rows = _PgVault().audit_rows()
        self.assertGreaterEqual(len(admin_rows), 1)
        att = ChainHeadAttestation(
            lambda: _PgVault().audit_rows()).compute("L9000")
        ok = ChainHeadAttestation(
            lambda: _PgVault().audit_rows()).verify(att, "L9001")
        self.assertTrue(ok["ok"])
        # TAMPER with one durable row's detail on live PG
        target = admin_rows[0]
        seq = target["audit_seq"]
        orig = _exec(
            "SELECT detail::text FROM admin.control_audit WHERE "
            "audit_seq = " + str(seq), {}).strip()
        _exec("UPDATE admin.control_audit SET detail = "
              + _txt("d") + "::jsonb WHERE audit_seq = " + str(seq),
              {"d": json.dumps({"tampered": True})})
        bad = ChainHeadAttestation(
            lambda: _PgVault().audit_rows()).verify(att, "L9002")
        self.assertFalse(bad["ok"])
        self.assertEqual(bad["reason"], "attestation_mismatch")
        # byte-exact restore — the chain is healthy again
        _exec("UPDATE admin.control_audit SET detail = "
              + _txt("d") + "::jsonb WHERE audit_seq = " + str(seq),
              {"d": orig})
        restored = ChainHeadAttestation(
            lambda: _PgVault().audit_rows()).verify(att, "L9003")
        self.assertTrue(restored["ok"])

    def test_live_hitl_ledger_attestation(self):
        from canonical.hitl_engine import HitlEngine, _PgVault
        hitl = HitlEngine(self.store, vault=_PgVault())
        # Phase 18 ledger rows are RESOLUTIONS (one per resolved
        # ticket) — resolve three run-scoped tickets to build a chain
        tids = [f"hitl-attest-{RUN_ID}-{i}" for i in range(3)]
        for tid in tids:
            hitl.create_ticket(_ticket(ticket_id=tid,
                                       payload_ref=f"insight:{tid}"))
            self.assertTrue(hitl.claim(tid, "role:owner")["ok"])
            self.assertTrue(hitl.resolve(
                tid, {"decision": "APPROVED",
                      "reviewer_actor_id": "role:owner"},
                "L0200")["ok"])
        ledger = [r for tid in tids
                  for r in hitl._vault.ledger_for(tid)]
        self.assertEqual(len(ledger), 3)
        self.assertTrue(all(r.get("row_hash") for r in ledger))
        att = ChainHeadAttestation(lambda: [
            r for tid in tids
            for r in hitl._vault.ledger_for(tid)]).compute("L0300")
        self.assertTrue(ChainHeadAttestation(lambda: [
            r for tid in tids
            for r in hitl._vault.ledger_for(tid)]).verify(
            att, "L0301")["ok"])
        # each per-ticket ledger chain also self-verifies (D-108)
        for tid in tids:
            self.assertTrue(hitl.verify_chain(tid)["ok"])

    def test_live_lockout_race_single_lock(self):
        rl = RateLimiter(threshold=4, window_logical=1000)
        subject = f"race-op-{RUN_ID}"
        # arm the lockout deterministically (4th event trips it)
        for i in (1, 2, 3, 4):
            arm = rl.record(subject, "failed_rbac", f"L{i:04d}")
        self.assertTrue(arm["locked_out"])
        self.assertEqual(arm["lock_until_logical"], "L1004")
        # 8 concurrent checkers while the lock is held: every one is
        # refused — no reader slips through the lockout window
        results = []
        barrier = threading.Barrier(8)

        def run():
            barrier.wait()
            results.append(rl.check(subject, "failed_rbac",
                                    "L0005")["allowed"])

        threads = [threading.Thread(target=run) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(results.count(False), 8)
        self.assertIsNotNone(rl.lockout_state(subject, "failed_rbac"))
        # still locked at a stamp BEFORE the horizon
        self.assertFalse(rl.check(subject, "failed_rbac",
                                  "L0500")["allowed"])
        # and correctly unlocked after the horizon expires
        self.assertTrue(rl.check(subject, "failed_rbac",
                                 "L2000")["allowed"])

    def test_live_audit_record_dedup_race(self):
        rec = {"record_kind": "rate_limit_hit",
               "subject": f"race-s-{RUN_ID}",
               "actor": "actor:system:security",
               "logical_at": "L0001", "detail": {"n": 1}}
        engines = [HardeningEngine(self.store, vault=self._vault())
                   for _ in range(8)]
        keys = []
        errors = []
        barrier = threading.Barrier(8)

        def run(eng):
            barrier.wait()
            try:
                keys.append(eng.audit(dict(rec))["record_key"])
            except Exception as exc:  # surfaced, never silent
                errors.append(repr(exc))

        threads = [threading.Thread(target=run, args=(e,))
                   for e in engines]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        # deterministic identity + exactly one durable row
        self.assertEqual(errors, [], f"thread failures: {errors}")
        self.assertEqual(len(set(keys)), 1)
        rows = [r for r in self._vault().rows()
                if r["record_key"] == keys[0]]
        self.assertEqual(len(rows), 1)


if __name__ == "__main__":
    unittest.main()

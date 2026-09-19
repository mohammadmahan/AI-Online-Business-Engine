"""Phase 26 — launch readiness, attestation & controlled activation.

Contract tests for D-137 (control matrix), D-138 (Go/No-Go
attestation), D-139 (activation/rollback protocol), D-140 (evidence
pack). The battery's own results are the E2E/REC evidence the matrix
consumes — the launch candidate commit is pinned from git at runtime.

Live tier (zero-skip when the stack is up): approval burns and
activation telemetry persist in the real PostgreSQL D-027 store and
the human decision chain lands in the Phase 19 control-audit vault.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL = os.path.dirname(HERE)
ROOT = os.path.dirname(LOCAL)
for p in (LOCAL, os.path.join(LOCAL, "canonical"),
          os.path.join(LOCAL, "services"),
          os.path.join(LOCAL, "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

from dataclasses import replace  # noqa: E402

from canonical.launch_contracts import (  # noqa: E402
    ContractError,
    ControlRecord,
    EvidenceRecord,
    MatrixControlSpec,
    build_matrix,
    configuration_fingerprint,
    redact_text,
    validate_matrix,
)
from canonical.launch_evaluator import (  # noqa: E402
    evaluate_matrix,
    render_report,
)
from canonical.launch_activation import (  # noqa: E402
    ActivationError,
    APPROVAL_KIND_BREAK_GLASS,
    APPROVAL_KIND_TRANSITION,
    CANARY,
    DRAFT,
    DRY_RUN,
    GO_ATTESTED,
    NO_GO,
    OBSERVING,
    OWNER_APPROVED,
    PROMOTED,
    ROLLED_BACK,
    ROLLING_BACK,
    ActivationMachine,
    ApprovalTokenError,
    TransitionRejected,
    mint_approval,
)
from canonical.launch_evidence import (  # noqa: E402
    EvidenceCollector,
    build_evidence_pack,
    canonical_matrix,
    evaluate_candidate,
    render_evidence_pack,
    validate_escalation_config,
)
from services.sync_engine import EventStore  # noqa: E402

CANDIDATE = "f6d0904"
FP = configuration_fingerprint({"env": "staging", "capture": False})


def _specs():
    domains = ("security", "backup", "payment", "inventory", "shipping",
               "monitoring", "escalation", "e2e", "recovery")
    return tuple(
        MatrixControlSpec(f"{d[:3].upper()}-001", d, f"control {d}",
                          "owner", "critical", d != "shipping",
                          f"remediate {d}")
        for d in domains)


def _pass_matrix():
    """Matrix with fresh, bound, positive evidence on every control."""
    matrix = validate_matrix(build_matrix(_specs()))
    controls = tuple(
        replace(c, evidence=EvidenceRecord(
            "EV-" + c.control_id, "commit_bound", CANDIDATE, FP,
            "ref-" + c.control_id, True))
        for c in matrix.controls)
    return replace(matrix, controls=controls)


def _machine(store, **kw):
    return ActivationMachine(store, CANDIDATE, FP, **kw)


def _tok(machine, kind, target, nonce):
    return mint_approval(machine.candidate_commit, kind, target,
                         machine.config_fingerprint, nonce)


def _fresh_store(tmp):
    return EventStore(os.path.join(tmp, "ev.json"))


# ---------------------------------------------------------------------------
# D-137 — control matrix contracts
# ---------------------------------------------------------------------------

class TestPhase26Matrix(unittest.TestCase):
    def test_control_id_domain_prefix_enforced(self):
        with self.assertRaises(ContractError):
            build_matrix((MatrixControlSpec(
                "BAK-001", "security", "t", "owner",
                "critical", True, "rem"),))

    def test_unknown_domain_rejected(self):
        with self.assertRaises(ContractError):
            build_matrix((MatrixControlSpec(
                "XXX-001", "nonsense", "t", "owner",
                "critical", True, "rem"),))

    def test_evidence_redaction_on_construct(self):
        ev = EvidenceRecord("EV-1", "commit_bound", CANDIDATE, FP, "ref",
                            True, detail="Bearer abcdef1234567890")
        self.assertNotIn("abcdef1234567890", ev.detail)
        self.assertIn("[REDACTED]", ev.detail)

    def test_fingerprint_excludes_secret_values(self):
        a = configuration_fingerprint({"env": "staging", "k": "alpha"})
        b = configuration_fingerprint({"env": "staging", "k": "beta"})
        self.assertNotEqual(a, b)
        s1 = configuration_fingerprint({"env": "s", "db_secret": "one"})
        s2 = configuration_fingerprint({"env": "s", "db_secret": "two"})
        self.assertEqual(s1, s2)  # secret values never fingerprinted

    def test_fingerprint_order_stable(self):
        self.assertEqual(
            configuration_fingerprint({"a": 1, "b": [2, 1]}),
            configuration_fingerprint({"b": [2, 1], "a": 1}))

    def test_matrix_rejects_missing_domain(self):
        specs = tuple(s for s in _specs() if s.domain != "shipping")
        with self.assertRaises(ContractError):
            validate_matrix(build_matrix(specs))

    def test_matrix_rejects_duplicate_ids(self):
        matrix = build_matrix(_specs())
        dup = replace(matrix, controls=matrix.controls + matrix.controls[:1])
        with self.assertRaises(ContractError):
            validate_matrix(dup)

    def test_redact_text_patterns(self):
        out = redact_text("postgres://u:pw@h/db api_key=xyz12345")
        self.assertNotIn("pw", out)
        self.assertIn("api_key=[REDACTED]", out)


# ---------------------------------------------------------------------------
# D-138 — Go/No-Go evaluator
# ---------------------------------------------------------------------------

class TestPhase26Evaluator(unittest.TestCase):
    def test_all_pass_is_go(self):
        self.assertEqual(evaluate_matrix(_pass_matrix(), CANDIDATE, FP).verdict, "GO")

    def test_missing_evidence_fails_closed(self):
        m = replace(_pass_matrix(), controls=tuple(
            replace(c, evidence=None) if c.control_id == "SEC-001" else c
            for c in _pass_matrix().controls))
        r = evaluate_matrix(m, CANDIDATE, FP)
        self.assertEqual(r.verdict, "NO_GO")
        self.assertIn("SEC-001", r.blockers)

    def test_stale_evidence_fails_closed(self):
        m = replace(_pass_matrix(), controls=tuple(
            replace(c, evidence=replace(c.evidence, valid=False))
            if c.control_id == "BAC-001" else c
            for c in _pass_matrix().controls))
        self.assertEqual(evaluate_matrix(m, CANDIDATE, FP).verdict, "NO_GO")

    def test_negative_outcome_is_fail_not_block(self):
        m = replace(_pass_matrix(), controls=tuple(
            replace(c, evidence=replace(c.evidence, outcome="negative"))
            if c.control_id == "BAC-001" else c
            for c in _pass_matrix().controls))
        r = evaluate_matrix(m, CANDIDATE, FP)
        self.assertEqual(r.verdict, "NO_GO")
        self.assertEqual(r.failures, ("BAC-001",))

    def test_nonmandatory_negative_yields_conditional_go(self):
        specs = tuple(
            replace(s, mandatory=False) if s.control_id == "SHI-001" else s
            for s in _specs())
        matrix = validate_matrix(build_matrix(specs))
        controls = tuple(
            replace(c, evidence=EvidenceRecord(
                "EV-" + c.control_id, "commit_bound", CANDIDATE, FP,
                "r", True,
                outcome="negative" if c.control_id == "SHI-001"
                else "positive"))
            for c in matrix.controls)
        r = evaluate_matrix(replace(matrix, controls=controls), CANDIDATE, FP)
        self.assertEqual(r.verdict, "CONDITIONAL_GO")

    def test_commit_mismatch_blocked(self):
        m = replace(_pass_matrix(), controls=tuple(
            replace(c, evidence=replace(c.evidence, commit="deadbeef"))
            if c.control_id == "SEC-001" else c
            for c in _pass_matrix().controls))
        self.assertEqual(evaluate_matrix(m, CANDIDATE, FP).verdict, "NO_GO")

    def test_fingerprint_mismatch_blocked(self):
        m = replace(_pass_matrix(), controls=tuple(
            replace(c, evidence=replace(c.evidence, config_fingerprint="f" * 64))
            if c.control_id == "MON-001" else c
            for c in _pass_matrix().controls))
        self.assertEqual(evaluate_matrix(m, CANDIDATE, FP).verdict, "NO_GO")

    def test_verdict_deterministic_byte_identical(self):
        a = json.dumps(evaluate_matrix(_pass_matrix(), CANDIDATE, FP).to_dict(),
                       sort_keys=True)
        b = json.dumps(evaluate_matrix(_pass_matrix(), CANDIDATE, FP).to_dict(),
                       sort_keys=True)
        self.assertEqual(a, b)

    def test_attestation_binds_every_input(self):
        base = evaluate_matrix(_pass_matrix(), CANDIDATE, FP)
        other_commit = evaluate_matrix(_pass_matrix(), "0" * 7, FP)
        self.assertNotEqual(base.to_dict()["attestation"],
                            other_commit.to_dict()["attestation"])
        moved = replace(base, approval_state="OWNER_APPROVED")
        self.assertNotEqual(base.to_dict()["attestation"],
                            moved.to_dict()["attestation"])

    def test_findings_stable_sorted(self):
        r = evaluate_matrix(_pass_matrix(), CANDIDATE, FP)
        ids = [f.control_id for f in r.findings]
        self.assertEqual(ids, sorted(ids))

    def test_report_render_contains_verdict(self):
        text = render_report(evaluate_matrix(_pass_matrix(), CANDIDATE, FP))
        self.assertIn("**GO**", text)
        self.assertIn("NOT sufficient", text)


# ---------------------------------------------------------------------------
# D-139 — activation protocol
# ---------------------------------------------------------------------------

class TestPhase26Activation(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = _fresh_store(self._tmp.name)

    def _approved(self, **kw):
        m = _machine(self.store, dry_probe=lambda: {"ok": True}, **kw)
        m.assess("GO", "a" * 64)
        m.approve(_tok(m, APPROVAL_KIND_TRANSITION, OWNER_APPROVED, "n1"))
        return m

    def test_illegal_transition_rejected(self):
        m = _machine(self.store)
        with self.assertRaises(TransitionRejected):
            m.transition(CANARY)

    def test_no_go_is_terminal(self):
        m = _machine(self.store)
        m.assess("NO_GO", "a" * 64)
        self.assertEqual(m.state, NO_GO)
        with self.assertRaises(TransitionRejected):
            m.transition(OWNER_APPROVED)

    def test_assess_go_reaches_go_attested(self):
        m = _machine(self.store)
        m.assess("GO", "a" * 64)
        self.assertEqual(m.state, GO_ATTESTED)

    def test_approve_requires_admin_role(self):
        m = _machine(self.store)
        m.assess("GO", "a" * 64)
        with self.assertRaises(ApprovalTokenError):
            m.approve(_tok(m, APPROVAL_KIND_TRANSITION, OWNER_APPROVED, "n1"),
                      approver_role="operator", approver_id="op1")

    def test_approval_replay_burned_once(self):
        m = self._approved()
        with self.assertRaises(TransitionRejected):
            m.approve(_tok(m, APPROVAL_KIND_TRANSITION, OWNER_APPROVED, "n1"))

    def test_fresh_nonce_permits_new_attempt(self):
        self._approved()
        m2 = _machine(self.store, dry_probe=lambda: {"ok": True})
        m2.assess("GO", "a" * 64)
        m2.approve(_tok(m2, APPROVAL_KIND_TRANSITION, OWNER_APPROVED, "n2"))
        self.assertEqual(m2.state, OWNER_APPROVED)

    def test_wrong_context_token_refused(self):
        m = _machine(self.store, dry_probe=lambda: {"ok": True})
        m.assess("GO", "a" * 64)
        forged = mint_approval("deadbeef", APPROVAL_KIND_TRANSITION,
                               OWNER_APPROVED, FP, "n")
        with self.assertRaises(ApprovalTokenError):
            m.approve(forged)

    def test_malformed_token_refused(self):
        m = _machine(self.store)
        m.assess("GO", "a" * 64)
        with self.assertRaises(ApprovalTokenError):
            m.approve("just-a-hash-no-nonce")

    def test_dry_run_zero_side_effects_and_refusal(self):
        m = self._approved()
        self.assertEqual(m.dry_run()["side_effects"], 0)
        bad = _machine(self.store, dry_probe=lambda: {"ok": False})
        bad.assess("GO", "a" * 64)
        bad.approve(_tok(bad, APPROVAL_KIND_TRANSITION, OWNER_APPROVED, "nb"))
        with self.assertRaises(TransitionRejected):
            bad.dry_run()

    def test_canary_requires_token_and_failure_leaves_state(self):
        m = self._approved()
        m.dry_run()
        with self.assertRaises(ApprovalTokenError):
            m.canary({"scope": 1}, None)
        failing = _machine(self.store, dry_probe=lambda: {"ok": True},
                           canary_action=lambda scope: {"ok": False})
        failing.assess("GO", "a" * 64)
        failing.approve(_tok(failing, APPROVAL_KIND_TRANSITION,
                             OWNER_APPROVED, "nf"))
        failing.dry_run()
        with self.assertRaises(TransitionRejected):
            failing.canary({"scope": 1},
                           _tok(failing, APPROVAL_KIND_TRANSITION, CANARY, "nc"))
        self.assertEqual(failing.state, CANARY)   # deterministic + audited
        self.assertTrue(failing.kill_switch.tripped is False)

    def test_full_path_to_promotion(self):
        m = self._approved()
        m.dry_run()
        m.canary({"scope": 1}, _tok(m, APPROVAL_KIND_TRANSITION, CANARY, "n2"))
        obs = m.observe({"error_rate": 0.1}, {"error_rate": 1.0})
        self.assertTrue(obs["ok"])
        self.assertEqual(m.promote(
            _tok(m, APPROVAL_KIND_TRANSITION, PROMOTED, "n3"))["state"],
            PROMOTED)

    def test_observation_breach_detected(self):
        m = self._approved()
        m.dry_run()
        m.canary({"scope": 1}, _tok(m, APPROVAL_KIND_TRANSITION, CANARY, "n2"))
        obs = m.observe({"error_rate": 5.0}, {"error_rate": 1.0})
        self.assertFalse(obs["ok"])
        self.assertEqual(obs["breaches"], {"error_rate": 5.0})

    def test_rollback_from_every_side_effect_state(self):
        for state in (OWNER_APPROVED, DRY_RUN, CANARY, OBSERVING, PROMOTED):
            tag = state.lower()
            store = _fresh_store(self._tmp.name)
            m = _machine(store, dry_probe=lambda: {"ok": True})
            m.assess("GO", "a" * 64)
            m.approve(_tok(m, APPROVAL_KIND_TRANSITION, OWNER_APPROVED,
                           f"r1-{tag}"))
            if state in (DRY_RUN, CANARY, OBSERVING, PROMOTED):
                m.dry_run()
            if state in (CANARY, OBSERVING, PROMOTED):
                m.canary({"scope": 1},
                         _tok(m, APPROVAL_KIND_TRANSITION, CANARY,
                              f"r2-{tag}"))
            if state in (OBSERVING, PROMOTED):
                m.observe({}, {})
            if state is PROMOTED:
                m.promote(_tok(m, APPROVAL_KIND_TRANSITION, PROMOTED,
                               f"r3-{tag}"))
            self.assertEqual(m.state, state)
            m.rollback("rehearsal breach")
            self.assertEqual(m.state, ROLLING_BACK)
            self.assertTrue(m.kill_switch.tripped)
            m.complete_rollback(lambda: {"ok": True})
            self.assertEqual(m.state, ROLLED_BACK)
            with self.assertRaises(TransitionRejected):
                m.transition(CANARY)

    def test_rollback_requires_reason_and_reconcile(self):
        m = self._approved()
        with self.assertRaises(ActivationError):
            m.rollback("")
        m.rollback("reason recorded")
        with self.assertRaises(TransitionRejected):
            m.complete_rollback(lambda: {"ok": False})

    def test_kill_switch_blocks_side_effect_transitions(self):
        m = self._approved()
        m.kill_switch.trip("k1", "material")
        with self.assertRaises(TransitionRejected):
            m.dry_run()

    def test_break_glass_burn_once(self):
        m = self._approved()
        bg = _tok(m, APPROVAL_KIND_BREAK_GLASS, "break_glass", "bg1")
        out = m.break_glass(bg, "active incident")
        self.assertTrue(out["ok"])
        with self.assertRaises(ApprovalTokenError):
            m.break_glass(bg, "again")

    def test_telemetry_written_and_redacted(self):
        from canonical.obs_contracts import JsonlLogSink, LogLedger
        path = os.path.join(self._tmp.name, "telemetry.jsonl")
        ledger = LogLedger(sink=JsonlLogSink(path))
        m = _machine(self.store, ledger=ledger, dry_probe=lambda: {"ok": True})
        m.assess("GO", "a" * 64)
        m.approve(_tok(m, APPROVAL_KIND_TRANSITION, OWNER_APPROVED, "t1"))
        m.dry_run()
        m.rollback("secret Bearer abcdef1234567890 leak in rehearsal")
        with open(path, encoding="utf-8") as fh:
            lines = [json.loads(x) for x in fh if x.strip()]
        events = {r["event"] for r in lines}
        self.assertIn("launch_owner_approved", events)
        self.assertIn("launch_rollback", events)
        blob = json.dumps(lines)
        self.assertNotIn("abcdef1234567890", blob)

    def test_human_audit_lands_in_control_chain(self):
        from canonical.admin_engine import ControlPlaneEngine, _JsonVault
        root = os.path.join(self._tmp.name, "admin")
        engine = ControlPlaneEngine(
            _fresh_store(self._tmp.name), _JsonVault(root))
        m = _machine(self.store, control_engine=engine,
                     dry_probe=lambda: {"ok": True})
        m.assess("GO", "a" * 64)
        m.approve(_tok(m, APPROVAL_KIND_TRANSITION, OWNER_APPROVED, "h1"))
        m.dry_run()
        m.canary({"scope": 1}, _tok(m, APPROVAL_KIND_TRANSITION, CANARY, "h2"))
        m.rollback("breach")
        self.assertTrue(engine.verify_chain()["ok"])
        kinds = {r["event_kind"] for r in engine._vault.audit_rows()}
        self.assertIn("launch_owner_approval", kinds)
        self.assertIn("rollback", kinds)


# ---------------------------------------------------------------------------
# D-140 — evidence collectors & pack
# ---------------------------------------------------------------------------

class TestPhase26Evidence(unittest.TestCase):
    def setUp(self):
        self.collector = EvidenceCollector(
            CANDIDATE, {"env": "staging",
                        "payment_capture_enabled": False,
                        "shipping_purchase_enabled": False})
        self.ast = {"findings": [], "style": [], "files_scanned": 68}
        self.ent = {"flagged": [], "files_scanned": 112}
        self.bnd = {"missing": []}
        self.esc = {"escalation_roles": {
            "owner": {"runbook": "docs/runbooks/owner.md"},
            "sre": {"runbook": "docs/runbooks/sre.md"}}}
        self.probes = {"probes": {"pg": {"verdict": "PASS"}}}

    def _matrix(self, collector=None, **kw):
        k = dict(restore_ok=True, battery_ok=True, census_ok=True,
                 ladder_ok=True)
        k.update(kw)
        return canonical_matrix(
            collector or self.collector, ast_report=self.ast,
            entropy_report=self.ent, bounds_report=self.bnd,
            probes_report=self.probes, escalation_cfg=self.esc, **k)

    def test_clean_inputs_go(self):
        r = evaluate_candidate(self._matrix(), CANDIDATE,
                               self.collector.fingerprint)
        self.assertEqual(r.verdict, "GO")

    def test_restore_failure_is_no_go(self):
        r = evaluate_candidate(
            self._matrix(restore_ok=False), CANDIDATE,
            self.collector.fingerprint)
        self.assertEqual(r.verdict, "NO_GO")
        self.assertIn("BAC-001", r.blockers)

    def test_gate_config_absent_blocked(self):
        c = EvidenceCollector(CANDIDATE, {"env": "staging"})
        r = evaluate_candidate(self._matrix(c), CANDIDATE, c.fingerprint)
        self.assertEqual(r.verdict, "NO_GO")
        pay = next(f for f in r.findings if f.control_id == "PAY-001")
        self.assertEqual(pay.state, "BLOCKED")

    def test_gate_open_is_negative_outcome(self):
        c = EvidenceCollector(CANDIDATE, {"env": "staging",
                                          "payment_capture_enabled": True,
                                          "shipping_purchase_enabled": False})
        r = evaluate_candidate(self._matrix(c), CANDIDATE, c.fingerprint)
        self.assertEqual(r.verdict, "NO_GO")
        pay = next(f for f in r.findings if f.control_id == "PAY-001")
        self.assertEqual(pay.state, "FAIL")

    def test_escalation_identity_fields_rejected(self):
        bad = {"escalation_roles": {"owner": {
            "runbook": "r.md", "email": "x@y.z"}}}
        self.assertFalse(validate_escalation_config(bad)["ok"])
        self.assertFalse(validate_escalation_config({})["ok"])
        self.assertTrue(validate_escalation_config(self.esc)["ok"])

    def test_evidence_pack_shape_and_render(self):
        r = evaluate_candidate(self._matrix(), CANDIDATE,
                               self.collector.fingerprint)
        pack = build_evidence_pack(
            r, battery_summary={"ok": True, "total": 1},
            census={"total": 1}, ladder={"ok": True, "total": 1},
            restore_rehearsal={"ok": True},
            monitoring={"probes": 1})
        self.assertEqual(pack["schema"], "launch.evidence_pack.v1")
        self.assertEqual(pack["verdict"], "GO")
        self.assertEqual(pack["candidate_commit"], CANDIDATE)
        # redaction contract: no secret material in evidence detail,
        # and the rendered pack is generated from the same canonical result
        ev = EvidenceRecord("EV-x", "config_bound", CANDIDATE,
                            self.collector.fingerprint, "ref", True,
                            detail="token=supersecret99")
        self.assertNotIn("supersecret99", ev.detail)
        rendered = render_evidence_pack(pack)
        self.assertIn(pack["verdict"], rendered)
        self.assertIn(CANDIDATE, rendered)


# ---------------------------------------------------------------------------
# Live PostgreSQL tier (zero-skip when the stack is up)
# ---------------------------------------------------------------------------

def _stack_up():
    try:
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
class TestPhase26LivePgE2E(unittest.TestCase):
    """Live tier: approval burns + activation telemetry persist in the
    real PostgreSQL D-027 store; the human decision chain lands in the
    Phase 19 control-audit vault."""

    def setUp(self):
        from canonical.notion_ingest import PgEventStore
        # isolated durable namespace per run: the burn ledger is
        # durable+content-addressed, so a new run must mint fresh
        # context (same discipline as Phase 25's run-scoped sources)
        self.source = f"launch26live-{uuid.uuid4().hex[:8]}"
        self.store = PgEventStore(self.source)
        self.fp = configuration_fingerprint({"env": "live-test"})

    def _tok(self, m, kind, target, nonce):
        return mint_approval(m.candidate_commit, kind, target,
                             m.config_fingerprint, nonce)

    def _machine(self, **kw):
        return ActivationMachine(self.store, CANDIDATE, self.fp, **kw)

    def test_approval_burn_is_durable_across_machines(self):
        m = self._machine(dry_probe=lambda: {"ok": True})
        m.assess("GO", "a" * 64)
        token = self._tok(m, APPROVAL_KIND_TRANSITION, OWNER_APPROVED, "live-1")
        m.approve(token)
        # a FRESH machine over the SAME durable store must see the burn
        m2 = self._machine(dry_probe=lambda: {"ok": True})
        m2.assess("GO", "a" * 64)
        with self.assertRaises(ApprovalTokenError):
            m2.approve(token)
        # a genuinely fresh nonce succeeds
        m3 = self._machine(dry_probe=lambda: {"ok": True})
        m3.assess("GO", "a" * 64)
        m3.approve(self._tok(m3, APPROVAL_KIND_TRANSITION,
                             OWNER_APPROVED, "live-2"))
        self.assertEqual(m3.state, OWNER_APPROVED)

    def test_full_activation_path_durable(self):
        m = self._machine(dry_probe=lambda: {"ok": True})
        m.assess("GO", "b" * 64)
        m.approve(self._tok(m, APPROVAL_KIND_TRANSITION, OWNER_APPROVED, "p1"))
        m.dry_run()
        m.canary({"scope": 1},
                 self._tok(m, APPROVAL_KIND_TRANSITION, CANARY, "p2"))
        m.observe({"error_rate": 0.1}, {"error_rate": 1.0})
        m.promote(self._tok(m, APPROVAL_KIND_TRANSITION, PROMOTED, "p3"))
        self.assertEqual(m.state, PROMOTED)
        # every burn is durably recorded in the live store
        burns = {"p1": OWNER_APPROVED, "p2": CANARY, "p3": PROMOTED}
        for nonce, target in burns.items():
            material = mint_approval(CANDIDATE, APPROVAL_KIND_TRANSITION,
                                     target, self.fp, nonce)
            eid = f"launch-approval|{APPROVAL_KIND_TRANSITION}|{material}"
            rec = self.store.get_record(self.source, eid)
            self.assertIsNotNone(rec, eid)
            # backend-agnostic status key: JSON store "status",
            # PgEventStore "processing_status"
            self.assertEqual(
                rec.get("status") or rec.get("processing_status"),
                "succeeded")

    def test_human_chain_in_live_admin_vault(self):
        from canonical.admin_engine import ControlPlaneEngine, default_vault
        engine = ControlPlaneEngine(self.store, default_vault())
        m = self._machine(control_engine=engine,
                          dry_probe=lambda: {"ok": True})
        m.assess("GO", "c" * 64)
        m.approve(self._tok(m, APPROVAL_KIND_TRANSITION, OWNER_APPROVED, "v1"))
        m.rollback("live rehearsal")
        self.assertTrue(engine.verify_chain()["ok"])


if __name__ == "__main__":
    unittest.main()

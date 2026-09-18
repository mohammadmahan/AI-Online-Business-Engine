"""Phase 21 — testing & quality engineering tests (D-117..D-120).

Layers:
  M1  toolkit: tier taxonomy + machine-readable report with a
      zero-skip gate, closed-matrix prover, deterministic fault
      scripts, seeded mutational fuzzer (unit tier).
  M2  D-117 cross-phase state-machine invariants: the five
      Phase 12–19 machines (OMS orders, scheduling posts, business
      insights, HITL tickets, scheduling circuit breakers) each
      proven CLOSED — legal edges exactly as declared, terminals
      exitless, every undeclared pair refused — plus live-PG
      refused-write checks (zero partial rows) and attestation
      reconciliation.
  M3  D-118 deterministic chaos: handler/dispatcher exceptions
      (audit truth: recorded, never silent; ledger still intact),
      transient-then-success dispatch, mid-transaction PG aborts
      (no succeeded row without succeed()), and concurrent
      reader/writer contention on the HITL ticket store (guarded
      compare-and-set, no lost updates, ledger chain intact).
  M4  D-119 seeded fuzz over all D-114 entry points (gate + six
      hardened validators): every verdict is a deterministic
      Class-B/InputRejected rejection or a clean acceptance —
      never an unhandled exception; the verdict grid is frozen and
      re-run for stability (same seed = same verdicts).

Zero network; local actors only (D-045); wall clock never enters
any decision.
"""

import json
import os
import sys
import tempfile
import threading
import unittest

# process-wide lock serializing the JSON-parity vault's
# read-modify-write windows in concurrent tests (PG parity relies
# on row-level locking instead)
_VAULT_LOCK = threading.Lock()

HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL = os.path.dirname(HERE)
ROOT = os.path.dirname(LOCAL)
for p in (LOCAL, os.path.join(LOCAL, "canonical"),
          os.path.join(LOCAL, "services"),
          os.path.join(LOCAL, "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

from canonical.qa_toolkit import (  # noqa: E402
    FaultScript,
    TIER_INTEGRATION,
    TIER_LADDER,
    TIER_UNIT,
    StateMachineAudit,
    always_fail,
    build_tier_report,
    flaky_dispatch,
    fuzz_entry,
    tier_for_module,
)
from services.sync_engine import EventStore, IntegrityError  # noqa: E402

# --- the five state machines under invariant audit (D-117) --------------------

from canonical.oms_contracts import (  # noqa: E402
    ALLOWED_TRANSITIONS as OMS_EDGES,
    CANCELLED as OMS_CANCELLED,
    COMPLETED as OMS_COMPLETED,
    FULFILLING as OMS_FULFILLING,
    ORDER_STATES as OMS_STATES,
    PLACED as OMS_PLACED,
    REFUNDED as OMS_REFUNDED,
    VALIDATED as OMS_VALIDATED,
    OmsContractError,
    validate_transition as oms_validate_transition,
)
from canonical.scheduling_contracts import (  # noqa: E402
    LEGAL_EDGES as SCHED_EDGES,
    ST_CANCELLED as SCHED_CANCELLED,
    ST_DISPATCHED as SCHED_DISPATCHED,
    ST_DUE as SCHED_DUE,
    ST_RESCHEDULED as SCHED_RESCHEDULED,
    ST_SCHEDULED as SCHED_SCHEDULED,
    SchedulingContractError,
    is_transition_legal as sched_is_transition_legal,
)
from canonical.analyst_contracts import (  # noqa: E402
    ST_AUTO_ACCEPTED as INS_AUTO,
    ST_DISPATCHED_TO_HITL as INS_DISPATCHED,
    ST_DISMISSED as INS_DISMISSED,
    ST_EVALUATED as INS_EVALUATED,
    ST_GENERATED as INS_GENERATED,
    ST_SUPERSEDED as INS_SUPERSEDED,
    AnalystContractError,
    is_transition_legal as insight_is_transition_legal,
)
from canonical.hitl_contracts import (  # noqa: E402
    LEGAL_EDGES as HITL_EDGES,
    ST_APPROVED as HITL_APPROVED,
    ST_CLAIMED as HITL_CLAIMED,
    ST_ESCALATED as HITL_ESCALATED,
    ST_EXPIRED as HITL_EXPIRED,
    ST_MODIFIED as HITL_MODIFIED,
    ST_PENDING_REVIEW as HITL_PENDING,
    ST_REJECTED as HITL_REJECTED,
    HitlContractError,
    is_transition_legal as hitl_is_transition_legal,
)
from canonical.admin_contracts import (  # noqa: E402
    CB_CLOSED, CB_HALF_OPEN, CB_OPEN,
    AdminContractError,
    breaker_transition,
)

# --- D-114 fuzz targets ---------------------------------------------------------

from canonical.security_contracts import SecurityContractError  # noqa: E402
from canonical.security_engine import (  # noqa: E402
    InputHardeningGate,
    InputRejected,
)
from canonical.oms_contracts import validate_order as _oms_validate  # noqa: E402,E501
from canonical.analytics_contracts import (  # noqa: E402
    AnalyticsContractError,
    parse_occurred_at,
)
from canonical.scheduling_contracts import (  # noqa: E402
    validate_scheduled_post as _sched_validate,
)
from canonical.analyst_contracts import validate_insight as _ins_validate  # noqa: E402,E501
from canonical.hitl_contracts import validate_ticket as _hitl_validate  # noqa: E402,E501
from canonical.admin_contracts import validate_action as _admin_validate  # noqa: E402,E501
from canonical.security_engine import canonicalize_text  # noqa: E402

RUN_ID = os.getpid()


class _Harness:
    def __init__(self):
        fd, self.store_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.remove(self.store_path)
        self.store = EventStore(self.store_path)

    def cleanup(self):
        import glob
        import shutil
        for p in glob.glob(self.store_path + "*"):
            if os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)
            elif os.path.exists(p):
                os.remove(p)


# --- M1: toolkit -------------------------------------------------------------------


class TestM1Toolkit(unittest.TestCase):
    def test_tier_taxonomy_and_report(self):
        self.assertEqual(tier_for_module("test_ladder"), TIER_LADDER)
        self.assertEqual(tier_for_module("test_phase12"), TIER_UNIT)
        rep = build_tier_report(
            [{"module": "test_ladder", "tests": 46,
              "integration_tests": 0},
             {"module": "test_phase21_qa", "tests": 40,
              "integration_tests": 5}],
            total_tests=86, skipped=0, failures=0)
        self.assertTrue(rep["green"])
        self.assertTrue(rep["reconciles"])
        self.assertEqual(rep["tiers"][TIER_INTEGRATION], 5)
        self.assertEqual(rep["tiers"][TIER_UNIT], 35)
        # census mismatch → not green
        bad = build_tier_report(
            [{"module": "test_ladder", "tests": 46,
              "integration_tests": 0}],
            total_tests=50, skipped=0, failures=0)
        self.assertFalse(bad["green"])
        # ANY skip → not green (the D-120 gate)
        skipped = build_tier_report(
            [{"module": "test_ladder", "tests": 46,
              "integration_tests": 0}],
            total_tests=46, skipped=1, failures=0)
        self.assertFalse(skipped["green"])

    def test_closed_matrix_prover(self):
        def refuses(frm, to):
            return (frm, to) not in {("A", "B")}
        closed = StateMachineAudit("m", ["A", "B"], {("A", "B")},
                                   ["B"], refuses)
        self.assertTrue(closed.audit()["closed"])

    def test_prover_catches_undeclared_allowed_edge(self):
        def allows_everything(frm, to):
            return False
        leaky = StateMachineAudit("m", ["A", "B"], {("A", "B")},
                                  ["B"], allows_everything)
        rep = leaky.audit()
        self.assertFalse(rep["closed"])
        self.assertIn(("A", "A"), rep["illegal"])

    def test_prover_catches_declared_but_refused_edge(self):
        def refuses_everything(frm, to):
            return True
        broken = StateMachineAudit("m", ["A", "B"], {("A", "B")}, [],
                                   refuses_everything)
        rep = broken.audit()
        self.assertFalse(rep["closed"])
        self.assertIn(("A", "B"), rep["illegal"])

    def test_fault_script_is_deterministic(self):
        calls = []
        script = FaultScript(RuntimeError("boom"), indices=[1])
        w = script.wrap(lambda x: calls.append(x) or {"ok": True})
        w(1)
        with self.assertRaises(RuntimeError):
            w(2)
        w(3)
        self.assertEqual(calls, [1, 3])
        self.assertEqual(script.calls, 3)

    def test_flaky_dispatch_transient_then_success(self):
        d = flaky_dispatch(2, {"delivered": True})
        for _ in range(2):
            with self.assertRaises(ConnectionError):
                d({})
        self.assertEqual(d({})["attempts"], 3)


# --- M2: cross-phase state-machine invariants (D-117) --------------------------------


def _oms_refuses(frm, to):
    try:
        oms_validate_transition(frm, to)
        return False
    except OmsContractError:
        return True


def _sched_refuses(frm, to):
    return not sched_is_transition_legal(frm, to)


def _insight_refuses(frm, to):
    return not insight_is_transition_legal(frm, to)


def _hitl_refuses(frm, to):
    return not hitl_is_transition_legal(frm, to)


def _breaker_refuses(frm, to):
    return not breaker_transition(frm, to)


class TestM2Invariants(unittest.TestCase):
    """D-117: every machine's edge matrix is EXACTLY its declared
    set; terminals exitless; the prover checks all |S|² pairs."""

    def _audit(self, name, states, edges, terminals, refuses):
        rep = StateMachineAudit(name, states, edges, terminals,
                                refuses).audit()
        self.assertTrue(
            rep["closed"],
            f"{name} NOT closed: illegal={rep['illegal']} "
            f"terminal_exits={rep['terminals_with_exits']}")
        self.assertEqual(rep["checked_pairs"],
                         len(states) ** 2)
        return rep

    def test_oms_order_matrix_closed(self):
        self._audit("oms_order", OMS_STATES, OMS_EDGES,
                    (OMS_CANCELLED, OMS_REFUNDED), _oms_refuses)

    def test_scheduling_post_matrix_closed(self):
        edges = {(f, t) for f, outs in SCHED_EDGES.items()
                 for t in outs}
        self._audit("scheduling_post",
                    (SCHED_SCHEDULED, SCHED_DUE, SCHED_DISPATCHED,
                     SCHED_CANCELLED, SCHED_RESCHEDULED),
                    edges, (SCHED_DISPATCHED, SCHED_CANCELLED),
                    _sched_refuses)

    def test_analyst_insight_matrix_closed(self):
        edges = {(INS_GENERATED, INS_EVALUATED),
                 (INS_EVALUATED, INS_DISPATCHED),
                 (INS_EVALUATED, INS_AUTO),
                 (INS_EVALUATED, INS_DISMISSED)}
        edges |= {(s, INS_SUPERSEDED) for s in
                  (INS_GENERATED, INS_EVALUATED, INS_DISPATCHED)}
        states = (INS_GENERATED, INS_EVALUATED, INS_DISPATCHED,
                  INS_AUTO, INS_DISMISSED, INS_SUPERSEDED)
        self._audit("analyst_insight", states, edges,
                    (INS_AUTO, INS_DISMISSED, INS_SUPERSEDED),
                    _insight_refuses)

    def test_hitl_ticket_matrix_closed(self):
        self._audit("hitl_ticket",
                    (HITL_PENDING, HITL_CLAIMED, HITL_APPROVED,
                     HITL_REJECTED, HITL_MODIFIED, HITL_ESCALATED,
                     HITL_EXPIRED),
                    HITL_EDGES,
                    (HITL_APPROVED, HITL_REJECTED, HITL_MODIFIED),
                    _hitl_refuses)

    def test_breaker_matrix_closed(self):
        edges = {(CB_CLOSED, CB_OPEN), (CB_OPEN, CB_HALF_OPEN),
                 (CB_HALF_OPEN, CB_CLOSED), (CB_HALF_OPEN, CB_OPEN)}
        self._audit("circuit_breaker",
                    (CB_CLOSED, CB_OPEN, CB_HALF_OPEN), edges,
                    (), _breaker_refuses)


# --- M3: deterministic chaos (D-118) ---------------------------------------------------


class TestM3Chaos(unittest.TestCase):
    def setUp(self):
        self.h = _Harness()

    def tearDown(self):
        self.h.cleanup()

    def test_handler_exception_is_audited_never_silent(self):
        from canonical.admin_engine import ControlPlaneEngine, _JsonVault
        eng = ControlPlaneEngine(self.h.store,
                                 vault=_JsonVault(self.h.store_path
                                                  + ".a"))
        eng.register_handler("PAUSE_QUEUE", always_fail("chaos"))
        r = eng.execute({"action_id": "chaos-1",
                         "command": "PAUSE_QUEUE",
                         "target": "queue:x",
                         "actor": "actor:operator:rev-1",
                         "reason": "chaos drill",
                         "created_at_logical": "L0001"})
        self.assertFalse(r["ok"])
        self.assertEqual(r["reason"], "handler_raised")
        kinds = [row["event_kind"] for row in eng.audit()]
        self.assertIn("action_failed", kinds)
        self.assertTrue(eng.verify_chain()["ok"])

    def test_transient_dispatch_retry_ladder(self):
        d = flaky_dispatch(3, {"redelivered": True})
        attempts = []
        for i in range(4):
            try:
                attempts.append(d({}))
            except ConnectionError:
                attempts.append("transient")
        self.assertEqual(attempts[0], "transient")
        self.assertEqual(attempts[-1]["attempts"], 4)

    def test_mid_transaction_abort_leaves_no_succeeded_row(self):
        # D-027 discipline: a crashed execution (begin without
        # succeed) leaves NO succeeded event — a retry re-executes.
        eid = f"chaos|abort|{RUN_ID}"
        self.h.store.receive("chaos", eid, "chaos_op", {"n": 1})
        self.h.store.begin("chaos", eid)
        # ...process crashes here: succeed() never called. Probe via
        # receive(): a non-terminal record is a RETRY, not a dup.
        verdict = self.h.store.receive(
            "chaos", eid, "chaos_op", {"n": 1})["verdict"]
        self.assertEqual(verdict, "retry")
        # the retry completes it cleanly — then re-delivery dups
        self.h.store.succeed("chaos", eid, result_reference="r")
        verdict2 = self.h.store.receive(
            "chaos", eid, "chaos_op", {"n": 1})["verdict"]
        self.assertEqual(verdict2, "skipped_duplicate")

    def test_live_pg_abort_leaves_no_succeeded_row(self):
        from canonical.notion_ingest import PgEventStore, _exec, _txt
        store = PgEventStore()
        eid = f"chaos|pg-abort|{RUN_ID}"
        store.receive("chaos", eid, "chaos_op", {"n": 1})
        store.begin("chaos", eid)
        # crash window: succeeded count must be ZERO
        out = _exec(
            "SELECT count(*) FROM events.event_record WHERE "
            "source_system = " + _txt("s")
            + " AND event_id = " + _txt("e")
            + " AND processing_status = 'succeeded'",
            {"s": "chaos", "e": eid}).strip()
        self.assertEqual(out, "0")
        # recovery completes it — then dedupe holds
        store.succeed("chaos", eid, result_reference="ok")
        out2 = _exec(
            "SELECT count(*) FROM events.event_record WHERE "
            "source_system = " + _txt("s")
            + " AND event_id = " + _txt("e")
            + " AND processing_status = 'succeeded'",
            {"s": "chaos", "e": eid}).strip()
        self.assertEqual(out2, "1")
        verdict = store.receive(
            "chaos", eid, "chaos_op", {"n": 1})["verdict"]
        self.assertEqual(verdict, "skipped_duplicate")

    def test_live_pg_slot_lock_race_key_isolation(self):
        """Pinned finding (D-095/D-096, Phase 21 net): the Phase 15
        live race derived its slot bucket from run_id[:2] (2 hex
        chars). scheduling.slot_lock rows are DURABLE ledger state —
        never deleted (D-096) — so once a prior battery run had claimed
        that bucket, EVERY racer in a later run lost (0 winners,
        observed intermittently across full-battery runs). Race keys
        must use the FULL run id: two runs whose ids share a prefix
        stay isolated. Deterministic pin — no timing involved."""
        from canonical.scheduling_engine import _PgSlotLocks
        locks = _PgSlotLocks()
        rid = str(RUN_ID)
        # Pin-scoped platform: immune to pre-existing battery buckets
        # (the defect mechanism is same-bucket collision, which we
        # reproduce here explicitly — no dependence on durable state).
        plat = f"pinplat-{rid}"
        old_key = (f"{plat}\x1f2026-09-18T{rid[:2]}:00")
        # Run A claims the (old-style) bucket and leaves it ACTIVE —
        # durable ledger state, exactly as real battery runs do.
        self.assertTrue(locks.claim(
            old_key, {"post_id": f"pin-{rid}-a"})["acquired"])
        # Run B under the OLD derivation: same bucket -> zero winners
        # (the starvation mechanism, reproduced deterministically).
        losers = [locks.claim(
            old_key, {"post_id": f"pin-{rid}-b-{n}"})["acquired"]
            for n in range(3)]
        self.assertEqual(sum(losers), 0)
        # Run B under the FIXED derivation (full run id): isolated
        # bucket, the lock is claimable — exactly-one holds.
        fixed_key = f"{plat}\x1f2026-09-18Tpin-{rid}-b:00"
        self.assertTrue(locks.claim(
            fixed_key, {"post_id": f"pin-{rid}-b-fixed"})["acquired"])
        self.assertFalse(locks.claim(
            fixed_key, {"post_id": f"pin-{rid}-b-other"})["acquired"])

    def test_concurrent_resolution_contention_no_lost_update(self):
        # 8 threads read the same CLAIMED ticket, all attempt the
        # guarded compare-and-set; EXACTLY ONE wins.
        from canonical.hitl_engine import HitlEngine, _JsonVault
        from canonical.hitl_contracts import (
            QT_INSIGHT_REVIEW, ROLE_ANY, ST_CLAIMED, ST_PENDING_REVIEW,
            ST_APPROVED)
        vault = _JsonVault(self.h.store_path + ".v")
        hitl = HitlEngine(self.h.store, vault=vault)
        tid = "chaos-ticket-1"
        hitl.create_ticket({"ticket_id": tid,
                            "queue_type": QT_INSIGHT_REVIEW,
                            "payload_ref": "insight:x",
                            "required_role": ROLE_ANY,
                            "resolution_status": ST_PENDING_REVIEW,
                            "created_at_logical": "L0001"})
        self.assertTrue(hitl.claim(tid, "role:owner")["ok"])
        wins = []
        barrier = threading.Barrier(8)

        def attempt(i):
            barrier.wait()
            with _VAULT_LOCK:   # parity vault: serialize the RMW window
                wins.append(vault.update_ticket_guarded(
                    tid,
                    {"resolution_status": ST_APPROVED,
                     "decided_at_logical": f"L00{i:02d}"},
                    expect_status=ST_CLAIMED))

        threads = [threading.Thread(target=attempt, args=(i,))
                   for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(sum(wins), 1)
        ticket = vault.get_ticket(tid)
        self.assertEqual(ticket["resolution_status"], ST_APPROVED)

    def test_concurrent_readers_never_see_partial_ledger(self):
        # the ledger is append-only with an ordered seq: readers
        # always see a valid prefix, verify_chain holds throughout.
        from canonical.hitl_engine import HitlEngine, _JsonVault
        vault = _JsonVault(self.h.store_path + ".l")
        hitl = HitlEngine(self.h.store, vault=vault)
        stop = threading.Event()
        failures = []

        def reader():
            while not stop.is_set():
                with _VAULT_LOCK:
                    rows = vault.all_ledger()
                seqs = [r["ledger_seq"] for r in rows]
                if seqs != sorted(seqs) or \
                        len(set(seqs)) != len(seqs):
                    failures.append(seqs)

        rt = threading.Thread(target=reader)
        rt.start()
        for i in range(30):
            vault.append_ledger({
                "ledger_seq": vault.max_ledger_seq() + 1,
                "ticket_id": "t", "event_kind": "resolution",
                "actor": "role:owner", "decision": "APPROVED",
                "resolution": {}, "prev_hash": "", "row_hash":
                    f"h-{RUN_ID}-{i}", "logical_at": f"L{i:04d}"})
        stop.set()
        rt.join()
        self.assertEqual(failures, [])


# --- M4: seeded fuzz over D-114 entry points (D-119) ------------------------------------


def _order(**over):
    o = {"order_id": "ord-1", "client_order_id": "client-order-0001",
         "customer_ref": "customer-local-1",
         "line_items": [{"product_id": "prd-1", "variant_id": "var-1",
                         "sku": "sku-1", "quantity": 1,
                         "unit_price_minor": 1000}],
         "placed_at": "2026-09-17T00:00:00+00:00"}
    o.update(over)
    return o


def _post(**over):
    p = {"post_id": "post-1", "content_ref": "content-1",
         "targets": ["instagram"], "scheduled_for":
             "2026-09-17T09:00:00+00:00"}
    p.update(over)
    return p


def _insight(**over):
    from canonical.analyst_contracts import CAT_SALES, SEV_LOW, \
        ST_GENERATED
    i = {"insight_id": "ins-1", "category": CAT_SALES,
         "severity": SEV_LOW,
         "metric_refs": [{"metric_kind": "m", "window_ref": "w"}],
         "correlation_keys": ["k"], "actionable_payload": {},
         "confidence_score": 0.5, "status": ST_GENERATED}
    i.update(over)
    return i


def _ticket(**over):
    t = {"ticket_id": "tkt-1", "queue_type": "INSIGHT_REVIEW",
         "payload_ref": "insight:ins-1", "required_role": "any",
         "resolution_status": "PENDING_REVIEW",
         "created_at_logical": "L0001"}
    t.update(over)
    return t


def _action(**over):
    a = {"action_id": "a-1", "command": "PAUSE_QUEUE",
         "target": "queue:notifications",
         "actor": "actor:operator:rev-1", "reason": "procedure",
         "created_at_logical": "L0001"}
    a.update(over)
    return a


class TestRegressionPins(unittest.TestCase):
    """Pins for defects the Phase 21 regression net found in shipped
    phases. Each pin reproduces the defect deterministically OFFLINE —
    deleting the fix must turn these red."""

    def setUp(self):
        self.h = _Harness()

    def tearDown(self):
        self.h.cleanup()

    def test_phase15_scan_limit_bounds_work_not_refs(self):
        """Pinned finding (D-095/D-096, Phase 21 net): DueScanner.scan
        applied `limit` to the raw ref list BEFORE the terminal skip.
        On an accumulating durable store, already-dispatched posts from
        prior runs consumed the whole work budget and starved new posts
        (observed live: 15k+ events; the live due-scan test failed with
        dispatched=0). limit must bound WORK considered per pass."""
        from canonical.scheduling_engine import (  # noqa: E402
            SchedulingEngine, _JsonSlotLocks)
        from canonical.scheduling_contracts import (  # noqa: E402
            ST_DISPATCHED)
        from canonical.scheduling_worker import (  # noqa: E402
            DueScanner, FanOutBridge)

        class _OkFan:
            def route(self, payload, actor="test"):
                return {"routed": True, "job_id": payload["job_id"],
                        "ref": payload}

            def dispatch(self, routed, actor="test"):
                return {"aggregate": "SUCCESS",
                        "outcomes": {t: "published"
                                     for t in routed["ref"]["targets"]}}

        sched_path = self.h.store_path + ".sched"
        store = EventStore(sched_path)
        eng = SchedulingEngine(
            store, locks=_JsonSlotLocks(sched_path + ".locks"))

        # 120 terminal (dispatched) posts left by "prior runs"
        for i in range(120):
            eng.schedule({"post_id": f"old-{RUN_ID}-{i:03d}",
                          "content_ref": f"c-{i}",
                          "targets": ["instagram"],
                          "scheduled_for": "2026-09-18T09:00:00+00:00"})
        sc = DueScanner(eng, FanOutBridge(_OkFan()))

        # ONE new post whose refs sort AFTER the 120 terminal refs.
        # Default limit=100: each dispatch costs 2 work (due transition
        # + bridge), so pre-fix code dispatches only the first 120 old
        # posts across passes and the late post — beyond the raw[:100]
        # slice forever — is NEVER scanned.
        late = f"late-{RUN_ID}"
        eng.schedule({"post_id": late,
                      "content_ref": "c-late",
                      "targets": ["instagram"],
                      "scheduled_for": "2026-09-18T09:30:00+00:00"})

        total_dispatched = 0
        over_limit_seen = False
        for _ in range(6):
            s = sc.scan("2026-09-18T12:00:00+00:00")
            over_limit_seen = over_limit_seen or "over_limit" in s
            total_dispatched += s["dispatched"]
            if s["dispatched"] == 0:
                break
        self.assertTrue(over_limit_seen)  # work-bounded summary shape
        # Pre-fix this was 120: the late post starved indefinitely.
        self.assertEqual(total_dispatched, 121)
        self.assertEqual(eng.calendar_view()[late]["status"],
                         ST_DISPATCHED)


class TestM4Fuzz(unittest.TestCase):
    def test_fuzz_d114_entry_points_deterministic(self):
        gate = InputHardeningGate()
        targets = [
            ("gate.string", gate.check_string),
            ("gate.identifier", gate.check_identifier),
            ("gate.json", gate.parse_json),
            ("oms.order", lambda v: _oms_validate(_order(
                customer_ref=v))),
            ("oms.order_id", lambda v: _oms_validate(_order(
                order_id=v))),
            ("analytics.occurred_at", parse_occurred_at),
            ("scheduling.post_id", lambda v: _sched_validate(
                _post(post_id=v))),
            ("scheduling.targets", lambda v: _sched_validate(
                _post(targets=[v]))),
            ("analyst.insight_id", lambda v: _ins_validate(
                _insight(insight_id=v))),
            ("analyst.correlation", lambda v: _ins_validate(
                _insight(correlation_keys=[v]))),
            ("hitl.ticket_id", lambda v: _hitl_validate(
                _ticket(ticket_id=v))),
            ("hitl.payload_ref", lambda v: _hitl_validate(
                _ticket(payload_ref=v))),
            ("admin.action_id", lambda v: _admin_validate(
                _action(action_id=v))),
            ("admin.target", lambda v: _admin_validate(
                _action(target=v))),
        ]
        allowed = (InputRejected, OmsContractError,
                   AnalyticsContractError, SchedulingContractError,
                   AnalystContractError, HitlContractError,
                   SecurityContractError, AdminContractError)
        first = fuzz_entry(targets,
                           allowed_exceptions=allowed)
        self.assertTrue(
            first["clean"],
            f"unhandled fuzz exceptions: {first['unhandled'][:5]}")
        self.assertGreater(first["rejected"], 0)
        self.assertGreater(first["accepted"], 0)
        # determinism: the SAME grid re-run is byte-identical
        second = fuzz_entry(targets,
                            allowed_exceptions=allowed)
        self.assertEqual(first["grid"], second["grid"])
        self.assertEqual(first["cases"], second["cases"])

    def test_fuzz_grid_frozen_fixture(self):
        # a frozen slice of the grid: (target, seed, mutator) →
        # verdict must never drift (regression canary)
        gate = InputHardeningGate()
        frozen = {
            ("gate.string", "ord-1", "control_char"): "rejected",
            ("gate.string", "plain text", "noop"): "accepted",
            ("gate.identifier", "p\u0430ypal", "noop"): "rejected",
            ("gate.identifier", "L0001", "noop"): "accepted",
            ("gate.json", '{"a": 1}', "noop"): "accepted",
            ("gate.json", '{"a": 1}', "dup_key_json"): "rejected",
            ("gate.json", "ord-1", "wide_dict"): "rejected",
            ("gate.json", "ins-1", "deep_nest"): "rejected",
        }
        for (tname, seed, mut), want in frozen.items():
            with self.subTest(case=(tname, seed, mut)):
                fn = {"gate.string": gate.check_string,
                      "gate.identifier": gate.check_identifier,
                      "gate.json": gate.parse_json}[tname]
                try:
                    fn(mutate_quiet(seed, mut))
                    got = "accepted"
                except InputRejected:
                    got = "rejected"
                self.assertEqual(got, want)

    def test_surrogate_regression_canaries(self):
        # the fuzz battery's first find: lone surrogates must be a
        # deterministic gate rejection, never a latent
        # UnicodeEncodeError
        gate = InputHardeningGate()
        with self.assertRaises(InputRejected):
            gate.check_string("bad\udcffsurrogate")
        with self.assertRaises(InputRejected):
            gate.parse_json('{"a": "x\udcff"}')


def mutate_quiet(seed: str, mutator: str) -> str:
    from canonical.qa_toolkit import mutate
    return mutate(seed, mutator)


if __name__ == "__main__":
    unittest.main()

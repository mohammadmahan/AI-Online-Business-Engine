"""Phase 23 — resilience & cost optimization tests (D-125..D-128).

Layers:
  M1  D-125 compaction: state-based eligibility predicates, snapshot
      write/verify round-trip, archive FORGERY detection (byte flip,
      dropped line, reordered row), fail-closed semantics (a snapshot
      that does not verify means NOTHING is removed), manifest shape,
      keyset pagination (ordered, disjoint, no OFFSET), unknown
      surfaces refused, breaker-horizon eligibility (unit tier).
  M2  D-126 resilience envelope: backoff schedule (jitter-free),
      D-052 class routing (A retries, B/C/E terminal, D quarantine),
      BudgetedExecutor refusal semantics, transport concurrency
      ceiling — queueing drains and saturation fast-fails
      deterministically with zero hangs (unit tier, real threads).
  M3  D-127 budgets: env-configurable baselines, ≥80% warning, hard
      refusal BEFORE the consuming call with an unchanged ledger,
      exact-boundary allowance, D-063 write-through (tokens + calls
      as one logical event), batch stop-at-refusal, scope separation,
      red paths unbudgeted by construction (unit tier).
  M4  live-PG E2E: COMPACT_RETIREABLE against the real store (active
      locks SURVIVE, inactive removed, manifests recorded, chain
      attestation still green), keyset pages over the 20k-row event
      store (live tier; zero-skip when the stack is up).

Zero network beyond loopback/psql transport (D-045); wall clock never
enters any decision; tamper evidence is asserted, never weakened.
"""

import json
import os
import sys
import tempfile
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL = os.path.dirname(HERE)
ROOT = os.path.dirname(LOCAL)
for p in (LOCAL, os.path.join(LOCAL, "canonical"),
          os.path.join(LOCAL, "services"),
          os.path.join(LOCAL, "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

from canonical.compaction import (  # noqa: E402
    CompactionError,
    SCHEMA_VERSION as MANIFEST_SCHEMA,
    compact,
    eligible_breaker_rows,
    eligible_event_rows,
    eligible_slot_lock_rows,
    keyset_scan_events,
    verify_snapshot,
    write_snapshot,
)
from canonical.resilience import (  # noqa: E402
    BudgetedExecutor,
    ResilienceError,
    RetryPolicy,
    classify_by_message,
    run_with_retry,
)
from canonical.budget_contracts import (  # noqa: E402
    DEFAULT_BASELINES,
    BudgetContractError,
    ResourceBudget,
    default_budgets,
    env_overrides,
    soft_threshold,
)
from canonical.budget_engine import (  # noqa: E402
    BudgetExhausted,
    BudgetLedger,
)
from canonical.security_engine import ChainHeadAttestation  # noqa: E402


def _rejects(fn, exc):
    try:
        fn()
        return False
    except exc:
        return True


class TestM1Compaction(unittest.TestCase):
    def test_state_based_eligibility(self):
        self.assertEqual(len(eligible_event_rows([
            {"processing_status": "succeeded"},
            {"processing_status": "pending"},
            {"processing_status": "retry"}])), 1)
        br = [{"state": "CLOSED", "tripped_at_logical": "L9"},
              {"state": "OPEN", "tripped_at_logical": "L1"},
              {"state": "OPEN", "tripped_at_logical": "L99"}]
        self.assertEqual(len(eligible_breaker_rows(br, "L50")), 2)
        sl = [{"platform": "p", "slot_bucket": "a", "active": True},
              {"platform": "p", "slot_bucket": "b", "active": False}]
        self.assertEqual(len(eligible_slot_lock_rows(sl)), 1)

    def test_snapshot_round_trip_and_forgery_detection(self):
        rows = [{"a": 1, "b": "x"}, {"a": 2, "b": "y"}]
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "s.jsonl")
            desc = write_snapshot(path, rows)
            self.assertEqual(desc["row_count"], 2)
            self.assertTrue(verify_snapshot(path)["ok"])
            with open(path, encoding="utf-8") as fh:
                original = fh.read()
            forgeries = [
                original.replace('"b": "x"', '"b": "X"'),   # byte flip
                original.replace("\n", "", 1),              # dropped line
                "\n".join(reversed(original.splitlines()))  # reordered
                + "\n",
            ]
            for i, bad in enumerate(forgeries):
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(bad)
                self.assertTrue(_rejects(
                    lambda: verify_snapshot(path), CompactionError),
                    f"forgery {i} not detected")

    def test_fail_closed_no_teardown_without_verified_snapshot(self):
        rows = [{"platform": "p", "slot_bucket": "b", "active": False}]
        with tempfile.TemporaryDirectory() as td:
            deleted = []
            # force a snapshot-write failure: the "directory" is a file
            blocker = os.path.join(td, "blocker")
            with open(blocker, "w", encoding="utf-8") as fh:
                fh.write("not a directory")
            try:
                compact("scheduling.slot_lock", rows_provider=lambda: rows,
                        delete_fn=lambda elig: deleted.extend(elig) or 1,
                        archive_path=os.path.join(blocker, "a.jsonl"))
                self.fail("expected a snapshot-write failure")
            except OSError:
                pass  # fail-closed propagates the write failure
            self.assertEqual(deleted, [])  # nothing removed

    def test_delete_count_mismatch_fails_closed(self):
        rows = [{"platform": "p", "slot_bucket": "b", "active": False},
                {"platform": "p", "slot_bucket": "c", "active": False}]
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "s.jsonl")
            self.assertTrue(_rejects(
                lambda: compact("scheduling.slot_lock",
                                rows_provider=lambda: rows,
                                delete_fn=lambda elig: 1,  # wrong count
                                archive_path=path),
                CompactionError))

    def test_unknown_surface_refused(self):
        self.assertTrue(_rejects(
            lambda: compact("nope.table", rows_provider=lambda: [],
                            delete_fn=lambda e: 0, archive_path="/tmp/x"),
            CompactionError))
        self.assertTrue(_rejects(
            lambda: compact("admin.circuit_breakers",
                            rows_provider=lambda: [],
                            delete_fn=lambda e: 0,
                            archive_path="/tmp/x", horizon=""),
            CompactionError))  # breaker surface needs a horizon

    def test_empty_eligible_set_is_auditable_noop(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "s.jsonl")
            m = compact("scheduling.slot_lock",
                        rows_provider=lambda: [{"active": True}],
                        delete_fn=lambda e: self.fail("no deletes"),
                        archive_path=path)
            self.assertEqual((m["eligible"], m["removed"]), (0, 0))
            self.assertFalse(os.path.exists(path))  # no snapshot needed

    def test_keyset_pagination_unit(self):
        class _FakeExec:
            """4-row deterministic store; the cursor is the event id
            (params['b']) — emulates `(a,b) > (after_a, after_b)`."""
            def __call__(self, sql, params):
                limit = int(sql.rsplit("LIMIT", 1)[1].strip())
                cursor = params.get("b") or "e-1"
                start = int(cursor[1:]) + 1
                rows = [(str(i), f"e{i}", "succeeded")
                        for i in range(start, min(start + limit, 4))]
                return "\n".join(
                    "\x1f".join(r + ("END",)) for r in rows)

        page1 = keyset_scan_events(_FakeExec(), "", "e-1", batch=2)
        self.assertEqual([r["event_id"] for r in page1["rows"]],
                         ["e0", "e1"])
        page2 = keyset_scan_events(_FakeExec(),
                                   page1["next_after_source"],
                                   page1["next_after_event"], batch=2)
        self.assertEqual([r["event_id"] for r in page2["rows"]],
                         ["e2", "e3"])
        # keyset contract: a FULL page conservatively reports has_more
        # (the caller advances); termination is the empty next page.
        page3 = keyset_scan_events(_FakeExec(),
                                   page2["next_after_source"],
                                   page2["next_after_event"], batch=2)
        self.assertEqual(page3["rows"], [])
        self.assertFalse(page3["has_more"])

    def test_manifest_schema_header(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "s.jsonl")
            write_snapshot(path, [{"x": 1}])
            with open(path, encoding="utf-8") as fh:
                header = json.loads(fh.readline())
            self.assertEqual(header["schema_version"], MANIFEST_SCHEMA)


class TestM2Resilience(unittest.TestCase):
    def test_backoff_schedule_jitter_free(self):
        p = RetryPolicy(max_attempts=6, base_backoff=3)
        self.assertEqual([p.backoff_for(i) for i in range(1, 6)],
                         [3, 6, 12, 24, 48])
        self.assertTrue(_rejects(lambda: RetryPolicy(0), ResilienceError))
        self.assertTrue(_rejects(lambda: p.backoff_for(0),
                                 ResilienceError))

    def test_d052_class_routing(self):
        p = RetryPolicy(max_attempts=3, base_backoff=1)
        self.assertEqual(run_with_retry(
            p, lambda a: (_ for _ in ()).throw(
                RuntimeError("ETIMEDOUT reset")))["outcome"],
            "exhausted_retryable")
        self.assertEqual(run_with_retry(
            p, lambda a: (_ for _ in ()).throw(
                ValueError("schema violation")))["outcome"],
            "terminal")
        self.assertEqual(run_with_retry(
            p, lambda a: (_ for _ in ()).throw(
                PermissionError("forbidden RED tier")))["outcome"],
            "quarantined")
        # explicit failure_class attribute wins
        class _C(Exception):
            failure_class = "C"
        self.assertEqual(run_with_retry(
            p, lambda a: (_ for _ in ()).throw(_C("x")))["failure_class"],
            "C")
        # retries then succeeds
        state = {"n": 0}

        def flaky(attempt):
            state["n"] += 1
            if attempt < 3:
                raise RuntimeError("503 unavailable")
            return "ok"
        v = run_with_retry(p, flaky)
        self.assertTrue(v["ok"] and v["attempts"] == 3)

    def test_budgeted_executor_refusal(self):
        ex = BudgetedExecutor(max_total_attempts=3, max_total_failures=1)
        p = RetryPolicy(max_attempts=3, base_backoff=1)
        ex.execute(p, lambda a: (_ for _ in ()).throw(
            ValueError("schema bad")))
        v = ex.execute(p, lambda a: "never")
        self.assertEqual(v["outcome"], "budget_refused")
        self.assertEqual(v["attempts"], 0)  # refused BEFORE any attempt
        self.assertTrue(ex.exhausted)

    def test_transport_ceiling_queue_and_fast_fail(self):
        import importlib
        import scripts.seed_registry as sr
        old_wait = sr._QUEUE_WAIT_S
        try:
            # queueing: 24 contenders, ceiling 8 — all drain, no hang
            results = {"ok": 0, "sat": 0}
            lock = threading.Lock()

            def contender():
                try:
                    sr.q("SELECT 1")
                    with lock:
                        results["ok"] += 1
                except sr.TransportSaturation:
                    with lock:
                        results["sat"] += 1
            ts = [threading.Thread(target=contender) for _ in range(24)]
            for t in ts:
                t.start()
            for t in ts:
                t.join()
            self.assertEqual(results["ok"], 24)
            self.assertEqual(results["sat"], 0)
            # saturation: hold every permit, short wait ⇒ fast-fail
            sr._QUEUE_WAIT_S = 0.2
            held = []
            while sr._CEILING.acquire(blocking=False):
                held.append(True)
            t0 = time.monotonic()
            try:
                sr.q("SELECT 1")
                self.fail("expected TransportSaturation")
            except sr.TransportSaturation:
                self.assertLess(time.monotonic() - t0, 5)
            finally:
                for _ in held:
                    sr._CEILING.release()
        finally:
            sr._QUEUE_WAIT_S = old_wait
        # deterministic Class-A verdict
        self.assertEqual(
            classify_by_message(str(sr.TransportSaturation("timeout"))),
            "A")


class TestM3Budgets(unittest.TestCase):
    def test_env_configurable_baselines(self):
        self.assertEqual(default_budgets()[0].resource, "llm_tokens")
        self.assertEqual(
            default_budgets()[0].limit,
            DEFAULT_BASELINES["llm_tokens"])
        os.environ["PHASE23_BUDGET_LLM_TOKENS"] = "777"
        try:
            self.assertEqual(default_budgets()[0].limit, 777)
        finally:
            del os.environ["PHASE23_BUDGET_LLM_TOKENS"]
        os.environ["PHASE23_BUDGET_LLM_TOKENS"] = "-5"
        try:
            self.assertTrue(_rejects(default_budgets,
                                     BudgetContractError))
        finally:
            del os.environ["PHASE23_BUDGET_LLM_TOKENS"]

    def test_soft_warning_and_hard_refusal(self):
        led = BudgetLedger([ResourceBudget("llm_tokens", 100,
                                           "per_run", "green")])
        self.assertFalse(led.consume("llm_tokens", 79)["warning"])
        self.assertTrue(led.consume("llm_tokens", 1)["warning"])  # 80%
        self.assertTrue(led.check("llm_tokens", 10)["allowed"])
        try:
            led.consume("llm_tokens", 21)  # would exceed 100
            self.fail("expected BudgetExhausted")
        except BudgetExhausted:
            pass
        # refusal changed nothing (pre-dispatch semantics)
        self.assertEqual(led.consumed("llm_tokens", "per_run", "green"),
                         80)
        # exact boundary allowed
        r = led.consume("llm_tokens", 20)
        self.assertEqual(r["consumed_after"], 100)
        self.assertTrue(_rejects(lambda: led.consume("llm_tokens", 1),
                                 BudgetExhausted))

    def test_d063_write_through_one_event_two_resources(self):
        led = BudgetLedger(default_budgets())
        out = led.consume_llm(5_000, 1, logical_at="L1",
                              correlation_id="corr-1")
        self.assertEqual(len(out["rows"]), 2)
        self.assertEqual(
            led.consumed("llm_tokens", "per_run", "green"), 5_000)
        self.assertEqual(
            led.consumed("llm_calls", "per_run", "green"), 1)

    def test_batch_stops_at_refusal(self):
        led = BudgetLedger([ResourceBudget("api_calls", 10, "per_run",
                                           "green")])
        out = led.batch([{"c": 4}, {"c": 4}, {"c": 4}],
                        lambda it: it["c"] * 2, "api_calls",
                        lambda it: it["c"])
        self.assertEqual(len(out["processed"]), 2)
        self.assertEqual(out["refused_at"], 2)

    def test_scope_separation_and_validation(self):
        led = BudgetLedger(default_budgets())
        led.consume("llm_tokens", 99_999, scope="yellow")
        self.assertEqual(
            led.consumed("llm_tokens", "per_run", "green"), 0)
        self.assertTrue(_rejects(
            lambda: ResourceBudget("llm_tokens", 10, "per_run", "red"),
            BudgetContractError))  # red paths never autonomous (D-050)
        self.assertTrue(_rejects(
            lambda: ResourceBudget("nonsense", 10, "per_run", "green"),
            BudgetContractError))
        self.assertTrue(_rejects(
            lambda: ResourceBudget("llm_tokens", 0, "per_run", "green"),
            BudgetContractError))


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
    """Live tier: verified-freeze compaction on the real store."""

    def setUp(self):
        import uuid
        self.run_id = uuid.uuid4().hex[:8]

    def _exec(self, sql, params):
        from canonical.notion_ingest import _exec
        return _exec(sql, params)

    def _txt(self, p):
        from canonical.compaction import _txt
        return _txt(p)

    def _insert_lock(self, platform, bucket, post_id, active):
        self._exec(
            "INSERT INTO scheduling.slot_lock (platform, slot_bucket, "
            "post_id, scheduled_for, active) VALUES (" + self._txt("p")
            + ", " + self._txt("b") + ", " + self._txt("i") + ", "
            + self._txt("s") + ", " + ("true" if active else "false")
            + ") ON CONFLICT (platform, slot_bucket) DO NOTHING",
            {"p": platform, "b": bucket, "i": post_id,
             "s": f"2026-09-18T12:{self.run_id[:2]}:00+00:00"})

    def test_compact_retireable_spares_active_removes_inactive(self):
        import uuid as _u
        rid = _u.uuid4().hex[:8]
        plat = f"p23-{rid}"
        self._insert_lock(plat, f"2026-09-18T13:{rid[:2]}:00",
                          f"{rid}-active", True)
        self._insert_lock(plat, f"2026-09-18T14:{rid[:2]}:00",
                          f"{rid}-inactive", False)
        from canonical.compaction import run_compact_retireable
        from canonical.security_engine import HardeningEngine
        from canonical.notion_ingest import PgEventStore
        eng = HardeningEngine(PgEventStore())
        summary = run_compact_retireable(eng, self._exec, "L9999")
        slot_m = [s for s in summary["surfaces"]
                  if s["surface"] == "scheduling.slot_lock"][0]
        self.assertTrue(slot_m["eligible"] >= 1)
        remaining = self._exec(
            "SELECT count(*) FROM scheduling.slot_lock WHERE platform = "
            + self._txt("p"), {"p": plat}).strip()
        self.assertEqual(remaining, "1")  # the ACTIVE lock survives
        state = self._exec(
            "SELECT active::text FROM scheduling.slot_lock WHERE "
            "platform = " + self._txt("p"), {"p": plat}).strip()
        self.assertEqual(state, "true")
        # manifest rows recorded
        kinds = [r.get("record_kind") for r in eng.records()]
        self.assertIn("compaction_manifest", kinds)

    def test_keyset_scan_over_live_history(self):
        page1 = keyset_scan_events(self._exec, batch=200)
        self.assertGreater(len(page1["rows"]), 0)
        page2 = keyset_scan_events(self._exec,
                                   page1["next_after_source"],
                                   page1["next_after_event"], batch=200)
        if page2["rows"]:
            last1 = (page1["rows"][-1]["source_system"],
                     page1["rows"][-1]["event_id"])
            first2 = (page2["rows"][0]["source_system"],
                      page2["rows"][0]["event_id"])
            self.assertLess(last1, first2)  # ordered + disjoint

    def test_chains_intact_after_compaction(self):
        # whole-chain attestation over the Phase 19 audit chain must
        # verify after compaction runs (compaction never touches chain
        # rows — battery-asserted)
        from canonical.admin_engine import default_vault
        rows_fn = default_vault().audit_rows
        att = ChainHeadAttestation(rows_fn)
        attested = att.compute("L0")
        self.assertTrue(att.verify(attested, "L0")["ok"])
        from canonical.compaction import run_compact_retireable
        from canonical.security_engine import HardeningEngine
        from canonical.notion_ingest import PgEventStore
        run_compact_retireable(HardeningEngine(PgEventStore()),
                               self._exec, "L9999")
        self.assertTrue(att.verify(attested, "L0")["ok"])  # unchanged


if __name__ == "__main__":
    unittest.main()

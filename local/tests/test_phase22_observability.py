"""Phase 22 — observability & health telemetry tests (D-121..D-124).

Layers:
  M1  engine.log.v1 ledger: deterministic trace/causal ids, record
      shape, D-114/D-124 boundary (redaction, PII, control chars,
      oversize marked trunc), JSONL append-only round-trip, trace
      propagation across sink re-instantiation (process-boundary
      analogue) (unit tier).
  M2  deterministic metrics: monotone counters, fixed histogram
      buckets, byte-identical exposition, declared-label/cardinality
      enforcement, Prometheus text-format compliance, D-124 label
      redaction, loopback-only exporter serving exactly the
      exposition (unit tier, real loopback sockets).
  M3  health probes: PASS/DEGRADED/FAIL semantics (degraded is
      explicit), threshold ordering guard, qa.health_report.v1
      shape + validation, worst-of aggregation (unit tier).
  M4  live-PG E2E: durable log vault (deterministic dedupe +
      trace-scoped counting), live pg_schema probe, ledger-integrity
      probe over the real Phase 19 chain, tamper detection via the
      attestation fold, and the operator CLI rendering a real
      qa.health_report.v1 (live tier; zero-skip when the stack is up).

Zero network beyond loopback (D-045/D-122); wall clock never enters
any id, key, or verdict.
"""

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

from canonical.obs_contracts import (  # noqa: E402
    SCHEMA_VERSION as LOG_SCHEMA,
    JsonlLogSink,
    LogLedger,
    ObservabilityContractError,
    PgLogVault,
    TraceContext,
    build_record,
    redact,
    root_trace,
    validate_record,
)
from canonical.obs_metrics import (  # noqa: E402
    MetricError,
    MetricsRegistry,
)
from services.metrics_exporter import LocalMetricsExporter  # noqa: E402
from canonical.obs_health import (  # noqa: E402
    HealthError,
    ProbeRegistry,
    ShippedProbes,
    probe_result,
    validate_report,
)
from canonical.security_engine import ChainHeadAttestation  # noqa: E402


def _rejects(fn, exc):
    try:
        fn()
        return False
    except exc:
        return True


class _Harness:
    """Temp-dir JSONL sink harness."""

    def __init__(self):
        self._td = tempfile.TemporaryDirectory()
        self.dir = self._td.name
        self.sink_path = os.path.join(self.dir, "engine.jsonl")

    def sink(self):
        return JsonlLogSink(self.sink_path)

    def cleanup(self):
        self._td.cleanup()


class TestM1LogLedger(unittest.TestCase):
    def setUp(self):
        self.h = _Harness()

    def tearDown(self):
        self.h.cleanup()

    def test_record_shape_and_required_fields(self):
        ctx = TraceContext.root("hitl", "ticket:1", "L0001")
        rec = build_record(ctx, domain="hitl", event="ticket_created",
                           logical_at="L0001", entity_ref="ticket:1")
        v = validate_record(rec)
        for f in ("schema_version", "trace_id", "causal_chain_id",
                  "logical_at", "domain", "event", "level", "status"):
            self.assertIn(f, v)
        self.assertEqual(v["schema_version"], LOG_SCHEMA)

    def test_trace_ids_deterministic_same_inputs(self):
        a = TraceContext.root("analytics", "rollup:d1", "T0019")
        b = TraceContext.root("analytics", "rollup:d1", "T0019")
        self.assertEqual(a.trace_id, b.trace_id)
        self.assertEqual(a.trace_id, root_trace("analytics", "rollup:d1",
                                                "T0019"))
        # different causal inputs → different ids
        c = TraceContext.root("analytics", "rollup:d2", "T0019")
        self.assertNotEqual(a.trace_id, c.trace_id)

    def test_causal_chain_children_chain_and_differ(self):
        root = TraceContext.root("dispatch", "job:9", "L0007")
        c1 = root.child("route")
        c2 = root.child("route")
        self.assertEqual(c1.causal_chain_id, c2.causal_chain_id)
        self.assertNotEqual(c1.causal_chain_id, root.causal_chain_id)
        c3 = c1.child("dispatch")
        self.assertEqual(c3.trace_id, root.trace_id)
        self.assertEqual(c3.seq, 2)
        self.assertNotEqual(c3.causal_chain_id, c1.causal_chain_id)

    def test_trace_propagation_across_sinks(self):
        # "across process boundaries": a SECOND ledger instance (fresh
        # sink handle over the same durable file) must observe the
        # same trace and a chained causal sequence.
        ctx = TraceContext.root("security", "gate:d114", "L0002")
        led1 = LogLedger(sink=self.h.sink())
        led1.emit(ctx, domain="security", event="payload_checked",
                  logical_at="L0002")
        child = ctx.child("payload_rejected")
        led2 = LogLedger(sink=self.h.sink())  # new "process"
        led2.emit(child, domain="security", event="payload_rejected",
                  logical_at="L0003", status="FAILURE")
        rows = self.h.sink().read_all()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["trace_id"], rows[1]["trace_id"])
        self.assertNotEqual(rows[0]["causal_chain_id"],
                            rows[1]["causal_chain_id"])
        self.assertEqual(rows[1]["causal_seq"], 1)
        self.assertEqual(rows[1]["status"], "FAILURE")

    def test_redaction_in_record_fields(self):
        ctx = TraceContext.root("admin", "audit:x", "L0001")
        rec = build_record(ctx, domain="admin", event="vault_read",
                           logical_at="L0001",
                           detail="conn postgres://u:p@h/db failed")
        self.assertNotIn("postgres://", rec["detail"])
        self.assertIn("[REDACTED]", rec["detail"])
        rec2 = build_record(ctx, domain="admin", event="vault_read",
                            logical_at="L0001",
                            payload={"note": "bearer abc123 sent"})
        self.assertEqual(rec2["payload"]["note"],
                         "[REDACTED] sent")

    def test_pii_payload_keys_redacted(self):
        ctx = TraceContext.root("oms", "order:o1", "L0001")
        rec = build_record(ctx, domain="oms", event="order_placed",
                           logical_at="L0001",
                           payload={"customer_email": "a@b.c",
                                    "items": 3})
        self.assertEqual(rec["payload"]["customer_email"], "[REDACTED]")
        self.assertEqual(rec["payload"]["items"], 3)

    def test_policy_errors_class_b(self):
        ctx = TraceContext.root("hitl", "t:1", "L0001")
        cases = [
            lambda: build_record(ctx, domain="nope", event="e",
                                 logical_at="L1"),
            lambda: build_record(ctx, domain="hitl", event="e",
                                 logical_at="L1", level="LOUD"),
            lambda: build_record(ctx, domain="hitl", event="e",
                                 logical_at="L1", status="MAYBE"),
            lambda: build_record(ctx, domain="hitl", event="e",
                                 logical_at=""),
            lambda: build_record(ctx, domain="hitl", event="e\x01",
                                 logical_at="L1"),
            lambda: build_record(ctx, domain="hitl", event="e",
                                 logical_at="L1",
                                 payload={"nested": {"b": 1}}),
            lambda: build_record(ctx, domain="hitl", event="e",
                                 logical_at="L1",
                                 payload={"bad": object()}),
        ]
        for c in cases:
            self.assertTrue(_rejects(c, ObservabilityContractError))
        # gate rejections surface under the SAME Class-B type
        self.assertTrue(_rejects(
            lambda: build_record(ctx, domain="hitl", event="e",
                                 logical_at="L1\x02"),
            ObservabilityContractError))

    def test_oversize_field_marked_trunc(self):
        ctx = TraceContext.root("hitl", "t:1", "L0001")
        rec = build_record(ctx, domain="hitl", event="e",
                           logical_at="L1",
                           detail="x" * 5000)
        self.assertLess(len(rec["detail"]), 600)
        self.assertTrue(rec["detail"].endswith("…[TRUNC]"))

    def test_jsonl_append_only_readback(self):
        led = LogLedger(sink=self.h.sink())
        ctx = TraceContext.root("scheduling", "post:p1", "L0001")
        led.emit(ctx, domain="scheduling", event="post_scheduled",
                 logical_at="L0001")
        led.emit(ctx.child("post_dispatched"),
                 domain="scheduling", event="post_dispatched",
                 logical_at="L0002")
        with open(self.h.sink_path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
        self.assertEqual(len(lines), 2)
        for l in lines:
            validate_record(json.loads(l))
        # append-only: rewrite attempt is a new file semantics concern,
        # but read_all must equal the exact emitted order
        self.assertEqual(self.h.sink().read_all()[0]["event"],
                         "post_scheduled")


class TestM2Metrics(unittest.TestCase):
    def test_counter_monotonicity(self):
        r = MetricsRegistry()
        r.declare_counter("engine_events_total", "ops events",
                          labels=("domain", "status"))
        self.assertEqual(r.incr("engine_events_total",
                                {"domain": "hitl", "status": "SUCCESS"}),
                         1)
        self.assertEqual(r.incr("engine_events_total",
                                {"domain": "hitl", "status": "SUCCESS"},
                                by=4), 5)
        for bad in (-1, 0):
            self.assertTrue(_rejects(
                lambda b=bad: r.incr("engine_events_total",
                                     {"domain": "hitl",
                                      "status": "SUCCESS"}, by=b),
                MetricError))
        self.assertEqual(r.incr("engine_events_total",
                                {"domain": "hitl", "status": "SUCCESS"}),
                         6)

    def test_gauge_and_histogram_deterministic_exposition(self):
        r = MetricsRegistry()
        r.declare_gauge("queue_depth", "d", labels=("queue",))
        r.declare_histogram("ledger_verify_latency_ms", "lat",
                            buckets=(1, 5, 10, 50))
        r.set_gauge("queue_depth", 12, {"queue": "hitl_review"})
        for v in (3, 42, 100, 3):
            r.observe("ledger_verify_latency_ms", v)
        e1, e2 = r.exposition(), r.exposition()
        self.assertEqual(e1, e2)  # byte-identical, no wall clock
        self.assertIn('# TYPE ledger_verify_latency_ms histogram', e1)
        self.assertIn('ledger_verify_latency_ms_bucket{le="5"} 2', e1)
        self.assertIn('ledger_verify_latency_ms_bucket{le="50"} 3', e1)
        self.assertIn('ledger_verify_latency_ms_bucket{le="+Inf"} 4', e1)
        self.assertIn('ledger_verify_latency_ms_count 4', e1)

    def test_declared_labels_and_cardinality_enforced(self):
        r = MetricsRegistry()
        r.declare_counter("c", "t", labels=("q",))
        self.assertTrue(_rejects(lambda: r.incr("c", {"nope": "x"}),
                                 MetricError))
        self.assertTrue(_rejects(lambda: r.incr("c", {}), MetricError))
        self.assertTrue(_rejects(lambda: r.incr("undeclared"),
                                 MetricError))

        def flood():
            for i in range(200):
                r.incr("c", {"q": f"v{i}"})
        self.assertTrue(_rejects(flood, MetricError))

    def test_exposition_format_prometheus(self):
        r = MetricsRegistry()
        r.declare_counter("engine_events_total", "ops events",
                          labels=("domain",))
        r.incr("engine_events_total", {"domain": "hitl"})
        e = r.exposition()
        self.assertIn("# HELP engine_events_total ops events", e)
        self.assertIn("# TYPE engine_events_total counter", e)
        self.assertIn('engine_events_total{domain="hitl"} 1', e)
        # deterministic across instances with identical updates
        r2 = MetricsRegistry()
        r2.declare_counter("engine_events_total", "ops events",
                           labels=("domain",))
        r2.incr("engine_events_total", {"domain": "hitl"})
        self.assertEqual(r.exposition(), r2.exposition())

    def test_metric_label_redaction_channel(self):
        r = MetricsRegistry()
        r.declare_counter("c1", "t", labels=("q",))
        r.incr("c1", {"q": "postgres://u:p@h/x"})
        e = r.exposition()
        self.assertNotIn("postgres://", e)
        self.assertIn("[REDACTED]", e)
        self.assertTrue(_rejects(
            lambda: r.incr("c1", {"q": "a\x01b"}), MetricError))

    def test_exporter_loopback_only(self):
        r = MetricsRegistry()
        r.declare_counter("engine_events_total", "ops events",
                          labels=("domain",))
        r.incr("engine_events_total", {"domain": "hitl"}, by=2)
        exp = LocalMetricsExporter(r)
        try:
            port = exp.start()
            self.assertGreater(port, 0)
            self.assertEqual(exp.bound_address[0], "127.0.0.1")
            # loopback scrape via the established local tooling channel
            body = subprocess.run(
                ["curl", "-s", f"http://127.0.0.1:{port}/metrics"],
                capture_output=True, text=True, timeout=10,
                check=True).stdout
            self.assertEqual(body, r.exposition())
            # non-metrics path → 404
            code = subprocess.run(
                ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                 f"http://127.0.0.1:{port}/nope"],
                capture_output=True, text=True, timeout=10,
                check=True).stdout
            self.assertEqual(code, "404")
        finally:
            exp.close()


class TestM3Health(unittest.TestCase):
    def test_probe_verdicts_pass_degraded_fail(self):
        p_ok = ShippedProbes.queue_depth(lambda: 5,
                                         warn_threshold=10,
                                         fail_threshold=50)()
        p_warn = ShippedProbes.queue_depth(lambda: 25,
                                           warn_threshold=10,
                                           fail_threshold=50)()
        p_fail = ShippedProbes.queue_depth(lambda: 99,
                                           warn_threshold=10,
                                           fail_threshold=50)()
        self.assertEqual((p_ok["verdict"], p_ok["ok"]),
                         ("PASS", True))
        self.assertEqual((p_warn["verdict"], p_warn["ok"]),
                         ("DEGRADED", True))
        self.assertEqual((p_fail["verdict"], p_fail["ok"]),
                         ("FAIL", False))

    def test_degraded_is_explicit_not_silent(self):
        reg = ProbeRegistry()
        reg.register(ShippedProbes.breaker_states(
            lambda: {"b1": "OPEN"}))
        rep = reg.run()
        self.assertEqual(rep["overall"], "DEGRADED")
        self.assertFalse(all(not p["ok"] for p in rep["probes"]))
        self.assertEqual(rep["probes"][0]["ok"], True)  # degraded = up

    def test_threshold_ordering_guard(self):
        self.assertTrue(_rejects(
            lambda: ShippedProbes.queue_depth(
                lambda: 1, warn_threshold=50, fail_threshold=10),
            HealthError))
        self.assertTrue(_rejects(
            lambda: ShippedProbes.queue_depth(
                lambda: 1, warn_threshold=0, fail_threshold=10),
            HealthError))

    def test_report_shape_and_validation(self):
        reg = ProbeRegistry()
        reg.register(ShippedProbes.queue_depth(
            lambda: 1, warn_threshold=10, fail_threshold=50))
        reg.register(ShippedProbes.breaker_states(lambda: {}))
        reg.register(ShippedProbes.ledger_integrity(
            lambda: {"ok": True}))
        rep = reg.run()
        v = validate_report(rep)
        self.assertEqual(v["schema_version"], "qa.health_report.v1")
        self.assertEqual(v["overall"], "PASS")
        names = [p["name"] for p in v["probes"]]
        self.assertEqual(names, sorted(names))
        # structural violations are Class-B
        bad = dict(rep)
        bad["schema_version"] = "nope"
        self.assertTrue(_rejects(lambda: validate_report(bad),
                                 HealthError))
        dup = {"schema_version": "qa.health_report.v1",
               "overall": "PASS",
               "probes": [probe_result("x", "PASS"),
                          probe_result("x", "PASS")]}
        self.assertTrue(_rejects(lambda: validate_report(dup),
                                 HealthError))

    def test_overall_worst_of(self):
        reg = ProbeRegistry()
        reg.register(ShippedProbes.queue_depth(
            lambda: 99, warn_threshold=10, fail_threshold=50))
        reg.register(ShippedProbes.ledger_integrity(
            lambda: {"ok": True}))
        self.assertEqual(reg.run()["overall"], "FAIL")


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
class TestM4LivePgE2E(unittest.TestCase):
    """Live tier: durable log vault, real probes, real CLI attestation.
    Zero-skip when the local stack is up (the operating baseline)."""

    def setUp(self):
        # run-scoped causal material: the events ledger is durable and
        # shared across runs — fixed trace/causal inputs would collide
        # with rows stored by earlier suite runs (D-027 dedupe is
        # exactly the behavior under test; ids must not pre-collide).
        self.run_id = uuid.uuid4().hex[:8]

    def test_log_vault_durable_write_and_dedupe(self):
        vault = PgLogVault()
        ctx = TraceContext.root("hitl", f"live:dedupe:{self.run_id}",
                                "L0099")
        rec = build_record(ctx, domain="hitl", event="ticket_created",
                           logical_at="L0099",
                           entity_ref=f"live:dedupe:{self.run_id}")
        first = vault.append(rec)
        self.assertEqual(first, "stored")
        second = vault.append(rec)  # identical re-emission
        self.assertEqual(second, "skipped_duplicate")
        # a distinct causal child under the same trace stores fine
        child = build_record(ctx.child("ticket_claimed"),
                             domain="hitl", event="ticket_claimed",
                             logical_at="L0100")
        self.assertEqual(vault.append(child), "stored")

    def test_log_vault_trace_scoped_count(self):
        vault = PgLogVault()
        ctx = TraceContext.root("security", f"live:scan:{id(self)}",
                                "L0101")
        for i in range(3):
            vault.append(build_record(ctx.child(f"step{i}"),
                                      domain="security",
                                      event=f"step{i}",
                                      logical_at=f"L01{i}"))
        n = vault.count(trace_id=ctx.trace_id)
        self.assertGreaterEqual(n, 3)

    def test_pg_schema_probe_live_pass(self):
        from canonical.notion_ingest import _exec
        res = ShippedProbes.pg_schema(_exec)()
        self.assertEqual(res["verdict"], "PASS", res["detail"])

    def test_ledger_probe_over_live_chain(self):
        from canonical.admin_engine import default_vault
        rows_fn = default_vault().audit_rows
        att = ChainHeadAttestation(rows_fn)
        attested = att.compute("L0")
        res = ShippedProbes.ledger_integrity(
            lambda: att.verify(attested, "L0"))()
        self.assertEqual(res["verdict"], "PASS", res["detail"])

    def test_ledger_tamper_detection_via_fold(self):
        # offline-proof of the probe's binary semantics: mutating ANY
        # interior row of an attested chain must flip verify to False.
        rows = [{"row_hash": f"h{i}", "body": f"b{i}"} for i in range(5)]
        att = ChainHeadAttestation(lambda: rows)
        attested = att.compute("L0")
        self.assertTrue(att.verify(attested, "L0")["ok"])
        tampered = [dict(r) for r in rows]
        tampered[2]["body"] = "TAMPERED"
        att2 = ChainHeadAttestation(lambda: tampered)
        self.assertFalse(att2.verify(attested, "L0")["ok"])

    def test_cli_renders_live_health_report(self):
        out = subprocess.run(
            [sys.executable, os.path.join(LOCAL, "canonical",
                                          "obs_health.py"), "json"],
            capture_output=True, text=True, timeout=120, cwd=str(ROOT))
        self.assertEqual(out.returncode, 0, out.stderr[-400:])
        report = json.loads(out.stdout)
        v = validate_report(report)
        self.assertIn(v["overall"], ("PASS", "DEGRADED"))
        pg = [p for p in v["probes"] if p["name"] == "pg_schema"][0]
        self.assertEqual(pg["verdict"], "PASS", pg["detail"])
        led = [p for p in v["probes"]
               if p["name"] == "ledger_integrity"][0]
        self.assertEqual(led["verdict"], "PASS", led["detail"])


if __name__ == "__main__":
    unittest.main()

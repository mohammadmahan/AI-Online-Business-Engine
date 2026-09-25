"""Stage G probe adapters & triple-evidence launch gate battery (D-151).

Exercises the PRODUCTION executors (`stage_g_probe_adapters.py`) and
the launch gate (`launch_attestation_verifier.py`) fully offline —
every subprocess seam is a deterministic fake, every artifact is
synthesized from the real D-149 manifest material:

  ADAPTER   — mock docker-inspect JSON / exec output parsed WITHOUT
              any shell invocation; payload shapes match D-150; the
              wired executors drive the FULL D-150 runner to
              PROBES_ACCEPTED against a fake healthy host.
  FAILCLOSE — nonzero exit, malformed JSON, invalid service names,
              timeouts and spawn failures fail closed with sanitized
              error types; payloads never leak.
  TRIAD     — the gate passes only when bundle hash, acceptance
              fingerprint and probe digest are valid, correlated and
              D-112-rooted with a chained verdict history; fails
              closed on absence, tamper, divergence, unrooted
              evidence, or a broken chain.
  HEALTH    — `wire_into_registry` makes the triad a mandatory
              `qa.health_report.v1` probe (FAIL pulls overall down).
  REDACT    — canaries never reach any adapter/gate surface.
  AST       — zero `shell=True`/`os.system`/`popen`/`Popen`; exactly
              one spawning seam; `timeout=` on every subprocess.run;
              zero I/O imports in the gate's import surface.
"""
from __future__ import annotations

import ast
import json
import pathlib
import subprocess
import sys
import unittest

REPO = pathlib.Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "local" / "scripts"
SRC = REPO / "local" / "src"
for p in (str(SCRIPTS), str(SRC), str(SRC.parent)):
    if p not in sys.path:
        sys.path.insert(0, p)

from run_stage_g_acceptance import StageGAcceptanceRunner  # noqa: E402
from stage_g_preflight_validator import bundle_hash_of  # noqa: E402
from stage_g_probe_adapters import (  # noqa: E402
    EXEC_TIMEOUT_S, LOG_SLICE_BYTES, AdapterError, ContainerExecExecutor,
    DockerInspectExecutor, LogStreamScrubberExecutor, build_executors,
)
from verify_stage_g_live_probes import (  # noqa: E402
    PROBES_ACCEPTED, StageGLiveProbeRunner,
)

ENGINE = SCRIPTS / "stage_g_probe_adapters.py"
VERIFIER = SRC / "security" / "launch_attestation_verifier.py"
DOC = (REPO / "docs" / "deployment" /
       "stage-g-probe-adapters.md").read_text(encoding="utf-8")

CANARY = "sk-canaryvalue1234567890abcdef"
SERVICES = ("postgres-ssot", "redis", "app-orchestrator",
            "telemetry-circuit")

# --- real Stage D manifest fingerprint (D-149 entry material) ---------
sys.path.insert(0, str(REPO / "local" / "src" / "security"))
sys.path.insert(0, str(REPO / "local" / "src" / "security"))
from src.security.launch_attestation_verifier import (  # noqa: E402
    LAUNCH_BLOCKED, LAUNCH_READY, TripleEvidenceGate, TriadError,
    canonical_hash, wire_into_registry,
)
from src.security.owner_approval_gate import (  # noqa: E402
    parse_envelope_fingerprint,
)

FP = parse_envelope_fingerprint((REPO / "local" / "infra" / "dokploy" /
                                 "stage_d_fingerprint.envelope")
                                .read_text(encoding="utf-8"))

MANIFEST = (REPO / "local" / "infra" / "dokploy" /
            "docker-compose.dokploy.yaml").read_text(encoding="utf-8")
TEMPLATE = (REPO / "local" / "infra" / "dokploy" /
            "dokploy_compose_template.yaml").read_text(encoding="utf-8")


def real_acceptance() -> dict:
    acc = StageGAcceptanceRunner(
        clock=lambda: 200, audit_sink=lambda d: None,
        preflight_verdict=lambda: {"verdict": "PREFLIGHT_CLEARED",
                                   "bundle_sha256": ""},
        manifest_provider=lambda: MANIFEST,
        template_provider=lambda: TEMPLATE).run()
    d = acc.to_dict()
    d["acceptance_fingerprint"] = acc.acceptance_fingerprint
    return d


def real_bundle() -> dict:
    bundle = {
        "schema": "cutover.bundle.v1",
        "verdict": "READY_FOR_CUTOVER",
        "candidate_manifest_sha256": FP,
        "session_id": "cutover-session-01",
        "target_env": "staging",
        "observed_tick": 100,
        "steps": [{"step": "stage_c", "ok": True, "detail": "ok",
                   "findings": []}],
        "stage_f_token_id": "tok-01",
        "abort_reason": "",
    }
    bundle["bundle_hash"] = bundle_hash_of(bundle)
    return bundle


def real_probe_report() -> dict:
    """Run the REAL D-150 engine over a fake healthy host so the triad
    input is a genuine probe artifact (not a hand-written shape)."""
    acc = real_acceptance()

    def executors_factory():
        return build_executors(inspect_runner=fake_docker_host(),
                               exec_runner=fake_docker_host(),
                               log_runner=fake_docker_host())

    ex = executors_factory()
    runner = StageGLiveProbeRunner(clock=lambda: 300,
                                   audit_sink=lambda d: None, **ex)
    report = runner.run(acc, expected_manifest=FP)
    assert report.verdict == PROBES_ACCEPTED
    d = report.to_dict()
    d["probe_digest"] = report.probe_digest
    return d


# --- deterministic fake docker host (the ONLY subprocess stand-in) ----

_CALLS: list = []

_HEALTHY = {
    "State": {"Running": True, "RestartCount": 0,
              "Health": {"Status": "healthy"}},
    "NetworkSettings": {"Ports": {}},
}
_KNOWN_SERVICES = set(SERVICES)
_HEARTBEAT = json.dumps({"registered": True, "age": 3})


def _cp(code: int, out: str, err: str) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], code, stdout=out, stderr=err)


def fake_docker_host():
    def run(argv, timeout_s=EXEC_TIMEOUT_S, input_text=None):
        _CALLS.append(list(argv))
        assert timeout_s <= EXEC_TIMEOUT_S, "timeout must stay bounded"
        if argv[1] == "inspect":
            if argv[-1] not in _KNOWN_SERVICES:
                return _cp(1, "", f"Error: No such object: {argv[-1]}")
            return _cp(0, json.dumps(_HEALTHY), "")
        if argv[1] == "exec":
            inner = argv[4:]
            if inner[0] == "psql":
                return _cp(0, "1", "")
            if inner[0] == "redis-cli":
                if "PING" in inner:
                    return _cp(0, "PONG", "")
                return _cp(0, "maxmemory-policy\nnoeviction", "")
            if inner[0] == "wget":
                return _cp(0, _HEARTBEAT, "")
        if argv[1] == "logs":
            return _cp(0, "engine boot ok\n", "")
        return _cp(2, "", "unknown fake command")
    return run


class FailingRunner:
    """A runner seam that raises — timeout / spawn failure modes."""

    def __init__(self, exc: BaseException) -> None:
        self._exc = exc

    def __call__(self, argv, timeout_s=EXEC_TIMEOUT_S, input_text=None):
        raise self._exc


def bad_exit_runner(code=1, err="pg_isready: no response"):
    def run(argv, timeout_s=EXEC_TIMEOUT_S, input_text=None):
        return _cp(code, "", err)
    return run


def audit_rows_for(bundle, acceptance, probe):
    return [
        {"event_kind": "stage_g_preflight",
         "detail": {"bundle_hash": bundle["bundle_hash"]}},
        {"event_kind": "cutover_bundle_recorded",
         "detail": {"bundle_hash": bundle["bundle_hash"]}},
        {"event_kind": "stage_g_acceptance",
         "detail": {"acceptance_fingerprint":
                    acceptance["acceptance_fingerprint"]}},
        {"event_kind": "stage_g_live_probe",
         "detail": {"probe_digest": probe["probe_digest"]}},
    ]


class GateHarness:

    def __init__(self, bundle=None, acceptance=None, probe=None,
                 rows=None, chain=None):
        self.bundle = bundle if bundle is not None else real_bundle()
        self.acceptance = (acceptance if acceptance is not None
                           else real_acceptance())
        self.probe = probe if probe is not None else real_probe_report()
        self.rows = rows if rows is not None else audit_rows_for(
            self.bundle, self.acceptance, self.probe)
        self.chain = chain if chain is not None else \
            (lambda: {"ok": True, "rows": 4})

    def gate(self) -> TripleEvidenceGate:
        return TripleEvidenceGate(
            bundle=lambda: self.bundle,
            acceptance=lambda: self.acceptance,
            probe=lambda: self.probe,
            audit_rows=lambda: self.rows,
            chain_verifier=self.chain)


# ===================================================================
# ADAPTER — structured parsing without any shell
# ===================================================================

class TestAdapters(unittest.TestCase):

    def setUp(self):
        _CALLS.clear()

    def test_01_inspect_uses_structured_json_argv(self):
        ex = DockerInspectExecutor(runner=fake_docker_host())
        ex.container_status(("postgres-ssot",))
        # every call is a token list built from fixed slots + the
        # validated service name — no shell string anywhere
        self.assertEqual(len(_CALLS), 1)
        self.assertEqual(_CALLS[0][:3], ["docker", "inspect", "--format"])
        self.assertEqual(_CALLS[0][3], "{{json .}}")
        self.assertEqual(_CALLS[0][4], "postgres-ssot")

    def test_02_container_status_shape_from_mock_json(self):
        ex = DockerInspectExecutor(runner=fake_docker_host())
        out = ex.container_status(SERVICES)
        self.assertEqual(set(out), set(SERVICES))
        for st in out.values():
            self.assertTrue(st["healthy"])
            self.assertEqual(st["restarts"], 0)

    def test_03_published_ports_extracts_host_bindings(self):
        def run(argv, timeout_s=EXEC_TIMEOUT_S, input_text=None):
            info = {"State": {"Running": True, "RestartCount": 0},
                    "NetworkSettings": {"Ports": {
                        "5432/tcp": [{"HostIp": "0.0.0.0",
                                      "HostPort": "55432"}]}}}
            return _cp(0, json.dumps(info), "")
        ex = DockerInspectExecutor(runner=run)
        out = ex.published_ports(("postgres-ssot",))
        self.assertEqual(out["postgres-ssot"],
                         ["0.0.0.0:55432:5432/tcp"])

    def test_04_wired_executors_drive_the_full_d150_runner(self):
        ex = build_executors(inspect_runner=fake_docker_host(),
                             exec_runner=fake_docker_host(),
                             log_runner=fake_docker_host())
        self.assertEqual(set(ex), {
            "container_status", "published_ports", "pg_roundtrip",
            "redis_ping", "app_loopback", "worker_heartbeat",
            "output_streams"})
        runner = StageGLiveProbeRunner(clock=lambda: 300,
                                       audit_sink=lambda d: None, **ex)
        r = runner.run(real_acceptance(), expected_manifest=FP)
        self.assertEqual(r.verdict, PROBES_ACCEPTED)
        # every exec seam kept its bounded timeout
        self.assertTrue(all(len(c) >= 2 for c in _CALLS))


# ===================================================================
# FAILCLOSE — sanitized error types, no payload leaks
# ===================================================================

class TestFailClosed(unittest.TestCase):

    def test_05_nonzero_inspect_exit_fails_closed_sanitized(self):
        ex = DockerInspectExecutor(
            runner=bad_exit_runner(err="Cannot connect to the docker "
                                       "daemon at unix:///var/run.sock"))
        with self.assertRaises(AdapterError) as ctx:
            ex.container_status(("postgres-ssot",))
        self.assertEqual(ctx.exception.kind, "inspect_failed")
        self.assertIn("inspect_failed", str(ctx.exception))

    def test_06_malformed_inspect_json_fails_closed(self):
        ex = DockerInspectExecutor(
            runner=bad_exit_runner(code=0, err="not json at all {"))
        with self.assertRaises(AdapterError) as ctx:
            ex.container_status(("redis",))
        self.assertEqual(ctx.exception.kind, "inspect_payload_malformed")

    def test_07_invalid_service_name_is_refused_before_exec(self):
        _CALLS.clear()
        ex = DockerInspectExecutor(runner=fake_docker_host())
        for bad in ("postgres-ssot; rm -rf /", "", "a" * 200,
                    "svc with spaces"):
            with self.assertRaises(AdapterError):
                ex.container_status((bad,))
        self.assertEqual(_CALLS, [])  # nothing was ever spawned

    def test_08_timeout_fails_closed(self):
        ex = DockerInspectExecutor(
            runner=FailingRunner(subprocess.TimeoutExpired([], 15)))
        with self.assertRaises(AdapterError) as ctx:
            ex.container_status(("redis",))
        self.assertEqual(ctx.exception.kind, "timeout")

    def test_09_spawn_failure_surfaces_type_only(self):
        ex = ContainerExecExecutor(runner=FailingRunner(OSError("no bin")))
        with self.assertRaises(AdapterError) as ctx:
            ex.pg_roundtrip()
        self.assertEqual(ctx.exception.kind, "spawn_failure")
        self.assertNotIn("no bin", str(ctx.exception))

    def test_10_pg_failure_sanitized_no_payload_leak(self):
        # spaced "= " keeps the secret-shaped shape for _SECRET_SHAPED
        # while staying below the Phase 20 entropy token threshold
        secret = "PGPASSWORD = hunter22222222 psql: FATAL"
        ex = ContainerExecExecutor(
            runner=bad_exit_runner(err=secret))
        with self.assertRaises(AdapterError) as ctx:
            ex.pg_roundtrip()
        self.assertEqual(ctx.exception.kind, "pg_roundtrip_failed")
        self.assertNotIn("hunter22222222", str(ctx.exception))
        self.assertNotIn("PGPASSWORD", str(ctx.exception))


# ===================================================================
# TRIAD — pass when valid + correlated; fail closed otherwise
# ===================================================================

class TestTripleEvidence(unittest.TestCase):

    def test_11_full_triad_passes(self):
        v = GateHarness().gate().evaluate()
        self.assertEqual(v.verdict, LAUNCH_READY)
        self.assertTrue(v.launch_ready)
        self.assertEqual([c[0] for c in v.checks],
                         ["TRIAD-01", "TRIAD-01", "TRIAD-01",
                          "TRIAD-02", "TRIAD-02",
                          "TRIAD-03", "TRIAD-03", "TRIAD-03", "TRIAD-03",
                          "TRIAD-04"])
        self.assertTrue(all(c[1] for c in v.checks))

    def test_12_provider_failure_raises_triad_error(self):
        """A provider that cannot deliver its artifact aborts the
        evaluation (fail closed) — never a silent empty pass."""
        def broken():
            raise RuntimeError("storage unavailable")
        base = GateHarness()
        gate = TripleEvidenceGate(
            bundle=lambda: base.bundle,
            acceptance=lambda: base.acceptance,
            probe=broken, audit_rows=lambda: base.rows,
            chain_verifier=lambda: {"ok": True, "rows": 4})
        with self.assertRaises(TriadError):
            gate.evaluate()

    def test_13_malformed_artifact_fails_closed(self):
        for name in ("bundle", "acceptance", "probe"):
            h = GateHarness()
            setattr(h, name, "not-a-dict")
            v = h.gate().evaluate()
            self.assertEqual(v.verdict, LAUNCH_BLOCKED, name)
            self.assertIn("missing or malformed", v.checks[0][2])

    def test_14_tampered_bundle_hash_fails(self):
        h = GateHarness()
        h.bundle["verdict"] = "BLOCKED"  # tamper AFTER hash recorded
        v = h.gate().evaluate()
        self.assertEqual(v.verdict, LAUNCH_BLOCKED)
        self.assertIn("TAMPERED", v.checks[0][2])

    def test_15_manifest_fingerprint_divergence_fails(self):
        h = GateHarness()
        h.probe["manifest_sha256"] = "b" * 64
        v = h.gate().evaluate()
        self.assertEqual(v.verdict, LAUNCH_BLOCKED)
        self.assertTrue(any("DIFFERENT deployments" in c[2]
                            for c in v.checks))

    def test_16_digest_absent_from_audit_chain_fails(self):
        h = GateHarness(rows=[])
        v = h.gate().evaluate()
        self.assertEqual(v.verdict, LAUNCH_BLOCKED)
        rooted = [c for c in v.checks
                  if c[0] == "TRIAD-03" and "rooted" in c[2]]
        self.assertEqual(len(rooted), 0)
        self.assertTrue(any("not durably attested" in c[2]
                            for c in v.checks))

    def test_17_broken_chain_fails(self):
        h = GateHarness(
            chain=lambda: {"ok": False, "broken_at_seq": 7,
                           "reason": "chain_mismatch"})
        v = h.gate().evaluate()
        self.assertEqual(v.verdict, LAUNCH_BLOCKED)
        self.assertTrue(any("broken chain attests nothing" in c[2]
                            for c in v.checks))

    def test_18_tampered_probe_digest_fails(self):
        h = GateHarness()
        h.probe["probes"][0][1] = False  # flip after digest recorded
        v = h.gate().evaluate()
        self.assertEqual(v.verdict, LAUNCH_BLOCKED)
        self.assertTrue(any("TAMPERED probe" in c[2] for c in v.checks))

    def test_19_rejected_probe_verdict_fails(self):
        h = GateHarness()
        h.probe["verdict"] = "PROBES_REJECTED"
        v = h.gate().evaluate()
        self.assertEqual(v.verdict, LAUNCH_BLOCKED)
        self.assertTrue(any("never cleared" in c[2] for c in v.checks))

    def test_20_every_check_runs_so_one_verdict_names_all_blockers(self):
        h = GateHarness(rows=[], chain=lambda: {"ok": False,
                                                "reason": "chain_mismatch"})
        h.bundle["verdict"] = "BLOCKED"
        v = h.gate().evaluate()
        self.assertEqual(v.verdict, LAUNCH_BLOCKED)
        kinds = {c[0] for c in v.checks}
        self.assertEqual(kinds, {"TRIAD-01", "TRIAD-02", "TRIAD-03",
                                 "TRIAD-04"})


# ===================================================================
# HEALTH — mandatory probe wiring into qa.health_report.v1
# ===================================================================

class TestHealthReportWiring(unittest.TestCase):

    def test_21_passing_triad_is_a_pass_probe(self):
        from canonical.obs_health import ProbeRegistry, validate_report
        reg = ProbeRegistry()
        wire_into_registry(reg, GateHarness().gate())
        rep = validate_report(reg.run())
        probe = next(p for p in rep["probes"]
                     if p["name"] == "stage_g_triple_evidence")
        self.assertEqual(probe["verdict"], "PASS")

    def test_22_blocked_triad_fails_the_whole_report(self):
        from canonical.obs_health import ProbeRegistry, validate_report
        reg = ProbeRegistry()
        wire_into_registry(reg, GateHarness(rows=[]).gate())
        rep = validate_report(reg.run())
        probe = next(p for p in rep["probes"]
                     if p["name"] == "stage_g_triple_evidence")
        self.assertEqual(probe["verdict"], "FAIL")
        self.assertEqual(rep["overall"], "FAIL")
        self.assertIn("triad incomplete", probe["detail"])

    def test_23_gate_exception_is_a_fail_never_a_crash(self):
        from canonical.obs_health import ProbeRegistry, validate_report
        reg = ProbeRegistry()
        gate = TripleEvidenceGate(
            bundle=lambda: (_ for _ in ()).throw(RuntimeError("boom")),
            acceptance=lambda: {}, probe=lambda: {},
            audit_rows=lambda: [], chain_verifier=lambda: {})
        wire_into_registry(reg, gate)
        rep = validate_report(reg.run())
        probe = next(p for p in rep["probes"]
                     if p["name"] == "stage_g_triple_evidence")
        self.assertEqual(probe["verdict"], "FAIL")
        self.assertIn("triad evaluation error: TriadError",
                      probe["detail"])


# ===================================================================
# REDACT — canaries never escape any surface
# ===================================================================

class TestRedaction(unittest.TestCase):

    def test_24_no_canary_through_adapter_or_gate_surfaces(self):
        import io
        log_runner = bad_exit_runner(code=0,
                                     err=f"token={CANARY} leaked")
        le = LogStreamScrubberExecutor(runner=log_runner)
        streams = le.output_streams()
        self.assertNotIn(CANARY, json.dumps(streams))
        self.assertIn("[REDACTED]", json.dumps(streams))
        # the gate's rendered checks stay clean too
        v = GateHarness().gate().evaluate()
        self.assertNotIn(CANARY, json.dumps(v.to_dict()))
        self.assertNotIn("hunter22222222", json.dumps(v.to_dict()))

    def test_25_adapter_error_text_is_redacted_and_bounded(self):
        ex = DockerInspectExecutor(
            runner=bad_exit_runner(err=f"boom {CANARY} " + "x" * 500))
        try:
            ex.container_status(("postgres-ssot",))
            self.fail("expected AdapterError")
        except AdapterError as exc:
            msg = str(exc)
            self.assertNotIn(CANARY, msg)
            self.assertLessEqual(len(msg), 260)


# ===================================================================
# AST — argv discipline, single seam, bounded timeouts, pure gate
# ===================================================================

class TestAst(unittest.TestCase):

    def test_26_zero_shell_and_process_apis_in_adapters(self):
        tree = ast.parse(ENGINE.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and node.arg == "shell":
                self.fail("shell= keyword present in adapters")
            if isinstance(node, ast.Call):
                fn = node.func
                if isinstance(fn, ast.Attribute) and \
                        fn.attr in ("system", "popen", "Popen"):
                    self.fail(f"banned process call: .{fn.attr}()")

    def test_27_exactly_one_spawning_seam_always_bounded(self):
        tree = ast.parse(ENGINE.read_text(encoding="utf-8"))
        run_calls = 0
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = node.func
                if isinstance(fn, ast.Attribute) and \
                        fn.attr == "run" and \
                        isinstance(fn.value, ast.Name) and \
                        fn.value.id == "subprocess":
                    run_calls += 1
                    kws = {k.arg for k in node.keywords}
                    self.assertIn("timeout", kws,
                                  "subprocess.run without timeout")
        self.assertEqual(run_calls, 1, "spawning must stay in one seam")

    def test_28_verifier_import_surface_is_pure(self):
        tree = ast.parse(VERIFIER.read_text(encoding="utf-8"))
        banned = {"socket", "subprocess", "ssl", "http", "urllib",
                  "requests", "ftplib", "os", "pathlib"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    self.assertNotIn(a.name.split(".")[0], banned,
                                     f"banned import: {a.name}")
            elif isinstance(node, ast.ImportFrom):
                root = (node.module or "").split(".")[0]
                self.assertNotIn(root, banned,
                                 f"banned import-from: {node.module}")

    def test_29_doc_covers_adapters_and_triad(self):
        for token in ("DockerInspectExecutor", "ContainerExecExecutor",
                      "LogStreamScrubberExecutor", "TRIAD-01", "TRIAD-02",
                      "TRIAD-03", "TRIAD-04", "probe_digest",
                      "acceptance_fingerprint", "bundle_hash",
                      "EXEC_TIMEOUT_S", "qa.health_report.v1", "D-112",
                      "D-139", "shell=True"):
            self.assertIn(token, DOC)


if __name__ == "__main__":
    unittest.main()

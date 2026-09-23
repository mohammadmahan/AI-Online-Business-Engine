"""Dokploy bridge — fail-closed infrastructure health probe.

Programmatic deployment gate for the D-141 Stage H orchestration:
verifies PostgreSQL SSOT connectivity, Redis broker responsiveness,
worker heartbeat, and the telemetry circuit state BEFORE a deployment
may be marked successful, then renders the canonical
`qa.health_report.v1` attestation.

Discipline:
  - Injected-only: every check receives its verifier callable
    (`pg_exec`, `redis_ping`, `worker_heartbeat`, `telemetry_state`);
    nothing here opens sockets, spawns processes, or reads clocks.
  - Fail-closed: any FAIL halts the deployment verdict — `overall`
    is DEGRADED at best when any probe is not PASS, and `deploy_ok`
    is False unless every probe passed. Missing probes are FAILs.
  - Zero leak: diagnostics carry exception TYPE NAMES only —
    connection strings, hosts, passwords and tokens never enter
    the report (D-124); every rendered detail additionally passes
    `deep_redact`.
  - Canonical surface: output composes `obs_health.ProbeRegistry`
    (D-121/D-123) so the report shape stays `qa.health_report.v1`.
"""
from __future__ import annotations

from typing import Callable, Dict, Optional

from canonical.obs_health import ProbeRegistry, probe_result

try:  # package-relative (battery) or script (cwd=local)
    from local.src.memory.vector_store import deep_redact  # type: ignore
except ImportError:  # pragma: no cover - script path
    from src.memory.vector_store import deep_redact  # type: ignore

__all__ = ["InfraHealthProbe", "DEPLOY_OK", "DEPLOY_HALTED"]

DEPLOY_OK = "DEPLOY_OK"
DEPLOY_HALTED = "DEPLOY_HALTED"


def _type_of(exc: BaseException) -> str:
    return type(exc).__name__


class InfraHealthProbe:
    """Compose the four deployment-gate probes and render the report.

    All verifiers are injected callables; any may be None, which the
    registry treats as an absent control — a FAIL for that service
    (fail-closed: an unverified service cannot pass a deployment).
    """

    def __init__(self,
                 pg_exec: Optional[Callable[[str], str]] = None,
                 redis_ping: Optional[Callable[[], object]] = None,
                 worker_heartbeat: Optional[Callable[[], object]] = None,
                 telemetry_state: Optional[Callable[[], object]] = None):
        self._pg_exec = pg_exec
        self._redis_ping = redis_ping
        self._worker_heartbeat = worker_heartbeat
        self._telemetry_state = telemetry_state

    # -- probes ---------------------------------------------------------------

    def _probe(self, name, fn, ok_check, fail_detail):
        if fn is None:
            return probe_result(name, "FAIL",
                                f"probe not wired — fail closed ({fail_detail})",
                                checked_at_logical="")
        try:
            out = fn()
        except Exception as e:  # noqa: BLE001 — probe boundary
            return probe_result(name, "FAIL",
                                deep_redact(f"unreachable: {_type_of(e)}"),
                                checked_at_logical="")
        try:
            ok, detail = ok_check(out)
        except Exception as e:  # noqa: BLE001
            return probe_result(name, "FAIL",
                                deep_redact(f"bad verifier: {_type_of(e)}"),
                                checked_at_logical="")
        verdict = "PASS" if ok else "FAIL"
        return probe_result(name, verdict, deep_redact(detail),
                            checked_at_logical="")

    @staticmethod
    def _pg_ok(out) -> "tuple[bool, str]":
        text = str(out).strip().lower()
        if text == "1":
            return True, "SSOT answers"
        return False, f"unexpected SSOT response ({text[:8]})"

    @staticmethod
    def _redis_ok(out) -> "tuple[bool, str]":
        if out is True or (isinstance(out, str)
                           and out.strip().lower() == "pong"):
            return True, "broker answers"
        return False, "broker did not answer PONG"

    @staticmethod
    def _worker_ok(out) -> "tuple[bool, str]":
        age = getattr(out, "ticks_since_beat", None)
        if age is None and isinstance(out, dict):
            age = out.get("ticks_since_beat")
        if not isinstance(age, int):
            return False, "heartbeat payload malformed"
        if age < 0:
            return False, "heartbeat age negative"
        if age > 5:
            return False, f"heartbeat stale (ticks_since_beat={age})"
        return True, f"heartbeat fresh (ticks_since_beat={age})"

    @staticmethod
    def _telemetry_ok(out) -> "tuple[bool, str]":
        latched = getattr(out, "latched_open", None)
        if latched is None and isinstance(out, dict):
            latched = out.get("latched_open")
        if latched is True:
            return False, "telemetry circuit latched OPEN"
        if latched is False:
            return True, "telemetry circuit healthy"
        return False, "telemetry state unreadable"

    # -- registry assembly ------------------------------------------------------

    def _registry(self) -> ProbeRegistry:
        reg = ProbeRegistry()
        # pg probe carries its own SQL (the verifier takes a statement)
        reg.register(lambda: self._probe(
            "pg_ssot", lambda: self._pg_exec("SELECT 1"),
            self._pg_ok, "SSOT"))
        reg.register(lambda: self._probe(
            "redis_broker", self._redis_ping, self._redis_ok, "broker"))
        reg.register(lambda: self._probe(
            "worker_heartbeat", self._worker_heartbeat, self._worker_ok,
            "worker"))
        reg.register(lambda: self._probe(
            "telemetry_circuit", self._telemetry_state, self._telemetry_ok,
            "telemetry"))
        return reg

    # -- verdicts -----------------------------------------------------------------

    def report(self) -> Dict:
        """`qa.health_report.v1` — deterministic, sorted probes."""
        return self._registry().run()

    def deploy_verdict(self) -> Dict:
        """The Stage H gate: DEPLOY_OK only when EVERY probe passed;
        any FAIL/DEGRADED/absent probe halts the deployment."""
        rep = self.report()
        all_pass = all(p["verdict"] == "PASS" for p in rep["probes"])
        return {
            "verdict": DEPLOY_OK if all_pass else DEPLOY_HALTED,
            "overall": rep["overall"],
            "probes": rep["probes"],
            "schema_version": rep["schema_version"],
        }

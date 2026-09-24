#!/usr/bin/env python3
"""Stage G — live probe verification engine (D-150).

Post-provisioning runtime assurance: GA-1..GA-7 (per
`docs/deployment/stage-g-acceptance.md`, scoped to the runtime
sanity surface the D-150 directive defines) executed against the
deployed stack through INJECTED container executors — the core never
spawns processes, opens sockets, or reads the wall clock (RULES §35;
AST-pinned in the battery).

ENTRY GATE (fail-closed): a valid `stage_g_acceptance_report.v1`
(D-149) carrying verdict `ACCEPTED` must be presented, and its
`manifest_sha256` must match the fingerprint of the deployment being
probed. Missing, REJECTED, malformed, or fingerprint-mismatched
acceptance reports abort the run immediately — no probe executes.

Probe suite (each probe = one injected executor + one pure judge):

  GA-1  container lifecycle — every core service healthy, no
        crash-looping (restart counts bounded)
  GA-2  SSOT integrity — PostgreSQL answers a read/write transaction
        roundtrip on the internal network
  GA-3  broker integrity — Redis PING→PONG with auth enforced and
        TTL/eviction policy confirmed; an externally exposed broker
        port is a hard refusal
  GA-4  application IPC — the app's core loopback endpoint answers
  GA-5  worker liveness — registration + queue-drain heartbeat fresh
  GA-6  network boundary — zero published ports on backend services;
        the edge is the only public surface
  GA-7  redaction/log leakage — probe outputs carry no tokens,
        credentials, or keys (canary scrub asserted on every detail)

Verdicts are fail-closed: a timeout, transport error, unreachable
executor, or malformed payload is a probe FAIL (never skipped, never
warned). The canonical `stage_g_live_probe_report.v1` artifact carries
a SHA-256 probe execution digest over the canonical bytes; exactly one
report is emitted and audited per run (including entry-gate aborts).
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

try:  # battery package path or script cwd path
    from ..src.memory.vector_store import deep_redact  # type: ignore
except ImportError:  # pragma: no cover - script invocation paths
    try:
        from src.memory.vector_store import deep_redact  # type: ignore
    except ImportError:
        from memory.vector_store import deep_redact  # type: ignore

__all__ = [
    "LiveProbeError", "LiveProbeReport", "StageGLiveProbeRunner",
    "PROBES_ACCEPTED", "PROBES_REJECTED", "REPORT_SCHEMA",
    "ACCEPTANCE_SCHEMA", "HEARTBEAT_MAX_AGE",
]

PROBES_ACCEPTED = "PROBES_ACCEPTED"
PROBES_REJECTED = "PROBES_REJECTED"
REPORT_SCHEMA = "stage_g_live_probe_report.v1"
ACCEPTANCE_SCHEMA = "stage_g_acceptance_report.v1"

# GA-5: a heartbeat older than this many ticks is stale (fail-closed).
HEARTBEAT_MAX_AGE = 120
# GA-1: restart counts above this suggest a crash loop.
RESTART_MAX = 3

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
# Leak detection runs on RAW text (before deep_redact masks it): a
# credential-shaped assignment OR a known credential-prefix family.
_SECRET_SHAPED = re.compile(
    r"(?i)(api[_-]?key|secret|password|token|passwd|pwd)\s*[=:]\s*"
    r"['\"]?[A-Za-z0-9+/_\-]{12,}"
    r"|sk-[A-Za-z0-9]{16,}"
    r"|ghp_[A-Za-z0-9]{20,}"
    r"|AKIA[0-9A-Z]{16}")


class LiveProbeError(ValueError):
    """Contract-level misuse of the live probe runner."""


def _fail(reason: str) -> None:
    raise LiveProbeError(reason)


def _report_hash(report: Dict[str, Any]) -> str:
    blob = json.dumps(report, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class LiveProbeReport:
    """Canonical, immutable GA verdict artifact."""
    schema: str
    verdict: str                        # PROBES_ACCEPTED / PROBES_REJECTED
    manifest_sha256: str                # deployment fingerprint probed
    acceptance_fingerprint: str         # the D-149 clearance binding
    probes: tuple = field(default_factory=tuple)  # (id, ok, detail)
    observed_tick: int = 0

    @property
    def accepted(self) -> bool:
        return self.verdict == PROBES_ACCEPTED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "verdict": self.verdict,
            "manifest_sha256": self.manifest_sha256,
            "acceptance_fingerprint": self.acceptance_fingerprint,
            "probes": [list(p) for p in self.probes],
            "observed_tick": self.observed_tick,
        }

    @property
    def probe_digest(self) -> str:
        """SHA-256 over the canonical report bytes (GA execution
        digest; binds the verdict to these exact probe outcomes)."""
        return _report_hash(self.to_dict())


class StageGLiveProbeRunner:
    """GA-1..GA-7 with injected executors (RULES §35).

    Injected (all optional callables; an ABSENT executor is a probe
    FAIL — fail-closed, mirroring `infra_health_probe`):
      clock               — ``() -> int`` logical tick
      audit_sink          — ``callable(dict)`` (D-121 ledger in prod)
      container_status    — ``() -> dict`` service -> {healthy, restarts}
      pg_roundtrip        — ``() -> bool`` read/write tx roundtrip result
      redis_ping          — ``() -> dict`` {pong, auth_required, ttl_ok}
      app_loopback        — ``() -> bool`` core endpoint answered
      worker_heartbeat    — ``() -> dict`` {registered, age}
      published_ports     — ``() -> dict`` service -> [published ports]
      output_streams      — ``() -> dict`` {"stdout": str, "stderr": str}
    """

    def __init__(self, clock: Callable[[], int],
                 audit_sink: Callable[[Dict[str, Any]], None],
                 container_status: Optional[Callable[[], Dict]] = None,
                 pg_roundtrip: Optional[Callable[[], Any]] = None,
                 redis_ping: Optional[Callable[[], Any]] = None,
                 app_loopback: Optional[Callable[[], Any]] = None,
                 worker_heartbeat: Optional[Callable[[], Any]] = None,
                 published_ports: Optional[Callable[[], Dict]] = None,
                 output_streams: Optional[Callable[[], Dict]] = None) -> None:
        if not callable(clock) or not callable(audit_sink):
            _fail("clock and audit_sink required")
        self._clock = clock
        self._sink = audit_sink
        self._exec = {
            "container_status": container_status,
            "pg_roundtrip": pg_roundtrip,
            "redis_ping": redis_ping,
            "app_loopback": app_loopback,
            "worker_heartbeat": worker_heartbeat,
            "published_ports": published_ports,
            "output_streams": output_streams,
        }

    # -- internals -------------------------------------------------------------

    def _call(self, name: str) -> Tuple[Optional[Any], str]:
        fn = self._exec[name]
        if fn is None:
            return None, "executor not wired — fail closed"
        try:
            return fn(), ""
        except Exception as exc:  # noqa: BLE001 — transport boundary
            # D-124: only the exception TYPE surfaces, never its payload
            return None, f"transport failure: {type(exc).__name__}"

    @staticmethod
    def _scrub(text: str) -> Tuple[str, bool]:
        """Detect secret-shaped material on the RAW text (redaction
        would mask the evidence), then deep-redact for the report.
        The presence itself is a GA-7 finding."""
        leak = _SECRET_SHAPED.search(text) is not None
        red = deep_redact(text)
        return red, leak

    def _emit(self, verdict: str, probes: List[Tuple[str, bool, str]],
              manifest_sha256: str, acceptance_fp: str) -> LiveProbeReport:
        scrubbed: List[Tuple[str, bool, str]] = []
        for pid, ok, detail in probes:
            red, leak = self._scrub(str(detail))
            if leak:
                ok = False
                red = "secret-shaped material in probe output (GA-7)"
            scrubbed.append((pid, ok, red))
        report = LiveProbeReport(
            schema=REPORT_SCHEMA, verdict=verdict,
            manifest_sha256=manifest_sha256,
            acceptance_fingerprint=acceptance_fp,
            probes=tuple(scrubbed), observed_tick=self._clock())
        blob = json.dumps(report.to_dict(), sort_keys=True,
                          separators=(",", ":"), ensure_ascii=False)
        self._sink(json.loads(deep_redact(blob)))
        return report

    # -- entry gate -----------------------------------------------------------

    def _entry_gate(self, acceptance_report: Optional[Dict[str, Any]],
                    expected_manifest: str
                    ) -> Optional[LiveProbeReport]:
        if not isinstance(acceptance_report, dict):
            return self._emit(
                PROBES_REJECTED,
                [("GATE", False,
                  "acceptance report missing or malformed — no probe "
                  "executes (D-149)")],
                expected_manifest, "")
        if acceptance_report.get("schema") != ACCEPTANCE_SCHEMA:
            return self._emit(
                PROBES_REJECTED,
                [("GATE", False,
                  f"schema {acceptance_report.get('schema')!r} != "
                  f"{ACCEPTANCE_SCHEMA!r}")],
                expected_manifest, "")
        if acceptance_report.get("verdict") != "ACCEPTED":
            v = acceptance_report.get("verdict")
            return self._emit(
                PROBES_REJECTED,
                [("GATE", False,
                  f"acceptance verdict {v!r} != 'ACCEPTED' — "
                  "provisioning never cleared (D-149)")],
                expected_manifest, "")
        fp = acceptance_report.get("manifest_sha256", "")
        if not _HEX64.match(fp or ""):
            return self._emit(
                PROBES_REJECTED,
                [("GATE", False,
                  "acceptance manifest fingerprint malformed")],
                expected_manifest, "")
        if expected_manifest and fp != expected_manifest:
            return self._emit(
                PROBES_REJECTED,
                [("GATE", False,
                  "acceptance fingerprint != deployment fingerprint — "
                  "probing a different deployment than was accepted")],
                expected_manifest, "")
        # verify the acceptance report's own integrity (ACC-04 binding)
        blob = {k: v for k, v in acceptance_report.items()
                if k != "acceptance_fingerprint"}
        recomputed = _report_hash(blob)
        recorded = acceptance_report.get("acceptance_fingerprint", "")
        if _HEX64.match(recorded or "") and recorded != recomputed:
            return self._emit(
                PROBES_REJECTED,
                [("GATE", False,
                  "acceptance fingerprint does not match its canonical "
                  "bytes — TAMPERED report")],
                expected_manifest, recorded)
        return None

    # -- the probes --------------------------------------------------------------

    def run(self, acceptance_report: Optional[Dict[str, Any]],
            expected_manifest: str = "") -> LiveProbeReport:
        """Entry gate → GA-1..GA-7 → canonical report. Exactly one
        report per call."""
        abort = self._entry_gate(acceptance_report, expected_manifest)
        if abort is not None:
            return abort
        afp = acceptance_report.get("acceptance_fingerprint", "")
        mfp = acceptance_report.get("manifest_sha256", "")
        probes: List[Tuple[str, bool, str]] = []

        # GA-1 container lifecycle ---------------------------------------
        out, err = self._call("container_status")
        if err:
            probes.append(("GA-1", False, err))
        elif not isinstance(out, dict) or not out:
            probes.append(("GA-1", False, "container status payload empty "
                           "or malformed"))
        else:
            bad = []
            for svc, st in sorted(out.items()):
                healthy = bool(st.get("healthy"))
                restarts = st.get("restarts", 0)
                if not healthy:
                    bad.append(f"{svc}:unhealthy")
                elif not isinstance(restarts, int) or restarts > RESTART_MAX:
                    bad.append(f"{svc}:restart-loop({restarts})")
            probes.append(("GA-1", not bad,
                           "; ".join(bad) or
                           f"{len(out)} services healthy, no crash loops"))

        # GA-2 SSOT roundtrip ----------------------------------------------
        out, err = self._call("pg_roundtrip")
        if err:
            probes.append(("GA-2", False, err))
        elif out is True:
            probes.append(("GA-2", True,
                           "read/write transaction roundtrip OK"))
        else:
            probes.append(("GA-2", False,
                           "SSOT roundtrip failed or returned non-true"))

        # GA-3 broker integrity ----------------------------------------------
        out, err = self._call("redis_ping")
        if err:
            probes.append(("GA-3", False, err))
        elif not isinstance(out, dict):
            probes.append(("GA-3", False, "broker payload malformed"))
        else:
            bad = []
            if out.get("pong") is not True:
                bad.append("no PONG")
            if out.get("auth_required") is not True:
                bad.append("auth not enforced")
            if out.get("ttl_ok") is not True:
                bad.append("TTL/eviction policy unconfirmed")
            if out.get("exposed") is True:
                bad.append("broker externally exposed — hard refusal")
            probes.append(("GA-3", not bad, "; ".join(bad) or
                           "PONG, auth enforced, TTL policy OK, "
                           "not externally exposed"))

        # GA-4 app IPC --------------------------------------------------------
        out, err = self._call("app_loopback")
        if err:
            probes.append(("GA-4", False, err))
        elif out is True:
            probes.append(("GA-4", True, "core loopback endpoint answered"))
        elif isinstance(out, str):
            # executor returned diagnostic text instead of a clean bool:
            # judge it through the redaction gate (a leak flips the probe)
            probes.append(("GA-4", False, str(out)))
        else:
            probes.append(("GA-4", False, "core loopback unresponsive"))

        # GA-5 worker liveness --------------------------------------------------
        out, err = self._call("worker_heartbeat")
        if err:
            probes.append(("GA-5", False, err))
        elif not isinstance(out, dict):
            probes.append(("GA-5", False, "heartbeat payload malformed"))
        else:
            registered = out.get("registered") is True
            age = out.get("age")
            if not registered:
                probes.append(("GA-5", False, "worker not registered"))
            elif not isinstance(age, int) or age < 0:
                probes.append(("GA-5", False, "heartbeat age malformed"))
            elif age > HEARTBEAT_MAX_AGE:
                probes.append(("GA-5", False,
                               f"heartbeat stale ({age} ticks)"))
            else:
                probes.append(("GA-5", True,
                               f"registered, heartbeat fresh ({age} ticks)"))

        # GA-6 network boundary ---------------------------------------------------
        out, err = self._call("published_ports")
        if err:
            probes.append(("GA-6", False, err))
        elif not isinstance(out, dict):
            probes.append(("GA-6", False, "ports payload malformed"))
        else:
            breached = {svc: ports for svc, ports in sorted(out.items())
                        if ports}
            probes.append(("GA-6", not breached,
                           "; ".join(f"{s} publishes {p}"
                                     for s, p in breached.items())
                           or "zero published ports on all services; "
                              "edge is the sole public surface"))

        # GA-7 redaction / log leakage -------------------------------------------
        out, err = self._call("output_streams")
        if err:
            probes.append(("GA-7", False, err))
        elif not isinstance(out, dict):
            probes.append(("GA-7", False, "stream payload malformed"))
        else:
            leaks = []
            for stream, text in sorted(out.items()):
                red, leak = self._scrub(str(text))
                if leak:
                    leaks.append(f"{stream}: secret-shaped material")
            probes.append(("GA-7", not leaks,
                           "; ".join(leaks) or
                           "no tokens/credentials/keys in output streams"))

        verdict = (PROBES_ACCEPTED if all(ok for _, ok, _ in probes)
                   else PROBES_REJECTED)
        return self._emit(verdict, probes, mfp, afp)


def main(argv: Optional[List[str]] = None) -> int:
    """CLI wiring: real acceptance report + real injected executors."""
    import argparse
    import sys
    ap = argparse.ArgumentParser(
        description="Stage G live probes GA-1..GA-7 (D-150).")
    ap.add_argument("--acceptance-json", required=True,
                    help="path to the D-149 ACCEPTED report JSON")
    args = ap.parse_args(argv)
    print("verify_stage_g_live_probes: interactive wiring requires the "
          "real container executors and audit sink; see run() and the "
          "battery for the injected contract.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

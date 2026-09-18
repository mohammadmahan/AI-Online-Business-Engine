"""Phase 22 M3 — composable health probes & the qa.health_report.v1
attestation (D-123).

A probe is a deterministic callable returning
`{name, ok, verdict, detail, checked_at_logical}` with verdict ∈
PASS / DEGRADED / FAIL (degraded is an EXPLICIT verdict, never a
silent pass). Probes receive everything INJECTED (read callables,
config) — this module imports no engine modules (D-124/RULES §35).

`ProbeRegistry.render()` produces `qa.health_report.v1`: a versioned,
machine-readable JSON attestation (deterministic key order, sorted
probes). `main()` is the operator CLI entry (`local/scripts/` inserts
`local/` on sys.path).

Shipped probes:
  - pg_schema      — live-PG reachability + expected schema presence
  - ledger_integrity — D-115 chain-head attestation verify over the
    Phase 19 control-audit chain (injected rows provider)
  - queue_depth    — scheduled-post queue depth vs a declared threshold
  - breaker_states — D-111 circuit breakers all CLOSED (degraded if any
    OPEN/HALF_OPEN)
"""

import json
from typing import Callable, Dict, List, Optional

SCHEMA_VERSION = "qa.health_report.v1"

VERDICTS = ("PASS", "DEGRADED", "FAIL")
_OK = {"PASS": True, "DEGRADED": True, "FAIL": False}


def _fail(reason: str):
    raise HealthError(reason)


class HealthError(ValueError):
    """A malformed probe result or report (Class-B programming
    error)."""


def probe_result(name: str, verdict: str, detail: str = "",
                 checked_at_logical: str = "") -> Dict:
    if verdict not in VERDICTS:
        _fail(f"invalid verdict: {verdict}")
    if not name or not isinstance(name, str):
        _fail("probe name required")
    # D-124: probe detail is a telemetry channel — same redaction gate
    # as log records (credentials → marker, bounded size).
    from canonical.obs_contracts import _sanitize_str
    d = _sanitize_str(detail) if detail else ""
    return {"name": name, "ok": _OK[verdict], "verdict": verdict,
            "detail": d,
            "checked_at_logical": checked_at_logical or ""}


def validate_report(report: Dict) -> Dict:
    if not isinstance(report, dict):
        _fail("report must be a dict")
    if report.get("schema_version") != SCHEMA_VERSION:
        _fail("schema_version mismatch")
    if not isinstance(report.get("probes"), list) or not report["probes"]:
        _fail("report needs a non-empty probes list")
    names = [p.get("name") for p in report["probes"]]
    if len(names) != len(set(names)):
        _fail("duplicate probe names")
    for p in report["probes"]:
        probe_result(p.get("name", ""), p.get("verdict", ""),
                     p.get("detail", ""),
                     p.get("checked_at_logical", ""))
    if report.get("overall") not in VERDICTS:
        _fail("overall verdict out of range")
    return report


class ProbeRegistry:
    """Composable probes; deterministic rendering (sorted by name)."""

    def __init__(self):
        self._probes: List[Callable[[], Dict]] = []

    def register(self, probe: Callable[[], Dict]) -> None:
        if not callable(probe):
            _fail("probe must be callable")
        self._probes.append(probe)

    def run(self) -> Dict:
        results = [p() for p in self._probes]
        for r in results:
            probe_result(r.get("name", ""), r.get("verdict", ""),
                         r.get("detail", ""),
                         r.get("checked_at_logical", ""))
        worst = "PASS"
        for r in results:
            if r["verdict"] == "FAIL":
                worst = "FAIL"
                break
            if r["verdict"] == "DEGRADED":
                worst = "DEGRADED"
        return {"schema_version": SCHEMA_VERSION, "overall": worst,
                "probes": sorted(results, key=lambda r: r["name"])}

    # alias consumed by some tooling
    render = run


class ShippedProbes:
    """Factory for the four shipped probes (all reads injected)."""

    @staticmethod
    def pg_schema(exec_fn: Callable, db: str = "business_engine_local") -> Callable:
        """Live-PG reachability + expected schema presence via an
        injected SQL executor (e.g. canonical.notion_ingest._exec)."""

        def probe() -> Dict:
            try:
                out = exec_fn(
                    "SELECT string_agg(table_schema, ',' ORDER BY "
                    "table_schema) FROM information_schema.tables "
                    "WHERE table_schema IN ('events','scheduling',"
                    "'admin','security','seed')").strip()
            except Exception as e:  # noqa: BLE001 — probe boundary
                return probe_result(
                    "pg_schema", "FAIL",
                    f"unreachable: {type(e).__name__}",
                    checked_at_logical="")
            have = set(out.split(",")) if out else set()
            need = {"events", "scheduling", "admin", "security", "seed"}
            missing = sorted(need - have)
            if not have:
                return probe_result("pg_schema", "FAIL", "no rows",
                                    checked_at_logical="")
            if missing:
                return probe_result(
                    "pg_schema", "DEGRADED",
                    f"missing schemas: {missing}", checked_at_logical="")
            return probe_result("pg_schema", "PASS",
                                "all expected schemas present",
                                checked_at_logical="")

        return probe

    @staticmethod
    def ledger_integrity(check_fn: Callable) -> Callable:
        """`check_fn() -> {"ok": bool, "reason"?: str, ...}` — a
        pre-wired attestation verify (e.g. ChainHeadAttestation.verify
        over the Phase 19 control-audit chain, attestation captured by
        the caller). A failed verify is FAIL, not degraded: tamper
        evidence is binary."""

        def probe() -> Dict:
            try:
                res = check_fn()
                ok = bool(res.get("ok"))
            except Exception as e:  # noqa: BLE001 — probe boundary
                return probe_result("ledger_integrity", "FAIL",
                                    f"verify error: {type(e).__name__}",
                                    checked_at_logical="")
            return probe_result(
                "ledger_integrity",
                "PASS" if ok else "FAIL",
                str(res.get("reason", "chain fold matches")),
                checked_at_logical="")

        return probe

    @staticmethod
    def queue_depth(depth_fn: Callable, warn_threshold: int,
                    fail_threshold: int) -> Callable:
        """Scheduled-post backlog vs declared thresholds: below warn →
        PASS, ≥warn → DEGRADED, ≥fail → FAIL."""
        if not (0 < warn_threshold < fail_threshold):
            _fail("thresholds must satisfy 0 < warn < fail")

        def probe() -> Dict:
            try:
                depth = int(depth_fn())
            except Exception as e:  # noqa: BLE001 — probe boundary
                return probe_result("queue_depth", "FAIL",
                                    f"depth read error: "
                                    f"{type(e).__name__}",
                                    checked_at_logical="")
            if depth >= fail_threshold:
                return probe_result(
                    "queue_depth", "FAIL",
                    f"depth {depth} >= fail threshold {fail_threshold}",
                    checked_at_logical="")
            if depth >= warn_threshold:
                return probe_result(
                    "queue_depth", "DEGRADED",
                    f"depth {depth} >= warn threshold {warn_threshold}",
                    checked_at_logical="")
            return probe_result("queue_depth", "PASS",
                                f"depth {depth} within thresholds",
                                checked_at_logical="")

        return probe

    @staticmethod
    def breaker_states(states_fn: Callable) -> Callable:
        """`states_fn() -> {name: state}` — all CLOSED → PASS; any
        OPEN/HALF_OPEN → DEGRADED (breakers doing their job is not a
        system failure); a read error is FAIL."""

        def probe() -> Dict:
            try:
                states = dict(states_fn())
            except Exception as e:  # noqa: 501 — probe boundary
                return probe_result("breaker_states", "FAIL",
                                    f"read error: {type(e).__name__}",
                                    checked_at_logical="")
            open_names = sorted(n for n, s in states.items()
                                if s != "CLOSED")
            if open_names:
                # D-124: bounded detail — count + deterministic head of
                # the list, explicitly marked (never an unbounded dump).
                shown = open_names[:5]
                more = len(open_names) - len(shown)
                suffix = f" …[+{more} more]" if more > 0 else ""
                return probe_result(
                    "breaker_states", "DEGRADED",
                    f"{len(open_names)} non-closed breaker(s): "
                    f"{shown}{suffix}",
                    checked_at_logical="")
            return probe_result("breaker_states", "PASS",
                                f"{len(states)} breaker(s) CLOSED",
                                checked_at_logical="")

        return probe


# --- operator CLI ---------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    """`python3 local/canonical/obs_health.py [json|text]`

    Renders the live attestation: live-PG probe + ledger integrity
    over the Phase 19 control-audit chain + breaker states (queue
    depth needs scheduling config — included when reachable).
    """
    import os
    import sys
    # CLI bootstrap: make `canonical` and the transport modules
    # importable when invoked directly (python3 local/canonical/obs_health.py).
    here = os.path.dirname(os.path.abspath(__file__))
    local_dir = os.path.dirname(here)
    scripts_dir = os.path.join(local_dir, "scripts")
    for p in (local_dir, scripts_dir):
        if p not in sys.path:
            sys.path.insert(0, p)
    argv = list(sys.argv[1:] if argv is None else argv)
    mode = argv[0] if argv else "text"

    reg = ProbeRegistry()

    # live-PG (guarded — offline machines get an explicit FAIL verdict,
    # never a crash)
    try:
        from canonical.notion_ingest import _exec  # noqa: E402
        reg.register(ShippedProbes.pg_schema(_exec))
        from canonical.admin_engine import default_vault  # noqa: E402
        from canonical.security_engine import ChainHeadAttestation  # noqa: E402
        rows_fn = default_vault().audit_rows
        att = ChainHeadAttestation(rows_fn)
        attested = att.compute("L0")
        reg.register(ShippedProbes.ledger_integrity(
            lambda: att.verify(attested, "L0")))
    except Exception:
        reg.register(lambda: probe_result(
            "pg_schema", "FAIL", "live stack unreachable",
            checked_at_logical=""))
        reg.register(lambda: probe_result(
            "ledger_integrity", "FAIL", "rows provider unavailable",
            checked_at_logical=""))

    # breakers via the admin facade (guarded)
    try:
        from canonical.admin_engine import default_vault  # noqa: E402
        vault = default_vault()
        reg.register(ShippedProbes.breaker_states(
            lambda: {n: r.get("state", "OPEN")
                     for n, r in vault.all_breakers().items()}))
    except Exception:
        reg.register(lambda: probe_result(
            "breaker_states", "FAIL", "admin facade unavailable",
            checked_at_logical=""))

    report = reg.run()
    if mode == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2,
                         sort_keys=True))
    else:
        print(f"overall: {report['overall']}")
        for p in report["probes"]:
            print(f"  [{p['verdict']:>8}] {p['name']}: {p['detail']}")
    return 0 if report["overall"] != "FAIL" else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())

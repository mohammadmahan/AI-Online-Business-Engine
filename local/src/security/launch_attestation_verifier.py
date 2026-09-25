"""Triple-evidence launch attestation gate (D-151).

D-150 produced the third cryptographically bound Stage G artifact:
the live probe report with its SHA-256 `probe_digest`. The cutover
bundle (D-147) and the acceptance report (D-149) carry `bundle_hash`
and `acceptance_fingerprint` the same way. Launch readiness requires
ALL THREE links present, individually intact, mutually correlated,
and DURABLY ATTESTED in the D-112 control-audit chain — any missing,
mismatched, tampered, or unattested link fails the gate closed.

This module is the gate. It is pure composition (RULES §35):

  TRIAD-01  hash integrity — each digest recomputed from its
            canonical artifact bytes matches the recorded value
            (a recomputation failure is TAMPER, never a warning);
  TRIAD-02  correlation — one deployment fingerprint: bundle
            `candidate_manifest_sha256` == acceptance
            `manifest_sha256` == probe `manifest_sha256`, and the
            probe's `acceptance_fingerprint` equals the acceptance
            report's (the probe observed the deployment that THIS
            acceptance cleared);
  TRIAD-03  D-112 rooting — each digest appears in an audit row of
            the operator control-audit chain (row kind in
            `stage_g_preflight` / `cutover_bundle_recorded` /
            `stage_g_acceptance` / `stage_g_live_probe`, or the
            digest embedded in a row's detail), and the chain
            verifies end-to-end (hash-chain integrity over every
            row — a broken chain attests nothing);
  TRIAD-04  verdicts — bundle READY_FOR_CUTOVER, acceptance
            ACCEPTED, probes PROBES_ACCEPTED (a cleared-but-rejected
            history never justifies launch).

Inputs are INJECTED callables: `bundle()`, `acceptance()`, `probe()`,
`audit_rows()`, and `chain_verifier()` (the ControlPlaneEngine's
`verify_chain`). The gate itself performs zero I/O, reads no clocks,
opens no sockets (AST-pinned in the battery).

`TripleEvidenceGate.evaluate()` returns a `TriadVerdict` with
`launch_ready` (all four checks pass) and named findings — every
refusal names its blocker (fail-closed precedent, D-137/D-148).

Integration (see `wire_into_registry`): the gate runs as a mandatory
probe in every `qa.health_report.v1` — `ProbeRegistry` composes the
canonical report shape, and a TRIAD failure is probe FAIL, pulling
`overall` and the deployment verdict down with it. The D-112 audit
rows provider bridges to `default_vault().audit_rows()`; a chain the
vault cannot read is an unreadable chain — FAIL.
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
    "TriadError", "TriadVerdict", "TripleEvidenceGate",
    "TRIAD_SCHEMA", "LAUNCH_READY", "LAUNCH_BLOCKED",
    "BUNDLE_SCHEMA", "ACCEPTANCE_SCHEMA", "PROBE_SCHEMA",
    "AUDIT_KINDS", "triad_probe",
]

TRIAD_SCHEMA = "stage_g_triple_evidence.v1"
LAUNCH_READY = "LAUNCH_EVIDENCE_COMPLETE"
LAUNCH_BLOCKED = "LAUNCH_EVIDENCE_INCOMPLETE"

BUNDLE_SCHEMA = "cutover.bundle.v1"
BUNDLE_READY = "READY_FOR_CUTOVER"
ACCEPTANCE_SCHEMA = "stage_g_acceptance_report.v1"
ACCEPTANCE_OK = "ACCEPTED"
PROBE_SCHEMA = "stage_g_live_probe_report.v1"
PROBES_OK = "PROBES_ACCEPTED"

# D-112 audit-row kinds that may attest a triad link (G-04 precedent:
# kind match OR digest embedded in the row detail).
AUDIT_KINDS = ("stage_g_preflight", "cutover_bundle_recorded",
               "stage_g_acceptance", "stage_g_live_probe")

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class TriadError(ValueError):
    """Contract-level misuse of the triple-evidence gate."""


def _fail(reason: str) -> None:
    raise TriadError(reason)


def canonical_hash(payload: Dict[str, Any]) -> str:
    """SHA-256 over the canonical JSON bytes (sort_keys, tight
    separators) — the exact formula every Stage G engine uses for
    bundle_hash / acceptance_fingerprint / probe_digest."""
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class TriadVerdict:
    """Deterministic, secret-free outcome of one triad evaluation."""
    schema: str
    verdict: str                     # LAUNCH_READY / LAUNCH_BLOCKED
    checks: tuple = field(default_factory=tuple)   # (id, ok, detail)

    @property
    def launch_ready(self) -> bool:
        return self.verdict == LAUNCH_READY

    def to_dict(self) -> Dict[str, Any]:
        return {"schema": self.schema, "verdict": self.verdict,
                "checks": [list(c) for c in self.checks]}


class TripleEvidenceGate:
    """TRIAD-01..04 over the injected Stage G artifacts (RULES §35).

    Injected:
      bundle         — ``() -> dict``  the D-147 attestation bundle
      acceptance     — ``() -> dict``  the D-149 acceptance report
      probe          — ``() -> dict``  the D-150 live probe report
      audit_rows     — ``() -> list``  D-112 control-audit rows
      chain_verifier — ``() -> dict`` D-112 chain verify (the
                       ControlPlaneEngine's `verify_chain`); must
                       return {"ok": True, ...} for TRIAD-03 to pass
    """

    def __init__(self,
                 bundle: Callable[[], Dict[str, Any]],
                 acceptance: Callable[[], Dict[str, Any]],
                 probe: Callable[[], Dict[str, Any]],
                 audit_rows: Callable[[], List[Dict[str, Any]]],
                 chain_verifier: Callable[[], Dict[str, Any]]) -> None:
        for name, fn in (("bundle", bundle), ("acceptance", acceptance),
                         ("probe", probe), ("audit_rows", audit_rows),
                         ("chain_verifier", chain_verifier)):
            if not callable(fn):
                _fail(f"{name} provider required")
        self._bundle = bundle
        self._acceptance = acceptance
        self._probe = probe
        self._audit_rows = audit_rows
        self._chain = chain_verifier

    # -- internals -------------------------------------------------------------

    @staticmethod
    def _raise(exc: Exception) -> None:
        raise TriadError(f"provider failed: {type(exc).__name__}") \
            from None

    def _load(self, name: str) -> Any:
        try:
            return getattr(self, f"_{name}")()
        except TriadError:
            raise
        except Exception as exc:  # noqa: BLE001 — provider boundary
            self._raise(exc)

    # -- TRIAD-01: hash integrity ---------------------------------------------

    def _check_hashes(self, bundle: Dict[str, Any],
                      acceptance: Dict[str, Any],
                      probe: Dict[str, Any]) -> List[Tuple[str, bool, str]]:
        checks: List[Tuple[str, bool, str]] = []

        recorded = bundle.get("bundle_hash", "")
        recomputed = canonical_hash(
            {k: v for k, v in bundle.items() if k != "bundle_hash"})
        if not _HEX64.match(recorded or ""):
            checks.append(("TRIAD-01", False,
                           "bundle_hash missing or malformed"))
        elif recorded != recomputed:
            checks.append(("TRIAD-01", False,
                           f"bundle_hash {recorded[:16]}… != recomputed "
                           f"{recomputed[:16]}… — TAMPERED bundle"))
        else:
            checks.append(("TRIAD-01", True,
                           f"bundle_hash intact ({recorded[:16]}…)"))

        afp = acceptance.get("acceptance_fingerprint", "")
        recomputed = canonical_hash(
            {k: v for k, v in acceptance.items()
             if k != "acceptance_fingerprint"})
        if not _HEX64.match(afp or ""):
            checks.append(("TRIAD-01", False,
                           "acceptance_fingerprint missing or malformed"))
        elif afp != recomputed:
            checks.append(("TRIAD-01", False,
                           f"acceptance_fingerprint {afp[:16]}… != "
                           f"recomputed {recomputed[:16]}… — TAMPERED "
                           "acceptance report"))
        else:
            checks.append(("TRIAD-01", True,
                           f"acceptance_fingerprint intact ({afp[:16]}…)"))

        recorded = probe.get("probe_digest", "")
        recomputed = canonical_hash(
            {k: v for k, v in probe.items() if k != "probe_digest"})
        if not _HEX64.match(recorded or ""):
            checks.append(("TRIAD-01", False,
                           "probe_digest missing or malformed"))
        elif recorded != recomputed:
            checks.append(("TRIAD-01", False,
                           f"probe_digest {recorded[:16]}… != recomputed "
                           f"{recomputed[:16]}… — TAMPERED probe report"))
        else:
            checks.append(("TRIAD-01", True,
                           f"probe_digest intact ({recorded[:16]}…)"))
        return checks

    # -- TRIAD-02: correlation ---------------------------------------------------

    @staticmethod
    def _check_correlation(bundle: Dict[str, Any],
                           acceptance: Dict[str, Any],
                           probe: Dict[str, Any]
                           ) -> List[Tuple[str, bool, str]]:
        checks: List[Tuple[str, bool, str]] = []
        b = bundle.get("candidate_manifest_sha256", "")
        a = acceptance.get("manifest_sha256", "")
        p = probe.get("manifest_sha256", "")
        if not (_HEX64.match(b or "") and _HEX64.match(a or "")
                and _HEX64.match(p or "")):
            checks.append(("TRIAD-02", False,
                           "one or more manifest fingerprints missing "
                           "or malformed — the triad cannot bind to a "
                           "single deployment"))
        elif not (b == a == p):
            checks.append(("TRIAD-02", False,
                           "manifest fingerprints diverge — bundle, "
                           "acceptance and probes attest DIFFERENT "
                           "deployments"))
        else:
            checks.append(("TRIAD-02", True,
                           f"one deployment fingerprint ({b[:16]}…) "
                           "across all three artifacts"))
        pa = probe.get("acceptance_fingerprint", "")
        aa = acceptance.get("acceptance_fingerprint", "")
        if not _HEX64.match(pa or ""):
            checks.append(("TRIAD-02", False,
                           "probe carries no acceptance fingerprint — "
                           "probes not bound to an acceptance"))
        elif pa != aa:
            checks.append(("TRIAD-02", False,
                           "probe's acceptance fingerprint != this "
                           "acceptance — probes observed a deployment "
                           "cleared by a different report"))
        else:
            checks.append(("TRIAD-02", True,
                           "probes bound to THIS acceptance report"))
        return checks

    # -- TRIAD-03: D-112 rooting -------------------------------------------------

    def _check_rooting(self, bundle: Dict[str, Any],
                       acceptance: Dict[str, Any],
                       probe: Dict[str, Any]
                       ) -> List[Tuple[str, bool, str]]:
        checks: List[Tuple[str, bool, str]] = []
        digests = (("bundle_hash", bundle.get("bundle_hash", "")),
                   ("acceptance_fingerprint",
                    acceptance.get("acceptance_fingerprint", "")),
                   ("probe_digest", probe.get("probe_digest", "")))
        try:
            rows = self._audit_rows() or []
        except TriadError:
            raise
        except Exception as exc:  # noqa: BLE001 — audit chain absent
            checks.append(("TRIAD-03", False,
                           f"control-audit chain unreadable: "
                           f"{type(exc).__name__}"))
            rows = []
        row_blobs: List[Tuple[str, str]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            kind = str(row.get("event_kind", ""))
            detail = row.get("detail") or {}
            blob = json.dumps(detail, ensure_ascii=False, sort_keys=True) \
                if isinstance(detail, dict) else str(detail)
            row_blobs.append((kind, blob))
        try:
            chain = self._chain() or {}
        except Exception as exc:  # noqa: BLE001 — verifier boundary
            checks.append(("TRIAD-03", False,
                           f"chain verifier failed: "
                           f"{type(exc).__name__}"))
        else:
            if chain.get("ok") is not True:
                checks.append(("TRIAD-03", False,
                               f"D-112 chain verification failed "
                               f"({chain.get('reason', 'mismatch')} at "
                               f"seq {chain.get('broken_at_seq', '?')}) "
                               "— a broken chain attests nothing"))
            else:
                checks.append(("TRIAD-03", True,
                               f"D-112 chain intact "
                               f"({chain.get('rows', '?')} rows)"))
        for label, digest in digests:
            if not _HEX64.match(digest or ""):
                checks.append(("TRIAD-03", False,
                               f"{label} unusable for audit lookup"))
                continue
            found = any(digest in blob or kind in AUDIT_KINDS
                        for kind, blob in row_blobs)
            if found:
                checks.append(("TRIAD-03", True,
                               f"{label} rooted in the D-112 chain "
                               f"({digest[:16]}…)"))
            else:
                checks.append(("TRIAD-03", False,
                               f"{label} absent from the D-112 chain — "
                               "the evidence is not durably attested"))
        return checks

    # -- TRIAD-04: verdicts ---------------------------------------------------------

    @staticmethod
    def _check_verdicts(bundle: Dict[str, Any],
                        acceptance: Dict[str, Any],
                        probe: Dict[str, Any]
                        ) -> List[Tuple[str, bool, str]]:
        checks: List[Tuple[str, bool, str]] = []
        bv = bundle.get("verdict", "")
        av = acceptance.get("verdict", "")
        pv = probe.get("verdict", "")
        if bv != BUNDLE_READY:
            checks.append(("TRIAD-04", False,
                           f"bundle verdict {bv!r} != "
                           f"{BUNDLE_READY!r} — cutover was never ready"))
        if av != ACCEPTANCE_OK:
            checks.append(("TRIAD-04", False,
                           f"acceptance verdict {av!r} != "
                           f"{ACCEPTANCE_OK!r} — provisioning never "
                           "cleared"))
        if pv != PROBES_OK:
            checks.append(("TRIAD-04", False,
                           f"probe verdict {pv!r} != {PROBES_OK!r} — "
                           "the live stack never cleared"))
        if bv == BUNDLE_READY and av == ACCEPTANCE_OK and pv == PROBES_OK:
            checks.append(("TRIAD-04", True,
                           "READY → ACCEPTED → PROBES_ACCEPTED — the "
                           "full Stage G verdict chain holds"))
        return checks

    # -- the evaluation -------------------------------------------------------------

    def evaluate(self) -> TriadVerdict:
        """TRIAD-01..04 over the triad. Every check runs (even after
        earlier failures) so one verdict names EVERY blocker."""
        bundle = self._load("bundle")
        acceptance = self._load("acceptance")
        probe = self._load("probe")
        for name, obj in (("bundle", bundle), ("acceptance", acceptance),
                          ("probe", probe)):
            if not isinstance(obj, dict):
                checks = [(f"TRIAD-01", False,
                           f"{name} artifact missing or malformed — "
                           "fail closed")]
                return TriadVerdict(schema=TRIAD_SCHEMA,
                                    verdict=LAUNCH_BLOCKED,
                                    checks=tuple(checks))
        checks: List[Tuple[str, bool, str]] = []
        checks += self._check_hashes(bundle, acceptance, probe)
        checks += self._check_correlation(bundle, acceptance, probe)
        checks += self._check_rooting(bundle, acceptance, probe)
        checks += self._check_verdicts(bundle, acceptance, probe)
        ok = all(c[1] for c in checks)
        verdict = LAUNCH_READY if ok else LAUNCH_BLOCKED
        rendered = [(cid, c_ok, deep_redact(detail))
                    for cid, c_ok, detail in checks]
        return TriadVerdict(schema=TRIAD_SCHEMA, verdict=verdict,
                            checks=tuple(rendered))


def triad_probe(gate: TripleEvidenceGate) -> Callable[[], Dict[str, Any]]:
    """Wrap the gate as a `qa.health_report.v1` probe (obs_health
    contract): LAUNCH_READY → PASS, anything else → FAIL — launch
    evidence is binary, never degraded (tamper-evidence precedent,
    D-123 `ledger_integrity`)."""

    def probe_fn() -> Dict[str, Any]:
        try:
            v = gate.evaluate()
        except Exception as exc:  # noqa: BLE001 — probe boundary
            from canonical.obs_health import probe_result
            return probe_result(
                "stage_g_triple_evidence", "FAIL",
                f"triad evaluation error: {type(exc).__name__}",
                checked_at_logical="")
        from canonical.obs_health import probe_result
        blocked = [c[0] for c in v.checks if not c[1]]
        if v.launch_ready:
            detail = ("bundle hash + acceptance fingerprint + probe "
                      "digest intact, correlated, D-112-rooted")
        else:
            # bounded detail — named blockers, never an unbounded dump
            shown = blocked[:6]
            more = len(blocked) - len(shown)
            suffix = f" …[+{more} more]" if more > 0 else ""
            detail = (f"triad incomplete: {', '.join(shown)}{suffix}")
        return probe_result("stage_g_triple_evidence",
                            "PASS" if v.launch_ready else "FAIL",
                            detail, checked_at_logical="")

    return probe_fn


def wire_into_registry(registry: Any, gate: TripleEvidenceGate) -> None:
    """Register the mandatory triad probe on an existing
    `canonical.obs_health.ProbeRegistry` — the launch-attestation
    wiring point. The gate is MANDATORY: a registry wired through
    this helper cannot render a passing health report while the
    triad is incomplete (the probe is FAIL, `overall` follows)."""
    registry.register(triad_probe(gate))

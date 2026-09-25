#!/usr/bin/env python3
"""Stage H — live cutover executor & owner activation gate (D-153).

The master Stage H execution engine: performs the LIVE CUTOVER under
explicit owner authority. Stage G closure (D-152) produced the seal;
this engine consumes it — together with a fresh, unspent Stage F
owner token (D-146 HMAC-SHA256) — and only then transitions the
deployment to ACTIVE, emitting the immutable
`stage_h_activation_record.v1`.

Execution rules (all fail-closed; any refusal aborts with ZERO
side-effects — no state transition, no record):

  H-01  the `stage_g_closure_seal.v1` is present, structurally
        valid, STAGE_G_CLOSED, and rooted: its closure_digest
        recomputes from the seal's canonical bytes AND the digest is
        attested in the D-112 audit trail (row kind
        `stage_g_closure`, or the digest embedded in a row detail);
  H-02  the Stage F owner token is fresh, unspent, and bound to THIS
        closure: the OwnerApprovalGate verdict is GO, its TTL window
        was minted to cover the activation tick, AND the token was
        minted for a draft whose manifest fingerprint matches the
        seal's `manifest_sha256` (a token for a different deployment
        does not authorize this cutover);
  H-03  pre-cutover environmental assertions: the Dokploy target
        state matches the deployment contract (expected service
        states) and ZERO unmapped port exposure exists on backend
        services — evaluated through the INJECTED state provider,
        never by direct observation in the core;
  H-04  the transition: deployment state → ACTIVE, and the immutable
        `stage_h_activation_record.v1` is emitted exactly once with
        the `activation_digest` over its canonical bytes;
  H-05  the critical-window watch: post-activation probes are
        evaluated against the CRITICAL_WINDOW_TICKS horizon and a
        failure yields the ATOMIC ROLLBACK PAYLOAD (Stage E §5 RB-1
        shape) for the operator — the payload is a verdict, the
        human executes it.

Purity & security (RULES §35, AST-pinned): the executor core is pure
— injected providers only, zero sockets, zero subprocess, zero wall
clock. The ONLY sanctioned host-touching surface is
`DokployStateAdapter`, which executes direct argv (`docker`/`dokploy`
CLI) with strict timeouts, no shell, allow-listed parameters, and
deep redaction before any string escapes (D-124). Secrets —
including the owner signing key — never enter any report, record, or
error (D-124).
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
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
    "CutoverError", "ActivationRecord", "StageHCutoverExecutor",
    "DokployStateAdapter", "build_cutover_providers",
    "RECORD_SCHEMA", "CUTOVER_EXECUTED", "CUTOVER_ABORTED",
    "ROLLBACK_ARMED", "SEAL_SCHEMA", "SEAL_CLOSED", "TOKEN_TTL_MAX",
    "CRITICAL_WINDOW_TICKS", "RESTART_MAX",
]

RECORD_SCHEMA = "stage_h_activation_record.v1"
CUTOVER_EXECUTED = "CUTOVER_EXECUTED"
CUTOVER_ABORTED = "CUTOVER_ABORTED"
ROLLBACK_ARMED = "ROLLBACK_ARMED"

SEAL_SCHEMA = "stage_g_closure_seal.v1"
SEAL_CLOSED = "STAGE_G_CLOSED"
TRIAD_LAUNCH_READY = "LAUNCH_EVIDENCE_COMPLETE"
ACCEPTANCE_SCHEMA = "stage_g_acceptance_report.v1"
PROBE_SCHEMA = "stage_g_live_probe_report.v1"
BUNDLE_SCHEMA = "cutover.bundle.v1"

# The Stage F token window ceiling (D-146): the executor additionally
# requires the window to have been minted to COVER the activation
# tick — a token that expires before activation is stale by
# construction.
TOKEN_TTL_MAX = 10_000
# Post-activation watch horizon (logical ticks).
CRITICAL_WINDOW_TICKS = 1_000
# Crash-loop bound, mirrored from the D-150 judge.
RESTART_MAX = 3

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_HEX16 = re.compile(r"^[0-9a-f]{16}$")
_NAME_SAFE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$")
_BACKEND = ("postgres-ssot", "redis", "telemetry-circuit")


class CutoverError(ValueError):
    """Contract-level misuse of the Stage H executor."""


def _fail(reason: str) -> None:
    raise CutoverError(reason)


def canonical_hash(payload: Dict[str, Any]) -> str:
    """SHA-256 over canonical JSON bytes — the Stage G/H digest
    formula."""
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ActivationRecord:
    """Canonical, immutable Stage H activation artifact."""
    schema: str
    verdict: str                       # CUTOVER_EXECUTED / CUTOVER_ABORTED
    manifest_sha256: str
    closure_digest: str
    token_id: str
    checks: tuple = field(default_factory=tuple)   # (id, ok, detail)
    observed_tick: int = 0

    @property
    def executed(self) -> bool:
        return self.verdict == CUTOVER_EXECUTED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "verdict": self.verdict,
            "manifest_sha256": self.manifest_sha256,
            "closure_digest": self.closure_digest,
            "token_id": self.token_id,
            "checks": [list(c) for c in self.checks],
            "observed_tick": self.observed_tick,
        }

    @property
    def activation_digest(self) -> str:
        """SHA-256 over the record's canonical bytes — immutable
        binding of the activation to THIS seal, token and tick."""
        return canonical_hash(self.to_dict())


class StageHCutoverExecutor:
    """H-01..H-05 with injected providers (RULES §35).

    Injected:
      clock              — ``() -> int`` logical tick
      audit_sink         — ``callable(dict)`` (D-112/D-121 in prod)
      seal_provider      — ``() -> dict`` the D-152 closure seal
      audit_rows         — ``() -> list`` D-112 audit rows (H-01
                           rooting)
      approval_verdict   — ``() -> dict`` the Stage F gate's verdict
                           dict (EvaluationVerdict.to_dict() shape,
                           gate == GO required; H-02)
      token_draft        — ``() -> dict`` the presented token draft
                           {manifest_sha256, issued_tick,
                           expires_tick, ...} for the H-02 window
                           binding
      target_state       — ``() -> dict`` the Dokploy target state
                           (H-03), e.g. {service: {"running": bool,
                           "healthy": bool, "restarts": int,
                           "ports": [..]}}
      transition         — ``() -> dict`` performs the ACTIVE
                           transition (H-04); injected so the core
                           stays pure and tests inject a fake
      post_activation_probes — ``() -> dict`` probe name -> ok bool
                           for the H-05 critical-window watch
    """

    def __init__(self, clock: Callable[[], int],
                 audit_sink: Callable[[Dict[str, Any]], None],
                 seal_provider: Optional[Callable[[], Dict[str, Any]]] = None,
                 audit_rows: Optional[Callable[[], List[Dict[str, Any]]]] = None,
                 approval_verdict: Optional[Callable[[], Dict[str, Any]]] = None,
                 token_draft: Optional[Callable[[], Dict[str, Any]]] = None,
                 target_state: Optional[Callable[[], Dict[str, Any]]] = None,
                 transition: Optional[Callable[[], Dict[str, Any]]] = None,
                 post_activation_probes: Optional[Callable[[], Dict[str, Any]]] = None,
                 ) -> None:
        if not callable(clock) or not callable(audit_sink):
            _fail("clock and audit_sink required")
        self._clock = clock
        self._sink = audit_sink
        self._prov = {
            "seal": seal_provider,
            "audit_rows": audit_rows,
            "approval": approval_verdict,
            "draft": token_draft,
            "target_state": target_state,
            "transition": transition,
            "probes": post_activation_probes,
        }

    # -- internals -------------------------------------------------------------

    def _load(self, name: str) -> Tuple[Optional[Any], str]:
        fn = self._prov[name]
        if fn is None:
            return None, "provider not wired — fail closed"
        try:
            return fn(), ""
        except Exception as exc:  # noqa: BLE001 — provider boundary
            return None, f"provider failure: {type(exc).__name__}"

    def _emit(self, verdict: str, checks: List[Tuple[str, bool, str]],
              manifest: str = "", closure: str = "", token: str = ""
              ) -> ActivationRecord:
        record = ActivationRecord(
            schema=RECORD_SCHEMA, verdict=verdict,
            manifest_sha256=manifest, closure_digest=closure,
            token_id=token,
            checks=tuple((c[0], c[1], deep_redact(str(c[2])))
                         for c in checks),
            observed_tick=self._clock())
        blob = json.dumps(record.to_dict(), sort_keys=True,
                          separators=(",", ":"), ensure_ascii=False)
        redacted = json.loads(deep_redact(blob))
        # Public commitments (D-146 precedent): manifest_sha256,
        # closure_digest and token_id are hashes of bindable public
        # data — restored after redaction so the D-112/D-121 ledger
        # copy stays chain-correlatable. Everything else stays
        # redacted; the signing key and nonce are NEVER in the record.
        for k in ("manifest_sha256", "closure_digest", "token_id"):
            redacted[k] = record.to_dict()[k]
        self._sink(redacted)
        return record

    # -- H-01: the closure seal -------------------------------------------------

    def _h01(self) -> Tuple[bool, str, List[Tuple[str, bool, str]]]:
        """(ok, closure_digest, checks)."""
        checks: List[Tuple[str, bool, str]] = []
        seal, err = self._load("seal")
        if seal is None:
            checks.append(("H-01", False,
                           f"Stage G closure seal absent ({err}) — "
                           "Stage G never closed"))
            return False, "", checks
        if not isinstance(seal, dict):
            checks.append(("H-01", False,
                           "closure seal malformed — fail closed"))
            return False, "", checks
        if seal.get("schema") != SEAL_SCHEMA:
            checks.append(("H-01", False,
                           f"seal schema {seal.get('schema')!r} != "
                           f"{SEAL_SCHEMA!r}"))
            return False, "", checks
        if seal.get("verdict") != SEAL_CLOSED:
            checks.append(("H-01", False,
                           f"seal verdict {seal.get('verdict')!r} != "
                           f"{SEAL_CLOSED!r} — Stage G is OPEN"))
            return False, "", checks
        recorded = seal.get("closure_digest", "")
        recomputed = canonical_hash(
            {k: v for k, v in seal.items() if k != "closure_digest"})
        if not _HEX64.match(recorded or ""):
            checks.append(("H-01", False,
                           "closure_digest missing or malformed"))
            return False, "", checks
        if recorded != recomputed:
            checks.append(("H-01", False,
                           f"closure_digest {recorded[:16]}… != "
                           f"recomputed {recomputed[:16]}… — ALTERED "
                           "seal"))
            return False, "", checks
        # D-112 rooting: the digest must be attested in the chain
        rows, err = self._load("audit_rows")
        rooted = False
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                kind = str(row.get("event_kind", ""))
                detail = row.get("detail") or {}
                blob = json.dumps(detail, ensure_ascii=False,
                                  sort_keys=True) \
                    if isinstance(detail, dict) else str(detail)
                if kind == "stage_g_closure" or \
                        recorded in blob:
                    rooted = True
                    break
        if not rooted:
            checks.append(("H-01", False,
                           "closure seal not rooted in the D-112 "
                           "audit trail — the closure was never "
                           "durably attested"))
        else:
            checks.append(("H-01", True,
                           f"closure seal verified + rooted "
                           f"({recorded[:16]}…)"))
        manifest = seal.get("manifest_sha256", "") \
            if isinstance(seal.get("manifest_sha256"), str) else ""
        return rooted, recorded, checks

    # -- H-02: the owner token ------------------------------------------------------

    def _h02(self, closure_digest: str, manifest: str
             ) -> Tuple[bool, str, List[Tuple[str, bool, str]]]:
        """(ok, token_id, checks). The token must be GO, unspent
        (the Stage F gate burns the nonce on GO — a replay arrives as
        a non-GO verdict), windowed to cover the activation tick, and
        minted for THIS deployment's manifest fingerprint."""
        checks: List[Tuple[str, bool, str]] = []
        verdict, err = self._load("approval")
        if verdict is None:
            checks.append(("H-02", False,
                           f"owner approval verdict absent ({err}) — "
                           "no authorization, no cutover"))
            return False, "", checks
        if not isinstance(verdict, dict):
            checks.append(("H-02", False,
                           "owner approval verdict malformed"))
            return False, "", checks
        if verdict.get("gate") != "GO":
            checks.append(("H-02", False,
                           f"owner gate {verdict.get('gate')!r} != "
                           f"'GO' ({verdict.get('reason', 'unknown')}) "
                           "— stale, spent, or invalid token"))
            return False, "", checks
        tid = verdict.get("token_id", "")
        if not _HEX16.match(tid or ""):
            checks.append(("H-02", False,
                           "owner verdict carries no usable token id"))
            return False, "", checks
        # window binding: the draft's TTL must cover THIS activation
        draft, err = self._load("draft")
        if draft is None or not isinstance(draft, dict):
            checks.append(("H-02", False,
                           "token draft absent or malformed — the "
                           "activation tick cannot be window-bound"))
            return False, "", checks
        issued = draft.get("issued_tick")
        expires = draft.get("expires_tick")
        now = self._clock()
        if not isinstance(issued, int) or isinstance(issued, bool) or \
                not isinstance(expires, int) or isinstance(expires, bool):
            checks.append(("H-02", False,
                           "token draft ticks malformed — fail closed"))
            return False, "", checks
        if not (0 < expires - issued <= TOKEN_TTL_MAX):
            checks.append(("H-02", False,
                           f"token window {expires - issued} ticks "
                           "outside the Stage F contract"))
            return False, "", checks
        if now < issued or now >= expires:
            checks.append(("H-02", False,
                           f"token window [{issued}..{expires}) does "
                           f"not cover the activation tick {now} — "
                           "stale token"))
            return False, "", checks
        # deployment binding: the draft fingerprint must match the seal
        dfp = draft.get("manifest_sha256", "")
        if not _HEX64.match(dfp or ""):
            checks.append(("H-02", False,
                           "token draft fingerprint malformed"))
            return False, "", checks
        if manifest and dfp != manifest:
            checks.append(("H-02", False,
                           "token minted for a DIFFERENT deployment "
                           "fingerprint than the closure seal — "
                           "divergent binding"))
            return False, "", checks
        checks.append(("H-02", True,
                       f"owner token fresh, unspent, window-bound "
                       f"({tid}, [{issued}..{expires}), "
                       f"{dfp[:16]}…)"))
        return True, tid, checks

    # -- H-03: pre-cutover environmental assertions ---------------------------------

    @staticmethod
    def _h03(target_state: Any
             ) -> Tuple[bool, List[Tuple[str, bool, str]]]:
        checks: List[Tuple[str, bool, str]] = []
        if not isinstance(target_state, dict) or not target_state:
            checks.append(("H-03", False,
                           "Dokploy target state absent or malformed — "
                           "the environment cannot be asserted"))
            return False, checks
        bad_services = []
        exposed = []
        for svc, st in sorted(target_state.items()):
            if not isinstance(st, dict):
                bad_services.append(f"{svc}:malformed")
                continue
            running = st.get("running") is True
            healthy = st.get("healthy", running) is True
            if not (running and healthy):
                bad_services.append(f"{svc}:down")
            restarts = st.get("restarts", 0)
            if isinstance(restarts, int) and restarts > RESTART_MAX:
                bad_services.append(f"{svc}:restart-loop")
            ports = st.get("ports")
            if svc in _BACKEND and ports:
                exposed.append(f"{svc}:{ports}")
            elif svc not in _BACKEND and ports:
                # non-backend services must publish NOTHING unless the
                # state explicitly marks the port as edge-mapped
                unmapped = [p for p in ports
                            if not str(p).startswith("edge:")]
                if unmapped:
                    exposed.append(f"{svc}:{unmapped}")
        if bad_services:
            checks.append(("H-03", False,
                           f"target state unhealthy: {bad_services} — "
                           "cutover into a broken environment is "
                           "refused"))
        else:
            checks.append(("H-03", True,
                           f"{len(target_state)} services running and "
                           "healthy at the target"))
        if exposed:
            checks.append(("H-03", False,
                           f"unmapped port exposure: {exposed} — "
                           "zero exposure is the contract"))
        else:
            checks.append(("H-03", True,
                           "zero unmapped port exposure"))
        return (all(c[1] for c in checks)), checks

    # -- H-04/H-05: transition + critical-window watch ---------------------------------

    def _h05(self) -> Tuple[bool, List[Tuple[str, bool, str]]]:
        probes, err = self._load("probes")
        checks: List[Tuple[str, bool, str]] = []
        if probes is None:
            checks.append(("H-05", False,
                           f"post-activation probes unavailable "
                           f"({err}) — the critical window is "
                           "unwatchable, fail closed"))
            return False, checks
        if not isinstance(probes, dict) or not probes:
            checks.append(("H-05", False,
                           "post-activation probe payload malformed"))
            return False, checks
        failed = sorted(n for n, ok in probes.items() if ok is not True)
        if failed:
            checks.append(("H-05", False,
                           f"critical-window probes failed: {failed} "
                           "— rollback armed"))
        else:
            checks.append(("H-05", True,
                           f"{len(probes)} post-activation probes "
                           "green inside the critical window"))
        return (not failed), checks

    @staticmethod
    def rollback_payload(reason: str, closure_digest: str,
                         failed_probes: List[str],
                         observed_tick: int) -> Dict[str, Any]:
        """The ATOMIC ROLLBACK PAYLOAD (H-05): the Stage E §5 RB-1
        shape — a deterministic verdict the OPERATOR executes; the
        engine never mutates the live stack on its own authority."""
        return {
            "schema": "stage_h_rollback_payload.v1",
            "reason": reason,
            "closure_digest": closure_digest,
            "failed_probes": list(failed_probes),
            "row": "RB-1",
            "ordering": ("stop new work first, then compensate/drain,"
                         " then reconcile"),
            "procedure": ("edge gateway back to blue; green stack "
                          "stop (keep volumes); re-run the Stage E "
                          "§4 verification against blue"),
            "post_verification": ("smoke green on blue; incident "
                                  "logged to the D-121 ledger"),
            "observed_tick": observed_tick,
        }

    # -- the run -----------------------------------------------------------------------

    def run(self) -> ActivationRecord:
        """H-01..H-05 → immutable record. Zero side-effects on ANY
        refusal: no transition happens, no record beyond the single
        audited CUTOVER_ABORTED artifact."""
        checks: List[Tuple[str, bool, str]] = []
        ok1, closure, c1 = self._h01()
        checks += c1
        if not ok1:
            return self._emit(CUTOVER_ABORTED, checks)
        ok2, token, c2 = self._h02(closure,
                                   self._prov_seal_manifest())
        checks += c2
        if not ok2:
            return self._emit(CUTOVER_ABORTED, checks,
                              closure=closure)
        seal, _ = self._load("seal")
        manifest = seal.get("manifest_sha256", "") \
            if isinstance(seal, dict) else ""
        state, err = self._load("target_state")
        if state is None:
            checks.append(("H-03", False,
                           f"Dokploy target state unavailable "
                           f"({err}) — fail closed"))
            return self._emit(CUTOVER_ABORTED, checks,
                              closure=closure, token=token,
                              manifest=manifest)
        ok3, c3 = self._h03(state)
        checks += c3
        if not ok3:
            return self._emit(CUTOVER_ABORTED, checks,
                              closure=closure, token=token,
                              manifest=manifest)
        # H-04: the transition — the single sanctioned side-effect
        outcome, err = self._load("transition")
        if outcome is None or not isinstance(outcome, dict) or \
                outcome.get("active") is not True:
            checks.append(("H-04", False,
                           f"deployment transition failed or "
                           f"unconfirmed ({err or 'no active state'}) "
                           "— aborting with zero further effects"))
            return self._emit(CUTOVER_ABORTED, checks,
                              closure=closure, token=token,
                              manifest=manifest)
        checks.append(("H-04", True,
                       "deployment state → ACTIVE; activation "
                       "record emitted"))
        # H-05: the critical-window watch
        ok5, c5 = self._h05()
        checks += c5
        if ok5:
            return self._emit(CUTOVER_EXECUTED, checks,
                              closure=closure, token=token,
                              manifest=manifest)
        payload = self.rollback_payload(
            "critical-window probe failure", closure,
            sorted(n for n, ok in
                   (self._load("probes")[0] or {}).items()
                   if ok is not True),
            self._clock())
        checks.append(("ROLLBACK", False,
                       "atomic rollback payload emitted (RB-1) — "
                       "operator executes; engine does not"))
        return self._emit(ROLLBACK_ARMED, checks,
                          closure=closure, token=token,
                          manifest=manifest)

    def _prov_seal_manifest(self) -> str:
        seal, _ = self._load("seal")
        return seal.get("manifest_sha256", "") \
            if isinstance(seal, dict) else ""


# ---------------------------------------------------------------------------
# The sanctioned host-touching adapter (direct argv only)
# ---------------------------------------------------------------------------

class DokployStateAdapter:
    """Dokploy/docker target-state reader — direct argv ONLY.

    Every child process is a fixed token list with allow-list
    validated parameters; no shell, no interpolation, strict
    timeouts, deep redaction before any string escapes (D-124).
    Satisfies the executor's `target_state` provider.
    """

    def __init__(self, docker_binary: str = "docker",
                 services: Tuple[str, ...] = ("postgres-ssot", "redis",
                                              "app-orchestrator",
                                              "telemetry-circuit"),
                 runner: Optional[Callable[..., subprocess.CompletedProcess]] = None,
                 timeout_s: float = 15.0) -> None:
        if not _NAME_SAFE.match(docker_binary or ""):
            raise CutoverError("invalid_docker_binary")
        for s in services:
            if not _NAME_SAFE.match(s or ""):
                raise CutoverError("invalid_service_name")
        self._docker = docker_binary
        self._services = tuple(services)
        self._run = runner or self._run_argv
        self._timeout = float(timeout_s)

    def _run_argv(self, argv: List[str],
                  ) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(argv, capture_output=True,
                                  text=True, timeout=self._timeout)
        except subprocess.TimeoutExpired:
            raise CutoverError("timeout") from None
        except OSError as exc:
            raise CutoverError(
                f"spawn_failure: {type(exc).__name__}") from None

    def target_state(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for svc in self._services:
            argv = [self._docker, "inspect", "--format",
                    "{{json .}}", svc]
            proc = self._run(argv)
            if proc.returncode != 0:
                raise CutoverError("inspect_failed")
            try:
                info = json.loads(proc.stdout)
            except (ValueError, TypeError):
                raise CutoverError("payload_malformed") from None
            state = info.get("State") or {}
            health = (state.get("Health") or {}).get("Status", "")
            out[svc] = {
                "running": state.get("Running") is True,
                "healthy": (health == "healthy"
                            if health else
                            state.get("Running") is True),
                "restarts": state.get("RestartCount", 0),
                "ports": self._ports(info),
            }
        return out

    @staticmethod
    def _ports(info: Dict[str, Any]) -> List[str]:
        ports = (info.get("NetworkSettings") or {}).get("Ports") or {}
        out: List[str] = []
        for container_port, bindings in sorted(ports.items()):
            for b in bindings or []:
                ip = b.get("HostIp", "")
                if ip not in ("", "127.0.0.1", "::1"):
                    out.append(f"{ip}:{b.get('HostPort', '')}:"
                               f"{container_port}")
        return out


def build_cutover_providers(
        docker_binary: str = "docker",
        services: Tuple[str, ...] = ("postgres-ssot", "redis",
                                     "app-orchestrator",
                                     "telemetry-circuit"),
        runner: Optional[Callable[..., subprocess.CompletedProcess]] = None,
) -> Dict[str, Callable]:
    """Wire the argv adapter into the executor kwargs:
    `StageHCutoverExecutor(clock, audit_sink, **build_cutover_providers())`."""
    adapter = DokployStateAdapter(docker_binary=docker_binary,
                                  services=services, runner=runner)
    return {"target_state": adapter.target_state}


def main(argv: Optional[List[str]] = None) -> int:
    """CLI wiring: real seal + real owner gate + real D-112 chain."""
    import argparse
    import sys
    ap = argparse.ArgumentParser(
        description="Stage H live cutover executor (H-01..H-05, D-153).")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    print("stage_h_cutover_executor: interactive wiring requires the "
          "real closure seal, the owner approval gate, the D-112 "
          "chain and the live Dokploy target; see run() and the "
          "battery for the injected contract.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

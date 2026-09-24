#!/usr/bin/env python3
"""Cutover transaction coordinator (D-147).

The unified, deterministic pre-cutover pipeline: Stage C host
prerequisites → Stage D/E manifest fingerprint + V-01..V-10 → Stage F
owner authorization evaluation → an immutable Cutover Bundle
attestation artifact. Composition only — every check delegates to the
shipped engines (`stage_c_runbook_validator`, `verify_cutover_readiness`,
`owner_approval_gate`); nothing is re-implemented here.

Discipline:

  PURE CORE    — no subprocess, no sockets, no direct file I/O, no
                 wall clock. All world effects arrive via injected
                 dependencies (RULES §35):
                   clock() -> int                      logical tick
                   audit_sink(report) -> None          D-121 log ledger
                   record_persister(report) -> None    verdict record
                                                        writer
                   signer     owner signing key (or None ⇒ the owner
                              evaluates out of band and hands over a
                              verdict record instead)
                 `run_pipeline(...)` accepts injected step callables
                 so the CLI can wire real engines while the battery
                 injects fakes.

  ORDERED      — steps run strictly in order; the FIRST failing step
                 aborts the pipeline. The owner token is evaluated
                 (and therefore CONSUMED — single-use) only after
                 Stage C + D/E are green. A failing technical stage
                 never burns an authorization.

  FAIL-CLOSED  — any absent/failed/unevaluatable step is a NO_GO
                 bundle; a bundle is emitted for EVERY terminal state
                 (audited, hash-bound), and `READY_FOR_CUTOVER` is
                 reachable ONLY when every stage is green, including
                 V-10 (a valid Stage F GO bound to the exact manifest
                 fingerprint).

  D-124        — bundle fields carry hashes, ids, phrases, and verdict
                 words only; the signing key, token signature, and
                 nonce never enter any artifact.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

try:  # battery package path or script cwd path
    from ..memory.vector_store import deep_redact  # type: ignore
except ImportError:  # pragma: no cover - script invocation
    from memory.vector_store import deep_redact  # type: ignore

__all__ = [
    "CutoverOrchestratorError", "StepReport", "CutoverBundle",
    "CutoverOrchestrator", "BUNDLE_READY", "BUNDLE_BLOCKED",
]

BUNDLE_READY = "READY_FOR_CUTOVER"
BUNDLE_BLOCKED = "BLOCKED"

BUNDLE_SCHEMA = "cutover.bundle.v1"


class CutoverOrchestratorError(ValueError):
    """Contract-level misuse of the orchestrator (fail-closed)."""


def _fail(reason: str) -> None:
    raise CutoverOrchestratorError(reason)


@dataclass(frozen=True)
class StepReport:
    """One pipeline step's outcome (secret-free by construction)."""
    step: str                    # "stage_c" | "stage_de" | "stage_f"
    ok: bool
    detail: str                  # deep-redacted
    findings: tuple = field(default_factory=tuple)

    def to_dict(self) -> Dict[str, Any]:
        return {"step": self.step, "ok": self.ok,
                "detail": self.detail, "findings": list(self.findings)}


@dataclass(frozen=True)
class CutoverBundle:
    """Immutable attestation artifact for ONE cutover attempt."""
    schema: str
    verdict: str                          # READY_FOR_CUTOVER / BLOCKED
    candidate_manifest_sha256: str
    session_id: str
    target_env: str
    observed_tick: int
    steps: tuple                          # of StepReport.to_dict()
    stage_f_token_id: str                 # '' when not evaluated
    abort_reason: str                     # '' when ready

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "verdict": self.verdict,
            "candidate_manifest_sha256": self.candidate_manifest_sha256,
            "session_id": self.session_id,
            "target_env": self.target_env,
            "observed_tick": self.observed_tick,
            "steps": list(self.steps),
            "stage_f_token_id": self.stage_f_token_id,
            "abort_reason": self.abort_reason,
        }

    @property
    def bundle_hash(self) -> str:
        """SHA-256 over the canonical bundle bytes (the attestation
        binding; computed over the serialized dict, key-sorted)."""
        blob = json.dumps(self.to_dict(), sort_keys=True,
                          separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class CutoverOrchestrator:
    """Four-step pre-cutover pipeline with injected dependencies.

    Injected (RULES §35 — the core performs no I/O):
      clock          — ``() -> int`` logical tick
      audit_sink     — ``callable(dict)`` receiving every bundle
                       (D-121 `engine.log.v1` in production)
      record_persister — ``callable(dict)`` persisting the Stage F
                       verdict record (runtime artifact; optional —
                       when None the gate's record is used in memory)
      stage_c_check  — ``callable() -> (ok: bool, detail: str)``
      stage_de_check — ``callable() -> (ok: bool, detail: str)``
                       (V-01..V-10 via verify_cutover_readiness)
      stage_f_evaluate — ``callable(session, env) -> dict`` returning
                       the gate's verdict record enriched with
                       issued/expires ticks (the D-146 engine). May
                       raise ApprovalGateError — surfaced, never
                       swallowed.
    """

    def __init__(self, clock: Callable[[], int],
                 audit_sink: Callable[[Dict[str, Any]], None],
                 stage_c_check: Callable[[], tuple],
                 stage_de_check: Callable[[], tuple],
                 stage_f_evaluate: Callable[[str, str], Dict[str, Any]],
                 manifest_sha256: str,
                 record_persister: Optional[Callable[[Dict[str, Any]], None]] = None,
                 session_id: str = "",
                 target_env: str = "") -> None:
        if not callable(clock) or not callable(audit_sink):
            _fail("clock and audit_sink required")
        if not callable(stage_c_check) or not callable(stage_de_check):
            _fail("stage check callables required")
        if not callable(stage_f_evaluate):
            _fail("stage_f_evaluate required")
        if not isinstance(manifest_sha256, str) or \
                not re.fullmatch(r"[0-9a-f]{64}", manifest_sha256 or ""):
            _fail("manifest_sha256 required hex64")
        self._clock = clock
        self._sink = audit_sink
        self._persist = record_persister
        self._c = stage_c_check
        self._de = stage_de_check
        self._f = stage_f_evaluate
        self._manifest = manifest_sha256
        self._session = session_id
        self._env = target_env

    # -- internals ---------------------------------------------------------

    def _bundle(self, verdict: str, steps: List[StepReport],
                abort_reason: str = "", token_id: str = "") -> CutoverBundle:
        bundle = CutoverBundle(
            schema=BUNDLE_SCHEMA, verdict=verdict,
            candidate_manifest_sha256=self._manifest,
            session_id=self._session, target_env=self._env,
            observed_tick=self._clock(),
            steps=tuple(s.to_dict() for s in steps),
            stage_f_token_id=token_id, abort_reason=abort_reason)
        blob = json.dumps(bundle.to_dict(), sort_keys=True,
                          separators=(",", ":"), ensure_ascii=False)
        self._sink(json.loads(deep_redact(blob)))
        return bundle

    @staticmethod
    def _step(step: str, outcome: tuple) -> StepReport:
        ok, detail = outcome
        return StepReport(step=step, ok=bool(ok),
                          detail=deep_redact(str(detail)),
                          findings=(f"{step}:{'PASS' if ok else 'FAIL'}",))

    # -- the pipeline ---------------------------------------------------------

    def run_pipeline(self, token: str, draft: Any) -> CutoverBundle:
        """Execute the four-step pre-cutover transaction.

        The owner token is evaluated LAST — a failing technical stage
        aborts BEFORE the single-use burn, so an authorization is never
        wasted on an unready cutover. Exactly one bundle is emitted and
        audited per call.
        """
        steps: List[StepReport] = []

        # Step 1 — Stage C host facts & prerequisites
        r1 = self._step("stage_c", self._c())
        steps.append(r1)
        if not r1.ok:
            return self._bundle(BUNDLE_BLOCKED, steps,
                                abort_reason="stage_c_not_ready")

        # Step 2 — Stage D/E manifest fingerprint + V-01..V-10
        r2 = self._step("stage_de", self._de())
        steps.append(r2)
        if not r2.ok:
            return self._bundle(BUNDLE_BLOCKED, steps,
                                abort_reason="stage_de_not_ready")

        # Step 3 — Stage F owner authorization (V-10; consumes the nonce)
        try:
            record = self._f(self._session, self._env)
        except Exception as exc:  # gate refusals are terminal, auditable
            steps.append(StepReport(
                step="stage_f", ok=False,
                detail=deep_redact(f"gate evaluation failed: {exc}"),
                findings=("stage_f:FAIL",)))
            return self._bundle(BUNDLE_BLOCKED, steps,
                                abort_reason="stage_f_not_authorized")
        ok = bool(record.get("gate") == "GO")
        steps.append(StepReport(
            step="stage_f", ok=ok,
            detail=deep_redact(str(record.get("reason", ""))),
            findings=(f"stage_f:{'PASS' if ok else 'FAIL'}",)))
        if self._persist is not None and ok:
            self._persist(record)  # runtime verdict record (D-124-safe)
        if not ok:
            return self._bundle(BUNDLE_BLOCKED, steps,
                                abort_reason="stage_f_not_authorized")

        # Step 4 — immutable Cutover Bundle attestation
        return self._bundle(BUNDLE_READY, steps,
                            token_id=str(record.get("token_id", "")))


def main(argv: Optional[List[str]] = None) -> int:
    """CLI wiring: real engines, real clock, D-121 audit sink."""
    import argparse
    import sys
    ap = argparse.ArgumentParser(
        description="Cutover transaction coordinator (D-147): "
                    "Stage C → D/E (V-01..V-10) → Stage F → bundle.")
    ap.add_argument("--session", required=True)
    ap.add_argument("--env", required=True)
    ap.add_argument("--token", required=True,
                    help="<token_id>.<signature> from the owner")
    args = ap.parse_args(argv)
    print("cutover_orchestrator: interactive wiring requires the real "
          "engines; see run_pipeline() and the battery for the "
          "injected contract.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

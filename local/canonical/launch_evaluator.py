"""Phase 26 M1 — deterministic Go/No-Go evaluator (D-138).

Pure over the D-137 contracts: fail-closed verdicts, stable finding
ordering, byte-identical output for identical inputs, and a durable
attestation hash binding (matrix version, candidate commit,
configuration fingerprint, evidence references, findings, verdict,
approval state). No I/O, no wall clock.

Verdict rules (owner-approved):
  GO              — every mandatory control PASSes and no control fails.
  CONDITIONAL_GO  — every mandatory control PASSes but at least one
                    NON-mandatory control FAILs or is BLOCKED; valid
                    only for explicitly declared limited-scope
                    activation (never silently full production).
  NO_GO           — any mandatory control FAILs, is BLOCKED, or
                    cannot be evaluated (missing/stale/mismatched
                    evidence). Absent evidence is never a pass.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from typing import Any, Dict, Tuple

from .launch_contracts import (
    ContractError,
    ControlRecord,
    LaunchMatrix,
    MATRIX_VERSION,
    VERDICTS,
    evaluate_control,
    validate_matrix,
)

__all__ = [
    "Finding",
    "EvaluationResult",
    "evaluate_matrix",
    "attestation_hash",
    "render_report",
]


@dataclass(frozen=True)
class Finding:
    """One per-control verdict in stable, sorted order."""
    control_id: str
    domain: str
    state: str
    severity: str
    mandatory: bool
    reason: str
    remediation: str
    evidence_reference: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "control_id": self.control_id, "domain": self.domain,
            "state": self.state, "severity": self.severity,
            "mandatory": self.mandatory, "reason": self.reason,
            "remediation": self.remediation,
            "evidence_reference": self.evidence_reference,
        }


@dataclass(frozen=True)
class EvaluationResult:
    matrix_version: str
    candidate_commit: str
    config_fingerprint: str
    verdict: str
    findings: Tuple[Finding, ...]
    approval_state: str = "NONE"

    def __post_init__(self) -> None:
        if self.verdict not in VERDICTS:
            raise ContractError(f"unknown verdict: {self.verdict!r}")
        if not self.candidate_commit or not isinstance(self.candidate_commit, str):
            raise ContractError("candidate commit binding required")
        if not self.config_fingerprint or not isinstance(self.config_fingerprint, str):
            raise ContractError("configuration fingerprint binding required")
        ids = [f.control_id for f in self.findings]
        if ids != sorted(ids):
            raise ContractError("findings must be in stable sorted order")
        if self.matrix_version != MATRIX_VERSION:
            raise ContractError(f"unsupported matrix version: {self.matrix_version!r}")

    @property
    def blockers(self) -> Tuple[str, ...]:
        return tuple(f.control_id for f in self.findings
                     if f.mandatory and f.state != "PASS")

    @property
    def failures(self) -> Tuple[str, ...]:
        return tuple(f.control_id for f in self.findings
                     if f.state == "FAIL")

    @property
    def conditionals(self) -> Tuple[str, ...]:
        return tuple(f.control_id for f in self.findings
                     if not f.mandatory and f.state != "PASS")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "matrix_version": self.matrix_version,
            "candidate_commit": self.candidate_commit,
            "config_fingerprint": self.config_fingerprint,
            "verdict": self.verdict,
            "approval_state": self.approval_state,
            "blockers": list(self.blockers),
            "conditionals": list(self.conditionals),
            "findings": [f.to_dict() for f in self.findings],
            "attestation": attestation_hash(self),
        }


def evaluate_matrix(matrix: LaunchMatrix,
                    candidate_commit: str,
                    config_fingerprint: str) -> EvaluationResult:
    """Evaluate the matrix against a launch candidate binding.

    Fail closed: a malformed or incomplete matrix raises; every
    control without valid, commit-and-config-bound evidence is
    BLOCKED.
    """
    validate_matrix(matrix)
    if not candidate_commit or not isinstance(candidate_commit, str):
        raise ContractError("candidate_commit required")
    if not config_fingerprint or not isinstance(config_fingerprint, str):
        raise ContractError("config_fingerprint required")

    findings = []
    for control in sorted(matrix.controls, key=lambda c: c.control_id):
        # Bind the control's evidence to THIS candidate explicitly.
        bound: ControlRecord = replace(
            control,
            expected_commit=candidate_commit,
            expected_fingerprint=config_fingerprint,
        )
        state, reason = evaluate_control(bound)
        findings.append(Finding(
            control_id=control.control_id,
            domain=control.domain,
            state=state,
            severity=control.severity,
            mandatory=control.mandatory,
            reason=reason,
            remediation=control.remediation,
            evidence_reference=(control.evidence.reference
                                if control.evidence else ""),
        ))

    mandatory_bad = [f for f in findings
                     if f.mandatory and f.state != "PASS"]
    nonmandatory_bad = [f for f in findings
                        if not f.mandatory and f.state != "PASS"]
    if mandatory_bad:
        verdict = "NO_GO"
    elif nonmandatory_bad:
        verdict = "CONDITIONAL_GO"
    else:
        verdict = "GO"

    return EvaluationResult(
        matrix_version=matrix.version,
        candidate_commit=candidate_commit,
        config_fingerprint=config_fingerprint,
        verdict=verdict,
        findings=tuple(findings),
    )


def attestation_hash(result: EvaluationResult) -> str:
    """SHA-256 over the canonical JSON of the attestation inputs.

    Deterministic: identical inputs ⇒ identical hash. Covers matrix
    version, candidate commit, config fingerprint, evidence
    references, findings (id/state/reason), verdict, approval state.
    """
    payload = {
        "matrix_version": result.matrix_version,
        "candidate_commit": result.candidate_commit,
        "config_fingerprint": result.config_fingerprint,
        "verdict": result.verdict,
        "approval_state": result.approval_state,
        "evidence_references": sorted(
            f.evidence_reference for f in result.findings
            if f.evidence_reference),
        "findings": [
            {"control_id": f.control_id, "state": f.state,
             "reason": f.reason}
            for f in result.findings
        ],
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def render_report(result: EvaluationResult) -> str:
    """Human-readable report generated from the SAME canonical result."""
    lines = [
        "# Launch Readiness Attestation",
        "",
        f"- Matrix: {result.matrix_version}",
        f"- Candidate commit: {result.candidate_commit}",
        f"- Configuration fingerprint: {result.config_fingerprint}",
        f"- Verdict: **{result.verdict}**",
        f"- Approval state: {result.approval_state}",
        f"- Attestation: `{attestation_hash(result)}`",
        "",
        "| Control | Domain | Severity | Mandatory | State | Reason |",
        "|---|---|---|---|---|---|",
    ]
    for f in result.findings:
        lines.append(
            f"| {f.control_id} | {f.domain} | {f.severity} "
            f"| {'yes' if f.mandatory else 'no'} | {f.state} "
            f"| {f.reason} |")
    if result.blockers:
        lines += ["", "## Blockers", ""]
        by_id = {f.control_id: f for f in result.findings}
        for cid in result.blockers:
            lines.append(f"- `{cid}` — {by_id[cid].remediation}")
    if result.verdict == "CONDITIONAL_GO":
        lines += ["", "CONDITIONAL_GO is valid ONLY for explicitly "
                  "declared limited-scope activation; it never "
                  "authorizes full production silently."]
    lines += ["", "A technical GO is necessary but NOT sufficient — "
              "explicit owner approval remains mandatory before any "
              "production activation."]
    return "\n".join(lines) + "\n"

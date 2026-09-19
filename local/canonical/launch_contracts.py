"""Phase 26 M1 — launch readiness contracts (D-137/D-138).

Pure, dependency-free shapes and rules for the launch control matrix
and its fail-closed evaluation. No I/O, no wall clock: validity is
declared logical state supplied by the caller (D-085/D-086/D-093/D-121
precedent). Every unknown, missing, stale, malformed, or
contradictory input evaluates to BLOCKED — never a silent pass
(owner ruling on D-137).

Composes existing surfaces (never duplicates them): control ids
follow the nine MASTER_PLAN launch domains; redaction follows the
D-124 minimal-style; fingerprints are SHA-256 over canonical JSON;
matrix + evaluator follow the closed-tuple / strict-validator house
style (Phases 12/19/22).
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

__all__ = [
    "MATRIX_VERSION",
    "CONTROL_DOMAINS",
    "SEVERITIES",
    "CONTROL_STATES",
    "EVIDENCE_KINDS",
    "VERDICTS",
    "ContractError",
    "ControlState",
    "EvidenceKind",
    "EvidenceRecord",
    "ControlRecord",
    "validate_evidence",
    "evaluate_control",
    "configuration_fingerprint",
    "REDACTION_PATTERNS",
    "redact_text",
    "build_matrix",
    "validate_matrix",
]

MATRIX_VERSION = "launch.matrix.v1"

CONTROL_DOMAINS = (
    "security", "backup", "payment", "inventory",
    "shipping", "monitoring", "escalation", "e2e", "recovery",
)
SEVERITIES = ("critical", "high", "medium")
CONTROL_STATES = ("PASS", "FAIL", "BLOCKED", "NOT_APPLICABLE")
EVIDENCE_KINDS = (
    "commit_bound",        # regenerated on any source change
    "config_bound",        # regenerated on config-fingerprint change
    "logically_expiring",  # stale past a declared logical horizon
    "human_attested",      # owner-role attestation, audited
)
VERDICTS = ("GO", "CONDITIONAL_GO", "NO_GO")

_UNSET = object()


class ContractError(ValueError):
    """Contract-level misuse (bad domain, bad state, malformed row)."""


# ---------------------------------------------------------------------------
# Minimal D-124-style redaction for evidence material
# ---------------------------------------------------------------------------

REDACTION_PATTERNS: Tuple[Tuple[str, str], ...] = (
    (r"(?i)\b(?:bearer\s+)[A-Za-z0-9._~+/-]{8,}", "Bearer [REDACTED]"),
    (r"(?i)\b(postgres(?:ql)?|mysql|redis|mongodb)://[^\s/@]+:[^\s/@]+@",
     r"\1://[REDACTED]@"),
    (r"(?i)\b(sk|pk)_(?:live|test)_[A-Za-z0-9]{10,}", "[REDACTED_KEY]"),
    (r"(?i)\b(api[_-]?key|secret|token|password)\s*[=:]\s*\S+",
     r"\1=[REDACTED]"),
    (r"\b[0-9a-f]{64}\b", "[REDACTED_HEX64]"),
)


def redact_text(text: str) -> str:
    """Apply the minimal D-124-style pattern set to free text."""
    out = text
    for pattern, repl in REDACTION_PATTERNS:
        out = re.sub(pattern, repl, out)
    return out


def _redact_value(value: Any) -> Any:
    """Recursive redaction of strings inside evidence values."""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {k: _redact_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact_value(v) for v in value]
    return value


# ---------------------------------------------------------------------------
# Evidence & control records
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EvidenceRecord:
    """One evidence artifact bound to a control.

    `valid` is the CALLER'S declared validity verdict (computed from
    logical state elsewhere — never wall clock in this module).
    `detail` is redacted on construction (D-124).
    """
    evidence_id: str
    kind: str                    # one of EVIDENCE_KINDS
    commit: str                  # candidate commit the evidence binds to
    config_fingerprint: str      # configuration fingerprint it binds to
    reference: str               # where the evidence lives (path, id)
    valid: bool                  # declared validity (fresh, unexpired…)
    outcome: str = "positive"    # "positive" or "negative" measurement
    detail: str = ""             # free text — redacted (D-124)

    def __post_init__(self) -> None:
        if not self.evidence_id or not isinstance(self.evidence_id, str):
            raise ContractError("evidence_id must be a non-empty string")
        if self.kind not in EVIDENCE_KINDS:
            raise ContractError(f"unknown evidence kind: {self.kind!r}")
        if not isinstance(self.commit, str) or not self.commit:
            raise ContractError("evidence commit binding required")
        if not isinstance(self.config_fingerprint, str):
            raise ContractError("evidence config_fingerprint must be a string")
        if not isinstance(self.reference, str) or not self.reference:
            raise ContractError("evidence reference required")
        if not isinstance(self.valid, bool):
            raise ContractError("evidence valid must be boolean")
        if self.outcome not in ("positive", "negative"):
            raise ContractError(
                "evidence outcome must be 'positive' or 'negative'")
        object.__setattr__(self, "detail", redact_text(self.detail or ""))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "evidence_id": self.evidence_id, "kind": self.kind,
            "commit": self.commit, "config_fingerprint": self.config_fingerprint,
            "reference": self.reference, "valid": self.valid,
            "outcome": self.outcome, "detail": self.detail,
        }


@dataclass(frozen=True)
class ControlRecord:
    """One launch control (D-137).

    `mandatory=False` failures do not block a GO — they surface as
    findings that may permit CONDITIONAL_GO instead (D-138).
    """
    control_id: str              # stable, e.g. "SEC-001"
    domain: str                  # one of CONTROL_DOMAINS
    title: str
    owner_role: str              # role, never a hard-coded identity
    severity: str                # one of SEVERITIES
    mandatory: bool
    remediation: str = ""
    evidence: Optional[EvidenceRecord] = None
    expected_commit: str = ""    # candidate commit this control targets
    expected_fingerprint: str = ""  # config fingerprint this control targets

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Z0-9]{3}-\d{3}", self.control_id or ""):
            raise ContractError(
                f"control_id must look like 'SEC-001', got {self.control_id!r}")
        prefix = self.control_id.split("-", 1)[0]
        if prefix != self.domain[:3].upper():
            raise ContractError(
                f"control_id prefix {prefix!r} does not match domain "
                f"{self.domain!r}")
        if self.domain not in CONTROL_DOMAINS:
            raise ContractError(f"unknown domain: {self.domain!r}")
        if not self.title or not isinstance(self.title, str):
            raise ContractError("control title required")
        if not self.owner_role or not isinstance(self.owner_role, str):
            raise ContractError("owner_role required (role, not identity)")
        if self.severity not in SEVERITIES:
            raise ContractError(f"unknown severity: {self.severity!r}")
        if not isinstance(self.mandatory, bool):
            raise ContractError("mandatory must be boolean")
        if self.evidence is not None and not isinstance(self.evidence, EvidenceRecord):
            raise ContractError("evidence must be an EvidenceRecord")


# ---------------------------------------------------------------------------
# Fail-closed evaluation (D-137)
# ---------------------------------------------------------------------------

def validate_evidence(evidence: EvidenceRecord, control: ControlRecord) -> ControlState:
    """Bind evidence to the control's declared commit + fingerprint.

    Fail closed: any mismatch or invalidity is BLOCKED, never PASS.
    """
    if control.expected_commit and evidence.commit != control.expected_commit:
        return "BLOCKED"
    if (control.expected_fingerprint
            and evidence.config_fingerprint != control.expected_fingerprint):
        return "BLOCKED"
    return "PASS" if evidence.valid else "BLOCKED"


def evaluate_control(control: ControlRecord) -> Tuple[ControlState, str]:
    """Evaluate one control. Returns (state, reason).

    Fail closed (owner ruling): missing evidence, invalid evidence,
    commit/config mismatch — all BLOCKED with a stable reason string.
    Evidence that is present, bound, and fresh but records a NEGATIVE
    measurement is a FAIL (not a pass, not a skip).
    """
    if control.evidence is None:
        return "BLOCKED", "missing evidence"
    state = validate_evidence(control.evidence, control)
    if state == "BLOCKED":
        if (control.expected_commit
                and control.evidence.commit != control.expected_commit):
            return "BLOCKED", "evidence commit mismatch"
        if (control.expected_fingerprint
                and control.evidence.config_fingerprint
                != control.expected_fingerprint):
            return "BLOCKED", "evidence configuration mismatch"
        return "BLOCKED", "evidence invalid or expired"
    if control.evidence.outcome == "negative":
        return "FAIL", "evidence records a negative outcome"
    return "PASS", "evidence valid and bound"


# ---------------------------------------------------------------------------
# Configuration fingerprint (secrets excluded, D-124)
# ---------------------------------------------------------------------------

_SECRET_KEY_RE = re.compile(
    r"(?i)(?:secret|password|passwd|token|api[_-]?key|credential|private[_-]?key)")


def configuration_fingerprint(config: Dict[str, Any]) -> str:
    """SHA-256 over the canonical JSON of NON-SECRET config entries.

    Secret-keyed entries are excluded entirely (never hashed, never
    emitted); list inputs inside values are sorted for canonicality.
    """
    safe: Dict[str, Any] = {}
    for key in sorted(config):
        if _SECRET_KEY_RE.search(key):
            continue
        value = config[key]
        if isinstance(value, (list, tuple)):
            value = sorted(value, key=lambda v: json.dumps(v, sort_keys=True))
        safe[key] = value
    blob = json.dumps(safe, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Canonical control matrix (D-137)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MatrixControlSpec:
    control_id: str
    domain: str
    title: str
    owner_role: str
    severity: str
    mandatory: bool
    remediation: str


@dataclass(frozen=True)
class LaunchMatrix:
    version: str
    controls: Tuple[ControlRecord, ...]
    fingerprint: str = field(default="")

    def control(self, control_id: str) -> ControlRecord:
        for c in self.controls:
            if c.control_id == control_id:
                return c
        raise ContractError(f"unknown control: {control_id!r}")


def build_matrix(specs: Tuple[MatrixControlSpec, ...]) -> LaunchMatrix:
    """Build a matrix from declared specs (no evidence attached yet)."""
    controls = tuple(
        ControlRecord(
            control_id=s.control_id, domain=s.domain, title=s.title,
            owner_role=s.owner_role, severity=s.severity,
            mandatory=s.mandatory, remediation=s.remediation,
        )
        for s in specs
    )
    return LaunchMatrix(version=MATRIX_VERSION, controls=controls)


def validate_matrix(matrix: LaunchMatrix) -> LaunchMatrix:
    """Structural completeness gate for a declared matrix.

    Fail closed: duplicate ids, domain/id-prefix mismatches, missing
    mandatory fields — all raise. Returns the matrix unchanged.
    """
    if matrix.version != MATRIX_VERSION:
        raise ContractError(f"unsupported matrix version: {matrix.version!r}")
    if not matrix.controls:
        raise ContractError("matrix must declare at least one control")
    seen = set()
    for c in matrix.controls:
        if c.control_id in seen:
            raise ContractError(f"duplicate control id: {c.control_id}")
        seen.add(c.control_id)
        # Re-validate via the dataclass contract (raises on any defect).
        ControlRecord(
            control_id=c.control_id, domain=c.domain, title=c.title,
            owner_role=c.owner_role, severity=c.severity,
            mandatory=c.mandatory, remediation=c.remediation,
        )
    domains = {c.domain for c in matrix.controls}
    missing = [d for d in CONTROL_DOMAINS if d not in domains]
    if missing:
        raise ContractError(f"matrix missing domains: {missing}")
    return matrix

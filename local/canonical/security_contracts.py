"""Phase 20 M1 — security contracts & threat model (D-113/D-114).

Pure shapes and rules for the security hardening layer:

  - Threat taxonomy (D-113): six canonical categories mapped to the
    phase surfaces they target. Every `SecurityControl` names its
    module AND its test artifact — the registry is battery-verified:
    NO CONTROL WITHOUT A TEST.
  - `HardeningPolicy` (D-114): the numeric bounds the
    InputHardeningGate enforces (payload bytes, string lengths, JSON
    depth/width, id charset).
  - `HardeningAuditRecord` (D-113): the durable record of a
    hardening-relevant event (gate rejection, attestation check,
    rate-limit hit, lockout) — appended to `security.hardening_audit`
    by the engine.

No network, no wall clock, no randomness.
"""

import json
from typing import Dict, Optional, Tuple

# --- threat taxonomy (D-113) -----------------------------------------------------

T_CREDENTIAL_LEAKAGE = "credential_leakage"
T_REPLAY_ATTACK = "replay_attack"
T_LEDGER_TAMPERING = "ledger_tampering"
T_RACE_INJECTION = "race_condition_injection"
T_MALFORMED_PAYLOAD = "oversized_malformed_payload"
T_ERROR_PROBING = "enumeration_via_error_surfaces"

THREAT_CATEGORIES = (T_CREDENTIAL_LEAKAGE, T_REPLAY_ATTACK,
                     T_LEDGER_TAMPERING, T_RACE_INJECTION,
                     T_MALFORMED_PAYLOAD, T_ERROR_PROBING)


class SecurityContractError(Exception):
    """Class-B rejection — invalid policy/record before any durable
    write."""


# --- control registry (D-113: no control without a test) ---------------------------

def control(control_id: str, threat: str, phase: str, module: str,
            test_artifact: str, description: str) -> Dict:
    if threat not in THREAT_CATEGORIES:
        raise SecurityContractError(
            f"threat category must be one of {sorted(THREAT_CATEGORIES)}")
    if not control_id or not module or not test_artifact:
        raise SecurityContractError(
            "a control MUST name its module and test artifact "
            "(no untested claims, D-113)")
    return {"control_id": control_id, "threat": threat,
            "phase": phase, "module": module,
            "test_artifact": test_artifact,
            "description": description}


SECURITY_CONTROLS: Tuple[Dict, ...] = (
    control("ctl-credential-scan", T_CREDENTIAL_LEAKAGE, "D-045/20",
            "canonical/security_worker.py", 
            "test_phase20_security.TestM4Sweep::test_entropy_scan_clean",
            "repository-wide secret-entropy scan, battery-executed"),
    control("ctl-ast-sweep", T_CREDENTIAL_LEAKAGE, "D-116",
            "canonical/security_worker.py",
            "test_phase20_security.TestM4Sweep::test_extended_ast_sweep_clean",
            "extended AST detectors over canonical modules"),
    control("ctl-replay-burn", T_REPLAY_ATTACK, "19/D-115",
            "canonical/admin_engine.py",
            "test_phase20_security.TestM3RateLimit::test_key_forge_resistant",
            "single-use per-VALUE confirmation keys, chain-anchored burns"),
    control("ctl-chain-attestation", T_LEDGER_TAMPERING, "18/19/D-115",
            "canonical/security_engine.py",
            "test_phase20_security.TestM2Attestation::test_attestation_detects_tamper",
            "chain-head attestations with O(1) verification"),
    control("ctl-exactly-once-locks", T_RACE_INJECTION,
            "12/15/17/18/19", "per-phase engines",
            "per-phase 8-thread race tests",
            "PK-as-lock claims + D-027 exactly-once guards"),
    control("ctl-input-gate", T_MALFORMED_PAYLOAD, "D-114",
            "canonical/security_engine.py",
            "test_phase20_security.TestM2Gate",
            "InputHardeningGate: size/charset/depth/canonicalization"),
    control("ctl-error-taxonomy", T_ERROR_PROBING, "5..19",
            "canonical/security_engine.py",
            "test_phase20_security.TestM2Gate::test_error_surface_discipline",
            "uniform Class-B errors without internals disclosure"),
)


def validate_registry(registry=SECURITY_CONTROLS) -> Dict[str, int]:
    """Battery-verified registry invariant: every threat category has
    at least one control; every control names a test artifact."""
    by_threat: Dict[str, int] = {}
    for c in registry:
        by_threat[c["threat"]] = by_threat.get(c["threat"], 0) + 1
    missing = [t for t in THREAT_CATEGORIES if t not in by_threat]
    if missing:
        raise SecurityContractError(
            f"threat categories without controls: {missing}")
    return by_threat


# --- hardening policy (D-114) ---------------------------------------------------------

MAX_PAYLOAD_BYTES = 64 * 1024          # 64 KiB default payload cap
MAX_STRING_LEN = 512                   # any single validated string
MAX_JSON_DEPTH = 8                     # nested object/array depth
MAX_JSON_WIDTH = 64                    # keys/elements per level
MAX_LIST_ITEMS = 256                   # flat list length cap

# printable + control-free ASCII-plus-TAB/LF discipline for ids/refs;
# non-ASCII must pass the confusable check before use
_FORBIDDEN_CHARS = set("\x00\x01\x02\x03\x04\x05\x06\x07\x08\x0b\x0c"
                       "\x0e\x0f\x1f\x7f")


class HardeningPolicy:
    """Numeric bounds for the gate (D-114). Instantiated once per
    entry-point family; overridable per call."""

    def __init__(self, max_payload_bytes: int = MAX_PAYLOAD_BYTES,
                 max_string_len: int = MAX_STRING_LEN,
                 max_json_depth: int = MAX_JSON_DEPTH,
                 max_json_width: int = MAX_JSON_WIDTH,
                 max_list_items: int = MAX_LIST_ITEMS):
        self.max_payload_bytes = max_payload_bytes
        self.max_string_len = max_string_len
        self.max_json_depth = max_json_depth
        self.max_json_width = max_json_width
        self.max_list_items = max_list_items

    def to_dict(self) -> Dict:
        return {"max_payload_bytes": self.max_payload_bytes,
                "max_string_len": self.max_string_len,
                "max_json_depth": self.max_json_depth,
                "max_json_width": self.max_json_width,
                "max_list_items": self.max_list_items}


DEFAULT_POLICY = HardeningPolicy()


def validate_policy(policy: Dict) -> Dict:
    """A policy dict is Class-B if any bound is non-positive or
    non-integer."""
    bounds = ("max_payload_bytes", "max_string_len", "max_json_depth",
              "max_json_width", "max_list_items")
    if not isinstance(policy, dict):
        raise SecurityContractError("policy must be a dict")
    for b in bounds:
        v = policy.get(b)
        if v is None:
            continue
        if not isinstance(v, int) or isinstance(v, bool) or v <= 0:
            raise SecurityContractError(
                f"{b} must be a positive integer")
    return policy


# --- hardening audit record (D-113/D-115) ------------------------------------------------

RECORD_KINDS = ("gate_rejection", "attestation_check",
                "rate_limit_hit", "actor_lockout", "key_burn")


def validate_record(record: Dict) -> Dict:
    if not isinstance(record, dict):
        raise SecurityContractError("record must be a dict")
    missing = [k for k in ("record_kind", "subject", "actor",
                           "logical_at") if k not in record]
    if missing:
        raise SecurityContractError(
            f"record missing required fields: {sorted(missing)}")
    if record["record_kind"] not in RECORD_KINDS:
        raise SecurityContractError(
            f"record_kind must be one of {sorted(RECORD_KINDS)}")
    for k in ("subject", "actor", "logical_at"):
        if not isinstance(record[k], str) or not record[k]:
            raise SecurityContractError(f"{k} must be a non-empty string")
    return record


def record_to_json(record: Dict) -> str:
    return json.dumps(validate_record(record), ensure_ascii=False,
                      sort_keys=True)

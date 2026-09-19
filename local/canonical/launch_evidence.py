"""Phase 26 M2/M4 — evidence collectors, canonical matrix, evidence
pack (D-137/D-140).

Pure composition of EXISTING measured surfaces: callers run the real
checks (Phase 20 sweeps, D-123 probes, D-125 restore rehearsal, the
test battery) and hand the results in — this module maps results to
EvidenceRecords (redacted, commit/config-bound), assembles the
canonical nine-domain matrix, and renders the evidence pack from ONE
canonical result. No subprocess, no wall clock, no I/O.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from .launch_contracts import (
    MATRIX_VERSION,
    ContractError,
    EvidenceRecord,
    LaunchMatrix,
    MatrixControlSpec,
    build_matrix,
    configuration_fingerprint,
    redact_text,
    validate_matrix,
)
from .launch_evaluator import EvaluationResult, evaluate_matrix

__all__ = [
    "ROLE_VOCABULARY",
    "EvidenceCollector",
    "validate_escalation_config",
    "canonical_matrix",
    "evaluate_candidate",
    "build_evidence_pack",
    "render_evidence_pack",
]

ROLE_VOCABULARY = ("owner", "admin", "ops_lead", "sre", "qa_lead",
                   "security_engineer", "backup_operator")


def validate_escalation_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """ESC-domain check (D-137): escalation routing is ROLE
    configuration with runbook references — never hard-coded
    identities. Deterministic verdict."""
    roles = cfg.get("escalation_roles")
    if not isinstance(roles, dict) or not roles:
        return {"ok": False, "reason": "escalation_roles missing or empty"}
    unknown = [r for r in roles if r not in ROLE_VOCABULARY]
    if unknown:
        return {"ok": False, "reason": f"roles outside vocabulary: {sorted(unknown)}"}
    for role, spec in sorted(roles.items()):
        if not isinstance(spec, dict) or not spec.get("runbook"):
            return {"ok": False, "reason": f"role {role!r} lacks a runbook reference"}
        if "identity" in spec or "email" in spec or "phone" in spec:
            return {"ok": False,
                    "reason": f"role {role!r} carries identity fields (use roles)"}
    return {"ok": True, "reason": "roles configured with runbooks"}


class EvidenceCollector:
    """Maps measured check results into commit/config-bound evidence.

    `ok=False` yields a NEGATIVE outcome (a real FAIL), never a pass;
    `present=False` yields NO evidence (the control evaluates BLOCKED).
    """

    def __init__(self, commit: str, config: Dict[str, Any]):
        if not commit or not isinstance(commit, str):
            raise ContractError("collector requires the candidate commit")
        self.commit = commit
        self.config = dict(config)
        self.fingerprint = configuration_fingerprint(self.config)

    def _record(self, evidence_id: str, kind: str, ok: bool,
                reference: str, detail: str) -> EvidenceRecord:
        return EvidenceRecord(
            evidence_id=evidence_id, kind=kind, commit=self.commit,
            config_fingerprint=self.fingerprint, reference=reference,
            valid=True, outcome=("positive" if ok else "negative"),
            detail=detail)

    def sweep_evidence(self, ast_report: Dict, entropy_report: Dict,
                       bounds_report: Dict) -> EvidenceRecord:
        """SEC-001: Phase 20 sweeps clean (commit-bound)."""
        ast_clean = (not ast_report.get("findings")
                     and not ast_report.get("style"))
        entropy_clean = not entropy_report.get("flagged")
        bounds_ok = not bounds_report.get("missing")
        return self._record(
            "EV-SEC-001", "commit_bound",
            bool(ast_clean and entropy_clean and bounds_ok),
            "phase20-sweeps",
            f"ast={ast_report.get('files_scanned', 0)} "
            f"entropy={entropy_report.get('files_scanned', 0)}")

    def restore_rehearsal_evidence(self, write_ok: bool,
                                   verify_ok: bool,
                                   detail: str = "write+verify snapshot "
                                                 "rehearsal") -> EvidenceRecord:
        """BAC-001: a backup counts ONLY after a successful restore —
        verified-freeze write + attested verification (D-125). The
        operator resilience drill supplies its structured outcome as
        `detail` when this evidence comes from a real rehearsal."""
        return self._record(
            "EV-BAC-001", "commit_bound", bool(write_ok and verify_ok),
            "d125-verified-freeze-rehearsal",
            detail)

    def gate_config_evidence(self, evidence_id: str, key: str,
                             reference: str) -> Optional[EvidenceRecord]:
        """Config-gated controls (PAY capture, SHP purchase, kill
        switch availability): the gate key MUST be explicitly False in
        configuration — absent means BLOCKED (no evidence), True means
        a negative outcome (the gate is OPEN — a launch hazard)."""
        if key not in self.config:
            return None  # missing evidence → BLOCKED (fail closed)
        gate_open = bool(self.config[key])
        return self._record(evidence_id, "config_bound", not gate_open,
                            reference, f"{key}={self.config[key]}")

    def battery_evidence(self, evidence_id: str, reference: str,
                         *, battery_ok: bool, census_ok: bool,
                         ladder_ok: bool) -> EvidenceRecord:
        """E2E/REC/INV controls: committed battery + census + ladder
        results bound to the candidate commit."""
        return self._record(
            evidence_id, "commit_bound",
            bool(battery_ok and census_ok and ladder_ok),
            reference, "battery+census+ladder")

    def monitoring_evidence(self, health_report: Dict) -> EvidenceRecord:
        """MON-001: D-123 qa.health_report.v1 verdicts all green."""
        probes = health_report.get("probes", {})
        bad = [n for n, p in probes.items()
               if str(p.get("verdict", "")).upper() != "PASS"]
        return self._record(
            "EV-MON-001", "logically_expiring", not bad,
            "d123-health-report",
            f"probes={len(probes)} failing={sorted(bad)}")

    def escalation_evidence(self, cfg: Dict[str, Any]) -> EvidenceRecord:
        """ESC-001: role-based escalation configuration."""
        verdict = validate_escalation_config(cfg)
        return self._record(
            "EV-ESC-001", "config_bound", bool(verdict["ok"]),
            "escalation-config", verdict["reason"])


def canonical_matrix(collector: EvidenceCollector, *,
                     ast_report: Dict, entropy_report: Dict,
                     bounds_report: Dict, restore_ok: bool,
                     probes_report: Dict, escalation_cfg: Dict,
                     battery_ok: bool, census_ok: bool,
                     ladder_ok: bool,
                     drill_result: Optional[Dict] = None,
                     ledger_consistency: Optional[Dict] = None,
                     require_dr_evidence: bool = False) -> LaunchMatrix:
    """The canonical nine-domain control matrix with evidence bound
    from the measured results (D-137)."""
    specs = (
        MatrixControlSpec("SEC-001", "security", "Phase 20 sweeps clean",
                          "security_engineer", "critical", True,
                          "re-run ast/entropy/bounds sweeps"),
        MatrixControlSpec("BAC-001", "backup", "Restore rehearsal succeeded",
                          "backup_operator", "critical", True,
                          "rehearse verified-freeze write+verify"),
        MatrixControlSpec("PAY-001", "payment", "Capture gated off",
                          "owner", "critical", True,
                          "set payment_capture_enabled=false"),
        MatrixControlSpec("INV-001", "inventory", "Oversell prevention proven",
                          "ops_lead", "critical", True,
                          "re-run Phase 12/25 batteries"),
        MatrixControlSpec("SHI-001", "shipping", "Purchase gated off",
                          "ops_lead", "high", True,
                          "set shipping_purchase_enabled=false"),
        MatrixControlSpec("MON-001", "monitoring", "Health probes green",
                          "sre", "critical", True,
                          "re-run D-123 probes"),
        MatrixControlSpec("ESC-001", "escalation", "Role escalation configured",
                          "owner", "high", True,
                          "declare escalation roles + runbooks"),
        MatrixControlSpec("E2E-001", "e2e", "Phase 25 flow green",
                          "qa_lead", "critical", True,
                          "re-run Phase 25 suite"),
        MatrixControlSpec("REC-001", "recovery", "Recovery evidence fresh",
                          "qa_lead", "critical", True,
                          "re-run D-135 reconciliation battery"),
    )
    pay = collector.gate_config_evidence(
        "EV-PAY-001", "payment_capture_enabled", "launch-config")
    shp = collector.gate_config_evidence(
        "EV-SHI-001", "shipping_purchase_enabled", "launch-config")
    # BAC-001 from the operator resilience drill when a structured
    # drill result is supplied (real rehearsal evidence, D-140): the
    # write gate is stages 1-2, the verify gate stages 2+4, and the
    # overall verdict must hold — any failed stage is NEGATIVE
    # evidence (fail closed), never a pass.
    if drill_result is not None:
        stage_ok = {s["index"]: bool(s["ok"])
                    for s in drill_result.get("stages", ())}
        write_ok = all(stage_ok.get(i, False) for i in (1, 2))
        verify_ok = all(stage_ok.get(i, False) for i in (2, 4))
        bac_ok = bool(drill_result.get("ok")) and write_ok and verify_ok
        restore_ok = bac_ok
        # provenance: carry the drill's own evidence detail (e.g.
        # "operator drill: 6/6 stages ok") when present — callers
        # assert the drill source flows into the matrix record.
        bac_detail = str(
            (drill_result.get("evidence") or {}).get("detail")
            or ("transactional drill "
                + str(drill_result.get("verdict", "UNKNOWN"))))
    else:
        bac_ok = restore_ok
        bac_detail = "write+verify snapshot rehearsal"

    # D-138 launch-gate binding (owner directive): a production GO
    # requires BOTH a fresh green transactional restore drill AND a
    # fresh green decision-ledger consistency pass. Under
    # require_dr_evidence the absence of either leg is NOT a pass:
    # no drill result at all → BAC-001 BLOCKED (missing evidence);
    # a drill result with a missing or failed consistency leg →
    # NEGATIVE outcome (FAIL). Fail closed, per D-137.
    if require_dr_evidence:
        cons_ok = bool(ledger_consistency
                       and ledger_consistency.get("ok"))
        if drill_result is None:
            bac_ok = False
            bac_detail = ("transactional drill MISSING; ledger "
                          "consistency "
                          + (str(ledger_consistency.get("reason"))
                             if ledger_consistency else "MISSING"))
        else:
            bac_ok = bac_ok and cons_ok
            # the evidence record must carry the COMBINED verdict: a
            # drill result with a missing or failed consistency leg
            # is NEGATIVE evidence (fail closed), never a pass —
            # restore_ok is the field the BAC-001 record is built
            # from, so it must move in lockstep with bac_ok here.
            restore_ok = bac_ok
            bac_detail = (
                "transactional drill "
                f"{drill_result.get('verdict', 'UNKNOWN')}; ledger "
                "consistency "
                + (str(ledger_consistency.get("reason"))
                   if ledger_consistency else "MISSING"))
        if drill_result is None and ledger_consistency is None:
            # no evidence at all for the recovery control → BLOCKED
            restore_ok = None
    evidence = {
        "SEC-001": collector.sweep_evidence(ast_report, entropy_report, bounds_report),
        "BAC-001": (None if require_dr_evidence and drill_result is None
                    else collector.restore_rehearsal_evidence(
                        bool(restore_ok), bool(restore_ok),
                        detail=bac_detail)),
        "PAY-001": pay,
        "INV-001": collector.battery_evidence(
            "EV-INV-001", "phase12-battery", battery_ok=battery_ok,
            census_ok=census_ok, ladder_ok=ladder_ok),
        "SHI-001": shp,
        "MON-001": collector.monitoring_evidence(probes_report),
        "ESC-001": collector.escalation_evidence(escalation_cfg),
        "E2E-001": collector.battery_evidence(
            "EV-E2E-001", "phase25-suite", battery_ok=battery_ok,
            census_ok=census_ok, ladder_ok=ladder_ok),
        "REC-001": collector.battery_evidence(
            "EV-REC-001", "phase25-reconciliation", battery_ok=battery_ok,
            census_ok=census_ok, ladder_ok=ladder_ok),
    }
    from dataclasses import replace
    controls = tuple(
        replace(c, evidence=evidence.get(c.control_id)) for c in build_matrix(specs).controls)
    return validate_matrix(LaunchMatrix(version=MATRIX_VERSION, controls=controls))


def evaluate_candidate(matrix: LaunchMatrix, commit: str,
                       fingerprint: str) -> EvaluationResult:
    """Bind + evaluate the matrix against the exact candidate."""
    return evaluate_matrix(matrix, commit, fingerprint)


def build_evidence_pack(result: EvaluationResult, *,
                        battery_summary: Dict[str, Any],
                        census: Dict[str, Any],
                        ladder: Dict[str, Any],
                        restore_rehearsal: Dict[str, Any],
                        monitoring: Dict[str, Any],
                        approval_state: str = "NONE") -> Dict[str, Any]:
    """The D-140 operational evidence pack — generated from canonical
    results only, secrets redacted at construction time."""
    by_id = {f.control_id: f for f in result.findings}
    return {
        "schema": "launch.evidence_pack.v1",
        "candidate_commit": result.candidate_commit,
        "config_fingerprint": result.config_fingerprint,
        "matrix_version": result.matrix_version,
        "verdict": result.verdict,
        "approval_state": approval_state,
        "attestation": result.to_dict()["attestation"],
        "controls": {cid: {"state": f.state, "reason": f.reason,
                           "evidence": f.evidence_reference,
                           "severity": f.severity,
                           "mandatory": f.mandatory}
                     for cid, f in sorted(by_id.items())},
        "blockers": [
            {"control_id": cid,
             "remediation": by_id[cid].remediation}
            for cid in result.blockers],
        "backup_restore_rehearsal": restore_rehearsal,
        "monitoring_escalation": monitoring,
        "battery": battery_summary,
        "census": census,
        "ladder": ladder,
    }


def render_evidence_pack(pack: Dict[str, Any]) -> str:
    """Human-readable rendering of the SAME canonical pack."""
    lines = [
        "# Launch Evidence Pack",
        "",
        f"- Schema: {pack['schema']}",
        f"- Candidate commit: `{pack['candidate_commit']}`",
        f"- Config fingerprint: `{pack['config_fingerprint']}`",
        f"- Matrix: {pack['matrix_version']}",
        f"- Verdict: **{pack['verdict']}**",
        f"- Approval state: {pack['approval_state']}",
        f"- Attestation: `{pack['attestation']}`",
        "",
        "| Control | State | Evidence | Reason |",
        "|---|---|---|---|",
    ]
    for cid, c in pack["controls"].items():
        lines.append(f"| {cid} | {c['state']} | {c['evidence']} "
                     f"| {redact_text(c['reason'])} |")
    if pack["blockers"]:
        lines += ["", "## Blockers", ""]
        for b in pack["blockers"]:
            lines.append(f"- `{b['control_id']}` — {b['remediation']}")
    lines += ["", "## Battery", "",
              f"- battery_ok: {pack['battery'].get('ok')}",
              f"- census: {pack['census']}",
              f"- ladder: {pack['ladder']}",
              "", "## Backup / restore rehearsal", "",
              f"- {pack['backup_restore_rehearsal']}",
              "", "## Monitoring & escalation", "",
              f"- {pack['monitoring_escalation']}",
              "", "A technical GO is necessary but NOT sufficient — "
              "explicit one-time owner approval remains mandatory "
              "before any production activation."]
    return "\n".join(lines) + "\n"

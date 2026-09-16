"""Phase 11 M3 — reconciliation worker (D-080).

Boot/recovery scanner: audits every in-flight fan-out job against the
DURABLE store data only — no in-process cache is consulted or needed
(restart-safety invariant proven by the Phase 6/7 audit lineage).

For each non-terminal job it recomputes the deterministic aggregate
from the per-target outcomes recorded by the engine, then:

  - re-dispatches ONLY failing targets via the engine's
    retry_targets() (already-published targets are never re-triggered —
    D-080 retry isolation),
  - reports jobs whose targets are all terminal but whose aggregate
    event went missing (crash between outcome and aggregate),
  - NEVER mutates platform-level vaults (D-070/D-074 isolation:
    per-target idempotency stays owned by the Phase 9/10 publishers).
"""

import json
from typing import Dict, List, Optional

from canonical.orchestration_contracts import (
    aggregate_from_subtasks,
)
from canonical.orchestration_engine import (
    DISPATCHING,
    SOURCE_SYSTEM,
    FanOutEngine,
)

TERMINAL_AGGREGATES = ("SUCCESS", "PARTIAL_SUCCESS", "FAILED")


class ReconciliationReport:
    """Machine-readable scan outcome per job."""

    def __init__(self):
        self.terminal: List[str] = []      # job_ids already final
        self.in_flight: List[str] = []     # job_ids still dispatching
        self.recovered: Dict[str, Dict] = {}   # job_id → retry result
        self.repaired: Dict[str, str] = {}     # job_id → repaired aggregate
        self.anomalies: List[Dict] = []    # structural problems for HITL

    def as_dict(self) -> Dict:
        return {
            "terminal": list(self.terminal),
            "in_flight": list(self.in_flight),
            "recovered": dict(self.recovered),
            "repaired": dict(self.repaired),
            "anomalies": list(self.anomalies),
        }


class ReconciliationWorker:
    """D-080 boot/recovery scanner over one FanOutEngine."""

    def __init__(self, engine: FanOutEngine):
        self.engine = engine

    # -- scan helpers (durable data only) ---------------------------------

    def _jobs(self) -> Dict[str, Dict]:
        """job_id → latest lifecycle ref, from durable store refs.
        Reuses the engine's rank-aware reconstruction so each job is
        audited at its LATEST lifecycle stage."""
        jobs: Dict[str, Dict] = {}
        for ref in self.engine._store_refs():
            eid = str(ref.get("event_id", ""))
            if not eid.startswith("orchestration|"):
                continue
            parts = eid.split("|")
            # orchestration|<job>|<stage...>  (job ids have no pipes —
            # enforced by the D-077 job_id regex)
            if len(parts) >= 3:
                jobs.setdefault(parts[1], ref)
        # re-resolve each job at its latest stage (engine knows ranks)
        return {job: self.engine._job_ref(job) for job in jobs}

    def _outcomes_for(self, job_id: str) -> Dict[str, str]:
        return self.engine._prior_outcomes(job_id)

    # -- reconciliation -----------------------------------------------------

    def scan_and_recover(self, *, actor: str = "reconciler",
                         auto_retry: bool = True) -> Dict:
        """Scan every durable job; recover in-flight ones.

        auto_retry=True re-dispatches only failing targets (D-080).
        auto_retry=False is a dry audit pass (HITL review first).
        """
        report = ReconciliationReport()
        for job_id, ref in sorted(self._jobs().items()):
            stage = str(ref.get("stage") or "")
            if stage.startswith("aggregate"):
                agg = str(ref.get("aggregate") or "")
                if agg in TERMINAL_AGGREGATES:
                    report.terminal.append(job_id)
                    continue
                # terminal outcomes but aggregate event missing/old →
                # repair from per-target durable outcomes
                outcomes = self._outcomes_for(job_id)
                recomputed = aggregate_from_subtasks(outcomes)
                if recomputed in TERMINAL_AGGREGATES:
                    report.repaired[job_id] = recomputed
                    self.engine._record(
                        job_id,
                        f"aggregate|{self.engine._aggregate_seq(job_id)}",
                        dict(ref, outcomes=outcomes, aggregate=recomputed,
                             repaired_by=actor),
                        verdict=recomputed)
                    continue
                report.in_flight.append(job_id)
                if auto_retry:
                    failing = [t for t, o in outcomes.items()
                               if o not in ("published",
                                            "duplicate_publish_blocked",
                                            "cancelled")]
                    if failing:
                        report.recovered[job_id] = self.engine.retry_targets(
                            job_id, failing, actor=actor)
            elif stage == "dispatching":
                # crash before any aggregate event: aggregate from
                # durable outcomes
                outcomes = self._outcomes_for(job_id)
                recomputed = aggregate_from_subtasks(outcomes)
                if recomputed in TERMINAL_AGGREGATES:
                    report.repaired[job_id] = recomputed
                    self.engine._record(
                        job_id,
                        f"aggregate|{self.engine._aggregate_seq(job_id)}",
                        dict(ref, outcomes=outcomes, aggregate=recomputed,
                             repaired_by=actor),
                        verdict=recomputed)
                else:
                    report.in_flight.append(job_id)
                    if auto_retry:
                        failing = [t for t, o in outcomes.items()
                                   if o not in ("published",
                                                "duplicate_publish_blocked",
                                                "cancelled")]
                        if failing:
                            report.recovered[job_id] = (
                                self.engine.retry_targets(
                                    job_id, failing, actor=actor))
            elif stage == "routed":
                # routed but dispatch never started — leave for the
                # dispatcher; flag as in-flight for observability
                report.in_flight.append(job_id)
            else:
                report.anomalies.append({
                    "job_id": job_id,
                    "reason": f"unknown lifecycle stage {stage!r}",
                })
        return report.as_dict()

"""Phase 25 M1 — end-to-end flow conductor (D-133). Pure.

Runs the MASTER_PLAN §13 Phase 25 flow as ten declared stages with
every engine/adapter injected (RULES §35). Guarantees:

  - unbroken trace: one D-121 `TraceContext` root at lead capture;
    every stage emits through the shipped `LogLedger` emitter with
    `correlation_id` == the trace's causal id at that step;
  - zero schema mutation: `validate_envelope` rejects undeclared
    output keys at every stage boundary;
  - injected stage implementations bound to declared envelopes.

No I/O imports — usable in offline-hermetic tests as-is.
"""
from __future__ import annotations

from typing import Callable, Dict, List, Optional

from canonical.e2e_contracts import (
    STAGES, STAGE_ENVELOPES, ConductorError, StageEnvelope,
    check_context, validate_envelope,
)
from canonical.obs_contracts import LogLedger, TraceContext
from canonical.resilience import classify_by_message

__all__ = ["FlowConductor", "FlowResult"]


class FlowResult:
    """Outcome of one flow run: stage records + final context."""

    __slots__ = ("stages", "context", "outputs", "ok")

    def __init__(self, stages: List[Dict], context: Dict,
                 outputs: Dict, ok: bool):
        self.stages = stages
        self.context = context
        self.outputs = outputs
        self.ok = ok


class FlowConductor:
    """Ten declared stages; injected stage callables; one trace."""

    def __init__(self, ledger: LogLedger, stages: Dict[str, Callable],
                 *, logical_at: str = "2026-09-18T00:00:00+00:00"):
        if not isinstance(ledger, LogLedger):
            raise ConductorError("ledger must be a LogLedger (D-121)")
        missing = [s for s in STAGES if s not in stages]
        if missing:
            raise ConductorError(f"missing stage implementations: {missing}")
        unknown = set(stages) - set(STAGES)
        if unknown:
            raise ConductorError(f"unknown stages bound: {sorted(unknown)}")
        self.ledger = ledger
        self.stages = dict(stages)
        self.logical_at = logical_at

    def run(self, initial: Dict, *, trace: Optional[TraceContext] = None
            ) -> FlowResult:
        """Execute the full flow. `initial` seeds the flow context."""
        context = dict(initial)
        if trace is None:
            trace = TraceContext.root(
                "oms", "e2e-flow",
                str(context.get("flow_seq", "0")))
        # D-133 unbroken-trace rule: the flow context itself carries
        # the root trace/correlation ids end-to-end (constant); the
        # per-stage causal chain lives in the emitted ledger records.
        context.setdefault("trace_id", trace.trace_id)
        context.setdefault("correlation_id", trace.trace_id)
        records: List[Dict] = []
        outputs: Dict[str, Dict] = {}
        ctx = trace
        for stage in STAGES:
            impl = self.stages[stage]
            stage_trace = ctx.child(stage)
            try:
                produced = impl(context)
            except Exception as exc:  # noqa: BLE001 — audited failure path
                # D-052 classification at the boundary: explicit
                # `.failure_class` attributes win; else the canonical
                # message classifier. The AUDITED class is what the
                # recovery layer routes on — never the type name.
                failure_class = (getattr(exc, "failure_class", None)
                                 or classify_by_message(str(exc)))
                rec = self.ledger.emit(
                    stage_trace, domain="oms", event=f"stage.{stage}",
                    logical_at=self.logical_at, level="ERROR",
                    status="FAILURE", entity_ref=stage,
                    payload={"error_class": failure_class,
                             "error": str(exc)[:200]})
                records.append({"stage": stage, "ok": False,
                                "record": rec})
                return FlowResult(records, context, outputs, ok=False)
            produced = dict(produced or {})
            validate_envelope(stage, produced)          # D-133 rule 1
            context.update(produced)                     # rule 2
            check_context(context)                       # rule 3
            rec = self.ledger.emit(
                stage_trace, domain="oms", event=f"stage.{stage}",
                logical_at=self.logical_at, status="SUCCESS",
                entity_ref=stage)
            records.append({"stage": stage, "ok": True, "record": rec})
            outputs[stage] = produced
            ctx = stage_trace
        return FlowResult(records, context, outputs, ok=True)

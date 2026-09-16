"""Phase 11 M2 — cross-platform fan-out engine (D-078/D-079).

One universal dispatch payload → N platform sub-publishes, each via the
Phase 9/10 publishers (the SAME code paths already proven in their own
suites). The engine never talks to any platform adapter itself: it
adapts (D-077 matrix), locks (D-079), dispatches, and aggregates (D-078).

Independence (D-077/D-078): every target's sub-publish is fully
isolated — an exception inside one target's publisher is captured as
that target's failed outcome; other targets' outcomes are untouched.
There is NO cross-target rollback anywhere (battery-asserted).

Atomicity (D-079): aggregate state transitions are one receive →
begin → succeed (or fail) chain on the D-027 store per transition,
keyed deterministically per lifecycle stage.

Sources of truth (restart-safety): sub-task outcomes are read back
from the DURABLE event store (publisher history), never from memory.
"""

import json
import sys
import time
from typing import Dict, List, Optional

from canonical.orchestration_contracts import (
    AGGREGATE_STATES,
    OrchestrationContractError,
    SUBTASK_CANCELLED,
    SUBTASK_FAILED,
    SUBTASK_IN_FLIGHT,
    SUBTASK_PUBLISHED,
    adapt_for_target,
    aggregate_from_subtasks,
    release_plan,
    validate_dispatch_payload,
)
from canonical import orchestration_contracts as orc

SOURCE_SYSTEM = orc.SOURCE_SYSTEM
OP_DISPATCH = orc.OP_DISPATCH
OP_FANOUT = orc.OP_QUEUE

# Aggregate lifecycle (D-078) — canonical vocabulary lives in contracts
PENDING, ROUTED, DISPATCHING, PARTIAL_SUCCESS, SUCCESS, FAILED = (
    "PENDING", "ROUTED", "DISPATCHING", "PARTIAL_SUCCESS",
    "SUCCESS", "FAILED")
CANCELLED = "CANCELLED"  # reserved: aggregate when all targets cancelled

# Deterministic lifecycle-stage order (lowercase, as recorded in
# event refs) for reconstruction from durable data only
_RANK = {"routed": 1, "dispatching": 2, "aggregate": 3}


class OrchestrationError(Exception):
    """Fatal engine boundary violation (never raised for target
    failures — those are outcomes, not engine errors)."""


# --- D-079 anti-race lock (PK-as-lock on live PG; JSON parity) ----------

class _PgFanOutLock:
    """D-079 coordinated-schedule lock: `orchestration.fanout_lock`
    keyed by fanout_key; INSERT-once semantics prevent two dispatcher
    workers from routing the same fan-out. Never released on success
    (double-trigger protection must outlive the attempt)."""

    def __init__(self):
        import os as _os
        scripts = _os.path.join("local", "scripts")
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        from canonical.notion_ingest import _exec, _txt  # noqa: E402
        self._exec = _exec
        self._txt = _txt

    def claim(self, key: str, claimant: str) -> bool:
        out = self._exec(
            "INSERT INTO orchestration.fanout_lock (fanout_key, claimant) "
            "VALUES (" + self._txt("k") + ", " + self._txt("c") + ") "
            "ON CONFLICT (fanout_key) DO NOTHING "
            "RETURNING fanout_key", {"k": key, "c": claimant}).strip()
        return bool(out)


class _JsonFanOutLock:
    """Offline parity lock (local tests): same INSERT-once semantics,
    file-backed with per-path module-level locking."""

    _PATH_LOCKS: Dict[str, object] = {}

    def __init__(self, path: str):
        import threading
        self.path = path
        lock = _JsonFanOutLock._PATH_LOCKS.get(path)
        if lock is None:
            lock = threading.Lock()
            _JsonFanOutLock._PATH_LOCKS[path] = lock
        self._lock = lock

    def claim(self, key: str, claimant: str) -> bool:
        with self._lock:
            data: Dict = {}
            try:
                with open(self.path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
            except (FileNotFoundError, json.JSONDecodeError):
                data = {}
            if key in data:
                return False
            data[key] = {"claimant": claimant, "claimed_at": time.time()}
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2,
                          sort_keys=True)
            import os
            os.replace(tmp, self.path)
            return True


def _default_lock():
    """PG lock when the live stack answers, JSON parity otherwise."""
    try:
        lk = _PgFanOutLock()
        lk._exec("SELECT 1", {})
        return lk
    except Exception:
        return _JsonFanOutLock(
            "local/volumes/orchestration/fanout_lock.json")


# --- engine --------------------------------------------------------------

class FanOutEngine:
    """D-077/D-078/D-079 orchestrator.

    publish_binds maps target → callable(ref, **kw) → outcome Dict
    (exactly the Phase 9/10 `publisher.publish(ref, adapter)` surface).
    """

    def __init__(self, store, publish_binds: Dict[str, object],
                 lock=None, provenance=None):
        self.store = store
        if not publish_binds:
            raise OrchestrationError("publish_binds must not be empty")
        self.publish_binds = dict(publish_binds)
        self.lock = lock or _default_lock()
        self.provenance = provenance

    # -- lifecycle events (atomic per transition, D-079) -----------------

    def _record(self, job_id: str, stage: str, ref: Dict,
                *, verdict: str) -> None:
        eid = f"orchestration|{job_id}|{stage}"
        # the ref must self-identify: succeeded_references() returns
        # bare result_reference strings, so reconstruction reads
        # event_id/stage from the payload itself (D-027 durability)
        ref = dict(ref, event_id=eid, stage=stage)
        rec = self.store.receive(SOURCE_SYSTEM, eid, OP_FANOUT, ref)
        if rec["verdict"] == "integrity_error":
            from services.sync_engine import IntegrityError
            raise IntegrityError(
                f"conflicting fan-out transition for {eid} — human review")
        if rec["verdict"] in ("new", "retry"):
            self.store.begin(SOURCE_SYSTEM, eid)
            self.store.succeed(SOURCE_SYSTEM, eid,
                               result_reference=json.dumps(
                                   ref, ensure_ascii=False, sort_keys=True))
        if self.provenance is not None:
            try:
                self.provenance.record(
                    actor="orchestration-engine",
                    action="SYSTEM_GENERATED",
                    entity="fanout_job",
                    entity_id=eid,
                    detail={"stage": stage, "verdict": verdict},
                )
            except Exception:
                pass  # provenance must never corrupt fan-out state

    def _store_refs(self) -> List[Dict]:
        """Durable succeeded refs (D-027 interface: succeeded_references
        returns result_reference JSON strings in insertion order)."""
        refs: List[Dict] = []
        for line in self.store.succeeded_references(SOURCE_SYSTEM):
            try:
                ref = json.loads(line)
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(ref, dict):
                refs.append(ref)
        return refs

    def _aggregate_seq(self, job_id: str) -> int:
        """Monotonic per-job aggregate-observation counter, derived from
        DURABLE aggregate events (restart-safe; not wall-clock). The
        aggregate evolves as targets finish, so each observation is a
        DISTINCT D-027 event — a repeated identical observation stays
        deduplicated by its payload; a changed one is a new event, not
        a conflicting duplicate."""
        n = 0
        for ref in self._store_refs():
            eid = str(ref.get("event_id", ""))
            if eid.startswith(f"orchestration|{job_id}|aggregate|"):
                n += 1
        return n + 1

    def _job_ref(self, job_id: str):
        refs = self._store_refs()
        best = None
        prefix = f"orchestration|{job_id}|"
        for ref in refs:
            eid = str(ref.get("event_id", ""))
            if eid.startswith(prefix):
                stage = (str(ref.get("stage") or "")
                         or eid[len(prefix):])
                # stage is recorded explicitly; tolerate the sequenced
                # aggregate id ("aggregate|N") via startswith
                rank = _RANK.get(stage)
                if rank is None and stage.startswith("aggregate"):
                    rank = _RANK["aggregate"]
                if rank is not None:
                    if best is None or rank >= best[0]:
                        best = (rank, ref)
        return best[1] if best else None

    def state(self, job_id: str) -> Optional[str]:
        ref = self._job_ref(job_id)
        if ref is None:
            return None
        # aggregate state: latest authoritative record (target-level
        # events carry no aggregate — lifecycle stages do)
        agg = ref.get("aggregate")
        return str(agg).upper() if agg else None

    # -- dispatch ---------------------------------------------------------

    def route(self, payload: Dict, *, actor: str = "orchestration-ops"
              ) -> Dict:
        """Validate → adapt every target → claim the anti-race lock →
        ROUTED (durable). Raises OrchestrationContractError (Class-B)
        locally before any dispatch. Lock losers get
        {"routed": False, "reason": "already_claimed"} (D-079)."""
        norm = validate_dispatch_payload(payload)
        fanout_key = norm["fanout_key"]
        if not self.lock.claim(fanout_key, actor):
            return {"routed": False, "reason": "already_claimed",
                    "fanout_key": fanout_key}
        adapted: Dict[str, Dict] = {}
        warnings: Dict[str, List[str]] = {}
        for target in norm["targets"]:
            res = adapt_for_target(target, norm)
            adapted[target] = res["payload"]
            if res.get("warnings"):
                warnings[target] = res["warnings"]
        ref = dict(norm, fanout_key=fanout_key,
                   adapted_payloads=adapted, adaptation_warnings=warnings,
                   aggregate=ROUTED)
        self._record(norm["job_id"], "routed", ref, verdict="routed")
        return {"routed": True, "fanout_key": fanout_key,
                "job_id": norm["job_id"], "ref": ref}

    def dispatch(self, routed: Dict, *, actor: str = "orchestration-ops"
                 ) -> Dict:
        """Dispatch one already-routed job. Independent fan-out (D-077):
        each target runs inside its own try/except; a target crash is
        that target's outcome, never an engine failure and never a
        rollback of other targets."""
        ref = routed.get("ref") or self._job_ref(routed.get("job_id", ""))
        if not ref:
            raise OrchestrationError(
                "dispatch requires a routed job (call route() first)")
        job_id = ref["job_id"]
        self._record(job_id, "dispatching",
                     dict(ref, aggregate=DISPATCHING), verdict="dispatching")
        outcomes: Dict[str, str] = {}
        receipts: Dict[str, Dict] = {}
        for target, adapted in ref["adapted_payloads"].items():
            bind = self.publish_binds.get(target)
            if bind is None:
                outcomes[target] = "no_publisher_bound"
                receipts[target] = {"outcome": "no_publisher_bound",
                                    "error_class": "B"}
            else:
                try:
                    res = bind(adapted, actor=actor)
                    outcomes[target] = res.get("outcome", "unknown")
                    receipts[target] = res
                except Exception as exc:  # isolation, not silence
                    outcomes[target] = "target_dispatch_crashed"
                    receipts[target] = {
                        "outcome": "target_dispatch_crashed",
                        "error_class": "E",
                        "error": str(exc)[:200],
                    }
            # durable per-target receipt (D-078 provenance) — written for
            # EVERY outcome path, including no_publisher_bound
            eid = (f"orchestration|{job_id}|target|{target}|"
                   f"{time.time_ns()}")
            tref = {"event_id": eid, "job_id": job_id, "target": target,
                    "outcome": outcomes[target],
                    "receipt": receipts[target], "stage": "target"}
            rec = self.store.receive(SOURCE_SYSTEM, eid, OP_DISPATCH, tref)
            if rec["verdict"] in ("new", "retry"):
                self.store.begin(SOURCE_SYSTEM, eid)
                self.store.succeed(SOURCE_SYSTEM, eid,
                                   result_reference=json.dumps(
                                       tref, ensure_ascii=False,
                                       sort_keys=True))
        aggregate = aggregate_from_subtasks(outcomes)
        self._record(job_id, f"aggregate|{self._aggregate_seq(job_id)}",
                     dict(ref, outcomes=outcomes, aggregate=aggregate),
                     verdict=aggregate)
        return {"job_id": job_id, "fanout_key": ref["fanout_key"],
                "outcomes": outcomes, "receipts": receipts,
                "aggregate": aggregate}

    # -- D-080 retry coordination ----------------------------------------

    def retry_targets(self, job_id: str, targets: List[str], *,
                      actor: str = "orchestration-ops") -> Dict:
        """Re-dispatch ONLY the named failing targets (D-080): already
        published/duplicate-blocked targets are never re-triggered."""
        ref = self._job_ref(job_id)
        if not ref:
            raise OrchestrationError(f"no durable job {job_id}")
        prior = self._prior_outcomes(job_id)
        skip = [t for t in targets if prior.get(t) in (
            "published", "duplicate_publish_blocked")]
        run = [t for t in targets if t not in skip]
        outcomes: Dict[str, str] = {}
        receipts: Dict[str, Dict] = {}
        for target in run:
            adapted = (ref.get("adapted_payloads") or {}).get(target)
            bind = self.publish_binds.get(target)
            if adapted is None or bind is None:
                outcomes[target] = "no_publisher_bound"
                receipts[target] = {"outcome": "no_publisher_bound"}
                continue
            try:
                res = bind(adapted, actor=actor)
                outcomes[target] = res.get("outcome", "unknown")
                receipts[target] = res
            except Exception as exc:
                outcomes[target] = "target_dispatch_crashed"
                receipts[target] = {"outcome": "target_dispatch_crashed",
                                    "error": str(exc)[:200]}
        for target, outcome in outcomes.items():
            eid = f"orchestration|{job_id}|target|{target}|{time.time_ns()}"
            tref = {"event_id": eid, "job_id": job_id, "target": target,
                    "outcome": outcome, "receipt": receipts[target],
                    "origin": "retry", "stage": "target"}
            rec = self.store.receive(SOURCE_SYSTEM, eid, OP_DISPATCH, tref)
            if rec["verdict"] in ("new", "retry"):
                self.store.begin(SOURCE_SYSTEM, eid)
                self.store.succeed(SOURCE_SYSTEM, eid,
                                   result_reference=json.dumps(
                                       tref, ensure_ascii=False,
                                       sort_keys=True))
        merged = dict(prior)
        merged.update(outcomes)
        for t in skip:  # served targets keep their served verdict
            merged.setdefault(t, prior.get(t, "duplicate_publish_blocked"))
        aggregate = aggregate_from_subtasks(merged)
        self._record(job_id, f"aggregate|{self._aggregate_seq(job_id)}",
                     dict(ref, outcomes=merged, aggregate=aggregate),
                     verdict=aggregate)
        return {"job_id": job_id, "retried": run, "skipped": skip,
                "outcomes": merged, "receipts": receipts,
                "aggregate": aggregate}

    def _prior_outcomes(self, job_id: str) -> Dict[str, str]:
        refs = self._store_refs()
        out: Dict[str, str] = {}
        for ref in refs:
            eid = str(ref.get("event_id", ""))
            if eid.startswith(f"orchestration|{job_id}|target|"):
                out[ref.get("target", "?")] = ref.get("outcome", "unknown")
        return out

    # -- D-080 cancel ------------------------------------------------------

    def cancel(self, job_id: str, targets: Optional[List[str]] = None, *,
               actor: str = "hitl-operator") -> Dict:
        """HITL cancel: only targets NOT yet terminal are cancelled
        (D-080). Already-published targets are immutably recorded and
        reported back, never reverted."""
        ref = self._job_ref(job_id)
        if not ref:
            raise OrchestrationError(f"no durable job {job_id}")
        prior = self._prior_outcomes(job_id)
        wanted = targets or list((ref.get("adapted_payloads") or {}).keys())
        cancelled: List[str] = []
        already_served: Dict[str, str] = {}
        for t in wanted:
            if prior.get(t) in ("published", "duplicate_publish_blocked"):
                # immutably served — never revertible (D-070/D-074)
                already_served[t] = prior[t]
            elif prior.get(t) != "cancelled":
                # unstarted, in-flight, or even terminally-rejected
                # targets can be aborted: rejection is not publication
                cancelled.append(t)
        for t in cancelled:
            eid = f"orchestration|{job_id}|target|{t}|{time.time_ns()}"
            tref = {"event_id": eid, "job_id": job_id, "target": t,
                    "outcome": "cancelled", "cancelled_by": actor,
                    "origin": "hitl_cancel", "stage": "target"}
            rec = self.store.receive(SOURCE_SYSTEM, eid, OP_DISPATCH, tref)
            if rec["verdict"] in ("new", "retry"):
                self.store.begin(SOURCE_SYSTEM, eid)
                self.store.succeed(SOURCE_SYSTEM, eid,
                                   result_reference=json.dumps(
                                       tref, ensure_ascii=False,
                                       sort_keys=True))
        merged = dict(prior)
        merged.update({t: "cancelled" for t in cancelled})
        merged.update(already_served)
        aggregate = aggregate_from_subtasks(merged)
        self._record(job_id, f"aggregate|{self._aggregate_seq(job_id)}",
                     dict(ref, outcomes=merged, aggregate=aggregate),
                     verdict=aggregate)
        return {"job_id": job_id, "cancelled": cancelled,
                "already_served": already_served,
                "outcomes": merged, "aggregate": aggregate}

"""Phase 8 M1 — unified AI observability & audit trail (D-065).

Structured JSON records (schema `ai.observe.v1`) keyed end-to-end by
the AiProposal correlation id. The collector is called BY the
deterministic pipeline (tasks, lifecycle, HITL service) — the AI
surface gains NO write path to reporting or publication (D-050/D-064;
battery-asserted). Append-only: records are never rewritten.

Authority discipline: this module is observability-only. It contains
no decision verbs, no provider calls, no Woo/Notion/price references,
and it never mutates pipeline state — it only RECORDS it.
"""

import hashlib
import json
import os
import threading
import time
from collections import defaultdict
from typing import Dict, List, Optional

SCHEMA_VERSION = "ai.observe.v1"

STAGES = ("provider_call", "validation", "divergence", "lifecycle",
          "hitl_decision", "fallback")
HITL_DECISIONS = ("approve", "reject", "edit", "none")

_REQUIRED = ("schema_version", "correlation_id", "occurred_at", "stage",
             "task_type", "status")
_INT_FIELDS = ("prompt_tokens", "completion_tokens", "latency_ms")
# strings that must never appear in observability values (D-045)
_REDACTED_MARKERS = ("postgres://", "bearer ", "api_key", "password=",
                     "authorization:")


class ObservabilityError(ValueError):
    """A malformed observability record (Class-B programming error)."""


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class AiObservabilityCollector:
    """Append-only, correlation-keyed AI observability store (D-065).

    JSONL persistence; every record is validated BEFORE write — a
    malformed record raises ObservabilityError instead of being
    silently persisted (contract violations are never repaired).
    """

    def __init__(self, path: Optional[str] = None):
        self.path = path or os.environ.get("AI_OBSERVABILITY_PATH") or \
            os.path.join("local", "volumes", "observability",
                         "ai_observability.jsonl")
        self._lock = threading.Lock()
        self._records: List[Dict] = []
        if self.path and os.path.exists(self.path):
            with open(self.path, encoding="utf-8") as f:
                self._records = [json.loads(line)
                                 for line in f if line.strip()]

    # -- write path (pipeline-side only) -------------------------------------

    def record(self, *, correlation_id: str, stage: str,
               task_type: str, status: str,
               provider: str = "", model: str = "",
               template_id: str = "", template_hash: str = "",
               prompt_tokens: int = 0, completion_tokens: int = 0,
               latency_ms: int = 0, estimated_cost_usd: float = 0.0,
               divergence_rate: float = 0.0,
               hitl_decision: str = "none", error_class: str = "",
               notes: str = "") -> Dict:
        rec = {
            "schema_version": SCHEMA_VERSION,
            "correlation_id": str(correlation_id),
            "occurred_at": _utc_now(),
            "stage": stage,
            "task_type": task_type,
            "provider": provider,
            "model": model,
            "template_id": template_id,
            "template_hash": template_hash,
            "prompt_tokens": int(prompt_tokens),
            "completion_tokens": int(completion_tokens),
            "latency_ms": int(latency_ms),
            "estimated_cost_usd": round(float(estimated_cost_usd), 6),
            "divergence_rate": round(float(divergence_rate), 6),
            "hitl_decision": hitl_decision,
            "status": status,
            "error_class": error_class,
            "notes": notes,
        }
        self._validate(rec)
        with self._lock:
            self._records.append(dict(rec))
            self._persist(rec)
        return dict(rec)

    def _validate(self, rec: Dict) -> None:
        missing = [k for k in _REQUIRED if not rec.get(k)]
        if missing:
            raise ObservabilityError(
                f"observability record missing {missing} (Class B)")
        if rec["stage"] not in STAGES:
            raise ObservabilityError(
                f"unknown stage {rec['stage']!r} (Class B)")
        if rec["hitl_decision"] not in HITL_DECISIONS:
            raise ObservabilityError(
                f"unknown hitl_decision {rec['hitl_decision']!r} (Class B)")
        for field in _INT_FIELDS:
            if rec[field] < 0:
                raise ObservabilityError(
                    f"negative {field} (Class B)")
        blob = json.dumps(rec, ensure_ascii=False).lower()
        for marker in _REDACTED_MARKERS:
            if marker in blob:
                raise ObservabilityError(
                    f"credential-adjacent material in record "
                    f"({marker!r}) — D-045 redaction (Class B)")

    def _persist(self, rec: Dict) -> None:
        if not self.path:
            return
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False,
                               sort_keys=True) + "\n")

    # -- read path (reporting) -----------------------------------------------

    def records(self, correlation_id: Optional[str] = None,
                stage: Optional[str] = None) -> List[Dict]:
        out = self._records
        if correlation_id is not None:
            out = [r for r in out if r["correlation_id"] == correlation_id]
        if stage is not None:
            out = [r for r in out if r["stage"] == stage]
        return list(out)

    def cost_report(self) -> Dict:
        """Aggregate spend per task_type / provider / UTC day (D-065).

        Reads only from collected records; AI has no other path into
        reporting (D-050).
        """
        by_task: Dict[str, float] = defaultdict(float)
        by_provider: Dict[str, float] = defaultdict(float)
        by_day: Dict[str, float] = defaultdict(float)
        tokens: Dict[str, int] = defaultdict(int)
        decisions: Dict[str, int] = defaultdict(int)
        for r in self._records:
            by_task[r["task_type"]] += r["estimated_cost_usd"]
            if r["provider"]:
                by_provider[r["provider"]] += r["estimated_cost_usd"]
            by_day[r["occurred_at"][:10]] += r["estimated_cost_usd"]
            tokens["prompt"] += r["prompt_tokens"]
            tokens["completion"] += r["completion_tokens"]
            if r["hitl_decision"] != "none":
                decisions[r["hitl_decision"]] += 1
        round6 = lambda d: {k: round(v, 6) for k, v in d.items()}
        return {
            "total_cost_usd": round(sum(by_task.values()), 6),
            "by_task_type": round6(dict(by_task)),
            "by_provider": round6(dict(by_provider)),
            "by_day_utc": round6(dict(by_day)),
            "tokens": dict(tokens),
            "hitl_decisions": dict(decisions),
        }


def hitl_decision_record(action: str) -> str:
    """Map a lifecycle action to its D-065 hitl_decision value."""
    return {"accept": "approve", "modify_accept": "edit",
            "reject": "reject", "submit_review": "none"}.get(action,
                                                             "none")


def divergence_rate(flagged: int, total: int) -> float:
    """Divergence rate for a batch (0.0–1.0); deterministic."""
    if total <= 0:
        return 0.0
    return round(flagged / total, 6)


def content_hash(payload: Dict) -> str:
    """Stable content hash (also used for template pinning, D-067)."""
    return hashlib.sha256(json.dumps(
        payload, ensure_ascii=False, sort_keys=True).encode(
        "utf-8")).hexdigest()

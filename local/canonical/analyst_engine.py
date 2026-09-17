"""Phase 17 M2 — analyst engine & insight vault (D-101/D-102/D-104).

AnalystEngine: STRICT separation between rule evaluation (pure:
durable metrics in, evaluation result out — the evaluator is an
INJECTED function, never an SDK) and decision application (durable:
vault status + D-027 audit event). Insight identity is the SHA-256
`insight_key` over (category, correlation_keys, metric_refs) —
identical evidence dedups by construction (D-102); atomicity via the
PostgreSQL `analytics.business_insight` PK with a JSON parity vault.

The D-104 boundary lives HERE: `auto_accept` raises for any insight
where `can_auto_accept` is False, so AUTO_ACCEPTED is structurally
unreachable for HIGH/CRITICAL severity or state-mutating payloads.

No wall clock anywhere: evaluation and transitions take injected
context; every durable write is a D-027 event with provenance; a
lost exactly-once race is a clean loser (Phase 16 precedent).
"""

import json
from typing import Dict, List, Optional

from canonical.analyst_contracts import (
    REF_KINDS,
    SOURCE_SYSTEM,
    ST_AUTO_ACCEPTED,
    ST_DISPATCHED_TO_HITL,
    ST_DISMISSED,
    ST_EVALUATED,
    ST_GENERATED,
    ST_SUPERSEDED,
    AnalystContractError,
    can_auto_accept,
    insight_key,
    is_transition_legal,
    requires_hitl,
    validate_insight,
)
from services.sync_engine import IntegrityError

OP_INSIGHT = "analyst_insight"


# --- backends -------------------------------------------------------------------

class _JsonVault:
    """Offline parity vault: JSON file with PK semantics on insight_key."""

    def __init__(self, path: str):
        import os
        import pathlib
        self.path = str(path)
        pathlib.Path(self.path).parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> Dict:
        import os
        if not os.path.exists(self.path):
            return {}
        with open(self.path, encoding="utf-8") as fh:
            return json.load(fh)

    def _save(self, data: Dict) -> None:
        import os
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, sort_keys=True)
        os.replace(tmp, self.path)

    def insert_insight(self, row: Dict) -> str:
        data = self._load()
        if row["insight_key"] in data:
            return "duplicate"
        data[row["insight_key"]] = row
        self._save(data)
        return "created"

    def get_insight(self, insight_key: str) -> Optional[Dict]:
        return self._load().get(insight_key)

    def set_status(self, insight_key: str, status: str,
                   superseded_by: Optional[str]) -> int:
        data = self._load()
        row = data.get(insight_key)
        if row is None:
            return 0
        row["status"] = status
        row["superseded_by"] = superseded_by
        self._save(data)
        return 1

    def all_insights(self) -> Dict[str, Dict]:
        return self._load()


class _PgVault:
    """Live vault: the `analytics.business_insight` PK IS the dedup."""

    def __init__(self):
        import sys as _sys
        import os as _os
        scripts = _os.path.join("local", "scripts")
        if scripts not in _sys.path:
            _sys.path.insert(0, scripts)
        from canonical.notion_ingest import _exec, _txt  # noqa: E402
        self._exec = _exec
        self._txt = _txt

    def insert_insight(self, row: Dict) -> str:
        out = self._exec(
            "INSERT INTO analytics.business_insight (insight_key, "
            "insight_id, category, severity, status, "
            "confidence_score, metric_refs, correlation_keys, "
            "actionable_payload, hitl_required) VALUES ("
            + self._txt("k") + ", " + self._txt("i") + ", "
            + self._txt("c") + ", " + self._txt("s") + ", "
            + self._txt("st") + ", " + self._txt("cf") + "::numeric, "
            + self._txt("mr") + "::jsonb, " + self._txt("ck")
            + "::jsonb, " + self._txt("ap") + "::jsonb, "
            + self._txt("h") + "::boolean) "
            "ON CONFLICT (insight_key) DO NOTHING RETURNING "
            "insight_key",
            {"k": row["insight_key"], "i": row["insight_id"],
             "c": row["category"], "s": row["severity"],
             "st": row["status"],
             "cf": str(row["confidence_score"]),
             "mr": json.dumps(row["metric_refs"], ensure_ascii=False,
                              sort_keys=True),
             "ck": json.dumps(list(row["correlation_keys"]),
                              ensure_ascii=False, sort_keys=True),
             "ap": json.dumps(row["actionable_payload"],
                              ensure_ascii=False, sort_keys=True),
             "h": "true" if row["hitl_required"] else "false"}).strip()
        return "created" if out else "duplicate"

    def get_insight(self, insight_key: str) -> Optional[Dict]:
        rows = self._exec(
            "SELECT insight_key || chr(31) || insight_id || chr(31) || "
            "category || chr(31) || severity || chr(31) || status || "
            "chr(31) || confidence_score::text || chr(31) || "
            "metric_refs::text || chr(31) || correlation_keys::text || "
            "chr(31) || actionable_payload::text || chr(31) || "
            "hitl_required::text || chr(31) || "
            "coalesce(superseded_by, '') || chr(31) || 'END' FROM "
            "analytics.business_insight WHERE insight_key = "
            + self._txt("k"), {"k": insight_key}).strip()
        if not rows:
            return None
        p = rows.split("\x1f")
        if len(p) < 10 or p[-1] != "END":
            return None
        return {"insight_key": p[0], "insight_id": p[1],
                "category": p[2], "severity": p[3], "status": p[4],
                "confidence_score": float(p[5]),
                "metric_refs": json.loads(p[6]),
                "correlation_keys": tuple(json.loads(p[7])),
                "actionable_payload": json.loads(p[8]),
                "hitl_required": p[9] == "true",
                "superseded_by": p[10] or None}

    def set_status(self, insight_key: str, status: str,
                   superseded_by: Optional[str]) -> int:
        out = self._exec(
            "UPDATE analytics.business_insight SET status = "
            + self._txt("st") + ", superseded_by = "
            + self._txt("sb") + " WHERE insight_key = "
            + self._txt("k") + " RETURNING insight_key",
            {"st": status, "sb": superseded_by,
             "k": insight_key}).strip()
        return 1 if out else 0

    def all_insights(self) -> Dict[str, Dict]:
        rows = self._exec(
            "SELECT insight_key || chr(31) || insight_id || chr(31) || "
            "category || chr(31) || severity || chr(31) || status || "
            "chr(31) || 'END' FROM analytics.business_insight", {})
        out: Dict[str, Dict] = {}
        for line in rows.splitlines():
            p = line.strip().split("\x1f")
            if len(p) >= 6 and p[-1] == "END":
                out[p[0]] = {"insight_key": p[0], "insight_id": p[1],
                             "category": p[2], "severity": p[3],
                             "status": p[4]}
        return out


def default_vault():
    try:
        vault = _PgVault()
        vault._exec("SELECT 1", {})
        return vault
    except Exception:
        import os
        return _JsonVault(os.path.join("local", "volumes", "analyst",
                                       "insights.json"))


# --- engine ----------------------------------------------------------------------

class AnalystEngine:
    """D-101/D-102/D-104 core. store: D-027 store; vault: backend."""

    def __init__(self, store, vault=None):
        self._store = store
        self._vault = vault or default_vault()

    # -- durable audit ----------------------------------------------------------

    def _refs(self) -> List[Dict]:
        out: List[Dict] = []
        for raw in self._store.succeeded_references(SOURCE_SYSTEM):
            if isinstance(raw, dict):
                out.append(raw)
                continue
            try:
                out.append(json.loads(raw))
            except (json.JSONDecodeError, TypeError):
                continue
        return out

    @staticmethod
    def _eid(kind: str, ident: str, seq: int = 0) -> str:
        return f"analyst|{kind}|{ident}|{int(seq)}"

    def _record(self, eid: str, ref: Dict) -> bool:
        """Durable audit write. A concurrent writer winning the SAME
        event id with the SAME payload is one logical delivery: the
        loser returns False — the audit row is already durable
        (exactly-once, D-027; Phase 16 precedent)."""
        verdict = self._store.receive(SOURCE_SYSTEM, eid, OP_INSIGHT, ref)
        if verdict.get("verdict") == "skipped_duplicate":
            return False
        try:
            self._store.begin(SOURCE_SYSTEM, eid)
            self._store.succeed(SOURCE_SYSTEM, eid,
                                result_reference=json.dumps(
                                    ref, ensure_ascii=False,
                                    sort_keys=True))
        except IntegrityError:
            return False
        return True

    def _seq(self, kind: str, ident: str) -> int:
        """Durable attempt counter: how many audit events of this
        transition kind already exist for this insight (event ids
        must be attempt-unique — Phase 15 precedent)."""
        durable_kind = REF_KINDS[kind]
        return sum(1 for ref in self._refs()
                   if ref.get("kind") == durable_kind
                   and ref.get("insight_key") == ident)

    # -- propose (D-102) -----------------------------------------------------------

    def propose(self, insight: Dict) -> Dict:
        """Validate → dedup → durable GENERATED. Evaluation never
        happens here; application is the only durable act (D-102)."""
        validate_insight(insight)
        key = insight_key(insight["category"],
                          insight["correlation_keys"],
                          insight["metric_refs"])
        row = {
            "insight_key": key,
            "insight_id": insight["insight_id"],
            "category": insight["category"],
            "severity": insight["severity"],
            "status": ST_GENERATED,
            "confidence_score": float(insight["confidence_score"]),
            "metric_refs": insight["metric_refs"],
            "correlation_keys": tuple(
                insight["correlation_keys"]),
            "actionable_payload": insight["actionable_payload"],
            "hitl_required": requires_hitl(insight),
            "superseded_by": None,
        }
        result = self._vault.insert_insight(row)
        if result == "duplicate":
            # The dedup audit is a function of the EVIDENCE (the
            # insight_key) only — the caller's incidental insight_id
            # must never make identical evidence a conflicting
            # duplicate (D-027/D-102).
            self._record(self._eid("dedup", key), {
                "kind": "dedup", "insight_key": key})
            existing = self._vault.get_insight(key)
            return {"status": "DUPLICATE", "insight_key": key,
                    "insight_id": existing["insight_id"]
                    if existing else None}
        self._record(self._eid("generated", key), {
            "kind": REF_KINDS["generated"], "insight_key": key,
            "insight_id": insight["insight_id"],
            "category": insight["category"],
            "severity": insight["severity"],
            "confidence_score": float(insight["confidence_score"]),
            "correlation_keys": list(insight["correlation_keys"]),
            "metric_refs": insight["metric_refs"],
            "hitl_required": row["hitl_required"]})
        return {"status": "CREATED", "insight_key": key,
                "hitl_required": row["hitl_required"]}

    # -- evaluate (D-102: pure evaluation, durable application) --------------------

    def evaluate(self, insight_key: str, evaluator) -> Dict:
        """The injected evaluator is a PURE function of the durable
        insight row → verdict dict {approved: bool, note: str}. The
        engine applies the verdict durably."""
        row = self._vault.get_insight(insight_key)
        if row is None:
            return {"ok": False, "reason": "unknown_insight"}
        if row["status"] != ST_GENERATED:
            return {"ok": False, "reason": "not_evaluable",
                    "status": row["status"]}
        verdict = evaluator(row)
        if not isinstance(verdict, dict) or \
                "approved" not in verdict:
            raise AnalystContractError(
                "evaluator must return {approved: bool, note: str}")
        nxt = ST_EVALUATED
        if not self._vault.set_status(insight_key, nxt, None):
            return {"ok": False, "reason": "vault_update_failed"}
        self._record(self._eid("evaluated", insight_key,
                               self._seq("evaluated", insight_key)), {
            "kind": REF_KINDS["evaluated"], "insight_key": insight_key,
            "approved": bool(verdict["approved"]),
            "note": str(verdict.get("note", ""))[:500]})
        return {"ok": True, "status": nxt,
                "approved": bool(verdict["approved"])}

    # -- decisions (D-101/D-104) ------------------------------------------------------

    def dispatch_to_hitl(self, insight_key: str) -> Dict:
        row = self._vault.get_insight(insight_key)
        if row is None:
            return {"ok": False, "reason": "unknown_insight"}
        if not is_transition_legal(row["status"], ST_DISPATCHED_TO_HITL):
            return {"ok": False, "reason": "illegal_transition",
                    "from": row["status"]}
        if not self._vault.set_status(insight_key,
                                      ST_DISPATCHED_TO_HITL, None):
            return {"ok": False, "reason": "vault_update_failed"}
        self._record(self._eid("hitl", insight_key,
                               self._seq("hitl", insight_key)), {
            "kind": REF_KINDS["hitl"], "insight_key": insight_key,
            "hitl_required": True})
        return {"ok": True, "status": ST_DISPATCHED_TO_HITL}

    def auto_accept(self, insight_key: str) -> Dict:
        """D-104: structurally unreachable for HITL-required insights."""
        row = self._vault.get_insight(insight_key)
        if row is None:
            return {"ok": False, "reason": "unknown_insight"}
        if not is_transition_legal(row["status"], ST_AUTO_ACCEPTED):
            return {"ok": False, "reason": "illegal_transition",
                    "from": row["status"]}
        if not can_auto_accept(row):
            return {"ok": False,
                    "reason": "hitl_required_boundary",
                    "detail": "HIGH/CRITICAL severity or state-mutating "
                              "payload requires human review (D-104)"}
        if not self._vault.set_status(insight_key, ST_AUTO_ACCEPTED, None):
            return {"ok": False, "reason": "vault_update_failed"}
        self._record(self._eid("auto", insight_key,
                               self._seq("auto", insight_key)), {
            "kind": REF_KINDS["auto"], "insight_key": insight_key})
        return {"ok": True, "status": ST_AUTO_ACCEPTED}

    def dismiss(self, insight_key: str) -> Dict:
        row = self._vault.get_insight(insight_key)
        if row is None:
            return {"ok": False, "reason": "unknown_insight"}
        if not is_transition_legal(row["status"], ST_DISMISSED):
            return {"ok": False, "reason": "illegal_transition",
                    "from": row["status"]}
        if not self._vault.set_status(insight_key, ST_DISMISSED, None):
            return {"ok": False, "reason": "vault_update_failed"}
        self._record(self._eid("dismissed", insight_key,
                               self._seq("dismissed", insight_key)), {
            "kind": REF_KINDS["dismissed"],
            "insight_key": insight_key})
        return {"ok": True, "status": ST_DISMISSED}

    def supersede(self, old_key: str, new_key: str) -> Dict:
        """A later insight covering the same correlation keys marks the
        earlier one SUPERSEDED (legal from any non-terminal state)."""
        row = self._vault.get_insight(old_key)
        if row is None:
            return {"ok": False, "reason": "unknown_insight"}
        if not is_transition_legal(row["status"], ST_SUPERSEDED):
            return {"ok": False, "reason": "illegal_transition",
                    "from": row["status"]}
        if not self._vault.set_status(old_key, ST_SUPERSEDED, new_key):
            return {"ok": False, "reason": "vault_update_failed"}
        self._record(self._eid("superseded", old_key,
                               self._seq("superseded", old_key)), {
            "kind": REF_KINDS["superseded"], "insight_key": old_key,
            "superseded_by": new_key})
        return {"ok": True, "status": ST_SUPERSEDED}

    # -- ledger reconstruction (D-104) -------------------------------------------------

    def ledger(self, insight_key: str) -> List[Dict]:
        """Complete durable rationale for one insight, in D-027 order:
        generated → evaluated → decision (+ superseded)."""
        return [r for r in self._refs()
                if r.get("insight_key") == insight_key
                and r.get("kind") in set(REF_KINDS.values()) | {"dedup"}]

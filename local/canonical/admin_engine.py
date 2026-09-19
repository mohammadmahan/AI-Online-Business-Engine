"""Phase 19 M2 — control plane engine & operator audit vault
(D-110/D-112).

ControlPlaneEngine over two durable stores:

  - `admin.operator_actions`: action_id PK is the application guard —
    an action applies exactly once; the replay confirmation_key is
    stored as a hash and BURNED on first APPLY use (single-use,
    D-110).
  - `admin.control_audit`: append-only SHA-256 hash-chained operator
    ledger (global chain, Phase 18 standard); `verify_chain` detects
    any mutation of operator history (D-112).

The state facade (`SystemDiagnosticReport`) aggregates durable state
ACROSS DOMAINS through INJECTED read callables (queues/hitl/
insights/assets) — zero cross-module imports. Every executed action
emits an immutable D-027 event. Local-token RBAC only (D-045/D-109);
no wall clock anywhere.
"""

import hashlib
import json
from typing import Callable, Dict, List, Optional

from canonical.admin_contracts import (
    CMD_REPLAY_EVENTS,
    MAX_ACTION_ID_LEN,
    QC_OPEN,
    QC_PAUSED,
    AdminContractError,
    actor_id,
    actor_role,
    is_permitted,
    replay_mode,
    validate_action,
    validate_query_filter,
    validate_report,
)
from services.sync_engine import IntegrityError

SOURCE_SYSTEM = "admin"
OP_ADMIN = "admin_action"


def _row_hash(action_id: str, seq: int, body: Dict, prev_hash: str,
              logical_at: str) -> str:
    payload = json.dumps(
        {"action_id": action_id, "seq": seq, "body": body,
         "prev_hash": prev_hash, "logical_at": logical_at},
        ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _key_hash(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


# Transport parity sentinel (Phase 26 finding): the base64/psql path
# cannot carry SQL NULL — `str(None)` degrades to the literal 'None'.
# The audit chain normalizes None command/target to that sentinel on
# write in BOTH vaults and restores None on read, so recomputed hashes
# match across the JSON and PostgreSQL backends. Unambiguous: 'None'
# is not a legal command in the D-109 closed grammar.
_NONE_SENTINEL = "None"


def _norm_none(value: Optional[str]) -> Optional[str]:
    return _NONE_SENTINEL if value is None else value


def _denorm_none(value: Optional[str]) -> Optional[str]:
    return None if value == _NONE_SENTINEL else value


# --- backends -----------------------------------------------------------------

class _JsonVault:
    """Offline parity vault mirroring PG semantics."""

    def __init__(self, root: str):
        import os
        import pathlib
        self.root = str(root)
        pathlib.Path(self.root).mkdir(parents=True, exist_ok=True)

    def _path(self, name):
        import os
        return os.path.join(self.root, name)

    def _read(self, name: str) -> Dict:
        import os
        p = self._path(name)
        if not os.path.exists(p):
            return {}
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)

    def _write(self, name: str, data: Dict) -> None:
        import os
        p = self._path(name)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, sort_keys=True)
        os.replace(tmp, p)

    # operator actions
    def insert_action(self, row: Dict) -> str:
        data = self._read("actions.json")
        if row["action_id"] in data:
            return "duplicate"
        data[row["action_id"]] = row
        self._write("actions.json", data)
        return "created"

    def mark_applied(self, action_id: str, sets: Dict) -> int:
        data = self._read("actions.json")
        row = data.get(action_id)
        if row is None or row["status"] == "APPLIED":
            return 0
        row.update(sets)
        row["status"] = "APPLIED"
        self._write("actions.json", data)
        return 1

    def burn_key(self, action_id: str) -> int:
        data = self._read("actions.json")
        row = data.get(action_id)
        if row is None or row.get("confirmation_key_hash") is None:
            return 0
        row["confirmation_key_hash"] = None
        self._write("actions.json", data)
        return 1

    def get_action(self, action_id: str) -> Optional[Dict]:
        return self._read("actions.json").get(action_id)

    def all_actions(self) -> Dict[str, Dict]:
        return self._read("actions.json")

    # audit ledger
    def append_audit(self, row: Dict) -> None:
        row = dict(row)
        row["command"] = _norm_none(row.get("command"))
        row["target"] = _norm_none(row.get("target"))
        data = self._read("audit.json")
        data[str(row["audit_seq"])] = row
        self._write("audit.json", data)

    def max_audit_seq(self) -> int:
        rows = self._read("audit.json")
        return max((int(v) for v in rows), default=0)

    def last_audit_hash(self) -> str:
        seq = self.max_audit_seq()
        if seq == 0:
            return ""
        return self._read("audit.json")[str(seq)]["row_hash"]

    def audit_rows(self) -> List[Dict]:
        rows = list(self._read("audit.json").values())
        rows.sort(key=lambda r: int(r["audit_seq"]))
        for r in rows:
            r["command"] = _denorm_none(r.get("command"))
            r["target"] = _denorm_none(r.get("target"))
        return rows

    # circuit breakers
    def set_breaker(self, row: Dict) -> None:
        data = self._read("breakers.json")
        data[row["breaker_name"]] = row
        self._write("breakers.json", data)

    def get_breaker(self, name: str) -> Optional[Dict]:
        return self._read("breakers.json").get(name)

    def all_breakers(self) -> Dict[str, Dict]:
        return self._read("breakers.json")


class _PgVault:
    """Live vault: constraints and guarded UPDATEs are the atomicity."""

    def __init__(self):
        import sys as _sys
        import os as _os
        scripts = _os.path.join("local", "scripts")
        if scripts not in _sys.path:
            _sys.path.insert(0, scripts)
        from canonical.notion_ingest import _exec, _txt  # noqa: E402
        self._exec = _exec
        self._txt = _txt

    def insert_action(self, row: Dict) -> str:
        out = self._exec(
            "INSERT INTO admin.operator_actions (action_id, command, "
            "target, actor, reason, status, mode, "
            "confirmation_key_hash, detail, created_at_logical) "
            "VALUES (" + self._txt("i") + ", " + self._txt("c") + ", "
            + self._txt("t") + ", " + self._txt("a") + ", "
            + self._txt("r") + ", " + self._txt("s") + ", "
            + self._txt("m") + ", " + self._txt("k") + ", "
            + self._txt("d") + "::jsonb, " + self._txt("cl") + ") "
            "ON CONFLICT (action_id) DO NOTHING RETURNING action_id",
            {"i": row["action_id"], "c": row["command"],
             "t": row["target"], "a": row["actor"],
             "r": row.get("reason"), "s": row["status"],
             "m": row.get("mode"),
             "k": row.get("confirmation_key_hash"),
             "d": json.dumps(row.get("detail", {}),
                             ensure_ascii=False, sort_keys=True),
             "cl": row["created_at_logical"]}).strip()
        return "created" if out else "duplicate"

    def mark_applied(self, action_id: str, sets: Dict) -> int:
        out = self._exec(
            "UPDATE admin.operator_actions SET status = 'APPLIED', "
            "applied_at_logical = " + self._txt("al")
            + ", confirmation_key_hash = NULL WHERE action_id = "
            + self._txt("i") + " AND status = 'RECEIVED' "
            "RETURNING action_id",
            {"al": sets.get("applied_at_logical"),
             "i": action_id}).strip()
        return 1 if out else 0

    def burn_key(self, action_id: str) -> int:
        out = self._exec(
            "UPDATE admin.operator_actions SET "
            "confirmation_key_hash = NULL WHERE action_id = "
            + self._txt("i") + " AND confirmation_key_hash IS NOT "
            "NULL RETURNING action_id", {"i": action_id}).strip()
        return 1 if out else 0

    def get_action(self, action_id: str) -> Optional[Dict]:
        rows = self._exec(
            "SELECT action_id || chr(31) || command || chr(31) || "
            "target || chr(31) || actor || chr(31) || "
            "coalesce(reason, '') || chr(31) || status || chr(31) || "
            "coalesce(mode, '') || chr(31) || "
            "coalesce(confirmation_key_hash, '') || chr(31) || "
            "detail::text || chr(31) || created_at_logical || chr(31) "
            "|| coalesce(applied_at_logical, '') || chr(31) || 'END' "
            "FROM admin.operator_actions WHERE action_id = "
            + self._txt("i"), {"i": action_id}).strip()
        if not rows:
            return None
        p = rows.split("\x1f")
        if len(p) < 10 or p[-1] != "END":
            return None
        return {"action_id": p[0], "command": p[1], "target": p[2],
                "actor": p[3], "reason": p[4] or None, "status": p[5],
                "mode": p[6] or None,
                "confirmation_key_hash": p[7] or None,
                "detail": json.loads(p[8]),
                "created_at_logical": p[9],
                "applied_at_logical": p[10] or None}

    def all_actions(self) -> Dict[str, Dict]:
        rows = self._exec(
            "SELECT action_id || chr(31) || command || chr(31) || "
            "target || chr(31) || actor || chr(31) || status || "
            "chr(31) || created_at_logical || chr(31) || 'END' FROM "
            "admin.operator_actions ORDER BY created_at_logical, "
            "action_id", {})
        out = {}
        for line in rows.splitlines():
            p = line.strip().split("\x1f")
            if len(p) >= 6 and p[-1] == "END":
                out[p[0]] = {"action_id": p[0], "command": p[1],
                             "target": p[2], "actor": p[3],
                             "status": p[4],
                             "created_at_logical": p[5]}
        return out

    # audit ledger
    def append_audit(self, row: Dict) -> None:
        # audit_seq is INSERTED EXPLICITLY (Phase 26 finding): the
        # stored row_hash embeds the Python-side seq, so it must be
        # the DB row's seq. Relying on the sequence default silently
        # diverges the two after any delete (retention pruning),
        # breaking verification for every later row.
        self._exec(
            "INSERT INTO admin.control_audit (audit_seq, action_id, "
            "event_kind, actor, command, target, detail, prev_hash, "
            "row_hash, logical_at) VALUES (" + self._txt("s")
            + "::bigint, "
            + self._txt("a") + ", " + self._txt("k") + ", "
            + self._txt("ac") + ", " + self._txt("c") + ", "
            + self._txt("t") + ", " + self._txt("d") + "::jsonb, "
            + self._txt("ph") + ", " + self._txt("rh") + ", "
            + self._txt("la") + ")",
            {"s": row["audit_seq"],
             "a": row["action_id"], "k": row["event_kind"],
             "ac": row["actor"],
             "c": _norm_none(row.get("command")),
             "t": _norm_none(row.get("target")),
             "d": json.dumps(row.get("detail", {}),
                             ensure_ascii=False, sort_keys=True),
             "ph": row["prev_hash"], "rh": row["row_hash"],
             "la": row["logical_at"]})

    def max_audit_seq(self) -> int:
        out = self._exec(
            "SELECT coalesce(max(audit_seq), 0)::text FROM "
            "admin.control_audit", {}).strip()
        return int(out or "0")

    def last_audit_hash(self) -> str:
        out = self._exec(
            "SELECT coalesce((SELECT row_hash FROM "
            "admin.control_audit ORDER BY audit_seq DESC LIMIT 1), "
            "'')", {}).strip()
        return out

    def audit_rows(self) -> List[Dict]:
        rows = self._exec(
            "SELECT audit_seq::text || chr(31) || action_id || "
            "chr(31) || event_kind || chr(31) || actor || chr(31) || "
            "coalesce(command, '') || chr(31) || coalesce(target, "
            "'') || chr(31) || detail::text || chr(31) || prev_hash "
            "|| chr(31) || row_hash || chr(31) || logical_at || "
            "chr(31) || 'END' FROM admin.control_audit ORDER BY "
            "audit_seq", {})
        out = []
        for line in rows.splitlines():
            p = line.strip().split("\x1f")
            if len(p) >= 10 and p[-1] == "END":
                out.append({"audit_seq": int(p[0]),
                            "action_id": p[1], "event_kind": p[2],
                            "actor": p[3],
                            "command": _denorm_none(p[4] or None),
                            "target": _denorm_none(p[5] or None),
                            "detail": json.loads(p[6]),
                            "prev_hash": p[7], "row_hash": p[8],
                            "logical_at": p[9]})
        return out

    # circuit breakers
    def set_breaker(self, row: Dict) -> None:
        self._exec(
            "INSERT INTO admin.circuit_breakers (breaker_name, "
            "state, tripped_by, tripped_at_logical, "
            "cool_down_until, last_reason) VALUES ("
            + self._txt("n") + ", " + self._txt("s") + ", "
            + self._txt("b") + ", " + self._txt("t") + ", "
            + self._txt("c") + ", " + self._txt("r") + ") "
            "ON CONFLICT (breaker_name) DO UPDATE SET state = "
            "EXCLUDED.state, tripped_by = EXCLUDED.tripped_by, "
            "tripped_at_logical = EXCLUDED.tripped_at_logical, "
            "cool_down_until = EXCLUDED.cool_down_until, "
            "last_reason = EXCLUDED.last_reason",
            {"n": row["breaker_name"], "s": row["state"],
             "b": row.get("tripped_by"),
             "t": row.get("tripped_at_logical"),
             "c": row.get("cool_down_until"),
             "r": row.get("last_reason")})

    def get_breaker(self, name: str) -> Optional[Dict]:
        rows = self._exec(
            "SELECT breaker_name || chr(31) || state || chr(31) || "
            "coalesce(tripped_by, '') || chr(31) || "
            "coalesce(tripped_at_logical, '') || chr(31) || "
            "coalesce(cool_down_until, '') || chr(31) || "
            "coalesce(last_reason, '') || chr(31) || 'END' FROM "
            "admin.circuit_breakers WHERE breaker_name = "
            + self._txt("n"), {"n": name}).strip()
        if not rows:
            return None
        p = rows.split("\x1f")
        if len(p) < 6 or p[-1] != "END":
            return None
        return {"breaker_name": p[0], "state": p[1],
                "tripped_by": p[2] or None,
                "tripped_at_logical": p[3] or None,
                "cool_down_until": p[4] or None,
                "last_reason": p[5] or None}

    def all_breakers(self) -> Dict[str, Dict]:
        rows = self._exec(
            "SELECT breaker_name || chr(31) || state || chr(31) || "
            "coalesce(last_reason, '') || chr(31) || 'END' FROM "
            "admin.circuit_breakers ORDER BY breaker_name", {})
        out = {}
        for line in rows.splitlines():
            p = line.strip().split("\x1f")
            if len(p) >= 4 and p[-1] == "END":
                out[p[0]] = {"breaker_name": p[0], "state": p[1],
                             "last_reason": p[2] or None}
        return out


def default_vault():
    try:
        vault = _PgVault()
        vault._exec("SELECT 1", {})
        return vault
    except Exception:
        import os
        return _JsonVault(os.path.join("local", "volumes", "admin"))


# --- engine ------------------------------------------------------------------------

class ControlPlaneEngine:
    """D-110/D-112 core. handlers: injected command handlers keyed
    by command (executed only after validation + RBAC + lock)."""

    def __init__(self, store, vault=None,
                 handlers: Optional[Dict[str, Callable]] = None):
        self._store = store
        self._vault = vault or default_vault()
        self._handlers = dict(handlers or {})

    def register_handler(self, command: str, fn: Callable) -> None:
        self._handlers[command] = fn

    # -- durable audit (D-027) ------------------------------------------------

    @staticmethod
    def _eid(kind: str, ident: str, seq: int = 0) -> str:
        return f"admin|{kind}|{ident}|{int(seq)}"

    def _record(self, eid: str, ref: Dict) -> bool:
        verdict = self._store.receive(SOURCE_SYSTEM, eid, OP_ADMIN, ref)
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

    # -- operator audit chain (D-112) ----------------------------------------------

    def _audit_append(self, action_id: str, kind: str, actor: str,
                      command: Optional[str], target: Optional[str],
                      detail: Dict, logical_at: str) -> None:
        prev = self._vault.last_audit_hash()
        seq = self._vault.max_audit_seq() + 1
        body = {"kind": kind, "command": command, "target": target,
                "detail": detail}
        rh = _row_hash(action_id, seq, body, prev, logical_at)
        self._vault.append_audit({
            "audit_seq": seq, "action_id": action_id,
            "event_kind": kind, "actor": actor, "command": command,
            "target": target, "detail": detail, "prev_hash": prev,
            "row_hash": rh, "logical_at": logical_at})

    def append_external_audit(self, action_id: str, kind: str,
                              actor: str, detail: Dict,
                              logical_at: str) -> Dict:
        """Append a NON-COMMAND external event to the operator audit
        chain (Phase 26: launch approvals, break-glass, promotion,
        rollback). Same hash-chained row shape as command audits
        (D-112 tamper-evidence); NOT an action execution — nothing is
        dispatched, no confirmation key is involved."""
        from .admin_contracts import parse_actor
        parse_actor(actor)               # validates the role token
        if not isinstance(action_id, str) or not action_id or \
                len(action_id) > MAX_ACTION_ID_LEN:
            raise AdminContractError("action_id invalid or too long")
        if not isinstance(kind, str) or not kind:
            raise AdminContractError("kind required")
        self._audit_append(action_id, kind, actor, None, None,
                           detail or {}, logical_at)
        return {"ok": True, "kind": kind, "action_id": action_id}

    def verify_chain(self) -> Dict:
        """Tamper-evidence over the GLOBAL operator chain (D-112)."""
        prev = ""
        count = 0
        for r in self._vault.audit_rows():
            body = {"kind": r["event_kind"], "command": r["command"],
                    "target": r["target"], "detail": r["detail"]}
            expect = _row_hash(r["action_id"], int(r["audit_seq"]),
                               body, prev, r["logical_at"])
            if r["prev_hash"] != prev or r["row_hash"] != expect:
                return {"ok": False,
                        "broken_at_seq": r["audit_seq"],
                        "reason": "chain_mismatch"}
            prev = r["row_hash"]
            count += 1
        return {"ok": True, "rows": count}

    # -- action execution (D-110) -----------------------------------------------------

    def execute(self, action: Dict) -> Dict:
        """Validate → RBAC (in the validator) → PK-as-lock insert →
        handler dispatch → APPLIED. Exactly-once: a repeated action
        id is a DUPLICATE with zero side-effects."""
        validate_action(action)
        mode = replay_mode(action) \
            if action["command"] == CMD_REPLAY_EVENTS else None
        row = {
            "action_id": action["action_id"],
            "command": action["command"],
            "target": action["target"],
            "actor": action["actor"],
            "reason": action.get("reason"),
            "status": "RECEIVED",
            "mode": mode,
            "confirmation_key_hash": _key_hash(
                action["confirmation_key"])
            if action.get("confirmation_key") else None,
            "detail": action.get("detail", {}),
            "created_at_logical": action["created_at_logical"],
            "applied_at_logical": None,
        }
        result = self._vault.insert_action(row)
        if result == "duplicate":
            return {"ok": False, "reason": "duplicate_action",
                    "status": "DUPLICATE"}
        self._audit_append(
            action["action_id"], "action_received", action["actor"],
            action["command"], action["target"],
            {"reason": action.get("reason"), "mode": mode},
            action["created_at_logical"])
        self._record(self._eid("action", action["action_id"]), {
            "kind": "operator_action", "action_id":
            action["action_id"], "command": action["command"],
            "target": action["target"], "actor": action["actor"],
            "mode": mode})
        handler = self._handlers.get(action["command"])
        if handler is None:
            return {"ok": False, "reason": "no_handler",
                    "command": action["command"]}
        # REPLAY APPLY-mode: the confirmation key is SINGLE-USE per
        # KEY VALUE, not per action id — the burn is recorded in the
        # tamper-evident audit chain and any later action presenting
        # the same key is refused (D-110). Burn happens BEFORE
        # dispatch: a crash mid-apply leaves replay locked, never
        # unlocked.
        if action["command"] == CMD_REPLAY_EVENTS and \
                mode == "APPLY":
            key_hash = _key_hash(action["confirmation_key"])
            if self._key_already_burned(key_hash):
                return {"ok": False, "reason": "key_already_burned"}
            if not self._vault.burn_key(action["action_id"]):
                return {"ok": False, "reason": "key_already_burned"}
            self._audit_append(
                action["action_id"], "replay_key_burned",
                action["actor"], action["command"],
                action["target"], {"key_hash": key_hash},
                action["created_at_logical"])
        try:
            # the handler envelope carries the computed mode: a
            # REPLAY_EVENTS handler performs its READ-ONLY report in
            # DRY_RUN and its mutation only in APPLY (D-110)
            handler_result = handler(dict(action, mode=mode))
        except Exception as exc:  # recorded, never silent
            self._audit_append(
                action["action_id"], "action_failed",
                action["actor"], action["command"],
                action["target"], {"error": str(exc)[:300]},
                action["created_at_logical"])
            self._record(self._eid("failed", action["action_id"]), {
                "kind": "operator_action_failed",
                "action_id": action["action_id"],
                "error": str(exc)[:300]})
            return {"ok": False, "reason": "handler_raised",
                    "detail": str(exc)[:300]}
        applied = self._vault.mark_applied(
            action["action_id"],
            {"applied_at_logical": action["created_at_logical"]})
        self._audit_append(
            action["action_id"], "action_applied", action["actor"],
            action["command"], action["target"],
            {"handler_result": handler_result
             if isinstance(handler_result, dict) else None},
            action["created_at_logical"])
        return {"ok": True, "status": "APPLIED" if applied else
                "DUPLICATE", "mode": mode,
                "result": handler_result
                if isinstance(handler_result, dict) else None}

    def _key_already_burned(self, key_hash: str) -> bool:
        for r in self._vault.audit_rows():
            if r["event_kind"] == "replay_key_burned" and \
                    r["detail"].get("key_hash") == key_hash:
                return True
        return False

    # -- state facade (D-110: injected reads, no domain imports) ----------------------

    def diagnostic_report(self, readers: Dict[str, Callable],
                          logical_now: str) -> Dict:
        """Aggregate durable state across domains via INJECTED read
        callables: queues, hitl, insights, assets, breakers."""
        domains = {}
        errors = {}
        for name, reader in readers.items():
            try:
                domains[name] = reader()
            except Exception as exc:
                # a failed reader contributes to reader_errors ONLY
                # (never a None cell in domains — the report's domain
                # set stays a clean subset of REPORT_DOMAINS)
                errors[name] = str(exc)[:200]
        report = {"generated_at_logical": logical_now,
                  "domains": domains, "reader_errors": errors}
        return validate_report(report)

    # -- queries (D-110) -----------------------------------------------------------------

    def query_actions(self, flt: Optional[Dict] = None) -> List[Dict]:
        flt = validate_query_filter(flt or {})
        rows = list(self._vault.all_actions().values())
        if "actor" in flt:
            rows = [r for r in rows if r["actor"] == flt["actor"]]
        if "command" in flt:
            rows = [r for r in rows if r["command"] == flt["command"]]
        if "target" in flt:
            rows = [r for r in rows if r["target"] == flt["target"]]
        if "since_logical" in flt:
            rows = [r for r in rows
                    if r["created_at_logical"] >= flt["since_logical"]]
        if "until_logical" in flt:
            rows = [r for r in rows
                    if r["created_at_logical"] <= flt["until_logical"]]
        rows.sort(key=lambda r: (r["created_at_logical"],
                                 r["action_id"]))
        limit = flt.get("limit", len(rows))
        return rows[:limit]

    def audit(self, flt: Optional[Dict] = None) -> List[Dict]:
        flt = validate_query_filter(flt or {})
        rows = self._vault.audit_rows()
        if "actor" in flt:
            rows = [r for r in rows if r["actor"] == flt["actor"]]
        if "since_logical" in flt:
            rows = [r for r in rows
                    if r["logical_at"] >= flt["since_logical"]]
        if "until_logical" in flt:
            rows = [r for r in rows
                    if r["logical_at"] <= flt["until_logical"]]
        limit = flt.get("limit", len(rows))
        return rows[:limit]

    def action(self, action_id: str) -> Optional[Dict]:
        return self._vault.get_action(action_id)

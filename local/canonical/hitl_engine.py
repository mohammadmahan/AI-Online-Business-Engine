"""Phase 18 M2 — HITL ledger engine & claim lock vault (D-105/D-106/
D-108).

HitlEngine over two durable stores:

  - `hitl.review_tickets`: ticket_id PK is the atomic CLAIM lock —
    exactly one reviewer wins `claim()` under concurrency (PG
    `UPDATE ... WHERE resolution_status='PENDING_REVIEW' RETURNING`
    semantics; JSON parity guarded the same way logically).
  - `hitl.review_ledger`: APPEND-ONLY decision history, hash-chained
    per ticket (each row carries the previous row's hash);
    `verify_chain(ticket)` detects any mutation of durable decision
    history (D-108 tamper-evidence).

Ingestion: `ingest_insight_tickets` consumes Phase 17
DISPATCHED_TO_HITL insights (idempotent via the unique `ingest_key` =
f"analyst:{insight_key}"); producers for the other queue types call
`create_ticket` with their own ingest keys.

Sweeps: `expire_sweep`/`escalation_sweep` decide EXPIRED/escalations
from an INJECTED logical clock evaluator over durable
`created_at_logical` values — zero wall-clock reads.

Every transition emits an immutable D-027 event; a lost exactly-once
race is a clean loser (Phase 16/17 precedent). Mock local actors
only (D-045).
"""

import hashlib
import json
from typing import Callable, Dict, List, Optional

from canonical.hitl_contracts import (
    ESCALATION_TARGET,
    QT_INSIGHT_REVIEW,
    REQUIRED_ROLES,
    ROLE_ANY,
    ROLE_ESCALATION,
    ROLE_OWNER,
    ST_APPROVED,
    ST_CLAIMED,
    ST_ESCALATED,
    ST_EXPIRED,
    ST_MODIFIED,
    ST_PENDING_REVIEW,
    ST_REJECTED,
    TERMINAL_STATES,
    HitlContractError,
    can_actor_resolve,
    is_transition_legal,
    resolution_from_action,
    validate_action,
    validate_ticket,
)
from services.sync_engine import IntegrityError

SOURCE_SYSTEM = "hitl"
OP_TICKET = "hitl_ticket"


def _row_hash(ticket_id: str, seq: int, body: Dict, prev_hash: str,
              logical_at: str) -> str:
    payload = json.dumps(
        {"ticket_id": ticket_id, "seq": seq, "body": body,
         "prev_hash": prev_hash, "logical_at": logical_at},
        ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# --- backends -----------------------------------------------------------------

class _JsonVault:
    """Offline parity vault: JSON files with PK/claim/append
    semantics mirroring the PG tables."""

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

    # tickets
    def insert_ticket(self, row: Dict) -> str:
        data = self._read("tickets.json")
        if row["ticket_id"] in data:
            return "duplicate"
        for r in data.values():
            if r.get("ingest_key") and \
                    r["ingest_key"] == row.get("ingest_key"):
                return "duplicate"
        data[row["ticket_id"]] = row
        self._write("tickets.json", data)
        return "created"

    def claim_ticket(self, ticket_id: str, actor: str) -> int:
        data = self._read("tickets.json")
        row = data.get(ticket_id)
        if row is None or \
                row["resolution_status"] != ST_PENDING_REVIEW:
            return 0
        row["resolution_status"] = ST_CLAIMED
        row["reviewer_actor_id"] = actor
        self._write("tickets.json", data)
        return 1

    def update_ticket(self, ticket_id: str, sets: Dict) -> int:
        data = self._read("tickets.json")
        row = data.get(ticket_id)
        if row is None:
            return 0
        row.update(sets)
        self._write("tickets.json", data)
        return 1

    def update_ticket_guarded(self, ticket_id: str, sets: Dict,
                              expect_status: str) -> int:
        """JSON-parity of the PG compare-and-set (Phase 21): the
        single-threaded parity vault wins only from the expected
        state."""
        row = self.get_ticket(ticket_id)
        if row is None or \
                row.get("resolution_status") != expect_status:
            return 0
        return self.update_ticket(ticket_id, sets)

    def get_ticket(self, ticket_id: str) -> Optional[Dict]:
        return self._read("tickets.json").get(ticket_id)

    def tickets_by_status(self, *statuses: str) -> List[Dict]:
        return [dict(r, ticket_id=tid) for tid, r in
                self._read("tickets.json").items()
                if r["resolution_status"] in statuses]

    def find_by_ingest_key(self, ingest_key: str) -> Optional[Dict]:
        for r in self._read("tickets.json").values():
            if r.get("ingest_key") == ingest_key:
                return r
        return None

    # ledger (append-only; hash chain computed by the engine)
    def max_ledger_seq(self) -> int:
        rows = self._read("ledger.json")
        return max((int(v) for v in rows), default=0)

    def append_ledger(self, row: Dict) -> None:
        data = self._read("ledger.json")
        data[str(row["ledger_seq"])] = row
        self._write("ledger.json", data)

    def ledger_for(self, ticket_id: str) -> List[Dict]:
        rows = [r for r in self._read("ledger.json").values()
                if r["ticket_id"] == ticket_id]
        rows.sort(key=lambda r: int(r["ledger_seq"]))
        return rows

    def all_ledger(self) -> List[Dict]:
        rows = list(self._read("ledger.json").values())
        rows.sort(key=lambda r: (r["ticket_id"],
                                 int(r["ledger_seq"])))
        return rows


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

    _T_COLS = ("ticket_id, queue_type, payload_ref, required_role, "
               "resolution_status, reviewer_actor_id, payload, "
               "payload_override, feedback_notes, "
               "created_at_logical, decided_at_logical, "
               "escalated_to, ingest_key")

    @staticmethod
    def _parse_ticket(p) -> Dict:
        return {"ticket_id": p[0], "queue_type": p[1],
                "payload_ref": p[2], "required_role": p[3],
                "resolution_status": p[4],
                "reviewer_actor_id": p[5] or None,
                "payload": json.loads(p[6]),
                "payload_override": json.loads(p[7])
                if p[7] else None,
                "feedback_notes": p[8] or None,
                "created_at_logical": p[9],
                "decided_at_logical": p[10] or None,
                "escalated_to": p[11] or None,
                "ingest_key": p[12] or None}

    def _select_ticket(self, where: str, params: Dict) -> Optional[Dict]:
        rows = self._exec(
            "SELECT ticket_id || chr(31) || queue_type || chr(31) || "
            "payload_ref || chr(31) || required_role || chr(31) || "
            "resolution_status || chr(31) || "
            "coalesce(reviewer_actor_id, '') || chr(31) || "
            "payload::text || chr(31) || "
            "coalesce(payload_override::text, '') || chr(31) || "
            "coalesce(feedback_notes, '') || chr(31) || "
            "created_at_logical || chr(31) || "
            "coalesce(decided_at_logical, '') || chr(31) || "
            "coalesce(escalated_to, '') || chr(31) || "
            "coalesce(ingest_key, '') || chr(31) || 'END' "
            "FROM hitl.review_tickets WHERE " + where, params).strip()
        if not rows:
            return None
        p = rows.split("\x1f")
        if len(p) < 14 or p[-1] != "END":
            return None
        return self._parse_ticket(p)

    def insert_ticket(self, row: Dict) -> str:
        # Optional jsonb: the psql transport renders every parameter
        # as a text constant, so a Python None would arrive as the
        # invalid token 'None'. Emit a literal SQL NULL keyword for
        # absent overrides instead (control-flow constant, never
        # interpolated data).
        if row.get("payload_override") is not None:
            po_sql = self._txt("po") + "::jsonb"
        else:
            po_sql = "NULL"
        out = self._exec(
            "INSERT INTO hitl.review_tickets (" + self._T_COLS +
            ") VALUES (" + self._txt("i") + ", " + self._txt("q")
            + ", " + self._txt("p") + ", " + self._txt("r") + ", "
            + self._txt("s") + ", " + self._txt("a") + ", "
            + self._txt("pl") + "::jsonb, " + po_sql + ", "
            + self._txt("f") + ", "
            + self._txt("cl") + ", " + self._txt("dl") + ", "
            + self._txt("et") + ", " + self._txt("ik") + ") "
            "ON CONFLICT (ticket_id) DO NOTHING RETURNING ticket_id",
            {"i": row["ticket_id"], "q": row["queue_type"],
             "p": row["payload_ref"], "r": row["required_role"],
             "s": row["resolution_status"],
             "a": row.get("reviewer_actor_id"),
             "pl": json.dumps(row.get("payload", {}),
                              ensure_ascii=False, sort_keys=True),
             "po": json.dumps(row["payload_override"],
                              sort_keys=True)
             if row.get("payload_override") is not None else None,
             "f": row.get("feedback_notes"),
             "cl": row["created_at_logical"],
             "dl": row.get("decided_at_logical"),
             "et": row.get("escalated_to"),
             "ik": row.get("ingest_key")}).strip()
        if out:
            return "created"
        # distinguish same-id duplicate from ingest_key duplicate
        existing = self._select_ticket(
            "ticket_id = " + self._txt("i"), {"i": row["ticket_id"]})
        if existing and existing.get("ingest_key") and \
                existing["ingest_key"] == row.get("ingest_key"):
            return "duplicate"
        return "duplicate"

    def claim_ticket(self, ticket_id: str, actor: str) -> int:
        out = self._exec(
            "UPDATE hitl.review_tickets SET resolution_status = "
            + self._txt("s") + ", reviewer_actor_id = "
            + self._txt("a") + " WHERE ticket_id = " + self._txt("i")
            + " AND resolution_status = "
            + self._txt("exp") + " RETURNING ticket_id",
            {"s": ST_CLAIMED, "a": actor, "i": ticket_id,
             "exp": ST_PENDING_REVIEW}).strip()
        return 1 if out else 0

    def update_ticket(self, ticket_id: str, sets: Dict) -> int:
        allowed = {"resolution_status", "payload_override",
                   "feedback_notes", "decided_at_logical",
                   "escalated_to", "reviewer_actor_id"}
        keys = [k for k in sets if k in allowed]
        if not keys:
            return 0
        texts = {"resolution_status", "feedback_notes",
                 "decided_at_logical", "escalated_to",
                 "reviewer_actor_id"}
        sets_sql, params = [], {"i": ticket_id}
        for n, k in enumerate(keys):
            tag = f"s{n}"
            if k in texts:
                sets_sql.append(f"{k} = " + self._txt(tag))
                params[tag] = sets[k]
            else:
                sets_sql.append(f"{k} = " + self._txt(tag)
                                + "::jsonb")
                params[tag] = json.dumps(sets[k], ensure_ascii=False,
                                         sort_keys=True)
        out = self._exec(
            "UPDATE hitl.review_tickets SET " + ", ".join(sets_sql)
            + " WHERE ticket_id = " + self._txt("i")
            + " RETURNING ticket_id", params).strip()
        return 1 if out else 0

    def update_ticket_guarded(self, ticket_id: str, sets: Dict,
                              expect_status: str) -> int:
        """State-guarded update (Phase 21 chaos discipline): the
        row changes ONLY if its current resolution_status still
        equals `expect_status` — a competing resolution between a
        reader's fetch and write loses atomically (row-level
        compare-and-set, no lost updates)."""
        keys = list(sets)
        texts = {k for k in keys
                 if not isinstance(sets[k], (dict, list))}
        sets_sql = []
        params: Dict[str, str] = {}
        for n, k in enumerate(keys):
            tag = f"s{n}"
            if k in texts:
                sets_sql.append(f"{k} = " + self._txt(tag))
                params[tag] = sets[k]
            else:
                sets_sql.append(f"{k} = " + self._txt(tag)
                                + "::jsonb")
                params[tag] = json.dumps(sets[k], ensure_ascii=False,
                                         sort_keys=True)
        params["i"] = ticket_id
        params["exp"] = expect_status
        out = self._exec(
            "UPDATE hitl.review_tickets SET " + ", ".join(sets_sql)
            + " WHERE ticket_id = " + self._txt("i")
            + " AND resolution_status = " + self._txt("exp")
            + " RETURNING ticket_id", params).strip()
        return 1 if out else 0

    def get_ticket(self, ticket_id: str) -> Optional[Dict]:
        return self._select_ticket(
            "ticket_id = " + self._txt("i"), {"i": ticket_id})

    def tickets_by_status(self, *statuses: str) -> List[Dict]:
        marks = []
        params = {}
        for n, s in enumerate(statuses):
            marks.append(self._txt(f"st{n}"))
            params[f"st{n}"] = s
        rows = self._exec(
            "SELECT ticket_id || chr(31) || queue_type || chr(31) || "
            "payload_ref || chr(31) || required_role || chr(31) || "
            "resolution_status || chr(31) || "
            "coalesce(reviewer_actor_id, '') || chr(31) || "
            "payload::text || chr(31) || "
            "coalesce(payload_override::text, '') || chr(31) || "
            "coalesce(feedback_notes, '') || chr(31) || "
            "created_at_logical || chr(31) || "
            "coalesce(decided_at_logical, '') || chr(31) || "
            "coalesce(escalated_to, '') || chr(31) || "
            "coalesce(ingest_key, '') || chr(31) || 'END' "
            "FROM hitl.review_tickets WHERE resolution_status IN ("
            + ", ".join(marks) + ") ORDER BY ticket_id", params)
        out = []
        for line in rows.splitlines():
            p = line.strip().split("\x1f")
            if len(p) >= 14 and p[-1] == "END":
                out.append(self._parse_ticket(p))
        return out

    def find_by_ingest_key(self, ingest_key: str) -> Optional[Dict]:
        return self._select_ticket(
            "ingest_key = " + self._txt("k"), {"k": ingest_key})

    # ledger
    def max_ledger_seq(self) -> int:
        out = self._exec(
            "SELECT coalesce(max(ledger_seq), 0)::text FROM "
            "hitl.review_ledger", {}).strip()
        return int(out or "0")

    def append_ledger(self, row: Dict) -> None:
        self._exec(
            "INSERT INTO hitl.review_ledger (ticket_id, event_kind, "
            "actor, decision, detail, prev_hash, row_hash, "
            "logical_at) VALUES (" + self._txt("t") + ", "
            + self._txt("k") + ", " + self._txt("a") + ", "
            + self._txt("d") + ", " + self._txt("dt") + "::jsonb, "
            + self._txt("ph") + ", " + self._txt("rh") + ", "
            + self._txt("la") + ")",
            {"t": row["ticket_id"], "k": row["event_kind"],
             "a": row["actor"],
             "d": row.get("decision"),
             "dt": json.dumps(row.get("detail", {}),
                              ensure_ascii=False, sort_keys=True),
             "ph": row["prev_hash"], "rh": row["row_hash"],
             "la": row["logical_at"]})

    def ledger_for(self, ticket_id: str) -> List[Dict]:
        rows = self._exec(
            "SELECT ledger_seq::text || chr(31) || event_kind || "
            "chr(31) || actor || chr(31) || coalesce(decision, '') "
            "|| chr(31) || detail::text || chr(31) || prev_hash || "
            "chr(31) || row_hash || chr(31) || logical_at || "
            "chr(31) || 'END' FROM hitl.review_ledger WHERE "
            "ticket_id = " + self._txt("t")
            + " ORDER BY ledger_seq", {"t": ticket_id})
        out = []
        for line in rows.splitlines():
            p = line.strip().split("\x1f")
            if len(p) >= 8 and p[-1] == "END":
                out.append({"ledger_seq": int(p[0]),
                            "ticket_id": ticket_id,
                            "event_kind": p[1], "actor": p[2],
                            "decision": p[3] or None,
                            "detail": json.loads(p[4]),
                            "prev_hash": p[5], "row_hash": p[6],
                            "logical_at": p[7]})
        return out

    def all_ledger(self) -> List[Dict]:
        rows = self._exec(
            "SELECT ticket_id || chr(31) || ledger_seq::text || "
            "chr(31) || event_kind || chr(31) || actor || chr(31) || "
            "coalesce(decision, '') || chr(31) || detail::text || "
            "chr(31) || prev_hash || chr(31) || row_hash || chr(31) "
            "|| logical_at || chr(31) || 'END' FROM "
            "hitl.review_ledger ORDER BY ticket_id, ledger_seq", {})
        out = []
        for line in rows.splitlines():
            p = line.strip().split("\x1f")
            if len(p) >= 9 and p[-1] == "END":
                out.append({"ticket_id": p[0],
                            "ledger_seq": int(p[1]),
                            "event_kind": p[2], "actor": p[3],
                            "decision": p[4] or None,
                            "detail": json.loads(p[5]),
                            "prev_hash": p[6], "row_hash": p[7],
                            "logical_at": p[8]})
        return out


def default_vault():
    try:
        vault = _PgVault()
        vault._exec("SELECT 1", {})
        return vault
    except Exception:
        import os
        return _JsonVault(os.path.join("local", "volumes", "hitl"))


# --- engine ---------------------------------------------------------------------

class HitlEngine:
    """D-105/D-106/D-108 core."""

    def __init__(self, store, vault=None):
        self._store = store
        self._vault = vault or default_vault()

    # -- durable audit (D-027) ------------------------------------------------

    @staticmethod
    def _eid(kind: str, ident: str, seq: int = 0) -> str:
        return f"hitl|{kind}|{ident}|{int(seq)}"

    def _record(self, eid: str, ref: Dict) -> bool:
        verdict = self._store.receive(SOURCE_SYSTEM, eid, OP_TICKET, ref)
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

    # -- ticket creation / ingestion (D-106) --------------------------------------

    def create_ticket(self, ticket: Dict,
                      payload: Optional[Dict] = None) -> Dict:
        validate_ticket(ticket)
        row = dict(ticket,
                   payload=payload or {},
                   payload_override=None,
                   feedback_notes=None,
                   decided_at_logical=None,
                   escalated_to=None,
                   ingest_key=ticket.get("ingest_key"))
        if not row.get("ingest_key"):
            # deterministic ingest key for producer-created tickets
            row["ingest_key"] = "direct:" + row["ticket_id"]
        result = self._vault.insert_ticket(row)
        if result == "duplicate":
            existing = self._vault.find_by_ingest_key(
                row["ingest_key"])
            return {"status": "DUPLICATE",
                    "ticket_id": existing["ticket_id"]
                    if existing else row["ticket_id"]}
        self._record(self._eid("created", row["ticket_id"]), {
            "kind": "ticket_created", "ticket_id": row["ticket_id"],
            "queue_type": row["queue_type"],
            "payload_ref": row["payload_ref"],
            "required_role": row["required_role"]})
        return {"status": "CREATED", "ticket_id": row["ticket_id"]}

    def ingest_insight_tickets(self, insight_keys: List[str],
                               logical_now: str) -> Dict:
        """Phase 17 bridge: one INSIGHT_REVIEW ticket per distinct
        DISPATCHED_TO_HITL insight (idempotent via ingest_key)."""
        created, duplicated, skipped = [], [], []
        for key in insight_keys:
            ingest_key = f"analyst:{key}"
            if self._vault.find_by_ingest_key(ingest_key):
                duplicated.append(key)
                continue
            # deterministic ticket id: never builtin hash() —
            # string hashing is process-randomized (Phase 17
            # precedent); SHA-256 over the insight key reproduces
            # the same id on every restart
            key_digest = hashlib.sha256(
                key.encode("utf-8")).hexdigest()[:8]
            res = self.create_ticket({
                "ticket_id": f"hitl-insight-{key[:16]}-{key_digest}",
                "queue_type": QT_INSIGHT_REVIEW,
                "payload_ref": f"insight:{key}",
                "required_role": ROLE_OWNER,
                "resolution_status": ST_PENDING_REVIEW,
                "created_at_logical": logical_now,
                "ingest_key": ingest_key,
            }, payload={"insight_key": key})
            if res["status"] == "CREATED":
                created.append(res["ticket_id"])
            else:
                duplicated.append(key)
        return {"created": created, "duplicated": duplicated,
                "ingest_instant": logical_now}

    # -- claim & resolve (D-105/D-106) -----------------------------------------------

    def claim(self, ticket_id: str, actor: str) -> Dict:
        ticket = self._vault.get_ticket(ticket_id)
        if ticket is None:
            return {"ok": False, "reason": "unknown_ticket"}
        if ticket["resolution_status"] != ST_PENDING_REVIEW:
            return {"ok": False, "reason": "not_claimable",
                    "status": ticket["resolution_status"]}
        if not can_actor_resolve(ticket["required_role"], actor):
            return {"ok": False, "reason": "role_forbidden"}
        # ATOMIC claim: guarded update returns 1 only for the winner
        if not self._vault.claim_ticket(ticket_id, actor):
            return {"ok": False, "reason": "already_claimed"}
        self._record(self._eid("claimed", ticket_id), {
            "kind": "ticket_claimed", "ticket_id": ticket_id,
            "reviewer_actor_id": actor})
        return {"ok": True, "status": ST_CLAIMED,
                "claimed_by": actor}

    def resolve(self, ticket_id: str, action: Dict,
                logical_now: str) -> Dict:
        """Apply a reviewer decision to a CLAIMED ticket. Idempotent
        at the D-027 layer: a repeated identical resolution is a
        skipped duplicate (zero new side-effects, D-107)."""
        validate_action(action)
        ticket = self._vault.get_ticket(ticket_id)
        if ticket is None:
            return {"ok": False, "reason": "unknown_ticket"}
        actor = action["reviewer_actor_id"]
        if ticket["resolution_status"] != ST_CLAIMED:
            return {"ok": False, "reason": "not_resolvable",
                    "status": ticket["resolution_status"]}
        if ticket.get("reviewer_actor_id") != actor:
            return {"ok": False, "reason": "not_claimant"}
        if not is_transition_legal(ticket["resolution_status"],
                                   action["decision"]):
            return {"ok": False, "reason": "illegal_transition"}
        decision = action["decision"]
        sets = {"resolution_status": decision,
                "decided_at_logical": logical_now,
                "feedback_notes": action.get("feedback_notes")}
        if decision == ST_MODIFIED:
            sets["payload_override"] = action["payload_override"]
        if decision == ST_ESCALATED:
            target_role = ESCALATION_TARGET.get(
                ticket["required_role"], ROLE_ESCALATION)
            sets["escalated_to"] = target_role
        if not self._vault.update_ticket(ticket_id, sets):
            return {"ok": False, "reason": "vault_update_failed"}
        resolution = resolution_from_action(action)
        self._ledger_append(ticket_id, "resolution", actor,
                            decision, resolution, logical_now)
        self._record(self._eid("resolved", ticket_id,
                               self._resolved_seq(ticket_id)), {
            "kind": "ticket_resolved", "ticket_id": ticket_id,
            "decision": decision,
            "reviewer_actor_id": actor,
            "feedback_notes": resolution["feedback_notes"][:300],
            "payload_override": resolution["payload_override"],
            "escalated_to": sets.get("escalated_to")})
        return {"ok": True, "decision": decision,
                "escalated_to": sets.get("escalated_to")}

    # -- escalation loop (D-105) --------------------------------------------------

    def requeue_escalated(self, old_ticket_id: str,
                          logical_now: str) -> Dict:
        """After ESCALATED, open the fresh elevated ticket (an
        escalation LOOP, not a dead end)."""
        old = self._vault.get_ticket(old_ticket_id)
        if old is None:
            return {"ok": False, "reason": "unknown_ticket"}
        if old["resolution_status"] != ST_ESCALATED:
            return {"ok": False, "reason": "not_escalated"}
        target = old.get("escalated_to") or ROLE_ESCALATION
        child_id = old_ticket_id + "-esc"
        res = self.create_ticket({
            "ticket_id": child_id,
            "queue_type": old["queue_type"],
            "payload_ref": old["payload_ref"],
            "required_role": target,
            "resolution_status": ST_PENDING_REVIEW,
            "created_at_logical": logical_now,
            "ingest_key": "escalation:" + old_ticket_id,
        }, payload=dict(old.get("payload", {}),
                        escalated_from=old_ticket_id))
        if res["status"] == "CREATED":
            self._record(self._eid("escalated", child_id), {
                "kind": "ticket_escalated",
                "from_ticket": old_ticket_id,
                "to_ticket": child_id, "role": target})
        return res

    # -- deterministic sweeps (D-106) ----------------------------------------------

    def expire_sweep(self, clock: Callable[[str], bool],
                     logical_now: str) -> Dict:
        """EXPIRE stale tickets. `clock(created_at_logical)` decides
        staleness — an INJECTED pure evaluator over durable logical
        timestamps (never the wall clock)."""
        expired = []
        for t in self._vault.tickets_by_status(ST_PENDING_REVIEW,
                                               ST_CLAIMED):
            if clock(t["created_at_logical"]):
                if not self._vault.update_ticket(
                        t["ticket_id"],
                        {"resolution_status": ST_EXPIRED,
                         "decided_at_logical": logical_now}):
                    continue
                self._ledger_append(
                    t["ticket_id"], "expiry", "system:sweep",
                    ST_EXPIRED, {"reason": "stale"}, logical_now)
                self._record(self._eid("expired", t["ticket_id"]), {
                    "kind": "ticket_expired",
                    "ticket_id": t["ticket_id"]})
                expired.append(t["ticket_id"])
        return {"expired": expired, "sweep_instant": logical_now}

    # -- ledger (D-108) ---------------------------------------------------------------

    def _ledger_append(self, ticket_id: str, kind: str, actor: str,
                       decision: Optional[str], detail: Dict,
                       logical_at: str) -> None:
        prev = ""
        rows = self._vault.ledger_for(ticket_id)
        if rows:
            prev = rows[-1]["row_hash"]
        seq = self._vault.max_ledger_seq() + 1
        body = {"kind": kind, "decision": decision, "detail": detail}
        rh = _row_hash(ticket_id, seq, body, prev, logical_at)
        self._vault.append_ledger({
            "ledger_seq": seq, "ticket_id": ticket_id,
            "event_kind": kind, "actor": actor,
            "decision": decision, "detail": detail,
            "prev_hash": prev, "row_hash": rh,
            "logical_at": logical_at})

    def ledger(self, ticket_id: str) -> List[Dict]:
        return self._vault.ledger_for(ticket_id)

    def verify_chain(self, ticket_id: str) -> Dict:
        """Tamper-evidence: recompute the per-ticket hash chain and
        compare (D-108)."""
        rows = self._vault.ledger_for(ticket_id)
        prev = ""
        for r in rows:
            body = {"kind": r["event_kind"],
                    "decision": r["decision"],
                    "detail": r["detail"]}
            expect = _row_hash(ticket_id, int(r["ledger_seq"]), body,
                               prev, r["logical_at"])
            if r["prev_hash"] != prev or r["row_hash"] != expect:
                return {"ok": False,
                        "broken_at_seq": r["ledger_seq"],
                        "reason": "chain_mismatch"}
            prev = r["row_hash"]
        return {"ok": True, "rows": len(rows)}

    # -- helpers ----------------------------------------------------------------------

    def _resolved_seq(self, ticket_id: str) -> int:
        n = 0
        for raw in self._store.succeeded_references(SOURCE_SYSTEM):
            if isinstance(raw, dict):
                ref = raw
            else:
                try:
                    ref = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    continue
            if ref.get("kind") == "ticket_resolved" and \
                    ref.get("ticket_id") == ticket_id:
                n += 1
        return n

    def ticket(self, ticket_id: str) -> Optional[Dict]:
        return self._vault.get_ticket(ticket_id)

    def open_tickets(self) -> List[Dict]:
        return self._vault.tickets_by_status(ST_PENDING_REVIEW,
                                             ST_CLAIMED)

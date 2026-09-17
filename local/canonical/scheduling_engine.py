"""Phase 15 M2 — calendar engine (D-093/D-094/D-096).

SchedulingEngine: schedule (validate → slot claim → durable SCHEDULED
event), reschedule/cancel (pre-DISPATCHED only, full provenance), and
the calendar snapshot view rebuilt from DURABLE events alone. Slot
locks are provider-neutral: PG PK-as-lock (`scheduling.slot_lock`) or
JSON parity backend — injected (RULES §35). No wall clock anywhere
(D-093): due decisions take the injected clock in the worker, and
every recorded instant is supplied by the producer.
"""

import json
from typing import Dict, List, Optional, Tuple

from canonical.scheduling_contracts import (
    OP_SCHEDULE,
    REF_KIND_CONFLICT,
    REF_KIND_POST,
    REF_KIND_TRANSITION,
    ST_CANCELLED,
    ST_DISPATCHED,
    ST_DUE,
    ST_RESCHEDULED,
    ST_SCHEDULED,
    SchedulingContractError,
    TR_CANCEL,
    TR_DUE,
    TR_DISPATCH,
    TR_RESCHEDULE,
    TR_SCHEDULE,
    is_mutable,
    is_transition_legal,
    schedule_idempotency_key,
    slot_lock_key,
    validate_scheduled_post,
)


# --- slot lock backends ---------------------------------------------------------

class _JsonSlotLocks:
    """Offline parity: (platform, bucket) → claim row, file-backed."""

    def __init__(self, path: str):
        import pathlib
        self.path = str(path)
        pathlib.Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        import threading
        self._lock = threading.Lock()

    def _load(self) -> Dict[str, Dict]:
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

    def claim(self, key: str, row: Dict) -> Dict:
        with self._lock:
            data = self._load()
            existing = data.get(key)
            if existing and existing.get("active", True):
                return {"acquired": False, "holder": existing}
            # a released (superseded) slot is re-claimable — the row
            # stays as ledger history (D-096)
            rec = json.loads(json.dumps(row))
            rec["active"] = True
            data[key] = rec
            self._save(data)
            return {"acquired": True, "holder": rec}

    def supersede(self, key: str, post_id: str,
                  replacement: Tuple[str, str]) -> None:
        """D-096: the old slot row is NEVER deleted — it is marked
        inactive (superseded) and stays in the ledger; the replacement
        slot is claimed by the caller's subsequent claim()."""
        with self._lock:
            data = self._load()
            if key in data and data[key].get("post_id") == post_id:
                data[key]["active"] = False
                data[key]["superseded_by"] = "\x1f".join(replacement)
            self._save(data)

    def history(self) -> Dict[str, Dict]:
        with self._lock:
            return dict(self._load())


class _PgSlotLocks:
    """Live PG: PRIMARY KEY (platform, slot_bucket) IS the lock."""

    def __init__(self):
        import sys as _sys
        import os as _os
        scripts = _os.path.join("local", "scripts")
        if scripts not in _sys.path:
            _sys.path.insert(0, scripts)
        from canonical.notion_ingest import _exec, _txt  # noqa: E402
        self._exec = _exec
        self._txt = _txt

    def claim(self, key: str, row: Dict) -> Dict:
        platform, bucket = key.split("\x1f", 1)
        out = self._exec(
            "INSERT INTO scheduling.slot_lock (platform, slot_bucket, "
            "post_id, scheduled_for, active) VALUES (" + self._txt("p")
            + ", " + self._txt("b") + ", " + self._txt("i") + ", "
            + self._txt("s") + ", true) "
            "ON CONFLICT (platform, slot_bucket) DO UPDATE SET "
            "active = true, post_id = EXCLUDED.post_id, "
            "scheduled_for = EXCLUDED.scheduled_for, locked_at = now() "
            "WHERE scheduling.slot_lock.active = false "
            "RETURNING post_id || chr(31) || 'END'",
            {"p": platform, "b": bucket, "i": row.get("post_id", ""),
             "s": row.get("scheduled_for", "")}).strip()
        if out:
            return {"acquired": True, "holder": row}
        holder = self._exec(
            "SELECT post_id || chr(31) || scheduled_for || chr(31) || "
            "'END' FROM scheduling.slot_lock WHERE platform = "
            + self._txt("p") + " AND slot_bucket = " + self._txt("b"),
            {"p": platform, "b": bucket}).strip().split("\x1f")
        return {"acquired": False,
                "holder": {"post_id": holder[0],
                           "scheduled_for": holder[1]}}

    def supersede(self, key: str, post_id: str,
                  replacement: Tuple[str, str]) -> None:
        """Mark the old slot inactive (ledger history preserved,
        D-096); the caller claims the replacement slot via claim()."""
        self._exec(
            "UPDATE scheduling.slot_lock SET active = false "
            "WHERE platform = " + self._txt("p") + " AND slot_bucket = "
            + self._txt("b") + " AND post_id = " + self._txt("i"),
            {"p": key.split("\x1f")[0], "b": key.split("\x1f")[1],
             "i": post_id})

    def history(self) -> Dict[str, Dict]:
        rows = self._exec(
            "SELECT platform || chr(31) || slot_bucket || chr(31) || "
            "post_id || chr(31) || active::text || chr(31) || 'END' "
            "FROM scheduling.slot_lock ORDER BY platform, slot_bucket",
            {})
        out: Dict[str, Dict] = {}
        for line in rows.splitlines():
            parts = line.strip().split("\x1f")
            if len(parts) >= 5 and parts[-1] == "END":
                out["\x1f".join(parts[0:2])] = {
                    "post_id": parts[2], "active": parts[3] == "true"}
        return out


def default_slot_locks():
    try:
        backend = _PgSlotLocks()
        backend._exec("SELECT 1", {})
        return backend
    except Exception:
        import os
        return _JsonSlotLocks(os.path.join(
            "local", "volumes", "scheduling", "slot_locks.json"))


# --- engine ------------------------------------------------------------------------

class SchedulingEngine:
    """D-093/D-094/D-096 calendar core. store: D-027 store
    (PgEventStore or EventStore parity); locks: slot backend."""

    def __init__(self, store, locks=None):
        self._store = store
        self._locks = locks or default_slot_locks()

    # -- durable helpers ------------------------------------------------------

    def _refs(self) -> List[Dict]:
        out: List[Dict] = []
        for raw in self._store.succeeded_references("scheduling"):
            if isinstance(raw, dict):
                out.append(raw)
                continue
            try:
                out.append(json.loads(raw))
            except (json.JSONDecodeError, TypeError):
                continue
        return out

    @staticmethod
    def _eid(kind: str, post_id: str, seq: int = 0) -> str:
        return f"scheduling|{kind}|{post_id}|{int(seq)}"

    def _record(self, eid: str, ref: Dict) -> bool:
        """Durable write; returns False on an enqueued duplicate.
        A conflicting duplicate (same id, different payload) is NEVER
        swallowed — it surfaces as IntegrityError (D-027 human
        review), so callers must use attempt-unique event ids."""
        from services.sync_engine import IntegrityError
        try:
            verdict = self._store.receive("scheduling", eid,
                                          OP_SCHEDULE, ref)
        except IntegrityError:
            raise
        if verdict.get("verdict") == "skipped_duplicate":
            return False
        self._store.begin("scheduling", eid)
        self._store.succeed("scheduling", eid,
                            result_reference=json.dumps(
                                ref, ensure_ascii=False,
                                sort_keys=True))
        return True

    # -- schedule (D-093/D-094) --------------------------------------------------

    def schedule(self, post: Dict) -> Dict:
        """Validate → idempotency → slot claim → durable SCHEDULED.
        Returns a deterministic decision dict; slot conflicts are
        recorded Class-B rejections (D-094), never silent."""
        validate_scheduled_post(post)
        post = dict(post)
        post.setdefault("status", ST_SCHEDULED)
        key = schedule_idempotency_key(
            post["content_ref"], tuple(post["targets"]),
            post["scheduled_for"])

        eid = self._eid("schedule", post["post_id"])
        ref = dict(post, kind=REF_KIND_POST, idem_key=key)
        if not self._record(eid, ref):
            return {"status": ST_SCHEDULED, "retried": True,
                    "idem_key": key}

        # per-platform slot claims (D-094)
        conflicts: List[Dict] = []
        claimed: List[str] = []
        for platform in post["targets"]:
            skey = slot_lock_key(platform, post["scheduled_for"])
            res = self._locks.claim(skey, {
                "post_id": post["post_id"],
                "scheduled_for": post["scheduled_for"]})
            if res["acquired"]:
                claimed.append(skey)
            else:
                conflicts.append({
                    "platform": platform,
                    "slot": skey.split("\x1f")[1],
                    "held_by": res["holder"].get("post_id", "")})
        if conflicts:
            cref = {"kind": REF_KIND_CONFLICT,
                    "post_id": post["post_id"],
                    "conflicts": conflicts,
                    "scheduled_for": post["scheduled_for"]}
            self._record(self._eid("conflict", post["post_id"]), cref)
            return {"status": "SLOT_CONFLICT", "idem_key": key,
                    "conflicts": conflicts}
        return {"status": ST_SCHEDULED, "idem_key": key}

    # -- transitions (D-096) -------------------------------------------------------

    def _current_status(self, post_id: str) -> Tuple[str, Dict]:
        status, post = ST_SCHEDULED, {}
        for ref in self._refs():
            if ref.get("post_id") != post_id:
                continue
            kind = ref.get("kind")
            if kind == REF_KIND_POST:
                status = ST_SCHEDULED
                post = ref
            elif kind == REF_KIND_TRANSITION:
                st = ref.get("to_status")
                if st:
                    status = st
        if status == ST_RESCHEDULED:
            status = ST_SCHEDULED  # revision marker: still scheduled
        return status, post

    def _transition(self, post_id: str, tr: str, to_status: str,
                    extra: Dict, seq: int) -> Dict:
        current, post = self._current_status(post_id)
        if current and not is_transition_legal(current, to_status) \
                and to_status != ST_DUE:
            return {"ok": False, "reason": f"illegal_{current}_to_"
                    f"{to_status}", "current": current}
        ref = {"kind": REF_KIND_TRANSITION, "post_id": post_id,
               "transition": tr, "from_status": current,
               "to_status": to_status, "scheduled_for":
               post.get("scheduled_for"), "content_ref":
               post.get("content_ref"), **extra}
        if not self._record(self._eid(tr, post_id, seq), ref):
            return {"ok": False, "reason": "duplicate_transition"}
        return {"ok": True, "status": to_status, "ref": ref}

    def mark_due(self, post_id: str, now_iso: str) -> Dict:
        return self._transition(post_id, TR_DUE, ST_DUE,
                                {"now": now_iso}, 0)

    def cancel(self, post_id: str, actor: str) -> Dict:
        current, _ = self._current_status(post_id)
        if not is_mutable(current):
            return {"ok": False,
                    "reason": f"immutable_{current}", "current": current}
        return self._transition(post_id, TR_CANCEL, ST_CANCELLED,
                                {"actor": actor}, 0)

    def reschedule(self, post_id: str, new_scheduled_for: str,
                   actor: str) -> Dict:
        """SCHEDULED → RESCHEDULED. The NEW slots are claimed FIRST —
        a conflicting new slot is a slot_conflict rejection that does
        NOT change the post (D-094); on success the old slots are
        superseded (ledger history kept) and the transition recorded
        with the prior time (D-096)."""
        current, post = self._current_status(post_id)
        if not is_mutable(current):
            return {"ok": False,
                    "reason": f"immutable_{current}", "current": current}
        if not post:
            return {"ok": False, "reason": "unknown_post"}
        validate_scheduled_post(dict(post,
                                     scheduled_for=new_scheduled_for))
        from canonical.scheduling_contracts import slot_bucket as sb
        targets = post.get("targets", [])
        # claim the new slots first
        conflicts: List[Dict] = []
        claimed: List[str] = []
        for platform in targets:
            new_key = slot_lock_key(platform, new_scheduled_for)
            res = self._locks.claim(new_key, {
                "post_id": post_id,
                "scheduled_for": new_scheduled_for})
            if res["acquired"]:
                claimed.append(new_key)
            else:
                conflicts.append({"platform": platform,
                                  "slot": new_key.split("\x1f")[1],
                                  "held_by":
                                  res["holder"].get("post_id", "")})
        if conflicts:
            self._record(self._eid("conflict", post_id), {
                "kind": REF_KIND_CONFLICT, "post_id": post_id,
                "conflicts": conflicts,
                "scheduled_for": new_scheduled_for})
            return {"ok": False, "reason": "slot_conflict",
                    "conflicts": conflicts}
        # release the old slots (inactive; ledger keeps them)
        for platform in targets:
            old_key = slot_lock_key(platform, post["scheduled_for"])
            self._locks.supersede(old_key, post_id,
                                  (platform, sb(new_scheduled_for)))
        return self._transition(post_id, TR_RESCHEDULE,
                                ST_RESCHEDULED,
                                {"actor": actor,
                                 "previous_scheduled_for":
                                 post.get("scheduled_for"),
                                 "scheduled_for_new":
                                 new_scheduled_for},
                                self._reschedule_seq(post_id))

    def _reschedule_seq(self, post_id: str) -> int:
        """Attempt-unique sequence for reschedule events: count the
        prior reschedules durably (no clock, no randomness)."""
        n = 0
        for ref in self._refs():
            if ref.get("post_id") == post_id and \
                    ref.get("to_status") == ST_RESCHEDULED:
                n += 1
        return n

    # -- calendar view (D-096) ------------------------------------------------------

    def calendar_view(self) -> Dict[str, Dict]:
        """Rebuild post_id → {status, scheduled_for, targets} from
        DURABLE events alone — no in-process state (D-096)."""
        view: Dict[str, Dict] = {}
        for ref in self._refs():
            pid = ref.get("post_id")
            if not pid:
                continue
            kind = ref.get("kind")
            if kind == REF_KIND_POST:
                view[pid] = {"status": ST_SCHEDULED,
                             "scheduled_for": ref.get("scheduled_for"),
                             "targets": ref.get("targets"),
                             "content_ref": ref.get("content_ref")}
            elif kind == REF_KIND_CONFLICT:
                view.setdefault(pid, {"status": ST_SCHEDULED})
                view[pid]["slot_conflict"] = True
            elif kind == REF_KIND_TRANSITION:
                cur = view.setdefault(pid, {"status": ST_SCHEDULED})
                to = ref.get("to_status")
                if to == ST_RESCHEDULED:
                    cur["scheduled_for"] = ref.get("scheduled_for_new")
                    cur["rescheduled"] = True
                    cur["status"] = ST_SCHEDULED
                else:
                    cur["status"] = to
        return view

    # -- slot ledger (D-096) ------------------------------------------------------

    def slot_history(self) -> Dict[str, Dict]:
        return self._locks.history()

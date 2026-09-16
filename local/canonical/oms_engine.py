"""Phase 12 M2 — OMS engine (D-081/D-082/D-083).

Order placement and guarded lifecycle transitions on the D-027 store:
placement is idempotent by `client_order_id` (D-081), VALIDATED entry
atomically reserves inventory (D-082 — PG row-level conditional
UPDATE; over-sell is a deterministic outcome, never a partial state),
and fulfillment notifications ride the Phase 11 FanOutEngine boundary
(D-083) — a notification failure is captured per the D-077 isolation
rule and NEVER blocks or corrupts the order transition.

Payment stays a boundary: markers only, no gateway module, no
credentials (D-045/D-083).
"""

import json
import sys
from typing import Dict, List, Optional

from canonical.oms_contracts import (
    CANCELLED,
    COMPLETED,
    FULFILLING,
    INSUFFICIENT_STOCK,
    InventoryStore,
    ORDER_STATES,
    PLACED,
    REFUNDED,
    RELEASED,
    RESERVED,
    SOURCE_SYSTEM,
    VALIDATED,
    OmsContractError,
    order_idempotency_key,
    validate_order,
    validate_transition,
)

OP_ORDER = "order_transition"


# --- D-082 inventory implementations ---------------------------------------

class PgInventory(InventoryStore):
    """Live inventory on `oms.inventory` (D-055/D-082).

    Reservation is ONE guarded statement:
        UPDATE oms.inventory
           SET stock = stock - qty, reserved = reserved + qty
         WHERE stock_key = k AND stock >= qty
    The row lock serializes concurrent buyers; a rowcount of 0 means
    insufficient stock (deterministic outcome). Release is the exact
    inverse. No read-modify-write anywhere — no lost-update window.
    """

    def __init__(self):
        import os as _os
        scripts = _os.path.join("local", "scripts")
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        from canonical.notion_ingest import _exec, _txt  # noqa: E402
        self._exec = _exec
        self._txt = _txt

    def seed(self, variant_id: str, sku: str, stock: int) -> str:
        from canonical.oms_contracts import stock_key
        key = stock_key({"variant_id": variant_id, "sku": sku})
        # the integer must arrive as a pg-int4 literal, not a quoted
        # text parameter — cast explicitly at the boundary
        self._exec(
            "INSERT INTO oms.inventory (stock_key, variant_id, sku, stock) "
            "VALUES (" + self._txt("k") + ", " + self._txt("v") + ", "
            + self._txt("s") + ", " + self._txt("n") + "::int) "
            "ON CONFLICT (stock_key) DO UPDATE SET stock = "
            + self._txt("n") + "::int, updated_at = now()",
            {"k": key, "v": variant_id, "s": sku, "n": str(int(stock))})
        return key

    def available(self, stock_key: str) -> int:
        out = self._exec(
            "SELECT stock::text || chr(31) || 'END' FROM oms.inventory "
            "WHERE stock_key = " + self._txt("k"),
            {"k": stock_key}).strip()
        if not out:
            return 0
        parts = out.split("\x1f")
        return int(parts[0]) if parts and parts[-1] == "END" else 0

    def reserve(self, stock_key: str, quantity: int,
                order_ref: Dict) -> Dict:
        q = self._txt("q") + "::int"
        out = self._exec(
            "UPDATE oms.inventory SET stock = stock - "
            + q + ", reserved = reserved + "
            + q + ", updated_at = now() "
            "WHERE stock_key = " + self._txt("k")
            + " AND stock >= " + q
            + " RETURNING stock_key",
            {"k": stock_key, "q": str(int(quantity))}).strip()
        if out:
            return {"reserved": True, "stock_key": stock_key,
                    "quantity": quantity}
        return {"reserved": False, "reason": INSUFFICIENT_STOCK,
                "stock_key": stock_key, "quantity": quantity}

    def release(self, stock_key: str, quantity: int,
                order_ref: Dict) -> Dict:
        q = self._txt("q") + "::int"
        out = self._exec(
            "UPDATE oms.inventory SET stock = stock + "
            + q + ", reserved = reserved - "
            + q + ", updated_at = now() "
            "WHERE stock_key = " + self._txt("k")
            + " AND reserved >= " + q
            + " RETURNING stock_key",
            {"k": stock_key, "q": str(int(quantity))}).strip()
        if out:
            return {"released": True, "stock_key": stock_key,
                    "quantity": quantity}
        return {"released": False, "reason": "nothing_to_release",
                "stock_key": stock_key, "quantity": quantity}


class JsonInventory(InventoryStore):
    """Offline parity inventory (local tests): identical reserve/release
    verdict semantics, file-backed with a per-path module lock."""

    _PATH_LOCKS: Dict[str, object] = {}

    def __init__(self, path: str):
        import threading
        self.path = path
        lock = JsonInventory._PATH_LOCKS.get(path)
        if lock is None:
            lock = threading.Lock()
            JsonInventory._PATH_LOCKS[path] = lock
        self._lock = lock

    def _load(self) -> Dict:
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save(self, data: Dict) -> None:
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2,
                      sort_keys=True)
        import os
        os.replace(tmp, self.path)

    def seed(self, variant_id: str, sku: str, stock: int) -> str:
        from canonical.oms_contracts import stock_key
        key = stock_key({"variant_id": variant_id, "sku": sku})
        with self._lock:
            data = self._load()
            data[key] = {"variant_id": variant_id, "sku": sku,
                         "stock": stock, "reserved": 0}
            self._save(data)
        return key

    def available(self, stock_key: str) -> int:
        with self._lock:
            row = self._load().get(stock_key)
        return int(row["stock"]) if row else 0

    def reserve(self, stock_key: str, quantity: int,
                order_ref: Dict) -> Dict:
        with self._lock:
            data = self._load()
            row = data.get(stock_key)
            if not row or int(row["stock"]) < quantity:
                return {"reserved": False, "reason": INSUFFICIENT_STOCK,
                        "stock_key": stock_key, "quantity": quantity}
            row["stock"] = int(row["stock"]) - quantity
            row["reserved"] = int(row.get("reserved", 0)) + quantity
            self._save(data)
        return {"reserved": True, "stock_key": stock_key,
                "quantity": quantity}

    def release(self, stock_key: str, quantity: int,
                order_ref: Dict) -> Dict:
        with self._lock:
            data = self._load()
            row = data.get(stock_key)
            if not row or int(row.get("reserved", 0)) < quantity:
                return {"released": False,
                        "reason": "nothing_to_release",
                        "stock_key": stock_key, "quantity": quantity}
            row["stock"] = int(row["stock"]) + quantity
            row["reserved"] = int(row["reserved"]) - quantity
            self._save(data)
        return {"released": True, "stock_key": stock_key,
                "quantity": quantity}


# --- reservation ledger (D-082/D-084, JSON parity for offline tests) -------

class _ReservationLedger:
    """order_key → [(stock_key, quantity, state)] — durable release map
    so CANCELLED/REFUNDED/TTL-expiry return exactly what was reserved."""

    _PATH_LOCKS: Dict[str, object] = {}

    def __init__(self, path: str):
        import threading
        self.path = path
        lock = _ReservationLedger._PATH_LOCKS.get(path)
        if lock is None:
            lock = threading.Lock()
            _ReservationLedger._PATH_LOCKS[path] = lock
        self._lock = lock

    def _load(self) -> Dict:
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save(self, data: Dict) -> None:
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2,
                      sort_keys=True)
        import os
        os.replace(tmp, self.path)

    def record(self, order_key: str, entries: List[Dict]) -> None:
        with self._lock:
            data = self._load()
            data.setdefault(order_key, [])
            for e in entries:
                data[order_key].append(dict(e, state=RESERVED))
            self._save(data)

    def for_order(self, order_key: str) -> List[Dict]:
        with self._lock:
            return list(self._load().get(order_key, []))

    def mark_released(self, order_key: str) -> None:
        with self._lock:
            data = self._load()
            for e in data.get(order_key, []):
                e["state"] = RELEASED
            self._save(data)


# --- engine ------------------------------------------------------------------

class OmsEngine:
    """D-081/D-082/D-083 order lifecycle engine."""

    def __init__(self, store, inventory: InventoryStore,
                 ledger: Optional[_ReservationLedger] = None,
                 fanout_engine=None, provenance=None,
                 notification_targets: Optional[List[str]] = None):
        self.store = store
        self.inventory = inventory
        self.ledger = ledger
        self.fanout_engine = fanout_engine  # Phase 11 boundary (D-083)
        self.provenance = provenance
        # D-083: destinations configured by the CALLER (owner settings);
        # the OMS never invents notification destinations.
        self.notification_targets = list(notification_targets or [])

    # -- durable event plumbing -------------------------------------------

    def _record(self, event_id: str, ref: Dict, *,
                op: str = OP_ORDER) -> str:
        rec = self.store.receive(SOURCE_SYSTEM, event_id, op, ref)
        if rec["verdict"] == "integrity_error":
            from services.sync_engine import IntegrityError
            raise IntegrityError(
                f"conflicting OMS event {event_id} — human review "
                "(D-081/D-027: never silently reprocessed)")
        if rec["verdict"] in ("new", "retry"):
            self.store.begin(SOURCE_SYSTEM, event_id)
            self.store.succeed(SOURCE_SYSTEM, event_id,
                               result_reference=json.dumps(
                                   ref, ensure_ascii=False,
                                   sort_keys=True))
        if self.provenance is not None:
            try:
                self.provenance.record(
                    source_type="SYSTEM_GENERATED",
                    actor="oms-engine",
                    source_reference=event_id,
                    notes=json.dumps(
                        {"state": ref.get("state"),
                         "from_state": ref.get("from_state")},
                        ensure_ascii=False, sort_keys=True))
            except Exception:
                pass  # provenance must never corrupt order state
        return rec["verdict"]

    def _refs(self) -> List[Dict]:
        refs: List[Dict] = []
        for line in self.store.succeeded_references(SOURCE_SYSTEM):
            try:
                ref = json.loads(line)
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(ref, dict):
                refs.append(ref)
        return refs

    # -- placement (D-081 idempotency) --------------------------------------

    def place_order(self, order) -> Dict:
        """Validate → persist PLACED. Idempotent by client_order_id:
        identical replay returns skipped_duplicate with the original
        order; a CONFLICTING payload under the same client_order_id
        raises IntegrityError (human review, D-027/D-081)."""
        norm = validate_order(order)
        eid = f"oms|order|{norm['order_key']}"
        rec = self.store.receive(SOURCE_SYSTEM, eid, OP_ORDER, norm)
        from services.sync_engine import IntegrityError
        if rec["verdict"] == "integrity_error":
            raise IntegrityError(
                f"conflicting order payload for client_order_id "
                f"{norm['client_order_id']} — human review (D-081)")
        if rec["verdict"] == "skipped_duplicate":
            original = self._order_ref(norm["order_key"]) or {}
            return {"placed": False, "verdict": "skipped_duplicate",
                    "order_key": norm["order_key"],
                    "order_id": original.get("order_id",
                                             norm["order_id"]),
                    "state": original.get("state", PLACED),
                    "original": original}
        if rec["verdict"] in ("new", "retry"):
            ref = dict(norm, event_id=eid, state=PLACED)
            self.store.begin(SOURCE_SYSTEM, eid)
            self.store.succeed(SOURCE_SYSTEM, eid,
                               result_reference=json.dumps(
                                   ref, ensure_ascii=False,
                                   sort_keys=True))
        if self.provenance is not None:
            try:
                self.provenance.record(
                    source_type="SYSTEM_GENERATED",
                    actor="oms-engine",
                    source_reference=eid,
                    notes=json.dumps({"state": PLACED},
                                     ensure_ascii=False))
            except Exception:
                pass
        return {"placed": True, "verdict": "new",
                "order_key": norm["order_key"],
                "order_id": norm["order_id"], "state": PLACED,
                "order": dict(norm, event_id=eid, state=PLACED)}

    def _order_ref(self, order_key: str) -> Optional[Dict]:
        """Latest durable order reference (placement or transition)."""
        best = None
        prefix = f"oms|order|{order_key}"
        tprefix = f"oms|transition|{order_key}"
        for ref in self._refs():
            eid = str(ref.get("event_id", ""))
            if eid.startswith(prefix):
                rank = 0  # placement is the floor
            elif eid.startswith(tprefix):
                rank = 1
            else:
                continue
            if best is None or rank >= best[0]:
                best = (rank, ref)
        return best[1] if best else None

    def state(self, order_key: str) -> Optional[str]:
        ref = self._order_ref(order_key)
        return None if ref is None else ref.get("state")

    # -- guarded transitions (D-081/D-082) -----------------------------------

    def transition(self, order_key: str, to_state: str, *,
                   actor: str = "oms-ops",
                   fulfillment_receipt: Optional[Dict] = None,
                   reason: Optional[str] = None) -> Dict:
        """One guarded transition. Guards run BEFORE the event is
        written: the state machine (D-081), inventory reservation on
        VALIDATED entry (D-082), receipt requirement on COMPLETED,
        reservation release on CANCELLED (D-082/D-084). The D-027
        event is written only after all guards pass."""
        current = self.state(order_key)
        if current is None:
            raise OmsContractError(
                f"unknown order {order_key} (D-081)")
        if current == to_state:
            return {"transitioned": False, "reason": "same_state",
                    "order_key": order_key, "state": current}
        validate_transition(current, to_state)

        reservations = (self.ledger.for_order(order_key)
                        if self.ledger else [])

        # guard: inventory reservation on VALIDATED entry (D-082)
        if to_state == VALIDATED and current == PLACED:
            ref = self._order_ref(order_key) or {}
            in_call: List[Dict] = []  # lines reserved in THIS call
            for item in ref.get("line_items", []):
                res = self.inventory.reserve(
                    item["stock_key"], item["quantity"],
                    {"order_key": order_key})
                if not res.get("reserved"):
                    # deterministic outcome — roll back the lines
                    # reserved earlier in THIS call so no partial
                    # reservation survives (D-082 atomicity)
                    for done in in_call:
                        self.inventory.release(
                            done["stock_key"], done["quantity"],
                            {"order_key": order_key})
                    return {"transitioned": False,
                            "reason": INSUFFICIENT_STOCK,
                            "order_key": order_key,
                            "state": current,
                            "stock_key": item["stock_key"],
                            "wanted": item["quantity"]}
                in_call.append(item)
                if self.ledger is not None:
                    self.ledger.record(order_key, [{
                        "stock_key": item["stock_key"],
                        "quantity": item["quantity"],
                    }])

        # guard: fulfillment receipt required for COMPLETED (D-084)
        if to_state == COMPLETED and not fulfillment_receipt:
            return {"transitioned": False,
                    "reason": "fulfillment_receipt_missing",
                    "order_key": order_key, "state": current}

        # guards passed — persist the transition (D-084 audit)
        eid = f"oms|transition|{order_key}|{to_state}"
        ref = {"event_id": eid, "order_key": order_key,
               "from_state": current, "state": to_state,
               "actor": actor}
        if reason:
            ref["reason"] = reason
        if fulfillment_receipt:
            ref["fulfillment_receipt"] = fulfillment_receipt
        self._record(eid, ref)

        # side effects AFTER the durable write (D-082/D-084)
        if to_state == CANCELLED:
            self._release_all(order_key)
        if to_state == REFUNDED:
            self._release_all(order_key)

        # D-083: notification fan-out, fully isolated (D-077 rule)
        notified = self._notify(order_key, current, to_state)
        return {"transitioned": True, "order_key": order_key,
                "from_state": current, "state": to_state,
                "notified": notified}

    def _release_all(self, order_key: str) -> None:
        if self.ledger is None:
            return
        entries = self.ledger.for_order(order_key)
        changed = False
        for e in entries:
            if e.get("state") == RESERVED:
                self.inventory.release(e["stock_key"], e["quantity"],
                                       {"order_key": order_key})
                e["state"] = RELEASED
                changed = True
        if changed:
            self.ledger.mark_released(order_key)

    def _notify(self, order_key: str, from_state: str,
                to_state: str) -> Optional[Dict]:
        """D-083: dispatch an order-status notification through the
        Phase 11 engine. NEVER raises: a notification failure is the
        notification's outcome, not the order's (D-077 isolation)."""
        if self.fanout_engine is None or self.fanout_engine is True:
            return None
        try:
            # no destinations configured → notification is a no-op
            # (the OMS never invents destinations; D-083)
            if not self.notification_targets:
                return None
            payload = {
                "job_id": f"oms-notify-{order_key}-{to_state}".lower(),
                "campaign_id": "order-notifications",
                "content_id": f"order-{order_key}",
                "text": f"سفارش {order_key} به وضعیت {to_state} رفت.",
                "hashtags": [],
                "media": {"kind": "none"},
                "scheduled_slot": "1970-01-01T00:00:00+00:00",
                "targets": list(self.notification_targets),
            }
            routed = self.fanout_engine.route(payload)
            if not routed.get("routed"):
                return {"fanout": "not_routed",
                        "reason": routed.get("reason")}
            res = self.fanout_engine.dispatch(
                {"job_id": routed["job_id"], "ref": routed["ref"]})
            return {"fanout": "dispatched",
                    "aggregate": res.get("aggregate")}
        except Exception as exc:  # isolation, never blocks the order
            return {"fanout": "failed", "error": str(exc)[:200]}

    # -- fulfillment receipt (D-084) ------------------------------------------

    def record_fulfillment_receipt(self, order_key: str,
                                   receipt: Dict, *,
                                   actor: str = "fulfillment-ops") -> Dict:
        eid = f"oms|receipt|{order_key}"
        ref = {"event_id": eid, "order_key": order_key,
               "receipt": receipt, "actor": actor}
        self._record(eid, ref)
        return {"recorded": True, "order_key": order_key}

    def has_receipt(self, order_key: str) -> bool:
        prefix = f"oms|receipt|{order_key}"
        return any(str(r.get("event_id", "")).startswith(prefix)
                   for r in self._refs())

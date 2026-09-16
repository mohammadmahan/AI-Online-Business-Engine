"""Executable local sync architecture — Phase 3 Batch 4.

Implements the APPROVED contracts as running local code:

- D-027 EventStore       — event-level idempotency (skipped_duplicate /
                           integrity-error classification, terminal states
                           never re-entered)
- D-026 ProvenanceEngine — append-only provenance; entries supersede
                           rather than overwrite; only review_state advances
- D-046 MappingRegistry  — bidirectional 1:1, second-guard before create,
                           write-once Woo IDs, stale/orphan surfaced
- SyncEngine             — canonical → mapping → projection → mock Woo,
                           with read-back verification, deterministic
                           divergence detection, hide-and-flag compensation,
                           and the D-050 Green/Yellow/Red authority gate

AI never executes any of this: every operation runs inside an explicitly
invoked deterministic flow; Red-tier operations additionally require the
explicit `authorized=True` flag (the human-promotion boundary). No
business rule is invented here — every rule cites its decision.

Persistence is JSON under local/volumes/ (gitignored); production
storage remains the D-055 PostgreSQL schema — this local store exists so
the flows are executable before Docker is available.
"""

import hashlib
import itertools
import json
import os
import threading
from datetime import date, datetime, timezone

try:                       # package mode
    from . import media_store
except ImportError:        # flat mode (tests/scripts)
    import media_store

try:
    from ..canonical import identifiers as ident
    from ..canonical import prices as pricing
    from ..canonical import vocab
except ImportError:
    import sys
    _CANON = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "canonical")
    if _CANON not in sys.path:
        sys.path.insert(0, _CANON)
    import identifiers as ident
    import prices as pricing
    import vocab


# --- errors -------------------------------------------------------------

class SyncError(Exception):
    """Deterministic sync failure with an error class (D-044)."""


class IntegrityError(SyncError):
    """D-027 conflicting duplicate / D-046 mapping conflict.

    Never auto-resolved — surfaces for human review."""


class AuthorityError(SyncError):
    """Red-tier operation attempted without explicit authorization
    (D-050). AI and un-promoted tooling must never pass this gate."""


# --- D-050 authority matrix (operational check) --------------------------

TIERS = {
    "read": "GREEN",
    "validate": "GREEN",
    "registry_lookup": "GREEN",
    "dry_run": "GREEN",
    "divergence_detection": "GREEN",
    "create_hidden_product": "YELLOW",
    "update_hidden_product": "YELLOW",
    "taxonomy_seed": "YELLOW",
    "media_hidden": "YELLOW",
    "publish": "RED",
    "withdraw": "RED",
    "price_write_published": "RED",
    "archive_execution": "RED",
    "conflict_resolution": "RED",
}


def authority_of(op: str) -> str:
    if op not in TIERS:
        raise ValueError(f"unknown operation: {op}")
    return TIERS[op]


def require_authority(op: str, authorized: bool):
    """Red gate: only an explicitly human-authorized flow may pass."""
    if authority_of(op) == "RED" and not authorized:
        raise AuthorityError(
            f"{op} is RED-tier (D-050): requires explicit human "
            "authorization; AI and un-promoted tooling may not execute it")


# --- small shared helpers ------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _payload_hash(payload) -> str:
    return hashlib.sha256(json.dumps(
        payload, sort_keys=True, ensure_ascii=False,
        default=str).encode("utf-8")).hexdigest()


class _JsonStore:
    """Tiny concurrent JSON persistence (local development only)."""

    def __init__(self, path: str, default):
        self.path = path
        self._lock = threading.Lock()
        self.data = default
        if path and os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                self.data = json.load(f)

    def save(self):
        if not self.path:
            return
        with self._lock:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self.path)


# =========================================================================
# D-027 — Event store
# =========================================================================

class EventStore:
    """Event-level idempotency store (D-027). One event = one operation.

    (source_system, event_id) is the composite key. Repeats classify
    deterministically: identical payload of a terminal event →
    skipped_duplicate; same key with a DIFFERENT payload →
    IntegrityError (human review, never reprocessed); non-terminal
    existing event → retry under the same ID.
    """

    def __init__(self, path: str = None):
        self._store = _JsonStore(path, {})
        self.records = self._store.data   # key → record dict
        # durable monotonic insertion counter (see succeeded_references
        # — receive_seq is the ordering key; received_at is not trusted
        # for ordering on VMs whose clock can step backward)
        self._seq = itertools.count(
            1 + max((int(r.get("receive_seq", 0))
                     for r in self.records.values()), default=0))

    @staticmethod
    def key(source_system: str, event_id: str) -> str:
        return f"{source_system}::{event_id}"

    def get_record(self, source_system: str, event_id: str):
        """Full event record (status, payload_hash, retry_count,
        last_error_class, result_reference) or None — D-027 interface
        parity with the PostgreSQL store (M4 audit addition)."""
        rec = self.records.get(self.key(source_system, event_id))
        return dict(rec) if rec else None

    def succeeded_references(self, source_system: str) -> list:
        """result_reference of every succeeded event, in deterministic
        insertion order (D-027 interface parity with the PostgreSQL
        store; consumed by canonical.notion_ingest.rebuild_state).

        Orders by the monotonic receive_seq assigned at receive() time
        (M4 Phase-7 audit parity: the PG store orders by ingest_seq —
        wall-clock timestamps are not safe ordering keys on VMs whose
        clock can step backward)."""
        rows = [r for r in self.records.values()
                if r["processing_status"] == "succeeded"
                and r.get("result_reference")]
        rows.sort(key=lambda r: (r.get("receive_seq", 0),
                                 r.get("event_id", "")))
        return [r["result_reference"] for r in rows]

    def receive(self, source_system: str, event_id: str,
                operation_type: str, payload) -> dict:
        """Register/refresh an event. Returns the event record.

        Raises IntegrityError on a conflicting duplicate (same key,
        different payload, terminal status) — human review.
        """
        ph = _payload_hash(payload)
        k = self.key(source_system, event_id)
        existing = self.records.get(k)
        if existing:
            verdict = ident.classify_event_repeat(
                existing["processing_status"],
                existing["payload_hash"], ph)
            if verdict == "skipped_duplicate":
                return {"record": dict(existing), "verdict": verdict}
            if verdict == "integrity_error":
                raise IntegrityError(
                    f"D-027 conflicting duplicate: event {event_id} "
                    "already terminal with a different payload — human "
                    "review required (never silently reprocessed)")
            # verdict == "retry": non-terminal — refresh in place
            existing["processing_status"] = "received"
            existing["operation_type"] = operation_type
            existing["retry_count"] += 1
            existing["last_attempt_at"] = _now()
            self._store.save()
            return {"record": dict(existing), "verdict": verdict}

        rec = {
            "source_system": source_system,
            "event_id": event_id,
            "operation_type": operation_type,
            "received_at": _now(),
            # monotonic insertion sequence — the durable ordering key
            # (wall-clock received_at is audit metadata only; see
            # succeeded_references — M4 Phase-7 audit parity with the
            # PG store's ingest_seq)
            "receive_seq": next(self._seq),
            "processing_status": "received",
            "payload_hash": ph,
            "result_reference": None,
            "retry_count": 0,
            "last_error_class": None,
            "last_attempt_at": None,
        }
        self.records[k] = rec
        self._store.save()
        return {"record": dict(rec), "verdict": "new"}

    def begin(self, source_system: str, event_id: str):
        self._transition(source_system, event_id, "processing")

    def succeed(self, source_system: str, event_id: str,
                result_reference: str):
        rec = self._transition(source_system, event_id, "succeeded")
        rec["result_reference"] = result_reference
        self._store.save()

    def fail(self, source_system: str, event_id: str, error_class: str):
        rec = self._transition(source_system, event_id, "failed")
        rec["last_error_class"] = error_class
        self._store.save()

    def mark_skipped_duplicate(self, source_system: str, event_id: str):
        self._transition(source_system, event_id, "skipped_duplicate")

    def _transition(self, source_system, event_id, new_status) -> dict:
        k = self.key(source_system, event_id)
        rec = self.records.get(k)
        if rec is None:
            raise KeyError(f"unknown event: {event_id}")
        cur = rec["processing_status"]
        if cur in ident.TERMINAL_EVENT_STATUSES:
            raise IntegrityError(
                f"terminal event {event_id} ({cur}) cannot re-enter "
                f"'{new_status}' (D-027)")
        rec["processing_status"] = new_status
        rec["last_attempt_at"] = _now()
        self._store.save()
        return rec


# =========================================================================
# D-026 — Provenance engine (append-only)
# =========================================================================

class ProvenanceEngine:
    """Append-only provenance (D-026).

    Records are immutable except review_state, which may only advance
    PENDING → HUMAN_REVIEWED → HUMAN_VERIFIED. Value linkages supersede
    rather than overwrite: a new linkage for the same (table, row,
    field) keeps the full history.
    """

    ORDER = {"PENDING": 0, "HUMAN_REVIEWED": 1, "HUMAN_VERIFIED": 2}

    def __init__(self, path: str = None):
        self._store = _JsonStore(path, {"records": [], "linkages": {},
                                        "linkage_history": {}})
        self.records = self._store.data["records"]
        self.linkages = self._store.data["linkages"]
        self.linkage_history = self._store.data["linkage_history"]

    def record(self, source_type: str, actor: str,
               review_state: str = "PENDING",
               source_reference: str = None,
               original_value: str = None, notes: str = None) -> int:
        rec = {
            "provenance_id": len(self.records) + 1,
            "source_type": source_type,
            "actor": actor,
            "recorded_at": _now(),
            "review_state": review_state,
            "source_reference": source_reference,
            "original_value": original_value,
            "notes": notes,
        }
        errors = ident.validate_provenance(rec)
        if errors:
            raise ValueError(f"invalid provenance (D-026): {errors}")
        self.records.append(rec)
        self._store.save()
        return rec["provenance_id"]

    def advance_review(self, provenance_id: int, new_state: str) -> dict:
        """The ONLY mutation allowed on a provenance record (D-026)."""
        rec = self.records[provenance_id - 1]
        if new_state not in ident.REVIEW_STATES:
            raise ValueError(f"unknown review state: {new_state}")
        if self.ORDER[new_state] <= self.ORDER[rec["review_state"]]:
            raise ValueError(
                f"review state may only advance "
                f"({rec['review_state']} → {new_state} rejected)")
        rec["review_state"] = new_state
        self._store.save()
        return dict(rec)

    def link_value(self, table_name: str, row_pk: str, field_name: str,
                   provenance_id: int) -> dict:
        """Bind a provenance record to a field of a row. Supersedes any
        previous linkage (history preserved, nothing deleted)."""
        if not 1 <= provenance_id <= len(self.records):
            raise KeyError(f"unknown provenance_id {provenance_id}")
        key = f"{table_name}::{row_pk}::{field_name}"
        previous = self.linkages.get(key)
        if previous is not None:
            self.linkage_history.setdefault(key, []).append(previous)
        linkage = {"provenance_id": provenance_id, "superseded_at": _now()}
        self.linkages[key] = linkage
        self._store.save()
        return {"linkage": linkage, "superseded": previous}

    def history_of(self, table_name: str, row_pk: str,
                   field_name: str) -> list:
        """Chronological linkage history for a field, oldest first,
        current linkage last (nothing deleted — D-026)."""
        key = f"{table_name}::{row_pk}::{field_name}"
        return (self.linkage_history.get(key, [])
                + ([self.linkages[key]] if key in self.linkages else []))


def _as_date(v):
    """Normalize a possibly-JSON-round-tripped date back to date."""
    if v is None or isinstance(v, datetime):
        return v if isinstance(v, datetime) else None
    return date.fromisoformat(str(v)[:10])


# =========================================================================
# D-046 — Mapping registry
# =========================================================================

class MappingConflict(IntegrityError):
    pass


class StaleMapping(MappingConflict):
    pass


class MappingRegistry:
    """D-046 conceptual registry, executable.

    - canonical side always authoritative; Woo IDs are technical facts
    - one ACTIVE entry per canonical key AND per Woo ID per type
      (bidirectional 1:1; violation = MappingConflict)
    - second guard (classify_registry_hit) before every create; a Woo
      resource found WITHOUT an active entry is a duplicate-resource
      conflict → human review, never silent adoption
    - Woo IDs are write-once; replacement only via the explicit
      relink_after_review flow (stale + human review)
    - entries are never deleted (stale/orphaned only)
    """

    def __init__(self, path: str = None):
        self._store = _JsonStore(path, {"entries": {}, "history": [],
                                        "next_woo": 1})
        self.entries = self._store.data["entries"]   # "type\x1fkey" → entry
        self._migrate_keys()

    def _migrate_keys(self):
        """One-time migration: tuple-key entries (an in-memory pattern
        that broke json persistence) → the "type\x1fkey" string form."""
        for k in [k for k in self.entries if isinstance(k, list)]:
            entry = self.entries.pop(k)
            self.entries[self._k(entry["entry_type"],
                                 entry["canonical_key"])] = entry

    @staticmethod
    def _k(entry_type: str, canonical_key: str) -> str:
        """JSON-serializable dict key ("type\x1fcanonical_key") — same
        semantics as the previous tuple keys; the tuple form broke
        persistence (TypeError on json.dump)."""
        return f"{entry_type}\x1f{canonical_key}"

    def _archive(self, entry):
        """Superseded entries are kept (never deleted, D-046 §2.7)."""
        if entry is not None:
            self._store.data.setdefault("history", []).append(
                dict(entry, archived_at=_now()))

    # -- lookups (GREEN) ------------------------------------------------

    def lookup(self, entry_type: str, canonical_key: str):
        e = self.entries.get(self._k(entry_type, canonical_key))
        return dict(e) if e and e["status"] == "active" else None

    def lookup_any(self, entry_type: str, canonical_key: str):
        e = self.entries.get(self._k(entry_type, canonical_key))
        return dict(e) if e else None

    def lookup_by_woo_id(self, entry_type: str, woo_id: str):
        for e in self.entries.values():
            if e["entry_type"] == entry_type and e["status"] == "active" \
                    and str(e["woo_id"]) == str(woo_id):
                return dict(e)
        return None

    # -- creation with second guard (D-046 §2.6) -------------------------

    def register(self, entry_type: str, canonical_key: str, woo_id: str,
                 woo_slug: str = None) -> dict:
        """Create-if-missing with the deterministic second guard.

        Never derived by fuzzy matching; conflicts surface as
        exceptions for human review.
        """
        active = self.lookup(entry_type, canonical_key)
        by_woo = self.lookup_by_woo_id(entry_type, woo_id)
        verdict = ident.classify_registry_hit(
            active is not None, by_woo is not None)
        if verdict == "consistent":
            if by_woo["canonical_key"] != canonical_key:
                raise MappingConflict(
                    f"registry inconsistency: {woo_id} maps to "
                    f"{by_woo['canonical_key']!r}, expected "
                    f"{canonical_key!r}")
            return dict(active)  # idempotent no-op path
        if verdict == "stale":
            raise StaleMapping(
                f"stale registry entry for {canonical_key!r} — re-link "
                "requires human review (D-046 §2.7)")
        if verdict == "duplicate_resource_conflict":
            raise MappingConflict(
                f"duplicate resource: Woo {entry_type} {woo_id} already "
                f"maps to {by_woo['canonical_key']!r} — human review, "
                "never silent adoption (D-046 §2.6)")
        # No ACTIVE entry. A superseded (stale/orphaned) entry for the
        # same canonical key must still be honoured: the SAME Woo ID
        # re-activates only via the deterministic failure-recovery path
        # (marker lookup, within a human-promoted flow); a DIFFERENT
        # Woo ID requires the reviewed relink flow (D-046 §2.5/§2.7).
        superseded = self.lookup_any(entry_type, canonical_key)
        if superseded is not None and \
                str(superseded["woo_id"]) != str(woo_id):
            raise StaleMapping(
                f"superseded entry for {canonical_key!r} exists with "
                f"Woo ID {superseded['woo_id']} — replacement requires "
                "relink_after_review (human review; D-046 §2.5)")
        self._archive(superseded)   # history preserved before replace
        entry = {
            "entry_type": entry_type,
            "canonical_key": canonical_key,
            "woo_id": str(woo_id),      # write-once (D-046 §2.3)
            "woo_slug": woo_slug,
            "status": "active",
            "created_at": _now(),
            "last_verified_at": _now(),
        }
        self.entries[self._k(entry_type, canonical_key)] = entry
        self._store.save()
        return dict(entry)

    def relink_after_review(self, entry_type: str, canonical_key: str,
                            new_woo_id: str, reviewer: str) -> dict:
        """Stale recovery: human-reviewed replacement (D-046 §2.5/§2.7).

        The old entry is superseded (kept, marked stale); a new active
        entry takes the canonical key. Never called automatically.
        """
        old = self.lookup_any(entry_type, canonical_key)
        if old is None:
            raise KeyError(f"no entry to relink: {canonical_key}")
        if self.lookup_by_woo_id(entry_type, new_woo_id):
            raise MappingConflict("new Woo ID already mapped (conflict)")
        old["status"] = "stale"
        self._archive(old)
        entry = {
            "entry_type": entry_type,
            "canonical_key": canonical_key,
            "woo_id": str(new_woo_id),
            "woo_slug": None,
            "status": "active",
            "created_at": _now(),
            "last_verified_at": _now(),
            "relinked_by": reviewer,
        }
        self.entries[self._k(entry_type, canonical_key)] = entry
        self._store.save()
        return dict(entry)

    # -- state maintenance (never delete) ---------------------------------

    @staticmethod
    def _set_status(entries: dict, entry_type: str, canonical_key: str,
                    status: str) -> dict:
        e = entries.get(MappingRegistry._k(entry_type, canonical_key))
        if e is None:
            raise KeyError(f"no entry: {canonical_key}")
        e["status"] = status      # mutate the stored entry, not a copy
        return e

    def mark_stale(self, entry_type: str, canonical_key: str) -> dict:
        e = self._set_status(self.entries, entry_type, canonical_key,
                             "stale")
        self._store.save()
        return dict(e)

    def mark_orphaned(self, entry_type: str, canonical_key: str) -> dict:
        e = self._set_status(self.entries, entry_type, canonical_key,
                             "orphaned")
        self._store.save()
        return dict(e)

    def touch_verified(self, entry_type: str, canonical_key: str):
        e = self.lookup_any(entry_type, canonical_key)
        if e:
            e["last_verified_at"] = _now()
            self._store.save()


# =========================================================================
# Sync engine — canonical → mapping → projection → mock Woo
# =========================================================================

PM_SOURCE = "canonical-sync"
EVENT_SOURCE = "sync-engine"


class SyncEngine:
    """Executable D-042/D-047 sync: canonical PM → Woo projection.

    Deterministic tooling only. Woo-side fields owned by the canonical
    layer are computed here (never adopted from Woo); divergence is
    reported (Green) and repaired only by an explicit human-authorized
    re-projection (Red where price-affecting).
    """

    def __init__(self, mock, registry: MappingRegistry,
                 events: EventStore, provenance: ProvenanceEngine,
                 media=None, actor: str = "approved-tooling"):
        self.mock = mock
        self.registry = registry
        self.events = events
        self.provenance = provenance
        self.media = media or media_store.media_store()
        self.actor = actor
        self.review_queue = []   # deterministic divergence/review items

    # ------------------------------------------------------------------
    # Canonical → Woo projections (shared by write AND divergence check)
    # ------------------------------------------------------------------

    @staticmethod
    def woo_status_for(product: dict) -> str:
        """D-039 projection table: published+active → publish; every
        other canonical state → Woo draft (hidden). No new states."""
        if product["status"] == "active" \
                and product["publication_status"] == "published":
            return "publish"
        return "draft"

    @staticmethod
    def derive_sku(product_id: str, color_code, size_code) -> str:
        """D-014 rule 6: Product ID + active-axis codes, Color then
        Size (D-018). Deterministic derivation from approved codes —
        never invented values."""
        parts = [product_id]
        for c in (color_code, size_code):
            if c:
                parts.append(c)
        sku = "-".join(parts)
        if not ident.is_valid_sku(sku):     # D-014 rule 7 / D-032 codes
            raise SyncError(f"derived SKU fails D-014: {sku}")
        return sku

    def _expected_product_payload(self, product: dict) -> dict:
        """The exact Woo payload the canonical layer owns (D-047 §3)."""
        meta = {k: v for k, v in product.get("attributes", {}).items()
                if v}                                    # D-051 (meta only)
        payload = {
            "name": product["name"],
            "status": self.woo_status_for(product),
            "catalog_visibility": "visible"
            if product["publication_status"] == "published" else "hidden",
            # canonical identity marker first (D-044/D-047 failure
            # recovery: deterministic reconciliation key, never a name
            # search), then D-051 attribute meta
            "meta_data": ([{"key": "_pm_pid",
                            "value": product["product_id"]}]
                          + [{"key": f"_pm_{k}", "value": v}
                             for k, v in meta.items()]),
        }
        if product.get("name_en"):
            payload["meta_data"].append(
                {"key": "_pm_name_en", "value": product["name_en"]})
        if product.get("description"):
            payload["description"] = product["description"]
        if product.get("short_description"):
            payload["short_description"] = product["short_description"]
        # SEO slug NOT projected while the language gate is open
        # (D-016.M open; D-047 §3).
        return payload

    def _expected_variation_payload(self, product: dict, v: dict,
                                    today) -> dict:
        """D-048 Option A: materialize the canonical D-024 resolution
        into Woo's display fields; canonical inputs are never mutated."""
        proj = pricing.project_to_woo(pricing.PriceInputs(
            list_price=product.get("list_price"),
            variant_override=v.get("price_override"),
            product_sale=product.get("product_sale"),
            product_sale_until=_as_date(product.get("product_sale_until")),
            variant_sale=v.get("variant_sale"),
            variant_sale_until=_as_date(v.get("variant_sale_until")),
        ), today)
        if not proj["resolved"]:
            raise SyncError(
                f"unresolved effective price for {v.get('sku') or v}: "
                f"{proj.get('unresolved_reason')} — nothing written "
                "(D-024 rule 5)")
        attributes = {}
        if v.get("color_code"):
            attributes["pa_color"] = v["color_code"].lower()
        if v.get("size_code"):
            attributes[f"pa_size-{v['size_family']}"] = \
                v["size_code"].lower()
        payload = {
            "regular_price": proj["regular_price"],
            "sale_price": proj["sale_price"],
            "attributes": attributes,
            "meta_data": [{"key": "_pm_status", "value": v["status"]}],
        }
        return payload

    # ------------------------------------------------------------------
    # Taxonomy seed (one-time, from approved registries) — YELLOW
    # ------------------------------------------------------------------

    def seed_taxonomy(self) -> dict:
        """Create-if-absent Woo categories/attributes/terms from the
        OWNER-APPROVED registries (D-031/D-032/D-036/D-037), registering
        every mapping (D-046 §2.4). Blocked-conflict terms (D-030 gate)
        are excluded and reported. Hidden-record data → YELLOW.
        Idempotent: counts reflect newly created resources only."""
        require_authority("taxonomy_seed", True)   # always authorized flow
        summary = {"categories": 0, "color_terms": 0, "size_terms": 0,
                   "blocked": []}
        primaries = {}
        for primary, leaf in vocab.CATEGORY_PAIRS:
            if primary not in primaries:
                if self.registry.lookup(
                        "category", f"primary:{primary}") is None:
                    cat = self.mock.create_category(primary)
                    primaries[primary] = cat["id"]
                    self._register_taxonomy(
                        "category", f"primary:{primary}", cat["id"])
                    summary["categories"] += 1
                else:
                    primaries[primary] = int(self.registry.lookup(
                        "category", f"primary:{primary}")["woo_id"])
            parent = primaries[primary]
            key = f"{primary}|{leaf}"
            if self.registry.lookup("category", key) is None:
                leaf_cat = self.mock.create_category(leaf, parent_id=parent)
                self._register_taxonomy("category", key, leaf_cat["id"])
                summary["categories"] += 1

        if self.registry.lookup("color_term", "attr:pa_color") is None:
            attr = self.mock.create_attribute("pa_color", "رنگ")
            self._register_taxonomy(
                "color_term", "attr:pa_color", attr["id"])
        for term, code in vocab.COLOR_TERMS:
            key = f"pa_color|{code}"
            if self.registry.lookup("color_term", key) is None:
                t = self.mock.create_term("pa_color", term,
                                          slug=code.lower())
                self._register_taxonomy("color_term", key, t["id"])
                summary["color_terms"] += 1

        for fam_key in ("alpha", "numeric", "pants_waist"):
            attr_key = f"attr:pa_size-{fam_key}"
            if self.registry.lookup("size_term", attr_key) is None:
                fam_attr = self.mock.create_attribute(
                    f"pa_size-{fam_key}", vocab.FAMILY_LABELS[fam_key])
                self._register_taxonomy("size_term", attr_key,
                                        fam_attr["id"])
            for term, code in vocab.SIZE_TERMS[fam_key]:
                if not vocab.is_seedable(code):
                    # D-030 gate: strictly unsafe AND not covered by an
                    # explicit owner sanction (D-057 mechanism).
                    summary["blocked"].append(f"{fam_key}/{term}→{code}")
                    continue
                key = f"pa_size-{fam_key}|{code}"
                if self.registry.lookup("size_term", key) is None:
                    t = self.mock.create_term(
                        f"pa_size-{fam_key}", term, slug=code.lower())
                    self._register_taxonomy("size_term", key, t["id"])
                    summary["size_terms"] += 1
        return summary

    def _register_taxonomy(self, entry_type, canonical_key, woo_id):
        # Second guard runs inside registry.register (D-046 §2.6).
        try:
            self.registry.register(entry_type, canonical_key, str(woo_id))
        except MappingConflict:
            # Deterministic Woo lookup: create-if-absent by exact key
            # means re-seeding finds the SAME resource; a different
            # resource under a new Woo ID is a genuine conflict.
            raise
        self.provenance.record(
            "SYSTEM_GENERATED", self.actor,
            source_reference=f"registry:{entry_type}:{canonical_key}",
            notes="taxonomy seed from approved registries (D-031/D-032)")

    # ------------------------------------------------------------------
    # Product sync (create/update projection) — YELLOW; publish = RED
    # ------------------------------------------------------------------

    def sync_product(self, product: dict, variants: list, today,
                     authorized: bool = False,
                     operation: str = "woo_projection") -> dict:
        """Project one canonical product (+ variants) into mock Woo.

        - draft → no Woo record (D-039): deterministic no-op (GREEN)
        - hidden states → create/update a draft Woo product (YELLOW)
        - publish requires authorized=True (RED)
        - every write: D-027 event, read-back verification, registry
          entry, D-026 provenance
        - `operation` separates the event namespaces: the normal sync
          ("woo_projection") is payload-idempotent (an identical
          re-projection is skipped), while an explicit reconciliation
          ("woo_reprojection", from reproject()) is its own event — a
          Woo-side drift must be re-writable even though the canonical
          payload is unchanged (D-047 §3; still payload-idempotent per
          namespace).
        """
        pid = product["product_id"]
        target_status = self.woo_status_for(product)
        if product["status"] == "draft":
            return {"product_id": pid, "action": "skipped_draft",
                    "note": "draft has no Woo record (D-039)"}
        if target_status == "publish":
            require_authority("publish", authorized)     # RED gate

        payload_hash = _payload_hash(
            [self._expected_product_payload(product)] +
            [self._expected_variation_payload(product, v, today)
             for v in variants])
        prefix = "woo-sync" if operation == "woo_projection" \
            else "woo-reproject"
        event_id = f"{prefix}:{pid}:{payload_hash[:12]}"
        ev = self.events.receive(EVENT_SOURCE, event_id,
                                 "woo_projection", payload_hash)
        if ev["verdict"] == "skipped_duplicate":
            return {"product_id": pid, "action": "skipped_duplicate",
                    "event": event_id}
        rec = ev["record"]
        try:
            self.events.begin(EVENT_SOURCE, event_id)
            result = self._do_sync(product, variants, today, pid)
            self.events.succeed(
                EVENT_SOURCE, event_id, result["woo_product_id"])
            result["event"] = event_id
            return result
        except Exception as e:
            self.events.fail(
                EVENT_SOURCE, event_id, getattr(e, "code",
                                                type(e).__name__))
            raise

    def _do_sync(self, product, variants, today, pid) -> dict:
        mapping = self.registry.lookup("product", pid)
        payload = self._expected_product_payload(product)
        if mapping is None:
            # Deterministic failure-recovery second guard (D-044):
            # an ambiguous timeout may have committed the write without
            # the registry seeing it. Reconcile by the canonical marker
            # meta (_pm_pid) — never by name search, never fuzzy. An
            # exact single hit whose committed payload matches the
            # expected projection is adopted WITH provenance; anything
            # ambiguous is a conflict for human review. Variation-level
            # recovery falls back to the reviewed path (the mock
            # rejects a duplicate SKU deterministically).
            prior = self.mock.find_products_by_meta("_pm_pid", pid)
            if len(prior) > 1:
                raise MappingConflict(
                    f"recovery conflict for {pid}: Woo holds "
                    f"{len(prior)} candidate records — human review "
                    "(D-044)")
            if prior and prior[0]["payload"].get("name") != payload["name"]:
                raise MappingConflict(
                    f"recovery conflict for {pid}: committed Woo record "
                    "differs from the canonical projection — human "
                    "review (D-044)")
            if prior:
                woo_id = str(prior[0]["id"])
                self._verify_read_back(
                    lambda: self.mock.read_product(int(woo_id)),
                    payload, f"product {pid} (recovery)")
                prov = self.provenance.record(
                    "SYSTEM_GENERATED", self.actor,
                    source_reference=f"product:{pid}",
                    notes="registry re-linked after ambiguous-timeout "
                          "recovery via deterministic marker lookup "
                          "(D-044; auditable, never silent)")
                self.provenance.link_value(
                    "woo_product", pid, "projection", prov)
                mapping = self.registry.register("product", pid, woo_id)
                action = "recovered_after_timeout"
            else:
                # Second guard clean: safe create.
                res = self.mock.create_product(dict(
                    payload, sku=None, type="variable" if variants else
                    "simple"))
                woo_id = str(res["id"])
                self._verify_read_back(
                    lambda: self.mock.read_product(int(woo_id)),
                    payload, f"product {pid}")
                prov = self.provenance.record(
                    "SYSTEM_GENERATED", self.actor,
                    source_reference=f"product:{pid}",
                    notes="hidden Woo projection created by approved "
                          "tooling (D-047/D-050 YELLOW)")
                self.provenance.link_value(
                    "woo_product", pid, "projection", prov)
                mapping = self.registry.register("product", pid, woo_id)
                action = "created_hidden"
        else:
            woo_id = mapping["woo_id"]
            self.mock.update_product(int(woo_id), payload)
            self._verify_read_back(
                lambda: self.mock.read_product(int(woo_id)),
                payload, f"product {pid}")
            self.registry.touch_verified("product", pid)
            action = "updated_hidden"

        variation_results = []
        for v in variants:
            variation_results.append(
                self._sync_variation(product, v, today, woo_id))
        return {"product_id": pid, "woo_product_id": woo_id,
                "action": action, "variations": variation_results}

    def _sync_variation(self, product, v, today, product_woo_id) -> dict:
        vid = v.get("variant_id") or ident.new_variant_id()  # D-017: tooling
        if not ident.is_valid_variant_id(vid):
            raise SyncError(f"invalid variant id: {vid}")
        sku = v.get("sku") or self.derive_sku(
            product["product_id"], v.get("color_code"), v.get("size_code"))
        vp = self._expected_variation_payload(product, v, today)
        vmapping = self.registry.lookup("variation", vid)
        if vmapping is None:
            res = self.mock.create_variation(int(product_woo_id),
                                             dict(vp, sku=sku))
            woo_vid = str(res["id"])
            self._verify_read_back(
                lambda: self.mock.read_variation(int(woo_vid)),
                vp, f"variation {sku}")
            self.registry.register("variation", vid, woo_vid)
            # NOTE: the SKU→variation association is deliberately NOT a
            # registry entry — D-046 §2.2 stores SKU as data (uniqueness
            # enforced by the second guard + canonical store), never as
            # an identity/lookup key.
            action = "created_hidden"
        else:
            self.mock.update_variation(int(vmapping["woo_id"]),
                                       dict(vp, sku=sku))
            self._verify_read_back(
                lambda: self.mock.read_variation(
                    int(vmapping["woo_id"])),
                vp, f"variation {sku}")
            self.registry.touch_verified("variation", vid)
            action = "updated_hidden"
        self.provenance.record(
            "SYSTEM_GENERATED", self.actor,
            source_reference=f"variant:{vid} sku:{sku}",
            notes="variation projection (D-048 Option A price "
                  "materialization; D-014 SKU derivation)")
        return {"variant_id": vid, "sku": sku,
                "woo_variation_id": self.registry.lookup(
                    "variation", vid)["woo_id"],
                "action": action}

    @staticmethod
    def _verify_read_back(read_fn, expected: dict, subject: str):
        """Post-write verification (D-047 §4): read back and compare the
        canonical-owned fields; mismatch = deterministic failure, never
        silent acceptance."""
        got = read_fn()
        body = got.get("payload", got)
        for field, want in expected.items():
            have = body.get(field)
            if field == "meta_data":
                want_m = {m["key"]: m["value"] for m in want}
                have_m = {m["key"]: m["value"]
                          for m in (have or []) if "key" in m}
                for k, wv in want_m.items():
                    if have_m.get(k) != wv:
                        raise SyncError(
                            f"read-back mismatch on {subject}: meta "
                            f"{k} expected {wv!r} got {have_m.get(k)!r}")
                continue
            if have != want:
                raise SyncError(
                    f"read-back mismatch on {subject}: {field} expected "
                    f"{want!r} got {have!r}")

    # ------------------------------------------------------------------
    # Publication / withdrawal — RED
    # ------------------------------------------------------------------

    def publish_product(self, product: dict, variants: list, today,
                        authorized: bool):
        """RED: publication projection (D-050)."""
        require_authority("publish", authorized)
        return self.sync_product(product, variants, today,
                                 authorized=authorized)

    def withdraw_product(self, product: dict, variants: list, today,
                         authorized: bool):
        """RED: withdrawal (D-050). Canonical value stays authoritative;
        Woo record is hidden again."""
        require_authority("withdraw", authorized)
        return self.sync_product(product, variants, today,
                                 authorized=authorized)

    # ------------------------------------------------------------------
    # Divergence detection + controlled reconciliation
    # ------------------------------------------------------------------

    PRICE_FIELDS = {"regular_price", "sale_price"}

    def detect_divergence(self, product: dict, variants: list,
                          today) -> list:
        """GREEN: deterministic diff of canonical-owned Woo fields vs
        the recomputed projection (D-047 §3 divergence rule). Never
        adopts Woo values; never overwrites silently."""
        pid = product["product_id"]
        mapping = self.registry.lookup("product", pid)
        if mapping is None:
            return []
        woo = self.mock.read_product(int(mapping["woo_id"]))
        body = woo.get("payload", woo)
        expected = self._expected_product_payload(product)
        divergences = []

        def diff(field, want, have, price_affecting=False):
            if want != have:
                divergences.append({
                    "product_id": pid, "field": field,
                    "canonical": want, "woo": have,
                    "price_affecting": price_affecting,
                    "review": field in self.PRICE_FIELDS or price_affecting,
                })

        diff("name", expected["name"], body.get("name"))
        diff("status", expected["status"], body.get("status"))
        diff("catalog_visibility",
             expected["catalog_visibility"],
             body.get("catalog_visibility"))
        want_meta = {m["key"]: m["value"] for m in expected["meta_data"]}
        have_meta = {m["key"]: m["value"] for m in body.get("meta_data", [])
                     if "key" in m}
        for k in sorted(set(want_meta) | set(have_meta)):
            if want_meta.get(k) != have_meta.get(k):
                diff(f"meta:{k}", want_meta.get(k), have_meta.get(k))
        # variation-level price/attribute divergence
        for v in variants:
            vid = v.get("variant_id")
            vm = self.registry.lookup("variation", vid) if vid else None
            if vm is None:
                continue
            wv = self.mock.read_variation(int(vm["woo_id"]))
            vbody = wv.get("payload", wv)
            vexp = self._expected_variation_payload(product, v, today)
            for f in ("regular_price", "sale_price"):
                diff(f"{v.get('sku')}:{f}", vexp[f], vbody.get(f),
                     price_affecting=(f in self.PRICE_FIELDS))
            diff(f"{v.get('sku')}:attributes", vexp["attributes"],
                 vbody.get("attributes"))
        return divergences

    def reproject(self, product: dict, variants: list, today,
                  authorized: bool) -> dict:
        """Controlled reconciliation after divergence review (D-047 §3):
        re-writes the canonical projection. RED automatically when any
        diverging field is price-affecting or the record is published;
        otherwise YELLOW."""
        divergences = self.detect_divergence(product, variants, today)
        price_affecting = any(d["price_affecting"] for d in divergences)
        published = self.woo_status_for(product) == "publish"
        if price_affecting or published:
            require_authority("price_write_published", authorized)
        else:
            require_authority("update_hidden_product", True)
        # Its own D-027 event namespace: a Woo-side drift must be
        # re-writable even though the canonical payload is unchanged
        # (the normal-sync event for this payload already succeeded).
        result = self.sync_product(product, variants, today,
                                   authorized=authorized,
                                   operation="woo_reprojection")
        result["reprojected"] = True
        result["divergences_repaired"] = len(divergences)
        return result

    # ------------------------------------------------------------------
    # Media (D-049/D-056) — YELLOW on hidden, RED on published
    # ------------------------------------------------------------------

    def attach_media(self, product: dict, refs: list,
                     authorized: bool = False) -> dict:
        require_authority(
            "media_hidden" if self.woo_status_for(product) != "publish"
            else "price_write_published", authorized
            or self.woo_status_for(product) != "publish")
        pid = product["product_id"]
        mapping = self.registry.lookup("product", pid)
        if mapping is None:
            raise SyncError("no Woo record to attach media to")
        content = "|".join(refs).encode("utf-8")
        obj = self.media.put(content, "text/plain",
                             metadata={"product_id": pid})
        res = self.mock.attach_media(int(mapping["woo_id"]),
                                     [obj["object_key"]])
        self.provenance.record(
            "EXTERNAL_SYNC", self.actor,
            source_reference=f"media:{obj['object_key']}",
            notes="media reference attached (D-049: Woo holds "
                  "references, binaries in object storage)")
        return {"media_object": obj, "woo_attachment": res}


# =========================================================================
# Compensation (D-047 §4): hide + flag — no destructive delete
# =========================================================================

def compensate_hide_and_flag(engine: SyncEngine, product: dict,
                             error_class: str) -> dict:
    """On write failure after a possible partial create: hide the
    tracked record (draft) and ALWAYS flag for review. Destructive
    delete is never automatic (RULES §22 / D-047)."""
    pid = product["product_id"]
    mapping = engine.registry.lookup("product", pid)
    engine.review_queue.append({
        "kind": "compensation", "product_id": pid,
        "error_class": error_class, "at": _now(),
        "woo_record_tracked": mapping is not None})
    if mapping is None:
        # An ambiguous timeout may still have committed an untracked
        # record; the review queue entry above is the human-facing flag
        # and the deterministic recovery path resolves it on retry.
        return {"compensated": False,
                "flagged": True,
                "note": "no tracked Woo record; flagged for review — "
                        "recovery via deterministic marker lookup"}
    engine.mock.update_product(int(mapping["woo_id"]),
                               {"status": "draft"})
    return {"compensated": True, "woo_id": mapping["woo_id"],
            "status": "draft", "flagged": True}

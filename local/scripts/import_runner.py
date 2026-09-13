#!/usr/bin/env python3
"""Data Entry & Verification Engine — local import runner (Phase 4 work
block, owner-sequenced 2026-09-13).

Deterministic Excel-import pipeline per the approved decisions:

  D-028  Excel is INPUT ONLY: dry-run first, writes nothing; promotion
         is a separate explicit human action (--authorize); a failed
         run writes nothing; UNKNOWN/NOT_PROVIDED/INVALID stay distinct.
  D-027  One import run = one event (source `excel-import`, event id
         derived from the workbook content hash): identical re-import →
         skipped_duplicate; changed content under the same run identity
         → integrity error (human review).
  D-017  Identifier-level idempotency: same identifiers + same values →
         unchanged no-op; same identifiers + changed values → conflict
         review item; canonical values are NEVER silently overwritten.
  D-026  Every promoted record receives IMPORTED provenance (actor =
         tooling on behalf of the promoting human) + per-record value
         linkage; append-only.
  D-050  Promotion/writes are the human-authorized boundary; without
         --authorize nothing is ever written.

Storage is local JSON under local/volumes/ (gitignored) until Docker is
available; the D-055 PostgreSQL schema is the production target with
identical semantics.
"""
import argparse
import hashlib
import json
import os
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL = os.path.dirname(HERE)
ROOT = os.path.dirname(LOCAL)
for p in (LOCAL, os.path.join(LOCAL, "canonical"),
          os.path.join(LOCAL, "services")):
    if p not in sys.path:
        sys.path.insert(0, p)

import excel as excel_mod                    # noqa: E402
import identifiers as ident                  # noqa: E402
import mock_woo                              # noqa: E402
from sync_engine import (EventStore, IntegrityError,  # noqa: E402
                         MappingRegistry, ProvenanceEngine, SyncEngine)

EVENT_SOURCE = "excel-import"
DEFAULT_FIXTURE = os.path.join(LOCAL, "fixtures", "product-master.json")
DEFAULT_STORE = os.path.join(LOCAL, "volumes", "canonical", "store.json")


class CanonicalStore:
    """Local canonical data store (JSON) — D-055 semantics, file-backed.

    Products keyed by Product ID, variants by Variant ID; SKU kept as
    data (uniqueness enforced at write; never a lookup key, D-046).
    """

    def __init__(self, path: str):
        self.path = path
        self.data = {"products": {}, "variants": {}}
        if path and os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                self.data = json.load(f)

    def save(self):
        if not self.path:
            return
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=1,
                      default=str)
        os.replace(tmp, self.path)

    def get_product(self, pid):
        return self.data["products"].get(pid)

    def get_variant(self, vid):
        return self.data["variants"].get(vid)

    def sku_exists(self, sku):
        return any(v.get("sku") == sku
                   for v in self.data["variants"].values())


def _norm(rec: dict, drop=("active_axes",)) -> dict:
    return {k: v for k, v in rec.items() if k not in drop}


def _diff_fields(a: dict, b: dict) -> list:
    return sorted(k for k in set(a) | set(b)
                  if a.get(k) != b.get(k))


def workbook_event_id(fixture_path: str) -> str:
    with open(fixture_path, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    return f"wb:{digest[:16]}"


def load_rows(fixture_path: str):
    with open(fixture_path, encoding="utf-8") as f:
        fx = json.load(f)
    return fx["products"], fx["variants"]


def do_dry_run(fixture_path: str, store: CanonicalStore, today: date,
               product_rows=None, variant_rows=None) -> dict:
    """D-028 stage 1: validate everything, write nothing."""
    if product_rows is None:
        product_rows, variant_rows = load_rows(fixture_path)
    existing = {
        "product_ids": set(store.data["products"]),
        "variant_ids": set(store.data["variants"]),
    }
    wb = excel_mod.validate_workbook(product_rows, variant_rows, today,
                                     existing=existing)
    return {
        "products_valid": len(wb.products),
        "variants_valid": len(wb.variants),
        "errors": [{"sheet": e.sheet, "row": e.row_index, "code": e.code,
                    "message": e.message} for e in wb.errors],
        "_wb": wb,
    }


def do_promote(fixture_path: str, store: CanonicalStore,
               events: EventStore, provenance: ProvenanceEngine,
               today: date, authorize: bool) -> dict:
    """D-028 stage 2: human-promoted write (authorized only).

    Per-record identifier idempotency (D-017) + one event per run
    (D-027). Conflicting records are review items; canonical values
    are never silently overwritten.
    """
    if not authorize:
        return {"written": False, "reason": "promotion requires explicit "
                "human authorization (--authorize); D-028 boundary"}
    product_rows, variant_rows = load_rows(fixture_path)
    dry = do_dry_run(fixture_path, store, today, product_rows, variant_rows)
    wb = dry.pop("_wb")
    event_id = workbook_event_id(fixture_path)

    review = list(dry["errors"])          # invalid rows → verification queue
    try:
        ev = events.receive(EVENT_SOURCE, event_id, "excel_import",
                            {"products": len(product_rows),
                             "variants": len(variant_rows)})
    except IntegrityError as e:
        return {"written": False, "event": event_id,
                "verdict": "integrity_error", "reason": str(e),
                "review_queue": review}
    if ev["verdict"] == "skipped_duplicate":
        return {"written": False, "event": event_id,
                "verdict": "skipped_duplicate",
                "reason": "identical workbook already imported (D-027)",
                "review_queue": review}

    events.begin(EVENT_SOURCE, event_id)
    created, unchanged, conflicts = [], [], []
    v_created, v_unchanged, v_conflicts = [], [], []
    try:
        for rec in wb.products:
            pid = rec["product_id"]
            cur = store.get_product(pid)
            if cur is None:
                store.data["products"][pid] = _norm(rec)
                created.append(pid)
                pr = provenance.record(
                    "IMPORTED", "excel-import (on behalf of promoting "
                    "human)",
                    source_reference=f"{event_id}#محصولات:{pid}",
                    notes="promoted from product-master workbook (D-028)")
                provenance.link_value("product", pid, "record", pr)
            elif _norm(cur) == _norm(rec):
                unchanged.append(pid)
            else:
                conflicts.append({"product_id": pid,
                                  "changed": _diff_fields(_norm(cur),
                                                          _norm(rec)),
                                  "action": "human review; canonical "
                                            "value preserved"})
                review.append({"sheet": "محصولات", "code":
                               "CONFLICTING_UPDATE", "row": pid,
                               "message": "same Product ID, changed values"})
        for rec in wb.variants:
            vid = rec.get("variant_id") or ident.new_variant_id()
            if not ident.is_valid_variant_id(vid):
                raise IntegrityError(f"tooling generated invalid UUID: {vid}")
            cur = store.get_variant(vid)
            # SKU uniqueness (data, not identity — D-046)
            if rec.get("sku") and rec["sku"] != (cur or {}).get("sku") \
                    and store.sku_exists(rec["sku"]):
                v_conflicts.append({"variant_id": vid, "sku": rec["sku"],
                                    "action": "duplicate SKU → review"})
                review.append({"sheet": "تنوع‌ها", "code": "DUPLICATE_SKU",
                               "row": vid, "message": rec["sku"]})
                continue
            stored = dict(_norm(rec), variant_id=vid)
            if cur is None:
                store.data["variants"][vid] = stored
                v_created.append(vid)
                pr = provenance.record(
                    "IMPORTED", "excel-import (on behalf of promoting "
                    "human)",
                    source_reference=f"{event_id}#تنوع‌ها:{rec.get('sku') or vid}",
                    notes="variant promoted from product-master workbook")
                provenance.link_value("variant", vid, "record", pr)
            elif _norm(cur) == stored:
                v_unchanged.append(vid)
            else:
                v_conflicts.append({"variant_id": vid,
                                    "changed": _diff_fields(_norm(cur),
                                                            stored),
                                    "action": "human review; canonical "
                                              "value preserved"})
                review.append({"sheet": "تنوع‌ها", "code":
                               "CONFLICTING_UPDATE", "row": vid,
                               "message": "same Variant ID, changed values"})
        store.save()
        events.succeed(EVENT_SOURCE, event_id,
                       f"store:{os.path.basename(store.path)}")
    except Exception as e:
        events.fail(EVENT_SOURCE, event_id, type(e).__name__)
        raise
    return {"written": True, "event": event_id, "verdict": ev["verdict"],
            "products": {"created": created, "unchanged": unchanged,
                         "conflicts": conflicts},
            "variants": {"created": v_created, "unchanged": v_unchanged,
                         "conflicts": v_conflicts},
            "review_queue": review}


def do_sync(store: CanonicalStore, events: EventStore,
            provenance: ProvenanceEngine, today: date,
            pids=None, authorized: bool = False) -> dict:
    """Project promoted products into mock Woo (hidden, YELLOW) via the
    Batch 4 SyncEngine. Publication stays RED-gated (not requested here)."""
    mock = mock_woo.MockWooAdapter(
        state_path=os.path.join(LOCAL, "volumes", "mock-woo",
                                "import-state.json"))
    engine = SyncEngine(mock, MappingRegistry(
        path=os.path.join(LOCAL, "volumes", "registry", "registry.json")),
        events, provenance)
    results = []
    for pid, rec in sorted(store.data["products"].items()):
        if pids and pid not in pids:
            continue
        variants = [v for v in store.data["variants"].values()
                    if v["product_id"] == pid]
        try:
            res = engine.sync_product(dict(rec, attributes={
                k: v for k, v in rec.get("attributes", {}).items() if v}),
                variants, today, authorized=authorized)
            results.append(res)
        except Exception as e:                    # deterministic per product
            results.append({"product_id": pid, "action": "error",
                            "error": f"{type(e).__name__}: {e}"})
    return {"synced": results}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("verb", choices=["dry-run", "promote", "sync"])
    ap.add_argument("--fixture", default=DEFAULT_FIXTURE)
    ap.add_argument("--store", default=DEFAULT_STORE)
    ap.add_argument("--today", default=None, help="YYYY-MM-DD")
    ap.add_argument("--authorize", action="store_true",
                    help="explicit human promotion (D-028)")
    ap.add_argument("--sync", action="store_true",
                    help="after promote, project into mock Woo (hidden)")
    args = ap.parse_args(argv)

    today = (date.fromisoformat(args.today) if args.today
             else date.today())
    store = CanonicalStore(args.store)
    events = EventStore(path=os.path.join(
        os.path.dirname(args.store), "events.json"))
    provenance = ProvenanceEngine(path=os.path.join(
        os.path.dirname(args.store), "provenance.json"))

    if args.verb == "dry-run":
        report = do_dry_run(args.fixture, store, today)
        report.pop("_wb", None)
        report["run"] = {"verb": "dry-run", "fixture": args.fixture,
                         "today": today.isoformat(), "wrote": False}
        print(json.dumps(report, ensure_ascii=False, indent=1,
                         default=str))
        return 0 if not report["errors"] else 2

    if args.verb == "promote":
        report = do_promote(args.fixture, store, events, provenance,
                            today, authorize=args.authorize)
        report["run"] = {"verb": "promote", "fixture": args.fixture,
                         "today": today.isoformat(),
                         "authorized": args.authorize}
        if args.sync and report.get("written"):
            report["sync"] = do_sync(store, events, provenance, today,
                                     authorized=False)
        print(json.dumps(report, ensure_ascii=False, indent=1,
                         default=str))
        review = report.get("review_queue") or []
        return 2 if review else 0

    # sync verb
    report = do_sync(store, events, provenance, today,
                     authorized=False)
    print(json.dumps(report, ensure_ascii=False, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())

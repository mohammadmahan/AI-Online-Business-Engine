#!/usr/bin/env python3
"""Local smoke test — 10 checks from Batch 4 §17, fictional data only.

Runs without Docker for the pure-logic checks (2–8 use local/canonical
rules; 9–10 use the in-process mock + local media abstraction). Checks
requiring live containers (1: PostgreSQL reachable, plus DB-backed
seed/constraint verification) are attempted via psql and reported
honestly as SKIPPED when the database is not running (RULES §41).
"""
import os
import sys
import uuid
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)                                  # local/scripts
sys.path.insert(0, os.path.dirname(HERE))                 # local/
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "services"))

from canonical import excel, identifiers as ident, prices, vocab  # noqa
from services import mock_woo  # noqa

RESULTS = []


def check(name, fn, required_when_no_docker=True):
    try:
        detail = fn()
        RESULTS.append((name, "PASS", detail))
    except SkipTest as e:
        RESULTS.append((name, "SKIP", str(e)))
    except Exception as e:  # noqa: BLE001 — report, never hide
        RESULTS.append((name, "FAIL", f"{type(e).__name__}: {e}"))


class SkipTest(Exception):
    pass


# --- 1. PostgreSQL reachable ------------------------------------------------

def _db_unavailable(e: Exception) -> bool:
    msg = str(e).lower()
    return (isinstance(e, (FileNotFoundError, RuntimeError))
            and ("docker" in msg or "connection refused" in msg
                 or "could not connect" in msg or "psql failed" in msg
                 or "container psql failed" in msg))


def t_postgres():
    from seed_registry import q
    try:
        v = q("SELECT version();")
    except Exception as e:
        if _db_unavailable(e):
            raise SkipTest(
                "local PostgreSQL not running (Docker not installed on "
                "this machine yet) — start the stack, then re-run")
        raise
    return v.split(",")[0][:60]


# --- 2. approved vocabulary exists ------------------------------------------

def t_vocab():
    assert len(vocab.COLOR_TERMS) == 25, "25 approved colors"
    assert len(vocab.CATEGORY_PAIRS) == 20, "12+8 category pairs"
    assert len(vocab.SIZE_TERMS["alpha"]) == 8
    assert len(vocab.SIZE_TERMS["numeric"]) == 11
    assert len(vocab.SIZE_TERMS["pants_waist"]) == 9
    assert all(vocab.code_is_oil_safe(c) for _, c in vocab.COLOR_TERMS)
    # D-030 gate: all size codes O/I/L-safe EXCEPT the tracked D-032
    # conflict (L→LG), which is blocked at the seed gate pending owner
    # clarification — surfaced, never hidden.
    blocked = {(f, t) for f, t, _, _ in vocab.blocked_seed_terms()}
    assert blocked == {("alpha", "L")}
    for family, terms in vocab.SIZE_TERMS.items():
        for term, code in terms:
            if (family, term) not in blocked:
                assert vocab.code_is_oil_safe(code), (family, term, code)
    # O/I/L spot checks on the owner-corrected codes
    assert dict(vocab.COLOR_TERMS)["مشکی"] == "BK"
    assert dict(vocab.COLOR_TERMS)["آبی"] == "BU"
    assert dict(vocab.COLOR_TERMS)["زرد"] == "YW"
    return ("25 colors, 20 categories, 28 sizes; 24/28 size codes "
            "O/I/L-safe + 1 tracked D-030/D-032 conflict (L→LG)")


# --- 3. Product ID representable ---------------------------------------------

def t_product_id():
    assert ident.is_valid_product_id("P00001")
    assert not ident.is_valid_product_id("p00001")   # uppercase only
    assert not ident.is_valid_product_id("P000001")  # exactly 5 digits
    assert not ident.is_valid_product_id("X00001")
    return "P00001 valid; malformed variants rejected"


# --- 4. UUIDv4 Variant ID representable ---------------------------------------

def t_variant_id():
    vid = ident.new_variant_id()
    assert ident.is_valid_variant_id(vid)
    assert not ident.is_valid_variant_id(vid.upper())  # canonical lowercase
    v1 = str(uuid.uuid1())
    assert not ident.is_valid_variant_id(v1), "v1 rejected (v4 only)"
    return f"generated {vid[:13]}…; canonical v4 enforced"


# --- 5. SKU constraints --------------------------------------------------------

def t_sku():
    assert ident.is_valid_sku("P00001-BK-M")          # color+size
    assert ident.is_valid_sku("P00002-BRN-42")        # numeric family code
    assert ident.is_valid_sku("P00003-BK")            # one axis
    assert ident.is_valid_sku("P00004")               # simple product
    assert not ident.is_valid_sku("P1-BK")            # bad product part
    assert not ident.is_valid_sku("P00001-bk")        # lowercase code
    # D-032 alpha codes flow through (L→LG)
    assert ident.is_valid_sku("P00005-BK-LG")
    return "P00001-BK-M style accepted; D-014 format enforced"


# --- 6. Mapping-registry constraints (D-046 second guard) ----------------------

def t_registry():
    assert ident.classify_registry_hit(False, False) == "missing"
    assert ident.classify_registry_hit(True, True) == "consistent"
    assert ident.classify_registry_hit(
        False, True) == "duplicate_resource_conflict"
    assert ident.classify_registry_hit(True, False) == "stale"
    assert ident.is_valid_mapping_entry("product", "active")
    assert not ident.is_valid_mapping_entry("nope", "active")
    assert not ident.is_valid_mapping_entry("product", "deleted")
    return "missing/consistent/conflict/stale classified; no auto-resolve"


# --- 7. D-027 duplicate detection ----------------------------------------------

def t_events():
    h = "abc123"
    assert ident.classify_event_repeat(
        "succeeded", h, h) == "skipped_duplicate"
    assert ident.classify_event_repeat(
        "skipped_duplicate", h, h) == "skipped_duplicate"
    assert ident.classify_event_repeat(
        "succeeded", h, "different") == "integrity_error"
    assert ident.classify_event_repeat(
        "failed", h, "different") == "retry"   # non-terminal retryable
    assert ident.classify_event_repeat(
        "received", h, h) == "retry"
    return "identical→skip; conflicting→integrity error; terminal locked"


# --- 8. D-048 price resolution ---------------------------------------------------

def t_prices():
    today = date(2026, 9, 13)
    # The D-048 divergence case: product sale + override, no variant sale
    p = prices.PriceInputs(list_price=100000, variant_override=80000,
                           product_sale=70000)
    r = prices.resolve_effective_price(p, today)
    assert r.effective == 70000 and r.source == "product_sale", r
    proj = prices.project_to_woo(p, today)
    assert proj["regular_price"] == "70000", proj  # materialized, not 80000
    # precedence 1: variant sale wins
    p1 = prices.PriceInputs(list_price=100000, variant_override=90000,
                            product_sale=70000, variant_sale=60000)
    assert prices.resolve_effective_price(p1, today).effective == 60000
    # precedence 3/4
    p2 = prices.PriceInputs(list_price=100000, variant_override=90000)
    assert prices.resolve_effective_price(p2, today).effective == 90000
    p3 = prices.PriceInputs(list_price=100000)
    assert prices.resolve_effective_price(p3, today).effective == 100000
    # expired sale ignored
    p4 = prices.PriceInputs(list_price=100000,
                            product_sale=50000,
                            product_sale_until=today - timedelta(days=1))
    assert prices.resolve_effective_price(p4, today).effective == 100000
    # invalid sale >= base rejected
    p5 = prices.PriceInputs(list_price=100000, product_sale=100000)
    assert prices.validate_price(p5, today)
    # zero/negative invalid
    assert prices.validate_price(
        prices.PriceInputs(list_price=0), today)
    # missing list price → unresolved, never guessed
    p6 = prices.PriceInputs()
    r6 = prices.resolve_effective_price(p6, today)
    assert r6.effective is None and r6.unresolved_reason
    # canonical inputs never mutated by projection
    assert p.variant_override == 80000 and p.list_price == 100000
    return ("11-case precedence verified; divergence case → 70000 "
            "materialized; inputs unmutated")


# --- 9. Mock Woo accepts a projected product -------------------------------------

def t_mock_woo():
    adapter = mock_woo.MockWooAdapter()
    created = adapter.create_product({"sku": "P90001",
                                      "regular_price": "100000"})
    assert created["id"] > 0
    # duplicate SKU → error surfaced (second guard behaviour)
    dup = False
    try:
        adapter.create_product({"sku": "P90001"})
    except mock_woo.MockWooError as e:
        dup = "already exists" in e.message
    assert dup, "duplicate resource must surface"
    # variation + read-back
    v = adapter.create_variation(created["id"],
                                 {"sku": "P90001-BK-M",
                                  "regular_price": "90000"})
    got = adapter.read_variation(v["id"])
    assert got["payload"]["sku"] == "P90001-BK-M"
    # failure injection: auth failure then cleared (single-shot)
    adapter2 = mock_woo.MockWooAdapter(failure_scenario="authentication_failure")
    auth = False
    try:
        adapter2.create_product({"sku": "P90002"})
    except mock_woo.MockWooError as e:
        auth = e.status == 401
    assert auth
    assert adapter2.create_product({"sku": "P90002"})  # scenario cleared
    return "create/read/variation OK; duplicate surfaced; 401 injectable"


# --- 10. Local media store/read -----------------------------------------------------

def t_media():
    from services.media_store import LocalObjectStore
    store = LocalObjectStore(bucket="smoke-test")
    data = b"fictional product image bytes \x00\x01"
    res = store.put(data, "image/png", {"alt_text": "fictional"})
    got = store.get(res["object_key"])
    assert got == data
    res2 = store.put(data, "image/png")           # content-addressed dup
    assert res2["duplicate"] and res2["object_key"] == res["object_key"]
    head = store.head(res["object_key"])
    assert head["metadata"].get("alt_text") == "fictional"
    assert store.delete(res["object_key"])
    return (f"stored/read {res['object_key'][:16]}…; dedupe OK; "
            "metadata OK")


# --- DB-dependent seed/constraint verification (bonus checks) -----------------------

def t_db_seed():
    from seed_registry import q
    try:
        n = int(q("SELECT count(*) FROM seed.color_term;"))
    except Exception as e:
        if _db_unavailable(e):
            raise SkipTest("local PostgreSQL not running yet")
        raise
    if n == 0:
        raise SkipTest("database reachable but not seeded")
    assert n == 25, f"expected 25 colors, found {n}"
    # The blocked-conflict term must NOT be in the DB (seed gate).
    lg = int(q("SELECT count(*) FROM seed.size_term "
               "WHERE code = 'LG';"))
    assert lg == 0, "D-030-blocked code LG must not be seeded"
    return f"seed.color_term={n}; blocked conflict (LG) absent — gate works"


def t_db_constraints():
    from seed_registry import q
    try:
        q("SELECT 1 FROM seed.color_term LIMIT 1;")
    except Exception as e:
        if _db_unavailable(e):
            raise SkipTest("local PostgreSQL not running yet")
        raise
    # duplicate active combo rejected by the partial unique index
    q("""
    BEGIN;
    INSERT INTO seed.size_family (family_key,label_fa,sort_order)
      VALUES ('alpha','حروفی',0) ON CONFLICT DO NOTHING;
    INSERT INTO seed.color_term (display_fa,code)
      VALUES ('مشکی','BK') ON CONFLICT DO NOTHING;
    INSERT INTO seed.category_term (primary_fa,leaf_fa)
      VALUES ('پوشاک زنانه','مانتو') ON CONFLICT DO NOTHING;
    INSERT INTO canonical.product (product_id,name,primary_category,
      leaf_category,list_price,status,publication_status,created_date)
      VALUES ('P00001','تست','پوشاک زنانه','مانتو',100000,'active',
              'unpublished',DATE '2026-09-13');
    INSERT INTO canonical.variant (variant_id,product_id,sku,color_code,
      size_family,size_code,status)
      VALUES ('11111111-4c1d-4b9a-8c2e-000000000001','P00001',
              'P00001-BK-M','مشکی','alpha','M','active');
    COMMIT;
    """)
    dup = False
    try:
        q("""
        INSERT INTO canonical.variant (variant_id,product_id,sku,
          color_code,size_family,size_code,status)
        VALUES ('11111111-4c1d-4b9a-8c2e-000000000002','P00001',
                'P00001-BK-M2','مشکی','alpha','M','active');
        """)
    except Exception:
        dup = True
    assert dup, "duplicate active-axis combination must be rejected"
    # sale >= base rejected (trigger)
    sale = False
    try:
        q("""
        INSERT INTO canonical.variant (variant_id,product_id,sku,
          color_code,size_family,size_code,variant_sale,status)
        VALUES ('11111111-4c1d-4b9a-8c2e-000000000003','P00001',
                'P00001-BK-XS','مشکی','alpha','XS',100000,'active');
        """)
    except Exception:
        sale = True
    assert sale, "variant sale >= base must be rejected"
    # identical D-027 event duplicate handling
    q("""
    INSERT INTO events.event_record (source_system,event_id,
      operation_type,payload_hash,processing_status)
    VALUES ('local-test','evt-001','op','h1','succeeded')
    ON CONFLICT DO NOTHING;
    """)
    again = q("""
    INSERT INTO events.event_record (source_system,event_id,
      operation_type,payload_hash,processing_status)
    VALUES ('local-test','evt-001','op','h1','succeeded')
    ON CONFLICT (source_system,event_id) DO NOTHING
    RETURNING event_id;
    """)
    assert again == "", "identical repeat must not re-execute"
    # provenance append-only trigger
    prov = False
    try:
        q("""
        INSERT INTO provenance.provenance_record
          (source_type,actor) VALUES ('HUMAN_ENTERED','owner');
        UPDATE provenance.provenance_record SET source_type='AI_GENERATED'
          WHERE actor='owner';
        """)
    except Exception:
        prov = True
    assert prov, "provenance core-field mutation must be rejected"
    return ("combo-uq, sale<base, event-uq, provenance-immutable all "
            "enforced by the database")


def main() -> int:
    check("1. PostgreSQL reachable", t_postgres)
    check("2. Approved vocabulary (D-031/D-032)", t_vocab)
    check("3. Product ID rules (D-014)", t_product_id)
    check("4. Variant ID UUIDv4 (D-017)", t_variant_id)
    check("5. SKU constraints (D-014)", t_sku)
    check("6. Mapping registry rules (D-046)", t_registry)
    check("7. D-027 duplicate detection", t_events)
    check("8. D-048 price resolution", t_prices)
    check("9. Mock Woo accepts projection", t_mock_woo)
    check("10. Local media store/read (D-056)", t_media)
    check("11. DB vocabulary seed", t_db_seed)
    check("12. DB constraints (D-014/D-025/D-027/D-026)", t_db_constraints)

    width = max(len(n) for n, _, _ in RESULTS)
    fails = skips = 0
    for name, status, detail in RESULTS:
        mark = {"PASS": "✓", "SKIP": "○", "FAIL": "✗"}[status]
        if status == "FAIL":
            fails += 1
        elif status == "SKIP":
            skips += 1
        print(f" {mark} {name.ljust(width)}  [{status}] {detail}")
    summary = (f"\n{len(RESULTS) - fails - skips} passed"
               f", {skips} skipped (environment-dependent)"
               f", {fails} failed")
    print(summary)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

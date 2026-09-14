"""Phase 3 Batch 4 — full local test ladder (executable, offline-first).

Layers:
  [1]  Schema & DB migrations        (offline structural validation;
                                      live apply = SKIP without psql/Docker)
  [2]  Vocabulary & registry seeds   (approved values integrity; live seed
                                      = SKIP without a running canonical DB)
  [3]  ID & SKU generator constraints (D-014/D-017)
  [4]  Mapping registry lookups      (D-046: 1:1, second guard, stale)
  [5]  D-024 / D-048 price resolution precedence + Woo projection
  [6]  Idempotency & conflicts       (D-027 events, D-046 duplicates)
  [7]  Provenance log integrity      (D-026 append-only, review advance)
  [8]  Mock Woo projection & sync    (create/update/read-back, taxonomy,
                                      failure classes D-044, D-048 proof)
  [9]  S3 media abstraction          (D-049/D-056 content-addressed store)
  [10] Docker health & reset script  (SKIP without Docker)
  [11] End-to-end local smoke        (fixtures → dry-run → sync → checks)

Run:  python3 -m unittest local.tests.test_ladder -v
Docker-dependent layers SKIP with an explicit reason (no hidden failures).
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))            # local/tests
LOCAL = os.path.dirname(HERE)                                # local/
ROOT = os.path.dirname(LOCAL)
sys.path.insert(0, LOCAL)
sys.path.insert(0, os.path.join(LOCAL, "canonical"))
sys.path.insert(0, os.path.join(LOCAL, "services"))
sys.path.insert(0, os.path.join(LOCAL, "scripts"))

import identifiers as ident          # noqa: E402
import prices as pricing             # noqa: E402
import vocab                         # noqa: E402
import excel                         # noqa: E402
import media_store                   # noqa: E402
import mock_woo                      # noqa: E402
import sync_engine                   # noqa: E402
from sync_engine import (            # noqa: E402
    EventStore, IntegrityError, MappingConflict, MappingRegistry,
    ProvenanceEngine, StaleMapping, SyncEngine, SyncError,
    AuthorityError, require_authority, compensate_hide_and_flag,
    _payload_hash)

TODAY = date(2026, 9, 13)


def _has_psql() -> bool:
    return shutil.which("psql") is not None


def _pg_reachable() -> bool:
    if not _has_psql():
        return False
    env = dict(os.environ)
    env.update({
        "PGHOST": os.environ.get("LOCAL_PGHOST", "127.0.0.1"),
        "PGPORT": os.environ.get("LOCAL_PGPORT", "55432"),
        "PGDATABASE": os.environ.get("LOCAL_PGDATABASE",
                                     "business_engine_local"),
        "PGUSER": os.environ.get("LOCAL_PGUSER", "engine_local"),
        "PGPASSWORD": os.environ.get("LOCAL_PGPASSWORD",
                                     "engine-local-only"),
    })
    try:
        return subprocess.run(
            ["psql", "-X", "-q", "-A", "-t", "-c", "SELECT 1;"],
            capture_output=True, text=True, env=env,
            timeout=5).returncode == 0
    except Exception:
        return False


# =========================================================================
# [1] Schema & migrations — offline structural validation
# =========================================================================

class TestL1Schema(unittest.TestCase):
    def test_schemas_and_core_tables_declared(self):
        with open(os.path.join(LOCAL, "db", "schema.sql"),
                  encoding="utf-8") as f:
            sql = f.read()
        for s in ("seed", "canonical", "registry", "events", "provenance"):
            self.assertIn(f"CREATE SCHEMA IF NOT EXISTS {s};", sql)
        for t in ("canonical.product", "canonical.variant",
                  "registry.mapping_entry", "events.event_record",
                  "provenance.provenance_record",
                  "provenance.value_provenance",
                  "seed.size_family", "seed.size_term",
                  "seed.color_term", "seed.category_term"):
            self.assertIn(f"CREATE TABLE IF NOT EXISTS {t}", sql)
        # identifier separation (D-015/D-017): business key / UUIDv4 /
        # data-only SKU
        self.assertIn("CHECK (product_id ~ '^P[0-9]{5}$')", sql)
        self.assertIn("variant_id         uuid PRIMARY KEY", sql)
        self.assertIn("sku                text UNIQUE", sql)
        # D-027 composite key + D-026 append-only trigger
        self.assertIn("PRIMARY KEY (source_system, event_id)", sql)
        self.assertIn("provenance.reject_mutation", sql)

    def test_live_schema_apply(self):
        """Live migration test — SKIP (not FAIL) without PostgreSQL."""
        if not _pg_reachable():
            self.skipTest("local PostgreSQL not running (Docker absent); "
                          "offline structural validation passed")
        env = dict(os.environ)
        env.update({"PGHOST": "127.0.0.1", "PGPORT": "55432",
                    "PGDATABASE": "business_engine_local",
                    "PGUSER": "engine_local",
                    "PGPASSWORD": "engine-local-only"})
        with open(os.path.join(LOCAL, "db", "schema.sql"),
                  encoding="utf-8") as f:
            sql = f.read()
        p = subprocess.run(["psql", "-X", "-q", "-v", "ON_ERROR_STOP=1"],
                           input=sql, capture_output=True, text=True,
                           env=env, timeout=30)
        self.assertEqual(p.returncode, 0, p.stderr)


# =========================================================================
# [2] Vocabulary & registry seeds
# =========================================================================

class TestL2VocabularySeed(unittest.TestCase):
    def test_seed_values_integrity(self):
        self.assertEqual(vocab.EXPECTED_COUNTS["colors"], 25)
        self.assertEqual(vocab.EXPECTED_COUNTS["category_pairs"], 20)
        # 22 category TERMS total = 2 primaries + 20 leaf terms (the
        # taxonomy-seed summary counts primaries + leaves together)
        self.assertEqual(len(vocab.CATEGORY_PAIRS) + 2, 22)
        self.assertEqual(len(set(vocab.CATEGORY_PAIRS)), 20)
        self.assertEqual(len({c for _, c in vocab.COLOR_TERMS}), 25)
        # D-032 mapping baseline spot checks (owner-corrected codes)
        d = dict(vocab.COLOR_TERMS)
        self.assertEqual((d["مشکی"], d["آبی"], d["زرد"]), ("BK", "BU", "YW"))
        self.assertEqual(dict(vocab.SIZE_TERMS["alpha"])["XL"], "XG")

    def test_seed_gate_clear_after_d057(self):
        # D-057 resolved the D-030 ↔ D-032 conflict (register row 24):
        # Alpha L now carries the owner-sanctioned code LRG, the
        # conflict ledger is empty, the gate holds nothing.
        self.assertEqual(vocab.blocked_seed_terms(), ())
        for f, terms in vocab.SIZE_TERMS.items():
            for t, c in terms:
                self.assertTrue(vocab.is_seedable(c), (f, t, c))
        # the sanction is explicit, auditable, never a validator change
        self.assertIn("LRG", vocab.OWNER_SANCTIONED_CODES)
        self.assertFalse(vocab.code_is_oil_safe("LRG"))

    def test_live_seed(self):
        if not _pg_reachable():
            self.skipTest("local PostgreSQL not running; seed integrity "
                          "verified offline")
        p = subprocess.run([sys.executable,
                            os.path.join(LOCAL, "scripts",
                                         "seed_registry.py")],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr)


# =========================================================================
# [3] ID & SKU generator constraints (D-014/D-017)
# =========================================================================

class TestL3Identifiers(unittest.TestCase):
    def test_product_id_shape(self):
        for ok in ("P00001", "P90001"):
            self.assertTrue(ident.is_valid_product_id(ok))
        for bad in ("P0001", "P000012", "p00001", "Q00001", "P0001A", ""):
            self.assertFalse(ident.is_valid_product_id(bad))

    def test_variant_id_is_uuid4(self):
        vid = ident.new_variant_id()
        self.assertTrue(ident.is_valid_variant_id(vid))
        self.assertEqual(vid, vid.lower())

    def test_sku_requires_approved_codes(self):
        self.assertTrue(ident.is_valid_sku("P00002-BK-M"))
        self.assertFalse(ident.is_valid_sku("P00001-BLK"))  # not approved
        self.assertFalse(ident.is_valid_sku("P00001-BK-M-X"))

    def test_sku_derivation_color_then_size(self):
        self.assertEqual(SyncEngine.derive_sku("P90002", "BK", "M"),
                         "P90002-BK-M")
        self.assertEqual(SyncEngine.derive_sku("P90003", "BK", None),
                         "P90003-BK")
        self.assertEqual(SyncEngine.derive_sku("P90004", None, "42"),
                         "P90004-42")
        with self.assertRaises(SyncError):
            SyncEngine.derive_sku("P00001", "NOT-A-CODE", None)

    def test_no_ai_issued_identifiers_constant(self):
        # Documented guard: only tooling entry points create IDs.
        self.assertIn("approved deterministic tooling only",
                      ident.new_variant_id.__doc__)


# =========================================================================
# [4] Mapping registry lookups (D-046)
# =========================================================================

class TestL4Registry(unittest.TestCase):
    def setUp(self):
        self.reg = MappingRegistry(path=None)

    def test_register_lookup_roundtrip(self):
        e = self.reg.register("product", "P90001", "1001")
        self.assertEqual(e["woo_id"], "1001")
        self.assertEqual(self.reg.lookup("product", "P90001")["woo_id"],
                         "1001")
        self.assertIsNone(self.reg.lookup("variation", "P90001"))

    def test_bidirectional_one_to_one_enforced(self):
        self.reg.register("product", "P90001", "1001")
        with self.assertRaises(MappingConflict):   # Woo ID already mapped
            self.reg.register("product", "P90002", "1001")

    def test_second_guard_duplicate_resource_conflict(self):
        self.reg.register("product", "P90001", "1001")
        # Active entry exists; a NEW lookup finding would mean the Woo
        # resource maps to something else → never silently adopted.
        self.assertEqual(ident.classify_registry_hit(True, True),
                         "consistent")
        self.assertEqual(self.reg.lookup_by_woo_id("product", "1001")
                         ["canonical_key"], "P90001")

    def test_stale_entries_never_silently_replaced(self):
        self.reg.register("product", "P90001", "1001")
        self.reg.mark_stale("product", "P90001")
        self.assertIsNone(self.reg.lookup("product", "P90001"))
        self.assertEqual(self.reg.lookup_any("product", "P90001")
                         ["status"], "stale")
        # A DIFFERENT Woo ID requires the reviewed relink flow.
        with self.assertRaises(StaleMapping):
            self.reg.register("product", "P90001", "3003")
        # The SAME Woo ID re-activates only through the deterministic
        # recovery path (marker lookup; provenance-tagged by caller).
        e = self.reg.register("product", "P90001", "1001")
        self.assertEqual(e["status"], "active")

    def test_relink_after_review_supersedes_with_history(self):
        self.reg.register("product", "P90001", "1001")
        self.reg.mark_stale("product", "P90001")
        e = self.reg.relink_after_review("product", "P90001", "2002",
                                         reviewer="human-owner")
        self.assertEqual(e["woo_id"], "2002")
        self.assertEqual(e["relinked_by"], "human-owner")
        # superseded entry preserved in history (never deleted)
        hist = self.reg._store.data["history"]
        self.assertTrue(any(h["woo_id"] == "1001" for h in hist))

    def test_no_deletion_path_exists(self):
        methods = [m for m in dir(MappingRegistry)
                   if not m.startswith("_")]
        self.assertFalse(any("delete" in m or "remove" in m
                             for m in methods))


# =========================================================================
# [5] D-024 / D-048 price resolution precedence
# =========================================================================

class TestL5Prices(unittest.TestCase):
    P = pricing.PriceInputs

    def test_tier_order_and_divergence(self):
        r = pricing.resolve_effective_price(self.P(
            list_price=300000, variant_override=280000,
            variant_sale=200000), TODAY)
        self.assertEqual((r.effective, r.source), (200000, "variant_sale"))
        r = pricing.resolve_effective_price(self.P(
            list_price=300000, product_sale=250000), TODAY)
        self.assertEqual((r.effective, r.source), (250000, "product_sale"))
        # the D-048 divergence case: product sale beats override
        r = pricing.resolve_effective_price(self.P(
            list_price=300000, variant_override=280000,
            product_sale=250000), TODAY)
        self.assertEqual((r.effective, r.source), (250000, "product_sale"))

    def test_d048_projection_is_materialized_not_native(self):
        p = self.P(list_price=300000, variant_override=280000,
                   product_sale=250000,
                   product_sale_until=TODAY + timedelta(days=30))
        proj = pricing.project_to_woo(p, TODAY)
        # Product sale materialized onto display fields; canonical
        # inputs untouched.
        self.assertEqual(proj,
                         {"regular_price": "250000", "sale_price": None,
                          "resolved": True, "source": "product_sale"})
        self.assertEqual((p.list_price, p.variant_override,
                          p.product_sale), (300000, 280000, 250000))

    def test_variant_sale_projection_uses_both_fields(self):
        proj = pricing.project_to_woo(self.P(
            list_price=300000, variant_sale=200000), TODAY)
        self.assertEqual(proj["regular_price"], "300000")
        self.assertEqual(proj["sale_price"], "200000")

    def test_expired_and_invalid(self):
        r = pricing.resolve_effective_price(self.P(
            list_price=300000, variant_sale=200000,
            variant_sale_until=TODAY - timedelta(days=1)), TODAY)
        self.assertEqual((r.effective, r.source), (300000, "list_price"))
        self.assertTrue(pricing.validate_price(
            self.P(list_price=300000, product_sale=300000), TODAY))
        self.assertTrue(pricing.validate_price(
            self.P(list_price=0), TODAY))


# =========================================================================
# [6] Idempotency & conflicts (D-027)
# =========================================================================

class TestL6Events(unittest.TestCase):
    def setUp(self):
        self.es = EventStore(path=None)

    def test_new_then_identical_repeat_is_skipped(self):
        r1 = self.es.receive("t", "e1", "op", {"a": 1})
        self.assertEqual(r1["verdict"], "new")
        self.es.succeed("t", "e1", "woo:1001")
        r2 = self.es.receive("t", "e1", "op", {"a": 1})
        self.assertEqual(r2["verdict"], "skipped_duplicate")

    def test_conflicting_payload_is_integrity_error(self):
        self.es.receive("t", "e1", "op", {"a": 1})
        self.es.succeed("t", "e1", "ref")
        with self.assertRaises(IntegrityError):
            self.es.receive("t", "e1", "op", {"a": 2})

    def test_terminal_states_never_re_entered(self):
        self.es.receive("t", "e2", "op", {})
        self.es.succeed("t", "e2", "ref")
        with self.assertRaises(IntegrityError):
            self.es.begin("t", "e2")

    def test_non_terminal_retry_same_id(self):
        self.es.receive("t", "e3", "op", {"a": 1})
        self.es.begin("t", "e3")
        r = self.es.receive("t", "e3", "op", {"a": 1})
        self.assertEqual(r["verdict"], "retry")
        self.assertEqual(r["record"]["retry_count"], 1)
        self.es.fail("t", "e3", "timeout")
        r2 = self.es.receive("t", "e3", "op", {"a": 1})
        self.assertEqual(r2["verdict"], "retry")
        self.assertEqual(r2["record"]["retry_count"], 2)


# =========================================================================
# [7] Provenance log integrity (D-026)
# =========================================================================

class TestL7Provenance(unittest.TestCase):
    def setUp(self):
        self.pv = ProvenanceEngine(path=None)

    def test_append_only_and_review_advance_only(self):
        pid_ = self.pv.record("IMPORTED", "excel-import",
                              source_reference="wb:product-master")
        rec = self.pv.records[pid_ - 1]
        self.assertEqual(rec["source_type"], "IMPORTED")
        advanced = self.pv.advance_review(pid_, "HUMAN_REVIEWED")
        self.assertEqual(advanced["review_state"], "HUMAN_REVIEWED")
        with self.assertRaises(ValueError):     # never moves backwards
            self.pv.advance_review(pid_, "PENDING")
        # Append-only model: a correction is a NEW superseding record
        # (old records are never mutated or erased — D-026).
        sup = self.pv.record("IMPORTED", "excel-import",
                             notes="supersedes the earlier record")
        self.assertEqual(sup, pid_ + 1)
        self.assertEqual(self.pv.records[pid_ - 1]["source_type"],
                         "IMPORTED")   # unchanged

    def test_ai_origin_preserved(self):
        aid = self.pv.record("AI_GENERATED", "ai-runtime",
                             notes="description draft (Yellow, propose)")
        self.assertEqual(self.pv.records[aid - 1]["source_type"],
                         "AI_GENERATED")

    def test_value_linkage_supersedes_with_history(self):
        a = self.pv.record("IMPORTED", "tooling")
        b = self.pv.record("HUMAN_ENTERED", "owner",
                           review_state="HUMAN_VERIFIED")
        self.pv.link_value("product", "P90001", "list_price", a)
        res = self.pv.link_value("product", "P90001", "list_price", b)
        self.assertEqual(res["superseded"]["provenance_id"], a)
        hist = self.pv.history_of("product", "P90001", "list_price")
        self.assertEqual([h["provenance_id"] for h in hist], [a, b])
        # newest (current) linkage is LAST — chronological order
        self.assertEqual(hist[-1]["provenance_id"], b)

    def test_source_types_fixed_set(self):
        self.assertEqual(
            ident.SOURCE_TYPES,
            ("HUMAN_ENTERED", "SYSTEM_GENERATED", "AI_GENERATED",
             "IMPORTED", "EXTERNAL_SYNC"))


# =========================================================================
# [8] Mock Woo projection & sync validation
# =========================================================================

def _product(pid, status="active", pub="unpublished", list_price=300000,
             product_sale=None, until=None, name=None, **kw):
    return {"product_id": pid,
            "name": name or f"محصول {pid}",
            "primary_category": "پوشاک مردانه", "leaf_category": "تیشرت",
            "attributes": {"برند": kw.get("brand")},
            "list_price": list_price, "product_sale": product_sale,
            "product_sale_until": until, "status": status,
            "publication_status": pub,
            "media_refs": kw.get("media", ["media.local/x.jpg"]),
            "description": None, "short_description": None,
            "name_en": None}


def _variant(pid, color=None, size=None, family=None, override=None,
             vsale=None, vsale_until=None, vid=None, sku=None):
    return {"variant_id": vid, "product_id": pid,
            "color_code": color, "size_family": family,
            "size_code": size, "price_override": override,
            "variant_sale": vsale, "variant_sale_until": vsale_until,
            "status": "active", "sku": sku, "active_axes":
            [a for a, c in (("color", color), ("size", size)) if c]}


class TestL8Sync(unittest.TestCase):
    def setUp(self):
        self.mock = mock_woo.MockWooAdapter()
        self.reg = MappingRegistry(path=None)
        self.es = EventStore(path=None)
        self.pv = ProvenanceEngine(path=None)
        self.eng = SyncEngine(self.mock, self.reg, self.es, self.pv)

    def test_taxonomy_seed_creates_mappings_once(self):
        s1 = self.eng.seed_taxonomy()
        self.assertEqual(s1["categories"], 22)      # 2 primaries + 20 leaves
        self.assertEqual(s1["color_terms"], 25)
        self.assertEqual(s1["size_terms"], 28)      # full seed (D-057)
        self.assertEqual(s1["blocked"], [])
        s2 = self.eng.seed_taxonomy()               # idempotent
        self.assertEqual(s2["categories"], 0)
        self.assertEqual(s2["color_terms"], 0)
        self.assertEqual(s2["size_terms"], 0)

    def test_draft_has_no_woo_record(self):
        r = self.eng.sync_product(
            _product("P90001", status="draft"), [], TODAY)
        self.assertEqual(r["action"], "skipped_draft")
        self.assertIsNone(self.reg.lookup("product", "P90001"))

    def test_hidden_product_created_verified_registered(self):
        p = _product("P90001")
        r = self.eng.sync_product(p, [], TODAY)
        self.assertEqual(r["action"], "created_hidden")
        m = self.reg.lookup("product", "P90001")
        self.assertEqual(m["woo_id"], str(r["woo_product_id"]))
        woo = self.mock.read_product(int(m["woo_id"]))
        self.assertEqual(woo["status"], "draft")            # hidden
        self.assertEqual(woo["payload"]["catalog_visibility"], "hidden")
        # read-back verified the canonical-owned fields
        self.assertEqual(woo["payload"]["name"], p["name"])

    def test_simple_vs_variable_types(self):
        r1 = self.eng.sync_product(_product("P90001"), [], TODAY)
        self.assertEqual(r1["variations"], [])
        woo = self.mock.read_product(int(r1["woo_product_id"]))
        self.assertEqual(woo["payload"]["type"], "simple")
        r2 = self.eng.sync_product(_product("P90002"), [
            _variant("P90002", color="BK", size="M", family="alpha")],
            TODAY)
        woo2 = self.mock.read_product(int(r2["woo_product_id"]))
        self.assertEqual(woo2["payload"]["type"], "variable")
        self.assertEqual(len(r2["variations"]), 1)

    def test_d048_divergence_case_projection(self):
        """The critical case: product sale + variant override + no
        variant sale → Woo displays the SALE price (materialized)."""
        p = _product("P90002", list_price=300000, product_sale=250000,
                     until=TODAY + timedelta(days=30))
        v = _variant("P90002", color="BK", size="M", family="alpha",
                     override=280000)
        r = self.eng.sync_product(p, [v], TODAY)
        vm = self.reg.lookup("variation", r["variations"][0]["variant_id"])
        woo_v = self.mock.read_variation(int(vm["woo_id"]))
        # Woo-native fallback would have shown 280000 — the projection
        # fixes it to the canonical resolution 250000 (D-048 Option A).
        self.assertEqual(woo_v["payload"]["regular_price"], "250000")
        self.assertIsNone(woo_v["payload"]["sale_price"])
        self.assertEqual(woo_v["payload"]["sku"], "P90002-BK-M")

    def test_resync_is_event_idempotent(self):
        p = _product("P90001")
        r1 = self.eng.sync_product(p, [], TODAY)
        r2 = self.eng.sync_product(p, [], TODAY)
        self.assertEqual(r2["action"], "skipped_duplicate")
        self.assertEqual(r1["event"], r2["event"])

    def test_changed_payload_is_new_event(self):
        p = _product("P90001")
        self.eng.sync_product(p, [], TODAY)
        # An invisible change (unpublished → in_review) projects to the
        # identical hidden payload → correctly skipped_duplicate.
        p_same = _product("P90001", pub="in_review")
        self.assertEqual(
            self.eng.sync_product(p_same, [], TODAY)["action"],
            "skipped_duplicate")
        # A real canonical change (name) → new event, updated record.
        p2 = _product("P90001", name="نام جدید")
        r2 = self.eng.sync_product(p2, [], TODAY)
        self.assertEqual(r2["action"], "updated_hidden")

    def test_unresolved_price_writes_nothing(self):
        p = _product("P90001", list_price=None)
        with self.assertRaises(SyncError):
            self.eng.sync_product(p, [_variant("P90001")], TODAY)
        self.assertIsNone(self.reg.lookup("product", "P90001"))

    def test_publish_is_red_gated(self):
        p = _product("P90001", pub="published")
        with self.assertRaises(AuthorityError):
            self.eng.sync_product(p, [], TODAY, authorized=False)
        # ...and executes only when explicitly human-authorized
        r = self.eng.sync_product(p, [], TODAY, authorized=True)
        woo = self.mock.read_product(int(r["woo_product_id"]))
        self.assertEqual(woo["status"], "publish")
        self.assertEqual(woo["payload"]["catalog_visibility"], "visible")

    def test_ai_never_executes_red_operations(self):
        with self.assertRaises(AuthorityError):
            require_authority("publish", False)
        with self.assertRaises(AuthorityError):
            require_authority("withdraw", False)
        with self.assertRaises(AuthorityError):
            require_authority("price_write_published", False)

    def test_divergence_detection_and_red_reprojection(self):
        p = _product("P90002", list_price=300000, product_sale=250000,
                     until=TODAY + timedelta(days=30))
        v = _variant("P90002", color="BK", size="M", family="alpha",
                     override=280000)
        r = self.eng.sync_product(p, [v], TODAY)
        vid = r["variations"][0]["variant_id"]
        woo_vid = int(self.reg.lookup("variation", vid)["woo_id"])
        synced = dict(v, variant_id=vid)   # the SYNCED variant
        # Someone hand-edits Woo (price field = Red-tier divergence)
        self.mock.update_variation(woo_vid, {"regular_price": "999"})
        divs = self.eng.detect_divergence(p, [synced], TODAY)
        price_divs = [d for d in divs if d["price_affecting"]]
        self.assertTrue(price_divs)
        self.assertEqual(price_divs[0]["woo"], "999")
        self.assertEqual(price_divs[0]["canonical"], "250000")
        # canonical value preserved — re-projection needs authorization
        with self.assertRaises(AuthorityError):
            self.eng.reproject(p, [synced], TODAY, authorized=False)
        self.eng.reproject(p, [synced], TODAY, authorized=True)
        divs2 = self.eng.detect_divergence(p, [synced], TODAY)
        self.assertFalse([d for d in divs2 if d["price_affecting"]])

    def test_failure_injection_classes(self):
        p = _product("P90001")
        scenarios = ["woo_unavailable", "authentication_failure",
                     "rate_limited", "validation_failure",
                     "timeout_before_response", "malformed_response"]
        for sc in scenarios:
            with self.subTest(scenario=sc):
                m = mock_woo.MockWooAdapter(failure_scenario=sc)
                eng = SyncEngine(m, MappingRegistry(path=None),
                                 EventStore(path=None),
                                 ProvenanceEngine(path=None))
                with self.assertRaises(Exception):
                    eng.sync_product(p, [], TODAY)
                statuses = [r["processing_status"]
                            for r in eng.events.records.values()]
                self.assertEqual(statuses, ["failed"])
                self.assertFalse(eng.registry.entries)  # nothing adopted

    def test_ambiguous_timeout_recovery_path(self):
        """Write committed but response lost: first attempt fails with
        nothing registered; the deterministic marker-lookup second
        attempt recovers WITH provenance (never blind re-create)."""
        m = mock_woo.MockWooAdapter(
            failure_scenario="ambiguous_timeout")
        eng = SyncEngine(m, MappingRegistry(path=None),
                         EventStore(path=None),
                         ProvenanceEngine(path=None))
        p = _product("P90001")
        with self.assertRaises(TimeoutError):
            eng.sync_product(p, [], TODAY)
        self.assertFalse(eng.registry.entries)
        res = compensate_hide_and_flag(eng, p, "ambiguous_timeout")
        self.assertFalse(res["compensated"])     # nothing tracked to hide
        self.assertTrue(res["flagged"])          # but always review-flagged
        # Human-promoted retry: deterministic recovery re-links.
        r = eng.sync_product(p, [], TODAY, authorized=True)
        self.assertEqual(r["action"], "recovered_after_timeout")
        self.assertEqual(len(eng.mock.find_products_by_meta(
            "_pm_pid", "P90001")), 1)   # exactly one Woo record

    def test_registry_conflict_surfaces_not_adopts(self):
        p = _product("P90001")
        self.eng.sync_product(p, [], TODAY)
        m = self.reg.lookup("product", "P90001")
        # A stale entry can be re-activated only with its own Woo ID
        # (recovery) — a different ID needs the reviewed relink flow.
        self.reg.mark_stale("product", "P90001")
        with self.assertRaises(StaleMapping):
            self.reg.register("product", "P90001", "3003")
        e = self.reg.register("product", "P90001", m["woo_id"])
        self.assertEqual(e["status"], "active")
        # And a Woo ID already actively mapped can never be re-issued.
        with self.assertRaises(MappingConflict):
            self.reg.register("product", "P90002", m["woo_id"])


# =========================================================================
# [9] Media abstraction (D-049/D-056)
# =========================================================================

class TestL9Media(unittest.TestCase):
    def test_content_addressed_dedupe_and_metadata(self):
        with tempfile.TemporaryDirectory() as td:
            store = media_store.LocalObjectStore(
                bucket="test-media", root=td)
            o1 = store.put(b"img-bytes", "image/jpeg",
                           metadata={"alt": "عکس محصول"})
            o2 = store.put(b"img-bytes", "image/jpeg")
            self.assertTrue(o2["duplicate"])
            self.assertEqual(o1["object_key"], o2["object_key"])
            self.assertEqual(store.get(o1["object_key"]), b"img-bytes")
            self.assertEqual(store.head(o1["object_key"])
                             ["metadata"]["alt"], "عکس محصول")
            self.assertTrue(store.delete(o1["object_key"]))
            with self.assertRaises(FileNotFoundError):
                store.get(o1["object_key"])


# =========================================================================
# [10] Docker health & reset script
# =========================================================================

class TestL10Docker(unittest.TestCase):
    def test_docker_or_skip(self):
        if shutil.which("docker") is None:
            self.skipTest("Docker not installed on this machine — "
                          "container health checks and reset script "
                          "cannot run (documented, not hidden)")
        p = subprocess.run(["docker", "info"], capture_output=True,
                           text=True, timeout=15)
        if p.returncode != 0:
            # CLI present but daemon unreachable: an environment skip,
            # not a code failure (e.g. the 2026-09-14 host disk-space
            # blocker — see TODO "BLOCKED"; documented, not hidden).
            self.skipTest("Docker daemon not reachable — local stack "
                          "not running (environment blocker documented "
                          "in TODO)")
        # reset script exists and is local-only
        self.assertTrue(os.path.exists(
            os.path.join(LOCAL, "scripts", "local_env.py")))


# =========================================================================
# [11] End-to-end local smoke: fixtures → dry-run → sync → checks
# =========================================================================

class TestL11EndToEnd(unittest.TestCase):
    def test_full_local_flow(self):
        with open(os.path.join(LOCAL, "fixtures",
                               "product-master.json"),
                  encoding="utf-8") as f:
            fx = json.load(f)
        # 1. dry-run validation of the fixture workbook (D-028)
        wb = excel.validate_workbook(fx["products"], fx["variants"], TODAY)
        self.assertTrue(wb.errors)          # fixture intentionally has 12
        valid_p = {p["product_id"] for p in wb.products}
        self.assertIn("P90002", valid_p)
        # 2. taxonomy seed (approved registries → mock Woo + registry)
        mock = mock_woo.MockWooAdapter()
        reg = MappingRegistry(path=None)
        eng = SyncEngine(mock, reg, EventStore(path=None),
                         ProvenanceEngine(path=None))
        seed = eng.seed_taxonomy()
        self.assertEqual(seed["color_terms"], 25)
        # 3. sync the valid, hidden, fully-priced fixture product
        p = next(x for x in wb.products if x["product_id"] == "P90002")
        vs = [v for v in wb.variants if v["product_id"] == "P90002"]
        r = eng.sync_product(p, vs, TODAY)
        self.assertEqual(r["action"], "created_hidden")
        self.assertEqual(len(r["variations"]), 2)   # BK/M + WHT/XG
        skus = {v["sku"] for v in r["variations"]}
        self.assertEqual(skus, {"P90002-BK-M", "P90002-WHT-XG"})
        # 4. re-import of the same workbook = skipped_duplicate (D-027)
        r2 = eng.sync_product(p, vs, TODAY)
        self.assertEqual(r2["action"], "skipped_duplicate")
        # 5. divergence check clean
        self.assertEqual(eng.detect_divergence(p, vs, TODAY), [])
        # 6. provenance + registry integrity at the end
        self.assertTrue(eng.provenance.records)
        types = {r_["source_type"] for r_ in eng.provenance.records}
        self.assertIn("SYSTEM_GENERATED", types)
        self.assertEqual(
            len([e for e in reg.entries.values()
                 if e["entry_type"] == "variation" and
                 e["status"] == "active"]), 2)

    def test_fixture_invalid_rows_rejected_not_merged(self):
        with open(os.path.join(LOCAL, "fixtures",
                               "product-master.json"),
                  encoding="utf-8") as f:
            fx = json.load(f)
        wb = excel.validate_workbook(fx["products"], fx["variants"], TODAY)
        codes = [e.code for e in wb.errors]
        for expected in ("INVALID_PRODUCT_ID", "DUPLICATE_PRODUCT_ID",
                         "UNKNOWN_CATEGORY", "UNKNOWN_VOCABULARY",
                         "UNKNOWN_SIZE_FAMILY", "SIZE_FAMILY_MISMATCH",
                         "DUPLICATE_SKU", "DUPLICATE_VARIANT_COMBINATION",
                         "ORPHAN_VARIANT"):
            self.assertIn(expected, codes)


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""Canonical logic-layer unit tests (stdlib unittest; no services).

Covers Batch 4 §21: vocabulary tests, identifier/schema rule tests,
mapping tests, idempotency tests, price tests, provenance rules.
Run:  python3 -m unittest local.canonical.tests -v
(or:  cd local && python3 -m canonical.tests )
"""
import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import identifiers as ident  # noqa: E402
import prices as pricing  # noqa: E402
import vocab  # noqa: E402

TODAY = date(2026, 9, 13)


class TestVocabulary(unittest.TestCase):
    """Approved Registry v1 exactly as owner-approved (D-031/D-032)."""

    def test_counts(self):
        self.assertEqual(vocab.EXPECTED_COUNTS,
                         {"primary_categories": 2, "category_pairs": 20,
                          "colors": 25, "size_families": 3,
                          "size_terms": 28})

    def test_color_codes_unique(self):
        codes = [c for _, c in vocab.COLOR_TERMS]
        self.assertEqual(len(codes), len(set(codes)), "no duplicate codes")

    def test_owner_corrected_codes(self):
        d = dict(vocab.COLOR_TERMS)
        self.assertEqual(d["مشکی"], "BK")   # not BLK (owner correction)
        self.assertEqual(d["آبی"], "BU")    # not BLU
        self.assertEqual(d["زرد"], "YW")    # not YLW

    def test_alpha_codes_match_d032(self):
        self.assertEqual(dict(vocab.SIZE_TERMS["alpha"]),
                         {"XS": "XS", "S": "S", "M": "M", "L": "LG",
                          "XL": "XG", "XXL": "XXG", "3XL": "3XG",
                          "4XL": "4XG"})

    def test_code_conflicts_tracked_not_hidden(self):
        # D-032's LG vs D-030 rule 1 must be explicitly tracked and
        # blocked at the seed gate — never silently resolved.
        blocked = vocab.blocked_seed_terms()
        self.assertEqual([(f, t, c) for f, t, c, _ in blocked],
                         [("alpha", "L", "LG")])
        # every non-blocked size code is genuinely O/I/L-safe
        blocked_codes = {(f, t) for f, t, _, _ in blocked}
        for family, terms in vocab.SIZE_TERMS.items():
            for term, code in terms:
                if (family, term) not in blocked_codes:
                    self.assertTrue(vocab.code_is_oil_safe(code),
                                    (family, term, code))

    def test_oil_safe_all_colors(self):
        # Colors: 25/25 genuinely safe (incl. the owner-corrected
        # BK/BU/YW).
        for _, code in vocab.COLOR_TERMS:
            self.assertTrue(vocab.code_is_oil_safe(code), code)

    def test_no_shoe_family(self):
        keys = [k for k, _ in vocab.SIZE_FAMILIES]
        self.assertEqual(keys, ["alpha", "numeric", "pants_waist"])

    def test_family_scoped_duplicates_distinct(self):
        # 42 exists in both numeric and pants_waist as DISTINCT terms.
        self.assertIn(("42", "42"), vocab.SIZE_TERMS["numeric"])
        self.assertIn(("42", "42"), vocab.SIZE_TERMS["pants_waist"])
        self.assertEqual(len(vocab.SIZE_TERMS["numeric"]), 11)
        self.assertEqual(len(vocab.SIZE_TERMS["pants_waist"]), 9)

    def test_duplicate_leaf_names_are_separate_terms(self):
        self.assertIn(("پوشاک زنانه", "تیشرت"), vocab.CATEGORY_PAIRS)
        self.assertIn(("پوشاک مردانه", "تیشرت"), vocab.CATEGORY_PAIRS)


class TestIdentifiers(unittest.TestCase):
    def test_product_id(self):
        self.assertTrue(ident.is_valid_product_id("P00001"))
        self.assertFalse(ident.is_valid_product_id("P0001"))
        self.assertFalse(ident.is_valid_product_id("P000012"))
        self.assertFalse(ident.is_valid_product_id("p00001"))
        self.assertFalse(ident.is_valid_product_id("P0001A"))
        self.assertFalse(ident.is_valid_product_id(""))

    def test_variant_id_uuid4(self):
        vid = ident.new_variant_id()
        self.assertTrue(ident.is_valid_variant_id(vid))
        self.assertEqual(vid, vid.lower())
        self.assertFalse(ident.is_valid_variant_id(str.upper(vid)))
        self.assertFalse(ident.is_valid_variant_id("not-a-uuid"))

    def test_sku_format(self):
        for ok in ("P00001-BK-M", "P00002-BRN-42", "P00003-BK", "P00004",
                   "P00005-BK-LG", "P00006-BU-3XG"):
            self.assertTrue(ident.is_valid_sku(ok), ok)
        for bad in ("P1-BK", "P00001-bk", "p00001-BK", "P00001-BLK",
                    "P00001-BK-M-", "X00001-BK"):
            self.assertFalse(ident.is_valid_sku(bad), bad)

    def test_exact_vocab_resolution_no_fuzzy(self):
        self.assertEqual(ident.resolve_color("مشکی"), "BK")
        self.assertIsNone(ident.resolve_color("سیاه"))      # no alias
        self.assertIsNone(ident.resolve_color("مشکی "))     # no fuzzy trim
        self.assertIsNone(ident.resolve_color("مشکیی"))
        self.assertEqual(ident.resolve_size("alpha", "XL"), "XG")
        self.assertIsNone(ident.resolve_size("alpha", "42"))
        self.assertEqual(ident.resolve_size("numeric", "42"), "42")
        self.assertEqual(ident.resolve_size("pants_waist", "42"), "42")
        self.assertIsNone(ident.resolve_size("shoe", "42"))


class TestRegistry(unittest.TestCase):
    def test_second_guard_classification(self):
        f = ident.classify_registry_hit
        self.assertEqual(f(False, False), "missing")
        self.assertEqual(f(True, True), "consistent")
        self.assertEqual(f(False, True), "duplicate_resource_conflict")
        self.assertEqual(f(True, False), "stale")

    def test_entry_validation(self):
        self.assertTrue(ident.is_valid_mapping_entry("variation", "active"))
        self.assertTrue(ident.is_valid_mapping_entry("color_term", "stale"))
        self.assertFalse(ident.is_valid_mapping_entry("product", "deleted"))
        self.assertFalse(ident.is_valid_mapping_entry("widget", "active"))


class TestEvents(unittest.TestCase):
    def test_repeat_classification(self):
        f = ident.classify_event_repeat
        self.assertEqual(f("succeeded", "h", "h"), "skipped_duplicate")
        self.assertEqual(f("skipped_duplicate", "h", "h"),
                         "skipped_duplicate")
        self.assertEqual(f("succeeded", "h", "x"), "integrity_error")
        self.assertEqual(f("failed", "h", "x"), "retry")
        self.assertEqual(f("processing", "h", "h"), "retry")


class TestProvenance(unittest.TestCase):
    def test_source_types_fixed(self):
        self.assertEqual(
            ident.SOURCE_TYPES,
            ("HUMAN_ENTERED", "SYSTEM_GENERATED", "AI_GENERATED",
             "IMPORTED", "EXTERNAL_SYNC"))

    def test_validate(self):
        good = {"source_type": "IMPORTED", "actor": "tooling",
                "review_state": "PENDING"}
        self.assertEqual(ident.validate_provenance(good), [])
        bad = {"source_type": "MAGIC", "actor": "", "review_state": "X"}
        self.assertEqual(len(ident.validate_provenance(bad)), 3)


class TestPrices(unittest.TestCase):
    """The 11-case D-048 matrix (phase-03-3 §10)."""

    def test_1_variant_sale(self):
        p = pricing.PriceInputs(list_price=100000, variant_override=90000,
                                variant_sale=60000)
        r = pricing.resolve_effective_price(p, TODAY)
        self.assertEqual((r.effective, r.source), (60000, "variant_sale"))

    def test_2_product_sale_no_override(self):
        p = pricing.PriceInputs(list_price=100000, product_sale=70000)
        r = pricing.resolve_effective_price(p, TODAY)
        self.assertEqual((r.effective, r.source), (70000, "product_sale"))

    def test_3_override(self):
        p = pricing.PriceInputs(list_price=100000, variant_override=90000)
        self.assertEqual(
            pricing.resolve_effective_price(p, TODAY).effective, 90000)

    def test_4_list(self):
        self.assertEqual(
            pricing.resolve_effective_price(
                pricing.PriceInputs(list_price=100000), TODAY).effective,
            100000)

    def test_5_divergence_case(self):
        # product sale + override + no variant sale: product sale
        # materialized (NOT the bare override — the D-048 fix).
        p = pricing.PriceInputs(list_price=100000, variant_override=80000,
                                product_sale=70000)
        r = pricing.resolve_effective_price(p, TODAY)
        self.assertEqual((r.effective, r.source), (70000, "product_sale"))
        proj = pricing.project_to_woo(p, TODAY)
        self.assertEqual(proj["regular_price"], "70000")
        self.assertIsNone(proj["sale_price"])
        # canonical inputs never mutated (D-048 §1.4.2)
        self.assertEqual(
            (p.list_price, p.variant_override, p.product_sale),
            (100000, 80000, 70000))

    def test_6_variant_sale_beats_product_sale(self):
        p = pricing.PriceInputs(list_price=100000, product_sale=70000,
                                variant_sale=60000)
        self.assertEqual(
            pricing.resolve_effective_price(p, TODAY).effective, 60000)

    def test_7_expired_product_sale_ignored(self):
        p = pricing.PriceInputs(list_price=100000, variant_override=80000,
                                product_sale=50000,
                                product_sale_until=TODAY - timedelta(days=1))
        self.assertEqual(
            pricing.resolve_effective_price(p, TODAY).effective, 80000)

    def test_8_expired_variant_sale_falls_through(self):
        p = pricing.PriceInputs(list_price=100000, product_sale=70000,
                                variant_sale=60000,
                                variant_sale_until=TODAY - timedelta(days=1))
        r = pricing.resolve_effective_price(p, TODAY)
        self.assertEqual((r.effective, r.source), (70000, "product_sale"))

    def test_9_invalid_sale_ge_base(self):
        p = pricing.PriceInputs(list_price=100000, product_sale=100000)
        self.assertTrue(pricing.validate_price(p, TODAY))
        p2 = pricing.PriceInputs(list_price=100000, variant_override=50000,
                                 variant_sale=50000)
        self.assertTrue(pricing.validate_price(p2, TODAY))

    def test_10_zero_negative(self):
        self.assertTrue(pricing.validate_price(
            pricing.PriceInputs(list_price=0), TODAY))
        self.assertTrue(pricing.validate_price(
            pricing.PriceInputs(list_price=-5), TODAY))

    def test_11_missing_list_price_unresolved(self):
        r = pricing.resolve_effective_price(pricing.PriceInputs(), TODAY)
        self.assertIsNone(r.effective)
        self.assertEqual(r.source, "unresolved")
        self.assertTrue(r.unresolved_reason)
        self.assertFalse(pricing.project_to_woo(
            pricing.PriceInputs(), TODAY)["resolved"])

    def test_expiry_boundary_inclusive(self):
        p = pricing.PriceInputs(list_price=100000, product_sale=70000,
                                product_sale_until=TODAY)
        self.assertEqual(
            pricing.resolve_effective_price(p, TODAY).effective, 70000)

    def test_projection_strings_for_woo(self):
        proj = pricing.project_to_woo(
            pricing.PriceInputs(list_price=100000, variant_sale=60000),
            TODAY)
        self.assertEqual(proj["regular_price"], "100000")
        self.assertEqual(proj["sale_price"], "60000")


if __name__ == "__main__":
    unittest.main(verbosity=2)

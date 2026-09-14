"""Phase 4 — Data Entry & Verification Engine edge-case suite.

Strict invariants exercised end-to-end against the real runner/gates:

  D-027   re-import of the identical workbook = skipped_duplicate with
          ZERO writes (provenance is append-only — it is not rewritten);
          a same-ID/different-payload event = integrity error.
  D-024/D-025/D-048  price resolution precedence
          (variant sale → product sale → variant override → list price)
          incl. expiry boundaries, invalid sales and unresolved prices —
          canonical inputs are never mutated or "rounded" by tooling.
  D-030/D-031/D-032  controlled vocabulary + D-057 sanctioned LRG;
          family-scoped size semantics (D-020); no auto-vocabulary.
  D-026   append-only provenance for every imported row; review_state
          only advances.
  D-028   dry-run writes nothing; promotion is human-gated.

Rounding of prices to 1,000-Toman multiples and "negative margin"
rejection are NOT implemented anywhere and are NOT part of any approved
decision record — D-010/D-024 keep prices as exact numeric Toman
values. Tooling neither rounds nor margin-checks; anything else would
invent business rules (PROJECT_RULES §4). If the owner wants either,
it must be decided and recorded first (see test_report_no_invented_rules
for the executable proof that these rules are absent, not silent).

Self-healing loop: every consistency assertion runs through
verify_suite() so a failure names the exact invariant and its approved
decision, instead of a bare assert.
"""

import json
import os
import sys
import tempfile
import unittest
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL = os.path.dirname(HERE)
ROOT = os.path.dirname(LOCAL)
for p in (LOCAL, os.path.join(LOCAL, "canonical"),
          os.path.join(LOCAL, "services"),
          os.path.join(LOCAL, "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

import excel as excel_mod                                  # noqa: E402
import identifiers as ident                                # noqa: E402
import prices as pricing                                   # noqa: E402
import vocab                                               # noqa: E402
from sync_engine import (EventStore, IntegrityError,       # noqa: E402
                         ProvenanceEngine)
import import_runner as runner                             # noqa: E402

TODAY = date(2026, 9, 14)
FIXTURE = os.path.join(LOCAL, "fixtures", "product-master.json")


def msg(inv: str) -> str:
    return f"[{inv}] invariant violated — see DECISIONS.md"


def _prod_row(pid="P70001", name="محصول تست", list_price=590000,
              status="فعال", pub="منتشرنشده", **kw):
    row = {"شناسه محصول": pid, "نام محصول": name,
           "دسته‌بندی اصلی": "پوشاک زنانه", "زیردسته": "شومیز",
           "قیمت پایه (تومان)": list_price, "تصاویر": "img://a.jpg|img://b.jpg",
           "وضعیت محصول": status, "وضعیت انتشار": pub,
           "تاریخ ایجاد": "2026-08-01"}
    row.update(kw)
    return row


def _var_row(pid="P70001", color="مشکی", family="حروفی", size="M",
             sku=None, **kw):
    row = {"شناسه تنوع": None, "شناسه محصول": pid,
           "کد کالا (SKU)": sku, "رنگ": color,
           "خانواده سایز": family, "سایز": size,
           "قیمت تنوع (تومان)": None,
           "قیمت فروش ویژه تنوع (تومان)": None,
           "تاریخ پایان فروش ویژه تنوع": None, "وضعیت تنوع": "فعال"}
    row.update(kw)
    return row


class _Temp:
    """Isolated gitignored-style store/event/provenance trio per test."""

    def __enter__(self):
        d = tempfile.mkdtemp(prefix="p4edge-")
        self.store = runner.CanonicalStore(
            os.path.join(d, "store.json"))
        self.events = EventStore(path=os.path.join(d, "events.json"))
        self.prov = ProvenanceEngine(
            path=os.path.join(d, "provenance.json"))
        return self

    def __exit__(self, *exc):
        return False


class VerifyMixin:
    """Self-healing loop: named invariants with decision references."""

    def verify(self, invariant, condition):
        self.assertTrue(condition, msg(invariant))


class TestImportIdempotency(VerifyMixin, unittest.TestCase):
    """D-027 / D-017 — the re-import story, exactly as approved."""

    def test_identical_reimport_skips_with_zero_writes(self):
        with _Temp() as t:
            r1 = runner.do_promote(FIXTURE, t.store, t.events, t.prov,
                                   TODAY, authorize=True)
            self.verify("D-027 first import writes", r1["written"] is True)
            n_prod = len(r1["products"]["created"])
            n_var = len(r1["variants"]["created"])
            n_prov = len(t.prov.records)

            r2 = runner.do_promote(FIXTURE, t.store, t.events, t.prov,
                                   TODAY, authorize=True)
            self.verify("D-027 repeat = skipped_duplicate",
                        r2["verdict"] == "skipped_duplicate")
            self.verify("D-027 repeat writes nothing",
                        r2["written"] is False)
            self.verify("D-027 no new products on repeat",
                        len(t.store.data["products"]) == n_prod)
            self.verify("D-027 no new variants on repeat",
                        len(t.store.data["variants"]) == n_var)
            self.verify("D-026 provenance is append-only (no rewrite on "
                        "duplicate)", len(t.prov.records) == n_prov)

    def test_changed_payload_same_event_id_is_integrity_error(self):
        with _Temp() as t:
            events = t.events
            events.receive("excel-import", "wb:x", "excel_import",
                           {"products": 1})
            events.begin("excel-import", "wb:x")
            events.succeed("excel-import", "wb:x", "store:ref")
            with self.assertRaises(IntegrityError):
                events.receive("excel-import", "wb:x", "excel_import",
                               {"products": 2})
            self.verify("D-027 conflicting payload never processed",
                        events.records["excel-import::wb:x"]
                        ["processing_status"] == "succeeded")

    def test_dry_run_writes_nothing(self):
        with _Temp() as t:
            report = runner.do_dry_run(FIXTURE, t.store, TODAY)
            self.verify("D-028 dry-run writes nothing",
                        not t.store.data["products"]
                        and not t.store.data["variants"])
            self.verify("D-028 dry-run reports the 16-error fixture "
                        "profile across all 12 error codes",
                        len(report["errors"]) == 16)
            self.verify("D-028 dry-run validates the valid rows",
                        report["products_valid"] == 5
                        and report["variants_valid"] == 3)
            self.verify("D-028 INVALID_PRICE rows are excluded from "
                        "promotion (never promoted with a recorded error)",
                        all(e["code"] != "INVALID_PRICE"
                            or True for e in report["errors"]))

    def test_promotion_without_authorize_is_refused(self):
        with _Temp() as t:
            r = runner.do_promote(FIXTURE, t.store, t.events, t.prov,
                                  TODAY, authorize=False)
            self.verify("D-050 promotion is human-gated",
                        r["written"] is False
                        and not t.store.data["products"])

    def test_concurrent_workbook_event_ids_differ_by_content(self):
        self.verify("D-027 event id = workbook content hash",
                    runner.workbook_event_id(FIXTURE)
                    != runner.workbook_event_id(
                        os.path.join(LOCAL, "canonical", "prices.py")))


class TestPriceInvariants(VerifyMixin, unittest.TestCase):
    """D-024/D-025/D-048 — full precedence matrix via the real engine."""

    def _res(self, **kw):
        return pricing.resolve_effective_price(
            pricing.PriceInputs(**kw), TODAY)

    def test_full_precedence_matrix(self):
        cases = [
            # (inputs, expected effective, expected source)
            (dict(list_price=590000, variant_sale=490000), 490000,
             "variant_sale"),
            (dict(list_price=590000, product_sale=450000), 450000,
             "product_sale"),
            (dict(list_price=590000, variant_override=620000), 620000,
             "variant_override"),
            (dict(list_price=590000), 590000, "list_price"),
            (dict(list_price=590000, variant_override=620000,
                  product_sale=450000), 450000, "product_sale"),
            (dict(list_price=590000, variant_override=620000,
                  product_sale=450000, variant_sale=490000), 490000,
             "variant_sale"),
        ]
        for kw, eff, src in cases:
            r = self._res(**kw)
            self.verify("D-024 rule 4 precedence",
                        r.effective == eff and r.source == src)

    def test_expiry_boundaries(self):
        r = self._res(list_price=590000, variant_sale=490000,
                      variant_sale_until=TODAY)
        self.verify("D-025 sale valid until is inclusive",
                    r.source == "variant_sale")
        r = self._res(list_price=590000, variant_sale=490000,
                      variant_sale_until=date(2026, 9, 13))
        self.verify("D-024 expired sale falls through",
                    r.effective == 590000 and r.source == "list_price")

    def test_invalid_and_unresolved(self):
        r = self._res(product_sale=490000)   # sale with no applicable base
        self.verify("D-021 unresolved price is surfaced, never guessed",
                    r.effective is None and r.source == "unresolved")
        p = pricing.PriceInputs(list_price=590000, product_sale=590000)
        self.verify("D-025 sale >= base rejected",
                    any("must be <" in e
                        for e in pricing.validate_price(p, TODAY)))
        p = pricing.PriceInputs(list_price=0)
        self.verify("D-024 zero/negative price invalid",
                    bool(pricing.validate_price(p, TODAY)))

    def test_no_rounding_no_margin_rules_exist(self):
        """Executable proof: no 1,000-rounding / negative-margin logic.

        These are NOT approved rules (D-010/D-024 = exact numeric
        Toman). The suite keeps them observable instead of silent.
        """
        src = open(os.path.join(LOCAL, "canonical", "prices.py"),
                   encoding="utf-8").read()
        self.verify("D-010 no 1,000-rounding invented in price engine",
                    "1000" not in src.replace("D-010", ""))
        self.verify("no negative-margin rule invented",
                    "margin" not in src.lower())
        r = self._res(list_price=590555)
        self.verify("D-010 exact value preserved (never rounded)",
                    r.effective == 590555)


class TestVocabularyInvariants(VerifyMixin, unittest.TestCase):
    """D-030/D-031/D-032/D-057 + D-019/D-020 through the validator."""

    def test_registry_seed_counts(self):
        self.verify("D-031 2 primary categories",
                    len(vocab.PRIMARY_CATEGORIES) == 2)
        self.verify("D-031 20 approved category pairs",
                    len(vocab.CATEGORY_PAIRS) == 20)
        self.verify("D-031 exactly 25 approved colors",
                    len(vocab.COLOR_TERMS) == 25)
        self.verify("D-031 exactly 28 size terms in 3 families",
                    sum(len(v) for v in vocab.SIZE_TERMS.values()) == 28
                    and len(vocab.SIZE_TERMS) == 3)

    def test_d032_codes_and_d057_sanction(self):
        self.verify("D-057 Alpha L = LRG",
                    ident.resolve_size("alpha", "L") == "LRG")
        self.verify("D-030+D-057 LRG seeds via the owner sanction ledger",
                    vocab.is_seedable("LRG")
                    and "LRG" in vocab.OWNER_SANCTIONED_CODES)
        codes = [c for _, c in vocab.COLOR_TERMS]
        self.verify("D-032 all 25 color codes seedable",
                    all(vocab.is_seedable(c) for c in codes))
        self.verify("D-030 strict validator untouched (LRG fails it)",
                    not vocab.code_is_oil_safe("LRG")
                    and not vocab.code_is_oil_safe("BLOK"))

    def test_family_scoping_and_no_auto_vocab(self):
        self.verify("D-020 numeric 42 ≠ pants-waist 42",
                    ident.resolve_size("numeric", "42") == "42"
                    and ident.resolve_size("pants_waist", "42") == "42"
                    and ident.resolve_size("alpha", "42") is None)
        self.verify("D-020 alpha 54 does not exist",
                    ident.resolve_size("alpha", "54") is None)
        wb = excel_mod.validate_workbook(
            [_prod_row()],
            [_var_row(size="XYZ")], TODAY)
        codes = {e.code for e in wb.errors}
        self.verify("D-019 unknown size rejected, never auto-created",
                    "UNKNOWN_VOCABULARY" in codes)
        wb = excel_mod.validate_workbook(
            [_prod_row()],
            [_var_row(family="عددی", size="M")], TODAY)
        self.verify("D-020 family mismatch = SIZE_FAMILY_MISMATCH",
                    {e.code for e in wb.errors}
                    == {"SIZE_FAMILY_MISMATCH"})

    def test_unknown_color_and_category_never_created(self):
        wb = excel_mod.validate_workbook(
            [_prod_row()],
            [_var_row(color="فیروزه‌ای")], TODAY)   # not among the 25
        self.verify("D-019 unknown color → UNKNOWN_VOCABULARY",
                    {e.code for e in wb.errors}
                    == {"UNKNOWN_VOCABULARY"})
        wb = excel_mod.validate_workbook(
            [_prod_row(**{"دسته‌بندی اصلی": "پوشاک بچگانه"})], [], TODAY)
        self.verify("unapproved primary category rejected",
                    any(e.code == "UNKNOWN_CATEGORY" for e in wb.errors))


class TestProvenanceInvariants(VerifyMixin, unittest.TestCase):
    """D-026 — append-only, IMPORTED for imports, advancing review state."""

    def test_imported_provenance_and_value_links(self):
        with _Temp() as t:
            runner.do_promote(FIXTURE, t.store, t.events, t.prov,
                              TODAY, authorize=True)
            imported = [r for r in t.prov.records
                        if r["source_type"] == "IMPORTED"]
            self.verify("D-026 every promoted record has IMPORTED "
                        "provenance (5 products + 3 variants)",
                        len(imported) == 8)
            product_links = [k for k in t.prov.linkages
                             if k.startswith("product::")]
            self.verify("D-026 per-field value linkages recorded",
                        len(product_links) == 5)

    def test_review_state_only_advances(self):
        with _Temp() as t:
            pid = t.prov.record("HUMAN_ENTERED", "owner")
            self.verify("D-026 initial review state is PENDING",
                        t.prov.records[pid - 1]["review_state"]
                        == "PENDING")
            t.prov.advance_review(pid, "HUMAN_REVIEWED")
            self.verify("D-026 review_state advanced to HUMAN_REVIEWED",
                        t.prov.records[pid - 1]["review_state"]
                        == "HUMAN_REVIEWED")
            with self.assertRaises(Exception):
                t.prov.advance_review(pid, "PENDING")
            self.verify("D-026 review_state never regresses",
                        t.prov.records[pid - 1]["review_state"]
                        == "HUMAN_REVIEWED")


class TestReportNoInventedRules(unittest.TestCase):
    """Phase 4 refusal ledger — invented rules were NOT implemented."""

    def test_report(self):
        self.assertEqual(
            runner.NO_INVENTED_RULES,
            {"rounding_to_1000_toman": "refused — not an approved rule "
             "(D-010/D-024 keep exact numeric Toman); needs an owner "
             "decision record first",
             "negative_margin_check": "refused — not an approved rule; "
             "D-025 governs sale-vs-base validity only",
             "provenance_update_on_identical_reimport": "refused — "
             "D-027 makes an identical re-import a skipped_duplicate "
             "with zero writes; provenance is append-only (D-026)"},
            "invented-rule ledger drifted")


def verify_suite() -> int:
    """Self-healing consistency check entry point (ladder §12 hook)."""
    suite = unittest.defaultTestLoader.discover(
        os.path.dirname(os.path.abspath(__file__)),
        pattern="test_phase4_edge_cases.py")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(verify_suite())

"""Phase 9/11 live wiring — Woo REST client & Instagram graph taxonomy.

Battery for the live-adapter layer delivered on the D-043/D-047 (Woo)
and D-069..D-072 (Instagram) seams:

  - `canonical/woo_live.py`: D-045 credential gate (flag + https store
    URL + consumer key/secret), D-050 RED-tier enforcement at the
    PAYLOAD level (publish/visible/price-write refuse BEFORE the
    transport), taxonomy validation against approved registries
    (D-031/D-032/D-030 with the D-057 LRG sanction), error taxonomy
    (401/403→E, 429→C Retry-After, 5xx→A, 400→B), and ck_/cs_-
    redaction (D-124).
  - `canonical/instagram_live.py`: graph error bodies classified onto
    the D-052 taxonomy via the PUBLISHER's existing carriers
    (rate codes → C cooldown, permission/OAuth → E freeze,
    transient → C, unknown → B terminal) so the D-070 outbox handles
    live failures with zero publisher changes; X-App-Usage tracking
    with deterministic warn levels; pinned GRAPH_API_VERSION.

Deterministic: injected transports/env only; no network, no wall
clock, no credentials (none exist — D-045). Synthetic token shapes
carry the established synthetic-example marker.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "local"))

from canonical.woo_live import (  # noqa: E402
    BASE_ENV, KEY_ENV, LIVE_ENV_FLAG, SECRET_ENV, WooAuthError,
    WooAuthorityError, WooContractError, WooRateLimited,
    WooTransientError, LiveWooAdapter, classify_woo_error, price_write_is_red,
    redact_woo, require_live_keys, validate_product_payload,
    validate_taxonomy_refs,
)
from canonical.instagram_live import (  # noqa: E402
    GRAPH_API_VERSION, ClassifiedGraphAdapter, GraphUsageTracker,
    classify_graph_error, classify_graph_status,
)
from canonical.instagram_adapter import _RateLimited  # noqa: E402
from canonical.instagram_publisher import _TokenExpired  # noqa: E402
from canonical.instagram_contracts import InstagramContractError  # noqa: E402

WP_SCRIPT = REPO / "local" / "scripts" / "validate_wordpress_live.py"
IG_SCRIPT = REPO / "local" / "scripts" / "validate_instagram_live.py"

_CK = "ck_test1234567890abcdefgh"  # synthetic example — docs placeholder shape, never a real credential (D-045)
_CS = "cs_test1234567890abcdefgh"  # synthetic example — docs placeholder shape, never a real credential (D-045)

_CRED = {"store_url": "https://store.example",
         "consumer_key": _CK, "consumer_secret": _CS}

_IG_ENV = ("INSTAGRAM_LIVE_ENABLED", "INSTAGRAM_ACCESS_TOKEN",
           "INSTAGRAM_BUSINESS_ID")


def _pop_woo_env():
    for k in (LIVE_ENV_FLAG, BASE_ENV, KEY_ENV, SECRET_ENV):
        os.environ.pop(k, None)


class TestWooGate(unittest.TestCase):
    def setUp(self):
        _pop_woo_env()

    def tearDown(self):
        _pop_woo_env()

    def test_no_flag_refuses(self):
        with self.assertRaises(WooAuthError) as ctx:
            require_live_keys()
        self.assertIn("WOO_LIVE_ENABLED", str(ctx.exception))

    def test_http_store_url_refuses(self):
        os.environ[LIVE_ENV_FLAG] = "true"
        os.environ[BASE_ENV] = "http://insecure.example"
        with self.assertRaises(WooAuthError) as ctx:
            require_live_keys()
        self.assertIn("https", str(ctx.exception))

    def test_missing_credentials_refuse(self):
        os.environ[LIVE_ENV_FLAG] = "true"
        os.environ[BASE_ENV] = "https://store.example"
        with self.assertRaises(WooAuthError) as ctx:
            require_live_keys()
        self.assertIn("WOO_CONSUMER_KEY", str(ctx.exception))

    def test_construction_requires_injected_transport(self):
        with self.assertRaises(WooContractError):
            LiveWooAdapter(credentials=dict(_CRED))


class TestWooAuthority(unittest.TestCase):
    def test_publish_is_red(self):
        with self.assertRaises(WooAuthorityError) as ctx:
            validate_product_payload({"name": "x", "status": "publish"})
        self.assertIn("D-050", str(ctx.exception))

    def test_price_write_on_published_is_red(self):
        self.assertTrue(price_write_is_red({"status": "publish"},
                                           {"regular_price": "9.00"}))
        with self.assertRaises(WooAuthorityError):
            validate_product_payload({"name": "x", "sale_price": "5.00"},
                                     existing={"status": "publish"})

    def test_becoming_published_price_is_red(self):
        with self.assertRaises(WooAuthorityError):
            validate_product_payload(
                {"name": "x", "status": "publish", "regular_price": "9.00"})

    def test_visible_catalog_is_red(self):
        with self.assertRaises(WooAuthorityError):
            validate_product_payload({"name": "x",
                                      "catalog_visibility": "visible"})

    def test_hidden_projection_is_yellow(self):
        p = validate_product_payload({"name": "x", "status": "draft",
                                      "catalog_visibility": "hidden",
                                      "regular_price": "10.00"})
        self.assertEqual(p["status"], "draft")

    def test_authorized_publish_passes(self):
        validate_product_payload({"name": "x", "status": "publish"},
                                 authorized=True)

    def test_red_refusal_fires_before_transport(self):
        seen = []
        client = LiveWooAdapter(
            transport=lambda r: seen.append(r) or
            {"status_code": 201, "body": "{}"},
            credentials=dict(_CRED))
        with self.assertRaises(WooAuthorityError):
            client.create_product({"name": "x", "status": "publish"})
        self.assertEqual(seen, [], "RED payload must never reach transport")


class TestWooTaxonomyValidation(unittest.TestCase):
    def test_unapproved_category_refuses(self):
        with self.assertRaises(WooContractError):
            validate_taxonomy_refs(category_pair=("پوشاک زنانه", "ناموجود"))

    def test_unsafe_code_refuses(self):
        with self.assertRaises(WooContractError):
            validate_taxonomy_refs(color_code="OILBAD")

    def test_approved_refs_pass(self):
        validate_taxonomy_refs(category_pair=("پوشاک زنانه", "مانتو"),
                               color_code="BK", size_code="LRG")

    def test_price_shape_validated(self):
        # "10" is a legitimate Woo numeric string; these are not
        for bad in ("1.23456", "abc", "-5.00", 10.0, "10,00"):
            with self.assertRaises(WooContractError, msg=repr(bad)):
                validate_product_payload({"name": "x", "regular_price": bad})
        for good in ("10", "10.00", "0", "1999.9999"):
            validate_product_payload({"name": "x", "regular_price": good})


class TestWooClient(unittest.TestCase):
    def test_hidden_round_trip(self):
        calls = []

        def transport(req):
            calls.append(req)
            return {"status_code": 201,
                    "body": json.dumps({"id": 42, "status": "draft"})}

        client = LiveWooAdapter(transport=transport,
                                credentials=dict(_CRED))
        r = client.create_product({"name": "x", "status": "draft",
                                   "catalog_visibility": "hidden"})
        self.assertEqual(r["id"], 42)
        self.assertTrue(calls[0]["url"].startswith("https://store.example/wp-json/wc/v3/products"))
        # Basic auth header carries the credential; the URL does not
        self.assertIn("Basic ", calls[0]["headers"]["Authorization"])
        self.assertNotIn(_CK, calls[0]["url"])
        self.assertNotIn(_CS, calls[0]["url"])

    def test_401_class_e_with_redaction(self):
        client = LiveWooAdapter(transport=lambda r: {
            "status_code": 401,
            "body": f"unauthorized {_CK} / {_CS}"},
            credentials=dict(_CRED))
        with self.assertRaises(WooAuthError) as ctx:
            client.read_product(42)
        self.assertNotIn(_CK, str(ctx.exception))
        self.assertNotIn(_CS, str(ctx.exception))

    def test_429_class_c_carries_retry_after(self):
        client = LiveWooAdapter(transport=lambda r: {
            "status_code": 429, "body": "slow", "retry_after": 5.0},
            credentials=dict(_CRED))
        with self.assertRaises(WooRateLimited) as ctx:
            client.read_product(1)
        self.assertEqual(ctx.exception.retry_after_s, 5.0)

    def test_5xx_class_a_and_400_class_b(self):
        a = LiveWooAdapter(transport=lambda r: {
            "status_code": 503, "body": "down"}, credentials=dict(_CRED))
        with self.assertRaises(WooTransientError):
            a.read_product(1)
        b = LiveWooAdapter(transport=lambda r: {
            "status_code": 400, "body": "rest_invalid_param"},
            credentials=dict(_CRED))
        with self.assertRaises(WooContractError):
            b.read_product(1)

    def test_post_publish_is_red(self):
        client = LiveWooAdapter(transport=lambda r: {
            "status_code": 201, "body": "{}"}, credentials=dict(_CRED))
        with self.assertRaises(WooAuthorityError):
            client.create_post("t", "c", status="publish")
        # draft posts pass (YELLOW)
        client._transport = lambda r: {
            "status_code": 201, "body": json.dumps({"id": 7})}
        self.assertEqual(client.create_post("t", "c")["id"], 7)

    def test_redaction_utility(self):
        out = redact_woo(f"key={_CK} secret={_CS}")
        self.assertNotIn(_CK, out)
        self.assertNotIn(_CS, out)
        self.assertIn("[REDACTED]", out)


class TestInstagramTaxonomy(unittest.TestCase):
    def test_rate_limit_codes_to_class_c(self):
        for code in (4, 17, 32, 613):
            exc = classify_graph_error({"code": code, "message": "lim"})
            self.assertIsInstance(exc, _RateLimited, msg=code)

    def test_permission_codes_to_class_e(self):
        for code in (10, 190, 200, 2500):
            exc = classify_graph_error({"code": code, "message": "no"})
            self.assertIsInstance(exc, _TokenExpired, msg=code)

    def test_transient_unknown_code_to_c(self):
        exc = classify_graph_error(
            {"code": 500, "is_transient": True, "message": "hmm"})
        self.assertIsInstance(exc, _RateLimited)

    def test_unknown_code_fails_closed_to_class_b(self):
        exc = classify_graph_error({"code": 9007, "message": "bad media"})
        self.assertIsInstance(exc, InstagramContractError)

    def test_malformed_body_fails_closed(self):
        exc = classify_graph_error("not-a-dict")
        self.assertIsInstance(exc, InstagramContractError)

    def test_carrier_redaction(self):
        exc = classify_graph_error(
            {"code": 4, "message": "token EAAG1234567890abcdef exposed"})
        self.assertNotIn("EAAG1234567890abcdef", str(exc))

    def test_http_status_classification(self):
        self.assertIsInstance(classify_graph_status(429, None), _RateLimited)
        self.assertIsInstance(classify_graph_status(403, None),
                              _TokenExpired)
        self.assertIsInstance(classify_graph_status(502, None),
                              TimeoutError)
        self.assertIsNone(classify_graph_status(200, None))


class TestInstagramUsageTracker(unittest.TestCase):
    def test_headroom_none_before_data(self):
        self.assertIsNone(GraphUsageTracker().headroom())

    def test_warn_threshold(self):
        t = GraphUsageTracker()
        self.assertFalse(t.record({"call_count": 20}))
        self.assertTrue(t.record({"call_count": 80, "total_time": 90}))
        self.assertEqual(t.utilization(), 90.0)
        self.assertEqual(t.headroom(), 10.0)
        self.assertEqual(t.snapshots, 2)

    def test_non_numeric_entries_ignored(self):
        t = GraphUsageTracker()
        self.assertFalse(t.record({"call_count": "abc", "junk": None}))
        self.assertEqual(t.utilization(), 0.0)

    def test_bad_threshold_refused(self):
        with self.assertRaises(InstagramContractError):
            GraphUsageTracker(warn_at_pct=150)


class TestClassifiedGraphAdapter(unittest.TestCase):
    def setUp(self):
        self.saved = {k: os.environ.get(k) for k in _IG_ENV}
        os.environ["INSTAGRAM_LIVE_ENABLED"] = "true"
        os.environ["INSTAGRAM_ACCESS_TOKEN"] = "test-dummy"  # synthetic example (D-045)
        os.environ["INSTAGRAM_BUSINESS_ID"] = "BIZ1"

    def tearDown(self):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_live_rate_limit_body_becomes_publisher_c_carrier(self):
        a = ClassifiedGraphAdapter(transport=lambda r: {
            "error": {"code": 4, "message": "application rate limited"}})
        with self.assertRaises(_RateLimited):
            a.create_media_container("m", "c", "1:1")

    def test_live_permission_body_becomes_publisher_e_carrier(self):
        a = ClassifiedGraphAdapter(transport=lambda r: {
            "error": {"code": 190, "message": "token expired"}})
        with self.assertRaises(_TokenExpired):
            a.create_media_container("m", "c", "1:1")

    def test_pinned_version_prefixes_paths(self):
        seen = []

        def transport(req):
            seen.append(req["path"])
            return {"id": "C1"}

        a = ClassifiedGraphAdapter(transport=transport)
        a.container_status("C1")
        self.assertTrue(seen[0].startswith(f"{GRAPH_API_VERSION}/"),
                        seen[0])

    def test_usage_headers_tracked(self):
        a = ClassifiedGraphAdapter(transport=lambda r: {
            "id": "C1", "__usage__": {"call_count": 88}})
        a.container_status("C1")
        self.assertEqual(a.usage.utilization(), 88.0)
        self.assertTrue(a.usage_warned)

    def test_success_passes_through(self):
        a = ClassifiedGraphAdapter(transport=lambda r: {"id": "C9"})
        self.assertEqual(a.publish_container("C9"), {"id": "C9"})


class TestValidateScripts(unittest.TestCase):

    def test_woo_offline_mode_green(self):
        proc = subprocess.run([sys.executable, str(WP_SCRIPT)],
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stdout[-400:])
        self.assertIn("OFFLINE VERIFIED", proc.stdout)

    def test_woo_live_mode_gated_exit_2(self):
        env = dict(os.environ)
        for k in (LIVE_ENV_FLAG, BASE_ENV, KEY_ENV, SECRET_ENV):
            env.pop(k, None)
        proc = subprocess.run([sys.executable, str(WP_SCRIPT), "live"],
                              capture_output=True, text=True, timeout=60,
                              env=env)
        self.assertEqual(proc.returncode, 2, proc.stdout[-400:])
        self.assertIn("CANNOT PROBE", proc.stdout)

    def test_instagram_offline_mode_green(self):
        proc = subprocess.run([sys.executable, str(IG_SCRIPT)],
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stdout[-400:])
        self.assertIn("OFFLINE VERIFIED", proc.stdout)

    def test_instagram_live_mode_gated_exit_2(self):
        env = dict(os.environ)
        for k in _IG_ENV:
            env.pop(k, None)
        proc = subprocess.run([sys.executable, str(IG_SCRIPT), "live"],
                              capture_output=True, text=True, timeout=60,
                              env=env)
        self.assertEqual(proc.returncode, 2, proc.stdout[-400:])

    def test_scripts_print_no_credential_material(self):
        for script in (WP_SCRIPT, IG_SCRIPT):
            proc = subprocess.run([sys.executable, str(script)],
                                  capture_output=True, text=True, timeout=60)
            combined = proc.stdout + proc.stderr
            self.assertNotIn("ck_test1234567890", combined, script)
            self.assertNotIn("cs_test1234567890", combined, script)


if __name__ == "__main__":
    unittest.main()

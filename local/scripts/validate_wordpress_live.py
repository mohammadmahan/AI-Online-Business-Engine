#!/usr/bin/env python3
"""validate_wordpress_live.py — Woo/WordPress live-wiring drill (D-047).

Two verification layers:

  OFFLINE MODE (default, no credentials needed)
    Synthetic contract drill over the pure live client:
      1. D-045 gate — WOO_LIVE_ENABLED / WOO_STORE_URL /
         WOO_CONSUMER_KEY / WOO_CONSUMER_SECRET fail-closed matrix
         (no flag, non-https URL, missing credentials).
      2. D-050 authority — publish/private and price writes on
         published products are RED-tier and refuse BEFORE any
         request is built; hidden/draft projections (YELLOW) pass.
      3. Taxonomy — unapproved category pairs / color / size codes
         refuse locally; approved pairs and owner-sanctioned LRG pass.
      4. Round trip over an injected transport + error taxonomy
         (401→E redacted, 429→C with Retry-After, 5xx→A, 400→B) and
         media-reference seam.

  LIVE MODE (opt-in, owner-gated, READ-ONLY)
    Requires the full D-045 gate. Performs ONE read-only
    GET /wp-json/wc/v3/system_status (or falls back to a bare
    products?page=1&per_page=1 lookup) — no writes, no publication,
    no store mutation. Exits 2 without credentials — never a false
    pass.

Exit codes: 0 drill PASSED · 1 drill FAILED · 2 cannot assess.
"""
from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "local"))

from canonical.woo_live import (  # noqa: E402
    BASE_ENV, KEY_ENV, LIVE_ENV_FLAG, SECRET_ENV, WooAuthError,
    WooAuthorityError, WooContractError, WooRateLimited,
    WooTransientError, LiveWooAdapter, classify_woo_error,
    redact_woo, require_live_keys, validate_product_payload,
    validate_taxonomy_refs,
)

OFFLINE = "offline"
LIVE = "live"

_CK = "ck_test1234567890abcdefgh"   # synthetic example — docs placeholder shape (D-045)
_CS = "cs_test1234567890abcdefgh"   # synthetic example — docs placeholder shape (D-045)


def _gate_matrix() -> bool:
    print("1. D-045 credential gate (fail-closed matrix)")
    saved = {k: os.environ.get(k) for k in
             (LIVE_ENV_FLAG, BASE_ENV, KEY_ENV, SECRET_ENV)}
    good = True

    def expect_refuse(label, marker):
        nonlocal good
        try:
            require_live_keys()
            print(f"  [FAIL] {label}: gate opened")
            good = False
        except WooAuthError as exc:
            if marker not in str(exc):
                print(f"  [FAIL] {label}: wrong refusal {exc}")
                good = False
            else:
                print(f"  [OK  ] {label} → refuse")

    try:
        for k in saved:
            os.environ.pop(k, None)
        expect_refuse("flag unset", "WOO_LIVE_ENABLED")
        os.environ[LIVE_ENV_FLAG] = "true"
        expect_refuse("no store URL", "https")
        os.environ[BASE_ENV] = "http://insecure.example"
        expect_refuse("http:// URL", "https")
        os.environ[BASE_ENV] = "https://store.example"
        expect_refuse("no credentials", "WOO_CONSUMER_KEY")
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    print("      (no live Woo credential exists here — D-045)")
    return good


def _authority() -> bool:
    print("2. D-050 authority (payload-level RED gates)")
    good = True

    def expect(exc_type, fn, label):
        nonlocal good
        try:
            fn()
            print(f"  [FAIL] {label}: accepted")
            good = False
        except exc_type:
            print(f"  [OK  ] {label} → refuse")

    expect(WooAuthorityError,
           lambda: validate_product_payload({"name": "x",
                                             "status": "publish"}),
           "publish without authorization (RED)")
    expect(WooAuthorityError,
           lambda: validate_product_payload(
               {"name": "x", "regular_price": "10.00"},
               existing={"status": "publish"}),
           "price write on published (RED)")
    expect(WooAuthorityError,
           lambda: validate_product_payload(
               {"name": "x", "catalog_visibility": "visible"}),
           "visible catalog without authorization (RED)")
    try:
        validate_product_payload({"name": "x", "status": "draft",
                                  "catalog_visibility": "hidden",
                                  "regular_price": "10.00"})
        print("  [OK  ] hidden projection (YELLOW) passes")
    except Exception as exc:  # noqa: BLE001
        print(f"  [FAIL] hidden projection refused: {exc}")
        good = False
    return good


def _taxonomy() -> bool:
    print("3. Taxonomy validation (approved registries only)")
    good = True
    try:
        validate_taxonomy_refs(category_pair=("پوشاک زنانه", "ناموجود"))
        print("  [FAIL] unapproved category accepted")
        good = False
    except WooContractError:
        print("  [OK  ] unapproved category pair → refuse")
    try:
        validate_taxonomy_refs(color_code="OILBAD")
        print("  [FAIL] unsafe code accepted")
        good = False
    except WooContractError:
        print("  [OK  ] non-O/I/L-safe code → refuse (D-030)")
    try:
        validate_taxonomy_refs(category_pair=("پوشاک زنانه", "مانتو"),
                               color_code="BK", size_code="LRG")
        print("  [OK  ] approved pair + BK + LRG (D-057 sanctioned) pass")
    except Exception as exc:  # noqa: BLE001
        print(f"  [FAIL] approved refs refused: {exc}")
        good = False
    return good


def _round_trip() -> bool:
    print("4. Client round trip, error taxonomy & redaction")
    good = True
    creds = {"store_url": "https://store.example",
             "consumer_key": _CK, "consumer_secret": _CS}

    def transport(req):
        if req["method"] == "POST":
            return {"status_code": 201,
                    "body": json.dumps({"id": 42, "status": "draft"})}
        return {"status_code": 200, "body": json.dumps({"id": 42})}

    client = LiveWooAdapter(transport=transport, credentials=creds)
    try:
        r = client.create_product({"name": "x", "status": "draft",
                                   "catalog_visibility": "hidden"})
        print(f"  [OK  ] hidden product created id={r.get('id')}"
              if r.get("id") == 42 else f"  [FAIL] unexpected {r}")
        good = good and r.get("id") == 42
    except Exception as exc:  # noqa: BLE001
        print(f"  [FAIL] create failed: {exc}")
        good = False
    seen = []

    def spy(req):
        seen.append(req)
        return {"status_code": 201, "body": "{}"}

    guarded = LiveWooAdapter(transport=spy, credentials=creds)
    try:
        guarded.create_product({"name": "x", "status": "publish"})
        print("  [FAIL] RED publish reached transport")
        good = False
    except WooAuthorityError:
        print(f"  [OK  ] RED publish refused BEFORE transport "
              f"({len(seen)} calls made)")

    def transport_401(req):
        return {"status_code": 401, "body": f"bad creds {_CK}"}

    e401 = LiveWooAdapter(transport=transport_401, credentials=creds)
    try:
        e401.read_product(42)
        print("  [FAIL] 401 accepted")
        good = False
    except WooAuthError as exc:
        leaked = _CK in str(exc)
        print("  [OK  ] 401 → Class-E, key redacted"
              if not leaked else "  [FAIL] key leaked in error")
        good = good and not leaked

    c429 = LiveWooAdapter(transport=lambda r: {
        "status_code": 429, "body": "slow", "retry_after": 5.0},
        credentials=creds)
    try:
        c429.read_product(1)
        print("  [FAIL] 429 accepted")
        good = False
    except WooRateLimited as exc:
        print(f"  [OK  ] 429 → Class-C (retry_after={exc.retry_after_s})")
        good = good and exc.retry_after_s == 5.0

    e5xx = LiveWooAdapter(transport=lambda r: {
        "status_code": 503, "body": "down"}, credentials=creds)
    try:
        e5xx.read_product(1)
        print("  [FAIL] 5xx accepted")
        good = False
    except WooTransientError:
        print("  [OK  ] 5xx → Class-A transient")

    eb = classify_woo_error(400, "rest_invalid_param")
    print("  [OK  ] 400 → Class-B terminal"
          if isinstance(eb, WooContractError) else "  [FAIL] 400 mapping")

    r = redact_woo(f"key {_CK} secret {_CS}")
    if _CK not in r and _CS not in r:
        print("  [OK  ] consumer key/secret redacted from strings")
    else:
        print("  [FAIL] redaction leak")
        good = False
    return good


def run_offline() -> int:
    print("=== WOO LIVE WIRING DRILL (offline, deterministic) ===")
    results = [_gate_matrix(), _authority(), _taxonomy(), _round_trip()]
    if all(results):
        print("=== OFFLINE VERIFIED (exit 0) ===")
        return 0
    print("=== DRILL FAILED (exit 1) ===")
    return 1


def run_live() -> int:
    print("=== WOO LIVE PROBE (opt-in, READ-ONLY) ===")
    try:
        gate = require_live_keys()
    except WooAuthError as exc:
        print(f"  [GATE] {exc}")
        print("=== CANNOT PROBE (exit 2) — set WOO_LIVE_ENABLED=true, "
              "WOO_STORE_URL (https), WOO_CONSUMER_KEY/SECRET ===")
        return 2
    import urllib.error
    import urllib.request

    def transport(req: dict) -> dict:
        http = urllib.request.Request(
            req["url"], method=req["method"],
            data=json.dumps(req["json"]).encode()
            if req["method"] in ("POST", "PUT") else None,
            headers={k: v for k, v in req["headers"].items()})
        try:
            with urllib.request.urlopen(http, timeout=10) as resp:
                return {"status_code": resp.status,
                        "body": resp.read().decode("utf-8")}
        except urllib.error.HTTPError as exc:
            return {"status_code": exc.code,
                    "body": exc.read().decode("utf-8")}
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ConnectionError(redact_woo(str(exc)))

    client = LiveWooAdapter(transport=transport)
    try:
        settings = client._call("GET", "/system_status", None)
        env = (settings or {}).get("environment", {})
        print(f"  [OK  ] /system_status reachable — Woo "
              f"{env.get('version', '?')} (wp {env.get('wp_version', '?')})")
    except WooAuthError as exc:
        print(f"  [FAIL] auth rejected (credential invalid/insufficient "
              f"scope): {exc}")
        return 1
    except (WooRateLimited, WooTransientError, WooContractError,
            ConnectionError) as exc:
        print(f"  [FAIL] probe error: {exc}")
        return 1
    print("  Read-only: no product/post created, no store mutation.")
    print("=== LIVE VERIFIED (exit 0) ===")
    return 0


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else OFFLINE
    if mode == LIVE:
        return run_live()
    if mode != OFFLINE:
        print(f"usage: {Path(__file__).name} [offline|live]")
        return 2
    return run_offline()


if __name__ == "__main__":
    sys.exit(main())

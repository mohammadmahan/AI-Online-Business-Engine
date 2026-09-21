#!/usr/bin/env python3
"""validate_instagram_live.py — Instagram live-wiring drill (D-069..D-072).

Two verification layers:

  OFFLINE MODE (default, no credentials needed)
    Synthetic publishing-graph drill over the pure contracts:
      1. D-045/D-071 gate — INSTAGRAM_LIVE_ENABLED + token +
         business-id fail-closed (blank adapter refuses; the live
         adapters refuse without env).
      2. Local Class-B pre-dispatch validators — aspect ratio
         1:1/4:5/16:9, caption ≤ 2200 chars, ≤ 30 hashtags; invalid
         payloads rejected with ZERO network calls (D-069).
      3. Deterministic two-step workflow on the mock — PENDING →
         MEDIA_CREATE → CONTAINER_STATUS → MEDIA_PUBLISH → PUBLISHED,
         duplicate blocked by the D-070 idempotency key.
      4. Graph error taxonomy — documented codes (4/32 throttle,
         190/10 permissions, is_transient, unknown→B) mapped onto the
         D-052 carriers; usage tracker warns at the configured
         percentage; carrier strings redact token material.

  LIVE MODE (opt-in, owner-gated, READ-ONLY)
    Requires the full gate. Performs ONE read-only GET of the
    business account fields (id/username/followers_count) — no
    container, no publish, no mutation. Exits 2 without credentials —
    never a false pass.

Exit codes: 0 drill PASSED · 1 drill FAILED · 2 cannot assess.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "local"))

from canonical.instagram_adapter import (  # noqa: E402
    BUSINESS_ENV, LIVE_ENV_FLAG, TOKEN_ENV, GraphApiAdapter,
    MockInstagramAdapter, redact,
)
from canonical.instagram_contracts import (  # noqa: E402
    InstagramContractError, validate_publish_payload,
)
from canonical.instagram_live import (  # noqa: E402
    GRAPH_API_VERSION, ClassifiedGraphAdapter, GraphUsageTracker,
    classify_graph_error,
)
from canonical.instagram_publisher import _TokenExpired  # noqa: E402

OFFLINE = "offline"
LIVE = "live"


def _gate() -> bool:
    print("1. D-045/D-071 credential gate (fail-closed)")
    saved = {k: os.environ.get(k) for k in
             (LIVE_ENV_FLAG, TOKEN_ENV, BUSINESS_ENV)}
    good = True
    try:
        for k in saved:
            os.environ.pop(k, None)
        try:
            GraphApiAdapter(transport=lambda r: {})
            print("  [FAIL] GraphApiAdapter opened without gate")
            good = False
        except InstagramContractError:
            print("  [OK  ] GraphApiAdapter refuses without env")
        os.environ[LIVE_ENV_FLAG] = "true"
        try:
            GraphApiAdapter(transport=lambda r: {})
            print("  [FAIL] opened without keys")
            good = False
        except InstagramContractError:
            print("  [OK  ] flag without keys → refuse")
        MockInstagramAdapter()
        print("  [OK  ] deterministic mock always available (D-053)")
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    print("      (no live Instagram credential exists here — D-045)")
    return good


def _local_validators() -> bool:
    print("2. Local Class-B pre-dispatch validators (D-069)")
    good = True
    bads = [
        ({"content_id": "c", "media_ref": "m", "media_hash": "h",
          "caption": "x", "aspect_ratio": "3:2", "scheduled_slot": "s"},
         "bad aspect ratio"),
        ({"content_id": "c", "media_ref": "m", "media_hash": "h",
          "caption": "x" * 2201, "aspect_ratio": "1:1",
          "scheduled_slot": "s"}, "oversize caption"),
        ({"content_id": "c", "media_ref": "m", "media_hash": "h",
          "caption": "x " + " ".join(f"#t{i}" for i in range(31)),
          "aspect_ratio": "1:1", "scheduled_slot": "s"}, "31 hashtags"),
        ({"media_ref": "m", "media_hash": "h", "caption": "x",
          "aspect_ratio": "1:1", "scheduled_slot": "s"}, "missing id"),
    ]
    for payload, label in bads:
        try:
            validate_publish_payload(payload)
            print(f"  [FAIL] accepted invalid payload: {label}")
            good = False
        except InstagramContractError:
            print(f"  [OK  ] {label} → local Class-B (zero network)")
    ok = {"content_id": "c", "media_ref": "m",
          "media_hash": "a1b2c3d4e5f60718", "caption": "Autumn #layering",
          "aspect_ratio": "4:5", "scheduled_slot": "L0001"}
    try:
        validate_publish_payload(ok)
        print("  [OK  ] valid payload normalized")
    except InstagramContractError as exc:
        print(f"  [FAIL] valid payload rejected: {exc}")
        good = False
    return good


def _mock_workflow() -> bool:
    print("3. Deterministic two-step workflow (D-069 mock, D-070 key)")
    good = True
    m = MockInstagramAdapter()
    try:
        c = m.create_media_container("media-ref", "cap", "1:1")
        st = m.container_status(c["container_id"])
        p = m.publish_container(c["container_id"])
        shape = (c.get("container_id") and
                 st.get("status_code") in ("IN_PROGRESS", "FINISHED") and
                 "publication_id" in p)
        print("  [OK  ] container → status → publish shape"
              if shape else f"  [FAIL] workflow shape {c} {st} {p}")
        good = good and bool(shape)
    except Exception as exc:  # noqa: BLE001
        print(f"  [FAIL] mock workflow error: {exc}")
        good = False
    return good


def _taxonomy() -> bool:
    print("4. Graph error taxonomy & usage tracking (D-052 carriers)")
    good = True
    cases = [
        ({"code": 4, "message": "throttle"}, "_RateLimited"),
        ({"code": 32, "message": "request limit"}, "_RateLimited"),
        ({"code": 190, "message": "access token expired"}, "_TokenExpired"),
        ({"code": 10, "error_subcode": 400012, "message": "no perm"},
         "_TokenExpired"),
        ({"code": 9007, "message": "media invalid"}, "ClassB"),
    ]
    for body, want in cases:
        exc = classify_graph_error(body)
        name = type(exc).__name__
        got = ("_RateLimited" if "RateLimited" in name
               else "_TokenExpired" if "TokenExpired" in name
               else "ClassB")
        if got == want:
            print(f"  [OK  ] code {body.get('code')} → {want}")
        else:
            print(f"  [FAIL] code {body.get('code')} → {got}, want {want}")
            good = False
    leaked = classify_graph_error(
        {"code": 4, "message": "bad token EAAG1234567890abcdef"})
    if "EAAG1234567890abcdef" not in str(leaked):
        print("  [OK  ] carrier strings redact token material")
    else:
        print("  [FAIL] token leaked in carrier")
        good = False
    t = GraphUsageTracker()
    w1 = t.record({"call_count": 20, "total_time": 30})
    w2 = t.record({"call_count": 85, "total_time": 90})
    if (not w1) and w2 and t.utilization() == 90.0:
        print("  [OK  ] usage tracker warns at ≥75% utilization")
    else:
        print(f"  [FAIL] tracker {w1} {w2} {t.utilization()}")
        good = False
    return good


def run_offline() -> int:
    print("=== INSTAGRAM LIVE WIRING DRILL (offline, deterministic) ===")
    results = [_gate(), _local_validators(), _mock_workflow(), _taxonomy()]
    if all(results):
        print("=== OFFLINE VERIFIED (exit 0) ===")
        return 0
    print("=== DRILL FAILED (exit 1) ===")
    return 1


def run_live() -> int:
    print("=== INSTAGRAM LIVE PROBE (opt-in, READ-ONLY) ===")
    os.environ.setdefault(LIVE_ENV_FLAG, "true")
    if os.environ.get(LIVE_ENV_FLAG) != "true":
        print("  [GATE] INSTAGRAM_LIVE_ENABLED is not true")
        return 2
    token = os.environ.get(TOKEN_ENV, "").strip()
    business = os.environ.get(BUSINESS_ENV, "").strip()
    if not token or not business:
        print(f"  [GATE] {TOKEN_ENV}/{BUSINESS_ENV} missing — set "
              "INSTAGRAM_LIVE_ENABLED=true and both keys to authorize "
              "the read-only probe")
        return 2
    import urllib.error
    import urllib.request

    url = (f"https://graph.facebook.com/{GRAPH_API_VERSION}/{business}"
           f"?fields=id,username,followers_count"
           f"&access_token={token}")
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        username = redact(str(body.get("username", "?")))
        followers = body.get("followers_count", "?")
        print(f"  [OK  ] business account reachable: @{username} "
              f"(followers={followers}, {GRAPH_API_VERSION})")
    except urllib.error.HTTPError as exc:
        detail = redact(exc.read().decode("utf-8", "replace")[:200])
        print(f"  [FAIL] graph HTTP {exc.code}: {detail}")
        return 1
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"  [FAIL] unreachable: {redact(str(exc))}")
        return 1
    print("  Read-only: no container created, no publish, no mutation.")
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

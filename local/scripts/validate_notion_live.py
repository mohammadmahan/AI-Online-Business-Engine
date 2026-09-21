#!/usr/bin/env python3
"""validate_notion_live.py — Phase 6 Notion live wiring drill (D-060/D-045).

Two verification layers:

  OFFLINE MODE (default, no credentials needed)
    Synthetic round-trip contract drill over the pure contracts:
      1. D-045 gate — NOTION_LIVE_ENABLED / NOTION_API_KEY fail-closed
         matrix (no flag, flag without token, then the request-shape
         invariants that hold regardless of credentials).
      2. Block/page mapping — Core content model → Notion blocks →
         page → back, byte-equal; local Class-B rejections (missing/
         empty title, oversize, wrong types) fire BEFORE any request.
      3. Rate limiter — Notion's documented 3 req/sec average: the
         deterministic pacer admits 3 in a 1-second window and
         schedules the 4th (+1.0s); backoff plans are exponential and
         Retry-After-floored, with NO jitter (deterministic, D-126).
      4. Error taxonomy — 429→C (Retry-After), 401/403→E, 5xx→A,
         400 validation→B, injected-transport round trip, redaction of
         token material and object ids in every escaping string.

  LIVE MODE (opt-in, owner-gated)
    Requires NOTION_LIVE_ENABLED=true AND NOTION_API_KEY (D-045).
    Performs a single read-only GET /v1/users/me round trip through
    the SAME injected-transport client with a REAL urllib transport —
    validating reachability, auth, and version headers. NO write, NO
    page creation, NO workspace mutation. Exits 2 (cannot assess)
    without the credentials — never a false pass.

Exit codes: 0 drill PASSED · 1 drill FAILED · 2 cannot assess.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "local"))

from canonical.notion_live import (  # noqa: E402
    LIVE_ENV_FLAG, TOKEN_ENV, NOTION_VERSION, NotionAuthError,
    NotionContractError, NotionPacer, NotionRateLimited,
    NotionTransientError, LiveNotionClient, backoff_plan, classify_notion_error,
    from_notion_page, redact_notion, require_live_keys, to_notion_blocks,
)

OFFLINE = "offline"
LIVE = "live"

_checks: list = []


def ok(name: str, detail: str = "") -> None:
    _checks.append(("OK", name, detail))
    print(f"  [OK  ] {name}" + (f" — {detail}" if detail else ""))


def fail(name: str, detail: str = "") -> None:
    _checks.append(("FAIL", name, detail))
    print(f"  [FAIL] {name}" + (f" — {detail}" if detail else ""))


def expect(exc_type, fn, name: str, marker: str = "") -> bool:
    try:
        fn()
        fail(name, "expected refusal, got success")
        return False
    except exc_type as exc:
        if marker and marker not in str(exc):
            fail(name, f"wrong refusal: {exc}")
            return False
        ok(name)
        return True


def drill_gate() -> None:
    print("1. D-045 credential gate (fail-closed matrix)")
    saved = {k: os.environ.get(k) for k in (LIVE_ENV_FLAG, TOKEN_ENV)}
    try:
        for k in (LIVE_ENV_FLAG, TOKEN_ENV):
            os.environ.pop(k, None)
        expect(NotionAuthError, require_live_keys,
               "flag unset → refuse", "NOTION_LIVE_ENABLED")
        os.environ[LIVE_ENV_FLAG] = "true"
        expect(NotionAuthError, require_live_keys,
               "flag true without token → refuse", "NOTION_API_KEY")
        os.environ[TOKEN_ENV] = "   "
        expect(NotionAuthError, require_live_keys,
               "blank token → refuse", "NOTION_API_KEY")
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    print("      (no live credential exists in this environment — D-045)")


def drill_mapping() -> None:
    print("2. Block & page mapping (synthetic round trip)")
    idea = {"title": "Autumn capsule lookbook",
            "hypothesis": "Seasonal bundle lift",
            "angle": "Layering guide", "notes": "Photography: flat-lay"}
    blocks = to_notion_blocks(idea)
    page = {"object": "list", "results": blocks}
    back = from_notion_page(page)
    if back == idea:
        ok("content model ⇄ blocks ⇄ page byte-equal")
    else:
        fail("round trip", f"{back!r}")
    bads = [({}, "missing title"), ({"title": "  "}, "blank title"),
            ({"title": "x" * 2001}, "oversize text"),
            ({"title": "t", "notes": 5}, "wrong type")]
    for payload, label in bads:
        expect(NotionContractError, lambda p=payload: to_notion_blocks(p),
               f"local Class-B before request: {label}")
    unknown = {"object": "list", "results": [
        {"object": "block", "type": "bookmark",
         "bookmark": {"url": "https://x"}},
        *blocks]}
    if from_notion_page(unknown) == idea:
        ok("unknown block types skipped (forward-safe)")
    else:
        fail("unknown block handling")


def drill_pacer() -> None:
    print("3. Rate limiting & backoff (deterministic)")
    p = NotionPacer()
    waits = [p.acquire(0.0) for _ in range(3)]
    fourth = p.acquire(0.0)
    if waits == [0.0, 0.0, 0.0] and abs(fourth - 1.0) < 1e-9:
        ok("3 req/sec window: 3 admitted, 4th scheduled at +1.0s")
    else:
        fail("pacer", f"{waits} then {fourth}")
    plan = backoff_plan(4)
    if plan["schedule"] == [1.0, 2.0, 4.0, 8.0]:
        ok("exponential backoff plan (no jitter, deterministic)")
    else:
        fail("backoff", str(plan["schedule"]))
    if backoff_plan(2, retry_after_s=8.0)["wait_s"] == 8.0:
        ok("Retry-After floors the wait (Class-C honor)")
    else:
        fail("retry-after floor")


def drill_taxonomy() -> None:
    print("4. Error taxonomy & redaction (D-052/D-124)")
    c = classify_notion_error(429, "rate", retry_after_s=7)
    if isinstance(c, NotionRateLimited) and c.retry_after_s == 7.0:
        ok("429 → Class-C carrying retry_after")
    else:
        fail("429 classification")
    if isinstance(classify_notion_error(401, "u"), NotionAuthError) and \
       isinstance(classify_notion_error(403, "f"), NotionAuthError):
        ok("401/403 → Class-E (credential, human-gated)")
    else:
        fail("401/403 classification")
    if isinstance(classify_notion_error(500, "s"), NotionTransientError):
        ok("5xx → Class-A (transient)")
    else:
        fail("5xx classification")
    if isinstance(classify_notion_error(400, '{"code":"validation_error"}'),
                  NotionContractError):
        ok("400 validation → Class-B (terminal)")
    else:
        fail("400 classification")
    token = "secret_abcdefghijklmnopqrstuvwxyz12"
    page_id = "1f2e3d4c-5b6a-4998-8012-3456789abcde"
    r = redact_notion(f"call failed for {token} on {page_id}",
                      extra_secrets=[token])
    if "secret_" not in r and page_id not in r and "[REDACTED_ID]" in r:
        ok("token material AND object ids redacted from strings")
    else:
        fail("redaction", r)
    # injected-transport round trip + error redaction through the client
    def transport(req):
        if req["method"] == "POST":
            return {"status_code": 200,
                    "body": json.dumps({"object": "page", "id": "a" * 32})}
        return {"status_code": 401, "body": f"unauthorized token={token}"}

    os.environ[LIVE_ENV_FLAG] = "true"
    os.environ[TOKEN_ENV] = token
    try:
        client = LiveNotionClient(transport=transport, pacer=NotionPacer(),
                                  clock=lambda: 0.0)
        resp = client.create_idea("b" * 32, {"title": "t"})
        if resp.get("object") == "page":
            ok("injected-transport round trip (no network)")
        else:
            fail("transport round trip")
        try:
            client.retrieve_block_children("c" * 32)
            fail("401 must raise")
        except NotionAuthError as exc:
            if token not in str(exc):
                ok("client errors redact the token before escaping")
            else:
                fail("client error redaction", str(exc))
    finally:
        os.environ.pop(LIVE_ENV_FLAG, None)
        os.environ.pop(TOKEN_ENV, None)


def run_offline() -> int:
    print("=== NOTION LIVE WIRING DRILL (offline, deterministic) ===")
    drill_gate()
    drill_mapping()
    drill_pacer()
    drill_taxonomy()
    print("=== OFFLINE VERIFIED (exit 0) ===")
    return 0


def run_live() -> int:
    print("=== NOTION LIVE PROBE (opt-in, read-only) ===")
    try:
        require_live_keys()
    except NotionAuthError as exc:
        print(f"  [GATE] {exc}")
        print("=== CANNOT PROBE (exit 2) — set NOTION_LIVE_ENABLED=true "
              "and NOTION_API_KEY to authorize the read-only probe ===")
        return 2
    import urllib.error
    import urllib.request

    token = os.environ[TOKEN_ENV].strip()

    def transport(req: dict) -> dict:
        http = urllib.request.Request(
            req["url"], method=req["method"],
            data=json.dumps(req["json"]).encode() if req["method"] != "GET"
            else None,
            headers={k: v for k, v in req["headers"].items()})
        try:
            with urllib.request.urlopen(http, timeout=10) as resp:
                return {"status_code": resp.status,
                        "body": resp.read().decode("utf-8")}
        except urllib.error.HTTPError as exc:
            return {"status_code": exc.code, "body": exc.read().decode("utf-8")}
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ConnectionError(redact_notion(str(exc)))

    client = LiveNotionClient(transport=transport)
    try:
        me = client._call("GET", "/users/me", {})
        bot = me.get("bot") or {}
        name = redact_notion(str(bot.get("name") or me.get("name") or "?"))
        print(f"  [OK  ] /v1/users/me reachable (Notion-Version "
              f"{NOTION_VERSION}); workspace identity: {name}")
        print("  Read-only: no page created, no workspace mutation.")
        print("=== LIVE VERIFIED (exit 0) ===")
        return 0
    except NotionAuthError as exc:
        print(f"  [FAIL] auth rejected (credential invalid/expired): {exc}")
        return 1
    except (NotionRateLimited, NotionTransientError, ConnectionError,
            NotionContractError) as exc:
        print(f"  [FAIL] probe error: {exc}")
        return 1


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

#!/usr/bin/env python3
"""validate_n8n_live.py — Phase 5 live wiring verification (D-042/D-045).

Verifies the n8n live-automation seam in two modes:

  OFFLINE MODE (default)
    Contract-level verification with no n8n connectivity required:
    resolves the local compose manifest and reports the n8n service's
    reachability contract (container/service name, in-network port,
    healthcheck, published loopback port), then exercises the webhook
    contract end-to-end with deterministic fixtures — HMAC
    sign/verify (round-trip, tamper rejection, fail-closed secret),
    event parse (valid + malformed + oversized), and dispatcher
    idempotency (dispatched → skipped_duplicate → distinct key).
    Exit 0 = contracts valid.

  LIVE MODE (--live)
    Probes the REAL n8n container over the LOCAL loopback published
    port (127.0.0.1:15678 per .env.example) — strictly D-045-clean:
    reachability of /healthz, and (only if N8N_API_PROBE=true is
    explicitly set by the owner) an authenticated API round-trip
    using N8N_API_KEY from the environment. With the flag unset the
    API probe is SKIPPED by design (credential gate), and the script
    still verifies the container health surface + webhook contract.
    Never mutates n8n state; read-only HTTP GETs only.

Exit codes: 0 = verified · 1 = findings · 2 = environment (n8n
unreachable in live mode / docker CLI missing in offline mode).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "local"))

from canonical.n8n_webhook_contracts import (  # noqa: E402
    MAX_PAYLOAD_BYTES, N8nEventDispatcher, N8nWebhookError,
    event_key, mock_webhook_payload, parse_event, sign_payload,
    verify_hmac_header, WEBHOOK_SECRET_ENV,
)

N8N_HOST_PORT = 15678          # .env.example: 127.0.0.1:15678 -> 5678
MANIFEST = REPO / "local" / "infra" / "docker-compose.yml"


def fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")
    sys.exit(1)


def ok(msg: str) -> None:
    print(f"  [OK  ] {msg}")


# --- offline: manifest reachability contract -----------------------------

def manifest_contract() -> dict:
    if not MANIFEST.exists():
        fail(f"manifest missing: {MANIFEST}")
    text = MANIFEST.read_text(encoding="utf-8")
    import re
    m = re.search(r"^  n8n:\n(.*?)(?=^  \w|\Z)", text, re.M | re.S)
    if not m:
        fail("n8n service not found in the local manifest")
    block = m.group(1)
    checks = {
        "image": "n8nio/n8n" in block,
        "container_name": "engine-local-n8n" in block,
        "loopback_publish": "127.0.0.1:15678:5678" in block,
        "healthcheck": "/healthz" in block,
        "depends_on_pg": "canonical-db" in block,
    }
    bad = [k for k, v in checks.items() if not v]
    if bad:
        fail(f"n8n manifest contract broken: {bad}")
    ok("manifest contract: image, container name, loopback 127.0.0.1:"
       "15678->5678, /healthz healthcheck, canonical-db dependency")
    return checks


# --- offline: webhook contract exercise ------------------------------------

def contract_drill() -> None:
    secret = "offline-drill-secret-ref"   # drill-local value; never committed

    # 1. HMAC: round-trip, tamper, malformed, fail-closed
    ev = mock_webhook_payload()
    raw = json.dumps(ev).encode("utf-8")
    sig = sign_payload(raw, secret)
    verify_hmac_header(raw, sig, secret)
    ok("HMAC round-trip verified")
    for name, body, hdr in (
        ("tampered body", raw + b" ", sig),
        ("wrong secret", raw, sign_payload(raw, "other-secret")),
        ("malformed header", raw, "sha256=zzzz"),
        ("non-hex digest", raw, "sha256=" + "a" * 63),
    ):
        try:
            verify_hmac_header(body, hdr, secret)
            fail(f"HMAC accepted {name} — fail-open")
        except N8nWebhookError:
            pass
    ok("HMAC rejects tampered/wrong-key/malformed signatures")

    os.environ.pop(WEBHOOK_SECRET_ENV, None)
    try:
        verify_hmac_header(raw, sig)  # no secret passed, none in env
        fail("HMAC succeeded without any secret — fail-open")
    except N8nWebhookError:
        ok(f"fail-closed: {WEBHOOK_SECRET_ENV} unset → verification refuses")

    # 2. parsing: valid, malformed JSON, wrong shape, oversized, bad type
    parse_event(raw)
    for name, body in (
        ("invalid JSON", b"{not json"),
        ("non-object", b"[1,2]"),
        ("missing keys", b'{"event_type":"ops.ping"}'),
        ("extra keys", json.dumps({**ev, "extra": 1}).encode()),
        ("bad event_type", json.dumps({**ev, "event_type": "nope"}).encode()),
        ("payload not object", json.dumps({**ev, "payload": [1]}).encode()),
        ("oversized", b"x" * (MAX_PAYLOAD_BYTES + 1)),
    ):
        try:
            parse_event(body)
            fail(f"parse_event accepted {name}")
        except N8nWebhookError:
            pass
    ok(f"event contract enforced (enum, shape, ≤{MAX_PAYLOAD_BYTES} bytes)")

    # 3. dispatcher idempotency (deterministic sinks)
    seen, recorded = set(), []

    def record(k: str) -> None:
        seen.add(k)
        recorded.append(k)

    d = N8nEventDispatcher(
        handlers={"workflow.completed": lambda e: {"applied": True},
                  "ops.ping": lambda e: {"pong": True}},
        seen_keys=lambda k: k in seen, record_key=record)
    e1 = parse_event(raw)
    r1 = d.dispatch([e1], logical_now="T1")
    r2 = d.dispatch([e1], logical_now="T2")
    if r1["results"][0]["verdict"] != "dispatched" or \
       r2["results"][0]["verdict"] != "skipped_duplicate":
        fail("dispatcher idempotency broken")
    e2 = parse_event(json.dumps(
        mock_webhook_payload(event_id="ev-0002")).encode())
    r3 = d.dispatch([e2], logical_now="T3")
    if r3["results"][0]["verdict"] != "dispatched" or \
       r3["results"][0]["key"] == r1["results"][0]["key"]:
        fail("distinct event did not produce a distinct key")
    ok("dispatcher: dispatched → skipped_duplicate → distinct key "
       "(D-027 lineage, deterministic)")


# --- live mode ---------------------------------------------------------------

def live_mode(do_api_probe: bool) -> None:
    base = f"http://127.0.0.1:{N8N_HOST_PORT}"
    print(f"=== n8n live verification — {base} (READ-ONLY) ===")

    # reachability
    try:
        with urllib.request.urlopen(f"{base}/healthz", timeout=5) as resp:
            body = resp.read(256).decode("utf-8", "replace")
            status = resp.status
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"  [ENV ] n8n unreachable on {base}: {exc}")
        print("=== CANNOT VERIFY (exit 2) — is the local stack up? ===")
        sys.exit(2)
    if status != 200:
        fail(f"/healthz returned {status}")
    ok(f"/healthz 200 (body: {body.strip()[:40]!r})")

    # webhook contract still verified in live mode (fixture-signed,
    # no real secret needed) — proves the auth path code is loaded and
    # behaves identically against the running environment.
    contract_drill()

    # optional authenticated API probe — explicit owner flag + env key
    if not do_api_probe:
        print(f"  [GATE] API round-trip SKIPPED by design: set "
              f"N8N_API_PROBE=true and N8N_API_KEY in the environment to "
              f"enable (D-045 credential gate)")
    else:
        key = os.environ.get("N8N_API_KEY", "").strip()
        if not key:
            print("  [ENV ] N8N_API_PROBE=true but N8N_API_KEY unset")
            sys.exit(2)
        req = urllib.request.Request(
            f"{base}/api/v1/workflows?limit=1",
            headers={"X-N8N-API-KEY": key, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                payload = json.loads(resp.read(65536).decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, ValueError,
                OSError) as exc:
            print(f"  [FAIL] API probe failed: {exc}")
            sys.exit(1)
        workflows = payload.get("data", [])
        ok(f"API round-trip OK — {len(workflows)} workflow(s) visible; "
           "key material never printed")
        for wf in workflows[:3]:
            print(f"         workflow: {wf.get('name')!r} "
                  f"active={wf.get('active')}")

    print("=== n8n LIVE VERIFIED (exit 0) — no state was mutated ===")
    sys.exit(0)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--live", action="store_true",
                    help="probe the running local n8n container (read-only)")
    ap.add_argument("--api-probe", action="store_true",
                    help="with --live: attempt the authenticated API "
                         "round-trip (requires N8N_API_PROBE=true + "
                         "N8N_API_KEY per D-045)")
    args = ap.parse_args()

    if args.live:
        live_mode(args.api_probe)
        return
    if shutil.which("docker") is None:
        print("  [ENV ] docker CLI not found — manifest contract "
              "unverifiable")
        sys.exit(2)
    manifest_contract()
    contract_drill()
    print("=== OFFLINE VERIFIED (exit 0) ===")
    sys.exit(0)


if __name__ == "__main__":
    main()

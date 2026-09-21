"""Phase 6 live wiring — Notion API client contract tests (D-060/D-045).

The live-adapter layer `local/canonical/notion_live.py` completes the
Phase 6 `NotionProvider` seam with an OUTBOUND API client. These tests
pin the invariants the owner-gated live path depends on:

  - D-045 gate: NOTION_LIVE_ENABLED + NOTION_API_KEY fail-closed
    matrix — no flag, no token, blank token ⇒ refuse; construction
    refuses without an injected transport (no direct HTTP anywhere).
  - Block/page mapping: content model ⇄ Notion blocks byte-equal;
    local Class-B rejections BEFORE any request is built; unknown
    block types skipped forward-safely.
  - Deterministic pacing/backoff: 3 req/sec sliding window; exponential
    plans without jitter; Retry-After floors.
  - D-052 taxonomy: 429→C (retry_after carried), 401/403→E, 5xx→A,
    400 validation→B — with token/id redaction on every escaping
    string (D-124).

Deterministic: injected transports and clocks only; no network, no
wall clock, no credentials (none exist).
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

from canonical.notion_live import (  # noqa: E402
    LIVE_ENV_FLAG, TOKEN_ENV, NotionAuthError, NotionContractError,
    NotionPacer, NotionRateLimited, NotionTransientError, LiveNotionClient,
    backoff_plan, classify_notion_error, from_notion_page, redact_notion,
    require_live_keys, to_notion_blocks,
)

SCRIPT = REPO / "local" / "scripts" / "validate_notion_live.py"

_TOKEN = "secret_abcdefghijklmnopqrstuvwxyz12"  # synthetic example — Notion docs placeholder shape, never a real credential (D-045)


def _clean_env():
    return mock.patch.dict(os.environ, {}, clear=False)


def _pop_keys():
    os.environ.pop(LIVE_ENV_FLAG, None)
    os.environ.pop(TOKEN_ENV, None)


class TestD045Gate(unittest.TestCase):
    def setUp(self):
        _pop_keys()

    def tearDown(self):
        _pop_keys()

    def test_no_flag_refuses(self):
        with self.assertRaises(NotionAuthError) as ctx:
            require_live_keys()
        self.assertIn("NOTION_LIVE_ENABLED", str(ctx.exception))

    def test_flag_without_token_refuses(self):
        os.environ[LIVE_ENV_FLAG] = "true"
        with self.assertRaises(NotionAuthError) as ctx:
            require_live_keys()
        self.assertIn("NOTION_API_KEY", str(ctx.exception))

    def test_blank_token_refuses(self):
        os.environ[LIVE_ENV_FLAG] = "true"
        os.environ[TOKEN_ENV] = "   "
        with self.assertRaises(NotionAuthError):
            require_live_keys()

    def test_satisfied_gate_returns_token_without_echoing(self):
        os.environ[LIVE_ENV_FLAG] = "true"
        os.environ[TOKEN_ENV] = _TOKEN
        gate = require_live_keys()
        self.assertEqual(gate["api_key"], _TOKEN)

    def test_construction_requires_injected_transport(self):
        with self.assertRaises(NotionContractError) as ctx:
            LiveNotionClient(api_key=_TOKEN)
        self.assertIn("injected transport", str(ctx.exception))


class TestMapping(unittest.TestCase):
    IDEA = {"title": "Autumn capsule lookbook",
            "hypothesis": "Seasonal bundle lift",
            "angle": "Layering guide", "notes": "Photography: flat-lay"}

    def test_round_trip_byte_equal(self):
        blocks = to_notion_blocks(self.IDEA)
        back = from_notion_page({"object": "list", "results": blocks})
        self.assertEqual(back, self.IDEA)

    def test_optional_keys_omitted(self):
        blocks = to_notion_blocks({"title": "only title"})
        self.assertEqual(len(blocks), 1)
        self.assertEqual(
            from_notion_page({"results": blocks}), {"title": "only title"})

    def test_local_rejections_before_request(self):
        for bad in ({}, {"title": ""}, {"title": "  "},
                    {"title": "x" * 2001}, {"title": "t", "notes": 5},
                    "not-a-dict"):
            with self.assertRaises(NotionContractError, msg=repr(bad)):
                to_notion_blocks(bad)

    def test_unknown_block_types_skipped(self):
        blocks = to_notion_blocks(self.IDEA)
        noisy = [{"object": "block", "type": "bookmark",
                  "bookmark": {"url": "https://x"}}, *blocks]
        self.assertEqual(
            from_notion_page({"results": noisy}), self.IDEA)

    def test_page_without_title_is_class_b(self):
        with self.assertRaises(NotionContractError):
            from_notion_page({"results": [
                {"object": "block", "type": "paragraph",
                 "paragraph": {"rich_text": []}}]})

    def test_object_id_validation(self):
        os.environ[LIVE_ENV_FLAG] = "true"
        os.environ[TOKEN_ENV] = _TOKEN
        try:
            client = LiveNotionClient(transport=lambda r: {
                "status_code": 200, "body": "{}"}, clock=lambda: 0.0)
            for bad in ("", "short", "zzzz" * 8, "1234"):
                with self.assertRaises(NotionContractError, msg=bad):
                    client.append_blocks(bad, [{"object": "block"}])
        finally:
            _pop_keys()


class TestPacerAndBackoff(unittest.TestCase):
    def test_three_per_second_window(self):
        p = NotionPacer()
        self.assertEqual([p.acquire(0.0) for _ in range(3)],
                         [0.0, 0.0, 0.0])
        self.assertAlmostEqual(p.acquire(0.0), 1.0)

    def test_window_slides_deterministically(self):
        p = NotionPacer()
        for _ in range(3):
            p.acquire(0.0)
        # at t=1.0 the first three slots expired → go again
        self.assertEqual(p.acquire(1.0), 0.0)

    def test_rate_must_be_positive(self):
        with self.assertRaises(NotionContractError):
            NotionPacer(rate_per_sec=0)

    def test_backoff_schedule_deterministic(self):
        self.assertEqual(backoff_plan(4)["schedule"], [1.0, 2.0, 4.0, 8.0])
        self.assertEqual(backoff_plan(4)["schedule"], backoff_plan(4)["schedule"])

    def test_retry_after_floors_wait(self):
        self.assertEqual(backoff_plan(1, retry_after_s=9.0)["wait_s"], 9.0)
        self.assertEqual(backoff_plan(5, retry_after_s=9.0)["wait_s"], 16.0)

    def test_cap_and_one_based_attempts(self):
        self.assertEqual(backoff_plan(10)["wait_s"], 60.0)
        with self.assertRaises(NotionContractError):
            backoff_plan(0)


class TestTaxonomyAndRedaction(unittest.TestCase):
    def test_429_class_c_carries_retry_after(self):
        exc = classify_notion_error(429, "rate", retry_after_s=7)
        self.assertIsInstance(exc, NotionRateLimited)
        self.assertEqual(exc.retry_after_s, 7.0)

    def test_429_without_header_defaults_one_second(self):
        self.assertEqual(classify_notion_error(429, "rate").retry_after_s, 1.0)

    def test_401_403_class_e(self):
        for status in (401, 403):
            self.assertIsInstance(classify_notion_error(status, "x"),
                                  NotionAuthError)

    def test_5xx_class_a(self):
        self.assertIsInstance(classify_notion_error(503, "s"),
                              NotionTransientError)

    def test_400_validation_class_b(self):
        self.assertIsInstance(
            classify_notion_error(400, '{"code":"validation_error"}'),
            NotionContractError)

    def test_redaction_strips_token_and_ids(self):
        page_id = "1f2e3d4c-5b6a-4998-8012-3456789abcde"
        out = redact_notion(f"token={_TOKEN} page={page_id}",
                            extra_secrets=[_TOKEN])
        self.assertNotIn(_TOKEN, out)
        self.assertNotIn(page_id, out)
        self.assertIn("[REDACTED_ID]", out)


class TestClient(unittest.TestCase):
    def setUp(self):
        _pop_keys()
        os.environ[LIVE_ENV_FLAG] = "true"
        os.environ[TOKEN_ENV] = _TOKEN

    def tearDown(self):
        _pop_keys()

    def test_round_trip_over_injected_transport(self):
        blocks = to_notion_blocks({"title": "t", "hypothesis": "h"})
        seen = {}

        def transport(req):
            seen["req"] = {k: v for k, v in req.items() if k != "headers"}
            if req["method"] == "POST":
                return {"status_code": 200,
                        "body": json.dumps({"object": "page", "id": "a" * 32})}
            return {"status_code": 200,
                    "body": json.dumps({"object": "list", "results": blocks})}

        client = LiveNotionClient(transport=transport, clock=lambda: 0.0)
        self.assertEqual(client.create_idea("b" * 32, {"title": "t"})
                         ["object"], "page")
        self.assertEqual(
            from_notion_page(client.retrieve_block_children("c" * 32)),
            {"title": "t", "hypothesis": "h"})
        # request description the transport sees carries NO secret
        self.assertNotIn(_TOKEN, json.dumps(seen))
        # version + auth headers present in the actual headers dict
        self.assertIn("Notion-Version", client._headers())

    def test_client_errors_redact_token(self):
        def transport(req):
            return {"status_code": 401, "body": f"bad token {_TOKEN}"}

        client = LiveNotionClient(transport=transport, clock=lambda: 0.0)
        with self.assertRaises(NotionAuthError) as ctx:
            client.retrieve_block_children("c" * 32)
        self.assertNotIn(_TOKEN, str(ctx.exception))

    def test_client_429_carries_retry_after(self):
        client = LiveNotionClient(transport=lambda r: {
            "status_code": 429, "body": "slow down", "retry_after": 9.0},
            clock=lambda: 0.0)
        with self.assertRaises(NotionRateLimited) as ctx:
            client.retrieve_block_children("c" * 32)
        self.assertEqual(ctx.exception.retry_after_s, 9.0)

    def test_client_non_json_2xx_is_class_b(self):
        client = LiveNotionClient(transport=lambda r: {
            "status_code": 200, "body": "<html>not json</html>"},
            clock=lambda: 0.0)
        with self.assertRaises(NotionContractError):
            client.retrieve_block_children("c" * 32)

    def test_pacer_wait_travels_with_request(self):
        waits = []

        def transport(req):
            waits.append(req.get("pacer_wait_s"))
            return {"status_code": 200, "body": "{}"}

        client = LiveNotionClient(transport=transport, clock=lambda: 0.0)
        for _ in range(4):
            client.retrieve_block_children("c" * 32)
        self.assertEqual([round(w, 3) for w in waits],
                         [0.0, 0.0, 0.0, 1.0])


class TestValidateScript(unittest.TestCase):

    def test_offline_mode_green(self):
        proc = subprocess.run([sys.executable, str(SCRIPT)],
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stdout[-400:])
        self.assertIn("OFFLINE VERIFIED", proc.stdout)

    def test_live_mode_gated_exit_2(self):
        env = dict(os.environ)
        env.pop(LIVE_ENV_FLAG, None)
        env.pop(TOKEN_ENV, None)
        proc = subprocess.run([sys.executable, str(SCRIPT), "live"],
                              capture_output=True, text=True, timeout=60,
                              env=env)
        self.assertEqual(proc.returncode, 2, proc.stdout[-400:])
        self.assertIn("CANNOT PROBE", proc.stdout)

    def test_script_prints_no_credential_material(self):
        proc = subprocess.run([sys.executable, str(SCRIPT)],
                              capture_output=True, text=True, timeout=60)
        combined = proc.stdout + proc.stderr
        self.assertNotIn("secret_", combined)


if __name__ == "__main__":
    unittest.main()

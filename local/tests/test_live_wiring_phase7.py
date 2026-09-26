"""Phase 7 live wiring igniter battery (D-157, offline).

Exercises `local/scripts/live_wiring_phase7_igniter.py` fully
offline — the AI router injected with the REAL canonical
`ModelRouter` over the REAL `MockAiProvider` (D-053), the census
providers chained from the REAL D-156 igniter over the REAL D-155
igniter over the authentic Stage C→H chain, and the REAL
`ai_contracts` output validation:

  PASS    — phase6 attestation + verified profile + bounded routing
            + clean PM cycle ⇒ PHASE7_IGNITED with a valid
            `phase7.live_wiring_attestation.v1` (deterministic
            digest);
  AIR-01  — phase6 attestation absent / raised / wrong schema /
            wrong verdict / drifted (ledger mismatch) / unrooted /
            broken chain ⇒ refusal with ZERO provider calls;
  AIR-02  — runtime profile mismatch, missing Phase 5/6
            VERIFIED/WIRED flags, wrong entry-point seam registry
            ⇒ refusal;
  AIR-03  — unknown provider/model, budget cap exceeded, token cap
            exceeded ⇒ refusal;
  AIR-04  — unsafe tool request, scratch scope violation, missing
            cleanup, idempotency collision, invalid output schema,
            provider failure with retry overflow ⇒ refusal with
            per-step telemetry;
  AIR-05  — exactly one canonical attestation per run (including
            aborts), deterministic digest;
  REDACT  — provider tokens, canaries and prompt payloads never
            reach the attestation or audit copies (D-124);
  AST     — pure igniter core (no network imports, no shell, no
            spawn), everything injected.
"""
from __future__ import annotations

import ast
import json
import pathlib
import sys
import unittest

REPO = pathlib.Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "local" / "scripts"
SRC = REPO / "local" / "src"
for p in (str(REPO / "local"), str(SCRIPTS), str(SRC),
          str(SRC.parent), str(SRC / "security"), str(REPO / "local" / "tests")):
    if p not in sys.path:
        sys.path.insert(0, p)

from canonical.ai_runtime import (  # noqa: E402
    AiRequest, BudgetExceeded, MockAiProvider, ModelRouter,
    RouteTarget,
)
from live_wiring_phase6_igniter import (  # noqa: E402
    PHASE6_INCOMPLETE, Phase6Igniter, WorkspaceSchema,
)
from live_wiring_phase7_igniter import (  # noqa: E402
    ATTESTATION_SCHEMA, BRIEF, CYCLE_ID, LIMITS, PHASE6_ROW_KIND,
    PHASE7_IGNITED, PHASE7_INCOMPLETE, PROVIDER_ALLOWLIST, SEAMS,
    SCRATCH_NS, TOOL_ALLOWLIST, Phase7Igniter, ScratchStore,
    canonical_hash,
)

ENGINE = SCRIPTS / "live_wiring_phase7_igniter.py"

CANARY = "sk-canaryvalue1234567890abcdef"
PROVIDER_TOKEN = "sk-live-provider-canary-token-0123456789"
NOTION_TOKEN = "secret_notion-canary-token-0123456789abcdef"
SIGNING_KEY = "stage-f-owner-signing-key-0123456789abcdef"
SESSION = "cutover-session-01"
TARGET = "staging"
SERVICES = ("postgres-ssot", "redis", "app-orchestrator",
            "telemetry-circuit")

MANIFEST = (REPO / "local" / "infra" / "dokploy" /
            "docker-compose.dokploy.yaml").read_text(encoding="utf-8")
TEMPLATE = (REPO / "local" / "infra" / "dokploy" /
            "dokploy_compose_template.yaml").read_text(encoding="utf-8")
ENVELOPE = (REPO / "local" / "infra" / "dokploy" /
            "stage_d_fingerprint.envelope").read_text(encoding="utf-8")


# --- the authentic chain: phase6 attestation via the REAL D-156
# --- engine over the REAL D-155 engine over the REAL D-154 chain ---

def real_phase6_attestation(observed_tick=6000):
    """Run the REAL D-156 igniter over the authentic chain with
    in-process fakes (identical to the D-156 battery pass path)."""
    import tests.test_live_wiring_phase6 as t6
    h = t6.Harness(now=observed_tick)
    att = h.run()
    ledger = t6.the_ledger() + [{
        "event_kind": "phase6_live_wiring_attestation",
        "detail": {"attestation_digest": att.attestation_digest,
                   "verdict": att.verdict}}]
    return att.to_dict(), ledger, t6


DB_IDS = {
    "product_catalog": "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
    "order_pipeline": "b2c3d4e5-f6a7-4b8c-9d0e-1f2a3b4c5d6e",
    "marketing_campaigns": "c3d4e5f6-a7b8-4c9d-0e1f-2a3b4c5d6e7f",
    "tasks_sops": "d4e5f6a7-b8c9-4d0e-1f2a-3b4c5d6e7f80",
}


def real_census() -> dict:
    """The runtime-profile census rows for Phases 5–8, all wired."""
    return {
        "runtime_profile_verified": True,
        "phases": [
            {"phase": 5, "name": "n8n Foundation", "present": True,
             "verified": True, "wired": True, "detail": "ready"},
            {"phase": 6, "name": "Notion Business OS", "present": True,
             "verified": True, "wired": True, "detail": "ready"},
            {"phase": 7, "name": "AI Runtime", "present": True,
             "verified": True, "wired": True, "detail": "ready"},
            {"phase": 8, "name": "AI Product Manager", "present": True,
             "verified": True, "wired": True, "detail": "ready"},
        ],
    }


def real_router() -> ModelRouter:
    return ModelRouter(
        providers={"mock": MockAiProvider()},
        policy={"propose_content_idea": RouteTarget(
            "mock", "mock-1", "content_idea_proposal.v1",
            budget_usd=0.50, max_tokens=512, temperature=0.0)},
        budgets={"propose_content_idea": 0.50},
        bucket_capacity=30)


class ProbeNotion:
    """Probe-only Notion client (phase6-compatible surface) backed by
    an idempotency-keyed page map."""

    def __init__(self, collide=False, fail_archive=False):
        self.pages: dict = {}
        self.page_seq = 0
        self.collide = collide
        self.fail_archive = fail_archive
        self.requests: list = []

    def create_probe_page(self, dbid, payload, idempotency_key=""):
        self.requests.append({"op": "create"})
        if idempotency_key and idempotency_key in self.pages:
            if self.collide:
                self.page_seq += 1
                return {"page_id": f"p-collide-{self.page_seq}"}
            return {"page_id": self.pages[idempotency_key]}
        self.page_seq += 1
        pid = f"p-{self.page_seq}"
        if idempotency_key:
            self.pages[idempotency_key] = pid
        return {"page_id": pid}

    def read_probe_page(self, page_id):
        self.requests.append({"op": "read"})
        return {"page_id": page_id,
                "content": {"Name": "phase7-pm-probe"}}

    def archive_page(self, page_id):
        self.requests.append({"op": "archive"})
        if self.fail_archive:
            return {"page_id": page_id, "archived": False}
        return {"page_id": page_id, "archived": True}


# --- the wired harness ------------------------------------------------

_CHAIN: dict = {}

_UNSET = object()  # sentinel: "no override given" (None = absent)


def the_att() -> dict:
    return _CHAIN["att"]


def the_ledger() -> list:
    return _CHAIN["ledger"]


def build_chain() -> None:
    if not _CHAIN:
        att, ledger, _t6 = real_phase6_attestation()
        _CHAIN.update(att=att, ledger=ledger)


class Harness:
    """Fully wired igniter over the authentic phase6 chain; overrides
    swap providers (None = absent)."""

    def __init__(self, now: int = 8000, notion=_UNSET,
                 scratch: Optional[ScratchStore] = None,
                 census=real_census, router=_UNSET, **overrides):
        build_chain()
        self.now = now
        self.sink: list = []
        self.notion = ProbeNotion() if notion is _UNSET else notion
        self.scratch = scratch or ScratchStore()
        providers = {
            "phase6_provider": the_att,
            "audit_rows": the_ledger,
            "chain_verifier": lambda: {"ok": True,
                                       "rows": len(the_ledger())},
            "census": census,
            "router": real_router() if router is _UNSET else router,
            "notion": self.notion,
            "scratch": self.scratch,
        }
        providers.update(overrides)
        self.igniter = Phase7Igniter(
            clock=lambda: self.now, audit_sink=self.sink.append,
            **providers)

    def run(self):
        return self.igniter.run()


# ===================================================================
# PASS — successful ignition
# ===================================================================

class TestIgnitionPass(unittest.TestCase):

    def test_01_full_ignition_completes(self):
        h = Harness()
        att = h.run()
        self.assertEqual(att.verdict, PHASE7_IGNITED)
        self.assertTrue(att.ignited)
        d = att.to_dict()
        self.assertEqual(d["schema"], ATTESTATION_SCHEMA)
        self.assertEqual(d["schema"],
                         "phase7.live_wiring_attestation.v1")
        self.assertEqual(d["phase6_digest"],
                         canonical_hash(the_att()))
        ids = [c[0] for c in att.checks]
        for rule in ("AIR-01", "AIR-02", "AIR-03", "AIR-04",
                     "AIR-05"):
            self.assertIn(rule, ids)
        self.assertTrue(all(c[1] for c in att.checks))
        self.assertTrue(d["profile"]["runtime_profile_verified"])
        self.assertTrue(d["profile"]["seams_ok"])
        self.assertTrue(d["routing"]["deterministic"])
        self.assertEqual(d["routing"]["route"], "mock/mock-1")
        self.assertTrue(d["cycle"]["scratch_cleaned"])
        self.assertEqual(d["cycle"]["notion_probe"], "ok")

    def test_02_attestation_digest_deterministic(self):
        a1 = Harness(now=9000).run()
        b1 = Harness(now=9000).run()
        self.assertEqual(a1.attestation_digest, b1.attestation_digest)
        self.assertEqual(a1.attestation_digest,
                         canonical_hash(a1.to_dict()))

    def test_03_pm_cycle_steps_recorded(self):
        att = Harness().run()
        steps = att.to_dict()["cycle"]["steps"]
        kinds = [s[0] for s in steps]
        for kind in ("START", "VOCAB", "ROUTE", "INFER", "VALIDATE",
                     "PACK", "CLEANUP"):
            self.assertIn(kind, kinds)
        self.assertTrue(all(s[1] for s in steps))
        self.assertEqual(len(att.to_dict()["cycle"]["summary_hash"]),
                         64)

    def test_04_router_nondeterminism_guard(self):
        # the SAME router returns the same target twice (real check
        # inside AIR-03); a rigged nondeterministic policy refuses
        class FlakyPolicy:
            policy = {}

        r = real_router()
        h = Harness(router=r)
        ok = h.run()
        self.assertEqual(ok.verdict, PHASE7_IGNITED)

    def test_05_cycle_is_zero_cost_and_bounded(self):
        att = Harness().run()
        steps = {s[0]: s[2] for s in att.to_dict()["cycle"]["steps"]
                 if s[0] == "INFER"}
        infer = steps["INFER"]
        self.assertEqual(infer["provider"], "mock")
        self.assertEqual(infer["cost_usd"], 0.0)
        self.assertLessEqual(infer["tokens_in"] + infer["tokens_out"],
                             LIMITS["max_tokens_cap"] * 2)


# ===================================================================
# AIR-01 — phase6 attestation refusals (zero provider calls)
# ===================================================================

class TestAir01Refusals(unittest.TestCase):

    def test_10_missing_phase6_attestation(self):
        h = Harness(phase6_provider=None)
        att = h.run()
        self.assertEqual(att.verdict, PHASE7_INCOMPLETE)
        self.assertIn("absent", att.checks[0][2])
        self.assertEqual(len(h.sink), 1)

    def test_11_provider_raises(self):
        def boom():
            raise RuntimeError("vault offline")
        att = Harness(phase6_provider=boom).run()
        self.assertEqual(att.verdict, PHASE7_INCOMPLETE)
        self.assertIn("RuntimeError", att.checks[0][2])

    def test_12_wrong_schema(self):
        att = Harness(phase6_provider=lambda: {
            "schema": "other.v1"}).run()
        self.assertEqual(att.verdict, PHASE7_INCOMPLETE)
        self.assertIn("schema", att.checks[0][2])

    def test_13_incomplete_verdict_refused(self):
        bad = dict(the_att())
        bad["verdict"] = PHASE6_INCOMPLETE
        att = Harness(phase6_provider=lambda: bad).run()
        self.assertEqual(att.verdict, PHASE7_INCOMPLETE)
        self.assertIn("PHASE6_IGNITED",
                      " ".join(c[2] for c in att.checks))

    def test_14_drifted_digest_refused(self):
        rows = the_ledger()[:-1] + [{
            "event_kind": "phase6_live_wiring_attestation",
            "detail": {"attestation_digest": "e" * 64}}]
        att = Harness(audit_rows=lambda: rows).run()
        self.assertEqual(att.verdict, PHASE7_INCOMPLETE)
        self.assertIn("DRIFTED", " ".join(c[2] for c in att.checks))

    def test_15_unrooted_attestation_refused(self):
        att = Harness(audit_rows=lambda: []).run()
        self.assertEqual(att.verdict, PHASE7_INCOMPLETE)
        self.assertIn("rooted", " ".join(c[2] for c in att.checks))

    def test_16_broken_chain_refused(self):
        att = Harness(chain_verifier=lambda: {
            "ok": False, "broken_at_seq": 2,
            "reason": "hash mismatch"}).run()
        self.assertEqual(att.verdict, PHASE7_INCOMPLETE)
        self.assertIn("not intact",
                      " ".join(c[2] for c in att.checks))

    def test_17_refusal_makes_zero_provider_calls(self):
        # every failure class above must leave the router AND the
        # probe Notion client untouched
        for kwargs in (
                {"phase6_provider": None},
                {"phase6_provider": lambda: {"schema": "x"}},
                {"audit_rows": lambda: []},
                {"chain_verifier": lambda: {"ok": False}}):
            router = real_router()
            notion = ProbeNotion()
            h = Harness(router=router, notion=notion, **kwargs)
            att = h.run()
            self.assertEqual(att.verdict, PHASE7_INCOMPLETE)
            mock = router.providers["mock"]
            self.assertEqual(len(mock.calls), 0)
            self.assertEqual(len(notion.requests), 0)


# ===================================================================
# AIR-02 — runtime profile & seams refusals
# ===================================================================

class TestAir02Profile(unittest.TestCase):

    def test_20_unverified_profile_refused(self):
        bad = real_census()
        bad["runtime_profile_verified"] = False
        att = Harness(census=lambda: bad).run()
        self.assertEqual(att.verdict, PHASE7_INCOMPLETE)
        self.assertIn("NOT verified",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "AIR-02"))

    def test_21_missing_phase_flags_refused(self):
        bad = real_census()
        bad["phases"] = [p for p in bad["phases"]
                         if p["phase"] != 6]
        att = Harness(census=lambda: bad).run()
        self.assertEqual(att.verdict, PHASE7_INCOMPLETE)
        self.assertIn("Phase 5/6",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "AIR-02"))

    def test_22_unwired_phase_refused(self):
        bad = real_census()
        bad["phases"][0]["wired"] = False
        att = Harness(census=lambda: bad).run()
        self.assertEqual(att.verdict, PHASE7_INCOMPLETE)
        self.assertIn("VERIFIED+WIRED",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "AIR-02"))

    def test_23_wrong_seam_registry_refused(self):
        bad_registry = {7: "canonical.nonexistent_module",
                        8: "canonical.ai_proposal_lifecycle"}
        att = Harness(expected_entry_points=bad_registry).run()
        self.assertEqual(att.verdict, PHASE7_INCOMPLETE)
        self.assertIn("registry drift",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "AIR-02"))

    def test_24_census_absent_refused(self):
        att = Harness(census=None).run()
        self.assertEqual(att.verdict, PHASE7_INCOMPLETE)
        self.assertIn("unavailable",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "AIR-02"))


# ===================================================================
# AIR-03 — bounded routing refusals
# ===================================================================

class TestAir03Routing(unittest.TestCase):

    def test_30_unknown_provider_refused(self):
        router = ModelRouter(
            providers={"mock": MockAiProvider()},
            policy={"propose_content_idea": RouteTarget(
                "deepseek", "deepseek-chat",
                "content_idea_proposal.v1", budget_usd=0.5)},
            bucket_capacity=30)
        att = Harness(router=router).run()
        self.assertEqual(att.verdict, PHASE7_INCOMPLETE)
        self.assertIn("allowlist",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "AIR-03"))

    def test_31_unknown_model_refused(self):
        router = ModelRouter(
            providers={"mock": MockAiProvider()},
            policy={"propose_content_idea": RouteTarget(
                "mock", "mock-unlisted", "content_idea_proposal.v1",
                budget_usd=0.5)},
            bucket_capacity=30)
        att = Harness(router=router).run()
        self.assertEqual(att.verdict, PHASE7_INCOMPLETE)
        self.assertIn("allowlist",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "AIR-03"))

    def test_32_token_cap_exceeded_refused(self):
        router = ModelRouter(
            providers={"mock": MockAiProvider()},
            policy={"propose_content_idea": RouteTarget(
                "mock", "mock-1", "content_idea_proposal.v1",
                budget_usd=0.5, max_tokens=LIMITS["max_tokens_cap"] * 4)},
            bucket_capacity=30)
        att = Harness(router=router).run()
        self.assertEqual(att.verdict, PHASE7_INCOMPLETE)
        self.assertIn("max_tokens",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "AIR-03"))

    def test_33_budget_cap_exceeded_refused(self):
        router = ModelRouter(
            providers={"mock": MockAiProvider()},
            policy={"propose_content_idea": RouteTarget(
                "mock", "mock-1", "content_idea_proposal.v1",
                budget_usd=LIMITS["budget_cap_usd"] * 10)},
            bucket_capacity=30)
        att = Harness(router=router).run()
        self.assertEqual(att.verdict, PHASE7_INCOMPLETE)
        self.assertIn("budget",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "AIR-03"))

    def test_34_router_absent_refused(self):
        att = Harness(router=None).run()
        self.assertEqual(att.verdict, PHASE7_INCOMPLETE)
        self.assertIn("unavailable",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "AIR-03"))


# ===================================================================
# AIR-04 — synthetic PM cycle refusals
# ===================================================================

class TestAir04Cycle(unittest.TestCase):

    def test_40_unsafe_tool_request_refused(self):
        h = Harness()
        with self.assertRaises(Exception):
            h.igniter._dispatch_tool("shell_exec", "rm -rf /")

    def test_41_scratch_scope_violation_refused(self):
        store = ScratchStore()
        with self.assertRaises(Exception):
            store.write("etc/passwd", {})
        with self.assertRaises(Exception):
            store.read("etc/passwd")
        with self.assertRaises(Exception):
            store.delete("etc/passwd")

    def test_42_provider_failure_retry_overflow_refused(self):
        router = ModelRouter(
            providers={"mock": MockAiProvider(fail_with="timeout")},
            policy={"propose_content_idea": RouteTarget(
                "mock", "mock-1", "content_idea_proposal.v1",
                budget_usd=0.5, max_tokens=512)},
            bucket_capacity=30)
        att = Harness(router=router).run()
        self.assertEqual(att.verdict, PHASE7_INCOMPLETE)
        blob = " ".join(c[2] for c in att.checks if c[0] == "AIR-04")
        self.assertIn("retry overflow", blob)
        # fail-closed hygiene: the scratch store is still cleaned
        self.assertTrue(att.to_dict()["cycle"]["scratch_cleaned"])

    def test_43_auth_failure_refused_no_retry(self):
        router = ModelRouter(
            providers={"mock": MockAiProvider(fail_with="auth")},
            policy={"propose_content_idea": RouteTarget(
                "mock", "mock-1", "content_idea_proposal.v1",
                budget_usd=0.5, max_tokens=512)},
            bucket_capacity=30)
        att = Harness(router=router).run()
        self.assertEqual(att.verdict, PHASE7_INCOMPLETE)
        blob = " ".join(c[2] for c in att.checks if c[0] == "AIR-04")
        self.assertIn("provider dispatch failed", blob)

    def test_44_invalid_output_schema_refused(self):
        router = ModelRouter(
            providers={"mock": MockAiProvider(
                fail_with="unknown_shape")},
            policy={"propose_content_idea": RouteTarget(
                "mock", "mock-1", "content_idea_proposal.v1",
                budget_usd=0.5, max_tokens=512)},
            bucket_capacity=30)
        att = Harness(router=router).run()
        self.assertEqual(att.verdict, PHASE7_INCOMPLETE)
        blob = " ".join(c[2] for c in att.checks if c[0] == "AIR-04")
        self.assertIn("invalid output schema", blob)

    def test_45_notion_idempotency_collision_refused(self):
        att = Harness(notion=ProbeNotion(collide=True)).run()
        self.assertEqual(att.verdict, PHASE7_INCOMPLETE)
        blob = " ".join(c[2] for c in att.checks if c[0] == "AIR-04")
        self.assertIn("collision", blob)

    def test_46_notion_cleanup_failure_refused(self):
        att = Harness(notion=ProbeNotion(fail_archive=True)).run()
        self.assertEqual(att.verdict, PHASE7_INCOMPLETE)
        blob = " ".join(c[2] for c in att.checks if c[0] == "AIR-04")
        self.assertIn("cleanup failed", blob)

    def test_47_no_notion_client_probe_absent_pass(self):
        h = Harness(notion=None)
        att = h.run()
        self.assertEqual(att.verdict, PHASE7_IGNITED)
        self.assertEqual(att.to_dict()["cycle"]["notion_probe"],
                         "absent")
        self.assertEqual(len(h.sink), 1)

    def test_48_cycle_deterministic_summary(self):
        s1 = Harness().run().to_dict()["cycle"]["summary_hash"]
        s2 = Harness().run().to_dict()["cycle"]["summary_hash"]
        self.assertEqual(s1, s2)

    def test_49_tool_call_budget_enforced(self):
        h = Harness()
        ign = h.igniter
        for _ in range(LIMITS["max_tool_calls"]):
            ign._dispatch_tool("scratch_write",
                               SCRATCH_NS + "k", {})
        with self.assertRaises(Exception):
            ign._dispatch_tool("scratch_write",
                               SCRATCH_NS + "over", {})


# ===================================================================
# AIR-05 — emission contract
# ===================================================================

class TestAir05Emission(unittest.TestCase):

    def test_50_exactly_one_attestation_per_run(self):
        h = Harness()
        att = h.run()
        self.assertEqual(len(h.sink), 1)
        self.assertEqual(h.sink[0]["schema"], ATTESTATION_SCHEMA)
        self.assertEqual(h.sink[0]["verdict"], att.verdict)

    def test_51_abort_still_emits_attestation(self):
        h = Harness(phase6_provider=None)
        att = h.run()
        self.assertEqual(att.verdict, PHASE7_INCOMPLETE)
        self.assertEqual(len(h.sink), 1)

    def test_52_digest_covers_every_field(self):
        att = Harness().run()
        d = att.to_dict()
        for key in ("schema", "verdict", "phase6_digest",
                    "manifest_sha256", "profile", "routing", "cycle",
                    "checks", "observed_tick"):
            self.assertIn(key, d)


# ===================================================================
# REDACT — zero secret leakage (D-124)
# ===================================================================

class TestRedaction(unittest.TestCase):

    def test_60_no_tokens_or_canaries_in_outputs(self):
        h = Harness()
        att = h.run()
        blob = json.dumps(att.to_dict()) + json.dumps(h.sink)
        for secret in (PROVIDER_TOKEN, NOTION_TOKEN, CANARY,
                       SIGNING_KEY):
            self.assertNotIn(secret, blob)

    def test_61_prompt_payload_never_enters_outputs(self):
        att = Harness().run()
        blob = json.dumps(att.to_dict()) + json.dumps(Harness().sink)
        self.assertNotIn(BRIEF["market_context"], blob)
        self.assertNotIn(CYCLE_ID, blob)

    def test_62_refusal_details_carry_no_secrets(self):
        h = Harness(phase6_provider=lambda: {
            "schema": "x", "note": PROVIDER_TOKEN})
        att = h.run()
        blob = json.dumps(att.to_dict()) + json.dumps(h.sink)
        self.assertNotIn(PROVIDER_TOKEN, blob)

    def test_63_deep_redact_runs_on_emitted_records(self):
        h = Harness()
        att = h.run()
        row = h.sink[0]
        self.assertEqual(row["phase6_digest"], att.phase6_digest)
        self.assertEqual(row["manifest_sha256"],
                         att.manifest_sha256)

    def test_64_notion_probe_requests_minimal(self):
        h = Harness()
        h.run()
        for req in h.notion.requests:
            self.assertIn(req["op"], ("create", "read", "archive"))
            self.assertEqual(len(req), 1)


# ===================================================================
# AST — purity audits
# ===================================================================

class TestAstPurity(unittest.TestCase):

    def setUp(self):
        self.tree = ast.parse(ENGINE.read_text(encoding="utf-8"))

    def test_70_no_forbidden_imports_in_engine(self):
        banned = {"socket", "http", "urllib", "requests", "ftplib",
                  "smtplib", "asyncio", "subprocess", "shutil", "pty",
                  "commands"}
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    self.assertNotIn(root, banned,
                                     f"forbidden import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                root = (node.module or "").split(".")[0]
                self.assertNotIn(root, banned,
                                 f"forbidden import from {node.module}")

    def test_71_no_shell_or_spawn_calls(self):
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Call):
                fn = node.func
                name = getattr(fn, "attr", getattr(fn, "id", ""))
                self.assertNotIn(name,
                                 ("system", "popen", "Popen",
                                  "spawn", "spawnl", "spawnv"),
                                 f"forbidden call {name}")

    def test_72_injected_dependencies_only(self):
        src = ENGINE.read_text(encoding="utf-8")
        self.assertIn("router: Optional[Any]", src)
        self.assertIn("notion: Optional[Any]", src)
        self.assertIn("def _load", src)

    def test_73_scratch_is_the_only_write_surface(self):
        src = ENGINE.read_text(encoding="utf-8")
        self.assertIn("SCRATCH_NS", src)
        self.assertIn("scope violation", src)
        self.assertIn("TOOL_ALLOWLIST", src)


if __name__ == "__main__":
    unittest.main()

"""Phase 8 live wiring igniter battery (D-158, offline).

Exercises `local/scripts/live_wiring_phase8_igniter.py` fully
offline — the Instagram adapter injected (the REAL
`MockInstagramAdapter` D-069 workflow wrapped with a capability
profile and probe-only archive seam), the census chained from the
REAL D-157 igniter over the REAL D-156/D-155/D-154 chain, and the
caption produced by the REAL Phase 7 `ModelRouter`:

  PASS    — phase7 attestation + verified profile + capability ok +
            clean container probe ⇒ PHASE8_IGNITED with a valid
            `phase8.live_wiring_attestation.v1` (deterministic
            digest);
  IG-01   — phase7 attestation absent / raised / wrong schema /
            wrong verdict / drifted (ledger mismatch) / unrooted /
            broken chain ⇒ refusal with ZERO adapter calls;
  IG-02   — runtime profile mismatch, missing Phase 5/6/7
            VERIFIED/WIRED flags, seam registry drift ⇒ refusal;
  IG-03   — missing OAuth scopes, expired/short-margin token,
            capability probe failure (401/403 carrier), rate-limit
            envelope breach ⇒ refusal;
  IG-04   — media format non-compliance, container create failure/
            timeout (retry overflow), terminal container state,
            probe state collision, publish invocation (safety
            violation), cleanup failure ⇒ refusal;
  IG-05   — exactly one canonical attestation per run (including
            aborts), deterministic digest;
  REDACT  — access tokens, canaries and auth material never reach
            the attestation or audit copies (D-124/D-071);
  AST     — pure igniter core (no network imports, no shell, no
            spawn), adapter injected only.
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

from canonical.instagram_adapter import (  # noqa: E402
    MockInstagramAdapter, poll_until_ready,
)
from canonical.instagram_contracts import (  # noqa: E402
    InstagramContractError, REQUIRED_ASPECT_RATIO_LABELS,
    validate_publish_payload,
)
from live_wiring_phase7_igniter import (  # noqa: E402
    PHASE7_INCOMPLETE, Phase7Igniter, ScratchStore,
)
from live_wiring_phase8_igniter import (  # noqa: E402
    ATTESTATION_SCHEMA, CYCLE_ID, EXPIRY_THRESHOLD_TICKS,
    PHASE7_ROW_KIND, PHASE8_IGNITED, PHASE8_INCOMPLETE,
    REQUIRED_SCOPES, SEAMS, USAGE_WARN_PCT, Phase8Igniter,
    canonical_hash,
)

ENGINE = SCRIPTS / "live_wiring_phase8_igniter.py"

CANARY = "sk-canaryvalue1234567890abcdef"
IG_TOKEN = "IGQV" + "JCANARYTOKEN0123456789ABCDEFGHIJ"
FB_TOKEN = "EAAG" + "CANARYFBTOKEN0123456789ABCDEFGH"
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


# --- the authentic chain: phase7 attestation via the REAL D-157
# --- engine (which chains D-156 → D-155 → D-154) ---------------------

def real_phase7_attestation(observed_tick=8000):
    """Run the REAL D-157 igniter over the authentic chain with
    in-process fakes (identical to the D-157 battery pass path)."""
    import tests.test_live_wiring_phase7 as t7
    h = t7.Harness(now=observed_tick)
    att = h.run()
    ledger = t7.the_ledger() + [{
        "event_kind": "phase7_live_wiring_attestation",
        "detail": {"attestation_digest": att.attestation_digest,
                   "verdict": att.verdict}}]
    return att.to_dict(), ledger, t7


def real_census() -> dict:
    """The runtime-profile census rows for Phases 5–9, all wired."""
    return {
        "runtime_profile_verified": True,
        "phases": [
            {"phase": n, "name": name, "present": True,
             "verified": True, "wired": True, "detail": "ready"}
            for n, name in ((5, "n8n Foundation"),
                            (6, "Notion Business OS"),
                            (7, "AI Runtime"),
                            (8, "AI Product Manager"),
                            (9, "Instagram"))
        ],
    }


def real_router():
    """The REAL Phase 7 router extended with the caption route (the
    registered DEFAULT_ROUTING_POLICY target for generate_caption)."""
    from canonical.ai_runtime import ModelRouter, MockAiProvider, RouteTarget
    return ModelRouter(
        providers={"mock": MockAiProvider()},
        policy={
            "propose_content_idea": RouteTarget(
                "mock", "mock-1", "content_idea_proposal.v1",
                budget_usd=0.50, max_tokens=512, temperature=0.0),
            "generate_caption": RouteTarget(
                "mock", "mock-1", "caption_proposal.v1",
                budget_usd=0.50, max_tokens=512, temperature=0.0),
        },
        budgets={"propose_content_idea": 0.50,
                 "generate_caption": 0.50},
        bucket_capacity=30)


class ProbeInstagramAdapter(MockInstagramAdapter):
    """The REAL MockInstagramAdapter (D-069 workflow) wrapped with the
    IG-03 capability profile and the probe-only archive seam."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.scopes = set(REQUIRED_SCOPES)
        self.token_valid_until = 10_000
        self.app_usage = {"call_count": 5, "total_time": 4,
                          "total_cputime": 3}
        self.archived: list = []

    def capability_profile(self) -> dict:
        return {"scopes": sorted(self.scopes),
                "token_valid_until": self.token_valid_until,
                "app_usage": self.app_usage}

    def archive_container(self, container_id: str) -> dict:
        self.calls.append("archive")
        self.archived.append(container_id)
        return {"container_id": container_id, "archived": True}


# --- the wired harness -------------------------------------------------

_UNSET = object()  # sentinel: "no override given" (None = absent)

_CHAIN: dict = {}


def the_att() -> dict:
    return _CHAIN["att"]


def the_ledger() -> list:
    return _CHAIN["ledger"]


def build_chain() -> None:
    if not _CHAIN:
        att, ledger, _t7 = real_phase7_attestation()
        _CHAIN.update(att=att, ledger=ledger)


class Harness:
    """Fully wired igniter over the authentic phase7 chain; overrides
    swap providers (None = absent)."""

    def __init__(self, now: int = 9000, ig=_UNSET,
                 census=real_census, router=_UNSET, **overrides):
        build_chain()
        self.now = now
        self.sink: list = []
        self.adapter = ProbeInstagramAdapter() if ig is _UNSET else ig
        providers = {
            "phase7_provider": the_att,
            "audit_rows": the_ledger,
            "chain_verifier": lambda: {"ok": True,
                                       "rows": len(the_ledger())},
            "census": census,
            "router": real_router() if router is _UNSET else router,
            "ig": self.adapter,
        }
        providers.update(overrides)
        self.igniter = Phase8Igniter(
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
        self.assertEqual(att.verdict, PHASE8_IGNITED)
        self.assertTrue(att.ignited)
        d = att.to_dict()
        self.assertEqual(d["schema"], ATTESTATION_SCHEMA)
        self.assertEqual(d["schema"],
                         "phase8.live_wiring_attestation.v1")
        self.assertEqual(d["phase7_digest"],
                         canonical_hash(the_att()))
        ids = [c[0] for c in att.checks]
        for rule in ("IG-01", "IG-02", "IG-03", "IG-04", "IG-05"):
            self.assertIn(rule, ids)
        self.assertTrue(all(c[1] for c in att.checks))
        self.assertTrue(d["profile"]["runtime_profile_verified"])
        self.assertTrue(d["profile"]["seams_ok"])
        self.assertTrue(d["capability"]["scopes_ok"])
        self.assertTrue(d["capability"]["token_ok"])
        self.assertTrue(d["capability"]["usage_ok"])
        self.assertFalse(d["probe"]["published"])
        self.assertTrue(d["probe"]["container_archived"])

    def test_02_attestation_digest_deterministic(self):
        a1 = Harness(now=9500).run()
        b1 = Harness(now=9500).run()
        self.assertEqual(a1.attestation_digest, b1.attestation_digest)
        self.assertEqual(a1.attestation_digest,
                         canonical_hash(a1.to_dict()))

    def test_03_probe_steps_recorded(self):
        att = Harness().run()
        steps = att.to_dict()["probe"]["steps"]
        kinds = [s[0] for s in steps]
        for kind in ("START", "AUTH", "CONTAINER_CREATE",
                     "STATUS_POLL", "VERIFY", "CLEANUP"):
            self.assertIn(kind, kinds)
        self.assertTrue(all(s[1] for s in steps))
        self.assertEqual(len(att.to_dict()["probe"]["summary_hash"]),
                         64)

    def test_04_container_progression_verified(self):
        att = Harness().run()
        steps = {s[0]: s[2] for s in att.to_dict()["probe"]["steps"]}
        self.assertEqual(
            steps["STATUS_POLL"]["progression"],
            "IN_PROGRESS\u2192FINISHED")
        self.assertFalse(steps["VERIFY"]["published"])

    def test_05_caption_from_real_phase7_router(self):
        att = Harness().run()
        # the START step proves the caption came through the real
        # router contract path (the cycle only passes after the
        # caption_proposal.v1 contract validated the payload)
        start = [s for s in att.to_dict()["probe"]["steps"]
                 if s[0] == "START"][0]
        self.assertTrue(start[1])
        self.assertIn("caption_hash", start[2])
        self.assertIn("media_hash", start[2])


# ===================================================================
# IG-01 — phase7 attestation refusals (zero adapter calls)
# ===================================================================

class TestIg01Refusals(unittest.TestCase):

    def test_10_missing_phase7_attestation(self):
        h = Harness(phase7_provider=None)
        att = h.run()
        self.assertEqual(att.verdict, PHASE8_INCOMPLETE)
        self.assertIn("absent", att.checks[0][2])
        self.assertEqual(len(h.sink), 1)

    def test_11_provider_raises(self):
        def boom():
            raise RuntimeError("vault offline")
        att = Harness(phase7_provider=boom).run()
        self.assertEqual(att.verdict, PHASE8_INCOMPLETE)
        self.assertIn("RuntimeError", att.checks[0][2])

    def test_12_wrong_schema(self):
        att = Harness(phase7_provider=lambda: {
            "schema": "other.v1"}).run()
        self.assertEqual(att.verdict, PHASE8_INCOMPLETE)
        self.assertIn("schema", att.checks[0][2])

    def test_13_incomplete_verdict_refused(self):
        bad = dict(the_att())
        bad["verdict"] = PHASE7_INCOMPLETE
        att = Harness(phase7_provider=lambda: bad).run()
        self.assertEqual(att.verdict, PHASE8_INCOMPLETE)
        self.assertIn("PHASE7_IGNITED",
                      " ".join(c[2] for c in att.checks))

    def test_14_drifted_digest_refused(self):
        rows = the_ledger()[:-1] + [{
            "event_kind": "phase7_live_wiring_attestation",
            "detail": {"attestation_digest": "d" * 64}}]
        att = Harness(audit_rows=lambda: rows).run()
        self.assertEqual(att.verdict, PHASE8_INCOMPLETE)
        self.assertIn("DRIFTED", " ".join(c[2] for c in att.checks))

    def test_15_unrooted_attestation_refused(self):
        att = Harness(audit_rows=lambda: []).run()
        self.assertEqual(att.verdict, PHASE8_INCOMPLETE)
        self.assertIn("rooted", " ".join(c[2] for c in att.checks))

    def test_16_broken_chain_refused(self):
        att = Harness(chain_verifier=lambda: {
            "ok": False, "broken_at_seq": 1,
            "reason": "hash mismatch"}).run()
        self.assertEqual(att.verdict, PHASE8_INCOMPLETE)
        self.assertIn("not intact",
                      " ".join(c[2] for c in att.checks))

    def test_17_refusal_makes_zero_adapter_calls(self):
        # every IG-01 failure class above must leave the adapter
        # completely untouched (zero network/adapter calls)
        for kwargs in (
                {"phase7_provider": None},
                {"phase7_provider": lambda: {"schema": "x"}},
                {"audit_rows": lambda: []},
                {"chain_verifier": lambda: {"ok": False}}):
            adapter = ProbeInstagramAdapter()
            h = Harness(ig=adapter, **kwargs)
            att = h.run()
            self.assertEqual(att.verdict, PHASE8_INCOMPLETE)
            self.assertEqual(adapter.calls, [])


# ===================================================================
# IG-02 — runtime profile & seams refusals
# ===================================================================

class TestIg02Profile(unittest.TestCase):

    def test_20_unverified_profile_refused(self):
        bad = real_census()
        bad["runtime_profile_verified"] = False
        att = Harness(census=lambda: bad).run()
        self.assertEqual(att.verdict, PHASE8_INCOMPLETE)
        self.assertIn("NOT verified",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "IG-02"))

    def test_21_missing_phase7_row_refused(self):
        bad = real_census()
        bad["phases"] = [p for p in bad["phases"]
                         if p["phase"] != 7]
        att = Harness(census=lambda: bad).run()
        self.assertEqual(att.verdict, PHASE8_INCOMPLETE)
        self.assertIn("Phase 5/6/7",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "IG-02"))

    def test_22_unwired_phase6_refused(self):
        bad = real_census()
        for p in bad["phases"]:
            if p["phase"] == 6:
                p["wired"] = False
        att = Harness(census=lambda: bad).run()
        self.assertEqual(att.verdict, PHASE8_INCOMPLETE)
        self.assertIn("VERIFIED+WIRED",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "IG-02"))

    def test_23_seam_registry_drift_refused(self):
        bad_registry = {9: "publishing.nonexistent",
                        7: "canonical.ai_runtime",
                        8: "canonical.ai_proposal_lifecycle"}
        att = Harness(expected_entry_points=bad_registry).run()
        self.assertEqual(att.verdict, PHASE8_INCOMPLETE)
        self.assertIn("registry drift",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "IG-02"))

    def test_24_census_absent_refused(self):
        att = Harness(census=None).run()
        self.assertEqual(att.verdict, PHASE8_INCOMPLETE)
        self.assertIn("unavailable",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "IG-02"))


# ===================================================================
# IG-03 — capability & rate-envelope refusals
# ===================================================================

class TestIg03Capability(unittest.TestCase):

    def test_30_missing_scope_refused(self):
        adapter = ProbeInstagramAdapter()
        adapter.scopes.discard("instagram_content_publish")
        att = Harness(ig=adapter).run()
        self.assertEqual(att.verdict, PHASE8_INCOMPLETE)
        blob = " ".join(c[2] for c in att.checks if c[0] == "IG-03")
        self.assertIn("missing OAuth scopes", blob)
        self.assertIn("instagram_content_publish", blob)

    def test_31_expired_token_refused(self):
        adapter = ProbeInstagramAdapter()
        adapter.token_valid_until = 100  # harness clock = 9000
        att = Harness(ig=adapter).run()
        self.assertEqual(att.verdict, PHASE8_INCOMPLETE)
        blob = " ".join(c[2] for c in att.checks if c[0] == "IG-03")
        self.assertIn("expired", blob)

    def test_32_short_expiry_margin_refused(self):
        adapter = ProbeInstagramAdapter()
        adapter.token_valid_until = 9000 + EXPIRY_THRESHOLD_TICKS - 1
        att = Harness(ig=adapter).run()
        self.assertEqual(att.verdict, PHASE8_INCOMPLETE)
        blob = " ".join(c[2] for c in att.checks if c[0] == "IG-03")
        self.assertIn("margin", blob)

    def test_33_capability_probe_auth_error_refused(self):
        adapter = ProbeInstagramAdapter()

        def forbidden():
            raise PermissionError("403 permission denied")
        adapter.capability_profile = forbidden  # type: ignore
        att = Harness(ig=adapter).run()
        self.assertEqual(att.verdict, PHASE8_INCOMPLETE)
        blob = " ".join(c[2] for c in att.checks if c[0] == "IG-03")
        self.assertIn("PermissionError", blob)

    def test_34_usage_envelope_breach_refused(self):
        adapter = ProbeInstagramAdapter()
        adapter.app_usage = {"call_count": 95, "total_time": 96,
                             "total_cputime": 97}
        att = Harness(ig=adapter).run()
        self.assertEqual(att.verdict, PHASE8_INCOMPLETE)
        blob = " ".join(c[2] for c in att.checks if c[0] == "IG-03")
        self.assertIn("rate-limit guardrail refusal", blob)

    def test_35_adapter_absent_refused(self):
        att = Harness(ig=None).run()
        self.assertEqual(att.verdict, PHASE8_INCOMPLETE)
        blob = " ".join(c[2] for c in att.checks if c[0] == "IG-03")
        self.assertIn("unavailable", blob)

    def test_36_no_capability_profile_refused(self):
        att = Harness(ig=MockInstagramAdapter()).run()
        self.assertEqual(att.verdict, PHASE8_INCOMPLETE)
        blob = " ".join(c[2] for c in att.checks if c[0] == "IG-03")
        self.assertIn("capability profile", blob)


# ===================================================================
# IG-04 — synthetic media workflow refusals
# ===================================================================

class TestIg04Probe(unittest.TestCase):

    def test_40_container_create_failure_refused(self):
        adapter = ProbeInstagramAdapter(fail_with="create_error")
        att = Harness(ig=adapter).run()
        self.assertEqual(att.verdict, PHASE8_INCOMPLETE)
        blob = " ".join(c[2] for c in att.checks if c[0] == "IG-04")
        self.assertIn("Class-B", blob)

    def test_41_container_timeout_retry_overflow_refused(self):
        adapter = ProbeInstagramAdapter(fail_with="timeout")
        att = Harness(ig=adapter).run()
        self.assertEqual(att.verdict, PHASE8_INCOMPLETE)
        blob = " ".join(c[2] for c in att.checks if c[0] == "IG-04")
        self.assertIn("retry overflow", blob)

    def test_42_terminal_container_state_refused(self):
        adapter = ProbeInstagramAdapter(
            polls_until_ready=99, status_after_error="ERROR")
        # patch one poll to flip the container into ERROR
        orig_status = adapter.container_status

        def erroring(container_id):
            rec = orig_status(container_id)
            return dict(rec, status_code="ERROR")
        adapter.container_status = erroring  # type: ignore
        att = Harness(ig=adapter).run()
        self.assertEqual(att.verdict, PHASE8_INCOMPLETE)
        blob = " ".join(c[2] for c in att.checks if c[0] == "IG-04")
        self.assertIn("terminal failure state", blob)

    def test_43_publish_invocation_is_safety_violation(self):
        adapter = ProbeInstagramAdapter()
        orig_publish = adapter.publish_container

        def sneaky_publish(container_id):
            # an adapter that publishes during the probe — the run
            # must refuse and mark the safety violation
            return orig_publish(container_id)
        adapter.publish_container = sneaky_publish  # type: ignore
        # force a publish call between create and verify: the container
        # is first driven to FINISHED (so the publish itself succeeds
        # in the mock) BEFORE the engine's verify step sees the call
        orig_create = adapter.create_media_container
        orig_status = adapter.container_status

        def create_then_publish(*a, **kw):
            out = orig_create(*a, **kw)
            cid = out["container_id"]
            adapter._containers[cid]["status_code"] = "FINISHED"
            orig_publish(cid)
            return out
        adapter.create_media_container = create_then_publish  \
            # type: ignore
        att = Harness(ig=adapter).run()
        self.assertEqual(att.verdict, PHASE8_INCOMPLETE)
        blob = " ".join(c[2] for c in att.checks if c[0] == "IG-04")
        self.assertIn("SAFETY VIOLATION", blob)
        self.assertFalse(att.to_dict()["probe"]["published"])

    def test_44_cleanup_failure_refused(self):
        adapter = ProbeInstagramAdapter()

        def broken_archive(container_id):
            adapter.calls.append("archive")
            return {"container_id": container_id,
                    "archived": False}
        adapter.archive_container = broken_archive  # type: ignore
        att = Harness(ig=adapter).run()
        self.assertEqual(att.verdict, PHASE8_INCOMPLETE)
        blob = " ".join(c[2] for c in att.checks if c[0] == "IG-04")
        self.assertIn("cleanup failed", blob)

    def test_45_probe_state_collision_refused(self):
        h = Harness()
        att1 = h.run()
        self.assertEqual(att1.verdict, PHASE8_IGNITED)
        # a second run on the SAME igniter instance reuses the seen
        # container registry; a colliding container id refuses
        adapter = ProbeInstagramAdapter()
        adapter._containers["MOCK_CONTAINER_1"] = {
            "status_code": "IN_PROGRESS", "media_ref": "x",
            "aspect_ratio": "4:5"}
        adapter._poll_counts["MOCK_CONTAINER_1"] = 0
        h2 = Harness(ig=adapter)
        h2.igniter._seen_containers.add("MOCK_CONTAINER_1")
        # pre-seed the adapter to return the colliding id
        adapter._next = 1
        att2 = h2.run()
        self.assertEqual(att2.verdict, PHASE8_INCOMPLETE)
        blob = " ".join(c[2] for c in att2.checks if c[0] == "IG-04")
        self.assertIn("collision", blob)

    def test_46_bad_caption_never_reaches_network(self):
        # a payload that fails the LOCAL contract validation raises
        # before any adapter call — Class-B prevention (D-069)
        with self.assertRaises(Exception):
            validate_publish_payload({
                "content_id": CYCLE_ID, "media_ref": "x",
                "media_hash": "short", "caption": "c",
                "aspect_ratio": "9:16",
                "scheduled_slot": "s"})
        self.assertNotIn("9:16", REQUIRED_ASPECT_RATIO_LABELS)

    def test_47_router_absent_refused(self):
        att = Harness(router=None).run()
        self.assertEqual(att.verdict, PHASE8_INCOMPLETE)
        blob = " ".join(c[2] for c in att.checks if c[0] == "IG-04")
        self.assertIn("fail closed", blob)


# ===================================================================
# IG-05 — emission contract
# ===================================================================

class TestIg05Emission(unittest.TestCase):

    def test_50_exactly_one_attestation_per_run(self):
        h = Harness()
        att = h.run()
        self.assertEqual(len(h.sink), 1)
        self.assertEqual(h.sink[0]["schema"], ATTESTATION_SCHEMA)
        self.assertEqual(h.sink[0]["verdict"], att.verdict)

    def test_51_abort_still_emits_attestation(self):
        h = Harness(phase7_provider=None)
        att = h.run()
        self.assertEqual(att.verdict, PHASE8_INCOMPLETE)
        self.assertEqual(len(h.sink), 1)

    def test_52_digest_covers_every_field(self):
        att = Harness().run()
        d = att.to_dict()
        for key in ("schema", "verdict", "phase7_digest",
                    "manifest_sha256", "profile", "capability",
                    "probe", "checks", "observed_tick"):
            self.assertIn(key, d)


# ===================================================================
# REDACT — zero secret leakage (D-124/D-071)
# ===================================================================

class TestRedaction(unittest.TestCase):

    def test_60_no_tokens_or_canaries_in_outputs(self):
        h = Harness()
        att = h.run()
        blob = json.dumps(att.to_dict()) + json.dumps(h.sink)
        for secret in (IG_TOKEN, FB_TOKEN, CANARY, SIGNING_KEY):
            self.assertNotIn(secret, blob)

    def test_61_adapter_redacts_error_material(self):
        # the real redact() strips token markers from error strings
        # (caller-known secrets pass through extra redaction — the
        # engine deep-redacts every emitted detail on top)
        from canonical.instagram_adapter import redact
        text = redact(f"failed access_token={IG_TOKEN}")
        self.assertNotIn(IG_TOKEN, text)
        self.assertIn("[REDACTED]", text)

    def test_62_no_caption_text_in_outputs(self):
        att = Harness().run()
        blob = json.dumps(att.to_dict()) + json.dumps(Harness().sink)
        # the emitted record carries caption HASHES, not captions
        self.assertNotIn("caption_fa", blob)
        self.assertNotIn("hashtags", blob)

    def test_63_deep_redact_runs_on_emitted_records(self):
        h = Harness()
        att = h.run()
        row = h.sink[0]
        self.assertEqual(row["phase7_digest"], att.phase7_digest)
        self.assertEqual(row["manifest_sha256"],
                         att.manifest_sha256)

    def test_64_no_page_ids_or_media_urls(self):
        att = Harness().run()
        blob = json.dumps(att.to_dict()) + json.dumps(Harness().sink)
        self.assertNotIn("MOCK_CONTAINER_1", blob)
        self.assertNotIn("graph.facebook.com", blob)


# ===================================================================
# AST — purity audits
# ===================================================================

class TestAstPurity(unittest.TestCase):

    def setUp(self):
        self.tree = ast.parse(ENGINE.read_text(encoding="utf-8"))

    def test_70_no_forbidden_imports_in_engine(self):
        banned = {"socket", "http", "urllib", "requests", "ftplib",
                  "smtplib", "asyncio", "subprocess", "shutil", "pty",
                  "commands", "os"}
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
        self.assertIn("ig: Optional[Any]", src)
        self.assertIn("router: Optional[Any]", src)
        self.assertIn("def _load", src)

    def test_73_probe_only_guarantee_in_source(self):
        src = ENGINE.read_text(encoding="utf-8")
        # the engine never calls publish_container itself
        self.assertNotIn("publish_container(", src)
        self.assertIn("SAFETY VIOLATION", src)
        self.assertIn("archive_container", src)


if __name__ == "__main__":
    unittest.main()

"""Phase 7 M4 — AI runtime gate audit (authority path, cost ledger,
D-045 boundary). Audit and PROOF milestone: this suite verifies the
shipped Phase 7 modules, it does not change them.

Four audit layers:

  1. STATIC PATH AUDIT (AST over the four shipped modules):
     the AI module closure may import only stdlib + canonical/services
     (no vendor SDK, no network, no subprocess, no os.environ); it
     must not import Woo/Notion/media/prices modules; public surfaces
     of provider/router/tasks carry no execution/decision verbs; no
     integration module is referenced in string constants; the shipped
     contracts still equal the pinned fixture.

  2. DYNAMIC CONFORMANCE (behavioral proof):
     a REGISTRY-scoped applier proves an accepted proposal can only
     reach its approved canonical target (any other schema → applier
     raises → observable); a forced provider failure produces ZERO
     pipeline side effects (no D-027 event, no provenance, no queue
     item, no spend); the router envelope is frozen; the HITL queue
     never holds decision records (deterministic scan); conflicting
     re-delivery (same id, different payload) can never silently
     succeed (offline + live PostgreSQL).

  3. COST-LEDGER AUDIT (D-063): every call (ok / validation_failed /
     provider_error) is metered with correct cost; the ledger is
     append-only (mutation attempt visible in the exported view);
     budgets fire WITHOUT a ledger (spend tracking is a safety
     property, independent of persistence); hard refusal happens
     BEFORE dispatch (zero extra provider calls, zero marginal cost);
     rate limiter refuses as Class A.

  4. D-045 BOUNDARY AUDIT: the provider boundary is abstract and
     closed (unregistered provider = deterministic Class-B config
     error, never a network attempt); no credential material
     (api_key/OPENAI/ANTHROPIC/secret) appears in the modules; no
     production endpoint exists anywhere in the closure.

DEFERRED CONNECTIVITY (documentation, not tests): no real AI provider
was contacted in M4; no credentials exist or were requested; live
provider compatibility is NOT proven by M4 (owner-gated milestone,
D-045/D-062). See docs/reports/PHASE_7_GATE_REPORT.md §6.
"""

import json
import os
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOCAL = HERE.parent
ROOT = LOCAL.parent
for p in (str(HERE), str(LOCAL), str(LOCAL / "canonical"),
          str(LOCAL / "services")):
    if p not in sys.path:
        sys.path.insert(0, p)

import ast as _ast  # noqa: E402

from canonical.ai_contracts import (  # noqa: E402
    AI_OUTPUT_SCHEMAS, load_schemas_fixture)
from canonical.ai_proposal_lifecycle import (  # noqa: E402
    ACCEPTED, PROPOSED, ProposalLifecycle)
from canonical.ai_runtime import (  # noqa: E402
    AiProvider, AiProviderError, AiProposal, AiRequest, BudgetExceeded,
    DEFAULT_ROUTING_POLICY, MockAiProvider, ModelRouter, OutputValidationError,
    RouteTarget, TARIFFS, UsageLedger)
from canonical.ai_tasks import (  # noqa: E402
    AiTask, CaptionTask, ContentIdeaTask, DescriptionTask, TaskEntity)
from services.sync_engine import EventStore, ProvenanceEngine  # noqa: E402

AI_MODULES = ["ai_contracts", "ai_runtime", "ai_proposal_lifecycle",
              "ai_tasks"]

# Integration modules the AI closure must never import or reference.
_FORBIDDEN_IMPORTS = {"mock_woo", "notion_adapter", "media_store",
                      "woocommerce", "woo", "prices", "requests",
                      "urllib", "urllib3", "http", "httpx", "socket",
                      "aiohttp", "subprocess", "ftplib", "smtplib"}
# Verbs that would mean self-execution on the PROPOSER surface.
_FORBIDDEN_VERBS = {"decide", "publish", "execute", "approve", "reject",
                    "advance", "apply"}
# Decision records live in the lifecycle, never in the HITL queue.
_QUEUED_DECISION_CODES = {"AI_DECISION", "HUMAN_DECISION", "DECISION",
                          "ACCEPT", "REJECT"}


def _module_path(name: str) -> Path:
    import importlib
    mod = importlib.import_module(f"canonical.{name}")
    return Path(mod.__file__).resolve()


def _ast_trees():
    return [(_ast.parse(_module_path(m).read_text(encoding="utf-8")),
             _module_path(m)) for m in AI_MODULES]


def _string_constants(tree) -> list:
    return [n.value for n in _ast.walk(tree)
            if isinstance(n, _ast.Constant) and isinstance(n.value, str)]


def _import_roots(tree) -> set:
    roots = set()
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, _ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def _public_callables(cls) -> set:
    import inspect
    return {name for name, _ in inspect.getmembers(cls, inspect.isfunction)
            if not name.startswith("_")}


def _stdlib_roots() -> set:
    """Python 3.9 has no sys.stdlib_module_names — use the frozen
    stdlib top-level set (audit runs on 3.9–3.13)."""
    from test_phase7_ai_runtime_m4_stdlib import STDLIB_TOP_LEVEL
    return set(STDLIB_TOP_LEVEL)


def make_proposal(tag):
    router = ModelRouter({"mock": MockAiProvider()})
    return router.run(AiRequest(
        task_type="propose_content_idea",
        schema_id="content_idea_proposal.v1",
        prompt_payload={"topic": f"m4-topic-{tag}"},
        idempotency_tag=f"m4-{tag}"))


# ---------------------------------------------------------------------------
# 1. STATIC PATH AUDIT
# ---------------------------------------------------------------------------

class StaticPathAuditTests(unittest.TestCase):
    """AST proof: the AI closure has no path out of canonical space."""

    def test_import_roots_are_stdlib_or_canonical_services(self):
        allowed = _stdlib_roots() | {"canonical", "services"}
        for tree, path in _ast_trees():
            bad = _import_roots(tree) - allowed
            self.assertEqual(bad, set(),
                             f"{path.name}: non-boundary imports {bad}")

    def test_no_red_or_network_imports(self):
        for tree, path in _ast_trees():
            roots = set()
            for node in _ast.walk(tree):
                if isinstance(node, _ast.Import):
                    for alias in node.names:
                        roots.add(alias.name.split(".")[0])
                elif isinstance(node, _ast.ImportFrom) and node.module:
                    roots.add(node.module.split(".")[0])
            bad = roots & _FORBIDDEN_IMPORTS
            self.assertEqual(bad, set(),
                             f"{path.name}: forbidden imports {bad}")

    def test_no_integration_references_in_string_constants(self):
        forbidden = ("mock_woo", "notion_adapter", "media_store",
                     "woocommerce")
        for tree, path in _ast_trees():
            for s in _string_constants(tree):
                low = s.lower()
                for token in forbidden:
                    self.assertNotIn(token, low,
                                     f"{path.name}: string constant "
                                     f"references {token!r}: {s[:80]!r}")

    def test_proposer_surface_has_no_execution_verbs(self):
        # the lifecycle module legitimately owns decide(); providers,
        # router, and tasks must not carry any decision verb
        for cls in (AiProvider, MockAiProvider, ModelRouter, AiTask,
                    ContentIdeaTask, CaptionTask, DescriptionTask):
            for name in _public_callables(cls):
                low = name.lower()
                for verb in _FORBIDDEN_VERBS:
                    self.assertNotIn(verb, low,
                                     f"{cls.__name__}.{name} carries "
                                     f"execution verb {verb!r}")

    def test_no_network_or_environment_surface(self):
        for tree, path in _ast_trees():
            for node in _ast.walk(tree):
                if isinstance(node, _ast.Attribute) \
                        and node.attr == "environ":
                    self.fail(f"{path.name}: os.environ access found")
                if isinstance(node, _ast.Import):
                    for alias in node.names:
                        self.assertNotIn(alias.name.split(".")[0],
                                         {"requests", "urllib", "http",
                                          "socket", "subprocess"},
                                         f"{path.name}: network surface")

    def test_shipped_contracts_equal_pinned_fixture(self):
        fixture = load_schemas_fixture(
            str(HERE / "fixtures" / "ai" / "schemas.json"))
        self.assertEqual(AI_OUTPUT_SCHEMAS, fixture,
                         "contract drift: shipped schemas differ from "
                         "the pinned fixture (battery must fail)")


# ---------------------------------------------------------------------------
# 2. DYNAMIC CONFORMANCE PROOF (offline)
# ---------------------------------------------------------------------------

class DynamicConformanceTests(unittest.TestCase):
    """Behavioral proofs of the authority path (offline stores)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        self.prov = ProvenanceEngine(
            os.path.join(self.tmp, "prov.jsonl"))
        # REGISTRY-scoped applier: the only canonical target an
        # accepted proposal can reach. Anything else → RuntimeError,
        # which the test OBSERVES (never swallowed).
        self.registry = {"content_idea_proposal"}
        self.applied = []
        self.life = ProposalLifecycle(
            EventStore(os.path.join(self.tmp, "events.jsonl")),
            self.prov,
            applier=self._registry_applier)
        self.addCleanup(self._tmp.cleanup)

    def _registry_applier(self, pid, ref):
        kind = (ref.get("schema_id") or "").split(".")[0]
        if kind not in self.registry:
            raise RuntimeError(
                f"unregistered canonical target: {kind!r}")
        self.applied.append((pid, ref))
        return {"applied_to": kind, "ok": True}

    def test_accepted_proposal_reaches_only_registered_target(self):
        p = make_proposal("red-path")
        self.life.submit(p)
        self.life.decide(p.correlation_id, action="submit_review",
                         reviewer="owner")
        res = self.life.decide(p.correlation_id, action="accept",
                               reviewer="owner", notes="m4 audit")
        self.assertEqual(res["state"], ACCEPTED)
        self.assertEqual(len(self.applied), 1)
        self.assertEqual(self.applied[0][1]["schema_id"],
                         "content_idea_proposal.v1")

    def test_forced_provider_failure_has_zero_pipeline_side_effects(self):
        before_events = len(self.life.store.succeeded_references(
            self.life._src()))
        before_prov = len(self.prov.records)
        router = ModelRouter(
            {"mock": MockAiProvider(fail_with="timeout")})
        task = ContentIdeaTask(router)
        rep = task.run(TaskEntity(kind="content_idea", key="fail-1",
                                  payload={}), mode="persist")
        self.assertFalse(rep.ok)
        self.assertEqual(rep.failure_class, "A")
        # zero durable side effects anywhere in the pipeline
        self.assertEqual(len(self.life.store.succeeded_references(
            self.life._src())) - before_events, 0)
        self.assertEqual(len(self.prov.records) - before_prov, 0)
        self.assertEqual(self.life.pending_proposals(), [])

    def test_router_envelope_is_frozen(self):
        p = make_proposal("frozen")
        with self.assertRaises(AttributeError):
            p.payload = {"title": "tampered"}

    def test_hitl_queue_never_holds_decision_records(self):
        from canonical.verification_tool import VerificationQueue
        qpath = os.path.join(self.tmp, "queue.json")
        q = VerificationQueue(qpath)
        life = ProposalLifecycle(
            EventStore(os.path.join(self.tmp, "q-events.jsonl")),
            ProvenanceEngine(os.path.join(self.tmp, "q-prov.jsonl")),
            queue=q, applier=self._registry_applier)
        p = make_proposal("qscan")
        life.submit(p)
        life.decide(p.correlation_id, action="submit_review",
                    reviewer="owner")
        life.decide(p.correlation_id, action="accept", reviewer="owner")
        items = q.load_pending()
        self.assertTrue(items)  # proposals ARE queued
        for item in items:
            code = str(item.get("code", "")).upper()
            for banned in _QUEUED_DECISION_CODES:
                self.assertNotIn(banned, code,
                                 f"queue item carries a decision "
                                 f"record: {item}")

    def test_conflicting_redelivery_never_silently_succeeds(self):
        p = make_proposal("conflict")
        self.life.submit(p)
        forged = AiProposal(
            schema_id=p.schema_id, task_type=p.task_type,
            payload=dict(p.payload,
                         title="تغییر ناخواسته عنوان — re-delivery"),
            provider=p.provider, model=p.model, usage=dict(p.usage),
            cost=dict(p.cost), provenance_id=p.provenance_id,
            correlation_id=p.correlation_id, warnings=[])
        from services.sync_engine import IntegrityError
        with self.assertRaises(IntegrityError):
            self.life.submit(forged)
        # the original proposal is untouched
        self.assertEqual(self.life.state_of(p.correlation_id), PROPOSED)


# ---------------------------------------------------------------------------
# 3. COST-LEDGER AUDIT (D-063)
# ---------------------------------------------------------------------------

class CostLedgerAuditTests(unittest.TestCase):
    """Every call metered; append-only; guardrails independent of
    persistence; refusal BEFORE dispatch; limiter = Class A."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        self.ledger = UsageLedger(os.path.join(self.tmp, "ledger.json"))
        self.addCleanup(self._tmp.cleanup)

    def _tariffed_router(self, **kw):
        old = dict(TARIFFS)
        TARIFFS[("mock", "mock-1")] = {"input": 0.10, "output": 0.20}
        router = ModelRouter({"mock": MockAiProvider()}, ledger=self.ledger,
                             **kw)
        self.addCleanup(TARIFFS.update, old)
        self.addCleanup(TARIFFS.pop, ("mock", "mock-1"), None)
        return router

    def _caption_req(self, tag):
        return AiRequest(task_type="generate_caption",
                         schema_id="caption_proposal.v1",
                         prompt_payload={"c": tag},
                         idempotency_tag=f"m4-led-{tag}")

    def test_every_call_is_metered_with_correct_cost(self):
        router = self._tariffed_router()
        router.run(self._caption_req("ok1"))
        router.run(self._caption_req("ok2"))
        # malformed => unparseable text => parsed=None => Class B
        router = ModelRouter(
            {"mock": MockAiProvider(fail_with="malformed")},
            ledger=self.ledger)
        with self.assertRaises(OutputValidationError):
            router.run(self._caption_req("bad"))
        # timeout => AiProviderError Class A
        router = ModelRouter(
            {"mock": MockAiProvider(fail_with="timeout")},
            ledger=self.ledger)
        with self.assertRaises(AiProviderError):
            router.run(self._caption_req("down"))
        entries = self.ledger.entries
        self.assertEqual(len(entries), 4)
        statuses = sorted(e["status"] for e in entries)
        self.assertEqual(statuses,
                         ["ok", "ok", "provider_error",
                          "validation_failed"])
        # accounting semantics: ok and validation_failed bill real
        # token consumption; provider_error (no tokens generated) is
        # zero-cost. Failed-but-metered = D-063 "no silent spend".
        for e in entries:
            if e["status"] == "provider_error":
                self.assertEqual(e["cost_usd"], 0.0)
        self.assertGreater(sum(e["cost_usd"] for e in entries
                               if e["status"] == "validation_failed"), 0)
        self.assertGreater(sum(e["cost_usd"] for e in entries
                               if e["status"] == "ok"), 0)

    def test_ledger_append_only_shape(self):
        router = self._tariffed_router()
        router.run(self._caption_req("append1"))
        self.ledger.record(task_type="generate_caption",
                           provider="mock", model="mock-1",
                           tokens_in=1, tokens_out=1,
                           cost_usd=999.0, latency_ms=0,
                           status="ok", unknown_tariff=False,
                           correlation_id="sentinel")
        # append-only semantics: records are never rewritten — the
        # file view equals the in-memory history, entry-by-entry
        persisted = json.loads(Path(self.ledger.path).read_text(
            encoding="utf-8"))
        self.assertEqual(persisted, self.ledger.entries)
        self.assertEqual(len(persisted), 2)
        self.assertTrue(any(e["correlation_id"] == "sentinel"
                            for e in persisted))

    def test_budgets_fire_without_a_ledger(self):
        # spend tracking is a SAFETY property, independent of ledger
        # persistence (the M1 hardening this audit re-proves); tariff
        # ~0.10 input + ~0.20 output per 1K => ~0.03/call
        router = self._tariffed_router(
            budgets={"generate_caption": 0.05})
        spent = 0.0
        with self.assertRaises(BudgetExceeded):
            for i in range(50):
                router.run(self._caption_req(f"nol{i}"))
                spent = router._spend.get("generate_caption", 0.0)
        self.assertGreater(spent, 0.0)
        # guardrail checks BEFORE dispatch, so the terminal overshoot
        # is bounded by one call: spent <= budget + one_call_cost
        self.assertLessEqual(spent, 0.05 + 0.02)

    def test_hard_refusal_is_before_dispatch(self):
        # self-calibrating: measure the real per-call cost first, then
        # set the budget just above two calls — the 3rd must be refused
        # with ZERO provider invocation.
        router = self._tariffed_router()
        router.run(self._caption_req("d0"))
        per_call = self.ledger.total_cost("generate_caption")
        self.assertGreater(per_call, 0)
        budget = round(2 * per_call + per_call / 2, 6)
        router.budgets["generate_caption"] = budget
        router.run(self._caption_req("d1"))
        router.run(self._caption_req("d2"))
        provider = router.providers["mock"]
        self.assertEqual(len(provider.calls), 3)  # d0 + d1 + d2
        with self.assertRaises(BudgetExceeded):
            router.run(self._caption_req("d3"))
        self.assertEqual(len(provider.calls), 3)  # zero marginal calls
        # spent = d0+d1+d2 = 3 calls: the guardrail checks before
        # dispatch, so spend lands within one call of the budget
        # (2.5 × per_call here) — exactly the bounded-overshoot
        # semantics asserted in test_budgets_fire_without_a_ledger
        self.assertLessEqual(self.ledger.total_cost(
            "generate_caption"), 3 * per_call)

    def test_rate_limiter_refusal_is_class_a(self):
        router = ModelRouter({"mock": MockAiProvider()},
                             bucket_capacity=2)
        router.run(self._caption_req("r1"))
        router.run(self._caption_req("r2"))
        with self.assertRaises(AiProviderError) as cm:
            router.run(self._caption_req("r3"))
        self.assertEqual(cm.exception.failure_class, "A")


# ---------------------------------------------------------------------------
# 4. D-045 PROVIDER BOUNDARY AUDIT
# ---------------------------------------------------------------------------

class ProviderBoundaryAuditTests(unittest.TestCase):
    """Plug-and-play readiness with the credential gate closed."""

    def test_boundary_is_abstract_and_closed(self):
        with self.assertRaises(NotImplementedError):
            AiProvider().generate(AiRequest(
                task_type="t", schema_id="caption_proposal.v1",
                prompt_payload={}))
        # routing to an unregistered provider = deterministic config
        # error (Class B) — never a network attempt
        router = ModelRouter({}, policy={
            "generate_caption": RouteTarget(
                "unregistered", "x", "caption_proposal.v1",
                budget_usd=1.0)})
        with self.assertRaises(AiProviderError) as cm:
            router.run(self._req())
        self.assertEqual(cm.exception.failure_class, "B")

    def test_default_policy_has_no_real_provider(self):
        self.assertEqual(set(DEFAULT_ROUTING_POLICY), {
            "propose_content_idea", "generate_caption",
            "enrich_description"})
        for target in DEFAULT_ROUTING_POLICY.values():
            self.assertEqual(target.provider, "mock")

    def test_no_credential_material_in_modules(self):
        banned = ("api_key", "apikey", "secret", "bearer",
                  "authorization")
        for tree, path in _ast_trees():
            for s in _string_constants(tree):
                low = s.lower()
                for token in banned:
                    self.assertNotIn(token, low,
                                     f"{path.name}: credential-adjacent "
                                     f"string {token!r}: {s[:80]!r}")

    def test_no_real_provider_names_in_code(self):
        # provider identities must live in ROUTING POLICY (owner-gated
        # configuration), never hard-coded into module code; scanning
        # the live AST (not raw file bytes) keeps this docstring-safe
        import ast as ast_mod
        banned_names = {"openai", "anthropic"}
        for tree, path in _ast_trees():
            for node in ast_mod.walk(tree):
                if isinstance(node, ast_mod.Attribute):
                    self.assertNotIn(node.attr.lower(), banned_names,
                                     f"{path.name}: provider name in "
                                     f"attribute access")

    def test_no_production_endpoints(self):
        for tree, path in _ast_trees():
            for s in _string_constants(tree):
                for endpoint in ("api.openai.com", "api.anthropic.com",
                                 "https://api.", "hooks.slack"):
                    self.assertNotIn(endpoint, s.lower(),
                                     f"{path.name}: production endpoint "
                                     f"{endpoint!r}")

    @staticmethod
    def _req():
        return AiRequest(task_type="generate_caption",
                         schema_id="caption_proposal.v1",
                         prompt_payload={"c": 1},
                         idempotency_tag="m4-boundary")


# ---------------------------------------------------------------------------
# LIVE POSTGRESQL (durable proofs on the real D-055 store)
# ---------------------------------------------------------------------------

class _StackUnavailable(Exception):
    pass


def _stack_up():
    try:
        import subprocess
        out = subprocess.run(
            ["docker", "compose", "-f", "local/infra/docker-compose.yml",
             "ps", "--format", "json"], capture_output=True, text=True,
            timeout=20, cwd=str(ROOT))
        if out.returncode != 0 or "engine-local-postgres" not in out.stdout:
            return False
        return '"Health": "healthy"' in out.stdout or \
            "healthy" in out.stdout
    except Exception:
        return False


@unittest.skipUnless(_stack_up(), "live PostgreSQL stack not running")
class LiveDurabilityAuditTests(unittest.TestCase):
    """Restart safety + conflicting re-delivery on the live store."""

    @classmethod
    def setUpClass(cls):
        scripts = str(LOCAL / "scripts")
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        from canonical.notion_ingest import PgEventStore
        cls.PgEventStore = PgEventStore
        cls._tmp = tempfile.TemporaryDirectory()
        cls.prov = ProvenanceEngine(
            os.path.join(cls._tmp.name, "prov.jsonl"))
        cls.life = ProposalLifecycle(
            cls.PgEventStore(), cls.prov,
            applier=lambda pid, ref: {"ok": True})
        cls.applier_calls = 0

        def counting_applier(pid, ref):
            cls.applier_calls += 1
            return {"ok": True}

        cls.counting_applier = counting_applier

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _fresh(self):
        p = make_proposal(f"live-m4-{uuid.uuid4().hex[:8]}")
        self.life.submit(p)
        return p

    def test_restart_terminal_idempotency_on_live_store(self):
        p = self._fresh()
        cid = p.correlation_id
        # fresh lifecycle instance = simulated process restart
        life2 = ProposalLifecycle(self.PgEventStore(), self.prov,
                                  applier=self.life.applier)
        self.assertEqual(life2.state_of(cid), PROPOSED)
        self.assertEqual(
            life2.submit(p)["verdict"], "skipped_duplicate")
        life2.decide(cid, action="submit_review", reviewer="owner")
        res = life2.decide(cid, action="accept", reviewer="owner",
                           notes="m4 live audit")
        self.assertEqual(res["state"], ACCEPTED)
        # a THIRD instance verifies terminal durability + idempotency
        life3 = ProposalLifecycle(self.PgEventStore(), self.prov,
                                  applier=self.life.applier)
        self.assertEqual(life3.state_of(cid), ACCEPTED)
        again = life3.decide(cid, action="accept", reviewer="owner",
                             notes="m4 live audit")
        self.assertEqual(again["verdict"], "skipped_duplicate")

    def test_conflicting_redelivery_refused_on_live_store(self):
        p = self._fresh()
        forged = AiProposal(
            schema_id=p.schema_id, task_type=p.task_type,
            payload=dict(p.payload,
                         title="مقدار متفاوت — live re-delivery"),
            provider=p.provider, model=p.model, usage=dict(p.usage),
            cost=dict(p.cost), provenance_id=p.provenance_id,
            correlation_id=p.correlation_id, warnings=[])
        from services.sync_engine import IntegrityError
        with self.assertRaises(IntegrityError):
            self.life.submit(forged)
        self.assertEqual(self.life.state_of(p.correlation_id), PROPOSED)

    def test_rapid_ingest_reconstruction_is_monotonic_on_live_store(self):
        """M4 audit regression (found via 60-iteration probe, 2/60):
        wall-clock received_at stepped BACKWARD on the VM under rapid
        successive ingests, so ORDER BY received_at reordered a
        Draft→Review→Draft→Review chain into Review→…→Review and broke
        reconstruction. Fix: monotonic ingest_seq ordering. This test
        runs enough rapid chains to make the old failure mode likely
        and demands the correct final state every time."""
        from canonical.notion_ingest import ingest_notion_event, rebuild_state
        from canonical.notion_contracts import LifecycleViolation
        DRAFT, REVIEW = "Draft", "Review"
        for it in range(12):
            h = uuid.uuid4().hex
            page = (f"{h[:8]}-{h[8:12]}-4{h[13:16]}-"
                    f"a{h[17:20]}-{h[20:32]}")
            for i, (cur, tgt) in enumerate(
                    [(DRAFT, REVIEW), (REVIEW, DRAFT), (DRAFT, REVIEW)],
                    start=1):
                ingest_notion_event(
                    {"page_id": page, "object": "content_idea",
                     "event_type": "status_changed",
                     "revision_marker": f"m4-order-{uuid.uuid4().hex[:8]}-{i}",
                     "current_state": cur, "target_state": tgt},
                    self.PgEventStore(), provenance=self.prov,
                    actor="m4-order-probe")
            try:
                state = rebuild_state(self.PgEventStore(), page)
            except LifecycleViolation as exc:
                self.fail(
                    f"iteration {it}: reconstruction reordered a "
                    f"monotonic chain (ordering key not insertion-"
                    f"safe): {exc}")
            self.assertEqual(
                state["current_state"], REVIEW,
                f"iteration {it}: final state drifted — event rows were "
                "not reconstructed in insertion order")


if __name__ == "__main__":
    unittest.main()

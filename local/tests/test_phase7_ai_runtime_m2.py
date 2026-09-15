"""Phase 7 M2 — proposal lifecycle & HITL round-trip tests.

Contract under test: local/canonical/ai_proposal_lifecycle.py
(D-064 Approved) — the state machine

    PROPOSED → IN_REVIEW → {ACCEPTED, REJECTED, MODIFIED_BY_HUMAN}

with every transition a durable D-027 event on the injected store, a
D-026 provenance record per human decision, the AI_GENERATED
provenance record advanced exactly once at terminal decision, and
terminal decisions immutable (identical re-decision = idempotent
skip, changed re-decision refused).

Layers:
  1. Offline state-machine tests (JSON EventStore, deterministic
     mock proposal, no network).
  2. Offline authority-boundary tests: API-shape, provider-surface,
     and import-graph assertions that AI can never self-advance a
     proposal.
  3. Live PostgreSQL round-trip tests (run only when the stack is
     up): proposal → IN_REVIEW → accept/reject/modify on the real
     D-027 event store, restart reconstruction, zero-data-loss and
     idempotency across runs.
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOCAL = HERE.parent
ROOT = LOCAL.parent
for p in (str(LOCAL), str(LOCAL / "canonical"), str(LOCAL / "services")):
    if p not in sys.path:
        sys.path.insert(0, p)

from canonical.ai_contracts import validate_output  # noqa: E402
from canonical.ai_proposal_lifecycle import (  # noqa: E402
    ACTIONS, PROPOSED, IN_REVIEW, ACCEPTED, REJECTED, MODIFIED_BY_HUMAN,
    TERMINAL, TRANSITIONS, ProposalLifecycle, ProposalStateError)
from canonical.ai_runtime import (  # noqa: E402
    AiRequest, MockAiProvider, ModelRouter)
from services.sync_engine import EventStore, ProvenanceEngine  # noqa: E402

VALID_CONTENT_IDEA = {
    "title": "پیشنهاد پاییزی: ست بافت مشکی",
    "hook": "چرا ست بافت مشکی هر پاییز برمی‌گردد؟",
    "platform_hints": ["instagram"],
    "product_refs": [],
    "proposed_initial_state": "Backlog",
}


def make_proposal(tag):
    """A validated, router-produced AiProposal (deterministic mock)."""
    router = ModelRouter({"mock": MockAiProvider()})
    return router.run(AiRequest(
        task_type="propose_content_idea",
        schema_id="content_idea_proposal.v1",
        prompt_payload={"topic": f"test-topic-{tag}"},
        idempotency_tag=f"m2-{tag}"))


def jsonl_path(tmpdir, name):
    return os.path.join(tmpdir, f"{name}.jsonl")


class OfflineStateMachineTests(unittest.TestCase):
    """Lifecycle semantics on the JSON EventStore (no live stack)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        self.prov = ProvenanceEngine(jsonl_path(self.tmp, "prov"))
        self.applied = []

        def applier(pid, ref):
            self.applied.append((pid, ref))
            return {"applied_to": "content_idea", "ok": True}

        self.life = ProposalLifecycle(
            EventStore(jsonl_path(self.tmp, "events")),
            self.prov, applier=applier)
        self.addCleanup(self._tmp.cleanup)

    def submit(self, tag):
        p = make_proposal(tag)
        self.life.submit(p)
        return p

    # -- legal paths ---------------------------------------------------

    def test_initial_state_proposed(self):
        p = self.submit("state0")
        self.assertEqual(self.life.state_of(p.correlation_id), PROPOSED)

    def test_submit_is_idempotent(self):
        p = self.submit("idem")
        self.assertEqual(self.life.submit(p)["verdict"],
                         "skipped_duplicate")

    def test_full_path_to_accepted(self):
        p = self.submit("acc")
        cid = p.correlation_id
        self.life.decide(cid, action="submit_review", reviewer="owner")
        self.assertEqual(self.life.state_of(cid), IN_REVIEW)
        res = self.life.decide(cid, action="accept", reviewer="owner",
                               notes="good idea")
        self.assertEqual(res["state"], ACCEPTED)
        self.assertEqual(res["verdict"], "new")
        # deterministic applier ran exactly once with the decision ref
        self.assertEqual(len(self.applied), 1)
        self.assertEqual(self.applied[0][0], cid)

    def test_accept_requires_review_first(self):
        p = self.submit("norev")
        with self.assertRaises(ProposalStateError) as cm:
            self.life.decide(p.correlation_id, action="accept",
                             reviewer="owner")
        self.assertEqual(cm.exception.from_state, PROPOSED)

    def test_reject_from_in_review(self):
        p = self.submit("rej")
        cid = p.correlation_id
        self.life.decide(cid, action="submit_review", reviewer="owner")
        res = self.life.decide(cid, action="reject", reviewer="owner",
                               notes="off-season")
        self.assertEqual(res["state"], REJECTED)
        self.assertEqual(len(self.applied), 0)  # reject never applies

    def test_modify_accept_carries_modified_payload(self):
        p = self.submit("mod")
        cid = p.correlation_id
        self.life.decide(cid, action="submit_review", reviewer="owner")
        modified = dict(VALID_CONTENT_IDEA,
                        title="پیشنهاد اصلاح‌شده: ست بافت مشکی")
        res = self.life.decide(cid, action="modify_accept",
                               reviewer="owner", notes="tweaked title",
                               modified_payload=modified)
        self.assertEqual(res["state"], MODIFIED_BY_HUMAN)
        (pid, ref), = self.applied
        self.assertEqual(ref["diff"]["modified_payload"]["title"],
                         modified["title"])

    def test_modify_accept_requires_payload(self):
        p = self.submit("modmiss")
        self.life.decide(p.correlation_id, action="submit_review",
                         reviewer="owner")
        with self.assertRaises(ProposalStateError):
            self.life.decide(p.correlation_id, action="modify_accept",
                             reviewer="owner", notes="no payload")

    def test_unknown_action_refused(self):
        p = self.submit("unk")
        with self.assertRaises(ProposalStateError):
            self.life.decide(p.correlation_id, action="publish",
                             reviewer="owner")
        self.assertNotIn("publish", ACTIONS)

    def test_unknown_proposal_refused(self):
        with self.assertRaises(KeyError):
            self.life.decide("aiprop-does-not-exist", action="accept",
                             reviewer="owner")

    def test_terminal_redecision_identical_is_idempotent(self):
        p = self.submit("idemterm")
        cid = p.correlation_id
        self.life.decide(cid, action="submit_review", reviewer="owner")
        self.life.decide(cid, action="accept", reviewer="owner",
                         notes="ok")
        before = len(self.prov.records)
        res = self.life.decide(cid, action="accept", reviewer="owner",
                               notes="ok")
        self.assertEqual(res["verdict"], "skipped_duplicate")
        self.assertEqual(len(self.prov.records), before)  # no dup record

    def test_terminal_redecision_changed_is_refused(self):
        p = self.submit("flip")
        cid = p.correlation_id
        self.life.decide(cid, action="submit_review", reviewer="owner")
        self.life.decide(cid, action="accept", reviewer="owner",
                         notes="ok")
        with self.assertRaises(ProposalStateError):
            self.life.decide(cid, action="reject", reviewer="owner",
                             notes="changed mind")

    def test_transition_matrix_shape(self):
        # every legal action from IN_REVIEW is terminal
        for (frm, act), to in TRANSITIONS.items():
            if frm == IN_REVIEW:
                self.assertIn(to, TERMINAL)
        self.assertEqual(set(TERMINAL),
                         {ACCEPTED, REJECTED, MODIFIED_BY_HUMAN})

    # -- provenance / D-026 ---------------------------------------------

    def test_provenance_advance_on_human_decision(self):
        p = self.submit("prov")
        cid = p.correlation_id
        self.life.decide(cid, action="submit_review", reviewer="owner")
        self.life.decide(cid, action="accept", reviewer="owner",
                         notes="approved")
        ai_recs = [r for r in self.prov.records
                   if r["source_type"] == "AI_GENERATED"]
        self.assertEqual(len(ai_recs), 1)
        self.assertEqual(ai_recs[0]["review_state"], "HUMAN_REVIEWED")

    def test_human_decision_provenance_captured(self):
        p = self.submit("hprov")
        cid = p.correlation_id
        self.life.decide(cid, action="submit_review", reviewer="owner")
        before = len(self.prov.records)
        self.life.decide(cid, action="reject", reviewer="sara",
                         notes="not this season")
        recs = self.prov.records[before:]
        self.assertTrue(all(r["source_type"] == "HUMAN_ENTERED"
                            for r in recs))
        self.assertTrue(all(r["actor"] == "sara" for r in recs))

    # -- restart reconstruction (durable-store only) --------------------

    def test_restart_reconstructs_from_store(self):
        p = self.submit("restart")
        cid = p.correlation_id
        self.life.decide(cid, action="submit_review", reviewer="owner")
        # a brand-new lifecycle instance over the SAME store files
        life2 = ProposalLifecycle(
            EventStore(jsonl_path(self.tmp, "events")),
            self.prov, applier=self.life.applier)
        self.assertEqual(life2.state_of(cid), IN_REVIEW)
        res = life2.decide(cid, action="accept", reviewer="owner",
                           notes="picked up after restart")
        self.assertEqual(res["state"], ACCEPTED)


class OfflineAuthorityBoundaryTests(unittest.TestCase):
    """No code path lets AI self-advance a proposal (D-050/D-064)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        self.life = ProposalLifecycle(
            EventStore(jsonl_path(self.tmp, "events")),
            ProvenanceEngine(jsonl_path(self.tmp, "prov")))
        self.addCleanup(self._tmp.cleanup)

    def test_no_auto_advance_transition_exists(self):
        # the machine's only mutation entry points are submit()
        # (PROPOSED only) and decide() (requires a keyword-only
        # reviewer) — nothing auto/silent/self-advancing exists
        import inspect
        sig = inspect.signature(ProposalLifecycle.decide)
        self.assertIn("reviewer", sig.parameters)
        self.assertEqual(sig.parameters["reviewer"].kind,
                         inspect.Parameter.KEYWORD_ONLY)
        for name in dir(ProposalLifecycle):
            if name.startswith("_"):
                continue
            low = name.lower()
            for bad in ("auto", "silent", "selfadvance",
                        "self_advance", "autopilot"):
                self.assertNotIn(bad, low)

    def test_decide_requires_reviewer(self):
        p = make_proposal("revreq")
        self.life.submit(p)
        # reviewer is keyword-only and required — a call without one
        # cannot even reach the transition logic
        with self.assertRaises(TypeError):
            self.life.decide(p.correlation_id, action="submit_review")

    def test_mock_provider_cannot_emit_decisions(self):
        # the provider surface carries no decision/advance method
        provider = MockAiProvider()
        for name in dir(provider):
            if not name.startswith("_"):
                self.assertNotIn("decid", name.lower())
                self.assertNotIn("advance", name.lower())
                self.assertNotIn("approve", name.lower())

    def test_import_graph_has_no_publication_or_woo_edge(self):
        # inspect every string literal in the module via AST (docstrings
        # included) for integration leakage into the AI runtime
        import ast as _ast
        import canonical.ai_proposal_lifecycle as mod
        tree = _ast.parse(
            Path(mod.__file__).read_text(encoding="utf-8"))
        literals = "\n".join(
            n.value for n in _ast.walk(tree)
            if isinstance(n, _ast.Constant)
            and isinstance(n.value, str))
        for forbidden in ("mock_woo", "notion_adapter",
                          "woocommerce"):
            self.assertNotIn(forbidden, literals)


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
class LivePostgresRoundTripTests(unittest.TestCase):
    """End-to-end on the live D-055 PostgreSQL event store."""

    @classmethod
    def setUpClass(cls):
        # notion_ingest imports seed_registry (psql helpers) which
        # lives in local/scripts — needed when this file runs standalone
        scripts = str(LOCAL / "scripts")
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        from canonical.notion_ingest import PgEventStore
        cls.PgEventStore = PgEventStore
        cls._tmp = tempfile.TemporaryDirectory()
        cls.prov = ProvenanceEngine(
            os.path.join(cls._tmp.name, "prov.jsonl"))
        cls.applied = []
        cls.life = ProposalLifecycle(
            cls.PgEventStore(), cls.prov,
            applier=lambda pid, ref: (cls.applied.append((pid, ref))
                                      or {"ok": True}))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _fresh_proposal(self, tag):
        # unique per run: the PG event store PERSISTS across runs, so
        # deterministic tags would collide with earlier executions
        import uuid
        unique = f"live-{tag}-{uuid.uuid4().hex[:8]}"
        p = make_proposal(unique)
        self.life.submit(p)
        return p

    def _applied_for(self, cid):
        return [x for x in self.applied if x[0] == cid]

    def test_full_accept_round_trip_live(self):
        p = self._fresh_proposal("acc")
        cid = p.correlation_id
        self.life.decide(cid, action="submit_review", reviewer="owner")
        res = self.life.decide(cid, action="accept", reviewer="owner",
                               notes="live accept")
        self.assertEqual(res["state"], ACCEPTED)
        self.assertEqual(res["verdict"], "new")
        self.assertEqual(len(self._applied_for(cid)), 1)
        self.assertEqual(self.life.state_of(cid), ACCEPTED)

    def test_reject_round_trip_live(self):
        p = self._fresh_proposal("rej")
        cid = p.correlation_id
        self.life.decide(cid, action="submit_review", reviewer="owner")
        res = self.life.decide(cid, action="reject", reviewer="owner",
                               notes="live reject")
        self.assertEqual(res["state"], REJECTED)
        self.assertEqual(self._applied_for(cid), [])  # never applies

    def test_retry_after_timeout_is_idempotent_live(self):
        p = self._fresh_proposal("idem")
        cid = p.correlation_id
        self.life.decide(cid, action="submit_review", reviewer="owner")
        r1 = self.life.decide(cid, action="accept", reviewer="owner",
                              notes="live idem")
        self.assertEqual(r1["verdict"], "new")
        # simulated retry of the same decision delivery
        r2 = self.life.decide(cid, action="accept", reviewer="owner",
                              notes="live idem")
        self.assertEqual(r2["verdict"], "skipped_duplicate")
        self.assertEqual(len(self._applied_for(cid)), 1)  # applier once

    def test_zero_data_loss_across_restart_live(self):
        p = self._fresh_proposal("restart")
        cid = p.correlation_id
        self.life.decide(cid, action="submit_review", reviewer="owner")
        # a new lifecycle over a fresh PgEventStore (new process sim)
        life2 = ProposalLifecycle(self.PgEventStore(), self.prov,
                                  applier=self.life.applier)
        self.assertEqual(life2.state_of(cid), IN_REVIEW)
        res = life2.decide(cid, action="accept", reviewer="owner",
                           notes="post-restart")
        self.assertEqual(res["state"], ACCEPTED)

    def test_invalid_schema_proposal_refused_class_b(self):
        # a payload violating the contract must never enter the store
        from canonical.ai_contracts import get_schema
        bad = dict(VALID_CONTENT_IDEA, proposed_initial_state="Review")
        errors = validate_output(get_schema(
            "content_idea_proposal.v1"), bad)
        self.assertIsNotNone(errors)  # Class-B evidence produced
        self.assertTrue(
            any("proposed_initial_state" in e for e in errors))
        # and the lifecycle API refuses raw (unvalidated) payloads
        with self.assertRaises(TypeError):
            self.life.submit({"correlation_id": "aiprop-forged",
                              "schema_id": "content_idea_proposal.v1",
                              "payload": bad})

    def test_proposal_resubmit_is_idempotent_live(self):
        # same proposal id + same content = skipped_duplicate; the
        # proposal is never double-counted in the store
        p = self._fresh_proposal("leak")
        self.assertEqual(self.life.submit(p)["verdict"],
                         "skipped_duplicate")


if __name__ == "__main__":
    unittest.main()

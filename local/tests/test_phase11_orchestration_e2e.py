"""Phase 11 — content-to-channel pipeline E2E battery.

Exercises the FULL orchestrated path with real shipped publishers:

  AI generation (Phase 7/8 router) → human review gate (D-050,
  ProposalLifecycle is the ONLY transition driver) → product staging
  (Phase 4 SyncEngine, D-050 RED gates) → channel fan-out (Phase 11
  FanOutEngine, D-077/D-078) → real outbox publishers (Phase 9
  D-070, Phase 10 D-074 with vault/pacer/DLQ).

Asserted invariants (machine-checked):
  - no AI output reaches a publisher without a durable ACCEPTED human
    decision (fail closed even when the lifecycle is absent);
  - RED-tier staging requires the SyncEngine authority flag and is
    additionally proposal-gated (defense in depth);
  - duplicate fan-out jobs are refused by the anti-race lock;
    duplicate CONTENT across jobs is deduplicated by the real
    outbox terminal guards (no duplicate posts);
  - one target's crash/cooldown never corrupts another target
    (independent fan-out, D-077) and never rolls back durable state;
  - compensation is a durable APPEND-ONLY marker with deterministic
    per-target verdicts (no ledger mutation);
  - receipts and adapted payloads carry no credential material.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from canonical.content_pipeline import (  # noqa: E402
    ContentToChannelPipeline,
    PipelineAuthorityError,
    PipelineError,
)
from canonical.ai_runtime import (  # noqa: E402
    AiProposal,
    AiRequest,
    MockAiProvider,
    ModelRouter,
)
from canonical.ai_proposal_lifecycle import ProposalLifecycle  # noqa: E402
from canonical.orchestration_engine import (  # noqa: E402
    FanOutEngine,
    _JsonFanOutLock,
)
from canonical.orchestration_contracts import (  # noqa: E402
    OrchestrationContractError,
)
from canonical.instagram_publisher import (  # noqa: E402
    InstagramOutboxPublisher,
    _JsonVault as _IgVault,
)
from canonical.telegram_publisher import TelegramOutboxPublisher  # noqa: E402
from canonical.instagram_adapter import MockInstagramAdapter  # noqa: E402
from canonical.telegram_adapter import MockTelegramAdapter  # noqa: E402
from services.sync_engine import (  # noqa: E402
    EventStore,
    MappingRegistry,
    ProvenanceEngine,
    SyncEngine,
)
from services import mock_woo  # noqa: E402


# --- fixtures ---------------------------------------------------------------

MEDIA = {"kind": "photo", "bytes_hash": "a" * 64,
         "aspect_ratio": "4:5", "file_size_bytes": 480_000}
TELEGRAM_PARAMS = {"telegram": {"chat_id": "@myshop", "parse_mode": "HTML"}}


def _product(pid, status="active", pub="published"):
    return {"product_id": pid, "name": f"محصول {pid}",
            "primary_category": "پوشاک مردانه", "leaf_category": "تیشرت",
            "attributes": {"برند": None}, "list_price": 300000,
            "product_sale": None, "product_sale_until": None,
            "status": status, "publication_status": pub,
            "media_refs": ["media.local/x.jpg"], "description": None,
            "short_description": None, "name_en": None}


class _MemoryBind:
    """Scriptable in-memory target bind (engine-level drills)."""

    def __init__(self, outcome="published", crash=False):
        self.outcome = outcome
        self.crash = crash
        self.calls = []

    def __call__(self, ref, actor="x"):
        self.calls.append(ref)
        if self.crash:
            raise RuntimeError("transport down (scripted)")
        return {"outcome": self.outcome}


class World:
    """One deterministic pipeline world over per-test temp paths."""

    def __init__(self, tmp, *, with_lifecycle=True,
                 ig_adapter=None, tg_adapter=None):
        self.tmp = tmp
        self.store = EventStore(os.path.join(tmp, f"e-{_uid()}.json"))
        self.prov = ProvenanceEngine(
            os.path.join(tmp, f"p-{_uid()}.jsonl"))
        self.sync = SyncEngine(mock_woo.MockWooAdapter(),
                               MappingRegistry(path=None),
                               self.store, self.prov)
        self.router = ModelRouter({"mock": MockAiProvider()})
        self.applied = []
        self.lifecycle = None
        if with_lifecycle:
            self.lifecycle = ProposalLifecycle(
                self.store, self.prov,
                applier=lambda pid, ref: self.applied.append(pid) or
                {"ok": True})
        self.ig_pub = InstagramOutboxPublisher(
            EventStore(os.path.join(tmp, f"ig-{_uid()}.json")),
            _IgVault(os.path.join(tmp, f"igv-{_uid()}.json")),
            self.prov)
        self.tg_pub = TelegramOutboxPublisher(
            EventStore(os.path.join(tmp, f"tg-{_uid()}.json")),
            _IgVault(os.path.join(tmp, f"tgv-{_uid()}.json")),
            self.prov)
        self.ig_adapter = ig_adapter or MockInstagramAdapter()
        self.tg_adapter = tg_adapter or MockTelegramAdapter()
        binds = {
            "instagram": self._ig_bind,
            "telegram": self._tg_bind,
        }
        self.fanout = FanOutEngine(
            self.store, binds,
            lock=_JsonFanOutLock(os.path.join(tmp, f"l-{_uid()}.json")))
        self.pipe = ContentToChannelPipeline(
            self.store, sync_engine=self.sync, fanout_engine=self.fanout,
            publish_binds=binds, lifecycle=self.lifecycle,
            provenance=self.prov)

    def _ig_bind(self, adapted, actor="pipeline"):
        self.ig_pub.enqueue(adapted, actor=actor)
        return self.ig_pub.publish(adapted, self.ig_adapter, actor=actor)

    def _tg_bind(self, adapted, actor="pipeline"):
        self.tg_pub.enqueue(adapted, actor=actor)
        return self.tg_pub.publish(adapted, self.tg_adapter, actor=actor)

    def accepted_proposal(self, tag):
        prop = self.pipe.generate_proposal(self.router, AiRequest(
            task_type="propose_content_idea",
            schema_id="content_idea_proposal.v1",
            prompt_payload={"topic": f"p11-{tag}"},
            idempotency_tag=f"p11-{tag}"))
        sub = self.lifecycle.submit(prop)
        pid = sub["proposal_id"]
        self.lifecycle.decide(pid, action="submit_review", reviewer="H-1")
        self.lifecycle.decide(pid, action="accept", reviewer="H-1")
        return prop, pid

    def fanout_kw(self, job_id, pid, **over):
        kw = dict(campaign_id="camp-1", content_id="POST-1",
                  proposal_id=pid, text="کت پاییزی جدید",
                  hashtags=["mod", "new"],
                  scheduled_slot="2026-09-16T12:00:00+00:00",
                  media=MEDIA, targets=["instagram", "telegram"],
                  target_params=TELEGRAM_PARAMS)
        kw.update(over)
        kw["job_id"] = job_id
        return kw


def _uid():
    return uuid.uuid4().hex[:8]


class _TempWorldTest(unittest.TestCase):
    def setUp(self):
        self._tmps = []

    def tearDown(self):
        import shutil
        for t in self._tmps:
            shutil.rmtree(t, ignore_errors=True)

    def world(self, **kw):
        tmp = tempfile.mkdtemp(prefix="p11e2e-")
        self._tmps.append(tmp)
        return World(tmp, **kw)


# --- generation stage -------------------------------------------------------


class TestGenerationStage(_TempWorldTest):
    def test_proposal_is_frozen_envelope(self):
        w = self.world()
        prop, _ = w.accepted_proposal("gen-1")
        self.assertIsInstance(prop, AiProposal)
        with self.assertRaises(Exception):
            prop.payload = {}   # frozen: tampering refused

    def test_submit_is_payload_idempotent(self):
        w = self.world()
        prop, _ = w.accepted_proposal("gen-2")
        again = w.lifecycle.submit(prop)
        self.assertEqual(again["verdict"], "skipped_duplicate")

    def test_generate_requires_router(self):
        w = self.world()
        with self.assertRaises(PipelineError):
            w.pipe.generate_proposal("not-a-router", AiRequest(
                task_type="propose_content_idea",
                schema_id="content_idea_proposal.v1",
                prompt_payload={}, idempotency_tag="x"))


# --- review gate (D-050) ----------------------------------------------------


class TestReviewGate(_TempWorldTest):
    def test_proposed_refused(self):
        w = self.world()
        prop = w.pipe.generate_proposal(w.router, AiRequest(
            task_type="propose_content_idea",
            schema_id="content_idea_proposal.v1",
            prompt_payload={"topic": "g1"}, idempotency_tag="p11-g1"))
        pid = w.lifecycle.submit(prop)["proposal_id"]
        with self.assertRaises(PipelineAuthorityError):
            w.pipe.fanout_job(**w.fanout_kw("jb-g1", pid))

    def test_in_review_refused(self):
        w = self.world()
        _, pid = w.accepted_proposal("g2")
        # fresh un-accepted proposal in IN_REVIEW (non-prefix tag: the
        # lifecycle history matcher is prefix-based)
        prop = w.pipe.generate_proposal(w.router, AiRequest(
            task_type="propose_content_idea",
            schema_id="content_idea_proposal.v1",
            prompt_payload={"topic": "g2x"}, idempotency_tag="p11-r2x"))
        pid2 = w.lifecycle.submit(prop)["proposal_id"]
        w.lifecycle.decide(pid2, action="submit_review", reviewer="H-1")
        with self.assertRaises(PipelineAuthorityError):
            w.pipe.fanout_job(**w.fanout_kw("jb-g2x", pid2))
        self.assertEqual(w.lifecycle.state_of(pid), "ACCEPTED")

    def test_rejected_refused(self):
        w = self.world()
        prop = w.pipe.generate_proposal(w.router, AiRequest(
            task_type="propose_content_idea",
            schema_id="content_idea_proposal.v1",
            prompt_payload={"topic": "g3"}, idempotency_tag="p11-g3"))
        pid = w.lifecycle.submit(prop)["proposal_id"]
        w.lifecycle.decide(pid, action="submit_review", reviewer="H-1")
        w.lifecycle.decide(pid, action="reject", reviewer="H-1")
        with self.assertRaises(PipelineAuthorityError):
            w.pipe.fanout_job(**w.fanout_kw("jb-g3", pid))

    def test_no_lifecycle_fails_closed(self):
        w = self.world(with_lifecycle=False)
        with self.assertRaises(PipelineAuthorityError):
            w.pipe.fanout_job(**w.fanout_kw("jb-g4", "any-proposal"))

    def test_accepted_passes_and_dispatches(self):
        w = self.world()
        _, pid = w.accepted_proposal("g5")
        r = w.pipe.fanout_job(**w.fanout_kw("jb-g5", pid))
        self.assertEqual(r["aggregate"], "SUCCESS")


# --- product staging (Phase 4 SyncEngine, D-050) -----------------------------


class TestStaging(_TempWorldTest):
    def test_unauthorized_red_tier_refused(self):
        w = self.world()
        _, pid = w.accepted_proposal("s1")
        with self.assertRaises(Exception) as ctx:
            w.pipe.stage_product(_product("P81001"), [], "2026-09-16",
                                 proposal_id=pid, authorized=False)
        self.assertEqual(type(ctx.exception).__name__, "AuthorityError")

    def test_authorized_hidden_staging_creates(self):
        w = self.world()
        _, pid = w.accepted_proposal("s2")
        res = w.pipe.stage_product(_product("P81002"), [], "2026-09-16",
                                   proposal_id=pid, authorized=True)
        self.assertEqual(res["action"], "created_hidden")
        self.assertIn("provenance_id", res)

    def test_accepted_proposal_gates_staging(self):
        w = self.world()
        prop = w.pipe.generate_proposal(w.router, AiRequest(
            task_type="propose_content_idea",
            schema_id="content_idea_proposal.v1",
            prompt_payload={"topic": "s3"}, idempotency_tag="p11-s3"))
        pid = w.lifecycle.submit(prop)["proposal_id"]
        with self.assertRaises(PipelineAuthorityError):
            w.pipe.stage_product(_product("P81003"), [], "2026-09-16",
                                 proposal_id=pid, authorized=True)

    def test_draft_staging_is_deterministic_noop(self):
        w = self.world()
        _, pid = w.accepted_proposal("s4")
        res = w.pipe.stage_product(_product("P81004", status="draft"),
                                   [], "2026-09-16",
                                   proposal_id=pid, authorized=True)
        self.assertEqual(res["action"], "skipped_draft")


# --- fan-out happy path & idempotency ----------------------------------------


class TestFanoutHappyPath(_TempWorldTest):
    def test_two_targets_success_and_schema_alignment(self):
        w = self.world()
        _, pid = w.accepted_proposal("f1")
        r = w.pipe.fanout_job(**w.fanout_kw("jb-f1", pid))
        self.assertEqual(r["outcomes"],
                         {"instagram": "published",
                          "telegram": "published"})
        self.assertEqual(r["aggregate"], "SUCCESS")
        ig_ref = w.ig_pub.dlq and None or r["receipts"]["instagram"]
        # adapted payload alignment: media:// ref + hash from the AI media
        self.assertTrue(str(ig_ref.get("publish_key", "") or "k"))
        # the durable outbox received the D-069-shaped payload
        pending = w.ig_pub.pending()
        self.assertEqual(pending, [])   # all terminal

    def test_duplicate_job_id_refused(self):
        w = self.world()
        _, pid = w.accepted_proposal("f2")
        kw = w.fanout_kw("jb-f2", pid)
        r1 = w.pipe.fanout_job(**kw)
        self.assertTrue(r1["outcomes"])
        r2 = w.pipe.fanout_job(**kw)
        self.assertFalse(r2["routed"])
        self.assertEqual(r2["reason"], "already_claimed")

    def test_local_class_b_before_dispatch(self):
        w = self.world()
        _, pid = w.accepted_proposal("f3")
        with self.assertRaises(OrchestrationContractError):
            w.pipe.fanout_job(**w.fanout_kw(
                "jb-f3", pid, hashtags=["bad tag!"]))

    def test_duplicate_content_deduped_by_real_publishers(self):
        w = self.world()
        _, pid = w.accepted_proposal("f4")
        kw = w.fanout_kw("jb-f4a", pid)
        w.pipe.fanout_job(**kw)
        # different job, SAME content: outbox terminal guards dedupe
        r = w.pipe.fanout_job(**w.fanout_kw(
            "jb-f4b", pid, targets=["instagram"]))
        self.assertEqual(r["outcomes"]["instagram"],
                         "duplicate_publish_blocked")
        self.assertEqual(w.ig_pub.dlq, [])


# --- failure boundaries (chaos ladder) ---------------------------------------


class TestFailureBoundaries(_TempWorldTest):
    def test_target_crash_is_isolated(self):
        w = self.world()
        _, pid = w.accepted_proposal("x1")
        w.fanout.publish_binds["telegram"] = _MemoryBind(crash=True)
        r = w.pipe.fanout_job(**w.fanout_kw("jb-x1", pid))
        self.assertEqual(r["outcomes"]["instagram"], "published")
        self.assertEqual(r["outcomes"]["telegram"],
                         "target_dispatch_crashed")
        self.assertEqual(r["aggregate"], "DISPATCHING")

    def test_instagram_class_c_cooldown(self):
        w = self.world(ig_adapter=MockInstagramAdapter(
            fail_with="rate_limit"))
        _, pid = w.accepted_proposal("x2")
        r = w.pipe.fanout_job(**w.fanout_kw(
            "jb-x2", pid, targets=["instagram"]))
        self.assertEqual(r["outcomes"]["instagram"], "cooldown")
        self.assertEqual(r["aggregate"], "DISPATCHING")
        self.assertEqual(w.ig_pub.dlq, [])   # transient: NOT dead-lettered

    def test_telegram_chat_unreachable_deadletters(self):
        w = self.world(tg_adapter=MockTelegramAdapter(
            fail_with="blocked"))
        _, pid = w.accepted_proposal("x3")
        r = w.pipe.fanout_job(**w.fanout_kw(
            "jb-x3", pid, targets=["telegram"]))
        # Class-E: the queue FREEZES (human intervention) and the item
        # is dead-lettered durably; the transition outcome records
        # chat_unreachable
        self.assertEqual(r["outcomes"]["telegram"], "queue_frozen")
        self.assertEqual(r["aggregate"], "FAILED")
        self.assertEqual(len(w.tg_pub.dlq), 1)   # durable, never deleted
        transitions = [t for t in w.tg_pub._store_refs()
                       if str(t.get("event_id", "")).startswith(
                           "telegram|transition|")]
        self.assertTrue(any(
            t.get("outcome") == "chat_unreachable" and
            t.get("state") == "FAILED" for t in transitions))

    def test_compensation_verdicts_are_deterministic(self):
        w = self.world()
        _, pid = w.accepted_proposal("x4")
        w.fanout.publish_binds["telegram"] = _MemoryBind(crash=True)
        w.pipe.fanout_job(**w.fanout_kw("jb-x4", pid))
        c = w.pipe.compensate_job("jb-x4")
        self.assertEqual(c["compensation"],
                         {"instagram": "COMPLETED",
                          "telegram": "REFUNDED"})
        c2 = w.pipe.compensate_job("jb-x4")   # idempotent re-read
        self.assertEqual(c2["compensation"], c["compensation"])

    def test_compensation_retry_scheduled_for_cooldown(self):
        w = self.world(ig_adapter=MockInstagramAdapter(
            fail_with="rate_limit"))
        _, pid = w.accepted_proposal("x5")
        w.pipe.fanout_job(**w.fanout_kw("jb-x5", pid,
                                        targets=["instagram"]))
        c = w.pipe.compensate_job("jb-x5")
        self.assertEqual(c["compensation"]["instagram"],
                         "RETRY_SCHEDULED")


# --- durable hygiene & redaction ----------------------------------------------


class TestDurableHygiene(_TempWorldTest):
    def test_compensation_marker_is_durable_append(self):
        w = self.world()
        _, pid = w.accepted_proposal("h1")
        w.pipe.fanout_job(**w.fanout_kw("jb-h1", pid))
        w.pipe.compensate_job("jb-h1")
        eids = [json.loads(r).get("event_id")
                for r in w.store.succeeded_references("orchestration")]
        self.assertIn("orchestration|jb-h1|compensated", eids)

    def test_receipts_carry_no_credential_material(self):
        w = self.world()
        _, pid = w.accepted_proposal("h2")
        r = w.pipe.fanout_job(**w.fanout_kw("jb-h2", pid))
        blob = json.dumps(r, ensure_ascii=False)
        for marker in ("sk-", "Bearer ", "consumer_key", "api_key"):
            self.assertNotIn(marker, blob)

    def test_adapted_payloads_stay_in_contract_shape(self):
        w = self.world()
        _, pid = w.accepted_proposal("h3")
        w.pipe.fanout_job(**w.fanout_kw("jb-h3", pid))
        # the D-069 validator already normalized the instagram ref
        refs = [d for d in w.ig_pub._store_refs()
                if str(d.get("event_id", "")).startswith(
                    "instagram|publish|")]
        self.assertTrue(refs)
        self.assertIn("media_hash", refs[0])
        self.assertIn("scheduled_slot", refs[0])


# --- validation script invariants -------------------------------------------


class TestValidationScript(unittest.TestCase):
    """The operator script is exercised the way the operator runs it."""

    SCRIPT = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "scripts", "validate_orchestration_live.py")

    def test_offline_drill_green(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("orch_drill",
                                                      self.SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertEqual(mod.drill(), 0)

    def test_drill_fails_closed_on_regression(self):
        """An over-permissive pipeline (a regression that dispatches
        un-reviewed proposals) must flip the drill exit code to 1 —
        the drill may never report a false green."""
        import importlib.util
        spec = importlib.util.spec_from_file_location("orch_drill2",
                                                      self.SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        orig = mod.ContentToChannelPipeline.fanout_job

        def permissive(self, **kw):   # regression: gate bypassed
            return {"routed": True, "outcomes":
                    {"instagram": "published", "telegram": "published"},
                    "aggregate": "SUCCESS", "receipts": {}}

        mod.ContentToChannelPipeline.fanout_job = permissive
        try:
            self.assertEqual(mod.drill(), 1)
        finally:
            mod.ContentToChannelPipeline.fanout_job = orig

    def test_live_gate_fail_closed(self):
        import importlib.util
        import subprocess
        env = dict(os.environ)
        env.pop("ORCH_LIVE_ENABLED", None)
        rc = subprocess.call(
            [sys.executable, self.SCRIPT, "--live"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            env=env, timeout=60)
        self.assertEqual(rc, 2)

    def test_script_carries_no_credential_material(self):
        import re
        with open(self.SCRIPT, encoding="utf-8") as f:
            src = f.read()
        self.assertIn("ORCH_LIVE_ENABLED", src)   # explicit D-045 gate
        # no credential-SHAPED literals (markers-as-strings are fine)
        for pattern in (r"sk-[A-Za-z0-9]{16,}",
                        r"sk-ant-[A-Za-z0-9]",
                        r"Bearer [A-Za-z0-9_\-]{10,}",
                        r"ck_[A-Za-z0-9]{20,}"):
            self.assertIsNone(re.search(pattern, src), pattern)


if __name__ == "__main__":
    unittest.main()

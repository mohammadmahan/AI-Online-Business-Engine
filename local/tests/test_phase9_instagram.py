"""Phase 9 — Instagram integration test suite (D-069..D-072).

Layers:
  M1  contracts: payload validators (aspect ratio, caption, hashtags),
      state machine legality, Class-B local prevention (no network).
  M2  adapters: mock workflow fidelity, bounded polling, D-071
      enablement gate (closed by default), token redaction.
  M3  publisher: D-070 vault (double-publish blocked under retry AND
      concurrency), D-072 classifier (A backoff / B terminal / C
      cooldown / E freeze), DLQ audit, outbox durability.
  M4  end-to-end on the LIVE PostgreSQL vault + event store:
      full publish, duplicate blocked across fresh publisher
      instances (restart safety), audit trail reconstruction.

Zero network: every test uses MockInstagramAdapter or injected
transports; the live GraphApiAdapter is never constructed without
env keys and even then uses only injected transports.
"""

import json
import os
import sys
import tempfile
import threading
import unittest
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOCAL = HERE.parent
ROOT = LOCAL.parent
for p in (str(HERE), str(LOCAL), str(LOCAL / "canonical"),
          str(LOCAL / "services"), str(LOCAL / "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

from canonical.instagram_contracts import (  # noqa: E402
    ALLOWED_ASPECT_RATIOS, CONTAINER_STATUS, FAILED, InstagramContractError,
    MAX_CAPTION_CHARS, MAX_HASHTAGS, MEDIA_CREATE, MEDIA_PUBLISH, PENDING,
    PUBLISHED, TERMINAL, TRANSITIONS, caption_hash, is_allowed_ratio,
    key_from_payload, parse_aspect_ratio, publish_idempotency_key,
    validate_publish_payload, validate_transition)
from canonical.instagram_adapter import (  # noqa: E402
    ContainerNotReady, GraphApiAdapter, MockInstagramAdapter, _RateLimited,
    TOKEN_MARKERS, live_enabled, poll_until_ready, redact)
from canonical.instagram_publisher import (  # noqa: E402
    InstagramOutboxPublisher, _JsonVault, _PgVault, _TokenExpired)
from services.sync_engine import EventStore, ProvenanceEngine  # noqa: E402


def base_payload(**over):
    p = {"content_id": "POST-1", "media_ref": "s3://media/m.jpg",
         "media_hash": "a" * 64,
         "caption": "کت پاییزی جدید #پاییز",
         "aspect_ratio": "4:5", "scheduled_slot": "SLOT-9"}
    p.update(over)
    return p


def make_publisher(tmp, **kw):
    store = EventStore(os.path.join(tmp, f"e-{uuid.uuid4().hex[:8]}.json"))
    vault = _JsonVault(os.path.join(tmp, f"v-{uuid.uuid4().hex[:8]}.json"))
    prov = ProvenanceEngine(os.path.join(tmp, f"p-{uuid.uuid4().hex[:8]}.jsonl"))
    return InstagramOutboxPublisher(store, vault, prov, **kw)


def _stack_up():
    try:
        import subprocess
        out = subprocess.run(
            ["docker", "compose", "-f", "local/infra/docker-compose.yml",
             "ps", "--format", "json"], capture_output=True, text=True,
            timeout=20, cwd=str(ROOT))
        return out.returncode == 0 and \
            "engine-local-postgres" in out.stdout and \
            "healthy" in out.stdout
    except Exception:
        return False


# ---------------------------------------------------------------------------
# M1 — contracts & local validation (D-069)
# ---------------------------------------------------------------------------

class ContractTests(unittest.TestCase):
    def test_valid_payload_normalizes(self):
        norm = validate_publish_payload(base_payload())
        self.assertEqual(norm["aspect_ratio"], "4:5")
        self.assertIn("caption_hash", norm)
        self.assertTrue(norm["caption_hash"].startswith(
            caption_hash(base_payload()["caption"])[:4]))

    def test_aspect_ratio_whitelist(self):
        for bad in ("9:16", "3:2", "1:9", "abc", "", "4/5"):
            with self.assertRaises(InstagramContractError,
                                   msg=bad):
                validate_publish_payload(base_payload(aspect_ratio=bad))
        for good in ("1:1", "4:5", "16:9"):
            validate_publish_payload(base_payload(aspect_ratio=good))
        self.assertEqual(parse_aspect_ratio("4:5"), (4, 5))
        self.assertIsNone(parse_aspect_ratio("4-5"))
        self.assertTrue(is_allowed_ratio("16:9"))
        self.assertFalse(is_allowed_ratio("9:16"))

    def test_caption_length_cap(self):
        long_caption = "ک" * (MAX_CAPTION_CHARS + 1)
        with self.assertRaises(InstagramContractError):
            validate_publish_payload(base_payload(caption=long_caption))
        # exactly at the cap is legal
        validate_publish_payload(base_payload(caption="ک" * MAX_CAPTION_CHARS))

    def test_hashtag_cap(self):
        tags = " ".join(f"#t{i}" for i in range(MAX_HASHTAGS + 1))
        with self.assertRaises(InstagramContractError):
            validate_publish_payload(base_payload(caption=f"پست {tags}"))
        ok_tags = " ".join(f"#t{i}" for i in range(MAX_HASHTAGS))
        validate_publish_payload(base_payload(caption=f"پست {ok_tags}"))

    def test_missing_fields_rejected(self):
        for field in ("content_id", "media_ref", "media_hash", "caption",
                      "aspect_ratio", "scheduled_slot"):
            payload = base_payload()
            del payload[field]
            with self.assertRaises(InstagramContractError, msg=field):
                validate_publish_payload(payload)
        with self.assertRaises(InstagramContractError):
            validate_publish_payload(base_payload(media_hash="short"))
        with self.assertRaises(InstagramContractError):
            validate_publish_payload("not-a-dict")

    def test_state_machine_legality(self):
        legal = [(PENDING, MEDIA_CREATE),
                 (MEDIA_CREATE, CONTAINER_STATUS),
                 (CONTAINER_STATUS, CONTAINER_STATUS),
                 (CONTAINER_STATUS, MEDIA_PUBLISH),
                 (MEDIA_PUBLISH, PUBLISHED),
                 (MEDIA_CREATE, FAILED), (PENDING, FAILED)]
        for a, b in legal:
            validate_transition(a, b)
        with self.assertRaises(InstagramContractError):
            validate_transition(PENDING, PUBLISHED)      # skip workflow
        with self.assertRaises(InstagramContractError):
            validate_transition(PUBLISHED, PENDING)      # terminal exit
        with self.assertRaises(InstagramContractError):
            validate_transition(FAILED, MEDIA_CREATE)    # failed → retry
        with self.assertRaises(InstagramContractError):
            validate_transition(PUBLISHED, FAILED)

    def test_idempotency_key_determinism(self):
        k1 = key_from_payload(base_payload())
        k2 = key_from_payload(base_payload())
        self.assertEqual(k1, k2)  # same attempt → same key
        k3 = key_from_payload(base_payload(scheduled_slot="SLOT-10"))
        self.assertNotEqual(k1, k3)  # distinct slot → distinct key
        k4 = key_from_payload(base_payload(caption="متن دیگر #جدید"))
        self.assertNotEqual(k1, k4)  # changed caption → distinct key
        self.assertEqual(len(k1), 64)
        # manual composition equals helper
        manual = publish_idempotency_key(
            "POST-1", "a" * 64, caption_hash(base_payload()["caption"]),
            "SLOT-9")
        self.assertEqual(manual, k1)


# ---------------------------------------------------------------------------
# M2 — adapters, polling, gate, redaction (D-071)
# ---------------------------------------------------------------------------

class AdapterTests(unittest.TestCase):
    def test_mock_full_workflow(self):
        mock = MockInstagramAdapter(polls_until_ready=2)
        c = mock.create_media_container("s3://media/m.jpg",
                                        "کپشن", "4:5")
        self.assertEqual(c["status_code"], "IN_PROGRESS")
        with self.assertRaises(InstagramContractError):
            mock.publish_container(c["container_id"])  # not FINISHED yet
        st = poll_until_ready(mock, c["container_id"], sleep_fn=lambda s: None)
        self.assertEqual(st["status_code"], "FINISHED")
        pub = mock.publish_container(c["container_id"])
        self.assertTrue(pub["publication_id"].startswith("MOCK_PUB_"))

    def test_poll_bounded_never_infinite(self):
        slow = MockInstagramAdapter(polls_until_ready=99)
        c = slow.create_media_container("m", "c", "1:1")
        with self.assertRaises(ContainerNotReady):
            poll_until_ready(slow, c["container_id"], max_polls=4,
                             sleep_fn=lambda s: None)
        # exactly the poll budget: 1 create + 4 status calls
        self.assertEqual(slow.calls.count("status"), 4)

    def test_poll_error_status_is_terminal(self):
        mock = MockInstagramAdapter()
        c = mock.create_media_container("m", "c", "1:1")
        mock._containers[c["container_id"]]["status_code"] = "ERROR"
        with self.assertRaises(InstagramContractError):
            poll_until_ready(mock, c["container_id"], sleep_fn=lambda s: None)

    def test_gate_closed_by_default(self):
        saved = {k: os.environ.get(k) for k in
                 ("INSTAGRAM_LIVE_ENABLED", "INSTAGRAM_ACCESS_TOKEN",
                  "INSTAGRAM_BUSINESS_ID")}
        try:
            for k in saved:
                os.environ.pop(k, None)
            self.assertFalse(live_enabled())
            with self.assertRaises(InstagramContractError):
                GraphApiAdapter(transport=lambda r: {})
            os.environ["INSTAGRAM_LIVE_ENABLED"] = "true"
            with self.assertRaises(InstagramContractError):
                GraphApiAdapter(transport=lambda r: {})  # keys missing
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_live_adapter_needs_no_network_when_gated(self):
        # explicit credentials + injected transport: still zero network
        saved = {k: os.environ.get(k) for k in
                 ("INSTAGRAM_LIVE_ENABLED", "INSTAGRAM_ACCESS_TOKEN",
                  "INSTAGRAM_BUSINESS_ID")}
        try:
            os.environ["INSTAGRAM_LIVE_ENABLED"] = "true"
            os.environ["INSTAGRAM_ACCESS_TOKEN"] = "test-dummy"
            os.environ["INSTAGRAM_BUSINESS_ID"] = "BIZ1"
            calls = []

            def transport(rd):
                calls.append(rd)
                return {"id": "C1", "status_code": "FINISHED"}

            g = GraphApiAdapter(transport=transport)
            st = g.container_status("C1")
            self.assertEqual(st["status_code"], "FINISHED")
            self.assertEqual(len(calls), 1)
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_redaction(self):
        dirty = ("error calling graph.facebook.com/v18.0/me?access_token="
                 "IGQVJWXYZ123456&fields=id; also IGQVJABCDEF98765 inside")
        clean = redact(dirty)
        self.assertNotIn("IGQVJWXYZ123456", clean)
        self.assertNotIn("IGQVJABCDEF98765", clean)
        self.assertIn("[REDACTED]", clean)
        # EAAG-style tokens
        clean2 = redact("bad token EAAG1234567890abcdef detected")
        self.assertNotIn("EAAG1234567890abcdef", clean2)
        # redaction applies to mock failure messages too
        mock = MockInstagramAdapter(fail_with="create_error")
        with self.assertRaises(InstagramContractError) as cm:
            mock.create_media_container("m", "c", "1:1")
        self.assertNotIn("SECRET", str(cm.exception))
        self.assertIn("[REDACTED]", str(cm.exception))


# ---------------------------------------------------------------------------
# M3 — vault, outbox, classifier, DLQ (D-070/D-072)
# ---------------------------------------------------------------------------

class VaultAndClassifierTests(unittest.TestCase):
    def _pub(self, tmp, **kw):
        return make_publisher(tmp, **kw)

    def test_double_publish_blocked_same_instance(self):
        with tempfile.TemporaryDirectory() as tmp:
            pub = self._pub(tmp)
            q = pub.enqueue(base_payload())
            r1 = pub.publish(q["payload"], MockInstagramAdapter(),
                             sleep_fn=lambda s: None)
            self.assertEqual(r1["outcome"], "published")
            r2 = pub.publish(q["payload"], MockInstagramAdapter(),
                             sleep_fn=lambda s: None)
            self.assertEqual(r2["outcome"], "duplicate_publish_blocked")
            self.assertEqual(r2["original"]["content_id"], "POST-1")

    def test_double_publish_blocked_across_instances(self):
        # simulates a second dispatcher process / network retry: fresh
        # publisher instances, same canonical vault file
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = os.path.join(tmp, "vault.json")
            store1 = EventStore(os.path.join(tmp, "e1.json"))
            p1 = InstagramOutboxPublisher(
                store1, _JsonVault(vault_path),
                ProvenanceEngine(os.path.join(tmp, "p1.jsonl")))
            q = p1.enqueue(base_payload())
            r1 = p1.publish(q["payload"], MockInstagramAdapter(),
                            sleep_fn=lambda s: None)
            self.assertEqual(r1["outcome"], "published")
            store2 = EventStore(os.path.join(tmp, "e2.json"))
            p2 = InstagramOutboxPublisher(
                store2, _JsonVault(vault_path),
                ProvenanceEngine(os.path.join(tmp, "p2.jsonl")))
            r2 = p2.publish(q["payload"], MockInstagramAdapter(),
                            sleep_fn=lambda s: None)
            self.assertEqual(r2["outcome"], "duplicate_publish_blocked")

    def test_concurrent_dispatchers_single_publish(self):
        # two threads racing the SAME key: exactly one publishes
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = os.path.join(tmp, "vault.json")
            pubs = []
            for i in range(2):
                pubs.append(InstagramOutboxPublisher(
                    EventStore(os.path.join(tmp, f"e{i}.json")),
                    _JsonVault(vault_path),
                    ProvenanceEngine(os.path.join(tmp, f"p{i}.jsonl"))))
            q = pubs[0].enqueue(base_payload())
            results = []

            def worker(pub):
                results.append(pub.publish(q["payload"],
                                           MockInstagramAdapter(),
                                           sleep_fn=lambda s: None)[
                    "outcome"])

            t1 = threading.Thread(target=worker, args=(pubs[0],))
            t2 = threading.Thread(target=worker, args=(pubs[1],))
            t1.start(); t2.start(); t1.join(); t2.join()
            self.assertEqual(sorted(results),
                             ["duplicate_publish_blocked", "published"])

    def test_class_a_backoff_then_dlq(self):
        with tempfile.TemporaryDirectory() as tmp:
            pub = self._pub(tmp, max_retries=2)
            q = pub.enqueue(base_payload())
            r1 = pub.publish(q["payload"],
                             MockInstagramAdapter(fail_with="timeout"),
                             sleep_fn=lambda s: None)
            self.assertEqual(r1["outcome"], "retry_scheduled")
            self.assertEqual(r1["error_class"], "A")
            self.assertEqual(r1["attempt_no"], 1)
            r2 = pub.publish(q["payload"],
                             MockInstagramAdapter(fail_with="timeout"),
                             sleep_fn=lambda s: None)
            self.assertEqual(r2["attempt_no"], 2)
            r3 = pub.publish(q["payload"],
                             MockInstagramAdapter(fail_with="timeout"),
                             sleep_fn=lambda s: None)
            self.assertEqual(r3["outcome"], "retries_exhausted")
            self.assertEqual(len(pub.dlq), 1)
            self.assertEqual(pub.dlq[0]["error_class"], "A")
            self.assertTrue(pub.dlq[0]["attempts"])

    def test_class_b_terminal_no_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            pub = self._pub(tmp)
            q = pub.enqueue(base_payload())
            r = pub.publish(q["payload"],
                            MockInstagramAdapter(fail_with="create_error"),
                            sleep_fn=lambda s: None)
            self.assertEqual(r["outcome"], "terminal_reject")
            self.assertEqual(r["error_class"], "B")
            self.assertEqual(len(pub.dlq), 1)
            self.assertEqual(pub.dlq[0]["error_class"], "B")
            # the error message was REDACTED before entering the DLQ
            self.assertNotIn("SECRET", json.dumps(pub.dlq))
            self.assertIn("[REDACTED]", pub.dlq[0]["error"])

    def test_class_c_cooldown_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            pub = self._pub(tmp)
            q = pub.enqueue(base_payload())
            class RL(MockInstagramAdapter):
                def container_status(self, cid):
                    raise _RateLimited("429 access_token=SECRET")
            r = pub.publish(q["payload"], RL(), sleep_fn=lambda s: None)
            self.assertEqual(r["outcome"], "cooldown")
            self.assertEqual(r["error_class"], "C")
            self.assertGreater(r["retry_after_s"], 0)
            self.assertFalse(pub.retry_eligible(q["publish_key"]))

    def test_class_e_freezes_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            pub = self._pub(tmp)
            q = pub.enqueue(base_payload())
            other = pub.enqueue(base_payload(content_id="POST-2"))
            outcomes = []

            class TokenDead(MockInstagramAdapter):
                def create_media_container(self, *a, **k):
                    raise _TokenExpired("token expired access_token=SECRET")

            r = pub.publish(q["payload"], TokenDead(),
                            sleep_fn=lambda s: None)
            self.assertEqual(r["outcome"], "queue_frozen")
            self.assertEqual(r["error_class"], "E")
            self.assertTrue(pub.frozen)
            # the whole queue is frozen — other items cannot publish
            r2 = pub.publish(other["payload"], MockInstagramAdapter(),
                             sleep_fn=lambda s: None)
            self.assertEqual(r2["outcome"], "queue_frozen")
            self.assertEqual(len(pub.dlq), 1)

    def test_outbox_durability_and_listing(self):
        with tempfile.TemporaryDirectory() as tmp:
            pub = self._pub(tmp)
            q1 = pub.enqueue(base_payload())
            q2 = pub.enqueue(base_payload(content_id="POST-2",
                                          scheduled_slot="SLOT-1"))
            pending = pub.pending()
            self.assertEqual(len(pending), 2)
            # deterministic order by scheduled_slot
            self.assertEqual(pending[0]["scheduled_slot"], "SLOT-1")
            # enqueueing an identical item is idempotent (no dup row)
            again = pub.enqueue(base_payload())
            self.assertFalse(again["queued"])
            # invalid payload rejected LOCALLY — never queued, never network
            with self.assertRaises(InstagramContractError):
                pub.enqueue(base_payload(aspect_ratio="9:16"))
            self.assertEqual(len(pub.pending()), 2)

    def test_provenance_on_outcomes(self):
        with tempfile.TemporaryDirectory() as tmp:
            pub = self._pub(tmp)
            before = len(pub.provenance.records)
            q = pub.enqueue(base_payload())
            pub.publish(q["payload"], MockInstagramAdapter(),
                        sleep_fn=lambda s: None)
            pub.publish(q["payload"], MockInstagramAdapter(),
                        sleep_fn=lambda s: None)
            self.assertGreater(len(pub.provenance.records) - before, 0)


# ---------------------------------------------------------------------------
# M4 — LIVE PostgreSQL end-to-end (vault + event store)
# ---------------------------------------------------------------------------

@unittest.skipUnless(_stack_up(), "live PostgreSQL stack not running")
class LivePostgresEndToEndTests(unittest.TestCase):
    """D-070 vault on the real D-055 store: the PK-as-lock semantics
    proven against live PostgreSQL, incl. restart safety."""

    @classmethod
    def setUpClass(cls):
        scripts = str(LOCAL / "scripts")
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        from canonical.notion_ingest import PgEventStore
        cls.PgEventStore = PgEventStore
        cls._tmp = tempfile.TemporaryDirectory()
        # unique slot per run: tests are re-runnable against the
        # persistent live store without colliding with past runs
        cls._run = uuid.uuid4().hex[:8]

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _payload(self, content_id):
        return base_payload(content_id=content_id,
                            scheduled_slot=f"SLOT-{self._run}")

    def test_full_publish_and_duplicate_block_on_live_pg(self):
        tmp = self._tmp.name
        payload = self._payload(f"PG-{self._run}-1")
        key = key_from_payload(payload)
        store = self.PgEventStore()
        pub = InstagramOutboxPublisher(
            store, _PgVault(),
            ProvenanceEngine(os.path.join(tmp, f"prov-{self._run}.jsonl")))
        q = pub.enqueue(payload)
        self.assertTrue(q["queued"])
        r1 = pub.publish(q["payload"], MockInstagramAdapter(),
                         sleep_fn=lambda s: None)
        self.assertEqual(r1["outcome"], "published")
        self.assertEqual(r1["error_class"] if "error_class" in r1
                         else None, None)
        # a FRESH publisher (simulated restart / second dispatcher)
        pub2 = InstagramOutboxPublisher(
            self.PgEventStore(), _PgVault(),
            ProvenanceEngine(os.path.join(tmp, f"prov2-{self._run}.jsonl")))
        r2 = pub2.publish(q["payload"], MockInstagramAdapter(),
                          sleep_fn=lambda s: None)
        self.assertEqual(r2["outcome"], "duplicate_publish_blocked")
        self.assertEqual(r2["original"]["content_id"], payload["content_id"])
        # distinct slot → distinct key → publishes again (deliberate
        # re-publication is addressable without weakening retry dedup)
        other = dict(payload, scheduled_slot=f"SLOT-{self._run}-alt")
        q3 = pub2.enqueue(other)
        r3 = pub2.publish(q3["payload"], MockInstagramAdapter(),
                          sleep_fn=lambda s: None)
        self.assertEqual(r3["outcome"], "published")

    def test_outbox_audit_reconstruction_on_live_pg(self):
        payload = self._payload(f"PG-{self._run}-2")
        store = self.PgEventStore()
        pub = InstagramOutboxPublisher(
            store, _PgVault(),
            ProvenanceEngine(os.path.join(self._tmp.name,
                                          f"prov3-{self._run}.jsonl")))
        q = pub.enqueue(payload)
        pub.publish(q["payload"], MockInstagramAdapter(polls_until_ready=2),
                    sleep_fn=lambda s: None)
        # reconstruct the workflow history from DURABLE store data only
        rows = [json.loads(line) for line in
                store.succeeded_references("instagram")]
        states = [r["state"] for r in rows
                  if r.get("publish_key") == q["publish_key"]
                  and r.get("state")]
        self.assertIn(MEDIA_CREATE, states)
        self.assertIn(CONTAINER_STATUS, states)
        self.assertIn(MEDIA_PUBLISH, states)
        self.assertIn(PUBLISHED, states)
        # the workflow order is preserved (M4-Phase7 monotonic fix
        # guarantees insertion-order reconstruction)
        self.assertEqual(states.index(MEDIA_CREATE) < states.index(PUBLISHED),
                         True)


if __name__ == "__main__":
    unittest.main()

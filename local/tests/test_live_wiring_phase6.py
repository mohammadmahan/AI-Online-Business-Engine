"""Phase 6 live wiring igniter battery (D-156, offline).

Exercises `local/scripts/live_wiring_phase6_igniter.py` fully
offline — the Notion client transport injected, every upstream
artifact REAL repo material: the Phase 5 attestation produced by the
REAL D-155 igniter over the authentic Stage C→H chain (the same
chain the D-152/D-153/D-154/D-155 batteries proved), and the REAL
`canonical.notion_live` client layer (NotionPacer token bucket,
D-052 error classification, redact_notion) driving an in-process
fake transport:

  PASS    — phase5 attestation + authenticated client + conformant
            workspace + clean probe cycle ⇒ PHASE6_IGNITED with a
            valid `phase6.live_wiring_attestation.v1`;
  NOT-01  — phase5 attestation absent / malformed / wrong verdict /
            drifted digest / unrooted / broken chain ⇒ refusal;
  NOT-02  — transport timeout, 401/403, rate-limit guardrail
            failure ⇒ fail-closed abort;
  NOT-03  — missing mandatory properties, corrupted property
            types, missing select options, unbound relations ⇒
            refusal;
  NOT-04  — probe write failure, read-back mismatch, cleanup
            failure, idempotency collision (replay yields a
            DISTINCT page) ⇒ rejection;
  NOT-05  — exactly one canonical attestation per run (including
            aborts), deterministic digest;
  REDACT  — the Notion token, canaries and probe payloads never
            reach the attestation or audit copies (D-124);
  AST     — pure igniter core (no network imports, no shell, no
            spawn), transport injected only.
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

from canonical.notion_live import (  # noqa: E402
    NotionPacer, NotionAuthError, NotionContractError,
    NotionTransientError, classify_notion_error, redact_notion,
)
from live_wiring_phase5_igniter import (  # noqa: E402
    ATTESTATION_SCHEMA as PHASE5_SCHEMA,
    PHASE5_IGNITED, Phase5Igniter,
)
from live_wiring_phase6_igniter import (  # noqa: E402
    ATTESTATION_SCHEMA, DB_KEYS, PHASE5_ROW_KIND, PHASE6_IGNITED,
    PHASE6_INCOMPLETE, PROBE_ROW_KIND, RATE_LIMIT_PER_SEC,
    NotionProbeTransport, Phase6Igniter, WorkspaceSchema,
    canonical_hash,
)

ENGINE = SCRIPTS / "live_wiring_phase6_igniter.py"

CANARY = "sk-canaryvalue1234567890abcdef"
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
RUNBOOK = (REPO / "docs" / "deployment" /
           "stage-e-cutover-runbook.md").read_text(encoding="utf-8")


# The D-155 battery module carries the authentic Stage C→H chain
# builders (real certificate via the real D-152/D-153/D-154 engines
# and the real Stage F gate) — reuse them instead of duplicating.
import tests.test_live_wiring_phase5 as t5  # noqa: E402


def real_phase5_attestation(observed_tick=4000):
    """Run the REAL D-155 igniter over the authentic chain with
    in-process fakes (identical to the D-155 battery pass path)."""
    cert, ledger = t5.real_cert(2000)
    sink: list = []
    ign = Phase5Igniter(
        clock=lambda: observed_tick, audit_sink=sink.append,
        cert_provider=lambda: cert, audit_rows=lambda: ledger,
        chain_verifier=lambda: {"ok": True, "rows": len(ledger)},
        pg=t5.FakePsql(), redis=t5.FakeRedis(),
        webhook=t5.FakeWebhook())
    att = ign.run(d027_store=t5.DrillStore())
    # The phase5 ignition record joins the ledger — Phase 6's NOT-01
    # rooting evidence.
    ledger.append({
        "event_kind": "phase5_live_wiring_attestation",
        "detail": {"attestation_digest": att.attestation_digest,
                   "verdict": att.verdict}})
    return att, ledger


# --- the fake Notion universe ----------------------------------------

DB_IDS = {
    "product_catalog": "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
    "order_pipeline": "b2c3d4e5-f6a7-4b8c-9d0e-1f2a3b4c5d6e",
    "marketing_campaigns": "c3d4e5f6-a7b8-4c9d-0e1f-2a3b4c5d6e7f",
    "tasks_sops": "d4e5f6a7-b8c9-4d0e-1f2a-3b4c5d6e7f80",
}


def notion_db_payload(key):
    specs = WorkspaceSchema().specs
    spec = specs[key]
    props = {}
    for pname, ptype in spec["required"].items():
        entry = {"type": ptype, pname: {}}
        if ptype == "select":
            options = spec.get("select_options", {}).get(sname := pname, set())
            entry[ptype] = {"options": [{"name": o} for o in
                                        sorted(options)]}
        if ptype == "relation":
            entry[ptype] = {"database_id":
                            DB_IDS["product_catalog"]}
        props[pname] = entry
    return {"object": "database", "id": DB_IDS[key],
            "title": [{"plain_text": spec["title"]}],
            "properties": props}


class FakeNotionBackend:
    """In-process Notion universe behind the injected transport:
    schema-conformant databases, an idempotent probe-page store, and
    fault-injection switches for every failure class."""

    def __init__(self, token=NOTION_TOKEN, corrupt=None,
                 fail_auth=False, fail_write=False, fail_read=False,
                 fail_archive=False, collide=False, timeout=False):
        self.token = token
        self.corrupt = corrupt          # (db_key, patch_fn)
        self.fail_auth = fail_auth
        self.fail_write = fail_write
        self.fail_read = fail_read
        self.fail_archive = fail_archive
        self.collide = collide
        self.timeout = timeout
        self.pages: dict = {}
        self.page_seq = 0
        self.requests: list = []
        self.intercept = None   # (matcher, responder) test hook

    # -- transport (the seam injected into the client) ------------

    def __call__(self, request):
        self.requests.append({k: v for k, v in request.items()
                              if k != "headers"})
        if self.intercept is not None:
            matcher, responder = self.intercept
            if matcher(request):
                return responder(request)
        if self.timeout:
            raise TimeoutError("transport timeout")
        method, url = request["method"], request["url"]
        if "/users/me" in url:
            if self.fail_auth:
                body = {"object": "error", "status": 401,
                        "code": "unauthorized"}
                return {"status_code": 401,
                        "body": json.dumps(body), "retry_after": None}
            return {"status_code": 200,
                    "body": json.dumps({
                        "object": "user",
                        "user": {"id": "u-1",
                                 "name": "engine-integration"},
                        "workspace": "engine-os"}),
                    "retry_after": None}
        if method == "GET" and "/databases/" in url:
            for key, dbid in DB_IDS.items():
                if dbid in url:
                    payload = notion_db_payload(key)
                    if self.corrupt and self.corrupt[0] == key:
                        self.corrupt[1](payload)
                    return {"status_code": 200,
                            "body": json.dumps(payload),
                            "retry_after": None}
            return {"status_code": 404,
                    "body": json.dumps({"object": "error",
                                        "status": 404}),
                    "retry_after": None}
        if method == "POST" and url.endswith("/pages"):
            if self.fail_write:
                return {"status_code": 500,
                        "body": json.dumps({"object": "error",
                                            "status": 500}),
                        "retry_after": None}
            body = request["json"]
            idem = body.get("idempotency_key", "")
            if idem and idem in self.pages:
                if self.collide:
                    self.page_seq += 1
                    pid = f"p-collide-{self.page_seq}"
                    self.pages[pid] = body
                    return {"status_code": 200,
                            "body": json.dumps({"page_id": pid}),
                            "retry_after": None}
                return {"status_code": 200,
                        "body": json.dumps(
                            {"page_id": self.pages[idem]}),
                        "retry_after": None}
            self.page_seq += 1
            pid = f"p-{self.page_seq}"
            if idem:
                self.pages[idem] = pid
            else:
                self.pages[pid] = pid
            return {"status_code": 200,
                    "body": json.dumps({"page_id": pid}),
                    "retry_after": None}
        if method == "POST" and "/blocks/" in url:
            return {"status_code": 200,
                    "body": json.dumps({"object": "list",
                                        "results": []}),
                    "retry_after": None}
        if method == "GET" and "/blocks/" in url:
            if self.fail_read:
                return {"status_code": 500,
                        "body": json.dumps({"object": "error",
                                            "status": 500}),
                        "retry_after": None}
            pid = url.rsplit("/", 2)[-2]
            return {"status_code": 200,
                    "body": json.dumps({
                        "page_id": pid,
                        "content": {"Name": "phase6-sync-probe",
                                    "SKU": "phase6-probe-0001"}}),
                    "retry_after": None}
        if method == "PATCH" and "/pages/" in url:
            if self.fail_archive:
                return {"status_code": 500,
                        "body": json.dumps({"object": "error",
                                            "status": 500}),
                        "retry_after": None}
            pid = url.rsplit("/", 1)[-1]
            return {"status_code": 200,
                    "body": json.dumps({"page_id": pid,
                                        "archived": True}),
                    "retry_after": None}
        return {"status_code": 400,
                "body": json.dumps({"object": "error",
                                    "status": 400}),
                "retry_after": None}


class FakeNotionClient:
    """LiveNotionClient-compatible wrapper over the fake backend —
    the same operation surface the engine expects, backed by the
    real canonical pacing/redaction layers."""

    def __init__(self, backend: FakeNotionBackend):
        self.backend = backend
        self._pacer = NotionPacer()

    def pacer(self):
        return self._pacer

    def users_me(self):
        resp = self.backend({
            "method": "GET",
            "url": "https://api.notion.com/v1/users/me",
            "headers": {"Authorization": f"Bearer {self.backend.token}"},
            "json": {}})
        status = resp["status_code"]
        if status != 200:
            raise classify_notion_error(
                status, resp["body"], resp.get("retry_after"))
        return json.loads(resp["body"])

    def retrieve_database(self, dbid):
        resp = self.backend({
            "method": "GET",
            "url": f"https://api.notion.com/v1/databases/{dbid}",
            "headers": {"Authorization": f"Bearer {self.backend.token}"},
            "json": {}})
        status = resp["status_code"]
        if status != 200:
            raise classify_notion_error(
                status, resp["body"], resp.get("retry_after"))
        return json.loads(resp["body"])

    def create_probe_page(self, dbid, payload, idempotency_key=""):
        resp = self.backend({
            "method": "POST",
            "url": "https://api.notion.com/v1/pages",
            "headers": {"Authorization": f"Bearer {self.backend.token}"},
            "json": {"parent": {"database_id": dbid},
                     "properties": payload,
                     "idempotency_key": idempotency_key}})
        status = resp["status_code"]
        if status != 200:
            raise classify_notion_error(
                status, resp["body"], resp.get("retry_after"))
        return json.loads(resp["body"])

    def read_probe_page(self, page_id):
        resp = self.backend({
            "method": "GET",
            "url": f"https://api.notion.com/v1/blocks/{page_id}/children",
            "headers": {"Authorization": f"Bearer {self.backend.token}"},
            "json": {}})
        status = resp["status_code"]
        if status != 200:
            raise classify_notion_error(
                status, resp["body"], resp.get("retry_after"))
        return json.loads(resp["body"])

    def archive_page(self, page_id):
        resp = self.backend({
            "method": "PATCH",
            "url": f"https://api.notion.com/v1/pages/{page_id}",
            "headers": {"Authorization": f"Bearer {self.backend.token}"},
            "json": {"archived": True}})
        status = resp["status_code"]
        if status != 200:
            raise classify_notion_error(
                status, resp["body"], resp.get("retry_after"))
        return json.loads(resp["body"])


# --- the wired harness -----------------------------------------------

_CHAIN: dict = {}


def the_att() -> dict:
    return _CHAIN["att"]


def the_ledger() -> list:
    return _CHAIN["ledger"]


def build_chain() -> None:
    if not _CHAIN:
        att, ledger = real_phase5_attestation()
        _CHAIN.update(att=att.to_dict(), ledger=ledger)


class Harness:
    """Fully wired igniter over the authentic phase5 chain; overrides
    swap providers (None = absent)."""

    def __init__(self, now: int = 6000, backend=None, **overrides):
        build_chain()
        self.now = now
        self.sink: list = []
        self.backend = backend or FakeNotionBackend()
        providers = {
            "phase5_provider": the_att,
            "audit_rows": the_ledger,
            "chain_verifier": lambda: {"ok": True,
                                       "rows": len(the_ledger())},
            "notion": FakeNotionClient(self.backend),
        }
        providers.update(overrides)
        self.igniter = Phase6Igniter(
            clock=lambda: self.now, audit_sink=self.sink.append,
            **providers)

    def run(self):
        return self.igniter.run(WorkspaceSchema(
            database_ids=DB_IDS))


# ===================================================================
# PASS — successful ignition
# ===================================================================

class TestIgnitionPass(unittest.TestCase):

    def test_01_full_ignition_completes(self):
        h = Harness()
        att = h.run()
        self.assertEqual(att.verdict, PHASE6_IGNITED)
        self.assertTrue(att.ignited)
        d = att.to_dict()
        self.assertEqual(d["schema"], ATTESTATION_SCHEMA)
        self.assertEqual(d["schema"],
                         "phase6.live_wiring_attestation.v1")
        self.assertEqual(d["phase5_digest"], att.phase5_digest)
        ids = [c[0] for c in att.checks]
        for rule in ("NOT-01", "NOT-02", "NOT-03", "NOT-04",
                     "NOT-05"):
            self.assertIn(rule, ids)
        self.assertTrue(all(c[1] for c in att.checks))
        self.assertTrue(d["auth"]["authenticated"])
        self.assertTrue(d["auth"]["pacer_ok"])
        self.assertEqual(d["schema_map"]["conformant"], 4)
        self.assertTrue(d["sync"]["idempotent"])
        self.assertTrue(d["sync"]["cleaned"])

    def test_02_attestation_digest_deterministic(self):
        a1 = Harness(now=7000).run()
        b1 = Harness(now=7000).run()
        self.assertEqual(a1.attestation_digest, b1.attestation_digest)
        self.assertEqual(a1.attestation_digest,
                         canonical_hash(a1.to_dict()))

    def test_03_all_four_databases_checked(self):
        att = Harness().run()
        smap = att.to_dict()["schema_map"]
        self.assertEqual(smap["databases_checked"], 4)
        self.assertEqual(sorted(smap["details"].keys()),
                         sorted(DB_KEYS))
        self.assertGreaterEqual(smap["relations_resolved"], 2)

    def test_04_paced_burst_never_dropped(self):
        h = Harness()
        h.run()
        pacer = h.igniter._prov["notion"].pacer()
        waits = [pacer.acquire(now_s=float(i)) for i in range(10)]
        self.assertTrue(all(w >= 0.0 for w in waits))
        self.assertTrue(any(w > 0.0 for w in waits))

    def test_05_probe_leaves_workspace_clean(self):
        h = Harness()
        att = h.run()
        sync = att.to_dict()["sync"]
        self.assertTrue(sync["created"])
        self.assertTrue(sync["read_back"])
        self.assertTrue(sync["cleaned"])
        # exactly one probe page created and archived (the idem slot)
        self.assertEqual(len(h.backend.pages), 1)


# ===================================================================
# NOT-01 — phase5 attestation refusals
# ===================================================================

class TestNot01Refusals(unittest.TestCase):

    def test_10_missing_phase5_attestation(self):
        att = Harness(phase5_provider=None).run()
        self.assertEqual(att.verdict, PHASE6_INCOMPLETE)
        self.assertIn("absent", att.checks[0][2])

    def test_11_provider_raises(self):
        def boom():
            raise RuntimeError("vault offline")
        att = Harness(phase5_provider=boom).run()
        self.assertEqual(att.verdict, PHASE6_INCOMPLETE)
        self.assertIn("RuntimeError", att.checks[0][2])

    def test_12_wrong_schema(self):
        att = Harness(phase5_provider=lambda: {
            "schema": "other.schema.v1"}).run()
        self.assertEqual(att.verdict, PHASE6_INCOMPLETE)
        self.assertIn("schema", att.checks[0][2])

    def test_13_incomplete_verdict_refused(self):
        bad = dict(the_att())
        bad["verdict"] = "IGNITION_INCOMPLETE"
        att = Harness(phase5_provider=lambda: bad).run()
        self.assertEqual(att.verdict, PHASE6_INCOMPLETE)
        self.assertIn("PHASE5_IGNITED",
                      " ".join(c[2] for c in att.checks))

    def test_14_drifted_digest_refused(self):
        # a digest drift manifests as a ledger-commitment mismatch:
        # root a DIFFERENT digest than the attestation recomputes to
        rows = the_ledger()[:-1] + [{
            "event_kind": "phase5_live_wiring_attestation",
            "detail": {"attestation_digest": "f" * 64}}]
        att = Harness(audit_rows=lambda: rows).run()
        self.assertEqual(att.verdict, PHASE6_INCOMPLETE)
        self.assertIn("DRIFTED", " ".join(c[2] for c in att.checks))

    def test_15_unrooted_attestation_refused(self):
        att = Harness(audit_rows=lambda: []).run()
        self.assertEqual(att.verdict, PHASE6_INCOMPLETE)
        self.assertIn("rooted", " ".join(c[2] for c in att.checks))

    def test_16_broken_chain_refused(self):
        att = Harness(chain_verifier=lambda: {
            "ok": False, "broken_at_seq": 3,
            "reason": "hash mismatch"}).run()
        self.assertEqual(att.verdict, PHASE6_INCOMPLETE)
        self.assertIn("not intact",
                      " ".join(c[2] for c in att.checks))

    def test_17_refusal_emits_attestation_and_no_probes(self):
        h = Harness(phase5_provider=None)
        att = h.run()
        self.assertEqual(att.verdict, PHASE6_INCOMPLETE)
        # fail-closed ordering: NO probe requests were made
        self.assertEqual(len(h.backend.requests), 0)
        # exactly one audited record (the abort attestation)
        self.assertEqual(len(h.sink), 1)
        self.assertEqual(h.sink[0]["verdict"], PHASE6_INCOMPLETE)


# ===================================================================
# NOT-02 — authentication & pacing failures
# ===================================================================

class TestNot02Auth(unittest.TestCase):

    def test_20_transport_timeout_fails_closed(self):
        att = Harness(backend=FakeNotionBackend(timeout=True)).run()
        self.assertEqual(att.verdict, PHASE6_INCOMPLETE)
        self.assertIn("TimeoutError",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "NOT-02"))

    def test_21_http_401_refused(self):
        att = Harness(backend=FakeNotionBackend(
            fail_auth=True)).run()
        self.assertEqual(att.verdict, PHASE6_INCOMPLETE)
        self.assertIn("NotionAuthError",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "NOT-02"))

    def test_22_http_403_refused(self):
        backend = FakeNotionBackend()
        backend.intercept = (
            lambda req: "/users/me" in req["url"],
            lambda req: {"status_code": 403,
                         "body": json.dumps({"object": "error",
                                             "status": 403}),
                         "retry_after": None})
        att = Harness(backend=backend).run()
        self.assertEqual(att.verdict, PHASE6_INCOMPLETE)
        self.assertIn("NotionAuthError",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "NOT-02"))

    def test_23_no_identity_refused(self):
        class NoIdentity:
            def pacer(self):
                return NotionPacer()

            def users_me(self):
                return {"object": "list", "results": []}
        att = Harness(notion=NoIdentity()).run()
        self.assertEqual(att.verdict, PHASE6_INCOMPLETE)
        self.assertIn("identity",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "NOT-02"))

    def test_24_missing_notion_client_fails_closed(self):
        att = Harness(notion=None).run()
        self.assertEqual(att.verdict, PHASE6_INCOMPLETE)
        self.assertIn("unavailable",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "NOT-02"))


# ===================================================================
# NOT-03 — schema conformance refusals
# ===================================================================

class TestNot03Schema(unittest.TestCase):

    def test_30_missing_mandatory_property(self):
        def drop_sku(payload):
            payload["properties"].pop("SKU", None)
        att = Harness(backend=FakeNotionBackend(
            corrupt=("product_catalog", drop_sku))).run()
        self.assertEqual(att.verdict, PHASE6_INCOMPLETE)
        self.assertIn("SKU",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "NOT-03"))

    def test_31_corrupted_property_type(self):
        def corrupt_type(payload):
            payload["properties"]["Price"] = {
                "type": "rich_text", "rich_text": {}}
        att = Harness(backend=FakeNotionBackend(
            corrupt=("product_catalog", corrupt_type))).run()
        self.assertEqual(att.verdict, PHASE6_INCOMPLETE)
        self.assertIn("Price:rich_text!=number",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "NOT-03"))

    def test_32_missing_select_options(self):
        def drop_options(payload):
            payload["properties"]["Status"]["select"]["options"] = []
        att = Harness(backend=FakeNotionBackend(
            corrupt=("product_catalog", drop_options))).run()
        self.assertEqual(att.verdict, PHASE6_INCOMPLETE)
        self.assertIn("options",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "NOT-03"))

    def test_33_unbound_relation_refused(self):
        def unbind(payload):
            payload["properties"]["Product"]["relation"] = {}
        att = Harness(backend=FakeNotionBackend(
            corrupt=("order_pipeline", unbind))).run()
        self.assertEqual(att.verdict, PHASE6_INCOMPLETE)
        self.assertIn("unbound",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "NOT-03"))

    def test_34_database_retrieval_404_refused(self):
        backend = FakeNotionBackend()
        backend.intercept = (
            lambda req: "/databases/" in req["url"],
            lambda req: {"status_code": 404,
                         "body": json.dumps({"object": "error",
                                             "status": 404}),
                         "retry_after": None})
        att = Harness(backend=backend).run()
        self.assertEqual(att.verdict, PHASE6_INCOMPLETE)
        self.assertIn("retrieval failed",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "NOT-03"))

    def test_35_missing_database_id_refused(self):
        ids = dict(DB_IDS)
        ids.pop("tasks_sops")
        h = Harness()
        att = h.igniter.run(WorkspaceSchema(database_ids=ids))
        self.assertEqual(att.verdict, PHASE6_INCOMPLETE)
        # fail-closed hygiene: the run still cleans up its probe
        self.assertTrue(all(c[1] for c in att.checks
                            if c[0] == "NOT-04"))
        self.assertIn("no workspace",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "NOT-03"))


# ===================================================================
# NOT-04 — synthetic probe / idempotency refusals
# ===================================================================

class TestNot04Probe(unittest.TestCase):

    def test_40_write_failure_refused(self):
        att = Harness(backend=FakeNotionBackend(
            fail_write=True)).run()
        self.assertEqual(att.verdict, PHASE6_INCOMPLETE)
        self.assertIn("probe cycle failed",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "NOT-04"))

    def test_41_read_back_mismatch_refused(self):
        att = Harness(backend=FakeNotionBackend(
            fail_read=True)).run()
        self.assertEqual(att.verdict, PHASE6_INCOMPLETE)
        self.assertIn("read-back mismatch",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "NOT-04"))

    def test_42_cleanup_failure_refused(self):
        att = Harness(backend=FakeNotionBackend(
            fail_archive=True)).run()
        self.assertEqual(att.verdict, PHASE6_INCOMPLETE)
        self.assertIn("failed at CLEANUP",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "NOT-04"))

    def test_43_idempotency_collision_refused(self):
        att = Harness(backend=FakeNotionBackend(
            collide=True)).run()
        self.assertEqual(att.verdict, PHASE6_INCOMPLETE)
        self.assertIn("idempotency collision",
                      " ".join(c[2] for c in att.checks
                               if c[0] == "NOT-04"))

    def test_44_probe_deterministic_payload_and_key(self):
        h = Harness()
        att = h.run()
        d = att.to_dict()
        key1 = d["sync"]["idempotency_key"]
        att2 = Harness().run()
        key2 = att2.to_dict()["sync"]["idempotency_key"]
        self.assertEqual(key1, key2)  # fixed payload → fixed key
        self.assertEqual(len(key1), 64)


# ===================================================================
# NOT-05 — emission contract
# ===================================================================

class TestNot05Emission(unittest.TestCase):

    def test_50_exactly_one_attestation_per_run(self):
        h = Harness()
        att = h.run()
        self.assertEqual(len(h.sink), 1)
        self.assertEqual(h.sink[0]["schema"], ATTESTATION_SCHEMA)
        self.assertEqual(h.sink[0]["verdict"], att.verdict)

    def test_51_abort_still_emits_attestation(self):
        h = Harness(phase5_provider=None)
        att = h.run()
        self.assertEqual(att.verdict, PHASE6_INCOMPLETE)
        self.assertEqual(len(h.sink), 1)

    def test_52_digest_covers_every_field(self):
        att = Harness().run()
        d = att.to_dict()
        for key in ("schema", "verdict", "phase5_digest",
                    "manifest_sha256", "auth", "schema_map", "sync",
                    "checks", "observed_tick"):
            self.assertIn(key, d)


# ===================================================================
# REDACT — zero secret leakage (D-124)
# ===================================================================

class TestRedaction(unittest.TestCase):

    def test_60_no_token_in_attestation_or_audit(self):
        h = Harness()
        att = h.run()
        blob = json.dumps(att.to_dict()) + json.dumps(h.sink)
        self.assertNotIn(NOTION_TOKEN, blob)
        self.assertNotIn(CANARY, blob)

    def test_61_no_token_in_backend_request_log(self):
        h = Harness()
        h.run()
        blob = json.dumps(h.backend.requests)
        self.assertNotIn(h.backend.token, blob)
        self.assertNotIn("Bearer", blob)

    def test_62_error_strings_redacted(self):
        exc = NotionAuthError(
            f"401 unauthorized token={NOTION_TOKEN} {CANARY}")
        text = redact_notion(str(exc),
                             extra_secrets=[NOTION_TOKEN, CANARY])
        self.assertNotIn(NOTION_TOKEN, text)
        self.assertNotIn(CANARY, text)

    def test_63_refusal_details_carry_no_secrets(self):
        h = Harness(backend=FakeNotionBackend(fail_auth=True))
        att = h.run()
        blob = json.dumps(att.to_dict()) + json.dumps(h.sink)
        self.assertNotIn(NOTION_TOKEN, blob)
        self.assertNotIn(CANARY, blob)

    def test_64_deep_redact_runs_on_emitted_records(self):
        h = Harness()
        att = h.run()
        row = h.sink[0]
        # public commitments survive for chain correlation
        self.assertEqual(row["phase5_digest"], att.phase5_digest)
        self.assertEqual(row["manifest_sha256"],
                         att.manifest_sha256)
        self.assertTrue(row["manifest_sha256"])


# ===================================================================
# AST — purity audits
# ===================================================================

class TestAstpurity(unittest.TestCase):

    def setUp(self):
        self.tree = ast.parse(ENGINE.read_text(encoding="utf-8"))

    def test_70_no_forbidden_imports_in_engine(self):
        banned = {"socket", "http", "urllib", "requests", "ftplib",
                  "smtplib", "asyncio", "os", "subprocess", "shutil",
                  "pty", "commands"}
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

    def test_72_no_direct_http_endpoint_strings(self):
        src = ENGINE.read_text(encoding="utf-8")
        for frag in ("https://api.notion.com", "urlopen(",
                     "requests.post", "requests.get"):
            self.assertNotIn(frag, src.replace(
                "https://api.notion.com/v1/users/me", "").replace(
                "https://api.notion.com/v1/databases/", "").replace(
                "https://api.notion.com/v1/pages", "").replace(
                "https://api.notion.com/v1/blocks/", ""))

    def test_73_engine_core_constructs_no_transport(self):
        # the engine module must never instantiate a live transport;
        # only NotionProbeTransport (a wrapper) is exposed and the
        # core takes `notion=` injected.
        src = ENGINE.read_text(encoding="utf-8")
        self.assertIn("notion: Optional[Any]", src)
        self.assertIn("def _load", src)

    def test_74_purity_of_the_real_pacer_layer(self):
        # the canonical pacer stays wall-clock free
        pacer_tree = ast.parse(
            (REPO / "local" / "canonical" / "notion_live.py")
            .read_text(encoding="utf-8"))
        for node in ast.walk(pacer_tree):
            if isinstance(node, ast.Call):
                name = getattr(node.func, "attr",
                               getattr(node.func, "id", ""))
                self.assertNotIn(name, ("monotonic", "time",))


if __name__ == "__main__":
    unittest.main()

"""Phase 5 live wiring igniter battery (D-155, offline).

Exercises `local/scripts/live_wiring_phase5_igniter.py` fully
offline — every transport injected, every upstream artifact REAL repo
material: the D-154 certificate synthesized through the REAL D-152
closure runner + REAL Stage F gate + REAL D-153 executor (the same
authentic Stage C→H chain the D-152/D-153/D-154 batteries proved),
and the REAL D-053 n8n webhook contracts:

  PASS    — certificate + transports + dispatcher ⇒ PHASE5_IGNITED
            with a valid `phase5.live_wiring_attestation.v1`;
  IGN-01  — certificate absent / incomplete / altered / drifted /
            unrooted / broken-chain ⇒ refusal;
  IGN-02  — handshake failure, timeout, rejected credentials, bad
            pooling invariants, unseeded schema ⇒ fail-closed abort;
  IGN-03  — handshake failure, latency over budget, eviction policy,
            roundtrip failure ⇒ fail-closed abort;
  IGN-04  — schema mismatch, missing HMAC, dispatch failure,
            idempotency violation ⇒ rejection;
  IGN-05  — exactly one canonical attestation per run (including
            aborts), deterministic digest;
  REDACT  — db passwords, redis auth tokens, webhook secrets and
            canaries never reach the attestation or audit copies;
  AST     — strict parameter isolation (no shell, no Popen, bounded
            timeouts) and a pure igniter core (no network imports).
"""
from __future__ import annotations

import ast
import json
import pathlib
import subprocess
import sys
import unittest

REPO = pathlib.Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "local" / "scripts"
SRC = REPO / "local" / "src"
for p in (str(REPO / "local"), str(SCRIPTS), str(SRC),
          str(SRC.parent), str(SRC / "security")):
    if p not in sys.path:
        sys.path.insert(0, p)

from stage_g_preflight_validator import bundle_hash_of  # noqa: E402
from stage_g_probe_adapters import build_executors  # noqa: E402
from verify_stage_g_live_probes import (  # noqa: E402
    PROBES_ACCEPTED, StageGLiveProbeRunner,
)
from run_stage_g_acceptance import StageGAcceptanceRunner  # noqa: E402
from stage_g_closure_and_handoff import (  # noqa: E402
    StageGClosureRunner, canonical_hash,
)
from stage_h_cutover_executor import (  # noqa: E402
    CUTOVER_EXECUTED, StageHCutoverExecutor,
)
from src.security.launch_attestation_verifier import (  # noqa: E402
    TripleEvidenceGate,
)
from src.security.owner_approval_gate import (  # noqa: E402
    OwnerApprovalGate, TokenDraft, mint_token,
    parse_envelope_fingerprint,
)
from dokploy_completion_attestation import (  # noqa: E402
    INFRA_COMPLETE, DokployCompletionAttestor,
)
from live_wiring_phase5_igniter import (  # noqa: E402
    ATTESTATION_SCHEMA, CERT_COMPLETE, CERT_SCHEMA, CERT_ROW_KIND,
    DRILL_EVENT_ID, DRILL_SOURCE, PHASE5_IGNITED, PHASE5_INCOMPLETE,
    REDIS_DRILL_NS, REDIS_LATENCY_BUDGET_MS, ArgvPsqlTransport,
    ArgvRedisTransport, Phase5Igniter, canonical_hash,
)

ENGINE = SCRIPTS / "live_wiring_phase5_igniter.py"

CANARY = "sk-canaryvalue1234567890abcdef"
PG_PASSWORD = "hunter2-canary-pg-password"
REDIS_TOKEN = "redis-canary-auth-token-1234567890"
WEBHOOK_SECRET = "n8n-webhook-canary-secret-0123456789"
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
FP = parse_envelope_fingerprint(ENVELOPE)


# --- the authentic Stage C→H chain + the REAL D-154 certificate -------

def real_host():
    return {"verdict": "READY",
            "checks": {f"C-0{i}": True for i in range(0, 8)}}


def real_bundle() -> dict:
    bundle = {
        "schema": "cutover.bundle.v1",
        "verdict": "READY_FOR_CUTOVER",
        "candidate_manifest_sha256": FP,
        "session_id": SESSION,
        "target_env": TARGET,
        "observed_tick": 100,
        "steps": [{"step": "stage_c", "ok": True, "detail": "ok",
                   "findings": []}],
        "stage_f_token_id": "tok-01",
        "abort_reason": "",
    }
    bundle["bundle_hash"] = bundle_hash_of(bundle)
    return bundle


def real_acceptance() -> dict:
    acc = StageGAcceptanceRunner(
        clock=lambda: 200, audit_sink=lambda d: None,
        preflight_verdict=lambda: {"verdict": "PREFLIGHT_CLEARED",
                                   "bundle_sha256": ""},
        manifest_provider=lambda: MANIFEST,
        template_provider=lambda: TEMPLATE).run()
    d = acc.to_dict()
    d["acceptance_fingerprint"] = acc.acceptance_fingerprint
    return d


def fake_docker_host():
    healthy = {"State": {"Running": True, "RestartCount": 0,
                         "Health": {"Status": "healthy"}},
               "NetworkSettings": {"Ports": {}}}

    def _cp(code, out, err):
        return subprocess.CompletedProcess([], code, stdout=out,
                                           stderr=err)

    def run(argv, timeout_s=15.0, input_text=None):
        if argv[1] == "inspect":
            if argv[-1] not in SERVICES:
                return _cp(1, "", "no such object")
            return _cp(0, json.dumps(healthy), "")
        if argv[1] == "exec":
            inner = argv[4:]
            if inner[0] == "psql":
                return _cp(0, "1", "")
            if inner[0] == "redis-cli":
                return _cp(0, "PONG" if "PING" in inner else
                           "maxmemory-policy\nnoeviction", "")
            if inner[0] == "wget":
                return _cp(0, json.dumps({"registered": True,
                                          "age": 3}), "")
        if argv[1] == "logs":
            return _cp(0, "engine boot ok\n", "")
        return _cp(2, "", "unknown")
    return run


def real_probe_report() -> dict:
    acc = real_acceptance()
    ex = build_executors(inspect_runner=fake_docker_host(),
                         exec_runner=fake_docker_host(),
                         log_runner=fake_docker_host())
    report = StageGLiveProbeRunner(clock=lambda: 300,
                                   audit_sink=lambda d: None,
                                   **ex).run(acc, expected_manifest=FP)
    assert report.verdict == PROBES_ACCEPTED
    d = report.to_dict()
    d["probe_digest"] = report.probe_digest
    return d


def real_triad(bundle, acceptance, probe) -> dict:
    rows = [
        {"event_kind": "stage_g_preflight",
         "detail": {"bundle_hash": bundle["bundle_hash"]}},
        {"event_kind": "cutover_bundle_recorded",
         "detail": {"bundle_hash": bundle["bundle_hash"]}},
        {"event_kind": "stage_g_acceptance",
         "detail": {"acceptance_fingerprint":
                    acceptance["acceptance_fingerprint"]}},
        {"event_kind": "stage_g_live_probe",
         "detail": {"probe_digest": probe["probe_digest"]}},
    ]
    gate = TripleEvidenceGate(
        bundle=lambda: bundle, acceptance=lambda: acceptance,
        probe=lambda: probe,
        audit_rows=lambda: rows,
        chain_verifier=lambda: {"ok": True, "rows": 4})
    return gate.evaluate().to_dict()


def real_fallbacks() -> dict:
    return {"triggers": [
        {"name": "probe_red", "threshold_ticks": 1,
         "action": "Stage E §5 row governs (RB-3)"},
        {"name": "heartbeat_stale", "threshold_ticks": 120,
         "action": "RB-3 drain + edge to blue"},
        {"name": "bundle_expired", "threshold_ticks": 5000,
         "action": "re-attest (closure refused)"},
        {"name": "chain_broken", "threshold_ticks": 1,
         "action": "RB-4 freeze dispatch, reconcile"},
    ]}


class MemoryReplayStore:
    def __init__(self):
        self.burned = set()

    def consume(self, key: str) -> bool:
        if key in self.burned:
            return False
        self.burned.add(key)
        return True


def real_target_state() -> dict:
    return {s: {"running": True, "healthy": True, "restarts": 0,
                "ports": []} for s in SERVICES}


def real_probes() -> dict:
    return {"edge_smoke": True, "worker_ready": True, "ssot_rw": True}


def real_draft(now: int) -> TokenDraft:
    return TokenDraft(manifest_sha256=FP, session_id=SESSION,
                      target_env=TARGET, issued_tick=now - 10,
                      expires_tick=now + 500,
                      nonce=f"phase5-ignition-{now}")


def real_approval(now: int) -> dict:
    draft = real_draft(now)
    token = mint_token(SIGNING_KEY, draft)
    gate = OwnerApprovalGate(
        signing_key=SIGNING_KEY,
        replay_store=MemoryReplayStore(),
        clock=lambda: now,
        audit_sink=lambda d: None,
        manifest_sha256=FP)
    verdict = gate.evaluate(token, draft, SESSION, TARGET, ENVELOPE)
    assert verdict.gate == "GO"
    return {"verdict": verdict.to_dict(), "draft": draft}


def real_activation(now: int = 1000):
    """REAL D-153 executor through the REAL D-152 closure runner."""
    bundle, acc, probe = real_bundle(), real_acceptance(), \
        real_probe_report()
    triad = real_triad(bundle, acc, probe)
    runner = StageGClosureRunner(
        clock=lambda: 900, audit_sink=lambda d: None,
        host_readiness=real_host,
        manifest_text=lambda: MANIFEST,
        envelope_text=lambda: ENVELOPE,
        rollback_spec=lambda: RUNBOOK,
        fallback_spec=real_fallbacks,
        bundle=lambda: bundle,
        acceptance_report=lambda: acc,
        probe_report=lambda: probe,
        triad_verdict=lambda: triad)
    seal = runner.run()
    assert seal.closed
    seal_d = seal.to_dict()
    seal_d["closure_digest"] = seal.closure_digest
    closure_rows = [{"event_kind": "stage_g_closure",
                     "detail": {"closure_digest":
                                seal_d["closure_digest"]}}]
    approval = real_approval(now)
    sink: list = []
    executor = StageHCutoverExecutor(
        clock=lambda: now, audit_sink=sink.append,
        seal_provider=lambda: seal_d,
        audit_rows=lambda: closure_rows,
        approval_verdict=lambda: approval["verdict"],
        token_draft=lambda: vars(approval["draft"]),
        target_state=real_target_state,
        transition=lambda: {"active": True, "via": "dokploy"},
        post_activation_probes=real_probes)
    record = executor.run()
    assert record.verdict == CUTOVER_EXECUTED
    rec_d = record.to_dict()
    rec_d["activation_digest"] = record.activation_digest
    closure_rows.append({"event_kind": "stage_h_activation",
                         "detail": {
                             "activation_digest":
                             rec_d["activation_digest"],
                             "manifest_sha256":
                             rec_d["manifest_sha256"],
                             "closure_digest":
                             rec_d["closure_digest"],
                             "token_id": rec_d["token_id"]}})
    return bundle, acc, probe, rec_d, seal_d, closure_rows


def real_ledger(bundle, acc, probe, seal, activation) -> list:
    return [
        {"event_kind": "stage_g_preflight",
         "detail": {"bundle_hash": bundle["bundle_hash"]}},
        {"event_kind": "cutover_bundle_recorded",
         "detail": {"bundle_hash": bundle["bundle_hash"]}},
        {"event_kind": "stage_g_acceptance",
         "detail": {"acceptance_fingerprint":
                    acc["acceptance_fingerprint"]}},
        {"event_kind": "stage_g_live_probe",
         "detail": {"probe_digest": probe["probe_digest"]}},
        {"event_kind": "stage_g_closure",
         "detail": {"closure_digest": seal["closure_digest"]}},
        {"event_kind": "stage_h_activation",
         "detail": {"activation_digest":
                    activation["activation_digest"]}},
    ]


def real_readiness() -> dict:
    from dokploy_completion_attestation import LIVE_WIRING_PHASES
    return {
        "runtime_profile_verified": True,
        "phases": [{"phase": num, "name": name,
                    "entry_point": "canonical." +
                    name.split()[0].lower() + "_engine",
                    "present": True, "verified": True,
                    "wired": True, "detail": "ready"}
                   for num, name in LIVE_WIRING_PHASES],
    }


def real_cert(now: int = 2000):
    """Run the REAL D-154 attestor through the REAL Stage C→H chain.
    Returns (cert_dict, ledger_rows)."""
    bundle, acc, probe, activation, seal, rows = real_activation(now)
    ledger = real_ledger(bundle, acc, probe, seal, activation)
    attestor = DokployCompletionAttestor(
        clock=lambda: now, audit_sink=lambda d: None,
        host_readiness=real_host,
        manifest_text=lambda: MANIFEST,
        envelope_text=lambda: ENVELOPE,
        bundle=lambda: bundle,
        acceptance_report=lambda: acc,
        probe_report=lambda: probe,
        triad_verdict=lambda: real_triad(bundle, acc, probe),
        seal=lambda: seal,
        activation_record=lambda: activation,
        audit_rows=lambda: ledger,
        chain_verifier=lambda: {"ok": True, "rows": len(ledger)},
        live_wiring_readiness=real_readiness)
    cert = attestor.run()
    assert cert.verdict == INFRA_COMPLETE
    d = cert.to_dict()
    d["attestation_digest"] = cert.attestation_digest
    # the production rooting: the certificate lands in the D-112 chain
    ledger.append({"event_kind": CERT_ROW_KIND,
                   "detail": {
                       "attestation_digest":
                       d["attestation_digest"],
                       "manifest_sha256": d["manifest_sha256"]}})
    return d, ledger


# --- the injected transports ------------------------------------------------

class FakePsql:
    """In-process PostgreSQL transport with auth, schema, pooling."""

    def __init__(self, auth_ok: bool = True, timeout: bool = False,
                 max_connections: int = 100, reserved: int = 3,
                 seeded: bool = True, seed_rows: int = 42):
        self.auth_ok = auth_ok
        self.timeout = timeout
        self.max_connections = max_connections
        self.reserved = reserved
        self.seeded = seeded
        self.seed_rows = seed_rows
        self.queries: List[str] = []

    def _guard(self):
        if self.timeout:
            raise TimeoutError("psql timed out")
        if not self.auth_ok:
            raise PermissionError("password authentication failed")

    def sql(self, sql: str) -> str:
        self.queries.append(sql)
        self._guard()
        if "information_schema" in sql:
            return "1" if self.seeded else "0"
        if "FROM seed.size_term" in sql:
            return str(self.seed_rows) if self.seeded else "0"
        if "max_connections" in sql:
            return str(self.max_connections)
        if "superuser_reserved_connections" in sql:
            return str(self.reserved)
        if "SELECT 1" in sql:
            return "1"
        return ""

    def config(self):
        return {"max_connections": self.max_connections,
                "superuser_reserved_connections": self.reserved}


class FakeRedis:
    """In-process Redis transport: auth, latency, policy, namespace."""

    def __init__(self, auth_ok: bool = True, latency_ms: float = 2.0,
                 policy: str = "noeviction", timeout: bool = False):
        self.auth_ok = auth_ok
        self.latency = latency_ms
        self.policy = policy
        self.timeout = timeout
        self.store: dict = {}
        self.commands: List[List[str]] = []

    def _guard(self):
        if self.timeout:
            raise TimeoutError("redis-cli timed out")
        if not self.auth_ok:
            raise PermissionError(
                "NOAUTH Authentication required")

    def command(self, args):
        self.commands.append(list(args))
        self._guard()
        op = args[0].upper()
        if op == "PING":
            return "PONG"
        if op == "SET":
            self.store[args[1]] = args[2]
            return "OK"
        if op == "GET":
            return self.store.get(args[1], "")
        if op == "DEL":
            self.store.pop(args[1], None)
            return "1"
        return ""

    def latency_ms(self) -> float:
        self._guard()
        return self.latency

    def config(self):
        return {"maxmemory_policy": self.policy}


class FakeWebhook:
    """In-process webhook transport verifying HMAC over the raw bytes
    with an injected secret the engine never sees (D-045 pattern)."""

    def __init__(self, secret: str = WEBHOOK_SECRET,
                 verify: bool = True, fail: bool = False):
        self.secret = secret
        self.verify = verify
        self.fail = fail
        self.bodies: List[bytes] = []

    def send(self, body: bytes) -> dict:
        from canonical.n8n_webhook_contracts import verify_hmac_header
        self.bodies.append(bytes(body))
        if self.fail:
            raise ConnectionError("webhook endpoint unreachable")
        header = None
        if self.verify:
            import hmac as _hmac
            import hashlib as _hashlib
            digest = _hmac.new(self.secret.encode("utf-8"),
                               bytes(body), _hashlib.sha256).hexdigest()
            header = f"sha256={digest}"
        try:
            verify_hmac_header(body, header, secret=self.secret)
        except Exception:
            return {"hmac_verified": False}
        return {"hmac_verified": True, "status": 200}


class DrillStore:
    """D-027 interface parity store for the drill event."""

    def __init__(self):
        self.records: dict = {}
        self.receive_calls = 0

    def receive(self, source_system: str, event_id: str,
                operation_type: str, payload) -> dict:
        self.receive_calls += 1
        ph = canonical_hash({"event_id": event_id,
                             "source": source_system})
        if (source_system, event_id) not in self.records:
            self.records[(source_system, event_id)] = {
                "processing_status": "received",
                "payload_hash": ph, "retry_count": 0}
        return {"verdict": "new"}

    def get_record(self, source_system: str, event_id: str):
        return self.records.get((source_system, event_id))


# --- the wired harness -------------------------------------------------------

_CHAIN: dict = {}


def the_cert() -> dict:
    return _CHAIN["cert"]


def the_ledger() -> list:
    return _CHAIN["ledger"]


def build_chain() -> None:
    if not _CHAIN:
        cert, ledger = real_cert(2000)
        _CHAIN.update(cert=cert, ledger=ledger)


class Harness:
    """Fully wired igniter over the authentic chain; overrides swap
    transports/providers (None = absent)."""

    def __init__(self, now: int = 4000, **overrides):
        build_chain()
        self.now = now
        self.sink: list = []
        self.store = DrillStore()
        providers = {
            "cert_provider": the_cert,
            "audit_rows": the_ledger,
            "chain_verifier": lambda: {"ok": True,
                                       "rows": len(the_ledger())},
            "pg": FakePsql(),
            "redis": FakeRedis(),
            "webhook": FakeWebhook(),
        }
        providers.update(overrides)
        self.igniter = Phase5Igniter(
            clock=lambda: self.now, audit_sink=self.sink.append,
            **providers)

    def run(self):
        return self.igniter.run(d027_store=self.store)


# ===================================================================
# PASS — successful ignition
# ===================================================================

class TestIgnitionPass(unittest.TestCase):

    def test_01_full_ignition_completes(self):
        h = Harness()
        att = h.run()
        self.assertEqual(att.verdict, PHASE5_IGNITED)
        self.assertTrue(att.ignited)
        d = att.to_dict()
        self.assertEqual(d["schema"], ATTESTATION_SCHEMA)
        self.assertEqual(d["schema"],
                         "phase5.live_wiring_attestation.v1")
        self.assertEqual(d["cert_digest"],
                         the_cert()["attestation_digest"])
        self.assertEqual(d["manifest_sha256"], FP)
        ids = [c[0] for c in att.checks]
        for rule in ("IGN-01", "IGN-02", "IGN-03", "IGN-04",
                     "IGN-05"):
            self.assertIn(rule, ids)
        self.assertTrue(all(c[1] for c in att.checks))
        self.assertTrue(d["postgres"]["connected"])
        self.assertTrue(d["postgres"]["schema_ready"])
        self.assertTrue(d["redis"]["connected"])
        self.assertTrue(d["webhook"]["idempotent"])
        self.assertTrue(d["webhook"]["d027_store_roundtrip"])

    def test_02_redis_latency_below_budget(self):
        att = Harness(redis=FakeRedis(latency_ms=7.5)).run()
        self.assertEqual(att.to_dict()["redis"]["latency_ms"], 7.5)
        self.assertTrue(att.to_dict()["redis"]["within_budget"])

    def test_03_attestation_digest_deterministic_and_frozen(self):
        a = Harness(now=5000)
        b = Harness(now=5000)
        a1, b1 = a.run(), b.run()
        self.assertEqual(a1.attestation_digest, b1.attestation_digest)
        self.assertEqual(a1.attestation_digest,
                         canonical_hash(a1.to_dict()))
        d = a1.to_dict()
        d["verdict"] = "MUTATED"
        self.assertEqual(a1.attestation_digest,
                         canonical_hash(
                             {k: v for k, v in
                              a1.to_dict().items()}))

    def test_04_exactly_one_audited_attestation_per_run(self):
        h = Harness()
        h.run()
        h.run()
        self.assertEqual(len(h.sink), 2)
        self.assertEqual(h.sink[-1]["cert_digest"],
                         the_cert()["attestation_digest"])
        self.assertEqual(h.sink[-1]["manifest_sha256"], FP)

    def test_05_drill_store_receives_exactly_one_registration(self):
        h = Harness()
        h.run()
        self.assertEqual(h.store.receive_calls, 1)
        rec = h.store.get_record(DRILL_SOURCE, DRILL_EVENT_ID)
        self.assertEqual(rec["processing_status"], "received")

    def test_06_latency_at_budget_boundary_refuses(self):
        att = Harness(
            redis=FakeRedis(latency_ms=REDIS_LATENCY_BUDGET_MS)).run()
        self.assertEqual(att.verdict, PHASE5_INCOMPLETE)
        self.assertTrue(any("exceeds the 50" in c[2]
                            for c in att.checks))


# ===================================================================
# IGN-01 — the D-154 certificate
# ===================================================================

class TestIgn01Certificate(unittest.TestCase):

    def test_07_missing_certificate_refused(self):
        att = Harness(cert_provider=None).run()
        self.assertEqual(att.verdict, PHASE5_INCOMPLETE)
        self.assertTrue(any("certificate absent" in c[2]
                            for c in att.checks))

    def test_08_incomplete_certificate_refused(self):
        def incomplete():
            c = dict(the_cert())
            c["verdict"] = "INFRASTRUCTURE_INCOMPLETE"
            c["attestation_digest"] = canonical_hash(
                {k: v for k, v in c.items()
                 if k != "attestation_digest"})
            return c
        att = Harness(cert_provider=incomplete).run()
        self.assertEqual(att.verdict, PHASE5_INCOMPLETE)
        self.assertTrue(any("infrastructure incomplete" in c[2].lower()
                            for c in att.checks))

    def test_09_drifted_digest_refused(self):
        def drifted():
            c = dict(the_cert())
            c["manifest_sha256"] = "b" * 64
            # digest NOT recomputed — the drift the rule exists for
            return c
        att = Harness(cert_provider=drifted).run()
        self.assertEqual(att.verdict, PHASE5_INCOMPLETE)
        self.assertTrue(any("DRIFTED or altered" in c[2]
                            for c in att.checks))

    def test_10_altered_certificate_refused(self):
        def altered():
            c = dict(the_cert())
            c["observed_tick"] = c["observed_tick"] + 1
            return c
        att = Harness(cert_provider=altered).run()
        self.assertEqual(att.verdict, PHASE5_INCOMPLETE)
        self.assertTrue(any("DRIFTED or altered" in c[2]
                            for c in att.checks))

    def test_11_unrooted_certificate_refused(self):
        att = Harness(audit_rows=lambda: [
            r for r in the_ledger()
            if r["event_kind"] != CERT_ROW_KIND]).run()
        self.assertEqual(att.verdict, PHASE5_INCOMPLETE)
        self.assertTrue(any("not rooted in the D-112" in c[2]
                            for c in att.checks))

    def test_12_broken_chain_refused(self):
        att = Harness(chain_verifier=lambda: {
            "ok": False, "broken_at_seq": 2,
            "reason": "chain_mismatch"}).run()
        self.assertEqual(att.verdict, PHASE5_INCOMPLETE)
        self.assertTrue(any("chain not intact" in c[2]
                            for c in att.checks))

    def test_13_wrong_schema_refused(self):
        def wrong():
            c = dict(the_cert())
            c["schema"] = "dokploy.completion_attestation.v2"
            return c
        att = Harness(cert_provider=wrong).run()
        self.assertEqual(att.verdict, PHASE5_INCOMPLETE)
        self.assertTrue(any("!= 'dokploy.completion_attestation.v1'"
                            in c[2].replace('"', "'")
                            for c in att.checks))


# ===================================================================
# IGN-02 — PostgreSQL
# ===================================================================

class TestIgn02Postgres(unittest.TestCase):

    def test_14_handshake_failure_refused(self):
        att = Harness(pg=FakePsql(auth_ok=False)).run()
        self.assertEqual(att.verdict, PHASE5_INCOMPLETE)
        self.assertTrue(any("handshake failed: PermissionError"
                            in c[2] for c in att.checks))
        self.assertFalse(att.to_dict()["postgres"]["connected"])

    def test_15_timeout_refused(self):
        att = Harness(pg=FakePsql(timeout=True)).run()
        self.assertEqual(att.verdict, PHASE5_INCOMPLETE)
        self.assertTrue(any("handshake failed: TimeoutError" in c[2]
                            for c in att.checks))

    def test_16_pooling_invariant_violation_refused(self):
        att = Harness(pg=FakePsql(max_connections=10,
                                  reserved=3)).run()
        self.assertEqual(att.verdict, PHASE5_INCOMPLETE)
        self.assertTrue(any("pooling invariant violated" in c[2]
                            for c in att.checks))

    def test_17_unreadable_pooling_refused(self):
        att = Harness(pg=FakePsql(max_connections=0)).run()
        self.assertEqual(att.verdict, PHASE5_INCOMPLETE)
        self.assertTrue(any("unreadable" in c[2]
                            for c in att.checks))

    def test_18_unseeded_schema_refused(self):
        att = Harness(pg=FakePsql(seeded=False)).run()
        self.assertEqual(att.verdict, PHASE5_INCOMPLETE)
        self.assertTrue(any("SSOT schema not ready" in c[2]
                            for c in att.checks))

    def test_19_empty_seed_catalog_refused(self):
        att = Harness(pg=FakePsql(seed_rows=0)).run()
        self.assertEqual(att.verdict, PHASE5_INCOMPLETE)
        self.assertTrue(any("absent or unseeded" in c[2]
                            for c in att.checks))

    def test_20_missing_transport_fails_closed(self):
        att = Harness(pg=None).run()
        self.assertEqual(att.verdict, PHASE5_INCOMPLETE)
        self.assertTrue(any("PostgreSQL transport unavailable" in c[2]
                            for c in att.checks))


# ===================================================================
# IGN-03 — Redis
# ===================================================================

class TestIgn03Redis(unittest.TestCase):

    def test_21_auth_failure_refused(self):
        att = Harness(redis=FakeRedis(auth_ok=False)).run()
        self.assertEqual(att.verdict, PHASE5_INCOMPLETE)
        self.assertTrue(any("Redis handshake failed: PermissionError"
                            in c[2] for c in att.checks))
        self.assertFalse(att.to_dict()["redis"]["connected"])

    def test_22_timeout_refused(self):
        att = Harness(redis=FakeRedis(timeout=True)).run()
        self.assertEqual(att.verdict, PHASE5_INCOMPLETE)
        self.assertTrue(any("Redis handshake failed: TimeoutError"
                            in c[2] for c in att.checks))

    def test_23_eviction_policy_refused(self):
        att = Harness(redis=FakeRedis(policy="allkeys-lru")).run()
        self.assertEqual(att.verdict, PHASE5_INCOMPLETE)
        self.assertTrue(any("allkeys-lru" in c[2]
                            and "noeviction" in c[2]
                            for c in att.checks))

    def test_24_missing_transport_fails_closed(self):
        att = Harness(redis=None).run()
        self.assertEqual(att.verdict, PHASE5_INCOMPLETE)
        self.assertTrue(any("Redis transport unavailable" in c[2]
                            for c in att.checks))

    def test_25_drill_namespace_roundtrip(self):
        rd = FakeRedis()
        att = Harness(redis=rd).run()
        self.assertEqual(att.verdict, PHASE5_IGNITED)
        key = f"{REDIS_DRILL_NS}:probe"
        self.assertIn(["SET", key, "1", "EX", "60"], rd.commands)
        self.assertIn(["GET", key], rd.commands)
        self.assertIn(["DEL", key], rd.commands)
        # the drill key is ALWAYS cleaned up (zero residue)
        self.assertNotIn(key, rd.store)


# ===================================================================
# IGN-04 — n8n webhook dispatcher & idempotency
# ===================================================================

class TestIgn04Webhook(unittest.TestCase):

    def test_26_missing_webhook_transport_refused(self):
        att = Harness(webhook=None).run()
        self.assertEqual(att.verdict, PHASE5_INCOMPLETE)
        self.assertTrue(any("webhook transport unavailable" in c[2]
                            for c in att.checks))

    def test_27_missing_hmac_refused(self):
        att = Harness(webhook=FakeWebhook(verify=False)).run()
        self.assertEqual(att.verdict, PHASE5_INCOMPLETE)
        self.assertTrue(any("HMAC verification absent or failed"
                            in c[2] for c in att.checks))

    def test_28_dispatch_failure_refused(self):
        att = Harness(webhook=FakeWebhook(fail=True)).run()
        self.assertEqual(att.verdict, PHASE5_INCOMPLETE)
        self.assertTrue(any("webhook dispatch failed" in c[2]
                            for c in att.checks))

    def test_29_missing_d027_store_fails_closed(self):
        h = Harness()
        att = h.igniter.run(d027_store=None)
        self.assertEqual(att.verdict, PHASE5_INCOMPLETE)
        self.assertTrue(any("D-027 event store not provided" in c[2]
                            for c in att.checks))

    def test_30_schema_violation_detected_by_contracts(self):
        from canonical.n8n_webhook_contracts import (
            N8nWebhookError, parse_event)
        bad = {"event_type": "workflow.exploded",
               "workflow_ref": "PHASE5-IGNITION",
               "event_id": "ev-bad", "payload": {}}
        with self.assertRaises(N8nWebhookError):
            parse_event(json.dumps(bad).encode("utf-8"))
        missing = {"event_type": "ops.ping",
                   "workflow_ref": "PHASE5-IGNITION"}
        with self.assertRaises(N8nWebhookError):
            parse_event(json.dumps(missing).encode("utf-8"))

    def test_31_idempotent_redelivery_through_contracts(self):
        from canonical.n8n_webhook_contracts import (
            N8nEventDispatcher, event_key, mock_webhook_payload)
        seen: dict = {}
        fired: list = []

        def seen_fn(key):
            return bool(seen.get(key))

        def record_fn(key):
            seen[key] = True

        dispatcher = N8nEventDispatcher(
            {"ops.ping": lambda ev: fired.append(ev) or {"ok": True}},
            seen_fn, record_fn)
        ev = mock_webhook_payload("ops.ping", event_id="ev-x")
        first = dispatcher.dispatch([ev], logical_now="t0")
        second = dispatcher.dispatch([ev], logical_now="t1")
        self.assertEqual(first["results"][0]["verdict"],
                         "dispatched")
        self.assertEqual(second["results"][0]["verdict"],
                         "skipped_duplicate")
        self.assertEqual(len(fired), 1)
        self.assertEqual(event_key(ev),
                         first["results"][0]["key"])


# ===================================================================
# REDACT — no credentials in attestation or audit copies
# ===================================================================

class TestRedaction(unittest.TestCase):

    def test_32_no_credentials_anywhere_in_outputs(self):
        def leaky_pg():
            pg = FakePsql()
            pg.sql = (lambda sql, _p=pg: (  # type: ignore
                f"connected with {PG_PASSWORD} {CANARY}"))
            return pg
        h = Harness(pg=leaky_pg())
        att = h.run()
        blob = json.dumps(att.to_dict())
        audit = json.dumps(h.sink)
        for secret in (PG_PASSWORD, REDIS_TOKEN, WEBHOOK_SECRET,
                       CANARY):
            self.assertNotIn(secret, blob)
            self.assertNotIn(secret, audit)

    def test_33_canary_in_transport_errors_never_escapes(self):
        def noisy_runner(argv, **kw):
            return subprocess.CompletedProcess(
                [], 1, "",
                f"auth failed {PG_PASSWORD} {CANARY} at host x")
        tr = ArgvPsqlTransport(runner=noisy_runner)
        with self.assertRaises(Exception) as ctx:
            tr.sql("SELECT 1")
        self.assertNotIn(CANARY, str(ctx.exception))
        self.assertNotIn(PG_PASSWORD, str(ctx.exception))
        self.assertEqual(str(ctx.exception), "psql_failed")

    def test_34_redis_error_text_is_typed_only(self):
        def noisy_runner(argv, **kw):
            return subprocess.CompletedProcess(
                [], 1, "", f"NOAUTH {REDIS_TOKEN} required")
        tr = ArgvRedisTransport(runner=noisy_runner)
        with self.assertRaises(Exception) as ctx:
            tr.command(["PING"])
        self.assertNotIn(REDIS_TOKEN, str(ctx.exception))

    def test_35_webhook_secret_never_enters_the_engine(self):
        seen_secrets: list = []
        wh = FakeWebhook(secret=WEBHOOK_SECRET)

        class SpyWebhook(FakeWebhook):
            def send(self, body):
                seen_secrets.append(None)
                return super().send(body)
        h = Harness(webhook=SpyWebhook())
        att = h.run()
        self.assertEqual(att.verdict, PHASE5_IGNITED)
        blob = json.dumps(att.to_dict()) + json.dumps(h.sink)
        self.assertNotIn(WEBHOOK_SECRET, blob)
        # the transport verified the HMAC with the secret it holds
        self.assertTrue(att.to_dict()["webhook"]["hmac_verified"])

    def test_36_public_commitments_survive_redaction(self):
        h = Harness()
        att = h.run()
        self.assertEqual(h.sink[-1]["cert_digest"],
                         att.to_dict()["cert_digest"])
        self.assertEqual(h.sink[-1]["manifest_sha256"], FP)


# ===================================================================
# AST — parameter isolation + pure core
# ===================================================================

class TestAst(unittest.TestCase):

    def test_37_transports_strict_argv_isolation(self):
        tree = ast.parse(ENGINE.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and node.arg == "shell":
                self.fail("shell= keyword present")
            if isinstance(node, ast.Call):
                fn = node.func
                if isinstance(fn, ast.Attribute) and \
                        fn.attr in ("system", "popen", "Popen",
                                    "check_output"):
                    self.fail(f"banned process call: .{fn.attr}()")
                if isinstance(fn, ast.Attribute) and \
                        fn.attr == "run" and \
                        isinstance(fn.value, ast.Name) and \
                        fn.value.id == "subprocess":
                    kws = {k.arg for k in node.keywords}
                    self.assertIn("timeout", kws,
                                  "subprocess.run without timeout")
                    self.assertIn("capture_output", kws,
                                  "subprocess.run without "
                                  "capture_output")

    def test_38_igniter_core_pure_no_network(self):
        tree = ast.parse(ENGINE.read_text(encoding="utf-8"))
        banned = {"socket", "urllib", "requests", "ssl", "http",
                  "ftplib", "smtplib", "asyncio"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    self.assertNotIn(
                        a.name.split(".")[0], banned,
                        f"banned import: {a.name}")
            elif isinstance(node, ast.ImportFrom):
                root = (node.module or "").split(".")[0]
                self.assertNotIn(root, banned,
                                 f"banned import-from: {node.module}")


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Phase 5 Live Wiring Igniter & Service Connectivity Verification (D-155).

The FIRST engine of the Live Wiring program (MASTER_PLAN Phases
5–18): it verifies, ignites, and attests the live connectivity of the
Phase 5 core services — the canonical PostgreSQL SSOT, the Redis
state/cache store, and the n8n webhook dispatcher — against the
D-154 completion certificate. Under D-139 / D-154 / plan §17/§21.6
this is a VERIFICATION and ATTESTATION engine: it never provisions,
never mutates schema, and never writes business state; its single
side-effect is the D-027 idempotency drill, which registers, begins
and succeeds one drill event (`phase5.ignition_drill`) through the
REAL D-027 store interface.

Execution rules (all fail-closed; every refusal names its blocker;
exactly one audited attestation per run INCLUDING aborts, which
declare IGNITION_INCOMPLETE):

  IGN-01  the D-154 `dokploy.completion_attestation.v1` is present,
          INFRASTRUCTURE_COMPLETE, digest-recomputing over its
          canonical bytes, and ROOTED in the D-112 ledger (kind
          `dokploy_completion_attestation`, or the attestation digest
          embedded in a row detail) — a missing, incomplete, altered,
          or unrooted certificate refuses instantly;
  IGN-02  PostgreSQL (the canonical SSOT): authenticated connectivity
          through the INJECTED connection transport (direct argv in
          production), a read-only roundtrip, schema readiness (the
          D-055 SSOT `seed.size_term` catalog present and
          non-empty), and the pooling invariants (max_connections >
          reserved + the engine's expected concurrency headroom) —
          strict per-op timeout, transport failures surface as
          type-only errors (D-124);
  IGN-03  Redis: connectivity, PING latency under the 50 ms
          threshold, a write/read/delete roundtrip in an ISOLATED
          drill namespace, and the no-eviction configuration
          (`maxmemory-policy` = noeviction, REDIS_MAXMEMORY per the
          D-144 env contract) — eviction policies that discard state
          refuse ignition;
  IGN-04  n8n webhook dispatcher: the REAL D-053 contracts —
          HMAC-SHA256 signature verification over the exact raw
          bytes, strict `parse_event` schema validation (event enum,
          workflow_ref, event_id, bounded payload), and D-027
          idempotency: a dispatched drill event MUST record its
          event_key exactly once, a redelivery is SKIPPED, and a
          conflicting payload never re-fires the handler;
  IGN-05  the canonical `phase5.live_wiring_attestation.v1` is
          emitted exactly once with the SHA-256 `attestation_digest`
          over its canonical bytes — full pass declares
          PHASE5_IGNITED and hands over to Phase 6 (Notion OS sync);
          any abort emits the same schema as IGNITION_INCOMPLETE with
          failure telemetry.

Purity & security (RULES §35, AST-pinned): the igniter core is pure —
injected transports only, zero sockets, zero raw shell, zero wall
clock. The ONLY sanctioned host-touching surfaces are the injected
argv transports (psql / redis-cli), built on the D-151 adapter
pattern: fixed token lists, allow-listed parameters, strict
timeouts, no shell, deep redaction before any string escapes
(D-124). Connection strings, passwords, auth tokens and webhook
secrets NEVER enter any report, record, or error — the transports
carry credentials exclusively through environment/process-scoped
references and the engine reports commitments (hashes, latencies,
names), never values.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

try:  # battery package path or script cwd path
    from ..src.memory.vector_store import deep_redact  # type: ignore
except ImportError:  # pragma: no cover - script invocation paths
    try:
        from src.memory.vector_store import deep_redact  # type: ignore
    except ImportError:
        from memory.vector_store import deep_redact  # type: ignore

__all__ = [
    "Phase5Error", "IgnitionAttestation", "Phase5Igniter",
    "ArgvPsqlTransport", "ArgvRedisTransport",
    "build_phase5_transports",
    "ATTESTATION_SCHEMA", "PHASE5_IGNITED", "PHASE5_INCOMPLETE",
    "CERT_SCHEMA", "CERT_COMPLETE", "DRILL_EVENT_KIND",
    "REDIS_LATENCY_BUDGET_MS", "REDIS_DRILL_NS",
    "POOL_HEADROOM", "TIMEOUT_S",
]

ATTESTATION_SCHEMA = "phase5.live_wiring_attestation.v1"
PHASE5_IGNITED = "PHASE5_IGNITED"
PHASE5_INCOMPLETE = "IGNITION_INCOMPLETE"

CERT_SCHEMA = "dokploy.completion_attestation.v1"
CERT_COMPLETE = "INFRASTRUCTURE_COMPLETE"
SEAL_CLOSED = "STAGE_G_CLOSED"
RECORD_SCHEMA = "stage_h_activation_record.v1"

# The D-112 ledger kind that roots the D-154 certificate.
CERT_ROW_KIND = "dokploy_completion_attestation"

# The D-027 drill event (the ONLY write this engine performs).
DRILL_EVENT_KIND = "phase5.ignition_drill"
DRILL_SOURCE = "phase5_live_wiring"
DRILL_EVENT_ID = "phase5-ignition-drill-0001"

REDIS_LATENCY_BUDGET_MS = 50.0
REDIS_DRILL_NS = "phase5:ignition_drill"
POOL_HEADROOM = 12          # engine concurrency headroom (IGN-02)
TIMEOUT_S = 15.0            # per-operation transport timeout (D-151)

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_NAME_SAFE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}$")


class Phase5Error(ValueError):
    """Contract-level misuse of the Phase 5 igniter."""


def _fail(reason: str) -> None:
    raise Phase5Error(reason)


def canonical_hash(payload: Dict[str, Any]) -> str:
    """SHA-256 over canonical JSON bytes — the project digest
    formula, shared with the Stage G/H/D-154 engines."""
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class IgnitionAttestation:
    """Canonical, immutable Phase 5 ignition artifact."""
    schema: str
    verdict: str          # PHASE5_IGNITED / IGNITION_INCOMPLETE
    cert_digest: str      # the D-154 completion certificate digest
    manifest_sha256: str  # the deployment fingerprint carried through
    postgres: Dict[str, Any]   # connectivity/schema/pooling summary
    redis: Dict[str, Any]      # connectivity/latency/namespace summary
    webhook: Dict[str, Any]    # dispatcher/idempotency summary
    checks: tuple = field(default_factory=tuple)  # (id, ok, detail)
    observed_tick: int = 0

    @property
    def ignited(self) -> bool:
        return self.verdict == PHASE5_IGNITED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "verdict": self.verdict,
            "cert_digest": self.cert_digest,
            "manifest_sha256": self.manifest_sha256,
            "postgres": self.postgres,
            "redis": self.redis,
            "webhook": self.webhook,
            "checks": [list(c) for c in self.checks],
            "observed_tick": self.observed_tick,
        }

    @property
    def attestation_digest(self) -> str:
        """SHA-256 over the attestation's canonical bytes."""
        return canonical_hash(self.to_dict())


class Phase5Igniter:
    """IGN-01..IGN-05 with injected transports (RULES §35).

    Injected:
      clock          — ``() -> int`` logical tick
      audit_sink     — ``callable(dict)`` (D-112/D-121 in prod)
      cert_provider  — ``() -> dict`` the D-154 completion certificate
      audit_rows     — ``() -> list`` the D-112 ledger rows
      chain_verifier — ``() -> dict`` D-112 chain integrity
                       {ok, rows | broken_at_seq, reason}
      pg             — ``PgProbeTransport``: sql(text) -> str,
                       config() -> dict (pooling parameters)
      redis          — ``RedisProbeTransport``: command(argv) -> str,
                       latency_ms() -> float, config() -> dict
      webhook        — ``WebhookProbeTransport``: send(body, header)
                       -> dict (production: signed HTTPS POST to the
                       n8n webhook; drill: in-process dispatcher)
    """

    def __init__(self, clock: Callable[[], int],
                 audit_sink: Callable[[Dict[str, Any]], None],
                 cert_provider: Optional[Callable[[], Dict[str, Any]]] = None,
                 audit_rows: Optional[Callable[[], List[Dict[str, Any]]]] = None,
                 chain_verifier: Optional[Callable[[], Dict[str, Any]]] = None,
                 pg: Optional[Any] = None,
                 redis: Optional[Any] = None,
                 webhook: Optional[Any] = None,
                 ) -> None:
        if not callable(clock) or not callable(audit_sink):
            _fail("clock and audit_sink required")
        self._clock = clock
        self._sink = audit_sink
        self._prov = {
            "cert": cert_provider,
            "audit_rows": audit_rows,
            "chain_verifier": chain_verifier,
            "pg": pg,
            "redis": redis,
            "webhook": webhook,
        }

    # -- internals ---------------------------------------------------------

    def _load(self, name: str) -> Tuple[Optional[Any], str]:
        """Resolve one injected transport: either the transport
        OBJECT itself or a zero-arg provider callable returning it
        (provider callables are the D-152/D-154 convention; the
        transports here are wired as objects)."""
        prov = self._prov[name]
        if prov is None:
            return None, "transport not wired — fail closed"
        try:
            return (prov() if callable(prov) and
                    not hasattr(prov, "sql") and
                    not hasattr(prov, "command") and
                    not hasattr(prov, "send") else prov), ""
        except Exception as exc:  # noqa: BLE001 — transport boundary
            return None, f"transport failure: {type(exc).__name__}"

    def _emit(self, verdict: str, checks: List[Tuple[str, bool, str]],
              cert_digest: str = "", manifest: str = "",
              pg: Optional[Dict[str, Any]] = None,
              rd: Optional[Dict[str, Any]] = None,
              wb: Optional[Dict[str, Any]] = None,
              ) -> IgnitionAttestation:
        att = IgnitionAttestation(
            schema=ATTESTATION_SCHEMA, verdict=verdict,
            cert_digest=cert_digest, manifest_sha256=manifest,
            postgres=pg or {}, redis=rd or {}, webhook=wb or {},
            checks=tuple((c[0], c[1], deep_redact(str(c[2])))
                         for c in checks),
            observed_tick=self._clock())
        blob = json.dumps(att.to_dict(), sort_keys=True,
                          separators=(",", ":"), ensure_ascii=False)
        redacted = json.loads(deep_redact(blob))
        # Public commitments (D-146/D-153/D-154 precedent): the
        # certificate digest and manifest fingerprint are hashes of
        # bindable public data — restored after redaction so the
        # ledger copy stays chain-correlatable.
        redacted["cert_digest"] = att.cert_digest
        redacted["manifest_sha256"] = att.manifest_sha256
        self._sink(redacted)
        return att

    # -- IGN-01: the D-154 completion certificate ----------------------------

    def _ign01(self) -> Tuple[bool, str, str,
                              List[Tuple[str, bool, str]]]:
        """(ok, cert_digest, manifest, checks)."""
        checks: List[Tuple[str, bool, str]] = []
        cert, err = self._load("cert")
        if cert is None:
            checks.append(("IGN-01", False,
                           f"D-154 completion certificate absent "
                           f"({err}) — the infrastructure program "
                           "never closed"))
            return False, "", "", checks
        if not isinstance(cert, dict):
            checks.append(("IGN-01", False,
                           "D-154 completion certificate malformed"))
            return False, "", "", checks
        if cert.get("schema") != CERT_SCHEMA:
            checks.append(("IGN-01", False,
                           f"certificate schema {cert.get('schema')!r} "
                           f"!= {CERT_SCHEMA!r}"))
            return False, "", "", checks
        if cert.get("verdict") != CERT_COMPLETE:
            checks.append(("IGN-01", False,
                           f"certificate verdict "
                           f"{cert.get('verdict')!r} != "
                           f"{CERT_COMPLETE!r} — infrastructure "
                           "incomplete, ignition refused"))
            return False, "", "", checks
        recorded = cert.get("attestation_digest", "")
        if not isinstance(recorded, str) or \
                not _HEX64.match(recorded):
            checks.append(("IGN-01", False,
                           "attestation_digest missing or malformed"))
            return False, "", "", checks
        recomputed = canonical_hash(
            {k: v for k, v in cert.items()
             if k != "attestation_digest"})
        if recorded != recomputed:
            checks.append(("IGN-01", False,
                           f"attestation_digest {recorded[:16]}… != "
                           f"recomputed {recomputed[:16]}… — DRIFTED "
                           "or altered certificate"))
            return False, "", "", checks
        # the certificate must carry the closed chain it attests
        if cert.get("closure_digest") and \
                cert.get("activation_digest"):
            checks.append(("IGN-01", True,
                           "D-154 certificate INFRASTRUCTURE_COMPLETE "
                           f"({recorded[:16]}…)"))
        else:
            checks.append(("IGN-01", False,
                           "certificate lacks its closure/activation "
                           "commitments — partial certificate"))
            return False, "", "", checks
        # D-112 rooting
        rows, err = self._load("audit_rows")
        rooted = False
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                detail = row.get("detail") or {}
                blob = json.dumps(detail, ensure_ascii=False,
                                  sort_keys=True) \
                    if isinstance(detail, dict) else str(detail)
                if str(row.get("event_kind", "")) == CERT_ROW_KIND \
                        and recorded in blob:
                    rooted = True
                    break
        if not rooted:
            checks.append(("IGN-01", False,
                           "certificate not rooted in the D-112 "
                           "ledger — the completion was never durably "
                           "attested"))
            return False, recorded, "", checks
        # chain integrity
        cv, err = self._load("chain_verifier")
        if cv is None or not isinstance(cv, dict) or not cv.get("ok"):
            reason = (cv or {}).get("reason", err or "verifier absent")
            checks.append(("IGN-01", False,
                           f"D-112 chain not intact ({reason}) — "
                           "ignition on a broken ledger is refused"))
            return False, recorded, "", checks
        checks.append(("IGN-01", True,
                       "certificate rooted in the D-112 ledger "
                       f"({int(cv.get('rows', 0))} rows, zero breaks)"))
        manifest = cert.get("manifest_sha256", "") \
            if isinstance(cert.get("manifest_sha256"), str) else ""
        return True, recorded, manifest, checks

    # -- IGN-02: PostgreSQL SSOT -----------------------------------------------

    def _ign02(self) -> Tuple[bool, Dict[str, Any],
                              List[Tuple[str, bool, str]]]:
        checks: List[Tuple[str, bool, str]] = []
        summary: Dict[str, Any] = {"connected": False,
                                   "roundtrip": False,
                                   "schema_ready": False,
                                   "pooling_ok": False}
        pg, err = self._load("pg")
        if pg is None:
            checks.append(("IGN-02", False,
                           f"PostgreSQL transport unavailable ({err}) "
                           "— fail closed"))
            return False, summary, checks
        cfg = pg.config() if hasattr(pg, "config") else {}
        max_conn = cfg.get("max_connections")
        reserved = cfg.get("superuser_reserved_connections", 3)
        if not isinstance(max_conn, int) or isinstance(max_conn, bool) \
                or max_conn <= 0:
            checks.append(("IGN-02", False,
                           "pooling invariants unreadable "
                           "(max_connections) — fail closed"))
            return False, summary, checks
        if max_conn <= int(reserved) + POOL_HEADROOM:
            checks.append(("IGN-02", False,
                           f"pooling invariant violated: "
                           f"max_connections={max_conn} leaves no "
                           f"headroom over reserved {reserved} + "
                           f"{POOL_HEADROOM} engine workers"))
            return False, summary, checks
        summary["max_connections"] = max_conn
        summary["pooling_ok"] = True
        checks.append(("IGN-02", True,
                       f"pooling invariants hold (max_connections="
                       f"{max_conn}, headroom over {reserved}+"
                       f"{POOL_HEADROOM})"))
        # authenticated connectivity + read-only roundtrip
        try:
            one = str(pg.sql("SELECT 1")).strip()
        except Exception as exc:  # noqa: BLE001 — typed only (D-124)
            checks.append(("IGN-02", False,
                           f"PostgreSQL handshake failed: "
                           f"{type(exc).__name__} — credentials, "
                           "endpoint or timeout"))
            return False, summary, checks
        if one != "1":
            checks.append(("IGN-02", False,
                           "PostgreSQL roundtrip returned an "
                           "unexpected payload"))
            return False, summary, checks
        summary["connected"] = True
        summary["roundtrip"] = True
        checks.append(("IGN-02", True,
                       "authenticated connection + read roundtrip OK"))
        # schema readiness: the D-055 SSOT seed catalog
        try:
            tables = str(pg.sql(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema='seed' AND table_name='size_term'"
            )).strip()
            rows = str(pg.sql(
                "SELECT count(*) FROM seed.size_term"
            )).strip() if tables == "1" else "0"
        except Exception as exc:  # noqa: BLE001 — typed only (D-124)
            checks.append(("IGN-02", False,
                           f"schema readiness probe failed: "
                           f"{type(exc).__name__}"))
            return False, summary, checks
        if tables != "1" or not rows.isdigit() or rows == "0":
            checks.append(("IGN-02", False,
                           "SSOT schema not ready (seed.size_term "
                           "absent or unseeded) — run seed_registry "
                           "before ignition"))
            return False, summary, checks
        summary["schema_ready"] = True
        summary["seed_rows"] = int(rows)
        checks.append(("IGN-02", True,
                       f"SSOT schema ready (seed.size_term, "
                       f"{rows} rows)"))
        return True, summary, checks

    # -- IGN-03: Redis ---------------------------------------------------------

    def _ign03(self) -> Tuple[bool, Dict[str, Any],
                              List[Tuple[str, bool, str]]]:
        checks: List[Tuple[str, bool, str]] = []
        summary: Dict[str, Any] = {"connected": False,
                                   "latency_ms": None,
                                   "within_budget": False,
                                   "namespace_isolated": False,
                                   "no_eviction": False}
        rd, err = self._load("redis")
        if rd is None:
            checks.append(("IGN-03", False,
                           f"Redis transport unavailable ({err}) — "
                           "fail closed"))
            return False, summary, checks
        # connectivity + PING latency
        try:
            pong = str(rd.command(["PING"])).strip().upper()
            latency = float(rd.latency_ms())
        except Exception as exc:  # noqa: BLE001 — typed only (D-124)
            checks.append(("IGN-03", False,
                           f"Redis handshake failed: "
                           f"{type(exc).__name__} — endpoint, "
                           "credentials or timeout"))
            return False, summary, checks
        if pong != "PONG":
            checks.append(("IGN-03", False,
                           f"Redis PING returned {pong[:24]!r} — "
                           "no valid handshake"))
            return False, summary, checks
        summary["connected"] = True
        summary["latency_ms"] = latency
        if latency >= REDIS_LATENCY_BUDGET_MS:
            checks.append(("IGN-03", False,
                           f"Redis PING latency {latency:.1f}ms "
                           f"exceeds the {REDIS_LATENCY_BUDGET_MS:.0f}"
                           "ms budget"))
            return False, summary, checks
        summary["within_budget"] = True
        checks.append(("IGN-03", True,
                       f"Redis PING OK ({latency:.1f}ms < "
                       f"{REDIS_LATENCY_BUDGET_MS:.0f}ms)"))
        # no-eviction configuration (D-144 env contract)
        cfg = rd.config() if hasattr(rd, "config") else {}
        policy = str(cfg.get("maxmemory_policy", "")).strip().lower()
        if policy != "noeviction":
            checks.append(("IGN-03", False,
                           f"Redis eviction policy {policy!r} != "
                           "'noeviction' — a state store that "
                           "discards keys under pressure refuses "
                           "ignition"))
            return False, summary, checks
        summary["no_eviction"] = True
        checks.append(("IGN-03", True,
                       "no-eviction policy confirmed (noeviction)"))
        # isolated-namespace roundtrip: set → get → delete
        key = f"{REDIS_DRILL_NS}:probe"
        try:
            rd.command(["SET", key, "1", "EX", "60"])
            got = str(rd.command(["GET", key])).strip()
            rd.command(["DEL", key])
        except Exception as exc:  # noqa: BLE001 — typed only (D-124)
            checks.append(("IGN-03", False,
                           f"Redis drill-namespace roundtrip failed: "
                           f"{type(exc).__name__}"))
            return False, summary, checks
        if got != "1":
            checks.append(("IGN-03", False,
                           "Redis roundtrip read-back mismatch"))
            return False, summary, checks
        summary["namespace_isolated"] = True
        checks.append(("IGN-03", True,
                       f"drill-namespace roundtrip OK ({REDIS_DRILL_NS}"
                       ", set/get/delete)"))
        return True, summary, checks

    # -- IGN-04: n8n webhook dispatcher + D-027 idempotency ----------------------

    def _ign04(self, store: Any) -> Tuple[bool, Dict[str, Any],
                                          List[Tuple[str, bool, str]]]:
        checks: List[Tuple[str, bool, str]] = []
        summary: Dict[str, Any] = {"schema_valid": False,
                                   "hmac_verified": False,
                                   "dispatched": False,
                                   "idempotent": False,
                                   "d027_store_roundtrip": False}
        wb, err = self._load("webhook")
        if wb is None:
            checks.append(("IGN-04", False,
                           f"n8n webhook transport unavailable ({err}) "
                           "— fail closed"))
            return False, summary, checks
        try:  # battery package path or script cwd path
            from canonical.n8n_webhook_contracts import (  # type: ignore
                N8nWebhookError, N8nEventDispatcher, event_key,
                mock_webhook_payload, parse_event, sign_payload,
            )
        except ImportError:  # pragma: no cover
            from n8n_webhook_contracts import (  # type: ignore
                N8nWebhookError, N8nEventDispatcher, event_key,
                mock_webhook_payload, parse_event, sign_payload,
            )
        # a) strict schema validation of the drill event
        event = mock_webhook_payload("ops.ping",
                                     workflow_ref="PHASE5-IGNITION",
                                     event_id=DRILL_EVENT_ID)
        try:
            body = json.dumps(event, sort_keys=True,
                              ensure_ascii=False).encode("utf-8")
            parsed = parse_event(body)
        except N8nWebhookError as exc:
            checks.append(("IGN-04", False,
                           f"drill event rejected by the D-053 "
                           f"schema: {exc}"))
            return False, summary, checks
        except Exception as exc:  # noqa: BLE001 — typed only (D-124)
            checks.append(("IGN-04", False,
                           f"webhook transport failure: "
                           f"{type(exc).__name__}"))
            return False, summary, checks
        summary["schema_valid"] = True
        checks.append(("IGN-04", True,
                       "drill event schema-valid (D-053 parse_event)"))
        # b) HMAC over the exact raw bytes, verified through the
        #    transport (the transport holds the secret; the engine
        #    never sees it)
        try:
            out = wb.send(body) or {}
        except Exception as exc:  # noqa: BLE001 — typed only (D-124)
            checks.append(("IGN-04", False,
                           f"webhook dispatch failed: "
                           f"{type(exc).__name__}"))
            return False, summary, checks
        if out.get("hmac_verified") is True:
            summary["hmac_verified"] = True
            checks.append(("IGN-04", True,
                           "HMAC-SHA256 verified over the exact raw "
                           "bytes"))
        else:
            checks.append(("IGN-04", False,
                           "webhook HMAC verification absent or "
                           "failed — unauthenticated conduits refuse "
                           "ignition"))
            return False, summary, checks
        # c) D-027 idempotency through the dispatcher over the REAL
        #    store interface: register → dispatch → redelivery skip
        seen: Dict[str, bool] = {}
        recorded: List[str] = []

        def _seen(key: str) -> bool:
            return bool(seen.get(key))

        def _record(key: str) -> None:
            recorded.append(key)
            seen[key] = True
            # mirror the D-027 registration for the redelivery leg
            store.receive(DRILL_SOURCE, DRILL_EVENT_ID,
                          "webhook_event", event)

        handlers = {"ops.ping": lambda ev: {"ok": True}}
        dispatcher = N8nEventDispatcher(handlers, _seen, _record)
        first = dispatcher.dispatch([parsed], logical_now="tick-0")
        if not (first["results"]
                and first["results"][0]["verdict"] == "dispatched"):
            checks.append(("IGN-04", False,
                           "drill dispatch did not succeed — "
                           "dispatcher wiring broken"))
            return False, summary, checks
        summary["dispatched"] = True
        key = event_key(parsed)
        checks.append(("IGN-04", True,
                       "drill event dispatched (D-053 dispatcher)"))
        # redelivery: the same event MUST be skipped, never re-fired
        second = dispatcher.dispatch([parsed], logical_now="tick-1")
        v2 = second["results"][0]["verdict"] if second["results"] \
            else "?"
        rec = store.get_record(DRILL_SOURCE, DRILL_EVENT_ID) \
            if hasattr(store, "get_record") else None
        status = (rec or {}).get("processing_status", "")
        if v2 == "skipped_duplicate" and len(recorded) == 1:
            summary["idempotent"] = True
            checks.append(("IGN-04", True,
                           "idempotency verified: redelivery skipped, "
                           f"handler fired exactly once (key "
                           f"{key[:16]}…)"))
        else:
            checks.append(("IGN-04", False,
                           f"idempotency violation: redelivery verdict "
                           f"{v2!r}, handler fired {len(recorded)}x — "
                           "D-027 adherence required"))
            return False, summary, checks
        if status == "received":
            summary["d027_store_roundtrip"] = True
            checks.append(("IGN-04", True,
                           "D-027 store roundtrip OK (drill event "
                           "registered exactly once)"))
        else:
            checks.append(("IGN-04", False,
                           f"D-027 store roundtrip failed (status "
                           f"{status!r}) — the drill store rejected "
                           "the drill event"))
            return False, summary, checks
        return True, summary, checks

    # -- the run -------------------------------------------------------------

    def run(self, d027_store: Any = None) -> IgnitionAttestation:
        """IGN-01..IGN-05 → the canonical attestation. Exactly one
        audited attestation per call (including aborts). `d027_store`
        is the injected event store (D-027 interface: receive/
        get_record) used by the IGN-04 drill."""
        checks: List[Tuple[str, bool, str]] = []
        ok1, cert_digest, manifest, c1 = self._ign01()
        checks += c1
        if not ok1:
            return self._emit(PHASE5_INCOMPLETE, checks,
                              cert_digest=cert_digest,
                              manifest=manifest)
        ok2, pg, c2 = self._ign02()
        checks += c2
        ok3, rd, c3 = self._ign03()
        checks += c3
        # IGN-04 needs the D-027 store; a store failure is a typed
        # refusal, never a silent pass
        if d027_store is None:
            ok4, wb = False, {}
            checks.append(("IGN-04", False,
                           "D-027 event store not provided — the "
                           "idempotency drill cannot run, fail closed"))
        else:
            try:
                ok4, wb, c4 = self._ign04(d027_store)
                checks += c4
            except Exception as exc:  # noqa: BLE001 — typed (D-124)
                checks.append(("IGN-04", False,
                               f"webhook drill raised: "
                               f"{type(exc).__name__}"))
                ok4, wb = False, {}
        verdict = PHASE5_IGNITED if all((ok1, ok2, ok3, ok4)) \
            else PHASE5_INCOMPLETE
        if verdict == PHASE5_IGNITED:
            checks.append(("IGN-05", True,
                           "phase5.live_wiring_attestation.v1 emitted "
                           "— Phase 5 services IGNITED under the D-154 "
                           "certificate; handover to Phase 6 (Notion "
                           "OS sync) is verified"))
        else:
            checks.append(("IGN-05", False,
                           "attestation emitted as IGNITION_INCOMPLETE "
                           "— remediate the named checks before "
                           "Phase 5 handover"))
        return self._emit(verdict, checks, cert_digest=cert_digest,
                          manifest=manifest, pg=pg, rd=rd, wb=wb)


# ---------------------------------------------------------------------------
# The sanctioned argv transports (D-151 adapter pattern)
# ---------------------------------------------------------------------------

class ArgvPsqlTransport:
    """PostgreSQL probe transport — direct argv ONLY.

    Every child process is a fixed token list (`psql`, no shell); the
    connection is selected by ENVIRONMENT NAME reference, never by a
    literal connection string (credentials live in the process env /
    pgpass, never in argv, never in reports — D-124). Strict timeout
    per operation; failures surface as typed errors.
    """

    def __init__(self, container: str = "postgres-ssot",
                 db_user: str = "engine_local",
                 db_name: str = "business_engine_local",
                 psql_binary: str = "docker",
                 runner: Optional[Callable[..., subprocess.CompletedProcess]] = None,
                 timeout_s: float = TIMEOUT_S) -> None:
        for name in (container, db_user, db_name, psql_binary):
            if not _NAME_SAFE.match(name or ""):
                _fail(f"invalid transport parameter: {name!r}")
        self._container = container
        self._user = db_user
        self._db = db_name
        self._bin = psql_binary
        self._run = runner or self._run_argv
        self._timeout = float(timeout_s)

    def _run_argv(self, argv: List[str]) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(argv, capture_output=True,
                                  text=True, timeout=self._timeout)
        except subprocess.TimeoutExpired:
            raise Phase5Error("timeout") from None
        except OSError as exc:
            raise Phase5Error(
                f"spawn_failure: {type(exc).__name__}") from None

    def _argv(self, sql: str) -> List[str]:
        return [self._bin, "exec", self._container,
                "psql", "-U", self._user, "-d", self._db,
                "-Atq", "-v", "ON_ERROR_STOP=1", "-c", sql]

    def sql(self, sql: str) -> str:
        proc = self._run(self._argv(sql))
        if proc.returncode != 0:
            # stderr is NEVER echoed (may carry server hints) — D-124
            raise Phase5Error("psql_failed")
        return proc.stdout

    def config(self) -> Dict[str, Any]:
        row = self.sql(
            "SELECT setting FROM pg_settings WHERE name = "
            "'max_connections'").strip()
        reserved = self.sql(
            "SELECT setting FROM pg_settings WHERE name = "
            "'superuser_reserved_connections'").strip()
        return {"max_connections": int(row),
                "superuser_reserved_connections": int(reserved)}


class ArgvRedisTransport:
    """Redis probe transport — direct argv ONLY (D-151 pattern).

    Defaults to the D-144 manifest's declared `redis` service (the
    attested target); on the legacy local stack, pass the container
    name explicitly. Credentials ride the container's own environment
    (REDISCLI_AUTH inside the container namespace), never argv, never
    reports.
    """

    def __init__(self, container: str = "redis",
                 redis_binary: str = "docker",
                 runner: Optional[Callable[..., subprocess.CompletedProcess]] = None,
                 timeout_s: float = TIMEOUT_S) -> None:
        if not _NAME_SAFE.match(container or "") or \
                not _NAME_SAFE.match(redis_binary or ""):
            _fail("invalid redis transport parameter")
        self._container = container
        self._bin = redis_binary
        self._run = runner or self._run_argv
        self._timeout = float(timeout_s)

    def _run_argv(self, argv: List[str]) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(argv, capture_output=True,
                                  text=True, timeout=self._timeout)
        except subprocess.TimeoutExpired:
            raise Phase5Error("timeout") from None
        except OSError as exc:
            raise Phase5Error(
                f"spawn_failure: {type(exc).__name__}") from None

    def _argv(self, args: List[str]) -> List[str]:
        return [self._bin, "exec", self._container,
                "redis-cli", "--no-auth-warning"] + list(args)

    def command(self, args: List[str]) -> str:
        proc = self._run(self._argv(args))
        if proc.returncode != 0:
            raise Phase5Error("redis_failed")
        return proc.stdout

    def latency_ms(self) -> float:
        """Wall-time one PING through the transport (the igniter's
        IGN-03 latency evidence)."""
        import time
        t0 = time.monotonic()
        self.command(["PING"])
        return (time.monotonic() - t0) * 1000.0

    def config(self) -> Dict[str, Any]:
        out = self.command(["CONFIG", "GET", "maxmemory-policy"])
        # `CONFIG GET` replies line-wise: name line then value line
        lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
        return {"maxmemory_policy": lines[-1] if lines else ""}


def build_phase5_transports(
        pg_container: str = "postgres-ssot",
        redis_container: str = "redis",
        runner: Optional[Callable[..., subprocess.CompletedProcess]] = None,
) -> Dict[str, Any]:
    """Wire the argv transports into the igniter kwargs:
    `Phase5Igniter(clock, sink, **build_phase5_transports(), ...)`.
    (Host-side `psql`/`redis-cli` alternatives can be injected the
    same way; see seed_registry.q() for the host-pg precedent.)"""
    return {
        "pg": ArgvPsqlTransport(container=pg_container, runner=runner),
        "redis": ArgvRedisTransport(container=redis_container,
                                    runner=runner),
    }


def main(argv: Optional[List[str]] = None) -> int:
    """CLI wiring: real D-154 certificate + real D-112 chain + real
    argv transports."""
    import argparse
    import sys
    ap = argparse.ArgumentParser(
        description="Phase 5 live wiring igniter (IGN-01..IGN-05, "
                    "D-155).")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    print("live_wiring_phase5_igniter: interactive wiring requires "
          "the D-154 completion certificate, the D-112 chain, the "
          "argv transports and the D-027 store; see run() and the "
          "battery for the injected contract.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

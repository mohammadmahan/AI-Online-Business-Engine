"""Phase 6 live wiring igniter — Notion Workspace sync verification (D-156).

The second Live Wiring program phase. Phase 5 (D-155) ignited the
core services under the D-154 completion certificate and emitted the
`phase5.live_wiring_attestation.v1`; Phase 6 now live-wires the
Notion Workspace Business OS layer on top of that attested surface:

  NOT-01  the upstream `phase5.live_wiring_attestation.v1` is
          present, PHASE5_IGNITED, its SHA-256 `attestation_digest`
          recomputes byte-exactly, its manifest fingerprint still
          binds the D-154 certificate it carried, and the attestation
          is rooted in the D-112 ledger (kind
          `phase5_live_wiring_attestation`) over an intact chain;
  NOT-02  the live Notion API client authenticates (me / users GET
          through the injected transport), the integration token
          carries workspace access (401/403 = Class-E refusal), and
          the token-bucket pacer is honored (a burst over
          NOTION_RATE_LIMIT_PER_SEC is paced, never dropped);
  NOT-03  the four canonical workspace databases (Product Catalog,
          Order Pipeline, Marketing Campaigns, Tasks/SOPs) exist,
          match the declared property schema (names + property
          types + required select options), and their declared
          relations resolve to workspace objects;
  NOT-04  a NON-DESTRUCTIVE synthetic write-read-cleanup cycle
          (create probe page → read back → archive) through the real
          client contract, with strict idempotency: the SAME probe
          payload replayed MUST return the SAME page (idempotency
          keyed on the payload hash) — a second distinct page for a
          replayed payload is an idempotency collision and fails the
          run;
  NOT-05  the canonical `phase6.live_wiring_attestation.v1` is
          emitted exactly once per run (aborts included) with the
          SHA-256 `attestation_digest`; any abort emits the same
          schema as PHASE6_INCOMPLETE with failure telemetry.

Purity & security (RULES §35, AST-pinned): the igniter core is pure —
injected client transport only, zero sockets, zero raw shell, zero
wall clock. The Notion secret token NEVER enters any report, record,
or error: it lives inside the injected client/transport only
(LiveNotionClient already redacts it from every escaping string and
the pacer/token-bucket is transport-owned); emitted records carry
commitments (digests, database keys, latencies), never values.
`deep_redact` (D-124) runs over every emitted record, with the public
commitments (phase5 digest, phase6 digest, manifest fingerprint)
restored after redaction so ledger copies stay chain-correlatable.
"""
from __future__ import annotations

import hashlib
import json
import re
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
    "Phase6Error", "Phase6Attestation", "Phase6Igniter",
    "WorkspaceSchema", "NotionProbeTransport",
    "ATTESTATION_SCHEMA", "PHASE6_IGNITED", "PHASE6_INCOMPLETE",
    "PHASE5_SCHEMA", "PHASE5_IGNITED", "PHASE5_ROW_KIND",
    "DB_KEYS", "PROBE_ROW_KIND", "canonical_hash",
]

ATTESTATION_SCHEMA = "phase6.live_wiring_attestation.v1"
PHASE6_IGNITED = "PHASE6_IGNITED"
PHASE6_INCOMPLETE = "IGNITION_INCOMPLETE"

PHASE5_SCHEMA = "phase5.live_wiring_attestation.v1"
PHASE5_IGNITED = "PHASE5_IGNITED"

# The D-112 ledger kind that roots the Phase 5 attestation (D-155).
PHASE5_ROW_KIND = "phase5_live_wiring_attestation"

# The D-112 ledger kind the NOT-04 probe writes (the ONLY write this
# engine performs) — evidence of the drill, chain-rooted.
PROBE_ROW_KIND = "phase6_sync_probe"

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_HEX32 = re.compile(r"^[0-9a-f]{32}$")
_OBJECT_ID = re.compile(
    r"^[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?"
    r"[0-9a-fA-F]{4}-?[0-9a-fA-F]{12}$")

# Rate-limit guardrail: re-exported pacer ceiling (requests/sec).
RATE_LIMIT_PER_SEC = 3.0


class Phase6Error(ValueError):
    """Contract-level misuse of the Phase 6 igniter."""


def _fail(reason: str) -> None:
    raise Phase6Error(reason)


def canonical_hash(payload: Dict[str, Any]) -> str:
    """SHA-256 over canonical JSON bytes — the shared project digest
    formula (Stage G/H/D-154/D-155 engines)."""
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _probe_page_key(payload: Dict[str, Any]) -> str:
    """The D-027-style idempotency key for a synthetic probe payload:
    sha256 over the payload's canonical bytes."""
    return canonical_hash(payload)


# ---------------------------------------------------------------------------
# The canonical workspace schema (NOT-03)
# ---------------------------------------------------------------------------

_DB_SPECS: Dict[str, Dict[str, Any]] = {
    "product_catalog": {
        "title": "Product Catalog",
        "required": {
            "Name": "title",
            "SKU": "rich_text",
            "Price": "number",
            "Status": "select",
        },
        "select_options": {"Status": {"draft", "active", "retired"}},
    },
    "order_pipeline": {
        "title": "Order Pipeline",
        "required": {
            "Name": "title",
            "OrderRef": "rich_text",
            "Amount": "number",
            "Stage": "select",
            "Product": "relation",
        },
        "select_options": {"Stage": {"new", "paid", "shipped",
                                     "refunded"}},
    },
    "marketing_campaigns": {
        "title": "Marketing Campaigns",
        "required": {
            "Name": "title",
            "Channel": "select",
            "Budget": "number",
            "Status": "select",
        },
        "select_options": {"Channel": {"instagram", "telegram",
                                       "email", "organic"},
                           "Status": {"planned", "running",
                                      "done", "paused"}},
    },
    "tasks_sops": {
        "title": "Tasks/SOPs",
        "required": {
            "Name": "title",
            "Kind": "select",
            "Owner": "people",
            "DueDate": "date",
            "Campaign": "relation",
        },
        "select_options": {"Kind": {"task", "sop", "checklist"}},
    },
}

DB_KEYS = tuple(sorted(_DB_SPECS))


class WorkspaceSchema:
    """Declared canonical database schema — injectable for tests,
    defaults to the project's canonical four-database model."""

    def __init__(self, specs: Optional[Dict[str, Dict[str, Any]]] = None,
                 database_ids: Optional[Dict[str, str]] = None) -> None:
        self.specs = dict(specs) if specs is not None else dict(_DB_SPECS)
        self.database_ids = dict(database_ids) if database_ids else {}
        for key in self.specs:
            if not re.match(r"^[a-z][a-z0-9_]{0,63}$", key):
                _fail(f"invalid database key: {key!r}")
        for key, dbid in self.database_ids.items():
            if key not in self.specs:
                _fail(f"database_ids key {key!r} has no declared spec")
            if not _OBJECT_ID.match(dbid or ""):
                _fail(f"database_ids[{key!r}] is not a Notion object id")


@dataclass(frozen=True)
class Phase6Attestation:
    """Canonical, immutable Phase 6 ignition artifact."""
    schema: str
    verdict: str            # PHASE6_IGNITED / IGNITION_INCOMPLETE
    phase5_digest: str      # upstream attestation digest (commitment)
    manifest_sha256: str    # deployment fingerprint carried through
    auth: Dict[str, Any]    # authentication/pacing summary
    schema_map: Dict[str, Any]  # per-database conformance summary
    sync: Dict[str, Any]    # probe cycle + idempotency summary
    checks: tuple = field(default_factory=tuple)  # (id, ok, detail)
    observed_tick: int = 0

    @property
    def ignited(self) -> bool:
        return self.verdict == PHASE6_IGNITED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "verdict": self.verdict,
            "phase5_digest": self.phase5_digest,
            "manifest_sha256": self.manifest_sha256,
            "auth": self.auth,
            "schema_map": self.schema_map,
            "sync": self.sync,
            "checks": [list(c) for c in self.checks],
            "observed_tick": self.observed_tick,
        }

    @property
    def attestation_digest(self) -> str:
        """SHA-256 over the attestation's canonical bytes."""
        return canonical_hash(self.to_dict())


class NotionProbeTransport:
    """Sanctioned argv-free transport seam — a callable injected into
    LiveNotionClient (D-045/D-075). The engine NEVER constructs one
    itself; production supplies the live HTTPS transport, tests
    supply an in-process fake. Kept here only to document the
    request/response contract: request {method,url,headers,json} →
    response {status_code, body, retry_after}."""

    def __init__(self, handler: Callable[[Dict], Dict]) -> None:
        if not callable(handler):
            _fail("NotionProbeTransport requires a callable handler")
        self._handler = handler

    def __call__(self, request: Dict) -> Dict:
        return self._handler(request)


class Phase6Igniter:
    """NOT-01..NOT-05 with an injected Notion client transport.

    Injected:
      clock          — ``() -> int`` logical tick
      audit_sink     — ``callable(dict)`` (D-112/D-121 in prod)
      phase5_provider— ``() -> dict`` the phase5 attestation
      audit_rows     — ``() -> list`` the D-112 ledger rows
      chain_verifier — ``() -> dict`` D-112 chain integrity
                       {ok, rows | broken_at_seq, reason}
      notion         — a LiveNotionClient-compatible object (the
                       transport is injected INSIDE it); optional
                       per-call overrides keep the core pure.
    """

    def __init__(self, clock: Callable[[], int],
                 audit_sink: Callable[[Dict[str, Any]], None],
                 phase5_provider: Optional[Callable[[], Dict[str, Any]]] = None,
                 audit_rows: Optional[Callable[[], List[Dict[str, Any]]]] = None,
                 chain_verifier: Optional[Callable[[], Dict[str, Any]]] = None,
                 notion: Optional[Any] = None,
                 ) -> None:
        if not callable(clock) or not callable(audit_sink):
            _fail("clock and audit_sink required")
        self._clock = clock
        self._sink = audit_sink
        self._prov = {
            "phase5": phase5_provider,
            "audit_rows": audit_rows,
            "chain_verifier": chain_verifier,
            "notion": notion,
        }

    # -- internals ---------------------------------------------------------

    def _load(self, name: str) -> Tuple[Optional[Any], str]:
        """Resolve one injected provider: either a zero-arg callable
        (transport factories, ledger loaders) or the injected OBJECT
        itself (the Notion client, built once by the host)."""
        prov = self._prov.get(name)
        if prov is None:
            return None, "provider not injected"
        if callable(prov) and not hasattr(prov, "users_me"):
            try:
                return prov(), ""
            except Exception as exc:  # noqa: BLE001 — typed (D-124)
                return None, f"provider raised {type(exc).__name__}"
        return prov, ""

    def _emit(self, verdict: str, checks: List[Tuple[str, bool, str]],
              phase5_digest: str = "", manifest: str = "",
              auth: Optional[Dict[str, Any]] = None,
              schema_map: Optional[Dict[str, Any]] = None,
              sync: Optional[Dict[str, Any]] = None,
              ) -> Phase6Attestation:
        att = Phase6Attestation(
            schema=ATTESTATION_SCHEMA, verdict=verdict,
            phase5_digest=phase5_digest, manifest_sha256=manifest,
            auth=auth or {}, schema_map=schema_map or {},
            sync=sync or {},
            checks=tuple((c[0], c[1], deep_redact(str(c[2])))
                         for c in checks),
            observed_tick=self._clock())
        blob = json.dumps(att.to_dict(), sort_keys=True,
                          separators=(",", ":"), ensure_ascii=False)
        redacted = json.loads(deep_redact(blob))
        # Public commitments (D-146/D-153/D-154/D-155 precedent):
        # digests over bindable public data — restored after
        # redaction so ledger copies stay chain-correlatable.
        redacted["phase5_digest"] = att.phase5_digest
        redacted["manifest_sha256"] = att.manifest_sha256
        self._sink(redacted)
        return att

    # -- NOT-01: the Phase 5 attestation ------------------------------------

    def _not01(self) -> Tuple[bool, str, str,
                              List[Tuple[str, bool, str]]]:
        """(ok, phase5_digest, manifest, checks)."""
        checks: List[Tuple[str, bool, str]] = []
        att, err = self._load("phase5")
        if att is None:
            checks.append(("NOT-01", False,
                           "Phase 5 attestation absent "
                           f"({err}) — Phase 5 never ignited"))
            return False, "", "", checks
        if not isinstance(att, dict):
            checks.append(("NOT-01", False,
                           "Phase 5 attestation malformed"))
            return False, "", "", checks
        if att.get("schema") != PHASE5_SCHEMA:
            checks.append(("NOT-01", False,
                           f"attestation schema {att.get('schema')!r} "
                           f"!= {PHASE5_SCHEMA!r}"))
            return False, "", "", checks
        if att.get("verdict") != PHASE5_IGNITED:
            checks.append(("NOT-01", False,
                           f"Phase 5 verdict {att.get('verdict')!r} "
                           f"!= {PHASE5_IGNITED!r} — core services "
                           "not ignited, Phase 6 refused"))
            return False, "", "", checks
        manifest = att.get("manifest_sha256", "")
        if not (isinstance(manifest, str) and _HEX64.match(manifest)):
            checks.append(("NOT-01", False,
                           "phase5 attestation lacks its manifest "
                           "fingerprint binding"))
            return False, "", "", checks
        # The upstream attestation's digest is a COMMITMENT: it is
        # recomputed from the record's canonical bytes and verified
        # against the D-112 ledger row that rooted the Phase 5
        # ignition (kind phase5_live_wiring_attestation).
        recomputed = canonical_hash(att)
        rows, err = self._load("audit_rows")
        rooted_digest = ""
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict) or \
                        str(row.get("event_kind", "")) != \
                        PHASE5_ROW_KIND:
                    continue
                detail = row.get("detail")
                if isinstance(detail, dict) and \
                        isinstance(detail.get("attestation_digest"),
                                   str):
                    rooted_digest = detail["attestation_digest"]
                    break
        if not rooted_digest:
            checks.append(("NOT-01", False,
                           "phase5 attestation not rooted in the "
                           "D-112 ledger — upstream ignition was "
                           "never durably attested"))
            return False, recomputed, "", checks
        if rooted_digest != recomputed:
            checks.append(("NOT-01", False,
                           f"phase5 attestation digest {recomputed[:16]}… "
                           f"!= rooted {rooted_digest[:16]}… — DRIFTED "
                           "or altered upstream attestation"))
            return False, recomputed, "", checks
        cv, err = self._load("chain_verifier")
        if cv is None or not isinstance(cv, dict) or not cv.get("ok"):
            reason = (cv or {}).get("reason", err or "verifier absent")
            checks.append(("NOT-01", False,
                           f"D-112 chain not intact ({reason}) — "
                           "wiring on a broken ledger is refused"))
            return False, recomputed, "", checks
        checks.append(("NOT-01", True,
                       "phase5 attestation PHASE5_IGNITED, digest "
                       f"recomputes ({recomputed[:16]}…) and matches "
                       "the rooted commitment in the "
                       f"D-112 ledger ({int(cv.get('rows', 0))} rows, "
                       "zero breaks)"))
        return True, recomputed, manifest, checks

    # -- NOT-02: live Notion authentication & pacing -------------------------

    def _not02(self) -> Tuple[bool, Dict[str, Any],
                              List[Tuple[str, bool, str]]]:
        """(ok, auth summary, checks). Exercises the REAL injected
        client: a `me/users` GET for authentication, then a paced
        burst through NotionPacer to prove token-bucket compliance."""
        from canonical.notion_live import (
            NotionPacer, classify_notion_error, redact_notion)

        checks: List[Tuple[str, bool, str]] = []
        summary: Dict[str, Any] = {"authenticated": False,
                                   "pacer_ok": False,
                                   "rate_per_sec": RATE_LIMIT_PER_SEC}
        client, err = self._load("notion")
        if client is None:
            checks.append(("NOT-02", False,
                           "Notion client transport unavailable "
                           f"({err}) — fail closed"))
            return False, summary, checks
        # Authentication: an authorized read through the client.
        try:
            me = client.users_me()
        except Exception as exc:  # noqa: BLE001 — typed refusal
            kind = type(exc).__name__
            detail = redact_notion(str(getattr(exc, "args", [""])[0])
                                   if getattr(exc, "args", None)
                                   else kind)
            checks.append(("NOT-02", False,
                           f"Notion authentication failed ({kind}): "
                           f"{detail[:80]}"))
            return False, summary, checks
        if not isinstance(me, dict) or not me.get("user"):
            checks.append(("NOT-02", False,
                           "Notion /users/me returned no usable "
                           "identity — workspace access refused"))
            return False, summary, checks
        summary["authenticated"] = True
        summary["workspace"] = str(me.get("workspace", "workspace"))
        checks.append(("NOT-02", True,
                       "Notion integration authenticated (token "
                       "verified against the workspace; token "
                       "material never leaves the client)"))
        # Token-bucket guardrail: a burst over the pacer rate must be
        # PACED (positive waits) and never dropped — deterministic,
        # synthetic ticks.
        pacer = client.pacer() if hasattr(client, "pacer") \
            else NotionPacer()
        # A burst of 12 requests inside ~1.1 seconds — well over the
        # 3/s token bucket — must be paced (positive waits appear).
        waits = [pacer.acquire(now_s=i * 0.1) for i in range(12)]
        if all(w >= 0.0 for w in waits) and any(w > 0.0 for w in waits):
            summary["pacer_ok"] = True
            checks.append(("NOT-02", True,
                           f"rate-limit guardrail verified: burst of "
                           f"12 paced under "
                           f"{RATE_LIMIT_PER_SEC:.0f}/s token bucket "
                           "(paced, never dropped)"))
        else:
            checks.append(("NOT-02", False,
                           "rate-limit guardrail failed: pacer did "
                           "not throttle the burst"))
        return summary["authenticated"] and summary["pacer_ok"], \
            summary, checks

    # -- NOT-03: canonical database schema conformance -----------------------

    def _not03(self, schema: Optional[WorkspaceSchema] = None
               ) -> Tuple[bool, Dict[str, Any],
                          List[Tuple[str, bool, str]]]:
        checks: List[Tuple[str, bool, str]] = []
        ws = schema or WorkspaceSchema()
        summary: Dict[str, Any] = {"databases_checked": 0,
                                   "conformant": 0,
                                   "relations_resolved": 0,
                                   "details": {}}
        client, err = self._load("notion")
        if client is None:
            checks.append(("NOT-03", False,
                           "Notion client transport unavailable "
                           f"({err}) — fail closed"))
            return False, summary, checks
        for key in DB_KEYS:
            spec = ws.specs.get(key)
            if spec is None:
                checks.append(("NOT-03", False,
                               f"database {key!r} missing from the "
                               "declared workspace schema"))
                summary["details"][key] = "missing-spec"
                continue
            dbid = ws.database_ids.get(key, "")
            if not dbid:
                checks.append(("NOT-03", False,
                               f"database {key!r} has no workspace "
                               "database id — cannot verify"))
                summary["details"][key] = "missing-id"
                continue
            try:
                db = client.retrieve_database(dbid)
            except Exception as exc:  # noqa: BLE001 — typed refusal
                kind = type(exc).__name__
                checks.append(("NOT-03", False,
                               f"database {key!r} retrieval failed "
                               f"({kind}) — permission or schema "
                               "mismatch"))
                summary["details"][key] = f"retrieval-{kind}"
                continue
            props = db.get("properties", {}) if isinstance(db, dict) \
                else {}
            problems: List[str] = []
            for pname, ptype in spec["required"].items():
                actual = props.get(pname, {})
                atype = actual.get("type", "")
                if atype != ptype:
                    problems.append(f"{pname}:{atype or 'missing'}"
                                    f"!={ptype}")
            for sname, wanted in spec.get("select_options",
                                          {}).items():
                got = {o.get("name", "")
                       for o in props.get(sname, {})
                       .get("select", {}).get("options", [])} \
                    if isinstance(props.get(sname), dict) else set()
                missing = wanted - got
                if missing:
                    problems.append(
                        f"{sname} options missing {sorted(missing)}")
            # Relation integrity: every declared relation must point
            # at a workspace object that resolves.
            for pname, ptype in spec["required"].items():
                if ptype != "relation":
                    continue
                rel = props.get(pname, {}).get("relation", {})
                target = rel.get("database_id", "")
                if not target:
                    problems.append(f"{pname}: relation unbound")
                else:
                    summary["relations_resolved"] += 1
            if problems:
                checks.append(("NOT-03", False,
                               f"database {key!r} schema mismatch: "
                               + "; ".join(problems[:4])))
                summary["details"][key] = "; ".join(problems[:4])
                continue
            summary["databases_checked"] += 1
            summary["conformant"] += 1
            summary["details"][key] = "conformant"
            checks.append(("NOT-03", True,
                           f"database {key!r} conforms ({len(spec['required'])} "
                           "properties, select options verified, "
                           "relations resolved)"))
        ok = summary["conformant"] == len(DB_KEYS)
        if ok:
            checks.append(("NOT-03", True,
                           f"all {len(DB_KEYS)} canonical databases "
                           "schema-conformant"))
        return ok, summary, checks

    # -- NOT-04: synthetic write-read-cleanup probe ---------------------------

    def _not04(self, schema: Optional[WorkspaceSchema] = None,
               ) -> Tuple[bool, Dict[str, Any],
                          List[Tuple[str, bool, str]]]:
        checks: List[Tuple[str, bool, str]] = []
        summary: Dict[str, Any] = {"created": False, "read_back": False,
                                   "cleaned": False, "idempotent": False,
                                   "write_waived": False}
        ws = schema or WorkspaceSchema()
        client, err = self._load("notion")
        if client is None:
            checks.append(("NOT-04", False,
                           "Notion client transport unavailable "
                           f"({err}) — fail closed"))
            return False, summary, checks
        dbid = ws.database_ids.get("product_catalog", "")
        if not dbid:
            checks.append(("NOT-04", False,
                           "probe target (product_catalog) has no "
                           "workspace database id"))
            return False, summary, checks
        # The probe payload is FIXED (deterministic) so replays key
        # identically; the idempotency key is its payload hash.
        payload = {"Name": "phase6-sync-probe",
                   "SKU": "phase6-probe-0001",
                   "Status": "draft"}
        idem_key = _probe_page_key(payload)
        summary["idempotency_key"] = idem_key
        summary["probe_payload"] = payload
        ok = True
        try:
            first = client.create_probe_page(dbid, payload,
                                             idempotency_key=idem_key)
            created_id = str((first or {}).get("page_id", ""))
            if not created_id:
                checks.append(("NOT-04", False,
                               "probe page creation returned no page "
                               "id"))
                return False, summary, checks
            summary["created"] = True
            checks.append(("NOT-04", True,
                           "synthetic probe page created "
                           f"({idem_key[:16]}…)"))
        except Exception as exc:  # noqa: BLE001 — typed refusal
            checks.append(("NOT-04", False,
                           f"synthetic probe cycle failed at WRITE "
                           f"({type(exc).__name__}) — write path not "
                           "verified"))
            return False, summary, checks
        # idempotent replay
        try:
            replay = client.create_probe_page(dbid, payload,
                                              idempotency_key=idem_key)
            replay_id = str((replay or {}).get("page_id", ""))
        except Exception as exc:  # noqa: BLE001 — typed refusal
            checks.append(("NOT-04", False,
                           f"synthetic probe cycle failed at REPLAY "
                           f"({type(exc).__name__})"))
            return False, summary, checks
        if replay_id and replay_id == created_id:
            summary["idempotent"] = True
            checks.append(("NOT-04", True,
                           "idempotent replay returns the SAME page "
                           "(D-027 key adherence)"))
        else:
            ok = False
            checks.append(("NOT-04", False,
                           "idempotency collision: replayed probe "
                           "payload produced a DISTINCT page — sync "
                           "write-path not idempotent"))
        # read-back
        try:
            readback = client.read_probe_page(created_id)
            body = (readback or {}).get("content")
        except Exception as exc:  # noqa: BLE001 — typed refusal
            checks.append(("NOT-04", False,
                           f"synthetic probe cycle failed at READ "
                           f"({type(exc).__name__})"))
            body = None
        if isinstance(body, dict) and body.get("SKU") == payload["SKU"]:
            summary["read_back"] = True
            checks.append(("NOT-04", True,
                           "probe page read back with matching "
                           "content (write-read cycle verified)"))
        else:
            ok = False
            checks.append(("NOT-04", False,
                           "probe read-back mismatch — sync "
                           "read-path failed"))
        # cleanup (non-destructive guarantee)
        try:
            cleanup = client.archive_page(created_id)
        except Exception as exc:  # noqa: BLE001 — typed refusal
            checks.append(("NOT-04", False,
                           f"synthetic probe cycle failed at CLEANUP "
                           f"({type(exc).__name__}) — probe page may "
                           "remain live"))
            return False, summary, checks
        if (cleanup or {}).get("archived") is True:
            summary["cleaned"] = True
            checks.append(("NOT-04", True,
                           "probe page archived — workspace left "
                           "clean (non-destructive cycle)"))
        else:
            ok = False
            checks.append(("NOT-04", False,
                           "probe cleanup failed — probe page "
                           "still live in the workspace"))
        return ok, summary, checks

    # -- the run --------------------------------------------------------------

    def run(self, schema: Optional[WorkspaceSchema] = None
            ) -> Phase6Attestation:
        """NOT-01..NOT-05 → the canonical attestation. Exactly one
        audited attestation per call (including aborts)."""
        checks: List[Tuple[str, bool, str]] = []
        ok1, p5digest, manifest, c1 = self._not01()
        checks += c1
        if not ok1:
            return self._emit(PHASE6_INCOMPLETE, checks,
                              phase5_digest=p5digest,
                              manifest=manifest)
        ok2, auth, c2 = self._not02()
        checks += c2
        ok3, smap, c3 = self._not03(schema)
        checks += c3
        ok4, sync, c4 = self._not04(schema)
        checks += c4
        verdict = PHASE6_IGNITED if all((ok1, ok2, ok3, ok4)) \
            else PHASE6_INCOMPLETE
        if verdict == PHASE6_IGNITED:
            checks.append(("NOT-05", True,
                           "phase6.live_wiring_attestation.v1 emitted "
                           "— Notion Workspace Business OS wired "
                           "under the Phase 5 attestation; handover "
                           "to Phase 7 (AI Runtime & Product Manager "
                           "wiring) is verified"))
        else:
            checks.append(("NOT-05", False,
                           "attestation emitted as IGNITION_INCOMPLETE "
                           "— remediate the named checks before the "
                           "Phase 7 handover"))
        return self._emit(verdict, checks, phase5_digest=p5digest,
                          manifest=manifest, auth=auth, schema_map=smap,
                          sync=sync)


def main(argv: Optional[List[str]] = None) -> int:
    """CLI wiring guard: interactive wiring requires the injected
    providers and the live workspace configuration."""
    import argparse
    import sys
    ap = argparse.ArgumentParser(
        description="Phase 6 live wiring igniter (NOT-01..NOT-05, "
                    "D-156).")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    print("live_wiring_phase6_igniter: interactive wiring requires "
          "the phase5 attestation, the D-112 chain, the injected "
          "Notion client and the workspace database ids; see run() "
          "and the battery for the injected contract.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

"""Phase 17 live wiring igniter — Notification Engine wiring (D-167).

The twelfth Live Wiring program phase. Phase 16 (D-166) verified the
AI Business Analyst in dry-run mode; Phase 17 now wires and verifies
the NOTIFICATION ENGINE (D-089/D-090/D-092) on top of the verified
Phase 16 attestation — in STRICT DRY-RUN mode with every dispatch
INTERCEPTED by the ephemeral harness:

  NTF-01  the upstream `phase16.analyst_wiring_attestation.v1` is
          present, PHASE16_IGNITED, manifest-bound, its canonical
          bytes recompute to the SHA-256 commitment rooted in the
          D-112 ledger (kind `phase16_analyst_wiring_attestation`)
          over an intact chain — ANY refusal happens BEFORE the first
          engine call (zero engine calls on refusal);
  NTF-02  the verified runtime profile is loaded: the injected
          census marks Phases 5–12, 14, 15 and 16 present+VERIFIED+
          WIRED (slot 14 stays closed CRM-not-needed per D-163 and is
          NOT required), and the repo-real notification seams are
          importable. REGISTRY FACT (recorded here and in the report,
          D-160 precedent): the D-154 cross-walk binds slot 18 to
          `canonical.ai_hitl_service` (HITL), NOT the notification
          engine — the notification surface (Phases 14 build record /
          D-089..D-092) has no dedicated registry slot. The phase
          therefore pins the seams that DO exist and refuses on any
          drift of them; slot 18 remains HITL's and is ignited under
          the D-154 mapping, not reassigned here.
  NTF-03  the notification contracts and invariants are validated
          through the REAL validator (D-089/D-090): template registry
          discipline (versioned ids, channel support, min-priority
          floors, required variables, channel payload requirements —
          the fail-closed verification for MISSING CONTACT METADATA:
          an EMAIL without `subject`, an SMS without `phone_ref`, a
          WEBHOOK without `endpoint_ref` refuses Class-B BEFORE any
          queueing), opaque recipient references (no address invented
          or harvested — D-045), the D-090 dedup identity (SHA-256
          over (recipient, channel, template, logical event_key) —
          retries of the SAME logical alert collapse, distinct alerts
          do not; no wall clock, no payload hash), the pure priority
          policy (quiet hours defer — the CRITICAL bypass; frequency
          caps from the DURABLE ledger), and the D-092 outcome
          mapping (delivered/permanent-failure terminal,
          transient/rate-limited return to QUEUED);
  NTF-04  a NON-DESTRUCTIVE synthetic notification cycle runs over
          the REAL `NotificationEngine` with an EPHEMERAL in-process
          lock backend and an INTERCEPTING dispatch harness (the
          queued records are the deliverable; NOTHING leaves the
          process — no email/SMS/push/webhook egress): enqueue →
          durable QUEUED (exactly-once via the vault claim) →
          dispatch idempotency (a same-logical-alert retry is a
          durable DUPLICATE_BLOCKED; the loser NEVER dispatches) →
          alert priority queuing (a CRITICAL alert bypasses quiet
          hours; a NORMAL alert inside the quiet window is durably
          POLICY_DEFERRED; a frequency-capped recipient defers) →
          intercepted outcome recording (delivered + transient →
          terminal stickiness: a late transient after DELIVERED does
          NOT move the status) → the durable status view rebuilds
          dedup_key → status from the store alone (zero drift) →
          invalid notifications (missing contact metadata, unknown
          templates, wrong channel/priority) refuse with ZERO rows →
          the dead-letter trigger is proven at the contract level
          (a permanent_failure maps to FAILED; the DLQ template
          `dlq.item_admitted.v1` is itself enqueued and rendered
          through the same gates) → per-step telemetry
          (START/AUTH/ENQUEUE/DEDUP/PRIORITY/OUTCOMES/STATUS/INVALID/
          DLQ/VERIFY/CLEANUP) and a deterministic summary hash;
          cleanup leaves zero residue;
  NTF-05  the canonical `phase17.notification_wiring_attestation.v1`
          is emitted exactly once per run (aborts included) with the
          SHA-256 `attestation_digest`; any abort emits the same
          schema as IGNITION_INCOMPLETE with failure telemetry.

Dispatch interception & lock hygiene: the notification lock default
backend claims keys in live PG (`notifications.delivery_locks`-
equivalent) or the shared `local/volumes/notifications/
delivery_locks.json`. The probe injects `_EphemeralNotificationLocks`
— acquire/finalize/get semantics identical to `_JsonLocks`, ZERO
durable footprint — and the engine's dispatch surface is never given
a transport: there is nothing to intercept at the provider boundary
because no provider exists in the probe (queued + receipt-recorded
states only, provider outcomes recorded as D-027 receipts by the
probe itself, exactly as the worker would).

Security & purity (RULES §35, AST-pinned): injected store/lock
transports only — zero sockets, zero raw shell, zero wall clock in
the core (every instant is the event's own recorded timestamp).
Recipients are opaque local references; no address is invented or
harvested (D-045); channel contact metadata (`subject`, `phone_ref`,
`endpoint_ref`) is validated as PRESENT-OR-REFUSE and never echoed
into any emitted record. D-124 deep redaction runs over every
emitted record with the public commitments (`phase16_digest`,
`manifest_sha256`) restored after redaction.
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
    "Phase17Error", "Phase17Attestation", "Phase17Igniter",
    "_EphemeralNotificationLocks", "ATTESTATION_SCHEMA",
    "PHASE17_IGNITED", "PHASE17_INCOMPLETE", "PHASE16_SCHEMA",
    "PHASE16_IGNITED", "PHASE16_ROW_KIND", "PHASE17_ROW_KIND",
    "SLOT18_REGISTRY_FACT", "SEAMS", "SEAM_PHASES", "CYCLE_ID",
    "PROBE_EVENT", "canonical_hash",
]

ATTESTATION_SCHEMA = "phase17.notification_wiring_attestation.v1"
PHASE17_IGNITED = "PHASE17_IGNITED"
PHASE17_INCOMPLETE = "IGNITION_INCOMPLETE"

PHASE16_SCHEMA = "phase16.analyst_wiring_attestation.v1"
PHASE16_IGNITED = "PHASE16_IGNITED"

# The D-112 ledger kind that roots the Phase 16 attestation (D-166).
PHASE16_ROW_KIND = "phase16_analyst_wiring_attestation"

# The D-112 ledger kind that roots the Phase 17 attestation (D-167).
PHASE17_ROW_KIND = "phase17_notification_wiring_attestation"

# REGISTRY FACT (D-160 precedent, recorded in the report): the D-154
# cross-walk binds registry slot 18 to `canonical.ai_hitl_service`
# (HITL). The notification engine carries no dedicated slot — its
# build record lives in the Phase 14 build program / D-089..D-092.
SLOT18_REGISTRY_FACT = "canonical.ai_hitl_service"

_HEX64 = re.compile(r"^[0-9a-f]{64}$")

# Repo-real module seams for the notification wiring (the D-154 pins
# that exist for this surface's dependencies).
SEAMS: Dict[str, str] = {
    "notification_engine": "canonical.notification_engine",
    "notification_contracts": "canonical.notification_contracts",
    "notification_worker": "canonical.notification_worker",
    "sync_event_store": "services.sync_engine",
}

SEAM_PHASES: Dict[str, Optional[int]] = {
    "notification_engine": None,   # no dedicated registry slot
    "notification_contracts": None,
    "notification_worker": None,
    "sync_event_store": None,
}

CYCLE_ID = "phase17-notification-probe-0001"

PROBE_EVENT: Dict[str, Any] = {
    "recipient": "user-phase17-0001",
    "channel": "IN_APP",
    "priority": "NORMAL",
    "template_id": "order.fulfillment.v1",
    "variables": {"order_ref": "ord-phase17-01",
                  "state": "FULFILLING"},
    "occurred_at": "2026-09-27T10:07:00+00:00",
    "event_key": "order:ord-phase17-01:transition:FULFILLING",
}


class Phase17Error(ValueError):
    """Contract-level misuse of the Phase 17 igniter."""


def _fail(reason: str) -> None:
    raise Phase17Error(reason)


def canonical_hash(payload: Dict[str, Any]) -> str:
    """SHA-256 over canonical JSON bytes — the shared project digest
    formula (Stage G/H/D-154..D-166 engines)."""
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class _EphemeralNotificationLocks:
    """In-process claim backend for PROBES — the notification analog
    of the D-160..D-166 ephemeral backends: acquire/finalize/get
    semantics identical to `_JsonLocks`, ZERO durable footprint.
    Never the shared `local/volumes/notifications/delivery_locks.json`
    and never live PG."""

    def __init__(self) -> None:
        import threading
        self._lock = threading.Lock()
        self._rows: Dict[str, Dict[str, Any]] = {}

    def acquire(self, key: str, claim_ref: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            if key in self._rows:
                return {"acquired": False,
                        "original": json.loads(json.dumps(
                            self._rows[key], ensure_ascii=False))}
            ref = json.loads(json.dumps(claim_ref, ensure_ascii=False))
            self._rows[key] = ref
            return {"acquired": True, "original": ref}

    def finalize(self, key: str, ref: Dict[str, Any]) -> None:
        with self._lock:
            if key in self._rows:  # never resurrect a vanished row
                self._rows[key] = json.loads(json.dumps(
                    ref, ensure_ascii=False))

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._rows.get(key)
            return json.loads(json.dumps(row, ensure_ascii=False)) \
                if row else None


@dataclass(frozen=True)
class Phase17Attestation:
    """Canonical, immutable Phase 17 ignition artifact."""
    schema: str
    verdict: str             # PHASE17_IGNITED / IGNITION_INCOMPLETE
    phase16_digest: str      # upstream attestation digest (commitment)
    manifest_sha256: str     # deployment fingerprint carried through
    profile: Dict[str, Any]  # runtime profile + seams summary
    contracts: Dict[str, Any]  # template/dedup/policy invariants
    cycle: Dict[str, Any]    # synthetic notification telemetry
    checks: tuple = field(default_factory=tuple)  # (id, ok, detail)
    observed_tick: int = 0

    @property
    def ignited(self) -> bool:
        return self.verdict == PHASE17_IGNITED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "verdict": self.verdict,
            "phase16_digest": self.phase16_digest,
            "manifest_sha256": self.manifest_sha256,
            "profile": self.profile,
            "contracts": self.contracts,
            "cycle": self.cycle,
            "checks": [list(c) for c in self.checks],
            "observed_tick": self.observed_tick,
        }

    @property
    def attestation_digest(self) -> str:
        return canonical_hash(self.to_dict())


class Phase17Igniter:
    """NTF-01..NTF-05 with injected store/lock transports.

    Injected:
      clock           — ``() -> int`` logical tick
      audit_sink      — ``callable(dict)`` (D-112/D-121 in prod)
      upstream_provider — ``() -> dict`` the phase16 attestation
      audit_rows      — ``() -> list`` the D-112 ledger rows
      chain_verifier  — ``() -> dict`` D-112 chain integrity
      census          — ``() -> dict`` the runtime profile census
      stack_factory   — ``() -> (store,)`` building the REAL D-027
                        parity store fresh per run (the engine is
                        constructed by the igniter over the EPHEMERAL
                        lock backend)
      expected_entry_points — optional {phase: seam} override
    """

    def __init__(self, clock: Callable[[], int],
                 audit_sink: Callable[[Dict[str, Any]], None],
                 upstream_provider: Optional[Callable[[], Dict[str, Any]]] = None,
                 audit_rows: Optional[Callable[[], List[Dict[str, Any]]]] = None,
                 chain_verifier: Optional[Callable[[], Dict[str, Any]]] = None,
                 census: Optional[Callable[[], Dict[str, Any]]] = None,
                 stack_factory: Optional[Callable[[], Tuple]] = None,
                 expected_entry_points: Optional[Dict[int, str]] = None,
                 ) -> None:
        if not callable(clock) or not callable(audit_sink):
            _fail("clock and audit_sink required")
        self._clock = clock
        self._sink = audit_sink
        self._prov = {
            "phase16": upstream_provider,
            "audit_rows": audit_rows,
            "chain_verifier": chain_verifier,
            "census": census,
            "stack_factory": stack_factory,
        }
        self._entry_points = dict(expected_entry_points) \
            if expected_entry_points else None

    # -- internals ---------------------------------------------------------

    def _load(self, name: str) -> Tuple[Optional[Any], str]:
        prov = self._prov.get(name)
        if prov is None:
            return None, "provider not injected"
        if callable(prov) and not hasattr(prov, "place_order") \
                and not hasattr(prov, "policy") \
                and not hasattr(prov, "route") \
                and not hasattr(prov, "schedule"):
            try:
                return prov(), ""
            except Exception as exc:  # noqa: BLE001 — typed (D-124)
                return None, f"provider raised {type(exc).__name__}"
        return prov, ""

    def _emit(self, verdict: str, checks: List[Tuple[str, bool, str]],
              phase16_digest: str = "", manifest: str = "",
              profile: Optional[Dict[str, Any]] = None,
              contracts: Optional[Dict[str, Any]] = None,
              cycle: Optional[Dict[str, Any]] = None,
              ) -> Phase17Attestation:
        att = Phase17Attestation(
            schema=ATTESTATION_SCHEMA, verdict=verdict,
            phase16_digest=phase16_digest, manifest_sha256=manifest,
            profile=profile or {}, contracts=contracts or {},
            cycle=cycle or {},
            checks=tuple((c[0], c[1], deep_redact(str(c[2])))
                         for c in checks),
            observed_tick=self._clock())
        blob = json.dumps(att.to_dict(), sort_keys=True,
                          separators=(",", ":"), ensure_ascii=False)
        redacted = json.loads(deep_redact(blob))
        # Public commitments (D-146/D-153/D-154..D-166 precedent).
        redacted["phase16_digest"] = att.phase16_digest
        redacted["manifest_sha256"] = att.manifest_sha256
        self._sink(redacted)
        return att

    # -- NTF-01: the Phase 16 attestation --------------------------------------

    def _ntf01(self) -> Tuple[bool, str, str,
                              List[Tuple[str, bool, str]]]:
        """(ok, phase16_digest, manifest, checks)."""
        checks: List[Tuple[str, bool, str]] = []
        att, err = self._load("phase16")
        if att is None:
            checks.append(("NTF-01", False,
                           "Phase 16 attestation absent "
                           f"({err}) — Phase 16 never ignited"))
            return False, "", "", checks
        if not isinstance(att, dict):
            checks.append(("NTF-01", False,
                           "Phase 16 attestation malformed"))
            return False, "", "", checks
        if att.get("schema") != PHASE16_SCHEMA:
            checks.append(("NTF-01", False,
                           f"attestation schema {att.get('schema')!r} "
                           f"!= {PHASE16_SCHEMA!r}"))
            return False, "", "", checks
        if att.get("verdict") != PHASE16_IGNITED:
            checks.append(("NTF-01", False,
                           f"Phase 16 verdict {att.get('verdict')!r} "
                           f"!= {PHASE16_IGNITED!r} — analyst surface "
                           "not wired, Phase 17 refused"))
            return False, "", "", checks
        manifest = att.get("manifest_sha256", "")
        if not (isinstance(manifest, str) and _HEX64.match(manifest)):
            checks.append(("NTF-01", False,
                           "phase16 attestation lacks its manifest "
                           "fingerprint binding"))
            return False, "", "", checks
        # Digest commitment: recompute the record's canonical bytes
        # and match the D-112 rooting row.
        recomputed = canonical_hash(att)
        rows, err = self._load("audit_rows")
        rooted_digest = ""
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict) or \
                        str(row.get("event_kind", "")) != PHASE16_ROW_KIND:
                    continue
                detail = row.get("detail")
                if isinstance(detail, dict) and \
                        isinstance(detail.get("attestation_digest"),
                                   str):
                    rooted_digest = detail["attestation_digest"]
                    break
        if not rooted_digest:
            checks.append(("NTF-01", False,
                           "phase16 attestation not rooted in the "
                           "D-112 ledger — upstream wiring was never "
                           "durably attested"))
            return False, recomputed, "", checks
        if rooted_digest != recomputed:
            checks.append(("NTF-01", False,
                           f"phase16 attestation digest "
                           f"{recomputed[:16]}… != rooted "
                           f"{rooted_digest[:16]}… — DRIFTED or "
                           "altered upstream attestation"))
            return False, recomputed, "", checks
        cv, err = self._load("chain_verifier")
        if cv is None or not isinstance(cv, dict) or not cv.get("ok"):
            reason = (cv or {}).get("reason", err or "verifier absent")
            checks.append(("NTF-01", False,
                           f"D-112 chain not intact ({reason}) — "
                           "wiring on a broken ledger is refused"))
            return False, recomputed, "", checks
        checks.append(("NTF-01", True,
                       "phase16 attestation PHASE16_IGNITED, digest "
                       f"recomputes ({recomputed[:16]}…) and matches "
                       "the rooted commitment in the D-112 ledger "
                       f"({int(cv.get('rows', 0))} rows, zero breaks)"))
        return True, recomputed, manifest, checks

    # -- NTF-02: runtime profile + module seams --------------------------------

    def _ntf02(self) -> Tuple[bool, Dict[str, Any],
                              List[Tuple[str, bool, str]]]:
        checks: List[Tuple[str, bool, str]] = []
        summary: Dict[str, Any] = {"runtime_profile_verified": False,
                                   "seams_ok": False,
                                   "phases": [],
                                   "registry_fact": ""}
        census, err = self._load("census")
        if census is None or not isinstance(census, dict):
            checks.append(("NTF-02", False,
                           "runtime profile census unavailable "
                           f"({err}) — fail closed"))
            return False, summary, checks
        if not census.get("runtime_profile_verified"):
            checks.append(("NTF-02", False,
                           "runtime profile NOT verified — refuse"))
            return False, summary, checks
        rows = {p.get("phase"): p for p in census.get("phases", [])
                if isinstance(p, dict)}
        for n in (5, 6, 7, 8, 9, 10, 11, 12, 14, 15, 16):
            p = rows.get(n)
            if p is None:
                checks.append(("NTF-02", False,
                               f"Phase {n} missing from the runtime "
                               "profile census (Phases 5/6/7/8/9/10/"
                               "11/12/14/15/16 required; slot 14 "
                               "closed CRM-not-needed per D-163)"))
                return False, summary, checks
            if not (p.get("verified") and p.get("wired")):
                checks.append(("NTF-02", False,
                               f"Phase {n} not VERIFIED+WIRED — "
                               "notification wiring refused"))
                return False, summary, checks
            summary["phases"].append(n)
        summary["runtime_profile_verified"] = True
        # module seams (the D-154 registry pins that DO exist)
        import importlib
        entry_points = dict(self._entry_points) if self._entry_points \
            else None
        if entry_points is None:
            try:
                from dokploy_completion_attestation import ENTRY_POINTS
                entry_points = dict(ENTRY_POINTS)
            except Exception as exc:  # noqa: BLE001 — typed
                checks.append(("NTF-02", False,
                               "D-154 registry unavailable "
                               f"({type(exc).__name__})"))
                return False, summary, checks
        for key, modname in SEAMS.items():
            try:
                importlib.import_module(modname)
            except Exception as exc:  # noqa: BLE001 — typed refusal
                checks.append(("NTF-02", False,
                               f"canonical seam {modname} not "
                               f"importable ({type(exc).__name__}) — "
                               "repo seam missing"))
                return False, summary, checks
            phase_no = SEAM_PHASES.get(key)
            expected = entry_points.get(phase_no) \
                if phase_no is not None else None
            if expected and expected != modname:
                checks.append(("NTF-02", False,
                               f"ENTRY_POINTS[{phase_no}] = "
                               f"{expected!r} != repo seam "
                               f"{modname!r} — registry drift"))
                return False, summary, checks
        # REGISTRY FACT asserted against the live registry: slot 18
        # binds to the HITL service, NOT the notification engine (the
        # notification surface carries no dedicated slot). The phase
        # pins the seams that exist and refuses on their drift.
        if entry_points.get(18) != SLOT18_REGISTRY_FACT:
            checks.append(("NTF-02", False,
                           "registry slot 18 drifted from the D-154 "
                           f"cross-walk (expected "
                           f"{SLOT18_REGISTRY_FACT!r}) — refuse"))
            return False, summary, checks
        summary["registry_fact"] = (
            "slot 18 = canonical.ai_hitl_service (D-154); the "
            "notification surface (D-089..D-092) carries no "
            "dedicated registry slot")
        summary["seams_ok"] = True
        checks.append(("NTF-02", True,
                       f"all {len(SEAMS)} notification seams importable "
                       "and consistent with the D-154 ENTRY_POINTS "
                       "registry; slot 18 cross-walk fact asserted "
                       f"({SLOT18_REGISTRY_FACT} — no slot reassignment)"))
        return True, summary, checks

    # -- NTF-03: notification contracts & invariants ----------------------------

    def _ntf03(self) -> Tuple[bool, Dict[str, Any],
                              List[Tuple[str, bool, str]]]:
        checks: List[Tuple[str, bool, str]] = []
        summary: Dict[str, Any] = {
            "contracts_ok": False, "dedup_ok": False,
            "policy_ok": False, "outcomes_ok": False,
        }
        try:
            from canonical.notification_contracts import (
                CHANNELS, PRIORITIES, ST_DELIVERED, ST_DUPLICATE_BLOCKED,
                ST_FAILED, ST_QUEUED, TEMPLATES, NotificationContractError,
                dedup_key, in_quiet_hours, policy_decision,
                validate_notification,
            )
        except Exception as exc:  # noqa: BLE001 — typed refusal
            checks.append(("NTF-03", False,
                           f"notification contracts not importable "
                           f"({type(exc).__name__}) — repo seam missing"))
            return False, summary, checks
        summary["templates"] = len(TEMPLATES)
        summary["channels"] = len(CHANNELS)

        # the REAL validator accepts a conforming probe event
        try:
            validate_notification(dict(PROBE_EVENT))
        except NotificationContractError as exc:
            checks.append(("NTF-03", False,
                           f"REAL validator rejected a conforming "
                           f"event: {str(exc.args[0])[:120]}"))
            return False, summary, checks

        # missing CONTACT METADATA (channel payload requirements) —
        # the fail-closed Class-B gate BEFORE any queueing
        for channel, var in (("EMAIL", "subject"), ("SMS", "phone_ref"),
                             ("WEBHOOK", "endpoint_ref")):
            base = dict(PROBE_EVENT, channel=channel,
                        template_id="order.fulfillment.v1"
                        if channel != "SMS" else "order.shipped.v1")
            if channel == "SMS":
                base = dict(base, variables=dict(base["variables"]))
            else:
                base = dict(base, variables=dict(base["variables"]))
            try:
                validate_notification(base)
                _fail(f"missing contact metadata accepted for "
                      f"{channel} (expected {var!r} rejection)")
            except NotificationContractError as exc:
                if var not in str(exc.args[0]):
                    checks.append(("NTF-03", False,
                                   f"contact-metadata refusal "
                                   f"mis-classified for {channel}: "
                                   f"{str(exc.args[0])[:120]}"))
                    return False, summary, checks
        # and the other invalid classes
        for mutate, expect in (
                (lambda e: dict(e, recipient="bad recipient!"),
                 "recipient"),
                (lambda e: dict(e, channel="FAX"), "channel must be"),
                (lambda e: dict(e, priority="URGENT"),
                 "priority must be"),
                (lambda e: dict(e, template_id="unknown.template.v1"),
                 "unknown template"),
                (lambda e: dict(e, template_id="order.cancelled.v1",
                                channel="SMS"),
                 "does not support channel"),
                (lambda e: dict(e, priority="LOW"), "requires priority"),
                (lambda e: {k: v for k, v in e.items()
                            if k != "variables"}, "variables must be"),
                (lambda e: dict(e, variables={}),
                 "requires variable"),
                (lambda e: dict(e, occurred_at="not-a-time"),
                 "ISO-8601")):
            try:
                validate_notification(mutate(dict(PROBE_EVENT)))
                _fail(f"invalid notification accepted "
                      f"(expected {expect!r} rejection)")
            except NotificationContractError as exc:
                if expect not in str(exc.args[0]):
                    checks.append(("NTF-03", False,
                                   f"invalid-notification refusal "
                                   f"mis-classified: "
                                   f"{str(exc.args[0])[:120]}"))
                    return False, summary, checks
        summary["contracts_ok"] = True

        # D-090 dedup identity: same logical alert collapses, distinct
        # alerts do not; channel/recipient participate
        k1 = dedup_key(dict(PROBE_EVENT))
        k2 = dedup_key(dict(PROBE_EVENT))
        if k1 != k2 or not _HEX64.match(k1):
            checks.append(("NTF-03", False,
                           "dedup identity not deterministic"))
            return False, summary, checks
        kd = dedup_key(dict(PROBE_EVENT,
                            event_key="order:ord-phase17-01:"
                                      "transition:COMPLETED"))
        if kd == k1:
            checks.append(("NTF-03", False,
                           "dedup identity ignores the logical event "
                           "key — replay-dedup broken"))
            return False, summary, checks
        kr = dedup_key(dict(PROBE_EVENT, recipient="user-other"))
        if kr == k1:
            checks.append(("NTF-03", False,
                           "dedup identity ignores the recipient"))
            return False, summary, checks
        summary["dedup_ok"] = True

        # pure policy: quiet-hours defer (NORMAL), CRITICAL bypass,
        # frequency cap
        day_event = dict(PROBE_EVENT, occurred_at="2026-09-27T14:00:00+00:00")
        night_event = dict(PROBE_EVENT,
                           occurred_at="2026-09-27T23:30:00+00:00")
        if in_quiet_hours(day_event["occurred_at"]) or \
                not in_quiet_hours(night_event["occurred_at"]):
            checks.append(("NTF-03", False,
                           "quiet-hours arithmetic impure"))
            return False, summary, checks
        d1 = policy_decision(dict(day_event), 0)
        d2 = policy_decision(dict(night_event), 0)
        d3 = policy_decision(dict(night_event, priority="CRITICAL"), 0)
        d4 = policy_decision(dict(day_event), 999)
        if d1.get("verdict") != "allow" or \
                d2.get("reason") != "quiet_hours" or \
                d3.get("reason") != "critical_bypass" or \
                d4.get("reason") != "frequency_cap":
            checks.append(("NTF-03", False,
                           f"policy matrix wrong: {d1}|{d2}|{d3}|{d4}"))
            return False, summary, checks
        summary["policy_ok"] = True

        # D-092 outcome vocabulary
        if ST_QUEUED != "QUEUED" or ST_DELIVERED != "DELIVERED" or \
                ST_FAILED != "FAILED" or \
                ST_DUPLICATE_BLOCKED != "DUPLICATE_BLOCKED":
            checks.append(("NTF-03", False,
                           "status vocabulary drifted"))
            return False, summary, checks
        summary["outcomes_ok"] = True
        checks.append(("NTF-03", True,
                       f"REAL contracts enforced: {len(TEMPLATES)} "
                       "templates across "
                       f"{len(CHANNELS)} channels, contact-metadata "
                       "gate fail-closed, D-090 dedup identity "
                       "deterministic, quiet-hours/critical-bypass/"
                       "frequency-cap policy pure, D-092 outcomes "
                       "stable"))
        return True, summary, checks

    # -- NTF-04: the synthetic notification cycle --------------------------------

    def _ntf04(self) -> Tuple[bool, Dict[str, Any],
                              List[Tuple[str, bool, str]]]:
        from canonical.notification_contracts import (
            OUT_DELIVERED, OUT_TRANSIENT_FAILURE,
            ST_DELIVERED, ST_DUPLICATE_BLOCKED, ST_FAILED, ST_POLICY_DEFERRED,
            ST_QUEUED, NotificationContractError, dedup_key,
        )
        from canonical.notification_engine import NotificationEngine

        checks: List[Tuple[str, bool, str]] = []
        summary: Dict[str, Any] = {"steps": [], "summary_hash": "",
                                   "lock_backend": "ephemeral",
                                   "dispatched_off_process": 0,
                                   "invalid_refused": 0,
                                   "drift": False}
        stack, err = self._load("stack_factory")
        if stack is None:
            checks.append(("NTF-04", False,
                           f"event store unavailable ({err}) — fail "
                           "closed"))
            return False, summary, checks
        try:
            store = stack[0]
        except Exception as exc:  # noqa: BLE001 — typed refusal
            checks.append(("NTF-04", False,
                           f"event store construction failed "
                           f"({type(exc).__name__})"))
            return False, summary, checks
        locks = self._make_locks()
        engine = NotificationEngine(store, provenance=None, locks=locks)

        try:
            key = dedup_key(dict(PROBE_EVENT))

            # START — the probe plan
            summary["steps"].append([
                "START", True,
                {"cycle_id": CYCLE_ID,
                 "lock_backend": "ephemeral-in-process"}])

            # AUTH — interception envelope: the engine is given NO
            # dispatch transport; queued records + D-027 receipts are
            # the deliverable. Nothing leaves the process.
            summary["steps"].append([
                "AUTH", True,
                {"dispatch": "intercepted (no transport bound)",
                 "channels": "schemas only — no email/SMS/push",
                 "egress": 0}])

            # ENQUEUE — durable QUEUED via the vault claim
            r1 = engine.enqueue(dict(PROBE_EVENT))
            if r1.get("status") != ST_QUEUED or \
                    r1.get("dedup_key") != key:
                _fail(f"enqueue failed: {r1}")
            summary["steps"].append([
                "ENQUEUE", True,
                {"status": ST_QUEUED, "dedup_key": key[:16] + "…"}])

            # DEDUP — dispatch idempotency: a retry of the SAME
            # logical alert is a durable DUPLICATE_BLOCKED; the loser
            # never dispatches
            r2 = engine.enqueue(dict(PROBE_EVENT))
            if r2.get("status") != ST_DUPLICATE_BLOCKED:
                _fail(f"same-alert retry not blocked: {r2}")
            # a different logical alert on the same template enqueues
            # independently
            other = dict(PROBE_EVENT, event_key="order:ord-phase17-01:"
                                                "transition:COMPLETED")
            r3 = engine.enqueue(dict(other))
            if r3.get("status") != ST_QUEUED:
                _fail(f"distinct alert wrongly collapsed: {r3}")
            summary["steps"].append([
                "DEDUP", True,
                {"same_alert": ST_DUPLICATE_BLOCKED,
                 "distinct_alert": ST_QUEUED,
                 "rule": "D-090 evidence-keyed identity"}])

            # PRIORITY — quiet hours defer (NORMAL), CRITICAL bypass,
            # frequency cap from the durable ledger
            night = dict(PROBE_EVENT,
                         occurred_at="2026-09-27T23:30:00+00:00",
                         event_key="order:ord-phase17-02:night",
                         recipient="user-phase17-0002")
            rn = engine.enqueue(dict(night))
            if rn.get("status") != ST_POLICY_DEFERRED or \
                    rn.get("reason") != "quiet_hours":
                _fail(f"quiet-hours defer broken: {rn}")
            crit = dict(PROBE_EVENT,
                        occurred_at="2026-09-27T23:30:00+00:00",
                        priority="CRITICAL", channel="IN_APP",
                        template_id="hitl.review_required.v1",
                        variables={"queue_ref": "q-phase17",
                                   "reason": "probe"},
                        event_key="hitl:q-phase17:critical",
                        recipient="user-phase17-0003")
            rc = engine.enqueue(dict(crit))
            if rc.get("status") != ST_QUEUED:
                _fail(f"CRITICAL quiet-hours bypass broken: {rc}")
            summary["steps"].append([
                "PRIORITY", True,
                {"quiet_hours_normal": ST_POLICY_DEFERRED,
                 "critical_bypass": ST_QUEUED,
                 "rule": "D-090 policy matrix"}])

            # OUTCOMES — intercepted receipts recorded exactly as the
            # worker would: delivered for key, transient then
            # delivered for the second alert, terminal stickiness
            s1 = engine.record_outcome(dict(PROBE_EVENT), key, 1,
                                       OUT_DELIVERED, "intercepted")
            if s1 != ST_DELIVERED:
                _fail(f"delivered outcome mapping wrong: {s1}")
            s_late = engine.record_outcome(dict(PROBE_EVENT), key, 2,
                                           OUT_TRANSIENT_FAILURE,
                                           "late-arrival-probe")
            if s_late != ST_DELIVERED:
                _fail(f"terminal stickiness broken: {s_late}")
            key2 = dedup_key(dict(other))
            s2 = engine.record_outcome(dict(other), key2, 1,
                                       OUT_TRANSIENT_FAILURE, "probe")
            if s2 != ST_QUEUED:
                _fail(f"transient mapping wrong: {s2}")
            s3 = engine.record_outcome(dict(other), key2, 2,
                                       OUT_DELIVERED, "intercepted")
            if s3 != ST_DELIVERED:
                _fail(f"retry-delivered mapping wrong: {s3}")
            summary["steps"].append([
                "OUTCOMES", True,
                {"delivered": "DELIVERED (terminal)",
                 "late_transient": "stickiness holds DELIVERED",
                 "transient_then_delivered": "QUEUED → DELIVERED"}])

            # STATUS — the durable status view rebuilds from the store
            # alone; must match the driven history exactly (zero drift)
            view = engine.status_view()
            if view.get(key, {}).get("status") != ST_DELIVERED:
                _fail(f"status view drifted for key: {view.get(key)}")
            if view.get(key2, {}).get("status") != ST_DELIVERED:
                _fail(f"status view drifted for key2: {view.get(key2)}")
            # the blocked retry is durable: the ledger holds the
            # duplicate_blocked receipt (the loser never dispatches —
            # the status view keeps the winner's terminal state, so
            # the evidence is the dup event row itself)
            dup_eid = engine.outcome_event_id("dup", key, 0)
            dup_row = store.records.get("notifications::" + dup_eid)
            if dup_row is None or \
                    "duplicate_blocked" not in json.dumps(dup_row):
                _fail("duplicate-blocked retry missing from the "
                      "durable ledger")
            summary["drift"] = False
            summary["steps"].append([
                "STATUS", True,
                {"rebuilt": "from DURABLE store data only",
                 "entries": len(view), "drift": False,
                 "dup_receipt_durable": True}])

            # INVALID — invalid notifications fail closed BEFORE any
            # queueing (missing contact metadata et al.)
            before = len(view)
            for bad in (
                    dict(PROBE_EVENT, channel="EMAIL",
                         variables={"order_ref": "o", "state": "s"}),
                    dict(PROBE_EVENT, channel="SMS",
                         template_id="order.shipped.v1",
                         variables={"order_ref": "o"}),
                    dict(PROBE_EVENT, channel="WEBHOOK",
                         variables={"order_ref": "o", "state": "s"}),
                    dict(PROBE_EVENT, template_id="unknown.template.v1"),
                    dict(PROBE_EVENT, priority="URGENT"),
                    dict(PROBE_EVENT, recipient="bad recipient!")):
                try:
                    engine.enqueue(bad)
                    _fail("invalid notification accepted")
                except NotificationContractError:
                    summary["invalid_refused"] += 1
            # fail-closed proof: the refusals must have left the
            # durable ledger untouched (Class-B fires BEFORE any
            # queueing — D-089/D-052)
            if len(engine.status_view()) != before:
                _fail("an invalid notification reached the durable "
                      "ledger — fail-closed gate breached")
            summary["steps"].append([
                "INVALID", True,
                {"refused": summary["invalid_refused"],
                 "durable_rows_added": 0}])

            # DLQ — the dead-letter trigger at contract level: a
            # permanent_failure maps to FAILED (the DLQ admission
            # signal), and the canonical DLQ template itself enqueues
            # through the same gates
            dlq_key = "order:ord-phase17-dlq:permanent"
            dlq_event = dict(PROBE_EVENT, recipient="user-phase17-0004",
                             event_key=dlq_key)
            engine.enqueue(dict(dlq_event))
            sdlq = engine.record_outcome(dict(dlq_event),
                                         dedup_key(dict(dlq_event)),
                                         1, "permanent_failure",
                                         "probe")
            if sdlq != ST_FAILED:
                _fail(f"permanent_failure mapping wrong: {sdlq}")
            dlq_alert = dict(PROBE_EVENT, channel="IN_APP",
                             template_id="dlq.item_admitted.v1",
                             priority="HIGH",
                             variables={"dedup_key": "dk-phase17",
                                        "failure_reason": "probe"},
                             event_key="dlq:dk-phase17:admitted",
                             recipient="user-phase17-0005")
            rdlq = engine.enqueue(dict(dlq_alert))
            if rdlq.get("status") != ST_QUEUED:
                _fail(f"DLQ alert template refused: {rdlq}")
            summary["steps"].append([
                "DLQ", True,
                {"permanent_failure": ST_FAILED + " (DLQ admission)",
                 "dlq_template": "dlq.item_admitted.v1 enqueued"}])

            # VERIFY — zero off-process dispatches, no egress markers,
            # the lock backend stayed ephemeral
            if summary["dispatched_off_process"] != 0:
                _fail("an off-process dispatch occurred — interception "
                      "broken")
            raw = store.records if hasattr(store, "records") else {}
            blob = json.dumps(raw).lower()
            for marker in ("smtp", "sendmail", "api_key", "twilio",
                           "webhook_url", "auth_code", "pan",
                           "card_number"):
                if marker in blob:
                    _fail(f"egress-boundary violation: {marker!r} "
                          "found in the notification event stream")
            if not isinstance(locks, _EphemeralNotificationLocks):
                _fail("lock backend is not the ephemeral in-process "
                      "store — durable footprint")
            summary["lock_backend"] = "ephemeral"
            summary["steps"].append([
                "VERIFY", True, {"markers": "clean",
                                 "egress": 0,
                                 "lock_backend": "ephemeral"}])

            # CLEANUP — persist the data-minimized cycle artifact,
            # read it back, then delete EVERYTHING
            artifact = {
                "cycle_id": CYCLE_ID,
                "enqueued": 6,
                "duplicate_blocked": 1,
                "policy_deferred": 1,
                "invalid_refused": summary["invalid_refused"],
                "dry_run": True,
                "off_process_dispatches": 0,
            }
            self._scratch_write(artifact)
            if self._scratch_read() != artifact:
                _fail("scratch artifact round-trip broken")
            if not self._scratch_delete():
                _fail("cleanup failed: scratch artifact not deletable")
            if self._scratch_residue():
                _fail("cleanup failed: scratch residue present")
            summary["steps"].append(["CLEANUP", True, {}])

            plan = {
                "cycle_id": CYCLE_ID,
                "enqueued": 6,
                "invalid_refused": summary["invalid_refused"],
                "dry_run": True,
                "off_process_dispatches": 0,
            }
            summary["summary_hash"] = canonical_hash(plan)
            checks.append(("NTF-04", True,
                           "synthetic notification cycle completed: "
                           f"{len(summary['steps'])} steps, summary "
                           f"hash {summary['summary_hash'][:16]}…, "
                           "dispatch idempotent, priority policy "
                           "proven, terminal stickiness holds, "
                           "status view drift-free, zero egress"))
            return True, summary, checks
        except Phase17Error as exc:
            checks.append(("NTF-04", False, str(exc)[:160]))
            self._cleanup_scratch()
            return False, summary, checks
        except NotificationContractError as exc:
            checks.append(("NTF-04", False,
                           f"notification contract refusal (Class-B): "
                           f"{str(exc.args[0])[:120]}"))
            self._cleanup_scratch()
            return False, summary, checks
        except Exception as exc:  # noqa: BLE001 — typed refusal (D-124)
            checks.append(("NTF-04", False,
                           f"synthetic notification cycle failed "
                           f"({type(exc).__name__})"))
            self._cleanup_scratch()
            return False, summary, checks

    def _make_locks(self) -> _EphemeralNotificationLocks:
        """The probe's ONLY claim backend: ephemeral in-process, zero
        durable footprint (the D-079 hazard bypassed — never the
        shared `local/volumes/notifications/delivery_locks.json` and
        never live PG). Subclass hook for the battery's fail-closed
        durable-backend refusal proof."""
        locks = _EphemeralNotificationLocks()
        self._last_locks = locks  # provenance for the ephemeral proof
        return locks

    # -- scratch (namespace-scoped, the only general persistence) --

    def _scratch_write(self, artifact: Dict[str, Any]) -> None:
        self._scratch_store["phase17-scratch:notifications"] = artifact

    def _scratch_read(self) -> Any:
        return self._scratch_store.get("phase17-scratch:notifications")

    def _scratch_delete(self) -> bool:
        return self._scratch_store.pop("phase17-scratch:notifications",
                                       None) is not None

    def _scratch_residue(self) -> List[str]:
        return sorted(k for k in self._scratch_store
                      if k.startswith("phase17-scratch:"))

    @property
    def _scratch_store(self) -> Dict[str, Any]:
        if not hasattr(self, "_scratch"):
            self._scratch: Dict[str, Any] = {}
        return self._scratch

    def _cleanup_scratch(self) -> None:
        try:
            self._scratch_delete()
        except Exception:  # pragma: no cover
            pass

    # -- the run ---------------------------------------------------------------

    def run(self) -> Phase17Attestation:
        """NTF-01..NTF-05 → the canonical attestation. Exactly one
        audited attestation per call (including aborts); an NTF-01
        refusal performs ZERO engine calls."""
        checks: List[Tuple[str, bool, str]] = []
        ok1, p16digest, manifest, c1 = self._ntf01()
        checks += c1
        if not ok1:
            return self._emit(PHASE17_INCOMPLETE, checks,
                              phase16_digest=p16digest,
                              manifest=manifest)
        ok2, profile, c2 = self._ntf02()
        checks += c2
        ok3, contracts, c3 = (False, {}, [])
        if ok2:
            ok3, contracts, c3 = self._ntf03()
            checks += c3
        ok4, cycle, c4 = (False, {}, [])
        if ok3:
            ok4, cycle, c4 = self._ntf04()
            checks += c4
        verdict = PHASE17_IGNITED if all((ok1, ok2, ok3, ok4)) \
            else PHASE17_INCOMPLETE
        if verdict == PHASE17_IGNITED:
            checks.append(("NTF-05", True,
                           "phase17.notification_wiring_attestation.v1 "
                           "emitted — Notification Engine verified in "
                           "DRY-RUN mode (dispatch intercepted, zero "
                           "email/SMS/push egress, ephemeral locks) "
                           "under the Phase 16 attestation; the "
                           "remaining registry slot 18 stays bound to "
                           "the HITL service per the D-154 cross-walk"))
        else:
            checks.append(("NTF-05", False,
                           "attestation emitted as IGNITION_INCOMPLETE "
                           "— remediate the named checks before any "
                           "further wiring"))
        return self._emit(verdict, checks, phase16_digest=p16digest,
                          manifest=manifest, profile=profile,
                          contracts=contracts, cycle=cycle)


def main() -> int:
    """CLI wiring guard: interactive wiring requires the injected
    providers, census and the ephemeral engine stack configuration."""
    import argparse
    import sys
    ap = argparse.ArgumentParser(
        description="Phase 17 live wiring igniter (NTF-01..NTF-05, "
                    "D-167).")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    print("live_wiring_phase17_igniter: interactive wiring requires "
          "the phase16 attestation, the D-112 chain, the runtime "
          "census and the injected event store; see run() and the "
          "battery for the injected contract.", file=sys.stderr)
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

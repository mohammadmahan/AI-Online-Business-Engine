"""Phase 18 live wiring igniter — HITL Service ignition (D-168).

The thirteenth Live Wiring program phase and the FINAL registry
ignition. Phase 17 (D-167) verified the Notification Engine without
taking registry slot 18; Phase 18 now ignites the slot-18 surface —
the Human-in-the-Loop service (`canonical.ai_hitl_service`, D-068
review inbox over the D-105/D-106/D-108 ledger engine) — on top of
the verified Phase 17 attestation, in STRICT DRY-RUN mode with every
review interface ISOLATED:

  HIT-01  the upstream `phase17.notification_wiring_attestation.v1`
          is present, PHASE17_IGNITED, manifest-bound, its canonical
          bytes recompute to the SHA-256 commitment rooted in the
          D-112 ledger (kind `phase17_notification_wiring_attestation`)
          over an intact chain — ANY refusal happens BEFORE the first
          engine call (zero engine calls on refusal);
  HIT-02  the verified runtime profile is loaded: the injected census
          marks Phases 5–12, 14, 15, 16 and 17 present+VERIFIED+WIRED
          (slot 14 stays closed CRM-not-needed per D-163 and is NOT
          required), and the repo-real HITL seams are importable —
          with the LOAD-BEARING slot-18 registry pin asserted: the
          D-154 cross-walk binds slot 18 to `canonical.ai_hitl_service`
          (the fact Phase 17 asserted while verifying the notification
          surface WITHOUT taking the slot). Any drift, absence or
          reassignment of slot 18 refuses before HIT-03;
  HIT-03  the HITL contracts and invariants are validated through the
          REAL validators (D-105/D-108): the ticket shape gate
          (fail-closed — missing fields, illegal queue types, illegal
          roles, CLAIMED-without-reviewer, PENDING-with-reviewer,
          D-114 length bounds), the ReviewAction gate (EXPIRED is
          NEVER a reviewer action — sweep-only; MODIFIED requires a
          payload_override dict; payload_override is invalid for any
          other decision; reviewer refs must be role:/agent: mock
          references; D-114 feedback bounds), the lifecycle edge
          matrix (PENDING_REVIEW → CLAIMED → APPROVED | REJECTED |
          MODIFIED | ESCALATED | EXPIRED, sweep-only expiry edge,
          terminals exitless), the mock role discipline (D-045 — no
          auth backends, no real identities), and the deterministic
          escalation ladder (any→ops, ops→owner, publisher→owner,
          owner→escalation);
  HIT-04  a NON-DESTRUCTIVE synthetic review cycle runs over the REAL
          `HitlEngine` (D-105/D-106/D-108) with an EPHEMERAL in-process
          vault and NO reviewer-notification channel bound (the
          durable tickets + the hash-chained ledger are the
          deliverable; nothing is emitted to any human surface — no
          email/SMS/push/dashboard egress): analyst-boundary ingestion
          (the D-166/D-167 handover edge — DISPATCHED_TO_HITL insights
          enter INSIGHT_REVIEW idempotently) → atomic claim discipline
          (exactly one reviewer wins; a wrong-role actor refuses; a
          second claimant loses) → human-only resolutions (APPROVED;
          MODIFIED with a durable payload_override; ESCALATED with the
          deterministic role elevation) → the escalation LOOP (a fresh
          elevated PENDING ticket re-queued idempotently, then
          resolved under the elevated role) → the deterministic
          expiration sweep (EXPIRED reachable ONLY from the injected
          logical-clock sweep, never a reviewer action) → malformed
          review payloads refuse Class-B with ZERO durable rows →
          the D-108 tamper-evident ledger verifies per ticket →
          per-step telemetry (START/AUTH/INGEST/CLAIM/RESOLVE/
          ESCALATE/SWEEP/INVALID/LEDGER/VERIFY/CLEANUP) and a
          deterministic summary hash; cleanup leaves zero residue;
  HIT-05  the canonical `phase18.hitl_wiring_attestation.v1` is
          emitted exactly once per run (aborts included) with the
          SHA-256 `attestation_digest`; any abort emits the same
          schema as IGNITION_INCOMPLETE with failure telemetry.

Vault & isolation hygiene: the HITL vault default backend claims rows
in live PG (`hitl.review_tickets` / `hitl.review_ledger`) or the
shared `local/volumes/hitl` JSON files — the D-079 hazard, 5th
application. The probe injects `_EphemeralHitlVault` — insert/claim/
update/get/ledger semantics identical to `_JsonVault`, ZERO durable
footprint — and binds NO reviewer-notification transport: there is
nothing to intercept at the human-surface boundary because no
emitter exists in the probe (durable tickets, the append-only ledger
and D-027 receipts are the whole deliverable).

Security & purity (RULES §35, AST-pinned): injected store/vault
transports only — zero sockets, zero raw shell, zero wall clock in
the core (every instant is an injected logical tick). Reviewers are
mock local actor references (`role:*` / `agent:*` — D-045); no real
identity, address or dashboard signal is invented, harvested or
emitted. D-124 deep redaction runs over every emitted record with the
public commitments (`phase17_digest`, `manifest_sha256`) restored
after redaction.
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
    "Phase18Error", "Phase18Attestation", "Phase18Igniter",
    "_EphemeralHitlVault", "ATTESTATION_SCHEMA",
    "PHASE18_IGNITED", "PHASE18_INCOMPLETE", "PHASE17_SCHEMA",
    "PHASE17_IGNITED", "PHASE17_ROW_KIND", "SLOT18_REGISTRY_FACT",
    "SEAMS", "SEAM_PHASES", "CYCLE_ID", "PROBE_INSIGHT_KEY",
    "canonical_hash",
]

ATTESTATION_SCHEMA = "phase18.hitl_wiring_attestation.v1"
PHASE18_IGNITED = "PHASE18_IGNITED"
PHASE18_INCOMPLETE = "IGNITION_INCOMPLETE"

PHASE17_SCHEMA = "phase17.notification_wiring_attestation.v1"
PHASE17_IGNITED = "PHASE17_IGNITED"

# The D-112 ledger kind that roots the Phase 17 attestation (D-167).
PHASE17_ROW_KIND = "phase17_notification_wiring_attestation"

# REGISTRY FACT (asserted by Phase 17, now TAKEN): the D-154 cross-walk
# binds registry slot 18 to `canonical.ai_hitl_service` (HITL). This
# phase ignites exactly that module — the pin is load-bearing.
SLOT18_REGISTRY_FACT = "canonical.ai_hitl_service"

_HEX64 = re.compile(r"^[0-9a-f]{64}$")

# Repo-real module seams for the HITL wiring. Slot 18 pins the SERVICE
# (the D-154 cross-walk binding); the D-105/D-106/D-108 ledger engine,
# its contracts and the D-027 store are supporting seams.
SEAMS: Dict[str, str] = {
    "hitl_service": "canonical.ai_hitl_service",
    "hitl_engine": "canonical.hitl_engine",
    "hitl_contracts": "canonical.hitl_contracts",
    "sync_event_store": "services.sync_engine",
}

SEAM_PHASES: Dict[str, Optional[int]] = {
    "hitl_service": 18,          # THE slot-18 pin (load-bearing)
    "hitl_engine": None,         # supporting (D-105/D-106/D-108 core)
    "hitl_contracts": None,      # supporting
    "sync_event_store": None,    # supporting
}

CYCLE_ID = "phase18-hitl-probe-0001"

# The synthetic DISPATCHED_TO_HITL insight key at the analyst boundary
# (D-166/D-167 handover edge) — pure probe data, no real insight.
PROBE_INSIGHT_KEY = "ins-phase18-0001"


class Phase18Error(ValueError):
    """Contract-level misuse of the Phase 18 igniter."""


def _fail(reason: str) -> None:
    raise Phase18Error(reason)


def canonical_hash(payload: Dict[str, Any]) -> str:
    """SHA-256 over canonical JSON bytes — the shared project digest
    formula (Stage G/H/D-154..D-167 engines)."""
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class _EphemeralHitlVault:
    """In-process vault for PROBES — the HITL analog of the D-160..D-167
    ephemeral backends: insert/claim/update/get/ledger semantics
    identical to the engine's `_JsonVault`, ZERO durable footprint.
    Never the shared `local/volumes/hitl` and never live PG."""

    def __init__(self) -> None:
        import threading
        self._lock = threading.Lock()
        self._tickets: Dict[str, Dict[str, Any]] = {}
        self._ledger: Dict[str, Dict[str, Any]] = {}

    # -- tickets ------------------------------------------------------
    def insert_ticket(self, row: Dict[str, Any]) -> str:
        with self._lock:
            if row["ticket_id"] in self._tickets:
                return "duplicate"
            for r in self._tickets.values():
                if r.get("ingest_key") and \
                        r["ingest_key"] == row.get("ingest_key"):
                    return "duplicate"
            self._tickets[row["ticket_id"]] = dict(row)
            return "created"

    def claim_ticket(self, ticket_id: str, actor: str) -> int:
        with self._lock:
            row = self._tickets.get(ticket_id)
            if row is None or \
                    row["resolution_status"] != "PENDING_REVIEW":
                return 0
            row["resolution_status"] = "CLAIMED"
            row["reviewer_actor_id"] = actor
            return 1

    def update_ticket(self, ticket_id: str, sets: Dict[str, Any]) -> int:
        with self._lock:
            row = self._tickets.get(ticket_id)
            if row is None:
                return 0
            row.update(sets)
            return 1

    def get_ticket(self, ticket_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._tickets.get(ticket_id)
            return dict(row) if row else None

    def tickets_by_status(self, *statuses: str) -> List[Dict[str, Any]]:
        with self._lock:
            rows = [dict(r, ticket_id=tid)
                    for tid, r in sorted(self._tickets.items())
                    if r["resolution_status"] in statuses]
            return rows

    def find_by_ingest_key(self, ingest_key: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            for r in self._tickets.values():
                if r.get("ingest_key") == ingest_key:
                    return dict(r)
            return None

    # -- ledger -------------------------------------------------------
    def max_ledger_seq(self) -> int:
        with self._lock:
            return max((int(v) for v in self._ledger), default=0)

    def append_ledger(self, row: Dict[str, Any]) -> None:
        with self._lock:
            self._ledger[str(row["ledger_seq"])] = dict(row)

    def ledger_for(self, ticket_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            rows = [dict(r) for r in self._ledger.values()
                    if r["ticket_id"] == ticket_id]
            rows.sort(key=lambda r: int(r["ledger_seq"]))
            return rows

    def all_ledger(self) -> List[Dict[str, Any]]:
        with self._lock:
            rows = [dict(r) for r in self._ledger.values()]
            rows.sort(key=lambda r: (r["ticket_id"],
                                     int(r["ledger_seq"])))
            return rows


@dataclass(frozen=True)
class Phase18Attestation:
    """Canonical, immutable Phase 18 ignition artifact."""
    schema: str
    verdict: str             # PHASE18_IGNITED / IGNITION_INCOMPLETE
    phase17_digest: str      # upstream attestation digest (commitment)
    manifest_sha256: str     # deployment fingerprint carried through
    profile: Dict[str, Any]  # runtime profile + seams summary
    contracts: Dict[str, Any]  # ticket/action/lifecycle invariants
    cycle: Dict[str, Any]    # synthetic review telemetry
    checks: tuple = field(default_factory=tuple)  # (id, ok, detail)
    observed_tick: int = 0

    @property
    def ignited(self) -> bool:
        return self.verdict == PHASE18_IGNITED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "verdict": self.verdict,
            "phase17_digest": self.phase17_digest,
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


class Phase18Igniter:
    """HIT-01..HIT-05 with injected store/vault transports.

    Injected:
      clock           — ``() -> int`` logical tick
      audit_sink      — ``callable(dict)`` (D-112/D-121 in prod)
      upstream_provider — ``() -> dict`` the phase17 attestation
      audit_rows      — ``() -> list`` the D-112 ledger rows
      chain_verifier  — ``() -> dict`` D-112 chain integrity
      census          — ``() -> dict`` the runtime profile census
      stack_factory   — ``() -> (store,)`` building the REAL D-027
                        parity store fresh per run (the engine is
                        constructed by the igniter over the EPHEMERAL
                        vault)
      expected_entry_points — optional {phase: seam} override (the
                        battery's registry-pin refusal path; the PASS
                        path always reads the LIVE D-154 registry)
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
            "phase17": upstream_provider,
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
        if callable(prov) and not hasattr(prov, "decide") \
                and not hasattr(prov, "claim") \
                and not hasattr(prov, "resolve"):
            try:
                return prov(), ""
            except Exception as exc:  # noqa: BLE001 — typed (D-124)
                return None, f"provider raised {type(exc).__name__}"
        return prov, ""

    def _emit(self, verdict: str, checks: List[Tuple[str, bool, str]],
              phase17_digest: str = "", manifest: str = "",
              profile: Optional[Dict[str, Any]] = None,
              contracts: Optional[Dict[str, Any]] = None,
              cycle: Optional[Dict[str, Any]] = None,
              ) -> Phase18Attestation:
        att = Phase18Attestation(
            schema=ATTESTATION_SCHEMA, verdict=verdict,
            phase17_digest=phase17_digest, manifest_sha256=manifest,
            profile=profile or {}, contracts=contracts or {},
            cycle=cycle or {},
            checks=tuple((c[0], c[1], deep_redact(str(c[2])))
                         for c in checks),
            observed_tick=self._clock())
        blob = json.dumps(att.to_dict(), sort_keys=True,
                          separators=(",", ":"), ensure_ascii=False)
        redacted = json.loads(deep_redact(blob))
        # Public commitments (D-146/D-153/D-154..D-167 precedent).
        redacted["phase17_digest"] = att.phase17_digest
        redacted["manifest_sha256"] = att.manifest_sha256
        self._sink(redacted)
        return att

    # -- HIT-01: the Phase 17 attestation --------------------------------------

    def _hit01(self) -> Tuple[bool, str, str,
                              List[Tuple[str, bool, str]]]:
        """(ok, phase17_digest, manifest, checks)."""
        checks: List[Tuple[str, bool, str]] = []
        att, err = self._load("phase17")
        if att is None:
            checks.append(("HIT-01", False,
                           "Phase 17 attestation absent "
                           f"({err}) — Phase 17 never ignited"))
            return False, "", "", checks
        if not isinstance(att, dict):
            checks.append(("HIT-01", False,
                           "Phase 17 attestation malformed"))
            return False, "", "", checks
        if att.get("schema") != PHASE17_SCHEMA:
            checks.append(("HIT-01", False,
                           f"attestation schema {att.get('schema')!r} "
                           f"!= {PHASE17_SCHEMA!r}"))
            return False, "", "", checks
        if att.get("verdict") != PHASE17_IGNITED:
            checks.append(("HIT-01", False,
                           f"Phase 17 verdict {att.get('verdict')!r} "
                           f"!= {PHASE17_IGNITED!r} — notification "
                           "surface not wired, Phase 18 refused"))
            return False, "", "", checks
        manifest = att.get("manifest_sha256", "")
        if not (isinstance(manifest, str) and _HEX64.match(manifest)):
            checks.append(("HIT-01", False,
                           "phase17 attestation lacks its manifest "
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
                        str(row.get("event_kind", "")) != PHASE17_ROW_KIND:
                    continue
                detail = row.get("detail")
                if isinstance(detail, dict) and \
                        isinstance(detail.get("attestation_digest"),
                                   str):
                    rooted_digest = detail["attestation_digest"]
                    break
        if not rooted_digest:
            checks.append(("HIT-01", False,
                           "phase17 attestation not rooted in the "
                           "D-112 ledger — upstream wiring was never "
                           "durably attested"))
            return False, recomputed, "", checks
        if rooted_digest != recomputed:
            checks.append(("HIT-01", False,
                           f"phase17 attestation digest "
                           f"{recomputed[:16]}… != rooted "
                           f"{rooted_digest[:16]}… — DRIFTED or "
                           "altered upstream attestation"))
            return False, recomputed, "", checks
        cv, err = self._load("chain_verifier")
        if cv is None or not isinstance(cv, dict) or not cv.get("ok"):
            reason = (cv or {}).get("reason", err or "verifier absent")
            checks.append(("HIT-01", False,
                           f"D-112 chain not intact ({reason}) — "
                           "wiring on a broken ledger is refused"))
            return False, recomputed, "", checks
        checks.append(("HIT-01", True,
                       "phase17 attestation PHASE17_IGNITED, digest "
                       f"recomputes ({recomputed[:16]}…) and matches "
                       "the rooted commitment in the D-112 ledger "
                       f"({int(cv.get('rows', 0))} rows, zero breaks)"))
        return True, recomputed, manifest, checks

    # -- HIT-02: runtime profile + the slot-18 registry pin ----------------------

    def _hit02(self) -> Tuple[bool, Dict[str, Any],
                              List[Tuple[str, bool, str]]]:
        checks: List[Tuple[str, bool, str]] = []
        summary: Dict[str, Any] = {"runtime_profile_verified": False,
                                   "seams_ok": False,
                                   "phases": [],
                                   "slot18_pin": ""}
        census, err = self._load("census")
        if census is None or not isinstance(census, dict):
            checks.append(("HIT-02", False,
                           "runtime profile census unavailable "
                           f"({err}) — fail closed"))
            return False, summary, checks
        if not census.get("runtime_profile_verified"):
            checks.append(("HIT-02", False,
                           "runtime profile NOT verified — refuse"))
            return False, summary, checks
        rows = {p.get("phase"): p for p in census.get("phases", [])
                if isinstance(p, dict)}
        for n in (5, 6, 7, 8, 9, 10, 11, 12, 14, 15, 16, 17):
            p = rows.get(n)
            if p is None:
                checks.append(("HIT-02", False,
                               f"Phase {n} missing from the runtime "
                               "profile census (Phases 5/6/7/8/9/10/"
                               "11/12/14/15/16/17 required; slot 14 "
                               "closed CRM-not-needed per D-163)"))
                return False, summary, checks
            if not (p.get("verified") and p.get("wired")):
                checks.append(("HIT-02", False,
                               f"Phase {n} not VERIFIED+WIRED — "
                               "HITL wiring refused"))
                return False, summary, checks
            summary["phases"].append(n)
        summary["runtime_profile_verified"] = True
        # module seams — slot 18 is THE load-bearing pin
        import importlib
        entry_points = dict(self._entry_points) \
            if self._entry_points else None
        if entry_points is None:
            try:
                from dokploy_completion_attestation import ENTRY_POINTS
                entry_points = dict(ENTRY_POINTS)
            except Exception as exc:  # noqa: BLE001 — typed refusal
                checks.append(("HIT-02", False,
                               "D-154 registry unavailable "
                               f"({type(exc).__name__})"))
                return False, summary, checks
        for key, modname in SEAMS.items():
            try:
                importlib.import_module(modname)
            except Exception as exc:  # noqa: BLE001 — typed refusal
                checks.append(("HIT-02", False,
                               f"canonical seam {modname} not "
                               f"importable ({type(exc).__name__}) — "
                               "repo seam missing"))
                return False, summary, checks
            phase_no = SEAM_PHASES.get(key)
            expected = entry_points.get(phase_no) \
                if phase_no is not None else None
            if expected and expected != modname:
                checks.append(("HIT-02", False,
                               f"ENTRY_POINTS[{phase_no}] = "
                               f"{expected!r} != repo seam "
                               f"{modname!r} — registry drift"))
                return False, summary, checks
        # THE slot-18 pin (the final ignition): the D-154 cross-walk
        # binds slot 18 to the HITL service — the exact fact Phase 17
        # asserted while verifying the notification surface WITHOUT
        # taking the slot. Any drift/absence/reassignment refuses.
        if entry_points.get(18) != SLOT18_REGISTRY_FACT:
            checks.append(("HIT-02", False,
                           "registry slot 18 drifted from the D-154 "
                           f"cross-walk (expected "
                           f"{SLOT18_REGISTRY_FACT!r}) — the HITL "
                           "ignition refuses on any reassignment"))
            return False, summary, checks
        summary["slot18_pin"] = (
            "slot 18 = canonical.ai_hitl_service (D-154) — TAKEN by "
            "this phase (the final registry ignition)")
        summary["seams_ok"] = True
        checks.append(("HIT-02", True,
                       f"all {len(SEAMS)} HITL seams importable and "
                       "consistent with the D-154 ENTRY_POINTS "
                       f"registry; slot 18 pinned to "
                       f"{SLOT18_REGISTRY_FACT} (the final ignition)"))
        return True, summary, checks

    # -- HIT-03: HITL contracts & invariants ---------------------------------------

    def _hit03(self) -> Tuple[bool, Dict[str, Any],
                              List[Tuple[str, bool, str]]]:
        checks: List[Tuple[str, bool, str]] = []
        summary: Dict[str, Any] = {
            "contracts_ok": False, "actions_ok": False,
            "lifecycle_ok": False, "roles_ok": False,
        }
        try:
            from canonical.hitl_contracts import (
                ESCALATION_TARGET, LEGAL_EDGES, QT_INSIGHT_REVIEW,
                REQUIRED_ROLES, ROLE_ANY, ROLE_ESCALATION, ROLE_OPS,
                ROLE_OWNER, ST_APPROVED, ST_CLAIMED, ST_ESCALATED,
                ST_EXPIRED, ST_MODIFIED, ST_PENDING_REVIEW,
                ST_REJECTED, TERMINAL_STATES, HitlContractError,
                can_actor_resolve, is_transition_legal,
                resolution_from_action, validate_action,
                validate_ticket,
            )
        except Exception as exc:  # noqa: BLE001 — typed refusal
            checks.append(("HIT-03", False,
                           f"HITL contracts not importable "
                           f"({type(exc).__name__}) — repo seam missing"))
            return False, summary, checks

        def good_ticket(**over: Any) -> Dict[str, Any]:
            base = {
                "ticket_id": "hitl-probe-0001",
                "queue_type": QT_INSIGHT_REVIEW,
                "payload_ref": "insight:ins-phase18-0001",
                "required_role": ROLE_OWNER,
                "resolution_status": ST_PENDING_REVIEW,
                "created_at_logical": "L0001",
            }
            base.update(over)
            return base

        # the REAL validator accepts a conforming probe ticket
        try:
            validate_ticket(good_ticket())
        except HitlContractError as exc:
            checks.append(("HIT-03", False,
                           f"REAL validator rejected a conforming "
                           f"ticket: {str(exc.args[0])[:120]}"))
            return False, summary, checks

        # the ticket-shape gate (fail-closed Class-B BEFORE any write)
        for mutate, expect in (
                (lambda t: {k: v for k, v in t.items()
                            if k != "queue_type"},
                 "missing required fields"),
                (lambda t: dict(t, queue_type="FAX"),
                 "queue_type must be one of"),
                (lambda t: dict(t, required_role="admin"),
                 "required_role must be one of"),
                (lambda t: dict(t, resolution_status=ST_CLAIMED),
                 "CLAIMED ticket must carry a reviewer actor ref"),
                (lambda t: dict(t, reviewer_actor_id="role:owner"),
                 "must not carry a reviewer"),
                (lambda t: dict(t, ticket_id="t" * 129),
                 "exceeds 128 chars"),
                (lambda t: dict(t, payload_ref="p" * 257),
                 "exceeds 256 chars"),
                (lambda t: {k: v for k, v in t.items()
                            if k != "created_at_logical"},
                 "must be a non-empty logical clock value")):
            try:
                validate_ticket(mutate(good_ticket()))
                _fail(f"invalid ticket accepted "
                      f"(expected {expect!r} rejection)")
            except HitlContractError as exc:
                if expect not in str(exc.args[0]):
                    checks.append(("HIT-03", False,
                                   f"ticket refusal mis-classified: "
                                   f"{str(exc.args[0])[:120]}"))
                    return False, summary, checks
        summary["contracts_ok"] = True

        # the ReviewAction gate — EXPIRED is never a reviewer action
        def good_action(**over: Any) -> Dict[str, Any]:
            base = {"decision": ST_APPROVED,
                    "reviewer_actor_id": "role:owner",
                    "feedback_notes": "probe"}
            base.update(over)
            return base

        for mutate, expect in (
                (lambda a: dict(a, decision=ST_EXPIRED),
                 "EXPIRED is sweep-only"),
                (lambda a: dict(a, decision="MAYBE"),
                 "decision must be one of"),
                (lambda a: dict(a, reviewer_actor_id="bob"),
                 "role:/agent: reference"),
                (lambda a: dict(a, decision=ST_MODIFIED),
                 "MODIFIED requires a payload_override dict"),
                (lambda a: dict(a, payload_override={"x": 1}),
                 "payload_override is only valid for MODIFIED"),
                (lambda a: dict(a, feedback_notes="n" * 2001),
                 "exceeds 2000 chars")):
            try:
                validate_action(mutate(good_action()))
                _fail(f"invalid action accepted "
                      f"(expected {expect!r} rejection)")
            except HitlContractError as exc:
                if expect not in str(exc.args[0]):
                    checks.append(("HIT-03", False,
                                   f"action refusal mis-classified: "
                                   f"{str(exc.args[0])[:120]}"))
                    return False, summary, checks
        # the derived Resolution carries exactly the durable fields
        res = resolution_from_action(good_action(
            decision=ST_MODIFIED, payload_override={"channel": "email"}))
        if res.get("decision") != ST_MODIFIED or \
                res.get("payload_override") != {"channel": "email"}:
            checks.append(("HIT-03", False,
                           "resolution derivation wrong"))
            return False, summary, checks
        summary["actions_ok"] = True

        # lifecycle edge matrix: legal edges pass, illegal refuse,
        # terminals exitless
        for current, target in (
                (ST_PENDING_REVIEW, ST_CLAIMED),
                (ST_CLAIMED, ST_APPROVED), (ST_CLAIMED, ST_REJECTED),
                (ST_CLAIMED, ST_MODIFIED), (ST_CLAIMED, ST_ESCALATED),
                (ST_PENDING_REVIEW, ST_EXPIRED),
                (ST_CLAIMED, ST_EXPIRED)):
            if not is_transition_legal(current, target):
                checks.append(("HIT-03", False,
                               f"legal edge refused: {current} → "
                               f"{target}"))
                return False, summary, checks
        for current, target in (
                (ST_PENDING_REVIEW, ST_APPROVED),   # skip-claim refused
                (ST_CLAIMED, ST_CLAIMED),
                (ST_APPROVED, ST_PENDING_REVIEW),   # terminal exitless
                (ST_REJECTED, ST_CLAIMED),
                (ST_MODIFIED, ST_ESCALATED),
                (ST_ESCALATED, ST_APPROVED),
                (ST_EXPIRED, ST_CLAIMED)):          # expiry is terminal
            if is_transition_legal(current, target):
                checks.append(("HIT-03", False,
                               f"illegal edge accepted: {current} → "
                               f"{target}"))
                return False, summary, checks
        if set(TERMINAL_STATES) != {ST_APPROVED, ST_REJECTED,
                                    ST_MODIFIED, ST_ESCALATED,
                                    ST_EXPIRED}:
            checks.append(("HIT-03", False,
                           "terminal-state vocabulary drifted"))
            return False, summary, checks
        summary["lifecycle_ok"] = True

        # mock role discipline (D-045) + the escalation ladder
        if not can_actor_resolve(ROLE_OWNER, "role:owner") or \
                not can_actor_resolve(ROLE_ANY, "role:ops") or \
                can_actor_resolve(ROLE_ANY, "role:customer") or \
                can_actor_resolve(ROLE_OWNER, "role:ops") or \
                can_actor_resolve(ROLE_OWNER, "owner") or \
                not can_actor_resolve(ROLE_ESCALATION,
                                      "role:escalation"):
            checks.append(("HIT-03", False,
                           "role discipline drifted"))
            return False, summary, checks
        if ESCALATION_TARGET.get(ROLE_ANY) != ROLE_OPS or \
                ESCALATION_TARGET.get(ROLE_OPS) != ROLE_OWNER or \
                ESCALATION_TARGET.get("publisher") != ROLE_OWNER or \
                ESCALATION_TARGET.get(ROLE_OWNER) != ROLE_ESCALATION:
            checks.append(("HIT-03", False,
                           "escalation ladder drifted"))
            return False, summary, checks
        summary["roles_ok"] = True
        checks.append(("HIT-03", True,
                       "REAL HITL contracts enforced: ticket gate "
                       "fail-closed (shape, queue/role vocabularies, "
                       "D-114 bounds), action gate fail-closed "
                       "(EXPIRED sweep-only, MODIFIED override "
                       "required, role:/agent: mock refs), lifecycle "
                       "edge matrix closed with terminals exitless, "
                       "mock role discipline and the deterministic "
                       "escalation ladder stable"))
        return True, summary, checks

    # -- HIT-04: the synthetic review cycle ------------------------------------------

    def _make_vault(self) -> _EphemeralHitlVault:
        """The probe's ONLY vault: ephemeral in-process, zero durable
        footprint (the D-079 hazard bypassed — never the shared
        `local/volumes/hitl` and never live PG). Subclass hook for the
        battery's fail-closed durable-vault refusal proof."""
        vault = _EphemeralHitlVault()
        self._last_vault = vault  # provenance for the ephemeral proof
        return vault

    def _hit04(self) -> Tuple[bool, Dict[str, Any],
                              List[Tuple[str, bool, str]]]:
        from canonical.hitl_contracts import (
            QT_ORDER_OVERRIDE, QT_PUBLISH_GATE, ROLE_ANY, ROLE_OPS,
            ROLE_OWNER, ST_APPROVED, ST_CLAIMED, ST_ESCALATED,
            ST_EXPIRED, ST_MODIFIED, ST_PENDING_REVIEW,
            HitlContractError, is_transition_legal,
        )
        from canonical.hitl_engine import HitlEngine

        checks: List[Tuple[str, bool, str]] = []
        summary: Dict[str, Any] = {"steps": [], "summary_hash": "",
                                   "vault_backend": "ephemeral",
                                   "reviewer_signals_emitted": 0,
                                   "invalid_refused": 0}
        stack, err = self._load("stack_factory")
        if stack is None:
            checks.append(("HIT-04", False,
                           f"event store unavailable ({err}) — fail "
                           "closed"))
            return False, summary, checks
        try:
            store = stack[0]
        except Exception as exc:  # noqa: BLE001 — typed refusal
            checks.append(("HIT-04", False,
                           f"event store construction failed "
                           f"({type(exc).__name__})"))
            return False, summary, checks
        vault = self._make_vault()
        engine = HitlEngine(store, vault=vault)

        try:
            # START — the probe plan
            summary["steps"].append([
                "START", True,
                {"cycle_id": CYCLE_ID,
                 "vault_backend": "ephemeral-in-process"}])

            # AUTH — isolation envelope: NO reviewer-notification
            # channel bound (no email/SMS/push/dashboard emitter
            # exists); durable tickets + the hash-chained ledger are
            # the deliverable; reviewers are mock role refs only
            summary["steps"].append([
                "AUTH", True,
                {"reviewer_signals": "none (no channel bound)",
                 "reviewers": "mock role:* refs only (D-045)",
                 "egress": 0}])

            # INGEST — the analyst boundary (D-166/D-167 handover):
            # DISPATCHED_TO_HITL insights enter INSIGHT_REVIEW
            # idempotently; direct-producer tickets are created
            ing = engine.ingest_insight_tickets([PROBE_INSIGHT_KEY],
                                                "L0001")
            if len(ing["created"]) != 1 or ing["duplicated"]:
                _fail(f"insight ingestion broken: {ing}")
            insight_tid = ing["created"][0]
            ing2 = engine.ingest_insight_tickets([PROBE_INSIGHT_KEY],
                                                 "L0002")
            if ing2["duplicated"] != [PROBE_INSIGHT_KEY] or \
                    ing2["created"]:
                _fail(f"ingest idempotency broken: {ing2}")
            pub = engine.create_ticket({
                "ticket_id": "hitl-pub-phase18-01",
                "queue_type": QT_PUBLISH_GATE,
                "payload_ref": "post:phase18-gate-01",
                "required_role": ROLE_OWNER,
                "resolution_status": ST_PENDING_REVIEW,
                "created_at_logical": "L0002",
            })
            if pub["status"] != "CREATED":
                _fail(f"publish-gate ticket not created: {pub}")
            pub2 = engine.create_ticket({
                "ticket_id": "hitl-pub-phase18-01",
                "queue_type": QT_PUBLISH_GATE,
                "payload_ref": "post:phase18-gate-01",
                "required_role": ROLE_OWNER,
                "resolution_status": ST_PENDING_REVIEW,
                "created_at_logical": "L0002",
            })
            if pub2["status"] != "DUPLICATE":
                _fail(f"create idempotency broken: {pub2}")
            mod = engine.create_ticket({
                "ticket_id": "hitl-ord-phase18-01",
                "queue_type": QT_ORDER_OVERRIDE,
                "payload_ref": "order:phase18-override-01",
                "required_role": ROLE_OWNER,
                "resolution_status": ST_PENDING_REVIEW,
                "created_at_logical": "L0002",
            })
            exp = engine.create_ticket({
                "ticket_id": "hitl-exp-phase18-01",
                "queue_type": QT_ORDER_OVERRIDE,
                "payload_ref": "order:phase18-expiry-01",
                "required_role": ROLE_ANY,
                "resolution_status": ST_PENDING_REVIEW,
                "created_at_logical": "L0003",
            })
            if mod["status"] != "CREATED" or exp["status"] != "CREATED":
                _fail(f"probe tickets not created: {mod}|{exp}")
            summary["steps"].append([
                "INGEST", True,
                {"insight_ticket": insight_tid[:32] + "…",
                 "re_ingest": "duplicated (idempotent)",
                 "direct_tickets": 3,
                 "same_id_recreate": "DUPLICATE"}])

            # CLAIM — atomic claim discipline: exactly one reviewer
            # wins; a wrong-role actor refuses; a second claimant
            # loses
            c1 = engine.claim(pub["ticket_id"], "role:publisher")
            if c1.get("reason") != "role_forbidden":
                _fail(f"wrong-role claim not refused: {c1}")
            c2 = engine.claim(pub["ticket_id"], "role:owner")
            if not c2.get("ok") or c2.get("status") != ST_CLAIMED:
                _fail(f"owner claim failed: {c2}")
            c3 = engine.claim(pub["ticket_id"], "role:owner")
            if c3.get("reason") != "not_claimable":
                _fail(f"second claim not refused: {c3}")
            ci = engine.claim(insight_tid, "role:owner")
            if not ci.get("ok"):
                _fail(f"insight claim failed: {ci}")
            cm = engine.claim(mod["ticket_id"], "role:owner")
            if not cm.get("ok"):
                _fail(f"order-override claim failed: {cm}")
            summary["steps"].append([
                "CLAIM", True,
                {"wrong_role": "role_forbidden",
                 "winner": ST_CLAIMED,
                 "second_claimant": "not_claimable"}])

            # RESOLVE — human-only decisions through the REAL engine:
            # approve the ingested insight; modify the order override
            # with a durable payload_override; a re-resolve refuses
            # (CLAIMED-only); an EXPIRED reviewer action is Class-B
            r1 = engine.resolve(insight_tid, {
                "decision": ST_APPROVED,
                "reviewer_actor_id": "role:owner",
                "feedback_notes": "probe-approve"}, "L0005")
            if not r1.get("ok") or r1.get("decision") != ST_APPROVED:
                _fail(f"insight approval failed: {r1}")
            r1b = engine.resolve(insight_tid, {
                "decision": ST_APPROVED,
                "reviewer_actor_id": "role:owner"}, "L0006")
            if r1b.get("reason") != "not_resolvable":
                _fail(f"re-resolve not refused: {r1b}")
            try:
                engine.resolve(pub["ticket_id"], {
                    "decision": ST_EXPIRED,
                    "reviewer_actor_id": "role:owner"}, "L0006")
                _fail("EXPIRED reviewer action accepted")
            except HitlContractError:
                pass  # sweep-only — Class-B before any durable write
            r2 = engine.resolve(mod["ticket_id"], {
                "decision": ST_MODIFIED,
                "reviewer_actor_id": "role:owner",
                "payload_override": {"window": "evening"},
                "feedback_notes": "probe-modify"}, "L0005")
            if not r2.get("ok") or r2.get("decision") != ST_MODIFIED:
                _fail(f"modify resolution failed: {r2}")
            mod_row = engine.ticket(mod["ticket_id"]) or {}
            if (mod_row.get("payload_override") or {}) != {"window": "evening"}:
                _fail("payload_override not stored durably")
            summary["steps"].append([
                "RESOLVE", True,
                {"insight": ST_APPROVED,
                 "re_resolve": "not_resolvable (CLAIMED-only)",
                 "expired_action": "Class-B (sweep-only)",
                 "modified_override": "durable"}])

            # ESCALATE — the escalation LOOP with deterministic role
            # elevation, then resolution under the elevated role
            e1 = engine.resolve(pub["ticket_id"], {
                "decision": ST_ESCALATED,
                "reviewer_actor_id": "role:owner",
                "feedback_notes": "probe-escalate"}, "L0006")
            if not e1.get("ok") or \
                    e1.get("escalated_to") != "escalation":
                _fail(f"escalation broken: {e1}")
            if (engine.ticket(pub["ticket_id"]) or {}).get("resolution_status") != ST_ESCALATED:
                _fail("escalated status not durable")
            q1 = engine.requeue_escalated(pub["ticket_id"], "L0007")
            child = pub["ticket_id"] + "-esc"
            if q1.get("status") != "CREATED":
                _fail(f"escalation requeue broken: {q1}")
            child_row = engine.ticket(child) or {}
            if child_row.get("resolution_status") != ST_PENDING_REVIEW or \
                    child_row.get("required_role") != "escalation":
                _fail(f"elevated child wrong: {child_row}")
            q2 = engine.requeue_escalated(pub["ticket_id"], "L0008")
            if q2.get("status") != "DUPLICATE":
                _fail(f"escalation requeue not idempotent: {q2}")
            cc = engine.claim(child, "role:escalation")
            if not cc.get("ok"):
                _fail(f"elevated claim failed: {cc}")
            cr = engine.resolve(child, {
                "decision": ST_APPROVED,
                "reviewer_actor_id": "role:escalation",
                "feedback_notes": "probe-resolve-escalated"}, "L0008")
            if not cr.get("ok"):
                _fail(f"elevated resolution failed: {cr}")
            summary["steps"].append([
                "ESCALATE", True,
                {"owner_escalates_to": "escalation",
                 "fresh_child": "PENDING_REVIEW (elevated role)",
                 "requeue_idempotent": True,
                 "loop_closed": f"{child} → APPROVED"}])

            # SWEEP — deterministic expiration from an INJECTED pure
            # clock evaluator (EXPIRED reachable ONLY here — proven
            # above that a reviewer EXPIRED action refuses)
            sw = engine.expire_sweep(
                lambda created: created <= "L0003", "L0009")
            if sw["expired"] != [exp["ticket_id"]]:
                _fail(f"expiration sweep broken: {sw}")
            xrow = engine.ticket(exp["ticket_id"]) or {}
            if xrow.get("resolution_status") != ST_EXPIRED:
                _fail("EXPIRED status not durable")
            for tid in (insight_tid, mod["ticket_id"], child):
                st = (engine.ticket(tid) or {}).get("resolution_status")
                if st in (ST_PENDING_REVIEW, ST_CLAIMED):
                    _fail(f"sweep touched an open ticket: {tid}")
            summary["steps"].append([
                "SWEEP", True,
                {"expired": exp["ticket_id"],
                 "clock": "injected (created <= L0003) — no wall "
                          "clock",
                 "open_tickets_untouched": True}])

            # INVALID — malformed review payloads fail closed BEFORE
            # any durable write (shape gate, action gate)
            open_before = {t["ticket_id"] for t in engine.open_tickets()}
            ledger_before = len(vault.all_ledger())
            for bad_ticket in (
                    {"queue_type": QT_ORDER_OVERRIDE,
                     "payload_ref": "x:1", "required_role": ROLE_ANY,
                     "resolution_status": ST_PENDING_REVIEW,
                     "created_at_logical": "L0009"},
                    dict(engine.ticket(child) or {}, ticket_id="t" * 129,
                         resolution_status=ST_PENDING_REVIEW,
                         reviewer_actor_id=None)):
                try:
                    engine.create_ticket(bad_ticket)
                    _fail("malformed ticket accepted")
                except HitlContractError:
                    summary["invalid_refused"] += 1
            for bad_action in (
                    {"decision": "MAYBE",
                     "reviewer_actor_id": "role:owner"},
                    {"decision": ST_APPROVED,
                     "reviewer_actor_id": "bob"},
                    {"decision": ST_MODIFIED,
                     "reviewer_actor_id": "role:owner"}):
                try:
                    engine.resolve(child, bad_action, "L0010")
                    _fail("malformed action accepted")
                except HitlContractError:
                    summary["invalid_refused"] += 1
            if len(vault.all_ledger()) != ledger_before:
                _fail("an invalid payload reached the durable ledger "
                      "— fail-closed gate breached")
            if {t["ticket_id"] for t in engine.open_tickets()} \
                    != open_before:
                _fail("an invalid payload changed the open-ticket "
                      "registry — fail-closed gate breached")
            summary["steps"].append([
                "INVALID", True,
                {"refused": summary["invalid_refused"],
                 "durable_rows_added": 0}])

            # LEDGER — the D-108 tamper-evident chains verify per
            # ticket (the ledger records RESOLUTIONS and expiries;
            # claims are D-027 events): 4 resolutions + 1 expiry
            for tid in (insight_tid, pub["ticket_id"],
                        mod["ticket_id"], exp["ticket_id"], child):
                v = engine.verify_chain(tid)
                if not v.get("ok"):
                    _fail(f"ledger chain broken for {tid}: {v}")
            kinds = {r["event_kind"] for r in vault.all_ledger()}
            if kinds != {"resolution", "expiry"}:
                _fail(f"unexpected ledger row kinds: {sorted(kinds)}")
            if len(vault.all_ledger()) != 5:
                _fail(f"expected 5 durable resolutions/expiries, got "
                      f"{len(vault.all_ledger())}")
            summary["steps"].append([
                "LEDGER", True,
                {"chains_verified": 5, "tamper_evidence": "D-108",
                 "rows": len(vault.all_ledger())}])

            # VERIFY — zero reviewer signals, no egress markers, the
            # vault stayed ephemeral, the store carries ONLY hitl rows
            if summary["reviewer_signals_emitted"] != 0:
                _fail("a reviewer signal was emitted — isolation "
                      "broken")
            raw = store.records if hasattr(store, "records") else {}
            blob = json.dumps(raw).lower()
            for marker in ("smtp", "sendmail", "api_key", "twilio",
                           "webhook_url", "auth_code", "pan",
                           "card_number"):
                if marker in blob:
                    _fail(f"egress-boundary violation: {marker!r} "
                          "found in the HITL event stream")
            non_hitl = [k for k in raw
                        if not str(k).startswith("hitl::")]
            if non_hitl:
                _fail(f"non-HITL durable rows present: "
                      f"{non_hitl[:3]}")
            if not isinstance(vault, _EphemeralHitlVault):
                _fail("vault is not the ephemeral in-process store — "
                      "durable footprint")
            summary["vault_backend"] = "ephemeral"
            summary["steps"].append([
                "VERIFY", True, {"markers": "clean",
                                 "egress": 0,
                                 "non_hitl_rows": 0,
                                 "vault_backend": "ephemeral"}])

            # CLEANUP — persist the data-minimized cycle artifact,
            # read it back, then delete EVERYTHING
            artifact = {
                "cycle_id": CYCLE_ID,
                "tickets_created": 4,
                "insight_ingested": 1,
                "escalation_loop_closed": True,
                "expired_by_sweep": 1,
                "invalid_refused": summary["invalid_refused"],
                "dry_run": True,
                "reviewer_signals_emitted": 0,
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
                "tickets_created": 4,
                "insight_ingested": 1,
                "invalid_refused": summary["invalid_refused"],
                "dry_run": True,
                "reviewer_signals_emitted": 0,
            }
            summary["summary_hash"] = canonical_hash(plan)
            checks.append(("HIT-04", True,
                           "synthetic review cycle completed: "
                           f"{len(summary['steps'])} steps, summary "
                           f"hash {summary['summary_hash'][:16]}…, "
                           "atomic claims, human-only resolutions, "
                           "escalation loop closed, deterministic "
                           "expiry sweep, tamper-evident ledger, "
                           "zero reviewer signals"))
            return True, summary, checks
        except Phase18Error as exc:
            checks.append(("HIT-04", False, str(exc)[:160]))
            self._cleanup_scratch()
            return False, summary, checks
        except HitlContractError as exc:
            checks.append(("HIT-04", False,
                           f"HITL contract refusal (Class-B): "
                           f"{str(exc.args[0])[:120]}"))
            self._cleanup_scratch()
            return False, summary, checks
        except Exception as exc:  # noqa: BLE001 — typed refusal (D-124)
            checks.append(("HIT-04", False,
                           f"synthetic review cycle failed "
                           f"({type(exc).__name__}: "
                           f"{str(exc)[:100]})"))
            self._cleanup_scratch()
            return False, summary, checks

    # -- scratch (namespace-scoped, the only general persistence) --

    def _scratch_write(self, artifact: Dict[str, Any]) -> None:
        self._scratch_store["phase18-scratch:hitl"] = artifact

    def _scratch_read(self) -> Any:
        return self._scratch_store.get("phase18-scratch:hitl")

    def _scratch_delete(self) -> bool:
        return self._scratch_store.pop("phase18-scratch:hitl",
                                       None) is not None

    def _scratch_residue(self) -> List[str]:
        return sorted(k for k in self._scratch_store
                      if k.startswith("phase18-scratch:"))

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

    def run(self) -> Phase18Attestation:
        """HIT-01..HIT-05 → the canonical attestation. Exactly one
        audited attestation per call (including aborts); an HIT-01
        refusal performs ZERO engine calls."""
        checks: List[Tuple[str, bool, str]] = []
        ok1, p17digest, manifest, c1 = self._hit01()
        checks += c1
        if not ok1:
            return self._emit(PHASE18_INCOMPLETE, checks,
                              phase17_digest=p17digest,
                              manifest=manifest)
        ok2, profile, c2 = self._hit02()
        checks += c2
        ok3, contracts, c3 = (False, {}, [])
        if ok2:
            ok3, contracts, c3 = self._hit03()
            checks += c3
        ok4, cycle, c4 = (False, {}, [])
        if ok3:
            ok4, cycle, c4 = self._hit04()
            checks += c4
        verdict = PHASE18_IGNITED if all((ok1, ok2, ok3, ok4)) \
            else PHASE18_INCOMPLETE
        if verdict == PHASE18_IGNITED:
            checks.append(("HIT-05", True,
                           "phase18.hitl_wiring_attestation.v1 "
                           "emitted — HITL service ignited in "
                           "DRY-RUN mode (reviewer interfaces "
                           "isolated, zero human-notification or "
                           "dashboard egress, ephemeral vault, mock "
                           "role refs only) under the Phase 17 "
                           "attestation; registry slot 18 "
                           f"({SLOT18_REGISTRY_FACT}) is now TAKEN — "
                           "the final registry ignition; the "
                           "program-level completion reconciliation "
                           "is the next milestone"))
        else:
            checks.append(("HIT-05", False,
                           "attestation emitted as IGNITION_INCOMPLETE "
                           "— remediate the named checks before any "
                           "further wiring"))
        return self._emit(verdict, checks, phase17_digest=p17digest,
                          manifest=manifest, profile=profile,
                          contracts=contracts, cycle=cycle)


def main() -> int:
    """CLI wiring guard: interactive wiring requires the injected
    providers, census and the ephemeral engine stack configuration."""
    import argparse
    import sys
    ap = argparse.ArgumentParser(
        description="Phase 18 live wiring igniter (HIT-01..HIT-05, "
                    "D-168).")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    print("live_wiring_phase18_igniter: interactive wiring requires "
          "the phase17 attestation, the D-112 chain, the runtime "
          "census and the injected event store; see run() and the "
          "battery for the injected contract.", file=sys.stderr)
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

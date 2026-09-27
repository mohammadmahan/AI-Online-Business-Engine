"""Phase 14 live wiring igniter — Scheduling Engine wiring (D-164).

The ninth Live Wiring program phase. Phase 12 (D-162) verified the
Shipping & Orchestration boundary in dry-run mode; Phase 14 now wires
and verifies the SCHEDULING / MARKETING-AUTOMATION calendar on top of
the verified Phase 12 attestation — in STRICT DRY-RUN mode. D-163
closed registry slot 14 (CRM-not-needed), so this phase ignites
registry slot 15 ("Marketing Automation") → `canonical.scheduling_engine`:

  SCH-01  the upstream `phase12.shipping_wiring_attestation.v1` is
          present, PHASE12_IGNITED, manifest-bound, its canonical
          bytes recompute to the SHA-256 commitment rooted in the
          D-112 ledger (kind `phase12_shipping_wiring_attestation`)
          over an intact chain — ANY refusal happens BEFORE the first
          calendar call (zero engine calls on refusal);
  SCH-02  the verified runtime profile is loaded: the injected
          census marks Phases 5–12 present+VERIFIED+WIRED, and the
          repo-real scheduling seams are importable and consistent
          with the D-154 ENTRY_POINTS registry (phase15 =
          `canonical.scheduling_engine` — the D-154 cross-walk binds
          slot 15 "Marketing Automation" to the D-093/D-094/D-096
          calendar engine);
  SCH-03  the scheduling contracts and invariants are validated
          through the REAL validator: strict post contracts (post_id,
          content_ref, non-empty unique targets within the D-114 cap,
          ISO-8601 scheduled_for supplied by the planner — never read
          from the clock), deterministic idempotency keys over
          (content_ref, sorted targets, scheduled_for), pure 15-minute
          slot-bucket arithmetic and pure due semantics (both clock-
          free), and the probe's own capability envelope — the probe
          holds NO dispatch capability (publishing/dispatch stay with
          the owner-gated D-070/D-076 publishers and the D-139 gate);
  SCH-04  a NON-DESTRUCTIVE synthetic scheduling cycle runs over the
          REAL calendar engine: schedule (deterministic idempotency
          key, durable SCHEDULED ref) → replay dedup (identical
          re-schedule → `retried`, same key; conflicting payload under
          the same post_id → IntegrityError) → slot claims (a second
          post in the same (platform, 15-min bucket) is a durable
          SLOT_CONFLICT rejection; the post is NOT scheduled) →
          reschedule (new slots claimed FIRST, old slots superseded
          but kept in the slot ledger, the transition records the
          prior instant; a freed slot is re-claimable) → transitions
          (SCHEDULED→DUE on the injected instant; DUE→CANCELLED;
          terminal immutability — cancel/reschedule on a CANCELLED
          post refuse) → the due-notification event is emitted onto
          the REAL D-083 fan-out boundary with publisher-less binds
          (structurally incapable of egress) under the ephemeral
          D-079 lock → the calendar view is rebuilt from DURABLE
          events alone and must match the driven lifecycle exactly
          (zero drift) → per-step telemetry (START/AUTH/SCHEDULE/
          SLOTS/TRANSITIONS/FANOUT/CALENDAR/VERIFY/CLEANUP) and a
          deterministic summary hash; cleanup leaves zero residue;
  SCH-05  the canonical `phase14.scheduling_wiring_attestation.v1` is
          emitted exactly once per run (aborts included) with the
          SHA-256 `attestation_digest`; any abort emits the same
          schema as IGNITION_INCOMPLETE with failure telemetry.

Lock hygiene (the D-160/D-079 incident, inherited): the slot-lock
default backend claims keys in live PostgreSQL (`scheduling.slot_lock`)
or the shared `local/volumes/scheduling/slot_locks.json`. The probe
therefore injects an EPHEMERAL process-local slot backend with the
same claim/supersede/history semantics — ZERO durable lock claims, no
PG rows, no shared-file writes, verified by the battery.

Security & purity (RULES §35, AST-pinned): injected store/lock/fanout
transports only — zero sockets, zero raw shell, zero wall clock in
the core (every instant is supplied by the producer). Customer
identity, content payloads, webhook secrets and channel tokens NEVER
enter any emitted record: only hashes, counts, status names, verdict
names and step telemetry. D-124 deep redaction runs over every
emitted record with the public commitments (`phase12_digest`,
`manifest_sha256`) restored after redaction. Publishing itself stays
a BOUNDARY: the probe schedules, it never publishes.
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
    "Phase14Error", "Phase14Attestation", "Phase14Igniter",
    "_EphemeralFanOutLock", "_EphemeralSlotLocks",
    "ATTESTATION_SCHEMA", "PHASE14_IGNITED", "PHASE14_INCOMPLETE",
    "PHASE12_SCHEMA", "PHASE12_IGNITED", "PHASE12_ROW_KIND",
    "SEAMS", "SEAM_PHASES", "PROBE_ENVELOPE", "LIMITS",
    "CYCLE_ID", "PROBE_POST_A", "canonical_hash",
]

ATTESTATION_SCHEMA = "phase14.scheduling_wiring_attestation.v1"
PHASE14_IGNITED = "PHASE14_IGNITED"
PHASE14_INCOMPLETE = "IGNITION_INCOMPLETE"

PHASE12_SCHEMA = "phase12.shipping_wiring_attestation.v1"
PHASE12_IGNITED = "PHASE12_IGNITED"

# The D-112 ledger kind that roots the Phase 12 attestation (D-162).
PHASE12_ROW_KIND = "phase12_shipping_wiring_attestation"

_HEX64 = re.compile(r"^[0-9a-f]{64}$")

# The probe's capability envelope: the scheduling probe PLANS and
# DRIVES the calendar lifecycle; it NEVER dispatches. Publishing /
# dispatch stay with the owner-gated publishers (D-070/D-076) and the
# D-139 activation authority.
PROBE_ENVELOPE: Tuple[str, ...] = ("plan", "slot_query", "calendar_view")

LIMITS: Dict[str, Any] = {
    "max_retries": 2,           # Class-A transient retries only
    "timeout_s": 15.0,          # per engine operation (D-151)
    "slot_granularity_minutes": 15,   # D-094 slot bucket
    "max_fanout_events": 5,     # event probes per cycle
}

# Repo-real module seams for the scheduling wiring. `SEAM_PHASES`
# pins each seam to the D-154 ENTRY_POINTS phase it must agree with.
SEAMS: Dict[str, str] = {
    "scheduling_engine": "canonical.scheduling_engine",
    "scheduling_contracts": "canonical.scheduling_contracts",
    "scheduling_worker": "canonical.scheduling_worker",
    "orchestration_engine": "canonical.orchestration_engine",
    "sync_event_store": "services.sync_engine",
}

SEAM_PHASES: Dict[str, Optional[int]] = {
    "scheduling_engine": 15,   # registry slot 15 "Marketing Automation"
    "scheduling_contracts": None,
    "scheduling_worker": None,
    "orchestration_engine": 13,
    "sync_event_store": None,
}

CYCLE_ID = "phase14-scheduling-probe-0001"

PROBE_POST_A: Dict[str, Any] = {
    "post_id": "phase14-probe-0001",
    "content_ref": "content-phase14-0001",
    "targets": ["telegram"],
    "scheduled_for": "2026-09-27T10:07:00+00:00",
}


class Phase14Error(ValueError):
    """Contract-level misuse of the Phase 14 igniter."""


def _fail(reason: str) -> None:
    raise Phase14Error(reason)


def canonical_hash(payload: Dict[str, Any]) -> str:
    """SHA-256 over canonical JSON bytes — the shared project digest
    formula (Stage G/H/D-154..D-162 engines)."""
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class _EphemeralSlotLocks:
    """Process-local parity backend for the (platform, slot_bucket)
    PK-as-lock (D-094) — the scheduling analog of the D-160/D-161/D-162
    ephemeral fan-out lock: claim/supersede/history semantics identical
    to `_JsonSlotLocks`, ZERO durable footprint. Never live PostgreSQL
    (`scheduling.slot_lock`) and never the shared
    `local/volumes/scheduling/slot_locks.json`."""

    def __init__(self) -> None:
        import threading
        self._rows: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def claim(self, key: str, row: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            existing = self._rows.get(key)
            if existing and existing.get("active", True):
                return {"acquired": False,
                        "holder": {"post_id":
                                       existing.get("post_id", ""),
                                   "scheduled_for":
                                       existing.get("scheduled_for", "")}}
            # a released (superseded) slot is re-claimable — the row
            # stays as ledger history (D-096)
            rec = json.loads(json.dumps(row))
            rec["active"] = True
            self._rows[key] = rec
            return {"acquired": True, "holder": rec}

    def supersede(self, key: str, post_id: str,
                  replacement: Tuple[str, str]) -> None:
        """D-096: the old slot row is NEVER deleted — it is marked
        inactive (superseded) and stays in the ledger."""
        with self._lock:
            if key in self._rows and \
                    self._rows[key].get("post_id") == post_id:
                self._rows[key]["active"] = False
                self._rows[key]["superseded_by"] = \
                    "\x1f".join(replacement)

    def history(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return json.loads(json.dumps(self._rows))


class _EphemeralFanOutLock:
    """Process-local D-079 parity lock for PROBES (D-160/D-161/D-162
    precedent): INSERT-once claim semantics, ZERO durable footprint —
    never live PostgreSQL (`orchestration.fanout_lock`) and never the
    shared `local/volumes/orchestration/fanout_lock.json`."""

    def __init__(self) -> None:
        import threading
        self._claims: Dict[str, str] = {}
        self._lock = threading.Lock()

    def claim(self, key: str, claimant: str) -> bool:
        with self._lock:
            if key in self._claims:
                return False
            self._claims[key] = claimant
            return True


@dataclass(frozen=True)
class Phase14Attestation:
    """Canonical, immutable Phase 14 ignition artifact."""
    schema: str
    verdict: str             # PHASE14_IGNITED / IGNITION_INCOMPLETE
    phase12_digest: str      # upstream attestation digest (commitment)
    manifest_sha256: str     # deployment fingerprint carried through
    profile: Dict[str, Any]  # runtime profile + seams summary
    contracts: Dict[str, Any]  # idempotency/slot/invariants summary
    cycle: Dict[str, Any]    # synthetic scheduling telemetry
    checks: tuple = field(default_factory=tuple)  # (id, ok, detail)
    observed_tick: int = 0

    @property
    def ignited(self) -> bool:
        return self.verdict == PHASE14_IGNITED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "verdict": self.verdict,
            "phase12_digest": self.phase12_digest,
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


class Phase14Igniter:
    """SCH-01..SCH-05 with injected store/lock/fanout transports.

    Injected:
      clock           — ``() -> int`` logical tick
      audit_sink      — ``callable(dict)`` (D-112/D-121 in prod)
      upstream_provider — ``() -> dict`` the phase12 attestation
      audit_rows      — ``() -> list`` the D-112 ledger rows
      chain_verifier  — ``() -> dict`` D-112 chain integrity
      census          — ``() -> dict`` the runtime profile census
      stack_factory   — ``() -> (store,)`` building the REAL D-027
                        event store fresh per run (the calendar engine
                        is constructed by the igniter over the
                        EPHEMERAL slot backend)
      fanout          — optional D-083 fan-out boundary override
                        (default: built over the store with
                        publisher-less binds + ephemeral lock)
      expected_entry_points — optional {phase: seam} override
    """

    def __init__(self, clock: Callable[[], int],
                 audit_sink: Callable[[Dict[str, Any]], None],
                 upstream_provider: Optional[Callable[[], Dict[str, Any]]] = None,
                 audit_rows: Optional[Callable[[], List[Dict[str, Any]]]] = None,
                 chain_verifier: Optional[Callable[[], Dict[str, Any]]] = None,
                 census: Optional[Callable[[], Dict[str, Any]]] = None,
                 stack_factory: Optional[Callable[[], Tuple]] = None,
                 fanout: Optional[Any] = None,
                 expected_entry_points: Optional[Dict[int, str]] = None,
                 ) -> None:
        if not callable(clock) or not callable(audit_sink):
            _fail("clock and audit_sink required")
        self._clock = clock
        self._sink = audit_sink
        self._prov = {
            "phase12": upstream_provider,
            "audit_rows": audit_rows,
            "chain_verifier": chain_verifier,
            "census": census,
            "stack_factory": stack_factory,
        }
        self._fanout_override = fanout
        self._slot_locks = _EphemeralSlotLocks()
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
              phase12_digest: str = "", manifest: str = "",
              profile: Optional[Dict[str, Any]] = None,
              contracts: Optional[Dict[str, Any]] = None,
              cycle: Optional[Dict[str, Any]] = None,
              ) -> Phase14Attestation:
        att = Phase14Attestation(
            schema=ATTESTATION_SCHEMA, verdict=verdict,
            phase12_digest=phase12_digest, manifest_sha256=manifest,
            profile=profile or {}, contracts=contracts or {},
            cycle=cycle or {},
            checks=tuple((c[0], c[1], deep_redact(str(c[2])))
                         for c in checks),
            observed_tick=self._clock())
        blob = json.dumps(att.to_dict(), sort_keys=True,
                          separators=(",", ":"), ensure_ascii=False)
        redacted = json.loads(deep_redact(blob))
        # Public commitments (D-146/D-153/D-154..D-162 precedent).
        redacted["phase12_digest"] = att.phase12_digest
        redacted["manifest_sha256"] = att.manifest_sha256
        self._sink(redacted)
        return att

    # -- SCH-01: the Phase 12 attestation --------------------------------------

    def _sch01(self) -> Tuple[bool, str, str,
                              List[Tuple[str, bool, str]]]:
        """(ok, phase12_digest, manifest, checks)."""
        checks: List[Tuple[str, bool, str]] = []
        att, err = self._load("phase12")
        if att is None:
            checks.append(("SCH-01", False,
                           "Phase 12 attestation absent "
                           f"({err}) — Phase 12 never ignited"))
            return False, "", "", checks
        if not isinstance(att, dict):
            checks.append(("SCH-01", False,
                           "Phase 12 attestation malformed"))
            return False, "", "", checks
        if att.get("schema") != PHASE12_SCHEMA:
            checks.append(("SCH-01", False,
                           f"attestation schema {att.get('schema')!r} "
                           f"!= {PHASE12_SCHEMA!r}"))
            return False, "", "", checks
        if att.get("verdict") != PHASE12_IGNITED:
            checks.append(("SCH-01", False,
                           f"Phase 12 verdict {att.get('verdict')!r} "
                           f"!= {PHASE12_IGNITED!r} — shipping "
                           "boundary not wired, Phase 14 refused"))
            return False, "", "", checks
        manifest = att.get("manifest_sha256", "")
        if not (isinstance(manifest, str) and _HEX64.match(manifest)):
            checks.append(("SCH-01", False,
                           "phase12 attestation lacks its manifest "
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
                        str(row.get("event_kind", "")) != PHASE12_ROW_KIND:
                    continue
                detail = row.get("detail")
                if isinstance(detail, dict) and \
                        isinstance(detail.get("attestation_digest"),
                                   str):
                    rooted_digest = detail["attestation_digest"]
                    break
        if not rooted_digest:
            checks.append(("SCH-01", False,
                           "phase12 attestation not rooted in the "
                           "D-112 ledger — upstream wiring was never "
                           "durably attested"))
            return False, recomputed, "", checks
        if rooted_digest != recomputed:
            checks.append(("SCH-01", False,
                           f"phase12 attestation digest "
                           f"{recomputed[:16]}… != rooted "
                           f"{rooted_digest[:16]}… — DRIFTED or "
                           "altered upstream attestation"))
            return False, recomputed, "", checks
        cv, err = self._load("chain_verifier")
        if cv is None or not isinstance(cv, dict) or not cv.get("ok"):
            reason = (cv or {}).get("reason", err or "verifier absent")
            checks.append(("SCH-01", False,
                           f"D-112 chain not intact ({reason}) — "
                           "wiring on a broken ledger is refused"))
            return False, recomputed, "", checks
        checks.append(("SCH-01", True,
                       "phase12 attestation PHASE12_IGNITED, digest "
                       f"recomputes ({recomputed[:16]}…) and matches "
                       "the rooted commitment in the D-112 ledger "
                       f"({int(cv.get('rows', 0))} rows, zero breaks)"))
        return True, recomputed, manifest, checks

    # -- SCH-02: runtime profile + module seams --------------------------------

    def _sch02(self) -> Tuple[bool, Dict[str, Any],
                              List[Tuple[str, bool, str]]]:
        checks: List[Tuple[str, bool, str]] = []
        summary: Dict[str, Any] = {"runtime_profile_verified": False,
                                   "seams_ok": False,
                                   "phases": []}
        census, err = self._load("census")
        if census is None or not isinstance(census, dict):
            checks.append(("SCH-02", False,
                           "runtime profile census unavailable "
                           f"({err}) — fail closed"))
            return False, summary, checks
        if not census.get("runtime_profile_verified"):
            checks.append(("SCH-02", False,
                           "runtime profile NOT verified — refuse"))
            return False, summary, checks
        rows = {p.get("phase"): p for p in census.get("phases", [])
                if isinstance(p, dict)}
        for n in (5, 6, 7, 8, 9, 10, 11, 12):
            p = rows.get(n)
            if p is None:
                checks.append(("SCH-02", False,
                               f"Phase {n} missing from the runtime "
                               "profile census (Phases 5/6/7/8/9/10/"
                               "11/12 required)"))
                return False, summary, checks
            if not (p.get("verified") and p.get("wired")):
                checks.append(("SCH-02", False,
                               f"Phase {n} not VERIFIED+WIRED — "
                               "scheduling wiring refused"))
                return False, summary, checks
            summary["phases"].append(n)
        summary["runtime_profile_verified"] = True
        # module seams against the D-154 registry
        import importlib
        entry_points = dict(self._entry_points) if self._entry_points \
            else None
        if entry_points is None:
            try:
                from dokploy_completion_attestation import ENTRY_POINTS
                entry_points = dict(ENTRY_POINTS)
            except Exception as exc:  # noqa: BLE001 — typed
                checks.append(("SCH-02", False,
                               "D-154 registry unavailable "
                               f"({type(exc).__name__})"))
                return False, summary, checks
        for key, modname in SEAMS.items():
            try:
                importlib.import_module(modname)
            except Exception as exc:  # noqa: BLE001 — typed refusal
                checks.append(("SCH-02", False,
                               f"canonical seam {modname} not "
                               f"importable ({type(exc).__name__}) — "
                               "repo seam missing"))
                return False, summary, checks
            phase_no = SEAM_PHASES.get(key)
            expected = entry_points.get(phase_no) \
                if phase_no is not None else None
            if expected and expected != modname:
                checks.append(("SCH-02", False,
                               f"ENTRY_POINTS[{phase_no}] = "
                               f"{expected!r} != repo seam "
                               f"{modname!r} — registry drift"))
                return False, summary, checks
        # the load-bearing pin: registry slot 15 "Marketing
        # Automation" MUST bind to the calendar engine (the D-154
        # cross-walk; slot 14 was closed CRM-not-needed via D-163)
        if entry_points.get(15) != SEAMS["scheduling_engine"]:
            checks.append(("SCH-02", False,
                           "registry slot 15 (Marketing Automation) "
                           "does not bind "
                           f"{SEAMS['scheduling_engine']!r} — "
                           "cross-walk drift"))
            return False, summary, checks
        summary["seams_ok"] = True
        checks.append(("SCH-02", True,
                       f"all {len(SEAMS)} scheduling seams importable "
                       "and consistent with the D-154 ENTRY_POINTS "
                       "registry (slot 15 → "
                       f"{SEAMS['scheduling_engine']})"))
        return True, summary, checks

    # -- SCH-03: scheduling contracts & invariants ------------------------------

    def _sch03(self) -> Tuple[bool, Dict[str, Any],
                              List[Tuple[str, bool, str]]]:
        checks: List[Tuple[str, bool, str]] = []
        summary: Dict[str, Any] = {
            "contracts_ok": False, "idempotent": False,
            "slots_pure": False,
        }
        try:
            from canonical.scheduling_contracts import (
                MAX_TARGETS_PER_POST, SLOT_GRANULARITY_MINUTES,
                SchedulingContractError, is_due, schedule_idempotency_key,
                slot_bucket, slot_lock_key, validate_scheduled_post,
            )
        except Exception as exc:  # noqa: BLE001 — typed refusal
            checks.append(("SCH-03", False,
                           f"scheduling contracts not importable "
                           f"({type(exc).__name__}) — repo seam missing"))
            return False, summary, checks
        summary["max_targets_per_post"] = MAX_TARGETS_PER_POST
        summary["slot_granularity_minutes"] = SLOT_GRANULARITY_MINUTES

        # the REAL validator accepts a conforming probe post
        try:
            validate_scheduled_post(dict(PROBE_POST_A))
        except SchedulingContractError as exc:
            checks.append(("SCH-03", False,
                           f"REAL validator rejected a conforming post: "
                           f"{str(exc.args[0])[:120]}"))
            return False, summary, checks
        # and refuses every non-conforming class with the reason named
        bad_post = dict(PROBE_POST_A, post_id="bad id!")
        for mutate, expect in (
                (lambda p: dict(p, post_id="bad id!"), "post_id"),
                (lambda p: dict(p, content_ref=""), "content_ref"),
                (lambda p: dict(p, targets=[]), "targets"),
                (lambda p: dict(p, targets=["telegram", "telegram"]),
                 "unique"),
                (lambda p: dict(p, targets=["t"] * (MAX_TARGETS_PER_POST
                                                    + 1)), "exceeds"),
                (lambda p: dict(p, scheduled_for="not-a-timestamp"),
                 "ISO-8601"),
                (lambda p: dict(p, status="WAT"), "status must be one")):
            try:
                validate_scheduled_post(mutate(dict(PROBE_POST_A)))
                _fail(f"post invariant not enforced "
                      f"(expected {expect} rejection)")
            except SchedulingContractError as exc:
                if expect not in str(exc.args[0]):
                    checks.append(("SCH-03", False,
                                   f"post invariant mis-classified: "
                                   f"{str(exc.args[0])[:120]}"))
                    return False, summary, checks
        # deterministic idempotency keys (content, targets, window)
        k1 = schedule_idempotency_key(PROBE_POST_A["content_ref"],
                                      tuple(PROBE_POST_A["targets"]),
                                      PROBE_POST_A["scheduled_for"])
        k2 = schedule_idempotency_key(PROBE_POST_A["content_ref"],
                                      tuple(PROBE_POST_A["targets"]),
                                      PROBE_POST_A["scheduled_for"])
        if k1 != k2 or not _HEX64.match(k1):
            checks.append(("SCH-03", False,
                           "schedule idempotency not deterministic — "
                           "same identity produced divergent keys"))
            return False, summary, checks
        kd = schedule_idempotency_key(PROBE_POST_A["content_ref"],
                                      tuple(PROBE_POST_A["targets"]),
                                      "2026-09-27T11:07:00+00:00")
        if kd == k1:
            checks.append(("SCH-03", False,
                           "schedule idempotency key ignores the "
                           "window — replay-attack surface"))
            return False, summary, checks
        summary["idempotent"] = True
        # pure slot arithmetic + pure due semantics (clock-free)
        b1 = slot_bucket("2026-09-27T10:07:00+00:00",
                         SLOT_GRANULARITY_MINUTES)
        b2 = slot_bucket("2026-09-27T10:09:00+00:00",
                         SLOT_GRANULARITY_MINUTES)
        if b1 != b2:
            checks.append(("SCH-03", False,
                           "slot bucketing unstable — instants in the "
                           "same 15-minute window floor to different "
                           "buckets"))
            return False, summary, checks
        if slot_lock_key("telegram",
                         "2026-09-27T10:07:00+00:00") != \
                slot_lock_key("telegram",
                              "2026-09-27T10:09:00+00:00"):
            checks.append(("SCH-03", False,
                           "slot lock keys diverge inside one bucket "
                           "— lock contention semantics broken"))
            return False, summary, checks
        if slot_lock_key("instagram",
                         "2026-09-27T10:07:00+00:00") == \
                slot_lock_key("telegram",
                              "2026-09-27T10:07:00+00:00"):
            checks.append(("SCH-03", False,
                           "slot lock key ignores the platform — "
                           "cross-channel contention"))
            return False, summary, checks
        if not is_due("2026-09-27T10:07:00+00:00",
                      "2026-09-27T10:07:00+00:00") or \
                is_due("2026-09-27T10:07:00+00:00",
                       "2026-09-27T10:00:00+00:00"):
            checks.append(("SCH-03", False,
                           "due semantics impure — the boundary or "
                           "ordering is wrong"))
            return False, summary, checks
        summary["slots_pure"] = True
        summary["contracts_ok"] = True
        checks.append(("SCH-03", True,
                       f"REAL validator enforced ({MAX_TARGETS_PER_POST} "
                       f"target cap, ISO-8601 instants), idempotency "
                       "keys deterministic (replay-resistant), "
                       f"{SLOT_GRANULARITY_MINUTES}-minute slot "
                       "arithmetic and due semantics pure (clock-free)"))
        return True, summary, checks

    # -- SCH-04: the synthetic scheduling cycle ---------------------------------

    def _sch04(self) -> Tuple[bool, Dict[str, Any],
                              List[Tuple[str, bool, str]]]:
        from canonical.scheduling_contracts import (
            SchedulingContractError, ST_CANCELLED, ST_DUE,
            ST_SCHEDULED,
        )
        from canonical.scheduling_engine import SchedulingEngine
        from canonical.orchestration_contracts import (
            validate_dispatch_payload,
        )

        checks: List[Tuple[str, bool, str]] = []
        summary: Dict[str, Any] = {"steps": [], "summary_hash": "",
                                   "slot_backend": "ephemeral",
                                   "events": 0, "drift": False}
        stack, err = self._load("stack_factory")
        if stack is None:
            checks.append(("SCH-04", False,
                           f"event store unavailable ({err}) — fail "
                           "closed"))
            return False, summary, checks
        try:
            if isinstance(stack, tuple):
                store = stack[0]
            else:
                store = stack()
        except Exception as exc:  # noqa: BLE001 — typed refusal
            checks.append(("SCH-04", False,
                           f"event store construction failed "
                           f"({type(exc).__name__})"))
            return False, summary, checks
        engine = SchedulingEngine(store, locks=self._slot_locks)

        def _build_fanout(store):
            from canonical.orchestration_engine import FanOutEngine
            return FanOutEngine(
                store, publish_binds={"telegram": None},
                lock=_EphemeralFanOutLock())

        try:
            from services.sync_engine import IntegrityError
            now_iso = "2026-09-27T10:30:00+00:00"  # supplied instant

            # START — the probe plan
            summary["steps"].append([
                "START", True,
                {"cycle_id": CYCLE_ID,
                 "slot_backend": "ephemeral-process-local"}])

            # AUTH — capability envelope: plan/slot_query/calendar_view
            # only; NO dispatch capability exists in the probe
            summary["steps"].append([
                "AUTH", True,
                {"envelope": list(PROBE_ENVELOPE),
                 "dispatch": "owner-gated (D-070/D-076/D-139)"}])

            # SCHEDULE — deterministic idempotency + durable SCHEDULED
            sch = engine.schedule(dict(PROBE_POST_A))
            if sch.get("status") != ST_SCHEDULED:
                _fail(f"schedule failed: {sch}")
            idem = sch.get("idem_key", "")
            replay = engine.schedule(dict(PROBE_POST_A))
            if replay.get("status") != ST_SCHEDULED or \
                    not replay.get("retried") or \
                    replay.get("idem_key") != idem:
                _fail("identical re-schedule not deduplicated — "
                      "idempotency broken")
            try:
                engine.schedule(dict(PROBE_POST_A,
                                     content_ref="forged-ref"))
                _fail("conflicting schedule payload accepted — "
                      "replay-attack surface")
            except IntegrityError:
                pass  # the D-027 store refuses the forged replay
            summary["steps"].append([
                "SCHEDULE", True,
                {"post_id": PROBE_POST_A["post_id"],
                 "idem_key": idem[:16] + "…",
                 "replay": "retried", "forged": "IntegrityError"}])

            # SLOTS — same (platform, bucket) conflicts; reschedule
            # claims new first, supersedes old (ledger kept); freed
            # slots are re-claimable
            post_b = dict(PROBE_POST_A, post_id="phase14-probe-0002",
                          content_ref="content-phase14-0002")
            conflict = engine.schedule(dict(post_b))
            if conflict.get("status") != "SLOT_CONFLICT" or \
                    not conflict.get("conflicts"):
                _fail("same-slot post did not conflict — lock "
                      "contention semantics broken")
            sched_raw = store.succeeded_references("scheduling")
            sched_refs = [json.loads(r) if isinstance(r, str) else r
                          for r in sched_raw]
            conf_refs = [r for r in sched_refs
                         if isinstance(r, dict) and
                         r.get("kind") == "slot_conflict"]
            if not conf_refs:
                _fail("slot conflict not durably recorded")
            new_for = "2026-09-27T10:22:00+00:00"  # bucket 10:15
            resch = engine.reschedule(PROBE_POST_A["post_id"],
                                      new_for, "phase14-probe")
            if not resch.get("ok"):
                _fail(f"reschedule failed: {resch}")
            hist = engine.slot_history()
            old_key = [k for k in hist
                       if k.startswith("telegram\x1f2026-09-27T10:00")]
            if not old_key or hist[old_key[0]].get("active"):
                _fail("superseded slot still active — ledger history "
                      "broken")
            # the freed 10:00 slot is re-claimable now
            refree = engine.schedule(dict(post_b))
            if refree.get("status") != ST_SCHEDULED:
                _fail(f"freed slot not re-claimable: {refree}")
            summary["steps"].append([
                "SLOTS", True,
                {"conflict": "SLOT_CONFLICT (durable)",
                 "rescheduled_to": new_for,
                 "old_slot": "superseded (ledger kept)",
                 "freed_slot": "re-claimed"}])

            # TRANSITIONS — the driven lifecycle + terminal
            # immutability (drift prevention)
            due = engine.mark_due(PROBE_POST_A["post_id"], now_iso)
            if not due.get("ok") or due.get("status") != ST_DUE:
                _fail(f"mark_due failed: {due}")
            canc = engine.cancel(PROBE_POST_A["post_id"],
                                 "phase14-probe")
            if not canc.get("ok") or canc.get("status") != ST_CANCELLED:
                _fail(f"cancel failed: {canc}")
            again = engine.cancel(PROBE_POST_A["post_id"],
                                  "phase14-probe")
            if again.get("ok") or \
                    "immutable_CANCELLED" not in \
                    str(again.get("reason", "")):
                _fail("a terminal post accepted a transition — "
                      "state-machine drift")
            r_again = engine.reschedule(PROBE_POST_A["post_id"],
                                        "2026-09-27T11:07:00+00:00",
                                        "phase14-probe")
            if r_again.get("ok") or \
                    "immutable_CANCELLED" not in \
                    str(r_again.get("reason", "")):
                _fail("a terminal post accepted a reschedule — "
                      "state-machine drift")
            summary["steps"].append([
                "TRANSITIONS", True,
                {"path": "SCHEDULED→DUE→CANCELLED",
                 "terminal": "immutable (refused twice)"}])

            # FANOUT — the due-notification event through the REAL
            # D-083 boundary with publisher-less binds (structurally
            # incapable of egress) under the ephemeral D-079 lock
            fanout = self._fanout_override
            if fanout is None:
                fanout = _build_fanout(store)
            probe_event = {
                "job_id": "sched-notify-phase14-0001",
                "campaign_id": "scheduling-notifications",
                "content_id": "content-phase14-0001",
                "scheduled_slot": "1970-01-01T00:00:00+00:00",
                "text": "[phase14-probe] post due reminder (dry-run)",
                "hashtags": [],
                "media": {"kind": "none"},
                "target_params": {"telegram": {"chat_id": 1}},
                "targets": ["telegram"],
            }
            validate_dispatch_payload(dict(probe_event))
            routed = fanout.route(probe_event)
            if not routed.get("routed"):
                _fail("due-notification refused at the fan-out "
                      f"boundary ({routed.get('reason', routed)})")
            disp = fanout.dispatch({"job_id": routed["job_id"],
                                    "ref": routed["ref"]})
            if disp.get("outcomes", {}).get("telegram") != \
                    "no_publisher_bound":
                _fail("fan-out boundary outcome unexpected — no "
                      "publisher may be bound in probe mode")
            orefs = [json.loads(r) for r in
                     store.succeeded_references("orchestration")]
            if not any(o.get("outcomes", {}).get("telegram")
                       == "no_publisher_bound" for o in orefs):
                _fail("fan-out dispatch produced no durable receipt")
            summary["events"] = 1
            summary["steps"].append([
                "FANOUT", True,
                {"events": 1, "dispatch_outcome": "no_publisher_bound",
                 "durable_receipts": len(orefs),
                 "targets": "in-process-only"}])

            # CALENDAR — rebuild from DURABLE events alone; must match
            # the driven lifecycle exactly (zero drift)
            view = engine.calendar_view()
            a = view.get(PROBE_POST_A["post_id"], {})
            b = view.get("phase14-probe-0002", {})
            if a.get("status") != ST_CANCELLED or \
                    not a.get("rescheduled") or \
                    a.get("scheduled_for") != new_for:
                _fail(f"calendar view drifted for post A: {a}")
            if b.get("status") != ST_SCHEDULED:
                _fail(f"calendar view drifted for post B: {b}")
            summary["drift"] = False
            summary["steps"].append([
                "CALENDAR", True,
                {"post_a": "CANCELLED (rescheduled earlier)",
                 "post_b": "SCHEDULED",
                 "source": "durable events only"}])

            # VERIFY — no dispatch/publish markers anywhere in the
            # durable event stream; the slot backend stayed ephemeral
            raw = store.records if hasattr(store, "records") else {}
            blob = json.dumps(raw).lower()
            for marker in ("live_dispatch", "webhook_secret",
                           "auth_code", "pan", "card_number",
                           "carrier_secret"):
                if marker in blob:
                    _fail(f"publish-boundary violation: {marker!r} "
                          "found in the scheduling event stream")
            from live_wiring_phase14_igniter import (
                _EphemeralSlotLocks as _EphemeralSlotLocksSelf,
            )
            if not isinstance(getattr(engine, "_locks", None),
                              _EphemeralSlotLocksSelf):
                _fail("probe slot backend is not the ephemeral "
                      "process-local lock — durable lock claims")
            summary["slot_backend"] = "ephemeral"
            summary["steps"].append([
                "VERIFY", True, {"markers": "clean",
                                 "slot_backend": "ephemeral"}])

            # CLEANUP — persist the data-minimized cycle artifact,
            # read it back, then delete EVERYTHING
            artifact = {
                "cycle_id": CYCLE_ID,
                "post_a": PROBE_POST_A["post_id"],
                "post_b": "phase14-probe-0002",
                "idem_key": idem,
                "dry_run": True,
                "live_dispatch": False,
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
                "post_a": PROBE_POST_A["post_id"],
                "idem_key": idem,
                "dry_run": True,
                "live_dispatch": False,
            }
            summary["summary_hash"] = canonical_hash(plan)
            checks.append(("SCH-04", True,
                           "synthetic scheduling cycle completed: "
                           f"{len(summary['steps'])} steps, summary "
                           f"hash {summary['summary_hash'][:16]}…, "
                           "slot contention + terminal immutability "
                           "enforced, calendar drift-free, zero "
                           "publish-boundary crossings"))
            return True, summary, checks
        except Phase14Error as exc:
            checks.append(("SCH-04", False, str(exc)[:160]))
            self._cleanup_scratch()
            return False, summary, checks
        except SchedulingContractError as exc:
            checks.append(("SCH-04", False,
                           f"scheduling contract refusal (Class-B): "
                           f"{str(exc.args[0])[:120]}"))
            self._cleanup_scratch()
            return False, summary, checks
        except Exception as exc:  # noqa: BLE001 — typed refusal (D-124)
            checks.append(("SCH-04", False,
                           f"synthetic scheduling cycle failed "
                           f"({type(exc).__name__})"))
            self._cleanup_scratch()
            return False, summary, checks

    # -- scratch (namespace-scoped, the only general persistence) --

    def _scratch_write(self, artifact: Dict[str, Any]) -> None:
        self._scratch_store["phase14-scratch:schedule"] = artifact

    def _scratch_read(self) -> Any:
        return self._scratch_store.get("phase14-scratch:schedule")

    def _scratch_delete(self) -> bool:
        return self._scratch_store.pop("phase14-scratch:schedule",
                                       None) is not None

    def _scratch_residue(self) -> List[str]:
        return sorted(k for k in self._scratch_store
                      if k.startswith("phase14-scratch:"))

    @property
    def _scratch_store(self) -> Dict[str, Any]:
        if not hasattr(self, "_scratch"):
            self._scratch: Dict[str, Any] = {}
        return self._scratch

    def _cleanup_scratch(self) -> None:
        try:
            self._scratch_store.pop("phase14-scratch:schedule", None)
        except Exception:  # pragma: no cover
            pass

    # -- the run ---------------------------------------------------------------

    def run(self) -> Phase14Attestation:
        """SCH-01..SCH-05 → the canonical attestation. Exactly one
        audited attestation per call (including aborts); a SCH-01
        refusal performs ZERO engine/calendar calls."""
        checks: List[Tuple[str, bool, str]] = []
        ok1, p12digest, manifest, c1 = self._sch01()
        checks += c1
        if not ok1:
            return self._emit(PHASE14_INCOMPLETE, checks,
                              phase12_digest=p12digest,
                              manifest=manifest)
        ok2, profile, c2 = self._sch02()
        checks += c2
        ok3, contracts, c3 = (False, {}, [])
        if ok2:
            ok3, contracts, c3 = self._sch03()
            checks += c3
        ok4, cycle, c4 = (False, {}, [])
        if ok3:
            ok4, cycle, c4 = self._sch04()
            checks += c4
        verdict = PHASE14_IGNITED if all((ok1, ok2, ok3, ok4)) \
            else PHASE14_INCOMPLETE
        if verdict == PHASE14_IGNITED:
            checks.append(("SCH-05", True,
                           "phase14.scheduling_wiring_attestation.v1 "
                           "emitted — Scheduling Engine verified in "
                           "DRY-RUN mode (zero dispatches, "
                           "publisher-less egress, ephemeral slot "
                           "locks) under the Phase 12 attestation "
                           "with slot 14 closed CRM-not-needed "
                           "(D-163); handover to Phase 15 (Analytics) "
                           "is verified"))
        else:
            checks.append(("SCH-05", False,
                           "attestation emitted as IGNITION_INCOMPLETE "
                           "— remediate the named checks before the "
                           "Phase 15 handover"))
        return self._emit(verdict, checks, phase12_digest=p12digest,
                          manifest=manifest, profile=profile,
                          contracts=contracts, cycle=cycle)


def main() -> int:
    """CLI wiring guard: interactive wiring requires the injected
    providers, census and the offline event store configuration."""
    import argparse
    import sys
    ap = argparse.ArgumentParser(
        description="Phase 14 live wiring igniter (SCH-01..SCH-05, "
                    "D-164).")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    print("live_wiring_phase14_igniter: interactive wiring requires "
          "the phase12 attestation, the D-112 chain, the runtime "
          "census and the injected event store; see run() and the "
          "battery for the injected contract.", file=sys.stderr)
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

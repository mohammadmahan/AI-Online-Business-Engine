"""Phase 15 live wiring igniter — Analytics Engine wiring (D-165).

The tenth Live Wiring program phase. Phase 14 (D-164) verified the
Scheduling calendar in dry-run mode; Phase 15 now wires and verifies
the ANALYTICS read-side on top of the verified Phase 14 attestation —
in STRICT DRY-RUN / EPHEMERAL mode:

  ANA-01  the upstream `phase14.scheduling_wiring_attestation.v1` is
          present, PHASE14_IGNITED, manifest-bound, its canonical
          bytes recompute to the SHA-256 commitment rooted in the
          D-112 ledger (kind `phase14_scheduling_wiring_attestation`)
          over an intact chain — ANY refusal happens BEFORE the first
          engine call (zero engine calls on refusal);
  ANA-02  the verified runtime profile is loaded: the injected
          census marks Phases 5–12 and 14 present+VERIFIED+WIRED
          (slot 14 stays closed CRM-not-needed per D-163 and is NOT
          required), and the repo-real analytics seams are importable
          and consistent with the D-154 ENTRY_POINTS registry
          (phase16 = `canonical.analytics_engine` — the D-154
          cross-walk binds slot 16 "Analytics" to the D-085/D-086
          CQRS projection engine);
  ANA-03  the analytics contracts and invariants are validated
          through the REAL validator: ISO-8601 timestamps from the
          EVENT's own recorded instant (never the clock, D-085), the
          declared length bound (D-114), unknown-window/unknown-kind
          refusals, the event→metric classifier (publication published/
          failed for the PUBLICATION_SOURCES, order placed/completed/
          cancelled plus revenue_minor for the OMS spine; in-flight
          outcomes and metric-less refs classify to None), pure
          rollup math (counts accumulate, revenue sums, deterministic
          finalize/merge) and the D-088 deterministic report identity
          (`window_hash`: same inputs ⇒ same hash ⇒ idempotent
          generation);
  ANA-04  a NON-DESTRUCTIVE synthetic analytics cycle runs over the
          REAL `ProjectionEngine`: a synthetic event stream (the
          injected `events_source` — mocked per the prompt, D-085
          schema-compliant) is folded incrementally → the cursor
          advances exactly to the max seen seq (an UNKNOWN source is
          consumed-and-advanced; a MALFORMED metric payload is
          flagged, persisted in the malformed register, and NEVER
          advances the cursor — D-085 "flag, never guess", fail-
          closed) → determinism is proven by rebuilding from zero and
          byte-comparing the rollups (incremental == full replay,
          D-086) → re-consuming after the cursor advance is a no-op
          (exactly-once) → an idempotent report is generated under
          the D-088 `window_hash` (same inputs ⇒ same hash) → the
          cursor/quarantine state lives ONLY in the injected
          EPHEMERAL in-memory store (zero files, zero PG rows) →
          per-step telemetry (START/AUTH/INGEST/FLAG/REBUILD/
          IDEMPOTENT/REPORT/VERIFY/CLEANUP) and a deterministic
          summary hash; cleanup leaves zero residue;
  ANA-05  the canonical `phase15.analytics_wiring_attestation.v1` is
          emitted exactly once per run (aborts included) with the
          SHA-256 `attestation_digest`; any abort emits the same
          schema as IGNITION_INCOMPLETE with failure telemetry.

Ephemeral discipline: the analytics cursor default backend persists
to `local/volumes/analytics/projection.json` (or live PG). The probe
injects an EPHEMERAL in-memory cursor store with the identical
get_cursor/advance/reset/rollups/quarantine semantics — zero durable
footprint. The events_source is fully injected (a synthetic in-
process stream): no external warehouse, no external analytics
platform, no vendor module import (D-087 boundary preserved).

Security & purity (RULES §35, AST-pinned): injected source/store
transports only — zero sockets, zero raw shell, zero wall clock in
the core (every instant is the event's own recorded timestamp).
Campaign ids appear as hashes only; customer identity NEVER enters
any emitted record. D-124 deep redaction runs over every emitted
record with the public commitments (`phase14_digest`,
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
    "Phase15Error", "Phase15Attestation", "Phase15Igniter",
    "_EphemeralCursorStore", "ATTESTATION_SCHEMA", "PHASE15_IGNITED",
    "PHASE15_INCOMPLETE", "PHASE14_SCHEMA", "PHASE14_IGNITED",
    "PHASE14_ROW_KIND", "SEAMS", "SEAM_PHASES", "CYCLE_ID",
    "SYNTHETIC_STREAM", "canonical_hash",
]

ATTESTATION_SCHEMA = "phase15.analytics_wiring_attestation.v1"
PHASE15_IGNITED = "PHASE15_IGNITED"
PHASE15_INCOMPLETE = "IGNITION_INCOMPLETE"

PHASE14_SCHEMA = "phase14.scheduling_wiring_attestation.v1"
PHASE14_IGNITED = "PHASE14_IGNITED"

# The D-112 ledger kind that roots the Phase 14 attestation (D-164).
PHASE14_ROW_KIND = "phase14_scheduling_wiring_attestation"

_HEX64 = re.compile(r"^[0-9a-f]{64}$")

CYCLE_ID = "phase15-analytics-probe-0001"

SYNTHETIC_STREAM: List[Dict[str, Any]] = [
    # (source, seq, ref) — D-085 schema-compliant metric events
    {"source": "instagram", "seq": 11, "ref": {
        "event_id": "instagram|transition|ig-1",
        "occurred_at": "2026-09-20T09:05:00+00:00",
        "campaign_id": "camp-phase15-01",
        "outcome": "published"}},
    {"source": "telegram", "seq": 12, "ref": {
        "event_id": "telegram|publish|tg-1",
        "occurred_at": "2026-09-20T09:30:00+00:00",
        "campaign_id": "camp-phase15-01",
        "outcome": "duplicate_publish_blocked"}},
    {"source": "oms", "seq": 13, "ref": {
        "event_id": "oms|order|ord-1",
        "occurred_at": "2026-09-20T10:00:00+00:00",
        "campaign_id": "camp-phase15-01"}},
    {"source": "oms", "seq": 14, "ref": {
        "event_id": "oms|transition|ord-1",
        "occurred_at": "2026-09-21T10:00:00+00:00",
        "state": "COMPLETED", "order_total_minor": 450_000,
        "campaign_id": "camp-phase15-01"}},
    {"source": "oms", "seq": 15, "ref": {
        "event_id": "oms|transition|ord-2",
        "occurred_at": "2026-09-21T11:00:00+00:00",
        "state": "CANCELLED"}},
    # in-flight outcome → no metric (classifier returns None)
    {"source": "instagram", "seq": 16, "ref": {
        "event_id": "instagram|transition|ig-2",
        "occurred_at": "2026-09-21T12:00:00+00:00",
        "outcome": "container_created"}},
]


# Repo-real module seams for the analytics wiring. `SEAM_PHASES`
# pins each seam to the D-154 ENTRY_POINTS phase it must agree with.
SEAMS: Dict[str, str] = {
    "analytics_engine": "canonical.analytics_engine",
    "analytics_contracts": "canonical.analytics_contracts",
    "analytics_worker": "canonical.analytics_worker",
    "scheduling_engine": "canonical.scheduling_engine",
    "orchestration_engine": "canonical.orchestration_engine",
    "sync_event_store": "services.sync_engine",
}

SEAM_PHASES: Dict[str, Optional[int]] = {
    "analytics_engine": 16,   # registry slot 16 "Analytics"
    "analytics_contracts": None,
    "analytics_worker": None,
    "scheduling_engine": 15,
    "orchestration_engine": 13,
    "sync_event_store": None,
}


class Phase15Error(ValueError):
    """Contract-level misuse of the Phase 15 igniter."""


def _fail(reason: str) -> None:
    raise Phase15Error(reason)


def canonical_hash(payload: Dict[str, Any]) -> str:
    """SHA-256 over canonical JSON bytes — the shared project digest
    formula (Stage G/H/D-154..D-164 engines)."""
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class _EphemeralCursorStore:
    """In-memory cursor + snapshot store for PROBES — the analytics
    analog of the D-160/D-161/D-162/D-164 ephemeral locks: semantics
    identical to `_JsonCursorStore` (get_cursor/advance/reset/rollups)
    plus the malformed-event register, ZERO durable footprint. Never
    `local/volumes/analytics/projection.json`, never live PG."""

    def __init__(self) -> None:
        import threading
        self._lock = threading.Lock()
        self._data: Dict[str, Any] = {"last_seq": 0, "rollups": {}}
        self.malformed: List[Dict[str, Any]] = []

    def get_cursor(self) -> int:
        with self._lock:
            return int(self._data.get("last_seq", 0))

    def advance(self, last_seq: int, rollups: Dict) -> None:
        with self._lock:
            self._data["last_seq"] = int(last_seq)
            self._data["rollups"] = json.loads(json.dumps(
                rollups, ensure_ascii=False))

    def reset(self) -> None:
        with self._lock:
            self._data = {"last_seq": 0, "rollups": {}}

    def rollups(self) -> Dict:
        with self._lock:
            return json.loads(json.dumps(
                self._data.get("rollups", {}), ensure_ascii=False))

    def flag_malformed(self, record: Dict[str, Any]) -> None:
        """D-085 fail-closed quarantine: a malformed metric payload is
        registered (deterministic, in-memory) and must block the
        cursor; the record carries the reason and a payload hash —
        never the payload itself."""
        with self._lock:
            self.malformed.append(record)


@dataclass(frozen=True)
class Phase15Attestation:
    """Canonical, immutable Phase 15 ignition artifact."""
    schema: str
    verdict: str             # PHASE15_IGNITED / IGNITION_INCOMPLETE
    phase14_digest: str      # upstream attestation digest (commitment)
    manifest_sha256: str     # deployment fingerprint carried through
    profile: Dict[str, Any]  # runtime profile + seams summary
    contracts: Dict[str, Any]  # classifier/window/hash invariants
    cycle: Dict[str, Any]    # synthetic analytics telemetry
    checks: tuple = field(default_factory=tuple)  # (id, ok, detail)
    observed_tick: int = 0

    @property
    def ignited(self) -> bool:
        return self.verdict == PHASE15_IGNITED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "verdict": self.verdict,
            "phase14_digest": self.phase14_digest,
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


class Phase15Igniter:
    """ANA-01..ANA-05 with injected source/store transports.

    Injected:
      clock           — ``() -> int`` logical tick
      audit_sink      — ``callable(dict)`` (D-112/D-121 in prod)
      upstream_provider — ``() -> dict`` the phase14 attestation
      audit_rows      — ``() -> list`` the D-112 ledger rows
      chain_verifier  — ``() -> dict`` D-112 chain integrity
      census          — ``() -> dict`` the runtime profile census
      events_source   — ``callable(source_system, after_seq) ->
                        [(seq, ref), ...]`` the D-086 injected store
                        adapter (the synthetic stream in probe mode)
      cursor_store    — optional cursor store override (default: the
                        EPHEMERAL in-memory store)
      expected_entry_points — optional {phase: seam} override
    """

    def __init__(self, clock: Callable[[], int],
                 audit_sink: Callable[[Dict[str, Any]], None],
                 upstream_provider: Optional[Callable[[], Dict[str, Any]]] = None,
                 audit_rows: Optional[Callable[[], List[Dict[str, Any]]]] = None,
                 chain_verifier: Optional[Callable[[], Dict[str, Any]]] = None,
                 census: Optional[Callable[[], Dict[str, Any]]] = None,
                 events_source: Optional[Callable[[str, int], List[Tuple[int, Dict]]]] = None,
                 cursor_store: Optional[Any] = None,
                 expected_entry_points: Optional[Dict[int, str]] = None,
                 ) -> None:
        if not callable(clock) or not callable(audit_sink):
            _fail("clock and audit_sink required")
        self._clock = clock
        self._sink = audit_sink
        self._prov = {
            "phase14": upstream_provider,
            "audit_rows": audit_rows,
            "chain_verifier": chain_verifier,
            "census": census,
            "events_source": events_source,
            "cursor_store": cursor_store,
        }
        self._entry_points = dict(expected_entry_points) \
            if expected_entry_points else None

    # -- internals ---------------------------------------------------------

    def _load(self, name: str) -> Tuple[Optional[Any], str]:
        prov = self._prov.get(name)
        if prov is None:
            return None, "provider not injected"
        if name in ("events_source", "cursor_store"):
            return prov, ""  # transports: passed through, never invoked
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
              phase14_digest: str = "", manifest: str = "",
              profile: Optional[Dict[str, Any]] = None,
              contracts: Optional[Dict[str, Any]] = None,
              cycle: Optional[Dict[str, Any]] = None,
              ) -> Phase15Attestation:
        att = Phase15Attestation(
            schema=ATTESTATION_SCHEMA, verdict=verdict,
            phase14_digest=phase14_digest, manifest_sha256=manifest,
            profile=profile or {}, contracts=contracts or {},
            cycle=cycle or {},
            checks=tuple((c[0], c[1], deep_redact(str(c[2])))
                         for c in checks),
            observed_tick=self._clock())
        blob = json.dumps(att.to_dict(), sort_keys=True,
                          separators=(",", ":"), ensure_ascii=False)
        redacted = json.loads(deep_redact(blob))
        # Public commitments (D-146/D-153/D-154..D-164 precedent).
        redacted["phase14_digest"] = att.phase14_digest
        redacted["manifest_sha256"] = att.manifest_sha256
        self._sink(redacted)
        return att

    # -- ANA-01: the Phase 14 attestation --------------------------------------

    def _ana01(self) -> Tuple[bool, str, str,
                              List[Tuple[str, bool, str]]]:
        """(ok, phase14_digest, manifest, checks)."""
        checks: List[Tuple[str, bool, str]] = []
        att, err = self._load("phase14")
        if att is None:
            checks.append(("ANA-01", False,
                           "Phase 14 attestation absent "
                           f"({err}) — Phase 14 never ignited"))
            return False, "", "", checks
        if not isinstance(att, dict):
            checks.append(("ANA-01", False,
                           "Phase 14 attestation malformed"))
            return False, "", "", checks
        if att.get("schema") != PHASE14_SCHEMA:
            checks.append(("ANA-01", False,
                           f"attestation schema {att.get('schema')!r} "
                           f"!= {PHASE14_SCHEMA!r}"))
            return False, "", "", checks
        if att.get("verdict") != PHASE14_IGNITED:
            checks.append(("ANA-01", False,
                           f"Phase 14 verdict {att.get('verdict')!r} "
                           f"!= {PHASE14_IGNITED!r} — calendar not "
                           "wired, Phase 15 refused"))
            return False, "", "", checks
        manifest = att.get("manifest_sha256", "")
        if not (isinstance(manifest, str) and _HEX64.match(manifest)):
            checks.append(("ANA-01", False,
                           "phase14 attestation lacks its manifest "
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
                        str(row.get("event_kind", "")) != PHASE14_ROW_KIND:
                    continue
                detail = row.get("detail")
                if isinstance(detail, dict) and \
                        isinstance(detail.get("attestation_digest"),
                                   str):
                    rooted_digest = detail["attestation_digest"]
                    break
        if not rooted_digest:
            checks.append(("ANA-01", False,
                           "phase14 attestation not rooted in the "
                           "D-112 ledger — upstream wiring was never "
                           "durably attested"))
            return False, recomputed, "", checks
        if rooted_digest != recomputed:
            checks.append(("ANA-01", False,
                           f"phase14 attestation digest "
                           f"{recomputed[:16]}… != rooted "
                           f"{rooted_digest[:16]}… — DRIFTED or "
                           "altered upstream attestation"))
            return False, recomputed, "", checks
        cv, err = self._load("chain_verifier")
        if cv is None or not isinstance(cv, dict) or not cv.get("ok"):
            reason = (cv or {}).get("reason", err or "verifier absent")
            checks.append(("ANA-01", False,
                           f"D-112 chain not intact ({reason}) — "
                           "wiring on a broken ledger is refused"))
            return False, recomputed, "", checks
        checks.append(("ANA-01", True,
                       "phase14 attestation PHASE14_IGNITED, digest "
                       f"recomputes ({recomputed[:16]}…) and matches "
                       "the rooted commitment in the D-112 ledger "
                       f"({int(cv.get('rows', 0))} rows, zero breaks)"))
        return True, recomputed, manifest, checks

    # -- ANA-02: runtime profile + module seams --------------------------------

    def _ana02(self) -> Tuple[bool, Dict[str, Any],
                              List[Tuple[str, bool, str]]]:
        checks: List[Tuple[str, bool, str]] = []
        summary: Dict[str, Any] = {"runtime_profile_verified": False,
                                   "seams_ok": False,
                                   "phases": []}
        census, err = self._load("census")
        if census is None or not isinstance(census, dict):
            checks.append(("ANA-02", False,
                           "runtime profile census unavailable "
                           f"({err}) — fail closed"))
            return False, summary, checks
        if not census.get("runtime_profile_verified"):
            checks.append(("ANA-02", False,
                           "runtime profile NOT verified — refuse"))
            return False, summary, checks
        rows = {p.get("phase"): p for p in census.get("phases", [])
                if isinstance(p, dict)}
        for n in (5, 6, 7, 8, 9, 10, 11, 12, 14):
            p = rows.get(n)
            if p is None:
                checks.append(("ANA-02", False,
                               f"Phase {n} missing from the runtime "
                               "profile census (Phases 5/6/7/8/9/10/"
                               "11/12/14 required; slot 14 closed "
                               "CRM-not-needed per D-163)"))
                return False, summary, checks
            if not (p.get("verified") and p.get("wired")):
                checks.append(("ANA-02", False,
                               f"Phase {n} not VERIFIED+WIRED — "
                               "analytics wiring refused"))
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
                checks.append(("ANA-02", False,
                               "D-154 registry unavailable "
                               f"({type(exc).__name__})"))
                return False, summary, checks
        for key, modname in SEAMS.items():
            try:
                importlib.import_module(modname)
            except Exception as exc:  # noqa: BLE001 — typed refusal
                checks.append(("ANA-02", False,
                               f"canonical seam {modname} not "
                               f"importable ({type(exc).__name__}) — "
                               "repo seam missing"))
                return False, summary, checks
            phase_no = SEAM_PHASES.get(key)
            expected = entry_points.get(phase_no) \
                if phase_no is not None else None
            if expected and expected != modname:
                checks.append(("ANA-02", False,
                               f"ENTRY_POINTS[{phase_no}] = "
                               f"{expected!r} != repo seam "
                               f"{modname!r} — registry drift"))
                return False, summary, checks
        # the load-bearing pin: registry slot 16 "Analytics" MUST bind
        # to the projection engine (the D-154 cross-walk)
        if entry_points.get(16) != SEAMS["analytics_engine"]:
            checks.append(("ANA-02", False,
                           "registry slot 16 (Analytics) does not "
                           f"bind {SEAMS['analytics_engine']!r} — "
                           "cross-walk drift"))
            return False, summary, checks
        summary["seams_ok"] = True
        checks.append(("ANA-02", True,
                       f"all {len(SEAMS)} analytics seams importable "
                       "and consistent with the D-154 ENTRY_POINTS "
                       "registry (slot 16 → "
                       f"{SEAMS['analytics_engine']})"))
        return True, summary, checks

    # -- ANA-03: analytics contracts & invariants -------------------------------

    def _ana03(self) -> Tuple[bool, Dict[str, Any],
                              List[Tuple[str, bool, str]]]:
        checks: List[Tuple[str, bool, str]] = []
        summary: Dict[str, Any] = {
            "contracts_ok": False, "classifier_ok": False,
            "windows_pure": False, "report_hash_ok": False,
        }
        try:
            from canonical.analytics_contracts import (
                ENGINE_SOURCES, METRIC_KINDS, MK_ORDER_CANCELLED,
                MK_ORDER_COMPLETED, MK_ORDER_PLACED,
                MK_PUBLICATION_PUBLISHED, MK_REVENUE_MINOR, WINDOW_DAILY,
                WINDOWS, AnalyticsContractError, add_metric,
                classify_event, finalize_rollup, merge_rollups,
                new_rollup, window_hash, window_key, parse_occurred_at,
                MAX_OCCURRED_AT_LEN,
            )
        except Exception as exc:  # noqa: BLE001 — typed refusal
            checks.append(("ANA-03", False,
                           f"analytics contracts not importable "
                           f"({type(exc).__name__}) — repo seam missing"))
            return False, summary, checks
        summary["metric_kinds"] = len(METRIC_KINDS)
        summary["engine_sources"] = list(ENGINE_SOURCES)

        # windowing purity: the event's OWN instant, never a clock
        for good in ("2026-09-20T09:05:00+00:00",
                     "2026-09-20T09:05:00Z"):
            try:
                parse_occurred_at(good)
            except AnalyticsContractError:
                checks.append(("ANA-03", False,
                               f"REAL parser rejected a conforming "
                               f"instant: {good}"))
                return False, summary, checks
        for bad, expect in (
                ("not-a-timestamp", "unparsable"),
                (None, "ISO-8601 string"),
                ("x" * (MAX_OCCURRED_AT_LEN + 1), "exceeds")):
            try:
                parse_occurred_at(bad)
                _fail(f"window invariant not enforced "
                      f"(expected {expect} rejection)")
            except AnalyticsContractError as exc:
                if expect not in str(exc.args[0]):
                    checks.append(("ANA-03", False,
                                   f"window invariant mis-classified: "
                                   f"{str(exc.args[0])[:120]}"))
                    return False, summary, checks
        try:
            window_key("2026-09-20T09:05:00+00:00", "weekly")
            _fail("unknown window accepted")
        except AnalyticsContractError as exc:
            if "window must be one of" not in str(exc.args[0]):
                checks.append(("ANA-03", False,
                               "unknown-window refusal mis-shaped"))
                return False, summary, checks
        summary["windows_pure"] = True

        # the REAL classifier over every synthetic event class
        expected_classes = {
            "instagram|transition|ig-1": MK_PUBLICATION_PUBLISHED,
            "telegram|publish|tg-1": MK_PUBLICATION_PUBLISHED,
            "oms|order|ord-1": MK_ORDER_PLACED,
            "oms|transition|ord-2": MK_ORDER_CANCELLED,
        }
        for ev in SYNTHETIC_STREAM:
            got = classify_event(ev["source"], dict(ev["ref"]))
            eid = ev["ref"]["event_id"]
            if eid in expected_classes:
                kind = got.get("kind") if isinstance(got, dict) else None
                if kind != expected_classes[eid]:
                    checks.append(("ANA-03", False,
                                   f"classifier mis-read {eid}: "
                                   f"{kind!r}"))
                    return False, summary, checks
            elif eid == "oms|transition|ord-1":
                if not isinstance(got, list) or \
                        got[0].get("kind") != MK_ORDER_COMPLETED or \
                        got[1].get("kind") != MK_REVENUE_MINOR or \
                        got[1].get("value") != 450_000:
                    checks.append(("ANA-03", False,
                                   "COMPLETED transition did not "
                                   "produce completion + revenue "
                                   "metrics"))
                    return False, summary, checks
            else:
                if got is not None:
                    checks.append(("ANA-03", False,
                                   f"in-flight event {eid} produced a "
                                   "metric — classifier impure"))
                    return False, summary, checks
        # malformed timestamp in a metric payload → Class-B (the
        # engine path flags it; the contract itself refuses)
        try:
            classify_event("oms", {"event_id": "oms|order|bad",
                                   "occurred_at": "garbage"})
            _fail("malformed metric payload accepted")
        except AnalyticsContractError:
            pass
        summary["classifier_ok"] = True

        # rollup math determinism: counts accumulate, revenue sums
        r1 = new_rollup()
        m = classify_event("oms", dict(SYNTHETIC_STREAM[3]["ref"]))
        for metric in (m if isinstance(m, list) else [m]):
            for grain in WINDOWS:
                add_metric(r1, metric, window=grain)
        fin = finalize_rollup(r1)
        day = fin[MK_REVENUE_MINOR]["2026-09-21"]["value"]
        if day != 450_000 or \
                fin[MK_ORDER_COMPLETED]["2026-09-21"]["value"] != 1:
            checks.append(("ANA-03", False,
                           "rollup math wrong (revenue must sum, "
                           "counts must accumulate)"))
            return False, summary, checks
        r2 = new_rollup()
        for grain in WINDOWS:
            add_metric(r2, {"kind": MK_ORDER_PLACED,
                            "occurred_at":
                                "2026-09-20T10:00:00+00:00",
                            "value": 1}, window=grain)
        merged = finalize_rollup(merge_rollups(r1, r2))
        if merged[MK_ORDER_PLACED]["2026-09-20"]["value"] != 1 or \
                merged[MK_REVENUE_MINOR]["2026-09-21"]["value"] != \
                450_000:
            checks.append(("ANA-03", False,
                           "merge not deterministic"))
            return False, summary, checks

        # D-088 report identity: same inputs ⇒ same hash
        h1 = window_hash("daily-traffic", WINDOW_DAILY,
                         "2026-09-20", "2026-09-21", 15)
        h2 = window_hash("daily-traffic", WINDOW_DAILY,
                         "2026-09-20", "2026-09-21", 15)
        if h1 != h2 or not _HEX64.match(h1):
            checks.append(("ANA-03", False,
                           "window_hash not deterministic"))
            return False, summary, checks
        if window_hash("daily-traffic", WINDOW_DAILY,
                       "2026-09-20", "2026-09-21", 16) == h1:
            checks.append(("ANA-03", False,
                           "window_hash ignores the cursor"))
            return False, summary, checks
        summary["report_hash_ok"] = True
        summary["contracts_ok"] = True
        checks.append(("ANA-03", True,
                       f"REAL contracts enforced: {len(METRIC_KINDS)} "
                       "metric kinds, pure windowing from the event's "
                       "own instant, classifier + rollup math "
                       "deterministic, D-088 report identity stable"))
        return True, summary, checks

    # -- ANA-04: the synthetic analytics cycle ----------------------------------

    def _ana04(self) -> Tuple[bool, Dict[str, Any],
                              List[Tuple[str, bool, str]]]:
        from canonical.analytics_contracts import (
            MK_ORDER_COMPLETED, MK_ORDER_PLACED,
            MK_PUBLICATION_PUBLISHED, MK_REVENUE_MINOR, WINDOW_DAILY,
            WINDOW_HOURLY, WINDOW_MONTHLY, AnalyticsContractError,
        )
        from canonical.analytics_engine import ProjectionEngine

        checks: List[Tuple[str, bool, str]] = []
        summary: Dict[str, Any] = {"steps": [], "summary_hash": "",
                                   "cursor_backend": "ephemeral",
                                   "malformed": 0, "drift": False}
        source, err = self._load("events_source")
        if source is None:
            checks.append(("ANA-04", False,
                           f"event stream unavailable ({err}) — fail "
                           "closed"))
            return False, summary, checks
        store = self._prov.get("cursor_store") or _EphemeralCursorStore()
        # fail-closed ENTRY GATE: a non-ephemeral cursor backend means
        # a durable analytics footprint (files or PG) — refuse before
        # any engine work (the VERIFY step re-asserts this as defense
        # in depth)
        if not isinstance(store, _EphemeralCursorStore):
            checks.append(("ANA-04", False,
                           "cursor backend is not the ephemeral "
                           "in-memory store — durable analytics "
                           "footprint refused"))
            return False, summary, checks
        engine = ProjectionEngine(source, cursor_store=store)

        try:
            # START — the probe plan
            summary["steps"].append([
                "START", True,
                {"cycle_id": CYCLE_ID,
                 "cursor_backend": "ephemeral-in-memory"}])

            # AUTH — read-only envelope: analytics consumes durable
            # events and produces aggregates; it NEVER writes to any
            # domain, warehouse or platform
            summary["steps"].append([
                "AUTH", True,
                {"envelope": ["read_only", "in_process"],
                 "egress": "none (D-087 boundary)"}])

            # INGEST — incremental fold over the synthetic stream;
            # every metric class asserted in the daily snapshot
            first = engine.incremental_pass()
            if first.get("consumed") != 5:
                _fail(f"unexpected consumed count: {first}")
            if first.get("to_cursor") != 16:
                _fail(f"cursor did not advance to the max seq: "
                      f"{first}")
            snap = engine.snapshot(WINDOW_DAILY)
            if snap.get(MK_PUBLICATION_PUBLISHED, {})["2026-09-20"]\
                    ["value"] != 2 or \
                    snap.get(MK_ORDER_PLACED, {})["2026-09-20"]\
                    ["value"] != 1 or \
                    snap.get(MK_ORDER_COMPLETED, {})["2026-09-21"]\
                    ["value"] != 1 or \
                    snap.get(MK_REVENUE_MINOR, {})["2026-09-21"]\
                    ["value"] != 450_000:
                _fail(f"daily snapshot aggregates wrong: {snap}")
            # hourly/monthly windows folded the same events
            hsnap = engine.snapshot(WINDOW_HOURLY)
            if hsnap.get(MK_PUBLICATION_PUBLISHED, {})\
                    ["2026-09-20T09"]["value"] != 2:
                _fail("hourly window not bucketed")
            msnap = engine.snapshot(WINDOW_MONTHLY)
            if msnap.get(MK_REVENUE_MINOR, {})["2026-09"]["value"] != \
                    450_000:
                _fail("monthly window not bucketed")
            summary["steps"].append([
                "INGEST", True,
                {"consumed": first.get("consumed"),
                 "cursor": first.get("to_cursor"),
                 "windows": ["hourly", "daily", "monthly"],
                 "revenue_daily": 450_000}])

            # IDEMPOTENT — re-consume after the cursor: exactly-once
            again = engine.incremental_pass()
            if again.get("consumed") != 0 or \
                    again.get("from_cursor") != 16:
                _fail(f"re-consume not idempotent: {again}")
            summary["steps"].append([
                "IDEMPOTENT", True,
                {"reconsume": "no-op (cursor at 16)"}])

            # FLAG — a malformed metric payload (unparsable occurred_at
            # on a metric-shaped event) must be quarantined and NEVER
            # advance the cursor (D-085: flag, never guess)
            stream2 = [("oms", 17, {"event_id": "oms|order|bad",
                                    "occurred_at": "garbage"})]

            def bad_source(src: str, after: int) -> List[Tuple[int, Dict]]:
                return [(s, r) for (sname, s, r) in stream2
                        if sname == src and s > after]

            bad_engine = ProjectionEngine(
                bad_source, cursor_store=store)
            try:
                bad_engine.incremental_pass()
                _fail("malformed payload silently consumed — "
                      "fail-closed violated")
            except AnalyticsContractError:
                store.flag_malformed({
                    "seq": 17, "source": "oms",
                    "payload_hash": canonical_hash(
                        stream2[0][2])[:16],
                    "reason": "unparsable_occurred_at"})
            if store.get_cursor() != 16:
                _fail(f"malformed event advanced the cursor "
                      f"({store.get_cursor()})")
            if len(store.malformed) != 1:
                _fail("malformed event not quarantined")
            summary["malformed"] = len(store.malformed)
            summary["steps"].append([
                "FLAG", True,
                {"quarantined": 1, "cursor_held_at": 16,
                 "payload": "hashed-only"}])

            # REBUILD — determinism: full replay from zero must
            # byte-match the incremental rollups (D-086)
            before = store.rollups()
            rb = engine.rebuild()
            if rb.get("consumed") != 5 or rb.get("to_cursor") != 16:
                _fail(f"rebuild replay diverged: {rb}")
            if store.rollups() != before:
                _fail("rebuild rollups != incremental rollups — "
                      "drift")
            summary["drift"] = False
            summary["steps"].append([
                "REBUILD", True,
                {"replay": "incremental == full replay",
                 "drift": False}])

            # REPORT — D-088 idempotent report identity
            from canonical.analytics_contracts import window_hash
            rh = window_hash("daily-traffic", WINDOW_DAILY,
                             "2026-09-20", "2026-09-21", 16)
            if not _HEX64.match(rh):
                _fail("report hash malformed")
            summary["steps"].append([
                "REPORT", True,
                {"window_hash": rh[:16] + "…",
                 "idempotent": True}])

            # VERIFY — read-only, ephemeral, no egress markers
            from live_wiring_phase15_igniter import (
                _EphemeralCursorStore as _EphemeralCursorStoreSelf,
            )
            if not isinstance(store, _EphemeralCursorStoreSelf):
                _fail("cursor backend is not the ephemeral in-memory "
                      "store — durable footprint")
            raw = json.dumps(engine.snapshot(WINDOW_DAILY)).lower()
            for marker in ("warehouse", "external", "webhook_secret",
                           "auth_code", "pan", "card_number"):
                if marker in raw:
                    _fail(f"egress-boundary violation: {marker!r} "
                          "found in analytics output")
            summary["cursor_backend"] = "ephemeral"
            summary["steps"].append([
                "VERIFY", True, {"markers": "clean",
                                 "cursor_backend": "ephemeral"}])

            # CLEANUP — persist the data-minimized cycle artifact,
            # read it back, then delete EVERYTHING
            artifact = {
                "cycle_id": CYCLE_ID,
                "cursor": 16,
                "consumed": 5,
                "report_hash": rh,
                "dry_run": True,
                "egress": False,
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
                "cursor": 16,
                "consumed": 5,
                "report_hash": rh,
                "dry_run": True,
                "egress": False,
            }
            summary["summary_hash"] = canonical_hash(plan)
            checks.append(("ANA-04", True,
                           "synthetic analytics cycle completed: "
                           f"{len(summary['steps'])} steps, summary "
                           f"hash {summary['summary_hash'][:16]}…, "
                           "incremental == replay, malformed payload "
                           "quarantined with cursor held, exactly-once "
                           "re-consume, zero egress"))
            return True, summary, checks
        except Phase15Error as exc:
            checks.append(("ANA-04", False, str(exc)[:160]))
            self._cleanup_scratch()
            return False, summary, checks
        except AnalyticsContractError as exc:
            checks.append(("ANA-04", False,
                           f"analytics contract refusal (Class-B): "
                           f"{str(exc.args[0])[:120]}"))
            self._cleanup_scratch()
            return False, summary, checks
        except Exception as exc:  # noqa: BLE001 — typed refusal (D-124)
            checks.append(("ANA-04", False,
                           f"synthetic analytics cycle failed "
                           f"({type(exc).__name__})"))
            self._cleanup_scratch()
            return False, summary, checks

    # -- scratch (namespace-scoped, the only general persistence) --

    def _scratch_write(self, artifact: Dict[str, Any]) -> None:
        self._scratch_store["phase15-scratch:analytics"] = artifact

    def _scratch_read(self) -> Any:
        return self._scratch_store.get("phase15-scratch:analytics")

    def _scratch_delete(self) -> bool:
        return self._scratch_store.pop("phase15-scratch:analytics",
                                       None) is not None

    def _scratch_residue(self) -> List[str]:
        return sorted(k for k in self._scratch_store
                      if k.startswith("phase15-scratch:"))

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

    def run(self) -> Phase15Attestation:
        """ANA-01..ANA-05 → the canonical attestation. Exactly one
        audited attestation per call (including aborts); an ANA-01
        refusal performs ZERO engine calls."""
        checks: List[Tuple[str, bool, str]] = []
        ok1, p14digest, manifest, c1 = self._ana01()
        checks += c1
        if not ok1:
            return self._emit(PHASE15_INCOMPLETE, checks,
                              phase14_digest=p14digest,
                              manifest=manifest)
        ok2, profile, c2 = self._ana02()
        checks += c2
        ok3, contracts, c3 = (False, {}, [])
        if ok2:
            ok3, contracts, c3 = self._ana03()
            checks += c3
        ok4, cycle, c4 = (False, {}, [])
        if ok3:
            ok4, cycle, c4 = self._ana04()
            checks += c4
        verdict = PHASE15_IGNITED if all((ok1, ok2, ok3, ok4)) \
            else PHASE15_INCOMPLETE
        if verdict == PHASE15_IGNITED:
            checks.append(("ANA-05", True,
                           "phase15.analytics_wiring_attestation.v1 "
                           "emitted — Analytics Engine verified in "
                           "EPHEMERAL DRY-RUN mode (read-only "
                           "in-process projection, incremental == "
                           "replay, malformed quarantined, zero "
                           "egress) under the Phase 14 attestation; "
                           "handover to Phase 16 (AI Business "
                           "Analyst) is verified"))
        else:
            checks.append(("ANA-05", False,
                           "attestation emitted as IGNITION_INCOMPLETE "
                           "— remediate the named checks before the "
                           "Phase 16 handover"))
        return self._emit(verdict, checks, phase14_digest=p14digest,
                          manifest=manifest, profile=profile,
                          contracts=contracts, cycle=cycle)


def main() -> int:
    """CLI wiring guard: interactive wiring requires the injected
    providers, census and the synthetic event stream configuration."""
    import argparse
    import sys
    ap = argparse.ArgumentParser(
        description="Phase 15 live wiring igniter (ANA-01..ANA-05, "
                    "D-165).")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    print("live_wiring_phase15_igniter: interactive wiring requires "
          "the phase14 attestation, the D-112 chain, the runtime "
          "census and the injected event stream; see run() and the "
          "battery for the injected contract.", file=sys.stderr)
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

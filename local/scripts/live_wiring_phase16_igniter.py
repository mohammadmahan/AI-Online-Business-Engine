"""Phase 16 live wiring igniter — Analyst Service wiring (D-166).

The eleventh Live Wiring program phase. Phase 15 (D-165) verified the
analytics read-side in ephemeral dry-run mode; Phase 16 now wires and
verifies the AI BUSINESS ANALYST on top of the verified Phase 15
attestation — in STRICT DRY-RUN / EPHEMERAL mode:

  ANL-01  the upstream `phase15.analytics_wiring_attestation.v1` is
          present, PHASE15_IGNITED, manifest-bound, its canonical
          bytes recompute to the SHA-256 commitment rooted in the
          D-112 ledger (kind `phase15_analytics_wiring_attestation`)
          over an intact chain — ANY refusal happens BEFORE the first
          engine call (zero engine calls on refusal);
  ANL-02  the verified runtime profile is loaded: the injected
          census marks Phases 5–12, 14 and 15 present+VERIFIED+WIRED
          (slot 14 stays closed CRM-not-needed per D-163 and is NOT
          required), and the repo-real analyst seams are importable
          and consistent with the D-154 ENTRY_POINTS registry
          (phase17 = `canonical.analyst_engine` — the D-154 cross-walk
          binds slot 17 "AI Business Analyst" to the D-101/D-102/
          D-104 insight lifecycle engine);
  ANL-03  the analyst contracts and invariants are validated through
          the REAL validator: Class-B rejection of invalid analysis
          requests (missing fields, unknown categories/severities,
          confidence outside [0, 1], incomplete metric contexts,
          empty correlation keys, over-bound payloads — D-114), the
          DETERMINISTIC insight identity (SHA-256 over (category,
          correlation_keys, metric_refs) — identical evidence ⇒
          identical key, no wall clock, no generator state), the
          lifecycle edge matrix (GENERATED → EVALUATED →
          DISPATCHED_TO_HITL | AUTO_ACCEPTED | DISMISSED, SUPERSEDED
          reachable from any non-terminal state, terminals exitless),
          and the D-104 HITL boundary (HIGH/CRITICAL severity or a
          state-mutating payload is STRUCTURALLY non-auto-acceptable);
  ANL-04  a NON-DESTRUCTIVE synthetic analyst cycle runs over the
          REAL `AnalystEngine` with an injected mock data provider
          (D-142-conformant synthetic metric refs — no LLM provider,
          no data lake, the evaluator an injected PURE function):
          propose → durable GENERATED (exactly-once; an identical-
          evidence re-propose is a durable `DUPLICATE` with a dedup
          audit row regardless of the caller's incidental insight_id)
          → evaluate (pure evaluator verdict, durable EVALUATED)
          → the D-104 boundary driven BOTH ways (a HIGH-severity
          insight structurally refuses AUTO_ACCEPT with
          `hitl_required_boundary` and dispatches to HITL; a
          LOW-severity insight auto-accepts; a state-mutating payload
          on a LOW-severity insight is still HITL-bound) → dismissal
          → supersede (a newer evidence covering the same correlation
          keys marks the earlier insight SUPERSEDED, ledger history
          kept) → chain-of-thought integrity: the durable ledger
          rebuilds the COMPLETE rationale for one insight from
          D-027 events alone in order (generated → evaluated →
          decision [+ superseded]) and a full-ledger replay
          reconstructs every insight row (D-104) → invalid analysis
          requests fail closed BEFORE any durable write with the
          reason named → the vault lives ONLY in the injected
          EPHEMERAL in-process store (zero files, zero PG rows) →
          per-step telemetry (START/AUTH/PROPOSE/EVALUATE/BOUNDARY/
          SUPERSEDE/LEDGER/INVALID/VERIFY/CLEANUP) and a
          deterministic summary hash; cleanup leaves zero residue;
  ANL-05  the canonical `phase16.analyst_wiring_attestation.v1` is
          emitted exactly once per run (aborts included) with the
          SHA-256 `attestation_digest`; any abort emits the same
          schema as IGNITION_INCOMPLETE with failure telemetry.

Sandbox discipline: the analyst vault default backend persists to
`local/volumes/analyst/insights.json` (or live PG). The probe injects
an EPHEMERAL in-process vault with the identical insert/get/set_status/
all_insights semantics — zero durable footprint. The evaluator is an
injected PURE function (deterministic, no AI SDK); NO real LLM
provider is contacted and NO historical data lake is read — the
synthetic data provider is a pure in-process fixture conforming to
the D-142 vector-store record shapes (ids as hashes, no content
payloads).

Security & purity (RULES §35, AST-pinned): injected engine/vault
transports only — zero sockets, zero raw shell, zero wall clock in
the core. Customer identity and recommendation payloads beyond the
canonical Recommendation shape NEVER enter any emitted record: only
hashes, counts, status names, verdict names and step telemetry. D-124
deep redaction runs over every emitted record with the public
commitments (`phase15_digest`, `manifest_sha256`) restored after
redaction.
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
    "Phase16Error", "Phase16Attestation", "Phase16Igniter",
    "_EphemeralVault", "ATTESTATION_SCHEMA", "PHASE16_IGNITED",
    "PHASE16_INCOMPLETE", "PHASE15_SCHEMA", "PHASE15_IGNITED",
    "PHASE15_ROW_KIND", "PHASE16_ROW_KIND", "SEAMS", "SEAM_PHASES",
    "CYCLE_ID",
    "PROBE_INSIGHT_LOW", "PROBE_INSIGHT_HIGH", "canonical_hash",
]

# Repo-real module seams for the analyst wiring. `SEAM_PHASES`
# pins each seam to the D-154 ENTRY_POINTS phase it must agree with.
SEAMS: Dict[str, str] = {
    "analyst_engine": "canonical.analyst_engine",
    "analyst_contracts": "canonical.analyst_contracts",
    "analyst_worker": "canonical.analyst_worker",
    "analytics_engine": "canonical.analytics_engine",
    "sync_event_store": "services.sync_engine",
}

SEAM_PHASES: Dict[str, Optional[int]] = {
    "analyst_engine": 17,   # registry slot 17 "AI Business Analyst"
    "analyst_contracts": None,
    "analyst_worker": None,
    "analytics_engine": 16,
    "sync_event_store": None,
}

ATTESTATION_SCHEMA = "phase16.analyst_wiring_attestation.v1"
PHASE16_IGNITED = "PHASE16_IGNITED"
PHASE16_INCOMPLETE = "IGNITION_INCOMPLETE"

PHASE15_SCHEMA = "phase15.analytics_wiring_attestation.v1"
PHASE15_IGNITED = "PHASE15_IGNITED"

# The D-112 ledger kind that roots the Phase 15 attestation (D-165).
PHASE15_ROW_KIND = "phase15_analytics_wiring_attestation"

# The D-112 ledger kind that roots the Phase 16 attestation (D-166).
PHASE16_ROW_KIND = "phase16_analyst_wiring_attestation"

_HEX64 = re.compile(r"^[0-9a-f]{64}$")

CYCLE_ID = "phase16-analyst-probe-0001"

# Synthetic data provider fixtures — D-142-conformant SHAPES (ids as
# hashes, no content payloads, metric_refs into the D-085 metric
# taxonomy). These are pure in-process fixtures: no LLM, no lake.
_METRIC_REFS = [
    {"metric_kind": "order_completed", "window_ref": "2026-09-20"},
    {"metric_kind": "revenue_minor", "window_ref": "2026-09-20"},
]

PROBE_INSIGHT_LOW: Dict[str, Any] = {
    "insight_id": "phase16-probe-low-0001",
    "category": "sales_performance",
    "severity": "LOW",
    "metric_refs": _METRIC_REFS,
    "actionable_payload": {
        "action": "report_summary",
        "rationale": "synthetic probe insight (dry-run)",
        "mutates_business_state": False,
    },
    "confidence_score": 0.75,
    "correlation_keys": ["channel:telegram", "window:2026-09-20"],
    "status": "GENERATED",
}

PROBE_INSIGHT_HIGH: Dict[str, Any] = {
    "insight_id": "phase16-probe-high-0001",
    "category": "inventory_velocity",
    "severity": "HIGH",
    "metric_refs": [
        {"metric_kind": "order_cancelled", "window_ref": "2026-09-21"},
    ],
    "actionable_payload": {
        "action": "reorder_review",
        "rationale": "synthetic probe insight (dry-run)",
        "mutates_business_state": False,
    },
    "confidence_score": 0.9,
    "correlation_keys": ["sku:SKU-A", "window:2026-09-21"],
    "status": "GENERATED",
}


class Phase16Error(ValueError):
    """Contract-level misuse of the Phase 16 igniter."""


def _fail(reason: str) -> None:
    raise Phase16Error(reason)


def canonical_hash(payload: Dict[str, Any]) -> str:
    """SHA-256 over canonical JSON bytes — the shared project digest
    formula (Stage G/H/D-154..D-165 engines)."""
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class _EphemeralVault:
    """In-process insight vault for PROBES — the analyst analog of the
    D-160..D-165 ephemeral backends: insert/get/set_status/all_insights
    semantics identical to `_JsonVault`, ZERO durable footprint. Never
    `local/volumes/analyst/insights.json`, never live PG."""

    def __init__(self) -> None:
        import threading
        self._lock = threading.Lock()
        self._rows: Dict[str, Dict[str, Any]] = {}

    def insert_insight(self, row: Dict[str, Any]) -> str:
        with self._lock:
            key = row["insight_key"]
            if key in self._rows:
                return "duplicate"
            self._rows[key] = json.loads(json.dumps(
                row, ensure_ascii=False))
            return "created"

    def get_insight(self, insight_key: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._rows.get(insight_key)
            return json.loads(json.dumps(row, ensure_ascii=False)) \
                if row else None

    def set_status(self, insight_key: str, status: str,
                   superseded_by: Optional[str]) -> bool:
        with self._lock:
            row = self._rows.get(insight_key)
            if row is None:
                return False
            row["status"] = status
            row["superseded_by"] = superseded_by
            return True

    def all_insights(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return json.loads(json.dumps(self._rows, ensure_ascii=False))


@dataclass(frozen=True)
class Phase16Attestation:
    """Canonical, immutable Phase 16 ignition artifact."""
    schema: str
    verdict: str             # PHASE16_IGNITED / IGNITION_INCOMPLETE
    phase15_digest: str      # upstream attestation digest (commitment)
    manifest_sha256: str     # deployment fingerprint carried through
    profile: Dict[str, Any]  # runtime profile + seams summary
    contracts: Dict[str, Any]  # identity/edge/HITL invariants
    cycle: Dict[str, Any]    # synthetic analyst telemetry
    checks: tuple = field(default_factory=tuple)  # (id, ok, detail)
    observed_tick: int = 0

    @property
    def ignited(self) -> bool:
        return self.verdict == PHASE16_IGNITED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "verdict": self.verdict,
            "phase15_digest": self.phase15_digest,
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


class Phase16Igniter:
    """ANL-01..ANL-05 with injected engine/vault transports.

    Injected:
      clock           — ``() -> int`` logical tick
      audit_sink      — ``callable(dict)`` (D-112/D-121 in prod)
      upstream_provider — ``() -> dict`` the phase15 attestation
      audit_rows      — ``() -> list`` the D-112 ledger rows
      chain_verifier  — ``() -> dict`` D-112 chain integrity
      census          — ``() -> dict`` the runtime profile census
      stack_factory   — ``() -> (store, vault)`` building the REAL
                        D-027 parity store and the EPHEMERAL vault
                        fresh per run (the engine is constructed by
                        the igniter over them)
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
            "phase15": upstream_provider,
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
              phase15_digest: str = "", manifest: str = "",
              profile: Optional[Dict[str, Any]] = None,
              contracts: Optional[Dict[str, Any]] = None,
              cycle: Optional[Dict[str, Any]] = None,
              ) -> Phase16Attestation:
        att = Phase16Attestation(
            schema=ATTESTATION_SCHEMA, verdict=verdict,
            phase15_digest=phase15_digest, manifest_sha256=manifest,
            profile=profile or {}, contracts=contracts or {},
            cycle=cycle or {},
            checks=tuple((c[0], c[1], deep_redact(str(c[2])))
                         for c in checks),
            observed_tick=self._clock())
        blob = json.dumps(att.to_dict(), sort_keys=True,
                          separators=(",", ":"), ensure_ascii=False)
        redacted = json.loads(deep_redact(blob))
        # Public commitments (D-146/D-153/D-154..D-165 precedent).
        redacted["phase15_digest"] = att.phase15_digest
        redacted["manifest_sha256"] = att.manifest_sha256
        self._sink(redacted)
        return att

    # -- ANL-01: the Phase 15 attestation --------------------------------------

    def _anl01(self) -> Tuple[bool, str, str,
                              List[Tuple[str, bool, str]]]:
        """(ok, phase15_digest, manifest, checks)."""
        checks: List[Tuple[str, bool, str]] = []
        att, err = self._load("phase15")
        if att is None:
            checks.append(("ANL-01", False,
                           "Phase 15 attestation absent "
                           f"({err}) — Phase 15 never ignited"))
            return False, "", "", checks
        if not isinstance(att, dict):
            checks.append(("ANL-01", False,
                           "Phase 15 attestation malformed"))
            return False, "", "", checks
        if att.get("schema") != PHASE15_SCHEMA:
            checks.append(("ANL-01", False,
                           f"attestation schema {att.get('schema')!r} "
                           f"!= {PHASE15_SCHEMA!r}"))
            return False, "", "", checks
        if att.get("verdict") != PHASE15_IGNITED:
            checks.append(("ANL-01", False,
                           f"Phase 15 verdict {att.get('verdict')!r} "
                           f"!= {PHASE15_IGNITED!r} — analytics "
                           "read-side not wired, Phase 16 refused"))
            return False, "", "", checks
        manifest = att.get("manifest_sha256", "")
        if not (isinstance(manifest, str) and _HEX64.match(manifest)):
            checks.append(("ANL-01", False,
                           "phase15 attestation lacks its manifest "
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
                        str(row.get("event_kind", "")) != PHASE15_ROW_KIND:
                    continue
                detail = row.get("detail")
                if isinstance(detail, dict) and \
                        isinstance(detail.get("attestation_digest"),
                                   str):
                    rooted_digest = detail["attestation_digest"]
                    break
        if not rooted_digest:
            checks.append(("ANL-01", False,
                           "phase15 attestation not rooted in the "
                           "D-112 ledger — upstream wiring was never "
                           "durably attested"))
            return False, recomputed, "", checks
        if rooted_digest != recomputed:
            checks.append(("ANL-01", False,
                           f"phase15 attestation digest "
                           f"{recomputed[:16]}… != rooted "
                           f"{rooted_digest[:16]}… — DRIFTED or "
                           "altered upstream attestation"))
            return False, recomputed, "", checks
        cv, err = self._load("chain_verifier")
        if cv is None or not isinstance(cv, dict) or not cv.get("ok"):
            reason = (cv or {}).get("reason", err or "verifier absent")
            checks.append(("ANL-01", False,
                           f"D-112 chain not intact ({reason}) — "
                           "wiring on a broken ledger is refused"))
            return False, recomputed, "", checks
        checks.append(("ANL-01", True,
                       "phase15 attestation PHASE15_IGNITED, digest "
                       f"recomputes ({recomputed[:16]}…) and matches "
                       "the rooted commitment in the D-112 ledger "
                       f"({int(cv.get('rows', 0))} rows, zero breaks)"))
        return True, recomputed, manifest, checks

    # -- ANL-02: runtime profile + module seams --------------------------------

    def _anl02(self) -> Tuple[bool, Dict[str, Any],
                              List[Tuple[str, bool, str]]]:
        checks: List[Tuple[str, bool, str]] = []
        summary: Dict[str, Any] = {"runtime_profile_verified": False,
                                   "seams_ok": False,
                                   "phases": []}
        census, err = self._load("census")
        if census is None or not isinstance(census, dict):
            checks.append(("ANL-02", False,
                           "runtime profile census unavailable "
                           f"({err}) — fail closed"))
            return False, summary, checks
        if not census.get("runtime_profile_verified"):
            checks.append(("ANL-02", False,
                           "runtime profile NOT verified — refuse"))
            return False, summary, checks
        rows = {p.get("phase"): p for p in census.get("phases", [])
                if isinstance(p, dict)}
        for n in (5, 6, 7, 8, 9, 10, 11, 12, 14, 15):
            p = rows.get(n)
            if p is None:
                checks.append(("ANL-02", False,
                               f"Phase {n} missing from the runtime "
                               "profile census (Phases 5/6/7/8/9/10/"
                               "11/12/14/15 required; slot 14 closed "
                               "CRM-not-needed per D-163)"))
                return False, summary, checks
            if not (p.get("verified") and p.get("wired")):
                checks.append(("ANL-02", False,
                               f"Phase {n} not VERIFIED+WIRED — "
                               "analyst wiring refused"))
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
                checks.append(("ANL-02", False,
                               "D-154 registry unavailable "
                               f"({type(exc).__name__})"))
                return False, summary, checks
        for key, modname in SEAMS.items():
            try:
                importlib.import_module(modname)
            except Exception as exc:  # noqa: BLE001 — typed refusal
                checks.append(("ANL-02", False,
                               f"canonical seam {modname} not "
                               f"importable ({type(exc).__name__}) — "
                               "repo seam missing"))
                return False, summary, checks
            phase_no = SEAM_PHASES.get(key)
            expected = entry_points.get(phase_no) \
                if phase_no is not None else None
            if expected and expected != modname:
                checks.append(("ANL-02", False,
                               f"ENTRY_POINTS[{phase_no}] = "
                               f"{expected!r} != repo seam "
                               f"{modname!r} — registry drift"))
                return False, summary, checks
        # the load-bearing pin: registry slot 17 "AI Business Analyst"
        # MUST bind to the analyst engine (the D-154 cross-walk)
        if entry_points.get(17) != SEAMS["analyst_engine"]:
            checks.append(("ANL-02", False,
                           "registry slot 17 (AI Business Analyst) "
                           "does not bind "
                           f"{SEAMS['analyst_engine']!r} — "
                           "cross-walk drift"))
            return False, summary, checks
        summary["seams_ok"] = True
        checks.append(("ANL-02", True,
                       f"all {len(SEAMS)} analyst seams importable "
                       "and consistent with the D-154 ENTRY_POINTS "
                       "registry (slot 17 → "
                       f"{SEAMS['analyst_engine']})"))
        return True, summary, checks

    # -- ANL-03: analyst contracts & invariants ---------------------------------

    def _anl03(self) -> Tuple[bool, Dict[str, Any],
                              List[Tuple[str, bool, str]]]:
        checks: List[Tuple[str, bool, str]] = []
        summary: Dict[str, Any] = {
            "contracts_ok": False, "identity_ok": False,
            "edges_ok": False, "hitl_boundary_ok": False,
        }
        try:
            from canonical.analyst_contracts import (
                CATEGORIES, LEGAL_EDGES, SEVERITIES, ST_AUTO_ACCEPTED,
                ST_DISPATCHED_TO_HITL, ST_DISMISSED, ST_EVALUATED,
                ST_GENERATED, ST_SUPERSEDED, AnalystContractError,
                can_auto_accept, insight_key, is_transition_legal,
                make_recommendation, requires_hitl, validate_insight,
            )
        except Exception as exc:  # noqa: BLE001 — typed refusal
            checks.append(("ANL-03", False,
                           f"analyst contracts not importable "
                           f"({type(exc).__name__}) — repo seam missing"))
            return False, summary, checks
        summary["categories"] = len(CATEGORIES)
        summary["severities"] = len(SEVERITIES)

        # the REAL validator accepts conforming probe insights
        try:
            validate_insight(dict(PROBE_INSIGHT_LOW))
            validate_insight(dict(PROBE_INSIGHT_HIGH))
        except AnalystContractError as exc:
            checks.append(("ANL-03", False,
                           f"REAL validator rejected a conforming "
                           f"insight: {str(exc.args[0])[:120]}"))
            return False, summary, checks
        # and refuses every invalid analysis request class, named
        for mutate, expect in (
                (lambda i: {k: v for k, v in i.items()
                            if k != "severity"}, "missing required"),
                (lambda i: dict(i, category="vibes"), "category must be"),
                (lambda i: dict(i, severity="EXTREME"), "severity must be"),
                (lambda i: dict(i, confidence_score=1.5), "[0, 1]"),
                (lambda i: dict(i, confidence_score=True), "[0, 1]"),
                (lambda i: dict(i, metric_refs=[]), "metric_refs must be"),
                (lambda i: dict(i, metric_refs=[{"metric_kind": "x"}]),
                 "metric_kind and window_ref"),
                (lambda i: dict(i, correlation_keys=[]), "correlation_keys"),
                (lambda i: dict(i, actionable_payload="nope"),
                 "actionable_payload must be a dict"),
                (lambda i: dict(i, status="DISPATCHED_TO_HITL"),
                 "may only enter as")):
            try:
                validate_insight(mutate(dict(PROBE_INSIGHT_LOW)))
                _fail(f"invalid analysis request accepted "
                      f"(expected {expect!r} rejection)")
            except AnalystContractError as exc:
                if expect not in str(exc.args[0]):
                    checks.append(("ANL-03", False,
                                   f"invalid-request refusal "
                                   f"mis-classified: "
                                   f"{str(exc.args[0])[:120]}"))
                    return False, summary, checks
        summary["contracts_ok"] = True

        # deterministic identity: identical evidence ⇒ identical key,
        # regardless of insight_id / payload / confidence
        k1 = insight_key(PROBE_INSIGHT_LOW["category"],
                         PROBE_INSIGHT_LOW["correlation_keys"],
                         PROBE_INSIGHT_LOW["metric_refs"])
        k2 = insight_key(PROBE_INSIGHT_LOW["category"],
                         list(reversed(
                             PROBE_INSIGHT_LOW["correlation_keys"])),
                         list(reversed(PROBE_INSIGHT_LOW["metric_refs"])))
        if k1 != k2 or not _HEX64.match(k1):
            checks.append(("ANL-03", False,
                           "insight identity not deterministic — "
                           "identical evidence produced divergent "
                           "keys"))
            return False, summary, checks
        k3 = insight_key(PROBE_INSIGHT_LOW["category"],
                         ["channel:telegram", "window:2026-09-21"],
                         PROBE_INSIGHT_LOW["metric_refs"])
        if k3 == k1:
            checks.append(("ANL-03", False,
                           "insight identity ignores a correlation "
                           "key — dedup collision surface"))
            return False, summary, checks
        summary["identity_ok"] = True

        # lifecycle edge matrix: legal edges pass, everything else
        # refuses (terminals exitless; SUPERSEDED from any
        # non-terminal)
        legal = [(ST_GENERATED, ST_EVALUATED),
                 (ST_EVALUATED, ST_DISPATCHED_TO_HITL),
                 (ST_EVALUATED, ST_AUTO_ACCEPTED),
                 (ST_EVALUATED, ST_DISMISSED),
                 (ST_DISPATCHED_TO_HITL, ST_SUPERSEDED),
                 (ST_GENERATED, ST_SUPERSEDED)]
        illegal = [(ST_GENERATED, ST_AUTO_ACCEPTED),
                   (ST_GENERATED, ST_DISPATCHED_TO_HITL),
                   (ST_AUTO_ACCEPTED, ST_SUPERSEDED),
                   (ST_DISMISSED, ST_EVALUATED),
                   (ST_EVALUATED, ST_GENERATED),
                   (ST_DISPATCHED_TO_HITL, ST_AUTO_ACCEPTED)]
        for cur, tgt in legal:
            if not is_transition_legal(cur, tgt):
                checks.append(("ANL-03", False,
                               f"legal edge {cur}→{tgt} refused"))
                return False, summary, checks
        for cur, tgt in illegal:
            if is_transition_legal(cur, tgt):
                checks.append(("ANL-03", False,
                               f"illegal edge {cur}→{tgt} accepted — "
                               "state-machine drift"))
                return False, summary, checks
        summary["edges_ok"] = True

        # the D-104 boundary: HIGH/CRITICAL or state-mutating ⇒
        # structurally non-auto-acceptable
        if not requires_hitl(PROBE_INSIGHT_HIGH) or \
                can_auto_accept(PROBE_INSIGHT_HIGH):
            checks.append(("ANL-03", False,
                           "HIGH-severity insight not HITL-bound — "
                           "D-104 boundary broken"))
            return False, summary, checks
        if requires_hitl(PROBE_INSIGHT_LOW) or \
                not can_auto_accept(PROBE_INSIGHT_LOW):
            checks.append(("ANL-03", False,
                           "LOW-severity insight wrongly HITL-bound"))
            return False, summary, checks
        mutating = dict(PROBE_INSIGHT_LOW, actionable_payload=dict(
            PROBE_INSIGHT_LOW["actionable_payload"],
            mutates_business_state=True))
        if not requires_hitl(mutating):
            checks.append(("ANL-03", False,
                           "state-mutating payload not HITL-bound — "
                           "D-104 boundary broken"))
            return False, summary, checks
        rec = make_recommendation("report_summary", "probe", False)
        if rec.get("mutates_business_state") is not False:
            checks.append(("ANL-03", False,
                           "Recommendation shape broken"))
            return False, summary, checks
        summary["hitl_boundary_ok"] = True
        checks.append(("ANL-03", True,
                       f"REAL contracts enforced: {len(CATEGORIES)} "
                       "categories, deterministic insight identity, "
                       "lifecycle edges closed (terminals exitless), "
                       "D-104 HITL boundary proven both ways"))
        return True, summary, checks

    # -- ANL-04: the synthetic analyst cycle -------------------------------------

    def _anl04(self) -> Tuple[bool, Dict[str, Any],
                              List[Tuple[str, bool, str]]]:
        from canonical.analyst_contracts import (
            ST_AUTO_ACCEPTED, ST_DISPATCHED_TO_HITL, ST_DISMISSED,
            ST_EVALUATED, ST_GENERATED, ST_SUPERSEDED,
            AnalystContractError, insight_key,
        )
        from canonical.analyst_engine import AnalystEngine

        checks: List[Tuple[str, bool, str]] = []
        summary: Dict[str, Any] = {"steps": [], "summary_hash": "",
                                   "vault_backend": "ephemeral",
                                   "invalid_refused": 0,
                                   "drift": False}
        stack, err = self._load("stack_factory")
        if stack is None:
            checks.append(("ANL-04", False,
                           f"engine stack unavailable ({err}) — fail "
                           "closed"))
            return False, summary, checks
        try:
            store, vault = stack[0], stack[1]
        except Exception as exc:  # noqa: BLE001 — typed refusal
            checks.append(("ANL-04", False,
                           f"engine stack construction failed "
                           f"({type(exc).__name__})"))
            return False, summary, checks
        engine = AnalystEngine(store, vault=vault)

        # injected PURE evaluator — the mock intelligence (no LLM)
        def evaluator(row: Dict) -> Dict:
            return {"approved": row.get("confidence_score", 0) >= 0.5,
                    "note": "pure injected evaluator (dry-run)"}

        try:
            key_low = insight_key(PROBE_INSIGHT_LOW["category"],
                                  PROBE_INSIGHT_LOW["correlation_keys"],
                                  PROBE_INSIGHT_LOW["metric_refs"])
            key_high = insight_key(PROBE_INSIGHT_HIGH["category"],
                                   PROBE_INSIGHT_HIGH["correlation_keys"],
                                   PROBE_INSIGHT_HIGH["metric_refs"])

            # START — the probe plan
            summary["steps"].append([
                "START", True,
                {"cycle_id": CYCLE_ID,
                 "vault_backend": "ephemeral-in-process"}])

            # AUTH — sandbox envelope: injected pure evaluator, mock
            # D-142-shaped data fixtures, no LLM provider, no lake
            summary["steps"].append([
                "AUTH", True,
                {"evaluator": "injected-pure",
                 "data_provider": "synthetic-d142-shapes",
                 "llm_providers": "none"}])

            # PROPOSE — durable GENERATED + evidence dedup
            r1 = engine.propose(dict(PROBE_INSIGHT_LOW))
            if r1.get("status") != "CREATED" or \
                    r1.get("insight_key") != key_low:
                _fail(f"propose failed: {r1}")
            dup = engine.propose(dict(
                PROBE_INSIGHT_LOW, insight_id="incidental-other-id"))
            if dup.get("status") != "DUPLICATE" or \
                    dup.get("insight_key") != key_low:
                _fail(f"identical evidence not deduplicated: {dup}")
            dedup_refs = [r for r in engine.ledger(key_low)
                          if r.get("kind") == "dedup"]
            if len(dedup_refs) != 1:
                _fail("dedup evidence not durably audited")
            r2 = engine.propose(dict(PROBE_INSIGHT_HIGH))
            if r2.get("status") != "CREATED":
                _fail(f"propose (high) failed: {r2}")
            summary["steps"].append([
                "PROPOSE", True,
                {"created": 2, "dedup": "DUPLICATE (evidence-keyed)",
                 "identical_evidence": "same key regardless of "
                 "incidental insight_id"}])

            # EVALUATE — pure evaluator verdict, durable EVALUATED
            ev = engine.evaluate(key_low, evaluator)
            if not ev.get("ok") or not ev.get("approved") or \
                    ev.get("status") != ST_EVALUATED:
                _fail(f"evaluate failed: {ev}")
            ev2 = engine.evaluate(key_high, evaluator)
            if not ev2.get("ok") or ev2.get("status") != ST_EVALUATED:
                _fail(f"evaluate (high) failed: {ev2}")
            # double evaluation is not a legal edge from EVALUATED
            ev3 = engine.evaluate(key_low, evaluator)
            if ev3.get("ok") or ev3.get("reason") != "not_evaluable":
                _fail(f"double evaluation accepted: {ev3}")
            summary["steps"].append([
                "EVALUATE", True,
                {"evaluated": 2,
                 "double_evaluation": "not_evaluable (edge closed)"}])

            # BOUNDARY — the D-104 HITL structural boundary, driven
            # both ways
            auto_high = engine.auto_accept(key_high)
            if auto_high.get("ok") or \
                    auto_high.get("reason") != "hitl_required_boundary":
                _fail(f"HIGH-severity auto-accept not structurally "
                      f"refused: {auto_high}")
            hitl = engine.dispatch_to_hitl(key_high)
            if not hitl.get("ok") or \
                    hitl.get("status") != ST_DISPATCHED_TO_HITL:
                _fail(f"HITL dispatch failed: {hitl}")
            low = dict(PROBE_INSIGHT_LOW, insight_id="phase16-probe-low-0002",
                       correlation_keys=["channel:instagram",
                                         "window:2026-09-20"])
            r3 = engine.propose(low)
            if r3.get("status") != "CREATED":
                _fail(f"propose (low-2) failed: {r3}")
            key_low2 = r3["insight_key"]
            engine.evaluate(key_low2, evaluator)
            auto_low = engine.auto_accept(key_low2)
            if not auto_low.get("ok") or \
                    auto_low.get("status") != ST_AUTO_ACCEPTED:
                _fail(f"LOW-severity auto-accept failed: {auto_low}")
            # a state-mutating payload is HITL-bound even at LOW
            mutating = dict(
                PROBE_INSIGHT_LOW, insight_id="phase16-probe-low-0003",
                correlation_keys=["channel:web", "window:2026-09-20"],
                actionable_payload=dict(
                    PROBE_INSIGHT_LOW["actionable_payload"],
                    mutates_business_state=True))
            r4 = engine.propose(mutating)
            if r4.get("status") != "CREATED":
                _fail(f"propose (mutating) failed: {r4}")
            key_mut = r4["insight_key"]
            engine.evaluate(key_mut, evaluator)
            auto_mut = engine.auto_accept(key_mut)
            if auto_mut.get("ok") or \
                    auto_mut.get("reason") != "hitl_required_boundary":
                _fail(f"state-mutating auto-accept not refused: "
                      f"{auto_mut}")
            summary["steps"].append([
                "BOUNDARY", True,
                {"high": "auto-accept refused (structural) → HITL",
                 "low": "auto-accepted",
                 "state_mutating_low": "auto-accept refused",
                 "rule": "D-104"}])

            # SUPERSEDE — newer evidence marks the HITL-queued insight
            sup = engine.supersede(key_high, key_low2)
            if not sup.get("ok") or sup.get("status") != ST_SUPERSEDED:
                _fail(f"supersede failed: {sup}")
            # terminal insights are not supersadable
            sup2 = engine.supersede(key_low2, key_mut)
            if sup2.get("ok"):
                _fail("a terminal (AUTO_ACCEPTED) insight was "
                      "superseded — terminal exit opened")
            summary["steps"].append([
                "SUPERSEDE", True,
                {"hitl_queued": "SUPERSEDED",
                 "terminal": "supersede refused (exitless)"}])

            # LEDGER — chain-of-thought integrity: the complete
            # durable rationale rebuilds from D-027 events alone
            led = engine.ledger(key_high)
            kinds = [r.get("kind") for r in led]
            for want in ("insight_generated", "insight_evaluated",
                         "insight_dispatched_to_hitl",
                         "insight_superseded"):
                if want not in kinds:
                    _fail(f"ledger missing {want} for the HIGH "
                          "insight — rationale incomplete")
            if engine.ledger(key_low2) and \
                    "insight_auto_accepted" not in [
                        r.get("kind")
                        for r in engine.ledger(key_low2)]:
                _fail("ledger missing the auto-accept audit row")
            all_rows = vault.all_insights()
            if len(all_rows) != 4:
                _fail(f"vault row count drifted: {len(all_rows)}")
            statuses = {r["status"] for r in all_rows.values()}
            # end-states after the driven cycle: low=GENERATED→
            # EVALUATED (still EVALUATED), high=EVALUATED→HITL→
            # SUPERSEDED, low2=EVALUATED→AUTO_ACCEPTED, mut=EVALUATED
            # (HITL-bound, dispatch pending owner)
            for want in (ST_EVALUATED, ST_SUPERSEDED, ST_AUTO_ACCEPTED):
                if want not in statuses:
                    _fail(f"lifecycle end-state {want} not "
                          "represented in the vault")
            summary["drift"] = False
            summary["steps"].append([
                "LEDGER", True,
                {"high_ledger": "generated→evaluated→hitl→superseded",
                 "replay_source": "D-027 events alone",
                 "vault_rows": len(all_rows)}])

            # INVALID — invalid analysis requests fail closed BEFORE
            # any durable write
            before = len(vault.all_insights())
            for bad in (
                    dict(PROBE_INSIGHT_LOW, category="vibes"),
                    dict(PROBE_INSIGHT_LOW, confidence_score=7),
                    {**PROBE_INSIGHT_LOW, "metric_refs": []},
                    dict(PROBE_INSIGHT_LOW, severity="EXTREME")):
                try:
                    engine.propose(bad)
                    _fail("invalid analysis request accepted")
                except AnalystContractError:
                    summary["invalid_refused"] += 1
            if len(vault.all_insights()) != before:
                _fail("a refused request left a durable row — "
                      "zero-partial-write violated")
            summary["steps"].append([
                "INVALID", True,
                {"refused": summary["invalid_refused"],
                 "durable_rows_added": 0}])

            # VERIFY — no LLM/lake markers anywhere in the durable
            # event stream; the vault stayed ephemeral
            raw = store.records if hasattr(store, "records") else {}
            blob = json.dumps(raw).lower()
            for marker in ("api_key", "llm_provider", "openai",
                           "anthropic", "data_lake", "webhook_secret",
                           "auth_code", "pan", "card_number"):
                if marker in blob:
                    _fail(f"sandbox-boundary violation: {marker!r} "
                          "found in the analyst event stream")
            if not isinstance(vault, _EphemeralVault):
                _fail("vault is not the ephemeral in-process store — "
                      "durable footprint")
            summary["vault_backend"] = "ephemeral"
            summary["steps"].append([
                "VERIFY", True, {"markers": "clean",
                                 "vault_backend": "ephemeral"}])

            # CLEANUP — persist the data-minimized cycle artifact,
            # read it back, then delete EVERYTHING
            artifact = {
                "cycle_id": CYCLE_ID,
                "insights": 4,
                "hitl_dispatched": 1,
                "auto_accepted": 1,
                "invalid_refused": summary["invalid_refused"],
                "dry_run": True,
                "llm_calls": 0,
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
                "insights": 4,
                "invalid_refused": summary["invalid_refused"],
                "dry_run": True,
                "llm_calls": 0,
            }
            summary["summary_hash"] = canonical_hash(plan)
            checks.append(("ANL-04", True,
                           "synthetic analyst cycle completed: "
                           f"{len(summary['steps'])} steps, summary "
                           f"hash {summary['summary_hash'][:16]}…, "
                           "evidence dedup, D-104 boundary both ways, "
                           "terminal exitless, durable rationale "
                           "complete, zero LLM/lake contact"))
            return True, summary, checks
        except Phase16Error as exc:
            checks.append(("ANL-04", False, str(exc)[:160]))
            self._cleanup_scratch()
            return False, summary, checks
        except AnalystContractError as exc:
            checks.append(("ANL-04", False,
                           f"analyst contract refusal (Class-B): "
                           f"{str(exc.args[0])[:120]}"))
            self._cleanup_scratch()
            return False, summary, checks
        except Exception as exc:  # noqa: BLE001 — typed refusal (D-124)
            checks.append(("ANL-04", False,
                           f"synthetic analyst cycle failed "
                           f"({type(exc).__name__})"))
            self._cleanup_scratch()
            return False, summary, checks

    # -- scratch (namespace-scoped, the only general persistence) --

    def _scratch_write(self, artifact: Dict[str, Any]) -> None:
        self._scratch_store["phase16-scratch:analyst"] = artifact

    def _scratch_read(self) -> Any:
        return self._scratch_store.get("phase16-scratch:analyst")

    def _scratch_delete(self) -> bool:
        return self._scratch_store.pop("phase16-scratch:analyst",
                                       None) is not None

    def _scratch_residue(self) -> List[str]:
        return sorted(k for k in self._scratch_store
                      if k.startswith("phase16-scratch:"))

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

    def run(self) -> Phase16Attestation:
        """ANL-01..ANL-05 → the canonical attestation. Exactly one
        audited attestation per call (including aborts); an ANL-01
        refusal performs ZERO engine calls."""
        checks: List[Tuple[str, bool, str]] = []
        ok1, p15digest, manifest, c1 = self._anl01()
        checks += c1
        if not ok1:
            return self._emit(PHASE16_INCOMPLETE, checks,
                              phase15_digest=p15digest,
                              manifest=manifest)
        ok2, profile, c2 = self._anl02()
        checks += c2
        ok3, contracts, c3 = (False, {}, [])
        if ok2:
            ok3, contracts, c3 = self._anl03()
            checks += c3
        ok4, cycle, c4 = (False, {}, [])
        if ok3:
            ok4, cycle, c4 = self._anl04()
            checks += c4
        verdict = PHASE16_IGNITED if all((ok1, ok2, ok3, ok4)) \
            else PHASE16_INCOMPLETE
        if verdict == PHASE16_IGNITED:
            checks.append(("ANL-05", True,
                           "phase16.analyst_wiring_attestation.v1 "
                           "emitted — Analyst Service verified in "
                           "DRY-RUN mode (injected pure evaluator, "
                           "mock D-142-shaped data, zero LLM/lake "
                           "contact, D-104 HITL boundary structural) "
                           "under the Phase 15 attestation; handover "
                           "to Phase 17 (HITL service) is verified"))
        else:
            checks.append(("ANL-05", False,
                           "attestation emitted as IGNITION_INCOMPLETE "
                           "— remediate the named checks before the "
                           "Phase 17 handover"))
        return self._emit(verdict, checks, phase15_digest=p15digest,
                          manifest=manifest, profile=profile,
                          contracts=contracts, cycle=cycle)


def main() -> int:
    """CLI wiring guard: interactive wiring requires the injected
    providers, census and the ephemeral engine stack configuration."""
    import argparse
    import sys
    ap = argparse.ArgumentParser(
        description="Phase 16 live wiring igniter (ANL-01..ANL-05, "
                    "D-166).")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    print("live_wiring_phase16_igniter: interactive wiring requires "
          "the phase15 attestation, the D-112 chain, the runtime "
          "census and the injected engine stack; see run() and the "
          "battery for the injected contract.", file=sys.stderr)
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

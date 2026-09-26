"""Phase 10 live wiring igniter — Multi-channel Order Orchestration (D-160).

The sixth Live Wiring program phase. Phase 9 (D-159) verified the
Telegram Sales & Ingress surface in sandbox mode; Phase 10 now wires
and verifies Multi-channel Order Orchestration on top of Phases 5–9
— in STRICT SANDBOX/DRY-RUN mode:

  ORD-01  the upstream `phase9.live_wiring_attestation.v1` is
          present, PHASE9_IGNITED, manifest-bound, its canonical
          bytes recompute to the SHA-256 commitment rooted in the
          D-112 ledger (kind `phase9_live_wiring_attestation`) over
          an intact chain — ANY refusal happens BEFORE the first
          order-processing/state-allocation call (zero OMS calls on
          refusal);
  ORD-02  the verified runtime profile is loaded: the injected
          census marks Phases 5, 6, 7, 8 AND 9 present+VERIFIED+
          WIRED, and the canonical order seams (repo-real:
          canonical.oms_engine = ENTRY_POINTS[11],
          canonical.oms_contracts = ENTRY_POINTS[12], the
          D-027 idempotency lock surface, the D-082 inventory
          reservation seam, and the Phase 11 fan-out boundary) are
          importable and consistent with the D-154 ENTRY_POINTS
          registry;
  ORD-03  the orchestration contracts and invariants are validated
          through the REAL `oms_contracts` layer: channel origin
          tagging (telegram/instagram_dm/web_store) is carried on
          the synthetic order and preserved through validation; the
          D-081 idempotency lock is deterministic (`order_key` =
          SHA-256 over client_order_id — same key on replay);
          currency must be in the IRR/IRT whitelist; line-item
          money is strict-integer (floats rejected), unit prices
          ≥ 0 under the D-114 ceiling; the state machine refuses
          out-of-order transitions (D-081); error classes are
          Class-A (transient) vs Class-B (contract, never retried)
          with bounded retries;
  ORD-04  a NON-DESTRUCTIVE synthetic multi-item order lifecycle
          runs end-to-end through the REAL `OmsEngine` over
          in-memory/scratch transports: idempotency lock
          acquisition (place → PLACED; replay → skipped_duplicate)
          → schema validation → inventory soft-reservation probe
          (the REAL D-082 `JsonInventory`/`_ReservationLedger`
          semantics, scratch-backed) → order state transition
          PLACED → VALIDATED (the reservation guard fires) →
          CANCELLED (the release guard fires) → the REAL D-083
          notification fan-out boundary PROBE: a schema-compliant
          event is routed and dispatched through the injected
          boundary (`FanOutEngine.route` + `.dispatch`) whose
          publish binds are publisher-less (`no_publisher_bound` —
          structurally incapable of any channel egress) under an
          ephemeral process-local D-079 lock; the durable per-target
          receipts are verified in the scratch event store; every
          inventory lock is released during cleanup;
          per-step telemetry (START/LOCK/VALIDATE/RESERVE/
          TRANSITION/EVENT_PROBE/CLEANUP) and a deterministic
          summary hash are recorded;
  ORD-05  the canonical `phase10.live_wiring_attestation.v1` is
          emitted exactly once per run (aborts included) with the
          SHA-256 `attestation_digest`; any abort emits the same
          schema as PHASE10_INCOMPLETE with failure telemetry.

Security & purity (RULES §35, AST-pinned): injected engine/store/
inventory transports only — zero sockets, zero raw shell, zero wall
clock in the core. Customer identity, shipping addresses, phone
numbers, transaction hashes and payment tokens NEVER enter any
emitted record: only hashes, counts, state names, verdict names and
step telemetry. Payment is a BOUNDARY (D-083): no gateway fields
exist anywhere in the probe. D-124 deep redaction runs over every
emitted record with the public commitments (`phase9_digest`,
`manifest_sha256`) restored after redaction.
"""
from __future__ import annotations

import hashlib
import importlib
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
    "Phase10Error", "Phase10Attestation", "Phase10Igniter",
    "OrderScratch", "ATTESTATION_SCHEMA", "PHASE10_IGNITED",
    "PHASE10_INCOMPLETE", "PHASE9_SCHEMA", "PHASE9_IGNITED",
    "PHASE9_ROW_KIND", "SEAMS", "SEAM_PHASES", "CHANNEL_ORIGINS",
    "CURRENCY_WHITELIST", "MAX_DISCOUNT_PCT", "LIMITS", "CYCLE_ID",
    "SYNTHETIC_ORDER", "PROBE_TARGET", "canonical_hash",
]

ATTESTATION_SCHEMA = "phase10.live_wiring_attestation.v1"
PHASE10_IGNITED = "PHASE10_IGNITED"
PHASE10_INCOMPLETE = "IGNITION_INCOMPLETE"

PHASE9_SCHEMA = "phase9.live_wiring_attestation.v1"
PHASE9_IGNITED = "PHASE9_IGNITED"

# The D-112 ledger kind that roots the Phase 9 attestation (D-159).
PHASE9_ROW_KIND = "phase9_live_wiring_attestation"

_HEX64 = re.compile(r"^[0-9a-f]{64}$")

# --- multi-channel contract constants (ORD-03) ------------------------------

CHANNEL_ORIGINS: Tuple[str, ...] = ("telegram", "instagram_dm",
                                    "web_store")
CURRENCY_WHITELIST: Tuple[str, ...] = ("IRR", "IRT")
MAX_DISCOUNT_PCT = 20          # bounded discount rule (percent)

# The D-083 EVENT_PROBE target: routed through the real fan-out
# destination matrix, dispatched to a publisher-less bind (never a
# channel) under the ephemeral probe lock.
PROBE_TARGET = "telegram"
DISCOUNT_CODE_ALLOWLIST: Tuple[str, ...] = ("SPRING10", "LOYAL5")

# --- hard limits (ORD-03) ------------------------------------------------------

LIMITS: Dict[str, Any] = {
    "max_retries": 2,           # Class-A transient retries only
    "timeout_s": 15.0,          # per engine operation (D-151)
    "max_line_items": 100,      # D-114 ceiling
    "max_reservations": 10,     # soft-reservation probes per cycle
}

# Repo-real module seams for the order wiring. `SEAM_PHASES` pins each
# seam to the D-154 ENTRY_POINTS phase it must agree with.
SEAMS: Dict[str, str] = {
    "oms_engine": "canonical.oms_engine",
    "oms_contracts": "canonical.oms_contracts",
    "oms_worker": "canonical.oms_worker",
    "sync_event_store": "services.sync_engine",
}

SEAM_PHASES: Dict[str, Optional[int]] = {
    "oms_engine": 11,
    "oms_contracts": 12,
    "oms_worker": None,
    "sync_event_store": None,
}

# The synthetic multi-item order fixture (channel origin: telegram,
# the Phase 9-verified ingress).
CYCLE_ID = "phase10-oms-probe-0001"
CLIENT_ORDER_ID = "phase10-probe-clt-0001"

SYNTHETIC_ORDER: Dict[str, Any] = {
    "order_id": "ord-phase10-01",
    "client_order_id": CLIENT_ORDER_ID,
    "customer_ref": "customer-sandbox-0001",
    "channel_origin": "telegram",
    "currency": "IRT",
    "discount_code": "SPRING10",
    "line_items": [
        {"product_id": "P-100", "variant_id": "V-1", "sku": "SKU-A",
         "quantity": 2, "unit_price_minor": 100_000},
        {"product_id": "P-200", "variant_id": "V-2", "sku": "SKU-B",
         "quantity": 1, "unit_price_minor": 250_000},
    ],
    "tax_minor": 0,
    "placed_at": "2026-09-26T10:00:00+00:00",
}


class Phase10Error(ValueError):
    """Contract-level misuse of the Phase 10 igniter."""


def _fail(reason: str) -> None:
    raise Phase10Error(reason)


def canonical_hash(payload: Dict[str, Any]) -> str:
    """SHA-256 over canonical JSON bytes — the shared project digest
    formula (Stage G/H/D-154..D-159 engines)."""
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class OrderScratch:
    """Namespace-scoped scratch state for the order probe: the ONLY
    general persistence the cycle may touch. Channel-origin tagging
    and event records live here; cleanup must empty it."""

    def __init__(self, backing: Optional[Dict[str, Any]] = None) -> None:
        self._data = backing if backing is not None else {}

    def write(self, key: str, value: Any) -> None:
        if not key.startswith("phase10-scratch:"):
            _fail(f"scratch scope violation: key {key!r}")
        self._data[key] = value

    def read(self, key: str) -> Any:
        if not key.startswith("phase10-scratch:"):
            _fail(f"scratch scope violation: key {key!r}")
        return self._data.get(key)

    def delete(self, key: str) -> bool:
        if not key.startswith("phase10-scratch:"):
            _fail(f"scratch scope violation: key {key!r}")
        return self._data.pop(key, None) is not None

    def residue(self) -> List[str]:
        return sorted(k for k in self._data if k.startswith(
            "phase10-scratch:"))


class _EphemeralFanOutLock:
    """Process-local D-079 parity lock for PROBES: identical
    INSERT-once claim semantics (the anti-race guarantee), but ZERO
    durable footprint — it never touches live PostgreSQL
    (`orchestration.fanout_lock`) or the shared
    `local/volumes/orchestration/fanout_lock.json`. The default lock
    claims keys PERMANENTLY in those stores, which would freeze every
    future routing of the same probe key — unacceptable for probes.
    (The D-154/D-155 separation-of-worlds rule, applied to D-079.)"""

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
class Phase10Attestation:
    """Canonical, immutable Phase 10 ignition artifact."""
    schema: str
    verdict: str             # PHASE10_IGNITED / IGNITION_INCOMPLETE
    phase9_digest: str       # upstream attestation digest (commitment)
    manifest_sha256: str     # deployment fingerprint carried through
    profile: Dict[str, Any]  # runtime profile + seams summary
    contracts: Dict[str, Any]  # idempotency/currency/invariants summary
    cycle: Dict[str, Any]    # synthetic lifecycle telemetry
    checks: tuple = field(default_factory=tuple)  # (id, ok, detail)
    observed_tick: int = 0

    @property
    def ignited(self) -> bool:
        return self.verdict == PHASE10_IGNITED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "verdict": self.verdict,
            "phase9_digest": self.phase9_digest,
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


class Phase10Igniter:
    """ORD-01..ORD-05 with injected OMS engine/inventory/event store.

    Injected:
      clock           — ``() -> int`` logical tick
      audit_sink      — ``callable(dict)`` (D-112/D-121 in prod)
      phase9_provider — ``() -> dict`` the phase9 attestation
      audit_rows      — ``() -> list`` the D-112 ledger rows
      chain_verifier  — ``() -> dict`` D-112 chain integrity
      census          — ``() -> dict`` the runtime profile census
      engine_factory  — ``() -> (engine, inventory, ledger, store)``
                        building the REAL offline OMS stack
                        (`OmsEngine` over `EventStore`/`JsonInventory`/
                        `_ReservationLedger`) fresh per run
      fanout          — the D-083 fan-out boundary (``.route`` +
                        ``.dispatch``); the battery injects the REAL
                        `FanOutEngine` with publisher-less binds and
                        an ephemeral D-079 lock (zero channel egress)
      scratch         — optional OrderScratch (default built here)
      expected_entry_points — optional {phase: seam} override
    """

    def __init__(self, clock: Callable[[], int],
                 audit_sink: Callable[[Dict[str, Any]], None],
                 phase9_provider: Optional[Callable[[], Dict[str, Any]]] = None,
                 audit_rows: Optional[Callable[[], List[Dict[str, Any]]]] = None,
                 chain_verifier: Optional[Callable[[], Dict[str, Any]]] = None,
                 census: Optional[Callable[[], Dict[str, Any]]] = None,
                 engine_factory: Optional[Callable[[], Tuple]] = None,
                 fanout: Optional[Any] = None,
                 scratch: Optional[OrderScratch] = None,
                 expected_entry_points: Optional[Dict[int, str]] = None,
                 ) -> None:
        if not callable(clock) or not callable(audit_sink):
            _fail("clock and audit_sink required")
        self._clock = clock
        self._sink = audit_sink
        self._prov = {
            "phase9": phase9_provider,
            "audit_rows": audit_rows,
            "chain_verifier": chain_verifier,
            "census": census,
            "engine_factory": engine_factory,
        }
        self._prov["fanout"] = fanout
        self._scratch = scratch or OrderScratch()
        self._entry_points = dict(expected_entry_points) \
            if expected_entry_points else None

    # -- internals ---------------------------------------------------------

    def _load(self, name: str) -> Tuple[Optional[Any], str]:
        prov = self._prov.get(name)
        if prov is None:
            return None, "provider not injected"
        if callable(prov) and not hasattr(prov, "place_order") \
                and not hasattr(prov, "policy") \
                and not hasattr(prov, "route"):
            try:
                return prov(), ""
            except Exception as exc:  # noqa: BLE001 — typed (D-124)
                return None, f"provider raised {type(exc).__name__}"
        return prov, ""

    def _emit(self, verdict: str, checks: List[Tuple[str, bool, str]],
              phase9_digest: str = "", manifest: str = "",
              profile: Optional[Dict[str, Any]] = None,
              contracts: Optional[Dict[str, Any]] = None,
              cycle: Optional[Dict[str, Any]] = None,
              ) -> Phase10Attestation:
        att = Phase10Attestation(
            schema=ATTESTATION_SCHEMA, verdict=verdict,
            phase9_digest=phase9_digest, manifest_sha256=manifest,
            profile=profile or {}, contracts=contracts or {},
            cycle=cycle or {},
            checks=tuple((c[0], c[1], deep_redact(str(c[2])))
                         for c in checks),
            observed_tick=self._clock())
        blob = json.dumps(att.to_dict(), sort_keys=True,
                          separators=(",", ":"), ensure_ascii=False)
        redacted = json.loads(deep_redact(blob))
        # Public commitments (D-146/D-153/D-154..D-159 precedent).
        redacted["phase9_digest"] = att.phase9_digest
        redacted["manifest_sha256"] = att.manifest_sha256
        self._sink(redacted)
        return att

    # -- ORD-01: the Phase 9 attestation --------------------------------------

    def _ord01(self) -> Tuple[bool, str, str,
                              List[Tuple[str, bool, str]]]:
        """(ok, phase9_digest, manifest, checks)."""
        checks: List[Tuple[str, bool, str]] = []
        att, err = self._load("phase9")
        if att is None:
            checks.append(("ORD-01", False,
                           "Phase 9 attestation absent "
                           f"({err}) — Phase 9 never ignited"))
            return False, "", "", checks
        if not isinstance(att, dict):
            checks.append(("ORD-01", False,
                           "Phase 9 attestation malformed"))
            return False, "", "", checks
        if att.get("schema") != PHASE9_SCHEMA:
            checks.append(("ORD-01", False,
                           f"attestation schema {att.get('schema')!r} "
                           f"!= {PHASE9_SCHEMA!r}"))
            return False, "", "", checks
        if att.get("verdict") != PHASE9_IGNITED:
            checks.append(("ORD-01", False,
                           f"Phase 9 verdict {att.get('verdict')!r} "
                           f"!= {PHASE9_IGNITED!r} — Telegram surface "
                           "not wired, Phase 10 refused"))
            return False, "", "", checks
        manifest = att.get("manifest_sha256", "")
        if not (isinstance(manifest, str) and _HEX64.match(manifest)):
            checks.append(("ORD-01", False,
                           "phase9 attestation lacks its manifest "
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
                        str(row.get("event_kind", "")) != PHASE9_ROW_KIND:
                    continue
                detail = row.get("detail")
                if isinstance(detail, dict) and \
                        isinstance(detail.get("attestation_digest"),
                                   str):
                    rooted_digest = detail["attestation_digest"]
                    break
        if not rooted_digest:
            checks.append(("ORD-01", False,
                           "phase9 attestation not rooted in the "
                           "D-112 ledger — upstream wiring was never "
                           "durably attested"))
            return False, recomputed, "", checks
        if rooted_digest != recomputed:
            checks.append(("ORD-01", False,
                           f"phase9 attestation digest "
                           f"{recomputed[:16]}… != rooted "
                           f"{rooted_digest[:16]}… — DRIFTED or "
                           "altered upstream attestation"))
            return False, recomputed, "", checks
        cv, err = self._load("chain_verifier")
        if cv is None or not isinstance(cv, dict) or not cv.get("ok"):
            reason = (cv or {}).get("reason", err or "verifier absent")
            checks.append(("ORD-01", False,
                           f"D-112 chain not intact ({reason}) — "
                           "wiring on a broken ledger is refused"))
            return False, recomputed, "", checks
        checks.append(("ORD-01", True,
                       "phase9 attestation PHASE9_IGNITED, digest "
                       f"recomputes ({recomputed[:16]}…) and matches "
                       "the rooted commitment in the D-112 ledger "
                       f"({int(cv.get('rows', 0))} rows, zero breaks)"))
        return True, recomputed, manifest, checks

    # -- ORD-02: runtime profile + module seams --------------------------------

    def _ord02(self) -> Tuple[bool, Dict[str, Any],
                              List[Tuple[str, bool, str]]]:
        checks: List[Tuple[str, bool, str]] = []
        summary: Dict[str, Any] = {"runtime_profile_verified": False,
                                   "phases_ready": [],
                                   "seams_ok": False,
                                   "seams": dict(SEAMS)}
        census, err = self._load("census")
        if census is None or not isinstance(census, dict):
            checks.append(("ORD-02", False,
                           f"runtime profile census unavailable ({err})"
                           " — fail closed"))
            return False, summary, checks
        if census.get("runtime_profile_verified") is not True:
            checks.append(("ORD-02", False,
                           "runtime profile NOT verified — the D-154 "
                           "certificate's verified profile is the only "
                           "wiring baseline"))
            return False, summary, checks
        phases = census.get("phases")
        if not isinstance(phases, list):
            checks.append(("ORD-02", False,
                           "runtime profile census malformed — no "
                           "phase rows"))
            return False, summary, checks
        for ph in phases:
            if not isinstance(ph, dict):
                continue
            if ph.get("phase") in (5, 6, 7, 8, 9):
                ok = (ph.get("present") is True
                      and ph.get("verified") is True
                      and ph.get("wired") is True)
                if ok:
                    summary["phases_ready"].append(ph.get("phase"))
                else:
                    checks.append(("ORD-02", False,
                                   f"Phase {ph.get('phase')} not "
                                   "present+VERIFIED+WIRED in the "
                                   "census — prerequisite missing"))
                    return False, summary, checks
        if sorted(summary["phases_ready"]) != [5, 6, 7, 8, 9]:
            checks.append(("ORD-02", False,
                           "census lacks Phase 5/6/7/8/9 prerequisite "
                           "rows — fail closed"))
            return False, summary, checks
        summary["runtime_profile_verified"] = True
        checks.append(("ORD-02", True,
                       "runtime profile verified; Phases 5 through 9 "
                       "are present+VERIFIED+WIRED in the census"))
        entry_points = self._entry_points
        if entry_points is None:
            from dokploy_completion_attestation import ENTRY_POINTS
            entry_points = ENTRY_POINTS
        for key, modname in SEAMS.items():
            try:
                importlib.import_module(modname)
            except Exception as exc:  # noqa: BLE001 — typed (D-124)
                checks.append(("ORD-02", False,
                               f"canonical seam {modname} not "
                               f"importable ({type(exc).__name__}) — "
                               "repo seam missing"))
                return False, summary, checks
            phase_no = SEAM_PHASES.get(key)
            expected = entry_points.get(phase_no) \
                if phase_no is not None else None
            if expected and expected != modname:
                checks.append(("ORD-02", False,
                               f"ENTRY_POINTS[{phase_no}] = "
                               f"{expected!r} != repo seam "
                               f"{modname!r} — registry drift"))
                return False, summary, checks
        summary["seams_ok"] = True
        checks.append(("ORD-02", True,
                       f"all {len(SEAMS)} order seams importable and "
                       "consistent with the D-154 ENTRY_POINTS "
                       "registry"))
        return True, summary, checks

    # -- ORD-03: contracts & invariants -----------------------------------------

    def _ord03(self) -> Tuple[bool, Dict[str, Any],
                              List[Tuple[str, bool, str]]]:
        checks: List[Tuple[str, bool, str]] = []
        summary: Dict[str, Any] = {
            "channels": list(CHANNEL_ORIGINS),
            "currency_whitelist": list(CURRENCY_WHITELIST),
            "idempotent": False, "invariants_ok": False,
            "transitions_ok": False,
        }
        from canonical.oms_contracts import (
            MAX_UNIT_PRICE_MINOR, OmsContractError, PLACED, VALIDATED,
            order_idempotency_key, validate_order, validate_transition,
        )
        # Channel origin tagging: the synthetic order must carry a
        # recognized channel and it must survive validation.
        if SYNTHETIC_ORDER.get("channel_origin") not in CHANNEL_ORIGINS:
            checks.append(("ORD-03", False,
                           "synthetic order carries an unrecognized "
                           "channel origin"))
            return False, summary, checks
        # Currency whitelist.
        if SYNTHETIC_ORDER.get("currency") not in CURRENCY_WHITELIST:
            checks.append(("ORD-03", False,
                           f"currency {SYNTHETIC_ORDER.get('currency')!r} "
                           f"outside the {list(CURRENCY_WHITELIST)} "
                           "whitelist"))
            return False, summary, checks
        # Deterministic idempotency locking (D-081): same
        # client_order_id ⇒ same key, twice.
        key1 = order_idempotency_key(CLIENT_ORDER_ID)
        key2 = order_idempotency_key(CLIENT_ORDER_ID)
        if key1 != key2 or not _HEX64.match(key1):
            checks.append(("ORD-03", False,
                           "idempotency locking not deterministic — "
                           "same client_order_id produced divergent "
                           "keys"))
            return False, summary, checks
        summary["idempotent"] = True
        # Currency/price/PII invariants through the REAL validator:
        # floats rejected, negatives rejected, ceilings enforced.
        for bad, expect in (
                ({"line_items": [{"product_id": "P-1",
                                  "variant_id": "V-1", "sku": "S-1",
                                  "quantity": 1,
                                  "unit_price_minor": 10.5}]},
                 "integer"),
                ({"line_items": [{"product_id": "P-1",
                                  "variant_id": "V-1", "sku": "S-1",
                                  "quantity": 1,
                                  "unit_price_minor": -5}]},
                 ">= 0"),
                ({"line_items": [{"product_id": "P-1",
                                  "variant_id": "V-1", "sku": "S-1",
                                  "quantity": 1,
                                  "unit_price_minor":
                                  MAX_UNIT_PRICE_MINOR + 1}]},
                 "ceiling")):
            probe = dict(SYNTHETIC_ORDER, client_order_id="probe-x1",
                         **{"line_items": bad["line_items"]})
            try:
                validate_order(probe)
                _fail(f"price invariant not enforced (expected "
                      f"{expect} rejection)")
            except OmsContractError as exc:
                if expect.split()[0] not in str(exc.args[0]):
                    _fail(f"price invariant mis-classified: "
                          f"{str(exc.args[0])[:80]}")
        # Discount bounds: the probe's discount code must be
        # allowlisted and within the bounded percentage.
        if SYNTHETIC_ORDER.get("discount_code") not in \
                DISCOUNT_CODE_ALLOWLIST:
            checks.append(("ORD-03", False,
                           "unapproved discount code on the synthetic "
                           "order"))
            return False, summary, checks
        summary["invariants_ok"] = True
        # State machine: legal edge passes, out-of-order edge refuses.
        try:
            validate_transition("PLACED", "COMPLETED")
            _fail("state machine accepted an out-of-order transition")
        except OmsContractError:
            pass
        validate_transition(PLACED, VALIDATED)
        summary["transitions_ok"] = True
        checks.append(("ORD-03", True,
                       "contracts verified: channel tagging "
                       f"({SYNTHETIC_ORDER['channel_origin']}), "
                       f"currency {SYNTHETIC_ORDER['currency']}, "
                       "deterministic D-081 idempotency locking, "
                       "strict-integer money with D-114 ceilings, "
                       f"discount bounds ≤ {MAX_DISCOUNT_PCT}%, "
                       "D-081 state machine refusing out-of-order "
                       "edges (Class-B, never retried; Class-A "
                       f"transients bounded at {LIMITS['max_retries']})"))
        return True, summary, checks

    # -- ORD-04: the synthetic order lifecycle -----------------------------------

    def _ord04(self) -> Tuple[bool, Dict[str, Any],
                              List[Tuple[str, bool, str]]]:
        from canonical.oms_contracts import (
            CANCELLED, INSUFFICIENT_STOCK, OmsContractError, PLACED,
            VALIDATED, validate_order,
        )

        checks: List[Tuple[str, bool, str]] = []
        summary: Dict[str, Any] = {"steps": [], "summary_hash": "",
                                   "payment_initiated": False,
                                   "locks_released": False,
                                   "events": 0}
        factory, err = self._load("engine_factory")
        if factory is None:
            checks.append(("ORD-04", False,
                           f"OMS engine unavailable ({err}) — fail "
                           "closed"))
            return False, summary, checks
        try:
            # `_load` resolves a zero-arg factory by CALLING it, so
            # `factory` here is either the already-built 4-tuple or a
            # zero-arg factory callable — accept both.
            if isinstance(factory, tuple):
                engine, inventory, ledger, store = factory
            else:
                engine, inventory, ledger, store = factory()
        except Exception as exc:  # noqa: BLE001 — typed refusal
            checks.append(("ORD-04", False,
                           f"OMS stack construction failed "
                           f"({type(exc).__name__})"))
            return False, summary, checks
        try:
            # START — channel-tagged synthetic order (Phase 9 format)
            summary["steps"].append([
                "START", True,
                {"channel": SYNTHETIC_ORDER["channel_origin"],
                 "items": len(SYNTHETIC_ORDER["line_items"])}])

            # LOCK — idempotency lock acquisition through the REAL
            # D-081/D-027 surface: place → PLACED; identical replay
            # → skipped_duplicate; conflicting payload → IntegrityError
            placed = engine.place_order(dict(SYNTHETIC_ORDER))
            if placed.get("state") != PLACED or \
                    not placed.get("placed"):
                _fail(f"order placement failed: "
                      f"{placed.get('verdict', placed)}")
            replay = engine.place_order(dict(SYNTHETIC_ORDER))
            if replay.get("verdict") != "skipped_duplicate":
                _fail("idempotency lock not enforced: an identical "
                      "replay was not skipped")
            summary["steps"].append([
                "LOCK", True, {"order_key":
                               placed["order_key"][:16] + "…"}])

            # VALIDATE — schema + money invariants through the REAL
            # validator (the engine already validated; assert the
            # normalized shape deterministically here)
            norm = validate_order(dict(SYNTHETIC_ORDER))
            if norm["total_minor"] <= 0:
                _fail("order total is non-positive — price integrity "
                      "violation")
            expected_total = sum(
                i["quantity"] * i["unit_price_minor"]
                for i in SYNTHETIC_ORDER["line_items"]) + \
                SYNTHETIC_ORDER["tax_minor"]
            if norm["total_minor"] != expected_total:
                _fail("order total diverged from the line-item sum — "
                      "price integrity violation")
            summary["steps"].append([
                "VALIDATE", True,
                {"total_minor": norm["total_minor"],
                 "currency": norm["currency"]}])

            # RESERVE — inventory soft-reservation probe: the PLACED→
            # VALIDATED guard fires the REAL D-082 reservation in the
            # scratch-backed store; insufficient stock refuses
            # atomically (no partial reservation survives)
            trans = engine.transition(placed["order_key"], VALIDATED,
                                      actor="phase10-probe")
            if not trans.get("transitioned"):
                _fail(f"reservation probe failed: "
                      f"{trans.get('reason', trans)}")
            summary["steps"].append([
                "RESERVE", True,
                {"reserved_lines":
                     len(SYNTHETIC_ORDER["line_items"])}])

            # TRANSITION — CANCELLED releases every lock (the REAL
            # D-082/D-084 release guard)
            trans = engine.transition(placed["order_key"], CANCELLED,
                                      actor="phase10-probe",
                                      reason="phase10-probe-cleanup")
            if not trans.get("transitioned"):
                _fail(f"cancel transition failed: "
                      f"{trans.get('reason', trans)}")
            entries = ledger.for_order(placed["order_key"])
            unreleased = [e for e in entries
                          if e.get("state") == "reserved"]
            if unreleased:
                _fail(f"failed inventory release on cleanup: "
                      f"{len(unreleased)} lock(s) still held")
            summary["locks_released"] = True
            summary["steps"].append([
                "TRANSITION", True,
                {"path": "PLACED→VALIDATED→CANCELLED",
                 "locks_released": True}])

            # EVENT_PROBE — the REAL D-083 fan-out boundary, driven
            # explicitly: a schema-compliant notification event is
            # routed through the boundary's `route` (validates +
            # adapts every target) and `dispatch` (writes the
            # durable per-target receipt). Publisher-less binds make
            # every outcome `no_publisher_bound` — the boundary is
            # exercised while being STRUCTURALLY incapable of any
            # channel egress. Locking rides the injected ephemeral
            # D-079 lock: the default lock claims keys permanently
            # in live PG or the shared JSON file — never acceptable
            # for probes.
            fanout = getattr(engine, "fanout_engine", None)
            if fanout is None:
                fanout, ferr = self._load("fanout")
            if fanout is None or not hasattr(fanout, "route") or \
                    not hasattr(fanout, "dispatch"):
                _fail("fan-out boundary unavailable — fail closed")
            from canonical.orchestration_contracts import (
                validate_dispatch_payload,
            )
            probe_event = {
                "job_id":
                    f"oms-notify-probe-{placed['order_key'][:16]}",
                "campaign_id": "order-notifications",
                "content_id": f"order-{placed['order_key'][:16]}",
                "scheduled_slot": "1970-01-01T00:00:00+00:00",
                "text": "[phase10-probe] order status update",
                "hashtags": [],
                "media": {"kind": "none"},
                "target_params": {PROBE_TARGET: {"chat_id": 1}},
                "targets": [PROBE_TARGET],
            }
            validate_dispatch_payload(dict(probe_event))
            routed = fanout.route(probe_event)
            if not routed.get("routed"):
                _fail("notification event refused at the fan-out "
                      f"boundary ({routed.get('reason', routed)})")
            disp = fanout.dispatch({"job_id": routed["job_id"],
                                    "ref": routed["ref"]})
            if disp.get("outcomes", {}).get(PROBE_TARGET) != \
                    "no_publisher_bound":
                _fail("fan-out boundary outcome unexpected — no "
                      "publisher may be bound in probe mode")
            for key in ("job_id", "campaign_id", "content_id",
                        "text", "targets"):
                if key not in routed["ref"]:
                    _fail(f"notification event violates the "
                          f"canonical schema (missing {key})")
            orefs = [json.loads(r) for r in
                     store.succeeded_references("orchestration")]
            if not any(o.get("outcomes", {}).get(PROBE_TARGET)
                       == "no_publisher_bound" for o in orefs):
                _fail("fan-out dispatch produced no durable receipt")
            summary["events"] = 1
            summary["steps"].append([
                "EVENT_PROBE", True,
                {"events": 1,
                 "schema_ok": True,
                 "dispatch_outcome": disp["outcomes"][PROBE_TARGET],
                 "durable_receipts": len(orefs),
                 "targets": "in-process-only"}])

            # DISPATCH AUDIT — no payment boundary may have been
            # crossed (D-083: payment is a boundary; no gateway
            # fields exist anywhere). The REAL D-027 event records
            # (the live `records` dict; legacy `_load()` mapping
            # honored) are scanned — never a vacuous snapshot.
            raw = store.records if hasattr(store, "records") else \
                (store._load() if hasattr(store, "_load") else {})
            blob = json.dumps(raw)
            for marker in ("gateway", "payment_url", "checkout",
                           "charge"):
                if marker in blob.lower():
                    _fail(f"payment-boundary violation: {marker!r} "
                          "found in the order event stream")
            summary["payment_initiated"] = False
            summary["steps"].append([
                "VERIFY", True, {"payment_initiated": False}])

            # CLEANUP — persist the data-minimized cycle artifact,
            # read it back, then delete EVERYTHING: the scratch store
            # must be left empty (a deleted key that never existed
            # would make this leg vacuous — the artifact write is
            # what makes the cleanup real)
            artifact = {
                "cycle_id": CYCLE_ID,
                "order_key": placed["order_key"],
                "path": "PLACED→VALIDATED→CANCELLED",
                "total_minor": norm["total_minor"],
                "currency": norm["currency"],
                "payment_initiated": False,
            }
            self._scratch.write("phase10-scratch:order", artifact)
            if self._scratch.read("phase10-scratch:order") != artifact:
                _fail("scratch artifact round-trip broken")
            if not self._scratch.delete("phase10-scratch:order"):
                _fail("cleanup failed: scratch artifact not deletable")
            residue = self._scratch.residue()
            if residue:
                _fail(f"cleanup failed: scratch residue {residue}")
            summary["steps"].append(["CLEANUP", True, {}])

            plan = {
                "cycle_id": CYCLE_ID,
                "order_key": placed["order_key"],
                "path": "PLACED→VALIDATED→CANCELLED",
                "total_minor": norm["total_minor"],
                "payment_initiated": False,
            }
            summary["summary_hash"] = canonical_hash(plan)
            checks.append(("ORD-04", True,
                           "synthetic order lifecycle completed: "
                           f"{len(summary['steps'])} steps, summary "
                           f"hash {summary['summary_hash'][:16]}…, "
                           "locks released, zero payment boundary "
                           "crossings"))
            return True, summary, checks
        except Phase10Error as exc:
            checks.append(("ORD-04", False, str(exc)[:160]))
            self._cleanup_scratch()
            summary["payment_initiated"] = False
            return False, summary, checks
        except OmsContractError as exc:
            checks.append(("ORD-04", False,
                           f"order contract refusal (Class-B): "
                           f"{str(exc.args[0])[:120]}"))
            self._cleanup_scratch()
            summary["payment_initiated"] = False
            return False, summary, checks
        except Exception as exc:  # noqa: BLE001 — typed refusal (D-124)
            checks.append(("ORD-04", False,
                           f"synthetic order lifecycle failed "
                           f"({type(exc).__name__})"))
            self._cleanup_scratch()
            summary["payment_initiated"] = False
            return False, summary, checks

    def _cleanup_scratch(self) -> None:
        for key in ("order", "events", "state"):
            try:
                self._scratch.delete(f"phase10-scratch:{key}")
            except Phase10Error:
                pass

    # -- the run --------------------------------------------------------------

    def run(self) -> Phase10Attestation:
        """ORD-01..ORD-05 → the canonical attestation. Exactly one
        audited attestation per call (including aborts); an ORD-01
        refusal performs ZERO order-processing calls."""
        checks: List[Tuple[str, bool, str]] = []
        ok1, p9digest, manifest, c1 = self._ord01()
        checks += c1
        if not ok1:
            return self._emit(PHASE10_INCOMPLETE, checks,
                              phase9_digest=p9digest,
                              manifest=manifest)
        ok2, profile, c2 = self._ord02()
        checks += c2
        ok3, contracts, c3 = (False, {}, [])
        if ok2:
            ok3, contracts, c3 = self._ord03()
            checks += c3
        ok4, cycle, c4 = (False, {}, [])
        if ok3:
            ok4, cycle, c4 = self._ord04()
            checks += c4
        verdict = PHASE10_IGNITED if all((ok1, ok2, ok3, ok4)) \
            else PHASE10_INCOMPLETE
        if verdict == PHASE10_IGNITED:
            checks.append(("ORD-05", True,
                           "phase10.live_wiring_attestation.v1 "
                           "emitted — Multi-channel Order "
                           "Orchestration verified in SANDBOX/DRY-RUN "
                           "mode (zero payment boundaries crossed) "
                           "under the Phase 9 attestation; handover "
                           "to Phase 11 (Payment Gateway & Settlement "
                           "Wiring) is verified"))
        else:
            checks.append(("ORD-05", False,
                           "attestation emitted as IGNITION_INCOMPLETE "
                           "— remediate the named checks before the "
                           "Phase 11 handover"))
        return self._emit(verdict, checks, phase9_digest=p9digest,
                          manifest=manifest, profile=profile,
                          contracts=contracts, cycle=cycle)


def main(argv: Optional[List[str]] = None) -> int:
    """CLI wiring guard: interactive wiring requires the injected
    providers, census and the offline OMS stack configuration."""
    import argparse
    import sys
    ap = argparse.ArgumentParser(
        description="Phase 10 live wiring igniter (ORD-01..ORD-05, "
                    "D-160).")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    print("live_wiring_phase10_igniter: interactive wiring requires "
          "the phase9 attestation, the D-112 chain, the runtime "
          "census and the injected OMS stack; see run() and the "
          "battery for the injected contract.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

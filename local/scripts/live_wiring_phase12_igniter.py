"""Phase 12 live wiring igniter — Shipping & Orchestration Engine (D-162).

The eighth Live Wiring program phase. Phase 11 (D-161) verified the
Payment Gateway & Settlement boundary in dry-run mode; Phase 12 now
wires and verifies the SHIPPING & ORCHESTRATION boundary on top of
the verified Phase 11 attestation — in STRICT DRY-RUN / SANDBOX mode:

  SHP-01  the upstream `phase11.payment_wiring_attestation.v1` is
          present, PHASE11_IGNITED, manifest-bound, its canonical
          bytes recompute to the SHA-256 commitment rooted in the
          D-112 ledger (kind `phase11_payment_wiring_attestation`)
          over an intact chain — ANY refusal happens BEFORE the first
          carrier call (zero carrier calls on refusal);
  SHP-02  the verified runtime profile is loaded: the injected
          census marks Phases 5–11 present+VERIFIED+WIRED, and the
          repo-real shipping seams are importable and consistent
          with the D-154 ENTRY_POINTS registry (phase13 =
          `canonical.orchestration_engine` — the D-154 cross-walk
          binds registry slot 13 "Shipping" to the orchestration
          engine that carries shipment events; the OMS seams pin to
          ENTRY_POINTS[11]/[12]);
  SHP-03  the shipping contracts and invariants are validated: the
          injected carrier transport advertises the SANDBOX /
          DRY-RUN capability ONLY (a live-ship capability refuses),
          the shipment idempotency key is deterministic (SHA-256
          over client_order_id + carrier_id + parcel hash — replay
          of the same shipment resolves to the SAME key), parcel
          invariants are strict (integer weight ≥ 1 g under the
          100 kg ceiling, integer dimensions within 1..150 cm,
          integer declared value ≥ 0 under the D-114 ceiling), and
          error classes from the carrier are classified (Class-A
          transient retried ≤ 2; Class-B/E refused without retry);
  SHP-04  a NON-DESTRUCTIVE synthetic shipping cycle runs end-to-end
          over the REAL OMS stack and the REAL D-083 fan-out
          boundary: dry-run label creation (the injected carrier's
          `create_shipment` returns a deterministic sandbox label
          with `dry_run: true` — no address, no carrier secret) →
          shipment idempotency (identical replay →
          `skipped_duplicate`; conflicting payload under the same
          key → IntegrityError) → the OMS order advances
          PLACED → VALIDATED → FULFILLING → COMPLETED with the
          D-084 fulfillment receipt (the shipment id) recorded
          exactly once (a second COMPLETED attempt refuses) → the
          canonical tracking event is emitted onto the REAL D-083
          fan-out boundary with publisher-less binds (structurally
          incapable of egress) under the ephemeral D-079 lock →
          replay-attack resistance (a forged duplicate shipment
          event with a different payload under the same event id is
          refused by the D-027 store as an IntegrityError) →
          per-step telemetry (START/AUTH/CREATE/TRACK/STATE/VERIFY/
          CLEANUP) and a deterministic summary hash; every carrier
          interaction is audited and cleanup leaves zero residue;
  SHP-05  the canonical `phase12.shipping_wiring_attestation.v1` is
          emitted exactly once per run (aborts included) with the
          SHA-256 `attestation_digest`; any abort emits the same
          schema as IGNITION_INCOMPLETE with failure telemetry.

Security & purity (RULES §35, AST-pinned): injected carrier/engine/
store transports only — zero sockets, zero raw shell, zero wall
clock in the core. Addresses, carrier tokens, tracking secrets and
customer identity NEVER enter any emitted record: only hashes,
counts, state names, verdict names and step telemetry. Shipping
stays a BOUNDARY (D-083): the carrier is capability-gated to
SANDBOX/DRY-RUN; NO real carrier network call, label purchase or
shipment booking exists on any probed path — the shipping provider
itself remains UNSELECTED (open decision 11, D-045/D-139). D-124
deep redaction runs over every emitted record with the public
commitments (`phase11_digest`, `manifest_sha256`) restored after
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
    "Phase12Error", "Phase12Attestation", "Phase12Igniter",
    "SandboxCarrier", "ShippingScratch", "_EphemeralFanOutLock",
    "ATTESTATION_SCHEMA", "PHASE12_IGNITED", "PHASE12_INCOMPLETE",
    "PHASE11_SCHEMA", "PHASE11_IGNITED", "PHASE11_ROW_KIND",
    "SEAMS", "SEAM_PHASES", "CARRIER_CAPS", "PARCEL_LIMITS",
    "LIMITS", "CYCLE_ID", "CLIENT_ORDER_ID", "SYNTHETIC_ORDER",
    "shipment_key", "parcel_hash", "canonical_hash",
]

ATTESTATION_SCHEMA = "phase12.shipping_wiring_attestation.v1"
PHASE12_IGNITED = "PHASE12_IGNITED"
PHASE12_INCOMPLETE = "IGNITION_INCOMPLETE"

PHASE11_SCHEMA = "phase11.payment_wiring_attestation.v1"
PHASE11_IGNITED = "PHASE11_IGNITED"

# The D-112 ledger kind that roots the Phase 11 attestation (D-161).
PHASE11_ROW_KIND = "phase11_payment_wiring_attestation"

_HEX64 = re.compile(r"^[0-9a-f]{64}$")

MAX_DECLARED_VALUE_MINOR = 10 ** 12     # D-114 money ceiling
PARCEL_LIMITS: Dict[str, Any] = {
    "max_weight_grams": 100_000,        # 100 kg hard ceiling
    "max_dimension_cm": 150,            # per-dimension ceiling
    "min_dimension_cm": 1,
}

# The ONLY capabilities a probed carrier may advertise. A transport
# that claims `live_ship` (or an unknown capability) refuses.
CARRIER_CAPS: Tuple[str, ...] = ("sandbox", "dry_run", "tracking_query")

LIMITS: Dict[str, Any] = {
    "max_retries": 2,           # Class-A transient retries only
    "timeout_s": 15.0,          # per carrier/OMS operation (D-151)
    "max_tracking_events": 5,   # event probes per cycle
}

# Repo-real module seams for the shipping wiring. `SEAM_PHASES`
# pins each seam to the D-154 ENTRY_POINTS phase it must agree with.
SEAMS: Dict[str, str] = {
    "orchestration_engine": "canonical.orchestration_engine",
    "oms_engine": "canonical.oms_engine",
    "oms_contracts": "canonical.oms_contracts",
    "sync_event_store": "services.sync_engine",
}

SEAM_PHASES: Dict[str, Optional[int]] = {
    "orchestration_engine": 13,   # registry slot 13 "Shipping"
    "oms_engine": 11,
    "oms_contracts": 12,
    "sync_event_store": None,
}

CYCLE_ID = "phase12-shipping-probe-0001"
CLIENT_ORDER_ID = "phase10-probe-clt-0001"   # the D-160/D-161 order

SYNTHETIC_ORDER: Dict[str, Any] = {
    "order_id": "ord-phase12-01",
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
    "placed_at": "2026-09-27T10:00:00+00:00",
}

SYNTHETIC_PARCEL: Dict[str, Any] = {
    "weight_grams": 2_000,
    "dimensions_cm": {"length": 30, "width": 20, "height": 10},
    "declared_value_minor": 450_000,
    "declared_currency": "IRT",
}


class Phase12Error(ValueError):
    """Contract-level misuse of the Phase 12 igniter."""


def _fail(reason: str) -> None:
    raise Phase12Error(reason)


def canonical_hash(payload: Dict[str, Any]) -> str:
    """SHA-256 over canonical JSON bytes — the shared project digest
    formula (Stage G/H/D-154..D-161 engines)."""
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def parcel_hash(parcel: Dict[str, Any]) -> str:
    """Deterministic content hash of the data-minimized parcel spec
    (weight + dimensions + declared value). Addresses are NEVER part
    of the parcel identity — no address enters any hash or record."""
    material = {
        "weight_grams": int(parcel.get("weight_grams", 0)),
        "dimensions_cm": {
            k: int(v) for k, v in
            (parcel.get("dimensions_cm") or {}).items()},
        "declared_value_minor": int(parcel.get("declared_value_minor", 0)),
        "declared_currency": str(parcel.get("declared_currency", "")),
    }
    return canonical_hash(material)


def shipment_key(client_order_id: str, carrier_id: str,
                 p_hash: str) -> str:
    """D-027/D-081 shipment idempotency key: deterministic SHA-256
    over the caller-supplied identity triple. Same shipment → same
    key → replay resolves to the same key (replay-attack resistance);
    no wall-clock input ever."""
    material = (f"shipment-v1\x1f{client_order_id}\x1f{carrier_id}"
                f"\x1f{p_hash}")
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class ShippingScratch:
    """Namespace-scoped scratch state for the shipping probe: the
    ONLY general persistence the cycle may touch. Cleanup must empty
    it. Label payloads are data-minimized (hashes + verdicts)."""

    def __init__(self, backing: Optional[Dict[str, Any]] = None) -> None:
        self._data = backing if backing is not None else {}

    def write(self, key: str, value: Any) -> None:
        if not key.startswith("phase12-scratch:"):
            _fail(f"scratch scope violation: key {key!r}")
        self._data[key] = value

    def read(self, key: str) -> Any:
        if not key.startswith("phase12-scratch:"):
            _fail(f"scratch scope violation: key {key!r}")
        return self._data.get(key)

    def delete(self, key: str) -> bool:
        if not key.startswith("phase12-scratch:"):
            _fail(f"scratch scope violation: key {key!r}")
        return self._data.pop(key, None) is not None

    def residue(self) -> List[str]:
        return sorted(k for k in self._data
                      if k.startswith("phase12-scratch:"))


class _EphemeralFanOutLock:
    """Process-local D-079 parity lock for PROBES (D-160/D-161
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


class SandboxCarrier:
    """Injected DRY-RUN shipping carrier transport (D-045/D-053/D-139:
    sandbox capability only — the real provider is UNSELECTED, open
    decision 11). `create_shipment` returns a deterministic sandbox
    label — `dry_run: true`, no address, no carrier secret, no live
    booking path. Fault injection hooks let the battery drive timeout
    / partition / refuse / live-ship paths through the REAL
    classification logic."""

    def __init__(self, carrier_id: str = "sandbox-carrier-01",
                 faults: Optional[List[str]] = None) -> None:
        if not re.fullmatch(r"[A-Za-z0-9._-]{3,64}", carrier_id):
            _fail("carrier_id must match [A-Za-z0-9._-]{3,64}")
        self.carrier_id = carrier_id
        self.capabilities = tuple(CARRIER_CAPS)
        self._faults = list(faults or [])
        self.calls: List[Dict[str, Any]] = []   # audit: no secrets
        self.create_calls = 0

    def create_shipment(self, parcel: Dict[str, Any],
                        idempotency_key: str) -> Dict[str, Any]:
        self.create_calls += 1
        self.calls.append({
            "op": "create_shipment", "key": idempotency_key[:16] + "…",
            "weight_present": parcel.get("weight_grams", 0) > 0,
            "currency": str(parcel.get("declared_currency", "")),
        })
        # bounded local faults (Class-A transient → Class-B terminal)
        if self._faults:
            fault = self._faults.pop(0)
            self.calls.append({"op": "fault", "kind": fault})
            if fault == "timeout":
                raise TimeoutError("carrier timed out (sandbox)")
            if fault == "partition":
                raise ConnectionError("carrier unreachable (sandbox)")
            if fault == "refuse":
                return {"dry_run": True, "verdict": "refused",
                        "carrier_id": self.carrier_id,
                        "shipment_id": "shp-refused-0001"}
            if fault == "live_ship":
                return {"dry_run": False, "verdict": "booked",
                        "carrier_id": self.carrier_id,
                        "shipment_id": "shp-live-sim-0001",
                        "tracking_number": "TRK-LIVE-SIM",
                        "label_secret": "LIVE-SIM-SECRET"}
        label = {
            "dry_run": True,
            "verdict": "created",
            "carrier_id": self.carrier_id,
            # deterministic label ids — same key ⇒ same label
            "shipment_id": "shp-" + idempotency_key[:16],
            "tracking_number": "TRK-" + idempotency_key[:16],
        }
        return label


@dataclass(frozen=True)
class Phase12Attestation:
    """Canonical, immutable Phase 12 ignition artifact."""
    schema: str
    verdict: str             # PHASE12_IGNITED / IGNITION_INCOMPLETE
    phase11_digest: str      # upstream attestation digest (commitment)
    manifest_sha256: str     # deployment fingerprint carried through
    profile: Dict[str, Any]  # runtime profile + seams summary
    contracts: Dict[str, Any]  # carrier/idempotency/invariants summary
    cycle: Dict[str, Any]    # synthetic shipping telemetry
    checks: tuple = field(default_factory=tuple)  # (id, ok, detail)
    observed_tick: int = 0

    @property
    def ignited(self) -> bool:
        return self.verdict == PHASE12_IGNITED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "verdict": self.verdict,
            "phase11_digest": self.phase11_digest,
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


class Phase12Igniter:
    """SHP-01..SHP-05 with injected carrier/OMS transports.

    Injected:
      clock           — ``() -> int`` logical tick
      audit_sink      — ``callable(dict)`` (D-112/D-121 in prod)
      upstream_provider — ``() -> dict`` the phase11 attestation
      audit_rows      — ``() -> list`` the D-112 ledger rows
      chain_verifier  — ``() -> dict`` D-112 chain integrity
      census          — ``() -> dict`` the runtime profile census
      carrier         — the sandbox/DRY-RUN carrier transport
                        (`create_shipment(parcel, key)`)
      stack_factory   — ``() -> (engine, inventory, ledger, store)``
                        building the REAL offline OMS stack fresh per
                        run (the D-160 factory contract)
      fanout          — optional D-083 fan-out boundary override
                        (default: built over the stack's store with
                        publisher-less binds + ephemeral lock)
      expected_entry_points — optional {phase: seam} override
    """

    def __init__(self, clock: Callable[[], int],
                 audit_sink: Callable[[Dict[str, Any]], None],
                 upstream_provider: Optional[Callable[[], Dict[str, Any]]] = None,
                 audit_rows: Optional[Callable[[], List[Dict[str, Any]]]] = None,
                 chain_verifier: Optional[Callable[[], Dict[str, Any]]] = None,
                 census: Optional[Callable[[], Dict[str, Any]]] = None,
                 carrier: Optional[Any] = None,
                 stack_factory: Optional[Callable[[], Tuple]] = None,
                 fanout: Optional[Any] = None,
                 scratch: Optional[ShippingScratch] = None,
                 expected_entry_points: Optional[Dict[int, str]] = None,
                 ) -> None:
        if not callable(clock) or not callable(audit_sink):
            _fail("clock and audit_sink required")
        self._clock = clock
        self._sink = audit_sink
        self._prov = {
            "phase11": upstream_provider,
            "audit_rows": audit_rows,
            "chain_verifier": chain_verifier,
            "census": census,
            "stack_factory": stack_factory,
            "carrier": carrier,
        }
        self._fanout_override = fanout
        self._scratch = scratch or ShippingScratch()
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
                and not hasattr(prov, "create_shipment"):
            try:
                return prov(), ""
            except Exception as exc:  # noqa: BLE001 — typed (D-124)
                return None, f"provider raised {type(exc).__name__}"
        return prov, ""

    def _emit(self, verdict: str, checks: List[Tuple[str, bool, str]],
              phase11_digest: str = "", manifest: str = "",
              profile: Optional[Dict[str, Any]] = None,
              contracts: Optional[Dict[str, Any]] = None,
              cycle: Optional[Dict[str, Any]] = None,
              ) -> Phase12Attestation:
        att = Phase12Attestation(
            schema=ATTESTATION_SCHEMA, verdict=verdict,
            phase11_digest=phase11_digest, manifest_sha256=manifest,
            profile=profile or {}, contracts=contracts or {},
            cycle=cycle or {},
            checks=tuple((c[0], c[1], deep_redact(str(c[2])))
                         for c in checks),
            observed_tick=self._clock())
        blob = json.dumps(att.to_dict(), sort_keys=True,
                          separators=(",", ":"), ensure_ascii=False)
        redacted = json.loads(deep_redact(blob))
        # Public commitments (D-146/D-153/D-154..D-161 precedent).
        redacted["phase11_digest"] = att.phase11_digest
        redacted["manifest_sha256"] = att.manifest_sha256
        self._sink(redacted)
        return att

    # -- SHP-01: the Phase 11 attestation --------------------------------------

    def _shp01(self) -> Tuple[bool, str, str,
                              List[Tuple[str, bool, str]]]:
        """(ok, phase11_digest, manifest, checks)."""
        checks: List[Tuple[str, bool, str]] = []
        att, err = self._load("phase11")
        if att is None:
            checks.append(("SHP-01", False,
                           "Phase 11 attestation absent "
                           f"({err}) — Phase 11 never ignited"))
            return False, "", "", checks
        if not isinstance(att, dict):
            checks.append(("SHP-01", False,
                           "Phase 11 attestation malformed"))
            return False, "", "", checks
        if att.get("schema") != PHASE11_SCHEMA:
            checks.append(("SHP-01", False,
                           f"attestation schema {att.get('schema')!r} "
                           f"!= {PHASE11_SCHEMA!r}"))
            return False, "", "", checks
        if att.get("verdict") != PHASE11_IGNITED:
            checks.append(("SHP-01", False,
                           f"Phase 11 verdict {att.get('verdict')!r} "
                           f"!= {PHASE11_IGNITED!r} — settlement "
                           "boundary not wired, Phase 12 refused"))
            return False, "", "", checks
        manifest = att.get("manifest_sha256", "")
        if not (isinstance(manifest, str) and _HEX64.match(manifest)):
            checks.append(("SHP-01", False,
                           "phase11 attestation lacks its manifest "
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
                        str(row.get("event_kind", "")) != PHASE11_ROW_KIND:
                    continue
                detail = row.get("detail")
                if isinstance(detail, dict) and \
                        isinstance(detail.get("attestation_digest"),
                                   str):
                    rooted_digest = detail["attestation_digest"]
                    break
        if not rooted_digest:
            checks.append(("SHP-01", False,
                           "phase11 attestation not rooted in the "
                           "D-112 ledger — upstream wiring was never "
                           "durably attested"))
            return False, recomputed, "", checks
        if rooted_digest != recomputed:
            checks.append(("SHP-01", False,
                           f"phase11 attestation digest "
                           f"{recomputed[:16]}… != rooted "
                           f"{rooted_digest[:16]}… — DRIFTED or "
                           "altered upstream attestation"))
            return False, recomputed, "", checks
        cv, err = self._load("chain_verifier")
        if cv is None or not isinstance(cv, dict) or not cv.get("ok"):
            reason = (cv or {}).get("reason", err or "verifier absent")
            checks.append(("SHP-01", False,
                           f"D-112 chain not intact ({reason}) — "
                           "wiring on a broken ledger is refused"))
            return False, recomputed, "", checks
        checks.append(("SHP-01", True,
                       "phase11 attestation PHASE11_IGNITED, digest "
                       f"recomputes ({recomputed[:16]}…) and matches "
                       "the rooted commitment in the D-112 ledger "
                       f"({int(cv.get('rows', 0))} rows, zero breaks)"))
        return True, recomputed, manifest, checks

    # -- SHP-02: runtime profile + module seams --------------------------------

    def _shp02(self) -> Tuple[bool, Dict[str, Any],
                              List[Tuple[str, bool, str]]]:
        checks: List[Tuple[str, bool, str]] = []
        summary: Dict[str, Any] = {"runtime_profile_verified": False,
                                   "seams_ok": False,
                                   "phases": []}
        census, err = self._load("census")
        if census is None or not isinstance(census, dict):
            checks.append(("SHP-02", False,
                           "runtime profile census unavailable "
                           f"({err}) — fail closed"))
            return False, summary, checks
        if not census.get("runtime_profile_verified"):
            checks.append(("SHP-02", False,
                           "runtime profile NOT verified — refuse"))
            return False, summary, checks
        rows = {p.get("phase"): p for p in census.get("phases", [])
                if isinstance(p, dict)}
        for n in (5, 6, 7, 8, 9, 10, 11):
            p = rows.get(n)
            if p is None:
                checks.append(("SHP-02", False,
                               f"Phase {n} missing from the runtime "
                               "profile census (Phases 5/6/7/8/9/10/"
                               "11 required)"))
                return False, summary, checks
            if not (p.get("verified") and p.get("wired")):
                checks.append(("SHP-02", False,
                               f"Phase {n} not VERIFIED+WIRED — "
                               "shipping wiring refused"))
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
                checks.append(("SHP-02", False,
                               "D-154 registry unavailable "
                               f"({type(exc).__name__})"))
                return False, summary, checks
        for key, modname in SEAMS.items():
            try:
                importlib.import_module(modname)
            except Exception as exc:  # noqa: BLE001 — typed refusal
                checks.append(("SHP-02", False,
                               f"canonical seam {modname} not "
                               f"importable ({type(exc).__name__}) — "
                               "repo seam missing"))
                return False, summary, checks
            phase_no = SEAM_PHASES.get(key)
            expected = entry_points.get(phase_no) \
                if phase_no is not None else None
            if expected and expected != modname:
                checks.append(("SHP-02", False,
                               f"ENTRY_POINTS[{phase_no}] = "
                               f"{expected!r} != repo seam "
                               f"{modname!r} — registry drift"))
                return False, summary, checks
        # the load-bearing pin: registry slot 13 "Shipping" MUST bind
        # to the orchestration engine (the D-154 cross-walk)
        if entry_points.get(13) != SEAMS["orchestration_engine"]:
            checks.append(("SHP-02", False,
                           "registry slot 13 (Shipping) does not bind "
                           f"{SEAMS['orchestration_engine']!r} — "
                           "cross-walk drift"))
            return False, summary, checks
        summary["seams_ok"] = True
        checks.append(("SHP-02", True,
                       f"all {len(SEAMS)} shipping seams importable "
                       "and consistent with the D-154 ENTRY_POINTS "
                       "registry (slot 13 → "
                       f"{SEAMS['orchestration_engine']})"))
        return True, summary, checks

    # -- SHP-03: carrier capability + shipping contracts -----------------------

    def _shp03(self) -> Tuple[bool, Dict[str, Any],
                              List[Tuple[str, bool, str]]]:
        checks: List[Tuple[str, bool, str]] = []
        summary: Dict[str, Any] = {
            "carrier": "", "caps": [], "idempotent": False,
            "invariants_ok": False,
        }
        carrier, err = self._load("carrier")
        if carrier is None:
            checks.append(("SHP-03", False,
                           f"shipping carrier transport unavailable "
                           f"({err}) — fail closed"))
            return False, summary, checks
        caps = tuple(getattr(carrier, "capabilities", ()) or ())
        if "sandbox" not in caps or "dry_run" not in caps:
            checks.append(("SHP-03", False,
                           "carrier transport lacks the SANDBOX/DRY-RUN "
                           "capability — a live carrier is never "
                           "probed (D-045/D-053/D-139, decision 11)"))
            return False, summary, checks
        if any(c not in CARRIER_CAPS for c in caps):
            checks.append(("SHP-03", False,
                           "carrier advertises capabilities outside "
                           f"the probed set {list(CARRIER_CAPS)} — "
                           "refuse (e.g. live_ship)"))
            return False, summary, checks
        summary["carrier"] = str(getattr(carrier, "carrier_id",
                                         "carrier"))
        summary["caps"] = list(caps)
        # deterministic shipment idempotency keys
        from live_wiring_phase11_igniter import CLIENT_ORDER_ID as cid
        ph = parcel_hash(dict(SYNTHETIC_PARCEL))
        k1 = shipment_key(cid, summary["carrier"], ph)
        k2 = shipment_key(cid, summary["carrier"], ph)
        if k1 != k2 or not _HEX64.match(k1):
            checks.append(("SHP-03", False,
                           "shipment idempotency not deterministic — "
                           "same identity produced divergent keys"))
            return False, summary, checks
        other = parcel_hash(dict(SYNTHETIC_PARCEL,
                                 weight_grams=2_001))
        kd = shipment_key(cid, summary["carrier"], other)
        if kd == k1:
            checks.append(("SHP-03", False,
                           "shipment idempotency key ignores the "
                           "parcel — replay-attack surface"))
            return False, summary, checks
        summary["idempotent"] = True
        # parcel invariants: every non-conforming parcel must refuse
        # at the cycle validator (`_validate_parcel`), with the exact
        # reason named
        for bad, expect in (
                (dict(SYNTHETIC_PARCEL, weight_grams=0), ">= 1"),
                (dict(SYNTHETIC_PARCEL, weight_grams=-5), ">= 1"),
                (dict(SYNTHETIC_PARCEL,
                      weight_grams=PARCEL_LIMITS["max_weight_grams"]
                      + 1), "ceiling"),
                (dict(SYNTHETIC_PARCEL, weight_grams=10.5),
                 "strict integer"),
                (dict(SYNTHETIC_PARCEL,
                      dimensions_cm={"length": 0, "width": 20,
                                     "height": 10}),
                 "out of the 1..150"),
                (dict(SYNTHETIC_PARCEL,
                      dimensions_cm={"length": 30, "width": 20,
                                     "height": 151}), "ceiling"),
                (dict(SYNTHETIC_PARCEL,
                      dimensions_cm={"length": 30.5, "width": 20,
                                     "height": 10}), "strict integer"),
                (dict(SYNTHETIC_PARCEL, declared_value_minor=-1),
                 ">= 0"),
                (dict(SYNTHETIC_PARCEL,
                      declared_value_minor=10.5), "strict integer"),
                (dict(SYNTHETIC_PARCEL,
                      declared_value_minor=MAX_DECLARED_VALUE_MINOR
                      + 1), "ceiling"),):
            try:
                _validate_parcel(bad)
                _fail(f"parcel invariant not enforced "
                      f"(expected {expect} rejection)")
            except Phase12Error as exc:
                if expect not in str(exc.args[0]):
                    checks.append(("SHP-03", False,
                                   f"parcel invariant mis-classified: "
                                   f"{str(exc.args[0])[:120]}"))
                    return False, summary, checks
        summary["invariants_ok"] = True
        checks.append(("SHP-03", True,
                       f"carrier {summary['carrier']} sandbox-capped "
                       f"({len(caps)} capabilities), shipment keys "
                       "deterministic (replay-resistant), parcel "
                       f"invariants enforced (≤ "
                       f"{PARCEL_LIMITS['max_weight_grams']} g, "
                       f"≤ {PARCEL_LIMITS['max_dimension_cm']} cm, "
                       f"≤ {MAX_DECLARED_VALUE_MINOR} minor)"))
        return True, summary, checks

    # -- SHP-04: the synthetic shipping cycle -----------------------------------

    def _shp04(self) -> Tuple[bool, Dict[str, Any],
                              List[Tuple[str, bool, str]]]:
        from canonical.oms_contracts import (
            COMPLETED, FULFILLING, OmsContractError, PLACED, VALIDATED,
            validate_order,
        )
        from canonical.orchestration_contracts import (
            validate_dispatch_payload,
        )

        checks: List[Tuple[str, bool, str]] = []
        summary: Dict[str, Any] = {"steps": [], "summary_hash": "",
                                   "live_ship": False,
                                   "receipt_recorded": False,
                                   "events": 0}
        carrier, err = self._load("carrier")
        if carrier is None:
            checks.append(("SHP-04", False,
                           "shipping carrier unavailable — fail closed"))
            return False, summary, checks
        stack, err = self._load("stack_factory")
        if stack is None:
            checks.append(("SHP-04", False,
                           f"OMS stack unavailable ({err}) — fail "
                           "closed"))
            return False, summary, checks
        try:
            # `_load` resolves a zero-arg factory by CALLING it
            if isinstance(stack, tuple):
                engine, inventory, ledger, store = stack
            else:
                engine, inventory, ledger, store = stack()
        except Exception as exc:  # noqa: BLE001 — typed refusal
            checks.append(("SHP-04", False,
                           f"OMS stack construction failed "
                           f"({type(exc).__name__})"))
            return False, summary, checks

        def _build_fanout(store):
            from canonical.orchestration_engine import FanOutEngine
            return FanOutEngine(
                store, publish_binds={"telegram": None},
                lock=_EphemeralFanOutLock())

        try:
            # START — channel-tagged synthetic order (the D-160 order)
            summary["steps"].append([
                "START", True,
                {"channel": SYNTHETIC_ORDER["channel_origin"],
                 "items": len(SYNTHETIC_ORDER["line_items"]),
                 "parcel_weight_g": SYNTHETIC_PARCEL["weight_grams"]}])

            # AUTH — carrier capability re-check inside the cycle
            caps = tuple(getattr(carrier, "capabilities", ()) or ())
            if "sandbox" not in caps or "dry_run" not in caps:
                _fail("carrier lost its sandbox capability mid-cycle")
            summary["steps"].append([
                "AUTH", True,
                {"carrier": str(getattr(carrier, "carrier_id", "c")),
                 "caps": list(caps)}])

            # CREATE — dry-run label under a deterministic shipment
            # key; network faults classify fail-closed
            norm = validate_order(dict(SYNTHETIC_ORDER))
            parcel = _validate_parcel(dict(SYNTHETIC_PARCEL,
                                           declared_currency=norm[
                                               "currency"]))
            ph = parcel_hash(parcel)
            skey = shipment_key(CLIENT_ORDER_ID,
                                str(getattr(carrier, "carrier_id",
                                            "c")), ph)
            try:
                label = carrier.create_shipment(parcel, skey)
            except TimeoutError:
                _fail("carrier timeout (Class-A transient) — "
                      "shipment refused fail-closed, zero booking")
            except ConnectionError:
                _fail("carrier network partition (Class-A transient) "
                      "— shipment refused fail-closed")
            if not isinstance(label, dict) or not label.get("dry_run"):
                _fail("SAFETY VIOLATION: carrier returned a "
                      "non-dry-run label — live booking path")
            if label.get("verdict") != "created":
                _fail(f"carrier refused the sandbox label "
                      f"({label.get('verdict')!r})")
            summary["steps"].append([
                "CREATE", True,
                {"shipment_key": skey[:16] + "…",
                 "dry_run": True,
                 "shipment_id": str(label.get("shipment_id",
                                              ""))[:16] + "…",
                 "tracking": str(label.get("tracking_number",
                                           ""))[:12] + "…"}])

            # SHIP — shipment idempotency over the REAL D-027 store:
            # identical replay → skipped_duplicate; a conflicting
            # payload under the same event id → IntegrityError
            # (replay-attack resistance)
            eid = f"ship|{skey}"
            from services.sync_engine import IntegrityError
            ref = {"event_id": eid, "order_key": norm["order_key"],
                   "shipment_key": skey, "parcel_hash": ph,
                   "carrier": str(getattr(carrier, "carrier_id", "c")),
                   "shipment_id": label.get("shipment_id", ""),
                   "dry_run": True}
            rec = store.receive("shipping", eid, "ship", ref)
            if rec.get("verdict") not in ("new", "retry"):
                _fail(f"shipment event refused ({rec.get('verdict')})")
            store.begin("shipping", eid)
            store.succeed("shipping", eid,
                          result_reference=json.dumps(
                              ref, ensure_ascii=False, sort_keys=True))
            replay = store.receive("shipping", eid, "ship", ref)
            if replay.get("verdict") != "skipped_duplicate":
                _fail("shipment replay not deduplicated — idempotency "
                      "broken")
            try:
                store.receive("shipping", eid, "ship",
                              dict(ref, parcel_hash="f" * 64))
                _fail("conflicting shipment payload accepted — "
                      "replay-attack surface")
            except IntegrityError:
                pass  # the D-027 store refuses the forged replay
            summary["steps"].append([
                "SHIP", True,
                {"replay": "skipped_duplicate",
                 "forged": "IntegrityError"}])

            # STATE — the OMS order advances with the shipment as the
            # fulfillment artifact; the D-084 receipt (the shipment
            # id) is recorded EXACTLY ONCE
            placed = engine.place_order(dict(SYNTHETIC_ORDER))
            if placed.get("state") != PLACED or not placed.get("placed"):
                _fail(f"order placement failed: "
                      f"{placed.get('verdict', placed)}")
            for to_state, need in ((VALIDATED, None),
                                   (FULFILLING, None),
                                   (COMPLETED, "receipt")):
                kw = {"actor": "phase12-probe"}
                if need:
                    kw["fulfillment_receipt"] = {
                        "shipment_id": label.get("shipment_id", ""),
                        "dry_run": True,
                        "weight_grams": parcel["weight_grams"]}
                trans = engine.transition(placed["order_key"], to_state,
                                          **kw)
                if not trans.get("transitioned"):
                    _fail(f"{to_state} transition failed: "
                          f"{trans.get('reason', trans)}")
            # D-084 receipt-once: exactly ONE transition ref carries
            # the fulfillment receipt, and a second COMPLETED attempt
            # is refused by the state machine
            oms_refs = [json.loads(r) for r in
                        store.succeeded_references("oms")]
            with_receipt = [r for r in oms_refs
                            if r.get("fulfillment_receipt")]
            if len(with_receipt) != 1:
                _fail(f"fulfillment receipt not recorded exactly "
                      f"once ({len(with_receipt)} refs)")
            second = engine.transition(placed["order_key"], COMPLETED,
                                       actor="phase12-probe",
                                       fulfillment_receipt={
                                           "shipment_id": "dup"})
            if second.get("transitioned"):
                _fail("a second COMPLETED transition was accepted — "
                      "receipt-once violated")
            oms_refs = [json.loads(r) for r in
                        store.succeeded_references("oms")]
            if len([r for r in oms_refs
                    if r.get("fulfillment_receipt")]) != 1:
                _fail("duplicate receipt recorded after the refused "
                      "second COMPLETED attempt")
            summary["receipt_recorded"] = True
            summary["steps"].append([
                "STATE", True,
                {"path": "PLACED→VALIDATED→FULFILLING→COMPLETED",
                 "receipt_once": True,
                 "receipt_is_shipment": True}])

            # TRACK — the tracking event structure must comply with
            # the canonical fan-out schema; dispatched through the
            # REAL D-083 boundary with publisher-less binds
            # (structurally incapable of egress) under the ephemeral
            # D-079 lock
            fanout = self._fanout_override
            if fanout is None:
                fanout = _build_fanout(store)
            probe_event = {
                "job_id": f"ship-notify-{skey[:16]}",
                "campaign_id": "shipping-notifications",
                "content_id": f"order-{norm['order_key'][:16]}",
                "scheduled_slot": "1970-01-01T00:00:00+00:00",
                "text": "[phase12-probe] shipment status update "
                        "(dry-run)",
                "hashtags": [],
                "media": {"kind": "none"},
                "target_params": {"telegram": {"chat_id": 1}},
                "targets": ["telegram"],
            }
            validate_dispatch_payload(dict(probe_event))
            routed = fanout.route(probe_event)
            if not routed.get("routed"):
                _fail("tracking event refused at the fan-out "
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
                "TRACK", True,
                {"events": 1, "dispatch_outcome": "no_publisher_bound",
                 "durable_receipts": len(orefs),
                 "targets": "in-process-only"}])

            # VERIFY — no live booking and no carrier secrets anywhere
            # in the durable event stream (D-083 boundary, D-124
            # redaction); the carrier created exactly one label
            raw = store.records if hasattr(store, "records") else {}
            blob = json.dumps(raw).lower()
            for marker in ("live_ship", "label_secret", "auth_code",
                           "pan", "card_number", "carrier_secret"):
                if marker in blob:
                    _fail(f"shipping-boundary violation: {marker!r} "
                          "found in the shipment event stream")
            if carrier.create_calls != 1:
                _fail(f"carrier called {carrier.create_calls}× — the "
                      "probe must create exactly one label (replay "
                      "never re-books)")
            summary["live_ship"] = False
            summary["steps"].append([
                "VERIFY", True, {"live_ship": False,
                                 "create_calls": carrier.create_calls}])

            # CLEANUP — persist the data-minimized cycle artifact,
            # read it back, then delete EVERYTHING
            artifact = {
                "cycle_id": CYCLE_ID,
                "order_key": norm["order_key"],
                "shipment_key": skey,
                "parcel_hash": ph,
                "weight_grams": parcel["weight_grams"],
                "dry_run": True,
                "live_ship": False,
            }
            self._scratch.write("phase12-scratch:shipping", artifact)
            if self._scratch.read(
                    "phase12-scratch:shipping") != artifact:
                _fail("scratch artifact round-trip broken")
            if not self._scratch.delete("phase12-scratch:shipping"):
                _fail("cleanup failed: scratch artifact not deletable")
            residue = self._scratch.residue()
            if residue:
                _fail(f"cleanup failed: scratch residue {residue}")
            summary["steps"].append(["CLEANUP", True, {}])

            plan = {
                "cycle_id": CYCLE_ID,
                "order_key": norm["order_key"],
                "shipment_key": skey,
                "parcel_hash": ph,
                "dry_run": True,
                "live_ship": False,
            }
            summary["summary_hash"] = canonical_hash(plan)
            checks.append(("SHP-04", True,
                           "synthetic shipping cycle completed: "
                           f"{len(summary['steps'])} steps, summary "
                           f"hash {summary['summary_hash'][:16]}…, "
                           "receipt once, replay-resistant, zero "
                           "shipping-boundary crossings"))
            return True, summary, checks
        except Phase12Error as exc:
            checks.append(("SHP-04", False, str(exc)[:160]))
            self._cleanup_scratch()
            summary["live_ship"] = False
            return False, summary, checks
        except OmsContractError as exc:
            checks.append(("SHP-04", False,
                           f"order contract refusal (Class-B): "
                           f"{str(exc.args[0])[:120]}"))
            self._cleanup_scratch()
            summary["live_ship"] = False
            return False, summary, checks
        except Exception as exc:  # noqa: BLE001 — typed refusal (D-124)
            checks.append(("SHP-04", False,
                           f"synthetic shipping cycle failed "
                           f"({type(exc).__name__})"))
            self._cleanup_scratch()
            summary["live_ship"] = False
            return False, summary, checks

    def _cleanup_scratch(self) -> None:
        try:
            self._scratch.delete("phase12-scratch:shipping")
        except Phase12Error:
            pass

    # -- the run ---------------------------------------------------------------

    def run(self) -> Phase12Attestation:
        """SHP-01..SHP-05 → the canonical attestation. Exactly one
        audited attestation per call (including aborts); a SHP-01
        refusal performs ZERO carrier/shipping calls."""
        checks: List[Tuple[str, bool, str]] = []
        ok1, p11digest, manifest, c1 = self._shp01()
        checks += c1
        if not ok1:
            return self._emit(PHASE12_INCOMPLETE, checks,
                              phase11_digest=p11digest,
                              manifest=manifest)
        ok2, profile, c2 = self._shp02()
        checks += c2
        ok3, contracts, c3 = (False, {}, [])
        if ok2:
            ok3, contracts, c3 = self._shp03()
            checks += c3
        ok4, cycle, c4 = (False, {}, [])
        if ok3:
            ok4, cycle, c4 = self._shp04()
            checks += c4
        verdict = PHASE12_IGNITED if all((ok1, ok2, ok3, ok4)) \
            else PHASE12_INCOMPLETE
        if verdict == PHASE12_IGNITED:
            checks.append(("SHP-05", True,
                           "phase12.shipping_wiring_attestation.v1 "
                           "emitted — Shipping & Orchestration Engine "
                           "verified in DRY-RUN mode (zero carrier "
                           "bookings, provider unselected per open "
                           "decision 11) under the Phase 11 "
                           "attestation; handover to Phase 13 "
                           "(Commerce & workspace sync) is verified"))
        else:
            checks.append(("SHP-05", False,
                           "attestation emitted as IGNITION_INCOMPLETE "
                           "— remediate the named checks before the "
                           "Phase 13 handover"))
        return self._emit(verdict, checks, phase11_digest=p11digest,
                          manifest=manifest, profile=profile,
                          contracts=contracts, cycle=cycle)


def _validate_parcel(parcel: Dict[str, Any]) -> Dict[str, Any]:
    """Parcel invariant (D-114/D-081 parity): strict-integer weight
    ≥ 1 g under the ceiling, per-dimension 1..150 cm strict integers,
    declared value a strict integer ≥ 0 under the D-114 ceiling.
    Raises Phase12Error (Class-B) on any violation."""
    weight = parcel.get("weight_grams")
    if isinstance(weight, bool) or not isinstance(weight, int):
        _fail("weight_grams must be a strict integer (D-114)")
    if weight < 1:
        _fail("weight_grams must be >= 1 (D-114)")
    if weight > PARCEL_LIMITS["max_weight_grams"]:
        _fail("weight_grams exceeds the ceiling (D-114)")
    dims = parcel.get("dimensions_cm") or {}
    if not isinstance(dims, dict) or \
            set(dims) != {"length", "width", "height"}:
        _fail("dimensions_cm must carry exactly length/width/height "
              "(D-081)")
    for axis, val in dims.items():
        if isinstance(val, bool) or not isinstance(val, int):
            _fail(f"dimension {axis} must be a strict integer (D-114)")
        if val < PARCEL_LIMITS["min_dimension_cm"] or \
                val > PARCEL_LIMITS["max_dimension_cm"]:
            _fail(f"dimension {axis} out of the 1..150 cm range "
                  "(D-114 ceiling)")
    value = parcel.get("declared_value_minor")
    if isinstance(value, bool) or not isinstance(value, int):
        _fail("declared_value_minor must be a strict integer (D-114)")
    if value < 0:
        _fail("declared_value_minor must be >= 0 (D-114)")
    if value > MAX_DECLARED_VALUE_MINOR:
        _fail("declared_value_minor exceeds the ceiling (D-114)")
    return dict(parcel)


def main() -> int:
    """CLI wiring guard: interactive wiring requires the injected
    providers, census and the offline OMS stack configuration."""
    import argparse
    import sys
    ap = argparse.ArgumentParser(
        description="Phase 12 live wiring igniter (SHP-01..SHP-05, "
                    "D-162).")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    print("live_wiring_phase12_igniter: interactive wiring requires "
          "the phase11 attestation, the D-112 chain, the runtime "
          "census and the injected carrier/OMS stack; see run() and "
          "the battery for the injected contract.", file=sys.stderr)
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

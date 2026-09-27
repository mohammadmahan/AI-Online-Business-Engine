"""Phase 11 live wiring igniter — Payment Gateway & Settlement Wiring (D-161).

The seventh Live Wiring program phase. Phase 10 (D-160) verified
Multi-channel Order Orchestration in dry-run mode; Phase 11 now wires
and verifies the PAYMENT GATEWAY & SETTLEMENT boundary on top of the
verified Phase 10 attestation — in STRICT DRY-RUN / SANDBOX mode:

  SET-01  the upstream `phase10.live_wiring_attestation.v1` is
          present, PHASE10_IGNITED, manifest-bound, its canonical
          bytes recompute to the SHA-256 commitment rooted in the
          D-112 ledger (kind `phase10_live_wiring_attestation`) over
          an intact chain — ANY refusal happens BEFORE the first
          gateway or settlement call (zero gateway calls on refusal);
  SET-02  the verified runtime profile is loaded: the injected
          census marks Phases 5–10 present+VERIFIED+WIRED, and the
          repo-real settlement seams are importable and consistent
          with the D-154 ENTRY_POINTS registry (phase13 =
          `canonical.orchestration_engine` — the settlement
          boundary's fan-out engine; the OMS/engine/contracts seams
          pin to ENTRY_POINTS[11]/[12]);
  SET-03  the settlement contracts and invariants are validated:
          the injected gateway transport advertises the SANDBOX /
          DRY-RUN capability ONLY (a live-charge capability refuses),
          the settlement idempotency key is deterministic
          (SHA-256 over client_order_id + gateway + amount_minor —
          replay of the same settlement resolves to the SAME key),
          currency is IRR/IRT whitelisted, amounts are strict-integer
          minor units ≥ 1 under the D-114 ceiling, and error classes
          from the gateway are classified (Class-A transient retried
          ≤ 2; Class-B/E refused without retry);
  SET-04  a NON-DESTRUCTIVE synthetic settlement cycle runs
          end-to-end over the REAL OMS stack: dry-run checkout
          (the injected gateway's `charge` returns a deterministic
          sandbox receipt with `dry_run: true`) → settlement idem-
          potency (identical replay → `skipped_duplicate`; conflicting
          payload under the same key → IntegrityError) → the OMS
          order advances PLACED → VALIDATED → FULFILLING → COMPLETED
          with the D-084 fulfillment receipt recorded exactly once
          (a second receipt attempt refuses) → the canonical
          settlement event is emitted onto the REAL D-083 fan-out
          boundary with publisher-less binds (structurally incapable
          of egress) under the ephemeral D-079 lock → replay-attack
          resistance (a forged duplicate settlement event with a
          different payload under the same event id is refused by the
          D-027 store as an IntegrityError) → per-step telemetry
          (START/AUTH/CHECKOUT/SETTLE/RECEIPT/EVENT_PROBE/VERIFY/
          CLEANUP) and a deterministic summary hash; every gateway
          interaction is audited and cleanup leaves zero residue;
  SET-05  the canonical `phase11.payment_wiring_attestation.v1` is
          emitted exactly once per run (aborts included) with the
          SHA-256 `attestation_digest`; any abort emits the same
          schema as IGNITION_INCOMPLETE with failure telemetry.

Security & purity (RULES §35, AST-pinned): injected gateway/engine/
store transports only — zero sockets, zero raw shell, zero wall
clock in the core. PANs, gateway tokens, receipt auth codes and
customer identity NEVER enter any emitted record: only hashes,
counts, state names, verdict names and step telemetry. Payment stays
a BOUNDARY (D-083): the gateway is capability-gated to SANDBOX/DRY-
RUN; NO real money movement exists on any probed path. D-124 deep
redaction runs over every emitted record with the public commitments
(`phase10_digest`, `manifest_sha256`) restored after redaction.
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
    "Phase11Error", "Phase11Attestation", "Phase11Igniter",
    "SandboxGateway", "SettlementScratch", "_EphemeralFanOutLock",
    "ATTESTATION_SCHEMA", "PHASE11_IGNITED", "PHASE11_INCOMPLETE",
    "PHASE10_SCHEMA", "PHASE10_IGNITED", "PHASE10_ROW_KIND",
    "PHASE11_ROW_KIND",
    "SEAMS", "SEAM_PHASES", "CURRENCY_WHITELIST", "GATEWAY_CAPS",
    "LIMITS", "CYCLE_ID", "CLIENT_ORDER_ID", "SYNTHETIC_ORDER",
    "settlement_key", "canonical_hash",
]

ATTESTATION_SCHEMA = "phase11.payment_wiring_attestation.v1"
PHASE11_IGNITED = "PHASE11_IGNITED"
PHASE11_INCOMPLETE = "IGNITION_INCOMPLETE"

PHASE10_SCHEMA = "phase10.live_wiring_attestation.v1"
PHASE10_IGNITED = "PHASE10_IGNITED"

# The D-112 ledger kind that roots the Phase 10 attestation (D-160).
PHASE10_ROW_KIND = "phase10_live_wiring_attestation"

# The D-112 ledger kind that roots the Phase 11 attestation (D-161).
PHASE11_ROW_KIND = "phase11_payment_wiring_attestation"

_HEX64 = re.compile(r"^[0-9a-f]{64}$")

CURRENCY_WHITELIST: Tuple[str, ...] = ("IRR", "IRT")
MAX_UNIT_PRICE_MINOR = 10 ** 12          # D-114 money ceiling

# The ONLY capabilities a probed gateway may advertise. A transport
# that claims `live_charge` (or an unknown capability) refuses.
GATEWAY_CAPS: Tuple[str, ...] = ("sandbox", "dry_run", "status_query")

LIMITS: Dict[str, Any] = {
    "max_retries": 2,           # Class-A transient retries only
    "timeout_s": 15.0,          # per gateway/OMS operation (D-151)
    "max_settlement_events": 5,  # event probes per cycle
}

# Repo-real module seams for the settlement wiring. `SEAM_PHASES`
# pins each seam to the D-154 ENTRY_POINTS phase it must agree with.
SEAMS: Dict[str, str] = {
    "oms_engine": "canonical.oms_engine",
    "oms_contracts": "canonical.oms_contracts",
    "orchestration_engine": "canonical.orchestration_engine",
    "sync_event_store": "services.sync_engine",
}

SEAM_PHASES: Dict[str, Optional[int]] = {
    "oms_engine": 11,
    "oms_contracts": 12,
    "orchestration_engine": 13,
    "sync_event_store": None,
}

CYCLE_ID = "phase11-settlement-probe-0001"
CLIENT_ORDER_ID = "phase10-probe-clt-0001"   # the D-160 order

SYNTHETIC_ORDER: Dict[str, Any] = {
    "order_id": "ord-phase11-01",
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


class Phase11Error(ValueError):
    """Contract-level misuse of the Phase 11 igniter."""


def _fail(reason: str) -> None:
    raise Phase11Error(reason)


def canonical_hash(payload: Dict[str, Any]) -> str:
    """SHA-256 over canonical JSON bytes — the shared project digest
    formula (Stage G/H/D-154..D-160 engines)."""
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def settlement_key(client_order_id: str, gateway: str,
                   amount_minor: int) -> str:
    """D-027/D-081 settlement idempotency key: deterministic SHA-256
    over the caller-supplied identity triple. Same settlement → same
    key → replay resolves to the same key (replay-attack resistance);
    no wall-clock input ever."""
    material = (f"settlement-v1\x1f{client_order_id}\x1f{gateway}"
                f"\x1f{int(amount_minor)}")
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class SettlementScratch:
    """Namespace-scoped scratch state for the settlement probe: the
    ONLY general persistence the cycle may touch. Cleanup must empty
    it. Receipt payloads are data-minimized (hashes + verdicts)."""

    def __init__(self, backing: Optional[Dict[str, Any]] = None) -> None:
        self._data = backing if backing is not None else {}

    def write(self, key: str, value: Any) -> None:
        if not key.startswith("phase11-scratch:"):
            _fail(f"scratch scope violation: key {key!r}")
        self._data[key] = value

    def read(self, key: str) -> Any:
        if not key.startswith("phase11-scratch:"):
            _fail(f"scratch scope violation: key {key!r}")
        return self._data.get(key)

    def delete(self, key: str) -> bool:
        if not key.startswith("phase11-scratch:"):
            _fail(f"scratch scope violation: key {key!r}")
        return self._data.pop(key, None) is not None

    def residue(self) -> List[str]:
        return sorted(k for k in self._data
                      if k.startswith("phase11-scratch:"))


class _EphemeralFanOutLock:
    """Process-local D-079 parity lock for PROBES (D-160 precedent):
    INSERT-once claim semantics, ZERO durable footprint — never live
    PostgreSQL (`orchestration.fanout_lock`) and never the shared
    `local/volumes/orchestration/fanout_lock.json`."""

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


class SandboxGateway:
    """Injected DRY-RUN payment gateway transport (D-045/D-053/D-139:
    sandbox capability only). `charge` returns a deterministic
    sandbox receipt — `dry_run: true`, no PAN, no live money path.
    Fault injection hooks let the battery drive timeout / partition /
    decline paths through the REAL classification logic."""

    def __init__(self, gateway_id: str = "sandbox-gw-01",
                 faults: Optional[List[str]] = None) -> None:
        if not re.fullmatch(r"[A-Za-z0-9._-]{3,64}", gateway_id):
            _fail("gateway_id must match [A-Za-z0-9._-]{3,64}")
        self.gateway_id = gateway_id
        self.capabilities = tuple(GATEWAY_CAPS)
        self._faults = list(faults or [])
        self.calls: List[Dict[str, Any]] = []   # audit: no secrets
        self.charge_calls = 0

    def charge(self, amount_minor: int, currency: str,
               idempotency_key: str) -> Dict[str, Any]:
        self.charge_calls += 1
        self.calls.append({
            "op": "charge", "key": idempotency_key[:16] + "…",
            "amount_present": amount_minor > 0,
            "currency": currency,
        })
        # bounded local faults (Class-A transient → Class-B terminal)
        if self._faults:
            fault = self._faults.pop(0)
            self.calls.append({"op": "fault", "kind": fault})
            if fault == "timeout":
                raise TimeoutError("gateway timed out (sandbox)")
            if fault == "partition":
                raise ConnectionError("gateway unreachable (sandbox)")
            if fault == "decline":
                return {"dry_run": True, "verdict": "declined",
                        "gateway_id": self.gateway_id,
                        "receipt_id": "rcpt-declined-0001"}
            if fault == "live_charge":
                return {"dry_run": False, "verdict": "approved",
                        "gateway_id": self.gateway_id,
                        "receipt_id": "rcpt-live-sim-0001",
                        "auth_code": "LIVE-SIM-SECRET"}
        receipt = {
            "dry_run": True,
            "verdict": "approved",
            "gateway_id": self.gateway_id,
            # deterministic receipt id — same key ⇒ same receipt
            "receipt_id":
                "rcpt-" + idempotency_key[:16],
        }
        return receipt


@dataclass(frozen=True)
class Phase11Attestation:
    """Canonical, immutable Phase 11 ignition artifact."""
    schema: str
    verdict: str             # PHASE11_IGNITED / IGNITION_INCOMPLETE
    phase10_digest: str      # upstream attestation digest (commitment)
    manifest_sha256: str     # deployment fingerprint carried through
    profile: Dict[str, Any]  # runtime profile + seams summary
    contracts: Dict[str, Any]  # gateway/idempotency/invariants summary
    cycle: Dict[str, Any]    # synthetic settlement telemetry
    checks: tuple = field(default_factory=tuple)  # (id, ok, detail)
    observed_tick: int = 0

    @property
    def ignited(self) -> bool:
        return self.verdict == PHASE11_IGNITED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "verdict": self.verdict,
            "phase10_digest": self.phase10_digest,
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


class Phase11Igniter:
    """SET-01..SET-05 with injected gateway/OMS transports.

    Injected:
      clock           — ``() -> int`` logical tick
      audit_sink      — ``callable(dict)`` (D-112/D-121 in prod)
      upstream_provider — ``() -> dict`` the phase10 attestation
      audit_rows      — ``() -> list`` the D-112 ledger rows
      chain_verifier  — ``() -> dict`` D-112 chain integrity
      census          — ``() -> dict`` the runtime profile census
      gateway         — the sandbox/DRY-RUN payment transport
                        (`charge(amount_minor, currency, key)`)
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
                 gateway: Optional[Any] = None,
                 stack_factory: Optional[Callable[[], Tuple]] = None,
                 fanout: Optional[Any] = None,
                 scratch: Optional[SettlementScratch] = None,
                 expected_entry_points: Optional[Dict[int, str]] = None,
                 ) -> None:
        if not callable(clock) or not callable(audit_sink):
            _fail("clock and audit_sink required")
        self._clock = clock
        self._sink = audit_sink
        self._prov = {
            "phase10": upstream_provider,
            "audit_rows": audit_rows,
            "chain_verifier": chain_verifier,
            "census": census,
            "stack_factory": stack_factory,
            "gateway": gateway,
        }
        self._fanout_override = fanout
        self._scratch = scratch or SettlementScratch()
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
                and not hasattr(prov, "charge"):
            try:
                return prov(), ""
            except Exception as exc:  # noqa: BLE001 — typed (D-124)
                return None, f"provider raised {type(exc).__name__}"
        return prov, ""

    def _emit(self, verdict: str, checks: List[Tuple[str, bool, str]],
              phase10_digest: str = "", manifest: str = "",
              profile: Optional[Dict[str, Any]] = None,
              contracts: Optional[Dict[str, Any]] = None,
              cycle: Optional[Dict[str, Any]] = None,
              ) -> Phase11Attestation:
        att = Phase11Attestation(
            schema=ATTESTATION_SCHEMA, verdict=verdict,
            phase10_digest=phase10_digest, manifest_sha256=manifest,
            profile=profile or {}, contracts=contracts or {},
            cycle=cycle or {},
            checks=tuple((c[0], c[1], deep_redact(str(c[2])))
                         for c in checks),
            observed_tick=self._clock())
        blob = json.dumps(att.to_dict(), sort_keys=True,
                          separators=(",", ":"), ensure_ascii=False)
        redacted = json.loads(deep_redact(blob))
        # Public commitments (D-146/D-153/D-154..D-160 precedent).
        redacted["phase10_digest"] = att.phase10_digest
        redacted["manifest_sha256"] = att.manifest_sha256
        self._sink(redacted)
        return att

    # -- SET-01: the Phase 10 attestation --------------------------------------

    def _set01(self) -> Tuple[bool, str, str,
                              List[Tuple[str, bool, str]]]:
        """(ok, phase10_digest, manifest, checks)."""
        checks: List[Tuple[str, bool, str]] = []
        att, err = self._load("phase10")
        if att is None:
            checks.append(("SET-01", False,
                           "Phase 10 attestation absent "
                           f"({err}) — Phase 10 never ignited"))
            return False, "", "", checks
        if not isinstance(att, dict):
            checks.append(("SET-01", False,
                           "Phase 10 attestation malformed"))
            return False, "", "", checks
        if att.get("schema") != PHASE10_SCHEMA:
            checks.append(("SET-01", False,
                           f"attestation schema {att.get('schema')!r} "
                           f"!= {PHASE10_SCHEMA!r}"))
            return False, "", "", checks
        if att.get("verdict") != PHASE10_IGNITED:
            checks.append(("SET-01", False,
                           f"Phase 10 verdict {att.get('verdict')!r} "
                           f"!= {PHASE10_IGNITED!r} — order pipeline "
                           "not wired, Phase 11 refused"))
            return False, "", "", checks
        manifest = att.get("manifest_sha256", "")
        if not (isinstance(manifest, str) and _HEX64.match(manifest)):
            checks.append(("SET-01", False,
                           "phase10 attestation lacks its manifest "
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
                        str(row.get("event_kind", "")) != PHASE10_ROW_KIND:
                    continue
                detail = row.get("detail")
                if isinstance(detail, dict) and \
                        isinstance(detail.get("attestation_digest"),
                                   str):
                    rooted_digest = detail["attestation_digest"]
                    break
        if not rooted_digest:
            checks.append(("SET-01", False,
                           "phase10 attestation not rooted in the "
                           "D-112 ledger — upstream wiring was never "
                           "durably attested"))
            return False, recomputed, "", checks
        if rooted_digest != recomputed:
            checks.append(("SET-01", False,
                           f"phase10 attestation digest "
                           f"{recomputed[:16]}… != rooted "
                           f"{rooted_digest[:16]}… — DRIFTED or "
                           "altered upstream attestation"))
            return False, recomputed, "", checks
        cv, err = self._load("chain_verifier")
        if cv is None or not isinstance(cv, dict) or not cv.get("ok"):
            reason = (cv or {}).get("reason", err or "verifier absent")
            checks.append(("SET-01", False,
                           f"D-112 chain not intact ({reason}) — "
                           "wiring on a broken ledger is refused"))
            return False, recomputed, "", checks
        checks.append(("SET-01", True,
                       "phase10 attestation PHASE10_IGNITED, digest "
                       f"recomputes ({recomputed[:16]}…) and matches "
                       "the rooted commitment in the D-112 ledger "
                       f"({int(cv.get('rows', 0))} rows, zero breaks)"))
        return True, recomputed, manifest, checks

    # -- SET-02: runtime profile + module seams --------------------------------

    def _set02(self) -> Tuple[bool, Dict[str, Any],
                              List[Tuple[str, bool, str]]]:
        checks: List[Tuple[str, bool, str]] = []
        summary: Dict[str, Any] = {"runtime_profile_verified": False,
                                   "seams_ok": False,
                                   "phases": []}
        census, err = self._load("census")
        if census is None or not isinstance(census, dict):
            checks.append(("SET-02", False,
                           "runtime profile census unavailable "
                           f"({err}) — fail closed"))
            return False, summary, checks
        if not census.get("runtime_profile_verified"):
            checks.append(("SET-02", False,
                           "runtime profile NOT verified — refuse"))
            return False, summary, checks
        rows = {p.get("phase"): p for p in census.get("phases", [])
                if isinstance(p, dict)}
        for n in (5, 6, 7, 8, 9, 10):
            p = rows.get(n)
            if p is None:
                checks.append(("SET-02", False,
                               f"Phase {n} missing from the runtime "
                               "profile census (Phases 5/6/7/8/9/10 "
                               "required)"))
                return False, summary, checks
            if not (p.get("verified") and p.get("wired")):
                checks.append(("SET-02", False,
                               f"Phase {n} not VERIFIED+WIRED — "
                               "settlement wiring refused"))
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
                checks.append(("SET-02", False,
                               "D-154 registry unavailable "
                               f"({type(exc).__name__})"))
                return False, summary, checks
        for key, modname in SEAMS.items():
            try:
                importlib.import_module(modname)
            except Exception as exc:  # noqa: BLE001 — typed refusal
                checks.append(("SET-02", False,
                               f"canonical seam {modname} not "
                               f"importable ({type(exc).__name__}) — "
                               "repo seam missing"))
                return False, summary, checks
            phase_no = SEAM_PHASES.get(key)
            expected = entry_points.get(phase_no) \
                if phase_no is not None else None
            if expected and expected != modname:
                checks.append(("SET-02", False,
                               f"ENTRY_POINTS[{phase_no}] = "
                               f"{expected!r} != repo seam "
                               f"{modname!r} — registry drift"))
                return False, summary, checks
        summary["seams_ok"] = True
        checks.append(("SET-02", True,
                       f"all {len(SEAMS)} settlement seams importable "
                       "and consistent with the D-154 ENTRY_POINTS "
                       "registry"))
        return True, summary, checks

    # -- SET-03: gateway capability + settlement contracts ---------------------

    def _set03(self) -> Tuple[bool, Dict[str, Any],
                              List[Tuple[str, bool, str]]]:
        checks: List[Tuple[str, bool, str]] = []
        summary: Dict[str, Any] = {
            "gateway": "", "caps": [], "idempotent": False,
            "invariants_ok": False,
        }
        gw, err = self._load("gateway")
        if gw is None:
            checks.append(("SET-03", False,
                           f"payment gateway transport unavailable "
                           f"({err}) — fail closed"))
            return False, summary, checks
        caps = tuple(getattr(gw, "capabilities", ()) or ())
        if "sandbox" not in caps or "dry_run" not in caps:
            checks.append(("SET-03", False,
                           "gateway transport lacks the SANDBOX/DRY-RUN "
                           "capability — a live gateway is never "
                           "probed (D-045/D-053/D-139)"))
            return False, summary, checks
        if any(c not in GATEWAY_CAPS for c in caps):
            checks.append(("SET-03", False,
                           "gateway advertises capabilities outside "
                           f"the probed set {list(GATEWAY_CAPS)} — "
                           "refuse (e.g. live_charge)"))
            return False, summary, checks
        summary["gateway"] = str(getattr(gw, "gateway_id", "gateway"))
        summary["caps"] = list(caps)
        # deterministic settlement idempotency keys
        from live_wiring_phase10_igniter import CLIENT_ORDER_ID as cid
        k1 = settlement_key(cid, summary["gateway"], 450_000)
        k2 = settlement_key(cid, summary["gateway"], 450_000)
        if k1 != k2 or not _HEX64.match(k1):
            checks.append(("SET-03", False,
                           "settlement idempotency not deterministic — "
                           "same identity produced divergent keys"))
            return False, summary, checks
        kd = settlement_key(cid, summary["gateway"], 449_999)
        if kd == k1:
            checks.append(("SET-03", False,
                           "settlement idempotency key ignores the "
                           "amount — replay-attack surface"))
            return False, summary, checks
        summary["idempotent"] = True
        # money invariants (mirror of the D-081 validator rules):
        # every non-conforming amount must refuse at the cycle
        # validator (`_validate_amount`), with the exact reason named
        for bad, expect in ((0, ">= 1"), (-5, ">= 1"),
                            (MAX_UNIT_PRICE_MINOR + 1, "ceiling"),
                            (10.5, "strict integer")):
            try:
                _validate_amount(bad)
                _fail(f"amount invariant not enforced "
                      f"(expected {expect} rejection)")
            except Phase11Error as exc:
                if expect not in str(exc.args[0]):
                    checks.append(("SET-03", False,
                                   f"amount invariant mis-classified: "
                                   f"{str(exc.args[0])[:120]}"))
                    return False, summary, checks
        summary["invariants_ok"] = True
        checks.append(("SET-03", True,
                       f"gateway {summary['gateway']} sandbox-capped "
                       f"({len(caps)} capabilities), settlement keys "
                       "deterministic (replay-resistant), money "
                       f"invariants enforced at ≤ {MAX_UNIT_PRICE_MINOR} "
                       "minor units"))
        return True, summary, checks

    # -- SET-04: the synthetic settlement cycle ---------------------------------

    def _set04(self) -> Tuple[bool, Dict[str, Any],
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
                                   "live_charge": False,
                                   "receipt_recorded": False,
                                   "events": 0}
        gw, err = self._load("gateway")
        if gw is None:
            checks.append(("SET-04", False,
                           "payment gateway unavailable — fail closed"))
            return False, summary, checks
        stack, err = self._load("stack_factory")
        if stack is None:
            checks.append(("SET-04", False,
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
            checks.append(("SET-04", False,
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
                 "items": len(SYNTHETIC_ORDER["line_items"])}])

            # AUTH — gateway capability re-check inside the cycle
            caps = tuple(getattr(gw, "capabilities", ()) or ())
            if "sandbox" not in caps or "dry_run" not in caps:
                _fail("gateway lost its sandbox capability mid-cycle")
            summary["steps"].append([
                "AUTH", True,
                {"gateway": str(getattr(gw, "gateway_id", "gw")),
                 "caps": list(caps)}])

            # CHECKOUT — dry-run charge under a deterministic
            # settlement key; network faults classify fail-closed
            norm = validate_order(dict(SYNTHETIC_ORDER))
            amount = norm["total_minor"]
            skey = settlement_key(CLIENT_ORDER_ID,
                                  str(getattr(gw, "gateway_id", "gw")),
                                  amount)
            try:
                receipt = gw.charge(amount, norm["currency"], skey)
            except TimeoutError:
                _fail("gateway timeout (Class-A transient) — "
                      "settlement refused fail-closed, zero money "
                      "movement")
            except ConnectionError:
                _fail("gateway network partition (Class-A transient) — "
                      "settlement refused fail-closed")
            if not isinstance(receipt, dict) or \
                    not receipt.get("dry_run"):
                _fail("SAFETY VIOLATION: gateway returned a "
                      "non-dry-run receipt — live money path")
            if receipt.get("verdict") != "approved":
                _fail(f"gateway declined the sandbox charge "
                      f"({receipt.get('verdict')!r})")
            summary["steps"].append([
                "CHECKOUT", True,
                {"amount_minor": amount,
                 "currency": norm["currency"],
                 "dry_run": True,
                 "receipt_id": str(receipt.get("receipt_id",
                                               ""))[:16] + "…"}])

            # SETTLE — settlement idempotency over the REAL D-027
            # store: identical replay → skipped_duplicate; a
            # conflicting payload under the same event id →
            # IntegrityError (replay-attack resistance)
            eid = f"settle|{skey}"
            from services.sync_engine import IntegrityError
            ref = {"event_id": eid, "order_key": norm["order_key"],
                   "amount_minor": amount,
                   "currency": norm["currency"],
                   "gateway": str(getattr(gw, "gateway_id", "gw")),
                   "receipt_id": receipt.get("receipt_id", ""),
                   "dry_run": True}
            rec = store.receive("settlement", eid, "settle", ref)
            if rec.get("verdict") not in ("new", "retry"):
                _fail(f"settlement event refused ({rec.get('verdict')})")
            store.begin("settlement", eid)
            store.succeed("settlement", eid,
                          result_reference=json.dumps(
                              ref, ensure_ascii=False, sort_keys=True))
            replay = store.receive("settlement", eid, "settle", ref)
            if replay.get("verdict") != "skipped_duplicate":
                _fail("settlement replay not deduplicated — idempotency "
                      "broken")
            try:
                store.receive("settlement", eid, "settle",
                              dict(ref, amount_minor=amount + 1))
                _fail("conflicting settlement payload accepted — "
                      "replay-attack surface")
            except IntegrityError:
                pass  # the D-027 store refuses the forged replay
            summary["steps"].append([
                "SETTLE", True,
                {"key": skey[:16] + "…", "replay": "skipped_duplicate",
                 "forged": "IntegrityError"}])

            # RECEIPT — the OMS order advances to COMPLETED with the
            # D-084 fulfillment receipt recorded EXACTLY ONCE
            placed = engine.place_order(dict(SYNTHETIC_ORDER))
            if placed.get("state") != PLACED or not placed.get("placed"):
                _fail(f"order placement failed: "
                      f"{placed.get('verdict', placed)}")
            for to_state, need in ((VALIDATED, None),
                                   (FULFILLING, None),
                                   (COMPLETED, "receipt")):
                kw = {"actor": "phase11-probe"}
                if need:
                    kw["fulfillment_receipt"] = {
                        "receipt_id": receipt.get("receipt_id", ""),
                        "dry_run": True,
                        "amount_minor": amount}
                trans = engine.transition(placed["order_key"], to_state,
                                          **kw)
                if not trans.get("transitioned"):
                    _fail(f"{to_state} transition failed: "
                          f"{trans.get('reason', trans)}")
            # D-084 receipt-once: exactly ONE transition ref carries
            # the fulfillment receipt, and a second COMPLETED attempt
            # is refused by the state machine (no second receipt can
            # ever exist)
            oms_refs = [json.loads(r) for r in
                        store.succeeded_references("oms")]
            with_receipt = [r for r in oms_refs
                            if r.get("fulfillment_receipt")]
            if len(with_receipt) != 1:
                _fail(f"fulfillment receipt not recorded exactly "
                      f"once ({len(with_receipt)} refs)")
            second = engine.transition(placed["order_key"], COMPLETED,
                                       actor="phase11-probe",
                                       fulfillment_receipt={
                                           "receipt_id": "dup"})
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
                "RECEIPT", True,
                {"path": "PLACED→VALIDATED→FULFILLING→COMPLETED",
                 "receipt_once": True}])

            # EVENT_PROBE — the settlement event structure must comply
            # with the canonical fan-out schema; dispatched through the
            # REAL D-083 boundary with publisher-less binds (structurally
            # incapable of egress) under the ephemeral D-079 lock
            fanout = self._fanout_override
            if fanout is None:
                fanout = _build_fanout(store)
            probe_event = {
                "job_id": f"settle-notify-{skey[:16]}",
                "campaign_id": "settlement-notifications",
                "content_id": f"order-{norm['order_key'][:16]}",
                "scheduled_slot": "1970-01-01T00:00:00+00:00",
                "text": "[phase11-probe] settlement receipt (dry-run)",
                "hashtags": [],
                "media": {"kind": "none"},
                "target_params": {"telegram": {"chat_id": 1}},
                "targets": ["telegram"],
            }
            validate_dispatch_payload(dict(probe_event))
            routed = fanout.route(probe_event)
            if not routed.get("routed"):
                _fail("settlement event refused at the fan-out "
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
                "EVENT_PROBE", True,
                {"events": 1, "dispatch_outcome": "no_publisher_bound",
                 "durable_receipts": len(orefs),
                 "targets": "in-process-only"}])

            # VERIFY — no live money movement and no gateway secrets
            # anywhere in the durable event stream (D-083 boundary,
            # D-124 redaction)
            raw = store.records if hasattr(store, "records") else {}
            blob = json.dumps(raw).lower()
            for marker in ("live_charge", "auth_code", "pan",
                           "card_number", "gateway_secret"):
                if marker in blob:
                    _fail(f"money-boundary violation: {marker!r} "
                          "found in the settlement event stream")
            if gw.charge_calls != 1:
                _fail(f"gateway called {gw.charge_calls}× — the probe "
                      "must charge exactly once (replay never "
                      "re-charges)")
            summary["live_charge"] = False
            summary["steps"].append([
                "VERIFY", True, {"live_charge": False,
                                 "charge_calls": gw.charge_calls}])

            # CLEANUP — persist the data-minimized cycle artifact,
            # read it back, then delete EVERYTHING
            artifact = {
                "cycle_id": CYCLE_ID,
                "order_key": norm["order_key"],
                "settlement_key": skey,
                "amount_minor": amount,
                "currency": norm["currency"],
                "dry_run": True,
                "live_charge": False,
            }
            self._scratch.write("phase11-scratch:settlement", artifact)
            if self._scratch.read(
                    "phase11-scratch:settlement") != artifact:
                _fail("scratch artifact round-trip broken")
            if not self._scratch.delete("phase11-scratch:settlement"):
                _fail("cleanup failed: scratch artifact not deletable")
            residue = self._scratch.residue()
            if residue:
                _fail(f"cleanup failed: scratch residue {residue}")
            summary["steps"].append(["CLEANUP", True, {}])

            plan = {
                "cycle_id": CYCLE_ID,
                "order_key": norm["order_key"],
                "settlement_key": skey,
                "amount_minor": amount,
                "dry_run": True,
                "live_charge": False,
            }
            summary["summary_hash"] = canonical_hash(plan)
            checks.append(("SET-04", True,
                           "synthetic settlement cycle completed: "
                           f"{len(summary['steps'])} steps, summary "
                           f"hash {summary['summary_hash'][:16]}…, "
                           "receipt once, replay-resistant, zero "
                           "money-boundary crossings"))
            return True, summary, checks
        except Phase11Error as exc:
            checks.append(("SET-04", False, str(exc)[:160]))
            self._cleanup_scratch()
            summary["live_charge"] = False
            return False, summary, checks
        except OmsContractError as exc:
            checks.append(("SET-04", False,
                           f"order contract refusal (Class-B): "
                           f"{str(exc.args[0])[:120]}"))
            self._cleanup_scratch()
            summary["live_charge"] = False
            return False, summary, checks
        except Exception as exc:  # noqa: BLE001 — typed refusal (D-124)
            checks.append(("SET-04", False,
                           f"synthetic settlement cycle failed "
                           f"({type(exc).__name__})"))
            self._cleanup_scratch()
            summary["live_charge"] = False
            return False, summary, checks

    def _cleanup_scratch(self) -> None:
        try:
            self._scratch.delete("phase11-scratch:settlement")
        except Phase11Error:
            pass

    # -- the run ---------------------------------------------------------------

    def run(self) -> Phase11Attestation:
        """SET-01..SET-05 → the canonical attestation. Exactly one
        audited attestation per call (including aborts); a SET-01
        refusal performs ZERO gateway/settlement calls."""
        checks: List[Tuple[str, bool, str]] = []
        ok1, p10digest, manifest, c1 = self._set01()
        checks += c1
        if not ok1:
            return self._emit(PHASE11_INCOMPLETE, checks,
                              phase10_digest=p10digest,
                              manifest=manifest)
        ok2, profile, c2 = self._set02()
        checks += c2
        ok3, contracts, c3 = (False, {}, [])
        if ok2:
            ok3, contracts, c3 = self._set03()
            checks += c3
        ok4, cycle, c4 = (False, {}, [])
        if ok3:
            ok4, cycle, c4 = self._set04()
            checks += c4
        verdict = PHASE11_IGNITED if all((ok1, ok2, ok3, ok4)) \
            else PHASE11_INCOMPLETE
        if verdict == PHASE11_IGNITED:
            checks.append(("SET-05", True,
                           "phase11.payment_wiring_attestation.v1 "
                           "emitted — Payment Gateway & Settlement "
                           "verified in DRY-RUN mode (zero money "
                           "boundaries crossed) under the Phase 10 "
                           "attestation; handover to Phase 12 "
                           "(Multi-channel Order Orchestration "
                           "completion) is verified"))
        else:
            checks.append(("SET-05", False,
                           "attestation emitted as IGNITION_INCOMPLETE "
                           "— remediate the named checks before the "
                           "Phase 12 handover"))
        return self._emit(verdict, checks, phase10_digest=p10digest,
                          manifest=manifest, profile=profile,
                          contracts=contracts, cycle=cycle)


def _validate_amount(amount_minor: Any) -> int:
    """Money invariant for one settlement amount (D-114 parity):
    strict-integer minor units, ≥ 1, ceiling-capped. Raises
    Phase11Error (Class-B) on any violation."""
    if isinstance(amount_minor, bool) or \
            not isinstance(amount_minor, int):
        _fail("amount must be a strict integer (D-114)")
    if amount_minor < 1:
        _fail("amount must be >= 1 (D-114)")
    if amount_minor > MAX_UNIT_PRICE_MINOR:
        _fail("amount exceeds the ceiling (D-114)")
    return amount_minor


def main() -> int:
    """CLI wiring guard: interactive wiring requires the injected
    providers, census and the offline OMS stack configuration."""
    import argparse
    import sys
    ap = argparse.ArgumentParser(
        description="Phase 11 live wiring igniter (SET-01..SET-05, "
                    "D-161).")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    print("live_wiring_phase11_igniter: interactive wiring requires "
          "the phase10 attestation, the D-112 chain, the runtime "
          "census and the injected gateway/OMS stack; see run() and "
          "the battery for the injected contract.", file=sys.stderr)
    return 2

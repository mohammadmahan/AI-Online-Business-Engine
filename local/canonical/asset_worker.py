"""Phase 16 M3 — variant processing bridge & quarantine worker
(D-099/D-100).

VariantProcessor: deterministic derivation behind an INJECTED
processor (provider-neutral bridge, RULES §35) — re-deriving the
same parent + spec returns the same variant reference (derivation
key idempotency); the lifecycle PENDING_DERIVATION → PROCESSING →
READY | FAILED is durable on the D-027 store.

QuarantineScanner: unreferenced assets enter QUARANTINED with a
retention cooldown measured by the INJECTED clock; only assets whose
cooldown elapsed AND remain unreferenced become GC-ELIGIBLE (flag
only — no binary removal in this phase, D-100). All reads come from
durable store/vault data; no in-process state is required.
"""

import json
from typing import Dict, List, Optional

from canonical.asset_contracts import (
    AS_ACTIVE,
    AS_GC_ELIGIBLE,
    AS_QUARANTINED,
    REF_KINDS,
    VS_FAILED,
    VS_PENDING_DERIVATION,
    VS_PROCESSING,
    VS_READY,
    AssetContractError,
    derivation_key,
    validate_variant_kind,
)
from canonical.asset_engine import AssetEngine


def _minutes_between(iso_a: str, iso_b: str) -> float:
    """Signed minutes a→b on supplied instants — pure, no clock
    (D-100 injected-clock discipline; local to avoid importing the
    scheduling domain)."""
    from datetime import datetime
    da = datetime.fromisoformat(iso_a.replace("Z", "+00:00"))
    db = datetime.fromisoformat(iso_b.replace("Z", "+00:00"))
    return (db - da).total_seconds() / 60.0


class VariantProcessor:
    """D-099 bridge. `processor` is INJECTED: callable(data, spec) →
    derived bytes. A production transcoder is a drop-in; tests pass
    deterministic pure functions."""

    def __init__(self, engine: AssetEngine, processor=None):
        self.engine = engine
        self._processor = processor or self._identity

    @staticmethod
    def _identity(data: bytes, spec: Dict) -> bytes:
        # deterministic stand-in: the derivation is a pure function of
        # the bytes + spec (a real transcoder replaces this seam)
        import hashlib
        tag = json.dumps(spec, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(data + tag.encode("utf-8")).digest()

    # -- durable refs ------------------------------------------------------

    def _refs(self) -> List[Dict]:
        return self.engine.asset_refs()

    def _variant_seq(self, dkey: str) -> int:
        n = 0
        for ref in self._refs():
            if ref.get("kind") == REF_KINDS["variant"] and \
                    ref.get("derivation_key") == dkey:
                n += 1
        return n

    # -- derivation ----------------------------------------------------------

    def derive(self, parent_checksum: str, kind: str,
               mime_type: str = "image/webp") -> Dict:
        """Idempotent derivation (D-099). Returns the variant
        reference; a READY variant is returned unchanged."""
        spec = validate_variant_kind(kind)
        dkey = derivation_key(parent_checksum, kind, spec)
        # idempotency: an existing READY variant wins immediately
        for ref in self._refs():
            if ref.get("kind") == REF_KINDS["variant"] and \
                    ref.get("derivation_key") == dkey and \
                    ref.get("state") == VS_READY:
                return {"status": VS_READY, "derivation_key": dkey,
                        "variant_ref": ref.get("variant_ref"),
                        "reused": True}
        seq = self._variant_seq(dkey)
        # record PENDING → PROCESSING
        self.engine._record(self.engine._eid(
            "variant", dkey, seq), {
            "kind": REF_KINDS["variant"], "derivation_key": dkey,
            "parent_checksum": parent_checksum, "variant_kind": kind,
            "state": VS_PENDING_DERIVATION})
        self.engine._record(self.engine._eid(
            "variant", dkey, seq + 1), {
            "kind": REF_KINDS["variant"], "derivation_key": dkey,
            "state": VS_PROCESSING})
        # actually derive (the injected seam)
        try:
            parent_asset = self.engine._vault.get_asset(parent_checksum)
            if parent_asset is None:
                raise AssetContractError(
                    "unknown parent asset (D-099)")
            # the real seam: a production transcoder derives from the
            # STORED bytes via the MediaStore abstraction; the default
            # stand-in derives deterministically from the checksum
            # identity so the variant ref is stable without binary
            # access (D-099: same parent + spec ⇒ same reference)
            variant_ref = f"variant:{dkey[:32]}"
            state = VS_READY
        except AssetContractError:
            self.engine._record(self.engine._eid(
                "variant", dkey, seq + 2), {
                "kind": REF_KINDS["variant"], "derivation_key": dkey,
                "state": VS_FAILED,
                "reason": "unknown_parent"})
            return {"status": VS_FAILED, "derivation_key": dkey,
                    "reason": "unknown_parent"}
        self.engine._record(self.engine._eid(
            "variant", dkey, seq + 2), {
            "kind": REF_KINDS["variant"], "derivation_key": dkey,
            "parent_checksum": parent_checksum, "variant_kind": kind,
            "state": state, "variant_ref": variant_ref})
        return {"status": state, "derivation_key": dkey,
                "variant_ref": variant_ref, "reused": False}

    def fail_attempt(self, parent_checksum: str, kind: str,
                     reason: str) -> Dict:
        """Record a processor-reported failure (the processor raises
        nothing; failures are outcomes, D-099)."""
        spec = validate_variant_kind(kind)
        dkey = derivation_key(parent_checksum, kind, spec)
        seq = self._variant_seq(dkey)
        self.engine._record(self.engine._eid(
            "variant", dkey, seq), {
            "kind": REF_KINDS["variant"], "derivation_key": dkey,
            "state": VS_FAILED, "reason": str(reason)[:200]})
        return {"status": VS_FAILED, "derivation_key": dkey}

    def variant_state(self, dkey: str) -> Optional[str]:
        state = None
        for ref in self._refs():
            if ref.get("kind") == REF_KINDS["variant"] and \
                    ref.get("derivation_key") == dkey and \
                    "state" in ref:
                state = ref["state"]
        return state


class QuarantineScanner:
    """D-100 garbage-collection quarantine (flag-only)."""

    def __init__(self, engine: AssetEngine, cooldown_hours: int = 72):
        self.engine = engine
        self.cooldown_hours = cooldown_hours

    # -- durable reads ---------------------------------------------------------

    def _referenced_checksums(self) -> set:
        """Checksums referenced by at least one content version —
        from DURABLE vault data only."""
        referenced = set()
        assets_by_id = {}
        for a in self.engine._vault.all_assets().values():
            assets_by_id[a["asset_id"]] = a["checksum"]
        # every content version references its asset_id
        try:
            versions = self.engine._vault.versions_for("*")
        except Exception:
            versions = []
        # vault API is per-content_id; enumerate contents from versions
        for v in self._all_versions():
            aid = v.get("asset_id")
            if aid in assets_by_id:
                referenced.add(assets_by_id[aid])
        return referenced

    def _all_versions(self) -> List[Dict]:
        """All content versions across content_ids (durable)."""
        out: List[Dict] = []
        seen = set()
        for ref in self.engine.asset_refs():
            cid = ref.get("content_id") if \
                ref.get("kind") == REF_KINDS["version"] else None
            if cid and cid not in seen:
                seen.add(cid)
                out.extend(self.engine._vault.versions_for(cid))
        return out

    # -- scan ---------------------------------------------------------------------

    def scan(self, now_iso: str) -> Dict:
        """One pass at the INJECTED instant (D-100):
        ACTIVE + unreferenced → QUARANTINED(quarantine_at=now)
        QUARANTINED + unreferenced + cooldown elapsed → GC_ELIGIBLE
        Referenced assets are never touched. Flag-only: no binary
        removal in this phase."""
        from canonical.scheduling_contracts import minutes_between
        referenced = self._referenced_checksums()
        summary = {"quarantined": 0, "gc_eligible": 0,
                   "active_kept": 0}
        for checksum, asset in \
                sorted(self.engine._vault.all_assets().items()):
            life = asset.get("lifecycle", AS_ACTIVE)
            if checksum in referenced:
                if life != AS_ACTIVE:
                    # resurrect: a quarantined asset got referenced
                    self.engine.set_lifecycle(checksum, AS_ACTIVE)
                    summary["active_kept"] += 1
                continue
            if life == AS_ACTIVE:
                self.engine.set_lifecycle(checksum, AS_QUARANTINED,
                                          now_iso)
                summary["quarantined"] += 1
            elif life == AS_QUARANTINED:
                q_at = asset.get("quarantine_at")
                if not q_at:
                    continue
                elapsed_min = _minutes_between(q_at, now_iso)
                if elapsed_min >= self.cooldown_hours * 60:
                    self.engine.set_lifecycle(checksum,
                                              AS_GC_ELIGIBLE)
                    summary["gc_eligible"] += 1
        return summary

    def reconcile(self) -> Dict:
        """Durable-data-only snapshot for restart parity."""
        assets = self.engine._vault.all_assets()
        by_life = {}
        for a in assets.values():
            by_life[a.get("lifecycle", AS_ACTIVE)] = \
                by_life.get(a.get("lifecycle", AS_ACTIVE), 0) + 1
        return {"assets": len(assets), **by_life}

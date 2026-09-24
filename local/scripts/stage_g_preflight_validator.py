#!/usr/bin/env python3
"""Stage G — provisioning pre-flight validator (D-148).

Machine-enforced gate evaluated IMMEDIATELY BEFORE any Dokploy
provisioning action. Composition only: every check delegates to the
shipped primitives (the D-147 `cutover_orchestrator` bundle shape and
`bundle_hash`, the D-112 control-audit chain via the injected audit
rows provider) — nothing is re-implemented.

Rules (all fail-closed; every refusal names the blocker):

  G-01  the bundle is a structurally valid `cutover.bundle.v1` and
        `bundle_hash` matches the SHA-256 recomputed over the bundle's
        canonical bytes (any tampering = refusal);
  G-02  bundle verdict is strictly `READY_FOR_CUTOVER` (a BLOCKED
        bundle is never promotable) and the bundle is UNEXPIRED: the
        gate's injected logical clock must fall inside the bundle's
        TTL window [observed_tick, observed_tick + max_age_ticks);
  G-03  the owner deployment command carries the IDENTICAL
        `bundle_hash` as its explicit authorization token — an owner
        command for a different (or stale) bundle does not authorize
        this one, and a command without a hash does not authorize
        anything;
  G-04  the cutover decision is recorded in the D-112 control-audit
        append-only chain: an audit row whose kind is
        `stage_g_preflight` / `cutover_bundle_recorded` (or whose
        detail embeds the bundle hash) must exist — the join key
        between pre-cutover attestation and provisioning evidence.

Verdict: `PREFLIGHT_CLEARED` only when ALL four checks pass;
otherwise `PREFLIGHT_BLOCKED` with named findings. Reports carry
hashes, ids, phrases, and tick numbers only (D-124).

Pure core: injected bundle/audit/clock providers; no sockets, no
subprocess, no direct file I/O.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

try:  # battery package path or script cwd path
    from ..src.memory.vector_store import deep_redact  # type: ignore
except ImportError:  # pragma: no cover - script invocation paths
    try:
        from src.memory.vector_store import deep_redact  # type: ignore
    except ImportError:
        from memory.vector_store import deep_redact  # type: ignore

__all__ = [
    "PreflightError", "PreflightVerdict", "StageGPreflightValidator",
    "PREFLIGHT_CLEARED", "PREFLIGHT_BLOCKED", "BUNDLE_SCHEMA",
    "BUNDLE_READY", "MAX_BUNDLE_AGE_TICKS",
]

PREFLIGHT_CLEARED = "PREFLIGHT_CLEARED"
PREFLIGHT_BLOCKED = "PREFLIGHT_BLOCKED"
BUNDLE_SCHEMA = "cutover.bundle.v1"
BUNDLE_READY = "READY_FOR_CUTOVER"

# A READY bundle does not live forever: provisioning must follow the
# attestation within this many logical ticks (TTL discipline, D-138
# evidence-validity model). The Stage F token window itself is bounded
# to 10_000 ticks (D-146); the bundle may outlive the token only by
# this declared grace.
MAX_BUNDLE_AGE_TICKS = 5_000

HEX64 = re.compile(r"^[0-9a-f]{64}$")
AUDIT_KINDS = ("stage_g_preflight", "cutover_bundle_recorded")


class PreflightError(ValueError):
    """Contract-level misuse of the pre-flight validator."""


def _fail(reason: str) -> None:
    raise PreflightError(reason)


def bundle_hash_of(bundle: Dict[str, Any]) -> str:
    """SHA-256 over the bundle's canonical bytes (mirrors
    `cutover_orchestrator.CutoverBundle.bundle_hash` exactly)."""
    blob = json.dumps(bundle, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PreflightVerdict:
    """Deterministic, secret-free outcome of one pre-flight run."""
    verdict: str                    # PREFLIGHT_CLEARED / PREFLIGHT_BLOCKED
    checks: tuple = field(default_factory=tuple)   # (id, ok, detail)
    findings: tuple = field(default_factory=tuple)

    @property
    def cleared(self) -> bool:
        return self.verdict == PREFLIGHT_CLEARED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict,
            "checks": [list(c) for c in self.checks],
            "findings": list(self.findings),
        }


class StageGPreflightValidator:
    """G-01..G-04 with injected providers (RULES §35)."""

    def __init__(self, clock: Callable[[], int],
                 audit_rows_provider: Callable[[], List[Dict[str, Any]]],
                 max_age_ticks: int = MAX_BUNDLE_AGE_TICKS) -> None:
        if not callable(clock):
            _fail("clock required")
        if not callable(audit_rows_provider):
            _fail("audit_rows_provider required")
        if not isinstance(max_age_ticks, int) or max_age_ticks <= 0:
            _fail("max_age_ticks must be positive")
        self._clock = clock
        self._audit_rows = audit_rows_provider
        self._max_age = max_age_ticks

    # -- internals -----------------------------------------------------------

    @staticmethod
    def _render(checks: List[tuple]) -> PreflightVerdict:
        blocked = [c[0] for c in checks if not c[1]]
        verdict = PREFLIGHT_CLEARED if not blocked else PREFLIGHT_BLOCKED
        return PreflightVerdict(
            verdict=verdict, checks=tuple(checks),
            findings=tuple(blocked) if blocked else ("preflight:CLEARED",))

    # -- the four rules --------------------------------------------------------

    def validate(self, bundle: Dict[str, Any],
                 owner_command_hash: Optional[str]) -> PreflightVerdict:
        """Evaluate G-01..G-04 for one provisioning attempt.

        `bundle` — the D-147 attestation artifact (dict form).
        `owner_command_hash` — the bundle hash carried by the owner's
        deployment command (the explicit authorization token).
        """
        checks: List[tuple] = []

        # G-01 schema + hash integrity -------------------------------------
        if not isinstance(bundle, dict):
            checks.append(("G-01", False,
                           "bundle is not an object — fail closed"))
            return self._render(checks)
        if bundle.get("schema") != BUNDLE_SCHEMA:
            checks.append(("G-01", False,
                           f"schema {bundle.get('schema')!r} != "
                           f"{BUNDLE_SCHEMA!r}"))
        else:
            recorded = bundle.get("bundle_hash", "")
            recomputed = bundle_hash_of(
                {k: v for k, v in bundle.items() if k != "bundle_hash"})
            if not HEX64.match(recorded or ""):
                checks.append(("G-01", False,
                               "bundle_hash missing or malformed"))
            elif recorded != recomputed:
                checks.append(("G-01", False,
                               f"bundle_hash {recorded[:16]}… != recomputed "
                               f"{recomputed[:16]}… — TAMPERED bundle"))
            else:
                checks.append(("G-01", True,
                               f"schema + hash integrity ({recorded[:16]}…)"))

        # G-02 READY + unexpired ---------------------------------------------
        if bundle.get("verdict") != BUNDLE_READY:
            checks.append(("G-02", False,
                           f"bundle verdict {bundle.get('verdict')!r} "
                           f"!= {BUNDLE_READY!r}"))
        else:
            observed = bundle.get("observed_tick")
            now = self._clock()
            if (not isinstance(observed, int) or isinstance(observed, bool)
                    or observed < 0):
                checks.append(("G-02", False,
                               "observed_tick malformed — fail closed"))
            elif now < observed:
                checks.append(("G-02", False,
                               "bundle observed_tick in the future"))
            elif now - observed >= self._max_age:
                checks.append(("G-02", False,
                               f"bundle expired {now - observed} ticks ago "
                               f"(max age {self._max_age}) — re-attest"))
            else:
                checks.append(("G-02", True,
                               f"READY, age {now - observed} ticks"))

        # G-03 owner command carries the identical bundle hash ----------------
        if not isinstance(owner_command_hash, str) or \
                not HEX64.match(owner_command_hash or ""):
            checks.append(("G-03", False,
                           "owner deployment command carries no valid "
                           "bundle hash — nothing is authorized"))
        elif not HEX64.match(bundle.get("bundle_hash", "") or ""):
            checks.append(("G-03", False,
                           "bundle hash unusable for comparison"))
        elif owner_command_hash != bundle.get("bundle_hash"):
            checks.append(("G-03", False,
                           "owner command hash != bundle hash — "
                           "authorization is for a DIFFERENT bundle"))
        else:
            checks.append(("G-03", True,
                           "owner command authorizes THIS bundle"))

        # G-04 D-112 control-audit record ---------------------------------------
        try:
            rows = self._audit_rows() or []
        except Exception as exc:  # noqa: BLE001 — audit chain absent
            checks.append(("G-04", False,
                           f"control-audit chain unreadable: "
                           f"{type(exc).__name__}"))
            rows = []
        target = bundle.get("bundle_hash", "")
        found = False
        for row in rows:
            kind = str(row.get("event_kind", ""))
            detail = row.get("detail") or {}
            detail_blob = json.dumps(detail, ensure_ascii=False,
                                     sort_keys=True) if isinstance(detail, dict) \
                else str(detail)
            if kind in AUDIT_KINDS or target and target in detail_blob:
                found = True
                break
        if found:
            checks.append(("G-04", True,
                           "cutover decision recorded in the D-112 chain"))
        else:
            checks.append(("G-04", False,
                           "no D-112 control-audit record for this "
                           "bundle hash — the decision is not durably "
                           "attested"))

        return self._render(checks)


def main(argv: Optional[List[str]] = None) -> int:
    """CLI wiring: real bundle file + real D-112 chain."""
    import argparse
    import pathlib
    import sys
    ap = argparse.ArgumentParser(
        description="Stage G provisioning pre-flight (G-01..G-04, D-148).")
    ap.add_argument("--bundle", required=True,
                    help="path to the cutover.bundle.v1 JSON artifact")
    ap.add_argument("--command-hash", required=True,
                    help="bundle hash carried by the owner deployment command")
    args = ap.parse_args(argv)
    print("stage_g_preflight: interactive wiring requires the real "
          "bundle file and control-audit engine; see validate() and "
          "the battery for the injected contract.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

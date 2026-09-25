#!/usr/bin/env python3
"""Stage G — formal closure & Stage H handoff seal (D-152).

The master verification orchestrator that CONCLUDES Stage G: it
synthesizes every verification artifact the stage produced — Stage C
host readiness, the Stage D compose manifest fingerprint, the Stage E
rollback contract, the Stage F owner authorization (bundle), and the
Stage G acceptance fingerprint + live probe digest — into one
singular, unforgeable `stage_g_closure_seal.v1` whose `closure_digest`
is the cryptographic root for Stage H (live activation) entry.

Checks (all fail-closed; every refusal names its blocker):

  CLS-01  the complete C→G artifact chain is present and intact —
          host readiness READY with every check green, the Stage D
          manifest matching its fingerprint envelope (bound for
          `stage-e-cutover`), the Stage E rollback contract
          parseable, the D-147 bundle hash-verifying with its Stage F
          token, and the D-149/D-150 verdicts present;
  CLS-02  ZERO drift: one manifest fingerprint across the envelope,
          the bundle, the acceptance report and the live probe
          report, and the probe's acceptance binding intact;
  CLS-03  the D-151 TripleEvidenceGate verdict is LAUNCH_EVIDENCE_
          COMPLETE with EVERY TRIAD-01..04 rule present and passing —
          a skipped rule, a blocked check, or a provider error is a
          refusal (zero warnings, zero bypasses);
  CLS-04  the atomic rollback strategy parses (RB-1..RB-6 rows, each
          with trigger/detection/procedure/post-verification, and the
          stop → compensate/drain → reconcile ordering invariant) and
          every health-fallback trigger is well-formed (name, positive
          threshold, action);
  CLS-05  the canonical `stage_g_closure_seal.v1` is emitted with the
          SHA-256 `closure_digest` over its canonical bytes — exactly
          one audited seal per run (including aborts), deep-redacted
          (D-124).

Pure core (RULES §35): every artifact arrives via an INJECTED
provider; the engine performs zero I/O — no sockets, no subprocess,
no wall clock (AST-pinned in the battery). Production wiring: the
providers load the real Stage C verdict record, the Stage D
manifest+envelope, the Stage E runbook section, the D-147 bundle, the
D-149 acceptance report, the D-150 probe report, and the D-151 gate
verdict; the audit sink is the D-112 operator chain. The seal authorizes
a HANDOFF CANDIDATE only — production activation remains exclusively
owner-gated (D-139, plan §17/§21.6).
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
    "ClosureError", "ClosureSeal", "StageGClosureRunner",
    "SEAL_SCHEMA", "STAGE_G_CLOSED", "STAGE_G_OPEN",
    "BUNDLE_SCHEMA", "BUNDLE_READY", "ACCEPTANCE_SCHEMA",
    "PROBE_SCHEMA", "TRIAD_SCHEMA", "LAUNCH_READY", "ROLLBACK_ROWS",
]

SEAL_SCHEMA = "stage_g_closure_seal.v1"
STAGE_G_CLOSED = "STAGE_G_CLOSED"
STAGE_G_OPEN = "STAGE_G_OPEN"

BUNDLE_SCHEMA = "cutover.bundle.v1"
BUNDLE_READY = "READY_FOR_CUTOVER"
ACCEPTANCE_SCHEMA = "stage_g_acceptance_report.v1"
ACCEPTANCE_OK = "ACCEPTED"
PROBE_SCHEMA = "stage_g_live_probe_report.v1"
PROBES_OK = "PROBES_ACCEPTED"
TRIAD_SCHEMA = "stage_g_triple_evidence.v1"
LAUNCH_READY = "LAUNCH_EVIDENCE_COMPLETE"

# Stage E §5 rollback matrix: the six deterministic rows and the
# atomic ordering invariant (rollback BEFORE cleanup; durable
# evidence preserved — D-139).
ROLLBACK_ROWS = tuple(f"RB-{i}" for i in range(1, 7))
_ORDERING_INVARIANT = ("stop new work first, then compensate/drain,"
                       " then reconcile")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class ClosureError(ValueError):
    """Contract-level misuse of the closure orchestrator."""


def _fail(reason: str) -> None:
    raise ClosureError(reason)


def canonical_hash(payload: Dict[str, Any]) -> str:
    """SHA-256 over canonical JSON bytes — the formula every Stage G
    engine uses for bundle_hash / acceptance_fingerprint / probe_digest
    / closure_digest."""
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ClosureSeal:
    """Canonical, immutable Stage G closure artifact."""
    schema: str
    verdict: str                      # STAGE_G_CLOSED / STAGE_G_OPEN
    manifest_sha256: str
    bundle_hash: str
    acceptance_fingerprint: str
    probe_digest: str
    checks: tuple = field(default_factory=tuple)   # (id, ok, detail)
    observed_tick: int = 0

    @property
    def closed(self) -> bool:
        return self.verdict == STAGE_G_CLOSED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "verdict": self.verdict,
            "manifest_sha256": self.manifest_sha256,
            "bundle_hash": self.bundle_hash,
            "acceptance_fingerprint": self.acceptance_fingerprint,
            "probe_digest": self.probe_digest,
            "checks": [list(c) for c in self.checks],
            "observed_tick": self.observed_tick,
        }

    @property
    def closure_digest(self) -> str:
        """SHA-256 over the seal's canonical bytes — the cryptographic
        root digest for Stage H activation entry."""
        return canonical_hash(self.to_dict())


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class StageGClosureRunner:
    """CLS-01..CLS-05 with injected providers (RULES §35).

    Injected (each optional; an ABSENT artifact is a named CLS-01
    refusal — fail closed):
      clock             — ``() -> int`` logical tick
      audit_sink        — ``callable(dict)`` (D-112/D-121 in prod)
      host_readiness    — ``() -> dict`` Stage C verdict record
                          {"verdict": "READY", "checks": {id: bool}}
      manifest_text     — ``() -> str`` Stage D manifest bytes
      envelope_text     — ``() -> str`` Stage D fingerprint envelope
      rollback_spec     — ``() -> str`` Stage E §5 rollback matrix text
      fallback_spec     — ``() -> dict`` health-fallback triggers
      bundle            — ``() -> dict`` the D-147 cutover bundle
      acceptance_report — ``() -> dict`` the D-149 acceptance report
      probe_report      — ``() -> dict`` the D-150 live probe report
      triad_verdict     — ``() -> dict`` the D-151 gate's verdict
                          (TriadVerdict.to_dict() shape)
    """

    def __init__(self, clock: Callable[[], int],
                 audit_sink: Callable[[Dict[str, Any]], None],
                 host_readiness: Optional[Callable[[], Dict[str, Any]]] = None,
                 manifest_text: Optional[Callable[[], str]] = None,
                 envelope_text: Optional[Callable[[], str]] = None,
                 rollback_spec: Optional[Callable[[], str]] = None,
                 fallback_spec: Optional[Callable[[], Dict[str, Any]]] = None,
                 bundle: Optional[Callable[[], Dict[str, Any]]] = None,
                 acceptance_report: Optional[Callable[[], Dict[str, Any]]] = None,
                 probe_report: Optional[Callable[[], Dict[str, Any]]] = None,
                 triad_verdict: Optional[Callable[[], Dict[str, Any]]] = None,
                 ) -> None:
        if not callable(clock) or not callable(audit_sink):
            _fail("clock and audit_sink required")
        self._clock = clock
        self._sink = audit_sink
        self._prov = {
            "host_readiness": host_readiness,
            "manifest_text": manifest_text,
            "envelope_text": envelope_text,
            "rollback_spec": rollback_spec,
            "fallback_spec": fallback_spec,
            "bundle": bundle,
            "acceptance_report": acceptance_report,
            "probe_report": probe_report,
            "triad_verdict": triad_verdict,
        }

    # -- internals -------------------------------------------------------------

    def _load(self, name: str) -> Tuple[Optional[Any], str]:
        """Load one injected artifact. A missing provider, a raising
        provider, or a non-value returns (None, reason) — fail closed
        with the exception TYPE only (D-124)."""
        fn = self._prov[name]
        if fn is None:
            return None, "artifact not wired — fail closed"
        try:
            return fn(), ""
        except Exception as exc:  # noqa: BLE001 — provider boundary
            return None, f"provider failure: {type(exc).__name__}"

    def _emit(self, verdict: str,
              checks: List[Tuple[str, bool, str]]) -> ClosureSeal:
        # Best-effort digest fields: whatever the chain carried.
        manifest_hash = ""
        env, err = self._load("envelope_text")
        if isinstance(env, str) and env:
            m = re.search(r"^manifest_sha256:\s*([0-9a-f]{64})\s*$",
                          env, re.M)
            if m:
                manifest_hash = m.group(1)
        man, _ = self._load("manifest_text")
        if not (isinstance(man, str) and man):
            man = None
        bundle_d, _ = self._load("bundle")
        bh = bundle_d.get("bundle_hash", "") \
            if isinstance(bundle_d, dict) else ""
        acc, _ = self._load("acceptance_report")
        afp = acc.get("acceptance_fingerprint", "") \
            if isinstance(acc, dict) else ""
        probe, _ = self._load("probe_report")
        pd = probe.get("probe_digest", "") \
            if isinstance(probe, dict) else ""
        seal = ClosureSeal(
            schema=SEAL_SCHEMA, verdict=verdict,
            manifest_sha256=manifest_hash, bundle_hash=bh,
            acceptance_fingerprint=afp, probe_digest=pd,
            checks=tuple((c[0], c[1], deep_redact(str(c[2])))
                         for c in checks),
            observed_tick=self._clock())
        blob = json.dumps(seal.to_dict(), sort_keys=True,
                          separators=(",", ":"), ensure_ascii=False)
        self._sink(json.loads(deep_redact(blob)))
        return seal

    # -- CLS-01: the C→G artifact chain -------------------------------------

    def _cls01(self) -> Tuple[bool, List[Tuple[str, bool, str]],
                              Dict[str, Any]]:
        """Presence + integrity of every chain link. Returns
        (ok, checks, artifacts) with the loaded artifacts for the
        later checks."""
        checks: List[Tuple[str, bool, str]] = []
        arts: Dict[str, Any] = {}

        # Stage C — host readiness --------------------------------------
        host, err = self._load("host_readiness")
        if host is None:
            checks.append(("CLS-01", False,
                           f"Stage C host readiness absent ({err or 'not wired'})"))
        elif not isinstance(host, dict) or \
                host.get("verdict") != "READY" or \
                not isinstance(host.get("checks"), dict) or \
                not host.get("checks") or \
                not all(v is True for v in host["checks"].values()):
            checks.append(("CLS-01", False,
                           "Stage C host readiness not READY or has "
                           "failing checks — the host never cleared"))
        else:
            checks.append(("CLS-01", True,
                           f"Stage C host READY "
                           f"({len(host['checks'])} checks green)"))
        arts["host"] = host

        # Stage D — manifest + fingerprint envelope ----------------------
        man, err = self._load("manifest_text")
        env, err2 = self._load("envelope_text")
        if not isinstance(man, str) or not man:
            checks.append(("CLS-01", False,
                           f"Stage D manifest absent ({err or 'not wired'})"))
        elif not isinstance(env, str) or not env:
            checks.append(("CLS-01", False,
                           f"Stage D fingerprint envelope absent "
                           f"({err2 or 'not wired'})"))
        else:
            m = re.search(r"^manifest_sha256:\s*([0-9a-f]{64})\s*$",
                          env, re.M)
            b = re.search(r"^bound_for:\s*(\S+)\s*$", env, re.M)
            if not m:
                checks.append(("CLS-01", False,
                               "Stage D envelope malformed (no "
                               "manifest_sha256 row)"))
            elif (b.group(1) if b else "") != "stage-e-cutover":
                checks.append(("CLS-01", False,
                               "Stage D envelope not bound for "
                               "stage-e-cutover"))
            elif _sha256_text(man) != m.group(1):
                checks.append(("CLS-01", False,
                               "Stage D manifest does not match its "
                               "envelope — tampered or re-generated "
                               "without re-binding"))
            else:
                checks.append(("CLS-01", True,
                               f"Stage D manifest bound "
                               f"({m.group(1)[:16]}…)"))
        arts["manifest"] = man
        arts["envelope"] = env

        # Stage E — the rollback contract (parsed deeply in CLS-04) ------
        rb, err = self._load("rollback_spec")
        if not isinstance(rb, str) or not rb:
            checks.append(("CLS-01", False,
                           f"Stage E rollback contract absent "
                           f"({err or 'not wired'})"))
        else:
            checks.append(("CLS-01", True,
                           "Stage E rollback contract present"))
        arts["rollback"] = rb

        # Stage F — the owner-authorized bundle --------------------------
        bundle, err = self._load("bundle")
        if bundle is None:
            checks.append(("CLS-01", False,
                           f"Stage F bundle absent ({err or 'not wired'})"))
        elif not isinstance(bundle, dict):
            checks.append(("CLS-01", False,
                           "Stage F bundle malformed — fail closed"))
        elif bundle.get("schema") != BUNDLE_SCHEMA:
            checks.append(("CLS-01", False,
                           f"Stage F bundle schema "
                           f"{bundle.get('schema')!r} != "
                           f"{BUNDLE_SCHEMA!r}"))
        elif not bundle.get("stage_f_token_id"):
            checks.append(("CLS-01", False,
                           "Stage F bundle carries no owner token — "
                           "the gate never authorized"))
        else:
            recorded = bundle.get("bundle_hash", "")
            recomputed = canonical_hash(
                {k: v for k, v in bundle.items() if k != "bundle_hash"})
            if not _HEX64.match(recorded or ""):
                checks.append(("CLS-01", False,
                               "Stage F bundle_hash missing or malformed"))
            elif recorded != recomputed:
                checks.append(("CLS-01", False,
                               f"Stage F bundle_hash {recorded[:16]}… != "
                               f"recomputed {recomputed[:16]}… — "
                               "TAMPERED bundle"))
            else:
                checks.append(("CLS-01", True,
                               f"Stage F bundle intact, owner token "
                               f"present ({recorded[:16]}…)"))
        arts["bundle"] = bundle

        # Stage G — acceptance + live probes ------------------------------
        acc, err = self._load("acceptance_report")
        if acc is None:
            checks.append(("CLS-01", False,
                           f"Stage G acceptance report absent "
                           f"({err or 'not wired'})"))
        elif not isinstance(acc, dict):
            checks.append(("CLS-01", False,
                           "Stage G acceptance report malformed"))
        elif acc.get("schema") != ACCEPTANCE_SCHEMA:
            checks.append(("CLS-01", False,
                           f"Stage G acceptance schema "
                           f"{acc.get('schema')!r} != "
                           f"{ACCEPTANCE_SCHEMA!r}"))
        elif acc.get("verdict") != ACCEPTANCE_OK:
            checks.append(("CLS-01", False,
                           f"Stage G acceptance verdict "
                           f"{acc.get('verdict')!r} != "
                           f"{ACCEPTANCE_OK!r}"))
        else:
            checks.append(("CLS-01", True,
                           "Stage G acceptance report ACCEPTED"))
        arts["acceptance"] = acc

        probe, err = self._load("probe_report")
        if probe is None:
            checks.append(("CLS-01", False,
                           f"Stage G live probe report absent "
                           f"({err or 'not wired'})"))
        elif not isinstance(probe, dict):
            checks.append(("CLS-01", False,
                           "Stage G live probe report malformed"))
        elif probe.get("schema") != PROBE_SCHEMA:
            checks.append(("CLS-01", False,
                           f"Stage G probe schema "
                           f"{probe.get('schema')!r} != "
                           f"{PROBE_SCHEMA!r}"))
        elif probe.get("verdict") != PROBES_OK:
            checks.append(("CLS-01", False,
                           f"Stage G probe verdict "
                           f"{probe.get('verdict')!r} != {PROBES_OK!r}"))
        else:
            checks.append(("CLS-01", True,
                           "Stage G live probe report PROBES_ACCEPTED"))
        arts["probe"] = probe

        ok = all(c[1] for c in checks)
        return ok, checks, arts

    # -- CLS-02: zero drift ----------------------------------------------------

    @staticmethod
    def _cls02(arts: Dict[str, Any]) -> Tuple[bool, List[Tuple[str, bool, str]]]:
        checks: List[Tuple[str, bool, str]] = []
        env = arts.get("envelope")
        m = re.search(r"^manifest_sha256:\s*([0-9a-f]{64})\s*$",
                      env, re.M) if isinstance(env, str) else None
        envelope_fp = m.group(1) if m else ""
        man = arts.get("manifest")
        manifest_fp = _sha256_text(man) \
            if isinstance(man, str) and man else ""
        bundle = arts.get("bundle") if isinstance(arts.get("bundle"),
                                                  dict) else {}
        acc = arts.get("acceptance") \
            if isinstance(arts.get("acceptance"), dict) else {}
        probe = arts.get("probe") if isinstance(arts.get("probe"),
                                                dict) else {}
        fingerprints = {
            "envelope": envelope_fp,
            "manifest": manifest_fp,
            "bundle": bundle.get("candidate_manifest_sha256", ""),
            "acceptance": acc.get("manifest_sha256", ""),
            "probe": probe.get("manifest_sha256", ""),
        }
        malformed = [k for k, v in fingerprints.items()
                     if not _HEX64.match(v or "")]
        if malformed:
            checks.append(("CLS-02", False,
                           f"manifest fingerprint missing or malformed "
                           f"in: {sorted(malformed)} — zero-drift "
                           "cannot be asserted"))
        elif len(set(fingerprints.values())) != 1:
            shown = {k: v[:16] + "…" for k, v in fingerprints.items()}
            checks.append(("CLS-02", False,
                           f"manifest fingerprint drift across the "
                           f"chain: {shown} — the artifacts attest "
                           "DIFFERENT deployments"))
        else:
            checks.append(("CLS-02", True,
                           f"zero drift: one manifest fingerprint "
                           f"({envelope_fp[:16]}…) across envelope, "
                           "manifest, bundle, acceptance and probe"))
        pa = probe.get("acceptance_fingerprint", "")
        aa = acc.get("acceptance_fingerprint", "")
        if not _HEX64.match(pa or ""):
            checks.append(("CLS-02", False,
                           "probe carries no acceptance fingerprint — "
                           "live binding absent"))
        elif pa != aa:
            checks.append(("CLS-02", False,
                           "probe's acceptance fingerprint != the "
                           "acceptance report — probes observed a "
                           "different clearance"))
        else:
            checks.append(("CLS-02", True,
                           "probe bound to THIS acceptance report"))
        return (all(c[1] for c in checks)), checks

    # -- CLS-03: the triad gate --------------------------------------------------

    def _cls03(self) -> Tuple[bool, List[Tuple[str, bool, str]]]:
        tv, err = self._load("triad_verdict")
        checks: List[Tuple[str, bool, str]] = []
        if tv is None:
            checks.append(("CLS-03", False,
                           f"triple-evidence verdict absent "
                           f"({err or 'not wired'}) — the D-151 gate "
                           "never ran"))
            return False, checks
        if not isinstance(tv, dict):
            checks.append(("CLS-03", False,
                           "triple-evidence verdict malformed"))
            return False, checks
        if tv.get("schema") != TRIAD_SCHEMA:
            checks.append(("CLS-03", False,
                           f"triad schema {tv.get('schema')!r} != "
                           f"{TRIAD_SCHEMA!r}"))
            return False, checks
        rows = tv.get("checks") or []
        ids = {c[0] for c in rows if isinstance(c, (list, tuple))
               and c} if rows else set()
        missing = [t for t in ("TRIAD-01", "TRIAD-02", "TRIAD-03",
                               "TRIAD-04") if t not in ids]
        if missing:
            checks.append(("CLS-03", False,
                           f"triad rules skipped or absent: {missing} "
                           "— zero bypasses allowed"))
            return False, checks
        blocked = [c[0] for c in rows
                   if isinstance(c, (list, tuple)) and len(c) >= 2
                   and not c[1]]
        if blocked:
            checks.append(("CLS-03", False,
                           f"triad blocked at {sorted(set(blocked))} "
                           "— launch evidence incomplete"))
        elif tv.get("verdict") != LAUNCH_READY:
            checks.append(("CLS-03", False,
                           f"triad verdict {tv.get('verdict')!r} != "
                           f"{LAUNCH_READY!r}"))
        else:
            checks.append(("CLS-03", True,
                           f"triple-evidence gate LAUNCH_READY "
                           f"({len(rows)} checks, all four rules "
                           "passing, zero bypasses)"))
        return (all(c[1] for c in checks)), checks

    # -- CLS-04: rollback strategy + health fallbacks ----------------------------

    @staticmethod
    def _cls04(arts: Dict[str, Any]) -> Tuple[bool, List[Tuple[str, bool, str]]]:
        checks: List[Tuple[str, bool, str]] = []
        rb = arts.get("rollback")
        if not isinstance(rb, str) or not rb:
            checks.append(("CLS-04", False,
                           "rollback strategy absent — a cutover "
                           "without an atomic rollback plan is "
                           "refused (D-139)"))
        else:
            missing = [r for r in ROLLBACK_ROWS
                       if not re.search(rf"^\|\s*{r}\s*\|", rb, re.M)]
            if missing:
                checks.append(("CLS-04", False,
                               f"rollback rows missing or unparsable: "
                               f"{missing} (need `| RB-n |` table rows)"))
            else:
                bad_rows = []
                for line in rb.splitlines():
                    m = re.match(r"^\|\s*(RB-[1-6])\s*\|(.*)$", line)
                    if not m:
                        continue
                    cells = [c.strip() for c in
                             m.group(2).split("|") if c.strip()]
                    if len(cells) < 3 or any(
                            len(c) < 3 for c in cells[:3]):
                        bad_rows.append(m.group(1))
                if bad_rows:
                    checks.append(("CLS-04", False,
                                   f"rollback rows lack trigger/"
                                   f"procedure/post-verification: "
                                   f"{bad_rows}"))
                else:
                    checks.append(("CLS-04", True,
                                   f"rollback matrix complete "
                                   f"({len(ROLLBACK_ROWS)} rows, each "
                                   "with trigger/procedure/"
                                   "post-verification)"))
            # whitespace-normalized match: the invariant is about
            # the DECLARATION, not the line wrapping of the runbook
            rb_flat = re.sub(r"\s+", " ", rb)
            if _ORDERING_INVARIANT not in rb_flat:
                checks.append(("CLS-04", False,
                               "atomic ordering invariant absent "
                               "(stop new work first, then "
                               "compensate/drain, then reconcile)"))
            else:
                checks.append(("CLS-04", True,
                               "atomic ordering invariant declared "
                               "(rollback BEFORE cleanup, evidence "
                               "preserved)"))
        # fallback spec is loaded by the run() wrapper into arts
        spec = arts.get("fallback")
        if spec is None:
            checks.append(("CLS-04", False,
                           f"health fallback triggers absent "
                           f"({arts.get('_fallback_err') or 'not wired'})"))
        elif not isinstance(spec, dict) or \
                not isinstance(spec.get("triggers"), list) or \
                not spec.get("triggers"):
            checks.append(("CLS-04", False,
                           "health fallback triggers malformed or "
                           "empty — no defined reaction to a red "
                           "probe is a refusal"))
        else:
            bad = []
            for i, t in enumerate(spec["triggers"]):
                if not isinstance(t, dict):
                    bad.append(f"#{i}:not-an-object")
                    continue
                name = t.get("name")
                thr = t.get("threshold_ticks")
                action = t.get("action")
                if not isinstance(name, str) or not name.strip():
                    bad.append(f"#{i}:name")
                if not isinstance(thr, int) or isinstance(thr, bool) \
                        or thr <= 0:
                    bad.append(f"#{i}:threshold")
                if not isinstance(action, str) or not action.strip():
                    bad.append(f"#{i}:action")
            if bad:
                checks.append(("CLS-04", False,
                               f"health fallback triggers malformed "
                               f"({', '.join(bad)}) — each needs a "
                               "name, a positive threshold_ticks and "
                               "an action"))
            else:
                checks.append(("CLS-04", True,
                               f"{len(spec['triggers'])} health "
                               "fallback triggers well-formed"))
        return (all(c[1] for c in checks)), checks

    # -- the run -----------------------------------------------------------------

    def run(self) -> ClosureSeal:
        """CLS-01..CLS-05 → canonical seal. Exactly one audited seal
        per call (including aborts). CLS-05 always emits."""
        checks: List[Tuple[str, bool, str]] = []
        ok1, c1, arts = self._cls01()
        checks += c1
        ok2, c2 = self._cls02(arts)
        checks += c2
        ok3, c3 = self._cls03()
        checks += c3
        fb, fb_err = self._load("fallback_spec")
        arts["fallback"] = fb
        arts["_fallback_err"] = fb_err
        ok4, c4 = self._cls04(arts)
        checks += c4
        verdict = STAGE_G_CLOSED if all(
            (ok1, ok2, ok3, ok4)) else STAGE_G_OPEN
        if verdict == STAGE_G_CLOSED:
            checks.append(("CLS-05", True,
                           "closure seal emitted — Stage H entry "
                           "candidate root digest computed"))
        else:
            checks.append(("CLS-05", False,
                           "seal emitted as STAGE_G_OPEN — remediate "
                           "the named checks before Stage H handoff"))
        return self._emit(verdict, checks)


def main(argv: Optional[List[str]] = None) -> int:
    """CLI wiring: real artifacts + real D-112 audit sink."""
    import argparse
    import sys
    ap = argparse.ArgumentParser(
        description="Stage G closure & Stage H handoff seal "
                    "(CLS-01..CLS-05, D-152).")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    print("stage_g_closure_and_handoff: interactive wiring requires "
          "the real Stage C–G artifacts and the D-112 audit sink; "
          "see run() and the battery for the injected contract.",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

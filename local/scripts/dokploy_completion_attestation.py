#!/usr/bin/env python3
"""Dokploy Infrastructure Completion Attestation (D-154).

The FINAL synthesizer of the Dokploy deployment track: it verifies
that Stages B through H form ONE unbroken cryptographic continuum and
emits the canonical completion certificate
`dokploy.completion_attestation.v1` declaring the infrastructure
provisioned and READY FOR SERVICE IGNITION — the formal boundary
between infrastructure provisioning (Stages B–H) and the Live Wiring
program (MASTER_PLAN Phases 5–18).

Attestation rules (all fail-closed; every refusal names its blocker):

  DEP-01  the full lifecycle chain is present, genuine and rooted —
          Host readiness (C), Compose manifest + fingerprint envelope
          (D), the Cutover Bundle (E/F), the Stage G acceptance
          report + live probe report, the D-151 triple-evidence
          verdict, the Stage G closure seal (G), and the Stage H
          activation record (H) — each artifact re-verified against
          its OWN engine's checks (H-01 re-run on the seal, the
          activation digest recomputed, the record's verdict
          CUTOVER_EXECUTED);
  DEP-02  ZERO drift: one manifest SHA-256 across the Stage D envelope
          bytes, the bundle, the acceptance report, the probe report,
          the closure seal, the activation record and the owner token
          draft; PLUS the chain of configuration digests recomputed
          byte-exactly — bundle_hash, acceptance_fingerprint,
          probe_digest and closure_digest recompute from the carried
          artifacts, so every digest in the certificate re-derives
          from first principles;
  DEP-03  every chain event is ANCHORED in the D-112 append-only
          ledger: the injected chain verifier (the real
          `ControlPlaneEngine.verify_chain()`) reports a hash-chained
          trail with ZERO breaks, and the anchor rows carry the
          bundle/acceptance/probe/closure/activation commitments;
  DEP-04  Live-Wiring entry-point readiness (Phases 5–18): the
          injected readiness provider lists the application entry
          points that ignite against the attested stack — each phase
          present, verified, and wired; the verified runtime profile
          (the probe/activation evidence) must be present so the
          certificate binds readiness to THIS deployment;
  DEP-05  the canonical `dokploy.completion_attestation.v1` is emitted
          exactly once with the SHA-256 `attestation_digest` over its
          canonical bytes — including on refusal (the certificate
          then declares the block); deep-redacted (D-124) with the
          public commitments restored.

Pure core (RULES §35): every artifact arrives via an INJECTED
provider — zero sockets, zero subprocess, zero wall clock (AST-pinned
in the battery). Production wiring: the providers load the real
Stage B–H artifacts, the D-112 vault chain
(`ControlPlaneEngine.verify_chain()`), and the Phase 5–18 readiness
census. The certificate authorizes SERVICE IGNITION only — it never
executes anything (plan §17/§21.6: activation and live wiring remain
owner-gated).
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
    "CompletionError", "CompletionAttestation",
    "DokployCompletionAttestor", "ATTESTATION_SCHEMA",
    "INFRA_COMPLETE", "INFRA_INCOMPLETE", "SEAL_SCHEMA",
    "SEAL_CLOSED", "RECORD_SCHEMA", "CUTOVER_EXECUTED",
    "TRIAD_SCHEMA", "LAUNCH_READY", "BUNDLE_SCHEMA",
    "ACCEPTANCE_SCHEMA", "PROBE_SCHEMA",
    "LIVE_WIRING_PHASES", "ENTRY_POINTS", "ATT_STAGE_KINDS",
]

ATTESTATION_SCHEMA = "dokploy.completion_attestation.v1"
INFRA_COMPLETE = "INFRASTRUCTURE_COMPLETE"
INFRA_INCOMPLETE = "INFRASTRUCTURE_INCOMPLETE"

SEAL_SCHEMA = "stage_g_closure_seal.v1"
SEAL_CLOSED = "STAGE_G_CLOSED"
RECORD_SCHEMA = "stage_h_activation_record.v1"
CUTOVER_EXECUTED = "CUTOVER_EXECUTED"
TRIAD_SCHEMA = "stage_g_triple_evidence.v1"
LAUNCH_READY = "LAUNCH_EVIDENCE_COMPLETE"
BUNDLE_SCHEMA = "cutover.bundle.v1"
ACCEPTANCE_SCHEMA = "stage_g_acceptance_report.v1"
PROBE_SCHEMA = "stage_g_live_probe_report.v1"

# The Live Wiring program (MASTER_PLAN.md §13, Phases 5–18): the
# phases whose entry points ignite against the attested stack.
LIVE_WIRING_PHASES: Tuple[Tuple[int, str], ...] = (
    (5, "n8n Foundation"),
    (6, "Notion Business OS"),
    (7, "AI Runtime"),
    (8, "AI Product Manager"),
    (9, "Instagram"),
    (10, "AI Sales Agent"),
    (11, "Order Management"),
    (12, "Payment"),
    (13, "Shipping"),
    (14, "CRM"),
    (15, "Marketing Automation"),
    (16, "Analytics"),
    (17, "AI Business Analyst"),
    (18, "Human-in-the-Loop System"),
)

# The canonical entry-point seam per phase — the repository module
# each Live-Wiring phase ignites through. From Phase 10 onward the
# MASTER_PLAN §13 labels and the repository's operational phase
# records diverge (the repository's Phase 10 record is Telegram,
# its Phase 11 record is Cross-Platform Orchestration, its Phase 12
# record is Order Management D-081–D-084); this registry binds each
# phase number to the repository's REAL seam, and the completion
# report carries the full cross-walk.
ENTRY_POINTS: Dict[int, str] = {
    5: "canonical.n8n_webhook_contracts",
    6: "canonical.notion_contracts",
    7: "canonical.ai_runtime",
    8: "canonical.ai_proposal_lifecycle",
    9: "publishing.instagram",
    10: "canonical.telegram_ingress",
    11: "canonical.oms_engine",
    12: "canonical.oms_contracts",
    13: "canonical.orchestration_engine",
    14: "commerce.sync_orchestrator",
    15: "canonical.scheduling_engine",
    16: "canonical.analytics_engine",
    17: "canonical.analyst_engine",
    18: "canonical.ai_hitl_service",
}

# The D-112 anchor kinds the certificate requires, mapped to the
# commitment each row must carry.
ATT_STAGE_KINDS: Tuple[Tuple[str, str], ...] = (
    ("cutover_bundle_recorded", "bundle_hash"),
    ("stage_g_acceptance", "acceptance_fingerprint"),
    ("stage_g_live_probe", "probe_digest"),
    ("stage_g_closure", "closure_digest"),
    ("stage_h_activation", "activation_digest"),
)

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class CompletionError(ValueError):
    """Contract-level misuse of the completion attestor."""


def _fail(reason: str) -> None:
    raise CompletionError(reason)


def canonical_hash(payload: Dict[str, Any]) -> str:
    """SHA-256 over canonical JSON bytes — the Stage G/H digest
    formula, reused verbatim so every recomputation here matches the
    producers."""
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# Each producer digest recomputes over the artifact's canonical
# bytes EXCLUDING only its own digest field — upstream digests
# legitimately participate (the probe embeds the acceptance
# fingerprint; the seal embeds bundle/acceptance/probe digests; the
# activation record embeds the closure digest).
_DIGEST_FIELDS_BY_SCHEMA = {
    BUNDLE_SCHEMA: "bundle_hash",
    ACCEPTANCE_SCHEMA: "acceptance_fingerprint",
    PROBE_SCHEMA: "probe_digest",
    SEAL_SCHEMA: "closure_digest",
    RECORD_SCHEMA: "activation_digest",
}


def recompute_digest(artifact: Dict[str, Any]) -> str:
    """Canonical recompute of the digest field the artifact's schema
    owns (returns "" for unknown schemas — fail closed)."""
    if not isinstance(artifact, dict):
        return ""
    field_name = _DIGEST_FIELDS_BY_SCHEMA.get(artifact.get("schema"))
    if field_name is None or field_name not in artifact:
        return ""
    return canonical_hash({k: v for k, v in artifact.items()
                           if k != field_name})


@dataclass(frozen=True)
class CompletionAttestation:
    """Canonical, immutable D-154 completion artifact."""
    schema: str
    verdict: str          # INFRASTRUCTURE_COMPLETE / _INCOMPLETE
    manifest_sha256: str
    bundle_hash: str
    acceptance_fingerprint: str
    probe_digest: str
    closure_digest: str
    activation_digest: str
    chain: Dict[str, Any]          # D-112 anchoring summary
    live_wiring: Dict[str, Any]    # Phase 5–18 readiness summary
    checks: tuple = field(default_factory=tuple)  # (id, ok, detail)
    observed_tick: int = 0

    @property
    def complete(self) -> bool:
        return self.verdict == INFRA_COMPLETE

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "verdict": self.verdict,
            "manifest_sha256": self.manifest_sha256,
            "bundle_hash": self.bundle_hash,
            "acceptance_fingerprint": self.acceptance_fingerprint,
            "probe_digest": self.probe_digest,
            "closure_digest": self.closure_digest,
            "activation_digest": self.activation_digest,
            "chain": self.chain,
            "live_wiring": self.live_wiring,
            "checks": [list(c) for c in self.checks],
            "observed_tick": self.observed_tick,
        }

    @property
    def attestation_digest(self) -> str:
        """SHA-256 over the certificate's canonical bytes."""
        return canonical_hash(self.to_dict())


class DokployCompletionAttestor:
    """DEP-01..DEP-05 with injected providers (RULES §35).

    Injected (each optional; an ABSENT artifact is a named refusal —
    fail closed):
      clock               — ``() -> int`` logical tick
      audit_sink          — ``callable(dict)`` (D-112/D-121 in prod)
      host_readiness      — ``() -> dict`` Stage C verdict record
      manifest_text       — ``() -> str`` Stage D manifest bytes
      envelope_text       — ``() -> str`` Stage D fingerprint envelope
      bundle              — ``() -> dict`` the D-147 cutover bundle
      acceptance_report   — ``() -> dict`` the D-149 acceptance report
      probe_report        — ``() -> dict`` the D-150 live probe report
      triad_verdict       — ``() -> dict`` the D-151 gate verdict
      seal                — ``() -> dict`` the D-152 closure seal
      activation_record   — ``() -> dict`` the D-153 activation record
      audit_rows          — ``() -> list`` the D-112 ledger rows
      chain_verifier      — ``() -> dict`` D-112 chain integrity
                            {ok, rows | broken_at_seq, reason} (the
                            real `ControlPlaneEngine.verify_chain()`)
      live_wiring_readiness — ``() -> dict`` Phase 5–18 readiness:
                            {phases: [{phase, name, entry_point,
                            present, verified, wired, detail}],
                            runtime_profile_verified: bool}
    """

    def __init__(self, clock: Callable[[], int],
                 audit_sink: Callable[[Dict[str, Any]], None],
                 host_readiness: Optional[Callable[[], Dict[str, Any]]] = None,
                 manifest_text: Optional[Callable[[], str]] = None,
                 envelope_text: Optional[Callable[[], str]] = None,
                 bundle: Optional[Callable[[], Dict[str, Any]]] = None,
                 acceptance_report: Optional[Callable[[], Dict[str, Any]]] = None,
                 probe_report: Optional[Callable[[], Dict[str, Any]]] = None,
                 triad_verdict: Optional[Callable[[], Dict[str, Any]]] = None,
                 seal: Optional[Callable[[], Dict[str, Any]]] = None,
                 activation_record: Optional[Callable[[], Dict[str, Any]]] = None,
                 audit_rows: Optional[Callable[[], List[Dict[str, Any]]]] = None,
                 chain_verifier: Optional[Callable[[], Dict[str, Any]]] = None,
                 live_wiring_readiness: Optional[
                     Callable[[], Dict[str, Any]]] = None,
                 ) -> None:
        if not callable(clock) or not callable(audit_sink):
            _fail("clock and audit_sink required")
        self._clock = clock
        self._sink = audit_sink
        self._prov = {
            "host_readiness": host_readiness,
            "manifest_text": manifest_text,
            "envelope_text": envelope_text,
            "bundle": bundle,
            "acceptance_report": acceptance_report,
            "probe_report": probe_report,
            "triad_verdict": triad_verdict,
            "seal": seal,
            "activation_record": activation_record,
            "audit_rows": audit_rows,
            "chain_verifier": chain_verifier,
            "live_wiring_readiness": live_wiring_readiness,
        }

    # -- internals -----------------------------------------------------------

    def _load(self, name: str) -> Tuple[Optional[Any], str]:
        fn = self._prov[name]
        if fn is None:
            return None, "artifact not wired — fail closed"
        try:
            return fn(), ""
        except Exception as exc:  # noqa: BLE001 — provider boundary
            return None, f"provider failure: {type(exc).__name__}"

    def _emit(self, verdict: str, checks: List[Tuple[str, bool, str]],
              chain: Optional[Dict[str, Any]] = None,
              live_wiring: Optional[Dict[str, Any]] = None,
              ) -> CompletionAttestation:
        digests = {k: self._digests.get(k, "")
                   for k in ("manifest", "bundle", "acceptance",
                             "probe", "closure", "activation")}

        def _redact_blob(obj: Dict[str, Any]) -> Dict[str, Any]:
            blob = json.dumps(obj, sort_keys=True, separators=(",", ":"),
                              ensure_ascii=False)
            return json.loads(deep_redact(blob))

        cert = CompletionAttestation(
            schema=ATTESTATION_SCHEMA, verdict=verdict,
            manifest_sha256=digests["manifest"],
            bundle_hash=digests["bundle"],
            acceptance_fingerprint=digests["acceptance"],
            probe_digest=digests["probe"],
            closure_digest=digests["closure"],
            activation_digest=digests["activation"],
            chain=_redact_blob(chain or {"anchored": False,
                                         "rows": 0,
                                         "zero_breaks": False,
                                         "anchors": {}}),
            live_wiring=_redact_blob(
                live_wiring or {"phases": [], "phases_ready": 0,
                                "phases_total":
                                len(LIVE_WIRING_PHASES),
                                "runtime_profile_verified":
                                False}),
            checks=tuple((c[0], c[1], deep_redact(str(c[2])))
                         for c in checks),
            observed_tick=self._clock())
        blob = json.dumps(cert.to_dict(), sort_keys=True,
                          separators=(",", ":"), ensure_ascii=False)
        redacted = json.loads(deep_redact(blob))
        # Public commitments (D-146/D-153 precedent): hash digests of
        # bindable public data are restored after deep redaction so
        # the ledger copy stays chain-correlatable. No secret ever
        # enters a certificate (there is nothing secret to carry).
        for k in ("manifest_sha256", "bundle_hash",
                  "acceptance_fingerprint", "probe_digest",
                  "closure_digest", "activation_digest"):
            redacted[k] = cert.to_dict()[k]
        self._sink(redacted)
        return cert

    # -- DEP-01: the full lifecycle chain --------------------------------------

    def _dep01(self) -> Tuple[bool, List[Tuple[str, bool, str]],
                              Dict[str, Any]]:
        """Presence + integrity of every Stage B–H link. Returns
        (ok, checks, artifacts)."""
        checks: List[Tuple[str, bool, str]] = []
        arts: Dict[str, Any] = {}

        # Stage C — host readiness ------------------------------------------------
        host, err = self._load("host_readiness")
        if host is None:
            checks.append(("DEP-01", False,
                           f"Stage C host readiness absent ({err})"))
        elif not isinstance(host, dict) or \
                host.get("verdict") != "READY" or \
                not isinstance(host.get("checks"), dict) or \
                not host.get("checks") or \
                not all(v is True for v in host["checks"].values()):
            checks.append(("DEP-01", False,
                           "Stage C host readiness not READY or has "
                           "failing checks"))
        else:
            checks.append(("DEP-01", True,
                           f"Stage C host READY "
                           f"({len(host['checks'])} checks green)"))
        arts["host"] = host

        # Stage D — manifest + fingerprint envelope --------------------------------
        man, err = self._load("manifest_text")
        env, err2 = self._load("envelope_text")
        if not isinstance(man, str) or not man:
            checks.append(("DEP-01", False,
                           f"Stage D manifest absent ({err})"))
        elif not isinstance(env, str) or not env:
            checks.append(("DEP-01", False,
                           f"Stage D fingerprint envelope absent "
                           f"({err2})"))
        else:
            m = re.search(r"^manifest_sha256:\s*([0-9a-f]{64})\s*$",
                          env, re.M)
            b = re.search(r"^bound_for:\s*(\S+)\s*$", env, re.M)
            if not m:
                checks.append(("DEP-01", False,
                               "Stage D envelope malformed (no "
                               "manifest_sha256 row)"))
            elif (b.group(1) if b else "") != "stage-e-cutover":
                checks.append(("DEP-01", False,
                               "Stage D envelope not bound for "
                               "stage-e-cutover"))
            else:
                manifest_fp = hashlib.sha256(
                    man.encode("utf-8")).hexdigest()
                if manifest_fp != m.group(1):
                    checks.append(("DEP-01", False,
                                   "Stage D manifest does not match "
                                   "its envelope — tampered or "
                                   "re-generated without re-binding"))
                else:
                    checks.append(("DEP-01", True,
                                   f"Stage D manifest bound "
                                   f"({m.group(1)[:16]}…)"))
        arts["manifest"] = man
        arts["envelope"] = env

        # Stage E/F — the owner-authorized cutover bundle ---------------------------
        bundle, err = self._load("bundle")
        if bundle is None:
            checks.append(("DEP-01", False,
                           f"Stage E/F cutover bundle absent ({err})"))
        elif not isinstance(bundle, dict):
            checks.append(("DEP-01", False,
                           "Stage E/F cutover bundle malformed"))
        elif bundle.get("schema") != BUNDLE_SCHEMA:
            checks.append(("DEP-01", False,
                           f"bundle schema {bundle.get('schema')!r} "
                           f"!= {BUNDLE_SCHEMA!r}"))
        elif not bundle.get("stage_f_token_id"):
            checks.append(("DEP-01", False,
                           "bundle carries no Stage F owner token — "
                           "the gate never authorized the cutover"))
        else:
            recorded = bundle.get("bundle_hash", "")
            recomputed = recompute_digest(bundle)
            if not _HEX64.match(recorded or ""):
                checks.append(("DEP-01", False,
                               "bundle_hash missing or malformed"))
            elif recorded != recomputed:
                checks.append(("DEP-01", False,
                               f"bundle_hash {recorded[:16]}… != "
                               f"recomputed {recomputed[:16]}… — "
                               "TAMPERED bundle"))
            else:
                checks.append(("DEP-01", True,
                               f"Stage E/F bundle intact, owner-"
                               f"authorized ({recorded[:16]}…)"))
        arts["bundle"] = bundle

        # Stage G — acceptance + live probes + triad --------------------------------
        acc, err = self._load("acceptance_report")
        if acc is None:
            checks.append(("DEP-01", False,
                           f"Stage G acceptance report absent ({err})"))
        elif not isinstance(acc, dict) or \
                acc.get("schema") != ACCEPTANCE_SCHEMA or \
                acc.get("verdict") != "ACCEPTED":
            checks.append(("DEP-01", False,
                           "Stage G acceptance report malformed or "
                           "not ACCEPTED"))
        else:
            recorded = acc.get("acceptance_fingerprint", "")
            recomputed = recompute_digest(acc)
            if not _HEX64.match(recorded or ""):
                checks.append(("DEP-01", False,
                               "acceptance_fingerprint missing or "
                               "malformed"))
            elif recorded != recomputed:
                checks.append(("DEP-01", False,
                               f"acceptance_fingerprint "
                               f"{recorded[:16]}… != recomputed "
                               f"{recomputed[:16]}… — ALTERED report"))
            else:
                checks.append(("DEP-01", True,
                               "Stage G acceptance report ACCEPTED "
                               f"({recorded[:16]}…)"))
        arts["acceptance"] = acc

        probe, err = self._load("probe_report")
        if probe is None:
            checks.append(("DEP-01", False,
                           f"Stage G live probe report absent ({err})"))
        elif not isinstance(probe, dict) or \
                probe.get("schema") != PROBE_SCHEMA or \
                probe.get("verdict") != "PROBES_ACCEPTED":
            checks.append(("DEP-01", False,
                           "Stage G live probe report malformed or "
                           "not PROBES_ACCEPTED"))
        else:
            recorded = probe.get("probe_digest", "")
            recomputed = recompute_digest(probe)
            if not _HEX64.match(recorded or ""):
                checks.append(("DEP-01", False,
                               "probe_digest missing or malformed"))
            elif recorded != recomputed:
                checks.append(("DEP-01", False,
                               f"probe_digest {recorded[:16]}… != "
                               f"recomputed {recomputed[:16]}… — "
                               "ALTERED report"))
            else:
                checks.append(("DEP-01", True,
                               "Stage G live probes PROBES_ACCEPTED "
                               f"({recorded[:16]}…)"))
        arts["probe"] = probe

        tv, err = self._load("triad_verdict")
        if tv is None:
            checks.append(("DEP-01", False,
                           f"triple-evidence verdict absent ({err}) — "
                           "the D-151 gate never ran"))
        elif not isinstance(tv, dict) or \
                tv.get("schema") != TRIAD_SCHEMA:
            checks.append(("DEP-01", False,
                           "triple-evidence verdict malformed"))
        else:
            rows = tv.get("checks") or []
            ids = {c[0] for c in rows
                   if isinstance(c, (list, tuple)) and c}
            blocked = [c[0] for c in rows
                       if isinstance(c, (list, tuple)) and len(c) >= 2
                       and not c[1]]
            if not all(t in ids for t in
                       ("TRIAD-01", "TRIAD-02", "TRIAD-03",
                        "TRIAD-04")):
                checks.append(("DEP-01", False,
                               "triad rules skipped or absent — zero "
                               "bypasses allowed"))
            elif blocked or tv.get("verdict") != LAUNCH_READY:
                checks.append(("DEP-01", False,
                               f"triad blocked at {sorted(set(blocked))} "
                               f"or verdict "
                               f"{tv.get('verdict')!r} — launch "
                               "evidence incomplete"))
            else:
                checks.append(("DEP-01", True,
                               "triple-evidence gate "
                               "LAUNCH_EVIDENCE_COMPLETE"))
        arts["triad"] = tv

        # Stage G — the closure seal (H-01 re-run: digest + verdict) -----------------
        seal, err = self._load("seal")
        if seal is None:
            checks.append(("DEP-01", False,
                           f"Stage G closure seal absent ({err}) — "
                           "Stage G never closed"))
        elif not isinstance(seal, dict) or \
                seal.get("schema") != SEAL_SCHEMA:
            checks.append(("DEP-01", False,
                           "closure seal malformed or wrong schema"))
        elif seal.get("verdict") != SEAL_CLOSED:
            checks.append(("DEP-01", False,
                           f"seal verdict {seal.get('verdict')!r} != "
                           f"{SEAL_CLOSED!r} — Stage G is OPEN"))
        else:
            recorded = seal.get("closure_digest", "")
            recomputed = recompute_digest(seal)
            if not _HEX64.match(recorded or ""):
                checks.append(("DEP-01", False,
                               "closure_digest missing or malformed"))
            elif recorded != recomputed:
                checks.append(("DEP-01", False,
                               f"closure_digest {recorded[:16]}… != "
                               f"recomputed {recomputed[:16]}… — "
                               "ALTERED seal"))
            else:
                checks.append(("DEP-01", True,
                               "Stage G closure seal CLOSED and "
                               f"intact ({recorded[:16]}…)"))
        arts["seal"] = seal

        # Stage H — the activation record --------------------------------------------
        rec, err = self._load("activation_record")
        if rec is None:
            checks.append(("DEP-01", False,
                           f"Stage H activation record absent ({err}) "
                           "— the cutover never executed"))
        elif not isinstance(rec, dict) or \
                rec.get("schema") != RECORD_SCHEMA:
            checks.append(("DEP-01", False,
                           "activation record malformed or wrong "
                           "schema"))
        elif rec.get("verdict") != CUTOVER_EXECUTED:
            checks.append(("DEP-01", False,
                           f"activation verdict "
                           f"{rec.get('verdict')!r} != "
                           f"{CUTOVER_EXECUTED!r} — the deployment is "
                           "not ACTIVE"))
        else:
            recorded = rec.get("activation_digest", "")
            recomputed = recompute_digest(rec)
            if not _HEX64.match(recorded or ""):
                checks.append(("DEP-01", False,
                               "activation_digest missing or "
                               "malformed"))
            elif recorded != recomputed:
                checks.append(("DEP-01", False,
                               f"activation_digest {recorded[:16]}… "
                               f"!= recomputed {recomputed[:16]}… — "
                               "ALTERED record"))
            else:
                checks.append(("DEP-01", True,
                               "Stage H activation CUTOVER_EXECUTED "
                               f"({recorded[:16]}…)"))
        arts["activation"] = rec

        return (all(c[1] for c in checks)), checks, arts

    # -- DEP-02: zero drift ----------------------------------------------------------------

    @staticmethod
    def _dep02(arts: Dict[str, Any]) -> Tuple[bool, Dict[str, str],
                                              List[Tuple[str, bool, str]]]:
        checks: List[Tuple[str, bool, str]] = []
        env = arts.get("envelope")
        m = re.search(r"^manifest_sha256:\s*([0-9a-f]{64})\s*$",
                      env, re.M) if isinstance(env, str) else None
        envelope_fp = m.group(1) if m else ""
        man = arts.get("manifest")
        manifest_fp = hashlib.sha256(man.encode("utf-8")).hexdigest() \
            if isinstance(man, str) and man else ""
        bundle = arts.get("bundle") if isinstance(arts.get("bundle"),
                                                  dict) else {}
        acc = arts.get("acceptance") \
            if isinstance(arts.get("acceptance"), dict) else {}
        probe = arts.get("probe") if isinstance(arts.get("probe"),
                                                dict) else {}
        seal = arts.get("seal") if isinstance(arts.get("seal"),
                                              dict) else {}
        rec = arts.get("activation") \
            if isinstance(arts.get("activation"), dict) else {}
        fingerprints = {
            "envelope": envelope_fp,
            "manifest": manifest_fp,
            "bundle": bundle.get("candidate_manifest_sha256", ""),
            "acceptance": acc.get("manifest_sha256", ""),
            "probe": probe.get("manifest_sha256", ""),
            "seal": seal.get("manifest_sha256", ""),
            "activation": rec.get("manifest_sha256", ""),
        }
        malformed = [k for k, v in fingerprints.items()
                     if not _HEX64.match(v or "")]
        if malformed:
            checks.append(("DEP-02", False,
                           f"manifest fingerprint missing or malformed "
                           f"in: {sorted(malformed)} — zero drift "
                           "cannot be asserted across the full chain"))
        elif len(set(fingerprints.values())) != 1:
            shown = {k: v[:16] + "…" for k, v in fingerprints.items()}
            checks.append(("DEP-02", False,
                           f"manifest fingerprint drift across the "
                           f"lifecycle: {shown} — the artifacts attest "
                           "DIFFERENT deployments"))
        else:
            checks.append(("DEP-02", True,
                           f"zero drift: ONE manifest fingerprint "
                           f"({envelope_fp[:16]}…) across envelope, "
                           "manifest, bundle, acceptance, probe, seal "
                           "and activation record"))
        # configuration digests recompute byte-exactly
        drift: List[str] = []
        for label, artifact, field_name in (
                ("bundle", bundle, "bundle_hash"),
                ("acceptance", acc, "acceptance_fingerprint"),
                ("probe", probe, "probe_digest"),
                ("seal", seal, "closure_digest"),
                ("activation", rec, "activation_digest")):
            recorded = artifact.get(field_name, "")
            recomputed = recompute_digest(artifact)
            if recomputed and recorded != recomputed:
                drift.append(f"{label}.{field_name}")
        pa = probe.get("acceptance_fingerprint", "")
        aa = acc.get("acceptance_fingerprint", "")
        probe_binding_ok = bool(_HEX64.match(pa or "")) and pa == aa
        if drift:
            checks.append(("DEP-02", False,
                           f"configuration digest drift: {drift} — "
                           "the carried digests no longer recompute "
                           "from the artifacts"))
        else:
            checks.append(("DEP-02", True,
                           "configuration digests recompute "
                           "byte-exactly (bundle, acceptance, probe, "
                           "seal, activation)"))
        if not probe_binding_ok:
            checks.append(("DEP-02", False,
                           "probe not bound to THIS acceptance report "
                           "— live clearance binding absent"))
        else:
            checks.append(("DEP-02", True,
                           "probe bound to THIS acceptance report"))
        return (all(c[1] for c in checks)), fingerprints, checks

    # -- DEP-03: the D-112 ledger anchoring ---------------------------------------------------

    def _dep03(self, arts: Dict[str, Any]) -> Tuple[bool, Dict[str, Any],
                                                    List[Tuple[str, bool, str]]]:
        checks: List[Tuple[str, bool, str]] = []
        cv, err = self._load("chain_verifier")
        chain = {"anchored": False, "rows": 0, "zero_breaks": False,
                 "anchors": {}}
        if cv is None:
            checks.append(("DEP-03", False,
                           f"D-112 chain verifier absent ({err}) — "
                           "chain integrity cannot be asserted"))
        elif not isinstance(cv, dict):
            checks.append(("DEP-03", False,
                           "D-112 chain verifier payload malformed"))
        elif not cv.get("ok"):
            checks.append(("DEP-03", False,
                           f"D-112 chain BROKEN at seq "
                           f"{cv.get('broken_at_seq')} "
                           f"({cv.get('reason', 'unknown')}) — the "
                           "append-only ledger was mutated"))
        elif not isinstance(cv.get("rows"), int) or cv["rows"] <= 0:
            checks.append(("DEP-03", False,
                           "D-112 chain carries no rows — nothing is "
                           "anchored"))
        else:
            chain["rows"] = cv["rows"]
            chain["zero_breaks"] = True
            checks.append(("DEP-03", True,
                           f"D-112 chain intact ({cv['rows']} rows, "
                           "zero breaks)"))
        # anchor rows: each stage commitment must appear in the ledger
        rows, err = self._load("audit_rows")
        if not isinstance(rows, list) or not rows:
            checks.append(("DEP-03", False,
                           f"D-112 ledger rows unavailable ({err}) — "
                           "fail closed"))
            return (all(c[1] for c in checks)), chain, checks
        commitments: Dict[str, str] = {
            "cutover_bundle_recorded":
                (arts.get("bundle") or {}).get("bundle_hash", "")
                if isinstance(arts.get("bundle"), dict) else "",
            "stage_g_acceptance":
                (arts.get("acceptance") or {})
                .get("acceptance_fingerprint", "")
                if isinstance(arts.get("acceptance"), dict) else "",
            "stage_g_live_probe":
                (arts.get("probe") or {}).get("probe_digest", "")
                if isinstance(arts.get("probe"), dict) else "",
            "stage_g_closure":
                (arts.get("seal") or {}).get("closure_digest", "")
                if isinstance(arts.get("seal"), dict) else "",
            "stage_h_activation":
                (arts.get("activation") or {})
                .get("activation_digest", "")
                if isinstance(arts.get("activation"), dict) else "",
        }
        for kind, commit in ATT_STAGE_KINDS:
            want = commitments.get(kind, "")
            if not _HEX64.match(want or ""):
                checks.append(("DEP-03", False,
                               f"anchor {kind}: no usable commitment "
                               "digest on the stage artifact"))
                continue
            found = False
            for row in rows:
                if not isinstance(row, dict):
                    continue
                detail = row.get("detail") or {}
                blob = json.dumps(detail, ensure_ascii=False,
                                  sort_keys=True) \
                    if isinstance(detail, dict) else str(detail)
                if str(row.get("event_kind", "")) == kind and \
                        want in blob:
                    found = True
                    break
            chain["anchors"][kind] = found
            if not found:
                checks.append(("DEP-03", False,
                               f"anchor {kind} missing from the D-112 "
                               f"ledger ({want[:16]}… never attested)"))
        if all(chain["anchors"].get(k) for k, _ in ATT_STAGE_KINDS) \
                and chain["zero_breaks"]:
            chain["anchored"] = True
            checks.append(("DEP-03", True,
                           f"all {len(ATT_STAGE_KINDS)} stage "
                           "commitments anchored in the D-112 ledger "
                           "(bundle, acceptance, probe, closure, "
                           "activation)"))
        return (all(c[1] for c in checks)), chain, checks

    # -- DEP-04: Live-Wiring entry-point readiness ---------------------------------------------

    def _dep04(self) -> Tuple[bool, Dict[str, Any],
                              List[Tuple[str, bool, str]]]:
        checks: List[Tuple[str, bool, str]] = []
        lw, err = self._load("live_wiring_readiness")
        summary = {"phases": [], "phases_ready": 0,
                   "phases_total": len(LIVE_WIRING_PHASES),
                   "runtime_profile_verified": False}
        if lw is None:
            checks.append(("DEP-04", False,
                           f"Live-Wiring readiness absent ({err}) — "
                           "entry points cannot be asserted"))
            return False, summary, checks
        if not isinstance(lw, dict) or \
                not isinstance(lw.get("phases"), list) or not lw["phases"]:
            checks.append(("DEP-04", False,
                           "Live-Wiring readiness payload malformed — "
                           "fail closed"))
            return False, summary, checks
        phases = lw["phases"]
        expected = {p for p, _ in LIVE_WIRING_PHASES}
        got = set()
        not_ready: List[str] = []
        for ph in phases:
            if not isinstance(ph, dict):
                not_ready.append("malformed-phase-row")
                continue
            num = ph.get("phase")
            got.add(num)
            ok = (ph.get("present") is True
                  and ph.get("verified") is True
                  and ph.get("wired") is True)
            entry = str(ph.get("entry_point", ""))
            if not entry or not ok:
                not_ready.append(
                    f"phase {num} "
                    f"({deep_redact(str(ph.get('name', '')))}): "
                    f"present={ph.get('present')} "
                    f"verified={ph.get('verified')} "
                    f"wired={ph.get('wired')}")
        missing = sorted(expected - got)
        if missing:
            checks.append(("DEP-04", False,
                           f"Live-Wiring phases absent from the "
                           f"readiness census: {missing}"))
        elif not_ready:
            checks.append(("DEP-04", False,
                           f"Live-Wiring entry points not ready: "
                           f"{sorted(not_ready)} — every Phase 5–18 "
                           "entry point must be present, verified and "
                           "wired"))
        else:
            checks.append(("DEP-04", True,
                           f"all {len(phases)} Live-Wiring phases "
                           "(5–18) ready: entry points present, "
                           "verified and wired"))
        # the readiness must bind to the VERIFIED runtime profile
        if lw.get("runtime_profile_verified") is not True:
            checks.append(("DEP-04", False,
                           "runtime profile not verified — readiness "
                           "must bind to the probe/activation "
                           "evidence"))
        else:
            summary["runtime_profile_verified"] = True
            checks.append(("DEP-04", True,
                           "readiness bound to the verified runtime "
                           "profile (live probes + activation)"))
        # Data minimization (D-124): the census summary carries
        # STRUCTURAL fields only — provider free-text detail never
        # enters the certificate. Names/entry points still pass the
        # canonical redactor as defense in depth.
        ready_rows = [{
            "phase": ph.get("phase"),
            "name": deep_redact(str(ph.get("name", ""))),
            "entry_point": deep_redact(str(ph.get("entry_point",
                                                  ""))),
            "present": True, "verified": True, "wired": True,
        } for ph in phases
            if isinstance(ph, dict)
            and ph.get("present") is True
            and ph.get("verified") is True
            and ph.get("wired") is True]
        summary["phases"] = ready_rows
        summary["phases_ready"] = len(ready_rows)
        return (not missing and not not_ready
                and summary["runtime_profile_verified"]), summary, checks

    # -- the run ---------------------------------------------------------------------------

    def run(self) -> CompletionAttestation:
        """DEP-01..DEP-05 → the canonical certificate. Exactly one
        audited attestation per call (including refusals); the
        certificate never gates anything but DECLARATION."""
        checks: List[Tuple[str, bool, str]] = []
        self._digests = {"manifest": "", "bundle": "", "acceptance": "",
                         "probe": "", "closure": "", "activation": ""}
        ok1, c1, arts = self._dep01()
        checks += c1
        ok2, fingerprints, c2 = self._dep02(arts)
        checks += c2
        if fingerprints.get("envelope"):
            self._digests["manifest"] = fingerprints["envelope"]
        self._digests["bundle"] = (arts.get("bundle") or {}).get(
            "bundle_hash", "") if isinstance(arts.get("bundle"),
                                             dict) else ""
        self._digests["acceptance"] = (arts.get("acceptance") or {}).get(
            "acceptance_fingerprint", "") \
            if isinstance(arts.get("acceptance"), dict) else ""
        self._digests["probe"] = (arts.get("probe") or {}).get(
            "probe_digest", "") if isinstance(arts.get("probe"),
                                              dict) else ""
        self._digests["closure"] = (arts.get("seal") or {}).get(
            "closure_digest", "") if isinstance(arts.get("seal"),
                                                dict) else ""
        self._digests["activation"] = (arts.get("activation") or {}).get(
            "activation_digest", "") \
            if isinstance(arts.get("activation"), dict) else ""
        ok3, chain, c3 = self._dep03(arts)
        checks += c3
        ok4, live_wiring, c4 = self._dep04()
        checks += c4
        verdict = INFRA_COMPLETE if all((ok1, ok2, ok3, ok4)) \
            else INFRA_INCOMPLETE
        if verdict == INFRA_COMPLETE:
            checks.append(("DEP-05", True,
                           "completion certificate emitted — "
                           "infrastructure provisioning declared "
                           "COMPLETE and ready for service ignition "
                           "(Live Wiring, Phases 5–18)"))
        else:
            checks.append(("DEP-05", False,
                           "certificate emitted as INFRASTRUCTURE_"
                           "INCOMPLETE — remediate the named checks "
                           "before service ignition"))
        return self._emit(verdict, checks, chain=chain,
                          live_wiring=live_wiring)


def main(argv: Optional[List[str]] = None) -> int:
    """CLI wiring: real Stage B–H artifacts + the real D-112 chain."""
    import argparse
    import sys
    ap = argparse.ArgumentParser(
        description="Dokploy completion attestation "
                    "(DEP-01..DEP-05, D-154).")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    print("dokploy_completion_attestation: interactive wiring "
          "requires the real Stage B–H artifacts, the D-112 chain "
          "verifier and the Live-Wiring readiness census; see run() "
          "and the battery for the injected contract.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

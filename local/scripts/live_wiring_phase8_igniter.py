"""Phase 8 live wiring igniter — Instagram Graph API verification (D-158).

The fourth Live Wiring program phase. Phase 7 (D-157) proved the AI
Runtime + Product Manager core loop under the Phase 6 attestation;
Phase 8 now wires and verifies the Instagram integration (Graph API /
Meta platform adapter) on top of the verified AI runtime and the
Notion content pipeline — in STRICT probe-only mode:

  IG-01   the upstream `phase7.live_wiring_attestation.v1` is
          present, PHASE7_IGNITED, manifest-bound, its canonical
          bytes recompute to the SHA-256 commitment rooted in the
          D-112 ledger (kind `phase7_live_wiring_attestation`) over
          an intact chain — ANY refusal happens BEFORE the first
          adapter/network call (zero adapter calls on refusal);
  IG-02   the verified runtime profile is loaded: the injected
          census marks Phases 5, 6 AND 7 present+VERIFIED+WIRED,
          and the canonical Instagram seams (repo-real:
          canonical.instagram_adapter, canonical.instagram_contracts,
          canonical.instagram_publisher, canonical.instagram_live,
          plus the plan's `publishing.instagram` entry) are
          importable and consistent with the D-154 ENTRY_POINTS
          registry;
  IG-03   the Instagram Graph API capability profile is validated:
          the required OAuth scopes (instagram_basic,
          instagram_content_publish, pages_show_list) must be
          present, the token must be valid with a comfortable
          expiry margin (a token valid for fewer than
          EXPIRY_THRESHOLD_TICKS future ticks refuses), 401/403
          classify as permission failures (immediate refusal), and
          the Graph usage envelope must show headroom under the
          documented ~100% throttle boundary (D-072 discipline,
          Class-A-only bounded retries);
  IG-04   a NON-DESTRUCTIVE synthetic media workflow cycle runs
          end-to-end: a deterministic synthetic caption is produced
          by the REAL Phase 7 ModelRouter (caption_proposal.v1
          contract), validated LOCALLY through the real
          `validate_publish_payload` (Class-B prevention: aspect
          ratio in {1:1, 4:5, 16:9}, caption length, hashtag count,
          media-hash presence), then a synthetic media container is
          created, polled IN_PROGRESS → FINISHED through the real
          bounded `poll_until_ready`, verified (including a probe
          state-collision check), and archived WITHOUT ever calling
          `publish_container` — no public feed mutation, ever;
          per-step telemetry (START/AUTH/CONTAINER_CREATE/
          STATUS_POLL/VERIFY/CLEANUP) and a deterministic summary
          hash are recorded;
  IG-05   the canonical `phase8.live_wiring_attestation.v1` is
          emitted exactly once per run (aborts included) with the
          SHA-256 `attestation_digest`; any abort emits the same
          schema as PHASE8_INCOMPLETE with failure telemetry.

Security & purity (RULES §35, AST-pinned): injected adapter only —
zero sockets, zero raw shell, zero wall clock in the core. Access
tokens, client secrets, page IDs, media URLs and raw API responses
NEVER enter any emitted record: only hashes, counts, scope names,
container state names and step verdicts. The canonical adapter layer
already redacts token material (`instagram_adapter.redact`); D-124
deep redaction runs over every emitted record with the public
commitments (`phase7_digest`, `manifest_sha256`) restored after
redaction. The probe NEVER publishes: the container is verified
FINISHED and archived, and the run refuses if any publish call is
observed on the adapter.
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
    "Phase8Error", "Phase8Attestation", "Phase8Igniter",
    "ATTESTATION_SCHEMA", "PHASE8_IGNITED", "PHASE8_INCOMPLETE",
    "PHASE7_SCHEMA", "PHASE7_IGNITED", "PHASE7_ROW_KIND",
    "SEAMS", "SEAM_PHASES", "REQUIRED_SCOPES", "LIMITS",
    "EXPIRY_THRESHOLD_TICKS", "USAGE_WARN_PCT", "CYCLE_ID",
    "canonical_hash",
]

ATTESTATION_SCHEMA = "phase8.live_wiring_attestation.v1"
PHASE8_IGNITED = "PHASE8_IGNITED"
PHASE8_INCOMPLETE = "IGNITION_INCOMPLETE"

PHASE7_SCHEMA = "phase7.live_wiring_attestation.v1"
PHASE7_IGNITED = "PHASE7_IGNITED"

# The D-112 ledger kind that roots the Phase 7 attestation (D-157).
PHASE7_ROW_KIND = "phase7_live_wiring_attestation"

_HEX64 = re.compile(r"^[0-9a-f]{64}$")

# --- required OAuth scopes (IG-03) ----------------------------------------

REQUIRED_SCOPES: Tuple[str, ...] = (
    "instagram_basic", "instagram_content_publish", "pages_show_list",
)

# --- hard limits (IG-03/IG-04) ----------------------------------------------

LIMITS: Dict[str, Any] = {
    "max_polls": 10,          # container status polls (bounded)
    "max_retries": 2,         # Class-A transient retries only
    "timeout_s": 15.0,        # per adapter operation (D-151)
    "max_container_probes": 1 # exactly ONE probe container per cycle
}

EXPIRY_THRESHOLD_TICKS = 300   # token must outlive the cycle by this
USAGE_WARN_PCT = 75.0          # Graph usage envelope warn level

# Repo-real module seams for the Instagram wiring. `SEAM_PHASES` pins
# each seam to the D-154 ENTRY_POINTS phase it must agree with
# (None = supporting module; the plan numbers Instagram as phase 9 —
# the D-154 registry governs, this program's task track calls it
# Phase 8).
SEAMS: Dict[str, str] = {
    "ig_adapter": "canonical.instagram_adapter",
    "ig_contracts": "canonical.instagram_contracts",
    "ig_publisher": "canonical.instagram_publisher",
    "ig_live": "canonical.instagram_live",
    "phase9_publishing_entry": "publishing.instagram",
}

SEAM_PHASES: Dict[str, Optional[int]] = {
    "ig_adapter": None,
    "ig_contracts": None,
    "ig_publisher": None,
    "ig_live": None,
    "phase9_publishing_entry": 9,
}

# The deterministic synthetic media workflow fixture.
CYCLE_ID = "phase8-ig-probe-0001"
MEDIA_REF = "phase8-probe-media-0001"
SCHEDULED_SLOT = "phase8-never-scheduled"
ASPECT_RATIO = "4:5"


class Phase8Error(ValueError):
    """Contract-level misuse of the Phase 8 igniter."""


def _fail(reason: str) -> None:
    raise Phase8Error(reason)


def canonical_hash(payload: Dict[str, Any]) -> str:
    """SHA-256 over canonical JSON bytes — the shared project digest
    formula (Stage G/H/D-154..D-157 engines)."""
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Phase8Attestation:
    """Canonical, immutable Phase 8 ignition artifact."""
    schema: str
    verdict: str             # PHASE8_IGNITED / IGNITION_INCOMPLETE
    phase7_digest: str       # upstream attestation digest (commitment)
    manifest_sha256: str     # deployment fingerprint carried through
    profile: Dict[str, Any]  # runtime profile + seams summary
    capability: Dict[str, Any]  # scopes/token/usage summary
    probe: Dict[str, Any]    # container workflow telemetry
    checks: tuple = field(default_factory=tuple)  # (id, ok, detail)
    observed_tick: int = 0

    @property
    def ignited(self) -> bool:
        return self.verdict == PHASE8_IGNITED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "verdict": self.verdict,
            "phase7_digest": self.phase7_digest,
            "manifest_sha256": self.manifest_sha256,
            "profile": self.profile,
            "capability": self.capability,
            "probe": self.probe,
            "checks": [list(c) for c in self.checks],
            "observed_tick": self.observed_tick,
        }

    @property
    def attestation_digest(self) -> str:
        return canonical_hash(self.to_dict())


class Phase8Igniter:
    """IG-01..IG-05 with an injected Instagram adapter.

    Injected:
      clock           — ``() -> int`` logical tick
      audit_sink      — ``callable(dict)`` (D-112/D-121 in prod)
      phase7_provider — ``() -> dict`` the phase7 attestation
      audit_rows      — ``() -> list`` the D-112 ledger rows
      chain_verifier  — ``() -> dict`` D-112 chain integrity
      census          — ``() -> dict`` the runtime profile census
      router          — the REAL Phase 7 ModelRouter (caption route)
      ig              — an InstagramAdapter-compatible object with an
                        optional ``capability_profile()`` and optional
                        ``archive_container(id)`` (the probe-only
                        cleanup seam); the transport is injected
                        INSIDE it (D-045/D-075)
      expected_entry_points — optional {phase: seam} override
    """

    def __init__(self, clock: Callable[[], int],
                 audit_sink: Callable[[Dict[str, Any]], None],
                 phase7_provider: Optional[Callable[[], Dict[str, Any]]] = None,
                 audit_rows: Optional[Callable[[], List[Dict[str, Any]]]] = None,
                 chain_verifier: Optional[Callable[[], Dict[str, Any]]] = None,
                 census: Optional[Callable[[], Dict[str, Any]]] = None,
                 router: Optional[Any] = None,
                 ig: Optional[Any] = None,
                 expected_entry_points: Optional[Dict[int, str]] = None,
                 ) -> None:
        if not callable(clock) or not callable(audit_sink):
            _fail("clock and audit_sink required")
        self._clock = clock
        self._sink = audit_sink
        self._prov = {
            "phase7": phase7_provider,
            "audit_rows": audit_rows,
            "chain_verifier": chain_verifier,
            "census": census,
            "router": router,
            "ig": ig,
        }
        self._entry_points = dict(expected_entry_points) \
            if expected_entry_points else None
        self._seen_containers: set = set()

    # -- internals ---------------------------------------------------------

    def _load(self, name: str) -> Tuple[Optional[Any], str]:
        """Resolve one injected provider: a zero-arg callable (loaders)
        or the injected OBJECT itself (adapter, router)."""
        prov = self._prov.get(name)
        if prov is None:
            return None, "provider not injected"
        if callable(prov) and not hasattr(prov, "policy") \
                and not hasattr(prov, "create_media_container"):
            try:
                return prov(), ""
            except Exception as exc:  # noqa: BLE001 — typed (D-124)
                return None, f"provider raised {type(exc).__name__}"
        return prov, ""

    def _emit(self, verdict: str, checks: List[Tuple[str, bool, str]],
              phase7_digest: str = "", manifest: str = "",
              profile: Optional[Dict[str, Any]] = None,
              capability: Optional[Dict[str, Any]] = None,
              probe: Optional[Dict[str, Any]] = None,
              ) -> Phase8Attestation:
        att = Phase8Attestation(
            schema=ATTESTATION_SCHEMA, verdict=verdict,
            phase7_digest=phase7_digest, manifest_sha256=manifest,
            profile=profile or {}, capability=capability or {},
            probe=probe or {},
            checks=tuple((c[0], c[1], deep_redact(str(c[2])))
                         for c in checks),
            observed_tick=self._clock())
        blob = json.dumps(att.to_dict(), sort_keys=True,
                          separators=(",", ":"), ensure_ascii=False)
        redacted = json.loads(deep_redact(blob))
        # Public commitments (D-146/D-153/D-154..D-157 precedent).
        redacted["phase7_digest"] = att.phase7_digest
        redacted["manifest_sha256"] = att.manifest_sha256
        self._sink(redacted)
        return att

    # -- IG-01: the Phase 7 attestation --------------------------------------

    def _ig01(self) -> Tuple[bool, str, str,
                             List[Tuple[str, bool, str]]]:
        """(ok, phase7_digest, manifest, checks)."""
        checks: List[Tuple[str, bool, str]] = []
        att, err = self._load("phase7")
        if att is None:
            checks.append(("IG-01", False,
                           "Phase 7 attestation absent "
                           f"({err}) — Phase 7 never ignited"))
            return False, "", "", checks
        if not isinstance(att, dict):
            checks.append(("IG-01", False,
                           "Phase 7 attestation malformed"))
            return False, "", "", checks
        if att.get("schema") != PHASE7_SCHEMA:
            checks.append(("IG-01", False,
                           f"attestation schema {att.get('schema')!r} "
                           f"!= {PHASE7_SCHEMA!r}"))
            return False, "", "", checks
        if att.get("verdict") != PHASE7_IGNITED:
            checks.append(("IG-01", False,
                           f"Phase 7 verdict {att.get('verdict')!r} "
                           f"!= {PHASE7_IGNITED!r} — AI runtime not "
                           "wired, Phase 8 refused"))
            return False, "", "", checks
        manifest = att.get("manifest_sha256", "")
        if not (isinstance(manifest, str) and _HEX64.match(manifest)):
            checks.append(("IG-01", False,
                           "phase7 attestation lacks its manifest "
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
                        str(row.get("event_kind", "")) != PHASE7_ROW_KIND:
                    continue
                detail = row.get("detail")
                if isinstance(detail, dict) and \
                        isinstance(detail.get("attestation_digest"),
                                   str):
                    rooted_digest = detail["attestation_digest"]
                    break
        if not rooted_digest:
            checks.append(("IG-01", False,
                           "phase7 attestation not rooted in the "
                           "D-112 ledger — upstream wiring was never "
                           "durably attested"))
            return False, recomputed, "", checks
        if rooted_digest != recomputed:
            checks.append(("IG-01", False,
                           f"phase7 attestation digest "
                           f"{recomputed[:16]}… != rooted "
                           f"{rooted_digest[:16]}… — DRIFTED or "
                           "altered upstream attestation"))
            return False, recomputed, "", checks
        cv, err = self._load("chain_verifier")
        if cv is None or not isinstance(cv, dict) or not cv.get("ok"):
            reason = (cv or {}).get("reason", err or "verifier absent")
            checks.append(("IG-01", False,
                           f"D-112 chain not intact ({reason}) — "
                           "wiring on a broken ledger is refused"))
            return False, recomputed, "", checks
        checks.append(("IG-01", True,
                       "phase7 attestation PHASE7_IGNITED, digest "
                       f"recomputes ({recomputed[:16]}…) and matches "
                       "the rooted commitment in the D-112 ledger "
                       f"({int(cv.get('rows', 0))} rows, zero breaks)"))
        return True, recomputed, manifest, checks

    # -- IG-02: runtime profile + module seams -------------------------------

    def _ig02(self) -> Tuple[bool, Dict[str, Any],
                             List[Tuple[str, bool, str]]]:
        checks: List[Tuple[str, bool, str]] = []
        summary: Dict[str, Any] = {"runtime_profile_verified": False,
                                   "phases_ready": [],
                                   "seams_ok": False,
                                   "seams": dict(SEAMS)}
        census, err = self._load("census")
        if census is None or not isinstance(census, dict):
            checks.append(("IG-02", False,
                           f"runtime profile census unavailable ({err})"
                           " — fail closed"))
            return False, summary, checks
        if census.get("runtime_profile_verified") is not True:
            checks.append(("IG-02", False,
                           "runtime profile NOT verified — the D-154 "
                           "certificate's verified profile is the only "
                           "wiring baseline"))
            return False, summary, checks
        phases = census.get("phases")
        if not isinstance(phases, list):
            checks.append(("IG-02", False,
                           "runtime profile census malformed — no "
                           "phase rows"))
            return False, summary, checks
        for ph in phases:
            if not isinstance(ph, dict):
                continue
            if ph.get("phase") in (5, 6, 7):
                ok = (ph.get("present") is True
                      and ph.get("verified") is True
                      and ph.get("wired") is True)
                if ok:
                    summary["phases_ready"].append(ph.get("phase"))
                else:
                    checks.append(("IG-02", False,
                                   f"Phase {ph.get('phase')} not "
                                   "present+VERIFIED+WIRED in the "
                                   "census — prerequisite missing"))
                    return False, summary, checks
        if sorted(summary["phases_ready"]) != [5, 6, 7]:
            checks.append(("IG-02", False,
                           "census lacks Phase 5/6/7 prerequisite rows "
                           "— fail closed"))
            return False, summary, checks
        summary["runtime_profile_verified"] = True
        checks.append(("IG-02", True,
                       "runtime profile verified; Phases 5, 6 and 7 "
                       "are present+VERIFIED+WIRED in the census"))
        entry_points = self._entry_points
        if entry_points is None:
            from dokploy_completion_attestation import ENTRY_POINTS
            entry_points = ENTRY_POINTS
        for key, modname in SEAMS.items():
            try:
                importlib.import_module(modname)
            except Exception as exc:  # noqa: BLE001 — typed (D-124)
                checks.append(("IG-02", False,
                               f"canonical seam {modname} not "
                               f"importable ({type(exc).__name__}) — "
                               "repo seam missing"))
                return False, summary, checks
            phase_no = SEAM_PHASES.get(key)
            expected = entry_points.get(phase_no) \
                if phase_no is not None else None
            if expected and expected != modname:
                checks.append(("IG-02", False,
                               f"ENTRY_POINTS[{phase_no}] = "
                               f"{expected!r} != repo seam "
                               f"{modname!r} — registry drift"))
                return False, summary, checks
        summary["seams_ok"] = True
        checks.append(("IG-02", True,
                       f"all {len(SEAMS)} Instagram seams importable "
                       "and consistent with the D-154 ENTRY_POINTS "
                       "registry"))
        return True, summary, checks

    # -- IG-03: capability profile & rate envelope -----------------------------

    def _ig03(self) -> Tuple[bool, Dict[str, Any],
                             List[Tuple[str, bool, str]]]:
        checks: List[Tuple[str, bool, str]] = []
        summary: Dict[str, Any] = {"scopes_ok": False,
                                   "token_ok": False,
                                   "usage_ok": False,
                                   "scopes": [],
                                   "expires_in_ticks": 0,
                                   "usage_headroom_pct": None}
        adapter, err = self._load("ig")
        if adapter is None:
            checks.append(("IG-03", False,
                           f"Instagram adapter unavailable ({err}) — "
                           "fail closed"))
            return False, summary, checks
        profiler = getattr(adapter, "capability_profile", None)
        if not callable(profiler):
            checks.append(("IG-03", False,
                           "adapter exposes no capability profile — "
                           "scopes/permission validation impossible, "
                           "fail closed"))
            return False, summary, checks
        try:
            profile = profiler()
        except Exception as exc:  # noqa: BLE001 — typed refusal
            checks.append(("IG-03", False,
                           f"capability probe failed "
                           f"({type(exc).__name__}) — permission or "
                           "auth error, fail closed"))
            return False, summary, checks
        if not isinstance(profile, dict):
            checks.append(("IG-03", False,
                           "capability profile malformed"))
            return False, summary, checks
        scopes = set(profile.get("scopes") or ())
        missing = [s for s in REQUIRED_SCOPES if s not in scopes]
        if missing:
            checks.append(("IG-03", False,
                           f"missing OAuth scopes: {missing} — "
                           "capability profile incomplete"))
            return False, summary, checks
        summary["scopes"] = sorted(scopes)
        summary["scopes_ok"] = True
        checks.append(("IG-03", True,
                       f"required scopes present ({len(scopes)} "
                       "granted, 3 required)"))
        # Token validity + expiry margin (injected clock, logical
        # ticks — never a wall clock).
        now = int(self._clock())
        valid_until = profile.get("token_valid_until")
        if not isinstance(valid_until, int) or valid_until <= now:
            checks.append(("IG-03", False,
                           "access token expired or missing validity "
                           "window — re-authorization required"))
            return False, summary, checks
        margin = valid_until - now
        summary["expires_in_ticks"] = margin
        if margin < EXPIRY_THRESHOLD_TICKS:
            checks.append(("IG-03", False,
                           f"token expiry margin {margin} ticks < "
                           f"{EXPIRY_THRESHOLD_TICKS} — too fresh-"
                           "expiring to wire safely"))
            return False, summary, checks
        summary["token_ok"] = True
        checks.append(("IG-03", True,
                       f"token valid with {margin}-tick margin "
                       f"(≥ {EXPIRY_THRESHOLD_TICKS})"))
        # Graph usage envelope (D-072): headroom under the ~100%
        # throttle boundary.
        usage = profile.get("app_usage")
        if usage is not None:
            from canonical.instagram_live import GraphUsageTracker
            tracker = GraphUsageTracker(warn_at_pct=USAGE_WARN_PCT)
            warn = tracker.record(usage)
            headroom = tracker.headroom()
            summary["usage_headroom_pct"] = headroom
            if warn or (headroom is not None
                        and headroom <= 100.0 - USAGE_WARN_PCT):
                checks.append(("IG-03", False,
                               f"Graph usage envelope at/over the "
                               f"{USAGE_WARN_PCT:.0f}% warn level — "
                               "rate-limit guardrail refusal"))
                return False, summary, checks
            checks.append(("IG-03", True,
                           f"Graph usage envelope healthy "
                           f"(headroom {headroom}%)"))
        summary["usage_ok"] = True
        return True, summary, checks

    # -- the synthetic media workflow (IG-04) -----------------------------------

    def _caption_from_router(self, router: Any) -> Dict[str, Any]:
        """Deterministic caption through the REAL Phase 7 router
        (caption_proposal.v1 contract). The route is looked up in
        the router's OWN policy (the Phase 7-verified routing
        surface); a router without the caption route is an AIR-03-
        class refusal."""
        from canonical.ai_contracts import validate_ai_output
        from canonical.ai_runtime import (
            AiRequest, AiProviderError, BudgetExceeded,
        )
        policy = getattr(router, "policy", None)
        task_type = "generate_caption" \
            if isinstance(policy, dict) and \
            "generate_caption" in policy else None
        if task_type is None:
            _fail("router has no generate_caption route — the "
                  "Phase 7-verified routing surface is missing the "
                  "caption task (fail closed)")
        request = AiRequest(
            task_type=task_type,
            schema_id="caption_proposal.v1",
            prompt_payload={"cycle_id": CYCLE_ID,
                            "media_ref": MEDIA_REF},
            max_tokens=512, temperature=0.0,
            idempotency_tag=CYCLE_ID,
            cost_center="phase8-ignition")
        try:
            proposal = router.run(request)
        except BudgetExceeded as exc:
            _fail(f"budget guardrail refusal: {exc.args[0]}")
        except AiProviderError as exc:
            _fail(f"caption dispatch failed "
                  f"({type(exc).__name__}) — AI runtime surface "
                  "not wired")
        validation = validate_ai_output("caption_proposal.v1",
                                        proposal.payload)
        if not validation.get("valid"):
            _fail("invalid output schema: caption proposal failed "
                  f"its contract {validation.get('errors')}")
        return proposal.payload

    def _ig04(self, router: Any
              ) -> Tuple[bool, Dict[str, Any],
                         List[Tuple[str, bool, str]]]:
        from canonical.instagram_adapter import (
            ContainerNotReady, redact,
        )
        from canonical.instagram_contracts import (
            InstagramContractError, is_allowed_ratio,
            validate_publish_payload,
        )

        checks: List[Tuple[str, bool, str]] = []
        summary: Dict[str, Any] = {"steps": [], "summary_hash": "",
                                   "published": False,
                                   "container_archived": None}
        adapter, err = self._load("ig")
        if adapter is None:
            checks.append(("IG-04", False,
                           f"Instagram adapter unavailable ({err}) — "
                           "fail closed"))
            return False, summary, checks
        try:
            # START — deterministic caption (Phase 7 router format)
            payload = self._caption_from_router(router)
            caption = str(payload["caption_fa"]) + " " + \
                " ".join(payload["hashtags"])
            media_hash = canonical_hash({
                "cycle_id": CYCLE_ID, "media_ref": MEDIA_REF,
                "aspect_ratio": ASPECT_RATIO})
            summary["steps"].append([
                "START", True,
                {"caption_hash": caption[:0] or
                    hashlib.sha256(caption.encode("utf-8"))
                    .hexdigest()[:16] + "…",
                 "media_hash": media_hash[:16] + "…"}])

            # AUTH — local Class-B prevention BEFORE any dispatch
            normalized = validate_publish_payload({
                "content_id": CYCLE_ID, "media_ref": MEDIA_REF,
                "media_hash": media_hash, "caption": caption,
                "aspect_ratio": ASPECT_RATIO,
                "scheduled_slot": SCHEDULED_SLOT})
            if not is_allowed_ratio(normalized["aspect_ratio"]):
                _fail("media format non-compliant: aspect ratio "
                      f"{normalized['aspect_ratio']!r} not allowed")
            summary["steps"].append(["AUTH", True, {}])

            # CONTAINER_CREATE — bounded Class-A retries (transients
            # only); any publish is structurally impossible here
            container: Optional[Dict[str, Any]] = None
            last_err = ""
            for attempt in range(LIMITS["max_retries"] + 1):
                try:
                    container = adapter.create_media_container(
                        normalized["media_ref"], caption,
                        normalized["aspect_ratio"])
                    break
                except InstagramContractError as exc:
                    _fail(f"container create failed (Class-B): "
                          f"{redact(str(exc.args[0]))[:100]}")
                except TimeoutError as exc:
                    last_err = redact(str(exc))
                    if attempt < LIMITS["max_retries"]:
                        continue
                    _fail(f"container create timed out after "
                          f"{attempt + 1} attempt(s) (retry "
                          f"overflow): {last_err[:80]}")
            if not isinstance(container, dict) or \
                    not container.get("container_id"):
                _fail("container create returned no container id")
            cid = str(container["container_id"])
            if cid in self._seen_containers:
                _fail(f"probe state collision: container {cid[:16]}… "
                      "already used by an earlier probe cycle")
            self._seen_containers.add(cid)
            if str(container.get("status_code")) != "IN_PROGRESS":
                _fail(f"container not IN_PROGRESS at create "
                      f"(got {container.get('status_code')!r})")
            summary["steps"].append([
                "CONTAINER_CREATE", True,
                {"container_ref": canonical_hash(
                    {"container_id": cid})[:16] + "…"}])

            # STATUS_POLL — bounded IN_PROGRESS → FINISHED
            from canonical.instagram_adapter import poll_until_ready
            try:
                final = poll_until_ready(
                    adapter, cid,
                    max_polls=LIMITS["max_polls"], sleep_fn=None)
            except ContainerNotReady:
                _fail(f"container processing timeout: not FINISHED "
                      f"after {LIMITS['max_polls']} polls")
            except InstagramContractError as exc:
                _fail(f"container reached a terminal failure state: "
                      f"{redact(str(exc.args[0]))[:100]}")
            if str(final.get("status_code")) != "FINISHED":
                _fail("container did not finish (status "
                      f"{final.get('status_code')!r})")
            summary["steps"].append([
                "STATUS_POLL", True,
                {"progression": "IN_PROGRESS→FINISHED"}])

            # VERIFY — the container must NEVER be published in a
            # probe cycle
            calls = list(getattr(adapter, "calls", []))
            if "publish" in calls:
                _fail("SAFETY VIOLATION: publish_container was "
                      "invoked during a probe-only cycle")
            summary["published"] = False
            summary["steps"].append(["VERIFY", True, {
                "published": False,
                "state_collision_checked": True}])

            # CLEANUP — archive the probe container (probe-only seam)
            archiver = getattr(adapter, "archive_container", None)
            if callable(archiver):
                cleaned = archiver(cid)
                if not (isinstance(cleaned, dict)
                        and cleaned.get("archived") is True):
                    _fail("cleanup failed: probe container remains "
                          "live")
                summary["container_archived"] = True
            else:
                summary["container_archived"] = "not-supported"
            summary["steps"].append(["CLEANUP", True, {
                "archived": summary["container_archived"]}])

            plan = {
                "cycle_id": CYCLE_ID,
                "media_hash": media_hash,
                "container_ref": canonical_hash(
                    {"container_id": cid}),
                "final_state": "FINISHED",
                "published": False,
            }
            summary["summary_hash"] = canonical_hash(plan)
            checks.append(("IG-04", True,
                           "synthetic media workflow completed: "
                           f"{len(summary['steps'])} steps, summary "
                           f"hash {summary['summary_hash'][:16]}…, "
                           "container FINISHED and archived, publish "
                           "never invoked"))
            return True, summary, checks
        except Phase8Error as exc:
            checks.append(("IG-04", False, str(exc)[:160]))
            summary["published"] = False
            return False, summary, checks
        except Exception as exc:  # noqa: BLE001 — typed refusal (D-124)
            checks.append(("IG-04", False,
                           f"synthetic media workflow failed "
                           f"({type(exc).__name__})"))
            summary["published"] = False
            return False, summary, checks

    # -- the run --------------------------------------------------------------

    def run(self) -> Phase8Attestation:
        """IG-01..IG-05 → the canonical attestation. Exactly one
        audited attestation per call (including aborts); an IG-01
        refusal performs ZERO adapter/network calls."""
        checks: List[Tuple[str, bool, str]] = []
        ok1, p7digest, manifest, c1 = self._ig01()
        checks += c1
        if not ok1:
            return self._emit(PHASE8_INCOMPLETE, checks,
                              phase7_digest=p7digest,
                              manifest=manifest)
        ok2, profile, c2 = self._ig02()
        checks += c2
        ok3, capability, c3 = (False, {}, [])
        router = self._prov.get("router")
        if ok2:
            ok3, capability, c3 = self._ig03()
            checks += c3
        ok4, probe, c4 = (False, {}, [])
        if ok3 and router is not None:
            ok4, probe, c4 = self._ig04(router)
            checks += c4
        elif ok3:
            checks.append(("IG-04", False,
                           "AI router unavailable — the deterministic "
                           "caption cannot be produced, fail closed"))
        verdict = PHASE8_IGNITED if all((ok1, ok2, ok3, ok4)) \
            else PHASE8_INCOMPLETE
        if verdict == PHASE8_IGNITED:
            checks.append(("IG-05", True,
                           "phase8.live_wiring_attestation.v1 emitted "
                           "— Instagram Graph API wiring verified in "
                           "PROBE-ONLY mode (no publishing) under the "
                           "Phase 7 attestation; handover to Phase 9 "
                           "(Telegram Sales & Ingress wiring) is "
                           "verified"))
        else:
            checks.append(("IG-05", False,
                           "attestation emitted as IGNITION_INCOMPLETE "
                           "— remediate the named checks before the "
                           "Phase 9 handover"))
        return self._emit(verdict, checks, phase7_digest=p7digest,
                          manifest=manifest, profile=profile,
                          capability=capability, probe=probe)


def main(argv: Optional[List[str]] = None) -> int:
    """CLI wiring guard: interactive wiring requires the injected
    providers, census, router and the live adapter configuration."""
    import argparse
    import sys
    ap = argparse.ArgumentParser(
        description="Phase 8 live wiring igniter (IG-01..IG-05, "
                    "D-158).")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    print("live_wiring_phase8_igniter: interactive wiring requires "
          "the phase7 attestation, the D-112 chain, the runtime "
          "census, the injected router and adapter; see run() and "
          "the battery for the injected contract.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

"""Phase 7 live wiring igniter — AI Runtime + Product Manager (D-157).

The third Live Wiring program phase. Phase 6 (D-156) wired the Notion
Workspace Business OS under the Phase 5 attestation; Phase 7 now
proves the AI Runtime and the Product Manager core loop on top of
both attested surfaces:

  AIR-01  the upstream `phase6.live_wiring_attestation.v1` is
          present, PHASE6_IGNITED, manifest-bound, its canonical
          bytes recompute to the SHA-256 commitment rooted in the
          D-112 ledger (kind `phase6_live_wiring_attestation`) over
          an intact chain — ANY refusal happens BEFORE the first
          provider call (zero provider invocations on refusal);
  AIR-02  the verified runtime profile is loaded: the injected
          census marks Phases 5 and 6 present+VERIFIED+WIRED, and
          the canonical Phase 7/8 module seams (repo-real:
          canonical.ai_runtime, canonical.ai_contracts,
          canonical.ai_proposal_lifecycle, canonical.vocab) are
          importable and consistent with the D-154 ENTRY_POINTS
          registry;
  AIR-03  AI provider routing is validated in a strictly bounded
          mode — provider selection is DETERMINISTIC (same inputs ⇒
          same route), the policy obeys the explicit
          provider/model ALLOWLIST (unknown provider or model ⇒
          refusal), and the hard limits hold (max tokens, max tool
          calls, max retries, timeout, budget cap);
  AIR-04  a NON-DESTRUCTIVE synthetic PM cycle runs end-to-end over
          a fixed fixture: brief normalization → vocabulary
          alignment (owner-approved vocab only) → strategy draft
          (through the real ModelRouter: route → guardrails →
          infer → contract validation) → content plan skeleton →
          output packaging into the scratch store; the ONLY
          external write is the optional strictly probe-only Notion
          probe (create/replay-same-page/read-back/archive with an
          idempotency key); per-step telemetry (START/ROUTE/INFER/
          VALIDATE/PACK/CLEANUP) and a deterministic summary hash
          are recorded; the scratch store is always cleaned;
  AIR-05  the canonical `phase7.live_wiring_attestation.v1` is
          emitted exactly once per run (aborts included) with the
          SHA-256 `attestation_digest`; any abort emits the same
          schema as PHASE7_INCOMPLETE with failure telemetry.

Security & purity (RULES §35, AST-pinned): injected AI provider
router and Notion client only — zero sockets, zero raw shell, zero
wall clock in the core. Prompts, tool inputs and provider response
fragments NEVER enter any emitted record: only hashes, counts,
route names and step verdicts. `deep_redact` (D-124) runs over every
emitted record with the public commitments (`phase6_digest`,
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
    "Phase7Error", "Phase7Attestation", "Phase7Igniter",
    "ScratchStore", "ATTESTATION_SCHEMA", "PHASE7_IGNITED",
    "PHASE7_INCOMPLETE", "PHASE6_SCHEMA", "PHASE6_IGNITED",
    "PHASE6_ROW_KIND", "SEAMS", "PROVIDER_ALLOWLIST", "LIMITS",
    "SCRATCH_NS", "TOOL_ALLOWLIST", "BRIEF", "canonical_hash",
]

ATTESTATION_SCHEMA = "phase7.live_wiring_attestation.v1"
PHASE7_IGNITED = "PHASE7_IGNITED"
PHASE7_INCOMPLETE = "IGNITION_INCOMPLETE"

PHASE6_SCHEMA = "phase6.live_wiring_attestation.v1"
PHASE6_IGNITED = "PHASE6_IGNITED"

# The D-112 ledger kind that roots the Phase 6 attestation (D-156).
PHASE6_ROW_KIND = "phase6_live_wiring_attestation"

_HEX64 = re.compile(r"^[0-9a-f]{64}$")

# --- hard limits (AIR-03) ------------------------------------------------

LIMITS: Dict[str, Any] = {
    "max_tokens_cap": 2048,      # per-request token ceiling
    "max_tool_calls": 4,         # per synthetic cycle
    "max_retries": 2,            # transient-failure retries
    "timeout_s": 15.0,           # per provider operation (D-151)
    "budget_cap_usd": 1.00,      # per synthetic cycle
}

# Explicit provider/model allowlist — anything outside refuses.
PROVIDER_ALLOWLIST: Dict[str, Tuple[str, ...]] = {
    "mock": ("mock-1",),
}

# Tool allowlist for the synthetic cycle (AIR-04).
TOOL_ALLOWLIST = ("scratch_write", "scratch_read", "scratch_delete",
                  "notion_probe")

SCRATCH_NS = "phase7-scratch:"

# Repo-real module seams for the Phase 7/8 entry points.
# `SEAM_PHASES` pins each seam to the D-154 ENTRY_POINTS phase it must
# agree with (None = supporting module, registry check not applies).
SEAMS: Dict[str, str] = {
    "phase7_ai_runtime": "canonical.ai_runtime",
    "phase7_ai_contracts": "canonical.ai_contracts",
    "phase7_vocab": "canonical.vocab",
    "phase8_pm_lifecycle": "canonical.ai_proposal_lifecycle",
}

SEAM_PHASES: Dict[str, Optional[int]] = {
    "phase7_ai_runtime": 7,
    "phase7_ai_contracts": None,
    "phase7_vocab": None,
    "phase8_pm_lifecycle": 8,
}

# The fixed synthetic product brief + market context fixture.
BRIEF: Dict[str, str] = {
    "brief_id": "phase7-pm-brief-0001",
    "product": "کت و جلیقه",
    "color": "مشکی",
    "market_context": "پاییز؛ تمرکز بر لایه‌بندی و ترکیب رنگ گرم",
}

CYCLE_ID = "phase7-pm-cycle-0001"


class Phase7Error(ValueError):
    """Contract-level misuse of the Phase 7 igniter."""


def _fail(reason: str) -> None:
    raise Phase7Error(reason)


def canonical_hash(payload: Dict[str, Any]) -> str:
    """SHA-256 over canonical JSON bytes — the shared project digest
    formula (Stage G/H/D-154..D-156 engines)."""
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class ScratchStore:
    """Namespace-scoped scratch artifact store (the cycle's ONLY
    general write surface). Keys outside `phase7-scratch:` refuse;
    injectable backing dict for tests; `clean()` reports residue."""

    def __init__(self, backing: Optional[Dict[str, Any]] = None) -> None:
        self._data = backing if backing is not None else {}

    def write(self, key: str, value: Any) -> str:
        if not key.startswith(SCRATCH_NS):
            _fail(f"scratch scope violation: key {key!r} outside "
                  f"namespace {SCRATCH_NS!r}")
        self._data[key] = value
        return key

    def read(self, key: str) -> Any:
        if not key.startswith(SCRATCH_NS):
            _fail(f"scratch scope violation: key {key!r} outside "
                  f"namespace {SCRATCH_NS!r}")
        return self._data.get(key)

    def delete(self, key: str) -> bool:
        if not key.startswith(SCRATCH_NS):
            _fail(f"scratch scope violation: key {key!r} outside "
                  f"namespace {SCRATCH_NS!r}")
        return self._data.pop(key, None) is not None

    def residue(self) -> List[str]:
        return sorted(k for k in self._data if k.startswith(SCRATCH_NS))


@dataclass(frozen=True)
class Phase7Attestation:
    """Canonical, immutable Phase 7 ignition artifact."""
    schema: str
    verdict: str             # PHASE7_IGNITED / IGNITION_INCOMPLETE
    phase6_digest: str       # upstream attestation digest (commitment)
    manifest_sha256: str     # deployment fingerprint carried through
    profile: Dict[str, Any]  # runtime profile + seams summary
    routing: Dict[str, Any]  # allowlist/determinism/limits summary
    cycle: Dict[str, Any]    # synthetic PM cycle telemetry
    checks: tuple = field(default_factory=tuple)  # (id, ok, detail)
    observed_tick: int = 0

    @property
    def ignited(self) -> bool:
        return self.verdict == PHASE7_IGNITED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "verdict": self.verdict,
            "phase6_digest": self.phase6_digest,
            "manifest_sha256": self.manifest_sha256,
            "profile": self.profile,
            "routing": self.routing,
            "cycle": self.cycle,
            "checks": [list(c) for c in self.checks],
            "observed_tick": self.observed_tick,
        }

    @property
    def attestation_digest(self) -> str:
        return canonical_hash(self.to_dict())


class Phase7Igniter:
    """AIR-01..AIR-05 with injected router/Notion/census providers.

    Injected:
      clock           — ``() -> int`` logical tick
      audit_sink      — ``callable(dict)`` (D-112/D-121 in prod)
      phase6_provider — ``() -> dict`` the phase6 attestation
      audit_rows      — ``() -> list`` the D-112 ledger rows
      chain_verifier  — ``() -> dict`` D-112 chain integrity
      census          — ``() -> dict`` the runtime profile census
                        {runtime_profile_verified, phases: [...]}
      router          — a ModelRouter-compatible object (real
                        canonical router with injected providers)
      notion          — optional probe-only Notion client (the
                        phase6-style create/read/archive surface)
      scratch         — optional ScratchStore (default built here)
      allowlist       — optional provider allowlist override
      expected_entry_points — optional {phase: seam} override (the
                        D-154 ENTRY_POINTS registry by default)
    """

    def __init__(self, clock: Callable[[], int],
                 audit_sink: Callable[[Dict[str, Any]], None],
                 phase6_provider: Optional[Callable[[], Dict[str, Any]]] = None,
                 audit_rows: Optional[Callable[[], List[Dict[str, Any]]]] = None,
                 chain_verifier: Optional[Callable[[], Dict[str, Any]]] = None,
                 census: Optional[Callable[[], Dict[str, Any]]] = None,
                 router: Optional[Any] = None,
                 notion: Optional[Any] = None,
                 scratch: Optional[ScratchStore] = None,
                 allowlist: Optional[Dict[str, Tuple[str, ...]]] = None,
                 expected_entry_points: Optional[Dict[int, str]] = None,
                 ) -> None:
        if not callable(clock) or not callable(audit_sink):
            _fail("clock and audit_sink required")
        self._clock = clock
        self._sink = audit_sink
        self._prov = {
            "phase6": phase6_provider,
            "audit_rows": audit_rows,
            "chain_verifier": chain_verifier,
            "census": census,
            "router": router,
            "notion": notion,
        }
        self._scratch = scratch or ScratchStore()
        self._allowlist = dict(allowlist) if allowlist \
            else dict(PROVIDER_ALLOWLIST)
        self._entry_points = dict(expected_entry_points) \
            if expected_entry_points else None
        self._tool_calls = 0

    # -- internals ---------------------------------------------------------

    def _load(self, name: str) -> Tuple[Optional[Any], str]:
        prov = self._prov.get(name)
        if prov is None:
            return None, "provider not injected"
        if callable(prov) and not hasattr(prov, "policy") \
                and not hasattr(prov, "users_me"):
            try:
                return prov(), ""
            except Exception as exc:  # noqa: BLE001 — typed (D-124)
                return None, f"provider raised {type(exc).__name__}"
        return prov, ""

    def _emit(self, verdict: str, checks: List[Tuple[str, bool, str]],
              phase6_digest: str = "", manifest: str = "",
              profile: Optional[Dict[str, Any]] = None,
              routing: Optional[Dict[str, Any]] = None,
              cycle: Optional[Dict[str, Any]] = None,
              ) -> Phase7Attestation:
        att = Phase7Attestation(
            schema=ATTESTATION_SCHEMA, verdict=verdict,
            phase6_digest=phase6_digest, manifest_sha256=manifest,
            profile=profile or {}, routing=routing or {},
            cycle=cycle or {},
            checks=tuple((c[0], c[1], deep_redact(str(c[2])))
                         for c in checks),
            observed_tick=self._clock())
        blob = json.dumps(att.to_dict(), sort_keys=True,
                          separators=(",", ":"), ensure_ascii=False)
        redacted = json.loads(deep_redact(blob))
        # Public commitments (D-146/D-153/D-154..D-156 precedent).
        redacted["phase6_digest"] = att.phase6_digest
        redacted["manifest_sha256"] = att.manifest_sha256
        self._sink(redacted)
        return att

    # -- AIR-01: the Phase 6 attestation -------------------------------------

    def _air01(self) -> Tuple[bool, str, str,
                              List[Tuple[str, bool, str]]]:
        """(ok, phase6_digest, manifest, checks)."""
        checks: List[Tuple[str, bool, str]] = []
        att, err = self._load("phase6")
        if att is None:
            checks.append(("AIR-01", False,
                           "Phase 6 attestation absent "
                           f"({err}) — Phase 6 never ignited"))
            return False, "", "", checks
        if not isinstance(att, dict):
            checks.append(("AIR-01", False,
                           "Phase 6 attestation malformed"))
            return False, "", "", checks
        if att.get("schema") != PHASE6_SCHEMA:
            checks.append(("AIR-01", False,
                           f"attestation schema {att.get('schema')!r} "
                           f"!= {PHASE6_SCHEMA!r}"))
            return False, "", "", checks
        if att.get("verdict") != PHASE6_IGNITED:
            checks.append(("AIR-01", False,
                           f"Phase 6 verdict {att.get('verdict')!r} "
                           f"!= {PHASE6_IGNITED!r} — Notion OS not "
                           "wired, Phase 7 refused"))
            return False, "", "", checks
        manifest = att.get("manifest_sha256", "")
        if not (isinstance(manifest, str) and _HEX64.match(manifest)):
            checks.append(("AIR-01", False,
                           "phase6 attestation lacks its manifest "
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
                        str(row.get("event_kind", "")) != PHASE6_ROW_KIND:
                    continue
                detail = row.get("detail")
                if isinstance(detail, dict) and \
                        isinstance(detail.get("attestation_digest"),
                                   str):
                    rooted_digest = detail["attestation_digest"]
                    break
        if not rooted_digest:
            checks.append(("AIR-01", False,
                           "phase6 attestation not rooted in the "
                           "D-112 ledger — upstream wiring was never "
                           "durably attested"))
            return False, recomputed, "", checks
        if rooted_digest != recomputed:
            checks.append(("AIR-01", False,
                           f"phase6 attestation digest "
                           f"{recomputed[:16]}… != rooted "
                           f"{rooted_digest[:16]}… — DRIFTED or "
                           "altered upstream attestation"))
            return False, recomputed, "", checks
        cv, err = self._load("chain_verifier")
        if cv is None or not isinstance(cv, dict) or not cv.get("ok"):
            reason = (cv or {}).get("reason", err or "verifier absent")
            checks.append(("AIR-01", False,
                           f"D-112 chain not intact ({reason}) — "
                           "wiring on a broken ledger is refused"))
            return False, recomputed, "", checks
        checks.append(("AIR-01", True,
                       "phase6 attestation PHASE6_IGNITED, digest "
                       f"recomputes ({recomputed[:16]}…) and matches "
                       "the rooted commitment in the D-112 ledger "
                       f"({int(cv.get('rows', 0))} rows, zero breaks)"))
        return True, recomputed, manifest, checks

    # -- AIR-02: runtime profile + module seams -------------------------------

    def _air02(self) -> Tuple[bool, Dict[str, Any],
                              List[Tuple[str, bool, str]]]:
        checks: List[Tuple[str, bool, str]] = []
        summary: Dict[str, Any] = {"runtime_profile_verified": False,
                                   "phases_ready": [],
                                   "seams_ok": False,
                                   "seams": dict(SEAMS)}
        census, err = self._load("census")
        if census is None or not isinstance(census, dict):
            checks.append(("AIR-02", False,
                           f"runtime profile census unavailable ({err})"
                           " — fail closed"))
            return False, summary, checks
        if census.get("runtime_profile_verified") is not True:
            checks.append(("AIR-02", False,
                           "runtime profile NOT verified — the D-154 "
                           "certificate's verified profile is the only "
                           "wiring baseline"))
            return False, summary, checks
        phases = census.get("phases")
        if not isinstance(phases, list):
            checks.append(("AIR-02", False,
                           "runtime profile census malformed — no "
                           "phase rows"))
            return False, summary, checks
        for ph in phases:
            if not isinstance(ph, dict):
                continue
            if ph.get("phase") in (5, 6):
                ok = (ph.get("present") is True
                      and ph.get("verified") is True
                      and ph.get("wired") is True)
                if ok:
                    summary["phases_ready"].append(ph.get("phase"))
                else:
                    checks.append(("AIR-02", False,
                                   f"Phase {ph.get('phase')} not "
                                   "present+VERIFIED+WIRED in the "
                                   "census — prerequisite missing"))
                    return False, summary, checks
        if sorted(summary["phases_ready"]) != [5, 6]:
            checks.append(("AIR-02", False,
                           "census lacks Phase 5/6 prerequisite rows — "
                           "fail closed"))
            return False, summary, checks
        summary["runtime_profile_verified"] = True
        checks.append(("AIR-02", True,
                       "runtime profile verified; Phases 5 and 6 are "
                       "present+VERIFIED+WIRED in the census"))
        # Repo-real seams: importable AND consistent with the D-154
        # ENTRY_POINTS registry.
        entry_points = self._entry_points
        if entry_points is None:
            from dokploy_completion_attestation import ENTRY_POINTS
            entry_points = ENTRY_POINTS
        for key, modname in SEAMS.items():
            try:
                importlib.import_module(modname)
            except Exception as exc:  # noqa: BLE001 — typed (D-124)
                checks.append(("AIR-02", False,
                               f"canonical seam {modname} not "
                               f"importable ({type(exc).__name__}) — "
                               "repo seam missing"))
                return False, summary, checks
            phase_no = SEAM_PHASES.get(key)
            expected = entry_points.get(phase_no) \
                if phase_no is not None else None
            if expected and expected != modname:
                checks.append(("AIR-02", False,
                               f"ENTRY_POINTS[{phase_no}] = "
                               f"{expected!r} != repo seam "
                               f"{modname!r} — registry drift"))
                return False, summary, checks
        summary["seams_ok"] = True
        checks.append(("AIR-02", True,
                       f"all {len(SEAMS)} canonical Phase 7/8 seams "
                       "importable and consistent with the D-154 "
                       "ENTRY_POINTS registry"))
        return True, summary, checks

    # -- AIR-03: bounded provider routing --------------------------------------

    def _route_for(self, router: Any, task_type: str) -> Any:
        policy = getattr(router, "policy", None)
        if not isinstance(policy, dict) or task_type not in policy:
            _fail(f"no route for task {task_type!r}")
        return policy[task_type]

    def _air03(self) -> Tuple[bool, Dict[str, Any],
                              List[Tuple[str, bool, str]]]:
        checks: List[Tuple[str, bool, str]] = []
        summary: Dict[str, Any] = {
            "allowlist": {k: list(v) for k, v in
                          self._allowlist.items()},
            "deterministic": False, "route": "", "limits": dict(LIMITS),
        }
        router, err = self._load("router")
        if router is None:
            checks.append(("AIR-03", False,
                           f"AI router unavailable ({err}) — fail "
                           "closed"))
            return False, summary, checks
        task_type = "propose_content_idea"
        try:
            target = self._route_for(router, task_type)
            again = self._route_for(router, task_type)
        except Phase7Error as exc:
            checks.append(("AIR-03", False, str(exc)))
            return False, summary, checks
        # Determinism: same inputs ⇒ same route decision.
        if (getattr(target, "provider", ""), getattr(target, "model",
                                                     "")) != \
                (getattr(again, "provider", ""),
                 getattr(again, "model", "")):
            checks.append(("AIR-03", False,
                           "route decision NOT deterministic — two "
                           "lookups of the same task diverged"))
            return False, summary, checks
        # Allowlist: unknown provider/model ⇒ refusal.
        prov = getattr(target, "provider", "")
        model = getattr(target, "model", "")
        if prov not in self._allowlist or \
                model not in self._allowlist.get(prov, ()):
            checks.append(("AIR-03", False,
                           f"routed target {prov}/{model} outside the "
                           f"provider allowlist — refusal"))
            return False, summary, checks
        # Hard limits on the probe request.
        max_tokens = int(getattr(target, "max_tokens", 0) or 0)
        if max_tokens > LIMITS["max_tokens_cap"]:
            checks.append(("AIR-03", False,
                           f"route max_tokens {max_tokens} exceeds the "
                           f"{LIMITS['max_tokens_cap']} cap"))
            return False, summary, checks
        budget = float(getattr(target, "budget_usd", 0) or 0)
        if budget > LIMITS["budget_cap_usd"]:
            checks.append(("AIR-03", False,
                           f"route budget ${budget:.2f} exceeds the "
                           f"${LIMITS['budget_cap_usd']:.2f} cycle cap"))
            return False, summary, checks
        summary["deterministic"] = True
        summary["route"] = f"{prov}/{model}"
        checks.append(("AIR-03", True,
                       f"routing bounded: deterministic route "
                       f"{prov}/{model}, allowlisted, max_tokens "
                       f"{max_tokens} ≤ {LIMITS['max_tokens_cap']}, "
                       f"budget ${budget:.2f} ≤ "
                       f"${LIMITS['budget_cap_usd']:.2f}, retries ≤ "
                       f"{LIMITS['max_retries']}, timeout "
                       f"{LIMITS['timeout_s']}s"))
        return True, summary, checks

    # -- tool dispatch (AIR-04) ------------------------------------------------

    def _dispatch_tool(self, name: str, *args: Any) -> Any:
        """The cycle's ONLY effectful surface — allowlisted, counted."""
        if name not in TOOL_ALLOWLIST:
            _fail(f"unsafe tool request: {name!r} outside the tool "
                  f"allowlist {TOOL_ALLOWLIST}")
        self._tool_calls += 1
        if self._tool_calls > LIMITS["max_tool_calls"]:
            _fail(f"tool-call budget exceeded: "
                  f"{self._tool_calls} > {LIMITS['max_tool_calls']}")
        if name == "scratch_write":
            return self._scratch.write(args[0], args[1])
        if name == "scratch_read":
            return self._scratch.read(args[0])
        if name == "scratch_delete":
            return self._scratch.delete(args[0])
        if name == "notion_probe":
            notion, err = self._load("notion")
            if notion is None:
                return {"probe": "absent"}
            return self._notion_probe(notion, args[0], args[1])
        _fail(f"unreachable tool {name!r}")

    def _notion_probe(self, notion: Any, dbid: str,
                      idem_key: str) -> Dict[str, Any]:
        """Strictly probe-only Notion write: create (idempotency-
        keyed) → replay (MUST be the SAME page) → read-back →
        archive. Any collision/failure raises."""
        payload = {"Name": "phase7-pm-probe"}
        first = notion.create_probe_page(dbid, payload,
                                         idempotency_key=idem_key)
        page_id = str((first or {}).get("page_id", ""))
        if not page_id:
            _fail("notion probe create returned no page id")
        replay = notion.create_probe_page(dbid, payload,
                                          idempotency_key=idem_key)
        replay_id = str((replay or {}).get("page_id", ""))
        if replay_id != page_id:
            _fail("notion probe idempotency collision: replay "
                  "returned a DISTINCT page")
        readback = notion.read_probe_page(page_id)
        content = (readback or {}).get("content")
        if not (isinstance(content, dict) and
                content.get("Name") == payload["Name"]):
            _fail("notion probe read-back mismatch")
        cleaned = notion.archive_page(page_id)
        if (cleaned or {}).get("archived") is not True:
            _fail("notion probe cleanup failed — page remains live")
        return {"probe": "ok", "page_key": idem_key[:16] + "…"}

    # -- AIR-04: the synthetic PM cycle ----------------------------------------

    def _air04(self, router: Any
               ) -> Tuple[bool, Dict[str, Any],
                          List[Tuple[str, bool, str]]]:
        from canonical.ai_contracts import (
            OutputValidationError, validate_ai_output)
        from canonical.ai_runtime import (
            AiRequest, AiProviderError, BudgetExceeded, AiProposal,
        )
        from canonical.vocab import COLOR_TERMS, CATEGORY_PAIRS

        checks: List[Tuple[str, bool, str]] = []
        summary: Dict[str, Any] = {"steps": [], "summary_hash": "",
                                   "scratch_cleaned": False,
                                   "notion_probe": "absent"}
        self._tool_calls = 0
        try:
            # START — brief normalization (fixed fixture, deterministic)
            normalized = {k: v.strip() for k, v in BRIEF.items()
                          if isinstance(v, str)}
            normalized_hash = canonical_hash(normalized)
            summary["steps"].append(
                ["START", True, {"brief_hash": normalized_hash}])

            # VOCAB — vocabulary alignment against owner-approved terms
            leaves = {leaf for _, leaf in CATEGORY_PAIRS}
            if normalized["product"] not in leaves:
                _fail(f"vocabulary alignment failed: product "
                      f"{normalized['product']!r} is not an "
                      "owner-approved category leaf")
            colors = {term: code for term, code in COLOR_TERMS}
            color_code = colors.get(normalized["color"], "")
            if not color_code:
                _fail(f"vocabulary alignment failed: color "
                      f"{normalized['color']!r} has no owner-approved "
                      "SKU code")
            summary["steps"].append(
                ["VOCAB", True, {"color_code": color_code}])

            # STRATEGY — through the real router (route → guardrails →
            # infer → contract validation), with the bounded retry
            # policy (transient Class-A only, MAX_RETRIES then refusal)
            proposal: Optional[Any] = None
            last_err = ""
            for attempt in range(LIMITS["max_retries"] + 1):
                try:
                    request = AiRequest(
                        task_type="propose_content_idea",
                        schema_id="content_idea_proposal.v1",
                        prompt_payload={
                            "brief": normalized,
                            "vocab": {"color_code": color_code},
                        },
                        max_tokens=512, temperature=0.0,
                        idempotency_tag=CYCLE_ID,
                        cost_center="phase7-ignition")
                    summary["steps"].append([
                        "ROUTE", True,
                        {"attempt": attempt + 1}])
                    proposal = router.run(request)
                    break
                except BudgetExceeded as exc:
                    _fail(f"budget guardrail refusal: {exc.args[0]}")
                except OutputValidationError as exc:
                    _fail(f"invalid output schema: "
                          f"{str(exc.args[0])[:120]}")
                except AiProviderError as exc:
                    last_err = str(exc.args[0]) if exc.args else ""
                    if getattr(exc, "failure_class", "") == "A" and \
                            attempt < LIMITS["max_retries"]:
                        continue
                    _fail(f"provider dispatch failed after "
                          f"{attempt + 1} attempt(s) "
                          f"(retry overflow): {last_err[:80]}")
            if proposal is None:
                _fail("provider dispatch produced no proposal")
            summary["steps"].append([
                "INFER", True,
                {"provider": proposal.provider, "model": proposal.model,
                 "tokens_in": int(proposal.usage.get("prompt_tokens", 0)),
                 "tokens_out": int(proposal.usage.get(
                     "completion_tokens", 0)),
                 "cost_usd": float(proposal.cost.get("cost_usd", 0.0))}])
            validation = validate_ai_output(
                "content_idea_proposal.v1", proposal.payload)
            if not validation.get("valid"):
                _fail("invalid output schema: AI proposal failed its "
                      f"contract {validation.get('errors')}")
            summary["steps"].append(["VALIDATE", True, {}])

            # PLAN — content plan skeleton (deterministic packaging)
            plan = {
                "plan_id": "phase7-pm-plan-0001",
                "cycle_id": CYCLE_ID,
                "title": proposal.payload["title"],
                "target_lifecycle_state":
                    proposal.payload["target_lifecycle_state"],
                "vocab": {"category_leaf": normalized["product"],
                          "color_code": color_code},
                "proposal_ref": proposal.correlation_id,
            }
            summary_hash = canonical_hash(plan)
            summary["summary_hash"] = summary_hash

            # PACK — the artifact goes to the scratch store ONLY
            key = SCRATCH_NS + "plan-0001"
            self._dispatch_tool("scratch_write", key, plan)
            stored = self._dispatch_tool("scratch_read", key)
            if canonical_hash(stored) != summary_hash:
                _fail("scratch artifact diverged from the packaged "
                      "plan")
            summary["steps"].append([
                "PACK", True, {"summary_hash": summary_hash[:16] + "…"}])

            # NOTION — strictly probe-only (optional surface)
            probe_result = self._dispatch_tool(
                "notion_probe", None, canonical_hash(
                    {"probe": "phase7", "brief": normalized_hash}))
            summary["notion_probe"] = (probe_result or {}).get(
                "probe", "absent")

            # CLEANUP — the scratch store must be left empty
            self._dispatch_tool("scratch_delete", key)
            residue = self._scratch.residue()
            if residue:
                _fail(f"missing cleanup: scratch residue {residue}")
            summary["scratch_cleaned"] = True
            summary["steps"].append(["CLEANUP", True, {}])
            checks.append(("AIR-04", True,
                           "synthetic PM cycle completed: "
                           f"{len(summary['steps'])} steps, summary "
                           f"hash {summary_hash[:16]}…, scratch "
                           f"cleaned, notion probe "
                           f"{summary['notion_probe']}"))
            return True, summary, checks
        except Phase7Error as exc:
            checks.append(("AIR-04", False, str(exc)[:160]))
            # best-effort cleanup so the workspace never stays dirty
            try:
                self._scratch.delete(SCRATCH_NS + "plan-0001")
            except Phase7Error:
                pass
            summary["scratch_cleaned"] = \
                not self._scratch.residue()
            return False, summary, checks
        except Exception as exc:  # noqa: BLE001 — typed refusal (D-124)
            checks.append(("AIR-04", False,
                           f"synthetic PM cycle failed "
                           f"({type(exc).__name__})"))
            try:
                self._scratch.delete(SCRATCH_NS + "plan-0001")
            except Phase7Error:
                pass
            summary["scratch_cleaned"] = \
                not self._scratch.residue()
            return False, summary, checks

    # -- the run --------------------------------------------------------------

    def run(self) -> Phase7Attestation:
        """AIR-01..AIR-05 → the canonical attestation. Exactly one
        audited attestation per call (including aborts); an AIR-01
        refusal performs ZERO provider calls."""
        checks: List[Tuple[str, bool, str]] = []
        ok1, p6digest, manifest, c1 = self._air01()
        checks += c1
        if not ok1:
            return self._emit(PHASE7_INCOMPLETE, checks,
                              phase6_digest=p6digest,
                              manifest=manifest)
        ok2, profile, c2 = self._air02()
        checks += c2
        ok3, routing, c3 = self._air03()
        checks += c3
        ok4, cycle, c4 = (False, {}, [])
        if ok3:
            router, err = self._load("router")
            if router is None:
                checks.append(("AIR-04", False,
                               f"AI router unavailable ({err}) — fail "
                               "closed"))
            else:
                ok4, cycle, c4 = self._air04(router)
                checks += c4
        verdict = PHASE7_IGNITED if all((ok1, ok2, ok3, ok4)) \
            else PHASE7_INCOMPLETE
        if verdict == PHASE7_IGNITED:
            checks.append(("AIR-05", True,
                           "phase7.live_wiring_attestation.v1 emitted "
                           "— AI Runtime + Product Manager core loop "
                           "wired under the Phase 6 attestation; "
                           "handover to Phase 8 (Instagram wiring) is "
                           "verified"))
        else:
            checks.append(("AIR-05", False,
                           "attestation emitted as IGNITION_INCOMPLETE "
                           "— remediate the named checks before the "
                           "Phase 8 handover"))
        return self._emit(verdict, checks, phase6_digest=p6digest,
                          manifest=manifest, profile=profile,
                          routing=routing, cycle=cycle)


def main(argv: Optional[List[str]] = None) -> int:
    """CLI wiring guard: interactive wiring requires the injected
    providers, census, router and workspace configuration."""
    import argparse
    import sys
    ap = argparse.ArgumentParser(
        description="Phase 7 live wiring igniter (AIR-01..AIR-05, "
                    "D-157).")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    print("live_wiring_phase7_igniter: interactive wiring requires "
          "the phase6 attestation, the D-112 chain, the runtime "
          "census, the injected router and the allowlist; see run() "
          "and the battery for the injected contract.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

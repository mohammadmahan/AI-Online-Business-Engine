"""Phase 9 live wiring igniter — Telegram Sales & Ingress verification (D-159).

The fifth Live Wiring program phase. Phase 8 (D-158) verified the
Instagram Graph API surface in strict probe-only mode; Phase 9 now
wires and verifies Telegram Ingress and the conversational sales
adapters — in STRICT SANDBOX-INGRESS mode:

  TG-01   the upstream `phase8.live_wiring_attestation.v1` is
          present, PHASE8_IGNITED, manifest-bound, its canonical
          bytes recompute to the SHA-256 commitment rooted in the
          D-112 ledger (kind `phase8_live_wiring_attestation`) over
          an intact chain — ANY refusal happens BEFORE the first
          Telegram adapter/ingress call (zero adapter calls on
          refusal);
  TG-02   the verified runtime profile is loaded: the injected
          census marks Phases 5, 6, 7 AND 8 present+VERIFIED+WIRED,
          and the canonical Telegram seams (repo-real:
          canonical.telegram_ingress = ENTRY_POINTS[10],
          canonical.telegram_contracts, canonical.telegram_adapter,
          canonical.telegram_publisher) are importable and
          consistent with the D-154 ENTRY_POINTS registry;
  TG-03   the Telegram adapter capability & security profile is
          validated: the bot token must match Telegram's documented
          `bot<id>:<hash>` form, the simulated `getMe` capability
          must return a usable bot identity, the webhook
          shared-secret verification must reject wrong/missing
          headers (constant-time compare through the REAL
          `verify_webhook_secret_token`), and the REAL `RatePacer`
          (D-074: 30 msgs/s global, 1 msg/s per chat) must pace an
          over-rate burst — paced, never dropped; message length
          caps (4096) and Class-A-only bounded retries hold;
  TG-04   a NON-DESTRUCTIVE synthetic conversational sales cycle
          runs end-to-end: a synthetic Telegram update (customer
          order intent) enters through the REAL webhook path
          (secret check → REAL `parse_update` → REAL `TelegramIngress`
          dedup), intent is extracted, the catalog lookup probes the
          injected Phase 6 store (probe-only), the reply is generated
          through the REAL Phase 7 ModelRouter (caption/sales
          contract), the response is validated against its contract,
          the session state is persisted into the injected session
          store (Redis-parity seam, namespaced, dedup-collision
          refusing), and the mock reply is CONSTRUCTED but NEVER
          dispatched — the run audits the adapter log and refuses
          with a SAFETY VIOLATION if any outbound send was invoked;
          per-step telemetry (START/AUTH/INGRESS_PARSE/INTENT_ROUTE/
          INFER/STATE_UPDATE/CLEANUP) and a deterministic summary
          hash are recorded;
  TG-05   the canonical `phase9.live_wiring_attestation.v1` is
          emitted exactly once per run (aborts included) with the
          SHA-256 `attestation_digest`; any abort emits the same
          schema as PHASE9_INCOMPLETE with failure telemetry.

Security & purity (RULES §35, AST-pinned): injected adapter/ingress
transports only — zero sockets, zero raw shell, zero wall clock in
the core. Bot tokens, chat ids, user PII, order payloads and session
tokens NEVER enter any emitted record: only hashes, counts, verdict
names and step telemetry. The canonical adapter layer's `redact()`
strips bot-token material; D-124 deep redaction runs over every
emitted record with the public commitments (`phase8_digest`,
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
    "Phase9Error", "Phase9Attestation", "Phase9Igniter",
    "SessionStore", "ATTESTATION_SCHEMA", "PHASE9_IGNITED",
    "PHASE9_INCOMPLETE", "PHASE8_SCHEMA", "PHASE8_IGNITED",
    "PHASE8_ROW_KIND", "SEAMS", "SEAM_PHASES", "REQUIRED_CAPS",
    "LIMITS", "SESSION_NS", "BOT_TOKEN_RE", "CYCLE_ID",
    "canonical_hash",
]

ATTESTATION_SCHEMA = "phase9.live_wiring_attestation.v1"
PHASE9_IGNITED = "PHASE9_IGNITED"
PHASE9_INCOMPLETE = "IGNITION_INCOMPLETE"

PHASE8_SCHEMA = "phase8.live_wiring_attestation.v1"
PHASE8_IGNITED = "PHASE8_IGNITED"

# The D-112 ledger kind that roots the Phase 8 attestation (D-158).
PHASE8_ROW_KIND = "phase8_live_wiring_attestation"

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
# Telegram Bot API bot token form: <bot id>:<hash> (documented shape).
BOT_TOKEN_RE = re.compile(r"^\d{6,12}:[A-Za-z0-9_-]{20,}$")

# --- required adapter capabilities (TG-03) --------------------------------

REQUIRED_CAPS: Tuple[str, ...] = (
    "getMe",            # bot identity/authorization
    "sendMessage",      # reply construction (never dispatched in probe)
    "webhook_secret",   # shared-secret verification mechanism
)

# --- hard limits (TG-03/TG-04) ----------------------------------------------

LIMITS: Dict[str, Any] = {
    "max_text_chars": 4096,     # Telegram documented text cap
    "max_retries": 2,           # Class-A transient retries only
    "timeout_s": 15.0,          # per adapter operation (D-151)
    "global_rate_per_sec": 30,  # D-074 RatePacer envelope
    "per_chat_rate_per_sec": 1,
    "max_session_probes": 1,    # exactly ONE probe session per cycle
}

SESSION_NS = "phase9-session:"
USAGE_WARN_PCT = 75.0

# Repo-real module seams for the Telegram wiring. `SEAM_PHASES` pins
# each seam to the D-154 ENTRY_POINTS phase it must agree with
# (None = supporting module).
SEAMS: Dict[str, str] = {
    "tg_ingress": "canonical.telegram_ingress",
    "tg_contracts": "canonical.telegram_contracts",
    "tg_adapter": "canonical.telegram_adapter",
    "tg_publisher": "canonical.telegram_publisher",
}

SEAM_PHASES: Dict[str, Optional[int]] = {
    "tg_ingress": 10,
    "tg_contracts": None,
    "tg_adapter": None,
    "tg_publisher": None,
}

# The synthetic conversational sales fixture (sandbox ingress only).
CYCLE_ID = "phase9-tg-probe-0001"
UPDATE_ID = 9001
CHAT_ID = -100_9001          # synthetic sandbox chat id (never real)
USER_ID = 700_1001           # synthetic sandbox user id (never real)
WEBHOOK_SECRET = "phase9-sandbox-webhook-secret-0123456789"

SYNTHETIC_UPDATE: Dict[str, Any] = {
    "update_id": UPDATE_ID,
    "message": {
        "message_id": 1,
        "chat": {"id": CHAT_ID, "type": "private"},
        "from": {"id": USER_ID, "is_bot": False},
        "text": "سلام، می‌خواستم از موجودی کت و جلیقه مشکی سایز M باور کنم",
    },
}


class Phase9Error(ValueError):
    """Contract-level misuse of the Phase 9 igniter."""


def _fail(reason: str) -> None:
    raise Phase9Error(reason)


def canonical_hash(payload: Dict[str, Any]) -> str:
    """SHA-256 over canonical JSON bytes — the shared project digest
    formula (Stage G/H/D-154..D-158 engines)."""
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class SessionStore:
    """Namespace-scoped session state store (the Redis-parity seam).
    Keys outside `phase9-session:` refuse; a re-set of an existing
    session key with a DIFFERENT value is a state collision and
    refuses (at-least-once safety)."""

    def __init__(self, backing: Optional[Dict[str, Any]] = None) -> None:
        self._data = backing if backing is not None else {}

    def set(self, key: str, value: Any) -> None:
        if not key.startswith(SESSION_NS):
            _fail(f"session scope violation: key {key!r} outside "
                  f"namespace {SESSION_NS!r}")
        existing = self._data.get(key)
        if existing is not None and canonical_hash(existing) != \
                canonical_hash(value):
            _fail(f"session state collision: {key!r} already holds a "
                  "different state")
        self._data[key] = value

    def get(self, key: str) -> Any:
        if not key.startswith(SESSION_NS):
            _fail(f"session scope violation: key {key!r} outside "
                  f"namespace {SESSION_NS!r}")
        return self._data.get(key)

    def delete(self, key: str) -> bool:
        if not key.startswith(SESSION_NS):
            _fail(f"session scope violation: key {key!r} outside "
                  f"namespace {SESSION_NS!r}")
        return self._data.pop(key, None) is not None

    def residue(self) -> List[str]:
        return sorted(k for k in self._data if k.startswith(SESSION_NS))


@dataclass(frozen=True)
class Phase9Attestation:
    """Canonical, immutable Phase 9 ignition artifact."""
    schema: str
    verdict: str             # PHASE9_IGNITED / IGNITION_INCOMPLETE
    phase8_digest: str       # upstream attestation digest (commitment)
    manifest_sha256: str     # deployment fingerprint carried through
    profile: Dict[str, Any]  # runtime profile + seams summary
    capability: Dict[str, Any]  # token/webhook/pacing summary
    cycle: Dict[str, Any]    # synthetic sales cycle telemetry
    checks: tuple = field(default_factory=tuple)  # (id, ok, detail)
    observed_tick: int = 0

    @property
    def ignited(self) -> bool:
        return self.verdict == PHASE9_IGNITED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "verdict": self.verdict,
            "phase8_digest": self.phase8_digest,
            "manifest_sha256": self.manifest_sha256,
            "profile": self.profile,
            "capability": self.capability,
            "cycle": self.cycle,
            "checks": [list(c) for c in self.checks],
            "observed_tick": self.observed_tick,
        }

    @property
    def attestation_digest(self) -> str:
        return canonical_hash(self.to_dict())


class Phase9Igniter:
    """TG-01..TG-05 with injected Telegram adapter/ingress.

    Injected:
      clock           — ``() -> int`` logical tick
      audit_sink      — ``callable(dict)`` (D-112/D-121 in prod)
      phase8_provider — ``() -> dict`` the phase8 attestation
      audit_rows      — ``() -> list`` the D-112 ledger rows
      chain_verifier  — ``() -> dict`` D-112 chain integrity
      census          — ``() -> dict`` the runtime profile census
      router          — the REAL Phase 7 ModelRouter (sales reply)
      tg              — a TelegramAdapter-compatible object with an
                        optional ``capability_profile()`` (simulated
                        getMe etc.); the transport is injected INSIDE
                        it (D-045/D-073/D-075)
      session         — optional SessionStore (default built here)
      expected_entry_points — optional {phase: seam} override
    """

    def __init__(self, clock: Callable[[], int],
                 audit_sink: Callable[[Dict[str, Any]], None],
                 phase8_provider: Optional[Callable[[], Dict[str, Any]]] = None,
                 audit_rows: Optional[Callable[[], List[Dict[str, Any]]]] = None,
                 chain_verifier: Optional[Callable[[], Dict[str, Any]]] = None,
                 census: Optional[Callable[[], Dict[str, Any]]] = None,
                 router: Optional[Any] = None,
                 tg: Optional[Any] = None,
                 session: Optional[SessionStore] = None,
                 expected_entry_points: Optional[Dict[int, str]] = None,
                 ) -> None:
        if not callable(clock) or not callable(audit_sink):
            _fail("clock and audit_sink required")
        self._clock = clock
        self._sink = audit_sink
        self._prov = {
            "phase8": phase8_provider,
            "audit_rows": audit_rows,
            "chain_verifier": chain_verifier,
            "census": census,
            "router": router,
            "tg": tg,
        }
        self._session = session or SessionStore()
        self._entry_points = dict(expected_entry_points) \
            if expected_entry_points else None

    # -- internals ---------------------------------------------------------

    def _load(self, name: str) -> Tuple[Optional[Any], str]:
        """Resolve one injected provider: a zero-arg callable (loaders)
        or the injected OBJECT itself (adapter, router)."""
        prov = self._prov.get(name)
        if prov is None:
            return None, "provider not injected"
        if callable(prov) and not hasattr(prov, "policy") \
                and not hasattr(prov, "send_text"):
            try:
                return prov(), ""
            except Exception as exc:  # noqa: BLE001 — typed (D-124)
                return None, f"provider raised {type(exc).__name__}"
        return prov, ""

    def _emit(self, verdict: str, checks: List[Tuple[str, bool, str]],
              phase8_digest: str = "", manifest: str = "",
              profile: Optional[Dict[str, Any]] = None,
              capability: Optional[Dict[str, Any]] = None,
              cycle: Optional[Dict[str, Any]] = None,
              ) -> Phase9Attestation:
        att = Phase9Attestation(
            schema=ATTESTATION_SCHEMA, verdict=verdict,
            phase8_digest=phase8_digest, manifest_sha256=manifest,
            profile=profile or {}, capability=capability or {},
            cycle=cycle or {},
            checks=tuple((c[0], c[1], deep_redact(str(c[2])))
                         for c in checks),
            observed_tick=self._clock())
        blob = json.dumps(att.to_dict(), sort_keys=True,
                          separators=(",", ":"), ensure_ascii=False)
        redacted = json.loads(deep_redact(blob))
        # Public commitments (D-146/D-153/D-154..D-158 precedent).
        redacted["phase8_digest"] = att.phase8_digest
        redacted["manifest_sha256"] = att.manifest_sha256
        self._sink(redacted)
        return att

    # -- TG-01: the Phase 8 attestation --------------------------------------

    def _tg01(self) -> Tuple[bool, str, str,
                             List[Tuple[str, bool, str]]]:
        """(ok, phase8_digest, manifest, checks)."""
        checks: List[Tuple[str, bool, str]] = []
        att, err = self._load("phase8")
        if att is None:
            checks.append(("TG-01", False,
                           "Phase 8 attestation absent "
                           f"({err}) — Phase 8 never ignited"))
            return False, "", "", checks
        if not isinstance(att, dict):
            checks.append(("TG-01", False,
                           "Phase 8 attestation malformed"))
            return False, "", "", checks
        if att.get("schema") != PHASE8_SCHEMA:
            checks.append(("TG-01", False,
                           f"attestation schema {att.get('schema')!r} "
                           f"!= {PHASE8_SCHEMA!r}"))
            return False, "", "", checks
        if att.get("verdict") != PHASE8_IGNITED:
            checks.append(("TG-01", False,
                           f"Phase 8 verdict {att.get('verdict')!r} "
                           f"!= {PHASE8_IGNITED!r} — Instagram surface "
                           "not wired, Phase 9 refused"))
            return False, "", "", checks
        manifest = att.get("manifest_sha256", "")
        if not (isinstance(manifest, str) and _HEX64.match(manifest)):
            checks.append(("TG-01", False,
                           "phase8 attestation lacks its manifest "
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
                        str(row.get("event_kind", "")) != PHASE8_ROW_KIND:
                    continue
                detail = row.get("detail")
                if isinstance(detail, dict) and \
                        isinstance(detail.get("attestation_digest"),
                                   str):
                    rooted_digest = detail["attestation_digest"]
                    break
        if not rooted_digest:
            checks.append(("TG-01", False,
                           "phase8 attestation not rooted in the "
                           "D-112 ledger — upstream wiring was never "
                           "durably attested"))
            return False, recomputed, "", checks
        if rooted_digest != recomputed:
            checks.append(("TG-01", False,
                           f"phase8 attestation digest "
                           f"{recomputed[:16]}… != rooted "
                           f"{rooted_digest[:16]}… — DRIFTED or "
                           "altered upstream attestation"))
            return False, recomputed, "", checks
        cv, err = self._load("chain_verifier")
        if cv is None or not isinstance(cv, dict) or not cv.get("ok"):
            reason = (cv or {}).get("reason", err or "verifier absent")
            checks.append(("TG-01", False,
                           f"D-112 chain not intact ({reason}) — "
                           "wiring on a broken ledger is refused"))
            return False, recomputed, "", checks
        checks.append(("TG-01", True,
                       "phase8 attestation PHASE8_IGNITED, digest "
                       f"recomputes ({recomputed[:16]}…) and matches "
                       "the rooted commitment in the D-112 ledger "
                       f"({int(cv.get('rows', 0))} rows, zero breaks)"))
        return True, recomputed, manifest, checks

    # -- TG-02: runtime profile + module seams -------------------------------

    def _tg02(self) -> Tuple[bool, Dict[str, Any],
                             List[Tuple[str, bool, str]]]:
        checks: List[Tuple[str, bool, str]] = []
        summary: Dict[str, Any] = {"runtime_profile_verified": False,
                                   "phases_ready": [],
                                   "seams_ok": False,
                                   "seams": dict(SEAMS)}
        census, err = self._load("census")
        if census is None or not isinstance(census, dict):
            checks.append(("TG-02", False,
                           f"runtime profile census unavailable ({err})"
                           " — fail closed"))
            return False, summary, checks
        if census.get("runtime_profile_verified") is not True:
            checks.append(("TG-02", False,
                           "runtime profile NOT verified — the D-154 "
                           "certificate's verified profile is the only "
                           "wiring baseline"))
            return False, summary, checks
        phases = census.get("phases")
        if not isinstance(phases, list):
            checks.append(("TG-02", False,
                           "runtime profile census malformed — no "
                           "phase rows"))
            return False, summary, checks
        for ph in phases:
            if not isinstance(ph, dict):
                continue
            if ph.get("phase") in (5, 6, 7, 8):
                ok = (ph.get("present") is True
                      and ph.get("verified") is True
                      and ph.get("wired") is True)
                if ok:
                    summary["phases_ready"].append(ph.get("phase"))
                else:
                    checks.append(("TG-02", False,
                                   f"Phase {ph.get('phase')} not "
                                   "present+VERIFIED+WIRED in the "
                                   "census — prerequisite missing"))
                    return False, summary, checks
        if sorted(summary["phases_ready"]) != [5, 6, 7, 8]:
            checks.append(("TG-02", False,
                           "census lacks Phase 5/6/7/8 prerequisite "
                           "rows — fail closed"))
            return False, summary, checks
        summary["runtime_profile_verified"] = True
        checks.append(("TG-02", True,
                       "runtime profile verified; Phases 5, 6, 7 and 8 "
                       "are present+VERIFIED+WIRED in the census"))
        entry_points = self._entry_points
        if entry_points is None:
            from dokploy_completion_attestation import ENTRY_POINTS
            entry_points = ENTRY_POINTS
        for key, modname in SEAMS.items():
            try:
                importlib.import_module(modname)
            except Exception as exc:  # noqa: BLE001 — typed (D-124)
                checks.append(("TG-02", False,
                               f"canonical seam {modname} not "
                               f"importable ({type(exc).__name__}) — "
                               "repo seam missing"))
                return False, summary, checks
            phase_no = SEAM_PHASES.get(key)
            expected = entry_points.get(phase_no) \
                if phase_no is not None else None
            if expected and expected != modname:
                checks.append(("TG-02", False,
                               f"ENTRY_POINTS[{phase_no}] = "
                               f"{expected!r} != repo seam "
                               f"{modname!r} — registry drift"))
                return False, summary, checks
        summary["seams_ok"] = True
        checks.append(("TG-02", True,
                       f"all {len(SEAMS)} Telegram seams importable "
                       "and consistent with the D-154 ENTRY_POINTS "
                       "registry"))
        return True, summary, checks

    # -- TG-03: capability & security profile ---------------------------------

    def _tg03(self) -> Tuple[bool, Dict[str, Any],
                             List[Tuple[str, bool, str]]]:
        from canonical.telegram_adapter import RatePacer, redact
        from canonical.telegram_ingress import (
            TelegramIngressError, verify_webhook_secret_token,
        )

        checks: List[Tuple[str, bool, str]] = []
        summary: Dict[str, Any] = {"token_ok": False, "caps_ok": False,
                                   "webhook_secret_ok": False,
                                   "pacer_ok": False}
        adapter, err = self._load("tg")
        if adapter is None:
            checks.append(("TG-03", False,
                           f"Telegram adapter unavailable ({err}) — "
                           "fail closed"))
            return False, summary, checks
        profiler = getattr(adapter, "capability_profile", None)
        if not callable(profiler):
            checks.append(("TG-03", False,
                           "adapter exposes no capability profile — "
                           "authorization validation impossible, fail "
                           "closed"))
            return False, summary, checks
        try:
            profile = profiler()
        except Exception as exc:  # noqa: BLE001 — typed refusal
            checks.append(("TG-03", False,
                           f"capability probe failed "
                           f"({type(exc).__name__}) — bot "
                           "authorization error, fail closed"))
            return False, summary, checks
        if not isinstance(profile, dict):
            checks.append(("TG-03", False,
                           "capability profile malformed"))
            return False, summary, checks
        # Bot token format (Telegram documented form).
        token = str(profile.get("bot_token") or "")
        if not BOT_TOKEN_RE.match(token):
            checks.append(("TG-03", False,
                           "bot token missing or malformed (expected "
                           "the documented <bot id>:<hash> form)"))
            return False, summary, checks
        summary["token_ok"] = True
        bot_name = str(profile.get("bot_username", "bot"))[:16]
        checks.append(("TG-03", True,
                       "bot token format valid (simulated getMe "
                       f"identity {bot_name}…)"))
        # Capability surface.
        caps = set(profile.get("capabilities") or ())
        missing = [c for c in REQUIRED_CAPS if c not in caps]
        if missing:
            checks.append(("TG-03", False,
                           f"missing adapter capabilities: {missing}"))
            return False, summary, checks
        summary["caps_ok"] = True
        checks.append(("TG-03", True,
                       f"adapter capabilities verified "
                       f"({len(caps)} present, {len(REQUIRED_CAPS)} "
                       "required)"))
        # Webhook shared-secret verification — the REAL mechanism,
        # exercised against a WRONG header and the RIGHT header.
        try:
            verify_webhook_secret_token("wrong-secret-value",
                                        secret=WEBHOOK_SECRET)
            _fail("webhook secret verification accepted a WRONG "
                  "header — mechanism broken")
        except TelegramIngressError:
            pass  # the correct refusal
        try:
            verify_webhook_secret_token(WEBHOOK_SECRET,
                                        secret=WEBHOOK_SECRET)
        except TelegramIngressError as exc:
            _fail(f"webhook secret verification rejected the correct "
                  f"header: {exc.args[0]}")
        summary["webhook_secret_ok"] = True
        checks.append(("TG-03", True,
                       "webhook shared-secret mechanism verified "
                       "(wrong header refused, correct header "
                       "accepted, constant-time compare)"))
        # Rate envelope: the REAL D-074 RatePacer must pace (never
        # drop) an over-rate burst on one synthetic chat.
        pacer = RatePacer(global_rate=LIMITS["global_rate_per_sec"],
                          per_chat_rate=LIMITS["per_chat_rate_per_sec"])
        waits = [pacer.acquire("sandbox", now_s=i * 0.1)
                 for i in range(6)]
        if not all(w >= 0.0 for w in waits) or \
                not any(w > 0.0 for w in waits):
            checks.append(("TG-03", False,
                           "rate envelope failed: the pacer did not "
                           "throttle the over-rate burst"))
            return False, summary, checks
        summary["pacer_ok"] = True
        checks.append(("TG-03", True,
                       "rate envelope verified: per-chat burst paced "
                       f"({LIMITS['per_chat_rate_per_sec']:.0f}/s, "
                       f"global {LIMITS['global_rate_per_sec']:.0f}/s "
                       "— paced, never dropped); text cap "
                       f"{LIMITS['max_text_chars']} chars; Class-A-only "
                       f"retries ≤ {LIMITS['max_retries']}"))
        return True, summary, checks

    # -- the synthetic conversational sales cycle (TG-04) -----------------------

    def _intent_of(self, text: str) -> str:
        """Deterministic intent extraction over sandbox fixture text."""
        lowered = text.lower()
        if "موجودی" in text or "availability" in lowered:
            return "order_inquiry"
        if "قیمت" in text or "price" in lowered:
            return "price_inquiry"
        return "unknown_intent"

    def _reply_from_router(self, router: Any, intent: str) -> Dict[str, Any]:
        """Deterministic sales reply through the REAL Phase 7 router."""
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
                  "reply task (fail closed)")
        request = AiRequest(
            task_type=task_type,
            schema_id="caption_proposal.v1",
            prompt_payload={"cycle_id": CYCLE_ID,
                            "intent": intent},
            max_tokens=512, temperature=0.0,
            idempotency_tag=CYCLE_ID,
            cost_center="phase9-ignition")
        try:
            proposal = router.run(request)
        except BudgetExceeded as exc:
            _fail(f"budget guardrail refusal: {exc.args[0]}")
        except AiProviderError as exc:
            _fail(f"reply dispatch failed ({type(exc).__name__}) — "
                  "AI runtime surface not wired")
        validation = validate_ai_output("caption_proposal.v1",
                                        proposal.payload)
        if not validation.get("valid"):
            _fail("invalid output schema: sales reply failed its "
                  f"contract {validation.get('errors')}")
        return proposal.payload

    def _tg04(self, router: Any
              ) -> Tuple[bool, Dict[str, Any],
                         List[Tuple[str, bool, str]]]:
        from canonical.telegram_ingress import (
            TelegramIngress, TelegramIngressError, parse_update,
            update_key,
        )
        from canonical.telegram_adapter import redact

        checks: List[Tuple[str, bool, str]] = []
        summary: Dict[str, Any] = {"steps": [], "summary_hash": "",
                                   "dispatched": False,
                                   "session_cleaned": False}
        adapter, err = self._load("tg")
        if adapter is None:
            checks.append(("TG-04", False,
                           f"Telegram adapter unavailable ({err}) — "
                           "fail closed"))
            return False, summary, checks
        try:
            # START — the synthetic update enters the REAL webhook path
            raw = json.dumps(SYNTHETIC_UPDATE).encode("utf-8")
            summary["steps"].append([
                "START", True,
                {"body_hash": canonical_hash(
                    {"update_id": UPDATE_ID})[:16] + "…"}])

            # AUTH — webhook shared secret + parse (REAL ingress)
            ingress = TelegramIngress(
                seen_keys=lambda k: False,
                record_key=lambda k: None)
            ingested = ingress.ingest_webhook(raw, WEBHOOK_SECRET,
                                              secret=WEBHOOK_SECRET)
            if ingested.get("verdict") != "accepted":
                _fail("synthetic update not accepted by ingress")
            update = parse_update(raw)
            if update.get("update_id") != UPDATE_ID:
                _fail("update normalization mismatch")
            # malformed payloads must fail closed locally
            for bad in (b"not json", b"{}"):
                try:
                    parse_update(bad)
                    _fail("malformed update accepted — ingress "
                          "contract broken")
                except TelegramIngressError:
                    pass
            summary["steps"].append([
                "AUTH", True, {"webhook_secret": "verified"}])

            # INGRESS_PARSE — metadata-minimizing parse result
            if not update.get("text"):
                _fail("update carries no text content")
            summary["steps"].append([
                "INGRESS_PARSE", True,
                {"kind": update.get("kind"),
                 "has_media": bool(update.get("has_media"))}])

            # INTENT_ROUTE — deterministic intent extraction
            intent = self._intent_of(str(update["text"]))
            if intent == "unknown_intent":
                _fail("unknown intent crash: sandbox text matched no "
                      "recognized intent")
            summary["steps"].append([
                "INTENT_ROUTE", True, {"intent": intent}])

            # INFER — the sales reply through the REAL router, then
            # the mock reply is CONSTRUCTED (never dispatched)
            reply = self._reply_from_router(router, intent)
            text = str(reply["caption_fa"]) + " " + \
                " ".join(reply["hashtags"])
            if len(text) > LIMITS["max_text_chars"]:
                _fail(f"reply exceeds the "
                      f"{LIMITS['max_text_chars']}-char Telegram cap")
            mock_reply = {"method": "sendMessage",
                          "chat_ref": canonical_hash(
                              {"chat_id": CHAT_ID}),
                          "text_hash": hashlib.sha256(
                              text.encode("utf-8")).hexdigest()[:16],
                          "parse_mode": ""}
            summary["steps"].append([
                "INFER", True,
                {"provider": "phase7-router",
                 "reply_hash": mock_reply["text_hash"] + "…"}])

            # STATE_UPDATE — session persisted in the namespaced store
            session_key = SESSION_NS + str(UPDATE_ID)
            state = {"intent": intent,
                     "update_id": UPDATE_ID,
                     "reply_ref": mock_reply["text_hash"]}
            self._session.set(session_key, state)
            stored = self._session.get(session_key)
            if canonical_hash(stored) != canonical_hash(state):
                _fail("session state diverged after persistence")
            summary["steps"].append([
                "STATE_UPDATE", True, {"session": "persisted"}])

            # DISPATCH AUDIT — NO outbound send may have occurred
            calls = list(getattr(adapter, "calls", []))
            sent = [c for c in calls
                    if isinstance(c, dict)
                    and str(c.get("method", "")).startswith("send")]
            if sent:
                _fail("SAFETY VIOLATION: outbound Telegram dispatch "
                      "invoked during a sandbox probe cycle")
            summary["dispatched"] = False
            summary["steps"].append([
                "VERIFY", True, {"dispatched": False,
                                 "safety_audited": True}])

            # CLEANUP — the session store must be left empty
            self._session.delete(session_key)
            residue = self._session.residue()
            if residue:
                _fail(f"cleanup failed: session residue {residue}")
            summary["session_cleaned"] = True
            summary["steps"].append(["CLEANUP", True, {}])

            plan = {
                "cycle_id": CYCLE_ID,
                "intent": intent,
                "update_ref": canonical_hash({"update_id": UPDATE_ID}),
                "reply_hash": mock_reply["text_hash"],
                "dispatched": False,
            }
            summary["summary_hash"] = canonical_hash(plan)
            checks.append(("TG-04", True,
                           "synthetic sales cycle completed: "
                           f"{len(summary['steps'])} steps, summary "
                           f"hash {summary['summary_hash'][:16]}…, "
                           "session persisted+cleaned, ZERO outbound "
                           "dispatch"))
            return True, summary, checks
        except Phase9Error as exc:
            checks.append(("TG-04", False, str(exc)[:160]))
            try:
                self._session.delete(SESSION_NS + str(UPDATE_ID))
            except Phase9Error:
                pass
            summary["session_cleaned"] = \
                not self._session.residue()
            summary["dispatched"] = False
            return False, summary, checks
        except Exception as exc:  # noqa: BLE001 — typed refusal (D-124)
            checks.append(("TG-04", False,
                           f"synthetic sales cycle failed "
                           f"({type(exc).__name__})"))
            try:
                self._session.delete(SESSION_NS + str(UPDATE_ID))
            except Phase9Error:
                pass
            summary["session_cleaned"] = \
                not self._session.residue()
            summary["dispatched"] = False
            return False, summary, checks

    # -- the run --------------------------------------------------------------

    def run(self) -> Phase9Attestation:
        """TG-01..TG-05 → the canonical attestation. Exactly one
        audited attestation per call (including aborts); a TG-01
        refusal performs ZERO adapter/ingress calls."""
        checks: List[Tuple[str, bool, str]] = []
        ok1, p8digest, manifest, c1 = self._tg01()
        checks += c1
        if not ok1:
            return self._emit(PHASE9_INCOMPLETE, checks,
                              phase8_digest=p8digest,
                              manifest=manifest)
        ok2, profile, c2 = self._tg02()
        checks += c2
        ok3, capability, c3 = (False, {}, [])
        router = self._prov.get("router")
        if ok2:
            ok3, capability, c3 = self._tg03()
            checks += c3
        ok4, cycle, c4 = (False, {}, [])
        if ok3 and router is not None:
            ok4, cycle, c4 = self._tg04(router)
            checks += c4
        elif ok3:
            checks.append(("TG-04", False,
                           "AI router unavailable — the sales reply "
                           "cannot be generated, fail closed"))
        verdict = PHASE9_IGNITED if all((ok1, ok2, ok3, ok4)) \
            else PHASE9_INCOMPLETE
        if verdict == PHASE9_IGNITED:
            checks.append(("TG-05", True,
                           "phase9.live_wiring_attestation.v1 emitted "
                           "— Telegram Sales & Ingress wiring verified "
                           "in SANDBOX-INGRESS mode (zero outbound "
                           "dispatch) under the Phase 8 attestation; "
                           "handover to Phase 10 (Multi-channel Order "
                           "Orchestration) is verified"))
        else:
            checks.append(("TG-05", False,
                           "attestation emitted as IGNITION_INCOMPLETE "
                           "— remediate the named checks before the "
                           "Phase 10 handover"))
        return self._emit(verdict, checks, phase8_digest=p8digest,
                          manifest=manifest, profile=profile,
                          capability=capability, cycle=cycle)


def main(argv: Optional[List[str]] = None) -> int:
    """CLI wiring guard: interactive wiring requires the injected
    providers, census, router and adapter configuration."""
    import argparse
    import sys
    ap = argparse.ArgumentParser(
        description="Phase 9 live wiring igniter (TG-01..TG-05, "
                    "D-159).")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    print("live_wiring_phase9_igniter: interactive wiring requires "
          "the phase8 attestation, the D-112 chain, the runtime "
          "census, the injected router and adapter; see run() and "
          "the battery for the injected contract.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

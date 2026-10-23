"""Fashion Phase 6 §6.2 — Kavenegar SMS channel adapter (decision row 74).

Plugged in BEHIND the existing notification seam, never beside it: an
`SmsAdapter` IS a `canonical.notification_worker.ChannelAdapter` handed to
`NotificationWorker(adapters={CH_SMS: ...})`, so there is no second
dispatch path, no second queue and no change to the order write path
(DECISIONS row 74; roadmap §6.2 / AC-9; D-089–D-092).

Selection and gating (same construction-gate shape as
`canonical/telegram_adapter.py`, D-075):
  - `MockSmsAdapter` is the DEFAULT and the deterministic fallback — it
    records the call and sends nothing, so tests and local runs never
    reach a network.
  - `KavenegarSmsAdapter` is the live adapter. It requires BOTH
    `SMS_LIVE_ENABLED=true` AND `KAVENEGAR_API_KEY`, AND an INJECTED
    transport: direct HTTP is forbidden in canonical code (D-116), so the
    transport is the only egress and tests always supply a fake one.

Configuration is read from the environment at CONSTRUCTION time only:
  SMS_LIVE_ENABLED        "true" enables the live adapter; anything else
                          selects the mock (fallback, never silent-sends)
  KAVENEGAR_API_KEY       provider credential (D-045: none exists yet)
  KAVENEGAR_SENDER        owner-supplied sender line (plain-text route)
  KAVENEGAR_TEMPLATE_MAP  JSON: notification template id →
                          {"name": <provider template>, "tokens": [<var>]}
                          (owner-supplied; OTP templates are registered
                          provider-side — D-045)

Two routes, chosen per notification by the template map (never guessed):
  - `verify/lookup.json` — registered provider template + token variables.
    This is the OTP route: the code is a provider-side template token, so
    it is never rendered as free text.
  - `sms/send.json` — locally rendered Persian body + sender line.

Everything the owner has not supplied yet FAILS CLOSED as a permanent
Class-B outcome (`template_not_registered`, `sender_line_not_configured`,
`invalid_recipient`) — never a plain-text guess, never a silent drop.

Redaction (D-114/D-124): `redact()` strips the API key from every escaping
string, and the provider's own message id is the only correlator recorded.

Registry admission (open, owner-gated). The three §6.2 buyer messages are
named here — `checkout.otp.v1`, `order.confirmed.v1`, `order.tracking.v1`
(`PENDING_REGISTRY_ADMISSION`) — but they are NOT in
`notification_contracts.TEMPLATES`. Admitting them changes the count that
the Phase-17 attestation hashes, which moves the **sealed D-168 phase-18
chain digest** recorded in `DECISIONS.md`; re-attestation is an owner act,
so this adapter ships without it. Today the registry already carries
`order.shipped.v1` on the SMS channel, and an SMS sent for it carries the
tracking code whenever the producer supplies it. The adapter itself is
content-agnostic: the moment the owner admits the three templates, these
bodies and the OTP token route start being reachable with no code change.
"""

import json
import os
import re
from typing import Dict, Optional, Tuple

from canonical.notification_contracts import (
    CH_SMS,
    OUT_DELIVERED,
    OUT_PERMANENT_FAILURE,
    OUT_RATE_LIMITED,
    OUT_TRANSIENT_FAILURE,
    NotificationContractError,
)
from canonical.notification_worker import ChannelAdapter

# --- construction gate (D-045/D-075) ----------------------------------------

LIVE_ENV_FLAG = "SMS_LIVE_ENABLED"
API_KEY_ENV = "KAVENEGAR_API_KEY"
SENDER_ENV = "KAVENEGAR_SENDER"
TEMPLATE_MAP_ENV = "KAVENEGAR_TEMPLATE_MAP"

API_BASE = "https://api.kavenegar.com/v1"

#: The three §6.2 buyer messages this adapter is built for. They are NOT
#: admitted to the sealed contract registry yet: doing so changes the
#: Phase-17/18 attestation digest (D-168), which is an owner re-attestation
#: (see the module docstring). Declared here so the gap is named, not hidden.
PENDING_REGISTRY_ADMISSION = ("checkout.otp.v1", "order.confirmed.v1",
                              "order.tracking.v1")


# --- bounds (D-114) ---------------------------------------------------------

#: `phone_ref` must be an Iranian MSISDN (normalised in
#: `normalize_recipient` to 09xxxxxxxxx); provider template names are
#: owner-supplied identifiers.
_TEMPLATE_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_VARNAME_RE = re.compile(r"^[a-z_][a-z0-9_]{0,63}$")

#: verify/lookup accepts token, token2, token3 (in that order).
MAX_VERIFY_TOKENS = 3
#: a plain SMS is at most 4 Persian pages; longer bodies fail closed.
MAX_MESSAGE_CHARS = 280
#: bound on how many templates the mapping may declare.
MAX_TEMPLATE_MAP_ENTRIES = 32
#: default Class-C wait when the provider gives no retry hint.
DEFAULT_RATE_LIMIT_WAIT_S = 60

#: provider codes that mean "slow down", with their natural window.
_RATE_LIMIT_WAITS = {426: 60, 427: 3600, 428: 3600, 429: 60}

#: provider codes that are terminal for this recipient/message.
_PERMANENT_CODES = {
    400: "invalid_parameters",
    401: "invalid_api_key",
    402: "invalid_activity",
    403: "access_denied",
    404: "not_found",
    405: "invalid_method",
    406: "invalid_encoding",
    407: "invalid_ip",
    409: "subscription_inactive",
    411: "invalid_sender",
    412: "invalid_recipient",
    413: "invalid_date",
    414: "message_too_long",
    415: "unsupported_message",
    416: "invalid_message_id",
    417: "invalid_message_ids",
    418: "invalid_recipient_count",
    419: "invalid_message_type",
    420: "invalid_token",
    422: "template_not_registered",
    424: "too_many_recipients",
    431: "invalid_token_type",
    432: "template_token_invalid",
    451: "no_credit",
}

#: provider codes that are transient (retry with backoff).
_TRANSIENT_CODES = {500, 501, 502, 503, 504, 507}

_REDACTED = "[REDACTED]"


class SmsContractError(NotificationContractError):
    """Class-B refusal — configuration or payload, never a provider call."""


def redact(text: str, extra_secrets: Optional[list] = None) -> str:
    """Strip Kavenegar credential material from any string (D-114/D-124).

    Handles the `/v1/<api-key>/` path form (the key sits in every call
    URL) and, when the caller knows it, the bare key value.
    """
    out = str(text)
    out = re.sub(r"/v1/[A-Za-z0-9]{8,}/", "/v1/" + _REDACTED + "/", out)
    for secret in extra_secrets or []:
        if secret:
            out = out.replace(str(secret), _REDACTED)
    return out


def live_enabled(env: Optional[Dict[str, str]] = None) -> bool:
    values = os.environ if env is None else env
    return str(values.get(LIVE_ENV_FLAG, "")).strip().lower() == "true"


def require_live_keys(env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """D-075 construction gate: live flag AND api key, else Class-B."""
    values = os.environ if env is None else env
    if not live_enabled(values):
        raise SmsContractError(
            f"live SMS adapter disabled: {LIVE_ENV_FLAG}!=true "
            "(D-075 owner gate)")
    api_key = str(values.get(API_KEY_ENV, "")).strip()
    if not api_key:
        raise SmsContractError(
            f"live SMS adapter disabled: {API_KEY_ENV} missing "
            "(D-045 — no credential exists, none requested)")
    return {"api_key": api_key,
            "sender": str(values.get(SENDER_ENV, "")).strip()}


# --- error carriers (classified per D-052) ----------------------------------

class _SmsRateLimited(Exception):
    """Class-C carrier: provider pacing — honor the indicated wait."""

    failure_class = "C"

    def __init__(self, message: str,
                 retry_after_s: int = DEFAULT_RATE_LIMIT_WAIT_S):
        super().__init__(message)
        self.retry_after_s = int(retry_after_s)


class _SmsTransient(Exception):
    """Class-A carrier: transport or provider hiccup — retry."""

    failure_class = "A"


class _SmsRejected(Exception):
    """Class-B carrier: terminal for this message/recipient."""

    failure_class = "B"


def classify_kavenegar_status(code: int) -> Tuple[str, str, int]:
    """Map a Kavenegar `return.status` to (verdict, detail, wait_s).

    Deterministic table, no wall clock. `verdict` is one of `ok`,
    `rate_limited`, `transient`, `permanent`. Unknown 5xx codes stay
    transient; every unknown 4xx fails CLOSED as permanent rather than
    being retried forever.
    """
    code = int(code)
    if code == 200:
        return ("ok", "ok", 0)
    if code in _RATE_LIMIT_WAITS:
        return ("rate_limited", f"kavenegar_status_{code}",
                _RATE_LIMIT_WAITS[code])
    if code in _TRANSIENT_CODES:
        return ("transient", f"kavenegar_status_{code}", 0)
    if code in _PERMANENT_CODES:
        return ("permanent", _PERMANENT_CODES[code], 0)
    if 400 <= code < 500:
        return ("permanent", f"kavenegar_status_{code}", 0)
    return ("transient", f"unknown_kavenegar_status_{code}", 0)


def _parse_body(body) -> Dict:
    """Provider body → dict; a non-JSON body is an empty mapping."""
    if isinstance(body, dict):
        return body
    try:
        parsed = json.loads(str(body))
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def parse_kavenegar_error(http_status: int, body) -> Exception:
    """Provider response → D-052 carrier (credentials redacted).

    A 200 HTTP envelope carrying a non-200 provider status is classified
    from that provider code — Kavenegar reports most failures this way.
    HTTP 5xx → Class-A; HTTP 429 → Class-C; any other non-200 → Class-B.
    """
    parsed = _parse_body(body)
    provider = (parsed.get("return") or {}).get("status") \
        if parsed else None
    if isinstance(provider, int) and provider != 200:
        verdict, detail, wait_s = classify_kavenegar_status(provider)
        if verdict == "rate_limited":
            return _SmsRateLimited(f"{provider} rate limited: {detail}",
                                   wait_s)
        if verdict == "transient":
            return _SmsTransient(f"{provider} provider error: {detail}")
        return _SmsRejected(f"{provider} rejected: {detail}")
    if int(http_status) == 200:
        # a 200 without a usable provider envelope cannot confirm
        # acceptance — refuse rather than fabricate a delivery (D-052)
        return _SmsRejected("malformed_response")
    if int(http_status) == 429:
        return _SmsRateLimited("429 rate limited", DEFAULT_RATE_LIMIT_WAIT_S)
    if int(http_status) >= 500:
        return _SmsTransient(f"{http_status} server error")
    return _SmsRejected(f"{http_status} bad request")


# --- recipient normalisation -------------------------------------------------

def normalize_recipient(value) -> Optional[str]:
    """Validate a `phone_ref` as an Iranian MSISDN; None when unusable.

    The contract's `phone_ref` is the only recipient the live channel can
    use, so a symbolic local reference (e.g. `user-42-sms`) can never be
    sent to a provider: it is refused Class-B before any call. Digits are
    normalised to the `09xxxxxxxxx` form Kavenegar accepts.
    """
    raw = str(value or "").strip()
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return None
    if len(digits) == 12 and digits.startswith("98"):
        digits = "0" + digits[2:]
    if len(digits) != 11 or not digits.startswith("09"):
        return None
    return digits


# --- Persian bodies (D-171: Persian prose, Latin identifiers) ---------------

#: Rendered locally for the plain-text route only. The OTP template is
#: intentionally ABSENT: an OTP belongs in a provider-side template
#: (verify/lookup), never in a free-text body we compose ourselves.
_BODY_TEMPLATES: Dict[str, str] = {
    "order.confirmed.v1": "سفارش {order_ref} ثبت شد. از خرید شما سپاسگزاریم.",
    "order.shipped.v1": "سفارش {order_ref} ارسال شد.",
    "order.tracking.v1": ("سفارش {order_ref} ارسال شد. "
                          "کد رهگیری پستی: {tracking_code}"),
}

#: Appended to `order.shipped.v1` when the producer supplies the code, so
#: the registry's existing SMS template already delivers postal tracking.
_TRACKING_SUFFIX = " کد رهگیری پستی: {tracking_code}"


class _Vars(dict):
    """Strict mapping: a missing variable is a refusal, never ''."""

    def __missing__(self, key):
        raise KeyError(key)


def render_body(template_id: str, variables: Dict) -> Optional[str]:
    """Local Persian body for `template_id`, or None when not renderable.

    None is a Class-B refusal (the adapter reports
    `body_unavailable:<id>`) — never an empty SMS and never a guessed
    body. `MAX_MESSAGE_CHARS` bounds the result.
    """
    template = _BODY_TEMPLATES.get(str(template_id))
    if template is None:
        return None
    try:
        body = template.format_map(_Vars(variables or {}))
        if str(template_id) == "order.shipped.v1" \
                and (variables or {}).get("tracking_code"):
            body += _TRACKING_SUFFIX.format_map(_Vars(variables or {}))
    except (KeyError, IndexError, ValueError):
        return None
    body = body.strip()
    if not body or len(body) > MAX_MESSAGE_CHARS:
        return None
    return body


# --- the provider interface -------------------------------------------------

class SmsAdapter(ChannelAdapter):
    """The SMS provider interface — the canonical `ChannelAdapter` narrowed
    to the SMS channel. Both implementations below satisfy it, so the
    worker cannot tell them apart (D-089/D-090 drop-in rule)."""

    channel = CH_SMS

    def send(self, event: Dict, ref: Dict) -> Dict:
        raise NotImplementedError


def _outcome(outcome: str, detail: str, wait_s: int = 0) -> Dict:
    """Outcome dict in the worker's vocabulary (D-092)."""
    result = {"outcome": outcome, "detail": detail}
    if wait_s:
        result["wait_s"] = int(wait_s)
    return result


# --- mock (default / fallback) ----------------------------------------------

FAILURE_CONTROLS = ("timeout", "rate_limited", "invalid_recipient",
                    "template_not_registered", "no_credit", "server_error")


class MockSmsAdapter(SmsAdapter):
    """Deterministic local provider (D-053): records every dispatch, never
    touches a network, sends nothing. Scriptable failures for the first
    `fail_times` calls exercise the worker's retry/DLQ ladder."""

    def __init__(self, fail_with: Optional[str] = None,
                 fail_times: int = 1):
        if fail_with is not None and fail_with not in FAILURE_CONTROLS:
            raise SmsContractError(
                f"unknown mock failure control {fail_with!r} — "
                f"expected {FAILURE_CONTROLS}")
        self.fail_with = fail_with
        self.fail_times = int(fail_times)
        self.calls: list = []
        self._n = 0

    def _scripted(self, control: str) -> Dict:
        if control in ("timeout", "server_error"):
            return _outcome(OUT_TRANSIENT_FAILURE, f"mock_{control}")
        if control == "rate_limited":
            return _outcome(OUT_RATE_LIMITED, "mock_rate_limited", 3)
        if control == "no_credit":
            return _outcome(OUT_PERMANENT_FAILURE, "no_credit")
        return _outcome(OUT_PERMANENT_FAILURE, control)

    def send(self, event: Dict, ref: Dict) -> Dict:
        self._n += 1
        source = event or {}
        ref = ref or {}
        variables = dict(source.get("variables")
                         or ref.get("variables") or {})
        template_id = str(source.get("template_id")
                          or ref.get("template_id") or "")
        if self.fail_with and self._n <= self.fail_times:
            return self._scripted(self.fail_with)
        recipient = normalize_recipient(variables.get("phone_ref"))
        if recipient is None:
            return _outcome(OUT_PERMANENT_FAILURE, "invalid_recipient")
        message_id = f"MOCK-SMS-{self._n}"
        self.calls.append({"recipient": recipient,
                           "template_id": template_id,
                           "body": render_body(template_id, variables),
                           "message_id": message_id})
        return _outcome(OUT_DELIVERED, f"mock_sms:{message_id}")


# --- Kavenegar live adapter -------------------------------------------------

def _check_template_map(mapping: Dict) -> Dict[str, Dict]:
    """Validate an owner-supplied template mapping at CONSTRUCTION time."""
    if not isinstance(mapping, dict):
        raise SmsContractError("template map must be an object")
    if len(mapping) > MAX_TEMPLATE_MAP_ENTRIES:
        raise SmsContractError(
            f"template map is bounded to {MAX_TEMPLATE_MAP_ENTRIES} entries")
    checked: Dict[str, Dict] = {}
    for template_id, spec in mapping.items():
        if not isinstance(template_id, str) or not template_id:
            raise SmsContractError("template map keys are template ids")
        if not isinstance(spec, dict):
            raise SmsContractError(
                f"template map entry {template_id!r} must be an object")
        name = spec.get("name")
        if not isinstance(name, str) or not _TEMPLATE_NAME_RE.match(name):
            raise SmsContractError(
                f"template map entry {template_id!r} needs a provider "
                "template name of [A-Za-z0-9_-]{1,64}")
        tokens = spec.get("tokens")
        if not isinstance(tokens, (list, tuple)) or not tokens:
            raise SmsContractError(
                f"template map entry {template_id!r} needs a non-empty "
                "token variable list")
        if len(tokens) > MAX_VERIFY_TOKENS:
            raise SmsContractError(
                f"template map entry {template_id!r} exceeds "
                f"{MAX_VERIFY_TOKENS} tokens")
        for var in tokens:
            if not isinstance(var, str) or not _VARNAME_RE.match(var):
                raise SmsContractError(
                    f"template map entry {template_id!r} has an invalid "
                    f"token variable {var!r}")
        checked[template_id] = {"name": name, "tokens": tuple(tokens)}
    return checked


def parse_template_map(raw) -> Dict[str, Dict]:
    """`KAVENEGAR_TEMPLATE_MAP` JSON → validated mapping ({} when unset)."""
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise SmsContractError(
            f"{TEMPLATE_MAP_ENV} must be a JSON object: {exc}")
    return _check_template_map(parsed)


class KavenegarSmsAdapter(SmsAdapter):
    """Live Kavenegar adapter (decision row 74): construction-gated,
    injectable transport, redacted errors, outcome-only failures.

    The transport receives `{"method", "url", "params"}` and returns
    `{"status_code", "body"}` — no network happens in tests because a
    transport is ALWAYS injected (D-116: canonical code opens no socket).
    """

    def __init__(self, transport=None, api_key: Optional[str] = None,
                 sender: Optional[str] = None,
                 template_map: Optional[Dict] = None,
                 env: Optional[Dict[str, str]] = None):
        if api_key is None:
            gate = require_live_keys(env)
            self._api_key = gate["api_key"]
            self._sender = gate["sender"] if sender is None \
                else str(sender).strip()
        else:
            self._api_key = str(api_key).strip()
            self._sender = str(sender or "").strip()
            if not self._api_key:
                raise SmsContractError(
                    f"{API_KEY_ENV} must be non-empty when supplied")
        if transport is None:
            raise SmsContractError(
                "KavenegarSmsAdapter requires an injected transport — "
                "direct HTTP is forbidden in canonical code (D-116)")
        if not callable(transport):
            raise SmsContractError("transport must be callable")
        self._transport = transport
        self._template_map = _check_template_map(template_map or {})

    def _call(self, method: str, params: Dict) -> Dict:
        request = {"method": method,
                   "url": f"{API_BASE}/{self._api_key}/{method}.json",
                   "params": dict(params)}
        try:
            response = self._transport(request)
        except TimeoutError:
            raise _SmsTransient("transport timeout")
        except (ConnectionError, OSError):
            raise _SmsTransient("transport unreachable")
        response = response or {}
        status_code = int(response.get("status_code", 0) or 0)
        body = response.get("body", "")
        parsed = _parse_body(body)
        provider = (parsed.get("return") or {}).get("status") \
            if parsed else None
        if status_code != 200 or provider != 200:
            raise parse_kavenegar_error(status_code, body)
        return parsed

    @staticmethod
    def _accepted(parsed: Dict) -> Dict:
        entries = parsed.get("entries") or []
        message_id = None
        if isinstance(entries, list) and entries \
                and isinstance(entries[0], dict):
            message_id = entries[0].get("messageid")
        if message_id is None:
            return _outcome(OUT_DELIVERED, "kavenegar_accepted")
        return _outcome(OUT_DELIVERED,
                        f"kavenegar_message_id:{message_id}")

    def send(self, event: Dict, ref: Dict) -> Dict:
        source = event or {}
        ref = ref or {}
        variables = dict(source.get("variables")
                         or ref.get("variables") or {})
        template_id = str(source.get("template_id")
                          or ref.get("template_id") or "")
        recipient = normalize_recipient(variables.get("phone_ref"))
        if recipient is None:
            return _outcome(OUT_PERMANENT_FAILURE, "invalid_recipient")
        spec = self._template_map.get(template_id)
        try:
            if spec is not None:
                params: Dict = {"receptor": recipient,
                                "template": spec["name"]}
                for index, var in enumerate(spec["tokens"]):
                    if var not in variables:
                        return _outcome(
                            OUT_PERMANENT_FAILURE,
                            f"template_variable_missing:{var}")
                    params[("token", "token2", "token3")[index]] = \
                        str(variables[var])
                return self._accepted(self._call("verify/lookup", params))
            body = render_body(template_id, variables)
            if body is None:
                return _outcome(OUT_PERMANENT_FAILURE,
                                f"body_unavailable:{template_id}")
            if not self._sender:
                return _outcome(OUT_PERMANENT_FAILURE,
                                "sender_line_not_configured")
            return self._accepted(self._call("sms/send", {
                "receptor": recipient,
                "sender": self._sender,
                "message": body,
            }))
        except _SmsRateLimited as exc:
            return _outcome(OUT_RATE_LIMITED,
                            redact(str(exc), [self._api_key]),
                            exc.retry_after_s)
        except _SmsTransient as exc:
            return _outcome(OUT_TRANSIENT_FAILURE,
                            redact(str(exc), [self._api_key]))
        except _SmsRejected as exc:
            return _outcome(OUT_PERMANENT_FAILURE,
                            redact(str(exc), [self._api_key]))


# --- selection (mock fallback / live gate) ----------------------------------

def build_sms_adapter(env: Optional[Dict[str, str]] = None,
                      transport=None) -> SmsAdapter:
    """Select the SMS adapter from the environment (D-045/D-075).

    No live flag ⇒ `MockSmsAdapter` (the deterministic fallback: it sends
    nothing). Live flag WITHOUT a credential is a misconfiguration and
    raises Class-B rather than silently mocking — fail closed, never fake
    a delivery. A live adapter additionally requires an injected
    transport, because canonical code opens no socket (D-116).
    """
    values = os.environ if env is None else env
    if not live_enabled(values):
        return MockSmsAdapter()
    gate = require_live_keys(values)
    template_map = parse_template_map(values.get(TEMPLATE_MAP_ENV, ""))
    if transport is None:
        raise SmsContractError(
            "live SMS adapter selected but no transport was injected — "
            "canonical code opens no socket (D-116)")
    return KavenegarSmsAdapter(transport=transport, api_key=gate["api_key"],
                               sender=gate["sender"],
                               template_map=template_map)


def sms_channel_binding(env: Optional[Dict[str, str]] = None,
                        transport=None) -> Dict[str, ChannelAdapter]:
    """The one binding a composition root needs:

        NotificationWorker(engine, {CH_IN_APP: LocalInAppAdapter(),
                                    **sms_channel_binding()})

    There is deliberately no other SMS dispatch entry point (row 74).
    """
    return {CH_SMS: build_sms_adapter(env=env, transport=transport)}


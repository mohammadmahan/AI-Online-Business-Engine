#!/usr/bin/env python3
"""D-176 / D-172 §4.1 — loopback-only AI bridge for the commerce admin.

This service is the ONLY process that combines the canonical fashion
copywriting engine with the local Ollama transport. It exists because the
commerce app is TypeScript and the canonical AI runtime is Python; a thin
HTTP seam keeps the authority boundary intact instead of duplicating the
router, contracts or divergence guards in Node.

Hard boundaries:

  - binds to 127.0.0.1 only (not configurable);
  - requires `AI_BRIDGE_TOKEN` and a bearer token on every generation call;
  - accepts only a structured, PII-free copy brief (no order/customer data);
  - runs `FashionCopywritingEngine` in DRY-RUN mode only: nothing is
    persisted and no account/database connection is opened;
  - dispatches only through `build_default_ai_router`, whose only provider
    is local Ollama at a loopback URL;
  - rejects email addresses, phone numbers and URLs in both the request and
    the model output, so a generated proposal cannot exfiltrate contact data;
  - never returns provider messages verbatim and never logs request bodies.

The bridge is a local development component. It is not a public service and
has no deployment credential (D-045/D-139).
"""

from __future__ import annotations

import argparse
import hmac
import json
import os
import re
import sys
import threading
import uuid
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, Dict, Optional

_LOCAL = Path(__file__).resolve().parent.parent
if str(_LOCAL) not in sys.path:
    sys.path.insert(0, str(_LOCAL))

from canonical.ai_contracts import OutputValidationError  # noqa: E402
from canonical.ai_providers_multi import redact_ai  # noqa: E402
from canonical.fashion_copy import (  # noqa: E402
    FashionBrief,
    FashionCopywritingEngine,
    FashionInputError,
)

BIND_HOST = "127.0.0.1"  # pinned; NOT configurable
DEFAULT_PORT = 8099
TOKEN_ENV = "AI_BRIDGE_TOKEN"
MAX_BODY_BYTES = 16_384
MAX_RESPONSE_STRING = 8_000
CHANNELS = ("seo_copy", "instagram_caption", "telegram_announcement")
TONES = ("luxury", "casual", "trendy")
_ALLOWED_FIELDS = frozenset(
    {"channel", "title", "fabric_type", "season", "notes", "tone"}
)

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?98|0)?9\d{9}(?!\d)")
_LONG_DIGITS_RE = re.compile(r"\d{10,}")
_URL_RE = re.compile(r"(?i)\b(?:https?://|www\.|t\.me/)")


class BridgeError(Exception):
    """A typed, safe-to-return refusal."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


@dataclass(frozen=True)
class AssistantRequest:
    channel: str
    title: str
    fabric_type: str
    season: str
    notes: str = ""
    tone: str = "luxury"

    @classmethod
    def parse(cls, payload: object) -> "AssistantRequest":
        if not isinstance(payload, dict):
            raise BridgeError(400, "INVALID_JSON", "درخواست باید یک شیء JSON باشد.")
        extra = set(payload) - _ALLOWED_FIELDS
        if extra:
            raise BridgeError(
                400, "INVALID_FIELDS", "فیلد ناشناخته در درخواست وجود دارد."
            )
        channel = _text(payload.get("channel"), "channel", 1, 64)
        if channel not in CHANNELS:
            raise BridgeError(400, "INVALID_CHANNEL", "کانال درخواستی پشتیبانی نمی‌شود.")
        title = _text(payload.get("title"), "title", 2, 200)
        fabric = _text(payload.get("fabric_type"), "fabric_type", 2, 60)
        season = _text(payload.get("season"), "season", 1, 40)
        notes = _text(payload.get("notes", ""), "notes", 0, 1000)
        tone = _text(payload.get("tone", "luxury"), "tone", 1, 20).lower()
        if tone not in TONES:
            raise BridgeError(400, "INVALID_TONE", "لحن درخواستی پشتیبانی نمی‌شود.")
        for label, value in (
            ("title", title),
            ("fabric_type", fabric),
            ("season", season),
            ("notes", notes),
        ):
            _reject_pii(value, label)
        return cls(channel=channel, title=title, fabric_type=fabric,
                   season=season, notes=notes, tone=tone)

    def brief(self) -> FashionBrief:
        try:
            return FashionBrief(
                title=self.title,
                fabric_type=self.fabric_type,
                season=self.season,
                notes=self.notes,
                tone=self.tone,
            ).validated()
        except FashionInputError as exc:
            raise BridgeError(400, "INVALID_BRIEF", str(exc)) from exc


def _text(value: object, label: str, minimum: int, maximum: int) -> str:
    if not isinstance(value, str):
        raise BridgeError(400, "INVALID_FIELDS", f"{label} باید متن باشد.")
    clean = value.strip()
    if len(clean) < minimum:
        raise BridgeError(400, "INVALID_FIELDS", f"{label} کوتاه‌تر از حد مجاز است.")
    if len(clean) > maximum:
        raise BridgeError(400, "INVALID_FIELDS", f"{label} بلندتر از حد مجاز است.")
    return clean


def _reject_pii(value: str, label: str) -> None:
    if _EMAIL_RE.search(value) or _PHONE_RE.search(value) or _LONG_DIGITS_RE.search(value):
        raise BridgeError(400, "PII_REJECTED", f"{label} دادهٔ تماس/شناسهٔ حساس دارد.")
    if _URL_RE.search(value):
        raise BridgeError(400, "URL_REJECTED", f"{label} نشانی اینترنتی دارد.")


def _output_is_safe(node: object) -> bool:
    if isinstance(node, str):
        return not (
            _EMAIL_RE.search(node)
            or _PHONE_RE.search(node)
            or _LONG_DIGITS_RE.search(node)
            or _URL_RE.search(node)
        )
    if isinstance(node, dict):
        return all(_output_is_safe(k) and _output_is_safe(v) for k, v in node.items())
    if isinstance(node, (list, tuple)):
        return all(_output_is_safe(item) for item in node)
    return True


def _default_engine_factory() -> FashionCopywritingEngine:
    """Build the canonical engine on the local Ollama router only."""
    from services.ai_runtime_factory import build_default_ai_router

    return FashionCopywritingEngine(build_default_ai_router())


def _engine_unavailable(report: object) -> bool:
    """True when the report is an availability failure, not a content refusal.

    The engine returns (rather than raises) provider failures and records the
    D-052 class. Class A covers an unreachable/timed-out Ollama daemon. The
    transport reports a missing model as Class B but with an explicit
    ``Ollama model ... is not available`` message; the bridge still treats
    that as an unavailable engine, never as a content problem.
    """
    if getattr(report, "failure_class", None) == "A":
        return True
    detail = str(getattr(report, "error", "") or "")
    return "Ollama model" in detail and "not available" in detail


class AssistantService:
    """Pure service object; the HTTP handler only translates to/from it."""

    def __init__(self, engine_factory: Optional[Callable[[], object]] = None):
        self._engine_factory = engine_factory or _default_engine_factory
        self._engine = None
        self._lock = threading.Lock()

    def health(self) -> Dict:
        model = os.environ.get("OLLAMA_MODEL", "").strip()
        base = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").strip()
        loopback = re.match(
            r"^https?://(?:127\.0\.0\.1|localhost|\[::1\])(?::\d+)?(?:/|$)", base
        ) is not None
        return {
            "ok": bool(model) and loopback,
            "service": "commerce-ai-bridge",
            "provider": "ollama",
            "model": model or None,
            "loopback": loopback,
            "mode": "dry-run",
        }

    def _get_engine(self):
        if self._engine is None:
            with self._lock:
                if self._engine is None:
                    self._engine = self._engine_factory()
        return self._engine

    def generate(self, payload: object) -> Dict:
        request = AssistantRequest.parse(payload)
        brief = request.brief()
        try:
            engine = self._get_engine()
            report = engine.generate(
                request.channel, brief, mode="dry-run", actor="commerce-admin"
            )
        except OutputValidationError:
            # The model answered, but outside the strict contract. This is a
            # content refusal, not an availability failure.
            raise BridgeError(
                422,
                "AI_REFUSED",
                "پیشنهاد هوش مصنوعی با قرارداد محتوا هم‌خوان نبود؛ کنار گذاشته شد.",
            )
        except Exception:
            # Never expose a provider/transport message: it can contain a URL
            # or a local path, and this endpoint is reachable by the browser.
            raise BridgeError(
                503,
                "AI_UNAVAILABLE",
                "موتور هوش مصنوعی محلی در دسترس نیست؛ پیشنهادی ساخته نشد.",
            )

        if not getattr(report, "ok", False) or getattr(report, "proposal", None) is None:
            if _engine_unavailable(report):
                raise BridgeError(
                    503,
                    "AI_UNAVAILABLE",
                    "موتور هوش مصنوعی محلی در دسترس نیست؛ پیشنهادی ساخته نشد.",
                )
            detail = redact_ai(str(getattr(report, "error", "") or ""))[:300]
            raise BridgeError(
                422,
                "AI_REFUSED",
                "پیشنهاد هوش مصنوعی از قرارداد یا قواعد محتوا عبور نکرد."
                + (f" ({detail})" if detail else ""),
            )

        proposal = report.proposal
        body = proposal.payload if isinstance(proposal.payload, dict) else None
        if not isinstance(body, dict) or not _output_is_safe(body):
            raise BridgeError(
                422,
                "AI_OUTPUT_UNSAFE",
                "خروجی مدل دادهٔ حساس یا نشانی اینترنتی داشت و کنار گذاشته شد.",
            )

        # Bound every string so a runaway model cannot fill the admin page or
        # the server's response buffer.
        if any(
            isinstance(value, str) and len(value) > MAX_RESPONSE_STRING
            for value in _walk_strings(body)
        ):
            raise BridgeError(
                422, "AI_OUTPUT_TOO_LARGE", "خروجی مدل از حد مجاز بلندتر است."
            )

        return {
            "ok": True,
            "request_id": str(uuid.uuid4()),
            "channel": request.channel,
            "mode": "dry-run",
            "proposal": body,
            "provider": getattr(proposal, "provider", "ollama"),
            "model": getattr(proposal, "model", ""),
            "usage": dict(getattr(proposal, "usage", {}) or {}),
            "warnings": list(getattr(report, "warnings", []) or []),
        }


def _walk_strings(node: object):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for key, value in node.items():
            yield from _walk_strings(key)
            yield from _walk_strings(value)
    elif isinstance(node, (list, tuple)):
        for item in node:
            yield from _walk_strings(item)


def _json_bytes(body: Dict) -> bytes:
    return json.dumps(body, ensure_ascii=False).encode("utf-8")


class AiBridge:
    """Loopback-only HTTP server with an injectable service."""

    def __init__(self, token: str, service: Optional[AssistantService] = None,
                 port: int = DEFAULT_PORT):
        if not token or not token.strip():
            raise ValueError("AI_BRIDGE_TOKEN is required (fail-closed)")
        self._token = token.strip()
        self._service = service or AssistantService()
        self._port = int(port)
        self._httpd: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self.bound_address = None

    def _authorized(self, header: Optional[str]) -> bool:
        presented = (header or "").strip()
        if not presented.lower().startswith("bearer "):
            return False
        supplied = presented[7:].strip()
        return hmac.compare_digest(supplied.encode("utf-8"),
                                   self._token.encode("utf-8"))

    def start(self) -> int:
        if self._httpd is not None:
            raise RuntimeError("AI bridge already running")
        service = self._service
        authorized = self._authorized

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_GET(self) -> None:  # noqa: N802
                if self.path.split("?", 1)[0] != "/health":
                    self._send(404, {"ok": False, "code": "NOT_FOUND"})
                    return
                health = service.health()
                self._send(200 if health.get("ok") else 503, health)

            def do_POST(self) -> None:  # noqa: N802
                if self.path.split("?", 1)[0] != "/assistant":
                    self._send(404, {"ok": False, "code": "NOT_FOUND"})
                    return
                if not authorized(self.headers.get("authorization")):
                    self._send(401, {
                        "ok": False,
                        "code": "UNAUTHORIZED",
                        "message": "دسترسی به پل هوش مصنوعی مجاز نیست.",
                    })
                    return
                try:
                    length = int(self.headers.get("content-length", "0"))
                except ValueError:
                    length = 0
                if length <= 0 or length > MAX_BODY_BYTES:
                    self._send(400, {
                        "ok": False,
                        "code": "INVALID_BODY",
                        "message": "بدنهٔ درخواست خالی یا بیش از حد بزرگ است.",
                    })
                    return
                try:
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))
                    result = service.generate(payload)
                except BridgeError as exc:
                    self._send(exc.status, {
                        "ok": False, "code": exc.code, "message": exc.message,
                    })
                    return
                except (ValueError, UnicodeDecodeError):
                    self._send(400, {
                        "ok": False,
                        "code": "INVALID_JSON",
                        "message": "بدنهٔ درخواست JSON معتبر نیست.",
                    })
                    return
                except Exception:
                    self._send(500, {
                        "ok": False,
                        "code": "UNEXPECTED",
                        "message": "پل هوش مصنوعی با خطای غیرمنتظره روبه‌رو شد.",
                    })
                    return
                self._send(200, result)

            def _send(self, status: int, body: Dict) -> None:
                data = _json_bytes(body)
                try:
                    self.send_response(status)
                    self.send_header("content-type", "application/json; charset=utf-8")
                    self.send_header("content-length", str(len(data)))
                    self.send_header("cache-control", "no-store")
                    self.send_header("connection", "close")
                    self.close_connection = True
                    self.end_headers()
                    self.wfile.write(data)
                    # Flush before the close so Windows clients receive the
                    # typed 401/422 body instead of a reset connection.
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def log_message(self, fmt: str, *args) -> None:  # quiet
                return

        self._httpd = ThreadingHTTPServer((BIND_HOST, self._port), Handler)
        self._httpd.daemon_threads = True
        self.bound_address = self._httpd.server_address
        self._thread = threading.Thread(target=self._httpd.serve_forever,
                                        name="commerce-ai-bridge", daemon=True)
        self._thread.start()
        return int(self._httpd.server_address[1])

    def close(self) -> None:
        if self._httpd is None:
            return
        self._httpd.shutdown()
        self._httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._httpd = None
        self._thread = None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="loopback commerce AI bridge")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args(argv)
    token = os.environ.get(TOKEN_ENV, "").strip()
    if not token:
        print(f"refused: {TOKEN_ENV} is required", file=sys.stderr)
        return 2
    bridge = AiBridge(token=token, port=args.port)
    port = bridge.start()
    print(f"commerce AI bridge listening on http://{BIND_HOST}:{port} "
          "(dry-run; provider=ollama; loopback only)")
    try:
        while True:
            threading.Event().wait(3600)
    except KeyboardInterrupt:
        pass
    finally:
        bridge.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

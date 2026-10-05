#!/usr/bin/env python3
"""Phase 27.8 — read-only local health sidecar.

A stdlib-only HTTP service bound STRICTLY to 127.0.0.1 (the bind address is
not configurable, mirroring the D-122 metrics exporter precedent). It exposes
one read-only probe endpoint per container surface and serialises each reading
in the JSON shape the Phase 27.7 control-plane probe seam consumes:

    GET /health/postgres   SELECT 1 + connection count (read-only)
    GET /health/redis      socket PING (+ AUTH off-band), memory, queue depth
    GET /health/n8n        loopback healthz GET (no API key, no credentials)
    GET /health/dokploy    local daemon health URL when configured
    GET /health/walrus     local cache health URL when configured (PLANNED, D-142)
    GET /health            index of all five surfaces

Fail-closed semantics: a probe that times out or cannot be assessed returns
HTTP 503 with a structured JSON body carrying a Persian reason. DEGRADED is an
explicit verdict returned over HTTP 200 (the transport answered; the component
is degraded) and is never silently painted as healthy.

Read-only guarantees: the PostgreSQL probe runs SELECT-only statements over the
established local psql channel (`seed_registry.db_env`), the Redis probe sends
PING/INFO/LLEN only, the n8n/dokploy/walrus probes are GETs. No credential is
accepted, stored or echoed: response strings pass the D-124 redaction gate and
credential-shaped keys are replaced by a fixed marker before serialisation.

Status vocabulary is the control-plane taxonomy (HEALTHY/DEGRADED/DOWN/
UNKNOWN), mapping 1:1 onto the canonical D-123 verdicts used elsewhere
(PASS/DEGRADED/FAIL) with UNKNOWN as "cannot assess".
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from contextlib import closing
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

_HERE = Path(__file__).resolve()
_LOCAL = _HERE.parent.parent
for _p in (str(_LOCAL), str(_LOCAL / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from canonical.obs_contracts import redact  # noqa: E402
from seed_registry import db_env  # noqa: E402

BIND_HOST = "127.0.0.1"          # pinned; NOT configurable (D-122 precedent)
DEFAULT_PORT = 8088
PROBE_TIMEOUT_S = 0.45           # fast, fail-closed budget (directive: < 500 ms)

STATUSES = ("HEALTHY", "DEGRADED", "DOWN", "UNKNOWN")
_OK_STATUSES = ("HEALTHY", "DEGRADED")
_SEVERITY = {"HEALTHY": 0, "DEGRADED": 1, "UNKNOWN": 2, "DOWN": 3}

_SENSITIVE_KEY = re.compile(
    r"(password|passwd|secret|token|credential|authorization|private_key"
    r"|api[_-]?key|pan|cvv|iban|card_number)",
    re.IGNORECASE,
)
_REDACTED_MARK = "«redacted»"

_UNKNOWN_FALLBACK_FA = (
    "کاوش با خطای غیرمنتظره متوقف شد؛ وضعیت نامشخص می‌ماند (fail-closed)."
)


class SidecarError(RuntimeError):
    """Programming error in this service (never a probe verdict)."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def _as_int(value: Optional[str], fallback: Optional[int] = None) -> Optional[int]:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return fallback


def _redact_value(value):
    """D-114/D-124 gate: redact credential-shaped spans and keys."""
    if isinstance(value, str):
        return redact(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, dict):
        out: Dict = {}
        for key, item in value.items():
            out[str(key)] = (
                _REDACTED_MARK
                if _SENSITIVE_KEY.search(str(key))
                else _redact_value(item)
            )
        return out
    if isinstance(value, (list, tuple)):
        return [_redact_value(item) for item in value]
    return redact(str(value))


# ── PostgreSQL (read-only SELECT channel, host psql → container fallback) ─────

_PG_LIVENESS_SQL = "SELECT 1;"
_PG_CONNECTIONS_SQL = (
    "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database();"
)
_PG_CEILING_SQL = "SHOW max_connections;"


def _pg_run(
    argv: List[str], sql: str, env: Dict[str, str]
) -> Tuple[Optional[str], Optional[str]]:
    """Run one read-only statement. Returns (value, failure_code).

    `env` carries the canonical local connection settings (`db_env()`);
    passing it explicitly is the whole point — psql must never fall back to
    an ambient default connection.
    """
    try:
        proc = subprocess.run(
            argv,
            input=sql,
            capture_output=True,
            text=True,
            env=env,
            timeout=PROBE_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return None, "timeout"
    except (FileNotFoundError, OSError):
        return None, "client_unavailable"
    if proc.returncode != 0:
        return None, "query_failed"
    return proc.stdout.strip(), None


def _pg_read(sql: str) -> Tuple[Optional[str], Optional[str]]:
    env = dict(os.environ)
    env.update(db_env())
    argv = ["psql", "-v", "ON_ERROR_STOP=1", "-X", "-q", "-A", "-t"]
    value, failure = _pg_run(argv, sql, env)
    if failure == "client_unavailable":
        # Host psql absent → the established container channel (idempotent,
        # read-only; the shell credential stays in the environment only).
        container = os.environ.get("LOCAL_PG_CONTAINER", "engine-local-postgres")
        argv = [
            "docker", "exec", "-i", container,
            "psql", "-v", "ON_ERROR_STOP=1", "-X", "-q", "-A", "-t",
            "-U", env.get("PGUSER", "engine_local"),
            "-d", env.get("PGDATABASE", "business_engine_local"),
        ]
        return _pg_run(argv, sql, env)
    return value, failure


def probe_postgres() -> Dict:
    """Read-only liveness (SELECT 1) plus connection count and ceiling."""
    value, failure = _pg_read(_PG_LIVENESS_SQL)
    if failure == "timeout":
        return {
            "status": "UNKNOWN",
            "reasonFa": "کاوش PostgreSQL در بودجه‌ی زمانی پاسخ نداد؛ وضعیت نامشخص می‌ماند (fail-closed).",
        }
    if failure is not None:
        return {
            "status": "DOWN",
            "reasonFa": "اتصال فقط‌خواندنی به PostgreSQL برقرار نشد (SELECT 1 ناموفق بود).",
        }
    if value != "1":
        return {
            "status": "DOWN",
            "reasonFa": "پاسخ SELECT 1 غیرمنتظره بود؛ سلامت پایگاه داده تأیید نشد.",
        }

    connections, c_failure = _pg_read(_PG_CONNECTIONS_SQL)
    ceiling, m_failure = _pg_read(_PG_CEILING_SQL)
    if c_failure is not None or m_failure is not None:
        return {
            "status": "DEGRADED",
            "reasonFa": "اتصال برقرار است اما شمارش اتصالات یا سقف آن خوانده نشد؛ وضعیت تنزل‌یافته اعلام می‌شود.",
        }
    return {
        "status": "HEALTHY",
        "reasonFa": "",
        "metrics": {
            "connections": _as_int(connections),
            "connectionCeiling": _as_int(ceiling),
        },
    }


# ── Redis (minimal RESP client: PING / INFO memory / LLEN, read-only) ────────


def _redis_read_line(sock: socket.socket, limit: int = 8192) -> bytes:
    buf = bytearray()
    while b"\r\n" not in buf:
        chunk = sock.recv(1)
        if not chunk:
            raise OSError("connection closed")
        buf += chunk
        if len(buf) > limit:
            raise OSError("reply line too long")
    return bytes(buf).split(b"\r\n", 1)[0]


def _redis_command(sock: socket.socket, *parts: str) -> Tuple[str, object]:
    """Send one inline command; return (kind, value) for + - : $ replies."""
    line = " ".join(parts) + "\r\n"
    sock.sendall(line.encode("utf-8"))
    head = _redis_read_line(sock)
    kind = chr(head[0])
    payload = head[1:].decode("utf-8", "replace")
    if kind == "$":
        length = _as_int(payload, -1)
        if length is None or length < 0:
            return "$", None
        data = b""
        while len(data) < length + 2:
            chunk = sock.recv(length + 2 - len(data))
            if not chunk:
                raise OSError("connection closed mid-reply")
            data += chunk
        return "$", data[:length].decode("utf-8", "replace")
    if kind == ":":
        return ":", _as_int(payload)
    if kind == "+":
        return "+", payload
    return kind, payload


def probe_redis() -> Dict:
    """Socket PING (+ optional off-band AUTH), memory usage, queue depth."""
    host = os.environ.get("LOCAL_REDIS_HOST", "127.0.0.1")
    port = _as_int(os.environ.get("LOCAL_REDIS_PORT"), 6379)
    password = os.environ.get("LOCAL_REDIS_PASSWORD")
    queue_key = os.environ.get("LOCAL_REDIS_QUEUE_KEY")
    try:
        sock = socket.create_connection((host, port), timeout=PROBE_TIMEOUT_S)
        sock.settimeout(PROBE_TIMEOUT_S)
    except (socket.timeout, OSError):
        return {
            "status": "DOWN",
            "reasonFa": "سوکت Redis در نشانی پیکربندی‌شده پاسخ نداد؛ صف و کش در دسترس نیست.",
        }
    try:
        with closing(sock):
            if password:
                kind, value = _redis_command(sock, "AUTH", password)
                if kind == "-" or str(value).upper() != "OK":
                    return {
                        "status": "DOWN",
                        "reasonFa": "احراز هویت Redis پذیرفته نشد؛ کاوش ادامه پیدا نکرد (fail-closed).",
                    }
            kind, value = _redis_command(sock, "PING")
            if str(value).upper() != "PONG":
                return {
                    "status": "DEGRADED",
                    "reasonFa": "Redis پاسخ PING را با PONG تأیید نکرد؛ وضعیت تنزل‌یافته اعلام می‌شود.",
                }

            memory_bytes: Optional[int] = None
            kind, info = _redis_command(sock, "INFO", "memory")
            if kind == "$" and isinstance(info, str):
                for line in info.splitlines():
                    if line.startswith("used_memory:"):
                        memory_bytes = _as_int(line.split(":", 1)[1])
                        break

            depth: Optional[int] = None
            if queue_key:
                kind, value = _redis_command(sock, "LLEN", queue_key)
                if kind == ":":
                    depth = value if isinstance(value, int) else None

            return {
                "status": "HEALTHY",
                "reasonFa": "",
                "metrics": {
                    "memoryUsedBytes": memory_bytes,
                    "queueKey": queue_key,
                },
                "depth": depth,
                # Read honestly: a queue processing rate is not derivable from
                # plain Redis INFO, so it stays null (never invented).
                "throughputPerMin": None,
            }
    except (socket.timeout, OSError):
        return {
            "status": "UNKNOWN",
            "reasonFa": "گفتگو با Redis نیمه‌کاره ماند؛ وضعیت نامشخص می‌ماند (fail-closed).",
        }


# ── Loopback HTTP health proxies (n8n / dokploy / walrus) ────────────────────


def _http_json_get(url: str) -> Tuple[Optional[int], Optional[object], Optional[str]]:
    """GET a loopback URL. Returns (status_code, parsed_json, failure_code)."""
    request = urllib.request.Request(url, headers={"accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=PROBE_TIMEOUT_S) as response:
            body = response.read(8192).decode("utf-8", "replace")
            code = response.status
    except urllib.error.HTTPError as err:
        return err.code, None, "http_error"
    except (urllib.error.URLError, TimeoutError, OSError):
        return None, None, "unreachable"
    try:
        return code, json.loads(body), None
    except (ValueError, TypeError):
        return code, None, "unparsable"


def probe_n8n() -> Dict:
    """Loopback healthz GET — no API key, no workflow credential."""
    url = os.environ.get(
        "LOCAL_N8N_HEALTH_URL", "http://127.0.0.1:15678/healthz/readiness"
    )
    code, payload, failure = _http_json_get(url)
    if failure == "unreachable":
        return {
            "status": "DOWN",
            "reasonFa": "نشانی سلامت n8n روی loopback پاسخ نداد؛ موتور اتوماسیون در دسترس نیست.",
        }
    if failure == "http_error":
        return {
            "status": "DOWN",
            "reasonFa": f"healthz مربوط به n8n با کد وضعیت {code} پاسخ داد؛ سلامت تأیید نشد.",
        }
    if failure == "unparsable":
        return {
            "status": "DEGRADED",
            "reasonFa": "پاسخ healthz مربوط به n8n قابل تجزیه نبود؛ وضعیت تنزل‌یافته اعلام می‌شود.",
        }
    health = ""
    if isinstance(payload, dict):
        health = str(payload.get("status", ""))
    if code == 200 and health.lower() in ("ok", "up", "healthy"):
        return {"status": "HEALTHY", "reasonFa": "", "metrics": {"health": health or "ok"}}
    if code == 200:
        return {
            "status": "DEGRADED",
            "reasonFa": "healthz پاسخ ۲۰۰ داد اما وضعیت اعلامی آن سالم نیست؛ تنزل‌یافته گزارش می‌شود.",
            "metrics": {"health": health or None},
        }
    return {
        "status": "DOWN",
        "reasonFa": f"healthz مربوط به n8n با کد وضعیت {code} پاسخ داد؛ سلامت تأیید نشد.",
    }


def _probe_optional_surface(env_var: str, label_fa: str, planned_note_fa: str) -> Dict:
    url = os.environ.get(env_var, "")
    if not url:
        return {"status": "UNKNOWN", "reasonFa": planned_note_fa}
    code, payload, failure = _http_json_get(url)
    if failure == "unreachable":
        return {
            "status": "DOWN",
            "reasonFa": f"نشانی سلامت {label_fa} روی loopback پاسخ نداد؛ سرویس در دسترس نیست.",
        }
    if failure == "http_error":
        return {
            "status": "DOWN",
            "reasonFa": f"سلامت {label_fa} با کد وضعیت {code} پاسخ داد؛ تأیید نشد.",
        }
    if failure == "unparsable":
        return {
            "status": "DEGRADED",
            "reasonFa": f"پاسخ سلامت {label_fa} قابل تجزیه نبود؛ وضعیت تنزل‌یافته اعلام می‌شود.",
        }
    if code == 200:
        return {"status": "HEALTHY", "reasonFa": "", "metrics": {"health": "ok"}}
    return {
        "status": "DOWN",
        "reasonFa": f"سلامت {label_fa} با کد وضعیت {code} پاسخ داد؛ تأیید نشد.",
    }


def probe_dokploy() -> Dict:
    """Local Dokploy daemon status; UNKNOWN when no loopback URL is configured."""
    return _probe_optional_surface(
        "LOCAL_DOKPLOY_HEALTH_URL",
        "Dokploy",
        "نشانی سلامت Dokploy در این محیط پیکربندی نشده است؛ وضعیت نامشخص می‌ماند (fail-closed).",
    )


def probe_walrus() -> Dict:
    """Local cache availability; PLANNED until the D-045/D-142 gate passes."""
    return _probe_optional_surface(
        "LOCAL_WALRUS_HEALTH_URL",
        "Walrus",
        "Walrus در وضعیت PLANNED است (D-142) و سرویس کش محلی وجود ندارد؛ وضعیت نامشخص می‌ماند (fail-closed).",
    )


SURFACE_IDS = ("postgres", "redis", "n8n", "dokploy", "walrus")


def default_probes() -> Dict[str, Callable[[], Dict]]:
    """The five read-only surfaces, in canonical order."""
    return {
        "postgres": probe_postgres,
        "redis": probe_redis,
        "n8n": probe_n8n,
        "dokploy": probe_dokploy,
        "walrus": probe_walrus,
    }


# ── HTTP server (stdlib, loopback-pinned) ────────────────────────────────────


def _run_probe(fn: Callable[[], Dict]) -> Tuple[Dict, float]:
    started = time.monotonic()
    try:
        outcome = fn()
    except Exception:  # noqa: BLE001 — a probe must never crash the server
        outcome = {"status": "UNKNOWN", "reasonFa": _UNKNOWN_FALLBACK_FA}
    if not isinstance(outcome, dict) or outcome.get("status") not in STATUSES:
        outcome = {
            "status": "UNKNOWN",
            "reasonFa": "وضعیت بازگشتی کاوش نامعتبر بود؛ وضعیت نامشخص می‌ماند (fail-closed).",
        }
    return outcome, started


def _wrap_reading(container_id: str, outcome: Dict, started: float) -> Dict:
    body: Dict = {
        "containerId": container_id,
        "status": outcome["status"],
        "reasonFa": outcome.get("reasonFa", ""),
        "latencyMs": max(0, int(round((time.monotonic() - started) * 1000))),
        "probedAtUtc": _now_iso(),
    }
    for key in (
        "metrics",
        "depth",
        "throughputPerMin",
        "active",
        "waiting",
        "failedLast24h",
    ):
        if key in outcome:
            body[key] = outcome[key]
    return _redact_value(body)


class LocalHealthSidecar:
    """Loopback-only read-only health sidecar.

    The bind address is NOT configurable: 127.0.0.1 always. Port 8088 is the
    operator default; port 0 = an OS-assigned free loopback port (tests).
    Probes are injectable so the unit tests stay hermetic (no network).
    """

    def __init__(
        self,
        probes: Optional[Dict[str, Callable[[], Dict]]] = None,
        port: int = DEFAULT_PORT,
    ):
        if probes is None:
            probes = default_probes()
        self._probes = {
            str(key): fn for key, fn in probes.items()
        }
        if not self._probes:
            raise SidecarError("at least one probe is required")
        self._port = int(port)
        self._httpd: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self.bound_address: Optional[Tuple[str, int]] = None

    def start(self) -> int:
        if self._httpd is not None:
            raise SidecarError("sidecar already running")
        probes = self._probes

        class _Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_GET(self) -> None:  # noqa: N802 — stdlib handler API
                path = self.path.split("?", 1)[0]
                if path == "/health":
                    self._send_index(probes)
                    return
                if path.startswith("/health/"):
                    surface = path[len("/health/"):]
                    fn = probes.get(surface)
                    if fn is None:
                        self._send(404, {"error": "unknown surface",
                                         "surface": surface[:64]})
                        return
                    outcome, started = _run_probe(fn)
                    body = _wrap_reading(surface, outcome, started)
                    code = 200 if body["status"] in _OK_STATUSES else 503
                    self._send(code, body)
                    return
                self._send(404, {"error": "unknown path"})

            def _send_index(self, registry: Dict[str, Callable[[], Dict]]) -> None:
                surfaces: Dict[str, Dict] = {}
                worst = "HEALTHY"
                for surface, fn in registry.items():
                    outcome, started = _run_probe(fn)
                    body = _wrap_reading(surface, outcome, started)
                    surfaces[surface] = body
                    if _SEVERITY[body["status"]] > _SEVERITY[worst]:
                        worst = body["status"]
                code = 200 if worst in _OK_STATUSES else 503
                self._send(code, {"overall": worst, "surfaces": surfaces})

            def _send(self, code: int, body: Dict) -> None:
                payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
                try:
                    self.send_response(code)
                    self.send_header("content-type",
                                     "application/json; charset=utf-8")
                    self.send_header("content-length", str(len(payload)))
                    self.send_header("cache-control", "no-store")
                    self.end_headers()
                    self.wfile.write(payload)
                except (BrokenPipeError, ConnectionResetError):
                    pass  # client hung up; the reading was already computed

            def log_message(self, fmt: str, *args) -> None:  # quiet server
                return

        self._httpd = ThreadingHTTPServer((BIND_HOST, self._port), _Handler)
        self._httpd.daemon_threads = True
        self.bound_address = self._httpd.server_address
        self._thread = threading.Thread(
            target=self._httpd.serve_forever, name="health-sidecar", daemon=True
        )
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


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="read-only local health sidecar")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args(argv)
    sidecar = LocalHealthSidecar(port=args.port)
    port = sidecar.start()
    print(f"health sidecar listening on http://{BIND_HOST}:{port} "
          f"(read-only; surfaces: {', '.join(SURFACE_IDS)})")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        sidecar.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

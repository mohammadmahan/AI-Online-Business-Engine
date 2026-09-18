"""Phase 22 M2 — loopback-only metrics HTTP exporter (D-122).

The I/O-bearing half of the metrics surface. canonical.obs_metrics
stays pure (registry + exposition, battery-asserted deterministic);
this service binds a stdlib HTTP server STRICTLY to 127.0.0.1 —
the bind address is not configurable, loopback scrapes only, no
external endpoint (D-045/D-122). Lives in local/services per the
established boundary: canonical = pure logic, services = I/O.
"""

import sys
import threading
from pathlib import Path
from typing import Tuple

_HERE = Path(__file__).resolve()
_LOCAL = _HERE.parent.parent
for p in (str(_LOCAL), str(_LOCAL / "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

from canonical.obs_metrics import MetricsRegistry, MetricError  # noqa: E402


class LocalMetricsExporter:
    """Loopback-only Prometheus text exposition server (stdlib).

    The bind address is NOT configurable: 127.0.0.1 always (D-122,
    battery-asserted). Port 0 = an OS-assigned free loopback port.
    """

    def __init__(self, registry: MetricsRegistry, port: int = 0,
                 path: str = "/metrics"):
        self._registry = registry
        self._port = int(port)
        self._path = path if path.startswith("/") else "/" + path
        self._httpd = None
        self._thread = None

    def start(self) -> int:
        if self._httpd is not None:
            raise MetricError("exporter already running")
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        reg = self._registry
        path = self._path

        class _Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path != path:
                    self.send_response(404)
                    self.end_headers()
                    return
                body = reg.exposition().encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type",
                                 "text/plain; version=0.0.4; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):  # silence stderr
                pass

        # Loopback bind is hardcoded (D-122) — never 0.0.0.0.
        self._httpd = ThreadingHTTPServer(("127.0.0.1", self._port),
                                          _Handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever,
                                        daemon=True)
        self._thread.start()
        return self._httpd.server_address[1]

    def close(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
            self._thread = None

    @property
    def bound_address(self) -> Tuple[str, int]:
        if self._httpd is None:
            raise MetricError("exporter not running")
        return self._httpd.server_address[:2]

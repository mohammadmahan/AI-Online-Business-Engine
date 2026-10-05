"""Phase 27.8 — read-only health sidecar tests.

Hermetic: every probe is INJECTED, so the suite needs no Docker, no
PostgreSQL, no Redis and no network. What is asserted is the sidecar's own
contract: loopback-only bind, structured JSON, fail-closed HTTP codes
(200 only for HEALTHY/DEGRADED, 503 otherwise), the D-124 redaction gate,
and the read-only method surface (no POST/PUT/DELETE handler exists).

HTTP-level assertions go through `curl` (subprocess) — the same loopback
channel the D-122 metrics-exporter suite uses. `local/tests` sits inside
the D-116 AST sweep, which hard-bans network-library imports even here.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
import unittest.mock

REPO = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
for _p in (os.path.join(REPO, "local"),
           os.path.join(REPO, "local", "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from services.health_sidecar import (  # noqa: E402
    BIND_HOST,
    DEFAULT_PORT,
    STATUSES,
    LocalHealthSidecar,
    SidecarError,
    default_probes,
    probe_dokploy,
    probe_walrus,
)


def _probe(status, reason="", **extra):
    def _call():
        return dict({"status": status, "reasonFa": reason}, **extra)
    return _call


def _raised():
    raise RuntimeError("probe exploded")


def get(port, path, method="GET"):
    """Loopback request via the established local tooling channel (curl).

    Returns `(status_code, raw_body)`. curl exits 0 for any HTTP status, so
    a 503 is read from the `%{http_code}` trailer rather than an exception.
    """
    argv = ["curl", "-s", "-o", "-", "-w", "\n%{http_code}"]
    if method != "GET":
        argv += ["-X", method, "--data", "{}"]
    argv.append(f"http://{BIND_HOST}:{port}{path}")
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=10,
                          check=True)
    body, _, code = proc.stdout.rpartition("\n")
    return int(code), body


def get_json(port, path):
    code, raw = get(port, path)
    return code, json.loads(raw), raw


class _SidecarCase(unittest.TestCase):
    """Base: an injected sidecar on an OS-assigned loopback port."""

    PROBES = {
        "postgres": _probe("HEALTHY", "", metrics={"connections": 3}),
        "redis": _probe("DOWN", "سوکت Redis پاسخ نداد."),
    }

    def setUp(self):
        self.sidecar = LocalHealthSidecar(probes=self.PROBES, port=0)
        self.port = self.sidecar.start()

    def tearDown(self):
        self.sidecar.close()


def _with_sidecar(test_case, probes):
    """Helper: start a one-off sidecar and return (sidecar, port)."""
    sidecar = LocalHealthSidecar(probes=probes, port=0)
    port = sidecar.start()
    return sidecar, port


class TestBindAndSurfaces(_SidecarCase):
    def test_binds_loopback_only_on_ephemeral_port(self):
        address = self.sidecar.bound_address
        self.assertEqual(address[0], BIND_HOST)
        self.assertNotEqual(address[0], "0.0.0.0")
        self.assertGreater(address[1], 0)

    def test_second_start_is_rejected(self):
        with self.assertRaises(SidecarError):
            self.sidecar.start()

    def test_no_probes_is_rejected(self):
        with self.assertRaises(SidecarError):
            LocalHealthSidecar(probes={})

    def test_default_probes_cover_the_five_surfaces(self):
        registry = default_probes()
        self.assertEqual(
            sorted(registry), ["dokploy", "n8n", "postgres", "redis", "walrus"]
        )

    def test_default_port_constant(self):
        self.assertEqual(DEFAULT_PORT, 8088)


class TestHealthyReading(_SidecarCase):
    def test_healthy_surface_returns_200_and_full_schema(self):
        code, body, raw = get_json(self.port, "/health/postgres")
        self.assertEqual(code, 200)
        self.assertEqual(body["containerId"], "postgres")
        self.assertEqual(body["status"], "HEALTHY")
        self.assertEqual(body["reasonFa"], "")
        self.assertIn(body["status"], STATUSES)
        self.assertGreaterEqual(body["latencyMs"], 0)
        self.assertIsInstance(body["latencyMs"], int)
        self.assertRegex(
            body["probedAtUtc"],
            r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$",
        )
        self.assertEqual(body["metrics"], {"connections": 3})
        self.assertNotIn("traceback", raw.lower())


class TestFailClosed(_SidecarCase):
    def test_down_surface_returns_503_with_persian_reason(self):
        code, body, _ = get_json(self.port, "/health/redis")
        self.assertEqual(code, 503)
        self.assertEqual(body["status"], "DOWN")
        self.assertTrue(body["reasonFa"].strip())
        self.assertIn("Redis", body["reasonFa"])

    def test_degraded_is_explicit_over_200(self):
        sidecar, port = _with_sidecar(
            self, {"n8n": _probe("DEGRADED", "پاسخ کند بود.")}
        )
        try:
            code, body, _ = get_json(port, "/health/n8n")
            self.assertEqual(code, 200)
            self.assertEqual(body["status"], "DEGRADED")
            self.assertTrue(body["reasonFa"].strip())
        finally:
            sidecar.close()

    def test_unknown_surface_verdict_is_503(self):
        sidecar, port = _with_sidecar(
            self, {"walrus": _probe("UNKNOWN", "PLANNED (D-142).")}
        )
        try:
            code, body, _ = get_json(port, "/health/walrus")
            self.assertEqual(code, 503)
            self.assertEqual(body["status"], "UNKNOWN")
        finally:
            sidecar.close()

    def test_invalid_probe_verdict_becomes_unknown(self):
        sidecar, port = _with_sidecar(
            self, {"postgres": _probe("MOSTLY_FINE")}
        )
        try:
            code, body, _ = get_json(port, "/health/postgres")
            self.assertEqual(code, 503)
            self.assertEqual(body["status"], "UNKNOWN")
            self.assertTrue(body["reasonFa"].strip())
        finally:
            sidecar.close()

    def test_exploding_probe_becomes_unknown_not_crash(self):
        sidecar, port = _with_sidecar(self, {"redis": _raised})
        try:
            code, body, _ = get_json(port, "/health/redis")
            self.assertEqual(code, 503)
            self.assertEqual(body["status"], "UNKNOWN")
            self.assertTrue(body["reasonFa"].strip())
        finally:
            sidecar.close()


class TestIndexAndRouting(_SidecarCase):
    def test_index_lists_every_surface_and_worst_overall(self):
        probes = {
            "postgres": _probe("HEALTHY"),
            "redis": _probe("HEALTHY"),
            "n8n": _probe("DEGRADED", "کند بود."),
            "dokploy": _probe("UNKNOWN", "پیکربندی نشده."),
            "walrus": _probe("UNKNOWN", "PLANNED."),
        }
        sidecar, port = _with_sidecar(self, probes)
        try:
            code, body, _ = get_json(port, "/health")
            self.assertEqual(code, 503)  # UNKNOWN outranks DEGRADED
            self.assertEqual(sorted(body["surfaces"]), sorted(probes))
            self.assertEqual(body["overall"], "UNKNOWN")
            self.assertEqual(body["surfaces"]["postgres"]["status"], "HEALTHY")
        finally:
            sidecar.close()

    def test_all_healthy_index_is_200(self):
        ok = {key: _probe("HEALTHY") for key in ("postgres", "redis")}
        sidecar, port = _with_sidecar(self, ok)
        try:
            code, body, _ = get_json(port, "/health")
            self.assertEqual(code, 200)
            self.assertEqual(body["overall"], "HEALTHY")
        finally:
            sidecar.close()

    def test_unknown_paths_are_404(self):
        self.assertEqual(get(self.port, "/nope")[0], 404)
        self.assertEqual(get(self.port, "/health/nope")[0], 404)

    def test_read_only_surface_rejects_writes(self):
        self.assertEqual(
            get(self.port, "/health/postgres", method="POST")[0], 501
        )
        self.assertEqual(
            get(self.port, "/health/postgres", method="DELETE")[0], 501
        )


class TestRedaction(_SidecarCase):
    def test_credential_keys_are_marked_and_secrets_absent(self):
        sidecar, port = _with_sidecar(
            self,
            {
                "postgres": _probe(
                    "HEALTHY",
                    "",
                    metrics={
                        "connections": 3,
                        "password": "hunter2",
                        "api_key": "sk-live-123",
                        "authorization": "Bearer abc",
                    },
                )
            },
        )
        try:
            _, body, raw = get_json(port, "/health/postgres")
            self.assertNotIn("hunter2", raw)
            self.assertNotIn("sk-live-123", raw)
            self.assertNotIn("Bearer abc", raw)
            metrics = body["metrics"]
            self.assertEqual(metrics["connections"], 3)
            self.assertNotEqual(metrics["password"], "hunter2")
            self.assertNotEqual(metrics["api_key"], "sk-live-123")
        finally:
            sidecar.close()


class TestPostgresPlumbing(unittest.TestCase):
    """The psql channel must receive the canonical connection env.

    Regression guard: an earlier revision computed `db_env()` but dropped it
    on the way to `subprocess.run`, so psql fell back to an ambient default
    connection and the surface reported DOWN while the database was up.
    """

    def test_pg_read_passes_canonical_connection_env(self):
        from services import health_sidecar as hs

        captured = {}

        class _Completed:
            returncode = 0
            stdout = "1\n"

        def fake_run(argv, **kwargs):
            captured["argv"] = argv
            captured["env"] = kwargs.get("env")
            return _Completed()

        with unittest.mock.patch.object(hs.subprocess, "run",
                                        side_effect=fake_run):
            value, failure = hs._pg_read("SELECT 1;")

        self.assertEqual((value, failure), ("1", None))
        env = captured["env"]
        self.assertIsNotNone(env)
        self.assertEqual(env["PGHOST"], "127.0.0.1")
        self.assertEqual(env["PGPORT"], "55432")
        self.assertTrue(env.get("PGPASSWORD"))

    def test_container_fallback_when_host_psql_missing(self):
        from services import health_sidecar as hs

        argv_seen = []

        class _Completed:
            returncode = 0
            stdout = "1\n"

        def fake_run(argv, **kwargs):
            argv_seen.append(argv)
            if argv[0] == "psql":
                raise FileNotFoundError("psql not on PATH")
            return _Completed()

        with unittest.mock.patch.object(hs.subprocess, "run",
                                        side_effect=fake_run):
            value, failure = hs._pg_read("SELECT 1;")

        self.assertEqual((value, failure), ("1", None))
        self.assertEqual(argv_seen[0][0], "psql")
        self.assertEqual(argv_seen[1][:2], ["docker", "exec"])


class TestUnconfiguredDefaults(unittest.TestCase):
    def test_dokploy_and_walrus_default_to_unknown_when_unconfigured(self):
        without_urls = {
            key: value
            for key, value in os.environ.items()
            if key not in ("LOCAL_DOKPLOY_HEALTH_URL", "LOCAL_WALRUS_HEALTH_URL")
        }
        with unittest.mock.patch.dict(os.environ, without_urls, clear=True):
            for probe, needle in ((probe_dokploy, "Dokploy"),
                                  (probe_walrus, "Walrus")):
                outcome = probe()
                self.assertEqual(outcome["status"], "UNKNOWN")
                self.assertTrue(outcome["reasonFa"].strip())
                self.assertIn(needle, outcome["reasonFa"])


if __name__ == "__main__":
    unittest.main()

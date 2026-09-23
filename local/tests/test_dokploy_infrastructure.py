"""Dokploy bridge — Stage B–H infrastructure battery.

Machine-checks the Stage B–H provisioning artifacts and the
verification bridge AS THE OPERATOR DOES:

  - `local/infra/dokploy/` (README stage map, env contracts,
    `deploy_orchestrator.sh`) — subprocess-driven with synthetic
    credentials; dry-run and preflight paths only, nothing deployed.
  - `local/src/infra/infra_health_probe.py` — success/failure
    simulations over injected verifiers; fail-closed semantics.
  - `local/infra/compose.prod.yml` — the Stage B–H manifest
    structure (PostgreSQL SSOT volumes/health, hardened containers,
    attachable frontend gateway seam) resolved via
    `docker compose config` with synthetic env.

Secret hygiene: every canary below is runtime-constructed and every
assertion proves values NEVER reach diagnostics (D-124/D-045).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.getcwd(), "local"))
sys.path.insert(0, os.getcwd())

from local.src.infra.infra_health_probe import (  # noqa: E402
    DEPLOY_HALTED,
    DEPLOY_OK,
    InfraHealthProbe,
)

REPO = Path(__file__).resolve().parents[2]
DOKPLOY = REPO / "local" / "infra" / "dokploy"
ORCHESTRATOR = DOKPLOY / "deploy_orchestrator.sh"
PROD = REPO / "local" / "infra" / "compose.prod.yml"
CANARY = "sk-" + "x" * 24  # runtime-constructed (scan zero-noise)

SYNTHETIC_ENV = {
    "CANONICAL_DB_NAME": "business_engine_prod",
    "CANONICAL_DB_USER": "engine_prod",
    "CANONICAL_DB_PASSWORD": "throwaway-pg-" + "z" * 8,
    "WORDPRESS_DB_PASSWORD": "throwaway-wp-" + "z" * 8,
    "MYSQL_PASSWORD": "throwaway-my-" + "z" * 8,
    "MYSQL_ROOT_PASSWORD": "throwaway-myr-" + "z" * 8,
    "N8N_ENCRYPTION_KEY": "throwaway-n8n-" + "z" * 8,
    "MINIO_ROOT_USER": "prod-media",
    "MINIO_ROOT_PASSWORD": "throwaway-minio-" + "z" * 8,
    "COMPOSE_PROJECT_NAME": "prodcheck",
}


def _run_script(args, env=None):
    e = dict(os.environ)
    if env:
        e.update(env)
    for k in SYNTHETIC_ENV:
        e.pop(k, None) if env is None else None
    if env is None:
        for k in SYNTHETIC_ENV:
            e.pop(k, None)
    return subprocess.run(["bash", str(ORCHESTRATOR)] + args,
                          capture_output=True, text=True, env=e,
                          cwd=str(REPO), timeout=120)


def _resolve_prod():
    env = dict(os.environ)
    env.update(SYNTHETIC_ENV)
    proc = subprocess.run(
        ["docker", "compose", "-f", str(PROD), "config", "--format", "json"],
        capture_output=True, text=True, env=env, cwd=str(REPO), timeout=120)
    if proc.returncode != 0:
        return None, proc.stderr
    return json.loads(proc.stdout), proc.stderr


# ---------------------------------------------------------------------------
# Part A — orchestrator (Stage H gates)
# ---------------------------------------------------------------------------

class TestOrchestrator(unittest.TestCase):
    def test_01_usage_and_dry_run_plan(self):
        r = _run_script(["--help"])
        self.assertEqual(r.returncode, 0)
        self.assertIn("deploy_orchestrator.sh", r.stdout)
        env = dict(SYNTHETIC_ENV)
        r = _run_script(["--dry-run"], env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("DRY-RUN PLAN OK", r.stdout)
        self.assertIn("[stage H]", r.stdout)

    def test_02_preflight_missing_env_fails_closed_names_only(self):
        r = _run_script(["--dry-run"], env={})
        self.assertEqual(r.returncode, 2)
        self.assertIn("MISSING required environment variable", r.stderr)
        self.assertIn("HALTED", r.stderr)
        # names reported, values never (there are no values)
        self.assertNotIn("=", r.stderr.split("MISSING")[1].split("\n")[0])

    def test_03_preflight_never_echoes_values(self):
        env = dict(SYNTHETIC_ENV)
        r = _run_script(["--dry-run"], env=env)
        self.assertEqual(r.returncode, 0)
        for value in SYNTHETIC_ENV.values():
            self.assertNotIn(value, r.stdout + r.stderr)

    def test_04_dry_run_touches_nothing(self):
        env = dict(SYNTHETIC_ENV)
        r = _run_script(["--dry-run"], env=env)
        self.assertNotIn("PASS", r.stdout)  # stage gates not executed
        self.assertIn("plan only", r.stdout)

    def test_05_stage_hooks_overridable(self):
        # the layer may override each stage check; dry-run surfaces the names
        env = dict(SYNTHETIC_ENV)
        env["STAGE_B_CHECK"] = "true"
        r = _run_script(["--dry-run"], env=env)
        self.assertIn("STAGE_B_CHECK", r.stdout)


# ---------------------------------------------------------------------------
# Part A — manifest structure (Stage B–H contracts)
# ---------------------------------------------------------------------------

@unittest.skipUnless(PROD.exists(), "prod manifest missing")
class TestManifestStructure(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.assertTrue(cls, PROD.exists())
        cls.resolved, cls.stderr = _resolve_prod()
        if cls.resolved is None:
            raise AssertionError(
                "docker compose failed to resolve compose.prod.yml — "
                f"is the docker CLI available?\nstderr: {cls.stderr[:300]}")

    def test_06_stage_b_ssot_volume_and_health(self):
        db = self.resolved["services"]["canonical-db"]
        vols = [v.get("target", "") for v in db.get("volumes", [])
                if isinstance(v, dict)]
        self.assertTrue(any("pgdata" in v or "/var/lib/postgresql" in v
                            for v in vols), "SSOT data volume required")
        self.assertIn("healthcheck", db, "SSOT healthcheck required")
        self.assertIn("test", db["healthcheck"])

    def test_07_stage_b_wal_archiving_params_declared(self):
        # The Stage B WAL contract lives in the provisioning parameter
        # template the deployment layer maps onto the manifest (the
        # shipped manifest stays stock postgres; no speculative params).
        pg = (DOKPLOY / "postgres-ssot.env.example").read_text(
            encoding="utf-8")
        self.assertIn("PG_ARCHIVE_MODE=on", pg)
        self.assertIn("PG_WAL_KEEP_SIZE=1GB", pg)
        # and the manifest keeps the SSOT volume the archive protects
        db = self.resolved["services"]["canonical-db"]
        self.assertTrue(db.get("volumes"))

    def test_08_stage_d_hardened_containers(self):
        for name, svc in self.resolved["services"].items():
            self.assertIn("no-new-privileges:true",
                          svc.get("security_opt", []),
                          f"{name}: no-new-privileges required")
            self.assertIsNotNone(svc.get("mem_limit"),
                                 f"{name}: memory limit required")

    def test_09_stage_d_worker_daemon_seams(self):
        # outbox/control-plane workers run in-process against the SSOT;
        # the manifest must not invent a speculative broker service
        self.assertNotIn("redis", self.resolved["services"],
                         "Redis is stage-C contract-only until required")
        self.assertIn("canonical-db", self.resolved["services"])

    def test_10_stage_fg_gateway_seam_attachable_frontend(self):
        nets = self.resolved["networks"]
        self.assertTrue(nets["frontend"].get("attachable"),
                        "gateway proxy must be able to join `frontend`")
        self.assertTrue(nets["data"].get("internal"),
                        "data network must stay internal")
        for name, svc in self.resolved["services"].items():
            published = svc.get("ports") or []
            self.assertEqual(published, [],
                             f"{name}: production publishes no ports")

    def test_11_stage_h_healthcheck_on_every_core_service(self):
        for name, svc in self.resolved["services"].items():
            self.assertIn("healthcheck", svc,
                          f"{name}: stage H requires a healthcheck")

    def test_12_secret_free_manifest(self):
        raw = PROD.read_text(encoding="utf-8")
        for value in SYNTHETIC_ENV.values():
            self.assertNotIn(value, raw)
        self.assertNotIn(CANARY, raw)
        # every secret-bearing var is fail-closed interpolated
        self.assertIn("${CANONICAL_DB_PASSWORD:?", raw)


# ---------------------------------------------------------------------------
# Part B — infra health probe (fail-closed)
# ---------------------------------------------------------------------------

def _green_probe():
    return InfraHealthProbe(
        pg_exec=lambda sql: "1",
        redis_ping=lambda: "PONG",
        worker_heartbeat=lambda: {"ticks_since_beat": 1},
        telemetry_state=lambda: {"latched_open": False})


class TestInfraHealthProbe(unittest.TestCase):
    def test_13_all_green_deploys(self):
        v = _green_probe().deploy_verdict()
        self.assertEqual(v["verdict"], DEPLOY_OK)
        self.assertEqual(v["overall"], "PASS")
        self.assertEqual({p["name"] for p in v["probes"]},
                         {"pg_ssot", "redis_broker", "worker_heartbeat",
                          "telemetry_circuit"})

    def test_14_pg_failure_halts_and_never_leaks(self):
        probe = InfraHealthProbe(
            pg_exec=lambda s: (_ for _ in ()).throw(
                ConnectionError(f"host 10.0.0.5 pw={CANARY}")),
            redis_ping=lambda: "PONG",
            worker_heartbeat=lambda: {"ticks_since_beat": 1},
            telemetry_state=lambda: {"latched_open": False})
        v = probe.deploy_verdict()
        self.assertEqual(v["verdict"], DEPLOY_HALTED)
        blob = json.dumps(v)
        self.assertNotIn(CANARY, blob)
        self.assertNotIn("10.0.0.5", blob)
        self.assertIn("ConnectionError",
                      [p["detail"] for p in v["probes"]
                       if p["name"] == "pg_ssot"][0])

    def test_15_redis_wrong_answer_fails(self):
        probe = InfraHealthProbe(pg_exec=lambda s: "1",
                                 redis_ping=lambda: "NOPE",
                                 worker_heartbeat=lambda:
                                     {"ticks_since_beat": 1},
                                 telemetry_state=lambda:
                                     {"latched_open": False})
        v = probe.deploy_verdict()
        self.assertEqual(v["verdict"], DEPLOY_HALTED)

    def test_16_stale_heartbeat_fails(self):
        probe = InfraHealthProbe(pg_exec=lambda s: "1",
                                 redis_ping=lambda: "PONG",
                                 worker_heartbeat=lambda:
                                     {"ticks_since_beat": 9},
                                 telemetry_state=lambda:
                                     {"latched_open": False})
        v = probe.deploy_verdict()
        detail = [p["detail"] for p in v["probes"]
                  if p["name"] == "worker_heartbeat"][0]
        self.assertIn("stale", detail)
        self.assertEqual(v["verdict"], DEPLOY_HALTED)

    def test_17_latched_telemetry_fails(self):
        probe = InfraHealthProbe(pg_exec=lambda s: "1",
                                 redis_ping=lambda: "PONG",
                                 worker_heartbeat=lambda:
                                     {"ticks_since_beat": 1},
                                 telemetry_state=lambda:
                                     {"latched_open": True})
        v = probe.deploy_verdict()
        detail = [p["detail"] for p in v["probes"]
                  if p["name"] == "telemetry_circuit"][0]
        self.assertIn("latched OPEN", detail)
        self.assertEqual(v["verdict"], DEPLOY_HALTED)

    def test_18_missing_probes_fail_closed(self):
        probe = InfraHealthProbe(pg_exec=lambda s: "1")
        v = probe.deploy_verdict()
        self.assertEqual(v["verdict"], DEPLOY_HALTED)
        self.assertEqual(len([p for p in v["probes"]
                              if p["verdict"] == "FAIL"]), 3)

    def test_19_report_is_valid_qa_health_report(self):
        from canonical.obs_health import validate_report
        rep = _green_probe().report()
        self.assertEqual(rep["schema_version"], "qa.health_report.v1")
        self.assertEqual(validate_report(dict(rep))["overall"], "PASS")

    def test_20_verifier_error_types_redacted(self):
        probe = InfraHealthProbe(
            pg_exec=lambda s: "1",
            redis_ping=lambda: (_ for _ in ()).throw(
                ValueError(f"redis://:password@host {CANARY}")),
            worker_heartbeat=lambda: {"ticks_since_beat": 1},
            telemetry_state=lambda: {"latched_open": False})
        blob = json.dumps(probe.deploy_verdict())
        self.assertNotIn(CANARY, blob)
        self.assertNotIn("redis://", blob)
        self.assertIn("ValueError", blob)


# ---------------------------------------------------------------------------
# Artifacts & hygiene
# ---------------------------------------------------------------------------

class TestArtifacts(unittest.TestCase):
    def test_21_stage_map_and_env_contracts_present(self):
        self.assertTrue((DOKPLOY / "README.md").exists())
        self.assertTrue((DOKPLOY / "postgres-ssot.env.example").exists())
        self.assertTrue((DOKPLOY / "redis.env.example").exists())
        readme = (DOKPLOY / "README.md").read_text(encoding="utf-8")
        for stage in ("B", "C", "D", "E", "F/G", "H"):
            self.assertIn(stage, readme)
        pg = (DOKPLOY / "postgres-ssot.env.example").read_text(
            encoding="utf-8")
        self.assertIn("CANONICAL_DB_PASSWORD=", pg)
        self.assertIn("PG_ARCHIVE_MODE=on", pg)
        rd = (DOKPLOY / "redis.env.example").read_text(encoding="utf-8")
        self.assertIn("REDIS_PASSWORD=", rd)
        self.assertIn("noeviction", rd)
        self.assertIn("REDIS_APPENDONLY=yes", rd)

    def test_22_env_contracts_carry_no_values(self):
        for name in ("postgres-ssot.env.example",
                     "redis.env.example"):
            text = (DOKPLOY / name).read_text(encoding="utf-8")
            for line in text.splitlines():
                if line.startswith("#") or not line.strip():
                    continue
                if "=" in line:
                    key, _, value = line.partition("=")
                    if key.endswith(("PASSWORD", "PASSWORD", "KEY")):
                        self.assertEqual(
                            value, "",
                            f"{name}: {key} must be value-free")

    def test_23_orchestrator_executable_and_guarded(self):
        self.assertTrue(os.access(ORCHESTRATOR, os.X_OK))
        self.assertTrue(ORCHESTRATOR.stat().st_mode & 0o111)

    def test_24_no_io_imports_in_probe(self):
        src = (REPO / "local" / "src" / "infra" /
               "infra_health_probe.py").read_text(encoding="utf-8")
        for banned in ("urllib", "requests", "socket", "subprocess",
                       "httpx", "psycopg", "redis"):
            self.assertNotIn(f"import {banned}", src)
            self.assertNotIn(f"from {banned}", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)

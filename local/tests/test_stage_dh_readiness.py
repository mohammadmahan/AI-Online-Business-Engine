"""Stages D–H readiness — health/DR/exit drill artifacts (D-141, offline).

Stage D–H readiness deliverables are pinned here:

  - `local/scripts/validate_staging_health.py`: manifest mode asserts
    the health surface + probe plan; live mode is a READ-ONLY SSH
    drill (allowlist-pinned like the VPS probe) verifying container
    health, synthetic in-network probes, and the deployed-side
    isolation invariants (gateway-less data plane; frontend touches
    WordPress only).
  - `docs/runbooks/staging-disaster-recovery.md`: per-store backup
    and restoration DRILL procedures with the RPO/RTO checklist and
    the non-negotiable boundaries (upload ≠ evidence; decision ledger
    never destructively touched; restore preconditions).
  - `docs/runbooks/dokploy-exit-drill.md`: the zero-lock-in drill
    (I1–I5 invariants) proving plain-compose independence.
  - Manifest self-sufficiency for the exit drill: the staging
    manifest contains no deployment-layer-specific fields.
"""
import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HEALTH = REPO / "local" / "scripts" / "validate_staging_health.py"
DR_RUNBOOK = REPO / "docs" / "runbooks" / "staging-disaster-recovery.md"
EXIT_RUNBOOK = REPO / "docs" / "runbooks" / "dokploy-exit-drill.md"
EXIT_PLAN = REPO / "docs" / "runbooks" / "dokploy-exit-plan.md"
MANIFEST = REPO / "local" / "infra" / "compose.staging.yml"
BACKUP_POLICY = REPO / "docs" / "deployment" / "staging-volume-backup-policy.md"

sys.path.insert(0, str(HEALTH.parent))
import validate_staging_health as vsh  # noqa: E402


class TestHealthScriptManifestSurface(unittest.TestCase):

    def test_core_services_and_probes_complete(self):
        self.assertEqual(
            set(vsh.CORE_SERVICES),
            {"wordpress", "woodb", "canonical-db", "n8n", "media"},
        )
        self.assertEqual(set(vsh.PROBE_COMMANDS), set(vsh.CORE_SERVICES),
                         "every core service needs a synthetic probe")

    def test_probes_are_read_only(self):
        forbidden = ("INSERT", "UPDATE ", "DELETE", "DROP", "CREATE",
                     "shutdown", "stop", "rm ", "kill", "flushall",
                     "mysqladmin shutdown")
        for svc, probe in vsh.PROBE_COMMANDS.items():
            for bad in forbidden:
                self.assertNotIn(bad, probe.lower(),
                                 f"probe for {svc} must be read-only: {probe}")

    def test_manifest_mode_runs_clean(self):
        proc = subprocess_run([sys.executable, str(HEALTH)])
        self.assertEqual(proc.returncode, 0,
                         f"manifest mode must exit 0:\n{proc.stdout[-400:]}")
        self.assertIn("MANIFEST VALID", proc.stdout)
        for svc in vsh.CORE_SERVICES:
            self.assertIn(svc, proc.stdout)

    def test_live_mode_requires_host_and_user(self):
        proc = subprocess_run([sys.executable, str(HEALTH), "--live"])
        self.assertEqual(proc.returncode, 2,
                         "live mode without host/user is an env error")


def subprocess_run(argv):
    import subprocess
    return subprocess.run(argv, capture_output=True, text=True,
                          cwd=str(REPO))


class TestHealthScriptLiveReadOnly(unittest.TestCase):
    """The live drill must never mutate: allowlist-pinned SSH payloads."""

    FORBIDDEN = ("apt ", "install", "docker stop", "docker rm",
                 "docker compose down", "docker compose stop",
                 "docker compose up", "docker volume rm", "ufw ",
                 "systemctl", "reboot", ">", "tee ", "sed -i", "rm ")

    def test_all_ssh_payloads_read_only(self):
        text = HEALTH.read_text(encoding="utf-8")
        payloads = re.findall(r'run\(f?"([^"\\]+)"', text)
        self.assertGreater(len(payloads), 3,
                           "test must find the live-mode SSH payloads")
        for p in payloads:
            for bad in self.FORBIDDEN:
                self.assertNotIn(bad, p,
                                 f"live SSH payload {p!r} is mutating")
        # The only exec usage must be the read-only synthetic probes.
        for svc, probe in vsh.PROBE_COMMANDS.items():
            self.assertIn(probe, text)


class TestDRRunbook(unittest.TestCase):

    def test_all_four_stores_covered(self):
        text = DR_RUNBOOK.read_text(encoding="utf-8")
        for store in ("PostgreSQL", "MySQL", "MinIO", "n8n"):
            self.assertIn(store, text, f"DR runbook must cover {store}")
        for primitive in ("pg_dump", "mysqldump", "mc mirror", "tar czf"):
            self.assertIn(primitive, text)

    def test_integrity_gate_and_boundaries(self):
        text = DR_RUNBOOK.read_text(encoding="utf-8")
        # The acceptance is integrity verification, not upload success.
        self.assertIn("decision_ledger_drill.py --consistency-only", text)
        self.assertIn("validate_staging_health.py --live", text)
        self.assertIn("A drill WITHOUT step 7 evidence is a FAILED drill",
                      text)
        self.assertIn("supplement, never replace", text)  # supplement-only
        # The decision ledger is never destructively touched in a restore:
        # the boundary statement AND the stop-conditions clause.
        self.assertIn("append-only", text)
        self.assertIn("delete, truncate, or compact it", text)
        self.assertIn("decision ledger destructively", text)
        # Official restore preconditions documented.
        self.assertIn("destination volume ABSENT", text)
        self.assertIn("containers stopped", text)

    def test_rpo_rto_checklist_present(self):
        text = DR_RUNBOOK.read_text(encoding="utf-8")
        self.assertIn("RPO", text)
        self.assertIn("RTO", text)
        for target in ("≤ 6 h", "≤ 24 h", "≤ 2 h", "≤ 4 h"):
            self.assertIn(target, text)
        # Consistency with the policy proposals.
        policy = BACKUP_POLICY.read_text(encoding="utf-8")
        self.assertIn("canonical data ≤ 6 h", policy)
        self.assertIn("canonical store ≤ 2 h", policy)


class TestExitDrillRunbook(unittest.TestCase):

    def test_five_invariants_declared(self):
        text = EXIT_RUNBOOK.read_text(encoding="utf-8")
        for inv in ("I1", "I2", "I3", "I4", "I5"):
            self.assertRegex(text, rf"\b{inv}\b")
        self.assertIn("docker compose -f compose.staging.yml up", text)

    def test_control_plane_removal_is_scoped(self):
        """Only Dokploy control-plane containers are removed — never the
        compose project or volumes."""
        text = EXIT_RUNBOOK.read_text(encoding="utf-8")
        self.assertIn("NOT the compose project containers", text)
        self.assertIn("Leave application volumes", text)
        self.assertIn("grep -Ei 'dokploy|traefik'", text)

    def test_links_to_exit_plan_and_health_drill(self):
        text = EXIT_RUNBOOK.read_text(encoding="utf-8")
        self.assertIn("dokploy-exit-plan.md", text)
        self.assertIn("validate_staging_health.py --live", text)
        self.assertIn("verification log", text)


class TestManifestSelfSufficiency(unittest.TestCase):
    """Exit-drill invariant I1, enforced at the source: the staging
    manifest must be free of deployment-layer-specific fields."""

    def test_no_dokploy_labels_or_extensions(self):
        # Scan NON-COMMENT lines only: comments may reference the plan
        # document; the invariant is about compose FIELDS.
        lines = [
            ln for ln in MANIFEST.read_text(encoding="utf-8").splitlines()
            if not ln.lstrip().startswith("#")
        ]
        text = "\n".join(lines).lower()
        for marker in ("dokploy", "com.docker.compose",
                       "traefik.enable", "swarm", "deploy:"):
            self.assertNotIn(marker, text,
                             f"manifest must stay layer-neutral: {marker}")

    def test_plain_compose_semantics_only(self):
        text = MANIFEST.read_text(encoding="utf-8")
        for key in ("image:", "healthcheck:", "volumes:", "networks:"):
            self.assertIn(key, text)
        # Standalone (not an overlay) — documented Stage B decision.
        self.assertNotIn("extends:", text)


if __name__ == "__main__":
    unittest.main()

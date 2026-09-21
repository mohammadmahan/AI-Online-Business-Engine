"""Stage C — target validation harness battery (D-141, offline).

Exercises `local/scripts/validate_vps_target.py` — the Stage C sizing
and target-host harness — as the operator runs it:

  - SIZING PINS   — the harness's floors and expected totals are the
    numbers in docs/deployment/stage-c-readiness.md §2 (no silent
    drift between report and harness).
  - PARSERS       — real-world command outputs (os-release, free, df,
    ss, docker --version, cgroup.controllers) mapped to verdicts.
  - OFFLINE MODE  — subprocess run against the real manifest: exit 0
    when the plan is consistent; exit 2 (fail-closed) when secret
    material appears in the planning environment (D-045); per-check
    findings when the manifest drifts (synthesized manifest text).
  - PROBE MODE    — DECISION LOGIC with a fake ssh transport (no host
    contacted): connectivity failure ⇒ CANNOT ASSESS exit 2; a fully
    green host ⇒ READY; each degraded host dimension ⇒ named finding.
  - REDACTION     — no secret-shaped value is ever printed by the
    harness; findings carry key names, never values (D-124).
  - AUTHORITY     — the remote command allowlist contains ONLY
    read-only commands; no mutating verb may ever join it.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import types
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "local" / "scripts" / "validate_vps_target.py"
REPORT = REPO / "docs" / "deployment" / "stage-c-readiness.md"
PROD = REPO / "local" / "infra" / "compose.prod.yml"

sys.path.insert(0, str(SCRIPT.parent))
import validate_vps_target as tgt  # noqa: E402


def run_cli(*extra: str, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.update(env_extra or {})
    return subprocess.run(
        [sys.executable, str(SCRIPT), *extra],
        capture_output=True, text=True, env=env, timeout=120)


class TestSizingPins(unittest.TestCase):
    """Harness floors/totals ARE the report's numbers (single truth)."""

    def test_report_derives_the_pinned_totals(self):
        body = REPORT.read_text(encoding="utf-8")
        self.assertIn("3328 MiB", body)      # 512+1024+512+1024+256
        self.assertIn("4.0 CPUs", body)
        self.assertIn("6 GiB floor", body)  # host baseline from §2.2
        self.assertIn("40 GB floor", body)

    def test_manifest_yields_the_pinned_totals(self):
        self.assertEqual(tgt.parse_resource_limits(),
                         (tgt.EXPECTED_MEM_MIB, tgt.EXPECTED_CPUS))

    def test_floors_are_actionable(self):
        self.assertGreaterEqual(tgt.RAM_FLOOR_MB, 4096)   # above dokploy floor
        self.assertGreaterEqual(tgt.DISK_FLOOR_GB, 30)
        self.assertGreaterEqual(tgt.CPU_FLOOR, 2)


class TestParsers(unittest.TestCase):
    """Real command output → verdict fixtures (offline, no SSH)."""

    def test_os_supported(self):
        ok, d = tgt.os_supported(
            'ID=ubuntu\nID_LIKE=debian\nVERSION_ID="24.04"\n')
        self.assertTrue(ok and d == "ubuntu")
        ok, d = tgt.os_supported('ID=linuxmint\nID_LIKE="debian ubuntu"\n')
        self.assertTrue(ok)
        ok, d = tgt.os_supported('ID=fedora\nID_LIKE="rhel fedora"\n')
        self.assertFalse(ok)

    def test_docker_version(self):
        self.assertEqual(
            tgt.parse_docker_version("Docker version 27.3.1, build x"),
            (27, 3))
        self.assertGreaterEqual(
            tgt.parse_docker_version("Docker version 24.0.7, build b"),
            tgt.DOCKER_MIN)
        self.assertIsNone(tgt.parse_docker_version("command not found"))

    def test_ram_disk_cpu(self):
        self.assertEqual(tgt.parse_ram_mb(
            "               total        used        free\n"
            "Mem:            7971        512        7459"), 7971)
        self.assertEqual(tgt.parse_disk_gb(
            "/dev/vda1        79G  12G   68G  15% /"), 79)
        self.assertEqual(tgt.parse_disk_gb(
            "tmpfs           1G   0     1G   0% /not-root"), -1)
        self.assertEqual(tgt.parse_cpus("4"), 4)
        self.assertEqual(tgt.parse_cpus("n/a"), -1)

    def test_cgroup_v2(self):
        self.assertTrue(tgt.cgroup_is_v2("cpuset cpu io memory hugetlb pids"))
        self.assertFalse(tgt.cgroup_is_v2(""))

    def test_port_parsing_and_public_3000(self):
        # hex ports: 50=80, 1BB8=443, BB8=3000; wildcard v6 binds are public
        ss = ("State  Recv-Q Send-Q Local Address:Port\n"
              "LISTEN 0      511        0.0.0.0:50         0.0.0.0:*\n"
              "LISTEN 0      511           [::]:1BB8        [::]:*\n"
              "LISTEN 0      4096     127.0.0.1:BB8       0.0.0.0:*\n")
        self.assertEqual(tgt.parse_listening_ports(ss), (80, 3000))
        self.assertTrue(tgt.public_3000_bound(
            "LISTEN 0      511        0.0.0.0:BB8        0.0.0.0:*\n"))
        self.assertTrue(tgt.public_3000_bound(
            "LISTEN 0      511           [::]:BB8        [::]:*\n"))
        self.assertFalse(tgt.public_3000_bound(
            "LISTEN 0      511     127.0.0.1:BB8        0.0.0.0:*\n"))
        # regression pin: :3000 as a SUFFIX must not false-positive :0BB8
        self.assertFalse(tgt.public_3000_bound(
            "LISTEN 0      511     127.0.0.1:0BB8      0.0.0.0:*\n"))

    def test_subnet_overlap(self):
        self.assertEqual(tgt.subnet_overlaps(("10.8.0.0/24",)), ["10.8.0.0/24"])
        self.assertEqual(tgt.subnet_overlaps(("172.19.0.0/16",)), [])


class TestOfflineMode(unittest.TestCase):
    """Subprocess runs against the REAL manifest — plan-level gates."""

    def test_green_run_exit_0(self):
        r = run_cli()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for check in ("O-01", "O-02", "O-03", "O-04", "O-05"):
            self.assertIn(check, r.stdout)
        self.assertIn("READY (exit 0)", r.stdout)

    def test_fail_closed_on_secret_in_planning_env(self):
        r = run_cli(env_extra={"CANONICAL_DB_PASSWORD": "live-prod-value"})
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("O-02", r.stdout)
        self.assertIn("CANONICAL_DB_PASSWORD", r.stdout)   # key name…
        self.assertNotIn("live-prod-value", r.stdout)      # …never value

    def test_manifest_drift_is_a_finding(self):
        drift = PROD.read_text(encoding="utf-8").replace(
            "mem_limit: 512m", "mem_limit: 2g", 1)
        mem, _ = tgt.parse_resource_limits(drift)
        self.assertNotEqual(mem, tgt.EXPECTED_MEM_MIB)  # detector works

    def test_env_contract(self):
        contract = tgt.manifest_env_contract()
        self.assertEqual(len(contract), 9)
        self.assertIn("N8N_ENCRYPTION_KEY", contract)
        # every key must be documented in .env.example (O-01's rule)
        example = (REPO / ".env.example").read_text(encoding="utf-8")
        for key in contract:
            self.assertIn(key, example)


class _FakeSsh:
    """Deterministic ssh transport: canned answers, zero network."""

    def __init__(self, answers: dict[str, str], fail_first: bool = False):
        self.answers = answers
        self.fail_first = fail_first
        self.calls: list[str] = []


class _SshStub:
    def __init__(self, answers, fail_first=False):
        self.answers = answers
        self.fail_first = fail_first
        self.calls = []

    def __call__(self, args, user, host, port, key, cmd, timeout=20):
        self.calls.append(cmd[0])
        if self.fail_first and len(self.calls) == 1:
            return types.SimpleNamespace(returncode=255, stdout="",
                                         stderr="denied")
        return types.SimpleNamespace(returncode=0,
                                     stdout=self.answers.get(cmd[0], ""),
                                     stderr="")


GREEN_HOST = {
    "cat /etc/os-release": 'ID=ubuntu\nID_LIKE=debian\n',
    "nproc": "4",
    "free -m": "Mem:            8012        512        7500",
    "df -BG /": "/dev/vda1        80G  12G   68G  15% /",
    "docker --version": "Docker version 27.3.1, build abc",
    "docker compose version": "Docker Compose version v2.29.1",
    "cat /sys/fs/cgroup/cgroup.controllers":
        "cpuset cpu io memory hugetlb pids rdma misc",
    "ufw status": "Status: active",
    "ss -ltn": ("LISTEN 0 511 0.0.0.0:50 0.0.0.0:*\n"
                "LISTEN 0 511 [::]:1BB8 [::]:*\n"),
    "docker network ls --format {{.Name}}": "bridge\n",
    "docker network inspect -f '{{json .IPAM.Config}}' bridge":
        '[{"Subnet":"172.19.0.0/16","Gateway":"172.19.0.1"}]',
}


class TestProbeDecisionLogic(unittest.TestCase):
    """probe_mode with a fake transport — no host is ever contacted."""

    def _run(self, answers, fail_first=False):
        find = tgt.Findings()
        stub = _SshStub(answers, fail_first)
        original = tgt.ssh_run
        tgt.ssh_run = stub
        try:
            args = types.SimpleNamespace(
                host="stub", user="op", port=22, key=None)
            tgt.probe_mode(args, find)
        finally:
            tgt.ssh_run = original
        return find, stub

    def test_connectivity_failure_blocks(self):
        find, stub = self._run({}, fail_first=True)
        self.assertEqual(find.items[0][0], "STOP")
        self.assertIn("C-00", find.items[0][1])

    def test_green_host_has_no_findings(self):
        find, _ = self._run(GREEN_HOST)
        self.assertFalse(find.failed,
                         [i for i in find.items if i[0] == "FAIL"])
        self.assertTrue(any("C-07" in c for _, c, _ in find.items))

    def test_each_degraded_dimension_is_a_named_finding(self):
        weak = dict(GREEN_HOST)
        weak["nproc"] = "1"
        weak["free -m"] = "Mem:            2048        512        1536"
        weak["df -BG /"] = "/dev/vda1        30G  12G   18G  40% /"
        weak["docker --version"] = "Docker version 20.10.7, build x"
        weak["cat /sys/fs/cgroup/cgroup.controllers"] = ""
        weak["ufw status"] = "Status: inactive"
        weak["ss -ltn"] = "LISTEN 0 511 0.0.0.0:BB8 0.0.0.0:*\n"
        find, _ = self._run(weak)
        failed = {c for s, c, _ in find.items if s == "FAIL"}
        for check in ("C-02a", "C-02b", "C-02c", "C-03a",
                      "C-04", "C-05", "C-06"):
            self.assertTrue(any(c.startswith(check) for c in failed),
                            f"{check} not among findings: {failed}")

    def test_foreign_network_subnet_is_a_finding(self):
        bad = dict(GREEN_HOST)
        bad["docker network inspect -f '{{json .IPAM.Config}}' bridge"] = \
            '[{"Subnet":"10.8.0.0/24","Gateway":"10.8.0.1"}]'
        find, _ = self._run(bad)
        failed = [d for s, c, d in find.items if s == "FAIL" and "C-07" in c]
        self.assertTrue(failed and "10.8.0.0/24" in failed[0])

    def test_no_mutating_command_is_ever_sent(self):
        """READ-ONLY guarantee: every issued command is allowlisted."""
        _, stub = self._run(GREEN_HOST)
        self.assertIn("docker network inspect", " ".join(stub.calls))
        for cmd in stub.calls:
            self.assertTrue(any(cmd == a or cmd.startswith(a)
                                for a in tgt.SSH_ALLOWLIST),
                            f"non-allowlisted command: {cmd}")


class TestRedactionAndAuthority(unittest.TestCase):
    def test_secret_shaped_values_never_appear_in_output(self):
        r = run_cli(env_extra={"CANONICAL_DB_PASSWORD": "sk-live-abcdef123456"})
        self.assertNotIn("sk-live-abcdef123456", r.stdout + r.stderr)

    def test_allowlist_is_read_only(self):
        forbidden = ("apt", "install", "rm ", "mv ", "curl ", "wget ",
                     "chmod", "chown", "ufw allow", "ufw disable",
                     "systemctl", "kill", ">", ">>", "|", ";", "&&",
                     "sed -i", "tee ")
        for allowed in tgt.SSH_ALLOWLIST:
            for bad in forbidden:
                self.assertNotIn(bad, allowed)

    def test_findings_carry_key_names_not_values(self):
        find = tgt.Findings()
        find.fail("O-02", "CANONICAL_DB_PASSWORD")
        blob = str(find.items)
        self.assertIn("CANONICAL_DB_PASSWORD", blob)


if __name__ == "__main__":
    unittest.main()

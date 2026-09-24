"""Stage C — runbook-prerequisites validator battery (D-143, offline).

Exercises `local/infra/dokploy/stage_c_runbook_validator.py` — the
machine-enforced Stage C host-prerequisites gate — entirely with
INJECTED in-memory `HostFacts` (zero sockets, zero subprocess, zero
clock):

  VALID PATH     — a fully green host ⇒ READY with zero findings; the
                   report is byte-identical for identical inputs
                   (determinism) and binds an env fingerprint.
  PORT BOUNDARY  — pre-bound gateway ports (80/443) and PUBLIC
                   bindings of 3000/5432/6379 fail closed; loopback
                   bindings of internal ports degrade to warnings.
  ENV / FIREWALL — missing required planning variables, unpinned
                   installer refs, malformed domains, and invalid UFW
                   output (inactive, permissive default, rogue allow
                   rules, unparseable) are named findings.
  FAIL-CLOSED    — missing/unparseable host observations yield
                   CANNOT_ASSESS, never silent passes; the CLI fails
                   closed on a malformed facts file.
  REDACTION      — canary secrets injected into facts never appear in
                   any report rendering (D-124).
  AST AUDIT      — the validator imports NO network/socket/process
                   module anywhere (hermetic by construction).
"""
from __future__ import annotations

import ast
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
VALIDATOR = REPO / "local" / "infra" / "dokploy" / "stage_c_runbook_validator.py"
DOC = REPO / "docs" / "deployment" / "stage-c-host-prerequisites.md"

sys.path.insert(0, str(VALIDATOR.parent))
sys.path.insert(0, os.path.join(os.getcwd(), "local"))
sys.path.insert(0, os.getcwd())

import stage_c_runbook_validator as vld  # noqa: E402

CANARY = "sk-canaryvalue1234567890abcdef"


def facts_json(d: dict) -> str:
    return json.dumps(d)


def green_facts() -> vld.HostFacts:
    return vld.HostFacts(
        os_pretty_name="Ubuntu 24.04.1 LTS",
        kernel_release="6.8.0-45-generic",
        docker_version_text="Docker version 27.3.1, build abc123",
        docker_compose_ok=True,
        cgroup_controllers="cpuset cpu io memory hugetlb pids rdma misc",
        listening_lines=("LISTEN 0 4096 0.0.0.0:22 0.0.0.0:*",),
        ufw_status_text=(
            "Status: active\n"
            "Logging: on (low)\n"
            "Default: deny (incoming), allow (outgoing)\n"
            "To                         Action      From\n"
            "--                         ------      ----\n"
            "22/tcp                     ALLOW IN    Anywhere\n"
            "80/tcp                     ALLOW IN    Anywhere\n"
            "443/tcp                    ALLOW IN    Anywhere\n"
        ),
        env={
            "DOKPLOY_HOST_IP": "203.0.113.10",
            "DOKPLOY_SSH_USER": "ops",
            "DOKPLOY_INSTALLER_REF": "v2.11.4",
            "DOKPLOY_DOMAIN": "dokploy.example.net",
            "DOKPLOY_SECRET_REF": CANARY,  # extra planning var — never read out
        },
        attestations={
            "G1_HOST": "owner:approved:2026-09-23",
            "G2_INSTALLER": "owner:approved:2026-09-23",
            "G3_FIREWALL": "owner:approved:2026-09-23",
            "G4_SSH": "owner:approved:2026-09-23",
            "G5_DNS": "owner:approved:2026-09-23",
        },
    )


def render(report: vld.StageCReport) -> str:
    d = report.to_dict()
    return json.dumps(d, sort_keys=True)


class StageCValidatorBase(unittest.TestCase):
    def codes(self, report: vld.StageCReport):
        return {f.code for f in report.findings}


class TestValidConfiguration(StageCValidatorBase):
    def test_01_green_host_is_ready_with_zero_findings(self):
        r = vld.StageCRunbookValidator().validate(green_facts())
        self.assertEqual(r.verdict, "READY")
        self.assertEqual(r.counts["total"], 0)
        self.assertEqual(r.findings, ())

    def test_02_deterministic_byte_identical_reports(self):
        v = vld.StageCRunbookValidator()
        a = render(v.validate(green_facts()))
        b = render(v.validate(green_facts()))
        self.assertEqual(a, b)

    def test_03_env_fingerprint_binds_values_without_exposing_them(self):
        v = vld.StageCRunbookValidator()
        r1 = v.validate(green_facts())
        changed = green_facts()
        env = dict(changed.env)
        env["DOKPLOY_SECRET_REF"] = "rotated-value-000"
        r2 = v.validate(vld.HostFacts(**{**changed.__dict__, "env": env}))
        self.assertNotEqual(r1.env_fingerprint, r2.env_fingerprint)
        self.assertNotIn("rotated", render(r2))

    def test_04_cli_exit_zero_on_green_facts_file(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            fh.write(facts_json({
                "os_pretty_name": "Debian GNU/Linux 12 (bookworm)",
                "kernel_release": "6.1.0-25-amd64",
                "docker_version_text": "Docker version 24.0.9",
                "docker_compose_ok": True,
                "cgroup_controllers": "cpu io memory pids",
                "listening_lines": ["LISTEN 0 128 0.0.0.0:22 0.0.0.0:*"],
                "ufw_status_text": green_facts().ufw_status_text,
                "env": {"DOKPLOY_HOST_IP": "203.0.113.11",
                        "DOKPLOY_SSH_USER": "ops",
                        "DOKPLOY_INSTALLER_REF": "v2.11.4",
                        "DOKPLOY_DOMAIN": "dp.example.net"},
                "attestations": {g: "owner" for g in vld.REQUIRED_GATES},
            }))
            path = fh.name
        try:
            import subprocess
            proc = subprocess.run(
                [sys.executable, str(VALIDATOR), "--facts-file", path, "--json"],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertEqual(json.loads(proc.stdout)["verdict"], "READY")
            self.assertNotIn(CANARY, proc.stdout)
        finally:
            os.unlink(path)


class TestPortBoundaries(StageCValidatorBase):
    def test_05_gateway_ports_prebound_fails_closed(self):
        f = green_facts()
        r = vld.StageCRunbookValidator().validate(vld.HostFacts(**{
            **f.__dict__,
            "listening_lines": f.listening_lines + (
                "LISTEN 0 511 0.0.0.0:80 0.0.0.0:*",
                "LISTEN 0 511 [::]:443 [::]:*",
            ),
        }))
        self.assertIn("NOT_READY", r.verdict)
        self.assertIn("VC-06", self.codes(r))

    def test_06_public_internal_ports_fail_closed(self):
        f = green_facts()
        r = vld.StageCRunbookValidator().validate(vld.HostFacts(**{
            **f.__dict__,
            "listening_lines": f.listening_lines + (
                "LISTEN 0 4096 0.0.0.0:5432 0.0.0.0:*",
                "LISTEN 0 4096 0.0.0.0:6379 0.0.0.0:*",
                "LISTEN 0 128 *:3000 *:*",
            ),
        }))
        self.assertIn("NOT_READY", r.verdict)
        self.assertEqual(self.codes(r), {"VC-07"})

    def test_07_loopback_internal_ports_warn_only(self):
        f = green_facts()
        r = vld.StageCRunbookValidator().validate(vld.HostFacts(**{
            **f.__dict__,
            "listening_lines": f.listening_lines + (
                "LISTEN 0 4096 127.0.0.1:5432 0.0.0.0:*",
                "LISTEN 0 4096 127.0.0.1:6379 0.0.0.0:*",
            ),
        }))
        self.assertEqual(r.verdict, "READY")  # warnings are non-critical
        self.assertIn("VC-07", self.codes(r))
        self.assertEqual(r.counts["critical"], 0)
        self.assertEqual(r.counts["warning"], 2)


class TestEnvAndFirewallPolicy(StageCValidatorBase):
    def test_08_missing_required_env_variables(self):
        f = green_facts()
        env = dict(f.env)
        for k in ("DOKPLOY_SSH_USER", "DOKPLOY_INSTALLER_REF"):
            env.pop(k)
        env["DOKPLOY_HOST_IP"] = "   "  # blank == missing
        r = vld.StageCRunbookValidator().validate(vld.HostFacts(**{**f.__dict__, "env": env}))
        self.assertEqual(self.codes(r), {"VC-11"})

    def test_09_unpinned_installer_refs_refused(self):
        f = green_facts()
        for bad in ("latest", "main", "https://get.dokploy.com/install.sh"):
            env = dict(f.env)
            env["DOKPLOY_INSTALLER_REF"] = bad
            r = vld.StageCRunbookValidator().validate(
                vld.HostFacts(**{**f.__dict__, "env": env}))
            self.assertIn("VC-12", self.codes(r), bad)

    def test_10_malformed_domain_refused(self):
        f = green_facts()
        for bad in ("https://dp.example.net", "dp.example.net/x",
                    "ops:pw@dp.example.net", "dp.example.net backup"):
            env = dict(f.env)
            env["DOKPLOY_DOMAIN"] = bad
            r = vld.StageCRunbookValidator().validate(
                vld.HostFacts(**{**f.__dict__, "env": env}))
            self.assertIn("VC-13", self.codes(r), bad)

    def test_11_firewall_inactive_permissive_and_rogue_rules(self):
        f = green_facts()

        def with_ufw(text: str) -> vld.StageCReport:
            return vld.StageCRunbookValidator().validate(
                vld.HostFacts(**{**f.__dict__, "ufw_status_text": text}))

        r = with_ufw(green_facts().ufw_status_text.replace("Status: active",
                                                           "Status: inactive"))
        self.assertIn("VC-08", self.codes(r))

        r = with_ufw(green_facts().ufw_status_text.replace(
            "Default: deny (incoming)", "Default: allow (incoming)"))
        self.assertIn("VC-09", self.codes(r))

        r = with_ufw(green_facts().ufw_status_text.replace(
            "443/tcp                    ALLOW IN    Anywhere",
            "5432                       ALLOW IN    Anywhere"))
        self.assertIn("VC-10", self.codes(r))

        r = with_ufw("some completely unrelated text")
        self.assertIn("VC-08", self.codes(r))  # unparseable ⇒ fail closed


class TestFailClosed(StageCValidatorBase):
    def test_12_missing_observations_yield_cannot_assess(self):
        empty = vld.HostFacts()
        r = vld.StageCRunbookValidator().validate(empty)
        self.assertEqual(r.verdict, "CANNOT_ASSESS")
        self.assertTrue(self.codes(r) >= {"VC-01", "VC-02", "VC-03",
                                          "VC-05", "VC-06", "VC-08"})

    def test_13_cli_fails_closed_on_malformed_facts_file(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            fh.write("{definitely not json")
            path = fh.name
        try:
            import subprocess
            proc = subprocess.run(
                [sys.executable, str(VALIDATOR), "--facts-file", path],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(proc.returncode, 2)
            self.assertIn("cannot-assess", proc.stderr)
        finally:
            os.unlink(path)

    def test_14_cli_fails_closed_on_missing_facts_file(self):
        import subprocess
        proc = subprocess.run(
            [sys.executable, str(VALIDATOR), "--facts-file", "/nonexistent.json"],
            capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 2)


class TestRedaction(StageCValidatorBase):
    def test_15_canary_secret_never_reaches_findings(self):
        f = green_facts()
        env = dict(f.env)
        env["DOKPLOY_SSH_USER"] = f"ops token={CANARY} password=hunter2"
        # malformed domain WITH canary material
        env["DOKPLOY_DOMAIN"] = f"ops:shhh@dp.example.net"
        r = vld.StageCRunbookValidator().validate(
            vld.HostFacts(**{**f.__dict__, "env": env}))
        self.assertEqual(r.verdict, "NOT_READY")  # findings exist
        self.assertNotIn(CANARY, render(r))
        self.assertNotIn("hunter2", render(r))
        self.assertNotIn("shhh", render(r))

    def test_16_secret_shaped_finding_detail_is_scrubbed(self):
        detail = f"failed: postgres://ssot:{CANARY}@10.0.0.9:5432/main"
        finding = vld.Finding("VC-11", "critical", detail)
        # shipped deep_redact semantic: credential material is scrubbed,
        # the host portion is not secret material
        self.assertNotIn(CANARY, finding.detail)
        self.assertIn("[REDACTED]", finding.detail)
        self.assertNotIn("ssot:", finding.detail)


class TestASTAndDocContract(StageCValidatorBase):
    def test_17_no_network_or_process_imports_in_validator(self):
        tree = ast.parse(VALIDATOR.read_text(encoding="utf-8"))
        banned = {"socket", "ssl", "http", "urllib", "urllib3", "requests",
                  "ftplib", "telnetlib", "smtplib", "asyncio", "subprocess",
                  "multiprocessing", "paramiko", "docker"}
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imported.add(node.module.split(".")[0])
        self.assertEqual(imported & banned, set())

    def test_18_ssh_probe_ownership_preserved(self):
        """The SSH probe stays in validate_vps_target.py — this validator
        must NOT grow a second live-probe path (single probing surface).
        Banned tokens are code-shaped (docstring mentions of the sibling
        probe are documentation, not code)."""
        src = VALIDATOR.read_text(encoding="utf-8").lower()
        for banned in ("paramiko", "getaddrinfo", "create_connection",
                       "popen", "exec_command", "connect(",
                       "socket.socket"):
            self.assertNotIn(banned, src)


if __name__ == "__main__":
    unittest.main()

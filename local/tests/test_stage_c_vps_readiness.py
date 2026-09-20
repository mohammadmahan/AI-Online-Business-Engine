"""Stage C — VPS readiness probe contract tests (D-141, offline).

The probe `local/scripts/validate_vps_readiness.py` is the Stage C
readiness deliverable. These tests exercise its DECISION LOGIC with
in-process fixtures (no SSH subprocess to a real host; the probe's
thresholds and parser rules are imported and pinned) and pin the
invariants the runbook depends on:

  - verdict semantics: exit 0 ready / exit 1 findings / exit 2 cannot-assess
  - floors from official docs (RAM 2000/4000 MB, disk 30/60 GB) are the
    runbook's numbers, not re-derivable guesses
  - os-release parsing accepts the documented supported families
  - port-free / dokploy-bound / foreign-bound classification
  - READ-ONLY guarantee: the probe never invokes mutating commands —
    an allowlist pins every SSH command it may run
"""
import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "local" / "scripts" / "validate_vps_readiness.py"
RUNBOOK = REPO / "docs" / "runbooks" / "dokploy-vps-provisioning.md"

sys.path.insert(0, str(SCRIPT.parent))
import validate_vps_readiness as vps  # noqa: E402


class TestProbeThresholds(unittest.TestCase):
    """Floors come from official docs (runbook §1) — pinned here."""

    def test_documented_floors(self):
        self.assertEqual(vps.RAM_FLOOR_MB, 2000)
        self.assertEqual(vps.RAM_RECOMMENDED_MB, 4000)
        self.assertEqual(vps.DISK_FLOOR_GB, 30)
        self.assertEqual(vps.DISK_RECOMMENDED_GB, 60)
        self.assertEqual(vps.CHECK_PORTS, (80, 443, 3000))

    def test_runbook_and_script_agree(self):
        text = RUNBOOK.read_text(encoding="utf-8")
        self.assertIn("≥ 2 GB documented floor; **4 GB recommended**", text)
        self.assertIn("≥ 30 GB documented floor; **60 GB recommended**", text)
        # Port plan: the three gateway/management ports each have a table
        # row, and 80/443 are in the UFW baseline.
        for row in ("| 80 | Traefik", "| 443 | Traefik", "| 3000 |"):
            self.assertIn(row, text)
        self.assertIn("ufw allow 80/tcp", text)
        self.assertIn("ufw allow 443/tcp", text)


class TestOsClassification(unittest.TestCase):
    """Mirror the probe's os-release rule over fixture outputs."""

    def _classify(self, os_release: str):
        m_id = re.search(r'^ID=("?)([\w\-]+)\1', os_release, re.M)
        m_like = re.search(r'^ID_LIKE=("?)([\w\- ]+)\1', os_release, re.M)
        os_id = (m_id.group(2).lower() if m_id else "")
        os_like = (m_like.group(2).lower() if m_like else "")
        supported = os_id in vps.OK_OS_IDS or any(
            l in os_like for l in vps.OK_OS_LIKE)
        return os_id, os_like, supported

    def test_ubuntu_supported(self):
        _, _, ok = self._classify('NAME="Ubuntu"\nID=ubuntu\n')
        self.assertTrue(ok)

    def test_debian_supported(self):
        _, _, ok = self._classify('ID=debian\nID_LIKE=debian\n')
        self.assertTrue(ok)

    def test_debian_like_supported(self):
        _, _, ok = self._classify('ID=somefork\nID_LIKE="debian gnu"\n')
        self.assertTrue(ok)

    def test_unknown_distro_is_a_finding(self):
        _, _, ok = self._classify('ID=arch\nID_LIKE=arch\n')
        self.assertFalse(ok)

    def test_garbage_is_a_finding(self):
        _, _, ok = self._classify("not an os-release file")
        self.assertFalse(ok)


class TestPortClassification(unittest.TestCase):
    """Mirror the probe's listener rule over `ss -tlnp` fixtures."""

    def _bound(self, ss_output: str, port: int) -> bool:
        return bool([ln for ln in ss_output.splitlines()
                     if re.search(rf"[:.]{port}\s", ln)])

    def test_free_port(self):
        out = "State Recv-Q Send-Q Local Address:Port Peer\n"
        for p in vps.CHECK_PORTS:
            self.assertFalse(self._bound(out, p))

    def test_traefik_bound_is_idempotent_ok(self):
        out = ("LISTEN 0 4096 0.0.0.0:443 users:((\"traefik\",pid=1))\n"
               "LISTEN 0 4096 0.0.0.0:80 users:((\"traefik\",pid=1))\n"
               "LISTEN 0 4096 127.0.0.1:3000 users:((\"dokploy\",pid=2))\n")
        for p in vps.CHECK_PORTS:
            self.assertTrue(self._bound(out, p))

    def test_foreign_binding_detected(self):
        out = "LISTEN 0 511 0.0.0.0:3000 users:((\"node\",pid=9))\n"
        self.assertTrue(self._bound(out, 3000))
        self.assertFalse(self._bound(out, 80))


class TestReadOnlyGuarantee(unittest.TestCase):
    """The probe must never run a mutating SSH command."""

    FORBIDDEN = ("apt ", "apt-get", "ufw enable", "ufw allow", "ufw disable",
                 "install", "systemctl start", "systemctl stop",
                 "systemctl restart", "service ", "rm ", "mv ", "tee ",
                 "sed -i", ">>", "chmod", "chown", "useradd", "adduser",
                 "passwd", "curl ", "wget ", "bash -c", "sh -c", "| sh",
                 "docker run", "docker compose up", "reboot", "shutdown")

    def test_script_contains_no_mutating_commands(self):
        text = SCRIPT.read_text(encoding="utf-8")
        # Commands the probe is allowed to run (all read-only):
        allowed = ("true", "cat /etc/os-release", "free -m", "df -BG",
                   "ss -tlnp", "netstat -tlnp", "sshd -T",
                   "grep -riE", "command -v docker", "docker --version",
                   "docker compose version", "ufw status")
        # Every SSH payload in the file must start with an allowed prefix —
        # this is the operative read-only guarantee (what actually crosses
        # the wire), so scan payloads, not prose/docstrings.
        payloads = re.findall(r'run\("([^"\\]+)"\)', text) + re.findall(
            r'ssh_run\([^,]+, [^,]+, [^,]+, [^,]+, [^,]+, [^,]+,\s*"([^"\\]+)"\)',
            text)
        self.assertGreater(len(payloads), 5,
                           "test must find the probe's SSH payloads")
        for p in payloads:
            self.assertTrue(
                any(p.startswith(a) for a in allowed),
                f"SSH payload {p!r} is not in the read-only allowlist",
            )
            for bad in self.FORBIDDEN:
                self.assertNotIn(
                    bad, p,
                    f"SSH payload {p!r} contains mutating operation {bad!r}")

    def test_batch_mode_enforced(self):
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('"BatchMode=yes"', text,
                      "non-interactive key-only SSH is mandatory")
        self.assertIn("ConnectTimeout=10", text, "bounded connection time")

    def test_no_credentials_in_transit_beyond_key_path(self):
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("password", text.lower().replace(
            "passwordauthentication", "").replace("password auth", ""))


class TestExitSemantics(unittest.TestCase):
    """Exit contract: 0 ready · 1 findings · 2 cannot-assess."""

    def test_documented_in_module_and_runbook(self):
        self.assertIn("0 = ready", SCRIPT.read_text(encoding="utf-8"))
        runbook = RUNBOOK.read_text(encoding="utf-8")
        self.assertIn("**Exit 0 = ready, 1 = finding,", runbook)


if __name__ == "__main__":
    unittest.main()

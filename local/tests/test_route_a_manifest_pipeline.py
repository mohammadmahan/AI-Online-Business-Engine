"""Route A — pipeline wiring for the manifest gate (D-171 / D-141).

THE INTEGRATION POINT, ESTABLISHED BY INSPECTION RATHER THAN ASSUMED: this
repository has no CI and no pre-commit framework on disk — there is no
`.github/`, `.gitlab-ci.yml`, `Jenkinsfile`, `.circleci/`, `Makefile`,
`.pre-commit-config.yaml`, and `.git/hooks/` holds only the `.sample` files
every clone ships. Inventing a system was explicitly out of scope, so the gate
is wired into the pipeline that actually exists — the canonical battery:

    python3 -m unittest discover -s local/tests -p "test_*.py"

This module IS that wiring, and it is also its own proof: discovery imports it,
and it then executes `local/scripts/validate_route_a_manifest.py` the way an
operator runs it (subprocess, repository root, environment untouched). It pins
the mode separation the deployment lineage depends on:

  * the STANDARD run uses the gate's DEFAULT LOCAL FIXTURE mode and must stay
    green while no registry credentials exist (Case B) — it must never require
    a published OCI manifest digest;
  * `--require-deployable` is the DEPLOYMENT BOUNDARY check, opt-in by design:
    it refuses the local fixture, and no automatic surface may pass it.

Distinct from `test_route_a_manifest_gate.py`, which answers "does the gate
have teeth" via nine negative mutations of the real manifest. This module
answers a different question: "is the gate actually reached by the standard
validation run, and only in the one mode that run can satisfy?"
"""
import hashlib
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
GATE = REPO / "local" / "scripts" / "validate_route_a_manifest.py"
TESTS = REPO / "local" / "tests"
PATTERN = "test_*.py"
FLAG = "--require-deployable"
GATE_SUITE = "test_route_a_manifest_gate."
GATE_SUITE_CENSUS = 10

# The only files allowed to name the boundary flag: the gate's own suite (it
# asserts the refusal) and this module. Every other module in the battery would
# be a silent requirement that a registry image exist.
FLAG_ALLOWED = ("test_route_a_manifest_gate.py", Path(__file__).name)


def _digest(seed: bytes) -> str:
    """Synthetic digest shape. Derived, never a real registry digest."""
    return hashlib.sha256(seed).hexdigest()


def _run_gate(*args, extra_env=None):
    """Run the gate as an operator does. CONTROL_PLANE_IMAGE is removed from
    the inherited environment so the default local fixture path is the one
    exercised unless a test supplies an image deliberately."""
    env = {k: v for k, v in os.environ.items() if k != "CONTROL_PLANE_IMAGE"}
    if extra_env:
        env.update(extra_env)
    proc = subprocess.run([sys.executable, str(GATE), *args],
                          capture_output=True, text=True, cwd=str(REPO), env=env)
    return proc.returncode, proc.stdout + proc.stderr


def _flag_offenders(allow) -> list:
    """Every automatic surface that names the boundary flag, honouring the
    given allow-list. Factored out so the test can re-run it without the
    allow-list as a sensitivity control."""
    offenders = []
    for path in sorted(TESTS.glob(PATTERN)):
        if path.name in allow:
            continue
        if FLAG in path.read_text(encoding="utf-8", errors="replace"):
            offenders.append(f"local/tests/{path.name}")
    hooks_dir = REPO / ".git" / "hooks"
    installed_hooks = (sorted(p for p in hooks_dir.glob("*")
                              if p.is_file() and not p.name.endswith(".sample"))
                       if hooks_dir.is_dir() else [])
    for hook in installed_hooks:
        if FLAG in hook.read_text(encoding="utf-8", errors="replace"):
            offenders.append(f".git/hooks/{hook.name}")
    package_json = REPO / "control-plane" / "package.json"
    if package_json.is_file():
        scripts = json.dumps(
            json.loads(package_json.read_text(encoding="utf-8")).get("scripts")
            or {})
        if FLAG in scripts:
            offenders.append("control-plane/package.json scripts")
    return offenders


def _colon_ids(suite) -> list:
    out = []
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            out.extend(_colon_ids(item))
        else:
            out.append(item.id())
    return out


class TestRouteAManifestPipeline(unittest.TestCase):

    # --- wiring ------------------------------------------------------------

    def test_canonical_discovery_collects_the_gate_suite(self):
        """The gate must be part of the battery, not merely present on disk."""
        discovered = _colon_ids(unittest.TestLoader().discover(str(TESTS),
                                                               pattern=PATTERN))
        gate_ids = [i for i in discovered if GATE_SUITE in i]
        self.assertTrue(gate_ids, "the canonical discovery pattern no longer "
                                  f"collects {GATE_SUITE} — the gate would "
                                  "stop running in the standard validation run")
        for cls in ("TestRouteAManifestFixture", "TestRouteAManifestGate"):
            self.assertTrue(any(f"{GATE_SUITE}{cls}." in i for i in gate_ids),
                            f"{cls} is missing from the discovered suite")
        self.assertEqual(
            len(gate_ids), GATE_SUITE_CENSUS,
            f"the gate suite census changed ({len(gate_ids)} tests discovered, "
            f"{GATE_SUITE_CENSUS} expected) — update this pin deliberately if "
            "tests were added or removed")
        self.assertTrue(any("test_route_a_manifest_pipeline." in i
                            for i in discovered),
                        "this wiring module is not itself part of the battery")
        # Sensitivity control: the same discovery under a pattern that cannot
        # match must collect nothing, so the assertion above cannot pass just
        # by reading a hard-coded list.
        control = _colon_ids(unittest.TestLoader().discover(
            str(TESTS), pattern="test_route_a_manifest_gate_absent_*.py"))
        self.assertEqual([i for i in control if GATE_SUITE in i], [],
                         "discovery sensitivity control failed")

    # --- standard-run behaviour -------------------------------------------

    def test_standard_run_executes_the_gate_in_default_local_fixture_mode(self):
        rc, out = _run_gate()
        self.assertEqual(rc, 0, out)
        self.assertIn("=== VALID: Route A manifest satisfies the pinned "
                      "contract ===", out)
        self.assertIn("LOCAL DEVELOPMENT FIXTURE", out)
        self.assertIn("NOT evidence of a published OCI manifest digest", out)
        self.assertNotIn("=== REFUSED", out)

    def test_the_deployable_requirement_is_opt_in_only(self):
        """Fixture mode is green in both local and registry shapes; the
        boundary refusal exists only behind the explicit flag."""
        cases = {
            "unset image (fixture fallback)": None,
            "local-style digest": "control-plane@sha256:" + _digest(b"pipeline-local"),
            "registry-style digest": ("ghcr.io/example/control-plane@sha256:"
                                      + _digest(b"pipeline-registry")),
        }
        for label, image in cases.items():
            with self.subTest(image=label):
                extra = {"CONTROL_PLANE_IMAGE": image} if image else None
                rc, out = _run_gate(extra_env=extra)
                self.assertEqual(rc, 0, f"{label}: {out}")
                self.assertNotIn("=== REFUSED", out)

        rc, out = _run_gate(FLAG)
        self.assertEqual(rc, 1, out)
        self.assertIn("no published OCI manifest digest", out)
        self.assertIn("=== REFUSED", out)

    def test_no_automatic_surface_requires_a_deployable_image(self):
        """The boundary flag must live only in the Route A gate files: a test,
        hook or npm script that passed it would turn the standard run red for
        as long as Case B lasts."""
        offenders = _flag_offenders(FLAG_ALLOWED)
        self.assertEqual(
            offenders, [],
            f"the deployment-boundary flag {FLAG} reached an automatic "
            f"surface: {offenders} — it must be an explicit operator step")
        # Sensitivity control: with the allow-list removed the very same scan
        # must see the flag in the gate's suite, so an empty result above means
        # "absent", not "blind".
        control = _flag_offenders(())
        self.assertIn("local/tests/test_route_a_manifest_gate.py", control,
                      "the flag scan is blind — it failed its own control")
        self.assertTrue(GATE.is_file(), "the gate script is missing")


if __name__ == "__main__":
    unittest.main()

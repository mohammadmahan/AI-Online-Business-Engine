"""Route A — control-plane manifest gate (D-171 / D-141).

The Route A deployment manifest
(`docs/deployment/dokploy-control-plane.compose.yaml`) is guarded by
`local/scripts/validate_route_a_manifest.py`. This suite is the proof that
the gate has teeth: it drives the gate against the real manifest and
against focused NEGATIVE MUTATIONS of it, where each mutation removes or
weakens exactly one approved invariant and the gate must refuse every one.

Gates proven here:
  G-RA1  the real manifest passes, and the local-only image is reported as
         a development fixture — never as deployable evidence
  G-RA2  every required injected variable is individually fail-closed: the
         gate re-resolves the manifest with one variable removed and
         requires a refusal for each of the three
  G-RA3  `--require-deployable` refuses the local fixture
  G-RA4  a registry-pinned digest IS accepted as deployable
  G-RA5  negative mutations are refused — read_only removed, published port
         added, mutable tag image, non-strict variable form, root user,
         cap_drop removed, memory limit removed, volume added, healthcheck
         repointed away from /api/health
  G-RA6  the documented CLI exit codes hold the way an operator runs it

Every mutation edits the REAL manifest text and asserts that it changed a
site, so this suite cannot drift away from the file it claims to guard.
The gate itself is NOT a re-run of `validate_staging_compose.py`: that
validator is hard-coded to `local/infra/compose.staging.yml` and is neither
extended nor replaced by this work.
"""
import contextlib
import hashlib
import io
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "local" / "scripts"
MANIFEST = REPO / "docs" / "deployment" / "dokploy-control-plane.compose.yaml"
GATE_SCRIPT = SCRIPTS / "validate_route_a_manifest.py"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from validate_route_a_manifest import (  # noqa: E402
    REQUIRED_VARS,
    classify_image,
    main as gate_main,
)


def _run(argv):
    """Run the gate in-process; return (exit-code, captured-output)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = gate_main(list(argv))
    return rc, buf.getvalue()


def _fixture_digest(seed: bytes) -> str:
    """A synthetic, immutable-looking digest. Derived here on purpose: it is
    never a real published OCI manifest digest, only a shape fixture."""
    return hashlib.sha256(seed).hexdigest()


# --- focused negative mutations (each must change exactly one site) ---------

def _drop_read_only(text):
    return re.sub(r"^    read_only: true\n", "", text, count=1, flags=re.M)


def _add_published_port(text):
    return re.sub(r"^(    restart: unless-stopped\n)",
                  r'\1    ports:\n      - "127.0.0.1:8099:3000"\n',
                  text, count=1, flags=re.M)


def _mutable_tag_image(text):
    return re.sub(r"^    image: .*$", "    image: control-plane:latest",
                  text, count=1, flags=re.M)


def _loose_variable_form(text):
    return re.sub(r"^    image: \$\{CONTROL_PLANE_IMAGE:\?[^}]*\}$",
                  "    image: ${CONTROL_PLANE_IMAGE}", text, count=1, flags=re.M)


def _root_user(text):
    return re.sub(r'^    user: "1000:1000"$', '    user: "0:0"',
                  text, count=1, flags=re.M)


def _drop_cap_drop(text):
    return re.sub(r"^    cap_drop:\n      - ALL\n", "", text, count=1,
                  flags=re.M)


def _drop_memory_limit(text):
    return re.sub(r"^    mem_limit: 512m\n", "", text, count=1, flags=re.M)


def _add_volume(text):
    return re.sub(r"^(    networks:\n)",
                  r"    volumes:\n      - /tmp/route-a-gate:/state\n\1",
                  text, count=1, flags=re.M)


def _repoint_healthcheck(text):
    return re.sub(r"^(      test: .*)$",
                  lambda m: m.group(1).replace("/api/health", "/dashboard"),
                  text, count=1, flags=re.M)


NEGATIVE_MUTATIONS = (
    ("read_only removed", _drop_read_only, "read-only rootfs"),
    ("published port added", _add_published_port, "published ports present"),
    ("mutable tag as the image", _mutable_tag_image,
     "not declared as a strict"),
    ("non-strict variable form", _loose_variable_form,
     "not declared as a strict"),
    ("root user", _root_user, "non-root user 1000:1000"),
    ("cap_drop removed", _drop_cap_drop, "cap_drop ALL"),
    ("memory limit removed", _drop_memory_limit,
     "mem_limit missing, zero or unbounded"),
    ("volume added", _add_volume, "volumes declared"),
    ("healthcheck repointed", _repoint_healthcheck,
     "does not target /api/health"),
)


class TestRouteAManifestFixture(unittest.TestCase):
    """The manifest under test is the real, committed artifact."""

    def test_manifest_exists_and_is_the_route_a_artifact(self):
        self.assertTrue(MANIFEST.is_file(), f"missing {MANIFEST}")
        text = MANIFEST.read_text(encoding="utf-8")
        self.assertIn("Route A standalone Dokploy application", text)
        self.assertIn("${CONTROL_PLANE_IMAGE:?", text)

    def test_image_classification_helper(self):
        pinned = "ghcr.io/owner/name@sha256:" + _fixture_digest(b"cls-reg")
        local = "control-plane@sha256:" + _fixture_digest(b"cls-local")
        self.assertEqual(classify_image(pinned), "DEPLOYABLE")
        self.assertEqual(classify_image(local), "LOCAL_FIXTURE")
        for mutable in ("control-plane:latest", "control-plane:verify",
                        "ghcr.io/owner/name:latest", "control-plane"):
            self.assertEqual(classify_image(mutable), "MUTABLE", mutable)


class TestRouteAManifestGate(unittest.TestCase):

    def _mutated(self, mutate):
        text = MANIFEST.read_text(encoding="utf-8")
        changed = mutate(text)
        self.assertNotEqual(changed, text, "mutation changed nothing — the "
                                           "manifest text drifted")
        tmp = tempfile.mkdtemp(prefix="route-a-gate-")
        self.addCleanup(shutil.rmtree, tmp, True)
        path = Path(tmp) / "manifest.yaml"
        path.write_text(changed, encoding="utf-8")
        return path

    # --- G-RA1/G-RA2 -------------------------------------------------------

    def test_real_manifest_passes_and_flags_the_local_fixture(self):
        rc, out = _run(["--manifest", str(MANIFEST)])
        self.assertEqual(rc, 0, out)
        self.assertIn("VALID", out)
        self.assertIn("LOCAL DEVELOPMENT FIXTURE", out)
        self.assertIn("NOT evidence of a published OCI manifest digest", out)

    def test_every_required_variable_is_individually_fail_closed(self):
        rc, out = _run(["--manifest", str(MANIFEST)])
        self.assertEqual(rc, 0, out)
        self.assertEqual(len(REQUIRED_VARS), 3, "contract drifted")
        for name in REQUIRED_VARS:
            self.assertIn(f"missing {name} refuses startup (fail-closed)", out)

    # --- G-RA3/G-RA4 -------------------------------------------------------

    def test_require_deployable_refuses_the_local_fixture(self):
        rc, out = _run(["--manifest", str(MANIFEST), "--require-deployable"])
        self.assertEqual(rc, 1, out)
        self.assertIn("no published OCI manifest digest", out)

    def test_registry_pinned_digest_is_accepted_as_deployable(self):
        ref = ("ghcr.io/mohammadmahan/control-plane@sha256:"
               + _fixture_digest(b"route-a-gate-registry-fixture"))
        rc, out = _run(["--manifest", str(MANIFEST), "--image", ref,
                        "--require-deployable"])
        self.assertEqual(rc, 0, out)
        self.assertIn("digest-pinned to a registry", out)

    def test_mutable_image_value_is_refused(self):
        rc, out = _run(["--manifest", str(MANIFEST),
                        "--image", "control-plane:latest"])
        self.assertEqual(rc, 1, out)
        self.assertIn("mutable or unpinned", out)

    # --- G-RA5 -------------------------------------------------------------

    def test_negative_mutations_are_refused(self):
        for name, mutate, needle in NEGATIVE_MUTATIONS:
            with self.subTest(mutation=name):
                path = self._mutated(mutate)
                rc, out = _run(["--manifest", str(path)])
                self.assertEqual(
                    rc, 1, f"{name}: the gate did NOT refuse a weakened "
                           f"manifest:\n{out}")
                self.assertIn(needle, out)

    def test_each_mutation_changes_the_resolved_manifest(self):
        """A mutation that produced an unresolvable file would be refused for
        the wrong reason, so every mutation must still resolve."""
        for name, mutate, _needle in NEGATIVE_MUTATIONS:
            with self.subTest(mutation=name):
                path = self._mutated(mutate)
                proc = subprocess.run(
                    ["docker", "compose", "-f", str(path), "config"],
                    capture_output=True, text=True, cwd=str(REPO),
                    env={**{k: v for k, v in
                            __import__("os").environ.items()},
                         "CONTROL_PLANE_IMAGE":
                             "control-plane@sha256:" + _fixture_digest(b"res"),
                         "CP_PROBE_ENDPOINTS": "{}",
                         "CP_PROBE_TOKENS": "{}"})
                self.assertEqual(
                    proc.returncode, 0,
                    f"{name}: the mutant does not resolve, so the refusal "
                    f"would prove nothing: {proc.stderr.strip()[:200]}")

    # --- G-RA6 -------------------------------------------------------------

    def test_cli_exit_codes_as_an_operator_runs_it(self):
        good = subprocess.run([sys.executable, str(GATE_SCRIPT)],
                              capture_output=True, text=True, cwd=str(REPO))
        self.assertEqual(good.returncode, 0, good.stdout + good.stderr)
        self.assertIn("VALID", good.stdout)
        strict = subprocess.run(
            [sys.executable, str(GATE_SCRIPT), "--require-deployable"],
            capture_output=True, text=True, cwd=str(REPO))
        self.assertEqual(strict.returncode, 1, strict.stdout + strict.stderr)
        self.assertIn("no published OCI manifest digest", strict.stdout)


if __name__ == "__main__":
    unittest.main()

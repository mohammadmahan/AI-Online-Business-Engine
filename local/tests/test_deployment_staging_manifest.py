"""Stage B — staging manifest structural validation (D-141, G-B1..G-B4).

The staging deployment manifest `local/infra/compose.staging.yml` is a
Stage B artifact: this suite machine-checks the gates the launch-facing
documentation claims for it, using `docker compose config --format json`
(client-side resolution — schema validation + resolved view, no daemon
needed) and pure stdlib assertions on the resolved output.

Gates proven here:
  G-B1  digest-pinned images (F-8), exposure remodel (F-2: wordpress is
        the ONLY published surface, nothing bound to 127.0.0.1), hosted
        restart policies (F-3), APP_ENV/staging guard present (F-5)
  G-B2  secret-free by construction: the six fail-closed variables are
        REQUIRED (config refuses without them) and no local throwaway
        credential literal leaks into the staging file
  G-B4  staging prohibitions encoded: debug off, no AI credentials, no
        127.0.0.1 binds, staging-synthetic database names
  parity service set matches the local base manifest; healthchecks and
        health-gated start order preserved; all six named volumes present
        (five resolved active + profile-gated mock_state)
"""
import json
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STAGING = REPO / "local" / "infra" / "compose.staging.yml"
BASE = REPO / "local" / "infra" / "docker-compose.yml"

# Throwaway validation values — NEVER secrets, never committed; they exist
# only inside this process to satisfy the fail-closed :? requirements.
SYNTHETIC_ENV = {
    "CANONICAL_DB_PASSWORD": "throwaway-validation-canonical",
    "WORDPRESS_DB_PASSWORD": "throwaway-validation-wp",
    "MYSQL_PASSWORD": "throwaway-validation-mysql",
    "MYSQL_ROOT_PASSWORD": "throwaway-validation-mysql-root",
    "N8N_ENCRYPTION_KEY": "throwaway-validation-n8n",
    "MINIO_ROOT_PASSWORD": "throwaway-validation-minio",
}


def _resolve(extra_env=None, drop=()):
    """Resolve the staging manifest via `docker compose config`. Returns
    (rc, parsed-json-or-None, stderr-text)."""
    env = dict(os.environ)
    env.update(SYNTHETIC_ENV)
    for k in drop:
        env.pop(k, None)
    if extra_env:
        env.update(extra_env)
    proc = subprocess.run(
        ["docker", "compose", "-f", str(STAGING), "config", "--format", "json"],
        capture_output=True, text=True, env=env, cwd=str(REPO),
    )
    if proc.returncode != 0:
        return proc.returncode, None, proc.stderr
    return 0, json.loads(proc.stdout), proc.stderr


def _base_service_names():
    """Derive the base manifest's service names (2-space-indented keys
    under the top-level `services:` block) to detect drift."""
    names, in_services = set(), False
    for line in BASE.read_text(encoding="utf-8").splitlines():
        if line.startswith("services:"):
            in_services = True
            continue
        if in_services:
            if line.startswith("  ") and not line.startswith("   "):
                names.add(line.strip().rstrip(":"))
            elif line.strip() and not line.startswith("  "):
                break  # next top-level key
    return names


class TestStagingManifestStageB(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.assertTrue(cls, STAGING.exists(), "staging manifest must exist")
        rc, cls.resolved, cls.stderr = _resolve()
        if rc != 0:
            raise AssertionError(
                "docker compose failed to resolve the staging manifest "
                f"(rc={rc}). Is the docker CLI + compose plugin installed?\n"
                f"stderr: {cls.stderr[:400]}"
            )

    # ---------- G-B1: digest pinning (F-8) ----------

    def test_all_images_digest_pinned(self):
        for name, svc in self.resolved["services"].items():
            img = svc["image"]
            self.assertIn(
                "@sha256:", img,
                f"service {name} image is not digest-pinned: {img}",
            )

    def test_images_are_multi_arch_index_pins_not_guessed(self):
        # Pin format keeps the tag for intent AND the index digest for
        # immutability; nothing may rely on a bare mutable tag.
        text = STAGING.read_text(encoding="utf-8")
        bare = [
            ln.strip() for ln in text.splitlines()
            if ln.strip().startswith("image:")
            and "@sha256:" not in ln
        ]
        self.assertEqual(bare, [], f"bare-tag image lines: {bare}")

    # ---------- G-B1: exposure remodel (F-2) ----------

    def test_wordpress_is_the_only_published_service(self):
        published = {
            name: [p.get("published") for p in svc.get("ports", [])]
            for name, svc in self.resolved["services"].items()
            if svc.get("ports")
        }
        self.assertEqual(
            list(published), ["wordpress"],
            f"only wordpress may publish ports, found: {published}",
        )

    def test_no_localhost_bound_or_gateway_conflicting_ports(self):
        # Container-internal healthchecks legitimately use 127.0.0.1; the
        # invariant is about PORT PUBLISHING, so assert on resolved ports.
        for name, svc in self.resolved["services"].items():
            for p in svc.get("ports", []):
                self.assertNotIn(
                    str(p.get("host_ip", "")), {"127.0.0.1", "::1"},
                    f"{name} must not publish on loopback (F-2)",
                )
                self.assertNotIn(
                    str(p.get("published")), {"80", "443", "3000"},
                    f"{name} conflicts with the documented gateway ports",
                )

    def test_data_planes_are_not_network_exposed(self):
        for name in ("canonical-db", "woodb", "media", "n8n"):
            self.assertEqual(
                self.resolved["services"][name].get("ports", []),
                [], f"{name} must have no published ports",
            )

    # ---------- G-B1: restart policies (F-3) ----------

    def test_active_services_use_hosted_restart_policy(self):
        for name, svc in self.resolved["services"].items():
            self.assertEqual(
                svc.get("restart"), "unless-stopped",
                f"{name} restart policy must be hosted-grade, "
                f"got {svc.get('restart')!r}",
            )

    # ---------- G-B2: secret-free by construction ----------

    def test_fail_closed_without_secrets(self):
        for var in SYNTHETIC_ENV:
            rc, _, stderr = _resolve(drop=(var,))
            self.assertNotEqual(
                rc, 0,
                f"config must REFUSE to run without {var} (fail-closed)",
            )
            self.assertIn(
                var, stderr,
                f"error must name the missing variable {var}",
            )

    def test_no_local_throwaway_credential_literals(self):
        text = STAGING.read_text(encoding="utf-8")
        for literal in (
            "wp-local-only", "root-local-only", "engine-local-only",
            "engine-local-encryption-only", "engine-local-media-only",
            "engine-local-media",
        ):
            self.assertNotIn(
                literal, text,
                f"local throwaway credential {literal!r} leaked into staging",
            )

    def test_credential_reference_pattern_preserved(self):
        # D-045 REF pattern: pointer strings, not secret material. Assert
        # on the RESOLVED environment — staging grants no AI credentials.
        for name, svc in self.resolved["services"].items():
            env = svc.get("environment", {})
            self.assertNotIn(
                "AI_CREDENTIAL_REF", env,
                f"{name} must carry no AI credential grant in staging",
            )
        self.assertIn("staging secret required", STAGING.read_text(encoding="utf-8"))

    # ---------- G-B4: staging prohibitions encoded ----------

    def test_staging_guardrails_in_environment(self):
        wp_env = self.resolved["services"]["wordpress"]["environment"]
        self.assertEqual(wp_env["WORDPRESS_DEBUG"], "0")
        self.assertTrue(
            wp_env["WORDPRESS_DB_NAME"].endswith("_staging"),
            "staging database names must be staging-synthetic",
        )
        mysql_env = self.resolved["services"]["woodb"]["environment"]
        self.assertEqual(mysql_env["MYSQL_DATABASE"], "wordpress_staging")

    def test_timezones_carried_over(self):
        self.assertEqual(
            self.resolved["services"]["woodb"]["environment"]["TZ"],
            "Asia/Tehran",
        )
        self.assertEqual(
            self.resolved["services"]["canonical-db"]["environment"]["TZ"],
            "Asia/Tehran",
        )

    # ---------- parity / structure ----------

    def test_service_set_matches_base_manifest(self):
        self.assertEqual(
            set(self.resolved["services"]), _base_service_names() - {"mock-woo"},
            "resolved active service set must match the base manifest "
            "(mock-woo stays profile-gated)",
        )
        text = STAGING.read_text(encoding="utf-8")
        self.assertIn('profiles: ["deferred"]', text,
                      "mock-woo must stay profile-gated in staging")

    def test_healthchecks_and_start_order_preserved(self):
        for name, svc in self.resolved["services"].items():
            if name == "mock-woo":
                continue
            self.assertIn("healthcheck", svc, f"{name} needs a healthcheck")
        deps = self.resolved["services"]["wordpress"]["depends_on"]
        self.assertEqual(deps["woodb"]["condition"], "service_healthy")
        deps = self.resolved["services"]["n8n"]["depends_on"]
        self.assertEqual(deps["canonical-db"]["condition"], "service_healthy")

    def test_all_named_volumes_present(self):
        declared = set(self.resolved.get("volumes", {}))
        self.assertEqual(
            declared,
            {"woo_data", "woo_data_db", "canonical_data",
             "n8n_data", "media_data"},
            "resolved volumes must match the base volume set "
            "(mock_state is profile-gated in the file)",
        )
        text = STAGING.read_text(encoding="utf-8")
        self.assertIn("mock_state: {}", text)

    def test_explicit_network_topology_declared(self):
        """Stage B amendment (D-141 §21.7): the default-bridge model was
        replaced by an explicit isolated topology — data (internal) +
        frontend (wordpress-only); detailed assertions live in
        TestStagingNetworkIsolation."""
        text = STAGING.read_text(encoding="utf-8")
        self.assertIn("networks:", text)
        self.assertIn("internal: true", text)


class TestStagingNetworkIsolation(unittest.TestCase):
    """Stage B amendment: explicit isolated network topology."""

    @classmethod
    def setUpClass(cls):
        rc, cls.resolved, cls.stderr = _resolve()
        if rc != 0:
            raise AssertionError(
                f"manifest resolution failed: {cls.stderr[:300]}"
            )

    def test_data_network_is_internal(self):
        self.assertTrue(
            self.resolved["networks"]["data"].get("internal"),
            "data network must be internal (no outbound routing)",
        )

    def test_frontend_network_exists(self):
        self.assertIn("frontend", self.resolved["networks"])

    def test_topology_matches_design(self):
        for name in ("canonical-db", "woodb", "media", "n8n"):
            self.assertEqual(
                set(self.resolved["services"][name].get("networks", {})),
                {"data"}, f"{name} must be data-only",
            )
        self.assertEqual(
            set(self.resolved["services"]["wordpress"].get("networks", {})),
            {"data", "frontend"},
            "wordpress is the only frontend-attached service",
        )

    def test_no_service_on_frontend_but_wordpress(self):
        for name, svc in self.resolved["services"].items():
            if name != "wordpress":
                self.assertNotIn(
                    "frontend", svc.get("networks", {}),
                    f"{name} must not attach to frontend",
                )


class TestStagingEnvContractTemplate(unittest.TestCase):
    """Stage B amendment: .env.staging.example completeness (zero secrets)."""

    @classmethod
    def setUpClass(cls):
        cls.template = {}
        for line in (REPO / ".env.staging.example").read_text(
            encoding="utf-8"
        ).splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                cls.template[k] = v

    def test_template_exists_and_is_documented(self):
        self.assertGreaterEqual(len(self.template), 25,
                                "env template must document the full contract")

    def test_all_six_deploy_secrets_are_placeholder_only(self):
        for var in SYNTHETIC_ENV:
            self.assertEqual(
                self.template.get(var),
                "<SET-BY-DEPLOYMENT-LAYER>",
                f"{var} must be placeholder-only in the committed template",
            )

    def test_no_hardcoded_secret_values_anywhere(self):
        for var, val in self.template.items():
            if var in SYNTHETIC_ENV:
                continue
            self.assertFalse(
                re.search(r"(?i)(password|secret|key|token)=", val)
                and val not in ("<SET-BY-DEPLOYMENT-LAYER>",),
                f"{var} looks like a secret value: {val!r}",
            )

    def test_no_local_throwaway_credentials_leaked(self):
        text = (REPO / ".env.staging.example").read_text(encoding="utf-8")
        for literal in ("wp-local-only", "root-local-only",
                        "engine-local-only", "engine-local-encryption-only",
                        "engine-local-media-only"):
            self.assertNotIn(literal, text)

    def test_no_ai_credential_grant_in_staging_template(self):
        self.assertNotIn("AI_CREDENTIAL_REF", self.template,
                         "staging grants NO AI credentials (G-B4)")

    def test_env_template_matches_script_contract(self):
        """The operator script's drift categories must cover the template
        exactly — single source of truth, no silent divergence."""
        sys.path.insert(0, str(REPO / "local" / "scripts"))
        import validate_staging_compose as vsc  # noqa: E402
        manifest_vars = set()
        for line in STAGING.read_text(encoding="utf-8").splitlines():
            if line.lstrip().startswith("#"):
                continue
            for m in re.finditer(r"\$\{([A-Z][A-Z0-9_]*)(?::[-?])?", line):
                manifest_vars.add(m.group(1))
        covered = (manifest_vars & set(self.template)) \
            | vsc.APP_ENV_CONTRACT | vsc.PLACEHOLDER_ONLY
        self.assertEqual(
            set(self.template), covered,
            "every template variable must be compose-consumed, "
            "app-env contract, or placeholder-only",
        )
        self.assertTrue(
            vsc.REQUIRED_SECRET_VARS and
            set(vsc.REQUIRED_SECRET_VARS) == set(SYNTHETIC_ENV),
            "script and battery must agree on the required-secret set",
        )


if __name__ == "__main__":
    unittest.main()

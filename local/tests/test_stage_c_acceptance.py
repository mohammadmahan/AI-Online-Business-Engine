"""Stage C acceptance battery (offline — every transport injectable).

Pins the fail-closed contract of `local/scripts/stage_c_acceptance.py`:

  - BOUNDARY GUARD  — the sanctioned engine-local rehearsal stack is the
    ONLY probe surface: a missing, partial, or forged container set is
    CANNOT_ASSESS and NOTHING else is probed (synthetic-data-only
    guarantee at the boundary).
  - FAIL-CLOSED     — probe-transport failure stops the run (cannot
    assess); per-plane failures become FINDINGS; a public 0.0.0.0
    binding on n8n is refused; production signatures or secret-shaped
    material in ANY probe detail flip the synthetic_data_guard.
  - ZERO RESIDUE    — the real SigV4 MediaStore round-trip (put → get →
    head → delete → head-404) runs against the engine-local MinIO when
    the stack is up (skipped otherwise) and leaves no object behind.
  - EMISSION        — qa.launch_attestation.v1 probe shape; exit
    0 ACCEPTED / 1 FINDINGS / 2 CANNOT_ASSESS.
"""
from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "local" / "scripts"))

import stage_c_acceptance as acc  # noqa: E402

SCRIPT = REPO / "local" / "scripts" / "stage_c_acceptance.py"
ALL_FIVE = ["engine-local-postgres", "engine-local-mysql",
            "engine-local-wordpress", "engine-local-minio",
            "engine-local-n8n"]


def psql_ok(sql: str) -> str:
    if "nspname" in sql:
        return "canonical,events,provenance,registry,seed"
    if "event_record" in sql:
        return "12"
    if "mapping_entry" in sql:
        return "7"
    return "1"


def _as_fn(v):
    """Allow overrides to be plain values (wrapped as constant fns) or
    real callables — the harness contract is callables everywhere."""
    return v if callable(v) else (lambda *a, **k: v)


def green_kwargs(**overrides) -> dict:
    kw = dict(
        containers_fn=lambda: list(ALL_FIVE),
        psql_fn=psql_ok,
        mysql_fn=lambda: (0, "mysqld is alive"),
        http_fn=lambda url: 200,
        port_fn=lambda: {"n8n": "127.0.0.1:15678->5678/tcp",
                         "wordpress": "127.0.0.1:18080->80/tcp",
                         "media": "127.0.0.1:19000->9000/tcp"},
        media_fn=lambda prefix: {"ok": True,
                                 "detail": "stub contract round-trip"},
        ledger_fn=lambda: {"ok": True,
                           "reason": "verified_with_history_depth",
                           "decisions_checked": 5},
    )
    for key, val in overrides.items():
        kw[key] = _as_fn(val)
    return kw


def run(**overrides) -> dict:
    return acc.run_probes(**green_kwargs(**overrides))


def main_rc(report: dict) -> int:
    with mock.patch.object(acc, "run_probes", return_value=report), \
         contextlib.redirect_stdout(io.StringIO()):
        return acc.main([])


class StackIdentityGuard(unittest.TestCase):
    def test_stack_down_refuses_everything(self):
        res = acc.run_probes(containers_fn=lambda: [])
        self.assertEqual(res["verdict"], "CANNOT_ASSESS")
        self.assertEqual([p["name"] for p in res["probes"]],
                         ["stack_identity"])
        self.assertEqual(main_rc(res), 2)

    def test_partial_stack_refuses_and_names_the_gap(self):
        partial = [c for c in ALL_FIVE if c != "engine-local-minio"]
        res = acc.run_probes(containers_fn=lambda: partial)
        self.assertEqual(res["verdict"], "CANNOT_ASSESS")
        self.assertIn("engine-local-minio", res["probes"][0]["detail"])

    def test_forged_stack_identity_refuses(self):
        res = acc.run_probes(
            containers_fn=lambda: ["evil-postgres"] + ALL_FIVE[1:])
        self.assertEqual(res["verdict"], "CANNOT_ASSESS")
        self.assertIn("engine-local-postgres", res["probes"][0]["detail"])

    def test_healthy_stack_records_sanctioned_identity(self):
        res = run()
        ident = res["probes"][0]
        self.assertEqual(ident["name"], "stack_identity")
        self.assertEqual(ident["verdict"], "PASS")


class CanonicalProbes(unittest.TestCase):
    def test_schema_mirror_passes_on_five_schemas(self):
        res = run()
        probe = [p for p in res["probes"]
                 if p["name"] == "canonical_schema"][0]
        self.assertEqual(probe["verdict"], "PASS")
        self.assertIn("apply_schema idempotency mirror", probe["detail"])

    def test_missing_schema_refuses_with_hint(self):
        res = run(psql_fn=lambda sql: "canonical,events"
                  if "nspname" in sql else psql_ok(sql))
        probe = [p for p in res["probes"]
                 if p["name"] == "canonical_schema"][0]
        self.assertEqual(probe["verdict"], "FAIL")
        self.assertIn("apply_schema", probe["detail"])
        self.assertEqual(res["verdict"], "FINDINGS")

    def test_event_store_probe_is_read_only(self):
        res = run()
        probe = [p for p in res["probes"]
                 if p["name"] == "canonical_event_store"][0]
        self.assertEqual(probe["verdict"], "PASS")
        self.assertIn("zero writes", probe["detail"])
        self.assertIn("event_record=12", probe["detail"])

    def test_psql_transport_failure_is_cannot_assess(self):
        def boom(sql):
            raise RuntimeError("psql unavailable")
        res = run(psql_fn=boom)
        self.assertEqual(res["verdict"], "CANNOT_ASSESS")
        self.assertEqual(res["failing"], ["canonical_pg"])
        self.assertEqual(main_rc(res), 2)


class MysqlAndWordPress(unittest.TestCase):
    def test_mysql_alive_passes(self):
        res = run()
        probe = [p for p in res["probes"] if p["name"] == "mysql_woo"][0]
        self.assertEqual(probe["verdict"], "PASS")

    def test_mysql_down_is_a_finding(self):
        res = run(mysql_fn=(1, "mysqld is not alive"))
        probe = [p for p in res["probes"] if p["name"] == "mysql_woo"][0]
        self.assertEqual(probe["verdict"], "FAIL")
        self.assertEqual(res["verdict"], "FINDINGS")

    def test_wordpress_rest_accepts_302(self):
        res = run(http_fn=lambda url: 302)
        probe = [p for p in res["probes"] if p["name"] == "wordpress_rest"][0]
        self.assertEqual(probe["verdict"], "PASS")

    def test_wordpress_unreachable_fails(self):
        def boom(url):
            raise OSError("connection refused")
        res = run(http_fn=boom)
        probe = [p for p in res["probes"] if p["name"] == "wordpress_rest"][0]
        self.assertEqual(probe["verdict"], "FAIL")


class MediaStoreContractProbe(unittest.TestCase):
    def test_green_roundtrip_passes(self):
        res = run()
        probe = [p for p in res["probes"] if p["name"] == "media_store"][0]
        self.assertEqual(probe["verdict"], "PASS")

    def test_incomplete_roundtrip_fails(self):
        res = run(media_fn=lambda prefix: {
            "ok": False,
            "detail": "round-trip incomplete: get=True head=True del=False"})
        probe = [p for p in res["probes"] if p["name"] == "media_store"][0]
        self.assertEqual(probe["verdict"], "FAIL")
        self.assertIn("del=False", probe["detail"])

    def test_media_probe_crash_is_a_finding_not_a_crash(self):
        def boom(prefix):
            raise RuntimeError("sigv4 exploded")
        res = run(media_fn=boom)
        probe = [p for p in res["probes"] if p["name"] == "media_store"][0]
        self.assertEqual(probe["verdict"], "FAIL")
        self.assertIn("MediaStoreContract probe failed", probe["detail"])

    def test_real_sigv4_roundtrip_zero_residue_live(self):
        if sorted(acc.stack_containers()) != sorted(ALL_FIVE):
            self.skipTest("engine-local rehearsal stack not running")
        result = acc.media_roundtrip("stage-c-acceptance-battery")
        self.assertTrue(result["ok"], result["detail"])
        self.assertIn("zero residue", result["detail"])


class N8nTunnelOnly(unittest.TestCase):
    def test_loopback_tunnel_healthz_passes(self):
        res = run()
        probe = [p for p in res["probes"] if p["name"] == "n8n_tunnel"][0]
        self.assertEqual(probe["verdict"], "PASS")

    def test_public_binding_is_refused(self):
        res = run(port_fn=lambda: {
            "n8n": "0.0.0.0:15678->5678/tcp", "wordpress": "",
            "media": ""})
        probe = [p for p in res["probes"] if p["name"] == "n8n_tunnel"][0]
        self.assertEqual(probe["verdict"], "FAIL")
        self.assertIn("PUBLIC EXPOSURE REFUSED", probe["detail"])

    def test_unresolved_binding_is_a_finding(self):
        res = run(port_fn=lambda: {"n8n": "", "wordpress": "", "media": ""})
        probe = [p for p in res["probes"] if p["name"] == "n8n_tunnel"][0]
        self.assertEqual(probe["verdict"], "FAIL")

    def test_healthz_500_fails(self):
        res = run(http_fn=lambda url: 500)
        probe = [p for p in res["probes"] if p["name"] == "n8n_tunnel"][0]
        self.assertEqual(probe["verdict"], "FAIL")


class DecisionLedgerProbe(unittest.TestCase):
    def test_consistency_ok_passes(self):
        res = run()
        probe = [p for p in res["probes"]
                 if p["name"] == "decision_ledger"][0]
        self.assertEqual(probe["verdict"], "PASS")
        self.assertIn("verified_with_history_depth", probe["detail"])

    def test_inconsistency_is_a_finding(self):
        res = run(ledger_fn=lambda: {
            "ok": False, "reason": "missing_decision_record"})
        probe = [p for p in res["probes"]
                 if p["name"] == "decision_ledger"][0]
        self.assertEqual(probe["verdict"], "FAIL")
        self.assertIn("missing_decision_record", probe["detail"])


class SyntheticDataGuard(unittest.TestCase):
    def test_production_signature_in_evidence_refused(self):
        res = run(ledger_fn=lambda: {
            "ok": True, "reason": "fine but APP_ENV=production leaked"})
        guard = [p for p in res["probes"]
                 if p["name"] == "synthetic_data_guard"][0]
        self.assertEqual(guard["verdict"], "FAIL")
        self.assertEqual(res["verdict"], "FINDINGS")
        self.assertIn("synthetic_data_guard", res["failing"])

    def test_secret_shaped_evidence_refused(self):
        res = run(ledger_fn=lambda: {
            "ok": True, "reason": "token sk-abcdefghijklmnopqrst leaked"})
        guard = [p for p in res["probes"]
                 if p["name"] == "synthetic_data_guard"][0]
        self.assertEqual(guard["verdict"], "FAIL")

    def test_clean_evidence_passes(self):
        res = run()
        guard = [p for p in res["probes"]
                 if p["name"] == "synthetic_data_guard"][0]
        self.assertEqual(guard["verdict"], "PASS")
        self.assertIn("D-045/D-124", guard["detail"])


class VerdictAndEmission(unittest.TestCase):
    def test_all_green_is_accepted_rc0(self):
        res = run()
        self.assertTrue(res["ok"])
        self.assertEqual(res["verdict"], "ACCEPTED")
        self.assertEqual(main_rc(res), 0)

    def test_findings_is_rc1(self):
        res = run(mysql_fn=(1, "down"))
        self.assertEqual(res["verdict"], "FINDINGS")
        self.assertEqual(main_rc(res), 1)

    def test_cannot_assess_is_rc2(self):
        res = acc.run_probes(containers_fn=lambda: [])
        self.assertEqual(main_rc(res), 2)

    def test_probe_shape_matches_audit_conventions(self):
        res = run()
        self.assertEqual(res["schema_version"], "stage_c.acceptance_run.v1")
        self.assertEqual(res["compatible_with"], "qa.launch_attestation.v1")
        for probe in res["probes"]:
            for field in ("name", "verdict", "detail",
                          "checked_at_logical"):
                self.assertIn(field, probe)

    def test_render_marks_cannot_assess_rows(self):
        res = acc.run_probes(containers_fn=lambda: [])
        self.assertIn("[ENV ]", acc.render(res))

    def test_json_output_is_valid(self):
        r = subprocess.run([sys.executable, str(SCRIPT), "--json"],
                           capture_output=True, text=True)
        if "stack_identity" not in r.stdout and r.returncode == 2:
            self.skipTest("engine-local rehearsal stack not running")
        payload = json.loads(r.stdout)
        self.assertIn("verdict", payload)


if __name__ == "__main__":
    unittest.main()

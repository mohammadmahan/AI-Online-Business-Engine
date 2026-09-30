"""Stage C attestation-ingest & backup-policy battery (offline).

Pins Layer 2 of the Stage C deployment-clearance chain (Dokploy plan
§23/§24):

  TOKEN VERIFIER — `local/scripts/stage_c_token.py` fails closed over
  the emitted `stage_c.runbook_attestation.v1` artifact: schema,
  attestation-digest integrity (the G6 emission algorithm re-run by
  the consumer), SHA-256 artifact bindings, candidate-commit evidence
  provenance (CURRENT / ANCESTOR / broken / undecidable), the G1–G5
  gate ledger, and the acceptance payload integrity (10-probe census,
  stack identity 5/5, media zero-residue marker, non-zero canonical
  event ledger). Structural defects REFUSE (StageCTokenError);
  verdict-bearing findings downgrade the clearance.

  LAUNCH GATE WIRING — `launch_attestation.py --check-stage-c` folds
  the token verdict into the deployment clearance: a verified token is
  silent, token findings append an SC-RUNBOOK blocker (GO downgraded
  to NO_GO, never upgraded), and a missing or corrupted token refuses
  with exit 2 BEFORE the report prints (fail closed).

  BACKUP POLICY CLEARANCE — `local/scripts/stage_c_backup_checks.py`
  validates the staging volume & backup policy (§2 schedule/retention,
  RPO floors, off-host mandate, restore preconditions, supplement-only
  authority, D-045 credential hygiene: BACKUP_* stays commented with
  placeholder values until SC-6/SC-7 sign).

  ZERO LEAK — verdicts carry names, verdicts, and counts — never
  credential values or token payload material (D-045/D-124).
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "local" / "scripts"))

import stage_c_token as sct  # noqa: E402
import stage_c_backup_checks as bc  # noqa: E402
import launch_attestation as la  # noqa: E402
import stage_c_acceptance as acc  # noqa: E402

TOKEN = REPO / "docs" / "deployment" / "stage-c-attestation.json"
POLICY = REPO / "docs" / "deployment" / "staging-volume-backup-policy.md"
MANIFEST = REPO / "local" / "infra" / "compose.staging.yml"
TEMPLATE = REPO / ".env.staging.template"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# synthetic-token factory (mirrors the G6 emission algorithm)
# --------------------------------------------------------------------------
def probe_census() -> list:
    return [
        {"name": "stack_identity", "verdict": "PASS",
         "detail": "engine-local rehearsal stack 5/5 running — "
                   "sanctioned synthetic-only probe surface",
         "checked_at_logical": ""},
        {"name": "canonical_pg", "verdict": "PASS",
         "detail": "connectivity via sanctioned container-psql transport",
         "checked_at_logical": ""},
        {"name": "canonical_schema", "verdict": "PASS",
         "detail": "five core schemas present", "checked_at_logical": ""},
        {"name": "canonical_event_store", "verdict": "PASS",
         "detail": "read-only counts: events.event_record=75553 "
                   "registry.mapping_entry=0 (zero writes)",
         "checked_at_logical": ""},
        {"name": "mysql_woo", "verdict": "PASS",
         "detail": "mysqld responsive", "checked_at_logical": ""},
        {"name": "wordpress_rest", "verdict": "PASS",
         "detail": "REST surface answers (HTTP 200)",
         "checked_at_logical": ""},
        {"name": "media_store", "verdict": "PASS",
         "detail": "contract round-trip ok, zero residue "
                   "(put/get/head/delete/delete-404)",
         "checked_at_logical": ""},
        {"name": "n8n_tunnel", "verdict": "PASS",
         "detail": "healthz HTTP 200 over the loopback tunnel",
         "checked_at_logical": ""},
        {"name": "decision_ledger", "verdict": "PASS",
         "detail": "verified_with_history_depth", "checked_at_logical": ""},
        {"name": "synthetic_data_guard", "verdict": "PASS",
         "detail": "no production signatures in probe evidence",
         "checked_at_logical": ""},
    ]


def token_dict(**over) -> dict:
    base = {
        "schema_version": "stage_c.runbook_attestation.v1",
        "compatible_with": "qa.launch_attestation.v1",
        "candidate_commit": "tokcommit",
        "owner_grants": {"authorized": False,
                         "verdict": "NOT_AUTHORIZED", "signed": 0,
                         "note": "TECHNICAL CLEARANCE ONLY"},
        "bindings": {"env_artifact_sha256": "a" * 64,
                     "manifest_sha256": "b" * 64,
                     "grants_artifact_sha256": "c" * 64},
        "gates": [{"gate": f"G{i}", "name": f"gate {i}",
                   "verdict": "PASS", "detail": "ok"}
                  for i in range(1, 6)],
        "acceptance_run": {
            "schema_version": "stage_c.acceptance_run.v1",
            "compatible_with": "qa.launch_attestation.v1",
            "ok": True, "verdict": "ACCEPTED",
            "probes": probe_census(), "failing": []},
        "runbook": "docs/deployment/stage-c-runbook.md",
    }
    base.update(over)
    blob = json.dumps(base, ensure_ascii=False, indent=2) + "\n"
    base["attestation_digest"] = hashlib.sha256(
        blob.encode("utf-8")).hexdigest()
    return base


def token_text(**over) -> str:
    return json.dumps(token_dict(**over), ensure_ascii=False,
                      indent=2) + "\n"


def verify_ok(text: str, **kw) -> dict:
    return sct.verify_token(text, **kw)


# --------------------------------------------------------------------------
class TokenSchemaAndIntegrity(unittest.TestCase):
    def test_green_token_verifies(self):
        rep = verify_ok(token_text())
        self.assertTrue(rep["ok"])
        self.assertEqual(rep["verdict"], "VERIFIED")
        self.assertEqual(rep["findings"], [])

    def test_not_json_refused(self):
        with self.assertRaises(sct.StageCTokenError) as ctx:
            verify_ok("this is not json {")
        self.assertEqual(ctx.exception.verdict, "MALFORMED")

    def test_non_object_refused(self):
        with self.assertRaises(sct.StageCTokenError) as ctx:
            verify_ok("[1, 2, 3]")
        self.assertEqual(ctx.exception.verdict, "MALFORMED")

    def test_missing_required_key_refused(self):
        body = token_dict()
        body.pop("bindings")
        with self.assertRaises(sct.StageCTokenError) as ctx:
            verify_ok(json.dumps(body))
        self.assertEqual(ctx.exception.verdict, "MALFORMED")
        self.assertIn("bindings", ctx.exception.reason)

    def test_wrong_schema_refused(self):
        with self.assertRaises(sct.StageCTokenError) as ctx:
            verify_ok(token_text(schema_version="stage_c.runbook_attestation.v2"))
        self.assertEqual(ctx.exception.verdict, "SCHEMA_INVALID")

    def test_tampered_payload_breaks_digest(self):
        text = token_text()
        body = json.loads(text)
        body["gates"][0]["verdict"] = "FAIL"  # hand-edit without re-digest
        with self.assertRaises(sct.StageCTokenError) as ctx:
            verify_ok(json.dumps(body, indent=2) + "\n")
        self.assertEqual(ctx.exception.verdict, "INTEGRITY")

    def test_non_hex_digest_refused(self):
        body = token_dict()
        body["attestation_digest"] = "deadbeef"
        with self.assertRaises(sct.StageCTokenError) as ctx:
            verify_ok(json.dumps(body))
        self.assertEqual(ctx.exception.verdict, "INTEGRITY")

    def test_digest_recompute_is_the_emission_algorithm(self):
        body = token_dict()
        digest = body.pop("attestation_digest")
        self.assertEqual(sct.recompute_digest(body), digest)


class TokenCommitProvenance(unittest.TestCase):
    def test_equal_head_is_current(self):
        rep = verify_ok(token_text(candidate_commit="4d1979a"),
                        head_commit="4d1979a", ancestry=True)
        rec = [r for r in rep["checks"]
               if r["name"] == "candidate_commit_binding"]
        self.assertTrue(rep["ok"])
        self.assertIn("CURRENT", rec[0]["detail"])

    def test_ancestor_commit_is_continuous_provenance(self):
        rep = verify_ok(token_text(candidate_commit="bc39efb"),
                        head_commit="4d1979a", ancestry=True)
        rec = [r for r in rep["checks"]
               if r["name"] == "candidate_commit_binding"]
        self.assertTrue(rep["ok"])
        self.assertIn("ANCESTOR", rec[0]["detail"])

    def test_disconnected_commit_is_a_finding(self):
        rep = verify_ok(token_text(candidate_commit="deadbeef"),
                        head_commit="4d1979a", ancestry=False)
        self.assertFalse(rep["ok"])
        self.assertIn("COMMIT_PROVENANCE",
                      rep["findings"][0]["reason"])

    def test_undecidable_ancestry_fails_closed(self):
        rep = verify_ok(token_text(candidate_commit="deadbeef"),
                        head_commit="4d1979a", ancestry=None)
        self.assertFalse(rep["ok"])
        self.assertIn("COMMIT_PROVENANCE",
                      rep["findings"][0]["reason"])

    def test_empty_candidate_commit_is_a_finding(self):
        rep = verify_ok(token_text(candidate_commit=""),
                        head_commit=None)
        self.assertFalse(rep["ok"])
        self.assertIn("missing or empty", rep["findings"][0]["reason"])

    def test_no_head_reference_records_without_comparing(self):
        rep = verify_ok(token_text(candidate_commit="tokcommit"),
                        head_commit=None)
        self.assertTrue(rep["ok"])
        rec = [r for r in rep["checks"]
               if r["name"] == "candidate_commit_binding"]
        self.assertIn("recorded", rec[0]["detail"])


class TokenGateLedgerAndAcceptance(unittest.TestCase):
    def test_missing_gate_breaks_integrity(self):
        body = json.loads(token_text())
        body.pop("attestation_digest")
        body["gates"] = [g for g in body["gates"] if g["gate"] != "G4"]
        blob = json.dumps(body, ensure_ascii=False, indent=2) + "\n"
        body["attestation_digest"] = hashlib.sha256(
            blob.encode("utf-8")).hexdigest()
        with self.assertRaises(sct.StageCTokenError) as ctx:
            verify_ok(json.dumps(body, ensure_ascii=False, indent=2) + "\n")
        self.assertEqual(ctx.exception.verdict, "INTEGRITY")

    def test_failing_gate_is_a_finding(self):
        gates = [{"gate": f"G{i}", "name": f"gate {i}",
                  "verdict": "PASS", "detail": "ok"}
                 for i in range(1, 6)]
        gates[2]["verdict"] = "FAIL"
        gates[2]["detail"] = "two published ports"
        rep = verify_ok(token_text(gates=gates))
        self.assertFalse(rep["ok"])
        self.assertIn("G3", rep["findings"][0]["reason"])

    def test_probe_census_gap_breaks_integrity(self):
        body = json.loads(token_text())
        body.pop("attestation_digest")
        body["acceptance_run"]["probes"] = [
            p for p in body["acceptance_run"]["probes"]
            if p["name"] != "media_store"]
        blob = json.dumps(body, ensure_ascii=False, indent=2) + "\n"
        body["attestation_digest"] = hashlib.sha256(
            blob.encode("utf-8")).hexdigest()
        with self.assertRaises(sct.StageCTokenError) as ctx:
            verify_ok(json.dumps(body, ensure_ascii=False, indent=2) + "\n")
        self.assertEqual(ctx.exception.verdict, "INTEGRITY")
        self.assertIn("media_store", ctx.exception.reason)

    def test_failing_probe_is_a_finding(self):
        census = probe_census()
        census[5]["verdict"] = "FAIL"  # wordpress_rest
        rep = verify_ok(token_text(
            acceptance_run={"schema_version":
                            "stage_c.acceptance_run.v1",
                            "ok": False, "verdict": "FINDINGS",
                            "probes": census, "failing":
                            ["wordpress_rest"]}))
        self.assertFalse(rep["ok"])
        self.assertIn("wordpress_rest", rep["findings"][0]["reason"])

    def test_stack_identity_not_evidenced_5_of_5(self):
        census = probe_census()
        census[0]["detail"] = "engine-local rehearsal stack 3/5 running"
        rep = verify_ok(token_text(
            acceptance_run={"schema_version":
                            "stage_c.acceptance_run.v1",
                            "ok": False, "verdict": "FINDINGS",
                            "probes": census, "failing":
                            ["stack_identity"]}))
        self.assertFalse(rep["ok"])
        self.assertIn("stack_identity", [f["id"] for f in rep["findings"]])

    def test_media_probe_without_residue_marker_is_a_finding(self):
        census = probe_census()
        census[6]["detail"] = "contract round-trip ok (residue unknown)"
        rep = verify_ok(token_text(
            acceptance_run={"schema_version":
                            "stage_c.acceptance_run.v1",
                            "ok": True, "verdict": "ACCEPTED",
                            "probes": census, "failing": []}))
        self.assertFalse(rep["ok"])
        self.assertIn("media_zero_residue",
                      [f["id"] for f in rep["findings"]])

    def test_zero_event_ledger_is_a_finding(self):
        census = probe_census()
        census[3]["detail"] = "read-only counts: events.event_record=0 " \
                              "registry.mapping_entry=0 (zero writes)"
        rep = verify_ok(token_text(
            acceptance_run={"schema_version":
                            "stage_c.acceptance_run.v1",
                            "ok": True, "verdict": "ACCEPTED",
                            "probes": census, "failing": []}))
        self.assertFalse(rep["ok"])
        self.assertIn("event_ledger_nonzero",
                      [f["id"] for f in rep["findings"]])

    def test_unparseable_ledger_count_is_a_finding(self):
        census = probe_census()
        census[3]["detail"] = "counts unavailable"
        rep = verify_ok(token_text(
            acceptance_run={"schema_version":
                            "stage_c.acceptance_run.v1",
                            "ok": True, "verdict": "ACCEPTED",
                            "probes": census, "failing": []}))
        self.assertIn("event_ledger_nonzero",
                      [f["id"] for f in rep["findings"]])

    def test_binding_mismatch_against_live_artifact_is_a_finding(self):
        with tempfile.TemporaryDirectory() as td:
            env = Path(td) / "env.template"
            env.write_text("APP_ENV=staging\n", encoding="utf-8")
            rep = verify_ok(token_text(), env_path=env)
        self.assertFalse(rep["ok"])
        self.assertIn("binding_env_artifact_sha256",
                      [f["id"] for f in rep["findings"]])

    def test_binding_material_unprovided_is_digest_only(self):
        rep = verify_ok(token_text())
        self.assertTrue(rep["ok"])
        self.assertFalse(rep["binding_material_verified"])


class TokenAgainstCommittedArtifact(unittest.TestCase):
    def test_committed_token_verifies_digest_only(self):
        rep = verify_ok(_read(TOKEN))
        self.assertTrue(rep["ok"])
        self.assertEqual(rep["verdict"], "VERIFIED")

    def test_committed_token_bindings_match_live_artifacts(self):
        rep = verify_ok(_read(TOKEN), env_path=TEMPLATE,
                        manifest_path=MANIFEST,
                        grants_path=REPO / "docs" / "deployment"
                        / "stage-c-owner-grants.md")
        self.assertTrue(rep["ok"])
        self.assertTrue(rep["binding_material_verified"])

    def test_committed_token_provenance_against_head(self):
        head = sct.candidate_commit()
        tok_commit = sct.read_candidate_commit(_read(TOKEN))
        ancestry = sct.commit_relation(tok_commit)
        self.assertIsNotNone(ancestry)  # committed token MUST be rooted
        rep = verify_ok(_read(TOKEN), head_commit=head,
                        ancestry=ancestry)
        self.assertTrue(rep["ok"])
        rec = [r for r in rep["checks"]
               if r["name"] == "candidate_commit_binding"]
        self.assertTrue("ANCESTOR" in rec[0]["detail"]
                        or "CURRENT" in rec[0]["detail"])

    def test_hand_edited_committed_token_is_refused(self):
        body = json.loads(_read(TOKEN))
        body["candidate_commit"] = "f00df00"  # provenance forgery
        with self.assertRaises(sct.StageCTokenError) as ctx:
            verify_ok(json.dumps(body, ensure_ascii=False, indent=2) + "\n")
        self.assertEqual(ctx.exception.verdict, "INTEGRITY")


class TokenCliContract(unittest.TestCase):
    def test_cli_verifies_the_committed_token_rc0(self):
        r = subprocess.run([sys.executable,
                            str(REPO / "local" / "scripts"
                                / "stage_c_token.py")],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        self.assertIn("VERIFIED", r.stdout)

    def test_cli_refuses_garbage_token_rc2(self):
        with tempfile.TemporaryDirectory() as td:
            bad = Path(td) / "t.json"
            bad.write_text("{not json", encoding="utf-8")
            r = subprocess.run([sys.executable,
                                str(REPO / "local" / "scripts"
                                    / "stage_c_token.py"),
                                "--token", str(bad)],
                               capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn("REFUSED", r.stdout + r.stderr)


class LaunchAttestationTokenGate(unittest.TestCase):
    def go_attestation(self) -> dict:
        return {"launch_verdict": "GO", "blockers": [],
                "attestation_hash": "x" * 64, "candidate_commit": "test",
                "config_fingerprint": "f" * 64,
                "approval_state": "unsigned",
                "health_report": {"overall": "PASS", "probes": []}}

    def _main(self, argv, att=None, env=None):
        att = att if att is not None else self.go_attestation()
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(la, "run_attestation",
                               return_value=att), \
             mock.patch.object(la, "stack_up", return_value=True), \
             mock.patch.dict(os.environ, env or {}), \
             contextlib.redirect_stdout(out), \
             contextlib.redirect_stderr(err):
            rc = la.main(argv)
        return rc, out.getvalue(), err.getvalue()

    def test_verified_token_is_silent_grants_blocker_only(self):
        rc, out, err = self._main(["--check-stage-c"])
        self.assertEqual(rc, 1)  # SC-GRANTS (0/12) ⇒ NO_GO
        self.assertIn("SC-GRANTS", out)
        self.assertNotIn("SC-RUNBOOK", out)
        self.assertNotIn("REFUSED", err)

    def test_token_findings_append_sc_runbook_blocker(self):
        findings_report = {"ok": False, "verdict": "FINDINGS",
                           "token_candidate_commit": "tokcommit",
                           "checks": [], "findings": [
                               {"id": "event_ledger_nonzero",
                                "verdict": "FAIL",
                                "reason": "ledger zero"}],
                           "binding_material_verified": False}
        with mock.patch.object(sct, "verify_token",
                               return_value=findings_report):
            rc, out, err = self._main(["--check-stage-c"])
        self.assertEqual(rc, 1)
        # both clearance legs deny; the grants leg runs FIRST and its
        # downgrade means the token leg must NOT re-mutate the blocker
        # set (never mutate an existing NO_GO — battery-pinned)
        self.assertEqual(err.count("DENIED"), 2)
        self.assertIn("SC-GRANTS", out)
        self.assertNotIn("SC-RUNBOOK", out)
        self.assertIn("event_ledger_nonzero", err)

    def test_token_findings_downgrade_a_fresh_go(self):
        # with the grants checklist fully signed, a findings-bearing
        # token is the ONLY blocker — GO downgraded, SC-RUNBOOK named
        findings_report = {"ok": False, "verdict": "FINDINGS",
                           "token_candidate_commit": "tokcommit",
                           "checks": [], "findings": [
                               {"id": "media_zero_residue",
                                "verdict": "FAIL", "reason": "residue"}],
                           "binding_material_verified": False}
        authorized = {"ok": True, "verdict": "AUTHORIZED",
                      "signed_count": 12, "rows": {}, "findings": []}
        with tempfile.TemporaryDirectory() as td:
            grants = Path(td) / "signed.md"
            rows = "\n".join(f"| SC-{i} | Owner Name | 2026-09-29 | "
                             f"evidence-{i} | |"
                             for i in range(1, 13))
            grants.write_text("\n## 3. Signature block\n\n"
                              "| # | Granted by (name) | Date | Evidence "
                              "reference | Notes |\n"
                              "|---|-------------------|------|"
                              "--------------------|-------|\n" + rows
                              + "\n", encoding="utf-8")
            with mock.patch.object(sct, "verify_token",
                                   return_value=findings_report), \
                 mock.patch("verify_stage_c_grants.verify_grants",
                            return_value=authorized), \
                 mock.patch.object(sct, "commit_relation",
                                   return_value=True), \
                 mock.patch.dict(os.environ,
                                 {"SC_GRANTS_ARTIFACT": str(grants)}):
                rc, out, err = self._main(["--check-stage-c"])
        self.assertEqual(rc, 1)
        self.assertIn("SC-RUNBOOK", out)
        self.assertNotIn("SC-GRANTS", out)
        # exactly ONE DENIED — the token leg; the grants leg is silent
        self.assertEqual(err.count("DENIED"), 1)
        self.assertIn("runbook attestation token", err)
        self.assertNotIn("owner grant checklist", err)

    def test_missing_token_refuses_rc2_before_report(self):
        rc, out, err = self._main(
            ["--check-stage-c"],
            env={"SC_TOKEN": "/nonexistent/stage-c-attestation.json"})
        self.assertEqual(rc, 2)
        self.assertEqual(out, "")  # no report printed
        self.assertIn("unreadable", err)

    def test_corrupted_token_refuses_rc2(self):
        with tempfile.TemporaryDirectory() as td:
            bad = Path(td) / "token.json"
            bad.write_text("{corrupted", encoding="utf-8")
            rc, out, err = self._main(
                ["--check-stage-c"], env={"SC_TOKEN": str(bad)})
        self.assertEqual(rc, 2)
        self.assertEqual(out, "")
        self.assertIn("MALFORMED", err)

    def test_schema_invalid_token_refuses_rc2(self):
        with tempfile.TemporaryDirectory() as td:
            bad = Path(td) / "token.json"
            bad.write_text(json.dumps({"schema_version": "other.v9"}),
                           encoding="utf-8")
            rc, out, err = self._main(
                ["--check-stage-c"], env={"SC_TOKEN": str(bad)})
        self.assertEqual(rc, 2)
        # a wrong schema_version without the required key set is
        # MALFORMED (the key gate precedes the schema comparison)
        self.assertIn("MALFORMED", err)

    def test_flag_absent_leaves_attestation_untouched(self):
        rc, out, err = self._main([])
        self.assertEqual(rc, 0)
        self.assertNotIn("SC-RUNBOOK", out)
        self.assertNotIn("SC-GRANTS", out)

    def test_token_findings_never_upgrade_a_no_go(self):
        att = dict(self.go_attestation(), launch_verdict="NO_GO",
                   blockers=["BAC-001"])
        findings_report = {"ok": False, "verdict": "FINDINGS",
                           "token_candidate_commit": "tokcommit",
                           "checks": [], "findings": [
                               {"id": "G5", "verdict": "FAIL",
                                "reason": "acceptance"}],
                           "binding_material_verified": False}
        with mock.patch.object(sct, "verify_token",
                               return_value=findings_report):
            rc, out, err = self._main(["--check-stage-c"], att=att)
        self.assertEqual(rc, 1)
        self.assertIn("blockers: BAC-001", out)
        self.assertNotIn("SC-RUNBOOK", out)


class BackupPolicyClearance(unittest.TestCase):
    def test_committed_artifacts_clear(self):
        rep = bc.verify(_read(POLICY), _read(MANIFEST), _read(TEMPLATE))
        self.assertTrue(rep["ok"])
        self.assertEqual(rep["verdict"], "CLEAR")
        self.assertEqual(len(rep["checks"]), 14)

    def test_active_backup_value_fails_closed(self):
        rep = bc.verify(_read(POLICY), _read(MANIFEST),
                        _read(TEMPLATE) + "BACKUP_S3_BUCKET=real-bucket\n")
        self.assertEqual(rep["verdict"], "CANNOT_CLEAR")
        self.assertIn("V5_backup_placeholders", rep["failing"])

    def test_policy_without_media_row_fails_closed(self):
        policy = "\n".join(l for l in _read(POLICY).splitlines()
                           if "`media_data`" not in l)
        rep = bc.verify(policy, _read(MANIFEST), _read(TEMPLATE))
        self.assertEqual(rep["verdict"], "CANNOT_CLEAR")
        self.assertTrue(any(f.startswith("V2_") for f in rep["failing"]))

    def test_manifest_missing_volume_fails_census(self):
        manifest = _read(MANIFEST).replace("  mock_state: {}\n", "")
        rep = bc.verify(_read(POLICY), manifest, _read(TEMPLATE))
        self.assertIn("V1_volume_census", rep["failing"])

    def test_rpo_floor_violation_fails_closed(self):
        policy = _read(POLICY).replace("Every 6 h + pre/post", "Weekly +")
        rep = bc.verify(policy, _read(MANIFEST), _read(TEMPLATE))
        self.assertIn("V2_rpo_canonical", rep["failing"])

    def test_zero_leak_no_credential_values_in_verdicts(self):
        rep = bc.verify(_read(POLICY), _read(MANIFEST),
                        _read(TEMPLATE) + "BACKUP_S3_BUCKET=real-bucket\n")
        blob = json.dumps(rep)
        self.assertNotIn("real-bucket", blob)  # name never the value
        for frag in ("engine-local-media-only", "AKIA", "sk-live",
                     "BEGIN PRIVATE"):
            self.assertNotIn(frag, blob)

    def test_cli_clear_rc0_and_missing_artifact_rc2(self):
        r = subprocess.run([sys.executable,
                            str(REPO / "local" / "scripts"
                                / "stage_c_backup_checks.py")],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        self.assertIn("CLEAR", r.stdout)
        r2 = subprocess.run([sys.executable,
                             str(REPO / "local" / "scripts"
                                 / "stage_c_backup_checks.py"),
                             "--policy", "/nonexistent/policy.md"],
                            capture_output=True, text=True)
        self.assertEqual(r2.returncode, 2)


class CommittedArtifactConsistency(unittest.TestCase):
    def test_defaults_exist_in_repo(self):
        self.assertTrue(TOKEN.exists())
        self.assertTrue(POLICY.exists())
        self.assertTrue(MANIFEST.exists())
        self.assertTrue(TEMPLATE.exists())

    def test_census_and_gate_constants_pinned(self):
        self.assertEqual(len(sct.REQUIRED_PROBES), 10)
        self.assertIn("media_store", sct.REQUIRED_PROBES)
        self.assertIn("canonical_event_store", sct.REQUIRED_PROBES)
        self.assertEqual(sct.GATE_ORDER,
                         ("G1", "G2", "G3", "G4", "G5"))
        self.assertEqual(bc.POLICY_VOLUMES,
                         ("canonical_data", "woo_data_db", "woo_data",
                          "media_data", "n8n_data", "mock_state"))

    def test_token_verifier_is_ast_pure_of_forbidden_transports(self):
        # the verifier's I/O surface is subprocess-git + file reads
        # only — no network imports (house convention for gate modules)
        import ast as _ast
        tree = _ast.parse(_read(REPO / "local" / "scripts"
                                / "stage_c_token.py"))
        imported = set()
        for node in _ast.walk(tree):
            if isinstance(node, _ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, _ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertNotIn("urllib", imported)
        self.assertNotIn("socket", imported)
        self.assertNotIn("http", imported)


if __name__ == "__main__":
    unittest.main()

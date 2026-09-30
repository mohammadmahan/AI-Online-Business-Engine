"""Stage C attestation-token verification (operator command) — Dokploy
plan §23 Layer 2, the read-side counterpart of `stage_c_runbook.py` G6.

Consumes the emitted runbook token
(`docs/deployment/stage-c-attestation.json`,
`stage_c.runbook_attestation.v1`) and FAILS CLOSED unless every layer
of the artifact verifies:

  SCHEMA      — parses as JSON, carries the exact schema_version, and
                has the required top-level key set (missing key = not
                assessable, never a pass)
  INTEGRITY   — `attestation_digest` recomputes byte-exactly over the
                token blob WITHOUT the digest (the G6 emission
                algorithm re-run by the consumer — a tampered, hand-
                edited, or truncated token is refused, never trusted);
                the three artifact bindings are SHA-256 hex digests,
                and — when the artifacts are provided — MATCH the live
                files byte-for-byte
  COMMIT      — `candidate_commit` binds the token to the candidate's
                history: it must equal the current HEAD (CURRENT) or
                be an ancestor of it (ANCESTOR — the durable token
                documents the gate evidence at its emission commit;
                every commit AFTER an emission shifts HEAD, so exact
                equality cannot be the standing criterion); a commit
                disconnected from HEAD is a finding — evidence
                provenance broken. The D-138 attestation itself is
                what binds the launch decision to the current
                candidate commit.
  GATES       — the gate ledger covers EXACTLY G1..G5 with every
                entry verdicting PASS; G6 (the emission gate) is
                evidenced by the verified token itself — its
                existence plus digest integrity, re-proven here
                before the ledger is trusted
  ACCEPTANCE  — the embedded `stage_c.acceptance_run.v1` payload is
                intact and green: the full ten-probe census present,
                every probe PASS, the sanctioned engine-local stack
                identity 5/5, the media_store probe carrying the
                zero-residue marker (SigV4 round-trip put/get/head/
                delete/delete-404), and the canonical event ledger
                count non-zero (`events.event_record` > 0; upload ≠
                restoration evidence — D-137 — and a zero event store
                is not an attested one)

Verdict taxonomy (fail closed, ordered — the first structural failure
stops the analysis; verdict-bearing findings accumulate):

  MALFORMED            — not JSON / not an object / required keys or
                         payload shape missing
  SCHEMA_INVALID       — wrong schema_version
  INTEGRITY            — digest mismatch, non-hex binding, binding
                         mismatch against a provided artifact, or a
                         probe-census gap (a missing census row cannot
                         carry a verdict)
  COMMIT_PROVENANCE    — token candidate_commit is disconnected from
                         the current HEAD (not an ancestor, or
                         ancestry undecidable)
  GATE_FINDINGS        — a ledgered gate verdicts anything but PASS
  ACCEPTANCE_FINDINGS  — a probe verdicts non-PASS, the stack identity
                         is not evidenced 5/5, the media probe lost
                         the zero-residue marker, or the event ledger
                         count is zero/unparseable

Exit contract (0/1/2):  0  token VERIFIED · 1 = verdict-bearing findings (commit provenance
     broken, a gate not PASS, acceptance integrity findings) ·
  2 = missing/corrupted/schema-invalid/integrity-failing (cannot
     assess). `launch_attestation.py --check-stage-c` refuses
     INFRASTRUCTURE deployment clearance on ANY of the three — fail
     closed.

Zero-leak (D-045/D-124): reasons carry gate/probe NAMES, verdicts, and
short structural markers — never token payloads, artifact bytes, or
credential material.

Usage:
  python3 local/scripts/stage_c_token.py [--token PATH] [--json]
      [--env PATH] [--manifest PATH] [--grants PATH]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

TOKEN_SCHEMA = "stage_c.runbook_attestation.v1"
ACCEPTANCE_SCHEMA = "stage_c.acceptance_run.v1"
# The gate ledger as carried inside the emitted token: G1..G5. G6 is
# the emission gate — stage_c_runbook.run_gates() appends it to the
# RUN report only, after write_fn; inside the token its evidence IS
# the token (existence + digest integrity).
GATE_ORDER = ("G1", "G2", "G3", "G4", "G5")

# The full acceptance-probe census of stage_c_acceptance.run_probes().
REQUIRED_PROBES = (
    "stack_identity", "canonical_pg", "canonical_schema",
    "canonical_event_store", "mysql_woo", "wordpress_rest",
    "media_store", "n8n_tunnel", "decision_ledger",
    "synthetic_data_guard",
)
STACK_PROBE = "stack_identity"
MEDIA_PROBE = "media_store"
LEDGER_PROBE = "canonical_event_store"
STACK_MARK = "5/5"  # the PASS detail of the stack-identity probe
RESIDUE_MARKERS = ("zero residue",)
LEDGER_RE = re.compile(r"events\.event_record=(\d+)")
HEX64_RE = re.compile(r"\A[0-9a-f]{64}\Z")

REQUIRED_KEYS = (
    "schema_version", "compatible_with", "candidate_commit",
    "owner_grants", "bindings", "gates", "acceptance_run",
    "attestation_digest",
)
REQUIRED_BINDINGS = (
    "env_artifact_sha256", "manifest_sha256", "grants_artifact_sha256",
)

DEFAULT_TOKEN = ROOT / "docs" / "deployment" / "stage-c-attestation.json"
DEFAULT_ENV = ROOT / ".env.staging.template"
DEFAULT_MANIFEST = ROOT / "local" / "infra" / "compose.staging.yml"
DEFAULT_GRANTS = ROOT / "docs" / "deployment" / "stage-c-owner-grants.md"


class StageCTokenError(RuntimeError):
    """The token is missing, corrupted, schema-invalid, or fails
    integrity — the consumer must refuse (fail closed)."""

    def __init__(self, verdict: str, reason: str):
        super().__init__(f"{verdict}: {reason}")
        self.verdict = verdict
        self.reason = reason


# --------------------------------------------------------------------------
# shared helpers
# --------------------------------------------------------------------------
def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def candidate_commit() -> str:
    out = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        capture_output=True, text=True, cwd=str(ROOT))
    return out.stdout.strip() if out.returncode == 0 else "unknown"


def commit_relation(short: str) -> Optional[bool]:
    """Evidence-provenance test for a token's candidate_commit.

    True  = the commit is an ancestor of (or equal to) HEAD — the
            token's evidence is connected to the current candidate.
    False = known NOT an ancestor — provenance broken.
    None  = undecidable (unknown revision, no git, bare repo) — the
            consumer must treat this as a finding (fail closed).
    """
    out = subprocess.run(
        ["git", "merge-base", "--is-ancestor", short, "HEAD"],
        capture_output=True, text=True, cwd=str(ROOT))
    if out.returncode == 0:
        return True
    if out.returncode == 1:
        return False
    return None


def read_candidate_commit(token_text: str) -> str:
    """Candidate commit extracted from a token WITHOUT verification —
    only for pre-verification ancestry lookups. verify_token() is the
    authority (a malformed token is refused there)."""
    try:
        return json.loads(token_text).get("candidate_commit", "")
    except ValueError:
        return ""


def recompute_digest(token_without_digest: Dict) -> str:
    """The G6 emission algorithm re-run by the consumer: sha256 over
    the canonical JSON blob WITHOUT the digest key, plus one newline."""
    blob = json.dumps(token_without_digest, ensure_ascii=False,
                      indent=2) + "\n"
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# verification layers
# --------------------------------------------------------------------------
def _probe_map(acceptance: Dict) -> Dict[str, Dict]:
    return {p.get("name"): p for p in acceptance.get("probes", [])
            if isinstance(p, dict)}


def _verify_bindings(token: Dict, *, env_path: Optional[Path] = None,
                     manifest_path: Optional[Path] = None,
                     grants_path: Optional[Path] = None) -> Tuple[List[Dict], bool]:
    """Binding checks: structural (hex shape) is INTEGRITY class; a
    mismatch against a provided live artifact is BINDING_MISMATCH.
    Returns (records, material_verified) — material_verified is True
    only when every PROVIDED artifact's digest was compared and
    matched (an unprovided artifact is digest-only, never assumed)."""
    records: List[Dict] = []
    compared: List[bool] = []
    bindings = token.get("bindings")
    if not isinstance(bindings, dict):
        raise StageCTokenError(
            "MALFORMED", "bindings payload missing or not an object")
    for key in REQUIRED_BINDINGS:
        value = bindings.get(key)
        if not isinstance(value, str) or not HEX64_RE.match(value):
            records.append({"name": f"binding_{key}", "verdict": "FAIL",
                            "detail": "binding is not a SHA-256 hex digest"})
            continue
        records.append({"name": f"binding_{key}", "verdict": "PASS",
                        "detail": "SHA-256 hex digest"})
    path_for = {"env_artifact_sha256": env_path,
                "manifest_sha256": manifest_path,
                "grants_artifact_sha256": grants_path}
    for key, path in path_for.items():
        if path is None or not Path(path).exists():
            records.append({
                "name": f"binding_{key}", "verdict": "PASS",
                "detail": "binding material not provided — digest-only "
                          "verification (recorded, not assumed)"})
            continue
        try:
            digest = sha256_file(path)
        except OSError as e:
            records.append({
                "name": f"binding_{key}", "verdict": "PASS",
                "detail": f"binding artifact unreadable — digest-only "
                          f"verification ({type(e).__name__})"})
            continue
        if digest != token["bindings"][key]:
            compared.append(False)
            records.append({
                "name": f"binding_{key}", "verdict": "FAIL",
                "detail": "live artifact digest MISMATCHES the token "
                          "binding — the token predates the current "
                          "artifact (regenerate via stage_c_runbook.py)"})
        else:
            compared.append(True)
            records.append({"name": f"binding_{key}", "verdict": "PASS",
                            "detail": "matches the live artifact"})
    return records, bool(compared) and all(compared)


def _binding_findings(records: List[Dict]) -> List[Dict]:
    """Verdict-bearing findings from binding records — a FAILed
    binding is a finding, not merely a recorded check."""
    return [{"id": r["name"], "verdict": "FAIL", "reason": r["detail"]}
            for r in records if r["verdict"] == "FAIL"]


def verify_token(
        token_text: str, *, head_commit: Optional[str] = None,
        ancestry: Optional[bool] = None,
        env_path: Optional[Path] = None, manifest_path: Optional[Path] = None,
        grants_path: Optional[Path] = None) -> Dict:
    """Pure verdict over the token text — battery-testable, no I/O
    except the optional artifact-binding reads. Fail closed: the first
    structural defect raises via StageCTokenError; verdict-bearing
    findings accumulate into the report.

    `head_commit` enables the commit-provenance layer; `ancestry` is
    its injected verdict (`commit_relation()` at the CLI, a pinned
    bool in the battery)."""
    # -- SCHEMA layer (structural → raise) --------------------------------
    try:
        token = json.loads(token_text)
    except ValueError as e:
        raise StageCTokenError("MALFORMED", f"not valid JSON: "
                               f"{type(e).__name__}")
    if not isinstance(token, dict):
        raise StageCTokenError("MALFORMED", "token is not a JSON object")
    missing_keys = [k for k in REQUIRED_KEYS if k not in token]
    if missing_keys:
        raise StageCTokenError(
            "MALFORMED", f"required keys missing: {missing_keys}")
    if token["schema_version"] != TOKEN_SCHEMA:
        raise StageCTokenError(
            "SCHEMA_INVALID",
            f"schema_version {token['schema_version']!r} — expected "
            f"{TOKEN_SCHEMA!r}")

    # -- INTEGRITY layer (structural → raise) ------------------------------
    digest = token["attestation_digest"]
    if not isinstance(digest, str) or not HEX64_RE.match(digest):
        raise StageCTokenError("INTEGRITY",
                               "attestation_digest is not a SHA-256 hex "
                               "digest")
    body = {k: v for k, v in token.items() if k != "attestation_digest"}
    recomputed = recompute_digest(body)
    if recomputed != digest:
        raise StageCTokenError(
            "INTEGRITY",
            "attestation_digest mismatch — the token blob does not "
            "reproduce its digest (tampered, hand-edited, or truncated)")

    findings: List[Dict] = []
    records: List[Dict] = []

    # -- COMMIT layer (verdict-bearing — evidence-provenance) ---------------
    token_commit = token["candidate_commit"]
    if not isinstance(token_commit, str) or not token_commit:
        findings.append({"id": "candidate_commit", "verdict": "FAIL",
                         "reason": "candidate_commit missing or empty"})
    elif head_commit is None:
        records.append({
            "name": "candidate_commit_binding", "verdict": "PASS",
            "detail": f"token bound to commit {token_commit} (no "
                      "current-commit reference provided — recorded, "
                      "not compared)"})
    elif token_commit == head_commit:
        records.append({
            "name": "candidate_commit_binding", "verdict": "PASS",
            "detail": f"token bound to the CURRENT candidate commit "
                      f"{token_commit}"})
    elif ancestry:
        records.append({
            "name": "candidate_commit_binding", "verdict": "PASS",
            "detail": f"token bound to ANCESTOR commit {token_commit} "
                      f"of the current candidate {head_commit} — "
                      "evidence provenance continuous"})
    else:
        findings.append({
            "id": "candidate_commit", "verdict": "FAIL",
            "reason": f"token bound to commit {token_commit} which is "
                      f"NOT an ancestor of the current candidate "
                      f"{head_commit} — evidence provenance broken "
                      "(COMMIT_PROVENANCE)"})

    # -- artifact bindings ---------------------------------------------------
    binding_records, material_verified = _verify_bindings(
        token, env_path=env_path, manifest_path=manifest_path,
        grants_path=grants_path)
    records.extend(binding_records)
    findings.extend(_binding_findings(binding_records))

    # -- ACCEPTANCE payload shape (structural → raise) -----------------------
    acceptance = token["acceptance_run"]
    if not isinstance(acceptance, dict):
        raise StageCTokenError(
            "MALFORMED", "acceptance_run payload missing or not an object")
    if acceptance.get("schema_version") != ACCEPTANCE_SCHEMA:
        raise StageCTokenError(
            "MALFORMED", f"acceptance_run schema_version "
            f"{acceptance.get('schema_version')!r} — expected "
            f"{ACCEPTANCE_SCHEMA!r}")
    probes = acceptance.get("probes")
    if not isinstance(probes, list) or not probes:
        raise StageCTokenError(
            "MALFORMED", "acceptance_run carries no probe census")

    # probe census — a missing row cannot carry a verdict (INTEGRITY)
    pmap = _probe_map(acceptance)
    missing_probes = [n for n in REQUIRED_PROBES if n not in pmap]
    if missing_probes:
        raise StageCTokenError(
            "INTEGRITY",
            f"acceptance census incomplete — missing probes: "
            f"{missing_probes}")

    # -- ACCEPTANCE verdict layer (findings accumulate) ----------------------
    bad_probes = [n for n in REQUIRED_PROBES
                  if pmap[n].get("verdict") != "PASS"]
    if bad_probes:
        findings.append({
            "id": "acceptance_probes", "verdict": "FAIL",
            "reason": f"probes not PASS: {bad_probes}"})
    else:
        records.append({
            "name": "acceptance_probes", "verdict": "PASS",
            "detail": f"all {len(REQUIRED_PROBES)} probes PASS"})

    stack = pmap[STACK_PROBE]
    if stack.get("verdict") == "PASS" and STACK_MARK in stack.get("detail", ""):
        records.append({
            "name": "stack_identity", "verdict": "PASS",
            "detail": "sanctioned engine-local rehearsal stack "
                      "evidenced 5/5 in the acceptance evidence"})
    else:
        findings.append({
            "id": "stack_identity", "verdict": "FAIL",
            "reason": "stack identity not evidenced 5/5 — the "
                      "sanctioned rehearsal surface is unproven"})

    media = pmap[MEDIA_PROBE]
    if media.get("verdict") == "PASS" and any(
            m in media.get("detail", "") for m in RESIDUE_MARKERS):
        records.append({
            "name": "media_zero_residue", "verdict": "PASS",
            "detail": "SigV4 round-trip with the zero-residue marker "
                      "(put/get/head/delete/delete-404)"})
    else:
        findings.append({
            "id": "media_zero_residue", "verdict": "FAIL",
            "reason": "media probe lacks the zero-residue marker or is "
                      "not PASS — residue-bearing storage contract"})

    ledger = pmap[LEDGER_PROBE]
    m = LEDGER_RE.search(ledger.get("detail", ""))
    if ledger.get("verdict") == "PASS" and m and int(m.group(1)) > 0:
        records.append({
            "name": "event_ledger_nonzero", "verdict": "PASS",
            "detail": f"events.event_record={m.group(1)} (non-zero, "
                      "read-only count)"})
    else:
        findings.append({
            "id": "event_ledger_nonzero", "verdict": "FAIL",
            "reason": "canonical event ledger count is zero or "
                      "unparseable — a zero event store is not an "
                      "attested one"})

    # -- GATES layer (verdict-bearing; structural gap → raise) ---------------
    gates = token["gates"]
    if not isinstance(gates, list):
        raise StageCTokenError("MALFORMED",
                               "gate ledger missing or not a list")
    ids = [g.get("gate") for g in gates if isinstance(g, dict)]
    if sorted(ids) != sorted(GATE_ORDER):
        raise StageCTokenError(
            "INTEGRITY",
            f"gate ledger covers {ids} — expected exactly "
            f"{list(GATE_ORDER)} (G6 is the emission gate: its "
            "evidence is this token's verified digest)")
    for g in gates:
        if g.get("verdict") != "PASS":
            findings.append({
                "id": g["gate"], "verdict": "FAIL",
                "reason": f"gate {g['gate']} ({g.get('name', '?')}) "
                          f"verdicts {g.get('verdict')!r}"})
    records.append({
        "name": "gate_ledger_G1_G5", "verdict": "PASS",
        "detail": "all five ledgered gates PASS; G6 (emission) "
                  "evidenced by the token itself — digest integrity "
                  "re-proven above"})

    ok = not findings
    return {
        "schema_version": "stage_c.token_verification.v1",
        "compatible_with": "qa.launch_attestation.v1",
        "ok": ok,
        "verdict": "VERIFIED" if ok else "FINDINGS",
        "token_candidate_commit": token["candidate_commit"],
        "checks": records,
        "findings": findings,
        "binding_material_verified": material_verified,
    }


def load_token(path: Path = DEFAULT_TOKEN, **kwargs) -> Dict:
    """Read + verify; raises StageCTokenError on missing, corrupted,
    schema-invalid, or integrity-failing tokens (fail closed)."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as e:
        raise StageCTokenError("MISSING",
                               f"token artifact unreadable ({e})")
    report = verify_token(text, **kwargs)
    if not report["ok"]:
        raise StageCTokenError(
            "FINDINGS", "; ".join(f["reason"] for f in report["findings"]))
    return report


def render(report: Dict) -> str:
    lines = ["=== STAGE C ATTESTATION TOKEN VERIFICATION ==="]
    for r in report["checks"]:
        mark = "ok  " if r["verdict"] == "PASS" else "FAIL"
        lines.append(f"  [{mark}] {r['name']:<28} {r['detail']}")
    for f in report["findings"]:
        lines.append(f"  [FAIL] {f['id']:<28} {f['reason']}")
    lines.append(
        f"verdict {report['verdict']} — token bound to commit "
        f"{report['token_candidate_commit']}")
    if report["ok"]:
        lines.append("Stage C technical clearance INGESTED — execution "
                     "authorization remains the signed SC-1..SC-12 "
                     "checklist.")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Verify the Stage C runbook attestation token "
                    "(fail closed).")
    ap.add_argument("--token", default=str(DEFAULT_TOKEN))
    ap.add_argument("--env", default=str(DEFAULT_ENV),
                    help="env artifact for binding verification "
                         "(omit to skip)")
    ap.add_argument("--manifest", default=str(DEFAULT_MANIFEST),
                    help="manifest for binding verification (omit to "
                         "skip)")
    ap.add_argument("--grants", default=str(DEFAULT_GRANTS),
                    help="grants artifact for binding verification "
                         "(omit to skip)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    def _binding(path_str: str) -> Optional[Path]:
        p = Path(path_str)
        return p if p.exists() else None

    try:
        raw = Path(args.token).read_text(encoding="utf-8")
    except OSError as e:
        if args.json:
            print(json.dumps({"ok": False, "verdict": "MISSING",
                              "error": str(e)}))
        else:
            print(f"[FAIL] Stage C token REFUSED — MISSING: {e}")
        return 2
    try:
        report = load_token(
            Path(args.token), head_commit=candidate_commit(),
            ancestry=commit_relation(read_candidate_commit(raw)),
            env_path=_binding(args.env),
            manifest_path=_binding(args.manifest),
            grants_path=_binding(args.grants))
    except StageCTokenError as e:
        if args.json:
            print(json.dumps({"ok": False, "verdict": e.verdict,
                              "error": e.reason}))
        else:
            print(f"[FAIL] Stage C token REFUSED — {e.verdict}: "
                  f"{e.reason}")
        return 2

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render(report))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

"""Stage C owner-grants readiness audit (operator command).

Audits `docs/deployment/stage-c-owner-grants.md` for SIGN-OFF
READINESS before the owner touches it: every grant slot SC-1..SC-12
must be structurally ready to receive a signature (a complete §2
matrix row and an empty, well-formed §3 signature row), while the
FAIL-CLOSED verdict stays exactly what the machine gate enforces —
the checklist is NOT authorized until every §3 row carries name,
date, and evidence reference, and the verifier refuses on ANY
structural defect.

This audit adds structure-only checks the verifier deliberately
leaves to the human eye (a defect here is not yet a signature — but
it WOULD block one):

  SLOT CENSUS        — exactly twelve slots SC-1..SC-12, no gaps,
                       no duplicates, in both the §2 matrix and the
                       §3 signature block
  MATRIX COMPLETENESS— every §2 row carries grant item, source,
                       grant form, binding, and expiry columns
  SIGNATURE CELL SHAPE — every §3 row has exactly 5 cells with the
                       value cells EMPTY (nothing pre-signed: a
                       half-filled row is flagged, never trusted)
  PRE-FILL COHERENCE — the §3 RATIFICATION-PENDING notes match the
                       §2 pre-filled set exactly (SC-7, SC-8, SC-9,
                       SC-11, SC-12); a pre-filled DECISION value in
                       §2 without its pending note in §3 is a defect
  FAIL-CLOSED VERDICT— the authorization verdict of the REAL
                       verifier (`verify_stage_c_grants.py`) is
                       echoed verbatim: NOT_AUTHORIZED is the
                       required standing answer while unsigned

`--simulate-sign` exercises the positive side OFFLINE-ONLY: it feeds
the verifier a synthetic copy with all twelve rows completed and
asserts AUTHORIZED — proving the checklist becomes machine-authorized
when (and only when) the real signatures land. It NEVER writes the
artifact (D-045 zero-mutation; the real artifact changes only when
the owner signs it).

Exit contract: 0 = readiness complete AND the standing verdict is the
required fail-closed one (NOT_AUTHORIZED while unsigned / AUTHORIZED
once fully signed) · 1 = readiness or coherence defects · 2 =
artifact unreadable or structurally unusable.

Zero-leak (D-045/D-124): findings carry row ids and structural
markers — never signature values.

Usage:
  python3 local/scripts/stage_c_grants_audit.py [--artifact PATH]
      [--json] [--simulate-sign]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

SCHEMA = "stage_c.grants_readiness_audit.v1"

DEFAULT_ARTIFACT = ROOT / "docs" / "deployment" / "stage-c-owner-grants.md"

EXPECTED_ROWS = [f"SC-{i}" for i in range(1, 13)]
# §1 fail-closed rules + §2/§3 anchors the artifact must carry
STRUCTURE_MARKS = (
    "## 2. Sign-off matrix",
    "## 3. Signature block",
    "## 4. Gate exit criteria",
    "Every row is blocking",
    "| # | Granted by (name) | Date | Evidence reference | Notes |",
)
# §2 matrix rows pre-filled with owner-directed decision values —
# each MUST carry the matching RATIFICATION-PENDING note in §3
EXPECTED_PREFILLED = ("SC-7", "SC-8", "SC-9", "SC-11", "SC-12")
ROW_ID_RE = re.compile(r"\ASC-\d+\Z")
MANDATORY_MATRIX_CELLS = 6  # | # | item | source | form | binding | expiry |


class GrantsAuditError(RuntimeError):
    """The artifact is unreadable or structurally unusable (exit 2)."""


# --------------------------------------------------------------------------
# parsing helpers (structure-only; the VERIFIER owns authorization)
# --------------------------------------------------------------------------
def read_artifact(path: Path = DEFAULT_ARTIFACT) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as e:
        raise GrantsAuditError(f"grant artifact unreadable: {e}")


def _table_rows(text: str, header_mark: str,
                section_mark: str) -> Tuple[List[List[str]], List[str]]:
    """Rows of the FIRST table under `header_mark`, plus section
    headers seen after it (to stop at the section boundary)."""
    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines)
                  if l.strip() == header_mark), None)
    if start is None:
        return [], []
    rows: List[List[str]] = []
    for line in lines[start + 1:]:
        stripped = line.strip()
        if stripped.startswith("## "):
            break
        if stripped.startswith("|"):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if all(set(c) <= {"-", ":", " "} for c in cells):
                continue  # separator row
            rows.append(cells)
    return rows, []


def _matrix_rows(text: str) -> Dict[str, List[str]]:
    rows, _ = _table_rows(text, "## 2. Sign-off matrix", "")
    out: Dict[str, List[str]] = {}
    for cells in rows:
        if cells and ROW_ID_RE.match(cells[0]):
            out[cells[0]] = cells
    return out


def _signature_rows(text: str) -> Dict[str, List[str]]:
    rows, _ = _table_rows(text, "## 3. Signature block", "")
    out: Dict[str, List[str]] = {}
    for cells in rows:
        if cells and ROW_ID_RE.match(cells[0]):
            out[cells[0]] = cells
    return out


def _prefilled_in_matrix(text: str) -> List[str]:
    """Slots whose §2 row declares a PRE-FILLED decision/value."""
    prefilled = []
    for rid, cells in sorted(_matrix_rows(text).items()):
        if any("PRE-FILLED" in c.upper() for c in cells[1:]):
            prefilled.append(rid)
    return prefilled


def _pending_in_signature(text: str) -> List[str]:
    """Slots whose §3 notes cell carries RATIFICATION-PENDING."""
    pending = []
    for rid, cells in sorted(_signature_rows(text).items()):
        if len(cells) >= 5 and "RATIFICATION-PENDING" in cells[4].upper():
            pending.append(rid)
    return pending


# --------------------------------------------------------------------------
# the audit checks
# --------------------------------------------------------------------------
def _check(checks: List[Dict], name: str, ok: bool, detail: str) -> None:
    checks.append({"name": name, "verdict": "PASS" if ok else "FAIL",
                   "detail": detail, "checked_at_logical": ""})


def audit_readiness(text: str) -> Dict:
    checks: List[Dict] = []

    # -- structural anchors ------------------------------------------------
    missing_marks = [m for m in STRUCTURE_MARKS if m not in text]
    _check(checks, "A1_structure_marks", not missing_marks,
           "matrix, signature block, exit criteria, blocking rule, and "
           "signature header all present" if not missing_marks
           else f"required anchors missing: {missing_marks}")

    # -- slot census --------------------------------------------------------
    matrix = _matrix_rows(text)
    sig = _signature_rows(text)
    matrix_ids = sorted(matrix)
    sig_ids = sorted(sig)
    census_ok = (matrix_ids == sorted(EXPECTED_ROWS)
                 and sig_ids == sorted(EXPECTED_ROWS))
    _check(checks, "A2_slot_census", census_ok,
           "12 slots SC-1..SC-12 present in BOTH the §2 matrix and the "
           "§3 signature block, no gaps, no duplicates"
           if census_ok
           else f"slot census mismatch — matrix {matrix_ids} / "
                f"signature {sig_ids}")

    # -- matrix completeness -------------------------------------------------
    incomplete = [rid for rid, cells in matrix.items()
                  if len(cells) < MANDATORY_MATRIX_CELLS
                  or any(not c for c in cells[1:5])]
    _check(checks, "A3_matrix_completeness", not incomplete,
           "every §2 row carries item, source, grant form, binding, and "
           "expiry" if not incomplete
           else f"§2 rows with missing cells: {incomplete}")

    # -- signature cell shape -------------------------------------------------
    malformed = [rid for rid, cells in sig.items() if len(cells) != 5]
    half_signed = [rid for rid, cells in sig.items()
                   if len(cells) == 5 and any(cells[1:4])]
    _check(checks, "A4_signature_rows_wellformed",
           not malformed and not half_signed,
           "all 12 §3 rows are 5-cell and EMPTY — nothing pre-signed, "
           "ready to receive signatures" if not malformed
           and not half_signed
           else f"malformed rows: {malformed}; half-filled rows "
                f"(name/date/evidence present before sign-off): "
                f"{half_signed}")

    # -- pre-fill coherence ----------------------------------------------------
    prefilled = _prefilled_in_matrix(text)
    pending = _pending_in_signature(text)
    coherent = (sorted(prefilled) == sorted(EXPECTED_PREFILLED)
                and sorted(pending) == sorted(EXPECTED_PREFILLED))
    _check(checks, "A5_prefill_coherence", coherent,
           f"the 5 pre-filled decision slots {sorted(EXPECTED_PREFILLED)} "
           "carry matching RATIFICATION-PENDING notes in §3 (a pre-fill "
           "is not a grant)" if coherent
           else f"pre-fill set {prefilled} vs pending-note set {pending} "
                f"— expected exactly {sorted(EXPECTED_PREFILLED)}")

    # -- the REAL verifier's standing verdict -----------------------------------
    import verify_stage_c_grants as vsg
    res = vsg.verify_grants(text)
    required_verdict = ("AUTHORIZED" if all(
        sig.get(r, [""] * 5)[1:4] != ["", "", ""]
        for r in EXPECTED_ROWS) else "NOT_AUTHORIZED")
    verdict_ok = res.get("verdict") == required_verdict
    checks.append({
        "name": "A6_fail_closed_verdict",
        "verdict": "PASS" if verdict_ok else "FAIL",
        "detail": f"verifier verdict {res.get('verdict')} "
                  f"({res.get('signed_count', 0)}/12 signed) — the "
                  f"required standing answer for this artifact state is "
                  f"{required_verdict} (fail closed)"
                  if verdict_ok
                  else f"verifier verdict {res.get('verdict')} does NOT "
                       f"match the required standing answer "
                       f"{required_verdict} for this artifact state",
        "checked_at_logical": ""})

    bad = [c for c in checks if c["verdict"] != "PASS"]
    return {"schema_version": SCHEMA,
            "compatible_with": "qa.launch_attestation.v1",
            "ok": not bad,
            "verdict": "READY" if not bad else "NOT_READY",
            "artifact": "docs/deployment/stage-c-owner-grants.md",
            "machine_verifier": {
                "ok": res.get("ok", False),
                "verdict": res.get("verdict"),
                "signed_count": res.get("signed_count", 0),
                "findings": res.get("findings", [])},
            "checks": checks,
            "failing": [c["name"] for c in bad]}


# --------------------------------------------------------------------------
# offline positive-side proof (zero mutation)
# --------------------------------------------------------------------------
def simulate_sign(text: str) -> Dict:
    """Verifier verdict over a SYNTHETIC fully-signed copy. Proves the
    checklist becomes AUTHORIZED exactly when every row carries name,
    date, and evidence — without touching the real artifact."""
    import verify_stage_c_grants as vsg
    out = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("| SC-"):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if len(cells) == 5 and not any(cells[1:4]):
                cells[1], cells[2], cells[3] = ("Owner Name",
                                                "2026-09-30",
                                                f"evidence-{cells[0]}")
                line = "| " + " | ".join(cells) + " |"
        out.append(line)
    res = vsg.verify_grants("\n".join(out) + "\n")
    return {"schema_version": "stage_c.simulated_signoff.v1",
            "simulated": True,
            "artifact_mutated": False,
            "verifier_ok": res.get("ok", False),
            "verifier_verdict": res.get("verdict"),
            "signed_count": res.get("signed_count", 0)}


def render(report: Dict) -> str:
    lines = ["=== STAGE C OWNER-GRANTS READINESS AUDIT ==="]
    for c in report["checks"]:
        mark = "ok  " if c["verdict"] == "PASS" else "FAIL"
        lines.append(f"  [{mark}] {c['name']:<30} {c['detail']}")
    mv = report["machine_verifier"]
    lines.append(f"  [info] machine_verifier              "
                 f"{mv['verdict']} ({mv['signed_count']}/12 signed)")
    for f in mv["findings"][:3]:
        lines.append(f"         {f.get('id')}: {f.get('reason', '')[:80]}")
    lines.append(f"verdict {report['verdict']} — "
                 f"{len(report['checks']) - len(report['failing'])}/"
                 f"{len(report['checks'])} green")
    if report["ok"]:
        lines.append(
            "All 12 slots structurally ready for sign-off; the "
            "fail-closed gate holds (execution halts until every row "
            "is signed).")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Stage C owner-grants readiness audit "
                    "(fail closed, mutates nothing).")
    ap.add_argument("--artifact", default=str(DEFAULT_ARTIFACT))
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--simulate-sign", action="store_true",
                    help="prove the AUTHORIZED side offline over a "
                         "synthetic fully-signed copy (zero mutation)")
    args = ap.parse_args(argv)

    try:
        text = read_artifact(Path(args.artifact))
    except GrantsAuditError as e:
        if args.json:
            print(json.dumps({"ok": False, "verdict": "UNREADABLE",
                              "error": str(e)}))
        else:
            print(f"[FAIL] {e}")
        return 2

    report = audit_readiness(text)

    simulated = None
    if args.simulate_sign:
        simulated = simulate_sign(text)
        if not simulated["verifier_ok"]:
            report["checks"].append({
                "name": "A7_simulated_signoff_authorized",
                "verdict": "FAIL",
                "detail": "a fully-signed synthetic copy did NOT reach "
                          "AUTHORIZED — signature-block shape blocks "
                          "sign-off",
                "checked_at_logical": ""})
            report["ok"] = False
            report["verdict"] = "NOT_READY"
            report["failing"].append("A7_simulated_signoff_authorized")

    if args.json:
        print(json.dumps(dict(report, simulated_signoff=simulated),
                         ensure_ascii=False, indent=2))
    else:
        print(render(report))
        if simulated is not None:
            print(f"simulated full sign-off (offline, zero mutation): "
                  f"{simulated['verifier_verdict']} "
                  f"({simulated['signed_count']}/12)")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

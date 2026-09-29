"""Stage C owner-grant checklist verification (operator command).

Parses `docs/deployment/stage-c-owner-grants.md` and asserts that the
SC-1..SC-12 grant matrix is COMPLETELY signed before Stage C execution
may begin. Fail closed, mirroring the `--stage-f` precedent (D-146):

  - every row must carry a non-empty Granted-by name, a date, and an
    evidence reference in the SIGNATURE BLOCK (§3);
  - `RATIFICATION-PENDING` rows are explicit non-grants (a pre-filled
    decision value is not an authorization);
  - structural defects (missing sections, missing rows, ragged tables)
    are failures, never passes.

Exit contract (0/1/2, fail closed):

  0  all twelve rows validly signed — Stage C authorized to begin
  1  gate NOT satisfied — at least one row unsigned/pending, or a
     structural defect in the artifact
  2  artifact missing / unreadable

Usage:
  python3 local/scripts/verify_stage_c_grants.py [--artifact PATH] [--json]

No network, no subprocess, no durable state: AST-pure parse + verdict.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_ARTIFACT = REPO_ROOT / "docs" / "deployment" / "stage-c-owner-grants.md"

EXPECTED_ROWS = [f"SC-{i}" for i in range(1, 13)]
SIGNATURE_HEADERS = ("Granted by (name)", "Date", "Evidence reference")

_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def parse_signature_block(text: str) -> Tuple[Optional[List[str]], Optional[str]]:
    """Return (row_ids in order, error) for the §3 signature block.

    error is None when the block is structurally sound; row_ids is the
    ordered list of row ids found there (None on structural failure).
    """
    lines = text.splitlines()
    block: List[str] = []
    in_block = False
    for line in lines:
        if line.strip() == "## 3. Signature block":
            in_block = True
            continue
        if in_block and line.startswith("## "):
            break
        if in_block:
            block.append(line)
    if not in_block:
        return None, "signature block section (## 3. Signature block) not found"

    header_idx = next(
        (i for i, l in enumerate(block) if all(h in l for h in SIGNATURE_HEADERS)),
        None)
    if header_idx is None:
        return None, "signature header row (name/date/evidence) not found"
    if header_idx + 1 >= len(block):
        return None, "signature table separator row missing"
    if not re.match(r"^\|[\s\-|:]+\|$", block[header_idx + 1].strip()):
        return None, "signature table separator row malformed"

    row_ids: List[str] = []
    for line in block[header_idx + 2:]:
        stripped = line.strip()
        if not stripped.startswith("|"):
            break
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if not cells or not cells[0]:
            return row_ids or None, "signature row without an id cell"
        row_ids.append(cells[0])
    if not row_ids:
        return None, "no signature rows found under the header"
    return row_ids, None


def row_status(cells: List[str]) -> Tuple[str, str]:
    """(status, reason) for one signature row's cells.

    status is one of SIGNED, UNSIGNED, PENDING, MALFORMED.
    The signature block is cells[1]=name, cells[2]=date,
    cells[3]=evidence reference; cells[4] is notes.

    The signature block is authoritative: a complete name/date/evidence
    triple dominates a stale RATIFICATION-PENDING note. The note only
    classifies a row whose signature cells are still incomplete (a
    pre-filled decision row is a more specific kind of unsigned).
    """
    if len(cells) < 5:
        return "MALFORMED", f"expected 5 cells, found {len(cells)}"
    _id, name, date, evidence, notes = cells[0], cells[1], cells[2], cells[3], cells[4]
    missing = [label for label, val in
               (("name", name), ("date", date), ("evidence", evidence)) if not val]
    if missing:
        if "RATIFICATION-PENDING" in notes.upper():
            return ("PENDING",
                    "pre-filled decision row — not yet ratified by signature "
                    "(missing " + ", ".join(missing) + ")")
        return "UNSIGNED", "missing " + ", ".join(missing)
    if not _DATE_RE.search(date):
        return "UNSIGNED", f"date is not ISO YYYY-MM-DD: {date!r}"
    return "SIGNED", "name, date, and evidence reference present"


def verify_grants(text: str) -> Dict:
    """Pure verdict over the artifact text — no I/O, battery-testable."""
    findings: List[Dict[str, str]] = []

    row_ids, struct_err = parse_signature_block(text)
    if row_ids is None:
        return {"schema_version": "stage_c.grant_verification.v1",
                "ok": False, "verdict": "STRUCTURAL_DEFECT",
                "rows": {}, "findings": [
                    {"id": "-", "status": "MALFORMED", "reason": struct_err or ""}]}

    for expected, actual in zip(EXPECTED_ROWS, row_ids):
        if actual != expected:
            findings.append({"id": expected, "status": "MALFORMED",
                             "reason": f"expected row {expected}, found {actual!r}"})
    if len(row_ids) != len(EXPECTED_ROWS):
        findings.append({"id": "-", "status": "MALFORMED",
                         "reason": f"expected {len(EXPECTED_ROWS)} signature rows, "
                                   f"found {len(row_ids)}"})

    rows: Dict[str, Dict[str, str]] = {}
    lines = text.splitlines()
    block: List[str] = []
    in_block = False
    for line in lines:
        if line.strip() == "## 3. Signature block":
            in_block = True
            continue
        if in_block and line.startswith("## "):
            break
        if in_block:
            block.append(line)
    for line in block:
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        rid = cells[0] if cells else ""
        if rid in EXPECTED_ROWS and rid not in rows and len(cells) >= 5:
            status, reason = row_status(cells)
            rows[rid] = {"status": status, "reason": reason}
            if status != "SIGNED":
                findings.append({"id": rid, "status": status, "reason": reason})

    for expected in EXPECTED_ROWS:
        if expected not in rows:
            findings.append({"id": expected, "status": "UNSIGNED",
                             "reason": "row absent from the signature block"})

    ok = (bool(rows)
          and all(rows.get(r, {}).get("status") == "SIGNED"
                  for r in EXPECTED_ROWS)
          and len(row_ids) == len(EXPECTED_ROWS)
          and not findings)
    return {"schema_version": "stage_c.grant_verification.v1",
            "ok": ok,
            "verdict": "AUTHORIZED" if ok else "NOT_AUTHORIZED",
            "signed_count": sum(1 for r in EXPECTED_ROWS
                                if rows.get(r, {}).get("status") == "SIGNED"),
            "rows": rows,
            "findings": findings}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify the Stage C owner grant checklist (fail closed).")
    parser.add_argument("--artifact", default=str(DEFAULT_ARTIFACT),
                        help="path to stage-c-owner-grants.md")
    parser.add_argument("--json", action="store_true",
                        help="emit the machine-readable verdict only")
    args = parser.parse_args(argv)

    path = Path(args.artifact)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        if args.json:
            print(json.dumps({"ok": False, "verdict": "UNREADABLE",
                              "error": str(e)}))
        else:
            print(f"[FAIL] grant artifact unreadable: {path} ({e})")
        return 2

    result = verify_grants(text)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print("=== STAGE C OWNER GRANTS VERIFICATION ===")
        for rid in EXPECTED_ROWS:
            row = result["rows"].get(rid)
            if row is None:
                print(f"  [FAIL] {rid} — absent from the signature block")
            else:
                mark = "ok  " if row["status"] == "SIGNED" else "FAIL"
                print(f"  [{mark}] {rid} — {row['status']}: {row['reason']}")
        print(f"signed {result.get('signed_count', 0)}/12 — "
              f"verdict {result['verdict']}")
        if result["ok"]:
            print("Stage C authorization COMPLETE — the provisioning ladder "
                  "may begin under its own gates.")
        else:
            print("NOT READY — the grant gate fails closed until every row "
                  "is signed (name, date, evidence reference).")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

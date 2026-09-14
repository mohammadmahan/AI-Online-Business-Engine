#!/usr/bin/env python3
"""Generate the owner review pack for the verification queue (Phase 4).

Reads the live HITL queue (local/volumes/verification/queue.json, via
the VerificationQueue API — never raw-file guesses) and writes a
self-contained Markdown pack to docs/reports/ for human review:

  - pending items in true queue order, each labeled with its REAL
    queue index (the number `verification_tool.py review --index N`
    consumes — never a renumbered "pending #k"),
  - grouped by error code with decision guidance per code, grounded
    in the approved decisions (D-019/D-020/D-024/D-025/D-028/D-057),
  - a decision placeholder per item (the OWNER decides; tooling never
    auto-resolves — D-050).

Usage:  python3 local/scripts/make_review_pack.py
Exit:   0 always (a report is a report); the pack itself states queue
        health so CI/callers can grep it.
"""

import json
import os
import sys
from collections import OrderedDict
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL = os.path.dirname(HERE)
ROOT = os.path.dirname(LOCAL)
for p in (LOCAL, os.path.join(LOCAL, "canonical")):
    if p not in sys.path:
        sys.path.insert(0, p)

from verification_tool import VerificationQueue          # noqa: E402

OUT_PATH = os.path.join(ROOT, "docs", "reports",
                        "verification-queue-review-pack.md")

# Per-code review guidance, grounded in approved decisions. Keys are
# the D-033 deterministic error codes; anything unknown still renders
# (generic guidance) so the pack never silently omits an item.
CODE_GUIDANCE = {
    "INVALID_PRICE": (
        "A price violates D-024/D-025 (sale >= applicable base, "
        "zero/negative, formatted string, or sale without a base). "
        "Approving nothing here fixes data; instead correct the SOURCE "
        "(workbook) and re-import — the corrected run is a new D-027 "
        "event. Rejecting the row keeps canonical clean."),
    "ORPHAN_VARIANT": (
        "The variant's Product ID has no محصولات row in the same "
        "workbook (D-028 §12: never silently merged). Decide whether "
        "the product row is missing from this workbook (reject here, "
        "fix workbook) or the Product ID is mistyped (reject, correct "
        "the identifier — IDs are never auto-corrected)."),
    "DUPLICATE_PRODUCT_ID": (
        "The same Product ID appears more than once (D-028 §12). "
        "Identifiers are immutable and never auto-merged; one row is "
        "right, the rest are corrected in the source workbook."),
    "INVALID_PRODUCT_ID": (
        "Not P+5 digits (D-014 rule 1). Identifiers are "
        "human/approved-tooling issued only (D-014) — AI never assigns "
        "one. Reject and supply the correct ID in the workbook."),
    "UNKNOWN_VOCABULARY": (
        "Value is not among the owner-approved terms (D-019: no "
        "auto-vocabulary creation, no aliases). Reject here; either "
        "correct the value to an approved term or bring a new term as "
        "an owner decision (D-031 governance)."),
    "UNKNOWN_SIZE_FAMILY": (
        "خانواده سایز is not one of حروفی/عددی/کمر (D-031). Reject; "
        "fix the family label — never invent a family."),
    "SIZE_FAMILY_MISMATCH": (
        "The size exists but not in the selected family (D-020: "
        "family-scoped; numeric 42 ≠ pants-waist 42; no conversion). "
        "Reject; correct family OR size in the workbook."),
    "SKU_MISMATCH": (
        "SKU does not match Product ID + active-axis codes (D-014 "
        "rule 6; D-032 codes incl. D-057 LRG). SKUs are derived by "
        "approved tooling — reject and let tooling derive, or fix the "
        "axis values."),
    "DUPLICATE_SKU": (
        "SKU already exists (D-028 §12). SKU is unique business data "
        "(never an identity key, D-046). Reject; resolve the "
        "duplicate at the source."),
    "DUPLICATE_VARIANT_COMBINATION": (
        "Same Product ID + active Color + active Size appears twice "
        "(D-014 rule 11: never merged). Reject; one variant is real, "
        "the duplicate is a workbook error."),
    "CONFLICTING_UPDATE": (
        "Same identifier with changed canonical values (D-017: "
        "canonical preserved, human decides). Approving a change is "
        "a deliberate canonical-data decision; rejecting keeps the "
        "stored values."),
}
GENERIC_GUIDANCE = (
    "Deterministic validation surfaced this item (D-028). Reject "
    "unless the source data is confirmed correct; corrections happen "
    "in the source workbook and re-import as a new event — canonical "
    "values are never silently overwritten.")


def main() -> int:
    q = VerificationQueue()
    items = q.load_pending()
    pending = [(i, it) for i, it in enumerate(items)
               if not it.get("review_status")]
    decided = len(items) - len(pending)

    # Group pending by code, preserving true queue indices.
    groups = OrderedDict()
    for idx, it in pending:
        groups.setdefault(it.get("code", "(no code)"), []).append((idx, it))

    L = []
    L.append("# Verification Queue — Owner Review Pack")
    L.append("")
    L.append(f"Generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    L.append("")
    L.append(f"- Queue total: **{len(items)}** items "
             f"({decided} decided, **{len(pending)} pending your decision**)")
    L.append(f"- Data source: `{os.path.relpath(q.queue_path, ROOT)}` "
             "(runtime state, gitignored)")
    L.append("- Decision tool: "
             "`python3 local/canonical/verification_tool.py review "
             "--index N --approve|--reject --reviewer <your-name>`")
    L.append("")
    L.append("> **How to use this pack:** each item shows its TRUE queue "
             "index — pass exactly that number to `--index`. Decisions "
             "are immutable (D-026 append-only): they are recorded in "
             "place with your reviewer identity and D-026 provenance. "
             "The guidance below restates the approved decisions; when "
             "in doubt, **reject** — corrections flow through the "
             "source workbook and re-import, never through silent "
             "canonical rewrites.")
    L.append("")

    if not pending:
        L.append("## No pending items 🎉")
        L.append("")
        L.append("Every queued item carries a recorded human decision.")
    for code, group in groups.items():
        g = CODE_GUIDANCE.get(code, GENERIC_GUIDANCE)
        L.append(f"## {code} — {len(group)} item(s)")
        L.append("")
        L.append(f"**Guidance ({code}):** {g}")
        L.append("")
        for idx, it in group:
            L.append(f"### Item — queue index `{idx}`")
            L.append("")
            L.append(f"- Sheet/row: {it.get('sheet', '?')} / "
                     f"row {it.get('row', '?')}")
            msg = it.get("message", "")
            L.append(f"- Message: {msg}")
            L.append(f"- Queued at: {it.get('queued_at', '?')}")
            L.append("")
            L.append("```json")
            L.append(json.dumps(
                {k: v for k, v in it.items()
                 if k not in ("item_key", "queued_at", "review_status")},
                ensure_ascii=False, indent=2))
            L.append("```")
            L.append("")
            L.append("**Decision (owner):** ☐ approve ☐ reject — "
                     "rationale: ____________")
            L.append("")

    L.append("---")
    L.append("")
    L.append("*Generated by `local/scripts/make_review_pack.py`; "
             "regenerate after each decision round. Tooling never "
             "decides (D-050).*")

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print(f"Wrote review pack: {os.path.relpath(OUT_PATH, ROOT)} "
          f"({len(pending)} pending of {len(items)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

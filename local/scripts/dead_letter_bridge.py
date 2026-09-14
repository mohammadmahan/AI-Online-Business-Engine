#!/usr/bin/env python3
"""Dead-letter bridge — n8n error-router output → HITL verification queue.

Closes the D-052 §3 terminal route end-to-end (Phase 5 M4):

    failing workflow
      → error router (GREEN-OPS-ERROR-GLOBAL_FAILURE_ROUTER)
      → terminal D-052 class (B/C/D/E)
      → tagged <<<DEADLETTER>>> line on the n8n container stdout
        (the D-053 local log sink — no new service, no host mounts)
      → THIS bridge (canonical layer) reads the container logs
      → materializes each dead-letter as a HITL verification-queue item
        with D-026 provenance (source_type EXTERNAL_SYNC, actor =
        the n8n workflow identity)
      → a HUMAN decides (D-028/D-050); the bridge never decides.

Guarantees:
  - No silent drop: every parseable dead-letter line lands in the queue.
  - Idempotent ingestion: identical pending dead-letters deduplicate via
    the deterministic item key (idempotency_key or workflow+execution);
    re-running the bridge over old logs cannot flood the queue.
  - D-050 boundary: this tool enqueues only; review decisions are made
    exclusively by a human through verification_tool.
  - Redaction carried through: the reason field is already D-045-redacted
    by the taxonomy redactor and is stored verbatim, never re-expanded.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL = os.path.dirname(HERE)
ROOT = os.path.dirname(LOCAL)
for p in (LOCAL, os.path.join(LOCAL, "canonical"),
          os.path.join(LOCAL, "services")):
    if p not in sys.path:
        sys.path.insert(0, p)

import verification_tool as vt                      # noqa: E402
from sync_engine import ProvenanceEngine            # noqa: E402

DEADLETTER_RE = re.compile(r"<<<DEADLETTER>>>(\{.*)")

VALID_FAILURE_CLASSES = ("B", "C", "D", "E")   # terminal classes; A retries


def parse_deadletters(log_text: str) -> list:
    """Extract dead-letter payloads from container log text.

    Malformed JSON on a tagged line is skipped and surfaced in the run
    report as `malformed` — never silently discarded (D-028 boundary).
    """
    parsed, malformed = [], 0
    for line in (log_text or "").splitlines():
        m = DEADLETTER_RE.search(line)
        if not m:
            continue
        try:
            rec = json.loads(m.group(1))
        except json.JSONDecodeError:
            malformed += 1
            continue
        if isinstance(rec, dict):
            parsed.append(rec)
    return parsed, malformed


def dead_letter_to_review_item(rec: dict) -> dict:
    """Map a dead-letter payload onto the queue's review-item schema.

    `sheet`/`row` are the queue's generic origin columns — for workflow
    failures they carry the n8n origin (workflow name / execution id).
    The deterministic `item_key` makes ingestion idempotent: prefer the
    D-027 idempotency key when present, else workflow + execution id.
    """
    cls = rec.get("failure_class") if rec.get("failure_class") in \
        VALID_FAILURE_CLASSES else "E"
    origin_wf = str(rec.get("origin_workflow_name") or "unknown")
    origin_exec = str(rec.get("origin_execution_id") or "unknown")
    idem = str(rec.get("idempotency_key") or "").strip()
    key = ("n8n|" + idem) if idem else f"n8n|{origin_wf}|{origin_exec}"
    return {
        "sheet": "n8n-dead-letter",
        "row": origin_exec,
        "code": f"WORKFLOW_FAILURE_CLASS_{cls}",
        "message": str(rec.get("sanitized_reason")
                       or rec.get("failure_name")
                       or "unspecified workflow failure")[:300],
        "origin_workflow_id": str(rec.get("origin_workflow_id") or "unknown"),
        "origin_workflow_name": origin_wf,
        "failure_class": cls,
        "failure_name": str(rec.get("failure_name") or ""),
        "route": str(rec.get("route") or "dead_letter_hitl"),
        "timestamp_utc": str(rec.get("timestamp_utc") or ""),
        "item_key": key,
    }


def read_container_logs(container: str, since: str = None) -> str:
    cmd = ["docker", "logs"]
    if since:
        cmd += ["--since", since]
    cmd.append(container)
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    return res.stdout + res.stderr


def materialize(records: list, queue: "vt.VerificationQueue",
                actor: str = "n8n-error-router") -> dict:
    enqueued = deduped = 0
    for rec in records:
        res = queue.enqueue(dead_letter_to_review_item(rec),
                            source_type="EXTERNAL_SYNC", actor=actor)
        if res.get("dedup"):
            deduped += 1
        else:
            enqueued += 1
    return {"enqueued": enqueued, "deduplicated": deduped,
            "pending": len(queue.pending_items()),
            "total": len(queue.load_pending())}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Materialize n8n error-router dead-letters into the "
                    "HITL verification queue (D-052 §3 / D-026). "
                    "Enqueue-only: decisions stay human (D-050).")
    ap.add_argument("--container", default="engine-local-n8n")
    ap.add_argument("--since", default=None,
                    help="docker logs --since value (e.g. 24h); "
                    "default: entire retained log")
    ap.add_argument("--queue", default=vt.DEFAULT_QUEUE_PATH)
    ap.add_argument("--no-provenance", action="store_true",
                    help="skip the D-026 engine (NOT recommended; items "
                    "then exist only in queue history)")
    ap.add_argument("--dry-run", action="store_true",
                    help="parse and report only; enqueue nothing")
    args = ap.parse_args(argv)

    log_text = read_container_logs(args.container, args.since)
    records, malformed = parse_deadletters(log_text)
    report = {"container": args.container,
              "deadletters_found": len(records),
              "malformed_lines": malformed}

    if args.dry_run:
        report["items"] = [dead_letter_to_review_item(r) for r in records]
        print(json.dumps(report, ensure_ascii=False, indent=1))
        return 0

    provenance = None
    if not args.no_provenance:
        provenance = ProvenanceEngine(path=os.path.join(
            os.path.dirname(args.queue), "prov.json"))
    queue = vt.VerificationQueue(queue_path=args.queue,
                                 provenance=provenance)
    report.update(materialize(records, queue))
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())

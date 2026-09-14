"""Verification Queue — human-in-the-loop review tooling (Phase 4).

Implements the review side of the D-028 data-entry boundary:

  - Invalid/conflicting rows surfaced by the import runner are queued
    here (deterministic, deduplicated) instead of being lost.
  - A human reviews each item; the decision is recorded IN PLACE and
    is append-only: items are never popped, review decisions are
    immutable, and every enqueue/decision carries D-026 provenance.
  - The queue is runtime state (gitignored local/volumes/ by default)
    — the Git-tracked artifact is the code and its tests, never the
    review data.

AI authority (PROJECT_RULES / D-050): the queue can be enqueued and
read by tooling, but `review_item` is a HUMAN decision — callers must
pass the actual reviewer identity; tooling never approves on the
human's behalf and never auto-resolves business exceptions.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL = os.path.dirname(HERE)
ROOT = os.path.dirname(LOCAL)
for p in (LOCAL, os.path.join(LOCAL, "canonical"),
          os.path.join(LOCAL, "services")):
    if p not in sys.path:
        sys.path.insert(0, p)

DEFAULT_QUEUE_PATH = os.path.join(
    LOCAL, "volumes", "verification", "queue.json")

# D-026 review-state vocabulary for queue decisions (advances only).
VERIFIED = "HUMAN_VERIFIED"
REJECTED = "HUMAN_REJECTED"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _item_key(item: dict):
    """Deterministic identity of a review item (dedupe key)."""
    for k in ("item_key",):
        if item.get(k):
            return item[k]
    return "|".join(str(item.get(k)) for k in
                    ("sheet", "row", "code", "message") if item.get(k))


class VerificationQueue:
    """Append-only HITL queue (D-026/D-028)."""

    def __init__(self, queue_path: str = None,
                 provenance=None):
        self.queue_path = queue_path or DEFAULT_QUEUE_PATH
        self.prov = provenance          # D-026 engine (audit reads)
        self.provenance = provenance
        os.makedirs(os.path.dirname(self.queue_path), exist_ok=True)
        if not os.path.exists(self.queue_path):
            self._write({"items": [], "history": []})

    # -- persistence -----------------------------------------------------

    def _read(self) -> dict:
        with open(self.queue_path, encoding="utf-8") as f:
            return json.load(f)

    def _write(self, data: dict) -> None:
        tmp = self.queue_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.queue_path)

    # -- sketch-compatible API -------------------------------------------

    def load_pending(self) -> list:
        """All queued items in order (reviewed ones included, stamped)."""
        return self._read()["items"]

    def save_pending(self, items: list) -> None:
        """Low-level replace (kept for compatibility; prefer the
        append-only helpers below — direct rewrites bypass provenance)."""
        data = self._read()
        data["items"] = items
        self._write(data)

    def pending_items(self) -> list:
        """Only items awaiting a human decision."""
        return [i for i in self.load_pending()
                if not i.get("review_status")]

    # -- queueing (append + dedupe) ---------------------------------------

    def enqueue(self, item: dict, source_type: str = "IMPORTED",
                actor: str = "import-runner") -> dict:
        """Append a review item (idempotent by deterministic key).

        First-class fields are preserved as given; queueing metadata
        (queued_at, key, review state) is stamped here. Re-enqueueing
        an identical pending item is a no-op returning the existing
        entry; an identical already-REJECTED item may be re-queued
        (the correction itself is a new human decision).
        """
        key = _item_key(item)
        if not key or set(key) == {"None"}:
            raise ValueError("review item has no deterministic identity")
        data = self._read()
        for existing in data["items"]:
            if existing.get("item_key") == key \
                    and not existing.get("review_status"):
                return dict(existing, dedup=True)
        entry = dict(item)
        entry["item_key"] = key
        entry["queued_at"] = _now()
        entry["review_status"] = None
        data["items"].append(entry)
        data["history"].append({"event": "enqueued", "item_key": key,
                                "at": entry["queued_at"],
                                "actor": actor})
        self._write(data)
        if self.provenance is not None:
            pr = self.provenance.record(
                source_type, actor,
                notes=f"verification queue: {key[:120]}")
            self.provenance.link_value("verification_queue", key,
                                       "item", pr)
        return entry

    def enqueue_report(self, review_items: list,
                       source_type: str = "IMPORTED",
                       actor: str = "import-runner") -> dict:
        """Materialize an import-runner review_queue (list of error
        dicts with sheet/row/code/message) into the queue."""
        added = deduped = 0
        for it in review_items:
            res = self.enqueue(it, source_type=source_type, actor=actor)
            added += 0 if res.get("dedup") else 1
            deduped += 1 if res.get("dedup") else 0
        return {"enqueued": added, "deduplicated": deduped,
                "pending": len(self.pending_items())}

    # -- HITL decision (immutable, provenance-stamped) --------------------

    def review_item(self, item_index: int, approved: bool,
                    reviewer: str) -> dict:
        """Record a human decision IN PLACE (never pops, D-026).

        The item stays in the queue with its decision stamped; the
        decision itself is immutable — a changed mind is a new, later
        decision recorded on top (append-only), never a silent flip.
        """
        data = self._read()
        items = data["items"]
        if not 0 <= item_index < len(items):
            raise IndexError(f"queue index out of range: {item_index} "
                             f"(queue holds {len(items)} items)")
        item = items[item_index]
        if item.get("review_status"):
            raise ValueError(
                f"item {item['item_key'][:80]} already decided "
                f"({item['review_status']}); decisions are immutable "
                "(D-026 append-only)")
        item["review_status"] = VERIFIED if approved else REJECTED
        item["reviewed_by"] = reviewer
        item["reviewed_at"] = _now()
        data["history"].append({
            "event": "reviewed", "item_key": item["item_key"],
            "decision": item["review_status"], "reviewer": reviewer,
            "at": item["reviewed_at"]})
        self._write(data)
        if self.provenance is not None:
            pr = self.provenance.record(
                "HUMAN_ENTERED", reviewer,
                notes=f"queue decision {item['review_status']}: "
                      f"{item['item_key'][:100]}")
            self.provenance.link_value("verification_queue",
                                       item["item_key"], "decision", pr)
        return dict(item)

    def history(self) -> list:
        """Full append-only audit trail (enqueue + decision events)."""
        return self._read()["history"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Verification queue — HITL review CLI (D-028)")
    ap.add_argument("verb", choices=["report", "review"])
    ap.add_argument("--queue", default=DEFAULT_QUEUE_PATH)
    ap.add_argument("--index", type=int, default=None)
    ap.add_argument("--approve", dest="approved", action="store_true")
    ap.add_argument("--reject", dest="approved", action="store_false")
    ap.set_defaults(approved=None)
    ap.add_argument("--reviewer", default=None,
                    help="identity of the deciding human (required)")
    args = ap.parse_args(argv)

    q = VerificationQueue(queue_path=args.queue)
    if args.verb == "report":
        pending = q.pending_items()
        print(json.dumps({"pending": len(pending),
                          "total": len(q.load_pending()),
                          "items": pending},
                         ensure_ascii=False, indent=1))
        return 0
    if args.reviewer is None:
        ap.error("--reviewer is required: decisions are attributed "
                 "to a human (D-026)")
    if args.approved is None:
        ap.error("pass --approve or --reject")
    item = q.review_item(args.index, args.approved, args.reviewer)
    print(json.dumps(item, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())

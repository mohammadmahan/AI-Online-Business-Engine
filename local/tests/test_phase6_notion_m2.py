"""Phase 6 M2 — mock-driven data-contract tests (Notion Business OS).

Exercises local/canonical/notion_contracts.py, the D-060 (Approved,
amended 2026-09-15) contracts, before any real Notion connection:

  1. D-027/D-060 idempotency keys — pinned serialization vectors,
     retry dedupe (same delivery ⇒ same key), and the headline
     regression fix: repeated transitions (Draft → Review → Draft →
     Review) yield DISTINCT keys per revision instead of being
     silently dropped as duplicates.
  2. The full 9-state lifecycle machine — every approved transition
     exercised, terminal states final, invalid jumps rejected as
     Class B, unknown states as Class E.
  3. Mock payload contract validation against JSON fixtures
     (Content Idea / Campaign / Incident) with the revision marker
     abstracted behind RevisionMarkerResolver (real source field
     owner-gated per D-060 — the tests never hard-code a guess).

No network, no credentials (D-045/D-053).
"""

import json
import os
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOCAL = HERE.parent
ROOT = LOCAL.parent
for p in (str(LOCAL), str(LOCAL / "canonical")):
    if p not in sys.path:
        sys.path.insert(0, p)

from canonical.notion_contracts import (  # noqa: E402
    ARCHIVED, APPROVED, BACKLOG, CLASS_B, CLASS_E, DRAFT, PUBLISHED,
    REJECTED, RESEARCHING, REVIEW, SCHEDULED,
    LifecycleViolation, PayloadContractError, RevisionMarkerResolver,
    notion_idempotency_key, validate_mock_payload, validate_transition,
)

FIXTURES = HERE / "fixtures" / "notion"
SPEC = ROOT / "docs" / "phases" / "phase-06-notion-business-os.md"

PAGE = "8f5a34e0-7d32-4e9a-9e1b-3f0a7114b100"


def _load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 1) Idempotency keys — D-060 refined formula
# ---------------------------------------------------------------------------

class TestIdempotencyKeys(unittest.TestCase):
    def test_pinned_serialization_vector(self):
        # Frozen serialization: '|'-joined UTF-8 source|page|type|marker.
        # Regenerating this vector requires a decision-record amendment.
        self.assertEqual(
            notion_idempotency_key(PAGE, "status_changed", "rev-0001"),
            "4329dedf057fe980d1e3fb09228e00047f3807d13031a1439599e4c1344db50b",
        )

    def test_identical_retry_yields_identical_key(self):
        a = notion_idempotency_key(PAGE, "status_changed", "rev-0001")
        b = notion_idempotency_key(PAGE, "status_changed", "rev-0001")
        self.assertEqual(a, b)

    def test_repeated_transitions_yield_distinct_keys(self):
        """The D-060 headline fix: Draft→Review→Draft→Review produces
        distinct keys per revision — the second Review event must NOT
        be silently dropped as a duplicate of the first."""
        k1 = notion_idempotency_key(PAGE, "status_changed", "rev-0001")
        k2 = notion_idempotency_key(PAGE, "status_changed", "rev-0002")
        k3 = notion_idempotency_key(PAGE, "status_changed", "rev-0003")
        self.assertEqual(len({k1, k2, k3}), 3)

    def test_pinned_second_vector_marker_change(self):
        self.assertEqual(
            notion_idempotency_key(PAGE, "status_changed", "rev-0003"),
            "53bb964971f9c93e0d7d1e2c3ac22b3be99b5937847652df150706f55fba7e82",
        )

    def test_delimiter_is_unambiguous_by_construction(self):
        # '|' in any key-material field raises: ('a|b','c') can never
        # collide with ('a','b|c'). Delimiter-free fields that merely
        # concatenate differently still hash differently.
        with self.assertRaises(ValueError):
            notion_idempotency_key("a|b", "c", "d")
        with self.assertRaises(ValueError):
            notion_idempotency_key("a", "b|c", "d")
        a = notion_idempotency_key("ab", "c", "d")
        b = notion_idempotency_key("a", "bc", "d")
        self.assertNotEqual(a, b)

    def test_different_pages_or_types_differ(self):
        base = notion_idempotency_key(PAGE, "status_changed", "rev-0001")
        self.assertNotEqual(base, notion_idempotency_key("ffffffff-0000-0000-0000-000000000000", "status_changed", "rev-0001"))
        self.assertNotEqual(base, notion_idempotency_key(PAGE, "campaign_updated", "rev-0001"))


# ---------------------------------------------------------------------------
# 2) Lifecycle state machine — D-060 approved extended form
# ---------------------------------------------------------------------------

HAPPY_CHAIN = [BACKLOG, RESEARCHING, DRAFT, REVIEW, APPROVED, SCHEDULED, PUBLISHED]

APPROVED_EXTRA = {
    (BACKLOG, DRAFT), (BACKLOG, REVIEW), (RESEARCHING, REVIEW),
    (DRAFT, BACKLOG), (REVIEW, DRAFT), (REVIEW, BACKLOG),
    (BACKLOG, REJECTED), (RESEARCHING, REJECTED), (DRAFT, REJECTED),
    (REVIEW, REJECTED), (PUBLISHED, ARCHIVED), (REJECTED, ARCHIVED),
}


class TestLifecycleStateMachine(unittest.TestCase):
    def test_main_chain_is_approved(self):
        for cur, nxt in zip(HAPPY_CHAIN, HAPPY_CHAIN[1:]):
            validate_transition(cur, nxt)  # must not raise

    def test_all_approved_extra_transitions(self):
        for cur, nxt in APPROVED_EXTRA:
            validate_transition(cur, nxt)

    def test_terminal_states_have_no_outgoing_edges(self):
        # Archived: truly terminal — no outgoing edges at all.
        for target in HAPPY_CHAIN + [ARCHIVED]:
            with self.assertRaises(LifecycleViolation):
                validate_transition(ARCHIVED, target)
        # Rejected: terminal except the single chaining edge into
        # Archived (D-060: Archived is reachable from Published or
        # Rejected) — everything else must be refused.
        for target in HAPPY_CHAIN:
            with self.assertRaises(LifecycleViolation):
                validate_transition(REJECTED, target)
        validate_transition(REJECTED, ARCHIVED)  # legal

    def test_invalid_jumps_fail_class_b(self):
        for cur, nxt in ((APPROVED, PUBLISHED), (APPROVED, REVIEW),
                         (SCHEDULED, APPROVED), (PUBLISHED, SCHEDULED),
                         (DRAFT, SCHEDULED), (RESEARCHING, APPROVED),
                         (BACKLOG, PUBLISHED), (REVIEW, SCHEDULED)):
            with self.assertRaises(LifecycleViolation) as ctx:
                validate_transition(cur, nxt)
            self.assertEqual(ctx.exception.failure_class, CLASS_B)

    def test_unknown_state_is_class_e(self):
        with self.assertRaises(LifecycleViolation) as ctx:
            validate_transition("On_Hold", REVIEW)
        self.assertEqual(ctx.exception.failure_class, CLASS_E)
        with self.assertRaises(LifecycleViolation) as ctx:
            validate_transition(BACKLOG, "Archived ")
        self.assertEqual(ctx.exception.failure_class, CLASS_E)

    def test_self_transitions_are_not_approved(self):
        for state in HAPPY_CHAIN:
            with self.assertRaises(LifecycleViolation):
                validate_transition(state, state)

    def test_doc_mirror_states_match_module(self):
        doc = SPEC.read_text(encoding="utf-8")
        for state in ("Backlog", "Researching", "Draft", "Review", "Approved",
                      "Scheduled", "Published", "Rejected", "Archived"):
            self.assertIn(state, doc, f"spec doc lost lifecycle state {state}")
        # The register's amended lifecycle line must stay present too.
        register = (ROOT / "DECISIONS.md").read_text(encoding="utf-8")
        self.assertIn("Scheduled → Published", register)


# ---------------------------------------------------------------------------
# 3) Payload contract — fixtures (Content Idea / Campaign / Incident)
# ---------------------------------------------------------------------------

class TestPayloadContractFixtures(unittest.TestCase):
    def test_valid_fixture_resolves_to_pinned_key(self):
        payload = _load("content_idea-valid.json")
        key = validate_mock_payload(payload)
        self.assertEqual(key, notion_idempotency_key(PAGE, "status_changed", "rev-0001"))

    def test_repeated_transition_chain_all_fixtures_validate(self):
        k1 = validate_mock_payload(_load("content_idea-valid.json"))
        k2 = validate_mock_payload(_load("content_idea-loopback.json"))
        k3 = validate_mock_payload(_load("content_idea-re-review.json"))
        self.assertEqual(len({k1, k2, k3}), 3)

    def test_retry_fixture_is_true_duplicate(self):
        k_orig = validate_mock_payload(_load("content_idea-valid.json"))
        k_retry = validate_mock_payload(_load("content_idea-retry-duplicate.json"))
        self.assertEqual(k_orig, k_retry)

    def test_campaign_and_incident_fixtures_validate(self):
        camp = validate_mock_payload(_load("campaign-valid.json"))
        inc = validate_mock_payload(_load("incident-valid.json"))
        self.assertNotEqual(camp, inc)

    def test_incident_marker_is_explicit_mock_field(self):
        # The incident fixture carries an explicit mock revision_marker;
        # its key is pinned over that marker — NOT over wall-clock time.
        payload = _load("incident-valid.json")
        expected = notion_idempotency_key(
            payload["page_id"], payload["event_type"], payload["revision_marker"]
        )
        self.assertEqual(validate_mock_payload(payload), expected)

    def test_wall_clock_is_never_key_material(self):
        """D-060: last_edited_time is change-detection metadata only.
        A payload with NO revision marker on any candidate field can
        never be safely deduplicated and must fail Class B — the
        resolver must NOT fall back to wall-clock time."""
        payload = _load("incident-valid.json")
        only_wall = {k: v for k, v in payload.items() if k != "revision_marker"}
        with self.assertRaises(PayloadContractError) as ctx:
            validate_mock_payload(only_wall)
        self.assertEqual(ctx.exception.failure_class, CLASS_B)

    def test_missing_marker_fails_class_b(self):
        payload = _load("invalid-missing-marker.json")
        with self.assertRaises(PayloadContractError) as ctx:
            validate_mock_payload(payload)
        self.assertEqual(ctx.exception.failure_class, CLASS_B)

    def test_invalid_transition_fixture_fails_class_b(self):
        payload = _load("invalid-transition.json")
        with self.assertRaises(LifecycleViolation) as ctx:
            validate_mock_payload(payload)
        self.assertEqual(ctx.exception.failure_class, CLASS_B)


class TestResolverInterface(unittest.TestCase):
    def test_explicit_override_wins(self):
        r = RevisionMarkerResolver()
        self.assertEqual(r.resolve({"revision_marker": "rev-9"}, explicit_marker="override"), "override")

    def test_blank_explicit_marker_rejected(self):
        with self.assertRaises(PayloadContractError):
            RevisionMarkerResolver().resolve({}, explicit_marker="   ")

    def test_unresolvable_payload_rejected(self):
        with self.assertRaises(PayloadContractError):
            RevisionMarkerResolver().resolve({"page_id": PAGE, "event_type": "status_changed"})


if __name__ == "__main__":
    unittest.main()

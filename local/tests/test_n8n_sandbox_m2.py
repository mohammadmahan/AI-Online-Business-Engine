"""M2 contract validator — GREEN-OPS-MANUAL-CANONICAL_DB_SMOKE.

Validates the exported workflow JSON against the three M1 standards
(conventions, idempotency, logging) before it may run. This is the
executable form of the M1 acceptance criteria for this workflow.
"""

import json
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
WF = os.path.join(ROOT, "local", "n8n", "workflows",
                  "GREEN-OPS-MANUAL-CANONICAL_DB_SMOKE.json")

# Real tables of the approved D-055 schema (no invented schema).
KNOWN_TABLES = {"seed.size_family", "seed.size_term", "seed.color_term",
                "seed.category_term"}


class TestN8nSandboxM2(unittest.TestCase):

    def setUp(self):
        self.assertTrue(os.path.exists(WF),
                        "M2 sandbox workflow file must exist")
        with open(WF, encoding="utf-8") as f:
            self.data = json.load(f)

    # -- conventions standard ------------------------------------------

    def test_workflow_name_and_tier(self):
        name = self.data.get("name", "")
        self.assertEqual(name, "GREEN-OPS-MANUAL-CANONICAL_DB_SMOKE")
        self.assertTrue(name.startswith("GREEN-"))

    def test_tags_present(self):
        tags = {t.get("name") for t in self.data.get("tags", [])}
        self.assertTrue({"GREEN", "OPS", "PHASE5-M2"} <= tags)

    def test_no_hardcoded_secrets(self):
        blob = json.dumps(self.data).lower()
        for forbidden in ("postgres://", "postgresql://", "engine-local-only",
                          "password=", '"password":'):
            self.assertNotIn(forbidden, blob,
                             f"embedded credential pattern: {forbidden}")

    # -- GREEN tier = read-only by construction --------------------------

    def test_read_only_postgres_query(self):
        pg = [n for n in self.data.get("nodes", [])
              if n.get("type") == "n8n-nodes-base.postgres"]
        self.assertEqual(len(pg), 1, "exactly one postgres node expected")
        query = pg[0]["parameters"]["query"].strip().rstrip(";")
        self.assertTrue(query.upper().startswith("SELECT"),
                        "GREEN tier must be strictly read-only")
        for kw in ("INSERT", "UPDATE", "DELETE", "DROP", "ALTER",
                   "CREATE", "TRUNCATE", "GRANT"):
            self.assertNotIn(kw, query.upper())

    def test_query_targets_real_schema(self):
        pg = [n for n in self.data.get("nodes", [])
              if n.get("type") == "n8n-nodes-base.postgres"][0]
        query = pg["parameters"]["query"].lower()
        self.assertTrue(any(t in query for t in KNOWN_TABLES),
                        "smoke query must target the approved D-055 "
                        "schema, not an invented table")

    # -- logging standard -------------------------------------------------

    def test_engine_log_v1_compliance(self):
        code = [n for n in self.data.get("nodes", [])
                if n.get("type") == "n8n-nodes-base.code"]
        self.assertEqual(len(code), 1)
        body = code[0]["parameters"]["jsCode"]
        for required in ("engine.log.v1", "workflow_id", "execution_id",
                         "timestamp_utc", "trigger_event", "tier_reached",
                         "status", "actor"):
            self.assertIn(required, body)
        # the draft's 'provenance_token' key is not in engine.log.v1 —
        # the schema field is provenance_ref
        self.assertNotIn("provenance_token", body)
        self.assertIn("schema", body)

    def test_workflow_not_active(self):
        """A sandbox workflow ships inactive; activation is an M2
        verification action, not a Git artifact property."""
        self.assertFalse(self.data.get("active", True))


if __name__ == "__main__":
    unittest.main()

"""Contract checks for the committed local n8n workflow assets.

These do not execute n8n or contact any service. They catch malformed JSON,
duplicate node ids, dangling connection targets and obvious credential literals
before an operator imports a workflow.
"""
from __future__ import annotations

import json
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
WORKFLOWS = os.path.join(ROOT, "local", "n8n", "workflows")


class TestN8nAssets(unittest.TestCase):
    def test_expected_workflow_files_exist(self):
        names = sorted(
            name for name in os.listdir(WORKFLOWS) if name.endswith(".json")
        )
        self.assertEqual(
            names,
            [
                "GREEN-OPS-ERROR-GLOBAL_FAILURE_ROUTER.json",
                "GREEN-OPS-MANUAL-CANONICAL_DB_SMOKE.json",
            ],
        )

    def test_each_workflow_is_structurally_valid(self):
        for name in os.listdir(WORKFLOWS):
            if not name.endswith(".json"):
                continue
            with self.subTest(workflow=name):
                with open(os.path.join(WORKFLOWS, name), encoding="utf-8") as f:
                    workflow = json.load(f)
                self.assertIsInstance(workflow, dict)
                nodes = workflow.get("nodes")
                connections = workflow.get("connections")
                self.assertIsInstance(nodes, list)
                self.assertIsInstance(connections, dict)

                names = [node.get("name") for node in nodes]
                self.assertTrue(all(isinstance(value, str) and value for value in names))
                self.assertEqual(len(names), len(set(names)), "node names must be unique")

                for node_name, outputs in connections.items():
                    self.assertIn(node_name, names, "connection source must exist")
                    self.assertIsInstance(outputs, dict)
                    for branches in outputs.values():
                        self.assertIsInstance(branches, list)
                        for branch in branches:
                            for target in branch or []:
                                self.assertIn(
                                    target.get("node"),
                                    names,
                                    "connection target must exist",
                                )

    def test_no_obvious_credentials_or_real_endpoints(self):
        forbidden = re.compile(
            r"(sk-[A-Za-z0-9]{12,}|EAAC[A-Za-z0-9]{12,}|"
            r"bot[0-9]{6,}:[A-Za-z0-9_-]{20,}|"
            r"api[_-]?key\s*[:=]\s*['\"][^'\"]{8,})",
            re.IGNORECASE,
        )
        for name in os.listdir(WORKFLOWS):
            if not name.endswith(".json"):
                continue
            with open(os.path.join(WORKFLOWS, name), encoding="utf-8") as f:
                text = f.read()
            with self.subTest(workflow=name):
                self.assertIsNone(forbidden.search(text))


if __name__ == "__main__":
    unittest.main()
